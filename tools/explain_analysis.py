"""Explain one move from a ChessBot analysis artifact, with an optional local LLM command."""
from __future__ import annotations

import argparse
import copy
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

from analyze_pgn import classify, from_player_perspective, numeric_score, pv_data, static_evaluation
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


MOVE_TOKEN = re.compile(
    r"(?<!\w)(?:[a-h][1-8][a-h][1-8][qrbn]?|O-O(?:-O)?|"
    r"[KQRBN](?:[a-h1-8])?x?[a-h][1-8](?:=[QRBN])?[+#]?|"
    r"[a-h](?:x[a-h])?[1-8](?:=[QRBN])?[+#]?)(?!\w)"
)


def record_board(record: dict[str, Any]) -> chess.Board:
    board = chess.Board(record.get("initial_fen", record["fen_before"]))
    if "initial_fen" in record:
        for previous in record.get("history_uci", []):
            board.push_uci(previous)
    return board


def parse_move(board: chess.Board, name: str) -> chess.Move:
    normalized = name.strip().replace("0", "O")
    try:
        if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", normalized.lower()):
            move = chess.Move.from_uci(normalized.lower())
        else:
            move = board.parse_san(normalized)
    except ValueError as error:
        raise ValueError(f"{name} no es una jugada SAN o UCI válida en la posición seleccionada") from error
    if move not in board.legal_moves:
        raise ValueError(f"{name} no es legal en la posición seleccionada")
    return move


def proposed_uci(record: dict[str, Any], explicit: str, question: str) -> list[str]:
    board = record_board(record)
    result: list[str] = []

    def add(move: chess.Move) -> None:
        name = move.uci()
        if name not in result:
            result.append(name)

    for token in re.split(r"[,;/\s]+", explicit.strip()):
        if token and token.lower() not in {"o", "or", "vs", "contra"}:
            add(parse_move(board, token))
    for match in MOVE_TOKEN.finditer(question):
        try:
            add(parse_move(board, match.group()))
        except ValueError:
            # Natural-language text can resemble SAN; only the explicit field
            # reports invalid tokens to the user.
            continue
    if len(result) > 4:
        raise ValueError("Se pueden comparar como máximo cuatro jugadas propuestas a la vez")
    return result


