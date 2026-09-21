#include "board/movegen.h"
#include "engine/engine.h"
#include "openings/opening_book.h"
#include <algorithm>
#include <atomic>
#include <doctest.h>
#include <stdexcept>

using namespace chessbot;
namespace {
SearchResult searchFen(std::string_view fen, int depth) {
    Engine engine;
    engine.setPosition(Board::fromFen(fen));
    SearchLimits limits;
    limits.depth = depth;
    return engine.search(limits);
}
} // namespace

TEST_CASE("search finds mate in one and reports distance") {
    const auto result = searchFen("7k/8/6K1/8/8/8/5Q2/8 w - - 0 1", 2);
    CHECK(result.completed);
    CHECK(result.bestMove.uci() == "f2f8");
    CHECK(result.score == ScoreMate - 1);
    REQUIRE_FALSE(result.principalVariation.empty());
    CHECK(result.principalVariation.front() == result.bestMove);
}

TEST_CASE("search finds a unique mate in two") {
    const auto result = searchFen("7k/8/4K3/8/8/8/3Q4/8 w - - 0 1", 4);
    CHECK(result.bestMove.uci() == "e6f7");
    CHECK(result.score == ScoreMate - 3);
    CHECK(result.principalVariation.size() >= 3);
}

TEST_CASE("search handles terminal mate, stalemate and insufficient material") {
    const auto mate = searchFen("7k/6Q1/6K1/8/8/8/8/8 b - - 100 51", 3);
    CHECK_FALSE(mate.bestMove);
    CHECK(mate.score == -ScoreMate);
    const auto stale = searchFen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 3);
    CHECK_FALSE(stale.bestMove);
    CHECK(stale.score == ScoreDraw);
    const auto draw = searchFen("4k3/8/8/8/8/8/8/4K3 w - - 0 1", 3);
    CHECK(draw.score == ScoreDraw);
    const auto fifty = searchFen("4k3/8/8/8/8/8/8/R3K3 w - - 100 51", 3);
    CHECK(fifty.score == ScoreDraw);
}

TEST_CASE("search honors repetition history") {
    auto board = Board::startPosition();
    for (int cycle = 0; cycle < 2; ++cycle)
        for (const auto uci : {"g1f3", "g8f6", "f3g1", "f6g8"}) {
            StateInfo state;
            board.playUci(uci, state);
        }
    Engine engine;
    engine.setPosition(board);
    SearchLimits limits;
    limits.depth = 3;
    CHECK(engine.search(limits).score == ScoreDraw);
}

TEST_CASE("search responds to check with a queen capture") {
    const auto result = searchFen("4k3/8/8/8/8/8/4q3/4KQ2 w - - 0 1", 2);
    CHECK(result.bestMove.uci() == "f1e2");
    CHECK(result.score > 500);
}

TEST_CASE("quiescence sees a forced recapture and avoids losing the queen for a rook") {
    const auto result = searchFen("3rk3/8/8/8/8/8/8/3QK3 w - - 0 1", 1);
    CHECK(result.bestMove.uci() != "d1d8");
    CHECK(result.qnodes > 0);
}

TEST_CASE("pseudo-legal tactical move generation excludes quiet moves") {
    auto board = Board::fromFen("4k3/8/8/8/8/8/4p3/3QK3 w - - 0 1");
    const auto all = legalMoveList(board);
    const auto tactical = pseudoLegalTacticalMoveList(board);
    CHECK_FALSE(tactical.empty());
    CHECK(tactical.size() < all.size());
    for (const auto move : tactical)
        CHECK((move.has(Capture) || move.promotion() != None));
}

TEST_CASE("optimized search recognizes stalemate at the horizon and in full search") {
    for (const int depth : {1, 2, 4}) {
        auto board = Board::fromFen("7k/5K2/8/6Q1/8/8/8/8 w - - 0 1");
        Engine engine;
        engine.setSearchMode(SearchMode::Optimized);
        engine.setPosition(board);
        SearchLimits limits;
        limits.depth = depth;
        for (const auto move : legalMoveList(board))
            if (move.uci() == "g5g6")
                limits.rootMoves.push_back(move);
        REQUIRE(limits.rootMoves.size() == 1);
        const auto result = engine.search(limits);
        CHECK(result.score == ScoreDraw);
        CHECK(result.bestMove.uci() == "g5g6");
    }
}

TEST_CASE("early legal-move detection agrees with full generation and restores the board") {
    for (const auto fen : {"7k/5KQ1/8/8/8/8/8/8 b - - 0 1", "7k/5K2/6Q1/8/8/8/8/8 b - - 0 1",
                           "4r1k1/8/8/3pP3/8/8/8/4K3 w - d6 0 1",
                           "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"}) {
        auto board = Board::fromFen(fen);
        for (int ply = 0; ply < 80; ++ply) {
            const auto before = board.fen();
            const auto key = board.key();
            const auto moves = legalMoveList(board);
            CHECK(hasLegalMove(board, pseudoLegalMoveList(board)) == !moves.empty());
            CHECK(hasLegalMove(board) == !moves.empty());
            CHECK(board.fen() == before);
            CHECK(board.key() == key);
            if (moves.empty())
                break;
            StateInfo state;
            board.makeMove(moves[(ply * 17 + 3) % moves.size()], state);
        }
    }
}

