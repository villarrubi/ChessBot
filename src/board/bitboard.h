#pragma once
#include "types.h"
#include <bit>
#include <cassert>

namespace chessbot {
inline Square popLsb(Bitboard &board) {
    assert(board);
    const auto square = static_cast<Square>(std::countr_zero(board));
    board &= board - 1;
    return square;
}
} // namespace chessbot