def analyze_missing_candidates(record: dict[str, Any], move_names: list[str], engine_path: Path,
                               depth: int, options: dict[str, Any] | None = None,
                               limit_data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not move_names:
        return []
    board = record_board(record)
    moves = [parse_move(board, name) for name in move_names]
    engine = chess.engine.SimpleEngine.popen_uci(str(engine_path.resolve(strict=True)))
    try:
        if options:
            engine.configure({key: value for key, value in options.items() if key in engine.options})
        limits = limit_data or {}
        limit = chess.engine.Limit(depth=limits.get("depth"), nodes=limits.get("nodes"),
                                    time=limits["movetime_ms"] / 1000 if limits.get("movetime_ms") else None)
        if not any((limit.depth, limit.nodes, limit.time)):
            limit.depth = depth
        response = engine.analyse(board, limit, root_moves=moves, multipv=len(moves),
                                  info=chess.engine.INFO_ALL)
    finally:
        engine.quit()
    infos = response if isinstance(response, list) else [response]
    found = {value["move"]: value for info in infos
             if (value := pv_data(board, info, board.turn))["move"]}
    missing = [name for name in move_names if name not in found]
    if missing:
        raise ValueError("El motor no devolvió una variante para: " + ", ".join(missing))
    cache: dict[str, dict[str, Any] | None] = {}
    for name in move_names:
        found[name]["source"] = "additional_search"
        found[name]["static_after"] = None
        if options and "SearchProfile" in options:
            following = board.copy()
            following.push_uci(name)
            value = static_evaluation(engine_path, following, True, None, cache)
            found[name]["static_after"] = from_player_perspective(value, True)
    return [found[name] for name in move_names]


def candidate_evidence(record: dict[str, Any], candidate: dict[str, Any],
                       reference: dict[str, Any] | None = None) -> dict[str, Any]:
    result = copy.deepcopy(candidate)
    best = reference or record["best"]
    label, loss, mate_note = classify(best["score"], result["score"], (50, 100, 200))
    board = record_board(record)
    move = chess.Move.from_uci(result["move"])
    moving = board.piece_at(move.from_square)
    captured = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, not board.turn)
    piece_names = {chess.PAWN: "peón", chess.KNIGHT: "caballo", chess.BISHOP: "alfil",
                   chess.ROOK: "torre", chess.QUEEN: "dama", chess.KING: "rey"}
    move_facts = {
        "moving_piece": piece_names[moving.piece_type] if moving else None,
        "capture": captured is not None,
        "captured_piece": piece_names[captured.piece_type] if captured else None,
        "gives_check": board.gives_check(move),
        "promotion": piece_names.get(move.promotion),
    }
    board.push(move)
    if result["move"] == record["played"]["move"]:
        result.setdefault("static_after", record.get("static_after"))
    elif result["move"] == best["move"]:
        result.setdefault("static_after", record.get("static_best_after"))
    line = result.get("pv_san", [])
    line_board = record_board(record)
    line_facts = []
    for name in result.get("pv_uci", [])[:14]:
        line_move = chess.Move.from_uci(name)
        if line_move not in line_board.legal_moves:
            break
        line_piece = line_board.piece_at(line_move.from_square)
        line_captured = line_board.piece_at(line_move.to_square)
        if line_board.is_en_passant(line_move):
            line_captured = chess.Piece(chess.PAWN, not line_board.turn)
        line_facts.append({
            "bando": "blancas" if line_board.turn else "negras",
            "san": line_board.san(line_move),
            "pieza": piece_names[line_piece.piece_type] if line_piece else None,
            "captura": piece_names[line_captured.piece_type] if line_captured else None,
            "jaque": line_board.gives_check(line_move),
        })
        line_board.push(line_move)
    result.update({
        "comparison_to_best": {"reference_move": best["move"], "reference_san": best["san"],
                               "reference_score": best["score"], "classification": label,
                               "centipawn_loss": loss, "mate_note": mate_note},
        "move_facts": move_facts,
        "fen_after": board.fen(),
        "plan_evidence": {
            "principal_variation": line[:14],
            "moves_by_proposing_side": line[:14:2],
            "opponent_responses": line[1:14:2],
            "checks": [move for move in line[:14] if "+" in move or "#" in move],
            "captures": [move for move in line[:14] if "x" in move],
            "detailed_sequence": line_facts,
        },
    })
    return result


def position_evidence(record: dict[str, Any]) -> dict[str, Any]:
    board = record_board(record)
    names = {chess.PAWN: "pawns", chess.KNIGHT: "knights", chess.BISHOP: "bishops",
             chess.ROOK: "rooks", chess.QUEEN: "queens", chess.KING: "king"}
    pieces = {}
    for color, color_name in ((chess.WHITE, "white"), (chess.BLACK, "black")):
        pieces[color_name] = {names[piece]: [chess.square_name(square)
                                             for square in board.pieces(piece, color)]
                              for piece in names}
    return {"fen": board.fen(), "side_to_move": "white" if board.turn else "black",
            "in_check": board.is_check(), "castling_rights": board.castling_xfen(),
            "pieces": pieces}


