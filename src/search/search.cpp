#include "search.h"
#include "board/movegen.h"
#include "eval/evaluation.h"
#include "ordering.h"
#include "time_manager.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <exception>
#include <thread>
#include <vector>

namespace chessbot {
namespace {
Score toTable(Score score, int ply) {
    if (score >= ScoreMate - MaxPly)
        return score + ply;
    if (score <= -ScoreMate + MaxPly)
        return score - ply;
    return score;
}
Score fromTable(Score score, int ply) {
    if (score >= ScoreMate - MaxPly)
        return score - ply;
    if (score <= -ScoreMate + MaxPly)
        return score + ply;
    return score;
}
bool contains(const std::vector<Move> &moves, Move candidate) {
    return std::find(moves.begin(), moves.end(), candidate) != moves.end();
}
bool quiet(Move move) {
    return !move.has(Capture) && move.promotion() == None;
}
int lateMoveReduction(int depth, int searched) {
    static const auto reductions = [] {
        std::array<std::array<int, 256>, MaxPly> table{};
        for (int d = 1; d < MaxPly; ++d)
            for (int n = 0; n < 256; ++n)
                table[d][n] = 1 + static_cast<int>(std::log(static_cast<double>(d)) *
                                                   std::log(static_cast<double>(n + 1)) / 2.25);
        return table;
    }();
    return reductions[depth][searched];
}
int materialValue(PieceType piece) {
    switch (piece) {
    case Pawn:
        return 100;
    case Knight:
        return 320;
    case Bishop:
        return 330;
    case Rook:
        return 500;
    case Queen:
        return 900;
    default:
        return 0;
    }
}

struct SharedSearchState {
    explicit SharedSearchState(std::uint64_t nodeLimit) : nodeLimit(nodeLimit) {}
    std::atomic<std::uint64_t> nodes{0};
    const std::uint64_t nodeLimit;
};

class Searcher {
  public:
    Searcher(Board board, const SearchLimits &limits, TranspositionTable &table,
             std::atomic_bool &stop, SharedSearchState &shared, int workerIndex, int overhead,
             EvaluationMode evaluationMode, const EvaluationParameters &evaluationParameters,
             const NnueNetwork *network, SearchMode searchMode, const SearchInfoCallback &callback)
        : board_(std::move(board)), limits_(limits), table_(table), stop_(stop), shared_(shared),
          workerIndex_(workerIndex), callback_(callback), evaluationMode_(evaluationMode),
          evaluationParameters_(evaluationParameters), network_(network), searchMode_(searchMode) {
        timer_.start(limits, board_.sideToMove(), overhead);
        if (network_)
            accumulator_ = network_->refresh(board_);
    }

    SearchResult run() {
        rootMoves_ = legalMoveList(board_);
        if (!limits_.rootMoves.empty()) {
            std::size_t kept = 0;
            for (const Move move : rootMoves_)
                if (contains(limits_.rootMoves, move))
                    rootMoves_[kept++] = move;
            rootMoves_.resize(kept);
        }
        if (rootMoves_.empty()) {
            result_.score = board_.inCheck(board_.sideToMove()) ? -ScoreMate : ScoreDraw;
            result_.completed = true;
            updateResultCounters();
            return result_;
        }
        result_.bestMove = rootMoves_[0];
        if (drawn()) {
            result_.completed = true;
            updateResultCounters();
            return result_;
        }
        const int maximumDepth =
            std::clamp(limits_.depth > 0 ? limits_.depth : MaxPly - 2, 1, MaxPly - 2);
        for (int depth = 1; depth <= maximumDepth && !stopped(); ++depth) {
            if (workerIndex_ > 0 && depth >= 6 && depth < maximumDepth &&
                (depth + workerIndex_) % 4 == 0)
                continue;
            const auto variations = searchVariations(depth);
            if (stopped() || variations.empty())
                break;
            result_.variations = variations;
            result_.score = variations.front().score;
            result_.principalVariation = variations.front().principalVariation;
            result_.bestMove = variations.front().move;
            result_.ponderMove =
                result_.principalVariation.size() > 1 ? result_.principalVariation[1] : Move{};
            result_.depth = depth;
            result_.completed = true;
            updateResultCounters();
            if (callback_)
                callback_(result_, table_.hashFullPermille());
            if ((limits_.depth == 0 && timer_.softExpired()) ||
                std::abs(result_.score) >= ScoreMate - MaxPly)
                break;
        }
        updateResultCounters();
        return result_;
    }