TEST_CASE("iterative deepening callback and persistent transposition table") {
    Engine engine;
    SearchLimits limits;
    limits.depth = 4;
    int callbacks = 0;
    int lastDepth = 0;
    const auto first = engine.search(limits, [&](const SearchResult &iteration, int hashFull) {
        CHECK(iteration.depth > lastDepth);
        CHECK(hashFull >= 0);
        lastDepth = iteration.depth;
        ++callbacks;
    });
    CHECK(callbacks == 4);
    CHECK(first.depth == 4);
    CHECK(first.bestMove);
    const auto second = engine.search(limits);
    CHECK(second.bestMove == first.bestMove);
    CHECK(second.score == first.score);
    CHECK(second.ttHits > 0);
    CHECK(second.nodes < first.nodes);
}

TEST_CASE("node limit stops safely and returns a legal fallback") {
    Engine engine;
    SearchLimits limits;
    limits.nodes = 10;
    const auto result = engine.search(limits);
    CHECK(result.nodes == 10);
    CHECK(result.bestMove);
    auto board = Board::startPosition();
    StateInfo state;
    CHECK_NOTHROW(board.playUci(result.bestMove.uci(), state));
}

TEST_CASE("external stop interrupts infinite analysis") {
    Engine engine;
    SearchLimits limits;
    limits.infinite = true;
    std::atomic_bool sawIteration{false};
    const auto result = engine.search(limits, [&](const SearchResult &, int) {
        sawIteration = true;
        engine.stop();
    });
    CHECK(sawIteration.load());
    CHECK(result.bestMove);
    CHECK(result.depth >= 1);
}

TEST_CASE("parallel search uses configurable threads and a global node limit") {
    Engine engine;
    CHECK(engine.threads() == 1);
    engine.setThreads(4);
    CHECK(engine.threads() == 4);
    SearchLimits limits;
    limits.nodes = 2000;
    const auto result = engine.search(limits);
    CHECK(result.nodes == limits.nodes);
    CHECK(result.bestMove);
    CHECK(result.completed);
    CHECK_THROWS_AS(engine.setThreads(0), std::invalid_argument);
    CHECK_THROWS_AS(engine.setThreads(MaxSearchThreads + 1), std::invalid_argument);
}

TEST_CASE("MultiPV returns distinct ordered root variations") {
    Engine engine;
    SearchLimits limits;
    limits.depth = 2;
    limits.multiPv = 3;
    const auto result = engine.search(limits);
    REQUIRE(result.variations.size() == 3);
    CHECK(result.bestMove == result.variations[0].move);
    CHECK(result.variations[0].score >= result.variations[1].score);
    CHECK(result.variations[1].score >= result.variations[2].score);
    for (std::size_t index = 0; index < result.variations.size(); ++index) {
        REQUIRE_FALSE(result.variations[index].principalVariation.empty());
        CHECK(result.variations[index].principalVariation.front() == result.variations[index].move);
        for (std::size_t other = 0; other < index; ++other)
            CHECK(result.variations[index].move != result.variations[other].move);
    }
}

TEST_CASE("root move restriction and null-move zugzwang guard") {
    Engine engine;
    auto board = Board::startPosition();
    engine.setPosition(board);
    SearchLimits restricted;
    restricted.depth = 3;
    for (const auto move : legalMoves(board))
        if (move.uci() == "e2e4")
            restricted.rootMoves.push_back(move);
    REQUIRE(restricted.rootMoves.size() == 1);
    CHECK(engine.search(restricted).bestMove.uci() == "e2e4");

    engine.setPosition(Board::fromFen("8/8/8/3k4/3p4/3P4/3K4/8 w - - 0 1"));
    engine.setSearchMode(SearchMode::Optimized);
    SearchLimits ending;
    ending.depth = 6;
    const auto result = engine.search(ending);
    CHECK(result.completed);
    CHECK(result.nullMoveAttempts == 0);
}

TEST_CASE("optimized MultiPV preserves complete ordered legal lines across iterations") {
    for (const int threads : {1, 4}) {
        Engine engine;
        engine.setThreads(threads);
        engine.setSearchMode(SearchMode::Optimized);
        SearchLimits limits;
        limits.depth = 6;
        limits.multiPv = 3;
        int reportedDepth = 0;
        Move reportedMove;
        const auto validate = [](const SearchResult &result) {
            REQUIRE(result.variations.size() == 3);
            for (std::size_t i = 0; i < result.variations.size(); ++i) {
                const auto &variation = result.variations[i];
                REQUIRE_FALSE(variation.principalVariation.empty());
                CHECK(variation.principalVariation.front() == variation.move);
                if (i > 0)
                    CHECK(result.variations[i - 1].score >= variation.score);
                for (std::size_t j = 0; j < i; ++j)
                    CHECK(result.variations[j].move != variation.move);
                auto board = Board::startPosition();
                for (const auto move : variation.principalVariation) {
                    StateInfo state;
                    CHECK_NOTHROW(board.playUci(move.uci(), state));
                }
            }
        };
        const auto result = engine.search(limits, [&](const SearchResult &iteration, int) {
            validate(iteration);
            CHECK(iteration.depth > reportedDepth);
            reportedDepth = iteration.depth;
            reportedMove = iteration.bestMove;
        });
        CHECK(result.depth == limits.depth);
        CHECK(reportedDepth == result.depth);
        CHECK(reportedMove == result.bestMove);
        validate(result);
    }
}

