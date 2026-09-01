#!/usr/bin/env python3
"""Build an exact-main index from five authenticated technical handoff pairs.

This is a technical evidence consumer, not a promotion tool.  It authenticates
GitHub run/artifact identities and Sigstore subjects before delegating byte-level
pair recombination to ``verify_technical_evidence_handoff_pair.py``.  Every
scientific, legal, engineering, commercial, and release authority remains false.
"""

from __future__ import annotations

import argparse
import binascii
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import time
from typing import Any, NoReturn, Sequence
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path("canonical/current-main-evidence-lanes.v1.json")
CATALOG_SCHEMA_PATH = Path("canonical/current-main-evidence-lanes.v1.schema.json")
INDEX_SCHEMA_PATH = Path("canonical/current-main-evidence-index.v1.schema.json")
PAIR_VERIFIER_PATH = Path("scripts/verify_technical_evidence_handoff_pair.py")
GENERATOR_WORKFLOW_PATH = ".github/workflows/current-main-evidence-index.yml"
ATTESTOR_WORKFLOW_PATH = ".github/workflows/_technical-evidence-attest.yml"
PRODUCT_STATE_WORKFLOW_PATH = ".github/workflows/product-state-current.yml"
NIGHTLY_WORKFLOW_PATH = ".github/workflows/nightly-full-quality.yml"
ISSUE_STATE_WORKFLOW_PATH = ".github/workflows/issue-state-current.yml"
ISSUE_STATE_SCHEMA_PATH = Path("canonical/issue-state-current.v1.schema.json")
ISSUE_STATE_INVENTORY_PATH = Path(
    "artifacts/manifests/issue_supersession_inventory.json"
)
ISSUE_STATE_VALIDATOR_PATH = Path("scripts/check_issue_supersession_inventory.py")
ISSUE_STATE_REPORT_PATH = PurePosixPath("issue-state-current.json")
ISSUE_STATE_BUNDLE_FILES = (
    ISSUE_STATE_WORKFLOW_PATH,
    ISSUE_STATE_INVENTORY_PATH.as_posix(),
    ISSUE_STATE_SCHEMA_PATH.as_posix(),
    ISSUE_STATE_REPORT_PATH.as_posix(),
    ISSUE_STATE_VALIDATOR_PATH.as_posix(),
)
ISSUE_STATE_CLAIM_BOUNDARY = (
    "This inventory and live report describe GitHub issue-state hygiene only. "
    "They do not prove solver accuracy, external V&V, design authority, legal "
    "rights, commercial authority, release eligibility, or product readiness."
)
ISSUE_STATE_FALSE_AUTHORITY = {
    "commercial_authority": False,
    "design_authority": False,
    "external_validation_authority": False,
    "numerical_authority": False,
    "release_authority": False,
}
ISSUE_STATE_MAX_POLL_ATTEMPTS = 20
ISSUE_STATE_POLL_INTERVAL_SECONDS = 15
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_API_BYTES = 10_000_000
MAX_ARCHIVE_BYTES = 300_000_000
MAX_ARCHIVE_MEMBERS = 192
MAX_FILE_BYTES = 100_000_000
MAX_UNCOMPRESSED_BYTES = 300_000_000
MAX_COMPRESSION_RATIO = 200
MAX_PRODUCT_STATE_ARTIFACT_BYTES = 1_200_000_000
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CLAIM_BOUNDARY = (
    "authenticated_exact_main_same_operator_technical_pairs_only_"
    "leaf_signature_roots_retained_"
    "full_pair_recombination_depends_on_upstream_artifact_retention_"
    "no_scientific_legal_engineering_commercial_or_release_promotion"
)
LANE_IDS = ("medium", "ifc", "mgt9", "mgt10", "native")
PRODUCT_STATE_ROOT_FILES = (
    "candidate-seal.json",
    "candidate-seal.replay-verification.json",
    "candidate-seal.sigstore.json",
    "candidate-seal.verification.json",
    "final-verification.json",
    "overlay-seal.json",
    "overlay.final-verification.json",
    "overlay.privileged-verification.json",
    "overlay.replay-verification.json",
    "overlay.sigstore.json",
    "product-state.embedded-verification.json",
    "product-state.json",
    "product-state.replay-verification.json",
    "product-state.sigstore.json",
    "provenance.embedded-verification.json",
    "provenance.json",
    "provenance.replay-verification.json",
    "provenance.sigstore.json",
)
UPSTREAM_BUNDLE_PREFIX = ".ci/current-main-evidence-bundle/upstream"
CONTRACT_FILES = (
    ".github/workflows/_technical-evidence-attest.yml",
    ".github/workflows/current-main-evidence-index.yml",
    ".github/workflows/ifc-import-health-current-source.yml",
    ".github/workflows/issue-state-current.yml",
    ".github/workflows/medium-scale-current-source.yml",
    ".github/workflows/mgt-import-health-current-source.yml",
    ".github/workflows/mgt-import-health-tenth-source.yml",
    ".github/workflows/native-frame-alpha-clean-install.yml",
    ".github/workflows/nightly-full-quality.yml",
    ".github/workflows/product-state-current.yml",
    "canonical/current-main-evidence-index.v1.schema.json",
    "canonical/current-main-evidence-lanes.v1.json",
    "canonical/current-main-evidence-lanes.v1.schema.json",
    "canonical/technical-evidence-handoff-pair.v1.schema.json",
    "scripts/verify_technical_evidence_handoff_pair.py",
)
LANE_TRUST_ROOTS: dict[str, dict[str, str]] = {
    "medium": {
        "category": "medium_scale",
        "workflow_name": "Medium Scale Current Source",
        "workflow_path": ".github/workflows/medium-scale-current-source.yml",
        "subject_path": "artifacts/medium-scale/current-source/medium-scale-execution.v1.json",
        "subject_schema_version": "medium-scale-current-source-execution.v1",
        "subject_source_key": "source_commit_sha",
    },
    "ifc": {
        "category": "import_health",
        "workflow_name": "IFC Import Health Current Source",
        "workflow_path": ".github/workflows/ifc-import-health-current-source.yml",
        "subject_path": ".ci/ifc-import-health-current-source/technical-receipt.json",
        "subject_schema_version": "ifc-import-health-current-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "mgt9": {
        "category": "import_health",
        "workflow_name": "MGT Import Health Current Source",
        "workflow_path": ".github/workflows/mgt-import-health-current-source.yml",
        "subject_path": ".ci/mgt-import-health-current-source/technical-receipt.json",
        "subject_schema_version": "mgt-import-health-current-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "mgt10": {
        "category": "import_health",
        "workflow_name": "MGT Import Health Tenth Source",
        "workflow_path": ".github/workflows/mgt-import-health-tenth-source.yml",
        "subject_path": ".ci/mgt-import-health-tenth-source/technical-receipt.json",
        "subject_schema_version": "mgt-import-health-tenth-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "native": {
        "category": "distribution",
        "workflow_name": "Native Frame Alpha Clean Install",
        "workflow_path": ".github/workflows/native-frame-alpha-clean-install.yml",
        "subject_path": "native-clean-install-summary.json",
        "subject_schema_version": "technical-native-clean-install-handoff.v1",
        "subject_source_key": "source_sha",
    },
}
LANE_POLICY_ROOTS: dict[str, dict[str, Any]] = {
    "medium": {
        "allowed_events": ["push"],
        "technical_scope": (
            "Five bounded same-operator medium-scale executions and internal "
            "oracle comparisons."
        ),
        "authority_not_granted": [
            "scientific_validation",
            "native_medium_product",
            "engineering_design",
            "commercial_use",
            "release",
        ],
        "promotion_blockers": [
            "scientific_medium_reference_missing",
            "native_medium_authority_missing",
        ],
    },
    "ifc": {
        "allowed_events": ["push"],
        "technical_scope": (
            "Ten-case IFC text import-health accounting with bounded "
            "silent-loss-zero checks."
        ),
        "authority_not_granted": [
            "solver_geometry",
            "independent_reproduction",
            "redistribution",
            "commercial_use",
            "engineering_design",
            "release",
        ],
        "promotion_blockers": [
            "independent_operator_missing",
            "legal_rights_missing",
        ],
    },
    "mgt9": {
        "allowed_events": ["push"],
        "technical_scope": (
            "Tracked MGT corpus technical nine-case accounting; this lane "
            "remains explicitly 9/10."
        ),
        "authority_not_granted": [
            "target_10_case_in_this_lane",
            "independent_reproduction",
            "redistribution",
            "commercial_use",
            "engineering_design",
            "release",
        ],
        "promotion_blockers": [
            "current_lane_is_intentionally_9_of_10",
            "legal_rights_missing",
        ],
    },
    "mgt10": {
        "allowed_events": ["push"],
        "technical_scope": (
            "Same-run MGT core nine plus runtime tenth-source technical accounting."
        ),
        "authority_not_granted": [
            "independent_reproduction",
            "redistribution",
            "commercial_use",
            "engineering_design",
            "release",
        ],
        "promotion_blockers": [
            "raw_tenth_source_not_retained",
            "legal_rights_missing",
            "independent_operator_missing",
        ],
    },
    "native": {
        "allowed_events": ["push", "workflow_dispatch"],
        "technical_scope": (
            "Bounded Linux/Windows portable package, clean-install, update, "
            "rollback, parity, and browser replay summary."
        ),
        "authority_not_granted": [
            "os_code_signing",
            "human_new_user",
            "independent_reproduction",
            "engineering_design",
            "commercial_use",
            "release",
        ],
        "promotion_blockers": [
            "os_code_signing_missing",
            "human_new_user_observation_missing",
        ],
    },
}


class EvidenceIndexError(RuntimeError):
    """Raised on any source, API, archive, attestation, or claim mismatch."""


def _fail(reason: str) -> NoReturn:
    raise EvidenceIndexError(reason)


def _require(condition: object, reason: str) -> None:
    if not condition:
        _fail(reason)


def _safe_positive_integer(value: Any, label: str) -> int:
    _require(
        type(value) is int and 1 <= value <= MAX_SAFE_INTEGER,
        f"safe_positive_integer_required:{label}",
    )
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        _require(key not in result, f"duplicate_json_key:{key}")
        result[key] = value
    return result


def _strict_integer(token: str, label: str) -> int:
    value = int(token)
    _require(abs(value) <= MAX_SAFE_INTEGER, f"unsafe_json_integer:{label}:{token}")
    return value


def _strict_float(token: str, label: str) -> float:
    value = float(token)
    _require(math.isfinite(value), f"nonfinite_json_number:{label}:{token}")
    return value


def _strict_json_bytes(raw: bytes, label: str) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_int=lambda token: _strict_integer(token, label),
            parse_float=lambda token: _strict_float(token, label),
            parse_constant=lambda token: _fail(
                f"nonfinite_json_number:{label}:{token}"
            ),
        )
    except EvidenceIndexError:
        raise
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise EvidenceIndexError(f"strict_json_invalid:{label}") from error


def _strict_json_object(raw: bytes, label: str) -> dict[str, Any]:
    value = _strict_json_bytes(raw, label)
    _require(type(value) is dict, f"json_object_required:{label}")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise EvidenceIndexError(f"file_unreadable:{label}") from error
    return _strict_json_object(raw, label)


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _pretty_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise EvidenceIndexError(f"file_hash_failed:{path}") from error
    return "sha256:" + digest.hexdigest()


def _write_new(path: Path, raw: bytes, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.is_symlink(), f"output_symlink_forbidden:{label}")
    try:
        with path.open("xb") as stream:
            stream.write(raw)
    except FileExistsError as error:
        raise EvidenceIndexError(f"output_exists:{label}") from error


def _write_json_new(path: Path, value: Any, label: str) -> bytes:
    raw = _pretty_bytes(value)
    _write_new(path, raw, label)
    return raw


def _safe_member_name(name: str, label: str) -> str:
    parts = name.split("/")
    path = PurePosixPath(name)
    _require(
        bool(name)
        and not name.startswith(("/", "./"))
        and not name.endswith("/")
        and "\\" not in name
        and "\x00" not in name
        and "" not in parts
        and "." not in parts
        and ".." not in parts
        and not path.is_absolute()
        and path.as_posix() == name
        and unicodedata.normalize("NFC", name) == name
        and 1 <= len(name) <= 2048
        and ":" not in name
        and all(
            unicodedata.category(character) not in {"Cc", "Cf"} for character in name
        ),
        f"unsafe_archive_member:{label}",
    )
    return name


def _inflate_raw_deflate(compressed: bytes, declared_size: int, label: str) -> bytes:
    inflater = zlib.decompressobj(-zlib.MAX_WBITS)
    output = bytearray()
    try:
        for offset in range(0, len(compressed), 64 * 1024):
            remaining = declared_size - len(output)
            _require(remaining >= 0, f"archive_expansion_invalid:{label}")
            output.extend(
                inflater.decompress(
                    compressed[offset : offset + 64 * 1024], remaining + 1
                )
            )
            _require(
                len(output) <= declared_size and not inflater.unconsumed_tail,
                f"archive_expansion_invalid:{label}",
            )
        output.extend(inflater.flush(declared_size - len(output) + 1))
    except zlib.error as error:
        raise EvidenceIndexError(f"archive_deflate_invalid:{label}") from error
    _require(
        inflater.eof
        and not inflater.unused_data
        and not inflater.unconsumed_tail
        and len(output) == declared_size,
        f"archive_expansion_invalid:{label}",
    )
    return bytes(output)


def _github_regular_attributes(external_attributes: int) -> bool:
    unix_mode = external_attributes >> 16
    permissions = unix_mode & 0o7777
    return (
        unix_mode & 0o170000 == 0o100000
        and external_attributes & 0xFFFF == 0x20
        and permissions & 0o400 != 0
        and permissions & ~0o666 == 0
    )


