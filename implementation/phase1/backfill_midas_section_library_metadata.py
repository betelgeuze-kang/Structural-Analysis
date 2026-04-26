#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from parse_midas_mgt_to_json_npz import derive_section_productization_for_model_payload
except ImportError:  # pragma: no cover - package import fallback
    from implementation.phase1.parse_midas_mgt_to_json_npz import derive_section_productization_for_model_payload


CANONICAL_MIDAS_ARTIFACTS = (
    Path("implementation/phase1/open_data/midas/midas_generator_33.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.pr_recheck.json"),
    Path("implementation/phase1/open_data/midas/midas_generator_33.optimized.roundtrip.json"),
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return payload


def _embedded_summary(section_library: dict[str, Any]) -> dict[str, Any]:
    summary = section_library.get("summary") if isinstance(section_library.get("summary"), dict) else {}
    return {
        "section_rows": int(summary.get("section_row_count", 0) or 0),
        "used": int(summary.get("used_section_count", 0) or 0),
        "unused": int(summary.get("unused_section_count", 0) or 0),
        "templates": int(summary.get("derived_template_count", 0) or 0),
        "family_mix": summary.get("family_counts") if isinstance(summary.get("family_counts"), dict) else {},
        "shape_mix": summary.get("shape_counts") if isinstance(summary.get("shape_counts"), dict) else {},
    }


def backfill_artifact(path: Path, *, write: bool = False) -> dict[str, Any]:
    payload = _load_json(path)
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    if not isinstance(model, dict):
        raise ValueError(f"{path} is missing a model object")
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    derived = derive_section_productization_for_model_payload(payload)
    if not derived:
        raise ValueError(f"{path} did not yield section_library metadata")
    existing = metadata.get("section_library") if isinstance(metadata.get("section_library"), dict) else {}
    changed = existing != derived
    if write and changed:
        metadata = dict(metadata)
        metadata["section_library"] = derived
        model = dict(model)
        model["metadata"] = metadata
        payload = dict(payload)
        payload["model"] = model
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = _embedded_summary(derived)
    summary.update(
        {
            "path": str(path),
            "changed": changed,
            "had_embedded_section_library": bool(existing),
            "written": bool(write and changed),
        }
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Embed section_library metadata into canonical MIDAS JSON artifacts.")
    parser.add_argument("paths", nargs="*", type=Path, default=list(CANONICAL_MIDAS_ARTIFACTS))
    parser.add_argument("--write", action="store_true", help="Write updated payloads back to disk.")
    args = parser.parse_args()

    for path in args.paths:
        summary = backfill_artifact(path, write=args.write)
        print(
            f"{path}: section_rows={summary['section_rows']} used={summary['used']} "
            f"unused={summary['unused']} templates={summary['templates']} "
            f"changed={summary['changed']} written={summary['written']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
