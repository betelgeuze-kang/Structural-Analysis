#!/usr/bin/env python3
"""Export bounded design-optimization changes back to MIDAS MGT."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
import sys
from typing import Any

import numpy as np
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1.compare_midas_loadcomb_roundtrip import build_roundtrip_report  # noqa: E402
from implementation.phase1.generate_audit_review_followup_manifest import build_followup_manifest  # noqa: E402
from implementation.phase1.generate_audit_review_resolution_manifest import (  # noqa: E402
    build_resolution_manifest,
    write_resolution_files,
)
from implementation.phase1.load_combination_engine import export_midas_loadcomb_from_model_payload  # noqa: E402
from implementation.phase1.semantic_mgt_diff import SemanticMgtDiff  # noqa: E402


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(token: Any) -> int | None:
    try:
        if token is None:
            return None
        text = str(token).strip()
        if not text:
            return None
        return int(float(text))
    except Exception:
        return None


def _as_float(token: Any) -> float | None:
    try:
        if token is None:
            return None
        text = str(token).strip()
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _format_float(value: float) -> str:
    return f"{float(value):.12g}"


def _safe_ratio(numerator: int, denominator: int) -> float:
    if int(denominator) <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _normalize_mgt_diff_line(line: str) -> str:
    return re.sub(r"\s+", "", str(line or "").strip())


def _trim_mgt_diff_line(line: str, *, limit: int = 160) -> str:
    text = " ".join(str(line or "").strip().split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


_MGT_DIFF_ELEMENT_TYPES = {
    "BEAM",
    "COLUMN",
    "PLATE",
    "WALL",
    "TRUSS",
    "BRACE",
    "CABLE",
    "LINK",
    "SPRING",
}


def _dedupe_text_list(values: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(text)
    return ordered


def _normalize_mgt_diff_search_tokens(*values: Any) -> list[str]:
    tokens: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        tokens.append(lowered)
        tokens.extend(token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:+/-]*", text))
    return _dedupe_text_list(tokens)


def _extract_mgt_diff_line_candidates(line: str) -> dict[str, list[str]]:
    trimmed = _trim_mgt_diff_line(line)
    tokens = [token.strip() for token in trimmed.split(",") if token.strip()]
    if not tokens:
        return {
            "member_ids": [],
            "section_ids": [],
            "card_ids": [],
        }
    member_ids: list[str] = []
    section_ids: list[str] = []
    card_ids: list[str] = [tokens[0]]
    if len(tokens) >= 2:
        second = str(tokens[1]).strip().upper()
        if second in _MGT_DIFF_ELEMENT_TYPES:
            member_ids.append(tokens[0])
            if len(tokens) >= 3 and str(tokens[2]).strip():
                section_ids.append(str(tokens[2]).strip())
        elif second in {"DBUSER", "VALUE"}:
            section_ids.append(tokens[0])
    if not section_ids and tokens and str(tokens[0]).strip().isdigit():
        section_ids.append(tokens[0])
    return {
        "member_ids": _dedupe_text_list(member_ids),
        "section_ids": _dedupe_text_list(section_ids),
        "card_ids": _dedupe_text_list(card_ids),
    }


def _build_section_to_member_ids_map(parsed_model_payload: dict[str, Any]) -> dict[str, list[str]]:
    model_payload = parsed_model_payload.get("model") if isinstance(parsed_model_payload.get("model"), dict) else {}
    section_to_members: dict[str, list[str]] = {}
    for row in model_payload.get("elements") or []:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("id", "") or "").strip()
        if not member_id:
            continue
        section_id = str(row.get("section_id", "") or "").strip()
        if not section_id:
            continue
        section_to_members.setdefault(section_id, []).append(member_id)
    return {key: _dedupe_text_list(values) for key, values in section_to_members.items()}


def _build_member_row_index_map(rows: list[dict[str, Any]]) -> dict[str, list[int]]:
    index_map: dict[str, list[int]] = {}
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        member_tokens = _dedupe_text_list(
            [
                row.get("member_id", ""),
                *(row.get("candidate_member_ids") or []),
                *(row.get("geometry_bridge_member_ids") or []),
            ]
        )
        for member_id in member_tokens:
            index_map.setdefault(str(member_id), []).append(int(row_index))
    return {
        key: [int(value) for value in values]
        for key, values in sorted(index_map.items())
        if str(key).strip() and values
    }


def _diff_row_id(index: int) -> str:
    return f"mgt-diff-row-{int(index):04d}"


def _read_meaningful_mgt_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    meaningful_lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = str(raw_line or "").strip()
        if not stripped or stripped.startswith(";"):
            continue
        meaningful_lines.append(stripped)
    return meaningful_lines


def _build_mgt_diff_summary(
    *,
    source_mgt_path: Path,
    output_mgt_path: Path,
    parsed_model_payload: dict[str, Any] | None = None,
    sample_limit: int = 8,
    window_limit: int = 96,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "source_output_mgt_diff_available": False,
        "source_output_mgt_source_meaningful_line_count": 0,
        "source_output_mgt_output_meaningful_line_count": 0,
        "source_output_mgt_changed_line_count": 0,
        "source_output_mgt_added_line_count": 0,
        "source_output_mgt_removed_line_count": 0,
        "source_output_mgt_total_delta_count": 0,
        "source_output_mgt_diff_sample_lines": [],
        "source_output_mgt_diff_search_tokens": [],
        "source_output_mgt_diff_member_ids": [],
        "source_output_mgt_diff_section_ids": [],
        "source_output_mgt_diff_member_row_indices": {},
        "source_output_mgt_diff_row_ids": [],
        "source_output_mgt_diff_window_search_tokens": [],
        "source_output_mgt_diff_window_member_ids": [],
        "source_output_mgt_diff_window_section_ids": [],
        "source_output_mgt_diff_window_member_row_indices": {},
        "source_output_mgt_diff_window_row_ids": [],
        "source_output_mgt_summary_line": (
            "source_vs_output_mgt: unavailable | source_mgt=no | output_mgt=no"
        ),
        "source_vs_output_diff_changed_line_count": 0,
        "source_vs_output_diff_added_line_count": 0,
        "source_vs_output_diff_removed_line_count": 0,
        "source_vs_output_diff_sample_rows": [],
        "source_vs_output_diff_sample_count": 0,
        "source_vs_output_diff_window_rows": [],
        "source_vs_output_diff_window_count": 0,
        "source_vs_output_diff_summary_line": (
            "source_vs_output_mgt: unavailable | source_mgt=no | output_mgt=no"
        ),
        "source_vs_output_source_line_count": 0,
        "source_vs_output_output_line_count": 0,
    }
    source_exists = bool(source_mgt_path.exists())
    output_exists = bool(output_mgt_path.exists())
    if not source_exists or not output_exists:
        summary["source_output_mgt_summary_line"] = (
            "source_vs_output_mgt: unavailable"
            f" | source_mgt={'yes' if source_exists else 'no'}"
            f" | output_mgt={'yes' if output_exists else 'no'}"
        )
        summary["source_vs_output_diff_summary_line"] = str(summary["source_output_mgt_summary_line"])
        return summary

    source_lines = _read_meaningful_mgt_lines(source_mgt_path)
    output_lines = _read_meaningful_mgt_lines(output_mgt_path)
    source_norm = [_normalize_mgt_diff_line(line) for line in source_lines]
    output_norm = [_normalize_mgt_diff_line(line) for line in output_lines]
    matcher = difflib.SequenceMatcher(a=source_norm, b=output_norm, autojunk=False)
    sample_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    sample_lines: list[str] = []
    aggregate_search_tokens: list[str] = []
    aggregate_member_ids: list[str] = []
    aggregate_section_ids: list[str] = []
    aggregate_window_search_tokens: list[str] = []
    aggregate_window_member_ids: list[str] = []
    aggregate_window_section_ids: list[str] = []
    changed_line_count = 0
    added_line_count = 0
    removed_line_count = 0
    section_to_member_ids = _build_section_to_member_ids_map(parsed_model_payload or {})

    def add_sample_line(line: str) -> None:
        if len(sample_lines) >= sample_limit:
            return
        sample_lines.append(str(line))

    def add_sample_row(
        *,
        kind: str,
        source_index: int | None,
        output_index: int | None,
        source_line: str,
        output_line: str,
    ) -> None:
        source_trimmed = _trim_mgt_diff_line(source_line)
        output_trimmed = _trim_mgt_diff_line(output_line)
        source_candidates = _extract_mgt_diff_line_candidates(source_trimmed)
        output_candidates = _extract_mgt_diff_line_candidates(output_trimmed)
        raw_candidate_member_ids = _dedupe_text_list(
            source_candidates.get("member_ids", []) + output_candidates.get("member_ids", [])
        )
        candidate_section_ids = _dedupe_text_list(
            source_candidates.get("section_ids", []) + output_candidates.get("section_ids", [])
        )
        candidate_card_ids = _dedupe_text_list(
            source_candidates.get("card_ids", []) + output_candidates.get("card_ids", [])
        )
        mapped_member_ids = _dedupe_text_list(
            [
                member_id
                for section_id in candidate_section_ids
                for member_id in section_to_member_ids.get(str(section_id), [])
            ]
        )
        candidate_member_ids = _dedupe_text_list(raw_candidate_member_ids + mapped_member_ids)
        search_tokens = _normalize_mgt_diff_search_tokens(
            kind,
            source_trimmed,
            output_trimmed,
            *(candidate_member_ids + candidate_section_ids + candidate_card_ids),
        )
        row_payload = {
            "kind": str(kind),
            "source_line_number": None if source_index is None else int(source_index + 1),
            "output_line_number": None if output_index is None else int(output_index + 1),
            "source_line": source_trimmed,
            "output_line": output_trimmed,
            "candidate_member_ids": candidate_member_ids,
            "candidate_section_ids": candidate_section_ids,
            "candidate_card_ids": candidate_card_ids,
            "geometry_bridge_member_ids": mapped_member_ids,
            "exact_member_id_match": bool(mapped_member_ids),
            "search_tokens": search_tokens,
            "search_text": " ".join(search_tokens),
        }
        if len(window_rows) < window_limit:
            window_row_index = len(window_rows)
            window_rows.append(
                dict(
                    row_payload,
                    row_index=int(window_row_index),
                    row_id=_diff_row_id(window_row_index),
                )
            )
            aggregate_window_search_tokens.extend(search_tokens)
            aggregate_window_member_ids.extend(candidate_member_ids)
            aggregate_window_section_ids.extend(candidate_section_ids)
        if len(sample_rows) < sample_limit:
            sample_row_index = len(sample_rows)
            sample_rows.append(
                dict(
                    row_payload,
                    row_index=int(sample_row_index),
                    row_id=_diff_row_id(sample_row_index),
                )
            )
            aggregate_search_tokens.extend(search_tokens)
            aggregate_member_ids.extend(candidate_member_ids)
            aggregate_section_ids.extend(candidate_section_ids)

    def add_replace_pair(source_index: int, output_index: int) -> None:
        add_sample_row(
            kind="replace",
            source_index=source_index,
            output_index=output_index,
            source_line=source_lines[source_index],
            output_line=output_lines[output_index],
        )
        add_sample_line(
            f"~ {_trim_mgt_diff_line(source_lines[source_index])}"
            f" -> {_trim_mgt_diff_line(output_lines[output_index])}"
        )

    def add_delete_line(source_index: int) -> None:
        add_sample_row(
            kind="delete",
            source_index=source_index,
            output_index=None,
            source_line=source_lines[source_index],
            output_line="",
        )
        add_sample_line(f"- {_trim_mgt_diff_line(source_lines[source_index])}")

    def add_insert_line(output_index: int) -> None:
        add_sample_row(
            kind="insert",
            source_index=None,
            output_index=output_index,
            source_line="",
            output_line=output_lines[output_index],
        )
        add_sample_line(f"+ {_trim_mgt_diff_line(output_lines[output_index])}")

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        source_span = max(i2 - i1, 0)
        output_span = max(j2 - j1, 0)
        if tag == "replace":
            pair_count = min(source_span, output_span)
            changed_line_count += pair_count
            removed_line_count += max(source_span - pair_count, 0)
            added_line_count += max(output_span - pair_count, 0)
            for offset in range(pair_count):
                add_replace_pair(i1 + offset, j1 + offset)
            for offset in range(pair_count, source_span):
                add_delete_line(i1 + offset)
            for offset in range(pair_count, output_span):
                add_insert_line(j1 + offset)
        elif tag == "delete":
            removed_line_count += source_span
            for offset in range(source_span):
                add_delete_line(i1 + offset)
        elif tag == "insert":
            added_line_count += output_span
            for offset in range(output_span):
                add_insert_line(j1 + offset)

    total_delta_count = int(changed_line_count + added_line_count + removed_line_count)
    summary_line = (
        f"source_vs_output_mgt: changed={changed_line_count} | "
        f"added={added_line_count} | removed={removed_line_count} | "
        f"source_lines={len(source_lines)} | output_lines={len(output_lines)}"
    )

    summary.update(
        {
            "source_output_mgt_diff_available": True,
            "source_output_mgt_source_meaningful_line_count": int(len(source_lines)),
            "source_output_mgt_output_meaningful_line_count": int(len(output_lines)),
            "source_output_mgt_changed_line_count": int(changed_line_count),
            "source_output_mgt_added_line_count": int(added_line_count),
            "source_output_mgt_removed_line_count": int(removed_line_count),
            "source_output_mgt_total_delta_count": total_delta_count,
            "source_output_mgt_diff_sample_lines": sample_lines,
            "source_output_mgt_diff_search_tokens": _dedupe_text_list(aggregate_search_tokens),
            "source_output_mgt_diff_member_ids": _dedupe_text_list(aggregate_member_ids),
            "source_output_mgt_diff_section_ids": _dedupe_text_list(aggregate_section_ids),
            "source_output_mgt_diff_member_row_indices": _build_member_row_index_map(sample_rows),
            "source_output_mgt_diff_row_ids": [
                str(row.get("row_id", "") or "")
                for row in sample_rows
                if str(row.get("row_id", "") or "").strip()
            ],
            "source_output_mgt_diff_window_search_tokens": _dedupe_text_list(aggregate_window_search_tokens),
            "source_output_mgt_diff_window_member_ids": _dedupe_text_list(aggregate_window_member_ids),
            "source_output_mgt_diff_window_section_ids": _dedupe_text_list(aggregate_window_section_ids),
            "source_output_mgt_diff_window_member_row_indices": _build_member_row_index_map(window_rows),
            "source_output_mgt_diff_window_row_ids": [
                str(row.get("row_id", "") or "")
                for row in window_rows
                if str(row.get("row_id", "") or "").strip()
            ],
            "source_output_mgt_summary_line": summary_line,
            "source_vs_output_diff_changed_line_count": int(changed_line_count),
            "source_vs_output_diff_added_line_count": int(added_line_count),
            "source_vs_output_diff_removed_line_count": int(removed_line_count),
            "source_vs_output_diff_sample_rows": sample_rows,
            "source_vs_output_diff_sample_count": int(len(sample_rows)),
            "source_vs_output_diff_window_rows": window_rows,
            "source_vs_output_diff_window_count": int(len(window_rows)),
            "source_vs_output_diff_summary_line": summary_line,
            "source_vs_output_source_line_count": int(len(source_lines)),
            "source_vs_output_output_line_count": int(len(output_lines)),
        }
    )
    return summary


def _format_delivery_boundary(
    *,
    direct_patch_action_family_counts: dict[str, int],
    instruction_sidecar_action_family_counts: dict[str, int],
    connection_detailing_delivery_mode: str,
    detailing_delivery_mode: str,
) -> str:
    def _format_counts(counts: dict[str, int]) -> str:
        parts = [f"{str(key)}={int(value)}" for key, value in sorted(counts.items()) if int(value) > 0]
        return ", ".join(parts) if parts else "none"

    return " | ".join(
        [
            f"direct_patch={_format_counts(direct_patch_action_family_counts)}",
            f"sidecar={_format_counts(instruction_sidecar_action_family_counts)}",
            f"connection_payload={str(connection_detailing_delivery_mode)}",
            f"detailing_payload={str(detailing_delivery_mode)}",
        ]
    )


def _is_instruction_sidecar_audit_only(row: dict[str, Any]) -> bool:
    if _is_instruction_sidecar_zero_touch_verified(row):
        return False
    followup_type = str(row.get("followup_type", "") or "").strip()
    if not bool(row.get("direct_patch_applied", False)):
        return False
    return "manual" not in followup_type


def _is_instruction_sidecar_manual_input(row: dict[str, Any]) -> bool:
    return not _is_instruction_sidecar_audit_only(row) and not _is_instruction_sidecar_zero_touch_verified(row)


def _is_instruction_sidecar_zero_touch_verified(row: dict[str, Any]) -> bool:
    if bool(row.get("zero_touch_verified", False)):
        return True
    family = str(row.get("action_family", "") or "").strip()
    followup_type = str(row.get("followup_type", "") or "").strip()
    direct_patch_kind = str(row.get("direct_patch_kind", "") or "").strip()
    if family not in {"connection_detailing", "detailing"}:
        return False
    if "zero_touch_verified" not in followup_type and not followup_type.endswith("_audit_after_material_patch"):
        return False
    if not bool(row.get("direct_patch_applied", False)):
        return False
    if not bool(row.get("structured_payload_present", False)):
        return False
    if not direct_patch_kind.endswith("material_metadata"):
        return False
    target_material_ids = row.get("direct_patch_target_material_ids")
    if not isinstance(target_material_ids, list) or not target_material_ids:
        return False
    structured_payload = row.get("structured_payload") if isinstance(row.get("structured_payload"), dict) else {}
    validation_boundary = str(structured_payload.get("validation_boundary", "") or "").strip()
    if validation_boundary and validation_boundary != "internal_engine_complete_external_validation_optional":
        return False
    return True


def _resolve_input_path(token: str | Path) -> Path:
    path = Path(token)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    repo_path = REPO_ROOT / path
    return repo_path.resolve() if repo_path.exists() else repo_path


def _default_rebar_payload_projection_path(source_mgt_path: Path) -> Path:
    return source_mgt_path.with_suffix(".rebar_payload_projection.json")


def _default_connection_detailing_payload_projection_path(source_mgt_path: Path) -> Path:
    return source_mgt_path.with_suffix(".connection_detailing_payload_projection.json")


def _default_detailing_payload_projection_path(source_mgt_path: Path) -> Path:
    return source_mgt_path.with_suffix(".detailing_payload_projection.json")


def _default_audit_review_manifest_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_manifest.json")


def _default_audit_review_packet_manifest_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_packets.json")


def _default_audit_review_packet_dir_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_packet_files")


def _default_audit_review_queue_manifest_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_queue.json")


def _default_audit_review_queue_status_dir_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_queue_status_files")


def _default_audit_review_followup_manifest_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_followup_manifest.json")


def _default_audit_review_resolution_manifest_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_resolution_manifest.json")


def _default_audit_review_resolution_dir_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".audit_review_resolution_files")


def _default_loadcomb_preview_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".loadcomb_preview.mgt")


def _default_loadcomb_roundtrip_report_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".loadcomb_roundtrip_report.json")


def _default_source_output_mgt_diff_json_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".source_output_diff.json")


def _default_source_output_mgt_diff_preview_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".source_output_diff.txt")


def _default_source_output_mgt_diff_window_json_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".source_output_diff_window.json")


def _default_source_output_mgt_diff_window_preview_path(output_mgt_path: Path) -> Path:
    return output_mgt_path.with_suffix(".source_output_diff_window.txt")


def _write_source_output_mgt_diff_artifacts(
    *,
    source_mgt_path: Path,
    output_mgt_path: Path,
    diff_summary: dict[str, Any],
    diff_json_out_path: Path,
    diff_preview_out_path: Path,
    diff_window_json_out_path: Path,
    diff_window_preview_out_path: Path,
) -> tuple[bool, bool, bool, bool]:
    diff_json_payload = {
        "schema_version": "1.0",
        "source_mgt": str(source_mgt_path),
        "output_mgt": str(output_mgt_path),
        "summary_line": str(diff_summary.get("source_output_mgt_summary_line", "") or ""),
        "meaningful_line_counts": {
            "source": int(diff_summary.get("source_output_mgt_source_meaningful_line_count", 0) or 0),
            "output": int(diff_summary.get("source_output_mgt_output_meaningful_line_count", 0) or 0),
        },
        "delta_counts": {
            "changed": int(diff_summary.get("source_output_mgt_changed_line_count", 0) or 0),
            "added": int(diff_summary.get("source_output_mgt_added_line_count", 0) or 0),
            "removed": int(diff_summary.get("source_output_mgt_removed_line_count", 0) or 0),
            "total": int(diff_summary.get("source_output_mgt_total_delta_count", 0) or 0),
        },
        "search_tokens": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_search_tokens") or [])
            if str(token).strip()
        ],
        "candidate_member_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_member_ids") or [])
            if str(token).strip()
        ],
        "candidate_section_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_section_ids") or [])
            if str(token).strip()
        ],
        "member_row_indices": {
            str(key): [int(value) for value in values]
            for key, values in (diff_summary.get("source_output_mgt_diff_member_row_indices") or {}).items()
            if str(key).strip()
        },
        "row_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_row_ids") or [])
            if str(token).strip()
        ],
        "sample_lines": [str(line) for line in (diff_summary.get("source_output_mgt_diff_sample_lines") or [])],
        "sample_rows": [row for row in (diff_summary.get("source_vs_output_diff_sample_rows") or []) if isinstance(row, dict)],
    }
    _write_json(diff_json_out_path, diff_json_payload)
    diff_window_json_payload = {
        "schema_version": "1.0",
        "source_mgt": str(source_mgt_path),
        "output_mgt": str(output_mgt_path),
        "summary_line": str(diff_summary.get("source_output_mgt_summary_line", "") or ""),
        "window_count": int(diff_summary.get("source_vs_output_diff_window_count", 0) or 0),
        "search_tokens": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_window_search_tokens") or [])
            if str(token).strip()
        ],
        "candidate_member_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_window_member_ids") or [])
            if str(token).strip()
        ],
        "candidate_section_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_window_section_ids") or [])
            if str(token).strip()
        ],
        "member_row_indices": {
            str(key): [int(value) for value in values]
            for key, values in (diff_summary.get("source_output_mgt_diff_window_member_row_indices") or {}).items()
            if str(key).strip()
        },
        "row_ids": [
            str(token)
            for token in (diff_summary.get("source_output_mgt_diff_window_row_ids") or [])
            if str(token).strip()
        ],
        "window_rows": [row for row in (diff_summary.get("source_vs_output_diff_window_rows") or []) if isinstance(row, dict)],
    }
    _write_json(diff_window_json_out_path, diff_window_json_payload)

    try:
        mgt_old = source_mgt_path.read_text(encoding="utf-8", errors="ignore") if source_mgt_path.exists() else ""
        mgt_new = output_mgt_path.read_text(encoding="utf-8", errors="ignore") if output_mgt_path.exists() else ""
        semantic_differ = SemanticMgtDiff(mgt_old, mgt_new)
        diff_text = semantic_differ.generate_diff_text()
        preview_lines = [
            "MIDAS source vs output diff preview (Semantic)",
            f"source_mgt={source_mgt_path}",
            f"output_mgt={output_mgt_path}",
            "",
            diff_text
        ]
    except Exception:
        preview_lines = [
            "MIDAS source vs output diff preview (Semantic Failed Fallback)",
            f"source_mgt={source_mgt_path}",
            f"output_mgt={output_mgt_path}",
            str(diff_summary.get("source_output_mgt_summary_line", "") or ""),
            "",
            "Sample delta lines:",
        ]
        sample_lines = [str(line) for line in (diff_summary.get("source_output_mgt_diff_sample_lines") or [])]
        preview_lines.extend(sample_lines or ["(none)"])

    diff_preview_out_path.parent.mkdir(parents=True, exist_ok=True)
    diff_preview_out_path.write_text("\n".join(preview_lines) + "\n", encoding="utf-8")

    window_preview_lines = [
        "MIDAS source vs output diff compare window",
        f"source_mgt={source_mgt_path}",
        f"output_mgt={output_mgt_path}",
        str(diff_summary.get("source_output_mgt_summary_line", "") or ""),
        f"window_count={int(diff_summary.get('source_vs_output_diff_window_count', 0) or 0)}",
        "",
        "Window delta rows:",
    ]
    for row in diff_window_json_payload["window_rows"]:
        kind = str(row.get("kind", "") or "replace")
        source_line_number = str(row.get("source_line_number", "") or "-")
        output_line_number = str(row.get("output_line_number", "") or "-")
        member_ids = ",".join(str(value) for value in (row.get("candidate_member_ids") or []) if str(value).strip()) or "-"
        window_preview_lines.append(
            f"{kind.upper()} | S:{source_line_number} | O:{output_line_number} | members={member_ids}"
        )
        if str(row.get("source_line", "") or "").strip():
            window_preview_lines.append(f"  src={str(row.get('source_line', '') or '')}")
        if str(row.get("output_line", "") or "").strip():
            window_preview_lines.append(f"  out={str(row.get('output_line', '') or '')}")
    if not diff_window_json_payload["window_rows"]:
        window_preview_lines.append("(none)")
    diff_window_preview_out_path.parent.mkdir(parents=True, exist_ok=True)
    diff_window_preview_out_path.write_text("\n".join(window_preview_lines) + "\n", encoding="utf-8")
    return (
        diff_json_out_path.exists(),
        diff_preview_out_path.exists(),
        diff_window_json_out_path.exists(),
        diff_window_preview_out_path.exists(),
    )


def _slugify_packet_component(token: Any) -> str:
    text = str(token or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "packet"


def _build_audit_review_packets(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    packet_map: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        action_family = str(row.get("action_family", "") or "").strip()
        followup_type = str(row.get("followup_type", "") or "").strip()
        review_priority = str(row.get("review_priority", "") or "").strip()
        packet_map[(action_family, followup_type, review_priority)].append(dict(row))

    packets: list[dict[str, Any]] = []
    for action_family, followup_type, review_priority in sorted(packet_map.keys()):
        bucket = packet_map[(action_family, followup_type, review_priority)]
        direct_patch_kind_counts = {
            str(k): int(v)
            for k, v in sorted(Counter(str(row.get("direct_patch_kind", "") or "") for row in bucket).items())
            if str(k)
        }
        member_type_counts = {
            str(k): int(v)
            for k, v in sorted(Counter(str(row.get("member_type", "") or "") for row in bucket).items())
            if str(k)
        }
        group_ids = sorted({str(row.get("group_id", "") or "") for row in bucket if str(row.get("group_id", "") or "").strip()})
        packets.append(
            {
                "packet_id": "|".join([action_family or "unknown", followup_type or "unknown", review_priority or "unknown"]),
                "action_family": action_family,
                "followup_type": followup_type,
                "review_priority": review_priority,
                "change_count": int(len(bucket)),
                "direct_patch_kind_counts": direct_patch_kind_counts,
                "member_type_counts": member_type_counts,
                "group_id_count": int(len(group_ids)),
                "group_ids_head": group_ids[:10],
            }
        )
    return packets


def _write_audit_review_packet_files(
    packet_dir_path: Path,
    packets: list[dict[str, Any]],
    audit_review_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if packet_dir_path.exists():
        for existing in packet_dir_path.glob("*.audit_packet.json"):
            existing.unlink()
    packet_dir_path.mkdir(parents=True, exist_ok=True)
    packet_row_map: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in audit_review_rows:
        key = (
            str(row.get("action_family", "") or "").strip(),
            str(row.get("followup_type", "") or "").strip(),
            str(row.get("review_priority", "") or "").strip(),
        )
        packet_row_map[key].append(dict(row))

    packet_files: list[dict[str, Any]] = []
    for index, packet in enumerate(packets, start=1):
        action_family = str(packet.get("action_family", "") or "").strip()
        followup_type = str(packet.get("followup_type", "") or "").strip()
        review_priority = str(packet.get("review_priority", "") or "").strip()
        key = (action_family, followup_type, review_priority)
        packet_rows = list(packet_row_map.get(key, []))
        file_name = (
            f"{index:02d}."
            f"{_slugify_packet_component(action_family)}."
            f"{_slugify_packet_component(followup_type)}."
            f"{_slugify_packet_component(review_priority)}.audit_packet.json"
        )
        packet_path = packet_dir_path / file_name
        _write_json(
            packet_path,
            {
                "schema_version": "1.0",
                "packet": dict(packet),
                "audit_review_rows": packet_rows,
                "summary": {
                    "packet_id": str(packet.get("packet_id", "")),
                    "action_family": action_family,
                    "followup_type": followup_type,
                    "review_priority": review_priority,
                    "change_count": int(packet.get("change_count", len(packet_rows)) or len(packet_rows)),
                    "row_count": int(len(packet_rows)),
                    "group_id_count": int(packet.get("group_id_count", 0) or 0),
                },
            },
        )
        packet_files.append(
            {
                "packet_id": str(packet.get("packet_id", "")),
                "action_family": action_family,
                "followup_type": followup_type,
                "review_priority": review_priority,
                "path": str(packet_path),
                "change_count": int(packet.get("change_count", len(packet_rows)) or len(packet_rows)),
                "row_count": int(len(packet_rows)),
            }
        )
    return packet_files


def _write_audit_review_queue_status_files(
    queue_status_dir_path: Path,
    packet_files: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if queue_status_dir_path.exists():
        for existing in queue_status_dir_path.glob("*.review_status.json"):
            existing.unlink()
    queue_status_dir_path.mkdir(parents=True, exist_ok=True)

    queue_items: list[dict[str, Any]] = []
    for index, packet_file in enumerate(packet_files, start=1):
        created_at_utc = _now_utc()
        action_family = str(packet_file.get("action_family", "") or "").strip()
        followup_type = str(packet_file.get("followup_type", "") or "").strip()
        review_priority = str(packet_file.get("review_priority", "") or "").strip()
        packet_id = str(packet_file.get("packet_id", "") or "").strip()
        file_name = (
            f"{index:02d}."
            f"{_slugify_packet_component(action_family)}."
            f"{_slugify_packet_component(followup_type)}."
            f"{_slugify_packet_component(review_priority)}.review_status.json"
        )
        status_path = queue_status_dir_path / file_name
        payload = {
            "schema_version": "1.0",
            "packet_id": packet_id,
            "action_family": action_family,
            "followup_type": followup_type,
            "review_priority": review_priority,
            "review_owner": "licensed_engineer",
            "queue_status": "pending_review",
            "acknowledged": False,
            "resolution": "",
            "created_at_utc": created_at_utc,
            "last_transition_at_utc": created_at_utc,
            "status_history": [
                {
                    "transitioned_at_utc": created_at_utc,
                    "from_status": "",
                    "to_status": "pending_review",
                    "note": "queue generated from audit review packets",
                }
            ],
            "change_count": int(packet_file.get("change_count", 0) or 0),
            "row_count": int(packet_file.get("row_count", 0) or 0),
            "packet_file_path": str(packet_file.get("path", "") or ""),
        }
        _write_json(status_path, payload)
        queue_items.append(
            {
                "packet_id": packet_id,
                "action_family": action_family,
                "followup_type": followup_type,
                "review_priority": review_priority,
                "review_owner": "licensed_engineer",
                "queue_status": "pending_review",
                "acknowledged": False,
                "resolution": "",
                "created_at_utc": created_at_utc,
                "last_transition_at_utc": created_at_utc,
                "path": str(status_path),
                "packet_file_path": str(packet_file.get("path", "") or ""),
                "change_count": int(packet_file.get("change_count", 0) or 0),
                "row_count": int(packet_file.get("row_count", 0) or 0),
            }
        )
    return queue_items


def _load_rebar_payload_projection(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_connection_detailing_payload_projection(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _load_detailing_payload_projection(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = _load_json(path)
    return payload if isinstance(payload, dict) else {}


def _infer_fy_from_text(token: Any) -> float | None:
    text = str(token or "").strip().upper()
    if not text:
        return None
    numeric = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    if numeric:
        try:
            value = float(numeric)
            if value > 0.0:
                return value
        except Exception:
            pass
    return None


def _load_material_payload_rows_with_fallback(
    model_json_path: Path,
    *,
    rebar_payload_projection_path: Path | None = None,
) -> list[dict[str, Any]]:
    model = _load_json(model_json_path)
    model_body = model.get("model", {}) if isinstance(model.get("model"), dict) else {}
    metadata = model_body.get("metadata", {}) if isinstance(model_body, dict) else {}
    material_payload_rows = metadata.get("design_material_rebar_payloads", []) if isinstance(metadata, dict) else []
    rebar_material_codes = metadata.get("rebar_material_codes", []) if isinstance(metadata, dict) else []
    projection = _load_rebar_payload_projection(rebar_payload_projection_path)
    projection_rows = projection.get("design_material_rebar_payloads", []) if isinstance(projection, dict) else []

    out: dict[int, dict[str, Any]] = {}
    for row in material_payload_rows if isinstance(material_payload_rows, list) else []:
        if not isinstance(row, dict):
            continue
        material_id = _as_int(row.get("material_id"))
        if material_id is None:
            continue
        out[int(material_id)] = dict(row)

    default_code = ""
    default_grade = ""
    default_fy = None
    if isinstance(rebar_material_codes, list) and rebar_material_codes:
        first = rebar_material_codes[0]
        if isinstance(first, dict):
            tokens = first.get("tokens") if isinstance(first.get("tokens"), list) else []
            if len(tokens) >= 2:
                default_code = str(tokens[0]).strip()
                default_grade = str(tokens[1]).strip()
                default_fy = _infer_fy_from_text(tokens[1])
    materials = model_body.get("materials", []) if isinstance(model_body, dict) else []
    for row in materials if isinstance(materials, list) else []:
        if not isinstance(row, dict):
            continue
        material_id = _as_int(row.get("id"))
        material_type = str(row.get("name", "") or "").strip().upper()
        material_name = ""
        raw_tokens = row.get("raw_tokens") if isinstance(row.get("raw_tokens"), list) else []
        if raw_tokens:
            material_name = str(raw_tokens[0]).strip()
        if material_id is None or material_type != "CONC":
            continue
        existing = dict(out.get(int(material_id), {}))
        if bool(existing.get("payload_present", False)):
            continue
        if not default_code and not default_grade and default_fy is None:
            continue
        out[int(material_id)] = {
            "material_id": int(material_id),
            "material_type": "CONC",
            "material_name": material_name or str(existing.get("material_name", "") or ""),
            "payload_basis": "global_rebar_material_code_fallback",
            "payload_present": True,
            "rbcode": default_code,
            "rbmain": default_grade,
            "rbsub": default_grade,
            "fy_r": float(default_fy) if default_fy is not None else None,
            "fys": float(default_fy) if default_fy is not None else None,
        }

    for row in projection_rows if isinstance(projection_rows, list) else []:
        if not isinstance(row, dict):
            continue
        material_id = _as_int(row.get("material_id"))
        if material_id is None:
            continue
        out[int(material_id)] = dict(row)
    return [out[k] for k in sorted(out)]


def _load_group_local_payload_rows(
    model_json_path: Path,
    *,
    rebar_payload_projection_path: Path | None = None,
) -> list[dict[str, Any]]:
    model = _load_json(model_json_path)
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    group_local_payloads = metadata.get("group_local_rebar_payloads", []) if isinstance(metadata, dict) else []
    projection = _load_rebar_payload_projection(rebar_payload_projection_path)
    projection_rows = projection.get("group_local_rebar_payloads", []) if isinstance(projection, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads if isinstance(group_local_payloads, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    for row in projection_rows if isinstance(projection_rows, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return [out[k] for k in sorted(out)]


def _load_group_local_connection_detailing_payload_rows(
    model_json_path: Path,
    *,
    connection_detailing_payload_projection_path: Path | None = None,
) -> list[dict[str, Any]]:
    model = _load_json(model_json_path)
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    group_local_payloads = metadata.get("group_local_connection_detailing_payloads", []) if isinstance(metadata, dict) else []
    projection = _load_connection_detailing_payload_projection(connection_detailing_payload_projection_path)
    projection_rows = projection.get("group_local_connection_detailing_payloads", []) if isinstance(projection, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads if isinstance(group_local_payloads, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    for row in projection_rows if isinstance(projection_rows, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return [out[k] for k in sorted(out)]


def _load_group_local_detailing_payload_rows(
    model_json_path: Path,
    *,
    detailing_payload_projection_path: Path | None = None,
) -> list[dict[str, Any]]:
    model = _load_json(model_json_path)
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    group_local_payloads = metadata.get("group_local_detailing_payloads", []) if isinstance(metadata, dict) else []
    projection = _load_detailing_payload_projection(detailing_payload_projection_path)
    projection_rows = projection.get("group_local_detailing_payloads", []) if isinstance(projection, dict) else []
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads if isinstance(group_local_payloads, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    for row in projection_rows if isinstance(projection_rows, list) else []:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return [out[k] for k in sorted(out)]


def _infer_action_family(row: dict[str, Any]) -> str:
    family = str(row.get("action_family", "") or "").strip()
    if family:
        return family
    member_type = str(row.get("member_type", "") or "").strip().lower()
    before_thickness = _as_float(row.get("before_thickness_scale"))
    after_thickness = _as_float(row.get("after_thickness_scale"))
    before_rebar = _as_float(row.get("before_rebar_ratio"))
    after_rebar = _as_float(row.get("after_rebar_ratio"))
    before_detailing = _as_float(row.get("before_detailing_quality"))
    after_detailing = _as_float(row.get("after_detailing_quality"))
    if before_thickness is not None and after_thickness is not None and abs(after_thickness - before_thickness) > 1.0e-12:
        if member_type == "wall":
            return "wall_thickness"
        if member_type == "slab":
            return "slab_thickness"
        if member_type == "beam":
            return "beam_section"
        return "thickness"
    if before_rebar is not None and after_rebar is not None and abs(after_rebar - before_rebar) > 1.0e-12:
        return "rebar"
    if before_detailing is not None and after_detailing is not None and abs(after_detailing - before_detailing) > 1.0e-12:
        return "detailing"
    return ""


def _row_group_tokens(row: dict[str, Any]) -> list[str]:
    group_id = str(row.get("group_id", "") or "").strip()
    return [token.strip().lower() for token in group_id.split(":")] if group_id else []


def _row_zone_label(row: dict[str, Any]) -> str:
    zone_label = str(row.get("zone_label", "") or "").strip().lower()
    if zone_label:
        return zone_label
    tokens = _row_group_tokens(row)
    return tokens[1] if len(tokens) >= 2 else ""


def _row_member_type(row: dict[str, Any]) -> str:
    member_type = str(row.get("member_type", "") or "").strip().lower()
    if member_type:
        return member_type
    tokens = _row_group_tokens(row)
    return tokens[3] if len(tokens) >= 4 else ""


def _infer_special_member_family(row: dict[str, Any]) -> str:
    family = _infer_action_family(row)
    if not family:
        return ""
    member_type = _row_member_type(row) or "member"
    zone_label = _row_zone_label(row)
    zone_prefix = f"{zone_label}_" if zone_label else ""
    if family == "perimeter_frame":
        return f"perimeter_frame_{member_type}"
    if family == "beam_section" and member_type == "beam":
        return f"{zone_prefix}beam_section"
    if family == "wall_thickness" and member_type == "wall":
        return f"{zone_prefix}wall_thickness"
    if family == "slab_thickness" and member_type == "slab":
        return f"{zone_prefix}slab_thickness"
    if family == "connection_detailing":
        return f"{zone_prefix}{member_type}_connection_detailing"
    if family == "detailing":
        return f"{zone_prefix}{member_type}_detailing"
    if family == "rebar":
        return f"{zone_prefix}{member_type}_rebar"
    return f"{zone_prefix}{member_type}_{family}"


def _annotate_special_member_family(row: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(row)
    special_member_family = _infer_special_member_family(annotated)
    if special_member_family:
        annotated["special_member_family"] = str(special_member_family)
    return annotated


def _load_group_element_map(dataset_npz_path: Path) -> dict[str, list[int]]:
    npz = np.load(dataset_npz_path, allow_pickle=False)
    member_ids = np.asarray(npz["member_ids"], dtype="<U128")
    group_ids = np.asarray(npz["group_ids"], dtype="<U128")
    out: dict[str, list[int]] = defaultdict(list)
    for member_id, group_id in zip(member_ids.tolist(), group_ids.tolist()):
        eid = _as_int(member_id)
        if eid is None:
            continue
        out[str(group_id)].append(int(eid))
    return {str(k): sorted(set(v)) for k, v in out.items()}


def _resolve_model_elements(payload: dict[str, Any]) -> list[dict[str, Any]]:
    model = payload.get("model")
    if isinstance(model, dict) and isinstance(model.get("elements"), list):
        return [row for row in model.get("elements", []) if isinstance(row, dict)]
    if isinstance(payload.get("elements"), list):
        return [row for row in payload.get("elements", []) if isinstance(row, dict)]
    return []


def _build_viewer_section_lookup(model_payload: dict[str, Any]) -> dict[str, int]:
    lookup: dict[str, int] = {}

    def _register(value: Any, section_id: int | None) -> None:
        if section_id is None:
            return
        text = str(value or "").strip()
        if not text:
            return
        lookup.setdefault(text.lower(), int(section_id))

    model = model_payload.get("model")
    if isinstance(model, dict):
        sections = model.get("sections")
        if isinstance(sections, list):
            for row in sections:
                if not isinstance(row, dict):
                    continue
                section_id = _as_int(row.get("id") or row.get("section_id"))
                for field in ("id", "section_id", "name", "section_name", "signature", "label", "summary"):
                    _register(row.get(field), section_id)
    sections = model_payload.get("sections")
    if isinstance(sections, list):
        for row in sections:
            if not isinstance(row, dict):
                continue
            section_id = _as_int(row.get("id") or row.get("section_id"))
            for field in ("id", "section_id", "name", "section_name", "signature", "label", "summary"):
                _register(row.get(field), section_id)

    metadata = model.get("metadata", {}) if isinstance(model, dict) else {}
    design_sections = metadata.get("design_sections", []) if isinstance(metadata, dict) else []
    for row in design_sections:
        if not isinstance(row, dict):
            continue
        section_id = _as_int(row.get("section_id"))
        _register(row.get("section_id"), section_id)
        row_tokens = row.get("row_tokens") if isinstance(row.get("row_tokens"), list) else []
        first = row_tokens[0] if row_tokens and isinstance(row_tokens[0], list) else []
        for token in first:
            _register(token, section_id)
        if len(first) >= 3:
            _register(first[2], section_id)
        if len(first) >= 2:
            _register(first[1], section_id)
    return lookup


def _resolve_viewer_section_override_target_id(
    entry: dict[str, Any],
    section_lookup: dict[str, int],
) -> tuple[int | None, str]:
    direct_target_id = _as_int(entry.get("target_section_id"))
    if direct_target_id is not None:
        return int(direct_target_id), "target_section_id"
    for field in (
        "target_section",
        "target_section_input",
        "target_section_name",
        "target_section_catalog_label",
    ):
        text = str(entry.get(field, "") or "").strip()
        if not text:
            continue
        resolved = section_lookup.get(text.lower())
        if resolved is not None:
            return int(resolved), field
    return None, ""


def _resolve_model_loads_container(model_payload: dict[str, Any]) -> dict[str, Any]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        raise TypeError("model payload must be a mapping")
    loads = model.get("loads")
    if not isinstance(loads, dict):
        loads = {}
        model["loads"] = loads
    return loads


def _resolve_model_metadata_container(model_payload: dict[str, Any]) -> dict[str, Any]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        raise TypeError("model payload must be a mapping")
    metadata = model.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        model["metadata"] = metadata
    return metadata


def _dedupe_nonempty_text(values: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        ordered.append(text)
    return ordered


def _build_loadcomb_lookup(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if not name:
            continue
        lookup.setdefault(name.lower(), row)
    return lookup


def _normalize_loadcomb_entry_rows(combo_row: dict[str, Any]) -> list[dict[str, Any]]:
    rows = combo_row.get("entry_rows") if isinstance(combo_row.get("entry_rows"), list) else []
    if not rows:
        rows = combo_row.get("entries") if isinstance(combo_row.get("entries"), list) else []
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        reference_kind = str(row.get("reference_kind", "") or "").strip().upper()
        reference_name = str(row.get("reference_name", "") or "").strip()
        if reference_kind not in {"ST", "CB"} or not reference_name:
            continue
        normalized_rows.append(
            {
                "reference_kind": reference_kind,
                "reference_name": reference_name,
                "factor": float(row.get("factor", 0.0) or 0.0),
            }
        )
    if normalized_rows:
        return normalized_rows
    factor_map = combo_row.get("factor_map") if isinstance(combo_row.get("factor_map"), dict) else {}
    return [
        {
            "reference_kind": "ST",
            "reference_name": str(case_name).strip(),
            "factor": float(factor),
        }
        for case_name, factor in sorted(factor_map.items())
        if str(case_name).strip()
    ]


def _scale_loadcomb_factor_map(factor_map: dict[str, Any], *, scale: float) -> dict[str, float]:
    return {
        str(key): float(value) * float(scale)
        for key, value in factor_map.items()
        if str(key).strip()
    }


def _build_loadcomb_expression(entry_rows: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for row in entry_rows:
        reference_name = str(row.get("reference_name", "") or "").strip()
        if not reference_name:
            continue
        factor = float(row.get("factor", 0.0) or 0.0)
        if abs(factor) <= 1.0e-12:
            continue
        token = f"{_format_float(factor)}({reference_name})"
        if parts and factor >= 0:
            parts.append(f"+ {token}")
        else:
            parts.append(token)
    return " ".join(parts) if parts else "expression n/a"


def _clone_loadcomb_row_with_scale(
    base_row: dict[str, Any],
    *,
    target_name: str,
    scale_factor: float,
    target_limit_state: str,
    target_combination_type: str,
) -> dict[str, Any]:
    cloned = json.loads(json.dumps(base_row, ensure_ascii=False))
    entry_rows = _normalize_loadcomb_entry_rows(base_row)
    scaled_entry_rows = [
        {
            "reference_kind": str(row.get("reference_kind", "") or "").strip().upper() or "ST",
            "reference_name": str(row.get("reference_name", "") or "").strip(),
            "factor": float(row.get("factor", 0.0) or 0.0) * float(scale_factor),
        }
        for row in entry_rows
        if str(row.get("reference_name", "") or "").strip()
    ]
    scaled_expression_components = [
        {
            **component,
            "factor": float(component.get("factor", 0.0) or 0.0) * float(scale_factor),
        }
        for component in (base_row.get("expression_components") or [])
        if isinstance(component, dict)
    ]
    base_factor_map = base_row.get("factor_map") if isinstance(base_row.get("factor_map"), dict) else {}
    base_expanded_factor_map = (
        base_row.get("expanded_factor_map") if isinstance(base_row.get("expanded_factor_map"), dict) else base_factor_map
    )
    factor_map = _scale_loadcomb_factor_map(base_factor_map, scale=float(scale_factor))
    expanded_factor_map = _scale_loadcomb_factor_map(base_expanded_factor_map, scale=float(scale_factor))
    referenced_combinations = [
        str(row.get("reference_name", "") or "").strip()
        for row in scaled_entry_rows
        if str(row.get("reference_kind", "") or "").strip().upper() == "CB"
        and str(row.get("reference_name", "") or "").strip()
    ]
    referenced_cases = [
        str(row.get("reference_name", "") or "").strip()
        for row in scaled_entry_rows
        if str(row.get("reference_kind", "") or "").strip().upper() == "ST"
        and str(row.get("reference_name", "") or "").strip()
    ]
    cloned["name"] = str(target_name)
    cloned["limit_state"] = str(target_limit_state or base_row.get("limit_state", "") or "ACTIVE")
    cloned["combination_type"] = str(target_combination_type or base_row.get("combination_type", "") or "GEN")
    cloned["entries"] = scaled_entry_rows
    cloned["entry_rows"] = scaled_entry_rows
    cloned["entry_count"] = int(len(scaled_entry_rows))
    cloned["entry_line_count"] = max(1, int((len(scaled_entry_rows) + 1) // 2)) if scaled_entry_rows else 0
    cloned["expression_components"] = scaled_expression_components
    cloned["factor_map"] = factor_map
    cloned["expanded_factor_map"] = expanded_factor_map
    cloned["expression"] = _build_loadcomb_expression(scaled_entry_rows)
    cloned["referenced_cases"] = _dedupe_nonempty_text(referenced_cases)
    cloned["referenced_combinations"] = _dedupe_nonempty_text(referenced_combinations)
    cloned["referenced_leaf_cases"] = _dedupe_nonempty_text(list(expanded_factor_map.keys()))
    cloned["generator_tokens"] = [
        "0",
        "0",
        cloned["expression"],
        "0",
        "0",
        "0",
    ]
    cloned["raw_rows"] = []
    cloned["scale_factor"] = float(scale_factor)
    cloned["source_combination_name"] = str(base_row.get("name", "") or "")
    return cloned


def _build_editor_seed_combo_node_from_row(
    combo_row: dict[str, Any],
    *,
    editor_stage: int = 1,
) -> dict[str, Any]:
    entry_rows = _normalize_loadcomb_entry_rows(combo_row)
    factor_map = combo_row.get("factor_map") if isinstance(combo_row.get("factor_map"), dict) else {}
    referenced_combinations = [
        str(row.get("reference_name", "") or "").strip()
        for row in entry_rows
        if str(row.get("reference_kind", "") or "").strip().upper() == "CB"
        and str(row.get("reference_name", "") or "").strip()
    ]
    referenced_leaf_cases = _dedupe_nonempty_text(
        list((combo_row.get("expanded_factor_map") or factor_map or {}).keys())
    )
    return {
        "id": f"COMBO:{str(combo_row.get('name', '') or '').strip()}",
        "name": str(combo_row.get("name", "") or "").strip(),
        "kind": "combo",
        "editor_stage": int(editor_stage),
        "limit_state": str(combo_row.get("limit_state", "") or "ACTIVE"),
        "combination_type": str(combo_row.get("combination_type", "") or "GEN"),
        "expression": str(combo_row.get("expression", "") or "expression n/a"),
        "entry_count": int(len(entry_rows)),
        "expansion_mode": str(combo_row.get("expansion_mode", "") or "linear_combination"),
        "expansion_depth": int(combo_row.get("expansion_depth", 1) or 1),
        "referenced_combinations": referenced_combinations,
        "referenced_leaf_cases": referenced_leaf_cases,
        "factor_map": {
            str(key): float(value)
            for key, value in factor_map.items()
            if str(key).strip()
        },
        "entry_rows": entry_rows,
        "node_role": "override_combo",
    }


def _extract_loadcomb_preview_rows(preview_text: str) -> list[str]:
    rows: list[str] = []
    inside = False
    for raw_line in str(preview_text or "").splitlines():
        stripped = raw_line.strip()
        upper = stripped.upper()
        if upper.startswith("*LOADCOMB"):
            inside = True
            continue
        if inside and upper.startswith("*"):
            break
        if not inside or not stripped or stripped.startswith(";"):
            continue
        rows.append(stripped)
    return rows


def _build_viewer_loadcomb_override_plan(
    *,
    patch_payload: dict[str, Any],
    model_payload: dict[str, Any],
) -> dict[str, Any]:
    patch_entries = patch_payload.get("patch_entries")
    if not isinstance(patch_entries, list):
        patch_entries = []
    loads = _resolve_model_loads_container(model_payload)
    combo_rows = [row for row in (loads.get("load_combinations") or []) if isinstance(row, dict)]
    combo_lookup = _build_loadcomb_lookup(combo_rows)
    metadata = _resolve_model_metadata_container(model_payload)
    editor_seed = (
        metadata.get("load_combination_editor_seed")
        if isinstance(metadata.get("load_combination_editor_seed"), dict)
        else {}
    )
    combination_nodes = [
        row
        for row in (editor_seed.get("combination_nodes") or [])
        if isinstance(row, dict) and str(row.get("name", "") or "").strip()
    ]
    combination_node_lookup = _build_loadcomb_lookup(combination_nodes)

    rows: list[dict[str, Any]] = []
    resolved_entry_count = 0
    unresolved_entry_count = 0
    replaced_combo_count = 0
    appended_combo_count = 0
    for entry in patch_entries:
        if not isinstance(entry, dict):
            continue
        base_name = str(
            entry.get("base_combination_name")
            or entry.get("base_combo_name")
            or entry.get("source_combination_name")
            or ""
        ).strip()
        target_name = str(
            entry.get("target_combination_name")
            or entry.get("target_combo_name")
            or entry.get("combination_name")
            or ""
        ).strip()
        if not target_name and base_name:
            target_name = f"{base_name}_OVR"
        scale_factor = float(entry.get("scale_factor", 1.0) or 1.0)
        target_limit_state = str(entry.get("target_limit_state", "") or "").strip()
        target_combination_type = str(entry.get("target_combination_type", "") or "").strip()
        base_row = combo_lookup.get(base_name.lower()) if base_name else None
        base_node = combination_node_lookup.get(base_name.lower()) if base_name else None
        resolved = isinstance(base_row, dict) and bool(target_name)
        patched_row = None
        patched_node = None
        if resolved:
            resolved_entry_count += 1
            patched_row = _clone_loadcomb_row_with_scale(
                base_row,
                target_name=target_name,
                scale_factor=scale_factor,
                target_limit_state=target_limit_state,
                target_combination_type=target_combination_type,
            )
            patched_node = _build_editor_seed_combo_node_from_row(
                patched_row,
                editor_stage=int(base_node.get("editor_stage", 1) or 1) if isinstance(base_node, dict) else 1,
            )
            if target_name.lower() in combo_lookup:
                replaced_combo_count += 1
            else:
                appended_combo_count += 1
        else:
            unresolved_entry_count += 1
        rows.append(
            {
                "base_combination_name": base_name,
                "target_combination_name": target_name,
                "scale_factor": float(scale_factor),
                "draft_note": str(entry.get("draft_note", "") or ""),
                "target_limit_state": target_limit_state,
                "target_combination_type": target_combination_type,
                "resolution_mode": "resolved_to_combo_clone" if resolved else "unresolved_base_combination",
                "replaces_existing_target": bool(target_name and target_name.lower() in combo_lookup),
                "patched_combo_row": patched_row,
                "patched_combo_node": patched_node,
            }
        )
    return {
        "rows": rows,
        "summary": {
            "patch_present": True,
            "patch_entry_count": int(len(rows)),
            "resolved_entry_count": int(resolved_entry_count),
            "unresolved_entry_count": int(unresolved_entry_count),
            "replaced_combo_count": int(replaced_combo_count),
            "appended_combo_count": int(appended_combo_count),
        },
    }


def _apply_viewer_loadcomb_override_plan_to_model_payload(
    *,
    model_payload: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    patch_path: Path,
) -> dict[str, Any]:
    patched_payload = json.loads(json.dumps(model_payload, ensure_ascii=False))
    loads = _resolve_model_loads_container(patched_payload)
    combo_rows = [row for row in (loads.get("load_combinations") or []) if isinstance(row, dict)]
    combo_index_by_name = {
        str(row.get("name", "") or "").strip().lower(): index
        for index, row in enumerate(combo_rows)
        if str(row.get("name", "") or "").strip()
    }
    metadata = _resolve_model_metadata_container(patched_payload)
    editor_seed = (
        metadata.get("load_combination_editor_seed")
        if isinstance(metadata.get("load_combination_editor_seed"), dict)
        else {}
    )
    if not editor_seed:
        editor_seed = {
            "contract_version": "0.1.0",
            "provenance": "viewer_loadcomb_override_patch",
            "seed_kind": "midas_load_combination_editor_seed",
            "limitations": [
                "Viewer-authored load-combination patches are bounded authoring seeds.",
            ],
            "summary": {},
            "case_nodes": [],
            "combination_nodes": [],
            "graph_edges": [],
        }
        metadata["load_combination_editor_seed"] = editor_seed
    combination_nodes = [
        row for row in (editor_seed.get("combination_nodes") or []) if isinstance(row, dict)
    ]
    combination_node_index_by_name = {
        str(row.get("name", "") or "").strip().lower(): index
        for index, row in enumerate(combination_nodes)
        if str(row.get("name", "") or "").strip()
    }

    resolved_entry_count = 0
    unresolved_entry_count = 0
    replaced_combo_count = 0
    appended_combo_count = 0
    applied_rows: list[dict[str, Any]] = []
    for row in plan_rows:
        if not isinstance(row, dict):
            continue
        target_name = str(row.get("target_combination_name", "") or "").strip()
        patched_row = row.get("patched_combo_row") if isinstance(row.get("patched_combo_row"), dict) else None
        patched_node = row.get("patched_combo_node") if isinstance(row.get("patched_combo_node"), dict) else None
        resolution_mode = str(row.get("resolution_mode", "") or "")
        if not target_name or patched_row is None:
            unresolved_entry_count += 1
            applied_rows.append(
                {
                    "base_combination_name": str(row.get("base_combination_name", "") or ""),
                    "target_combination_name": target_name,
                    "scale_factor": float(row.get("scale_factor", 1.0) or 1.0),
                    "draft_note": str(row.get("draft_note", "") or ""),
                    "resolution_mode": resolution_mode or "unresolved_base_combination",
                }
            )
            continue
        target_key = target_name.lower()
        replaced_existing = target_key in combo_index_by_name
        if replaced_existing:
            combo_rows[int(combo_index_by_name[target_key])] = patched_row
            replaced_combo_count += 1
        else:
            combo_index_by_name[target_key] = len(combo_rows)
            combo_rows.append(patched_row)
            appended_combo_count += 1
        if patched_node is not None:
            if target_key in combination_node_index_by_name:
                combination_nodes[int(combination_node_index_by_name[target_key])] = patched_node
            else:
                combination_node_index_by_name[target_key] = len(combination_nodes)
                combination_nodes.append(patched_node)
        resolved_entry_count += 1
        applied_rows.append(
            {
                "base_combination_name": str(row.get("base_combination_name", "") or ""),
                "target_combination_name": target_name,
                "scale_factor": float(row.get("scale_factor", 1.0) or 1.0),
                "draft_note": str(row.get("draft_note", "") or ""),
                "target_limit_state": str(patched_row.get("limit_state", "") or ""),
                "target_combination_type": str(patched_row.get("combination_type", "") or ""),
                "resolution_mode": resolution_mode or "resolved_to_combo_clone",
                "replaces_existing_target": bool(replaced_existing),
                "entry_count": int(len(_normalize_loadcomb_entry_rows(patched_row))),
                "factor_map": {
                    str(key): float(value)
                    for key, value in (patched_row.get("factor_map") or {}).items()
                    if str(key).strip()
                },
                "source_combination_name": str(patched_row.get("source_combination_name", "") or ""),
            }
        )

    loads["load_combinations"] = combo_rows
    editor_seed["combination_nodes"] = combination_nodes
    summary = editor_seed.get("summary") if isinstance(editor_seed.get("summary"), dict) else {}
    summary["combination_count"] = int(len(combination_nodes))
    editor_seed["summary"] = summary
    loadcomb_preview_text = export_midas_loadcomb_from_model_payload(
        patched_payload,
        include_comments=False,
    )
    model = patched_payload.get("model") if isinstance(patched_payload.get("model"), dict) else {}
    if model:
        model["load_combinations_raw"] = _extract_loadcomb_preview_rows(loadcomb_preview_text)
    patched_payload["viewer_loadcomb_override_patch"] = {
        "contract_version": 1,
        "patch_mode": "working_loadcomb_override_patch",
        "applied_at": _now_utc(),
        "source_patch": str(patch_path),
        "patch_entry_count": int(len(plan_rows)),
        "resolved_entry_count": int(resolved_entry_count),
        "unresolved_entry_count": int(unresolved_entry_count),
        "replaced_combo_count": int(replaced_combo_count),
        "appended_combo_count": int(appended_combo_count),
        "rows": applied_rows,
    }
    return patched_payload


def _build_viewer_section_override_plan(
    *,
    patch_payload: dict[str, Any],
    model_payload: dict[str, Any],
) -> dict[str, Any]:
    patch_entries = patch_payload.get("patch_entries")
    if not isinstance(patch_entries, list):
        patch_entries = []
    section_lookup = _build_viewer_section_lookup(model_payload)
    elements = _resolve_model_elements(model_payload)
    elements_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for element in elements:
        for field in ("id", "element_id", "member_id"):
            key = str(element.get(field, "") or "").strip()
            if key:
                elements_by_key[key].append(element)

    rows: list[dict[str, Any]] = []
    retarget_map: dict[int, int] = {}
    resolved_entry_count = 0
    unresolved_entry_count = 0
    matched_element_count = 0
    retargeted_element_count = 0
    for entry in patch_entries:
        if not isinstance(entry, dict):
            continue
        candidate_keys = _dedupe_text_list(
            [
                entry.get("member_id"),
                entry.get("representative_element_id"),
                *(entry.get("element_ids") or []),
            ]
        )
        matched_elements: list[dict[str, Any]] = []
        seen_element_ids: set[int] = set()
        for key in candidate_keys:
            for element in elements_by_key.get(str(key), []):
                element_id = _as_int(element.get("id") or element.get("element_id"))
                if element_id is None or element_id in seen_element_ids:
                    continue
                seen_element_ids.add(int(element_id))
                matched_elements.append(element)
        target_section_id, resolution_source = _resolve_viewer_section_override_target_id(entry, section_lookup)
        matched_ids = sorted(
            int(_as_int(element.get("id") or element.get("element_id")) or 0)
            for element in matched_elements
            if _as_int(element.get("id") or element.get("element_id")) is not None
        )
        matched_element_count += len(matched_ids)
        retargeted_ids: list[int] = []
        if target_section_id is not None:
            resolved_entry_count += 1
            for element in matched_elements:
                element_id = _as_int(element.get("id") or element.get("element_id"))
                current_section_id = _as_int(element.get("section_id"))
                if element_id is None or current_section_id is None:
                    continue
                if int(current_section_id) == int(target_section_id):
                    continue
                retarget_map[int(element_id)] = int(target_section_id)
                retargeted_ids.append(int(element_id))
            retargeted_element_count += len(retargeted_ids)
        else:
            unresolved_entry_count += 1
        rows.append(
            {
                "member_id": str(entry.get("member_id", "") or ""),
                "target_section": str(
                    entry.get("target_section")
                    or entry.get("target_section_input")
                    or entry.get("target_section_name")
                    or ""
                ),
                "target_section_id": int(target_section_id) if target_section_id is not None else None,
                "target_section_resolution_source": str(resolution_source),
                "target_section_resolution_mode": str(
                    entry.get("target_section_resolution_mode", "") or ("resolved_to_section_id" if target_section_id is not None else "unresolved_free_text")
                ),
                "matched_element_ids": matched_ids,
                "matched_element_count": int(len(matched_ids)),
                "retargeted_element_ids": retargeted_ids,
                "retargeted_element_count": int(len(retargeted_ids)),
                "representative_element_id": str(entry.get("representative_element_id", "") or ""),
                "draft_note": str(entry.get("draft_note", "") or ""),
            }
        )
    return {
        "rows": rows,
        "element_retarget_map": retarget_map,
        "summary": {
            "patch_present": True,
            "patch_member_count": int(patch_payload.get("patch_member_count", 0) or len(rows)),
            "patch_entry_count": int(len(rows)),
            "resolved_entry_count": int(resolved_entry_count),
            "unresolved_entry_count": int(unresolved_entry_count),
            "matched_element_count": int(matched_element_count),
            "retargeted_element_count": int(retargeted_element_count),
        },
    }


def _apply_viewer_section_override_plan_to_model_payload(
    *,
    model_payload: dict[str, Any],
    plan_rows: list[dict[str, Any]],
    patch_path: Path,
) -> dict[str, Any]:
    patched_payload = json.loads(json.dumps(model_payload, ensure_ascii=False))
    elements = _resolve_model_elements(patched_payload)
    by_id = {
        int(element_id): element
        for element in elements
        if isinstance(element, dict) and (element_id := _as_int(element.get("id") or element.get("element_id"))) is not None
    }
    resolved_entry_count = 0
    unresolved_entry_count = 0
    matched_element_count = 0
    retargeted_element_count = 0
    for row in plan_rows:
        target_section_id = _as_int(row.get("target_section_id"))
        matched_ids = [int(v) for v in (row.get("matched_element_ids") or []) if _as_int(v) is not None]
        retargeted_ids = [int(v) for v in (row.get("retargeted_element_ids") or []) if _as_int(v) is not None]
        matched_element_count += len(matched_ids)
        retargeted_element_count += len(retargeted_ids)
        if target_section_id is not None:
            resolved_entry_count += 1
        else:
            unresolved_entry_count += 1
        for element_id in matched_ids:
            element = by_id.get(int(element_id))
            if not isinstance(element, dict):
                continue
            previous_section_id = _as_int(element.get("section_id"))
            if previous_section_id is not None:
                element["viewer_section_override_previous_section_id"] = int(previous_section_id)
            if target_section_id is not None and int(element_id) in retargeted_ids:
                element["section_id"] = int(target_section_id)
                element["viewer_section_override_resolved_section_id"] = int(target_section_id)
                element["viewer_section_override_resolved_section_name"] = str(row.get("target_section", "") or "")
            element["viewer_section_override_target_section"] = str(row.get("target_section", "") or "")
            element["viewer_section_override_draft_note"] = str(row.get("draft_note", "") or "")
            element["viewer_section_override_resolution"] = str(
                row.get("target_section_resolution_mode", "") or ("resolved_to_section_id" if target_section_id is not None else "unresolved_free_text")
            )
            element["viewer_section_override_applied_at"] = _now_utc()
    patched_payload["viewer_section_override_patch"] = {
        "contract_version": 1,
        "patch_mode": "working_section_override_patch",
        "applied_at": _now_utc(),
        "source_patch": str(patch_path),
        "patch_member_count": int(len(plan_rows)),
        "patch_entry_count": int(len(plan_rows)),
        "resolved_entry_count": int(resolved_entry_count),
        "unresolved_entry_count": int(unresolved_entry_count),
        "matched_element_count": int(matched_element_count),
        "retargeted_element_count": int(retargeted_element_count),
        "rows": plan_rows,
    }
    return patched_payload


def _build_model_maps(model_json_path: Path) -> tuple[dict[int, dict[str, Any]], dict[str, list[int]]]:
    model = _load_json(model_json_path)
    elements = model.get("model", {}).get("elements", []) if isinstance(model.get("model"), dict) else []
    metadata = model.get("model", {}).get("metadata", {}) if isinstance(model.get("model"), dict) else {}
    design_sections = metadata.get("design_sections", []) if isinstance(metadata, dict) else []
    element_map: dict[int, dict[str, Any]] = {}
    for row in elements:
        if not isinstance(row, dict):
            continue
        eid = _as_int(row.get("id"))
        sec_id = _as_int(row.get("section_id"))
        material_id = _as_int(row.get("material_id"))
        if eid is None or sec_id is None:
            continue
        element_map[int(eid)] = {
            "section_id": int(sec_id),
            "material_id": int(material_id) if material_id is not None else None,
            "family": str(row.get("family", "") or "").strip().lower(),
            "type": str(row.get("type", "") or "").strip().upper(),
        }
    signature_to_ids: dict[str, list[int]] = defaultdict(list)
    for row in design_sections:
        if not isinstance(row, dict):
            continue
        sec_id = _as_int(row.get("section_id"))
        row_tokens = row.get("row_tokens") if isinstance(row.get("row_tokens"), list) else []
        first = row_tokens[0] if row_tokens and isinstance(row_tokens[0], list) else []
        signature = ""
        if len(first) >= 3:
            signature = str(first[2]).strip()
        elif len(first) >= 2:
            signature = str(first[1]).strip()
        if sec_id is None or not signature:
            continue
        signature_to_ids[signature].append(int(sec_id))
    return element_map, {str(k): sorted(set(v)) for k, v in signature_to_ids.items()}

def _collect_viewer_section_override_element_retargets(
    parsed_model_payload: dict[str, Any],
) -> tuple[dict[int, int], list[dict[str, Any]]]:
    patch_receipt = (
        parsed_model_payload.get("viewer_section_override_patch")
        if isinstance(parsed_model_payload.get("viewer_section_override_patch"), dict)
        else {}
    )
    patch_rows = patch_receipt.get("rows") if isinstance(patch_receipt.get("rows"), list) else []
    patch_rows_by_member_id: dict[str, dict[str, Any]] = {}
    for row in patch_rows:
        if not isinstance(row, dict):
            continue
        member_id = str(row.get("member_id", "") or "").strip()
        if member_id and member_id not in patch_rows_by_member_id:
            patch_rows_by_member_id[member_id] = row

    element_retarget_map: dict[int, int] = {}
    retarget_rows: list[dict[str, Any]] = []
    for row in _resolve_model_elements(parsed_model_payload):
        element_id = _as_int(row.get("id"))
        if element_id is None:
            element_id = _as_int(row.get("element_id"))
        if element_id is None:
            element_id = _as_int(row.get("member_id"))
        resolved_section_id = _as_int(row.get("viewer_section_override_resolved_section_id"))
        previous_section_id = _as_int(row.get("viewer_section_override_previous_section_id"))
        current_section_id = _as_int(row.get("section_id"))
        resolution = str(row.get("viewer_section_override_resolution", "") or "").strip()
        if element_id is None or resolved_section_id is None or resolution != "resolved_to_section_id":
            continue
        if current_section_id is not None and int(current_section_id) != int(resolved_section_id):
            continue
        if previous_section_id is not None and int(previous_section_id) == int(resolved_section_id):
            continue
        member_id = str(row.get("member_id", row.get("id", row.get("element_id", ""))) or "").strip()
        patch_row = patch_rows_by_member_id.get(member_id, {})
        element_retarget_map[int(element_id)] = int(resolved_section_id)
        retarget_rows.append(
            {
                "element_id": int(element_id),
                "member_id": member_id,
                "previous_section_id": previous_section_id,
                "resolved_section_id": int(resolved_section_id),
                "current_section_id": current_section_id,
                "target_section": str(row.get("viewer_section_override_target_section", "") or ""),
                "resolved_section_name": str(row.get("viewer_section_override_resolved_section_name", "") or ""),
                "draft_note": str(row.get("viewer_section_override_draft_note", "") or ""),
                "applied_at": str(
                    row.get("viewer_section_override_applied_at")
                    or patch_row.get("applied_at")
                    or patch_receipt.get("applied_at")
                    or ""
                ),
                "source": "viewer_section_override_patch",
            }
        )
    retarget_rows.sort(key=lambda row: (int(row.get("element_id", 0)), str(row.get("member_id", ""))))
    return element_retarget_map, retarget_rows


def _load_rebar_payload_summary(
    model_json_path: Path,
    *,
    rebar_payload_projection_path: Path | None = None,
) -> dict[str, Any]:
    material_payloads = _load_material_payload_rows_with_fallback(
        model_json_path,
        rebar_payload_projection_path=rebar_payload_projection_path,
    )
    group_local_payloads = _load_group_local_payload_rows(
        model_json_path,
        rebar_payload_projection_path=rebar_payload_projection_path,
    )
    has_material_level_namespace = bool(material_payloads)
    has_group_local_namespace = bool(group_local_payloads)
    if has_group_local_namespace:
        namespace_mode = "group_local"
    elif has_material_level_namespace:
        namespace_mode = "material_level_only"
    else:
        namespace_mode = "none"
    return {
        "material_level_rebar_payload_row_count": int(len(material_payloads)),
        "material_level_rebar_payload_available_count": int(
            sum(1 for row in material_payloads if isinstance(row, dict) and bool(row.get("payload_present", False)))
        ),
        "group_local_rebar_payload_row_count": int(len(group_local_payloads)),
        "group_local_rebar_payload_available_count": int(
            sum(1 for row in group_local_payloads if isinstance(row, dict) and bool(row.get("payload_present", False)))
        ),
        "rebar_payload_namespace_mode": str(namespace_mode),
        "rebar_payload_material_level_namespace_present": bool(has_material_level_namespace),
        "rebar_payload_group_local_namespace_present": bool(has_group_local_namespace),
        "group_local_rebar_payload_group_ids": {
            str(row.get("group_id", ""))
            for row in group_local_payloads
            if isinstance(row, dict) and str(row.get("group_id", ""))
        },
    }


def _load_connection_detailing_payload_summary(
    model_json_path: Path,
    *,
    connection_detailing_payload_projection_path: Path | None = None,
) -> dict[str, Any]:
    group_local_payloads = _load_group_local_connection_detailing_payload_rows(
        model_json_path,
        connection_detailing_payload_projection_path=connection_detailing_payload_projection_path,
    )
    has_group_local_namespace = bool(group_local_payloads)
    return {
        "group_local_connection_detailing_payload_row_count": int(len(group_local_payloads)),
        "group_local_connection_detailing_payload_available_count": int(
            sum(1 for row in group_local_payloads if isinstance(row, dict) and bool(row.get("payload_present", False)))
        ),
        "connection_detailing_payload_namespace_mode": "group_local" if has_group_local_namespace else "none",
        "connection_detailing_payload_group_local_namespace_present": bool(has_group_local_namespace),
        "group_local_connection_detailing_payload_group_ids": {
            str(row.get("group_id", ""))
            for row in group_local_payloads
            if isinstance(row, dict) and str(row.get("group_id", ""))
        },
    }


def _load_detailing_payload_summary(
    model_json_path: Path,
    *,
    detailing_payload_projection_path: Path | None = None,
) -> dict[str, Any]:
    group_local_payloads = _load_group_local_detailing_payload_rows(
        model_json_path,
        detailing_payload_projection_path=detailing_payload_projection_path,
    )
    has_group_local_namespace = bool(group_local_payloads)
    return {
        "group_local_detailing_payload_row_count": int(len(group_local_payloads)),
        "group_local_detailing_payload_available_count": int(
            sum(1 for row in group_local_payloads if isinstance(row, dict) and bool(row.get("payload_present", False)))
        ),
        "detailing_payload_namespace_mode": "group_local" if has_group_local_namespace else "none",
        "detailing_payload_group_local_namespace_present": bool(has_group_local_namespace),
        "group_local_detailing_payload_group_ids": {
            str(row.get("group_id", ""))
            for row in group_local_payloads
            if isinstance(row, dict) and str(row.get("group_id", ""))
        },
    }


def _load_material_rebar_payload_map(
    model_json_path: Path,
    *,
    rebar_payload_projection_path: Path | None = None,
) -> dict[int, dict[str, Any]]:
    material_payloads = _load_material_payload_rows_with_fallback(
        model_json_path,
        rebar_payload_projection_path=rebar_payload_projection_path,
    )
    out: dict[int, dict[str, Any]] = {}
    for row in material_payloads:
        if not isinstance(row, dict):
            continue
        material_id = _as_int(row.get("material_id"))
        if material_id is None:
            continue
        out[int(material_id)] = dict(row)
    return out


def _load_group_local_rebar_payload_map(
    model_json_path: Path,
    *,
    rebar_payload_projection_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    group_local_payloads = _load_group_local_payload_rows(
        model_json_path,
        rebar_payload_projection_path=rebar_payload_projection_path,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return out


def _load_group_local_connection_detailing_payload_map(
    model_json_path: Path,
    *,
    connection_detailing_payload_projection_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    group_local_payloads = _load_group_local_connection_detailing_payload_rows(
        model_json_path,
        connection_detailing_payload_projection_path=connection_detailing_payload_projection_path,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return out


def _load_group_local_detailing_payload_map(
    model_json_path: Path,
    *,
    detailing_payload_projection_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    group_local_payloads = _load_group_local_detailing_payload_rows(
        model_json_path,
        detailing_payload_projection_path=detailing_payload_projection_path,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in group_local_payloads:
        if not isinstance(row, dict):
            continue
        group_id = str(row.get("group_id", "") or "").strip()
        if not group_id:
            continue
        out[group_id] = dict(row)
    return out


def _load_group_element_ids(
    *,
    row: dict[str, Any],
    group_to_elements: dict[str, list[int]],
) -> list[int]:
    group_id = str(row.get("group_id", "") or "")
    member_type = str(row.get("member_type", "") or "").strip().lower()
    element_ids = list(group_to_elements.get(group_id, []))
    if not element_ids and member_type == "wall" and ":slab:" in group_id:
        element_ids = list(group_to_elements.get(group_id.replace(":slab:", ":wall:"), []))
    return [int(v) for v in element_ids]


def _resolve_group_element_ids_with_source(
    *,
    row: dict[str, Any],
    group_to_elements: dict[str, list[int]],
) -> tuple[list[int], str]:
    group_id = str(row.get("group_id", "") or "")
    member_type = str(row.get("member_type", "") or "").strip().lower()
    direct_ids = [int(v) for v in group_to_elements.get(group_id, [])]
    if direct_ids:
        return direct_ids, "direct_group_id"
    if member_type == "wall" and ":slab:" in group_id:
        alt_group_id = group_id.replace(":slab:", ":wall:", 1)
        alt_ids = [int(v) for v in group_to_elements.get(alt_group_id, [])]
        if alt_ids:
            return alt_ids, "alt_slab_wall_group_id"
    if member_type == "slab" and ":wall:" in group_id:
        alt_group_id = group_id.replace(":wall:", ":slab:", 1)
        alt_ids = [int(v) for v in group_to_elements.get(alt_group_id, [])]
        if alt_ids:
            return alt_ids, "alt_wall_slab_group_id"
    return [], "unmapped_group_id"


def _resolve_group_local_rebar_payload_with_source(
    *,
    row: dict[str, Any],
    group_local_rebar_payload_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    group_id = str(row.get("group_id", "") or "").strip()
    member_type = str(row.get("member_type", "") or "").strip().lower()
    candidates = [(group_id, "direct_group_id")]
    if member_type == "wall" and ":slab:" in group_id:
        candidates.append((group_id.replace(":slab:", ":wall:", 1), "alt_slab_wall_group_id"))
    elif member_type == "slab" and ":wall:" in group_id:
        candidates.append((group_id.replace(":wall:", ":slab:", 1), "alt_wall_slab_group_id"))
    for candidate_group_id, source in candidates:
        payload = group_local_rebar_payload_map.get(candidate_group_id)
        if isinstance(payload, dict):
            return dict(payload), source
    return {}, "unmapped_group_id"


def _resolve_group_local_connection_detailing_payload_with_source(
    *,
    row: dict[str, Any],
    group_local_connection_detailing_payload_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    group_id = str(row.get("group_id", "") or "").strip()
    member_type = str(row.get("member_type", "") or "").strip().lower()
    candidates = [(group_id, "direct_group_id")]
    if member_type == "wall" and ":slab:" in group_id:
        candidates.append((group_id.replace(":slab:", ":wall:", 1), "alt_slab_wall_group_id"))
    elif member_type == "slab" and ":wall:" in group_id:
        candidates.append((group_id.replace(":wall:", ":slab:", 1), "alt_wall_slab_group_id"))
    for candidate_group_id, source in candidates:
        payload = group_local_connection_detailing_payload_map.get(candidate_group_id)
        if isinstance(payload, dict):
            return dict(payload), source
    return {}, "unmapped_group_id"


def _resolve_group_local_detailing_payload_with_source(
    *,
    row: dict[str, Any],
    group_local_detailing_payload_map: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    group_id = str(row.get("group_id", "") or "").strip()
    member_type = str(row.get("member_type", "") or "").strip().lower()
    candidates = [(group_id, "direct_group_id")]
    if member_type == "wall" and ":slab:" in group_id:
        candidates.append((group_id.replace(":slab:", ":wall:", 1), "alt_slab_wall_group_id"))
    elif member_type == "slab" and ":wall:" in group_id:
        candidates.append((group_id.replace(":wall:", ":slab:", 1), "alt_wall_slab_group_id"))
    for candidate_group_id, source in candidates:
        payload = group_local_detailing_payload_map.get(candidate_group_id)
        if isinstance(payload, dict):
            return dict(payload), source
    return {}, "unmapped_group_id"


def _derive_group_local_rebar_bridge_rows(
    *,
    changes: list[dict[str, Any]],
    group_to_elements: dict[str, list[int]],
    element_map: dict[int, dict[str, Any]],
    material_rebar_payload_map: dict[int, dict[str, Any]],
    group_local_rebar_payload_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, dict):
            continue
        family = str(_infer_action_family(row))
        if family not in {"rebar", "perimeter_frame"}:
            continue
        element_ids, mapping_source = _resolve_group_element_ids_with_source(
            row=row,
            group_to_elements=group_to_elements,
        )
        group_local_payload, payload_mapping_source = _resolve_group_local_rebar_payload_with_source(
            row=row,
            group_local_rebar_payload_map=group_local_rebar_payload_map,
        )
        group_local_payload_present = bool(group_local_payload.get("payload_present", False))
        material_ids = sorted(
            {
                int(elem.get("material_id"))
                for eid in element_ids
                for elem in [element_map.get(int(eid))]
                if isinstance(elem, dict) and _as_int(elem.get("material_id")) is not None
            }
        )
        payload_rows = [material_rebar_payload_map.get(int(mid), {}) for mid in material_ids]
        payload_available_ids = [
            int(mid)
            for mid, payload_row in zip(material_ids, payload_rows)
            if isinstance(payload_row, dict) and bool(payload_row.get("payload_present", False))
        ]
        direct_patch_eligible = bool(element_ids and material_ids and group_local_payload_present)
        if not element_ids:
            reason = "unmapped_group_to_elements"
        elif not material_ids:
            reason = "unmapped_elements_to_materials"
        elif not group_local_payload_present and len(material_ids) > 1:
            reason = "mixed_material_scope"
        elif not group_local_payload_present:
            reason = "material_payload_missing"
        else:
            reason = "eligible"
        rows.append(
            {
                "group_id": str(row.get("group_id", "") or ""),
                "member_type": str(row.get("member_type", "") or "").strip().lower(),
                "action_family": family,
                "mapping_source": mapping_source,
                "element_id_count": int(len(element_ids)),
                "element_ids_head": [int(v) for v in element_ids[:16]],
                "material_ids": [int(v) for v in material_ids],
                "material_payload_available_ids": [int(v) for v in payload_available_ids],
                "direct_patch_eligible": bool(direct_patch_eligible),
                "ineligibility_reason": reason,
                "group_local_payload_present": bool(group_local_payload_present),
                "group_local_payload_group_id": str(group_local_payload.get("group_id", "") or ""),
                "group_local_payload_mapping_source": str(payload_mapping_source),
                "payload_source_class": "group_local_rebar_payload" if group_local_payload_present else "",
                "group_local_payload": dict(group_local_payload) if group_local_payload_present else {},
            }
        )
    return rows


def _derive_group_local_connection_detailing_bridge_rows(
    *,
    changes: list[dict[str, Any]],
    group_to_elements: dict[str, list[int]],
    element_map: dict[int, dict[str, Any]],
    material_rebar_payload_map: dict[int, dict[str, Any]],
    group_local_connection_detailing_payload_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, dict):
            continue
        family = str(_infer_action_family(row))
        if family != "connection_detailing":
            continue
        element_ids, mapping_source = _resolve_group_element_ids_with_source(
            row=row,
            group_to_elements=group_to_elements,
        )
        connection_payload, payload_mapping_source = _resolve_group_local_connection_detailing_payload_with_source(
            row=row,
            group_local_connection_detailing_payload_map=group_local_connection_detailing_payload_map,
        )
        connection_payload_present = bool(connection_payload.get("payload_present", False))
        if not element_ids and connection_payload_present:
            payload_element_ids = [
                int(v)
                for v in (
                    list(connection_payload.get("element_ids", []))
                    if isinstance(connection_payload.get("element_ids"), list)
                    else []
                )
                if _as_int(v) is not None
            ]
            if not payload_element_ids:
                payload_element_ids_head = [
                    int(v)
                    for v in (
                        list(connection_payload.get("element_ids_head", []))
                        if isinstance(connection_payload.get("element_ids_head"), list)
                        else []
                    )
                    if _as_int(v) is not None
                ]
                payload_element_count = _as_int(connection_payload.get("element_id_count"))
                if payload_element_ids_head and payload_element_count is not None and int(payload_element_count) <= len(payload_element_ids_head):
                    payload_element_ids = payload_element_ids_head
            if payload_element_ids:
                element_ids = [int(v) for v in payload_element_ids]
                mapping_source = f"payload_projection:{str(payload_mapping_source or 'element_ids')}"
        material_ids = sorted(
            {
                int(elem.get("material_id"))
                for eid in element_ids
                for elem in [element_map.get(int(eid))]
                if isinstance(elem, dict) and _as_int(elem.get("material_id")) is not None
            }
        )
        section_ids = sorted(
            {
                int(elem.get("section_id"))
                for eid in element_ids
                for elem in [element_map.get(int(eid))]
                if isinstance(elem, dict) and _as_int(elem.get("section_id")) is not None
            }
        )
        payload_rows = [material_rebar_payload_map.get(int(mid), {}) for mid in material_ids]
        payload_available_ids = [
            int(mid)
            for mid, payload_row in zip(material_ids, payload_rows)
            if isinstance(payload_row, dict) and bool(payload_row.get("payload_present", False))
        ]
        material_payload = dict(payload_rows[0]) if len(material_ids) == 1 and isinstance(payload_rows[0], dict) else {}
        direct_patch_eligible = bool(
            str(row.get("member_type", "") or "").strip().lower() == "beam"
            and element_ids
            and len(material_ids) == 1
            and len(section_ids) == 1
            and connection_payload_present
            and bool(material_payload.get("payload_present", False))
        )
        if str(row.get("member_type", "") or "").strip().lower() != "beam":
            reason = "unsupported_member_type"
        elif not element_ids:
            reason = "unmapped_group_to_elements"
        elif not material_ids:
            reason = "unmapped_elements_to_materials"
        elif len(material_ids) != 1:
            reason = "multi_material_scope"
        elif len(section_ids) != 1:
            reason = "multi_section_scope"
        elif not connection_payload_present:
            reason = "structured_payload_missing"
        elif not bool(material_payload.get("payload_present", False)):
            reason = "material_payload_missing"
        else:
            reason = "eligible"
        rows.append(
            {
                "group_id": str(row.get("group_id", "") or ""),
                "member_type": str(row.get("member_type", "") or "").strip().lower(),
                "action_family": family,
                "mapping_source": mapping_source,
                "element_id_count": int(len(element_ids)),
                "element_ids": [int(v) for v in element_ids],
                "element_ids_head": [int(v) for v in element_ids[:16]],
                "section_ids": [int(v) for v in section_ids],
                "material_ids": [int(v) for v in material_ids],
                "material_payload_available_ids": [int(v) for v in payload_available_ids],
                "direct_patch_eligible": bool(direct_patch_eligible),
                "ineligibility_reason": str(reason),
                "structured_payload_present": bool(connection_payload_present),
                "structured_payload_group_id": str(connection_payload.get("group_id", "") or ""),
                "structured_payload_mapping_source": str(payload_mapping_source),
                "structured_payload_source_class": str(connection_payload.get("payload_source_class", "") or ""),
                "structured_payload": dict(connection_payload) if connection_payload_present else {},
                "material_payload": dict(material_payload) if bool(material_payload.get("payload_present", False)) else {},
                "material_payload_source_class": str(material_payload.get("payload_basis", "") or ""),
            }
        )
    return rows


def _derive_group_local_detailing_bridge_rows(
    *,
    changes: list[dict[str, Any]],
    group_to_elements: dict[str, list[int]],
    element_map: dict[int, dict[str, Any]],
    material_rebar_payload_map: dict[int, dict[str, Any]],
    group_local_detailing_payload_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, dict):
            continue
        family = str(_infer_action_family(row))
        if family != "detailing":
            continue
        element_ids, mapping_source = _resolve_group_element_ids_with_source(
            row=row,
            group_to_elements=group_to_elements,
        )
        detailing_payload, payload_mapping_source = _resolve_group_local_detailing_payload_with_source(
            row=row,
            group_local_detailing_payload_map=group_local_detailing_payload_map,
        )
        detailing_payload_present = bool(detailing_payload.get("payload_present", False))
        if not element_ids and detailing_payload_present:
            payload_element_ids = [
                int(v)
                for v in (
                    list(detailing_payload.get("element_ids", []))
                    if isinstance(detailing_payload.get("element_ids"), list)
                    else []
                )
                if _as_int(v) is not None
            ]
            if not payload_element_ids:
                payload_element_ids_head = [
                    int(v)
                    for v in (
                        list(detailing_payload.get("element_ids_head", []))
                        if isinstance(detailing_payload.get("element_ids_head"), list)
                        else []
                    )
                    if _as_int(v) is not None
                ]
                payload_element_count = _as_int(detailing_payload.get("element_id_count"))
                if payload_element_ids_head and payload_element_count is not None and int(payload_element_count) <= len(payload_element_ids_head):
                    payload_element_ids = payload_element_ids_head
            if payload_element_ids:
                element_ids = [int(v) for v in payload_element_ids]
                mapping_source = f"payload_projection:{str(payload_mapping_source or 'element_ids')}"
        material_ids = sorted(
            {
                int(elem.get("material_id"))
                for eid in element_ids
                for elem in [element_map.get(int(eid))]
                if isinstance(elem, dict) and _as_int(elem.get("material_id")) is not None
            }
        )
        section_ids = sorted(
            {
                int(elem.get("section_id"))
                for eid in element_ids
                for elem in [element_map.get(int(eid))]
                if isinstance(elem, dict) and _as_int(elem.get("section_id")) is not None
            }
        )
        payload_rows = [material_rebar_payload_map.get(int(mid), {}) for mid in material_ids]
        payload_rows_by_material_id = {
            int(mid): dict(payload_row)
            for mid, payload_row in zip(material_ids, payload_rows)
            if isinstance(payload_row, dict) and bool(payload_row.get("payload_present", False))
        }
        payload_available_ids = [
            int(mid)
            for mid, payload_row in zip(material_ids, payload_rows)
            if isinstance(payload_row, dict) and bool(payload_row.get("payload_present", False))
        ]
        direct_patch_eligible = bool(
            element_ids
            and material_ids
            and detailing_payload_present
            and len(payload_available_ids) == len(material_ids)
        )
        if not element_ids:
            reason = "unmapped_group_to_elements"
        elif not material_ids:
            reason = "unmapped_elements_to_materials"
        elif not detailing_payload_present:
            reason = "structured_payload_missing"
        elif len(payload_available_ids) != len(material_ids):
            reason = "material_payload_missing"
        else:
            reason = "eligible"
        rows.append(
            {
                "group_id": str(row.get("group_id", "") or ""),
                "member_type": str(row.get("member_type", "") or "").strip().lower(),
                "action_family": family,
                "mapping_source": mapping_source,
                "element_id_count": int(len(element_ids)),
                "element_ids": [int(v) for v in element_ids],
                "element_ids_head": [int(v) for v in element_ids[:16]],
                "section_ids": [int(v) for v in section_ids],
                "material_ids": [int(v) for v in material_ids],
                "material_payload_available_ids": [int(v) for v in payload_available_ids],
                "direct_patch_eligible": bool(direct_patch_eligible),
                "ineligibility_reason": str(reason),
                "structured_payload_present": bool(detailing_payload_present),
                "structured_payload_group_id": str(detailing_payload.get("group_id", "") or ""),
                "structured_payload_mapping_source": str(payload_mapping_source),
                "structured_payload_source_class": str(detailing_payload.get("payload_source_class", "") or ""),
                "structured_payload": dict(detailing_payload) if detailing_payload_present else {},
                "material_payload_rows_by_material_id": payload_rows_by_material_id,
                "material_payload_source_class": ", ".join(
                    sorted(
                        {
                            str(payload_row.get("payload_basis", "") or "")
                            for payload_row in payload_rows_by_material_id.values()
                            if isinstance(payload_row, dict)
                        }
                    )
                ),
            }
        )
    return rows


def _resolve_section_ids_for_change(
    *,
    row: dict[str, Any],
    action_family: str,
    group_to_elements: dict[str, list[int]],
    element_map: dict[int, dict[str, Any]],
    section_signature_to_ids: dict[str, list[int]],
) -> list[int]:
    group_id = str(row.get("group_id", "") or "")
    member_type = str(row.get("member_type", "") or "").strip().lower()
    element_ids = group_to_elements.get(group_id, [])
    if not element_ids and member_type == "wall" and ":slab:" in group_id:
        element_ids = group_to_elements.get(group_id.replace(":slab:", ":wall:"), [])
    section_ids: set[int] = set()
    for eid in element_ids:
        elem = element_map.get(int(eid))
        if not isinstance(elem, dict):
            continue
        family = str(elem.get("family", "") or "").strip().lower()
        if action_family == "beam_section" and member_type == "beam" and family == "beam":
            section_ids.add(int(elem["section_id"]))
        elif action_family == "wall_thickness" and member_type == "wall" and family == "shell":
            section_ids.add(int(elem["section_id"]))
        elif action_family == "slab_thickness" and member_type == "slab" and family == "shell":
            section_ids.add(int(elem["section_id"]))
    if section_ids:
        return sorted(section_ids)
    signature = group_id.split(":")[-1].strip() if group_id else ""
    if action_family == "beam_section" and signature:
        return list(section_signature_to_ids.get(signature, []))
    return []


def _model_id_bounds(model_json_path: Path) -> tuple[int, int, int]:
    model = _load_json(model_json_path)
    model_body = model.get("model", {}) if isinstance(model.get("model"), dict) else {}
    metadata = model_body.get("metadata", {}) if isinstance(model_body, dict) else {}
    design_sections = metadata.get("design_sections", []) if isinstance(metadata, dict) else []
    thickness_rows = metadata.get("thickness", []) if isinstance(metadata, dict) else []
    elements = model_body.get("elements", []) if isinstance(model_body, dict) else []
    material_payload_rows = metadata.get("design_material_rebar_payloads", []) if isinstance(metadata, dict) else []
    max_section_id = 0
    max_thickness_id = 0
    max_material_id = 0
    for row in design_sections:
        if isinstance(row, dict):
            max_section_id = max(max_section_id, int(_as_int(row.get("section_id")) or 0))
    for row in thickness_rows:
        if isinstance(row, dict):
            max_thickness_id = max(max_thickness_id, int(_as_int(row.get("thickness_id")) or 0))
    for row in elements:
        if isinstance(row, dict):
            max_material_id = max(max_material_id, int(_as_int(row.get("material_id")) or 0))
    for row in material_payload_rows:
        if isinstance(row, dict):
            max_material_id = max(max_material_id, int(_as_int(row.get("material_id")) or 0))
    return max_section_id, max_thickness_id, max_material_id


def _rewrite_sect_scale_line(line: str, ratio: float) -> tuple[str, dict[str, Any]] | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    if len(toks) < 8:
        return None
    sec_id = _as_int(toks[0])
    values = [_as_float(tok) for tok in toks[1:8]]
    if sec_id is None or any(v is None for v in values):
        return None
    new_values = [float(v) * float(ratio) for v in values if v is not None]
    tail = toks[8:]
    new_toks = [str(sec_id)] + [_format_float(v) for v in new_values] + tail
    return (
        "    " + ", ".join(new_toks) + "\n",
        {
            "section_id": int(sec_id),
            "ratio": float(ratio),
            "old_values": [float(v) for v in values if v is not None],
            "new_values": [float(v) for v in new_values],
        },
    )


def _rewrite_thickness_line(line: str, ratio: float) -> tuple[str, dict[str, Any]] | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    if len(toks) < 6:
        return None
    thickness_id = _as_int(toks[0])
    thk_in = _as_float(toks[4])
    thk_out = _as_float(toks[5])
    if thickness_id is None or thk_in is None:
        return None
    new_toks = list(toks)
    new_thk_in = float(thk_in) * float(ratio)
    new_toks[4] = _format_float(new_thk_in)
    new_thk_out = thk_out
    if thk_out is not None:
        new_thk_out = float(thk_out) * float(ratio)
        new_toks[5] = _format_float(new_thk_out)
    return (
        "    " + ", ".join(new_toks) + "\n",
        {
            "thickness_id": int(thickness_id),
            "ratio": float(ratio),
            "old_thickness_in": float(thk_in),
            "new_thickness_in": float(new_thk_in),
            "old_thickness_out": float(thk_out or 0.0),
            "new_thickness_out": float(new_thk_out or 0.0),
        },
    )


def _clone_section_line(line: str, *, new_id: int) -> str | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    sec_id = _as_int(toks[0]) if toks else None
    if sec_id is None:
        return None
    new_toks = list(toks)
    new_toks[0] = str(int(new_id))
    if len(new_toks) >= 3:
        base_name = str(new_toks[2]).strip() or f"SEC{int(sec_id)}"
        new_toks[2] = f"{base_name}_OPT{int(new_id)}"
    return "    " + ", ".join(new_toks) + "\n"


def _clone_thickness_line(line: str, *, new_id: int, ratio: float) -> tuple[str, dict[str, Any]] | None:
    rewritten = _rewrite_thickness_line(line, ratio)
    if rewritten is None:
        return None
    new_line, detail = rewritten
    toks = [tok.strip() for tok in new_line.rstrip("\n").split(",")]
    if not toks:
        return None
    toks[0] = str(int(new_id))
    return (
        "    " + ", ".join(toks) + "\n",
        {
            **detail,
            "thickness_id": int(new_id),
            "source_thickness_id": int(detail.get("thickness_id", 0) or 0),
            "cloned_from_thickness_id": int(detail.get("thickness_id", 0) or 0),
            "inserted_new_row": True,
        },
    )


def _clone_sect_scale_line(line: str, *, new_id: int, ratio: float) -> tuple[str, dict[str, Any]] | None:
    rewritten = _rewrite_sect_scale_line(line, ratio)
    if rewritten is None:
        return None
    new_line, detail = rewritten
    toks = [tok.strip() for tok in new_line.rstrip("\n").split(",")]
    if not toks:
        return None
    toks[0] = str(int(new_id))
    return (
        "    " + ", ".join(toks) + "\n",
        {
            **detail,
            "section_id": int(new_id),
            "source_section_id": int(detail.get("section_id", 0) or 0),
            "cloned_from_section_id": int(detail.get("section_id", 0) or 0),
            "inserted_new_row": True,
        },
    )


def _rewrite_element_property_id(line: str, *, new_property_id: int) -> tuple[str, dict[str, Any]] | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    if len(toks) < 4:
        return None
    elem_id = _as_int(toks[0])
    old_property_id = _as_int(toks[3])
    if elem_id is None or old_property_id is None:
        return None
    new_toks = list(toks)
    new_toks[3] = str(int(new_property_id))
    return (
        "    " + ", ".join(new_toks) + "\n",
        {
            "element_id": int(elem_id),
            "old_property_id": int(old_property_id),
            "new_property_id": int(new_property_id),
        },
    )


def _rewrite_element_targets(
    line: str,
    *,
    new_material_id: int | None = None,
    new_property_id: int | None = None,
) -> tuple[str, dict[str, Any]] | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    if len(toks) < 4:
        return None
    elem_id = _as_int(toks[0])
    old_material_id = _as_int(toks[2])
    old_property_id = _as_int(toks[3])
    if elem_id is None:
        return None
    new_toks = list(toks)
    detail: dict[str, Any] = {"element_id": int(elem_id)}
    if new_material_id is not None:
        if old_material_id is None:
            return None
        new_toks[2] = str(int(new_material_id))
        detail.update({"old_material_id": int(old_material_id), "new_material_id": int(new_material_id)})
    if new_property_id is not None:
        if old_property_id is None:
            return None
        new_toks[3] = str(int(new_property_id))
        detail.update({"old_property_id": int(old_property_id), "new_property_id": int(new_property_id)})
    return ("    " + ", ".join(new_toks) + "\n", detail)


def _rewrite_dgn_matl_payload_line(
    line: str,
    *,
    payload: dict[str, Any],
    new_material_id: int,
) -> tuple[str, dict[str, Any]] | None:
    toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
    source_material_id = _as_int(toks[0]) if toks else None
    material_type = str(toks[1]).strip().upper() if len(toks) >= 2 else ""
    if source_material_id is None or material_type not in {"CONC", "SRC"}:
        return None
    while len(toks) <= 13:
        toks.append("")
    rbcode = str(payload.get("rbcode", toks[9]) or "").strip()
    rbmain = str(payload.get("rbmain", toks[10]) or "").strip()
    rbsub = str(payload.get("rbsub", toks[11]) or "").strip()
    fy_r = payload.get("fy_r", toks[12])
    fys = payload.get("fys", toks[13])
    toks[0] = str(int(new_material_id))
    toks[9] = rbcode
    toks[10] = rbmain
    toks[11] = rbsub
    toks[12] = "" if fy_r in {None, ""} else _format_float(float(fy_r))
    toks[13] = "" if fys in {None, ""} else _format_float(float(fys))
    return (
        "    " + ", ".join(toks) + "\n",
        {
            "source_material_id": int(source_material_id),
            "material_id": int(new_material_id),
            "source_material_type": material_type,
            "payload_source_class": "group_local_rebar_payload",
            "rbcode": rbcode,
            "rbmain": rbmain,
            "rbsub": rbsub,
            "fy_r": None if fy_r in {None, ""} else float(fy_r),
            "fys": None if fys in {None, ""} else float(fys),
        },
    )


def _apply_mgt_patches(
    *,
    source_mgt_path: Path,
    output_mgt_path: Path,
    section_scale_patches: dict[int, float],
    thickness_patches: dict[int, float],
    section_clone_specs: list[dict[str, Any]] | None = None,
    thickness_clone_specs: list[dict[str, Any]] | None = None,
    element_retarget_map: dict[int, int] | None = None,
    material_clone_specs: list[dict[str, Any]] | None = None,
    element_material_retarget_map: dict[int, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    lines = source_mgt_path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    current_section = ""
    out_lines: list[str] = []
    applied_scale_rows: list[dict[str, Any]] = []
    applied_thickness_rows: list[dict[str, Any]] = []
    applied_material_rows: list[dict[str, Any]] = []
    retargeted_element_rows: list[dict[str, Any]] = []
    seen_section_scale_ids: set[int] = set()
    seen_thickness_ids: set[int] = set()
    section_clone_specs = list(section_clone_specs or [])
    thickness_clone_specs = list(thickness_clone_specs or [])
    element_retarget_map = {int(k): int(v) for k, v in (element_retarget_map or {}).items()}
    material_clone_specs = list(material_clone_specs or [])
    element_material_retarget_map = {
        int(k): int(v) for k, v in (element_material_retarget_map or {}).items()
    }
    section_clones_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    thickness_clones_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    material_clones_by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for spec in section_clone_specs:
        source_id = _as_int(spec.get("source_id"))
        new_id = _as_int(spec.get("new_id"))
        if source_id is None or new_id is None:
            continue
        section_clones_by_source[int(source_id)].append({"source_id": int(source_id), "new_id": int(new_id), "ratio": float(spec.get("ratio", 1.0) or 1.0)})
    for spec in thickness_clone_specs:
        source_id = _as_int(spec.get("source_id"))
        new_id = _as_int(spec.get("new_id"))
        if source_id is None or new_id is None:
            continue
        thickness_clones_by_source[int(source_id)].append({"source_id": int(source_id), "new_id": int(new_id), "ratio": float(spec.get("ratio", 1.0) or 1.0)})
    for spec in material_clone_specs:
        source_id = _as_int(spec.get("source_id"))
        new_id = _as_int(spec.get("new_id"))
        payload = spec.get("payload") if isinstance(spec.get("payload"), dict) else {}
        if source_id is None or new_id is None or not payload:
            continue
        material_clones_by_source[int(source_id)].append(
            {
                "source_id": int(source_id),
                "new_id": int(new_id),
                "payload": payload,
            }
        )

    def _flush_pending_sect_scale_rows() -> None:
        missing_ids = sorted(set(int(v) for v in section_scale_patches) - seen_section_scale_ids)
        for sec_id in missing_ids:
            ratio = float(section_scale_patches[int(sec_id)])
            new_line = (
                "    "
                + ", ".join(
                    [
                        str(int(sec_id)),
                        _format_float(ratio),
                        _format_float(ratio),
                        _format_float(ratio),
                        _format_float(ratio),
                        _format_float(ratio),
                        _format_float(ratio),
                        _format_float(ratio),
                        "",
                        "1",
                    ]
                )
                + "\n"
            )
            out_lines.append(new_line)
            applied_scale_rows.append(
                {
                    "section_id": int(sec_id),
                    "ratio": float(ratio),
                    "old_values": [1.0] * 7,
                    "new_values": [float(ratio)] * 7,
                    "inserted_new_row": True,
                }
            )
            seen_section_scale_ids.add(int(sec_id))

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("*"):
            if current_section == "SECT-SCALE":
                _flush_pending_sect_scale_rows()
            current_section = stripped[1:].split(";", 1)[0].strip().upper()
            out_lines.append(line)
            continue
        if not stripped or stripped.startswith(";"):
            out_lines.append(line)
            continue
        if current_section == "SECTION":
            toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
            sec_id = _as_int(toks[0]) if toks else None
            out_lines.append(line)
            if sec_id is not None:
                for spec in section_clones_by_source.get(int(sec_id), []):
                    clone_line = _clone_section_line(line, new_id=int(spec["new_id"]))
                    if clone_line is not None:
                        out_lines.append(clone_line)
            continue
        if current_section == "ELEMENT":
            toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
            elem_id = _as_int(toks[0]) if toks else None
            if elem_id is not None and (
                int(elem_id) in element_retarget_map or int(elem_id) in element_material_retarget_map
            ):
                rewritten = _rewrite_element_targets(
                    line,
                    new_material_id=element_material_retarget_map.get(int(elem_id)),
                    new_property_id=element_retarget_map.get(int(elem_id)),
                )
                if rewritten is not None:
                    new_line, detail = rewritten
                    retargeted_element_rows.append(detail)
                    out_lines.append(new_line)
                    continue
        if current_section == "DGN-MATL":
            toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
            material_id = _as_int(toks[0]) if toks else None
            out_lines.append(line)
            if material_id is not None:
                for spec in material_clones_by_source.get(int(material_id), []):
                    clone = _rewrite_dgn_matl_payload_line(
                        line,
                        payload=dict(spec.get("payload", {})),
                        new_material_id=int(spec["new_id"]),
                    )
                    if clone is not None:
                        clone_line, detail = clone
                        applied_material_rows.append(detail)
                        out_lines.append(clone_line)
            continue
        if current_section == "SECT-SCALE":
            toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
            sec_id = _as_int(toks[0]) if toks else None
            emitted_line = False
            if sec_id is not None and int(sec_id) in section_scale_patches:
                rewritten = _rewrite_sect_scale_line(line, section_scale_patches[int(sec_id)])
                if rewritten is not None:
                    new_line, detail = rewritten
                    applied_scale_rows.append(detail)
                    seen_section_scale_ids.add(int(sec_id))
                    out_lines.append(new_line)
                    emitted_line = True
            if not emitted_line:
                out_lines.append(line)
            if sec_id is not None:
                for spec in section_clones_by_source.get(int(sec_id), []):
                    cloned = _clone_sect_scale_line(line, new_id=int(spec["new_id"]), ratio=float(spec["ratio"]))
                    if cloned is not None:
                        clone_line, detail = cloned
                        applied_scale_rows.append(detail)
                        seen_section_scale_ids.add(int(spec["new_id"]))
                        out_lines.append(clone_line)
            if emitted_line or sec_id is not None:
                continue
        elif current_section == "THICKNESS":
            toks = [tok.strip() for tok in line.rstrip("\n").split(",")]
            thickness_id = _as_int(toks[0]) if toks else None
            emitted_line = False
            if thickness_id is not None and int(thickness_id) in thickness_patches:
                rewritten = _rewrite_thickness_line(line, thickness_patches[int(thickness_id)])
                if rewritten is not None:
                    new_line, detail = rewritten
                    applied_thickness_rows.append(detail)
                    seen_thickness_ids.add(int(thickness_id))
                    out_lines.append(new_line)
                    emitted_line = True
            if not emitted_line:
                out_lines.append(line)
            if thickness_id is not None:
                for spec in thickness_clones_by_source.get(int(thickness_id), []):
                    cloned = _clone_thickness_line(line, new_id=int(spec["new_id"]), ratio=float(spec["ratio"]))
                    if cloned is not None:
                        clone_line, detail = cloned
                        applied_thickness_rows.append(detail)
                        seen_thickness_ids.add(int(spec["new_id"]))
                        out_lines.append(clone_line)
            if emitted_line or thickness_id is not None:
                continue
        out_lines.append(line)
    if current_section == "SECT-SCALE":
        _flush_pending_sect_scale_rows()
    output_mgt_path.parent.mkdir(parents=True, exist_ok=True)
    output_mgt_path.write_text("".join(out_lines), encoding="utf-8")
    return applied_scale_rows, applied_thickness_rows, applied_material_rows, retargeted_element_rows


def main() -> int:
    p = argparse.ArgumentParser(description="Export bounded design-optimization changes back to MIDAS MGT.")
    p.add_argument("--source-mgt", default="implementation/phase1/open_data/midas/midas_generator_33.mgt")
    p.add_argument("--parsed-model-json", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--dataset-npz", default="implementation/phase1/release/design_optimization/design_optimization_dataset.npz")
    p.add_argument("--changes-json", default="implementation/phase1/release/design_optimization/design_optimization_cost_reduction_changes.json")
    p.add_argument("--section-override-patch-json", default="")
    p.add_argument("--section-override-applied-source-json-out", default="")
    p.add_argument("--loadcomb-override-patch-json", default="")
    p.add_argument("--loadcomb-override-applied-source-json-out", default="")
    p.add_argument(
        "--rebar-payload-projection-json",
        default="",
    )
    p.add_argument(
        "--connection-detailing-payload-projection-json",
        default="",
    )
    p.add_argument(
        "--detailing-payload-projection-json",
        default="",
    )
    p.add_argument("--output-mgt", default="implementation/phase1/open_data/midas/midas_generator_33.optimized.mgt")
    p.add_argument("--report-out", default="implementation/phase1/open_data/midas/midas_generator_33.optimized.export_report.json")
    p.add_argument("--patch-manifest-out", default="implementation/phase1/open_data/midas/midas_generator_33.optimized.patch_manifest.json")
    p.add_argument("--instruction-sidecar-out", default="implementation/phase1/open_data/midas/midas_generator_33.optimized.instruction_sidecar.json")
    p.add_argument("--audit-review-manifest-out", default="")
    p.add_argument("--audit-review-packet-manifest-out", default="")
    p.add_argument("--audit-review-packet-dir-out", default="")
    p.add_argument("--audit-review-queue-manifest-out", default="")
    p.add_argument("--audit-review-queue-status-dir-out", default="")
    p.add_argument("--audit-review-followup-manifest-out", default="")
    p.add_argument("--audit-review-resolution-manifest-out", default="")
    p.add_argument("--audit-review-resolution-dir-out", default="")
    p.add_argument("--loadcomb-preview-out", default="")
    p.add_argument("--loadcomb-roundtrip-report-out", default="")
    p.add_argument("--source-output-diff-json-out", default="")
    p.add_argument("--source-output-diff-preview-out", default="")
    p.add_argument("--source-output-diff-window-json-out", default="")
    p.add_argument("--source-output-diff-window-preview-out", default="")
    args = p.parse_args()

    source_mgt_path = _resolve_input_path(args.source_mgt)
    parsed_model_json_path = _resolve_input_path(args.parsed_model_json)
    dataset_npz_path = _resolve_input_path(args.dataset_npz)
    changes_json_path = _resolve_input_path(args.changes_json)
    section_override_patch_json_path = (
        _resolve_input_path(args.section_override_patch_json)
        if str(args.section_override_patch_json).strip()
        else None
    )
    loadcomb_override_patch_json_path = (
        _resolve_input_path(args.loadcomb_override_patch_json)
        if str(args.loadcomb_override_patch_json).strip()
        else None
    )
    rebar_payload_projection_json_path = (
        _resolve_input_path(args.rebar_payload_projection_json)
        if str(args.rebar_payload_projection_json).strip()
        else _default_rebar_payload_projection_path(source_mgt_path)
    )
    connection_detailing_payload_projection_json_path = (
        _resolve_input_path(args.connection_detailing_payload_projection_json)
        if str(args.connection_detailing_payload_projection_json).strip()
        else _default_connection_detailing_payload_projection_path(source_mgt_path)
    )
    detailing_payload_projection_json_path = (
        _resolve_input_path(args.detailing_payload_projection_json)
        if str(args.detailing_payload_projection_json).strip()
        else _default_detailing_payload_projection_path(source_mgt_path)
    )
    output_mgt_path = Path(args.output_mgt)
    report_out_path = Path(args.report_out)
    patch_manifest_out_path = Path(args.patch_manifest_out)
    instruction_sidecar_out_path = Path(args.instruction_sidecar_out)
    audit_review_manifest_out_path = (
        Path(args.audit_review_manifest_out)
        if str(args.audit_review_manifest_out).strip()
        else _default_audit_review_manifest_path(output_mgt_path)
    )
    audit_review_packet_manifest_out_path = (
        Path(args.audit_review_packet_manifest_out)
        if str(args.audit_review_packet_manifest_out).strip()
        else _default_audit_review_packet_manifest_path(output_mgt_path)
    )
    audit_review_packet_dir_out_path = (
        Path(args.audit_review_packet_dir_out)
        if str(args.audit_review_packet_dir_out).strip()
        else _default_audit_review_packet_dir_path(output_mgt_path)
    )
    audit_review_queue_manifest_out_path = (
        Path(args.audit_review_queue_manifest_out)
        if str(args.audit_review_queue_manifest_out).strip()
        else _default_audit_review_queue_manifest_path(output_mgt_path)
    )
    audit_review_queue_status_dir_out_path = (
        Path(args.audit_review_queue_status_dir_out)
        if str(args.audit_review_queue_status_dir_out).strip()
        else _default_audit_review_queue_status_dir_path(output_mgt_path)
    )
    audit_review_followup_manifest_out_path = (
        Path(args.audit_review_followup_manifest_out)
        if str(args.audit_review_followup_manifest_out).strip()
        else _default_audit_review_followup_manifest_path(output_mgt_path)
    )
    audit_review_resolution_manifest_out_path = (
        Path(args.audit_review_resolution_manifest_out)
        if str(args.audit_review_resolution_manifest_out).strip()
        else _default_audit_review_resolution_manifest_path(output_mgt_path)
    )
    audit_review_resolution_dir_out_path = (
        Path(args.audit_review_resolution_dir_out)
        if str(args.audit_review_resolution_dir_out).strip()
        else _default_audit_review_resolution_dir_path(output_mgt_path)
    )
    loadcomb_preview_out_path = (
        Path(args.loadcomb_preview_out)
        if str(args.loadcomb_preview_out).strip()
        else _default_loadcomb_preview_path(output_mgt_path)
    )
    loadcomb_roundtrip_report_out_path = (
        Path(args.loadcomb_roundtrip_report_out)
        if str(args.loadcomb_roundtrip_report_out).strip()
        else _default_loadcomb_roundtrip_report_path(output_mgt_path)
    )
    source_output_diff_json_out_path = (
        Path(args.source_output_diff_json_out)
        if str(args.source_output_diff_json_out).strip()
        else _default_source_output_mgt_diff_json_path(output_mgt_path)
    )
    source_output_diff_preview_out_path = (
        Path(args.source_output_diff_preview_out)
        if str(args.source_output_diff_preview_out).strip()
        else _default_source_output_mgt_diff_preview_path(output_mgt_path)
    )
    source_output_diff_window_json_out_path = (
        Path(args.source_output_diff_window_json_out)
        if str(args.source_output_diff_window_json_out).strip()
        else _default_source_output_mgt_diff_window_json_path(output_mgt_path)
    )
    source_output_diff_window_preview_out_path = (
        Path(args.source_output_diff_window_preview_out)
        if str(args.source_output_diff_window_preview_out).strip()
        else _default_source_output_mgt_diff_window_preview_path(output_mgt_path)
    )
    section_override_applied_source_json_out_path = (
        Path(args.section_override_applied_source_json_out)
        if str(args.section_override_applied_source_json_out).strip()
        else output_mgt_path.with_suffix(".viewer_section_override_source.json")
        if section_override_patch_json_path is not None
        else None
    )
    loadcomb_override_applied_source_json_out_path = (
        Path(args.loadcomb_override_applied_source_json_out)
        if str(args.loadcomb_override_applied_source_json_out).strip()
        else output_mgt_path.with_suffix(".viewer_loadcomb_override_source.json")
        if loadcomb_override_patch_json_path is not None
        else None
    )

    reason_code = "PASS"
    reason = "bounded MIDAS export completed"
    contract_pass = False

    if not source_mgt_path.exists():
        reason_code = "ERR_SOURCE_MGT_MISSING"
        reason = "source MIDAS MGT file was missing"
    elif not parsed_model_json_path.exists():
        reason_code = "ERR_PARSED_MODEL_MISSING"
        reason = "parsed MIDAS model JSON was missing"
    elif not dataset_npz_path.exists():
        reason_code = "ERR_DATASET_MISSING"
        reason = "design optimization dataset NPZ was missing"
    elif not changes_json_path.exists():
        reason_code = "ERR_CHANGES_MISSING"
        reason = "design optimization changes JSON was missing"
    elif section_override_patch_json_path is not None and not section_override_patch_json_path.exists():
        reason_code = "ERR_SECTION_OVERRIDE_PATCH_MISSING"
        reason = "viewer section override patch JSON was missing"
    elif loadcomb_override_patch_json_path is not None and not loadcomb_override_patch_json_path.exists():
        reason_code = "ERR_LOADCOMB_OVERRIDE_PATCH_MISSING"
        reason = "viewer load combination override patch JSON was missing"

    supported_rows: list[dict[str, Any]] = []
    unsupported_rows: list[dict[str, Any]] = []
    applied_scale_rows: list[dict[str, Any]] = []
    applied_thickness_rows: list[dict[str, Any]] = []
    applied_material_rows: list[dict[str, Any]] = []
    retargeted_element_rows: list[dict[str, Any]] = []
    instruction_sidecar_rows: list[dict[str, Any]] = []
    section_clone_specs: list[dict[str, Any]] = []
    thickness_clone_specs: list[dict[str, Any]] = []
    material_clone_specs: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    derived_group_local_rebar_bridge_rows: list[dict[str, Any]] = []
    parsed_model_payload: dict[str, Any] = {}
    viewer_section_override_patch_present = False
    viewer_section_override_patch_member_count = 0
    viewer_section_override_patch_matched_element_count = 0
    viewer_section_override_patch_resolved_entry_count = 0
    viewer_section_override_patch_unresolved_entry_count = 0
    viewer_section_override_retarget_rows: list[dict[str, Any]] = []
    viewer_loadcomb_override_patch_present = False
    viewer_loadcomb_override_patch_entry_count = 0
    viewer_loadcomb_override_patch_resolved_entry_count = 0
    viewer_loadcomb_override_patch_unresolved_entry_count = 0
    viewer_loadcomb_override_patch_appended_combo_count = 0
    viewer_loadcomb_override_patch_replaced_combo_count = 0
    viewer_loadcomb_override_rows: list[dict[str, Any]] = []
    loadcomb_preview_text = ""
    loadcomb_roundtrip_report: dict[str, Any] = {}
    loadcomb_roundtrip_summary_line = "MIDAS loadcomb-roundtrip: unavailable"
    loadcomb_roundtrip_pass = False
    loadcomb_recovery_mode = ""
    loadcomb_combo_count = 0
    loadcomb_preview_exists = False
    loadcomb_roundtrip_report_exists = False

    if reason_code == "PASS":
        parsed_model_payload = _load_json(parsed_model_json_path)
        if section_override_patch_json_path is not None:
            section_override_patch_payload = _load_json(section_override_patch_json_path)
            if (
                isinstance(section_override_patch_payload, dict)
                and str(section_override_patch_payload.get("patch_mode", "") or "").strip()
                == "working_section_override_patch"
            ):
                viewer_section_override_plan = _build_viewer_section_override_plan(
                    patch_payload=section_override_patch_payload,
                    model_payload=parsed_model_payload,
                )
                parsed_model_payload = _apply_viewer_section_override_plan_to_model_payload(
                    model_payload=parsed_model_payload,
                    plan_rows=list(viewer_section_override_plan.get("rows") or []),
                    patch_path=section_override_patch_json_path,
                )
                if section_override_applied_source_json_out_path is not None:
                    _write_json(section_override_applied_source_json_out_path, parsed_model_payload)
                    parsed_model_json_path = section_override_applied_source_json_out_path
        if loadcomb_override_patch_json_path is not None:
            loadcomb_override_patch_payload = _load_json(loadcomb_override_patch_json_path)
            if (
                isinstance(loadcomb_override_patch_payload, dict)
                and str(loadcomb_override_patch_payload.get("patch_mode", "") or "").strip()
                == "working_loadcomb_override_patch"
            ):
                viewer_loadcomb_override_plan = _build_viewer_loadcomb_override_plan(
                    patch_payload=loadcomb_override_patch_payload,
                    model_payload=parsed_model_payload,
                )
                parsed_model_payload = _apply_viewer_loadcomb_override_plan_to_model_payload(
                    model_payload=parsed_model_payload,
                    plan_rows=list(viewer_loadcomb_override_plan.get("rows") or []),
                    patch_path=loadcomb_override_patch_json_path,
                )
                latest_applied_source_out_path = (
                    loadcomb_override_applied_source_json_out_path
                    or section_override_applied_source_json_out_path
                    or output_mgt_path.with_suffix(".viewer_loadcomb_override_source.json")
                )
                if latest_applied_source_out_path is not None:
                    _write_json(latest_applied_source_out_path, parsed_model_payload)
                    parsed_model_json_path = latest_applied_source_out_path
        viewer_section_override_patch = (
            parsed_model_payload.get("viewer_section_override_patch")
            if isinstance(parsed_model_payload.get("viewer_section_override_patch"), dict)
            else {}
        )
        viewer_section_override_patch_present = bool(viewer_section_override_patch)
        viewer_section_override_patch_member_count = int(
            viewer_section_override_patch.get("patch_member_count", 0)
            or viewer_section_override_patch.get("patch_entry_count", 0)
            or 0
        )
        viewer_section_override_patch_matched_element_count = int(
            viewer_section_override_patch.get("matched_element_count", 0) or 0
        )
        viewer_section_override_patch_resolved_entry_count = int(
            viewer_section_override_patch.get("resolved_entry_count", 0) or 0
        )
        viewer_section_override_patch_unresolved_entry_count = int(
            viewer_section_override_patch.get("unresolved_entry_count", 0) or 0
        )
        viewer_section_override_retarget_map, viewer_section_override_retarget_rows = (
            _collect_viewer_section_override_element_retargets(parsed_model_payload)
        )
        viewer_loadcomb_override_patch = (
            parsed_model_payload.get("viewer_loadcomb_override_patch")
            if isinstance(parsed_model_payload.get("viewer_loadcomb_override_patch"), dict)
            else {}
        )
        viewer_loadcomb_override_patch_present = bool(viewer_loadcomb_override_patch)
        viewer_loadcomb_override_patch_entry_count = int(
            viewer_loadcomb_override_patch.get("patch_entry_count", 0) or 0
        )
        viewer_loadcomb_override_patch_resolved_entry_count = int(
            viewer_loadcomb_override_patch.get("resolved_entry_count", 0) or 0
        )
        viewer_loadcomb_override_patch_unresolved_entry_count = int(
            viewer_loadcomb_override_patch.get("unresolved_entry_count", 0) or 0
        )
        viewer_loadcomb_override_patch_appended_combo_count = int(
            viewer_loadcomb_override_patch.get("appended_combo_count", 0) or 0
        )
        viewer_loadcomb_override_patch_replaced_combo_count = int(
            viewer_loadcomb_override_patch.get("replaced_combo_count", 0) or 0
        )
        viewer_loadcomb_override_rows = [
            row for row in (viewer_loadcomb_override_patch.get("rows") or []) if isinstance(row, dict)
        ]
        changes_payload = _load_json(changes_json_path)
        changes = changes_payload.get("changes") if isinstance(changes_payload.get("changes"), list) else []
        rebar_payload_summary = _load_rebar_payload_summary(
            parsed_model_json_path,
            rebar_payload_projection_path=rebar_payload_projection_json_path,
        )
        connection_detailing_payload_summary = _load_connection_detailing_payload_summary(
            parsed_model_json_path,
            connection_detailing_payload_projection_path=connection_detailing_payload_projection_json_path,
        )
        detailing_payload_summary = _load_detailing_payload_summary(
            parsed_model_json_path,
            detailing_payload_projection_path=detailing_payload_projection_json_path,
        )
        material_rebar_payload_map = _load_material_rebar_payload_map(
            parsed_model_json_path,
            rebar_payload_projection_path=rebar_payload_projection_json_path,
        )
        group_local_rebar_payload_map = _load_group_local_rebar_payload_map(
            parsed_model_json_path,
            rebar_payload_projection_path=rebar_payload_projection_json_path,
        )
        group_local_connection_detailing_payload_map = _load_group_local_connection_detailing_payload_map(
            parsed_model_json_path,
            connection_detailing_payload_projection_path=connection_detailing_payload_projection_json_path,
        )
        group_local_detailing_payload_map = _load_group_local_detailing_payload_map(
            parsed_model_json_path,
            detailing_payload_projection_path=detailing_payload_projection_json_path,
        )
        try:
            loadcomb_preview_text = export_midas_loadcomb_from_model_payload(parsed_model_payload)
        except Exception:
            loadcomb_preview_text = ""
        if loadcomb_preview_text.strip():
            loadcomb_preview_out_path.parent.mkdir(parents=True, exist_ok=True)
            loadcomb_preview_out_path.write_text(loadcomb_preview_text, encoding="utf-8")
            loadcomb_preview_exists = bool(loadcomb_preview_out_path.exists())
            try:
                loadcomb_roundtrip_report = build_roundtrip_report(
                    model_payload=parsed_model_payload,
                    source_path=str(parsed_model_json_path),
                    export_text=loadcomb_preview_text,
                )
            except Exception:
                loadcomb_roundtrip_report = {}
            if loadcomb_roundtrip_report:
                _write_json(loadcomb_roundtrip_report_out_path, loadcomb_roundtrip_report)
                loadcomb_roundtrip_report_exists = bool(loadcomb_roundtrip_report_out_path.exists())
                loadcomb_roundtrip_pass = bool(loadcomb_roundtrip_report.get("pass", False))
                loadcomb_recovery_mode = str(loadcomb_roundtrip_report.get("recovery_mode", "") or "")
                loadcomb_combo_count = int(loadcomb_roundtrip_report.get("raw_combo_count", 0) or 0)
                coverage_preview = f"{float(loadcomb_roundtrip_report.get('exact_entry_row_coverage', 0.0) or 0.0):.2f}"
                loadcomb_roundtrip_summary_line = (
                    f"MGT export LOADCOMB roundtrip: {'ok' if loadcomb_roundtrip_pass else 'check'}"
                    f" | entry_row_coverage={coverage_preview}"
                    f" | combos={loadcomb_combo_count}"
                    f"{f' | recovery={loadcomb_recovery_mode}' if loadcomb_recovery_mode else ''}"
                )
        group_to_elements = _load_group_element_map(dataset_npz_path)
        element_map, section_signature_to_ids = _build_model_maps(parsed_model_json_path)
        max_section_id, max_thickness_id, max_material_id = _model_id_bounds(parsed_model_json_path)
        next_section_id = int(max_section_id) + 1
        next_thickness_id = int(max_thickness_id) + 1
        next_material_id = int(max_material_id) + 1
        derived_group_local_rebar_bridge_rows = _derive_group_local_rebar_bridge_rows(
            changes=changes,
            group_to_elements=group_to_elements,
            element_map=element_map,
            material_rebar_payload_map=material_rebar_payload_map,
            group_local_rebar_payload_map=group_local_rebar_payload_map,
        )
        derived_group_local_connection_detailing_bridge_rows = _derive_group_local_connection_detailing_bridge_rows(
            changes=changes,
            group_to_elements=group_to_elements,
            element_map=element_map,
            material_rebar_payload_map=material_rebar_payload_map,
            group_local_connection_detailing_payload_map=group_local_connection_detailing_payload_map,
        )
        derived_group_local_detailing_bridge_rows = _derive_group_local_detailing_bridge_rows(
            changes=changes,
            group_to_elements=group_to_elements,
            element_map=element_map,
            material_rebar_payload_map=material_rebar_payload_map,
            group_local_detailing_payload_map=group_local_detailing_payload_map,
        )
        rebar_bridge_rows_by_key = {
            (str(row.get("group_id", "")), str(row.get("action_family", ""))): row
            for row in derived_group_local_rebar_bridge_rows
            if isinstance(row, dict)
        }
        connection_detailing_bridge_rows_by_key = {
            (str(row.get("group_id", "")), str(row.get("action_family", ""))): row
            for row in derived_group_local_connection_detailing_bridge_rows
            if isinstance(row, dict)
        }
        detailing_bridge_rows_by_key = {
            (str(row.get("group_id", "")), str(row.get("action_family", ""))): row
            for row in derived_group_local_detailing_bridge_rows
            if isinstance(row, dict)
        }

        candidate_rows: list[dict[str, Any]] = []
        section_ratio_requests: dict[tuple[str, int], set[float]] = defaultdict(set)
        direct_patch_supported_families = (
            "beam_section",
            "wall_thickness",
            "slab_thickness",
            "rebar",
            "perimeter_frame",
            "connection_detailing",
            "detailing",
        )
        sidecar_supported_families = {"detailing", "connection_detailing", "rebar", "perimeter_frame"}
        element_material_retarget_map: dict[int, int] = {}
        for row in changes:
            if not isinstance(row, dict):
                continue
            family = _infer_action_family(row)
            member_type = str(row.get("member_type", "") or "").strip().lower()
            before = _as_float(row.get("before_thickness_scale"))
            after = _as_float(row.get("after_thickness_scale"))
            before_detailing = _as_float(row.get("before_detailing_quality"))
            after_detailing = _as_float(row.get("after_detailing_quality"))
            before_rebar = _as_float(row.get("before_rebar_ratio"))
            after_rebar = _as_float(row.get("after_rebar_ratio"))
            if family in sidecar_supported_families:
                if family in {"detailing", "connection_detailing"}:
                    if (
                        before_detailing is None
                        or after_detailing is None
                        or abs(float(after_detailing) - float(before_detailing)) <= 1.0e-12
                    ):
                        unsupported_rows.append(
                            {
                                "group_id": str(row.get("group_id", "")),
                                "member_type": member_type,
                                "action_family": family,
                                "reason": "invalid_detailing_delta",
                            }
                        )
                        continue
                elif family in {"rebar", "perimeter_frame"}:
                    if (
                        before_rebar is None
                        or after_rebar is None
                        or abs(float(after_rebar) - float(before_rebar)) <= 1.0e-12
                    ):
                        unsupported_rows.append(
                            {
                                "group_id": str(row.get("group_id", "")),
                                "member_type": member_type,
                                "action_family": family,
                                "reason": "invalid_rebar_delta",
                            }
                        )
                        continue
                    bridge_row = rebar_bridge_rows_by_key.get((str(row.get("group_id", "")), family), {})
                    if isinstance(bridge_row, dict) and bool(bridge_row.get("direct_patch_eligible", False)):
                        payload = bridge_row.get("group_local_payload") if isinstance(bridge_row.get("group_local_payload"), dict) else {}
                        material_ids = [int(v) for v in list(bridge_row.get("material_ids", [])) if _as_int(v) is not None]
                        element_ids = _load_group_element_ids(row=row, group_to_elements=group_to_elements)
                        if payload and material_ids and element_ids:
                            clone_rows: list[dict[str, Any]] = []
                            target_material_ids: list[int] = []
                            per_source_material_new_id: dict[int, int] = {}
                            element_material_retarget_rows: dict[int, int] = {}
                            for material_id in material_ids:
                                new_material_id = int(next_material_id)
                                next_material_id += 1
                                per_source_material_new_id[int(material_id)] = int(new_material_id)
                                material_clone_specs.append(
                                    {
                                        "source_id": int(material_id),
                                        "new_id": int(new_material_id),
                                        "payload": dict(payload),
                                        "group_id": str(row.get("group_id", "")),
                                        "action_family": family,
                                    }
                                )
                                clone_rows.append({"source_id": int(material_id), "new_id": int(new_material_id)})
                                target_material_ids.append(int(new_material_id))
                            for eid in element_ids:
                                elem = element_map.get(int(eid))
                                source_material_id = _as_int(elem.get("material_id")) if isinstance(elem, dict) else None
                                if source_material_id is None:
                                    continue
                                new_material_id = per_source_material_new_id.get(int(source_material_id))
                                if new_material_id is not None:
                                    element_material_retarget_rows[int(eid)] = int(new_material_id)
                            if element_material_retarget_rows:
                                candidate = {
                                    "group_id": str(row.get("group_id", "")),
                                    "member_type": member_type,
                                    "action_family": family,
                                    "action_name": str(row.get("action_name", "") or ""),
                                    "zone_label": str(row.get("zone_label", "") or ""),
                                    "story_band": _as_int(row.get("story_band")) or 0,
                                    "semantic_group": str(row.get("semantic_group", "") or ""),
                                    "ratio": float(after_rebar) / float(before_rebar),
                                    "element_ids": [int(v) for v in element_ids],
                                    "target_material_ids": [int(v) for v in target_material_ids],
                                    "before_rebar_ratio": float(before_rebar),
                                    "after_rebar_ratio": float(after_rebar),
                                    "payload_source_class": str(bridge_row.get("payload_source_class", "") or ""),
                                    "payload_mapping_source": str(bridge_row.get("group_local_payload_mapping_source", "") or ""),
                                    "clone_rows": clone_rows,
                                }
                                supported_rows.append(candidate)
                                element_map.update(
                                    {
                                        int(eid): {
                                            **dict(element_map.get(int(eid), {})),
                                            "material_id": int(mid),
                                        }
                                        for eid, mid in element_material_retarget_rows.items()
                                    }
                                )
                                element_material_retarget_map.update(element_material_retarget_rows)
                                continue
                instruction_kind = "detailing_followup"
                followup_type = "detailing_manual_review"
                review_priority = "medium"
                structured_payload: dict[str, Any] = {}
                structured_payload_mapping_source = ""
                direct_patch_applied = False
                direct_patch_kind = ""
                direct_patch_target_material_ids: list[int] = []
                direct_patch_clone_rows: list[dict[str, Any]] = []
                if family == "connection_detailing":
                    connection_payload, connection_payload_mapping_source = _resolve_group_local_connection_detailing_payload_with_source(
                        row=row,
                        group_local_connection_detailing_payload_map=group_local_connection_detailing_payload_map,
                    )
                    structured_payload = dict(connection_payload)
                    structured_payload_mapping_source = str(connection_payload_mapping_source)
                    bridge_row = connection_detailing_bridge_rows_by_key.get((str(row.get("group_id", "")), family), {})
                    if isinstance(bridge_row, dict) and bool(bridge_row.get("direct_patch_eligible", False)):
                        payload = bridge_row.get("material_payload") if isinstance(bridge_row.get("material_payload"), dict) else {}
                        material_ids = [int(v) for v in list(bridge_row.get("material_ids", [])) if _as_int(v) is not None]
                        element_ids = [int(v) for v in list(bridge_row.get("element_ids", [])) if _as_int(v) is not None]
                        if not element_ids:
                            element_ids = _load_group_element_ids(row=row, group_to_elements=group_to_elements)
                        if payload and material_ids and element_ids:
                            clone_rows: list[dict[str, Any]] = []
                            target_material_ids: list[int] = []
                            per_source_material_new_id: dict[int, int] = {}
                            element_material_retarget_rows: dict[int, int] = {}
                            for material_id in material_ids:
                                new_material_id = int(next_material_id)
                                next_material_id += 1
                                per_source_material_new_id[int(material_id)] = int(new_material_id)
                                material_clone_specs.append(
                                    {
                                        "source_id": int(material_id),
                                        "new_id": int(new_material_id),
                                        "payload": dict(payload),
                                        "group_id": str(row.get("group_id", "")),
                                        "action_family": family,
                                        "payload_source_class": str(bridge_row.get("material_payload_source_class", "") or ""),
                                    }
                                )
                                clone_rows.append({"source_id": int(material_id), "new_id": int(new_material_id)})
                                target_material_ids.append(int(new_material_id))
                            for eid in element_ids:
                                elem = element_map.get(int(eid))
                                source_material_id = _as_int(elem.get("material_id")) if isinstance(elem, dict) else None
                                if source_material_id is None:
                                    continue
                                new_material_id = per_source_material_new_id.get(int(source_material_id))
                                if new_material_id is not None:
                                    element_material_retarget_rows[int(eid)] = int(new_material_id)
                            if element_material_retarget_rows:
                                candidate = {
                                    "group_id": str(row.get("group_id", "")),
                                    "member_type": member_type,
                                    "action_family": family,
                                    "action_name": str(row.get("action_name", "") or ""),
                                    "zone_label": str(row.get("zone_label", "") or ""),
                                    "story_band": _as_int(row.get("story_band")) or 0,
                                    "semantic_group": str(row.get("semantic_group", "") or ""),
                                    "ratio": 1.0,
                                    "element_ids": [int(v) for v in element_ids],
                                    "target_material_ids": [int(v) for v in target_material_ids],
                                    "before_rebar_ratio": float(before_rebar) if before_rebar is not None else None,
                                    "after_rebar_ratio": float(after_rebar) if after_rebar is not None else None,
                                    "before_detailing_quality": float(before_detailing) if before_detailing is not None else None,
                                    "after_detailing_quality": float(after_detailing) if after_detailing is not None else None,
                                    "payload_source_class": str(bridge_row.get("material_payload_source_class", "") or ""),
                                    "payload_mapping_source": str(bridge_row.get("structured_payload_mapping_source", "") or ""),
                                    "direct_patch_kind": "connection_detailing_material_metadata",
                                    "clone_rows": clone_rows,
                                }
                                supported_rows.append(candidate)
                                element_map.update(
                                    {
                                        int(eid): {
                                            **dict(element_map.get(int(eid), {})),
                                            "material_id": int(mid),
                                        }
                                        for eid, mid in element_material_retarget_rows.items()
                                    }
                                )
                                element_material_retarget_map.update(element_material_retarget_rows)
                                direct_patch_applied = True
                                direct_patch_kind = "connection_detailing_material_metadata"
                                direct_patch_target_material_ids = [int(v) for v in target_material_ids]
                                direct_patch_clone_rows = clone_rows
                    instruction_kind = "connection_detailing_followup"
                    followup_type = (
                        "connection_detailing_audit_after_material_patch"
                        if direct_patch_applied
                        else "connection_detailing_manual_update"
                    )
                    review_priority = "high"
                elif family == "detailing":
                    detailing_payload, detailing_payload_mapping_source = _resolve_group_local_detailing_payload_with_source(
                        row=row,
                        group_local_detailing_payload_map=group_local_detailing_payload_map,
                    )
                    structured_payload = dict(detailing_payload)
                    structured_payload_mapping_source = str(detailing_payload_mapping_source)
                    bridge_row = detailing_bridge_rows_by_key.get((str(row.get("group_id", "")), family), {})
                    if isinstance(bridge_row, dict) and bool(bridge_row.get("direct_patch_eligible", False)):
                        material_ids = [int(v) for v in list(bridge_row.get("material_ids", [])) if _as_int(v) is not None]
                        element_ids = [int(v) for v in list(bridge_row.get("element_ids", [])) if _as_int(v) is not None]
                        payload_rows_by_material_id = (
                            bridge_row.get("material_payload_rows_by_material_id")
                            if isinstance(bridge_row.get("material_payload_rows_by_material_id"), dict)
                            else {}
                        )
                        if not element_ids:
                            element_ids = _load_group_element_ids(row=row, group_to_elements=group_to_elements)
                        if payload_rows_by_material_id and material_ids and element_ids:
                            clone_rows: list[dict[str, Any]] = []
                            target_material_ids: list[int] = []
                            per_source_material_new_id: dict[int, int] = {}
                            element_material_retarget_rows: dict[int, int] = {}
                            for material_id in material_ids:
                                payload = (
                                    payload_rows_by_material_id.get(str(material_id))
                                    if isinstance(payload_rows_by_material_id.get(str(material_id)), dict)
                                    else payload_rows_by_material_id.get(int(material_id), {})
                                )
                                if not isinstance(payload, dict) or not bool(payload.get("payload_present", False)):
                                    continue
                                new_material_id = int(next_material_id)
                                next_material_id += 1
                                per_source_material_new_id[int(material_id)] = int(new_material_id)
                                material_clone_specs.append(
                                    {
                                        "source_id": int(material_id),
                                        "new_id": int(new_material_id),
                                        "payload": dict(payload),
                                        "group_id": str(row.get("group_id", "")),
                                        "action_family": family,
                                        "payload_source_class": str(bridge_row.get("material_payload_source_class", "") or ""),
                                    }
                                )
                                clone_rows.append({"source_id": int(material_id), "new_id": int(new_material_id)})
                                target_material_ids.append(int(new_material_id))
                            for eid in element_ids:
                                elem = element_map.get(int(eid))
                                source_material_id = _as_int(elem.get("material_id")) if isinstance(elem, dict) else None
                                if source_material_id is None:
                                    continue
                                new_material_id = per_source_material_new_id.get(int(source_material_id))
                                if new_material_id is not None:
                                    element_material_retarget_rows[int(eid)] = int(new_material_id)
                            if element_material_retarget_rows:
                                candidate = {
                                    "group_id": str(row.get("group_id", "")),
                                    "member_type": member_type,
                                    "action_family": family,
                                    "action_name": str(row.get("action_name", "") or ""),
                                    "zone_label": str(row.get("zone_label", "") or ""),
                                    "story_band": _as_int(row.get("story_band")) or 0,
                                    "semantic_group": str(row.get("semantic_group", "") or ""),
                                    "ratio": 1.0,
                                    "element_ids": [int(v) for v in element_ids],
                                    "target_material_ids": [int(v) for v in target_material_ids],
                                    "before_rebar_ratio": float(before_rebar) if before_rebar is not None else None,
                                    "after_rebar_ratio": float(after_rebar) if after_rebar is not None else None,
                                    "before_detailing_quality": float(before_detailing) if before_detailing is not None else None,
                                    "after_detailing_quality": float(after_detailing) if after_detailing is not None else None,
                                    "payload_source_class": str(bridge_row.get("material_payload_source_class", "") or ""),
                                    "payload_mapping_source": str(bridge_row.get("structured_payload_mapping_source", "") or ""),
                                    "direct_patch_kind": "detailing_material_metadata",
                                    "clone_rows": clone_rows,
                                }
                                supported_rows.append(candidate)
                                element_map.update(
                                    {
                                        int(eid): {
                                            **dict(element_map.get(int(eid), {})),
                                            "material_id": int(mid),
                                        }
                                        for eid, mid in element_material_retarget_rows.items()
                                    }
                                )
                                element_material_retarget_map.update(element_material_retarget_rows)
                                direct_patch_applied = True
                                direct_patch_kind = "detailing_material_metadata"
                                direct_patch_target_material_ids = [int(v) for v in target_material_ids]
                                direct_patch_clone_rows = clone_rows
                    if direct_patch_applied:
                        followup_type = "detailing_audit_after_material_patch"
                elif family == "rebar":
                    instruction_kind = "rebar_followup"
                    followup_type = "rebar_manual_update"
                    review_priority = "high" if member_type in {"wall", "column"} else "medium"
                elif family == "perimeter_frame":
                    instruction_kind = "perimeter_frame_followup"
                    followup_type = "perimeter_frame_manual_update"
                    review_priority = "high"
                sidecar_element_ids = _load_group_element_ids(row=row, group_to_elements=group_to_elements)
                if family == "connection_detailing":
                    bridge_row = connection_detailing_bridge_rows_by_key.get((str(row.get("group_id", "")), family), {})
                    if isinstance(bridge_row, dict):
                        bridge_element_ids = [int(v) for v in list(bridge_row.get("element_ids", [])) if _as_int(v) is not None]
                        if bridge_element_ids:
                            sidecar_element_ids = bridge_element_ids
                elif family == "detailing":
                    bridge_row = detailing_bridge_rows_by_key.get((str(row.get("group_id", "")), family), {})
                    if isinstance(bridge_row, dict):
                        bridge_element_ids = [int(v) for v in list(bridge_row.get("element_ids", [])) if _as_int(v) is not None]
                        if bridge_element_ids:
                            sidecar_element_ids = bridge_element_ids
                instruction_sidecar_rows.append(
                    {
                        "group_id": str(row.get("group_id", "")),
                        "member_type": member_type,
                        "action_family": family,
                        "action_name": str(row.get("action_name", "") or ""),
                        "before_rebar_ratio": float(before_rebar) if before_rebar is not None else None,
                        "after_rebar_ratio": float(after_rebar) if after_rebar is not None else None,
                        "before_detailing_quality": float(before_detailing) if before_detailing is not None else None,
                        "after_detailing_quality": float(after_detailing) if after_detailing is not None else None,
                        "instruction_kind": instruction_kind,
                        "followup_type": followup_type,
                        "review_priority": review_priority,
                        "review_owner": "licensed_engineer",
                        "review_required": True,
                        "element_ids": sidecar_element_ids,
                        "zone_label": str(row.get("zone_label", "") or ""),
                        "story_band": _as_int(row.get("story_band")) or 0,
                        "semantic_group": str(row.get("semantic_group", "") or ""),
                        "structured_payload_present": bool(structured_payload.get("payload_present", False)),
                        "structured_payload_group_id": str(structured_payload.get("group_id", "") or ""),
                        "structured_payload_mapping_source": str(structured_payload_mapping_source),
                        "structured_payload_source_class": str(structured_payload.get("payload_source_class", "") or ""),
                        "structured_payload_section_ids": [
                            int(v)
                            for v in (
                                list(structured_payload.get("section_ids", []))
                                if isinstance(structured_payload.get("section_ids"), list)
                                else []
                            )
                            if _as_int(v) is not None
                        ],
                        "structured_payload_material_ids": [
                            int(v)
                            for v in (
                                list(structured_payload.get("material_ids", []))
                                if isinstance(structured_payload.get("material_ids"), list)
                                else []
                            )
                            if _as_int(v) is not None
                        ],
                        "structured_payload": dict(structured_payload)
                        if bool(structured_payload.get("payload_present", False))
                        else {},
                        "direct_patch_applied": bool(direct_patch_applied),
                        "direct_patch_kind": str(direct_patch_kind),
                        "direct_patch_target_material_ids": [int(v) for v in direct_patch_target_material_ids],
                        "direct_patch_clone_rows": direct_patch_clone_rows,
                    }
                )
                continue
            if family not in direct_patch_supported_families:
                unsupported_rows.append(
                    {
                        "group_id": str(row.get("group_id", "")),
                        "member_type": member_type,
                        "action_family": family or "unknown",
                        "reason": "unsupported_action_family",
                    }
                )
                continue
            if before is None or after is None or before <= 1.0e-12:
                unsupported_rows.append(
                    {
                        "group_id": str(row.get("group_id", "")),
                        "member_type": member_type,
                        "action_family": family,
                        "reason": "invalid_scale_delta",
                    }
                )
                continue
            ratio = float(after) / float(before)
            element_ids = _load_group_element_ids(row=row, group_to_elements=group_to_elements)
            section_ids = _resolve_section_ids_for_change(
                row=row,
                action_family=family,
                group_to_elements=group_to_elements,
                element_map=element_map,
                section_signature_to_ids=section_signature_to_ids,
            )
            if not section_ids:
                unsupported_rows.append(
                    {
                        "group_id": str(row.get("group_id", "")),
                        "member_type": member_type,
                        "action_family": family,
                        "reason": "unmapped_group_to_section_ids",
                    }
                )
                continue
            candidate = {
                "group_id": str(row.get("group_id", "")),
                "member_type": member_type,
                "action_family": family,
                "zone_label": str(row.get("zone_label", "") or ""),
                "story_band": _as_int(row.get("story_band")) or 0,
                "semantic_group": str(row.get("semantic_group", "") or ""),
                "ratio": float(ratio),
                "element_ids": [int(v) for v in element_ids],
                "section_ids": [int(v) for v in section_ids],
                "before_thickness_scale": float(before),
                "after_thickness_scale": float(after),
            }
            candidate_rows.append(candidate)
            bucket_name = "SECT-SCALE" if family == "beam_section" else "THICKNESS"
            for sec_id in section_ids:
                section_ratio_requests[(bucket_name, int(sec_id))].add(round(float(ratio), 10))

        section_scale_patches: dict[int, float] = {}
        thickness_patches: dict[int, float] = {}
        element_retarget_map: dict[int, int] = dict(viewer_section_override_retarget_map)
        for candidate in candidate_rows:
            bucket_name = "SECT-SCALE" if str(candidate["action_family"]) == "beam_section" else "THICKNESS"
            conflicts = {
                int(sid): len(section_ratio_requests[(bucket_name, int(sid))]) > 1
                for sid in candidate["section_ids"]
            }
            if any(conflicts.values()) and not candidate["element_ids"]:
                unsupported_rows.append(
                    {
                        "group_id": str(candidate["group_id"]),
                        "member_type": str(candidate["member_type"]),
                        "action_family": str(candidate["action_family"]),
                        "reason": "shared_section_conflict_without_element_mapping",
                        "conflict_section_ids": [int(v) for v, blocked in conflicts.items() if blocked],
                    }
                )
                continue
            target_property_ids: list[int] = []
            clone_rows: list[dict[str, Any]] = []
            for sid in candidate["section_ids"]:
                sid = int(sid)
                if conflicts.get(sid, False):
                    if bucket_name == "SECT-SCALE":
                        new_id = int(next_section_id)
                        next_section_id += 1
                        section_clone_specs.append(
                            {
                                "source_id": int(sid),
                                "new_id": int(new_id),
                                "ratio": float(candidate["ratio"]),
                                "group_id": str(candidate["group_id"]),
                            }
                        )
                    else:
                        new_id = int(next_thickness_id)
                        next_thickness_id += 1
                        thickness_clone_specs.append(
                            {
                                "source_id": int(sid),
                                "new_id": int(new_id),
                                "ratio": float(candidate["ratio"]),
                                "group_id": str(candidate["group_id"]),
                            }
                        )
                    for eid in candidate["element_ids"]:
                        elem = element_map.get(int(eid))
                        if isinstance(elem, dict) and int(elem.get("section_id", -1)) == int(sid):
                            element_retarget_map[int(eid)] = int(new_id)
                    target_property_ids.append(int(new_id))
                    clone_rows.append({"source_id": int(sid), "new_id": int(new_id)})
                else:
                    target_property_ids.append(int(sid))
            if not target_property_ids:
                unsupported_rows.append(
                    {
                        "group_id": str(candidate["group_id"]),
                        "member_type": str(candidate["member_type"]),
                        "action_family": str(candidate["action_family"]),
                        "reason": "unmapped_group_to_section_ids",
                    }
                )
                continue
            supported_rows.append({**candidate, "target_property_ids": [int(v) for v in target_property_ids], "clone_rows": clone_rows})
            for sid in target_property_ids:
                if bucket_name == "SECT-SCALE":
                    section_scale_patches[int(sid)] = float(candidate["ratio"])
                else:
                    thickness_patches[int(sid)] = float(candidate["ratio"])

        if (
            not section_scale_patches
            and not thickness_patches
            and not material_clone_specs
            and not element_retarget_map
            and not instruction_sidecar_rows
        ):
            if viewer_loadcomb_override_patch_present and loadcomb_preview_text.strip():
                output_mgt_path.parent.mkdir(parents=True, exist_ok=True)
                output_mgt_path.write_text(
                    source_mgt_path.read_text(encoding="utf-8", errors="ignore"),
                    encoding="utf-8",
                )
                contract_pass = bool(output_mgt_path.exists() and loadcomb_preview_exists)
                if not contract_pass:
                    reason_code = "ERR_EXPORT_WRITE_FAILED"
                    reason = "loadcomb authoring preview was generated, but the bounded MIDAS export copy was not written"
            else:
                reason_code = "ERR_NO_SUPPORTED_EXPORT_PATCHES"
                reason = "no exportable beam_section, wall/slab thickness, viewer section override, or loadcomb authoring patches were resolved"
        else:
            if (
                section_scale_patches
                or thickness_patches
                or material_clone_specs
                or element_retarget_map
                or element_material_retarget_map
            ):
                applied_scale_rows, applied_thickness_rows, applied_material_rows, retargeted_element_rows = _apply_mgt_patches(
                    source_mgt_path=source_mgt_path,
                    output_mgt_path=output_mgt_path,
                    section_scale_patches=section_scale_patches,
                    thickness_patches=thickness_patches,
                    section_clone_specs=section_clone_specs,
                    thickness_clone_specs=thickness_clone_specs,
                    element_retarget_map=element_retarget_map,
                    material_clone_specs=material_clone_specs,
                    element_material_retarget_map=element_material_retarget_map,
                )
            else:
                output_mgt_path.parent.mkdir(parents=True, exist_ok=True)
                output_mgt_path.write_text(source_mgt_path.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            viewer_section_override_rows_by_element_id = {
                int(row["element_id"]): row
                for row in viewer_section_override_retarget_rows
                if _as_int(row.get("element_id")) is not None
            }
            enriched_retargeted_rows: list[dict[str, Any]] = []
            for row in retargeted_element_rows:
                enriched = dict(row)
                element_id = _as_int(row.get("element_id"))
                new_property_id = _as_int(row.get("new_property_id"))
                viewer_row = (
                    viewer_section_override_rows_by_element_id.get(int(element_id))
                    if element_id is not None
                    else None
                )
                if (
                    isinstance(viewer_row, dict)
                    and new_property_id is not None
                    and new_property_id == _as_int(viewer_row.get("resolved_section_id"))
                ):
                    enriched.update(
                        {
                            "retarget_source": "viewer_section_override_patch",
                            "member_id": str(viewer_row.get("member_id", "") or ""),
                            "target_section": str(viewer_row.get("target_section", "") or ""),
                            "previous_section_id": _as_int(viewer_row.get("previous_section_id")),
                            "resolved_section_id": _as_int(viewer_row.get("resolved_section_id")),
                            "resolved_section_name": str(viewer_row.get("resolved_section_name", "") or ""),
                            "draft_note": str(viewer_row.get("draft_note", "") or ""),
                            "viewer_patch_applied_at": str(viewer_row.get("applied_at", "") or ""),
                        }
                    )
                enriched_retargeted_rows.append(enriched)
            retargeted_element_rows = enriched_retargeted_rows
            contract_pass = bool(
                output_mgt_path.exists()
                and (
                    applied_scale_rows
                    or applied_thickness_rows
                    or applied_material_rows
                    or retargeted_element_rows
                    or instruction_sidecar_rows
                )
            )
            if not contract_pass:
                reason_code = "ERR_EXPORT_WRITE_FAILED"
                reason = "optimized MIDAS MGT was not written with any supported patch rows"
    else:
        rebar_payload_summary = {
            "material_level_rebar_payload_row_count": 0,
            "material_level_rebar_payload_available_count": 0,
            "group_local_rebar_payload_row_count": 0,
            "group_local_rebar_payload_available_count": 0,
            "group_local_rebar_payload_group_ids": set(),
        }
        connection_detailing_payload_summary = {
            "group_local_connection_detailing_payload_row_count": 0,
            "group_local_connection_detailing_payload_available_count": 0,
            "connection_detailing_payload_namespace_mode": "none",
            "connection_detailing_payload_group_local_namespace_present": False,
            "group_local_connection_detailing_payload_group_ids": set(),
        }
        detailing_payload_summary = {
            "group_local_detailing_payload_row_count": 0,
            "group_local_detailing_payload_available_count": 0,
            "detailing_payload_namespace_mode": "none",
            "detailing_payload_group_local_namespace_present": False,
            "group_local_detailing_payload_group_ids": set(),
        }
        material_rebar_payload_map = {}
        derived_group_local_connection_detailing_bridge_rows = []
        derived_group_local_detailing_bridge_rows = []

    supported_rows = [_annotate_special_member_family(row) for row in supported_rows]
    instruction_sidecar_reference_rows = [_annotate_special_member_family(row) for row in instruction_sidecar_rows]
    for row in instruction_sidecar_reference_rows:
        if not _is_instruction_sidecar_zero_touch_verified(row):
            continue
        family = str(row.get("action_family", "") or "").strip() or "instruction"
        row["zero_touch_verified"] = True
        row["review_required"] = False
        row["review_owner"] = "none"
        row["queue_status"] = "zero_touch_verified"
        row["followup_status"] = "closed_zero_touch_verified"
        row["audit_status"] = "closed_zero_touch_verified"
        row["followup_type"] = f"{family}_zero_touch_verified"
        row["zero_touch_verification_reason"] = (
            "direct_patch_material_metadata_with_structured_payload_and_complete_internal_mapping"
        )
    instruction_sidecar_zero_touch_rows = [
        row for row in instruction_sidecar_reference_rows if _is_instruction_sidecar_zero_touch_verified(row)
    ]
    instruction_sidecar_audit_only_rows = [
        row for row in instruction_sidecar_reference_rows if _is_instruction_sidecar_audit_only(row)
    ]
    instruction_sidecar_manual_input_rows = [
        row for row in instruction_sidecar_reference_rows if _is_instruction_sidecar_manual_input(row)
    ]
    instruction_sidecar_rows = instruction_sidecar_manual_input_rows
    unsupported_reason_counts = {
        str(k): int(v) for k, v in sorted(Counter(str(row.get("reason", "")) for row in unsupported_rows).items())
    }
    supported_rows_all = [*supported_rows, *instruction_sidecar_reference_rows]
    direct_patch_action_family_counts = {
        str(k): int(v) for k, v in sorted(Counter(str(row.get("action_family", "")) for row in supported_rows).items())
    }
    supported_action_family_counts = {str(k): int(v) for k, v in sorted(Counter(str(row.get("action_family", "")) for row in supported_rows_all).items())}
    special_member_direct_patch_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(str(row.get("special_member_family", "")) for row in supported_rows if str(row.get("special_member_family", "")).strip()).items()
        )
    }
    special_member_supported_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(
                str(row.get("special_member_family", ""))
                for row in supported_rows_all
                if str(row.get("special_member_family", "")).strip()
            ).items()
        )
    }
    instruction_sidecar_action_family_counts = {
        str(k): int(v) for k, v in sorted(Counter(str(row.get("action_family", "")) for row in instruction_sidecar_rows).items())
    }
    special_member_instruction_sidecar_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(
                str(row.get("special_member_family", ""))
                for row in instruction_sidecar_rows
                if str(row.get("special_member_family", "")).strip()
            ).items()
        )
    }
    instruction_sidecar_review_priority_counts = {
        str(k): int(v) for k, v in sorted(Counter(str(row.get("review_priority", "")) for row in instruction_sidecar_rows).items())
    }
    instruction_sidecar_followup_type_counts = {
        str(k): int(v) for k, v in sorted(Counter(str(row.get("followup_type", "")) for row in instruction_sidecar_rows).items())
    }
    instruction_sidecar_audit_only_change_count = int(len(instruction_sidecar_audit_only_rows))
    instruction_sidecar_manual_input_change_count = int(len(instruction_sidecar_manual_input_rows))
    instruction_sidecar_zero_touch_verified_change_count = int(len(instruction_sidecar_zero_touch_rows))
    instruction_sidecar_audit_only_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(str(row.get("action_family", "")) for row in instruction_sidecar_audit_only_rows).items()
        )
    }
    instruction_sidecar_zero_touch_verified_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(str(row.get("action_family", "")) for row in instruction_sidecar_zero_touch_rows).items()
        )
    }
    special_member_instruction_sidecar_zero_touch_verified_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(
                str(row.get("special_member_family", ""))
                for row in instruction_sidecar_zero_touch_rows
                if str(row.get("special_member_family", "")).strip()
            ).items()
        )
    }
    instruction_sidecar_manual_input_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(str(row.get("action_family", "")) for row in instruction_sidecar_manual_input_rows).items()
        )
    }
    audit_review_packets = _build_audit_review_packets(instruction_sidecar_audit_only_rows)
    audit_review_packet_count = int(len(audit_review_packets))
    audit_review_packet_files = _write_audit_review_packet_files(
        audit_review_packet_dir_out_path,
        audit_review_packets,
        instruction_sidecar_audit_only_rows,
    )
    audit_review_packet_file_count = int(len(audit_review_packet_files))
    audit_review_queue_items = _write_audit_review_queue_status_files(
        audit_review_queue_status_dir_out_path,
        audit_review_packet_files,
    )
    audit_review_queue_item_count = int(len(audit_review_queue_items))
    audit_review_packet_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("action_family", "") or "") for row in audit_review_packets).items())
        if str(k)
    }
    audit_review_packet_followup_type_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("followup_type", "") or "") for row in audit_review_packets).items())
        if str(k)
    }
    audit_review_packet_review_priority_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("review_priority", "") or "") for row in audit_review_packets).items())
        if str(k)
    }
    audit_review_packet_file_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("action_family", "") or "") for row in audit_review_packet_files).items())
        if str(k)
    }
    audit_review_queue_status_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("queue_status", "") or "") for row in audit_review_queue_items).items())
        if str(k)
    }
    audit_review_queue_action_family_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("action_family", "") or "") for row in audit_review_queue_items).items())
        if str(k)
    }
    audit_review_queue_pending_count = int(
        sum(1 for row in audit_review_queue_items if str(row.get("queue_status", "")) == "pending_review")
    )
    audit_review_queue_acknowledged_count = int(
        sum(1 for row in audit_review_queue_items if bool(row.get("acknowledged", False)))
    )
    connection_detailing_direct_patch_eligible_change_count = int(
        sum(1 for row in supported_rows if str(row.get("action_family", "")) == "connection_detailing")
    )
    detailing_direct_patch_eligible_change_count = int(
        sum(1 for row in supported_rows if str(row.get("action_family", "")) == "detailing")
    )
    connection_detailing_structured_payload_mapped_change_count = int(
        sum(
            1
            for row in instruction_sidecar_reference_rows
            if str(row.get("action_family", "")) == "connection_detailing" and bool(row.get("structured_payload_present", False))
        )
    )
    connection_detailing_zero_touch_verified_change_count = int(
        sum(1 for row in instruction_sidecar_zero_touch_rows if str(row.get("action_family", "")) == "connection_detailing")
    )
    detailing_structured_payload_mapped_change_count = int(
        sum(
            1
            for row in instruction_sidecar_reference_rows
            if str(row.get("action_family", "")) == "detailing" and bool(row.get("structured_payload_present", False))
        )
    )
    detailing_zero_touch_verified_change_count = int(
        sum(1 for row in instruction_sidecar_zero_touch_rows if str(row.get("action_family", "")) == "detailing")
    )
    connection_detailing_delivery_mode = "manual_sidecar_only"
    if int(connection_detailing_direct_patch_eligible_change_count) > 0:
        connection_detailing_delivery_mode = (
            "direct_patch_native_authoring_zero_touch_verified"
            if connection_detailing_zero_touch_verified_change_count == connection_detailing_direct_patch_eligible_change_count
            else "direct_patch_metadata_plus_sidecar"
        )
    elif int(connection_detailing_structured_payload_mapped_change_count) > 0:
        connection_detailing_delivery_mode = "structured_group_local_payload_plus_sidecar"
    elif int(connection_detailing_payload_summary.get("group_local_connection_detailing_payload_row_count", 0) or 0) > 0:
        connection_detailing_delivery_mode = "structured_payload_present_but_unmapped"
    detailing_delivery_mode = "manual_sidecar_only"
    if int(detailing_direct_patch_eligible_change_count) > 0:
        detailing_delivery_mode = (
            "direct_patch_native_authoring_zero_touch_verified"
            if detailing_zero_touch_verified_change_count == detailing_direct_patch_eligible_change_count
            else "direct_patch_metadata_plus_sidecar"
        )
    elif int(detailing_structured_payload_mapped_change_count) > 0:
        detailing_delivery_mode = "structured_group_local_payload_plus_sidecar"
    elif int(detailing_payload_summary.get("group_local_detailing_payload_row_count", 0) or 0) > 0:
        detailing_delivery_mode = "structured_payload_present_but_unmapped"
    delivery_boundary = _format_delivery_boundary(
        direct_patch_action_family_counts=direct_patch_action_family_counts,
        instruction_sidecar_action_family_counts=instruction_sidecar_action_family_counts,
        connection_detailing_delivery_mode=connection_detailing_delivery_mode,
        detailing_delivery_mode=detailing_delivery_mode,
    )
    derived_group_local_rebar_bridge_row_count = int(len(derived_group_local_rebar_bridge_rows))
    derived_group_local_rebar_mapped_change_count = int(
        sum(1 for row in derived_group_local_rebar_bridge_rows if int(row.get("element_id_count", 0)) > 0)
    )
    derived_group_local_rebar_payload_available_group_count = int(
        sum(1 for row in derived_group_local_rebar_bridge_rows if bool(row.get("group_local_payload_present", False)))
    )
    rebar_direct_patch_eligible_change_count = int(
        sum(1 for row in derived_group_local_rebar_bridge_rows if bool(row.get("direct_patch_eligible", False)))
    )
    rebar_direct_patch_ineligible_reason_counts = {
        str(k): int(v)
        for k, v in sorted(
            Counter(
                str(row.get("ineligibility_reason", ""))
                for row in derived_group_local_rebar_bridge_rows
                if not bool(row.get("direct_patch_eligible", False))
            ).items()
        )
    }
    rebar_direct_patch_mapping_source_counts = {
        str(k): int(v)
        for k, v in sorted(Counter(str(row.get("mapping_source", "")) for row in derived_group_local_rebar_bridge_rows).items())
    }
    rebar_delivery_mode = "structured_sidecar_only"
    if int(rebar_direct_patch_eligible_change_count) > 0:
        rebar_delivery_mode = "direct_patch_eligible"
    elif int(rebar_payload_summary.get("group_local_rebar_payload_row_count", 0) or 0) > 0:
        rebar_delivery_mode = "group_local_payload_present_but_unmapped"
    support_mode = "bounded_patch_subset"
    if (
        int(len(unsupported_rows)) == 0
        and instruction_sidecar_manual_input_change_count == 0
        and instruction_sidecar_audit_only_change_count == 0
        and int(len(supported_rows_all)) > 0
    ):
        support_mode = "native_authoring_supported_changeset"
    evidence_model = "direct_patch_only"
    if (
        instruction_sidecar_zero_touch_verified_change_count > 0
        and instruction_sidecar_audit_only_change_count > 0
        and instruction_sidecar_manual_input_change_count > 0
    ):
        evidence_model = "direct_patch_plus_zero_touch_verification_and_audit_manifest_and_manual_sidecar"
    elif instruction_sidecar_zero_touch_verified_change_count > 0 and instruction_sidecar_audit_only_change_count > 0:
        evidence_model = "direct_patch_plus_zero_touch_verification_and_audit_review_manifest"
    elif instruction_sidecar_zero_touch_verified_change_count > 0 and instruction_sidecar_manual_input_change_count > 0:
        evidence_model = "direct_patch_plus_zero_touch_verification_manifest_and_manual_sidecar"
    elif instruction_sidecar_audit_only_change_count > 0 and instruction_sidecar_manual_input_change_count > 0:
        evidence_model = "direct_patch_plus_audit_manifest_and_manual_sidecar"
    elif instruction_sidecar_audit_only_change_count > 0:
        evidence_model = "direct_patch_plus_audit_review_manifest"
    elif instruction_sidecar_zero_touch_verified_change_count > 0:
        evidence_model = "direct_patch_plus_zero_touch_verification_manifest"
    elif instruction_sidecar_manual_input_change_count > 0:
        evidence_model = "direct_patch_plus_structured_sidecar"
    total_change_count = int(len(supported_rows_all) + len(unsupported_rows))
    supported_change_count = int(len(supported_rows_all))
    patched_supported_change_count = int(len(supported_rows))
    direct_patch_change_count = int(len(supported_rows))
    instruction_sidecar_change_count = int(len(instruction_sidecar_rows))
    unsupported_change_count = int(len(unsupported_rows))
    supported_change_ratio = _safe_ratio(supported_change_count, total_change_count)
    direct_patch_change_ratio = _safe_ratio(direct_patch_change_count, total_change_count)
    instruction_sidecar_change_ratio = _safe_ratio(instruction_sidecar_change_count, total_change_count)
    zero_touch_verified_change_ratio = _safe_ratio(
        instruction_sidecar_zero_touch_verified_change_count,
        total_change_count,
    )
    unsupported_change_ratio = _safe_ratio(unsupported_change_count, total_change_count)
    native_authoring_summary_line = (
        f"supported={supported_change_count}/{total_change_count} | "
        f"direct_patch={direct_patch_change_count} | "
        f"zero_touch_verified={instruction_sidecar_zero_touch_verified_change_count} | "
        f"manual_sidecar={instruction_sidecar_manual_input_change_count} | "
        f"unsupported={unsupported_change_count}"
    )
    native_export_verification_parts = [
        f"contract={'PASS' if contract_pass else reason_code or 'CHECK'}",
        f"support_mode={support_mode}",
        f"output_mgt={'yes' if output_mgt_path.exists() else 'no'}",
        f"loadcomb_roundtrip={'yes' if loadcomb_roundtrip_pass else 'no'}",
        f"direct_patch={direct_patch_change_count}",
    ]
    if viewer_loadcomb_override_patch_resolved_entry_count > 0:
        native_export_verification_parts.append(
            f"loadcomb_override={viewer_loadcomb_override_patch_resolved_entry_count}"
        )
    native_export_verification_parts.extend(
        [
            f"audit_pending={audit_review_queue_pending_count}",
            f"unsupported={unsupported_change_count}",
        ]
    )
    mgt_output_status_parts = [
        f"output_mgt={'yes' if output_mgt_path.exists() else 'no'}",
        f"loadcomb_preview={'yes' if loadcomb_preview_exists else 'no'}",
        f"loadcomb_roundtrip_report={'yes' if loadcomb_roundtrip_report_exists else 'no'}",
        f"combos={loadcomb_combo_count}",
        f"viewer_section_override={len(viewer_section_override_retarget_rows)}",
    ]
    if viewer_loadcomb_override_patch_resolved_entry_count > 0:
        mgt_output_status_parts.append(
            f"viewer_loadcomb_override={viewer_loadcomb_override_patch_resolved_entry_count}"
        )
    native_export_verification_line = (
        " | ".join(native_export_verification_parts)
    )
    mgt_output_status_line = (
        " | ".join(mgt_output_status_parts)
    )
    mgt_diff_summary = _build_mgt_diff_summary(
        source_mgt_path=source_mgt_path,
        output_mgt_path=output_mgt_path,
        parsed_model_payload=parsed_model_payload,
    )
    (
        source_output_diff_json_exists,
        source_output_diff_preview_exists,
        source_output_diff_window_json_exists,
        source_output_diff_window_preview_exists,
    ) = _write_source_output_mgt_diff_artifacts(
        source_mgt_path=source_mgt_path,
        output_mgt_path=output_mgt_path,
        diff_summary=mgt_diff_summary,
        diff_json_out_path=source_output_diff_json_out_path,
        diff_preview_out_path=source_output_diff_preview_out_path,
        diff_window_json_out_path=source_output_diff_window_json_out_path,
        diff_window_preview_out_path=source_output_diff_window_preview_out_path,
    )
    source_output_mgt_verification_receipt_line = (
        f"source_output_mgt=yes | "
        f"diff_json={'yes' if source_output_diff_json_exists else 'no'} | "
        f"diff_preview={'yes' if source_output_diff_preview_exists else 'no'} | "
        f"window_json={'yes' if source_output_diff_window_json_exists else 'no'} | "
        f"window_preview={'yes' if source_output_diff_window_preview_exists else 'no'} | "
        f"delta_total={int(mgt_diff_summary.get('source_output_mgt_total_delta_count', 0) or 0)}"
    )
    audit_review_queue_status_line = (
        f"queue_items={audit_review_queue_item_count} | "
        f"pending_review={audit_review_queue_pending_count} | "
        f"acknowledged={audit_review_queue_acknowledged_count}"
    )
    _write_json(
        audit_review_manifest_out_path,
        {
            "schema_version": "1.0",
            "audit_review_rows": instruction_sidecar_audit_only_rows,
            "zero_touch_verified_rows": instruction_sidecar_zero_touch_rows,
            "manual_input_reference_rows": instruction_sidecar_manual_input_rows,
            "summary": {
                "audit_review_manifest_change_count": instruction_sidecar_audit_only_change_count,
                "audit_review_manifest_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
                "zero_touch_verified_change_count": instruction_sidecar_zero_touch_verified_change_count,
                "zero_touch_verified_action_family_counts": instruction_sidecar_zero_touch_verified_action_family_counts,
                "instruction_sidecar_manual_input_change_count": instruction_sidecar_manual_input_change_count,
                "instruction_sidecar_manual_input_action_family_counts": instruction_sidecar_manual_input_action_family_counts,
                "audit_review_packet_count": audit_review_packet_count,
                "audit_review_packet_action_family_counts": audit_review_packet_action_family_counts,
                "audit_review_packet_followup_type_counts": audit_review_packet_followup_type_counts,
                "audit_review_packet_review_priority_counts": audit_review_packet_review_priority_counts,
                "audit_review_packet_file_count": audit_review_packet_file_count,
                "audit_review_packet_file_action_family_counts": audit_review_packet_file_action_family_counts,
                "audit_review_queue_item_count": audit_review_queue_item_count,
                "audit_review_queue_pending_count": audit_review_queue_pending_count,
                "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
                "audit_review_queue_status_counts": audit_review_queue_status_counts,
                "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
                "audit_boundary_mode": "post_patch_audit_only"
                if int(instruction_sidecar_audit_only_change_count) > 0 and int(instruction_sidecar_manual_input_change_count) == 0
                else "mixed_audit_and_manual"
                if int(instruction_sidecar_audit_only_change_count) > 0 and int(instruction_sidecar_manual_input_change_count) > 0
                else "zero_touch_verified_only"
                if int(instruction_sidecar_zero_touch_verified_change_count) > 0 and int(instruction_sidecar_manual_input_change_count) == 0
                else "manual_only"
                if int(instruction_sidecar_manual_input_change_count) > 0
                else "none",
            },
        },
    )
    _write_json(
        audit_review_packet_manifest_out_path,
        {
            "schema_version": "1.0",
            "audit_review_packets": audit_review_packets,
            "audit_review_packet_files": audit_review_packet_files,
            "audit_review_packet_directory": str(audit_review_packet_dir_out_path),
            "summary": {
                "audit_review_packet_count": audit_review_packet_count,
                "audit_review_packet_action_family_counts": audit_review_packet_action_family_counts,
                "audit_review_packet_followup_type_counts": audit_review_packet_followup_type_counts,
                "audit_review_packet_review_priority_counts": audit_review_packet_review_priority_counts,
                "audit_review_packet_file_count": audit_review_packet_file_count,
                "audit_review_packet_file_action_family_counts": audit_review_packet_file_action_family_counts,
                "audit_review_manifest_change_count": instruction_sidecar_audit_only_change_count,
                "audit_packet_delivery_mode": "family_split_post_patch_audit_packets"
                if audit_review_packet_count > 0
                else "none",
            },
        },
    )
    _write_json(
        audit_review_queue_manifest_out_path,
        {
            "schema_version": "1.0",
            "audit_review_queue_items": audit_review_queue_items,
            "audit_review_queue_status_directory": str(audit_review_queue_status_dir_out_path),
            "summary": {
                "audit_review_queue_item_count": audit_review_queue_item_count,
                "audit_review_queue_pending_count": audit_review_queue_pending_count,
                "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
                "audit_review_queue_status_counts": audit_review_queue_status_counts,
                "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
                "audit_review_queue_status_mode": "generated_pending_review_queue"
                if audit_review_queue_item_count > 0
                else "none",
            },
        },
    )
    audit_review_followup_manifest_payload = build_followup_manifest(
        {
            "schema_version": "1.0",
            "audit_review_queue_items": audit_review_queue_items,
            "audit_review_queue_status_directory": str(audit_review_queue_status_dir_out_path),
            "summary": {
                "audit_review_queue_item_count": audit_review_queue_item_count,
                "audit_review_queue_pending_count": audit_review_queue_pending_count,
                "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
                "audit_review_queue_status_counts": audit_review_queue_status_counts,
                "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
                "audit_review_queue_status_mode": "generated_pending_review_queue"
                if audit_review_queue_item_count > 0
                else "none",
            },
        }
    )
    _write_json(audit_review_followup_manifest_out_path, audit_review_followup_manifest_payload)
    audit_review_followup_summary = (
        audit_review_followup_manifest_payload.get("summary")
        if isinstance(audit_review_followup_manifest_payload.get("summary"), dict)
        else {}
    )
    audit_review_followup_item_count = int(audit_review_followup_summary.get("audit_review_followup_item_count", 0) or 0)
    audit_review_followup_open_item_count = int(
        audit_review_followup_summary.get("audit_review_followup_open_item_count", 0) or 0
    )
    audit_review_followup_closed_item_count = int(
        audit_review_followup_summary.get("audit_review_followup_closed_item_count", 0) or 0
    )
    audit_review_followup_action_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_action_counts") or {}).items())
    }
    audit_review_followup_action_label = ", ".join(
        f"{action}={count}" for action, count in sorted(audit_review_followup_action_counts.items())
    )
    audit_review_followup_owner_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_owner_counts") or {}).items())
    }
    audit_review_followup_owner_label = ", ".join(
        f"{owner}={count}" for owner, count in sorted(audit_review_followup_owner_counts.items())
    )
    audit_review_followup_review_owner_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_review_owner_counts") or {}).items())
    }
    audit_review_followup_review_owner_label = ", ".join(
        f"{owner}={count}" for owner, count in sorted(audit_review_followup_review_owner_counts.items())
    )
    audit_review_followup_status_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_status_counts") or {}).items())
    }
    audit_review_followup_status_label = ", ".join(
        f"{status}={count}" for status, count in sorted(audit_review_followup_status_counts.items())
    )
    audit_review_followup_sla_state_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_sla_state_counts") or {}).items())
    }
    audit_review_followup_sla_state_label = ", ".join(
        f"{state}={count}" for state, count in sorted(audit_review_followup_sla_state_counts.items())
    )
    audit_review_followup_age_bucket_counts = {
        str(k): int(v)
        for k, v in sorted((audit_review_followup_summary.get("audit_review_followup_age_bucket_counts") or {}).items())
    }
    audit_review_followup_age_bucket_label = ", ".join(
        f"{bucket}={count}" for bucket, count in sorted(audit_review_followup_age_bucket_counts.items())
    )
    audit_review_followup_overdue_item_count = int(
        audit_review_followup_summary.get("audit_review_followup_overdue_item_count", 0) or 0
    )
    audit_review_followup_oldest_open_age_hours = float(
        audit_review_followup_summary.get("audit_review_followup_oldest_open_age_hours", 0.0) or 0.0
    )
    audit_review_followup_oldest_open_packet_id = str(
        audit_review_followup_summary.get("audit_review_followup_oldest_open_packet_id", "") or ""
    )
    audit_review_followup_reference_time_utc = str(
        audit_review_followup_summary.get("audit_review_followup_reference_time_utc", "") or ""
    )
    audit_review_followup_sla_policy_label = str(
        audit_review_followup_summary.get("audit_review_followup_sla_policy_label", "") or ""
    )
    audit_review_followup_mode = str(audit_review_followup_summary.get("audit_review_followup_mode", "") or "")
    audit_review_resolution_manifest_payload = build_resolution_manifest(
        {
            "schema_version": "1.0",
            "audit_review_queue_items": audit_review_queue_items,
            "audit_review_queue_status_directory": str(audit_review_queue_status_dir_out_path),
        },
        audit_review_followup_manifest_payload,
    )
    audit_review_resolution_files = write_resolution_files(
        audit_review_resolution_dir_out_path,
        audit_review_resolution_manifest_payload.get("audit_review_resolution_rows", []),
    )
    audit_review_resolution_manifest_payload["audit_review_resolution_files"] = audit_review_resolution_files
    audit_review_resolution_manifest_payload["audit_review_resolution_directory"] = str(audit_review_resolution_dir_out_path)
    resolution_summary = (
        audit_review_resolution_manifest_payload.get("summary")
        if isinstance(audit_review_resolution_manifest_payload.get("summary"), dict)
        else {}
    )
    resolution_summary["audit_review_resolution_file_count"] = int(len(audit_review_resolution_files))
    _write_json(audit_review_resolution_manifest_out_path, audit_review_resolution_manifest_payload)
    audit_review_resolution_item_count = int(resolution_summary.get("audit_review_resolution_item_count", 0) or 0)
    audit_review_resolution_file_count = int(resolution_summary.get("audit_review_resolution_file_count", 0) or 0)
    audit_review_resolution_open_item_count = int(
        resolution_summary.get("audit_review_resolution_open_item_count", 0) or 0
    )
    audit_review_resolution_closed_item_count = int(
        resolution_summary.get("audit_review_resolution_closed_item_count", 0) or 0
    )
    audit_review_resolution_pending_item_count = int(
        resolution_summary.get("audit_review_resolution_pending_item_count", 0) or 0
    )
    audit_review_resolution_open_revision_count = int(
        resolution_summary.get("audit_review_resolution_open_revision_count", 0) or 0
    )
    audit_review_resolution_closed_packet_count = int(
        resolution_summary.get("audit_review_resolution_closed_packet_count", 0) or 0
    )
    audit_review_resolution_action_counts = {
        str(k): int(v)
        for k, v in sorted((resolution_summary.get("audit_review_resolution_action_counts") or {}).items())
    }
    audit_review_resolution_action_label = ", ".join(
        f"{action}={count}" for action, count in sorted(audit_review_resolution_action_counts.items())
    )
    audit_review_resolution_owner_counts = {
        str(k): int(v)
        for k, v in sorted((resolution_summary.get("audit_review_resolution_owner_counts") or {}).items())
    }
    audit_review_resolution_owner_label = ", ".join(
        f"{owner}={count}" for owner, count in sorted(audit_review_resolution_owner_counts.items())
    )
    audit_review_resolution_status_counts = {
        str(k): int(v)
        for k, v in sorted((resolution_summary.get("audit_review_resolution_status_counts") or {}).items())
    }
    audit_review_resolution_status_label = ", ".join(
        f"{status}={count}" for status, count in sorted(audit_review_resolution_status_counts.items())
    )
    audit_review_resolution_mode = str(resolution_summary.get("audit_review_resolution_mode", "") or "")
    _write_json(
        instruction_sidecar_out_path,
        {
            "schema_version": "1.0",
            "instruction_sidecar_rows": instruction_sidecar_rows,
            "audit_review_reference_rows": instruction_sidecar_audit_only_rows,
            "zero_touch_verified_reference_rows": instruction_sidecar_zero_touch_rows,
            "derived_group_local_rebar_bridge_rows": derived_group_local_rebar_bridge_rows,
            "summary": {
                "instruction_sidecar_change_count": int(len(instruction_sidecar_rows)),
                "instruction_sidecar_action_family_counts": instruction_sidecar_action_family_counts,
                "instruction_sidecar_review_priority_counts": instruction_sidecar_review_priority_counts,
                "instruction_sidecar_followup_type_counts": instruction_sidecar_followup_type_counts,
                "instruction_sidecar_audit_only_change_count": instruction_sidecar_audit_only_change_count,
                "instruction_sidecar_audit_only_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
                "instruction_sidecar_zero_touch_verified_change_count": instruction_sidecar_zero_touch_verified_change_count,
                "instruction_sidecar_zero_touch_verified_action_family_counts": instruction_sidecar_zero_touch_verified_action_family_counts,
                "instruction_sidecar_manual_input_change_count": instruction_sidecar_manual_input_change_count,
                "instruction_sidecar_manual_input_action_family_counts": instruction_sidecar_manual_input_action_family_counts,
                "audit_review_manifest_change_count": instruction_sidecar_audit_only_change_count,
                "zero_touch_verified_change_count": instruction_sidecar_zero_touch_verified_change_count,
                "zero_touch_verified_action_family_counts": instruction_sidecar_zero_touch_verified_action_family_counts,
                "audit_review_manifest_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
                "audit_review_packet_count": audit_review_packet_count,
                "audit_review_packet_action_family_counts": audit_review_packet_action_family_counts,
                "audit_review_packet_followup_type_counts": audit_review_packet_followup_type_counts,
                "audit_review_packet_review_priority_counts": audit_review_packet_review_priority_counts,
                "audit_review_packet_file_count": audit_review_packet_file_count,
                "audit_review_packet_file_action_family_counts": audit_review_packet_file_action_family_counts,
                "audit_review_queue_item_count": audit_review_queue_item_count,
                "audit_review_queue_pending_count": audit_review_queue_pending_count,
                "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
                "audit_review_queue_status_counts": audit_review_queue_status_counts,
                "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
                "audit_review_followup_item_count": audit_review_followup_item_count,
                "audit_review_followup_open_item_count": audit_review_followup_open_item_count,
                "audit_review_followup_closed_item_count": audit_review_followup_closed_item_count,
                "audit_review_followup_action_counts": audit_review_followup_action_counts,
                "audit_review_followup_action_label": audit_review_followup_action_label,
                "audit_review_followup_owner_counts": audit_review_followup_owner_counts,
                "audit_review_followup_owner_label": audit_review_followup_owner_label,
                "audit_review_followup_review_owner_counts": audit_review_followup_review_owner_counts,
                "audit_review_followup_review_owner_label": audit_review_followup_review_owner_label,
                "audit_review_followup_status_counts": audit_review_followup_status_counts,
                "audit_review_followup_status_label": audit_review_followup_status_label,
                "audit_review_followup_sla_state_counts": audit_review_followup_sla_state_counts,
                "audit_review_followup_sla_state_label": audit_review_followup_sla_state_label,
                "audit_review_followup_age_bucket_counts": audit_review_followup_age_bucket_counts,
                "audit_review_followup_age_bucket_label": audit_review_followup_age_bucket_label,
                "audit_review_followup_overdue_item_count": audit_review_followup_overdue_item_count,
                "audit_review_followup_oldest_open_age_hours": audit_review_followup_oldest_open_age_hours,
                "audit_review_followup_oldest_open_packet_id": audit_review_followup_oldest_open_packet_id,
                "audit_review_followup_reference_time_utc": audit_review_followup_reference_time_utc,
                "audit_review_followup_sla_policy_label": audit_review_followup_sla_policy_label,
                "audit_review_followup_mode": audit_review_followup_mode,
                "audit_review_resolution_item_count": audit_review_resolution_item_count,
                "audit_review_resolution_file_count": audit_review_resolution_file_count,
                "audit_review_resolution_open_item_count": audit_review_resolution_open_item_count,
                "audit_review_resolution_closed_item_count": audit_review_resolution_closed_item_count,
                "audit_review_resolution_pending_item_count": audit_review_resolution_pending_item_count,
                "audit_review_resolution_open_revision_count": audit_review_resolution_open_revision_count,
                "audit_review_resolution_closed_packet_count": audit_review_resolution_closed_packet_count,
                "audit_review_resolution_action_counts": audit_review_resolution_action_counts,
                "audit_review_resolution_action_label": audit_review_resolution_action_label,
                "audit_review_resolution_owner_counts": audit_review_resolution_owner_counts,
                "audit_review_resolution_owner_label": audit_review_resolution_owner_label,
                "audit_review_resolution_status_counts": audit_review_resolution_status_counts,
                "audit_review_resolution_status_label": audit_review_resolution_status_label,
                "audit_review_resolution_mode": audit_review_resolution_mode,
                "direct_patch_supported_action_families": [str(v) for v in direct_patch_supported_families],
                "sidecar_supported_action_families": sorted(str(v) for v in sidecar_supported_families),
                "material_level_rebar_payload_row_count": int(rebar_payload_summary.get("material_level_rebar_payload_row_count", 0)),
                "material_level_rebar_payload_available_count": int(
                    rebar_payload_summary.get("material_level_rebar_payload_available_count", 0)
                ),
                "group_local_rebar_payload_row_count": int(rebar_payload_summary.get("group_local_rebar_payload_row_count", 0)),
                "group_local_rebar_payload_available_count": int(
                    rebar_payload_summary.get("group_local_rebar_payload_available_count", 0)
                ),
                "group_local_connection_detailing_payload_row_count": int(
                    connection_detailing_payload_summary.get("group_local_connection_detailing_payload_row_count", 0)
                ),
                "group_local_connection_detailing_payload_available_count": int(
                    connection_detailing_payload_summary.get("group_local_connection_detailing_payload_available_count", 0)
                ),
                "group_local_detailing_payload_row_count": int(
                    detailing_payload_summary.get("group_local_detailing_payload_row_count", 0)
                ),
                "group_local_detailing_payload_available_count": int(
                    detailing_payload_summary.get("group_local_detailing_payload_available_count", 0)
                ),
                "connection_detailing_payload_namespace_mode": str(
                    connection_detailing_payload_summary.get("connection_detailing_payload_namespace_mode", "none")
                ),
                "connection_detailing_payload_group_local_namespace_present": bool(
                    connection_detailing_payload_summary.get("connection_detailing_payload_group_local_namespace_present", False)
                ),
                "detailing_payload_namespace_mode": str(
                    detailing_payload_summary.get("detailing_payload_namespace_mode", "none")
                ),
                "detailing_payload_group_local_namespace_present": bool(
                    detailing_payload_summary.get("detailing_payload_group_local_namespace_present", False)
                ),
                "connection_detailing_structured_payload_mapped_change_count": int(
                    connection_detailing_structured_payload_mapped_change_count
                ),
                "connection_detailing_direct_patch_eligible_change_count": int(
                    connection_detailing_direct_patch_eligible_change_count
                ),
                "connection_detailing_zero_touch_verified_change_count": int(
                    connection_detailing_zero_touch_verified_change_count
                ),
                "detailing_direct_patch_eligible_change_count": int(
                    detailing_direct_patch_eligible_change_count
                ),
                "detailing_structured_payload_mapped_change_count": int(
                    detailing_structured_payload_mapped_change_count
                ),
                "detailing_zero_touch_verified_change_count": int(detailing_zero_touch_verified_change_count),
                "connection_detailing_delivery_mode": str(connection_detailing_delivery_mode),
                "detailing_delivery_mode": str(detailing_delivery_mode),
                "mgt_export_delivery_boundary": str(delivery_boundary),
                "rebar_payload_namespace_mode": str(rebar_payload_summary.get("rebar_payload_namespace_mode", "none")),
                "rebar_payload_material_level_namespace_present": bool(
                    rebar_payload_summary.get("rebar_payload_material_level_namespace_present", False)
                ),
                "rebar_payload_group_local_namespace_present": bool(
                    rebar_payload_summary.get("rebar_payload_group_local_namespace_present", False)
                ),
                "rebar_delivery_mode": str(rebar_delivery_mode),
                "evidence_model": str(evidence_model),
                "derived_group_local_rebar_bridge_row_count": derived_group_local_rebar_bridge_row_count,
                "derived_group_local_rebar_mapped_change_count": derived_group_local_rebar_mapped_change_count,
                "derived_group_local_rebar_payload_available_group_count": derived_group_local_rebar_payload_available_group_count,
                "rebar_direct_patch_eligible_change_count": int(rebar_direct_patch_eligible_change_count),
                "rebar_direct_patch_ineligible_reason_counts": rebar_direct_patch_ineligible_reason_counts,
                "rebar_direct_patch_mapping_source_counts": rebar_direct_patch_mapping_source_counts,
            },
        },
    )
    manifest = {
        "schema_version": "1.0",
        "support_mode": support_mode,
        "supported_action_families": ["beam_section", "wall_thickness", "slab_thickness", "detailing", "connection_detailing", "rebar", "perimeter_frame"],
        "direct_patch_supported_action_families": [str(v) for v in direct_patch_supported_families],
        "special_member_supported_action_families": sorted(special_member_supported_action_family_counts),
        "special_member_direct_patch_supported_action_families": sorted(special_member_direct_patch_action_family_counts),
        "sidecar_supported_action_families": sorted(str(v) for v in sidecar_supported_families),
        "material_level_rebar_payload_row_count": int(rebar_payload_summary.get("material_level_rebar_payload_row_count", 0)),
        "material_level_rebar_payload_available_count": int(rebar_payload_summary.get("material_level_rebar_payload_available_count", 0)),
        "group_local_rebar_payload_row_count": int(rebar_payload_summary.get("group_local_rebar_payload_row_count", 0)),
        "group_local_rebar_payload_available_count": int(rebar_payload_summary.get("group_local_rebar_payload_available_count", 0)),
        "group_local_connection_detailing_payload_row_count": int(
            connection_detailing_payload_summary.get("group_local_connection_detailing_payload_row_count", 0)
        ),
        "group_local_connection_detailing_payload_available_count": int(
            connection_detailing_payload_summary.get("group_local_connection_detailing_payload_available_count", 0)
        ),
        "group_local_detailing_payload_row_count": int(
            detailing_payload_summary.get("group_local_detailing_payload_row_count", 0)
        ),
        "group_local_detailing_payload_available_count": int(
            detailing_payload_summary.get("group_local_detailing_payload_available_count", 0)
        ),
        "connection_detailing_payload_namespace_mode": str(
            connection_detailing_payload_summary.get("connection_detailing_payload_namespace_mode", "none")
        ),
        "connection_detailing_payload_group_local_namespace_present": bool(
            connection_detailing_payload_summary.get("connection_detailing_payload_group_local_namespace_present", False)
        ),
        "detailing_payload_namespace_mode": str(
            detailing_payload_summary.get("detailing_payload_namespace_mode", "none")
        ),
        "detailing_payload_group_local_namespace_present": bool(
            detailing_payload_summary.get("detailing_payload_group_local_namespace_present", False)
        ),
        "connection_detailing_structured_payload_mapped_change_count": int(
            connection_detailing_structured_payload_mapped_change_count
        ),
        "connection_detailing_direct_patch_eligible_change_count": int(
            connection_detailing_direct_patch_eligible_change_count
        ),
        "connection_detailing_zero_touch_verified_change_count": int(
            connection_detailing_zero_touch_verified_change_count
        ),
        "detailing_direct_patch_eligible_change_count": int(
            detailing_direct_patch_eligible_change_count
        ),
        "detailing_structured_payload_mapped_change_count": int(
            detailing_structured_payload_mapped_change_count
        ),
        "detailing_zero_touch_verified_change_count": int(detailing_zero_touch_verified_change_count),
        "connection_detailing_delivery_mode": str(connection_detailing_delivery_mode),
        "detailing_delivery_mode": str(detailing_delivery_mode),
        "mgt_export_delivery_boundary": str(delivery_boundary),
        "rebar_payload_namespace_mode": str(rebar_payload_summary.get("rebar_payload_namespace_mode", "none")),
        "rebar_payload_material_level_namespace_present": bool(
            rebar_payload_summary.get("rebar_payload_material_level_namespace_present", False)
        ),
        "rebar_payload_group_local_namespace_present": bool(
            rebar_payload_summary.get("rebar_payload_group_local_namespace_present", False)
        ),
        "rebar_delivery_mode": str(rebar_delivery_mode),
        "evidence_model": str(evidence_model),
        "derived_group_local_rebar_bridge_row_count": derived_group_local_rebar_bridge_row_count,
        "derived_group_local_rebar_mapped_change_count": derived_group_local_rebar_mapped_change_count,
        "derived_group_local_rebar_payload_available_group_count": derived_group_local_rebar_payload_available_group_count,
        "rebar_direct_patch_eligible_change_count": int(rebar_direct_patch_eligible_change_count),
        "rebar_direct_patch_ineligible_reason_counts": rebar_direct_patch_ineligible_reason_counts,
        "rebar_direct_patch_mapping_source_counts": rebar_direct_patch_mapping_source_counts,
        "instruction_sidecar_audit_only_change_count": instruction_sidecar_audit_only_change_count,
        "instruction_sidecar_audit_only_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
        "instruction_sidecar_zero_touch_verified_change_count": instruction_sidecar_zero_touch_verified_change_count,
        "instruction_sidecar_zero_touch_verified_action_family_counts": instruction_sidecar_zero_touch_verified_action_family_counts,
        "special_member_instruction_sidecar_zero_touch_verified_action_family_counts": (
            special_member_instruction_sidecar_zero_touch_verified_action_family_counts
        ),
        "instruction_sidecar_manual_input_change_count": instruction_sidecar_manual_input_change_count,
        "instruction_sidecar_manual_input_action_family_counts": instruction_sidecar_manual_input_action_family_counts,
        "audit_review_manifest_change_count": instruction_sidecar_audit_only_change_count,
        "audit_review_manifest_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
        "audit_review_packet_count": audit_review_packet_count,
        "audit_review_packet_action_family_counts": audit_review_packet_action_family_counts,
        "audit_review_packet_followup_type_counts": audit_review_packet_followup_type_counts,
        "audit_review_packet_review_priority_counts": audit_review_packet_review_priority_counts,
        "audit_review_packet_file_count": audit_review_packet_file_count,
        "audit_review_packet_file_action_family_counts": audit_review_packet_file_action_family_counts,
        "audit_review_queue_item_count": audit_review_queue_item_count,
        "audit_review_queue_pending_count": audit_review_queue_pending_count,
        "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
        "audit_review_queue_status_counts": audit_review_queue_status_counts,
        "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
        "audit_review_followup_item_count": audit_review_followup_item_count,
        "audit_review_followup_open_item_count": audit_review_followup_open_item_count,
        "audit_review_followup_closed_item_count": audit_review_followup_closed_item_count,
        "audit_review_followup_action_counts": audit_review_followup_action_counts,
        "audit_review_followup_action_label": audit_review_followup_action_label,
        "audit_review_followup_owner_counts": audit_review_followup_owner_counts,
        "audit_review_followup_owner_label": audit_review_followup_owner_label,
        "audit_review_followup_review_owner_counts": audit_review_followup_review_owner_counts,
        "audit_review_followup_review_owner_label": audit_review_followup_review_owner_label,
        "audit_review_followup_status_counts": audit_review_followup_status_counts,
        "audit_review_followup_status_label": audit_review_followup_status_label,
        "audit_review_followup_sla_state_counts": audit_review_followup_sla_state_counts,
        "audit_review_followup_sla_state_label": audit_review_followup_sla_state_label,
        "audit_review_followup_age_bucket_counts": audit_review_followup_age_bucket_counts,
        "audit_review_followup_age_bucket_label": audit_review_followup_age_bucket_label,
        "audit_review_followup_overdue_item_count": audit_review_followup_overdue_item_count,
        "audit_review_followup_oldest_open_age_hours": audit_review_followup_oldest_open_age_hours,
        "audit_review_followup_oldest_open_packet_id": audit_review_followup_oldest_open_packet_id,
        "audit_review_followup_reference_time_utc": audit_review_followup_reference_time_utc,
        "audit_review_followup_sla_policy_label": audit_review_followup_sla_policy_label,
        "audit_review_followup_mode": audit_review_followup_mode,
        "audit_review_resolution_item_count": audit_review_resolution_item_count,
        "audit_review_resolution_file_count": audit_review_resolution_file_count,
        "audit_review_resolution_open_item_count": audit_review_resolution_open_item_count,
        "audit_review_resolution_closed_item_count": audit_review_resolution_closed_item_count,
        "audit_review_resolution_pending_item_count": audit_review_resolution_pending_item_count,
        "audit_review_resolution_open_revision_count": audit_review_resolution_open_revision_count,
        "audit_review_resolution_closed_packet_count": audit_review_resolution_closed_packet_count,
        "audit_review_resolution_action_counts": audit_review_resolution_action_counts,
        "audit_review_resolution_action_label": audit_review_resolution_action_label,
        "audit_review_resolution_owner_counts": audit_review_resolution_owner_counts,
        "audit_review_resolution_owner_label": audit_review_resolution_owner_label,
        "audit_review_resolution_status_counts": audit_review_resolution_status_counts,
        "audit_review_resolution_status_label": audit_review_resolution_status_label,
        "audit_review_resolution_mode": audit_review_resolution_mode,
        "special_member_supported_action_family_counts": special_member_supported_action_family_counts,
        "special_member_direct_patch_action_family_counts": special_member_direct_patch_action_family_counts,
        "special_member_instruction_sidecar_action_family_counts": special_member_instruction_sidecar_action_family_counts,
        "supported_changes": supported_rows_all,
        "unsupported_changes": unsupported_rows,
        "applied_section_scale_rows": applied_scale_rows,
        "applied_thickness_rows": applied_thickness_rows,
        "applied_material_rows": applied_material_rows,
        "retargeted_element_rows": retargeted_element_rows,
        "viewer_section_override_retarget_rows": viewer_section_override_retarget_rows,
        "viewer_loadcomb_override_rows": viewer_loadcomb_override_rows,
        "instruction_sidecar_rows": instruction_sidecar_rows,
        "audit_review_rows": instruction_sidecar_audit_only_rows,
        "zero_touch_verified_rows": instruction_sidecar_zero_touch_rows,
        "audit_review_packets": audit_review_packets,
        "audit_review_packet_files": audit_review_packet_files,
        "audit_review_queue_items": audit_review_queue_items,
        "audit_review_resolution_files": audit_review_resolution_files,
        "derived_group_local_rebar_bridge_rows": derived_group_local_rebar_bridge_rows,
    }
    _write_json(patch_manifest_out_path, manifest)
    report = {
        "schema_version": "1.0",
        "contract_pass": bool(contract_pass),
        "reason_code": str(reason_code),
        "reason": str(reason),
        "summary": {
            "support_mode": support_mode,
            "supported_action_families": ["beam_section", "wall_thickness", "slab_thickness", "detailing", "connection_detailing", "rebar", "perimeter_frame"],
            "direct_patch_supported_action_families": [str(v) for v in direct_patch_supported_families],
            "special_member_supported_action_families": sorted(special_member_supported_action_family_counts),
            "special_member_direct_patch_supported_action_families": sorted(special_member_direct_patch_action_family_counts),
            "sidecar_supported_action_families": sorted(str(v) for v in sidecar_supported_families),
            "source_mgt_exists": bool(source_mgt_path.exists()),
            "output_mgt_exists": bool(output_mgt_path.exists()),
            "loadcomb_preview_exists": bool(loadcomb_preview_exists),
            "loadcomb_roundtrip_report_exists": bool(loadcomb_roundtrip_report_exists),
            "loadcomb_roundtrip_pass": bool(loadcomb_roundtrip_pass),
            "loadcomb_roundtrip_summary_line": str(loadcomb_roundtrip_summary_line),
            "loadcomb_roundtrip_recovery_mode": str(loadcomb_recovery_mode),
            "loadcomb_combo_count": int(loadcomb_combo_count),
            "total_change_count": total_change_count,
            "supported_change_count": supported_change_count,
            "patched_supported_change_count": patched_supported_change_count,
            "direct_patch_change_count": direct_patch_change_count,
            "instruction_sidecar_change_count": instruction_sidecar_change_count,
            "supported_change_ratio": supported_change_ratio,
            "direct_patch_change_ratio": direct_patch_change_ratio,
            "instruction_sidecar_change_ratio": instruction_sidecar_change_ratio,
            "instruction_sidecar_zero_touch_verified_change_ratio": zero_touch_verified_change_ratio,
            "unsupported_change_ratio": unsupported_change_ratio,
            "native_authoring_summary_line": native_authoring_summary_line,
            "native_export_verification_line": native_export_verification_line,
            "mgt_output_status_line": mgt_output_status_line,
            "source_output_mgt_diff_available": bool(
                mgt_diff_summary.get("source_output_mgt_diff_available", False)
            ),
            "source_output_mgt_summary_line": str(
                mgt_diff_summary.get("source_output_mgt_summary_line", "")
            ),
            "source_output_mgt_source_meaningful_line_count": int(
                mgt_diff_summary.get("source_output_mgt_source_meaningful_line_count", 0)
            ),
            "source_output_mgt_output_meaningful_line_count": int(
                mgt_diff_summary.get("source_output_mgt_output_meaningful_line_count", 0)
            ),
            "source_output_mgt_changed_line_count": int(
                mgt_diff_summary.get("source_output_mgt_changed_line_count", 0)
            ),
            "source_output_mgt_added_line_count": int(
                mgt_diff_summary.get("source_output_mgt_added_line_count", 0)
            ),
            "source_output_mgt_removed_line_count": int(
                mgt_diff_summary.get("source_output_mgt_removed_line_count", 0)
            ),
            "source_output_mgt_total_delta_count": int(
                mgt_diff_summary.get("source_output_mgt_total_delta_count", 0)
            ),
            "source_output_mgt_diff_sample_lines": list(
                mgt_diff_summary.get("source_output_mgt_diff_sample_lines") or []
            ),
            "source_output_mgt_diff_search_tokens": list(
                mgt_diff_summary.get("source_output_mgt_diff_search_tokens") or []
            ),
            "source_output_mgt_diff_member_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_member_ids") or []
            ),
            "source_output_mgt_diff_section_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_section_ids") or []
            ),
            "source_output_mgt_diff_member_row_indices": dict(
                mgt_diff_summary.get("source_output_mgt_diff_member_row_indices") or {}
            ),
            "source_output_mgt_diff_row_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_row_ids") or []
            ),
            "source_output_mgt_diff_window_search_tokens": list(
                mgt_diff_summary.get("source_output_mgt_diff_window_search_tokens") or []
            ),
            "source_output_mgt_diff_window_member_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_window_member_ids") or []
            ),
            "source_output_mgt_diff_window_section_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_window_section_ids") or []
            ),
            "source_output_mgt_diff_window_member_row_indices": dict(
                mgt_diff_summary.get("source_output_mgt_diff_window_member_row_indices") or {}
            ),
            "source_output_mgt_diff_window_row_ids": list(
                mgt_diff_summary.get("source_output_mgt_diff_window_row_ids") or []
            ),
            "source_output_mgt_diff_json_exists": bool(source_output_diff_json_exists),
            "source_output_mgt_diff_preview_exists": bool(source_output_diff_preview_exists),
            "source_output_mgt_diff_window_json_exists": bool(source_output_diff_window_json_exists),
            "source_output_mgt_diff_window_preview_exists": bool(source_output_diff_window_preview_exists),
            "source_output_mgt_verification_receipt_line": str(source_output_mgt_verification_receipt_line),
            "source_vs_output_diff_summary_line": str(
                mgt_diff_summary.get("source_vs_output_diff_summary_line", "")
            ),
            "source_vs_output_diff_changed_line_count": int(
                mgt_diff_summary.get("source_vs_output_diff_changed_line_count", 0)
            ),
            "source_vs_output_diff_added_line_count": int(
                mgt_diff_summary.get("source_vs_output_diff_added_line_count", 0)
            ),
            "source_vs_output_diff_removed_line_count": int(
                mgt_diff_summary.get("source_vs_output_diff_removed_line_count", 0)
            ),
            "source_vs_output_diff_sample_rows": list(
                mgt_diff_summary.get("source_vs_output_diff_sample_rows") or []
            ),
            "source_vs_output_diff_sample_count": int(
                mgt_diff_summary.get("source_vs_output_diff_sample_count", 0)
            ),
            "source_vs_output_diff_window_rows": list(
                mgt_diff_summary.get("source_vs_output_diff_window_rows") or []
            ),
            "source_vs_output_diff_window_count": int(
                mgt_diff_summary.get("source_vs_output_diff_window_count", 0)
            ),
            "source_vs_output_source_line_count": int(
                mgt_diff_summary.get("source_vs_output_source_line_count", 0)
            ),
            "source_vs_output_output_line_count": int(
                mgt_diff_summary.get("source_vs_output_output_line_count", 0)
            ),
            "audit_review_queue_status_line": audit_review_queue_status_line,
            "unsupported_change_count": unsupported_change_count,
            "material_level_rebar_payload_row_count": int(rebar_payload_summary.get("material_level_rebar_payload_row_count", 0)),
            "material_level_rebar_payload_available_count": int(
                rebar_payload_summary.get("material_level_rebar_payload_available_count", 0)
            ),
            "group_local_rebar_payload_row_count": int(rebar_payload_summary.get("group_local_rebar_payload_row_count", 0)),
            "group_local_rebar_payload_available_count": int(
                rebar_payload_summary.get("group_local_rebar_payload_available_count", 0)
            ),
            "group_local_connection_detailing_payload_row_count": int(
                connection_detailing_payload_summary.get("group_local_connection_detailing_payload_row_count", 0)
            ),
            "group_local_connection_detailing_payload_available_count": int(
                connection_detailing_payload_summary.get("group_local_connection_detailing_payload_available_count", 0)
            ),
            "group_local_detailing_payload_row_count": int(
                detailing_payload_summary.get("group_local_detailing_payload_row_count", 0)
            ),
            "group_local_detailing_payload_available_count": int(
                detailing_payload_summary.get("group_local_detailing_payload_available_count", 0)
            ),
            "connection_detailing_payload_namespace_mode": str(
                connection_detailing_payload_summary.get("connection_detailing_payload_namespace_mode", "none")
            ),
            "connection_detailing_payload_group_local_namespace_present": bool(
                connection_detailing_payload_summary.get("connection_detailing_payload_group_local_namespace_present", False)
            ),
            "detailing_payload_namespace_mode": str(
                detailing_payload_summary.get("detailing_payload_namespace_mode", "none")
            ),
            "detailing_payload_group_local_namespace_present": bool(
                detailing_payload_summary.get("detailing_payload_group_local_namespace_present", False)
            ),
            "connection_detailing_structured_payload_mapped_change_count": int(
                connection_detailing_structured_payload_mapped_change_count
            ),
            "connection_detailing_direct_patch_eligible_change_count": int(
                connection_detailing_direct_patch_eligible_change_count
            ),
            "connection_detailing_zero_touch_verified_change_count": int(
                connection_detailing_zero_touch_verified_change_count
            ),
            "detailing_direct_patch_eligible_change_count": int(
                detailing_direct_patch_eligible_change_count
            ),
            "detailing_structured_payload_mapped_change_count": int(
                detailing_structured_payload_mapped_change_count
            ),
            "detailing_zero_touch_verified_change_count": int(detailing_zero_touch_verified_change_count),
            "connection_detailing_delivery_mode": str(connection_detailing_delivery_mode),
            "detailing_delivery_mode": str(detailing_delivery_mode),
            "mgt_export_delivery_boundary": str(delivery_boundary),
            "rebar_payload_namespace_mode": str(rebar_payload_summary.get("rebar_payload_namespace_mode", "none")),
            "rebar_payload_material_level_namespace_present": bool(
                rebar_payload_summary.get("rebar_payload_material_level_namespace_present", False)
            ),
            "rebar_payload_group_local_namespace_present": bool(
                rebar_payload_summary.get("rebar_payload_group_local_namespace_present", False)
            ),
            "rebar_delivery_mode": str(rebar_delivery_mode),
            "evidence_model": str(evidence_model),
            "derived_group_local_rebar_bridge_row_count": derived_group_local_rebar_bridge_row_count,
            "derived_group_local_rebar_mapped_change_count": derived_group_local_rebar_mapped_change_count,
            "derived_group_local_rebar_payload_available_group_count": derived_group_local_rebar_payload_available_group_count,
            "rebar_direct_patch_eligible_change_count": int(rebar_direct_patch_eligible_change_count),
            "rebar_direct_patch_ineligible_reason_counts": rebar_direct_patch_ineligible_reason_counts,
            "rebar_direct_patch_mapping_source_counts": rebar_direct_patch_mapping_source_counts,
            "patched_section_scale_row_count": int(len(applied_scale_rows)),
            "patched_thickness_row_count": int(len(applied_thickness_rows)),
            "patched_material_row_count": int(len(applied_material_rows)),
            "cloned_section_count": int(len(section_clone_specs)),
            "cloned_thickness_count": int(len(thickness_clone_specs)),
            "cloned_material_count": int(len(material_clone_specs)),
            "retargeted_element_row_count": int(len(retargeted_element_rows)),
            "viewer_section_override_patch_present": bool(viewer_section_override_patch_present),
            "viewer_section_override_patch_member_count": int(viewer_section_override_patch_member_count),
            "viewer_section_override_patch_matched_element_count": int(
                viewer_section_override_patch_matched_element_count
            ),
            "viewer_section_override_patch_resolved_entry_count": int(
                viewer_section_override_patch_resolved_entry_count
            ),
            "viewer_section_override_patch_unresolved_entry_count": int(
                viewer_section_override_patch_unresolved_entry_count
            ),
            "viewer_section_override_applied_source_json_exists": bool(
                section_override_applied_source_json_out_path is not None
                and section_override_applied_source_json_out_path.exists()
            ),
            "viewer_section_override_retarget_row_count": int(
                len(
                    [
                        row
                        for row in retargeted_element_rows
                        if str(row.get("retarget_source", "") or "") == "viewer_section_override_patch"
                    ]
                )
            ),
            "viewer_loadcomb_override_patch_present": bool(viewer_loadcomb_override_patch_present),
            "viewer_loadcomb_override_patch_entry_count": int(viewer_loadcomb_override_patch_entry_count),
            "viewer_loadcomb_override_patch_resolved_entry_count": int(
                viewer_loadcomb_override_patch_resolved_entry_count
            ),
            "viewer_loadcomb_override_patch_unresolved_entry_count": int(
                viewer_loadcomb_override_patch_unresolved_entry_count
            ),
            "viewer_loadcomb_override_patch_appended_combo_count": int(
                viewer_loadcomb_override_patch_appended_combo_count
            ),
            "viewer_loadcomb_override_patch_replaced_combo_count": int(
                viewer_loadcomb_override_patch_replaced_combo_count
            ),
            "viewer_loadcomb_override_applied_source_json_exists": bool(
                loadcomb_override_applied_source_json_out_path is not None
                and loadcomb_override_applied_source_json_out_path.exists()
            ),
            "direct_patch_action_family_counts": direct_patch_action_family_counts,
            "supported_action_family_counts": supported_action_family_counts,
            "special_member_direct_patch_action_family_counts": special_member_direct_patch_action_family_counts,
            "special_member_supported_action_family_counts": special_member_supported_action_family_counts,
        "instruction_sidecar_action_family_counts": instruction_sidecar_action_family_counts,
        "special_member_instruction_sidecar_action_family_counts": special_member_instruction_sidecar_action_family_counts,
        "instruction_sidecar_review_priority_counts": instruction_sidecar_review_priority_counts,
            "instruction_sidecar_followup_type_counts": instruction_sidecar_followup_type_counts,
            "instruction_sidecar_audit_only_change_count": instruction_sidecar_audit_only_change_count,
            "instruction_sidecar_audit_only_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
            "instruction_sidecar_zero_touch_verified_change_count": instruction_sidecar_zero_touch_verified_change_count,
            "instruction_sidecar_zero_touch_verified_action_family_counts": instruction_sidecar_zero_touch_verified_action_family_counts,
            "special_member_instruction_sidecar_zero_touch_verified_action_family_counts": (
                special_member_instruction_sidecar_zero_touch_verified_action_family_counts
            ),
            "instruction_sidecar_manual_input_change_count": instruction_sidecar_manual_input_change_count,
            "instruction_sidecar_manual_input_action_family_counts": instruction_sidecar_manual_input_action_family_counts,
        "audit_review_manifest_change_count": instruction_sidecar_audit_only_change_count,
        "audit_review_manifest_action_family_counts": instruction_sidecar_audit_only_action_family_counts,
        "audit_review_packet_count": audit_review_packet_count,
        "audit_review_packet_action_family_counts": audit_review_packet_action_family_counts,
        "audit_review_packet_followup_type_counts": audit_review_packet_followup_type_counts,
        "audit_review_packet_review_priority_counts": audit_review_packet_review_priority_counts,
        "audit_review_packet_file_count": audit_review_packet_file_count,
        "audit_review_packet_file_action_family_counts": audit_review_packet_file_action_family_counts,
        "audit_review_queue_item_count": audit_review_queue_item_count,
        "audit_review_queue_pending_count": audit_review_queue_pending_count,
        "audit_review_queue_acknowledged_count": audit_review_queue_acknowledged_count,
        "audit_review_queue_status_counts": audit_review_queue_status_counts,
        "audit_review_queue_action_family_counts": audit_review_queue_action_family_counts,
        "audit_review_followup_item_count": audit_review_followup_item_count,
        "audit_review_followup_open_item_count": audit_review_followup_open_item_count,
        "audit_review_followup_closed_item_count": audit_review_followup_closed_item_count,
        "audit_review_followup_action_counts": audit_review_followup_action_counts,
        "audit_review_followup_action_label": audit_review_followup_action_label,
        "audit_review_followup_owner_counts": audit_review_followup_owner_counts,
        "audit_review_followup_owner_label": audit_review_followup_owner_label,
        "audit_review_followup_review_owner_counts": audit_review_followup_review_owner_counts,
        "audit_review_followup_review_owner_label": audit_review_followup_review_owner_label,
        "audit_review_followup_status_counts": audit_review_followup_status_counts,
        "audit_review_followup_status_label": audit_review_followup_status_label,
        "audit_review_followup_sla_state_counts": audit_review_followup_sla_state_counts,
        "audit_review_followup_sla_state_label": audit_review_followup_sla_state_label,
        "audit_review_followup_age_bucket_counts": audit_review_followup_age_bucket_counts,
        "audit_review_followup_age_bucket_label": audit_review_followup_age_bucket_label,
        "audit_review_followup_overdue_item_count": audit_review_followup_overdue_item_count,
        "audit_review_followup_oldest_open_age_hours": audit_review_followup_oldest_open_age_hours,
        "audit_review_followup_oldest_open_packet_id": audit_review_followup_oldest_open_packet_id,
        "audit_review_followup_reference_time_utc": audit_review_followup_reference_time_utc,
        "audit_review_followup_sla_policy_label": audit_review_followup_sla_policy_label,
        "audit_review_followup_mode": audit_review_followup_mode,
        "audit_review_resolution_item_count": audit_review_resolution_item_count,
        "audit_review_resolution_file_count": audit_review_resolution_file_count,
        "audit_review_resolution_open_item_count": audit_review_resolution_open_item_count,
        "audit_review_resolution_closed_item_count": audit_review_resolution_closed_item_count,
        "audit_review_resolution_pending_item_count": audit_review_resolution_pending_item_count,
        "audit_review_resolution_open_revision_count": audit_review_resolution_open_revision_count,
        "audit_review_resolution_closed_packet_count": audit_review_resolution_closed_packet_count,
        "audit_review_resolution_action_counts": audit_review_resolution_action_counts,
        "audit_review_resolution_action_label": audit_review_resolution_action_label,
        "audit_review_resolution_owner_counts": audit_review_resolution_owner_counts,
        "audit_review_resolution_owner_label": audit_review_resolution_owner_label,
        "audit_review_resolution_status_counts": audit_review_resolution_status_counts,
        "audit_review_resolution_status_label": audit_review_resolution_status_label,
        "audit_review_resolution_mode": audit_review_resolution_mode,
        "unsupported_reason_counts": unsupported_reason_counts,
        },
        "artifacts": {
            "source_mgt": str(source_mgt_path),
            "output_mgt": str(output_mgt_path),
            "section_override_patch_json": str(section_override_patch_json_path) if section_override_patch_json_path is not None else "",
            "section_override_applied_source_json": str(section_override_applied_source_json_out_path) if section_override_applied_source_json_out_path is not None else "",
            "loadcomb_override_patch_json": str(loadcomb_override_patch_json_path) if loadcomb_override_patch_json_path is not None else "",
            "loadcomb_override_applied_source_json": str(loadcomb_override_applied_source_json_out_path) if loadcomb_override_applied_source_json_out_path is not None else "",
            "patch_manifest_json": str(patch_manifest_out_path),
            "instruction_sidecar_json": str(instruction_sidecar_out_path),
            "audit_review_manifest_json": str(audit_review_manifest_out_path),
            "audit_review_packet_manifest_json": str(audit_review_packet_manifest_out_path),
            "audit_review_packet_directory": str(audit_review_packet_dir_out_path),
            "audit_review_queue_manifest_json": str(audit_review_queue_manifest_out_path),
            "audit_review_queue_status_directory": str(audit_review_queue_status_dir_out_path),
            "audit_review_followup_manifest_json": str(audit_review_followup_manifest_out_path),
            "audit_review_resolution_manifest_json": str(audit_review_resolution_manifest_out_path),
            "audit_review_resolution_directory": str(audit_review_resolution_dir_out_path),
            "rebar_payload_projection_json": str(rebar_payload_projection_json_path),
            "connection_detailing_payload_projection_json": str(connection_detailing_payload_projection_json_path),
            "detailing_payload_projection_json": str(detailing_payload_projection_json_path),
            "loadcomb_preview_mgt": str(loadcomb_preview_out_path),
            "loadcomb_roundtrip_report_json": str(loadcomb_roundtrip_report_out_path),
            "source_output_mgt_diff_json": str(source_output_diff_json_out_path),
            "source_output_mgt_diff_preview_txt": str(source_output_diff_preview_out_path),
            "source_output_mgt_diff_window_json": str(source_output_diff_window_json_out_path),
            "source_output_mgt_diff_window_preview_txt": str(source_output_diff_window_preview_out_path),
        },
    }
    _write_json(report_out_path, report)
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
