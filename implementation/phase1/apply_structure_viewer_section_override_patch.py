#!/usr/bin/env python3
"""Apply a structure-viewer section override patch to a copied source artifact."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import urlencode


REASONS = {
    "PASS": "structure viewer section override patch applied",
    "ERR_PATCH_INVALID": "patch payload is missing required contract fields",
    "ERR_SOURCE_INVALID": "source artifact is missing a writable elements container",
    "ERR_WRITEBACK_ARGS": "raw MIDAS writeback arguments are incomplete",
    "ERR_WRITEBACK_EXPORT_FAIL": "raw MIDAS writeback export failed",
}

DEFAULT_RESULTS_EXPLORER_HTML = Path(
    "implementation/phase1/release/visualization/structural_optimization_viewer.html"
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _normalize(value: object) -> str:
    return str(value or "").strip()


def _resolve_elements_container(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    direct = payload.get("elements")
    if isinstance(direct, list):
        return direct
    model = payload.get("model")
    if isinstance(model, dict):
        nested = model.get("elements")
        if isinstance(nested, list):
            return nested
    return None


def _resolve_sections(payload: dict[str, Any]) -> list[dict[str, Any]]:
    direct = payload.get("sections")
    if isinstance(direct, list):
        return [row for row in direct if isinstance(row, dict)]
    model = payload.get("model")
    if isinstance(model, dict):
        nested = model.get("sections")
        if isinstance(nested, list):
            return [row for row in nested if isinstance(row, dict)]
    return []


def _section_lookup_keys(section: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("id", "name", "section_name", "signature", "label", "summary"):
        value = _normalize(section.get(field))
        if value:
            keys.add(value)
    return keys


def _find_target_section_id(sections: list[dict[str, Any]], target_section: str) -> tuple[str, str]:
    target = _normalize(target_section)
    if not target:
        return "", ""
    for section in sections:
        if target in _section_lookup_keys(section):
            return _normalize(section.get("id")), _normalize(section.get("name") or section.get("label") or target)
    return "", ""


def _find_target_section_from_entry(
    sections: list[dict[str, Any]],
    entry: dict[str, Any],
) -> tuple[str, str]:
    direct_target_id = _normalize(entry.get("target_section_id"))
    if direct_target_id:
        fallback_name = _normalize(
            entry.get("target_section_name")
            or entry.get("target_section_catalog_label")
            or entry.get("target_section_input")
            or entry.get("target_section")
            or direct_target_id
        )
        for section in sections:
            if _normalize(section.get("id")) == direct_target_id:
                return direct_target_id, _normalize(section.get("name") or section.get("label") or fallback_name)
        return direct_target_id, fallback_name

    for field in ("target_section", "target_section_input", "target_section_name", "target_section_catalog_label"):
        resolved_id, resolved_name = _find_target_section_id(sections, _normalize(entry.get(field)))
        if resolved_id:
            return resolved_id, resolved_name
    return "", ""


def _element_member_keys(element: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for field in ("member_id", "id", "element_id"):
        value = _normalize(element.get(field))
        if value:
            keys.add(value)
    return keys


def _unique_nonempty(values: list[object]) -> list[str]:
    return sorted({_normalize(value) for value in values if _normalize(value)})


def _relative_href(target: Path, base: Path) -> str:
    try:
        return str(target.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(target.resolve())


def _as_file_uri(path: Path) -> str:
    try:
        return path.resolve().as_uri()
    except ValueError:
        return str(path.resolve())


def _slugify(value: object) -> str:
    text = _normalize(value).lower()
    slug = "".join(ch if ch.isalnum() else "_" for ch in text).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "item"


def _build_writeback_row_action_hint(row: dict[str, Any]) -> str:
    resolution = _normalize(row.get("resolution"))
    changed = bool(row.get("changed"))
    changed_element_count = int(row.get("changed_element_count", 0) or 0)
    target_section = _normalize(row.get("target_section"))
    previous_sections = ", ".join(_unique_nonempty(list(row.get("previous_section_ids") or []))) or "--"
    next_sections = ", ".join(_unique_nonempty(list(row.get("next_section_ids") or []))) or "--"
    if resolution != "resolved_to_section_id":
        return "target section did not resolve to a section_id; inspect the patch manifest and fix the section mapping before trusting writeback output."
    if not changed:
        return "no element section changed for this member; confirm the representative section already matched the requested target before exporting again."
    return (
        f"verify member section reassignment {previous_sections} -> {next_sections} "
        f"(changed elements={changed_element_count}, target={target_section or 'n/a'}) "
        "in the compare console, then review the patched MIDAS MGT and diff report."
    )


def _summarize_writeback_compare_kind_counts(rows: list[dict[str, Any]]) -> tuple[dict[str, int], str]:
    counts: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = _normalize(row.get("kind")) or "unknown"
        counts[kind] = int(counts.get(kind, 0) or 0) + 1
    summary = " | ".join(
        f"{kind}={int(count)}" for kind, count in sorted(counts.items()) if int(count) > 0
    )
    return counts, (summary or "none")


def _build_writeback_result_compare_payload(
    *,
    generated_at: str,
    diff_review_json_out: Path,
    diff_review_html_out: Path,
    writeback_report_out: Path,
    writeback_patch_manifest_out: Path,
    writeback_instruction_sidecar_out: Path,
    output_mgt_path: Path,
    patch_payload: dict[str, Any],
    diff_payload: dict[str, Any],
    applied_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        report_payload = _load_json(writeback_report_out)
    except Exception:
        report_payload = {}
    report_summary = (
        report_payload.get("summary")
        if isinstance(report_payload.get("summary"), dict)
        else {}
    )
    window_rows = [
        row
        for row in (report_summary.get("source_vs_output_diff_window_rows") or [])
        if isinstance(row, dict)
    ]
    sample_rows = [
        row
        for row in (report_summary.get("source_vs_output_diff_sample_rows") or [])
        if isinstance(row, dict)
    ]
    window_member_row_indices = (
        report_summary.get("source_output_mgt_diff_window_member_row_indices")
        if isinstance(report_summary.get("source_output_mgt_diff_window_member_row_indices"), dict)
        else {}
    )
    sample_member_row_indices = (
        report_summary.get("source_output_mgt_diff_member_row_indices")
        if isinstance(report_summary.get("source_output_mgt_diff_member_row_indices"), dict)
        else {}
    )

    compare_rows: list[dict[str, Any]] = []
    matched_member_count = 0
    actual_window_match_count = 0
    for row in applied_rows:
        if not isinstance(row, dict):
            continue
        member_id = _normalize(row.get("member_id"))
        window_indices = [
            int(value)
            for value in (window_member_row_indices.get(member_id) or [])
            if isinstance(value, int) or str(value).strip().isdigit()
        ]
        sample_indices = [
            int(value)
            for value in (sample_member_row_indices.get(member_id) or [])
            if isinstance(value, int) or str(value).strip().isdigit()
        ]
        matched_window_rows = [
            window_rows[index]
            for index in window_indices
            if 0 <= int(index) < len(window_rows)
        ]
        matched_sample_rows = [
            sample_rows[index]
            for index in sample_indices
            if 0 <= int(index) < len(sample_rows)
        ]
        effective_rows = matched_window_rows or matched_sample_rows
        kind_counts, kind_summary = _summarize_writeback_compare_kind_counts(effective_rows)
        if effective_rows:
            matched_member_count += 1
        if matched_window_rows:
            actual_window_match_count += 1
        if matched_window_rows:
            compare_status = "matched_regenerated_artifact_diff_window"
            compare_status_label = (
                f"actual regenerated artifact compare | window_rows={len(matched_window_rows)}"
            )
        elif matched_sample_rows:
            compare_status = "matched_regenerated_artifact_diff_sample_only"
            compare_status_label = (
                f"actual regenerated artifact compare | sample_rows={len(matched_sample_rows)}"
            )
        else:
            compare_status = "no_regenerated_artifact_member_match"
            compare_status_label = (
                "actual regenerated artifact compare | no member-specific source/output diff rows"
            )
        compare_summary_label = (
            f"{compare_status_label} | kinds={kind_summary} | sections="
            f"{', '.join(_unique_nonempty(list(row.get('previous_section_ids') or []))) or '--'}"
            f" -> {', '.join(_unique_nonempty(list(row.get('next_section_ids') or []))) or '--'}"
        )
        compare_rows.append(
            {
                **row,
                "actual_regenerated_compare_status": compare_status,
                "actual_regenerated_compare_status_label": compare_status_label,
                "actual_regenerated_compare_summary_label": compare_summary_label,
                "actual_regenerated_compare_kind_counts": kind_counts,
                "actual_regenerated_compare_kind_summary": kind_summary,
                "actual_regenerated_compare_window_row_indices": window_indices,
                "actual_regenerated_compare_sample_row_indices": sample_indices,
                "actual_regenerated_compare_row_ids": [
                    _normalize(item.get("row_id")) for item in effective_rows if _normalize(item.get("row_id"))
                ],
                "actual_regenerated_compare_window_rows": matched_window_rows,
                "actual_regenerated_compare_sample_rows": matched_sample_rows,
                "actual_regenerated_compare_effective_row_count": int(len(effective_rows)),
            }
        )

    member_ids = _unique_nonempty([row.get("member_id") for row in compare_rows])
    return {
        "schema_version": "1.0",
        "run_id": "phase1-structure-viewer-section-override-writeback-result-compare",
        "generated_at": generated_at,
        "contract_pass": bool(diff_payload.get("contract_pass")),
        "compare_surface_mode": "standalone_html_and_json",
        "viewer_url": _normalize(patch_payload.get("viewer_url")),
        "source_patch": str(patch_payload.get("source_patch") or diff_payload.get("source_patch") or ""),
        "source_artifact": str(diff_payload.get("source_artifact") or ""),
        "source_mgt": str(diff_payload.get("source_mgt") or ""),
        "dataset_npz": str(diff_payload.get("dataset_npz") or ""),
        "output_mgt": str(output_mgt_path),
        "writeback_report": str(writeback_report_out),
        "writeback_patch_manifest": str(writeback_patch_manifest_out),
        "writeback_instruction_sidecar": str(writeback_instruction_sidecar_out),
        "writeback_diff_review_json": str(diff_review_json_out),
        "writeback_diff_review_html": str(diff_review_html_out),
        "summary": {
            "member_count": int(len(member_ids)),
            "matched_member_count": int(matched_member_count),
            "actual_window_match_count": int(actual_window_match_count),
            "window_row_count": int(len(window_rows)),
            "sample_row_count": int(len(sample_rows)),
            "source_output_mgt_summary_line": str(
                report_summary.get("source_output_mgt_summary_line", "") or ""
            ),
            "source_vs_output_diff_summary_line": str(
                report_summary.get("source_vs_output_diff_summary_line", "") or ""
            ),
            "summary_line": (
                f"actual regenerated compare | matched_members={matched_member_count}/{len(member_ids)}"
                f" | window_matches={actual_window_match_count}"
                f" | diff_window_rows={len(window_rows)}"
            ),
        },
        "rows": compare_rows,
    }


def _build_writeback_result_compare_html(
    payload: dict[str, Any],
    *,
    html_path: Path,
    results_explorer_diff_review_url: str,
) -> str:
    summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    base_dir = html_path.parent
    link_rows = [
        ("Viewer", _normalize(payload.get("viewer_url"))),
        ("Results explorer diff review", _normalize(results_explorer_diff_review_url)),
        ("Writeback diff review", _relative_href(Path(str(payload.get("writeback_diff_review_html"))), base_dir) if _normalize(payload.get("writeback_diff_review_html")) else ""),
        ("Writeback report", _relative_href(Path(str(payload.get("writeback_report"))), base_dir) if _normalize(payload.get("writeback_report")) else ""),
        ("Patched MIDAS MGT", _relative_href(Path(str(payload.get("output_mgt"))), base_dir) if _normalize(payload.get("output_mgt")) else ""),
    ]
    links_html = "".join(
        f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">{html.escape(label)}</a>'
        for label, href in link_rows
        if href
    )
    row_cards: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        compare_href = _normalize(row.get("results_explorer_compare_url"))
        row_cards.append(
            "".join(
                [
                    "<tr>",
                    "<td>",
                    html.escape(_normalize(row.get("member_id")) or "--"),
                    (
                        f'<div><a href="{html.escape(compare_href)}" target="_blank" rel="noopener noreferrer">Open compare console</a></div>'
                        if compare_href
                        else ""
                    ),
                    "</td>",
                    f"<td>{html.escape(_normalize(row.get('actual_regenerated_compare_status_label')) or '--')}</td>",
                    f"<td>{html.escape(_normalize(row.get('actual_regenerated_compare_kind_summary')) or '--')}</td>",
                    f"<td>{html.escape(', '.join([str(v) for v in (row.get('actual_regenerated_compare_row_ids') or [])]) or '--')}</td>",
                    f"<td>{html.escape(_normalize(row.get('writeback_action_hint')) or '--')}</td>",
                    "</tr>",
                ]
            )
        )
    rows_html = "".join(row_cards) or '<tr><td colspan="5">No compare rows available.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Section Override Writeback Result Compare</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');
    :root {{
      color-scheme: dark;
      --bg:#08121d;
      --panel:#111c29;
      --panel-soft:#152435;
      --text:#ecf2f6;
      --muted:#96a8bb;
      --border:#2b3d50;
      --accent:#4fb7ad;
      --accent-warm:#f4b56b;
      --shadow:0 18px 40px rgba(0,0,0,.24);
    }}
    body {{
      margin: 0;
      font: 14px/1.6 'IBM Plex Sans KR','Pretendard','Noto Sans KR',sans-serif;
      background:
        radial-gradient(circle at top left, rgba(244,181,107,.12), transparent 24%),
        radial-gradient(circle at 84% 16%, rgba(79,183,173,.16), transparent 22%),
        linear-gradient(180deg, #07111c 0%, #0d1824 42%, #111e2b 100%);
      color: var(--text);
    }}
    .page {{ max-width: 1240px; margin: 0 auto; padding: 28px 24px 40px; }}
    .panel {{
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-soft) 100%);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px 24px;
      margin-bottom: 18px;
      box-shadow: var(--shadow);
    }}
    h1 {{
      margin: 0 0 12px;
      font-family: 'Space Grotesk','IBM Plex Sans KR',sans-serif;
      font-size: 34px;
      letter-spacing: -.04em;
    }}
    p {{ color: var(--muted); }}
    .links {{ display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(79,183,173,.18);
      background: rgba(79,183,173,.08);
      font-weight: 700;
    }}
    .summary {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
    .metric {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(79,183,173,.08);
      border: 1px solid rgba(79,183,173,.14);
    }}
    .metric strong {{
      display:block;
      font-family:'Space Grotesk','IBM Plex Sans KR',sans-serif;
      font-size:24px;
      letter-spacing:-.03em;
      color:var(--accent-warm);
    }}
    table {{ width:100%; border-collapse:collapse; }}
    th, td {{ padding:12px; border-bottom:1px solid rgba(150,168,187,.12); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.14em; }}
  </style>
</head>
<body>
  <div class="page">
    <section class="panel">
      <h1>Section Override Writeback Result Compare</h1>
      <p>This surface re-reads the regenerated writeback artifacts and summarizes the member-level source/output diff evidence that can be reviewed alongside the compare console.</p>
      <div class="summary">
        <div class="metric"><strong>{int(summary.get("matched_member_count", 0) or 0)}/{int(summary.get("member_count", 0) or 0)}</strong><span>members matched in regenerated diff artifacts</span></div>
        <div class="metric"><strong>{int(summary.get("actual_window_match_count", 0) or 0)}</strong><span>members matched in diff window rows</span></div>
        <div class="metric"><strong>{int(summary.get("window_row_count", 0) or 0)}</strong><span>source/output diff window rows</span></div>
        <div class="metric"><strong>{int(summary.get("sample_row_count", 0) or 0)}</strong><span>source/output diff sample rows</span></div>
      </div>
      <div class="links">{links_html}</div>
      <p>{html.escape(str(summary.get("summary_line", "") or ""))}</p>
      <p>{html.escape(str(summary.get("source_output_mgt_summary_line", "") or ""))}</p>
    </section>
    <section class="panel">
      <table>
        <thead>
          <tr>
            <th>Member</th>
            <th>Actual regenerated compare</th>
            <th>Diff kinds</th>
            <th>Row ids</th>
            <th>Suggested action</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </div>
</body>
</html>"""


