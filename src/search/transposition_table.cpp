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
    entries_.assign(count, {});
    mask_ = count - 1;
    megabytes_ = megabytes;
    age_ = 0;
}
void TranspositionTable::clear() {
    std::fill(entries_.begin(), entries_.end(), TTEntry{});
}
const TTEntry *TranspositionTable::probe(std::uint64_t key) const {
    const auto &entry = entries_[key & mask_];
    return entry.bound != Bound::None && entry.key == key ? &entry : nullptr;
}
void TranspositionTable::store(std::uint64_t key, Move move, Score score, int depth, Bound bound,
                               int rule50) {
    auto &entry = entries_[key & mask_];
    if (entry.bound == Bound::None || entry.key == key || depth >= entry.depth || entry.age != age_)
        entry = {key,
                 move,
                 score,
                 static_cast<std::int16_t>(depth),
                 bound,
                 age_,
                 static_cast<std::uint8_t>(std::clamp(rule50, 0, 100))};
}
int TranspositionTable::hashFullPermille() const {
    const auto sample = std::min<std::size_t>(1000, entries_.size());
    if (!sample)
        return 0;
    std::size_t used = 0;
    for (std::size_t i = 0; i < sample; ++i)
        used += entries_[i].bound != Bound::None && entries_[i].age == age_;
    return static_cast<int>(used * 1000 / sample);
}
} // namespace chessbot
