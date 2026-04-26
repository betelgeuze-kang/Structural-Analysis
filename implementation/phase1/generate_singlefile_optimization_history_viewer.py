from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from implementation.phase1.generate_optimization_history_viewer_payload import build_demo_payload
from implementation.phase1.singlefile_viewer_support import inline_design_theme_stylesheet

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "src" / "structure-viewer" / "optimization_history.html"
LOCAL_PAYLOAD_SCRIPT_RE = re.compile(
    r"\s*<script\s+src=[\"'](?:\./)?optimization_history\.data\.js[\"']\s*>\s*</script>\s*",
    re.IGNORECASE,
)
INLINE_JSON_RE = re.compile(
    r"(<script type=\"application/json\" id=\"optimization-history-data\">\s*)(.*?)(\s*</script>)",
    re.DOTALL,
)
HEAD_CLOSE_RE = re.compile(r"</head>", re.IGNORECASE)


def load_payload(payload_path: Path) -> dict[str, Any]:
    if payload_path.exists():
        return json.loads(payload_path.read_text(encoding="utf-8"))
    return build_demo_payload()


def generate_singlefile_optimization_history_html(payload: dict[str, Any]) -> str:
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    html = inline_design_theme_stylesheet(html)
    html, head_count = HEAD_CLOSE_RE.subn("<script>window.__STRUCTURAL_SINGLEFILE__=true;</script>\n</head>", html, count=1)
    if head_count != 1:
        raise RuntimeError("Failed to mark optimization history template as single-file")
    html = LOCAL_PAYLOAD_SCRIPT_RE.sub("\n", html, count=1)
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2).replace("</", "<\\/")

    def _replace(match: re.Match[str]) -> str:
        return f"{match.group(1)}{payload_json}{match.group(3)}"

    html, count = INLINE_JSON_RE.subn(_replace, html, count=1)
    if count != 1:
        raise RuntimeError("Failed to inject optimization history payload into template HTML")
    return html


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a single-file optimization history viewer HTML.")
    parser.add_argument(
        "--payload",
        default="implementation/phase1/release/visualization/optimization_history_viewer.json",
        help="Path to the optimization history payload JSON.",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/release/visualization/optimization_history_viewer_singlefile.html",
        help="Output HTML path.",
    )
    args = parser.parse_args()

    payload_path = Path(args.payload)
    output_path = Path(args.out)
    payload = load_payload(payload_path)
    html = generate_singlefile_optimization_history_html(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"Wrote optimization history single-file viewer: {output_path}")
    print(f"  payload: {payload_path if payload_path.exists() else 'demo fallback'}")
    print(f"  size_kb: {len(html) / 1024:.1f}")


if __name__ == "__main__":
    main()
