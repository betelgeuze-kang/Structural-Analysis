#!/usr/bin/env python3
"""Compare clean-runner Frame Alpha replay receipts from Linux and Windows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Sequence


SCHEMA_VERSION = "structural-frame-alpha-clean-install-cross-platform.v1"
REPLAY_SCHEMA = "structural-frame-alpha-clean-install-replay.v1"
PLATFORMS = ("linux-x86_64-gnu", "windows-x86_64-msvc")
IDENTITY_FIELDS = (
    "schema_version",
    "authority_profile",
    "result_hash",
    "model_content_hash",
    "model_semantic_hash",
    "model_provenance_hash",
    "load_pattern_id",
    "load_combination_id",
    "native_abi_version",
    "solver",
    "node_count",
    "member_count",
    "canonical_result_sha256",
)


class CrossPlatformReplayError(RuntimeError):
    """Raised when the two clean-runner receipts are incomplete or divergent."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _load_object(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CrossPlatformReplayError(f"invalid_receipt:{path}") from error
    if not isinstance(payload, dict):
        raise CrossPlatformReplayError(f"receipt_must_be_object:{path}")
    return payload, raw


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise CrossPlatformReplayError(f"output_must_not_exist:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def compare_replays(
    *, receipt_paths: list[Path], expected_source_commit: str
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", expected_source_commit) is None:
        raise CrossPlatformReplayError("expected_source_commit_invalid")
    rows: dict[str, dict[str, Any]] = {}
    receipt_hashes: dict[str, str] = {}
    for path in receipt_paths:
        payload, raw = _load_object(path)
        platform = payload.get("platform_tag")
        source = payload.get("source")
        runner = payload.get("runner")
        replay = payload.get("analysis_replay")
        if (
            payload.get("schema_version") != REPLAY_SCHEMA
            or payload.get("status") != "pass"
            or platform not in PLATFORMS
            or platform in rows
            or not isinstance(source, dict)
            or source.get("commit_sha") != expected_source_commit
            or not isinstance(runner, dict)
            or runner.get("profile") != "github_hosted_ephemeral"
            or runner.get("fresh_extraction_directory") is not True
            or runner.get("source_build_output_used") is not False
            or not isinstance(replay, dict)
            or replay.get("repeat_count") != 2
            or replay.get("byte_identical") is not True
        ):
            raise CrossPlatformReplayError(f"receipt_contract_invalid:{path}")
        rows[str(platform)] = payload
        receipt_hashes[str(platform)] = _sha256_bytes(raw)
    if set(rows) != set(PLATFORMS):
        raise CrossPlatformReplayError("platform_coordinate_set_mismatch")

    linux = rows[PLATFORMS[0]]
    windows = rows[PLATFORMS[1]]
    if linux["source"] != windows["source"]:
        raise CrossPlatformReplayError("source_binding_mismatch")
    linux_replay = linux["analysis_replay"]
    windows_replay = windows["analysis_replay"]
    matching = {
        field: linux_replay.get(field) == windows_replay.get(field)
        for field in IDENTITY_FIELDS
    }
    mismatched = [field for field, matched in matching.items() if not matched]
    if mismatched:
        raise CrossPlatformReplayError(
            "cross_platform_result_mismatch:" + ",".join(mismatched)
        )

    coordinates = {
        platform: {
            "receipt_sha256": receipt_hashes[platform],
            "archive_sha256": rows[platform]["archive"]["sha256"],
            "manifest_hash": rows[platform]["archive"]["manifest_hash"],
            "package_id": rows[platform]["archive"]["package_id"],
        }
        for platform in PLATFORMS
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "source": linux["source"],
        "coordinates": coordinates,
        "matching": matching,
        "analysis_identity": {field: linux_replay[field] for field in IDENTITY_FIELDS},
        "authority": {
            "linux_portable_clean_runner_installation": "passed",
            "windows_portable_clean_runner_installation": "passed",
            "same_source_linux_windows_result_parity": "passed",
            "browser_execution": "not_evaluated",
            "os_code_signing": "not_evaluated",
            "current_main_artifact_attestation": "separate_workflow_job_required",
            "automatic_update": "not_implemented",
            "rollback": "not_implemented",
            "engineering_design": "not_authoritative",
            "commercial_use": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "same_source_frame_alpha_portable_archives_replayed_from_fresh_linux_and_"
            "windows_github_hosted_extractions_with_byte_identical_result_ir_not_browser_"
            "code_signing_update_rollback_commercial_or_release_authority"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, action="append", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        payload = compare_replays(
            receipt_paths=arguments.receipt,
            expected_source_commit=arguments.expected_source_commit,
        )
        _write_new(arguments.output, payload)
    except (CrossPlatformReplayError, OSError) as error:
        print(f"Frame Alpha cross-platform replay failed: {error}", file=sys.stderr)
        return 1
    print(_canonical_bytes(payload).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
