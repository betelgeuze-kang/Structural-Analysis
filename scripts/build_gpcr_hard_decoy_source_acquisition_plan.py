#!/usr/bin/env python3
"""Build the GPCR hard-decoy source acquisition plan."""

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

from materialize_gpcr_hard_decoy_suite_report import (  # noqa: E402
    ACTUAL_CLOSURE_CRITERION_ID,
    EXIT_CRITERIA,
    RAW_ROW_QUALITY_CRITERIA,
    REQUIRED_TARGETS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_source_acquisition_plan.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_ROWS_OUT = PRODUCTIZATION / "gpcr_hard_decoy_rows.json"
DEFAULT_POSITIVE_SOURCE_SNAPSHOT = (
    PRODUCTIZATION / "gpcr_hard_decoy_positive_source_snapshot.json"
)
DEFAULT_POSITIVE_SOURCE_SNAPSHOT_MD = DEFAULT_POSITIVE_SOURCE_SNAPSHOT.with_suffix(
    ".md"
)
DEFAULT_DECOY_SOURCE_SNAPSHOT = (
    PRODUCTIZATION / "gpcr_hard_decoy_decoy_source_snapshot.json"
)
DEFAULT_DECOY_SOURCE_SNAPSHOT_MD = DEFAULT_DECOY_SOURCE_SNAPSHOT.with_suffix(".md")
DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"

SCHEMA_VERSION = "gpcr-hard-decoy-source-acquisition-plan.v1"
CHEMBL_API_ROOT = "https://www.ebi.ac.uk/chembl/api/data"
TARGET_SOURCES = (
    {
        "target_id": "DRD2",
        "gene_symbol": "DRD2",
        "organism": "Homo sapiens",
        "uniprot_accession": "P14416",
        "chembl_target_id": "CHEMBL217",
        "chembl_pref_name": "D(2) dopamine receptor",
        "target_type": "SINGLE PROTEIN",
    },
    {
        "target_id": "HTR2A",
        "gene_symbol": "HTR2A",
        "organism": "Homo sapiens",
        "uniprot_accession": "P28223",
        "chembl_target_id": "CHEMBL224",
        "chembl_pref_name": "5-hydroxytryptamine receptor 2A",
        "target_type": "SINGLE PROTEIN",
    },
    {
        "target_id": "OPRM1",
        "gene_symbol": "OPRM1",
        "organism": "Homo sapiens",
        "uniprot_accession": "P35372",
        "chembl_target_id": "CHEMBL233",
        "chembl_pref_name": "Mu-type opioid receptor",
        "target_type": "SINGLE PROTEIN",
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    if not resolved.exists():
        return {}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _positive_source_snapshot_summary(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "artifact": str(DEFAULT_POSITIVE_SOURCE_SNAPSHOT),
        "markdown_artifact": str(DEFAULT_POSITIVE_SOURCE_SNAPSHOT_MD),
        "status": str(snapshot.get("status") or "missing"),
        "contract_pass": snapshot.get("contract_pass"),
        "positive_source_ready": bool(snapshot.get("positive_source_ready")),
        "actual_closure_ready": bool(snapshot.get("actual_closure_ready")),
        "target_candidate_counts": dict(snapshot.get("target_candidate_counts") or {}),
        "total_positive_candidate_count": int(
            snapshot.get("total_positive_candidate_count") or 0
        ),
        "minimum_positive_rows_per_target": int(
            snapshot.get("minimum_positive_rows_per_target") or 0
        ),
        "closure_blockers": [
            str(row) for row in snapshot.get("closure_blockers", [])
        ]
        if isinstance(snapshot.get("closure_blockers"), list)
        else [],
        "blocker_count": int(snapshot.get("blocker_count") or 0),
        "command": (
            "python3 scripts/build_gpcr_hard_decoy_positive_source_snapshot.py "
            f"--out {DEFAULT_POSITIVE_SOURCE_SNAPSHOT} "
            f"--out-md {DEFAULT_POSITIVE_SOURCE_SNAPSHOT_MD}"
        ),
    }


def _decoy_source_snapshot_summary(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    summary = snapshot.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    return {
        "artifact": str(DEFAULT_DECOY_SOURCE_SNAPSHOT),
        "markdown_artifact": str(DEFAULT_DECOY_SOURCE_SNAPSHOT_MD),
        "status": str(snapshot.get("status") or "missing"),
        "contract_pass": snapshot.get("contract_pass"),
        "decoy_candidate_source_ready": bool(
            snapshot.get("decoy_candidate_source_ready")
        ),
        "actual_closure_ready": bool(snapshot.get("actual_closure_ready")),
        "target_candidate_counts": dict(snapshot.get("target_candidate_counts") or {}),
        "total_decoy_candidate_count": int(
            snapshot.get("total_decoy_candidate_count") or 0
        ),
        "minimum_decoy_rows_per_target": int(
            snapshot.get("minimum_decoy_rows_per_target") or 0
        ),
        "minimum_decoy_standard_value_nm": float(
            snapshot.get("minimum_decoy_standard_value_nm") or 0.0
        ),
        "closure_blockers": [
            str(row) for row in snapshot.get("closure_blockers", [])
        ]
        if isinstance(snapshot.get("closure_blockers"), list)
        else [],
        "blocker_count": int(snapshot.get("blocker_count") or 0),
        "command": (
            "python3 scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py "
            f"--out {DEFAULT_DECOY_SOURCE_SNAPSHOT} "
            f"--out-md {DEFAULT_DECOY_SOURCE_SNAPSHOT_MD}"
        ),
    }


def _target_query_url(uniprot_accession: str) -> str:
    return (
        f"{CHEMBL_API_ROOT}/target.json?"
        f"target_components__accession={uniprot_accession}"
        "&target_type=SINGLE+PROTEIN&format=json&limit=20"
    )


def _target_source(row: dict[str, str]) -> dict[str, Any]:
    chembl_target_id = row["chembl_target_id"]
    target_id = row["target_id"]
    return {
        **row,
        "source_role": "target_activity_candidate_source_only",
        "official_target_query_url": _target_query_url(row["uniprot_accession"]),
        "chembl_target_record_url": f"{CHEMBL_API_ROOT}/target/{chembl_target_id}.json",
        "chembl_activity_query_template": (
            f"{CHEMBL_API_ROOT}/activity.json?target_chembl_id={chembl_target_id}"
            "&standard_type__in=Ki,IC50,Kd,EC50&limit=1000"
        ),
        "minimum_positive_rows_required": int(
            RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"]
        ),
        "minimum_decoy_rows_required": int(
            RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"]
        ),
        "minimum_total_rows_required": int(
            RAW_ROW_QUALITY_CRITERIA["min_total_row_count_per_target"]
        ),
        "target_specific_row_filter": {
            "target_id": target_id,
            "organism": "Homo sapiens",
            "chembl_target_id": chembl_target_id,
            "uniprot_accession": row["uniprot_accession"],
        },
        "claim_boundary": (
            "The ChEMBL target and activity endpoints can identify target-linked "
            "positive ligand and weak/low-affinity decoy candidates, but they do "
            "not by themselves provide the curated target-specific hard-decoy set, "
            "scoring run, or Phase 3 closure rows."
        ),
    }


def _per_target_exit_gate(target_id: str) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "required_rows": dict(RAW_ROW_QUALITY_CRITERIA),
        "required_metrics": {
            "ranking_pr_auc_ci_low": f">={EXIT_CRITERIA['ranking_pr_auc_ci_low_min']}",
            "top20_hit_rate": f">={EXIT_CRITERIA['top20_hit_rate_min']}",
            "decoys_above_positive_count": (
                f"<={EXIT_CRITERIA['decoys_above_positive_count_max']}"
            ),
            "positive_out_anchored_by_top_decoys": EXIT_CRITERIA[
                "positive_out_anchored_by_top_decoys_allowed"
            ],
            ACTUAL_CLOSURE_CRITERION_ID: (
                "computed_from_raw_hard_decoy_rows_with_quality_minimums"
            ),
        },
    }


def build_gpcr_hard_decoy_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    target_sources = [_target_source(dict(row)) for row in TARGET_SOURCES]
    positive_source_snapshot = _load_json(repo_root, DEFAULT_POSITIVE_SOURCE_SNAPSHOT)
    positive_source_summary = _positive_source_snapshot_summary(
        positive_source_snapshot
    )
    decoy_source_snapshot = _load_json(repo_root, DEFAULT_DECOY_SOURCE_SNAPSHOT)
    decoy_source_summary = _decoy_source_snapshot_summary(decoy_source_snapshot)
    required_targets = list(REQUIRED_TARGETS)
    target_ids = [str(row["target_id"]) for row in target_sources]
    blockers = [
        "gpcr_hard_decoy_rows_not_acquired",
        "target_specific_hard_decoy_source_not_attached",
        "gpcr_scoring_protocol_receipts_not_attached",
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_gpcr_hard_decoy_source_acquisition_plan.py"),
                Path("scripts/build_gpcr_hard_decoy_positive_source_snapshot.py"),
                Path("scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py"),
                DEFAULT_POSITIVE_SOURCE_SNAPSHOT,
                DEFAULT_DECOY_SOURCE_SNAPSHOT,
                Path("scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py"),
                Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
            ],
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_source_acquisition_plan",
            repo_root=repo_root,
        ),
        "status": "operator_acquisition_required",
        "contract_pass": True,
        "actual_closure_ready": False,
        "required_targets": required_targets,
        "target_source_count": len(target_sources),
        "target_sources": target_sources,
        "target_source_ids": {
            str(row["target_id"]): {
                "chembl_target_id": str(row["chembl_target_id"]),
                "uniprot_accession": str(row["uniprot_accession"]),
            }
            for row in target_sources
        },
        "positive_source_snapshot": positive_source_summary,
        "decoy_source_snapshot": decoy_source_summary,
        "per_target_exit_gates": [
            _per_target_exit_gate(target_id) for target_id in required_targets
        ],
        "row_artifact_contract": {
            "default_output": str(DEFAULT_ROWS_OUT),
            "required_flat_row_fields": [
                "target_id",
                "molecule_id",
                "score",
                "is_positive",
                "is_decoy",
                "score_direction",
                "source_checksum",
                "provenance_ref",
            ],
            "score_direction_policy": (
                "Use one score_direction per target and preserve the direction used "
                "by the scoring protocol."
            ),
            "row_source_receipt_policy": (
                "Every molecule row must carry source_checksum and provenance_ref; "
                "the attached row file must also be passed to the importer with a "
                "source_id, source_url, source_license, and source_artifact_sha256."
            ),
        },
        "acceptable_source_roles": [
            {
                "role": "positive_ligand_candidates",
                "minimum_per_target": int(
                    RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"]
                ),
                "candidate_source": "ChEMBL target activity rows or stronger operator-attached source",
                "candidate_snapshot": positive_source_summary,
                "closure_boundary": (
                    "Positive candidate sources do not close hard-decoy evaluation "
                    "without target-specific decoys and a scoring run."
                ),
            },
            {
                "role": "hard_decoy_candidates",
                "minimum_per_target": int(
                    RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"]
                ),
                "candidate_source": (
                    "ChEMBL weak/low-affinity target-specific candidates for "
                    "source preflight, followed by an operator-attached curated "
                    "hard-decoy set with license, checksum, and provenance receipts"
                ),
                "candidate_snapshot": decoy_source_summary,
                "closure_boundary": (
                    "Weak/low-affinity ChEMBL candidates, generic negatives, "
                    "unlabeled molecules, or fixture/generated IDs do not satisfy "
                    "the hard-decoy source requirement without curated rows and a "
                    "documented scoring run."
                ),
            },
            {
                "role": "scoring_protocol",
                "minimum_per_target": int(
                    RAW_ROW_QUALITY_CRITERIA["min_total_row_count_per_target"]
                ),
                "candidate_source": (
                    "One reproducible scoring protocol applied to positives and "
                    "decoys for each required target"
                ),
                "closure_boundary": (
                    "Metrics are recomputed by the suite materializer from raw rows; "
                    "summary-only metrics are preflight evidence only."
                ),
            },
        ],
        "operator_acquisition_checklist": [
            "verify_human_target_mapping_against_chembl_target_endpoint",
            "build_gpcr_hard_decoy_positive_source_snapshot",
            "build_gpcr_hard_decoy_decoy_source_snapshot",
            "attach_positive_ligand_candidates_with_activity_receipts",
            "attach_target_specific_hard_decoy_candidates_with_license_receipts",
            "run_one_documented_scoring_protocol_for_all_rows_per_target",
            "write_gpcr_hard_decoy_rows_at_default_dropzone",
            "run_gpcr_raw_row_importer_with_source_receipt_fields",
            "run_gpcr_suite_materializer_and_refresh_science_actual_closure",
        ],
        "commands": {
            "write_plan": (
                "python3 scripts/build_gpcr_hard_decoy_source_acquisition_plan.py"
            ),
            "build_positive_source_snapshot": (
                "python3 scripts/build_gpcr_hard_decoy_positive_source_snapshot.py "
                f"--out {DEFAULT_POSITIVE_SOURCE_SNAPSHOT} "
                f"--out-md {DEFAULT_POSITIVE_SOURCE_SNAPSHOT_MD}"
            ),
            "build_decoy_source_snapshot": (
                "python3 scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py "
                f"--out {DEFAULT_DECOY_SOURCE_SNAPSHOT} "
                f"--out-md {DEFAULT_DECOY_SOURCE_SNAPSHOT_MD}"
            ),
            "import_rows": (
                "python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py "
                f"--rows {DEFAULT_ROWS_OUT} --out {DEFAULT_OPERATOR_TEMPLATE} "
                "--source-id <source-id> --source-url <source-url> "
                "--source-license <license>"
            ),
            "materialize_suite": (
                "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
                f"--intake {DEFAULT_OPERATOR_TEMPLATE} --out-report {DEFAULT_SUITE_REPORT} "
                "--fail-blocked"
            ),
            "science_actual_closure": (
                "python3 scripts/materialize_science_actual_closure_from_rows.py "
                "--fail-blocked"
            ),
        },
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "target_source_count": len(target_sources),
            "required_target_count": len(required_targets),
            "target_source_mapping_complete": target_ids == required_targets,
            "positive_source_ready": bool(
                positive_source_summary.get("positive_source_ready")
            ),
            "positive_source_snapshot_status": str(
                positive_source_summary.get("status") or ""
            ),
            "total_positive_candidate_count": int(
                positive_source_summary.get("total_positive_candidate_count") or 0
            ),
            "decoy_candidate_source_ready": bool(
                decoy_source_summary.get("decoy_candidate_source_ready")
            ),
            "decoy_source_snapshot_status": str(
                decoy_source_summary.get("status") or ""
            ),
            "total_decoy_candidate_count": int(
                decoy_source_summary.get("total_decoy_candidate_count") or 0
            ),
            "minimum_positive_rows_total": int(
                RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"]
            )
            * len(required_targets),
            "minimum_decoy_rows_total": int(
                RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"]
            )
            * len(required_targets),
            "actual_closure_ready": False,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This plan records verified public target identifiers and the row/source "
            "contract needed to acquire GPCR hard-decoy evidence. Candidate ChEMBL "
            "snapshots are source receipts only; they do not attach curated decoys, "
            "docking scores, or licenses, and they do not close Phase 3 until the raw "
            "rows pass the suite materializer."
        ),
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GPCR Hard-Decoy Source Acquisition Plan",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `actual_closure_ready`: `{payload['actual_closure_ready']}`",
        f"- `blocker_count`: `{payload['blocker_count']}`",
        f"- `positive_source_snapshot`: `{payload['positive_source_snapshot']['artifact']}`",
        f"- `positive_source_ready`: `{payload['positive_source_snapshot']['positive_source_ready']}`",
        f"- `decoy_source_snapshot`: `{payload['decoy_source_snapshot']['artifact']}`",
        f"- `decoy_candidate_source_ready`: `{payload['decoy_source_snapshot']['decoy_candidate_source_ready']}`",
        "",
        "| Target | UniProt | ChEMBL | Role |",
        "|---|---|---|---|",
    ]
    for row in payload["target_sources"]:
        lines.append(
            f"| `{row['target_id']}` | `{row['uniprot_accession']}` | "
            f"`{row['chembl_target_id']}` | `{row['source_role']}` |"
        )
    lines.extend(["", "## Commands", ""])
    for key, command in payload["commands"].items():
        lines.append(f"- `{key}`: `{command}`")
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_gpcr_hard_decoy_source_acquisition_plan(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_source_acquisition_plan(repo_root=repo_root)
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(_markdown(payload), encoding="utf-8")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_gpcr_hard_decoy_source_acquisition_plan(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "gpcr-hard-decoy-source-acquisition-plan: "
            f"{payload['status']} | targets={payload['target_source_count']} | "
            f"blockers={payload['blocker_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
