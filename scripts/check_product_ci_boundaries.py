#!/usr/bin/env python3
"""Validate structural-core, legacy-evidence, and molecular-quarantine CI ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUARANTINE_MANIFEST = Path(
    "implementation/phase1/release_evidence/productization/"
    "structural_scope_quarantine_manifest.json"
)
SCHEMA_VERSION = "product-ci-boundary-report.v1"
LANES = ("core", "legacy_evidence", "molecular_quarantine")

MOLECULAR_TOKENS = (
    "gpcr",
    "pocketmd",
    "ligand",
    "docking",
    "vina",
    "gnina",
    "molecular",
    "science_actual",
    "h_bond",
    "md3bead",
    "fep",
    "free_energy",
    "all_atom",
    "casf_pdbbind",
    "pdbbind",
    "dud_e",
    "lit_pcba",
    "posebusters",
    "symmetry_rmsd",
    "symmetry_aware_ligand",
    "public_benchmark_enrichment",
    "public_benchmark_pose",
    "public_benchmark_vina_gnina",
)

CORE_PREFIXES = ("src/structural_analysis/",)
CORE_EXACT_PATHS = {
    "implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py",
    "implementation/phase1/release_viewer_bundler.py",
    "scripts/build_analytic_frame_verification_artifact.py",
    "scripts/build_phase2_adaptive_newton_continuation_artifacts.py",
    "scripts/build_phase2_geometric_nonlinear_benchmark_artifacts.py",
    "scripts/build_phase2_modal_buckling_kernel_artifacts.py",
    "scripts/build_phase2_newton_globalization_artifacts.py",
    "scripts/build_phase2_whole_model_modal_artifacts.py",
    "scripts/build_phase2_whole_model_buckling_artifacts.py",
    "scripts/run_external_code_to_code_technical_receipt.py",
    "scripts/run_external_modal_buckling_technical_receipt.py",
    "scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
    "scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
    "scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
    "scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
    "scripts/build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
    "scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
    "scripts/build_phase2_shallow_arch_arc_length_artifacts.py",
    "scripts/build_phase2_state_updated_concrete_damage_artifacts.py",
    "scripts/build_phase2_state_updated_composite_section_artifacts.py",
    "scripts/build_phase2_state_updated_bilinear_link_artifacts.py",
    "scripts/build_phase2_state_updated_steel_material_artifacts.py",
    "scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py",
    "scripts/build_medium_benchmark_corpus_plan.py",
    "scripts/build_phase3_medium_model_scorecard_readiness_receipt.py",
    "scripts/build_phase6_benchmark_scale_status.py",
    "scripts/build_phase6_silent_import_loss_status.py",
    "scripts/acquire_buildingsmart_ifc_current_source.py",
    "scripts/build_ifc_import_health_current_source_receipt.py",
    "scripts/build_internal_license_due_diligence.py",
    "scripts/build_mgt_import_health_current_source_receipt.py",
    "scripts/build_developer_preview_rc_status.py",
    "scripts/build_developer_preview_final_gate_owner_packet.py",
    "scripts/build_structural_product_development_roadmap.py",
    "scripts/build_verification_hierarchy_status.py",
    "scripts/check_git_remote_safety.py",
    "scripts/check_core_quality.py",
    "scripts/check_large_git_blobs.py",
    "scripts/check_native_ci_contract.py",
    "scripts/check_native_capabilities.py",
    "scripts/check_native_dependency_boundary.py",
    "scripts/check_native_dependency_licenses.py",
    "scripts/check_pr_issue_metadata.py",
    "scripts/check_product_ci_boundaries.py",
    "scripts/check_repo_hygiene.py",
    "scripts/check_structural_scope_contamination.py",
    "scripts/plan_source_boundary_cleanup.py",
    "scripts/report_source_boundary_footprint.py",
    "scripts/run_product_ci_lane.py",
    "scripts/run_engine_v2_hip_fgmres_recurrence.py",
    "scripts/run_engine_v2_hip_primitive_parity.py",
    "scripts/run_phase3_medium_model_scorecard_receipt.py",
    "scripts/verify_quality_gate.py",
    "scripts/verify_release_artifacts_manifest.py",
    "scripts/verify_open_data_external_artifacts_manifest.py",
    "scripts/verify_structure_viewer_contracts.py",
    "scripts/classify_native_ci_scope.py",
    "tests/test_authoritative_linear_frame.py",
    "tests/test_authoritative_linear_frame_reference_cases.py",
    "tests/test_analytic_frame_verification.py",
    "tests/test_benchmark_scientific_acceptance.py",
    "tests/test_build_medium_benchmark_corpus_plan.py",
    "tests/test_build_phase2_adaptive_newton_continuation_artifacts.py",
    "tests/test_build_phase2_geometric_nonlinear_benchmark_artifacts.py",
    "tests/test_build_phase2_modal_buckling_kernel_artifacts.py",
    "tests/test_build_phase2_newton_globalization_artifacts.py",
    "tests/test_build_phase2_whole_model_modal_artifacts.py",
    "tests/test_whole_model_modal_analysis.py",
    "tests/test_build_phase2_whole_model_buckling_artifacts.py",
    "tests/test_whole_model_buckling_analysis.py",
    "tests/test_external_code_to_code_technical_receipt.py",
    "tests/test_external_modal_buckling_technical_receipt.py",
    "tests/test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py",
    "tests/test_build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py",
    "tests/test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py",
    "tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py",
    "tests/test_build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py",
    "tests/test_build_g1_mgt_load_coupled_arc_length_adapter_receipt.py",
    "tests/test_build_phase2_shallow_arch_arc_length_artifacts.py",
    "tests/test_build_phase2_state_updated_concrete_damage_artifacts.py",
    "tests/test_build_phase2_state_updated_composite_section_artifacts.py",
    "tests/test_build_phase2_state_updated_bilinear_link_artifacts.py",
    "tests/test_build_phase2_state_updated_steel_material_artifacts.py",
    "tests/test_build_stateful_nonlinear_no_solve_reaction_only_artifact.py",
    "tests/test_build_phase3_medium_model_scorecard_readiness_receipt.py",
    "tests/test_build_phase6_benchmark_scale_status.py",
    "tests/test_build_phase6_silent_import_loss_status.py",
    "tests/test_ifc_import_health_current_source.py",
    "tests/test_ifc_import_health_current_source_workflow.py",
    "tests/test_build_internal_license_due_diligence.py",
    "tests/test_mgt_import_health_current_source.py",
    "tests/test_mgt_import_health_current_source_workflow.py",
    "tests/test_build_developer_preview_rc_status.py",
    "tests/test_build_developer_preview_final_gate_owner_packet.py",
    "tests/test_build_structural_product_development_roadmap.py",
    "tests/test_build_verification_hierarchy_status.py",
    "tests/test_core_quality_contract.py",
    "tests/test_current_head_readiness_ci.py",
    "tests/test_check_large_git_blobs.py",
    "tests/test_native_ci_scope.py",
    "tests/test_native_capability_manifest.py",
    "tests/test_native_ci_workflow_contract.py",
    "tests/test_native_dependency_license.py",
    "tests/test_check_pr_issue_metadata.py",
    "tests/test_check_product_ci_boundaries.py",
    "tests/test_elastic_material_contract.py",
    "tests/test_mgt_frame_kernel_extraction.py",
    "tests/test_midas_explicit_adapter.py",
    "tests/test_midas_mgt_nodal_load_contract.py",
    "tests/test_medium_benchmark_corpus_contract.py",
    "tests/test_nonlinear_adaptive_continuation.py",
    "tests/test_nonlinear_fully_constrained_no_solve.py",
    "tests/test_nonlinear_line_search_acceptance.py",
    "tests/test_nonlinear_newton_config_contract.py",
    "tests/test_nonlinear_arc_length.py",
    "tests/test_geometric_nonlinear_benchmarks.py",
    "tests/test_modal_generalized_eigen_v1.py",
    "tests/test_buckling_generalized_eigen_v1.py",
    "tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py",
    "tests/test_arc_length_cpu_fgmres_tangent_bridge.py",
    "tests/test_arc_length_cpu_fgmres_continuation.py",
    "tests/test_sparse_chain_cpu_fgmres_arc_length.py",
    "tests/test_load_coupled_sparse_chain_arc_length.py",
    "tests/test_g1_mgt_load_coupled_arc_length_adapter.py",
    "tests/test_engine_v2_cpu_fgmres_tangent.py",
    "tests/test_nonlinear_vector_arc_length.py",
    "tests/test_shallow_arch_arc_length_benchmark.py",
    "tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py",
    "tests/test_engine_v2_hip_fgmres_recurrence.py",
    "tests/test_engine_v2_hip_fgmres_recurrence_runner.py",
    "tests/test_engine_v2_hip_primitive_parity.py",
    "tests/test_engine_v2_hip_primitive_parity_runner.py",
    "tests/test_state_updated_concrete_damage_newton.py",
    "tests/test_state_updated_composite_section_newton.py",
    "tests/test_state_updated_bilinear_link_newton.py",
    "tests/test_state_updated_steel_material_newton.py",
    "tests/test_product_ci_workflow_contract.py",
    "tests/test_run_phase3_medium_model_scorecard_receipt.py",
    "tests/test_verification_hierarchy_contract.py",
    "tests/test_project_ops_api_service.py",
    "tests/test_release_viewer_bundler.py",
    "tests/test_result_validation_tolerance.py",
    "tests/test_runtime_dependency_contract.py",
    "tests/test_source_boundary_ci_contract.py",
    "tests/test_source_boundary_footprint_report.py",
    "tests/test_stateful_corotational_fiber_frame2d_adaptive.py",
    "tests/test_stateful_corotational_fiber_frame2d_arc_length.py",
    "tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_gap_linked_frame_cyclic_benchmark.py",
    "tests/test_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark.py",
    "tests/test_structure_viewer_dom_safety_contract.py",
    "tests/test_structural_analysis_core_api.py",
    "tests/test_typed_domain_model.py",
    "tests/test_verify_quality_gate_contract.py",
}
CORE_TEST_PREFIXES = (
    "tests/test_authoritative_linear_",
    "tests/test_structure_viewer_",
)

# The control-plane filename intentionally avoids product-domain tokens so the
# structural scope audit does not mistake the quarantine workflow itself for a
# molecular product artifact.
REQUIRED_WORKFLOW_LANES = {
    ".github/workflows/ci.yml": "core",
    ".github/workflows/legacy-evidence-ci.yml": "legacy_evidence",
    ".github/workflows/science-quarantine-ci.yml": "molecular_quarantine",
}
GITHUB_HOSTED_RUNNER_ALLOWLIST = ("ubuntu-24.04",)


def _workflow_runner_labels(text: str) -> list[str]:
    """Return literal runner labels so aliases and expressions fail closed."""

    labels: list[str] = []
    for match in re.finditer(r"^\s*runs-on:\s*([^\s#]+)", text, re.MULTILINE):
        labels.append(match.group(1).strip("'\""))
    return labels


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _git_tracked_python_paths(repo_root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return sorted(
        row for row in completed.stdout.decode("utf-8", "replace").split("\0") if row
    )


def _normalized(path: str) -> str:
    return path.replace("-", "_").lower()


def looks_molecular(path: str) -> bool:
    normalized = _normalized(path)
    return any(token in normalized for token in MOLECULAR_TOKENS)


def is_core_path(path: str) -> bool:
    return (
        path in CORE_EXACT_PATHS
        or any(path.startswith(prefix) for prefix in CORE_PREFIXES)
        or any(path.startswith(prefix) for prefix in CORE_TEST_PREFIXES)
    )


def classify_path(path: str, *, quarantined_paths: set[str]) -> str:
    """Return the exactly-one CI lane that owns one tracked Python path."""

    if path in quarantined_paths or looks_molecular(path):
        return "molecular_quarantine"
    if is_core_path(path):
        return "core"
    return "legacy_evidence"


def _quarantine_paths(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("paths", [])
    if not isinstance(rows, list):
        return set()
    return {
        str(row.get("path", "")).strip()
        for row in rows
        if isinstance(row, dict) and str(row.get("path", "")).strip()
    }


def _workflow_checks(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for workflow_path, lane in REQUIRED_WORKFLOW_LANES.items():
        path = repo_root / workflow_path
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        present = path.exists()
        runner_call_present = f"scripts/run_product_ci_lane.py --lane {lane}" in text
        runner_labels = _workflow_runner_labels(text)
        hosted = bool(runner_labels) and all(
            label in GITHUB_HOSTED_RUNNER_ALLOWLIST for label in runner_labels
        )
        row = {
            "path": workflow_path,
            "lane": lane,
            "present": present,
            "runner_call_present": runner_call_present,
            "runner_labels": runner_labels,
            "runner_allowlist": list(GITHUB_HOSTED_RUNNER_ALLOWLIST),
            "github_hosted": hosted,
            "contract_pass": bool(present and runner_call_present and hosted),
        }
        rows.append(row)
        if not present:
            blockers.append(f"workflow_missing:{workflow_path}")
        elif not runner_call_present:
            blockers.append(f"workflow_lane_runner_missing:{workflow_path}:{lane}")
        elif not hosted:
            blockers.append(f"workflow_not_github_hosted:{workflow_path}")
    return rows, blockers


def build_report(
    *,
    repo_root: Path = ROOT,
    quarantine_manifest: Path = DEFAULT_QUARANTINE_MANIFEST,
    tracked_python_paths: Iterable[str] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    manifest_path = _resolve(repo_root, quarantine_manifest)
    manifest = _load_json(manifest_path)
    manifest_rows = manifest.get("paths", [])
    manifest_rows = manifest_rows if isinstance(manifest_rows, list) else []
    quarantined_paths = _quarantine_paths(manifest)
    python_paths = (
        sorted(set(tracked_python_paths))
        if tracked_python_paths is not None
        else _git_tracked_python_paths(repo_root)
    )

    lane_paths = {lane: [] for lane in LANES}
    for path in python_paths:
        lane_paths[classify_path(path, quarantined_paths=quarantined_paths)].append(
            path
        )

    blockers: list[str] = []
    declared_count = manifest.get("path_count")
    if declared_count != len(manifest_rows):
        blockers.append(
            "quarantine_manifest_path_count_mismatch:"
            f"declared={declared_count}:observed={len(manifest_rows)}"
        )

    missing_manifest_paths = sorted(
        path
        for path in lane_paths["molecular_quarantine"]
        if path not in quarantined_paths
    )
    blockers.extend(
        f"molecular_python_path_missing_from_quarantine_manifest:{path}"
        for path in missing_manifest_paths
    )

    core_molecular_overlap = sorted(
        path for path in lane_paths["core"] if looks_molecular(path)
    )
    blockers.extend(
        f"molecular_path_owned_by_core_lane:{path}" for path in core_molecular_overlap
    )

    workflow_rows, workflow_blockers = _workflow_checks(repo_root)
    blockers.extend(workflow_blockers)
    blockers = sorted(dict.fromkeys(blockers))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready" if not blockers else "blocked",
        "contract_pass": not blockers,
        "lane_counts": {lane: len(lane_paths[lane]) for lane in LANES},
        "lane_paths": lane_paths,
        "quarantine_manifest": quarantine_manifest.as_posix(),
        "quarantine_manifest_declared_count": declared_count,
        "quarantine_manifest_observed_count": len(manifest_rows),
        "molecular_python_paths_missing_from_manifest": missing_manifest_paths,
        "core_molecular_overlap": core_molecular_overlap,
        "workflow_contracts": workflow_rows,
        "blockers": blockers,
        "claim_boundary": (
            "This report assigns every tracked Python file to exactly one CI ownership "
            "lane. Molecular-quarantine checks preserve syntax and isolation only and do "
            "not promote quarantined science code into the structural product surface."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quarantine-manifest",
        type=Path,
        default=DEFAULT_QUARANTINE_MANIFEST,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-paths", choices=LANES)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_report(quarantine_manifest=args.quarantine_manifest)
    if args.print_paths:
        for path in payload["lane_paths"][args.print_paths]:
            print(path)
    elif args.json:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        print(rendered)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(
            "Product CI boundaries: "
            f"{payload['status']} | "
            + " | ".join(f"{lane}={payload['lane_counts'][lane]}" for lane in LANES)
        )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
