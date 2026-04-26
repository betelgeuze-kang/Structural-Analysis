from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from implementation.phase1.singlefile_viewer_support import inline_design_theme_stylesheet


REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWER_DIR = REPO_ROOT / "src" / "structure-viewer"
VENDOR_DIR = VIEWER_DIR / "vendor"
RELEASE_VISUALIZATION_DIR = REPO_ROOT / "implementation" / "phase1" / "release" / "visualization"
PANEL_ZONE_SINGLEFILE_HTML = RELEASE_VISUALIZATION_DIR / "panel_zone_viewer_singlefile.html"
MIDAS33_MODEL_JSON = REPO_ROOT / "implementation" / "phase1" / "open_data" / "midas" / "midas_generator_33.json"
MIDAS33_PR_MODEL_JSON = REPO_ROOT / "implementation" / "phase1" / "open_data" / "midas" / "midas_generator_33.pr_recheck.json"
MIDAS33_OPTIMIZED_MODEL_JSON = REPO_ROOT / "implementation" / "phase1" / "open_data" / "midas" / "midas_generator_33.optimized.roundtrip.json"
KDS_ROW_PROVENANCE_TABLE_JSON = REPO_ROOT / "implementation" / "phase1" / "release" / "kds_compliance" / "midas_kds_row_provenance_table.json"
DYNAMIC_TIME_HISTORY_REPORT_JSON = REPO_ROOT / "implementation" / "phase1" / "dynamic_time_history_report.json"
NONLINEAR_NDTHA_STRESS_REPORT_JSON = REPO_ROOT / "implementation" / "phase1" / "nonlinear_ndtha_stress_report.json"
MEMBER_FORCE_SOFT_ACCEPT_REPORT_JSON = REPO_ROOT / "implementation" / "phase1" / "member_force_soft_accept_report.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_payload(path: Path, global_name: str, payload: Any) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(f"window.{global_name}={serialized};\n", encoding="utf-8")


def _encode_js_module_data_url(module_source: str) -> str:
    encoded = base64.b64encode(module_source.encode("utf-8")).decode("ascii")
    return f"data:text/javascript;base64,{encoded}"


def _build_inline_vendor_import_urls() -> tuple[str, str]:
    three_source = (VENDOR_DIR / "three.module.js").read_text(encoding="utf-8")
    three_import_url = _encode_js_module_data_url(three_source)

    orbit_source = (VENDOR_DIR / "OrbitControls.js").read_text(encoding="utf-8")
    orbit_source = orbit_source.replace(
        "from './three.module.js';",
        f"from '{three_import_url}';",
    )
    orbit_controls_import_url = _encode_js_module_data_url(orbit_source)
    return three_import_url, orbit_controls_import_url


def generate_panel_zone_singlefile_html(payload: Any) -> str:
    html = (VIEWER_DIR / "panel_zone.html").read_text(encoding="utf-8")
    html = inline_design_theme_stylesheet(html)
    html = re.sub(
        r"\s*<script\s+src=[\"'](?:\./)?panel_zone\.data\.js[\"']\s*>\s*</script>\s*",
        "\n",
        html,
        count=1,
    )
    three_import_url, orbit_controls_import_url = _build_inline_vendor_import_urls()
    html, three_count = re.subn(
        r"import\s+\*\s+as\s+THREE\s+from\s+['\"]\.\/vendor\/three\.module\.js['\"];",
        f"import * as THREE from '{three_import_url}';",
        html,
        count=1,
    )
    html, orbit_count = re.subn(
        r"import\s+\{\s*OrbitControls\s*\}\s+from\s+['\"]\.\/vendor\/OrbitControls\.js['\"];",
        f"import {{ OrbitControls }} from '{orbit_controls_import_url}';",
        html,
        count=1,
    )
    if three_count != 1 or orbit_count != 1:
        raise RuntimeError("Failed to inline panel-zone viewer vendor imports")

    embedded_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    injection = (
        "<script>window.__STRUCTURAL_SINGLEFILE__=true;</script>"
        "<script type=\"application/json\" id=\"embedded-panel-zone-payload\">"
        f"{embedded_json}"
        "</script>"
    )
    return html.replace("</body>", f"{injection}\n</body>", 1)


