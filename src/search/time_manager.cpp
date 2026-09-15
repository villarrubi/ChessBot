#include "time_manager.h"
#include <algorithm>

namespace chessbot {
void TimeManager::start(const SearchLimits &limits, Color side, int overheadMs) {
    start_ = Clock::now();
    timed_ = false;
    softMs_ = hardMs_ = 0;
    if (limits.infinite)
        return;
    if (limits.moveTimeMs > 0) {
        softMs_ = hardMs_ = std::max(1, limits.moveTimeMs - overheadMs);
        timed_ = true;
        return;
    }
    const int remaining = side == White ? limits.whiteTimeMs : limits.blackTimeMs;
    const int increment = side == White ? limits.whiteIncrementMs : limits.blackIncrementMs;
    if (remaining < 0)
        return;
    const int usable = std::max(1, remaining - overheadMs);
    const int moves = limits.movesToGo > 0 ? limits.movesToGo : 30;
    softMs_ = std::clamp(usable / moves + increment * 3 / 4, 1, usable);
    hardMs_ = std::clamp(softMs_ * 4, 1, std::max(1, usable / 2));
    hardMs_ = std::max(softMs_, hardMs_);
    timed_ = true;
}
std::uint64_t TimeManager::elapsedMs() const {
    return static_cast<std::uint64_t>(
        std::chrono::duration_cast<std::chrono::milliseconds>(Clock::now() - start_).count());
}
bool TimeManager::hardExpired() const {
    return timed_ && elapsedMs() >= static_cast<std::uint64_t>(hardMs_);
}
bool TimeManager::softExpired() const {
    return timed_ && elapsedMs() >= static_cast<std::uint64_t>(softMs_);
}
} // namespace chessbot
