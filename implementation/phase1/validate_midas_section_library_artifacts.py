from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_TARGETS = (
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def summarize_artifact(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    section_library = metadata.get("section_library") if isinstance(metadata.get("section_library"), dict) else {}
    derived_catalog = section_library.get("derived_catalog") if isinstance(section_library.get("derived_catalog"), dict) else {}
    summary = section_library.get("summary") if isinstance(section_library.get("summary"), dict) else {}
    source_label = str(
        derived_catalog.get("source_label")
        or section_library.get("provenance")
        or "n/a"
    )
    summary_line = (
        f"MIDAS section-library: {('ok' if section_library else 'missing')} | "
        f"{int(summary.get('used_section_count', 0) or 0)}/{int(summary.get('section_row_count', 0) or 0)} used | "
        f"{int(summary.get('derived_template_count', 0) or 0)} templates | "
        f"source={source_label}"
    )
    return {
        "path": str(path),
        "has_section_library": bool(section_library),
        "used_section_count": int(summary.get("used_section_count", 0) or 0),
        "section_row_count": int(summary.get("section_row_count", 0) or 0),
        "derived_template_count": int(summary.get("derived_template_count", 0) or 0),
        "source_label": source_label,
        "summary_line": summary_line,
        "coverage_label": (
            f"{int(summary.get('used_section_count', 0) or 0)}/{int(summary.get('section_row_count', 0) or 0)} used"
            if section_library
            else "missing"
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate embedded MIDAS section_library metadata.")
    parser.add_argument(
        "--path",
        dest="paths",
        action="append",
        help="Explicit MIDAS model JSON to inspect. Can be passed multiple times. Defaults to the three canonical MIDAS artifacts.",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="Exit non-zero if any target is missing section_library metadata.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    targets = [Path(item) for item in args.paths] if args.paths else list(DEFAULT_TARGETS)
    summaries = [summarize_artifact(path) for path in targets]
    for row in summaries:
        print(
            f"{row['summary_line']} | {row['path']}"
        )
    if args.require and any(not row["has_section_library"] for row in summaries):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
