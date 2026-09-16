"""Run reproducible UCI matches from free, FEN, named, or forced-line starts."""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import platform
import random
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn
import chess.polyglot


@dataclass
class Opening:
    identifier: str
    name: str
    eco: str | None
    start_fen: str
    moves: list[str]
    source: str
    version: str = "unversioned"

    def initial_board(self) -> chess.Board:
        return chess.Board() if self.start_fen == "startpos" else chess.Board(self.start_fen)


@dataclass
class EngineConfig:
    path: Path
    name: str
    options: dict[str, Any]
    cwd: Path | None
    environment: dict[str, str]


@dataclass
class RunningEngine:
    config: EngineConfig
    process: chess.engine.SimpleEngine
    identifier: dict[str, str]


def normalize_moves(start_fen: str, moves: list[str]) -> list[str]:
    board = chess.Board() if start_fen == "startpos" else chess.Board(start_fen)
    normalized = []
    for token in moves:
        try:
            move = chess.Move.from_uci(token.lower())
            if move not in board.legal_moves:
                raise ValueError
        except ValueError:
            try:
                move = board.parse_san(token)
            except ValueError as error:
                raise ValueError(f"illegal opening move {token!r} after {normalized}") from error
        normalized.append(move.uci())
        board.push(move)
    return normalized


def native_openings(path: Path) -> list[Opening]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("openings", [])
        version = str(payload.get("version", "unversioned"))
    elif isinstance(payload, list):
        rows = payload
        version = "unversioned"
    else:
        raise ValueError("native opening JSON must be an object or array")
    result = []
    for index, row in enumerate(rows):
        start = row.get("start_fen", "startpos")
        if start != "startpos" and not chess.Board(start).is_valid():
            raise ValueError(f"invalid FEN in opening {row.get('id', index)}")
        moves = normalize_moves(start, list(row.get("moves_uci", row.get("moves", []))))
        result.append(Opening(str(row.get("id", f"native-{index + 1}")),
                              str(row.get("name", row.get("id", f"Opening {index + 1}"))),
                              row.get("eco"), start, moves, str(path),
                              version))
    return result


def pgn_openings(path: Path) -> list[Opening]:
    result = []
    with path.open(encoding="utf-8") as handle:
        index = 0
        while game := chess.pgn.read_game(handle):
            index += 1
            if game.errors:
                raise ValueError(f"invalid opening PGN game {index}: {game.errors}")
            start = game.board().fen() if game.headers.get("SetUp") == "1" else "startpos"
            result.append(Opening(game.headers.get("OpeningId", f"pgn-{index}"),
                                  game.headers.get("Opening", game.headers.get("Event",
                                                                              f"PGN {index}")),
                                  game.headers.get("ECO"), start,
                                  normalize_moves(start, [move.uci() for move in
                                                          game.mainline_moves()]), str(path)))
    return result


def epd_openings(path: Path) -> list[Opening]:
    result = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        board, operations = chess.Board.from_epd(line)
        result.append(Opening(str(operations.get("id", f"epd-{index}")),
                              str(operations.get("id", f"EPD {index}")), None, board.fen(), [],
                              str(path)))
    return result


def text_openings(path: Path) -> list[Opening]:
    result = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            fields = [field.strip() for field in line.split("|")]
            if len(fields) != 5:
                raise ValueError("native text openings require id|name|eco|fen|moves")
            identifier, name, eco, start, raw_moves = fields
            moves = raw_moves.split()
        else:
            try:
                board = chess.Board(line)
                identifier, name, eco, start, moves = f"fen-{index}", f"FEN {index}", None, board.fen(), []
            except ValueError:
                identifier, name, eco, start, moves = f"line-{index}", f"Line {index}", None, "startpos", line.split()
        result.append(Opening(identifier, name, eco or None, start,
                              normalize_moves(start, moves), str(path)))
    return result


def polyglot_openings(path: Path) -> list[Opening]:
    board = chess.Board()
    result = []
    with chess.polyglot.open_reader(str(path)) as reader:
        for index, entry in enumerate(reader.find_all(board), start=1):
            move = entry.move
            result.append(Opening(f"polyglot-{index}", f"Polyglot root {move.uci()}", None,
                                  "startpos", [move.uci()], str(path)))
    return result


