#pragma once
#include "types.h"
#include <array>

namespace chessbot {
struct Zobrist {
    std::array<std::array<std::array<std::uint64_t, 64>, 6>, 2> piece{};
    std::array<std::uint64_t, 16> castling{};
    std::array<std::uint64_t, 8> enPassant{};
    std::uint64_t side = 0;
    Zobrist();
};
const Zobrist &zobrist();
} // namespace chessbot
