#!/usr/bin/env python3
"""Materialize Public Benchmark Phase 2 closure from operator row files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import materialize_public_benchmark_harness_bundle as harness_bundle  # noqa: E402
import materialize_public_benchmark_enrichment_scorecard as enrichment_scorecard  # noqa: E402
import materialize_public_benchmark_operator_bundle_from_rows as row_bundle  # noqa: E402
import materialize_public_benchmark_pose_validity_input as pose_validity_input  # noqa: E402
import materialize_public_benchmark_subset_manifest as subset_manifest  # noqa: E402
import materialize_public_benchmark_vina_gnina_comparison_adapter as vina_gnina_adapter  # noqa: E402
from score_symmetry_aware_ligand_rmsd import DEFAULT_THRESHOLD_ANGSTROM  # noqa: E402
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")

DEFAULT_OUT = PRODUCTIZATION / "public_benchmark_phase2_row_audit.json"
DEFAULT_OPERATOR_BUNDLE_OUT = PRODUCTIZATION / "public_benchmark_operator_bundle.json"
DEFAULT_HARNESS_REPORT_OUT = (
    PRODUCTIZATION / "public_benchmark_harness_bundle_materialization_report.json"
)
DEFAULT_ARTIFACT_BUNDLE_OUT = PRODUCTIZATION / "public_benchmark_harness_bundle.json"
DEFAULT_OUT_DIR = PRODUCTIZATION

SCHEMA_VERSION = "public-benchmark-phase2-row-audit.v1"

ROW_INPUTS = {
    "subset_rows": "CASF/PDBBind subset rows",
    "pose_rows": "CASF/PDBBind pose-coordinate rows",
    "enrichment_rows": "DUD-E/LIT-PCBA enrichment rows",
    "vina_gnina_rows": "Vina/GNINA engine comparison rows",
}
ACCEPTED_ROW_FORMATS = ("json", "jsonl", "ndjson", "csv")
SOURCE_CHECKSUM_POLICY = {
    "accepted_checksum_format": "sha256:<64 lowercase or uppercase hex characters>",
    "required_receipt_field": "source_checksum",
}

COMPONENT_ROW_INPUTS = {
    "casf_pdbbind_pose_success_harness": ("subset_rows", "pose_rows"),
    "symmetry_aware_ligand_rmsd": ("pose_rows",),
    "posebusters_style_pose_validity": ("pose_rows",),
    "vina_gnina_comparison_adapter": ("vina_gnina_rows",),
    "dud_e_or_lit_pcba_enrichment": ("enrichment_rows",),
}

ARTIFACT_BUNDLE_ROLES = (
    "subset_manifest",
    "pose_validity_packet",
    "rmsd_scorecard",
    "pose_success_harness",
    "enrichment_scorecard",
    "vina_gnina_comparison_adapter",
    "external_receipts_validation",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _write_json(repo_root: Path, path: Path, payload: dict[str, Any]) -> None:
    resolved = _resolve(repo_root, path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")


def _resolved_out_dir(repo_root: Path, out_dir: Path) -> Path:
    return out_dir if out_dir.is_absolute() else repo_root / out_dir


def _artifact_paths_for_out_dir(repo_root: Path, out_dir: Path) -> list[Path]:
    resolved_out_dir = _resolved_out_dir(repo_root, out_dir)
    return [
        resolved_out_dir / harness_bundle.ARTIFACT_FILENAMES[role]
        for role in ARTIFACT_BUNDLE_ROLES
    ]


def _row_intake_contracts(
    *,
    operator_bundle_out: Path,
    out_dir: Path,
    harness_report_out: Path,
    artifact_bundle_out: Path,
    target_subset_case_count: int | None,
) -> dict[str, Any]:
    target_case_count = int(
        target_subset_case_count
        or subset_manifest.DEFAULT_TARGET_SUBSET_CASE_COUNT
    )
    common_source_receipt_fields = [
        "source_license_or_accession",
        "source_checksum",
        "provenance_ref",
    ]
    minimum_component_counts = {
        str(row["component_id"]): {
            str(row["count_field"]): int(row["required_minimum_count"])
        }
        for row in harness_bundle.PHASE2_REQUIRED_COMPONENTS
    }
    return {
        "subset_rows": {
            "row_input_id": "subset_rows",
            "description": ROW_INPUTS["subset_rows"],
            "accepted_formats": list(ACCEPTED_ROW_FORMATS),
            "required_case_fields": list(subset_manifest.REQUIRED_CASE_FIELDS),
            "required_local_source_file_fields": list(
                subset_manifest.LOCAL_SOURCE_FILE_FIELDS
            ),
            "supported_source_families": ["CASF/PDBBind"],
            "supported_benchmark_splits": list(
                subset_manifest.SUPPORTED_CASF_PDBBIND_BENCHMARK_SPLITS
            ),
            "required_pose_success_metric": (
                subset_manifest.REQUIRED_POSE_SUCCESS_METRIC
            ),
            "default_target_subset_case_count": target_case_count,
            "minimum_phase2_component_counts": minimum_component_counts,
            "source_checksum_policy": SOURCE_CHECKSUM_POLICY,
            "source_receipt_required_fields": common_source_receipt_fields,
            "source_actuality_policy": row_bundle.SOURCE_ACTUALITY_POLICY,
            "feeds_components": ["casf_pdbbind_pose_success_harness"],
            "materialization_chain": [
                "materialize_public_benchmark_subset_manifest",
                "validate_public_benchmark_subset_manifest",
                "materialize_public_benchmark_pose_validity_input",
                "materialize_public_benchmark_pose_success_harness",
            ],
        },
        "pose_rows": {
            "row_input_id": "pose_rows",
            "description": ROW_INPUTS["pose_rows"],
            "accepted_formats": list(ACCEPTED_ROW_FORMATS),
            "required_pose_fields": list(pose_validity_input.REQUIRED_POSE_FIELDS),
            "paired_row_inputs_required": ["subset_rows"],
            "coordinate_payload_fields": ["reference_atoms", "predicted_atoms"],
            "required_context_fields": [
                "ligand_atom_order_contract",
                "symmetry_permutation_contract",
                "receptor_context",
            ],
            "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
            "default_rmsd_threshold_angstrom": DEFAULT_THRESHOLD_ANGSTROM,
            "minimum_phase2_component_counts": minimum_component_counts,
            "source_actuality_policy": {
                "required_pose_source_receipt_fields": list(
                    row_bundle.POSE_SOURCE_RECEIPT_FIELDS
                ),
                "placeholder_markers_rejected": list(
                    row_bundle.PLACEHOLDER_SOURCE_TEXT_MARKERS
                ),
                "placeholder_provenance_prefixes_rejected": list(
                    row_bundle.PLACEHOLDER_PROVENANCE_PREFIXES
                ),
            },
            "feeds_components": [
                "symmetry_aware_ligand_rmsd",
                "posebusters_style_pose_validity",
                "casf_pdbbind_pose_success_harness",
            ],
            "materialization_chain": [
                "materialize_public_benchmark_pose_validity_input",
                "validate_public_benchmark_pose_validity",
                "materialize_public_benchmark_posebusters_validity_packet",
                "materialize_public_benchmark_rmsd_scorecard",
                "materialize_public_benchmark_pose_success_harness",
            ],
        },
        "enrichment_rows": {
            "row_input_id": "enrichment_rows",
            "description": ROW_INPUTS["enrichment_rows"],
            "accepted_formats": list(ACCEPTED_ROW_FORMATS),
            "accepted_shapes": [
                "targets_with_scored_molecules",
                "flat_target_molecule_rows",
            ],
            "required_target_fields": list(enrichment_scorecard.REQUIRED_TARGET_FIELDS),
            "required_molecule_fields": list(
                enrichment_scorecard.REQUIRED_MOLECULE_FIELDS
            ),
            "supported_benchmark_families": list(
                enrichment_scorecard.SUPPORTED_FAMILIES
            ),
            "source_checksum_policy": SOURCE_CHECKSUM_POLICY,
            "source_receipt_required_fields": common_source_receipt_fields,
            "source_actuality_policy": row_bundle.SOURCE_ACTUALITY_POLICY,
            "computed_metrics": [
                "roc_auc",
                "enrichment_factor_1pct",
                "enrichment_factor_5pct",
            ],
            "minimum_phase2_component_counts": minimum_component_counts,
            "feeds_components": ["dud_e_or_lit_pcba_enrichment"],
            "materialization_chain": [
                "materialize_public_benchmark_enrichment_scorecard",
            ],
        },
        "vina_gnina_rows": {
            "row_input_id": "vina_gnina_rows",
            "description": ROW_INPUTS["vina_gnina_rows"],
            "accepted_formats": list(ACCEPTED_ROW_FORMATS),
            "accepted_shapes": [
                "cases_with_engine_runs",
                "flat_case_engine_run_rows",
            ],
            "required_case_fields": list(vina_gnina_adapter.REQUIRED_CASE_FIELDS),
            "required_engine_run_fields": list(
                vina_gnina_adapter.REQUIRED_ENGINE_RUN_FIELDS
            ),
            "supported_engines": list(vina_gnina_adapter.SUPPORTED_ENGINES),
            "supported_benchmark_splits": list(
                vina_gnina_adapter.SUPPORTED_BENCHMARK_SPLITS
            ),
            "default_pose_success_rmsd_threshold_angstrom": (
                vina_gnina_adapter.DEFAULT_POSE_SUCCESS_RMSD_THRESHOLD_ANGSTROM
            ),
            "source_checksum_policy": SOURCE_CHECKSUM_POLICY,
            "source_receipt_required_fields": common_source_receipt_fields,
            "source_actuality_policy": row_bundle.SOURCE_ACTUALITY_POLICY,
            "computed_comparison_fields": [
                "case_count",
                "engine_case_counts",
                "pose_success_rate",
                "symmetry_aware_rmsd_median_angstrom",
            ],
            "minimum_phase2_component_counts": minimum_component_counts,
            "feeds_components": ["vina_gnina_comparison_adapter"],
            "materialization_chain": [
                "materialize_public_benchmark_vina_gnina_comparison_adapter",
            ],
        },
        "phase2_outputs": {
            "operator_bundle": str(operator_bundle_out),
            "harness_materialization_report": str(harness_report_out),
            "artifact_bundle": str(artifact_bundle_out),
            "out_dir": str(out_dir),
            "required_artifact_roles": list(ARTIFACT_BUNDLE_ROLES),
            "minimum_phase2_component_counts": minimum_component_counts,
        },
        "claim_boundary": (
            "These row contracts describe operator-attached Phase 2 benchmark inputs. "
            "They do not download public benchmark files, approve redistribution, run "
            "docking engines, infer chemistry, or convert fixture/proxy rows into "
            "external beta evidence."
        ),
    }


def _row_inputs(
    *,
    subset_rows_path: Path | None,
    pose_rows_path: Path | None,
    enrichment_rows_path: Path | None,
    vina_gnina_rows_path: Path | None,
) -> dict[str, Path | None]:
    return {
        "subset_rows": subset_rows_path,
        "pose_rows": pose_rows_path,
        "enrichment_rows": enrichment_rows_path,
        "vina_gnina_rows": vina_gnina_rows_path,
    }


def _missing_components(row_inputs: dict[str, Path | None]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for component_id, required_inputs in COMPONENT_ROW_INPUTS.items():
        missing = [input_id for input_id in required_inputs if row_inputs[input_id] is None]
        blockers = [f"{input_id}_not_provided" for input_id in missing]
        components.append(
            {
                "component_id": component_id,
                "status": "operator_evidence_required",
                "contract_pass": False,
                "ready": False,
                "materialized": False,
                "required_row_inputs": list(required_inputs),
                "missing_row_inputs": missing,
                "expected_rows_mode": "operator_attached_public_benchmark_rows",
                "blockers": blockers,
                "outputs": {},
            }
        )
    return components


def _component_error(exc: Exception) -> dict[str, Any]:
    return {
        "component_id": "public_benchmark_phase2_row_materialization",
        "status": "blocked",
        "contract_pass": False,
        "ready": False,
        "materialized": False,
        "blockers": [f"public_benchmark_phase2_materialization_failed:{exc}"],
        "outputs": {},
    }


def _components_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for row in report.get("components", []):
        if not isinstance(row, dict):
            continue
        component_id = str(row.get("component_id") or "")
        components.append(
            {
                "component_id": component_id,
                "status": str(row.get("status") or ""),
                "contract_pass": bool(row.get("contract_pass")),
                "source_artifact_contract_pass": bool(
                    row.get("source_artifact_contract_pass")
                ),
                "ready": bool(row.get("ready")),
                "materialized": True,
                "artifact_role": str(row.get("artifact_role") or ""),
                "artifact": str(row.get("artifact") or ""),
                "count_field": str(row.get("count_field") or ""),
                "current_count": int(row.get("current_count") or 0),
                "required_minimum_count": int(row.get("required_minimum_count") or 0),
                "required_row_inputs": list(
                    COMPONENT_ROW_INPUTS.get(component_id, ())
                ),
                "missing_row_inputs": [],
                "expected_rows_mode": "operator_attached_public_benchmark_rows",
                "operator_evidence_required": not bool(row.get("ready")),
                "blockers": [str(blocker) for blocker in row.get("blockers", [])],
            }
        )
    return components


def build_public_benchmark_phase2_row_audit(
    *,
    repo_root: Path = ROOT,
    subset_rows_path: Path | None = None,
    pose_rows_path: Path | None = None,
    enrichment_rows_path: Path | None = None,
    vina_gnina_rows_path: Path | None = None,
    target_subset_case_count: int | None = None,
    operator_bundle_out: Path = DEFAULT_OPERATOR_BUNDLE_OUT,
    out_dir: Path = DEFAULT_OUT_DIR,
    harness_report_out: Path = DEFAULT_HARNESS_REPORT_OUT,
    artifact_bundle_out: Path = DEFAULT_ARTIFACT_BUNDLE_OUT,
) -> dict[str, Any]:
    row_intake_contracts = _row_intake_contracts(
        operator_bundle_out=operator_bundle_out,
        out_dir=out_dir,
        harness_report_out=harness_report_out,
        artifact_bundle_out=artifact_bundle_out,
        target_subset_case_count=target_subset_case_count,
    )
    row_inputs = _row_inputs(
        subset_rows_path=subset_rows_path,
        pose_rows_path=pose_rows_path,
        enrichment_rows_path=enrichment_rows_path,
        vina_gnina_rows_path=vina_gnina_rows_path,
    )
    input_paths = [
        Path("scripts/materialize_public_benchmark_phase2_from_rows.py"),
        Path("scripts/materialize_public_benchmark_operator_bundle_from_rows.py"),
        Path("scripts/materialize_public_benchmark_harness_bundle.py"),
    ]
    input_paths.extend(path for path in row_inputs.values() if path is not None)

    missing_input_ids = [
        input_id for input_id, path in row_inputs.items() if path is None
    ]
    if missing_input_ids:
        components = _missing_components(row_inputs)
        phase2_requirements = harness_bundle.build_phase2_requirement_rows(
            components
        )
        phase2_requirement_summary = (
            harness_bundle.build_phase2_requirement_summary(phase2_requirements)
        )
        blockers = [
            f"{component['component_id']}::{blocker}"
            for component in components
            for blocker in component["blockers"]
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            **release_evidence_metadata(
                input_paths=input_paths,
                reused_evidence=False,
                reuse_policy="public_benchmark_phase2_row_audit_from_operator_rows",
                repo_root=repo_root,
            ),
            "status": "operator_evidence_required",
            "contract_pass": False,
            "phase2_ready": False,
            "missing_row_inputs": missing_input_ids,
            "row_input_contract": ROW_INPUTS,
            "row_intake_contracts": row_intake_contracts,
            "blockers": blockers,
            "component_count": len(components),
            "component_ready_count": 0,
            "components": components,
            "phase2_requirements": phase2_requirements,
            "phase2_requirement_summary": phase2_requirement_summary,
            "outputs": {},
            "required_phase2_components": [
                dict(row) for row in harness_bundle.PHASE2_REQUIRED_COMPONENTS
            ],
            "claim_boundary": (
                "This runner only materializes operator-attached public benchmark row "
                "files through the existing Public Benchmark harness materializers. It "
                "does not download CASF/PDBBind, DUD-E, or LIT-PCBA data, approve "
                "licenses, run docking engines, infer chemistry, or treat fixture/proxy "
                "rows as actual Phase 2 evidence."
            ),
        }

    try:
        operator_bundle = row_bundle.build_public_benchmark_operator_bundle_from_rows(
            subset_rows_path=subset_rows_path or Path(),
            pose_rows_path=pose_rows_path or Path(),
            enrichment_rows_path=enrichment_rows_path or Path(),
            vina_gnina_rows_path=vina_gnina_rows_path or Path(),
            target_subset_case_count=target_subset_case_count,
            repo_root=repo_root,
        )
        _write_json(repo_root, operator_bundle_out, operator_bundle)
        materialization_report = (
            harness_bundle.materialize_public_benchmark_harness_bundle(
                operator_bundle,
                repo_root=repo_root,
                bundle_path=operator_bundle_out,
                out_dir=out_dir,
                target_subset_case_count=target_subset_case_count,
            )
        )
        _write_json(repo_root, harness_report_out, materialization_report)
        artifact_bundle = harness_bundle.materialize_public_benchmark_artifact_bundle(
            _artifact_paths_for_out_dir(repo_root, out_dir),
            repo_root=repo_root,
        )
        _write_json(repo_root, artifact_bundle_out, artifact_bundle)
    except Exception as exc:
        components = [_component_error(exc)]
        phase2_requirements = harness_bundle.build_phase2_requirement_rows(
            components
        )
        phase2_requirement_summary = (
            harness_bundle.build_phase2_requirement_summary(phase2_requirements)
        )
        blockers = [
            f"{components[0]['component_id']}::{blocker}"
            for blocker in components[0]["blockers"]
        ]
        return {
            "schema_version": SCHEMA_VERSION,
            **release_evidence_metadata(
                input_paths=input_paths,
                reused_evidence=False,
                reuse_policy="public_benchmark_phase2_row_audit_from_operator_rows",
                repo_root=repo_root,
            ),
            "status": "blocked",
            "contract_pass": False,
            "phase2_ready": False,
            "missing_row_inputs": [],
            "row_input_contract": ROW_INPUTS,
            "row_intake_contracts": row_intake_contracts,
            "blockers": blockers,
            "component_count": len(components),
            "component_ready_count": 0,
            "components": components,
            "phase2_requirements": phase2_requirements,
            "phase2_requirement_summary": phase2_requirement_summary,
            "outputs": {},
            "claim_boundary": (
                "Public Benchmark Phase 2 row materialization failed before any "
                "readiness claim could be made."
            ),
        }

    components = _components_from_report(materialization_report)
    phase2_requirements = harness_bundle.build_phase2_requirement_rows(components)
    phase2_requirement_summary = harness_bundle.build_phase2_requirement_summary(
        phase2_requirements
    )
    operator_materialization_report = operator_bundle.get("materialization_report", {})
    if not isinstance(operator_materialization_report, dict):
        operator_materialization_report = {}
    source_actuality_check = operator_materialization_report.get("source_actuality_check", {})
    if not isinstance(source_actuality_check, dict):
        source_actuality_check = {}
    source_actuality_blockers = [
        str(blocker)
        for blocker in source_actuality_check.get("blockers", [])
        if str(blocker)
    ]
    phase2_ready = bool(
        materialization_report.get("phase2_ready")
        and artifact_bundle.get("phase2_ready")
        and not source_actuality_blockers
    )
    phase2_exit_gate = materialization_report.get("phase2_exit_gate")
    if not isinstance(phase2_exit_gate, dict):
        phase2_exit_gate = {}
    failed_criteria = [
        str(item) for item in phase2_exit_gate.get("failed_criteria", [])
    ]
    blockers = [
        str(blocker)
        for blocker in materialization_report.get("blockers", [])
        if str(blocker)
    ]
    blockers.extend(f"phase2_exit_gate::{criterion}" for criterion in failed_criteria)
    blockers.extend(
        f"operator_bundle_source_actuality::{blocker}"
        for blocker in source_actuality_blockers
    )
    blockers.extend(
        f"{component['component_id']}::{blocker}"
        for component in components
        for blocker in component.get("blockers", [])
    )
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_phase2_row_audit_from_operator_rows",
            repo_root=repo_root,
        ),
        "status": "ready" if phase2_ready else "operator_evidence_required",
        "contract_pass": phase2_ready,
        "phase2_ready": phase2_ready,
        "tier_beta_ready": bool(materialization_report.get("tier_beta_ready")),
        "missing_row_inputs": [],
        "row_input_contract": ROW_INPUTS,
        "row_intake_contracts": row_intake_contracts,
            "operator_bundle_materialization_report": operator_materialization_report,
            "operator_bundle_source_actuality_check": source_actuality_check,
        "phase2_exit_gate": phase2_exit_gate,
        "blockers": blockers,
        "component_count": len(components),
        "component_ready_count": sum(1 for component in components if component["ready"]),
        "components": components,
        "phase2_requirements": phase2_requirements,
        "phase2_requirement_summary": phase2_requirement_summary,
        "outputs": {
            "operator_bundle": str(operator_bundle_out),
            "harness_materialization_report": str(harness_report_out),
            "artifact_bundle": str(artifact_bundle_out),
            "out_dir": str(out_dir),
        },
        "required_phase2_components": [
            dict(row) for row in harness_bundle.PHASE2_REQUIRED_COMPONENTS
        ],
        "claim_boundary": (
            "This runner only materializes operator-attached public benchmark row files "
            "through the existing Public Benchmark harness materializers. It does not "
            "download CASF/PDBBind, DUD-E, or LIT-PCBA data, approve licenses, run "
            "docking engines, infer chemistry, or treat fixture/proxy rows as actual "
            "Phase 2 evidence."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--subset-rows", type=Path)
    parser.add_argument("--pose-rows", type=Path)
    parser.add_argument("--enrichment-rows", type=Path)
    parser.add_argument("--vina-gnina-rows", type=Path)
    parser.add_argument("--target-subset-case-count", type=int)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--operator-bundle-out", type=Path, default=DEFAULT_OPERATOR_BUNDLE_OUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--harness-report-out", type=Path, default=DEFAULT_HARNESS_REPORT_OUT)
    parser.add_argument("--artifact-bundle-out", type=Path, default=DEFAULT_ARTIFACT_BUNDLE_OUT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_public_benchmark_phase2_row_audit(
        repo_root=args.repo_root,
        subset_rows_path=args.subset_rows,
        pose_rows_path=args.pose_rows,
        enrichment_rows_path=args.enrichment_rows,
        vina_gnina_rows_path=args.vina_gnina_rows,
        target_subset_case_count=args.target_subset_case_count,
        operator_bundle_out=args.operator_bundle_out,
        out_dir=args.out_dir,
        harness_report_out=args.harness_report_out,
        artifact_bundle_out=args.artifact_bundle_out,
    )
    _write_json(args.repo_root, args.out, payload)
    print(
        "public-benchmark-phase2-row-audit: "
        f"{payload['status']} | ready={payload['component_ready_count']}/"
        f"{payload['component_count']} | blockers={len(payload['blockers'])}"
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
