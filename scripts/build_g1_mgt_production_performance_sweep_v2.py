#!/usr/bin/env python3
"""Validate repeated same-workload G1 production performance samples."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    sys.path.insert(0, str(candidate))

from g1_receipt_provenance import (  # noqa: E402
    build_provenance,
    validate_provenance,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_production_performance_sweep_v2.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/g1_mgt_production_performance_sweep_v2.schema.json"
)
VERSION = "g1-mgt-production-performance-sweep.v2"
SAMPLE_VERSION = "g1-mgt-production-performance-sample.v2"
ARCHITECTURES = ("gfx1030", "gfx1100")
KPI_FIELDS = (
    "krylov_iteration_count",
    "matvec_count",
    "preconditioner_apply_count",
    "h2d_bytes",
    "d2h_bytes",
    "mid_step_d2h_bytes",
    "peak_vram_bytes",
    "checkpoint_overhead_seconds",
    "end_to_end_wall_seconds",
    "cpu_baseline_wall_seconds",
    "speedup_vs_cpu",
)
SOURCE_PATHS = (
    Path("scripts/build_g1_mgt_production_performance_sweep_v2.py"),
    Path("scripts/g1_receipt_provenance.py"),
    SCHEMA,
    Path("tests/test_build_g1_mgt_production_performance_sweep_v2.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("g1_performance_json_object_required")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _validate_numeric_sample_fields(sample: dict[str, Any]) -> None:
    for name in KPI_FIELDS:
        value = sample[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            raise ValueError(f"g1_performance_sample_{name}_invalid")
    for name in (
        "krylov_iteration_count",
        "matvec_count",
        "preconditioner_apply_count",
        "h2d_bytes",
        "d2h_bytes",
        "peak_vram_bytes",
        "mid_step_d2h_bytes",
    ):
        if type(sample[name]) is not int:
            raise ValueError(f"g1_performance_sample_{name}_integer_required")


def validate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    required = {
        "schema_version",
        "receipt_hash",
        "architecture",
        "source_commit_sha",
        "wheel_sha256",
        "workload_hash",
        "checkpoint_sha256",
        "terminal_parity_digest",
        "repetition_index",
        "production_mgt_workload",
        "synthetic_fixture",
        "mid_step_d2h_bytes",
        *KPI_FIELDS,
    }
    if set(sample) != required:
        raise ValueError("g1_performance_sample_field_set_invalid")
    if sample["schema_version"] != SAMPLE_VERSION:
        raise ValueError("g1_performance_sample_schema_invalid")
    if sample["architecture"] not in ARCHITECTURES:
        raise ValueError("g1_performance_sample_architecture_invalid")
    if not (
        isinstance(sample["source_commit_sha"], str)
        and len(sample["source_commit_sha"]) == 40
        and all(c in "0123456789abcdef" for c in sample["source_commit_sha"])
    ):
        raise ValueError("g1_performance_sample_source_commit_invalid")
    for name in (
        "wheel_sha256",
        "workload_hash",
        "checkpoint_sha256",
        "terminal_parity_digest",
    ):
        if not _is_hash(sample[name]):
            raise ValueError(f"g1_performance_sample_{name}_invalid")
    if type(sample["repetition_index"]) is not int or sample["repetition_index"] < 0:
        raise ValueError("g1_performance_sample_repetition_invalid")
    if (
        type(sample["production_mgt_workload"]) is not bool
        or type(sample["synthetic_fixture"]) is not bool
    ):
        raise ValueError("g1_performance_sample_workload_flags_invalid")
    if sample["synthetic_fixture"] and sample["production_mgt_workload"]:
        raise ValueError("g1_performance_synthetic_fixture_cannot_claim_production")
    _validate_numeric_sample_fields(sample)
    if sample["mid_step_d2h_bytes"] != 0:
        raise ValueError("g1_performance_sample_mid_step_d2h_nonzero")
    if sample["receipt_hash"] != _hash(sample):
        raise ValueError("g1_performance_sample_hash_mismatch")
    return sample


def create_sample(**values: Any) -> dict[str, Any]:
    payload = {"schema_version": SAMPLE_VERSION, "receipt_hash": "", **values}
    _validate_numeric_sample_fields(payload)
    payload["receipt_hash"] = _hash(payload)
    return validate_sample(payload)


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("g1_performance_percentile_empty")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "sample_count": len(rows),
        "kpis": {
            name: {
                "p50": statistics.median(float(row[name]) for row in rows),
                "p95": _percentile((float(row[name]) for row in rows), 0.95),
            }
            for name in KPI_FIELDS
        },
        "mid_step_d2h_bytes_max": max(row["mid_step_d2h_bytes"] for row in rows),
    }


def build(
    *,
    samples: Sequence[dict[str, Any]] = (),
    root: Path = ROOT,
    generated_at: str | None = None,
    provenance_source_commit_sha: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    rows = sorted(
        (validate_sample(dict(sample)) for sample in samples),
        key=lambda row: (
            row["architecture"],
            row["repetition_index"],
            row["receipt_hash"],
        ),
    )
    production = [
        row
        for row in rows
        if row["production_mgt_workload"] and not row["synthetic_fixture"]
    ]
    synthetic_count = len(rows) - len(production)
    grouped = {
        architecture: [row for row in production if row["architecture"] == architecture]
        for architecture in ARCHITECTURES
    }
    for architecture, arch_rows in grouped.items():
        indices = [row["repetition_index"] for row in arch_rows]
        if len(indices) != len(set(indices)):
            raise ValueError(f"g1_performance_duplicate_repetition:{architecture}")
    identity_fields = (
        "source_commit_sha",
        "wheel_sha256",
        "workload_hash",
        "checkpoint_sha256",
        "terminal_parity_digest",
    )
    identity = {
        name: sorted({row[name] for row in production}) for name in identity_fields
    }
    identity_consistent = bool(production) and all(
        len(values) == 1 for values in identity.values()
    )
    sufficient_repetitions = all(len(grouped[arch]) >= 3 for arch in ARCHITECTURES)
    cross_device_ready = (
        identity_consistent and sufficient_repetitions and synthetic_count == 0
    )
    blockers: list[str] = []
    if not identity_consistent:
        blockers.append("same_source_wheel_workload_checkpoint_parity_not_proven")
    if not sufficient_repetitions:
        blockers.append("three_repetitions_per_architecture_not_available")
    if synthetic_count:
        blockers.append("synthetic_samples_excluded_from_production_sweep")
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "ready" if cross_device_ready else "partial",
        "contract_pass": True,
        "provenance": build_provenance(
            root,
            SOURCE_PATHS,
            source_commit_sha=provenance_source_commit_sha,
        ),
        "sample_count": len(rows),
        "production_sample_count": len(production),
        "synthetic_sample_count": synthetic_count,
        "samples": rows,
        "sample_receipt_hashes": sorted(row["receipt_hash"] for row in rows),
        "identity": {
            name: values[0] if len(values) == 1 else None
            for name, values in identity.items()
        },
        "architecture_summaries": {
            architecture: _summary(arch_rows) if arch_rows else None
            for architecture, arch_rows in grouped.items()
        },
        "claims": {
            "production_mgt_workload_only": bool(production) and synthetic_count == 0,
            "same_source_wheel_workload_checkpoint": identity_consistent,
            "terminal_parity_digest_bound": identity_consistent,
            "three_repetitions_per_architecture": sufficient_repetitions,
            "cross_device_production_performance_sweep": cross_device_ready,
            "synthetic_fixture_promoted": False,
            "g1_closure": False,
        },
        "blockers_remaining": blockers,
        "claim_boundary": (
            "This performance gate accepts only repeated actual production-MGT "
            "samples with identical source, wheel, workload, checkpoint, and terminal "
            "parity digest. It reports p50/p95 Krylov, matvec, preconditioner, transfer, "
            "VRAM, checkpoint, wall-time, and speedup KPIs. Synthetic fixtures are "
            "excluded and can never establish the production sweep or G1 closure."
        ),
    }
    payload["receipt_hash"] = _hash(payload)
    return payload


def validate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    require_commit_bound: bool = False,
) -> dict[str, Any]:
    schema = _read(_resolve(root, SCHEMA))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload):
        raise ValueError("g1_performance_sweep_receipt_hash_mismatch")
    validate_provenance(
        payload["provenance"],
        root=root.resolve(),
        expected_paths=SOURCE_PATHS,
        require_commit_bound=require_commit_bound,
    )
    if payload["claims"]["synthetic_fixture_promoted"] is not False:
        raise ValueError("g1_performance_synthetic_promotion_forbidden")
    expected = build(
        samples=payload["samples"],
        root=root,
        generated_at=payload["generated_at"],
        provenance_source_commit_sha=payload["provenance"]["source_commit_sha"],
    )
    if payload != expected:
        raise ValueError("g1_performance_sweep_replay_mismatch")
    return payload


def write(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = build(root=root)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    target = _resolve(ROOT, args.out)
    if args.check:
        validate(_read(target), root=ROOT, require_commit_bound=True)
        print("g1_mgt_production_performance_sweep_v2_consistent")
        return 0
    payload = write(out=args.out)
    print(
        f"{payload['status']} | production_samples=0 | cross_device_performance=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
