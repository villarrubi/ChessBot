#include "board/movegen.h"
#include <array>
#include <doctest.h>
#include <stdexcept>
using namespace chessbot;

TEST_CASE("starting position PERFT and divide") {
    auto board = Board::startPosition();
    const auto original = board;
    const std::array<std::uint64_t, 5> expected{1, 20, 400, 8902, 197281};
    for (int depth = 0; depth <= 4; ++depth) {
        CHECK(perft(board, depth) == expected[depth]);
        CHECK(board == original);
    }
    std::uint64_t sum = 0;
    for (const auto &[move, nodes] : perftDivide(board, 3)) {
        (void)move;
        sum += nodes;
    }
    CHECK(sum == 8902);
    CHECK(board == original);
    CHECK_THROWS_AS(perft(board, -1), std::invalid_argument);
    CHECK_THROWS_AS(perftDivide(board, 0), std::invalid_argument);
}

TEST_CASE("special-position PERFT regression suite") {
    struct Fixture {
        const char *fen;
        std::array<std::uint64_t, 3> nodes;
    };
    const Fixture fixtures[] = {
        {"r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", {48, 2039, 97862}},
        {"8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", {14, 191, 2812}},
        {"r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", {6, 264, 9467}},
        {"rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", {44, 1486, 62379}},
    };
    for (const auto &fixture : fixtures) {
        INFO(fixture.fen);
        auto board = Board::fromFen(fixture.fen);
        const auto original = board;
        for (int depth = 1; depth <= 3; ++depth)
            CHECK(perft(board, depth) == fixture.nodes[depth - 1]);
        CHECK(board == original);
    }
}

TEST_CASE("slow full starting position PERFT to depth six") {
    auto board = Board::startPosition();
    const auto original = board;
    CHECK(perft(board, 5) == 4865609);
    CHECK(perft(board, 6) == 119060324);
    CHECK(board == original);
}
