#!/usr/bin/env python3
"""Build a fill-in operator attachment manifest from the current G7 action queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from implementation.phase1 import run_korean_medium_large_ingest_pipeline as ingest  # noqa: E402


DEFAULT_QUEUE_OUT = ingest.KOREA_DIR / "operator_attachment_manifest.queue.json"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _expected_manifest_file(action: dict[str, Any]) -> str:
    source_id = str(action.get("source_id") or "")
    expected = [
        str(item)
        for item in action.get("expected_artifacts", [])
        if isinstance(item, str) and item
    ]
    action_format = str(action.get("format") or "").lower()
    if action_format == "mgt":
        suffixes = (".mgt",)
    elif action_format == "ifc":
        suffixes = (".ifc",)
    elif action_format == "zip":
        suffixes = (".zip", ".mgt")
    elif action_format == "pdf":
        suffixes = (".pdf", ".mgt")
    else:
        suffixes = ()
    for suffix in suffixes:
        for name in expected:
            if name.lower().endswith(suffix):
                return name
    if expected:
        return expected[0]
    suffix = f".{action_format}" if action_format else ""
    return f"{source_id}{suffix}"


def build_operator_attachment_manifest_queue(
    *,
    receipt_path: Path = ingest.DEFAULT_RECEIPT,
) -> dict[str, Any]:
    receipt = _load_json(receipt_path)
    queue = receipt.get("operator_action_queue")
    actions = [row for row in queue if isinstance(row, dict)] if isinstance(queue, list) else []
    attachments: list[dict[str, Any]] = []
    for action in actions:
        source_id = str(action.get("source_id") or "")
        target_directory = Path(str(action.get("target_directory") or ""))
        expected_file = _expected_manifest_file(action)
        local_path = target_directory / expected_file if expected_file else target_directory
        attachments.append(
            {
                "source_id": source_id,
                "local_path": str(local_path),
                "file_type": Path(expected_file).suffix.lower(),
                "rights_confirmed": False,
                "source_native_artifact": False,
                "provenance_url": str(action.get("provenance_url") or ""),
                "license_hint": str(action.get("license_hint") or ""),
                "operator_note": (
                    "Fill this path with the source-native artifact for this source, "
                    "then set rights_confirmed and source_native_artifact to true."
                ),
                "action_type": str(action.get("action_type") or ""),
                "download_url": str(action.get("download_url") or ""),
                "target_directory": str(action.get("target_directory") or ""),
                "acceptance_checks": list(action.get("acceptance_checks") or []),
                "current_attach_provenance": str(
                    action.get("current_attach_provenance") or ""
                ),
            }
        )
    action_packet = receipt.get("operator_action_packet")
    action_packet = action_packet if isinstance(action_packet, dict) else {}
    resolution_plan = action_packet.get("operator_resolution_plan")
    resolution_plan = resolution_plan if isinstance(resolution_plan, dict) else {}
    candidate_matrix_summary = action_packet.get("candidate_matrix_summary")
    candidate_matrix_summary = (
        candidate_matrix_summary if isinstance(candidate_matrix_summary, dict) else {}
    )
    priority_batches = resolution_plan.get("priority_batches")
    priority_batches = priority_batches if isinstance(priority_batches, list) else []
    auto_promotable = int(resolution_plan.get("auto_promotable_repo_candidate_count") or 0)
    autofill_candidate_status = (
        "exact_clean_repo_candidates_available"
        if auto_promotable > 0
        else "blocked_no_exact_clean_repo_candidate"
    )
    return {
        "schema_version": "korean-medium-large-operator-attachment-manifest.v1",
        "source_receipt_path": str(receipt_path),
        "status": "pending_operator_fill" if attachments else "ready",
        "attachment_count": int(len(attachments)),
        "attachments": attachments,
        "autofill_candidate_status": autofill_candidate_status,
        "auto_promotable_repo_candidate_count": auto_promotable,
        "minimum_operator_real_mgt_needed": int(
            resolution_plan.get("minimum_operator_real_mgt_needed") or 0
        ),
        "source_mapping_blocked_action_count": int(
            resolution_plan.get("source_mapping_blocked_action_count") or 0
        ),
        "rights_blocked_private_candidate_action_count": int(
            resolution_plan.get("rights_blocked_private_candidate_action_count") or 0
        ),
        "candidate_matrix_summary": candidate_matrix_summary,
        "priority_batches": priority_batches,
        "operator_resolution_plan": resolution_plan,
        "claim_boundary": (
            "This queue is a fill-in manifest. Rows are intentionally not accepted "
            "until the operator attaches the artifact and confirms rights/source-native "
            "provenance. Repo-local candidates are not auto-filled when no exact clean "
            "candidate exists or when source mapping, rights, or benchmark-bridge checks "
            "remain open."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, default=ingest.DEFAULT_RECEIPT)
    parser.add_argument("--out", type=Path, default=DEFAULT_QUEUE_OUT)
    parser.add_argument("--show-summary", action="store_true")
    args = parser.parse_args()

    payload = build_operator_attachment_manifest_queue(receipt_path=args.receipt)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.show_summary:
        print(
            "operator-attachment-queue: "
            f"attachments={payload['attachment_count']} "
            f"status={payload['status']} -> {args.out}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
