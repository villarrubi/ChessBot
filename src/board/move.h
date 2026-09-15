#pragma once
#include "types.h"

namespace chessbot {
enum MoveFlag : unsigned { Capture = 1, EnPassant = 2, Castle = 4, DoublePush = 8 };
class Move {
    std::uint32_t value_ = 0;

  public:
    Move() = default;
    constexpr Move(Square from, Square to, PieceType moving, PieceType captured = None,
                   PieceType promotion = None, unsigned flags = 0)
        : value_(static_cast<unsigned>(from) | (static_cast<unsigned>(to) << 6) |
                 (static_cast<unsigned>(promotion) << 12) | (flags << 15) |
                 (static_cast<unsigned>(moving) << 19) | (static_cast<unsigned>(captured) << 22)) {}
    Square from() const {
        return value_ & 63;
    }
    Square to() const {
        return (value_ >> 6) & 63;
    }
    PieceType promotion() const {
        return static_cast<PieceType>((value_ >> 12) & 7);
    }
    PieceType moving() const {
        return static_cast<PieceType>((value_ >> 19) & 7);
    }
    PieceType captured() const {
        return static_cast<PieceType>((value_ >> 22) & 7);
    }
    bool has(MoveFlag flag) const {
        return ((value_ >> 15) & flag) != 0;
    }
    explicit operator bool() const {
        return value_ != 0;
    }
    std::uint32_t value() const {
        return value_;
    }
    std::string uci() const;
    bool operator==(const Move &) const = default;
};
static_assert(sizeof(Move) == sizeof(std::uint32_t));
} // namespace chessbot
