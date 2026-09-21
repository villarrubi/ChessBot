"""Exercise live output, preemption, cancellation and full PGN/FEN exports."""
import argparse
import json
import queue
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import chess
import chess.pgn


class Session:
    def __init__(self, engine, directory, request):
        self.directory = directory
        path = directory / "request.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", "tools/analysis_session.py", "--live",
             "--engine", str(engine), "--request", str(path), "--output-dir", str(directory)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1)
        self.events = queue.Queue()
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.process.stdout:
            if line.startswith("{"):
                self.events.put(json.loads(line))

    def command(self, **command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def until(self, predicate, seconds=15):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            try:
                event = self.events.get(timeout=0.1)
            except queue.Empty:
                if self.process.poll() is not None:
                    raise AssertionError(self.process.stderr.read()) from None
                continue
            if predicate(event):
                return event
        raise AssertionError("Timed out waiting for live event")

    def finish(self):
        self.process.wait(timeout=10)
        assert self.process.returncode == 0, self.process.stderr.read()
        return json.loads((self.directory / "analysis.json").read_text(encoding="utf-8"))

    def close(self):
        if self.process.poll() is None:
            self.command(command="cancel")
            self.process.wait(timeout=10)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        folder = Path(temp)
        live = Session(args.engine.resolve(), folder,
                       {"kind": "pgn", "text": "1. e4 e5 2. Nf3 *", "depth": 20,
                        "multipv": 3, "threads": 2})
        try:
            initial = live.until(lambda e: e["event"] == "init")
            rows = initial["payload"]["games"][0]["moves"]
            assert len(rows) == 3 and all(not row["complete"] for row in rows)
            assert rows[2]["move_uci"] == "g1f3"
            live.until(lambda e: e["event"] == "record" and e["ply"] == 3 and e["record"]["candidates"])
            started = time.monotonic()
            live.command(command="focus", game=0, ply=1)
            live.until(lambda e: e["event"] == "status" and e["ply"] == 1, seconds=5)
            assert time.monotonic() - started < 5
            partial = live.until(lambda e: e["event"] == "record" and e["ply"] == 1 and e["record"]["candidates"])
            assert not partial["record"]["complete"]
            assert partial["record"]["classification"] == "provisional"
            for variation in partial["record"]["candidates"]:
                board = chess.Board(partial["record"]["fen_before"])
                assert variation["positions"][0] == board.fen()
                for index, name in enumerate(variation["pv_uci"], 1):
                    board.push_uci(name)
                    assert variation["positions"][index] == board.fen()
            live.command(command="focus", game=0, ply=2)
            live.until(lambda e: e["event"] == "status" and e["ply"] == 2, seconds=5)
            live.command(command="cancel")
            assert not live.until(lambda e: e["event"] == "done")["complete"]
            payload = live.finish()
            assert not payload["complete"] and len(payload["games"][0]["moves"]) == 3
            assert any(row["candidates"] for row in payload["games"][0]["moves"])
        finally:
            live.close()
        complete = Session(args.engine.resolve(), folder,
                           {"kind": "pgn", "text": "1. e4 e5 2. Nf3 *", "depth": 3, "threads": 2})
        try:
            assert complete.until(lambda e: e["event"] == "done")["complete"]
            payload = complete.finish()
            assert all(row["complete"] for row in payload["games"][0]["moves"])
            with (folder / "annotated.pgn").open(encoding="utf-8") as handle:
                assert len(list(chess.pgn.read_game(handle).mainline_moves())) == 3
        finally:
            complete.close()
        fen = Session(args.engine.resolve(), folder,
                      {"kind": "fen", "text": chess.STARTING_FEN, "depth": 2, "multipv": 3})
        try:
            initial = fen.until(lambda e: e["event"] == "init")["payload"]["games"][0]["moves"][0]
            assert initial["move_uci"] is None and initial["fen_after"] == chess.STARTING_FEN
            assert fen.until(lambda e: e["event"] == "done")["complete"]
            row = fen.finish()["games"][0]["moves"][0]
            assert row["mode"] == "position" and row["move_uci"] == row["best"]["move"]
            assert row["played"] == row["best"]
        finally:
            fen.close()
        multi = Session(args.engine.resolve(), folder,
                        {"kind": "pgn", "text": '[Event "First"]\n\n1. a3 *\n\n[Event "Second"]\n\n1. h3 *',
                         "depth": 3, "multipv": 1})
        try:
            assert multi.until(lambda e: e["event"] == "done")["complete"]
            games = multi.finish()["games"]
            assert len(games) == 2
            for game, move in zip(games, ("a2a3", "h2h3"), strict=True):
                row = game["moves"][0]
                assert row["complete"] and row["played"]["move"] == move
                assert row["played"]["score"]["cp"] is not None
        finally:
            multi.close()
        terminal = Session(args.engine.resolve(), folder,
                           {"kind": "fen", "text": "7k/5K2/6Q1/8/8/8/8/8 b - - 1 1", "depth": 2})
        try:
            assert terminal.until(lambda e: e["event"] == "done")["complete"]
            game = terminal.finish()["games"][0]
            assert game["moves"] == [] and "terminal" in game
        finally:
            terminal.close()
    print("PASS: live initial board, partial lines, priority switching, cancellation and PGN/FEN exports")


if __name__ == "__main__":
    main()
