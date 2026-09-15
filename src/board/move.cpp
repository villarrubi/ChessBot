#include "move.h"
#include <stdexcept>

namespace chessbot {
Square parseSquare(std::string_view text) {
    if (text.size() != 2 || text[0] < 'a' || text[0] > 'h' || text[1] < '1' || text[1] > '8')
        throw std::invalid_argument("Invalid square");
    return (text[1] - '1') * 8 + text[0] - 'a';
}
std::string squareName(Square square) {
    if (square < 0 || square >= 64)
        throw std::invalid_argument("Invalid square index");
    return {static_cast<char>('a' + fileOf(square)), static_cast<char>('1' + rankOf(square))};
}
std::string Move::uci() const {
    auto result = squareName(from()) + squareName(to());
    if (promotion() != None)
        result += "pnbrqk"[promotion()];
    return result;
}
} // namespace chessbot
