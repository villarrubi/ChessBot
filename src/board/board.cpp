#include "board.h"
#include "attack_tables.h"
#include "bitboard.h"
#include "movegen.h"
#include "zobrist.h"
#include <algorithm>
#include <cassert>
#include <cctype>
#include <charconv>
#include <sstream>
#include <stdexcept>

namespace chessbot {
namespace {
constexpr std::string_view Symbols = "PNBRQKpnbrqk";
std::uint64_t parseCounter(const std::string &text, bool positive) {
    std::uint64_t result = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), result);
    if (error != std::errc{} || end != text.data() + text.size() || result > 1000000000 ||
        (positive && result == 0))
        throw std::invalid_argument("FEN: invalid counter (allowed range 0/1..1000000000)");
    return result;
}
unsigned cornerRights(Square square) {
    switch (square) {
    case 0:
        return WhiteQueen;
    case 7:
        return WhiteKing;
    case 56:
        return BlackQueen;
    case 63:
        return BlackKing;
    default:
        return 0;
    }
}
} // namespace

Board Board::fromFen(std::string_view fen) {
    Board board;
    std::istringstream input{std::string(fen)};
    std::string placement, turn, rights, ep, halfmove, fullmove, extra;
    if (!(input >> placement >> turn >> rights >> ep >> halfmove >> fullmove) || (input >> extra))
        throw std::invalid_argument("FEN: expected exactly six fields");
    int rank = 7, file = 0;
    bool previousDigit = false;
    for (const char symbol : placement) {
        if (symbol == '/') {
            if (file != 8 || rank == 0)
                throw std::invalid_argument("FEN: invalid rank width/count");
            --rank;
            file = 0;
            previousDigit = false;
        } else if (symbol >= '1' && symbol <= '8') {
            if (previousDigit)
                throw std::invalid_argument("FEN: adjacent empty-square counts");
            file += symbol - '0';
            previousDigit = true;
        } else {
            const auto index = Symbols.find(symbol);
            if (index == std::string_view::npos || file >= 8)
                throw std::invalid_argument("FEN: invalid piece or rank width");
            board.put(rank * 8 + file++,
                      {static_cast<PieceType>(index % 6), index < 6 ? White : Black});
            previousDigit = false;
        }
        if (file > 8)
            throw std::invalid_argument("FEN: rank exceeds eight squares");
    }
    if (rank != 0 || file != 8)
        throw std::invalid_argument("FEN: expected eight complete ranks");
    if (turn != "w" && turn != "b")
        throw std::invalid_argument("FEN: side must be w or b");
    board.side_ = turn == "w" ? White : Black;
    if (rights != "-") {
        for (const char right : rights) {
            const auto index = std::string_view("KQkq").find(right);
            if (index == std::string_view::npos || (board.castling_ & (1U << index)))
                throw std::invalid_argument("FEN: invalid or duplicate castling right");
            board.castling_ |= 1U << index;
        }
    }
    board.ep_ = ep == "-" ? NoSquare : parseSquare(ep);
    board.halfmove_ = parseCounter(halfmove, false);
    board.fullmove_ = parseCounter(fullmove, true);
    for (const Color color : {White, Black}) {
        if (std::popcount(board.pieces(color, King)) != 1)
            throw std::invalid_argument("FEN: exactly one king per color is required");
        if (std::popcount(board.pieces(color, Pawn)) > 8 ||
            std::popcount(board.occupied(color)) > 16)
            throw std::invalid_argument("FEN: too many pieces or pawns");
        if (board.pieces(color, Pawn) & 0xFF000000000000FFULL)
            throw std::invalid_argument("FEN: pawn on promotion rank");
        constexpr Bitboard dark = 0xAA55AA55AA55AA55ULL;
        const int promotionsNeeded =
            std::max(0, std::popcount(board.pieces(color, Knight)) - 2) +
            std::max(0, std::popcount(board.pieces(color, Rook)) - 2) +
            std::max(0, std::popcount(board.pieces(color, Queen)) - 1) +
            std::max(0, std::popcount(board.pieces(color, Bishop) & dark) - 1) +
            std::max(0, std::popcount(board.pieces(color, Bishop) & ~dark) - 1);
        if (promotionsNeeded > 8 - std::popcount(board.pieces(color, Pawn)))
            throw std::invalid_argument("FEN: promoted material exceeds missing pawns");
        const int base = color == White ? 0 : 56;
        const unsigned kingRight = color == White ? WhiteKing : BlackKing;
        const unsigned queenRight = color == White ? WhiteQueen : BlackQueen;
        if ((board.castling_ & (kingRight | queenRight)) &&
            board.at(base + 4) != Piece{King, color})
            throw std::invalid_argument("FEN: castling king is not on its home square");
        if ((board.castling_ & kingRight) && board.at(base + 7) != Piece{Rook, color})
            throw std::invalid_argument("FEN: kingside castling rook is missing");
        if ((board.castling_ & queenRight) && board.at(base) != Piece{Rook, color})
            throw std::invalid_argument("FEN: queenside castling rook is missing");
    }
    if (board.inCheck(opposite(board.side_)))
        throw std::invalid_argument("FEN: the side that just moved is in check");
    const Color enemy = opposite(board.side_);
    const Square king = board.kingSquare(board.side_);
    const auto checkers = (attacks().pawn[board.side_][king] & board.pieces(enemy, Pawn)) |
                          (attacks().knight[king] & board.pieces(enemy, Knight)) |
                          (bishopAttacks(king, board.occupied()) &
                           (board.pieces(enemy, Bishop) | board.pieces(enemy, Queen))) |
                          (rookAttacks(king, board.occupied()) &
                           (board.pieces(enemy, Rook) | board.pieces(enemy, Queen)));
    if (std::popcount(checkers) > 2)
        throw std::invalid_argument("FEN: more than two simultaneous checks");
    if (board.ep_ != NoSquare) {
        const int step = board.side_ == White ? 8 : -8;
        const int expectedRank = board.side_ == White ? 5 : 2;
        if (rankOf(board.ep_) != expectedRank || board.at(board.ep_).type != None ||
            board.at(board.ep_ - step) != Piece{Pawn, opposite(board.side_)} ||
            board.at(board.ep_ + step).type != None || board.halfmove_ != 0)
            throw std::invalid_argument("FEN: inconsistent en passant state");
    }
    board.key_ = board.recomputeKey();
    board.history_.reserve(512);
    board.history_.push_back(board.key_);
    assert(board.invariants());
    return board;
}