  private:
    Board board_;
    const SearchLimits &limits_;
    TranspositionTable &table_;
    std::atomic_bool &stop_;
    SharedSearchState &shared_;
    int workerIndex_;
    const SearchInfoCallback &callback_;
    EvaluationMode evaluationMode_;
    const EvaluationParameters &evaluationParameters_;
    const NnueNetwork *network_;
    NnueAccumulator accumulator_;
    SearchMode searchMode_;
    TimeManager timer_;
    SearchResult result_;
    MoveList rootMoves_;
    std::array<std::array<Move, MaxPly>, MaxPly> pv_{};
    std::array<int, MaxPly> pvLength_{};
    std::array<std::array<Move, 2>, MaxPly> killers_{};
    HistoryTable history_{};
    std::uint64_t nodes_ = 0, publishedNodes_ = 0, qnodes_ = 0, ttHits_ = 0, betaCutoffs_ = 0;
    std::uint64_t firstMoveCutoffs_ = 0, generatedMoves_ = 0, aspirationResearches_ = 0;
    std::uint64_t nullMoveAttempts_ = 0, nullMoveCutoffs_ = 0, lmrReductions_ = 0;
    std::uint64_t lmrResearches_ = 0;
    int selectiveDepth_ = 0, maximumBranching_ = 0, nullDepth_ = 0;

