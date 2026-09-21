"""Analyze a launcher request (PGN, FEN or a live game's UCI history)."""
from __future__ import annotations

import argparse
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

from analyze_pgn import analyze_game, write_report
from explain_analysis import deterministic_explanation


def read_games(request: dict[str, Any]) -> tuple[list[chess.pgn.Game], bool]:
    kind = request.get("kind")
    if kind == "pgn":
        stream = io.StringIO(request.get("text", ""))
        games = []
        while game := chess.pgn.read_game(stream):
            if game.errors:
                raise ValueError(f"PGN inválido: {game.errors[0]}")
            if not game.board().is_valid():
                raise ValueError("La posición inicial del PGN no es válida.")
            games.append(game)
        if not games:
            raise ValueError("Introduce un PGN con al menos una partida.")
        return games, False
    if kind not in {"fen", "game"}:
        raise ValueError("Tipo de análisis desconocido.")
    board = chess.Board(request.get("text", "") if kind == "fen" else chess.STARTING_FEN)
    if not board.is_valid():
        raise ValueError("La FEN no representa una posición válida.")
    game = chess.pgn.Game()
    game.setup(board)
    node: chess.pgn.GameNode = game
    for name in request.get("moves", []) if kind == "game" else []:
        move = board.parse_uci(name)
        node = node.add_variation(move)
        board.push(move)
    return [game], kind == "fen" or not game.variations


def run_session(request: dict[str, Any], engine_path: Path, output: Path) -> dict[str, Any]:
    games, position_only = read_games(request)
    depth, multipv = int(request.get("depth", 4)), int(request.get("multipv", 3))
    if not 1 <= depth <= 12 or not 1 <= multipv <= 10:
        raise ValueError("Profundidad (1–12) o alternativas (1–10) fuera de rango.")
    output.mkdir(parents=True, exist_ok=True)
    results, annotated_games = [], []
    cache: dict[str, Any] = {}
    with chess.engine.SimpleEngine.popen_uci(str(engine_path.resolve(strict=True))) as engine:
        engine.configure({"OwnBook": False, "NNUE": False})
        for index, game in enumerate(games, 1):
            print(f"Analizando partida {index}/{len(games)}…", flush=True)
            board = game.board()
            if position_only:
                if board.is_game_over(claim_draw=True):
                    results.append({"headers": dict(game.headers), "moves": [],
                                    "fen": board.fen(), "terminal": str(board.outcome(claim_draw=True))})
                    continue
                info = engine.analyse(board, chess.engine.Limit(depth=depth))
                game.add_variation(info["pv"][0])
            result, annotated = analyze_game(game, engine, engine_path,
                                             chess.engine.Limit(depth=depth), multipv,
                                             (50, 100, 200), None, True, cache, None,
                                             progress=lambda ply, index=index: print(f"Analizando partida {index}/{len(games)} · jugada {ply}…", flush=True))
            result["fen"] = game.board().fen()
            for record in result["moves"]:
                record["mode"] = "position" if position_only else "game"
                record["explanation"] = deterministic_explanation(record, "", None)
            results.append(result)
            if not position_only:
                annotated_games.append(annotated)
    payload = {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(),
               "source": request["kind"], "engine": {"path": str(engine_path.resolve()),
               "options": {"OwnBook": False, "NNUE": False}, "multipv": multipv,
               "limit": {"depth": depth, "nodes": None, "movetime_ms": None}},
               "games": results}
    (output / "analysis.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(output / "report.md", payload)
    if annotated_games:
        with (output / "annotated.pgn").open("w", encoding="utf-8") as handle:
            for game in annotated_games:
                game.accept(chess.pgn.FileExporter(handle))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        run_session(json.loads(args.request.read_text(encoding="utf-8-sig")), args.engine, args.output_dir)
    except (ValueError, OSError, chess.engine.EngineError) as error:
        parser.exit(1, f"No se pudo analizar: {error}\n")
    print("Análisis completo.", flush=True)


if __name__ == "__main__":
    main()
