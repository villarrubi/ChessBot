"""Small cross-platform helpers for limiting a child process to CPU cores."""
from __future__ import annotations

import ctypes
import os


MAX_AFFINITY_CORES = 64


def validate_cores(cores: int) -> int:
    available = os.cpu_count() or 1
    maximum = min(available, MAX_AFFINITY_CORES)
    if cores < 1 or cores > maximum:
        raise ValueError(f"cores must be between 1 and {maximum}")
    return cores


def set_process_affinity(pid: int, cores: int | None) -> None:
    """Restrict *pid* to the first ``cores`` logical processors."""
    if cores is None:
        return
    validate_cores(cores)
    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        kernel32.SetProcessAffinityMask.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int
        process = kernel32.OpenProcess(0x0200 | 0x1000, False, pid)
        if not process:
            error = ctypes.get_last_error()
            raise OSError(error, f"OpenProcess failed for pid {pid}")
        try:
            mask = (1 << cores) - 1
            if not kernel32.SetProcessAffinityMask(process, ctypes.c_size_t(mask)):
                error = ctypes.get_last_error()
                raise OSError(error, f"SetProcessAffinityMask failed for pid {pid}")
        finally:
            kernel32.CloseHandle(process)
    elif hasattr(os, "sched_setaffinity"):
        available = sorted(os.sched_getaffinity(0))
        os.sched_setaffinity(pid, set(available[:cores]))
