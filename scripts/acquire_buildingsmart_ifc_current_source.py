#!/usr/bin/env python3
"""Acquire and verify the immutable buildingSMART IFC import-health corpus."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = Path(
    "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json"
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


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
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
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError("manifest_schema_version_invalid")
    if payload.get("storage_boundary") != (
        "download_to_gitignored_private_corpus_never_bundle_or_upload"
    ):
        raise ManifestError("manifest_storage_boundary_invalid")
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


def _download_exact(url: str, target: Path, row: dict[str, Any], *, kind: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{target.name}.",
            suffix=".download",
            dir=target.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            with urlopen(request, timeout=120) as response:  # noqa: S310 - pinned HTTPS URLs
                while chunk := response.read(1024 * 1024):
                    temporary.write(chunk)
        blockers = _validate_local_file(temporary_path, row, kind=kind)
        if blockers:
            raise OSError("downloaded_source_bytes_do_not_match_manifest")
        temporary_path.replace(target)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise


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
        download_error = ""
        if not local_path.exists() and download_missing:
            try:
                _download_exact(
                    str(row["download_url"]),
                    local_path,
                    row,
                    kind=kind,
                )
            except (HTTPError, URLError, OSError, TimeoutError) as exc:
                download_error = exc.__class__.__name__
        blockers = _validate_local_file(local_path, row, kind=kind)
        if download_error:
            blockers.append(f"source_download_failed:{kind}:{row_id}:{download_error}")
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
                "local_path": row["local_path"],
                "expected_byte_length": row["byte_length"],
                "observed_byte_length": local_path.stat().st_size
                if local_path.exists() and local_path.is_file()
                else 0,
                "expected_sha256": row["sha256"],
                "observed_sha256": _sha256(local_path)
                if local_path.exists() and local_path.is_file()
                else "",
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
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = write_acquisition_receipt(
            manifest_path=args.manifest,
            receipt_out=args.receipt_out,
            source_commit_sha=args.source_commit_sha,
            download_missing=not args.check,
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
    return 0 if payload["technical_contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