std::string Board::fen() const {
    std::ostringstream out;
    for (int rank = 7; rank >= 0; --rank) {
        int empty = 0;
        for (int file = 0; file < 8; ++file) {
            const auto piece = at(rank * 8 + file);
            if (piece.type == None) {
                ++empty;
                continue;
            }
            if (empty) {
                out << empty;
                empty = 0;
            }
            out << Symbols[piece.type + 6 * piece.color];
        }
        if (empty)
            out << empty;
        if (rank)
            out << '/';
    }
    out << (side_ == White ? " w " : " b ");
    if (!castling_)
        out << '-';
    for (unsigned index = 0; index < 4; ++index)
        if (castling_ & (1U << index))
            out << "KQkq"[index];
    out << ' ' << (ep_ == NoSquare ? "-" : squareName(ep_)) << ' ' << halfmove_ << ' ' << fullmove_;
    return out.str();
}

void Board::put(Square square, Piece piece) {
    assert(piece.type != None && at(square).type == None);
    mailbox_[square] = piece;
    pieces_[piece.color][piece.type] |= bit(square);
    occupied_[piece.color] |= bit(square);
    key_ ^= zobrist().piece[piece.color][piece.type][square];
}
void Board::remove(Square square) {
    const auto piece = at(square);
    assert(piece.type != None);
    pieces_[piece.color][piece.type] &= ~bit(square);
    occupied_[piece.color] &= ~bit(square);
    mailbox_[square] = {};
    key_ ^= zobrist().piece[piece.color][piece.type][square];
}
Square Board::kingSquare(Color color) const {
    assert(pieces(color, King));
    return static_cast<Square>(std::countr_zero(pieces(color, King)));
}
bool Board::attackedWith(Square square, Color by, Bitboard occupancy, Bitboard removed) const {
    const auto &table = attacks();
    if (table.pawn[opposite(by)][square] & pieces(by, Pawn) & ~removed)
        return true;
    if (table.knight[square] & pieces(by, Knight) & ~removed)
        return true;
    if (table.king[square] & pieces(by, King) & ~removed)
        return true;
    if (bishopAttacks(square, occupancy) & (pieces(by, Bishop) | pieces(by, Queen)) & ~removed)
        return true;
    return (rookAttacks(square, occupancy) & (pieces(by, Rook) | pieces(by, Queen)) & ~removed) !=
           0;
}
bool Board::isAttacked(Square square, Color by) const {
    return attackedWith(square, by, occupied());
}
bool Board::inCheck(Color color) const {
    return isAttacked(kingSquare(color), opposite(color));
}

