#!/usr/bin/env python3
"""Compatibility entry point for the bounded planar external V&V matrix."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# These compatibility wrappers must bootstrap the repository root before importing
# the shared implementation when executed directly from a clean checkout.
from scripts import build_bounded_planar_external_vv_matrix_core as _core  # noqa: E402
from scripts.generated_package_check import run_matrix_cli  # noqa: E402

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))


def main() -> int:
    return run_matrix_cli(_core)


if __name__ == "__main__":
    raise SystemExit(main())
