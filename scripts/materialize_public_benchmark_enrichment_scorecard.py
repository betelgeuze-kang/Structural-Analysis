#!/usr/bin/env python3
"""Materialize a DUD-E/LIT-PCBA enrichment scorecard from operator intake."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_SCORECARD_OUT = PRODUCTIZATION / "public_benchmark_enrichment_scorecard.json"

SCHEMA_VERSION = "public-benchmark-enrichment-materialization.v1"
SCORECARD_SCHEMA_VERSION = "public-benchmark-enrichment-scorecard.v1"
SUPPORTED_FAMILIES = ("DUD-E", "LIT-PCBA")
REQUIRED_TARGET_FIELDS = (
    "benchmark_family",
    "target_id",
    "score_direction",
    "scored_molecules",
    "source_license_or_accession",
    "source_checksum",
    "provenance_ref",
)
REQUIRED_MOLECULE_FIELDS = ("molecule_id", "is_active", "score")
SOURCE_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PLACEHOLDER_SOURCE_TEXT_MARKERS = (
    "<operator",
    "dry-run",
    "dummy",
    "example.invalid",
    "example://",
    "fake",
    "fixture",
    "mock",
    "operator_supplied",
    "placeholder",
    "synthetic",
    "test-accession",
    "todo",
    "unit-test",
)
PLACEHOLDER_PROVENANCE_PREFIXES = (
    "operator://",
    "local-evidence://",
    "local://",
    "fixture://",
    "mock://",
    "synthetic://",
    "placeholder://",
    "test://",
    "unit-test://",
    "file://",
)
ROW_INTEGRITY_POLICY = {
    "required_unique_row_keys": {
        "targets": ["target_id"],
        "target_scored_molecules": ["molecule_id"],
    },
    "purpose": (
        "Duplicate enrichment targets or scored molecules cannot be used to inflate "
        "Public Benchmark enrichment coverage or active/decoy counts."
    ),
}
SCORE_DIRECTION_POLICY = {
    "required": True,
    "accepted_values": ["higher_is_better", "lower_is_better"],
    "accepted_aliases": {
        "higher_is_better": ["higher", "higher_is_better", "descending"],
        "lower_is_better": ["lower", "lower_is_better", "ascending"],
    },
    "blank_values": "rejected; no implicit default is applied",
}
BOOLEAN_LABEL_POLICY = {
    "is_active": "must be a JSON boolean true/false; strings and numbers are rejected",
}
NUMERIC_VALUE_POLICY = {
    "score": "must parse to a finite float; NaN and Infinity are rejected",
}
ACTIVE_DECOY_POLICY = {
    "per_target_requirement": (
        "each target must contain at least one active molecule and one decoy molecule"
    ),
}


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    return None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _is_sha256_ref(value: str) -> bool:
    return bool(SOURCE_CHECKSUM_PATTERN.fullmatch(value))


def _contains_placeholder_marker(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(marker in lowered for marker in PLACEHOLDER_SOURCE_TEXT_MARKERS)


def _has_placeholder_provenance_prefix(value: Any) -> bool:
    lowered = _string(value).lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not _is_sha256_ref(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _family(value: Any) -> str:
    token = _string(value).upper().replace("_", "-")
    if token in {"DUDE", "DUD-E"}:
        return "DUD-E"
    if token in {"LITPCBA", "LIT-PCBA"}:
        return "LIT-PCBA"
    return token


def _direction(value: Any) -> str:
    token = _string(value).lower()
    if token in {"higher", "higher_is_better", "descending"}:
        return "higher_is_better"
    if token in {"lower", "lower_is_better", "ascending"}:
        return "lower_is_better"
    return token


def _top_count(total: int, fraction: float) -> int:
    return max(1, min(total, int(math.ceil(total * fraction))))


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _counts_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = _string(row.get(key))
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _roc_auc(
    *,
    active_scores: list[float],
    decoy_scores: list[float],
    higher_is_better: bool,
) -> float | None:
    if not active_scores or not decoy_scores:
        return None
    wins = 0.0
    comparisons = 0
    for active in active_scores:
        for decoy in decoy_scores:
            comparisons += 1
            if active == decoy:
                wins += 0.5
            elif (active > decoy) if higher_is_better else (active < decoy):
                wins += 1.0
    return wins / comparisons if comparisons else None


def _enrichment_factor(
    *,
    ranked: list[dict[str, Any]],
    active_count: int,
    top_count: int,
) -> float | None:
    total = len(ranked)
    if total == 0 or active_count == 0 or top_count == 0:
        return None
    top_actives = sum(1 for row in ranked[:top_count] if row["is_active"])
    expected_active_fraction = active_count / total
    return (top_actives / top_count) / expected_active_fraction


def _target_key(row: dict[str, Any], index: int) -> str:
    return _string(row.get("target_id")) or f"target_{index + 1}"


def _normalize_molecule(
    row: dict[str, Any],
    *,
    target_key: str,
    index: int,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    for field in REQUIRED_MOLECULE_FIELDS:
        if field not in row:
            blockers.append(f"{target_key}:molecule_{index}:{field}_missing")

    molecule_id = _string(row.get("molecule_id"))
    is_active = _boolean(row.get("is_active"))
    score = _number(row.get("score"))
    if "molecule_id" in row and not molecule_id:
        blockers.append(f"{target_key}:molecule_{index}:molecule_id_blank")
    if "is_active" in row and is_active is None:
        blockers.append(f"{target_key}:molecule_{index}:is_active_invalid")
    if "score" in row and score is None:
        blockers.append(f"{target_key}:molecule_{index}:score_invalid")

    return (
        {
            "molecule_id": molecule_id,
            "is_active": is_active,
            "score": score,
        },
        blockers,
    )


def _score_target(row: dict[str, Any], *, index: int) -> dict[str, Any]:
    target_key = _target_key(row, index)
    blockers: list[str] = []
    root_cause_tags: list[str] = []

    for field in REQUIRED_TARGET_FIELDS:
        if field not in row:
            blockers.append(f"{target_key}:{field}_missing")
            root_cause_tags.append("operator_values_required")

    family = _family(row.get("benchmark_family"))
    target_id = _string(row.get("target_id"))
    score_direction = _direction(row.get("score_direction"))
    source_license = _string(row.get("source_license_or_accession"))
    source_checksum = _string(row.get("source_checksum"))
    provenance_ref = _string(row.get("provenance_ref"))

    if "benchmark_family" in row and family not in SUPPORTED_FAMILIES:
        blockers.append(f"{target_key}:benchmark_family_unsupported")
        root_cause_tags.append("unsupported_benchmark_family")
    if "target_id" in row and not target_id:
        blockers.append(f"{target_key}:target_id_blank")
        root_cause_tags.append("operator_values_required")
    if "score_direction" in row and score_direction not in {
        "higher_is_better",
        "lower_is_better",
    }:
        blockers.append(f"{target_key}:score_direction_invalid")
        root_cause_tags.append("operator_values_required")
    if "source_license_or_accession" in row and not source_license:
        blockers.append(f"{target_key}:source_license_or_accession_blank")
        root_cause_tags.append("operator_values_required")
    elif (
        "source_license_or_accession" in row
        and source_license
        and _contains_placeholder_marker(source_license)
    ):
        blockers.append(f"{target_key}:source_license_or_accession_placeholder")
        root_cause_tags.append("operator_receipts_required")
    if "source_checksum" in row:
        if not source_checksum:
            blockers.append(f"{target_key}:source_checksum_blank")
            root_cause_tags.append("operator_values_required")
        elif not _is_sha256_ref(source_checksum):
            blockers.append(f"{target_key}:source_checksum_invalid")
            root_cause_tags.append("operator_receipts_required")
        elif _is_repeated_placeholder_checksum(source_checksum):
            blockers.append(f"{target_key}:source_checksum_placeholder_digest")
            root_cause_tags.append("operator_receipts_required")
    if "provenance_ref" in row and not provenance_ref:
        blockers.append(f"{target_key}:provenance_ref_blank")
        root_cause_tags.append("operator_values_required")
    elif (
        "provenance_ref" in row
        and provenance_ref
        and (
            _has_placeholder_provenance_prefix(provenance_ref)
            or _contains_placeholder_marker(provenance_ref)
        )
    ):
        blockers.append(f"{target_key}:provenance_ref_placeholder")
        root_cause_tags.append("operator_receipts_required")

    raw_molecules = _as_list(row.get("scored_molecules"))
    if not raw_molecules:
        blockers.append(f"{target_key}:scored_molecules_missing")
        root_cause_tags.append("operator_values_required")

    molecules: list[dict[str, Any]] = []
    seen_molecule_ids: set[str] = set()
    for molecule_index, raw_molecule in enumerate(raw_molecules):
        if not isinstance(raw_molecule, dict):
            blockers.append(f"{target_key}:molecule_{molecule_index}:invalid_object")
            root_cause_tags.append("operator_values_required")
            continue
        molecule, molecule_blockers = _normalize_molecule(
            raw_molecule,
            target_key=target_key,
            index=molecule_index,
        )
        molecules.append(molecule)
        blockers.extend(molecule_blockers)
        if molecule_blockers:
            root_cause_tags.append("operator_values_required")
        molecule_id = _string(molecule.get("molecule_id"))
        if molecule_id:
            if molecule_id in seen_molecule_ids:
                blockers.append(
                    f"{target_key}:molecule_{molecule_index}:"
                    f"molecule_id_duplicate:{molecule_id}"
                )
                root_cause_tags.append("row_integrity_required")
            else:
                seen_molecule_ids.add(molecule_id)

    valid_molecules = [
        molecule
        for molecule in molecules
        if molecule["is_active"] is not None and molecule["score"] is not None
    ]
    active_count = sum(1 for molecule in valid_molecules if molecule["is_active"])
    decoy_count = sum(1 for molecule in valid_molecules if not molecule["is_active"])
    if valid_molecules and active_count == 0:
        blockers.append(f"{target_key}:active_molecules_missing")
        root_cause_tags.append("active_decoy_labels_required")
    if valid_molecules and decoy_count == 0:
        blockers.append(f"{target_key}:decoy_molecules_missing")
        root_cause_tags.append("active_decoy_labels_required")

    higher_is_better = score_direction != "lower_is_better"
    ranked = sorted(
        valid_molecules,
        key=lambda molecule: float(molecule["score"]),
        reverse=higher_is_better,
    )
    top_1pct_count = _top_count(len(ranked), 0.01) if ranked else 0
    top_5pct_count = _top_count(len(ranked), 0.05) if ranked else 0
    active_scores = [float(molecule["score"]) for molecule in valid_molecules if molecule["is_active"]]
    decoy_scores = [float(molecule["score"]) for molecule in valid_molecules if not molecule["is_active"]]
    enrichment_factor_1pct = _enrichment_factor(
        ranked=ranked,
        active_count=active_count,
        top_count=top_1pct_count,
    )
    enrichment_factor_5pct = _enrichment_factor(
        ranked=ranked,
        active_count=active_count,
        top_count=top_5pct_count,
    )
    roc_auc = _roc_auc(
        active_scores=active_scores,
        decoy_scores=decoy_scores,
        higher_is_better=higher_is_better,
    )

    return {
        "benchmark_family": family,
        "target_id": target_id,
        "score_direction": score_direction,
        "molecule_count": len(valid_molecules),
        "active_count": active_count,
        "decoy_count": decoy_count,
        "top_1pct_count": top_1pct_count,
        "top_5pct_count": top_5pct_count,
        "enrichment_factor_1pct": enrichment_factor_1pct,
        "enrichment_factor_5pct": enrichment_factor_5pct,
        "roc_auc": roc_auc,
        "source_license_or_accession": source_license,
        "source_checksum": source_checksum,
        "provenance_ref": provenance_ref,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
    }


def _summary(rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    families = sorted({row["benchmark_family"] for row in rows if row["benchmark_family"]})
    family_target_counts = _counts_by_key(rows, "benchmark_family")
    missing_supported_families = [
        family for family in SUPPORTED_FAMILIES if family not in family_target_counts
    ]
    return {
        "benchmark_family_count": len(families),
        "benchmark_families": families,
        "benchmark_family_target_counts": family_target_counts,
        "covered_supported_family_count": len(
            [family for family in SUPPORTED_FAMILIES if family in family_target_counts]
        ),
        "missing_supported_families": missing_supported_families,
        "target_count": len(rows),
        "ready_target_count": sum(1 for row in rows if row["contract_pass"]),
        "molecule_count": sum(int(row.get("molecule_count") or 0) for row in rows),
        "active_count": sum(int(row.get("active_count") or 0) for row in rows),
        "decoy_count": sum(int(row.get("decoy_count") or 0) for row in rows),
        "enrichment_factor_1pct_median": _median(
            [float(row["enrichment_factor_1pct"]) for row in rows if row["enrichment_factor_1pct"] is not None]
        ),
        "enrichment_factor_5pct_median": _median(
            [float(row["enrichment_factor_5pct"]) for row in rows if row["enrichment_factor_5pct"] is not None]
        ),
        "roc_auc_median": _median(
            [float(row["roc_auc"]) for row in rows if row["roc_auc"] is not None]
        ),
        "blocker_count": len(blockers),
    }


def materialize_enrichment_scorecard(
    intake_payload: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
) -> dict[str, Any]:
    raw_targets = [row for row in _as_list(intake_payload.get("targets")) if isinstance(row, dict)]
    rows: list[dict[str, Any]] = []
    seen_target_ids: set[str] = set()
    for index, row in enumerate(raw_targets):
        scored = _score_target(row, index=index)
        target_id = _string(scored.get("target_id"))
        if target_id:
            if target_id in seen_target_ids:
                scored["blockers"].append(f"{target_id}:target_id_duplicate")
                scored["root_cause_tags"] = list(
                    dict.fromkeys(
                        [*scored["root_cause_tags"], "row_integrity_required"]
                    )
                )
                scored["status"] = "blocked"
                scored["contract_pass"] = False
            else:
                seen_target_ids.add(target_id)
        rows.append(scored)
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    root_cause_tags = list(dict.fromkeys(tag for row in rows for tag in row["root_cause_tags"]))
    if not rows:
        blockers = [
            "dud_e_lit_pcba_enrichment_targets_missing",
            "dud_e_lit_pcba_scored_molecules_missing",
            "dud_e_lit_pcba_active_decoy_labels_missing",
        ]
        root_cause_tags = ["operator_enrichment_rows_required"]

    summary = _summary(rows, blockers)
    enrichment_ready = bool(rows and not blockers)
    first_blocked_target = next(
        (row["target_id"] or f"target_{index + 1}" for index, row in enumerate(rows) if row["blockers"]),
        "dud_e_lit_pcba_operator_intake" if blockers else "",
    )
    input_paths = [Path("scripts/materialize_public_benchmark_enrichment_scorecard.py")]
    if intake_path is not None:
        input_paths.append(intake_path)

    return {
        "schema_version": SCORECARD_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="public_benchmark_enrichment_scorecard_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if enrichment_ready else "operator_evidence_required",
        "contract_pass": enrichment_ready,
        "public_benchmark_enrichment_ready": enrichment_ready,
        "real_enrichment_target_count": len(rows),
        "benchmark_family_target_counts": summary["benchmark_family_target_counts"],
        "target_rows": rows,
        "summary": summary,
        "required_target_fields": list(REQUIRED_TARGET_FIELDS),
        "required_molecule_fields": list(REQUIRED_MOLECULE_FIELDS),
        "row_integrity_policy": ROW_INTEGRITY_POLICY,
        "score_direction_policy": SCORE_DIRECTION_POLICY,
        "boolean_label_policy": BOOLEAN_LABEL_POLICY,
        "numeric_value_policy": NUMERIC_VALUE_POLICY,
        "active_decoy_policy": ACTIVE_DECOY_POLICY,
        "supported_benchmark_families": list(SUPPORTED_FAMILIES),
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": root_cause_tags,
        "blockers": blockers,
        "materialization_report": {
            "schema_version": SCHEMA_VERSION,
            "operator_target_count": len(raw_targets),
            "materialized_target_count": len(rows),
            "ready_target_count": summary["ready_target_count"],
            "benchmark_family_target_counts": summary["benchmark_family_target_counts"],
            "blocker_count": len(blockers),
            "public_benchmark_enrichment_ready": enrichment_ready,
        },
        "summary_line": (
            "Public benchmark enrichment scorecard: PASS | "
            f"targets={len(rows)} | families={','.join(summary['benchmark_families'])}"
            if enrichment_ready
            else (
                "Public benchmark enrichment scorecard: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"blockers={len(blockers)}"
            )
        ),
        "claim_boundary": (
            "This scorecard computes DUD-E/LIT-PCBA enrichment metrics from "
            "operator-attached scored molecule rows. It does not download benchmark data, "
            "validate ligand chemistry, compare docking engines, or close Tier beta by itself."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out-scorecard", type=Path, default=DEFAULT_SCORECARD_OUT)
    parser.add_argument("--out-report", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intake_payload = json.loads(args.intake.read_text(encoding="utf-8"))
    scorecard = materialize_enrichment_scorecard(
        intake_payload,
        repo_root=args.repo_root,
        intake_path=args.intake,
    )
    args.out_scorecard.parent.mkdir(parents=True, exist_ok=True)
    args.out_scorecard.write_text(_json_text(scorecard), encoding="utf-8")
    if args.out_report is not None:
        args.out_report.parent.mkdir(parents=True, exist_ok=True)
        args.out_report.write_text(
            _json_text(scorecard["materialization_report"]),
            encoding="utf-8",
        )
    print(
        "public-benchmark-enrichment-materialization: "
        f"{scorecard['status']} | targets={scorecard['real_enrichment_target_count']} | "
        f"blockers={len(scorecard['blockers'])}"
    )
    return 1 if args.fail_blocked and not scorecard["public_benchmark_enrichment_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
