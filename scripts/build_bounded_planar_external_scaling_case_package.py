#!/usr/bin/env python3
"""Compatibility entry point for the bounded planar scaling package."""

from scripts import build_bounded_planar_external_scaling_case_package_core as _core
from scripts.generated_package_check import run_package_cli

for _name in dir(_core):
    if not _name.startswith("__"):
        globals().setdefault(_name, getattr(_core, _name))


def main() -> int:
    return run_package_cli(_core)


if __name__ == "__main__":
    raise SystemExit(main())
