#!/usr/bin/env python3
"""Materialize a PocketMD Lite top-k survival report from operator intake rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
SURFACE_DIR = Path("implementation/phase1/release_evidence/surface")

DEFAULT_CONTRACT = PRODUCTIZATION / "pocketmd_lite_contract.json"
DEFAULT_REPORT_OUT = PRODUCTIZATION / "pocketmd_lite_topk_survival_report.json"
DEFAULT_SURFACE_OUT = SURFACE_DIR / "pocketmd_lite_science_product_surface.json"
DEFAULT_READONLY_API = PRODUCTIZATION / "pocketmd_lite_readonly_api.json"
DEFAULT_HANDOFF = PRODUCTIZATION / "pocketmd_lite_delivery_handoff.json"

SCHEMA_VERSION = "pocketmd-lite-topk-survival-report.v1"
MATERIALIZATION_SCHEMA_VERSION = "pocketmd-lite-topk-survival-materialization.v1"
SURFACE_SCHEMA_VERSION = "pocketmd-lite-science-product-surface.v1"

REQUIRED_CASE_FIELDS = (
    "case_id",
    "source_family",
    "top_k_rank",
    "candidate_id",
    "pre_refinement_energy_proxy",
    "post_refinement_energy_proxy",
    "local_min_survived",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_count_before",
    "clash_count_after",
    "uncertainty_interval",
    "provenance_ref",
    "source_checksum",
)
REQUIRED_METRICS = (
    "local_min_survival_rate",
    "contact_persistence_rate",
    "h_bond_persistence_rate",
    "clash_relief_rate",
    "uncertainty_width_median",
)
REQUIRED_SUMMARY_METRICS = (
    "local_min_survival_rate",
    "contact_persistence_rate_median",
    "h_bond_persistence_rate_median",
    "clash_relief_rate",
    "uncertainty_width_median",
)
BLOCKED_CLAIMS = (
    "broad_all_atom_md_claim",
    "free_energy_perturbation_claim",
    "long_timescale_md_claim",
    "de_novo_binding_mode_claim",
)
EMPTY_INTAKE_BLOCKERS = (
    "pocketmd_lite_topk_candidate_rows_missing",
    "pocketmd_lite_local_min_survival_rows_missing",
    "pocketmd_lite_contact_persistence_rows_missing",
    "pocketmd_lite_h_bond_persistence_rows_missing",
    "pocketmd_lite_clash_relief_rows_missing",
    "pocketmd_lite_uncertainty_rows_missing",
)
TOPK_ROW_QUALITY_CRITERIA = {
    "min_real_refinement_case_count": 3,
    "min_candidate_count_per_case": 2,
    "min_top_k_rank_coverage_per_case": 2,
    "min_total_top_k_candidate_count": 6,
}
SOURCE_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PLACEHOLDER_SOURCE_TEXT_MARKERS = (
    "<operator",
    "fixture",
    "synthetic",
    "mock",
    "placeholder",
    "dummy",
    "example",
    "operator_supplied",
    "unit-test",
    "test-only",
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
)
PLACEHOLDER_SOURCE_URL_MARKERS = (
    "://example.",
    ".example/",
    ".invalid",
    ".test/",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
)
PLACEHOLDER_SOURCE_URL_PREFIXES = (
    *PLACEHOLDER_PROVENANCE_PREFIXES,
    "file://",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string(value: Any) -> str:
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _is_sha256_ref(value: str) -> bool:
    return bool(SOURCE_CHECKSUM_PATTERN.fullmatch(value))


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not _is_sha256_ref(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _has_placeholder_provenance_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _rate(value: Any) -> float | None:
    parsed = _number(value)
    if parsed is None or parsed < 0.0 or parsed > 1.0:
        return None
    return parsed


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def _uncertainty_width(value: Any) -> tuple[float | None, str]:
    if not isinstance(value, dict):
        return None, ""
    low = _number(value.get("low"))
    high = _number(value.get("high"))
    unit = _string(value.get("unit") or "energy_proxy_delta")
    if low is None or high is None or high < low:
        return None, unit
    return high - low, unit


def _case_rows(intake: Any) -> list[dict[str, Any]]:
    if isinstance(intake, list):
        raw_rows = intake
    elif isinstance(intake, dict):
        raw_rows = _as_list(intake.get("cases"))
    else:
        raw_rows = []
    return [row for row in raw_rows if isinstance(row, dict)]


def _row_key(row: dict[str, Any], index: int) -> str:
    return _string(row.get("case_id")) or f"case_{index + 1}"


def _normalize_candidate_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    row_key = _row_key(row, index)
    blockers: list[str] = []
    root_cause_tags: list[str] = []

    for field in REQUIRED_CASE_FIELDS:
        if field not in row:
            blockers.append(f"{row_key}:{field}_missing")
            root_cause_tags.append("operator_values_required")

    case_id = _string(row.get("case_id"))
    source_family = _string(row.get("source_family"))
    candidate_id = _string(row.get("candidate_id"))
    provenance_ref = _string(row.get("provenance_ref"))
    source_checksum = _string(row.get("source_checksum"))
    top_k_rank = _integer(row.get("top_k_rank"))
    pre_energy = _number(row.get("pre_refinement_energy_proxy"))
    post_energy = _number(row.get("post_refinement_energy_proxy"))
    local_min_survived = _boolean(row.get("local_min_survived"))
    contact_rate = _rate(row.get("contact_persistence_rate"))
    h_bond_rate = _rate(row.get("h_bond_persistence_rate"))
    clash_before = _integer(row.get("clash_count_before"))
    clash_after = _integer(row.get("clash_count_after"))
    uncertainty_width, uncertainty_unit = _uncertainty_width(row.get("uncertainty_interval"))

    string_fields = {
        "case_id": case_id,
        "source_family": source_family,
        "candidate_id": candidate_id,
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
    }
    for field, value in string_fields.items():
        if field in row and not value:
            blockers.append(f"{row_key}:{field}_blank")
            root_cause_tags.append("operator_values_required")
    if (
        "source_checksum" in row
        and source_checksum
        and not _is_sha256_ref(source_checksum)
    ):
        blockers.append(f"{row_key}:source_checksum_invalid")
        root_cause_tags.append("operator_receipts_required")
    elif (
        "source_checksum" in row
        and source_checksum
        and _is_repeated_placeholder_checksum(source_checksum)
    ):
        blockers.append(f"{row_key}:source_checksum_placeholder_digest")
        root_cause_tags.append("operator_receipts_required")
    if (
        "provenance_ref" in row
        and provenance_ref
        and (
            _has_placeholder_provenance_prefix(provenance_ref)
            or _contains_marker(provenance_ref, PLACEHOLDER_SOURCE_TEXT_MARKERS)
        )
    ):
        blockers.append(f"{row_key}:provenance_ref_placeholder")
        root_cause_tags.append("operator_receipts_required")

    if "top_k_rank" in row and (top_k_rank is None or top_k_rank < 1):
        blockers.append(f"{row_key}:top_k_rank_invalid")
        root_cause_tags.append("top_k_rank_invalid")
    if "pre_refinement_energy_proxy" in row and pre_energy is None:
        blockers.append(f"{row_key}:pre_refinement_energy_proxy_invalid")
        root_cause_tags.append("operator_values_required")
    if "post_refinement_energy_proxy" in row and post_energy is None:
        blockers.append(f"{row_key}:post_refinement_energy_proxy_invalid")
        root_cause_tags.append("operator_values_required")
    if "local_min_survived" in row and local_min_survived is None:
        blockers.append(f"{row_key}:local_min_survived_invalid")
        root_cause_tags.append("operator_values_required")
    if "contact_persistence_rate" in row and contact_rate is None:
        blockers.append(f"{row_key}:contact_persistence_rate_invalid")
        root_cause_tags.append("operator_values_required")
    if "h_bond_persistence_rate" in row and h_bond_rate is None:
        blockers.append(f"{row_key}:h_bond_persistence_rate_invalid")
        root_cause_tags.append("operator_values_required")
    if "clash_count_before" in row and (clash_before is None or clash_before < 0):
        blockers.append(f"{row_key}:clash_count_before_invalid")
        root_cause_tags.append("operator_values_required")
    if "clash_count_after" in row and (clash_after is None or clash_after < 0):
        blockers.append(f"{row_key}:clash_count_after_invalid")
        root_cause_tags.append("operator_values_required")
    if "uncertainty_interval" in row and uncertainty_width is None:
        blockers.append(f"{row_key}:uncertainty_interval_invalid")
        root_cause_tags.append("operator_values_required")

    clash_relief = (
        clash_after < clash_before
        if clash_before is not None
        and clash_after is not None
        and clash_before >= 0
        and clash_after >= 0
        else None
    )

    return {
        "case_id": case_id,
        "source_family": source_family,
        "top_k_rank": top_k_rank,
        "candidate_id": candidate_id,
        "pre_refinement_energy_proxy": pre_energy,
        "post_refinement_energy_proxy": post_energy,
        "energy_proxy_delta": (
            post_energy - pre_energy if pre_energy is not None and post_energy is not None else None
        ),
        "local_min_survived": local_min_survived,
        "contact_persistence_rate": contact_rate,
        "h_bond_persistence_rate": h_bond_rate,
        "clash_count_before": clash_before,
        "clash_count_after": clash_after,
        "clash_relief": clash_relief,
        "uncertainty_width": uncertainty_width,
        "uncertainty_unit": uncertainty_unit,
        "provenance_ref": provenance_ref,
        "source_checksum": source_checksum,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
    }


def _topk_row_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    min_case_count = TOPK_ROW_QUALITY_CRITERIA["min_real_refinement_case_count"]
    min_candidates_per_case = TOPK_ROW_QUALITY_CRITERIA[
        "min_candidate_count_per_case"
    ]
    min_rank_coverage = TOPK_ROW_QUALITY_CRITERIA[
        "min_top_k_rank_coverage_per_case"
    ]
    min_total_candidates = TOPK_ROW_QUALITY_CRITERIA[
        "min_total_top_k_candidate_count"
    ]
    required_ranks = list(range(1, min_rank_coverage + 1))
    rows_by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        case_id = _string(row.get("case_id"))
        if case_id:
            rows_by_case.setdefault(case_id, []).append(row)

    case_candidate_counts = {
        case_id: len(case_rows) for case_id, case_rows in sorted(rows_by_case.items())
    }
    case_rank_coverage = {
        case_id: sorted(
            {
                int(top_k_rank)
                for top_k_rank in (row.get("top_k_rank") for row in case_rows)
                if _integer(top_k_rank) is not None and int(top_k_rank) >= 1
            }
        )
        for case_id, case_rows in sorted(rows_by_case.items())
    }

    blockers: list[str] = []
    if rows:
        if len(rows_by_case) < min_case_count:
            blockers.append("pocketmd_lite_real_refinement_case_count_below_minimum")
        if len(rows) < min_total_candidates:
            blockers.append("pocketmd_lite_topk_candidate_count_below_minimum")
        for case_id in sorted(rows_by_case):
            if case_candidate_counts[case_id] < min_candidates_per_case:
                blockers.append(f"{case_id}:top_k_candidate_count_below_minimum")
            rank_set = set(case_rank_coverage[case_id])
            if not set(required_ranks).issubset(rank_set):
                blockers.append(f"{case_id}:top_k_rank_coverage_below_minimum")

    blockers = list(dict.fromkeys(blockers))
    return {
        "contract_pass": bool(rows and not blockers),
        "minimums": dict(TOPK_ROW_QUALITY_CRITERIA),
        "required_rank_span_per_case": required_ranks,
        "real_refinement_case_count": len(rows_by_case),
        "top_k_candidate_count": len(rows),
        "case_candidate_counts": case_candidate_counts,
        "case_rank_coverage": case_rank_coverage,
        "blockers": blockers,
        "root_cause_tags": (
            ["top_k_refinement_coverage_required"] if blockers else []
        ),
    }


def _summary(
    rows: list[dict[str, Any]],
    blockers: list[str],
    *,
    topk_row_quality: dict[str, Any],
) -> dict[str, Any]:
    local_min_rows = [
        bool(row["local_min_survived"])
        for row in rows
        if row.get("local_min_survived") is not None
    ]
    contact_rates = [
        float(row["contact_persistence_rate"])
        for row in rows
        if row.get("contact_persistence_rate") is not None
    ]
    h_bond_rates = [
        float(row["h_bond_persistence_rate"])
        for row in rows
        if row.get("h_bond_persistence_rate") is not None
    ]
    clash_relief_rows = [
        bool(row["clash_relief"]) for row in rows if row.get("clash_relief") is not None
    ]
    uncertainty_widths = [
        float(row["uncertainty_width"])
        for row in rows
        if row.get("uncertainty_width") is not None
    ]
    case_ids = {_string(row.get("case_id")) for row in rows if _string(row.get("case_id"))}

    return {
        "local_min_survival_rate": (
            sum(1 for value in local_min_rows if value) / len(local_min_rows)
            if local_min_rows
            else None
        ),
        "contact_persistence_rate_median": _median(contact_rates),
        "h_bond_persistence_rate_median": _median(h_bond_rates),
        "clash_relief_rate": (
            sum(1 for value in clash_relief_rows if value) / len(clash_relief_rows)
            if clash_relief_rows
            else None
        ),
        "uncertainty_width_median": _median(uncertainty_widths),
        "top_k_candidate_count": len(rows),
        "real_refinement_case_count": len(case_ids),
        "blocker_count": len(blockers),
        "top_k_row_quality": topk_row_quality,
    }


def _topk_integrity_blockers(rows: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    root_cause_tags: list[str] = []
    ranks_by_case: dict[tuple[str, int], str] = {}
    candidates_by_case: dict[tuple[str, str], str] = {}
    for row in rows:
        case_id = _string(row.get("case_id"))
        candidate_id = _string(row.get("candidate_id"))
        top_k_rank = _integer(row.get("top_k_rank"))
        if not case_id:
            continue
        if top_k_rank is not None:
            rank_key = (case_id, top_k_rank)
            if rank_key in ranks_by_case:
                blockers.append(f"{case_id}:top_k_rank_{top_k_rank}_duplicate")
                root_cause_tags.append("top_k_integrity_required")
            else:
                ranks_by_case[rank_key] = candidate_id
        if candidate_id:
            candidate_key = (case_id, candidate_id)
            if candidate_key in candidates_by_case:
                blockers.append(f"{case_id}:candidate_id_{candidate_id}_duplicate")
                root_cause_tags.append("top_k_integrity_required")
            else:
                candidates_by_case[candidate_key] = candidate_id
    return blockers, list(dict.fromkeys(root_cause_tags))


def _operator_input_source_receipt(
    intake: Any,
    *,
    repo_root: Path,
) -> dict[str, Any]:
    source = _as_dict(intake.get("operator_input_source")) if isinstance(intake, dict) else {}
    blockers: list[str] = []
    if not source:
        blockers.append("operator_input_source_receipt_required")
    elif _string(source.get("mode")) != "raw_top_k_refinement_rows":
        blockers.append("operator_input_source_mode_not_raw_top_k_refinement_rows")

    source_artifact = _string(source.get("source_artifact"))
    source_artifact_sha256 = _string(source.get("source_artifact_sha256"))
    if source:
        for field_name in ("source_id", "source_url", "source_license"):
            if not _string(source.get(field_name)):
                blockers.append(f"operator_input_source_{field_name}_required")
        if not source_artifact:
            blockers.append("operator_input_source_source_artifact_required")
        if not source_artifact_sha256:
            blockers.append("operator_input_source_source_artifact_sha256_required")
        elif not source_artifact_sha256.startswith("sha256:"):
            blockers.append("operator_input_source_source_artifact_sha256_invalid")

    source_artifact_exists = False
    source_artifact_sha256_matches = False
    if source_artifact:
        source_path = Path(source_artifact)
        resolved_source = source_path if source_path.is_absolute() else repo_root / source_path
        source_artifact_exists = resolved_source.exists()
        if not source_artifact_exists:
            blockers.append("operator_input_source_source_artifact_missing")
        elif source_artifact_sha256.startswith("sha256:"):
            actual_sha256 = file_sha256(resolved_source)
            source_artifact_sha256_matches = actual_sha256 == source_artifact_sha256
            if not source_artifact_sha256_matches:
                blockers.append("operator_input_source_source_artifact_sha256_mismatch")

    actuality_blockers = _source_actuality_blockers(source) if source else []
    blockers.extend(actuality_blockers)
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "mode": _string(source.get("mode")),
        "source_artifact": source_artifact,
        "source_artifact_present": source_artifact_exists,
        "source_artifact_sha256_present": bool(source_artifact_sha256),
        "source_artifact_sha256_matches": source_artifact_sha256_matches,
        "source_id_present": bool(_string(source.get("source_id"))),
        "source_url_present": bool(_string(source.get("source_url"))),
        "source_license_present": bool(_string(source.get("source_license"))),
        "source_actuality_check": {
            "contract_pass": not actuality_blockers,
            "blockers": actuality_blockers,
            "blocked_marker_policy": {
                "text_markers": list(PLACEHOLDER_SOURCE_TEXT_MARKERS),
                "url_markers": list(PLACEHOLDER_SOURCE_URL_MARKERS),
                "url_prefixes": list(PLACEHOLDER_SOURCE_URL_PREFIXES),
            },
        },
        "blockers": blockers,
        "claim_boundary": (
            "Actual PocketMD Lite top-k refinement closure requires operator rows "
            "plus a verifiable source artifact receipt. In-memory or fixture-like "
            "rows without source metadata remain non-promoting."
        ),
    }


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _has_placeholder_url_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_SOURCE_URL_PREFIXES)


def _source_actuality_blockers(source: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    source_id = _string(source.get("source_id"))
    source_license = _string(source.get("source_license"))
    source_url = _string(source.get("source_url"))
    if source_id and _contains_marker(source_id, PLACEHOLDER_SOURCE_TEXT_MARKERS):
        blockers.append("operator_input_source_source_id_placeholder")
    if source_license and _contains_marker(source_license, PLACEHOLDER_SOURCE_TEXT_MARKERS):
        blockers.append("operator_input_source_source_license_placeholder")
    if source_url and (
        _has_placeholder_url_prefix(source_url)
        or _contains_marker(source_url, PLACEHOLDER_SOURCE_URL_MARKERS)
        or _contains_marker(source_url, PLACEHOLDER_SOURCE_TEXT_MARKERS)
    ):
        blockers.append("operator_input_source_source_url_placeholder")
    return blockers


def build_operator_input_source_receipt(
    intake: Any,
    *,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    return _operator_input_source_receipt(intake, repo_root=repo_root)


def _matching_blockers(blockers: list[str], *needles: str) -> list[str]:
    return [
        blocker
        for blocker in blockers
        if any(needle in blocker for needle in needles)
    ]


def _count_min_gate(
    *,
    criterion_id: str,
    current: int,
    required: int,
    blockers: list[str],
) -> dict[str, Any]:
    passed = current >= required
    return {
        "criterion_id": criterion_id,
        "pass": passed,
        "current": current,
        "required": f">={required}",
        "blockers": [] if passed else blockers,
    }


def _metric_present_gate(
    *,
    criterion_id: str,
    metric_key: str,
    summary: dict[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    current = summary.get(metric_key)
    passed = current is not None
    return {
        "criterion_id": criterion_id,
        "pass": passed,
        "metric_key": metric_key,
        "current": current,
        "required": "present",
        "blockers": [] if passed else blockers,
    }


def _boolean_gate(
    *,
    criterion_id: str,
    current: bool,
    required: bool,
    blockers: list[str],
) -> dict[str, Any]:
    passed = current is required
    return {
        "criterion_id": criterion_id,
        "pass": passed,
        "current": current,
        "required": required,
        "blockers": [] if passed else blockers,
    }


def build_phase4_exit_gate(
    *,
    summary: dict[str, Any],
    blockers: list[str],
    product_surface_ready: bool,
    first_blocked_target: str,
    blocked_claims: list[str] | None = None,
) -> dict[str, Any]:
    claims = blocked_claims if blocked_claims is not None else list(BLOCKED_CLAIMS)
    broad_claims_locked = all(
        claim in claims
        for claim in ("broad_all_atom_md_claim", "free_energy_perturbation_claim")
    )
    criteria = [
        _count_min_gate(
            criterion_id="top_k_refinement_rows_present",
            current=int(summary.get("top_k_candidate_count") or 0),
            required=TOPK_ROW_QUALITY_CRITERIA["min_total_top_k_candidate_count"],
            blockers=_matching_blockers(blockers, "topk_candidate", "candidate_rows"),
        ),
        _boolean_gate(
            criterion_id="top_k_refinement_case_coverage",
            current=bool(
                _as_dict(summary.get("top_k_row_quality")).get("contract_pass")
            ),
            required=True,
            blockers=_matching_blockers(
                blockers,
                "real_refinement_case_count",
                "top_k_candidate_count",
                "top_k_rank_coverage",
                "candidate_rows",
                "topk_candidate",
            ),
        ),
        _metric_present_gate(
            criterion_id="local_min_survival_materialized",
            metric_key="local_min_survival_rate",
            summary=summary,
            blockers=_matching_blockers(blockers, "local_min"),
        ),
        _metric_present_gate(
            criterion_id="contact_persistence_materialized",
            metric_key="contact_persistence_rate_median",
            summary=summary,
            blockers=_matching_blockers(blockers, "contact", "contact_hbond"),
        ),
        _metric_present_gate(
            criterion_id="h_bond_persistence_materialized",
            metric_key="h_bond_persistence_rate_median",
            summary=summary,
            blockers=_matching_blockers(blockers, "h_bond", "contact_hbond"),
        ),
        _metric_present_gate(
            criterion_id="clash_relief_materialized",
            metric_key="clash_relief_rate",
            summary=summary,
            blockers=_matching_blockers(blockers, "clash"),
        ),
        _metric_present_gate(
            criterion_id="uncertainty_summary_materialized",
            metric_key="uncertainty_width_median",
            summary=summary,
            blockers=_matching_blockers(blockers, "uncertainty"),
        ),
        _boolean_gate(
            criterion_id="report_blockers_resolved",
            current=not blockers,
            required=True,
            blockers=blockers,
        ),
        _boolean_gate(
            criterion_id="broad_all_atom_fep_claims_locked",
            current=broad_claims_locked,
            required=True,
            blockers=[],
        ),
    ]
    failed_criteria = [
        str(row["criterion_id"]) for row in criteria if not bool(row["pass"])
    ]
    return {
        "status": "ready" if product_surface_ready and not failed_criteria else "blocked",
        "claim": "pocketmd_lite_top_k_refinement",
        "real_refinement_case_count": int(summary.get("real_refinement_case_count") or 0),
        "top_k_candidate_count": int(summary.get("top_k_candidate_count") or 0),
        "first_blocked_target": first_blocked_target,
        "criteria": criteria,
        "failed_criterion_count": len(failed_criteria),
        "failed_criteria": failed_criteria,
    }


def _input_paths(
    *,
    intake_path: Path | None,
    contract_path: Path | None,
) -> list[Path]:
    paths = [Path("scripts/materialize_pocketmd_lite_topk_survival_report.py")]
    if intake_path is not None:
        paths.append(intake_path)
    if contract_path is not None:
        paths.append(contract_path)
    return paths


def _contract_schema_version(contract: dict[str, Any] | None) -> str:
    if not isinstance(contract, dict):
        return ""
    return _string(contract.get("schema_version"))


def materialize_pocketmd_lite_topk_survival_report(
    intake: Any,
    *,
    contract: dict[str, Any] | None = None,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
    contract_path: Path | None = None,
) -> dict[str, Any]:
    rows = [_normalize_candidate_row(row, index) for index, row in enumerate(_case_rows(intake))]
    blockers = [blocker for row in rows for blocker in row["blockers"]]
    root_cause_tags = list(dict.fromkeys(tag for row in rows for tag in row["root_cause_tags"]))
    integrity_blockers, integrity_root_causes = _topk_integrity_blockers(rows)
    blockers.extend(integrity_blockers)
    root_cause_tags.extend(integrity_root_causes)
    topk_row_quality = _topk_row_quality(rows)
    if rows and not topk_row_quality["contract_pass"]:
        blockers.extend(_as_list(topk_row_quality.get("blockers")))
        root_cause_tags.extend(_as_list(topk_row_quality.get("root_cause_tags")))
    operator_input_source_receipt = _operator_input_source_receipt(
        intake,
        repo_root=repo_root,
    )
    if rows and not operator_input_source_receipt["contract_pass"]:
        blockers.extend(_as_list(operator_input_source_receipt.get("blockers")))
        root_cause_tags.append("operator_receipts_required")
    if not rows:
        blockers.extend(EMPTY_INTAKE_BLOCKERS)
        root_cause_tags.append("operator_refinement_rows_required")

    blockers = list(dict.fromkeys(blockers))
    root_cause_tags = list(dict.fromkeys(root_cause_tags))
    summary = _summary(rows, blockers, topk_row_quality=topk_row_quality)
    metrics_complete = all(summary[metric] is not None for metric in REQUIRED_SUMMARY_METRICS)
    product_surface_ready = bool(
        rows and topk_row_quality["contract_pass"] and not blockers and metrics_complete
    )
    first_blocked_target = next(
        (
            row.get("case_id") or row.get("candidate_id") or "operator_intake"
            for row in rows
            if row["blockers"]
        ),
        "top_k_refinement_operator_intake"
        if blockers and not rows
        else (str(blockers[0]).split(":", 1)[0] if blockers else ""),
    )
    phase4_exit_gate = build_phase4_exit_gate(
        summary=summary,
        blockers=blockers,
        product_surface_ready=product_surface_ready,
        first_blocked_target=first_blocked_target,
        blocked_claims=list(BLOCKED_CLAIMS),
    )

    return {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(intake_path=intake_path, contract_path=contract_path),
            reused_evidence=False,
            reuse_policy="pocketmd_lite_topk_survival_report_materialized_from_operator_intake",
            repo_root=repo_root,
        ),
        "status": "ready" if product_surface_ready else "operator_evidence_required",
        "contract_pass": product_surface_ready,
        "product_surface_ready": product_surface_ready,
        "materialization_schema_version": MATERIALIZATION_SCHEMA_VERSION,
        "contract_schema_version": _contract_schema_version(contract),
        "real_refinement_case_count": summary["real_refinement_case_count"],
        "top_k_candidate_count": summary["top_k_candidate_count"],
        "rows": rows,
        "summary": summary,
        "top_k_row_quality": topk_row_quality,
        "required_metrics": list(REQUIRED_METRICS),
        "required_case_fields": list(REQUIRED_CASE_FIELDS),
        "first_blocked_target": first_blocked_target,
        "root_cause_tags": list(dict.fromkeys(root_cause_tags)),
        "blockers": blockers,
        "operator_input_source_receipt": operator_input_source_receipt,
        "blocked_claims": list(BLOCKED_CLAIMS),
        "phase4_exit_gate": phase4_exit_gate,
        "next_actions": (
            [
                "review_pocketmd_lite_topk_survival_report",
                "regenerate_pocketmd_lite_science_product_surface",
                "regenerate_pm_release_gate_report",
            ]
            if product_surface_ready
            else [
                "attach_top_k_candidate_refinement_rows",
                "rerun_pocketmd_lite_topk_survival_materializer",
                "resolve_report_blockers",
                "regenerate_pocketmd_lite_science_product_surface",
            ]
        ),
        "materialization_report": {
            "schema_version": MATERIALIZATION_SCHEMA_VERSION,
            "operator_intake_row_count": len(rows),
            "real_refinement_case_count": summary["real_refinement_case_count"],
            "top_k_candidate_count": summary["top_k_candidate_count"],
            "top_k_row_quality_contract_pass": topk_row_quality["contract_pass"],
            "top_k_row_quality_minimums": dict(TOPK_ROW_QUALITY_CRITERIA),
            "metric_complete": metrics_complete,
            "blocker_count": len(blockers),
            "product_surface_ready": product_surface_ready,
            "phase4_exit_gate_status": phase4_exit_gate["status"],
            "phase4_failed_criterion_count": phase4_exit_gate["failed_criterion_count"],
        },
        "summary_line": (
            "PocketMD Lite top-k survival report: PASS | "
            f"cases={summary['real_refinement_case_count']} | "
            f"candidates={summary['top_k_candidate_count']} | "
            f"local_min_survival={summary['local_min_survival_rate']}"
            if product_surface_ready
            else (
                "PocketMD Lite top-k survival report: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"blockers={len(blockers)}"
            )
        ),
        "claim_boundary": (
            "This report materializes bounded PocketMD Lite evidence from operator-attached "
            "top-k refinement rows. It does not run MD, create candidate rows, infer FEP, "
            "or unlock broad all-atom dynamics claims."
        ),
    }


def build_pocketmd_lite_science_product_surface(
    report: dict[str, Any],
    *,
    contract: dict[str, Any] | None = None,
    report_path: Path | None = None,
    contract_path: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    product_surface_ready = bool(report.get("product_surface_ready") and report.get("contract_pass"))
    status = "ready" if product_surface_ready else "locked"
    blockers = _as_list(report.get("blockers"))
    root_cause_tags = _as_list(report.get("root_cause_tags"))
    first_blocked_target = _string(report.get("first_blocked_target"))
    if not product_surface_ready and not first_blocked_target:
        first_blocked_target = "top_k_refinement_operator_intake"
    phase4_exit_gate = report.get("phase4_exit_gate")
    if not isinstance(phase4_exit_gate, dict):
        phase4_exit_gate = build_phase4_exit_gate(
            summary=report.get("summary", {}) if isinstance(report.get("summary"), dict) else {},
            blockers=[str(row) for row in blockers],
            product_surface_ready=product_surface_ready,
            first_blocked_target=first_blocked_target,
            blocked_claims=[str(row) for row in _as_list(report.get("blocked_claims"))],
        )

    return {
        "schema_version": SURFACE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=_input_paths(intake_path=report_path, contract_path=contract_path),
            reused_evidence=False,
            reuse_policy="pocketmd_lite_science_product_surface_from_topk_survival_report",
            repo_root=repo_root,
        ),
        "surface_id": "pocketmd_lite_science_product_surface",
        "science_surface_family": "pocketmd_lite",
        "surface_scope": "pocketmd_lite_top_k_refinement",
        "surface_kind": "science_product_surface",
        "product_capability_id": "pocketmd_lite_top_k_refinement",
        "status": status,
        "reason_code": "PASS" if product_surface_ready else "ERR_POCKETMD_LITE_PRODUCT_SURFACE_LOCKED",
        "contract_pass": product_surface_ready,
        "locked": not product_surface_ready,
        "claim_locked": not product_surface_ready,
        "product_surface_ready": product_surface_ready,
        "first_blocked_target": "" if product_surface_ready else first_blocked_target,
        "root_cause_tags": [] if product_surface_ready else root_cause_tags,
        "blockers": [] if product_surface_ready else blockers,
        "blocked_claims": list(BLOCKED_CLAIMS),
        "phase4_exit_gate": phase4_exit_gate,
        "operator_input_source_receipt": _as_dict(
            report.get("operator_input_source_receipt")
        ),
        "required_receipts": [
            "top_k_candidate_refinement_rows",
            "local_min_survival_report",
            "contact_persistence_report",
            "h_bond_persistence_report",
            "clash_relief_report",
            "uncertainty_summary",
        ],
        "linked_artifacts": {
            "contract": str(contract_path or DEFAULT_CONTRACT),
            "topk_survival_report": str(report_path or DEFAULT_REPORT_OUT),
            "readonly_api": str(DEFAULT_READONLY_API),
            "delivery_handoff": str(DEFAULT_HANDOFF),
        },
        "readiness_summary": {
            "contract_ready": bool(contract.get("contract_pass")) if isinstance(contract, dict) else False,
            "readonly_api_ready": True,
            "handoff_ready": True,
            "real_refinement_case_count": int(report.get("real_refinement_case_count") or 0),
            "top_k_candidate_count": int(report.get("top_k_candidate_count") or 0),
            "blocked_claim_count": len(BLOCKED_CLAIMS),
            "summary": report.get("summary", {}),
            "phase4_exit_gate_status": str(phase4_exit_gate.get("status") or ""),
            "phase4_failed_criterion_count": int(
                phase4_exit_gate.get("failed_criterion_count") or 0
            ),
            "phase4_failed_criteria": [
                str(row) for row in _as_list(phase4_exit_gate.get("failed_criteria"))
            ],
        },
        "materializer": {
            "schema_version": MATERIALIZATION_SCHEMA_VERSION,
            "script": "scripts/materialize_pocketmd_lite_topk_survival_report.py",
            "report_path": str(report_path or DEFAULT_REPORT_OUT),
        },
        "goal_roadmap_linkage": {
            "phase": "Phase 4",
            "roadmap_item": "PocketMD Lite science product surface",
            "bottleneck": (
                "pocketmd_lite_science_product_surface_ready"
                if product_surface_ready
                else "pocketmd_lite_science_product_surface_locked"
            ),
            "next_goal_actions": (
                [
                    "publish_pocketmd_lite_readonly_api",
                    "regenerate_product_capabilities_surface",
                    "regenerate_goal_bottleneck_action_board",
                ]
                if product_surface_ready
                else [
                    "run_pocketmd_lite_topk_survival_materializer",
                    "publish_pocketmd_lite_readonly_api",
                    "regenerate_product_capabilities_surface",
                    "regenerate_goal_bottleneck_action_board",
                ]
            ),
        },
        "next_actions": (
            [
                "review_pocketmd_lite_topk_survival_report",
                "publish_pocketmd_lite_readonly_api",
                "regenerate_pm_release_gate_report",
            ]
            if product_surface_ready
            else [
                "attach_top_k_candidate_refinement_rows",
                "run_pocketmd_lite_topk_survival_materializer",
                "regenerate_pocketmd_lite_science_product_surface",
                "regenerate_pm_release_gate_report",
            ]
        ),
        "summary_line": (
            "PocketMD Lite science product surface: PASS | "
            f"cases={int(report.get('real_refinement_case_count') or 0)} | "
            f"candidates={int(report.get('top_k_candidate_count') or 0)}"
            if product_surface_ready
            else (
                "PocketMD Lite science product surface: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'}"
            )
        ),
        "claim_boundary": (
            "PocketMD Lite is exposed as a bounded science product surface for top-k "
            "local refinement evidence only. Broad all-atom MD, FEP, long-timescale "
            "dynamics, and de novo binding claims remain locked."
        ),
    }


def _resolve(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--out-report", type=Path, default=DEFAULT_REPORT_OUT)
    parser.add_argument("--out-surface", type=Path, default=DEFAULT_SURFACE_OUT)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = args.repo_root
    intake_path = _resolve(repo_root, args.intake)
    contract_path = _resolve(repo_root, args.contract)
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    contract = _load_optional_json(contract_path)
    report = materialize_pocketmd_lite_topk_survival_report(
        intake,
        contract=contract,
        repo_root=repo_root,
        intake_path=args.intake,
        contract_path=args.contract if contract_path.exists() else None,
    )

    out_report = _resolve(repo_root, args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(_json_text(report), encoding="utf-8")

    surface = build_pocketmd_lite_science_product_surface(
        report,
        contract=contract,
        report_path=args.out_report,
        contract_path=args.contract if contract_path.exists() else None,
        repo_root=repo_root,
    )
    out_surface = _resolve(repo_root, args.out_surface)
    out_surface.parent.mkdir(parents=True, exist_ok=True)
    out_surface.write_text(_json_text(surface), encoding="utf-8")

    print(
        "pocketmd-lite-topk-survival-materialization: "
        f"{report['status']} | cases={report['real_refinement_case_count']} | "
        f"candidates={report['top_k_candidate_count']} | blockers={len(report['blockers'])}"
    )
    return 1 if args.fail_blocked and not report["product_surface_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
