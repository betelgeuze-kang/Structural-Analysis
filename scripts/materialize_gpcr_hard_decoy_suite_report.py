#!/usr/bin/env python3
"""Materialize a GPCR hard-decoy suite report from operator target metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from release_evidence_metadata import file_sha256, release_evidence_metadata  # noqa: E402


SCHEMA_VERSION = "gpcr-hard-decoy-suite-report.v1"
SURFACE_SCHEMA_VERSION = "gpcr-hard-decoy-evidence-surface.v1"
REQUIRED_TARGETS = ("DRD2", "HTR2A", "OPRM1")
GPCR_PRODUCT_REPORT_ROUTE = "/product/gpcr-hard-decoy-suite-report"
GPCR_OPERATOR_INTAKE_ROUTE = "/product/gpcr-hard-decoy-suite-report/operator-intake"
DEFAULT_OPERATOR_INTAKE_PACKET = Path(
    "implementation/phase1/release_evidence/productization/"
    "gpcr_hard_decoy_operator_intake_packet.json"
)
DEFAULT_OPERATOR_TEMPLATE = Path(
    "implementation/phase1/release_evidence/productization/"
    "gpcr_hard_decoy_operator_template.json"
)
DEFAULT_SUITE_REPORT = Path(
    "implementation/phase1/release_evidence/productization/"
    "gpcr_hard_decoy_suite_report.json"
)
DEFAULT_EVIDENCE_SURFACE = Path(
    "implementation/phase1/release_evidence/surface/"
    "gpcr_hard_decoy_evidence_surface.json"
)
EXIT_CRITERIA = {
    "ranking_pr_auc_ci_low_min": 0.45,
    "top20_hit_rate_min": 0.20,
    "decoys_above_positive_count_max": 0,
    "positive_out_anchored_by_top_decoys_allowed": False,
}
ACTUAL_CLOSURE_CRITERION_ID = "raw_hard_decoy_rows_actual_closure"
RAW_ROW_QUALITY_CRITERIA = {
    "min_positive_count_per_target": 4,
    "min_decoy_count_per_target": 20,
    "min_total_row_count_per_target": 24,
}
PHASE3_MATERIALIZATION_STEPS = [
    "materialize_gpcr_hard_decoy_suite_report",
    "refresh_gpcr_hard_decoy_product_report",
    "refresh_product_capabilities_surface",
    "refresh_goal_bottleneck_roadmap_surface",
]
RAW_RANKING_ROW_FIELDS = ("molecule_id", "score", "is_positive", "is_decoy")
RAW_RANKING_SOURCE_RECEIPT_FIELDS = ("source_checksum", "provenance_ref")
REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS = (
    *RAW_RANKING_ROW_FIELDS,
    *RAW_RANKING_SOURCE_RECEIPT_FIELDS,
)
RANKING_PR_AUC_CI_CONFIDENCE_LEVEL = 0.95
RANKING_PR_AUC_BOOTSTRAP_REPLICATES = 512
SOURCE_CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-fA-F]{64}$")
PLACEHOLDER_SOURCE_TEXT_MARKERS = (
    "<operator",
    "fixture",
    "synthetic",
    "mock",
    "placeholder",
    "dummy",
    "example",
    "unit-test",
    "test-only",
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


def _slot_id_for_target(target_id: str) -> str:
    return f"{target_id.lower()}_hard_decoy_metrics"


def _phase3_minimum_evidence(target_id: str) -> dict[str, Any]:
    return {
        "target_id": target_id,
        "required_operator_fields": [
            "target_id",
            "ranking_pr_auc_ci_low",
            "top20_hit_rate",
            "decoys_above_positive_count",
            "positive_out_anchored_by_top_decoys",
            "score_direction",
            "hard_decoy_rows",
        ],
        "required_hard_decoy_row_fields": list(
            REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS
        ),
        "thresholds": {
            "ranking_pr_auc_ci_low": ">=0.45",
            "top20_hit_rate": ">=0.2",
            "decoys_above_positive_count": "<=0",
            "positive_out_anchored_by_top_decoys": False,
            "hard_decoy_rows": (
                "computed_from_raw_hard_decoy_rows_with_quality_minimums"
            ),
        },
        "raw_row_quality_minimums": dict(RAW_ROW_QUALITY_CRITERIA),
        "criterion_by_field": {
            "ranking_pr_auc_ci_low": "ranking_pr_auc_ci_low_min",
            "top20_hit_rate": "top20_hit_rate_min",
            "decoys_above_positive_count": "decoys_above_positive_count_max",
            "positive_out_anchored_by_top_decoys": (
                "no_positive_out_anchored_by_top_decoys"
            ),
            "hard_decoy_rows": ACTUAL_CLOSURE_CRITERION_ID,
        },
        "accepted_input_modes": [
            {
                "mode": "summary_metrics",
                "closure_scope": "preflight_only",
                "required_fields": [
                    "target_id",
                    "ranking_pr_auc_ci_low",
                    "top20_hit_rate",
                    "decoys_above_positive_count",
                    "positive_out_anchored_by_top_decoys",
                ],
            },
            {
                "mode": "raw_hard_decoy_rows",
                "closure_scope": "actual_phase3_closure",
                "required_fields": ["target_id", "score_direction", "hard_decoy_rows"],
                "required_row_fields": list(
                    REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS
                ),
                "computed_fields": [
                    "ranking_pr_auc_ci_low",
                    "top20_hit_rate",
                    "decoys_above_positive_count",
                    "positive_out_anchored_by_top_decoys",
                    "hard_decoy_row_quality",
                ],
            },
        ],
        "row_source_receipt_policy": {
            "required_row_fields": list(RAW_RANKING_SOURCE_RECEIPT_FIELDS),
            "source_checksum_policy": (
                "source_checksum must be sha256:<64 hex> and not a repeated "
                "placeholder digest"
            ),
            "provenance_ref_policy": (
                "provenance_ref must be nonblank and must not use local, fixture, "
                "mock, synthetic, placeholder, or file-only provenance prefixes"
            ),
        },
        "actual_closure_required_mode": "raw_hard_decoy_rows",
    }


def _materialization_command() -> str:
    return (
        "python3 scripts/materialize_gpcr_hard_decoy_suite_report.py "
        f"--intake {DEFAULT_OPERATOR_TEMPLATE} "
        f"--out-report {DEFAULT_SUITE_REPORT} "
        f"--out-surface {DEFAULT_EVIDENCE_SURFACE} --fail-blocked"
    )


def _operator_evidence_gap_register(report: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = [
        row
        for row in _as_list(_as_dict(report.get("phase3_exit_gate")).get("criteria"))
        if isinstance(row, dict)
    ]
    target_rows = [
        row for row in _as_list(report.get("target_rows")) if isinstance(row, dict)
    ]
    rows: list[dict[str, Any]] = []
    for index, target_id in enumerate(REQUIRED_TARGETS, start=1):
        target_row = next(
            (row for row in target_rows if str(row.get("target_id") or "") == target_id),
            {},
        )
        blocked_criteria = [
            str(row.get("criterion_id") or "")
            for row in criteria
            if target_id in [str(item) for item in _as_list(row.get("failed_targets"))]
        ]
        if target_row and target_row.get("status") == "pass" and not blocked_criteria:
            continue
        if not blocked_criteria:
            blocked_criteria = [
                "ranking_pr_auc_ci_low_min",
                "top20_hit_rate_min",
                "decoys_above_positive_count_max",
                "no_positive_out_anchored_by_top_decoys",
                ACTUAL_CLOSURE_CRITERION_ID,
            ]
        rows.append(
            {
                "slot_priority": index,
                "slot_id": _slot_id_for_target(target_id),
                "target_id": target_id,
                "status": "operator_input_required",
                "phase3_blocked": True,
                "blocked_phase3_criteria": blocked_criteria,
                "first_next_action": (
                    f"fill {target_id} hard-decoy metrics in the GPCR operator "
                    "intake packet"
                ),
                "minimum_evidence": _phase3_minimum_evidence(target_id),
                "materialization_steps": list(PHASE3_MATERIALIZATION_STEPS),
                "materialization_command": _materialization_command(),
                "validation_command": _materialization_command(),
            }
        )
    return rows


def _operator_handoff_summary(
    report: dict[str, Any],
    operator_evidence_gap_register: list[dict[str, Any]],
) -> dict[str, Any]:
    first_operator_evidence_gap = (
        operator_evidence_gap_register[0] if operator_evidence_gap_register else {}
    )
    blockers = _as_list(report.get("blockers"))
    return {
        "route": GPCR_OPERATOR_INTAKE_ROUTE,
        "artifact": str(DEFAULT_OPERATOR_INTAKE_PACKET),
        "first_blocker": str(blockers[0]) if blockers else "",
        "first_blocked_target": str(report.get("first_blocked_target") or ""),
        "first_next_action": str(
            first_operator_evidence_gap.get("first_next_action") or ""
        ),
        "required_slot_count": len(REQUIRED_TARGETS),
        "blocked_operator_slot_count": len(operator_evidence_gap_register),
        "minimum_evidence": dict(
            first_operator_evidence_gap.get("minimum_evidence") or {}
        ),
        "materialization_steps": [
            str(row)
            for row in _as_list(first_operator_evidence_gap.get("materialization_steps"))
        ],
        "materialization_command": str(
            first_operator_evidence_gap.get("materialization_command") or ""
        ),
        "validation_command": str(
            first_operator_evidence_gap.get("validation_command") or ""
        ),
    }


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _target_key(value: Any) -> str:
    return str(value or "").strip().upper()


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
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


def _operator_input_source_receipt(
    intake: dict[str, Any],
    *,
    repo_root: Path,
) -> dict[str, Any]:
    source = _as_dict(intake.get("operator_input_source"))
    blockers: list[str] = []
    if not source:
        blockers.append("operator_input_source_receipt_required")
    elif str(source.get("mode") or "") != "raw_hard_decoy_rows":
        blockers.append("operator_input_source_mode_not_raw_hard_decoy_rows")

    source_artifact = str(source.get("source_artifact") or "").strip()
    source_artifact_sha256 = str(source.get("source_artifact_sha256") or "").strip()
    if source:
        for field_name in ("source_id", "source_url", "source_license"):
            if not str(source.get(field_name) or "").strip():
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
        "mode": str(source.get("mode") or ""),
        "source_artifact": source_artifact,
        "source_artifact_present": source_artifact_exists,
        "source_artifact_sha256_present": bool(source_artifact_sha256),
        "source_artifact_sha256_matches": source_artifact_sha256_matches,
        "source_id_present": bool(str(source.get("source_id") or "").strip()),
        "source_url_present": bool(str(source.get("source_url") or "").strip()),
        "source_license_present": bool(str(source.get("source_license") or "").strip()),
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
            "Actual GPCR Phase 3 closure requires raw hard-decoy rows plus a "
            "verifiable operator input source receipt. In-memory or fixture-like rows "
            "without source artifact metadata remain non-promoting."
        ),
    }


def _contains_marker(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in markers)


def _has_placeholder_url_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_SOURCE_URL_PREFIXES)


def _has_placeholder_provenance_prefix(value: str) -> bool:
    lowered = value.lower()
    return any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PROVENANCE_PREFIXES)


def _is_repeated_placeholder_checksum(value: str) -> bool:
    if not SOURCE_CHECKSUM_PATTERN.fullmatch(value):
        return False
    digest = value.split(":", 1)[1].lower()
    return len(set(digest)) == 1


def _source_actuality_blockers(source: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    source_id = str(source.get("source_id") or "").strip()
    source_license = str(source.get("source_license") or "").strip()
    source_url = str(source.get("source_url") or "").strip()
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


def _score_direction(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token in {"", "higher", "higher_is_better", "descending"}:
        return "higher_is_better"
    if token in {"lower", "lower_is_better", "ascending"}:
        return "lower_is_better"
    return token


def _row_by_target(intake: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _as_list(intake.get("targets")):
        if not isinstance(row, dict):
            continue
        target_id = _target_key(row.get("target_id") or row.get("target"))
        if target_id:
            rows[target_id] = row
    return rows


def _raw_hard_decoy_rows(row: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("hard_decoy_rows", "ranking_rows", "scored_molecules"):
        rows = _as_list(row.get(key))
        if rows:
            return [item for item in rows if isinstance(item, dict)]
    return []


def _average_precision(ranked_rows: list[dict[str, Any]], positive_count: int) -> float | None:
    if positive_count <= 0:
        return None
    precision_sum = 0.0
    hits = 0
    for index, ranked_row in enumerate(ranked_rows, start=1):
        if bool(ranked_row["is_positive"]):
            hits += 1
            precision_sum += hits / index
    return precision_sum / positive_count


def _stable_bootstrap_seed(target_id: str, rows: list[dict[str, Any]]) -> int:
    payload = {
        "target_id": target_id,
        "rows": [
            {
                "molecule_id": str(row["molecule_id"]),
                "score": float(row["score"]),
                "is_positive": bool(row["is_positive"]),
                "is_decoy": bool(row["is_decoy"]),
            }
            for row in rows
        ],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _rank_rows(rows: list[dict[str, Any]], *, score_direction: str) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda ranked_row: (float(ranked_row["score"]), str(ranked_row["molecule_id"])),
        reverse=score_direction == "higher_is_better",
    )


def _score_is_better(left: float, right: float, *, score_direction: str) -> bool:
    if score_direction == "lower_is_better":
        return left < right
    return left > right


def _score_is_at_least_as_good(
    left: float,
    right: float,
    *,
    score_direction: str,
) -> bool:
    if score_direction == "lower_is_better":
        return left <= right
    return left >= right


def _best_score(scores: list[float], *, score_direction: str) -> float:
    return min(scores) if score_direction == "lower_is_better" else max(scores)


def _worst_score(scores: list[float], *, score_direction: str) -> float:
    return max(scores) if score_direction == "lower_is_better" else min(scores)


def _bootstrap_average_precision_ci_low(
    *,
    target_id: str,
    normalized_rows: list[dict[str, Any]],
    score_direction: str,
    confidence_level: float = RANKING_PR_AUC_CI_CONFIDENCE_LEVEL,
    replicate_count: int = RANKING_PR_AUC_BOOTSTRAP_REPLICATES,
) -> float | None:
    positives = [row for row in normalized_rows if row["is_positive"]]
    decoys = [row for row in normalized_rows if row["is_decoy"]]
    if not positives or not decoys or replicate_count <= 0:
        return None
    rng = random.Random(_stable_bootstrap_seed(target_id, normalized_rows))
    bootstrap_values: list[float] = []
    for _index in range(replicate_count):
        sampled_rows = [
            rng.choice(positives) for _positive_index in range(len(positives))
        ] + [rng.choice(decoys) for _decoy_index in range(len(decoys))]
        ranked_sample = _rank_rows(sampled_rows, score_direction=score_direction)
        score = _average_precision(ranked_sample, len(positives))
        if score is not None:
            bootstrap_values.append(score)
    if not bootstrap_values:
        return None
    bootstrap_values.sort()
    lower_tail = max((1.0 - confidence_level) / 2.0, 0.0)
    lower_index = min(
        len(bootstrap_values) - 1,
        max(0, int(math.floor(lower_tail * len(bootstrap_values)))),
    )
    return float(bootstrap_values[lower_index])


def _computed_hard_decoy_metrics(
    target_id: str,
    row: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    raw_rows = _raw_hard_decoy_rows(row)
    if not raw_rows:
        return {}, [], []

    blockers: list[str] = []
    root_cause_tags: list[str] = []
    normalized_rows: list[dict[str, Any]] = []
    seen_molecule_ids: set[str] = set()
    score_direction = _score_direction(row.get("score_direction"))
    if score_direction not in {"higher_is_better", "lower_is_better"}:
        blockers.append(f"{target_id}:score_direction_invalid")
        root_cause_tags.append("operator_values_required")
        score_direction = "higher_is_better"

    for index, raw_row in enumerate(raw_rows):
        row_key = str(raw_row.get("molecule_id") or f"row_{index + 1}").strip()
        for field in REQUIRED_ACTUAL_CLOSURE_RAW_ROW_FIELDS:
            if field not in raw_row:
                blockers.append(f"{target_id}:{row_key}:{field}_missing")
                if field in RAW_RANKING_SOURCE_RECEIPT_FIELDS:
                    root_cause_tags.append("hard_decoy_row_actuality_required")
                else:
                    root_cause_tags.append("operator_values_required")
        molecule_id = str(raw_row.get("molecule_id") or "").strip()
        score = _number(raw_row.get("score"))
        is_positive = _boolean(raw_row.get("is_positive"))
        is_decoy = _boolean(raw_row.get("is_decoy"))
        source_checksum = str(raw_row.get("source_checksum") or "").strip()
        provenance_ref = str(raw_row.get("provenance_ref") or "").strip()
        if "molecule_id" in raw_row and not molecule_id:
            blockers.append(f"{target_id}:{row_key}:molecule_id_blank")
            root_cause_tags.append("operator_values_required")
        elif molecule_id and _contains_marker(molecule_id, PLACEHOLDER_SOURCE_TEXT_MARKERS):
            blockers.append(f"{target_id}:{row_key}:molecule_id_placeholder")
            root_cause_tags.append("hard_decoy_row_actuality_required")
        elif molecule_id:
            if molecule_id in seen_molecule_ids:
                blockers.append(f"{target_id}:{row_key}:molecule_id_duplicate")
                root_cause_tags.append("hard_decoy_row_integrity_required")
            seen_molecule_ids.add(molecule_id)
        if "score" in raw_row and score is None:
            blockers.append(f"{target_id}:{row_key}:score_invalid")
            root_cause_tags.append("operator_values_required")
        if "is_positive" in raw_row and is_positive is None:
            blockers.append(f"{target_id}:{row_key}:is_positive_invalid")
            root_cause_tags.append("operator_values_required")
        if "is_decoy" in raw_row and is_decoy is None:
            blockers.append(f"{target_id}:{row_key}:is_decoy_invalid")
            root_cause_tags.append("operator_values_required")
        if is_positive is not None and is_decoy is not None and is_positive is is_decoy:
            blockers.append(f"{target_id}:{row_key}:positive_decoy_label_invalid")
            root_cause_tags.append("operator_values_required")
        if "source_checksum" in raw_row:
            if not source_checksum:
                blockers.append(f"{target_id}:{row_key}:source_checksum_blank")
                root_cause_tags.append("hard_decoy_row_actuality_required")
            elif not SOURCE_CHECKSUM_PATTERN.fullmatch(source_checksum):
                blockers.append(f"{target_id}:{row_key}:source_checksum_invalid")
                root_cause_tags.append("hard_decoy_row_actuality_required")
            elif _is_repeated_placeholder_checksum(source_checksum):
                blockers.append(
                    f"{target_id}:{row_key}:source_checksum_placeholder_digest"
                )
                root_cause_tags.append("hard_decoy_row_actuality_required")
        if "provenance_ref" in raw_row:
            if not provenance_ref:
                blockers.append(f"{target_id}:{row_key}:provenance_ref_blank")
                root_cause_tags.append("hard_decoy_row_actuality_required")
            elif (
                _has_placeholder_provenance_prefix(provenance_ref)
                or _contains_marker(provenance_ref, PLACEHOLDER_SOURCE_TEXT_MARKERS)
            ):
                blockers.append(f"{target_id}:{row_key}:provenance_ref_placeholder")
                root_cause_tags.append("hard_decoy_row_actuality_required")
        if score is not None and is_positive is not None and is_decoy is not None:
            normalized_rows.append(
                {
                    "molecule_id": molecule_id or row_key,
                    "score": score,
                    "is_positive": is_positive,
                    "is_decoy": is_decoy,
                }
            )

    positive_count = sum(1 for ranked_row in normalized_rows if ranked_row["is_positive"])
    decoy_count = sum(1 for ranked_row in normalized_rows if ranked_row["is_decoy"])
    if normalized_rows and positive_count == 0:
        blockers.append(f"{target_id}:positive_rows_missing")
        root_cause_tags.append("operator_values_required")
    if normalized_rows and decoy_count == 0:
        blockers.append(f"{target_id}:decoy_rows_missing")
        root_cause_tags.append("operator_values_required")
    if blockers:
        return {
            "hard_decoy_row_count": len(raw_rows),
            "valid_hard_decoy_row_count": len(normalized_rows),
            "hard_decoy_positive_count": positive_count,
            "hard_decoy_decoy_count": decoy_count,
            "hard_decoy_row_quality": {
                "contract_pass": False,
                "minimums": dict(RAW_ROW_QUALITY_CRITERIA),
                "positive_count": positive_count,
                "decoy_count": decoy_count,
                "total_row_count": len(normalized_rows),
                "blockers": blockers,
            },
            "calculation_status": "blocked",
        }, blockers, root_cause_tags

    ranked_rows = _rank_rows(normalized_rows, score_direction=score_direction)
    ranked_with_positions = [
        {**ranked_row, "rank": index}
        for index, ranked_row in enumerate(ranked_rows, start=1)
    ]
    positive_scores = [
        float(ranked_row["score"])
        for ranked_row in normalized_rows
        if ranked_row["is_positive"]
    ]
    decoy_scores = [
        float(ranked_row["score"])
        for ranked_row in normalized_rows
        if ranked_row["is_decoy"]
    ]
    top20_rows = ranked_with_positions[: min(20, len(ranked_with_positions))]
    top20_hit_rate = (
        sum(1 for ranked_row in top20_rows if ranked_row["is_positive"]) / len(top20_rows)
        if top20_rows
        else None
    )
    best_positive_score = _best_score(positive_scores, score_direction=score_direction)
    worst_positive_score = _worst_score(positive_scores, score_direction=score_direction)
    best_decoy_score = _best_score(decoy_scores, score_direction=score_direction)
    decoys_above_positive_count = sum(
        1
        for score in decoy_scores
        if _score_is_better(score, best_positive_score, score_direction=score_direction)
    )
    out_anchored_positive_count = sum(
        1
        for score in positive_scores
        if _score_is_at_least_as_good(
            best_decoy_score,
            score,
            score_direction=score_direction,
        )
    )
    positive_out_anchored_by_top_decoys = bool(
        decoy_scores and out_anchored_positive_count > 0
    )
    average_precision = _average_precision(ranked_with_positions, positive_count)
    average_precision_ci_low = _bootstrap_average_precision_ci_low(
        target_id=target_id,
        normalized_rows=normalized_rows,
        score_direction=score_direction,
    )
    quality_blockers: list[str] = []
    quality_root_cause_tags: list[str] = []
    if positive_count < RAW_ROW_QUALITY_CRITERIA["min_positive_count_per_target"]:
        quality_blockers.append(
            f"{target_id}:hard_decoy_rows_positive_count_below_actual_closure_minimum"
        )
    if decoy_count < RAW_ROW_QUALITY_CRITERIA["min_decoy_count_per_target"]:
        quality_blockers.append(
            f"{target_id}:hard_decoy_rows_decoy_count_below_actual_closure_minimum"
        )
    if len(normalized_rows) < RAW_ROW_QUALITY_CRITERIA["min_total_row_count_per_target"]:
        quality_blockers.append(
            f"{target_id}:hard_decoy_rows_total_count_below_actual_closure_minimum"
        )
    if quality_blockers:
        quality_root_cause_tags.append("hard_decoy_row_quality_required")

    return {
        "hard_decoy_row_count": len(raw_rows),
        "valid_hard_decoy_row_count": len(normalized_rows),
        "hard_decoy_positive_count": positive_count,
        "hard_decoy_decoy_count": decoy_count,
        "score_direction": score_direction,
        "ranking_pr_auc": average_precision,
        "ranking_pr_auc_ci_low": average_precision_ci_low,
        "ranking_pr_auc_ci_confidence_level": RANKING_PR_AUC_CI_CONFIDENCE_LEVEL,
        "ranking_pr_auc_ci_method": "deterministic_stratified_bootstrap_average_precision",
        "ranking_pr_auc_ci_replicates": RANKING_PR_AUC_BOOTSTRAP_REPLICATES,
        "top20_hit_rate": top20_hit_rate,
        "decoys_above_positive_count": decoys_above_positive_count,
        "positive_out_anchored_by_top_decoys": positive_out_anchored_by_top_decoys,
        "out_anchored_positive_count": out_anchored_positive_count,
        "best_positive_score": best_positive_score,
        "worst_positive_score": worst_positive_score,
        "best_decoy_score": best_decoy_score,
        "top_decoy_anchor_policy": (
            "score_direction_aware; top decoy tied with or better than any positive blocks"
        ),
        "calculation_method": (
            "ranking_pr_auc_ci_low=deterministic_stratified_bootstrap_average_precision; "
            "top20_hit_rate=positive_fraction_in_top_min_20_rows; "
            "decoys_above_positive_count=decoys_strictly_better_than_best_positive; "
            "positive_out_anchored_by_top_decoys="
            "top_decoy_tied_with_or_better_than_any_positive"
        ),
        "hard_decoy_row_quality": {
            "contract_pass": not quality_blockers,
            "minimums": dict(RAW_ROW_QUALITY_CRITERIA),
            "positive_count": positive_count,
            "decoy_count": decoy_count,
            "total_row_count": len(normalized_rows),
            "blockers": quality_blockers,
        },
        "calculation_status": (
            "computed" if not quality_blockers else "computed_but_quality_blocked"
        ),
    }, quality_blockers, quality_root_cause_tags


def _metric_value(
    row: dict[str, Any],
    computed_metrics: dict[str, Any],
    field_name: str,
) -> Any:
    if field_name in row and row.get(field_name) is not None:
        return row.get(field_name)
    return computed_metrics.get(field_name)


def _float_matches(left: float, right: float, *, tolerance: float = 1.0e-9) -> bool:
    return abs(left - right) <= tolerance


def _computed_metric_consistency_blockers(
    target_id: str,
    row: dict[str, Any],
    computed_metrics: dict[str, Any],
) -> tuple[list[str], list[str]]:
    if computed_metrics.get("calculation_status") != "computed":
        return [], []
    blockers: list[str] = []
    root_cause_tags: list[str] = []
    comparable_fields = (
        "top20_hit_rate",
        "decoys_above_positive_count",
        "positive_out_anchored_by_top_decoys",
    )
    for field_name in comparable_fields:
        if (
            field_name not in row
            or row.get(field_name) is None
            or computed_metrics.get(field_name) is None
        ):
            continue
        supplied = row.get(field_name)
        computed = computed_metrics[field_name]
        consistent = supplied is computed
        if isinstance(computed, bool):
            consistent = _boolean(supplied) is computed
        elif isinstance(computed, float):
            supplied_number = _number(supplied)
            consistent = (
                supplied_number is not None
                and _float_matches(float(supplied_number), computed)
            )
        elif isinstance(computed, int):
            consistent = _integer(supplied) == computed
        if not consistent:
            blockers.append(f"{target_id}:{field_name}_inconsistent_with_hard_decoy_rows")
            root_cause_tags.append("hard_decoy_metric_inconsistency")

    ranking_ci_low = _number(row.get("ranking_pr_auc_ci_low"))
    ranking_pr_auc = _number(computed_metrics.get("ranking_pr_auc"))
    if ranking_ci_low is not None and ranking_pr_auc is not None and ranking_ci_low > ranking_pr_auc:
        blockers.append(f"{target_id}:ranking_pr_auc_ci_low_above_computed_pr_auc")
        root_cause_tags.append("hard_decoy_metric_inconsistency")
    computed_ci_low = _number(computed_metrics.get("ranking_pr_auc_ci_low"))
    if (
        ranking_ci_low is not None
        and computed_ci_low is not None
        and ranking_ci_low > computed_ci_low
        and not _float_matches(ranking_ci_low, computed_ci_low)
    ):
        blockers.append(
            f"{target_id}:ranking_pr_auc_ci_low_inconsistent_with_hard_decoy_rows"
        )
        root_cause_tags.append("hard_decoy_metric_inconsistency")
    return blockers, root_cause_tags


def _missing_target_row(target_id: str) -> dict[str, Any]:
    blockers = [
        f"{target_id}:operator_metrics_required",
        f"{target_id}:ranking_pr_auc_ci_low_required",
        f"{target_id}:top20_hit_rate_required",
        f"{target_id}:decoys_above_positive_count_required",
        f"{target_id}:positive_out_anchored_by_top_decoys_required",
        f"{target_id}:hard_decoy_rows_required_for_actual_closure",
    ]
    return {
        "target_id": target_id,
        "status": "blocked",
        "contract_pass": False,
        "ranking_pr_auc_ci_low": None,
        "top20_hit_rate": None,
        "decoys_above_positive_count": None,
        "positive_out_anchored_by_top_decoys": None,
        "computed_hard_decoy_metrics": {"calculation_status": "missing"},
        "criteria": EXIT_CRITERIA,
        "root_cause_tags": ["operator_values_required"],
        "blockers": blockers,
    }


def _target_result(target_id: str, row: dict[str, Any]) -> dict[str, Any]:
    computed_metrics, computed_blockers, computed_root_causes = (
        _computed_hard_decoy_metrics(target_id, row)
    )
    ranking = _number(_metric_value(row, computed_metrics, "ranking_pr_auc_ci_low"))
    top20 = _number(_metric_value(row, computed_metrics, "top20_hit_rate"))
    decoys_above = _integer(
        _metric_value(row, computed_metrics, "decoys_above_positive_count")
    )
    out_anchored = _boolean(
        _metric_value(row, computed_metrics, "positive_out_anchored_by_top_decoys")
        if "positive_out_anchored_by_top_decoys" in row
        or "positive_out_anchored_by_top_decoys" in computed_metrics
        else row.get("positive_out_anchored_by_top_decoy")
    )
    blockers: list[str] = []
    root_cause_tags: list[str] = []
    blockers.extend(computed_blockers)
    root_cause_tags.extend(computed_root_causes)
    consistency_blockers, consistency_root_causes = (
        _computed_metric_consistency_blockers(target_id, row, computed_metrics)
    )
    blockers.extend(consistency_blockers)
    root_cause_tags.extend(consistency_root_causes)
    if not _raw_hard_decoy_rows(row):
        blockers.append(f"{target_id}:hard_decoy_rows_required_for_actual_closure")
        root_cause_tags.append("hard_decoy_rows_required")

    if ranking is None:
        blockers.append(f"{target_id}:ranking_pr_auc_ci_low_required")
        root_cause_tags.append("operator_values_required")
    elif ranking < EXIT_CRITERIA["ranking_pr_auc_ci_low_min"]:
        blockers.append(f"{target_id}:ranking_pr_auc_ci_low_below_threshold")
        root_cause_tags.append("ranking_pr_auc_ci_low_below_threshold")

    if top20 is None:
        blockers.append(f"{target_id}:top20_hit_rate_required")
        root_cause_tags.append("operator_values_required")
    elif top20 < EXIT_CRITERIA["top20_hit_rate_min"]:
        blockers.append(f"{target_id}:top20_hit_rate_below_threshold")
        root_cause_tags.append("top20_hit_rate_below_threshold")

    if decoys_above is None:
        blockers.append(f"{target_id}:decoys_above_positive_count_required")
        root_cause_tags.append("operator_values_required")
    elif decoys_above > EXIT_CRITERIA["decoys_above_positive_count_max"]:
        blockers.append(f"{target_id}:decoys_above_positive_count_above_limit")
        root_cause_tags.append("decoy_rank_leakage")

    if out_anchored is None:
        blockers.append(f"{target_id}:positive_out_anchored_by_top_decoys_required")
        root_cause_tags.append("operator_values_required")
    elif out_anchored is not EXIT_CRITERIA["positive_out_anchored_by_top_decoys_allowed"]:
        blockers.append(f"{target_id}:positive_out_anchored_by_top_decoys")
        root_cause_tags.append("positive_out_anchored_by_top_decoys")

    deduped_root_causes = list(dict.fromkeys(root_cause_tags))
    return {
        "target_id": target_id,
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "ranking_pr_auc_ci_low": ranking,
        "top20_hit_rate": top20,
        "decoys_above_positive_count": decoys_above,
        "positive_out_anchored_by_top_decoys": out_anchored,
        "computed_hard_decoy_metrics": computed_metrics,
        "criteria": EXIT_CRITERIA,
        "root_cause_tags": deduped_root_causes,
        "blockers": blockers,
    }


def _field_blockers(row: dict[str, Any], field_name: str) -> list[str]:
    return [
        str(blocker)
        for blocker in _as_list(row.get("blockers"))
        if str(blocker).split(":", 1)[-1].startswith(field_name)
    ]


def _numeric_min_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: float,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, float | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _number(row.get(field_name))
        current_by_target[target_id] = value
        if value is None or value < required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": f">={required:g}",
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _integer_max_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: int,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, int | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _integer(row.get(field_name))
        current_by_target[target_id] = value
        if value is None or value > required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": f"<={required}",
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _boolean_gate(
    *,
    target_rows: list[dict[str, Any]],
    criterion_id: str,
    field_name: str,
    required: bool,
) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, bool | None] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        value = _boolean(row.get(field_name))
        current_by_target[target_id] = value
        if value is not required:
            failed_targets.append(target_id)
            blockers.extend(_field_blockers(row, field_name))
    return {
        "criterion_id": criterion_id,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": required,
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _actual_hard_decoy_rows_gate(*, target_rows: list[dict[str, Any]]) -> dict[str, Any]:
    failed_targets: list[str] = []
    blockers: list[str] = []
    current_by_target: dict[str, str] = {}
    for row in target_rows:
        target_id = str(row.get("target_id") or "")
        computed_metrics = _as_dict(row.get("computed_hard_decoy_metrics"))
        status = str(computed_metrics.get("calculation_status") or "")
        current_by_target[target_id] = status or "missing"
        if status != "computed":
            failed_targets.append(target_id)
            blockers.extend(
                str(blocker)
                for blocker in _as_list(row.get("blockers"))
                if "hard_decoy_rows" in str(blocker)
                or "positive_rows_missing" in str(blocker)
                or "decoy_rows_missing" in str(blocker)
                or "operator_input_source" in str(blocker)
            )
    return {
        "criterion_id": ACTUAL_CLOSURE_CRITERION_ID,
        "pass": not failed_targets,
        "current_by_target": current_by_target,
        "required": "computed_from_raw_hard_decoy_rows_with_quality_minimums",
        "failed_targets": failed_targets,
        "blockers": blockers,
    }


def _phase3_exit_gate(
    *,
    target_rows: list[dict[str, Any]],
    target_pass_count: int,
    broad_safe: bool,
    first_blocked_target: str,
) -> dict[str, Any]:
    criteria = [
        _numeric_min_gate(
            target_rows=target_rows,
            criterion_id="ranking_pr_auc_ci_low_min",
            field_name="ranking_pr_auc_ci_low",
            required=float(EXIT_CRITERIA["ranking_pr_auc_ci_low_min"]),
        ),
        _numeric_min_gate(
            target_rows=target_rows,
            criterion_id="top20_hit_rate_min",
            field_name="top20_hit_rate",
            required=float(EXIT_CRITERIA["top20_hit_rate_min"]),
        ),
        _integer_max_gate(
            target_rows=target_rows,
            criterion_id="decoys_above_positive_count_max",
            field_name="decoys_above_positive_count",
            required=int(EXIT_CRITERIA["decoys_above_positive_count_max"]),
        ),
        _boolean_gate(
            target_rows=target_rows,
            criterion_id="no_positive_out_anchored_by_top_decoys",
            field_name="positive_out_anchored_by_top_decoys",
            required=bool(EXIT_CRITERIA["positive_out_anchored_by_top_decoys_allowed"]),
        ),
        _actual_hard_decoy_rows_gate(target_rows=target_rows),
    ]
    failed_criteria = [
        str(row["criterion_id"]) for row in criteria if not bool(row["pass"])
    ]
    return {
        "status": "ready" if broad_safe else "blocked",
        "claim": "broad_gpcr_hard_decoy_closure",
        "target_count": len(REQUIRED_TARGETS),
        "target_pass_count": target_pass_count,
        "first_blocked_target": first_blocked_target,
        "criteria": criteria,
        "failed_criterion_count": len(failed_criteria),
        "failed_criteria": failed_criteria,
    }


def materialize_gpcr_hard_decoy_suite_report(
    intake: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    intake_path: Path | None = None,
) -> dict[str, Any]:
    rows_by_target = _row_by_target(intake)
    target_rows = [
        _target_result(target_id, rows_by_target[target_id])
        if target_id in rows_by_target
        else _missing_target_row(target_id)
        for target_id in REQUIRED_TARGETS
    ]
    operator_input_source_receipt = _operator_input_source_receipt(
        intake,
        repo_root=repo_root,
    )
    if not operator_input_source_receipt["contract_pass"]:
        for row in target_rows:
            computed_metrics = _as_dict(row.get("computed_hard_decoy_metrics"))
            if computed_metrics.get("calculation_status") != "computed":
                continue
            computed_metrics["calculation_status"] = "computed_without_source_receipt"
            row["computed_hard_decoy_metrics"] = computed_metrics
            target_id = str(row.get("target_id") or "")
            row["blockers"].extend(
                f"{target_id}:{blocker}"
                for blocker in _as_list(operator_input_source_receipt.get("blockers"))
            )
            row["root_cause_tags"] = list(
                dict.fromkeys([*_as_list(row.get("root_cause_tags")), "operator_receipts_required"])
            )
            row["status"] = "blocked"
            row["contract_pass"] = False

    blockers = [blocker for row in target_rows for blocker in row["blockers"]]
    root_cause_tags = list(
        dict.fromkeys(tag for row in target_rows for tag in row["root_cause_tags"])
    )
    first_blocked_target = next(
        (row["target_id"] for row in target_rows if row["status"] != "pass"),
        "",
    )
    target_pass_count = sum(1 for row in target_rows if row["contract_pass"])
    broad_safe = bool(target_pass_count == len(REQUIRED_TARGETS) and not blockers)
    phase3_exit_gate = _phase3_exit_gate(
        target_rows=target_rows,
        target_pass_count=target_pass_count,
        broad_safe=broad_safe,
        first_blocked_target=first_blocked_target,
    )
    operator_gap_report = {
        "phase3_exit_gate": phase3_exit_gate,
        "target_rows": target_rows,
    }
    operator_evidence_gap_register = _operator_evidence_gap_register(operator_gap_report)
    first_operator_evidence_gap = (
        operator_evidence_gap_register[0] if operator_evidence_gap_register else {}
    )
    input_paths = [Path("scripts/materialize_gpcr_hard_decoy_suite_report.py")]
    if intake_path is not None:
        input_paths.append(intake_path)

    payload = {
        "schema_version": SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_suite_report_materialized_from_operator_metrics",
            repo_root=repo_root,
        ),
        "status": "ready" if broad_safe else "locked",
        "contract_pass": broad_safe,
        "broad_gpcr_family_claim_safe": broad_safe,
        "target_count": len(REQUIRED_TARGETS),
        "target_pass_count": target_pass_count,
        "first_blocked_target": first_blocked_target,
        "first_blocker": blockers[0] if blockers else "",
        "root_cause_tags": root_cause_tags,
        "exit_criteria": EXIT_CRITERIA,
        "operator_input_source_receipt": operator_input_source_receipt,
        "phase3_exit_gate": phase3_exit_gate,
        "target_rows": target_rows,
        "blockers": blockers,
        "operator_intake_route": GPCR_OPERATOR_INTAKE_ROUTE,
        "operator_intake_required_slot_count": len(REQUIRED_TARGETS),
        "operator_evidence_gap_count": len(operator_evidence_gap_register),
        "first_operator_evidence_gap": first_operator_evidence_gap,
        "operator_evidence_gap_register": operator_evidence_gap_register,
        "summary_line": (
            "GPCR hard-decoy suite: PASS"
            if broad_safe
            else (
                "GPCR hard-decoy suite: LOCKED | "
                f"first_blocked_target={first_blocked_target or 'none'} | "
                f"root_cause={','.join(root_cause_tags) or 'none'}"
            )
        ),
        "claim_boundary": (
            "This report evaluates operator-attached DRD2/HTR2A/OPRM1 hard-decoy "
            "metrics against the Phase 3 exit criteria. It does not infer target "
            "activity, generate docking results, or unlock broad GPCR claims without "
            "all required numeric receipts."
        ),
    }
    payload["operator_handoff_summary"] = _operator_handoff_summary(
        payload,
        operator_evidence_gap_register,
    )
    return payload


def build_gpcr_evidence_surface(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    contract_pass = bool(report.get("broad_gpcr_family_claim_safe"))
    status = "ready" if contract_pass else "locked"
    operator_evidence_gap_register = _operator_evidence_gap_register(report)
    first_operator_evidence_gap = (
        operator_evidence_gap_register[0] if operator_evidence_gap_register else {}
    )
    blockers = _as_list(report.get("blockers"))
    first_blocker = str(blockers[0]) if blockers else ""
    next_actions = (
        ["review_gpcr_hard_decoy_suite_report"]
        if contract_pass
        else [
            "fill_gpcr_hard_decoy_operator_intake_packet",
            "fill_drd2_htr2a_oprm1_operator_template_values",
            "run_gpcr_hard_decoy_suite_materializer",
            "refresh_gpcr_hard_decoy_product_report",
            "regenerate_product_capabilities_surface",
            "regenerate_goal_bottleneck_roadmap_surface",
        ]
    )
    operator_handoff_summary = _operator_handoff_summary(
        report,
        operator_evidence_gap_register,
    )
    input_paths = [
        Path("scripts/materialize_gpcr_hard_decoy_suite_report.py"),
    ]
    if report_path is not None:
        input_paths.append(report_path)
    return {
        "schema_version": SURFACE_SCHEMA_VERSION,
        **release_evidence_metadata(
            input_paths=input_paths,
            reused_evidence=False,
            reuse_policy="gpcr_hard_decoy_evidence_surface_from_suite_report",
            repo_root=repo_root,
        ),
        "surface_id": "gpcr_hard_decoy_evidence_surface",
        "science_surface_family": "gpcr",
        "surface_scope": "broad_gpcr_hard_decoy",
        "status": status,
        "reason_code": "PASS" if contract_pass else "ERR_BROAD_GPCR_CLAIM_LOCKED",
        "contract_pass": contract_pass,
        "locked": not contract_pass,
        "claim_locked": not contract_pass,
        "broad_gpcr_family_claim_safe": contract_pass,
        "target_families": list(REQUIRED_TARGETS),
        "exit_criteria": EXIT_CRITERIA,
        "phase3_exit_gate": _as_dict(report.get("phase3_exit_gate")),
        "operator_input_source_receipt": _as_dict(
            report.get("operator_input_source_receipt")
        ),
        "first_blocked_target": str(report.get("first_blocked_target") or ""),
        "first_blocker": first_blocker,
        "root_cause_tags": _as_list(report.get("root_cause_tags")),
        "suite_report": str(report_path) if report_path is not None else "",
        "blockers": blockers,
        "operator_intake_route": GPCR_OPERATOR_INTAKE_ROUTE,
        "operator_intake_required_slot_count": len(REQUIRED_TARGETS),
        "operator_evidence_gap_count": len(operator_evidence_gap_register),
        "first_operator_evidence_gap": first_operator_evidence_gap,
        "operator_evidence_gap_register": operator_evidence_gap_register,
        "operator_handoff_summary": operator_handoff_summary,
        "next_actions": next_actions,
        "summary_line": str(report.get("summary_line") or ""),
        "claim_boundary": (
            "This GPCR evidence surface mirrors the hard-decoy suite report for PM "
            "routing. Broad GPCR claims stay locked until every required target row "
            "passes the numeric exit criteria."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake", type=Path, required=True)
    parser.add_argument("--out-report", type=Path, required=True)
    parser.add_argument("--out-surface", type=Path)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    intake = json.loads(args.intake.read_text(encoding="utf-8"))
    report = materialize_gpcr_hard_decoy_suite_report(
        intake,
        repo_root=args.repo_root,
        intake_path=args.intake,
    )
    args.out_report.parent.mkdir(parents=True, exist_ok=True)
    args.out_report.write_text(_json_text(report), encoding="utf-8")
    if args.out_surface is not None:
        surface = build_gpcr_evidence_surface(
            report,
            report_path=args.out_report,
            repo_root=args.repo_root,
        )
        args.out_surface.parent.mkdir(parents=True, exist_ok=True)
        args.out_surface.write_text(_json_text(surface), encoding="utf-8")
    print(
        "gpcr-hard-decoy-suite: "
        f"{report['status']} | targets={report['target_pass_count']}/{report['target_count']} | "
        f"first_blocked={report['first_blocked_target'] or 'none'} | "
        f"blockers={len(report['blockers'])}"
    )
    return 1 if args.fail_blocked and not report["broad_gpcr_family_claim_safe"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
