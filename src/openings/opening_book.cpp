#include "opening_book.h"
#include "board/movegen.h"
#include <algorithm>
#include <charconv>
#include <fstream>
#include <limits>
#include <sstream>
#include <stdexcept>

namespace chessbot {
namespace {
std::vector<std::string> splitTabs(const std::string &line) {
    std::vector<std::string> fields;
    std::size_t start = 0;
    while (true) {
        const auto tab = line.find('\t', start);
        fields.push_back(line.substr(start, tab - start));
        if (tab == std::string::npos)
            return fields;
        start = tab + 1;
    }
}
std::uint64_t number(std::string_view text, std::string_view field) {
    std::uint64_t value = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size())
        throw std::invalid_argument("Book: invalid " + std::string(field));
    return value;
}
int signedNumber(std::string_view text, std::string_view field) {
    int value = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size())
        throw std::invalid_argument("Book: invalid " + std::string(field));
    return value;
}
std::uint64_t mix(std::uint64_t value) {
    value += 0x9E3779B97F4A7C15ULL;
    value = (value ^ (value >> 30)) * 0xBF58476D1CE4E5B9ULL;
    value = (value ^ (value >> 27)) * 0x94D049BB133111EBULL;
    return value ^ (value >> 31);
}
std::string bookPositionKey(const Board &board) {
    std::istringstream input(board.fen());
    std::string result, field;
    for (int index = 0; index < 4; ++index) {
        input >> field;
        if (index)
            result += ' ';
        result += field;
    }
    return result;
}
} // namespace

std::string_view bookPolicyName(BookPolicy policy) {
    switch (policy) {
    case BookPolicy::Best:
        return "best";
    case BookPolicy::Weighted:
        return "weighted";
    case BookPolicy::Random:
        return "random";
    case BookPolicy::Explore:
        return "explore";
    }
    return "unknown";
}
void OpeningBook::clear() {
    entries_.clear();
    version_ = "unversioned";
}
void OpeningBook::load(const std::string &path) {
    std::ifstream input(path);
    if (!input)
        throw std::invalid_argument("Book: cannot open file: " + path);
    std::unordered_map<std::string, std::vector<BookMove>> loaded;
    std::string loadedVersion = "unversioned", line;
    int lineNumber = 0;
    while (std::getline(input, line)) {
        ++lineNumber;
        if (line.empty())
            continue;
        if (line.starts_with("# version=")) {
            loadedVersion = line.substr(10);
            continue;
        }
        if (line[0] == '#')
            continue;
        const auto fields = splitTabs(line);
        if (fields.size() != 9)
            throw std::invalid_argument("Book: line " + std::to_string(lineNumber) +
                                        " must contain 9 tab-separated fields");
        auto board = Board::fromFen(fields[0] + " 0 1");
        Move move;
        for (const auto legal : legalMoveList(board))
            if (legal.uci() == fields[1])
                move = legal;
        if (!move)
            throw std::invalid_argument("Book: illegal move on line " + std::to_string(lineNumber));
        const auto weight = number(fields[2], "weight");
        if (!weight || weight > static_cast<std::uint64_t>(std::numeric_limits<int>::max()))
            throw std::invalid_argument("Book: weight must be between 1 and INT_MAX");
        BookMove entry{move,
                       static_cast<int>(weight),
                       number(fields[3], "games"),
                       number(fields[4], "wins"),
                       number(fields[5], "draws"),
                       number(fields[6], "losses"),
                       signedNumber(fields[7], "engine score"),
                       fields[8]};
        if (entry.wins + entry.draws + entry.losses > entry.games)
            throw std::invalid_argument("Book: WDL exceeds games on line " +
                                        std::to_string(lineNumber));
        loaded[bookPositionKey(board)].push_back(std::move(entry));
    }
    entries_ = std::move(loaded);
    version_ = std::move(loadedVersion);
}
std::optional<BookSelection> OpeningBook::select(Board board, BookPolicy policy,
                                                 std::uint64_t seed) const {
    const auto found = entries_.find(bookPositionKey(board));
    if (found == entries_.end())
        return std::nullopt;
    std::vector<const BookMove *> legal;
    const auto moves = legalMoveList(board);
    for (const auto &entry : found->second)
        if (std::find(moves.begin(), moves.end(), entry.move) != moves.end())
            legal.push_back(&entry);
    if (legal.empty())
        return std::nullopt;
    const BookMove *selected = legal.front();
    if (policy == BookPolicy::Best)
        selected = *std::max_element(legal.begin(), legal.end(), [](const auto *a, const auto *b) {
            return std::pair{a->weight, a->engineScore} < std::pair{b->weight, b->engineScore};
        });
    else if (policy == BookPolicy::Explore)
        selected = *std::min_element(legal.begin(), legal.end(), [](const auto *a, const auto *b) {
            return std::pair{a->games, -a->weight} < std::pair{b->games, -b->weight};
        });
    else {
        const auto random = mix(seed ^ board.key());
        if (policy == BookPolicy::Random)
            selected = legal[random % legal.size()];
        else {
            std::uint64_t total = 0;
            for (const auto *entry : legal)
                total += static_cast<std::uint64_t>(entry->weight);
            auto target = random % total;
            for (const auto *entry : legal) {
                if (target < static_cast<std::uint64_t>(entry->weight)) {
                    selected = entry;
                    break;
                }
                target -= static_cast<std::uint64_t>(entry->weight);
            }
        }
    }
    return BookSelection{*selected, version_};
}
} // namespace chessbot
