#include "eval/evaluation.h"
#include <doctest.h>

using namespace chessbot;

TEST_CASE("evaluation breakdown sums exactly and uses tapered phase") {
    const auto start = evaluateDetailed(Board::startPosition());
    CHECK(start.phase == 24);
    CHECK(start.total == start.material + start.pieceSquare + start.mobility + start.pawnStructure +
                             start.passedPawns + start.bishopPair + start.rookActivity +
                             start.kingSafety + start.space + start.tempo);
    CHECK(start.material == 0);
    CHECK(start.tempo == 10);

    const auto ending = evaluateDetailed(Board::fromFen("4k3/8/8/8/8/8/8/4K3 w - - 0 1"));
    CHECK(ending.phase == 0);
    CHECK(ending.total == ending.tempo);
}

TEST_CASE("evaluation perspective changes with side to move") {
    const auto white = evaluateDetailed(Board::fromFen("4k3/8/8/8/8/8/P7/Q3K3 w - - 0 1"));
    const auto black = evaluateDetailed(Board::fromFen("4k3/8/8/8/8/8/P7/Q3K3 b - - 0 1"));
    CHECK(white.material > 900);
    CHECK(black.material == -white.material);
    CHECK(black.total == -white.total + 2 * white.tempo);
}

TEST_CASE("mirroring colors and turn preserves side-to-move evaluation") {
    const auto original = evaluateDetailed(
        Board::fromFen("r3k2r/ppp2ppp/2n1bn2/3pp3/3PP3/2N1BN2/PPP2PPP/R3K2R w KQkq - 2 9"));
    const auto mirrored = evaluateDetailed(
        Board::fromFen("r3k2r/ppp2ppp/2n1bn2/3pp3/3PP3/2N1BN2/PPP2PPP/R3K2R b KQkq - 2 9"));
    CHECK(original.total == mirrored.total);
    CHECK(original.material == mirrored.material);
    CHECK(original.phase == mirrored.phase);
}

TEST_CASE("positional components react to their intended features") {
    const auto passed = evaluateDetailed(Board::fromFen("7k/8/4P3/8/8/8/8/4K3 w - - 0 1"));
    const auto blocked = evaluateDetailed(Board::fromFen("7k/4p3/4P3/8/8/8/8/4K3 w - - 0 1"));
    CHECK(passed.passedPawns > 0);
    CHECK(blocked.passedPawns == 0);

    const auto pair = evaluateDetailed(Board::fromFen("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1"));
    CHECK(pair.bishopPair > 0);
    const auto activeRook = evaluateDetailed(Board::fromFen("7k/R7/8/8/8/8/8/4K3 w - - 0 1"));
    CHECK(activeRook.rookActivity > 0);
}

TEST_CASE("basic phase-two profile contains only material, PST and tempo") {
    const auto board = Board::fromFen("7k/8/4P3/8/8/8/8/4K3 w - - 0 1");
    const auto basic = evaluateDetailed(board, EvaluationMode::Basic);
    CHECK(basic.total == basic.material + basic.pieceSquare + basic.tempo);
    CHECK(basic.mobility == 0);
    CHECK(basic.pawnStructure == 0);
    CHECK(basic.passedPawns == 0);
    CHECK(basic.kingSafety == 0);
    CHECK(evaluateDetailed(board).total != basic.total);
}
