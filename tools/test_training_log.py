"""Tests for durable training history and crash recovery."""
import json
import os
import tempfile
from pathlib import Path

from training_log import TrainingLogger, recover_stale_runs, runs


with tempfile.TemporaryDirectory(prefix="chessbot-training-log-") as directory:
    path = Path(directory) / "history.jsonl"
    logger = TrainingLogger("nnue", Path(directory) / "run", path=path)
    logger.start()
    logger.progress("training", {"epoch": 3, "epochs": 10})
    logger.finish("completed", details={"selected_epoch": 3})
    assert runs(path)[0]["status"] == "completed"
    assert runs(path)[0]["progress"] == {"epoch": 3, "epochs": 10}

    stale_id = "stale-run"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"schema_version": 1, "event": "start",
                                 "run_id": stale_id, "kind": "cycle", "pid": os.getpid() + 1000000,
                                 "timestamp": "2026-01-01T00:00:00+00:00"}) + "\n")
        handle.write('{"partial":')
    assert recover_stale_runs(path) == [stale_id]
    assert runs(path)[-1]["status"] == "interrupted"

print("PASS: durable training history, progress and stale-run recovery")
