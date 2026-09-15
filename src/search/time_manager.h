#pragma once
#include "board/types.h"
#include "engine/limits.h"
#include <chrono>

namespace chessbot {
class TimeManager {
  public:
    void start(const SearchLimits &limits, Color side, int overheadMs);
    bool hardExpired() const;
    bool softExpired() const;
    std::uint64_t elapsedMs() const;

  private:
    using Clock = std::chrono::steady_clock;
    Clock::time_point start_{};
    int softMs_ = 0;
    int hardMs_ = 0;
    bool timed_ = false;
};
} // namespace chessbot
