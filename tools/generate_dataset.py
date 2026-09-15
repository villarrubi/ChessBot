"""Generate a versioned evaluation dataset from PGN games and match metadata."""
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chess
import chess.pgn


COMPONENTS = ("material", "piece_square", "mobility", "pawn_structure", "passed_pawns",
              "bishop_pair", "rook_activity", "king_safety", "space", "tempo")
SCHEMA_VERSION = 1


@dataclass
class Sample:
    game_id: str
    source: str
    origin: str
    result_white: float
    ply: int
    fen: str
    search_score_cp: int | None
    search_score_perspective: str | None


class FeatureEngine:
    def __init__(self, executable: Path, eval_file: Path | None = None):
        command = [str(executable), "features-stream"]
        if eval_file:
            command += ["--eval-file", str(eval_file)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True, bufsize=1)

    def evaluate(self, fen: str) -> dict[str, Any]:
        assert self.process.stdin and self.process.stdout
        self.process.stdin.write(fen + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            error = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"feature engine stopped unexpectedly: {error}")
        payload = json.loads(line)
        if "error" in payload:
            raise ValueError(payload["error"])
        return payload

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            code = self.process.wait()
        if code:
            error = self.process.stderr.read() if self.process.stderr else ""
            raise RuntimeError(f"feature engine exited with {code}: {error}")


def result_value(result: str) -> float | None:
    return {"1-0": 1.0, "1/2-1/2": 0.5, "0-1": 0.0}.get(result)


def metadata_scores(paths: Iterable[Path]) -> dict[tuple[str, int, int], tuple[int | None, str]]:
    scores: dict[tuple[str, int, int], tuple[int | None, str]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        pgn = Path(payload.get("artifacts", {}).get("pgn", "games.pgn"))
        if not pgn.is_absolute():
            pgn = (path.parent / pgn).resolve()
        for game in payload.get("games", []):
            round_number = int(game.get("round", 0))
            for move in game.get("moves", []):
                perspective = move.get("side", "white" if int(move["ply"]) % 2 else "black")
                scores[(str(pgn), round_number, int(move["ply"]))] = (move.get("score_cp"),
                                                                      perspective)
    return scores


def read_games(paths: Iterable[Path],
               scores: dict[tuple[str, int, int], tuple[int | None, str]],
               skip_plies: int, sample_every: int, max_per_game: int) -> list[Sample]:
    samples: list[Sample] = []
    for path in paths:
        absolute = str(path.resolve())
        with path.open(encoding="utf-8") as handle:
            index = 0
            while game := chess.pgn.read_game(handle):
                index += 1
                if game.errors:
                    raise ValueError(f"invalid PGN game {index} in {path}: {game.errors}")
                outcome = result_value(game.headers.get("Result", "*"))
                if outcome is None:
                    continue
                game_id = f"{absolute}#{index}"
                origin = game.headers.get("Source", game.headers.get("Event", path.stem))
                board = game.board()
                selected = 0
                for relative_ply, move in enumerate(game.mainline_moves(), start=1):
                    board.push(move)
                    ply = board.ply()
                    if relative_ply <= skip_plies or (relative_ply - skip_plies - 1) % sample_every:
                        continue
                    if board.is_game_over(claim_draw=True):
                        continue
                    score, perspective = scores.get((absolute, index, ply), (None, None))
                    samples.append(Sample(game_id, absolute, origin, outcome, ply, board.fen(),
                                          score, perspective))
                    selected += 1
                    if max_per_game and selected >= max_per_game:
                        break
    return samples


def split_games(samples: list[Sample], validation_fraction: float, seed: int) -> dict[str, str]:
    games = sorted({sample.game_id for sample in samples})
    random.Random(seed).shuffle(games)
    count = round(len(games) * validation_fraction)
    if len(games) > 1:
        count = min(len(games) - 1, max(1, count))
    validation = set(games[:count])
    return {game: "validation" if game in validation else "train" for game in games}


def write_output(rows: list[dict[str, Any]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".parquet":
        try:
            import pandas as pd
        except ImportError as error:
            raise RuntimeError("Parquet output requires pip install -e '.[analysis]'") from error
        pd.DataFrame(rows).to_parquet(output, index=False)
    else:
        with output.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pgn", type=Path, nargs="+", required=True)
    parser.add_argument("--metadata", type=Path, nargs="*", default=[])
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--eval-file", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skip-plies", type=int, default=8)
    parser.add_argument("--sample-every", type=int, default=2)
    parser.add_argument("--max-per-game", type=int, default=64)
    parser.add_argument("--max-per-bucket", type=int, default=0,
                        help="cap samples per 200 cp evaluation bucket; zero disables")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()
    if args.skip_plies < 0 or args.sample_every < 1 or args.max_per_game < 0:
        parser.error("invalid filtering limits")
    if not 0 < args.validation_fraction < 1:
        parser.error("validation-fraction must be between zero and one")
    scores = metadata_scores(args.metadata)
    samples = read_games(args.pgn, scores, args.skip_plies, args.sample_every,
                         args.max_per_game)
    if not samples:
        parser.error("no usable positions found")
    split = split_games(samples, args.validation_fraction, args.seed)
    engine = FeatureEngine(args.engine.resolve(strict=True), args.eval_file)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    buckets: dict[int, int] = {}
    try:
        for sample in samples:
            features = engine.evaluate(sample.fen)
            key = str(features["key"])
            if key in seen:
                continue
            bucket = int(features["total"]) // 200
            if args.max_per_bucket and buckets.get(bucket, 0) >= args.max_per_bucket:
                continue
            seen.add(key)
            buckets[bucket] = buckets.get(bucket, 0) + 1
            side_white = features["side_to_move"] == "white"
            row = {"schema_version": SCHEMA_VERSION, "zobrist": key, "fen": features["fen"],
                   "side_to_move": features["side_to_move"], "ply": sample.ply,
                   "game_id": sample.game_id, "source": sample.source, "origin": sample.origin,
                   "split": split[sample.game_id], "result_white": sample.result_white,
                   "result_stm": sample.result_white if side_white else 1 - sample.result_white,
                   "search_score_cp": sample.search_score_cp,
                   "search_score_perspective": sample.search_score_perspective,
                   "evaluation_version": features["evaluation_version"],
                   "static_total": features["total"]}
            row.update({name: features[name] for name in COMPONENTS})
            rows.append(row)
    finally:
        engine.close()
    if not rows:
        parser.error("all positions were removed by deduplication or balancing")
    write_output(rows, args.output)
    schema = {"schema_version": SCHEMA_VERSION, "rows": len(rows),
              "games": len({row["game_id"] for row in rows}),
              "splits": {name: sum(row["split"] == name for row in rows)
                         for name in ("train", "validation")},
              "components": list(COMPONENTS), "perspective": "side_to_move",
              "target": "result_stm", "deduplication": "zobrist across all splits",
              "filters": {"skip_plies": args.skip_plies, "sample_every": args.sample_every,
                          "max_per_game": args.max_per_game,
                          "max_per_bucket": args.max_per_bucket}, "seed": args.seed}
    schema_path = args.output.with_suffix(args.output.suffix + ".schema.json")
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"dataset": str(args.output), "schema": str(schema_path), **schema}))


if __name__ == "__main__":
    main()
