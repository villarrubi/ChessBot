#pragma once
#include "board/move.h"
#include <cstdint>
#include <vector>

namespace chessbot {
struct RootVariation {
    Move move;
    Score score = ScoreDraw;
    std::vector<Move> principalVariation;
};
struct SearchResult {
    Move bestMove;
    Move ponderMove;
    Score score = ScoreDraw;
    int depth = 0;
    int selectiveDepth = 0;
    std::uint64_t nodes = 0;
    std::uint64_t qnodes = 0;
    std::uint64_t timeMs = 0;
    std::uint64_t ttHits = 0;
    std::uint64_t betaCutoffs = 0;
    std::uint64_t firstMoveCutoffs = 0;
    std::uint64_t generatedMoves = 0;
    std::uint64_t aspirationResearches = 0;
    std::uint64_t nullMoveAttempts = 0;
    std::uint64_t nullMoveCutoffs = 0;
    std::uint64_t lmrReductions = 0;
    std::uint64_t lmrResearches = 0;
    std::uint64_t futilityPrunes = 0;
    int maximumBranching = 0;
    std::vector<Move> principalVariation;
    std::vector<RootVariation> variations;
    bool completed = false;
};
} // namespace chessbot
