#pragma once
#include "move.h"
#include <array>
#include <vector>

namespace chessbot {
inline constexpr std::string_view StartFen =
    "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

struct StateInfo {
    std::uint64_t key;
    unsigned castling;
    Square enPassant;
    std::uint64_t halfmove, fullmove;
    Piece captured;
    std::size_t historySize;
};
enum class GameStatus { Ongoing, Checkmate, Stalemate, InsufficientMaterial, Threefold, FiftyMove };

class Board {
  public:
    static Board fromFen(std::string_view fen);
    static Board startPosition() {
        return fromFen(StartFen);
    }
    std::string fen() const;
    Piece at(Square square) const {
        return mailbox_[square];
    }
    Bitboard pieces(Color color, PieceType type) const {
        return pieces_[color][type];
    }
    Bitboard occupied() const {
        return occupied_[White] | occupied_[Black];
    }
    Bitboard occupied(Color color) const {
        return occupied_[color];
    }
    Color sideToMove() const {
        return side_;
    }
    unsigned castlingRights() const {
        return castling_;
    }
    Square enPassantSquare() const {
        return ep_;
    }
    std::uint64_t halfmoveClock() const {
        return halfmove_;
    }
    std::uint64_t fullmoveNumber() const {
        return fullmove_;
    }
    std::uint64_t key() const {
        return key_;
    }
    const std::vector<std::uint64_t> &history() const {
        return history_;
    }
    Square kingSquare(Color color) const;
    bool isAttacked(Square square, Color by) const;
    bool inCheck(Color color) const;
    bool hasLegalEnPassant() const;
    std::uint64_t recomputeKey() const;
    bool invariants() const;
    // Low-level contract: move comes from this position's move generator.
    // For untrusted input use playUci(), which checks full legality first.
    void makeMove(Move move, StateInfo &state);
    void unmakeMove(Move move, const StateInfo &state);
    // Search-only null move. It deliberately preserves castling rights and material.
    void makeNullMove(StateInfo &state);
    void unmakeNullMove(const StateInfo &state);
    Move playUci(std::string_view text, StateInfo &state);
    bool isThreefoldRepetition() const;
    bool isInsufficientMaterial() const;
    GameStatus status(bool claimDraws = true);
    bool operator==(const Board &) const = default;

  private:
    std::array<std::array<Bitboard, 6>, 2> pieces_{};
    std::array<Bitboard, 2> occupied_{};
    std::array<Piece, 64> mailbox_{};
    Color side_ = White;
    unsigned castling_ = 0;
    Square ep_ = NoSquare;
    std::uint64_t halfmove_ = 0, fullmove_ = 1, key_ = 0;
    std::vector<std::uint64_t> history_;
    void put(Square square, Piece piece);
    void remove(Square square);
    bool attackedWith(Square square, Color by, Bitboard occupancy, Bitboard removed = 0) const;
    std::uint64_t stateKey() const;
};
std::string_view statusName(GameStatus status);
} // namespace chessbot
