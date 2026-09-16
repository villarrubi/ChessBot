"""Exercise opening import formats and phase-7 match scenarios A through F."""
import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import chess
import chess.pgn
import chess.polyglot

from match_runner import load_openings, statistics


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
engine = args.engine.resolve(strict=True)


def run(output: Path, *arguments: str) -> dict:
    command = [sys.executable, str(root / "tools" / "match_runner.py"),
               "--engine-a", str(engine), "--engine-b", str(engine), "--output-dir", str(output),
               *arguments]
    subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
    with (output / "games.pgn").open(encoding="utf-8") as handle:
        while game := chess.pgn.read_game(handle):
            assert not game.errors
    assert (output / "engine.log").exists()
    assert (output / "progress.log").exists()
    return payload


with tempfile.TemporaryDirectory() as directory:
    temporary = Path(directory)
    # Import PGN, EPD, FEN/UCI text, native JSON, and a minimal Polyglot book.
    epd = temporary / "suite.epd"
    epd.write_text(chess.Board().epd(id="initial") + "\n", encoding="utf-8")
    fen = temporary / "suite.fen"
    fen.write_text(chess.STARTING_FEN + "\n", encoding="utf-8")
    uci = temporary / "suite.uci"
    uci.write_text("e2e4 e7e5 g1f3\n", encoding="utf-8")
    native = temporary / "custom.json"
    native.write_text(json.dumps({"version": "test", "openings": [{
        "id": "king_gambit", "name": "King's Gambit", "start_fen": "startpos",
        "moves": ["e4", "e5", "f4"]}]}), encoding="utf-8")
    polyglot = temporary / "suite.bin"
    move = chess.Move.from_uci("e2e4")
    raw_move = (move.to_square & 7) | ((move.to_square >> 3) << 3) | \
               ((move.from_square & 7) << 6) | ((move.from_square >> 3) << 9)
    polyglot.write_bytes(struct.pack(">QHHI", chess.polyglot.zobrist_hash(chess.Board()),
                                     raw_move, 10, 0))
    assert len(load_openings(root / "data" / "openings" / "core.json")) >= 4
    assert len(load_openings(root / "tests" / "positions" / "analysis_sample.pgn")) == 1
    assert len(load_openings(epd)) == len(load_openings(fen)) == len(load_openings(uci)) == 1
    assert load_openings(native)[0].moves == ["e2e4", "e7e5", "f2f4"]
    assert load_openings(polyglot)[0].moves == ["e2e4"]

    decisive = [{"result": "0-1", "engine_a_color": "white",
                 "opening": {"id": str(index), "start_fen": "startpos", "moves_uci": []}}
                for index in range(8)]
    extreme = statistics(decisive, None, paired=False)
    assert extreme["score_rate"] == 0 and extreme["elo_confidence95"][0] == -1199.83

    # A/F: free paired game, both engines think from move one without a book.
    free = run(temporary / "free", "--games", "2", "--depth", "1", "--max-plies", "4",
               "--options-a", '{"OwnBook": false}', "--options-b", '{"OwnBook": false}')
    assert free["statistics"]["games"] == 2
    assert {game["engine_a_color"] for game in free["games"]} == {"white", "black"}
    assert all(game["opening"]["release_ply"] == 0 for game in free["games"])

    explored = run(temporary / "explored", "--games", "12", "--depth", "1", "--max-plies", "10",
                   "--exploration-plies", "4", "--exploration-depth", "1",
                   "--exploration-max-loss-cp", "200", "--seed", "17")
    prefixes = [tuple(game["opening"]["moves_uci"]) for game in explored["games"]]
    assert all(prefixes[i] == prefixes[i + 1] for i in range(0, 12, 2))
    assert len(set(prefixes)) > 1
    repeated = run(temporary / "repeated", "--games", "12", "--depth", "1", "--max-plies", "10",
                   "--exploration-plies", "4", "--exploration-depth", "1",
                   "--exploration-max-loss-cp", "200", "--seed", "17")
    assert prefixes == [tuple(game["opening"]["moves_uci"]) for game in repeated["games"]]
    assert all(game["moves"][0]["score_fen"] for game in explored["games"])

    # B: a named Grünfeld line with ChessBot A fixed as Black.
    named = run(temporary / "named", "--games", "1", "--depth", "1", "--max-plies", "13",
                "--color-mode", "a-black", "--openings",
                str(root / "data" / "openings" / "core.json"), "--opening-id",
                "gruenfeld_exchange_001")
    assert named["games"][0]["engine_a_color"] == "black"
    assert named["games"][0]["opening"]["eco"] == "D85"
    assert named["games"][0]["opening"]["version"] == "core-openings-v1"
    assert named["games"][0]["opening"]["release_ply"] == 12

    filtered = run(temporary / "filtered", "--games", "4", "--depth", "1", "--max-plies", "2",
                   "--openings", str(root / "data" / "openings" / "core.json"),
                   "--opening-ids", "italian_giuoco_001,scotch_001")
    assert {(game["opening"]["id"], game["engine_a_color"]) for game in filtered["games"]} == {
        ("italian_giuoco_001", "white"), ("italian_giuoco_001", "black"),
        ("scotch_001", "white"), ("scotch_001", "black")}

    # C: exact SAN/UCI prefix, validated before release.
    exact = run(temporary / "exact", "--games", "1", "--depth", "1", "--max-plies", "4",
                "--moves", "e4 e5 Nf3")
    assert exact["games"][0]["opening"]["moves_uci"] == ["e2e4", "e7e5", "g1f3"]

    # D: arbitrary legal FEN.
    custom_fen = "4k3/8/8/8/8/8/8/R3K3 w - - 0 1"
    arbitrary = run(temporary / "fen", "--games", "1", "--depth", "1", "--max-plies", "2",
                    "--fen", custom_fen)
    assert arbitrary["games"][0]["opening"]["start_fen"] == custom_fen

    # E: native own book after release, including provenance in move metadata.
    book_options = json.dumps({"BookFile": str((root / "tests" / "positions" /
                                                "test_book.tsv").resolve()),
                               "BookPolicy": "best", "OwnBook": True})
    booked = run(temporary / "book", "--games", "1", "--depth", "2", "--max-plies", "2",
                 "--options-a", book_options, "--options-b", book_options)
    assert booked["games"][0]["moves"][0]["uci"] == "e2e4"
    assert booked["games"][0]["moves"][0]["book"]

print("PASS: generic matches, scenarios A-F, openings, book metadata, PGN and experiment JSON")