def _build_panel_zone_row_provenance_lookup() -> dict[str, Any]:
    if not KDS_ROW_PROVENANCE_TABLE_JSON.exists():
        return {}
    payload = _read_json(KDS_ROW_PROVENANCE_TABLE_JSON)
    member_lookup: dict[str, dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        baseline_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
        if not baseline_member_id:
            continue
        member_lookup.setdefault(
            baseline_member_id,
            {
                "baseline_focus_member_id": baseline_member_id,
                "member_id": str(row.get("member_id", "") or "").strip(),
                "case_id": str(row.get("case_id", "") or "").strip(),
                "combination_name": str(row.get("combination_name", "") or "").strip(),
                "clause_label": str(row.get("clause_label", "") or "").strip(),
                "viewer_row_ref": str(row.get("viewer_row_ref", "") or "").strip(),
                "viewer_row_url": str(row.get("viewer_row_url", "") or "").strip(),
                "viewer_slice_url": str(row.get("viewer_slice_url", "") or "").strip(),
                "bridge_row_provenance_mode_label": str(row.get("bridge_row_provenance_mode_label", "") or "").strip(),
                "bridge_row_provenance_summary_label": str(row.get("bridge_row_provenance_summary_label", "") or "").strip(),
            },
        )
    for row in payload.get("member_filter_rows") or []:
        if not isinstance(row, dict):
            continue
        baseline_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
        if not baseline_member_id:
            continue
        member_lookup.setdefault(
            baseline_member_id,
            {
                "baseline_focus_member_id": baseline_member_id,
                "member_id": str(row.get("member_id", "") or "").strip(),
                "case_id": str(row.get("top_case_id", "") or "").strip(),
                "combination_name": str(row.get("top_combination_name", "") or "").strip(),
                "clause_label": str(row.get("top_clause_label", "") or "").strip(),
                "viewer_row_ref": "",
                "viewer_row_url": str(row.get("viewer_row_url", "") or "").strip(),
                "viewer_slice_url": str(row.get("viewer_slice_url", "") or "").strip(),
                "bridge_row_provenance_mode_label": "member-filter provenance",
                "bridge_row_provenance_summary_label": str(row.get("member_summary_label", "") or "").strip(),
            },
        )
    return {
        "source": str(KDS_ROW_PROVENANCE_TABLE_JSON.relative_to(REPO_ROOT)),
        "member_lookup": member_lookup,
        "member_count": len(member_lookup),
    }


def build_payloads() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()

    viewer_report = _read_json(
        REPO_ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "visualization"
        / "structural_optimization_viewer.json"
    )
    smoke_history = _read_json(
        REPO_ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "design_optimization"
        / "design_optimization_cost_reduction_smoke_history.json"
    )
    solver_loop = _read_json(
        REPO_ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "design_optimization"
        / "design_optimization_solver_loop_report.json"
    )
    solver_loop_long = _read_json(
        REPO_ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "design_optimization"
        / "design_optimization_solver_loop_long_report.json"
    )
    stage_c = _read_json(
        REPO_ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "design_optimization"
        / "design_optimization_stage_c_report.json"
    )
    dynamic_time_history_report = _read_json(DYNAMIC_TIME_HISTORY_REPORT_JSON)
    nonlinear_ndtha_stress_report = _read_json(NONLINEAR_NDTHA_STRESS_REPORT_JSON)
    member_force_soft_accept_report = _read_json(MEMBER_FORCE_SOFT_ACCEPT_REPORT_JSON)
    panel_zone_joint = _read_json(REPO_ROOT / "implementation" / "phase1" / "panel_zone_joint_geometry_3d.json")
    panel_zone_anchorage = _read_json(
        REPO_ROOT / "implementation" / "phase1" / "panel_zone_rebar_anchorage_3d.json"
    )
    panel_zone_clash_artifact = _read_json(
        REPO_ROOT / "implementation" / "phase1" / "panel_zone_clash_artifact.json"
    )
    panel_zone_clash_verification = _read_json(
        REPO_ROOT / "implementation" / "phase1" / "panel_zone_clash_verification_3d.json"
    )
    panel_zone_clash_report = _read_json(REPO_ROOT / "implementation" / "phase1" / "panel_zone_clash_report.json")
    panel_zone_row_provenance_lookup = _build_panel_zone_row_provenance_lookup()

    return {
        "index": {
            "generated_at": generated_at,
            "source": "release_visualization",
            "case_context": viewer_report.get("case_context", {}),
            "interactive_3d": viewer_report.get("interactive_3d", {}),
            "results_explorer": viewer_report.get("results_explorer", {}),
        },
        "charts": {
            "generated_at": generated_at,
            "source": "release_visualization",
            "case_context": viewer_report.get("case_context", {}),
            "results_explorer": viewer_report.get("results_explorer", {}),
            "dynamic_time_history_report": dynamic_time_history_report,
            "nonlinear_ndtha_stress_report": nonlinear_ndtha_stress_report,
            "member_force_soft_accept_report": member_force_soft_accept_report,
            "member_force_station_source": member_force_soft_accept_report.get("station_source", {}),
            "member_overlay": viewer_report.get("member_overlay", {}),
            "change_overview": viewer_report.get("change_overview", {}),
            "detail_context": viewer_report.get("detail_context", {}),
        },
        "optimization_history": {
            "generated_at": generated_at,
            "source": "design_optimization_history",
            "smoke_history": smoke_history,
            "solver_loop_summary": solver_loop.get("summary", {}),
            "solver_loop_long_summary": solver_loop_long.get("summary", {}),
            "stage_c_summary": stage_c.get("summary", {}),
            "solver_loop_reason": solver_loop.get("reason_code"),
            "solver_loop_long_reason": solver_loop_long.get("reason_code"),
            "stage_c_reason": stage_c.get("reason_code"),
        },
        "panel_zone": {
            "generated_at": generated_at,
            "source": "panel_zone_release_artifacts",
            "joint_geometry": panel_zone_joint,
            "anchorage": panel_zone_anchorage,
            "clash_artifact": panel_zone_clash_artifact,
            "clash_verification": panel_zone_clash_verification,
            "clash_report": panel_zone_clash_report,
            "row_provenance_lookup": panel_zone_row_provenance_lookup,
        },
    }


def build_index_preset_payloads() -> dict[str, Any]:
    presets: dict[str, Any] = {}
    sources = [
        ("midas33", MIDAS33_MODEL_JSON, "canonical MIDAS33 raw model"),
        ("midas33_pr", MIDAS33_PR_MODEL_JSON, "canonical MIDAS33 pr_recheck raw model"),
        ("midas33_optimized", MIDAS33_OPTIMIZED_MODEL_JSON, "canonical MIDAS33 optimized roundtrip raw model"),
    ]
    for preset_key, path, label in sources:
        if not path.exists():
            continue
        presets[preset_key] = {
            "label": label,
            "report_name": path.name,
            "path": str(path.relative_to(REPO_ROOT)),
            "payload": _read_json(path),
        }
    return presets


def main() -> None:
    payloads = build_payloads()
    preset_payloads = build_index_preset_payloads()
    VIEWER_DIR.mkdir(parents=True, exist_ok=True)
    RELEASE_VISUALIZATION_DIR.mkdir(parents=True, exist_ok=True)
    _write_payload(VIEWER_DIR / "index.data.js", "__STRUCTURE_VIEWER_PAYLOAD__", payloads["index"])
    _write_payload(VIEWER_DIR / "index.midas33.data.js", "__STRUCTURE_VIEWER_PRESET_PAYLOADS__", preset_payloads)
    _write_payload(VIEWER_DIR / "charts.data.js", "__STRUCTURAL_CHARTS_DATA__", payloads["charts"])
    _write_payload(
        VIEWER_DIR / "optimization_history.data.js",
        "__OPTIMIZATION_HISTORY_PAYLOAD__",
        payloads["optimization_history"],
    )
    _write_payload(VIEWER_DIR / "panel_zone.data.js", "__PANEL_ZONE_PAYLOAD__", payloads["panel_zone"])
    PANEL_ZONE_SINGLEFILE_HTML.write_text(
        generate_panel_zone_singlefile_html(payloads["panel_zone"]),
        encoding="utf-8",
    )
    print("Wrote structure viewer payloads:")
    print(f"  {VIEWER_DIR / 'index.data.js'}")
    print(f"  {VIEWER_DIR / 'index.midas33.data.js'}")
    print(f"  {VIEWER_DIR / 'charts.data.js'}")
    print(f"  {VIEWER_DIR / 'optimization_history.data.js'}")
    print(f"  {VIEWER_DIR / 'panel_zone.data.js'}")
    print(f"  {PANEL_ZONE_SINGLEFILE_HTML}")


if __name__ == "__main__":
    main()
