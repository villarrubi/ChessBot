#include "attack_tables.h"
#include "bitboard.h"
#include <bit>
#include <cstdlib>
#include <vector>

#if defined(_MSC_VER) && defined(_M_X64)
#include <immintrin.h>
#include <intrin.h>
#elif (defined(__GNUC__) || defined(__clang__)) && defined(__x86_64__)
#include <immintrin.h>
#endif

namespace chessbot {
AttackTables::AttackTables() {
    for (Square from = 0; from < 64; ++from) {
        for (Square to = 0; to < 64; ++to) {
            const int dx = fileOf(to) - fileOf(from), dy = rankOf(to) - rankOf(from);
            if (std::abs(dx) * std::abs(dy) == 2)
                knight[from] |= bit(to);
            if (std::abs(dx) <= 1 && std::abs(dy) <= 1 && from != to)
                king[from] |= bit(to);
            if (std::abs(dx) == 1 && dy == 1)
                pawn[White][from] |= bit(to);
            if (std::abs(dx) == 1 && dy == -1)
                pawn[Black][from] |= bit(to);
        }
    }
}
const AttackTables &attacks() {
    static const AttackTables tables;
    return tables;
}
namespace {
Bitboard ray(Square square, Bitboard occupied, int dx, int dy) {
    Bitboard result = 0;
    int x = fileOf(square) + dx, y = rankOf(square) + dy;
    while (x >= 0 && x < 8 && y >= 0 && y < 8) {
        const auto target = bit(y * 8 + x);
        result |= target;
        if (target & occupied)
            break;
        x += dx;
        y += dy;
    }
    return result;
}
Bitboard rawBishopAttacks(Square square, Bitboard occupied) {
    return ray(square, occupied, 1, 1) | ray(square, occupied, 1, -1) |
           ray(square, occupied, -1, 1) | ray(square, occupied, -1, -1);
}
Bitboard rawRookAttacks(Square square, Bitboard occupied) {
    return ray(square, occupied, 1, 0) | ray(square, occupied, -1, 0) |
           ray(square, occupied, 0, 1) | ray(square, occupied, 0, -1);
}
Bitboard relevantRay(Square square, int dx, int dy) {
    Bitboard result = 0;
    int x = fileOf(square) + dx, y = rankOf(square) + dy;
    while (x >= 0 && x < 8 && y >= 0 && y < 8) {
        const int nextX = x + dx, nextY = y + dy;
        if (nextX < 0 || nextX >= 8 || nextY < 0 || nextY >= 8)
            break;
        result |= bit(y * 8 + x);
        x = nextX;
        y = nextY;
    }
    return result;
}
Bitboard deposit(std::size_t index, Bitboard mask) {
    Bitboard result = 0;
    unsigned sourceBit = 0;
    while (mask) {
        const Square square = popLsb(mask);
        if (index & (std::size_t{1} << sourceBit))
            result |= bit(square);
        ++sourceBit;
    }
    return result;
}
std::size_t extractSoftware(Bitboard occupied, Bitboard mask) {
    std::size_t result = 0;
    unsigned targetBit = 0;
    while (mask) {
        const Square square = popLsb(mask);
        if (occupied & bit(square))
            result |= std::size_t{1} << targetBit;
        ++targetBit;
    }
    return result;
}
bool bmi2Available() {
#if defined(_MSC_VER) && defined(_M_X64)
    int registers[4]{};
    __cpuidex(registers, 7, 0);
    return (registers[1] & (1 << 8)) != 0;
#elif (defined(__GNUC__) || defined(__clang__)) && defined(__x86_64__)
    return __builtin_cpu_supports("bmi2");
#else
    return false;
#endif
}
#if defined(_MSC_VER) && defined(_M_X64)
std::size_t extractHardware(Bitboard occupied, Bitboard mask) {
    return static_cast<std::size_t>(_pext_u64(occupied, mask));
}
#elif (defined(__GNUC__) || defined(__clang__)) && defined(__x86_64__)
__attribute__((target("bmi2"))) std::size_t extractHardware(Bitboard occupied, Bitboard mask) {
    return static_cast<std::size_t>(_pext_u64(occupied, mask));
}
#endif

struct SliderTable {
    std::array<Bitboard, 64> masks{};
    std::array<std::vector<Bitboard>, 64> attacks{};
};
using AttackGenerator = Bitboard (*)(Square, Bitboard);
struct SliderTables {
    SliderTable bishop, rook;
    bool usePext = bmi2Available();
    SliderTables() {
        for (Square square = 0; square < 64; ++square) {
            bishop.masks[square] = relevantRay(square, 1, 1) | relevantRay(square, 1, -1) |
                                   relevantRay(square, -1, 1) | relevantRay(square, -1, -1);
            rook.masks[square] = relevantRay(square, 1, 0) | relevantRay(square, -1, 0) |
                                 relevantRay(square, 0, 1) | relevantRay(square, 0, -1);
            const std::array<std::pair<SliderTable *, AttackGenerator>, 2> generators{
                std::pair{&bishop, &rawBishopAttacks}, std::pair{&rook, &rawRookAttacks}};
            for (const auto [table, generator] : generators) {
                const auto count = std::size_t{1} << std::popcount(table->masks[square]);
                table->attacks[square].resize(count);
                for (std::size_t index = 0; index < count; ++index)
                    table->attacks[square][index] =
                        generator(square, deposit(index, table->masks[square]));
            }
        }
    }
};
const SliderTables &sliders() {
    static const SliderTables tables;
    return tables;
}
std::size_t attackIndex(Bitboard occupied, Bitboard mask, bool usePext) {
#if (defined(_MSC_VER) && defined(_M_X64)) ||                                                      \
    ((defined(__GNUC__) || defined(__clang__)) && defined(__x86_64__))
    if (usePext)
        return extractHardware(occupied, mask);
#else
    (void)usePext;
#endif
    return extractSoftware(occupied, mask);
}
} // namespace
Bitboard bishopAttacks(Square s, Bitboard occupied) {
    const auto &tables = sliders();
    return tables.bishop.attacks[s][attackIndex(occupied, tables.bishop.masks[s], tables.usePext)];
}
Bitboard rookAttacks(Square s, Bitboard occupied) {
    const auto &tables = sliders();
    return tables.rook.attacks[s][attackIndex(occupied, tables.rook.masks[s], tables.usePext)];
}
std::string_view slidingAttackBackend() {
    return sliders().usePext ? "pext" : "lookup-software";
}
} // namespace chessbot
