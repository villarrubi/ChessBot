"""Analyze PGN games with a UCI engine and export JSON, annotated PGN and Markdown."""
from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn


def score_data(score: chess.engine.PovScore, color: chess.Color) -> dict[str, int | None]:
    relative = score.pov(color)
    return {"cp": relative.score(), "mate": relative.mate()}


def numeric_score(score: dict[str, int | None]) -> int:
    mate = score["mate"]
    if mate is not None:
        return (100_000 - min(abs(mate), 999)) * (1 if mate > 0 else -1)
    return int(score["cp"] or 0)


def classify(best: dict[str, int | None], played: dict[str, int | None], thresholds: tuple[int, int,
                                                                                         int]) -> tuple[str, int | None, str | None]:
    best_mate, played_mate = best["mate"], played["mate"]
    if best_mate is not None or played_mate is not None:
        if (best_mate is not None and best_mate > 0 and
                (played_mate is None or played_mate <= 0)) or (played_mate is not None and
                                                               played_mate < 0):
            return "blunder", None, "se pierde una secuencia de mate o se permite mate"
        if best_mate is not None and played_mate is not None and best_mate > 0 and played_mate > 0:
            delta = max(0, played_mate - best_mate)
            return ("best" if delta == 0 else "inaccuracy"), None, f"mate retrasado {delta} plies"
        return "best", None, "resultado de mate conservado"
    loss = max(0, numeric_score(best) - numeric_score(played))
    if loss >= thresholds[2]:
        label = "blunder"
    elif loss >= thresholds[1]:
        label = "mistake"
    elif loss >= thresholds[0]:
        label = "inaccuracy"
    else:
        label = "best" if loss <= 10 else "good"
    return label, loss, None


def pv_data(board: chess.Board, info: dict[str, Any], color: chess.Color) -> dict[str, Any]:
    line_board = board.copy(stack=False)
    uci, san = [], []
    for move in info.get("pv", []):
        if move not in line_board.legal_moves:
            break
        uci.append(move.uci())
        san.append(line_board.san(move))
        line_board.push(move)
    return {
        "move": uci[0] if uci else None,
        "san": san[0] if san else None,
        "score": score_data(info["score"], color),
        "depth": info.get("depth"),
        "seldepth": info.get("seldepth"),
        "nodes": info.get("nodes"),
        "nps": info.get("nps"),
        "hashfull": info.get("hashfull"),
        "time_ms": round(info.get("time", 0) * 1000),
        "pv_uci": uci,
        "pv_san": san,
    }


def static_evaluation(engine: Path, board: chess.Board, enabled: bool,
                      cache: dict[str, dict[str, Any] | None]) -> dict[str, Any] | None:
    fen = board.fen()
    if fen in cache:
        return cache[fen]
    if not enabled:
        cache[fen] = None
        return None
    try:
        result = subprocess.run([str(engine), "eval", "--fen", fen], check=True,
                                capture_output=True, text=True, timeout=10)
        value = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        value = None
    cache[fen] = value
    return value


def from_player_perspective(value: dict[str, Any] | None, flip: bool) -> dict[str, Any] | None:
    if value is None:
        return None
    result = dict(value)
    if flip:
        for key, component in result.items():
            if key not in {"perspective", "phase"} and isinstance(component, int):
                result[key] = -component
    result["perspective"] = "player_before_move"
    return result


def analysis_limit(args: argparse.Namespace) -> chess.engine.Limit:
    if args.movetime_ms is not None:
        return chess.engine.Limit(time=args.movetime_ms / 1000)
    if args.nodes is not None:
        return chess.engine.Limit(nodes=args.nodes)
    return chess.engine.Limit(depth=args.depth)


def analyze_game(game: chess.pgn.Game, engine: chess.engine.SimpleEngine, engine_path: Path,
                 limit: chess.engine.Limit, multipv: int, thresholds: tuple[int, int, int],
                 max_plies: int | None, include_static: bool,
                 static_cache: dict[str, dict[str, Any] | None]) -> tuple[dict[str, Any], chess.pgn.Game]:
    board = game.board()
    annotated = chess.pgn.Game()
    annotated.setup(game.board())
    annotated.headers.update(game.headers)
    annotated.headers["Annotator"] = "ChessBot analyzer 0.6.0"
    annotated_node: chess.pgn.GameNode = annotated
    records = []
    history_uci: list[str] = []
    history_san: list[str] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        if max_plies is not None and ply > max_plies:
            break
        color = board.turn
        fen_before = board.fen()
        san = board.san(move)
        candidates_raw = engine.analyse(board, limit, multipv=multipv,
                                        info=chess.engine.INFO_ALL)
        if isinstance(candidates_raw, dict):
            candidates_raw = [candidates_raw]
        candidates = [pv_data(board, info, color) for info in candidates_raw]
        played_raw = engine.analyse(board, limit, root_moves=[move], info=chess.engine.INFO_ALL)
        played = pv_data(board, played_raw, color)
        best = candidates[0]
        classification, loss, mate_note = classify(best["score"], played["score"], thresholds)
        static_before = static_evaluation(engine_path, board, include_static, static_cache)
        board.push(move)
        static_after_raw = static_evaluation(engine_path, board, include_static, static_cache)
        static_after = from_player_perspective(static_after_raw, flip=True)
        record = {
            "ply": ply,
            "move_number": (ply + 1) // 2,
            "color": "white" if color == chess.WHITE else "black",
            "move_uci": move.uci(),
            "move_san": san,
            "fen_before": fen_before,
            "fen_after": board.fen(),
            "history_uci": list(history_uci),
            "history_san": list(history_san),
            "classification": classification,
            "centipawn_loss": loss,
            "mate_note": mate_note,
            "best": best,
            "played": played,
            "candidates": candidates,
            "static_before": from_player_perspective(static_before, flip=False),
            "static_after": static_after,
        }
        records.append(record)
        history_uci.append(move.uci())
        history_san.append(san)
        annotated_node = annotated_node.add_variation(move)
        score_text = (f"mate {played['score']['mate']}" if played["score"]["mate"] is not None
                      else f"{int(played['score']['cp'] or 0) / 100:+.2f}")
        loss_text = "mate" if loss is None else f"-{loss / 100:.2f}"
        annotated_node.comment = (f"{classification}; eval {score_text}; loss {loss_text}; "
                                  f"best {best['san']}; PV {' '.join(best['pv_san'][:8])}")
    return {"headers": dict(game.headers), "moves": records}, annotated


