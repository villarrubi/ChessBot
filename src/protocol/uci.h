#pragma once
#include "engine/engine.h"
#include <istream>
#include <mutex>
#include <ostream>
#include <string>
#include <thread>

namespace chessbot {
class UciProtocol {
  public:
    UciProtocol(std::istream &input, std::ostream &output) : input_(input), output_(output) {}
    ~UciProtocol();
    int run();

  private:
    std::istream &input_;
    std::ostream &output_;
    Engine engine_;
    std::thread worker_;
    std::mutex outputMutex_;
    bool debug_ = false;
    bool fullAnalysis_ = false;
    int multiPv_ = 1;

    void handle(const std::string &line, bool &quit);
    void identify();
    void setOption(std::string_view arguments);
    void setPosition(std::string_view arguments);
    void go(std::string_view arguments);
    void stopAndJoin();
    void writeLine(const std::string &line);
    void writeInfo(const SearchResult &result, int hashFull);
    void writeEvaluation();
};
} // namespace chessbot