def normalize_candidates(extra: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if extra is None:
        return []
    return [extra] if isinstance(extra, dict) else extra


def build_context(record: dict[str, Any], question: str,
                  extra: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
    proposed = normalize_candidates(extra)
    player = "blancas" if record.get("color") == "white" else "negras"
    opponent = "negras" if player == "blancas" else "blancas"
    return {
        "mode": record.get("mode", "game"),
        "score_perspective": "player_before_move",
        "player": record.get("color"),
        "player_spanish": player,
        "opponent_spanish": opponent,
        "instruction": ("Evaluate every entry in proposed_moves explicitly. Separate calculated facts "
                        "from positional interpretation. Explain candidate idea, drawback, likely plan "
                        "for each side and practical warning, tying every claim to position_features, "
                        "static components or plan_evidence. A principal variation alone does not prove "
                        "forced play. Never invent scores, variations or missing tactical evidence."),
        "question": question,
        "position": record["fen_before"],
        "position_features": position_evidence(record),
        "history_uci": record.get("history_uci", []),
        "history_san": record.get("history_san", []),
        "played_move": record["played"],
        "best_move": record["best"],
        "selected_focus": candidate_evidence(record, record["played"]),
        "best_focus": candidate_evidence(record, record["best"]),
        "candidates": record["candidates"],
        "additional_candidate": proposed[0] if proposed else None,
        "additional_candidates": proposed,
        "proposed_moves": proposed,
        "classification": record["classification"],
        "centipawn_loss": record["centipawn_loss"],
        "mate_note": record["mate_note"],
        "static_before": record["static_before"],
        "static_after": record["static_after"],
        "static_best_after": record.get("static_best_after"),
        "static_scope": "static_after describes ONLY played_move; static_best_after describes ONLY best_move",
        "response_requirements": [
            "Give a direct verdict for every proposed move, including score, difference from best and PV.",
            "Explain the purpose and downside of each move only when supported by the evidence.",
            "Give a conditional plan for the proposing side and a counter-plan for the opponent.",
            "Distinguish engine facts from interpretation and say when evidence is insufficient.",
        ],
        "verified_summary": deterministic_explanation(record, question, proposed),
    }


def deterministic_explanation(record: dict[str, Any], question: str,
                              extra: dict[str, Any] | list[dict[str, Any]] | None) -> str:
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
    for candidate in normalize_candidates(extra):
        comparison = candidate.get("comparison_to_best", {})
        loss = comparison.get("centipawn_loss")
        if candidate["move"] == comparison.get("reference_move"):
            difference = "mejor resultado de la comparación conjunta"
        elif loss is None:
            difference = comparison.get("mate_note") or "comparación de mate"
        else:
            reference_score = score_text(comparison["reference_score"])
            difference = (f"{loss / 100:.2f} peones peor que "
                          f"{comparison.get('reference_san', 'la mejor propuesta')} "
                          f"({reference_score} en la misma búsqueda)")
        source = "búsqueda adicional" if candidate.get("source") == "additional_search" else "variante ya calculada"
        verdict = LABELS.get(comparison.get("classification"), comparison.get("classification", "sin clasificar"))
        facts = candidate.get("move_facts", {})
        captured_piece = facts.get("captured_piece")
        article = "una" if captured_piece in {"dama", "torre"} else "un"
        action = (f"captura {article} {captured_piece}" if facts.get("capture")
                  else "no realiza una captura")
        if facts.get("gives_check"):
            action += " y da jaque"
        lines.append(f"La {source} de {candidate['san']} da {score_text(candidate['score'])} "
                     f"({difference}) y se clasifica como {verdict}. La jugada {action}; su variante es "
                     f"{' '.join(candidate.get('pv_san', [])[:12])}.")
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
    parser.add_argument("--move", "--moves", dest="moves", default="",
                        help="one to four alternatives in SAN or UCI, separated by commas")
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
    requested = proposed_uci(record, args.moves, args.question)
    available = {candidate["move"]: candidate for candidate in
                 [*record["candidates"], record["played"], record["best"]]
                 if candidate.get("move")}
    reference = record["best"]
    if requested and args.engine:
        comparison_moves = list(requested)
        if record["best"]["move"] not in comparison_moves:
            comparison_moves.append(record["best"]["move"])
        calculated = analyze_missing_candidates(record, comparison_moves, args.engine, args.depth,
                                                payload.get("engine", {}).get("options"),
                                                payload.get("engine", {}).get("limit"))
        available.update({candidate["move"]: candidate for candidate in calculated})
        reference = max(calculated, key=lambda candidate: numeric_score(candidate["score"]))
    else:
        missing = [name for name in requested if name not in available]
        if missing:
            raise ValueError("las jugadas propuestas carecen de evaluación; pasa --engine para calcularlas")
    proposed = [candidate_evidence(record, available[name], reference) for name in requested]
    context = build_context(record, args.question, proposed)
    if args.context_output:
        args.context_output.parent.mkdir(parents=True, exist_ok=True)
        args.context_output.write_text(json.dumps(context, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    verified = deterministic_explanation(record, args.question, proposed)
    answer = verified
    source, warning = "motor", None
    if args.llm_command:
        answer, source = run_llm(args.llm_command, context), "custom"
    elif args.provider != "none":
        try:
            interpretation, model = ollama_explanation(context, args.model)
            answer = verified + "\n\n" + interpretation
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
