#include "ordering.h"
#include <algorithm>
#include <array>

namespace chessbot {
namespace {
constexpr std::array<int, 7> Value{100, 320, 330, 500, 900, 20000, 0};
int priority(Move move, Move ttMove, Move firstKiller, Move secondKiller,
             const HistoryTable *history, Color side) {
    if (ttMove && move == ttMove)
        return 1'000'000;
    int score = 0;
    if (move.promotion() != None)
        score += 100'000 + Value[move.promotion()];
    if (move.has(Capture))
        score += 50'000 + Value[move.captured()] * 16 - Value[move.moving()];
    else if (firstKiller && move == firstKiller)
        score += 40'000;
    else if (secondKiller && move == secondKiller)
        score += 30'000;
    if (history && !move.has(Capture) && move.promotion() == None)
        score += std::min(20'000, (*history)[side][move.from()][move.to()]);
    return score;
}
} // namespace
void orderMoves(MoveList &moves, Move ttMove, Move firstKiller, Move secondKiller,
                const HistoryTable *history, Color side) {
    // Score each move once. Stable insertion sort is efficient for these short,
    // mostly tied lists and avoids an allocation at every search node.
    std::array<int, 256> scores;
    for (std::size_t i = 0; i < moves.size(); ++i) {
        const Move move = moves[i];
        const int score = priority(move, ttMove, firstKiller, secondKiller, history, side);
        std::size_t j = i;
        while (j > 0 && scores[j - 1] < score) {
            moves[j] = moves[j - 1];
            scores[j] = scores[j - 1];
            --j;
        }
        moves[j] = move;
        scores[j] = score;
    }
}
} // namespace chessbot
