#include "zobrist.h"

namespace chessbot {
Zobrist::Zobrist() {
    // Fixed SplitMix64 sequence: hashes are reproducible across platforms.
    std::uint64_t seed = 0x4348455353424F54ULL;
    const auto next = [&seed]() {
        auto z = (seed += 0x9E3779B97F4A7C15ULL);
        z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
        z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
        return z ^ (z >> 31);
    };
    for (auto &color : piece)
        for (auto &type : color)
            for (auto &square : type)
                square = next();
    for (auto &rights : castling)
        rights = next();
    for (auto &file : enPassant)
        file = next();
    side = next();
}
const Zobrist &zobrist() {
    static const Zobrist keys;
    return keys;
}
} // namespace chessbot