bool Board::hasLegalEnPassant() const {
    if (ep_ == NoSquare)
        return false;
    auto candidates = attacks().pawn[opposite(side_)][ep_] & pieces(side_, Pawn);
    const auto captured = bit(ep_ + (side_ == White ? -8 : 8));
    while (candidates) {
        const auto from = popLsb(candidates);
        const auto occupancy = (occupied() & ~bit(from) & ~captured) | bit(ep_);
        // Test the resulting occupancy directly: no recursive make/hash calls.
        if (!attackedWith(kingSquare(side_), opposite(side_), occupancy, captured))
            return true;
    }
    return false;
}
std::uint64_t Board::stateKey() const {
    auto result = zobrist().castling[castling_];
    if (side_ == Black)
        result ^= zobrist().side;
    if (hasLegalEnPassant())
        result ^= zobrist().enPassant[fileOf(ep_)];
    return result;
}
std::uint64_t Board::recomputeKey() const {
    auto result = stateKey();
    for (const Color color : {White, Black}) {
        for (int type = Pawn; type <= King; ++type) {
            auto bb = pieces_[color][type];
            while (bb)
                result ^= zobrist().piece[color][type][popLsb(bb)];
        }
    }
    return result;
}
bool Board::invariants() const {
    Bitboard seen = 0;
    for (const Color color : {White, Black}) {
        Bitboard combined = 0;
        if (std::popcount(pieces(color, King)) != 1)
            return false;
        for (int type = Pawn; type <= King; ++type) {
            auto bb = pieces_[color][type];
            if (seen & bb)
                return false;
            seen |= bb;
            combined |= bb;
            while (bb)
                if (at(popLsb(bb)) != Piece{static_cast<PieceType>(type), color})
                    return false;
        }
        if (combined != occupied_[color])
            return false;
    }
    for (Square square = 0; square < 64; ++square)
        if ((at(square).type != None) != ((seen & bit(square)) != 0))
            return false;
    return !(occupied_[White] & occupied_[Black]) && fullmove_ >= 1 && castling_ <= 15 &&
           key_ == recomputeKey() && !history_.empty() && history_.back() == key_;
}