def strict_github_artifact_archive(raw: bytes, label: str) -> dict[str, bytes]:
    """Parse upload-artifact ZIP bytes without trusting ``zipfile`` extraction."""

    _require(22 <= len(raw) <= MAX_ARCHIVE_BYTES, f"archive_size_invalid:{label}")
    _require(raw[-22:-18] == b"PK\x05\x06", f"archive_eocd_missing:{label}")
    try:
        (
            signature,
            disk_number,
            directory_disk,
            disk_entries,
            total_entries,
            directory_size,
            directory_offset,
            comment_size,
        ) = struct.unpack_from("<4s4H2LH", raw, len(raw) - 22)
    except struct.error as error:
        raise EvidenceIndexError(f"archive_eocd_invalid:{label}") from error
    directory_end = directory_offset + directory_size
    _require(
        signature == b"PK\x05\x06"
        and disk_number == directory_disk == 0
        and disk_entries == total_entries
        and 0 < total_entries <= MAX_ARCHIVE_MEMBERS
        and comment_size == 0
        and directory_end == len(raw) - 22
        and directory_offset < directory_end,
        f"archive_eocd_invalid:{label}",
    )
    records: list[dict[str, Any]] = []
    cursor = directory_offset
    for _ in range(total_entries):
        _require(cursor + 46 <= directory_end, f"archive_central_invalid:{label}")
        try:
            central = struct.unpack_from("<4s6H3L5H2L", raw, cursor)
        except struct.error as error:
            raise EvidenceIndexError(f"archive_central_invalid:{label}") from error
        (
            central_signature,
            made_by,
            needed,
            flags,
            method,
            modified_time,
            modified_date,
            crc32,
            compressed_size,
            uncompressed_size,
            name_size,
            extra_size,
            member_comment_size,
            member_disk,
            internal_attributes,
            external_attributes,
            local_offset,
        ) = central
        name_start = cursor + 46
        name_end = name_start + name_size
        row_end = name_end + extra_size + member_comment_size
        _require(
            central_signature == b"PK\x01\x02"
            and row_end <= directory_end
            and name_size > 0
            and extra_size == member_comment_size == member_disk == 0
            and made_by == 0x032D
            and needed == 20
            and flags in {0x08, 0x808}
            and method == 8
            and internal_attributes == 0
            and _github_regular_attributes(external_attributes)
            and local_offset < directory_offset
            and compressed_size not in {0, 0xFFFFFFFF}
            and uncompressed_size not in {0, 0xFFFFFFFF}
            and local_offset != 0xFFFFFFFF,
            f"archive_central_invalid:{label}",
        )
        name_bytes = raw[name_start:name_end]
        try:
            name = name_bytes.decode("utf-8" if flags & 0x800 else "cp437")
        except UnicodeDecodeError as error:
            raise EvidenceIndexError(
                f"archive_member_encoding_invalid:{label}"
            ) from error
        name = _safe_member_name(name, label)
        _require(
            uncompressed_size <= MAX_FILE_BYTES
            and uncompressed_size <= compressed_size * MAX_COMPRESSION_RATIO,
            f"archive_member_size_invalid:{label}:{name}",
        )
        records.append(
            {
                "name": name,
                "name_bytes": name_bytes,
                "needed": needed,
                "flags": flags,
                "method": method,
                "modified_time": modified_time,
                "modified_date": modified_date,
                "crc32": crc32,
                "compressed_size": compressed_size,
                "uncompressed_size": uncompressed_size,
                "local_offset": local_offset,
            }
        )
        cursor = row_end
    _require(cursor == directory_end, f"archive_central_tail_invalid:{label}")

    values: dict[str, bytes] = {}
    aliases: set[str] = set()
    total_uncompressed = 0
    local_cursor = 0
    for row in sorted(records, key=lambda item: item["local_offset"]):
        _require(
            row["local_offset"] == local_cursor
            and local_cursor + 30 <= directory_offset,
            f"archive_local_offset_invalid:{label}",
        )
        try:
            local = struct.unpack_from("<4s5H3L2H", raw, local_cursor)
        except struct.error as error:
            raise EvidenceIndexError(f"archive_local_invalid:{label}") from error
        (
            local_signature,
            local_needed,
            local_flags,
            local_method,
            local_time,
            local_date,
            local_crc32,
            local_compressed_size,
            local_uncompressed_size,
            local_name_size,
            local_extra_size,
        ) = local
        name_start = local_cursor + 30
        name_end = name_start + local_name_size
        data_start = name_end + local_extra_size
        data_end = data_start + row["compressed_size"]
        descriptor_end = data_end + 16
        _require(
            local_signature == b"PK\x03\x04"
            and local_needed == row["needed"]
            and local_flags == row["flags"]
            and local_method == row["method"]
            and local_time == row["modified_time"]
            and local_date == row["modified_date"]
            and local_crc32 == local_compressed_size == local_uncompressed_size == 0
            and local_extra_size == 0
            and raw[name_start:name_end] == row["name_bytes"]
            and descriptor_end <= directory_offset,
            f"archive_local_invalid:{label}",
        )
        try:
            descriptor = struct.unpack_from("<4s3L", raw, data_end)
        except struct.error as error:
            raise EvidenceIndexError(f"archive_descriptor_invalid:{label}") from error
        _require(
            descriptor
            == (
                b"PK\x07\x08",
                row["crc32"],
                row["compressed_size"],
                row["uncompressed_size"],
            ),
            f"archive_descriptor_invalid:{label}",
        )
        value = _inflate_raw_deflate(
            raw[data_start:data_end], row["uncompressed_size"], label
        )
        _require(
            binascii.crc32(value) & 0xFFFFFFFF == row["crc32"],
            f"archive_crc_invalid:{label}:{row['name']}",
        )
        name = row["name"]
        alias = unicodedata.normalize("NFC", name).casefold()
        _require(
            name not in values and alias not in aliases,
            f"duplicate_archive_member:{label}:{name}",
        )
        values[name] = value
        aliases.add(alias)
        total_uncompressed += len(value)
        _require(
            total_uncompressed <= MAX_UNCOMPRESSED_BYTES,
            f"archive_total_size_invalid:{label}",
        )
        local_cursor = descriptor_end
    _require(local_cursor == directory_offset, f"archive_local_tail_invalid:{label}")
    for name, value in values.items():
        if name.endswith(".json"):
            _strict_json_bytes(value, f"{label}:{name}")
    return values


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self, request: Request, fp: Any, code: int, message: str, headers: Any, url: str
    ) -> None:
        return None