def load_openings(path: Path) -> list[Opening]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        result = native_openings(path)
    elif suffix == ".pgn":
        result = pgn_openings(path)
    elif suffix == ".epd":
        result = epd_openings(path)
    elif suffix == ".bin":
        result = polyglot_openings(path)
    else:
        result = text_openings(path)
    if not result:
        raise ValueError(f"opening source contains no entries: {path}")
    return result


def parse_json_object(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} must be valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def engine_config(path: Path, name: str | None, options: str, cwd: Path | None,
                  environment: str) -> EngineConfig:
    resolved = path.resolve(strict=True)
    resolved_cwd = cwd.resolve(strict=True) if cwd else None
    env = {str(key): str(value) for key, value in parse_json_object(environment, "environment").items()}
    return EngineConfig(resolved, name or resolved.stem, parse_json_object(options, "options"),
                        resolved_cwd, env)


def start_engine(config: EngineConfig, timeout: float) -> RunningEngine:
    environment = os.environ.copy()
    environment.update(config.environment)
    process = chess.engine.SimpleEngine.popen_uci(str(config.path), timeout=timeout,
                                                  cwd=str(config.cwd) if config.cwd else None,
                                                  env=environment)
    try:
        if config.options:
            process.configure(config.options)
    except Exception:
        process.close()
        raise
    return RunningEngine(config, process, dict(process.id))


def choose_assignment(mode: str, index: int) -> tuple[bool, str]:
    if mode in {"paired", "alternate"}:
        swapped = index % 2 == 1
    else:
        swapped = mode == "a-black"
    return swapped, "black" if swapped else "white"


def search_limit(args: argparse.Namespace, clocks: dict[chess.Color, float]) -> chess.engine.Limit:
    if args.depth is not None:
        return chess.engine.Limit(depth=args.depth)
    if args.nodes is not None:
        return chess.engine.Limit(nodes=args.nodes)
    if args.movetime_ms is not None:
        return chess.engine.Limit(time=args.movetime_ms / 1000)
    return chess.engine.Limit(white_clock=max(0, clocks[chess.WHITE]),
                              black_clock=max(0, clocks[chess.BLACK]),
                              white_inc=args.increment_ms / 1000,
                              black_inc=args.increment_ms / 1000,
                              remaining_moves=args.moves_to_go)


def result_for_winner(winner: chess.Color | None) -> str:
    if winner is None:
        return "1/2-1/2"
    return "1-0" if winner == chess.WHITE else "0-1"


