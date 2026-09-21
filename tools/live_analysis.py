"""Live PGN analysis: JSON-lines events out, focus/cancel commands in."""
from __future__ import annotations

import copy
import json
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import chess
import chess.engine
import chess.pgn

from analyze_pgn import classify, from_player_perspective, pv_data, static_evaluation, write_report
from explain_analysis import deterministic_explanation


def emit(event: str, **data: Any) -> None:
    print(json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)


def empty_evaluation() -> dict[str, Any]:
    return {"score": {"cp": None, "mate": None}, "san": None, "depth": 0, "pv_uci": [], "pv_san": []}


def candidate(board: chess.Board, info: dict[str, Any]) -> dict[str, Any]:
    result = pv_data(board, info, board.turn)
    line = board.copy()
    result["positions"] = [line.fen()]
    for name in result["pv_uci"]:
        line.push_uci(name)
        result["positions"].append(line.fen())
    return result


class Controls:
    def __init__(self, keys: set[tuple[int, int]]):
        self.lock = threading.Lock()
        self.keys = keys
        self.focus: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self.active: chess.engine.SimpleAnalysisResult | None = None
        self.cancelled = False
        self.revision = 0

    def listen(self) -> None:
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    continue
                with self.lock:
                    if command.get("command") == "cancel":
                        self.cancelled = True
                    elif command.get("command") == "focus":
                        key = (int(command["game"]), int(command["ply"]))
                        if key not in self.keys:
                            continue
                        self.focus = key
                        if key == self.current:
                            continue
                    else:
                        continue
                    self.revision += 1
                    if self.active is not None:
                        self.active.stop()
            except (ValueError, KeyError, TypeError):
                continue


class Interrupted(Exception):
    pass


