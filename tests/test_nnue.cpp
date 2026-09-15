#include "board/movegen.h"
#include "engine/engine.h"
#include "eval/nnue.h"
#include <doctest.h>
#include <filesystem>
#include <fstream>
#include <random>

using namespace chessbot;
namespace {
std::filesystem::path writeTestNetwork() {
    const auto path = std::filesystem::temp_directory_path() / "chessbot-test-network.nnue";
    std::ofstream output(path);
    output << "CHESSBOT_NNUE 1\nversion test-nnue-v1\n"
              "architecture sparse_768x2_relu_1\nhidden_size 2\n"
              "input_quant 1\noutput_quant 1\nhidden_bias 0 0\ninput_weights";
    constexpr int values[] = {100, 320, 330, 500, 900, 0};
    for (int color = 0; color < 2; ++color)
        for (int type = 0; type < 6; ++type)
            for (int square = 0; square < 64; ++square)
                output << ' ' << (color == White ? values[type] : 0) << ' '
                       << (color == Black ? values[type] : 0);
    output << "\noutput_bias 0\noutput_weights 1 -1\nEND\n";
    return path;
}
void checkMove(NnueNetwork &network, Board board, std::string_view moveName) {
    auto incremental = network.refresh(board);
    const auto original = incremental;
    Move selected;
    for (const auto move : legalMoveList(board))
        if (move.uci() == moveName)
            selected = move;
    REQUIRE(selected);
    StateInfo state;
    board.makeMove(selected, state);
    network.updateAfterMove(incremental, board, selected, state);
    CHECK(incremental == network.refresh(board));
    CHECK(network.evaluate(board, incremental) == network.evaluate(board));
    board.unmakeMove(selected, state);
    incremental = original;
    CHECK(incremental == network.refresh(board));
}
} // namespace

TEST_CASE("NNUE loader and quantized inference use side-to-move perspective") {
    const auto path = writeTestNetwork();
    NnueNetwork network;
    network.load(path.string());
    CHECK(network.version() == "test-nnue-v1");
    CHECK(network.hiddenSize() == 2);
    CHECK(network.memoryBytes() > 0);
    CHECK(network.evaluate(Board::startPosition()) == 0);
    CHECK(network.evaluate(Board::fromFen("4k3/8/8/8/8/8/P7/Q3K3 w - - 0 1")) == 1000);
    CHECK(network.evaluate(Board::fromFen("4k3/8/8/8/8/8/P7/Q3K3 b - - 0 1")) == -1000);
    std::filesystem::remove(path);
}

TEST_CASE(
    "NNUE accumulator updates and restores quiet, capture, castle, en passant and promotion") {
    const auto path = writeTestNetwork();
    NnueNetwork network;
    network.load(path.string());
    checkMove(network, Board::startPosition(), "e2e4");
    checkMove(network, Board::fromFen("4k3/8/8/8/8/8/4q3/4KQ2 w - - 0 1"), "f1e2");
    checkMove(network, Board::fromFen("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"), "e1g1");
    checkMove(network, Board::fromFen("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"), "e5d6");
    checkMove(network, Board::fromFen("4k3/P7/8/8/8/8/8/4K3 w - - 0 1"), "a7a8q");

    auto board = Board::startPosition();
    auto accumulator = network.refresh(board);
    std::mt19937 randomizer(19);
    std::vector<Move> played;
    std::vector<StateInfo> states;
    std::vector<NnueAccumulator> previousAccumulators;
    for (int ply = 0; ply < 80; ++ply) {
        auto moves = legalMoveList(board);
        if (moves.empty())
            break;
        const auto move = moves[randomizer() % moves.size()];
        StateInfo state;
        previousAccumulators.push_back(accumulator);
        board.makeMove(move, state);
        network.updateAfterMove(accumulator, board, move, state);
        played.push_back(move);
        states.push_back(state);
        CHECK(accumulator == network.refresh(board));
    }
    while (!played.empty()) {
        board.unmakeMove(played.back(), states.back());
        accumulator = previousAccumulators.back();
        CHECK(accumulator == network.refresh(board));
        played.pop_back();
        states.pop_back();
        previousAccumulators.pop_back();
    }
    CHECK(board.fen() == StartFen);
    std::filesystem::remove(path);
}

TEST_CASE("engine exposes neural score and manual evaluation as auxiliary evidence") {
    const auto path = writeTestNetwork();
    Engine engine;
    engine.setNnueFile(path.string());
    engine.setNnue(true);
    engine.setPosition(Board::fromFen("4k3/8/8/8/8/8/P7/Q3K3 w - - 0 1"));
    const auto report = engine.evaluateDetailed();
    CHECK(report.source == "nnue");
    CHECK(report.networkVersion == "test-nnue-v1");
    CHECK(report.manualAuxiliary);
    CHECK(report.total == report.neural);
    CHECK(report.manualTotal != 0);
    SearchLimits limits;
    limits.depth = 1;
    CHECK(engine.search(limits).bestMove);
    engine.setNnue(false);
    CHECK(engine.evaluateDetailed().source == "hce");
    std::filesystem::remove(path);
}

TEST_CASE("NNUE rejects malformed files and cannot be enabled before loading") {
    Engine engine;
    CHECK_THROWS_AS(engine.setNnue(true), std::invalid_argument);
    const auto path = std::filesystem::temp_directory_path() / "chessbot-invalid-network.nnue";
    {
        std::ofstream output(path);
        output << "invalid\n";
    }
    CHECK_THROWS_AS(engine.setNnueFile(path.string()), std::invalid_argument);
    std::filesystem::remove(path);
}
