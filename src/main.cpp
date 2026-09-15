#include "board/attack_tables.h"
#include "board/movegen.h"
#include "engine/engine.h"
#include "protocol/uci.h"
#include <algorithm>
#include <charconv>
#include <chrono>
#include <iostream>
#include <sstream>
#include <stdexcept>

using namespace chessbot;
namespace {
std::string quote(std::string_view value);
void help() {
    std::cout
        << "ChessBot 0.8.0 - UCI chess engine and diagnostic CLI\n"
           "Usage: chessbot                         Start UCI protocol\n"
           "       chessbot <inspect|eval|legal|perft N|divide N> [--fen FEN] [--moves \"e2e4 "
           "e7e5\"]\n"
           "       chessbot bench [depth] [Baseline|Optimized]\n"
           "       chessbot validate-stream\n"
           "       chessbot features-stream [--eval-file FILE]\n"
           "Stream input: one FEN per line, optionally followed by TAB and UCI moves.\n"
           "Stream output: one JSON object per line; invalid requests return an error object.\n";
}
void printEvaluationFields(const EvalBreakdown &eval) {
    std::cout << "\"perspective\":\"side_to_move\",\"total\":" << eval.total
              << ",\"material\":" << eval.material << ",\"piece_square\":" << eval.pieceSquare
              << ",\"mobility\":" << eval.mobility << ",\"pawn_structure\":" << eval.pawnStructure
              << ",\"passed_pawns\":" << eval.passedPawns << ",\"bishop_pair\":" << eval.bishopPair
              << ",\"rook_activity\":" << eval.rookActivity
              << ",\"king_safety\":" << eval.kingSafety << ",\"space\":" << eval.space
              << ",\"tempo\":" << eval.tempo << ",\"phase\":" << eval.phase;
}
void printEvaluation(const EvalBreakdown &eval) {
    std::cout << '{';
    printEvaluationFields(eval);
    std::cout << "}\n";
}
void benchmark(int depth, SearchMode mode) {
    constexpr std::string_view positions[] = {
        StartFen,
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
    };
    Engine engine;
    engine.setSearchMode(mode);
    std::uint64_t nodes = 0, qnodes = 0, ttHits = 0, betaCutoffs = 0, elapsed = 0;
    std::uint64_t firstCutoffs = 0, generated = 0, nullAttempts = 0, nullCutoffs = 0;
    std::uint64_t lmrReductions = 0, lmrResearches = 0, aspirationResearches = 0;
    for (const auto fen : positions) {
        engine.setPosition(Board::fromFen(fen));
        SearchLimits limits;
        limits.depth = depth;
        const auto result = engine.search(limits);
        nodes += result.nodes;
        qnodes += result.qnodes;
        ttHits += result.ttHits;
        betaCutoffs += result.betaCutoffs;
        firstCutoffs += result.firstMoveCutoffs;
        generated += result.generatedMoves;
        nullAttempts += result.nullMoveAttempts;
        nullCutoffs += result.nullMoveCutoffs;
        lmrReductions += result.lmrReductions;
        lmrResearches += result.lmrResearches;
        aspirationResearches += result.aspirationResearches;
        elapsed += result.timeMs;
        std::cout << "position " << quote(fen) << " depth " << result.depth << " score "
                  << result.score << " nodes " << result.nodes << " time " << result.timeMs
                  << " qnodes " << result.qnodes << " tthits " << result.ttHits << " cutoffs "
                  << result.betaCutoffs << " bestmove "
                  << (result.bestMove ? result.bestMove.uci() : "0000") << '\n';
    }
    std::cout << "total nodes " << nodes << " time " << elapsed << " nps "
              << nodes * 1000 / std::max<std::uint64_t>(1, elapsed) << " qnodes " << qnodes
              << " qsearch_percent " << (nodes ? qnodes * 100 / nodes : 0) << " tthits " << ttHits
              << " cutoffs " << betaCutoffs << " first_cutoffs " << firstCutoffs << " generated "
              << generated << " null_cutoffs " << nullCutoffs << '/' << nullAttempts
              << " lmr_researches " << lmrResearches << '/' << lmrReductions
              << " aspiration_researches " << aspirationResearches << " search_profile "
              << (mode == SearchMode::Optimized ? "Optimized" : "Baseline") << " sliders "
              << slidingAttackBackend() << " hash_mb " << engine.hashSize() << '\n';
}
std::string quote(std::string_view value) {
    std::string out = "\"";
    constexpr char hex[] = "0123456789abcdef";
    for (const unsigned char c : value) {
        if (c == '"' || c == '\\') {
            out += '\\';
            out += static_cast<char>(c);
        } else if (c < 32) {
            out += "\\u00";
            out += hex[c >> 4];
            out += hex[c & 15];
        } else
            out += static_cast<char>(c);
    }
    return out + '"';
}
void applyMoves(Board &board, const std::string &text) {
    std::istringstream input(text);
    std::string token;
    while (input >> token) {
        StateInfo state;
        board.playUci(token, state);
    }
}
std::vector<std::string> moveNames(Board &board) {
    std::vector<std::string> result;
    for (const auto move : legalMoves(board))
        result.push_back(move.uci());
    std::sort(result.begin(), result.end());
    return result;
}
void inspect(Board &board) {
    const auto moves = moveNames(board);
    std::cout << "{\"fen\":" << quote(board.fen())
              << ",\"key\":" << quote(std::to_string(board.key()))
              << ",\"in_check\":" << (board.inCheck(board.sideToMove()) ? "true" : "false")
              << ",\"threefold\":" << (board.isThreefoldRepetition() ? "true" : "false")
              << ",\"insufficient_material\":"
              << (board.isInsufficientMaterial() ? "true" : "false")
              << ",\"status\":" << quote(statusName(board.status())) << ",\"legal_moves\":[";
    for (std::size_t i = 0; i < moves.size(); ++i) {
        if (i)
            std::cout << ',';
        std::cout << quote(moves[i]);
    }
    std::cout << "]}\n";
}
void stream() {
    std::string line;
    while (std::getline(std::cin, line)) {
        try {
            const auto tab = line.find('\t');
            auto board = Board::fromFen(line.substr(0, tab));
            if (tab != std::string::npos)
                applyMoves(board, line.substr(tab + 1));
            inspect(board);
        } catch (const std::exception &error) {
            std::cout << "{\"error\":" << quote(error.what()) << "}\n";
        }
        std::cout.flush();
    }
}
void featureStream(const EvaluationParameters &parameters) {
    std::string line;
    while (std::getline(std::cin, line)) {
        try {
            const auto tab = line.find('\t');
            auto board = Board::fromFen(line.substr(0, tab));
            if (tab != std::string::npos)
                applyMoves(board, line.substr(tab + 1));
            std::cout << "{\"fen\":" << quote(board.fen())
                      << ",\"key\":" << quote(std::to_string(board.key())) << ",\"side_to_move\":"
                      << quote(board.sideToMove() == White ? "white" : "black") << ',';
            const auto eval = evaluateDetailed(board, EvaluationMode::Positional, parameters);
            std::cout << "\"evaluation_version\":" << quote(parameters.version) << ',';
            printEvaluationFields(eval);
            std::cout << "}\n";
        } catch (const std::exception &error) {
            std::cout << "{\"error\":" << quote(error.what()) << "}\n";
        }
        std::cout.flush();
    }
}
} // namespace
int main(int argc, char **argv) {
    try {
        if (argc == 1)
            return UciProtocol(std::cin, std::cout).run();
        if (argc == 2 && std::string_view(argv[1]) == "--help") {
            help();
            return 0;
        }
        const std::string command = argv[1];
        if (command == "validate-stream") {
            if (argc != 2)
                throw std::invalid_argument("validate-stream takes no arguments");
            stream();
            return 0;
        }
        if (command == "features-stream") {
            EvaluationParameters parameters;
            if (argc == 4 && std::string_view(argv[2]) == "--eval-file")
                parameters = loadEvaluationParameters(argv[3]);
            else if (argc != 2)
                throw std::invalid_argument("features-stream accepts only --eval-file FILE");
            featureStream(parameters);
            return 0;
        }
        if (command == "bench") {
            int depth = 5;
            SearchMode mode = SearchMode::Optimized;
            if (argc > 4)
                throw std::invalid_argument("bench accepts depth and search profile");
            if (argc >= 3) {
                const std::string_view text = argv[2];
                const auto [end, error] =
                    std::from_chars(text.data(), text.data() + text.size(), depth);
                if (error != std::errc{} || end != text.data() + text.size() || depth < 1 ||
                    depth > 12)
                    throw std::invalid_argument("Benchmark depth must be between 1 and 12");
            }
            if (argc == 4) {
                const std::string_view profile = argv[3];
                if (profile == "Baseline")
                    mode = SearchMode::Baseline;
                else if (profile != "Optimized")
                    throw std::invalid_argument("Search profile must be Baseline or Optimized");
            }
            benchmark(depth, mode);
            return 0;
        }
        int index = 2, depth = 0;
        if (command == "perft" || command == "divide") {
            if (index == argc)
                throw std::invalid_argument("Missing depth");
            const std::string_view text = argv[index++];
            const auto [end, error] =
                std::from_chars(text.data(), text.data() + text.size(), depth);
            if (error != std::errc{} || end != text.data() + text.size() || depth < 0 || depth > 10)
                throw std::invalid_argument("Depth must be an integer between 0 and 10");
        } else if (command != "inspect" && command != "eval" && command != "legal") {
            throw std::invalid_argument("Unknown command: " + command);
        }
        std::string fen{StartFen}, moves;
        bool sawFen = false, sawMoves = false;
        while (index < argc) {
            const std::string option = argv[index++];
            if (index == argc)
                throw std::invalid_argument("Missing option value");
            if (option == "--fen" && !sawFen) {
                fen = argv[index++];
                sawFen = true;
            } else if (option == "--moves" && !sawMoves) {
                moves = argv[index++];
                sawMoves = true;
            } else
                throw std::invalid_argument("Unknown or duplicate option: " + option);
        }
        auto board = Board::fromFen(fen);
        applyMoves(board, moves);
        if (command == "inspect")
            inspect(board);
        else if (command == "eval")
            printEvaluation(evaluateDetailed(board));
        else if (command == "legal")
            for (const auto &move : moveNames(board))
                std::cout << move << '\n';
        else if (command == "perft")
            std::cout << perft(board, depth) << '\n';
        else {
            std::uint64_t total = 0;
            for (const auto &[move, nodes] : perftDivide(board, depth)) {
                std::cout << move.uci() << ": " << nodes << '\n';
                total += nodes;
            }
            std::cout << "total: " << total << '\n';
        }
        return 0;
    } catch (const std::exception &error) {
        std::cerr << "error: " << error.what() << '\n';
        return 2;
    }
}
