"""End-to-end smoke test for PGN analysis and evidence-bound explanations."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import chess.pgn


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
engine = args.engine.resolve(strict=True)

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    analysis = output / "analysis.json"
    annotated = output / "annotated.pgn"
    report = output / "report.md"
    subprocess.run([
        str(root / ".venv" / "Scripts" / "python.exe") if (root / ".venv" / "Scripts" /
                                                               "python.exe").exists() else "python",
        str(root / "tools" / "analyze_pgn.py"), "--input",
        str(root / "tests" / "positions" / "analysis_sample.pgn"), "--engine", str(engine),
        "--depth", "2", "--multipv", "2", "--max-plies", "3", "--json", str(analysis),
        "--annotated-pgn", str(annotated), "--report", str(report),
    ], check=True, capture_output=True, text=True)
    payload = json.loads(analysis.read_text(encoding="utf-8"))
    moves = payload["games"][0]["moves"]
    assert payload["schema_version"] == 1 and len(moves) == 3
    assert all(len(move["candidates"]) == 2 for move in moves)
    assert all(move["played"]["move"] == move["move_uci"] for move in moves)
    assert all(move["static_before"] and move["static_after"] for move in moves)
    with annotated.open(encoding="utf-8") as handle:
        game = chess.pgn.read_game(handle)
    assert game and not game.errors and all(node.comment for node in game.mainline())
    assert "| Ply |" in report.read_text(encoding="utf-8")
    context = output / "context.json"
    explanation = subprocess.run([
        str(root / ".venv" / "Scripts" / "python.exe") if (root / ".venv" / "Scripts" /
                                                               "python.exe").exists() else "python",
        str(root / "tools" / "explain_analysis.py"), "--analysis", str(analysis), "--ply", "1",
        "--question", "¿Qué cambia con h2h4?", "--engine", str(engine), "--depth", "2",
        "--context-output", str(context),
    ], check=True, capture_output=True, text=True)
    assert "búsqueda adicional" in explanation.stdout
    assert json.loads(context.read_text(encoding="utf-8"))["additional_candidate"]["move"] == "h2h4"

print("PASS: PGN analysis, JSON, annotated PGN, report and evidence-bound explanation")
