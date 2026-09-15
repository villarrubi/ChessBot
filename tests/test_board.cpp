#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include "board/attack_tables.h"
#include "board/bitboard.h"
#include "board/movegen.h"
#include <algorithm>
#include <doctest.h>
#include <random>
#include <stdexcept>

using namespace chessbot;
namespace {
bool contains(Board &board, std::string_view uci) {
    const auto moves = legalMoves(board);
    return std::any_of(moves.begin(), moves.end(), [&](Move move) { return move.uci() == uci; });
}
void play(Board &board, std::string_view uci) {
    StateInfo state;
    board.playUci(uci, state);
}
} // namespace

TEST_CASE("square mapping, bit operations and compact move encoding") {
    CHECK(parseSquare("a1") == 0);
    CHECK(parseSquare("h8") == 63);
    for (Square square = 0; square < 64; ++square)
        CHECK(parseSquare(squareName(square)) == square);
    CHECK_THROWS_AS(parseSquare("i1"), std::invalid_argument);
    CHECK_THROWS_AS(squareName(64), std::invalid_argument);
    Bitboard bb = bit(0) | bit(63);
    CHECK(popLsb(bb) == 0);
    CHECK(popLsb(bb) == 63);
    CHECK(bb == 0);
    const Move promotion(54, 63, Pawn, Rook, Knight, Capture);
    CHECK(promotion.uci() == "g7h8n");
    CHECK(promotion.moving() == Pawn);
    CHECK(promotion.captured() == Rook);
    CHECK(promotion.has(Capture));
    CHECK_FALSE(promotion.has(Castle));
    CHECK(ScoreMate - 1 > ScoreMate - 3);
    CHECK(-ScoreMate + 3 > -ScoreMate + 1);
}

TEST_CASE("attack tables and blocked sliding rays") {
    CHECK(std::popcount(attacks().knight[0]) == 2);
    CHECK(std::popcount(attacks().knight[27]) == 8);
    CHECK(std::popcount(attacks().king[63]) == 3);
    CHECK(attacks().pawn[White][8] == bit(17));
    CHECK(attacks().pawn[Black][55] == bit(46));
    CHECK(std::popcount(bishopAttacks(0, 0)) == 7);
    CHECK(bishopAttacks(0, bit(18)) == (bit(9) | bit(18)));
    CHECK(std::popcount(rookAttacks(0, 0)) == 14);
    CHECK((rookAttacks(0, bit(8)) & bit(16)) == 0);
}

TEST_CASE("FEN roundtrip and validation") {
    auto board = Board::startPosition();
    CHECK(board.fen() == StartFen);
    CHECK(board.invariants());
    CHECK(legalMoves(board).size() == 20);
    const std::vector<std::string> invalid = {
        "",
        "8/8/8/8/8/8/8/8 w - - 0 1",
        "4k3/8/8/8/8/8/8/4K3 w - - 0 1 extra",
        "4k3/8/8/8/8/8/8/4K3 x - - 0 1",
        "4k3/8/8/8/8/8/8/4K3 w K - 0 1",
        "4k3/8/8/8/8/8/8/4K2R w KK - 0 1",
        "4k3/8/8/8/8/8/8/4K3 w - e3 0 1",
        "4k3/8/8/8/8/8/8/P3K3 w - - 0 1",
        "4k3/4K3/8/8/8/8/8/8 w - - 0 1",
        "4k3/8/8/8/8/8/8/K3R3 w - - 0 1",
        "4k3/8/8/8/8/8/8/4K3 w - - -1 1",
        "4k3/8/8/8/8/8/8/4K3 w - - 0 0",
        "4k3/8/8/8/8/8/8/4K3 w - - 0 9999999999999999999999999",
        "4k3/8/8/8/8/8/8/4K3 w - - 0x 1",
        "4k3/8/8/8/8/8/8/44 w - - 0 1",
        "4k3/8/8/8/8/8/8/4K4 w - - 0 1",
        "4k3/8/8/8/8/8/8/4K3/8 w - - 0 1",
        "4k3/8/8/8/8/8/8/4X3 w - - 0 1",
        "4k3/8/8/4p3/8/8/8/4K3 w - e6 1 2",
        "4k3/4n3/8/4p3/8/8/8/4K3 w - e6 0 2",
        "4k3/8/8/8/8/8/PPPPPPPP/QQ2K3 w - - 0 1",
        "k3r3/8/8/8/1b5b/8/8/4K3 w - - 0 1",
    };
    for (const auto &fen : invalid) {
        INFO(fen);
        CHECK_THROWS_AS(Board::fromFen(fen), std::invalid_argument);
    }
    play(board, "e2e4");
    CHECK(board.fen() == "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1");
    CHECK(Board::fromFen(board.fen()).fen() == board.fen());
    const auto before = board;
    CHECK_THROWS_AS(play(board, "e7e4"), std::invalid_argument);
    CHECK(board == before);
}

