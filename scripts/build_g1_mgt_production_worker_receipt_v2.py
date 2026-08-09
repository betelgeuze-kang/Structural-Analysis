#!/usr/bin/env python3
"""Build the additive G1 production-worker v2 offline replay receipt.

The receipt compares terminal authority projections, not backend-specific full
ResultIR hashes.  Local device discovery belongs to capture time; this builder
replays already-bound artifacts and cannot promote an unsigned hardware run.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

import build_g1_mgt_hardware_envelope as envelope_gate  # noqa: E402
import build_g1_mgt_nonlinear_result_ir as result_gate  # noqa: E402
import build_g1_mgt_terminal_checkpoint_bundle_v2 as checkpoint_gate  # noqa: E402
import run_g1_mgt_device_fgmres as device_gate  # noqa: E402
from g1_receipt_provenance import (  # noqa: E402
    build_provenance,
    validate_provenance,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash  # noqa: E402
from structural_analysis.engine_v2.contracts.nonlinear_result import (  # noqa: E402
    validate_nonlinear_result_manifest,
)
from structural_analysis.engine_v2.contracts.result_ir import (  # noqa: E402
    validate_diagnostic_ir_manifest,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_production_worker_receipt_v2.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/g1_mgt_production_worker_receipt_v2.schema.json"
)
VERSION = "g1-mgt-production-worker-receipt.v2"
PARITY_PROFILE = "g1-terminal-resultir-authority-parity.v2"
PARITY_BINDING_KEYS = checkpoint_gate.PARITY_BINDING_KEYS
SOURCE_PATHS = (
    Path("scripts/build_g1_mgt_production_worker_receipt_v2.py"),
    Path("scripts/g1_receipt_provenance.py"),
    SCHEMA,
    Path("tests/test_build_g1_mgt_production_worker_receipt_v2.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("g1_worker_v2_json_object_required")
    return value


def _hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def terminal_authority_projection(result: dict[str, Any]) -> dict[str, Any]:
    """Return backend-neutral fields that define terminal numerical parity."""

    return {
        "schema_version": PARITY_PROFILE,
        "bindings": {key: result["bindings"][key] for key in PARITY_BINDING_KEYS},
        "load_factor": result["load_factor"],
        "time_s": result["time_s"],
        "dof_count": result["dof_count"],
        "displacement": {
            key: result["displacement_artifact"][key]
            for key in (
                "name",
                "dtype",
                "shape",
                "byte_length",
                "storage_profile",
                "unit_profile",
                "data_hash",
            )
        },
    }


def terminal_parity_digest(
    hip_result: dict[str, Any], cpu_result: dict[str, Any]
) -> str:
    """Require equal authority projections while permitting distinct full hashes."""

    hip_projection = terminal_authority_projection(hip_result)
    cpu_projection = terminal_authority_projection(cpu_result)
    if hip_projection != cpu_projection:
        raise ValueError("g1_worker_v2_terminal_authority_parity_failed")
    return canonical_hash(hip_projection)


def diagnostic_parity_digest(diagnostic: dict[str, Any]) -> str:
    """Hash backend-neutral diagnostic bindings and invariant dispositions."""

    invariant_codes = {
        "fallback_and_regularization_zero",
        "mid_step_d2h_zero",
        "nonlinear_material_family_breadth_unavailable",
    }
    entries = [
        {
            key: entry[key]
            for key in ("code", "path", "severity", "disposition", "occurrence_count")
        }
        for entry in diagnostic["entries"]
        if entry["code"] in invariant_codes
    ]
    if {entry["code"] for entry in entries} != invariant_codes:
        raise ValueError("g1_worker_v2_diagnostic_invariant_entries_missing")
    return canonical_hash(
        {
            "schema_version": "g1-terminal-diagnostic-authority-parity.v2",
            "bindings": {
                key: diagnostic["bindings"][key]
                for key in (
                    "model_ir_content_hash",
                    "execution_plan_hash",
                    "operator_hash",
                    "state_hash",
                    "state_epoch",
                    "equation_scaling_hash",
                    "reduced_csr_identity_hash",
                )
            },
            "entries": sorted(entries, key=lambda row: row["code"]),
        }
    )


def build(
    *,
    root: Path = ROOT,
    generated_at: str | None = None,
    provenance_source_commit_sha: str | None = None,
) -> dict[str, Any]:
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
    envelope = envelope_gate.validate(
        _read(root / envelope_gate.DEFAULT_OUT),
        root=root,
        require_current_sources=True,
    )
    checkpoint = checkpoint_gate.validate(
        _read(root / checkpoint_gate.DEFAULT_OUT), root=root, current=True
    )
    if not (
        result["source"]["fgmres_receipt_hash"] == device["receipt_hash"]
        and envelope["evidence_payload"]["upstream"]["receipt_hash"]
        == device["receipt_hash"]
        and checkpoint["source"]["device_receipt_hash"] == device["receipt_hash"]
        and checkpoint["source"]["result_receipt_hash"] == result["receipt_hash"]
    ):
        raise ValueError("g1_worker_v2_source_chain_mismatch")

    hip = validate_nonlinear_result_manifest(
        _read(root / result_gate.DEFAULT_HIP_RESULT)
    )
    cpu = validate_nonlinear_result_manifest(
        _read(root / result_gate.DEFAULT_CPU_RESULT)
    )
    diagnostic = validate_diagnostic_ir_manifest(
        _read(root / result_gate.DEFAULT_DIAGNOSTIC)
    )
    parity_digest = terminal_parity_digest(hip, cpu)
    if not (
        hip["result_hash"] == result["parity"]["hip_result_hash"]
        and cpu["result_hash"] == result["parity"]["cpu_result_hash"]
        and diagnostic["diagnostic_hash"] == result["diagnostic"]["diagnostic_hash"]
    ):
        raise ValueError("g1_worker_v2_terminal_artifact_hash_mismatch")
    projection = terminal_authority_projection(hip)
    for key in (
        "model_ir_content_hash",
        "execution_plan_hash",
        "operator_hash",
        "state_hash",
        "state_epoch",
        "equation_scaling_hash",
        "reduced_csr_identity_hash",
    ):
        if diagnostic["bindings"].get(key) != projection["bindings"][key]:
            raise ValueError(f"g1_worker_v2_diagnostic_binding_mismatch:{key}")

    runtime = device["hardware_execution"]
    claims = device["claims"]
    signature_verified = envelope["signature"]["state"] == "verified"
    lifecycle = {
        "state_rhs_csr_uploaded": claims["single_device_lifecycle"],
        "persistent_device_buffers_used": claims["single_device_lifecycle"],
        "residual_jvp_on_device": claims["terminal_physical_residual_replay"],
        "accepted_state_tangent_refresh_on_device": False,
        "equation_scaling_on_device": claims["equation_scaling"],
        "production_preconditioner_used": claims["production_size_fgmres"],
        "production_fgmres_used": claims["production_size_fgmres"],
        "newton_update_on_device": claims["newton_update_on_device"],
        "line_search_on_device": claims["physical_line_search_on_device"],
        "material_commit_rollback_on_device": claims["material_commit_rollback"],
        "convergence_gate_on_device": claims["nonlinear_convergence_gate_on_device"],
        "checkpoint_emitted": claims["checkpoint_emitted"],
        "result_ir_emitted": result["claims"][
            "authoritative_nonlinear_resultir_emitted"
        ],
        "diagnostic_ir_emitted": result["claims"]["diagnosticir_emitted"],
    }
    proven_lifecycle = {
        name: passed
        for name, passed in lifecycle.items()
        if name != "accepted_state_tangent_refresh_on_device"
    }
    if not all(proven_lifecycle.values()):
        raise ValueError("g1_worker_v2_lifecycle_incomplete")
    kpis = {
        "krylov_iteration_count": runtime["krylov_iterations"],
        "matvec_count": runtime["matvec_count"],
        "preconditioner_apply_count": runtime["preconditioner_apply_count"],
        "h2d_bytes": runtime["h2d_bytes"],
        "d2h_bytes": runtime["d2h_bytes"],
        "mid_step_d2h_bytes": 0,
        "peak_vram_bytes": runtime["tracked_peak_device_allocation_bytes"],
        "checkpoint_overhead_seconds": device["comparison"]["checkpoint_artifact"][
            "serialization_overhead_seconds"
        ],
        "end_to_end_wall_seconds": device["performance"][
            "gpu_device_lifecycle_wall_seconds"
        ],
        "cpu_baseline_wall_seconds": device["performance"]["cpu_baseline"][
            "wall_seconds"
        ],
        "speedup_vs_cpu": device["performance"]["speedup_vs_cpu"],
    }
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
        "capture_boundary": {
            "mode": "offline_bound_artifact_replay",
            "local_device_probe_performed": False,
            "local_device_probe_required_for_offline_replay": False,
            "signed_hardware_envelope_verified": signature_verified,
            "hardware_identity_trusted": False,
        },
        "source": {
            "repository_commit_sha": device["source"]["repository_commit_sha"],
            "device_architecture": device["runtime"]["gcn_arch_name"],
            "wheel_sha256": device["runtime"]["wheel_sha256"],
            "binary_sha256": device["runtime"]["binary_sha256"],
            "device_receipt_hash": device["receipt_hash"],
            "hardware_envelope_hash": envelope["receipt_hash"],
            "result_receipt_hash": result["receipt_hash"],
            "checkpoint_bundle_hash": checkpoint["receipt_hash"],
        },
        "terminal_parity": {
            "profile": PARITY_PROFILE,
            "parity_digest": parity_digest,
            "hip_result_hash": hip["result_hash"],
            "cpu_result_hash": cpu["result_hash"],
            "full_result_hashes_equal": hip["result_hash"] == cpu["result_hash"],
            "shared_bindings": projection["bindings"],
            "displacement_data_hash": projection["displacement"]["data_hash"],
            "diagnostic_hash": diagnostic["diagnostic_hash"],
            "diagnostic_parity_digest": diagnostic_parity_digest(diagnostic),
        },
        "lifecycle": lifecycle,
        "kpis": kpis,
        "claims": {
            "terminal_resultir_authority_parity": True,
            "terminal_resultir_full_hash_equality_required": False,
            "diagnostic_ir_bound": True,
            "accepted_state_tangent_refresh_on_device_proven": False,
            "fallback_zero_observed_in_bound_receipt": True,
            "mid_step_d2h_zero_observed": runtime["mid_iteration_d2h_transfer_count"]
            == 0,
            "offline_replay_without_local_device_probe": True,
            "trusted_hardware_execution": False,
            "production_worker_ready": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "accepted_state_tangent_refresh_hip_not_proven",
            "trusted_hardware_identity_receipt_not_bound",
            "independent_gfx1100_worker_receipt_not_bound",
            "cross_device_performance_sweep_not_bound",
            "nonlinear_material_family_breadth_not_closed",
        ],
        "claim_boundary": (
            "This additive worker receipt replays an already-bound gfx1030 capture "
            "without probing local device nodes. It proves terminal authority parity "
            "from shared model, plan, scaling, CSR, state, material, path, terminal, "
            "and displacement identities while preserving distinct backend ResultIR "
            "hashes. An unsigned envelope, missing trusted identity policy, absent "
            "accepted-state HIP tangent-refresh evidence, independent gfx1100 receipt, "
            "and open nonlinear material breadth keep the production worker and G1 "
            "closure false."
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
        raise ValueError("g1_worker_v2_receipt_hash_mismatch")
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
            raise ValueError("g1_worker_v2_offline_replay_mismatch")
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
        print("g1_mgt_production_worker_receipt_v2_consistent")
        return 0
    payload = write(out=args.out)
    print(
        "partial | terminal_parity=true | trusted_hardware=false | "
        f"digest={payload['terminal_parity']['parity_digest']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
