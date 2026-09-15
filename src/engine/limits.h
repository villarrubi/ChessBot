#pragma once
#include "board/move.h"
#include <cstdint>
#include <vector>

namespace chessbot {
enum class SearchMode { Baseline, Optimized };
struct SearchLimits {
    int depth = 0;
    std::uint64_t nodes = 0;
    int moveTimeMs = 0;
    int whiteTimeMs = -1;
    int blackTimeMs = -1;
    int whiteIncrementMs = 0;
    int blackIncrementMs = 0;
    int movesToGo = 0;
    int multiPv = 1;
    std::vector<Move> rootMoves;
    bool infinite = false;
};
} // namespace chessbot
