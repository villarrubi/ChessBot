"""Explain one move from a ChessBot analysis artifact, with an optional local LLM command."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import chess
import chess.engine

from local_explainer import explain as ollama_explanation


LABELS = {
    "best": "buena",
    "good": "aceptable",
    "inaccuracy": "imprecisión",
    "mistake": "error",
    "blunder": "error grave",
}


def score_text(score: dict[str, int | None]) -> str:
    if score["mate"] is not None:
        mate = score["mate"]
        unit = "movimiento" if abs(mate) == 1 else "movimientos"
        return "jaque mate en contra" if mate == 0 else f"mate {'a favor' if mate > 0 else 'en contra'} en {abs(mate)} {unit}"
    return f"{int(score['cp'] or 0) / 100:+.2f} peones"


def strongest_components(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[str]:
    if not before or not after:
        return []
    names = {
        "material": "material", "piece_square": "colocación", "mobility": "movilidad",
        "pawn_structure": "estructura de peones", "passed_pawns": "peones pasados",
        "bishop_pair": "pareja de alfiles", "rook_activity": "actividad de torres",
        "king_safety": "seguridad del rey", "space": "espacio", "tempo": "tempo",
    }
    changes = [(key, int(after.get(key, 0)) - int(before.get(key, 0))) for key in names]
    changes.sort(key=lambda item: abs(item[1]), reverse=True)
    return [f"{names[key]} {delta / 100:+.2f}" for key, delta in changes[:3] if delta]


def find_record(payload: dict[str, Any], game_index: int, ply: int) -> dict[str, Any]:
    games = payload.get("games", [])
    if game_index < 1 or game_index > len(games):
        raise ValueError("game index is outside the artifact")
    for record in games[game_index - 1].get("moves", []):
        if record.get("ply") == ply:
            return record
    raise ValueError("ply is outside the analyzed portion of the game")


def requested_uci(question: str) -> str | None:
    match = re.search(r"\b([a-h][1-8][a-h][1-8][qrbn]?)\b", question.lower())
    return match.group(1) if match else None


def analyze_missing_candidate(record: dict[str, Any], move_name: str, engine_path: Path,
                              depth: int, options: dict[str, Any] | None = None,
                              limit_data: dict[str, Any] | None = None) -> dict[str, Any]:
    board = chess.Board(record.get("initial_fen", record["fen_before"]))
    if "initial_fen" in record:
        for previous in record.get("history_uci", []):
            board.push_uci(previous)
    move = chess.Move.from_uci(move_name)
    if move not in board.legal_moves:
        raise ValueError(f"{move_name} is not legal in the selected position")
    engine = chess.engine.SimpleEngine.popen_uci(str(engine_path.resolve(strict=True)))
    try:
        if options:
            engine.configure({key: value for key, value in options.items() if key in engine.options})
        limits = limit_data or {}
        limit = chess.engine.Limit(depth=limits.get("depth"), nodes=limits.get("nodes"),
                                    time=limits["movetime_ms"] / 1000 if limits.get("movetime_ms") else None)
        if not any((limit.depth, limit.nodes, limit.time)):
            limit.depth = depth
        info = engine.analyse(board, limit, root_moves=[move],
                              info=chess.engine.INFO_ALL)
    finally:
        engine.quit()
    relative = info["score"].pov(board.turn)
    line_board = board.copy(stack=False)
    san = []
    for candidate in info.get("pv", []):
        san.append(line_board.san(candidate))
        line_board.push(candidate)
    return {"move": move_name, "san": board.san(move),
            "score": {"cp": relative.score(), "mate": relative.mate()},
            "depth": info.get("depth"), "nodes": info.get("nodes"), "pv_san": san,
            "source": "additional_search"}


def build_context(record: dict[str, Any], question: str, extra: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "mode": record.get("mode", "game"),
        "score_perspective": "player_before_move",
        "player": record.get("color"),
        "instruction": ("Answer only from the supplied engine evidence. Separate calculated facts "
                        "from interpretation. A principal variation alone does not prove forced play. "
                        "Never invent scores, variations or missing tactical evidence."),
        "question": question,
        "position": record["fen_before"],
        "history_uci": record.get("history_uci", []),
        "history_san": record.get("history_san", []),
        "played_move": record["played"],
        "best_move": record["best"],
        "candidates": record["candidates"],
        "additional_candidate": extra,
        "classification": record["classification"],
        "centipawn_loss": record["centipawn_loss"],
        "mate_note": record["mate_note"],
        "static_before": record["static_before"],
        "static_after": record["static_after"],
        "static_best_after": record.get("static_best_after"),
        "static_scope": "static_after describes ONLY played_move; static_best_after describes ONLY best_move",
        "verified_summary": deterministic_explanation(record, question, extra),
    }


def deterministic_explanation(record: dict[str, Any], question: str,
                              extra: dict[str, Any] | None) -> str:
    played, best = record["played"], record["best"]
    label = LABELS.get(record["classification"], record["classification"])
    loss = record["centipawn_loss"]
    loss_text = (record["mate_note"] or "la evaluación contiene una secuencia de mate") if loss is None else f"la pérdida es de {loss / 100:.2f} peones"
    lines = [f"La jugada {record['move_san']} se clasifica como {label}: {loss_text}.",
             f"La búsqueda valora la jugada en {score_text(played['score'])}; prefería "
             f"{best['san']} con {score_text(best['score'])}."]
    if record.get("mode") == "position":
        lines = [f"El motor recomienda {best['san']} con {score_text(best['score'])}."]
    color = "blancas" if record.get("color") == "white" else "negras"
    lines.append(f"Todas las puntuaciones se muestran desde la perspectiva de {color}.")
    if best.get("pv_san"):
        lines.append("La variante calculada para la mejor opción es: " + " ".join(best["pv_san"][:10]) + ".")
    if played.get("pv_san") and played["move"] != best["move"]:
        lines.append("La continuación calculada tras la jugada elegida es: " + " ".join(played["pv_san"][:10]) + ".")
    components = strongest_components(record.get("static_before"), record.get("static_after"))
    if components:
        lines.append("Tras la jugada, los mayores cambios estáticos para quien movió son: " +
                     ", ".join(components) + ".")
        lines.append("Son cambios de evaluación estática, no una demostración táctica ni un desglose de la búsqueda.")
    if record.get("static_before", {}) and record["static_before"].get("manual_auxiliary"):
        lines.append("Los componentes manuales son auxiliares: no descomponen la puntuación NNUE.")
    if extra:
        lines.append(f"La búsqueda adicional de {extra['san']} da {score_text(extra['score'])}; "
                     f"su variante es {' '.join(extra['pv_san'][:10])}.")
    if question:
        lines.append("Interpretación: esta respuesta se limita a las puntuaciones, componentes y variantes anteriores.")
    return "\n\n".join(lines)


def run_llm(command: str, context: dict[str, Any]) -> str:
    arguments = shlex.split(command, posix=os.name != "nt")
    result = subprocess.run(arguments, input=json.dumps(context, ensure_ascii=False), text=True,
                            capture_output=True, check=True, timeout=120)
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--game", type=int, default=1)
    parser.add_argument("--ply", type=int, required=True)
    parser.add_argument("--question", default="")
    parser.add_argument("--move", default="", help="explicit alternative in SAN or UCI")
    parser.add_argument("--provider", choices=["none", "auto", "ollama"], default="none")
    parser.add_argument("--model", default="")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--engine", type=Path,
                        help="run a new search when the question names a missing UCI move")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--llm-command",
                        help="optional local command that reads the evidence context as JSON on stdin")
    parser.add_argument("--context-output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.analysis.read_text(encoding="utf-8"))
    record = find_record(payload, args.game, args.ply)
    if args.depth < 1:
        parser.error("depth must be positive")
    named_move = requested_uci(args.question)
    if args.move:
        named_move = chess.Board(record["fen_before"]).parse_san(args.move).uci()
    known = {candidate["move"] for candidate in record["candidates"]}
    known.update({record["played"]["move"], record["best"]["move"]})
    extra = None
    if named_move and named_move not in known:
        if not args.engine:
            raise ValueError("the requested move lacks evidence; pass --engine to calculate it")
        extra = analyze_missing_candidate(record, named_move, args.engine, args.depth,
                                          payload.get("engine", {}).get("options"),
                                          payload.get("engine", {}).get("limit"))
    elif named_move:
        extra = next(candidate for candidate in [*record["candidates"], record["played"], record["best"]]
                     if candidate["move"] == named_move)
    context = build_context(record, args.question, extra)
    if args.context_output:
        args.context_output.parent.mkdir(parents=True, exist_ok=True)
        args.context_output.write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    answer = deterministic_explanation(record, args.question, extra)
    source, warning = "motor", None
    if args.llm_command:
        answer, source = run_llm(args.llm_command, context), "custom"
    elif args.provider != "none":
        try:
            answer, model = ollama_explanation(context, args.model)
            source = f"Ollama · {model}"
        except (OSError, ValueError, TimeoutError) as error:
            warning = f"IA local no disponible: {error}. Se muestra la explicación del motor."
            print(warning, file=sys.stderr)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps({"text": answer, "source": source, "warning": warning},
                                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(answer)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, chess.engine.EngineError, subprocess.SubprocessError) as error:
        print(f"No se pudo explicar la jugada: {error}", file=sys.stderr)
        raise SystemExit(1) from error
