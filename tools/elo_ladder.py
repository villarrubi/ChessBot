"""Estimate an engine's playing strength against Stockfish UCI strength levels."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from match_runner import load_openings


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENINGS = ROOT / "data" / "openings" / "eco-500.json"


def expected_eco_codes() -> set[str]:
    return {f"{letter}{number:02d}" for letter in "ABCDE" for number in range(100)}


def validate_openings(path: Path) -> int:
    """Validate the default A00-E99 suite and return the number of entries."""
    openings = load_openings(path)
    if path.resolve() == DEFAULT_OPENINGS.resolve():
        codes = [opening.eco for opening in openings]
        if len(openings) != 500 or len(codes) != len(set(codes)) or set(codes) != expected_eco_codes():
            raise ValueError("eco-500.json debe contener exactamente los códigos ECO A00-E99")
    return len(openings)


def configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


configure_utf8_stdio()


def run_level(args: argparse.Namespace, level: int, output: Path) -> dict[str, Any]:
    command = [sys.executable, str(ROOT / "tools" / "match_runner.py"),
               "--engine-a", str(args.engine.resolve(strict=True)), "--engine-b",
               str(args.stockfish.resolve(strict=True)), "--name-a", "ChessBot",
               "--name-b", f"Stockfish {level}", "--options-b",
               json.dumps({"UCI_LimitStrength": True, "UCI_Elo": level,
                           "Threads": args.threads}),
               "--options-a", json.dumps({"Threads": args.threads}),
               "--cores-a", str(args.cores),
               "--cores-b", str(args.cores),
               "--games", str(args.games_per_level), "--depth", str(args.depth),
               "--max-plies", str(args.max_plies), "--color-mode", "paired",
               "--openings", str(args.openings.resolve(strict=True)), "--seed", str(args.seed),
               "--engine-log-level", "WARNING", "--output-dir", str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    statistics = metadata["statistics"]
    return {
        "stockfish_elo": level,
        "games": statistics["games"],
        "wins": statistics["wins"],
        "draws": statistics["draws"],
        "losses": statistics["losses"],
        "score_rate": statistics["score_rate"],
        "elo_difference": statistics["elo"],
        "elo_difference_confidence95": statistics["elo_confidence95"],
        "estimated_elo": round(level + statistics["elo"], 1),
        "estimated_elo_confidence95": [round(level + value, 1)
                                        for value in statistics["elo_confidence95"]],
        "directory": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--stockfish", type=Path, required=True)
    parser.add_argument("--openings", type=Path, default=DEFAULT_OPENINGS,
                        help="suite de aperturas; por defecto contiene A00-E99")
    parser.add_argument("--levels", default="1320,1600,2000,2400,2800,3100",
                        help="comma-separated Stockfish UCI_Elo levels")
    parser.add_argument("--games-per-level", type=int, default=1000,
                        help="partidas por nivel; se necesitan 1000 para A00-E99")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--max-plies", type=int, default=160)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.games_per_level < 2 or args.games_per_level % 2:
        parser.error("games-per-level must be a positive even number")
    if args.depth < 1 or args.max_plies < 1 or not 1 <= args.threads <= 256 or not 1 <= args.cores <= 64:
        parser.error("depth/max-plies must be positive, threads 1..256 and cores 1..64")
    try:
        levels = sorted({int(value.strip()) for value in args.levels.split(",") if value.strip()})
    except ValueError as error:
        parser.error(f"invalid levels: {error}")
    if not levels or any(level < 1320 or level > 3190 for level in levels):
        parser.error("levels must be between 1320 and 3190 Elo (rango UCI de Stockfish)")
    args.engine.resolve(strict=True)
    args.stockfish.resolve(strict=True)
    openings_path = args.openings.resolve(strict=True)
    try:
        opening_count = validate_openings(openings_path)
    except ValueError as error:
        parser.error(str(error))
    required_games = opening_count * 2
    if args.games_per_level < required_games:
        parser.error(f"games-per-level debe ser al menos {required_games} para jugar cada apertura "
                     "con ambos colores")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    rows = []
    for level in levels:
        print(f"\n=== Stockfish {level} Elo ===", flush=True)
        rows.append(run_level(args, level, args.output_dir / f"stockfish-{level}"))
    summary = {
        "engine": str(args.engine.resolve()),
        "stockfish": str(args.stockfish.resolve()),
        "levels": levels,
        "games_per_level": args.games_per_level,
        "depth": args.depth,
        "threads": args.threads,
        "cores": args.cores,
        "max_plies": args.max_plies,
        "openings": str(openings_path),
        "opening_count": opening_count,
        "games_per_opening": 2,
        "results": rows,
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n",
                                                   encoding="utf-8")
    with (args.output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["stockfish_elo", "games", "wins", "draws",
                                                     "losses", "score_rate", "estimated_elo",
                                                     "estimated_elo_confidence95"])
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in writer.fieldnames})
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
