#include "engine.h"
#include <stdexcept>

namespace chessbot {
Engine::Engine() : board_(Board::startPosition()), table_(64) {}
SearchResult Engine::search(const SearchLimits &limits, const SearchInfoCallback &callback) {
    prepareSearch();
    return searchPrepared(limits, callback);
}
SearchResult Engine::searchPrepared(const SearchLimits &limits,
                                    const SearchInfoCallback &callback) {
    if (ownBook_ && limits.rootMoves.empty()) {
        if (const auto selection = book_.select(board_, bookPolicy_, bookSeed_)) {
            SearchResult result;
            result.bestMove = selection->entry.move;
            result.principalVariation = {result.bestMove};
            result.variations = {{result.bestMove, ScoreDraw, {result.bestMove}}};
            result.fromBook = result.completed = true;
            result.bookVersion = selection->version;
            result.bookPolicy = bookPolicyName(bookPolicy_);
            result.bookSource = selection->entry.source;
            result.bookGames = selection->entry.games;
            result.bookWeight = selection->entry.weight;
            return result;
        }
    }
    return runSearch(board_, limits, table_, stop_, moveOverheadMs_, evaluationMode_,
                     evaluationParameters_, nnueEnabled_ ? &network_ : nullptr, searchMode_,
                     threads_, callback);
}
void Engine::clear() {
    stop();
    table_.clear();
}
void Engine::setHashSize(std::size_t megabytes) {
    stop();
    table_.resize(megabytes);
}
void Engine::setMoveOverhead(int milliseconds) {
    if (milliseconds < 0 || milliseconds > 5000)
        throw std::invalid_argument("Move Overhead must be between 0 and 5000 ms");
    moveOverheadMs_ = milliseconds;
}
void Engine::setThreads(int count) {
    if (count < 1 || count > MaxSearchThreads)
        throw std::invalid_argument("Threads must be between 1 and " +
                                    std::to_string(MaxSearchThreads));
    stop();
    threads_ = count;
}
} // namespace chessbot
