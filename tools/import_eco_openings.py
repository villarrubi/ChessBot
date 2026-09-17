"""Import one representative line for each of the 500 ECO codes."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

import chess
import chess.pgn


def read_source(source: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(source.glob("*.tsv")):
        with path.open(encoding="utf-8", newline="") as handle:
            rows.extend(csv.DictReader(handle, delimiter="\t"))
    return rows


def parse_moves(pgn: str) -> list[str]:
    game = chess.pgn.read_game(__import__("io").StringIO(pgn + " *"))
    if game is None or game.errors:
        raise ValueError(f"línea PGN no válida: {pgn}")
    return [move.uci() for move in game.mainline_moves()]


def choose_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        eco = row.get("eco", "").strip()
        if not re.fullmatch(r"[A-E][0-9]{2}", eco):
            continue
        moves = parse_moves(row.get("pgn", ""))
        grouped.setdefault(eco, []).append({
            "eco": eco,
            "name": row.get("name", eco).strip(),
            "moves_uci": moves,
        })

    selected: list[dict[str, Any]] = []
    for eco in sorted(grouped):
        candidates = grouped[eco]
        # Keep the prefix useful without forcing an entire deep variation. A
        # 10-ply line usually identifies the ECO while leaving the engine room
        # to play the middlegame itself.
        choice = min(candidates, key=lambda item: (abs(len(item["moves_uci"]) - 10),
                                                    len(item["moves_uci"]),
                                                    item["name"]))
        selected.append({
            "id": f"eco_{eco.lower()}",
            "name": choice["name"],
            "eco": eco,
            "start_fen": "startpos",
            "moves_uci": choice["moves_uci"],
        })
    return selected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="directorio con a.tsv ... e.tsv")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    openings = choose_rows(read_source(args.source))
    expected = {f"{letter}{number:02d}" for letter in "ABCDE" for number in range(100)}
    actual = {opening["eco"] for opening in openings}
    missing = sorted(expected - actual)
    if missing:
        raise SystemExit(f"faltan códigos ECO: {', '.join(missing)}")
    payload = {
        "schema_version": 1,
        "version": "eco-500-lichess-v1",
        "source": "lichess-org/chess-openings (CC0)",
        "source_url": "https://github.com/lichess-org/chess-openings",
        "description": "Una línea representativa para cada código ECO A00-E99.",
        "openings": openings,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"Escritas {len(openings)} aperturas ECO en {args.output}")


if __name__ == "__main__":
    main()
