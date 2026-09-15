#pragma once
#include "board.h"
#include <array>
#include <cassert>
#include <utility>

namespace chessbot {
class MoveList {
  public:
    void push_back(Move move) {
        assert(size_ < moves_.size());
        moves_[size_++] = move;
    }
    Move *begin() {
        return moves_.data();
    }
    Move *end() {
        return moves_.data() + size_;
    }
    const Move *begin() const {
        return moves_.data();
    }
    const Move *end() const {
        return moves_.data() + size_;
    }
    Move &operator[](std::size_t index) {
        return moves_[index];
    }
    const Move &operator[](std::size_t index) const {
        return moves_[index];
    }
    std::size_t size() const {
        return size_;
    }
    bool empty() const {
        return size_ == 0;
    }
    void resize(std::size_t size) {
        size_ = size;
    }

  private:
    // The maximum number of legal chess moves in one position is 218.
    std::array<Move, 256> moves_{};
    std::size_t size_ = 0;
};

MoveList pseudoLegalMoveList(const Board &board);
MoveList legalMoveList(Board &board);
std::vector<Move> legalMoves(Board &board);
std::uint64_t perft(Board &board, int depth);
std::vector<std::pair<Move, std::uint64_t>> perftDivide(Board &board, int depth);
} // namespace chessbot
