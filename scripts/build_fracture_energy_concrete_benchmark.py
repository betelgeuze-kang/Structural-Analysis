#!/usr/bin/env python3
"""Build or check the bounded fracture-energy concrete benchmark receipt."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile

from structural_analysis.benchmark.fracture_energy_concrete import (
    build_fracture_energy_concrete_mesh_objectivity_benchmark,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    ROOT / "artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json"
)


def _bytes() -> bytes:
    payload = build_fracture_energy_concrete_mesh_objectivity_benchmark()
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = _bytes()
    output = args.out.resolve()
    if args.check:
        if not output.is_file() or output.read_bytes() != expected:
            print(f"fracture-energy benchmark drift: {output}")
            return 1
        print("fracture-energy benchmark: PASS")
        return 0
    _write_atomic(output, expected)
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
