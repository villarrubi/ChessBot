#pragma once
#include "board/move.h"
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <optional>
#include <vector>

namespace chessbot {
enum class Bound : std::uint8_t { None, Exact, Lower, Upper };
struct TTEntry {
    std::uint64_t key = 0;
    Move bestMove;
    Score score = 0;
    std::int16_t depth = -1;
    Bound bound = Bound::None;
    std::uint8_t age = 0;
    std::uint8_t rule50 = 0;
};

class TranspositionTable {
  public:
    explicit TranspositionTable(std::size_t megabytes = 64) {
        resize(megabytes);
    }
    void resize(std::size_t megabytes);
    void clear();
    void newSearch() {
        age_.fetch_add(1, std::memory_order_relaxed);
    }
    std::optional<TTEntry> probe(std::uint64_t key) const;
    void store(std::uint64_t key, Move move, Score score, int depth, Bound bound, int rule50,
               bool preserveDeeper = false);
    int hashFullPermille() const;
    std::size_t megabytes() const {
        return megabytes_;
    }

  private:
    static constexpr std::size_t LockCount = 4096;
    std::vector<TTEntry> entries_;
    std::size_t mask_ = 0;
    std::size_t megabytes_ = 0;
    std::atomic<std::uint8_t> age_{0};
    mutable std::array<std::mutex, LockCount> locks_;
};
} // namespace chessbot
