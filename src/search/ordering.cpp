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
    std::stable_sort(moves.begin(), moves.end(), [&](Move a, Move b) {
        return priority(a, ttMove, firstKiller, secondKiller, history, side) >
               priority(b, ttMove, firstKiller, secondKiller, history, side);
    });
}
} // namespace chessbot
