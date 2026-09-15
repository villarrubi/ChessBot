#include "uci.h"
#include "board/movegen.h"
#include <algorithm>
#include <charconv>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace chessbot {
namespace {
std::string trim(std::string_view text) {
    const auto first = text.find_first_not_of(" \t\r\n");
    if (first == std::string_view::npos)
        return {};
    const auto last = text.find_last_not_of(" \t\r\n");
    return std::string(text.substr(first, last - first + 1));
}
int parseInt(std::string_view text, int minimum, int maximum, std::string_view name) {
    int value = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size() || value < minimum ||
        value > maximum)
        throw std::invalid_argument(std::string(name) + " is outside its supported range");
    return value;
}
std::uint64_t parseNodes(std::string_view text) {
    std::uint64_t value = 0;
    const auto [end, error] = std::from_chars(text.data(), text.data() + text.size(), value);
    if (error != std::errc{} || end != text.data() + text.size() || value == 0)
        throw std::invalid_argument("nodes must be a positive integer");
    return value;
}
std::string scoreText(Score score) {
    if (score >= ScoreMate - MaxPly) {
        const int plies = ScoreMate - score;
        return "mate " + std::to_string((plies + 1) / 2);
    }
    if (score <= -ScoreMate + MaxPly) {
        const int plies = ScoreMate + score;
        return "mate -" + std::to_string((plies + 1) / 2);
    }
    return "cp " + std::to_string(score);
}
std::vector<std::string> tokens(std::string_view text) {
    std::istringstream input{std::string(text)};
    std::vector<std::string> result;
    for (std::string token; input >> token;)
        result.push_back(token);
    return result;
}
} // namespace

