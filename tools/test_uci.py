"""End-to-end checks for the asynchronous UCI protocol."""
import argparse
import queue
import subprocess
import threading
import time
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()

process = subprocess.Popen(
    [str(args.engine.resolve(strict=True))],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)
lines: queue.Queue[str] = queue.Queue()


def reader() -> None:
    assert process.stdout
    for line in process.stdout:
        lines.put(line.rstrip("\r\n"))


threading.Thread(target=reader, daemon=True).start()


def send(command: str) -> None:
    assert process.stdin
    process.stdin.write(command + "\n")
    process.stdin.flush()


def wait_for(predicate, timeout: float = 10.0) -> list[str]:
    received = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            line = lines.get(timeout=max(0.01, deadline - time.monotonic()))
        except queue.Empty:
            break
        received.append(line)
        if predicate(line):
            return received
    raise AssertionError(f"Timed out; received: {received}")


try:
    send("uci")
    greeting = wait_for(lambda line: line == "uciok")
    assert any(line == "id name ChessBot 0.10.0" for line in greeting)
    for option in ("Hash", "Threads", "Move Overhead", "OwnBook", "BookFile", "BookPolicy",
                   "BookSeed", "MultiPV", "SearchProfile", "Evaluation", "EvalFile", "NNUE",
                   "NNUEFile"):
        assert any(line.startswith(f"option name {option} ") for line in greeting), option

    send("isready")
    assert wait_for(lambda line: line == "readyok")[-1] == "readyok"
    send("setoption name Hash value 16")
    send("setoption name Move Overhead value 1")
    send("setoption name Evaluation value Basic")
    send("setoption name Evaluation value Positional")
    send("setoption name EvalFile value data/evaluation/hce-default-v1.params")
    send("setoption name EvalFile value data/evaluation/missing.params")
    assert "cannot open file" in wait_for(lambda line: "info string error:" in line)[-1]
    send("setoption name EvalFile value <empty>")
    send("setoption name AnalysisDetail value Full")
    send("setoption name NNUE value true")
    assert "requires a loaded NNUEFile" in wait_for(lambda line: "info string error:" in line)[-1]
    send("position broken")
    assert "position requires" in wait_for(lambda line: "info string error:" in line)[-1]

    send("position startpos moves e2e4 e7e5")
    send("eval")
    evaluation = wait_for(lambda line: line.startswith("info string eval "))[-1]
    assert "side_to_move" in evaluation and "material" in evaluation and "phase" in evaluation
    send("go depth 3")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=30)
    assert any(line.startswith("info string eval ") for line in result), result
    assert any(line.startswith("info depth 3 ") for line in result), result
    assert result[-1].split()[1] != "0000"

    send("setoption name BookFile value tests/positions/test_book.tsv")
    send("setoption name BookPolicy value best")
    send("setoption name OwnBook value true")
    send("position startpos")
    send("go depth 8")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=5)
    assert any("info string book move e2e4" in line and "version test-book-v1" in line
               for line in result), result
    assert result[-1].split()[1] == "e2e4"
    send("setoption name OwnBook value false")

    send("setoption name MultiPV value 3")
    send("position startpos")
    send("go depth 2")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=30)
    final_lines = [line for line in result if line.startswith("info depth 2 ")]
    assert {f" multipv {index} " for index in (1, 2, 3)} <= {
        next(part for part in (f" multipv {index} " for index in (1, 2, 3)) if part in line)
        for line in final_lines
    }
    send("setoption name MultiPV value 1")
    send("go depth 2 searchmoves e2e4")
    assert wait_for(lambda line: line.startswith("bestmove "), timeout=30)[-1].split()[1] == "e2e4"
    send("go depth 2 searchmoves e2e5")
    assert "illegal searchmove" in wait_for(lambda line: "info string error:" in line)[-1]

    send("position fen 7k/8/6K1/8/8/8/5Q2/8 w - - 0 1")
    send("go depth 2")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=30)
    assert any(" score mate 1 " in line for line in result), result
    assert result[-1].split()[1] == "f2f8"

    send("position startpos")
    started = time.monotonic()
    send("go movetime 60")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=5)
    assert time.monotonic() - started < 2.0
    assert result[-1].split()[1] != "0000"

    send("go nodes 100")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=5)
    assert result[-1].split()[1] != "0000"

    send("go wtime 100 btime 100 winc 5 binc 5 movestogo 20")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=5)
    assert result[-1].split()[1] != "0000"

    send("go wtime 0 btime 0")
    result = wait_for(lambda line: line.startswith("bestmove "), timeout=2)
    assert result[-1].split()[1] != "0000"

    send("go wtime 100")
    assert "supplied together" in wait_for(lambda line: "info string error:" in line)[-1]

    for _ in range(10):
        send("go infinite")
        send("stop")
        assert wait_for(lambda line: line.startswith("bestmove "), timeout=2)[-1].split()[1] != "0000"

    send("go infinite")
    wait_for(lambda line: line.startswith("info depth "), timeout=5)
    send("isready")
    assert wait_for(lambda line: line == "readyok", timeout=2)[-1] == "readyok"
    send("stop")
    assert wait_for(lambda line: line.startswith("bestmove "), timeout=5)[-1].split()[1] != "0000"

    send("debug on")
    send("unknown-test-command")
    assert "ignored command" in wait_for(lambda line: "ignored command" in line)[-1]
    send("quit")
    assert process.wait(timeout=5) == 0
    assert not process.stderr.read(), "Unexpected stderr output"
    print("PASS: UCI handshake, options, errors, eval, depth/nodes/time/infinite search and stop")
finally:
    if process.poll() is None:
        process.kill()
