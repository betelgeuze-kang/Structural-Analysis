from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from implementation.phase1.singlefile_viewer_support import inline_design_theme_stylesheet

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "src" / "structure-viewer" / "charts.html"
LOCAL_PAYLOAD_SCRIPT_RE = re.compile(
    r"\s*<script\s+src=[\"'](?:\./)?charts\.data\.js[\"']\s*>\s*</script>\s*",
    re.IGNORECASE,
)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_payload(
    *,
    viewer_report: dict[str, Any] | None,
    dynamic_report: dict[str, Any] | None,
    ndtha_report: dict[str, Any] | None,
    member_force_report: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "charts_singlefile_export",
        "case_context": viewer_report.get("case_context", {}) if isinstance(viewer_report, dict) else {},
        "results_explorer": viewer_report.get("results_explorer", {}) if isinstance(viewer_report, dict) else {},
        "dynamic_time_history_report": dynamic_report,
        "nonlinear_ndtha_stress_report": ndtha_report,
        "member_force_soft_accept_report": member_force_report,
    }


def generate_singlefile_charts_html(payload: dict[str, Any]) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = inline_design_theme_stylesheet(html)
    embedded_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    injection = (
        "<script>window.__STRUCTURAL_SINGLEFILE__=true;</script>\n"
        "<script type=\"application/json\" id=\"charts-artifact-data\">\n"
        f"{embedded_json}\n"
        "</script>\n"
    )
    html, count = LOCAL_PAYLOAD_SCRIPT_RE.subn(f"\n{injection}", html, count=1)
    if count != 1:
        raise RuntimeError("Failed to inline charts payload into template HTML")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a single-file structural charts viewer HTML.")
    parser.add_argument(
        "--viewer",
        default="implementation/phase1/release/visualization/structural_optimization_viewer.json",
        help="Path to the structural optimization viewer JSON.",
    )
    parser.add_argument(
        "--dynamic",
        default="implementation/phase1/dynamic_time_history_report.json",
        help="Path to the dynamic time history report JSON.",
    )
    parser.add_argument(
        "--ndtha",
        default="implementation/phase1/nonlinear_ndtha_stress_report.json",
        help="Path to the nonlinear NDTHA report JSON.",
    )
    parser.add_argument(
        "--member-force",
        default="implementation/phase1/member_force_soft_accept_report.json",
        help="Path to the member force report JSON.",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/visualization/charts_viewer_singlefile.html",
        help="Output HTML path.",
    )
    args = parser.parse_args()

    payload = build_payload(
        viewer_report=_load_optional_json(Path(args.viewer)),
        dynamic_report=_load_optional_json(Path(args.dynamic)),
        ndtha_report=_load_optional_json(Path(args.ndtha)),
        member_force_report=_load_optional_json(Path(args.member_force)),
    )
    html = generate_singlefile_charts_html(payload)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote charts single-file viewer: {output_path}")
    print(f"  size_kb: {len(html) / 1024:.1f}")


if __name__ == "__main__":
    main()
