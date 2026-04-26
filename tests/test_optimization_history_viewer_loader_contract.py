from __future__ import annotations

import json
from pathlib import Path


def _extract_assignment_payload(script_text: str, variable_name: str) -> dict:
    prefix = f"window.{variable_name}="
    assert script_text.startswith(prefix), f"{variable_name} assignment not found"
    payload_text = script_text[len(prefix):].strip()
    if payload_text.endswith(";"):
        payload_text = payload_text[:-1]
    return json.loads(payload_text)


def test_optimization_history_html_prefers_local_script_then_inline_then_repo_then_demo() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    assert "./optimization_history.data.js" in text
    assert "window.__OPTIMIZATION_HISTORY_PAYLOAD__" in text
    assert "window.__STRUCTURE_VIEWER_DATA__" in text
    assert "window.__STRUCTURE_VIEWER_PAYLOAD__" in text
    assert "optimization-history-data" in text
    assert "readLocalPayloadScript" in text
    assert "readInlineJson" in text
    assert "../../implementation/phase1/release/visualization/optimization_history_viewer.json" in text
    assert "demo fallback" in text
    assert "render(inlinePayload || localPayload || DEMO_PAYLOAD" in text
    assert "embedded inline payload" in text
    assert "local payload script" in text
    assert 'id="provenance-source"' in text
    assert 'id="provenance-report"' in text
    assert 'id="provenance-timestamp"' in text
    assert 'id="provenance-selection"' in text
    assert 'id="copy-deep-link"' in text


def test_optimization_history_html_keeps_suite_shell_identity_and_dense_chrome() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    assert 'body class="structural-surface history-command-shell"' in text
    assert 'class="companion-topbar"' in text
    assert 'class="companion-workspace history-workspace"' in text
    assert 'class="shell-nav-list"' in text
    assert 'class="chip chip-button"' in text
    assert 'class="summary-bar companion-insight"' in text


def test_optimization_history_html_avoids_cdn_only_runtime_dependencies() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    forbidden_fragments = [
        "cdn.jsdelivr.net",
        "unpkg.com",
        "three.module.js",
        'type="importmap"',
        "OrbitControls",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in text


def test_optimization_history_html_syncs_query_and_copy_link_from_shared_selection() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    assert "buildSelectionQueryUrl" in text
    assert "syncSelectionQuery" in text
    assert "navigator.clipboard" in text
    assert 'document.getElementById("copy-deep-link").addEventListener("click"' in text
    assert "Deep link copied" in text


def test_optimization_history_html_exposes_dynamic_history_insight_rail_markers() -> None:
    text = Path("src/structure-viewer/optimization_history.html").read_text(encoding="utf-8")

    assert 'class="summary-bar companion-insight"' in text
    for element_id in [
        "iterations-card",
        "iterations-note",
        "cost-card",
        "cost-note",
        "dcr-card",
        "dcr-note",
        "modified-card",
        "modified-note",
    ]:
        assert f'id="{element_id}"' in text

    assert 'document.getElementById("cost-panel-note").textContent = last.event_label || "final accepted batch";' in text
    assert 'document.getElementById("dcr-panel-note").textContent = last.event_note || "final D/C envelope";' in text
    assert 'document.getElementById("modified-panel-note").textContent = `unique modified groups ${summary.modified_total ?? last.modified ?? "-"}`;' in text
    assert 'selected rows ${last.selected_count ?? "-"}' in text


def test_optimization_history_local_payload_script_contains_real_artifact_context() -> None:
    script_text = Path("src/structure-viewer/optimization_history.data.js").read_text(encoding="utf-8")
    payload = _extract_assignment_payload(script_text, "__OPTIMIZATION_HISTORY_PAYLOAD__")

    assert payload["source"] == "design_optimization_history"
    assert "smoke_history" in payload
    assert "solver_loop_summary" in payload
    assert "solver_loop_long_summary" in payload
    assert payload["smoke_history"]["summary"]["count"] >= 1
    assert payload["solver_loop_summary"]["solver_backend_static"] == "rocm_torch_hip_mainloop"
    assert payload["solver_loop_long_summary"]["objective_calibration_applied"] is True