UciProtocol::~UciProtocol() {
    stopAndJoin();
}
void UciProtocol::writeLine(const std::string &line) {
    std::lock_guard lock(outputMutex_);
    output_ << line << '\n' << std::flush;
}
void UciProtocol::identify() {
    writeLine("id name ChessBot 0.6.0");
    writeLine("id author ChessBot contributors");
    writeLine("option name Hash type spin default 64 min 1 max 4096");
    writeLine("option name Threads type spin default 1 min 1 max 1");
    writeLine("option name Move Overhead type spin default 10 min 0 max 5000");
    writeLine("option name OwnBook type check default false");
    writeLine("option name MultiPV type spin default 1 min 1 max 10");
    writeLine("option name SearchProfile type combo default Baseline var Baseline var Optimized");
    writeLine("option name AnalysisDetail type combo default Basic var Basic var Full");
    writeLine("option name Evaluation type combo default Positional var Basic var Positional");
    writeLine("option name NNUE type check default false");
    writeLine("uciok");
}
void UciProtocol::stopAndJoin() {
    if (worker_.joinable()) {
        engine_.stop();
        worker_.join();
    }
}
void UciProtocol::setOption(std::string_view arguments) {
    const auto words = tokens(arguments);
    if (words.empty() || words[0] != "name")
        throw std::invalid_argument("setoption requires 'name'");
    auto valueIt = std::find(words.begin() + 1, words.end(), "value");
    const std::string name = [&] {
        std::string result;
        for (auto it = words.begin() + 1; it != valueIt; ++it) {
            if (!result.empty())
                result += ' ';
            result += *it;
        }
        return result;
    }();
    std::string value;
    if (valueIt != words.end()) {
        for (auto it = valueIt + 1; it != words.end(); ++it) {
            if (!value.empty())
                value += ' ';
            value += *it;
        }
    }
    stopAndJoin();
    if (name == "Hash")
        engine_.setHashSize(static_cast<std::size_t>(parseInt(value, 1, 4096, "Hash")));
    else if (name == "Move Overhead")
        engine_.setMoveOverhead(parseInt(value, 0, 5000, "Move Overhead"));
    else if (name == "Threads") {
        if (parseInt(value, 1, 1, "Threads") != 1)
            throw std::invalid_argument("only one search thread is available");
    } else if (name == "MultiPV") {
        multiPv_ = parseInt(value, 1, 10, "MultiPV");
    } else if (name == "OwnBook" || name == "NNUE") {
        if (value != "false")
            throw std::invalid_argument(name + " is not available in this version");
    } else if (name == "AnalysisDetail") {
        if (value != "Basic" && value != "Full")
            throw std::invalid_argument("AnalysisDetail must be Basic or Full");
        fullAnalysis_ = value == "Full";
    } else if (name == "Evaluation") {
        if (value == "Basic")
            engine_.setEvaluationMode(EvaluationMode::Basic);
        else if (value == "Positional")
            engine_.setEvaluationMode(EvaluationMode::Positional);
        else
            throw std::invalid_argument("Evaluation must be Basic or Positional");
    } else if (name == "SearchProfile") {
        if (value == "Baseline")
            engine_.setSearchMode(SearchMode::Baseline);
        else if (value == "Optimized")
            engine_.setSearchMode(SearchMode::Optimized);
        else
            throw std::invalid_argument("SearchProfile must be Baseline or Optimized");
    } else
        throw std::invalid_argument("unsupported option: " + name);
}
void UciProtocol::setPosition(std::string_view arguments) {
    stopAndJoin();
    const auto words = tokens(arguments);
    if (words.empty())
        throw std::invalid_argument("position requires startpos or fen");
    std::size_t index = 0;
    Board board;
    if (words[index] == "startpos") {
        board = Board::startPosition();
        ++index;
    } else if (words[index] == "fen") {
        if (words.size() < 7)
            throw std::invalid_argument("position fen requires six FEN fields");
        std::string fen;
        for (int field = 0; field < 6; ++field) {
            if (field)
                fen += ' ';
            fen += words[++index];
        }
        ++index;
        board = Board::fromFen(fen);
    } else
        throw std::invalid_argument("position requires startpos or fen");
    if (index < words.size()) {
        if (words[index++] != "moves")
            throw std::invalid_argument("expected moves after position");
        for (; index < words.size(); ++index) {
            StateInfo state;
            board.playUci(words[index], state);
        }
    }
    engine_.setPosition(board);
}
void UciProtocol::writeInfo(const SearchResult &result, int hashFull) {
    const auto nps = result.nodes * 1000 / std::max<std::uint64_t>(1, result.timeMs);
    const auto &variations = result.variations;
    const std::size_t count = variations.empty() ? 1 : variations.size();
    for (std::size_t index = 0; index < count; ++index) {
        const Score score = variations.empty() ? result.score : variations[index].score;
        const auto &pv =
            variations.empty() ? result.principalVariation : variations[index].principalVariation;
        std::ostringstream line;
        line << "info depth " << result.depth << " seldepth " << result.selectiveDepth
             << " multipv " << index + 1 << " score " << scoreText(score) << " nodes "
             << result.nodes << " nps " << nps << " hashfull " << hashFull << " time "
             << result.timeMs << " pv";
        for (const Move move : pv)
            line << ' ' << move.uci();
        writeLine(line.str());
    }
    if (fullAnalysis_) {
        const auto countedNodes = std::max<std::uint64_t>(1, result.nodes);
        writeLine(
            "info string search_metrics qnodes " + std::to_string(result.qnodes) + " tthits " +
            std::to_string(result.ttHits) + " cutoffs " + std::to_string(result.betaCutoffs) +
            " first_cutoffs " + std::to_string(result.firstMoveCutoffs) + " generated " +
            std::to_string(result.generatedMoves) + " branching_milli " +
            std::to_string(result.generatedMoves * 1000 / countedNodes) + " max_branching " +
            std::to_string(result.maximumBranching) + " aspiration_researches " +
            std::to_string(result.aspirationResearches) + " null_cutoffs " +
            std::to_string(result.nullMoveCutoffs) + "/" + std::to_string(result.nullMoveAttempts) +
            " lmr_researches " + std::to_string(result.lmrResearches) + "/" +
            std::to_string(result.lmrReductions) + " futility " +
            std::to_string(result.futilityPrunes) + " hash_mb " +
            std::to_string(engine_.hashSize()));
    }
}
void UciProtocol::go(std::string_view arguments) {
    stopAndJoin();
    SearchLimits limits;
    limits.multiPv = multiPv_;
    const auto words = tokens(arguments);
    const auto isGoOption = [](std::string_view word) {
        return word == "depth" || word == "nodes" || word == "movetime" || word == "wtime" ||
               word == "btime" || word == "winc" || word == "binc" || word == "movestogo" ||
               word == "infinite" || word == "searchmoves";
    };
    for (std::size_t index = 0; index < words.size(); ++index) {
        const auto requireValue = [&]() -> const std::string & {
            if (++index >= words.size())
                throw std::invalid_argument("missing value after go option");
            return words[index];
        };
        if (words[index] == "depth")
            limits.depth = parseInt(requireValue(), 1, MaxPly - 2, "depth");
        else if (words[index] == "nodes")
            limits.nodes = parseNodes(requireValue());
        else if (words[index] == "movetime")
            limits.moveTimeMs = parseInt(requireValue(), 1, 2'000'000'000, "movetime");
        else if (words[index] == "wtime")
            limits.whiteTimeMs = parseInt(requireValue(), 0, 2'000'000'000, "wtime");
        else if (words[index] == "btime")
            limits.blackTimeMs = parseInt(requireValue(), 0, 2'000'000'000, "btime");
        else if (words[index] == "winc")
            limits.whiteIncrementMs = parseInt(requireValue(), 0, 2'000'000'000, "winc");
        else if (words[index] == "binc")
            limits.blackIncrementMs = parseInt(requireValue(), 0, 2'000'000'000, "binc");
        else if (words[index] == "movestogo")
            limits.movesToGo = parseInt(requireValue(), 1, 1000, "movestogo");
        else if (words[index] == "infinite")
            limits.infinite = true;
        else if (words[index] == "searchmoves") {
            auto position = engine_.position();
            const auto legal = legalMoves(position);
            while (index + 1 < words.size() && !isGoOption(words[index + 1])) {
                const auto &name = words[++index];
                const auto found = std::find_if(legal.begin(), legal.end(),
                                                [&](Move move) { return move.uci() == name; });
                if (found == legal.end())
                    throw std::invalid_argument("illegal searchmove: " + name);
                if (std::find(limits.rootMoves.begin(), limits.rootMoves.end(), *found) ==
                    limits.rootMoves.end())
                    limits.rootMoves.push_back(*found);
            }
            if (limits.rootMoves.empty())
                throw std::invalid_argument("searchmoves requires at least one legal move");
        } else
            throw std::invalid_argument("unsupported go option: " + words[index]);
    }
    if ((limits.whiteTimeMs >= 0) != (limits.blackTimeMs >= 0))
        throw std::invalid_argument("wtime and btime must be supplied together");
    if (!limits.depth && !limits.nodes && !limits.moveTimeMs && limits.whiteTimeMs < 0 &&
        limits.blackTimeMs < 0)
        limits.infinite = true;
    if (fullAnalysis_)
        writeEvaluation();
    engine_.prepareSearch();
    worker_ = std::thread([this, limits] {
        const auto result =
            engine_.searchPrepared(limits, [this](const SearchResult &iteration, int hashFull) {
                writeInfo(iteration, hashFull);
            });
        writeLine("bestmove " + (result.bestMove ? result.bestMove.uci() : std::string("0000")) +
                  (result.ponderMove ? " ponder " + result.ponderMove.uci() : ""));
    });
}
void UciProtocol::handle(const std::string &line, bool &quit) {
    const auto split = line.find_first_of(" \t");
    const std::string command = line.substr(0, split);
    const std::string arguments = split == std::string::npos ? "" : trim(line.substr(split + 1));
    if (command == "uci")
        identify();
    else if (command == "isready")
        writeLine("readyok");
    else if (command == "ucinewgame") {
        stopAndJoin();
        engine_.clear();
    } else if (command == "position")
        setPosition(arguments);
    else if (command == "go")
        go(arguments);
    else if (command == "stop")
        stopAndJoin();
    else if (command == "quit") {
        stopAndJoin();
        quit = true;
    } else if (command == "setoption")
        setOption(arguments);
    else if (command == "debug") {
        if (arguments != "on" && arguments != "off")
            throw std::invalid_argument("debug expects on or off");
        debug_ = arguments == "on";
    } else if (command == "eval")
        writeEvaluation();
    else if (!command.empty() && debug_)
        writeLine("info string ignored command: " + command);
}
void UciProtocol::writeEvaluation() {
    const auto eval = engine_.evaluateDetailed();
    writeLine("info string eval side_to_move total " + std::to_string(eval.total) + " material " +
              std::to_string(eval.material) + " pst " + std::to_string(eval.pieceSquare) +
              " mobility " + std::to_string(eval.mobility) + " pawns " +
              std::to_string(eval.pawnStructure) + " passed " + std::to_string(eval.passedPawns) +
              " bishop_pair " + std::to_string(eval.bishopPair) + " rooks " +
              std::to_string(eval.rookActivity) + " king " + std::to_string(eval.kingSafety) +
              " space " + std::to_string(eval.space) + " tempo " + std::to_string(eval.tempo) +
              " phase " + std::to_string(eval.phase));
}
int UciProtocol::run() {
    bool quit = false;
    for (std::string line; !quit && std::getline(input_, line);) {
        try {
            handle(trim(line), quit);
        } catch (const std::exception &error) {
            writeLine("info string error: " + std::string(error.what()));
        }
    }
    stopAndJoin();
    return 0;
}
} // namespace chessbot
