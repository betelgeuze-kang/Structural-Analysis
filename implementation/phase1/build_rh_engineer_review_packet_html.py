#!/usr/bin/env python3
"""Render engineer-review HTML from RH signed-closure packet template JSON."""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "rh-engineer-review-packet-html.v1"


def build_rh_engineer_review_packet_html(
    *,
    template_payload: dict[str, Any],
    bundle_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    packets = template_payload.get("packets") if isinstance(template_payload.get("packets"), dict) else {}
    rows: list[str] = []
    for work_id, packet in sorted(packets.items()):
        if not isinstance(packet, dict):
            continue
        fields = packet.get("template_fields") if isinstance(packet.get("template_fields"), dict) else {}
        checklist = packet.get("engineer_checklist") or []
        rows.append(
            "<section>"
            f"<h2>{html.escape(str(work_id))}</h2>"
            f"<p><strong>Required:</strong> {html.escape(str(packet.get('closure_evidence_required') or ''))}</p>"
            f"<p><strong>Supplementary:</strong> {html.escape(str(packet.get('supplementary_evidence_path') or ''))}</p>"
            f"<p>{html.escape(str(packet.get('supplementary_metric_note') or ''))}</p>"
            "<h3>Checklist</h3><ul>"
            + "".join(f"<li>{html.escape(str(item))}</li>" for item in checklist)
            + "</ul>"
            "<h3>Sign-off fields (fill before closure)</h3><table><tbody>"
            + "".join(
                f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value or ''))}</td></tr>"
                for key, value in fields.items()
            )
            + "</tbody></table></section>"
        )

    summary = bundle_summary or {}
    body = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        "<title>RH engineer review packet template</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:920px;margin:2rem auto;padding:0 1rem}"
        "section{border:1px solid #ccc;border-radius:8px;padding:1rem;margin:1rem 0}"
        "table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:.4rem;text-align:left}"
        "</style></head><body>"
        "<h1>RH engineer review packet (template)</h1>"
        "<p>Supplementary evidence does not close RH items. Attach signed artifact paths after review.</p>"
        f"<p>Delivery bundle: {html.escape(str(summary.get('reanalysis_status') or ''))} | "
        f"MGT integrity: {html.escape(str(summary.get('mgt_integrity_status') or ''))} | "
        f"Story: {html.escape(str(summary.get('story_reanalysis_status') or ''))}</p>"
        + "".join(rows)
        + "</body></html>"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "template_html",
        "html": body,
        "packet_count": len(packets),
    }
