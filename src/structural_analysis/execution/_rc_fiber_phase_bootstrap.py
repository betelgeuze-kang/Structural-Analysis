"""Linux direct-child death protection, before any solver or package imports.

PDEATHSIG protects this direct child, not descendants escaping its process group.
The expected-parent check closes the parent-death-before-arming race. No preexec
callback is used: the durable worker already has a heartbeat thread.
"""

from __future__ import annotations

import ctypes
import os
import json
from pathlib import Path
import runpy
import signal
import sys


def _arm_parent_death_signal(expected_parent_pid: int) -> None:
    if sys.platform != "linux" or type(expected_parent_pid) is not int:
        raise RuntimeError("RC phase parent-death protection requires Linux")
    if expected_parent_pid <= 0:
        raise RuntimeError("RC phase expected parent must be a positive worker PID")
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    prctl.restype = ctypes.c_int
    if prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    if os.getppid() != expected_parent_pid:
        os._exit(125)


def _main() -> None:
    if len(sys.argv) != 5:
        raise RuntimeError(
            "RC phase bootstrap requires parent, source, entry and dependencies"
        )
    _arm_parent_death_signal(int(sys.argv[1]))
    source = Path(sys.argv[2]).resolve(strict=True)
    entry = Path(sys.argv[3]).resolve(strict=True)
    if entry != source / "structural_analysis/execution/rc_fiber_phase_supervisor.py":
        raise RuntimeError("RC phase bootstrap entry differs from its source root")
    dependencies = json.loads(sys.argv[4])
    if (
        type(dependencies) is not list
        or len(dependencies) > 3
        or any(
            type(value) is not str
            or len(value) > 4096
            or not Path(value).is_absolute()
            or not Path(value).is_dir()
            for value in dependencies
        )
    ):
        raise RuntimeError("RC phase dependency roots invalid")
    site_start = next(
        (
            index
            for index, value in enumerate(sys.path)
            if "site-packages" in Path(value).parts
            or "dist-packages" in Path(value).parts
        ),
        len(sys.path),
    )
    sys.path[site_start:site_start] = dependencies
    sys.path.insert(0, str(source))
    runpy.run_path(str(entry), run_name="__main__")


if __name__ == "__main__":
    _main()
