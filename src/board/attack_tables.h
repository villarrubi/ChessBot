#pragma once
#include "types.h"
#include <array>
#include <string_view>

namespace chessbot {
struct AttackTables {
    std::array<Bitboard, 64> knight{}, king{};
    std::array<std::array<Bitboard, 64>, 2> pawn{};
    AttackTables();
};
const AttackTables &attacks();
Bitboard bishopAttacks(Square square, Bitboard occupied);
Bitboard rookAttacks(Square square, Bitboard occupied);
std::string_view slidingAttackBackend();
} // namespace chessbot
