#pragma once
#include "board/board.h"
#include <string>

namespace chessbot {
enum class EvaluationMode { Basic, Positional };
struct EvaluationParameters {
    int material = 1000;
    int pieceSquare = 1000;
    int mobility = 1000;
    int pawnStructure = 1000;
    int passedPawns = 1000;
    int bishopPair = 1000;
    int rookActivity = 1000;
    int kingSafety = 1000;
    int space = 1000;
    int tempo = 1000;
    int calibration = 1000;
    std::string version = "hce-default-v1";
};
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
EvalBreakdown evaluateDetailed(const Board &board, EvaluationMode mode = EvaluationMode::Positional,
                               const EvaluationParameters &parameters = {});
EvaluationParameters loadEvaluationParameters(const std::string &path);
inline Score evaluate(const Board &board, EvaluationMode mode = EvaluationMode::Positional,
                      const EvaluationParameters &parameters = {}) {
    return evaluateDetailed(board, mode, parameters).total;
}
} // namespace chessbot
