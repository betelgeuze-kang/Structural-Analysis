#!/usr/bin/env python3
"""Validate real-project corpus provenance before any crawler or benchmark promotion."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from jsonschema import Draft202012Validator


SCHEMA_VERSION = "real_project_corpus_manifest.v1"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase_ids(manifest: dict[str, Any]) -> list[str]:
    return [str(row.get("phase_id", "") or "") for row in manifest.get("phase_closeout_order", [])]


def validate_manifest(manifest: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    schema_validator = Draft202012Validator(schema)
    for error in sorted(schema_validator.iter_errors(manifest), key=lambda item: list(item.path)):
        path = ".".join(str(part) for part in error.path) or "<root>"
        errors.append(f"schema violation at {path}: {error.message}")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    if _phase_ids(manifest)[:3] != ["P0", "P1", "P2"]:
        errors.append("phase_closeout_order must start with P0, P1, P2")

    source_ids: set[str] = set()
    for source in manifest.get("source_families", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id", "") or "")
        if source_id in source_ids:
            errors.append(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)
        access = source.get("access_policy") if isinstance(source.get("access_policy"), dict) else {}
        classification = str(access.get("classification", "") or "")
        redistribution_allowed = bool(access.get("redistribution_allowed", False))
        requires_manual_review = bool(access.get("requires_manual_review", False))
        if classification in {"restricted", "unknown", "redacted"} and redistribution_allowed:
            errors.append(f"restricted sources cannot be marked redistribution_allowed: {source_id}")
        if classification in {"restricted", "unknown"} and not requires_manual_review:
            errors.append(f"restricted or unknown sources require manual review: {source_id}")
        if source.get("priority_phase") == "P0" and not source.get("p0_exit_gates"):
            errors.append(f"P0 source requires p0_exit_gates: {source_id}")

    for artifact in manifest.get("artifact_rows", []):
        if not isinstance(artifact, dict):
            continue
        artifact_id = str(artifact.get("artifact_id", "") or "")
        source_id = str(artifact.get("source_id", "") or "")
        if source_id and source_id not in source_ids:
            errors.append(f"artifact references unknown source_id: {artifact_id} -> {source_id}")
        access = artifact.get("access_policy") if isinstance(artifact.get("access_policy"), dict) else {}
        classification = str(access.get("classification", "") or "")
        if classification in {"restricted", "unknown", "redacted"} and bool(access.get("redistribution_allowed", False)):
            errors.append(f"restricted artifacts cannot be marked redistribution_allowed: {artifact_id}")
        if artifact.get("retrieval_status") == "downloaded":
            if not artifact.get("sha256") or not artifact.get("bytes"):
                errors.append(f"downloaded artifacts require sha256 and bytes: {artifact_id}")
            if not artifact.get("file_inventory"):
                errors.append(f"downloaded artifacts require file_inventory: {artifact_id}")
    return errors


def _summary(manifest: dict[str, Any]) -> str:
    sources = [row for row in manifest.get("source_families", []) if isinstance(row, dict)]
    p0_sources = [row for row in sources if row.get("priority_phase") == "P0"]
    p0_ready = [
        row
        for row in p0_sources
        if row.get("official_entrypoint_url") and row.get("access_policy") and row.get("p0_exit_gates")
    ]
    return (
        "Real project corpus manifest OK | "
        f"sources={len(sources)} | "
        f"p0_ready_sources={len(p0_ready)}/{len(p0_sources)} | "
        f"artifacts={len(manifest.get('artifact_rows', []))}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--show-summary", action="store_true")
    args = parser.parse_args()

    schema = _load_json(args.schema)
    manifest = _load_json(args.manifest)
    errors = validate_manifest(manifest, schema)
    if errors:
        print("Real project corpus manifest failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    if args.show_summary:
        print(_summary(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
