from __future__ import annotations

import argparse
import difflib
import hashlib
from datetime import datetime, timezone
import html
import json
import math
import os
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

try:
    from implementation.phase1.ui_design_tokens import build_signal_desk_light_css
except ImportError:  # pragma: no cover - direct script execution fallback
    from ui_design_tokens import build_signal_desk_light_css
try:
    from implementation.phase1.ui_layout_fragments import (
        render_link_pills,
        render_route_context_banner,
        render_split_hero,
        render_token_row,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from ui_layout_fragments import render_link_pills, render_route_context_banner, render_split_hero, render_token_row


DEFAULT_VIEWER_JSON = Path("implementation/phase1/release/visualization/structural_optimization_viewer.json")
DEFAULT_OUT_HTML = Path("implementation/phase1/release/visualization/optimized_drawing_review.html")
DEFAULT_OUT_EXPERT_HTML = Path("implementation/phase1/release/visualization/optimized_drawing_expert_review.html")
DEFAULT_EXPERT_METADATA_JSON = Path("implementation/phase1/release/visualization/expert_review_issue_metadata.json")
LEGACY_EXPERT_METADATA_TEMPLATE_DIR = Path(
    "implementation/phase1/release/visualization/expert_review_metadata_templates"
)
DEFAULT_EXPERT_METADATA_TEMPLATE_DIR = Path("implementation/phase1/review_metadata_templates")
DEFAULT_EXPERT_METADATA_TEMPLATE_NAME = "default"
DEFAULT_EXPERT_METADATA_TEMPLATE_INDEX = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR / "index.json"
DEFAULT_EXPERT_METADATA_ONBOARDING_SCHEMA = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR / "project_onboarding.schema.json"
DEFAULT_EXPERT_METADATA_ONBOARDING_EXAMPLE = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR / "project_onboarding.example.json"
DEFAULT_EXPERT_METADATA_FIELD_SPEC = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR / "field_spec.json"
DEFAULT_OUT_EXPERT_METADATA_JSON = Path(
    "implementation/phase1/release/visualization/optimized_drawing_expert_review.metadata.json"
)
DEFAULT_OUT_SUMMARY = Path("implementation/phase1/release/visualization/optimized_drawing_review_summary.json")
DEFAULT_REAL_DRAWING_PRIVATE_CORPUS_REPORT = Path(
    "tmp/real_drawing_private_corpus/real_drawing_private_corpus_report.json"
)
DEFAULT_MODEL_OPTIMIZATION_INTAKE_QUEUE = Path(
    "tmp/real_drawing_private_corpus/model_optimization_intake_queue.json"
)
DEFAULT_REDACTED_MANIFEST = Path("tmp/real_drawing_private_corpus/redacted_manifest.json")


def _effective_expert_metadata_template_dir(template_dir: Path) -> Path:
    """Prefer source-controlled templates, but keep old release-template checkouts usable."""
    if template_dir.exists():
        return template_dir
    if template_dir == DEFAULT_EXPERT_METADATA_TEMPLATE_DIR and LEGACY_EXPERT_METADATA_TEMPLATE_DIR.exists():
        return LEGACY_EXPERT_METADATA_TEMPLATE_DIR
    return template_dir

PROJECTIONS: tuple[tuple[str, str, str], ...] = (
    ("plan_xy", "Plan", "평면 기준으로 baseline과 최적화 overlay를 비교합니다."),
    ("elevation_xz", "Elevation", "입면 기준으로 수직 변화와 대표 부재 조정을 확인합니다."),
    ("isometric_xyz", "Isometric", "아이소메트릭 기준으로 전체 형상과 최적화 분포를 읽습니다."),
)

INTERACTIVE_3D_PAYLOAD_CONTRACT_VERSION = "optimized-review-3d-after-segment-v1"
COORDINATE_CONTRACT_VERSION = "optimized-review-3d-coordinate-v1"
WORKSPACE_SELECTION_CONTRACT_VERSION = "optimized-review-workspace-selection-v1"
WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION = "optimized-review-workspace-diff-focus-v1"
WORKSPACE_SELECTION_CONTRACT_FEATURES: dict[str, bool] = {
    "member_restore": True,
    "story_restore": True,
    "grid_restore": True,
    "stale_param_cleanup": True,
    "member_diff_focus": True,
    "non_member_diff_clear": True,
}
CANONICAL_WORKSPACE_SELECTION_PARAMS: tuple[str, ...] = (
    "selection_kind",
    "selection_id",
    "selection_label",
    "selection_provenance",
    "selection_story",
    "selection_contract_version",
)
AFTER_SEGMENT_NULLABLE_METRIC_FIELDS: tuple[str, ...] = (
    "cost_delta",
    "constructability_delta",
    "max_dcr_after",
    "linked_diff_row_count",
)
AFTER_SEGMENT_EVIDENCE_FIELD_NAMES: tuple[str, ...] = (
    "before_after_snapshot_note",
    "ai_reason",
    "optimization_meaning_label",
    "action_name_label",
    "action_family_label",
    "selection_gate_label",
    "review_handoff_summary",
    "source_output_diff_focus",
    "output_diff_focus",
)
AFTER_SEGMENT_REQUIRED_CONTRACT_FIELDS: tuple[str, ...] = (
    "member_id",
    "group_id",
    "member_type",
    "story_band_label",
    "zone_label",
    "action_name",
    "before_section",
    "after_section",
    "before_thickness_scale",
    "after_thickness_scale",
    "before_rebar_ratio",
    "after_rebar_ratio",
    *AFTER_SEGMENT_NULLABLE_METRIC_FIELDS,
    *AFTER_SEGMENT_EVIDENCE_FIELD_NAMES,
    "color",
    "p0",
    "p1",
)
AFTER_SEGMENT_NULLABLE_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "cost_delta": ("cost_delta", "cost_proxy_delta"),
    "constructability_delta": ("constructability_delta",),
    "max_dcr_after": ("max_dcr_after", "max_dcr_after_max"),
    "linked_diff_row_count": ("linked_diff_row_count",),
}
REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS: tuple[str, ...] = (
    "ai_reason",
    "review_handoff_summary",
    "source_output_diff_focus",
    "linked_diff_row_count",
)
REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS: dict[str, str] = {
    "ai_reason": "No data",
    "review_handoff_summary": "No data",
    "source_output_diff_focus": "No data",
    "linked_diff_row_count": "not linked",
}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_text_excerpt(reference: str, *, base_dir: Path, max_chars: int = 12000) -> str:
    for candidate in _candidate_reference_paths(reference, base_dir=base_dir):
        if candidate.exists() and candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8", errors="ignore")[:max_chars]
            except Exception:
                return ""
    return ""


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _nullable_after_segment_metric(row: dict[str, Any], field_name: str) -> float | None:
    for alias in AFTER_SEGMENT_NULLABLE_METRIC_ALIASES.get(field_name, (field_name,)):
        if alias in row:
            return _optional_float(row.get(alias))
    return None


def _representative_evidence_completeness_receipt(
    evidence_values: dict[str, Any],
) -> dict[str, Any]:
    missing_fields: list[str] = []
    display_labels: dict[str, str] = {}
    missing_labels: dict[str, str] = {}
    for field_name in REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS:
        value = evidence_values.get(field_name)
        if field_name == "linked_diff_row_count":
            is_missing = _optional_float(value) is None
            display_label = str(_optional_float(value)) if not is_missing else REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS[field_name]
        else:
            text = str(value or "").strip()
            is_missing = not text
            display_label = text if text else REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS[field_name]
        display_labels[field_name] = display_label
        if is_missing:
            missing_fields.append(field_name)
            missing_labels[field_name] = REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS[field_name]

    if not missing_fields:
        status = "complete"
    elif len(missing_fields) == len(REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS):
        status = "missing"
    else:
        status = "partial"
    return {
        "evidence_completeness_status": status,
        "missing_evidence_fields": missing_fields,
        "missing_evidence_labels": missing_labels,
        "evidence_display_labels": display_labels,
    }


def _representative_evidence_completeness_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"complete": 0, "partial": 0, "missing": 0}
    missing_field_counts = {field_name: 0 for field_name in REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS}
    for row in rows:
        status = str(row.get("evidence_completeness_status", "") or "")
        if status in counts:
            counts[status] += 1
        for field_name in row.get("missing_evidence_fields") or []:
            if field_name in missing_field_counts:
                missing_field_counts[field_name] += 1
    return {
        "total": len(rows),
        "complete": counts["complete"],
        "partial": counts["partial"],
        "missing": counts["missing"],
        "missing_evidence_field_counts": missing_field_counts,
    }


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "")).strip("-").lower()
    return slug or "item"


def _format_signed(value: Any, digits: int = 3) -> str:
    number = _safe_float(value, 0.0)
    return f"{number:+.{digits}f}"


def _format_generated_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
    except Exception:
        return text[:10]


def _resolve_expert_review_metadata(case_context: dict[str, Any]) -> dict[str, Any]:
    for key in (
        "expert_review_metadata",
        "external_expert_metadata",
        "review_package_metadata",
        "title_block_metadata",
    ):
        value = case_context.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _resolve_expert_review_metadata_template(case_context: dict[str, Any]) -> str:
    for key in (
        "expert_review_metadata_template",
        "expert_metadata_template",
        "review_package_template",
        "title_block_template",
    ):
        value = case_context.get(key)
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    elif value is None:
        raw_items = []
    else:
        raw_items = [value]
    items: list[str] = []
    for item in raw_items:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _expert_change_reason(row: dict[str, Any]) -> str:
    story = str(row.get("story_band", "") or row.get("story_band_label", "") or "target story").strip() or "target story"
    zone = str(row.get("zone_label", "") or "critical zone").strip() or "critical zone"
    member_type = str(row.get("member_type", "") or row.get("member_type_label", "") or "member").strip() or "member"
    groups = max(_safe_int(row.get("changed_group_count", 0), 0), 1)
    cost_delta = _safe_float(
        row.get("cost_proxy_delta_sum", row.get("cost_delta", 0.0)),
        0.0,
    )
    constructability = _safe_float(
        row.get("constructability_delta_sum", row.get("constructability_delta", 0.0)),
        0.0,
    )
    max_dcr = _safe_float(row.get("max_dcr_after_max", row.get("max_dcr_after", 0.0)), 0.0)
    return (
        f"{story} {zone} {member_type} changes cover {groups} revision group"
        f"{'' if groups == 1 else 's'}, with quantity/cost proxy {cost_delta:+.3f}, "
        f"constructability {constructability:+.3f}, and governing D/C after change {max_dcr:.3f}."
    )


def _default_expert_issue_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    case_id_raw = str(payload.get("case_id", "") or "optimized_drawing_review")
    generated_date = _format_generated_date(payload.get("generated_at"))
    return {
        "project_title": str(payload.get("case_title", "") or "Optimized Drawing Expert Review"),
        "project_number": f"EXP-{_safe_slug(case_id_raw).replace('-', '_').upper()}",
        "issue_date": generated_date,
        "issue_purpose": "Permit / Committee Submission",
        "revision_code": "REV-00",
        "revision_status": "Issued for review",
        "sheet_size": "A3 landscape",
        "discipline": "Structural Optimization Review",
        "client_name": "Confidential / internal demo",
        "site_name": "Project site to be assigned",
        "jurisdiction": "Authority review route",
        "code_basis": "KDS / project criteria to be confirmed by reviewer",
        "prepared_by": "AI Structural Optimization Review Tool",
        "reviewed_by": "Reviewer to sign",
        "company_name": "AI Structural Optimization Review",
        "committee_package_label": "Permit / Committee Submission",
        "review_route_note": "Machine-verifiable checks are prefilled; reviewer confirmation lines remain open for sign-off.",
    }


def _merge_expert_metadata_layer(base: dict[str, Any], layer: dict[str, Any]) -> None:
    alias_to_canonical = {
        "project_title": "project_name",
        "project_id": "project_number",
        "job_number": "project_number",
        "owner_name": "client_name",
        "site_label": "site_name",
        "project_site": "site_name",
        "jurisdiction": "authority_name",
        "jurisdiction_name": "authority_name",
        "authority_label": "authority_name",
        "issue_purpose": "package_purpose_label",
        "committee_package_label": "package_purpose_label",
        "submission_purpose": "package_purpose_label",
        "issue_stage_label": "issue_phase_label",
        "submission_track_label": "issue_phase_label",
        "permit_track_label": "issue_phase_label",
        "discipline": "discipline_label",
        "prepared_by_label": "prepared_by",
        "reviewed_by_label": "reviewed_by",
    }
    for key, value in layer.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            base[str(key)] = text
            canonical_key = alias_to_canonical.get(str(key))
            if canonical_key:
                base[canonical_key] = text


def _resolve_expert_metadata_template_path(
    template_name: str,
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> Path | None:
    text = str(template_name or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.suffix.lower() == ".json":
        if candidate.is_absolute():
            return candidate
        if candidate.exists():
            return candidate
        return template_dir / candidate
    return template_dir / f"{text}.json"


def _resolve_expert_metadata_template_index_path(
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> Path:
    return template_dir / "index.json"


def _resolve_expert_metadata_onboarding_schema_path(
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> Path:
    return template_dir / "project_onboarding.schema.json"


def _resolve_expert_metadata_onboarding_example_path(
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> Path:
    return template_dir / "project_onboarding.example.json"


def _resolve_expert_metadata_field_spec_path(
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> Path:
    return template_dir / "field_spec.json"


def _load_expert_metadata_template_index(
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> dict[str, Any]:
    return _load_json(_resolve_expert_metadata_template_index_path(template_dir=template_dir))


def _resolve_expert_metadata_template_record(
    selected_template_name: str,
    selected_template_path: str,
    *,
    template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> dict[str, Any]:
    index_payload = _load_expert_metadata_template_index(template_dir=template_dir)
    selected_name = str(selected_template_name or "").strip()
    selected_path = str(selected_template_path or "").strip()
    selected_filename = Path(selected_path).name if selected_path else ""
    matched_entry: dict[str, Any] = {}
    templates = index_payload.get("templates")
    if isinstance(templates, list):
        for entry in templates:
            if not isinstance(entry, dict):
                continue
            entry_name = str(entry.get("name", "") or "").strip()
            entry_path = str(entry.get("path", "") or "").strip()
            if selected_name and entry_name == selected_name:
                matched_entry = dict(entry)
                break
            if selected_filename and entry_path and Path(entry_path).name == selected_filename:
                matched_entry = dict(entry)
                break
    selected_label = (
        str(matched_entry.get("label", "") or "").strip()
        or str(matched_entry.get("description", "") or "").strip()
        or selected_name
    )
    return {
        "template_set_name": str(index_payload.get("template_set_name", "") or "").strip(),
        "template_set_label": str(index_payload.get("template_set_label", "") or "").strip(),
        "template_set_description": str(index_payload.get("template_set_description", "") or "").strip(),
        "default_template": str(index_payload.get("default_template", "") or "").strip(),
        "selected_template": selected_name,
        "selected_template_path": selected_path,
        "selected_template_label": selected_label,
        "selected_template_description": str(matched_entry.get("description", "") or "").strip(),
        "selected_template_recommended_for": _string_list(matched_entry.get("recommended_for")),
        "selected_template_onboarding_focus_fields": _string_list(
            matched_entry.get("onboarding_focus_fields")
        ),
        "template_record_found": bool(matched_entry),
        "template_record": matched_entry,
    }


def _build_expert_metadata_template_selection_receipt(
    template_record: dict[str, Any],
    *,
    source_mode: str,
) -> str:
    parts: list[str] = []
    selected_template = str(template_record.get("selected_template", "") or "").strip() or "default"
    parts.append(f"template={selected_template}")
    selected_label = str(template_record.get("selected_template_label", "") or "").strip()
    if selected_label:
        parts.append(f"label={selected_label}")
    template_set_label = str(template_record.get("template_set_label", "") or "").strip()
    if template_set_label:
        parts.append(f"set={template_set_label}")
    parts.append(f"index={'matched' if template_record.get('template_record_found') else 'fallback'}")
    source_mode_text = str(source_mode or "").strip() or "default_embedded_issue_metadata"
    parts.append(f"source_mode={source_mode_text}")
    selected_path = str(template_record.get("selected_template_path", "") or "").strip()
    if selected_path:
        parts.append(f"path={selected_path}")
    return " | ".join(parts)


def _resolve_merged_expert_review_metadata(
    payload: dict[str, Any],
    *,
    expert_metadata_json_path: Path = DEFAULT_EXPERT_METADATA_JSON,
    expert_metadata_template: str = DEFAULT_EXPERT_METADATA_TEMPLATE_NAME,
    expert_metadata_template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
) -> tuple[dict[str, Any], str, str, str]:
    expert_metadata_template_dir = _effective_expert_metadata_template_dir(expert_metadata_template_dir)
    merged = dict(_default_expert_issue_metadata(payload))
    source_parts: list[str] = []
    index_payload = _load_expert_metadata_template_index(template_dir=expert_metadata_template_dir)
    selected_template_name = str(payload.get("expert_review_metadata_template", "") or "").strip()
    fallback_template_name = str(expert_metadata_template or "").strip()
    if not selected_template_name:
        if fallback_template_name and fallback_template_name != DEFAULT_EXPERT_METADATA_TEMPLATE_NAME:
            selected_template_name = fallback_template_name
        else:
            selected_template_name = (
                str(index_payload.get("default_template", "") or "").strip()
                or fallback_template_name
                or DEFAULT_EXPERT_METADATA_TEMPLATE_NAME
            )
    template_path = _resolve_expert_metadata_template_path(
        selected_template_name,
        template_dir=expert_metadata_template_dir,
    )
    template_payload = _load_json(template_path) if template_path else {}
    if template_payload:
        _merge_expert_metadata_layer(merged, template_payload)
        source_parts.append("template_metadata_json")

    external = _load_json(expert_metadata_json_path)
    if external:
        _merge_expert_metadata_layer(merged, external)
        source_parts.append("external_issue_metadata_json")

    embedded = payload.get("expert_review_metadata") if isinstance(payload.get("expert_review_metadata"), dict) else {}
    if embedded:
        _merge_expert_metadata_layer(merged, embedded)
        source_parts.append("viewer_case_context_metadata")

    if not source_parts:
        return merged, "default_embedded_issue_metadata", selected_template_name, str(template_path or "")
    return merged, "+".join(source_parts), selected_template_name, str(template_path or "")


def _dedupe_search_tokens(values: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _collect_search_tokens(*values: Any) -> list[str]:
    tokens: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        lowered = text.lower()
        tokens.append(lowered)
        tokens.extend(token.lower() for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:+/-]*", text))
    return _dedupe_search_tokens(tokens)


def _placeholder_svg(label: str, message: str) -> str:
    safe_label = html.escape(label, quote=True)
    safe_message = html.escape(message, quote=True)
    return (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 960 540' role='img' "
        f"aria-label='{safe_label}'>"
        "<rect width='960' height='540' rx='24' fill='#f7efe3'/>"
        "<rect x='28' y='28' width='904' height='484' rx='18' fill='#fffaf2' stroke='#d9cfbf'/>"
        f"<text x='56' y='88' fill='#103b4c' font-size='28' font-family='IBM Plex Sans KR, sans-serif' font-weight='700'>{safe_label}</text>"
        f"<text x='56' y='132' fill='#5f6d78' font-size='18' font-family='IBM Plex Sans KR, sans-serif'>{safe_message}</text>"
        "</svg>"
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = "\n".join(line.rstrip() for line in text.splitlines())
    if text.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")


def _rel_href(target: Path | str, *, base_dir: Path, source_base_dir: Path | None = None) -> str:
    target_text = str(target or "").strip()
    if not target_text:
        return ""
    split = urlsplit(target_text)
    if split.scheme or split.netloc:
        return target_text
    if not split.path:
        return target_text
    candidate = Path(split.path)
    base_resolved = base_dir.resolve()
    href_path = split.path
    if candidate.is_absolute():
        href_path = os.path.relpath(candidate, base_resolved)
    elif (base_dir / candidate).exists():
        href_path = split.path
    elif candidate.exists():
        href_path = os.path.relpath(candidate.resolve(), base_resolved)
    elif source_base_dir is not None and (source_base_dir / candidate).exists():
        href_path = os.path.relpath((source_base_dir / candidate).resolve(), base_resolved)
    return urlunsplit(("", "", href_path.replace(os.sep, "/"), split.query, split.fragment))


def _href_with_params(base_href: str, **params: Any) -> str:
    href = str(base_href or "").strip()
    if not href:
        return ""
    split = urlsplit(href)
    merged = dict(parse_qsl(split.query, keep_blank_values=True))
    for key, value in params.items():
        if value in (None, ""):
            continue
        merged[str(key)] = str(value)
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(merged, doseq=True), split.fragment))


def _asset_filename(kind: str, projection_key: str) -> str:
    return f"optimized_drawing_review.{projection_key}.{kind}.svg"


def _write_projection_assets(
    viewer_payload: dict[str, Any],
    *,
    viewer_json_path: Path,
    out_html_path: Path,
) -> dict[str, dict[str, str]]:
    baseline = viewer_payload.get("baseline_structure") if isinstance(viewer_payload.get("baseline_structure"), dict) else {}
    overlay = viewer_payload.get("member_overlay") if isinstance(viewer_payload.get("member_overlay"), dict) else {}
    asset_dir = out_html_path.parent / "optimized_drawing_review_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)
    projection_assets: dict[str, dict[str, str]] = {}
    for projection_key, _, _ in PROJECTIONS:
        baseline_svg = str(baseline.get(f"{projection_key}_svg", "") or "").strip()
        overlay_svg = str(overlay.get(f"{projection_key}_svg", "") or "").strip()
        if not baseline_svg:
            baseline_svg = _placeholder_svg("Baseline drawing unavailable", "Baseline structural drawing SVG is not available.")
        if not overlay_svg:
            overlay_svg = _placeholder_svg("Optimized overlay unavailable", "Optimized member overlay SVG is not available.")
        baseline_path = asset_dir / _asset_filename("baseline", projection_key)
        overlay_path = asset_dir / _asset_filename("overlay", projection_key)
        _write_text(baseline_path, baseline_svg)
        _write_text(overlay_path, overlay_svg)
        projection_assets[projection_key] = {
            "baseline_svg_path": str(baseline_path),
            "overlay_svg_path": str(overlay_path),
            "baseline_svg_href": os.path.relpath(baseline_path, out_html_path.parent),
            "overlay_svg_href": os.path.relpath(overlay_path, out_html_path.parent),
            "baseline_svg_inline": baseline_svg,
            "overlay_svg_inline": overlay_svg,
        }
    return projection_assets


def _dedupe_top_members(rows: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    ordered = sorted(rows, key=lambda row: abs(_safe_float(row.get("cost_delta", 0.0))), reverse=True)
    seen: set[str] = set()
    top_rows: list[dict[str, Any]] = []
    for row in ordered:
        member_id = str(row.get("member_id", "") or "").strip()
        if not member_id or member_id in seen:
            continue
        seen.add(member_id)
        top_rows.append(
            {
                "member_id": member_id,
                "member_type": str(row.get("member_type", "") or ""),
                "story_band_label": str(row.get("story_band_label", "") or ""),
                "zone_label": str(row.get("zone_label", "") or ""),
                "action_name_label": str(row.get("action_name_label", "") or ""),
                "cost_delta": _safe_float(row.get("cost_delta", 0.0)),
                "constructability_delta": _safe_float(row.get("constructability_delta", 0.0)),
                "selection_gate_label": str(row.get("selection_gate_label", "") or ""),
                "before_after_snapshot_note": str(row.get("before_after_snapshot_note", "") or ""),
            }
        )
        if len(top_rows) >= limit:
            break
    return top_rows


def _representative_member_export_fields(
    row: dict[str, Any],
    *,
    base_href: str = "",
    after_segment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence_source = after_segment if isinstance(after_segment, dict) else {}
    member_id = str(row.get("member_id", "") or "").strip()
    story_band_label = str(row.get("story_band_label", "") or "").strip()
    viewer_focus_href = str(row.get("viewer_focus_href", "") or "").strip()
    if not viewer_focus_href and base_href and member_id:
        viewer_focus_href = _href_with_params(
            base_href,
            view="core",
            focus="interactive3d",
            focus_member=member_id,
            member_id=member_id,
            case_id=member_id,
            baseline_secondary="elevation",
        )

    selection_kind = str(row.get("selection_kind", "") or "member").strip() or "member"
    selection_id = str(row.get("selection_id", "") or member_id).strip() or member_id
    selection_label = str(row.get("selection_label", "") or member_id).strip() or member_id
    selection_provenance = str(row.get("selection_provenance", "") or "member-table").strip() or "member-table"
    selection_story = str(row.get("selection_story", "") or story_band_label).strip()
    selection_contract_version = (
        str(row.get("selection_contract_version", "") or WORKSPACE_SELECTION_CONTRACT_VERSION).strip()
        or WORKSPACE_SELECTION_CONTRACT_VERSION
    )
    selection_deep_link_href = str(row.get("selection_deep_link_href", "") or "").strip()
    if not selection_deep_link_href and base_href and member_id:
        selection_deep_link_href = _href_with_params(
            base_href,
            selection_kind=selection_kind,
            selection_id=selection_id,
            selection_label=selection_label,
            selection_provenance=selection_provenance,
            selection_story=selection_story or None,
            selection_contract_version=selection_contract_version,
        )

    def _text(*keys: str, default: str = "") -> str:
        for source in (evidence_source, row):
            if not isinstance(source, dict):
                continue
            for key in keys:
                value = source.get(key)
                if value is None:
                    continue
                text = str(value).strip()
                if text:
                    return text
        return default

    linked_diff_row_count: float | None = None
    for source in (evidence_source, row):
        if not isinstance(source, dict) or "linked_diff_row_count" not in source:
            continue
        linked_diff_row_count = _optional_float(source.get("linked_diff_row_count"))
        if linked_diff_row_count is not None:
            break

    evidence_values = {
        "ai_reason": _text("ai_reason", "optimization_reason", "reason"),
        "review_handoff_summary": _text("review_handoff_summary", "handoff_summary"),
        "source_output_diff_focus": _text("source_output_diff_focus", "output_diff_focus"),
        "linked_diff_row_count": linked_diff_row_count,
    }
    evidence_completeness_receipt = _representative_evidence_completeness_receipt(evidence_values)

    return {
        "member_id": member_id,
        "member_type": str(row.get("member_type", "") or ""),
        "story_band_label": story_band_label,
        "zone_label": str(row.get("zone_label", "") or ""),
        "action_name_label": str(row.get("action_name_label", "") or ""),
        "cost_delta": round(_safe_float(row.get("cost_delta", 0.0)), 3),
        "constructability_delta": round(_safe_float(row.get("constructability_delta", 0.0)), 3),
        "before_after_snapshot_note": _text("before_after_snapshot_note"),
        "viewer_focus_href": viewer_focus_href,
        "selection_kind": selection_kind,
        "selection_id": selection_id,
        "selection_label": selection_label,
        "selection_provenance": selection_provenance,
        "selection_story": selection_story,
        "selection_contract_version": selection_contract_version,
        "selection_deep_link_href": selection_deep_link_href,
        "selection_gate_label": _text("selection_gate_label", "selection_gate", default=str(row.get("selection_gate_label", "") or "")),
        "ai_reason": evidence_values["ai_reason"],
        "optimization_meaning_label": _text("optimization_meaning_label"),
        "action_family_label": _text("action_family_label"),
        "review_handoff_summary": evidence_values["review_handoff_summary"],
        "source_output_diff_focus": evidence_values["source_output_diff_focus"],
        "output_diff_focus": _text("output_diff_focus"),
        "linked_diff_row_count": evidence_values["linked_diff_row_count"],
        **evidence_completeness_receipt,
    }


def _render_top_member_row(row: dict[str, Any]) -> str:
    story_band_label = str(row.get("story_band_label", "") or "").strip()
    story_band_key = story_band_label.lower()
    search_tokens = " ".join(
        [
            str(row.get("member_id", "") or ""),
            str(row.get("member_type", "") or ""),
            story_band_label,
            str(row.get("zone_label", "") or ""),
            str(row.get("action_name_label", "") or ""),
        ]
    ).lower()
    viewer_focus_href = str(row.get("viewer_focus_href", "") or "").strip()
    inspect_html = (
        f"<a class='inspect-link' href='{html.escape(viewer_focus_href)}'>Open</a>"
        if viewer_focus_href
        else "n/a"
    )
    return (
        "<tr "
        "tabindex='0' "
        "aria-selected='false' "
        f"data-member-id='{html.escape(str(row.get('member_id', '') or ''))}' "
        f"data-story-band='{html.escape(story_band_label)}' "
        f"data-story-band-key='{html.escape(story_band_key)}' "
        f"data-search='{html.escape(search_tokens)}'>"
        f"<td data-label='Member'>{html.escape(str(row.get('member_id', '') or 'n/a'))}</td>"
        f"<td data-label='Type'>{html.escape(str(row.get('member_type', '') or 'n/a'))}</td>"
        f"<td data-label='Story'>{html.escape(story_band_label or 'n/a')}</td>"
        f"<td data-label='Zone'>{html.escape(str(row.get('zone_label', '') or 'n/a'))}</td>"
        f"<td data-label='Action'>{html.escape(str(row.get('action_name_label', '') or 'n/a'))}</td>"
        f"<td data-label='Cost delta'>{_safe_float(row.get('cost_delta', 0.0)):.3f}</td>"
        f"<td data-label='Constructability'>{_safe_float(row.get('constructability_delta', 0.0)):.3f}</td>"
        f"<td data-label='Snapshot'>{html.escape(str(row.get('before_after_snapshot_note', '') or 'n/a'))}</td>"
        f"<td data-label='Inspect'>{inspect_html}</td>"
        "</tr>"
    )


def _join_search_tokens(*values: Any) -> str:
    tokens: list[str] = []
    seen: set[str] = set()
    for value in values:
        for token in re.findall(r"[a-z0-9]+", str(value or "").lower()):
            if token and (len(token) > 2 or token.isdigit()) and token not in seen:
                seen.add(token)
                tokens.append(token)
    return " ".join(tokens)


def _sample_diff_member_id(row: dict[str, Any]) -> str:
    candidate_member_ids = [
        str(value).strip()
        for value in (row.get("candidate_member_ids") or [])
        if str(value).strip()
    ]
    if candidate_member_ids:
        return candidate_member_ids[0]
    kind = str(row.get("kind", "") or "replace").strip().lower()
    source_line = str(row.get("source_line", "") or "").strip()
    output_line = str(row.get("output_line", "") or "").strip()
    candidates = (output_line, source_line) if kind == "insert" else (source_line, output_line)
    for candidate in candidates:
        match = re.search(r"\b(\d+)\b", candidate)
        if match:
            return match.group(1)
    return ""


def _sample_diff_member_ids(row: dict[str, Any]) -> list[str]:
    return [
        str(value).strip()
        for value in (row.get("candidate_member_ids") or [])
        if str(value).strip()
    ]


def _sample_diff_section_ids(row: dict[str, Any]) -> list[str]:
    explicit = [
        str(value).strip()
        for value in (row.get("candidate_section_ids") or [])
        if str(value).strip()
    ]
    if explicit:
        return explicit
    tokens = _collect_search_tokens(
        row.get("source_line", ""),
        row.get("output_line", ""),
    )
    return [token for token in tokens if re.fullmatch(r"[a-z0-9_.:+/-]+", token)]


def _read_meaningful_mgt_lines(path: Path) -> list[str]:
    if not path.exists() or not path.is_file():
        return []
    meaningful_lines: list[str] = []
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = str(raw_line or "").strip()
            if not stripped or stripped.startswith(";"):
                continue
            meaningful_lines.append(stripped)
    except Exception:
        return []
    return meaningful_lines


def _read_meaningful_mgt_lines_from_reference(reference: str, *, base_dir: Path) -> list[str]:
    for candidate in _candidate_reference_paths(reference, base_dir=base_dir):
        if candidate.exists() and candidate.is_file():
            return _read_meaningful_mgt_lines(candidate)
    return []


def _dedupe_exact_text_list(values: list[Any]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _normalize_mgt_compare_line(line: str) -> str:
    return re.sub(r"\s+", "", str(line or "").strip())


def _extract_candidate_ids_from_mgt_line(text: str) -> tuple[list[str], list[str], list[str]]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.:+/-]*", str(text or "").strip())
    digit_tokens = [token for token in tokens if any(ch.isdigit() for ch in token)]
    if not digit_tokens and tokens:
        digit_tokens = tokens[:1]
    candidate_member_ids = digit_tokens[:1]
    candidate_section_ids = digit_tokens[1:3]
    candidate_card_ids = candidate_member_ids[:]
    return candidate_member_ids, candidate_section_ids, candidate_card_ids


def _normalize_compare_entry(row: dict[str, Any], *, fallback_index: int = 0) -> dict[str, Any]:
    kind = str(row.get("kind", "") or "replace").strip().lower() or "replace"
    source_line_number = str(row.get("source_line_number", "") or "").strip()
    output_line_number = str(row.get("output_line_number", "") or "").strip()
    source_line = str(row.get("source_line", "") or "").strip()
    output_line = str(row.get("output_line", "") or "").strip()
    display_line = str(row.get("display_line", "") or "").strip()
    if not display_line:
        if kind == "insert":
            display_line = f"+ O:{output_line_number or '-'} | out={output_line}"
        elif kind == "delete":
            display_line = f"- S:{source_line_number or '-'} | src={source_line}"
        elif source_line or output_line:
            display_line = (
                f"~ S:{source_line_number or '-'} O:{output_line_number or '-'} | "
                f"src={source_line} | out={output_line}"
            )
        else:
            display_line = "No source/output diff sample lines available."
    candidate_member_ids = _dedupe_exact_text_list([
        value for value in (row.get("candidate_member_ids") or []) if str(value).strip()
    ])
    candidate_section_ids = _dedupe_exact_text_list([
        value for value in (row.get("candidate_section_ids") or []) if str(value).strip()
    ])
    candidate_card_ids = _dedupe_exact_text_list([
        value for value in (row.get("candidate_card_ids") or []) if str(value).strip()
    ])
    geometry_bridge_member_ids = _dedupe_exact_text_list([
        value for value in (row.get("geometry_bridge_member_ids") or []) if str(value).strip()
    ])
    if not candidate_member_ids or not candidate_section_ids or not candidate_card_ids:
        inferred_member_ids, inferred_section_ids, inferred_card_ids = _extract_candidate_ids_from_mgt_line(
            source_line or output_line or display_line
        )
        if not candidate_member_ids:
            candidate_member_ids = _dedupe_exact_text_list(inferred_member_ids)
        if not candidate_section_ids:
            candidate_section_ids = _dedupe_exact_text_list(inferred_section_ids)
        if not candidate_card_ids:
            candidate_card_ids = _dedupe_exact_text_list(inferred_card_ids)
    exact_member_id_match = bool(row.get("exact_member_id_match", False))
    member_id = str(row.get("member_id", "") or "").strip() or (candidate_member_ids[0] if candidate_member_ids else "")
    if not exact_member_id_match and member_id:
        exact_member_id_match = member_id in candidate_member_ids or member_id in geometry_bridge_member_ids
    search_tokens = _collect_search_tokens(
        fallback_index,
        kind,
        member_id,
        source_line_number,
        output_line_number,
        source_line,
        output_line,
        display_line,
        *candidate_member_ids,
        *candidate_section_ids,
        *candidate_card_ids,
        *geometry_bridge_member_ids,
    )
    return {
        "kind": kind,
        "member_id": member_id,
        "source_line_number": source_line_number,
        "output_line_number": output_line_number,
        "source_line": source_line,
        "output_line": output_line,
        "display_line": display_line,
        "candidate_member_ids": candidate_member_ids,
        "candidate_section_ids": candidate_section_ids,
        "candidate_card_ids": candidate_card_ids,
        "geometry_bridge_member_ids": geometry_bridge_member_ids,
        "exact_member_id_match": exact_member_id_match,
        "search_tokens": search_tokens,
        "search_text": " ".join(search_tokens),
    }


def _compare_entry_key(entry: dict[str, Any]) -> str:
    return " | ".join(
        [
            str(entry.get("kind", "") or "replace"),
            str(entry.get("source_line_number", "") or ""),
            str(entry.get("output_line_number", "") or ""),
            _normalize_mgt_compare_line(entry.get("source_line", "")),
            _normalize_mgt_compare_line(entry.get("output_line", "")),
            _normalize_mgt_compare_line(entry.get("display_line", "")),
        ]
    )


def _build_compare_window_artifacts(
    source_reference: str,
    output_reference: str,
    *,
    base_dir: Path,
    sample_limit: int = 24,
) -> dict[str, Any]:
    source_lines = _read_meaningful_mgt_lines_from_reference(source_reference, base_dir=base_dir)
    output_lines = _read_meaningful_mgt_lines_from_reference(output_reference, base_dir=base_dir)
    summary: dict[str, Any] = {
        "available": False,
        "summary_line": "compare_window: unavailable",
        "source_line_count": len(source_lines),
        "output_line_count": len(output_lines),
        "row_count": 0,
        "rows": [],
        "preview_lines": [],
        "preview_text": "",
    }
    if not source_lines or not output_lines:
        return summary
    matcher = difflib.SequenceMatcher(
        a=[_normalize_mgt_compare_line(line) for line in source_lines],
        b=[_normalize_mgt_compare_line(line) for line in output_lines],
        autojunk=False,
    )
    rows: list[dict[str, Any]] = []
    for tag, source_start, source_end, output_start, output_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        source_span = source_end - source_start
        output_span = output_end - output_start
        if tag == "replace":
            span = min(source_span, output_span)
            for offset in range(span):
                if len(rows) >= sample_limit:
                    break
                rows.append(
                    _normalize_compare_entry(
                        {
                            "kind": "replace",
                            "source_line_number": source_start + offset + 1,
                            "output_line_number": output_start + offset + 1,
                            "source_line": source_lines[source_start + offset],
                            "output_line": output_lines[output_start + offset],
                        },
                        fallback_index=len(rows),
                    )
                )
            if len(rows) >= sample_limit:
                break
            if source_span > output_span:
                for offset in range(output_span, source_span):
                    if len(rows) >= sample_limit:
                        break
                    rows.append(
                        _normalize_compare_entry(
                            {
                                "kind": "delete",
                                "source_line_number": source_start + offset + 1,
                                "output_line_number": "",
                                "source_line": source_lines[source_start + offset],
                                "output_line": "",
                            },
                            fallback_index=len(rows),
                        )
                    )
            elif output_span > source_span:
                for offset in range(source_span, output_span):
                    if len(rows) >= sample_limit:
                        break
                    rows.append(
                        _normalize_compare_entry(
                            {
                                "kind": "insert",
                                "source_line_number": "",
                                "output_line_number": output_start + offset + 1,
                                "source_line": "",
                                "output_line": output_lines[output_start + offset],
                            },
                            fallback_index=len(rows),
                        )
                    )
        elif tag == "delete":
            for offset in range(source_span):
                if len(rows) >= sample_limit:
                    break
                rows.append(
                    _normalize_compare_entry(
                        {
                            "kind": "delete",
                            "source_line_number": source_start + offset + 1,
                            "output_line_number": "",
                            "source_line": source_lines[source_start + offset],
                            "output_line": "",
                        },
                        fallback_index=len(rows),
                    )
                )
        elif tag == "insert":
            for offset in range(output_span):
                if len(rows) >= sample_limit:
                    break
                rows.append(
                    _normalize_compare_entry(
                        {
                            "kind": "insert",
                            "source_line_number": "",
                            "output_line_number": output_start + offset + 1,
                            "source_line": "",
                            "output_line": output_lines[output_start + offset],
                        },
                        fallback_index=len(rows),
                    )
                )
        if len(rows) >= sample_limit:
            break
    if not rows:
        return summary
    preview_lines = [
        "MIDAS source vs output compare window",
        f"source_mgt={source_reference}",
        f"output_mgt={output_reference}",
        f"compare_window: rows={len(rows)} | source_lines={len(source_lines)} | output_lines={len(output_lines)}",
        "",
        "Sample compare rows:",
    ]
    preview_lines.extend(str(row.get("display_line", "") or "") for row in rows[:sample_limit])
    summary.update(
        {
            "available": True,
            "summary_line": (
                f"compare_window: rows={len(rows)} | source_lines={len(source_lines)} | output_lines={len(output_lines)}"
            ),
            "row_count": len(rows),
            "rows": rows,
            "preview_lines": preview_lines,
            "preview_text": "\n".join(preview_lines),
        }
    )
    return summary


def _compact_point(values: Any) -> list[float]:
    return _compact_point_with_validity(values)[0]


def _compact_point_with_validity(values: Any) -> tuple[list[float], bool]:
    return _compact_point_with_validity_details(values)[0:2]


def _json_safe_coordinate_metadata(value: Any, *, max_list_items: int | None = None) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (list, tuple)):
        items = list(value)
        if max_list_items is not None:
            items = items[:max_list_items]
        return [_json_safe_coordinate_metadata(item) for item in items]
    if isinstance(value, dict):
        return {str(key): _json_safe_coordinate_metadata(item) for key, item in value.items()}
    return str(value)


def _json_safe_coordinate_sample(value: Any) -> Any:
    return _json_safe_coordinate_metadata(value, max_list_items=4)


def _coordinate_raw_shape(values: Any) -> dict[str, Any]:
    shape: dict[str, Any] = {"type": type(values).__name__}
    if isinstance(values, (list, tuple)):
        shape["length"] = len(values)
        shape["item_types"] = [type(item).__name__ for item in list(values)[:3]]
    return shape


def _coordinate_diagnostic(endpoint: str, values: Any, reason: str, *, component_index: int | None = None) -> dict[str, Any]:
    diagnostic = {
        "endpoint": endpoint,
        "reason": reason,
        "raw_shape": _coordinate_raw_shape(values),
        "raw_sample": _json_safe_coordinate_sample(values),
    }
    if component_index is not None:
        diagnostic["component_index"] = component_index
    return diagnostic


def _compact_point_with_validity_details(values: Any, *, endpoint: str = "point") -> tuple[list[float], bool, dict[str, Any]]:
    if not isinstance(values, (list, tuple)):
        reason = "missing" if values is None else "not_array"
        return [0.0, 0.0, 0.0], False, _coordinate_diagnostic(endpoint, values, reason)
    if len(values) < 3:
        return [0.0, 0.0, 0.0], False, _coordinate_diagnostic(endpoint, values, "short")
    compact: list[float] = []
    for index, value in enumerate(values[:3]):
        if value is None or isinstance(value, bool):
            reason = "bool" if isinstance(value, bool) else "null"
            return [0.0, 0.0, 0.0], False, _coordinate_diagnostic(endpoint, values, reason, component_index=index)
        try:
            numeric = float(value)
        except Exception:
            return [0.0, 0.0, 0.0], False, _coordinate_diagnostic(endpoint, values, "non_numeric", component_index=index)
        if not math.isfinite(numeric):
            return [0.0, 0.0, 0.0], False, _coordinate_diagnostic(endpoint, values, "non_finite", component_index=index)
        compact.append(round(numeric, 3))
    return compact, True, {}


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _merge_coordinate_diagnostics(
    upstream: Any,
    generated: dict[str, dict[str, Any]],
    fallback_fields: list[str],
    *,
    upstream_invalid: bool,
) -> dict[str, Any]:
    safe_upstream = _json_safe_coordinate_metadata(_safe_dict(upstream))
    diagnostics = dict(safe_upstream) if isinstance(safe_upstream, dict) else {}
    endpoint_reasons = dict(_safe_dict(diagnostics.get("endpoint_reasons")))
    raw_shapes = dict(_safe_dict(diagnostics.get("raw_shapes")))
    for endpoint, detail in generated.items():
        endpoint_reasons[endpoint] = detail.get("reason", "invalid")
        raw_shapes[endpoint] = detail.get("raw_shape", {})
        diagnostics[endpoint] = detail
    if upstream_invalid and not diagnostics.get("upstream_coordinate_valid"):
        diagnostics["upstream_coordinate_valid"] = False
    diagnostics["endpoint_reasons"] = endpoint_reasons
    diagnostics["raw_shapes"] = raw_shapes
    diagnostics["fallback_fields"] = fallback_fields
    return diagnostics


def _merge_coordinate_provenance(
    upstream: Any,
    generated: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    provenance: list[dict[str, Any]] = []
    if isinstance(upstream, list):
        provenance.extend(
            item
            for item in (_json_safe_coordinate_metadata(entry) for entry in upstream if isinstance(entry, dict))
            if isinstance(item, dict)
        )
    elif isinstance(upstream, dict):
        safe_upstream = _json_safe_coordinate_metadata(upstream)
        if isinstance(safe_upstream, dict):
            provenance.append(safe_upstream)
    provenance.extend(generated)
    return provenance


def _coordinate_contract_fields(row: dict[str, Any]) -> dict[str, Any]:
    p0, p0_valid, p0_diagnostic = _compact_point_with_validity_details(row.get("p0"), endpoint="p0")
    p1, p1_valid, p1_diagnostic = _compact_point_with_validity_details(row.get("p1"), endpoint="p1")
    upstream_invalid = row.get("coordinate_valid") is False
    fallback_fields = [
        str(field).strip()
        for field in _safe_list(row.get("coordinate_fallback_fields"))
        if str(field).strip()
    ]
    generated_diagnostics: dict[str, dict[str, Any]] = {}
    generated_provenance: list[dict[str, Any]] = []
    if not p0_valid:
        fallback_fields.append("p0")
        generated_diagnostics["p0"] = p0_diagnostic
        generated_provenance.append({"endpoint": "p0", "field": "p0", "reason": p0_diagnostic.get("reason", "invalid"), "source": "compact_coordinate_contract"})
    if not p1_valid:
        fallback_fields.append("p1")
        generated_diagnostics["p1"] = p1_diagnostic
        generated_provenance.append({"endpoint": "p1", "field": "p1", "reason": p1_diagnostic.get("reason", "invalid"), "source": "compact_coordinate_contract"})
    fallback_fields = list(dict.fromkeys(fallback_fields))
    coordinate_valid = not fallback_fields and not upstream_invalid
    upstream_status = str(row.get("coordinate_status", "") or "").strip()
    coordinate_status = upstream_status if upstream_invalid and upstream_status else ("valid" if coordinate_valid else f"fallback:{','.join(fallback_fields) or 'upstream'}")
    diagnostics = _merge_coordinate_diagnostics(
        row.get("coordinate_fallback_diagnostics"),
        generated_diagnostics,
        fallback_fields,
        upstream_invalid=upstream_invalid,
    )
    provenance = _merge_coordinate_provenance(row.get("coordinate_fallback_provenance"), generated_provenance)
    if coordinate_valid:
        diagnostics = {}
        provenance = []
    return {
        "p0": p0,
        "p1": p1,
        "coordinate_valid": coordinate_valid,
        "coordinate_status": coordinate_status,
        "coordinate_fallback_fields": fallback_fields,
        "coordinate_fallback_provenance": provenance,
        "coordinate_fallback_diagnostics": diagnostics,
    }


def _candidate_reference_paths(reference: str, *, base_dir: Path) -> list[Path]:
    raw = str(reference or "").strip()
    if not raw:
        return []
    path = Path(raw)
    if path.is_absolute():
        return [path]
    candidates: list[Path] = []
    seen: set[str] = set()
    for base in [Path.cwd().resolve(), base_dir.resolve(), *base_dir.resolve().parents]:
        candidate = (base / path).resolve()
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(candidate)
    return candidates


def _load_upstream_payload(reference: str, *, base_dir: Path) -> tuple[dict[str, Any], str]:
    for candidate in _candidate_reference_paths(reference, base_dir=base_dir):
        if candidate.exists() and candidate.is_file():
            return _load_json(candidate), str(candidate)
    return {}, ""


def _load_mgt_export_report(
    *,
    viewer_json_path: Path,
    case_context: dict[str, Any],
    artifact_links: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    candidate_refs: list[str] = []
    for ref in [
        case_context.get("mgt_export_report_path"),
        case_context.get("mgt_export_report_json"),
        artifact_links.get("mgt_export_report_json"),
        artifact_links.get("ai_mgt_export_report_json"),
    ]:
        ref_text = str(ref or "").strip()
        if ref_text:
            candidate_refs.append(ref_text)
    candidate_refs.append(
        str(viewer_json_path.parent.parent.parent / "open_data/midas/midas_generator_33.optimized.export_report.json")
    )
    seen: set[str] = set()
    for ref in candidate_refs:
        if ref in seen:
            continue
        seen.add(ref)
        payload, resolved = _load_upstream_payload(ref, base_dir=viewer_json_path.parent)
        if payload:
            return payload, resolved
    return {}, ""


def _load_midas_native_roundtrip_gate_report(
    *,
    viewer_json_path: Path,
    case_context: dict[str, Any],
    artifact_links: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    candidate_refs: list[str] = []
    for ref in [
        case_context.get("midas_native_roundtrip_gate_report_path"),
        case_context.get("midas_native_roundtrip_gate_report_json"),
        artifact_links.get("midas_native_roundtrip_gate_report_json"),
    ]:
        ref_text = str(ref or "").strip()
        if ref_text:
            candidate_refs.append(ref_text)
    candidate_refs.append(str(viewer_json_path.parent.parent.parent / "midas_native_roundtrip_gate_report.json"))
    seen: set[str] = set()
    for ref in candidate_refs:
        if ref in seen:
            continue
        seen.add(ref)
        payload, resolved = _load_upstream_payload(ref, base_dir=viewer_json_path.parent)
        if payload:
            return payload, resolved
    return {}, ""


def _axis_dimension_from_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in {"x", "x_axis", "x_axes", "axis_x", "grid_x"} or " x" in f" {text}" or text.startswith("x_"):
        return "x"
    if text in {"y", "y_axis", "y_axes", "axis_y", "grid_y"} or " y" in f" {text}" or text.startswith("y_"):
        return "y"
    if text in {"z", "z_axis", "z_axes", "axis_z", "grid_z", "story", "stories", "level", "levels"} or text.startswith("z_"):
        return "z"
    if "story" in text or "level" in text or "elevation" in text:
        return "z"
    if "axis" in text or "grid" in text:
        if any(token in text for token in ["horizontal", "east-west", "ew"]):
            return "x"
        if any(token in text for token in ["vertical", "north-south", "ns"]):
            return "y"
    return ""


def _extract_axis_value(row: dict[str, Any], *, dimension_hint: str) -> float | None:
    keys = [
        "value",
        "coord",
        "coordinate",
        "position",
        "offset",
        "center",
        "elevation",
        dimension_hint,
    ]
    for key in keys:
        if key and key in row:
            try:
                return round(float(row.get(key)), 3)
            except Exception:
                continue
    return None


def _coerce_axis_row(row: Any, *, dimension_hint: str = "") -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    dimension = (
        _axis_dimension_from_text(row.get("dimension"))
        or _axis_dimension_from_text(row.get("axis"))
        or _axis_dimension_from_text(row.get("orientation"))
        or dimension_hint
    )
    label = ""
    for key in ("label", "name", "axis_name", "grid_name", "grid_label", "axis_label", "story_label", "level_name", "id"):
        value = str(row.get(key, "") or "").strip()
        if value:
            label = value
            break
    value = _extract_axis_value(row, dimension_hint=dimension)
    if not label or value is None:
        return None
    return {
        "dimension": dimension or "z",
        "label": label,
        "value": value,
        "count": max(_safe_int(row.get("count", 1), 1), 1),
    }


def _merge_axis_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, float], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("label", "") or ""), round(_safe_float(row.get("value", 0.0)), 3))
        if key not in merged:
            merged[key] = {
                "label": str(row.get("label", "") or ""),
                "value": round(_safe_float(row.get("value", 0.0)), 3),
                "count": max(_safe_int(row.get("count", 1), 1), 1),
            }
            continue
        merged[key]["count"] = max(
            _safe_int(merged[key].get("count", 1), 1),
            _safe_int(row.get("count", 1), 1),
        )
    return sorted(merged.values(), key=lambda item: (_safe_float(item.get("value", 0.0)), str(item.get("label", ""))))


def _extract_named_axis_refs_from_object(payload: Any, *, path_hint: str = "") -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {"x": [], "y": [], "z": []}

    def visit(node: Any, *, context: str = "") -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                next_context = str(key or "")
                context_label = f"{context} {next_context}".strip().lower()
                axis_container = any(token in context_label for token in ("axis", "grid", "story", "level"))
                dimension_hint = _axis_dimension_from_text(next_context) or _axis_dimension_from_text(context)
                if isinstance(value, list) and (
                    axis_container
                    or (next_context.lower() in {"x", "y", "z"} and any(token in str(context or "").lower() for token in ("axis", "grid", "story", "level")))
                ):
                    for item in value:
                        row = _coerce_axis_row(item, dimension_hint=dimension_hint)
                        if row:
                            found[str(row.get("dimension", "z"))].append(row)
                elif isinstance(value, dict) and next_context.lower() in {"x", "y", "z"} and axis_container:
                    row = _coerce_axis_row(value, dimension_hint=next_context.lower())
                    if row:
                        found[str(row.get("dimension", "z"))].append(row)
                visit(value, context=next_context)
        elif isinstance(node, list):
            for item in node:
                visit(item, context=context)

    visit(payload, context=path_hint)
    return {dimension: _merge_axis_rows(rows) for dimension, rows in found.items()}


def _cluster_axis_refs(values: list[float], *, prefix: str, tolerance: float = 1.25, limit: int = 6) -> list[dict[str, Any]]:
    ordered = sorted(_safe_float(value) for value in values)
    if not ordered:
        return []
    clusters: list[dict[str, Any]] = []
    for value in ordered:
        if not clusters:
            clusters.append({"center": value, "values": [value]})
            continue
        last = clusters[-1]
        if abs(value - _safe_float(last.get("center", 0.0))) <= tolerance:
            last_values = list(last.get("values", []))
            last_values.append(value)
            last["values"] = last_values
            last["center"] = sum(last_values) / max(len(last_values), 1)
        else:
            clusters.append({"center": value, "values": [value]})
    significant = [cluster for cluster in clusters if len(cluster.get("values", [])) >= 8]
    selected = significant or clusters
    if len(selected) > limit:
        selected = sorted(selected, key=lambda cluster: (-len(cluster.get("values", [])), _safe_float(cluster.get("center", 0.0))))[:limit]
    selected = sorted(selected, key=lambda cluster: _safe_float(cluster.get("center", 0.0)))
    return [
        {
            "label": f"{prefix}{index + 1}",
            "value": round(_safe_float(cluster.get("center", 0.0)), 3),
            "count": len(cluster.get("values", [])),
        }
        for index, cluster in enumerate(selected)
    ]


def _normalize_story_band_key(value: Any) -> str:
    key = str(value or "").strip().lower()
    story_match = re.match(r"^s0*(\d+)$", key)
    normalized = story_match.group(1) if story_match else key
    return re.sub(r"^0+(?=\d)", "", normalized)


def _valid_point_array(point: Any) -> bool:
    if not isinstance(point, (list, tuple)) or len(point) < 3:
        return False
    for value in point[:3]:
        try:
            numeric = float(value)
        except Exception:
            return False
        if not math.isfinite(numeric):
            return False
    return True


def _is_renderable_story_segment(segment: dict[str, Any]) -> bool:
    return (
        bool(segment)
        and segment.get("coordinate_valid") is not False
        and _valid_point_array(segment.get("p0"))
        and _valid_point_array(segment.get("p1"))
    )


def _annotate_story_band_rows(
    story_band_rows: list[dict[str, Any]],
    interactive_3d_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    counts_by_story_key: dict[str, dict[str, int]] = {}
    for segment in [
        *([row for row in (interactive_3d_payload.get("baseline_segments") or []) if isinstance(row, dict)]),
        *([row for row in (interactive_3d_payload.get("after_segments") or []) if isinstance(row, dict)]),
    ]:
        story_label = str(segment.get("story_band_label", "") or "").strip()
        story_key = _normalize_story_band_key(story_label)
        if not story_key:
            continue
        counts = counts_by_story_key.setdefault(
            story_key,
            {
                "total_segment_count": 0,
                "renderable_segment_count": 0,
                "focusable_segment_count": 0,
                "invalid_excluded_count": 0,
            },
        )
        counts["total_segment_count"] += 1
        if _is_renderable_story_segment(segment):
            counts["renderable_segment_count"] += 1
            counts["focusable_segment_count"] += 1
        else:
            counts["invalid_excluded_count"] += 1

    annotated_rows: list[dict[str, Any]] = []
    for row in story_band_rows:
        story_label = str(row.get("story_band", "") or row.get("story_band_label", "") or "").strip()
        counts = counts_by_story_key.get(_normalize_story_band_key(story_label), {})
        annotated_row = dict(row)
        annotated_row["total_segment_count"] = _safe_int(counts.get("total_segment_count", 0))
        annotated_row["renderable_segment_count"] = _safe_int(counts.get("renderable_segment_count", 0))
        annotated_row["focusable_segment_count"] = _safe_int(counts.get("focusable_segment_count", 0))
        annotated_row["invalid_excluded_count"] = _safe_int(counts.get("invalid_excluded_count", 0))
        annotated_rows.append(annotated_row)
    return annotated_rows


def _build_story_refs(baseline_segments: list[dict[str, Any]], after_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_story: dict[str, list[float]] = {}
    for row in [*baseline_segments, *after_segments]:
        if not bool(row.get("coordinate_valid", False)):
            continue
        story_label = str(row.get("story_band_label", "") or "").strip()
        if not story_label:
            continue
        p0 = row.get("p0") if isinstance(row.get("p0"), list) and len(row.get("p0")) == 3 else _compact_point(row.get("p0"))
        p1 = row.get("p1") if isinstance(row.get("p1"), list) and len(row.get("p1")) == 3 else _compact_point(row.get("p1"))
        midpoint_z = round((p0[2] + p1[2]) / 2.0, 3)
        by_story.setdefault(story_label, []).append(midpoint_z)
    ordered = []
    for label, values in by_story.items():
        average = round(sum(values) / max(len(values), 1), 3)
        ordered.append({"label": label, "value": average, "count": len(values)})
    return sorted(ordered, key=lambda row: _safe_float(row.get("value", 0.0)))


def _compact_3d_baseline_segment(row: dict[str, Any]) -> dict[str, Any]:
    coordinate_fields = _coordinate_contract_fields(row)
    return {
        "member_id": str(row.get("member_id", "") or "").strip(),
        "member_type": str(row.get("category", "") or "").strip() or "beam",
        "story_band_label": str(row.get("story_band_label", "") or "").strip(),
        "section_name": str(row.get("section_name", "") or "").strip(),
        "section_id": _safe_int(row.get("section_id", 0)),
        "color": str(row.get("color", "") or "").strip(),
        **coordinate_fields,
    }


def _compact_3d_after_segment(row: dict[str, Any]) -> dict[str, Any]:
    coordinate_fields = _coordinate_contract_fields(row)
    evidence_fields = {
        "before_after_snapshot_note": str(row.get("before_after_snapshot_note", "") or "").strip(),
        "ai_reason": str(row.get("ai_reason", row.get("optimization_reason", row.get("reason", ""))) or "").strip(),
        "optimization_meaning_label": str(row.get("optimization_meaning_label", "") or "").strip(),
        "action_name_label": str(row.get("action_name_label", "") or "").strip(),
        "action_family_label": str(row.get("action_family_label", row.get("action_family", "")) or "").strip(),
        "selection_gate_label": str(row.get("selection_gate_label", row.get("selection_gate", "")) or "").strip(),
        "review_handoff_summary": str(row.get("review_handoff_summary", row.get("handoff_summary", "")) or "").strip(),
        "source_output_diff_focus": str(row.get("source_output_diff_focus", "") or "").strip(),
        "output_diff_focus": str(row.get("output_diff_focus", "") or "").strip(),
    }
    compact = {
        "member_id": str(row.get("member_id", "") or "").strip(),
        "group_id": str(row.get("group_id", "") or "").strip(),
        "member_type": str(row.get("member_type", "") or "").strip() or "beam",
        "story_band_label": str(row.get("story_band_label", "") or "").strip(),
        "zone_label": str(row.get("zone_label", "") or "").strip(),
        "action_name": str(row.get("action_name", "") or "").strip(),
        "before_section": str(row.get("before_section", "") or "").strip(),
        "after_section": str(row.get("after_section", "") or "").strip(),
        "before_thickness_scale": _safe_float(row.get("before_thickness_scale", 0.0)),
        "after_thickness_scale": _safe_float(row.get("after_thickness_scale", 0.0)),
        "before_rebar_ratio": _safe_float(row.get("before_rebar_ratio", 0.0)),
        "after_rebar_ratio": _safe_float(row.get("after_rebar_ratio", 0.0)),
        **{field_name: _nullable_after_segment_metric(row, field_name) for field_name in AFTER_SEGMENT_NULLABLE_METRIC_FIELDS},
        **evidence_fields,
        "color": str(row.get("color", "") or "").strip(),
        **coordinate_fields,
    }
    return compact


def _build_after_segment_contract_validation(after_rows_raw: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> dict[str, Any]:
    segments_with_all_contract_fields = sum(
        1 for row in after_rows if all(field_name in row for field_name in AFTER_SEGMENT_REQUIRED_CONTRACT_FIELDS)
    )
    return {
        "after_segment_count": len(after_rows_raw),
        "compact_after_segment_count": len(after_rows),
        "after_segment_count_matches": len(after_rows_raw) == len(after_rows),
        "segments_with_all_contract_fields": segments_with_all_contract_fields,
    }


def _build_coordinate_contract_validation(
    baseline_rows_raw: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    after_rows_raw: list[dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    preview_limit = 8
    valid_rows = [row for row in [*baseline_rows, *after_rows] if bool(row.get("coordinate_valid", False))]
    valid_points = [
        point
        for row in valid_rows
        for point in (row.get("p0"), row.get("p1"))
        if isinstance(point, list) and len(point) == 3
    ]

    def _invalid_row_detail(row: dict[str, Any], *, lane: str, index: int) -> dict[str, Any]:
        return {
            "lane": lane,
            "index": index,
            "member_id": str(row.get("member_id", "") or "").strip(),
            "coordinate_status": str(row.get("coordinate_status", "") or "").strip(),
            "coordinate_fallback_fields": _safe_list(row.get("coordinate_fallback_fields")),
            "coordinate_fallback_diagnostics": _safe_dict(row.get("coordinate_fallback_diagnostics")),
        }

    def _lane_stats(rows_raw: list[dict[str, Any]], rows: list[dict[str, Any]], prefix: str) -> dict[str, Any]:
        invalid_indexed_rows = [(index, row) for index, row in enumerate(rows) if not bool(row.get("coordinate_valid", False))]
        invalid_rows = [row for _, row in invalid_indexed_rows]
        fallback_fields = [
            field
            for row in invalid_rows
            for field in (row.get("coordinate_fallback_fields") or [])
            if str(field).strip()
        ]
        invalid_preview = [
            _invalid_row_detail(row, lane=prefix, index=index)
            for index, row in invalid_indexed_rows[:preview_limit]
        ]
        return {
            f"{prefix}_segment_count": len(rows_raw),
            f"compact_{prefix}_segment_count": len(rows),
            f"{prefix}_invalid_coordinate_count": len(invalid_rows),
            f"{prefix}_coordinate_fallback_field_count": len(fallback_fields),
            f"{prefix}_coordinate_fallback_fields": fallback_fields,
            f"{prefix}_invalid_coordinate_preview": invalid_preview,
            f"{prefix}_invalid_coordinate_preview_limit": preview_limit,
            f"{prefix}_invalid_coordinate_truncated_count": max(0, len(invalid_rows) - len(invalid_preview)),
        }

    baseline_stats = _lane_stats(baseline_rows_raw, baseline_rows, "baseline")
    after_stats = _lane_stats(after_rows_raw, after_rows, "after")
    total_invalid = (
        _safe_int(baseline_stats.get("baseline_invalid_coordinate_count", 0))
        + _safe_int(after_stats.get("after_invalid_coordinate_count", 0))
    )
    total_fallback_fields = (
        _safe_int(baseline_stats.get("baseline_coordinate_fallback_field_count", 0))
        + _safe_int(after_stats.get("after_coordinate_fallback_field_count", 0))
    )
    invalid_preview = [
        *(_safe_list(baseline_stats.get("baseline_invalid_coordinate_preview"))),
        *(_safe_list(after_stats.get("after_invalid_coordinate_preview"))),
    ][:preview_limit]
    valid_geometry_available = bool(valid_rows and valid_points)
    return {
        **baseline_stats,
        **after_stats,
        "total_segment_count": len(baseline_rows_raw) + len(after_rows_raw),
        "compact_total_segment_count": len(baseline_rows) + len(after_rows),
        "valid_geometry_available": valid_geometry_available,
        "no_valid_geometry": not valid_geometry_available,
        "geometry_status": "valid_geometry_available" if valid_geometry_available else "no_valid_geometry",
        "valid_point_count": len(valid_points),
        "valid_segment_count": len(valid_rows),
        "invalid_excluded_count": total_invalid,
        "invalid_coordinate_count": total_invalid,
        "coordinate_fallback_field_count": total_fallback_fields,
        "invalid_coordinate_preview": invalid_preview,
        "invalid_coordinate_preview_limit": preview_limit,
        "invalid_coordinate_truncated_count": max(0, total_invalid - len(invalid_preview)),
        "invalid_coordinate_details": {
            "baseline": _safe_list(baseline_stats.get("baseline_invalid_coordinate_preview")),
            "after": _safe_list(after_stats.get("after_invalid_coordinate_preview")),
            "preview_limit": preview_limit,
        },
        "coordinate_contract_valid": total_invalid == 0,
    }


def _build_3d_payload(viewer_payload: dict[str, Any], *, viewer_json_path: Path) -> dict[str, Any]:
    interactive = viewer_payload.get("interactive_3d") if isinstance(viewer_payload.get("interactive_3d"), dict) else {}
    case_context = viewer_payload.get("case_context") if isinstance(viewer_payload.get("case_context"), dict) else {}
    baseline_rows_raw = [row for row in (interactive.get("baseline_segments") or []) if isinstance(row, dict)]
    after_rows_raw = [row for row in (interactive.get("after_segments") or []) if isinstance(row, dict)]
    baseline_rows = [_compact_3d_baseline_segment(row) for row in baseline_rows_raw]
    after_rows = [_compact_3d_after_segment(row) for row in after_rows_raw]
    valid_coordinate_rows = [row for row in [*baseline_rows, *after_rows] if bool(row.get("coordinate_valid", False))]
    all_points = [
        point
        for row in valid_coordinate_rows
        for point in (row.get("p0"), row.get("p1"))
        if isinstance(point, list) and len(point) == 3
    ]
    valid_geometry_available = bool(valid_coordinate_rows and all_points)
    total_segment_count = len(baseline_rows) + len(after_rows)
    valid_segment_count = len(valid_coordinate_rows)
    invalid_excluded_count = max(0, total_segment_count - valid_segment_count)
    xs = [_safe_float(point[0]) for point in all_points] or [0.0]
    ys = [_safe_float(point[1]) for point in all_points] or [0.0]
    zs = [_safe_float(point[2]) for point in all_points] or [0.0]
    interactive_axis_refs = _extract_named_axis_refs_from_object(
        {"axis_refs": interactive.get("named_axis_refs") or interactive.get("axis_refs") or {}},
        path_hint="interactive_axis_refs",
    )
    axis_ref_source_mode = str(interactive.get("axis_ref_source_mode", "") or "geometry_derived_axis_refs").strip() or "geometry_derived_axis_refs"
    axis_ref_note = str(
        interactive.get("axis_ref_note", "") or "Explicit MIDAS grid axis names are not surfaced in the current geometry-bridge payload, so the 3D workspace uses geometry-derived axis references."
    ).strip()
    axis_ref_source_path = str(interactive.get("axis_ref_source_path", "") or "").strip()
    upstream_axis_refs = {"x": [], "y": [], "z": []}
    explicit_named_axis_available = False
    if axis_ref_source_mode == "geometry_derived_axis_refs":
        candidate_source_path = ""
        upstream_axis_refs = _extract_named_axis_refs_from_object(viewer_payload, path_hint="viewer_payload")
        if not any(upstream_axis_refs.values()):
            model_path = str(case_context.get("model_path", "") or "").strip()
            if model_path:
                upstream_payload, candidate_source_path = _load_upstream_payload(model_path, base_dir=viewer_json_path.parent)
                if upstream_payload:
                    upstream_axis_refs = _extract_named_axis_refs_from_object(upstream_payload, path_hint="model_path")
        explicit_named_axis_available = bool(upstream_axis_refs.get("x") or upstream_axis_refs.get("y"))
        if not explicit_named_axis_available:
            upstream_axis_refs = {"x": [], "y": [], "z": []}
        if explicit_named_axis_available:
            axis_ref_source_mode = "upstream_named_axis_refs"
            axis_ref_source_path = candidate_source_path
            axis_ref_note = str(
                interactive.get("axis_ref_note", "") or "Named axis/grid references were loaded from the upstream geometry/model payload and are rendered directly in the 3D workspace."
            ).strip()
    if not valid_geometry_available:
        axis_ref_source_mode = "no_valid_geometry"
        axis_ref_source_path = axis_ref_source_path or ""
        axis_ref_note = str(
            interactive.get("axis_ref_note", "")
            or "No valid coordinate rows were available; the workspace is showing an audit-visible no valid geometry state, and fallback origin coordinates remain shape-compatible only."
        ).strip()
        x_refs: list[dict[str, Any]] = []
        y_refs: list[dict[str, Any]] = []
        z_refs: list[dict[str, Any]] = []
    else:
        x_refs = upstream_axis_refs.get("x") or interactive_axis_refs.get("x") or _cluster_axis_refs(xs, prefix="X")
        y_refs = upstream_axis_refs.get("y") or interactive_axis_refs.get("y") or _cluster_axis_refs(ys, prefix="Y")
        z_refs = upstream_axis_refs.get("z") or interactive_axis_refs.get("z") or _build_story_refs(baseline_rows, after_rows) or _cluster_axis_refs(zs, prefix="Z", tolerance=0.35, limit=8)
    coordinate_contract_validation = _build_coordinate_contract_validation(
        baseline_rows_raw,
        baseline_rows,
        after_rows_raw,
        after_rows,
    )
    return {
        "mode": str(interactive.get("mode", "") or "interactive_canvas_xyz_structure"),
        "comparison_availability": str(interactive.get("comparison_availability", "") or "baseline_vs_changed"),
        "interactive_3d_payload_contract_version": INTERACTIVE_3D_PAYLOAD_CONTRACT_VERSION,
        "coordinate_contract_version": COORDINATE_CONTRACT_VERSION,
        "workspace_selection_contract_version": WORKSPACE_SELECTION_CONTRACT_VERSION,
        "workspace_diff_focus_contract_version": WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION,
        "workspace_selection_contract_features": dict(WORKSPACE_SELECTION_CONTRACT_FEATURES),
        "nullable_metric_fields": list(AFTER_SEGMENT_NULLABLE_METRIC_FIELDS),
        "evidence_field_names": list(AFTER_SEGMENT_EVIDENCE_FIELD_NAMES),
        "after_segment_contract_validation": _build_after_segment_contract_validation(after_rows_raw, after_rows),
        "coordinate_contract_validation": coordinate_contract_validation,
        "valid_geometry_available": valid_geometry_available,
        "no_valid_geometry": not valid_geometry_available,
        "geometry_status": "valid_geometry_available" if valid_geometry_available else "no_valid_geometry",
        "valid_point_count": len(all_points),
        "valid_segment_count": valid_segment_count,
        "invalid_excluded_count": invalid_excluded_count,
        "extent_source": "valid_coordinates" if valid_geometry_available else "no_valid_geometry",
        "extent_status": "valid_geometry_available" if valid_geometry_available else "no_valid_geometry",
        "baseline_segment_count": len(baseline_rows),
        "after_segment_count": len(after_rows),
        "baseline_segments": baseline_rows,
        "after_segments": after_rows,
        "extent": {
            "min_x": round(min(xs), 3),
            "max_x": round(max(xs), 3),
            "min_y": round(min(ys), 3),
            "max_y": round(max(ys), 3),
            "min_z": round(min(zs), 3),
            "max_z": round(max(zs), 3),
        },
        "axis_refs": {
            "x": x_refs,
            "y": y_refs,
            "z": z_refs,
        },
        "axis_ref_source_mode": axis_ref_source_mode,
        "axis_ref_source_path": axis_ref_source_path,
        "axis_ref_note": axis_ref_note,
        "baseline_category_label": str(interactive.get("baseline_category_label", "") or ""),
        "after_family_label": str(interactive.get("after_family_label", "") or ""),
        "story_slice_label": str(interactive.get("story_slice_label", "") or ""),
    }


def build_review_payload(
    viewer_payload: dict[str, Any],
    *,
    viewer_json_path: Path = DEFAULT_VIEWER_JSON,
    out_html_path: Path = DEFAULT_OUT_HTML,
) -> dict[str, Any]:
    case_context = viewer_payload.get("case_context") if isinstance(viewer_payload.get("case_context"), dict) else {}
    change_overview = viewer_payload.get("change_overview") if isinstance(viewer_payload.get("change_overview"), dict) else {}
    baseline_structure = viewer_payload.get("baseline_structure") if isinstance(viewer_payload.get("baseline_structure"), dict) else {}
    member_overlay = viewer_payload.get("member_overlay") if isinstance(viewer_payload.get("member_overlay"), dict) else {}
    artifact_links = viewer_payload.get("artifact_links") if isinstance(viewer_payload.get("artifact_links"), dict) else {}

    member_type_rows = [row for row in (change_overview.get("member_type_rows") or []) if isinstance(row, dict)]
    story_band_rows = [row for row in (change_overview.get("story_band_rows") or []) if isinstance(row, dict)]
    zone_rows = [row for row in (change_overview.get("zone_rows") or []) if isinstance(row, dict)]
    locator_rows = [row for row in (member_overlay.get("member_locator_rows") or []) if isinstance(row, dict)]

    changed_group_count = sum(_safe_int(row.get("changed_group_count", 0)) for row in member_type_rows)
    changed_member_count = _safe_int(member_overlay.get("changed_member_count", 0))
    total_element_count = _safe_int(baseline_structure.get("total_element_count", 0))
    signed_cost_proxy_delta_total = sum(_safe_float(row.get("cost_proxy_delta_sum", 0.0)) for row in member_type_rows)
    constructability_delta_total = sum(_safe_float(row.get("constructability_delta_sum", 0.0)) for row in member_type_rows)
    max_dcr_after = max((_safe_float(row.get("max_dcr_after_max", 0.0)) for row in member_type_rows), default=0.0)
    out_dir = out_html_path.parent
    viewer_dir = viewer_json_path.parent
    full_viewer_href = _rel_href(Path(viewer_dir) / "structural_optimization_viewer.html", base_dir=out_dir)
    full_viewer_core_href = f"{full_viewer_href}?view=core" if full_viewer_href else ""
    artifact_source_base_dir = viewer_json_path.parent.parent
    committee_dashboard_href = _rel_href(
        artifact_links.get("committee_dashboard_html", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    analysis_gallery_href = _rel_href(
        artifact_links.get("analysis_gallery_onepage_html", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    project_registry_href = _rel_href(
        artifact_links.get("project_registry_report", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    project_package_href = _rel_href(
        artifact_links.get("project_package_zip", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    project_registry_signature_href = _rel_href(
        artifact_links.get("project_registry_signature", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    batch_job_report_href = _rel_href(
        artifact_links.get("external_benchmark_batch_job_report_json", ""),
        base_dir=out_dir,
        source_base_dir=artifact_source_base_dir,
    )
    mgt_export_report_payload, mgt_export_report_path = _load_mgt_export_report(
        viewer_json_path=viewer_json_path,
        case_context=case_context,
        artifact_links=artifact_links,
    )
    midas_roundtrip_gate_payload, midas_roundtrip_gate_path = _load_midas_native_roundtrip_gate_report(
        viewer_json_path=viewer_json_path,
        case_context=case_context,
        artifact_links=artifact_links,
    )
    mgt_export_summary = (
        mgt_export_report_payload.get("summary")
        if isinstance(mgt_export_report_payload.get("summary"), dict)
        else {}
    )
    midas_roundtrip_gate_summary = (
        midas_roundtrip_gate_payload.get("summary")
        if isinstance(midas_roundtrip_gate_payload.get("summary"), dict)
        else {}
    )
    mgt_export_artifacts = (
        mgt_export_report_payload.get("artifacts")
        if isinstance(mgt_export_report_payload.get("artifacts"), dict)
        else {}
    )
    mgt_source_mgt_path = str(mgt_export_artifacts.get("source_mgt", "") or "").strip()
    mgt_output_mgt_path = str(mgt_export_artifacts.get("output_mgt", "") or "").strip()
    mgt_loadcomb_preview_path = str(mgt_export_artifacts.get("loadcomb_preview_mgt", "") or "").strip()
    mgt_loadcomb_roundtrip_report_path = str(mgt_export_artifacts.get("loadcomb_roundtrip_report_json", "") or "").strip()
    mgt_source_output_diff_json_path = str(mgt_export_artifacts.get("source_output_mgt_diff_json", "") or "").strip()
    mgt_source_output_diff_preview_path = str(mgt_export_artifacts.get("source_output_mgt_diff_preview_txt", "") or "").strip()
    mgt_source_output_diff_window_json_path = str(
        mgt_export_artifacts.get("source_output_mgt_diff_window_json", "") or ""
    ).strip()
    mgt_source_output_diff_window_preview_path = str(
        mgt_export_artifacts.get("source_output_mgt_diff_window_preview_txt", "") or ""
    ).strip()
    mgt_export_report_href = _rel_href(mgt_export_report_path, base_dir=out_dir)
    mgt_source_mgt_href = _rel_href(mgt_source_mgt_path, base_dir=out_dir)
    mgt_output_mgt_href = _rel_href(mgt_output_mgt_path, base_dir=out_dir)
    mgt_loadcomb_preview_href = _rel_href(mgt_loadcomb_preview_path, base_dir=out_dir)
    mgt_loadcomb_roundtrip_report_href = _rel_href(mgt_loadcomb_roundtrip_report_path, base_dir=out_dir)
    mgt_source_output_diff_json_href = _rel_href(mgt_source_output_diff_json_path, base_dir=out_dir)
    mgt_source_output_diff_preview_href = _rel_href(mgt_source_output_diff_preview_path, base_dir=out_dir)
    mgt_source_output_diff_window_json_href = _rel_href(mgt_source_output_diff_window_json_path, base_dir=out_dir)
    mgt_source_output_diff_window_preview_href = _rel_href(
        mgt_source_output_diff_window_preview_path,
        base_dir=out_dir,
    )
    mgt_source_output_diff_preview_text = _load_text_excerpt(
        mgt_source_output_diff_preview_path,
        base_dir=viewer_json_path.parent,
    )
    mgt_source_output_diff_window_preview_text = _load_text_excerpt(
        mgt_source_output_diff_window_preview_path,
        base_dir=viewer_json_path.parent,
    )
    mgt_compare_window_payload: dict[str, Any] = {}
    if mgt_source_output_diff_window_json_path:
        mgt_compare_window_payload, _ = _load_upstream_payload(
            mgt_source_output_diff_window_json_path,
            base_dir=viewer_json_path.parent,
        )
    mgt_compare_window_rows = [
        row for row in (mgt_export_summary.get("source_vs_output_diff_window_rows") or []) if isinstance(row, dict)
    ]
    if not mgt_compare_window_rows:
        mgt_compare_window_rows = [
            row
            for row in (
                mgt_compare_window_payload.get("window_rows")
                or mgt_compare_window_payload.get("rows")
                or mgt_compare_window_payload.get("sample_rows")
                or []
            )
            if isinstance(row, dict)
        ]
    mgt_compare_window_member_row_indices = {
        str(key): [int(value) for value in values]
        for key, values in (
            mgt_compare_window_payload.get("member_row_indices")
            or mgt_export_summary.get("source_output_mgt_diff_window_member_row_indices")
            or {}
        ).items()
        if str(key).strip()
    }
    compare_window_summary_line = str(
        mgt_compare_window_payload.get("summary_line", "") or mgt_export_summary.get("source_vs_output_diff_summary_line", "") or ""
    )
    compare_window_preview_text = mgt_source_output_diff_window_preview_text or mgt_source_output_diff_preview_text
    if not mgt_compare_window_rows and mgt_source_mgt_path and mgt_output_mgt_path:
        compare_window_artifacts = _build_compare_window_artifacts(
            mgt_source_mgt_path,
            mgt_output_mgt_path,
            base_dir=viewer_json_path.parent,
        )
        mgt_compare_window_rows = [
            row for row in (compare_window_artifacts.get("rows") or []) if isinstance(row, dict)
        ]
        compare_window_summary_line = str(compare_window_artifacts.get("summary_line", "") or compare_window_summary_line)
        compare_window_preview_text = str(compare_window_artifacts.get("preview_text", "") or compare_window_preview_text)
    mgt_compare_window_row_count = len(mgt_compare_window_rows)
    mgt_compare_window_available = bool(mgt_compare_window_rows)
    if not compare_window_summary_line and mgt_compare_window_available:
        compare_window_summary_line = (
            f"compare_window: rows={mgt_compare_window_row_count} | "
            f"source_lines={mgt_export_summary.get('source_vs_output_source_line_count', 0)} | "
            f"output_lines={mgt_export_summary.get('source_vs_output_output_line_count', 0)}"
        )

    top_story_band_rows = sorted(
        story_band_rows,
        key=lambda row: abs(_safe_float(row.get("cost_proxy_delta_sum", 0.0))),
        reverse=True,
    )[:12]
    top_zone_rows = sorted(
        zone_rows,
        key=lambda row: abs(_safe_float(row.get("cost_proxy_delta_sum", 0.0))),
        reverse=True,
    )
    top_members = _dedupe_top_members(locator_rows, limit=24)
    for row in top_members:
        member_id = str(row.get("member_id", "") or "").strip()
        row["viewer_focus_href"] = _href_with_params(
            full_viewer_core_href or full_viewer_href,
            view="core",
            focus="interactive3d",
            focus_member=member_id,
            member_id=member_id,
            case_id=member_id,
            baseline_secondary="elevation",
        )
    projection_assets = _write_projection_assets(
        viewer_payload,
        viewer_json_path=viewer_json_path,
        out_html_path=out_html_path,
    )
    interactive_3d_payload = _build_3d_payload(viewer_payload, viewer_json_path=viewer_json_path)
    top_story_band_rows = _annotate_story_band_rows(top_story_band_rows, interactive_3d_payload)
    after_segments_by_member_id = {
        str(row.get("member_id", "") or "").strip(): row
        for row in (interactive_3d_payload.get("after_segments") or [])
        if isinstance(row, dict) and str(row.get("member_id", "") or "").strip()
    }
    member_selection_base_href = full_viewer_core_href or full_viewer_href
    for row in top_members:
        member_id = str(row.get("member_id", "") or "").strip()
        row.update(
            _representative_member_export_fields(
                row,
                base_href=member_selection_base_href,
                after_segment=after_segments_by_member_id.get(member_id),
            )
        )
    representative_evidence_completeness_summary = _representative_evidence_completeness_summary(top_members)
    projection_rows = [
        {
            "projection_key": key,
            "projection_label": label,
            "projection_note": note,
            **projection_assets[key],
        }
        for key, label, note in PROJECTIONS
    ]

    return {
        "schema_version": "optimized_drawing_review.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_viewer_json": str(viewer_json_path),
        "case_id": str(case_context.get("case_id", "") or "optimized_drawing_review"),
        "case_title": str(case_context.get("case_title", "") or "Optimized Drawing Review"),
        "case_note": str(case_context.get("case_note", "") or ""),
        "status_label": str(case_context.get("status_label", "") or ""),
        "expert_review_metadata": _resolve_expert_review_metadata(case_context),
        "expert_review_metadata_template": _resolve_expert_review_metadata_template(case_context),
        "changed_group_count": changed_group_count,
        "changed_member_count": changed_member_count,
        "total_element_count": total_element_count,
        "signed_cost_proxy_delta_total": round(signed_cost_proxy_delta_total, 3),
        "constructability_delta_total": round(constructability_delta_total, 3),
        "max_dcr_after_max": round(max_dcr_after, 3),
        "member_type_rows": member_type_rows,
        "story_band_rows": top_story_band_rows,
        "zone_rows": top_zone_rows,
        "top_members": top_members,
        "representative_evidence_completeness_summary": representative_evidence_completeness_summary,
        "projection_rows": projection_rows,
        "interactive_3d_payload": interactive_3d_payload,
        "precision_mode": str(interactive_3d_payload.get("mode", "") or "interactive_canvas_xyz_structure"),
        "viewer_html_href": full_viewer_href,
        "viewer_core_href": full_viewer_core_href,
        "committee_dashboard_href": committee_dashboard_href,
        "analysis_gallery_href": analysis_gallery_href,
        "project_registry_href": project_registry_href,
        "project_package_href": project_package_href,
        "project_registry_signature_href": project_registry_signature_href,
        "batch_job_report_href": batch_job_report_href,
        "mgt_export_report_href": mgt_export_report_href,
        "mgt_source_mgt_href": mgt_source_mgt_href,
        "mgt_output_mgt_href": mgt_output_mgt_href,
        "mgt_loadcomb_preview_href": mgt_loadcomb_preview_href,
        "mgt_loadcomb_roundtrip_report_href": mgt_loadcomb_roundtrip_report_href,
        "mgt_source_output_diff_json_href": mgt_source_output_diff_json_href,
        "mgt_source_output_diff_preview_href": mgt_source_output_diff_preview_href,
        "mgt_source_output_diff_window_json_href": mgt_source_output_diff_window_json_href,
        "mgt_source_output_diff_window_preview_href": mgt_source_output_diff_window_preview_href,
        "mgt_compare_window_json_href": mgt_source_output_diff_window_json_href,
        "mgt_compare_window_txt_href": mgt_source_output_diff_window_preview_href,
        "mgt_compare_window_summary_line": compare_window_summary_line,
        "mgt_compare_window_row_count": mgt_compare_window_row_count,
        "mgt_compare_window_available": mgt_compare_window_available,
        "mgt_compare_window_preview_text": compare_window_preview_text,
        "mgt_compare_window_rows": mgt_compare_window_rows,
        "mgt_compare_window_member_row_indices": mgt_compare_window_member_row_indices,
        "mgt_export_contract_pass": bool(mgt_export_report_payload.get("contract_pass", False)),
        "mgt_export_reason_code": str(mgt_export_report_payload.get("reason_code", "") or ""),
        "mgt_export_reason": str(mgt_export_report_payload.get("reason", "") or ""),
        "mgt_export_support_mode": str(mgt_export_summary.get("support_mode", "") or ""),
        "mgt_export_delivery_boundary": str(mgt_export_summary.get("mgt_export_delivery_boundary", "") or ""),
        "mgt_export_output_mgt_exists": bool(mgt_export_summary.get("output_mgt_exists", False)),
        "mgt_export_loadcomb_roundtrip_pass": bool(mgt_export_summary.get("loadcomb_roundtrip_pass", False)),
        "mgt_export_loadcomb_roundtrip_summary_line": str(
            mgt_export_summary.get("loadcomb_roundtrip_summary_line", "") or ""
        ),
        "mgt_export_source_output_mgt_diff_available": bool(
            mgt_export_summary.get("source_output_mgt_diff_available", False)
        ),
        "mgt_export_source_output_mgt_summary_line": str(
            mgt_export_summary.get("source_output_mgt_summary_line", "")
            or mgt_export_summary.get("source_vs_output_diff_summary_line", "")
            or ""
        ),
        "mgt_export_source_output_mgt_source_meaningful_line_count": _safe_int(
            mgt_export_summary.get(
                "source_output_mgt_source_meaningful_line_count",
                mgt_export_summary.get("source_vs_output_source_line_count", 0),
            )
        ),
        "mgt_export_source_output_mgt_output_meaningful_line_count": _safe_int(
            mgt_export_summary.get(
                "source_output_mgt_output_meaningful_line_count",
                mgt_export_summary.get("source_vs_output_output_line_count", 0),
            )
        ),
        "mgt_export_source_output_mgt_changed_line_count": _safe_int(
            mgt_export_summary.get(
                "source_output_mgt_changed_line_count",
                mgt_export_summary.get("source_vs_output_diff_changed_line_count", 0),
            )
        ),
        "mgt_export_source_output_mgt_added_line_count": _safe_int(
            mgt_export_summary.get(
                "source_output_mgt_added_line_count",
                mgt_export_summary.get("source_vs_output_diff_added_line_count", 0),
            )
        ),
        "mgt_export_source_output_mgt_removed_line_count": _safe_int(
            mgt_export_summary.get(
                "source_output_mgt_removed_line_count",
                mgt_export_summary.get("source_vs_output_diff_removed_line_count", 0),
            )
        ),
        "mgt_export_source_output_mgt_total_delta_count": _safe_int(
            mgt_export_summary.get("source_output_mgt_total_delta_count", 0)
        ),
        "mgt_export_source_output_mgt_diff_sample_lines": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_sample_lines") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_search_tokens": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_search_tokens") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_member_ids": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_member_ids") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_section_ids": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_section_ids") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_member_row_indices": {
            str(key): [int(value) for value in values]
            for key, values in (mgt_export_summary.get("source_output_mgt_diff_member_row_indices") or {}).items()
            if str(key).strip()
        },
        "mgt_export_source_output_mgt_diff_json_exists": bool(
            mgt_export_summary.get("source_output_mgt_diff_json_exists", False)
        ),
        "mgt_export_source_output_mgt_diff_preview_exists": bool(
            mgt_export_summary.get("source_output_mgt_diff_preview_exists", False)
        ),
        "mgt_export_source_output_mgt_diff_window_json_exists": bool(
            mgt_export_summary.get("source_output_mgt_diff_window_json_exists", False)
        ),
        "mgt_export_source_output_mgt_diff_window_preview_exists": bool(
            mgt_export_summary.get("source_output_mgt_diff_window_preview_exists", False)
        ),
        "mgt_export_source_output_mgt_verification_receipt_line": str(
            mgt_export_summary.get("source_output_mgt_verification_receipt_line", "") or ""
        ),
        "mgt_export_source_output_mgt_diff_preview_text": mgt_source_output_diff_preview_text,
        "mgt_export_source_output_mgt_diff_window_preview_text": mgt_source_output_diff_window_preview_text,
        "mgt_export_source_output_mgt_diff_sample_rows": [
            row
            for row in (mgt_export_summary.get("source_vs_output_diff_sample_rows") or [])
            if isinstance(row, dict)
        ],
        "mgt_export_source_output_mgt_diff_window_search_tokens": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_window_search_tokens") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_window_member_ids": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_window_member_ids") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_window_section_ids": [
            str(value)
            for value in (mgt_export_summary.get("source_output_mgt_diff_window_section_ids") or [])
            if str(value).strip()
        ],
        "mgt_export_source_output_mgt_diff_window_member_row_indices": {
            str(key): [int(value) for value in values]
            for key, values in (mgt_export_summary.get("source_output_mgt_diff_window_member_row_indices") or {}).items()
            if str(key).strip()
        },
        "mgt_export_source_vs_output_diff_summary_line": str(
            mgt_export_summary.get("source_vs_output_diff_summary_line", "") or ""
        ),
        "mgt_export_source_vs_output_diff_changed_line_count": _safe_int(
            mgt_export_summary.get("source_vs_output_diff_changed_line_count", 0)
        ),
        "mgt_export_source_vs_output_diff_added_line_count": _safe_int(
            mgt_export_summary.get("source_vs_output_diff_added_line_count", 0)
        ),
        "mgt_export_source_vs_output_diff_removed_line_count": _safe_int(
            mgt_export_summary.get("source_vs_output_diff_removed_line_count", 0)
        ),
        "mgt_export_source_vs_output_diff_sample_count": _safe_int(
            mgt_export_summary.get("source_vs_output_diff_sample_count", 0)
        ),
        "mgt_export_source_vs_output_diff_sample_rows": [
            row
            for row in (mgt_export_summary.get("source_vs_output_diff_sample_rows") or [])
            if isinstance(row, dict)
        ],
        "mgt_export_source_vs_output_diff_window_rows": [
            row
            for row in (mgt_export_summary.get("source_vs_output_diff_window_rows") or [])
            if isinstance(row, dict)
        ],
        "mgt_export_source_vs_output_diff_window_count": _safe_int(
            mgt_export_summary.get("source_vs_output_diff_window_count", 0)
        ),
        "mgt_export_source_vs_output_source_line_count": _safe_int(
            mgt_export_summary.get("source_vs_output_source_line_count", 0)
        ),
        "mgt_export_source_vs_output_output_line_count": _safe_int(
            mgt_export_summary.get("source_vs_output_output_line_count", 0)
        ),
        "mgt_export_native_authoring_summary_line": str(
            mgt_export_summary.get("native_authoring_summary_line", "") or ""
        ),
        "mgt_export_total_change_count": _safe_int(mgt_export_summary.get("total_change_count", 0)),
        "mgt_export_supported_change_count": _safe_int(mgt_export_summary.get("supported_change_count", 0)),
        "mgt_export_supported_change_ratio": _safe_float(mgt_export_summary.get("supported_change_ratio", 0.0)),
        "mgt_export_direct_patch_change_count": _safe_int(mgt_export_summary.get("direct_patch_change_count", 0)),
        "mgt_export_direct_patch_change_ratio": _safe_float(mgt_export_summary.get("direct_patch_change_ratio", 0.0)),
        "mgt_export_patched_supported_change_count": _safe_int(mgt_export_summary.get("patched_supported_change_count", 0)),
        "mgt_export_instruction_sidecar_change_count": _safe_int(
            mgt_export_summary.get("instruction_sidecar_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_change_ratio": _safe_float(
            mgt_export_summary.get("instruction_sidecar_change_ratio", 0.0)
        ),
        "mgt_export_instruction_sidecar_zero_touch_verified_change_count": _safe_int(
            mgt_export_summary.get("instruction_sidecar_zero_touch_verified_change_count", 0)
        ),
        "mgt_export_instruction_sidecar_zero_touch_verified_change_ratio": _safe_float(
            mgt_export_summary.get("instruction_sidecar_zero_touch_verified_change_ratio", 0.0)
        ),
        "mgt_export_unsupported_change_count": _safe_int(mgt_export_summary.get("unsupported_change_count", 0)),
        "mgt_export_unsupported_change_ratio": _safe_float(mgt_export_summary.get("unsupported_change_ratio", 0.0)),
        "mgt_export_loadcomb_combo_count": _safe_int(mgt_export_summary.get("loadcomb_combo_count", 0)),
        "mgt_export_audit_review_queue_item_count": _safe_int(mgt_export_summary.get("audit_review_queue_item_count", 0)),
        "mgt_export_audit_review_queue_pending_count": _safe_int(mgt_export_summary.get("audit_review_queue_pending_count", 0)),
        "mgt_export_diff_summary_line": str(mgt_export_summary.get("diff_summary_line", "") or ""),
        "mgt_export_diff_rows": [
            row
            for row in (mgt_export_summary.get("diff_rows") or [])
            if isinstance(row, dict)
        ],
        "midas_roundtrip_gate_report_href": _rel_href(midas_roundtrip_gate_path, base_dir=out_dir),
        "midas_roundtrip_gate_contract_pass": bool(midas_roundtrip_gate_payload.get("contract_pass", False)),
        "midas_roundtrip_gate_reason_code": str(midas_roundtrip_gate_payload.get("reason_code", "") or ""),
        "midas_roundtrip_gate_summary_line": str(midas_roundtrip_gate_payload.get("summary_line", "") or ""),
        "midas_roundtrip_gate_ready_count": _safe_int(midas_roundtrip_gate_summary.get("native_writeback_ready_count", 0)),
        "midas_roundtrip_gate_corpus_case_count": _safe_int(midas_roundtrip_gate_summary.get("corpus_case_count", 0)),
        "midas_roundtrip_gate_public_native_ready_count": _safe_int(
            midas_roundtrip_gate_summary.get("public_native_writeback_ready_count", 0)
        ),
        "midas_roundtrip_gate_public_source_ready_count": _safe_int(
            midas_roundtrip_gate_summary.get("public_source_writeback_ready_count", 0)
        ),
        "midas_roundtrip_gate_public_structural_preview_ready_count": _safe_int(
            midas_roundtrip_gate_summary.get("public_archive_structural_preview_writeback_ready_count", 0)
        ),
        "midas_roundtrip_gate_pending_review_total": _safe_int(
            midas_roundtrip_gate_summary.get("pending_review_total", 0)
        ),
        "midas_roundtrip_gate_loadcomb_exact_case_count": _safe_int(
            midas_roundtrip_gate_summary.get("loadcomb_exact_case_count", 0)
        ),
        "midas_roundtrip_gate_taxonomy_exact_count": _safe_int(
            (midas_roundtrip_gate_summary.get("taxonomy_case_counts") or {}).get("preserved_exact", 0)
        ),
        "midas_roundtrip_gate_taxonomy_canonical_count": _safe_int(
            (midas_roundtrip_gate_summary.get("taxonomy_case_counts") or {}).get("canonical_rewrite", 0)
        ),
        "mgt_export_special_member_supported_action_family_label": str(
            mgt_export_summary.get("special_member_supported_action_family_label", "") or ""
        ),
        "mgt_export_special_member_direct_patch_action_family_label": str(
            mgt_export_summary.get("special_member_direct_patch_action_family_label", "") or ""
        ),
        "mgt_export_special_member_zero_touch_verified_action_family_label": str(
            mgt_export_summary.get("special_member_zero_touch_verified_action_family_label", "") or ""
        ),
    }


def _real_drawing_corpus_view(payload: dict[str, Any]) -> dict[str, Any]:
    corpus = payload.get("real_drawing_private_corpus") if isinstance(payload.get("real_drawing_private_corpus"), dict) else {}
    summary = corpus.get("summary") if isinstance(corpus.get("summary"), dict) else {}
    policy = corpus.get("policy") if isinstance(corpus.get("policy"), dict) else {}
    ready_count = _safe_int(summary.get("optimized_drawing_generation_ready_count", summary.get("ready_asset_count", 0)))
    candidate_count = _safe_int(summary.get("candidate_file_count", summary.get("model_optimization_candidate_count", 0)))
    if candidate_count <= 0:
        candidate_count = ready_count
    ready_model_asset_count = _safe_int(summary.get("ready_model_asset_count", summary.get("model_asset_count", 0)))
    solver_exact_ready_count = _safe_int(summary.get("solver_exact_ready_count", 0))
    proxy_or_preview_ready_count = _safe_int(summary.get("proxy_or_preview_ready_count", 0))
    drawing_sheet_candidate_count = _safe_int(summary.get("drawing_sheet_candidate_count", 0))
    project_count = _safe_int(summary.get("project_count", 0))
    release_surface_allowed_count = _safe_int(policy.get("release_surface_allowed_count", 0))
    raw_redistribution_allowed_count = _safe_int(policy.get("raw_redistribution_allowed_count", 0))
    surface_safe = bool(policy.get("surface_safe", False))
    metadata_only = surface_safe and release_surface_allowed_count == 0 and raw_redistribution_allowed_count == 0
    return {
        "available": bool(corpus.get("available", False)),
        "registered": bool(corpus.get("registered", False)) and ready_count > 0,
        "summary_line": str(corpus.get("summary_line", "") or ""),
        "ready_count": ready_count,
        "candidate_count": candidate_count,
        "ready_model_asset_count": ready_model_asset_count,
        "solver_exact_ready_count": solver_exact_ready_count,
        "proxy_or_preview_ready_count": proxy_or_preview_ready_count,
        "drawing_sheet_candidate_count": drawing_sheet_candidate_count,
        "project_count": project_count,
        "release_surface_allowed_count": release_surface_allowed_count,
        "raw_redistribution_allowed_count": raw_redistribution_allowed_count,
        "metadata_only": metadata_only,
        "surface_label": "metadata-only" if metadata_only else "review required",
    }


def render_review_html(payload: dict[str, Any]) -> str:
    case_id = html.escape(str(payload.get("case_id", "") or "optimized_drawing_review"))
    case_title = html.escape(str(payload.get("case_title", "") or "Optimized Drawing Review"))
    case_note = html.escape(str(payload.get("case_note", "") or ""))
    status_label = html.escape(str(payload.get("status_label", "") or ""))
    precision_mode = html.escape(str(payload.get("precision_mode", "") or "interactive_canvas_xyz_structure"))
    member_type_rows = [row for row in (payload.get("member_type_rows") or []) if isinstance(row, dict)]
    story_rows = [row for row in (payload.get("story_band_rows") or []) if isinstance(row, dict)]
    zone_rows = [row for row in (payload.get("zone_rows") or []) if isinstance(row, dict)]
    top_members = [row for row in (payload.get("top_members") or []) if isinstance(row, dict)]
    projection_rows = [row for row in (payload.get("projection_rows") or []) if isinstance(row, dict)]
    real_drawing_corpus = _real_drawing_corpus_view(payload)
    interactive_3d_payload = payload.get("interactive_3d_payload") if isinstance(payload.get("interactive_3d_payload"), dict) else {}
    baseline_segment_count = int(interactive_3d_payload.get("baseline_segment_count", 0) or 0)
    after_segment_count = int(interactive_3d_payload.get("after_segment_count", 0) or 0)
    valid_geometry_available = bool(interactive_3d_payload.get("valid_geometry_available", True))
    valid_segment_count = _safe_int(interactive_3d_payload.get("valid_segment_count", 0))
    invalid_excluded_count = _safe_int(interactive_3d_payload.get("invalid_excluded_count", 0))
    changed_member_count = int(payload.get("changed_member_count", 0) or 0)
    interactive_3d_json = json.dumps(interactive_3d_payload, ensure_ascii=False).replace("<", "\\u003c")
    workspace_selection_contract_version_json = json.dumps(WORKSPACE_SELECTION_CONTRACT_VERSION)
    workspace_diff_focus_contract_version_json = json.dumps(WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION)
    axis_refs = interactive_3d_payload.get("axis_refs") if isinstance(interactive_3d_payload.get("axis_refs"), dict) else {}
    x_axis_refs = [row for row in (axis_refs.get("x") or []) if isinstance(row, dict)]
    y_axis_refs = [row for row in (axis_refs.get("y") or []) if isinstance(row, dict)]
    z_axis_refs = [row for row in (axis_refs.get("z") or []) if isinstance(row, dict)]
    axis_ref_note = html.escape(str(interactive_3d_payload.get("axis_ref_note", "") or ""))
    axis_ref_source_mode = html.escape(str(interactive_3d_payload.get("axis_ref_source_mode", "") or "geometry_derived_axis_refs"))
    axis_ref_source_path = html.escape(str(interactive_3d_payload.get("axis_ref_source_path", "") or ""))
    axis_ref_label = " | ".join(
        filter(
            None,
            [
                " ".join(f"{html.escape(str(row.get('label', '') or ''))}={_safe_float(row.get('value', 0.0)):.1f}" for row in x_axis_refs[:4]),
                " ".join(f"{html.escape(str(row.get('label', '') or ''))}={_safe_float(row.get('value', 0.0)):.1f}" for row in y_axis_refs[:4]),
                " ".join(f"{html.escape(str(row.get('label', '') or ''))}={_safe_float(row.get('value', 0.0)):.1f}" for row in z_axis_refs[:4]),
            ],
        )
    )

    member_type_cards = "\n".join(
        (
            f"<article class='mini-card'>"
            f"<div class='mini-card-label'>{html.escape(str(row.get('label', '') or 'n/a'))}</div>"
            f"<div class='mini-card-value'>{_safe_int(row.get('changed_group_count', 0))} groups</div>"
            f"<div class='mini-card-note'>cost { _safe_float(row.get('cost_proxy_delta_sum', 0.0)):.3f} | "
            f"max DCR { _safe_float(row.get('max_dcr_after_max', 0.0)):.3f}</div>"
            f"</article>"
        )
        for row in member_type_rows
    )
    zone_chips = " ".join(
        f"<span class='zone-chip'>{html.escape(str(row.get('label', '') or 'n/a'))}: "
        f"{_safe_int(row.get('changed_group_count', 0))} groups</span>"
        for row in zone_rows
    )
    story_rows_count = len(story_rows)
    story_rows_total = story_rows_count or 1
    story_rows_total_groups = sum(_safe_int(row.get("changed_group_count", 0)) for row in story_rows) or 1
    story_rows_ranked = list(enumerate(story_rows, start=1))
    story_strip_rows = story_rows_ranked[:5]
    story_mini_strip_html = "\n".join(
        (
            "<article class='story-mini-chip "
            f"{'is-primary' if rank == 1 else 'is-secondary' if rank == 2 else 'is-tertiary' if rank == 3 else 'is-neutral'}' "
            f"data-story-chip='true' "
            f"data-story-band='{html.escape(str(row.get('story_band', '') or ''))}' "
            f"data-story-band-key='{html.escape(str(row.get('story_band', '') or '').strip().lower())}' "
            f"data-story-rank='{rank}' "
            f"data-story-slot='Elevation slot {rank} / {story_rows_total}' "
            "role='button' "
            "tabindex='0' "
            f"title='Hover to preview this story band in 3D. Click to center-fit the 3D view and commit selection.'>"
            "<div class='story-mini-chip-head'>"
            f"<div class='story-mini-chip-story'>{html.escape(str(row.get('story_band', '') or 'n/a'))}</div>"
            f"<div class='story-mini-chip-slot'>Elevation slot {rank} / {story_rows_total}</div>"
            "</div>"
            f"<div class='story-mini-chip-line'>{html.escape(str(row.get('zone_label', '') or 'n/a'))} · {html.escape(str(row.get('member_type', '') or 'n/a'))}</div>"
            "<div class='story-mini-chip-track'>"
            f"<div class='story-mini-chip-track-fill' style='width:{max(10, int(round((_safe_int(row.get('changed_group_count', 0)) / story_rows_total_groups) * 100))) }%;'></div>"
            "</div>"
            f"<div class='story-mini-chip-count'>{_safe_int(row.get('changed_group_count', 0))} groups</div>"
            f"<div class='story-mini-chip-emphasis'>cost {_safe_float(row.get('cost_proxy_delta_sum', 0.0)):.3f} | constructability {_safe_float(row.get('constructability_delta_sum', 0.0)):.3f} | max DCR {_safe_float(row.get('max_dcr_after_max', 0.0)):.3f}</div>"
            f"<div class='story-mini-chip-share'>{max(1, int(round((_safe_int(row.get('changed_group_count', 0)) / story_rows_total_groups) * 100)))}% of story-band changes</div>"
            "</article>"
        )
        for rank, row in story_strip_rows
    ) or "<div class='story-mini-empty'>No story-band priorities were provided in this case.</div>"
    story_rows_html = "\n".join(
        (
            "<tr class='story-band-row' "
            "data-story-band-row='true' "
            f"data-story='{html.escape(str(row.get('story_band', '') or ''))}' "
            f"data-story-band='{html.escape(str(row.get('story_band', '') or ''))}' "
            f"data-story-band-key='{html.escape(str(row.get('story_band', '') or '').strip().lower())}' "
            f"data-member-type='{html.escape(str(row.get('member_type', '') or ''))}' "
            f"data-zone='{html.escape(str(row.get('zone_label', '') or ''))}' "
            f"data-story-rank='{rank}' "
            f"data-story-slot='Elevation slot {rank} / {story_rows_total}' "
            "role='button' tabindex='0' aria-selected='false'>"
            f"<td data-label='Elevation slot'><span class='story-slot-pill'>Elevation slot {rank} / {story_rows_total}</span></td>"
            f"<td data-label='Story'>{html.escape(str(row.get('story_band', '') or 'n/a'))}</td>"
            f"<td data-label='Zone'>{html.escape(str(row.get('zone_label', '') or 'n/a'))}</td>"
            f"<td data-label='Member'>{html.escape(str(row.get('member_type', '') or 'n/a'))}</td>"
            f"<td data-label='Groups'>{_safe_int(row.get('changed_group_count', 0))}</td>"
            f"<td data-label='Cost delta'>{_safe_float(row.get('cost_proxy_delta_sum', 0.0)):.3f}</td>"
            f"<td data-label='Constructability'>{_safe_float(row.get('constructability_delta_sum', 0.0)):.3f}</td>"
            f"<td data-label='Max DCR after'>{_safe_float(row.get('max_dcr_after_max', 0.0)):.3f}</td>"
            "</tr>"
        )
        for rank, row in story_rows_ranked
    )
    top_member_rows_html = "\n".join(_render_top_member_row(row) for row in top_members)
    viewer_core_href = html.escape(str(payload.get("viewer_core_href", "") or ""))
    viewer_html_href = html.escape(str(payload.get("viewer_html_href", "") or ""))
    expert_review_href = html.escape(str(payload.get("expert_review_href", "") or ""))
    committee_dashboard_href = html.escape(str(payload.get("committee_dashboard_href", "") or ""))
    analysis_gallery_href = html.escape(str(payload.get("analysis_gallery_href", "") or ""))
    project_registry_href = html.escape(str(payload.get("project_registry_href", "") or ""))
    project_package_href = html.escape(str(payload.get("project_package_href", "") or ""))
    batch_job_report_href = html.escape(str(payload.get("batch_job_report_href", "") or ""))
    mgt_export_report_href = html.escape(str(payload.get("mgt_export_report_href", "") or ""))
    mgt_source_mgt_href = html.escape(str(payload.get("mgt_source_mgt_href", "") or ""))
    mgt_output_mgt_href = html.escape(str(payload.get("mgt_output_mgt_href", "") or ""))
    mgt_loadcomb_preview_href = html.escape(str(payload.get("mgt_loadcomb_preview_href", "") or ""))
    mgt_loadcomb_roundtrip_report_href = html.escape(str(payload.get("mgt_loadcomb_roundtrip_report_href", "") or ""))
    mgt_source_output_diff_json_href = html.escape(str(payload.get("mgt_source_output_diff_json_href", "") or ""))
    mgt_source_output_diff_preview_href = html.escape(str(payload.get("mgt_source_output_diff_preview_href", "") or ""))
    mgt_source_output_diff_window_json_href = html.escape(
        str(payload.get("mgt_source_output_diff_window_json_href", "") or "")
    )
    mgt_source_output_diff_window_preview_href = html.escape(
        str(payload.get("mgt_source_output_diff_window_preview_href", "") or "")
    )
    mgt_export_contract_pass = bool(payload.get("mgt_export_contract_pass", False))
    mgt_export_support_mode = html.escape(str(payload.get("mgt_export_support_mode", "") or "n/a"))
    mgt_export_reason = html.escape(str(payload.get("mgt_export_reason", "") or ""))
    mgt_export_reason_code = html.escape(str(payload.get("mgt_export_reason_code", "") or ""))
    mgt_export_delivery_boundary = html.escape(str(payload.get("mgt_export_delivery_boundary", "") or "n/a"))
    mgt_export_output_mgt_exists = bool(payload.get("mgt_export_output_mgt_exists", False))
    mgt_export_loadcomb_roundtrip_pass = bool(payload.get("mgt_export_loadcomb_roundtrip_pass", False))
    mgt_export_loadcomb_roundtrip_summary_line = html.escape(
        str(payload.get("mgt_export_loadcomb_roundtrip_summary_line", "") or "n/a")
    )
    mgt_export_source_output_mgt_diff_available = bool(
        payload.get("mgt_export_source_output_mgt_diff_available", False)
    )
    mgt_export_source_output_mgt_summary_line = html.escape(
        str(payload.get("mgt_export_source_output_mgt_summary_line", "") or "n/a")
    )
    mgt_export_source_output_mgt_source_meaningful_line_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_source_meaningful_line_count", 0)
    )
    mgt_export_source_output_mgt_output_meaningful_line_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_output_meaningful_line_count", 0)
    )
    mgt_export_source_output_mgt_changed_line_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_changed_line_count", 0)
    )
    mgt_export_source_output_mgt_added_line_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_added_line_count", 0)
    )
    mgt_export_source_output_mgt_removed_line_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_removed_line_count", 0)
    )
    mgt_export_source_output_mgt_total_delta_count = _safe_int(
        payload.get("mgt_export_source_output_mgt_total_delta_count", 0)
    )
    mgt_export_source_output_mgt_diff_json_exists = bool(
        payload.get("mgt_export_source_output_mgt_diff_json_exists", False)
    )
    mgt_export_source_output_mgt_diff_preview_exists = bool(
        payload.get("mgt_export_source_output_mgt_diff_preview_exists", False)
    )
    mgt_export_source_output_mgt_diff_window_json_exists = bool(
        payload.get("mgt_export_source_output_mgt_diff_window_json_exists", False)
    )
    mgt_export_source_output_mgt_diff_window_preview_exists = bool(
        payload.get("mgt_export_source_output_mgt_diff_window_preview_exists", False)
    )
    mgt_export_source_output_mgt_verification_receipt_line = html.escape(
        str(payload.get("mgt_export_source_output_mgt_verification_receipt_line", "") or "n/a")
    )
    mgt_export_source_output_mgt_diff_preview_text = html.escape(
        str(payload.get("mgt_export_source_output_mgt_diff_preview_text", "") or "")
    )
    mgt_export_source_output_mgt_diff_window_preview_text = html.escape(
        str(payload.get("mgt_export_source_output_mgt_diff_window_preview_text", "") or "")
    )
    mgt_export_source_output_mgt_diff_sample_lines = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_sample_lines") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_search_tokens = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_search_tokens") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_member_ids = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_member_ids") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_member_row_indices = {
        str(key): [int(value) for value in values]
        for key, values in (payload.get("mgt_export_source_output_mgt_diff_member_row_indices") or {}).items()
        if str(key).strip()
    }
    mgt_export_source_output_mgt_diff_section_ids = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_section_ids") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_window_search_tokens = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_window_search_tokens") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_window_member_ids = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_window_member_ids") or [])
        if str(value).strip()
    ]
    mgt_export_source_output_mgt_diff_window_member_row_indices = {
        str(key): [int(value) for value in values]
        for key, values in (payload.get("mgt_export_source_output_mgt_diff_window_member_row_indices") or {}).items()
        if str(key).strip()
    }
    mgt_export_source_output_mgt_diff_window_section_ids = [
        str(value)
        for value in (payload.get("mgt_export_source_output_mgt_diff_window_section_ids") or [])
        if str(value).strip()
    ]
    mgt_compare_window_json_href = html.escape(str(payload.get("mgt_compare_window_json_href", "") or ""))
    mgt_compare_window_txt_href = html.escape(str(payload.get("mgt_compare_window_txt_href", "") or ""))
    mgt_compare_window_summary_line = html.escape(str(payload.get("mgt_compare_window_summary_line", "") or ""))
    mgt_compare_window_row_count = _safe_int(payload.get("mgt_compare_window_row_count", 0))
    mgt_compare_window_preview_text = html.escape(str(payload.get("mgt_compare_window_preview_text", "") or ""))
    mgt_compare_window_rows = [
        row for row in (payload.get("mgt_compare_window_rows") or []) if isinstance(row, dict)
    ]
    mgt_compare_window_member_row_indices = {
        str(key): [int(value) for value in values]
        for key, values in (payload.get("mgt_compare_window_member_row_indices") or {}).items()
        if str(key).strip()
    }
    mgt_export_source_output_mgt_diff_sample_rows = [
        row for row in (payload.get("mgt_export_source_output_mgt_diff_sample_rows") or []) if isinstance(row, dict)
    ]
    mgt_export_source_vs_output_diff_summary_line = html.escape(
        str(payload.get("mgt_export_source_vs_output_diff_summary_line", "") or "n/a")
    )
    mgt_export_source_vs_output_diff_changed_line_count = _safe_int(
        payload.get("mgt_export_source_vs_output_diff_changed_line_count", 0)
    )
    mgt_export_source_vs_output_diff_added_line_count = _safe_int(
        payload.get("mgt_export_source_vs_output_diff_added_line_count", 0)
    )
    mgt_export_source_vs_output_diff_removed_line_count = _safe_int(
        payload.get("mgt_export_source_vs_output_diff_removed_line_count", 0)
    )
    mgt_export_source_vs_output_diff_sample_count = _safe_int(
        payload.get("mgt_export_source_vs_output_diff_sample_count", 0)
    )
    mgt_export_source_vs_output_source_line_count = _safe_int(
        payload.get("mgt_export_source_vs_output_source_line_count", 0)
    )
    mgt_export_source_vs_output_output_line_count = _safe_int(
        payload.get("mgt_export_source_vs_output_output_line_count", 0)
    )
    mgt_export_source_vs_output_diff_sample_rows = [
        row for row in (payload.get("mgt_export_source_vs_output_diff_sample_rows") or []) if isinstance(row, dict)
    ]
    mgt_export_source_vs_output_diff_window_rows = [
        row for row in (payload.get("mgt_export_source_vs_output_diff_window_rows") or []) if isinstance(row, dict)
    ]
    mgt_export_source_vs_output_diff_window_count = _safe_int(
        payload.get("mgt_export_source_vs_output_diff_window_count", 0)
    )
    mgt_compare_window_available = bool(
        mgt_export_source_vs_output_diff_window_count or mgt_export_source_vs_output_diff_window_rows
    )
    mgt_export_native_authoring_summary_line = html.escape(
        str(payload.get("mgt_export_native_authoring_summary_line", "") or "n/a")
    )
    mgt_export_total_change_count = _safe_int(payload.get("mgt_export_total_change_count", 0))
    mgt_export_supported_change_count = _safe_int(payload.get("mgt_export_supported_change_count", 0))
    mgt_export_supported_change_ratio = _safe_float(payload.get("mgt_export_supported_change_ratio", 0.0))
    mgt_export_direct_patch_change_count = _safe_int(payload.get("mgt_export_direct_patch_change_count", 0))
    mgt_export_direct_patch_change_ratio = _safe_float(payload.get("mgt_export_direct_patch_change_ratio", 0.0))
    mgt_export_patched_supported_change_count = _safe_int(payload.get("mgt_export_patched_supported_change_count", 0))
    mgt_export_instruction_sidecar_change_count = _safe_int(payload.get("mgt_export_instruction_sidecar_change_count", 0))
    mgt_export_instruction_sidecar_change_ratio = _safe_float(
        payload.get("mgt_export_instruction_sidecar_change_ratio", 0.0)
    )
    mgt_export_instruction_sidecar_zero_touch_verified_change_count = _safe_int(
        payload.get("mgt_export_instruction_sidecar_zero_touch_verified_change_count", 0)
    )
    mgt_export_instruction_sidecar_zero_touch_verified_change_ratio = _safe_float(
        payload.get("mgt_export_instruction_sidecar_zero_touch_verified_change_ratio", 0.0)
    )
    mgt_export_unsupported_change_count = _safe_int(payload.get("mgt_export_unsupported_change_count", 0))
    mgt_export_unsupported_change_ratio = _safe_float(payload.get("mgt_export_unsupported_change_ratio", 0.0))
    mgt_export_loadcomb_combo_count = _safe_int(payload.get("mgt_export_loadcomb_combo_count", 0))
    mgt_export_audit_review_queue_item_count = _safe_int(payload.get("mgt_export_audit_review_queue_item_count", 0))
    mgt_export_audit_review_queue_pending_count = _safe_int(payload.get("mgt_export_audit_review_queue_pending_count", 0))
    mgt_export_diff_summary_line = html.escape(str(payload.get("mgt_export_diff_summary_line", "") or ""))
    mgt_export_diff_rows = [row for row in (payload.get("mgt_export_diff_rows") or []) if isinstance(row, dict)]
    midas_roundtrip_gate_report_href = html.escape(str(payload.get("midas_roundtrip_gate_report_href", "") or ""))
    midas_roundtrip_gate_contract_pass = bool(payload.get("midas_roundtrip_gate_contract_pass", False))
    midas_roundtrip_gate_summary_line = html.escape(str(payload.get("midas_roundtrip_gate_summary_line", "") or "n/a"))
    midas_roundtrip_gate_ready_count = _safe_int(payload.get("midas_roundtrip_gate_ready_count", 0))
    midas_roundtrip_gate_corpus_case_count = _safe_int(payload.get("midas_roundtrip_gate_corpus_case_count", 0))
    midas_roundtrip_gate_public_native_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_native_ready_count", 0)
    )
    midas_roundtrip_gate_public_source_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_source_ready_count", 0)
    )
    midas_roundtrip_gate_public_structural_preview_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_structural_preview_ready_count", 0)
    )
    midas_roundtrip_gate_pending_review_total = _safe_int(payload.get("midas_roundtrip_gate_pending_review_total", 0))
    midas_roundtrip_gate_loadcomb_exact_case_count = _safe_int(
        payload.get("midas_roundtrip_gate_loadcomb_exact_case_count", 0)
    )
    midas_roundtrip_gate_taxonomy_exact_count = _safe_int(payload.get("midas_roundtrip_gate_taxonomy_exact_count", 0))
    midas_roundtrip_gate_taxonomy_canonical_count = _safe_int(
        payload.get("midas_roundtrip_gate_taxonomy_canonical_count", 0)
    )
    mgt_export_special_member_supported_action_family_label = html.escape(
        str(payload.get("mgt_export_special_member_supported_action_family_label", "") or "n/a")
    )
    mgt_export_special_member_direct_patch_action_family_label = html.escape(
        str(payload.get("mgt_export_special_member_direct_patch_action_family_label", "") or "n/a")
    )
    mgt_export_special_member_zero_touch_verified_action_family_label = html.escape(
        str(payload.get("mgt_export_special_member_zero_touch_verified_action_family_label", "") or "n/a")
    )

    def _dock_tree_row(label: str, value: Any, *, is_child: bool = False, state_class: str = "is-good") -> str:
        row_class = "dock-tree-row is-child" if is_child else "dock-tree-row"
        return (
            f"<div class='{row_class}'>"
            f"<span class='dock-tree-label'><span class='dock-tree-bullet'></span>{html.escape(label)}</span>"
            f"<span class='dock-tree-state {state_class}'>{html.escape(str(value))}</span>"
            "</div>"
        )

    def _dock_tree_section(title: str, tag: str, rows_html: str) -> str:
        return (
            "<section class='dock-tree-section'>"
            f"<div class='dock-tree-branch-head'><span class='dock-tree-branch-title'>{html.escape(title)}</span>"
            f"<span class='dock-tree-branch-tag'>{html.escape(tag)}</span></div>"
            f"{rows_html}"
            "</section>"
        )

    member_type_tree_rows_html = "".join(
        (
            "<div class='dock-tree-row is-child'>"
            f"<span class='dock-tree-label'><span class='dock-tree-bullet'></span>{html.escape(str(row.get('label', '') or 'n/a'))}</span>"
            f"<span class='dock-tree-state is-good'>{_safe_int(row.get('changed_group_count', 0))}</span>"
            "</div>"
        )
        for row in member_type_rows[:6]
    )
    mgt_diff_sample_rows_html = "".join(
        (
            "<div class='mgt-diff-row'>"
            f"<div class='mgt-diff-row-head'><span class='mgt-diff-kind is-{html.escape(str(row.get('kind', '') or 'replace'))}'>{html.escape(str(row.get('kind', '') or 'replace').upper())}</span>"
            f"<span>S:{html.escape(str(row.get('source_line_number', '')) or '-')}</span>"
            f"<span>O:{html.escape(str(row.get('output_line_number', '')) or '-')}</span></div>"
            f"<div class='mgt-diff-code'><span class='mgt-diff-code-label'>src</span><code>{html.escape(str(row.get('source_line', '') or ''))}</code></div>"
            f"<div class='mgt-diff-code'><span class='mgt-diff-code-label'>out</span><code>{html.escape(str(row.get('output_line', '') or ''))}</code></div>"
            "</div>"
        )
        for row in mgt_export_source_vs_output_diff_sample_rows[:8]
    )

    dock_tree_html = "\n".join(
        [
            _dock_tree_section(
                "Geometry bridge",
                "source",
                "\n".join(
                    [
                        _dock_tree_row("Axis / Grid refs", "on"),
                        _dock_tree_row("Story reference lines", "on", is_child=True),
                    ]
                ),
            ),
            _dock_tree_section(
                "Model lanes",
                "overlay",
                "\n".join(
                    [
                        _dock_tree_row("Baseline structure lane", "on"),
                        _dock_tree_row("Optimized overlay lane", "on", is_child=True),
                    ]
                ),
            ),
            _dock_tree_section(
                "Member families",
                str(max(len(member_type_rows), 1)),
                "\n".join(
                    [
                        _dock_tree_row(
                            "Beam / Column / Wall / Slab",
                            max(len(member_type_rows), 1),
                        ),
                        member_type_tree_rows_html,
                    ]
                ),
            ),
            _dock_tree_section(
                "MGT checks",
                "bounded",
                "\n".join(
                    [
                        _dock_tree_row("LOADCOMB combos", mgt_export_loadcomb_combo_count),
                        _dock_tree_row("Direct patch changes", mgt_export_direct_patch_change_count, is_child=True),
                        _dock_tree_row(
                            "Patched supported changes",
                            mgt_export_patched_supported_change_count,
                            is_child=True,
                        ),
                        _dock_tree_row(
                            "Audit queue pending",
                            mgt_export_audit_review_queue_pending_count,
                            is_child=True,
                            state_class="is-good" if mgt_export_audit_review_queue_pending_count == 0 else "is-warn",
                        ),
                        _dock_tree_row(
                            "Unsupported changes",
                            mgt_export_unsupported_change_count,
                            is_child=True,
                            state_class="is-good" if mgt_export_unsupported_change_count == 0 else "is-warn",
                        ),
                        _dock_tree_row(
                            "Source vs output changed",
                            mgt_export_source_vs_output_diff_changed_line_count,
                            is_child=True,
                            state_class="is-good" if mgt_export_source_vs_output_diff_changed_line_count >= 0 else "is-neutral",
                        ),
                        _dock_tree_row(
                            "Source vs output sample",
                            mgt_export_source_vs_output_diff_sample_count,
                            is_child=True,
                            state_class="is-neutral",
                        ),
                        _dock_tree_row(
                            "Source vs output window",
                            mgt_export_source_vs_output_diff_window_count,
                            is_child=True,
                            state_class="is-neutral",
                        ),
                    ]
                ),
            ),
            _dock_tree_section(
                "Validation breadth",
                str(midas_roundtrip_gate_corpus_case_count or "gate"),
                "\n".join(
                    [
                        _dock_tree_row(
                            "Native ready / corpus",
                            f"{midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)}",
                            state_class="is-good" if midas_roundtrip_gate_ready_count > 0 else "is-neutral",
                        ),
                        _dock_tree_row(
                            "Public native ready",
                            midas_roundtrip_gate_public_native_ready_count,
                            is_child=True,
                            state_class="is-good" if midas_roundtrip_gate_public_native_ready_count > 0 else "is-neutral",
                        ),
                        _dock_tree_row(
                            "Public source ready",
                            midas_roundtrip_gate_public_source_ready_count,
                            is_child=True,
                            state_class="is-good" if midas_roundtrip_gate_public_source_ready_count > 0 else "is-neutral",
                        ),
                        _dock_tree_row(
                            "Structural preview ready",
                            midas_roundtrip_gate_public_structural_preview_ready_count,
                            is_child=True,
                            state_class="is-good" if midas_roundtrip_gate_public_structural_preview_ready_count > 0 else "is-neutral",
                        ),
                    ]
                ),
            ),
        ]
    )

    mgt_verification_diff_rows_html_parts: list[str] = []
    if mgt_export_source_vs_output_diff_summary_line and mgt_export_source_vs_output_diff_summary_line != "n/a":
        mgt_verification_diff_rows_html_parts.append(
            f"<div class='mgt-diff-summary'>{mgt_export_source_vs_output_diff_summary_line}</div>"
        )
        mgt_verification_diff_rows_html_parts.append(
            "<div class='mgt-diff-grid'>"
            f"<div class='mgt-diff-stat'><span>Source lines</span><strong>{mgt_export_source_vs_output_source_line_count}</strong></div>"
            f"<div class='mgt-diff-stat'><span>Output lines</span><strong>{mgt_export_source_vs_output_output_line_count}</strong></div>"
            f"<div class='mgt-diff-stat'><span>Changed</span><strong>{mgt_export_source_vs_output_diff_changed_line_count}</strong></div>"
            f"<div class='mgt-diff-stat'><span>Added / Removed</span><strong>{mgt_export_source_vs_output_diff_added_line_count} / {mgt_export_source_vs_output_diff_removed_line_count}</strong></div>"
            "</div>"
        )
        if mgt_diff_sample_rows_html:
            mgt_verification_diff_rows_html_parts.append(
                f"<div class='mgt-diff-samples'>{mgt_diff_sample_rows_html}</div>"
            )
    if mgt_export_diff_summary_line:
        mgt_verification_diff_rows_html_parts.append(
            f"<div class='mgt-diff-summary'>{mgt_export_diff_summary_line}</div>"
        )
    if mgt_export_diff_rows:
        for row in mgt_export_diff_rows:
            tone = str(row.get("tone", "") or "").strip().lower()
            if tone in {"pass", "good", "ok", "positive", "green"}:
                tone_class = "is-good"
            elif tone in {"bad", "error", "fail", "negative", "red"}:
                tone_class = "is-bad"
            elif tone in {"neutral", "info"}:
                tone_class = "is-neutral"
            else:
                tone_class = "is-warn" if tone else "is-neutral"
            label = html.escape(str(row.get("label", "") or "n/a"))
            value = html.escape(str(row.get("value", "") or "n/a"))
            note = html.escape(str(row.get("note", "") or ""))
            row_html = (
                "<div class='mgt-diff-row'>"
                "<div class='mgt-diff-row-head'>"
                f"<span class='mgt-diff-label'>{label}</span>"
                f"<span class='mgt-diff-value {tone_class}'>{value}</span>"
                "</div>"
            )
            if note:
                row_html += f"<div class='mgt-diff-note'>{note}</div>"
            row_html += "</div>"
            mgt_verification_diff_rows_html_parts.append(row_html)
    elif not mgt_diff_sample_rows_html and not (
        mgt_export_source_vs_output_diff_summary_line and mgt_export_source_vs_output_diff_summary_line != "n/a"
    ):
        mgt_verification_diff_rows_html_parts.append(
            "<div class='mgt-diff-empty'>No compact diff payload supplied; bounded summary stays visible.</div>"
        )
    mgt_verification_diff_rows_html = "\n".join(mgt_verification_diff_rows_html_parts)
    mgt_source_output_diff_rows_source = (
        mgt_compare_window_rows
        if mgt_compare_window_rows
        else mgt_export_source_vs_output_diff_window_rows
        if mgt_export_source_vs_output_diff_window_rows
        else mgt_export_source_output_mgt_diff_sample_rows
    )
    mgt_source_output_diff_entries: list[dict[str, Any]] = []
    if mgt_source_output_diff_rows_source:
        for index, row in enumerate(mgt_source_output_diff_rows_source):
            kind = str(row.get("kind", "") or "replace").strip().lower()
            row_index = _safe_int(row.get("row_index", index))
            row_id = str(row.get("row_id", "") or f"mgt-diff-row-{row_index:04d}")
            source_line_number = str(row.get("source_line_number", "") or "").strip()
            output_line_number = str(row.get("output_line_number", "") or "").strip()
            source_line = str(row.get("source_line", "") or "").strip()
            output_line = str(row.get("output_line", "") or "").strip()
            candidate_member_ids = _sample_diff_member_ids(row)
            candidate_section_ids = _sample_diff_section_ids(row)
            candidate_card_ids = [
                str(value).strip()
                for value in (row.get("candidate_card_ids") or [])
                if str(value).strip()
            ]
            exact_member_id_match = bool(row.get("exact_member_id_match", False))
            geometry_bridge_member_ids = [
                str(value).strip()
                for value in (row.get("geometry_bridge_member_ids") or [])
                if str(value).strip()
            ]
            if not candidate_card_ids and candidate_member_ids:
                candidate_card_ids = candidate_member_ids[:]
            if kind == "insert":
                display_line = f"+ O:{output_line_number or '-'} | out={output_line}"
            elif kind == "delete":
                display_line = f"- S:{source_line_number or '-'} | src={source_line}"
            else:
                display_line = (
                    f"~ S:{source_line_number or '-'} O:{output_line_number or '-'} | "
                    f"src={source_line} | out={output_line}"
                )
            member_id = candidate_member_ids[0] if candidate_member_ids else _sample_diff_member_id(row)
            search_text = _join_search_tokens(
                index,
                kind,
                member_id,
                *(candidate_member_ids + geometry_bridge_member_ids),
                source_line_number,
                output_line_number,
                source_line,
                output_line,
                display_line,
            )
            mgt_source_output_diff_entries.append(
                {
                    "row_index": row_index,
                    "row_id": row_id,
                    "kind": kind,
                    "member_id": member_id,
                    "source_line_number": source_line_number,
                    "output_line_number": output_line_number,
                    "source_line": source_line,
                    "output_line": output_line,
                    "display_line": display_line,
                    "search_text": search_text,
                    "candidate_member_ids": candidate_member_ids,
                    "candidate_section_ids": candidate_section_ids,
                    "candidate_card_ids": candidate_card_ids,
                    "geometry_bridge_member_ids": geometry_bridge_member_ids,
                    "exact_member_id_match": exact_member_id_match,
                }
            )
    else:
        for index, line in enumerate(mgt_export_source_output_mgt_diff_sample_lines[:12]):
            display_line = str(line)
            member_match = re.search(r"\b(\d+)\b", display_line)
            mgt_source_output_diff_entries.append(
                {
                    "row_index": index,
                    "row_id": f"mgt-diff-row-{index:04d}",
                    "kind": "replace" if display_line.startswith("~") else "insert" if display_line.startswith("+") else "delete" if display_line.startswith("-") else "neutral",
                    "member_id": member_match.group(1) if member_match else "",
                    "candidate_member_ids": [member_match.group(1)] if member_match else [],
                    "candidate_section_ids": [],
                    "candidate_card_ids": [member_match.group(1)] if member_match else [],
                    "geometry_bridge_member_ids": [],
                    "exact_member_id_match": False,
                    "source_line_number": "",
                    "output_line_number": "",
                    "source_line": "",
                    "output_line": "",
                    "display_line": display_line,
                    "search_text": _join_search_tokens(index, display_line),
                }
            )
    if not mgt_source_output_diff_entries:
        mgt_source_output_diff_entries = [
            {
                "row_index": 0,
                "row_id": "mgt-diff-row-0000",
                "kind": "neutral",
                "member_id": "",
                "source_line_number": "",
                "output_line_number": "",
                "source_line": "",
                "output_line": "",
                "display_line": "No source/output diff sample lines available.",
                "search_text": "no source output diff sample lines available",
                "candidate_member_ids": [],
                "candidate_section_ids": [],
                "candidate_card_ids": [],
                "geometry_bridge_member_ids": [],
                "exact_member_id_match": False,
            }
        ]
    mgt_diff_row_index_map: dict[str, list[int]] = {
        str(key): [int(value) for value in values]
        for key, values in (
            mgt_compare_window_member_row_indices
            or mgt_export_source_output_mgt_diff_window_member_row_indices
            or mgt_export_source_output_mgt_diff_member_row_indices
            or {}
        ).items()
        if str(key).strip()
    }
    if not mgt_diff_row_index_map:
        for entry in mgt_source_output_diff_entries:
            row_index = _safe_int(entry.get("row_index", 0))
            for key in _dedupe_exact_text_list(
                [
                    entry.get("member_id", ""),
                    *(entry.get("candidate_member_ids") or []),
                    *(entry.get("geometry_bridge_member_ids") or []),
                ]
            ):
                mgt_diff_row_index_map.setdefault(key, []).append(row_index)
                lower_key = key.lower()
                if lower_key != key:
                    mgt_diff_row_index_map.setdefault(lower_key, []).append(row_index)
    mgt_diff_row_index_map_json = json.dumps(mgt_diff_row_index_map, ensure_ascii=False).replace("<", "\\u003c")
    def _data_list_attr(values: Any) -> str:
        return html.escape("|".join(_dedupe_exact_text_list([value for value in (values or []) if str(value).strip()])))

    compare_page_size = 32

    def _compare_page_source_text(entries: list[dict[str, Any]]) -> str:
        return "\n".join(
            (
                f"S:{str(entry.get('source_line_number', '') or '-'):>6} | "
                f"{str(entry.get('source_line', '') or '(insert)')}"
            )
            for entry in entries
        )

    def _compare_page_output_text(entries: list[dict[str, Any]]) -> str:
        return "\n".join(
            (
                f"O:{str(entry.get('output_line_number', '') or '-'):>6} | "
                f"{str(entry.get('output_line', '') or '(delete)')}"
            )
            for entry in entries
        )

    mgt_compare_page_groups: list[dict[str, Any]] = []

    mgt_source_output_raw_diff_lines = [str(entry.get("display_line", "") or "") for entry in mgt_source_output_diff_entries]
    mgt_source_output_raw_diff_lines_html = "\n".join(
        (
            "<div class='mgt-raw-diff-line "
            f"{'is-insert' if str(entry.get('kind', '') or '').startswith('insert') else 'is-delete' if str(entry.get('kind', '') or '').startswith('delete') else 'is-replace' if str(entry.get('kind', '') or '').startswith('replace') else 'is-neutral'}'>"
            f"<span class='mgt-raw-diff-line-shell' data-raw-diff-line data-diff-index='{_safe_int(entry.get('row_index', index))}' data-diff-row-id='{html.escape(str(entry.get('row_id', '') or ''))}' data-diff-key='{html.escape(_compare_entry_key(entry))}' data-member-id='{html.escape(str(entry.get('member_id', '') or ''))}' data-member-ids='{_data_list_attr([*(entry.get('candidate_member_ids') or []), *(entry.get('geometry_bridge_member_ids') or [])])}' data-candidate-member-ids='{_data_list_attr(entry.get('candidate_member_ids'))}' data-candidate-section-ids='{_data_list_attr(entry.get('candidate_section_ids'))}' data-candidate-card-ids='{_data_list_attr(entry.get('candidate_card_ids'))}' data-geometry-bridge-member-ids='{_data_list_attr(entry.get('geometry_bridge_member_ids'))}' data-exact-member-id-match='{ 'true' if entry.get('exact_member_id_match') else 'false' }' data-search='{html.escape(str(entry.get('search_text', '') or ''))}'>"
            f"<span class='mgt-raw-diff-marker'>{html.escape((str(entry.get('display_line', '') or '')[:1]) or '•')}</span>"
            f"<code>{html.escape(str(entry.get('display_line', '') or ''))}</code>"
            "</span></div>"
        )
        for index, entry in enumerate(mgt_source_output_diff_entries)
    )
    mgt_source_output_compare_rows_html = "\n".join(
        (
            "<article class='mgt-compare-row' data-compare-row "
            f"data-diff-index='{_safe_int(entry.get('row_index', index))}' "
            f"data-compare-page='{index // compare_page_size}' "
            f"data-diff-row-id='{html.escape(str(entry.get('row_id', '') or ''))}' "
            f"data-diff-key='{html.escape(_compare_entry_key(entry))}' "
            f"data-member-id='{html.escape(str(entry.get('member_id', '') or ''))}' "
            f"data-member-ids='{_data_list_attr([*(entry.get('candidate_member_ids') or []), *(entry.get('geometry_bridge_member_ids') or [])])}' "
            f"data-candidate-member-ids='{_data_list_attr(entry.get('candidate_member_ids'))}' "
            f"data-candidate-section-ids='{_data_list_attr(entry.get('candidate_section_ids'))}' "
            f"data-candidate-card-ids='{_data_list_attr(entry.get('candidate_card_ids'))}' "
            f"data-geometry-bridge-member-ids='{_data_list_attr(entry.get('geometry_bridge_member_ids'))}' "
            f"data-exact-member-id-match='{ 'true' if entry.get('exact_member_id_match') else 'false' }' "
            f"data-search='{html.escape(str(entry.get('search_text', '') or ''))}'>"
            "<div class='mgt-compare-row-head'>"
            f"<div class='mgt-compare-row-kicker'>{html.escape(str(entry.get('kind', '') or 'neutral').upper())}</div>"
            f"<div class='mgt-compare-row-meta'>S:{html.escape(str(entry.get('source_line_number', '') or '-'))} | O:{html.escape(str(entry.get('output_line_number', '') or '-'))} | member {html.escape(str(entry.get('member_id', '') or 'n/a'))}</div>"
            "</div>"
            "<div class='mgt-compare-split'>"
            "<section class='mgt-compare-side is-source'>"
            "<div class='mgt-compare-side-label'>Source</div>"
            f"<pre class='mgt-compare-code'>{html.escape(str(entry.get('source_line', '') or 'n/a'))}</pre>"
            "</section>"
            "<section class='mgt-compare-side is-output'>"
            "<div class='mgt-compare-side-label'>Optimized</div>"
            f"<pre class='mgt-compare-code'>{html.escape(str(entry.get('output_line', '') or 'n/a'))}</pre>"
            "</section>"
            "</div>"
            "</article>"
        )
        for index, entry in enumerate(mgt_source_output_diff_entries)
    )
    for page_index, page_start in enumerate(range(0, len(mgt_source_output_diff_entries), compare_page_size)):
        page_entries = mgt_source_output_diff_entries[page_start : page_start + compare_page_size]
        page_rows_html = "\n".join(
            (
                "<article class='mgt-compare-page-row' data-compare-page-row "
                f"data-diff-index='{_safe_int(entry.get('row_index', index))}' "
                f"data-compare-page='{page_index}' "
                f"data-diff-row-id='{html.escape(str(entry.get('row_id', '') or ''))}' "
                f"data-diff-key='{html.escape(_compare_entry_key(entry))}' "
                f"data-member-id='{html.escape(str(entry.get('member_id', '') or ''))}' "
                f"data-member-ids='{_data_list_attr([*(entry.get('candidate_member_ids') or []), *(entry.get('geometry_bridge_member_ids') or [])])}' "
                f"data-exact-member-id-match='{ 'true' if entry.get('exact_member_id_match') else 'false' }'>"
                "<div class='mgt-compare-page-rail'>"
                f"<div class='mgt-compare-page-index'>#{index + 1:03d}</div>"
                f"<div class='mgt-compare-page-member'>{html.escape(str(entry.get('member_id', '') or 'n/a'))}</div>"
                f"<div class='mgt-compare-page-meta'>S:{html.escape(str(entry.get('source_line_number', '') or '-'))} | O:{html.escape(str(entry.get('output_line_number', '') or '-'))}</div>"
                "</div>"
                "<div class='mgt-compare-page-split'>"
                "<section class='mgt-compare-page-side is-source'>"
                "<div class='mgt-compare-page-side-label'>Source</div>"
                f"<pre class='mgt-compare-page-code'>{html.escape(str(entry.get('source_line', '') or 'n/a'))}</pre>"
                "</section>"
                "<section class='mgt-compare-page-side is-output'>"
                "<div class='mgt-compare-page-side-label'>Optimized</div>"
                f"<pre class='mgt-compare-page-code'>{html.escape(str(entry.get('output_line', '') or 'n/a'))}</pre>"
                "</section>"
                "</div>"
                "</article>"
            )
            for index, entry in enumerate(page_entries, start=page_start)
        )
        mgt_compare_page_groups.append(
            {
                "page_index": page_index,
                "row_count": len(page_entries),
                "source_text": _compare_page_source_text(page_entries),
                "output_text": _compare_page_output_text(page_entries),
                "rows_html": page_rows_html,
            }
        )
    mgt_compare_page_tabs_html = "".join(
        (
            "<button class='mgt-compare-page-tab "
            f"{'is-active' if int(group.get('page_index', 0)) == 0 else ''}' "
            f"type='button' data-compare-page-tab='{int(group.get('page_index', 0))}' "
            f"aria-selected='{'true' if int(group.get('page_index', 0)) == 0 else 'false'}'>"
            f"<span>Page {int(group.get('page_index', 0)) + 1}</span>"
            f"<span class='mgt-compare-page-tab-count'>{_safe_int(group.get('row_count', 0))}</span>"
            "</button>"
        )
        for group in mgt_compare_page_groups
    )
    mgt_compare_page_nav_html = "".join(
        (
            f"<button class='mgt-compare-nav-button' type='button' data-compare-page-nav='{action}'>{label}</button>"
        )
        for action, label in [
            ("first", "First"),
            ("prev", "Prev"),
            ("next", "Next"),
            ("last", "Last"),
        ]
    )
    mgt_compare_page_panels_html = "\n".join(
        (
            "<section class='mgt-compare-page-panel "
            f"{'is-active' if int(group.get('page_index', 0)) == 0 else ''}' "
            f"data-compare-page-panel='{int(group.get('page_index', 0))}' "
            f"{'' if int(group.get('page_index', 0)) == 0 else 'hidden'}>"
            "<div class='mgt-compare-page-text-grid'>"
            "<section class='mgt-compare-page-text-panel is-source'>"
            "<div class='mgt-compare-page-text-label'>Source page</div>"
            f"<pre class='mgt-compare-page-text-code'>{html.escape(str(group.get('source_text', '') or 'n/a'))}</pre>"
            "</section>"
            "<section class='mgt-compare-page-text-panel is-output'>"
            "<div class='mgt-compare-page-text-label'>Optimized page</div>"
            f"<pre class='mgt-compare-page-text-code'>{html.escape(str(group.get('output_text', '') or 'n/a'))}</pre>"
            "</section>"
            "</div>"
            f"<div class='mgt-compare-page'>{str(group.get('rows_html', '') or '')}</div>"
            "</section>"
        )
        for group in mgt_compare_page_groups
    )
    mgt_artifact_link_specs = [
        {"label": "MGT export report", "href": mgt_export_report_href},
        {"label": "Source .mgt", "href": mgt_source_mgt_href},
        {"label": "Optimized .mgt", "href": mgt_output_mgt_href},
        {"label": "LOADCOMB preview", "href": mgt_loadcomb_preview_href},
        {"label": "Roundtrip report", "href": mgt_loadcomb_roundtrip_report_href},
        {"label": "Diff JSON", "href": mgt_source_output_diff_json_href},
        {"label": "Diff TXT", "href": mgt_source_output_diff_preview_href},
        {"label": "Diff Window JSON", "href": mgt_source_output_diff_window_json_href},
        {"label": "Diff Window TXT", "href": mgt_source_output_diff_window_preview_href},
        {"label": "Native roundtrip gate", "href": midas_roundtrip_gate_report_href},
    ]
    mgt_artifact_links_html = render_link_pills(links=mgt_artifact_link_specs, quote="'")
    mgt_artifact_links_markup = render_link_pills(
        links=mgt_artifact_link_specs,
        container_class="link-row",
        container_attrs={"style": "margin-top:14px;"},
        quote="'",
    )
    mgt_artifact_tab_links_markup = render_link_pills(
        links=mgt_artifact_link_specs,
        container_class="link-row",
        container_attrs={"style": "margin-top:12px;"},
        quote="'",
    )
    mgt_compare_window_links_html = render_link_pills(
        links=[
            {"label": "Window JSON", "href": mgt_compare_window_json_href},
            {"label": "Window TXT", "href": mgt_compare_window_txt_href},
        ],
        quote="'",
        separator=" ",
    )
    mgt_verification_tab_buttons_html = (
        "<div class='mgt-tab-strip' role='tablist' aria-label='MGT verification workspace tabs'>"
        "<button class='mgt-tab-button is-active' type='button' data-mgt-tab='summary' aria-selected='true'>Summary</button>"
        "<button class='mgt-tab-button' type='button' data-mgt-tab='compare' aria-selected='false'>Compare</button>"
        "<button class='mgt-tab-button' type='button' data-mgt-tab='raw' aria-selected='false'>Raw diff</button>"
        "<button class='mgt-tab-button' type='button' data-mgt-tab='artifacts' aria-selected='false'>Artifacts</button>"
        "</div>"
    )
    mgt_verification_summary_tab_html = f"""
    <section class='mgt-tab-panel is-active' data-mgt-tab-panel='summary'>
      <div class='mgt-verification-summary'>
        <div class='mgt-verification-summary-title'>Bounded support</div>
        <div class='mgt-verification-summary-line'>{mgt_export_native_authoring_summary_line}</div>
        <div class='mgt-console-grid'>
          <div class='mgt-console-kv'>
            <span>Output MGT</span>
            <strong title='{mgt_output_mgt_href or "n/a"}'>{mgt_output_mgt_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Support mode</span>
            <strong>{mgt_export_support_mode}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Roundtrip</span>
            <strong>{mgt_export_loadcomb_roundtrip_summary_line}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Boundary</span>
            <strong title='{mgt_export_delivery_boundary}'>{mgt_export_delivery_boundary}</strong>
          </div>
        </div>
        <div class='mgt-verification-summary-note'>
          <code>output_mgt_exists={"true" if mgt_export_output_mgt_exists else "false"}</code> |
          <code>loadcomb_roundtrip={"true" if mgt_export_loadcomb_roundtrip_pass else "false"}</code> |
          <code>supported={mgt_export_supported_change_count}/{mgt_export_total_change_count or max(mgt_export_supported_change_count, 1)}</code> |
          <code>direct_patch={mgt_export_direct_patch_change_count}</code> |
          <code>zero_touch={mgt_export_instruction_sidecar_zero_touch_verified_change_count}</code>
        </div>
        <div class='mgt-verification-summary-note'>Receipt: {mgt_export_source_output_mgt_verification_receipt_line}</div>
        <div class='mgt-verification-summary-note'>
          Bound: {mgt_export_support_mode} | delivery={mgt_export_delivery_boundary}
        </div>
      </div>
      <div class='mgt-diff-panel'>
        <div class='mgt-diff-panel-head'>
          <div class='mgt-diff-panel-kicker'>Compact diff</div>
          <div class='mgt-diff-panel-count'>{max(len(mgt_export_diff_rows), mgt_export_source_vs_output_diff_sample_count)} rows</div>
        </div>
        {mgt_verification_diff_rows_html}
      </div>
    </section>
    """
    mgt_raw_diff_preview_combined = mgt_compare_window_preview_text or mgt_export_source_output_mgt_diff_preview_text
    if (
        mgt_compare_window_preview_text
        and mgt_export_source_output_mgt_diff_preview_text
        and mgt_compare_window_preview_text != mgt_export_source_output_mgt_diff_preview_text
    ):
        mgt_raw_diff_preview_combined = (
            f"{mgt_compare_window_preview_text}\n\n{mgt_export_source_output_mgt_diff_preview_text}"
        )
    mgt_verification_compare_tab_html = f"""
    <section class='mgt-tab-panel' data-mgt-tab-panel='compare' hidden>
      <div class='mgt-compare-panel'>
        <div class='mgt-diff-panel-head'>
          <div class='mgt-diff-panel-kicker'>Source vs Optimized</div>
          <div class='mgt-diff-panel-count'>{len(mgt_source_output_diff_entries)} rows</div>
        </div>
        <div class='mgt-compare-summary'>Side-by-side source/output pairs are sourced from {('the widened diff window artifact' if mgt_compare_window_available else 'the same diff sample rows that feed the raw diff tab')}.</div>
        <div class='mgt-verification-summary-note'>
          Compare window: {mgt_compare_window_summary_line or 'n/a'} |
          rows={mgt_compare_window_row_count} |
          {mgt_compare_window_links_html}
        </div>
        <div class='mgt-compare-preview'>{mgt_compare_window_preview_text if mgt_compare_window_preview_text else mgt_export_source_output_mgt_diff_preview_text}</div>
        <div class='mgt-compare-sheet'>
          <div class='mgt-compare-sheet-head'>
            <div class='mgt-compare-sheet-kicker'>Page diff</div>
            <div class='mgt-compare-sheet-note'>Wider source/output sheet for MIDAS-style review and exact member jump.</div>
          </div>
          <div class='mgt-compare-pager-dock'>
            <div class='mgt-compare-pager-cluster'>
              <div class='mgt-compare-pager' role='tablist' aria-label='Compare page dock pager'>
                {mgt_compare_page_tabs_html}
              </div>
              <div class='mgt-compare-nav'>
                {mgt_compare_page_nav_html}
              </div>
            </div>
            <div class='mgt-compare-pager-summary'>{len(mgt_compare_page_groups)} pages | {len(mgt_source_output_diff_entries)} rows</div>
          </div>
          {mgt_compare_page_panels_html}
        </div>
        <div class='mgt-compare-list'>{mgt_source_output_compare_rows_html}</div>
      </div>
    </section>
    """
    mgt_verification_raw_tab_html = f"""
    <section class='mgt-tab-panel' data-mgt-tab-panel='raw' hidden>
      <div class='mgt-raw-diff-shell'>
        <div class='mgt-raw-diff-summary'>{mgt_export_source_output_mgt_summary_line}</div>
        <div class='mgt-raw-diff-metrics'>
          <div class='mgt-raw-diff-metric'><span>Source lines</span><strong>{mgt_export_source_output_mgt_source_meaningful_line_count}</strong></div>
          <div class='mgt-raw-diff-metric'><span>Output lines</span><strong>{mgt_export_source_output_mgt_output_meaningful_line_count}</strong></div>
          <div class='mgt-raw-diff-metric'><span>Changed / Added / Removed</span><strong>{mgt_export_source_output_mgt_changed_line_count} / {mgt_export_source_output_mgt_added_line_count} / {mgt_export_source_output_mgt_removed_line_count}</strong></div>
          <div class='mgt-raw-diff-metric'><span>Total delta</span><strong>{mgt_export_source_output_mgt_total_delta_count}</strong></div>
          <div class='mgt-raw-diff-metric'><span>Diff available</span><strong>{'yes' if mgt_export_source_output_mgt_diff_available else 'no'}</strong></div>
          <div class='mgt-raw-diff-metric'><span>Rows</span><strong>{len(mgt_source_output_raw_diff_lines)}</strong></div>
        </div>
        <div class='mgt-raw-diff-toolbar'>
          <input class='mgt-raw-diff-search' id='mgt-raw-diff-search' type='search' placeholder='raw diff line, card id, section id, token으로 필터'>
          <div class='mgt-raw-diff-count' id='mgt-raw-diff-count'>visible {len(mgt_source_output_raw_diff_lines)} / {len(mgt_source_output_raw_diff_lines)}</div>
        </div>
        {f"<pre class='mgt-raw-diff-preview'>{mgt_raw_diff_preview_combined}</pre>" if mgt_raw_diff_preview_combined else ""}
        <div class='mgt-raw-diff-list'>{mgt_source_output_raw_diff_lines_html}</div>
      </div>
    </section>
    """
    mgt_verification_artifacts_tab_html = f"""
    <section class='mgt-tab-panel' data-mgt-tab-panel='artifacts' hidden>
      <div class='mgt-verification-summary'>
        <div class='mgt-verification-summary-title'>Artifacts</div>
        <div class='mgt-verification-summary-line'>Source / output path links and support boundaries stay visible here for audit-friendly review.</div>
        <div class='mgt-console-grid'>
          <div class='mgt-console-kv'>
            <span>Source MGT</span>
            <strong title='{mgt_source_mgt_href or "n/a"}'>{mgt_source_mgt_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Optimized MGT</span>
            <strong title='{mgt_output_mgt_href or "n/a"}'>{mgt_output_mgt_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Roundtrip gate</span>
            <strong title='{midas_roundtrip_gate_report_href or "n/a"}'>{midas_roundtrip_gate_report_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Export report</span>
            <strong title='{mgt_export_report_href or "n/a"}'>{mgt_export_report_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Diff JSON</span>
            <strong title='{mgt_source_output_diff_json_href or "n/a"}'>{mgt_source_output_diff_json_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Diff TXT</span>
            <strong title='{mgt_source_output_diff_preview_href or "n/a"}'>{mgt_source_output_diff_preview_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Diff Window JSON</span>
            <strong title='{mgt_source_output_diff_window_json_href or "n/a"}'>{mgt_source_output_diff_window_json_href or "n/a"}</strong>
          </div>
          <div class='mgt-console-kv'>
            <span>Diff Window TXT</span>
            <strong title='{mgt_source_output_diff_window_preview_href or "n/a"}'>{mgt_source_output_diff_window_preview_href or "n/a"}</strong>
          </div>
        </div>
        <div class='mgt-verification-summary-note'>Core evidence: {mgt_export_native_authoring_summary_line}</div>
        <div class='mgt-verification-summary-note'>Diff artifacts: json={'yes' if mgt_export_source_output_mgt_diff_json_exists else 'no'} | txt={'yes' if mgt_export_source_output_mgt_diff_preview_exists else 'no'} | window_json={'yes' if mgt_export_source_output_mgt_diff_window_json_exists else 'no'} | window_txt={'yes' if mgt_export_source_output_mgt_diff_window_preview_exists else 'no'}</div>
        <div class='mgt-verification-summary-note'>Receipt: {mgt_export_source_output_mgt_verification_receipt_line}</div>
      </div>
      {mgt_artifact_tab_links_markup}
    </section>
    """
    mgt_verification_tabs_html = (
        mgt_verification_tab_buttons_html
        + "<div class='mgt-tab-panels'>"
        + mgt_verification_summary_tab_html
        + mgt_verification_compare_tab_html
        + mgt_verification_raw_tab_html
        + mgt_verification_artifacts_tab_html
        + "</div>"
    )
    mgt_export_badge_class = "is-pass" if mgt_export_contract_pass else "is-warn"
    mgt_export_badge_label = "contract=PASS" if mgt_export_contract_pass else f"contract={mgt_export_reason_code or 'CHECK'}"
    general_artifact_links_markup = render_link_pills(
        links=[
            {"label": "External Expert Mode", "href": expert_review_href},
            {"label": "Core viewer", "href": viewer_core_href},
            {"label": "Full viewer", "href": viewer_html_href},
            {"label": "Committee dashboard", "href": committee_dashboard_href},
            {"label": "Evidence gallery", "href": analysis_gallery_href},
            {"label": "Project registry", "href": project_registry_href},
            {"label": "Project package zip", "href": project_package_href},
            {"label": "Batch job report", "href": batch_job_report_href},
        ],
        container_class="link-row",
        quote="'",
    )
    mgt_verification_band_markup = render_token_row(
        items=[
            f"support={mgt_export_support_mode}",
            f"output .mgt {'yes' if mgt_export_output_mgt_exists else 'no'}",
            f"LOADCOMB {'exact' if mgt_export_loadcomb_roundtrip_pass else 'check'}",
            f"pending review {midas_roundtrip_gate_pending_review_total}",
        ],
        container_class="mgt-verification-band",
        item_class="mgt-verification-chip",
        quote="'",
    )
    def _toolbar_button(label: str, preset: str, icon_svg: str, *, active: bool = False) -> str:
        active_class = " is-active" if active else ""
        data_attr = f" data-camera-preset='{html.escape(preset)}'" if preset else " data-camera-reset"
        return (
            f"<button class='precision-button{active_class}' type='button'{data_attr}>"
            f"<span class='toolbar-icon' aria-hidden='true'>{icon_svg}</span>"
            f"<span class='toolbar-text'>{html.escape(label)}</span>"
            "</button>"
        )

    toolbar_buttons_html = "".join(
        [
            _toolbar_button(
                "Iso",
                "iso",
                "<svg viewBox='0 0 24 24' role='img'><path d='M4.5 8.2 12 4l7.5 4.2-7.5 4.3z'/><path d='M4.5 8.2v7.6L12 20l7.5-4.2V8.2'/><path d='M12 12.5V20'/><path d='M4.5 15.8 12 20l7.5-4.2'/></svg>",
                active=True,
            ),
            _toolbar_button(
                "Top",
                "top",
                "<svg viewBox='0 0 24 24' role='img'><path d='M4 6h16v12H4z'/><path d='M7 9h10'/><path d='M7 12h10'/><path d='M7 15h10'/><path d='M12 3.5v2.5'/></svg>",
            ),
            _toolbar_button(
                "Front",
                "front",
                "<svg viewBox='0 0 24 24' role='img'><path d='M5 5h14v14H5z'/><path d='M8 8h8'/><path d='M8 12h8'/><path d='M8 16h8'/><path d='M12 2.8v2.2'/></svg>",
            ),
            _toolbar_button(
                "Side",
                "side",
                "<svg viewBox='0 0 24 24' role='img'><path d='M6 5h12v14H6z'/><path d='M9 8h6'/><path d='M9 12h4.5'/><path d='M9 16h6'/><path d='M18 12.2h2.2'/></svg>",
            ),
            "<button class='precision-button' type='button' data-camera-flip-180 title='현재 3D 뷰를 Y축 기준으로 180도 회전합니다.'>"
            "<span class='toolbar-icon' aria-hidden='true'><svg viewBox='0 0 24 24' role='img'><path d='M12 4.5a7.5 7.5 0 1 1-5.3 2.2'/><path d='M7 4.5h5v5'/><path d='M12 19.5a7.5 7.5 0 0 0 5.3-2.2'/><path d='M17 19.5h-5v-5'/></svg></span>"
            "<span class='toolbar-text'>Flip 180</span>"
            "</button>",
            _toolbar_button(
                "Reset",
                "",
                "<svg viewBox='0 0 24 24' role='img'><path d='M12 4.5a7.5 7.5 0 1 1-5.3 2.2'/><path d='M7 4.5h5v5'/><path d='M12 10.5 9.8 8.3'/></svg>",
            ),
        ]
    )
    mgt_banner_state_class = "is-pass" if mgt_export_contract_pass else "is-warn"
    mgt_banner_state_label = "CONTRACT PASS" if mgt_export_contract_pass else f"CONTRACT {mgt_export_reason_code or 'CHECK'}"
    mgt_banner_title = "Optimized .mgt is ready" if mgt_export_contract_pass else "Optimized .mgt needs review"
    mgt_banner_subtitle = (
        f"{mgt_export_support_mode or 'n/a'} · supported={mgt_export_supported_change_count}/{mgt_export_total_change_count or max(mgt_export_supported_change_count, 1)}"
    )
    mgt_banner_meta = (
        f"output .mgt={'yes' if mgt_export_output_mgt_exists else 'no'} · "
        f"LOADCOMB={'exact' if mgt_export_loadcomb_roundtrip_pass else 'check'} · "
        f"combos={mgt_export_loadcomb_combo_count} · "
        f"direct_patch={mgt_export_direct_patch_change_count} ({mgt_export_direct_patch_change_ratio:.0%}) · "
        f"zero_touch={mgt_export_instruction_sidecar_zero_touch_verified_change_count} ({mgt_export_instruction_sidecar_zero_touch_verified_change_ratio:.0%}) · "
        f"breadth={midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)} · "
        f"public_native={midas_roundtrip_gate_public_native_ready_count} · "
        f"structural_preview={midas_roundtrip_gate_public_structural_preview_ready_count} · "
        f"exact={midas_roundtrip_gate_taxonomy_exact_count} canonical={midas_roundtrip_gate_taxonomy_canonical_count} · "
        f"pending_review={midas_roundtrip_gate_pending_review_total}"
    )
    mgt_first_banner_html = f"""
    <section class='mgt-first-banner'>
      <div class='mgt-first-banner-copy'>
        <div class='mgt-first-banner-kicker'>MGT EXPORT VERIFIED</div>
        <h2>{html.escape(mgt_banner_title)}</h2>
        <p>{html.escape(mgt_banner_subtitle)}</p>
        <div class='mgt-first-banner-meta'>{html.escape(mgt_banner_meta)}</div>
      </div>
      <div class='mgt-first-banner-status'>
        <span class='mgt-first-banner-pill {mgt_banner_state_class}'>{html.escape(mgt_banner_state_label)}</span>
        <span class='mgt-first-banner-pill'>output .mgt {"yes" if mgt_export_output_mgt_exists else "no"}</span>
        <span class='mgt-first-banner-pill'>LOADCOMB {"exact" if mgt_export_loadcomb_roundtrip_pass else "check"}</span>
      </div>
      <div class='mgt-first-banner-links'>
        {mgt_artifact_links_html}
      </div>
    </section>
    """
    leading_story_row = story_rows[0] if story_rows else {}

    def _drawing_sheet_line(label: str, value: Any) -> str:
        value_text = "n/a" if value in (None, "") else str(value)
        return (
            "<div class='drawing-sheet-line'>"
            f"<strong>{html.escape(label)}</strong>"
            f"<span>{value_text}</span>"
            "</div>"
        )

    def _projection_sheet_card(index: int, row: dict[str, Any]) -> str:
        baseline_href = str(row.get("baseline_svg_href", "") or "").strip()
        overlay_href = str(row.get("overlay_svg_href", "") or "").strip()
        links_html = ""
        empty_links_html = "<span class='drawing-sheet-empty'>No sheet assets available.</span>"
        if baseline_href:
            links_html += f"<a class='drawing-sheet-link' href='{html.escape(baseline_href)}'>Open baseline</a>"
        if overlay_href:
            links_html += f"<a class='drawing-sheet-link' href='{html.escape(overlay_href)}'>Open optimized</a>"
        link_block = links_html or empty_links_html
        return (
            "<article class='drawing-sheet-mini'>"
            "<div class='drawing-sheet-mini-head'>"
            f"<span class='drawing-sheet-mini-index'>Sheet {index + 1:02d}</span>"
            f"<span class='drawing-sheet-mini-label'>{html.escape(str(row.get('projection_label', '') or 'Sheet'))}</span>"
            "</div>"
            f"<div class='drawing-sheet-mini-note'>{html.escape(str(row.get('projection_note', '') or ''))}</div>"
            f"<div class='drawing-sheet-mini-links'>{link_block}</div>"
            "</article>"
        )

    projection_sheet_cards_html = "\n".join(
        _projection_sheet_card(index, row)
        for index, row in enumerate(projection_rows)
    ) or "<div class='drawing-sheet-empty'>No projection sheets were provided for this review package.</div>"
    real_drawing_registry_sheet_html = ""
    real_drawing_summary_card_html = ""
    if real_drawing_corpus["registered"]:
        ready_count = _safe_int(real_drawing_corpus["ready_count"])
        candidate_count = _safe_int(real_drawing_corpus["candidate_count"])
        ready_model_asset_count = _safe_int(real_drawing_corpus["ready_model_asset_count"])
        solver_exact_ready_count = _safe_int(real_drawing_corpus["solver_exact_ready_count"])
        proxy_or_preview_ready_count = _safe_int(real_drawing_corpus["proxy_or_preview_ready_count"])
        drawing_sheet_candidate_count = _safe_int(real_drawing_corpus["drawing_sheet_candidate_count"])
        project_count = _safe_int(real_drawing_corpus["project_count"])
        surface_label = html.escape(str(real_drawing_corpus["surface_label"] or "metadata-only"))
        real_drawing_registry_sheet_html = (
            "<article class='drawing-sheet-mini'>"
            "<div class='drawing-sheet-mini-head'>"
            "<span class='drawing-sheet-mini-index'>Corpus R00</span>"
            "<span class='drawing-sheet-mini-label'>Real drawing corpus</span>"
            "</div>"
            f"<div class='drawing-sheet-mini-note'>{ready_count}/{candidate_count or max(ready_count, 1)} intake-ready model files across {project_count} projects; "
            f"{drawing_sheet_candidate_count} drawing-sheet candidates are registered on a {surface_label} release surface.</div>"
            "<div class='drawing-sheet-mini-links'>"
            f"<span class='drawing-sheet-empty'>derived assets {ready_model_asset_count} | solver-exact {solver_exact_ready_count} | proxy/preview {proxy_or_preview_ready_count}</span>"
            "</div>"
            "</article>"
        )
        real_drawing_summary_card_html = f"""
    <article class='card'>
      <div class='card-label'>Real drawing corpus</div>
      <div class='card-value'>{ready_count}/{candidate_count or max(ready_count, 1)}</div>
      <div class='card-note'>{ready_model_asset_count} derived assets | solver-exact {solver_exact_ready_count} | {surface_label}</div>
    </article>"""

    external_expert_mode_html = f"""
    <section class='external-expert-mode'>
      <div class='external-expert-head'>
        <div>
          <div class='external-expert-kicker'>External Expert Mode</div>
          <h2>Sheet-style drawing package surface</h2>
          <p>Use this view for external structural review. It explains why the optimizer changed the package, shows the drawing sheets, and keeps validation evidence in reviewer language. Internal verification remains available below, but it is secondary in this mode.</p>
        </div>
        <div class='external-expert-summary'>
          <span class='external-expert-summary-pill'>Why changed first</span>
          <span class='external-expert-summary-pill'>Validation evidence next</span>
          <span class='external-expert-summary-pill'>Internal trace secondary</span>
        </div>
      </div>
      <div class='sheet-package-surface'>
        <article class='drawing-sheet is-wide'>
          <div class='drawing-sheet-head'>
            <div class='drawing-sheet-number'>Sheet 00</div>
            <div class='drawing-sheet-kicker'>Cover / scope</div>
          </div>
          <h3>{case_title}</h3>
          <p>{case_note or "baseline + optimized overlay"}</p>
          <div class='drawing-sheet-list'>
            {_drawing_sheet_line("Reviewer focus", "Why the package changed and what sheet set was delivered")}
            {_drawing_sheet_line("Status", status_label or "baseline + optimized overlay")}
            {_drawing_sheet_line("Export boundary", f"{mgt_export_support_mode} | {mgt_export_delivery_boundary}")}
            {_drawing_sheet_line("3D read order", "Plan -> Elevation -> Isometric -> validation evidence")}
          </div>
          <div class='drawing-sheet-legend'>External reviewers should read the package sheets first; internal verification appears below as a secondary trace surface.</div>
        </article>
        <article class='drawing-sheet'>
          <div class='drawing-sheet-head'>
            <div class='drawing-sheet-number'>Sheet 01</div>
            <div class='drawing-sheet-kicker'>Why changed</div>
          </div>
          <h3>Why this changed</h3>
          <p>Optimization is concentrated where the package is most overdesigned. The review surface emphasizes the strongest story bands and special-member families first so an external structural expert can read the design intent before the mechanics.</p>
          <div class='drawing-sheet-list'>
            {_drawing_sheet_line("Top story band", f"{html.escape(str(leading_story_row.get('story_band', '') or 'n/a'))} | zone {html.escape(str(leading_story_row.get('zone_label', '') or 'n/a'))} | cost {_safe_float(leading_story_row.get('cost_proxy_delta_sum', 0.0)):.3f}")}
            {_drawing_sheet_line("Member family", mgt_export_special_member_supported_action_family_label)}
            {_drawing_sheet_line("Direct patch lane", mgt_export_special_member_direct_patch_action_family_label)}
            {_drawing_sheet_line("Zero-touch lane", mgt_export_special_member_zero_touch_verified_action_family_label)}
          </div>
        </article>
        <article class='drawing-sheet'>
          <div class='drawing-sheet-head'>
            <div class='drawing-sheet-number'>Sheet 02</div>
            <div class='drawing-sheet-kicker'>Validation</div>
          </div>
          <h3>Validation evidence</h3>
          <p>External review should confirm the native export, roundtrip gate, and diff receipt together before treating the package as ready for sign-off.</p>
          <div class='drawing-sheet-list'>
            {_drawing_sheet_line("Native export", mgt_export_native_authoring_summary_line)}
            {_drawing_sheet_line("Roundtrip gate", mgt_export_loadcomb_roundtrip_summary_line)}
            {_drawing_sheet_line("Diff receipt", mgt_export_source_output_mgt_verification_receipt_line)}
            {_drawing_sheet_line("Native gate", midas_roundtrip_gate_summary_line)}
          </div>
        </article>
        <article class='drawing-sheet is-wide'>
          <div class='drawing-sheet-head'>
            <div class='drawing-sheet-number'>Sheet 03</div>
            <div class='drawing-sheet-kicker'>Drawing package index</div>
          </div>
          <h3>Drawing package index</h3>
          <p>The sheet set below exposes the plan, elevation, and isometric assets that correspond to the review package.</p>
          <div class='drawing-sheet-mini-grid'>
            {projection_sheet_cards_html}
            {real_drawing_registry_sheet_html}
          </div>
        </article>
      </div>
    </section>
    """
    route_context_banner_markup = render_route_context_banner(quote="'")
    drawing_hero_markup = render_split_hero(
        section_id="drawing-hero",
        main_markup=f"""      <div class='hero-kicker'>Structural Signal Desk | Optimized drawing review</div>
      <h1>{case_title}</h1>
      <p>{case_note}</p>
      <div class='hero-meta-row'>
        <div class='status'>{status_label or "baseline + optimized overlay"}</div>
        <span class='hero-meta-pill'>changed groups {_safe_int(payload.get("changed_group_count", 0))}</span>
        <span class='hero-meta-pill'>changed members {_safe_int(payload.get("changed_member_count", 0))}</span>
        <span class='hero-meta-pill'>max D/C {_safe_float(payload.get("max_dcr_after_max", 0.0)):.3f}</span>
      </div>
      {general_artifact_links_markup}""",
        side_markup=f"""      <div class='hero-side-kicker'>Review evidence routing</div>
      <div class='mgt-console mgt-verification-surface is-secondary'>
        <div class='mgt-console-head'>
          <div>
            <div class='mgt-console-kicker'>Internal verification surface</div>
            <h3>Traceable native export</h3>
          </div>
          <span class='mgt-console-badge {mgt_export_badge_class}'>{mgt_export_badge_label}</span>
        </div>
        {mgt_verification_band_markup}
        <div class='mgt-console-note mgt-console-note-secondary'>Kept for internal traceability. External experts should start with the sheet package above and only use this panel for native export audit details.</div>
        {mgt_verification_tabs_html}
        <div class='mgt-console-note'>Gate: {midas_roundtrip_gate_summary_line}</div>
        {f"<div class='mgt-console-note'>Export check: {mgt_export_reason or mgt_export_reason_code or 'PASS'}</div>" if not mgt_export_contract_pass else ""}
        {mgt_artifact_links_markup}
      </div>
      <div class='hero-side-copy'>
        <h2>Internal trace surface</h2>
        <p>Start with the package sheets above for external review. Use this lower-priority panel only when you need native export audit detail, roundtrip context, or the exact verification tabs.</p>
      </div>""",
        side_tag="aside",
        quote="'",
    )
    return f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Optimized Drawing Review</title>
<style>
{build_signal_desk_light_css()}
:root {{
  --soft-shadow:0 18px 34px rgba(28,36,48,.08);
  --soft-shadow-strong:0 22px 42px rgba(18,56,71,.14);
  --ui-border:rgba(28,36,48,.10);
  --text-on-dark:var(--surface-light-strong);
  --focus:#1b9bd1;
  --viewer-stage-ribbon-top:56px;
  --viewer-stage-compass-bottom:184px;
  --viewer-stage-overlay-bottom:12px;
  --viewer-chrome-glass:linear-gradient(180deg, rgba(12,24,35,.76), rgba(8,17,27,.66));
  --viewer-chrome-panel:linear-gradient(180deg, rgba(12,24,35,.84), rgba(8,17,27,.74));
  --viewer-chrome-border:rgba(232,241,245,.12);
  --viewer-chrome-border-strong:rgba(232,241,245,.18);
  --viewer-chrome-shadow:0 18px 34px rgba(0,0,0,.24);
  --viewer-chrome-shadow-strong:0 18px 36px rgba(0,0,0,.24);
  --viewer-chrome-inset:inset 0 1px 0 rgba(255,255,255,.06);
  --review-shell-bg:linear-gradient(135deg, rgba(255,253,248,.98) 0%, rgba(247,239,227,.94) 100%);
  --review-evidence-bg:linear-gradient(135deg, rgba(255,253,248,.98) 0%, rgba(232,244,244,.96) 52%, rgba(247,239,227,.94) 100%);
  --review-sheet-shadow:0 14px 28px rgba(82,63,29,.08);
}}
* {{ box-sizing:border-box; }}
html {{ overflow-x:hidden; }}
body {{
  margin:0;
  font-family:var(--font-ui);
  color:var(--ink);
  background:
    radial-gradient(circle at 18% 12%, rgba(255,255,255,0.88), rgba(255,255,255,0) 38%),
    radial-gradient(circle at 85% 8%, rgba(79,183,173,0.12), rgba(79,183,173,0) 28%),
    linear-gradient(180deg, #f7f1e8 0%, var(--bg) 100%);
}}
a {{ color:inherit; text-decoration:none; }}
.page {{ max-width:1600px; margin:0 auto; padding:32px 24px 72px; }}
.route-context-banner {{
  margin-bottom:16px;
  padding:18px 20px;
}}
.route-context-banner__eyebrow {{ color:var(--muted); }}
.route-context-banner__title {{ margin-top:6px; font-size:26px; font-weight:700; line-height:1.08; color:var(--ink); }}
.route-context-banner__meta {{ margin-top:10px; display:flex; flex-wrap:wrap; gap:8px; }}
.route-context-banner__meta span {{ box-shadow:inset 0 1px 0 rgba(255,255,255,.42); }}
.route-context-banner__note {{ margin-top:12px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; color:var(--muted); font-size:13px; }}
.route-context-banner__return {{
  display:inline-flex;
  align-items:center;
  font-weight:700;
}}
.route-focus-target {{
  outline:3px solid rgba(15,106,115,.42);
  outline-offset:6px;
  border-radius:18px;
  animation:routeFocusPulse 1.8s ease-out 1;
}}
.route-selection-target {{
  box-shadow:0 0 0 3px rgba(15,106,115,.28);
  animation:routeSelectionPulse 1.8s ease-out 1;
}}
@keyframes routeFocusPulse {{
  0% {{ box-shadow:0 0 0 0 rgba(15,106,115,.28); }}
  100% {{ box-shadow:0 0 0 18px rgba(15,106,115,0); }}
}}
@keyframes routeSelectionPulse {{
  0% {{ box-shadow:0 0 0 0 rgba(15,106,115,.24); }}
  100% {{ box-shadow:0 0 0 14px rgba(15,106,115,0); }}
}}
.case-shell {{
  border-radius:var(--radius-xl);
  border:1px solid var(--ui-border);
  background:var(--review-shell-bg);
  color:var(--ink);
  padding:16px 18px;
  margin-bottom:16px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:14px;
  box-shadow:var(--soft-shadow);
  position:relative;
  overflow:hidden;
}}
.case-shell::after {{
  content:'';
  position:absolute;
  inset:0;
  background:
    linear-gradient(90deg, rgba(255,255,255,.60) 0, rgba(255,255,255,0) 22%),
    linear-gradient(180deg, rgba(255,255,255,.28) 0, rgba(255,255,255,0) 42%);
  pointer-events:none;
}}
.case-shell strong {{
  font-family:var(--font-display);
  font-size:18px;
  line-height:1.08;
  letter-spacing:-0.02em;
}}
.status-chip {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  min-height:34px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  background:var(--surface-light-strong);
  border:1px solid var(--review-pill-border);
  color:var(--review-pill-ink);
  font-size:11px;
  font-weight:700;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.56);
}}
.mgt-first-banner {{
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:18px;
  align-items:center;
  padding:22px 24px;
  margin:16px 0 20px;
  border-radius:var(--radius-xl);
  border:1px solid rgba(15,106,115,.28);
  background:var(--review-evidence-bg);
  color:var(--ink);
  box-shadow:var(--soft-shadow);
  position:relative;
  overflow:hidden;
}}
.mgt-first-banner::before {{
  content:'';
  position:absolute;
  inset:0;
  background:
    linear-gradient(90deg, rgba(255,255,255,.62) 0, rgba(255,255,255,0) 24%),
    linear-gradient(180deg, rgba(255,255,255,.22) 0, rgba(255,255,255,0) 44%);
  pointer-events:none;
}}
.mgt-first-banner-copy {{
  position:relative;
  z-index:1;
  min-width:0;
}}
.mgt-first-banner-kicker {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  color:var(--brand);
}}
.mgt-first-banner h2 {{
  margin:8px 0 8px;
  font-family:var(--font-display);
  font-size:32px;
  line-height:1.08;
  letter-spacing:-0.03em;
  color:var(--ink);
}}
.mgt-first-banner p {{
  margin:0;
  font-size:14px;
  line-height:1.65;
  color:var(--muted);
}}
.mgt-first-banner-meta {{
  margin-top:12px;
  font-size:12px;
  line-height:1.5;
  color:var(--review-meta-ink);
  font-variant-numeric:tabular-nums;
}}
.mgt-first-banner-status {{
  display:flex;
  flex-wrap:wrap;
  justify-content:flex-end;
  gap:10px;
  position:relative;
  z-index:1;
  min-width:0;
}}
.mgt-first-banner-pill {{
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  background:var(--surface-light-strong);
  border:1px solid var(--review-pill-border);
  color:var(--review-pill-ink);
  font-size:11px;
  font-weight:800;
  letter-spacing:.04em;
  text-transform:uppercase;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.58);
}}
.mgt-first-banner-pill.is-pass {{
  background:rgba(47,125,90,.12);
  border-color:rgba(47,125,90,.20);
  color:var(--success);
}}
.mgt-first-banner-pill.is-warn {{
  background:var(--review-pill-warm-bg);
  border-color:var(--review-pill-warm-border);
  color:var(--review-pill-warm-ink);
}}
.mgt-first-banner-links {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:14px;
  position:relative;
  z-index:1;
  grid-column:1 / -1;
  min-width:0;
}}
.hero {{
  display:grid;
  grid-template-columns:1.25fr .95fr;
  gap:20px;
  align-items:stretch;
  min-width:0;
}}
.hero > * {{
  min-width:0;
  max-width:100%;
}}
.hero-main {{
  padding:30px;
  background:
    radial-gradient(circle at 20% 0%, rgba(255,255,255,.18), rgba(255,255,255,0) 34%),
    var(--review-hero-bg);
  color:#f5fbfb;
  position:relative;
  overflow:hidden;
}}
.hero-main::before {{
  content:'';
  position:absolute;
  inset:0;
  background:
    linear-gradient(90deg, rgba(255,255,255,.08) 0, rgba(255,255,255,0) 18%),
    linear-gradient(180deg, rgba(255,255,255,.05) 0, rgba(255,255,255,0) 46%);
  pointer-events:none;
}}
.hero-main h1 {{
  margin:0 0 12px;
  font-size:var(--type-h1-size);
  line-height:var(--type-h1-line-height);
  letter-spacing:var(--type-h1-tracking);
  overflow-wrap:anywhere;
}}
.hero-kicker {{
  margin-bottom:12px;
  color:#cdebed;
}}
.hero-main p {{ margin:0; max-width:64ch; font-size:15px; line-height:1.72; color:#d7edf0; overflow-wrap:anywhere; }}
.hero-meta-row {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:18px;
}}
.hero-main .status {{
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  background:rgba(255,255,255,.12);
  border:1px solid rgba(255,255,255,.18);
  font-size:12px;
  font-weight:700;
}}
.hero-meta-pill {{
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  background:rgba(255,255,255,.10);
  border:1px solid rgba(255,255,255,.14);
  color:#eef8f9;
  font-size:12px;
  font-weight:700;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.08);
}}
.hero-side {{
  padding:24px;
  color:var(--ink);
  overflow:hidden;
}}
.hero-side-kicker {{ color:var(--brand); }}
.hero-side-copy {{ margin-top:18px; display:grid; gap:10px; }}
.hero-side h2 {{ margin:0; color:var(--ink); }}
.hero-side p {{ margin:0; color:var(--muted); }}
.link-row {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:18px;
}}
.link-pill {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:36px;
  padding:0 14px;
  background:rgba(255,255,255,.14);
  border:1px solid rgba(255,255,255,.18);
  color:#f5fbfb;
  font-size:12px;
  font-weight:700;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.06);
}}
.mgt-console {{
  margin-top:16px;
  padding:16px;
  border-radius:var(--radius-lg);
  background:linear-gradient(180deg, rgba(8,18,27,.88) 0%, rgba(16,26,36,.94) 100%);
  border:1px solid rgba(128,154,175,.22);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.05);
  max-width:100%;
  min-width:0;
  overflow:hidden;
}}
.mgt-console-head {{
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  gap:10px;
  align-items:flex-start;
  min-width:0;
}}
.mgt-console-kicker {{
  font-size:10px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
  color:#7dd0d6;
}}
.mgt-console h3 {{
  margin:6px 0 0;
  font-size:22px;
  line-height:1.08;
  letter-spacing:-0.03em;
  color:#f5fbfb;
}}
.mgt-console-badge {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:6px 10px;
  border-radius:999px;
  font-size:10px;
  font-weight:800;
  letter-spacing:.10em;
  text-transform:uppercase;
  border:1px solid transparent;
  white-space:nowrap;
}}
.mgt-console-badge.is-pass {{
  background:rgba(28,122,79,.18);
  border-color:rgba(28,122,79,.34);
  color:#9ff0c4;
}}
.mgt-console-badge.is-warn {{
  background:rgba(201,109,44,.16);
  border-color:rgba(201,109,44,.32);
  color:#ffd3b2;
}}
.mgt-console-grid {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
  min-width:0;
}}
.mgt-console-kv {{
  min-height:78px;
  padding:12px 12px 11px;
  border-radius:16px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.10);
  min-width:0;
}}
.mgt-console-kv span {{
  display:block;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:#8fa5b2;
  margin-bottom:8px;
}}
.mgt-console-kv strong {{
  display:block;
  font-size:12px;
  line-height:1.45;
  color:#edf6f9;
  word-break:break-word;
}}
.mgt-console-note {{
  margin-top:12px;
  padding:10px 12px;
  border-radius:14px;
  border:1px solid rgba(125,208,214,.14);
  background:rgba(125,208,214,.06);
  color:#d5edf1;
  font-size:12px;
  line-height:1.55;
  min-width:0;
  overflow-wrap:anywhere;
}}
.mgt-console-note code {{
  color:#9ff0c4;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}}
.mgt-verification-surface {{
  display:grid;
  gap:12px;
  min-width:0;
}}
.mgt-verification-surface.is-secondary {{
  opacity:.92;
  background:linear-gradient(180deg, rgba(8,18,27,.82) 0%, rgba(16,26,36,.90) 100%);
  border-color:rgba(128,154,175,.16);
}}
.mgt-verification-surface.is-secondary .mgt-console-kicker {{
  color:#8fa5b2;
}}
.mgt-verification-surface.is-secondary .mgt-console h3 {{
  font-size:18px;
  color:#e3eef3;
}}
.mgt-console-note-secondary {{
  background:rgba(255,255,255,.04);
  border-color:rgba(255,255,255,.08);
  color:#c7d6df;
}}
.external-expert-mode {{
  margin-top:24px;
  padding:24px;
  border-radius:var(--radius-xl);
  border:1px solid rgba(15,106,115,.16);
  background:
    radial-gradient(circle at 16% 14%, rgba(255,255,255,.84), rgba(255,255,255,0) 34%),
    linear-gradient(180deg, rgba(255,253,248,.98) 0%, rgba(247,239,227,.96) 100%);
  box-shadow:var(--soft-shadow);
  color:var(--ink);
}}
.external-expert-head {{
  display:flex;
  justify-content:space-between;
  gap:18px;
  align-items:flex-start;
}}
.external-expert-kicker {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  color:var(--brand);
}}
.external-expert-mode h2 {{
  margin:8px 0 10px;
  font-size:28px;
  line-height:1.08;
  letter-spacing:-0.04em;
  color:var(--ink);
}}
.external-expert-mode p {{
  margin:0;
  max-width:980px;
  color:var(--muted);
  font-size:14px;
  line-height:1.7;
}}
.external-expert-summary {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  justify-content:flex-end;
  align-items:flex-start;
}}
.external-expert-summary-pill {{
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  background:var(--surface-light-strong);
  border:1px solid var(--review-pill-warm-border);
  color:var(--review-pill-warm-ink);
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.72);
}}
.sheet-package-surface {{
  display:grid;
  grid-template-columns:repeat(12, minmax(0, 1fr));
  gap:14px;
  margin-top:18px;
}}
.drawing-sheet {{
  grid-column:span 6;
  padding:18px 18px 16px;
  border-radius:var(--radius-lg);
  background:var(--review-panel-bg);
  border:1px solid rgba(15,106,115,.12);
  box-shadow:var(--review-sheet-shadow);
  position:relative;
  overflow:hidden;
}}
.drawing-sheet::before {{
  content:'';
  position:absolute;
  inset:0;
  background:
    linear-gradient(135deg, rgba(255,255,255,.58) 0, rgba(255,255,255,0) 28%),
    linear-gradient(180deg, rgba(255,255,255,.10) 0, rgba(255,255,255,0) 44%);
  pointer-events:none;
}}
.drawing-sheet.is-wide {{
  grid-column:span 12;
}}
.drawing-sheet-head {{
  display:flex;
  justify-content:space-between;
  gap:10px;
  align-items:flex-start;
  position:relative;
  z-index:1;
}}
.drawing-sheet-number {{
  display:inline-flex;
  align-items:center;
  min-height:30px;
  padding:0 10px;
  border-radius:var(--radius-pill);
  background:var(--review-pill-bg);
  border:1px solid var(--review-pill-border);
  color:var(--review-pill-ink);
  font-size:10px;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.drawing-sheet-kicker {{
  color:var(--review-meta-ink);
  font-size:10px;
  font-weight:800;
  letter-spacing:.14em;
  text-transform:uppercase;
  text-align:right;
}}
.drawing-sheet h3 {{
  position:relative;
  z-index:1;
  margin:10px 0 8px;
  font-family:var(--font-display);
  font-size:22px;
  line-height:1.08;
  letter-spacing:-0.04em;
  color:var(--ink);
}}
.drawing-sheet p {{
  position:relative;
  z-index:1;
  margin:0;
  color:var(--muted);
  font-size:13px;
  line-height:1.65;
}}
.drawing-sheet-list {{
  position:relative;
  z-index:1;
  display:grid;
  gap:8px;
  margin-top:14px;
}}
.drawing-sheet-line {{
  display:grid;
  grid-template-columns:minmax(0, .42fr) minmax(0, 1fr);
  gap:8px;
  padding:10px 11px;
  border-radius:var(--radius-sm);
  background:rgba(255,255,255,.64);
  border:1px solid rgba(15,106,115,.10);
}}
.drawing-sheet-line strong {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--review-meta-ink);
}}
.drawing-sheet-line span {{
  font-size:12px;
  line-height:1.45;
  color:var(--ink);
  word-break:break-word;
}}
.drawing-sheet-legend {{
  position:relative;
  z-index:1;
  margin-top:12px;
  font-size:11px;
  color:var(--review-meta-ink);
  letter-spacing:.02em;
}}
.drawing-sheet-mini-grid {{
  position:relative;
  z-index:1;
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
}}
.drawing-sheet-mini {{
  padding:12px;
  border-radius:var(--radius-md);
  background:rgba(255,255,255,.68);
  border:1px solid rgba(15,106,115,.10);
  display:grid;
  gap:8px;
}}
.drawing-sheet-mini-head {{
  display:flex;
  justify-content:space-between;
  gap:8px;
  align-items:flex-start;
}}
.drawing-sheet-mini-index {{
  display:inline-flex;
  align-items:center;
  min-height:28px;
  padding:0 9px;
  border-radius:var(--radius-pill);
  background:var(--review-pill-warm-bg);
  border:1px solid var(--review-pill-warm-border);
  color:var(--review-pill-warm-ink);
  font-size:10px;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.drawing-sheet-mini-label {{
  color:var(--ink);
  font-size:12px;
  font-weight:800;
  letter-spacing:.01em;
  text-align:right;
}}
.drawing-sheet-mini-note {{
  color:var(--muted);
  font-size:12px;
  line-height:1.5;
}}
.drawing-sheet-mini-links {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}}
.drawing-sheet-link {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:30px;
  padding:0 10px;
  border-radius:var(--radius-pill);
  border:1px solid rgba(15,106,115,.14);
  background:rgba(255,255,255,.84);
  color:var(--brand);
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.drawing-sheet-link:hover {{
  border-color:rgba(15,106,115,.24);
  color:var(--brand);
}}
.drawing-sheet-empty {{
  margin-top:14px;
  padding:12px 14px;
  border-radius:var(--radius-md);
  border:1px dashed rgba(15,106,115,.22);
  background:rgba(255,255,255,.48);
  color:var(--review-meta-ink);
  font-size:12px;
}}
.mgt-verification-band {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:14px;
  min-width:0;
}}
.mgt-verification-chip {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:999px;
  border:1px solid rgba(125,208,214,.18);
  background:rgba(125,208,214,.08);
  color:#d8eef1;
  font-size:10px;
  font-weight:800;
  letter-spacing:.10em;
  text-transform:uppercase;
}}
.mgt-verification-grid {{
  display:grid;
  grid-template-columns:minmax(0, 1fr) minmax(0, .92fr);
  gap:12px;
  align-items:start;
  min-width:0;
}}
.mgt-tab-strip {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:14px;
  min-width:0;
}}
.mgt-tab-button {{
  appearance:none;
  border:1px solid rgba(166,181,196,.20);
  background:rgba(255,255,255,.06);
  color:#d5edf1;
  border-radius:12px;
  padding:7px 11px;
  font:inherit;
  font-size:11px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  cursor:pointer;
  transition:background .12s ease, border-color .12s ease, transform .12s ease, box-shadow .12s ease;
}}
.mgt-tab-button:hover {{
  background:rgba(255,255,255,.09);
  border-color:rgba(159,184,196,.36);
  transform:translateY(-1px);
}}
.mgt-tab-button.is-active {{
  background:linear-gradient(180deg, rgba(23,127,137,.96) 0%, rgba(16,92,102,.96) 100%);
  border-color:#1b97a2;
  color:#f5fbfb;
  box-shadow:0 10px 20px rgba(15,106,115,.18);
}}
.mgt-tab-button:focus-visible {{
  outline:2px solid rgba(15,155,209,.32);
  outline-offset:2px;
}}
.mgt-tab-panels {{
  margin-top:12px;
  min-width:0;
}}
.mgt-tab-panel {{
  display:none;
}}
.mgt-tab-panel.is-active {{
  display:block;
}}
.mgt-verification-summary,
.mgt-diff-panel {{
  padding:14px;
  border-radius:16px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.10);
  min-width:0;
  max-width:100%;
  overflow:hidden;
}}
.mgt-verification-summary {{
  display:grid;
  gap:10px;
}}
.mgt-verification-summary-title {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#7dd0d6;
  font-weight:800;
}}
.mgt-verification-summary-line {{
  font-size:13px;
  line-height:1.55;
  color:#edf6f9;
  word-break:break-word;
}}
.mgt-verification-summary-note {{
  font-size:12px;
  line-height:1.55;
  color:#d5edf1;
}}
.mgt-diff-panel {{
  display:grid;
  gap:10px;
}}
.mgt-diff-panel-head {{
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  align-items:center;
  gap:8px;
  min-width:0;
}}
.mgt-diff-panel-kicker {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#7dd0d6;
  font-weight:800;
}}
.mgt-diff-panel-count {{
  display:inline-flex;
  align-items:center;
  padding:4px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.10);
  color:#d7ebef;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.mgt-diff-summary {{
  padding:8px 10px;
  border-radius:12px;
  background:rgba(125,208,214,.08);
  border:1px solid rgba(125,208,214,.16);
  color:#d9f3f7;
  font-size:12px;
  line-height:1.55;
}}
.mgt-diff-row {{
  padding-top:10px;
  border-top:1px solid rgba(255,255,255,.08);
}}
.mgt-diff-row-head {{
  display:flex;
  justify-content:space-between;
  gap:10px;
  align-items:center;
}}
.mgt-diff-label {{
  font-size:12px;
  font-weight:800;
  color:#edf6f9;
}}
.mgt-diff-value {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:4px 8px;
  border-radius:999px;
  border:1px solid transparent;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  white-space:nowrap;
}}
.mgt-diff-value.is-good {{
  background:rgba(28,122,79,.18);
  border-color:rgba(28,122,79,.34);
  color:#a6efc7;
}}
.mgt-diff-value.is-warn {{
  background:rgba(201,109,44,.18);
  border-color:rgba(201,109,44,.34);
  color:#ffd7ba;
}}
.mgt-diff-value.is-neutral {{
  background:rgba(255,255,255,.06);
  border-color:rgba(255,255,255,.12);
  color:#dbe9ed;
}}
.mgt-diff-value.is-bad {{
  background:rgba(154,55,55,.18);
  border-color:rgba(154,55,55,.34);
  color:#ffc8c8;
}}
.mgt-diff-note {{
  margin-top:6px;
  font-size:11px;
  line-height:1.5;
  color:#a9c2cf;
}}
.mgt-diff-empty {{
  padding:10px 12px;
  border-radius:12px;
  border:1px dashed rgba(125,208,214,.24);
  background:rgba(125,208,214,.05);
  color:#c0d7df;
  font-size:12px;
  line-height:1.55;
}}
.mgt-compare-panel {{
  display:grid;
  gap:10px;
  padding:14px;
  border-radius:16px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.10);
  min-width:0;
  overflow:hidden;
}}
.mgt-compare-summary {{
  padding:10px 12px;
  border-radius:12px;
  background:rgba(15,106,115,.10);
  border:1px solid rgba(125,208,214,.14);
  color:#d6f0f3;
  font-size:12px;
  line-height:1.55;
}}
.mgt-compare-preview {{
  padding:12px 14px;
  border-radius:14px;
  background:rgba(8,18,27,.66);
  border:1px solid rgba(255,255,255,.08);
  color:#dbe9ed;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
  white-space:pre-wrap;
  word-break:break-word;
  max-height:180px;
  overflow:auto;
}}
.mgt-compare-sheet {{
  display:grid;
  gap:10px;
  padding:14px;
  border-radius:16px;
  background:rgba(7,14,22,.66);
  border:1px solid rgba(125,208,214,.12);
  box-shadow:0 18px 40px rgba(0,0,0,.16);
  min-width:0;
  overflow:hidden;
}}
.mgt-compare-sheet-head {{
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  gap:12px;
  align-items:flex-end;
  min-width:0;
}}
.mgt-compare-sheet-kicker {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#7dd0d6;
  font-weight:800;
}}
.mgt-compare-sheet-note {{
  font-size:12px;
  line-height:1.5;
  color:#aec7d1;
  text-align:right;
}}
.mgt-compare-pager-dock {{
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:12px;
  align-items:center;
  padding:10px 12px;
  border-radius:14px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-pager-cluster {{
  display:grid;
  gap:10px;
  min-width:0;
}}
.mgt-compare-pager {{
  display:flex;
  gap:8px;
  flex-wrap:wrap;
}}
.mgt-compare-nav {{
  display:flex;
  gap:8px;
  flex-wrap:wrap;
}}
.mgt-compare-nav-button {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:64px;
  padding:7px 11px;
  border-radius:10px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(9,18,27,.72);
  color:#a9c0ca;
  font-size:10px;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
  cursor:pointer;
}}
.mgt-compare-nav-button:hover {{
  border-color:rgba(125,208,214,.28);
  color:#dff3f6;
}}
.mgt-compare-nav-button:disabled {{
  opacity:.38;
  cursor:not-allowed;
}}
.mgt-compare-page-tab {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:12px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(12,22,32,.68);
  color:#b8ccd4;
  font-size:11px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
  cursor:pointer;
}}
.mgt-compare-page-tab.is-active {{
  border-color:rgba(240,90,40,.48);
  background:rgba(240,90,40,.12);
  color:#fff2ea;
  box-shadow:0 0 0 1px rgba(240,90,40,.16);
}}
.mgt-compare-page-tab-count {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:26px;
  height:20px;
  padding:0 6px;
  border-radius:999px;
  background:rgba(255,255,255,.08);
  color:inherit;
  font-size:10px;
  letter-spacing:.04em;
}}
.mgt-compare-pager-summary {{
  color:#8ca3af;
  font-size:11px;
  font-weight:700;
  letter-spacing:.06em;
  text-transform:uppercase;
}}
.mgt-compare-page-panel {{
  display:grid;
  gap:10px;
  min-width:0;
}}
.mgt-compare-page-panel[hidden] {{
  display:none;
}}
.mgt-compare-page-text-grid {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
}}
.mgt-compare-page-text-panel {{
  display:grid;
  gap:8px;
  padding:12px;
  border-radius:14px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-page-text-label {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#8ca3af;
  font-weight:800;
}}
.mgt-compare-page-text-code {{
  margin:0;
  max-height:240px;
  overflow:auto;
  white-space:pre;
  color:#edf6f9;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
}}
.mgt-compare-page {{
  display:grid;
  gap:12px;
  max-height:520px;
  overflow:auto;
  padding-right:4px;
}}
.mgt-compare-page-row {{
  display:grid;
  grid-template-columns:180px minmax(0, 1fr);
  gap:12px;
  padding:12px;
  border-radius:14px;
  background:rgba(8,18,27,.42);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-page-row[data-exact-member-id-match='true'] {{
  border-color:rgba(240,90,40,.36);
  box-shadow:0 0 0 1px rgba(240,90,40,.10);
}}
.mgt-compare-page-row.is-focused {{
  border-color:rgba(240,90,40,.52);
  box-shadow:0 0 0 2px rgba(240,90,40,.14), 0 12px 24px rgba(10,18,27,.24);
}}
.mgt-compare-page-row.is-match {{
  border-color:rgba(240,90,40,.32);
  box-shadow:0 0 0 1px rgba(240,90,40,.10);
}}
.mgt-compare-page-row.is-dim {{
  opacity:.44;
}}
.mgt-compare-page-row:hover {{
  border-color:rgba(125,208,214,.28);
  cursor:pointer;
}}
.mgt-compare-row:hover {{
  border-color:rgba(125,208,214,.28);
  cursor:pointer;
}}
.mgt-compare-page-rail {{
  display:grid;
  gap:8px;
  align-content:start;
}}
.mgt-compare-page-index {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:max-content;
  padding:4px 9px;
  border-radius:999px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.10);
  color:#d7ebef;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
}}
.mgt-compare-page-member {{
  color:#edf6f9;
  font-size:12px;
  font-weight:800;
  letter-spacing:.03em;
}}
.mgt-compare-page-meta {{
  color:#97adba;
  font-size:11px;
  line-height:1.45;
}}
.mgt-compare-page-split {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  min-width:0;
}}
.mgt-compare-page-side {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-page-side-label {{
  margin-bottom:8px;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#8ca3af;
  font-weight:800;
}}
.mgt-compare-page-code {{
  margin:0;
  white-space:pre-wrap;
  word-break:break-word;
  color:#edf6f9;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
}}
.mgt-compare-list {{
  display:grid;
  gap:10px;
}}
.mgt-compare-row {{
  padding:12px;
  border-radius:14px;
  background:rgba(8,18,27,.38);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-row.is-focused {{
  border-color:rgba(240,90,40,.52);
  box-shadow:0 0 0 2px rgba(240,90,40,.14), 0 12px 24px rgba(10,18,27,.24);
}}
.mgt-compare-row.is-match {{
  border-color:rgba(240,90,40,.32);
  box-shadow:0 0 0 1px rgba(240,90,40,.10);
}}
.mgt-compare-row.is-dim {{
  opacity:.48;
}}
.mgt-compare-row-head {{
  display:flex;
  flex-wrap:wrap;
  justify-content:space-between;
  gap:10px;
  align-items:center;
  margin-bottom:10px;
  min-width:0;
}}
.mgt-compare-row-kicker {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#7dd0d6;
  font-weight:800;
}}
.mgt-compare-row-meta {{
  font-size:11px;
  color:#a9c2cf;
  text-align:right;
}}
.mgt-compare-split {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  min-width:0;
}}
.mgt-compare-side {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-compare-side-label {{
  margin-bottom:8px;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#8ca3af;
  font-weight:800;
}}
.mgt-compare-code {{
  margin:0;
  white-space:pre-wrap;
  word-break:break-word;
  color:#edf6f9;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
}}
.mgt-raw-diff-line.is-match {{
  border-color:rgba(240,90,40,.48);
  box-shadow:0 0 0 2px rgba(240,90,40,.12);
}}
.mgt-raw-diff-line.is-dim {{
  opacity:.42;
}}
.mgt-raw-diff-line.is-focused {{
  border-color:rgba(240,90,40,.64);
  box-shadow:0 0 0 2px rgba(240,90,40,.16);
}}
.mgt-raw-diff-shell {{
  display:grid;
  gap:10px;
  min-width:0;
  overflow:hidden;
}}
.mgt-raw-diff-summary {{
  padding:12px 14px;
  border-radius:14px;
  background:rgba(15,106,115,.10);
  border:1px solid rgba(125,208,214,.14);
  color:#d6f0f3;
  font-size:12px;
  line-height:1.55;
}}
.mgt-raw-diff-metrics {{
  display:grid;
  grid-template-columns:repeat(3, minmax(0, 1fr));
  gap:8px;
}}
.mgt-raw-diff-metric {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
}}
.mgt-raw-diff-metric span {{
  display:block;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:#8ca3af;
  margin-bottom:6px;
}}
.mgt-raw-diff-metric strong {{
  display:block;
  color:#edf6f9;
  font-size:13px;
  line-height:1.35;
}}
.mgt-raw-diff-preview {{
  margin:0;
  max-height:220px;
  overflow:auto;
  padding:12px 14px;
  border-radius:14px;
  background:rgba(8,18,27,.66);
  border:1px solid rgba(255,255,255,.08);
  color:#dbe9ed;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
  white-space:pre-wrap;
  word-break:break-word;
}}
.mgt-raw-diff-toolbar {{
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:10px;
  align-items:center;
}}
.mgt-raw-diff-search {{
  width:100%;
  border:1px solid rgba(255,255,255,.10);
  border-radius:12px;
  padding:10px 12px;
  background:rgba(8,18,27,.52);
  color:#edf6f9;
  font:inherit;
  font-size:12px;
}}
.mgt-raw-diff-search::placeholder {{
  color:#8ca3af;
}}
.mgt-raw-diff-search:focus {{
  outline:none;
  border-color:rgba(15,155,209,.42);
  box-shadow:0 0 0 3px rgba(15,155,209,.12);
}}
.mgt-raw-diff-count {{
  display:inline-flex;
  align-items:center;
  padding:8px 10px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.10);
  color:#d7ebef;
  font-size:11px;
  font-weight:800;
  letter-spacing:.04em;
  white-space:nowrap;
}}
.mgt-raw-diff-list {{
  display:grid;
  gap:8px;
  max-height:320px;
  overflow:auto;
  padding-right:4px;
}}
.mgt-raw-diff-line {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(10,18,27,.42);
  border:1px solid rgba(255,255,255,.08);
  transition:opacity .12s ease, border-color .12s ease, box-shadow .12s ease;
}}
.mgt-raw-diff-line-shell {{
  display:grid;
  grid-template-columns:56px minmax(0, 1fr);
  gap:10px;
  align-items:start;
}}
.mgt-raw-diff-line.is-replace {{
  border-left:3px solid rgba(15,155,209,.64);
}}
.mgt-raw-diff-line.is-insert {{
  border-left:3px solid rgba(28,122,79,.64);
}}
.mgt-raw-diff-line.is-delete {{
  border-left:3px solid rgba(201,109,44,.64);
}}
.mgt-raw-diff-line.is-neutral {{
  border-left:3px solid rgba(255,255,255,.18);
}}
.mgt-raw-diff-marker {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:42px;
  padding:4px 7px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.12);
  color:#dbe9ed;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.mgt-raw-diff-line code {{
  display:block;
  white-space:pre-wrap;
  word-break:break-word;
  color:#edf6f9;
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size:11px;
  line-height:1.55;
}}
.cards {{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:16px;
  margin-top:20px;
}}
.card {{
  padding:18px;
  border-radius:var(--radius-lg);
  background:var(--review-panel-bg);
  border:1px solid rgba(15,106,115,.12);
  box-shadow:var(--soft-shadow);
  position:relative;
  overflow:hidden;
}}
.card::before {{
  content:'';
  position:absolute;
  inset:0;
  background:linear-gradient(180deg, rgba(255,255,255,0.65) 0%, rgba(255,255,255,0) 44%);
  pointer-events:none;
}}
.card-label {{
  color:var(--muted);
}}
.card-value {{
  margin-top:8px;
  color:var(--ink);
}}
.card-note {{
  margin-top:8px;
  font-size:13px;
  color:var(--muted);
}}
.section {{
  margin-top:24px;
  padding:24px;
  border-radius:var(--radius-xl);
  background:var(--review-panel-quiet-bg);
  border:1px solid rgba(15,106,115,.12);
  box-shadow:var(--soft-shadow);
  position:relative;
}}
.section h2 {{
  margin:0 0 8px;
  color:var(--ink);
}}
.section .lead {{
  margin:0;
  font-size:14px;
  line-height:1.7;
  color:var(--muted);
}}
.projection-tabs {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:18px;
}}
.precision-toolbar {{
  display:grid;
  grid-template-columns:minmax(0, 1fr) auto;
  gap:14px;
  align-items:center;
  margin-top:16px;
  padding:14px 16px;
  border-radius:22px;
  background:
    radial-gradient(circle at 16% 10%, rgba(33,95,108,.18), rgba(33,95,108,0) 42%),
    linear-gradient(180deg, rgba(14,22,31,.96) 0%, rgba(23,34,47,.96) 100%);
  border:1px solid rgba(129,151,168,.26);
  box-shadow:0 14px 30px rgba(13,18,24,.14);
  color:#e7f1f4;
}}
.toolbar-group {{
  display:flex;
  flex-direction:column;
  gap:8px;
}}
.toolbar-label {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#8db8c3;
}}
.precision-actions {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}}
.precision-button {{
  appearance:none;
  border:1px solid rgba(166,181,196,.26);
  cursor:pointer;
  padding:8px 12px;
  border-radius:14px;
  background:linear-gradient(180deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.03) 100%);
  color:#ecf4f7;
  font:inherit;
  font-size:12px;
  font-weight:700;
  transition:background .12s ease, border-color .12s ease, color .12s ease, transform .12s ease, box-shadow .12s ease;
  position:relative;
  display:inline-flex;
  align-items:center;
  gap:8px;
  min-height:36px;
}}
.precision-button:hover {{
  border-color:rgba(159,184,196,.48);
  background:rgba(255,255,255,.09);
  transform:translateY(-1px);
}}
.precision-button:focus-visible {{
  outline:2px solid rgba(15,155,209,.38);
  outline-offset:2px;
}}
.precision-button.is-active {{
  background:linear-gradient(180deg, #197a82 0%, #0f5b62 100%);
  border-color:#1b97a2;
  color:#f5fbfb;
  box-shadow:0 10px 22px rgba(15,106,115,.28);
}}
.toolbar-icon {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  width:15px;
  height:15px;
}}
.toolbar-icon svg {{
  width:15px;
  height:15px;
  stroke:currentColor;
  fill:none;
  stroke-linecap:round;
  stroke-linejoin:round;
  stroke-width:1.5;
  vector-effect:non-scaling-stroke;
}}
.toolbar-text {{
  line-height:1;
}}
.sync-toggle {{
  display:inline-flex;
  gap:8px;
  align-items:center;
  font-size:12px;
  font-weight:700;
  color:#40505c;
}}
.layer-toolbar {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  align-items:center;
  margin-top:10px;
  padding:12px 14px;
  border-radius:18px;
  background:linear-gradient(180deg, rgba(21,32,44,.96) 0%, rgba(29,42,56,.96) 100%);
  border:1px solid rgba(129,151,168,.24);
  box-shadow:0 10px 20px rgba(13,18,24,.10);
}}
.layer-title {{
  margin-right:4px;
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:#8db8c3;
}}
.layer-chip {{
  appearance:none;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  flex-direction:column;
  gap:6px;
  min-width:76px;
  padding:8px 10px;
  border-radius:14px;
  border:1px solid rgba(166,181,196,.22);
  background:linear-gradient(180deg, rgba(255,255,255,.08) 0%, rgba(255,255,255,.04) 100%);
  font-size:12px;
  font-weight:700;
  color:#edf4f7;
  cursor:pointer;
  transition:background .12s ease, border-color .12s ease, color .12s ease, box-shadow .12s ease;
  user-select:none;
}}
.layer-glyph {{
  width:18px;
  height:18px;
  display:flex;
  align-items:center;
  justify-content:center;
  line-height:1;
}}
.layer-glyph svg {{
  width:18px;
  height:18px;
  stroke:currentColor;
  fill:none;
  stroke-linecap:round;
  stroke-linejoin:round;
  stroke-width:1.2;
  transition:transform .12s ease;
  vector-effect:non-scaling-stroke;
}}
.layer-chip-label {{
  font-size:10px;
  letter-spacing:.02em;
}}
.layer-chip[aria-pressed='true'],
.layer-chip.is-on,
.layer-chip:has(input:checked) {{
  background:linear-gradient(180deg, rgba(23,127,137,.96) 0%, rgba(16,92,102,.96) 100%);
  border-color:#1b97a2;
  color:#f5fbfb;
  box-shadow:0 10px 20px rgba(15,106,115,.20);
}}
.overlay-mode-toolbar {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:8px;
  margin-top:10px;
}}
.overlay-mode-button {{
  appearance:none;
  border:1px solid rgba(168,190,202,.22);
  border-radius:14px;
  padding:9px 10px;
  background:linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.035));
  color:#d8e7ec;
  cursor:pointer;
  font-size:11px;
  font-weight:800;
  letter-spacing:.02em;
  text-align:left;
  transition:background .12s ease, border-color .12s ease, color .12s ease, box-shadow .12s ease;
}}
.overlay-mode-button[aria-pressed='true'],
.overlay-mode-button.is-active {{
  border-color:#8fd6ce;
  color:#f6fffd;
  background:linear-gradient(135deg, rgba(21,127,137,.96), rgba(49,89,129,.92));
  box-shadow:0 12px 24px rgba(13,83,91,.22);
}}
.legend-strip {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:14px;
}}
.legend-pill {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:8px 12px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.12);
  font-size:12px;
  font-weight:700;
  color:#edf4f7;
}}
.legend-swatch {{
  width:12px;
  height:12px;
  border-radius:999px;
  border:1px solid rgba(0,0,0,.12);
}}
.viewer-3d-grid {{
  display:grid;
  grid-template-columns:280px minmax(0,1fr) 344px;
  gap:16px;
  margin-top:14px;
  align-items:start;
}}
.precision-pane {{
  padding:16px;
  border-radius:22px;
  border:1px solid #c9d5e0;
  background:linear-gradient(180deg, #fbfdff 0%, #f2f6fa 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.6);
  position:relative;
}}
.drawing-eyebrow {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--muted);
}}
.precision-headline {{
  margin-bottom:12px;
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:10px;
  flex-wrap:wrap;
}}
.precision-headline h3 {{
  margin:8px 0 6px;
}}
.precision-badges {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}}
.precision-metric {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 10px;
  border-radius:10px;
  background:#ecf2f5;
  border:1px solid #d1dde4;
  font-size:11px;
  color:#2f434f;
  font-weight:700;
}}
.precision-pane h3, .inspector-panel h3 {{
  margin:8px 0 14px;
  font-size:20px;
  letter-spacing:-0.03em;
}}
.precision-canvas-wrap {{
  position:relative;
  overflow:hidden;
  min-height:clamp(560px, 72vh, 720px);
  border-radius:24px;
  border:1px solid rgba(112,132,148,.34);
  background:
    radial-gradient(circle at 18% 10%, rgba(125,208,214,.20), transparent 30%),
    radial-gradient(circle at 88% 72%, rgba(240,90,40,.12), transparent 34%),
    linear-gradient(180deg, #08111b 0%, #0d1824 48%, #101d2a 100%);
  cursor:grab;
  box-shadow:
    0 28px 70px rgba(17,34,48,.24),
    inset 0 1px 0 rgba(255,255,255,.12),
    inset 0 0 0 1px rgba(255,255,255,.04);
  isolation:isolate;
}}
.precision-canvas-wrap::before {{
  content:'';
  position:absolute;
  inset:0;
  z-index:0;
  pointer-events:none;
  background:
    linear-gradient(rgba(125,208,214,.075) 1px, transparent 1px),
    linear-gradient(90deg, rgba(125,208,214,.075) 1px, transparent 1px),
    radial-gradient(circle at 50% 42%, transparent 0, rgba(5,12,20,.32) 74%);
  background-size:42px 42px, 42px 42px, 100% 100%;
  mask-image:linear-gradient(90deg, transparent 0, black 12%, black 88%, transparent 100%);
}}
.precision-canvas-wrap::after {{
  content:'';
  position:absolute;
  inset:20px;
  z-index:0;
  pointer-events:none;
  border:1px solid rgba(232,241,245,.08);
  border-radius:20px;
  box-shadow:inset 0 0 60px rgba(125,208,214,.055);
}}
.precision-canvas-wrap.is-dragging {{
  cursor:grabbing;
}}
.precision-canvas-wrap canvas {{
  position:relative;
  z-index:1;
  width:100%;
  height:clamp(560px, 72vh, 720px);
  display:block;
  image-rendering:auto;
  touch-action:none;
  user-select:none;
}}
.viewer-stage-hud {{
  position:absolute;
  left:16px;
  top:16px;
  z-index:4;
  display:flex;
  align-items:center;
  flex-wrap:wrap;
  gap:8px;
  max-width:calc(100% - 340px);
  pointer-events:none;
}}
.viewer-stage-chip {{
  display:inline-flex;
  align-items:center;
  gap:7px;
  min-height:30px;
  padding:7px 11px;
  border-radius:999px;
  border:1px solid var(--viewer-chrome-border);
  background:var(--viewer-chrome-panel);
  color:#d8e8ee;
  box-shadow:var(--viewer-chrome-shadow), var(--viewer-chrome-inset);
  backdrop-filter:blur(12px);
  font-size:11px;
  font-weight:800;
  letter-spacing:.01em;
}}
.viewer-stage-chip::after {{
  content:attr(data-full-label);
}}
.viewer-stage-chip[data-full-label='']::after {{
  content:'';
}}
.viewer-stage-chip.is-live::before {{
  content:'';
  width:8px;
  height:8px;
  border-radius:999px;
  background:#7dd0d6;
  box-shadow:0 0 0 4px rgba(125,208,214,.12);
}}
.viewer-axis-compass {{
  position:absolute;
  left:18px;
  bottom:58px;
  z-index:4;
  width:92px;
  height:92px;
  border:1px solid var(--viewer-chrome-border);
  border-radius:22px;
  background:var(--viewer-chrome-glass);
  box-shadow:var(--viewer-chrome-shadow), var(--viewer-chrome-inset);
  backdrop-filter:blur(12px);
  pointer-events:none;
}}
.viewer-axis-compass::before,
.viewer-axis-compass::after {{
  content:'';
  position:absolute;
  left:46px;
  top:18px;
  width:1px;
  height:56px;
  background:linear-gradient(180deg, #7dd0d6, rgba(125,208,214,.04));
  transform-origin:50% 100%;
}}
.viewer-axis-compass::after {{
  transform:rotate(58deg);
  background:linear-gradient(180deg, #f0b86f, rgba(240,184,111,.04));
}}
.viewer-axis-node {{
  position:absolute;
  display:grid;
  place-items:center;
  width:24px;
  height:24px;
  border-radius:999px;
  color:#08111b;
  font-size:10px;
  font-weight:900;
  box-shadow:0 8px 18px rgba(0,0,0,.24);
}}
.viewer-axis-node.is-x {{
  right:12px;
  top:24px;
  background:#f0b86f;
}}
.viewer-axis-node.is-y {{
  left:34px;
  top:8px;
  background:#7dd0d6;
}}
.viewer-axis-node.is-z {{
  left:14px;
  bottom:14px;
  background:#95b8ff;
}}
.viewer-status-ribbon {{
  position:absolute;
  left:126px;
  right:18px;
  bottom:18px;
  z-index:4;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  min-height:38px;
  padding:8px 12px;
  border:1px solid var(--viewer-chrome-border);
  border-radius:999px;
  background:var(--viewer-chrome-glass);
  color:#d8e8ee;
  box-shadow:var(--viewer-chrome-shadow), var(--viewer-chrome-inset);
  backdrop-filter:blur(12px);
  pointer-events:none;
  font-size:11px;
  font-weight:800;
}}
.viewer-status-ribbon span {{
  min-width:0;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}}
.viewer-status-ribbon span::after {{
  content:attr(data-full-label);
}}
.viewer-status-ribbon span[data-full-label='']::after {{
  content:'';
}}
.viewer-viewport-controls {{
  position:absolute;
  right:16px;
  top:50%;
  z-index:6;
  display:grid;
  gap:8px;
  transform:translateY(-50%);
}}
.viewer-viewport-button {{
  min-width:42px;
  min-height:42px;
  display:grid;
  place-items:center;
  border:1px solid var(--viewer-chrome-border-strong);
  border-radius:14px;
  background:var(--viewer-chrome-panel);
  color:#e8f1f5;
  box-shadow:var(--viewer-chrome-shadow), var(--viewer-chrome-inset);
  backdrop-filter:blur(14px);
  font-size:13px;
  font-weight:900;
  letter-spacing:.01em;
  cursor:pointer;
  touch-action:manipulation;
}}
.viewer-viewport-button:hover,
.viewer-viewport-button:focus-visible {{
  border-color:rgba(125,208,214,.58);
  color:#ffffff;
  outline:none;
  box-shadow:0 18px 34px rgba(0,0,0,.30), 0 0 0 3px rgba(125,208,214,.18), inset 0 1px 0 rgba(255,255,255,.10);
}}
.sr-only {{
  position:absolute;
  width:1px;
  height:1px;
  padding:0;
  margin:-1px;
  overflow:hidden;
  clip:rect(0,0,0,0);
  white-space:nowrap;
  border:0;
}}
.selection-overlay {{
  position:absolute;
  right:16px;
  top:16px;
  width:min(300px, calc(100% - 32px));
  border:1px solid var(--viewer-chrome-border);
  border-radius:18px;
  padding:12px 14px;
  background:var(--viewer-chrome-panel);
  box-shadow:var(--viewer-chrome-shadow-strong), var(--viewer-chrome-inset);
  color:#e8f1f5;
  opacity:0.98;
  pointer-events:none;
  z-index:5;
  backdrop-filter:blur(14px);
}}
.selection-overlay.is-empty {{
  opacity:0.86;
}}
.selection-overlay.is-empty .selection-overlay-line:not(.selection-overlay-muted) {{
  display:none;
}}
.selection-overlay-head {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
}}
.selection-overlay-title {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.12em;
  color:#7dd0d6;
  font-weight:900;
}}
.selection-overlay-actions {{
  display:flex;
  align-items:center;
  gap:6px;
  flex-wrap:wrap;
  justify-content:flex-end;
}}
.selection-clear-button,
.selection-share-button {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:28px;
  padding:5px 9px;
  border:1px solid var(--viewer-chrome-border-strong);
  border-radius:999px;
  background:rgba(232,241,245,.08);
  color:#e8f1f5;
  font-size:10px;
  font-weight:900;
  cursor:pointer;
  pointer-events:auto;
}}
.selection-share-button {{
  background:rgba(125,208,214,.14);
  color:#f3fbff;
}}
.selection-clear-button:disabled,
.selection-share-button:disabled {{
  opacity:.48;
  cursor:default;
}}
.selection-clear-button:not(:disabled):hover,
.selection-clear-button:not(:disabled):focus-visible,
.selection-share-button:not(:disabled):hover,
.selection-share-button:not(:disabled):focus-visible {{
  border-color:rgba(125,208,214,.58);
  outline:none;
  box-shadow:0 0 0 3px rgba(125,208,214,.16);
}}
.selection-overlay-line {{
  margin-top:6px;
  font-size:12px;
  line-height:1.45;
  color:#e8f1f5;
  word-break:break-word;
  font-variant-numeric:tabular-nums;
}}
.selection-overlay-muted {{
  color:#aebdc7;
  font-size:11px;
}}
.viewer-tooltip {{
  position:absolute;
  left:0;
  top:0;
  width:min(320px, calc(100% - 28px));
  padding:12px 14px;
  border-radius:16px;
  border:1px solid var(--viewer-chrome-border);
  background:var(--viewer-chrome-panel);
  box-shadow:var(--viewer-chrome-shadow), var(--viewer-chrome-inset);
  color:#e8f1f5;
  opacity:0;
  transform:translate(14px, 14px);
  pointer-events:none;
  transition:opacity .12s ease;
  backdrop-filter:blur(14px);
  z-index:6;
}}
.viewer-tooltip.is-visible {{
  opacity:1;
}}
.viewer-tooltip-title {{
  font-size:13px;
  font-weight:800;
  color:#f5fbfb;
}}
.viewer-tooltip-grid {{
  display:grid;
  grid-template-columns:84px 1fr;
  gap:4px 8px;
  margin-top:8px;
  font-size:12px;
  line-height:1.5;
  color:#d8e8ee;
}}
.viewer-tooltip-label {{
  color:#7dd0d6;
  text-transform:uppercase;
  letter-spacing:.08em;
  font-size:10px;
  font-weight:700;
}}
.viewer-tooltip-note {{
  margin-top:8px;
  color:#aebdc7;
  font-size:11px;
  line-height:1.5;
}}
.viewer-badge-row {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  margin-top:10px;
}}
.viewer-badge {{
  display:inline-flex;
  align-items:center;
  padding:8px 10px;
  border-radius:999px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);
  font-size:12px;
  font-weight:700;
  color:#e8f1f5;
}}
.dock-panel {{
  position:sticky;
  top:18px;
  align-self:start;
  padding:18px;
  border-radius:22px;
  background:linear-gradient(180deg, rgba(14,22,31,.96) 0%, rgba(24,35,47,.96) 100%);
  border:1px solid rgba(129,151,168,.24);
  box-shadow:0 16px 32px rgba(13,18,24,.16);
  color:#e7f0f4;
}}
.dock-panel h3 {{
  margin:6px 0 0;
  font-size:22px;
  line-height:1.08;
  letter-spacing:-0.03em;
  color:#f5fbfb;
}}
.dock-kicker {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#7dd0d6;
  font-weight:800;
}}
.dock-kicker-subhead {{
  margin-top:6px;
}}
.dock-subhead {{
  margin:16px 0 8px;
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#8ca3af;
}}
.dock-stat-grid {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:10px;
  margin-top:14px;
}}
.dock-stat {{
  min-height:78px;
  padding:12px 12px 11px;
  border-radius:16px;
  background:rgba(255,255,255,.05);
  border:1px solid rgba(255,255,255,.10);
}}
.dock-stat span {{
  display:block;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#8ca3af;
  margin-bottom:8px;
}}
.dock-stat strong {{
  display:block;
  font-size:13px;
  line-height:1.45;
  color:#edf6f9;
  word-break:break-word;
}}
.dock-status-line {{
  margin-top:12px;
  padding:10px 12px;
  border-radius:14px;
  border:1px solid rgba(125,208,214,.14);
  background:rgba(125,208,214,.06);
  color:#d5edf1;
  font-size:12px;
  line-height:1.55;
  font-variant-numeric:tabular-nums;
}}
.dock-tree {{
  display:grid;
  gap:10px;
  margin-top:10px;
}}
.dock-tree-section {{
  display:grid;
  gap:8px;
  padding:12px 12px 12px 14px;
  border-radius:16px;
  background:rgba(255,255,255,.03);
  border:1px solid rgba(255,255,255,.08);
  border-left:2px solid rgba(125,208,214,.28);
}}
.dock-tree-branch-head {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin-bottom:2px;
}}
.dock-tree-branch-title {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.16em;
  color:#7dd0d6;
  font-weight:800;
}}
.dock-tree-branch-tag {{
  display:inline-flex;
  align-items:center;
  padding:4px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.10);
  color:#d5e6eb;
  font-size:9px;
  font-weight:800;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.dock-tree-row {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:9px 11px;
  border-radius:12px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
}}
.dock-tree-row.is-child {{
  margin-left:10px;
  padding-left:10px;
  background:rgba(255,255,255,.02);
  border-left:1px solid rgba(125,208,214,.18);
}}
.dock-tree-label {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  color:#e7f0f4;
  font-size:12px;
  font-weight:700;
}}
.dock-tree-bullet {{
  width:7px;
  height:7px;
  border-radius:999px;
  background:#7dd0d6;
  box-shadow:0 0 0 4px rgba(125,208,214,.10);
}}
.dock-tree-state {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:42px;
  padding:4px 8px;
  border-radius:999px;
  background:rgba(255,255,255,.08);
  border:1px solid rgba(255,255,255,.12);
  color:#cfe6ee;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.dock-tree-state.is-good {{
  background:rgba(28,122,79,.18);
  border-color:rgba(28,122,79,.34);
  color:#a6efc7;
}}
.dock-tree-state.is-warn {{
  background:rgba(201,109,44,.18);
  border-color:rgba(201,109,44,.34);
  color:#ffd7ba;
}}
.dock-tree-state.is-neutral {{
  background:rgba(255,255,255,.06);
  border-color:rgba(255,255,255,.12);
  color:#dce6eb;
}}
.dock-tree-state.is-bad {{
  background:rgba(154,55,55,.18);
  border-color:rgba(154,55,55,.34);
  color:#ffc8c8;
}}
.dock-links {{
  margin-top:12px;
}}
.mgt-diff-panel {{
  margin-top:12px;
  padding:12px;
  border-radius:16px;
  border:1px solid rgba(255,255,255,.10);
  background:rgba(255,255,255,.04);
}}
.mgt-diff-summary {{
  font-size:12px;
  line-height:1.55;
  color:#d5edf1;
}}
.mgt-diff-grid {{
  display:grid;
  grid-template-columns:repeat(2, minmax(0, 1fr));
  gap:8px;
  margin-top:10px;
  min-width:0;
}}
.mgt-diff-stat {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(255,255,255,.04);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-diff-stat span {{
  display:block;
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:#8ca3af;
  margin-bottom:6px;
}}
.mgt-diff-stat strong {{
  display:block;
  color:#edf6f9;
  font-size:13px;
  line-height:1.4;
}}
.mgt-diff-samples {{
  display:grid;
  gap:8px;
  margin-top:10px;
  min-width:0;
}}
.mgt-diff-row {{
  padding:10px 11px;
  border-radius:12px;
  background:rgba(10,18,27,.42);
  border:1px solid rgba(255,255,255,.08);
  min-width:0;
}}
.mgt-diff-row-head {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  align-items:center;
  margin-bottom:8px;
  color:#b7ccd4;
  font-size:11px;
  font-weight:700;
}}
.mgt-diff-kind {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-width:62px;
  padding:4px 8px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.06);
  color:#edf6f9;
  font-size:10px;
  letter-spacing:.08em;
}}
.mgt-diff-kind.is-replace {{
  background:rgba(15,155,209,.16);
  border-color:rgba(15,155,209,.32);
  color:#afe6ff;
}}
.mgt-diff-kind.is-insert {{
  background:rgba(28,122,79,.18);
  border-color:rgba(28,122,79,.34);
  color:#a6efc7;
}}
.mgt-diff-kind.is-delete {{
  background:rgba(201,109,44,.18);
  border-color:rgba(201,109,44,.34);
  color:#ffd7ba;
}}
.mgt-diff-code {{
  display:grid;
  grid-template-columns:34px minmax(0, 1fr);
  gap:8px;
  align-items:start;
  color:#dce9ee;
  font-size:11px;
  line-height:1.5;
}}
.mgt-diff-code + .mgt-diff-code {{
  margin-top:6px;
}}
.mgt-diff-code-label {{
  color:#8ca3af;
  text-transform:uppercase;
  letter-spacing:.08em;
  font-weight:700;
}}
.mgt-diff-code code {{
  font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space:pre-wrap;
  word-break:break-word;
}}
.inspector-panel {{
  position:sticky;
  top:18px;
  align-self:start;
  width:auto;
  max-height:calc(100vh - 160px);
  overflow:auto;
  padding:18px;
  border-radius:22px;
  border:1px solid var(--line);
  background:linear-gradient(180deg, #fcfeff 0%, #f3f7fa 100%);
  box-shadow:0 18px 34px rgba(30,39,50,.08);
  border-color:#c7d3df;
  z-index:2;
}}
.inspector-eyebrow {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.14em;
  color:var(--muted);
}}
.inspector-grid {{
  display:grid;
  grid-template-columns:1fr;
  gap:10px;
}}
.inspector-item {{
  padding:12px 13px;
  border-radius:16px;
  background:linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
  border:1px solid #d9e3ea;
  font-variant-numeric:tabular-nums;
}}
.inspector-item-label {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.12em;
  color:var(--muted);
  line-height:1.35;
}}
.inspector-item-value {{
  margin-top:6px;
  font-size:13px;
  line-height:1.55;
  color:#24313b;
  word-break:break-word;
  font-variant-numeric:tabular-nums;
}}
.inspector-evidence-card {{
  margin-top:12px;
  padding:14px;
  border-radius:18px;
  border:1px solid rgba(15,106,115,.18);
  background:
    radial-gradient(circle at 10% 0%, rgba(255,255,255,.92), rgba(255,255,255,0) 38%),
    linear-gradient(135deg, rgba(239,250,250,.98), rgba(255,248,236,.96));
  box-shadow:inset 0 1px 0 rgba(255,255,255,.62);
}}
.inspector-evidence-card.is-empty {{
  background:linear-gradient(180deg, #ffffff 0%, #f8fbfd 100%);
  border-color:#d9e3ea;
}}
.inspector-evidence-head {{
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:10px;
}}
.inspector-evidence-title {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.13em;
  color:#0f6a73;
  font-weight:800;
}}
.inspector-evidence-badge {{
  flex:0 0 auto;
  max-width:48%;
  padding:4px 8px;
  border-radius:999px;
  background:rgba(15,106,115,.09);
  color:#0f6a73;
  font-size:10px;
  font-weight:800;
  letter-spacing:.06em;
  text-transform:uppercase;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}}
.inspector-evidence-reason {{
  margin-top:9px;
  color:#24313b;
  font-size:13px;
  line-height:1.55;
}}
.inspector-evidence-grid {{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:11px;
}}
.inspector-evidence-metric {{
  min-width:0;
  padding:9px 10px;
  border-radius:13px;
  background:rgba(255,255,255,.70);
  border:1px solid rgba(137,164,181,.20);
}}
.inspector-evidence-label {{
  font-size:10px;
  text-transform:uppercase;
  letter-spacing:.10em;
  color:#697b88;
  line-height:1.35;
}}
.inspector-evidence-value {{
  margin-top:4px;
  font-size:12px;
  line-height:1.45;
  color:#24313b;
  font-variant-numeric:tabular-nums;
  word-break:break-word;
}}
.inspector-evidence-handoff {{
  margin-top:10px;
  padding-top:10px;
  border-top:1px dashed rgba(15,106,115,.22);
  color:#455763;
  font-size:12px;
  line-height:1.55;
}}
.precision-caption {{
  margin-top:10px;
  color:var(--muted);
  font-size:12px;
  line-height:1.6;
}}
.mini-card-grid {{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(180px,1fr));
  gap:12px;
  margin-top:16px;
}}
.mini-card {{
  padding:16px;
  border-radius:18px;
  border:1px solid var(--line);
  background:#fffdf8;
}}
.mini-card-label {{
  font-size:12px;
  text-transform:uppercase;
  letter-spacing:.12em;
  color:var(--muted);
}}
.mini-card-value {{
  margin-top:6px;
  font-size:20px;
  font-weight:800;
}}
.mini-card-note {{
  margin-top:8px;
  color:var(--muted);
  font-size:12px;
  line-height:1.5;
}}
.zone-chip-row {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:16px;
}}
.zone-chip {{
  display:inline-flex;
  padding:9px 12px;
  border-radius:999px;
  background:var(--brand-soft);
  color:#134851;
  font-size:12px;
  font-weight:700;
}}
.story-mini-strip {{
  display:grid;
  gap:10px;
  margin-top:16px;
  padding:14px;
  border-radius:18px;
  background:linear-gradient(180deg, #f8fbfd 0%, #f3f7fb 100%);
  border:1px solid #d7e0ea;
}}
.story-mini-strip-head {{
  display:flex;
  gap:12px;
  flex-wrap:wrap;
  align-items:flex-start;
  justify-content:space-between;
}}
.story-mini-strip-title {{
  font-size:11px;
  font-weight:800;
  text-transform:uppercase;
  letter-spacing:.18em;
  color:#8c5a33;
}}
.story-mini-strip-note {{
  max-width:52rem;
  font-size:12px;
  line-height:1.55;
  color:#5a6b78;
}}
.story-mini-strip-grid {{
  display:grid;
  grid-template-columns:repeat(auto-fit, minmax(168px, 1fr));
  gap:10px;
}}
.story-mini-chip {{
  position:relative;
  display:grid;
  gap:5px;
  padding:11px 12px 10px 14px;
  border-radius:15px;
  background:#ffffff;
  border:1px solid #d8e1eb;
  box-shadow:0 10px 18px rgba(39,58,74,.04);
  overflow:hidden;
  cursor:pointer;
  transition:border-color .18s ease, box-shadow .18s ease, transform .18s ease, background .18s ease;
}}
.story-mini-chip::before {{
  content:'';
  position:absolute;
  left:0;
  top:0;
  bottom:0;
  width:4px;
  background:#d96f32;
}}
.story-mini-chip.is-primary::before {{ background:#c46a2d; }}
.story-mini-chip.is-secondary::before {{ background:#d96f32; }}
.story-mini-chip.is-tertiary::before {{ background:#f0a63c; }}
.story-mini-chip.is-neutral::before {{ background:#9c6b4a; }}
.story-mini-chip:hover,
.story-mini-chip:focus-visible {{
  border-color:rgba(240,90,40,.38);
  box-shadow:0 12px 20px rgba(39,58,74,.06), 0 0 0 1px rgba(240,90,40,.10);
  transform:translateY(-1px);
  outline:none;
}}
.story-mini-chip.is-active {{
  border-color:rgba(240,90,40,.54);
  box-shadow:0 14px 24px rgba(39,58,74,.08), 0 0 0 2px rgba(240,90,40,.12);
  transform:translateY(-1px);
}}
.story-mini-chip.is-active::before {{
  width:6px;
  background:#f05a28;
}}
.story-mini-chip-head {{
  display:flex;
  justify-content:space-between;
  gap:10px;
  align-items:center;
  padding-left:6px;
}}
.story-mini-chip-story {{
  font-size:12px;
  font-weight:800;
  color:#223544;
  letter-spacing:.06em;
}}
.story-mini-chip-slot {{
  font-size:10px;
  font-weight:800;
  color:#9a572a;
  text-transform:uppercase;
  letter-spacing:.12em;
  white-space:nowrap;
}}
.story-mini-chip-line {{
  padding-left:6px;
  font-size:12px;
  font-weight:800;
  color:#6f4021;
  letter-spacing:.03em;
}}
.story-mini-chip-track {{
  height:6px;
  margin-left:6px;
  overflow:hidden;
  border-radius:999px;
  background:rgba(217,111,50,.12);
}}
.story-mini-chip-track-fill {{
  height:100%;
  min-width:10%;
  border-radius:999px;
  background:linear-gradient(90deg, #4b6778 0%, #d96f32 55%, #f0a63c 100%);
}}
.story-mini-chip-count {{
  padding-left:6px;
  font-size:12px;
  font-weight:700;
  color:#5b4537;
}}
.story-mini-chip-emphasis {{
  padding-left:6px;
  font-size:11px;
  font-weight:700;
  color:#7c4e30;
  line-height:1.4;
}}
.story-mini-chip-share {{
  padding-left:6px;
  font-size:11px;
  color:#7a675b;
  line-height:1.45;
}}
.story-mini-empty {{
  padding:10px 12px;
  border-radius:12px;
  border:1px dashed rgba(125,208,214,.24);
  background:rgba(125,208,214,.05);
  color:#6f7f89;
  font-size:12px;
  line-height:1.55;
}}
.story-slot-pill {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:4px 8px;
  border-radius:999px;
  background:#fff5ee;
  border:1px solid #f0c4a9;
  color:#8c4f27;
  font-size:10px;
  font-weight:800;
  letter-spacing:.08em;
  text-transform:uppercase;
}}
.table-wrap {{
  overflow:auto;
  max-width:100%;
  min-width:0;
  width:100%;
  contain:inline-size;
  overscroll-behavior-x:contain;
  -webkit-overflow-scrolling:touch;
  margin-top:14px;
}}
.table-wrap table {{
  min-width:760px;
}}
.story-table-wrap,
.member-table-wrap {{
  overflow-x:auto;
}}
.story-table-wrap table {{
  min-width:760px;
}}
.member-table-wrap table {{
  min-width:920px;
}}
table {{
  width:100%;
  border-collapse:collapse;
  font-size:13px;
  border-radius:14px;
  overflow:hidden;
  border:1px solid #d4dfeb;
}}
th, td {{
  padding:11px 10px;
  border-bottom:1px solid #e2e9f0;
  text-align:left;
  vertical-align:top;
}}
thead th {{
  position:sticky;
  top:0;
  z-index:2;
  background:#f4f8fb;
  border-bottom:1px solid #ccd9e6;
  backdrop-filter:blur(2px);
}}
th {{
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.12em;
  color:var(--muted);
}}
tbody tr.is-selected-row {{
  background:#edf6f8;
  box-shadow:inset 0 0 0 1px rgba(15,106,115,.2);
}}
tbody tr:focus-visible {{
  outline:2px solid rgba(15,106,115,.45);
  outline-offset:-2px;
}}
tbody tr.is-story-active {{
  background:#fff5ec;
  box-shadow:inset 0 0 0 1px rgba(240,90,40,.18);
}}
tbody tr.is-story-active.is-selected-row {{
  background:#edf6f8;
  box-shadow:inset 0 0 0 1px rgba(15,106,115,.22), 0 0 0 1px rgba(240,90,40,.12);
}}
tbody tr.story-band-row {{
  cursor:pointer;
}}
tbody tr.story-band-row:hover,
tbody tr.story-band-row:focus-visible {{
  background:#fff8f2;
  outline:none;
}}
tbody tr:hover {{
  background:#f4f9fb;
}}
.search-box {{
  width:100%;
  margin-top:16px;
  border:1px solid var(--line);
  border-radius:14px;
  padding:12px 14px;
  font:inherit;
  background:#fffdf8;
}}
.search-box:focus {{
  outline:none;
  border-color:var(--brand);
  box-shadow:0 0 0 3px rgba(15,106,115,.12);
}}
.inspect-link {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  padding:8px 10px;
  border-radius:999px;
  border:1px solid #c7d2df;
  background:#edf4f7;
  font-size:12px;
  font-weight:700;
}}
.footnote {{
  margin-top:16px;
  padding:14px 16px;
  border-radius:18px;
  background:linear-gradient(180deg, #f3f7fb 0%, #edf2f7 100%);
  border:1px solid #c6d7df;
  color:#35505c;
  font-size:13px;
  line-height:1.65;
}}
@media (max-width: 1024px) {{
  .hero, .viewer-3d-grid {{ grid-template-columns:1fr; }}
  .viewer-3d-grid > .precision-pane {{ order:1; }}
  .viewer-3d-grid > .dock-panel {{ order:2; }}
  .viewer-3d-grid > .inspector-panel {{ order:3; }}
  .precision-canvas-wrap {{ min-height:clamp(380px, 62vh, 560px); }}
  .precision-canvas-wrap canvas {{ height:clamp(380px, 62vh, 560px); }}
  .viewer-stage-hud {{
    left:12px;
    right:12px;
    top:12px;
    max-width:none;
    gap:6px;
  }}
  .viewer-stage-chip {{
    min-height:28px;
    padding:6px 9px;
    font-size:10px;
  }}
  .viewer-stage-chip::after {{
    content:attr(data-mobile-label);
  }}
  .viewer-axis-compass {{
    left:14px;
    bottom:var(--viewer-stage-compass-bottom);
    width:74px;
    height:74px;
    border-radius:18px;
  }}
  .viewer-axis-compass::before,
  .viewer-axis-compass::after {{
    left:37px;
    top:15px;
    height:44px;
  }}
  .viewer-axis-node {{
    width:21px;
    height:21px;
  }}
  .viewer-axis-node.is-x {{
    right:9px;
    top:20px;
  }}
  .viewer-axis-node.is-y {{
    left:27px;
    top:7px;
  }}
  .viewer-axis-node.is-z {{
    left:11px;
    bottom:11px;
  }}
  .viewer-status-ribbon {{
    left:14px;
    right:132px;
    top:var(--viewer-stage-ribbon-top);
    bottom:auto;
    justify-content:flex-start;
    flex-wrap:wrap;
    border-radius:18px;
    min-height:34px;
    padding:7px 10px;
  }}
  .viewer-status-ribbon span::after {{
    content:attr(data-mobile-label);
  }}
  .viewer-viewport-controls {{
    right:12px;
    top:96px;
    transform:none;
    gap:7px;
  }}
  .viewer-viewport-button {{
    min-width:44px;
    min-height:44px;
    border-radius:15px;
  }}
  .selection-overlay {{
    top:auto;
    left:12px;
    right:12px;
    bottom:var(--viewer-stage-overlay-bottom);
    width:auto;
    max-height:28%;
    overflow:auto;
    border-radius:18px 18px 14px 14px;
    padding:10px 12px;
    background:var(--viewer-chrome-glass);
  }}
  .selection-overlay-line {{
    margin-top:4px;
    font-size:11px;
    line-height:1.35;
  }}
  .selection-overlay-title {{
    font-size:9px;
  }}
  .story-table-wrap,
  .member-table-wrap {{
    overflow-x:hidden;
  }}
  .story-table-wrap table,
  .story-table-wrap thead,
  .story-table-wrap tbody,
  .story-table-wrap tr,
  .story-table-wrap th,
  .story-table-wrap td,
  .member-table-wrap table,
  .member-table-wrap thead,
  .member-table-wrap tbody,
  .member-table-wrap tr,
  .member-table-wrap th,
  .member-table-wrap td {{
    display:block;
    width:100%;
    min-width:0;
  }}
  .story-table-wrap table,
  .member-table-wrap table {{
    border:0;
    background:transparent;
  }}
  .story-table-wrap thead,
  .member-table-wrap thead {{
    position:absolute;
    width:1px;
    height:1px;
    overflow:hidden;
    clip:rect(0 0 0 0);
    white-space:nowrap;
  }}
  .story-table-wrap tbody,
  .member-table-wrap tbody {{
    display:grid;
    gap:10px;
  }}
  .story-table-wrap tbody tr,
  .member-table-wrap tbody tr {{
    display:grid;
    gap:7px;
    padding:12px;
    border:1px solid #d4dfeb;
    border-radius:16px;
    background:#fffdf8;
    box-shadow:0 10px 18px rgba(39,58,74,.05);
  }}
  .story-table-wrap tbody tr:hover,
  .member-table-wrap tbody tr:hover {{
    background:#f8fcfd;
  }}
  .story-table-wrap tbody td,
  .member-table-wrap tbody td {{
    display:grid;
    grid-template-columns:104px minmax(0, 1fr);
    gap:10px;
    align-items:start;
    padding:0;
    border:0;
    word-break:break-word;
  }}
  .story-table-wrap tbody td::before,
  .member-table-wrap tbody td::before {{
    content:attr(data-label);
    color:var(--muted);
    font-size:10px;
    font-weight:800;
    letter-spacing:.10em;
    text-transform:uppercase;
  }}
  .table-wrap {{
    overflow-x:hidden;
    width:100%;
    max-width:100%;
    min-width:0;
  }}
  .table-wrap table {{
    min-width:0;
    table-layout:fixed;
  }}
  .table-wrap th,
  .table-wrap td {{
    min-width:0;
    overflow-wrap:anywhere;
    word-break:break-word;
  }}
  .precision-toolbar {{ grid-template-columns:1fr; }}
  .mgt-first-banner {{ grid-template-columns:1fr; }}
  .mgt-first-banner-status {{ justify-content:flex-start; }}
  .mgt-verification-grid,
  .mgt-console-grid,
  .mgt-diff-grid,
  .mgt-raw-diff-metrics,
  .mgt-raw-diff-toolbar,
  .mgt-compare-pager-dock,
  .mgt-compare-page-text-grid,
  .mgt-compare-page-row,
  .mgt-compare-page-split,
  .mgt-compare-split {{
    grid-template-columns:1fr;
  }}
  .mgt-console,
  .mgt-verification-summary,
  .mgt-diff-panel,
  .mgt-compare-panel,
  .mgt-compare-sheet,
  .mgt-raw-diff-shell {{
    width:100%;
    max-width:100%;
  }}
  .mgt-console-badge,
  .mgt-diff-value,
  .mgt-raw-diff-count {{
    white-space:normal;
    text-align:left;
  }}
  .external-expert-head {{ flex-direction:column; }}
  .external-expert-summary {{ justify-content:flex-start; }}
  .sheet-package-surface {{ grid-template-columns:1fr; }}
  .drawing-sheet, .drawing-sheet.is-wide {{ grid-column:1 / -1; }}
  .drawing-sheet-mini-grid {{ grid-template-columns:1fr; }}
  .dock-panel {{
    position:relative;
    top:0;
  }}
  .inspector-panel {{
    position:relative;
    top:0;
    right:auto;
    width:auto;
    max-height:none;
    z-index:auto;
  }}
}}
</style>
</head>
<body class='signal-desk-light'>
<div class='page'>
  {route_context_banner_markup}
  <section class='case-shell' id='drawing-package-shell'>
    <strong>Case: {case_id}</strong>
    <div>
      <span class='status-chip'>Mode: {precision_mode}</span>
      <span class='status-chip'>Baseline: {baseline_segment_count}</span>
      <span class='status-chip'>Optimized: {after_segment_count}</span>
      <span class='status-chip'>Changed: {changed_member_count}</span>
      <span class='status-chip'>MGT: {"PASS" if mgt_export_contract_pass else "CHECK"}</span>
      <span class='status-chip'>Output .mgt: {"yes" if mgt_export_output_mgt_exists else "no"}</span>
      <span class='status-chip'>LOADCOMB: {"exact" if mgt_export_loadcomb_roundtrip_pass else "check"}</span>
    </div>
  </section>
  {mgt_first_banner_html}
  {external_expert_mode_html}
  {drawing_hero_markup}

  <section class='cards' id='drawing-summary-cards'>
    <article class='card'>
      <div class='card-label'>Changed groups</div>
      <div class='card-value'>{_safe_int(payload.get("changed_group_count", 0))}</div>
      <div class='card-note'>최적화가 실제로 적용된 semantic group 수</div>
    </article>
    <article class='card'>
      <div class='card-label'>Changed members</div>
      <div class='card-value'>{_safe_int(payload.get("changed_member_count", 0))}</div>
      <div class='card-note'>overlay로 추적 가능한 부재 수</div>
    </article>
    <article class='card'>
      <div class='card-label'>Baseline elements</div>
      <div class='card-value'>{_safe_int(payload.get("total_element_count", 0))}</div>
      <div class='card-note'>baseline 구조 프레임 기준 전체 element</div>
    </article>
    <article class='card'>
      <div class='card-label'>Cost proxy delta</div>
      <div class='card-value'>{_safe_float(payload.get("signed_cost_proxy_delta_total", 0.0)):.3f}</div>
      <div class='card-note'>부호 포함 total cost proxy delta</div>
    </article>
    <article class='card'>
      <div class='card-label'>Constructability delta</div>
      <div class='card-value'>{_safe_float(payload.get("constructability_delta_total", 0.0)):.3f}</div>
      <div class='card-note'>시공성 변화 총합</div>
    </article>
    <article class='card'>
      <div class='card-label'>Max DCR after</div>
      <div class='card-value'>{_safe_float(payload.get("max_dcr_after_max", 0.0)):.3f}</div>
      <div class='card-note'>변경 이후 최대 governing DCR</div>
    </article>
    {real_drawing_summary_card_html}
  </section>

  <section class='section' id='drawing-3d-workspace'>
    <h2>3D Structural Workspace</h2>
    <p class='lead'>지금 화면은 plan/elevation/isometric 스냅샷이 아니라, 실제 xyz segment를 바로 렌더링하는 3D workspace입니다. 드래그로 회전하고, 휠로 확대하며, row를 누르면 해당 member로 center-fit 이동합니다.</p>
    <div class='precision-toolbar'>
      <div class='toolbar-group'>
        <div class='toolbar-label'>View presets</div>
        <div class='precision-actions'>{toolbar_buttons_html}</div>
      </div>
      <div class='toolbar-group'>
        <div class='toolbar-label'>Workspace state</div>
        <div class='viewer-badge-row'>
          <span class='viewer-badge'>XYZ canvas</span>
          <span class='viewer-badge'>baseline={_safe_int(interactive_3d_payload.get("baseline_segment_count", 0))}</span>
          <span class='viewer-badge'>optimized={_safe_int(interactive_3d_payload.get("after_segment_count", 0))}</span>
          <span class='viewer-badge'>renderable rows={valid_segment_count}</span>
          <span class='viewer-badge'>invalid rows excluded={invalid_excluded_count}</span>
          <span class='viewer-badge'>geometry={'valid rows' if valid_geometry_available else 'no valid rows'}</span>
        </div>
      </div>
    </div>
  <div class='viewer-3d-grid'>
      <aside class='dock-panel'>
        <div class='dock-kicker'>CAD Workspace</div>
        <h3>Workspace Dock</h3>
        <div class='dock-stat-grid'>
          <div class='dock-stat'><span>Mode</span><strong>{precision_mode}</strong></div>
          <div class='dock-stat'><span>Baseline</span><strong>{baseline_segment_count}</strong></div>
          <div class='dock-stat'><span>Optimized</span><strong>{after_segment_count}</strong></div>
          <div class='dock-stat'><span>Changed</span><strong>{changed_member_count}</strong></div>
        </div>
        <div class='dock-subhead'>Display tree</div>
        <div class='dock-kicker dock-kicker-subhead'>Model Explorer</div>
        <div class='dock-tree'>{dock_tree_html}</div>
        <div class='dock-subhead'>Layers</div>
        <div class='layer-toolbar'>
          <div class='layer-title'>Layers</div>
          <button type='button' class='layer-chip is-on' data-3d-toggle='grid' aria-pressed='true' title='Axis refs'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M4.5 3.5h15'/>
                <path d='M4.5 8h15'/>
                <path d='M4.5 12.5h15'/>
                <path d='M4.5 17h15'/>
                <path d='M4.5 20.5h15'/>
                <path d='M4.5 3.5v17'/>
                <path d='M19.5 3.5v17'/>
                <circle cx='4.5' cy='3.5' r='0.8'/>
                <circle cx='19.5' cy='3.5' r='0.8'/>
                <circle cx='4.5' cy='20.5' r='0.8'/>
                <circle cx='19.5' cy='20.5' r='0.8'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Axis</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='stories' aria-pressed='true' title='Story refs'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M4 4v16'/>
                <path d='M4 4h14'/>
                <path d='M4.5 7h13'/>
                <path d='M4.5 10h11.5'/>
                <path d='M4.5 13h10'/>
                <path d='M4.5 16h8.5'/>
                <path d='M4 20h14'/>
                <path d='M5 4.5h1'/>
                <path d='M5 8h1'/>
                <path d='M5 11h1'/>
                <path d='M5 14h1'/>
                <path d='M5 17h1'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Story</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='baseline' aria-pressed='true' title='Baseline segments'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M3 21h18'/>
                <path d='M4 21V8'/>
                <path d='M6.5 21V11'/>
                <path d='M9 21V6'/>
                <path d='M11.5 21V10'/>
                <path d='M14 21V13'/>
                <path d='M16.5 21V9'/>
                <path d='M19 21V16'/>
                <path d='M4 18h15.5'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Base</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='optimized' aria-pressed='true' title='Optimized segments'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M3 20h18'/>
                <path d='M4 20V10'/>
                <path d='M6.8 20V8'/>
                <path d='M9.6 20V13'/>
                <path d='M12.4 20V6'/>
                <path d='M15.2 20V11'/>
                <path d='M18 20V4'/>
                <path d='M4.2 20h2'/>
                <path d='M7 8l2.4-2.2 2.5 2.8 1.8-2.6'/>
                <circle cx='18' cy='4' r='0.75'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Opt</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='beam' aria-pressed='true' title='Beam'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M2.7 11h18.6'/>
                <path d='M4.8 9.5h14.4'/>
                <path d='M4.8 12.5h14.4'/>
                <path d='M3.8 10.3v3.4'/>
                <path d='M20.2 10.3v3.4'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Beam</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='column' aria-pressed='true' title='Column'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M8.8 3.8h6.4v16.4H8.8z'/>
                <path d='M9.6 6.4h4.8'/>
                <path d='M9.6 10.2h4.8'/>
                <path d='M9.6 14h4.8'/>
                <path d='M9.6 17.8h4.8'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Col</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='wall' aria-pressed='true' title='Wall'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M4 5h16v14H4z'/>
                <path d='M7 8h10'/>
                <path d='M7 11h10'/>
                <path d='M7 14h10'/>
                <path d='M6 5v14'/>
                <path d='M18 5v14'/>
                <path d='M4 15.5h16'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Wall</span>
          </button>
          <button type='button' class='layer-chip is-on' data-3d-toggle='slab' aria-pressed='true' title='Slab'>
            <span class='layer-glyph' aria-hidden='true'>
              <svg viewBox='0 0 24 24' role='img'>
                <path d='M3.8 12.7h16.4'/>
                <path d='M5.5 8h13'/>
                <path d='M5.5 15.4h13'/>
                <path d='M5.5 17.5h13'/>
                <path d='M5.5 6.2h13'/>
                <path d='M5.5 10.8h13'/>
                <path d='M5.5 13h13'/>
              </svg>
            </span>
            <span class='layer-chip-label'>Slab</span>
          </button>
        </div>
        <div class='dock-subhead'>AI Optimization Overlay Mode</div>
        <div class='overlay-mode-toolbar' role='group' aria-label='AI optimization overlay mode'>
          <button type='button' class='overlay-mode-button is-active' data-overlay-mode='member_type' aria-pressed='true'>Member type</button>
          <button type='button' class='overlay-mode-button' data-overlay-mode='dcr' aria-pressed='false'>D/C ratio</button>
          <button type='button' class='overlay-mode-button' data-overlay-mode='cost_delta' aria-pressed='false'>Cost delta</button>
          <button type='button' class='overlay-mode-button' data-overlay-mode='constructability' aria-pressed='false'>Constructability</button>
        </div>
        <div class='dock-subhead'>Legend</div>
        <div class='legend-strip' id='overlay-mode-legend' aria-live='polite'>
          <span class='legend-pill'><span class='legend-swatch' style='background:#6f91c9'></span>Beam</span>
          <span class='legend-pill'><span class='legend-swatch' style='background:#4c8b68'></span>Column</span>
          <span class='legend-pill'><span class='legend-swatch' style='background:#b76b46'></span>Wall</span>
          <span class='legend-pill'><span class='legend-swatch' style='background:#baa57a'></span>Slab</span>
          <span class='legend-pill'><span class='legend-swatch' style='background:#f05a28'></span>Selected</span>
        </div>
        <div class='dock-subhead'>MGT quick status</div>
        <div class='dock-status-line'>
          contract={"PASS" if mgt_export_contract_pass else "CHECK"} | mode={mgt_export_support_mode} | supported={mgt_export_supported_change_count}/{mgt_export_total_change_count or max(mgt_export_supported_change_count, 1)} | direct_patch={mgt_export_direct_patch_change_count} | zero_touch={mgt_export_instruction_sidecar_zero_touch_verified_change_count} | breadth={midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)} | exact={midas_roundtrip_gate_taxonomy_exact_count} canonical={midas_roundtrip_gate_taxonomy_canonical_count} | pending_review={midas_roundtrip_gate_pending_review_total}
        </div>
        <div class='dock-subhead'>Exports</div>
        <div class='link-row dock-links'>{mgt_artifact_links_html}</div>
      </aside>
      <article class='precision-pane'>
        <div class='precision-headline'>
          <div>
            <div class='drawing-eyebrow'>Interactive 3D</div>
            <h3>XYZ Structure + Optimized Overlay</h3>
          </div>
          <div class='precision-badges'>
            <span class='precision-metric'>Mode: {precision_mode}</span>
            <span class='precision-metric'>Baseline Segments: {baseline_segment_count}</span>
            <span class='precision-metric'>Optimized Segments: {after_segment_count}</span>
            <span class='precision-metric'>Changed Members: {changed_member_count}</span>
          </div>
        </div>
        <div class='precision-canvas-wrap' id='viewer-3d-wrap'>
          <canvas id='viewer-3d-canvas' width='1200' height='720' tabindex='0' aria-label='Interactive 3D structural workspace canvas. Use plus and minus to zoom, arrow keys or WASD to orbit, Shift plus arrow keys or WASD to pan, Escape to clear selection, and 0 or F to fit the view.'></canvas>
          <div id='viewer-selection-live' class='sr-only' aria-live='polite' aria-atomic='true'>No member selected</div>
          <div class='viewer-stage-hud' aria-label='3D drawing viewport status'>
            <span class='viewer-stage-chip is-live' data-full-label='XYZ model live' data-mobile-label='Live'></span>
            <span class='viewer-stage-chip' data-full-label='baseline / optimized overlay' data-mobile-label='Overlay'></span>
            <span class='viewer-stage-chip' data-full-label='row-linked member focus' data-mobile-label='Focus'></span>
          </div>
          <div class='viewer-axis-compass' aria-hidden='true'>
            <span class='viewer-axis-node is-x'>X</span>
            <span class='viewer-axis-node is-y'>Y</span>
            <span class='viewer-axis-node is-z'>Z</span>
          </div>
        <div class='viewer-status-ribbon' aria-hidden='true'>
          <span data-full-label='Drag orbit' data-mobile-label='Drag orbit'></span>
          <span data-full-label='Shift + drag pan' data-mobile-label='2-finger pan'></span>
          <span data-full-label='Pinch zoom / 2-finger pan' data-mobile-label='Pinch / pan'></span>
          <span data-full-label='Wheel zoom' data-mobile-label='Buttons zoom'></span>
          <span data-full-label='Click member to pin' data-mobile-label='Tap pin'></span>
        </div>
          <div class='viewer-viewport-controls' role='group' aria-label='3D viewport direct controls'>
            <button class='viewer-viewport-button' type='button' data-viewport-control='zoom-in' aria-label='Zoom in 3D view' title='Zoom in'>+</button>
            <button class='viewer-viewport-button' type='button' data-viewport-control='zoom-out' aria-label='Zoom out 3D view' title='Zoom out'>-</button>
            <button class='viewer-viewport-button' type='button' data-viewport-control='fit-view' aria-label='Fit and reset 3D view' title='Fit view'>Fit</button>
          </div>
          <div class='viewer-tooltip' id='viewer-3d-tooltip' aria-hidden='true'></div>
          <div class='selection-overlay is-empty' id='viewer-selection-overlay'>
            <div class='selection-overlay-head'>
              <div class='selection-overlay-title'>Selection</div>
              <div class='selection-overlay-actions'>
                <button class='selection-share-button' type='button' data-selection-share aria-label='Copy selected member, story, or grid deep link' disabled>Copy link</button>
                <button class='selection-clear-button' type='button' data-selection-clear aria-label='Clear selected member or grid bubble' disabled>Clear</button>
              </div>
            </div>
            <div class='selection-overlay-line selection-overlay-muted' id='viewer-selection-overlay-member'>No member selected</div>
            <div class='selection-overlay-line' id='viewer-selection-overlay-section'>Section: n/a</div>
            <div class='selection-overlay-line' id='viewer-selection-overlay-thickness'>Thickness: n/a</div>
            <div class='selection-overlay-line' id='viewer-selection-overlay-rebar'>Rebar: n/a</div>
          </div>
        </div>
        <div class='precision-caption'>{axis_ref_note or "Current geometry bridge does not expose explicit MIDAS axis names, so the workspace draws geometry-derived axis references on top of the true xyz segments."}</div>
        <div class='footnote'>
          드래그: 회전 | <strong>Shift + 드래그</strong>: pan | 휠: zoom | row 클릭: 선택 member center-fit<br>
          <strong>Axis source</strong>: {axis_ref_source_mode}{f" | {axis_ref_source_path}" if axis_ref_source_path else ""}<br>
          <strong>Axis refs</strong>: {axis_ref_label or "geometry-derived refs unavailable"}<br>
          더 깊은 drill-down이 필요하면 <strong>Core viewer</strong>에서 interactive 3D, row provenance, code-check slice까지 이어서 볼 수 있습니다.
        </div>
      </article>
      <aside class='inspector-panel'>
        <div class='inspector-eyebrow'>Selection Inspector</div>
        <h3>Before / After</h3>
        <div class='inspector-grid'>
          <div class='inspector-item'><div class='inspector-item-label'>Member</div><div class='inspector-item-value' id='inspector-member'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Lane</div><div class='inspector-item-value' id='inspector-lane'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Type / Story / Zone</div><div class='inspector-item-value' id='inspector-type'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Section</div><div class='inspector-item-value' id='inspector-section'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Thickness</div><div class='inspector-item-value' id='inspector-thickness'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Rebar</div><div class='inspector-item-value' id='inspector-rebar'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Coordinates</div><div class='inspector-item-value' id='inspector-coordinates'>n/a</div></div>
          <div class='inspector-item'><div class='inspector-item-label'>Snapshot</div><div class='inspector-item-value' id='inspector-snapshot'>선택된 member의 before/after note가 여기 고정으로 표시됩니다.</div></div>
        </div>
        <div class='inspector-evidence-card is-empty' id='inspector-evidence-card' aria-live='polite'>
          <div class='inspector-evidence-head'>
            <div class='inspector-evidence-title'>Review Evidence Card</div>
            <div class='inspector-evidence-badge' id='inspector-evidence-gate'>No evidence selected</div>
          </div>
          <div class='inspector-evidence-reason' id='inspector-evidence-reason'>No evidence selected.</div>
          <div class='inspector-evidence-grid'>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>Action</div><div class='inspector-evidence-value' id='inspector-evidence-action'>n/a</div></div>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>D/C after</div><div class='inspector-evidence-value' id='inspector-evidence-dcr'>n/a</div></div>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>Cost delta</div><div class='inspector-evidence-value' id='inspector-evidence-cost'>n/a</div></div>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>Constructability</div><div class='inspector-evidence-value' id='inspector-evidence-constructability'>n/a</div></div>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>Linked diff rows</div><div class='inspector-evidence-value' id='inspector-evidence-diff-count'>n/a</div></div>
            <div class='inspector-evidence-metric'><div class='inspector-evidence-label'>Diff focus</div><div class='inspector-evidence-value' id='inspector-evidence-diff-focus'>No data</div></div>
          </div>
          <div class='inspector-evidence-handoff' id='inspector-evidence-handoff'>Selection handoff: No data.</div>
        </div>
      </aside>
    </div>
  </section>

  <section class='section' id='drawing-what-changed'>
    <h2>What Changed</h2>
    <p class='lead'>어떤 member type과 zone에서 최적화가 집중됐는지 먼저 좁혀서 보는 요약입니다.</p>
    <div class='mini-card-grid'>{member_type_cards}</div>
    <div class='zone-chip-row'>{zone_chips}</div>
  </section>

  <section class='section' id='drawing-story-band-priorities'>
    <h2>Story Band Priorities</h2>
    <p class='lead'>cost proxy 변화량이 큰 story/zone 우선으로 정렬했습니다.</p>
    <div class='story-mini-strip'>
      <div class='story-mini-strip-head'>
        <div class='story-mini-strip-title'>Story mini-highlights</div>
        <div class='story-mini-strip-note'>Top {len(story_strip_rows)} of {story_rows_count} elevation slots are shown as compact chips so the strongest story bands read first, with slot rank and change share kept visible. Hover a chip to preview the 3D halo for that story band; click to center-fit the 3D view, lock the active story band, and highlight the matching rows.</div>
      </div>
      <div class='story-mini-strip-grid'>{story_mini_strip_html}</div>
    </div>
    <div class='table-wrap story-table-wrap'>
      <table>
        <thead>
          <tr>
            <th>Elevation slot</th>
            <th>Story</th>
            <th>Zone</th>
            <th>Member</th>
            <th>Groups</th>
            <th>Cost delta</th>
            <th>Constructability</th>
            <th>Max DCR after</th>
          </tr>
        </thead>
        <tbody>{story_rows_html}</tbody>
      </table>
    </div>
  </section>

  <section class='section' id='drawing-member-review'>
    <h2>Representative Changed Members</h2>
    <p class='lead'>가장 영향이 큰 부재를 먼저 추려서 확인할 수 있게 정리했습니다.</p>
    <input class='search-box' type='search' id='member-search' placeholder='member id, member type, story, zone, action으로 필터'>
    <div class='table-wrap member-table-wrap'>
      <table>
        <thead>
          <tr>
            <th>Member</th>
            <th>Type</th>
            <th>Story</th>
            <th>Zone</th>
            <th>Action</th>
            <th>Cost delta</th>
            <th>Constructability</th>
            <th>Snapshot</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody id='member-table-body'>{top_member_rows_html}</tbody>
      </table>
    </div>
  </section>
</div>
<script type='application/json' id='optimized-review-3d-data'>{interactive_3d_json}</script>
<script type='application/json' id='mgt-diff-row-index-map'>{mgt_diff_row_index_map_json}</script>
<script>
const REVIEW_3D = JSON.parse(document.getElementById('optimized-review-3d-data').textContent || '{{}}');
const mgtDiffRowIndexMap = JSON.parse(document.getElementById('mgt-diff-row-index-map').textContent || '{{}}');
const canvas = document.getElementById('viewer-3d-canvas');
const canvasWrap = document.getElementById('viewer-3d-wrap');
const context = canvas ? canvas.getContext('2d') : null;
const hoverTooltip = document.getElementById('viewer-3d-tooltip');
const toggleInputs = [...document.querySelectorAll('[data-3d-toggle]')];
const overlayModeButtons = [...document.querySelectorAll('[data-overlay-mode]')];
const overlayModeLegend = document.getElementById('overlay-mode-legend');
const memberRows = [...document.querySelectorAll('#member-table-body tr')];
const storyChipNodes = [...document.querySelectorAll('[data-story-chip]')];
const storyBandRows = [...document.querySelectorAll('[data-story-band-row]')];
const cameraButtons = [...document.querySelectorAll('[data-camera-preset]')];
const cameraFlipButton = document.querySelector('[data-camera-flip-180]');
const viewportControlButtons = [...document.querySelectorAll('[data-viewport-control]')];
const selectionLiveRegion = document.getElementById('viewer-selection-live');
const clearSelectionButton = document.querySelector('[data-selection-clear]');
const shareSelectionButton = document.querySelector('[data-selection-share]');
const compareRowNodes = [...document.querySelectorAll('[data-compare-row]')];
const comparePageRowNodes = [...document.querySelectorAll('[data-compare-page-row]')];
const comparePageTabButtons = [...document.querySelectorAll('[data-compare-page-tab]')];
const comparePagePanels = [...document.querySelectorAll('[data-compare-page-panel]')];
const comparePageNavButtons = [...document.querySelectorAll('[data-compare-page-nav]')];
const inspector = {{
  member: document.getElementById('inspector-member'),
  lane: document.getElementById('inspector-lane'),
  type: document.getElementById('inspector-type'),
  section: document.getElementById('inspector-section'),
  thickness: document.getElementById('inspector-thickness'),
  rebar: document.getElementById('inspector-rebar'),
  coordinates: document.getElementById('inspector-coordinates'),
  snapshot: document.getElementById('inspector-snapshot'),
  evidenceCard: document.getElementById('inspector-evidence-card'),
  evidenceGate: document.getElementById('inspector-evidence-gate'),
  evidenceReason: document.getElementById('inspector-evidence-reason'),
  evidenceAction: document.getElementById('inspector-evidence-action'),
  evidenceDcr: document.getElementById('inspector-evidence-dcr'),
  evidenceCost: document.getElementById('inspector-evidence-cost'),
  evidenceConstructability: document.getElementById('inspector-evidence-constructability'),
  evidenceDiffCount: document.getElementById('inspector-evidence-diff-count'),
  evidenceDiffFocus: document.getElementById('inspector-evidence-diff-focus'),
  evidenceHandoff: document.getElementById('inspector-evidence-handoff'),
}};
const selectionOverlay = {{
  container: document.getElementById('viewer-selection-overlay'),
  member: document.getElementById('viewer-selection-overlay-member'),
  section: document.getElementById('viewer-selection-overlay-section'),
  thickness: document.getElementById('viewer-selection-overlay-thickness'),
  rebar: document.getElementById('viewer-selection-overlay-rebar'),
}};
const WORKSPACE_SELECTION_CONTRACT_VERSION = {workspace_selection_contract_version_json};
const WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION = {workspace_diff_focus_contract_version_json};
const LEGACY_WORKSPACE_SELECTION_PARAMS = ['member', 'story', 'grid'];
const CANONICAL_WORKSPACE_SELECTION_PARAMS = [
  'selection_kind',
  'selection_id',
  'selection_label',
  'selection_provenance',
  'selection_story',
  'selection_contract_version',
];
const MIDAS_COLORS = {{
  beam: '#7aa7ff',
  column: '#62d9ad',
  wall: '#f08a58',
  slab: '#d7bd83',
  selected: '#ff6a2d',
  neutral: '#9aa8b5',
  baselineDim: 'rgba(142, 161, 181, 0.30)',
  grid: 'rgba(125, 208, 214, 0.16)',
  story: 'rgba(240, 184, 111, 0.14)',
  axisText: '#b9c8d1',
  bubbleFill: 'rgba(255, 251, 243, 0.95)',
  bubbleFillHover: 'rgba(255, 236, 203, 0.98)',
  bubbleFillSelected: 'rgba(255, 224, 191, 0.98)',
  bubbleStroke: 'rgba(137, 116, 90, 0.82)',
  bubbleStrokeHover: '#e28b16',
  bubbleStrokeSelected: '#f05a28',
  bubbleText: '#3e4e57',
  bubbleTextHover: '#6f4a09',
  bubbleTextSelected: '#7d1d08',
  gridTick: 'rgba(214, 231, 236, 0.72)',
}};
const viewerState = {{
  yaw: -0.88,
  pitch: 0.58,
  flipAxisSign: -1,
  panX: 0,
  panY: 0,
  scale: 1,
  dragging: false,
  panMode: false,
  pointerId: null,
  touchPoints: new Map(),
  pinchStartDistance: 0,
  pinchStartScale: 1,
  pinchStartCentroid: null,
  pointerDownX: 0,
  pointerDownY: 0,
  dragDistance: 0,
  lastTapEligible: true,
  renderQueued: false,
  startX: 0,
  startY: 0,
  selectedMemberId: '',
  selectedGridBubbleId: '',
  hoveredGridBubbleId: '',
  gridBubbles: [],
  hoveredSegmentKey: '',
  hoveredCompareMemberId: '',
  activeStoryBand: '',
  previewStoryBand: '',
  overlayMode: 'member_type',
  projectedSegments: [],
  viewPreset: 'iso',
  canvasCssWidth: 1200,
  canvasCssHeight: 720,
  pixelRatio: 1,
}};
function clamp(value, min, max) {{
  return Math.min(max, Math.max(min, value));
}}
function normalizeCameraAngle(value) {{
  const tau = Math.PI * 2;
  const wrapped = ((Number(value) || 0) % tau + tau) % tau;
  return wrapped > Math.PI ? wrapped - tau : wrapped;
}}
function parseDataList(value = '') {{
  return Array.from(
    new Set(
      String(value || '')
        .split(/[|,\s]+/)
        .map((token) => token.trim())
        .filter(Boolean)
    )
  );
}}
function normalizeStoryBandKey(value = '') {{
  const key = String(value || '').trim().toLowerCase();
  const storyMatch = key.match(/^s0*(\d+)$/);
  return storyMatch ? storyMatch[1].replace(/^0+(?=\d)/, '') : key.replace(/^0+(?=\d)/, '');
}}
function diffNodeSearchText(node) {{
  return [
    String(node?.dataset?.search || ''),
    String(node?.dataset?.memberId || ''),
    String(node?.dataset?.candidateMemberIds || ''),
    String(node?.dataset?.candidateSectionIds || ''),
    String(node?.dataset?.candidateCardIds || ''),
    String(node?.dataset?.geometryBridgeMemberIds || ''),
  ]
    .join(' ')
    .toLowerCase();
}}
function diffNodeExactMemberMatch(node, memberId) {{
  const exact = String(memberId || '').trim().toLowerCase();
  if (!exact) return false;
  return [
    String(node?.dataset?.memberId || ''),
    ...parseDataList(node?.dataset?.candidateMemberIds || ''),
    ...parseDataList(node?.dataset?.geometryBridgeMemberIds || ''),
  ].some((token) => String(token || '').trim().toLowerCase() === exact);
}}
function diffNodeRow(node) {{
  return node?.closest?.('.mgt-raw-diff-line') || node?.closest?.('.mgt-compare-row') || null;
}}
function getToggleState() {{
  return Object.fromEntries(
    toggleInputs.map((input) => {{
      const key = String(input.getAttribute('data-3d-toggle') || '').trim();
      const checked = input.type === 'checkbox'
        ? Boolean(input.checked)
        : input.getAttribute('aria-pressed') === 'true';
      return [key, checked];
    }})
  );
}}
function resizeCanvas() {{
  if (!canvas || !canvasWrap || !context) return;
  const rect = canvasWrap.getBoundingClientRect();
  const dpr = Math.min(Math.max(Number(window.devicePixelRatio || 1), 1), 2);
  const cssWidth = Math.max(1, Math.floor(rect.width));
  const cssHeight = Math.max(380, Math.floor(rect.height));
  const nextWidth = Math.round(cssWidth * dpr);
  const nextHeight = Math.round(cssHeight * dpr);
  if (canvas.width !== nextWidth || canvas.height !== nextHeight) {{
    canvas.width = nextWidth;
    canvas.height = nextHeight;
  }}
  viewerState.canvasCssWidth = cssWidth;
  viewerState.canvasCssHeight = cssHeight;
  viewerState.pixelRatio = dpr;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
}}
function viewportWidth() {{
  return Number(viewerState.canvasCssWidth || canvas?.getBoundingClientRect?.().width || canvas?.width || 0);
}}
function viewportHeight() {{
  return Number(viewerState.canvasCssHeight || canvas?.getBoundingClientRect?.().height || canvas?.height || 0);
}}
function extentSpan(extent) {{
  return Math.max(
    Number(extent.max_x || 0) - Number(extent.min_x || 0),
    Number(extent.max_y || 0) - Number(extent.min_y || 0),
    (Number(extent.max_z || 0) - Number(extent.min_z || 0)) * 3,
    1
  );
}}
function resetCamera(preset = 'iso') {{
  const extent = REVIEW_3D.extent || {{}};
  const span = extentSpan(extent);
  viewerState.viewPreset = preset;
  if (preset === 'top') {{
    viewerState.yaw = 0;
    viewerState.pitch = 0.001;
  }} else if (preset === 'front') {{
    viewerState.yaw = -Math.PI / 2;
    viewerState.pitch = Math.PI / 2.8;
  }} else if (preset === 'side') {{
    viewerState.yaw = 0;
    viewerState.pitch = Math.PI / 2.8;
  }} else {{
    viewerState.yaw = -0.88;
    viewerState.pitch = 0.58;
  }}
  viewerState.panX = 0;
  viewerState.panY = 0;
  viewerState.scale = clamp((Math.min(viewportWidth(), viewportHeight()) * 0.56) / span, 2.5, 12);
  cameraButtons.forEach((button) => button.classList.toggle('is-active', button.dataset.cameraPreset === preset));
  if (cameraFlipButton) {{
    cameraFlipButton.classList.toggle('is-active', viewerState.flipAxisSign === -1);
  }}
  render3D();
}}
function toggleCameraFlip180() {{
  viewerState.flipAxisSign *= -1;
  if (cameraFlipButton) {{
    cameraFlipButton.classList.toggle('is-active', viewerState.flipAxisSign === -1);
  }}
  render3D();
}}
function applyViewportControl(action) {{
  if (action === 'zoom-in') {{
    viewerState.scale = clamp(viewerState.scale * 1.16, 1.6, 30);
    render3D();
    return;
  }}
  if (action === 'zoom-out') {{
    viewerState.scale = clamp(viewerState.scale / 1.16, 1.6, 30);
    render3D();
    return;
  }}
  if (action === 'fit-view') {{
    resetCamera(viewerState.viewPreset || 'iso');
  }}
}}
function projectPoint(point) {{
  const extent = REVIEW_3D.extent || {{}};
  const cx = (Number(extent.min_x || 0) + Number(extent.max_x || 0)) / 2;
  const cy = (Number(extent.min_y || 0) + Number(extent.max_y || 0)) / 2;
  const cz = (Number(extent.min_z || 0) + Number(extent.max_z || 0)) / 2;
  const dx = Number(point[0] || 0) - cx;
  const dy = Number(point[1] || 0) - cy;
  const dz = Number(point[2] || 0) - cz;
  const flippedDx = viewerState.flipAxisSign === -1 ? -dx : dx;
  const flippedDz = viewerState.flipAxisSign === -1 ? -dz : dz;
  const yaw = viewerState.yaw;
  const cosYaw = Math.cos(yaw);
  const sinYaw = Math.sin(yaw);
  const cosPitch = Math.cos(viewerState.pitch);
  const sinPitch = Math.sin(viewerState.pitch);
  const x1 = flippedDx * cosYaw - dy * sinYaw;
  const y1 = flippedDx * sinYaw + dy * cosYaw;
  const z1 = flippedDz;
  const y2 = y1 * cosPitch - z1 * sinPitch;
  const z2 = y1 * sinPitch + z1 * cosPitch;
  return {{
    x: viewportWidth() / 2 + viewerState.panX + x1 * viewerState.scale,
    y: viewportHeight() / 2 + viewerState.panY - z2 * viewerState.scale,
    depth: y2,
  }};
}}
function projectedPointIsFinite(point) {{
  return Boolean(point)
    && Number.isFinite(Number(point.x))
    && Number.isFinite(Number(point.y))
    && Number.isFinite(Number(point.depth));
}}
function validPointArray(point) {{
  return Array.isArray(point)
    && point.length >= 3
    && point.slice(0, 3).every((value) => Number.isFinite(Number(value)));
}}
function isRenderableSegment(segment) {{
  return Boolean(segment)
    && segment.coordinate_valid !== false
    && validPointArray(segment.p0)
    && validPointArray(segment.p1);
}}
function coordinateFallbackReasonText(row) {{
  const diagnostics = row && row.coordinate_fallback_diagnostics && typeof row.coordinate_fallback_diagnostics === 'object'
    ? row.coordinate_fallback_diagnostics
    : {{}};
  const endpointReasons = diagnostics.endpoint_reasons && typeof diagnostics.endpoint_reasons === 'object'
    ? diagnostics.endpoint_reasons
    : {{}};
  const reasonPairs = Object.entries(endpointReasons)
    .filter(([endpoint, reason]) => displayText(endpoint, '') && displayText(reason, ''))
    .map(([endpoint, reason]) => `${{endpoint}}=${{reason}}`);
  if (reasonPairs.length) return reasonPairs.join(', ');
  const provenance = Array.isArray(row?.coordinate_fallback_provenance) ? row.coordinate_fallback_provenance : [];
  const provenancePairs = provenance
    .map((item) => item && typeof item === 'object' ? `${{displayText(item.endpoint || item.field, 'coord')}}=${{displayText(item.reason, 'invalid')}}` : '')
    .filter(Boolean);
  return provenancePairs.join(', ');
}}
function coordinateStatusText(row) {{
  if (!row) return 'coordinates unavailable (missing segment)';
  if (row.coordinate_valid === true) return 'coordinates valid';
  const status = displayText(row.coordinate_status, 'fallback');
  const fields = Array.isArray(row.coordinate_fallback_fields) && row.coordinate_fallback_fields.length
    ? row.coordinate_fallback_fields.join(', ')
    : 'p0/p1';
  const reasons = coordinateFallbackReasonText(row);
  const reasonText = reasons ? `; reason: ${{reasons}}` : '';
  return `coordinates unavailable (${{status}}; fallback: ${{fields}}${{reasonText}})`;
}}
function geometryAvailabilityText() {{
  if (REVIEW_3D.valid_geometry_available !== false) return 'Geometry available for rendering';
  const invalidCount = Number(REVIEW_3D.invalid_excluded_count || 0);
  return `Geometry audit: no valid rows; ${{invalidCount}} invalid rows excluded`;
}}
function projectedEntryVisible(entry) {{
  if (!projectedPointIsFinite(entry?.p0) || !projectedPointIsFinite(entry?.p1)) return false;
  const minX = Math.min(entry.p0.x, entry.p1.x);
  const maxX = Math.max(entry.p0.x, entry.p1.x);
  const minY = Math.min(entry.p0.y, entry.p1.y);
  const maxY = Math.max(entry.p0.y, entry.p1.y);
  return maxX >= -96 && minX <= viewportWidth() + 96 && maxY >= -96 && minY <= viewportHeight() + 96;
}}
function resetViewportToExtent() {{
  viewerState.panX = 0;
  viewerState.panY = 0;
  viewerState.scale = clamp((Math.min(viewportWidth(), viewportHeight()) * 0.56) / extentSpan(REVIEW_3D.extent || {{}}), 2.5, 12);
}}
function zoomAtCanvasPoint(canvasX, canvasY, zoomFactor) {{
  const beforeScale = viewerState.scale;
  const nextScale = clamp(beforeScale * Number(zoomFactor || 1), 1.6, 30);
  const scaleRatio = nextScale / (beforeScale || 1);
  const originX = viewportWidth() / 2;
  const originY = viewportHeight() / 2;
  viewerState.panX = canvasX - originX - (canvasX - originX - viewerState.panX) * scaleRatio;
  viewerState.panY = canvasY - originY - (canvasY - originY - viewerState.panY) * scaleRatio;
  viewerState.scale = nextScale;
}}
function gestureCentroid(points) {{
  const safePoints = points.filter(Boolean);
  if (!safePoints.length) return {{ x: viewportWidth() / 2, y: viewportHeight() / 2 }};
  const total = safePoints.reduce((sum, point) => ({{ x: sum.x + point.x, y: sum.y + point.y }}), {{ x: 0, y: 0 }});
  return {{ x: total.x / safePoints.length, y: total.y / safePoints.length }};
}}
function gestureDistance(points) {{
  if (points.length < 2) return 0;
  return Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
}}
function updatePinchGesture() {{
  const touchPoints = viewerState.touchPoints;
  if (touchPoints.size < 2) return false;
  const points = [...touchPoints.values()];
  const centroid = gestureCentroid(points);
  const distance = gestureDistance(points);
  if (!viewerState.pinchStartDistance) {{
    viewerState.pinchStartDistance = distance || 1;
    viewerState.pinchStartScale = viewerState.scale;
    viewerState.pinchStartCentroid = centroid;
    return true;
  }}
  const previousCentroid = viewerState.pinchStartCentroid || centroid;
  viewerState.panX += centroid.x - previousCentroid.x;
  viewerState.panY += centroid.y - previousCentroid.y;
  viewerState.pinchStartCentroid = centroid;
  const zoomFactor = distance / (viewerState.pinchStartDistance || distance || 1);
  zoomAtCanvasPoint(centroid.x, centroid.y, (viewerState.pinchStartScale * zoomFactor) / viewerState.scale);
  viewerState.lastTapEligible = false;
  return true;
}}
function lineDistance(px, py, ax, ay, bx, by) {{
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) return Math.hypot(px - ax, py - ay);
  const t = clamp(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1);
  const cx = ax + t * dx;
  const cy = ay + t * dy;
  return Math.hypot(px - cx, py - cy);
}}
function segmentKey(segment) {{
  const lane = String(segment?.lane || '');
  const memberId = String(segment?.member_id || '');
  return `${{lane}}:${{memberId}}`;
}}
function formatThickness(value) {{
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? `x${{numeric.toFixed(2)}}` : 'n/a';
}}
function formatRebar(value) {{
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric > 0 ? numeric.toFixed(3) : 'n/a';
}}
function displayText(value, fallback = 'n/a') {{
  const text = String(value ?? '').trim();
  return text ? text : fallback;
}}
function formatOptionalNumber(value, digits = 3) {{
  if (value === null || value === undefined || value === '') return 'n/a';
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : 'n/a';
}}
function memberRowsFor(memberId) {{
  return [...(REVIEW_3D.baseline_segments || []), ...(REVIEW_3D.after_segments || [])].filter(
    (row) => String(row.member_id || '') === String(memberId || '')
  );
}}
function buildSegmentMeta(segment) {{
  const memberId = String(segment?.member_id || '').trim();
  const after = memberRowsFor(memberId).find((row) => Object.prototype.hasOwnProperty.call(row, 'before_section'));
  const baseline = memberRowsFor(memberId).find((row) => !Object.prototype.hasOwnProperty.call(row, 'before_section'));
  const source = segment || after || baseline || {{}};
  const lane = String(source.lane || (after ? 'optimized' : 'baseline'));
  return {{
    memberId,
    lane: lane === 'optimized' ? 'optimized overlay' : 'baseline structure',
    memberType: String(source.member_type || source.category || 'segment'),
    story: String(source.story_band_label || 'story n/a'),
    zone: String(source.zone_label || 'zone n/a'),
    sectionBefore: String((after && after.before_section) || source.section_name || 'n/a') || 'n/a',
    sectionAfter: String((after && after.after_section) || source.section_name || 'n/a') || 'n/a',
    thicknessBefore: formatThickness((after && after.before_thickness_scale) ?? source.before_thickness_scale),
    thicknessAfter: formatThickness((after && after.after_thickness_scale) ?? source.after_thickness_scale),
    rebarBefore: formatRebar((after && after.before_rebar_ratio) ?? source.before_rebar_ratio),
    rebarAfter: formatRebar((after && after.after_rebar_ratio) ?? source.after_rebar_ratio),
    snapshot: String((after && after.before_after_snapshot_note) || source.before_after_snapshot_note || 'baseline member: direct before/after snapshot not available'),
    reason: displayText((after && (after.ai_reason || after.optimization_meaning_label)) || source.ai_reason || source.optimization_meaning_label, 'No data'),
    action: displayText((after && (after.action_name_label || after.action_name)) || source.action_name_label || source.action_name, 'n/a'),
    actionFamily: displayText((after && after.action_family_label) || source.action_family_label, 'n/a'),
    gate: displayText((after && after.selection_gate_label) || source.selection_gate_label, 'n/a'),
    dcrAfter: (after && after.max_dcr_after) ?? source.max_dcr_after,
    costDelta: (after && after.cost_delta) ?? source.cost_delta,
    constructabilityDelta: (after && after.constructability_delta) ?? source.constructability_delta,
    linkedDiffRowCount: (after && after.linked_diff_row_count) ?? source.linked_diff_row_count,
    diffFocus: displayText((after && (after.source_output_diff_focus || after.output_diff_focus)) || source.source_output_diff_focus || source.output_diff_focus, 'No data'),
    handoff: displayText((after && after.review_handoff_summary) || source.review_handoff_summary, 'No data'),
  }};
}}
function buildMemberMeta(memberId) {{
  const rows = memberRowsFor(memberId);
  const after = rows.find((row) => Object.prototype.hasOwnProperty.call(row, 'before_section'));
  const baseline = rows.find((row) => !Object.prototype.hasOwnProperty.call(row, 'before_section'));
  return buildSegmentMeta({{ ...(after || baseline || {{}}), lane: after ? 'optimized' : 'baseline' }});
}}
function setEvidenceCardState({{ gate = 'No evidence selected', reason = 'No evidence selected.', action = 'n/a', dcr = 'n/a', cost = 'n/a', constructability = 'n/a', diffCount = 'n/a', diffFocus = 'No data', handoff = 'No data', empty = false }} = {{}}) {{
  if (!inspector.evidenceCard) return;
  inspector.evidenceCard.classList.toggle('is-empty', Boolean(empty));
  if (inspector.evidenceGate) inspector.evidenceGate.textContent = displayText(gate, 'n/a');
  if (inspector.evidenceReason) inspector.evidenceReason.textContent = displayText(reason, 'No data');
  if (inspector.evidenceAction) inspector.evidenceAction.textContent = displayText(action, 'n/a');
  if (inspector.evidenceDcr) inspector.evidenceDcr.textContent = displayText(dcr, 'n/a');
  if (inspector.evidenceCost) inspector.evidenceCost.textContent = displayText(cost, 'n/a');
  if (inspector.evidenceConstructability) inspector.evidenceConstructability.textContent = displayText(constructability, 'n/a');
  if (inspector.evidenceDiffCount) inspector.evidenceDiffCount.textContent = displayText(diffCount, 'n/a');
  if (inspector.evidenceDiffFocus) inspector.evidenceDiffFocus.textContent = displayText(diffFocus, 'No data');
  if (inspector.evidenceHandoff) inspector.evidenceHandoff.textContent = `Selection handoff: ${{displayText(handoff, 'No data')}}`;
}}
function updateMemberEvidenceCard(memberId) {{
  const meta = buildMemberMeta(memberId);
  const mappedDiffRows = diffRowIndexesForMember(memberId);
  const hasExplicitDiffCount = meta.linkedDiffRowCount !== null && meta.linkedDiffRowCount !== undefined && meta.linkedDiffRowCount !== '';
  const explicitDiffCount = hasExplicitDiffCount ? Number(meta.linkedDiffRowCount) : NaN;
  const diffCount = Number.isFinite(explicitDiffCount) ? String(Math.round(explicitDiffCount)) : (mappedDiffRows.length ? String(mappedDiffRows.length) : 'n/a');
  const action = meta.actionFamily !== 'n/a' ? `${{meta.action}} / ${{meta.actionFamily}}` : meta.action;
  const handoff = meta.handoff !== 'No data'
    ? meta.handoff
    : `Review ${{meta.memberId || 'member'}} in the 3D selection, copy the canonical deep link, then inspect linked raw diff rows if present.`;
  setEvidenceCardState({{
    gate: meta.gate,
    reason: meta.reason,
    action,
    dcr: formatOptionalNumber(meta.dcrAfter, 3),
    cost: formatOptionalNumber(meta.costDelta, 3),
    constructability: formatOptionalNumber(meta.constructabilityDelta, 3),
    diffCount,
    diffFocus: meta.diffFocus,
    handoff,
    empty: false,
  }});
}}
function updateStoryEvidenceCard(storyBand) {{
  const label = displayText(storyBand, 'story aggregate');
  const counts = storyBandSelectionCounts(label);
  setEvidenceCardState({{
    gate: 'story aggregate',
    reason: `Story aggregate evidence for ${{label}}. Renderable rows, total rows, and excluded invalid rows are shown explicitly; select a member for AI reason and member-level handoff detail.`,
    action: 'story aggregate',
    dcr: 'n/a',
    cost: 'n/a',
    constructability: 'n/a',
    diffCount: 'n/a',
    diffFocus: `Renderable story segments: ${{counts.renderable}} of ${{counts.total}} total; ${{counts.invalidExcluded}} invalid rows excluded`,
    handoff: `Canonical selection deep link keeps ${{label}} reviewer handoff.`,
    empty: false,
  }});
}}
function updateGridEvidenceCard(bubble) {{
  if (!bubble) {{
    setEvidenceCardState({{ empty: true }});
    return;
  }}
  setEvidenceCardState({{
    gate: 'axis intersection',
    reason: `Grid axis intersection ${{bubble.label || 'intersection'}} selected. Select a member for optimization evidence.`,
    action: 'grid navigation',
    dcr: 'n/a',
    cost: 'n/a',
    constructability: 'n/a',
    diffCount: 'n/a',
    diffFocus: `${{bubble.xLabel || 'X'}} / ${{bubble.yLabel || 'Y'}}`,
    handoff: `Copy link preserves grid=${{bubble.id || bubble.label || 'intersection'}} for reviewer orientation.`,
    empty: false,
  }});
}}
function updateInspector(memberId) {{
  if (!memberId) {{
    inspector.member.textContent = 'n/a';
    inspector.lane.textContent = 'n/a';
    inspector.type.textContent = 'n/a';
    inspector.section.textContent = 'n/a';
    inspector.thickness.textContent = 'n/a';
    inspector.rebar.textContent = 'n/a';
    inspector.coordinates.textContent = 'n/a';
    inspector.snapshot.textContent = '선택된 항목이 없습니다.';
    setEvidenceCardState({{ empty: true }});
    return;
  }}
  const meta = buildMemberMeta(memberId);
  inspector.member.textContent = meta.memberId || 'n/a';
  inspector.lane.textContent = meta.lane;
  inspector.type.textContent = `${{meta.memberType}} | ${{meta.story}} | ${{meta.zone}}`;
  inspector.section.textContent = `${{meta.sectionBefore}} -> ${{meta.sectionAfter}}`;
  inspector.thickness.textContent = `${{meta.thicknessBefore}} -> ${{meta.thicknessAfter}}`;
  inspector.rebar.textContent = `${{meta.rebarBefore}} -> ${{meta.rebarAfter}}`;
  const coords = memberRowsFor(memberId)
    .slice(0, 4)
    .map((row) => {{
      if (!isRenderableSegment(row)) return coordinateStatusText(row);
      return '(' + row.p0.map((value) => Number(value).toFixed(2)).join(', ') + ') -> (' + row.p1.map((value) => Number(value).toFixed(2)).join(', ') + ')';
    }})
    .join('\\n');
  inspector.coordinates.textContent = coords || 'n/a';
  inspector.snapshot.textContent = meta.snapshot;
  updateMemberEvidenceCard(memberId);
}}
function updateSelectionOverlay(memberId) {{
  if (!selectionOverlay.container || !selectionOverlay.member || !selectionOverlay.section || !selectionOverlay.thickness || !selectionOverlay.rebar) {{
    return;
  }}
  if (!memberId) {{
    selectionOverlay.member.className = 'selection-overlay-line selection-overlay-muted';
    selectionOverlay.section.textContent = 'Section: n/a';
    selectionOverlay.thickness.textContent = 'Thickness: n/a';
    selectionOverlay.rebar.textContent = 'Rebar: n/a';
    selectionOverlay.member.textContent = 'No member selected';
    setSelectionOverlayEmpty(!viewerState.selectedGridBubbleId);
    announceSelection(viewerState.selectedGridBubbleId ? 'Grid bubble selected' : 'No member selected');
    return;
  }}
  const meta = buildMemberMeta(memberId);
  setSelectionOverlayEmpty(false);
  selectionOverlay.member.className = 'selection-overlay-line';
  selectionOverlay.member.textContent = `${{meta.memberId}} | ${{meta.memberType}} | ${{meta.story}} / ${{meta.zone}}`;
  selectionOverlay.section.textContent = `Section: ${{meta.sectionBefore}} -> ${{meta.sectionAfter}}`;
  selectionOverlay.thickness.textContent = `Thickness: ${{meta.thicknessBefore}} -> ${{meta.thicknessAfter}}`;
  selectionOverlay.rebar.textContent = `Rebar: ${{meta.rebarBefore}} -> ${{meta.rebarAfter}}`;
  announceSelection(`Pinned member ${{meta.memberId}}, ${{meta.memberType}}, ${{meta.story}} / ${{meta.zone}}`);
}}
function visibleSegmentKind(kind, toggles) {{
  if (!kind) return true;
  return Boolean(toggles[String(kind).toLowerCase()]);
}}
const OVERLAY_MODE_LEGENDS = {{
  member_type: [
    ['#7aa7ff', 'Beam'],
    ['#62d9ad', 'Column'],
    ['#f08a58', 'Wall'],
    ['#d7bd83', 'Slab'],
    ['#9aa8b5', 'Unknown type'],
    ['#ff6a2d', 'Selected'],
  ],
  dcr: [
    ['#42c77a', 'D/C <= 0.60'],
    ['#f0c85a', '0.60-0.85'],
    ['#f08a58', '0.85-1.00'],
    ['#d94a38', '> 1.00'],
    ['#9aa8b5', 'No D/C data'],
    ['#ff6a2d', 'Selected'],
  ],
  cost_delta: [
    ['#2fbf8f', 'Cost saving'],
    ['#8fd6ce', 'Small / neutral'],
    ['#f08a58', 'Cost increase'],
    ['#9aa8b5', 'No cost data'],
    ['#ff6a2d', 'Selected'],
  ],
  constructability: [
    ['#35c285', 'Easier to build'],
    ['#b8c6d1', 'Neutral'],
    ['#e0a64f', 'More complex'],
    ['#9aa8b5', 'No constructability data'],
    ['#ff6a2d', 'Selected'],
  ],
}};
function finiteMetric(value) {{
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}}
function colorForMemberType(segment, lane) {{
  const memberType = String(segment.member_type || segment.category || '').toLowerCase();
  if (lane === 'baseline') return MIDAS_COLORS[memberType] || MIDAS_COLORS.neutral;
  if (memberType === 'beam') return '#3f8cff';
  if (memberType === 'column') return '#35e6a2';
  if (memberType === 'wall') return '#ff7a4d';
  if (memberType === 'slab') return '#f0b86f';
  return segment.color || MIDAS_COLORS.neutral;
}}
function colorForDcr(segment) {{
  const dcr = finiteMetric(segment.max_dcr_after);
  if (dcr === null || dcr <= 0) return MIDAS_COLORS.neutral;
  if (dcr <= 0.6) return '#42c77a';
  if (dcr <= 0.85) return '#f0c85a';
  if (dcr <= 1.0) return '#f08a58';
  return '#d94a38';
}}
function colorForCostDelta(segment) {{
  const delta = finiteMetric(segment.cost_delta);
  if (delta === null) return MIDAS_COLORS.neutral;
  if (delta < -0.001) return '#2fbf8f';
  if (delta > 0.001) return '#f08a58';
  return '#8fd6ce';
}}
function colorForConstructability(segment) {{
  const delta = finiteMetric(segment.constructability_delta);
  if (delta === null) return MIDAS_COLORS.neutral;
  if (delta < -0.001) return '#35c285';
  if (delta > 0.001) return '#e0a64f';
  return '#b8c6d1';
}}
function colorForSegment(segment, lane, selected) {{
  if (selected) return MIDAS_COLORS.selected;
  const mode = String(viewerState.overlayMode || 'member_type');
  if (mode === 'dcr') return lane === 'optimized' ? colorForDcr(segment) : MIDAS_COLORS.neutral;
  if (mode === 'cost_delta') return lane === 'optimized' ? colorForCostDelta(segment) : MIDAS_COLORS.neutral;
  if (mode === 'constructability') return lane === 'optimized' ? colorForConstructability(segment) : MIDAS_COLORS.neutral;
  return colorForMemberType(segment, lane);
}}
function updateOverlayLegend() {{
  if (!overlayModeLegend) return;
  const mode = String(viewerState.overlayMode || 'member_type');
  const rows = OVERLAY_MODE_LEGENDS[mode] || OVERLAY_MODE_LEGENDS.member_type;
  overlayModeLegend.innerHTML = rows.map(([color, label]) => (
    `<span class='legend-pill'><span class='legend-swatch' style='background:${{color}}'></span>${{label}}</span>`
  )).join('');
}}
function setOverlayMode(mode) {{
  const nextMode = OVERLAY_MODE_LEGENDS[mode] ? mode : 'member_type';
  viewerState.overlayMode = nextMode;
  overlayModeButtons.forEach((button) => {{
    const active = button.dataset.overlayMode === nextMode;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-pressed', String(active));
  }});
  updateOverlayLegend();
  render3D();
}}
function drawPinnedLabel(label, x, y, options = {{}}) {{
  const text = String(label || '').trim();
  if (!text) return;
  const fontSize = Number(options.fontSize || 16);
  const fontWeight = String(options.fontWeight || '700');
  const offsetX = Number(options.offsetX || 0);
  const offsetY = Number(options.offsetY || 0);
  const paddingX = Number(options.paddingX || 8);
  const paddingY = Number(options.paddingY || 4);
  const bg = String(options.background || 'rgba(255, 250, 242, 0.92)');
  const stroke = String(options.stroke || 'rgba(110, 123, 136, 0.42)');
  const textColor = String(options.textColor || MIDAS_COLORS.axisText);
  const radius = Number(options.radius || 8);
  const finalX = x + offsetX;
  const finalY = y + offsetY;
  context.save();
  context.font = `${{fontWeight}} ${{fontSize}}px IBM Plex Sans KR, sans-serif`;
  const width = context.measureText(text).width + paddingX * 2;
  const height = fontSize + paddingY * 2;
  const left = finalX - width / 2;
  const top = finalY - height / 2;
  context.beginPath();
  context.moveTo(left + radius, top);
  context.lineTo(left + width - radius, top);
  context.quadraticCurveTo(left + width, top, left + width, top + radius);
  context.lineTo(left + width, top + height - radius);
  context.quadraticCurveTo(left + width, top + height, left + width - radius, top + height);
  context.lineTo(left + radius, top + height);
  context.quadraticCurveTo(left, top + height, left, top + height - radius);
  context.lineTo(left, top + radius);
  context.quadraticCurveTo(left, top, left + radius, top);
  context.closePath();
  context.fillStyle = bg;
  context.fill();
  context.strokeStyle = stroke;
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = textColor;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, finalX, finalY + 0.5);
  context.restore();
}}
function drawGridBubble(label, x, y, options = {{}}) {{
  const text = String(label || '').trim();
  if (!text) return;
  const fontSize = Number(options.fontSize || 10);
  const fontWeight = String(options.fontWeight || '700');
  const radius = Number(options.radius || 13);
  const state = String(options.state || 'normal');
  const palette = {{
    normal: {{
      fill: String(options.fill || MIDAS_COLORS.bubbleFill),
      stroke: String(options.stroke || MIDAS_COLORS.bubbleStroke),
      textColor: String(options.textColor || MIDAS_COLORS.bubbleText),
      lineWidth: Number(options.lineWidth || 1.4),
      radius: Number(options.radius || 12.8),
    }},
    hover: {{
      fill: String(options.hoverFill || MIDAS_COLORS.bubbleFillHover),
      stroke: String(options.hoverStroke || MIDAS_COLORS.bubbleStrokeHover),
      textColor: String(options.hoverTextColor || MIDAS_COLORS.bubbleTextHover),
      lineWidth: Number(options.hoverLineWidth || 2.1),
      radius: Number(options.radius || 13.4),
    }},
    selected: {{
      fill: String(options.selectedFill || MIDAS_COLORS.bubbleFillSelected),
      stroke: String(options.selectedStroke || MIDAS_COLORS.bubbleStrokeSelected),
      textColor: String(options.selectedTextColor || MIDAS_COLORS.bubbleTextSelected),
      lineWidth: Number(options.selectedLineWidth || 2.4),
      radius: Number(options.radius || 13.9),
    }},
  }};
  const style = palette[state] || palette.normal;
  context.save();
  context.beginPath();
  context.arc(x, y, style.radius || radius, 0, Math.PI * 2);
  context.fillStyle = style.fill;
  context.fill();
  context.strokeStyle = style.stroke;
  context.lineWidth = style.lineWidth;
  context.stroke();
  context.fillStyle = style.textColor;
  context.font = `${{fontWeight}} ${{fontSize}}px IBM Plex Sans KR, sans-serif`;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillText(text, x, y + 0.5);
  context.restore();
}}
function drawAxisTickMark(point, tangent, options = {{}}) {{
  const length = Number(options.length || 9);
  const x = Number(point?.x || 0);
  const y = Number(point?.y || 0);
  const vx = Number(tangent?.x || 0);
  const vy = Number(tangent?.y || 0);
  const magnitude = Math.hypot(vx, vy) || 1;
  const nx = -vy / magnitude;
  const ny = vx / magnitude;
  const half = length / 2;
  const p0 = {{ x: x + nx * half, y: y + ny * half }};
  const p1 = {{ x: x - nx * half, y: y - ny * half }};
  const color = String(options.color || MIDAS_COLORS.gridTick);
  context.save();
  context.strokeStyle = color;
  context.lineWidth = Number(options.lineWidth || 1.7);
  context.lineCap = 'round';
  context.beginPath();
  context.moveTo(p0.x, p0.y);
  context.lineTo(p1.x, p1.y);
  context.stroke();
  context.restore();
}}
function drawLabeledReferenceLine(p0, p1, label, color, dash = [6, 6], options = {{}}) {{
  const a = projectPoint(p0);
  const b = projectPoint(p1);
  context.save();
  context.strokeStyle = color;
  context.setLineDash(dash);
  context.lineWidth = Number(options.lineWidth || 1.6);
  context.beginPath();
  context.moveTo(a.x, a.y);
  context.lineTo(b.x, b.y);
  context.stroke();
  context.restore();
  const anchor = String(options.anchor || 'mid');
  const labelX = anchor === 'end' ? b.x : anchor === 'start' ? a.x : (a.x + b.x) / 2;
  const labelY = anchor === 'end' ? b.y : anchor === 'start' ? a.y : (a.y + b.y) / 2;
  drawPinnedLabel(label, labelX, labelY, options);
}}
function drawAxisRefs(toggles) {{
  if (!toggles.grid) return;
  const extent = REVIEW_3D.extent || {{}};
  const minX = Number(extent.min_x || 0);
  const maxX = Number(extent.max_x || 0);
  const minY = Number(extent.min_y || 0);
  const maxY = Number(extent.max_y || 0);
  const minZ = Number(extent.min_z || 0);
  (REVIEW_3D.axis_refs?.x || []).forEach((row) => {{
    const value = Number(row.value || 0);
    const start3d = [value, minY, minZ];
    const end3d = [value, maxY, minZ];
    const start = projectPoint(start3d);
    const end = projectPoint(end3d);
    const tangent = {{
      x: end.x - start.x,
      y: end.y - start.y,
    }};
    drawLabeledReferenceLine(
      start3d,
      end3d,
      String(row.label || 'X'),
      MIDAS_COLORS.grid,
      [10, 7],
      {{
        anchor: 'mid',
        fontSize: 17,
        fontWeight: '800',
        lineWidth: 1.8,
        offsetX: 0,
        offsetY: -14,
      }}
    );
    drawAxisTickMark(start, tangent, {{
      length: 10,
      color: MIDAS_COLORS.gridTick,
      lineWidth: 1.7,
    }});
    drawAxisTickMark(end, tangent, {{
      length: 10,
      color: MIDAS_COLORS.gridTick,
      lineWidth: 1.7,
    }});
  }});
  (REVIEW_3D.axis_refs?.y || []).forEach((row) => {{
    const value = Number(row.value || 0);
    const start3d = [minX, value, minZ];
    const end3d = [maxX, value, minZ];
    const start = projectPoint(start3d);
    const end = projectPoint(end3d);
    const tangent = {{
      x: end.x - start.x,
      y: end.y - start.y,
    }};
    drawLabeledReferenceLine(
      start3d,
      end3d,
      String(row.label || 'Y'),
      MIDAS_COLORS.grid,
      [10, 7],
      {{
        anchor: 'mid',
        fontSize: 17,
        fontWeight: '800',
        lineWidth: 1.8,
        offsetX: 0,
        offsetY: 14,
      }}
    );
    drawAxisTickMark(start, tangent, {{
      length: 10,
      color: MIDAS_COLORS.gridTick,
      lineWidth: 1.7,
    }});
    drawAxisTickMark(end, tangent, {{
      length: 10,
      color: MIDAS_COLORS.gridTick,
      lineWidth: 1.7,
    }});
  }});
}}
function drawAxisEdgeRepeatLabels(toggles) {{
  if (!toggles.grid) return;
  const extent = REVIEW_3D.extent || {{}};
  const minX = Number(extent.min_x || 0);
  const maxX = Number(extent.max_x || 0);
  const minY = Number(extent.min_y || 0);
  const maxY = Number(extent.max_y || 0);
  const minZ = Number(extent.min_z || 0);
  (REVIEW_3D.axis_refs?.x || []).forEach((row) => {{
    const value = Number(row.value || 0);
    const start = projectPoint([value, minY, minZ]);
    const end = projectPoint([value, maxY, minZ]);
    const top = start.y <= end.y ? start : end;
    const bottom = start.y <= end.y ? end : start;
    drawPinnedLabel(String(row.label || 'X'), top.x, top.y, {{
      fontSize: 18,
      fontWeight: '800',
      paddingX: 9,
      paddingY: 5,
      offsetY: -18,
      background: 'rgba(255, 248, 236, 0.96)',
      stroke: 'rgba(110, 123, 136, 0.50)',
    }});
    drawPinnedLabel(String(row.label || 'X'), bottom.x, bottom.y, {{
      fontSize: 18,
      fontWeight: '800',
      paddingX: 9,
      paddingY: 5,
      offsetY: 18,
      background: 'rgba(255, 248, 236, 0.96)',
      stroke: 'rgba(110, 123, 136, 0.50)',
    }});
  }});
  (REVIEW_3D.axis_refs?.y || []).forEach((row) => {{
    const value = Number(row.value || 0);
    const start = projectPoint([minX, value, minZ]);
    const end = projectPoint([maxX, value, minZ]);
    const left = start.x <= end.x ? start : end;
    const right = start.x <= end.x ? end : start;
    drawPinnedLabel(String(row.label || 'Y'), left.x, left.y, {{
      fontSize: 18,
      fontWeight: '800',
      paddingX: 9,
      paddingY: 5,
      offsetX: -22,
      background: 'rgba(255, 248, 236, 0.96)',
      stroke: 'rgba(110, 123, 136, 0.50)',
    }});
    drawPinnedLabel(String(row.label || 'Y'), right.x, right.y, {{
      fontSize: 18,
      fontWeight: '800',
      paddingX: 9,
      paddingY: 5,
      offsetX: 22,
      background: 'rgba(255, 248, 236, 0.96)',
      stroke: 'rgba(110, 123, 136, 0.50)',
    }});
  }});
}}
function stableGridBubbleId(xLabel, yLabel) {{
  return `${{String(xLabel || 'X').trim()}}-${{String(yLabel || 'Y').trim()}}`;
}}
function drawGridIntersectionBubbles(toggles) {{
  if (!toggles.grid) {{
    viewerState.gridBubbles = [];
    return;
  }}
  const extent = REVIEW_3D.extent || {{}};
  const minZ = Number(extent.min_z || 0);
  const xRows = Array.isArray(REVIEW_3D.axis_refs?.x) ? REVIEW_3D.axis_refs.x : [];
  const yRows = Array.isArray(REVIEW_3D.axis_refs?.y) ? REVIEW_3D.axis_refs.y : [];
  const hoveredId = String(viewerState.hoveredGridBubbleId || '');
  const selectedId = String(viewerState.selectedGridBubbleId || '');
  viewerState.gridBubbles = [];
  xRows.forEach((xRow) => {{
    yRows.forEach((yRow) => {{
      const xLabel = String(xRow.label || 'X');
      const yLabel = String(yRow.label || 'Y');
      const bubbleId = stableGridBubbleId(xLabel, yLabel);
      const point = projectPoint([Number(xRow.value || 0), Number(yRow.value || 0), minZ]);
      if (point.x < -32 || point.x > viewportWidth() + 32 || point.y < -32 || point.y > viewportHeight() + 32) return;
      const state = selectedId && bubbleId === selectedId
        ? 'selected'
        : hoveredId && bubbleId === hoveredId
          ? 'hover'
          : 'normal';
      viewerState.gridBubbles.push({{
        id: bubbleId,
        label: `${{xLabel}}-${{yLabel}}`,
        xLabel,
        yLabel,
        x: point.x,
        y: point.y,
        state,
      }});
      drawGridBubble(`${{String(xRow.label || 'X')}}-${{String(yRow.label || 'Y')}}`, point.x, point.y, {{
        fontSize: 9.5,
        radius: 12.5,
        state,
      }});
    }});
  }});
  return viewerState.gridBubbles;
}}
function drawStoryRefs(toggles) {{
  if (!toggles.stories) return;
  const extent = REVIEW_3D.extent || {{}};
  const minX = Number(extent.min_x || 0);
  const maxX = Number(extent.max_x || 0);
  const midY = (Number(extent.min_y || 0) + Number(extent.max_y || 0)) / 2;
  const activeStoryBandKey = normalizeStoryBandKey(viewerState.activeStoryBand || '');
  const previewStoryBandKey = normalizeStoryBandKey(viewerState.previewStoryBand || '');
  (REVIEW_3D.axis_refs?.z || []).forEach((row) => {{
    const value = Number(row.value || 0);
    const rowKey = normalizeStoryBandKey(row.label || '');
    const isActiveStoryBand = Boolean(activeStoryBandKey && rowKey === activeStoryBandKey);
    const isPreviewStoryBand = !isActiveStoryBand && Boolean(previewStoryBandKey && rowKey === previewStoryBandKey);
    drawLabeledReferenceLine(
      [minX, midY, value],
      [maxX, midY, value],
      String(row.label || 'Z'),
      isActiveStoryBand ? 'rgba(15, 106, 115, 0.42)' : isPreviewStoryBand ? 'rgba(56, 124, 232, 0.34)' : MIDAS_COLORS.story,
      [4, 8],
      {{
        anchor: 'end',
        fontSize: isActiveStoryBand ? 14 : isPreviewStoryBand ? 13.5 : 13,
        fontWeight: isActiveStoryBand ? '800' : isPreviewStoryBand ? '760' : '700',
        lineWidth: isActiveStoryBand ? 2.2 : isPreviewStoryBand ? 1.8 : 1.2,
        offsetX: 12,
        offsetY: -8,
        background: isActiveStoryBand
          ? 'rgba(236, 251, 252, 0.98)'
          : isPreviewStoryBand
            ? 'rgba(241, 247, 255, 0.98)'
            : 'rgba(248, 252, 252, 0.88)',
        stroke: isActiveStoryBand
          ? 'rgba(15, 106, 115, 0.42)'
          : isPreviewStoryBand
            ? 'rgba(56, 124, 232, 0.38)'
            : 'rgba(125, 208, 214, 0.38)',
      }}
    );
  }});
}}
function drawAxisTriad() {{
  const origin = {{ x: 84, y: viewportHeight() - 72 }};
  const size = 48;
  const axes = [
    {{ label: 'X', dx: size, dy: 0, color: '#b03f5b' }},
    {{ label: 'Y', dx: size * 0.68, dy: -size * 0.55, color: '#0f6a73' }},
    {{ label: 'Z', dx: 0, dy: -size, color: '#2463eb' }},
  ];
  context.save();
  context.lineWidth = 2.2;
  context.font = '12px IBM Plex Sans KR, sans-serif';
  axes.forEach((axis) => {{
    context.strokeStyle = axis.color;
    context.fillStyle = axis.color;
    context.beginPath();
    context.moveTo(origin.x, origin.y);
    context.lineTo(origin.x + axis.dx, origin.y + axis.dy);
    context.stroke();
    context.fillText(axis.label, origin.x + axis.dx + 6, origin.y + axis.dy + 4);
  }});
  context.restore();
}}
function segmentSelectionCentroid(segmentEntries) {{
  if (!segmentEntries.length) return {{ x: viewportWidth() / 2, y: viewportHeight() / 2 }};
  const x = segmentEntries.reduce((acc, entry) => acc + entry.p0.x + entry.p1.x, 0) / (segmentEntries.length * 2);
  const y = segmentEntries.reduce((acc, entry) => acc + entry.p0.y + entry.p1.y, 0) / (segmentEntries.length * 2);
  return {{ x, y }};
}}
function drawMemberMetaOverlay(memberId, segmentEntries, options = {{}}) {{
  const normalizedMemberId = String(memberId || '').trim();
  if (!normalizedMemberId || !segmentEntries.length) return;
  const meta = buildMemberMeta(normalizedMemberId);
  const centroid = segmentSelectionCentroid(segmentEntries);
  const state = String(options.state || 'normal');
  const palette = {{
    selected: {{
      background: 'rgba(255, 245, 227, 0.98)',
      stroke: '#d57a23',
      textColor: '#432808',
      lineWidth: 2.2,
    }},
    hover: {{
      background: 'rgba(242, 251, 253, 0.98)',
      stroke: '#1b8d96',
      textColor: '#1f3841',
      lineWidth: 1.6,
    }},
    normal: {{
      background: 'rgba(250, 252, 253, 0.97)',
      stroke: 'rgba(74, 94, 110, 0.85)',
      textColor: '#2d3f4a',
      lineWidth: 1.4,
    }},
  }};
  const style = palette[state] || palette.normal;
  const sectionBadge = `${{meta.sectionBefore}} -> ${{meta.sectionAfter}}`;
  const detail = `thk: ${{meta.thicknessBefore}} -> ${{meta.thicknessAfter}} / rebar: ${{meta.rebarBefore}} -> ${{meta.rebarAfter}}`;
  drawPinnedLabel(`${{meta.memberId}} (${{meta.memberType}})`, centroid.x + 12, centroid.y - 34, {{
    fontSize: 12,
    fontWeight: '800',
    paddingX: 10,
    paddingY: 5,
    background: style.background,
    stroke: style.stroke,
    textColor: style.textColor,
    lineWidth: style.lineWidth,
    radius: 9,
  }});
  drawPinnedLabel(`${{meta.story}} / ${{meta.zone}}`, centroid.x + 12, centroid.y - 16, {{
    fontSize: 11,
    fontWeight: '700',
    paddingX: 10,
    paddingY: 4,
    background: style.background,
    stroke: style.stroke,
    textColor: style.textColor,
    lineWidth: style.lineWidth,
    radius: 9,
  }});
  drawPinnedLabel(sectionBadge, centroid.x + 12, centroid.y + 4, {{
    fontSize: 11,
    fontWeight: '700',
    paddingX: 10,
    paddingY: 4,
    background: style.background,
    stroke: style.stroke,
    textColor: style.textColor,
    lineWidth: style.lineWidth,
    radius: 9,
  }});
  drawPinnedLabel(detail, centroid.x + 12, centroid.y + 22, {{
    fontSize: 10,
    fontWeight: '600',
    paddingX: 10,
    paddingY: 4,
    background: style.background,
    stroke: style.stroke,
    textColor: style.textColor,
    lineWidth: style.lineWidth,
    radius: 9,
  }});
}}
function drawMemberHoverHalo(entry) {{
  context.save();
  context.strokeStyle = 'rgba(240, 90, 40, 0.96)';
  context.setLineDash([10, 6]);
  context.lineCap = 'round';
  context.lineWidth = 6.2;
  context.globalAlpha = 0.95;
  context.beginPath();
  context.moveTo(entry.p0.x, entry.p0.y);
  context.lineTo(entry.p1.x, entry.p1.y);
  context.stroke();
  context.restore();
}}
function drawStoryBandHalo(entry, options = {{}}) {{
  const preview = Boolean(options.preview);
  context.save();
  context.strokeStyle = preview ? 'rgba(56, 124, 232, 0.90)' : 'rgba(15, 106, 115, 0.92)';
  context.setLineDash(preview ? [8, 5] : [12, 6]);
  context.lineCap = 'round';
  context.lineWidth = preview ? 4.4 : 5.4;
  context.globalAlpha = preview ? 0.82 : 0.92;
  context.beginPath();
  context.moveTo(entry.p0.x, entry.p0.y);
  context.lineTo(entry.p1.x, entry.p1.y);
  context.stroke();
  context.restore();
}}
function hideTooltip() {{
  if (!hoverTooltip) return;
  hoverTooltip.classList.remove('is-visible');
  hoverTooltip.setAttribute('aria-hidden', 'true');
}}
function showGridBubbleTooltip(bubble, offsetX, offsetY) {{
  if (!hoverTooltip || !canvasWrap || !bubble) return;
  hoverTooltip.innerHTML = `
    <div class='viewer-tooltip-title'>Grid Intersection</div>
    <div class='viewer-tooltip-grid'>
      <div class='viewer-tooltip-label'>Grid</div><div>${{bubble.label || ''}}</div>
      <div class='viewer-tooltip-label'>Axis X</div><div>${{bubble.xLabel || ''}}</div>
      <div class='viewer-tooltip-label'>Axis Y</div><div>${{bubble.yLabel || ''}}</div>
      <div class='viewer-tooltip-label'>State</div><div>${{bubble.state || 'normal'}}</div>
    </div>
  `;
  hoverTooltip.style.left = `${{Math.max(10, offsetX + 14)}}px`;
  hoverTooltip.style.top = `${{Math.max(10, offsetY + 14)}}px`;
  const wrapRect = canvasWrap.getBoundingClientRect();
  const tipRect = hoverTooltip.getBoundingClientRect();
  const maxLeft = Math.max(10, wrapRect.width - tipRect.width - 12);
  const maxTop = Math.max(10, wrapRect.height - tipRect.height - 12);
  hoverTooltip.style.left = `${{Math.min(Math.max(10, offsetX + 14), maxLeft)}}px`;
  hoverTooltip.style.top = `${{Math.min(Math.max(10, offsetY + 14), maxTop)}}px`;
  hoverTooltip.classList.add('is-visible');
  hoverTooltip.setAttribute('aria-hidden', 'false');
}}
function showTooltip(entry, offsetX, offsetY) {{
  if (!hoverTooltip || !canvasWrap) return;
  const meta = buildSegmentMeta(entry.segment);
  hoverTooltip.innerHTML = `
    <div class='viewer-tooltip-title'>${{meta.memberId || 'member'}} | ${{meta.memberType}}</div>
    <div class='viewer-tooltip-grid'>
      <div class='viewer-tooltip-label'>Lane</div><div>${{meta.lane}}</div>
      <div class='viewer-tooltip-label'>Story</div><div>${{meta.story}}</div>
      <div class='viewer-tooltip-label'>Zone</div><div>${{meta.zone}}</div>
      <div class='viewer-tooltip-label'>Section</div><div>${{meta.sectionBefore}} -> ${{meta.sectionAfter}}</div>
      <div class='viewer-tooltip-label'>Thickness</div><div>${{meta.thicknessBefore}} -> ${{meta.thicknessAfter}}</div>
      <div class='viewer-tooltip-label'>Rebar</div><div>${{meta.rebarBefore}} -> ${{meta.rebarAfter}}</div>
    </div>
    <div class='viewer-tooltip-note'>${{meta.snapshot}}</div>
  `;
  hoverTooltip.style.left = `${{Math.max(10, offsetX + 14)}}px`;
  hoverTooltip.style.top = `${{Math.max(10, offsetY + 14)}}px`;
  const wrapRect = canvasWrap.getBoundingClientRect();
  const tipRect = hoverTooltip.getBoundingClientRect();
  const maxLeft = Math.max(10, wrapRect.width - tipRect.width - 12);
  const maxTop = Math.max(10, wrapRect.height - tipRect.height - 12);
  hoverTooltip.style.left = `${{Math.min(Math.max(10, offsetX + 14), maxLeft)}}px`;
  hoverTooltip.style.top = `${{Math.min(Math.max(10, offsetY + 14), maxTop)}}px`;
  hoverTooltip.classList.add('is-visible');
  hoverTooltip.setAttribute('aria-hidden', 'false');
}}
function updateGridBubbleInspector(bubble) {{
  if (!inspector.member) return;
  if (!bubble) {{
    inspector.member.textContent = 'n/a';
    inspector.lane.textContent = 'n/a';
    inspector.type.textContent = 'n/a';
    inspector.section.textContent = 'n/a';
    inspector.thickness.textContent = 'n/a';
    inspector.rebar.textContent = 'n/a';
    inspector.coordinates.textContent = 'n/a';
    inspector.snapshot.textContent = '선택된 항목이 없습니다.';
    if (!viewerState.selectedMemberId) {{
      setSelectionOverlayEmpty(true);
      announceSelection('No member selected');
    }}
    updateGridEvidenceCard(null);
    return;
  }}
  inspector.member.textContent = `Grid ${{bubble.label || 'intersection'}}`;
  inspector.lane.textContent = 'grid map';
  inspector.type.textContent = 'axis intersection';
  inspector.section.textContent = `${{bubble.xLabel || 'X'}} / ${{bubble.yLabel || 'Y'}}`;
  inspector.thickness.textContent = 'n/a';
  inspector.rebar.textContent = 'n/a';
  inspector.coordinates.textContent = `${{bubble.xLabel || 'X'}} / ${{bubble.yLabel || 'Y'}}`;
  inspector.snapshot.textContent = '그리드 교차점 선택: 축명 표시';
  if (selectionOverlay.member && selectionOverlay.section && selectionOverlay.thickness && selectionOverlay.rebar) {{
    setSelectionOverlayEmpty(false);
    selectionOverlay.member.className = 'selection-overlay-line';
    selectionOverlay.member.textContent = `Grid ${{bubble.label || 'intersection'}}`;
    selectionOverlay.section.textContent = `Axes: ${{bubble.xLabel || 'X'}} / ${{bubble.yLabel || 'Y'}}`;
    selectionOverlay.thickness.textContent = 'Type: axis intersection';
    selectionOverlay.rebar.textContent = 'Member: n/a';
  }}
  updateGridEvidenceCard(bubble);
  announceSelection(`Pinned grid ${{bubble.label || 'intersection'}}, axes ${{bubble.xLabel || 'X'}} / ${{bubble.yLabel || 'Y'}}`);
}}
function collectRenderableSegments(toggles) {{
  const renderables = [];
  if (toggles.baseline) {{
    (REVIEW_3D.baseline_segments || []).forEach((segment) => {{
      if (!visibleSegmentKind(segment.member_type || segment.category, toggles)) return;
      if (!isRenderableSegment(segment)) return;
      renderables.push({{ ...segment, lane: 'baseline' }});
    }});
  }}
  if (toggles.optimized) {{
    (REVIEW_3D.after_segments || []).forEach((segment) => {{
      if (!visibleSegmentKind(segment.member_type || segment.category, toggles)) return;
      if (!isRenderableSegment(segment)) return;
      renderables.push({{ ...segment, lane: 'optimized' }});
    }});
  }}
  return renderables;
}}
function drawStageGridBackdrop() {{
  const step = 44;
  const width = viewportWidth();
  const height = viewportHeight();
  context.save();
  context.strokeStyle = 'rgba(125, 208, 214, 0.055)';
  context.lineWidth = 1;
  for (let x = 0; x <= width; x += step) {{
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }}
  for (let y = 0; y <= height; y += step) {{
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }}
  const vignette = context.createRadialGradient(
    width * 0.5,
    height * 0.42,
    width * 0.08,
    width * 0.5,
    height * 0.42,
    Math.max(width, height) * 0.68
  );
  vignette.addColorStop(0, 'rgba(125, 208, 214, 0.08)');
  vignette.addColorStop(0.62, 'rgba(8, 17, 27, 0)');
  vignette.addColorStop(1, 'rgba(0, 0, 0, 0.30)');
  context.fillStyle = vignette;
  context.fillRect(0, 0, width, height);
  context.restore();
}}
function drawNoValidGeometryNotice() {{
  if (REVIEW_3D.valid_geometry_available !== false) return;
  const message = geometryAvailabilityText();
  context.save();
  context.fillStyle = 'rgba(8, 19, 31, 0.78)';
  context.strokeStyle = 'rgba(255, 190, 96, 0.52)';
  context.lineWidth = 1.2;
  const width = Math.min(520, Math.max(280, viewportWidth() - 64));
  const height = 74;
  const x = (viewportWidth() - width) / 2;
  const y = Math.max(92, viewportHeight() * 0.28);
  context.fillRect(x, y, width, height);
  context.strokeRect(x, y, width, height);
  context.fillStyle = '#ffd28a';
  context.font = '700 15px sans-serif';
  context.textAlign = 'center';
  context.fillText(message, viewportWidth() / 2, y + 32);
  context.fillStyle = 'rgba(232, 244, 255, 0.78)';
  context.font = '12px sans-serif';
  context.fillText('Invalid rows stay excluded from extent, axis refs, camera fit, and hit testing; fallback points remain shape-compatible only.', viewportWidth() / 2, y + 54);
  context.restore();
}}
function scheduleRender3D() {{
  if (viewerState.renderQueued) return;
  viewerState.renderQueued = true;
  window.requestAnimationFrame(() => render3DNow());
}}
function render3D() {{
  scheduleRender3D();
}}
function render3DNow() {{
  viewerState.renderQueued = false;
  if (!context || !canvas) return;
  resizeCanvas();
  const toggles = getToggleState();
  const width = viewportWidth();
  const height = viewportHeight();
  context.clearRect(0, 0, width, height);
  const stageGradient = context.createLinearGradient(0, 0, 0, height);
  stageGradient.addColorStop(0, '#08131f');
  stageGradient.addColorStop(0.55, '#0d1c29');
  stageGradient.addColorStop(1, '#111f2d');
  context.fillStyle = stageGradient;
  context.fillRect(0, 0, width, height);
  drawStageGridBackdrop();
  drawNoValidGeometryNotice();
  drawAxisRefs(toggles);
  drawStoryRefs(toggles);
  const buildProjectedRenderables = () => collectRenderableSegments(toggles).map((segment) => {{
    const p0 = projectPoint(segment.p0);
    const p1 = projectPoint(segment.p1);
    const depth = (Number(p0.depth) + Number(p1.depth)) / 2;
    return {{ segment, p0, p1, depth }};
  }}).filter((entry) => projectedPointIsFinite(entry.p0) && projectedPointIsFinite(entry.p1) && Number.isFinite(entry.depth));
  let renderables = buildProjectedRenderables();
  if (renderables.length && !renderables.some((entry) => projectedEntryVisible(entry))) {{
    resetViewportToExtent();
    renderables = buildProjectedRenderables();
  }}
  renderables.sort((a, b) => a.depth - b.depth);
  viewerState.projectedSegments = renderables;
  const selectedId = String(viewerState.selectedMemberId || '');
  const hoveredKey = String(viewerState.hoveredSegmentKey || '');
  const activeStoryBandKey = normalizeStoryBandKey(viewerState.activeStoryBand || '');
  const previewStoryBandKey = normalizeStoryBandKey(viewerState.previewStoryBand || '');
  const hoveredEntry = hoveredKey
    ? renderables.find((entry) => segmentKey(entry.segment) === hoveredKey)
    : null;
  const hoveredMemberId = String(
    viewerState.hoveredCompareMemberId || (hoveredEntry ? String(hoveredEntry.segment.member_id || '') : '')
  );
  renderables.forEach((entry) => {{
    const selected = selectedId && String(entry.segment.member_id || '') === selectedId;
    const hovered = hoveredKey && segmentKey(entry.segment) === hoveredKey;
    const hoveredMember = hoveredMemberId && String(entry.segment.member_id || '') === hoveredMemberId;
    const entryStoryBandKey = normalizeStoryBandKey(entry.segment.story_band_label || '');
    const storyBandActive = activeStoryBandKey && entryStoryBandKey === activeStoryBandKey;
    const storyBandPreview = !storyBandActive && previewStoryBandKey && entryStoryBandKey === previewStoryBandKey;
    const lane = entry.segment.lane;
    const color = colorForSegment(entry.segment, lane, selected);
    context.save();
    context.strokeStyle = color;
    context.lineWidth = selected ? 4.4 : storyBandActive ? 3.9 : hovered ? 3.4 : lane === 'optimized' ? 2.6 : 1.4;
    context.globalAlpha = selected ? 1 : storyBandActive ? 0.98 : hovered ? 1 : lane === 'baseline' ? 0.34 : 0.92;
    context.beginPath();
    context.moveTo(entry.p0.x, entry.p0.y);
    context.lineTo(entry.p1.x, entry.p1.y);
    context.stroke();
    context.restore();
    if (hoveredMember && !selected) {{
      drawMemberHoverHalo(entry);
    }}
    if (storyBandActive && !selected) {{
      drawStoryBandHalo(entry);
    }}
    if (storyBandPreview) {{
      drawStoryBandHalo(entry, {{ preview: true }});
    }}
  }});
  if (selectedId) {{
    const selectedEntries = renderables.filter((entry) => String(entry.segment.member_id || '') === selectedId);
    drawMemberMetaOverlay(selectedId, selectedEntries, {{ state: 'selected' }});
  }}
  if (!selectedId && hoveredMemberId) {{
    const hoveredEntries = renderables.filter((entry) => String(entry.segment.member_id || '') === hoveredMemberId);
    drawMemberMetaOverlay(hoveredMemberId, hoveredEntries, {{ state: 'hover' }});
  }}
  drawAxisEdgeRepeatLabels(toggles);
  drawGridIntersectionBubbles(toggles);
  drawAxisTriad();
}}
function focusMember(memberId) {{
  const matches = [...(REVIEW_3D.baseline_segments || []), ...(REVIEW_3D.after_segments || [])].filter(
    (row) => String(row.member_id || '') === String(memberId || '') && isRenderableSegment(row)
  );
  if (!matches.length) return;
  const xs = matches.flatMap((row) => [Number(row.p0[0]), Number(row.p1[0])]);
  const ys = matches.flatMap((row) => [Number(row.p0[1]), Number(row.p1[1])]);
  const zs = matches.flatMap((row) => [Number(row.p0[2]), Number(row.p1[2])]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const cz = (Math.min(...zs) + Math.max(...zs)) / 2;
  const extent = REVIEW_3D.extent || {{}};
  const globalCenterX = (Number(extent.min_x || 0) + Number(extent.max_x || 0)) / 2;
  const globalCenterY = (Number(extent.min_y || 0) + Number(extent.max_y || 0)) / 2;
  const globalCenterZ = (Number(extent.min_z || 0) + Number(extent.max_z || 0)) / 2;
  const span = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys), (Math.max(...zs) - Math.min(...zs)) * 4, 1);
  viewerState.scale = clamp((Math.min(viewportWidth(), viewportHeight()) * 0.32) / span, 1.6, 22);
  const target = projectPoint([cx, cy, cz]);
  const worldProjection = projectPoint([globalCenterX, globalCenterY, globalCenterZ]);
  if (!projectedPointIsFinite(target) || !projectedPointIsFinite(worldProjection)) {{
    resetViewportToExtent();
    return;
  }}
  viewerState.panX += worldProjection.x - target.x;
  viewerState.panY += worldProjection.y - target.y;
}}
function storyBandSegmentsFor(storyBand) {{
  const key = normalizeStoryBandKey(storyBand);
  if (!key) return [];
  return [...(REVIEW_3D.baseline_segments || []), ...(REVIEW_3D.after_segments || [])].filter(
    (row) => normalizeStoryBandKey(row.story_band_label || '') === key
  );
}}
function storyBandSelectionCounts(storyBand) {{
  const matches = storyBandSegmentsFor(storyBand);
  const renderableMatches = matches.filter(isRenderableSegment);
  return {{
    total: matches.length,
    renderable: renderableMatches.length,
    focusable: renderableMatches.length,
    invalidExcluded: Math.max(0, matches.length - renderableMatches.length),
    matches,
    renderableMatches,
  }};
}}
function syncStoryBandState(storyBand) {{
  const label = String(storyBand || '').trim();
  const key = normalizeStoryBandKey(label);
  viewerState.activeStoryBand = label;
  storyChipNodes.forEach((node) => {{
    const nodeKey = normalizeStoryBandKey(node.dataset.storyBandKey || node.dataset.storyBand || '');
    const active = Boolean(key && nodeKey === key);
    node.classList.toggle('is-active', active);
    node.setAttribute('aria-pressed', String(active));
  }});
  storyBandRows.forEach((row) => {{
    const rowKey = normalizeStoryBandKey(row.dataset.storyBandKey || row.dataset.storyBand || '');
    const active = Boolean(key && rowKey === key);
    row.classList.toggle('is-story-active', active);
    row.setAttribute('aria-selected', String(active));
  }});
  memberRows.forEach((row) => {{
    const rowKey = normalizeStoryBandKey(row.dataset.storyBandKey || row.dataset.storyBand || '');
    row.classList.toggle('is-story-active', Boolean(key && rowKey === key));
  }});
}}
function setActiveStoryBand(storyBand, options = {{}}) {{
  syncStoryBandState(storyBand);
  viewerState.previewStoryBand = '';
  if (options.syncUrl !== false) {{
    syncWorkspaceUrlState({{ replace: true }});
  }}
  if (options.render !== false) {{
    render3D();
  }}
}}
function setPreviewStoryBand(storyBand, options = {{}}) {{
  const label = String(storyBand || '').trim();
  if (viewerState.previewStoryBand === label && options.render !== true) return;
  viewerState.previewStoryBand = label;
  if (options.render !== false) {{
    render3D();
  }}
}}
function focusStoryBand(storyBand, options = {{}}) {{
  return commitWorkspaceSelection({{ kind: 'story', id: storyBand, source: options.source || 'story' }}, options);
}}
function applyWorkspaceStorySelection(storyBand, options = {{}}) {{
  const counts = storyBandSelectionCounts(storyBand);
  const focusMatches = counts.renderableMatches;
  viewerState.selectedMemberId = '';
  viewerState.selectedGridBubbleId = '';
  memberRows.forEach((row) => {{
    row.classList.toggle('is-selected-row', false);
    row.setAttribute('aria-selected', 'false');
  }});
  updateGridBubbleInspector(null);
  setActiveStoryBand(storyBand, {{ render: false, syncUrl: options.syncUrl }});
  updateStorySelectionOverlay(storyBand);
  if (options.syncDiff !== false) {{
    syncWorkspaceDiffFocus(workspaceSelectionState(), options);
  }}
  if (options.centerFit === false) {{
    if (options.render !== false) {{
      render3D();
    }}
    return;
  }}
  if (!focusMatches.length) {{
    if (options.render !== false) {{
      render3D();
    }}
    return;
  }}
  const xs = focusMatches.flatMap((row) => [Number(row.p0[0]), Number(row.p1[0])]);
  const ys = focusMatches.flatMap((row) => [Number(row.p0[1]), Number(row.p1[1])]);
  const zs = focusMatches.flatMap((row) => [Number(row.p0[2]), Number(row.p1[2])]);
  const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
  const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
  const cz = (Math.min(...zs) + Math.max(...zs)) / 2;
  const extent = REVIEW_3D.extent || {{}};
  const globalCenterX = (Number(extent.min_x || 0) + Number(extent.max_x || 0)) / 2;
  const globalCenterY = (Number(extent.min_y || 0) + Number(extent.max_y || 0)) / 2;
  const globalCenterZ = (Number(extent.min_z || 0) + Number(extent.max_z || 0)) / 2;
  const span = Math.max(
    Math.max(...xs) - Math.min(...xs),
    Math.max(...ys) - Math.min(...ys),
    (Math.max(...zs) - Math.min(...zs)) * 4,
    1
  );
  viewerState.scale = clamp((Math.min(viewportWidth(), viewportHeight()) * 0.34) / span, 1.6, 22);
  const target = projectPoint([cx, cy, cz]);
  const worldProjection = projectPoint([globalCenterX, globalCenterY, globalCenterZ]);
  if (!projectedPointIsFinite(target) || !projectedPointIsFinite(worldProjection)) {{
    resetViewportToExtent();
    if (options.render !== false) {{
      render3D();
    }}
    return;
  }}
  viewerState.panX += worldProjection.x - target.x;
  viewerState.panY += worldProjection.y - target.y;
  if (options.render !== false) {{
    render3D();
  }}
}}
function announceSelection(message) {{
  if (selectionLiveRegion) {{
    selectionLiveRegion.textContent = String(message || 'No member selected');
  }}
}}
function setSelectionOverlayEmpty(empty) {{
  if (selectionOverlay.container) {{
    selectionOverlay.container.classList.toggle('is-empty', Boolean(empty));
  }}
  if (clearSelectionButton) {{
    clearSelectionButton.disabled = Boolean(empty);
  }}
  if (shareSelectionButton) {{
    shareSelectionButton.disabled = Boolean(empty);
  }}
}}
function updateStorySelectionOverlay(storyBand) {{
  const label = String(storyBand || '').trim();
  if (!label || !selectionOverlay.member || !selectionOverlay.section || !selectionOverlay.thickness || !selectionOverlay.rebar) {{
    return;
  }}
  const counts = storyBandSelectionCounts(label);
  setSelectionOverlayEmpty(false);
  selectionOverlay.member.className = 'selection-overlay-line';
  selectionOverlay.member.textContent = `Story ${{label}} selected`;
  selectionOverlay.section.textContent = `Story band focus: ${{label}}`;
  selectionOverlay.thickness.textContent = `Renderable story segments: ${{counts.renderable}} of ${{counts.total}} total`;
  selectionOverlay.rebar.textContent = `Excluded from rendering: ${{counts.invalidExcluded}} invalid rows`;
  updateStoryEvidenceCard(label);
  announceSelection(`Story ${{label}} selected, ${{counts.focusable}} renderable segments out of ${{counts.total}} total; ${{counts.invalidExcluded}} invalid rows excluded`);
}}
function workspaceSelectionState() {{
  const memberId = String(viewerState.selectedMemberId || '').trim();
  const storyBand = String(viewerState.activeStoryBand || '').trim();
  const gridBubbleId = String(viewerState.selectedGridBubbleId || '').trim();
  if (memberId) {{
    const meta = buildMemberMeta(memberId);
    const story = storyBand || String(meta.story || '').trim();
    return {{
      kind: 'member',
      id: memberId,
      story,
      label: meta.memberId || memberId,
      provenance: 'member-table',
      hasSelection: true,
      contractVersion: WORKSPACE_SELECTION_CONTRACT_VERSION,
    }};
  }}
  if (storyBand) {{
    return {{
      kind: 'story',
      id: storyBand,
      story: storyBand,
      label: `Story ${{storyBand}}`,
      provenance: 'story-band',
      hasSelection: true,
      contractVersion: WORKSPACE_SELECTION_CONTRACT_VERSION,
    }};
  }}
  if (gridBubbleId) {{
    const bubble = viewerState.gridBubbles.find((item) => String(item.id || '') === gridBubbleId) || null;
    return {{
      kind: 'grid',
      id: gridBubbleId,
      story: '',
      label: bubble ? String(bubble.label || bubble.id || gridBubbleId) : gridBubbleId,
      provenance: 'grid-bubble',
      hasSelection: true,
      contractVersion: WORKSPACE_SELECTION_CONTRACT_VERSION,
    }};
  }}
  return {{
    kind: 'clear',
    id: '',
    story: '',
    label: '',
    provenance: 'empty',
    hasSelection: false,
    contractVersion: WORKSPACE_SELECTION_CONTRACT_VERSION,
  }};
}}
function deleteWorkspaceSelectionParams(params) {{
  LEGACY_WORKSPACE_SELECTION_PARAMS.forEach((key) => params.delete(key));
  CANONICAL_WORKSPACE_SELECTION_PARAMS.forEach((key) => params.delete(key));
  return params;
}}
function hasCanonicalWorkspaceSelectionParams(params) {{
  return CANONICAL_WORKSPACE_SELECTION_PARAMS.some((key) => params.has(key));
}}
function hasLegacyWorkspaceSelectionParams(params) {{
  return LEGACY_WORKSPACE_SELECTION_PARAMS.some((key) => params.has(key));
}}
function writeWorkspaceSelectionParams(params, state) {{
  deleteWorkspaceSelectionParams(params);
  state = state || workspaceSelectionState();
  if (!state || !state.hasSelection) return params;
  const canonicalKinds = new Set(['member', 'story', 'grid']);
  if (!canonicalKinds.has(state.kind) || !state.id) return params;
  params.set('selection_kind', state.kind);
  params.set('selection_id', state.id);
  params.set('selection_contract_version', WORKSPACE_SELECTION_CONTRACT_VERSION);
  if (state.label) {{
    params.set('selection_label', state.label);
  }}
  if (state.provenance) {{
    params.set('selection_provenance', state.provenance);
  }}
  if (state.story) {{
    params.set('selection_story', state.story);
  }}
  return params;
}}
function cleanupWorkspaceSelectionHashParams(url) {{
  const hashText = String(url.hash || '').replace(/^#/, '');
  if (!hashText || !hashText.includes('=')) return;
  const hashParams = new URLSearchParams(hashText);
  if (!hasLegacyWorkspaceSelectionParams(hashParams) && !hasCanonicalWorkspaceSelectionParams(hashParams)) return;
  writeWorkspaceSelectionParams(hashParams, {{
    kind: 'clear',
    id: '',
    story: '',
    label: '',
    provenance: 'hash-cleanup',
    hasSelection: false,
    contractVersion: WORKSPACE_SELECTION_CONTRACT_VERSION,
  }});
  const nextHash = hashParams.toString();
  url.hash = nextHash ? `#${{nextHash}}` : '';
}}
function syncWorkspaceUrlState(options = {{}}) {{
  if (!window.history || !window.location) return;
  const url = new URL(window.location.href);
  const params = url.searchParams;
  writeWorkspaceSelectionParams(params, workspaceSelectionState());
  cleanupWorkspaceSelectionHashParams(url);
  const nextUrl = `${{url.pathname}}${{url.search}}${{url.hash}}`;
  if (nextUrl === `${{window.location.pathname}}${{window.location.search}}${{window.location.hash}}`) return;
  window.history.replaceState(null, '', nextUrl);
}}
function buildWorkspaceDeepLink() {{
  if (!window.location) return '';
  const state = workspaceSelectionState();
  if (!state.hasSelection) return '';
  const url = new URL(window.location.href);
  const params = url.searchParams;
  writeWorkspaceSelectionParams(params, state);
  cleanupWorkspaceSelectionHashParams(url);
  return url.href;
}}
function copyTextWithFallback(text) {{
  if (navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {{
    return navigator.clipboard.writeText(text).catch(() => copyTextWithFallbackViaTextarea(text));
  }}
  return copyTextWithFallbackViaTextarea(text);
}}
function copyTextWithFallbackViaTextarea(text) {{
  return new Promise((resolve, reject) => {{
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {{
      const copied = document.execCommand('copy');
      document.body.removeChild(textarea);
      copied ? resolve() : reject(new Error('fallback copy failed'));
    }} catch (error) {{
      document.body.removeChild(textarea);
      reject(error);
    }}
  }});
}}
async function copyWorkspaceDeepLink() {{
  const deepLink = buildWorkspaceDeepLink();
  if (!deepLink) {{
    announceSelection('No selected member, story, or grid to copy');
    return;
  }}
  try {{
    await copyTextWithFallback(deepLink);
    announceSelection('Selection deep link copied');
  }} catch (error) {{
    announceSelection('Could not copy selection deep link. Select and copy the browser URL manually.');
  }}
}}
function applyWorkspaceGridSelection(bubble, options = {{}}) {{
  const nextBubble = bubble && viewerState.selectedGridBubbleId !== bubble.id ? bubble : null;
  viewerState.selectedMemberId = '';
  viewerState.selectedGridBubbleId = nextBubble ? String(nextBubble.id || '') : '';
  memberRows.forEach((row) => {{
    row.classList.toggle('is-selected-row', false);
    row.setAttribute('aria-selected', 'false');
  }});
  setActiveStoryBand('', {{ render: false, syncUrl: false }});
  updateInspector('');
  updateSelectionOverlay('');
  updateGridBubbleInspector(nextBubble);
  if (options.syncDiff !== false) {{
    syncWorkspaceDiffFocus(workspaceSelectionState(), options);
  }}
  if (options.syncUrl !== false) {{
    syncWorkspaceUrlState({{ replace: true }});
  }}
  if (options.render !== false) {{
    render3D();
  }}
}}
function applyWorkspaceClearSelection(options = {{}}) {{
  viewerState.selectedMemberId = '';
  viewerState.selectedGridBubbleId = '';
  memberRows.forEach((row) => {{
    row.classList.toggle('is-selected-row', false);
    row.setAttribute('aria-selected', 'false');
  }});
  updateInspector('');
  updateGridBubbleInspector(null);
  updateSelectionOverlay('');
  setActiveStoryBand('', {{ render: false, syncUrl: false }});
  if (options.syncDiff !== false) {{
    syncWorkspaceDiffFocus(workspaceSelectionState(), options);
  }}
  if (options.syncUrl !== false) {{
    syncWorkspaceUrlState({{ replace: true }});
  }}
  if (options.render !== false) {{
    render3D();
  }}
}}
function commitWorkspaceSelection(selection = {{}}, options = {{}}) {{
  const kind = String(selection.kind || 'clear').trim().toLowerCase();
  const id = String(selection.id || '').trim();
  if (kind === 'member') {{
    return applyWorkspaceMemberSelection(id, options);
  }}
  if (kind === 'grid') {{
    const bubble = selection.bubble || viewerState.gridBubbles.find((item) => String(item.id || '') === id) || null;
    return applyWorkspaceGridSelection(bubble, options);
  }}
  if (kind === 'story') {{
    return applyWorkspaceStorySelection(id, options);
  }}
  return applyWorkspaceClearSelection(options);
}}
function clearWorkspaceSelection(options = {{}}) {{
  return commitWorkspaceSelection({{ kind: 'clear', source: options.source || 'clear' }}, options);
}}
function workspaceRestoreParams() {{
  const searchParams = new URLSearchParams(window.location.search || '');
  const hashText = String(window.location.hash || '').replace(/^#/, '');
  const hashParams = new URLSearchParams(hashText.includes('=') ? hashText : '');
  const hasCanonical = hasCanonicalWorkspaceSelectionParams(searchParams) || hasCanonicalWorkspaceSelectionParams(hashParams);
  return {{
    hasCanonical,
    selectionKind: searchParams.get('selection_kind') || hashParams.get('selection_kind') || '',
    selectionId: searchParams.get('selection_id') || hashParams.get('selection_id') || '',
    selectionLabel: searchParams.get('selection_label') || hashParams.get('selection_label') || '',
    selectionProvenance: searchParams.get('selection_provenance') || hashParams.get('selection_provenance') || '',
    selectionStory: searchParams.get('selection_story') || hashParams.get('selection_story') || '',
    selectionContractVersion: searchParams.get('selection_contract_version') || hashParams.get('selection_contract_version') || '',
    member: searchParams.get('member') || hashParams.get('member') || '',
    story: searchParams.get('story') || hashParams.get('story') || '',
    grid: searchParams.get('grid') || hashParams.get('grid') || '',
  }};
}}
function restoreWorkspaceSelectionFromUrl() {{
  const params = workspaceRestoreParams();
  const canonicalKind = String(params.selectionKind || '').trim().toLowerCase();
  const canonicalId = String(params.selectionId || '').trim();
  if (canonicalKind === 'clear') {{
    commitWorkspaceSelection({{ kind: 'clear', source: 'url-restore' }}, {{ centerFit: false, syncUrl: true }});
    return true;
  }}
  if (canonicalKind && canonicalId) {{
    if (canonicalKind === 'member' && memberRows.some((row) => row.dataset.memberId === canonicalId)) {{
      commitWorkspaceSelection({{ kind: 'member', id: canonicalId, source: 'url-restore' }}, {{ centerFit: true, syncUrl: true }});
      return true;
    }}
    if (canonicalKind === 'story') {{
      commitWorkspaceSelection({{ kind: 'story', id: canonicalId, source: 'url-restore' }}, {{ centerFit: true, syncUrl: true }});
      return true;
    }}
    if (canonicalKind === 'grid') {{
      if (!viewerState.gridBubbles.length) {{
        render3DNow();
      }}
      const canonicalBubble = viewerState.gridBubbles.find((item) => String(item.id || '') === canonicalId) || null;
      if (canonicalBubble) {{
        commitWorkspaceSelection({{ kind: 'grid', id: canonicalId, source: 'url-restore' }}, {{ centerFit: false, syncUrl: true }});
        return true;
      }}
    }}
    return false;
  }}
  if (params.hasCanonical) {{
    commitWorkspaceSelection({{ kind: 'clear', source: 'url-restore-invalid-canonical' }}, {{ centerFit: false, syncUrl: true }});
    return true;
  }}
  const memberId = String(params.member || '').trim();
  const storyBand = String(params.story || '').trim();
  const gridBubbleId = String(params.grid || '').trim();
  // Restore priority: member > story > grid.
  if (memberId && memberRows.some((row) => row.dataset.memberId === memberId)) {{
    commitWorkspaceSelection({{ kind: 'member', id: memberId, source: 'url-restore' }}, {{ centerFit: true, syncUrl: true }});
    return true;
  }}
  if (storyBand) {{
    commitWorkspaceSelection({{ kind: 'story', id: storyBand, source: 'url-restore' }}, {{ centerFit: true, syncUrl: true }});
    return true;
  }}
  if (gridBubbleId) {{
    if (!viewerState.gridBubbles.length) {{
      render3DNow();
    }}
    const bubble = viewerState.gridBubbles.find((item) => String(item.id || '') === gridBubbleId) || null;
    if (bubble) {{
      commitWorkspaceSelection({{ kind: 'grid', id: gridBubbleId, source: 'url-restore' }}, {{ centerFit: false, syncUrl: true }});
      return true;
    }}
  }}
  return false;
}}
function selectMember(memberId, options = {{}}) {{
  return commitWorkspaceSelection({{ kind: 'member', id: memberId, source: options.source || 'member' }}, options);
}}
function applyWorkspaceMemberSelection(memberId, options = {{}}) {{
  viewerState.selectedMemberId = String(memberId || '').trim();
  viewerState.selectedGridBubbleId = '';
  memberRows.forEach((row) => {{
    const selected = row.dataset.memberId === viewerState.selectedMemberId;
    row.classList.toggle('is-selected-row', selected);
    row.setAttribute('aria-selected', String(selected));
  }});
  updateInspector(viewerState.selectedMemberId);
  updateSelectionOverlay(viewerState.selectedMemberId);
  if (viewerState.selectedMemberId) {{
    setActiveStoryBand(buildMemberMeta(viewerState.selectedMemberId).story, {{ render: false, syncUrl: false }});
  }} else {{
    setActiveStoryBand('', {{ render: false, syncUrl: false }});
  }}
  if (options.centerFit !== false && viewerState.selectedMemberId) {{
    focusMember(viewerState.selectedMemberId);
  }}
  if (!viewerState.selectedMemberId) {{
    updateGridBubbleInspector(null);
  }}
  syncWorkspaceDiffFocus(workspaceSelectionState(), options);
  if (options.syncUrl !== false) {{
    syncWorkspaceUrlState({{ replace: true }});
  }}
  if (options.render !== false) {{
    render3D();
  }}
}}
function coarsePointerHitRadius(pointerType = '') {{
  return String(pointerType || '') === 'touch' || window.matchMedia?.('(pointer: coarse)')?.matches ? 18 : 9;
}}
function nearestProjectedEntry(offsetX, offsetY, pointerType = '') {{
  const maxDistance = coarsePointerHitRadius(pointerType);
  let best = null;
  viewerState.projectedSegments.forEach((entry) => {{
    const distance = lineDistance(offsetX, offsetY, entry.p0.x, entry.p0.y, entry.p1.x, entry.p1.y);
    if (distance > maxDistance) return;
    if (!best || distance < best.distance) best = {{ entry, distance }};
  }});
  return best ? best.entry : null;
}}
function nearestGridBubble(offsetX, offsetY, pointerType = '') {{
  if (!viewerState.gridBubbles.length) return null;
  const maxDistance = coarsePointerHitRadius(pointerType) + 7;
  let best = null;
  viewerState.gridBubbles.forEach((bubble) => {{
    const distance = Math.hypot(offsetX - bubble.x, offsetY - bubble.y);
    if (distance > maxDistance) return;
    if (!best || distance < best.distance) best = {{ bubble, distance }};
  }});
  return best ? best.bubble : null;
}}
function handleCanvasKeyboard(event) {{
  if (!canvas) return;
  const key = String(event.key || '');
  const lowerKey = key.toLowerCase();
  if (event.key === 'Escape') {{
    event.preventDefault();
    clearWorkspaceSelection();
    return;
  }}
  if (event.key === '+' || event.key === '=') {{
    event.preventDefault();
    zoomAtCanvasPoint(viewportWidth() / 2, viewportHeight() / 2, 1.16);
    render3D();
    return;
  }}
  if (event.key === '-' || event.key === '_') {{
    event.preventDefault();
    zoomAtCanvasPoint(viewportWidth() / 2, viewportHeight() / 2, 1 / 1.16);
    render3D();
    return;
  }}
  if (event.key === '0' || event.key.toLowerCase() === 'f') {{
    event.preventDefault();
    resetCamera(viewerState.viewPreset || 'iso');
    return;
  }}
  const directionByKey = {{
    arrowleft: [-1, 0],
    a: [-1, 0],
    arrowright: [1, 0],
    d: [1, 0],
    arrowup: [0, -1],
    w: [0, -1],
    arrowdown: [0, 1],
    s: [0, 1],
  }};
  const direction = directionByKey[lowerKey];
  if (!direction) return;
  event.preventDefault();
  const keyboardPanStep = event.shiftKey ? 32 : 0;
  const keyboardOrbitStep = event.shiftKey ? 0 : 0.08;
  if (keyboardPanStep) {{
    viewerState.panX += direction[0] * keyboardPanStep;
    viewerState.panY += direction[1] * keyboardPanStep;
  }} else {{
    viewerState.yaw = normalizeCameraAngle(viewerState.yaw + direction[0] * keyboardOrbitStep);
    viewerState.pitch = clamp(viewerState.pitch + direction[1] * keyboardOrbitStep, -1.25, 1.25);
  }}
  render3D();
}}
if (canvas && canvasWrap) {{
  canvas.addEventListener('keydown', handleCanvasKeyboard);
  canvas.addEventListener('wheel', (event) => {{
    event.preventDefault();
    const delta = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    const rect = canvas.getBoundingClientRect();
    zoomAtCanvasPoint(event.clientX - rect.left, event.clientY - rect.top, delta);
    render3D();
  }}, {{ passive: false }});
  canvas.addEventListener('pointerdown', (event) => {{
    event.preventDefault();
    if (event.pointerType === 'touch') {{
      const rect = canvas.getBoundingClientRect();
      viewerState.touchPoints.set(event.pointerId, {{
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      }});
      if (viewerState.touchPoints.size >= 2) {{
        viewerState.dragging = false;
        viewerState.pointerId = null;
        viewerState.panMode = true;
        viewerState.lastTapEligible = false;
        viewerState.pinchStartDistance = 0;
        updatePinchGesture();
        hideTooltip();
        canvasWrap.classList.add('is-dragging');
        canvas.setPointerCapture(event.pointerId);
        return;
      }}
    }}
    viewerState.dragging = true;
    viewerState.panMode = event.shiftKey || event.pointerType === 'touch';
    viewerState.pointerId = event.pointerId;
    viewerState.startX = event.clientX;
    viewerState.startY = event.clientY;
    viewerState.pointerDownX = event.clientX;
    viewerState.pointerDownY = event.clientY;
    viewerState.dragDistance = 0;
    viewerState.lastTapEligible = true;
    viewerState.hoveredGridBubbleId = '';
    viewerState.hoveredSegmentKey = '';
    viewerState.hoveredCompareMemberId = '';
    hideTooltip();
    canvasWrap.classList.add('is-dragging');
    canvas.setPointerCapture(event.pointerId);
  }});
  canvas.addEventListener('pointermove', (event) => {{
    if (event.pointerType === 'touch' && viewerState.touchPoints.has(event.pointerId)) {{
      const rect = canvas.getBoundingClientRect();
      viewerState.touchPoints.set(event.pointerId, {{
        x: event.clientX - rect.left,
        y: event.clientY - rect.top,
      }});
      if (viewerState.touchPoints.size >= 2) {{
        updatePinchGesture();
        hideTooltip();
        render3D();
        return;
      }}
    }}
    if (viewerState.dragging && viewerState.pointerId === event.pointerId) {{
      const dx = event.clientX - viewerState.startX;
      const dy = event.clientY - viewerState.startY;
      viewerState.dragDistance = Math.max(
        viewerState.dragDistance,
        Math.hypot(event.clientX - viewerState.pointerDownX, event.clientY - viewerState.pointerDownY)
      );
      if (viewerState.dragDistance > 6) viewerState.lastTapEligible = false;
      viewerState.startX = event.clientX;
      viewerState.startY = event.clientY;
      if (viewerState.panMode) {{
        viewerState.panX += dx;
        viewerState.panY += dy;
      }} else {{
        viewerState.yaw += dx * 0.008;
        viewerState.pitch = clamp(viewerState.pitch + dy * 0.008, -1.25, 1.25);
      }}
      hideTooltip();
      render3D();
      return;
    }}
    const rect = canvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const hoveredBubble = nearestGridBubble(localX, localY, event.pointerType);
    const entry = nearestProjectedEntry(localX, localY, event.pointerType);
    const nextBubbleId = hoveredBubble ? hoveredBubble.id : '';
    const nextKey = hoveredBubble ? '' : entry ? segmentKey(entry.segment) : '';
    let changed = false;
    if (nextBubbleId !== viewerState.hoveredGridBubbleId) {{
      viewerState.hoveredGridBubbleId = nextBubbleId;
      changed = true;
    }}
    if (nextKey !== viewerState.hoveredSegmentKey) {{
      viewerState.hoveredSegmentKey = nextKey;
      changed = true;
    }}
    if (changed) {{
      render3D();
    }}
    if (hoveredBubble) {{
      showGridBubbleTooltip(hoveredBubble, localX, localY);
    }} else if (entry) {{
      showTooltip(entry, localX, localY);
    }} else {{
      hideTooltip();
    }}
  }});
  const stopDrag = (event) => {{
    if (event.pointerType === 'touch') {{
      viewerState.touchPoints.delete(event.pointerId);
      if (viewerState.touchPoints.size < 2) {{
        viewerState.pinchStartDistance = 0;
        viewerState.pinchStartCentroid = null;
      }}
    }}
    if (viewerState.pointerId !== event.pointerId) return;
    viewerState.dragging = false;
    viewerState.pointerId = null;
    canvasWrap.classList.remove('is-dragging');
  }};
  canvas.addEventListener('pointerup', stopDrag);
  canvas.addEventListener('pointercancel', stopDrag);
  canvas.addEventListener('pointerleave', () => {{
    viewerState.hoveredGridBubbleId = '';
    viewerState.hoveredSegmentKey = '';
    viewerState.hoveredCompareMemberId = '';
    hideTooltip();
    render3D();
  }});
  canvas.addEventListener('click', (event) => {{
    if (!viewerState.lastTapEligible) return;
    const rect = canvas.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;
    const bubble = nearestGridBubble(localX, localY, event.pointerType);
    const entry = nearestProjectedEntry(localX, localY, event.pointerType);
    if (bubble) {{
      commitWorkspaceSelection({{ kind: 'grid', id: bubble.id, source: 'canvas', bubble }}, {{ centerFit: false }});
      return;
    }}
    if (entry?.segment?.member_id) {{
      commitWorkspaceSelection({{ kind: 'member', id: entry.segment.member_id, source: 'canvas' }}, {{ centerFit: false }});
    }} else {{
      commitWorkspaceSelection({{ kind: 'clear', source: 'canvas-empty' }}, {{ centerFit: false }});
    }}
  }});
}}
toggleInputs.forEach((input) => {{
  if (input.type === 'checkbox') {{
    input.addEventListener('change', () => render3D());
    return;
  }}
  input.addEventListener('click', () => {{
    const next = input.getAttribute('aria-pressed') !== 'true';
    input.setAttribute('aria-pressed', String(next));
    input.classList.toggle('is-on', next);
    render3D();
  }});
}});
overlayModeButtons.forEach((button) => {{
  button.addEventListener('click', () => setOverlayMode(button.dataset.overlayMode || 'member_type'));
}});
cameraButtons.forEach((button) => {{
  button.addEventListener('click', () => resetCamera(button.dataset.cameraPreset || 'iso'));
}});
viewportControlButtons.forEach((button) => {{
  button.addEventListener('click', (event) => {{
    event.preventDefault();
    hideTooltip();
    applyViewportControl(button.dataset.viewportControl || '');
  }});
}});
const cameraResetButton = document.querySelector('[data-camera-reset]');
if (cameraResetButton) {{
  cameraResetButton.addEventListener('click', () => resetCamera(viewerState.viewPreset || 'iso'));
}}
const mgtTabButtons = [...document.querySelectorAll('[data-mgt-tab]')];
const mgtTabPanels = [...document.querySelectorAll('[data-mgt-tab-panel]')];
const rawDiffSearchInput = document.getElementById('mgt-raw-diff-search');
const rawDiffLineNodes = [...document.querySelectorAll('[data-raw-diff-line]')];
const rawDiffNodeByIndex = new Map(rawDiffLineNodes.map((node) => [String(node.dataset.diffIndex || ''), node]));
const compareRowNodeByIndex = new Map(compareRowNodes.map((node) => [String(node.dataset.diffIndex || ''), node]));
const comparePageRowNodeByIndex = new Map(comparePageRowNodes.map((node) => [String(node.dataset.diffIndex || ''), node]));
const rawDiffCount = document.getElementById('mgt-raw-diff-count');
function extractSearchTokens(value = '') {{
  return Array.from(new Set((String(value || '').toLowerCase().match(/[a-z0-9]+/g) || []).filter((token) => token.length > 2 || /^[0-9]+$/.test(token))));
}}
function memberIdsForDiffNode(node) {{
  return [
    String(node?.dataset?.memberId || ''),
    ...parseDataList(node?.dataset?.candidateMemberIds || node?.dataset?.memberIds || ''),
    ...parseDataList(node?.dataset?.geometryBridgeMemberIds || ''),
  ]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
}}
function diffRowIndexesForMember(memberId) {{
  const exact = String(memberId || '').trim();
  if (!exact) return [];
  const direct = mgtDiffRowIndexMap[exact] || mgtDiffRowIndexMap[exact.toLowerCase()] || [];
  if (!Array.isArray(direct)) return [];
  return direct
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value >= 0);
}}
function diffRowsForIndexes(nodeMap, indexes) {{
  return indexes
    .map((index) => nodeMap.get(String(index)))
    .filter(Boolean);
}}
function activateMgtTab(tabName) {{
  const nextTab = String(tabName || 'summary');
  mgtTabButtons.forEach((button) => {{
    const active = String(button.dataset.mgtTab || 'summary') === nextTab;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
  }});
  mgtTabPanels.forEach((panel) => {{
    const active = String(panel.dataset.mgtTabPanel || 'summary') === nextTab;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  }});
}}
function activateComparePage(pageIndex = '0') {{
  const pageCount = comparePagePanels.length || comparePageTabButtons.length || 1;
  const nextPage = String(clamp(Number(pageIndex) || 0, 0, Math.max(pageCount - 1, 0)));
  comparePageTabButtons.forEach((button) => {{
    const active = String(button.dataset.comparePageTab || '0') === nextPage;
    button.classList.toggle('is-active', active);
    button.setAttribute('aria-selected', String(active));
  }});
  comparePagePanels.forEach((panel) => {{
    const active = String(panel.dataset.comparePagePanel || '0') === nextPage;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  }});
  updateComparePagerNav();
}}
function currentComparePageIndex() {{
  const activeButton = comparePageTabButtons.find((button) => button.classList.contains('is-active'));
  return Number(activeButton?.dataset?.comparePageTab || 0) || 0;
}}
function stepComparePage(action = '') {{
  const pageCount = comparePagePanels.length || comparePageTabButtons.length || 1;
  const current = currentComparePageIndex();
  if (action === 'first') {{
    activateComparePage('0');
    return;
  }}
  if (action === 'prev') {{
    activateComparePage(String(Math.max(0, current - 1)));
    return;
  }}
  if (action === 'next') {{
    activateComparePage(String(Math.min(pageCount - 1, current + 1)));
    return;
  }}
  if (action === 'last') {{
    activateComparePage(String(Math.max(pageCount - 1, 0)));
  }}
}}
function updateComparePagerNav() {{
  const pageCount = comparePagePanels.length || comparePageTabButtons.length || 1;
  const current = currentComparePageIndex();
  comparePageNavButtons.forEach((button) => {{
    const action = String(button.dataset.comparePageNav || '');
    const disabled = (action === 'first' || action === 'prev')
      ? current <= 0
      : current >= pageCount - 1;
    button.disabled = disabled;
  }});
}}
function setHoveredCompareMember(memberId = '') {{
  const next = String(memberId || '').trim();
  if (viewerState.hoveredCompareMemberId === next) return;
  viewerState.hoveredCompareMemberId = next;
  render3D();
}}
function updateRawDiffFilter(query = '', options = {{}}) {{
  const normalized = String(query || '').trim().toLowerCase();
  const tokens = extractSearchTokens(normalized);
  const matchMode = String(options.matchMode || 'all');
  let visibleCount = 0;
  let bestNode = null;
  let bestScore = -1;
  rawDiffLineNodes.forEach((node) => {{
    const haystack = diffNodeSearchText(node);
    const visible = !tokens.length || (matchMode === 'any'
      ? tokens.some((token) => haystack.includes(token))
      : tokens.every((token) => haystack.includes(token)));
    const row = node.closest('.mgt-raw-diff-line');
    if (row) {{
      row.hidden = !visible;
      row.classList.toggle('is-match', visible && tokens.length > 0);
      row.classList.toggle('is-dim', tokens.length > 0 && !visible);
      row.classList.remove('is-focused');
    }}
    if (visible) {{
      visibleCount += 1;
      const score = tokens.reduce((count, token) => count + (haystack.includes(token) ? 1 : 0), 0);
      if (score > bestScore) {{
        bestScore = score;
        bestNode = node;
      }}
    }}
  }});
  compareRowNodes.forEach((node) => {{
    const haystack = diffNodeSearchText(node);
    const visible = !tokens.length || (matchMode === 'any'
      ? tokens.some((token) => haystack.includes(token))
      : tokens.every((token) => haystack.includes(token)));
    const row = node.closest('.mgt-compare-row');
    if (row) {{
      row.hidden = !visible;
      row.classList.toggle('is-match', visible && tokens.length > 0);
      row.classList.toggle('is-dim', tokens.length > 0 && !visible);
      row.classList.remove('is-focused');
    }}
    if (visible) {{
      const score = tokens.reduce((count, token) => count + (haystack.includes(token) ? 1 : 0), 0);
      if (score > bestScore) {{
        bestScore = score;
        bestNode = node;
      }}
    }}
  }});
  comparePageRowNodes.forEach((node) => {{
    const haystack = diffNodeSearchText(node);
    const visible = !tokens.length || (matchMode === 'any'
      ? tokens.some((token) => haystack.includes(token))
      : tokens.every((token) => haystack.includes(token)));
    node.hidden = !visible;
    node.classList.toggle('is-match', visible && tokens.length > 0);
    node.classList.toggle('is-dim', tokens.length > 0 && !visible);
    node.classList.remove('is-focused');
  }});
  if (rawDiffCount) {{
    rawDiffCount.textContent = 'visible ' + String(visibleCount) + ' / ' + String(rawDiffLineNodes.length);
  }}
  return bestNode;
}}
function focusRelatedRawDiffRows(reference = '', fallbackReference = '') {{
  const memberId = String(reference || '').trim();
  const query = [memberId, String(fallbackReference || '').trim()].filter(Boolean).join(' ');
  compareRowNodes.forEach((row) => {{
    row.classList.remove('is-focused', 'is-match', 'is-dim');
  }});
  comparePageRowNodes.forEach((row) => {{
    row.classList.remove('is-focused', 'is-match', 'is-dim');
  }});
  if (!query) return null;
  const exactIndexes = diffRowIndexesForMember(memberId);
  const exactRawNodes = exactIndexes.length ? diffRowsForIndexes(rawDiffNodeByIndex, exactIndexes) : [];
  const exactCompareRows = exactIndexes.length ? diffRowsForIndexes(compareRowNodeByIndex, exactIndexes) : [];
  const exactComparePageRows = exactIndexes.length ? diffRowsForIndexes(comparePageRowNodeByIndex, exactIndexes) : [];
  const fallbackExactRawNodes = !exactRawNodes.length && memberId
    ? rawDiffLineNodes.filter((node) => memberIdsForDiffNode(node).includes(memberId))
    : [];
  const fallbackExactCompareRows = !exactCompareRows.length && memberId
    ? compareRowNodes.filter((row) => memberIdsForDiffNode(row).includes(memberId))
    : [];
  const fallbackExactComparePageRows = !exactComparePageRows.length && memberId
    ? comparePageRowNodes.filter((row) => memberIdsForDiffNode(row).includes(memberId))
    : [];
  const resolvedExactRawNodes = exactRawNodes.length ? exactRawNodes : fallbackExactRawNodes;
  const resolvedExactCompareRows = exactCompareRows.length ? exactCompareRows : fallbackExactCompareRows;
  const resolvedExactComparePageRows = exactComparePageRows.length ? exactComparePageRows : fallbackExactComparePageRows;
  if (resolvedExactCompareRows.length) {{
    compareRowNodes.forEach((row) => {{
      const exact = resolvedExactCompareRows.includes(row);
      row.classList.toggle('is-match', exact);
      row.classList.toggle('is-dim', !exact);
    }});
    resolvedExactCompareRows[0].classList.add('is-focused');
  }}
  if (resolvedExactComparePageRows.length) {{
    comparePageRowNodes.forEach((row) => {{
      const exact = resolvedExactComparePageRows.includes(row);
      row.classList.toggle('is-match', exact);
      row.classList.toggle('is-dim', !exact);
    }});
    resolvedExactComparePageRows[0].classList.add('is-focused');
  }}
  if (resolvedExactRawNodes.length && rawDiffSearchInput) {{
    rawDiffSearchInput.value = memberId;
  }} else if (rawDiffSearchInput) {{
    rawDiffSearchInput.value = query;
  }}
  const bestNode = resolvedExactRawNodes[0] || updateRawDiffFilter(resolvedExactRawNodes.length ? memberId : query, {{ matchMode: resolvedExactRawNodes.length ? 'any' : 'any' }});
  const targetNode = bestNode || rawDiffLineNodes.find((node) => diffNodeSearchText(node).includes(query.toLowerCase()));
  const targetRow = targetNode ? targetNode.closest('.mgt-raw-diff-line') : null;
  const compareTarget = resolvedExactCompareRows[0] || compareRowNodes.find((row) => diffNodeSearchText(row).includes(query.toLowerCase())) || null;
  const comparePageTarget = resolvedExactComparePageRows[0] || comparePageRowNodes.find((row) => diffNodeSearchText(row).includes(query.toLowerCase())) || null;
  if (resolvedExactCompareRows.length) {{
    activateMgtTab('compare');
    activateComparePage(comparePageTarget?.dataset?.comparePage || compareTarget?.dataset?.comparePage || '0');
    comparePageTarget?.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'smooth' }});
    compareTarget?.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'smooth' }});
  }} else if (targetRow) {{
    activateMgtTab('raw');
  }}
  if (targetRow) {{
    targetRow.classList.add('is-focused');
    targetRow.scrollIntoView({{ block: 'center', inline: 'nearest', behavior: 'smooth' }});
  }}
  return compareTarget || targetRow;
}}
function clearRelatedRawDiffRows(reason = 'member-level diff not selected') {{
  rawDiffLineNodes.forEach((node) => {{
    const row = node.closest('.mgt-raw-diff-line');
    if (row) {{
      row.hidden = false;
      row.classList.remove('is-focused', 'is-match', 'is-dim');
    }}
  }});
  compareRowNodes.forEach((row) => {{
    row.hidden = false;
    row.classList.remove('is-focused', 'is-match', 'is-dim');
  }});
  comparePageRowNodes.forEach((row) => {{
    row.hidden = false;
    row.classList.remove('is-focused', 'is-match', 'is-dim');
  }});
  if (rawDiffSearchInput) {{
    rawDiffSearchInput.value = '';
    rawDiffSearchInput.dataset.diffFocusState = String(reason || 'member-level diff not selected');
  }}
  if (rawDiffCount) {{
    rawDiffCount.textContent = 'visible ' + String(rawDiffLineNodes.length) + ' / ' + String(rawDiffLineNodes.length);
  }}
  return null;
}}
function syncWorkspaceDiffFocus(state = workspaceSelectionState(), options = {{}}) {{
  if (options.syncDiff === false) return null;
  if (state && state.kind === 'member' && state.id) {{
    const selectedRow = memberRows.find((row) => row.dataset.memberId === state.id);
    const meta = buildMemberMeta(state.id);
    const fallbackReference = selectedRow
      ? String(selectedRow.dataset.search || '')
      : [meta.memberId, meta.sectionBefore, meta.sectionAfter, meta.story, meta.zone].join(' ');
    return focusRelatedRawDiffRows(state.id, fallbackReference);
  }}
  return clearRelatedRawDiffRows('member-level diff not selected');
}}
mgtTabButtons.forEach((button) => {{
  button.addEventListener('click', () => activateMgtTab(button.dataset.mgtTab || 'summary'));
}});
activateMgtTab('summary');
activateComparePage('0');
updateComparePagerNav();
const searchInput = document.getElementById('member-search');
memberRows.forEach((row) => {{
  row.dataset.memberId = String(row.dataset.memberId || (row.children[0] ? String(row.children[0].textContent || '').trim() : '')).trim();
  row.addEventListener('click', (event) => {{
    if (event.target instanceof Element && event.target.closest('a')) return;
    selectMember(row.dataset.memberId || '', {{ centerFit: true }});
  }});
  row.addEventListener('keydown', (event) => {{
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    selectMember(row.dataset.memberId || '', {{ centerFit: true }});
  }});
}});
storyChipNodes.forEach((node) => {{
  const getStoryBand = () => node.dataset.storyBand || node.dataset.storyBandKey || '';
  const activate = () => focusStoryBand(getStoryBand());
  const preview = () => setPreviewStoryBand(getStoryBand());
  node.addEventListener('mouseenter', preview);
  node.addEventListener('focus', preview);
  node.addEventListener('mouseleave', () => setPreviewStoryBand('', {{ render: true }}));
  node.addEventListener('blur', () => setPreviewStoryBand('', {{ render: true }}));
  node.addEventListener('click', activate);
  node.addEventListener('keydown', (event) => {{
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    activate();
  }});
}});
storyBandRows.forEach((row) => {{
  row.addEventListener('click', (event) => {{
    if (event.target instanceof Element && event.target.closest('a')) return;
    focusStoryBand(row.dataset.storyBand || row.dataset.storyBandKey || '');
  }});
  row.addEventListener('keydown', (event) => {{
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    focusStoryBand(row.dataset.storyBand || row.dataset.storyBandKey || '');
  }});
}});
compareRowNodes.forEach((row) => {{
  row.addEventListener('mouseenter', () => {{
    setHoveredCompareMember(String(row.dataset.memberId || memberIdsForDiffNode(row)[0] || '').trim());
  }});
  row.addEventListener('mouseleave', () => setHoveredCompareMember(''));
  row.addEventListener('click', (event) => {{
    if (event.target instanceof Element && event.target.closest('a')) return;
    activateMgtTab('compare');
    activateComparePage(row.dataset.comparePage || '0');
    const memberId = String(row.dataset.memberId || memberIdsForDiffNode(row)[0] || '').trim();
    if (memberId) {{
      selectMember(memberId, {{ centerFit: true }});
    }}
  }});
}});
comparePageRowNodes.forEach((row) => {{
  row.addEventListener('mouseenter', () => {{
    setHoveredCompareMember(String(row.dataset.memberId || memberIdsForDiffNode(row)[0] || '').trim());
  }});
  row.addEventListener('mouseleave', () => setHoveredCompareMember(''));
  row.addEventListener('click', (event) => {{
    if (event.target instanceof Element && event.target.closest('a')) return;
    activateMgtTab('compare');
    activateComparePage(row.dataset.comparePage || '0');
    const memberId = String(row.dataset.memberId || memberIdsForDiffNode(row)[0] || '').trim();
    if (memberId) {{
      selectMember(memberId, {{ centerFit: true }});
    }}
  }});
}});
comparePageTabButtons.forEach((button) => {{
  button.addEventListener('click', () => {{
    activateComparePage(button.dataset.comparePageTab || '0');
    updateComparePagerNav();
  }});
}});
comparePageNavButtons.forEach((button) => {{
  button.addEventListener('click', () => {{
    stepComparePage(button.dataset.comparePageNav || '');
    updateComparePagerNav();
  }});
}});
if (searchInput) {{
  searchInput.addEventListener('input', () => {{
    const query = String(searchInput.value || '').trim().toLowerCase();
    memberRows.forEach((row) => {{
      const haystack = String(row.dataset.search || '').toLowerCase();
      row.hidden = query && !haystack.includes(query);
    }});
  }});
}}
if (rawDiffSearchInput) {{
  rawDiffSearchInput.addEventListener('input', () => updateRawDiffFilter(rawDiffSearchInput.value || '', {{ matchMode: 'all' }}));
}}
if (cameraFlipButton) {{
  cameraFlipButton.addEventListener('click', () => toggleCameraFlip180());
}}
if (clearSelectionButton) {{
  clearSelectionButton.addEventListener('click', (event) => {{
    event.preventDefault();
    clearWorkspaceSelection();
    canvas?.focus?.();
  }});
}}
if (shareSelectionButton) {{
  shareSelectionButton.addEventListener('click', (event) => {{
    event.preventDefault();
    copyWorkspaceDeepLink();
  }});
}}
updateRawDiffFilter(rawDiffSearchInput ? rawDiffSearchInput.value || '' : '', {{ matchMode: 'all' }});
window.addEventListener('resize', () => {{
  resizeCanvas();
  render3D();
}});
resizeCanvas();
updateOverlayLegend();
resetCamera('iso');
const restoredWorkspaceSelection = restoreWorkspaceSelectionFromUrl();
if (memberRows.length && !restoredWorkspaceSelection) {{
  commitWorkspaceSelection({{ kind: 'member', id: memberRows[0].dataset.memberId || '', source: 'default-row' }}, {{ centerFit: true, syncDiff: false }});
}}
</script>
<script>
(() => {{
  const params = new URL(window.location.href).searchParams;
  const title = String(params.get('route_title') || '').trim();
  const banner = document.getElementById('route-context-banner');
  if (!banner || !title) return;

  const renderText = (id, value) => {{
    const element = document.getElementById(id);
    if (!element) return;
    const text = String(value || '').trim();
    element.textContent = text;
    element.hidden = !text;
  }};

  const reviewMode = String(params.get('review_mode') || '').replace(/[_-]+/g, ' ').trim();
  const routeStep = String(params.get('route_step') || '').trim();
  const fromLabel = String(params.get('from_label') || '').trim();
  const targetLabel = String(params.get('target_label') || '').trim();
  const selectionStatus = String(params.get('selection_status') || '').trim();
  const sourceLabel = String(params.get('source_label') || '').trim();
  const targetSurface = String(params.get('target_surface') || '').trim();

  renderText('route-context-title', title);
  renderText('route-context-step', [routeStep ? `step ${{routeStep}}` : '', reviewMode].filter(Boolean).join(' | '));
  renderText('route-context-source', fromLabel ? `from ${{fromLabel}}` : '');
  renderText('route-context-target', targetLabel ? `target ${{targetLabel}}` : '');
  renderText('route-context-status', selectionStatus ? `selection ${{selectionStatus}}` : '');
  renderText(
    'route-context-note',
    [sourceLabel ? `snapshot ${{sourceLabel}}` : '', targetSurface ? `surface ${{targetSurface}}` : '']
      .filter(Boolean)
      .join(' | '),
  );

  const returnTo = String(params.get('return_to') || '').trim();
  const returnLabel = String(params.get('return_label') || 'Structural Optimization Workbench').trim();
  const returnLink = document.getElementById('route-context-return');
  if (returnLink && returnTo) {{
    returnLink.href = returnTo;
    returnLink.textContent = returnLabel;
    returnLink.hidden = false;
  }}

  banner.hidden = false;
  const routeFocusId = String(params.get('route_focus') || '').trim();
  const routeFocusTarget = routeFocusId ? document.getElementById(routeFocusId) : null;
  if (routeFocusTarget) {{
    window.requestAnimationFrame(() => {{
      routeFocusTarget.classList.add('route-focus-target');
      routeFocusTarget.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
      window.setTimeout(() => routeFocusTarget.classList.remove('route-focus-target'), 2200);
    }});
  }}

  const normalizeRouteStoryBand = (value) => {{
    const raw = String(value || '').trim();
    if (!raw) return '';
    const numeric = Number(raw.replace(/^S/i, ''));
    if (Number.isFinite(numeric) && numeric > 0) {{
      return String(Math.trunc(numeric));
    }}
    return raw.replace(/^S/i, '').replace(/^0+/, '').trim();
  }};
  const flashRouteSelection = (node) => {{
    if (!node) return;
    if ('hidden' in node) {{
      node.hidden = false;
    }}
    window.requestAnimationFrame(() => {{
      node.classList.add('route-selection-target');
      node.scrollIntoView({{ behavior: 'smooth', block: 'center', inline: 'nearest' }});
      window.setTimeout(() => node.classList.remove('route-selection-target'), 2200);
    }});
  }};
  const routeMemberId = String(params.get('route_member_id') || '').trim();
  const routeStoryBand = String(params.get('route_story_band') || '').trim();
  const routeDiffIndex = String(params.get('route_diff_index') || '').trim();
  const routeDiffRowId = String(params.get('route_diff_row_id') || '').trim();
  const routeComparePage = String(params.get('route_compare_page') || '').trim();
  const routeStoryBandKey = normalizeRouteStoryBand(routeStoryBand);
  const routeStoryBandTarget = routeStoryBandKey
    ? storyBandRows.find(
        (row) => normalizeRouteStoryBand(row.dataset.storyBandKey || row.dataset.storyBand || row.dataset.story || '') === routeStoryBandKey,
      ) || null
    : null;
  if (routeStoryBandTarget) {{
    focusStoryBand(routeStoryBandTarget.dataset.storyBand || routeStoryBandTarget.dataset.storyBandKey || '');
    flashRouteSelection(routeStoryBandTarget);
  }}

  if (routeMemberId) {{
    selectMember(routeMemberId, {{ centerFit: true }});
    const routeMemberRow = memberRows.find((row) => String(row.dataset.memberId || '').trim() === routeMemberId) || null;
    if (routeMemberRow) {{
      routeMemberRow.hidden = false;
      flashRouteSelection(routeMemberRow);
    }}
  }}

  let routeDiffTarget = routeDiffIndex
    ? comparePageRowNodeByIndex.get(routeDiffIndex)
      || compareRowNodeByIndex.get(routeDiffIndex)
      || rawDiffNodeByIndex.get(routeDiffIndex)
      || null
    : null;
  if (!routeDiffTarget && routeDiffRowId) {{
    routeDiffTarget = [
      ...comparePageRowNodes,
      ...compareRowNodes,
      ...rawDiffLineNodes,
    ].find((node) => String(node.dataset.diffRowId || '').trim() === routeDiffRowId) || null;
  }}
  if (!routeDiffTarget && routeMemberId) {{
    routeDiffTarget = comparePageRowNodes.find((row) => memberIdsForDiffNode(row).includes(routeMemberId))
      || compareRowNodes.find((row) => memberIdsForDiffNode(row).includes(routeMemberId))
      || rawDiffLineNodes.find((row) => memberIdsForDiffNode(row).includes(routeMemberId))
      || null;
  }}
  if (routeComparePage) {{
    activateComparePage(routeComparePage);
  }}
  if (routeDiffTarget) {{
    const comparePage = String(routeDiffTarget.dataset.comparePage || routeComparePage || '').trim();
    const routeDiffMemberId = String(routeDiffTarget.dataset.memberId || memberIdsForDiffNode(routeDiffTarget)[0] || '').trim();
    if (routeDiffTarget.hasAttribute('data-raw-diff-line')) {{
      activateMgtTab('raw');
    }} else {{
      activateMgtTab('compare');
      activateComparePage(comparePage || '0');
    }}
    routeDiffTarget.hidden = false;
    if (!routeMemberId && routeDiffMemberId) {{
      selectMember(routeDiffMemberId, {{ centerFit: true }});
    }}
    flashRouteSelection(routeDiffTarget);
  }}
}})();
</script>
</body>
</html>
"""


def render_expert_review_html(payload: dict[str, Any]) -> str:
    case_id_raw = str(payload.get("case_id", "") or "optimized_drawing_review")
    case_id = html.escape(case_id_raw)
    case_title_raw = str(payload.get("case_title", "") or "Optimized Drawing Expert Review")
    case_title = html.escape(case_title_raw)
    case_note_raw = str(payload.get("case_note", "") or "")
    case_note = html.escape(case_note_raw)
    status_label_raw = str(payload.get("status_label", "") or "baseline + optimized overlay")
    status_label = html.escape(status_label_raw)
    expert_review_metadata = (
        payload.get("expert_review_metadata")
        if isinstance(payload.get("expert_review_metadata"), dict)
        else {}
    )

    def _meta_text(*keys: str, default: str = "") -> str:
        for key in keys:
            value = expert_review_metadata.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return str(default)

    project_name_raw = _meta_text("project_name", "project_title", default=case_title_raw)
    project_number_raw = _meta_text("project_number", "project_id", "job_number", default=case_id_raw.upper())
    client_name_raw = _meta_text("client_name", "owner_name", default="Client not provided")
    site_name_raw = _meta_text("site_name", "site_label", "project_site", default="Site not provided")
    authority_name_raw = _meta_text("authority_name", "jurisdiction_name", "authority_label", default="Authority of record")
    permit_label_raw = _meta_text("permit_label", "permit_review_label", default="Permit review")
    committee_label_raw = _meta_text("committee_label", "committee_review_label", default="Committee review")
    package_purpose_label_raw = _meta_text(
        "package_purpose_label",
        "submission_purpose",
        "package_label",
        default="Jurisdictional Structural Review Package",
    )
    issue_phase_label_raw = _meta_text(
        "issue_phase_label",
        "issue_stage_label",
        "submission_track_label",
        "permit_track_label",
        default=status_label_raw,
    )
    generated_date_raw = _format_generated_date(
        _meta_text("issue_date", "submission_date", "permit_issue_date", default=str(payload.get("generated_at", "") or ""))
    )
    generated_date = html.escape(generated_date_raw)
    issue_id_raw = _meta_text("package_id", "issue_id", default=f"EXP-{_safe_slug(case_id_raw).replace('-', '_').upper()}")
    issue_id = html.escape(issue_id_raw)
    story_rows = [row for row in (payload.get("story_band_rows") or []) if isinstance(row, dict)]
    top_members = [row for row in (payload.get("top_members") or []) if isinstance(row, dict)]
    projection_rows = [row for row in (payload.get("projection_rows") or []) if isinstance(row, dict)]
    real_drawing_corpus = _real_drawing_corpus_view(payload)
    changed_group_count = _safe_int(payload.get("changed_group_count", 0))
    changed_member_count = _safe_int(payload.get("changed_member_count", 0))
    total_element_count = _safe_int(payload.get("total_element_count", 0))
    signed_cost_proxy_delta_total = _safe_float(payload.get("signed_cost_proxy_delta_total", 0.0))
    constructability_delta_total = _safe_float(payload.get("constructability_delta_total", 0.0))
    max_dcr_after_max = _safe_float(payload.get("max_dcr_after_max", 0.0))
    viewer_core_href = html.escape(str(payload.get("viewer_core_href", "") or ""))
    viewer_html_href = html.escape(str(payload.get("viewer_html_href", "") or ""))
    committee_dashboard_href = html.escape(str(payload.get("committee_dashboard_href", "") or ""))
    analysis_gallery_href = html.escape(str(payload.get("analysis_gallery_href", "") or ""))
    project_registry_href = html.escape(str(payload.get("project_registry_href", "") or ""))
    project_package_href = html.escape(str(payload.get("project_package_href", "") or ""))
    batch_job_report_href = html.escape(str(payload.get("batch_job_report_href", "") or ""))
    mgt_export_report_href = html.escape(str(payload.get("mgt_export_report_href", "") or ""))
    mgt_source_mgt_href = html.escape(str(payload.get("mgt_source_mgt_href", "") or ""))
    mgt_output_mgt_href = html.escape(str(payload.get("mgt_output_mgt_href", "") or ""))
    mgt_loadcomb_roundtrip_report_href = html.escape(
        str(payload.get("mgt_loadcomb_roundtrip_report_href", "") or "")
    )
    expert_pdf_href = html.escape(str(payload.get("expert_pdf_href", "") or ""))
    internal_workspace_href = html.escape(str(payload.get("internal_review_href", "") or viewer_html_href or ""))

    mgt_export_contract_pass = bool(payload.get("mgt_export_contract_pass", False))
    mgt_export_output_mgt_exists = bool(payload.get("mgt_export_output_mgt_exists", False))
    mgt_export_loadcomb_roundtrip_pass = bool(payload.get("mgt_export_loadcomb_roundtrip_pass", False))
    mgt_export_support_mode = html.escape(str(payload.get("mgt_export_support_mode", "") or "n/a"))
    mgt_export_delivery_boundary = html.escape(str(payload.get("mgt_export_delivery_boundary", "") or "n/a"))
    mgt_export_reason = html.escape(str(payload.get("mgt_export_reason", "") or ""))
    mgt_export_native_authoring_summary_line = html.escape(
        str(payload.get("mgt_export_native_authoring_summary_line", "") or "n/a")
    )
    mgt_export_supported_change_count = _safe_int(payload.get("mgt_export_supported_change_count", 0))
    mgt_export_total_change_count = _safe_int(payload.get("mgt_export_total_change_count", 0))
    mgt_export_direct_patch_change_count = _safe_int(payload.get("mgt_export_direct_patch_change_count", 0))
    mgt_export_instruction_sidecar_zero_touch_verified_change_count = _safe_int(
        payload.get("mgt_export_instruction_sidecar_zero_touch_verified_change_count", 0)
    )
    mgt_export_unsupported_change_count = _safe_int(payload.get("mgt_export_unsupported_change_count", 0))
    mgt_export_loadcomb_combo_count = _safe_int(payload.get("mgt_export_loadcomb_combo_count", 0))
    mgt_export_audit_review_queue_pending_count = _safe_int(
        payload.get("mgt_export_audit_review_queue_pending_count", 0)
    )
    mgt_export_source_vs_output_diff_summary_line = html.escape(
        str(payload.get("mgt_export_source_vs_output_diff_summary_line", "") or "n/a")
    )
    mgt_compare_window_row_count = _safe_int(payload.get("mgt_compare_window_row_count", 0))

    midas_roundtrip_gate_summary_line = html.escape(
        str(payload.get("midas_roundtrip_gate_summary_line", "") or "n/a")
    )
    midas_roundtrip_gate_report_href = html.escape(str(payload.get("midas_roundtrip_gate_report_href", "") or ""))
    midas_roundtrip_gate_ready_count = _safe_int(payload.get("midas_roundtrip_gate_ready_count", 0))
    midas_roundtrip_gate_corpus_case_count = _safe_int(payload.get("midas_roundtrip_gate_corpus_case_count", 0))
    midas_roundtrip_gate_public_native_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_native_ready_count", 0)
    )
    midas_roundtrip_gate_public_source_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_source_ready_count", 0)
    )
    midas_roundtrip_gate_pending_review_total = _safe_int(payload.get("midas_roundtrip_gate_pending_review_total", 0))
    midas_roundtrip_gate_taxonomy_exact_count = _safe_int(payload.get("midas_roundtrip_gate_taxonomy_exact_count", 0))
    midas_roundtrip_gate_taxonomy_canonical_count = _safe_int(
        payload.get("midas_roundtrip_gate_taxonomy_canonical_count", 0)
    )
    real_drawing_corpus_evidence_line = ""
    if real_drawing_corpus["registered"]:
        ready_count = _safe_int(real_drawing_corpus["ready_count"])
        candidate_count = _safe_int(real_drawing_corpus["candidate_count"])
        ready_model_asset_count = _safe_int(real_drawing_corpus["ready_model_asset_count"])
        solver_exact_ready_count = _safe_int(real_drawing_corpus["solver_exact_ready_count"])
        proxy_or_preview_ready_count = _safe_int(real_drawing_corpus["proxy_or_preview_ready_count"])
        drawing_sheet_candidate_count = _safe_int(real_drawing_corpus["drawing_sheet_candidate_count"])
        project_count = _safe_int(real_drawing_corpus["project_count"])
        surface_label = html.escape(str(real_drawing_corpus["surface_label"] or "metadata-only"))
        real_drawing_corpus_evidence_line = (
            "<div class='sheet-receipt-line'><strong>Real drawing corpus</strong>: "
            f"{ready_count}/{candidate_count or max(ready_count, 1)} intake-ready model files, "
            f"{ready_model_asset_count} derived assets, {solver_exact_ready_count} solver-exact and "
            f"{proxy_or_preview_ready_count} proxy/preview rows across {project_count} projects; "
            f"{drawing_sheet_candidate_count} drawing-sheet candidates are registered as {surface_label}.</div>"
        )

    executive_cards_html = "".join(
        [
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Optimization scope</div>"
                f"<div class='expert-kpi-value'>{changed_group_count} groups / {changed_member_count} members</div>"
                "<div class='expert-kpi-note'>Changed groups and representative members carried into the review package.</div>"
                "</article>"
            ),
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Quantity / cost proxy</div>"
                f"<div class='expert-kpi-value'>{_format_signed(signed_cost_proxy_delta_total)}</div>"
                "<div class='expert-kpi-note'>Signed total reduction proxy across the optimized structural package.</div>"
                "</article>"
            ),
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Constructability delta</div>"
                f"<div class='expert-kpi-value'>{_format_signed(constructability_delta_total)}</div>"
                "<div class='expert-kpi-note'>Negative values indicate simplification or lighter detailing burden in this package.</div>"
                "</article>"
            ),
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Governing D/C after change</div>"
                f"<div class='expert-kpi-value'>{max_dcr_after_max:.3f}</div>"
                "<div class='expert-kpi-note'>Maximum reported demand/capacity ratio after optimization, retained below unity.</div>"
                "</article>"
            ),
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Native MIDAS export</div>"
                f"<div class='expert-kpi-value'>{'VERIFIED' if mgt_export_contract_pass and mgt_export_output_mgt_exists else 'CHECK'}</div>"
                f"<div class='expert-kpi-note'>Optimized .mgt {'was produced' if mgt_export_output_mgt_exists else 'was not produced'} and support scope is {mgt_export_support_mode}.</div>"
                "</article>"
            ),
            (
                "<article class='expert-kpi-card'>"
                "<div class='expert-kpi-label'>Validation receipt</div>"
                f"<div class='expert-kpi-value'>{'LOADCOMB exact' if mgt_export_loadcomb_roundtrip_pass else 'Review required'}</div>"
                f"<div class='expert-kpi-note'>Roundtrip cases {midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)} | pending review {midas_roundtrip_gate_pending_review_total}.</div>"
                "</article>"
            ),
        ]
    )

    projection_sheet_cards_html = "".join(
        (
            "<article class='sheet-figure-card'>"
            f"<div class='sheet-figure-head'><span>{html.escape(str(row.get('projection_label', '') or 'Projection'))}</span>"
            "<span>NOT TO SCALE</span></div>"
            f"<div class='sheet-figure-stage'>{str(row.get('overlay_svg_inline', '') or row.get('baseline_svg_inline', ''))}</div>"
            f"<div class='sheet-figure-note'>{html.escape(str(row.get('projection_note', '') or ''))}</div>"
            "</article>"
        )
        for row in projection_rows
    )

    story_schedule_rows_html = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(row.get('story_band', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('zone_label', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('member_type', '') or 'n/a'))}</td>"
            f"<td>{_safe_int(row.get('changed_group_count', 0))}</td>"
            f"<td>{_format_signed(row.get('cost_proxy_delta_sum', 0.0))}</td>"
            f"<td>{_format_signed(row.get('constructability_delta_sum', 0.0))}</td>"
            f"<td>{_safe_float(row.get('max_dcr_after_max', 0.0)):.3f}</td>"
            f"<td>{html.escape(_expert_change_reason(row), quote=True)}</td>"
            "</tr>"
        )
        for row in story_rows[:12]
    )
    if not story_schedule_rows_html:
        story_schedule_rows_html = (
            "<tr><td colspan='8' class='expert-empty'>No story-band revision rows were available for this package.</td></tr>"
        )

    why_changed_cards_html = "".join(
        (
            "<article class='why-card'>"
            f"<div class='why-card-head'>{html.escape(str(row.get('story_band', '') or 'n/a'))} · {html.escape(str(row.get('zone_label', '') or 'n/a'))}</div>"
            f"<div class='why-card-title'>{html.escape(str(row.get('member_type', '') or 'member').title(), quote=True)} revision priority</div>"
            f"<div class='why-card-copy'>{html.escape(_expert_change_reason(row), quote=True)}</div>"
            "<div class='why-card-tags'>"
            f"<span class='why-tag'>groups={_safe_int(row.get('changed_group_count', 0))}</span>"
            f"<span class='why-tag'>costΔ={_format_signed(row.get('cost_proxy_delta_sum', 0.0))}</span>"
            f"<span class='why-tag'>D/C after={_safe_float(row.get('max_dcr_after_max', 0.0)):.3f}</span>"
            "</div>"
            "</article>"
        )
        for row in story_rows[:3]
    )

    derived_representative_evidence_summary = _representative_evidence_completeness_summary(top_members)
    representative_evidence_summary = dict(derived_representative_evidence_summary)
    representative_evidence_summary_payload = payload.get("representative_evidence_completeness_summary")
    if isinstance(representative_evidence_summary_payload, dict):
        representative_evidence_summary.update(representative_evidence_summary_payload)
    representative_evidence_missing_field_counts_raw = representative_evidence_summary.get("missing_evidence_field_counts")
    if not isinstance(representative_evidence_missing_field_counts_raw, dict):
        representative_evidence_missing_field_counts_raw = derived_representative_evidence_summary.get(
            "missing_evidence_field_counts",
            {},
        )
    representative_evidence_total = _safe_int(representative_evidence_summary.get("total", len(top_members)))
    representative_evidence_complete = _safe_int(representative_evidence_summary.get("complete", 0))
    representative_evidence_partial = _safe_int(representative_evidence_summary.get("partial", 0))
    representative_evidence_missing = _safe_int(representative_evidence_summary.get("missing", 0))
    representative_evidence_missing_field_counts = {
        field_name: _safe_int(representative_evidence_missing_field_counts_raw.get(field_name, 0))
        for field_name in REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS
    }
    if representative_evidence_total <= 0:
        representative_evidence_status = "empty"
    elif representative_evidence_missing > 0 and representative_evidence_complete == 0 and representative_evidence_partial == 0:
        representative_evidence_status = "missing"
    elif representative_evidence_partial > 0 or representative_evidence_missing > 0:
        representative_evidence_status = "partial"
    else:
        representative_evidence_status = "complete"

    representative_evidence_preview_rows = list(top_members)
    if representative_evidence_preview_rows:
        representative_evidence_preview_rows = [
            row
            for _, row in sorted(
                enumerate(representative_evidence_preview_rows),
                key=lambda item: (
                    {"missing": 0, "partial": 1, "complete": 2}.get(
                        str(item[1].get("evidence_completeness_status", "") or "").strip().lower(),
                        3,
                    ),
                    item[0],
                ),
            )[:8]
        ]
    else:
        representative_evidence_preview_rows = []

    def _expert_evidence_status_badge(status: str) -> str:
        status_key = status if status in {"complete", "partial", "missing"} else "empty"
        label = {
            "complete": "complete",
            "partial": "partial",
            "missing": "missing",
            "empty": "No data",
        }[status_key]
        return f"<span class='expert-evidence-status is-{status_key}'>{html.escape(label)}</span>"

    def _expert_evidence_field_chip(field_name: str, value: str, *, fallback: bool = False) -> str:
        return (
            f"<span class='expert-evidence-field-chip {'is-fallback' if fallback else ''}'>"
            f"<span class='expert-evidence-inline-key'>{html.escape(field_name)}</span>"
            f"<span class='expert-evidence-inline-value'>{html.escape(value)}</span>"
            "</span>"
        )

    representative_evidence_summary_cards_html = "".join(
        (
            "<article class='expert-evidence-stat'>"
            f"<div class='expert-evidence-stat-label'>{label}</div>"
            f"<div class='expert-evidence-stat-value'>{value}</div>"
            f"<div class='expert-evidence-stat-note'>{note}</div>"
            "</article>"
        )
        for label, value, note in [
            (
                "Total rows",
                str(representative_evidence_total),
                "Representative members summarized by the completeness receipt.",
            ),
            (
                "Complete",
                str(representative_evidence_complete),
                "Rows where the tracked evidence hooks are all linked.",
            ),
            (
                "Partial",
                str(representative_evidence_partial),
                "Rows that still carry visible No data or not linked labels.",
            ),
            (
                "Missing",
                str(representative_evidence_missing),
                "Rows where every tracked evidence hook is still absent.",
            ),
        ]
    )

    representative_evidence_field_cards_html = "".join(
        (
            "<article class='expert-evidence-stat'>"
            f"<div class='expert-evidence-stat-label'>{field_label}</div>"
            f"<div class='expert-evidence-stat-value'>{_safe_int(representative_evidence_missing_field_counts.get(field_name, 0))}</div>"
            f"<div class='expert-evidence-stat-note'>missing label: {missing_label}</div>"
            "</article>"
        )
        for field_name, field_label, missing_label in [
            ("ai_reason", "AI reason", REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS["ai_reason"]),
            (
                "review_handoff_summary",
                "Review handoff",
                REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS["review_handoff_summary"],
            ),
            (
                "source_output_diff_focus",
                "Diff focus",
                REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS["source_output_diff_focus"],
            ),
            (
                "linked_diff_row_count",
                "linked_diff_row_count",
                REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS["linked_diff_row_count"],
            ),
        ]
    )

    def _expert_evidence_display_label(row: dict[str, Any], field_name: str) -> str:
        labels = row.get("evidence_display_labels") if isinstance(row.get("evidence_display_labels"), dict) else {}
        label = str(labels.get(field_name, "") or "").strip()
        if label:
            return label
        if field_name == "linked_diff_row_count":
            value = _optional_float(row.get(field_name))
            return str(value) if value is not None else REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS[field_name]
        text = str(row.get(field_name, "") or "").strip()
        return text if text else REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS[field_name]

    representative_evidence_preview_rows_html = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(row.get('member_id', '') or 'n/a'))}</td>"
            f"<td>{_expert_evidence_status_badge(str(row.get('evidence_completeness_status', '') or 'empty'))}</td>"
            "<td><div class='expert-evidence-field-stack'>"
            + (
                "".join(
                    _expert_evidence_field_chip(
                        field_name,
                        str(
                            (row.get("missing_evidence_labels") if isinstance(row.get("missing_evidence_labels"), dict) else {}).get(
                                field_name,
                                REPRESENTATIVE_MEMBER_MISSING_EVIDENCE_LABELS.get(field_name, "No data"),
                            )
                        ),
                        fallback=True,
                    )
                    for field_name in (row.get("missing_evidence_fields") or [])
                    if field_name in REPRESENTATIVE_MEMBER_EVIDENCE_FIELDS
                )
                or _expert_evidence_field_chip("missing_evidence_fields", "none")
            )
            + "</div></td>"
            "<td><div class='expert-evidence-field-stack'>"
            + _expert_evidence_field_chip(
                "ai_reason",
                _expert_evidence_display_label(row, "ai_reason"),
                fallback="ai_reason" in (row.get("missing_evidence_fields") or []),
            )
            + _expert_evidence_field_chip(
                "review_handoff_summary",
                _expert_evidence_display_label(row, "review_handoff_summary"),
                fallback="review_handoff_summary" in (row.get("missing_evidence_fields") or []),
            )
            + "</div></td>"
            "<td><div class='expert-evidence-field-stack'>"
            + _expert_evidence_field_chip(
                "source_output_diff_focus",
                _expert_evidence_display_label(row, "source_output_diff_focus"),
                fallback="source_output_diff_focus" in (row.get("missing_evidence_fields") or []),
            )
            + _expert_evidence_field_chip(
                "linked_diff_row_count",
                _expert_evidence_display_label(row, "linked_diff_row_count"),
                fallback="linked_diff_row_count" in (row.get("missing_evidence_fields") or []),
            )
            + "</div></td>"
            "</tr>"
        )
        for row in representative_evidence_preview_rows
    )
    if not representative_evidence_preview_rows_html:
        representative_evidence_preview_rows_html = (
            "<tr><td colspan='5' class='is-fallback'>No representative member evidence rows were available. "
            "missing_evidence_fields remain explicit when data arrives.</td></tr>"
        )

    expert_evidence_receipt_html = (
        "<aside class='expert-evidence-receipt' aria-label='Representative Evidence Receipt'>"
        "<div class='expert-evidence-receipt-head'>"
        "<div>"
        "<div class='expert-evidence-receipt-kicker'>Representative evidence completeness</div>"
        "<div class='expert-evidence-receipt-title'>Representative Evidence Receipt</div>"
        "<div class='expert-evidence-receipt-copy'>The package does not hide missing optimization rationale or diff linkage. "
        "Each representative member keeps missing_evidence_fields visible with explicit No data or not linked labels for PDF and HTML review.</div>"
        "</div>"
        f"{_expert_evidence_status_badge(representative_evidence_status)}"
        "</div>"
        f"<div class='expert-evidence-stats'>{representative_evidence_summary_cards_html}</div>"
        "<div class='expert-evidence-receipt-banner'><p><strong>Missing-data rule</strong>: blanks are not coerced to zero. "
        "Fields such as ai_reason, review_handoff_summary, source_output_diff_focus, and linked_diff_row_count remain visible until linked evidence is supplied.</p></div>"
        f"<div class='expert-evidence-stats'>{representative_evidence_field_cards_html}</div>"
        "<div class='expert-evidence-table-wrap'>"
        "<table class='expert-evidence-table'>"
        "<thead><tr>"
        "<th>Member</th>"
        "<th>Status</th>"
        "<th>missing_evidence_fields</th>"
        "<th>Review rationale</th>"
        "<th>Diff linkage</th>"
        "</tr></thead>"
        f"<tbody>{representative_evidence_preview_rows_html}</tbody>"
        "</table>"
        "</div>"
        "<div class='expert-evidence-footnote'>This receipt is intentionally placed before the representative member table so external reviewers can separate engineering change intent from incomplete handoff evidence.</div>"
        "</aside>"
    )

    member_sheet_rows_html = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(row.get('member_id', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('member_type', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('story_band_label', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('zone_label', '') or 'n/a'))}</td>"
            f"<td>{html.escape(str(row.get('action_name_label', '') or 'n/a'))}</td>"
            f"<td>{_format_signed(row.get('cost_delta', 0.0))}</td>"
            f"<td>{_format_signed(row.get('constructability_delta', 0.0))}</td>"
            f"<td>{html.escape(str(row.get('before_after_snapshot_note', '') or 'n/a'))}</td>"
            "</tr>"
        )
        for row in top_members[:10]
    )
    if not member_sheet_rows_html:
        member_sheet_rows_html = (
            "<tr><td colspan='8' class='expert-empty'>Representative changed members were not available for this package.</td></tr>"
        )

    expert_links_html = "".join(
        link
        for link in [
            f"<a class='expert-link-pill' href='{internal_workspace_href}'>Technical workspace</a>" if internal_workspace_href else "",
            f"<a class='expert-link-pill' href='{expert_pdf_href}'>PDF issue package</a>" if expert_pdf_href else "",
            f"<a class='expert-link-pill' href='{viewer_core_href}'>Core viewer</a>" if viewer_core_href else "",
            f"<a class='expert-link-pill' href='{mgt_output_mgt_href}'>Optimized .mgt</a>" if mgt_output_mgt_href else "",
            f"<a class='expert-link-pill' href='{mgt_source_mgt_href}'>Source .mgt</a>" if mgt_source_mgt_href else "",
            f"<a class='expert-link-pill' href='{mgt_export_report_href}'>Export report</a>" if mgt_export_report_href else "",
            f"<a class='expert-link-pill' href='{midas_roundtrip_gate_report_href}'>Roundtrip receipt</a>" if midas_roundtrip_gate_report_href else "",
            f"<a class='expert-link-pill' href='{committee_dashboard_href}'>Committee dashboard</a>" if committee_dashboard_href else "",
            f"<a class='expert-link-pill' href='{analysis_gallery_href}'>Evidence gallery</a>" if analysis_gallery_href else "",
            f"<a class='expert-link-pill' href='{project_registry_href}'>Project registry</a>" if project_registry_href else "",
            f"<a class='expert-link-pill' href='{project_package_href}'>Project package zip</a>" if project_package_href else "",
            f"<a class='expert-link-pill' href='{batch_job_report_href}'>Batch job report</a>" if batch_job_report_href else "",
        ]
    )

    validation_rows_html = "".join(
        (
            "<div class='validation-row'>"
            f"<div class='validation-label'>{label}</div>"
            f"<div class='validation-value'>{value}</div>"
            f"<div class='validation-note'>{note}</div>"
            "</div>"
        )
        for label, value, note in [
            (
                "MIDAS native export",
                "verified" if mgt_export_contract_pass and mgt_export_output_mgt_exists else "check",
                "Optimized .mgt package was emitted from the current optimization run and kept inside the supported native-authoring boundary.",
            ),
            (
                "Load combination roundtrip",
                "exact" if mgt_export_loadcomb_roundtrip_pass else "review",
                f"Load combination editor seed and roundtrip receipt remain aligned across {mgt_export_loadcomb_combo_count} combinations.",
            ),
            (
                "Supported scope",
                f"{mgt_export_supported_change_count}/{mgt_export_total_change_count or max(mgt_export_supported_change_count, 1)}",
                f"Direct patch {mgt_export_direct_patch_change_count}, zero-touch verified {mgt_export_instruction_sidecar_zero_touch_verified_change_count}, unsupported {mgt_export_unsupported_change_count}.",
            ),
            (
                "Review queue",
                str(mgt_export_audit_review_queue_pending_count),
                "Pending audit items remained at zero in this package, so the current surface is suitable for external engineering review rather than internal triage only.",
            ),
            (
                "Roundtrip breadth",
                f"{midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)} ready",
                f"Public native-ready {midas_roundtrip_gate_public_native_ready_count}, public source-ready {midas_roundtrip_gate_public_source_ready_count}, taxonomy exact {midas_roundtrip_gate_taxonomy_exact_count}, canonical {midas_roundtrip_gate_taxonomy_canonical_count}.",
            ),
            (
                "Source vs optimized diff",
                str(mgt_compare_window_row_count),
                "A widened MIDAS compare window is available for exact member jump and line-by-line review inside the technical workspace.",
            ),
        ]
    )

    sheet_total = 4
    package_purpose_label = package_purpose_label_raw
    revision_code = _meta_text("revision_code", default="REV-00")
    revision_status = _meta_text("revision_status", default="Issued for external review")
    prepared_by_label = _meta_text("prepared_by", "prepared_by_label", default="AI Structural Optimization Review Tool")
    reviewer_fill_label = _meta_text("reviewed_by", "reviewed_by_label", default="Reviewer to sign")
    discipline_label = _meta_text("discipline_label", default="Structural Optimization Review")
    checklist_head_label = _meta_text("checklist_head_label", default="Jurisdiction checklist")
    checklist_title_label = _meta_text(
        "checklist_title",
        default=f"{authority_name_raw} issue checklist",
    )
    signoff_head_label = _meta_text("signoff_head_label", default="Authority disposition")
    signoff_title_label = _meta_text(
        "signoff_title",
        default=f"{authority_name_raw} disposition block",
    )
    reviewer_office_label = _meta_text(
        "reviewer_label",
        "reviewer_office_label",
        default="Authority reviewer / office",
    )
    disposition_label = _meta_text("disposition_label", default="Disposition / permit status")
    comments_label = _meta_text("comments_label", default="Comments / conditions")
    signature_label = _meta_text("signature_label", default="Signature / date")

    def _sheet_titleblock_markup(
        sheet_code: str,
        sheet_title_text: str,
        sheet_copy_text: str,
        *,
        sheet_index: int,
        meta_pairs: list[tuple[str, str]],
    ) -> str:
        meta_html = "".join(
            f"<div class='sheet-meta'><span class='sheet-meta-label'>{html.escape(label, quote=True)}</span>"
            f"<span class='sheet-meta-value'>{html.escape(value, quote=True)}</span></div>"
            for label, value in meta_pairs
        )
        return (
            f"<div class='sheet-register'>{html.escape(package_purpose_label, quote=True)} | "
            f"SHEET {html.escape(sheet_code, quote=True)} / {sheet_total}</div>"
            "<div class='sheet-titleblock'>"
            "<div class='sheet-titleblock-head'>"
            f"<div class='sheet-kicker'>Sheet {html.escape(sheet_code, quote=True)}</div>"
            f"<div class='sheet-title'>{html.escape(sheet_title_text, quote=True)}</div>"
            f"<div class='sheet-copy'>{html.escape(sheet_copy_text, quote=True)}</div>"
            "</div>"
            "<div class='sheet-titleblock-side'>"
            "<div class='sheet-revision-stamp'>"
            "<div class='sheet-revision-kicker'>Revision Stamp</div>"
            f"<div class='sheet-revision-code'>{html.escape(revision_code, quote=True)}</div>"
            f"<div class='sheet-revision-line'>status={html.escape(revision_status, quote=True)}</div>"
            f"<div class='sheet-revision-line'>issue={html.escape(package_purpose_label, quote=True)}</div>"
            f"<div class='sheet-revision-line'>date={generated_date}</div>"
            "</div>"
            f"<div class='sheet-meta-grid'>{meta_html}</div>"
            "</div>"
            "</div>"
        )

    def _sheet_footer_titleblock_markup(sheet_code: str, *, sheet_index: int) -> str:
        footer_cells = [
            ("Project", project_name_raw),
            ("Project No", project_number_raw),
            ("Client", client_name_raw),
            ("Package", package_purpose_label),
            ("Discipline", discipline_label),
            ("Revision", revision_code),
            ("Issue Date", generated_date),
            ("Sheet", f"{sheet_code} / {sheet_total}"),
            ("Prepared By", prepared_by_label),
            ("Reviewed By", reviewer_fill_label),
        ]
        footer_html = "".join(
            "<div class='sheet-footer-cell'>"
            f"<span class='sheet-footer-label'>{html.escape(label, quote=True)}</span>"
            f"<strong class='sheet-footer-value'>{html.escape(value, quote=True)}</strong>"
            "</div>"
            for label, value in footer_cells
        )
        return (
            "<div class='sheet-footer-titleblock'>"
            "<div class='sheet-footer-brand'>AI Structural Optimization Review</div>"
            f"<div class='sheet-footer-grid'>{footer_html}</div>"
            "</div>"
        )

    reviewer_checklist_items = [
        (
            "Optimized .mgt attached to submission set",
            mgt_export_output_mgt_exists,
            "Optimized MIDAS file is available as part of the linked evidence bundle.",
        ),
        (
            "LOADCOMB roundtrip remains exact",
            mgt_export_loadcomb_roundtrip_pass,
            "Load combination editor seed stayed aligned with the exported package.",
        ),
        (
            "Unsupported change count remains zero",
            mgt_export_unsupported_change_count == 0,
            "No unsupported write-back actions were reported in this package.",
        ),
        (
            "Pending review queue remains zero",
            midas_roundtrip_gate_pending_review_total == 0,
            "Current package does not carry unresolved audit queue items.",
        ),
        (
            "Story-band schedule checked for governing stories",
            False,
            f"{authority_name_raw} reviewer to confirm that the controlling story bands were reviewed against office criteria.",
        ),
        (
            "Representative member callouts checked",
            False,
            "Reviewer to confirm that representative before/after member notes are acceptable for issue.",
        ),
        (
            f"{permit_label_raw} / {committee_label_raw} remarks appended",
            False,
            f"Use this line for {authority_name_raw} conditions, caveats, or submission notes.",
        ),
        (
            "Final authority disposition ready after reviewer comments",
            False,
            "Mark after manual comment resolution and issue approval.",
        ),
    ]
    reviewer_checklist_html = "".join(
        (
            "<div class='checklist-item "
            f"{'is-checked' if checked else 'is-open'}'>"
            f"<div class='checklist-box'>{'✓' if checked else ''}</div>"
            "<div class='checklist-body'>"
            f"<div class='checklist-title'>{html.escape(label, quote=True)}</div>"
            f"<div class='checklist-note'>{html.escape(note, quote=True)}</div>"
            "</div>"
            "</div>"
        )
        for label, checked, note in reviewer_checklist_items
    )

    executive_titleblock_html = _sheet_titleblock_markup(
        "E-01",
        "Executive Review Sheet",
        "Decision-ready overview for a structural reviewer: scope changed, governing ratios after revision, and the current validation position for the optimized MIDAS package.",
        sheet_index=1,
        meta_pairs=[
            ("Package ID", issue_id),
            ("Project No", project_number_raw),
            ("Authority", authority_name_raw),
            ("Issue Date", generated_date),
            ("Issue Track", issue_phase_label_raw),
        ],
    )
    drawings_titleblock_html = _sheet_titleblock_markup(
        "E-02",
        "Drawing Review Sheets",
        "Projection snapshots and the story-band revision schedule are grouped the way a reviewer typically reads them: overall location first, then height-based revision concentration.",
        sheet_index=2,
        meta_pairs=[
            ("Project", project_name_raw),
            ("Site", site_name_raw),
            ("Permit Track", permit_label_raw),
            ("Issue Stage", issue_phase_label_raw),
        ],
    )
    why_titleblock_html = _sheet_titleblock_markup(
        "E-03",
        "Why Changed / Representative Callouts",
        "This sheet rewrites the optimization output in structural review language: which members were reduced, what reserve remained after the change, and which representative members should be checked first.",
        sheet_index=3,
        meta_pairs=[
            ("Client", client_name_raw),
            ("Discipline", discipline_label),
            ("Prepared By", prepared_by_label),
            ("Reviewed By", reviewer_fill_label),
        ],
    )
    validation_titleblock_html = _sheet_titleblock_markup(
        "E-04",
        "Validation Receipt",
        "Validation is stated here in professional review language: export result, roundtrip behavior, supported scope, and corpus evidence. Raw diff and internal diagnostics stay linked rather than crowding the sheet.",
        sheet_index=4,
        meta_pairs=[
            ("Authority", authority_name_raw),
            ("Permit Track", permit_label_raw),
            ("Committee Track", committee_label_raw),
            ("Revision Status", revision_status),
        ],
    )

    return f"""<!doctype html>
<html lang='ko'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>{case_title} | External Expert Mode</title>
<style>
{build_signal_desk_light_css()}
:root {{
  --line-strong:#c8b89e;
  --paper:var(--surface-light-strong);
  --sheet:var(--surface-light);
  --sheet-shadow:0 22px 48px rgba(25,42,57,.08);
  --sheet-titleband:linear-gradient(180deg, rgba(255,248,238,.98) 0%, rgba(247,239,227,.98) 100%);
  --sheet-accent-line:rgba(15,106,115,.18);
}}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; background:linear-gradient(180deg,#f6f0e6 0%,#f8f4ec 35%,#f4efe7 100%); color:var(--ink); font-family:var(--font-ui); }}
body {{ padding:24px; }}
a {{ color:inherit; }}
.expert-page {{ max-width:1440px; margin:0 auto; display:grid; gap:20px; }}
.expert-hero {{
  display:grid;
  grid-template-columns:1.2fr .9fr;
  gap:18px;
}}
.expert-hero-main {{
  background:
    radial-gradient(circle at 18% 8%, rgba(255,255,255,.16), rgba(255,255,255,0) 32%),
    var(--review-hero-bg);
  color:#f4fbfc;
  padding:28px 30px;
}}
.expert-eyebrow {{
  color:#c8e9eb;
}}
.expert-hero-main h1 {{
  margin:10px 0 12px;
  font-size:var(--type-h1-size);
  line-height:var(--type-h1-line-height);
  letter-spacing:var(--type-h1-tracking);
}}
.expert-hero-main p {{
  margin:0;
  font-size:15px;
  line-height:1.72;
  color:#e0f0f1;
}}
.expert-link-row,.expert-mode-nav,.expert-hero-pills,.why-card-tags {{
  display:flex;
  flex-wrap:wrap;
  gap:8px;
}}
.expert-link-row {{ margin-top:0; }}
.expert-hero-pills {{ margin-top:16px; }}
.expert-toolbar {{
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:16px;
  align-items:center;
}}
.expert-link-pill,.expert-nav-link,.expert-pill {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:6px;
  text-decoration:none;
}}
.expert-nav-link {{
  background:var(--surface-light-strong);
  color:var(--ink);
}}
.expert-pill {{
  background:rgba(255,255,255,.16);
  color:#f4fbfc;
  border-color:rgba(255,255,255,.18);
}}
.expert-print-button {{
  appearance:none;
  border:1px solid rgba(255,255,255,.18);
  border-radius:var(--radius-pill);
  background:rgba(255,255,255,.16);
  color:#f4fbfc;
  min-height:36px;
  padding:0 14px;
  font:inherit;
  font-size:12px;
  font-weight:800;
  letter-spacing:.02em;
  cursor:pointer;
}}
.expert-hero-side {{
  background:var(--review-panel-bg);
  border:1px solid var(--line);
  padding:22px 24px;
  box-shadow:var(--sheet-shadow);
}}
.expert-hero-side h2 {{
  margin:0 0 10px;
}}
.expert-hero-side p {{ margin:0; color:var(--muted); }}
.expert-evidence-receipt {{
  border:1px solid rgba(79,183,173,.22);
  border-radius:22px;
  padding:18px;
  background:
    radial-gradient(circle at 92% 0%, rgba(79,183,173,.12), transparent 28%),
    linear-gradient(180deg,#122231 0%,#0c1620 100%);
  color:#edf4f7;
  box-shadow:0 18px 36px rgba(8,18,29,.18);
  display:grid;
  gap:14px;
}}
.expert-evidence-receipt-head {{
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:14px;
}}
.expert-evidence-receipt-kicker {{
  font-size:10px;
  letter-spacing:.14em;
  text-transform:uppercase;
  color:#94d7d9;
  font-weight:800;
}}
.expert-evidence-receipt-title {{
  margin-top:6px;
  font-family:var(--font-display);
  font-size:18px;
  line-height:1.12;
  letter-spacing:-0.03em;
  font-weight:800;
}}
.expert-evidence-receipt-copy {{
  margin-top:8px;
  font-size:13px;
  line-height:1.65;
  color:#c9d7df;
}}
.expert-evidence-status {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:32px;
  padding:0 12px;
  border-radius:var(--radius-pill);
  border:1px solid rgba(255,255,255,.12);
  font-size:11px;
  letter-spacing:.12em;
  text-transform:uppercase;
  font-weight:800;
  white-space:nowrap;
}}
.expert-evidence-status.is-complete {{
  background:rgba(47,125,90,.18);
  border-color:rgba(47,125,90,.34);
  color:#c8e9d5;
}}
.expert-evidence-status.is-partial {{
  background:rgba(244,181,107,.18);
  border-color:rgba(244,181,107,.32);
  color:#ffe1b8;
}}
.expert-evidence-status.is-missing {{
  background:rgba(161,73,46,.2);
  border-color:rgba(161,73,46,.34);
  color:#ffd9d1;
}}
.expert-evidence-status.is-empty {{
  background:rgba(150,160,173,.16);
  border-color:rgba(150,160,173,.26);
  color:#e1e8ee;
}}
.expert-evidence-receipt-banner {{
  border-radius:18px;
  border:1px solid rgba(255,255,255,.1);
  background:rgba(255,255,255,.04);
  padding:12px 14px;
}}
.expert-evidence-receipt-banner p {{
  margin:0;
  color:#dbe6eb;
  font-size:13px;
  line-height:1.6;
}}
.expert-evidence-stats {{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:10px;
}}
.expert-evidence-stat {{
  border-radius:16px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(255,255,255,.05);
  padding:12px 14px;
}}
.expert-evidence-stat-label {{
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#a6bac7;
  font-weight:800;
}}
.expert-evidence-stat-value {{
  margin-top:6px;
  font-family:var(--font-display);
  font-size:24px;
  line-height:1.05;
  letter-spacing:-0.03em;
  font-weight:800;
  color:#f5fbfc;
}}
.expert-evidence-stat-note {{
  margin-top:6px;
  font-size:12px;
  line-height:1.55;
  color:#c8d4db;
}}
.expert-evidence-table-wrap {{
  overflow:auto;
  border-radius:18px;
  border:1px solid rgba(255,255,255,.08);
  background:rgba(8,18,29,.22);
}}
.expert-evidence-table {{
  width:100%;
  min-width:0;
  border-collapse:collapse;
}}
.expert-evidence-table thead th {{
  background:rgba(255,255,255,.06);
  color:#a6bac7;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
}}
.expert-evidence-table th,
.expert-evidence-table td {{
  padding:10px 12px;
  border-bottom:1px solid rgba(255,255,255,.08);
  font-size:12px;
  line-height:1.45;
}}
.expert-evidence-table td {{
  color:#e7eef2;
}}
.expert-evidence-field-stack {{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
}}
.expert-evidence-field-chip {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  min-height:26px;
  padding:0 8px;
  border-radius:999px;
  border:1px solid rgba(255,255,255,.1);
  background:rgba(255,255,255,.05);
  color:#e7eef2;
}}
.expert-evidence-field-chip.is-fallback {{
  border-color:rgba(244,181,107,.2);
  background:rgba(244,181,107,.1);
  color:#ffe1b8;
}}
.expert-evidence-inline-key {{
  color:#a6bac7;
  font-weight:800;
}}
.expert-evidence-inline-value {{
  color:inherit;
}}
.expert-evidence-table tbody tr:nth-child(even) {{
  background:rgba(255,255,255,.02);
}}
.expert-evidence-table tbody tr:last-child td {{
  border-bottom:none;
}}
.expert-evidence-table td.is-fallback {{
  color:#c8d4db;
}}
.expert-evidence-footnote {{
  font-size:12px;
  line-height:1.6;
  color:#c0ced6;
}}
.expert-receipt-spaced,
.expert-mode-nav {{
  margin-top:16px;
}}
.expert-kpi-grid {{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:14px;
}}
.expert-kpi-card {{
  border:1px solid rgba(15,106,115,.12);
  padding:18px;
  background:var(--review-panel-bg);
  box-shadow:var(--sheet-shadow);
}}
.expert-kpi-label {{
  color:#617785;
}}
.expert-kpi-value {{
  margin-top:8px;
  color:var(--ink);
}}
.expert-kpi-note {{
  margin-top:8px;
  font-size:13px;
  line-height:1.65;
  color:var(--muted);
}}
.expert-sheet {{
  border:1px solid var(--line-strong);
  border-radius:var(--radius-xl);
  background:var(--paper);
  box-shadow:0 28px 60px rgba(26,42,56,.08);
  overflow:hidden;
  break-inside:avoid;
  page-break-inside:avoid;
}}
.sheet-register {{
  display:flex;
  align-items:center;
  justify-content:flex-end;
  gap:8px;
  padding:10px 20px 0;
  font-size:11px;
  letter-spacing:.14em;
  text-transform:uppercase;
  color:#7c6d60;
  font-weight:800;
}}
.sheet-titleblock {{
  display:grid;
  grid-template-columns:1.25fr .85fr;
  gap:18px;
  padding:22px 24px;
  background:var(--sheet-titleband);
  border-bottom:1px solid #d9cbb9;
  box-shadow:inset 0 -1px 0 rgba(15,106,115,.08);
}}
.sheet-titleblock-head {{
  display:grid;
  gap:6px;
}}
.sheet-titleblock-side {{
  display:grid;
  gap:12px;
}}
.sheet-kicker {{ color:#6c7f8a; }}
.sheet-title {{
  color:var(--ink);
}}
.sheet-copy {{
  color:var(--muted);
}}
.sheet-meta-grid {{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:10px;
}}
.sheet-revision-stamp {{
  border:2px solid rgba(143,74,25,.44);
  border-radius:18px;
  padding:12px 14px;
  background:linear-gradient(180deg,#fff8f2 0%,#fff0e2 100%);
  color:var(--accent-warm-ink);
  justify-self:end;
  min-width:240px;
  box-shadow:0 10px 18px rgba(181,93,51,.08);
}}
.sheet-revision-kicker {{
  font-size:10px;
  letter-spacing:.14em;
  text-transform:uppercase;
  font-weight:800;
  color:#97502d;
}}
.sheet-revision-code {{
  margin-top:6px;
  font-size:28px;
  line-height:1.02;
  letter-spacing:-0.04em;
  font-weight:900;
}}
.sheet-revision-line {{
  margin-top:4px;
  font-size:12px;
  line-height:1.55;
  color:#7a4a34;
}}
.sheet-meta {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:var(--radius-md);
  padding:10px 12px;
  background:#fffdf9;
}}
.sheet-meta-label {{
  display:block;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#74838f;
  font-weight:800;
}}
.sheet-meta-value {{
  display:block;
  margin-top:6px;
  font-size:13px;
  color:#334856;
  line-height:1.55;
}}
.sheet-body {{
  padding:22px 24px 26px;
  display:grid;
  gap:18px;
}}
.sheet-grid-2 {{
  display:grid;
  grid-template-columns:1.05fr .95fr;
  gap:16px;
}}
.sheet-note-panel {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  padding:16px 18px;
  background:var(--review-panel-quiet-bg);
}}
.sheet-note-panel h3 {{
  margin:0 0 10px;
  font-family:var(--font-display);
  font-size:18px;
  letter-spacing:-0.02em;
}}
.sheet-note-panel p, .sheet-note-panel li {{ color:var(--muted); }}
.sheet-note-panel ul {{
  margin:0;
  padding-left:18px;
}}
.sheet-figure-grid {{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:14px;
}}
.sheet-figure-card {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  overflow:hidden;
  background:#fffdf9;
}}
.sheet-figure-head {{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:8px;
  padding:10px 12px;
  border-bottom:1px solid rgba(15,106,115,.10);
  font-size:11px;
  text-transform:uppercase;
  letter-spacing:.1em;
  color:#6d7f89;
  font-weight:800;
}}
.sheet-figure-stage {{
  background:#fcfaf5;
  min-height:220px;
  display:grid;
  place-items:center;
  padding:10px;
}}
.sheet-figure-stage svg {{
  width:100%;
  height:auto;
  max-height:220px;
}}
.sheet-figure-note {{
  padding:12px;
  font-size:13px;
  line-height:1.65;
  color:var(--muted);
}}
.why-grid {{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:14px;
}}
.why-card {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  padding:16px;
  background:var(--review-panel-quiet-bg);
}}
.why-card-head {{
  font-size:11px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#6d7f89;
  font-weight:800;
}}
.why-card-title {{
  margin-top:8px;
  font-family:var(--font-display);
  font-size:18px;
  font-weight:800;
  letter-spacing:-0.03em;
}}
.why-card-copy {{
  margin-top:10px;
  font-size:14px;
  line-height:1.7;
  color:var(--muted);
}}
.why-tag {{
  display:inline-flex;
  align-items:center;
  justify-content:center;
  min-height:30px;
  padding:0 10px;
  border-radius:var(--radius-pill);
  border:1px solid var(--review-pill-warm-border);
  background:#fff9f0;
  font-size:11px;
  color:var(--accent-warm-ink);
}}
.expert-table-wrap {{
  overflow:auto;
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
}}
table {{
  width:100%;
  border-collapse:collapse;
  min-width:860px;
}}
th,td {{
  padding:12px 14px;
  border-bottom:1px solid #e8dfd3;
  text-align:left;
  vertical-align:top;
  font-size:13px;
}}
th {{
  background:#fbf6ed;
  font-size:11px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#6d7f89;
}}
tbody tr:nth-child(even) {{
  background:#fffdf9;
}}
.expert-empty {{
  text-align:center;
  color:var(--muted);
  padding:18px;
}}
.validation-grid {{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:14px;
}}
.validation-row {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  padding:16px;
  background:var(--review-panel-quiet-bg);
}}
.validation-label {{
  font-size:11px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#6d7f89;
  font-weight:800;
}}
.validation-value {{
  margin-top:8px;
  font-family:var(--font-display);
  font-size:24px;
  line-height:1.08;
  letter-spacing:-0.03em;
  font-weight:800;
}}
.validation-note {{
  margin-top:10px;
  font-size:14px;
  line-height:1.7;
  color:var(--muted);
}}
.sheet-receipt {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  padding:16px 18px;
  background:#fffdf9;
  display:grid;
  gap:8px;
}}
.sheet-receipt-line {{
  font-size:14px;
  line-height:1.72;
  color:var(--muted);
}}
.sheet-receipt-line strong {{
  color:var(--ink);
}}
.reviewer-checklist-grid {{
  display:grid;
  grid-template-columns:1.2fr .8fr;
  gap:16px;
}}
.reviewer-checklist-panel,.reviewer-signoff-panel {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:20px;
  padding:16px 18px;
  background:var(--review-panel-quiet-bg);
}}
.reviewer-checklist-head {{
  font-size:11px;
  letter-spacing:.14em;
  text-transform:uppercase;
  color:#6d7f89;
  font-weight:800;
}}
.reviewer-checklist-title {{
  margin-top:8px;
  font-family:var(--font-display);
  font-size:20px;
  line-height:1.08;
  letter-spacing:-0.03em;
  font-weight:800;
}}
.reviewer-checklist-copy {{
  margin-top:8px;
  font-size:14px;
  line-height:1.72;
  color:var(--muted);
}}
.checklist-grid {{
  display:grid;
  gap:10px;
  margin-top:14px;
}}
.checklist-item {{
  display:grid;
  grid-template-columns:24px 1fr;
  gap:12px;
  align-items:flex-start;
  padding:12px 0;
  border-top:1px solid #e6ddcf;
}}
.checklist-item:first-child {{
  border-top:0;
  padding-top:0;
}}
.checklist-box {{
  width:24px;
  height:24px;
  border-radius:6px;
  border:2px solid #ccb89f;
  display:grid;
  place-items:center;
  font-size:16px;
  font-weight:900;
  color:#ffffff;
  background:#fffdf8;
}}
.checklist-item.is-checked .checklist-box {{
  border-color:#0f6a73;
  background:#0f6a73;
}}
.checklist-item.is-open .checklist-box {{
  border-style:dashed;
}}
.checklist-title {{
  font-size:14px;
  line-height:1.55;
  font-weight:700;
  color:#2f4654;
}}
.checklist-note {{
  margin-top:4px;
  font-size:13px;
  line-height:1.68;
  color:var(--muted);
}}
.reviewer-signoff-grid {{
  display:grid;
  gap:12px;
  margin-top:14px;
}}
.reviewer-signoff-row {{
  display:grid;
  gap:6px;
}}
.reviewer-signoff-label {{
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#6d7f89;
  font-weight:800;
}}
.reviewer-signoff-line {{
  min-height:44px;
  border-bottom:1px solid #bfb2a0;
  display:flex;
  align-items:flex-end;
  padding-bottom:6px;
  color:#7b6b5d;
  font-size:13px;
}}
.sheet-footer-titleblock {{
  display:grid;
  gap:12px;
  margin-top:10px;
  padding:14px 18px 0;
  border-top:2px solid #cabbab;
}}
.sheet-footer-brand {{
  font-size:12px;
  letter-spacing:.16em;
  text-transform:uppercase;
  color:#6e7f8b;
  font-weight:800;
}}
.sheet-footer-grid {{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:10px;
}}
.sheet-footer-cell {{
  border:1px solid rgba(15,106,115,.10);
  border-radius:12px;
  padding:10px 12px;
  background:#fffdf9;
}}
.sheet-footer-label {{
  display:block;
  font-size:10px;
  letter-spacing:.12em;
  text-transform:uppercase;
  color:#70818c;
  font-weight:800;
}}
.sheet-footer-value {{
  display:block;
  margin-top:6px;
  font-size:13px;
  line-height:1.5;
  color:#2f4553;
}}
.sheet-titleblock,.sheet-footer-titleblock,.expert-table-wrap,table,thead,tbody,tr {{
  break-inside:avoid;
  page-break-inside:avoid;
}}
@page {{
  size:A3 landscape;
  margin:12mm;
}}
@media (max-width: 1120px) {{
  .expert-hero,.sheet-grid-2,.expert-kpi-grid,.sheet-figure-grid,.why-grid,.validation-grid,.reviewer-checklist-grid {{
    grid-template-columns:1fr;
  }}
  .sheet-titleblock {{
    grid-template-columns:1fr;
  }}
  .sheet-footer-grid {{
    grid-template-columns:1fr 1fr;
  }}
  .sheet-revision-stamp {{
    justify-self:start;
    min-width:0;
  }}
}}
@media print {{
  html,body {{
    background:#ffffff;
  }}
  body {{
    padding:0;
    -webkit-print-color-adjust:exact;
    print-color-adjust:exact;
  }}
  .expert-page {{
    max-width:none;
    gap:0;
  }}
  .expert-link-row,.expert-mode-nav,.expert-print-button {{
    display:none;
  }}
  .expert-hero {{
    margin-bottom:10mm;
    break-after:avoid-page;
    page-break-after:avoid;
  }}
  .expert-kpi-grid {{
    margin-bottom:10mm;
    break-after:page;
    page-break-after:always;
  }}
  .expert-sheet {{
    border-radius:0;
    box-shadow:none;
    border:1px solid #b9ac99;
    min-height:250mm;
    margin:0 0 10mm 0;
    break-after:page;
    page-break-after:always;
  }}
  .expert-sheet:last-of-type {{
    break-after:auto;
    page-break-after:auto;
  }}
  .expert-table-wrap {{
    overflow:visible;
  }}
  table {{
    min-width:0;
  }}
  thead {{
    display:table-header-group;
  }}
  tr,td,th {{
    break-inside:avoid;
    page-break-inside:avoid;
  }}
  .sheet-register {{
    padding-top:8mm;
  }}
  .sheet-figure-card,.validation-row,.reviewer-checklist-panel,.reviewer-signoff-panel,.sheet-note-panel,.why-card,.expert-evidence-receipt {{
    break-inside:avoid;
    page-break-inside:avoid;
  }}
}}
</style>
</head>
<body class='signal-desk-light'>
<div class='expert-page'>
  <section class='expert-hero'>
    <div class='expert-hero-main'>
      <div class='expert-eyebrow'>External Expert Mode</div>
      <h1>{case_title}</h1>
      <p>This package is organized for external structural review. It keeps the optimization story in engineering language: what changed, where the revised members are concentrated, why reserve could be reduced, and how the current MIDAS validation receipt supports the package.</p>
      <div class='expert-hero-pills'>
        <span class='expert-pill'>case={case_id}</span>
        <span class='expert-pill'>issue={issue_id}</span>
        <span class='expert-pill'>date={generated_date}</span>
        <span class='expert-pill'>status={status_label}</span>
        <span class='expert-pill'>project={html.escape(project_number_raw)}</span>
        <span class='expert-pill'>authority={html.escape(authority_name_raw)}</span>
      </div>
      <div class='expert-toolbar'>
        <div class='expert-link-row'>{expert_links_html}</div>
        <button class='expert-print-button' type='button' onclick='window.print()'>Print / Save PDF</button>
      </div>
    </div>
    <aside class='expert-hero-side'>
      <h2>Package Position</h2>
      <p>{case_note or "The current package compares the baseline structural model against the optimized structural revision and focuses on decision-ready review output."}</p>
      <div class='sheet-receipt expert-receipt-spaced'>
        <div class='sheet-receipt-line'><strong>Project</strong>: {html.escape(project_name_raw)} | {html.escape(project_number_raw)}</div>
        <div class='sheet-receipt-line'><strong>Client / Site</strong>: {html.escape(client_name_raw)} | {html.escape(site_name_raw)}</div>
        <div class='sheet-receipt-line'><strong>Authority track</strong>: {html.escape(authority_name_raw)} | {html.escape(permit_label_raw)} | {html.escape(committee_label_raw)}</div>
        <div class='sheet-receipt-line'><strong>Issue phase</strong>: {html.escape(issue_phase_label_raw)}</div>
      </div>
      <div class='expert-mode-nav'>
        <a class='expert-nav-link' href='#sheet-executive'>Sheet E-01 Executive Review</a>
        <a class='expert-nav-link' href='#sheet-drawings'>Sheet E-02 Drawing Review</a>
        <a class='expert-nav-link' href='#sheet-why'>Sheet E-03 Why Changed</a>
        <a class='expert-nav-link' href='#sheet-validation'>Sheet E-04 Validation Receipt</a>
      </div>
      <div class='sheet-receipt expert-receipt-spaced'>
        <div class='sheet-receipt-line'><strong>Native MIDAS export</strong>: {'verified' if mgt_export_contract_pass and mgt_export_output_mgt_exists else 'check'}</div>
        <div class='sheet-receipt-line'><strong>Load combination roundtrip</strong>: {'exact' if mgt_export_loadcomb_roundtrip_pass else 'review'}</div>
        <div class='sheet-receipt-line'><strong>Pending manual review</strong>: {mgt_export_audit_review_queue_pending_count}</div>
        <div class='sheet-receipt-line'><strong>Technical workspace</strong>: internal debug vocabulary and raw diff surfaces remain available through the linked workspace, not on this review package.</div>
      </div>
    </aside>
  </section>

  <section class='expert-kpi-grid'>
    {executive_cards_html}
  </section>

  <section class='expert-sheet' id='sheet-executive'>
    {executive_titleblock_html}
    <div class='sheet-body'>
      <div class='sheet-grid-2'>
        <div class='sheet-note-panel'>
          <h3>External reviewer summary</h3>
          <p>The optimized structural package retains a governing D/C of {max_dcr_after_max:.3f} while reducing the signed quantity/cost proxy by {_format_signed(signed_cost_proxy_delta_total)} and shifting constructability by {_format_signed(constructability_delta_total)}. The changed scope is concentrated into {changed_group_count} revision groups covering {changed_member_count} members, so the review target is narrow enough to inspect directly.</p>
          <p>For delivery, the current run produced an optimized MIDAS file ({'yes' if mgt_export_output_mgt_exists else 'no'}) and the load combination roundtrip remained {'exact' if mgt_export_loadcomb_roundtrip_pass else 'under review'}. This page intentionally strips internal debugging language and keeps only engineering review signals.</p>
        </div>
        <div class='sheet-note-panel'>
          <h3>Review notes</h3>
          <ul>
            <li>Optimization changes are shown as revised member groups, not as a free-form redraw of the entire model.</li>
            <li>Each story-band entry keeps a governing D/C after change so reserve reduction can be checked against the controlling level.</li>
            <li>The technical workspace and raw MIDAS line diff remain linked for exact follow-up inspection when needed.</li>
            <li>This issue is arranged for browser Print to PDF so the same sheet can be carried directly into permit or committee review.</li>
          </ul>
        </div>
      </div>
      {_sheet_footer_titleblock_markup("E-01", sheet_index=1)}
    </div>
  </section>

  <section class='expert-sheet' id='sheet-drawings'>
    {drawings_titleblock_html}
    <div class='sheet-body'>
      <div class='sheet-figure-grid'>{projection_sheet_cards_html}</div>
      <div class='expert-table-wrap'>
        <table>
          <thead>
            <tr>
              <th>Story</th>
              <th>Zone</th>
              <th>Member</th>
              <th>Groups</th>
              <th>Quantity / Cost delta</th>
              <th>Constructability</th>
              <th>Governing D/C after</th>
              <th>Reviewer note</th>
            </tr>
          </thead>
          <tbody>{story_schedule_rows_html}</tbody>
        </table>
      </div>
      {_sheet_footer_titleblock_markup("E-02", sheet_index=2)}
    </div>
  </section>

  <section class='expert-sheet' id='sheet-why'>
    {why_titleblock_html}
    <div class='sheet-body'>
      <div class='why-grid'>{why_changed_cards_html or "<div class='sheet-note-panel'>No why-changed cards were available.</div>"}</div>
      {expert_evidence_receipt_html}
      <div class='expert-table-wrap'>
        <table>
          <thead>
            <tr>
              <th>Member</th>
              <th>Type</th>
              <th>Story</th>
              <th>Zone</th>
              <th>Revision action</th>
              <th>Quantity / Cost delta</th>
              <th>Constructability</th>
              <th>Callout</th>
            </tr>
          </thead>
          <tbody>{member_sheet_rows_html}</tbody>
        </table>
      </div>
      {_sheet_footer_titleblock_markup("E-03", sheet_index=3)}
    </div>
  </section>

  <section class='expert-sheet' id='sheet-validation'>
    {validation_titleblock_html}
    <div class='sheet-body'>
      <div class='validation-grid'>{validation_rows_html}</div>
      <div class='reviewer-checklist-grid'>
        <div class='reviewer-checklist-panel'>
          <div class='reviewer-checklist-head'>{html.escape(checklist_head_label)}</div>
          <div class='reviewer-checklist-title'>{html.escape(checklist_title_label)}</div>
          <div class='reviewer-checklist-copy'>Use this panel when exporting to PDF for an authority, permit, or committee packet. The checked lines reflect machine-verifiable evidence; the open lines are intentionally left for reviewer confirmation and jurisdiction-specific remarks.</div>
          <div class='checklist-grid'>{reviewer_checklist_html}</div>
        </div>
        <div class='reviewer-signoff-panel'>
          <div class='reviewer-checklist-head'>{html.escape(signoff_head_label)}</div>
          <div class='reviewer-checklist-title'>{html.escape(signoff_title_label)}</div>
          <div class='reviewer-checklist-copy'>Print-to-PDF output keeps this block on the final validation sheet so comments, disposition, and signatures can be appended without rebuilding the package layout.</div>
          <div class='reviewer-signoff-grid'>
            <div class='reviewer-signoff-row'>
              <div class='reviewer-signoff-label'>{html.escape(reviewer_office_label)}</div>
              <div class='reviewer-signoff-line'></div>
            </div>
            <div class='reviewer-signoff-row'>
              <div class='reviewer-signoff-label'>{html.escape(disposition_label)}</div>
              <div class='reviewer-signoff-line'>Approved / Approved as noted / Revise and resubmit</div>
            </div>
            <div class='reviewer-signoff-row'>
              <div class='reviewer-signoff-label'>{html.escape(comments_label)}</div>
              <div class='reviewer-signoff-line'></div>
            </div>
            <div class='reviewer-signoff-row'>
              <div class='reviewer-signoff-label'>{html.escape(signature_label)}</div>
              <div class='reviewer-signoff-line'></div>
            </div>
          </div>
        </div>
      </div>
      <div class='sheet-grid-2'>
        <div class='sheet-receipt'>
          <div class='sheet-receipt-line'><strong>Native authoring summary</strong>: {mgt_export_native_authoring_summary_line}</div>
          <div class='sheet-receipt-line'><strong>Source vs optimized diff</strong>: {mgt_export_source_vs_output_diff_summary_line}</div>
          <div class='sheet-receipt-line'><strong>Roundtrip receipt</strong>: {midas_roundtrip_gate_summary_line}</div>
          <div class='sheet-receipt-line'><strong>Delivery boundary</strong>: {mgt_export_delivery_boundary}</div>
        </div>
        <div class='sheet-receipt'>
          <div class='sheet-receipt-line'><strong>Validation comment</strong>: The current package is appropriate for external engineering review because native export completed, the load combination roundtrip remained {('exact' if mgt_export_loadcomb_roundtrip_pass else 'under review')}, unsupported changes remained at {mgt_export_unsupported_change_count}, and pending review remained at {midas_roundtrip_gate_pending_review_total}.</div>
          <div class='sheet-receipt-line'><strong>Corpus evidence</strong>: {midas_roundtrip_gate_ready_count} ready cases inside a {midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)}-case roundtrip corpus, with {midas_roundtrip_gate_public_native_ready_count} public native-ready references.</div>
          {real_drawing_corpus_evidence_line}
          <div class='sheet-receipt-line'><strong>Follow-up path</strong>: Use the linked technical workspace for exact line diff, member click-through, and interactive 3D inspection if the reviewer wants to audit an individual callout.</div>
        </div>
      </div>
      {f"<div class='sheet-receipt'><div class='sheet-receipt-line'><strong>Export check note</strong>: {mgt_export_reason}</div></div>" if mgt_export_reason else ""}
      {_sheet_footer_titleblock_markup("E-04", sheet_index=4)}
    </div>
  </section>
</div>
</body>
</html>
"""


def prepare_review_payload(
    viewer_json_path: Path = DEFAULT_VIEWER_JSON,
    *,
    out_html_path: Path = DEFAULT_OUT_HTML,
    expert_metadata_json_path: Path = DEFAULT_EXPERT_METADATA_JSON,
    expert_metadata_template: str = DEFAULT_EXPERT_METADATA_TEMPLATE_NAME,
    expert_metadata_template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
    real_drawing_corpus_report_path: Path | None = DEFAULT_REAL_DRAWING_PRIVATE_CORPUS_REPORT,
    model_optimization_intake_queue_path: Path | None = DEFAULT_MODEL_OPTIMIZATION_INTAKE_QUEUE,
    redacted_manifest_path: Path | None = DEFAULT_REDACTED_MANIFEST,
) -> dict[str, Any]:
    expert_metadata_template_dir = _effective_expert_metadata_template_dir(expert_metadata_template_dir)
    viewer_payload = _load_json(viewer_json_path)
    payload = build_review_payload(viewer_payload, viewer_json_path=viewer_json_path, out_html_path=out_html_path)
    expert_review_metadata, expert_review_metadata_source_mode, expert_review_metadata_template, expert_review_metadata_template_path = _resolve_merged_expert_review_metadata(
        payload,
        expert_metadata_json_path=expert_metadata_json_path,
        expert_metadata_template=expert_metadata_template,
        expert_metadata_template_dir=expert_metadata_template_dir,
    )
    payload["expert_review_metadata"] = expert_review_metadata
    payload["expert_review_metadata_source_mode"] = expert_review_metadata_source_mode
    payload["expert_review_metadata_path"] = str(expert_metadata_json_path)
    payload["expert_review_metadata_template"] = str(expert_review_metadata_template or "")
    payload["expert_review_metadata_template_path"] = str(expert_review_metadata_template_path or "")
    template_index_payload = _load_expert_metadata_template_index(template_dir=expert_metadata_template_dir)
    template_index_path = _resolve_expert_metadata_template_index_path(template_dir=expert_metadata_template_dir)
    onboarding_schema_path = _resolve_expert_metadata_onboarding_schema_path(template_dir=expert_metadata_template_dir)
    onboarding_example_path = _resolve_expert_metadata_onboarding_example_path(template_dir=expert_metadata_template_dir)
    field_spec_path = _resolve_expert_metadata_field_spec_path(template_dir=expert_metadata_template_dir)
    template_record = _resolve_expert_metadata_template_record(
        expert_review_metadata_template,
        str(expert_review_metadata_template_path or ""),
        template_dir=expert_metadata_template_dir,
    )
    payload["expert_review_metadata_template_dir"] = str(expert_metadata_template_dir)
    payload["expert_review_metadata_template_index_path"] = str(template_index_path)
    payload["expert_review_metadata_onboarding_schema_path"] = str(onboarding_schema_path)
    payload["expert_review_metadata_onboarding_example_path"] = str(onboarding_example_path)
    payload["expert_review_metadata_field_spec_path"] = str(field_spec_path)
    payload["expert_review_metadata_template_index_href"] = _review_artifact_href(template_index_path, base_dir=out_html_path.parent)
    payload["expert_review_metadata_onboarding_schema_href"] = _review_artifact_href(onboarding_schema_path, base_dir=out_html_path.parent)
    payload["expert_review_metadata_onboarding_example_href"] = _review_artifact_href(onboarding_example_path, base_dir=out_html_path.parent)
    payload["expert_review_metadata_field_spec_href"] = _review_artifact_href(field_spec_path, base_dir=out_html_path.parent)
    payload["expert_review_metadata_template_set"] = {
        "template_set_name": str(template_index_payload.get("template_set_name", "") or "").strip(),
        "template_set_label": str(template_index_payload.get("template_set_label", "") or "").strip(),
        "template_set_description": str(template_index_payload.get("template_set_description", "") or "").strip(),
        "default_template": str(template_index_payload.get("default_template", "") or "").strip(),
    }
    payload["expert_review_metadata_template_record"] = template_record
    payload["expert_review_metadata_template_selection_receipt"] = _build_expert_metadata_template_selection_receipt(
        template_record,
        source_mode=expert_review_metadata_source_mode,
    )
    payload["expert_review_metadata_onboarding_purpose"] = str(
        template_index_payload.get("project_onboarding_purpose", "") or ""
    ).strip() or "Customer-facing intake form for expert review title block, routing, and reviewer labels."
    payload["expert_review_metadata_onboarding_sections"] = _string_list(
        template_index_payload.get("project_onboarding_sections")
    )
    # Keep the earlier alias so summary consumers do not lose compatibility.
    payload["expert_issue_metadata"] = expert_review_metadata
    payload["expert_issue_metadata_source_mode"] = expert_review_metadata_source_mode
    payload["expert_issue_metadata_path"] = str(expert_metadata_json_path)
    payload["real_drawing_private_corpus"] = _build_real_drawing_private_corpus_payload(
        corpus_report_path=real_drawing_corpus_report_path,
        intake_queue_path=model_optimization_intake_queue_path,
        redacted_manifest_path=redacted_manifest_path,
        out_html_path=out_html_path,
    )
    return payload


def _review_artifact_href(target: Path | str, *, base_dir: Path) -> str:
    return _rel_href(target, base_dir=base_dir)


def _real_corpus_public_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _safe_int(count, 0) for key, count in value.items() if str(key).strip()}


def _real_corpus_path(path: Path | None) -> Path | None:
    if path is None:
        return None
    return path if path.exists() and path.is_file() else None


def _build_real_drawing_private_corpus_payload(
    *,
    corpus_report_path: Path | None = DEFAULT_REAL_DRAWING_PRIVATE_CORPUS_REPORT,
    intake_queue_path: Path | None = DEFAULT_MODEL_OPTIMIZATION_INTAKE_QUEUE,
    redacted_manifest_path: Path | None = DEFAULT_REDACTED_MANIFEST,
    out_html_path: Path = DEFAULT_OUT_HTML,
) -> dict[str, Any]:
    report_path = _real_corpus_path(corpus_report_path)
    queue_path = _real_corpus_path(intake_queue_path)
    manifest_path = _real_corpus_path(redacted_manifest_path)
    if not any((report_path, queue_path, manifest_path)):
        return {
            "available": False,
            "release_surface": "not_registered",
            "summary_line": "No real drawing private corpus intake artifacts were found.",
        }

    report_payload = _load_json(report_path) if report_path else {}
    queue_payload = _load_json(queue_path) if queue_path else {}
    manifest_payload = _load_json(manifest_path) if manifest_path else {}
    report_summary = report_payload.get("summary") if isinstance(report_payload.get("summary"), dict) else {}
    manifest_summary = (
        report_payload.get("manifest_summary")
        if isinstance(report_payload.get("manifest_summary"), dict)
        else manifest_payload.get("summary")
        if isinstance(manifest_payload.get("summary"), dict)
        else {}
    )
    queue_summary = (
        report_payload.get("queue_summary")
        if isinstance(report_payload.get("queue_summary"), dict)
        else queue_payload.get("summary")
        if isinstance(queue_payload.get("summary"), dict)
        else {}
    )
    consistency = report_payload.get("consistency") if isinstance(report_payload.get("consistency"), dict) else {}
    policy = manifest_payload.get("policy") if isinstance(manifest_payload.get("policy"), dict) else {}
    projects = [row for row in (manifest_payload.get("projects") or []) if isinstance(row, dict)]
    files = [
        file_row
        for project in projects
        for file_row in (project.get("files") or [])
        if isinstance(file_row, dict)
    ]
    queue_rows = [row for row in (queue_payload.get("queue") or []) if isinstance(row, dict)]
    source_status = {
        "corpus_report_loaded": bool(report_path),
        "model_optimization_intake_queue_loaded": bool(queue_path),
        "redacted_manifest_loaded": bool(manifest_path),
    }
    contract_pass = bool(
        report_payload.get("contract_pass", False)
        or queue_payload.get("contract_pass", False)
        or manifest_payload.get("contract_pass", False)
    )
    manifest_file_type_counts = _real_corpus_public_count_map(
        manifest_summary.get("file_type_counts")
        or {
            file_type: sum(1 for file_row in files if str(file_row.get("file_type", "") or "") == file_type)
            for file_type in sorted({str(file_row.get("file_type", "") or "") for file_row in files if str(file_row.get("file_type", "") or "")})
        }
    )
    route_counts = _real_corpus_public_count_map(queue_summary.get("route_counts"))
    status_counts = _real_corpus_public_count_map(queue_summary.get("status_counts"))
    ready_count = _safe_int(
        queue_summary.get(
            "optimized_drawing_generation_ready_count",
            sum(1 for row in queue_rows if bool(row.get("ready_for_optimized_drawing_generation", False))),
        )
    )
    candidate_count = _safe_int(queue_summary.get("candidate_file_count", len(queue_rows)))
    ready_model_asset_count = _safe_int(
        queue_summary.get(
            "optimized_drawing_generation_ready_model_asset_count",
            sum(_safe_int(row.get("model_asset_count", 0)) for row in queue_rows if row.get("ready_for_optimized_drawing_generation")),
        )
    )
    project_count = _safe_int(manifest_summary.get("project_count", len(projects)))
    file_count = _safe_int(manifest_summary.get("file_count", len(files)))
    drawing_sheet_candidate_count = _safe_int(
        manifest_summary.get(
            "drawing_sheet_candidate_count",
            sum(_safe_int(file_row.get("pdf_page_count", 0)) for file_row in files if file_row.get("drawing_review_candidate")),
        )
    )
    release_surface_allowed = bool(
        policy.get("release_surface_allowed", manifest_summary.get("release_surface_allowed", False))
    )
    raw_redistribution_allowed = bool(
        policy.get("raw_redistribution_allowed", manifest_summary.get("raw_redistribution_allowed", False))
    )
    raw_redistribution_allowed_count = _safe_int(manifest_summary.get("raw_redistribution_allowed_count", 0))
    release_surface_allowed_count = _safe_int(manifest_summary.get("release_surface_allowed_count", 0))
    surface_safe = bool(
        consistency.get("surface_safe", False)
        or (
            not release_surface_allowed
            and not raw_redistribution_allowed
            and raw_redistribution_allowed_count == 0
            and release_surface_allowed_count == 0
        )
    )
    release_surface = "release_safe_metadata_only" if surface_safe else "review_required"
    summary_line = (
        f"real drawing corpus: {ready_count}/{candidate_count or max(ready_count, 1)} intake-ready assets, "
        f"{project_count} projects, {drawing_sheet_candidate_count} drawing-sheet candidates; "
        f"raw redistribution={'allowed' if raw_redistribution_allowed else 'blocked'}."
    )
    return {
        "available": True,
        "registered": ready_count > 0,
        "schema_version": "real-drawing-private-corpus-release-surface.v1",
        "generated_at": str(report_payload.get("generated_at") or queue_payload.get("generated_at") or manifest_payload.get("generated_at") or ""),
        "contract_pass": contract_pass,
        "reason_code": str(report_payload.get("reason_code") or queue_payload.get("reason_code") or ""),
        "release_surface": release_surface,
        "source_status": source_status,
        "summary_line": summary_line,
        "policy": {
            "private_only": bool(manifest_summary.get("private_only", True)),
            "raw_redistribution_allowed": raw_redistribution_allowed,
            "raw_redistribution_allowed_count": raw_redistribution_allowed_count,
            "release_surface_allowed": release_surface_allowed,
            "release_surface_allowed_count": release_surface_allowed_count,
            "surface_safe": surface_safe,
            "storage_boundary": str(
                policy.get("storage_boundary", manifest_summary.get("storage_boundary", "private_corpus_only")) or ""
            ),
            "license_basis": str(policy.get("license_basis", manifest_summary.get("license_basis", "")) or ""),
        },
        "summary": {
            "project_count": project_count,
            "file_count": file_count,
            "total_mb": round(_safe_float(manifest_summary.get("total_mb", 0.0)), 3),
            "drawing_review_candidate_count": _safe_int(manifest_summary.get("drawing_review_candidate_count", 0)),
            "drawing_sheet_candidate_count": drawing_sheet_candidate_count,
            "candidate_file_count": candidate_count,
            "model_optimization_candidate_count": _safe_int(
                manifest_summary.get("model_optimization_candidate_count", candidate_count)
            ),
            "model_asset_count": _safe_int(
                manifest_summary.get(
                    "model_optimization_asset_count",
                    ready_model_asset_count,
                )
            ),
            "optimized_drawing_generation_ready_count": ready_count,
            "ready_asset_count": ready_count,
            "ready_model_asset_count": ready_model_asset_count,
            "solver_exact_ready_count": _safe_int(queue_summary.get("solver_exact_ready_count", 0)),
            "solver_graph_ready_count": _safe_int(queue_summary.get("solver_graph_ready_count", 0)),
            "proxy_or_preview_ready_count": _safe_int(queue_summary.get("proxy_or_preview_ready_count", 0)),
            "direct_mgt_ready_count": _safe_int(
                report_payload.get("queue_breakdown", {}).get("direct_mgt_ready_count", 0)
                if isinstance(report_payload.get("queue_breakdown"), dict)
                else queue_summary.get("direct_mgt_solver_exact_count", 0)
            ),
            "ifc_proxy_graph_ready_count": _safe_int(queue_summary.get("ifc_proxy_graph_ready_count", 0)),
            "archive_hard_tier_ready_count": _safe_int(queue_summary.get("archive_hard_tier_ready_count", 0)),
            "archive_hard_tier_blocked_count": _safe_int(queue_summary.get("archive_hard_tier_blocked_count", 0)),
            "ready_node_count_total": _safe_int(queue_summary.get("ready_node_count_total", 0)),
            "ready_element_count_total": _safe_int(queue_summary.get("ready_element_count_total", 0)),
            "remaining_blocker_count": _safe_int(report_summary.get("remaining_blocker_count", 0)),
        },
        "file_type_counts": manifest_file_type_counts,
        "route_counts": route_counts,
        "status_counts": status_counts,
        "consistency": {
            "counts_consistent": bool(consistency.get("counts_consistent", False)),
            "surface_safe": bool(consistency.get("surface_safe", False)),
            "tier_acceptance_all_pass": bool(consistency.get("tier_acceptance_all_pass", False)),
            "release_surface_allowed_count_zero": bool(
                consistency.get("release_surface_allowed_count_zero", False)
            ),
            "raw_redistribution_allowed_false": bool(consistency.get("raw_redistribution_allowed_false", False)),
            "input_artifact_freshness_pass": bool(consistency.get("input_artifact_freshness_pass", False)),
        },
    }


def _build_artifact_href_validation(
    hrefs: dict[str, Any],
    *,
    base_dir: Path,
    required_keys: set[str] | None = None,
    generated_keys: set[str] | None = None,
) -> dict[str, Any]:
    required = required_keys or set()
    generated = generated_keys or set()
    entries: list[dict[str, Any]] = []
    for key, value in sorted(hrefs.items()):
        href = str(value or "").strip()
        if not href:
            continue
        split = urlsplit(href)
        is_external = bool(split.scheme or split.netloc)
        local_path = split.path if not is_external else ""
        target_exists = False
        if is_external:
            status = "external"
        elif not local_path:
            status = "empty"
        else:
            target_exists = key in generated or (base_dir / local_path).exists()
            if target_exists:
                status = "ok"
            elif key in required:
                status = "missing_required"
            else:
                status = "missing_optional"
        entries.append(
            {
                "key": key,
                "href": href,
                "status": status,
                "required": key in required,
                "exists": bool(target_exists),
                "external": is_external,
            }
        )
    missing_required = [entry for entry in entries if entry["status"] == "missing_required"]
    missing_optional = [entry for entry in entries if entry["status"] == "missing_optional"]
    return {
        "pass": not missing_required,
        "base_dir": str(base_dir),
        "checked_count": len(entries),
        "ok_count": sum(1 for entry in entries if entry["status"] == "ok"),
        "external_count": sum(1 for entry in entries if entry["status"] == "external"),
        "missing_required_count": len(missing_required),
        "missing_optional_count": len(missing_optional),
        "missing_required_keys": [str(entry["key"]) for entry in missing_required],
        "missing_optional_keys": [str(entry["key"]) for entry in missing_optional],
        "entries": entries,
    }


ARCHIVE_HANDOFF_CONTRACT_VERSION = "optimized-review-archive-handoff-v1"
ARCHIVE_HANDOFF_REQUIRED_HREF_KEYS = {
    "optimized_review_html_href",
    "expert_review_html_href",
    "review_summary_json_href",
    "expert_metadata_json_href",
    "mgt_export_report_href",
    "mgt_source_mgt_href",
    "mgt_optimized_mgt_href",
    "mgt_loadcomb_roundtrip_report_href",
    "midas_roundtrip_gate_report_href",
}
ARCHIVE_HANDOFF_OPTIONAL_HREF_KEYS = {
    "project_registry_href",
    "project_package_zip_href",
    "project_registry_signature_href",
}
PROJECT_PACKAGE_MEMBERSHIP_CONTRACT_VERSION = "optimized-review-project-package-membership-v1"
PROJECT_PACKAGE_REQUIRED_MEMBERS: tuple[dict[str, str], ...] = (
    {
        "artifact_key": "optimized_review_html_href",
        "artifact_name": "optimized_drawing_review.html",
        "package_member": "visualization/optimized_drawing_review.html",
    },
    {
        "artifact_key": "expert_review_html_href",
        "artifact_name": "optimized_drawing_expert_review.html",
        "package_member": "visualization/optimized_drawing_expert_review.html",
    },
    {
        "artifact_key": "review_summary_json_href",
        "artifact_name": "optimized_drawing_review_summary.json",
        "package_member": "visualization/optimized_drawing_review_summary.json",
    },
    {
        "artifact_key": "expert_metadata_json_href",
        "artifact_name": "optimized_drawing_expert_review.metadata.json",
        "package_member": "visualization/optimized_drawing_expert_review.metadata.json",
    },
)


def _compact_artifact_href_validation(validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "pass": bool(validation.get("pass", False)),
        "checked_count": _safe_int(validation.get("checked_count", 0)),
        "ok_count": _safe_int(validation.get("ok_count", 0)),
        "external_count": _safe_int(validation.get("external_count", 0)),
        "missing_required_count": _safe_int(validation.get("missing_required_count", 0)),
        "missing_optional_count": _safe_int(validation.get("missing_optional_count", 0)),
        "missing_required_keys": [str(key) for key in (validation.get("missing_required_keys") or [])],
        "missing_optional_keys": [str(key) for key in (validation.get("missing_optional_keys") or [])],
    }


def _first_existing_reference_path(reference: str, *, base_dir: Path) -> Path | None:
    for candidate in _candidate_reference_paths(reference, base_dir=base_dir):
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _file_receipt(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists() or not path.is_file():
        return {
            "artifact_exists": False,
            "artifact_bytes": 0,
            "artifact_sha256": "",
        }
    data = path.read_bytes()
    return {
        "artifact_exists": True,
        "artifact_bytes": len(data),
        "artifact_sha256": hashlib.sha256(data).hexdigest(),
    }


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _zip_member_names(path: Path | None) -> set[str]:
    if path is None or not path.exists() or not path.is_file():
        return set()
    try:
        with zipfile.ZipFile(path) as archive:
            return set(archive.namelist())
    except zipfile.BadZipFile:
        return set()


def _upsert_project_package_required_members(
    hrefs: dict[str, str],
    *,
    base_dir: Path,
) -> dict[str, Any]:
    package_href = str(hrefs.get("project_package_zip_href", "") or "")
    package_path = _first_existing_reference_path(package_href, base_dir=base_dir)
    if package_path is None:
        return {
            "updated": False,
            "reason": "project_package_zip_missing",
            "updated_members": [],
        }

    source_rows: list[tuple[str, Path]] = []
    for required in PROJECT_PACKAGE_REQUIRED_MEMBERS:
        artifact_href = str(hrefs.get(required["artifact_key"], "") or "")
        artifact_path = _first_existing_reference_path(artifact_href, base_dir=base_dir)
        if artifact_path is None:
            continue
        source_rows.append((required["package_member"], artifact_path))

    if not source_rows:
        return {
            "updated": False,
            "reason": "no_required_member_sources",
            "updated_members": [],
        }

    preserved_entries: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(package_path, mode="r") as archive:
            for info in archive.infolist():
                if info.filename in {member for member, _ in source_rows}:
                    continue
                preserved_entries[info.filename] = archive.read(info.filename)
    except zipfile.BadZipFile:
        preserved_entries = {}

    for member, artifact_path in source_rows:
        preserved_entries[member] = artifact_path.read_bytes()

    package_manifest_payload: dict[str, Any] | None = None
    if "package_manifest.json" in preserved_entries:
        try:
            package_manifest_payload = json.loads(preserved_entries["package_manifest.json"].decode("utf-8"))
        except Exception:
            package_manifest_payload = None
    if isinstance(package_manifest_payload, dict):
        existing_rows = [
            row
            for row in (package_manifest_payload.get("artifact_rows") or [])
            if isinstance(row, dict)
            and f"artifacts/{str(row.get('label', '') or '')}" in preserved_entries
        ]
        existing_labels = {str(row.get("label", "") or "") for row in existing_rows}
        for member, artifact_path in source_rows:
            label = member
            if label in existing_labels:
                continue
            payload = artifact_path.read_bytes()
            existing_rows.append(
                {
                    "label": label,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "bytes": len(payload),
                }
            )
            existing_labels.add(label)
        package_manifest_payload["artifact_rows"] = existing_rows
        preserved_entries["package_manifest.json"] = _canonical_json_bytes(package_manifest_payload)

    package_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(package_path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name, payload in sorted(preserved_entries.items(), key=lambda item: item[0]):
            info = zipfile.ZipInfo(filename=name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            archive.writestr(info, payload)

    return {
        "updated": True,
        "reason": "required_members_upserted",
        "updated_members": [member for member, _ in source_rows],
    }


def _build_project_package_membership_contract(
    hrefs: dict[str, str],
    *,
    base_dir: Path,
) -> dict[str, Any]:
    package_href = str(hrefs.get("project_package_zip_href", "") or "")
    package_path = _first_existing_reference_path(package_href, base_dir=base_dir)
    package_receipt = _file_receipt(package_path)
    zip_names = _zip_member_names(package_path)
    package_exists = bool(package_receipt.get("artifact_exists", False))

    artifact_rows: list[dict[str, Any]] = []
    for required in PROJECT_PACKAGE_REQUIRED_MEMBERS:
        artifact_key = required["artifact_key"]
        artifact_href = str(hrefs.get(artifact_key, "") or "")
        artifact_path = _first_existing_reference_path(artifact_href, base_dir=base_dir)
        artifact_receipt = _file_receipt(artifact_path)
        package_member = required["package_member"]
        package_member_present = package_member in zip_names
        artifact_rows.append(
            {
                "artifact_key": artifact_key,
                "artifact_name": required["artifact_name"],
                "artifact_href": artifact_href,
                "artifact_path": str(artifact_path or ""),
                "package_member": package_member,
                "artifact_exists": bool(artifact_receipt.get("artifact_exists", False)),
                "artifact_bytes": _safe_int(artifact_receipt.get("artifact_bytes", 0)),
                "artifact_sha256": str(artifact_receipt.get("artifact_sha256", "") or ""),
                "sha256_receipt_status": (
                    "observed_existing_artifact"
                    if artifact_receipt.get("artifact_sha256")
                    else "artifact_not_available"
                ),
                "package_member_present": package_member_present,
                "package_member_status": (
                    "packaged"
                    if package_member_present
                    else ("missing_package_member" if package_exists else "package_missing")
                ),
            }
        )

    missing_members = [
        str(row["package_member"])
        for row in artifact_rows
        if not bool(row.get("package_member_present", False))
    ]
    missing_artifacts = [
        str(row["artifact_name"])
        for row in artifact_rows
        if not bool(row.get("artifact_exists", False))
    ]
    if not package_href:
        status = "not_packaged"
    elif not package_exists:
        status = "package_missing"
    elif missing_members:
        status = "missing_package_member"
    elif missing_artifacts:
        status = "missing_artifact"
    else:
        status = "packaged"

    return {
        "contract_version": PROJECT_PACKAGE_MEMBERSHIP_CONTRACT_VERSION,
        "project_package_href": package_href,
        "project_package_path": str(package_path or ""),
        "package_exists": package_exists,
        "package_bytes": _safe_int(package_receipt.get("artifact_bytes", 0)),
        "package_sha256": str(package_receipt.get("artifact_sha256", "") or ""),
        "package_membership_status": status,
        "package_ready": status == "packaged",
        "required_member_count": len(PROJECT_PACKAGE_REQUIRED_MEMBERS),
        "present_member_count": len(PROJECT_PACKAGE_REQUIRED_MEMBERS) - len(missing_members),
        "missing_package_member_count": len(missing_members),
        "missing_package_members": missing_members,
        "missing_artifact_count": len(missing_artifacts),
        "missing_artifacts": missing_artifacts,
        "explicit_status_labels": [
            "stale package",
            "missing package member",
            "hash mismatch",
            "not packaged",
        ],
        "artifact_rows": artifact_rows,
        "sha256_receipt_scope": (
            "observed files at contract build time; generated JSON self-hashes are finalized by the package manifest"
        ),
    }


def _build_archive_handoff_contract(payload: dict[str, Any]) -> dict[str, Any]:
    hrefs = {
        "optimized_review_html_href": str(
            payload.get("optimized_review_html_href") or payload.get("internal_review_href") or ""
        ),
        "expert_review_html_href": str(
            payload.get("expert_review_html_href") or payload.get("expert_review_href") or ""
        ),
        "review_summary_json_href": str(payload.get("review_summary_json_href", "") or ""),
        "expert_metadata_json_href": str(
            payload.get("expert_metadata_json_href") or payload.get("expert_review_metadata_json_href") or ""
        ),
        "project_registry_href": str(payload.get("project_registry_href", "") or ""),
        "project_package_zip_href": str(payload.get("project_package_zip_href") or payload.get("project_package_href") or ""),
        "project_registry_signature_href": str(payload.get("project_registry_signature_href", "") or ""),
        "mgt_export_report_href": str(payload.get("mgt_export_report_href", "") or ""),
        "mgt_source_mgt_href": str(payload.get("mgt_source_mgt_href", "") or ""),
        "mgt_optimized_mgt_href": str(payload.get("mgt_optimized_mgt_href") or payload.get("mgt_output_mgt_href") or ""),
        "mgt_loadcomb_roundtrip_report_href": str(payload.get("mgt_loadcomb_roundtrip_report_href", "") or ""),
        "midas_roundtrip_gate_report_href": str(payload.get("midas_roundtrip_gate_report_href", "") or ""),
    }
    hrefs = {key: value for key, value in hrefs.items() if value.strip()}
    base_dir = Path(str(payload.get("archive_handoff_base_dir") or "."))
    package_membership_contract = _build_project_package_membership_contract(hrefs, base_dir=base_dir)
    validation = _build_artifact_href_validation(
        hrefs,
        base_dir=base_dir,
        required_keys=ARCHIVE_HANDOFF_REQUIRED_HREF_KEYS,
        generated_keys={"review_summary_json_href", "expert_metadata_json_href"},
    )
    validation_summary = _compact_artifact_href_validation(validation)
    return {
        "contract_version": ARCHIVE_HANDOFF_CONTRACT_VERSION,
        "pass": bool(validation_summary.get("pass", False)),
        "hrefs": hrefs,
        "required_href_keys": sorted(ARCHIVE_HANDOFF_REQUIRED_HREF_KEYS),
        "optional_href_keys": sorted(ARCHIVE_HANDOFF_OPTIONAL_HREF_KEYS),
        "artifact_href_validation_summary": validation_summary,
        "project_package_membership_contract": package_membership_contract,
    }


def _expert_review_issue_fields(payload: dict[str, Any]) -> dict[str, str]:
    metadata = payload.get("expert_review_metadata") if isinstance(payload.get("expert_review_metadata"), dict) else {}

    def _meta_text(*keys: str, default: str = "") -> str:
        for key in keys:
            value = metadata.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return str(default)

    case_id_raw = str(payload.get("case_id", "") or "optimized_drawing_review")
    case_title_raw = str(payload.get("case_title", "") or "Optimized Drawing Expert Review")
    status_label_raw = str(payload.get("status_label", "") or "baseline + optimized overlay")
    authority_name_raw = _meta_text(
        "authority_name",
        "jurisdiction_name",
        "authority_label",
        "jurisdiction",
        default="Authority of record",
    )
    return {
        "project_name": _meta_text("project_name", "project_title", default=case_title_raw),
        "project_number": _meta_text("project_number", "project_id", "job_number", default=case_id_raw.upper()),
        "client_name": _meta_text("client_name", "owner_name", default="Client not provided"),
        "site_name": _meta_text("site_name", "site_label", "project_site", default="Site not provided"),
        "authority_name": authority_name_raw,
        "permit_label": _meta_text("permit_label", "permit_review_label", default="Permit review"),
        "committee_label": _meta_text("committee_label", "committee_review_label", default="Committee review"),
        "package_purpose_label": _meta_text(
            "package_purpose_label",
            "submission_purpose",
            "package_label",
            "issue_purpose",
            "committee_package_label",
            default="Jurisdictional Structural Review Package",
        ),
        "issue_phase_label": _meta_text(
            "issue_phase_label",
            "issue_stage_label",
            "submission_track_label",
            "permit_track_label",
            default=status_label_raw,
        ),
        "issue_date": _format_generated_date(
            _meta_text(
                "issue_date",
                "submission_date",
                "permit_issue_date",
                default=str(payload.get("generated_at", "") or ""),
            )
        ),
        "issue_id": _meta_text(
            "package_id",
            "issue_id",
            default=f"EXP-{_safe_slug(case_id_raw).replace('-', '_').upper()}",
        ),
        "revision_code": _meta_text("revision_code", default="REV-00"),
        "revision_status": _meta_text("revision_status", default="Issued for external review"),
        "discipline": _meta_text("discipline", "discipline_label", default="Structural Optimization Review"),
        "prepared_by": _meta_text(
            "prepared_by",
            "prepared_by_label",
            default="AI Structural Optimization Review Tool",
        ),
        "reviewed_by": _meta_text("reviewed_by", "reviewed_by_label", default="Reviewer to sign"),
        "sheet_size": _meta_text("sheet_size", default="A3 landscape"),
        "company_name": _meta_text("company_name", default="AI Structural Optimization Review"),
        "code_basis": _meta_text(
            "code_basis",
            default="KDS / project criteria to be confirmed by reviewer",
        ),
        "review_route_note": _meta_text(
            "review_route_note",
            default="Machine-verifiable checks are prefilled; reviewer confirmation lines remain open for sign-off.",
        ),
        "checklist_head_label": _meta_text("checklist_head_label", default="Jurisdiction checklist"),
        "checklist_title": _meta_text("checklist_title", default=f"{authority_name_raw} issue checklist"),
        "signoff_head_label": _meta_text("signoff_head_label", default="Authority disposition"),
        "signoff_title": _meta_text("signoff_title", default=f"{authority_name_raw} disposition block"),
        "reviewer_office_label": _meta_text(
            "reviewer_label",
            "reviewer_office_label",
            default="Authority reviewer / office",
        ),
        "disposition_label": _meta_text("disposition_label", default="Disposition / permit status"),
        "comments_label": _meta_text("comments_label", default="Comments / conditions"),
        "signature_label": _meta_text("signature_label", default="Signature / date"),
    }


def _expert_review_validation_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    mgt_export_supported_change_count = _safe_int(payload.get("mgt_export_supported_change_count", 0))
    mgt_export_total_change_count = _safe_int(payload.get("mgt_export_total_change_count", 0))
    mgt_export_direct_patch_change_count = _safe_int(payload.get("mgt_export_direct_patch_change_count", 0))
    mgt_export_instruction_sidecar_zero_touch_verified_change_count = _safe_int(
        payload.get("mgt_export_instruction_sidecar_zero_touch_verified_change_count", 0)
    )
    mgt_export_unsupported_change_count = _safe_int(payload.get("mgt_export_unsupported_change_count", 0))
    mgt_export_loadcomb_combo_count = _safe_int(payload.get("mgt_export_loadcomb_combo_count", 0))
    midas_roundtrip_gate_ready_count = _safe_int(payload.get("midas_roundtrip_gate_ready_count", 0))
    midas_roundtrip_gate_corpus_case_count = _safe_int(payload.get("midas_roundtrip_gate_corpus_case_count", 0))
    midas_roundtrip_gate_public_native_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_native_ready_count", 0)
    )
    midas_roundtrip_gate_public_source_ready_count = _safe_int(
        payload.get("midas_roundtrip_gate_public_source_ready_count", 0)
    )
    midas_roundtrip_gate_taxonomy_exact_count = _safe_int(payload.get("midas_roundtrip_gate_taxonomy_exact_count", 0))
    midas_roundtrip_gate_taxonomy_canonical_count = _safe_int(
        payload.get("midas_roundtrip_gate_taxonomy_canonical_count", 0)
    )
    return [
        {
            "label": "MIDAS native export",
            "value": "verified"
            if payload.get("mgt_export_contract_pass") and payload.get("mgt_export_output_mgt_exists")
            else "check",
            "note": "Optimized .mgt package was emitted from the current optimization run and kept inside the supported native-authoring boundary.",
        },
        {
            "label": "Load combination roundtrip",
            "value": "exact" if payload.get("mgt_export_loadcomb_roundtrip_pass") else "review",
            "note": f"Load combination editor seed and roundtrip receipt remain aligned across {mgt_export_loadcomb_combo_count} combinations.",
        },
        {
            "label": "Supported scope",
            "value": f"{mgt_export_supported_change_count}/{mgt_export_total_change_count or max(mgt_export_supported_change_count, 1)}",
            "note": (
                f"Direct patch {mgt_export_direct_patch_change_count}, zero-touch verified "
                f"{mgt_export_instruction_sidecar_zero_touch_verified_change_count}, unsupported "
                f"{mgt_export_unsupported_change_count}."
            ),
        },
        {
            "label": "Review queue",
            "value": str(_safe_int(payload.get("mgt_export_audit_review_queue_pending_count", 0))),
            "note": "Pending audit items remained at zero in this package, so the current surface is suitable for external engineering review rather than internal triage only.",
        },
        {
            "label": "Roundtrip breadth",
            "value": f"{midas_roundtrip_gate_ready_count}/{midas_roundtrip_gate_corpus_case_count or max(midas_roundtrip_gate_ready_count, 1)} ready",
            "note": (
                f"Public native-ready {midas_roundtrip_gate_public_native_ready_count}, public source-ready "
                f"{midas_roundtrip_gate_public_source_ready_count}, taxonomy exact {midas_roundtrip_gate_taxonomy_exact_count}, "
                f"canonical {midas_roundtrip_gate_taxonomy_canonical_count}."
            ),
        },
        {
            "label": "Source vs optimized diff",
            "value": str(_safe_int(payload.get("mgt_compare_window_row_count", 0))),
            "note": "A widened MIDAS compare window is available for exact member jump and line-by-line review inside the technical workspace.",
        },
    ]


def _expert_review_checklist_rows(payload: dict[str, Any], issue_fields: dict[str, str]) -> list[dict[str, Any]]:
    authority_name_raw = issue_fields.get("authority_name", "Authority of record")
    permit_label_raw = issue_fields.get("permit_label", "Permit review")
    committee_label_raw = issue_fields.get("committee_label", "Committee review")
    return [
        {
            "label": "Optimized .mgt attached to submission set",
            "checked": bool(payload.get("mgt_export_output_mgt_exists", False)),
            "note": "Optimized MIDAS file is available as part of the linked evidence bundle.",
        },
        {
            "label": "LOADCOMB roundtrip remains exact",
            "checked": bool(payload.get("mgt_export_loadcomb_roundtrip_pass", False)),
            "note": "Load combination editor seed stayed aligned with the exported package.",
        },
        {
            "label": "Unsupported change count remains zero",
            "checked": _safe_int(payload.get("mgt_export_unsupported_change_count", 0)) == 0,
            "note": "No unsupported write-back actions were reported in this package.",
        },
        {
            "label": "Pending review queue remains zero",
            "checked": _safe_int(payload.get("midas_roundtrip_gate_pending_review_total", 0)) == 0,
            "note": "Current package does not carry unresolved audit queue items.",
        },
        {
            "label": "Story-band schedule checked for governing stories",
            "checked": False,
            "note": f"{authority_name_raw} reviewer to confirm that the controlling story bands were reviewed against office criteria.",
        },
        {
            "label": "Representative member callouts checked",
            "checked": False,
            "note": "Reviewer to confirm that representative before/after member notes are acceptable for issue.",
        },
        {
            "label": f"{permit_label_raw} / {committee_label_raw} remarks appended",
            "checked": False,
            "note": f"Use this line for {authority_name_raw} conditions, caveats, or submission notes.",
        },
        {
            "label": "Final authority disposition ready after reviewer comments",
            "checked": False,
            "note": "Mark after manual comment resolution and issue approval.",
        },
    ]


def _interactive_3d_geometry_contract(interactive_3d_payload: dict[str, Any]) -> dict[str, Any]:
    validation = (
        interactive_3d_payload.get("coordinate_contract_validation")
        if isinstance(interactive_3d_payload.get("coordinate_contract_validation"), dict)
        else {}
    )
    return {
        "coordinate_contract_version": str(interactive_3d_payload.get("coordinate_contract_version", "") or ""),
        "valid_geometry_available": bool(interactive_3d_payload.get("valid_geometry_available", False)),
        "no_valid_geometry": bool(interactive_3d_payload.get("no_valid_geometry", False)),
        "geometry_status": str(interactive_3d_payload.get("geometry_status", "") or ""),
        "valid_point_count": _safe_int(interactive_3d_payload.get("valid_point_count", 0)),
        "valid_segment_count": _safe_int(interactive_3d_payload.get("valid_segment_count", 0)),
        "invalid_excluded_count": _safe_int(interactive_3d_payload.get("invalid_excluded_count", 0)),
        "extent_source": str(interactive_3d_payload.get("extent_source", "") or ""),
        "extent_status": str(interactive_3d_payload.get("extent_status", "") or ""),
        "axis_ref_source_mode": str(interactive_3d_payload.get("axis_ref_source_mode", "") or ""),
        "coordinate_contract_valid": bool(validation.get("coordinate_contract_valid", False)),
    }


def _build_export_handoff_contracts(payload: dict[str, Any]) -> dict[str, Any]:
    interactive_3d_payload = payload.get("interactive_3d_payload") if isinstance(payload.get("interactive_3d_payload"), dict) else {}
    selection_features = dict(
        interactive_3d_payload.get("workspace_selection_contract_features") or WORKSPACE_SELECTION_CONTRACT_FEATURES
    )
    raw_member_indices = {
        str(key): [int(value) for value in values]
        for key, values in (payload.get("mgt_export_source_output_mgt_diff_member_row_indices") or {}).items()
        if str(key).strip()
    }
    window_member_indices = {
        str(key): [int(value) for value in values]
        for key, values in (
            payload.get("mgt_compare_window_member_row_indices")
            or payload.get("mgt_export_source_output_mgt_diff_window_member_row_indices")
            or {}
        ).items()
        if str(key).strip()
    }
    member_indices = raw_member_indices or window_member_indices
    raw_diff_contract = {
        "source_output_diff_json_href": str(payload.get("mgt_source_output_diff_json_href", "") or ""),
        "source_output_diff_txt_href": str(payload.get("mgt_source_output_diff_preview_href", "") or ""),
        "source_output_diff_window_json_href": str(payload.get("mgt_source_output_diff_window_json_href", "") or ""),
        "source_output_diff_window_txt_href": str(payload.get("mgt_source_output_diff_window_preview_href", "") or ""),
        "source_output_diff_json_available": bool(payload.get("mgt_export_source_output_mgt_diff_json_exists", False)),
        "source_output_diff_txt_available": bool(payload.get("mgt_export_source_output_mgt_diff_preview_exists", False)),
        "source_output_diff_window_json_available": bool(
            payload.get("mgt_export_source_output_mgt_diff_window_json_exists", False)
        ),
        "source_output_diff_window_txt_available": bool(
            payload.get("mgt_export_source_output_mgt_diff_window_preview_exists", False)
        ),
        "changed_line_count": _safe_int(payload.get("mgt_export_source_output_mgt_changed_line_count", 0)),
        "added_line_count": _safe_int(payload.get("mgt_export_source_output_mgt_added_line_count", 0)),
        "removed_line_count": _safe_int(payload.get("mgt_export_source_output_mgt_removed_line_count", 0)),
        "total_delta_count": _safe_int(payload.get("mgt_export_source_output_mgt_total_delta_count", 0)),
        "member_row_indices_available": bool(member_indices),
        "member_row_indices": member_indices,
        "window_member_row_indices_available": bool(window_member_indices),
        "window_member_row_indices": window_member_indices,
    }
    return {
        "interactive_3d_geometry_contract": _interactive_3d_geometry_contract(interactive_3d_payload),
        "archive_handoff_contract": _build_archive_handoff_contract(payload),
        "workspace_selection_contract": {
            "selection_contract_version": str(
                interactive_3d_payload.get("workspace_selection_contract_version", "")
                or WORKSPACE_SELECTION_CONTRACT_VERSION
            ),
            "feature_flags": selection_features,
            "canonical_param_names": list(CANONICAL_WORKSPACE_SELECTION_PARAMS),
        },
        "workspace_diff_focus_contract": {
            "diff_focus_contract_version": str(
                interactive_3d_payload.get("workspace_diff_focus_contract_version", "")
                or WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION
            ),
            "member_scoped_focus": bool(selection_features.get("member_diff_focus", False)),
            "non_member_clear_semantics": bool(selection_features.get("non_member_diff_clear", False)),
            "member_row_indices_available": bool(member_indices),
        },
        "raw_diff_artifact_contract": raw_diff_contract,
    }


def build_expert_review_metadata_payload(
    payload: dict[str, Any],
    *,
    out_html: Path,
    out_expert_html: Path,
    out_summary: Path,
    out_expert_metadata_json: Path,
) -> dict[str, Any]:
    issue_fields = _expert_review_issue_fields(payload)
    validation_rows = _expert_review_validation_rows(payload)
    checklist_rows = _expert_review_checklist_rows(payload, issue_fields)
    interactive_3d_payload = payload.get("interactive_3d_payload") if isinstance(payload.get("interactive_3d_payload"), dict) else {}
    interactive_3d_geometry_contract = _interactive_3d_geometry_contract(interactive_3d_payload)
    after_segments_by_member_id = {
        str(row.get("member_id", "") or "").strip(): row
        for row in (interactive_3d_payload.get("after_segments") or [])
        if isinstance(row, dict) and str(row.get("member_id", "") or "").strip()
    }
    bundle_base_dir = out_expert_metadata_json.parent
    artifact_paths = {
        "optimized_review_html": str(out_html),
        "expert_review_html": str(out_expert_html),
        "review_summary_json": str(out_summary),
        "expert_review_metadata_json": str(out_expert_metadata_json),
        "technical_workspace_html": str(out_html),
        "viewer_html": str(payload.get("viewer_html_href", "") or ""),
        "viewer_core_html": str(payload.get("viewer_core_href", "") or ""),
        "committee_dashboard_html": str(payload.get("committee_dashboard_href", "") or ""),
        "analysis_gallery_html": str(payload.get("analysis_gallery_href", "") or ""),
        "project_registry_report": str(payload.get("project_registry_href", "") or ""),
        "project_package_zip": str(payload.get("project_package_href", "") or ""),
        "project_registry_signature": str(payload.get("project_registry_signature_href", "") or ""),
        "external_benchmark_batch_job_report_json": str(payload.get("batch_job_report_href", "") or ""),
        "mgt_export_report_json": str(payload.get("mgt_export_report_href", "") or ""),
        "mgt_source_file": str(payload.get("mgt_source_mgt_href", "") or ""),
        "mgt_output_file": str(payload.get("mgt_output_mgt_href", "") or ""),
        "mgt_roundtrip_report_json": str(payload.get("mgt_loadcomb_roundtrip_report_href", "") or ""),
        "midas_roundtrip_gate_report_json": str(payload.get("midas_roundtrip_gate_report_href", "") or ""),
        "mgt_source_output_diff_json": str(payload.get("mgt_source_output_diff_json_href", "") or ""),
        "mgt_source_output_diff_txt": str(payload.get("mgt_source_output_diff_preview_href", "") or ""),
        "mgt_source_output_diff_window_json": str(payload.get("mgt_source_output_diff_window_json_href", "") or ""),
        "mgt_source_output_diff_window_txt": str(payload.get("mgt_source_output_diff_window_preview_href", "") or ""),
        "expert_metadata_template_index_json": str(payload.get("expert_review_metadata_template_index_path", "") or ""),
        "expert_metadata_field_spec_json": str(payload.get("expert_review_metadata_field_spec_path", "") or ""),
        "expert_metadata_onboarding_schema_json": str(payload.get("expert_review_metadata_onboarding_schema_path", "") or ""),
        "expert_metadata_onboarding_example_json": str(payload.get("expert_review_metadata_onboarding_example_path", "") or ""),
    }
    artifact_hrefs = {
        key: _review_artifact_href(value, base_dir=bundle_base_dir)
        for key, value in artifact_paths.items()
        if str(value).strip()
    }
    artifact_href_validation = _build_artifact_href_validation(
        artifact_hrefs,
        base_dir=bundle_base_dir,
        required_keys={
            "optimized_review_html",
            "expert_review_html",
            "review_summary_json",
            "technical_workspace_html",
            "mgt_export_report_json",
            "mgt_source_file",
            "mgt_output_file",
            "mgt_roundtrip_report_json",
            "midas_roundtrip_gate_report_json",
            "expert_metadata_template_index_json",
            "expert_metadata_field_spec_json",
            "expert_metadata_onboarding_schema_json",
            "expert_metadata_onboarding_example_json",
        },
        generated_keys={"review_summary_json", "expert_review_metadata_json"},
    )
    representative_members = [
        _representative_member_export_fields(
            row,
            base_href=str(payload.get("viewer_core_href", "") or payload.get("viewer_html_href", "") or ""),
            after_segment=after_segments_by_member_id.get(str(row.get("member_id", "") or "").strip()),
        )
        for row in (payload.get("top_members") or [])
        if isinstance(row, dict)
    ]
    template_record = payload.get("expert_review_metadata_template_record")
    if not isinstance(template_record, dict):
        template_record = {}
    template_set = payload.get("expert_review_metadata_template_set")
    if not isinstance(template_set, dict):
        template_set = {}
    return {
        "schema_version": "optimized_drawing_expert_review.metadata.v1",
        "generated_at": str(payload.get("generated_at", "") or ""),
        "source_viewer_json": str(payload.get("source_viewer_json", "") or ""),
        "issue_metadata_source_mode": str(payload.get("expert_review_metadata_source_mode", "") or ""),
        "issue_metadata_source_path": str(payload.get("expert_review_metadata_path", "") or ""),
        "issue_metadata_template": str(payload.get("expert_review_metadata_template", "") or ""),
        "issue_metadata_template_path": str(payload.get("expert_review_metadata_template_path", "") or ""),
        "issue_metadata_template_dir": str(payload.get("expert_review_metadata_template_dir", "") or ""),
        "issue_metadata_template_index_path": str(payload.get("expert_review_metadata_template_index_path", "") or ""),
        "issue_metadata_onboarding_schema_path": str(payload.get("expert_review_metadata_onboarding_schema_path", "") or ""),
        "issue_metadata_onboarding_example_path": str(payload.get("expert_review_metadata_onboarding_example_path", "") or ""),
        "issue_metadata_field_spec_path": str(payload.get("expert_review_metadata_field_spec_path", "") or ""),
        "issue_metadata_template_selection_receipt": str(
            payload.get("expert_review_metadata_template_selection_receipt", "") or ""
        ),
        "case": {
            "case_id": str(payload.get("case_id", "") or ""),
            "case_title": str(payload.get("case_title", "") or ""),
            "case_note": str(payload.get("case_note", "") or ""),
            "status_label": str(payload.get("status_label", "") or ""),
        },
        "issue_fields": issue_fields,
        "template_selection": {
            "source_mode": str(payload.get("expert_review_metadata_source_mode", "") or ""),
            "selection_receipt": str(payload.get("expert_review_metadata_template_selection_receipt", "") or ""),
            "template_dir": str(payload.get("expert_review_metadata_template_dir", "") or ""),
            "template_index_path": str(payload.get("expert_review_metadata_template_index_path", "") or ""),
            "template_set": template_set,
            "selected_template": str(payload.get("expert_review_metadata_template", "") or ""),
            "selected_template_path": str(payload.get("expert_review_metadata_template_path", "") or ""),
            "selected_template_record": template_record,
        },
        "onboarding_artifacts": {
            "purpose": str(payload.get("expert_review_metadata_onboarding_purpose", "") or ""),
            "sections": list(payload.get("expert_review_metadata_onboarding_sections") or []),
            "template_index_path": str(payload.get("expert_review_metadata_template_index_path", "") or ""),
            "template_index_href": str(payload.get("expert_review_metadata_template_index_href", "") or ""),
            "field_spec_path": str(payload.get("expert_review_metadata_field_spec_path", "") or ""),
            "field_spec_href": str(payload.get("expert_review_metadata_field_spec_href", "") or ""),
            "project_onboarding_schema_path": str(
                payload.get("expert_review_metadata_onboarding_schema_path", "") or ""
            ),
            "project_onboarding_schema_href": str(
                payload.get("expert_review_metadata_onboarding_schema_href", "") or ""
            ),
            "project_onboarding_example_path": str(
                payload.get("expert_review_metadata_onboarding_example_path", "") or ""
            ),
            "project_onboarding_example_href": str(
                payload.get("expert_review_metadata_onboarding_example_href", "") or ""
            ),
        },
        "summary": {
            "changed_group_count": _safe_int(payload.get("changed_group_count", 0)),
            "changed_member_count": _safe_int(payload.get("changed_member_count", 0)),
            "total_element_count": _safe_int(payload.get("total_element_count", 0)),
            "signed_cost_proxy_delta_total": round(_safe_float(payload.get("signed_cost_proxy_delta_total", 0.0)), 3),
            "constructability_delta_total": round(_safe_float(payload.get("constructability_delta_total", 0.0)), 3),
            "max_dcr_after_max": round(_safe_float(payload.get("max_dcr_after_max", 0.0)), 3),
            "mgt_compare_window_row_count": _safe_int(payload.get("mgt_compare_window_row_count", 0)),
            "native_authoring_summary_line": str(payload.get("mgt_export_native_authoring_summary_line", "") or ""),
            "source_vs_output_diff_summary_line": str(payload.get("mgt_export_source_vs_output_diff_summary_line", "") or ""),
            "roundtrip_gate_summary_line": str(payload.get("midas_roundtrip_gate_summary_line", "") or ""),
            "delivery_boundary": str(payload.get("mgt_export_delivery_boundary", "") or ""),
            "precision_mode": str(payload.get("precision_mode", "") or ""),
            "axis_ref_source_mode": str(
                interactive_3d_payload.get("axis_ref_source_mode", "")
            ),
            "interactive_3d_geometry_contract": interactive_3d_geometry_contract,
        },
        "export_handoff_contracts": _build_export_handoff_contracts(payload),
        "artifacts": {
            "paths": artifact_paths,
            "hrefs": artifact_hrefs,
            "href_validation": artifact_href_validation,
        },
        "artifact_href_validation": artifact_href_validation,
        "projection_rows": [
            {
                "projection_key": str(row.get("projection_key", "") or ""),
                "projection_label": str(row.get("projection_label", "") or ""),
                "projection_note": str(row.get("projection_note", "") or ""),
                "baseline_asset_href": str(row.get("baseline_asset_href", "") or ""),
                "overlay_asset_href": str(row.get("overlay_asset_href", "") or ""),
            }
            for row in (payload.get("projection_rows") or [])
            if isinstance(row, dict)
        ],
        "story_schedule_rows": [
            {
                "story_band": str(row.get("story_band", "") or ""),
                "zone_label": str(row.get("zone_label", "") or ""),
                "member_type": str(row.get("member_type", "") or ""),
                "changed_group_count": _safe_int(row.get("changed_group_count", 0)),
                "cost_proxy_delta_sum": round(_safe_float(row.get("cost_proxy_delta_sum", 0.0)), 3),
                "constructability_delta_sum": round(_safe_float(row.get("constructability_delta_sum", 0.0)), 3),
                "max_dcr_after_max": round(_safe_float(row.get("max_dcr_after_max", 0.0)), 3),
                "total_segment_count": _safe_int(row.get("total_segment_count", 0)),
                "renderable_segment_count": _safe_int(row.get("renderable_segment_count", 0)),
                "focusable_segment_count": _safe_int(row.get("focusable_segment_count", 0)),
                "invalid_excluded_count": _safe_int(row.get("invalid_excluded_count", 0)),
                "reviewer_reason": _expert_change_reason(row),
            }
            for row in (payload.get("story_band_rows") or [])
            if isinstance(row, dict)
        ],
        "representative_members": [
            row
            for row in representative_members
        ],
        "representative_evidence_completeness_summary": _representative_evidence_completeness_summary(
            representative_members
        ),
        "validation_rows": validation_rows,
        "reviewer_checklist_items": checklist_rows,
    }


def write_review_artifacts(
    viewer_json_path: Path = DEFAULT_VIEWER_JSON,
    *,
    out_html: Path = DEFAULT_OUT_HTML,
    out_expert_html: Path | None = None,
    expert_metadata_json_path: Path = DEFAULT_EXPERT_METADATA_JSON,
    expert_metadata_template: str = DEFAULT_EXPERT_METADATA_TEMPLATE_NAME,
    expert_metadata_template_dir: Path = DEFAULT_EXPERT_METADATA_TEMPLATE_DIR,
    out_expert_metadata_json: Path | None = None,
    out_summary: Path = DEFAULT_OUT_SUMMARY,
    real_drawing_corpus_report_path: Path | None = DEFAULT_REAL_DRAWING_PRIVATE_CORPUS_REPORT,
    model_optimization_intake_queue_path: Path | None = DEFAULT_MODEL_OPTIMIZATION_INTAKE_QUEUE,
    redacted_manifest_path: Path | None = DEFAULT_REDACTED_MANIFEST,
) -> dict[str, Any]:
    expert_html_path = out_expert_html or out_html.with_name("optimized_drawing_expert_review.html")
    expert_metadata_out_path = out_expert_metadata_json or expert_html_path.with_suffix(".metadata.json")
    payload = prepare_review_payload(
        viewer_json_path=viewer_json_path,
        out_html_path=out_html,
        expert_metadata_json_path=expert_metadata_json_path,
        expert_metadata_template=expert_metadata_template,
        expert_metadata_template_dir=expert_metadata_template_dir,
        real_drawing_corpus_report_path=real_drawing_corpus_report_path,
        model_optimization_intake_queue_path=model_optimization_intake_queue_path,
        redacted_manifest_path=redacted_manifest_path,
    )
    payload["archive_handoff_base_dir"] = str(out_html.parent)
    payload["optimized_review_html_href"] = os.path.relpath(out_html, out_html.parent)
    payload["expert_review_html_href"] = os.path.relpath(expert_html_path, out_html.parent)
    payload["review_summary_json_href"] = os.path.relpath(out_summary, out_html.parent)
    payload["expert_metadata_json_href"] = os.path.relpath(expert_metadata_out_path, out_html.parent)
    payload["expert_review_href"] = os.path.relpath(expert_html_path, out_html.parent)
    payload["internal_review_href"] = os.path.relpath(out_html, expert_html_path.parent)
    payload["expert_pdf_href"] = os.path.relpath(expert_html_path.with_suffix(".pdf"), expert_html_path.parent)
    payload["expert_review_metadata_json_href"] = os.path.relpath(expert_metadata_out_path, out_html.parent)
    _write_text(out_html, render_review_html(payload))
    _write_text(expert_html_path, render_expert_review_html(payload))
    expert_review_metadata_payload = build_expert_review_metadata_payload(
        payload,
        out_html=out_html,
        out_expert_html=expert_html_path,
        out_summary=out_summary,
        out_expert_metadata_json=expert_metadata_out_path,
    )
    _write_text(
        expert_metadata_out_path,
        json.dumps(expert_review_metadata_payload, ensure_ascii=False, indent=2, sort_keys=True),
    )
    summary_payload = {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "member_type_rows",
            "story_band_rows",
            "zone_rows",
            "top_members",
            "projection_rows",
            "mgt_compare_window_rows",
        }
    }
    summary_payload["projection_count"] = len(payload.get("projection_rows") or [])
    summary_payload["projection_keys"] = [str(row.get("projection_key", "") or "") for row in (payload.get("projection_rows") or []) if isinstance(row, dict)]
    summary_payload["top_member_count"] = len(payload.get("top_members") or [])
    summary_payload["member_type_count"] = len(payload.get("member_type_rows") or [])
    summary_payload["story_band_priority_count"] = len(payload.get("story_band_rows") or [])
    summary_payload["zone_priority_count"] = len(payload.get("zone_rows") or [])
    interactive_3d_payload = payload.get("interactive_3d_payload") if isinstance(payload.get("interactive_3d_payload"), dict) else {}
    summary_payload["interactive_3d_payload_contract_version"] = str(
        interactive_3d_payload.get("interactive_3d_payload_contract_version", "") or ""
    )
    summary_payload["interactive_3d_nullable_metric_fields"] = list(
        interactive_3d_payload.get("nullable_metric_fields") or []
    )
    summary_payload["interactive_3d_evidence_field_names"] = list(
        interactive_3d_payload.get("evidence_field_names") or []
    )
    summary_payload["interactive_3d_after_segment_contract_validation"] = (
        interactive_3d_payload.get("after_segment_contract_validation") or {}
    )
    summary_payload["interactive_3d_coordinate_contract_version"] = str(
        interactive_3d_payload.get("coordinate_contract_version", "") or ""
    )
    summary_payload["interactive_3d_coordinate_contract_validation"] = (
        interactive_3d_payload.get("coordinate_contract_validation") or {}
    )
    summary_payload["interactive_3d_valid_geometry_available"] = bool(
        interactive_3d_payload.get("valid_geometry_available", True)
    )
    summary_payload["interactive_3d_no_valid_geometry"] = bool(
        interactive_3d_payload.get("no_valid_geometry", False)
    )
    summary_payload["interactive_3d_geometry_status"] = str(
        interactive_3d_payload.get("geometry_status", "") or ""
    )
    summary_payload["interactive_3d_valid_point_count"] = _safe_int(
        interactive_3d_payload.get("valid_point_count", 0)
    )
    summary_payload["interactive_3d_valid_segment_count"] = _safe_int(
        interactive_3d_payload.get("valid_segment_count", 0)
    )
    summary_payload["interactive_3d_invalid_excluded_count"] = _safe_int(
        interactive_3d_payload.get("invalid_excluded_count", 0)
    )
    summary_payload["interactive_3d_geometry_contract"] = _interactive_3d_geometry_contract(interactive_3d_payload)
    summary_payload["interactive_3d_workspace_selection_contract_version"] = str(
        interactive_3d_payload.get("workspace_selection_contract_version", "") or WORKSPACE_SELECTION_CONTRACT_VERSION
    )
    summary_payload["interactive_3d_workspace_diff_focus_contract_version"] = str(
        interactive_3d_payload.get("workspace_diff_focus_contract_version", "") or WORKSPACE_DIFF_FOCUS_CONTRACT_VERSION
    )
    summary_payload["interactive_3d_workspace_selection_contract_features"] = dict(
        interactive_3d_payload.get("workspace_selection_contract_features") or WORKSPACE_SELECTION_CONTRACT_FEATURES
    )
    summary_payload["story_schedule_rows"] = [
        {
            "story_band": str(row.get("story_band", "") or ""),
            "zone_label": str(row.get("zone_label", "") or ""),
            "member_type": str(row.get("member_type", "") or ""),
            "changed_group_count": _safe_int(row.get("changed_group_count", 0)),
            "cost_proxy_delta_sum": round(_safe_float(row.get("cost_proxy_delta_sum", 0.0)), 3),
            "constructability_delta_sum": round(_safe_float(row.get("constructability_delta_sum", 0.0)), 3),
            "max_dcr_after_max": round(_safe_float(row.get("max_dcr_after_max", 0.0)), 3),
            "total_segment_count": _safe_int(row.get("total_segment_count", 0)),
            "renderable_segment_count": _safe_int(row.get("renderable_segment_count", 0)),
            "focusable_segment_count": _safe_int(row.get("focusable_segment_count", 0)),
            "invalid_excluded_count": _safe_int(row.get("invalid_excluded_count", 0)),
            "reviewer_reason": _expert_change_reason(row),
        }
        for row in (payload.get("story_band_rows") or [])
        if isinstance(row, dict)
    ]
    summary_payload["export_handoff_contracts"] = _build_export_handoff_contracts(summary_payload)
    summary_payload["output_html"] = str(out_html)
    summary_payload["output_expert_html"] = str(expert_html_path)
    summary_payload["output_expert_pdf"] = str(expert_html_path.with_suffix(".pdf"))
    summary_payload["output_expert_metadata_json"] = str(expert_metadata_out_path)
    summary_payload["expert_review_metadata"] = payload.get("expert_review_metadata") or {}
    summary_payload["expert_review_metadata_source_mode"] = str(payload.get("expert_review_metadata_source_mode", "") or "")
    summary_payload["expert_review_metadata_path"] = str(payload.get("expert_review_metadata_path", "") or "")
    summary_payload["expert_review_metadata_template"] = str(payload.get("expert_review_metadata_template", "") or "")
    summary_payload["expert_review_metadata_template_path"] = str(payload.get("expert_review_metadata_template_path", "") or "")
    summary_payload["expert_review_metadata_template_dir"] = str(payload.get("expert_review_metadata_template_dir", "") or "")
    summary_payload["expert_review_metadata_template_index_path"] = str(
        payload.get("expert_review_metadata_template_index_path", "") or ""
    )
    summary_payload["expert_review_metadata_template_index_href"] = str(
        payload.get("expert_review_metadata_template_index_href", "") or ""
    )
    summary_payload["expert_review_metadata_template_set"] = payload.get("expert_review_metadata_template_set") or {}
    summary_payload["expert_review_metadata_template_record"] = payload.get("expert_review_metadata_template_record") or {}
    summary_payload["expert_review_metadata_template_selection_receipt"] = str(
        payload.get("expert_review_metadata_template_selection_receipt", "") or ""
    )
    summary_payload["expert_review_metadata_onboarding_purpose"] = str(
        payload.get("expert_review_metadata_onboarding_purpose", "") or ""
    )
    summary_payload["expert_review_metadata_onboarding_sections"] = list(
        payload.get("expert_review_metadata_onboarding_sections") or []
    )
    summary_payload["expert_review_metadata_onboarding_schema_path"] = str(
        payload.get("expert_review_metadata_onboarding_schema_path", "") or ""
    )
    summary_payload["expert_review_metadata_onboarding_schema_href"] = str(
        payload.get("expert_review_metadata_onboarding_schema_href", "") or ""
    )
    summary_payload["expert_review_metadata_onboarding_example_path"] = str(
        payload.get("expert_review_metadata_onboarding_example_path", "") or ""
    )
    summary_payload["expert_review_metadata_onboarding_example_href"] = str(
        payload.get("expert_review_metadata_onboarding_example_href", "") or ""
    )
    summary_payload["expert_review_metadata_field_spec_path"] = str(
        payload.get("expert_review_metadata_field_spec_path", "") or ""
    )
    summary_payload["expert_review_metadata_field_spec_href"] = str(
        payload.get("expert_review_metadata_field_spec_href", "") or ""
    )
    summary_payload["expert_issue_metadata"] = payload.get("expert_issue_metadata") or {}
    summary_payload["expert_issue_metadata_source_mode"] = str(payload.get("expert_issue_metadata_source_mode", "") or "")
    summary_payload["expert_issue_metadata_path"] = str(payload.get("expert_issue_metadata_path", "") or "")
    summary_payload["expert_review_metadata_json_href"] = str(payload.get("expert_review_metadata_json_href", "") or "")
    summary_href_values = {
        key: value
        for key, value in summary_payload.items()
        if key.endswith("_href") and str(value or "").strip()
    }
    summary_payload["artifact_href_validation"] = _build_artifact_href_validation(
        summary_href_values,
        base_dir=out_html.parent,
        required_keys={
            "expert_review_href",
            "internal_review_href",
            "expert_review_metadata_json_href",
            "mgt_export_report_href",
            "mgt_source_mgt_href",
            "mgt_output_mgt_href",
            "mgt_loadcomb_roundtrip_report_href",
            "mgt_source_output_diff_json_href",
            "mgt_source_output_diff_preview_href",
            "mgt_source_output_diff_window_json_href",
            "mgt_source_output_diff_window_preview_href",
            "mgt_compare_window_json_href",
            "mgt_compare_window_txt_href",
            "midas_roundtrip_gate_report_href",
            "expert_review_metadata_template_index_href",
            "expert_review_metadata_onboarding_schema_href",
            "expert_review_metadata_onboarding_example_href",
            "expert_review_metadata_field_spec_href",
        },
    )
    summary_payload["output_assets_dir"] = str(out_html.parent / "optimized_drawing_review_assets")
    _write_text(out_summary, json.dumps(summary_payload, ensure_ascii=False, indent=2))
    shared_export_handoff_contracts = _build_export_handoff_contracts(summary_payload)
    summary_payload["export_handoff_contracts"] = shared_export_handoff_contracts
    expert_review_metadata_payload["export_handoff_contracts"] = shared_export_handoff_contracts
    _write_text(
        expert_metadata_out_path,
        json.dumps(expert_review_metadata_payload, ensure_ascii=False, indent=2, sort_keys=True),
    )
    _write_text(out_summary, json.dumps(summary_payload, ensure_ascii=False, indent=2))
    archive_hrefs = shared_export_handoff_contracts.get("archive_handoff_contract", {}).get("hrefs", {})
    if isinstance(archive_hrefs, dict):
        package_update_receipt = _upsert_project_package_required_members(
            {str(key): str(value) for key, value in archive_hrefs.items()},
            base_dir=out_html.parent,
        )
        shared_export_handoff_contracts = _build_export_handoff_contracts(summary_payload)
        shared_export_handoff_contracts["archive_handoff_contract"][
            "project_package_update_receipt"
        ] = package_update_receipt
        summary_payload["export_handoff_contracts"] = shared_export_handoff_contracts
        expert_review_metadata_payload["export_handoff_contracts"] = shared_export_handoff_contracts
        _write_text(
            expert_metadata_out_path,
            json.dumps(expert_review_metadata_payload, ensure_ascii=False, indent=2, sort_keys=True),
        )
        _write_text(out_summary, json.dumps(summary_payload, ensure_ascii=False, indent=2))
    return summary_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--viewer-json", default=str(DEFAULT_VIEWER_JSON))
    parser.add_argument("--out-html", default=str(DEFAULT_OUT_HTML))
    parser.add_argument("--out-expert-html", default="")
    parser.add_argument("--expert-metadata-json", default=str(DEFAULT_EXPERT_METADATA_JSON))
    parser.add_argument("--expert-metadata-template", default=DEFAULT_EXPERT_METADATA_TEMPLATE_NAME)
    parser.add_argument("--expert-metadata-template-dir", default=str(DEFAULT_EXPERT_METADATA_TEMPLATE_DIR))
    parser.add_argument("--out-expert-metadata-json", default="")
    parser.add_argument("--out-summary", default=str(DEFAULT_OUT_SUMMARY))
    parser.add_argument("--real-drawing-corpus-report", default=str(DEFAULT_REAL_DRAWING_PRIVATE_CORPUS_REPORT))
    parser.add_argument("--model-optimization-intake-queue", default=str(DEFAULT_MODEL_OPTIMIZATION_INTAKE_QUEUE))
    parser.add_argument("--redacted-manifest", default=str(DEFAULT_REDACTED_MANIFEST))
    args = parser.parse_args()

    def _optional_path(value: str) -> Path | None:
        text = str(value or "").strip()
        return Path(text) if text else None

    write_review_artifacts(
        viewer_json_path=Path(args.viewer_json),
        out_html=Path(args.out_html),
        out_expert_html=Path(args.out_expert_html) if str(args.out_expert_html).strip() else None,
        expert_metadata_json_path=Path(args.expert_metadata_json),
        expert_metadata_template=str(args.expert_metadata_template),
        expert_metadata_template_dir=Path(args.expert_metadata_template_dir),
        out_expert_metadata_json=(
            Path(args.out_expert_metadata_json) if str(args.out_expert_metadata_json).strip() else None
        ),
        out_summary=Path(args.out_summary),
        real_drawing_corpus_report_path=_optional_path(args.real_drawing_corpus_report),
        model_optimization_intake_queue_path=_optional_path(args.model_optimization_intake_queue),
        redacted_manifest_path=_optional_path(args.redacted_manifest),
    )


if __name__ == "__main__":
    main()
