from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from implementation.phase1.generate_selfcontained_viewer import build_inline_vendor_import_urls
from implementation.phase1.generate_structure_viewer_payloads import _build_panel_zone_row_provenance_lookup
from implementation.phase1.singlefile_viewer_support import inline_design_theme_stylesheet

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "src" / "structure-viewer" / "panel_zone.html"
LOCAL_PAYLOAD_SCRIPT_RE = re.compile(
    r"\s*<script\s+src=[\"'](?:\./)?panel_zone\.data\.js[\"']\s*>\s*</script>\s*",
    re.IGNORECASE,
)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_panel_zone_payload(
    *,
    clash_report: dict[str, Any] | None,
    clash_artifact: dict[str, Any] | None,
    clash_verification: dict[str, Any] | None,
    joint_geometry: dict[str, Any] | None,
    anchorage: dict[str, Any] | None,
    inbox_status: dict[str, Any] | None = None,
    row_provenance_lookup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "viewer_family": "panel_zone_viewer",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clash_report": clash_report,
        "clash_artifact": clash_artifact,
        "clash_verification": clash_verification,
        "joint_geometry": joint_geometry,
        "anchorage": anchorage,
        "inbox_status": inbox_status,
        "row_provenance_lookup": row_provenance_lookup,
    }


def _inline_vendor_module_imports(
    html_content: str,
    *,
    three_import_url: str,
    orbit_controls_import_url: str,
) -> str:
    html_content, three_count = re.subn(
        r"import\s+\*\s+as\s+THREE\s+from\s+['\"]\.\/vendor\/three\.module\.js['\"];",
        f"import * as THREE from '{three_import_url}';",
        html_content,
        count=1,
    )
    html_content, orbit_count = re.subn(
        r"import\s+\{\s*OrbitControls\s*\}\s+from\s+['\"]\.\/vendor\/OrbitControls\.js['\"];",
        f"import {{ OrbitControls }} from '{orbit_controls_import_url}';",
        html_content,
        count=1,
    )
    if three_count != 1 or orbit_count != 1:
        raise RuntimeError("Failed to inline panel-zone vendor module imports from the template HTML")
    return html_content


def generate_singlefile_panel_zone_html(payload: dict[str, Any]) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = inline_design_theme_stylesheet(html)
    html = LOCAL_PAYLOAD_SCRIPT_RE.sub("\n", html, count=1)
    three_import_url, orbit_controls_import_url = build_inline_vendor_import_urls()
    html = _inline_vendor_module_imports(
        html,
        three_import_url=three_import_url,
        orbit_controls_import_url=orbit_controls_import_url,
    )
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")
    injection = (
        "<script>window.__STRUCTURAL_SINGLEFILE__=true;</script>\n"
        "<script type=\"application/json\" id=\"embedded-panel-zone-payload\">\n"
        f"{payload_json}\n"
        "</script>\n"
    )
    if "<script type=\"module\">" not in html:
        raise RuntimeError("Panel-zone template is missing the module bootstrap script")
    return html.replace("<script type=\"module\">", f"{injection}<script type=\"module\">", 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a single-file panel-zone viewer HTML.")
    parser.add_argument(
        "--clash-report",
        default="implementation/phase1/panel_zone_clash_report.json",
        help="Path to the panel-zone clash report JSON.",
    )
    parser.add_argument(
        "--clash-artifact",
        default="implementation/phase1/panel_zone_clash_artifact.json",
        help="Path to the panel-zone clash artifact JSON.",
    )
    parser.add_argument(
        "--joint-geometry",
        default="implementation/phase1/panel_zone_joint_geometry_3d.json",
        help="Path to the joint geometry JSON.",
    )
    parser.add_argument(
        "--clash-verification",
        default="implementation/phase1/panel_zone_clash_verification_3d.json",
        help="Path to the clash verification JSON.",
    )
    parser.add_argument(
        "--anchorage",
        default="implementation/phase1/panel_zone_rebar_anchorage_3d.json",
        help="Path to the anchorage JSON.",
    )
    parser.add_argument(
        "--inbox-status",
        default="implementation/phase1/panel_zone_solver_verified_inbox_status.json",
        help="Path to the panel-zone solver inbox status JSON.",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/visualization/panel_zone_viewer_singlefile.html",
        help="Output HTML path.",
    )
    args = parser.parse_args()

    payload = build_panel_zone_payload(
        clash_report=_load_optional_json(Path(args.clash_report)),
        clash_artifact=_load_optional_json(Path(args.clash_artifact)),
        clash_verification=_load_optional_json(Path(args.clash_verification)),
        joint_geometry=_load_optional_json(Path(args.joint_geometry)),
        anchorage=_load_optional_json(Path(args.anchorage)),
        inbox_status=_load_optional_json(Path(args.inbox_status)),
        row_provenance_lookup=_build_panel_zone_row_provenance_lookup(),
    )
    html = generate_singlefile_panel_zone_html(payload)
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote panel-zone single-file viewer: {output_path}")
    print(f"  size_kb: {len(html) / 1024:.1f}")


if __name__ == "__main__":
    main()
