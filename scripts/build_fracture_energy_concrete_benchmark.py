#!/usr/bin/env python3
"""Build or validate the source-bound fracture-energy concrete receipt."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.benchmark.fracture_energy_concrete import (  # noqa: E402
    build_fracture_energy_concrete_mesh_objectivity_benchmark,
    validate_fracture_energy_concrete_mesh_objectivity_benchmark,
)


DEFAULT_OUT = Path(
    "artifacts/benchmarks/fracture_energy_concrete_mesh_objectivity.json"
)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"nonfinite_json_constant:{value}")

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=reject_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("fracture_energy_artifact_root_invalid")
    return payload


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    encoded = (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    output = _resolve(args.out)
    if args.check:
        payload = validate_fracture_energy_concrete_mesh_objectivity_benchmark(
            _read_json(output),
            repo_root=ROOT,
            require_current_sources=True,
            rerun=True,
        )
        print(
            "fracture_energy_concrete_consistent"
            f" | artifact={payload['artifact_hash']}"
            f" | sources={payload['source']['source_set_hash']}"
        )
        return 0

    payload = build_fracture_energy_concrete_mesh_objectivity_benchmark(repo_root=ROOT)
    _write_atomic(output, payload)
    print(
        f"{payload['status']}"
        f" | meshes={len(payload['mesh_cases'])}/3"
        f" | artifact={payload['artifact_hash']}"
        f" | sources={payload['source']['source_set_hash']}"
    )
    return 0 if payload["contract_pass"] is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
