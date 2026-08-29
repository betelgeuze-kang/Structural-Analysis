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
MAX_SAFE_INTEGER = 9_007_199_254_740_991
MAX_API_BYTES = 10_000_000
MAX_ARCHIVE_BYTES = 300_000_000
MAX_ARCHIVE_MEMBERS = 192
MAX_FILE_BYTES = 100_000_000
MAX_UNCOMPRESSED_BYTES = 300_000_000
MAX_COMPRESSION_RATIO = 200
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CLAIM_BOUNDARY = (
    "authenticated_exact_main_same_operator_technical_pairs_only_"
    "no_scientific_legal_engineering_commercial_or_release_promotion"
)
LANE_IDS = ("medium", "ifc", "mgt9", "mgt10", "native")
LANE_TRUST_ROOTS: dict[str, dict[str, str]] = {
    "medium": {
        "workflow_name": "Medium Scale Current Source",
        "workflow_path": ".github/workflows/medium-scale-current-source.yml",
        "subject_path": "artifacts/medium-scale/current-source/medium-scale-execution.v1.json",
        "subject_schema_version": "medium-scale-current-source-execution.v1",
        "subject_source_key": "source_commit_sha",
    },
    "ifc": {
        "workflow_name": "IFC Import Health Current Source",
        "workflow_path": ".github/workflows/ifc-import-health-current-source.yml",
        "subject_path": ".ci/ifc-import-health-current-source/technical-receipt.json",
        "subject_schema_version": "ifc-import-health-current-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "mgt9": {
        "workflow_name": "MGT Import Health Current Source",
        "workflow_path": ".github/workflows/mgt-import-health-current-source.yml",
        "subject_path": ".ci/mgt-import-health-current-source/technical-receipt.json",
        "subject_schema_version": "mgt-import-health-current-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "mgt10": {
        "workflow_name": "MGT Import Health Tenth Source",
        "workflow_path": ".github/workflows/mgt-import-health-tenth-source.yml",
        "subject_path": ".ci/mgt-import-health-tenth-source/technical-receipt.json",
        "subject_schema_version": "mgt-import-health-tenth-source-technical-receipt.v1",
        "subject_source_key": "source_commit_sha",
    },
    "native": {
        "workflow_name": "Native Frame Alpha Clean Install",
        "workflow_path": ".github/workflows/native-frame-alpha-clean-install.yml",
        "subject_path": "native-clean-install-summary.json",
        "subject_schema_version": "technical-native-clean-install-handoff.v1",
        "subject_source_key": "source_sha",
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
            "lanes",
        },
        "catalog",
    )
    _require(
        catalog["schema_version"] == "current-main-evidence-lanes.v1"
        and catalog["catalog_id"]
        == "current-main-authenticated-technical-handoff-pairs.v1"
        and catalog["required_lane_count"] == 5
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
        and overlay
        == {
            "direction": "nightly_to_product_state_to_evidence_index",
            "version": "reserved-for-authenticated-product-state-overlay.v1",
            "consumption_enabled": False,
            "artifact": None,
        },
        "catalog_overlay_interface_invalid",
    )
    lanes = catalog["lanes"]
    _require(type(lanes) is list and len(lanes) == 5, "catalog_lane_count_invalid")
    _require(
        tuple(row.get("lane_id") for row in lanes) == LANE_IDS,
        "catalog_lane_order_invalid",
    )
    for row in lanes:
        lane_id = row["lane_id"]
        trust = LANE_TRUST_ROOTS[lane_id]
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
            row.get("evidence_mode") == "handoff_pair"
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
            and type(row.get("allowed_events")) is list
            and set(row["allowed_events"]).issubset({"push", "workflow_dispatch"})
            and row["allowed_events"]
            and len(row["allowed_events"]) == len(set(row["allowed_events"]))
            and type(row.get("authority_not_granted")) is list
            and "release" in row["authority_not_granted"]
            and type(row.get("promotion_blockers")) is list
            and bool(row["promotion_blockers"]),
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
    if expected_run_id is not None:
        _require(run_id == expected_run_id, f"run_id_mismatch:{workflow_name}")
    head_repository = run.get("head_repository")
    _require(
        run.get("run_attempt") == 1
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
        row.get("run_id") == run_id
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
    run = api.json(
        f"actions/runs/{product_state_run_id}/attempts/1", "product_state_run"
    )
    _validate_run_common(
        run,
        repository=api.repository,
        source_sha=source_sha,
        workflow_path=".github/workflows/product-state-current.yml",
        workflow_name="Product State Current",
        allowed_events={"workflow_run"},
        expected_run_id=product_state_run_id,
    )
    jobs = api.json(
        f"actions/runs/{product_state_run_id}/attempts/1/jobs?per_page=100",
        "product_state_jobs",
    )
    rows = jobs.get("jobs")
    _require(
        type(rows) is list
        and all(type(row) is dict for row in rows)
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


def _select_lane_run(
    api: GitHubApi, lane: dict[str, Any], source_sha: str
) -> dict[str, Any]:
    workflow_file = quote(PurePosixPath(lane["workflow_path"]).name, safe="")
    payload = api.json(
        f"actions/workflows/{workflow_file}/runs?branch=main&status=success&per_page=100",
        f"workflow_runs:{lane['lane_id']}",
    )
    rows = payload.get("workflow_runs")
    _require(
        type(rows) is list
        and len(rows) <= 100
        and type(payload.get("total_count")) is int
        and payload["total_count"] >= len(rows),
        f"workflow_run_inventory_invalid:{lane['lane_id']}",
    )
    matches = [
        row
        for row in rows
        if type(row) is dict
        and row.get("run_attempt") == 1
        and row.get("head_sha") == source_sha
        and row.get("head_branch") == "main"
        and row.get("path") == lane["workflow_path"]
        and row.get("name") == lane["workflow_name"]
        and row.get("status") == "completed"
        and row.get("conclusion") == "success"
        and row.get("event") in lane["allowed_events"]
    ]
    _require(len(matches) == 1, f"unique_first_attempt_run_required:{lane['lane_id']}")
    run_id = _safe_positive_integer(matches[0].get("id"), f"run_id:{lane['lane_id']}")
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
        and size <= MAX_ARCHIVE_BYTES
        and artifact.get("expired") is False
        and artifact.get("url") == expected_url
        and artifact.get("archive_download_url") == expected_url + "/zip"
        and type(workflow_run) is dict
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
        _require(
            all(
                matches[0].get(key) == refetched.get(key)
                for key in (
                    "id",
                    "name",
                    "digest",
                    "size_in_bytes",
                    "expired",
                    "workflow_run",
                )
            ),
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
    _require(
        verified.get("source_tree_sha") == source_tree_sha
        and verified.get("event") == run["event"]
        and verified.get("workflow_blob_sha") == workflow_blob_sha
        and verified.get("attestor_workflow_blob_sha") == attestor_blob_sha
        and verified.get("handoff_artifact_id") == handoff_artifact["id"]
        and verified.get("attestation_artifact_id") == attestation_artifact["id"],
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
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceIndexError(f"datetime_invalid:{label}") from error
    return value


def _build_index(
    *,
    catalog: dict[str, Any],
    lanes: list[dict[str, Any]],
    lane_rows: list[dict[str, Any]],
    repository: str,
    source_sha: str,
    tree_sha: str,
    generator_blob_sha: str,
    product_state_blob_sha: str,
    generator_event: str,
    generator_run_id: int,
    product_state_run: dict[str, Any],
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
        "upstream": {
            "workflow_name": "Product State Current",
            "workflow_path": ".github/workflows/product-state-current.yml",
            "workflow_blob_sha": product_state_blob_sha,
            "run_id": product_state_run["id"],
            "run_attempt": 1,
            "conclusion": "success",
            "head_sha": source_sha,
            "overlay": {
                "direction": "nightly_to_product_state_to_evidence_index",
                "consumed": False,
                "artifact": None,
            },
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
        "claim_boundary": CLAIM_BOUNDARY,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


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
            "upstream",
            "generator",
            "status",
            "contract_pass",
            "technical_pair_count",
            "authority",
            "lanes",
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
            "overlay",
        },
        "index_upstream",
    )
    _require(
        upstream["workflow_name"] == "Product State Current"
        and upstream["workflow_path"] == ".github/workflows/product-state-current.yml"
        and type(upstream["workflow_blob_sha"]) is str
        and SHA1_RE.fullmatch(upstream["workflow_blob_sha"]) is not None
        and upstream["run_attempt"] == 1
        and upstream["conclusion"] == "success"
        and upstream["head_sha"] == source["commit_sha"]
        and upstream["overlay"]
        == {
            "direction": "nightly_to_product_state_to_evidence_index",
            "consumed": False,
            "artifact": None,
        },
        "index_upstream_invalid",
    )
    _safe_positive_integer(upstream["run_id"], "index_product_state_run_id")
    if expected_product_state_run_id is not None:
        _require(
            upstream["run_id"] == expected_product_state_run_id,
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
        and generator["run_attempt"] == 1
        and generator["event"] in {"workflow_run", "workflow_dispatch", "local_test"},
        "index_generator_invalid",
    )
    _safe_positive_integer(generator["run_id"], "index_generator_run_id")
    if expected_generator_run_id is not None:
        _require(
            generator["run_id"] == expected_generator_run_id,
            "expected_generator_run_id_mismatch",
        )
    _require(
        index["authority"]
        == {
            "technical_only": True,
            "scientific_validation": False,
            "legal_authority": False,
            "commercial_use": False,
            "engineering_design": False,
            "release": False,
        },
        "index_authority_promotion_forbidden",
    )
    rows = index["lanes"]
    _require(
        type(rows) is list
        and len(rows) == 5
        and tuple(row.get("lane_id") for row in rows) == LANE_IDS,
        "index_lane_order_invalid",
    )
    artifact_ids: set[int] = set()
    run_ids: set[int] = set()
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
                and artifact.get("workflow_run_id") == run_id
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
        len(run_ids) == 5 and len(artifact_ids) == 10, "index_global_identity_collision"
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
    _require(
        generator_event in {"workflow_run", "workflow_dispatch"},
        "generator_event_invalid",
    )
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
        repository=repository,
        source_sha=source_sha,
        tree_sha=tree_sha,
        generator_blob_sha=generator_blob_sha,
        product_state_blob_sha=product_state_blob_sha,
        generator_event=generator_event,
        generator_run_id=generator_run_id,
        product_state_run=product_state,
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
