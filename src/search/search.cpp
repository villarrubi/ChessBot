#include "search.h"
#include "board/movegen.h"
#include "eval/evaluation.h"
#include "ordering.h"
#include "time_manager.h"
#include <algorithm>
#include <array>
#include <cmath>

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

class Searcher {
  public:
    Searcher(Board board, const SearchLimits &limits, TranspositionTable &table,
             std::atomic_bool &stop, int overhead, EvaluationMode evaluationMode,
             const EvaluationParameters &evaluationParameters, const NnueNetwork *network,
             SearchMode searchMode, const SearchInfoCallback &callback)
        : board_(std::move(board)), limits_(limits), table_(table), stop_(stop),
          callback_(callback), evaluationMode_(evaluationMode),
          evaluationParameters_(evaluationParameters), network_(network), searchMode_(searchMode) {
        timer_.start(limits, board_.sideToMove(), overhead);
        if (network_)
            accumulator_ = network_->refresh(board_);
    }

    SearchResult run() {
        table_.newSearch();
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
    std::uint64_t nodes_ = 0, qnodes_ = 0, ttHits_ = 0, betaCutoffs_ = 0;
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
    void updateResultCounters() {
        result_.nodes = nodes_;
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
        if (limits_.nodes && nodes_ >= limits_.nodes) {
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
        ++nodes_;
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
        if (const auto *entry = table_.probe(board_.key()))
            ttMove = entry->bestMove;
        orderMoves(moves, ttMove, {}, {}, optimized() ? &history_ : nullptr, board_.sideToMove());
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
        if (bestMove)
            table_.store(board_.key(), bestMove, toTable(best, 0), depth,
                         best <= originalAlpha ? Bound::Upper
                         : best >= beta        ? Bound::Lower
                                               : Bound::Exact,
                         static_cast<int>(board_.halfmoveClock()));
        return {bestMove, best, std::move(bestLine)};
    }
    std::vector<RootVariation> searchVariations(int depth) {
        std::vector<RootVariation> variations;
        const int requested =
            std::min(std::clamp(limits_.multiPv, 1, 10), static_cast<int>(rootMoves_.size()));
        for (int index = 0; index < requested && !stopped(); ++index) {
            RootVariation variation;
            if (index == 0 && requested == 1 && optimized() && depth >= 4 && result_.completed) {
                int window = 35;
                while (!stopped()) {
                    const Score alpha = std::max(-ScoreInfinity, result_.score - window);
                    const Score beta = std::min(ScoreInfinity, result_.score + window);
                    variation = searchRoot(depth, alpha, beta, {});
                    if (!variation.move || (variation.score > alpha && variation.score < beta) ||
                        (alpha == -ScoreInfinity && beta == ScoreInfinity))
                        break;
                    ++aspirationResearches_;
                    window = std::min(ScoreInfinity, window * 2);
                }
            } else {
                std::vector<Move> excluded;
                excluded.reserve(variations.size());
                for (const auto &previous : variations)
                    excluded.push_back(previous.move);
                variation = searchRoot(depth, -ScoreInfinity, ScoreInfinity, excluded);
            }
            if (!variation.move)
                break;
            variations.push_back(std::move(variation));
        }
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
        if (const auto *entry = table_.probe(board_.key())) {
            ++ttHits_;
            ttMove = entry->bestMove;
            const Score ttScore = fromTable(entry->score, ply);
            if (entry->depth >= depth &&
                entry->rule50 == std::min<std::uint64_t>(100, board_.halfmoveClock())) {
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

        const Score staticEval = staticEvaluation();
        if (optimized() && allowNull && !inCheck && depth >= 6 && staticEval >= beta &&
            beta < ScoreMate - MaxPly && hasNullMaterial()) {
            ++nullMoveAttempts_;
            StateInfo state;
            board_.makeNullMove(state);
            ++nullDepth_;
            const int reduction = 2 + depth / 4;
            const Score score =
                -negamax(std::max(0, depth - 1 - reduction), -beta, -beta + 1, ply + 1, false);
            --nullDepth_;
            board_.unmakeNullMove(state);
            if (stopped())
                return 0;
            if (score >= beta) {
                ++nullMoveCutoffs_;
                return score;
            }
        }

        auto moves = legalMoveList(board_);
        countMoves(moves.size());
        if (moves.empty())
            return inCheck ? -ScoreMate + ply : ScoreDraw;
        orderMoves(moves, ttMove, killers_[ply][0], killers_[ply][1],
                   optimized() ? &history_ : nullptr, board_.sideToMove());
        Score best = -ScoreInfinity;
        Move bestMove;
        int searched = 0;
        const Color side = board_.sideToMove();
        for (const Move move : moves) {
            const bool isQuiet = quiet(move);
            StateInfo state;
            makeMove(move, state);
            const bool givesCheck = board_.inCheck(board_.sideToMove());
            const int childDepth = depth - 1;
            Score score;
            if (optimized() && searched > 0) {
                int reduction = 0;
                if (depth >= 6 && searched >= 4 && isQuiet && !inCheck && !givesCheck) {
                    reduction = 1 + (depth >= 6 && searched >= 6 ? 1 : 0);
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
        if (best == -ScoreInfinity)
            best = staticEval;
        const Bound bound = best <= originalAlpha ? Bound::Upper
                            : best >= beta        ? Bound::Lower
                                                  : Bound::Exact;
        table_.store(board_.key(), bestMove, toTable(best, ply), depth, bound,
                     static_cast<int>(board_.halfmoveClock()));
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
        auto moves = legalMoveList(board_);
        countMoves(moves.size());
        if (moves.empty())
            return check ? -ScoreMate + ply : ScoreDraw;
        if (!check) {
            const Score standPat = staticEvaluation();
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
        for (const Move move : moves) {
            StateInfo state;
            makeMove(move, state);
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
        return alpha;
    }
};
} // namespace

SearchResult runSearch(Board board, const SearchLimits &limits, TranspositionTable &table,
                       std::atomic_bool &stop, int moveOverheadMs, EvaluationMode evaluationMode,
                       const EvaluationParameters &evaluationParameters, const NnueNetwork *network,
                       SearchMode searchMode, const SearchInfoCallback &callback) {
    return Searcher(std::move(board), limits, table, stop, moveOverheadMs, evaluationMode,
                    evaluationParameters, network, searchMode, callback)
        .run();
}
} // namespace chessbot
