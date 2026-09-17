#include "transposition_table.h"
#include <algorithm>
#include <stdexcept>

namespace chessbot {
void TranspositionTable::resize(std::size_t megabytes) {
    if (megabytes < 1 || megabytes > 4096)
        throw std::invalid_argument("Hash must be between 1 and 4096 MB");
    const std::size_t bytes = megabytes * 1024 * 1024;
    std::size_t count = 1;
    while (count <= bytes / sizeof(TTEntry) / 2)
        count *= 2;
    std::vector<std::unique_lock<std::mutex>> locks;
    locks.reserve(LockCount);
    for (auto &mutex : locks_)
        locks.emplace_back(mutex);
    entries_.assign(count, {});
    mask_ = count - 1;
    megabytes_ = megabytes;
    age_.store(0, std::memory_order_relaxed);
}
void TranspositionTable::clear() {
    std::vector<std::unique_lock<std::mutex>> locks;
    locks.reserve(LockCount);
    for (auto &mutex : locks_)
        locks.emplace_back(mutex);
    std::fill(entries_.begin(), entries_.end(), TTEntry{});
}
std::optional<TTEntry> TranspositionTable::probe(std::uint64_t key) const {
    const auto index = key & mask_;
    std::lock_guard lock(locks_[index & (LockCount - 1)]);
    const auto &entry = entries_[index];
    return entry.bound != Bound::None && entry.key == key ? std::optional<TTEntry>(entry)
                                                          : std::nullopt;
}
void TranspositionTable::store(std::uint64_t key, Move move, Score score, int depth, Bound bound,
                               int rule50) {
    const auto index = key & mask_;
    std::lock_guard lock(locks_[index & (LockCount - 1)]);
    auto &entry = entries_[index];
    const auto age = age_.load(std::memory_order_relaxed);
    if (entry.bound == Bound::None || entry.key == key || depth >= entry.depth || entry.age != age)
        entry = {key,
                 move,
                 score,
                 static_cast<std::int16_t>(depth),
                 bound,
                 age,
                 static_cast<std::uint8_t>(std::clamp(rule50, 0, 100))};
}
int TranspositionTable::hashFullPermille() const {
    const auto sample = std::min<std::size_t>(1000, entries_.size());
    if (!sample)
        return 0;
    const auto age = age_.load(std::memory_order_relaxed);
    std::size_t used = 0;
    for (std::size_t i = 0; i < sample; ++i) {
        std::lock_guard lock(locks_[i & (LockCount - 1)]);
        used += entries_[i].bound != Bound::None && entries_[i].age == age;
    }
    return static_cast<int>(used * 1000 / sample);
}
} // namespace chessbot
