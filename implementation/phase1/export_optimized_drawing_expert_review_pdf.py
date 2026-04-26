from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any
import zipfile

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas


DEFAULT_EXPERT_REVIEW_METADATA_JSON = Path(
    "implementation/phase1/release/visualization/optimized_drawing_expert_review.metadata.json"
)
DEFAULT_BATCH_TEMPLATE_ORDER = (
    "default",
    "seoul_permit_review",
    "structural_peer_committee",
    "international_english",
)
PAGE_SIZE = landscape(A3)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE
PAGE_MARGIN = 14 * mm
PDF_FONT_REGULAR = "ExpertReviewNanum"
PDF_FONT_BOLD = "ExpertReviewNanum-Bold"
PDF_FONT_CANDIDATES = {
    PDF_FONT_REGULAR: [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ],
    PDF_FONT_BOLD: [
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ],
}
PDF_TEMPLATE_PRESETS: dict[str, dict[str, Any]] = {
    "default": {
        "label": "Default expert review package",
        "issue_field_overrides": {},
    },
    "seoul_permit_review": {
        "label": "Seoul permit review package",
        "issue_field_overrides": {
            "authority_name": "Seoul Metropolitan Permit Review Office",
            "permit_label": "Seoul Building Permit Review",
            "committee_label": "Permit coordination track",
            "package_purpose_label": "Seoul Permit Review Package",
            "checklist_head_label": "Permit checklist",
            "checklist_title": "Seoul permit issue checklist",
            "signoff_head_label": "Permit disposition",
            "signoff_title": "Seoul permit disposition block",
            "reviewer_office_label": "Permit reviewer / office",
            "disposition_label": "Permit disposition",
            "comments_label": "Permit comments / conditions",
            "review_route_note": (
                "Use this package for Seoul permit review handoff. "
                "Machine-verifiable checks are prefilled; permit comments remain open for sign-off."
            ),
        },
    },
    "structural_peer_committee": {
        "label": "Structural peer committee review package",
        "issue_field_overrides": {
            "authority_name": "Structural Peer Committee",
            "permit_label": "Permit interface review",
            "committee_label": "Structural peer committee",
            "package_purpose_label": "Structural Peer Committee Review Package",
            "checklist_head_label": "Peer committee checklist",
            "checklist_title": "Structural peer committee issue checklist",
            "signoff_head_label": "Committee disposition",
            "signoff_title": "Structural peer committee disposition block",
            "reviewer_office_label": "Peer reviewer / committee office",
            "disposition_label": "Committee disposition",
            "comments_label": "Committee comments / conditions",
            "review_route_note": (
                "Use this package for external structural peer committee review. "
                "Machine-verifiable checks are prefilled; committee remarks remain open for sign-off."
            ),
        },
    },
    "international_english": {
        "label": "International English expert review package",
        "issue_field_overrides": {
            "authority_name": "International Peer Review Board",
            "permit_label": "Global Code Compliance Review",
            "committee_label": "International Expert Panel",
            "package_purpose_label": "Design Optimization Independent Review",
            "checklist_head_label": "Compliance Verification",
            "checklist_title": "Structural Optimization Verification Checklist",
            "signoff_head_label": "Final Disposition",
            "signoff_title": "Reviewer Disposition & Sign-off",
            "reviewer_office_label": "Independent Reviewer",
            "disposition_label": "Disposition Status",
            "comments_label": "Review Remarks & Conditions",
            "review_route_note": (
                "This document serves as an international standard expert review package. "
                "Machine-verifiable optimization checks are pre-populated. "
                "The independent reviewer is expected to provide final sign-off."
            ),
        },
    },
}
ZIP_FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _pdf_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    if not text:
        return ""
    return text


def _metric_text(value: Any, digits: int = 3) -> str:
    try:
        return f"{float(value):+.{digits}f}"
    except Exception:
        return _pdf_text(value)


def _default_out_pdf(metadata_json_path: Path) -> Path:
    if metadata_json_path.name.endswith(".metadata.json"):
        return metadata_json_path.with_name(metadata_json_path.name[: -len(".metadata.json")] + ".pdf")
    return metadata_json_path.with_suffix(".pdf")


def _default_batch_out_dir(metadata_json_path: Path) -> Path:
    default_pdf = _default_out_pdf(metadata_json_path)
    return default_pdf.parent / f"{default_pdf.stem}_batch"


def _deep_copy_json(value: Any) -> Any:
    return copy.deepcopy(value)


def _resolve_template_names(template_names: list[str] | tuple[str, ...] | None) -> list[str]:
    if not template_names:
        return list(DEFAULT_BATCH_TEMPLATE_ORDER)
    resolved: list[str] = []
    seen: set[str] = set()
    for raw_name in template_names:
        template_name = str(raw_name or "").strip()
        if not template_name or template_name in seen:
            continue
        if template_name not in PDF_TEMPLATE_PRESETS:
            raise ValueError(f"unknown PDF template: {template_name}")
        seen.add(template_name)
        resolved.append(template_name)
    if not resolved:
        raise ValueError("no valid PDF templates were requested")
    return resolved


