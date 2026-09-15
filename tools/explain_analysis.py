"""Explain one move from a ChessBot analysis artifact, with an optional local LLM command."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

import chess
import chess.engine


LABELS = {
    "best": "buena",
    "good": "aceptable",
    "inaccuracy": "imprecisión",
    "mistake": "error",
    "blunder": "error grave",
}


def score_text(score: dict[str, int | None]) -> str:
    if score["mate"] is not None:
        return f"mate en {score['mate']}"
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
                              depth: int) -> dict[str, Any]:
    board = chess.Board(record["fen_before"])
    move = chess.Move.from_uci(move_name)
    if move not in board.legal_moves:
        raise ValueError(f"{move_name} is not legal in the selected position")
    engine = chess.engine.SimpleEngine.popen_uci(str(engine_path.resolve(strict=True)))
    try:
        info = engine.analyse(board, chess.engine.Limit(depth=depth), root_moves=[move],
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
        "instruction": ("Answer only from the supplied engine evidence. Separate calculated facts "
                        "from interpretation and do not claim a forced tactic unless a mate score or "
                        "principal variation demonstrates it."),
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
    if best.get("pv_san"):
        lines.append("La variante calculada para la mejor opción es: " + " ".join(best["pv_san"][:10]) + ".")
    components = strongest_components(record.get("static_before"), record.get("static_after"))
    if components:
        lines.append("Tras la jugada, los mayores cambios estáticos para quien movió son: " +
                     ", ".join(components) + ".")
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
    parser.add_argument("--engine", type=Path,
                        help="run a new search when the question names a missing UCI move")
    parser.add_argument("--depth", type=int, default=4)
    parser.add_argument("--llm-command",
                        help="optional local command that reads the evidence context as JSON on stdin")
    parser.add_argument("--context-output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.analysis.read_text(encoding="utf-8"))
    record = find_record(payload, args.game, args.ply)
    named_move = requested_uci(args.question)
    known = {candidate["move"] for candidate in record["candidates"]}
    known.update({record["played"]["move"], record["best"]["move"]})
    extra = None
    if named_move and named_move not in known:
        if not args.engine:
            raise ValueError("the requested move lacks evidence; pass --engine to calculate it")
        extra = analyze_missing_candidate(record, named_move, args.engine, args.depth)
    context = build_context(record, args.question, extra)
    if args.context_output:
        args.context_output.parent.mkdir(parents=True, exist_ok=True)
        args.context_output.write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    print(run_llm(args.llm_command, context) if args.llm_command else
          deterministic_explanation(record, args.question, extra))


if __name__ == "__main__":
    main()
