"""Run a small paired UCI match and save a PGN; intended as the phase-3 regression runner."""
import argparse
import json
import math
import platform
from datetime import UTC, datetime
from pathlib import Path

import chess
import chess.engine
import chess.pgn


def engine_id(path: Path) -> str:
    return path.stem


def play_game(white: chess.engine.SimpleEngine, black: chess.engine.SimpleEngine,
              white_name: str, black_name: str, limit: chess.engine.Limit, max_plies: int,
              start: chess.Board) -> chess.pgn.Game:
    board = start.copy(stack=False)
    game = chess.pgn.Game()
    game.setup(board)
    game.headers.update({
        "Event": "ChessBot regression match",
        "Date": datetime.now(UTC).strftime("%Y.%m.%d"),
        "White": white_name,
        "Black": black_name,
    })
    node = game
    while not board.is_game_over(claim_draw=True) and board.ply() < max_plies:
        player = white if board.turn == chess.WHITE else black
        result = player.play(board, limit)
        if result.move not in board.legal_moves:
            raise RuntimeError(f"{white_name if board.turn else black_name} returned an illegal move")
        board.push(result.move)
        node = node.add_variation(result.move)
    if board.is_game_over(claim_draw=True):
        outcome = board.outcome(claim_draw=True)
        game.headers["Result"] = outcome.result() if outcome else "*"
        game.headers["Termination"] = outcome.termination.name.lower() if outcome else "unknown"
    else:
        game.headers["Result"] = "1/2-1/2"
        game.headers["Termination"] = "adjudication: maximum plies"
    return game


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-a", type=Path, required=True)
    parser.add_argument("--engine-b", type=Path, required=True)
    parser.add_argument("--games", type=int, default=2)
    limit_group = parser.add_mutually_exclusive_group()
    limit_group.add_argument("--depth", type=int)
    limit_group.add_argument("--movetime-ms", type=int)
    limit_group.add_argument("--nodes", type=int)
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--fen", default=chess.STARTING_FEN)
    parser.add_argument("--openings", type=Path,
                        help="UTF-8 file with one FEN per line; each is used for a color-reversed pair")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluation-a", choices=("Basic", "Positional"), default="Positional")
    parser.add_argument("--evaluation-b", choices=("Basic", "Positional"), default="Positional")
    parser.add_argument("--search-a", choices=("Baseline", "Optimized"), default="Optimized")
    parser.add_argument("--search-b", choices=("Baseline", "Optimized"), default="Optimized")
    parser.add_argument("--move-overhead", type=int, default=1)
    args = parser.parse_args()
    if args.games < 1 or args.max_plies < 1 or args.move_overhead < 0 or \
            (args.depth is not None and args.depth < 1) or \
            (args.movetime_ms is not None and args.movetime_ms < 1) or \
            (args.nodes is not None and args.nodes < 1):
        parser.error("games, limits and max-plies must be positive")
    if args.depth is None and args.movetime_ms is None and args.nodes is None:
        args.depth = 2
    if args.depth is not None:
        limit = chess.engine.Limit(depth=args.depth)
    elif args.nodes is not None:
        limit = chess.engine.Limit(nodes=args.nodes)
    else:
        limit = chess.engine.Limit(time=args.movetime_ms / 1000.0)
    engine_a = args.engine_a.resolve(strict=True)
    engine_b = args.engine_b.resolve(strict=True)
    opening_fens = [args.fen]
    if args.openings:
        opening_fens = [line.strip() for line in args.openings.read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.lstrip().startswith("#")]
        if not opening_fens:
            parser.error("opening file contains no FEN positions")
    starts = [chess.Board(fen) for fen in opening_fens]
    if any(not board.is_valid() for board in starts):
        parser.error("one or more FEN positions are not valid standard chess positions")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    first = chess.engine.SimpleEngine.popen_uci(str(engine_a))
    second = chess.engine.SimpleEngine.popen_uci(str(engine_b))
    first.configure({"Evaluation": args.evaluation_a, "SearchProfile": args.search_a,
                     "Move Overhead": args.move_overhead})
    second.configure({"Evaluation": args.evaluation_b, "SearchProfile": args.search_b,
                      "Move Overhead": args.move_overhead})
    games = []
    try:
        for index in range(args.games):
            start = starts[(index // 2) % len(starts)]
            swapped = index % 2 == 1
            white, black = (second, first) if swapped else (first, second)
            white_name, black_name = ((engine_id(engine_b), engine_id(engine_a)) if swapped else
                                      (engine_id(engine_a), engine_id(engine_b)))
            game = play_game(white, black, white_name, black_name, limit, args.max_plies, start)
            game.headers["Round"] = str(index + 1)
            game.headers["EngineA"] = str(engine_a)
            game.headers["EngineB"] = str(engine_b)
            if args.depth is not None:
                game.headers["SearchDepth"] = str(args.depth)
            elif args.nodes is not None:
                game.headers["SearchNodes"] = str(args.nodes)
            else:
                game.headers["MoveTimeMs"] = str(args.movetime_ms)
            game.headers["EvaluationA"] = args.evaluation_a
            game.headers["EvaluationB"] = args.evaluation_b
            game.headers["SearchProfileA"] = args.search_a
            game.headers["SearchProfileB"] = args.search_b
            game.headers["WhiteEvaluation"] = args.evaluation_b if swapped else args.evaluation_a
            game.headers["BlackEvaluation"] = args.evaluation_a if swapped else args.evaluation_b
            games.append(game)
    finally:
        first.quit()
        second.quit()

    with args.output.open("w", encoding="utf-8") as handle:
        exporter = chess.pgn.FileExporter(handle)
        for game in games:
            game.accept(exporter)
    game_scores = []
    for index, game in enumerate(games):
        result = game.headers["Result"]
        if result == "1/2-1/2":
            game_scores.append(0.5)
        elif result in ("1-0", "0-1"):
            a_is_white = index % 2 == 0
            game_scores.append(float((result == "1-0") == a_is_white))
        else:
            game_scores.append(0.5)
    score_a = sum(game_scores)
    pair_scores = [(game_scores[index] + game_scores[index + 1]) / 2
                   for index in range(0, len(game_scores) - 1, 2)]
    samples = pair_scores if len(pair_scores) >= 2 else game_scores
    score_rate = score_a / len(game_scores)
    variance = (sum((sample - score_rate) ** 2 for sample in samples) /
                (len(samples) - 1)) if len(samples) >= 2 else 0.0
    margin = 1.96 * math.sqrt(variance / max(1, len(samples)))
    confidence = [max(0.001, score_rate - margin), min(0.999, score_rate + margin)]
    elo = lambda rate: 400 * math.log10(rate / (1 - rate))
    summary = {
        "games": len(games),
        "results": {result: sum(g.headers["Result"] == result for g in games)
                    for result in ("1-0", "0-1", "1/2-1/2", "*")},
        "paired_colors": args.games > 1,
        "score_a": score_a,
        "score_b": len(games) - score_a,
        "wdl_a": {"wins": game_scores.count(1.0), "draws": game_scores.count(0.5),
                  "losses": game_scores.count(0.0)},
        "score_rate_a": round(score_rate, 4),
        "score_confidence95": [round(value, 4) for value in confidence],
        "elo_estimate": round(elo(min(0.999, max(0.001, score_rate))), 1),
        "elo_confidence95": [round(elo(value), 1) for value in confidence],
        "confidence_method": "normal approximation over paired-opening scores",
        "depth": args.depth,
        "movetime_ms": args.movetime_ms,
        "nodes": args.nodes,
        "search_a": args.search_a,
        "search_b": args.search_b,
        "max_plies": args.max_plies,
        "move_overhead": args.move_overhead,
        "platform": platform.platform(),
        "output": str(args.output),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