def _build_results_explorer_diff_review_url(
    *,
    diff_review_json_out: Path,
    diff_review_html_out: Path,
    writeback_report_out: Path,
    writeback_patch_manifest_out: Path,
    writeback_instruction_sidecar_out: Path,
    output_mgt_path: Path,
    patch_payload: dict[str, Any],
    diff_payload: dict[str, Any],
    writeback_compare_json_out: Path | None = None,
    writeback_compare_html_out: Path | None = None,
) -> str:
    params = {
        "source": "section_override_writeback_diff_review",
        "focus": "results",
        "results_companion": "footer",
        "results_detail_block": "footer",
        "writeback_diff_json": _as_file_uri(diff_review_json_out),
        "writeback_diff_html": _as_file_uri(diff_review_html_out),
        "writeback_report": _as_file_uri(writeback_report_out),
        "writeback_patch_manifest": _as_file_uri(writeback_patch_manifest_out),
        "writeback_instruction_sidecar": _as_file_uri(writeback_instruction_sidecar_out),
        "writeback_output_mgt": _as_file_uri(output_mgt_path),
        "writeback_contract_pass": "true" if bool(diff_payload.get("contract_pass")) else "false",
        "writeback_changed_rows": str(
            int(diff_payload.get("summary", {}).get("changed_row_count", 0) or 0)
        ),
        "writeback_changed_elements": str(
            int(diff_payload.get("summary", {}).get("changed_element_count", 0) or 0)
        ),
        "member_set": "|".join(
            _unique_nonempty([row.get("member_id") for row in diff_payload.get("rows", [])])
        ),
    }
    if writeback_compare_json_out is not None:
        params["writeback_compare_json"] = _as_file_uri(writeback_compare_json_out)
    if writeback_compare_html_out is not None:
        params["writeback_compare_html"] = _as_file_uri(writeback_compare_html_out)
    viewer_url = _normalize(patch_payload.get("viewer_url"))
    if viewer_url:
        params["viewer_return_url"] = viewer_url
    return f"{_as_file_uri(DEFAULT_RESULTS_EXPLORER_HTML)}?{urlencode(params)}"


