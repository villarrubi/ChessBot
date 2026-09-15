#pragma once
#include "engine/limits.h"
#include "engine/result.h"
#include "eval/evaluation.h"
#include "openings/opening_book.h"
#include "search/search.h"
#include "search/transposition_table.h"
#include <atomic>

namespace chessbot {
class Engine {
  public:
    Engine();
    void setPosition(const Board &position) {
        board_ = position;
    }
    const Board &position() const {
        return board_;
    }
    SearchResult search(const SearchLimits &limits, const SearchInfoCallback &callback = {});
    // UCI arms the stop flag before publishing its worker thread, preventing an immediate-stop
    // race.
    void prepareSearch() {
        stop_.store(false, std::memory_order_relaxed);
    }
    SearchResult searchPrepared(const SearchLimits &limits,
                                const SearchInfoCallback &callback = {});
    EvalBreakdown evaluateDetailed() const {
        return chessbot::evaluateDetailed(board_, evaluationMode_, evaluationParameters_);
    }
    void stop() {
        stop_.store(true, std::memory_order_relaxed);
    }
    void clear();
    void setHashSize(std::size_t megabytes);
    std::size_t hashSize() const {
        return table_.megabytes();
    }
    void setMoveOverhead(int milliseconds);
    void setEvaluationMode(EvaluationMode mode) {
        stop();
        evaluationMode_ = mode;
        table_.clear();
    }
    EvaluationMode evaluationMode() const {
        return evaluationMode_;
    }
    void setEvaluationFile(const std::string &path) {
        stop();
        evaluationParameters_ =
            path.empty() ? EvaluationParameters{} : loadEvaluationParameters(path);
        table_.clear();
    }
    const EvaluationParameters &evaluationParameters() const {
        return evaluationParameters_;
    }
    int moveOverhead() const {
        return moveOverheadMs_;
    }
    void setOwnBook(bool enabled) {
        stop();
        ownBook_ = enabled;
    }
    void setBookFile(const std::string &path) {
        stop();
        if (path.empty())
            book_.clear();
        else
            book_.load(path);
    }
    void setBookPolicy(BookPolicy policy) {
        stop();
        bookPolicy_ = policy;
    }
    void setBookSeed(std::uint64_t seed) {
        stop();
        bookSeed_ = seed;
    }
    void setSearchMode(SearchMode mode) {
        stop();
        searchMode_ = mode;
        table_.clear();
    }
    SearchMode searchMode() const {
        return searchMode_;
    }

  private:
    Board board_;
    TranspositionTable table_;
    std::atomic_bool stop_{false};
    int moveOverheadMs_ = 10;
    EvaluationMode evaluationMode_ = EvaluationMode::Positional;
    EvaluationParameters evaluationParameters_;
    SearchMode searchMode_ = SearchMode::Baseline;
    OpeningBook book_;
    BookPolicy bookPolicy_ = BookPolicy::Weighted;
    std::uint64_t bookSeed_ = 1;
    bool ownBook_ = false;
};
} // namespace chessbot