TEST_CASE("castling paths, checks and rook capture rights") {
    auto board = Board::fromFen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1");
    CHECK(contains(board, "e1g1"));
    CHECK(contains(board, "e1c1"));
    const auto original = board;
    StateInfo state;
    const auto move = board.playUci("e1c1", state);
    CHECK(board.at(2) == (Piece{King, White}));
    CHECK(board.at(3) == (Piece{Rook, White}));
    CHECK(board.castlingRights() == 12);
    board.unmakeMove(move, state);
    CHECK(board == original);
    play(board, "a1a8");
    CHECK(board.castlingRights() == (WhiteKing | BlackKing));
    auto throughCheck = Board::fromFen("k4r2/8/8/8/8/8/8/4K2R w K - 0 1");
    CHECK_FALSE(contains(throughCheck, "e1g1"));
    auto checked = Board::fromFen("k3r3/8/8/8/8/8/8/4K2R w K - 0 1");
    CHECK_FALSE(contains(checked, "e1g1"));
    auto blocked = Board::fromFen("4k3/8/8/8/8/8/8/RN2K3 w Q - 0 1");
    CHECK_FALSE(contains(blocked, "e1c1"));
    auto attackedB1 = Board::fromFen("1r2k3/8/8/8/8/8/8/R3K3 w Q - 0 1");
    CHECK(contains(attackedB1, "e1c1"));
    auto black = Board::fromFen("r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1");
    CHECK(contains(black, "e8c8"));
    CHECK(contains(black, "e8g8"));
    play(black, "e8g8");
    CHECK(black.fullmoveNumber() == 2);
    CHECK(black.at(61) == (Piece{Rook, Black}));
}

TEST_CASE("promotions, en passant and pinned en passant hash") {
    auto promotion = Board::fromFen("1r2k3/P7/8/8/8/8/8/4K3 w - - 0 1");
    for (const auto suffix : {"q", "r", "b", "n"}) {
        CHECK(contains(promotion, std::string("a7a8") + suffix));
        CHECK(contains(promotion, std::string("a7b8") + suffix));
    }
    const auto before = promotion;
    StateInfo state;
    const auto move = promotion.playUci("a7b8n", state);
    CHECK(promotion.at(57) == (Piece{Knight, White}));
    CHECK(promotion.halfmoveClock() == 0);
    promotion.unmakeMove(move, state);
    CHECK(promotion == before);

    auto ep = Board::fromFen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2");
    auto noEp = Board::fromFen("4k3/8/8/3pP3/8/8/8/4K3 w - - 0 2");
    CHECK(ep.hasLegalEnPassant());
    CHECK(ep.key() != noEp.key());
    const auto epBefore = ep;
    const auto epMove = ep.playUci("e5d6", state);
    CHECK(ep.at(parseSquare("d5")).type == None);
    CHECK(ep.at(parseSquare("d6")) == (Piece{Pawn, White}));
    ep.unmakeMove(epMove, state);
    CHECK(ep == epBefore);

    auto pinned = Board::fromFen("4k3/8/8/r4pPK/8/8/8/8 w - f6 0 2");
    auto pinnedNoEp = Board::fromFen("4k3/8/8/r4pPK/8/8/8/8 w - - 0 2");
    CHECK_FALSE(contains(pinned, "g5f6"));
    CHECK_FALSE(pinned.hasLegalEnPassant());
    CHECK(pinned.key() == pinnedNoEp.key());
    auto uncapturable = Board::startPosition();
    play(uncapturable, "e2e4");
    auto noTarget = Board::fromFen("rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1");
    CHECK(uncapturable.key() == noTarget.key());
    auto escape = Board::fromFen("k7/8/8/3pP3/4K3/8/8/8 w - d6 0 2");
    CHECK(escape.inCheck(White));
    CHECK(contains(escape, "e5d6"));
}

TEST_CASE("pins, double check, discovered check and king adjacency") {
    auto pinned = Board::fromFen("k3r3/8/8/8/8/8/4R3/4K3 w - - 0 1");
    CHECK_FALSE(contains(pinned, "e2d2"));
    CHECK(contains(pinned, "e2e8"));
    auto doubleCheck = Board::fromFen("k3r3/8/8/8/1b6/8/6R1/4K3 w - - 0 1");
    for (const auto move : legalMoves(doubleCheck))
        CHECK(move.moving() == King);
    auto discovered = Board::fromFen("4k3/8/8/8/8/8/4B3/K3R3 w - - 0 1");
    play(discovered, "e2b5");
    CHECK(discovered.inCheck(Black));
    auto kings = Board::fromFen("8/8/8/8/8/4k3/8/4K3 w - - 0 1");
    CHECK_FALSE(contains(kings, "e1e2"));
    CHECK_FALSE(contains(kings, "e1d2"));
}

