"""End-to-end launcher analysis requests, including FEN and SAN alternatives."""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import chess

from analysis_session import run_session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", required=True, type=Path)
args = parser.parse_args()
engine = args.engine.resolve(strict=True)

with tempfile.TemporaryDirectory() as directory:
    output = Path(directory)
    payload = run_session({"kind": "game", "moves": ["e2e4", "e7e5"], "depth": 2}, engine, output)
    records = payload["games"][0]["moves"]
    assert len(records) == 2 and records[1]["color"] == "black"
    assert records[1]["history_uci"] == ["e2e4"]
    result_path = output / "explanation.json"
    subprocess.run([sys.executable, "-X", "utf8", str(Path(__file__).with_name("explain_analysis.py")),
                    "--analysis", str(output / "analysis.json"), "--ply", "2", "--move", "h5",
                    "--engine", str(engine), "--json-output", str(result_path)],
                   capture_output=True, check=True, text=True, encoding="utf-8")
    explanation = json.loads(result_path.read_text(encoding="utf-8"))
    assert "búsqueda adicional de h5" in explanation["text"]
    assert "negras" in explanation["text"]
    position = run_session({"kind": "fen", "text": chess.STARTING_FEN, "depth": 1}, engine, output)
    assert position["games"][0]["moves"][0]["mode"] == "position"
    assert "recomienda" in position["games"][0]["moves"][0]["explanation"]
    terminal = run_session({"kind": "fen", "text": "7k/6Q1/5K2/8/8/8/8/8 b - - 0 1", "depth": 1}, engine, output)
    assert terminal["games"][0]["moves"] == [] and terminal["games"][0]["terminal"]
    fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR b KQkq - 0 12"
    custom = run_session({"kind": "pgn", "text": f'[SetUp "1"]\n[FEN "{fen}"]\n\n12... e5 *', "depth": 1}, engine, output)
    assert custom["games"][0]["moves"][0]["move_number"] == 12

print("PASS: launcher PGN/FEN/history, terminal position, SAN alternative and score perspective")
