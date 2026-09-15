#pragma once
#include "board/movegen.h"
#include <array>

namespace chessbot {
using HistoryTable = std::array<std::array<std::array<int, 64>, 64>, 2>;
void orderMoves(MoveList &moves, Move ttMove, Move firstKiller = {}, Move secondKiller = {},
                const HistoryTable *history = nullptr, Color side = White);
} // namespace chessbot
