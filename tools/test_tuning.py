"""Exercise dataset generation, tuning artifacts, engine loading, and safe rejection."""
import argparse
import csv
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import chess
import chess.pgn


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
engine = args.engine.resolve(strict=True)


def make_games(path: Path) -> None:
    randomizer = random.Random(17)
    with path.open("w", encoding="utf-8") as handle:
        exporter = chess.pgn.FileExporter(handle)
        for index in range(8):
            game = chess.pgn.Game()
            game.headers.update({"Event": f"Dataset source {index // 2}", "Round": str(index + 1),
                                 "Result": ("1-0", "0-1", "1/2-1/2")[index % 3]})
            board = game.board()
            node = game
            for _ in range(20 + index):
                if board.is_game_over():
                    break
                moves = list(board.legal_moves)
                move = moves[randomizer.randrange(len(moves))]
                node = node.add_variation(move)
                board.push(move)
            game.accept(exporter)


with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)
    pgn = temporary / "training.pgn"
    dataset = temporary / "dataset.csv"
    tuning = temporary / "tuning"
    decision = temporary / "decision"
    active = temporary / "active.params"
    make_games(pgn)
    subprocess.run([sys.executable, str(root / "tools" / "generate_dataset.py"), "--pgn",
                    str(pgn), "--engine", str(engine), "--output", str(dataset), "--skip-plies",
                    "2", "--sample-every", "2", "--max-per-game", "8",
                    "--validation-fraction", "0.25"], check=True, capture_output=True, text=True)
    with dataset.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and {row["split"] for row in rows} == {"train", "validation"}
    assert len({row["zobrist"] for row in rows}) == len(rows)
    train_games = {row["game_id"] for row in rows if row["split"] == "train"}
    validation_games = {row["game_id"] for row in rows if row["split"] == "validation"}
    assert train_games.isdisjoint(validation_games)
    schema = json.loads((temporary / "dataset.csv.schema.json").read_text(encoding="utf-8"))
    assert schema["schema_version"] == 1 and schema["perspective"] == "side_to_move"

    subprocess.run([sys.executable, str(root / "tools" / "tune_eval.py"), "--dataset",
                    str(dataset), "--output-dir", str(tuning), "--reference",
                    str(root / "data" / "evaluation" / "hce-default-v1.params"), "--iterations",
                    "80", "--version", "test-candidate-v1"], check=True, capture_output=True,
                   text=True)
    report = json.loads((tuning / "tuning.json").read_text(encoding="utf-8"))
    assert report["candidate"]["parameters"].endswith("candidate.params")
    candidate_text = (tuning / "candidate.params").read_text(encoding="utf-8")
    assert "version=test-candidate-v1" in candidate_text
    evaluated = subprocess.run([str(engine), "features-stream", "--eval-file",
                                str(tuning / "candidate.params")], input=chess.STARTING_FEN + "\n",
                               check=True, capture_output=True, text=True)
    assert json.loads(evaluated.stdout)["evaluation_version"] == "test-candidate-v1"

    active.write_text("do-not-replace\n", encoding="utf-8")
    subprocess.run([sys.executable, str(root / "tools" / "evaluate_candidate.py"), "--engine",
                    str(engine), "--candidate", str(tuning / "candidate.params"), "--reference",
                    str(tuning / "reference.params"), "--tuning-report",
                    str(tuning / "tuning.json"), "--openings",
                    str(root / "data" / "openings" / "core.json"), "--output-dir", str(decision),
                    "--games", "2", "--depth", "1", "--benchmark-depth", "1", "--max-plies",
                    "4", "--max-performance-regression", "10", "--minimum-lower-score", "0.999",
                    "--promote-to", str(active)], check=True, capture_output=True, text=True)
    outcome = json.loads((decision / "decision.json").read_text(encoding="utf-8"))
    assert outcome["decision"] == "reject"
    assert active.read_text(encoding="utf-8") == "do-not-replace\n"
    assert (decision / "candidate.params").exists() and (decision / "reference.params").exists()

print("PASS: dataset schema/splits, tuning, candidate loading and guarded promotion")
