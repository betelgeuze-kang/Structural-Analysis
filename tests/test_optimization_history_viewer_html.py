from __future__ import annotations

import json
import re
from pathlib import Path


def _extract_inline_payload(html_text: str) -> dict:
    match = re.search(
        r'<script type="application/json" id="optimization-history-data">\s*(\{.*?\})\s*</script>',
        html_text,
        re.DOTALL,
    )
    assert match, "optimization-history-data inline payload not found"
    return json.loads(match.group(1))


def test_html_embeds_real_optimization_payload_snapshot() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    html_path = repo_root / "src/structure-viewer/optimization_history.html"
    payload_path = repo_root / "implementation/phase1/release/visualization/optimization_history_viewer.json"

    html_text = html_path.read_text(encoding="utf-8")
    inline_payload = _extract_inline_payload(html_text)
    release_payload = json.loads(payload_path.read_text(encoding="utf-8"))

    assert "Generate mock history data" not in html_text
    assert "DEFAULT_ARTIFACT_CANDIDATES" in html_text
    assert "optimization_history_viewer.json" in html_text
    assert inline_payload["viewer_family"] == "optimization_history_viewer"
    assert inline_payload["source_mode"] == "report_plus_accepted_rows"
    assert inline_payload["summary"]["iteration_count"] == release_payload["summary"]["iteration_count"]
    assert inline_payload["summary"]["changed_group_count"] == release_payload["summary"]["changed_group_count"]
    assert inline_payload["summary"]["final_cost_proxy"] == release_payload["summary"]["final_cost_proxy"]
    assert inline_payload["summary"]["final_max_dcr"] == release_payload["summary"]["final_max_dcr"]
    assert inline_payload["history"][-1]["modified"] == release_payload["history"][-1]["modified"]
    assert inline_payload["history"][-1]["selected_count"] == release_payload["history"][-1]["selected_count"]
    assert 'id="export-png"' in html_text
    assert 'id="toggle-light-mode-button"' in html_text
    assert 'id="toggle-shortcuts-button"' in html_text
    assert 'id="shortcut-help"' in html_text
    assert 'const VIEWER_THEME_KEY = "optimization-history-theme-v1";' in html_text
    assert "function toggleLightMode()" in html_text
    assert "function toggleShortcutHelp(" in html_text
    assert "@media print" in html_text
    assert "async function exportOptimizationHistoryPng()" in html_text
    assert 'document.getElementById("export-png").addEventListener("click"' in html_text