def write_report(path: Path, payload: dict[str, Any]) -> None:
    lines = ["# ChessBot PGN analysis", "",
             f"Generated: {payload['generated_at']}", "",
             f"Engine: `{payload['engine']['path']}`", ""]
    for game_index, game in enumerate(payload["games"], start=1):
        headers = game["headers"]
        lines.extend([f"## Game {game_index}: {headers.get('White', '?')} – {headers.get('Black', '?')}",
                      "", "| Ply | Move | Classification | Loss | Score | Best |", "| ---: | --- | --- | ---: | ---: | --- |"])
        for move in game["moves"]:
            score = move["played"]["score"]
            score_text = f"M{score['mate']}" if score["mate"] is not None else f"{(score['cp'] or 0) / 100:+.2f}"
            loss = "mate" if move["centipawn_loss"] is None else f"{move['centipawn_loss'] / 100:.2f}"
            lines.append(f"| {move['ply']} | {move['move_san']} | {move['classification']} | {loss} | {score_text} | {move['best']['san']} |")
        lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument("--depth", type=int)
    limits.add_argument("--movetime-ms", type=int)
    limits.add_argument("--nodes", type=int)
    parser.add_argument("--multipv", type=int, default=3)
    parser.add_argument("--max-plies", type=int)
    parser.add_argument("--inaccuracy", type=int, default=50)
    parser.add_argument("--mistake", type=int, default=100)
    parser.add_argument("--blunder", type=int, default=200)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--annotated-pgn", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--no-static", action="store_true",
                        help="skip the ChessBot diagnostic eval command for external engines")
    args = parser.parse_args()
    if args.depth is None and args.movetime_ms is None and args.nodes is None:
        args.depth = 4
    if args.multipv < 1 or args.multipv > 10:
        parser.error("multipv must be between 1 and 10")
    if args.depth is not None and args.depth < 1 or args.movetime_ms is not None and args.movetime_ms < 1 or args.nodes is not None and args.nodes < 1:
        parser.error("search limits must be positive")
    thresholds = (args.inaccuracy, args.mistake, args.blunder)
    if not (0 <= thresholds[0] <= thresholds[1] <= thresholds[2]):
        parser.error("classification thresholds must be ordered and nonnegative")
    engine_path = args.engine.resolve(strict=True)
    input_path = args.input.resolve(strict=True)
    games = []
    with input_path.open(encoding="utf-8") as handle:
        while game := chess.pgn.read_game(handle):
            if game.errors:
                raise ValueError(f"invalid PGN: {game.errors}")
            games.append(game)
    if not games:
        parser.error("input contains no PGN games")
    for path in (args.json, args.annotated_pgn, args.report):
        path.parent.mkdir(parents=True, exist_ok=True)
    engine = chess.engine.SimpleEngine.popen_uci(str(engine_path))
    results, annotated_games = [], []
    cache: dict[str, dict[str, Any] | None] = {}
    try:
        for game in games:
            result, annotated = analyze_game(game, engine, engine_path, analysis_limit(args),
                                             args.multipv, thresholds, args.max_plies,
                                             not args.no_static, cache)
            results.append(result)
            annotated_games.append(annotated)
    finally:
        engine.quit()
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": str(input_path),
        "engine": {"path": str(engine_path), "multipv": args.multipv,
                   "limit": {"depth": args.depth, "movetime_ms": args.movetime_ms,
                             "nodes": args.nodes}},
        "thresholds_cp": {"inaccuracy": thresholds[0], "mistake": thresholds[1],
                          "blunder": thresholds[2]},
        "games": results,
    }
    args.json.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with args.annotated_pgn.open("w", encoding="utf-8") as handle:
        exporter = chess.pgn.FileExporter(handle)
        for game in annotated_games:
            game.accept(exporter)
    write_report(args.report, payload)
    print(json.dumps({"games": len(results), "moves": sum(len(g["moves"]) for g in results),
                      "json": str(args.json), "annotated_pgn": str(args.annotated_pgn),
                      "report": str(args.report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
