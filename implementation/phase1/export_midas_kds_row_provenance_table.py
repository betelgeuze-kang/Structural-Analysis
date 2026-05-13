#!/usr/bin/env python3
"""Export full MIDAS KDS row-level provenance tables to JSON and CSV."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlencode
from typing import Any

from runtime_contracts import InputContractError, validate_input_contract

from implementation.phase1 import generate_structural_optimization_visualization_viewer as viewer_module


INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["model_json", "kds_report", "out_json", "out_csv", "out_report"],
    "properties": {
        "model_json": {"type": "string", "minLength": 1},
        "kds_report": {"type": "string", "minLength": 1},
        "out_json": {"type": "string", "minLength": 1},
        "out_csv": {"type": "string", "minLength": 1},
        "out_report": {"type": "string", "minLength": 1},
    },
}

VIEWER_REVERSE_SYNC_CONTRACT_VERSION = str(
    getattr(viewer_module, "ROW_PROVENANCE_REVERSE_SYNC_CONTRACT_VERSION", "viewer_subset_reverse_jump_v2")
)
DEFAULT_VIEWER_READING_MODE = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_VIEWER_MODE", "midas")
)
DEFAULT_VIEWER_FOCUS_TARGET = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_FOCUS_TARGET", "interactive3d")
)
DEFAULT_VIEWER_CODECHECK_SURFACE = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_SURFACE", "drilldown")
)
DEFAULT_VIEWER_RESULTS_CARD = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_CARD", "envelope")
)
DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_SAMPLE_INDEX", 0)
)
DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_DETAIL_ITEM_INDEX", 0)
)
DEFAULT_VIEWER_RESULTS_COMPANION = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_COMPANION", "interactive")
)
DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_COMPANION_ITEM_INDEX", 0)
)
DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_COMPANION_FOCUS_KEY", "chart-marker:0")
)
DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_COMPANION_SELECTION_KEY", "results-companion:interactive")
)
DEFAULT_VIEWER_RESULTS_DETAIL_BLOCK = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_DETAIL_BLOCK", "chart")
)
DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_DETAIL_FOCUS_KEY", "chart-marker:0")
)
DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_RESULTS_DETAIL_SELECTION_KEY", "results-detail:chart")
)
DEFAULT_VIEWER_CODECHECK_COMPANION = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_COMPANION", "detail")
)
DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_COMPANION_ITEM_INDEX", 0)
)
DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_COMPANION_FOCUS_KEY", "row-provenance:jump-row")
)
DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_COMPANION_SELECTION_KEY", "codecheck-companion:detail")
)
DEFAULT_VIEWER_CODECHECK_DETAIL_BLOCK = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_DETAIL_BLOCK", "row-provenance")
)
DEFAULT_VIEWER_CODECHECK_APPENDIX_BLOCK = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_APPENDIX_BLOCK", "subset-summary")
)
DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_DETAIL_ITEM_INDEX", 0)
)
DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_DETAIL_FOCUS_KEY", "row-provenance:jump-row")
)
DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_DETAIL_SELECTION_KEY", "codecheck-detail:row-provenance")
)
DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX = int(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_APPENDIX_ITEM_INDEX", 0)
)
DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_APPENDIX_FOCUS_KEY", "subset:current-slice")
)
DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_CODECHECK_APPENDIX_SELECTION_KEY", "codecheck-appendix:subset-summary")
)
DEFAULT_VIEWER_SLICE_RESULTS_COMPANION = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_SLICE_RESULTS_COMPANION", "checks")
)
DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_SLICE_CODECHECK_COMPANION", "reviewer-appendix")
)
DEFAULT_VIEWER_INTERACTIVE_DETAIL_MORE = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_INTERACTIVE_DETAIL_MORE", "open")
)
DEFAULT_VIEWER_OVERLAY_DETAIL_MORE = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_OVERLAY_DETAIL_MORE", "open")
)
DEFAULT_VIEWER_BASELINE_SECONDARY = str(
    getattr(viewer_module, "DEFAULT_ROW_PROVENANCE_BASELINE_SECONDARY", "elevation")
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "")).strip("_").lower()
    return slug or "item"


def _viewer_row_ref(
    *,
    combination_name: str,
    row_index: int,
    member_id: str = "",
    case_id: str = "",
) -> str:
    if hasattr(viewer_module, "_viewer_row_ref"):
        return str(
            viewer_module._viewer_row_ref(
                combination_name=combination_name,
                row_index=row_index,
                member_id=member_id,
                case_id=case_id,
            )
        )
    tokens = [
        str(combination_name or "").replace("::", ":").strip(),
        str(int(row_index)),
        str(member_id or "").replace("::", ":").strip(),
        str(case_id or "").replace("::", ":").strip(),
    ]
    return "::".join(tokens)


def _focus_member_id(
    *,
    baseline_focus_member_id: str = "",
    member_id: str = "",
    case_id: str = "",
) -> str:
    return (
        str(baseline_focus_member_id or "").strip()
        or str(member_id or "").strip()
        or str(case_id or "").strip()
    )


def _int_or_default(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _viewer_reverse_sync_state(
    *,
    combination_name: str,
    combination_highlights_by_name: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    highlight = combination_highlights_by_name.get(str(combination_name), {})
    if not isinstance(highlight, dict):
        highlight = {}
    return {
        "viewer_reading_mode": DEFAULT_VIEWER_READING_MODE,
        "viewer_focus_target": DEFAULT_VIEWER_FOCUS_TARGET,
        "viewer_results_card": str(
            highlight.get("recommended_results_card", DEFAULT_VIEWER_RESULTS_CARD) or DEFAULT_VIEWER_RESULTS_CARD
        ).strip().lower(),
        "viewer_results_series_index": max(
            _int_or_default(
                highlight.get(
                    "recommended_results_series_index_label",
                    highlight.get("recommended_results_series_index", 0),
                ),
                0,
            ),
            0,
        ),
        "viewer_results_sample_index": DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX,
        "viewer_results_detail_item_index": DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX,
        "viewer_results_companion_item_index": DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX,
        "viewer_results_companion_focus_key": DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY,
        "viewer_results_companion_selection_key": DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY,
        "viewer_results_detail_focus_key": DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY,
        "viewer_results_detail_selection_key": DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY,
        "viewer_codecheck_filtered_row_index": 0,
        "viewer_codecheck_surface": DEFAULT_VIEWER_CODECHECK_SURFACE,
        "viewer_codecheck_clause_index": 0,
        "viewer_codecheck_hazard_index": 0,
        "viewer_codecheck_rule_family_index": 0,
        "viewer_results_companion": DEFAULT_VIEWER_RESULTS_COMPANION,
        "viewer_results_detail_block": DEFAULT_VIEWER_RESULTS_DETAIL_BLOCK,
        "viewer_codecheck_companion": DEFAULT_VIEWER_CODECHECK_COMPANION,
        "viewer_codecheck_companion_item_index": DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX,
        "viewer_codecheck_companion_focus_key": DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY,
        "viewer_codecheck_companion_selection_key": DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY,
        "viewer_codecheck_detail_block": DEFAULT_VIEWER_CODECHECK_DETAIL_BLOCK,
        "viewer_codecheck_appendix_block": DEFAULT_VIEWER_CODECHECK_APPENDIX_BLOCK,
        "viewer_codecheck_detail_item_index": DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX,
        "viewer_codecheck_appendix_item_index": DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX,
        "viewer_codecheck_detail_focus_key": DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY,
        "viewer_codecheck_appendix_focus_key": DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY,
        "viewer_codecheck_detail_selection_key": DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY,
        "viewer_codecheck_appendix_selection_key": DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY,
        "viewer_slice_results_companion": DEFAULT_VIEWER_SLICE_RESULTS_COMPANION,
        "viewer_slice_codecheck_companion": DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION,
        "viewer_interactive_detail_more": DEFAULT_VIEWER_INTERACTIVE_DETAIL_MORE,
        "viewer_overlay_detail_more": DEFAULT_VIEWER_OVERLAY_DETAIL_MORE,
        "viewer_baseline_secondary": DEFAULT_VIEWER_BASELINE_SECONDARY,
        "reverse_sync_contract_version": VIEWER_REVERSE_SYNC_CONTRACT_VERSION,
    }


def _viewer_url_for_row(
    *,
    combination_name: str,
    row_index: int | None = None,
    clause_label: str = "",
    hazard_type: str = "",
    rule_family: str = "",
    source: str = "row_provenance_csv",
    subset_key: str = "",
    subset_type: str = "",
    row_ref: str = "",
    focus_member: str = "",
    member_id: str = "",
    case_id: str = "",
    baseline_focus_member_id: str = "",
    subset_csv: str = "",
    subset_manifest: str = "",
    view_mode: str = "",
    focus: str = "",
    results_card: str = "",
    results_series_index: int | None = None,
    results_sample_index: int | None = None,
    results_detail_item_index: int | None = None,
    results_companion_item_index: int | None = None,
    results_companion_selection_key: str = "",
    results_companion_focus_key: str = "",
    results_detail_focus_key: str = "",
    results_detail_selection_key: str = "",
    codecheck_filtered_row_index: int | None = None,
    codecheck_clause_index: int | None = None,
    codecheck_hazard_index: int | None = None,
    codecheck_rule_family_index: int | None = None,
    results_companion: str = "",
    results_detail_block: str = "",
    codecheck_surface: str = "",
    codecheck_companion: str = "",
    codecheck_companion_item_index: int | None = None,
    codecheck_companion_selection_key: str = "",
    codecheck_companion_focus_key: str = "",
    codecheck_detail_block: str = "",
    codecheck_appendix_block: str = "",
    codecheck_detail_item_index: int | None = None,
    codecheck_appendix_item_index: int | None = None,
    codecheck_detail_focus_key: str = "",
    codecheck_appendix_focus_key: str = "",
    codecheck_detail_selection_key: str = "",
    codecheck_appendix_selection_key: str = "",
    interactive_detail_more: str = "",
    overlay_detail_more: str = "",
    baseline_secondary: str = "",
) -> str:
    viewer_path = (Path(__file__).resolve().parent / "release" / "visualization" / "structural_optimization_viewer.html").resolve()
    params = {
        "source": str(source or "row_provenance_csv"),
        "combination": combination_name,
    }
    if row_index is not None:
        params["row"] = str(int(row_index))
    if clause_label:
        params["clause"] = clause_label
    if hazard_type:
        params["hazard"] = hazard_type
    if rule_family:
        params["rule_family"] = rule_family
    if subset_key:
        params["subset_key"] = subset_key
    if subset_type:
        params["subset_type"] = subset_type
    if row_ref:
        params["row_ref"] = row_ref
    if focus_member:
        params["focus_member"] = focus_member
    if member_id:
        params["member_id"] = member_id
    if case_id:
        params["case_id"] = case_id
    if baseline_focus_member_id:
        params["baseline_focus_member_id"] = baseline_focus_member_id
    if subset_csv:
        params["subset_csv"] = subset_csv
    if subset_manifest:
        params["subset_manifest"] = subset_manifest
    if view_mode:
        params["view"] = view_mode
    if focus:
        params["focus"] = focus
    if results_card:
        params["results_card"] = results_card
    if results_series_index is not None:
        params["results_series"] = str(int(results_series_index))
    if results_sample_index is not None:
        params["results_sample"] = str(int(results_sample_index))
    if results_detail_item_index is not None:
        params["results_detail_item_index"] = str(int(results_detail_item_index))
    if results_companion_item_index is not None:
        params["results_companion_item_index"] = str(int(results_companion_item_index))
    if results_companion_focus_key:
        params["results_companion_focus_key"] = str(results_companion_focus_key)
    if results_companion_selection_key:
        params["results_companion_selection_key"] = str(results_companion_selection_key)
    if results_detail_focus_key:
        params["results_detail_focus_key"] = str(results_detail_focus_key)
    if results_detail_selection_key:
        params["results_detail_selection_key"] = str(results_detail_selection_key)
    if codecheck_filtered_row_index is not None:
        params["codecheck_filtered_row"] = str(int(codecheck_filtered_row_index))
    if codecheck_clause_index is not None:
        params["codecheck_clause_index"] = str(int(codecheck_clause_index))
    if codecheck_hazard_index is not None:
        params["codecheck_hazard_index"] = str(int(codecheck_hazard_index))
    if codecheck_rule_family_index is not None:
        params["codecheck_rule_family_index"] = str(int(codecheck_rule_family_index))
    if results_companion:
        params["results_companion"] = results_companion
    if results_detail_block:
        params["results_detail_block"] = results_detail_block
    if codecheck_surface:
        params["codecheck_surface"] = codecheck_surface
    if codecheck_companion:
        params["codecheck_companion"] = codecheck_companion
    if codecheck_companion_item_index is not None:
        params["codecheck_companion_item_index"] = str(int(codecheck_companion_item_index))
    if codecheck_companion_focus_key:
        params["codecheck_companion_focus_key"] = str(codecheck_companion_focus_key)
    if codecheck_companion_selection_key:
        params["codecheck_companion_selection_key"] = str(codecheck_companion_selection_key)
    if codecheck_detail_block:
        params["codecheck_detail_block"] = codecheck_detail_block
    if codecheck_appendix_block:
        params["codecheck_appendix_block"] = codecheck_appendix_block
    if codecheck_detail_item_index is not None:
        params["codecheck_detail_item_index"] = str(int(codecheck_detail_item_index))
    if codecheck_appendix_item_index is not None:
        params["codecheck_appendix_item_index"] = str(int(codecheck_appendix_item_index))
    if codecheck_detail_focus_key:
        params["codecheck_detail_focus_key"] = str(codecheck_detail_focus_key)
    if codecheck_appendix_focus_key:
        params["codecheck_appendix_focus_key"] = str(codecheck_appendix_focus_key)
    if codecheck_detail_selection_key:
        params["codecheck_detail_selection_key"] = str(codecheck_detail_selection_key)
    if codecheck_appendix_selection_key:
        params["codecheck_appendix_selection_key"] = str(codecheck_appendix_selection_key)
    if interactive_detail_more:
        params["interactive_detail_more"] = interactive_detail_more
    if overlay_detail_more:
        params["overlay_detail_more"] = overlay_detail_more
    if baseline_secondary:
        params["baseline_secondary"] = baseline_secondary
    return f"{viewer_path.as_uri()}?{urlencode(params)}"


def _results_companion_focus_key(companion: str, *, series_index: int, sample_index: int) -> str:
    normalized = str(companion or "").strip().lower()
    if normalized == "interactive":
        return f"chart-marker:{max(int(sample_index), 0)}"
    if normalized == "compare":
        return "compare:0"
    if normalized == "checks":
        return "check:0"
    if normalized == "footer":
        return "report-link"
    if normalized == "metrics":
        return "metric:0"
    return DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY


def _results_companion_selection_key(companion: str) -> str:
    normalized = str(companion or "").strip().lower()
    if normalized:
        return f"results-companion:{normalized}"
    return DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY


def _results_detail_focus_key(detail_block: str, *, series_index: int, sample_index: int) -> str:
    normalized = str(detail_block or "").strip().lower()
    if normalized == "chart":
        return f"chart-marker:{max(int(sample_index), 0)}"
    if normalized == "series":
        return f"series:{max(int(series_index), 0)}"
    if normalized == "sample":
        return "pill:sample-value"
    if normalized == "checks":
        return "check:0"
    if normalized == "footer":
        return "report-link"
    if normalized == "metrics":
        return "metric:0"
    return DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY


def _results_detail_selection_key(detail_block: str) -> str:
    normalized = str(detail_block or "").strip().lower()
    if normalized:
        return f"results-detail:{normalized}"
    return DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY


def _codecheck_companion_focus_key(companion: str, *, row_ref: str) -> str:
    normalized = str(companion or "").strip().lower()
    if normalized == "reviewer-appendix":
        return "subset:current-slice"
    if normalized == "clause-filter":
        return "clause:all"
    if normalized == "table" and str(row_ref or "").strip():
        return f"row:{row_ref}"
    if normalized in {"summary", "shell"}:
        return "summary:review-rows"
    return DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY


def _codecheck_companion_selection_key(companion: str, *, row_ref: str) -> str:
    if str(row_ref or "").strip():
        return f"row:{row_ref}"
    normalized = str(companion or "").strip().lower()
    if normalized:
        return f"codecheck-companion:{normalized}"
    return DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY


def _codecheck_detail_focus_key(detail_block: str, *, row_ref: str) -> str:
    normalized = str(detail_block or "").strip().lower()
    if normalized == "clause-drilldown":
        return "clause-drilldown:title"
    if normalized == "member-inventory":
        return "member-inventory:summary"
    if normalized == "clause-provenance":
        return "clause-provenance:summary"
    if normalized == "row-provenance":
        return "row-provenance:jump-row"
    return DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY


def _codecheck_detail_selection_key(detail_block: str, *, row_ref: str) -> str:
    if str(row_ref or "").strip():
        return f"row:{row_ref}"
    normalized = str(detail_block or "").strip().lower()
    if normalized:
        return f"codecheck-detail:{normalized}"
    return DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY


def _codecheck_appendix_focus_key(appendix_block: str) -> str:
    normalized = str(appendix_block or "").strip().lower()
    if normalized == "hazard-filter":
        return "hazard:all"
    if normalized == "rule-family-filter":
        return "rule-family:all"
    if normalized == "overview":
        return "subset:overview"
    return DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY


def _codecheck_appendix_selection_key(appendix_block: str, *, subset_key: str = "") -> str:
    if str(subset_key or "").strip():
        return f"subset:{str(subset_key or '').strip()}"
    normalized = str(appendix_block or "").strip().lower()
    if normalized:
        return f"codecheck-appendix:{normalized}"
    return DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY


def _flatten_rows(
    table_by_name: dict[str, Any],
    *,
    combination_highlights_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    def _dimension_options(rows: list[dict[str, Any]], key: str) -> list[str]:
        counts: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get(key, "") or "").strip()
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
        return [
            label
            for label, _count in sorted(
                counts.items(),
                key=lambda item: (-int(item[1]), str(item[0])),
            )
        ]

    def _option_index(options: list[str], label: str) -> int:
        normalized_label = str(label or "").strip()
        if not normalized_label:
            return 0
        try:
            return options.index(normalized_label)
        except ValueError:
            return 0

    rows_out: list[dict[str, Any]] = []
    for combination_name, payload in sorted(table_by_name.items(), key=lambda item: str(item[0])):
        if not isinstance(payload, dict):
            continue
        reverse_sync_state = _viewer_reverse_sync_state(
            combination_name=str(combination_name),
            combination_highlights_by_name=combination_highlights_by_name,
        )
        geometry_bridge_summary_label = str(payload.get("geometry_bridge_summary_label", "") or "").strip()
        geometry_bridge_source_label = str(payload.get("geometry_bridge_source_label", "") or "").strip()
        geometry_bridge_contract_label = str(payload.get("geometry_bridge_contract_label", "") or "").strip()
        table_rows = [
            row for row in (payload.get("table_rows") or [])
            if isinstance(row, dict)
        ]
        clause_options = _dimension_options(table_rows, "clause_label")
        hazard_options = _dimension_options(table_rows, "hazard_type")
        rule_family_options = _dimension_options(table_rows, "rule_family")
        for row_index, row in enumerate(payload.get("table_rows") or []):
            if not isinstance(row, dict):
                continue
            row_index_value = int(row.get("row_index", row_index) or row_index)
            clause_label = str(row.get("clause_label", "") or "")
            hazard_type = str(row.get("hazard_type", "") or "")
            rule_family = str(row.get("rule_family", "") or "")
            filtered_rows = [
                candidate for candidate in table_rows
                if str(candidate.get("clause_label", "") or "").strip() == clause_label.strip()
                and str(candidate.get("hazard_type", "") or "").strip() == hazard_type.strip()
                and str(candidate.get("rule_family", "") or "").strip() == rule_family.strip()
            ]
            filtered_row_display_index = next(
                (
                    display_index
                    for display_index, candidate in enumerate(filtered_rows)
                    if int(candidate.get("row_index", display_index) or display_index) == row_index_value
                ),
                0,
            )
            baseline_focus_member_id = str(row.get("baseline_focus_member_id", "") or "")
            member_id = str(row.get("member_id", "") or "")
            case_id = str(row.get("case_id", "") or "")
            focus_member = _focus_member_id(
                baseline_focus_member_id=baseline_focus_member_id,
                member_id=member_id,
                case_id=case_id,
            )
            viewer_row_ref = _viewer_row_ref(
                combination_name=str(combination_name),
                row_index=row_index_value,
                member_id=member_id,
                case_id=case_id,
            )
            viewer_results_card = str(reverse_sync_state.get("viewer_results_card", "") or "")
            viewer_results_series_index = int(reverse_sync_state.get("viewer_results_series_index", 0) or 0)
            viewer_results_sample_index = int(reverse_sync_state.get("viewer_results_sample_index", DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX) or 0)
            viewer_results_companion = str(reverse_sync_state.get("viewer_results_companion", "") or "")
            viewer_results_detail_block = str(reverse_sync_state.get("viewer_results_detail_block", "") or "")
            viewer_codecheck_companion = str(reverse_sync_state.get("viewer_codecheck_companion", "") or "")
            viewer_codecheck_detail_block = str(reverse_sync_state.get("viewer_codecheck_detail_block", "") or "")
            viewer_codecheck_appendix_block = str(reverse_sync_state.get("viewer_codecheck_appendix_block", "") or "")
            viewer_results_companion_focus_key = _results_companion_focus_key(
                viewer_results_companion,
                series_index=viewer_results_series_index,
                sample_index=viewer_results_sample_index,
            )
            viewer_results_companion_selection_key = _results_companion_selection_key(
                viewer_results_companion,
            )
            viewer_results_detail_focus_key = _results_detail_focus_key(
                viewer_results_detail_block,
                series_index=viewer_results_series_index,
                sample_index=viewer_results_sample_index,
            )
            viewer_results_detail_selection_key = _results_detail_selection_key(
                viewer_results_detail_block,
            )
            combination_subset_key = f"combination:{combination_name}"
            viewer_codecheck_companion_focus_key = _codecheck_companion_focus_key(
                viewer_codecheck_companion,
                row_ref=viewer_row_ref,
            )
            viewer_codecheck_companion_selection_key = _codecheck_companion_selection_key(
                viewer_codecheck_companion,
                row_ref=viewer_row_ref,
            )
            viewer_codecheck_detail_focus_key = _codecheck_detail_focus_key(
                viewer_codecheck_detail_block,
                row_ref=viewer_row_ref,
            )
            viewer_codecheck_detail_selection_key = _codecheck_detail_selection_key(
                viewer_codecheck_detail_block,
                row_ref=viewer_row_ref,
            )
            viewer_codecheck_appendix_focus_key = _codecheck_appendix_focus_key(
                viewer_codecheck_appendix_block,
            )
            viewer_codecheck_appendix_selection_key = _codecheck_appendix_selection_key(
                viewer_codecheck_appendix_block,
                subset_key=combination_subset_key,
            )
            export_row = {
                "combination_name": str(combination_name),
                "row_index": row_index_value,
                "viewer_row_ref": viewer_row_ref,
                "member_id": member_id,
                "case_id": case_id,
                "member_type": str(row.get("member_type", "") or ""),
                "component": str(row.get("component", "") or ""),
                "hazard_type": str(row.get("hazard_type", "") or ""),
                "rule_family": str(row.get("rule_family", "") or ""),
                "topology_type": str(row.get("topology_type", "") or ""),
                "clause_label": str(row.get("clause_label", "") or ""),
                "clause_title_label": str(row.get("clause_title_label", "") or ""),
                "clause_family_label": str(row.get("clause_family_label", "") or ""),
                "dcr_label": str(row.get("dcr_label", "") or ""),
                "demand_label": str(row.get("demand_label", "") or ""),
                "capacity_label": str(row.get("capacity_label", "") or ""),
                "combination_scale_label": str(row.get("combination_scale_label", "") or ""),
                "baseline_focus_member_id": baseline_focus_member_id,
                "viewer_focus_member_id": focus_member,
                "viewer_reading_mode": str(reverse_sync_state.get("viewer_reading_mode", "") or ""),
                "viewer_focus_target": str(reverse_sync_state.get("viewer_focus_target", "") or ""),
                "viewer_results_card": viewer_results_card,
                "viewer_results_series_index": viewer_results_series_index,
                "viewer_results_sample_index": viewer_results_sample_index,
                "viewer_results_detail_item_index": int(reverse_sync_state.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX) or 0),
                "viewer_results_companion_item_index": int(reverse_sync_state.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX) or 0),
                "viewer_results_companion_selection_key": viewer_results_companion_selection_key,
                "viewer_results_companion_focus_key": viewer_results_companion_focus_key,
                "viewer_results_detail_selection_key": viewer_results_detail_selection_key,
                "viewer_results_detail_focus_key": viewer_results_detail_focus_key,
                "viewer_codecheck_filtered_row_index": int(filtered_row_display_index),
                "viewer_codecheck_clause_index": int(_option_index(clause_options, clause_label)),
                "viewer_codecheck_hazard_index": int(_option_index(hazard_options, hazard_type)),
                "viewer_codecheck_rule_family_index": int(_option_index(rule_family_options, rule_family)),
                "viewer_results_companion": viewer_results_companion,
                "viewer_results_detail_block": viewer_results_detail_block,
                "viewer_codecheck_surface": str(reverse_sync_state.get("viewer_codecheck_surface", "") or ""),
                "viewer_codecheck_companion": viewer_codecheck_companion,
                "viewer_codecheck_companion_item_index": int(reverse_sync_state.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX) or 0),
                "viewer_codecheck_companion_selection_key": viewer_codecheck_companion_selection_key,
                "viewer_codecheck_companion_focus_key": viewer_codecheck_companion_focus_key,
                "viewer_codecheck_detail_block": viewer_codecheck_detail_block,
                "viewer_codecheck_appendix_block": viewer_codecheck_appendix_block,
                "viewer_codecheck_detail_item_index": int(reverse_sync_state.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX) or 0),
                "viewer_codecheck_appendix_item_index": int(reverse_sync_state.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX) or 0),
                "viewer_codecheck_detail_selection_key": viewer_codecheck_detail_selection_key,
                "viewer_codecheck_detail_focus_key": viewer_codecheck_detail_focus_key,
                "viewer_codecheck_appendix_selection_key": viewer_codecheck_appendix_selection_key,
                "viewer_codecheck_appendix_focus_key": viewer_codecheck_appendix_focus_key,
                "viewer_interactive_detail_more": str(reverse_sync_state.get("viewer_interactive_detail_more", "") or ""),
                "viewer_overlay_detail_more": str(reverse_sync_state.get("viewer_overlay_detail_more", "") or ""),
                "viewer_baseline_secondary": str(reverse_sync_state.get("viewer_baseline_secondary", "") or ""),
                "reverse_sync_contract_version": str(reverse_sync_state.get("reverse_sync_contract_version", "") or ""),
                "bridge_available": bool(row.get("bridge_available", False)),
                "bridge_source_label": str(row.get("bridge_source_label", "") or ""),
                "bridge_contract_label": str(row.get("bridge_contract_label", "") or ""),
                "bridge_summary_label": str(row.get("bridge_summary_label", "") or ""),
                "bridge_match_strategy_label": str(row.get("bridge_match_strategy_label", "") or ""),
                "bridge_row_provenance_summary_label": str(row.get("bridge_row_provenance_summary_label", "") or ""),
                "bridge_row_provenance_top_row_label": str(row.get("bridge_row_provenance_top_row_label", "") or ""),
                "bridge_row_provenance_row_count_label": str(row.get("bridge_row_provenance_row_count_label", "") or ""),
                "bridge_row_provenance_combination_count_label": str(row.get("bridge_row_provenance_combination_count_label", "") or ""),
                "bridge_row_provenance_clause_count_label": str(row.get("bridge_row_provenance_clause_count_label", "") or ""),
                "bridge_row_provenance_component_count_label": str(row.get("bridge_row_provenance_component_count_label", "") or ""),
                "bridge_row_provenance_mode_label": str(row.get("bridge_row_provenance_mode_label", "") or ""),
                "bridge_review_keys_label": str(row.get("bridge_review_keys_label", "") or ""),
                "bridge_member_inventory_count_label": str(row.get("bridge_member_inventory_count_label", "") or ""),
                "bridge_member_inventory_summary_label": str(row.get("bridge_member_inventory_summary_label", "") or ""),
                "bridge_member_inventory_member_type_label": str(row.get("bridge_member_inventory_member_type_label", "") or ""),
                "bridge_member_inventory_source_label": str(row.get("bridge_member_inventory_source_label", "") or ""),
                "clause_provenance_summary_label": str(row.get("clause_provenance_summary_label", "") or ""),
                "clause_provenance_inventory_label": str(row.get("clause_provenance_inventory_label", "") or ""),
                "clause_combo_row_count_label": str(row.get("clause_combo_row_count_label", "") or ""),
                "clause_combo_member_count_label": str(row.get("clause_combo_member_count_label", "") or ""),
                "clause_component_mix_label": str(row.get("clause_component_mix_label", "") or ""),
                "clause_hazard_mix_label": str(row.get("clause_hazard_mix_label", "") or ""),
                "clause_rule_family_mix_label": str(row.get("clause_rule_family_mix_label", "") or ""),
                "clause_topology_mix_label": str(row.get("clause_topology_mix_label", "") or ""),
                "clause_governing_row_label": str(row.get("clause_governing_row_label", "") or ""),
                "geometry_bridge_summary_label": geometry_bridge_summary_label,
                "geometry_bridge_source_label": geometry_bridge_source_label,
                "geometry_bridge_contract_label": geometry_bridge_contract_label,
                "viewer_row_url": _viewer_url_for_row(
                    combination_name=str(combination_name),
                    row_index=row_index_value,
                    clause_label=clause_label,
                    hazard_type=hazard_type,
                    rule_family=rule_family,
                    source="row_provenance_csv",
                    subset_key=combination_subset_key,
                    subset_type="combination",
                    row_ref=viewer_row_ref,
                    focus_member=focus_member,
                    member_id=member_id,
                    case_id=case_id,
                    baseline_focus_member_id=baseline_focus_member_id,
                    view_mode=str(reverse_sync_state.get("viewer_reading_mode", "") or ""),
                    focus=str(reverse_sync_state.get("viewer_focus_target", "") or ""),
                    results_card=viewer_results_card,
                    results_series_index=viewer_results_series_index,
                    results_sample_index=viewer_results_sample_index,
                    results_detail_item_index=int(reverse_sync_state.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX) or 0),
                    results_companion_item_index=int(reverse_sync_state.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX) or 0),
                    results_companion_selection_key=viewer_results_companion_selection_key,
                    results_companion_focus_key=viewer_results_companion_focus_key,
                    results_detail_selection_key=viewer_results_detail_selection_key,
                    results_detail_focus_key=viewer_results_detail_focus_key,
                    codecheck_filtered_row_index=int(filtered_row_display_index),
                    codecheck_clause_index=int(_option_index(clause_options, clause_label)),
                    codecheck_hazard_index=int(_option_index(hazard_options, hazard_type)),
                    codecheck_rule_family_index=int(_option_index(rule_family_options, rule_family)),
                    results_companion=viewer_results_companion,
                    results_detail_block=viewer_results_detail_block,
                    codecheck_surface=str(reverse_sync_state.get("viewer_codecheck_surface", "") or ""),
                    codecheck_companion=viewer_codecheck_companion,
                    codecheck_companion_item_index=int(reverse_sync_state.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX) or 0),
                    codecheck_companion_selection_key=viewer_codecheck_companion_selection_key,
                    codecheck_companion_focus_key=viewer_codecheck_companion_focus_key,
                    codecheck_detail_block=viewer_codecheck_detail_block,
                    codecheck_appendix_block=viewer_codecheck_appendix_block,
                    codecheck_detail_item_index=int(reverse_sync_state.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX) or 0),
                    codecheck_appendix_item_index=int(reverse_sync_state.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX) or 0),
                    codecheck_detail_selection_key=viewer_codecheck_detail_selection_key,
                    codecheck_detail_focus_key=viewer_codecheck_detail_focus_key,
                    codecheck_appendix_selection_key=viewer_codecheck_appendix_selection_key,
                    codecheck_appendix_focus_key=viewer_codecheck_appendix_focus_key,
                    interactive_detail_more=str(reverse_sync_state.get("viewer_interactive_detail_more", "") or ""),
                    overlay_detail_more=str(reverse_sync_state.get("viewer_overlay_detail_more", "") or ""),
                    baseline_secondary=str(reverse_sync_state.get("viewer_baseline_secondary", "") or ""),
                ),
                "viewer_slice_url": _viewer_url_for_row(
                    combination_name=str(combination_name),
                    source="row_provenance_csv",
                    subset_key=combination_subset_key,
                    subset_type="combination",
                    row_ref=viewer_row_ref,
                    focus_member=focus_member,
                    member_id=member_id,
                    case_id=case_id,
                    baseline_focus_member_id=baseline_focus_member_id,
                    view_mode=str(reverse_sync_state.get("viewer_reading_mode", "") or ""),
                    focus=str(reverse_sync_state.get("viewer_focus_target", "") or ""),
                    results_card=viewer_results_card,
                    results_series_index=viewer_results_series_index,
                    results_sample_index=viewer_results_sample_index,
                    results_detail_item_index=int(reverse_sync_state.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX) or 0),
                    results_companion_item_index=int(reverse_sync_state.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX) or 0),
                    results_companion_selection_key=_results_companion_selection_key(
                        str(reverse_sync_state.get("viewer_slice_results_companion", "") or ""),
                    ),
                    results_companion_focus_key=_results_companion_focus_key(
                        str(reverse_sync_state.get("viewer_slice_results_companion", "") or ""),
                        series_index=viewer_results_series_index,
                        sample_index=viewer_results_sample_index,
                    ),
                    results_detail_selection_key=viewer_results_detail_selection_key,
                    results_detail_focus_key=viewer_results_detail_focus_key,
                    codecheck_filtered_row_index=int(filtered_row_display_index),
                    codecheck_clause_index=int(_option_index(clause_options, clause_label)),
                    codecheck_hazard_index=int(_option_index(hazard_options, hazard_type)),
                    codecheck_rule_family_index=int(_option_index(rule_family_options, rule_family)),
                    results_companion=str(reverse_sync_state.get("viewer_slice_results_companion", "") or ""),
                    results_detail_block=viewer_results_detail_block,
                    codecheck_surface=str(reverse_sync_state.get("viewer_codecheck_surface", "") or ""),
                    codecheck_companion=str(reverse_sync_state.get("viewer_slice_codecheck_companion", "") or ""),
                    codecheck_companion_item_index=int(reverse_sync_state.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX) or 0),
                    codecheck_companion_selection_key=_codecheck_companion_selection_key(
                        str(reverse_sync_state.get("viewer_slice_codecheck_companion", "") or ""),
                        row_ref=viewer_row_ref,
                    ),
                    codecheck_companion_focus_key=_codecheck_companion_focus_key(
                        str(reverse_sync_state.get("viewer_slice_codecheck_companion", "") or ""),
                        row_ref=viewer_row_ref,
                    ),
                    codecheck_detail_block=viewer_codecheck_detail_block,
                    codecheck_appendix_block=viewer_codecheck_appendix_block,
                    codecheck_detail_item_index=int(reverse_sync_state.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX) or 0),
                    codecheck_appendix_item_index=int(reverse_sync_state.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX) or 0),
                    codecheck_detail_selection_key=viewer_codecheck_detail_selection_key,
                    codecheck_detail_focus_key=viewer_codecheck_detail_focus_key,
                    codecheck_appendix_selection_key=_codecheck_appendix_selection_key(
                        viewer_codecheck_appendix_block,
                        subset_key=combination_subset_key,
                    ),
                    codecheck_appendix_focus_key=_codecheck_appendix_focus_key(viewer_codecheck_appendix_block),
                    interactive_detail_more=str(reverse_sync_state.get("viewer_interactive_detail_more", "") or ""),
                    overlay_detail_more=str(reverse_sync_state.get("viewer_overlay_detail_more", "") or ""),
                    baseline_secondary=str(reverse_sync_state.get("viewer_baseline_secondary", "") or ""),
                ),
            }
            rows_out.append(export_row)
    return rows_out


def _preview_rows(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for row in rows[: max(int(limit), 0)]:
        preview.append(
            {
                "combination_name": str(row.get("combination_name", "") or ""),
                "member_id": str(row.get("member_id", "") or ""),
                "case_id": str(row.get("case_id", "") or ""),
                "clause_label": str(row.get("clause_label", "") or ""),
                "baseline_focus_member_id": str(row.get("baseline_focus_member_id", "") or ""),
                "bridge_row_provenance_mode_label": str(row.get("bridge_row_provenance_mode_label", "") or ""),
                "clause_provenance_summary_label": str(row.get("clause_provenance_summary_label", "") or ""),
                "bridge_member_inventory_summary_label": str(row.get("bridge_member_inventory_summary_label", "") or ""),
            }
        )
    return preview


def _write_rows_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "combination_name",
        "row_index",
        "member_id",
        "case_id",
        "member_type",
        "component",
        "clause_label",
        "baseline_focus_member_id",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _slugify(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value))
    return "_".join(part for part in normalized.split("_") if part) or "unknown"


def _subset_row_refs(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    items = rows[: max(int(limit), 0)] if limit is not None else rows
    for row in items:
        refs.append(
            {
                "combination_name": str(row.get("combination_name", "") or ""),
                "row_index": int(row.get("row_index", 0) or 0),
                "member_id": str(row.get("member_id", "") or ""),
                "case_id": str(row.get("case_id", "") or ""),
                "clause_label": str(row.get("clause_label", "") or ""),
                "baseline_focus_member_id": str(row.get("baseline_focus_member_id", "") or ""),
                "viewer_focus_member_id": str(row.get("viewer_focus_member_id", "") or ""),
                "viewer_row_ref": str(row.get("viewer_row_ref", "") or ""),
                "viewer_row_url": str(row.get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(row.get("viewer_slice_url", "") or ""),
            }
        )
    return refs


def _filter_subset_rows(
    rows: list[dict[str, Any]],
    *,
    subset_type: str,
    key: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = str(row.get(key, "") or "").strip()
        if not label:
            continue
        grouped.setdefault(label, []).append(row)
    ordered: list[dict[str, Any]] = []
    for label, subset_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        member_ids = sorted({str(row.get("member_id", "") or "") for row in subset_rows if str(row.get("member_id", "") or "")})
        combination_names = sorted(
            {str(row.get("combination_name", "") or "") for row in subset_rows if str(row.get("combination_name", "") or "")}
        )
        clause_labels = sorted({str(row.get("clause_label", "") or "") for row in subset_rows if str(row.get("clause_label", "") or "")})
        top_row = subset_rows[0] if subset_rows else {}
        ordered.append(
            {
                key: label,
                "subset_type": subset_type,
                "subset_key": f"{subset_type}:{label}",
                "subset_slug": f"{subset_type}_{_slugify(label)}",
                "row_count": int(len(subset_rows)),
                "member_count": int(len(member_ids)),
                "combination_count": int(len(combination_names)),
                "clause_count": int(len(clause_labels)),
                "top_combination_name": str(top_row.get("combination_name", "") or ""),
                "top_member_id": str(top_row.get("member_id", "") or ""),
                "top_clause_label": str(top_row.get("clause_label", "") or ""),
                "top_dcr_label": str(top_row.get("dcr_label", "") or ""),
                "viewer_row_url": str(top_row.get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(top_row.get("viewer_slice_url", "") or ""),
                "preview_rows": _preview_rows(subset_rows, limit=3),
                "row_refs": _subset_row_refs(subset_rows, limit=limit),
            }
        )
    return ordered


def _clause_filter_rows(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        clause_label = str(row.get("clause_label", "") or "").strip()
        if not clause_label:
            continue
        grouped.setdefault(clause_label, []).append(row)
    ordered: list[dict[str, Any]] = []
    for clause_label, clause_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        preview_rows = _preview_rows(clause_rows, limit=3)
        member_ids = sorted({str(row.get("member_id", "") or "") for row in clause_rows if str(row.get("member_id", "") or "")})
        combination_names = sorted(
            {str(row.get("combination_name", "") or "") for row in clause_rows if str(row.get("combination_name", "") or "")}
        )
        top_row = clause_rows[0] if clause_rows else {}
        ordered.append(
            {
                "clause_label": clause_label,
                "clause_title_label": str(top_row.get("clause_title_label", "") or ""),
                "clause_family_label": str(top_row.get("clause_family_label", "") or ""),
                "row_count": int(len(clause_rows)),
                "member_count": int(len(member_ids)),
                "combination_count": int(len(combination_names)),
                "top_combination_name": str(top_row.get("combination_name", "") or ""),
                "top_member_id": str(top_row.get("member_id", "") or ""),
                "top_case_id": str(top_row.get("case_id", "") or ""),
                "top_dcr_label": str(top_row.get("dcr_label", "") or ""),
                "viewer_row_url": str(top_row.get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(top_row.get("viewer_slice_url", "") or ""),
                "preview_rows": preview_rows,
            }
        )
    if limit is not None:
        return ordered[: max(int(limit), 0)]
    return ordered


def _member_filter_rows(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        member_id = str(row.get("member_id", "") or "").strip()
        if not member_id:
            continue
        grouped.setdefault(member_id, []).append(row)
    ordered: list[dict[str, Any]] = []
    for member_id, member_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        preview_rows = _preview_rows(member_rows, limit=3)
        clause_labels = sorted({str(row.get("clause_label", "") or "") for row in member_rows if str(row.get("clause_label", "") or "")})
        combination_names = sorted(
            {str(row.get("combination_name", "") or "") for row in member_rows if str(row.get("combination_name", "") or "")}
        )
        member_types = sorted({str(row.get("member_type", "") or "") for row in member_rows if str(row.get("member_type", "") or "")})
        top_row = member_rows[0] if member_rows else {}
        ordered.append(
            {
                "member_id": member_id,
                "baseline_focus_member_id": str(top_row.get("baseline_focus_member_id", "") or ""),
                "member_type_label": ", ".join(member_types) if member_types else "",
                "row_count": int(len(member_rows)),
                "clause_count": int(len(clause_labels)),
                "combination_count": int(len(combination_names)),
                "top_combination_name": str(top_row.get("combination_name", "") or ""),
                "top_clause_label": str(top_row.get("clause_label", "") or ""),
                "top_case_id": str(top_row.get("case_id", "") or ""),
                "viewer_row_url": str(top_row.get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(top_row.get("viewer_slice_url", "") or ""),
                "preview_rows": preview_rows,
            }
        )
    if limit is not None:
        return ordered[: max(int(limit), 0)]
    return ordered


def _hazard_filter_rows(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        hazard_type = str(row.get("hazard_type", "") or "").strip()
        if not hazard_type:
            continue
        grouped.setdefault(hazard_type, []).append(row)
    ordered: list[dict[str, Any]] = []
    for hazard_type, hazard_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        preview_rows = _preview_rows(hazard_rows, limit=3)
        member_ids = sorted({str(row.get("member_id", "") or "") for row in hazard_rows if str(row.get("member_id", "") or "")})
        clause_labels = sorted({str(row.get("clause_label", "") or "") for row in hazard_rows if str(row.get("clause_label", "") or "")})
        ordered.append(
            {
                "hazard_type": hazard_type,
                "row_count": int(len(hazard_rows)),
                "member_count": int(len(member_ids)),
                "clause_count": int(len(clause_labels)),
                "combination_count": int(
                    len({str(row.get("combination_name", "") or "") for row in hazard_rows if str(row.get("combination_name", "") or "")})
                ),
                "top_combination_name": str(hazard_rows[0].get("combination_name", "") or ""),
                "top_member_id": str(hazard_rows[0].get("member_id", "") or ""),
                "top_clause_label": str(hazard_rows[0].get("clause_label", "") or ""),
                "top_dcr_label": str(hazard_rows[0].get("dcr_label", "") or ""),
                "viewer_row_url": str(hazard_rows[0].get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(hazard_rows[0].get("viewer_slice_url", "") or ""),
                "preview_rows": preview_rows,
            }
        )
    if limit is not None:
        return ordered[: max(int(limit), 0)]
    return ordered


def _rule_family_filter_rows(rows: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rule_family = str(row.get("rule_family", "") or "").strip()
        if not rule_family:
            continue
        grouped.setdefault(rule_family, []).append(row)
    ordered: list[dict[str, Any]] = []
    for rule_family, rule_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        preview_rows = _preview_rows(rule_rows, limit=3)
        member_ids = sorted({str(row.get("member_id", "") or "") for row in rule_rows if str(row.get("member_id", "") or "")})
        hazard_types = sorted({str(row.get("hazard_type", "") or "") for row in rule_rows if str(row.get("hazard_type", "") or "")})
        ordered.append(
            {
                "rule_family": rule_family,
                "row_count": int(len(rule_rows)),
                "member_count": int(len(member_ids)),
                "hazard_count": int(len(hazard_types)),
                "combination_count": int(
                    len({str(row.get("combination_name", "") or "") for row in rule_rows if str(row.get("combination_name", "") or "")})
                ),
                "top_combination_name": str(rule_rows[0].get("combination_name", "") or ""),
                "top_member_id": str(rule_rows[0].get("member_id", "") or ""),
                "top_clause_label": str(rule_rows[0].get("clause_label", "") or ""),
                "top_dcr_label": str(rule_rows[0].get("dcr_label", "") or ""),
                "viewer_row_url": str(rule_rows[0].get("viewer_row_url", "") or ""),
                "viewer_slice_url": str(rule_rows[0].get("viewer_slice_url", "") or ""),
                "preview_rows": preview_rows,
            }
        )
    if limit is not None:
        return ordered[: max(int(limit), 0)]
    return ordered


def build_row_provenance_export(model_json: Path, kds_report: Path) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    viewer_module.DEFAULT_KDS_COMPLIANCE_REPORT = kds_report
    context = viewer_module._make_midas_load_pattern_context(model_json)
    combination_highlights_by_name = {
        str(row.get("name", "") or ""): row
        for row in (context.get("load_combination_highlights") or [])
        if isinstance(row, dict) and str(row.get("name", "") or "")
    }
    table_by_name = (
        context.get("load_combination_codecheck_table_by_name")
        if isinstance(context.get("load_combination_codecheck_table_by_name"), dict)
        else {}
    )
    rows = _flatten_rows(
        table_by_name,
        combination_highlights_by_name=combination_highlights_by_name,
    )
    clause_names = sorted({str(row.get("clause_label", "") or "") for row in rows if str(row.get("clause_label", "") or "")})
    member_ids = sorted({str(row.get("member_id", "") or "") for row in rows if str(row.get("member_id", "") or "")})
    exact_rows = sum(
        1
        for row in rows
        if str(row.get("bridge_row_provenance_mode_label", "") or "").strip() == "exact row-level provenance"
    )
    clause_filter_rows = _clause_filter_rows(rows)
    member_filter_rows = _member_filter_rows(rows)
    hazard_filter_rows = _hazard_filter_rows(rows)
    rule_family_filter_rows = _rule_family_filter_rows(rows)
    hazard_filter_subsets = _filter_subset_rows(rows, subset_type="hazard", key="hazard_type")
    rule_family_filter_subsets = _filter_subset_rows(rows, subset_type="rule_family", key="rule_family")
    export_payload = {
        "schema_version": "1.1",
        "run_id": "phase1-midas-kds-row-provenance-table-export",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "combination_count": int(len(table_by_name)),
            "row_count": int(len(rows)),
            "member_count": int(len(member_ids)),
            "clause_count": int(len(clause_names)),
            "exact_row_count": int(exact_rows),
            "heuristic_row_count": int(max(len(rows) - exact_rows, 0)),
            "clause_filter_count": int(len(clause_filter_rows)),
            "member_filter_count": int(len(member_filter_rows)),
            "hazard_filter_count": int(len(hazard_filter_rows)),
            "rule_family_filter_count": int(len(rule_family_filter_rows)),
            "hazard_subset_count": int(len(hazard_filter_subsets)),
            "rule_family_subset_count": int(len(rule_family_filter_subsets)),
        },
        "preview_rows": _preview_rows(rows),
        "clause_filter_rows": clause_filter_rows,
        "member_filter_rows": member_filter_rows,
        "hazard_filter_rows": hazard_filter_rows,
        "rule_family_filter_rows": rule_family_filter_rows,
        "hazard_filter_subsets": hazard_filter_subsets,
        "rule_family_filter_subsets": rule_family_filter_subsets,
        "reviewer_appendix": {
            "schema_version": "filter_subset_v1",
            "reverse_jump_contract_version": VIEWER_REVERSE_SYNC_CONTRACT_VERSION,
            "clause_filters": clause_filter_rows,
            "member_filters": member_filter_rows,
            "hazard_filters": hazard_filter_rows,
            "rule_family_filters": rule_family_filter_rows,
            "hazard_filter_subsets": hazard_filter_subsets,
            "rule_family_filter_subsets": rule_family_filter_subsets,
        },
        "rows": rows,
    }
    report = {
        "schema_version": "1.1",
        "run_id": "phase1-midas-kds-row-provenance-table-export-report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "combination_count": int(len(table_by_name)),
            "row_count": int(len(rows)),
            "member_count": int(len(member_ids)),
            "clause_count": int(len(clause_names)),
            "exact_row_count": int(exact_rows),
            "clause_filter_count": int(len(clause_filter_rows)),
            "member_filter_count": int(len(member_filter_rows)),
            "hazard_filter_count": int(len(hazard_filter_rows)),
            "rule_family_filter_count": int(len(rule_family_filter_rows)),
            "hazard_subset_count": int(len(hazard_filter_subsets)),
            "rule_family_subset_count": int(len(rule_family_filter_subsets)),
        },
        "preview_rows": _preview_rows(rows),
        "clause_filter_rows": _clause_filter_rows(rows, limit=8),
        "member_filter_rows": _member_filter_rows(rows, limit=8),
        "hazard_filter_rows": _hazard_filter_rows(rows, limit=8),
        "rule_family_filter_rows": _rule_family_filter_rows(rows, limit=8),
        "hazard_filter_subsets": _filter_subset_rows(rows, subset_type="hazard", key="hazard_type", limit=12),
        "rule_family_filter_subsets": _filter_subset_rows(rows, subset_type="rule_family", key="rule_family", limit=12),
        "summary_line": (
            f"MIDAS KDS row provenance export: {'PASS' if rows else 'CHECK'} | "
            f"combos={len(table_by_name)} | rows={len(rows)} | members={len(member_ids)} | "
            f"clauses={len(clause_names)} | exact_rows={exact_rows} | "
            f"clause_filters={len(clause_filter_rows)} | member_filters={len(member_filter_rows)} | "
            f"reverse_jump={VIEWER_REVERSE_SYNC_CONTRACT_VERSION}"
        ),
        "contract_pass": bool(rows),
        "reason_code": "PASS" if rows else "ERR_NO_ROWS",
        "reason": "row-level provenance table exported" if rows else "no row-level provenance rows were available",
    }
    return export_payload, report, rows


def _build_subset_artifacts(rows: list[dict[str, Any]], subset_root: Path) -> dict[str, Any]:
    subset_root.mkdir(parents=True, exist_ok=True)
    rows_by_combination: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        combination_name = str(row.get("combination_name", "") or "").strip()
        if not combination_name:
            continue
        rows_by_combination.setdefault(combination_name, []).append(row)

    def _build_subset_contract(
        *,
        combination_name: str,
        subset_type: str,
        subset_key: str,
        subset_rows: list[dict[str, Any]],
        csv_path: Path,
        metadata_json: Path,
        hazard_label: str = "",
        rule_family_label: str = "",
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        top_row = subset_rows[0] if subset_rows else {}
        top_row_index = int(top_row.get("row_index", 0) or 0) if isinstance(top_row, dict) else 0
        top_member_id = str(top_row.get("member_id", "") or "") if isinstance(top_row, dict) else ""
        top_case_id = str(top_row.get("case_id", "") or "") if isinstance(top_row, dict) else ""
        top_baseline_focus_member_id = (
            str(top_row.get("baseline_focus_member_id", "") or "") if isinstance(top_row, dict) else ""
        )
        top_focus_member = _focus_member_id(
            baseline_focus_member_id=top_baseline_focus_member_id,
            member_id=top_member_id,
            case_id=top_case_id,
        )
        top_row_ref = (
            str(top_row.get("viewer_row_ref", "") or "").strip()
            if isinstance(top_row, dict)
            else ""
        ) or _viewer_row_ref(
            combination_name=combination_name,
            row_index=top_row_index,
            member_id=top_member_id,
            case_id=top_case_id,
        )
        top_viewer_reading_mode = str(top_row.get("viewer_reading_mode", "") or "") if isinstance(top_row, dict) else ""
        top_viewer_focus_target = str(top_row.get("viewer_focus_target", "") or "") if isinstance(top_row, dict) else ""
        top_viewer_results_card = str(top_row.get("viewer_results_card", "") or "") if isinstance(top_row, dict) else ""
        top_viewer_results_series_index = (
            _int_or_default(top_row.get("viewer_results_series_index", 0), 0) if isinstance(top_row, dict) else 0
        )
        top_viewer_results_sample_index = (
            _int_or_default(top_row.get("viewer_results_sample_index", DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX), DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX
        )
        top_viewer_results_detail_item_index = (
            _int_or_default(top_row.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX
        )
        top_viewer_results_companion_item_index = (
            _int_or_default(top_row.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX
        )
        top_viewer_results_detail_focus_key = (
            str(top_row.get("viewer_results_detail_focus_key", DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY
        )
        top_viewer_results_detail_selection_key = (
            str(top_row.get("viewer_results_detail_selection_key", DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY
        )
        top_viewer_codecheck_filtered_row_index = (
            _int_or_default(top_row.get("viewer_codecheck_filtered_row_index", 0), 0)
            if isinstance(top_row, dict) else 0
        )
        top_viewer_codecheck_clause_index = (
            _int_or_default(top_row.get("viewer_codecheck_clause_index", 0), 0)
            if isinstance(top_row, dict) else 0
        )
        top_viewer_codecheck_hazard_index = (
            _int_or_default(top_row.get("viewer_codecheck_hazard_index", 0), 0)
            if isinstance(top_row, dict) else 0
        )
        top_viewer_codecheck_rule_family_index = (
            _int_or_default(top_row.get("viewer_codecheck_rule_family_index", 0), 0)
            if isinstance(top_row, dict) else 0
        )
        top_viewer_results_companion = (
            str(top_row.get("viewer_results_companion", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_codecheck_surface = (
            str(top_row.get("viewer_codecheck_surface", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_codecheck_companion = (
            str(top_row.get("viewer_codecheck_companion", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_codecheck_companion_item_index = (
            _int_or_default(top_row.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX
        )
        top_viewer_codecheck_detail_block = (
            str(top_row.get("viewer_codecheck_detail_block", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_results_detail_block = (
            str(top_row.get("viewer_results_detail_block", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_codecheck_appendix_block = (
            str(top_row.get("viewer_codecheck_appendix_block", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_codecheck_detail_item_index = (
            _int_or_default(top_row.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX
        )
        top_viewer_codecheck_appendix_item_index = (
            _int_or_default(top_row.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX
        )
        top_viewer_codecheck_detail_focus_key = (
            str(top_row.get("viewer_codecheck_detail_focus_key", DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY
        )
        top_viewer_codecheck_detail_selection_key = (
            str(top_row.get("viewer_codecheck_detail_selection_key", DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY
        )
        top_viewer_codecheck_appendix_focus_key = (
            str(top_row.get("viewer_codecheck_appendix_focus_key", DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY)
            if isinstance(top_row, dict) else DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY
        )
        top_viewer_interactive_detail_more = (
            str(top_row.get("viewer_interactive_detail_more", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_overlay_detail_more = (
            str(top_row.get("viewer_overlay_detail_more", "") or "") if isinstance(top_row, dict) else ""
        )
        top_viewer_baseline_secondary = (
            str(top_row.get("viewer_baseline_secondary", "") or "") if isinstance(top_row, dict) else ""
        )
        viewer_subset_url = _viewer_url_for_row(
            combination_name=combination_name,
            source="row_provenance_subset_csv",
            hazard_type=hazard_label,
            rule_family=rule_family_label,
            subset_key=subset_key,
            subset_type=subset_type,
            row_ref=top_row_ref,
            focus_member=top_focus_member,
            member_id=top_member_id,
            case_id=top_case_id,
            baseline_focus_member_id=top_baseline_focus_member_id,
            subset_csv=str(csv_path),
            subset_manifest=str(metadata_json),
            view_mode=top_viewer_reading_mode,
            focus=top_viewer_focus_target,
            results_card=top_viewer_results_card,
            results_series_index=top_viewer_results_series_index,
            results_sample_index=top_viewer_results_sample_index,
            results_detail_item_index=top_viewer_results_detail_item_index,
            results_companion_item_index=top_viewer_results_companion_item_index,
            results_companion_selection_key=_results_companion_selection_key(
                DEFAULT_VIEWER_SLICE_RESULTS_COMPANION or top_viewer_results_companion,
            ),
            results_companion_focus_key=_results_companion_focus_key(
                DEFAULT_VIEWER_SLICE_RESULTS_COMPANION or top_viewer_results_companion,
                series_index=top_viewer_results_series_index,
                sample_index=top_viewer_results_sample_index,
            ),
            results_detail_selection_key=top_viewer_results_detail_selection_key,
            results_detail_focus_key=top_viewer_results_detail_focus_key,
            codecheck_filtered_row_index=top_viewer_codecheck_filtered_row_index,
            codecheck_clause_index=top_viewer_codecheck_clause_index,
            codecheck_hazard_index=top_viewer_codecheck_hazard_index,
            codecheck_rule_family_index=top_viewer_codecheck_rule_family_index,
            results_companion=DEFAULT_VIEWER_SLICE_RESULTS_COMPANION or top_viewer_results_companion,
            results_detail_block=top_viewer_results_detail_block,
            codecheck_surface=top_viewer_codecheck_surface,
            codecheck_companion=DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION or top_viewer_codecheck_companion,
            codecheck_companion_item_index=top_viewer_codecheck_companion_item_index,
            codecheck_companion_selection_key=_codecheck_companion_selection_key(
                DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION or top_viewer_codecheck_companion,
                row_ref=top_row_ref,
            ),
            codecheck_companion_focus_key=_codecheck_companion_focus_key(
                DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION or top_viewer_codecheck_companion,
                row_ref=top_row_ref,
            ),
            codecheck_detail_block=top_viewer_codecheck_detail_block,
            codecheck_appendix_block=top_viewer_codecheck_appendix_block,
            codecheck_detail_item_index=top_viewer_codecheck_detail_item_index,
            codecheck_appendix_item_index=top_viewer_codecheck_appendix_item_index,
            codecheck_detail_selection_key=top_viewer_codecheck_detail_selection_key,
            codecheck_detail_focus_key=top_viewer_codecheck_detail_focus_key,
            codecheck_appendix_selection_key=_codecheck_appendix_selection_key(
                top_viewer_codecheck_appendix_block,
                subset_key=subset_key,
            ),
            codecheck_appendix_focus_key=top_viewer_codecheck_appendix_focus_key,
            interactive_detail_more=top_viewer_interactive_detail_more,
            overlay_detail_more=top_viewer_overlay_detail_more,
            baseline_secondary=top_viewer_baseline_secondary,
        )
        contextual_rows: list[dict[str, Any]] = []
        row_refs: list[dict[str, Any]] = []
        for row in subset_rows:
            row_index = int(row.get("row_index", 0) or 0)
            member_id = str(row.get("member_id", "") or "")
            case_id = str(row.get("case_id", "") or "")
            baseline_focus_member_id = str(row.get("baseline_focus_member_id", "") or "")
            focus_member = baseline_focus_member_id or member_id or case_id
            viewer_row_ref = str(row.get("viewer_row_ref", "") or "").strip() or _viewer_row_ref(
                combination_name=combination_name,
                row_index=row_index,
                member_id=member_id,
                case_id=case_id,
            )
            viewer_subset_row_url = _viewer_url_for_row(
                combination_name=combination_name,
                row_index=row_index,
                clause_label=str(row.get("clause_label", "") or ""),
                hazard_type=hazard_label,
                rule_family=rule_family_label,
                source="row_provenance_subset_csv",
                subset_key=subset_key,
                subset_type=subset_type,
                row_ref=viewer_row_ref,
                focus_member=focus_member,
                member_id=member_id,
                case_id=case_id,
                baseline_focus_member_id=baseline_focus_member_id,
                subset_csv=str(csv_path),
                subset_manifest=str(metadata_json),
                view_mode=str(row.get("viewer_reading_mode", "") or ""),
                focus=str(row.get("viewer_focus_target", "") or ""),
                results_card=str(row.get("viewer_results_card", "") or ""),
                results_series_index=_int_or_default(row.get("viewer_results_series_index", 0), 0),
                results_sample_index=_int_or_default(row.get("viewer_results_sample_index", DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX), DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX),
                results_detail_item_index=_int_or_default(row.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX),
                results_companion_item_index=_int_or_default(row.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX),
                results_companion_selection_key=str(row.get("viewer_results_companion_selection_key", DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY) or DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY),
                results_companion_focus_key=str(row.get("viewer_results_companion_focus_key", DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY) or DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY),
                results_detail_selection_key=str(row.get("viewer_results_detail_selection_key", DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY),
                results_detail_focus_key=str(row.get("viewer_results_detail_focus_key", DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY),
                codecheck_filtered_row_index=_int_or_default(row.get("viewer_codecheck_filtered_row_index", 0), 0),
                codecheck_clause_index=_int_or_default(row.get("viewer_codecheck_clause_index", 0), 0),
                codecheck_hazard_index=_int_or_default(row.get("viewer_codecheck_hazard_index", 0), 0),
                codecheck_rule_family_index=_int_or_default(row.get("viewer_codecheck_rule_family_index", 0), 0),
                results_companion=str(row.get("viewer_results_companion", "") or ""),
                results_detail_block=str(row.get("viewer_results_detail_block", "") or ""),
                codecheck_surface=str(row.get("viewer_codecheck_surface", "") or ""),
                codecheck_companion=str(row.get("viewer_codecheck_companion", "") or ""),
                codecheck_companion_item_index=_int_or_default(row.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX),
                codecheck_companion_selection_key=str(row.get("viewer_codecheck_companion_selection_key", DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY),
                codecheck_companion_focus_key=str(row.get("viewer_codecheck_companion_focus_key", DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY),
                codecheck_detail_block=str(row.get("viewer_codecheck_detail_block", "") or ""),
                codecheck_appendix_block=str(row.get("viewer_codecheck_appendix_block", "") or ""),
                codecheck_detail_item_index=_int_or_default(row.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX),
                codecheck_appendix_item_index=_int_or_default(row.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX),
                codecheck_detail_selection_key=str(row.get("viewer_codecheck_detail_selection_key", DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY),
                codecheck_detail_focus_key=str(row.get("viewer_codecheck_detail_focus_key", DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY),
                codecheck_appendix_selection_key=str(row.get("viewer_codecheck_appendix_selection_key", DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY),
                codecheck_appendix_focus_key=str(row.get("viewer_codecheck_appendix_focus_key", DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY),
                interactive_detail_more=str(row.get("viewer_interactive_detail_more", "") or ""),
                overlay_detail_more=str(row.get("viewer_overlay_detail_more", "") or ""),
                baseline_secondary=str(row.get("viewer_baseline_secondary", "") or ""),
            )
            contextual_row = {
                **row,
                "viewer_master_row_url": str(row.get("viewer_row_url", "") or ""),
                "viewer_master_slice_url": str(row.get("viewer_slice_url", "") or ""),
                "viewer_row_url": viewer_subset_row_url,
                "viewer_slice_url": viewer_subset_url,
                "viewer_subset_type": subset_type,
                "viewer_subset_key": subset_key,
                "viewer_subset_csv": str(csv_path),
                "viewer_subset_manifest_json": str(metadata_json),
                "viewer_subset_url": viewer_subset_url,
                "viewer_subset_row_url": viewer_subset_row_url,
            }
            contextual_rows.append(contextual_row)
            row_refs.append(
                {
                    "combination_name": combination_name,
                    "row_index": row_index,
                    "member_id": member_id,
                    "case_id": case_id,
                    "clause_label": str(row.get("clause_label", "") or ""),
                    "baseline_focus_member_id": baseline_focus_member_id,
                    "viewer_focus_member_id": focus_member,
                    "viewer_reading_mode": str(row.get("viewer_reading_mode", "") or ""),
                    "viewer_focus_target": str(row.get("viewer_focus_target", "") or ""),
                    "viewer_results_card": str(row.get("viewer_results_card", "") or ""),
                    "viewer_results_series_index": _int_or_default(row.get("viewer_results_series_index", 0), 0),
                    "viewer_results_sample_index": _int_or_default(row.get("viewer_results_sample_index", DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX), DEFAULT_VIEWER_RESULTS_SAMPLE_INDEX),
                    "viewer_results_detail_item_index": _int_or_default(row.get("viewer_results_detail_item_index", DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_DETAIL_ITEM_INDEX),
                    "viewer_results_companion_item_index": _int_or_default(row.get("viewer_results_companion_item_index", DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_RESULTS_COMPANION_ITEM_INDEX),
                    "viewer_results_companion_selection_key": str(row.get("viewer_results_companion_selection_key", DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY) or DEFAULT_VIEWER_RESULTS_COMPANION_SELECTION_KEY),
                    "viewer_results_companion_focus_key": str(row.get("viewer_results_companion_focus_key", DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY) or DEFAULT_VIEWER_RESULTS_COMPANION_FOCUS_KEY),
                    "viewer_results_detail_selection_key": str(row.get("viewer_results_detail_selection_key", DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_SELECTION_KEY),
                    "viewer_results_detail_focus_key": str(row.get("viewer_results_detail_focus_key", DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_RESULTS_DETAIL_FOCUS_KEY),
                    "viewer_codecheck_filtered_row_index": _int_or_default(row.get("viewer_codecheck_filtered_row_index", 0), 0),
                    "viewer_codecheck_clause_index": _int_or_default(row.get("viewer_codecheck_clause_index", 0), 0),
                    "viewer_codecheck_hazard_index": _int_or_default(row.get("viewer_codecheck_hazard_index", 0), 0),
                    "viewer_codecheck_rule_family_index": _int_or_default(row.get("viewer_codecheck_rule_family_index", 0), 0),
                    "viewer_results_companion": str(row.get("viewer_results_companion", "") or ""),
                    "viewer_results_detail_block": str(row.get("viewer_results_detail_block", "") or ""),
                    "viewer_codecheck_surface": str(row.get("viewer_codecheck_surface", "") or ""),
                    "viewer_codecheck_companion": str(row.get("viewer_codecheck_companion", "") or ""),
                    "viewer_codecheck_companion_item_index": _int_or_default(row.get("viewer_codecheck_companion_item_index", DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_COMPANION_ITEM_INDEX),
                    "viewer_codecheck_companion_selection_key": str(row.get("viewer_codecheck_companion_selection_key", DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_COMPANION_SELECTION_KEY),
                    "viewer_codecheck_companion_focus_key": str(row.get("viewer_codecheck_companion_focus_key", DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_COMPANION_FOCUS_KEY),
                    "viewer_codecheck_detail_block": str(row.get("viewer_codecheck_detail_block", "") or ""),
                    "viewer_codecheck_appendix_block": str(row.get("viewer_codecheck_appendix_block", "") or ""),
                    "viewer_codecheck_detail_item_index": _int_or_default(row.get("viewer_codecheck_detail_item_index", DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_DETAIL_ITEM_INDEX),
                    "viewer_codecheck_appendix_item_index": _int_or_default(row.get("viewer_codecheck_appendix_item_index", DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX), DEFAULT_VIEWER_CODECHECK_APPENDIX_ITEM_INDEX),
                    "viewer_codecheck_detail_selection_key": str(row.get("viewer_codecheck_detail_selection_key", DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_SELECTION_KEY),
                    "viewer_codecheck_detail_focus_key": str(row.get("viewer_codecheck_detail_focus_key", DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_DETAIL_FOCUS_KEY),
                    "viewer_codecheck_appendix_selection_key": str(row.get("viewer_codecheck_appendix_selection_key", DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY) or DEFAULT_VIEWER_CODECHECK_APPENDIX_SELECTION_KEY),
                    "viewer_codecheck_appendix_focus_key": str(row.get("viewer_codecheck_appendix_focus_key", DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY) or DEFAULT_VIEWER_CODECHECK_APPENDIX_FOCUS_KEY),
                    "viewer_interactive_detail_more": str(row.get("viewer_interactive_detail_more", "") or ""),
                    "viewer_overlay_detail_more": str(row.get("viewer_overlay_detail_more", "") or ""),
                    "viewer_baseline_secondary": str(row.get("viewer_baseline_secondary", "") or ""),
                    "viewer_row_ref": viewer_row_ref,
                    "viewer_row_url": viewer_subset_row_url,
                    "viewer_slice_url": viewer_subset_url,
                }
            )
        member_count = len(
            {
                str(row.get("member_id", "") or "").strip()
                for row in contextual_rows
                if str(row.get("member_id", "") or "").strip()
            }
        )
        clause_count = len(
            {
                str(row.get("clause_label", "") or "").strip()
                for row in contextual_rows
                if str(row.get("clause_label", "") or "").strip()
            }
        )
        contract_payload = {
            "schema_version": VIEWER_REVERSE_SYNC_CONTRACT_VERSION,
            "subset_type": subset_type,
            "subset_key": subset_key,
            "combination_name": combination_name,
            "hazard_label": hazard_label,
            "rule_family_label": rule_family_label,
            "row_count": int(len(contextual_rows)),
            "member_count": int(member_count),
            "clause_count": int(clause_count),
            "artifacts": {
                "csv": str(csv_path),
                "metadata_json": str(metadata_json),
            },
            "viewer_slice_url": viewer_subset_url,
            "viewer_row_url": str(row_refs[0].get("viewer_row_url", "") or "") if row_refs else "",
            "viewer_focus_member_id": str(row_refs[0].get("viewer_focus_member_id", "") or "") if row_refs else "",
            "viewer_reading_mode": top_viewer_reading_mode,
            "viewer_focus_target": top_viewer_focus_target,
            "viewer_results_card": top_viewer_results_card,
            "viewer_results_series_index": int(top_viewer_results_series_index),
            "viewer_results_sample_index": int(top_viewer_results_sample_index),
            "viewer_results_detail_item_index": int(top_viewer_results_detail_item_index),
            "viewer_results_companion_item_index": int(top_viewer_results_companion_item_index),
            "viewer_results_companion_selection_key": _results_companion_selection_key(
                DEFAULT_VIEWER_SLICE_RESULTS_COMPANION or top_viewer_results_companion,
            ),
            "viewer_results_detail_selection_key": top_viewer_results_detail_selection_key,
            "viewer_codecheck_filtered_row_index": int(top_viewer_codecheck_filtered_row_index),
            "viewer_codecheck_clause_index": int(top_viewer_codecheck_clause_index),
            "viewer_codecheck_hazard_index": int(top_viewer_codecheck_hazard_index),
            "viewer_codecheck_rule_family_index": int(top_viewer_codecheck_rule_family_index),
            "viewer_results_companion": DEFAULT_VIEWER_SLICE_RESULTS_COMPANION or top_viewer_results_companion,
            "viewer_results_detail_block": str(DEFAULT_VIEWER_RESULTS_DETAIL_BLOCK or ""),
            "viewer_codecheck_surface": top_viewer_codecheck_surface,
            "viewer_codecheck_companion": DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION or top_viewer_codecheck_companion,
            "viewer_codecheck_companion_item_index": int(top_viewer_codecheck_companion_item_index),
            "viewer_codecheck_companion_selection_key": _codecheck_companion_selection_key(
                DEFAULT_VIEWER_SLICE_CODECHECK_COMPANION or top_viewer_codecheck_companion,
                row_ref=top_row_ref,
            ),
            "viewer_codecheck_detail_block": top_viewer_codecheck_detail_block,
            "viewer_codecheck_appendix_block": str(DEFAULT_VIEWER_CODECHECK_APPENDIX_BLOCK or ""),
            "viewer_codecheck_detail_item_index": int(top_viewer_codecheck_detail_item_index),
            "viewer_codecheck_appendix_item_index": int(top_viewer_codecheck_appendix_item_index),
            "viewer_codecheck_detail_selection_key": top_viewer_codecheck_detail_selection_key,
            "viewer_codecheck_appendix_selection_key": _codecheck_appendix_selection_key(
                top_viewer_codecheck_appendix_block,
                subset_key=subset_key,
            ),
            "viewer_interactive_detail_more": top_viewer_interactive_detail_more,
            "viewer_overlay_detail_more": top_viewer_overlay_detail_more,
            "viewer_baseline_secondary": top_viewer_baseline_secondary,
            "reverse_sync_contract_version": VIEWER_REVERSE_SYNC_CONTRACT_VERSION,
            "row_refs": row_refs,
            "preview_row_refs": row_refs[: min(len(row_refs), 12)],
        }
        return contextual_rows, contract_payload

    artifact_index: dict[str, Any] = {
        "subset_root": str(subset_root),
        "contract_version": VIEWER_REVERSE_SYNC_CONTRACT_VERSION,
        "combination_count": int(len(rows_by_combination)),
        "combination_rows": {},
    }
    for combination_name, combo_rows in sorted(rows_by_combination.items()):
        combo_slug = _safe_slug(combination_name)
        combo_root = subset_root / combo_slug
        all_csv = combo_root / "all.csv"
        all_json = combo_root / "all.json"
        combination_subset_key = f"combination:{combination_name}"
        contextual_combo_rows, combo_contract = _build_subset_contract(
            combination_name=combination_name,
            subset_type="combination",
            subset_key=combination_subset_key,
            subset_rows=combo_rows,
            csv_path=all_csv,
            metadata_json=all_json,
        )
        _write_rows_csv(contextual_combo_rows, all_csv)
        all_json.write_text(json.dumps(combo_contract, ensure_ascii=False, indent=2), encoding="utf-8")
        combo_payload: dict[str, Any] = {
            "slug": combo_slug,
            "row_count": int(len(combo_rows)),
            "all_csv": str(all_csv),
            "all_metadata_json": str(all_json),
            "subset_key": combination_subset_key,
            "subset_type": "combination",
            "viewer_slice_url": str(combo_contract.get("viewer_slice_url", "") or ""),
            "viewer_row_url": str(combo_contract.get("viewer_row_url", "") or ""),
            "viewer_focus_member_id": str(combo_contract.get("viewer_focus_member_id", "") or ""),
            "row_refs_preview": combo_contract.get("preview_row_refs", []),
            "hazard": {},
            "rule_family": {},
            "hazard_rule_family": {},
        }

        hazard_groups: dict[str, list[dict[str, Any]]] = {}
        rule_groups: dict[str, list[dict[str, Any]]] = {}
        hazard_rule_groups: dict[str, list[dict[str, Any]]] = {}
        for row in combo_rows:
            hazard_label = str(row.get("hazard_type", "") or "").strip()
            rule_label = str(row.get("rule_family", "") or "").strip()
            if hazard_label:
                hazard_groups.setdefault(hazard_label, []).append(row)
            if rule_label:
                rule_groups.setdefault(rule_label, []).append(row)
            if hazard_label or rule_label:
                composite_key = f"{hazard_label}::{rule_label}"
                hazard_rule_groups.setdefault(composite_key, []).append(row)

        for hazard_label, hazard_rows in sorted(hazard_groups.items()):
            hazard_slug = _safe_slug(hazard_label)
            hazard_csv = combo_root / "hazard" / f"{hazard_slug}.csv"
            hazard_json = combo_root / "hazard" / f"{hazard_slug}.json"
            subset_key = f"hazard:{hazard_label}"
            contextual_rows, subset_contract = _build_subset_contract(
                combination_name=combination_name,
                subset_type="hazard",
                subset_key=subset_key,
                subset_rows=hazard_rows,
                csv_path=hazard_csv,
                metadata_json=hazard_json,
                hazard_label=hazard_label,
            )
            _write_rows_csv(contextual_rows, hazard_csv)
            hazard_json.write_text(json.dumps(subset_contract, ensure_ascii=False, indent=2), encoding="utf-8")
            combo_payload["hazard"][hazard_label] = {
                "slug": hazard_slug,
                "row_count": int(len(hazard_rows)),
                "csv": str(hazard_csv),
                "metadata_json": str(hazard_json),
                "subset_key": subset_key,
                "subset_type": "hazard",
                "viewer_slice_url": str(subset_contract.get("viewer_slice_url", "") or ""),
                "viewer_row_url": str(subset_contract.get("viewer_row_url", "") or ""),
                "viewer_focus_member_id": str(subset_contract.get("viewer_focus_member_id", "") or ""),
                "row_refs_preview": subset_contract.get("preview_row_refs", []),
            }

        for rule_label, rule_rows in sorted(rule_groups.items()):
            rule_slug = _safe_slug(rule_label)
            rule_csv = combo_root / "rule_family" / f"{rule_slug}.csv"
            rule_json = combo_root / "rule_family" / f"{rule_slug}.json"
            subset_key = f"rule_family:{rule_label}"
            contextual_rows, subset_contract = _build_subset_contract(
                combination_name=combination_name,
                subset_type="rule_family",
                subset_key=subset_key,
                subset_rows=rule_rows,
                csv_path=rule_csv,
                metadata_json=rule_json,
                rule_family_label=rule_label,
            )
            _write_rows_csv(contextual_rows, rule_csv)
            rule_json.write_text(json.dumps(subset_contract, ensure_ascii=False, indent=2), encoding="utf-8")
            combo_payload["rule_family"][rule_label] = {
                "slug": rule_slug,
                "row_count": int(len(rule_rows)),
                "csv": str(rule_csv),
                "metadata_json": str(rule_json),
                "subset_key": subset_key,
                "subset_type": "rule_family",
                "viewer_slice_url": str(subset_contract.get("viewer_slice_url", "") or ""),
                "viewer_row_url": str(subset_contract.get("viewer_row_url", "") or ""),
                "viewer_focus_member_id": str(subset_contract.get("viewer_focus_member_id", "") or ""),
                "row_refs_preview": subset_contract.get("preview_row_refs", []),
            }

        for composite_key, subset_rows in sorted(hazard_rule_groups.items()):
            hazard_label, _, rule_label = composite_key.partition("::")
            hazard_slug = _safe_slug(hazard_label)
            rule_slug = _safe_slug(rule_label)
            subset_csv = combo_root / "hazard_rule" / f"{hazard_slug}__{rule_slug}.csv"
            subset_json = combo_root / "hazard_rule" / f"{hazard_slug}__{rule_slug}.json"
            subset_key = f"hazard_rule:{composite_key}"
            contextual_rows, subset_contract = _build_subset_contract(
                combination_name=combination_name,
                subset_type="hazard_rule",
                subset_key=subset_key,
                subset_rows=subset_rows,
                csv_path=subset_csv,
                metadata_json=subset_json,
                hazard_label=hazard_label,
                rule_family_label=rule_label,
            )
            _write_rows_csv(contextual_rows, subset_csv)
            subset_json.write_text(json.dumps(subset_contract, ensure_ascii=False, indent=2), encoding="utf-8")
            combo_payload["hazard_rule_family"][composite_key] = {
                "hazard_label": hazard_label,
                "rule_family_label": rule_label,
                "slug": f"{hazard_slug}__{rule_slug}",
                "row_count": int(len(subset_rows)),
                "csv": str(subset_csv),
                "metadata_json": str(subset_json),
                "subset_key": subset_key,
                "subset_type": "hazard_rule",
                "viewer_slice_url": str(subset_contract.get("viewer_slice_url", "") or ""),
                "viewer_row_url": str(subset_contract.get("viewer_row_url", "") or ""),
                "viewer_focus_member_id": str(subset_contract.get("viewer_focus_member_id", "") or ""),
                "row_refs_preview": subset_contract.get("preview_row_refs", []),
            }

        artifact_index["combination_rows"][combination_name] = combo_payload
    return artifact_index


def write_row_provenance_export(
    *,
    model_json: Path,
    kds_report: Path,
    out_json: Path,
    out_csv: Path,
    out_report: Path,
    input_payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    export_payload, report, rows = build_row_provenance_export(model_json, kds_report)
    export_payload["inputs"] = {
        **input_payload,
        "input_sha256": {
            "model_json": _sha256(model_json) if model_json.exists() else "",
            "kds_report": _sha256(kds_report) if kds_report.exists() else "",
        },
    }
    out_json.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_rows_csv(rows, out_csv)

    subset_root = out_csv.parent / "midas_kds_row_provenance_subsets"
    subset_artifacts = _build_subset_artifacts(rows, subset_root)
    export_payload["artifacts"] = {
        "json": str(out_json),
        "csv": str(out_csv),
        "report": str(out_report),
        "subset_root": str(subset_root),
        "subset_index": subset_artifacts,
    }
    out_json.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report["inputs"] = input_payload
    report["artifacts"] = {
        "json": str(out_json),
        "csv": str(out_csv),
        "subset_root": str(subset_root),
        "combination_subset_count": int(subset_artifacts.get("combination_count", 0)),
    }
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return export_payload, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-json", default="implementation/phase1/open_data/midas/midas_generator_33.json")
    parser.add_argument("--kds-report", default="implementation/phase1/release/kds_compliance/code_check_report.json")
    parser.add_argument("--out-json", default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.json")
    parser.add_argument("--out-csv", default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table.csv")
    parser.add_argument("--out-report", default="implementation/phase1/release/kds_compliance/midas_kds_row_provenance_table_report.json")
    args = parser.parse_args()

    input_payload = {
        "model_json": str(args.model_json),
        "kds_report": str(args.kds_report),
        "out_json": str(args.out_json),
        "out_csv": str(args.out_csv),
        "out_report": str(args.out_report),
    }
    out_json = Path(args.out_json)
    out_csv = Path(args.out_csv)
    out_report = Path(args.out_report)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_report.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.export_midas_kds_row_provenance_table")
        model_json = Path(args.model_json)
        kds_report = Path(args.kds_report)

        _, report = write_row_provenance_export(
            model_json=model_json,
            kds_report=kds_report,
            out_json=out_json,
            out_csv=out_csv,
            out_report=out_report,
            input_payload=input_payload,
        )
        print(str(report.get("summary_line", "")))
        if not bool(report.get("contract_pass", False)):
            raise SystemExit(1)
    except InputContractError as exc:
        report = {
            "schema_version": "1.0",
            "run_id": "phase1-midas-kds-row-provenance-table-export-report",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "summary_line": "MIDAS KDS row provenance export: CHECK | invalid input",
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": str(exc),
        }
        out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report["summary_line"])
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
