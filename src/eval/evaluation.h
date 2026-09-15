#pragma once
#include "board/board.h"

namespace chessbot {
enum class EvaluationMode { Basic, Positional };
struct EvalBreakdown {
    Score material = 0;
    Score pieceSquare = 0;
    Score mobility = 0;
    Score pawnStructure = 0;
    Score passedPawns = 0;
    Score bishopPair = 0;
    Score rookActivity = 0;
    Score kingSafety = 0;
    Score space = 0;
    Score tempo = 0;
    Score total = 0;
    int phase = 0;
};

// All public evaluation scores use the side-to-move perspective.
EvalBreakdown evaluateDetailed(const Board &board,
                               EvaluationMode mode = EvaluationMode::Positional);
inline Score evaluate(const Board &board, EvaluationMode mode = EvaluationMode::Positional) {
    return evaluateDetailed(board, mode).total;
}
} // namespace chessbot
