#!/usr/bin/env python3
"""Bind the accepted G1 terminal state into an offline-replayable checkpoint bundle.

The bundle intentionally proves only an accepted Newton terminal restart.  It
does not claim a mid-Krylov restart, a second hardware execution, or G1 closure.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

import build_g1_mgt_nonlinear_result_ir as result_gate  # noqa: E402
import run_g1_mgt_device_fgmres as device_gate  # noqa: E402
from g1_receipt_provenance import (  # noqa: E402
    build_provenance,
    validate_provenance,
)
from release_evidence_metadata import file_sha256  # noqa: E402
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts.nonlinear_result import (  # noqa: E402
    validate_nonlinear_result_manifest,
)
from structural_analysis.engine_v2.contracts.result_ir import (  # noqa: E402
    validate_diagnostic_ir_manifest,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_terminal_checkpoint_bundle_v2.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/g1_mgt_terminal_checkpoint_bundle_v2.schema.json"
)
VERSION = "g1-mgt-terminal-checkpoint-bundle.v2"
SOURCE_PATHS = (
    Path("scripts/build_g1_mgt_terminal_checkpoint_bundle_v2.py"),
    Path("scripts/g1_receipt_provenance.py"),
    SCHEMA,
    Path("tests/test_build_g1_mgt_terminal_checkpoint_bundle_v2.py"),
)
PARITY_BINDING_KEYS = (
    "model_ir_content_hash",
    "execution_plan_hash",
    "equation_scaling_hash",
    "reduced_csr_identity_hash",
    "operator_hash",
    "state_hash",
    "state_epoch",
    "material_state_bundle_hash",
    "integration_point_order_hash",
    "path_history_hash",
    "nonlinear_terminal_hash",
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("g1_checkpoint_bundle_json_object_required")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _artifact(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    path = _resolve(root, Path(item["path"]))
    if not path.is_file():
        raise ValueError(f"g1_checkpoint_bundle_artifact_missing:{item['path']}")
    if file_sha256(path) != item["file_sha256"]:
        raise ValueError(f"g1_checkpoint_bundle_artifact_hash_mismatch:{item['path']}")
    if path.stat().st_size != item["byte_length"]:
        raise ValueError(f"g1_checkpoint_bundle_artifact_size_mismatch:{item['path']}")
    return {
        "path": item["path"],
        "byte_length": item["byte_length"],
        "file_sha256": item["file_sha256"],
    }


def build(
    *,
    root: Path = ROOT,
    generated_at: str | None = None,
    provenance_source_commit_sha: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic authority overlay from existing bound artifacts."""

    root = root.resolve()
    device = device_gate.validate(
        _read(root / device_gate.DEFAULT_OUT),
        root=root,
        current=True,
        artifacts=True,
    )
    result = result_gate.validate(
        _read(root / result_gate.DEFAULT_OUT),
        root=root,
        current=True,
        artifacts=True,
    )
    if result["source"]["fgmres_receipt_hash"] != device["receipt_hash"]:
        raise ValueError("g1_checkpoint_bundle_device_result_receipt_mismatch")

    hip = validate_nonlinear_result_manifest(
        _read(root / result_gate.DEFAULT_HIP_RESULT)
    )
    cpu = validate_nonlinear_result_manifest(
        _read(root / result_gate.DEFAULT_CPU_RESULT)
    )
    diagnostic = validate_diagnostic_ir_manifest(
        _read(root / result_gate.DEFAULT_DIAGNOSTIC)
    )
    shared_bindings = {key: hip["bindings"][key] for key in PARITY_BINDING_KEYS}
    if any(cpu["bindings"].get(key) != value for key, value in shared_bindings.items()):
        raise ValueError("g1_checkpoint_bundle_result_binding_parity_failed")
    for key in (
        "model_ir_content_hash",
        "execution_plan_hash",
        "operator_hash",
        "state_hash",
        "state_epoch",
        "equation_scaling_hash",
        "reduced_csr_identity_hash",
    ):
        if diagnostic["bindings"].get(key) != shared_bindings[key]:
            raise ValueError(f"g1_checkpoint_bundle_diagnostic_binding_mismatch:{key}")

    checkpoint_item = device["comparison"]["checkpoint_artifact"]
    checkpoint_path = _resolve(root, Path(checkpoint_item["path"]))
    _artifact(root, checkpoint_item)
    with np.load(checkpoint_path, allow_pickle=False) as replay:
        required = {
            "accepted_state_hash",
            "free_displacement_data_hash",
            "free_displacements_m",
            "equilibrium_operator_binding_hash",
            "load_scale",
            "model_source_sha256",
            "source_commit_sha",
        }
        if not required.issubset(replay.files):
            raise ValueError("g1_checkpoint_bundle_npz_fields_missing")
        free = np.ascontiguousarray(replay["free_displacements_m"], dtype="<f8")
        if str(replay["accepted_state_hash"]) != checkpoint_item["accepted_state_hash"]:
            raise ValueError("g1_checkpoint_bundle_state_hash_mismatch")
        if str(replay["free_displacement_data_hash"]) != array_data_hash(free):
            raise ValueError("g1_checkpoint_bundle_free_state_hash_mismatch")
        if (
            str(replay["equilibrium_operator_binding_hash"])
            != shared_bindings["execution_plan_hash"]
        ):
            raise ValueError("g1_checkpoint_bundle_execution_plan_hash_mismatch")
        if (
            str(replay["model_source_sha256"])
            != shared_bindings["model_ir_content_hash"]
        ):
            raise ValueError("g1_checkpoint_bundle_model_hash_mismatch")
        if (
            str(replay["source_commit_sha"])
            != device["source"]["repository_commit_sha"]
        ):
            raise ValueError("g1_checkpoint_bundle_source_commit_mismatch")
        if float(replay["load_scale"]) != 1.0:
            raise ValueError("g1_checkpoint_bundle_full_load_required")

    material = device["material_lifecycle"]
    committed_item = material["artifacts"]["committed"]
    _artifact(root, committed_item)
    material_bundle = material["material_state_bundle"]
    if (
        material_bundle["committed_bundle_hash"]
        != shared_bindings["material_state_bundle_hash"]
        or material_bundle["entry_count"] != result["terminal"]["material_entry_count"]
    ):
        raise ValueError("g1_checkpoint_bundle_material_binding_mismatch")

    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "partial",
        "contract_pass": True,
        "provenance": build_provenance(
            root,
            SOURCE_PATHS,
            source_commit_sha=provenance_source_commit_sha,
        ),
        "source": {
            "device_receipt_hash": device["receipt_hash"],
            "result_receipt_hash": result["receipt_hash"],
            "repository_commit_sha": device["source"]["repository_commit_sha"],
        },
        "checkpoint": {
            **_artifact(root, checkpoint_item),
            "accepted_state_hash": checkpoint_item["accepted_state_hash"],
            "free_displacement_data_hash": checkpoint_item[
                "free_displacement_data_hash"
            ],
            "load_factor": 1.0,
            "exact_npz_reload": True,
        },
        "material": {
            "committed_artifact": _artifact(root, committed_item),
            "committed_bundle_hash": material_bundle["committed_bundle_hash"],
            "integration_point_order_hash": shared_bindings[
                "integration_point_order_hash"
            ],
            "entry_count": material_bundle["entry_count"],
            "committed_epoch": material_bundle["committed_epoch"],
        },
        "solver_bindings": shared_bindings,
        "terminal_outputs": {
            "hip_result_hash": hip["result_hash"],
            "cpu_result_hash": cpu["result_hash"],
            "displacement_data_hash": hip["displacement_artifact"]["data_hash"],
            "diagnostic_hash": diagnostic["diagnostic_hash"],
        },
        "claims": {
            "accepted_newton_terminal_restart_bound": True,
            "material_state_restart_bound": True,
            "equation_scaling_bound": True,
            "reduced_csr_identity_bound": True,
            "path_history_bound": True,
            "diagnostic_ir_bound": True,
            "offline_replay_without_local_device_probe": True,
            "mid_krylov_restart": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "mid_krylov_restart_not_captured",
            "independent_gfx1100_hardware_not_available",
            "nonlinear_material_family_breadth_not_closed",
        ],
        "claim_boundary": (
            "This v2 bundle binds one accepted full-load Newton terminal state, "
            "its committed material bundle, equation scaling, reduced CSR identity, "
            "path history, ResultIR pair, and DiagnosticIR for exact offline replay. "
            "It is not a Krylov mid-iteration checkpoint, independent hardware "
            "attestation, nonlinear material-breadth proof, or G1 closure receipt."
        ),
    }
    payload["receipt_hash"] = _hash(payload)
    return payload


def validate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    current: bool = False,
    require_commit_bound: bool = False,
) -> dict[str, Any]:
    schema = _read(_resolve(root, SCHEMA))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _hash(payload):
        raise ValueError("g1_checkpoint_bundle_receipt_hash_mismatch")
    validate_provenance(
        payload["provenance"],
        root=root.resolve(),
        expected_paths=SOURCE_PATHS,
        require_commit_bound=require_commit_bound,
    )
    if current:
        expected = build(
            root=root,
            generated_at=payload["generated_at"],
            provenance_source_commit_sha=payload["provenance"]["source_commit_sha"],
        )
        if payload != expected:
            raise ValueError("g1_checkpoint_bundle_replay_mismatch")
    return payload


def write(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = build(root=root)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root, current=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    target = _resolve(ROOT, args.out)
    if args.check:
        validate(_read(target), root=ROOT, current=True, require_commit_bound=True)
        print("g1_mgt_terminal_checkpoint_bundle_v2_consistent")
        return 0
    payload = write(out=args.out)
    print(
        "partial | terminal_restart=true | material_restart=true | "
        f"hash={payload['receipt_hash']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