def _build_results_explorer_compare_member_url(
    *,
    member_id: str,
    member_ids: list[str],
    action_hint: str,
    resolution: str,
    target_section: str,
    previous_sections: list[str],
    next_sections: list[str],
    viewer_url: str,
    diff_review_json_out: Path | None = None,
    diff_review_html_out: Path | None = None,
    writeback_report_out: Path | None = None,
    writeback_patch_manifest_out: Path | None = None,
    writeback_instruction_sidecar_out: Path | None = None,
    output_mgt_path: Path | None = None,
    writeback_compare_json_out: Path | None = None,
    writeback_compare_html_out: Path | None = None,
    writeback_compare_status: str = "",
    writeback_compare_summary: str = "",
    writeback_compare_kind_summary: str = "",
    writeback_compare_row_ids: list[str] | None = None,
    writeback_compare_row_count: int = 0,
) -> str:
    params = {
        "source": "section_override_writeback_diff_review",
        "focus": "results",
        "results_card": "envelope",
        "results_companion": "compare",
        "results_detail_block": "compare",
        "results_detail_selection_key": "results-detail:compare",
        "results_detail_focus_key": f"selection-set-compare:member:{_slugify(member_id)}",
        "codecheck_detail_block": "selection-set",
        "codecheck_detail_selection_key": f"selection-set:{member_id}",
        "codecheck_detail_focus_key": f"selection-set:row:{_slugify(member_id)}",
        "focus_member": member_id,
        "member_id": member_id,
        "member_set": "|".join(_unique_nonempty(member_ids)),
        "writeback_member_id": member_id,
        "writeback_resolution": resolution,
        "writeback_target_section": target_section,
        "writeback_previous_sections": "|".join(_unique_nonempty(previous_sections)),
        "writeback_next_sections": "|".join(_unique_nonempty(next_sections)),
        "writeback_action_hint": action_hint,
    }
    if viewer_url:
        params["viewer_return_url"] = viewer_url
    if diff_review_json_out is not None:
        params["writeback_diff_json"] = _as_file_uri(diff_review_json_out)
    if diff_review_html_out is not None:
        params["writeback_diff_html"] = _as_file_uri(diff_review_html_out)
    if writeback_report_out is not None:
        params["writeback_report"] = _as_file_uri(writeback_report_out)
    if writeback_patch_manifest_out is not None:
        params["writeback_patch_manifest"] = _as_file_uri(writeback_patch_manifest_out)
    if writeback_instruction_sidecar_out is not None:
        params["writeback_instruction_sidecar"] = _as_file_uri(writeback_instruction_sidecar_out)
    if output_mgt_path is not None:
        params["writeback_output_mgt"] = _as_file_uri(output_mgt_path)
    if writeback_compare_json_out is not None:
        params["writeback_compare_json"] = _as_file_uri(writeback_compare_json_out)
    if writeback_compare_html_out is not None:
        params["writeback_compare_html"] = _as_file_uri(writeback_compare_html_out)
    if _normalize(writeback_compare_status):
        params["writeback_compare_status"] = _normalize(writeback_compare_status)
    if _normalize(writeback_compare_summary):
        params["writeback_compare_summary"] = _normalize(writeback_compare_summary)
    if _normalize(writeback_compare_kind_summary):
        params["writeback_compare_kind_summary"] = _normalize(writeback_compare_kind_summary)
    if writeback_compare_row_count > 0:
        params["writeback_compare_row_count"] = str(int(writeback_compare_row_count))
    row_ids = _unique_nonempty(list(writeback_compare_row_ids or []))
    if row_ids:
        params["writeback_compare_row_ids"] = "|".join(row_ids)
    return f"{_as_file_uri(DEFAULT_RESULTS_EXPLORER_HTML)}?{urlencode(params)}"