    bool optimized() const {
        return searchMode_ == SearchMode::Optimized;
    }
    Score staticEvaluation() const {
        return network_ ? network_->evaluate(board_, accumulator_)
                        : evaluate(board_, evaluationMode_, evaluationParameters_);
    }
    void makeMove(Move move, StateInfo &state) {
        board_.makeMove(move, state);
        if (network_)
            network_->updateAfterMove(accumulator_, board_, move, state);
    }
    void unmakeMove(Move move, const StateInfo &state) {
        if (network_)
            network_->updateBeforeUnmake(accumulator_, board_, move, state);
        board_.unmakeMove(move, state);
    }
    void clearPv() {
        for (auto &row : pv_)
            row.fill({});
        pvLength_.fill(0);
    }
    void publishNodes() {
        if (shared_.nodeLimit || publishedNodes_ == nodes_)
            return;
        shared_.nodes.fetch_add(nodes_ - publishedNodes_, std::memory_order_relaxed);
        publishedNodes_ = nodes_;
    }
    void updateResultCounters() {
        publishNodes();
        result_.nodes = shared_.nodes.load(std::memory_order_relaxed);
        result_.qnodes = qnodes_;
        result_.ttHits = ttHits_;
        result_.betaCutoffs = betaCutoffs_;
        result_.firstMoveCutoffs = firstMoveCutoffs_;
        result_.generatedMoves = generatedMoves_;
        result_.aspirationResearches = aspirationResearches_;
        result_.nullMoveAttempts = nullMoveAttempts_;
        result_.nullMoveCutoffs = nullMoveCutoffs_;
        result_.lmrReductions = lmrReductions_;
        result_.lmrResearches = lmrResearches_;
        result_.maximumBranching = maximumBranching_;
        result_.selectiveDepth = selectiveDepth_;
        result_.timeMs = timer_.elapsedMs();
    }
    bool stopped() {
        if (stop_.load(std::memory_order_relaxed))
            return true;
        if (shared_.nodeLimit &&
            shared_.nodes.load(std::memory_order_relaxed) >= shared_.nodeLimit) {
            stop_.store(true, std::memory_order_relaxed);
            return true;
        }
        if ((nodes_ & 255U) == 0 && timer_.hardExpired()) {
            stop_.store(true, std::memory_order_relaxed);
            return true;
        }
        return false;
    }
    bool enterNode(int ply, bool quiescence) {
        if (stopped())
            return false;
        if (shared_.nodeLimit) {
            auto current = shared_.nodes.load(std::memory_order_relaxed);
            while (true) {
                if (current >= shared_.nodeLimit) {
                    stop_.store(true, std::memory_order_relaxed);
                    return false;
                }
                if (shared_.nodes.compare_exchange_weak(current, current + 1,
                                                        std::memory_order_relaxed))
                    break;
            }
        }
        ++nodes_;
        if (!shared_.nodeLimit && (nodes_ - publishedNodes_) >= 1024)
            publishNodes();
        if (quiescence)
            ++qnodes_;
        selectiveDepth_ = std::max(selectiveDepth_, ply);
        return true;
    }
    bool drawn() const {
        if (board_.isInsufficientMaterial())
            return true;
        return nullDepth_ == 0 && (board_.halfmoveClock() >= 100 || board_.isThreefoldRepetition());
    }
    void countMoves(std::size_t count) {
        generatedMoves_ += count;
        maximumBranching_ = std::max(maximumBranching_, static_cast<int>(count));
    }
    void updatePv(int ply, Move move) {
        pv_[ply][0] = move;
        const int childLength = ply + 1 < MaxPly ? pvLength_[ply + 1] : 0;
        for (int index = 0; index < childLength && index + 1 < MaxPly; ++index)
            pv_[ply][index + 1] = pv_[ply + 1][index];
        pvLength_[ply] = std::min(MaxPly, childLength + 1);
    }
    void recordQuietCutoff(int ply, Move move, Color side, int depth) {
        if (killers_[ply][0] != move) {
            killers_[ply][1] = killers_[ply][0];
            killers_[ply][0] = move;
        }
        auto &value = history_[side][move.from()][move.to()];
        value = std::min(20'000, value + depth * depth);
    }
    bool hasNullMaterial() const {
        const Color side = board_.sideToMove();
        return board_.pieces(side, Knight) || board_.pieces(side, Bishop) ||
               board_.pieces(side, Rook) || board_.pieces(side, Queen);
    }

    RootVariation searchRoot(int depth, Score alpha, Score beta,
                             const std::vector<Move> &excluded) {
        clearPv();
        auto moves = rootMoves_;
        Move ttMove;
        if (const auto entry = table_.probe(board_.key()))
            ttMove = entry->bestMove;
        orderMoves(moves, ttMove, {}, {}, optimized() ? &history_ : nullptr, board_.sideToMove());
        if (optimized() && limits_.multiPv > 1 && !result_.variations.empty()) {
            // Preserve the previous iteration's MultiPV order. The root TT entry
            // alone cannot represent the best move for every excluded-move set.
            const auto rank = [&](Move move) {
                for (std::size_t i = 0; i < result_.variations.size(); ++i)
                    if (result_.variations[i].move == move)
                        return i;
                return result_.variations.size();
            };
            std::stable_sort(moves.begin(), moves.end(),
                             [&](Move a, Move b) { return rank(a) < rank(b); });
        }
        const Score originalAlpha = alpha;
        Score best = -ScoreInfinity;
        Move bestMove;
        std::vector<Move> bestLine;
        int searched = 0;
        countMoves(moves.size());
        for (const Move move : moves) {
            if (contains(excluded, move))
                continue;
            StateInfo state;
            makeMove(move, state);
            Score score;
            if (optimized() && searched > 0) {
                score = -negamax(depth - 1, -alpha - 1, -alpha, 1, true);
                if (score > alpha && score < beta)
                    score = -negamax(depth - 1, -beta, -alpha, 1, true);
            } else
                score = -negamax(depth - 1, -beta, -alpha, 1, true);
            unmakeMove(move, state);
            if (stopped())
                return {};
            ++searched;
            if (score > best) {
                best = score;
                bestMove = move;
                bestLine.assign(1, move);
                bestLine.insert(bestLine.end(), pv_[1].begin(), pv_[1].begin() + pvLength_[1]);
            }
            alpha = std::max(alpha, score);
            if (alpha >= beta) {
                ++betaCutoffs_;
                if (searched == 1)
                    ++firstMoveCutoffs_;
                break;
            }
        }
        // A search with excluded/restricted root moves is not an exact result
        // for the unrestricted position and must not overwrite its TT entry.
        if (bestMove && excluded.empty() && limits_.rootMoves.empty())
            table_.store(board_.key(), bestMove, toTable(best, 0), depth,
                         best <= originalAlpha ? Bound::Upper
                         : best >= beta        ? Bound::Lower
                                               : Bound::Exact,
                         static_cast<int>(board_.halfmoveClock()), optimized());
        return {bestMove, best, std::move(bestLine)};
    }
    std::vector<RootVariation> searchVariations(int depth) {
        std::vector<RootVariation> variations;
        const int requested =
            std::min(std::max(limits_.multiPv, 1), static_cast<int>(rootMoves_.size()));
        for (int index = 0; index < requested && !stopped(); ++index) {
            RootVariation variation;
            std::vector<Move> excluded;
            excluded.reserve(variations.size());
            for (const auto &previous : variations)
                excluded.push_back(previous.move);
            if (optimized() && depth >= 4 &&
                static_cast<std::size_t>(index) < result_.variations.size()) {
                const Score previousScore = result_.variations[index].score;
                int window = 35;
                while (!stopped()) {
                    const Score alpha = std::max(-ScoreInfinity, previousScore - window);
                    const Score beta = std::min(ScoreInfinity, previousScore + window);
                    variation = searchRoot(depth, alpha, beta, excluded);
                    if (!variation.move || (variation.score > alpha && variation.score < beta) ||
                        (alpha == -ScoreInfinity && beta == ScoreInfinity))
                        break;
                    ++aspirationResearches_;
                    window = std::min(ScoreInfinity, window * 2);
                }
            } else {
                variation = searchRoot(depth, -ScoreInfinity, ScoreInfinity, excluded);
            }
            if (!variation.move)
                break;
            variations.push_back(std::move(variation));
        }
        std::stable_sort(
            variations.begin(), variations.end(),
            [](const RootVariation &a, const RootVariation &b) { return a.score > b.score; });
        return variations;
    }

    Score negamax(int depth, Score alpha, Score beta, int ply, bool allowNull) {
        pvLength_[ply] = 0;
        if (depth <= 0)
            return quiescence(alpha, beta, ply);
        if (!enterNode(ply, false))
            return 0;
        if (drawn()) {
            if (board_.inCheck(board_.sideToMove()) && legalMoveList(board_).empty())
                return -ScoreMate + ply;
            return ScoreDraw;
        }
        if (ply >= MaxPly - 1)
            return staticEvaluation();
        const bool inCheck = board_.inCheck(board_.sideToMove());
        const Score originalAlpha = alpha;
        Move ttMove;
        if (const auto entry = table_.probe(board_.key())) {
            ++ttHits_;
            ttMove = entry->bestMove;
            const Score ttScore = fromTable(entry->score, ply);
            const auto rule50 = std::min<std::uint64_t>(100, board_.halfmoveClock());
            const bool rule50Compatible =
                entry->rule50 == rule50 ||
                (optimized() && entry->rule50 + depth < 100 && rule50 + depth < 100);
            if (entry->depth >= depth && rule50Compatible) {
                if (entry->bound == Bound::Exact) {
                    if (ttMove) {
                        pv_[ply][0] = ttMove;
                        pvLength_[ply] = 1;
                    }
                    return ttScore;
                }
                if (entry->bound == Bound::Lower && ttScore >= beta)
                    return ttScore;
                if (entry->bound == Bound::Upper && ttScore <= alpha)
                    return ttScore;
            }
        }

        if (optimized() && !ttMove && !inCheck && depth >= 6)
            --depth;

        const Score staticEval = staticEvaluation();
        const bool narrowWindow = beta - alpha == 1;
        if (optimized() && narrowWindow && !inCheck && depth <= 3 && alpha > -ScoreMate + MaxPly &&
            staticEval + 220 * depth <= alpha) {
            const Score razor = quiescence(alpha, beta, ply);
            if (razor <= alpha)
                return razor;
        }
        if (optimized() && narrowWindow && !inCheck && depth <= 7 &&
            std::abs(beta) < ScoreMate - MaxPly && staticEval - 80 * depth >= beta)
            return hasLegalMove(board_) ? staticEval : ScoreDraw;
        if (optimized() && allowNull && !inCheck && depth >= 3 && staticEval >= beta &&
            std::abs(beta) < ScoreMate - MaxPly && hasNullMaterial()) {
            ++nullMoveAttempts_;
            StateInfo state;
            board_.makeNullMove(state);
            ++nullDepth_;
            const int reduction = 2 + depth / 3;
            const Score score =
                -negamax(std::max(0, depth - 1 - reduction), -beta, -beta + 1, ply + 1, false);
            --nullDepth_;
            board_.unmakeNullMove(state);
            if (stopped())
                return 0;
            if (score >= beta) {
                ++nullMoveCutoffs_;
                return hasLegalMove(board_) ? score : ScoreDraw;
            }
        }

        auto moves = optimized() ? pseudoLegalMoveList(board_) : legalMoveList(board_);
        countMoves(moves.size());
        if (!optimized() && moves.empty())
            return inCheck ? -ScoreMate + ply : ScoreDraw;
        orderMoves(moves, ttMove, killers_[ply][0], killers_[ply][1],
                   optimized() ? &history_ : nullptr, board_.sideToMove());
        Score best = -ScoreInfinity;
        Move bestMove;
        int searched = 0;
        const Color side = board_.sideToMove();
        int legalMoves = 0;
        for (const Move move : moves) {
            const bool isQuiet = quiet(move);
            StateInfo state;
            makeMove(move, state);
            if (optimized() && board_.inCheck(side)) {
                unmakeMove(move, state);
                continue;
            }
            ++legalMoves;
            const bool givesCheck = board_.inCheck(board_.sideToMove());
            const int childDepth = depth - 1;
            if (optimized() && depth <= 3 && searched > 0 && isQuiet && !inCheck && !givesCheck &&
                std::abs(alpha) < ScoreMate - MaxPly && staticEval + 100 * depth <= alpha) {
                unmakeMove(move, state);
                continue;
            }
            if (optimized() && narrowWindow && depth <= 6 && isQuiet && !inCheck && !givesCheck &&
                std::abs(alpha) < ScoreMate - MaxPly && searched >= 4 + 2 * depth) {
                unmakeMove(move, state);
                continue;
            }
            Score score;
            if (optimized() && searched > 0) {
                int reduction = 0;
                if (depth >= 3 && searched >= 3 && isQuiet && !inCheck && !givesCheck) {
                    reduction = lateMoveReduction(depth, searched);
                    if (narrowWindow && depth >= 5)
                        ++reduction;
                    reduction = std::min(reduction, childDepth - 1);
                }
                if (reduction > 0) {
                    ++lmrReductions_;
                    score = -negamax(childDepth - reduction, -alpha - 1, -alpha, ply + 1, true);
                    if (score > alpha) {
                        ++lmrResearches_;
                        score = -negamax(childDepth, -alpha - 1, -alpha, ply + 1, true);
                    }
                } else
                    score = -negamax(childDepth, -alpha - 1, -alpha, ply + 1, true);
                if (score > alpha && score < beta)
                    score = -negamax(childDepth, -beta, -alpha, ply + 1, true);
            } else
                score = -negamax(childDepth, -beta, -alpha, ply + 1, true);
            unmakeMove(move, state);
            if (stopped())
                return 0;
            const int moveIndex = searched++;
            if (score > best) {
                best = score;
                bestMove = move;
            }
            if (score > alpha) {
                alpha = score;
                updatePv(ply, move);
            }
            if (alpha >= beta) {
                ++betaCutoffs_;
                if (moveIndex == 0)
                    ++firstMoveCutoffs_;
                if (isQuiet)
                    recordQuietCutoff(ply, move, side, depth);
                break;
            }
        }
        if (optimized() && legalMoves == 0)
            return inCheck ? -ScoreMate + ply : ScoreDraw;
        if (best == -ScoreInfinity)
            best = staticEval;
        const Bound bound = best <= originalAlpha ? Bound::Upper
                            : best >= beta        ? Bound::Lower
                                                  : Bound::Exact;
        table_.store(board_.key(), bestMove, toTable(best, ply), depth, bound,
                     static_cast<int>(board_.halfmoveClock()), optimized());
        return best;
    }
    Score quiescence(Score alpha, Score beta, int ply) {
        pvLength_[ply] = 0;
        if (!enterNode(ply, true))
            return 0;
        if (drawn()) {
            if (board_.inCheck(board_.sideToMove()) && legalMoveList(board_).empty())
                return -ScoreMate + ply;
            return ScoreDraw;
        }
        if (ply >= MaxPly - 1)
            return staticEvaluation();
        const bool check = board_.inCheck(board_.sideToMove());
        auto moves = optimized() ? pseudoLegalMoveList(board_) : legalMoveList(board_);
        countMoves(moves.size());
        if (check && !optimized() && moves.empty())
            return -ScoreMate + ply;
        if (!check && !optimized() && moves.empty())
            return ScoreDraw;
        if (!check && optimized() && !hasLegalMove(board_, moves))
            return ScoreDraw;
        Score standPat = -ScoreInfinity;
        if (!check) {
            standPat = staticEvaluation();
            if (standPat >= beta)
                return standPat;
            alpha = std::max(alpha, standPat);
            std::size_t kept = 0;
            for (const Move move : moves)
                if (move.has(Capture) || move.promotion() != None)
                    moves[kept++] = move;
            moves.resize(kept);
        }
        orderMoves(moves, {});
        int searched = 0;
        int legalMoves = 0;
        const Color side = board_.sideToMove();
        for (const Move move : moves) {
            if (optimized() && !check && move.promotion() == None &&
                std::abs(alpha) < ScoreMate - MaxPly &&
                standPat + materialValue(move.captured()) + 150 < alpha)
                continue;
            StateInfo state;
            makeMove(move, state);
            if (optimized() && board_.inCheck(side)) {
                unmakeMove(move, state);
                continue;
            }
            ++legalMoves;
            const Score score = -quiescence(-beta, -alpha, ply + 1);
            unmakeMove(move, state);
            if (stopped())
                return 0;
            if (score > alpha) {
                alpha = score;
                updatePv(ply, move);
                if (alpha >= beta) {
                    ++betaCutoffs_;
                    if (searched == 0)
                        ++firstMoveCutoffs_;
                    break;
                }
            }
            ++searched;
        }
        if (optimized() && check && legalMoves == 0)
            return -ScoreMate + ply;
        return alpha;
    }
};
} // namespace

SearchResult runSearch(Board board, const SearchLimits &limits, TranspositionTable &table,
                       std::atomic_bool &stop, int moveOverheadMs, EvaluationMode evaluationMode,
                       const EvaluationParameters &evaluationParameters, const NnueNetwork *network,
                       SearchMode searchMode, int threadCount, const SearchInfoCallback &callback) {
    table.newSearch();
    SharedSearchState shared(limits.nodes);
    std::vector<SearchResult> results(static_cast<std::size_t>(threadCount));
    std::vector<std::exception_ptr> errors(static_cast<std::size_t>(threadCount));
    std::vector<std::thread> workers;
    workers.reserve(static_cast<std::size_t>(threadCount - 1));
    try {
        for (int index = 1; index < threadCount; ++index) {
            workers.emplace_back([&, index, workerBoard = board]() mutable {
                try {
                    results[static_cast<std::size_t>(index)] =
                        Searcher(std::move(workerBoard), limits, table, stop, shared, index,
                                 moveOverheadMs, evaluationMode, evaluationParameters, network,
                                 searchMode, {})
                            .run();
                    // Any worker that completed the requested depth and all
                    // variations has a usable result; don't wait for worker 0.
                    if (limits.depth > 0 &&
                        results[static_cast<std::size_t>(index)].depth >= limits.depth)
                        stop.store(true, std::memory_order_relaxed);
                } catch (...) {
                    errors[static_cast<std::size_t>(index)] = std::current_exception();
                    stop.store(true, std::memory_order_relaxed);
                }
            });
        }
    } catch (...) {
        stop.store(true, std::memory_order_relaxed);
        for (auto &worker : workers)
            worker.join();
        throw;
    }
    try {
        results[0] = Searcher(std::move(board), limits, table, stop, shared, 0, moveOverheadMs,
                              evaluationMode, evaluationParameters, network, searchMode, callback)
                         .run();
    } catch (...) {
        errors[0] = std::current_exception();
    }
    stop.store(true, std::memory_order_relaxed);
    for (auto &worker : workers)
        worker.join();
    for (const auto &error : errors)
        if (error)
            std::rethrow_exception(error);

    std::size_t selected = 0;
    for (std::size_t index = 1; index < results.size(); ++index)
        if (results[index].depth > results[selected].depth)
            selected = index;
    SearchResult result = results[selected];
    result.nodes = shared.nodes.load(std::memory_order_relaxed);
    result.qnodes = result.ttHits = result.betaCutoffs = result.firstMoveCutoffs = 0;
    result.generatedMoves = result.aspirationResearches = result.nullMoveAttempts = 0;
    result.nullMoveCutoffs = result.lmrReductions = result.lmrResearches = 0;
    result.maximumBranching = result.selectiveDepth = 0;
    for (const auto &workerResult : results) {
        result.qnodes += workerResult.qnodes;
        result.ttHits += workerResult.ttHits;
        result.betaCutoffs += workerResult.betaCutoffs;
        result.firstMoveCutoffs += workerResult.firstMoveCutoffs;
        result.generatedMoves += workerResult.generatedMoves;
        result.aspirationResearches += workerResult.aspirationResearches;
        result.nullMoveAttempts += workerResult.nullMoveAttempts;
        result.nullMoveCutoffs += workerResult.nullMoveCutoffs;
        result.lmrReductions += workerResult.lmrReductions;
        result.lmrResearches += workerResult.lmrResearches;
        result.maximumBranching = std::max(result.maximumBranching, workerResult.maximumBranching);
        result.selectiveDepth = std::max(result.selectiveDepth, workerResult.selectiveDepth);
        result.timeMs = std::max(result.timeMs, workerResult.timeMs);
    }
    if (selected != 0 && callback)
        callback(result, table.hashFullPermille());
    return result;
}
} // namespace chessbot