def _template_pdf_filename(metadata_json_path: Path, template_name: str) -> str:
    base_pdf = _default_out_pdf(metadata_json_path)
    return f"{base_pdf.stem}.{template_name}{base_pdf.suffix}"


def _apply_pdf_template(metadata: dict[str, Any], template_name: str) -> dict[str, Any]:
    template = PDF_TEMPLATE_PRESETS.get(template_name)
    if template is None:
        raise ValueError(f"unknown PDF template: {template_name}")
    materialized = _deep_copy_json(metadata)
    issue_fields = (
        materialized.get("issue_fields")
        if isinstance(materialized.get("issue_fields"), dict)
        else {}
    )
    materialized_issue_fields = dict(issue_fields)
    materialized_issue_fields.update(template.get("issue_field_overrides") or {})
    materialized_issue_fields["pdf_template_name"] = template_name
    materialized_issue_fields["pdf_template_label"] = str(template.get("label", template_name))
    materialized["issue_fields"] = materialized_issue_fields
    materialized["pdf_template_name"] = template_name
    materialized["pdf_template_label"] = str(template.get("label", template_name))
    return materialized


def _manifest_relpath(target: Path, *, base_dir: Path) -> str:
    return os.path.relpath(target, base_dir)


def _resolve_artifact_path(path_text: str, *, metadata_json_path: Path) -> Path:
    candidate = Path(str(path_text or "").strip())
    if not str(candidate):
        raise FileNotFoundError("artifact path was empty")
    if candidate.is_absolute():
        if candidate.exists():
            return candidate
        raise FileNotFoundError(candidate)
    if candidate.exists():
        return candidate.resolve()
    sibling = (metadata_json_path.parent / candidate).resolve()
    if sibling.exists():
        return sibling
    raise FileNotFoundError(candidate)


def _copy_artifact_bytes(source_path: Path, destination_path: Path) -> None:
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_bytes(source_path.read_bytes())


def _template_metadata_filename(metadata_json_path: Path, template_name: str) -> str:
    if metadata_json_path.name.endswith(".metadata.json"):
        return metadata_json_path.name[: -len(".metadata.json")] + f".{template_name}.metadata.json"
    return f"{metadata_json_path.stem}.{template_name}.json"


def _template_zip_filename(metadata_json_path: Path, template_name: str) -> str:
    base_pdf = _default_out_pdf(metadata_json_path)
    return f"{base_pdf.stem}.{template_name}.submission.zip"


def _template_html_filenames(template_name: str) -> tuple[str, str]:
    return (
        f"optimized_drawing_review.{template_name}.html",
        f"optimized_drawing_expert_review.{template_name}.html",
    )


def _materialize_template_metadata(
    metadata: dict[str, Any],
    *,
    template_name: str,
    output_metadata_json: Path,
    output_review_html: Path,
    output_expert_html: Path,
    output_pdf: Path,
    output_zip: Path,
) -> dict[str, Any]:
    materialized = _apply_pdf_template(metadata, template_name)
    artifacts = materialized.get("artifacts") if isinstance(materialized.get("artifacts"), dict) else {}
    artifact_paths = artifacts.get("paths") if isinstance(artifacts.get("paths"), dict) else {}
    artifact_hrefs = artifacts.get("hrefs") if isinstance(artifacts.get("hrefs"), dict) else {}

    updated_paths = dict(artifact_paths)
    updated_paths["optimized_review_html"] = str(output_review_html)
    updated_paths["expert_review_html"] = str(output_expert_html)
    updated_paths["expert_review_metadata_json"] = str(output_metadata_json)
    updated_paths["template_pdf"] = str(output_pdf)
    updated_paths["submission_zip"] = str(output_zip)

    base_dir = output_metadata_json.parent
    updated_hrefs = dict(artifact_hrefs)
    updated_hrefs["optimized_review_html"] = _manifest_relpath(output_review_html, base_dir=base_dir)
    updated_hrefs["expert_review_html"] = _manifest_relpath(output_expert_html, base_dir=base_dir)
    updated_hrefs["expert_review_metadata_json"] = _manifest_relpath(output_metadata_json, base_dir=base_dir)
    updated_hrefs["template_pdf"] = _manifest_relpath(output_pdf, base_dir=base_dir)
    updated_hrefs["submission_zip"] = _manifest_relpath(output_zip, base_dir=base_dir)

    materialized["artifacts"] = {
        **artifacts,
        "paths": updated_paths,
        "hrefs": updated_hrefs,
    }
    materialized["template_submission_bundle"] = {
        "template_name": template_name,
        "output_review_html": str(output_review_html),
        "output_expert_html": str(output_expert_html),
        "output_metadata_json": str(output_metadata_json),
        "output_pdf": str(output_pdf),
        "output_zip": str(output_zip),
    }
    return materialized


