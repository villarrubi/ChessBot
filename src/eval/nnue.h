#pragma once
#include "board/board.h"
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace chessbot {
inline constexpr int NnueInputSize = 12 * 64;
inline constexpr int NnueMaximumHidden = 64;

struct NnueAccumulator {
    std::array<std::int32_t, NnueMaximumHidden> values{};
    int size = 0;
    bool operator==(const NnueAccumulator &) const = default;
};

class NnueNetwork {
  public:
    void load(const std::string &path);
    bool loaded() const {
        return hiddenSize_ > 0;
    }
    int hiddenSize() const {
        return hiddenSize_;
    }
    const std::string &version() const {
        return version_;
    }
    std::size_t memoryBytes() const;
    NnueAccumulator refresh(const Board &board) const;
    void updateAfterMove(NnueAccumulator &accumulator, const Board &after, Move move,
                         const StateInfo &state) const;
    Score evaluate(const Board &board, const NnueAccumulator &accumulator) const;
    Score evaluate(const Board &board) const {
        return evaluate(board, refresh(board));
    }

  private:
    int hiddenSize_ = 0, inputQuant_ = 256, outputQuant_ = 256;
    std::string version_;
    std::vector<std::int32_t> hiddenBias_;
    std::vector<std::int16_t> inputWeights_, outputWeights_;
    std::int64_t outputBias_ = 0;

    static int feature(Piece piece, Square square);
    void addFeature(NnueAccumulator &accumulator, Piece piece, Square square, int sign) const;
};
} // namespace chessbot
