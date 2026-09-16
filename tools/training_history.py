"""Show the durable history of ChessBot training runs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from training_log import DEFAULT_LOG_PATH, recover_stale_runs, runs


LABELS = {
    "completed": "COMPLETED",
    "failed": "FAILED",
    "interrupted": "INTERRUPTED",
    "running": "RUNNING",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    recover_stale_runs(args.log_file)
    values = runs(args.log_file)
    if args.as_json:
        print(json.dumps(values, indent=2, ensure_ascii=False))
        return
    if not values:
        print(f"No hay entrenamientos registrados. Log: {args.log_file.resolve()}")
        return
    print(f"Log: {args.log_file.resolve()}")
    for value in reversed(values):
        started = str(value.get("started_at", ""))[:19].replace("T", " ")
        kind = str(value.get("kind", "training"))
        status = LABELS.get(str(value.get("status")), str(value.get("status")))
        stage = f" | fase: {value['stage']}" if value.get("stage") else ""
        output = value.get("output_dir") or "(sin carpeta de salida)"
        print(f"{started} | {status:<11} | {kind:<5}{stage} | {output}")
        if value.get("error") or value.get("reason"):
            print(f"  detalle: {value.get('error') or value.get('reason')}")


if __name__ == "__main__":
    main()
