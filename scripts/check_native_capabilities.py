#!/usr/bin/env python3
"""Validate and query fail-closed native capability promotion state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path("native/capabilities.json")
EXPECTED_OWNERS = {
    "abi_v1_base": "structural-ffi",
    "backend_selector": "structural-ffi",
    "modelir_v2_rust_wire": "structural-contracts",
    "modelir_v2_cpp_core": "structural_model_ir",
    "modelir_v2": "structural-contracts",
    "modelir_ndtha_adapter": "structural_model_ir",
    "modelir_ndtha_product_e2e": "structural-cli",
    "mgt_import_health": "structural-cli",
    "reference_materials_elements_cpu": "structural_elements",
    "dense_assembly_cpu": "structural_assembly",
    "sparse_linear_solver_cpu": "structural_solver_cpu",
    "sparse_linear_checkpoint": "structural-runtime",
    "sparse_linear_product_e2e": "structural-cli",
    "generalized_eigen_solver_cpu": "structural_solver_cpu",
    "generalized_eigen_checkpoint": "structural-runtime",
    "generalized_eigen_product_e2e": "structural-cli",
    "track_point_load_cpu": "structural_solver_cpu",
    "nonlinear_static_cpu": "structural_solver_cpu",
    "nonlinear_static_checkpoint": "structural-runtime",
    "nonlinear_static_product_e2e": "structural-cli",
    "nonlinear_ndtha_cpu": "structural_solver_cpu",
    "checkpoint_restart": "structural-runtime",
    "product_e2e": "structural-cli",
    "durable_jobs": "structural-runtime",
    "service_api": "structural-cli",
    "external_comparison": "structural-cli",
    "pdf_report": "structural-report",
    "native_workbench": "structural-workbench",
    "native_benchmark_catalog": "structural-catalog",
    "native_frontend_build": "structural-frontend-contract",
    "native_frontend_preview": "structural-frontend-contract",
    "native_frontend_contract": "structural-frontend-contract",
    "native_viewer_js_syntax": "structural-frontend-contract",
    "native_viewer_readme_capture": "structural-frontend-contract",
    "native_viewer_report_pdf_export": "structural-frontend-contract",
    "native_viewer_visual_regression": "structural-frontend-contract",
    "native_viewer_sample_workflow": "structural-frontend-contract",
    "native_evidence_bundle": "structural-evidence",
    "native_distribution": "structural-distribution",
    "native_deployment": "structural-workbench",
    "native_automation_cutover": "structural-distribution",
    "hip_backend": "structural_c_abi_v1",
}
VALID_STATUSES = frozenset({"planned", "implemented", "deprecated"})
VALID_CUTOVER_GATES = frozenset({f"C{index}" for index in range(7)})


def load_capabilities(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("native capability manifest must be an object")
    return payload


def validate_capabilities(payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_version") != "native-capabilities.v1":
        blockers.append("native_capability_schema_version_invalid")
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        return [*blockers, "native_capabilities_mapping_invalid"]
    for capability, owner in EXPECTED_OWNERS.items():
        row = capabilities.get(capability)
        if not isinstance(row, dict):
            blockers.append(f"native_capability_missing:{capability}")
            continue
        status = row.get("status")
        gate = row.get("cutover_gate")
        if status not in VALID_STATUSES:
            blockers.append(f"native_capability_status_invalid:{capability}:{status}")
        if row.get("owner") != owner:
            blockers.append(f"native_capability_owner_invalid:{capability}:{owner}")
        if not str(row.get("claim", "")).strip():
            blockers.append(f"native_capability_claim_missing:{capability}")
        if status == "implemented" and gate not in VALID_CUTOVER_GATES:
            blockers.append(f"native_capability_gate_missing:{capability}")
        if status != "implemented" and gate is not None:
            blockers.append(f"native_capability_unimplemented_gate_set:{capability}:{gate}")
    return sorted(dict.fromkeys(blockers))


def capability_is_enabled(payload: dict[str, Any], capability: str) -> bool:
    capabilities = payload.get("capabilities", {})
    row = capabilities.get(capability, {}) if isinstance(capabilities, dict) else {}
    return isinstance(row, dict) and row.get("status") == "implemented"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--is-enabled", choices=sorted(EXPECTED_OWNERS))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-invalid", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    try:
        payload = load_capabilities(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"native capability manifest invalid: {exc}", file=sys.stderr)
        return 2
    blockers = validate_capabilities(payload)
    report = {
        "schema_version": "native-capability-validation.v1",
        "contract_pass": not blockers,
        "status": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "capabilities": payload.get("capabilities", {}),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    elif args.is_enabled is None:
        print(f"Native capabilities: {report['status']}")
    if blockers:
        return 1 if args.fail_invalid or args.is_enabled else 0
    if args.is_enabled is not None:
        enabled = capability_is_enabled(payload, args.is_enabled)
        print(f"{args.is_enabled}={'enabled' if enabled else 'disabled'}")
        return 0 if enabled else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