TEST_CASE("terminal positions and explicit claimable draw policy") {
    auto mate = Board::fromFen("7k/6Q1/6K1/8/8/8/8/8 b - - 100 90");
    CHECK(mate.status() == GameStatus::Checkmate);
    auto stale = Board::fromFen("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1");
    CHECK(stale.status() == GameStatus::Stalemate);
    auto fifty = Board::fromFen("4k3/8/8/8/8/8/8/R3K3 w - - 100 60");
    CHECK(fifty.status() == GameStatus::FiftyMove);
    CHECK(fifty.status(false) == GameStatus::Ongoing);
    auto almost = Board::fromFen("4k3/8/8/8/8/8/8/R3K3 w - - 99 60");
    CHECK(almost.status() == GameStatus::Ongoing);
    play(almost, "a1a2");
    CHECK(almost.status() == GameStatus::FiftyMove);
    auto board = Board::startPosition();
    for (int cycle = 0; cycle < 2; ++cycle) {
        for (auto move : {"g1f3", "g8f6", "f3g1", "f6g8"})
            play(board, move);
        CHECK(board.isThreefoldRepetition() == (cycle == 1));
    }
    CHECK(board.status() == GameStatus::Threefold);
    CHECK(board.status(false) == GameStatus::Ongoing);
    CHECK_FALSE(Board::fromFen(board.fen()).isThreefoldRepetition());
    play(board, "e2e4");
    CHECK_FALSE(board.isThreefoldRepetition());
    CHECK(board.halfmoveClock() == 0);
}

TEST_CASE("insufficient material conservative cases") {
    for (const auto fen : {"4k3/8/8/8/8/8/8/4K3 w - - 0 1", "4k3/8/8/8/8/8/8/2B1K3 w - - 0 1",
                           "4k3/8/8/8/8/8/8/1N2K3 w - - 0 1", "4kb2/8/8/8/8/8/8/2B1K3 w - - 0 1"}) {
        auto board = Board::fromFen(fen);
        CHECK(board.isInsufficientMaterial());
        CHECK(board.status() == GameStatus::InsufficientMaterial);
    }
    for (const auto fen : {"4k3/8/8/8/8/8/8/1NN1K3 w - - 0 1", "4k1b1/8/8/8/8/8/8/2B1K3 w - - 0 1",
                           "4k3/8/8/8/8/8/8/1NB1K3 w - - 0 1", "4k3/8/8/8/8/8/P7/4K3 w - - 0 1"})
        CHECK_FALSE(Board::fromFen(fen).isInsufficientMaterial());
}

TEST_CASE("zobrist includes side and castling but excludes clocks") {
    const auto first = Board::fromFen("4k3/8/8/8/8/8/8/4K2R w K - 0 1");
    CHECK(first.key() != Board::fromFen("4k3/8/8/8/8/8/8/4K2R w - - 0 1").key());
    CHECK(first.key() != Board::fromFen("4k3/8/8/8/8/8/8/4K2R b K - 0 1").key());
    CHECK(first.key() == Board::fromFen("4k3/8/8/8/8/8/8/4K2R w K - 72 50").key());
}

TEST_CASE("search-only null move restores en passant, clocks, history and hash") {
    auto board = Board::fromFen("4k3/8/8/8/3pP3/8/8/4K3 b - e3 0 1");
    const auto original = board;
    StateInfo state;
    board.makeNullMove(state);
    CHECK(board.sideToMove() == White);
    CHECK(board.enPassantSquare() == NoSquare);
    CHECK(board.halfmoveClock() == 1);
    CHECK(board.fullmoveNumber() == 2);
    CHECK(board.key() == board.recomputeKey());
    CHECK(board.history().size() == original.history().size() + 1);
    board.unmakeNullMove(state);
    CHECK(board == original);
}

TEST_CASE("random legal games restore all state and incremental hashes") {
    std::mt19937 rng(20260914);
    for (int game = 0; game < 40; ++game) {
        auto board = Board::startPosition();
        std::vector<Board> before;
        std::vector<std::pair<Move, StateInfo>> stack;
        for (int ply = 0; ply < 150; ++ply) {
            const auto snapshot = board;
            const auto moves = legalMoves(board);
            CHECK(board == snapshot);
            if (moves.empty())
                break;
            const auto move = moves[rng() % moves.size()];
            before.push_back(board);
            StateInfo state;
            board.makeMove(move, state);
            CHECK(board.invariants());
            CHECK(board.key() == board.recomputeKey());
            CHECK_FALSE(board.inCheck(opposite(board.sideToMove())));
            stack.emplace_back(move, state);
        }
        while (!stack.empty()) {
            const auto [move, state] = stack.back();
            stack.pop_back();
            board.unmakeMove(move, state);
            CHECK(board == before.back());
            before.pop_back();
        }
        CHECK(board == Board::startPosition());
    }
}
