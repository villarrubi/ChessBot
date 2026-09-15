#pragma once
#include <cstdint>
#include <string>
#include <string_view>

namespace chessbot {
using Bitboard = std::uint64_t;
using Square = int;
using Score = int;
constexpr Square NoSquare = -1;
constexpr Score ScoreDraw = 0, ScoreMate = 32000, ScoreInfinity = 32767;
constexpr int MaxPly = 128;
enum Color : int { White, Black };
constexpr Color opposite(Color c) {
    return c == White ? Black : White;
}
enum PieceType : int { Pawn, Knight, Bishop, Rook, Queen, King, None };
enum CastlingRight : unsigned { WhiteKing = 1, WhiteQueen = 2, BlackKing = 4, BlackQueen = 8 };
struct Piece {
    PieceType type = None;
    Color color = White;
    bool operator==(const Piece &) const = default;
};
constexpr int fileOf(Square s) {
    return s % 8;
}
constexpr int rankOf(Square s) {
    return s / 8;
}
constexpr Bitboard bit(Square s) {
    return Bitboard{1} << s;
}
Square parseSquare(std::string_view text);
std::string squareName(Square square);
} // namespace chessbot