def _build_writeback_diff_review_payload(
    *,
    generated_at: str,
    patch_path: Path,
    source_path: Path,
    source_mgt_path: Path,
    dataset_npz_path: Path,
    output_mgt_path: Path,
    writeback_report_out: Path,
    writeback_patch_manifest_out: Path,
    writeback_instruction_sidecar_out: Path,
    patch_payload: dict[str, Any],
    applied_rows: list[dict[str, Any]],
    writeback_contract_pass: bool,
) -> dict[str, Any]:
    changed_rows = [row for row in applied_rows if bool(row.get("changed"))]
    changed_element_count = sum(int(row.get("changed_element_count", 0) or 0) for row in changed_rows)
    return {
        "schema_version": "1.0",
        "run_id": "phase1-structure-viewer-section-override-writeback-diff-review",
        "generated_at": generated_at,
        "contract_pass": writeback_contract_pass,
        "review_surface_mode": "standalone_html_and_json",
        "viewer_url": _normalize(patch_payload.get("viewer_url")),
        "source_patch": str(patch_path),
        "source_artifact": str(source_path),
        "source_mgt": str(source_mgt_path),
        "dataset_npz": str(dataset_npz_path),
        "output_mgt": str(output_mgt_path),
        "writeback_report": str(writeback_report_out),
        "writeback_patch_manifest": str(writeback_patch_manifest_out),
        "writeback_instruction_sidecar": str(writeback_instruction_sidecar_out),
        "summary": {
            "patch_member_count": int(patch_payload.get("patch_member_count", 0) or 0),
            "reviewable_row_count": len(applied_rows),
            "changed_row_count": len(changed_rows),
            "changed_element_count": changed_element_count,
            "resolved_entry_count": sum(1 for row in applied_rows if _normalize(row.get("resolution")) == "resolved_to_section_id"),
            "unresolved_entry_count": sum(1 for row in applied_rows if _normalize(row.get("resolution")) != "resolved_to_section_id"),
        },
        "rows": applied_rows,
    }


