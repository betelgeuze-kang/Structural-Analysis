#!/usr/bin/env python3
"""Acquire and verify the immutable buildingSMART IFC import-health corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(
    "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json"
)
DEFAULT_MANIFEST_SCHEMA = Path(
    "canonical/buildingsmart-ifc-current-source-manifest.v1.schema.json"
)
DEFAULT_RECEIPT = Path(".ci/ifc-import-health-current-source/acquisition-receipt.json")
SCHEMA_VERSION = "buildingsmart-ifc-current-source-manifest.v1"
RECEIPT_SCHEMA_VERSION = "buildingsmart-ifc-current-source-acquisition-receipt.v1"
EXPECTED_CASE_COUNT = 10
EXPECTED_CLEAN_CASE_COUNT = 2
EXPECTED_DIRTY_CASE_COUNT = 8
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
USER_AGENT = "structural-analysis-ifc-current-source/1"
DOWNLOAD_MAX_ATTEMPTS = 3
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_RETRY_DELAYS_SECONDS = (2, 5)
RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
MAX_FAILURE_DIAGNOSTIC_BYTES = 1024 * 1024
FAILURE_DIAGNOSTIC_SCHEMA_VERSION = "ifc-acquisition-failure-diagnostic.v1"

CERTIFICATION_REPOSITORY = "buildingSMART/Certification-datasets"
CERTIFICATION_COMMIT_SHA = "e6f1c1d80ac216e1c1d6f88d4650f13d8c8277b7"
COMMUNITY_REPOSITORY = "buildingsmart-community/Community-Sample-Test-Files"
COMMUNITY_COMMIT_SHA = "7ddf57a201f88a0c213d5322b02ed15e94a60a40"
CERTIFICATION_LICENSE_ID = "buildingsmart_certification_datasets_cc_by_4_0"
COMMUNITY_LICENSE_ID = "buildingsmart_community_samples_cc_by_4_0"
EXPECTED_CASE_LANES = {
    "buildingsmart_pcert_building_structural": "clean",
    "buildingsmart_pcert_infra_bridge": "clean",
    "buildingsmart_community_duplex_architectural": "dirty",
    "buildingsmart_community_duplex_electrical": "dirty",
    "buildingsmart_community_duplex_mep": "dirty",
    "buildingsmart_community_clinic_architectural": "dirty",
    "buildingsmart_community_clinic_electrical": "dirty",
    "buildingsmart_community_clinic_hvac": "dirty",
    "buildingsmart_community_clinic_plumbing": "dirty",
    "buildingsmart_community_clinic_structural": "dirty",
}
EXPECTED_AUTHORITY_CLAIMS = {
    "commercial_use_authority": False,
    "independent_reproduction": False,
    "product_legal_approval": False,
    "redistribution_authority": False,
    "release_authority": False,
    "scientific_validation_authority": False,
    "solver_geometry_or_topology_authority": False,
}
EXPECTED_CASE_PATHS = {
    "buildingsmart_pcert_building_structural": (
        "IFC 4.3.2.0 (IFC4X3_ADD2)/PCERT-Sample-Scene/Building-Structural.ifc",
        "private_corpus/phase3/buildingsmart/pcert/Building-Structural.ifc",
    ),
    "buildingsmart_pcert_infra_bridge": (
        "IFC 4.3.2.0 (IFC4X3_ADD2)/PCERT-Sample-Scene/Infra-Bridge.ifc",
        "private_corpus/phase3/buildingsmart/pcert/Infra-Bridge.ifc",
    ),
    "buildingsmart_community_duplex_architectural": (
        "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/Duplex_A_20110907.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_duplex_architectural/Duplex_A_20110907.ifc",
    ),
    "buildingsmart_community_duplex_electrical": (
        "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/Duplex_Electrical_20121207.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_duplex_electrical/Duplex_Electrical_20121207.ifc",
    ),
    "buildingsmart_community_duplex_mep": (
        "IFC 2.3.0.1 (IFC 2x3)/Duplex Apartment/Duplex_MEP_20110907.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_duplex_mep/Duplex_MEP_20110907.ifc",
    ),
    "buildingsmart_community_clinic_architectural": (
        "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_Architectural.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_clinic_architectural/Clinic_Architectural.ifc",
    ),
    "buildingsmart_community_clinic_electrical": (
        "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_Electrical.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_clinic_electrical/Clinic_Electrical.ifc",
    ),
    "buildingsmart_community_clinic_hvac": (
        "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_HVAC.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_clinic_hvac/Clinic_HVAC.ifc",
    ),
    "buildingsmart_community_clinic_plumbing": (
        "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_Plumbing.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_clinic_plumbing/Clinic_Plumbing.ifc",
    ),
    "buildingsmart_community_clinic_structural": (
        "IFC 2.3.0.1 (IFC 2x3)/Medical-Dental Clinic/Clinic_Structural.ifc",
        "private_corpus/phase3/buildingsmart/community/"
        "buildingsmart_community_clinic_structural/Clinic_Structural.ifc",
    ),
}
EXPECTED_LICENSE_ROWS = {
    CERTIFICATION_LICENSE_ID: {
        "authority_boundary": (
            "Upstream license bytes and SPDX identity are recorded; product/legal "
            "approval is not granted by this manifest."
        ),
        "byte_length": 317,
        "download_url": (
            "https://raw.githubusercontent.com/buildingSMART/Certification-datasets/"
            f"{CERTIFICATION_COMMIT_SHA}/LICENSE"
        ),
        "license_id": CERTIFICATION_LICENSE_ID,
        "local_path": (
            "private_corpus/phase3/buildingsmart/licenses/"
            "certification-datasets.LICENSE"
        ),
        "sha256": (
            "sha256:3e20c50b6edfdb4be207f64495586115d0574c8394538109d74f79e1d8976d18"
        ),
        "spdx_expression": "CC-BY-4.0",
        "upstream_commit_sha": CERTIFICATION_COMMIT_SHA,
        "upstream_path": "LICENSE",
        "upstream_repository": CERTIFICATION_REPOSITORY,
    },
    COMMUNITY_LICENSE_ID: {
        "authority_boundary": (
            "Upstream license bytes and SPDX identity are recorded; product/legal "
            "approval is not granted by this manifest."
        ),
        "byte_length": 217,
        "download_url": (
            "https://raw.githubusercontent.com/buildingsmart-community/"
            f"Community-Sample-Test-Files/{COMMUNITY_COMMIT_SHA}/LICENSE"
        ),
        "license_id": COMMUNITY_LICENSE_ID,
        "local_path": (
            "private_corpus/phase3/buildingsmart/licenses/"
            "community-sample-test-files.LICENSE"
        ),
        "sha256": (
            "sha256:53799fe3374cd952bfd3df62b617d105192b90ac350814aeea484b4593716bf0"
        ),
        "spdx_expression": "CC-BY-4.0",
        "upstream_commit_sha": COMMUNITY_COMMIT_SHA,
        "upstream_path": "LICENSE",
        "upstream_repository": COMMUNITY_REPOSITORY,
    },
}


class ManifestError(ValueError):
    """Raised when the tracked source manifest is not fail-closed."""


class DownloadIntegrityError(OSError):
    """Raised when downloaded bytes do not match the immutable manifest."""


class DownloadTruncatedError(OSError):
    """Raised when a transport closes before the immutable byte length arrives."""


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError(f"json_duplicate_key:{path}:{key}")
            result[key] = value
        return result

    payload = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=lambda token: (_ for _ in ()).throw(
            ManifestError(f"json_nonfinite_number:{path}:{token}")
        ),
    )

    def require_finite(value: Any, location: str = "$") -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ManifestError(f"json_nonfinite_number:{path}:{location}")
        if isinstance(value, dict):
            for key, nested in value.items():
                require_finite(nested, f"{location}.{key}")
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                require_finite(nested, f"{location}[{index}]")

    require_finite(payload)
    if not isinstance(payload, dict):
        raise ManifestError(f"json_object_required:{path}")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _manifest_sha256(path: Path) -> str:
    return _sha256(path)


def _required_string(row: dict[str, Any], key: str, row_id: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ManifestError(f"manifest_string_required:{row_id}:{key}")
    return value


def _required_positive_int(row: dict[str, Any], key: str, row_id: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ManifestError(f"manifest_positive_integer_required:{row_id}:{key}")
    return value


def _validate_artifact_row(
    row: dict[str, Any],
    *,
    row_id: str,
    kind: str,
) -> None:
    expected_sha256 = _required_string(row, "sha256", row_id)
    commit_sha = _required_string(row, "upstream_commit_sha", row_id)
    download_url = _required_string(row, "download_url", row_id)
    upstream_repository = _required_string(row, "upstream_repository", row_id)
    upstream_path = _required_string(row, "upstream_path", row_id)
    local_path = Path(_required_string(row, "local_path", row_id))
    _required_positive_int(row, "byte_length", row_id)
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise ManifestError(f"manifest_sha256_invalid:{row_id}")
    if COMMIT_RE.fullmatch(commit_sha) is None:
        raise ManifestError(f"manifest_commit_sha_invalid:{row_id}")
    if not upstream_path or upstream_path.startswith("/"):
        raise ManifestError(f"manifest_upstream_path_invalid:{row_id}")
    encoded_path = quote(upstream_path, safe="/")
    allowed_urls = {
        f"https://raw.githubusercontent.com/{upstream_repository}/{commit_sha}/{encoded_path}",
        (
            "https://media.githubusercontent.com/media/"
            f"{upstream_repository}/{commit_sha}/{encoded_path}"
        ),
    }
    if download_url not in allowed_urls:
        raise ManifestError(f"manifest_download_url_not_exact_commit_path:{row_id}")
    if local_path.is_absolute() or ".." in local_path.parts:
        raise ManifestError(f"manifest_local_path_invalid:{row_id}")
    if local_path.parts[:1] != ("private_corpus",):
        raise ManifestError(f"manifest_local_path_outside_private_corpus:{row_id}")
    if kind == "case" and local_path.suffix.lower() != ".ifc":
        raise ManifestError(f"manifest_ifc_suffix_invalid:{row_id}")


def validate_manifest(
    payload: dict[str, Any],
    *,
    require_canonical_identity: bool = True,
) -> dict[str, Any]:
    schema = _load_json(ROOT / DEFAULT_MANIFEST_SCHEMA)
    schema_errors = sorted(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if schema_errors:
        location = ".".join(str(part) for part in schema_errors[0].path) or "$"
        raise ManifestError(
            f"manifest_schema_invalid:{location}:{schema_errors[0].message}"
        )
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("manifest_schema_version_invalid")
    if payload.get("storage_boundary") != (
        "download_to_gitignored_private_corpus_never_bundle_or_upload"
    ):
        raise ManifestError("manifest_storage_boundary_invalid")
    if payload.get("authority_claims") != EXPECTED_AUTHORITY_CLAIMS:
        raise ManifestError("manifest_authority_claims_invalid")
    cases = payload.get("cases")
    licenses = payload.get("licenses")
    if not isinstance(cases, list) or not all(isinstance(row, dict) for row in cases):
        raise ManifestError("manifest_cases_invalid")
    if not isinstance(licenses, list) or not all(
        isinstance(row, dict) for row in licenses
    ):
        raise ManifestError("manifest_licenses_invalid")
    if (
        payload.get("case_count") != EXPECTED_CASE_COUNT
        or len(cases) != EXPECTED_CASE_COUNT
    ):
        raise ManifestError("manifest_case_count_invalid")
    if len(licenses) != 2:
        raise ManifestError("manifest_license_count_invalid")

    case_ids: set[str] = set()
    local_paths: set[str] = set()
    source_hashes: set[str] = set()
    source_coordinates: set[tuple[str, str, str]] = set()
    source_urls: set[str] = set()
    model_identities: set[str] = set()
    license_ids: set[str] = set()
    lanes: list[str] = []
    for row in licenses:
        license_id = _required_string(row, "license_id", "license")
        if license_id in license_ids:
            raise ManifestError(f"manifest_duplicate_license_id:{license_id}")
        license_ids.add(license_id)
        _validate_artifact_row(row, row_id=license_id, kind="license")
        if row.get("spdx_expression") != "CC-BY-4.0":
            raise ManifestError(f"manifest_license_spdx_invalid:{license_id}")
        if row.get("authority_boundary") != (
            "Upstream license bytes and SPDX identity are recorded; product/legal "
            "approval is not granted by this manifest."
        ):
            raise ManifestError(
                f"manifest_license_authority_boundary_invalid:{license_id}"
            )

    for row in cases:
        case_id = _required_string(row, "case_id", "case")
        if case_id in case_ids:
            raise ManifestError(f"manifest_duplicate_case_id:{case_id}")
        case_ids.add(case_id)
        _validate_artifact_row(row, row_id=case_id, kind="case")
        local_path = _required_string(row, "local_path", case_id)
        if local_path in local_paths:
            raise ManifestError(f"manifest_duplicate_local_path:{local_path}")
        local_paths.add(local_path)
        source_hash = _required_string(row, "sha256", case_id)
        coordinate = (
            _required_string(row, "upstream_repository", case_id),
            _required_string(row, "upstream_commit_sha", case_id),
            _required_string(row, "upstream_path", case_id),
        )
        source_url = _required_string(row, "download_url", case_id)
        model_identity = _required_string(row, "model_identity_sha256", case_id)
        if model_identity != source_hash:
            raise ManifestError(f"manifest_model_identity_not_exact_bytes:{case_id}")
        for value, values, reason in (
            (source_hash, source_hashes, "source_sha256"),
            (coordinate, source_coordinates, "source_coordinate"),
            (source_url, source_urls, "download_url"),
            (model_identity, model_identities, "model_identity"),
        ):
            if value in values:
                raise ManifestError(f"manifest_duplicate_{reason}:{case_id}")
            values.add(value)
        lane_kind = _required_string(row, "lane_kind", case_id)
        if lane_kind not in {"clean", "dirty"}:
            raise ManifestError(f"manifest_lane_kind_invalid:{case_id}")
        lanes.append(lane_kind)
        license_id = _required_string(row, "license_id", case_id)
        if license_id not in license_ids:
            raise ManifestError(f"manifest_unknown_license_id:{case_id}:{license_id}")
        if row.get("filename") != Path(local_path).name:
            raise ManifestError(f"manifest_filename_local_path_mismatch:{case_id}")
    if lanes.count("clean") != EXPECTED_CLEAN_CASE_COUNT:
        raise ManifestError("manifest_clean_case_count_invalid")
    if lanes.count("dirty") != EXPECTED_DIRTY_CASE_COUNT:
        raise ManifestError("manifest_dirty_case_count_invalid")
    if require_canonical_identity:
        if case_ids != set(EXPECTED_CASE_LANES):
            raise ManifestError("manifest_canonical_case_set_invalid")
        for row in cases:
            case_id = str(row["case_id"])
            expected_lane = EXPECTED_CASE_LANES[case_id]
            if row.get("lane_kind") != expected_lane:
                raise ManifestError(
                    f"manifest_canonical_case_lane_invalid:{case_id}"
                )
            expected_license = (
                CERTIFICATION_LICENSE_ID
                if expected_lane == "clean"
                else COMMUNITY_LICENSE_ID
            )
            expected_repository = (
                CERTIFICATION_REPOSITORY
                if expected_lane == "clean"
                else COMMUNITY_REPOSITORY
            )
            expected_commit = (
                CERTIFICATION_COMMIT_SHA
                if expected_lane == "clean"
                else COMMUNITY_COMMIT_SHA
            )
            if row.get("license_id") != expected_license:
                raise ManifestError(
                    f"manifest_canonical_case_license_invalid:{case_id}"
                )
            if row.get("upstream_repository") != expected_repository:
                raise ManifestError(
                    f"manifest_canonical_case_repository_invalid:{case_id}"
                )
            if row.get("upstream_commit_sha") != expected_commit:
                raise ManifestError(
                    f"manifest_canonical_case_commit_invalid:{case_id}"
                )
            expected_upstream_path, expected_local_path = EXPECTED_CASE_PATHS[case_id]
            if row.get("upstream_path") != expected_upstream_path:
                raise ManifestError(
                    f"manifest_canonical_case_upstream_path_invalid:{case_id}"
                )
            if row.get("local_path") != expected_local_path:
                raise ManifestError(
                    f"manifest_canonical_case_local_path_invalid:{case_id}"
                )
        license_map = {str(row["license_id"]): row for row in licenses}
        if set(license_map) != set(EXPECTED_LICENSE_ROWS):
            raise ManifestError("manifest_canonical_license_set_invalid")
        for license_id, expected_row in EXPECTED_LICENSE_ROWS.items():
            if license_map[license_id] != expected_row:
                raise ManifestError(
                    f"manifest_canonical_license_identity_invalid:{license_id}"
                )
    return payload


def load_manifest(
    *,
    repo_root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    require_canonical_identity: bool = True,
) -> tuple[dict[str, Any], Path]:
    resolved = (
        manifest_path if manifest_path.is_absolute() else repo_root / manifest_path
    )
    if not resolved.exists():
        raise ManifestError(f"manifest_missing:{manifest_path.as_posix()}")
    return (
        validate_manifest(
            _load_json(resolved),
            require_canonical_identity=require_canonical_identity,
        ),
        resolved,
    )


def _private_path(repo_root: Path, declared_path: str) -> Path:
    root = repo_root.resolve()
    resolved = (root / declared_path).resolve()
    private_root = (root / "private_corpus").resolve()
    try:
        resolved.relative_to(private_root)
    except ValueError as exc:
        raise ManifestError(
            f"resolved_path_outside_private_corpus:{declared_path}"
        ) from exc
    return resolved


def _artifact_rows(manifest: dict[str, Any]) -> Iterable[tuple[str, dict[str, Any]]]:
    for row in manifest["licenses"]:
        yield "license", row
    for row in manifest["cases"]:
        yield "case", row


def _validate_local_file(path: Path, row: dict[str, Any], *, kind: str) -> list[str]:
    blockers: list[str] = []
    row_id = str(row.get("case_id") or row.get("license_id"))
    if not path.exists() or not path.is_file():
        return [f"source_file_missing:{kind}:{row_id}"]
    observed_size = path.stat().st_size
    if observed_size != row["byte_length"]:
        blockers.append(f"source_byte_length_mismatch:{kind}:{row_id}")
    observed_sha256 = _sha256(path)
    if observed_sha256 != row["sha256"]:
        blockers.append(f"source_sha256_mismatch:{kind}:{row_id}")
    if kind == "case":
        with path.open("rb") as handle:
            prefix = handle.read(64).lstrip()
        if not prefix.startswith(b"ISO-10303-21;"):
            blockers.append(f"source_ifc_header_invalid:{row_id}")
    return blockers


def _download_policy() -> dict[str, Any]:
    return {
        "max_attempts": DOWNLOAD_MAX_ATTEMPTS,
        "retry_delays_seconds": list(DOWNLOAD_RETRY_DELAYS_SECONDS),
        "timeout_seconds": DOWNLOAD_TIMEOUT_SECONDS,
    }


def _not_requested_download_evidence() -> dict[str, Any]:
    return {
        **_download_policy(),
        "attempt_count": 0,
        "error_events": [],
        "recovered_after_retry": False,
        "requested": False,
        "status": "not_requested",
    }


def _download_error_kind(
    exc: BaseException,
    *,
    transport_stage: bool,
) -> str:
    if isinstance(exc, DownloadIntegrityError):
        return "integrity"
    if isinstance(exc, DownloadTruncatedError):
        return "truncated_transport"
    if isinstance(exc, HTTPError):
        return "http_status"
    if not transport_stage:
        return "local_io"
    if isinstance(exc, URLError):
        return "url_transport"
    if isinstance(exc, TimeoutError):
        return "timeout_transport"
    if isinstance(exc, HTTPException):
        return "http_protocol"
    if isinstance(exc, ConnectionError):
        return "connection_transport"
    if isinstance(exc, OSError):
        return "os_transport"
    raise AssertionError("download_error_kind_unreachable")


def _is_retryable_download_error(exc: BaseException, *, error_kind: str) -> bool:
    if error_kind == "http_status":
        return isinstance(exc, HTTPError) and exc.code in RETRYABLE_HTTP_STATUSES
    return error_kind in {
        "connection_transport",
        "http_protocol",
        "os_transport",
        "timeout_transport",
        "truncated_transport",
        "url_transport",
    }


def _download_exact(
    url: str,
    target: Path,
    row: dict[str, Any],
    *,
    kind: str,
    opener: Any | None = None,
    sleeper: Any | None = None,
) -> dict[str, Any]:
    """Download immutable bytes with bounded retries and stable error evidence."""

    target.parent.mkdir(parents=True, exist_ok=True)
    open_url = urlopen if opener is None else opener
    sleep = time.sleep if sleeper is None else sleeper
    error_events: list[dict[str, Any]] = []
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        request = Request(url, headers={"User-Agent": USER_AGENT})
        temporary_path: Path | None = None
        transport_stage = False
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{target.name}.",
                suffix=".download",
                dir=target.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                transport_stage = True
                with open_url(  # noqa: S310 - pinned HTTPS URLs from strict manifest
                    request,
                    timeout=DOWNLOAD_TIMEOUT_SECONDS,
                ) as response:
                    downloaded_size = 0
                    while chunk := response.read(1024 * 1024):
                        downloaded_size += len(chunk)
                        if downloaded_size > row["byte_length"]:
                            raise DownloadIntegrityError(
                                "downloaded_source_exceeds_manifest_byte_length"
                            )
                        transport_stage = False
                        temporary.write(chunk)
                        transport_stage = True
                    if downloaded_size < row["byte_length"]:
                        raise DownloadTruncatedError(
                            "downloaded_source_shorter_than_manifest_byte_length"
                        )
                transport_stage = False
            blockers = _validate_local_file(temporary_path, row, kind=kind)
            if blockers:
                raise DownloadIntegrityError(
                    "downloaded_source_bytes_do_not_match_manifest"
                )
            temporary_path.replace(target)
            return {
                **_download_policy(),
                "attempt_count": attempt,
                "error_events": error_events,
                "recovered_after_retry": bool(error_events),
                "requested": True,
                "status": "succeeded",
            }
        except (HTTPError, URLError, HTTPException, OSError, TimeoutError) as exc:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            error_kind = _download_error_kind(
                exc,
                transport_stage=transport_stage,
            )
            event: dict[str, Any] = {
                "attempt": attempt,
                "error_class": exc.__class__.__name__,
                "error_kind": error_kind,
                "retryable": _is_retryable_download_error(
                    exc,
                    error_kind=error_kind,
                ),
            }
            if isinstance(exc, HTTPError):
                event["http_status"] = int(exc.code)
            error_events.append(event)
            if event["retryable"] and attempt < DOWNLOAD_MAX_ATTEMPTS:
                sleep(DOWNLOAD_RETRY_DELAYS_SECONDS[attempt - 1])
            else:
                break
        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise
    return {
        **_download_policy(),
        "attempt_count": len(error_events),
        "error_events": error_events,
        "recovered_after_retry": False,
        "requested": True,
        "status": "failed",
    }


def build_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    source_commit_sha: str,
    download_missing: bool,
    require_canonical_identity: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    if COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise ManifestError("source_commit_sha_invalid")
    manifest, resolved_manifest = load_manifest(
        repo_root=repo_root,
        manifest_path=manifest_path,
        require_canonical_identity=require_canonical_identity,
    )
    artifacts: list[dict[str, Any]] = []
    for kind, row in _artifact_rows(manifest):
        row_id = str(row.get("case_id") or row.get("license_id"))
        local_path = _private_path(repo_root, str(row["local_path"]))
        download = _not_requested_download_evidence()
        if not local_path.exists() and download_missing:
            download = _download_exact(
                str(row["download_url"]),
                local_path,
                row,
                kind=kind,
            )
        blockers = _validate_local_file(local_path, row, kind=kind)
        if download["status"] == "failed":
            error_class = download["error_events"][-1]["error_class"]
            blockers.append(
                f"source_download_failed:{kind}:{row_id}:{error_class}"
            )
        artifacts.append(
            {
                "artifact_kind": kind,
                "artifact_id": row_id,
                "case_id": row.get("case_id", ""),
                "lane_kind": row.get("lane_kind", ""),
                "license_id": row.get("license_id", ""),
                "upstream_repository": row["upstream_repository"],
                "upstream_commit_sha": row["upstream_commit_sha"],
                "upstream_path": row["upstream_path"],
                "download_url": row["download_url"],
                "local_path": row["local_path"],
                "model_identity_sha256": row.get("model_identity_sha256", ""),
                "expected_byte_length": row["byte_length"],
                "observed_byte_length": local_path.stat().st_size
                if local_path.exists() and local_path.is_file()
                else 0,
                "expected_sha256": row["sha256"],
                "observed_sha256": _sha256(local_path)
                if local_path.exists() and local_path.is_file()
                else "",
                "download": download,
                "verified": not blockers,
                "blockers": sorted(set(blockers)),
            }
        )
    blockers = sorted(
        {blocker for artifact in artifacts for blocker in artifact["blockers"]}
    )
    case_rows = [row for row in artifacts if row["artifact_kind"] == "case"]
    license_rows = [row for row in artifacts if row["artifact_kind"] == "license"]
    technical_contract_pass = bool(
        len(case_rows) == EXPECTED_CASE_COUNT
        and all(row["verified"] for row in case_rows)
        and len(license_rows) == 2
        and all(row["verified"] for row in license_rows)
        and not blockers
    )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": source_commit_sha,
        "manifest_path": resolved_manifest.relative_to(repo_root).as_posix(),
        "manifest_sha256": _manifest_sha256(resolved_manifest),
        "status": "ready" if technical_contract_pass else "blocked",
        "technical_contract_pass": technical_contract_pass,
        "case_count": len(case_rows),
        "verified_case_count": sum(1 for row in case_rows if row["verified"]),
        "clean_case_count": sum(1 for row in case_rows if row["lane_kind"] == "clean"),
        "dirty_case_count": sum(1 for row in case_rows if row["lane_kind"] == "dirty"),
        "license_material_count": len(license_rows),
        "verified_license_material_count": sum(
            1 for row in license_rows if row["verified"]
        ),
        "artifacts": artifacts,
        "blockers": blockers,
        "product_legal_approval": False,
        "redistribution_authority": False,
        "commercial_use_authority": False,
        "release_authority": False,
        "claim_boundary": (
            "A ready receipt proves that the ten private-corpus IFC inputs and two upstream "
            "license files match the immutable manifest bytes. It does not upload raw IFC "
            "files or grant product/legal, redistribution, commercial-use, solver-geometry, "
            "independent-reproduction, or release authority."
        ),
    }


def write_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    receipt_out: Path = DEFAULT_RECEIPT,
    source_commit_sha: str,
    download_missing: bool,
) -> dict[str, Any]:
    payload = build_acquisition_receipt(
        repo_root=repo_root,
        manifest_path=manifest_path,
        source_commit_sha=source_commit_sha,
        download_missing=download_missing,
    )
    resolved = receipt_out if receipt_out.is_absolute() else repo_root / receipt_out
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(_json_text(payload), encoding="utf-8")
    return payload


def acquisition_reverification_view(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = json.loads(_json_text(payload))
    normalized.pop("generated_at", None)
    artifacts = normalized.get("artifacts")
    if isinstance(artifacts, list):
        for row in artifacts:
            if isinstance(row, dict):
                _validate_download_evidence(row.get("download"))
                row.pop("download", None)
    return normalized


def _validate_download_evidence(value: Any) -> None:
    expected_keys = {
        "attempt_count",
        "error_events",
        "max_attempts",
        "recovered_after_retry",
        "requested",
        "retry_delays_seconds",
        "status",
        "timeout_seconds",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise ManifestError("acquisition_download_evidence_invalid")
    if (
        value["max_attempts"] != DOWNLOAD_MAX_ATTEMPTS
        or value["timeout_seconds"] != DOWNLOAD_TIMEOUT_SECONDS
        or value["retry_delays_seconds"] != list(DOWNLOAD_RETRY_DELAYS_SECONDS)
        or type(value["attempt_count"]) is not int
        or not 0 <= value["attempt_count"] <= DOWNLOAD_MAX_ATTEMPTS
        or type(value["requested"]) is not bool
        or type(value["recovered_after_retry"]) is not bool
        or not isinstance(value["error_events"], list)
        or not isinstance(value["status"], str)
        or value["status"] not in {"failed", "not_requested", "succeeded"}
    ):
        raise ManifestError("acquisition_download_evidence_invalid")
    events = value["error_events"]
    for index, event in enumerate(events, 1):
        if (
            not isinstance(event, dict)
            or set(event)
            not in (
                {"attempt", "error_class", "error_kind", "retryable"},
                {
                    "attempt",
                    "error_class",
                    "error_kind",
                    "http_status",
                    "retryable",
                },
            )
            or event.get("attempt") != index
            or not isinstance(event.get("error_class"), str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", event["error_class"])
            is None
            or type(event.get("retryable")) is not bool
            or event.get("error_kind")
            not in {
                "connection_transport",
                "http_protocol",
                "http_status",
                "integrity",
                "local_io",
                "os_transport",
                "timeout_transport",
                "truncated_transport",
                "url_transport",
            }
            or (
                "http_status" in event
                and (
                    type(event["http_status"]) is not int
                    or not 100 <= event["http_status"] <= 599
                )
            )
        ):
            raise ManifestError("acquisition_download_event_invalid")
        kind = event["error_kind"]
        if kind == "http_status":
            classification_valid = (
                event["error_class"] == "HTTPError" and "http_status" in event
            )
            expected_retryable = (
                event.get("http_status") in RETRYABLE_HTTP_STATUSES
                if classification_valid
                else False
            )
        else:
            expected_retryable = kind not in {"integrity", "local_io"}
            classification_valid = "http_status" not in event
            if kind == "integrity":
                classification_valid = (
                    classification_valid
                    and event["error_class"] == "DownloadIntegrityError"
                )
            elif kind == "truncated_transport":
                classification_valid = (
                    classification_valid
                    and event["error_class"] == "DownloadTruncatedError"
                )
        if (
            not classification_valid
            or event["retryable"] is not expected_retryable
        ):
            raise ManifestError("acquisition_download_event_classification_invalid")
        reserved_kinds = {
            "DownloadIntegrityError": "integrity",
            "DownloadTruncatedError": "truncated_transport",
            "HTTPError": "http_status",
            "HTTPException": "http_protocol",
            "URLError": "url_transport",
        }
        reserved_kind = reserved_kinds.get(event["error_class"])
        if reserved_kind is not None and kind != reserved_kind:
            raise ManifestError("acquisition_download_event_classification_invalid")
    if value["status"] == "not_requested":
        valid = (
            value["requested"] is False
            and value["attempt_count"] == 0
            and events == []
            and value["recovered_after_retry"] is False
        )
    elif value["status"] == "succeeded":
        valid = (
            value["requested"] is True
            and value["attempt_count"] == len(events) + 1
            and 1 <= value["attempt_count"] <= DOWNLOAD_MAX_ATTEMPTS
            and all(event["retryable"] is True for event in events)
            and value["recovered_after_retry"] is bool(events)
        )
    else:
        prior_events = events[:-1]
        final_event = events[-1:] or [{}]
        valid = (
            value["requested"] is True
            and value["attempt_count"] == len(events)
            and 1 <= value["attempt_count"] <= DOWNLOAD_MAX_ATTEMPTS
            and all(event["retryable"] is True for event in prior_events)
            and (
                final_event[0].get("retryable") is False
                or value["attempt_count"] == DOWNLOAD_MAX_ATTEMPTS
            )
            and value["recovered_after_retry"] is False
        )
    if not valid:
        raise ManifestError("acquisition_download_evidence_invalid")


def _read_bounded_failure_diagnostic(
    path: Path,
) -> tuple[dict[str, Any], str]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ManifestError("acquisition_diagnostic_open_invalid") from exc
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or not 0 < info.st_size <= MAX_FAILURE_DIAGNOSTIC_BYTES
        ):
            raise ManifestError("acquisition_diagnostic_file_invalid")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ManifestError("acquisition_diagnostic_size_changed")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ManifestError("acquisition_diagnostic_size_changed")
    finally:
        os.close(descriptor)

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError("acquisition_diagnostic_duplicate_key")
            result[key] = value
        return result

    try:
        payload = json.loads(
            b"".join(chunks),
            object_pairs_hook=unique_object,
            parse_constant=lambda _token: (_ for _ in ()).throw(
                ManifestError("acquisition_diagnostic_nonfinite")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError("acquisition_diagnostic_json_invalid") from exc
    if not isinstance(payload, dict):
        raise ManifestError("acquisition_diagnostic_contract_invalid")
    raw = b"".join(chunks)
    return payload, f"sha256:{hashlib.sha256(raw).hexdigest()}"


def validate_failure_diagnostic(
    *,
    receipt_path: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    """Validate a blocked receipt and return its bounded sanitized diagnostic."""

    if COMMIT_RE.fullmatch(source_commit_sha) is None:
        raise ManifestError("source_commit_sha_invalid")
    payload, receipt_sha256 = _read_bounded_failure_diagnostic(receipt_path)
    top_keys = {
        "artifacts",
        "blockers",
        "case_count",
        "claim_boundary",
        "clean_case_count",
        "commercial_use_authority",
        "dirty_case_count",
        "generated_at",
        "license_material_count",
        "manifest_path",
        "manifest_sha256",
        "product_legal_approval",
        "redistribution_authority",
        "release_authority",
        "schema_version",
        "source_commit_sha",
        "status",
        "technical_contract_pass",
        "verified_case_count",
        "verified_license_material_count",
    }
    artifact_keys = {
        "artifact_id",
        "artifact_kind",
        "blockers",
        "case_id",
        "download",
        "download_url",
        "expected_byte_length",
        "expected_sha256",
        "lane_kind",
        "license_id",
        "local_path",
        "model_identity_sha256",
        "observed_byte_length",
        "observed_sha256",
        "upstream_commit_sha",
        "upstream_path",
        "upstream_repository",
        "verified",
    }
    if set(payload) != top_keys:
        raise ManifestError("acquisition_diagnostic_contract_invalid")
    artifacts = payload["artifacts"]
    blockers = payload["blockers"]
    if (
        payload["schema_version"] != RECEIPT_SCHEMA_VERSION
        or payload["source_commit_sha"] != source_commit_sha
        or payload["status"] != "blocked"
        or payload["technical_contract_pass"] is not False
        or payload["case_count"] != EXPECTED_CASE_COUNT
        or payload["clean_case_count"] != EXPECTED_CLEAN_CASE_COUNT
        or payload["dirty_case_count"] != EXPECTED_DIRTY_CASE_COUNT
        or payload["license_material_count"] != 2
        or not isinstance(blockers, list)
        or not blockers
        or not all(isinstance(item, str) and item for item in blockers)
        or not isinstance(artifacts, list)
        or len(artifacts) != EXPECTED_CASE_COUNT + 2
        or any(
            payload[key] is not False
            for key in (
                "commercial_use_authority",
                "product_legal_approval",
                "redistribution_authority",
                "release_authority",
            )
        )
    ):
        raise ManifestError("acquisition_diagnostic_identity_invalid")
    identities: set[tuple[str, str]] = set()
    for row in artifacts:
        if not isinstance(row, dict) or set(row) != artifact_keys:
            raise ManifestError("acquisition_diagnostic_artifact_invalid")
        _validate_download_evidence(row["download"])
        identity = (str(row["artifact_kind"]), str(row["artifact_id"]))
        if identity in identities:
            raise ManifestError("acquisition_diagnostic_artifact_duplicate")
        identities.add(identity)
    expected_identities = {
        ("case", case_id) for case_id in EXPECTED_CASE_LANES
    } | {
        ("license", CERTIFICATION_LICENSE_ID),
        ("license", COMMUNITY_LICENSE_ID),
    }
    if identities != expected_identities:
        raise ManifestError("acquisition_diagnostic_artifact_set_invalid")
    acquisition_reverification_view(payload)
    if any(type(row["verified"]) is not bool for row in artifacts):
        raise ManifestError("acquisition_diagnostic_verified_flag_invalid")
    verified_case_count = sum(
        row["verified"] for row in artifacts if row["artifact_kind"] == "case"
    )
    verified_license_count = sum(
        row["verified"] for row in artifacts if row["artifact_kind"] == "license"
    )
    for key, upper_bound in (
        ("verified_case_count", EXPECTED_CASE_COUNT),
        ("verified_license_material_count", 2),
    ):
        value = payload[key]
        if type(value) is not int or not 0 <= value <= upper_bound:
            raise ManifestError("acquisition_diagnostic_count_invalid")
    if (
        payload["verified_case_count"] != verified_case_count
        or payload["verified_license_material_count"] != verified_license_count
    ):
        raise ManifestError("acquisition_diagnostic_count_mismatch")
    failed_artifacts: list[dict[str, Any]] = []
    for row in artifacts:
        if row["verified"]:
            continue
        download = row["download"]
        error_events = [
            {
                key: event[key]
                for key in (
                    "attempt",
                    "error_class",
                    "error_kind",
                    "http_status",
                    "retryable",
                )
                if key in event
            }
            for event in download["error_events"]
        ]
        failure_categories: list[str] = []
        if download["status"] == "failed":
            failure_categories.append("download_failed")
        if (
            row["observed_byte_length"] != row["expected_byte_length"]
            or row["observed_sha256"] != row["expected_sha256"]
        ):
            failure_categories.append("exact_byte_identity_failed")
        if row["artifact_kind"] == "case" and not row["observed_sha256"]:
            failure_categories.append("ifc_header_not_observed")
        if not failure_categories:
            failure_categories.append("artifact_contract_failed")
        failed_artifacts.append(
            {
                "artifact_id": row["artifact_id"],
                "artifact_kind": row["artifact_kind"],
                "download_attempt_count": download["attempt_count"],
                "download_error_events": error_events,
                "download_status": download["status"],
                "failure_categories": sorted(set(failure_categories)),
            }
        )
    if not failed_artifacts:
        raise ManifestError("acquisition_diagnostic_failed_artifact_missing")
    return {
        "authority_claims": {
            "commercial_use_authority": False,
            "independent_reproduction": False,
            "product_legal_approval": False,
            "redistribution_authority": False,
            "release_authority": False,
        },
        "counts": {
            "case_count": payload["case_count"],
            "license_material_count": payload["license_material_count"],
            "verified_case_count": verified_case_count,
            "verified_license_material_count": verified_license_count,
        },
        "diagnostic_only": True,
        "failed_artifacts": failed_artifacts,
        "producer_receipt_sha256": receipt_sha256,
        "raw_ifc_files_uploaded": False,
        "schema_version": FAILURE_DIAGNOSTIC_SCHEMA_VERSION,
        "source_commit_sha": source_commit_sha,
    }


def write_failure_diagnostic(
    *,
    receipt_path: Path,
    output_path: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    payload = validate_failure_diagnostic(
        receipt_path=receipt_path,
        source_commit_sha=source_commit_sha,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=output_path.parent,
        delete=False,
    ) as temporary:
        temporary.write(_json_text(payload))
        temporary_path = Path(temporary.name)
    temporary_path.chmod(0o400)
    temporary_path.replace(output_path)
    return payload


def check_acquisition_receipt(
    *,
    repo_root: Path = ROOT,
    manifest_path: Path = DEFAULT_MANIFEST,
    receipt_out: Path = DEFAULT_RECEIPT,
    source_commit_sha: str,
) -> dict[str, Any]:
    """Reverify local bytes without erasing the producer's download evidence."""

    repo_root = repo_root.resolve()
    resolved = receipt_out if receipt_out.is_absolute() else repo_root / receipt_out
    if not resolved.is_file() or resolved.is_symlink():
        raise ManifestError("acquisition_receipt_missing_for_check")
    persisted = _load_json(resolved)
    replayed = build_acquisition_receipt(
        repo_root=repo_root,
        manifest_path=manifest_path,
        source_commit_sha=source_commit_sha,
        download_missing=False,
    )
    if replayed["technical_contract_pass"] is not True:
        resolved.write_text(_json_text(replayed), encoding="utf-8")
        return replayed
    if acquisition_reverification_view(persisted) != acquisition_reverification_view(
        replayed
    ):
        raise ManifestError("acquisition_receipt_reverification_mismatch")
    return persisted


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--receipt-out", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--source-commit-sha", required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the private corpus without downloading missing inputs",
    )
    parser.add_argument(
        "--validate-failure-diagnostic",
        action="store_true",
        help="validate a blocked JSON receipt for diagnostic-only upload",
    )
    parser.add_argument("--failure-diagnostic-out", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.check and args.validate_failure_diagnostic:
        print("IFC current-source acquisition: blocked | incompatible_modes")
        return 1
    if args.validate_failure_diagnostic:
        if args.failure_diagnostic_out is None:
            print(
                "IFC current-source acquisition diagnostic: blocked | "
                "failure_diagnostic_out_required"
            )
            return 1
        resolved = (
            args.receipt_out
            if args.receipt_out.is_absolute()
            else ROOT / args.receipt_out
        )
        output = (
            args.failure_diagnostic_out
            if args.failure_diagnostic_out.is_absolute()
            else ROOT / args.failure_diagnostic_out
        )
        try:
            write_failure_diagnostic(
                receipt_path=resolved,
                output_path=output,
                source_commit_sha=args.source_commit_sha,
            )
        except (ManifestError, json.JSONDecodeError) as exc:
            print(f"IFC current-source acquisition diagnostic: blocked | {exc}")
            return 1
        print("IFC current-source acquisition diagnostic: valid")
        return 0
    try:
        if args.check:
            payload = check_acquisition_receipt(
                manifest_path=args.manifest,
                receipt_out=args.receipt_out,
                source_commit_sha=args.source_commit_sha,
            )
        else:
            payload = write_acquisition_receipt(
                manifest_path=args.manifest,
                receipt_out=args.receipt_out,
                source_commit_sha=args.source_commit_sha,
                download_missing=True,
            )
    except (ManifestError, json.JSONDecodeError) as exc:
        print(f"IFC current-source acquisition: blocked | {exc}")
        return 1
    if args.json:
        print(_json_text(payload), end="")
    else:
        print(
            "IFC current-source acquisition: "
            f"{payload['status']} | cases={payload['verified_case_count']}/"
            f"{payload['case_count']} | licenses="
            f"{payload['verified_license_material_count']}/"
            f"{payload['license_material_count']}"
        )
    if payload["technical_contract_pass"] is not True:
        for blocker in payload.get("blockers", []):
            print(f"IFC current-source acquisition blocker: {blocker}", file=sys.stderr)
    return 0 if payload["technical_contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