def play_game(first: RunningEngine, second: RunningEngine, opening: Opening, index: int,
              args: argparse.Namespace) -> tuple[chess.pgn.Game, dict[str, Any]]:
    swapped, a_color_name = choose_assignment(args.color_mode, index)
    white, black = (second, first) if swapped else (first, second)
    board = opening.initial_board()
    game = chess.pgn.Game()
    game.setup(board)
    game.headers.update({"Event": args.event, "Site": "Local", "Date": datetime.now(UTC).strftime("%Y.%m.%d"),
                         "Round": str(index + 1), "White": white.config.name,
                         "Black": black.config.name, "Opening": opening.name,
                         "OpeningId": opening.identifier, "OpeningSource": opening.source,
                         "ReleasePly": str(len(opening.moves)), "EngineAColor": a_color_name})
    if opening.eco:
        game.headers["ECO"] = opening.eco
    node: chess.pgn.GameNode = game
    for move_name in opening.moves:
        move = chess.Move.from_uci(move_name)
        node = node.add_variation(move)
        node.comment = "forced opening prefix"
        board.push(move)
    initial_seconds = args.initial_ms / 1000 if args.initial_ms is not None else 0.0
    clocks = {chess.WHITE: initial_seconds, chess.BLACK: initial_seconds}
    move_records, failure = [], None
    termination = "maximum plies"
    winner: chess.Color | None = None
    while not board.is_game_over(claim_draw=True) and board.ply() < args.max_plies:
        side = board.turn
        running = white if side == chess.WHITE else black
        limit = search_limit(args, clocks)
        started = time.monotonic()
        try:
            played = running.process.play(board, limit, info=chess.engine.INFO_ALL)
            elapsed = time.monotonic() - started
            if played.move is None or played.move not in board.legal_moves:
                raise chess.engine.EngineError("engine returned no legal move")
            if args.initial_ms is not None:
                clocks[side] -= elapsed
                if clocks[side] < -args.clock_tolerance_ms / 1000:
                    raise TimeoutError("engine exceeded its game clock")
                clocks[side] += args.increment_ms / 1000
            san = board.san(played.move)
            board.push(played.move)
            node = node.add_variation(played.move)
            score = played.info.get("score")
            score_cp = score.pov(side).score(mate_score=100_000) if score else None
            info_string = played.info.get("string")
            record = {"ply": board.ply(), "side": "white" if side == chess.WHITE else "black",
                      "engine": running.config.name, "uci": played.move.uci(),
                      "san": san, "elapsed_ms": round(elapsed * 1000, 3),
                      "clock_ms": round(clocks[side] * 1000, 3) if args.initial_ms is not None else None,
                      "depth": played.info.get("depth"), "nodes": played.info.get("nodes"),
                      "score_cp": score_cp,
                      "book": info_string if isinstance(info_string, str) and
                      info_string.startswith("book move ") else None}
            move_records.append(record)
            node.comment = (f"clk {record['clock_ms']}ms; depth {record['depth']}; "
                            f"nodes {record['nodes']}; score {record['score_cp']}" +
                            (f"; {record['book']}" if record["book"] else ""))
        except (chess.engine.EngineError, chess.engine.EngineTerminatedError,
                TimeoutError, subprocess.SubprocessError, OSError) as error:
            failure = {"engine": running.config.name, "ply": board.ply() + 1,
                       "type": type(error).__name__, "message": str(error)}
            termination = "engine failure"
            if args.failure_policy == "abort":
                raise
            winner = None if args.failure_policy == "draw" else not side
            break
    if failure is None and board.is_game_over(claim_draw=True):
        outcome = board.outcome(claim_draw=True)
        winner = outcome.winner if outcome else None
        termination = outcome.termination.name.lower() if outcome else "unknown"
    game.headers["Result"] = result_for_winner(winner)
    game.headers["Termination"] = termination
    game.headers["FinalFEN"] = board.fen()
    metadata = {"round": index + 1, "result": game.headers["Result"],
                "termination": termination, "final_fen": board.fen(), "engine_a_color": a_color_name,
                "opening": {"id": opening.identifier, "name": opening.name, "eco": opening.eco,
                            "source": opening.source, "version": opening.version,
                            "start_fen": opening.start_fen,
                            "moves_uci": opening.moves, "release_ply": len(opening.moves)},
                "moves": move_records, "failure": failure}
    return game, metadata


