#!/usr/bin/env python3
"""Materialize or index public benchmark harness bundle artifacts."""

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

from build_public_benchmark_operator_intake_packet import (  # noqa: E402
    build_public_benchmark_operator_intake_packet,
)
from build_public_benchmark_source_of_truth import build_source_of_truth  # noqa: E402
from materialize_public_benchmark_enrichment_scorecard import (  # noqa: E402
    materialize_enrichment_scorecard,
)
from materialize_public_benchmark_pose_success_harness import (  # noqa: E402
    materialize_pose_success_harness,
)
from materialize_public_benchmark_pose_validity_input import (  # noqa: E402
    materialize_pose_validity_input,
)
from materialize_public_benchmark_posebusters_validity_packet import (  # noqa: E402
    materialize_posebusters_validity_packet,
)
from materialize_public_benchmark_rmsd_scorecard import (  # noqa: E402
    materialize_rmsd_scorecard,
)
from materialize_public_benchmark_subset_manifest import (  # noqa: E402
    materialize_subset_manifest,
)
from materialize_public_benchmark_vina_gnina_comparison_adapter import (  # noqa: E402
    materialize_vina_gnina_comparison_adapter,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402
from validate_public_benchmark_external_receipts import (  # noqa: E402
    validate_external_receipts,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
ARTIFACT_BUNDLE_SCHEMA_VERSION = "public-benchmark-harness-bundle.v1"
FULL_MATERIALIZER_SCHEMA_VERSION = (
    "public-benchmark-harness-bundle-materialization.v1"
)

DEFAULT_ARTIFACT_BUNDLE_OUT = PRODUCTIZATION / "public_benchmark_harness_bundle.json"
DEFAULT_OUT_DIR = PRODUCTIZATION
DEFAULT_REPORT_NAME = "public_benchmark_harness_bundle_materialization_report.json"
DEFAULT_ARTIFACTS = (
    PRODUCTIZATION / "public_benchmark_subset_manifest.json",
    PRODUCTIZATION / "public_benchmark_pose_validity_packet.json",
    PRODUCTIZATION / "public_benchmark_symmetry_rmsd_scorecard.json",
    PRODUCTIZATION / "public_benchmark_pose_success_harness.json",
    PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json",
    PRODUCTIZATION / "public_benchmark_vina_gnina_comparison_adapter.json",
    PRODUCTIZATION / "public_benchmark_external_receipts_validation.json",
)

ARTIFACT_FILENAMES = {
    "subset_manifest": "public_benchmark_subset_manifest.json",
    "pose_validity_input": "public_benchmark_pose_validity_input.json",
    "pose_validity_packet": "public_benchmark_pose_validity_packet.json",
    "rmsd_scorecard": "public_benchmark_symmetry_rmsd_scorecard.json",
    "pose_success_harness": "public_benchmark_pose_success_harness.json",
    "enrichment_scorecard": "public_benchmark_enrichment_scorecard.json",
    "vina_gnina_comparison_adapter": "public_benchmark_vina_gnina_comparison_adapter.json",
    "external_receipts_validation": "public_benchmark_external_receipts_validation.json",
    "source_of_truth": "public_benchmark_source_of_truth.json",
}

SLOT_ALIASES = {
    "casf_pdbbind_subset_intake": (
        "casf_pdbbind_subset_intake",
        "casf_pdbbind_subset",
        "subset_manifest_intake",
        "subset",
    ),
    "pose_coordinate_intake": (
        "pose_coordinate_intake",
        "pose_coordinates",
        "pose_validity_intake",
        "pose",
    ),
    "dud_e_lit_pcba_enrichment_intake": (
        "dud_e_lit_pcba_enrichment_intake",
        "enrichment_intake",
        "enrichment",
    ),
    "vina_gnina_comparison_intake": (
        "vina_gnina_comparison_intake",
        "vina_gnina_intake",
        "vina_gnina",
    ),
}

READY_FIELDS = {
    "subset_manifest": "public_benchmark_ready",
    "pose_validity_input": "pose_validity_ready",
    "pose_validity_packet": "posebusters_validity_ready",
    "rmsd_scorecard": "scorecard_ready",
    "pose_success_harness": "pose_success_harness_ready",
    "enrichment_scorecard": "public_benchmark_enrichment_ready",
    "vina_gnina_comparison_adapter": "public_benchmark_engine_comparison_ready",
    "external_receipts_validation": "public_benchmark_external_receipts_ready",
    "source_of_truth": "public_benchmark_ready",
}

ARTIFACT_ROLE_BY_FILENAME = {
    filename: role for role, filename in ARTIFACT_FILENAMES.items()
}

PHASE2_REQUIRED_COMPONENTS = (
    {
        "component_id": "casf_pdbbind_pose_success_harness",
        "requirement": "CASF/PDBBind pose-success harness",
        "artifact_role": "pose_success_harness",
        "criterion_id": "casf_pdbbind_pose_success_harness_ready",
        "ready_field": READY_FIELDS["pose_success_harness"],
        "count_field": "real_benchmark_case_count",
        "required_minimum_count": 1,
    },
    {
        "component_id": "symmetry_aware_ligand_rmsd",
        "requirement": "Symmetry-aware ligand RMSD scorecard",
        "artifact_role": "rmsd_scorecard",
        "criterion_id": "symmetry_aware_ligand_rmsd_ready",
        "ready_field": READY_FIELDS["rmsd_scorecard"],
        "count_field": "real_benchmark_case_count",
        "required_minimum_count": 1,
    },
    {
        "component_id": "posebusters_style_pose_validity",
        "requirement": "PoseBusters-style pose validity packet",
        "artifact_role": "pose_validity_packet",
        "criterion_id": "posebusters_style_pose_validity_ready",
        "ready_field": READY_FIELDS["pose_validity_packet"],
        "count_field": "real_benchmark_case_count",
        "required_minimum_count": 1,
    },
    {
        "component_id": "vina_gnina_comparison_adapter",
        "requirement": "Vina/GNINA comparison adapter",
        "artifact_role": "vina_gnina_comparison_adapter",
        "criterion_id": "vina_gnina_comparison_ready",
        "ready_field": READY_FIELDS["vina_gnina_comparison_adapter"],
        "count_field": "real_comparison_case_count",
        "required_minimum_count": 1,
    },
    {
        "component_id": "dud_e_or_lit_pcba_enrichment",
        "requirement": "DUD-E or LIT-PCBA enrichment scorecard",
        "artifact_role": "enrichment_scorecard",
        "criterion_id": "dud_e_or_lit_pcba_enrichment_ready",
        "ready_field": READY_FIELDS["enrichment_scorecard"],
        "count_field": "real_enrichment_target_count",
        "required_minimum_count": 1,
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _slot_payload(bundle: dict[str, Any], slot_id: str) -> dict[str, Any]:
    for key in SLOT_ALIASES[slot_id]:
        payload = bundle.get(key)
        if isinstance(payload, dict):
            return payload
    return {}


def _resolve_out_dir(out_dir: Path, *, repo_root: Path) -> Path:
    return out_dir if out_dir.is_absolute() else repo_root / out_dir


def _display_path(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_text(payload), encoding="utf-8")


def _ready_from_payload(
    *,
    payload: dict[str, Any],
    ready_field: str,
    exists: bool,
    blockers: list[str],
) -> bool:
    if not exists or blockers:
        return False
    if ready_field in payload:
        return bool(payload.get(ready_field))
    if payload.get("contract_pass") is False:
        return False
    return str(payload.get("status") or "") == "ready"


def _artifact_counts(payload: dict[str, Any]) -> dict[str, int]:
    report = _as_dict(payload.get("materialization_report"))
    return {
        "target_subset_case_count": _as_int(
            payload.get("target_subset_case_count")
            or report.get("target_subset_case_count")
        ),
        "materialized_case_count": _as_int(
            payload.get("materialized_case_count")
            or report.get("materialized_case_count")
        ),
        "real_benchmark_case_count": _as_int(
            payload.get("real_benchmark_case_count")
            or report.get("real_benchmark_case_count")
        ),
        "real_enrichment_target_count": _as_int(
            payload.get("real_enrichment_target_count")
            or report.get("real_enrichment_target_count")
        ),
        "real_comparison_case_count": _as_int(
            payload.get("real_comparison_case_count")
            or report.get("real_comparison_case_count")
        ),
    }


def _phase2_component_rows(
    artifact_summaries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    summary_by_role = {
        str(summary.get("artifact_role")): summary for summary in artifact_summaries
    }
    rows: list[dict[str, Any]] = []
    for required in PHASE2_REQUIRED_COMPONENTS:
        role = str(required["artifact_role"])
        summary = summary_by_role.get(role, {})
        count_field = str(required["count_field"])
        current_count = _as_int(summary.get(count_field))
        required_minimum_count = _as_int(required["required_minimum_count"], default=1)
        blockers = [str(blocker) for blocker in _as_list(summary.get("blockers"))]
        if not summary:
            blockers.append(f"phase2_component_artifact_missing:{role}")
        elif not bool(summary.get("exists", True)):
            blockers.append(f"phase2_component_artifact_missing:{role}")
        if current_count < required_minimum_count:
            blockers.append(
                f"{count_field}_below_required:"
                f"{current_count}<{required_minimum_count}"
            )
        contract_pass = summary.get("contract_pass") is True
        ready = bool(
            summary
            and summary.get("exists", True)
            and summary.get("ready")
            and contract_pass
            and current_count >= required_minimum_count
            and not blockers
        )
        rows.append(
            {
                "component_id": str(required["component_id"]),
                "requirement": str(required["requirement"]),
                "artifact_role": role,
                "artifact": str(summary.get("artifact") or ""),
                "schema_version": str(summary.get("schema_version") or ""),
                "status": str(summary.get("status") or "artifact_missing"),
                "contract_pass": contract_pass,
                "ready_field": str(required["ready_field"]),
                "ready": ready,
                "count_field": count_field,
                "current_count": current_count,
                "required_minimum_count": required_minimum_count,
                "blocker_count": len(blockers),
                "blockers": blockers,
            }
        )
    return rows


def _build_phase2_exit_gate(
    component_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    component_by_id = {
        str(row["component_id"]): row for row in component_rows
    }
    criteria: list[dict[str, Any]] = []
    for required in PHASE2_REQUIRED_COMPONENTS:
        component_id = str(required["component_id"])
        component = component_by_id.get(component_id, {})
        blockers = [str(blocker) for blocker in _as_list(component.get("blockers"))]
        criteria.append(
            {
                "criterion_id": str(required["criterion_id"]),
                "component_id": component_id,
                "artifact_role": str(required["artifact_role"]),
                "pass": bool(component.get("ready")),
                "current": {
                    str(required["count_field"]): _as_int(
                        component.get("current_count")
                    ),
                    "ready": bool(component.get("ready")),
                    "contract_pass": bool(component.get("contract_pass")),
                },
                "required": {
                    str(required["count_field"]): _as_int(
                        required["required_minimum_count"],
                        default=1,
                    ),
                    "ready": True,
                    "contract_pass": True,
                },
                "blockers": blockers,
            }
        )
    failed_criteria = [
        str(row["criterion_id"]) for row in criteria if not bool(row["pass"])
    ]
    return {
        "claim": "public_benchmark_harness_phase2_exit_gate",
        "status": "ready" if not failed_criteria else "blocked",
        "criteria": criteria,
        "failed_criteria": failed_criteria,
        "failed_criterion_count": len(failed_criteria),
        "component_count": len(component_rows),
        "ready_component_count": sum(1 for row in component_rows if row["ready"]),
        "required_component_count": len(PHASE2_REQUIRED_COMPONENTS),
    }


def materialize_public_benchmark_artifact_bundle(
    artifact_paths: list[Path],
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    for path in artifact_paths:
        resolved = path if path.is_absolute() else repo_root / path
        payload = _load_json(resolved)
        exists = resolved.exists()
        if not exists:
            blockers.append(f"artifact_missing:{path.as_posix()}")
        role = ARTIFACT_ROLE_BY_FILENAME.get(path.name)
        if role is None:
            artifact_blockers = [
                str(blocker) for blocker in _as_list(payload.get("blockers"))
            ]
            rows.append(
                {
                    "artifact_role": "",
                    "artifact": path.as_posix(),
                    "exists": exists,
                    "schema_version": str(payload.get("schema_version") or ""),
                    "status": str(payload.get("status") or ""),
                    "contract_pass": payload.get("contract_pass"),
                    **_artifact_counts(payload),
                    "ready_field": "",
                    "ready": False,
                    "blocker_count": len(artifact_blockers),
                    "blockers": artifact_blockers,
                }
            )
            continue
        rows.append(
            _artifact_summary(
                role=role,
                artifact_path=resolved,
                payload=payload,
                repo_root=repo_root,
                exists=exists,
            )
        )

    phase2_components = _phase2_component_rows(rows)
    phase2_exit_gate = _build_phase2_exit_gate(phase2_components)
    phase2_ready = phase2_exit_gate["status"] == "ready"

    return {
        "schema_version": ARTIFACT_BUNDLE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/materialize_public_benchmark_harness_bundle.py"),
                *artifact_paths,
            ],
            reused_evidence=False,
            reuse_policy="public_benchmark_harness_bundle_from_materialized_local_artifacts",
            repo_root=repo_root,
        ),
        "status": "ready" if not blockers else "artifact_bundle_incomplete",
        "contract_pass": not blockers,
        "artifact_count": len(rows),
        "missing_artifact_count": len(blockers),
        "artifact_rows": rows,
        "required_components": list(PHASE2_REQUIRED_COMPONENTS),
        "components": phase2_components,
        "phase2_ready": phase2_ready,
        "phase2_exit_gate": phase2_exit_gate,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": FULL_MATERIALIZER_SCHEMA_VERSION,
            "artifact_count": len(rows),
            "missing_artifact_count": len(blockers),
            "phase2_component_count": len(phase2_components),
            "phase2_ready_component_count": sum(
                1 for row in phase2_components if row["ready"]
            ),
            "phase2_ready": phase2_ready,
        },
        "claim_boundary": (
            "This bundle indexes local public-benchmark harness artifacts only. "
            "It does not fetch benchmark data, run docking engines, attach external "
            "receipts, or promote Tier beta readiness by itself."
        ),
    }


def _artifact_summary(
    *,
    role: str,
    artifact_path: Path,
    payload: dict[str, Any],
    repo_root: Path,
    exists: bool = True,
) -> dict[str, Any]:
    ready_field = READY_FIELDS[role]
    blockers = [str(blocker) for blocker in _as_list(payload.get("blockers"))]
    return {
        "artifact_role": role,
        "artifact": _display_path(artifact_path, repo_root=repo_root),
        "exists": exists,
        "schema_version": str(payload.get("schema_version") or ""),
        "status": str(payload.get("status") or ""),
        "contract_pass": payload.get("contract_pass"),
        **_artifact_counts(payload),
        "ready_field": ready_field,
        "ready": _ready_from_payload(
            payload=payload,
            ready_field=ready_field,
            exists=exists,
            blockers=blockers,
        ),
        "blocker_count": len(blockers),
        "blockers": blockers,
    }


def _collect_blockers(artifact_summaries: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for summary in artifact_summaries:
        role = str(summary["artifact_role"])
        for blocker in _as_list(summary.get("blockers")):
            blockers.append(f"{role}:{blocker}")
    return blockers


def materialize_public_benchmark_harness_bundle(
    bundle_payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    bundle_path: Path | None = None,
    out_dir: Path = DEFAULT_OUT_DIR,
    target_subset_case_count: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    resolved_out_dir = _resolve_out_dir(out_dir, repo_root=repo_root)
    paths = {
        role: resolved_out_dir / filename
        for role, filename in ARTIFACT_FILENAMES.items()
    }

    subset_intake = _slot_payload(bundle_payload, "casf_pdbbind_subset_intake")
    pose_intake = _slot_payload(bundle_payload, "pose_coordinate_intake")
    enrichment_intake = _slot_payload(
        bundle_payload, "dud_e_lit_pcba_enrichment_intake"
    )
    vina_gnina_intake = _slot_payload(bundle_payload, "vina_gnina_comparison_intake")
    target_count = (
        target_subset_case_count
        or bundle_payload.get("target_subset_case_count")
        or subset_intake.get("target_subset_case_count")
    )

    subset_manifest = materialize_subset_manifest(
        subset_intake,
        repo_root=repo_root,
        intake_path=bundle_path,
        target_subset_case_count=int(target_count) if target_count else None,
    )
    pose_validity_input = materialize_pose_validity_input(
        subset_manifest,
        pose_intake,
        repo_root=repo_root,
        subset_manifest_path=paths["subset_manifest"],
        pose_intake_path=bundle_path,
    )
    pose_validity_packet = materialize_posebusters_validity_packet(
        pose_validity_input,
        repo_root=repo_root,
        pose_validity_input_path=paths["pose_validity_input"],
    )
    rmsd_scorecard = materialize_rmsd_scorecard(
        pose_validity_input,
        repo_root=repo_root,
        pose_validity_input_path=paths["pose_validity_input"],
    )
    pose_success_harness = materialize_pose_success_harness(
        pose_validity_packet,
        rmsd_scorecard,
        repo_root=repo_root,
        pose_validity_packet_path=paths["pose_validity_packet"],
        rmsd_scorecard_path=paths["rmsd_scorecard"],
    )
    enrichment_scorecard = materialize_enrichment_scorecard(
        enrichment_intake,
        repo_root=repo_root,
        intake_path=bundle_path,
    )
    vina_gnina_comparison_adapter = materialize_vina_gnina_comparison_adapter(
        vina_gnina_intake,
        repo_root=repo_root,
        intake_path=bundle_path,
    )
    external_receipts_validation = validate_external_receipts(
        subset_manifest=subset_manifest,
        enrichment_scorecard=enrichment_scorecard,
        vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
    )
    operator_intake_packet = build_public_benchmark_operator_intake_packet(
        repo_root=repo_root
    )

    artifacts: dict[str, dict[str, Any]] = {
        "subset_manifest": subset_manifest,
        "pose_validity_input": pose_validity_input,
        "pose_validity_packet": pose_validity_packet,
        "rmsd_scorecard": rmsd_scorecard,
        "pose_success_harness": pose_success_harness,
        "enrichment_scorecard": enrichment_scorecard,
        "vina_gnina_comparison_adapter": vina_gnina_comparison_adapter,
        "external_receipts_validation": external_receipts_validation,
    }

    source_refresh_error = ""
    try:
        source_of_truth = build_source_of_truth(
            subset_manifest=subset_manifest,
            pose_validity_packet=pose_validity_packet,
            rmsd_scorecard=rmsd_scorecard,
            pose_success_harness=pose_success_harness,
            enrichment_scorecard=enrichment_scorecard,
            vina_gnina_comparison_adapter=vina_gnina_comparison_adapter,
            external_receipts_validation=external_receipts_validation,
            operator_intake_packet=operator_intake_packet,
            repo_root=repo_root,
        )
    except Exception as exc:
        source_refresh_error = f"{exc.__class__.__name__}: {exc}"
        source_of_truth = {
            "schema_version": "public-benchmark-source-of-truth.v1",
            "status": "source_refresh_failed",
            "contract_pass": False,
            "public_benchmark_ready": False,
            "tier_beta_ready": False,
            "blockers": [
                f"public_benchmark_source_of_truth_refresh_failed:{exc.__class__.__name__}"
            ],
        }
    artifacts["source_of_truth"] = source_of_truth

    for role, payload in artifacts.items():
        _write_json(paths[role], payload)

    artifact_summaries = [
        _artifact_summary(
            role=role,
            artifact_path=paths[role],
            payload=payload,
            repo_root=repo_root,
        )
        for role, payload in artifacts.items()
    ]
    blockers = _collect_blockers(artifact_summaries)
    if source_refresh_error:
        blockers.append(f"source_of_truth:{source_refresh_error}")

    phase2_components = _phase2_component_rows(artifact_summaries)
    phase2_exit_gate = _build_phase2_exit_gate(phase2_components)
    phase2_ready = phase2_exit_gate["status"] == "ready"
    source_tier_beta_ready = bool(source_of_truth.get("tier_beta_ready"))
    tier_beta_ready = bool(source_tier_beta_ready and phase2_ready)
    bundle_ready = bool(source_of_truth.get("public_benchmark_ready")) and bool(
        phase2_ready and not blockers
    )
    report_input_paths = [
        Path("scripts/materialize_public_benchmark_harness_bundle.py")
    ]
    if bundle_path is not None:
        report_input_paths.append(bundle_path)

    return {
        "schema_version": FULL_MATERIALIZER_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=report_input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_harness_materialized_from_operator_bundle",
            repo_root=repo_root,
        ),
        "status": "ready" if bundle_ready else "operator_evidence_required",
        "contract_pass": bundle_ready,
        "public_benchmark_ready": bool(source_of_truth.get("public_benchmark_ready")),
        "tier_beta_ready": tier_beta_ready,
        "source_of_truth_tier_beta_ready": source_tier_beta_ready,
        "required_components": list(PHASE2_REQUIRED_COMPONENTS),
        "components": phase2_components,
        "phase2_ready": phase2_ready,
        "phase2_exit_gate": phase2_exit_gate,
        "target_subset_case_count": int(
            subset_manifest.get("target_subset_case_count") or 0
        ),
        "materialized_subset_case_count": int(
            subset_manifest.get("materialized_case_count") or 0
        ),
        "real_pose_case_count": int(
            pose_validity_input.get("real_benchmark_case_count") or 0
        ),
        "real_pose_success_harness_case_count": int(
            pose_success_harness.get("real_benchmark_case_count") or 0
        ),
        "real_enrichment_target_count": int(
            enrichment_scorecard.get("real_enrichment_target_count") or 0
        ),
        "real_vina_gnina_comparison_case_count": int(
            vina_gnina_comparison_adapter.get("real_comparison_case_count") or 0
        ),
        "artifact_outputs": {
            role: _display_path(path, repo_root=repo_root)
            for role, path in paths.items()
        },
        "artifact_summaries": artifact_summaries,
        "ready_artifact_count": sum(1 for row in artifact_summaries if row["ready"]),
        "blocked_artifact_count": sum(
            1 for row in artifact_summaries if not row["ready"]
        ),
        "phase2_ready_component_count": sum(
            1 for row in phase2_components if row["ready"]
        ),
        "phase2_blocked_component_count": sum(
            1 for row in phase2_components if not row["ready"]
        ),
        "blocker_count": len(blockers),
        "blockers": blockers,
        "source_refresh_error": source_refresh_error,
        "tier_beta_gate": _as_dict(source_of_truth.get("tier_beta_gate")),
        "claim_boundary": (
            "This bundle materializer only consumes operator-attached local benchmark "
            "descriptors, coordinates, scores, and receipts. It does not download, "
            "license, redistribute, or approve external benchmark data."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--target-subset-case-count", type=int)
    parser.add_argument("--artifact", type=Path, action="append", dest="artifacts")
    parser.add_argument("--out", type=Path, default=DEFAULT_ARTIFACT_BUNDLE_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.bundle is not None:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        report = materialize_public_benchmark_harness_bundle(
            bundle,
            repo_root=args.repo_root,
            bundle_path=args.bundle,
            out_dir=args.out_dir,
            target_subset_case_count=args.target_subset_case_count,
        )
        out_dir = _resolve_out_dir(args.out_dir, repo_root=args.repo_root.resolve())
        out_report = args.out_report or out_dir / DEFAULT_REPORT_NAME
        _write_json(out_report, report)
        print(
            "public-benchmark-harness-bundle-materialization: "
            f"{report['status']} | tier_beta_ready={report['tier_beta_ready']} | "
            f"ready_artifacts={report['ready_artifact_count']}/"
            f"{len(report['artifact_summaries'])} | blockers={report['blocker_count']}"
        )
        return 1 if args.fail_blocked and not report["tier_beta_ready"] else 0

    artifacts = list(args.artifacts or DEFAULT_ARTIFACTS)
    artifact_bundle = materialize_public_benchmark_artifact_bundle(
        artifacts,
        repo_root=args.repo_root,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_json_text(artifact_bundle), encoding="utf-8")
    if args.json:
        print(_json_text(artifact_bundle), end="")
    else:
        print(
            "public-benchmark-harness-bundle: "
            f"{artifact_bundle['status']} | "
            f"artifacts={artifact_bundle['artifact_count']} | "
            f"missing={artifact_bundle['missing_artifact_count']}"
        )
    return 1 if args.fail_blocked and not artifact_bundle["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
