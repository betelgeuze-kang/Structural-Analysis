"""Read-only host inventory, not an AMD execution/performance certificate.

No external executable or kernel is launched. Device nodes and installed tools
are observations only. A driver, kernel and complete solver must each be tested
on actual hardware before any GPU profile is admitted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil


def _small_text(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            raw = stream.read(257)
        if len(raw) > 256:
            return None
        return raw.decode("ascii").strip()
    except (OSError, UnicodeError):
        return None


def inspect_local_runtime(
    *, sysfs_root: Path = Path("/sys/class/drm"), dev_root: Path = Path("/dev")
) -> dict:
    devices = []
    if sysfs_root.is_dir():
        for card in sorted(sysfs_root.iterdir()):
            if not re.fullmatch(r"card[0-9]+", card.name):
                continue
            vendor = _small_text(card / "device/vendor")
            if vendor is None or vendor.lower() != "0x1002":
                continue
            device = _small_text(card / "device/device")
            if device is not None and not re.fullmatch(r"0x[0-9a-fA-F]{4}", device):
                device = None
            devices.append(
                {"card": card.name, "vendor_id": "0x1002", "device_id": device}
            )
    node = dev_root / "kfd"
    return {
        "schema_version": "local-structural-runtime-inventory.v1",
        "platform": platform.system(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "amd_display_devices": devices,
        "kfd_node_present": node.exists(),
        "kfd_read_write_access": node.exists() and os.access(node, os.R_OK | os.W_OK),
        "tool_paths": {
            name: shutil.which(name) for name in ("hipcc", "rocminfo", "amd-smi")
        },
        "hardware_kernel_executed": False,
        "gpu_numerical_parity_verified": False,
        "gpu_performance_measured": False,
        "qualified_gpu_solver_profiles": [],
        "automatic_gpu_selection": False,
        "boundary": "Inventory does not qualify a GPU, driver, precision mode or whole solver. No model or solver setting is changed.",
    }


def main() -> int:
    print(
        json.dumps(inspect_local_runtime(), allow_nan=False, sort_keys=True, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
