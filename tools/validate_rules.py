"""Differential rules/PERFT validation against python-chess; never used by the C++ core."""

import argparse
import json
import random
import subprocess
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parents[1]


def expected_state(board: chess.Board) -> dict:
    moves = sorted(move.uci() for move in board.legal_moves)
    if not moves:
        status = "checkmate" if board.is_check() else "stalemate"
    elif board.is_insufficient_material():
        status = "insufficient_material"
    elif board.is_repetition(3):
        status = "threefold_repetition"
    elif board.halfmove_clock >= 100:
        status = "fifty_move"
    else:
        status = "ongoing"
    return {
        "fen": board.fen(en_passant="fen"),
        "in_check": board.is_check(),
        "threefold": board.is_repetition(3),
        "insufficient_material": board.is_insufficient_material(),
        "status": status,
        "legal_moves": moves,
    }


def reference_perft(board: chess.Board, depth: int) -> int:
    if depth == 0:
        return 1
    if depth == 1:
        return board.legal_moves.count()
    result = 0
    for move in list(board.legal_moves):
        board.push(move)
        result += reference_perft(board, depth - 1)
        board.pop()
    return result


def validate(engine: Path, games: int, plies: int, seed: int, depth: int) -> None:
    fixtures = json.loads((ROOT / "tests/positions/perft.json").read_text(encoding="utf-8"))
    fixtures += [
        {**fixture, "name": fixture["name"] + "_mirrored",
         "fen": chess.Board(fixture["fen"]).mirror().fen(en_passant="fen")}
        for fixture in list(fixtures)
    ]
    requests: list[str] = []
    expected: list[dict] = []

    def record(start: str, prefix: list[str], board: chess.Board) -> None:
        requests.append(start + "\t" + " ".join(prefix))
        expected.append(expected_state(board))

    for fixture in fixtures:
        board = chess.Board(fixture["fen"])
        if not board.is_valid():
            raise AssertionError(f"Invalid reference fixture: {fixture['name']}")
        record(fixture["fen"], [], board)
        # Compare every immediate successor, including all promotion choices.
        for move in list(board.legal_moves):
            board.push(move)
            record(fixture["fen"], [move.uci()], board)
            board.pop()
        for d in range(1, depth + 1):
            reference = reference_perft(board, d)
            known = fixture.get("nodes", [])
            if d <= len(known) and reference != known[d - 1]:
                raise AssertionError(f"Reference fixture mismatch: {fixture['name']} depth {d}")
            actual = subprocess.run(
                [str(engine), "perft", str(d), "--fen", fixture["fen"]],
                check=True, capture_output=True, text=True, timeout=120,
            )
            if int(actual.stdout.strip()) != reference:
                raise AssertionError(f"PERFT mismatch: {fixture['name']} depth {d}")

    rng = random.Random(seed)
    for game in range(games):
        # Alternate normal games and continuations of special positions.
        start = chess.STARTING_FEN if game % 2 == 0 else rng.choice(fixtures)["fen"]
        board = chess.Board(start)
        prefix: list[str] = []
        for _ in range(plies):
            record(start, prefix, board)
            legal = list(board.legal_moves)
            if not legal:
                break
            move = rng.choice(legal)
            prefix.append(move.uci())
            board.push(move)
        record(start, prefix, board)

    repeated = chess.Board()
    prefix = []
    for uci in ["g1f3", "g8f6", "f3g1", "f6g8"] * 2:
        repeated.push_uci(uci)
        prefix.append(uci)
        record(chess.STARTING_FEN, prefix, repeated)

    run = subprocess.run(
        [str(engine), "validate-stream"], input="\n".join(requests) + "\n",
        capture_output=True, text=True, check=True, timeout=300,
    )
    lines = run.stdout.splitlines()
    if len(lines) != len(expected):
        raise AssertionError(f"Expected {len(expected)} responses, got {len(lines)}: {run.stderr}")
    for request, wanted, line in zip(requests, expected, lines, strict=True):
        actual = json.loads(line)
        for field, value in wanted.items():
            if actual.get(field) != value:
                raise AssertionError(f"Mismatch in {field}\nRequest: {request}\nExpected: {value}\nActual: {actual}")
    print(f"PASS: {len(expected)} positions, {len(fixtures)} PERFT fixtures through depth {depth}, seed {seed}")


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--games", type=positive, default=40)
    parser.add_argument("--plies", type=positive, default=150)
    parser.add_argument("--seed", type=int, default=20260914)
    parser.add_argument("--perft-depth", type=positive, choices=range(1, 5), default=3)
    args = parser.parse_args()
    validate(args.engine.resolve(strict=True), args.games, args.plies, args.seed, args.perft_depth)