def _build_writeback_diff_review_html(
    payload: dict[str, Any],
    *,
    html_path: Path,
    writeback_report_out: Path,
    writeback_patch_manifest_out: Path,
    writeback_instruction_sidecar_out: Path,
    output_mgt_path: Path,
    results_explorer_diff_review_url: str,
) -> str:
    summary = payload.get("summary", {})
    rows = payload.get("rows", [])
    base_dir = html_path.parent
    link_rows = [
        ("Viewer", _normalize(payload.get("viewer_url"))),
        ("Results explorer diff review", _normalize(results_explorer_diff_review_url)),
        ("Writeback report", _relative_href(writeback_report_out, base_dir)),
        ("Patch manifest", _relative_href(writeback_patch_manifest_out, base_dir)),
        ("Instruction sidecar", _relative_href(writeback_instruction_sidecar_out, base_dir)),
        ("Patched MIDAS MGT", _relative_href(output_mgt_path, base_dir)),
    ]
    links_html = "".join(
        f'<a href="{html.escape(href)}" target="_blank" rel="noopener noreferrer">{html.escape(label)}</a>'
        for label, href in link_rows
        if href
    )
    row_cards = []
    for row in rows:
        member_id = _normalize(row.get("member_id")) or "--"
        resolution = _normalize(row.get("resolution")) or "--"
        previous_sections = ", ".join(_unique_nonempty(list(row.get("previous_section_ids") or []))) or "--"
        next_sections = ", ".join(_unique_nonempty(list(row.get("next_section_ids") or []))) or "--"
        target_section = _normalize(row.get("target_section")) or "--"
        matched_element_ids = ", ".join(_unique_nonempty(list(row.get("matched_element_ids") or []))) or "--"
        change_label = "changed" if bool(row.get("changed")) else "unchanged"
        compare_href = _normalize(row.get("results_explorer_compare_url"))
        action_hint = _normalize(row.get("writeback_action_hint")) or "--"
        row_cards.append(
            "".join(
                [
                    '<tr>',
                    (
                        f'<td>{html.escape(member_id)}'
                        + (
                            f"<div><a href=\"{html.escape(compare_href)}\" target=\"_blank\" rel=\"noopener noreferrer\">Open compare console</a></div>"
                            if compare_href
                            else ""
                        )
                        + '</td>'
                    ),
                    f'<td>{html.escape(resolution)}</td>',
                    f'<td>{html.escape(previous_sections)}</td>',
                    f'<td>{html.escape(next_sections)}</td>',
                    f'<td>{html.escape(target_section)}</td>',
                    f'<td>{html.escape(matched_element_ids)}</td>',
                    f'<td>{html.escape(change_label)}</td>',
                    f'<td>{html.escape(action_hint)}</td>',
                    '</tr>',
                ]
            )
        )
    rows_html = "".join(row_cards) or '<tr><td colspan="8">No diff rows available.</td></tr>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Section Override Writeback Diff Review</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');
    :root {{
      color-scheme: dark;
      --bg:#08121d;
      --panel:#111c29;
      --panel-alt:#152435;
      --text:#ecf2f6;
      --muted:#96a8bb;
      --accent:#4fb7ad;
      --accent-warm:#f4b56b;
      --border:#2b3d50;
      --shadow:0 18px 40px rgba(0,0,0,.24);
    }}
    body {{
      margin: 0;
      font: 14px/1.6 'IBM Plex Sans KR','Pretendard','Noto Sans KR',sans-serif;
      background:
        radial-gradient(circle at top left, rgba(244,181,107,.12), transparent 24%),
        radial-gradient(circle at 84% 16%, rgba(79,183,173,.16), transparent 22%),
        linear-gradient(180deg, #07111c 0%, #0d1824 42%, #111e2b 100%);
      color: var(--text);
    }}
    .page {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    .panel {{
      background: linear-gradient(180deg, var(--panel) 0%, var(--panel-alt) 100%);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 22px 24px;
      margin-bottom: 18px;
      box-shadow: var(--shadow);
    }}
    h1 {{
      margin: 0 0 12px;
      font-family: 'Space Grotesk','IBM Plex Sans KR',sans-serif;
      font-size: 34px;
      letter-spacing: -.04em;
    }}
    p {{
      color: var(--muted);
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }}
    .metric {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(79,183,173,.08);
      border: 1px solid rgba(79,183,173,.14);
    }}
    .metric strong {{
      display: block;
      font-family:'Space Grotesk','IBM Plex Sans KR',sans-serif;
      font-size: 24px;
      letter-spacing:-.03em;
      color: var(--accent-warm);
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
    }}
    .links a {{
      color: var(--accent);
      text-decoration: none;
      padding: 8px 12px;
      border: 1px solid rgba(79,183,173,.18);
      border-radius: 999px;
      background: rgba(79,183,173,.08);
      font-weight: 700;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    th, td {{
      padding: 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      color: var(--muted);
      font-weight: 700;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-size: 11px;
    }}
    .muted {{
      color: var(--muted);
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="panel">
      <h1>Section Override Writeback Diff Review</h1>
      <p class="muted">Generated at {html.escape(_normalize(payload.get("generated_at")))}. This surface summarizes the raw MIDAS writeback diff that came from a structure-viewer section override patch.</p>
      <div class="summary">
        <div class="metric"><span class="muted">Patch Members</span><strong>{int(summary.get("patch_member_count", 0) or 0)}</strong></div>
        <div class="metric"><span class="muted">Reviewable Rows</span><strong>{int(summary.get("reviewable_row_count", 0) or 0)}</strong></div>
        <div class="metric"><span class="muted">Changed Rows</span><strong>{int(summary.get("changed_row_count", 0) or 0)}</strong></div>
        <div class="metric"><span class="muted">Changed Elements</span><strong>{int(summary.get("changed_element_count", 0) or 0)}</strong></div>
        <div class="metric"><span class="muted">Resolved</span><strong>{int(summary.get("resolved_entry_count", 0) or 0)}</strong></div>
        <div class="metric"><span class="muted">Unresolved</span><strong>{int(summary.get("unresolved_entry_count", 0) or 0)}</strong></div>
      </div>
      <div class="links">{links_html}</div>
    </section>
    <section class="panel">
      <h2>Per-member Diff</h2>
      <table>
        <thead>
          <tr>
            <th>Member</th>
            <th>Resolution</th>
            <th>Before</th>
            <th>After</th>
            <th>Target</th>
            <th>Element IDs</th>
            <th>Status</th>
            <th>Action Hint</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def _augment_writeback_report(
    report_path: Path,
    *,
    diff_review_json_out: Path,
    diff_review_html_out: Path,
    diff_payload: dict[str, Any],
    compare_json_out: Path | None = None,
    compare_html_out: Path | None = None,
    compare_payload: dict[str, Any] | None = None,
) -> None:
    if not report_path.exists():
        return
    try:
        report_payload = _load_json(report_path)
    except Exception:
        return
    if not isinstance(report_payload, dict):
        return
    summary = report_payload.setdefault("summary", {})
    if isinstance(summary, dict):
        summary["section_override_writeback_diff_review_json"] = str(diff_review_json_out)
        summary["section_override_writeback_diff_review_html"] = str(diff_review_html_out)
        summary["section_override_writeback_diff_review_row_count"] = int(diff_payload.get("summary", {}).get("reviewable_row_count", 0) or 0)
        summary["section_override_writeback_diff_review_changed_row_count"] = int(diff_payload.get("summary", {}).get("changed_row_count", 0) or 0)
        summary["section_override_writeback_results_explorer_diff_review_url"] = _normalize(
            diff_payload.get("results_explorer_diff_review_url")
        )
        if compare_json_out is not None:
            summary["section_override_writeback_result_compare_json"] = str(compare_json_out)
        if compare_html_out is not None:
            summary["section_override_writeback_result_compare_html"] = str(compare_html_out)
        if isinstance(compare_payload, dict):
            summary["section_override_writeback_result_compare_member_count"] = int(
                compare_payload.get("summary", {}).get("member_count", 0) or 0
            )
            summary["section_override_writeback_result_compare_matched_member_count"] = int(
                compare_payload.get("summary", {}).get("matched_member_count", 0) or 0
            )
            summary["section_override_writeback_result_compare_summary_line"] = _normalize(
                compare_payload.get("summary", {}).get("summary_line")
            )
    report_payload["section_override_writeback_diff_review"] = {
        "contract_pass": bool(diff_payload.get("contract_pass")),
        "review_surface_mode": _normalize(diff_payload.get("review_surface_mode")),
        "json_out": str(diff_review_json_out),
        "html_out": str(diff_review_html_out),
        "results_explorer_diff_review_url": _normalize(diff_payload.get("results_explorer_diff_review_url")),
        "summary": diff_payload.get("summary", {}),
    }
    if compare_json_out is not None or compare_html_out is not None:
        report_payload["section_override_writeback_result_compare"] = {
            "json_out": str(compare_json_out) if compare_json_out is not None else "",
            "html_out": str(compare_html_out) if compare_html_out is not None else "",
            "summary": compare_payload.get("summary", {}) if isinstance(compare_payload, dict) else {},
        }
    _write_json(report_path, report_payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source-mgt", default="")
    parser.add_argument("--dataset-npz", default="")
    parser.add_argument("--output-mgt", default="")
    parser.add_argument("--writeback-report-out", default="")
    parser.add_argument("--writeback-patch-manifest-out", default="")
    parser.add_argument("--writeback-instruction-sidecar-out", default="")
    args = parser.parse_args()

    patch_path = Path(args.patch)
    source_path = Path(args.source)
    out_path = Path(args.out)
    source_mgt_path = Path(args.source_mgt) if str(args.source_mgt).strip() else None
    dataset_npz_path = Path(args.dataset_npz) if str(args.dataset_npz).strip() else None
    output_mgt_path = Path(args.output_mgt) if str(args.output_mgt).strip() else None
    writeback_requested = any([source_mgt_path, dataset_npz_path, output_mgt_path])

    patch_payload = _load_json(patch_path)
    source_payload = _load_json(source_path)

    if not isinstance(patch_payload, dict) or _normalize(patch_payload.get("patch_mode")) != "working_section_override_patch":
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-apply-structure-viewer-section-override-patch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_PATCH_INVALID",
            "reason": REASONS["ERR_PATCH_INVALID"],
            "inputs": {
                "patch": str(patch_path),
                "source": str(source_path),
                "out": str(out_path),
            },
        }
        _write_json(out_path, payload)
        raise SystemExit(1)

    if not isinstance(source_payload, dict):
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-apply-structure-viewer-section-override-patch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_SOURCE_INVALID",
            "reason": REASONS["ERR_SOURCE_INVALID"],
            "inputs": {
                "patch": str(patch_path),
                "source": str(source_path),
                "out": str(out_path),
            },
        }
        _write_json(out_path, payload)
        raise SystemExit(1)

    elements = _resolve_elements_container(source_payload)
    if elements is None:
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-apply-structure-viewer-section-override-patch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_SOURCE_INVALID",
            "reason": REASONS["ERR_SOURCE_INVALID"],
            "inputs": {
                "patch": str(patch_path),
                "source": str(source_path),
                "out": str(out_path),
            },
        }
        _write_json(out_path, payload)
        raise SystemExit(1)

    if writeback_requested and not (source_mgt_path and dataset_npz_path and output_mgt_path):
        payload = {
            "schema_version": "1.0",
            "run_id": "phase1-apply-structure-viewer-section-override-patch",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": "ERR_WRITEBACK_ARGS",
            "reason": REASONS["ERR_WRITEBACK_ARGS"],
            "inputs": {
                "patch": str(patch_path),
                "source": str(source_path),
                "out": str(out_path),
                "source_mgt": str(source_mgt_path or ""),
                "dataset_npz": str(dataset_npz_path or ""),
                "output_mgt": str(output_mgt_path or ""),
            },
        }
        _write_json(out_path, payload)
        raise SystemExit(1)

    patch_entries = patch_payload.get("patch_entries")
    if not isinstance(patch_entries, list):
        patch_entries = []
    sections = _resolve_sections(source_payload)

    by_key: dict[str, list[dict[str, Any]]] = {}
    for element in elements:
        if not isinstance(element, dict):
            continue
        for key in _element_member_keys(element):
            by_key.setdefault(key, []).append(element)

    applied_rows: list[dict[str, Any]] = []
    matched_element_count = 0
    resolved_count = 0
    unresolved_count = 0
    all_patch_member_ids = _unique_nonempty(
        [_normalize(entry.get("member_id")) for entry in patch_entries if isinstance(entry, dict)]
    )
    viewer_url = _normalize(patch_payload.get("viewer_url"))

    for entry in patch_entries:
        if not isinstance(entry, dict):
            continue
        member_id = _normalize(entry.get("member_id"))
        candidate_keys = {
            member_id,
            *[_normalize(value) for value in entry.get("element_ids", []) if _normalize(value)],
            _normalize(entry.get("representative_element_id")),
        }
        candidate_keys.discard("")
        matched_elements: list[dict[str, Any]] = []
        seen_ids: set[int] = set()
        for key in candidate_keys:
            for element in by_key.get(key, []):
                element_id = id(element)
                if element_id in seen_ids:
                    continue
                seen_ids.add(element_id)
                matched_elements.append(element)

        target_section = _normalize(entry.get("target_section"))
        resolved_section_id, resolved_section_name = _find_target_section_from_entry(sections, entry)
        resolution = "resolved_to_section_id" if resolved_section_id else "unresolved_target_section"
        if resolved_section_id:
            resolved_count += 1
        else:
            unresolved_count += 1
        matched_element_count += len(matched_elements)
        element_diffs: list[dict[str, Any]] = []

        for element in matched_elements:
            previous_section_id = element.get("section_id")
            element_identifier = (
                _normalize(element.get("id"))
                or _normalize(element.get("element_id"))
                or _normalize(element.get("member_id"))
            )
            element["viewer_section_override_target_section"] = target_section
            element["viewer_section_override_resolution"] = resolution
            element["viewer_section_override_applied_at"] = _normalize(entry.get("applied_at")) or _normalize(patch_payload.get("applied_at"))
            element["viewer_section_override_draft_note"] = _normalize(entry.get("draft_note"))
            element["viewer_section_override_previous_section_id"] = previous_section_id
            if resolved_section_id:
                element["section_id"] = resolved_section_id
                element["viewer_section_override_resolved_section_id"] = resolved_section_id
                element["viewer_section_override_resolved_section_name"] = resolved_section_name or target_section
            element_diffs.append(
                {
                    "element_id": element_identifier,
                    "member_id": _normalize(element.get("member_id")) or member_id,
                    "previous_section_id": _normalize(previous_section_id),
                    "next_section_id": _normalize(element.get("section_id")),
                }
            )

        previous_section_ids = _unique_nonempty([row.get("previous_section_id") for row in element_diffs])
        next_section_ids = _unique_nonempty([row.get("next_section_id") for row in element_diffs])
        changed_element_count = sum(
            1
            for row in element_diffs
            if _normalize(row.get("previous_section_id")) != _normalize(row.get("next_section_id"))
        )
        changed = any(
            _normalize(row.get("previous_section_id")) != _normalize(row.get("next_section_id"))
            for row in element_diffs
        )
        row_payload = {
            "member_id": member_id,
            "representative_element_id": _normalize(entry.get("representative_element_id")),
            "matched_element_count": len(matched_elements),
            "matched_element_ids": [row["element_id"] for row in element_diffs if _normalize(row.get("element_id"))],
            "target_section": target_section,
            "resolved_section_id": resolved_section_id,
            "resolved_section_name": resolved_section_name,
            "resolution": resolution,
            "previous_section_ids": previous_section_ids,
            "next_section_ids": next_section_ids,
            "changed_element_count": changed_element_count,
            "changed": changed,
            "element_diffs": element_diffs,
        }
        row_payload["writeback_action_hint"] = _build_writeback_row_action_hint(row_payload)
        row_payload["results_explorer_compare_url"] = _build_results_explorer_compare_member_url(
            member_id=member_id,
            member_ids=all_patch_member_ids,
            action_hint=str(row_payload["writeback_action_hint"]),
            resolution=resolution,
            target_section=target_section,
            previous_sections=previous_section_ids,
            next_sections=next_section_ids,
            viewer_url=viewer_url,
        )
        applied_rows.append(row_payload)

    source_payload["viewer_section_override_patch"] = {
        "contract_version": 1,
        "patch_mode": "working_section_override_patch",
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "source_patch": str(patch_path),
        "source_artifact": str(source_path),
        "patch_member_count": int(patch_payload.get("patch_member_count", 0) or 0),
        "matched_element_count": matched_element_count,
        "resolved_entry_count": resolved_count,
        "unresolved_entry_count": unresolved_count,
        "rows": applied_rows,
    }
    _write_json(out_path, source_payload)

    if writeback_requested and source_mgt_path and dataset_npz_path and output_mgt_path:
        writeback_report_out = (
            Path(args.writeback_report_out)
            if str(args.writeback_report_out).strip()
            else output_mgt_path.with_suffix(".section_override_writeback_report.json")
        )
        writeback_patch_manifest_out = (
            Path(args.writeback_patch_manifest_out)
            if str(args.writeback_patch_manifest_out).strip()
            else output_mgt_path.with_suffix(".section_override_writeback_manifest.json")
        )
        writeback_instruction_sidecar_out = (
            Path(args.writeback_instruction_sidecar_out)
            if str(args.writeback_instruction_sidecar_out).strip()
            else output_mgt_path.with_suffix(".section_override_instruction_sidecar.json")
        )
        diff_review_json_out = output_mgt_path.with_suffix(".section_override_writeback_diff_review.json")
        diff_review_html_out = output_mgt_path.with_suffix(".section_override_writeback_diff_review.html")
        compare_json_out = output_mgt_path.with_suffix(".section_override_writeback_result_compare.json")
        compare_html_out = output_mgt_path.with_suffix(".section_override_writeback_result_compare.html")
        with tempfile.TemporaryDirectory(prefix="section-override-writeback-") as temp_dir:
            temp_dir_path = Path(temp_dir)
            empty_changes_json = temp_dir_path / "empty_changes.json"
            _write_json(empty_changes_json, {"schema_version": "1.0", "changes": []})
            export_cmd = [
                sys.executable,
                "implementation/phase1/export_design_optimization_to_mgt.py",
                "--source-mgt",
                str(source_mgt_path),
                "--parsed-model-json",
                str(out_path),
                "--dataset-npz",
                str(dataset_npz_path),
                "--changes-json",
                str(empty_changes_json),
                "--output-mgt",
                str(output_mgt_path),
                "--report-out",
                str(writeback_report_out),
                "--patch-manifest-out",
                str(writeback_patch_manifest_out),
                "--instruction-sidecar-out",
                str(writeback_instruction_sidecar_out),
            ]
            proc = subprocess.run(export_cmd, check=False, capture_output=True, text=True)
        diff_payload = _build_writeback_diff_review_payload(
            generated_at=datetime.now(timezone.utc).isoformat(),
            patch_path=patch_path,
            source_path=source_path,
            source_mgt_path=source_mgt_path,
            dataset_npz_path=dataset_npz_path,
            output_mgt_path=output_mgt_path,
            writeback_report_out=writeback_report_out,
            writeback_patch_manifest_out=writeback_patch_manifest_out,
            writeback_instruction_sidecar_out=writeback_instruction_sidecar_out,
            patch_payload=patch_payload,
            applied_rows=applied_rows,
            writeback_contract_pass=proc.returncode == 0,
        )
        results_explorer_diff_review_url = _build_results_explorer_diff_review_url(
            diff_review_json_out=diff_review_json_out,
            diff_review_html_out=diff_review_html_out,
            writeback_report_out=writeback_report_out,
            writeback_patch_manifest_out=writeback_patch_manifest_out,
            writeback_instruction_sidecar_out=writeback_instruction_sidecar_out,
            output_mgt_path=output_mgt_path,
            patch_payload=patch_payload,
            diff_payload=diff_payload,
            writeback_compare_json_out=compare_json_out,
            writeback_compare_html_out=compare_html_out,
        )
        compare_payload = _build_writeback_result_compare_payload(
            generated_at=datetime.now(timezone.utc).isoformat(),
            diff_review_json_out=diff_review_json_out,
            diff_review_html_out=diff_review_html_out,
            writeback_report_out=writeback_report_out,
            writeback_patch_manifest_out=writeback_patch_manifest_out,
            writeback_instruction_sidecar_out=writeback_instruction_sidecar_out,
            output_mgt_path=output_mgt_path,
            patch_payload=patch_payload,
            diff_payload=diff_payload,
            applied_rows=applied_rows,
        )
        compare_rows_by_member_id = {
            _normalize(row.get("member_id")): row
            for row in compare_payload.get("rows", [])
            if isinstance(row, dict) and _normalize(row.get("member_id"))
        }
        for row in applied_rows:
            member_compare_row = compare_rows_by_member_id.get(_normalize(row.get("member_id")), {})
            compare_url = _build_results_explorer_compare_member_url(
                member_id=_normalize(row.get("member_id")),
                member_ids=all_patch_member_ids,
                action_hint=_normalize(row.get("writeback_action_hint")),
                resolution=_normalize(row.get("resolution")),
                target_section=_normalize(row.get("target_section")),
                previous_sections=list(row.get("previous_section_ids") or []),
                next_sections=list(row.get("next_section_ids") or []),
                viewer_url=viewer_url,
                diff_review_json_out=diff_review_json_out,
                diff_review_html_out=diff_review_html_out,
                writeback_report_out=writeback_report_out,
                writeback_patch_manifest_out=writeback_patch_manifest_out,
                writeback_instruction_sidecar_out=writeback_instruction_sidecar_out,
                output_mgt_path=output_mgt_path,
                writeback_compare_json_out=compare_json_out,
                writeback_compare_html_out=compare_html_out,
                writeback_compare_status=_normalize(
                    member_compare_row.get("actual_regenerated_compare_status_label")
                ),
                writeback_compare_summary=_normalize(
                    member_compare_row.get("actual_regenerated_compare_summary_label")
                ),
                writeback_compare_kind_summary=_normalize(
                    member_compare_row.get("actual_regenerated_compare_kind_summary")
                ),
                writeback_compare_row_ids=list(
                    member_compare_row.get("actual_regenerated_compare_row_ids") or []
                ),
                writeback_compare_row_count=int(
                    member_compare_row.get("actual_regenerated_compare_effective_row_count", 0) or 0
                ),
            )
            row["results_explorer_compare_url"] = compare_url
            if isinstance(member_compare_row, dict):
                member_compare_row["results_explorer_compare_url"] = compare_url
        source_payload["viewer_section_override_patch"]["rows"] = applied_rows
        diff_payload["results_explorer_diff_review_url"] = results_explorer_diff_review_url
        diff_payload["rows"] = applied_rows
        _write_json(diff_review_json_out, diff_payload)
        _write_text(
            diff_review_html_out,
            _build_writeback_diff_review_html(
                diff_payload,
                html_path=diff_review_html_out,
                writeback_report_out=writeback_report_out,
                writeback_patch_manifest_out=writeback_patch_manifest_out,
                writeback_instruction_sidecar_out=writeback_instruction_sidecar_out,
                output_mgt_path=output_mgt_path,
                results_explorer_diff_review_url=results_explorer_diff_review_url,
            ),
        )
        _write_json(compare_json_out, compare_payload)
        _write_text(
            compare_html_out,
            _build_writeback_result_compare_html(
                compare_payload,
                html_path=compare_html_out,
                results_explorer_diff_review_url=results_explorer_diff_review_url,
            ),
        )
        _augment_writeback_report(
            writeback_report_out,
            diff_review_json_out=diff_review_json_out,
            diff_review_html_out=diff_review_html_out,
            diff_payload=diff_payload,
            compare_json_out=compare_json_out,
            compare_html_out=compare_html_out,
            compare_payload=compare_payload,
        )
        source_payload["viewer_section_override_patch"]["raw_midas_writeback"] = {
            "source_mgt": str(source_mgt_path),
            "dataset_npz": str(dataset_npz_path),
            "output_mgt": str(output_mgt_path),
            "report_out": str(writeback_report_out),
            "patch_manifest_out": str(writeback_patch_manifest_out),
            "instruction_sidecar_out": str(writeback_instruction_sidecar_out),
            "diff_review_json_out": str(diff_review_json_out),
            "diff_review_html_out": str(diff_review_html_out),
            "result_compare_json_out": str(compare_json_out),
            "result_compare_html_out": str(compare_html_out),
            "diff_review_surface_mode": "standalone_html_and_json",
            "diff_review_open_target": str(diff_review_html_out),
            "results_explorer_diff_review_url": results_explorer_diff_review_url,
            "contract_pass": proc.returncode == 0,
            "command": export_cmd,
            "stdout": str(proc.stdout or "").strip(),
            "stderr": str(proc.stderr or "").strip(),
        }
        _write_json(out_path, source_payload)
        if proc.returncode != 0:
            raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
