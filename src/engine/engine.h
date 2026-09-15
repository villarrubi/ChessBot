#pragma once
#include "engine/limits.h"
#include "engine/result.h"
#include "eval/evaluation.h"
#include "eval/nnue.h"
#include "openings/opening_book.h"
#include "search/search.h"
#include "search/transposition_table.h"
#include <atomic>
#include <stdexcept>

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
        auto result = chessbot::evaluateDetailed(board_, evaluationMode_, evaluationParameters_);
        if (nnueEnabled_) {
            result.neural = network_.evaluate(board_);
            result.total = result.neural;
            result.manualAuxiliary = true;
            result.source = "nnue";
            result.networkVersion = network_.version();
        }
        return result;
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
    void setEvaluationFile(const std::string &path) {
        stop();
        evaluationParameters_ =
            path.empty() ? EvaluationParameters{} : loadEvaluationParameters(path);
        table_.clear();
    }
    void setNnueFile(const std::string &path) {
        stop();
        if (path.empty()) {
            network_ = NnueNetwork{};
            nnueEnabled_ = false;
        } else {
            network_.load(path);
        }
        table_.clear();
    }
    void setNnue(bool enabled) {
        stop();
        if (enabled && !network_.loaded())
            throw std::invalid_argument("NNUE requires a loaded NNUEFile");
        nnueEnabled_ = enabled;
        table_.clear();
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
    NnueNetwork network_;
    bool nnueEnabled_ = false;
    SearchMode searchMode_ = SearchMode::Baseline;
    OpeningBook book_;
    BookPolicy bookPolicy_ = BookPolicy::Weighted;
    std::uint64_t bookSeed_ = 1;
    bool ownBook_ = false;
};
} // namespace chessbot