def run_live(request: dict[str, Any], engine_path: Path, output: Path,
             games: list[chess.pgn.Game], position_only: bool) -> dict[str, Any]:
    depth, multipv, threads = (int(request.get(key, default)) for key, default in
                               (("depth", 4), ("multipv", 3), ("threads", 1)))
    if not 1 <= depth <= 126 or not 1 <= multipv <= 256 or not 1 <= threads <= 256:
        raise ValueError("Profundidad, variantes o hilos fuera de rango.")
    output.mkdir(parents=True, exist_ok=True)
    jobs: dict[tuple[int, int], dict[str, Any]] = {}
    results = []
    for game_index, game in enumerate(games):
        board = game.board()
        rows = []
        result = {"headers": dict(game.headers), "fen": board.fen(), "moves": rows}
        results.append(result)
        moves = list(game.mainline_moves())
        if position_only:
            if board.is_game_over(claim_draw=True):
                result["terminal"] = str(board.outcome(claim_draw=True))
                continue
            moves = [next(iter(board.legal_moves))]
        names: list[str] = []
        sans: list[str] = []
        for ply, move in enumerate(moves, 1):
            before = board.copy()
            san = board.san(move)
            row = {"ply": ply, "move_number": board.fullmove_number,
                   "initial_fen": game.board().fen(), "color": "white" if board.turn else "black",
                   "move_uci": move.uci(), "move_san": san, "fen_before": board.fen(),
                   "history_uci": list(names), "history_san": list(sans),
                   "classification": "pending", "centipawn_loss": None, "mate_note": None,
                   "best": empty_evaluation(), "played": empty_evaluation(), "candidates": [],
                   "mode": "position" if position_only else "game", "complete": False,
                   "stage": "pending", "explanation": "Pendiente de análisis.",
                   "static_before": None, "static_after": None, "static_best_after": None}
            board.push(move)
            row["fen_after"] = board.fen()
            if position_only:
                # The internal placeholder is not a recommendation until a PV arrives.
                row["move_uci"] = row["move_san"] = None
                row["fen_after"] = before.fen()
            rows.append(row)
            jobs[(game_index, ply)] = {"board": before, "move": move, "row": row}
            names.append(move.uci())
            sans.append(san)

    payload = {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(),
               "source": request["kind"], "complete": False,
               "engine": {"path": str(engine_path.resolve()), "multipv": multipv,
                          "options": {"OwnBook": False, "NNUE": False, "Threads": threads,
                                      "Hash": 256, "SearchProfile": "Optimized"},
                          "limit": {"depth": depth, "nodes": None, "movetime_ms": None}},
               "games": results}

    def save() -> None:
        temp = output / "analysis.json.tmp"
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(output / "analysis.json")

    save()
    emit("init", payload=payload)
    controls = Controls(set(jobs))
    # Open on the last move of the first game, matching the board shown by the UI.
    if results and results[0]["moves"]:
        controls.focus = (0, len(results[0]["moves"]))
    threading.Thread(target=controls.listen, daemon=True).start()
    cache: dict[str, Any] = {}
    pending = list(jobs)

    with chess.engine.SimpleEngine.popen_uci(str(engine_path.resolve(strict=True))) as engine:
        engine.configure(payload["engine"]["options"])
        while pending:
            with controls.lock:
                if controls.cancelled:
                    break
                selected = controls.focus
                controls.focus = None
                key = selected if selected in pending else pending[0]
                controls.current = key
                revision = controls.revision
            game_index, ply = key
            job = jobs[key]
            row, board = job["row"], job["board"]

            def publish(stage: str, row=row, game_index=game_index, ply=ply) -> None:
                row["stage"] = stage
                emit("record", game=game_index, ply=ply, record=row)

            def search(root_moves: list[chess.Move] | None = None, *, board=board, row=row,
                       job=job, game_index=game_index, ply=ply, revision=revision,
                       publish=publish) -> list[dict[str, Any]]:
                count = min(multipv, board.legal_moves.count()) if root_moves is None else 1
                stage = "variantes" if root_moves is None else "jugada realizada"
                emit("status", game=game_index, ply=ply, stage=stage)
                completed_depth = 0
                latest: list[dict[str, Any]] = []
                with engine.analysis(board, chess.engine.Limit(depth=depth), multipv=count,
                                     root_moves=root_moves, info=chess.engine.INFO_ALL) as analysis:
                    with controls.lock:
                        controls.active = analysis
                        if controls.revision != revision or controls.cancelled:
                            analysis.stop()
                    try:
                        for _ in analysis:
                            infos = analysis.multipv
                            if len(infos) != count or any("score" not in info or not info.get("pv") for info in infos):
                                continue
                            depths = [info.get("depth", 0) for info in infos]
                            if min(depths) != max(depths) or min(depths) <= completed_depth:
                                continue
                            completed_depth = min(depths)
                            latest = [candidate(board, info) for info in infos]
                            if root_moves is None:
                                row["candidates"] = latest
                                row["best"] = latest[0]
                                if position_only:
                                    job["move"] = chess.Move.from_uci(latest[0]["move"])
                                    row["move_uci"], row["move_san"] = latest[0]["move"], latest[0]["san"]
                                    row["fen_after"] = latest[0]["positions"][1]
                                row["played"] = next((value for value in latest if value["move"] == job["move"].uci()), empty_evaluation())
                            else:
                                row["played"] = latest[0]
                            row["classification"] = "provisional"
                            row["explanation"] = "Evaluación provisional; el motor sigue calculando."
                            publish(stage)
                    finally:
                        with controls.lock:
                            controls.active = None
                with controls.lock:
                    if controls.cancelled or controls.revision != revision:
                        raise Interrupted
                if not latest:
                    # Claimable draws may have a score but no PV from the engine.
                    if board.is_game_over(claim_draw=True):
                        latest = [candidate(board, {"score": chess.engine.PovScore(chess.engine.Cp(0), board.turn),
                                                     "pv": [job["move"]], "depth": 0})]
                    else:
                        raise ValueError("El motor terminó sin una variante completa.")
                return latest

            try:
                candidates = search()
                row["candidates"], row["best"] = candidates, candidates[0]
                row["played"] = next((value for value in candidates if value["move"] == job["move"].uci()), None)
                if row["played"] is None:
                    row["played"] = empty_evaluation()
                    row["played"] = search([job["move"]])[0]
                row["classification"], row["centipawn_loss"], row["mate_note"] = classify(
                    row["best"]["score"], row["played"]["score"], (50, 100, 200))
                row["static_before"] = from_player_perspective(static_evaluation(engine_path, board, True, None, cache), False)
                for name, move in (("static_after", job["move"]), ("static_best_after", chess.Move.from_uci(row["best"]["move"]))):
                    following = board.copy()
                    following.push(move)
                    row[name] = from_player_perspective(static_evaluation(engine_path, following, True, None, cache), True)
                row["complete"] = True
                row["explanation"] = deterministic_explanation(row, "", None)
                publish("complete")
                pending.remove(key)
                with controls.lock:
                    controls.keys.discard(key)
                save()
            except Interrupted:
                publish("paused")
                save()
        payload["complete"] = not pending
        save()
    # A partial report must not turn unknown evaluations into zeroes.
    report = copy.deepcopy(payload)
    for game in report["games"]:
        game["moves"] = [row for row in game["moves"] if row["complete"]]
    write_report(output / "report.md", report)
    if not position_only:
        with (output / "annotated.pgn").open("w", encoding="utf-8") as handle:
            for index, game in enumerate(games):
                annotated = copy.deepcopy(game)
                for node, row in zip(annotated.mainline(), results[index]["moves"], strict=True):
                    if row["complete"]:
                        node.set_eval(chess.engine.PovScore(
                            chess.engine.Mate(row["played"]["score"]["mate"]) if row["played"]["score"]["mate"] is not None
                            else chess.engine.Cp(row["played"]["score"]["cp"]), row["color"] == "white"))
                        node.comment += f" {row['classification']}; best {row['best']['san']}"
                annotated.accept(chess.pgn.FileExporter(handle))
    emit("done", complete=payload["complete"])
    return payload
