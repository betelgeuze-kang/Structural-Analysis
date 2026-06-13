#!/usr/bin/env python3
"""Build a G7 review packet for source-native direct download actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from implementation.phase1.open_data.korea import build_operator_attachment_manifest_queue


DEFAULT_REVIEW_OUT = (
    build_operator_attachment_manifest_queue.ingest.KOREA_DIR
    / "operator_attachment_direct_download_review.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _is_specific_remote_download(url_text: str) -> bool:
    parsed = urlparse(str(url_text or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.rstrip("/")
    if not path:
        return False
    return bool(parsed.query) or "." in Path(path).name


def build_operator_direct_download_review(
    *,
    queue_path: Path = build_operator_attachment_manifest_queue.DEFAULT_QUEUE_OUT,
) -> dict[str, Any]:
    queue = _load_json(queue_path)
    attachments = queue.get("attachments")
    rows = [row for row in attachments if isinstance(row, dict)] if isinstance(attachments, list) else []
    direct_rows = [
        row for row in rows if _is_specific_remote_download(str(row.get("download_url") or ""))
    ]
    portal_rows = [
        row
        for row in rows
        if str(row.get("download_url") or row.get("provenance_url") or "").startswith(
            ("http://", "https://")
        )
        and row not in direct_rows
    ]
    direct_downloads = [
        {
            "source_id": str(row.get("source_id") or ""),
            "action_type": str(row.get("action_type") or ""),
            "file_type": str(row.get("file_type") or ""),
            "download_url": str(row.get("download_url") or ""),
            "provenance_url": str(row.get("provenance_url") or ""),
            "license_hint": str(row.get("license_hint") or ""),
            "local_path": str(row.get("local_path") or ""),
            "target_directory": str(row.get("target_directory") or ""),
            "acceptance_checks": list(row.get("acceptance_checks") or []),
            "source_native_artifact_candidate": True,
            "rights_confirmed": False,
            "raw_redistribution_allowed": False,
            "countable_after_operator_manifest": False,
            "next_step": "download_to_local_path_then_confirm_document_level_rights",
        }
        for row in direct_rows
    ]
    operator_manifest_prefill_rows = [
        {
            "source_id": row["source_id"],
            "local_path": row["local_path"],
            "file_type": row["file_type"],
            "rights_confirmed": False,
            "source_native_artifact": False,
            "provenance_url": row["provenance_url"],
            "license_hint": row["license_hint"],
            "operator_note": (
                "Specific official download URL exists. Do not set rights_confirmed "
                "or source_native_artifact until the artifact is downloaded, matched "
                "to this source, and document-level rights review is complete."
            ),
        }
        for row in direct_downloads
    ]
    status = "pending_rights_review" if direct_downloads else "no_direct_download_actions"
    return {
        "schema_version": "korean-medium-large-operator-direct-download-review.v1",
        "queue_path": str(queue_path),
        "status": status,
        "specific_remote_download_action_count": int(len(direct_downloads)),
        "portal_landing_action_count": int(len(portal_rows)),
        "direct_download_source_ids": [row["source_id"] for row in direct_downloads],
        "direct_downloads": direct_downloads,
        "operator_manifest_prefill_rows": operator_manifest_prefill_rows,
        "raw_download_policy": "no_automatic_http_downloads_without_document_level_rights_review",
        "claim_boundary": (
            "This review packet identifies official direct-download actions only. It "
            "does not download raw files, confirm rights, or count rows as G7 corpus "
            "evidence. Rows become countable only through an accepted "
            "operator_attachment_manifest.json overlay and replayed ingest checks."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--queue",
        type=Path,
        default=build_operator_attachment_manifest_queue.DEFAULT_QUEUE_OUT,
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REVIEW_OUT)
    parser.add_argument("--show-summary", action="store_true")
    args = parser.parse_args()

    payload = build_operator_direct_download_review(queue_path=args.queue)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.show_summary:
        print(
            "operator-direct-download-review: "
            f"status={payload['status']} "
            f"direct={payload['specific_remote_download_action_count']} "
            f"portal={payload['portal_landing_action_count']} -> {args.out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