TEST_CASE("safe optimized search preserves the fixed-depth reference") {
    Engine engine;
    SearchLimits limits;
    limits.depth = 4;
    engine.setSearchMode(SearchMode::Baseline);
    const auto baseline = engine.search(limits);
    engine.setSearchMode(SearchMode::Optimized);
    const auto optimized = engine.search(limits);
    CHECK(optimized.bestMove == baseline.bestMove);
    CHECK(optimized.score == baseline.score);
    CHECK(optimized.generatedMoves > 0);
    CHECK(optimized.maximumBranching >= 20);
}

TEST_CASE("optimized MultiPV finds mate and the forced queen capture") {
    for (const auto fen : {"7k/8/6K1/8/8/8/5Q2/8 w - - 0 1", "4k3/8/8/8/8/8/4q3/4KQ2 w - - 0 1"}) {
        Engine engine;
        auto board = Board::fromFen(fen);
        const auto expectedVariations = std::min<std::size_t>(3, legalMoveList(board).size());
        engine.setPosition(board);
        engine.setSearchMode(SearchMode::Optimized);
        engine.setThreads(4);
        SearchLimits limits;
        limits.depth = 4;
        limits.multiPv = 3;
        const auto result = engine.search(limits);
        REQUIRE(result.variations.size() == expectedVariations);
        const bool mate = std::string_view(fen).starts_with("7k");
        if (mate) {
            CHECK(result.bestMove.uci() == "f2f8");
            CHECK(result.score == ScoreMate - 1);
        } else {
            CHECK(result.bestMove.captured() == Queen);
            CHECK(result.bestMove.to() == parseSquare("e2"));
            CHECK(result.score > 500);
        }
    }
}

TEST_CASE("native opening book validates moves and applies deterministic policies") {
    OpeningBook book;
    book.load("tests/positions/test_book.tsv");
    CHECK(book.version() == "test-book-v1");
    auto board = Board::startPosition();
    const auto best = book.select(board, BookPolicy::Best, 1);
    REQUIRE(best);
    CHECK(best->entry.move.uci() == "e2e4");
    CHECK(best->entry.games == 100);
    const auto explore = book.select(board, BookPolicy::Explore, 1);
    REQUIRE(explore);
    CHECK(explore->entry.move.uci() == "d2d4");
    CHECK(book.select(board, BookPolicy::Weighted, 42)->entry.move ==
          book.select(board, BookPolicy::Weighted, 42)->entry.move);
    CHECK_THROWS_AS(book.load("tests/positions/missing-book.tsv"), std::invalid_argument);
}

TEST_CASE("transposition table sizing, bounds and replacement") {
    TranspositionTable table(1);
    CHECK(table.megabytes() == 1);
    CHECK(table.hashFullPermille() == 0);
    const Move move(parseSquare("e2"), parseSquare("e4"), Pawn, None, None, DoublePush);
    table.newSearch();
    table.store(42, move, 123, 4, Bound::Exact, 17);
    REQUIRE(table.probe(42));
    CHECK(table.probe(42)->bestMove == move);
    CHECK(table.probe(42)->score == 123);
    CHECK(table.probe(42)->depth == 4);
    CHECK(table.probe(42)->bound == Bound::Exact);
    CHECK(table.probe(42)->rule50 == 17);
    CHECK_FALSE(table.probe(43));
    table.clear();
    CHECK_FALSE(table.probe(42));
    CHECK_THROWS_AS(table.resize(0), std::invalid_argument);
    CHECK_THROWS_AS(table.resize(4097), std::invalid_argument);
}

TEST_CASE("optimized TT keeps deeper results when another worker stores a shallow bound") {
    TranspositionTable table(1);
    table.newSearch();
    table.store(42, {}, 100, 12, Bound::Exact, 0, true);
    table.store(42, {}, 80, 2, Bound::Upper, 0, true);
    REQUIRE(table.probe(42));
    CHECK(table.probe(42)->depth == 12);
    CHECK(table.probe(42)->score == 100);
    table.store(42, {}, 90, 13, Bound::Lower, 0, true);
    CHECK(table.probe(42)->depth == 13);
    // A different rule-50 state or a new search can replace the old entry.
    table.store(42, {}, 0, 2, Bound::Upper, 99, true);
    CHECK(table.probe(42)->rule50 == 99);
    table.newSearch();
    table.store(42, {}, 50, 1, Bound::Upper, 99, true);
    CHECK(table.probe(42)->depth == 1);
}
