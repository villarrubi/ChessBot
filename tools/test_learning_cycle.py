"""Smoke-test a complete learning cycle and guarded rejection."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import torch

from train_nnue import loss_values


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
engine = args.engine.resolve(strict=True)

prediction = torch.tensor([0.0, 0.0])
outcomes = torch.tensor([0.5, 0.5])
teachers = torch.tensor([0.0, 800.0])
searched = torch.tensor([True, False])
_, mixed = loss_values(prediction, outcomes, teachers, searched, "mixed", 1.0)
_, search = loss_values(prediction, outcomes, teachers, searched, "search", 1.0)
assert mixed["teacher_loss"] == 0.75 and search["teacher_loss"] == 0.0

with tempfile.TemporaryDirectory(prefix="chessbot-cycle-") as directory:
    temporary = Path(directory)
    active = temporary / "active.nnue"
    active.write_text("preserve-active-network\n", encoding="utf-8")
    config = {
        "schema_version": 1,
        "id": "learning-cycle-test",
        "mode": "nnue",
        "engine": str(engine),
        "reference": "data/evaluation/hce-default-v1.params",
        "reference_kind": "hce",
        "source_pgns": [],
        "candidate_version": "learning-cycle-test-v1",
        "seed": 71,
        "budgets": {"selfplay_games": 4, "evaluation_games": 2, "max_seconds": 120,
                    "max_storage_mb": 20, "threads": 1},
        "selfplay": {"enabled": True, "depth": 1, "max_plies": 8,
                     "opponent_engine": str(engine), "opponent_name": "external-test"},
        "dataset": {"skip_plies": 0, "sample_every": 1, "max_per_game": 4,
                    "validation_fraction": 0.2},
        "training": {"hidden": 4, "epochs": 1, "batch_size": 128},
        "evaluation": {"depth": 1, "benchmark_depth": 1, "max_plies": 4,
                       "max_performance_regression": 10,
                       "minimum_lower_score": 0.999,
                       "minimum_independent_samples": 1},
        "promote_to": str(active),
    }
    config_path = temporary / "config.json"
    output = temporary / "output"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(root / "tools" / "learning_cycle.py"), "--config",
         str(config_path), "--engine", str(engine), "--output-dir", str(output)],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    decision = json.loads((output / "evaluation" / "decision.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete" and manifest["decision"] == "reject"
    assert [row["stage"] for row in manifest["commands"]] == [
        "games", "data", "training", "candidate_evaluation"]
    games_command = manifest["commands"][0]["command"]
    assert games_command[games_command.index("--engine-b") + 1] == str(engine)
    assert games_command[games_command.index("--cwd-b") + 1] == str(engine.parent)
    assert manifest["artifacts"] and all(row["sha256"] for row in manifest["artifacts"])
    assert decision["artifacts"]["promoted_to"] is None
    assert active.read_text(encoding="utf-8") == "preserve-active-network\n"

print("PASS: budgeted learning cycle, manifest, artifacts, rejection and active rollback")
