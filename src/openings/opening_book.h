#pragma once
#include "board/board.h"
#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace chessbot {
enum class BookPolicy { Best, Weighted, Random, Explore };

struct BookMove {
    Move move;
    int weight = 1;
    std::uint64_t games = 0, wins = 0, draws = 0, losses = 0;
    Score engineScore = 0;
    std::string source;
};

struct BookSelection {
    BookMove entry;
    std::string version;
};

class OpeningBook {
  public:
    void load(const std::string &path);
    void clear();
    std::optional<BookSelection> select(Board board, BookPolicy policy, std::uint64_t seed) const;
    const std::string &version() const {
        return version_;
    }

  private:
    std::unordered_map<std::string, std::vector<BookMove>> entries_;
    std::string version_ = "unversioned";
};

std::string_view bookPolicyName(BookPolicy policy);
} // namespace chessbot
