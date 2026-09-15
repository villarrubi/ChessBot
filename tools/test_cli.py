"""Exercise the actual command-line boundary, including recovery after invalid requests."""
import argparse
import json
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--engine", type=Path, required=True)
args = parser.parse_args()
engine = str(args.engine.resolve(strict=True))

def run(*arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([engine, *arguments], input=input_text, text=True,
                          capture_output=True, timeout=30)

for arguments in [("unknown",), ("perft", "-1"), ("perft", "2x"), ("divide", "0"),
                  ("inspect", "--fen", "invalid"), ("inspect", "--moves", "e2e5"),
                  ("inspect", "--fen"), ("validate-stream", "extra")]:
    result = run(*arguments)
    assert result.returncode == 2 and "error:" in result.stderr and not result.stdout, result

result = run("inspect", "--moves", "e2e4 e7e5")
assert result.returncode == 0, result.stderr
assert json.loads(result.stdout)["fen"] == "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2"
assert run("perft", "0").stdout.strip() == "1"
assert run("perft", "3").stdout.strip() == "8902"
divide = run("divide", "3")
assert divide.returncode == 0 and "total: 8902" in divide.stdout
assert sum(int(line.split(": ")[1]) for line in divide.stdout.splitlines()[:-1]) == 8902
fen = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
result = run("validate-stream", input_text=f'invalid\n{fen}\tbad"move\n{fen}\n')
responses = [json.loads(line) for line in result.stdout.splitlines()]
assert result.returncode == 0 and len(responses) == 3
assert "error" in responses[0] and "error" in responses[1]
assert responses[2]["status"] == "insufficient_material"
print("PASS: CLI input validation, JSON error recovery, FEN, PERFT and divide")
