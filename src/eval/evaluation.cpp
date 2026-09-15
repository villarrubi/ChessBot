#include "evaluation.h"
#include "board/attack_tables.h"
#include "board/bitboard.h"
#include <algorithm>
#include <array>
#include <bit>
#include <cstdlib>

namespace chessbot {
namespace {
constexpr int MaxPhase = 24;
constexpr std::array<int, 6> MgValue{100, 320, 330, 500, 900, 0};
constexpr std::array<int, 6> EgValue{120, 305, 325, 510, 900, 0};
constexpr std::array<int, 6> PhaseWeight{0, 1, 1, 2, 4, 0};
constexpr Bitboard Center = 0x0000001818000000ULL;
constexpr Bitboard ExtendedCenter = 0x00003C3C3C3C0000ULL;

struct PairScore {
    int mg = 0;
    int eg = 0;
    PairScore &operator+=(PairScore other) {
        mg += other.mg;
        eg += other.eg;
        return *this;
    }
};

int relativeRank(Color color, Square square) {
    return color == White ? rankOf(square) : 7 - rankOf(square);
}
int centerDistance(Square square) {
    return std::abs(fileOf(square) * 2 - 7) + std::abs(rankOf(square) * 2 - 7);
}
PairScore pieceSquare(PieceType type, Color color, Square square) {
    const int rank = relativeRank(color, square);
    const int center = 14 - centerDistance(square);
    switch (type) {
    case Pawn:
        return {rank * 5 + center / 3, rank * 9 + center / 4};
    case Knight:
        return {center * 4 - 28, center * 3 - 21};
    case Bishop:
        return {center * 2 - 12 + rank, center * 2 - 12};
    case Rook:
        return {rank * 2, rank * 4};
    case Queen:
        return {center - 8, center - 8};
    case King: {
        const int castled = (fileOf(square) == 6 || fileOf(square) == 2) && rank == 0 ? 28 : 0;
        return {castled - center * 3, center * 4 - 28};
    }
    default:
        return {};
    }
}
int blend(PairScore score, int phase) {
    return (score.mg * phase + score.eg * (MaxPhase - phase)) / MaxPhase;
}
int sign(Color color) {
    return color == White ? 1 : -1;
}
bool passedPawn(const Board &board, Color color, Square square) {
    const Color enemy = opposite(color);
    const int direction = color == White ? 1 : -1;
    for (int rank = rankOf(square) + direction; rank >= 0 && rank < 8; rank += direction) {
        for (int file = std::max(0, fileOf(square) - 1); file <= std::min(7, fileOf(square) + 1);
             ++file) {
            if (board.pieces(enemy, Pawn) & bit(rank * 8 + file))
                return false;
        }
    }
    return true;
}
bool candidatePassedPawn(const Board &board, Color color, Square square) {
    if (passedPawn(board, color, square))
        return false;
    const Color enemy = opposite(color);
    int enemyAhead = 0, friendlySupport = 0;
    const int direction = color == White ? 1 : -1;
    for (int rank = rankOf(square) + direction; rank >= 0 && rank < 8; rank += direction) {
        for (int file = std::max(0, fileOf(square) - 1); file <= std::min(7, fileOf(square) + 1);
             ++file)
            enemyAhead += (board.pieces(enemy, Pawn) & bit(rank * 8 + file)) != 0;
    }
    for (int rank = std::max(0, rankOf(square) - 1); rank <= std::min(7, rankOf(square) + 1);
         ++rank)
        for (int file : {fileOf(square) - 1, fileOf(square) + 1})
            if (file >= 0 && file < 8)
                friendlySupport += (board.pieces(color, Pawn) & bit(rank * 8 + file)) != 0;
    return friendlySupport >= enemyAhead;
}
Bitboard pieceAttacks(const Board &board, PieceType type, Square square) {
    switch (type) {
    case Knight:
        return attacks().knight[square];
    case Bishop:
        return bishopAttacks(square, board.occupied());
    case Rook:
        return rookAttacks(square, board.occupied());
    case Queen:
        return bishopAttacks(square, board.occupied()) | rookAttacks(square, board.occupied());
    default:
        return 0;
    }
}
int kingDistance(Square a, Square b) {
    return std::max(std::abs(fileOf(a) - fileOf(b)), std::abs(rankOf(a) - rankOf(b)));
}
} // namespace

EvalBreakdown evaluateDetailed(const Board &board, EvaluationMode mode) {
    EvalBreakdown result;
    std::array<PairScore, 10> terms{};
    std::array<Bitboard, 2> pawnControl{};
    for (const Color color : {White, Black}) {
        auto pawns = board.pieces(color, Pawn);
        while (pawns)
            pawnControl[color] |= attacks().pawn[color][popLsb(pawns)];
    }
    int phase = 0;

    for (const Color color : {White, Black}) {
        const int side = sign(color);
        for (int rawType = Pawn; rawType <= King; ++rawType) {
            const auto type = static_cast<PieceType>(rawType);
            auto pieces = board.pieces(color, type);
            phase += std::popcount(pieces) * PhaseWeight[type];
            while (pieces) {
                const Square square = popLsb(pieces);
                terms[0] += {side * MgValue[type], side * EgValue[type]};
                const auto pst = pieceSquare(type, color, square);
                terms[1] += {side * pst.mg, side * pst.eg};
                if (type >= Knight && type <= Queen) {
                    const auto destinations =
                        pieceAttacks(board, type, square) & ~board.occupied(color);
                    const int safe = std::popcount(destinations & ~pawnControl[opposite(color)]);
                    const int count = std::popcount(destinations);
                    const int weight = type == Queen ? 1 : type == Rook ? 2 : 3;
                    terms[2] += {side * (count * weight + safe), side * count * weight};
                    const Bitboard valuableTargets = board.occupied(opposite(color)) &
                                                     ~board.pieces(opposite(color), Pawn) &
                                                     ~board.pieces(opposite(color), King);
                    terms[2] += {side * 4 * std::popcount(destinations & valuableTargets),
                                 side * 2 * std::popcount(destinations & valuableTargets)};
                    if (count <= 1)
                        terms[1] += {side * -10, side * -5};
                    if ((type == Knight || type == Bishop) && relativeRank(color, square) >= 3 &&
                        (attacks().pawn[opposite(color)][square] & board.pieces(color, Pawn)) &&
                        !(pawnControl[opposite(color)] & bit(square)))
                        terms[1] += {side * 18, side * 10};
                }
            }
        }

        auto pawns = board.pieces(color, Pawn);
        int islands = 0;
        bool previousFile = false;
        for (int file = 0; file < 8; ++file) {
            const Bitboard fileMask = 0x0101010101010101ULL << file;
            const int count = std::popcount(pawns & fileMask);
            if (count && !previousFile)
                ++islands;
            previousFile = count != 0;
            if (count > 1)
                terms[3] += {side * -14 * (count - 1), side * -20 * (count - 1)};
        }
        terms[3] += {side * -4 * std::max(0, islands - 1), side * -3 * std::max(0, islands - 1)};

        constexpr Bitboard darkSquares = 0xAA55AA55AA55AA55ULL;
        auto bishops = board.pieces(color, Bishop);
        while (bishops) {
            const Square square = popLsb(bishops);
            const Bitboard sameColor = bit(square) & darkSquares ? darkSquares : ~darkSquares;
            const int sameColorPawns = std::popcount(pawns & sameColor);
            terms[1] += {side * -2 * sameColorPawns, side * -sameColorPawns};
        }

        auto pawnCopy = pawns;
        while (pawnCopy) {
            const Square square = popLsb(pawnCopy);
            const int file = fileOf(square), rank = relativeRank(color, square);
            const Bitboard adjacentFiles = (file > 0 ? 0x0101010101010101ULL << (file - 1) : 0) |
                                           (file < 7 ? 0x0101010101010101ULL << (file + 1) : 0);
            const bool isolated = !(pawns & adjacentFiles);
            const bool connected = attacks().pawn[opposite(color)][square] & pawns;
            if (isolated)
                terms[3] += {side * -13, side * -18};
            if (connected)
                terms[3] += {side * (5 + rank), side * (8 + rank)};
            const int forward = square + (color == White ? 8 : -8);
            const bool blocked = forward >= 0 && forward < 64 && (board.occupied() & bit(forward));
            const bool backward = !connected && !isolated && blocked;
            if (backward)
                terms[3] += {side * -9, side * -12};
            if (candidatePassedPawn(board, color, square))
                terms[3] += {side * (4 + rank * 2), side * (6 + rank * 3)};

            if (passedPawn(board, color, square)) {
                static constexpr std::array<int, 8> MgPassed{0, 5, 10, 20, 35, 60, 100, 0};
                static constexpr std::array<int, 8> EgPassed{0, 10, 20, 40, 70, 120, 200, 0};
                int mg = MgPassed[rank], eg = EgPassed[rank];
                if (connected) {
                    mg += 8 + rank * 2;
                    eg += 12 + rank * 3;
                }
                if (blocked) {
                    mg -= 6 + rank;
                    eg -= 12 + rank * 2;
                }
                const Square target = color == White ? 56 + file : file;
                eg += 3 * (kingDistance(board.kingSquare(opposite(color)), target) -
                           kingDistance(board.kingSquare(color), target));
                const Bitboard fileMask = 0x0101010101010101ULL << file;
                const Bitboard behind = color == White ? (bit(square) - 1) & fileMask
                                                       : ~((bit(square) << 1) - 1) & fileMask;
                if (board.pieces(color, Rook) & behind) {
                    mg += 8;
                    eg += 14;
                }
                if (board.pieces(opposite(color), Rook) & behind) {
                    mg -= 8;
                    eg -= 14;
                }
                terms[4] += {side * mg, side * eg};
            }
        }

        if (std::popcount(board.pieces(color, Bishop)) >= 2)
            terms[5] += {side * 28, side * 42};

        auto rooks = board.pieces(color, Rook);
        while (rooks) {
            const Square square = popLsb(rooks);
            const Bitboard fileMask = 0x0101010101010101ULL << fileOf(square);
            const bool ownPawn = board.pieces(color, Pawn) & fileMask;
            const bool enemyPawn = board.pieces(opposite(color), Pawn) & fileMask;
            if (!ownPawn)
                terms[6] += {side * (enemyPawn ? 10 : 18), side * (enemyPawn ? 6 : 12)};
            if (relativeRank(color, square) == 6)
                terms[6] += {side * 18, side * 28};
        }
        if (std::popcount(board.pieces(color, Rook)) >= 2) {
            const auto first = static_cast<Square>(std::countr_zero(board.pieces(color, Rook)));
            auto other = board.pieces(color, Rook) & ~bit(first);
            if (other) {
                const auto second = static_cast<Square>(std::countr_zero(other));
                const auto line = fileOf(first) == fileOf(second)
                                      ? rookAttacks(first, board.occupied())
                                      : rookAttacks(first, board.occupied());
                if (line & bit(second))
                    terms[6] += {side * 10, side * 8};
            }
        }

        const Square king = board.kingSquare(color);
        const int direction = color == White ? 1 : -1;
        int shield = 0;
        for (int dr = 1; dr <= 2; ++dr) {
            const int rank = rankOf(king) + direction * dr;
            if (rank < 0 || rank > 7)
                continue;
            for (int file = std::max(0, fileOf(king) - 1); file <= std::min(7, fileOf(king) + 1);
                 ++file)
                shield += (board.pieces(color, Pawn) & bit(rank * 8 + file)) != 0;
        }
        const Bitboard kingZone = attacks().king[king] | bit(king);
        int attacksInZone = 0;
        for (Square square = 0; square < 64; ++square)
            if ((kingZone & bit(square)) && board.isAttacked(square, opposite(color)))
                ++attacksInZone;
        int openFiles = 0;
        for (int file = std::max(0, fileOf(king) - 1); file <= std::min(7, fileOf(king) + 1);
             ++file) {
            const Bitboard fileMask = 0x0101010101010101ULL << file;
            if (!(board.pieces(color, Pawn) & fileMask))
                openFiles += (board.pieces(opposite(color), Pawn) & fileMask) ? 1 : 2;
        }
        const int queenFactor = board.pieces(opposite(color), Queen) ? 2 : 1;
        terms[7] += {side * (shield * 8 - attacksInZone * 7 * queenFactor - openFiles * 6),
                     side * (shield * 2 - attacksInZone * 2 - openFiles)};

        Bitboard controlled = 0;
        auto sidePawns = board.pieces(color, Pawn);
        while (sidePawns)
            controlled |= attacks().pawn[color][popLsb(sidePawns)];
        for (const PieceType type : {Knight, Bishop, Rook, Queen}) {
            auto pieces = board.pieces(color, type);
            while (pieces)
                controlled |= pieceAttacks(board, type, popLsb(pieces));
        }
        const Bitboard enemyHalf = color == White ? 0xFFFFFFFF00000000ULL : 0x00000000FFFFFFFFULL;
        terms[8] += {side * 2 * std::popcount(controlled & enemyHalf & ExtendedCenter),
                     side * std::popcount(controlled & enemyHalf & Center)};
    }

    phase = std::min(phase, MaxPhase);
    result.phase = phase;
    result.material = blend(terms[0], phase);
    result.pieceSquare = blend(terms[1], phase);
    result.mobility = blend(terms[2], phase);
    result.pawnStructure = blend(terms[3], phase);
    result.passedPawns = blend(terms[4], phase);
    result.bishopPair = blend(terms[5], phase);
    result.rookActivity = blend(terms[6], phase);
    result.kingSafety = blend(terms[7], phase);
    result.space = blend(terms[8], phase);
    result.tempo = 10;
    const int perspective = board.sideToMove() == White ? 1 : -1;
    for (Score *component : {&result.material, &result.pieceSquare, &result.mobility,
                             &result.pawnStructure, &result.passedPawns, &result.bishopPair,
                             &result.rookActivity, &result.kingSafety, &result.space})
        *component *= perspective;
    if (mode == EvaluationMode::Basic) {
        result.mobility = 0;
        result.pawnStructure = 0;
        result.passedPawns = 0;
        result.bishopPair = 0;
        result.rookActivity = 0;
        result.kingSafety = 0;
        result.space = 0;
    }
    result.total = result.material + result.pieceSquare + result.mobility + result.pawnStructure +
                   result.passedPawns + result.bishopPair + result.rookActivity +
                   result.kingSafety + result.space + result.tempo;
    return result;
}
} // namespace chessbot
