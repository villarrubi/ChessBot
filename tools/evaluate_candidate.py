"""Evaluate and promote or reject an HCE or NNUE candidate through recorded gates."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import chess
import chess.engine

from process_affinity import set_process_affinity


POSITIONS = (chess.STARTING_FEN,
             "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
             "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
TACTICS = (("7k/8/6K1/8/8/8/5Q2/8 w - - 0 1", ("f2f8",), 2),
           ("7k/8/4K3/8/8/8/3Q4/8 w - - 0 1", ("e6f7",), 4),
           # Both captures win the undefended queen; Kxe2 is also correct.
           ("4k3/8/8/8/8/8/4q3/4KQ2 w - - 0 1", ("f1e2", "e1e2"), 2))


def engine_options(kind: str, artifact: Path) -> dict[str, Any]:
    if kind == "nnue":
        return {"NNUEFile": str(artifact), "NNUE": True, "OwnBook": False}
    return {"EvalFile": str(artifact), "NNUE": False, "OwnBook": False}


def start_engine(engine: Path, options: dict[str, Any], cores: int) -> chess.engine.SimpleEngine:
    process = chess.engine.SimpleEngine.popen_uci(str(engine), timeout=15)
    set_process_affinity(process.transport.get_pid(), cores)
    process.configure(options)
    return process


def correctness(engine: Path, options: dict[str, Any], cores: int) -> dict[str, Any]:
    perft = []
    for depth, expected in ((3, 8902), (4, 197281)):
        run = subprocess.run([str(engine), "perft", str(depth)], check=True,
                             capture_output=True, text=True)
        actual = int(run.stdout.strip())
        perft.append({"depth": depth, "expected": expected, "actual": actual,
                      "pass": actual == expected})
    process = start_engine(engine, options, cores)
    tactics = []
    try:
        for fen, expected, depth in TACTICS:
            played = process.play(chess.Board(fen), chess.engine.Limit(depth=depth))
            actual = played.move.uci() if played.move else "0000"
            tactics.append({"fen": fen, "depth": depth, "expected": expected,
                            "actual": actual, "pass": actual in expected})
    finally:
        process.quit()
    return {"perft": perft, "tactics": tactics,
            "pass": all(row["pass"] for row in perft + tactics)}


def benchmark(engine: Path, options: dict[str, Any], depth: int, cores: int) -> dict[str, Any]:
    process = start_engine(engine, options, cores)
    elapsed = nodes = 0
    rows = []
    try:
        for fen in POSITIONS:
            started = time.perf_counter()
            result = process.play(chess.Board(fen), chess.engine.Limit(depth=depth, nodes=2_000_000),
                                  info=chess.engine.INFO_ALL, game=object())
            duration = time.perf_counter() - started
            count = int(result.info.get("nodes", 0))
            elapsed += duration
            nodes += count
            rows.append({"fen": fen, "move": result.move.uci() if result.move else "0000",
                         "nodes": count, "elapsed_ms": round(duration * 1000, 3),
                         "completed_depth": int(result.info.get("depth", 0)) >= depth})
    finally:
        process.quit()
    return {"depth": depth, "nodes": nodes, "elapsed_ms": round(elapsed * 1000, 3),
            "mean_latency_ms": round(elapsed * 1000 / len(POSITIONS), 3),
            "nps": round(nodes / max(elapsed, 1e-9)), "positions": rows}


def validation_gate(report_path: Path | None) -> tuple[bool, dict[str, Any] | None]:
    if report_path is None:
        return True, None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if "validation_improved" in report:
        return bool(report["validation_improved"]), report
    metrics = report.get("metrics", {}).get("validation", {})
    required = ("loss", "brier", "wdl_ece")
    valid = all(key in metrics and math.isfinite(float(metrics[key])) for key in required)
    initial = report.get("metrics", {}).get("initial_validation")
    if initial:
        quantized = report["metrics"].get("quantized_validation", {})
        valid = (valid and metrics["loss"] <= initial["loss"] and
                 math.isfinite(float(quantized.get("loss", float("nan")))) and
                 quantized["loss"] <= metrics["loss"] + 0.02)
    return valid, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--candidate-kind", choices=("hce", "nnue"), default="hce")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--reference-kind", choices=("hce", "nnue"), default="hce")
    parser.add_argument("--training-report", "--tuning-report", dest="training_report",
                        type=Path)
    parser.add_argument("--openings", type=Path, default=Path("data/openings/core.json"))
    parser.add_argument("--opening-ids",
                        help="comma-separated opening identifiers to include")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--games", type=int, default=16)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--benchmark-depth", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--max-performance-regression", type=float, default=0.20)
    parser.add_argument("--max-search-slowdown", type=float, default=3.0)
    parser.add_argument("--exploration-plies", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--minimum-lower-score", type=float, default=0.5)
    parser.add_argument("--minimum-independent-samples", type=int, default=8)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--promote-to", type=Path)
    args = parser.parse_args()
    if args.games < 2 or args.games % 2 or args.depth < 1 or args.benchmark_depth < 1:
        parser.error("games must be a positive even number and depths must be positive")
    if args.cores < 1 or args.cores > 64:
        parser.error("cores must be between 1 and 64")
    engine = args.engine.resolve(strict=True)
    candidate = args.candidate.resolve(strict=True)
    reference = args.reference.resolve(strict=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_copy = (args.output_dir / f"candidate{candidate.suffix}").resolve()
    reference_copy = (args.output_dir / f"reference{reference.suffix}").resolve()
    shutil.copy2(candidate, candidate_copy)
    shutil.copy2(reference, reference_copy)
    candidate_options = engine_options(args.candidate_kind, candidate_copy)
    reference_options = engine_options(args.reference_kind, reference_copy)

    rules = correctness(engine, candidate_options, args.cores)
    reference_benchmark = benchmark(engine, reference_options, args.benchmark_depth, args.cores)
    candidate_benchmark = benchmark(engine, candidate_options, args.benchmark_depth, args.cores)
    nps_ratio = candidate_benchmark["nps"] / max(reference_benchmark["nps"], 1)
    performance_ratio = 1 / max(nps_ratio, 1e-9)
    latency_ratio = candidate_benchmark["elapsed_ms"] / max(reference_benchmark["elapsed_ms"], 1)
    performance_pass = (nps_ratio >= 1 - args.max_performance_regression and
                        latency_ratio <= args.max_search_slowdown and
                        all(row["completed_depth"] for row in candidate_benchmark["positions"]))
    match_dir = args.output_dir / "match"
    command = [sys.executable, str(Path(__file__).with_name("match_runner.py")),
               "--engine-a", str(engine), "--engine-b", str(engine), "--name-a", "candidate",
               "--name-b", "reference", "--options-a", json.dumps(candidate_options),
               "--options-b", json.dumps(reference_options), "--games", str(args.games),
               "--depth", str(args.depth), "--max-plies", str(args.max_plies),
               "--color-mode", "paired", "--openings", str(args.openings.resolve(strict=True)),
               "--output-dir", str(match_dir), "--exploration-plies", str(args.exploration_plies),
               "--exploration-engine", "b", "--seed", str(args.seed),
               "--cores-a", str(args.cores), "--cores-b", str(args.cores)]
    if args.opening_ids:
        command.extend(["--opening-ids", args.opening_ids])
    subprocess.run(command, check=True)
    match = json.loads((match_dir / "metadata.json").read_text(encoding="utf-8"))
    statistics = match["statistics"]
    strength_pass = (statistics["score_confidence95"][0] > args.minimum_lower_score and
                     statistics.get("independent_samples", 0) >=
                     args.minimum_independent_samples)
    validation_pass, training = validation_gate(args.training_report)
    gates = {"correctness_and_tactics": rules["pass"], "validation": validation_pass,
             "performance": performance_pass, "strength": strength_pass}
    accepted = all(gates.values())
    promoted = None
    if accepted and args.promote_to:
        args.promote_to.parent.mkdir(parents=True, exist_ok=True)
        if args.promote_to.exists():
            backup = args.output_dir / f"previous-promoted-reference{args.promote_to.suffix}"
            shutil.copy2(args.promote_to, backup)
        shutil.copy2(candidate_copy, args.promote_to)
        promoted = str(args.promote_to)
    decision = {"schema_version": 2, "decision": "accept" if accepted else "reject",
                "candidate_kind": args.candidate_kind, "reference_kind": args.reference_kind,
                "gates": gates, "thresholds": {
                   "maximum_performance_regression": args.max_performance_regression,
                    "maximum_search_slowdown": args.max_search_slowdown,
                    "minimum_lower_score": args.minimum_lower_score,
                    "minimum_independent_samples": args.minimum_independent_samples},
                "correctness": rules, "benchmark": {"reference": reference_benchmark,
                    "candidate": candidate_benchmark, "relative_nps": nps_ratio,
                    "nps_slowdown_ratio": performance_ratio,
                    "search_time_ratio": latency_ratio,
                    "candidate_artifact_bytes": candidate_copy.stat().st_size},
                "match": {"metadata": str(match_dir / "metadata.json"),
                          "statistics": statistics}, "training_report": training,
                "options": {"candidate": candidate_options, "reference": reference_options},
                "artifacts": {"candidate": str(candidate_copy),
                              "reference": str(reference_copy), "promoted_to": promoted}}
    decision_path = args.output_dir / "decision.json"
    decision_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision["decision"], "gates": gates,
                      "report": str(decision_path)}))


if __name__ == "__main__":
    main()