def _deterministic_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_deterministic_zip(zip_path: Path, *, entries: list[tuple[str, Path]]) -> list[dict[str, Any]]:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    entry_summaries: list[dict[str, Any]] = []
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for arcname, source_path in entries:
            source_bytes = source_path.read_bytes()
            info = zipfile.ZipInfo(filename=arcname, date_time=ZIP_FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o644 << 16
            archive.writestr(info, source_bytes)
            entry_summaries.append(
                {
                    "arcname": arcname,
                    "source_path": str(source_path),
                    "size_bytes": len(source_bytes),
                    "sha256": hashlib.sha256(source_bytes).hexdigest(),
                }
            )
    return entry_summaries


def _register_pdf_fonts() -> None:
    for font_name, candidates in PDF_FONT_CANDIDATES.items():
        if font_name in pdfmetrics.getRegisteredFontNames():
            continue
        font_path = next((candidate for candidate in candidates if candidate.exists()), None)
        if font_path is None:
            raise FileNotFoundError(f"Unable to locate a font file for {font_name}")
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))


def _draw_wrapped_text(
    canvas: Canvas,
    text: str,
    *,
    x: float,
    y: float,
    max_width: float,
    font_name: str = PDF_FONT_REGULAR,
    font_size: float = 9.0,
    leading: float = 12.0,
    color: colors.Color = colors.black,
) -> float:
    lines = simpleSplit(_pdf_text(text), font_name, font_size, max_width)
    cursor_y = y
    canvas.setFont(font_name, font_size)
    canvas.setFillColor(color)
    for line in lines:
        canvas.drawString(x, cursor_y, line)
        cursor_y -= leading
    return cursor_y