class GitHubApi:
    """Small authenticated REST client with an explicit artifact redirect boundary."""

    def __init__(self, repository: str, token: str) -> None:
        _require(REPOSITORY_RE.fullmatch(repository) is not None, "repository_invalid")
        _require(bool(token), "github_token_missing")
        self.repository = repository
        self.token = token
        self.root = f"https://api.github.com/repos/{repository}/"
        self.opener = build_opener(_NoRedirect())
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _api_url(self, endpoint: str) -> str:
        _require(
            bool(endpoint)
            and not endpoint.startswith(("/", "."))
            and "\\" not in endpoint
            and "\x00" not in endpoint,
            "api_endpoint_invalid",
        )
        url = self.root + endpoint
        parsed = urlsplit(url)
        _require(
            parsed.scheme == "https"
            and parsed.hostname == "api.github.com"
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and parsed.fragment == ""
            and parsed.path.startswith(f"/repos/{self.repository}/"),
            "api_url_invalid",
        )
        return url

    def json(self, endpoint: str, label: str) -> dict[str, Any]:
        url = self._api_url(endpoint)
        request = Request(url, headers=self.headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                _require(
                    response.status == 200
                    and response.geturl() == url
                    and response.headers.get("Location") is None,
                    f"api_response_identity_invalid:{label}",
                )
                raw = response.read(MAX_API_BYTES + 1)
        except HTTPError as error:
            raise EvidenceIndexError(f"api_http_error:{label}:{error.code}") from error
        except OSError as error:
            raise EvidenceIndexError(f"api_unavailable:{label}") from error
        _require(0 < len(raw) <= MAX_API_BYTES, f"api_response_size_invalid:{label}")
        return _strict_json_object(raw, f"api:{label}")

    def artifact_archive(self, artifact: dict[str, Any], label: str) -> bytes:
        artifact_id = _safe_positive_integer(artifact.get("id"), f"artifact_id:{label}")
        expected_url = self._api_url(f"actions/artifacts/{artifact_id}/zip")
        _require(
            artifact.get("archive_download_url") == expected_url,
            f"artifact_download_url_invalid:{label}",
        )
        request = Request(expected_url, headers=self.headers)
        try:
            self.opener.open(request, timeout=30)
            _fail(f"artifact_redirect_required:{label}")
        except HTTPError as error:
            _require(
                error.code in {301, 302, 303, 307, 308},
                f"artifact_redirect_status_invalid:{label}",
            )
            location = error.headers.get("Location")
        except OSError as error:
            raise EvidenceIndexError(
                f"artifact_redirect_unavailable:{label}"
            ) from error
        _require(
            type(location) is str and bool(location),
            f"artifact_location_missing:{label}",
        )
        parsed = urlsplit(location)
        hostname = parsed.hostname or ""
        _require(
            parsed.scheme == "https"
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and parsed.fragment == ""
            and (
                hostname.endswith(".blob.core.windows.net")
                or hostname.endswith(".actions.githubusercontent.com")
                or hostname.endswith(".githubusercontent.com")
            ),
            f"artifact_location_origin_invalid:{label}",
        )
        try:
            with self.opener.open(Request(location), timeout=60) as response:
                _require(
                    response.status == 200
                    and response.geturl() == location
                    and response.headers.get("Location") is None,
                    f"artifact_blob_identity_invalid:{label}",
                )
                raw = response.read(MAX_ARCHIVE_BYTES + 1)
        except OSError as error:
            raise EvidenceIndexError(
                f"artifact_blob_download_failed:{label}"
            ) from error
        _require(
            0 < len(raw) <= MAX_ARCHIVE_BYTES, f"artifact_archive_size_invalid:{label}"
        )
        _require(
            len(raw) == artifact["size_in_bytes"],
            f"artifact_api_size_mismatch:{label}",
        )
        _require(
            _sha256_bytes(raw) == artifact["digest"],
            f"artifact_api_digest_mismatch:{label}",
        )
        return raw


def _exact_keys(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    _require(type(value) is dict and set(value) == keys, f"object_keys_invalid:{label}")
    return value


def _load_catalog(source_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    catalog_path = source_root / CATALOG_PATH
    catalog = _read_json(catalog_path, "catalog")
    _exact_keys(
        catalog,
        {
            "schema_version",
            "catalog_id",
            "required_lane_count",
            "required_run_attempt",
            "technical_claims_only",
            "release_authority",
            "product_state_upstream",
            "issue_state_observation",
            "lanes",
        },
        "catalog",
    )
    _require(
        catalog["schema_version"] == "current-main-evidence-lanes.v1"
        and catalog["catalog_id"]
        == "current-main-authenticated-technical-handoff-pairs.v1"
        and type(catalog["required_lane_count"]) is int
        and catalog["required_lane_count"] == 5
        and type(catalog["required_run_attempt"]) is int
        and catalog["required_run_attempt"] == 1
        and catalog["technical_claims_only"] is True
        and catalog["release_authority"] is False,
        "catalog_header_invalid",
    )
    upstream = catalog["product_state_upstream"]
    _exact_keys(
        upstream,
        {
            "workflow_name",
            "workflow_path",
            "trigger",
            "exact_source_required",
            "successful_first_attempt_required",
            "required_jobs",
            "overlay_interface",
        },
        "catalog_product_state_upstream",
    )
    _require(
        type(upstream) is dict
        and upstream.get("workflow_name") == "Product State Current"
        and upstream.get("workflow_path")
        == ".github/workflows/product-state-current.yml"
        and upstream.get("trigger") == "workflow_run"
        and upstream.get("exact_source_required") is True
        and upstream.get("successful_first_attempt_required") is True
        and upstream.get("required_jobs")
        == [
            "build-current-state",
            "attest-current-state",
            "verify-current-state",
            "replay-final-attestations",
        ],
        "catalog_product_state_upstream_invalid",
    )
    overlay = upstream.get("overlay_interface")
    _require(
        type(overlay) is dict
        and _canonical_bytes(overlay)
        == _canonical_bytes(
            {
                "direction": "nightly_to_product_state_to_evidence_index",
                "version": "authenticated-product-state-overlay.v1",
                "consumption_enabled": True,
                "artifact_name_template": (
                    "post-main-evidence-overlay-attested-"
                    "{run_id}-{run_attempt}-{source_sha}"
                ),
            }
        ),
        "catalog_overlay_interface_invalid",
    )
    issue_state = catalog["issue_state_observation"]
    _exact_keys(
        issue_state,
        {
            "workflow_name",
            "workflow_path",
            "allowed_event",
            "exact_source_required",
            "successful_first_attempt_required",
            "required_jobs",
            "artifact_name_template",
            "bundle_files",
            "report_path",
            "inventory_path",
            "schema_path",
            "validator_path",
            "technical_lane",
            "promotion_eligible",
            "observation_scope",
        },
        "catalog_issue_state_observation",
    )
    _require(
        issue_state
        == {
            "workflow_name": "Issue State Current",
            "workflow_path": ISSUE_STATE_WORKFLOW_PATH,
            "allowed_event": "push",
            "exact_source_required": True,
            "successful_first_attempt_required": True,
            "required_jobs": ["offline-contract", "live-exact-main"],
            "artifact_name_template": (
                "issue-state-current-{source_sha}-{run_id}-{run_attempt}"
            ),
            "bundle_files": list(ISSUE_STATE_BUNDLE_FILES),
            "report_path": ISSUE_STATE_REPORT_PATH.as_posix(),
            "inventory_path": ISSUE_STATE_INVENTORY_PATH.as_posix(),
            "schema_path": ISSUE_STATE_SCHEMA_PATH.as_posix(),
            "validator_path": ISSUE_STATE_VALIDATOR_PATH.as_posix(),
            "technical_lane": False,
            "promotion_eligible": False,
            "observation_scope": "github_issue_state_hygiene_only",
        },
        "catalog_issue_state_observation_invalid",
    )
    lanes = catalog["lanes"]
    _require(type(lanes) is list and len(lanes) == 5, "catalog_lane_count_invalid")
    _require(
        tuple(row.get("lane_id") for row in lanes) == LANE_IDS,
        "catalog_lane_order_invalid",
    )
    catalog_schema = _read_json(
        source_root / CATALOG_SCHEMA_PATH, "catalog_schema"
    )
    schema_properties = catalog_schema.get("properties")
    _require(type(schema_properties) is dict, "catalog_schema_properties_invalid")
    lane_schema = _exact_keys(
        schema_properties.get("lanes"),
        {"type", "minItems", "maxItems", "prefixItems", "items"},
        "catalog_schema_lanes",
    )
    prefix_items = lane_schema.get("prefixItems")
    _require(
        lane_schema.get("type") == "array"
        and type(lane_schema.get("minItems")) is int
        and lane_schema.get("minItems") == 5
        and type(lane_schema.get("maxItems")) is int
        and lane_schema.get("maxItems") == 5
        and lane_schema.get("items") is False
        and type(prefix_items) is list
        and len(prefix_items) == 5,
        "catalog_schema_lane_topology_invalid",
    )
    schema_lane_constants = []
    for index, item in enumerate(prefix_items):
        item = _exact_keys(item, {"const"}, f"catalog_schema_lane:{index}")
        _require(
            type(item.get("const")) is dict,
            f"catalog_schema_lane_const_invalid:{index}",
        )
        schema_lane_constants.append(item["const"])
    _require(
        _canonical_bytes(schema_lane_constants) == _canonical_bytes(lanes),
        "catalog_schema_lane_constants_mismatch",
    )
    for row in lanes:
        lane_id = row["lane_id"]
        trust = LANE_TRUST_ROOTS[lane_id]
        policy = LANE_POLICY_ROOTS[lane_id]
        _exact_keys(
            row,
            {
                "lane_id",
                "category",
                "evidence_mode",
                "workflow_name",
                "workflow_path",
                "allowed_events",
                "producer_job",
                "attestor_job_suffix",
                "subject_path",
                "subject_schema_version",
                "subject_source_key",
                "handoff_name_template",
                "attestation_name_template",
                "technical_scope",
                "authority_not_granted",
                "promotion_blockers",
            },
            f"catalog_lane:{lane_id}",
        )
        _require(
            row.get("category") == trust["category"]
            and row.get("evidence_mode") == "handoff_pair"
            and row.get("workflow_name") == trust["workflow_name"]
            and row.get("workflow_path") == trust["workflow_path"]
            and row.get("producer_job") == "produce-unprivileged"
            and row.get("attestor_job_suffix")
            == "verify-attest-privileged-fresh-hosted"
            and row.get("subject_path") == trust["subject_path"]
            and row.get("subject_schema_version") == trust["subject_schema_version"]
            and row.get("subject_source_key") == trust["subject_source_key"]
            and row.get("handoff_name_template")
            == "{lane}-technical-handoff-{run_id}-{run_attempt}-{source_sha}"
            and row.get("attestation_name_template")
            == "{lane}-technical-handoff-{run_id}-{run_attempt}-{source_sha}-attestation"
            and _canonical_bytes(
                {
                    "allowed_events": row.get("allowed_events"),
                    "technical_scope": row.get("technical_scope"),
                    "authority_not_granted": row.get("authority_not_granted"),
                    "promotion_blockers": row.get("promotion_blockers"),
                }
            )
            == _canonical_bytes(policy),
            f"catalog_lane_contract_invalid:{lane_id}",
        )
    return catalog, lanes


def _blob_identity(api: GitHubApi, path: str, source_sha: str, label: str) -> str:
    endpoint = f"contents/{quote(path, safe='/')}?ref={source_sha}"
    payload = api.json(endpoint, f"source_blob:{label}")
    blob_sha = payload.get("sha")
    _require(
        payload.get("type") == "file"
        and payload.get("path") == path
        and type(blob_sha) is str
        and SHA1_RE.fullmatch(blob_sha) is not None
        and type(payload.get("size")) is int
        and 0 < payload["size"] <= MAX_API_BYTES,
        f"source_blob_identity_invalid:{label}",
    )
    return blob_sha


def _source_identity(api: GitHubApi, source_sha: str) -> tuple[str, str, str, str]:
    _require(SHA1_RE.fullmatch(source_sha) is not None, "source_sha_invalid")
    main = api.json("git/ref/heads/main", "main_ref")
    main_object = main.get("object")
    _require(
        main.get("ref") == "refs/heads/main"
        and type(main_object) is dict
        and main_object.get("type") == "commit"
        and main_object.get("sha") == source_sha,
        "exact_main_ref_mismatch",
    )
    commit = api.json(f"git/commits/{source_sha}", "source_commit")
    tree = commit.get("tree")
    _require(
        commit.get("sha") == source_sha
        and type(tree) is dict
        and type(tree.get("sha")) is str
        and SHA1_RE.fullmatch(tree["sha"]) is not None,
        "source_commit_identity_invalid",
    )
    attestor_blob = _blob_identity(api, ATTESTOR_WORKFLOW_PATH, source_sha, "attestor")
    generator_blob = _blob_identity(
        api, GENERATOR_WORKFLOW_PATH, source_sha, "generator"
    )
    product_state_blob = _blob_identity(
        api,
        ".github/workflows/product-state-current.yml",
        source_sha,
        "product_state",
    )
    return tree["sha"], attestor_blob, generator_blob, product_state_blob


def _validate_run_common(
    run: dict[str, Any],
    *,
    repository: str,
    source_sha: str,
    workflow_path: str,
    workflow_name: str,
    allowed_events: set[str],
    expected_run_id: int | None = None,
) -> int:
    run_id = _safe_positive_integer(run.get("id"), f"run_id:{workflow_name}")
    _safe_positive_integer(run.get("run_number"), f"run_number:{workflow_name}")
    if expected_run_id is not None:
        _require(run_id == expected_run_id, f"run_id_mismatch:{workflow_name}")
    head_repository = run.get("head_repository")
    _require(
        type(run.get("run_attempt")) is int
        and run.get("run_attempt") == 1
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("head_sha") == source_sha
        and run.get("head_branch") == "main"
        and run.get("path") == workflow_path
        and run.get("name") == workflow_name
        and run.get("event") in allowed_events
        and type(head_repository) is dict
        and head_repository.get("full_name") == repository,
        f"workflow_run_identity_invalid:{workflow_name}",
    )
    return run_id


def _validate_github_hosted_job(
    row: dict[str, Any],
    *,
    run_id: int,
    source_sha: str,
    allowed_runner_labels: set[str],
    label: str,
) -> int:
    job_id = _safe_positive_integer(row.get("id"), f"job_id:{label}")
    runner_id = _safe_positive_integer(row.get("runner_id"), f"runner_id:{label}")
    labels = row.get("labels")
    _require(
        type(row.get("run_id")) is int
        and row.get("run_id") == run_id
        and type(row.get("run_attempt")) is int
        and row.get("run_attempt") == 1
        and row.get("head_sha") == source_sha
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
        and type(labels) is list
        and len(labels) == 1
        and labels[0] in allowed_runner_labels
        and type(row.get("runner_group_id")) is int
        and row["runner_group_id"] == 0
        and row.get("runner_group_name") == "GitHub Actions"
        and row.get("runner_name") == f"GitHub Actions {runner_id}",
        f"github_hosted_job_identity_invalid:{label}",
    )
    return job_id


def _product_state_run(
    api: GitHubApi, source_sha: str, product_state_run_id: int
) -> dict[str, Any]:
    _safe_positive_integer(product_state_run_id, "product_state_run_id")
    workflow_path = ".github/workflows/product-state-current.yml"
    workflow_name = "Product State Current"
    workflow_file = quote(PurePosixPath(workflow_path).name, safe="")
    inventory = api.json(
        f"actions/workflows/{workflow_file}/runs?branch=main"
        f"&head_sha={source_sha}&per_page=100",
        "product_state_workflow_runs",
    )
    inventory_rows = inventory.get("workflow_runs")
    _require(
        type(inventory_rows) is list
        and len(inventory_rows) <= 100
        and all(type(row) is dict for row in inventory_rows)
        and type(inventory.get("total_count")) is int
        and inventory["total_count"] == len(inventory_rows),
        "product_state_workflow_run_inventory_invalid",
    )
    _require(
        len(inventory_rows) == 1,
        "product_state_unique_exact_source_run_required",
    )
    _validate_run_common(
        inventory_rows[0],
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=workflow_path,
        workflow_name=workflow_name,
        allowed_events={"workflow_run"},
        expected_run_id=product_state_run_id,
    )
    run = api.json(
        f"actions/runs/{product_state_run_id}/attempts/1", "product_state_run"
    )
    _validate_run_common(
        run,
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=workflow_path,
        workflow_name=workflow_name,
        allowed_events={"workflow_run"},
        expected_run_id=product_state_run_id,
    )
    run_refetch_fields = (
        "id",
        "run_number",
        "run_attempt",
        "status",
        "conclusion",
        "head_sha",
        "head_branch",
        "path",
        "name",
        "event",
    )
    _require(
        _canonical_bytes(
            {key: inventory_rows[0].get(key) for key in run_refetch_fields}
        )
        == _canonical_bytes({key: run.get(key) for key in run_refetch_fields}),
        "product_state_run_list_refetch_mismatch",
    )
    jobs = api.json(
        f"actions/runs/{product_state_run_id}/attempts/1/jobs?per_page=100",
        "product_state_jobs",
    )
    rows = jobs.get("jobs")
    _require(
        type(rows) is list
        and all(type(row) is dict for row in rows)
        and type(jobs.get("total_count")) is int
        and jobs.get("total_count") == len(rows)
        and len(rows) <= 100,
        "product_state_job_inventory_invalid",
    )
    required = {
        "build-current-state",
        "attest-current-state",
        "verify-current-state",
        "replay-final-attestations",
    }
    _require(
        len(rows) == 4
        and {row.get("name") for row in rows} == required
        and len({row.get("id") for row in rows}) == 4,
        "product_state_four_stage_success_required",
    )
    for row in rows:
        _validate_github_hosted_job(
            row,
            run_id=product_state_run_id,
            source_sha=source_sha,
            allowed_runner_labels={"ubuntu-latest"},
            label=f"product_state:{row['name']}",
        )
    return run


def _git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


def _select_issue_state_run(
    api: GitHubApi,
    issue_state: dict[str, Any],
    source_sha: str,
    *,
    max_poll_attempts: int = ISSUE_STATE_MAX_POLL_ATTEMPTS,
    poll_interval_seconds: int = ISSUE_STATE_POLL_INTERVAL_SECONDS,
    sleep: Any = time.sleep,
) -> dict[str, Any]:
    _require(
        type(max_poll_attempts) is int and 1 <= max_poll_attempts <= 120,
        "issue_state_poll_attempts_invalid",
    )
    _require(
        type(poll_interval_seconds) is int and 0 <= poll_interval_seconds <= 60,
        "issue_state_poll_interval_invalid",
    )
    workflow_file = quote(PurePosixPath(issue_state["workflow_path"]).name, safe="")
    for poll_attempt in range(1, max_poll_attempts + 1):
        payload = api.json(
            f"actions/workflows/{workflow_file}/runs?branch=main&event=push"
            f"&head_sha={source_sha}&per_page=100",
            f"issue_state_workflow_runs:poll:{poll_attempt}",
        )
        rows = payload.get("workflow_runs")
        _require(
            type(rows) is list
            and len(rows) <= 100
            and all(type(row) is dict for row in rows)
            and type(payload.get("total_count")) is int
            and payload["total_count"] == len(rows),
            "issue_state_workflow_run_inventory_invalid",
        )
        _require(
            len(rows) <= 1,
            "issue_state_unique_exact_source_push_run_required",
        )
        if rows:
            candidate = rows[0]
            _safe_positive_integer(
                candidate.get("run_number"), "issue_state_run_number"
            )
            _require(
                type(candidate.get("run_attempt")) is int
                and candidate.get("run_attempt") == 1
                and candidate.get("head_sha") == source_sha
                and candidate.get("head_branch") == "main"
                and candidate.get("path") == issue_state["workflow_path"]
                and candidate.get("name") == issue_state["workflow_name"]
                and candidate.get("event") == issue_state["allowed_event"],
                "issue_state_exact_source_push_run_identity_invalid",
            )
            if candidate.get("status") == "completed":
                _require(
                    candidate.get("conclusion") == "success",
                    "issue_state_first_attempt_push_run_not_successful",
                )
                run_id = _safe_positive_integer(
                    candidate.get("id"), "issue_state_run_id"
                )
                run = api.json(
                    f"actions/runs/{run_id}/attempts/1", "issue_state_workflow_run"
                )
                _validate_run_common(
                    run,
                    repository=api.repository,
                    source_sha=source_sha,
                    workflow_path=issue_state["workflow_path"],
                    workflow_name=issue_state["workflow_name"],
                    allowed_events={issue_state["allowed_event"]},
                    expected_run_id=run_id,
                )
                run_refetch_fields = (
                    "id",
                    "run_number",
                    "run_attempt",
                    "status",
                    "conclusion",
                    "head_sha",
                    "head_branch",
                    "path",
                    "name",
                    "event",
                )
                _require(
                    _canonical_bytes(
                        {key: candidate.get(key) for key in run_refetch_fields}
                    )
                    == _canonical_bytes(
                        {key: run.get(key) for key in run_refetch_fields}
                    ),
                    "issue_state_run_list_refetch_mismatch",
                )
                return run
            _require(
                candidate.get("status") in {"queued", "in_progress", "waiting"},
                "issue_state_run_status_invalid",
            )
        if poll_attempt < max_poll_attempts:
            sleep(poll_interval_seconds)
    _fail("issue_state_run_unavailable_after_bounded_poll")


def _validate_issue_state_jobs(
    api: GitHubApi, issue_state: dict[str, Any], source_sha: str, run_id: int
) -> dict[str, int]:
    payload = api.json(
        f"actions/runs/{run_id}/attempts/1/jobs?per_page=100",
        "issue_state_jobs",
    )
    rows = payload.get("jobs")
    _require(
        type(rows) is list
        and all(type(row) is dict for row in rows)
        and type(payload.get("total_count")) is int
        and payload.get("total_count") == len(rows)
        and len(rows) == 2
        and {row.get("name") for row in rows} == set(issue_state["required_jobs"])
        and len({row.get("id") for row in rows}) == 2,
        "issue_state_exact_two_job_success_required",
    )
    result: dict[str, int] = {}
    for row in rows:
        job_id = _validate_github_hosted_job(
            row,
            run_id=run_id,
            source_sha=source_sha,
            allowed_runner_labels={"ubuntu-24.04"},
            label=f"issue_state:{row['name']}",
        )
        result[row["name"].replace("-", "_")] = job_id
    return result


def _issue_state_artifact(
    api: GitHubApi,
    issue_state: dict[str, Any],
    source_sha: str,
    run_id: int,
) -> dict[str, Any]:
    expected_name = issue_state["artifact_name_template"].format(
        source_sha=source_sha, run_id=run_id, run_attempt=1
    )
    payload = api.json(
        f"actions/runs/{run_id}/artifacts?per_page=100",
        "issue_state_artifact_inventory",
    )
    rows = payload.get("artifacts")
    _require(
        type(rows) is list
        and all(type(row) is dict for row in rows)
        and len(rows) <= 100
        and type(payload.get("total_count")) is int
        and payload.get("total_count") == len(rows),
        "issue_state_artifact_inventory_invalid",
    )
    matches = [row for row in rows if row.get("name") == expected_name]
    _require(len(matches) == 1, "issue_state_unique_artifact_required")
    listed = matches[0]
    artifact_id = _safe_positive_integer(
        listed.get("id"), "issue_state_listed_artifact_id"
    )
    artifact = api.json(
        f"actions/artifacts/{artifact_id}", "issue_state_artifact_by_id"
    )
    workflow_run = artifact.get("workflow_run")
    expires_at = _parse_datetime(
        artifact.get("expires_at"), "issue_state_artifact_expires_at"
    )
    _artifact_identity(
        api,
        artifact,
        lane_id="issue_state_observation",
        expected_id=artifact_id,
        expected_name=expected_name,
        run_id=run_id,
        source_sha=source_sha,
    )
    _require(
        type(workflow_run) is dict
        and type(workflow_run.get("repository_id")) is int
        and workflow_run.get("repository_id") == 1136685613
        and type(workflow_run.get("head_repository_id")) is int
        and workflow_run.get("head_repository_id") == 1136685613,
        "issue_state_artifact_repository_identity_invalid",
    )
    refetch_fields = (
        "id",
        "name",
        "digest",
        "size_in_bytes",
        "expired",
        "expires_at",
        "workflow_run",
    )
    _require(
        _canonical_bytes({key: listed.get(key) for key in refetch_fields})
        == _canonical_bytes({key: artifact.get(key) for key in refetch_fields}),
        "issue_state_artifact_list_refetch_mismatch",
    )
    artifact["expires_at"] = expires_at
    return artifact


def _run_issue_state_replay(
    *,
    source_root: Path,
    report_path: Path,
    inventory_path: Path,
    schema_path: Path,
    repository: str,
    source_sha: str,
    source_tree_sha: str,
    run_id: int,
) -> None:
    command = [
        sys.executable,
        str(source_root / ISSUE_STATE_VALIDATOR_PATH),
        "--repo-root",
        str(source_root),
        "--inventory",
        str(inventory_path),
        "--schema",
        str(schema_path),
        "--check-report",
        str(report_path),
        "--expected-source-sha",
        source_sha,
        "--expected-source-tree-sha",
        source_tree_sha,
        "--repository",
        repository,
        "--repository-id",
        "1136685613",
        "--workflow-path",
        ISSUE_STATE_WORKFLOW_PATH,
        "--workflow-ref",
        (f"{repository}/{ISSUE_STATE_WORKFLOW_PATH}@refs/heads/main"),
        "--workflow-sha",
        source_sha,
        "--source-ref",
        "refs/heads/main",
        "--github-run-id",
        str(run_id),
        "--github-run-attempt",
        "1",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except OSError as error:
        raise EvidenceIndexError("issue_state_report_replay_unavailable") from error
    _require(result.returncode == 0, "issue_state_report_schema_replay_failed")
    _require(
        result.stdout == b"issue state current report: pass\n",
        "issue_state_report_replay_output_invalid",
    )


def _validate_issue_state_bundle_members(
    members: dict[str, bytes],
) -> dict[str, bytes]:
    _require(
        len(members) == 5
        and tuple(sorted(members)) == tuple(sorted(ISSUE_STATE_BUNDLE_FILES)),
        "issue_state_artifact_exact_five_file_bundle_required",
    )
    return members


def _observation_hash(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("observation_sha256", None)
    return _sha256_bytes(_canonical_bytes(body))


def _collect_issue_state_observation(
    *,
    api: GitHubApi,
    issue_state: dict[str, Any],
    source_sha: str,
    source_tree_sha: str,
    source_root: Path,
    input_root: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    run = _select_issue_state_run(api, issue_state, source_sha)
    run_id = run["id"]
    job_ids = _validate_issue_state_jobs(api, issue_state, source_sha, run_id)
    artifact = _issue_state_artifact(api, issue_state, source_sha, run_id)
    archive_raw = api.artifact_archive(artifact, "issue_state_observation")
    members = _validate_issue_state_bundle_members(
        strict_github_artifact_archive(archive_raw, "issue_state_observation")
    )

    source_blob_shas: dict[str, str] = {}
    for source_path in ISSUE_STATE_BUNDLE_FILES:
        if source_path == ISSUE_STATE_REPORT_PATH.as_posix():
            continue
        source_raw = (source_root / source_path).read_bytes()
        source_blob_sha = _blob_identity(
            api, source_path, source_sha, f"issue_state:{source_path}"
        )
        _require(
            members[source_path] == source_raw
            and _git_blob_sha(members[source_path]) == source_blob_sha,
            f"issue_state_source_blob_mismatch:{source_path}",
        )
        source_blob_shas[source_path] = source_blob_sha

    issue_input = input_root / "issue-state"
    issue_bundle = bundle_root / "issue-state"
    issue_input.mkdir(parents=True, exist_ok=False)
    issue_bundle.mkdir(parents=True, exist_ok=False)
    for path in ISSUE_STATE_BUNDLE_FILES:
        _write_new(issue_input / path, members[path], f"issue_state_input:{path}")
        _write_new(issue_bundle / path, members[path], f"issue_state_bundle:{path}")
    _run_issue_state_replay(
        source_root=source_root,
        report_path=issue_input / ISSUE_STATE_REPORT_PATH,
        inventory_path=issue_input / ISSUE_STATE_INVENTORY_PATH,
        schema_path=issue_input / ISSUE_STATE_SCHEMA_PATH,
        repository=api.repository,
        source_sha=source_sha,
        source_tree_sha=source_tree_sha,
        run_id=run_id,
    )

    report = _strict_json_object(
        members[ISSUE_STATE_REPORT_PATH.as_posix()], "issue_state_report"
    )
    inventory = _exact_keys(
        report.get("inventory"),
        {
            "path",
            "sha256",
            "observed_at",
            "open_issue_count",
            "open_issue_numbers",
            "projection_sha256",
        },
        "issue_state_report_inventory",
    )
    authority = _exact_keys(
        report.get("authority"),
        set(ISSUE_STATE_FALSE_AUTHORITY),
        "issue_state_authority",
    )
    _require(
        report.get("schema_version") == "issue-state-current.v1"
        and report.get("profile") == "issue_state_current.v1"
        and report.get("status") == "pass"
        and report.get("contract_pass") is True
        and report.get("mode") == "live_exact_main"
        and report.get("repository") == api.repository
        and report.get("source")
        == {
            "repository_commit_sha": source_sha,
            "repository_tree_sha": source_tree_sha,
        }
        and report.get("run_identity", {}).get("github_run_id") == str(run_id)
        and type(report.get("run_identity", {}).get("github_run_attempt")) is int
        and report.get("run_identity", {}).get("github_run_attempt") == 1
        and report.get("live_github", {}).get("verified") is True
        and report.get("live_github", {}).get("exact_match") is True
        and all(value is True for value in report.get("consistency_gates", {}).values())
        and authority == ISSUE_STATE_FALSE_AUTHORITY
        and report.get("blockers") == []
        and report.get("claim_boundary") == ISSUE_STATE_CLAIM_BOUNDARY,
        "issue_state_report_contract_invalid",
    )
    numbers = inventory.get("open_issue_numbers")
    _require(
        inventory.get("path") == ISSUE_STATE_INVENTORY_PATH.as_posix()
        and inventory.get("sha256")
        == _sha256_bytes(members[ISSUE_STATE_INVENTORY_PATH.as_posix()])
        and type(inventory.get("open_issue_count")) is int
        and inventory["open_issue_count"] >= 0
        and type(numbers) is list
        and numbers == sorted(set(numbers))
        and all(type(number) is int and number > 0 for number in numbers)
        and inventory["open_issue_count"] == len(numbers)
        and type(inventory.get("projection_sha256")) is str
        and SHA256_RE.fullmatch(inventory["projection_sha256"]) is not None,
        "issue_state_inventory_binding_invalid",
    )
    bundle_rows = [
        {
            "path": path,
            "sha256": _sha256_bytes(members[path]),
            "bytes": len(members[path]),
        }
        for path in ISSUE_STATE_BUNDLE_FILES
    ]
    observation: dict[str, Any] = {
        "workflow_path": ISSUE_STATE_WORKFLOW_PATH,
        "workflow_blob_sha": source_blob_shas[ISSUE_STATE_WORKFLOW_PATH],
        "run_id": run_id,
        "run_attempt": 1,
        "event": "push",
        "job_ids": job_ids,
        "artifact": {
            **_normalized_artifact(artifact, run_id, source_sha),
            "expired": False,
            "expires_at": artifact["expires_at"],
        },
        "bundle": {"file_count": 5, "files": bundle_rows},
        "report": {
            "path": ISSUE_STATE_REPORT_PATH.as_posix(),
            "sha256": _sha256_bytes(members[ISSUE_STATE_REPORT_PATH.as_posix()]),
            "schema_path": ISSUE_STATE_SCHEMA_PATH.as_posix(),
            "schema_sha256": _sha256_bytes(members[ISSUE_STATE_SCHEMA_PATH.as_posix()]),
            "schema_version": "issue-state-current.v1",
            "profile": "issue_state_current.v1",
            "status": "pass",
            "contract_pass": True,
        },
        "inventory": {
            "path": inventory["path"],
            "sha256": inventory["sha256"],
            "observed_at": inventory["observed_at"],
            "open_issue_count": inventory["open_issue_count"],
            "open_issue_numbers": numbers,
            "projection_sha256": inventory["projection_sha256"],
        },
        "authority": dict(ISSUE_STATE_FALSE_AUTHORITY),
        "technical_lane": False,
        "promotion_eligible": False,
        "claim_boundary": ISSUE_STATE_CLAIM_BOUNDARY,
    }
    observation["observation_sha256"] = _observation_hash(observation)
    return observation


def _select_lane_run(
    api: GitHubApi, lane: dict[str, Any], source_sha: str
) -> dict[str, Any]:
    workflow_file = quote(PurePosixPath(lane["workflow_path"]).name, safe="")
    payload = api.json(
        f"actions/workflows/{workflow_file}/runs?branch=main"
        f"&head_sha={source_sha}&per_page=100",
        f"workflow_runs:{lane['lane_id']}",
    )
    rows = payload.get("workflow_runs")
    _require(
        type(rows) is list
        and len(rows) <= 100
        and all(type(row) is dict for row in rows)
        and type(payload.get("total_count")) is int
        and payload["total_count"] == len(rows),
        f"workflow_run_inventory_invalid:{lane['lane_id']}",
    )
    _require(len(rows) == 1, f"unique_exact_source_run_required:{lane['lane_id']}")
    candidate = rows[0]
    _safe_positive_integer(
        candidate.get("run_number"), f"run_number:{lane['lane_id']}"
    )
    _require(
        type(candidate.get("run_attempt")) is int
        and candidate.get("run_attempt") == 1
        and candidate.get("head_sha") == source_sha
        and candidate.get("head_branch") == "main"
        and candidate.get("path") == lane["workflow_path"]
        and candidate.get("name") == lane["workflow_name"]
        and candidate.get("event") in lane["allowed_events"],
        f"exact_source_run_identity_invalid:{lane['lane_id']}",
    )
    _require(
        candidate.get("status") == "completed"
        and candidate.get("conclusion") == "success",
        f"first_attempt_run_not_successful:{lane['lane_id']}",
    )
    run_id = _safe_positive_integer(candidate.get("id"), f"run_id:{lane['lane_id']}")
    run = api.json(
        f"actions/runs/{run_id}/attempts/1", f"workflow_run:{lane['lane_id']}"
    )
    _validate_run_common(
        run,
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=lane["workflow_path"],
        workflow_name=lane["workflow_name"],
        allowed_events=set(lane["allowed_events"]),
        expected_run_id=run_id,
    )
    run_refetch_fields = (
        "id",
        "run_number",
        "run_attempt",
        "status",
        "conclusion",
        "head_sha",
        "head_branch",
        "path",
        "name",
        "event",
    )
    _require(
        _canonical_bytes({key: candidate.get(key) for key in run_refetch_fields})
        == _canonical_bytes({key: run.get(key) for key in run_refetch_fields}),
        f"run_list_refetch_mismatch:{lane['lane_id']}",
    )
    return run


def _validate_lane_jobs(
    api: GitHubApi, lane: dict[str, Any], source_sha: str, run_id: int
) -> tuple[int, int]:
    payload = api.json(
        f"actions/runs/{run_id}/attempts/1/jobs?per_page=100",
        f"jobs:{lane['lane_id']}",
    )
    rows = payload.get("jobs")
    _require(
        type(rows) is list
        and 1 <= len(rows) <= 100
        and all(type(row) is dict for row in rows)
        and type(payload.get("total_count")) is int
        and payload.get("total_count") == len(rows),
        f"job_inventory_must_be_complete:{lane['lane_id']}",
    )
    producers = [row for row in rows if row.get("name") == lane["producer_job"]]
    attestors = [
        row
        for row in rows
        if type(row.get("name")) is str
        and (
            row["name"] == lane["attestor_job_suffix"]
            or row["name"].endswith(" / " + lane["attestor_job_suffix"])
        )
    ]
    _require(
        len(producers) == len(attestors) == 1,
        f"producer_attestor_job_identity_invalid:{lane['lane_id']}",
    )
    allowed_runner_labels = (
        {"ubuntu-24.04", "windows-2025"}
        if lane["lane_id"] == "native"
        else {"ubuntu-24.04"}
    )
    job_ids = {
        _validate_github_hosted_job(
            row,
            run_id=run_id,
            source_sha=source_sha,
            allowed_runner_labels=allowed_runner_labels,
            label=f"{lane['lane_id']}:{row.get('name')}",
        )
        for row in rows
    }
    _require(len(job_ids) == len(rows), f"job_id_collision:{lane['lane_id']}")
    producer_id = _safe_positive_integer(
        producers[0].get("id"), f"producer_job_id:{lane['lane_id']}"
    )
    attestor_id = _safe_positive_integer(
        attestors[0].get("id"), f"attestor_job_id:{lane['lane_id']}"
    )
    _require(producer_id != attestor_id, f"job_id_collision:{lane['lane_id']}")
    return producer_id, attestor_id


def _artifact_identity(
    api: GitHubApi,
    artifact: dict[str, Any],
    *,
    lane_id: str,
    expected_id: int,
    expected_name: str,
    run_id: int,
    source_sha: str,
    maximum: int = MAX_ARCHIVE_BYTES,
) -> dict[str, Any]:
    workflow_run = artifact.get("workflow_run")
    artifact_id = _safe_positive_integer(artifact.get("id"), f"artifact_id:{lane_id}")
    size = _safe_positive_integer(
        artifact.get("size_in_bytes"), f"artifact_size:{lane_id}"
    )
    digest = artifact.get("digest")
    expected_url = api._api_url(f"actions/artifacts/{artifact_id}")
    _require(
        artifact_id == expected_id
        and artifact.get("name") == expected_name
        and type(digest) is str
        and SHA256_RE.fullmatch(digest) is not None
        and size <= maximum
        and artifact.get("expired") is False
        and artifact.get("url") == expected_url
        and artifact.get("archive_download_url") == expected_url + "/zip"
        and type(workflow_run) is dict
        and type(workflow_run.get("id")) is int
        and workflow_run.get("id") == run_id
        and workflow_run.get("head_sha") == source_sha
        and workflow_run.get("head_branch") == "main",
        f"artifact_identity_invalid:{lane_id}:{expected_name}",
    )
    return artifact


def _select_lane_artifacts(
    api: GitHubApi,
    lane: dict[str, Any],
    source_sha: str,
    run_id: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = api.json(
        f"actions/runs/{run_id}/artifacts?per_page=100",
        f"artifact_inventory:{lane['lane_id']}",
    )
    rows = payload.get("artifacts")
    _require(
        type(rows) is list
        and len(rows) <= 100
        and all(type(row) is dict for row in rows)
        and type(payload.get("total_count")) is int
        and payload.get("total_count") == len(rows),
        f"artifact_inventory_must_be_complete:{lane['lane_id']}",
    )
    substitutions = {
        "lane": lane["lane_id"],
        "run_id": run_id,
        "run_attempt": 1,
        "source_sha": source_sha,
    }
    handoff_name = lane["handoff_name_template"].format(**substitutions)
    attestation_name = lane["attestation_name_template"].format(**substitutions)
    selected: list[dict[str, Any]] = []
    for expected_name in (handoff_name, attestation_name):
        matches = [row for row in rows if row.get("name") == expected_name]
        _require(
            len(matches) == 1,
            f"unique_artifact_name_required:{lane['lane_id']}:{expected_name}",
        )
        listed_id = _safe_positive_integer(
            matches[0].get("id"), f"listed_artifact_id:{lane['lane_id']}"
        )
        refetched = api.json(
            f"actions/artifacts/{listed_id}",
            f"artifact_by_id:{lane['lane_id']}:{listed_id}",
        )
        selected.append(
            _artifact_identity(
                api,
                refetched,
                lane_id=lane["lane_id"],
                expected_id=listed_id,
                expected_name=expected_name,
                run_id=run_id,
                source_sha=source_sha,
            )
        )
        refetch_fields = (
            "id",
            "name",
            "digest",
            "size_in_bytes",
            "expired",
            "workflow_run",
        )
        _require(
            _canonical_bytes(
                {key: matches[0].get(key) for key in refetch_fields}
            )
            == _canonical_bytes({key: refetched.get(key) for key in refetch_fields}),
            f"artifact_list_refetch_mismatch:{lane['lane_id']}:{expected_name}",
        )
    _require(
        selected[0]["id"] != selected[1]["id"],
        f"artifact_id_collision:{lane['lane_id']}",
    )
    return selected[0], selected[1]


def _normalized_artifact(
    artifact: dict[str, Any], run_id: int, source_sha: str
) -> dict[str, Any]:
    return {
        "id": artifact["id"],
        "name": artifact["name"],
        "api_digest": artifact["digest"],
        "size_in_bytes": artifact["size_in_bytes"],
        "workflow_run_id": run_id,
        "workflow_run_attempt": 1,
        "source_sha": source_sha,
    }


def _run_artifact_inventory(
    api: GitHubApi, run_id: int, label: str
) -> list[dict[str, Any]]:
    payload = api.json(
        f"actions/runs/{run_id}/artifacts?per_page=100", f"artifacts:{label}"
    )
    rows = payload.get("artifacts")
    _require(
        type(rows) is list
        and len(rows) <= 100
        and all(type(row) is dict for row in rows)
        and type(payload.get("total_count")) is int
        and payload["total_count"] == len(rows),
        f"artifact_inventory_must_be_complete:{label}",
    )
    return rows


def _select_named_artifact(
    api: GitHubApi,
    inventory: list[dict[str, Any]],
    *,
    expected_name: str,
    run_id: int,
    source_sha: str,
    label: str,
    maximum: int = MAX_ARCHIVE_BYTES,
) -> dict[str, Any]:
    matches = [row for row in inventory if row.get("name") == expected_name]
    _require(len(matches) == 1, f"unique_artifact_name_required:{label}")
    artifact_id = _safe_positive_integer(
        matches[0].get("id"), f"listed_artifact_id:{label}"
    )
    artifact = api.json(
        f"actions/artifacts/{artifact_id}", f"artifact_by_id:{label}:{artifact_id}"
    )
    _artifact_identity(
        api,
        artifact,
        lane_id=label,
        expected_id=artifact_id,
        expected_name=expected_name,
        run_id=run_id,
        source_sha=source_sha,
        maximum=maximum,
    )
    _parse_datetime(artifact.get("expires_at"), f"artifact_expires_at:{label}")
    refetch_fields = (
        "id",
        "name",
        "digest",
        "size_in_bytes",
        "expired",
        "expires_at",
        "workflow_run",
    )
    _require(
        _canonical_bytes({key: matches[0].get(key) for key in refetch_fields})
        == _canonical_bytes({key: artifact.get(key) for key in refetch_fields}),
        f"artifact_list_refetch_mismatch:{label}",
    )
    return artifact


def _normalized_upstream_artifact(
    artifact: dict[str, Any], run_id: int, source_sha: str
) -> dict[str, Any]:
    return {
        **_normalized_artifact(artifact, run_id, source_sha),
        "expired": False,
        "expires_at": _parse_datetime(
            artifact.get("expires_at"), f"artifact_expires_at:{artifact['name']}"
        ),
    }


def _nightly_run(
    api: GitHubApi, source_sha: str, nightly_run_id: int
) -> dict[str, Any]:
    workflow_name = "Nightly Full Quality"
    workflow_file = quote(PurePosixPath(NIGHTLY_WORKFLOW_PATH).name, safe="")
    inventory = api.json(
        f"actions/workflows/{workflow_file}/runs?branch=main"
        f"&head_sha={source_sha}&per_page=100",
        "nightly_workflow_runs",
    )
    rows = inventory.get("workflow_runs")
    _require(
        type(rows) is list
        and len(rows) <= 100
        and all(type(row) is dict for row in rows)
        and type(inventory.get("total_count")) is int
        and inventory["total_count"] == len(rows),
        "nightly_workflow_run_inventory_invalid",
    )
    _require(len(rows) == 1, "nightly_unique_exact_source_run_required")
    _validate_run_common(
        rows[0],
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=NIGHTLY_WORKFLOW_PATH,
        workflow_name=workflow_name,
        allowed_events={"schedule", "workflow_dispatch"},
        expected_run_id=nightly_run_id,
    )
    run = api.json(f"actions/runs/{nightly_run_id}/attempts/1", "nightly_run")
    _validate_run_common(
        run,
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=NIGHTLY_WORKFLOW_PATH,
        workflow_name=workflow_name,
        allowed_events={"schedule", "workflow_dispatch"},
        expected_run_id=nightly_run_id,
    )
    run_refetch_fields = (
        "id",
        "run_number",
        "run_attempt",
        "status",
        "conclusion",
        "head_sha",
        "head_branch",
        "path",
        "name",
        "event",
    )
    _require(
        _canonical_bytes({key: rows[0].get(key) for key in run_refetch_fields})
        == _canonical_bytes({key: run.get(key) for key in run_refetch_fields}),
        "nightly_run_list_refetch_mismatch",
    )
    return run


def _root_reference(name: str, members: dict[str, bytes]) -> dict[str, Any]:
    raw = members[name]
    return {
        "path": f"{UPSTREAM_BUNDLE_PREFIX}/{name}",
        "sha256": _sha256_bytes(raw),
        "bytes": len(raw),
    }


def _collect_upstream_roots(
    *,
    api: GitHubApi,
    source_sha: str,
    product_state_run: dict[str, Any],
    source_root: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    product_state_run_id = _safe_positive_integer(
        product_state_run.get("id"), "product_state_run_id"
    )
    product_state_run_number = _safe_positive_integer(
        product_state_run.get("run_number"), "product_state_run_number"
    )
    product_inventory = _run_artifact_inventory(
        api, product_state_run_id, "product_state"
    )
    product_artifact = _select_named_artifact(
        api,
        product_inventory,
        expected_name=f"product-state-current-success-{source_sha}",
        run_id=product_state_run_id,
        source_sha=source_sha,
        label="product_state_final",
        maximum=MAX_PRODUCT_STATE_ARTIFACT_BYTES,
    )
    verification_artifact = _select_named_artifact(
        api,
        product_inventory,
        expected_name=(
            f"product-state-final-verification-{product_state_run_id}-1-{source_sha}"
        ),
        run_id=product_state_run_id,
        source_sha=source_sha,
        label="product_state_verification_roots",
    )
    signed_artifact = _select_named_artifact(
        api,
        product_inventory,
        expected_name=f"product-state-signed-{product_state_run_id}-1-{source_sha}",
        run_id=product_state_run_id,
        source_sha=source_sha,
        label="product_state_signed",
        maximum=MAX_PRODUCT_STATE_ARTIFACT_BYTES,
    )
    _require(
        len(
            {
                product_artifact["id"],
                verification_artifact["id"],
                signed_artifact["id"],
            }
        )
        == 3,
        "product_state_artifact_id_collision",
    )
    root_archive = api.artifact_archive(
        verification_artifact, "product_state_verification_roots"
    )
    members = strict_github_artifact_archive(
        root_archive, "product_state_verification_roots"
    )
    _require(
        tuple(sorted(members)) == PRODUCT_STATE_ROOT_FILES,
        "product_state_root_bundle_member_set_invalid",
    )
    report = _strict_json_object(members["final-verification.json"], "final_verification")
    _exact_keys(
        report,
        {
            "schema_version",
            "repository",
            "source_commit_sha",
            "workflow_path",
            "workflow_run_id",
            "workflow_run_number",
            "workflow_run_attempt",
            "main_ref_before_publish",
            "main_ref_after_publish",
            "nightly_run",
            "signed_artifact",
            "final_artifact",
            "raw_zip_bytes",
            "raw_zip_sha256",
            "candidate_seal_sha256",
            "candidate_seal_attestation_verification_bytes",
            "candidate_seal_attestation_verification_sha256",
            "files",
            "technical_integrity_pass",
            "release_authority",
            "claim_boundary",
        },
        "product_state_final_verification",
    )
    final_identity = _exact_keys(
        report.get("final_artifact"),
        {
            "id",
            "name",
            "digest",
            "size_in_bytes",
            "archive_download_url",
            "expired",
            "workflow_run",
        },
        "product_state_final_artifact_report",
    )
    signed_identity = _exact_keys(
        report.get("signed_artifact"),
        {"id", "name", "digest", "raw_zip_bytes", "raw_zip_sha256"},
        "product_state_signed_artifact_report",
    )
    _require(
        report.get("schema_version")
        == "product-state-final-artifact-verification.v1"
        and report.get("repository") == api.repository
        and report.get("source_commit_sha") == source_sha
        and report.get("workflow_path") == PRODUCT_STATE_WORKFLOW_PATH
        and type(report.get("workflow_run_id")) is int
        and report.get("workflow_run_id") == product_state_run_id
        and type(report.get("workflow_run_number")) is int
        and report.get("workflow_run_number") == product_state_run_number
        and type(report.get("workflow_run_attempt")) is int
        and report.get("workflow_run_attempt") == 1
        and report.get("main_ref_before_publish") == source_sha
        and report.get("main_ref_after_publish") == source_sha
        and report.get("technical_integrity_pass") is True
        and report.get("release_authority") is False
        and type(report.get("raw_zip_bytes")) is int
        and 0 < report["raw_zip_bytes"] <= MAX_PRODUCT_STATE_ARTIFACT_BYTES
        and report["raw_zip_bytes"] == product_artifact["size_in_bytes"]
        and report.get("raw_zip_sha256") == product_artifact["digest"]
        and _canonical_bytes(final_identity)
        == _canonical_bytes({key: product_artifact[key] for key in final_identity})
        and _canonical_bytes(signed_identity)
        == _canonical_bytes(
            {
                "id": signed_artifact["id"],
                "name": signed_artifact["name"],
                "digest": signed_artifact["digest"],
                "raw_zip_bytes": signed_artifact["size_in_bytes"],
                "raw_zip_sha256": signed_artifact["digest"],
            }
        )
        and report.get("claim_boundary")
        == (
            "Final artifact byte-integrity verification only; no release, legal, "
            "design, commercial, redistribution, or independent-verification "
            "authority is granted."
        ),
        "product_state_final_verification_identity_invalid",
    )
    manifest_rows = report.get("files")
    _require(
        type(manifest_rows) is list
        and 1 <= len(manifest_rows) <= 6010
        and all(type(row) is dict for row in manifest_rows),
        "product_state_final_manifest_invalid",
    )
    final_manifest: dict[str, dict[str, Any]] = {}
    for row in manifest_rows:
        _exact_keys(row, {"path", "bytes", "sha256"}, "product_state_final_file")
        path = row.get("path")
        _require(
            type(path) is str
            and path not in final_manifest
            and type(row.get("bytes")) is int
            and 0 < row["bytes"] <= 300_000_000
            and type(row.get("sha256")) is str
            and SHA256_RE.fullmatch(row["sha256"]) is not None,
            "product_state_final_file_identity_invalid",
        )
        final_manifest[path] = row
    _require(
        [row["path"] for row in manifest_rows] == sorted(final_manifest),
        "product_state_final_manifest_not_canonical",
    )
    compact_to_final = {
        "product-state.json": "artifacts/manifests/product_state.current.v1.json",
        "product-state.sigstore.json": (
            ".ci/product-state-inputs/product-state.current.sigstore.json"
        ),
        "product-state.embedded-verification.json": (
            ".ci/product-state-inputs/product-state.current.attestation-verification.json"
        ),
        "provenance.json": (
            ".ci/product-state-inputs/product-state.provenance-bundle.v1.json"
        ),
        "provenance.sigstore.json": (
            ".ci/product-state-inputs/product-state.provenance-bundle.sigstore.json"
        ),
        "provenance.embedded-verification.json": (
            ".ci/product-state-inputs/"
            "product-state.provenance-bundle.attestation-verification.json"
        ),
        "overlay-seal.json": (
            ".ci/product-state-inputs/post-main-overlay/"
            "post-main-evidence-overlay.seal.json"
        ),
        "overlay.sigstore.json": (
            ".ci/product-state-inputs/post-main-overlay/"
            "post-main-evidence-overlay.sigstore.json"
        ),
        "overlay.privileged-verification.json": (
            ".ci/product-state-inputs/"
            "post-main-overlay-privileged-attestation-verification.json"
        ),
        "overlay.final-verification.json": (
            ".ci/product-state-inputs/"
            "post-main-overlay-final-attestation-verification.json"
        ),
        "candidate-seal.json": "product-state-candidate.seal.json",
        "candidate-seal.sigstore.json": (
            ".ci/product-state-inputs/product-state-candidate.seal.sigstore.json"
        ),
    }
    for compact_name, final_name in compact_to_final.items():
        row = final_manifest.get(final_name)
        _require(
            type(row) is dict
            and row["bytes"] == len(members[compact_name])
            and row["sha256"] == _sha256_bytes(members[compact_name]),
            f"product_state_compact_root_binding_invalid:{compact_name}",
        )
    _require(
        report.get("candidate_seal_sha256")
        == _sha256_bytes(members["candidate-seal.json"])
        and type(report.get("candidate_seal_attestation_verification_bytes"))
        is int
        and 0
        < report["candidate_seal_attestation_verification_bytes"]
        <= MAX_FILE_BYTES
        and report["candidate_seal_attestation_verification_bytes"]
        == len(members["candidate-seal.verification.json"])
        and report.get("candidate_seal_attestation_verification_sha256")
        == _sha256_bytes(members["candidate-seal.verification.json"])
        and members["product-state.replay-verification.json"]
        == members["product-state.embedded-verification.json"]
        and members["provenance.replay-verification.json"]
        == members["provenance.embedded-verification.json"]
        and members["overlay.replay-verification.json"]
        == members["overlay.final-verification.json"]
        == members["overlay.privileged-verification.json"]
        and members["candidate-seal.replay-verification.json"]
        == members["candidate-seal.verification.json"],
        "product_state_offline_replay_root_mismatch",
    )
    nightly_report = _exact_keys(
        report.get("nightly_run"),
        {
            "id",
            "run_number",
            "run_attempt",
            "name",
            "path",
            "event",
            "conclusion",
            "head_branch",
            "head_sha",
        },
        "product_state_nightly_run",
    )
    nightly_run_id = _safe_positive_integer(
        nightly_report.get("id"), "nightly_run_id"
    )
    nightly = _nightly_run(api, source_sha, nightly_run_id)
    _require(
        _canonical_bytes(nightly_report)
        == _canonical_bytes({key: nightly[key] for key in nightly_report}),
        "product_state_nightly_run_report_mismatch",
    )
    overlay_inventory = _run_artifact_inventory(api, nightly_run_id, "nightly")
    overlay_artifact = _select_named_artifact(
        api,
        overlay_inventory,
        expected_name=(
            f"post-main-evidence-overlay-attested-{nightly_run_id}-1-{source_sha}"
        ),
        run_id=nightly_run_id,
        source_sha=source_sha,
        label="nightly_attested_overlay",
    )
    overlay_archive = api.artifact_archive(overlay_artifact, "nightly_attested_overlay")
    overlay_members = strict_github_artifact_archive(
        overlay_archive, "nightly_attested_overlay"
    )
    _require(
        overlay_members.get("post-main-evidence-overlay.seal.json")
        == members["overlay-seal.json"]
        and overlay_members.get("post-main-evidence-overlay.sigstore.json")
        == members["overlay.sigstore.json"],
        "product_state_consumed_overlay_bytes_mismatch",
    )
    upstream_bundle = bundle_root / "upstream"
    upstream_bundle.mkdir(parents=True, exist_ok=False)
    root_rows = []
    for name in PRODUCT_STATE_ROOT_FILES:
        _write_new(
            upstream_bundle / name,
            members[name],
            f"product_state_root_bundle:{name}",
        )
        root_rows.append(_root_reference(name, members))

    roots = {
        "product_state_document": _root_reference("product-state.json", members),
        "product_state_attestation_bundle": _root_reference(
            "product-state.sigstore.json", members
        ),
        "product_state_attestation_report": _root_reference(
            "product-state.embedded-verification.json", members
        ),
        "provenance_document": _root_reference("provenance.json", members),
        "provenance_attestation_bundle": _root_reference(
            "provenance.sigstore.json", members
        ),
        "provenance_attestation_report": _root_reference(
            "provenance.embedded-verification.json", members
        ),
        "candidate_seal": _root_reference("candidate-seal.json", members),
        "candidate_seal_attestation_bundle": _root_reference(
            "candidate-seal.sigstore.json", members
        ),
        "candidate_seal_attestation_report": _root_reference(
            "candidate-seal.verification.json", members
        ),
    }
    return {
        "product_state_artifact": _normalized_upstream_artifact(
            product_artifact, product_state_run_id, source_sha
        ),
        "root_bundle": {
            "artifact": _normalized_upstream_artifact(
                verification_artifact, product_state_run_id, source_sha
            ),
            "file_count": len(root_rows),
            "files": root_rows,
        },
        "roots": roots,
        "overlay": {
            "direction": "nightly_to_product_state_to_evidence_index",
            "consumed": True,
            "workflow_name": "Nightly Full Quality",
            "workflow_path": NIGHTLY_WORKFLOW_PATH,
            "workflow_blob_sha": _blob_identity(
                api, NIGHTLY_WORKFLOW_PATH, source_sha, "nightly_workflow"
            ),
            "run_id": nightly_run_id,
            "run_attempt": 1,
            "event": nightly["event"],
            "artifact": _normalized_upstream_artifact(
                overlay_artifact, nightly_run_id, source_sha
            ),
            "seal": _root_reference("overlay-seal.json", members),
            "attestation_bundle": _root_reference("overlay.sigstore.json", members),
            "attestation_report": _root_reference(
                "overlay.final-verification.json", members
            ),
        },
    }


def _run_sigstore_verification(
    *,
    subject_path: Path,
    bundle_path: Path,
    report_path: Path,
    repository: str,
    source_sha: str,
) -> bytes:
    command = [
        "gh",
        "attestation",
        "verify",
        str(subject_path),
        "--repo",
        repository,
        "--bundle",
        str(bundle_path),
        "--signer-workflow",
        f"{repository}/{ATTESTOR_WORKFLOW_PATH}",
        "--signer-digest",
        source_sha,
        "--source-digest",
        source_sha,
        "--source-ref",
        "refs/heads/main",
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True)
    except OSError as error:
        raise EvidenceIndexError("gh_attestation_verify_unavailable") from error
    _require(result.returncode == 0, "gh_attestation_verify_failed")
    _require(
        0 < len(result.stdout) <= 16 * 1024 * 1024, "gh_attestation_report_size_invalid"
    )
    _strict_json_bytes(result.stdout, "gh_attestation_report")
    _write_new(report_path, result.stdout, "sigstore_report")
    return result.stdout


def _invoke_pair_verifier(
    *,
    pair_path: Path,
    handoff_archive_path: Path,
    attestation_archive_path: Path,
    report_path: Path,
    expected_lane: str,
    expected_source_sha: str,
) -> tuple[dict[str, Any], bytes]:
    command = [
        sys.executable,
        str(ROOT / PAIR_VERIFIER_PATH),
        "--pair",
        str(pair_path),
        "--handoff-archive",
        str(handoff_archive_path),
        "--attestation-archive",
        str(attestation_archive_path),
        "--sigstore-report",
        str(report_path),
    ]
    result = subprocess.run(command, check=False, capture_output=True)
    _require(result.returncode == 0, "technical_pair_verifier_failed")
    _require(
        0 < len(result.stdout) <= 4 * 1024 * 1024,
        "technical_pair_verifier_output_size_invalid",
    )
    verified = _strict_json_object(result.stdout, "technical_pair_verifier_result")
    _require(
        verified.get("valid") is True
        and verified.get("lane") == expected_lane
        and verified.get("source_commit_sha") == expected_source_sha
        and type(verified.get("run_attempt")) is int
        and verified.get("run_attempt") == 1,
        f"technical_pair_result_invalid:{expected_lane}",
    )
    return verified, result.stdout


def _collect_lane(
    *,
    api: GitHubApi,
    lane: dict[str, Any],
    source_sha: str,
    source_tree_sha: str,
    attestor_blob_sha: str,
    input_root: Path,
    bundle_root: Path,
) -> dict[str, Any]:
    lane_id = lane["lane_id"]
    run = _select_lane_run(api, lane, source_sha)
    run_id = run["id"]
    producer_job_id, attestor_job_id = _validate_lane_jobs(
        api, lane, source_sha, run_id
    )
    workflow_blob_sha = _blob_identity(
        api, lane["workflow_path"], source_sha, f"lane:{lane_id}"
    )
    handoff_artifact, attestation_artifact = _select_lane_artifacts(
        api, lane, source_sha, run_id
    )

    lane_input = input_root / lane_id
    lane_bundle = bundle_root / lane_id
    lane_input.mkdir(parents=True, exist_ok=False)
    lane_bundle.mkdir(parents=True, exist_ok=False)
    handoff_raw = api.artifact_archive(handoff_artifact, f"{lane_id}:handoff")
    handoff_members = strict_github_artifact_archive(handoff_raw, f"{lane_id}:handoff")
    attestation_raw = api.artifact_archive(
        attestation_artifact, f"{lane_id}:attestation"
    )
    attestation_members = strict_github_artifact_archive(
        attestation_raw, f"{lane_id}:attestation"
    )
    _require(
        set(attestation_members) == {"attestation.json"},
        f"attestation_artifact_member_set_invalid:{lane_id}",
    )
    seal_raw = handoff_members.get("handoff-seal.json")
    subject_raw = handoff_members.get(lane["subject_path"])
    _require(type(seal_raw) is bytes, f"handoff_seal_missing:{lane_id}")
    _require(type(subject_raw) is bytes, f"technical_subject_missing:{lane_id}")
    subject_document = _strict_json_object(subject_raw, f"subject:{lane_id}")
    _require(
        subject_document.get("schema_version") == lane["subject_schema_version"]
        and subject_document.get(lane["subject_source_key"]) == source_sha,
        f"technical_subject_source_contract_invalid:{lane_id}",
    )
    bundle_raw = attestation_members["attestation.json"]

    handoff_archive_path = lane_input / "handoff.zip"
    attestation_archive_path = lane_input / "attestation.zip"
    subject_path = lane_input / "subject" / PurePosixPath(lane["subject_path"]).name
    attestation_bundle_path = lane_input / "attestation.json"
    report_path = lane_input / "sigstore-verification.json"
    _write_new(handoff_archive_path, handoff_raw, f"handoff_archive:{lane_id}")
    _write_new(
        attestation_archive_path,
        attestation_raw,
        f"attestation_archive:{lane_id}",
    )
    _write_new(subject_path, subject_raw, f"technical_subject:{lane_id}")
    _write_new(attestation_bundle_path, bundle_raw, f"attestation_bundle:{lane_id}")

    # Cryptographic verification intentionally precedes construction and use of
    # the source-owned pair verifier input.
    report_raw = _run_sigstore_verification(
        subject_path=subject_path,
        bundle_path=attestation_bundle_path,
        report_path=report_path,
        repository=api.repository,
        source_sha=source_sha,
    )
    normalized_handoff = _normalized_artifact(handoff_artifact, run_id, source_sha)
    normalized_attestation = _normalized_artifact(
        attestation_artifact, run_id, source_sha
    )
    normalized_attestation.update(
        {
            "bundle_path": "attestation.json",
            "bundle_sha256": _sha256_bytes(bundle_raw),
        }
    )
    pair = {
        "schema_version": "technical-evidence-handoff-pair.v1",
        "lane": lane_id,
        "github_api": {
            "repository": api.repository,
            "source_commit_sha": source_sha,
            "source_tree_sha": source_tree_sha,
            "source_ref": "refs/heads/main",
            "workflow_path": lane["workflow_path"],
            "workflow_blob_sha": workflow_blob_sha,
            "attestor_workflow_path": ATTESTOR_WORKFLOW_PATH,
            "attestor_workflow_blob_sha": attestor_blob_sha,
            "event": run["event"],
            "run_id": run_id,
            "run_attempt": 1,
        },
        "handoff_artifact": {
            key: normalized_handoff[key]
            for key in (
                "id",
                "name",
                "api_digest",
                "workflow_run_id",
                "workflow_run_attempt",
                "source_sha",
            )
        },
        "handoff_seal": {
            "path": "handoff-seal.json",
            "sha256": _sha256_bytes(seal_raw),
        },
        "technical_subject": {
            "path": lane["subject_path"],
            "sha256": _sha256_bytes(subject_raw),
            "schema_version": lane["subject_schema_version"],
        },
        "attestation_artifact": {
            key: normalized_attestation[key]
            for key in (
                "id",
                "name",
                "api_digest",
                "workflow_run_id",
                "workflow_run_attempt",
                "source_sha",
                "bundle_path",
                "bundle_sha256",
            )
        },
        "sigstore_verification": {
            "verified": True,
            "report_sha256": _sha256_bytes(report_raw),
            "bundle_sha256": _sha256_bytes(bundle_raw),
            "subject_name": subject_path.name,
            "subject_sha256": _sha256_bytes(subject_raw),
            "repository": api.repository,
            "signer_workflow": f"{api.repository}/{ATTESTOR_WORKFLOW_PATH}",
            "signer_digest": source_sha,
            "source_digest": source_sha,
            "source_ref": "refs/heads/main",
            "deny_self_hosted_runners": True,
        },
    }
    pair_path = lane_input / "pair.json"
    pair_raw = _write_json_new(pair_path, pair, f"pair:{lane_id}")
    verified, verified_raw = _invoke_pair_verifier(
        pair_path=pair_path,
        handoff_archive_path=handoff_archive_path,
        attestation_archive_path=attestation_archive_path,
        report_path=report_path,
        expected_lane=lane_id,
        expected_source_sha=source_sha,
    )
    verified_handoff_artifact_id = _safe_positive_integer(
        verified.get("handoff_artifact_id"),
        f"verified_handoff_artifact_id:{lane_id}",
    )
    verified_attestation_artifact_id = _safe_positive_integer(
        verified.get("attestation_artifact_id"),
        f"verified_attestation_artifact_id:{lane_id}",
    )
    _require(
        verified.get("source_tree_sha") == source_tree_sha
        and verified.get("event") == run["event"]
        and verified.get("workflow_blob_sha") == workflow_blob_sha
        and verified.get("attestor_workflow_blob_sha") == attestor_blob_sha
        and verified_handoff_artifact_id == handoff_artifact["id"]
        and verified_attestation_artifact_id == attestation_artifact["id"],
        f"technical_pair_api_binding_invalid:{lane_id}",
    )
    _write_new(lane_bundle / "pair.json", pair_raw, f"bundle_pair:{lane_id}")
    _write_new(
        lane_bundle / "technical-subject.json",
        subject_raw,
        f"bundle_technical_subject:{lane_id}",
    )
    _write_new(
        lane_bundle / "sigstore-verification.json",
        report_raw,
        f"bundle_sigstore_report:{lane_id}",
    )
    _write_new(
        lane_bundle / "sigstore-bundle.json",
        bundle_raw,
        f"bundle_sigstore_bundle:{lane_id}",
    )
    _write_new(
        lane_bundle / "handoff-seal.json",
        seal_raw,
        f"bundle_handoff_seal:{lane_id}",
    )
    _write_new(
        lane_bundle / "verified-pair.json",
        verified_raw,
        f"bundle_verified_pair:{lane_id}",
    )
    return {
        "lane_id": lane_id,
        "workflow_path": lane["workflow_path"],
        "workflow_blob_sha": workflow_blob_sha,
        "attestor_workflow_path": ATTESTOR_WORKFLOW_PATH,
        "attestor_workflow_blob_sha": attestor_blob_sha,
        "run_id": run_id,
        "run_attempt": 1,
        "event": run["event"],
        "producer_job_id": producer_job_id,
        "attestor_job_id": attestor_job_id,
        "handoff_artifact": normalized_handoff,
        "attestation_artifact": {
            key: normalized_attestation[key]
            for key in (
                "id",
                "name",
                "api_digest",
                "size_in_bytes",
                "workflow_run_id",
                "workflow_run_attempt",
                "source_sha",
            )
        },
        "technical_subject_path": lane["subject_path"],
        "technical_subject_sha256": _sha256_bytes(subject_raw),
        "pair_sha256": _sha256_bytes(pair_raw),
        "sigstore_verification_report_sha256": _sha256_bytes(report_raw),
        "sigstore_bundle_sha256": _sha256_bytes(bundle_raw),
        "handoff_seal_sha256": _sha256_bytes(seal_raw),
        "verified_pair_sha256": _sha256_bytes(verified_raw),
        "contract_pass": True,
        "technical_scope": lane["technical_scope"],
        "authority_not_granted": lane["authority_not_granted"],
        "promotion_eligible": False,
        "promotion_blockers": lane["promotion_blockers"],
    }


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = dict(payload)
    body.pop("artifact_hash", None)
    return _sha256_bytes(_canonical_bytes(body))


def _parse_datetime(value: Any, label: str) -> str:
    _require(type(value) is str and bool(value), f"datetime_required:{label}")
    _require(
        re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
            r"(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})",
            value,
        )
        is not None,
        f"datetime_invalid:{label}",
    )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceIndexError(f"datetime_invalid:{label}") from error
    _require(
        parsed.tzinfo is not None and parsed.utcoffset() is not None,
        f"datetime_timezone_required:{label}",
    )
    return value


def _check_issue_state_observation(
    observation: Any,
    *,
    issue_state: dict[str, Any],
    source_sha: str,
) -> tuple[int, int]:
    value = _exact_keys(
        observation,
        {
            "workflow_path",
            "workflow_blob_sha",
            "run_id",
            "run_attempt",
            "event",
            "job_ids",
            "artifact",
            "bundle",
            "report",
            "inventory",
            "authority",
            "technical_lane",
            "promotion_eligible",
            "claim_boundary",
            "observation_sha256",
        },
        "index_issue_state_observation",
    )
    run_id = _safe_positive_integer(value.get("run_id"), "issue_state_run_id")
    authority = _exact_keys(
        value.get("authority"), set(ISSUE_STATE_FALSE_AUTHORITY), "index_issue_authority"
    )
    _require(
        value.get("workflow_path") == issue_state["workflow_path"]
        and type(value.get("workflow_blob_sha")) is str
        and SHA1_RE.fullmatch(value["workflow_blob_sha"]) is not None
        and type(value.get("run_attempt")) is int
        and value.get("run_attempt") == 1
        and value.get("event") == "push"
        and value.get("technical_lane") is False
        and value.get("promotion_eligible") is False
        and all(authority[key] is False for key in ISSUE_STATE_FALSE_AUTHORITY)
        and value.get("claim_boundary") == ISSUE_STATE_CLAIM_BOUNDARY
        and value.get("observation_sha256") == _observation_hash(value),
        "index_issue_state_contract_invalid",
    )
    jobs = _exact_keys(
        value.get("job_ids"),
        {"offline_contract", "live_exact_main"},
        "index_issue_state_jobs",
    )
    job_ids = {
        _safe_positive_integer(job_id, f"issue_state_job:{name}")
        for name, job_id in jobs.items()
    }
    _require(len(job_ids) == 2, "index_issue_state_job_collision")
    artifact = _exact_keys(
        value.get("artifact"),
        {
            "id",
            "name",
            "api_digest",
            "size_in_bytes",
            "workflow_run_id",
            "workflow_run_attempt",
            "source_sha",
            "expired",
            "expires_at",
        },
        "index_issue_state_artifact",
    )
    artifact_id = _safe_positive_integer(
        artifact.get("id"), "index_issue_state_artifact_id"
    )
    expected_name = issue_state["artifact_name_template"].format(
        source_sha=source_sha, run_id=run_id, run_attempt=1
    )
    _require(
        artifact.get("name") == expected_name
        and type(artifact.get("api_digest")) is str
        and SHA256_RE.fullmatch(artifact["api_digest"]) is not None
        and type(artifact.get("size_in_bytes")) is int
        and 1 <= artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES
        and type(artifact.get("workflow_run_id")) is int
        and artifact.get("workflow_run_id") == run_id
        and type(artifact.get("workflow_run_attempt")) is int
        and artifact.get("workflow_run_attempt") == 1
        and artifact.get("source_sha") == source_sha
        and artifact.get("expired") is False,
        "index_issue_state_artifact_binding_invalid",
    )
    _parse_datetime(artifact.get("expires_at"), "index_issue_state_artifact_expiry")
    bundle = _exact_keys(
        value.get("bundle"), {"file_count", "files"}, "index_issue_state_bundle"
    )
    files = bundle.get("files")
    _require(
        type(bundle.get("file_count")) is int
        and bundle.get("file_count") == 5
        and type(files) is list
        and len(files) == 5,
        "index_issue_state_bundle_count_invalid",
    )
    expected_paths = issue_state["bundle_files"]
    bundle_digests: dict[str, str] = {}
    for row, expected_path in zip(files, expected_paths, strict=True):
        _exact_keys(
            row, {"path", "sha256", "bytes"}, f"index_issue_state_file:{expected_path}"
        )
        _require(
            row.get("path") == expected_path
            and type(row.get("sha256")) is str
            and SHA256_RE.fullmatch(row["sha256"]) is not None
            and type(row.get("bytes")) is int
            and 1 <= row["bytes"] <= MAX_FILE_BYTES,
            f"index_issue_state_file_invalid:{expected_path}",
        )
        bundle_digests[expected_path] = row["sha256"]
    _require(
        list(bundle_digests) == expected_paths,
        "index_issue_state_exact_five_file_bundle_invalid",
    )
    report = _exact_keys(
        value.get("report"),
        {
            "path",
            "sha256",
            "schema_path",
            "schema_sha256",
            "schema_version",
            "profile",
            "status",
            "contract_pass",
        },
        "index_issue_state_report",
    )
    _require(
        _canonical_bytes(report)
        == _canonical_bytes(
            {
                "path": issue_state["report_path"],
                "sha256": bundle_digests[issue_state["report_path"]],
                "schema_path": issue_state["schema_path"],
                "schema_sha256": bundle_digests[issue_state["schema_path"]],
                "schema_version": "issue-state-current.v1",
                "profile": "issue_state_current.v1",
                "status": "pass",
                "contract_pass": True,
            }
        ),
        "index_issue_state_report_binding_invalid",
    )
    inventory = _exact_keys(
        value.get("inventory"),
        {
            "path",
            "sha256",
            "observed_at",
            "open_issue_count",
            "open_issue_numbers",
            "projection_sha256",
        },
        "index_issue_state_inventory",
    )
    numbers = inventory.get("open_issue_numbers")
    _require(
        inventory.get("path") == issue_state["inventory_path"]
        and inventory.get("sha256") == bundle_digests[issue_state["inventory_path"]]
        and type(inventory.get("observed_at")) is str
        and re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z",
            inventory["observed_at"],
        )
        is not None
        and type(inventory.get("open_issue_count")) is int
        and inventory["open_issue_count"] >= 0
        and type(numbers) is list
        and numbers == sorted(set(numbers))
        and all(type(number) is int and number > 0 for number in numbers)
        and inventory["open_issue_count"] == len(numbers)
        and type(inventory.get("projection_sha256")) is str
        and SHA256_RE.fullmatch(inventory["projection_sha256"]) is not None,
        "index_issue_state_inventory_binding_invalid",
    )
    _parse_datetime(
        inventory["observed_at"], "index_issue_state_inventory_observed_at"
    )
    return run_id, artifact_id


def _build_index(
    *,
    catalog: dict[str, Any],
    lanes: list[dict[str, Any]],
    lane_rows: list[dict[str, Any]],
    issue_state_observation: dict[str, Any],
    repository: str,
    source_sha: str,
    tree_sha: str,
    generator_blob_sha: str,
    product_state_blob_sha: str,
    generator_event: str,
    generator_run_id: int,
    product_state_run: dict[str, Any],
    upstream_roots: dict[str, Any],
    source_root: Path,
) -> dict[str, Any]:
    _require(
        tuple(row["lane_id"] for row in lane_rows) == LANE_IDS,
        "lane_result_order_invalid",
    )
    _require(len(lanes) == len(lane_rows) == 5, "lane_result_count_invalid")
    generated_at = _parse_datetime(
        product_state_run.get("updated_at"), "product_state_updated_at"
    )
    contract_rows = []
    for relative in CONTRACT_FILES:
        raw = (source_root / relative).read_bytes()
        _require(0 < len(raw) <= MAX_FILE_BYTES, f"contract_file_size_invalid:{relative}")
        contract_rows.append(
            {
                "path": relative,
                "sha256": _sha256_bytes(raw),
                "bytes": len(raw),
                "git_blob_sha": _git_blob_sha(raw),
            }
        )
    payload: dict[str, Any] = {
        "schema_version": "current-main-evidence-index.v1",
        "index_id": "current-main-authenticated-technical-handoff-pairs.v1",
        "generated_at": generated_at,
        "source": {
            "repository": repository,
            "commit_sha": source_sha,
            "tree_sha": tree_sha,
            "observed_main_sha": source_sha,
            "exact_main_match": True,
        },
        "catalog": {
            "path": CATALOG_PATH.as_posix(),
            "sha256": _sha256_path(source_root / CATALOG_PATH),
            "schema_path": CATALOG_SCHEMA_PATH.as_posix(),
            "schema_sha256": _sha256_path(source_root / CATALOG_SCHEMA_PATH),
        },
        "contracts": {
            "file_count": len(contract_rows),
            "files": contract_rows,
        },
        "upstream": {
            "workflow_name": "Product State Current",
            "workflow_path": PRODUCT_STATE_WORKFLOW_PATH,
            "workflow_blob_sha": product_state_blob_sha,
            "run_id": product_state_run["id"],
            "run_attempt": 1,
            "conclusion": "success",
            "head_sha": source_sha,
            **upstream_roots,
        },
        "generator": {
            "workflow_path": GENERATOR_WORKFLOW_PATH,
            "workflow_blob_sha": generator_blob_sha,
            "run_id": generator_run_id,
            "run_attempt": 1,
            "event": generator_event,
        },
        "status": "pass",
        "contract_pass": True,
        "technical_pair_count": 5,
        "authority": {
            "technical_only": True,
            "scientific_validation": False,
            "legal_authority": False,
            "commercial_use": False,
            "engineering_design": False,
            "release": False,
        },
        "lanes": lane_rows,
        "issue_state_observation": issue_state_observation,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _check_root_reference(value: Any, *, label: str) -> dict[str, Any]:
    row = _exact_keys(value, {"path", "sha256", "bytes"}, label)
    _require(
        type(row.get("path")) is str
        and row["path"].startswith(UPSTREAM_BUNDLE_PREFIX + "/")
        and type(row.get("sha256")) is str
        and SHA256_RE.fullmatch(row["sha256"]) is not None
        and type(row.get("bytes")) is int
        and 1 <= row["bytes"] <= MAX_FILE_BYTES,
        f"root_reference_invalid:{label}",
    )
    return row


def _check_upstream_artifact(
    value: Any,
    *,
    label: str,
    source_sha: str,
    run_id: int,
    expected_name: str,
    maximum: int = MAX_ARCHIVE_BYTES,
) -> int:
    artifact = _exact_keys(
        value,
        {
            "id",
            "name",
            "api_digest",
            "size_in_bytes",
            "workflow_run_id",
            "workflow_run_attempt",
            "source_sha",
            "expired",
            "expires_at",
        },
        label,
    )
    artifact_id = _safe_positive_integer(artifact.get("id"), f"artifact_id:{label}")
    _require(
        artifact.get("name") == expected_name
        and type(artifact.get("api_digest")) is str
        and SHA256_RE.fullmatch(artifact["api_digest"]) is not None
        and type(artifact.get("size_in_bytes")) is int
        and 1 <= artifact["size_in_bytes"] <= maximum
        and type(artifact.get("workflow_run_id")) is int
        and artifact.get("workflow_run_id") == run_id
        and type(artifact.get("workflow_run_attempt")) is int
        and artifact["workflow_run_attempt"] == 1
        and artifact.get("source_sha") == source_sha
        and artifact.get("expired") is False,
        f"upstream_artifact_invalid:{label}",
    )
    _parse_datetime(artifact.get("expires_at"), f"artifact_expires_at:{label}")
    return artifact_id


def _check_root_role(
    value: Any,
    *,
    expected_name: str,
    manifest: dict[str, dict[str, Any]],
    label: str,
) -> None:
    row = _check_root_reference(value, label=label)
    expected_path = f"{UPSTREAM_BUNDLE_PREFIX}/{expected_name}"
    _require(
        row.get("path") == expected_path and manifest.get(expected_path) == row,
        f"root_role_binding_invalid:{label}",
    )


def check_index(
    *,
    index_path: Path,
    source_root: Path = ROOT,
    expected_source_sha: str | None = None,
    expected_repository: str | None = None,
    expected_generator_run_id: int | None = None,
    expected_product_state_run_id: int | None = None,
) -> dict[str, Any]:
    catalog, catalog_lanes = _load_catalog(source_root)
    index = _read_json(index_path, "index")
    _exact_keys(
        index,
        {
            "schema_version",
            "index_id",
            "generated_at",
            "source",
            "catalog",
            "contracts",
            "upstream",
            "generator",
            "status",
            "contract_pass",
            "technical_pair_count",
            "authority",
            "lanes",
            "issue_state_observation",
            "claim_boundary",
            "artifact_hash",
        },
        "index",
    )
    _require(
        index["schema_version"] == "current-main-evidence-index.v1"
        and index["index_id"] == "current-main-authenticated-technical-handoff-pairs.v1"
        and index["status"] == "pass"
        and index["contract_pass"] is True
        and type(index["technical_pair_count"]) is int
        and index["technical_pair_count"] == 5
        and index["claim_boundary"] == CLAIM_BOUNDARY
        and index["artifact_hash"] == _artifact_hash(index),
        "index_header_invalid",
    )
    _parse_datetime(index["generated_at"], "index_generated_at")
    source = _exact_keys(
        index["source"],
        {
            "repository",
            "commit_sha",
            "tree_sha",
            "observed_main_sha",
            "exact_main_match",
        },
        "index_source",
    )
    _require(
        type(source["repository"]) is str
        and REPOSITORY_RE.fullmatch(source["repository"]) is not None
        and type(source["commit_sha"]) is str
        and SHA1_RE.fullmatch(source["commit_sha"]) is not None
        and type(source["tree_sha"]) is str
        and SHA1_RE.fullmatch(source["tree_sha"]) is not None
        and source["observed_main_sha"] == source["commit_sha"]
        and source["exact_main_match"] is True,
        "index_source_invalid",
    )
    if expected_source_sha is not None:
        _require(
            source["commit_sha"] == expected_source_sha, "expected_source_sha_mismatch"
        )
    if expected_repository is not None:
        _require(
            source["repository"] == expected_repository, "expected_repository_mismatch"
        )
    catalog_row = index["catalog"]
    _require(
        catalog_row
        == {
            "path": CATALOG_PATH.as_posix(),
            "sha256": _sha256_path(source_root / CATALOG_PATH),
            "schema_path": CATALOG_SCHEMA_PATH.as_posix(),
            "schema_sha256": _sha256_path(source_root / CATALOG_SCHEMA_PATH),
        },
        "index_catalog_binding_invalid",
    )
    contracts = _exact_keys(
        index["contracts"], {"file_count", "files"}, "index_contracts"
    )
    contract_rows = contracts.get("files")
    _require(
        type(contracts.get("file_count")) is int
        and contracts["file_count"] == len(CONTRACT_FILES)
        and type(contract_rows) is list
        and len(contract_rows) == len(CONTRACT_FILES),
        "index_contract_count_invalid",
    )
    for row, relative in zip(contract_rows, CONTRACT_FILES, strict=True):
        row = _exact_keys(
            row,
            {"path", "sha256", "bytes", "git_blob_sha"},
            f"index_contract:{relative}",
        )
        raw = (source_root / relative).read_bytes()
        _require(
            row.get("path") == relative
            and type(row.get("sha256")) is str
            and row["sha256"] == _sha256_bytes(raw)
            and type(row.get("bytes")) is int
            and row["bytes"] == len(raw)
            and type(row.get("git_blob_sha")) is str
            and row["git_blob_sha"] == _git_blob_sha(raw),
            f"index_contract_binding_invalid:{relative}",
        )
    upstream = _exact_keys(
        index["upstream"],
        {
            "workflow_name",
            "workflow_path",
            "workflow_blob_sha",
            "run_id",
            "run_attempt",
            "conclusion",
            "head_sha",
            "product_state_artifact",
            "root_bundle",
            "roots",
            "overlay",
        },
        "index_upstream",
    )
    product_state_run_id = _safe_positive_integer(
        upstream.get("run_id"), "index_product_state_run_id"
    )
    _require(
        upstream["workflow_name"] == "Product State Current"
        and upstream["workflow_path"] == PRODUCT_STATE_WORKFLOW_PATH
        and type(upstream["workflow_blob_sha"]) is str
        and SHA1_RE.fullmatch(upstream["workflow_blob_sha"]) is not None
        and type(upstream["run_attempt"]) is int
        and upstream["run_attempt"] == 1
        and upstream["conclusion"] == "success"
        and upstream["head_sha"] == source["commit_sha"],
        "index_upstream_invalid",
    )
    product_artifact_id = _check_upstream_artifact(
        upstream["product_state_artifact"],
        label="product_state_final",
        source_sha=source["commit_sha"],
        run_id=product_state_run_id,
        expected_name=f"product-state-current-success-{source['commit_sha']}",
        maximum=MAX_PRODUCT_STATE_ARTIFACT_BYTES,
    )
    root_bundle = _exact_keys(
        upstream["root_bundle"],
        {"artifact", "file_count", "files"},
        "index_upstream_root_bundle",
    )
    root_artifact_id = _check_upstream_artifact(
        root_bundle["artifact"],
        label="product_state_verification_roots",
        source_sha=source["commit_sha"],
        run_id=product_state_run_id,
        expected_name=(
            f"product-state-final-verification-{product_state_run_id}-1-"
            f"{source['commit_sha']}"
        ),
    )
    root_files = root_bundle.get("files")
    _require(
        type(root_bundle.get("file_count")) is int
        and root_bundle["file_count"] == len(PRODUCT_STATE_ROOT_FILES)
        and type(root_files) is list
        and len(root_files) == len(PRODUCT_STATE_ROOT_FILES),
        "index_upstream_root_bundle_count_invalid",
    )
    root_manifest: dict[str, dict[str, Any]] = {}
    for position, expected_name in enumerate(PRODUCT_STATE_ROOT_FILES):
        row = _check_root_reference(
            root_files[position], label=f"root_bundle_file:{expected_name}"
        )
        expected_path = f"{UPSTREAM_BUNDLE_PREFIX}/{expected_name}"
        _require(
            row["path"] == expected_path and expected_path not in root_manifest,
            "index_upstream_root_bundle_topology_invalid",
        )
        root_manifest[expected_path] = row
    roots = _exact_keys(
        upstream["roots"],
        {
            "product_state_document",
            "product_state_attestation_bundle",
            "product_state_attestation_report",
            "provenance_document",
            "provenance_attestation_bundle",
            "provenance_attestation_report",
            "candidate_seal",
            "candidate_seal_attestation_bundle",
            "candidate_seal_attestation_report",
        },
        "index_upstream_roots",
    )
    for role, expected_name in {
        "product_state_document": "product-state.json",
        "product_state_attestation_bundle": "product-state.sigstore.json",
        "product_state_attestation_report": (
            "product-state.embedded-verification.json"
        ),
        "provenance_document": "provenance.json",
        "provenance_attestation_bundle": "provenance.sigstore.json",
        "provenance_attestation_report": "provenance.embedded-verification.json",
        "candidate_seal": "candidate-seal.json",
        "candidate_seal_attestation_bundle": "candidate-seal.sigstore.json",
        "candidate_seal_attestation_report": "candidate-seal.verification.json",
    }.items():
        _check_root_role(
            roots[role],
            expected_name=expected_name,
            manifest=root_manifest,
            label=role,
        )
    overlay = _exact_keys(
        upstream["overlay"],
        {
            "direction",
            "consumed",
            "workflow_name",
            "workflow_path",
            "workflow_blob_sha",
            "run_id",
            "run_attempt",
            "event",
            "artifact",
            "seal",
            "attestation_bundle",
            "attestation_report",
        },
        "index_upstream_overlay",
    )
    nightly_run_id = _safe_positive_integer(overlay.get("run_id"), "index_nightly_run_id")
    _require(
        overlay.get("direction") == "nightly_to_product_state_to_evidence_index"
        and overlay.get("consumed") is True
        and overlay.get("workflow_name") == "Nightly Full Quality"
        and overlay.get("workflow_path") == NIGHTLY_WORKFLOW_PATH
        and type(overlay.get("workflow_blob_sha")) is str
        and SHA1_RE.fullmatch(overlay["workflow_blob_sha"]) is not None
        and type(overlay.get("run_attempt")) is int
        and overlay["run_attempt"] == 1
        and overlay.get("event") in {"schedule", "workflow_dispatch"},
        "index_upstream_overlay_invalid",
    )
    overlay_artifact_id = _check_upstream_artifact(
        overlay["artifact"],
        label="nightly_attested_overlay",
        source_sha=source["commit_sha"],
        run_id=nightly_run_id,
        expected_name=(
            f"post-main-evidence-overlay-attested-{nightly_run_id}-1-"
            f"{source['commit_sha']}"
        ),
    )
    for role, expected_name in {
        "seal": "overlay-seal.json",
        "attestation_bundle": "overlay.sigstore.json",
        "attestation_report": "overlay.final-verification.json",
    }.items():
        _check_root_role(
            overlay[role],
            expected_name=expected_name,
            manifest=root_manifest,
            label=f"overlay_{role}",
        )
    _require(
        len({product_artifact_id, root_artifact_id, overlay_artifact_id}) == 3,
        "index_upstream_artifact_id_collision",
    )
    if expected_product_state_run_id is not None:
        _require(
            product_state_run_id == expected_product_state_run_id,
            "expected_product_state_run_id_mismatch",
        )
    generator = _exact_keys(
        index["generator"],
        {"workflow_path", "workflow_blob_sha", "run_id", "run_attempt", "event"},
        "index_generator",
    )
    _require(
        generator["workflow_path"] == GENERATOR_WORKFLOW_PATH
        and type(generator["workflow_blob_sha"]) is str
        and SHA1_RE.fullmatch(generator["workflow_blob_sha"]) is not None
        and type(generator["run_attempt"]) is int
        and generator["run_attempt"] == 1
        and generator["event"] == "workflow_run",
        "index_generator_invalid",
    )
    generator_run_id = _safe_positive_integer(
        generator["run_id"], "index_generator_run_id"
    )
    if expected_generator_run_id is not None:
        _require(
            generator["run_id"] == expected_generator_run_id,
            "expected_generator_run_id_mismatch",
        )
    authority = _exact_keys(
        index["authority"],
        {
            "technical_only",
            "scientific_validation",
            "legal_authority",
            "commercial_use",
            "engineering_design",
            "release",
        },
        "index_authority",
    )
    _require(
        authority["technical_only"] is True
        and all(
            authority[key] is False
            for key in (
                "scientific_validation",
                "legal_authority",
                "commercial_use",
                "engineering_design",
                "release",
            )
        ),
        "index_authority_promotion_forbidden",
    )
    issue_run_id, issue_artifact_id = _check_issue_state_observation(
        index["issue_state_observation"],
        issue_state=catalog["issue_state_observation"],
        source_sha=source["commit_sha"],
    )
    rows = index["lanes"]
    _require(
        type(rows) is list
        and len(rows) == 5
        and tuple(row.get("lane_id") for row in rows) == LANE_IDS,
        "index_lane_order_invalid",
    )
    artifact_ids: set[int] = {
        issue_artifact_id,
        product_artifact_id,
        root_artifact_id,
        overlay_artifact_id,
    }
    run_ids: set[int] = {
        issue_run_id,
        product_state_run_id,
        nightly_run_id,
        generator_run_id,
    }
    _require(
        len(artifact_ids) == 4 and len(run_ids) == 4,
        "index_initial_global_identity_collision",
    )
    for row, specification in zip(rows, catalog_lanes, strict=True):
        lane_id = specification["lane_id"]
        _exact_keys(
            row,
            {
                "lane_id",
                "workflow_path",
                "workflow_blob_sha",
                "attestor_workflow_path",
                "attestor_workflow_blob_sha",
                "run_id",
                "run_attempt",
                "event",
                "producer_job_id",
                "attestor_job_id",
                "handoff_artifact",
                "attestation_artifact",
                "technical_subject_path",
                "technical_subject_sha256",
                "pair_sha256",
                "sigstore_verification_report_sha256",
                "sigstore_bundle_sha256",
                "handoff_seal_sha256",
                "verified_pair_sha256",
                "contract_pass",
                "technical_scope",
                "authority_not_granted",
                "promotion_eligible",
                "promotion_blockers",
            },
            f"index_lane:{lane_id}",
        )
        _require(
            row.get("workflow_path") == specification["workflow_path"]
            and type(row.get("workflow_blob_sha")) is str
            and SHA1_RE.fullmatch(row["workflow_blob_sha"]) is not None
            and row.get("attestor_workflow_path") == ATTESTOR_WORKFLOW_PATH
            and type(row.get("attestor_workflow_blob_sha")) is str
            and SHA1_RE.fullmatch(row["attestor_workflow_blob_sha"]) is not None
            and type(row.get("run_attempt")) is int
            and row.get("run_attempt") == 1
            and row.get("event") in specification["allowed_events"]
            and row.get("technical_subject_path") == specification["subject_path"]
            and type(row.get("technical_subject_sha256")) is str
            and SHA256_RE.fullmatch(row["technical_subject_sha256"]) is not None
            and type(row.get("pair_sha256")) is str
            and SHA256_RE.fullmatch(row["pair_sha256"]) is not None
            and type(row.get("sigstore_verification_report_sha256")) is str
            and SHA256_RE.fullmatch(row["sigstore_verification_report_sha256"])
            is not None
            and type(row.get("sigstore_bundle_sha256")) is str
            and SHA256_RE.fullmatch(row["sigstore_bundle_sha256"]) is not None
            and type(row.get("handoff_seal_sha256")) is str
            and SHA256_RE.fullmatch(row["handoff_seal_sha256"]) is not None
            and type(row.get("verified_pair_sha256")) is str
            and SHA256_RE.fullmatch(row["verified_pair_sha256"]) is not None
            and row.get("contract_pass") is True
            and row.get("technical_scope") == specification["technical_scope"]
            and row.get("authority_not_granted")
            == specification["authority_not_granted"]
            and row.get("promotion_eligible") is False
            and row.get("promotion_blockers") == specification["promotion_blockers"],
            f"index_lane_contract_invalid:{lane_id}",
        )
        run_id = _safe_positive_integer(row.get("run_id"), f"index_run_id:{lane_id}")
        run_ids.add(run_id)
        producer = _safe_positive_integer(
            row.get("producer_job_id"), f"producer_job_id:{lane_id}"
        )
        attestor = _safe_positive_integer(
            row.get("attestor_job_id"), f"attestor_job_id:{lane_id}"
        )
        _require(producer != attestor, f"index_job_collision:{lane_id}")
        for artifact_kind in ("handoff_artifact", "attestation_artifact"):
            artifact = row.get(artifact_kind)
            _require(
                type(artifact) is dict,
                f"index_artifact_missing:{lane_id}:{artifact_kind}",
            )
            _exact_keys(
                artifact,
                {
                    "id",
                    "name",
                    "api_digest",
                    "size_in_bytes",
                    "workflow_run_id",
                    "workflow_run_attempt",
                    "source_sha",
                },
                f"index_artifact:{lane_id}:{artifact_kind}",
            )
            artifact_id = _safe_positive_integer(
                artifact.get("id"), f"index_artifact_id:{lane_id}:{artifact_kind}"
            )
            _require(
                artifact_id not in artifact_ids
                and type(artifact.get("workflow_run_id")) is int
                and artifact.get("workflow_run_id") == run_id
                and type(artifact.get("workflow_run_attempt")) is int
                and artifact.get("workflow_run_attempt") == 1
                and artifact.get("source_sha") == source["commit_sha"]
                and type(artifact.get("api_digest")) is str
                and SHA256_RE.fullmatch(artifact["api_digest"]) is not None
                and type(artifact.get("size_in_bytes")) is int
                and 1 <= artifact["size_in_bytes"] <= MAX_ARCHIVE_BYTES,
                f"index_artifact_binding_invalid:{lane_id}:{artifact_kind}",
            )
            artifact_ids.add(artifact_id)
        expected_handoff = specification["handoff_name_template"].format(
            lane=lane_id,
            run_id=run_id,
            run_attempt=1,
            source_sha=source["commit_sha"],
        )
        _require(
            row["handoff_artifact"]["name"] == expected_handoff
            and row["attestation_artifact"]["name"]
            == expected_handoff + "-attestation",
            f"index_artifact_name_invalid:{lane_id}",
        )
    _require(
        len(run_ids) == 9 and len(artifact_ids) == 14,
        "index_global_identity_collision",
    )
    return index


def collect_and_build(
    *,
    source_sha: str,
    repository: str,
    token: str,
    product_state_run_id: int,
    generator_event: str,
    generator_run_id: int,
    generator_run_attempt: int,
    input_root: Path,
    bundle_root: Path,
    output_path: Path,
    source_root: Path = ROOT,
) -> dict[str, Any]:
    _require(generator_event == "workflow_run", "generator_event_invalid")
    _safe_positive_integer(generator_run_id, "generator_run_id")
    _require(generator_run_attempt == 1, "generator_first_attempt_required")
    _require(SHA1_RE.fullmatch(source_sha) is not None, "source_sha_invalid")
    _require(REPOSITORY_RE.fullmatch(repository) is not None, "repository_invalid")
    _require(not input_root.exists(), "input_root_must_not_exist")
    _require(not bundle_root.exists(), "bundle_root_must_not_exist")
    _require(not output_path.exists(), "output_must_not_exist")
    catalog, lanes = _load_catalog(source_root)
    api = GitHubApi(repository, token)
    (
        tree_sha,
        attestor_blob_sha,
        generator_blob_sha,
        product_state_blob_sha,
    ) = _source_identity(api, source_sha)
    product_state = _product_state_run(api, source_sha, product_state_run_id)
    input_root.mkdir(parents=True, exist_ok=False)
    bundle_root.mkdir(parents=True, exist_ok=False)
    upstream_roots = _collect_upstream_roots(
        api=api,
        source_sha=source_sha,
        product_state_run=product_state,
        source_root=source_root,
        bundle_root=bundle_root,
    )
    issue_state_observation = _collect_issue_state_observation(
        api=api,
        issue_state=catalog["issue_state_observation"],
        source_sha=source_sha,
        source_tree_sha=tree_sha,
        source_root=source_root,
        input_root=input_root,
        bundle_root=bundle_root,
    )
    lane_rows = [
        _collect_lane(
            api=api,
            lane=lane,
            source_sha=source_sha,
            source_tree_sha=tree_sha,
            attestor_blob_sha=attestor_blob_sha,
            input_root=input_root,
            bundle_root=bundle_root,
        )
        for lane in lanes
    ]
    index = _build_index(
        catalog=catalog,
        lanes=lanes,
        lane_rows=lane_rows,
        issue_state_observation=issue_state_observation,
        repository=repository,
        source_sha=source_sha,
        tree_sha=tree_sha,
        generator_blob_sha=generator_blob_sha,
        product_state_blob_sha=product_state_blob_sha,
        generator_event=generator_event,
        generator_run_id=generator_run_id,
        product_state_run=product_state,
        upstream_roots=upstream_roots,
        source_root=source_root,
    )
    _write_json_new(output_path, index, "index")
    check_index(
        index_path=output_path,
        source_root=source_root,
        expected_source_sha=source_sha,
        expected_repository=repository,
        expected_generator_run_id=generator_run_id,
        expected_product_state_run_id=product_state_run_id,
    )
    return index


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--source-sha", required=True)
    collect.add_argument("--repository", required=True)
    collect.add_argument("--product-state-run-id", type=int, required=True)
    collect.add_argument("--generator-event", required=True)
    collect.add_argument("--generator-run-id", type=int, required=True)
    collect.add_argument("--generator-run-attempt", type=int, required=True)
    collect.add_argument("--input-root", type=Path, required=True)
    collect.add_argument("--bundle-root", type=Path, required=True)
    collect.add_argument("--out", type=Path, required=True)
    collect.add_argument("--source-root", type=Path, default=ROOT)
    check = subparsers.add_parser("check")
    check.add_argument("--index", type=Path, required=True)
    check.add_argument("--source-root", type=Path, default=ROOT)
    check.add_argument("--expected-source-sha")
    check.add_argument("--expected-repository")
    check.add_argument("--expected-generator-run-id", type=int)
    check.add_argument("--expected-product-state-run-id", type=int)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "collect":
            collect_and_build(
                source_sha=args.source_sha,
                repository=args.repository,
                token=os.environ.get("GH_TOKEN", ""),
                product_state_run_id=args.product_state_run_id,
                generator_event=args.generator_event,
                generator_run_id=args.generator_run_id,
                generator_run_attempt=args.generator_run_attempt,
                input_root=args.input_root,
                bundle_root=args.bundle_root,
                output_path=args.out,
                source_root=args.source_root,
            )
        else:
            check_index(
                index_path=args.index,
                source_root=args.source_root,
                expected_source_sha=args.expected_source_sha,
                expected_repository=args.expected_repository,
                expected_generator_run_id=args.expected_generator_run_id,
                expected_product_state_run_id=args.expected_product_state_run_id,
            )
    except EvidenceIndexError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