def statistics(games: list[dict[str, Any]], sprt: tuple[float, float, float, float] | None,
               paired: bool) -> dict[str, Any]:
    scores = []
    for game in games:
        result, color = game["result"], game["engine_a_color"]
        if result == "1/2-1/2":
            scores.append(0.5)
        else:
            winner = "white" if result == "1-0" else "black"
            scores.append(float(winner == color))
    rate = sum(scores) / len(scores)
    pairs = [(scores[index] + scores[index + 1]) / 2
             for index in range(0, len(scores) - 1, 2)] if paired else []
    clustered = paired and bool(pairs)
    if clustered:
        clusters: dict[str, list[float]] = {}
        for index, pair_score in enumerate(pairs):
            opening = games[index * 2]["opening"]
            key = json.dumps({"id": opening["id"], "start_fen": opening["start_fen"],
                              "moves_uci": opening["moves_uci"]}, sort_keys=True)
            clusters.setdefault(key, []).append(pair_score)
        samples = [sum(values) / len(values) for values in clusters.values()]
    else:
        samples = scores
    sample_rate = sum(samples) / len(samples)
    variance = sum((sample - sample_rate) ** 2 for sample in samples) / max(1, len(samples) - 1)
    margin = 1.96 * math.sqrt(variance / len(samples)) if len(samples) >= 2 else 1.0
    def clamp_probability(value: float) -> float:
        return min(0.999, max(0.001, value))

    confidence = [clamp_probability(sample_rate - margin),
                  clamp_probability(sample_rate + margin)]

    def elo(value: float) -> float:
        return 400 * math.log10(value / (1 - value))
    result = {"games": len(scores), "wins": scores.count(1.0), "draws": scores.count(0.5),
              "losses": scores.count(0.0), "score": sum(scores), "score_rate": round(rate, 5),
              "score_confidence95": [round(value, 5) for value in confidence],
              "elo": round(elo(min(0.999, max(0.001, rate))), 2),
              "elo_confidence95": [round(elo(value), 2) for value in confidence],
              "independent_samples": len(samples),
              "confidence_method": ("normal approximation over opening-clustered paired scores"
                                    if clustered else
                                    "normal approximation over individual game scores")}
    if sprt:
        elo0, elo1, alpha, beta = sprt
        def probability(value: float) -> float:
            return 1 / (1 + 10 ** (-value / 400))

        p0, p1 = probability(elo0), probability(elo1)
        llr = sum(score * math.log(p1 / p0) + (1 - score) * math.log((1 - p1) / (1 - p0))
                  for score in samples)
        lower, upper = math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)
        decision = "accept_h1" if llr >= upper else "accept_h0" if llr <= lower else "continue"
        result["sprt"] = {"elo0": elo0, "elo1": elo1, "alpha": alpha, "beta": beta,
                          "llr": round(llr, 5), "bounds": [round(lower, 5), round(upper, 5)],
                          "decision": decision,
                          "method": "trinomial scores approximated as fractional Bernoulli"}
    return result


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, check=True,
                              capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-a", type=Path, required=True)
    parser.add_argument("--engine-b", type=Path, required=True)
    parser.add_argument("--name-a")
    parser.add_argument("--name-b")
    parser.add_argument("--options-a", default="{}")
    parser.add_argument("--options-b", default="{}")
    parser.add_argument("--cwd-a", type=Path)
    parser.add_argument("--cwd-b", type=Path)
    parser.add_argument("--env-a", default="{}")
    parser.add_argument("--env-b", default="{}")
    parser.add_argument("--games", type=int, default=2)
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument("--depth", type=int)
    limits.add_argument("--nodes", type=int)
    limits.add_argument("--movetime-ms", type=int)
    limits.add_argument("--initial-ms", type=int)
    parser.add_argument("--increment-ms", type=int, default=0)
    parser.add_argument("--moves-to-go", type=int)
    parser.add_argument("--clock-tolerance-ms", type=int, default=100)
    parser.add_argument("--max-plies", type=int, default=200)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--failure-policy", choices=("forfeit", "draw", "abort"), default="forfeit")
    parser.add_argument("--color-mode", choices=("paired", "alternate", "a-white", "a-black"),
                        default="paired")
    parser.add_argument("--fen")
    parser.add_argument("--moves", default="", help="additional forced SAN or UCI moves")
    parser.add_argument("--openings", type=Path)
    parser.add_argument("--opening-id")
    parser.add_argument("--opening-ids",
                        help="comma-separated opening identifiers to include")
    parser.add_argument("--opening-name")
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--event", default="ChessBot engine match")
    parser.add_argument("--engine-log-level", choices=("DEBUG", "INFO", "WARNING"),
                        default="WARNING",
                        help="verbosity of the technical UCI log written to engine.log")
    parser.add_argument("--sprt-elo0", type=float)
    parser.add_argument("--sprt-elo1", type=float)
    parser.add_argument("--sprt-alpha", type=float, default=0.05)
    parser.add_argument("--sprt-beta", type=float, default=0.05)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.games < 1 or args.max_plies < 1 or args.timeout <= 0:
        parser.error("games, max-plies and timeout must be positive")
    if all(value is None for value in (args.depth, args.nodes, args.movetime_ms, args.initial_ms)):
        args.depth = 2
    if any(value is not None and value < 1 for value in
           (args.depth, args.nodes, args.movetime_ms, args.initial_ms)):
        parser.error("search limits must be positive")
    if args.increment_ms < 0 or args.clock_tolerance_ms < 0:
        parser.error("clock values must be nonnegative")
    if (args.sprt_elo0 is None) != (args.sprt_elo1 is None):
        parser.error("SPRT requires both elo0 and elo1")
    root = Path(__file__).resolve().parents[1]
    config_a = engine_config(args.engine_a, args.name_a, args.options_a, args.cwd_a, args.env_a)
    config_b = engine_config(args.engine_b, args.name_b, args.options_b, args.cwd_b, args.env_b)
    if args.openings:
        openings = load_openings(args.openings.resolve(strict=True))
    elif args.fen:
        board = chess.Board(args.fen)
        if not board.is_valid():
            parser.error("invalid start FEN")
        openings = [Opening("custom-fen", "Custom FEN", None, board.fen(), [], "command-line")]
    else:
        openings = [Opening("startpos", "Starting position", None, "startpos", [], "built-in")]
    if args.opening_id:
        openings = [opening for opening in openings if opening.identifier == args.opening_id]
    if args.opening_ids:
        identifiers = {value.strip() for value in args.opening_ids.split(",") if value.strip()}
        openings = [opening for opening in openings if opening.identifier in identifiers]
    if args.opening_name:
        query = args.opening_name.casefold()
        openings = [opening for opening in openings if query in opening.name.casefold()]
    if not openings:
        parser.error("opening filter selected no entries")
    if args.moves:
        for opening in openings:
            board = opening.initial_board()
            for move_name in opening.moves:
                board.push_uci(move_name)
            extra = normalize_moves(board.fen(), args.moves.split())
            opening.moves.extend(extra)
    if args.shuffle:
        random.Random(args.seed).shuffle(openings)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.output_dir / "engine.log"
    handler = logging.FileHandler(log_path, encoding="utf-8")
    logging.getLogger("chess.engine").addHandler(handler)
    logging.getLogger("chess.engine").setLevel(getattr(logging, args.engine_log_level))
    first = start_engine(config_a, args.timeout)
    try:
        second = start_engine(config_b, args.timeout)
    except Exception:
        first.process.close()
        raise
    games, records = [], []
    started = time.monotonic()
    try:
        for index in range(args.games):
            opening_index = index // 2 if args.color_mode == "paired" else index
            opening = openings[opening_index % len(openings)]
            game, record = play_game(first, second, opening, index, args)
            games.append(game)
            records.append(record)
            wins = sum(1 for item in records if item["result"] == ("1-0" if item["engine_a_color"] == "white" else "0-1"))
            draws = sum(1 for item in records if item["result"] == "1/2-1/2")
            losses = len(records) - wins - draws
            score = wins + 0.5 * draws
            print(f"[partida {index + 1}/{args.games}] {record['result']} | "
                  f"{opening.name} | W {wins} D {draws} L {losses} | "
                  f"score {score / len(records):.3f} | "
                  f"{time.monotonic() - started:.0f}s", flush=True)
    finally:
        for running in (first, second):
            try:
                running.process.quit()
            except (chess.engine.EngineTerminatedError, TimeoutError):
                running.process.close()
        handler.close()
        logging.getLogger("chess.engine").removeHandler(handler)
    pgn_path = args.output_dir / "games.pgn"
    with pgn_path.open("w", encoding="utf-8") as handle:
        exporter = chess.pgn.FileExporter(handle)
        for game in games:
            game.accept(exporter)
    sprt = ((args.sprt_elo0, args.sprt_elo1, args.sprt_alpha, args.sprt_beta)
            if args.sprt_elo0 is not None else None)
    metadata = {"schema_version": 1, "created_at": datetime.now(UTC).isoformat(),
                "git_commit": git_commit(root), "platform": platform.platform(), "seed": args.seed,
                "engines": {"a": {"path": str(config_a.path), "name": config_a.name,
                                      "id": first.identifier, "options": config_a.options,
                                      "cwd": str(config_a.cwd) if config_a.cwd else None,
                                      "environment_keys": sorted(config_a.environment)},
                            "b": {"path": str(config_b.path), "name": config_b.name,
                                      "id": second.identifier, "options": config_b.options,
                                      "cwd": str(config_b.cwd) if config_b.cwd else None,
                                      "environment_keys": sorted(config_b.environment)}},
                "conditions": {"games": args.games, "color_mode": args.color_mode,
                               "depth": args.depth, "nodes": args.nodes,
                               "movetime_ms": args.movetime_ms, "initial_ms": args.initial_ms,
                               "increment_ms": args.increment_ms, "moves_to_go": args.moves_to_go,
                               "max_plies": args.max_plies, "failure_policy": args.failure_policy},
                "statistics": statistics(records, sprt, args.color_mode == "paired"),
                "games": records,
                "artifacts": {"pgn": pgn_path.name, "log": log_path.name}}
    metadata_path = args.output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(json.dumps({"metadata": str(metadata_path), "pgn": str(pgn_path),
                      "statistics": metadata["statistics"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
