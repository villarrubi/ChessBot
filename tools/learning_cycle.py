"""Run a budgeted games-to-candidate learning cycle with reproducible artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from queue import Empty, Queue
from threading import Thread
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def git_value(*arguments: str) -> str | None:
    try:
        return subprocess.run(["git", *arguments], cwd=ROOT, check=True, capture_output=True,
                              text=True).stdout.strip()
    except subprocess.SubprocessError:
        return None


def compiler_metadata() -> dict[str, str]:
    cache = ROOT / "build" / "CMakeCache.txt"
    result: dict[str, str] = {}
    if cache.exists():
        for line in cache.read_text(encoding="utf-8", errors="replace").splitlines():
            for key in ("CMAKE_CXX_COMPILER", "CMAKE_CXX_COMPILER_VERSION"):
                if line.startswith(key + ":"):
                    result[key.lower()] = line.split("=", 1)[-1]
    return result


class Cycle:
    def __init__(self, config_path: Path, output: Path, engine_override: Path | None = None):
        self.config_path = config_path
        self.config = json.loads(config_path.read_text(encoding="utf-8"))
        self.output = output
        self.engine_override = engine_override
        self.started = time.monotonic()
        self.commands: list[dict[str, Any]] = []
        self.budgets = self.config.get("budgets", {})
        self.max_seconds = float(self.budgets.get("max_seconds", 3600))
        self.max_bytes = int(float(self.budgets.get("max_storage_mb", 1024)) * 1024 * 1024)
        if self.config.get("schema_version") != 1 or not self.config.get("id"):
            raise ValueError("config requires schema_version 1 and a non-empty id")
        selfplay_games = int(self.budgets.get("selfplay_games", 0))
        evaluation_games = int(self.budgets.get("evaluation_games", 16))
        if selfplay_games < 0 or selfplay_games % 2:
            raise ValueError("selfplay_games must be a nonnegative even number")
        if evaluation_games < 2 or evaluation_games % 2:
            raise ValueError("evaluation_games must be a positive even number")
        if self.max_seconds <= 0 or self.max_bytes <= 0:
            raise ValueError("time and storage budgets must be positive")
        if int(self.budgets.get("threads", 1)) < 1:
            raise ValueError("threads must be positive")

    def remaining(self) -> float:
        return self.max_seconds - (time.monotonic() - self.started)

    def output_bytes(self) -> int:
        return sum(path.stat().st_size for path in self.output.rglob("*") if path.is_file())

    def check_budgets(self) -> None:
        if self.remaining() <= 0:
            raise TimeoutError("learning cycle exceeded max_seconds")
        if self.output_bytes() > self.max_bytes:
            raise RuntimeError("learning cycle exceeded max_storage_mb")

    def run(self, stage: str, command: list[str]) -> None:
        self.check_budgets()
        started = time.monotonic()
        print(f"[{stage}] iniciado", flush=True)
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                   errors="replace", bufsize=1)
        output: Queue[str] = Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                output.put(line)

        reader = Thread(target=read_output, daemon=True)
        reader.start()
        captured: list[str] = []
        deadline = time.monotonic() + max(1, self.remaining())
        while process.poll() is None or reader.is_alive() or not output.empty():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                process.wait()
                raise subprocess.TimeoutExpired(command, self.max_seconds)
            try:
                line = output.get(timeout=min(0.2, remaining))
            except Empty:
                continue
            print(line, end="", flush=True)
            captured.append(line)
        reader.join(timeout=1)
        code = process.returncode
        stdout = "".join(captured)
        record = {"stage": stage, "command": command, "exit_code": code,
                  "duration_seconds": round(time.monotonic() - started, 3),
                  "stdout": stdout[-4000:], "stderr": ""}
        self.commands.append(record)
        if code:
            raise RuntimeError(f"{stage} failed with exit code {code}: {stdout[-1000:]}")
        self.check_budgets()

    def options(self, kind: str, artifact: Path) -> dict[str, Any]:
        if kind == "nnue":
            return {"NNUEFile": str(artifact), "NNUE": True, "Threads":
                    int(self.budgets.get("threads", 1))}
        return {"EvalFile": str(artifact), "NNUE": False, "Threads":
                int(self.budgets.get("threads", 1))}

    def execute(self) -> dict[str, Any]:
        mode = self.config.get("mode", "nnue")
        if mode not in {"nnue", "hce"}:
            raise ValueError("mode must be nnue or hce")
        engine = (self.engine_override or (ROOT / self.config["engine"])).resolve(strict=True)
        reference = (ROOT / self.config["reference"]).resolve(strict=True)
        reference_kind = self.config.get("reference_kind", "hce")
        openings = (ROOT / self.config.get("openings", "data/openings/core.json")).resolve(
            strict=True)
        seed = int(self.config.get("seed", 1))
        python = sys.executable
        self.output.mkdir(parents=True, exist_ok=False)
        shutil.copy2(self.config_path, self.output / "config.json")
        pgns = [(ROOT / value).resolve(strict=True) for value in self.config.get("source_pgns", [])]
        metadata: list[Path] = []

        selfplay = self.config.get("selfplay", {})
        selfplay_games = int(self.budgets.get("selfplay_games", 0))
        if selfplay.get("enabled", selfplay_games > 0) and selfplay_games:
            match = self.output / "selfplay"
            options = json.dumps(self.options(reference_kind, reference))
            opponent_value = selfplay.get("opponent_engine")
            if opponent_value:
                opponent = Path(opponent_value)
                if not opponent.is_absolute():
                    opponent = ROOT / opponent
                opponent = opponent.resolve(strict=True)
                opponent_options = json.dumps(selfplay.get("opponent_options", {}))
                opponent_name = str(selfplay.get("opponent_name", opponent.stem))
            else:
                opponent = engine
                opponent_options = options
                opponent_name = "generator-b"
            command = [python, str(ROOT / "tools" / "match_runner.py"), "--engine-a",
                       str(engine), "--engine-b", str(opponent), "--name-a", "ChessBot",
                       "--name-b", opponent_name, "--options-a", options, "--options-b",
                       opponent_options, "--games", str(selfplay_games), "--depth",
                       str(selfplay.get("depth", 1)), "--max-plies",
                       str(selfplay.get("max_plies", 80)), "--color-mode", "paired",
                       "--openings", str(openings), "--seed", str(seed), "--output-dir",
                       str(match)]
            if opponent_value:
                command.extend(["--cwd-b", str(opponent.parent)])
            opening_ids = selfplay.get("opening_ids", [])
            if opening_ids:
                command.extend(["--opening-ids", ",".join(map(str, opening_ids))])
            command.extend(["--engine-log-level", str(selfplay.get("engine_log_level", "WARNING"))])
            self.run("games", command)
            pgns.append(match / "games.pgn")
            metadata.append(match / "metadata.json")
        if not pgns:
            raise ValueError("the cycle needs source_pgns or a positive selfplay_games budget")

        dataset = self.output / "dataset.csv"
        dataset_config = self.config.get("dataset", {})
        feature_eval = (ROOT / self.config.get("feature_eval_file",
                                              "data/evaluation/hce-default-v1.params")).resolve(
            strict=True)
        command = [python, str(ROOT / "tools" / "generate_dataset.py"), "--pgn",
                   *map(str, pgns), "--engine", str(engine), "--eval-file", str(feature_eval),
                   "--output", str(dataset), "--skip-plies",
                   str(dataset_config.get("skip_plies", 2)), "--sample-every",
                   str(dataset_config.get("sample_every", 2)), "--max-per-game",
                   str(dataset_config.get("max_per_game", 24)), "--max-per-bucket",
                   str(dataset_config.get("max_per_bucket", 0)), "--validation-fraction",
                   str(dataset_config.get("validation_fraction", 0.2)), "--seed", str(seed)]
        if metadata:
            command.extend(["--metadata", *map(str, metadata)])
        self.run("data", command)

        training = self.output / "training"
        training_config = self.config.get("training", {})
        if mode == "nnue":
            command = [python, str(ROOT / "tools" / "train_nnue.py"), "--dataset",
                       str(dataset), "--output-dir", str(training), "--version",
                       str(self.config.get("candidate_version", self.config["id"])), "--hidden",
                       str(training_config.get("hidden", 32)), "--epochs",
                       str(training_config.get("epochs", 20)), "--batch-size",
                       str(training_config.get("batch_size", 256)), "--learning-rate",
                       str(training_config.get("learning_rate", 0.002)), "--target",
                       str(training_config.get("target", "mixed")), "--teacher-weight",
                       str(training_config.get("teacher_weight", 0.25)), "--seed", str(seed)]
            if training_config.get("binary_shards", False):
                command.extend(["--shard-dir", str(training / "shards"), "--shard-size",
                                str(training_config.get("shard_size", 100_000))])
            candidate, report = training / "candidate.nnue", training / "training.json"
        else:
            command = [python, str(ROOT / "tools" / "tune_eval.py"), "--dataset",
                       str(dataset), "--output-dir", str(training), "--reference",
                       str(reference), "--iterations", str(training_config.get("iterations", 500)),
                       "--version", str(self.config.get("candidate_version", self.config["id"]))]
            candidate, report = training / "candidate.params", training / "tuning.json"
        self.run("training", command)

        evaluation = self.output / "evaluation"
        eval_config = self.config.get("evaluation", {})
        games = int(self.budgets.get("evaluation_games", 16))
        promotion = self.config.get("promote_to")
        command = [python, str(ROOT / "tools" / "evaluate_candidate.py"), "--engine",
                   str(engine), "--candidate", str(candidate), "--candidate-kind", mode,
                   "--reference", str(reference), "--reference-kind", reference_kind,
                   "--training-report", str(report), "--openings", str(openings),
                   "--output-dir", str(evaluation), "--games", str(games), "--depth",
                   str(eval_config.get("depth", 3)), "--benchmark-depth",
                   str(eval_config.get("benchmark_depth", 4)), "--max-plies",
                   str(eval_config.get("max_plies", 160)), "--max-performance-regression",
                   str(eval_config.get("max_performance_regression", 0.2)),
                   "--minimum-lower-score", str(eval_config.get("minimum_lower_score", 0.5)),
                   "--minimum-independent-samples",
                   str(eval_config.get("minimum_independent_samples", 8))]
        opening_ids = eval_config.get("opening_ids", [])
        if opening_ids:
            command.extend(["--opening-ids", ",".join(map(str, opening_ids))])
        if promotion:
            command.extend(["--promote-to", str((ROOT / promotion).resolve())])
        self.run("candidate_evaluation", command)
        decision = json.loads((evaluation / "decision.json").read_text(encoding="utf-8"))
        return {"decision": decision["decision"], "engine": engine}

    def manifest(self, status: str, result: dict[str, Any] | None,
                 error: str | None = None) -> dict[str, Any]:
        files = []
        if self.output.exists():
            paths = (path for path in sorted(self.output.rglob("*"))
                     if path.is_file() and path.name != "manifest.json")
            files.extend({"path": str(path.relative_to(self.output)),
                          "bytes": path.stat().st_size, "sha256": digest(path)}
                         for path in paths)
        engine_version = None
        if result:
            run = subprocess.run([str(result["engine"]), "--help"], capture_output=True,
                                 text=True)
            engine_version = run.stdout.splitlines()[0] if run.stdout else None
        return {"schema_version": 1, "experiment_id": self.config.get("id"),
                "status": status, "decision": result.get("decision") if result else None,
                "error": error, "created_at": datetime.now(UTC).isoformat(),
                "duration_seconds": round(time.monotonic() - self.started, 3),
                "budgets": self.budgets, "storage_bytes": self.output_bytes(),
                "versions": {"engine": engine_version,
                             "search": self.config.get("search_version", "optimized-v1"),
                             "evaluation": self.config.get("evaluation_version", "hce-default-v1"),
                             "book": self.config.get("book_version", "core-v1"),
                             "network": self.config.get("candidate_version"),
                             "dataset_schema": 1},
                "environment": {"git_commit": git_value("rev-parse", "HEAD"),
                                "git_dirty": bool(git_value("status", "--porcelain")),
                                "seed": self.config.get("seed", 1), "python": sys.version,
                                "platform": platform.platform(), "processor": platform.processor(),
                                "cpu_count": os.cpu_count(), **compiler_metadata()},
                "commands": self.commands, "artifacts": files}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--engine", type=Path,
                        help="override the engine path from the config (useful in CI)")
    args = parser.parse_args()
    config = args.config.resolve(strict=True)
    output = args.output_dir.resolve()
    if output.exists():
        parser.error("output directory already exists; use a new experiment directory")
    cycle = Cycle(config, output, args.engine)
    result = None
    error = None
    try:
        result = cycle.execute()
        status = "complete"
    except Exception as exception:
        status, error = "failed", str(exception)
    output.mkdir(parents=True, exist_ok=True)
    manifest = cycle.manifest(status, result, error)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n",
                                           encoding="utf-8")
    print(json.dumps({"status": status, "decision": manifest["decision"],
                      "manifest": str(output / "manifest.json"), "error": error}))
    if error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
