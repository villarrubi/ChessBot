"""Durable, append-only history for training and learning-cycle runs."""
from __future__ import annotations

import json
import os
import socket
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_PATH = ROOT / "build" / "training-history.jsonl"
TERMINAL_STATUSES = {"completed", "failed", "interrupted"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError, PermissionError):
        return False
    return True


def read_events(path: Path = DEFAULT_LOG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                # A power loss can leave a final partial line. Keep all prior events usable.
                continue
            if isinstance(value, dict) and value.get("run_id"):
                events.append(value)
    return events


def _append(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    # O_APPEND plus one write makes each small event independent of Python buffering.
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_RDWR, 0o644)
    try:
        # A power loss may have left a partial final JSON line. Separate it before
        # appending the recovery event so all later records remain readable.
        if os.lseek(descriptor, 0, os.SEEK_END) > 0:
            os.lseek(descriptor, -1, os.SEEK_END)
            if os.read(descriptor, 1) != b"\n":
                os.write(descriptor, b"\n")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def recover_stale_runs(path: Path = DEFAULT_LOG_PATH) -> list[str]:
    """Close runs whose process disappeared before it could write a terminal event."""
    events = read_events(path)
    states: dict[str, dict[str, Any]] = {}
    for event in events:
        run_id = str(event["run_id"])
        state = states.setdefault(run_id, {"run_id": run_id})
        state.update(event)
        if event.get("event") == "start":
            state["start"] = event
        elif event.get("event") in TERMINAL_STATUSES:
            state["terminal"] = event

    recovered: list[str] = []
    for run_id, state in states.items():
        if state.get("terminal") or state.get("event") != "progress" and state.get("event") != "start":
            continue
        pid = int(state.get("pid", 0))
        if _pid_alive(pid):
            continue
        start = state.get("start", state)
        _append(path, {
            "schema_version": 1,
            "event": "interrupted",
            "status": "interrupted",
            "run_id": run_id,
            "timestamp": now(),
            "pid": pid,
            "host": socket.gethostname(),
            "output_dir": start.get("output_dir"),
            "stage": state.get("stage"),
            "progress": state.get("progress"),
            "reason": "process disappeared before a terminal event; possible crash, reboot or forced termination",
        })
        recovered.append(run_id)
    return recovered


def runs(path: Path = DEFAULT_LOG_PATH) -> list[dict[str, Any]]:
    """Return one current summary per run, preserving log order."""
    summaries: dict[str, dict[str, Any]] = {}
    for event in read_events(path):
        run_id = str(event["run_id"])
        summary = summaries.setdefault(run_id, {
            "run_id": run_id,
            "status": "running",
            "kind": event.get("kind"),
            "started_at": event.get("timestamp"),
            "output_dir": event.get("output_dir"),
            "stage": None,
            "progress": None,
        })
        if event.get("event") == "start":
            summary.update({
                "kind": event.get("kind"),
                "started_at": event.get("timestamp"),
                "output_dir": event.get("output_dir"),
                "command": event.get("command"),
            })
        elif event.get("event") == "progress":
            summary.update({"stage": event.get("stage"), "progress": event.get("progress")})
        elif event.get("event") in TERMINAL_STATUSES:
            summary.update({
                "status": event.get("status", event.get("event")),
                "finished_at": event.get("timestamp"),
                "error": event.get("error"),
                "reason": event.get("reason"),
                "details": event.get("details", {}),
            })
    return list(summaries.values())


class TrainingLogger:
    """Small durable event writer shared by direct NNUE training and full cycles."""

    def __init__(self, kind: str, output_dir: Path | None = None,
                 command: list[str] | None = None, path: Path = DEFAULT_LOG_PATH,
                 metadata: dict[str, Any] | None = None):
        self.path = path.resolve()
        self.run_id = uuid.uuid4().hex
        self.kind = kind
        self.output_dir = str(output_dir.resolve()) if output_dir else None
        self.command = command or [sys.executable, *sys.argv]
        self.metadata = metadata or {}
        self.started_at = now()
        self._closed = False

    def _event(self, event: str, **values: Any) -> None:
        payload: dict[str, Any] = {
            "schema_version": 1,
            "event": event,
            "run_id": self.run_id,
            "kind": self.kind,
            "timestamp": now(),
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "output_dir": self.output_dir,
        }
        payload.update(values)
        _append(self.path, payload)

    def start(self) -> None:
        self._event("start", status="running", command=self.command, metadata=self.metadata)

    def progress(self, stage: str, progress: dict[str, Any] | None = None) -> None:
        if not self._closed:
            self._event("progress", stage=stage, progress=progress or {})

    def finish(self, status: str, error: str | None = None,
               details: dict[str, Any] | None = None) -> None:
        if self._closed:
            return
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"invalid terminal training status: {status}")
        self._event(status, status=status, error=error, details=details or {})
        self._closed = True
