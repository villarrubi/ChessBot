"""Evaluate and promote or reject an evaluation parameter candidate with recorded gates."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import chess
import chess.engine


POSITIONS = (chess.STARTING_FEN,
             "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
             "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")
TACTICS = (("7k/8/6K1/8/8/8/5Q2/8 w - - 0 1", "f2f8", 2),
           ("7k/8/4K3/8/8/8/3Q4/8 w - - 0 1", "e6f7", 4),
           ("4k3/8/8/8/8/8/4q3/4KQ2 w - - 0 1", "f1e2", 2))


def correctness(engine: Path, candidate: Path) -> dict[str, Any]:
    perft = []
    for depth, expected in ((3, 8902), (4, 197281)):
        run = subprocess.run([str(engine), "perft", str(depth)], check=True,
                             capture_output=True, text=True)
        actual = int(run.stdout.strip())
        perft.append({"depth": depth, "expected": expected, "actual": actual,
                      "pass": actual == expected})
    process = chess.engine.SimpleEngine.popen_uci(str(engine), timeout=10)
    tactics = []
    try:
        process.configure({"EvalFile": str(candidate)})
        for fen, expected, depth in TACTICS:
            played = process.play(chess.Board(fen), chess.engine.Limit(depth=depth))
            actual = played.move.uci() if played.move else "0000"
            tactics.append({"fen": fen, "depth": depth, "expected": expected, "actual": actual,
                            "pass": actual == expected})
    finally:
        process.quit()
    return {"perft": perft, "tactics": tactics,
            "pass": all(row["pass"] for row in perft + tactics)}


def benchmark(engine: Path, parameters: Path, depth: int) -> dict[str, Any]:
    process = chess.engine.SimpleEngine.popen_uci(str(engine), timeout=15)
    elapsed = nodes = 0
    rows = []
    try:
        process.configure({"EvalFile": str(parameters), "OwnBook": False})
        for fen in POSITIONS:
            started = time.perf_counter()
            result = process.play(chess.Board(fen), chess.engine.Limit(depth=depth),
                                  info=chess.engine.INFO_ALL)
            duration = time.perf_counter() - started
            count = int(result.info.get("nodes", 0))
            elapsed += duration
            nodes += count
            rows.append({"fen": fen, "move": result.move.uci() if result.move else "0000",
                         "nodes": count, "elapsed_ms": round(duration * 1000, 3)})
    finally:
        process.quit()
    return {"depth": depth, "nodes": nodes, "elapsed_ms": round(elapsed * 1000, 3),
            "nps": round(nodes / max(elapsed, 1e-9)), "positions": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--tuning-report", type=Path)
    parser.add_argument("--openings", type=Path, default=Path("data/openings/core.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--games", type=int, default=16)
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--benchmark-depth", type=int, default=4)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--max-performance-regression", type=float, default=0.20)
    parser.add_argument("--minimum-lower-score", type=float, default=0.5)
    parser.add_argument("--minimum-independent-samples", type=int, default=8)
    parser.add_argument("--promote-to", type=Path)
    args = parser.parse_args()
    if args.games < 2 or args.games % 2 or args.depth < 1 or args.benchmark_depth < 1:
        parser.error("games must be a positive even number and depths must be positive")
    engine = args.engine.resolve(strict=True)
    candidate = args.candidate.resolve(strict=True)
    reference = args.reference.resolve(strict=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidate_copy = (args.output_dir / "candidate.params").resolve()
    reference_copy = (args.output_dir / "reference.params").resolve()
    shutil.copy2(candidate, candidate_copy)
    shutil.copy2(reference, reference_copy)

    rules = correctness(engine, candidate_copy)
    reference_benchmark = benchmark(engine, reference_copy, args.benchmark_depth)
    candidate_benchmark = benchmark(engine, candidate_copy, args.benchmark_depth)
    performance_ratio = (candidate_benchmark["elapsed_ms"] /
                         max(reference_benchmark["elapsed_ms"], 0.001))
    performance_pass = performance_ratio <= 1 + args.max_performance_regression
    match_dir = args.output_dir / "match"
    command = [sys.executable, str(Path(__file__).with_name("match_runner.py")),
               "--engine-a", str(engine), "--engine-b", str(engine), "--name-a", "candidate",
               "--name-b", "reference", "--options-a", json.dumps({"EvalFile": str(candidate_copy)}),
               "--options-b", json.dumps({"EvalFile": str(reference_copy)}), "--games",
               str(args.games), "--depth", str(args.depth), "--max-plies", str(args.max_plies),
               "--color-mode", "paired", "--openings", str(args.openings.resolve(strict=True)),
               "--output-dir", str(match_dir)]
    subprocess.run(command, check=True)
    match = json.loads((match_dir / "metadata.json").read_text(encoding="utf-8"))
    statistics = match["statistics"]
    strength_pass = (statistics["score_confidence95"][0] > args.minimum_lower_score and
                     statistics.get("independent_samples", 0) >= args.minimum_independent_samples)
    validation_pass = True
    tuning: dict[str, Any] | None = None
    if args.tuning_report:
        tuning = json.loads(args.tuning_report.read_text(encoding="utf-8"))
        validation_pass = bool(tuning.get("validation_improved"))
    gates = {"correctness_and_tactics": rules["pass"], "validation": validation_pass,
             "performance": performance_pass, "strength": strength_pass}
    accepted = all(gates.values())
    promoted = None
    if accepted and args.promote_to:
        args.promote_to.parent.mkdir(parents=True, exist_ok=True)
        if args.promote_to.exists():
            shutil.copy2(args.promote_to, args.output_dir / "previous-promoted-reference.params")
        shutil.copy2(candidate_copy, args.promote_to)
        promoted = str(args.promote_to)
    decision = {"schema_version": 1, "decision": "accept" if accepted else "reject",
                "gates": gates, "thresholds": {
                    "maximum_performance_regression": args.max_performance_regression,
                    "minimum_lower_score": args.minimum_lower_score,
                    "minimum_independent_samples": args.minimum_independent_samples},
                "correctness": rules, "benchmark": {"reference": reference_benchmark,
                                                       "candidate": candidate_benchmark,
                                                       "elapsed_ratio": performance_ratio},
                "match": {"metadata": str(match_dir / "metadata.json"),
                          "statistics": statistics}, "tuning_report": tuning,
                "artifacts": {"candidate": str(candidate_copy), "reference": str(reference_copy),
                              "promoted_to": promoted}}
    decision_path = args.output_dir / "decision.json"
    decision_path.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"decision": decision["decision"], "gates": gates,
                      "report": str(decision_path)}))


if __name__ == "__main__":
    main()
