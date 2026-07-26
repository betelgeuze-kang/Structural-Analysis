#!/usr/bin/env python3
"""Build the fail-closed P3 entry and completion gate manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
ROADMAP_STATUS_PATH = Path("artifacts/manifests/product_roadmap_status.json")
CAPABILITY_REGISTRY_PATH = Path("artifacts/manifests/capabilities.yaml")
CUSTOMER_SHADOW_STATUS_PATH = Path(
    "implementation/phase1/customer_shadow_evidence_status.json"
)
ROADMAP_PATH = Path("docs/repository-architecture-and-product-roadmap.md")
OUTPUT_PATH = Path("artifacts/manifests/p3_entry_gate.json")

P3_CAPABILITY_IDS = (
    "element.shell_plate",
    "interaction.contact",
    "element.cable",
    "analysis.soil_structure_interaction",
    "analysis.staged_construction",
    "analysis.mixed_frame_shell_nonlinear",
    "execution.distributed",
    "backend.rocm_hip_production",
    "evidence.customer_shadow_three",
    "design.code_modules",
    "ai.guarded_execution",
)

REQUIRED_EXTERNAL_EVIDENCE_IDS = (
    "product_license_approved",
    "repository_hygiene_closed",
    "committed_current_head_ci_receipt",
    "opensees_level2_promoted",
    "second_solver_level2_promoted",
    "published_material_cyclic_level3",
    "published_snap_through_level3",
    "frame3d_external_comparison",
    "checkpoint_resume_job_service_promoted",
    "signed_engineering_review",
)

PROXY_INVENTORY = (
    {
        "path": "src/structural_analysis/assembly/coupled_static.py",
        "classification": "two_dof_frame_shell_named_nonlinear_spring_seed",
        "product_capability": "analysis.mixed_frame_shell_nonlinear",
        "promotable": False,
        "reason": "No shell element, mesh assembly, integration-point state, or general frame-shell solve.",
    },
    {
        "path": "implementation/phase1/run_mgt_coupled_frame_shell_sparse_equilibrium.py",
        "classification": "large_model_linear_sparse_technical_probe",
        "product_capability": "analysis.mixed_frame_shell_nonlinear",
        "promotable": False,
        "reason": "Its receipt explicitly keeps coupled_frame_shell_nonlinear_equilibrium false.",
    },
    {
        "path": "implementation/phase1/run_general_fe_contact_benchmark_gate.py",
        "classification": "phase1_contact_proxy_evidence",
        "product_capability": "interaction.contact",
        "promotable": False,
        "reason": "Phase1 evidence is outside the canonical core product boundary and is not a public contact formulation.",
    },
    {
        "path": "implementation/phase1/advanced_ssi.py",
        "classification": "phase1_ssi_research_asset",
        "product_capability": "analysis.soil_structure_interaction",
        "promotable": False,
        "reason": "No promoted core solver profile, external V&V package, or release authority.",
    },
    {
        "path": "implementation/phase1/construction_stage_engine.py",
        "classification": "phase1_construction_stage_research_asset",
        "product_capability": "analysis.staged_construction",
        "promotable": False,
        "reason": "No promoted core state-transfer/checkpoint contract or external validation package.",
    },
    {
        "path": "src/structural_analysis/engine_v2_backends/hip_fgmres_recurrence.py",
        "classification": "bounded_hip_backend_research_asset",
        "product_capability": "backend.rocm_hip_production",
        "promotable": False,
        "reason": "CPU sparse reference, full-path parity, residency, fallback, provenance, and external V&V gates remain open.",
    },
)


class P3EntryGateError(ValueError):
    """Raised when a P3 gate input cannot be evaluated safely."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise P3EntryGateError(f"cannot load {path}: {error}") from error
    if not isinstance(value, dict):
        raise P3EntryGateError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _capability_map(registry: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = registry.get("capabilities")
    if not isinstance(rows, list):
        raise P3EntryGateError("capability registry has no capability list")
    result: dict[str, Mapping[str, Any]] = {}
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            raise P3EntryGateError("capability row must be an object")
        capability_id = raw_row.get("id")
        if not isinstance(capability_id, str) or not capability_id:
            raise P3EntryGateError("capability row has no id")
        result[capability_id] = raw_row
    return result


def evaluate_p3_entry_gate(
    *,
    roadmap_status: Mapping[str, Any],
    capability_registry: Mapping[str, Any],
    customer_shadow_status: Mapping[str, Any],
    input_checksums: Mapping[str, str],
) -> dict[str, Any]:
    """Evaluate P3 without converting proxy or local candidate evidence into authority."""
    phases_raw = roadmap_status.get("phases")
    phases = phases_raw if isinstance(phases_raw, dict) else {}
    phase_checks = [
        {
            "id": f"{phase.lower()}_closed",
            "required": "closed",
            "observed": phases.get(phase, "missing"),
            "pass": phases.get(phase) == "closed",
        }
        for phase in ("P0", "P1", "P2")
    ]

    pull_requests_raw = roadmap_status.get("pull_requests")
    pull_requests = pull_requests_raw if isinstance(pull_requests_raw, list) else []
    pr_by_number = {
        row.get("number"): row
        for row in pull_requests
        if isinstance(row, dict) and isinstance(row.get("number"), int)
    }
    closed_pr_numbers = [
        number
        for number in range(1, 19)
        if isinstance(pr_by_number.get(number), dict)
        and pr_by_number[number].get("status") == "closed"
    ]
    missing_or_open_pr_numbers = [
        number for number in range(1, 19) if number not in closed_pr_numbers
    ]

    external_raw = roadmap_status.get("required_external_evidence")
    external = external_raw if isinstance(external_raw, dict) else {}
    external_checks = [
        {
            "id": evidence_id,
            "required": True,
            "observed": external.get(evidence_id),
            "pass": external.get(evidence_id) is True,
        }
        for evidence_id in REQUIRED_EXTERNAL_EVIDENCE_IDS
    ]

    snapshot_checks = [
        {
            "id": "authoritative_release_snapshot",
            "required": True,
            "observed": roadmap_status.get("authoritative_release_snapshot"),
            "pass": roadmap_status.get("authoritative_release_snapshot") is True,
        },
        {
            "id": "roadmap_closure_pass",
            "required": True,
            "observed": roadmap_status.get("closure_pass"),
            "pass": roadmap_status.get("closure_pass") is True,
        },
        {
            "id": "ordered_prs_1_through_18_closed",
            "required": 18,
            "observed": len(closed_pr_numbers),
            "pass": len(closed_pr_numbers) == 18,
            "missing_or_open_pr_numbers": missing_or_open_pr_numbers,
        },
    ]

    capabilities = _capability_map(capability_registry)
    feature_rows: list[dict[str, Any]] = []
    for capability_id in P3_CAPABILITY_IDS:
        row = capabilities.get(capability_id)
        if row is None:
            feature_rows.append(
                {
                    "capability_id": capability_id,
                    "status": "missing",
                    "public": False,
                    "authority": "none",
                    "completion_pass": False,
                }
            )
            continue
        status = row.get("status")
        public = row.get("public")
        authority = row.get("authority")
        feature_rows.append(
            {
                "capability_id": capability_id,
                "status": status,
                "public": public,
                "authority": authority,
                "completion_pass": status in {"supported", "bounded_public"}
                and public is True
                and authority != "none",
            }
        )

    shadow_summary_raw = customer_shadow_status.get("summary")
    shadow_summary = shadow_summary_raw if isinstance(shadow_summary_raw, dict) else {}
    completed_shadow_cases = shadow_summary.get("completed_shadow_case_count")
    minimum_shadow_cases = shadow_summary.get("min_completed_shadow_cases")
    customer_shadow_pass = (
        customer_shadow_status.get("contract_pass") is True
        and isinstance(completed_shadow_cases, int)
        and isinstance(minimum_shadow_cases, int)
        and minimum_shadow_cases >= 3
        and completed_shadow_cases >= minimum_shadow_cases
    )
    customer_shadow_check = {
        "id": "validated_customer_shadow_cases",
        "required_minimum": 3,
        "configured_minimum": minimum_shadow_cases,
        "observed": completed_shadow_cases,
        "source_contract_pass": customer_shadow_status.get("contract_pass"),
        "pass": customer_shadow_pass,
    }

    entry_checks = [*phase_checks, *snapshot_checks, *external_checks]
    entry_gate_pass = all(check["pass"] is True for check in entry_checks)
    feature_completion_pass = all(
        row["completion_pass"] is True for row in feature_rows
    )
    p3_completion_pass = entry_gate_pass and feature_completion_pass and customer_shadow_pass

    blockers = [
        str(check["id"]) for check in entry_checks if check["pass"] is not True
    ]
    blockers.extend(
        f"{row['capability_id']}_not_supported"
        for row in feature_rows
        if row["completion_pass"] is not True
    )
    if not customer_shadow_pass:
        blockers.append("validated_customer_shadow_cases_below_three")

    return {
        "schema_version": "structural-analysis-p3-entry-gate.v1",
        "status": "ready" if p3_completion_pass else "blocked",
        "contract_pass": True,
        "base_head": roadmap_status.get("base_head"),
        "assessment_scope": roadmap_status.get("assessment_scope"),
        "authoritative_release_snapshot": roadmap_status.get(
            "authoritative_release_snapshot"
        ),
        "entry_gate_pass": entry_gate_pass,
        "p3_completion_pass": p3_completion_pass,
        "phase_prerequisite_checks": phase_checks,
        "snapshot_and_sequence_checks": snapshot_checks,
        "external_evidence_checks": external_checks,
        "p3_feature_checks": feature_rows,
        "customer_shadow_check": customer_shadow_check,
        "proxy_inventory": [dict(row) for row in PROXY_INVENTORY],
        "blockers": blockers,
        "input_checksums": dict(sorted(input_checksums.items())),
        "claim_boundary": (
            "This artifact is a fail-closed change-control gate. Existing phase1, "
            "proxy, benchmark, fallback, or working-tree candidate assets do not grant "
            "P3 entry or product authority. P3 entry requires closed P0-P2 phases, "
            "closed PRs 1-18, a current authoritative snapshot, and every named external "
            "receipt; P3 completion additionally requires supported capabilities and at "
            "least three validated customer-shadow cases."
        ),
    }


def build_p3_entry_gate(repo_root: Path = ROOT) -> dict[str, Any]:
    source_paths = (
        ROADMAP_STATUS_PATH,
        CAPABILITY_REGISTRY_PATH,
        CUSTOMER_SHADOW_STATUS_PATH,
        ROADMAP_PATH,
        Path("scripts/build_p3_entry_gate.py"),
    )
    inputs = {
        relative.as_posix(): _sha256(repo_root / relative) for relative in source_paths
    }
    return evaluate_p3_entry_gate(
        roadmap_status=_load_object(repo_root / ROADMAP_STATUS_PATH),
        capability_registry=_load_object(repo_root / CAPABILITY_REGISTRY_PATH),
        customer_shadow_status=_load_object(repo_root / CUSTOMER_SHADOW_STATUS_PATH),
        input_checksums=inputs,
    )


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def check_p3_entry_gate(
    *, repo_root: Path = ROOT, output_path: Path = OUTPUT_PATH
) -> tuple[bool, str]:
    expected = _serialized(build_p3_entry_gate(repo_root))
    target = repo_root / output_path
    if not target.exists():
        return False, f"p3_entry_gate_missing:{output_path.as_posix()}"
    if target.read_text(encoding="utf-8") != expected:
        return False, f"p3_entry_gate_stale:{output_path.as_posix()}"
    return True, "p3_entry_gate_current"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    payload = build_p3_entry_gate(args.repo_root)
    if args.write:
        target = args.repo_root / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_serialized(payload), encoding="utf-8")
    if args.check:
        current, message = check_p3_entry_gate(
            repo_root=args.repo_root, output_path=args.output
        )
        if args.json:
            print(
                json.dumps(
                    {"contract_current": current, "message": message},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(message)
        return 0 if current else 1
    if args.json or not args.write:
        print(_serialized(payload), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
