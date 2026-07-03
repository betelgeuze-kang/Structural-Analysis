#!/usr/bin/env python3
"""Build a ChEMBL decoy-candidate source snapshot for the GPCR hard-decoy suite."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

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
DEFAULT_OUT = PRODUCTIZATION / "gpcr_hard_decoy_decoy_source_snapshot.json"
DEFAULT_OUT_MD = DEFAULT_OUT.with_suffix(".md")
SCHEMA_VERSION = "gpcr-hard-decoy-decoy-source-snapshot.v1"
CHEMBL_API_ROOT = "https://www.ebi.ac.uk/chembl/api/data"
DEFAULT_ACTIVITY_LIMIT = 1000
DEFAULT_CANDIDATE_LIMIT = 20
DEFAULT_MIN_DECOY_STANDARD_VALUE_NM = 10000.0
ACCEPTED_WEAK_RELATIONS = frozenset({"=", ">", ">="})
TARGET_SOURCES = (
    {
        "target_id": "DRD2",
        "gene_symbol": "DRD2",
        "uniprot_accession": "P14416",
        "chembl_target_id": "CHEMBL217",
        "chembl_pref_name": "D(2) dopamine receptor",
    },
    {
        "target_id": "HTR2A",
        "gene_symbol": "HTR2A",
        "uniprot_accession": "P28223",
        "chembl_target_id": "CHEMBL224",
        "chembl_pref_name": "5-hydroxytryptamine receptor 2A",
    },
    {
        "target_id": "OPRM1",
        "gene_symbol": "OPRM1",
        "uniprot_accession": "P35372",
        "chembl_target_id": "CHEMBL233",
        "chembl_pref_name": "Mu-type opioid receptor",
    },
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256_payload(payload: Any) -> str:
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(rendered.encode('utf-8')).hexdigest()}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if parsed > 0 else None
    token = str(value).strip()
    if not token:
        return None
    try:
        parsed = float(token)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def _activity_query_url(chembl_target_id: str, *, limit: int) -> str:
    params = urlencode(
        {
            "target_chembl_id": chembl_target_id,
            "standard_type__in": "Ki,IC50,Kd,EC50",
            "standard_units": "nM",
            "order_by": "-standard_value",
            "limit": limit,
            "format": "json",
        }
    )
    return f"{CHEMBL_API_ROOT}/activity.json?{params}"


def _fetch_json(url: str, *, timeout_seconds: int) -> dict[str, Any]:
    with urlopen(url, timeout=timeout_seconds) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, dict) else {}


def _load_fixture(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _payload_for_target(
    *,
    target_id: str,
    chembl_target_id: str,
    fixture_payload: dict[str, Any] | None,
    limit: int,
    timeout_seconds: int,
) -> tuple[dict[str, Any], str]:
    query_url = _activity_query_url(chembl_target_id, limit=limit)
    if fixture_payload is not None:
        fixture_rows = fixture_payload.get(target_id) or fixture_payload.get(
            chembl_target_id
        )
        if isinstance(fixture_rows, dict):
            return fixture_rows, query_url
        if isinstance(fixture_rows, list):
            return {
                "activities": fixture_rows,
                "page_meta": {"total_count": len(fixture_rows)},
            }, query_url
        return {"activities": [], "page_meta": {"total_count": 0}}, query_url
    return _fetch_json(query_url, timeout_seconds=timeout_seconds), query_url


def _activity_sort_key(row: dict[str, Any]) -> tuple[float, str]:
    value = _number(row.get("standard_value"))
    return (-(value if value is not None else 0.0), str(row.get("molecule_chembl_id") or ""))


def _is_decoy_candidate(
    row: dict[str, Any],
    *,
    minimum_standard_value_nm: float,
) -> bool:
    relation = str(row.get("standard_relation") or "").strip()
    value = _number(row.get("standard_value"))
    return (
        bool(row.get("molecule_chembl_id"))
        and row.get("standard_units") == "nM"
        and relation in ACCEPTED_WEAK_RELATIONS
        and value is not None
        and value >= minimum_standard_value_nm
    )


def _candidate_rows(
    *,
    target_id: str,
    chembl_target_id: str,
    query_url: str,
    payload: dict[str, Any],
    candidate_limit: int,
    minimum_standard_value_nm: float,
) -> list[dict[str, Any]]:
    activities = [
        row
        for row in payload.get("activities", [])
        if isinstance(row, dict)
        and _is_decoy_candidate(
            row,
            minimum_standard_value_nm=minimum_standard_value_nm,
        )
    ]
    candidates: list[dict[str, Any]] = []
    seen_molecules: set[str] = set()
    for row in sorted(activities, key=_activity_sort_key):
        molecule_id = str(row["molecule_chembl_id"])
        if molecule_id in seen_molecules:
            continue
        seen_molecules.add(molecule_id)
        activity_id = str(row.get("activity_id") or "")
        provenance_ref = (
            f"{CHEMBL_API_ROOT}/activity/{activity_id}.json"
            if activity_id
            else query_url
        )
        source_row = {
            "target_id": target_id,
            "chembl_target_id": chembl_target_id,
            "molecule_id": molecule_id,
            "activity_id": activity_id,
            "standard_type": str(row.get("standard_type") or ""),
            "standard_relation": str(row.get("standard_relation") or ""),
            "standard_value_nm": _number(row.get("standard_value")),
            "minimum_decoy_standard_value_nm": minimum_standard_value_nm,
            "standard_units": str(row.get("standard_units") or ""),
            "document_chembl_id": str(row.get("document_chembl_id") or ""),
            "assay_chembl_id": str(row.get("assay_chembl_id") or ""),
            "source_query_url": query_url,
            "provenance_ref": provenance_ref,
            "selection_rule": (
                "target-specific ChEMBL activity row with nM value at or above "
                f"{minimum_standard_value_nm:g} and relation in =,>,>="
            ),
        }
        candidates.append(
            {
                **source_row,
                "source_checksum": _sha256_payload(source_row),
                "closure_role": "decoy_candidate_source_only",
            }
        )
        if len(candidates) >= candidate_limit:
            break
    return candidates


def _target_snapshot(
    *,
    target_source: dict[str, str],
    fixture_payload: dict[str, Any] | None,
    activity_limit: int,
    candidate_limit: int,
    minimum_standard_value_nm: float,
    timeout_seconds: int,
) -> dict[str, Any]:
    target_id = target_source["target_id"]
    chembl_target_id = target_source["chembl_target_id"]
    payload, query_url = _payload_for_target(
        target_id=target_id,
        chembl_target_id=chembl_target_id,
        fixture_payload=fixture_payload,
        limit=activity_limit,
        timeout_seconds=timeout_seconds,
    )
    candidates = _candidate_rows(
        target_id=target_id,
        chembl_target_id=chembl_target_id,
        query_url=query_url,
        payload=payload,
        candidate_limit=candidate_limit,
        minimum_standard_value_nm=minimum_standard_value_nm,
    )
    minimum_decoy = int(RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"])
    blockers = []
    if len(candidates) < minimum_decoy:
        blockers.append(f"{target_id}:chembl_decoy_candidate_count_below_minimum")
    return {
        **target_source,
        "status": "decoy_candidates_ready" if not blockers else "decoy_candidates_incomplete",
        "contract_pass": not blockers,
        "decoy_candidate_count": len(candidates),
        "minimum_decoy_rows_required": minimum_decoy,
        "minimum_decoy_standard_value_nm": minimum_standard_value_nm,
        "activity_total_count": int(payload.get("page_meta", {}).get("total_count") or 0),
        "activity_query_url": query_url,
        "activity_payload_sha256": _sha256_payload(payload),
        "candidate_limit": candidate_limit,
        "accepted_standard_relations": sorted(ACCEPTED_WEAK_RELATIONS),
        "decoy_candidates": candidates,
        "blockers": blockers,
        "claim_boundary": (
            "These ChEMBL rows identify target-linked weak/low-affinity ligand "
            "candidates only; they are not a curated hard-decoy benchmark set and "
            "do not include a scoring run."
        ),
    }


def build_gpcr_hard_decoy_decoy_source_snapshot(
    *,
    repo_root: Path = ROOT,
    fixture_path: Path | None = None,
    activity_limit: int = DEFAULT_ACTIVITY_LIMIT,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    minimum_standard_value_nm: float = DEFAULT_MIN_DECOY_STANDARD_VALUE_NM,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    fixture_payload = (
        _load_fixture(fixture_path if fixture_path.is_absolute() else repo_root / fixture_path)
        if fixture_path is not None
        else None
    )
    target_snapshots = [
        _target_snapshot(
            target_source=dict(target_source),
            fixture_payload=fixture_payload,
            activity_limit=activity_limit,
            candidate_limit=candidate_limit,
            minimum_standard_value_nm=minimum_standard_value_nm,
            timeout_seconds=timeout_seconds,
        )
        for target_source in TARGET_SOURCES
    ]
    blockers = [
        blocker
        for target in target_snapshots
        for blocker in target["blockers"]
    ]
    target_candidate_counts = {
        str(target["target_id"]): int(target["decoy_candidate_count"])
        for target in target_snapshots
    }
    minimum_decoy = int(RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"])
    total_candidate_count = sum(target_candidate_counts.values())
    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=[
                Path("scripts/build_gpcr_hard_decoy_decoy_source_snapshot.py"),
                *([fixture_path] if fixture_path is not None else []),
            ],
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_decoy_source_snapshot_from_chembl",
            repo_root=repo_root,
        ),
        "status": "decoy_candidate_sources_ready" if not blockers else "decoy_candidate_sources_incomplete",
        "contract_pass": not blockers,
        "decoy_candidate_source_ready": not blockers,
        "actual_closure_ready": False,
        "required_targets": list(REQUIRED_TARGETS),
        "target_snapshot_count": len(target_snapshots),
        "target_snapshots": target_snapshots,
        "target_candidate_counts": target_candidate_counts,
        "minimum_decoy_rows_per_target": minimum_decoy,
        "minimum_decoy_standard_value_nm": minimum_standard_value_nm,
        "total_decoy_candidate_count": total_candidate_count,
        "source_role": "target_specific_low_affinity_decoy_candidate_source_only",
        "closure_blockers": [
            "target_specific_hard_decoy_source_not_attached",
            "gpcr_scoring_protocol_receipts_not_attached",
            "gpcr_hard_decoy_rows_not_materialized",
        ],
        "blockers": blockers,
        "blocker_count": len(blockers),
        "summary": {
            "decoy_candidate_source_ready": not blockers,
            "actual_closure_ready": False,
            "required_target_count": len(REQUIRED_TARGETS),
            "target_snapshot_count": len(target_snapshots),
            "minimum_decoy_rows_per_target": minimum_decoy,
            "minimum_decoy_standard_value_nm": minimum_standard_value_nm,
            "total_decoy_candidate_count": total_candidate_count,
            "target_candidate_counts": target_candidate_counts,
            "blocker_count": len(blockers),
            "closure_blocker_count": 3,
        },
        "claim_boundary": (
            "This snapshot is a target-specific weak/low-affinity candidate source "
            "receipt over official ChEMBL activity rows for DRD2, HTR2A, and OPRM1. "
            "It does not provide a curated hard-decoy benchmark, docking scores, or "
            "Phase 3 closure rows."
        ),
    }


def render_gpcr_hard_decoy_decoy_source_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# GPCR Hard-Decoy Decoy Source Snapshot",
        "",
        f"- `status`: `{payload['status']}`",
        f"- `contract_pass`: `{payload['contract_pass']}`",
        f"- `decoy_candidate_source_ready`: `{payload['decoy_candidate_source_ready']}`",
        f"- `actual_closure_ready`: `{payload['actual_closure_ready']}`",
        f"- `total_decoy_candidate_count`: `{payload['total_decoy_candidate_count']}`",
        "",
        "| Target | ChEMBL | Candidates | Activity Rows |",
        "|---|---|---:|---:|",
    ]
    for row in payload["target_snapshots"]:
        lines.append(
            f"| `{row['target_id']}` | `{row['chembl_target_id']}` | "
            f"{row['decoy_candidate_count']} | {row['activity_total_count']} |"
        )
    lines.extend(["", str(payload["claim_boundary"]), ""])
    return "\n".join(lines)


def write_gpcr_hard_decoy_decoy_source_snapshot(
    *,
    repo_root: Path = ROOT,
    out: Path = DEFAULT_OUT,
    out_md: Path = DEFAULT_OUT_MD,
    fixture_path: Path | None = None,
    activity_limit: int = DEFAULT_ACTIVITY_LIMIT,
    candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
    minimum_standard_value_nm: float = DEFAULT_MIN_DECOY_STANDARD_VALUE_NM,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    payload = build_gpcr_hard_decoy_decoy_source_snapshot(
        repo_root=repo_root,
        fixture_path=fixture_path,
        activity_limit=activity_limit,
        candidate_limit=candidate_limit,
        minimum_standard_value_nm=minimum_standard_value_nm,
        timeout_seconds=timeout_seconds,
    )
    resolved_out = out if out.is_absolute() else repo_root / out
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(_json_text(payload), encoding="utf-8")
    resolved_md = out_md if out_md.is_absolute() else repo_root / out_md
    resolved_md.parent.mkdir(parents=True, exist_ok=True)
    resolved_md.write_text(
        render_gpcr_hard_decoy_decoy_source_markdown(payload),
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--activity-limit", type=int, default=DEFAULT_ACTIVITY_LIMIT)
    parser.add_argument("--candidate-limit", type=int, default=DEFAULT_CANDIDATE_LIMIT)
    parser.add_argument(
        "--minimum-standard-value-nm",
        type=float,
        default=DEFAULT_MIN_DECOY_STANDARD_VALUE_NM,
    )
    parser.add_argument("--timeout-seconds", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_gpcr_hard_decoy_decoy_source_snapshot(
        repo_root=args.repo_root,
        out=args.out,
        out_md=args.out_md,
        fixture_path=args.fixture,
        activity_limit=args.activity_limit,
        candidate_limit=args.candidate_limit,
        minimum_standard_value_nm=args.minimum_standard_value_nm,
        timeout_seconds=args.timeout_seconds,
    )
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "gpcr-hard-decoy-decoy-source-snapshot: "
            f"{payload['status']} | candidates={payload['total_decoy_candidate_count']} | "
            f"blockers={payload['blocker_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
