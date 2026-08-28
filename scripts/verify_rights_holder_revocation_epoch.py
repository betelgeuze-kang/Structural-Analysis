#!/usr/bin/env python3
"""Verify the independently pinned, signed latest release revocation epoch."""

from __future__ import annotations

import argparse
import base64
import binascii
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Mapping

sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_rights_holder_license_decision import (  # noqa: E402
    MAX_AUTHORITY_FILE_BYTES,
    REPOSITORY_ID,
    _load_object_bytes,
    _trusted_openssl_signature_inspection,
    sha256_bytes,
)


SCHEMA_VERSION = "rights-holder-revocation-epoch.v1"
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def canonical_revocation_epoch_bytes(payload: Mapping[str, Any]) -> bytes:
    signed = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(
        signed,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_pinned_file(path: Path) -> tuple[bytes, str]:
    """Read one owner-controlled regular file without following any path symlink."""

    if not path.is_absolute() or not hasattr(os, "O_NOFOLLOW"):
        return b"", "path_not_absolute_or_nofollow_unavailable"
    descriptors: list[int] = []
    try:
        parts = path.parts
        directory_fd = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(directory_fd)
        for part in parts[1:-1]:
            directory_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            descriptors.append(directory_fd)
        file_fd = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_fd,
        )
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid not in {0, os.geteuid()}
            or before.st_mode & 0o022
            or before.st_size > MAX_AUTHORITY_FILE_BYTES
        ):
            return b"", "unsafe_type_owner_permissions_or_size"
        payload = bytearray()
        while len(payload) <= MAX_AUTHORITY_FILE_BYTES:
            chunk = os.read(file_fd, min(64 * 1024, MAX_AUTHORITY_FILE_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        after = os.fstat(file_fd)
        stable = all(
            getattr(before, field) == getattr(after, field)
            for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        )
        if not stable or len(payload) != before.st_size or len(payload) > MAX_AUTHORITY_FILE_BYTES:
            return b"", "changed_or_oversize"
        return bytes(payload), "ok"
    except (OSError, UnicodeError, ValueError):
        return b"", "unreadable_or_symlinked"
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _parse_utc(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def _valid_id_list(value: Any, *, minimum: int) -> bool:
    return bool(
        isinstance(value, list)
        and all(isinstance(item, str) and len(item) >= minimum for item in value)
        and len(value) == len(set(value))
    )


def inspect_rights_holder_revocation_epoch(
    *,
    epoch_path: Path,
    public_key_path: Path,
    expected_epoch_sha256: str,
    expected_public_key_sha256: str,
    expected_minimum_epoch: int,
    expected_default_branch: str,
    expected_default_branch_head: str,
    decision_id: str,
    decision_signer_id: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    epoch_bytes, epoch_status = _read_pinned_file(epoch_path)
    key_bytes, key_status = _read_pinned_file(public_key_path)
    epoch_file_sha256 = sha256_bytes(epoch_bytes) if epoch_bytes else ""
    public_key_sha256 = sha256_bytes(key_bytes) if key_bytes else ""
    if epoch_status != "ok":
        blockers.append(f"revocation_epoch_{epoch_status}")
    if key_status != "ok":
        blockers.append(f"revocation_public_key_{key_status}")
    if not _SHA256.fullmatch(expected_epoch_sha256 or ""):
        blockers.append("revocation_epoch_expected_hash_invalid")
    elif epoch_file_sha256 != expected_epoch_sha256:
        blockers.append("revocation_epoch_hash_mismatch")
    if not _SHA256.fullmatch(expected_public_key_sha256 or ""):
        blockers.append("revocation_public_key_expected_hash_invalid")
    elif public_key_sha256 != expected_public_key_sha256:
        blockers.append("revocation_public_key_hash_mismatch")

    epoch = _load_object_bytes(epoch_bytes)
    signature = epoch.get("signature") if isinstance(epoch.get("signature"), dict) else {}
    exact_keys = {
        "schema_version",
        "repository_id",
        "epoch",
        "issued_at_utc",
        "default_branch",
        "default_branch_commit_sha",
        "signer_id",
        "previous_epoch_sha256",
        "revoked_signer_ids",
        "revoked_decision_ids",
        "claim_boundary",
        "signature",
    }
    shape_pass = bool(
        set(epoch) == exact_keys
        and epoch.get("schema_version") == SCHEMA_VERSION
        and epoch.get("repository_id") == REPOSITORY_ID
        and isinstance(epoch.get("epoch"), int)
        and not isinstance(epoch.get("epoch"), bool)
        and epoch.get("epoch", 0) >= 1
        and isinstance(epoch.get("signer_id"), str)
        and len(epoch.get("signer_id", "")) >= 3
        and isinstance(epoch.get("claim_boundary"), str)
        and len(epoch.get("claim_boundary", "")) >= 80
        and _valid_id_list(epoch.get("revoked_signer_ids"), minimum=3)
        and _valid_id_list(epoch.get("revoked_decision_ids"), minimum=8)
        and set(signature) == {"algorithm", "signed_payload_sha256", "value_base64"}
        and signature.get("algorithm") == "rsa-sha256"
    )
    if not shape_pass:
        blockers.append("revocation_epoch_schema_invalid")

    branch_binding_pass = bool(
        expected_default_branch == "main"
        and epoch.get("default_branch") == expected_default_branch
        and _SOURCE_SHA.fullmatch(expected_default_branch_head or "")
        and epoch.get("default_branch_commit_sha") == expected_default_branch_head
    )
    if not branch_binding_pass:
        blockers.append("revocation_epoch_default_branch_binding_mismatch")
    epoch_number_pass = bool(
        isinstance(expected_minimum_epoch, int)
        and expected_minimum_epoch >= 1
        and isinstance(epoch.get("epoch"), int)
        and not isinstance(epoch.get("epoch"), bool)
        and epoch.get("epoch", 0) >= expected_minimum_epoch
    )
    if not epoch_number_pass:
        blockers.append("revocation_epoch_rollback_detected")
    issued_at = _parse_utc(epoch.get("issued_at_utc"))
    if issued_at is None or issued_at > datetime.now(timezone.utc):
        blockers.append("revocation_epoch_time_invalid")
    previous = epoch.get("previous_epoch_sha256")
    if not isinstance(previous, str) or (previous and not _SHA256.fullmatch(previous)):
        blockers.append("revocation_epoch_previous_hash_invalid")

    signed_bytes = b""
    signed_payload_sha256 = ""
    try:
        signed_bytes = canonical_revocation_epoch_bytes(epoch)
        signed_payload_sha256 = sha256_bytes(signed_bytes)
    except (TypeError, UnicodeError, ValueError):
        blockers.append("revocation_epoch_canonical_payload_invalid")
    if signature.get("signed_payload_sha256") != signed_payload_sha256:
        blockers.append("revocation_epoch_signed_payload_hash_mismatch")
    try:
        signature_bytes = base64.b64decode(
            str(signature.get("value_base64") or ""),
            validate=True,
        )
    except (ValueError, binascii.Error):
        signature_bytes = b""
    if len(signature_bytes) > 16 * 1024:
        signature_bytes = b""
    signature_verified, key_bits, key_exponent = (False, 0, 0)
    if key_bytes and signature_bytes and signed_bytes:
        signature_verified, key_bits, key_exponent = _trusted_openssl_signature_inspection(
            public_key_bytes=key_bytes,
            signature_bytes=signature_bytes,
            signed_bytes=signed_bytes,
        )
    if not signature_verified:
        blockers.append("revocation_epoch_signature_not_verified")

    revoked_signer_ids = epoch.get("revoked_signer_ids")
    revoked_decision_ids = epoch.get("revoked_decision_ids")
    revoked_signer_set = (
        set(revoked_signer_ids)
        if isinstance(revoked_signer_ids, list)
        and all(isinstance(value, str) for value in revoked_signer_ids)
        else set()
    )
    revoked_decision_set = (
        set(revoked_decision_ids)
        if isinstance(revoked_decision_ids, list)
        and all(isinstance(value, str) for value in revoked_decision_ids)
        else set()
    )
    signer_revoked = decision_signer_id in revoked_signer_set
    decision_revoked = decision_id in revoked_decision_set
    if not decision_id or not decision_signer_id:
        blockers.append("revocation_epoch_decision_identity_missing")
    if signer_revoked:
        blockers.append("rights_holder_decision_signer_revoked_by_latest_epoch")
    if decision_revoked:
        blockers.append("rights_holder_decision_revoked_by_latest_epoch")
    blockers = sorted(set(blockers))
    return {
        "schema_version": "rights-holder-revocation-epoch-inspection.v1",
        "contract_pass": not blockers,
        "epoch": epoch.get("epoch") if isinstance(epoch.get("epoch"), int) else 0,
        "epoch_file_sha256": epoch_file_sha256,
        "public_key_sha256": public_key_sha256,
        "public_key_bits": key_bits,
        "public_key_exponent": key_exponent,
        "signature_verified": signature_verified,
        "branch_binding_pass": branch_binding_pass,
        "epoch_number_pass": epoch_number_pass,
        "decision_id": decision_id,
        "decision_signer_id": decision_signer_id,
        "decision_revoked": decision_revoked,
        "signer_revoked": signer_revoked,
        "release_authority": False,
        "blockers": blockers,
        "claim_boundary": (
            "This verifies only the independently release-environment-pinned latest "
            "revocation epoch and prevents an older source decision from bypassing a "
            "later revocation. It grants no license, redistribution, or release authority."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--epoch", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--expected-epoch-sha256", required=True)
    parser.add_argument("--expected-public-key-sha256", required=True)
    parser.add_argument("--expected-minimum-epoch", type=int, required=True)
    parser.add_argument("--expected-default-branch", required=True)
    parser.add_argument("--expected-default-branch-head", required=True)
    parser.add_argument("--decision-id", required=True)
    parser.add_argument("--decision-signer-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    if not (sys.flags.isolated and sys.flags.dont_write_bytecode):
        print("revocation epoch: BLOCKED | invoke with /usr/bin/python3 -I -B", file=sys.stderr)
        return 2
    args = build_parser().parse_args(argv)
    payload = inspect_rights_holder_revocation_epoch(
        epoch_path=args.epoch,
        public_key_path=args.public_key,
        expected_epoch_sha256=args.expected_epoch_sha256,
        expected_public_key_sha256=args.expected_public_key_sha256,
        expected_minimum_epoch=args.expected_minimum_epoch,
        expected_default_branch=args.expected_default_branch,
        expected_default_branch_head=args.expected_default_branch_head,
        decision_id=args.decision_id,
        decision_signer_id=args.decision_signer_id,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