def _draw_header(
    canvas: Canvas,
    *,
    sheet_code: str,
    title: str,
    subtitle: str,
    issue_fields: dict[str, Any],
    page_number: int,
    page_total: int,
) -> float:
    top = PAGE_HEIGHT - PAGE_MARGIN
    canvas.setFillColor(colors.HexColor("#f3f7fa"))
    canvas.roundRect(PAGE_MARGIN, top - 44 * mm, PAGE_WIDTH - (2 * PAGE_MARGIN), 44 * mm, 8 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#17394a"))
    canvas.setFont(PDF_FONT_BOLD, 22)
    canvas.drawString(PAGE_MARGIN + 8 * mm, top - 12 * mm, _pdf_text(title))
    canvas.setFont(PDF_FONT_BOLD, 10)
    canvas.setFillColor(colors.HexColor("#5f7684"))
    canvas.drawString(PAGE_MARGIN + 8 * mm, top - 6 * mm, f"Sheet {sheet_code} / {page_total}")
    canvas.setFillColor(colors.HexColor("#4e6370"))
    _draw_wrapped_text(
        canvas,
        subtitle,
        x=PAGE_MARGIN + 8 * mm,
        y=top - 20 * mm,
        max_width=(PAGE_WIDTH - 2 * PAGE_MARGIN) * 0.62,
        font_size=9.5,
        leading=12,
        color=colors.HexColor("#4e6370"),
    )

    right_x = PAGE_WIDTH - PAGE_MARGIN - 82 * mm
    right_y = top - 8 * mm
    meta_lines = [
        f"Project: {_pdf_text(issue_fields.get('project_name', ''))}",
        f"Project No: {_pdf_text(issue_fields.get('project_number', ''))}",
        f"Issue ID: {_pdf_text(issue_fields.get('issue_id', ''))}",
        f"Issue Date: {_pdf_text(issue_fields.get('issue_date', ''))}",
        f"Revision: {_pdf_text(issue_fields.get('revision_code', ''))} / {_pdf_text(issue_fields.get('revision_status', ''))}",
        f"Authority: {_pdf_text(issue_fields.get('authority_name', ''))}",
    ]
    canvas.setFillColor(colors.HexColor("#17394a"))
    canvas.setFont(PDF_FONT_BOLD, 9)
    for index, line in enumerate(meta_lines):
        canvas.drawString(right_x, right_y - index * 5.5 * mm, line)

    canvas.setFillColor(colors.HexColor("#d8643a"))
    canvas.roundRect(right_x, top - 26 * mm, 34 * mm, 14 * mm, 3 * mm, fill=0, stroke=1)
    canvas.setFont(PDF_FONT_BOLD, 14)
    canvas.drawCentredString(right_x + 17 * mm, top - 18 * mm, _pdf_text(issue_fields.get("revision_code", "REV-00")))
    return top - 50 * mm


def _draw_footer(canvas: Canvas, *, issue_fields: dict[str, Any], page_number: int, page_total: int) -> None:
    footer_y = PAGE_MARGIN - 2 * mm
    canvas.setStrokeColor(colors.HexColor("#b4c0c8"))
    canvas.line(PAGE_MARGIN, footer_y + 7 * mm, PAGE_WIDTH - PAGE_MARGIN, footer_y + 7 * mm)
    canvas.setFont(PDF_FONT_REGULAR, 8.5)
    canvas.setFillColor(colors.HexColor("#526874"))
    footer_left = (
        f"{_pdf_text(issue_fields.get('company_name', 'AI Structural Optimization Review'))} | "
        f"{_pdf_text(issue_fields.get('package_purpose_label', 'Expert Review Package'))}"
    )
    canvas.drawString(PAGE_MARGIN, footer_y + 2 * mm, footer_left)
    canvas.drawRightString(
        PAGE_WIDTH - PAGE_MARGIN,
        footer_y + 2 * mm,
        f"Page {page_number} / {page_total}",
    )


def _draw_metric_cards(canvas: Canvas, *, x: float, y: float, width: float, metrics: list[tuple[str, str, str]]) -> float:
    columns = 3
    gap = 5 * mm
    card_width = (width - gap * (columns - 1)) / columns
    card_height = 28 * mm
    for index, (label, value, note) in enumerate(metrics):
        row = index // columns
        col = index % columns
        card_x = x + col * (card_width + gap)
        card_y = y - row * (card_height + gap)
        canvas.setFillColor(colors.HexColor("#fbfcfe"))
        canvas.setStrokeColor(colors.HexColor("#c4d0d8"))
        canvas.roundRect(card_x, card_y - card_height, card_width, card_height, 3 * mm, fill=1, stroke=1)
        canvas.setFillColor(colors.HexColor("#6c818d"))
        canvas.setFont(PDF_FONT_BOLD, 8.5)
        canvas.drawString(card_x + 4 * mm, card_y - 5 * mm, _pdf_text(label))
        canvas.setFillColor(colors.HexColor("#17394a"))
        canvas.setFont(PDF_FONT_BOLD, 14)
        canvas.drawString(card_x + 4 * mm, card_y - 12 * mm, _pdf_text(value))
        _draw_wrapped_text(
            canvas,
            note,
            x=card_x + 4 * mm,
            y=card_y - 17 * mm,
            max_width=card_width - 8 * mm,
            font_size=8.2,
            leading=10.0,
            color=colors.HexColor("#4f6471"),
        )
    rows = (len(metrics) + columns - 1) // columns
    return y - rows * card_height - max(0, rows - 1) * gap


def _draw_table(
    canvas: Canvas,
    *,
    x: float,
    y: float,
    width: float,
    columns: list[tuple[str, str, float]],
    rows: list[dict[str, Any]],
    title: str,
    subtitle: str = "",
    max_rows: int | None = None,
) -> float:
    canvas.setFillColor(colors.HexColor("#17394a"))
    canvas.setFont(PDF_FONT_BOLD, 11)
    canvas.drawString(x, y, _pdf_text(title))
    cursor_y = y - 5 * mm
    if subtitle:
        cursor_y = _draw_wrapped_text(
            canvas,
            subtitle,
            x=x,
            y=cursor_y,
            max_width=width,
            font_size=8.5,
            leading=10.5,
            color=colors.HexColor("#617784"),
        )
        cursor_y -= 2 * mm

    selected_rows = rows[:max_rows] if max_rows else rows
    header_height = 9 * mm
    column_widths = [width * fraction for _, _, fraction in columns]
    row_top = cursor_y
    canvas.setFillColor(colors.HexColor("#eef3f7"))
    canvas.rect(x, row_top - header_height, width, header_height, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor("#c5d0d8"))
    canvas.rect(x, row_top - header_height, width, header_height, fill=0, stroke=1)
    current_x = x
    canvas.setFont(PDF_FONT_BOLD, 8.5)
    canvas.setFillColor(colors.HexColor("#516774"))
    for (label, _, _), col_width in zip(columns, column_widths):
        canvas.drawString(current_x + 2.5 * mm, row_top - 6.2 * mm, _pdf_text(label))
        current_x += col_width

    cursor_y = row_top - header_height
    for row in selected_rows:
        cell_lines: list[list[str]] = []
        row_height = 0.0
        for (_, key, _), col_width in zip(columns, column_widths):
            value = row.get(key, "")
            text = _pdf_text(value)
            lines = simpleSplit(text, PDF_FONT_REGULAR, 8.3, max(col_width - 5 * mm, 20))
            if not lines:
                lines = [""]
            cell_lines.append(lines)
            row_height = max(row_height, len(lines) * 9.5 + 4)
        cursor_y -= row_height
        canvas.setStrokeColor(colors.HexColor("#d3dbe1"))
        canvas.rect(x, cursor_y, width, row_height, fill=0, stroke=1)
        current_x = x
        for lines, col_width in zip(cell_lines, column_widths):
            text_y = cursor_y + row_height - 7
            canvas.setFont(PDF_FONT_REGULAR, 8.3)
            canvas.setFillColor(colors.HexColor("#203b4a"))
            for line in lines:
                canvas.drawString(current_x + 2.5 * mm, text_y, line)
                text_y -= 9.5
            current_x += col_width
            canvas.line(current_x, cursor_y, current_x, cursor_y + row_height)
    return cursor_y


def export_expert_review_pdf(
    expert_review_metadata_json: Path = DEFAULT_EXPERT_REVIEW_METADATA_JSON,
    *,
    out_pdf: Path | None = None,
    template_name: str = "default",
) -> dict[str, Any]:
    _register_pdf_fonts()
    raw_metadata = _load_json(expert_review_metadata_json)
    if not raw_metadata:
        raise ValueError(f"expert review metadata JSON not found or invalid: {expert_review_metadata_json}")
    metadata = _apply_pdf_template(raw_metadata, template_name)

    issue_fields = metadata.get("issue_fields") if isinstance(metadata.get("issue_fields"), dict) else {}
    summary = metadata.get("summary") if isinstance(metadata.get("summary"), dict) else {}
    case = metadata.get("case") if isinstance(metadata.get("case"), dict) else {}
    projection_rows = [row for row in (metadata.get("projection_rows") or []) if isinstance(row, dict)]
    story_rows = [row for row in (metadata.get("story_schedule_rows") or []) if isinstance(row, dict)]
    member_rows = [row for row in (metadata.get("representative_members") or []) if isinstance(row, dict)]
    validation_rows = [row for row in (metadata.get("validation_rows") or []) if isinstance(row, dict)]
    checklist_rows = [row for row in (metadata.get("reviewer_checklist_items") or []) if isinstance(row, dict)]
    artifact_hrefs = (
        (metadata.get("artifacts") or {}).get("hrefs")
        if isinstance((metadata.get("artifacts") or {}).get("hrefs"), dict)
        else {}
    )

    pdf_path = out_pdf or _default_out_pdf(expert_review_metadata_json)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    canvas = Canvas(str(pdf_path), pagesize=PAGE_SIZE, pageCompression=0, invariant=1)
    canvas.setTitle(_pdf_text(issue_fields.get("project_name", "Optimized Drawing Expert Review")))
    canvas.setAuthor(_pdf_text(issue_fields.get("prepared_by", "AI Structural Optimization Review Tool")))
    canvas.setCreator("optimized_drawing_expert_review_pdf_exporter")
    canvas.setSubject(
        _pdf_text(
            issue_fields.get(
                "package_purpose_label",
                metadata.get("pdf_template_label", "External Expert Review Package"),
            )
        )
    )
    canvas.setKeywords(
        f"optimized-drawing, expert-review, deterministic-pdf, template={_pdf_text(template_name)}"
    )

    page_total = 4
    native_export_state = "CHECK"
    if validation_rows:
        native_export_state = "VERIFIED" if str(validation_rows[0].get("value", "")).lower() == "verified" else "CHECK"

    y = _draw_header(
        canvas,
        sheet_code="E-01",
        title="Executive Review Sheet",
        subtitle="Decision-ready summary of the optimized structural package, kept in expert review language and stable enough for repeat PDF export.",
        issue_fields=issue_fields,
        page_number=1,
        page_total=page_total,
    )
    metrics = [
        ("Optimization scope", f"{summary.get('changed_group_count', 0)} groups / {summary.get('changed_member_count', 0)} members", "Changed groups and representative members carried into the review package."),
        ("Quantity / cost proxy", _metric_text(summary.get("signed_cost_proxy_delta_total", 0.0)), "Signed total reduction proxy across the optimized structural package."),
        ("Constructability delta", _metric_text(summary.get("constructability_delta_total", 0.0)), "Negative values indicate simplification or lighter detailing burden in this package."),
        ("Governing D/C after", f"{float(summary.get('max_dcr_after_max', 0.0) or 0.0):.3f}", "Maximum reported demand/capacity ratio after optimization, retained below unity."),
        ("Native MIDAS export", native_export_state, "Optimized .mgt status captured from the current export receipt."),
        ("Review route", _pdf_text(issue_fields.get("authority_name", "Authority of record")), _pdf_text(issue_fields.get("review_route_note", ""))),
    ]
    y = _draw_metric_cards(canvas, x=PAGE_MARGIN, y=y, width=PAGE_WIDTH - 2 * PAGE_MARGIN, metrics=metrics) - 8 * mm
    y = _draw_wrapped_text(
        canvas,
        case.get("case_note") or "The current package compares the baseline structural model against the optimized structural revision and focuses on decision-ready review output.",
        x=PAGE_MARGIN,
        y=y,
        max_width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        font_size=10,
        leading=13,
        color=colors.HexColor("#2f4757"),
    )
    y -= 8 * mm
    handoff_text = (
        f"Technical workspace: {_pdf_text(artifact_hrefs.get('technical_workspace_html', 'not linked'))} | "
        f"Optimized .mgt: {_pdf_text(artifact_hrefs.get('mgt_output_file', 'not linked'))} | "
        f"Export report: {_pdf_text(artifact_hrefs.get('mgt_export_report_json', 'not linked'))} | "
        f"Project registry: {_pdf_text(artifact_hrefs.get('project_registry_report', 'not linked'))} | "
        f"Project package: {_pdf_text(artifact_hrefs.get('project_package_zip', 'not linked'))}"
    )
    _draw_wrapped_text(
        canvas,
        handoff_text,
        x=PAGE_MARGIN,
        y=y,
        max_width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        font_size=8.7,
        leading=11,
        color=colors.HexColor("#556b77"),
    )
    _draw_footer(canvas, issue_fields=issue_fields, page_number=1, page_total=page_total)
    canvas.showPage()

    y = _draw_header(
        canvas,
        sheet_code="E-02",
        title="Drawing Review Sheets",
        subtitle="Projection summary plus the story-band schedule used for expert review and committee-oriented package scanning.",
        issue_fields=issue_fields,
        page_number=2,
        page_total=page_total,
    )
    projection_table_rows = [
        {
            "projection_label": row.get("projection_label", ""),
            "projection_note": row.get("projection_note", ""),
            "asset_ref": row.get("overlay_asset_href", "") or row.get("baseline_asset_href", ""),
        }
        for row in projection_rows
    ]
    y = _draw_table(
        canvas,
        x=PAGE_MARGIN,
        y=y,
        width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        columns=[
            ("Projection", "projection_label", 0.16),
            ("Review note", "projection_note", 0.54),
            ("Asset ref", "asset_ref", 0.30),
        ],
        rows=projection_table_rows,
        title="Projection package",
        subtitle="This PDF stays deterministic and table-first; asset refs point back to the HTML/linked surface when a reviewer wants the visual sheet.",
        max_rows=3,
    ) - 8 * mm
    _draw_table(
        canvas,
        x=PAGE_MARGIN,
        y=y,
        width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        columns=[
            ("Story", "story_band", 0.11),
            ("Zone", "zone_label", 0.13),
            ("Member", "member_type", 0.12),
            ("Groups", "changed_group_count", 0.08),
            ("Cost delta", "cost_proxy_delta_sum", 0.12),
            ("Construct.", "constructability_delta_sum", 0.10),
            ("D/C after", "max_dcr_after_max", 0.10),
            ("Reviewer reason", "reviewer_reason", 0.24),
        ],
        rows=story_rows,
        title="Story-band revision schedule",
        subtitle="The same prioritized story rows are used here as in the browser package, so review order stays consistent across surfaces.",
        max_rows=12,
    )
    _draw_footer(canvas, issue_fields=issue_fields, page_number=2, page_total=page_total)
    canvas.showPage()

    y = _draw_header(
        canvas,
        sheet_code="E-03",
        title="Why Changed / Representative Callouts",
        subtitle="Representative changed members pulled from the optimized drawing package for expert-facing callout review.",
        issue_fields=issue_fields,
        page_number=3,
        page_total=page_total,
    )
    _draw_table(
        canvas,
        x=PAGE_MARGIN,
        y=y,
        width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        columns=[
            ("Member", "member_id", 0.12),
            ("Type", "member_type", 0.10),
            ("Story", "story_band_label", 0.10),
            ("Zone", "zone_label", 0.11),
            ("Action", "action_name_label", 0.15),
            ("Cost delta", "cost_delta", 0.10),
            ("Construct.", "constructability_delta", 0.10),
            ("Callout", "before_after_snapshot_note", 0.22),
        ],
        rows=member_rows,
        title="Representative changed members",
        subtitle="Prioritized members are listed with before/after callouts and the same focus route carried by the HTML review package.",
        max_rows=12,
    )
    _draw_footer(canvas, issue_fields=issue_fields, page_number=3, page_total=page_total)
    canvas.showPage()

    y = _draw_header(
        canvas,
        sheet_code="E-04",
        title="Validation Receipt",
        subtitle="Validation evidence, reviewer checklist, and the handoff route required for expert-facing package review.",
        issue_fields=issue_fields,
        page_number=4,
        page_total=page_total,
    )
    validation_metric_rows = [
        {
            "label": row.get("label", ""),
            "value": row.get("value", ""),
            "note": row.get("note", ""),
        }
        for row in validation_rows
    ]
    y = _draw_table(
        canvas,
        x=PAGE_MARGIN,
        y=y,
        width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        columns=[
            ("Validation item", "label", 0.22),
            ("State", "value", 0.14),
            ("Review note", "note", 0.64),
        ],
        rows=validation_metric_rows,
        title="Validation evidence",
        subtitle="These rows are copied from the review package metadata JSON so PDF output stays stable across repeated exports.",
        max_rows=8,
    ) - 10 * mm
    checklist_table_rows = [
        {
            "status": "[x]" if row.get("checked") else "[ ]",
            "label": row.get("label", ""),
            "note": row.get("note", ""),
        }
        for row in checklist_rows
    ]
    y = _draw_table(
        canvas,
        x=PAGE_MARGIN,
        y=y,
        width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        columns=[
            ("State", "status", 0.08),
            ("Checklist item", "label", 0.32),
            ("Reviewer note", "note", 0.60),
        ],
        rows=checklist_table_rows,
        title="Reviewer checklist",
        subtitle="Machine-verifiable lines are prefilled; open lines remain intentionally available for reviewer sign-off and comments.",
        max_rows=8,
    ) - 8 * mm
    route_text = (
        f"Review route: dashboard={_pdf_text(artifact_hrefs.get('committee_dashboard_html', 'not linked'))} | "
        f"drawing package={_pdf_text(artifact_hrefs.get('expert_review_html', 'not linked'))} | "
        f"technical workspace={_pdf_text(artifact_hrefs.get('technical_workspace_html', 'not linked'))} | "
        f"project registry={_pdf_text(artifact_hrefs.get('project_registry_report', 'not linked'))} | "
        f"batch job report={_pdf_text(artifact_hrefs.get('external_benchmark_batch_job_report_json', 'not linked'))}"
    )
    _draw_wrapped_text(
        canvas,
        route_text,
        x=PAGE_MARGIN,
        y=y,
        max_width=PAGE_WIDTH - 2 * PAGE_MARGIN,
        font_size=8.7,
        leading=11,
        color=colors.HexColor("#556b77"),
    )
    _draw_footer(canvas, issue_fields=issue_fields, page_number=4, page_total=page_total)
    canvas.save()

    return {
        "metadata_json": str(expert_review_metadata_json),
        "out_pdf": str(pdf_path),
        "page_count": page_total,
        "issue_id": _pdf_text(issue_fields.get("issue_id", "")),
        "template_name": template_name,
        "template_label": str(metadata.get("pdf_template_label", template_name)),
        "authority_name": _pdf_text(issue_fields.get("authority_name", "")),
        "package_purpose_label": _pdf_text(issue_fields.get("package_purpose_label", "")),
        "revision_code": _pdf_text(issue_fields.get("revision_code", "")),
        "embedded_font_regular": PDF_FONT_REGULAR,
        "embedded_font_bold": PDF_FONT_BOLD,
    }


def export_expert_review_pdf_batch(
    expert_review_metadata_json: Path = DEFAULT_EXPERT_REVIEW_METADATA_JSON,
    *,
    out_dir: Path | None = None,
    template_names: list[str] | tuple[str, ...] | None = None,
    out_manifest_json: Path | None = None,
    out_receipt_txt: Path | None = None,
) -> dict[str, Any]:
    metadata = _load_json(expert_review_metadata_json)
    if not metadata:
        raise ValueError(f"expert review metadata JSON not found or invalid: {expert_review_metadata_json}")

    selected_templates = _resolve_template_names(template_names)
    batch_dir = out_dir or _default_batch_out_dir(expert_review_metadata_json)
    batch_dir.mkdir(parents=True, exist_ok=True)

    default_pdf = _default_out_pdf(expert_review_metadata_json)
    manifest_path = out_manifest_json or batch_dir / f"{default_pdf.stem}.batch_manifest.json"
    receipt_path = out_receipt_txt or batch_dir / f"{default_pdf.stem}.batch_receipt.txt"

    artifacts = metadata.get("artifacts") if isinstance(metadata.get("artifacts"), dict) else {}
    artifact_paths = artifacts.get("paths") if isinstance(artifacts.get("paths"), dict) else {}
    source_review_html = _resolve_artifact_path(
        str(
            artifact_paths.get("optimized_review_html")
            or artifact_paths.get("technical_workspace_html")
            or ""
        ),
        metadata_json_path=expert_review_metadata_json,
    )
    source_expert_html = _resolve_artifact_path(
        str(artifact_paths.get("expert_review_html") or ""),
        metadata_json_path=expert_review_metadata_json,
    )

    export_results: list[dict[str, Any]] = []
    for template_name in selected_templates:
        review_html_filename, expert_html_filename = _template_html_filenames(template_name)
        review_html_path = batch_dir / review_html_filename
        expert_html_path = batch_dir / expert_html_filename
        metadata_json_path = batch_dir / _template_metadata_filename(expert_review_metadata_json, template_name)
        pdf_path = batch_dir / _template_pdf_filename(expert_review_metadata_json, template_name)
        zip_path = batch_dir / _template_zip_filename(expert_review_metadata_json, template_name)

        _copy_artifact_bytes(source_review_html, review_html_path)
        _copy_artifact_bytes(source_expert_html, expert_html_path)

        template_metadata = _materialize_template_metadata(
            metadata,
            template_name=template_name,
            output_metadata_json=metadata_json_path,
            output_review_html=review_html_path,
            output_expert_html=expert_html_path,
            output_pdf=pdf_path,
            output_zip=zip_path,
        )
        metadata_json_path.write_text(
            json.dumps(template_metadata, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        export_result = export_expert_review_pdf(
            expert_review_metadata_json=metadata_json_path,
            out_pdf=pdf_path,
            template_name=template_name,
        )
        zip_entries = _write_deterministic_zip(
            zip_path,
            entries=[
                ("optimized_drawing_review.html", review_html_path),
                ("optimized_drawing_expert_review.html", expert_html_path),
                ("optimized_drawing_expert_review.metadata.json", metadata_json_path),
                ("optimized_drawing_expert_review.pdf", pdf_path),
            ],
        )
        export_result["output_review_html"] = str(review_html_path)
        export_result["output_expert_html"] = str(expert_html_path)
        export_result["output_metadata_json"] = str(metadata_json_path)
        export_result["submission_zip"] = str(zip_path)
        export_result["zip_entries"] = zip_entries
        export_result["zip_entry_count"] = len(zip_entries)
        export_result["zip_sha256"] = _deterministic_file_sha256(zip_path)
        export_results.append(export_result)

    manifest_base_dir = manifest_path.parent
    manifest_payload = {
        "schema_version": "optimized_drawing_expert_review_pdf.batch_manifest.v1",
        "generated_at": str(metadata.get("generated_at", "") or ""),
        "source_metadata_json": str(expert_review_metadata_json),
        "output_dir": str(batch_dir),
        "template_order": selected_templates,
        "template_count": len(selected_templates),
        "receipt_txt": str(receipt_path),
        "zip_bundle_count": len(selected_templates),
        "templates": [
            {
                "template_name": str(result.get("template_name", "") or ""),
                "template_label": str(result.get("template_label", "") or ""),
                "output_review_html": str(result.get("output_review_html", "") or ""),
                "relative_review_html": _manifest_relpath(
                    Path(str(result.get("output_review_html", ""))),
                    base_dir=manifest_base_dir,
                ),
                "output_expert_html": str(result.get("output_expert_html", "") or ""),
                "relative_expert_html": _manifest_relpath(
                    Path(str(result.get("output_expert_html", ""))),
                    base_dir=manifest_base_dir,
                ),
                "output_metadata_json": str(result.get("output_metadata_json", "") or ""),
                "relative_metadata_json": _manifest_relpath(
                    Path(str(result.get("output_metadata_json", ""))),
                    base_dir=manifest_base_dir,
                ),
                "out_pdf": str(result.get("out_pdf", "") or ""),
                "relative_pdf": _manifest_relpath(Path(str(result.get("out_pdf", ""))), base_dir=manifest_base_dir),
                "submission_zip": str(result.get("submission_zip", "") or ""),
                "relative_submission_zip": _manifest_relpath(
                    Path(str(result.get("submission_zip", ""))),
                    base_dir=manifest_base_dir,
                ),
                "zip_entry_count": int(result.get("zip_entry_count", 0) or 0),
                "zip_sha256": str(result.get("zip_sha256", "") or ""),
                "zip_entries": [
                    {
                        "arcname": str(entry.get("arcname", "") or ""),
                        "size_bytes": int(entry.get("size_bytes", 0) or 0),
                        "sha256": str(entry.get("sha256", "") or ""),
                    }
                    for entry in (result.get("zip_entries") or [])
                    if isinstance(entry, dict)
                ],
                "page_count": int(result.get("page_count", 0) or 0),
                "issue_id": str(result.get("issue_id", "") or ""),
                "authority_name": str(result.get("authority_name", "") or ""),
                "package_purpose_label": str(result.get("package_purpose_label", "") or ""),
                "revision_code": str(result.get("revision_code", "") or ""),
            }
            for result in export_results
        ],
    }
    manifest_path.write_text(json.dumps(manifest_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    receipt_lines = [
        "optimized_drawing_expert_review_pdf_batch",
        f"source_metadata_json={expert_review_metadata_json}",
        f"output_dir={batch_dir}",
        f"manifest_json={manifest_path}",
        f"zip_bundle_count={len(selected_templates)}",
        f"template_order={','.join(selected_templates)}",
        f"template_count={len(selected_templates)}",
    ]
    receipt_lines.extend(
        (
            f"{item['template_name']} | label={item['template_label']} | html={item['relative_expert_html']} | "
            f"metadata={item['relative_metadata_json']} | pdf={item['relative_pdf']} | zip={item['relative_submission_zip']} | "
            f"entries={item['zip_entry_count']} | issue={item['issue_id']} | authority={item['authority_name']} | "
            f"package={item['package_purpose_label']}"
        )
        for item in manifest_payload["templates"]
    )
    receipt_path.write_text("\n".join(receipt_lines) + "\n", encoding="utf-8")

    return {
        "manifest_json": str(manifest_path),
        "receipt_txt": str(receipt_path),
        "output_dir": str(batch_dir),
        "template_order": selected_templates,
        "template_count": len(selected_templates),
        "zip_bundle_count": len(selected_templates),
        "templates": manifest_payload["templates"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expert-review-metadata-json", default=str(DEFAULT_EXPERT_REVIEW_METADATA_JSON))
    parser.add_argument("--out-pdf", default="")
    parser.add_argument("--batch-out-dir", default="")
    parser.add_argument("--batch-templates", default="default,seoul_permit_review,structural_peer_committee")
    parser.add_argument("--batch-manifest-json", default="")
    parser.add_argument("--batch-receipt-txt", default="")
    args = parser.parse_args()
    if (
        str(args.batch_out_dir).strip()
        or str(args.batch_manifest_json).strip()
        or str(args.batch_receipt_txt).strip()
    ):
        raw_templates = [item.strip() for item in str(args.batch_templates).split(",")]
        export_expert_review_pdf_batch(
            expert_review_metadata_json=Path(args.expert_review_metadata_json),
            out_dir=Path(args.batch_out_dir) if str(args.batch_out_dir).strip() else None,
            template_names=[item for item in raw_templates if item],
            out_manifest_json=Path(args.batch_manifest_json) if str(args.batch_manifest_json).strip() else None,
            out_receipt_txt=Path(args.batch_receipt_txt) if str(args.batch_receipt_txt).strip() else None,
        )
    else:
        export_expert_review_pdf(
            expert_review_metadata_json=Path(args.expert_review_metadata_json),
            out_pdf=Path(args.out_pdf) if str(args.out_pdf).strip() else None,
        )


if __name__ == "__main__":
    main()