void Board::makeMove(Move move, StateInfo &state) {
    const Color us = side_;
    const auto moving = at(move.from());
    assert(moving == (Piece{move.moving(), us}));
    const Square captureSquare =
        move.has(EnPassant) ? move.to() + (us == White ? -8 : 8) : move.to();
    const auto captured = at(captureSquare);
    assert(captured.type != King && (captured.type == None || captured.color != us));
    state = {key_, castling_, ep_, halfmove_, fullmove_, captured, history_.size()};
    key_ ^= stateKey();
    remove(move.from());
    if (captured.type != None)
        remove(captureSquare);
    put(move.to(), {move.promotion() == None ? moving.type : move.promotion(), us});
    if (move.has(Castle)) {
        const bool kingSide = move.to() > move.from();
        const Square rookFrom = (us == White ? 0 : 56) + (kingSide ? 7 : 0);
        const Square rookTo = move.from() + (kingSide ? 1 : -1);
        remove(rookFrom);
        put(rookTo, {Rook, us});
    }
    if (moving.type == King)
        castling_ &= ~(us == White ? 3U : 12U);
    castling_ &= ~cornerRights(move.from());
    castling_ &= ~cornerRights(move.to());
    ep_ = move.has(DoublePush) ? (move.from() + move.to()) / 2 : NoSquare;
    halfmove_ = moving.type == Pawn || captured.type != None ? 0 : halfmove_ + 1;
    if (us == Black)
        ++fullmove_;
    side_ = opposite(us);
    key_ ^= stateKey();
    history_.push_back(key_);
    assert(invariants());
}
void Board::unmakeMove(Move move, const StateInfo &state) {
    assert(history_.size() == state.historySize + 1);
    side_ = opposite(side_);
    remove(move.to());
    put(move.from(), {move.moving(), side_});
    if (move.has(Castle)) {
        const bool kingSide = move.to() > move.from();
        const Square rookFrom = (side_ == White ? 0 : 56) + (kingSide ? 7 : 0);
        const Square rookTo = move.from() + (kingSide ? 1 : -1);
        remove(rookTo);
        put(rookFrom, {Rook, side_});
    }
    if (state.captured.type != None) {
        const Square captureSquare =
            move.has(EnPassant) ? move.to() + (side_ == White ? -8 : 8) : move.to();
        put(captureSquare, state.captured);
    }
    castling_ = state.castling;
    ep_ = state.enPassant;
    halfmove_ = state.halfmove;
    fullmove_ = state.fullmove;
    key_ = state.key;
    history_.resize(state.historySize);
    assert(invariants());
}
void Board::makeNullMove(StateInfo &state) {
    assert(!inCheck(side_));
    state = {key_, castling_, ep_, halfmove_, fullmove_, {}, history_.size()};
    key_ ^= stateKey();
    ep_ = NoSquare;
    ++halfmove_;
    if (side_ == Black)
        ++fullmove_;
    side_ = opposite(side_);
    key_ ^= stateKey();
    history_.push_back(key_);
    assert(invariants());
}
void Board::unmakeNullMove(const StateInfo &state) {
    side_ = opposite(side_);
    castling_ = state.castling;
    ep_ = state.enPassant;
    halfmove_ = state.halfmove;
    fullmove_ = state.fullmove;
    key_ = state.key;
    history_.resize(state.historySize);
    assert(invariants());
}
Move Board::playUci(std::string_view text, StateInfo &state) {
    for (const auto move : legalMoves(*this)) {
        if (move.uci() == text) {
            makeMove(move, state);
            return move;
        }
    }
    throw std::invalid_argument("Illegal move: " + std::string(text));
}
bool Board::isThreefoldRepetition() const {
    const auto count = std::min<std::uint64_t>(halfmove_, history_.size() - 1);
    const auto begin = history_.size() - 1 - static_cast<std::size_t>(count);
    return std::count(history_.begin() + static_cast<std::ptrdiff_t>(begin), history_.end(),
                      key_) >= 3;
}
bool Board::isInsufficientMaterial() const {
    if (pieces(White, Pawn) || pieces(Black, Pawn) || pieces(White, Rook) || pieces(Black, Rook) ||
        pieces(White, Queen) || pieces(Black, Queen))
        return false;
    const auto bishops = pieces(White, Bishop) | pieces(Black, Bishop);
    const auto knights = pieces(White, Knight) | pieces(Black, Knight);
    if (std::popcount(bishops | knights) <= 1)
        return true;
    // Bishops only, all on the same square color. KNN vs K is deliberately not a draw.
    constexpr Bitboard dark = 0xAA55AA55AA55AA55ULL;
    return knights == 0 && ((bishops & dark) == 0 || (bishops & ~dark) == 0);
}
GameStatus Board::status(bool claimDraws) {
    if (legalMoves(*this).empty())
        return inCheck(side_) ? GameStatus::Checkmate : GameStatus::Stalemate;
    if (isInsufficientMaterial())
        return GameStatus::InsufficientMaterial;
    if (claimDraws && isThreefoldRepetition())
        return GameStatus::Threefold;
    if (claimDraws && halfmove_ >= 100)
        return GameStatus::FiftyMove;
    return GameStatus::Ongoing;
}
std::string_view statusName(GameStatus status) {
    switch (status) {
    case GameStatus::Ongoing:
        return "ongoing";
    case GameStatus::Checkmate:
        return "checkmate";
    case GameStatus::Stalemate:
        return "stalemate";
    case GameStatus::InsufficientMaterial:
        return "insufficient_material";
    case GameStatus::Threefold:
        return "threefold_repetition";
    case GameStatus::FiftyMove:
        return "fifty_move";
    }
    return "unknown";
}
} // namespace chessbot
