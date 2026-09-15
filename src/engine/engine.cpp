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
    return runSearch(board_, limits, table_, stop_, moveOverheadMs_, evaluationMode_, searchMode_,
                     callback);
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
} // namespace chessbot
