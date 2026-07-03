#!/usr/bin/env python3
"""Build GPCR raw ranking rows from ChEMBL activity source snapshots."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from materialize_gpcr_hard_decoy_suite_report import (  # noqa: E402
    RAW_ROW_QUALITY_CRITERIA,
    REQUIRED_TARGETS,
)
from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_POSITIVE_SNAPSHOT = (
    PRODUCTIZATION / "gpcr_hard_decoy_positive_source_snapshot.json"
)
DEFAULT_DECOY_SNAPSHOT = PRODUCTIZATION / "gpcr_hard_decoy_decoy_source_snapshot.json"
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_chembl_activity_rows.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
DEFAULT_ROWS_OUT = PRODUCTIZATION / "gpcr_hard_decoy_rows.json"
DEFAULT_OPERATOR_TEMPLATE = PRODUCTIZATION / "gpcr_hard_decoy_operator_template.json"
DEFAULT_SUITE_REPORT = PRODUCTIZATION / "gpcr_hard_decoy_suite_report.json"

SCHEMA_VERSION = "gpcr-hard-decoy-chembl-activity-rows.v1"
CHEMBL_ACTIVITY_API_URL = "https://www.ebi.ac.uk/chembl/api/data/activity"
SOURCE_ID = "chembl_gpcr_activity_positive_low_affinity_rows"
SOURCE_LICENSE = "ChEMBL public API activity rows; use subject to EBI and ChEMBL terms"
SOURCE_VERSION = "live_chembl_api_snapshot"


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    else:
        try:
            parsed = float(str(value).strip())
        except ValueError:
            return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _activity_score(standard_value_nm: Any) -> float | None:
    value_nm = _number(standard_value_nm)
    if value_nm is None:
        return None
    molar = value_nm * 1.0e-9
    if molar <= 0:
        return None
    return -math.log10(molar)


def _candidate_rows(snapshot: dict[str, Any], *, target_id: str, key: str) -> list[dict[str, Any]]:
    for target in snapshot.get("target_snapshots", []):
        if isinstance(target, dict) and str(target.get("target_id") or "") == target_id:
            return [row for row in target.get(key, []) if isinstance(row, dict)]
    return []


def _ranking_row(
    *,
    target_id: str,
    candidate: dict[str, Any],
    is_positive: bool,
) -> dict[str, Any] | None:
    molecule_id = str(candidate.get("molecule_id") or "").strip()
    score = _activity_score(candidate.get("standard_value_nm"))
    source_checksum = str(candidate.get("source_checksum") or "").strip()
    provenance_ref = str(candidate.get("provenance_ref") or "").strip()
    if not molecule_id or score is None or not source_checksum or not provenance_ref:
        return None
    return {
        "target_id": target_id,
        "molecule_id": molecule_id,
        "score": score,
        "score_direction": "higher_is_better",
        "is_positive": is_positive,
        "is_decoy": not is_positive,
        "source_checksum": source_checksum,
        "provenance_ref": provenance_ref,
        "activity_id": str(candidate.get("activity_id") or ""),
        "chembl_target_id": str(candidate.get("chembl_target_id") or ""),
        "standard_type": str(candidate.get("standard_type") or ""),
        "standard_relation": str(candidate.get("standard_relation") or ""),
        "standard_value_nm": _number(candidate.get("standard_value_nm")),
        "standard_units": str(candidate.get("standard_units") or ""),
        "source_role": (
            "chembl_positive_activity_row"
            if is_positive
            else "chembl_low_affinity_decoy_activity_row"
        ),
        "scoring_protocol": "pchembl_like_activity_score_from_standard_value_nm",
    }


def build_gpcr_hard_decoy_chembl_activity_rows(
    *,
    repo_root: Path = ROOT,
    positive_snapshot_path: Path = DEFAULT_POSITIVE_SNAPSHOT,
    decoy_snapshot_path: Path = DEFAULT_DECOY_SNAPSHOT,
) -> dict[str, Any]:
    positive_snapshot = _load_json(repo_root, positive_snapshot_path)
    decoy_snapshot = _load_json(repo_root, decoy_snapshot_path)
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    target_counts: dict[str, dict[str, int]] = {}
    for target_id in REQUIRED_TARGETS:
        seen_molecules: set[str] = set()
        target_rows: list[dict[str, Any]] = []
        for candidate in _candidate_rows(
            positive_snapshot,
            target_id=target_id,
            key="positive_candidates",
        ):
            row = _ranking_row(
                target_id=target_id,
                candidate=candidate,
                is_positive=True,
            )
            if row is None:
                blockers.append(f"{target_id}:positive_candidate_row_invalid")
                continue
            molecule_id = str(row["molecule_id"])
            if molecule_id in seen_molecules:
                blockers.append(f"{target_id}:{molecule_id}:molecule_id_duplicate")
                continue
            seen_molecules.add(molecule_id)
            target_rows.append(row)
        for candidate in _candidate_rows(
            decoy_snapshot,
            target_id=target_id,
            key="decoy_candidates",
        ):
            row = _ranking_row(
                target_id=target_id,
                candidate=candidate,
                is_positive=False,
            )
            if row is None:
                blockers.append(f"{target_id}:decoy_candidate_row_invalid")
                continue
            molecule_id = str(row["molecule_id"])
            if molecule_id in seen_molecules:
                blockers.append(f"{target_id}:{molecule_id}:molecule_id_duplicate")
                continue
            seen_molecules.add(molecule_id)
            target_rows.append(row)
        positive_count = sum(1 for row in target_rows if row["is_positive"])
        decoy_count = sum(1 for row in target_rows if row["is_decoy"])
        total_count = len(target_rows)
        if positive_count < RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"]:
            blockers.append(f"{target_id}:positive_count_below_minimum")
        if decoy_count < RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"]:
            blockers.append(f"{target_id}:decoy_count_below_minimum")
        if total_count < RAW_ROW_QUALITY_CRITERIA["min_total_row_count_per_target"]:
            blockers.append(f"{target_id}:total_count_below_minimum")
        target_counts[target_id] = {
            "positive_count": positive_count,
            "decoy_count": decoy_count,
            "total_count": total_count,
        }
        rows.extend(target_rows)
    blockers = sorted(dict.fromkeys(blockers))
    raw_rows_ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_gpcr_hard_decoy_chembl_activity_rows.py"),
                positive_snapshot_path,
                decoy_snapshot_path,
            ],
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_chembl_activity_rows_from_source_snapshots",
            repo_root=repo_root,
        ),
        "status": "raw_activity_rows_ready" if raw_rows_ready else "raw_activity_rows_blocked",
        "contract_pass": raw_rows_ready,
        "raw_rows_ready": raw_rows_ready,
        "actual_closure_ready": False,
        "row_count": len(rows),
        "target_counts": target_counts,
        "required_targets": list(REQUIRED_TARGETS),
        "score_direction": "higher_is_better",
        "scoring_protocol": {
            "protocol_id": "pchembl_like_activity_score_from_standard_value_nm",
            "score_formula": "-log10(standard_value_nm * 1e-9)",
            "score_direction": "higher_is_better",
            "positive_selection": "ChEMBL strong activity rows from positive source snapshot",
            "decoy_selection": "ChEMBL target-specific weak/low-affinity rows from decoy source snapshot",
            "claim_boundary": (
                "This is an activity-derived ranking protocol over ChEMBL source rows. "
                "It is not a docking run and should be promoted only if the product "
                "accepts ChEMBL low-affinity rows as the hard-decoy source."
            ),
        },
        "suggested_operator_input_source": {
            "source_id": SOURCE_ID,
            "source_url": CHEMBL_ACTIVITY_API_URL,
            "source_license": SOURCE_LICENSE,
            "source_version": SOURCE_VERSION,
            "source_artifact": str(DEFAULT_ROWS_OUT),
        },
        "materialization_commands": {
            "copy_to_default_rows": (
                f"cp {DEFAULT_OUT} {DEFAULT_ROWS_OUT}"
            ),
            "import_operator_template": (
                "python3 scripts/materialize_gpcr_hard_decoy_operator_template_from_rows.py "
                f"--rows {DEFAULT_ROWS_OUT} --out {DEFAULT_OPERATOR_TEMPLATE} "
                f"--source-id {SOURCE_ID} --source-url {CHEMBL_ACTIVITY_API_URL} "
                f"--source-license '{SOURCE_LICENSE}' --source-version {SOURCE_VERSION}"
            ),
            "materialize_suite": (
                "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
                f"--intake {DEFAULT_OPERATOR_TEMPLATE} --out-report {DEFAULT_SUITE_REPORT} "
                "--fail-blocked"
            ),
        },
        "rows": rows,
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "raw_rows_ready": raw_rows_ready,
            "actual_closure_ready": False,
            "row_count": len(rows),
            "target_counts": target_counts,
            "blocker_count": len(blockers),
        },
        "claim_boundary": (
            "This artifact materializes source-attached GPCR ranking rows from official "
            "ChEMBL activity snapshots. It enables importer and suite verification, but "
            "does not by itself change the default GPCR suite report or promote broad "
            "GPCR hard-decoy closure."
        ),
    }


def render_gpcr_hard_decoy_chembl_activity_rows_markdown(
    payload: dict[str, Any],
) -> str:
    lines = [
        "# GPCR Hard-Decoy ChEMBL Activity Rows",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `raw_rows_ready`: `{payload['raw_rows_ready']}`",
        f"- `actual_closure_ready`: `{payload['actual_closure_ready']}`",
        f"- `row_count`: `{payload['row_count']}`",
        "",
        "| Target | Positives | Decoys | Total |",
        "|---|---:|---:|---:|",
    ]
    for target_id, counts in payload["target_counts"].items():
        lines.append(
            f"| `{target_id}` | {counts['positive_count']} | "
            f"{counts['decoy_count']} | {counts['total_count']} |"
        )
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_gpcr_hard_decoy_chembl_activity_rows(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    positive_snapshot_path: Path = DEFAULT_POSITIVE_SNAPSHOT,
    decoy_snapshot_path: Path = DEFAULT_DECOY_SNAPSHOT,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_chembl_activity_rows(
        repo_root=repo_root,
        positive_snapshot_path=positive_snapshot_path,
        decoy_snapshot_path=decoy_snapshot_path,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_gpcr_hard_decoy_chembl_activity_rows_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--positive-snapshot", type=Path, default=DEFAULT_POSITIVE_SNAPSHOT)
    parser.add_argument("--decoy-snapshot", type=Path, default=DEFAULT_DECOY_SNAPSHOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_gpcr_hard_decoy_chembl_activity_rows(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        positive_snapshot_path=args.positive_snapshot,
        decoy_snapshot_path=args.decoy_snapshot,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "gpcr-hard-decoy-chembl-activity-rows: "
            f"{payload['status']} | rows={payload['row_count']} | "
            f"blockers={payload['blocker_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
