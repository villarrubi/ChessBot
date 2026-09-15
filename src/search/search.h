#pragma once
#include "board/board.h"
#include "engine/limits.h"
#include "engine/result.h"
#include "eval/evaluation.h"
#include "search/transposition_table.h"
#include <atomic>
#include <functional>

namespace chessbot {
using SearchInfoCallback = std::function<void(const SearchResult &, int hashFullPermille)>;

SearchResult runSearch(Board board, const SearchLimits &limits, TranspositionTable &table,
                       std::atomic_bool &stop, int moveOverheadMs, EvaluationMode evaluationMode,
                       const EvaluationParameters &evaluationParameters, SearchMode searchMode,
                       const SearchInfoCallback &callback = {});
} // namespace chessbot
