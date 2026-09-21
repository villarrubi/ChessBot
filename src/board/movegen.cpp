#include "movegen.h"
#include "attack_tables.h"
#include "bitboard.h"
#include <stdexcept>

namespace chessbot {
MoveList pseudoLegalMoveList(const Board &board) {
    MoveList moves;
    const Color us = board.sideToMove(), them = opposite(us);
    const auto occupied = board.occupied();
    const auto targets = ~board.occupied(us) & ~board.pieces(them, King);
    const auto emit = [&](Square from, Square to, PieceType type, unsigned flags = 0) {
        const auto captured = flags & EnPassant ? Pawn : board.at(to).type;
        if (captured != None)
            flags |= Capture;
        if (type == Pawn && (rankOf(to) == 0 || rankOf(to) == 7)) {
            for (const PieceType promotion : {Queen, Rook, Bishop, Knight})
                moves.push_back(Move(from, to, type, captured, promotion, flags));
        } else {
            moves.push_back(Move(from, to, type, captured, None, flags));
        }
    };
    auto pawns = board.pieces(us, Pawn);
    const int step = us == White ? 8 : -8;
    while (pawns) {
        const auto from = popLsb(pawns);
        const auto to = from + step;
        if (to >= 0 && to < 64 && !(occupied & bit(to))) {
            emit(from, to, Pawn);
            if (rankOf(from) == (us == White ? 1 : 6) && !(occupied & bit(to + step)))
                emit(from, to + step, Pawn, DoublePush);
        }
        auto captures = attacks().pawn[us][from] & board.occupied(them) & targets;
        while (captures)
            emit(from, popLsb(captures), Pawn);
        const auto ep = board.enPassantSquare();
        if (ep != NoSquare && (attacks().pawn[us][from] & bit(ep)))
            emit(from, ep, Pawn, EnPassant);
    }
    for (const PieceType type : {Knight, Bishop, Rook, Queen, King}) {
        auto pieces = board.pieces(us, type);
        while (pieces) {
            const auto from = popLsb(pieces);
            Bitboard destinations = 0;
            switch (type) {
            case Knight:
                destinations = attacks().knight[from];
                break;
            case Bishop:
                destinations = bishopAttacks(from, occupied);
                break;
            case Rook:
                destinations = rookAttacks(from, occupied);
                break;
            case Queen:
                destinations = bishopAttacks(from, occupied) | rookAttacks(from, occupied);
                break;
            case King:
                destinations = attacks().king[from];
                break;
            default:
                break;
            }
            destinations &= targets;
            while (destinations)
                emit(from, popLsb(destinations), type);
        }
    }
    const int base = us == White ? 0 : 56;
    if (!board.inCheck(us)) {
        const unsigned kingRight = us == White ? WhiteKing : BlackKing;
        const unsigned queenRight = us == White ? WhiteQueen : BlackQueen;
        if ((board.castlingRights() & kingRight) && !(occupied & (bit(base + 5) | bit(base + 6))) &&
            !board.isAttacked(base + 5, them) && !board.isAttacked(base + 6, them))
            emit(base + 4, base + 6, King, Castle);
        if ((board.castlingRights() & queenRight) &&
            !(occupied & (bit(base + 1) | bit(base + 2) | bit(base + 3))) &&
            !board.isAttacked(base + 3, them) && !board.isAttacked(base + 2, them))
            emit(base + 4, base + 2, King, Castle);
    }
    return moves;
}
MoveList legalMoveList(Board &board) {
    auto candidates = pseudoLegalMoveList(board);
    const Color us = board.sideToMove();
    std::size_t count = 0;
    for (const auto move : candidates) {
        StateInfo state;
        board.makeMove(move, state);
        const bool legal = !board.inCheck(us);
        board.unmakeMove(move, state);
        if (legal)
            candidates[count++] = move;
    }
    candidates.resize(count);
    return candidates;
}
MoveList pseudoLegalTacticalMoveList(const Board &board) {
    auto candidates = pseudoLegalMoveList(board);
    std::size_t count = 0;
    for (const auto move : candidates) {
        if (!move.has(Capture) && move.promotion() == None)
            continue;
        candidates[count++] = move;
    }
    candidates.resize(count);
    return candidates;
}
std::vector<Move> legalMoves(Board &board) {
    const auto moves = legalMoveList(board);
    return {moves.begin(), moves.end()};
}
std::uint64_t perft(Board &board, int depth) {
    if (depth < 0)
        throw std::invalid_argument("PERFT depth must be nonnegative");
    if (depth == 0)
        return 1;
    const auto moves = legalMoves(board);
    if (depth == 1)
        return moves.size();
    std::uint64_t nodes = 0;
    for (const auto move : moves) {
        StateInfo state;
        board.makeMove(move, state);
        nodes += perft(board, depth - 1);
        board.unmakeMove(move, state);
    }
    return nodes;
}
std::vector<std::pair<Move, std::uint64_t>> perftDivide(Board &board, int depth) {
    if (depth < 1)
        throw std::invalid_argument("Divide depth must be positive");
    std::vector<std::pair<Move, std::uint64_t>> result;
    for (const auto move : legalMoves(board)) {
        StateInfo state;
        board.makeMove(move, state);
        const auto nodes = perft(board, depth - 1);
        board.unmakeMove(move, state);
        result.emplace_back(move, nodes);
    }
    return result;
}
} // namespace chessbot
