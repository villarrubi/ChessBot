"""Check NNUE file round-trips, Python/C++ parity, provenance, and UCI activation."""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import chess
import chess.engine

from nnue_format import INPUT_SIZE, QuantizedNetwork, read_network, write_network


def fixture() -> QuantizedNetwork:
    hidden = 4
    weights = []
    values = (100, 320, 330, 500, 900, 0)
    for feature in range(INPUT_SIZE):
        color = feature // (6 * 64)
        piece = (feature // 64) % 6
        square = feature % 64
        sign = 1 if color == 0 else -1
        weights.extend((sign * values[piece], sign * (square % 8),
                        sign * (square // 8), 1))
    return QuantizedNetwork("parity-fixture-v1", hidden, 1, 1, [5000, 500, 500, 0],
                            weights, -5000, [1, 1, 1, 0])


def positions() -> list[chess.Board]:
    result = [chess.Board(),
              chess.Board("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/"
                          "R3K2R w KQkq - 0 1"),
              chess.Board("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1")]
    board = chess.Board()
    generator = random.Random(9)
    for _ in range(60):
        if board.is_game_over():
            board.reset()
        board.push(generator.choice(list(board.legal_moves)))
        result.append(board.copy(stack=False))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    args = parser.parse_args()
    engine_path = args.engine.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="chessbot-nnue-") as directory:
        network_path = Path(directory) / "fixture.nnue"
        write_network(network_path, fixture())
        network = read_network(network_path)
        checked = 0
        for board in positions():
            run = subprocess.run([str(engine_path), "eval", "--fen", board.fen(),
                                  "--nnue-file", str(network_path)], check=True,
                                 capture_output=True, text=True, timeout=10)
            evaluation = json.loads(run.stdout)
            expected = network.evaluate(board)
            assert evaluation["total"] == expected, (board.fen(), expected, evaluation)
            assert evaluation["neural"] == expected
            assert evaluation["source"] == "nnue"
            assert evaluation["network_version"] == network.version
            assert evaluation["manual_auxiliary"] is True
            checked += 1

        process = chess.engine.SimpleEngine.popen_uci(str(engine_path), timeout=10)
        try:
            process.configure({"NNUEFile": str(network_path), "NNUE": True})
            info = process.analyse(chess.Board(), chess.engine.Limit(depth=2),
                                   info=chess.engine.INFO_ALL)
            assert info["nodes"] > 0 and info["pv"]
            process.configure({"NNUE": False})
            assert process.play(chess.Board(), chess.engine.Limit(depth=1)).move is not None
        finally:
            process.quit()
        analysis = Path(directory) / "analysis.json"
        subprocess.run([sys.executable, str(Path(__file__).with_name("analyze_pgn.py")),
                        "--input", str(Path(__file__).parents[1] / "tests" / "positions" /
                                         "analysis_sample.pgn"), "--engine", str(engine_path),
                        "--nnue-file", str(network_path), "--depth", "1", "--multipv", "1",
                        "--max-plies", "1", "--json", str(analysis), "--annotated-pgn",
                        str(Path(directory) / "analysis.pgn"), "--report",
                        str(Path(directory) / "analysis.md")], check=True, capture_output=True,
                       text=True, timeout=30)
        payload = json.loads(analysis.read_text(encoding="utf-8"))
        static = payload["games"][0]["moves"][0]["static_before"]
        assert static["source"] == "nnue" and static["manual_auxiliary"] is True
        assert static["network_version"] == network.version
    print(f"PASS: {checked} Python/C++ NNUE scores, provenance, UCI search, HCE fallback")


if __name__ == "__main__":
    main()
