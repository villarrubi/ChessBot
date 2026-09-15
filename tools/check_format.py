"""Check (or apply) the pinned clang-format style on project-owned C++ sources."""
import argparse
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fix", action="store_true")
parser.add_argument("--clang-format", default="clang-format")
args = parser.parse_args()
files = sorted(str(path) for folder in ("src", "tests") for path in (root / folder).rglob("*")
               if path.suffix in {".cpp", ".h"})
formatter = args.clang_format
if "/" in formatter or "\\" in formatter:
    formatter = str(Path(formatter).resolve(strict=True))
command = [formatter] + (["-i"] if args.fix else ["--dry-run", "--Werror"]) + files
subprocess.run(command, check=True, cwd=root)
