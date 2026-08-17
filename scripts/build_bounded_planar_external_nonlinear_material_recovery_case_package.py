#!/usr/bin/env python3
"""Compatibility entry point for the bounded planar nonlinear package."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_bounded_planar_external_nonlinear_material_recovery_case_package_core as _core
from scripts.generated_package_check import run_package_cli

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))


def main() -> int:
    return run_package_cli(_core)


if __name__ == "__main__":
    raise SystemExit(main())
