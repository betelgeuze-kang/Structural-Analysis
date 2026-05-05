#!/usr/bin/env python3
"""Write a compact index for release publication evidence artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "release-publication-evidence-index.v1"


def _load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _file_entry(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": "", "exists": False, "bytes": 0}
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() else 0,
    }


def build_index(
    *,
    manifest: Path,
    release_assets_json: Path,
    artifact_root: Path,
    upload_plan_json: Path,
    metadata_preflight_json: Path,
    p0_status_json: Path,
    p0_status_md: Path | None = None,
    publication_report_json: Path | None = None,
    promoted_manifest_json: Path | None = None,
    post_publish_roundtrip_json: Path | None = None,
    tag_ref_present: bool = True,
) -> dict[str, Any]:
    manifest_payload = _load_json(manifest)
    p0_payload = _load_json(p0_status_json)
    publication_payload = _load_json(publication_report_json)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_tag": str(manifest_payload.get("release_tag", "") or ""),
        "tag_ref_present": bool(tag_ref_present),
        "p0_closed": bool(p0_payload.get("p0_closed", False)),
        "release_publication_closed": bool(p0_payload.get("release_publication_closed", False)),
        "core_evidence_closed": bool(p0_payload.get("core_evidence_closed", False)),
        "job_status": str(publication_payload.get("job_status", "") or ""),
        "paths": {
            "manifest": str(manifest),
            "promoted_manifest_json": str(promoted_manifest_json) if promoted_manifest_json else "",
            "release_assets_json": str(release_assets_json),
            "artifact_root": str(artifact_root),
            "upload_plan_json": str(upload_plan_json),
            "metadata_preflight_json": str(metadata_preflight_json),
            "p0_status_json": str(p0_status_json),
            "p0_status_md": str(p0_status_md) if p0_status_md else "",
            "publication_report_json": str(publication_report_json) if publication_report_json else "",
            "post_publish_roundtrip_json": str(post_publish_roundtrip_json) if post_publish_roundtrip_json else "",
        },
        "files": {
            "manifest": _file_entry(manifest),
            "promoted_manifest_json": _file_entry(promoted_manifest_json),
            "release_assets_json": _file_entry(release_assets_json),
            "artifact_root": _file_entry(artifact_root),
            "upload_plan_json": _file_entry(upload_plan_json),
            "metadata_preflight_json": _file_entry(metadata_preflight_json),
            "p0_status_json": _file_entry(p0_status_json),
            "p0_status_md": _file_entry(p0_status_md),
            "publication_report_json": _file_entry(publication_report_json),
            "post_publish_roundtrip_json": _file_entry(post_publish_roundtrip_json),
        },
        "handoff_commands": {
            "p0_status": [
                "python3",
                "scripts/check_p0_closure_status.py",
                "--publication-evidence-index",
                "<release-publication-evidence-index.json>",
                "--json",
            ],
            "p1_readiness": [
                "python3",
                "scripts/check_p1_readiness_status.py",
                "--p0-status",
                str(p0_status_json),
                "--json",
            ],
            "clean_checkout_chain": [
                "python3",
                "scripts/materialize_clean_checkout_evidence_chain.py",
                "--publication-evidence-index",
                "<release-publication-evidence-index.json>",
                "--json",
            ],
            "post_publish_roundtrip": [
                "python3",
                "scripts/hydrate_github_release_assets.py",
                "--repo",
                "<owner/repo>",
                "--manifest",
                str(manifest),
                "--artifact-root",
                "<hydrated-release-root>",
                "--write",
                "--out",
                "<post-publish-roundtrip.json>",
            ],
        },
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--promoted-manifest-json", type=Path)
    parser.add_argument("--release-assets-json", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--upload-plan-json", type=Path, required=True)
    parser.add_argument("--metadata-preflight-json", type=Path, required=True)
    parser.add_argument("--p0-status-json", type=Path, required=True)
    parser.add_argument("--p0-status-md", type=Path)
    parser.add_argument("--publication-report-json", type=Path)
    parser.add_argument("--post-publish-roundtrip-json", type=Path)
    parser.add_argument("--tag-ref-present", action="store_true", default=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_index(
        manifest=args.manifest,
        promoted_manifest_json=args.promoted_manifest_json,
        release_assets_json=args.release_assets_json,
        artifact_root=args.artifact_root,
        upload_plan_json=args.upload_plan_json,
        metadata_preflight_json=args.metadata_preflight_json,
        p0_status_json=args.p0_status_json,
        p0_status_md=args.p0_status_md,
        publication_report_json=args.publication_report_json,
        post_publish_roundtrip_json=args.post_publish_roundtrip_json,
        tag_ref_present=bool(args.tag_ref_present),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
