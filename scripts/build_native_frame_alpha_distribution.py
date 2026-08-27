#!/usr/bin/env python3
"""Build and verify the bounded portable Frame Alpha CLI distribution."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import stat
import subprocess
import sys
import tempfile
import threading
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_native_dependency_licenses import (  # noqa: E402
    FIRST_PARTY_POLICY,
    check_dependency_licenses,
)

PACKAGE_VERSION = "0.1.0"
MANIFEST_SCHEMA = "structural-frame-alpha-cli-distribution.v1"
SMOKE_SCHEMA = "structural-frame-alpha-cli-distribution-smoke.v1"
WORKSTATION_MANIFEST_SCHEMA = "structural-frame-alpha-workstation-distribution.v2"
WORKSTATION_SMOKE_SCHEMA = "structural-frame-alpha-workstation-distribution-smoke.v2"
PLATFORMS = ("linux-x86_64-gnu", "windows-x86_64-msvc")
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024
MAX_WORKSTATION_FILES = 512
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MANIFEST_AUTHORITY = {
    "package_construction": "bounded_candidate",
    "same_runner_clean_extract": "not_evaluated_in_manifest",
    "clean_machine_installation": "not_evaluated",
    "linux_windows_parity": "not_established",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
SMOKE_AUTHORITY = {
    "same_runner_clean_extract": "passed",
    "clean_machine_installation": "not_evaluated",
    "linux_windows_parity": "not_established_by_one_receipt",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
MANIFEST_CLAIM = (
    "portable_cli_distribution_construction_not_installer_clean_machine_or_"
    "release_authority"
)
SMOKE_CLAIM = (
    "same_runner_clean_extract_validate_and_analyze_smoke_not_clean_machine_or_"
    "release_authority"
)
WORKSTATION_MANIFEST_AUTHORITY = {
    "package_construction": "bounded_candidate",
    "workbench_static_files": "hash_bound_operator_supplied_build",
    "same_runner_extracted_loopback_host": "not_evaluated_in_manifest",
    "browser_execution": "not_evaluated",
    "clean_machine_installation": "not_evaluated",
    "linux_windows_parity": "not_established",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
WORKSTATION_SMOKE_AUTHORITY = {
    "same_runner_extracted_loopback_host": "passed",
    "browser_execution": "not_evaluated",
    "clean_machine_installation": "not_evaluated",
    "linux_windows_parity": "not_established_by_one_receipt",
    "engineering_design": "not_authoritative",
    "commercial_use": "not_authoritative",
    "release_readiness": "not_authoritative",
}
WORKSTATION_MANIFEST_CLAIM = (
    "hash_bound_cli_and_workbench_static_distribution_not_installer_browser_"
    "execution_clean_machine_or_release_authority"
)
WORKSTATION_SMOKE_CLAIM = (
    "same_runner_clean_extract_loopback_static_and_capability_smoke_not_browser_"
    "execution_clean_machine_or_release_authority"
)
WORKBENCH_SUBMISSION_URL = "/api/v1/frame3d/jobs"
LICENSE_SBOM_PATH = "SBOM.native-license.json"


class DistributionError(RuntimeError):
    """Raised when a distribution candidate fails closed."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _strict_json(value: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise DistributionError(f"{label}_duplicate_key:{key}")
            result[key] = item
        return result

    try:
        decoded = value.decode("utf-8")
        payload = json.loads(
            decoded,
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                DistributionError(f"{label}_nonfinite:{token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DistributionError(f"{label}_invalid_json:{error}") from error
    if not isinstance(payload, dict):
        raise DistributionError(f"{label}_must_be_object")
    return payload


def _native_license_sbom() -> bytes:
    payload = check_dependency_licenses(ROOT)
    if payload.get("contract_pass") is not True:
        blockers = payload.get("blockers")
        detail = ",".join(str(item) for item in blockers) if blockers else "unknown"
        raise DistributionError(f"native_license_sbom_blocked:{detail}")
    first_party = payload.get("first_party_license")
    release_clearance = payload.get("release_clearance")
    if (
        not isinstance(first_party, dict)
        or first_party.get("contract_pass") is not True
        or first_party.get("posture") != FIRST_PARTY_POLICY["posture"]
        or first_party.get("license_ref") != FIRST_PARTY_POLICY["license_ref"]
        or not isinstance(first_party.get("workspace_package_count"), int)
        or int(first_party["workspace_package_count"]) < 1
        or release_clearance
        != {
            "status": "blocked",
            "product_license_approval": False,
            "commercial_redistribution_approved": False,
            "third_party_redistribution_clearance": "not_established",
            "blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
        }
    ):
        raise DistributionError("native_license_sbom_authority_invalid")
    return _canonical_bytes(payload) + b"\n"


def _license_manifest(
    files: dict[str, tuple[bytes, str, bool]],
) -> dict[str, Any]:
    return {
        "repository_posture": FIRST_PARTY_POLICY["posture"],
        "license_ref": FIRST_PARTY_POLICY["license_ref"],
        "license_path": "LICENSE",
        "license_sha256": _sha256_bytes(files["LICENSE"][0]),
        "sbom_path": LICENSE_SBOM_PATH,
        "sbom_sha256": _sha256_bytes(files[LICENSE_SBOM_PATH][0]),
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "release_clearance": "blocked",
        "release_blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
    }


def _require_file(path: Path, label: str, *, maximum: int = MAX_FILE_BYTES) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise DistributionError(f"{label}_must_be_regular_file:{path}")
    size = path.stat().st_size
    if size < 1 or size > maximum:
        raise DistributionError(f"{label}_size_invalid:{size}")
    return path.read_bytes()


def _command(
    command: list[str], label: str, *, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DistributionError(f"{label}_failed:{completed.returncode}:{detail}")
    return completed


def _git_sha(value: str, label: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise DistributionError(f"{label}_invalid")
    return value


def _verify_source_checkout(source_commit: str, source_tree: str) -> None:
    head = _command(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        "source_checkout_head",
        timeout=15,
    ).stdout.strip()
    tree = _command(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"],
        "source_checkout_tree",
        timeout=15,
    ).stdout.strip()
    tracked_status = _command(
        [
            "git",
            "-C",
            str(ROOT),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
        "source_checkout_status",
        timeout=15,
    ).stdout
    if head != source_commit or tree != source_tree:
        raise DistributionError("source_checkout_identity_mismatch")
    if tracked_status.strip():
        raise DistributionError("source_checkout_tracked_files_dirty")


def _binary_relative_path(platform_tag: str) -> str:
    return (
        "bin/structural-cli.exe"
        if platform_tag == "windows-x86_64-msvc"
        else "bin/structural-cli"
    )


def _verify_binary_format(content: bytes, platform_tag: str) -> None:
    if platform_tag == "linux-x86_64-gnu":
        if (
            len(content) < 20
            or content[:4] != b"\x7fELF"
            or content[4] != 2
            or content[5] != 1
            or int.from_bytes(content[18:20], "little") != 62
        ):
            raise DistributionError("structural_cli_not_linux_x86_64_elf")
        return
    if len(content) < 64 or content[:2] != b"MZ":
        raise DistributionError("structural_cli_not_windows_x86_64_pe")
    pe_offset = int.from_bytes(content[60:64], "little")
    if (
        pe_offset + 6 > len(content)
        or content[pe_offset : pe_offset + 4] != b"PE\0\0"
        or int.from_bytes(content[pe_offset + 4 : pe_offset + 6], "little") != 0x8664
    ):
        raise DistributionError("structural_cli_not_windows_x86_64_pe")


def _binary_format(platform_tag: str) -> str:
    return (
        "pe32plus-x86_64" if platform_tag == "windows-x86_64-msvc" else "elf64-x86_64"
    )


def _source_files(
    binary: Path, platform_tag: str
) -> dict[str, tuple[bytes, str, bool]]:
    distribution = ROOT / "native/distribution"
    return {
        "LICENSE": (
            _require_file(ROOT / "LICENSE", "license"),
            "text/plain; charset=utf-8",
            False,
        ),
        LICENSE_SBOM_PATH: (
            _native_license_sbom(),
            "application/json",
            False,
        ),
        "README.md": (
            _require_file(distribution / "README.md", "distribution_readme"),
            "text/markdown; charset=utf-8",
            False,
        ),
        _binary_relative_path(platform_tag): (
            _require_file(binary, "structural_cli"),
            "application/octet-stream",
            True,
        ),
        "examples/frame-alpha-cantilever.model-ir.json": (
            _require_file(
                distribution / "frame-alpha-cantilever.model-ir.json",
                "frame_alpha_example",
            ),
            "application/json",
            False,
        ),
        "schemas/frame_alpha_distribution_manifest_v1.schema.json": (
            _require_file(
                distribution / "frame_alpha_distribution_manifest_v1.schema.json",
                "distribution_manifest_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/frame_alpha_distribution_smoke_v1.schema.json": (
            _require_file(
                distribution / "frame_alpha_distribution_smoke_v1.schema.json",
                "distribution_smoke_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/external_linear_frame3d_reference_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/external_linear_frame3d_reference_v1.schema.json",
                "external_reference_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/linear_frame3d_comparison_ir_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/linear_frame3d_comparison_ir_v1.schema.json",
                "comparison_ir_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/native_linear_frame3d_job_submission_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/native_linear_frame3d_job_submission_v1.schema.json",
                "native_job_submission_schema",
            ),
            "application/json",
            False,
        ),
    }


def _workbench_media_type(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
        ".woff2": "font/woff2",
    }.get(suffix, "application/octet-stream")


def _workbench_files(workbench: Path) -> dict[str, tuple[bytes, str, bool]]:
    if workbench.is_symlink() or not workbench.is_dir():
        raise DistributionError(f"workbench_must_be_directory:{workbench}")
    files: dict[str, tuple[bytes, str, bool]] = {}
    for source in sorted(workbench.rglob("*")):
        if source.is_symlink():
            raise DistributionError(f"workbench_symlink_forbidden:{source}")
        if source.is_dir():
            continue
        if not source.is_file():
            raise DistributionError(f"workbench_entry_invalid:{source}")
        relative = source.relative_to(workbench).as_posix()
        path = PurePosixPath(relative)
        if any(part in {"", ".", ".."} for part in path.parts):
            raise DistributionError(f"workbench_path_unsafe:{relative}")
        content = _require_file(source, "workbench_file")
        files[f"workbench/{relative}"] = (
            content,
            _workbench_media_type(relative),
            False,
        )
    if not files or len(files) > MAX_WORKSTATION_FILES:
        raise DistributionError(f"workbench_file_count_invalid:{len(files)}")
    if "workbench/index.html" not in files:
        raise DistributionError("workbench_index_missing")
    assets = [path for path in files if path.startswith("workbench/assets/")]
    if not assets:
        raise DistributionError("workbench_assets_missing")
    javascript = b"\n".join(
        content
        for path, (content, _media_type, _executable) in files.items()
        if path.endswith(".js")
    )
    if WORKBENCH_SUBMISSION_URL.encode("utf-8") not in javascript:
        raise DistributionError("workbench_submission_url_missing")
    return files


def _workstation_source_files(
    binary: Path, platform_tag: str, workbench: Path
) -> dict[str, tuple[bytes, str, bool]]:
    distribution = ROOT / "native/distribution"
    files = {
        "LICENSE": (
            _require_file(ROOT / "LICENSE", "license"),
            "text/plain; charset=utf-8",
            False,
        ),
        LICENSE_SBOM_PATH: (
            _native_license_sbom(),
            "application/json",
            False,
        ),
        "README.md": (
            _require_file(
                distribution / "WORKSTATION.md", "workstation_distribution_readme"
            ),
            "text/markdown; charset=utf-8",
            False,
        ),
        _binary_relative_path(platform_tag): (
            _require_file(binary, "structural_cli"),
            "application/octet-stream",
            True,
        ),
        "examples/frame-alpha-cantilever.model-ir.json": (
            _require_file(
                distribution / "frame-alpha-cantilever.model-ir.json",
                "frame_alpha_example",
            ),
            "application/json",
            False,
        ),
        "schemas/frame_alpha_workstation_distribution_manifest_v2.schema.json": (
            _require_file(
                distribution
                / "frame_alpha_workstation_distribution_manifest_v2.schema.json",
                "workstation_distribution_manifest_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/frame_alpha_workstation_distribution_smoke_v2.schema.json": (
            _require_file(
                distribution
                / "frame_alpha_workstation_distribution_smoke_v2.schema.json",
                "workstation_distribution_smoke_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/external_linear_frame3d_reference_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/external_linear_frame3d_reference_v1.schema.json",
                "external_reference_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/linear_frame3d_comparison_ir_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/linear_frame3d_comparison_ir_v1.schema.json",
                "comparison_ir_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/native_linear_frame3d_job_submission_v1.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/native_linear_frame3d_job_submission_v1.schema.json",
                "native_job_submission_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/native_linear_frame3d_job_event_v2.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/native_linear_frame3d_job_event_v2.schema.json",
                "native_job_event_schema",
            ),
            "application/json",
            False,
        ),
        "schemas/native_linear_frame3d_job_view_v2.schema.json": (
            _require_file(
                ROOT
                / "native/crates/structural-contracts/schemas/native_linear_frame3d_job_view_v2.schema.json",
                "native_job_view_schema",
            ),
            "application/json",
            False,
        ),
    }
    files.update(_workbench_files(workbench))
    return files


def _manifest_without_hash(
    *,
    files: dict[str, tuple[bytes, str, bool]],
    platform_tag: str,
    source_commit: str,
    source_tree: str,
    binary_version: str,
) -> dict[str, Any]:
    binary_path = _binary_relative_path(platform_tag)
    binary = files[binary_path][0]
    rows = [
        {
            "path": path,
            "media_type": media_type,
            "byte_length": len(content),
            "sha256": _sha256_bytes(content),
            "executable": executable,
        }
        for path, (content, media_type, executable) in sorted(files.items())
    ]
    return {
        "schema_version": MANIFEST_SCHEMA,
        "package_id": f"structural-frame-alpha-cli-{PACKAGE_VERSION}-{platform_tag}",
        "package_version": PACKAGE_VERSION,
        "platform_tag": platform_tag,
        "source": {
            "commit_sha": source_commit,
            "tree_sha": source_tree,
            "binding_profile": "verified_clean_git_checkout.v1",
        },
        "archive_profile": "deterministic_zip_deflate.v1",
        "build_profile": "rust_release_static_cpp_cpu.v1",
        "binary": {
            "path": binary_path,
            "version": binary_version,
            "format": _binary_format(platform_tag),
            "sha256": _sha256_bytes(binary),
            "byte_length": len(binary),
        },
        "license": _license_manifest(files),
        "files": rows,
        "authority": MANIFEST_AUTHORITY,
        "claim_boundary": MANIFEST_CLAIM,
    }


def _zip_entry(
    path: str, content: bytes, executable: bool
) -> tuple[zipfile.ZipInfo, bytes]:
    info = zipfile.ZipInfo(path, FIXED_ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    mode = stat.S_IFREG | (0o755 if executable else 0o644)
    info.external_attr = mode << 16
    return info, content


def build_distribution(
    *,
    structural_cli: Path,
    platform_tag: str,
    source_commit: str,
    source_tree: str,
    output: Path,
) -> dict[str, Any]:
    if platform_tag not in PLATFORMS:
        raise DistributionError(f"platform_tag_invalid:{platform_tag}")
    source_commit = _git_sha(source_commit, "source_commit")
    source_tree = _git_sha(source_tree, "source_tree")
    _verify_source_checkout(source_commit, source_tree)
    if output.exists() or output.is_symlink():
        raise DistributionError(f"output_must_not_exist:{output}")
    structural_cli = structural_cli.resolve()
    files = _source_files(structural_cli, platform_tag)
    _verify_binary_format(files[_binary_relative_path(platform_tag)][0], platform_tag)
    version = _command([str(structural_cli), "--version"], "binary_version", timeout=15)
    binary_version = version.stdout.strip()
    if binary_version != f"structural-cli {PACKAGE_VERSION}":
        raise DistributionError(f"binary_version_invalid:{binary_version}")
    body = _manifest_without_hash(
        files=files,
        platform_tag=platform_tag,
        source_commit=source_commit,
        source_tree=source_tree,
        binary_version=binary_version,
    )
    manifest = {
        "schema_version": body.pop("schema_version"),
        "manifest_hash": _sha256_bytes(_canonical_bytes(body)),
        **body,
    }
    root_name = manifest["package_id"]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise DistributionError(f"temporary_output_exists:{temporary}")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for path, (content, _media_type, executable) in sorted(files.items()):
                info, payload = _zip_entry(f"{root_name}/{path}", content, executable)
                archive.writestr(info, payload, compresslevel=9)
            info, payload = _zip_entry(
                f"{root_name}/manifest.json",
                _canonical_bytes(manifest) + b"\n",
                False,
            )
            archive.writestr(info, payload, compresslevel=9)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return manifest


def _workstation_manifest_without_hash(
    *,
    files: dict[str, tuple[bytes, str, bool]],
    platform_tag: str,
    source_commit: str,
    source_tree: str,
    binary_version: str,
) -> dict[str, Any]:
    binary_path = _binary_relative_path(platform_tag)
    binary = files[binary_path][0]
    rows = [
        {
            "path": path,
            "media_type": media_type,
            "byte_length": len(content),
            "sha256": _sha256_bytes(content),
            "executable": executable,
        }
        for path, (content, media_type, executable) in sorted(files.items())
    ]
    workbench_rows = [row for row in rows if row["path"].startswith("workbench/")]
    index = next(row for row in workbench_rows if row["path"] == "workbench/index.html")
    return {
        "schema_version": WORKSTATION_MANIFEST_SCHEMA,
        "package_id": f"structural-frame-alpha-workstation-{PACKAGE_VERSION}-{platform_tag}",
        "package_version": PACKAGE_VERSION,
        "platform_tag": platform_tag,
        "source": {
            "commit_sha": source_commit,
            "tree_sha": source_tree,
            "binding_profile": "verified_clean_git_checkout.v1",
        },
        "archive_profile": "deterministic_zip_deflate.v1",
        "build_profile": "rust_release_static_cpp_cpu_plus_operator_supplied_vite.v2",
        "binary": {
            "path": binary_path,
            "version": binary_version,
            "format": _binary_format(platform_tag),
            "sha256": _sha256_bytes(binary),
            "byte_length": len(binary),
        },
        "license": _license_manifest(files),
        "workbench": {
            "root": "workbench",
            "index_path": "workbench/index.html",
            "index_sha256": index["sha256"],
            "file_count": len(workbench_rows),
            "byte_length": sum(int(row["byte_length"]) for row in workbench_rows),
            "submission_url": WORKBENCH_SUBMISSION_URL,
            "build_binding": "hash_bound_operator_supplied_vite_output.v1",
        },
        "files": rows,
        "authority": WORKSTATION_MANIFEST_AUTHORITY,
        "claim_boundary": WORKSTATION_MANIFEST_CLAIM,
    }


def build_workstation_distribution(
    *,
    structural_cli: Path,
    workbench: Path,
    platform_tag: str,
    source_commit: str,
    source_tree: str,
    output: Path,
) -> dict[str, Any]:
    if platform_tag not in PLATFORMS:
        raise DistributionError(f"platform_tag_invalid:{platform_tag}")
    source_commit = _git_sha(source_commit, "source_commit")
    source_tree = _git_sha(source_tree, "source_tree")
    _verify_source_checkout(source_commit, source_tree)
    if output.exists() or output.is_symlink():
        raise DistributionError(f"output_must_not_exist:{output}")
    structural_cli = structural_cli.resolve()
    files = _workstation_source_files(structural_cli, platform_tag, workbench)
    _verify_binary_format(files[_binary_relative_path(platform_tag)][0], platform_tag)
    version = _command([str(structural_cli), "--version"], "binary_version", timeout=15)
    binary_version = version.stdout.strip()
    if binary_version != f"structural-cli {PACKAGE_VERSION}":
        raise DistributionError(f"binary_version_invalid:{binary_version}")
    body = _workstation_manifest_without_hash(
        files=files,
        platform_tag=platform_tag,
        source_commit=source_commit,
        source_tree=source_tree,
        binary_version=binary_version,
    )
    manifest = {
        "schema_version": body.pop("schema_version"),
        "manifest_hash": _sha256_bytes(_canonical_bytes(body)),
        **body,
    }
    root_name = manifest["package_id"]
    if sum(len(content) for content, _media, _executable in files.values()) > MAX_ARCHIVE_BYTES:
        raise DistributionError("workstation_payload_size_invalid")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.partial-{os.getpid()}")
    if temporary.exists() or temporary.is_symlink():
        raise DistributionError(f"temporary_output_exists:{temporary}")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
            strict_timestamps=True,
        ) as archive:
            for path, (content, _media_type, executable) in sorted(files.items()):
                info, payload = _zip_entry(f"{root_name}/{path}", content, executable)
                archive.writestr(info, payload, compresslevel=9)
            info, payload = _zip_entry(
                f"{root_name}/manifest.json",
                _canonical_bytes(manifest) + b"\n",
                False,
            )
            archive.writestr(info, payload, compresslevel=9)
        os.replace(temporary, output)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return manifest


def _safe_archive_path(value: str, root_name: str) -> str:
    if "\\" in value or value.startswith("/"):
        raise DistributionError(f"archive_path_unsafe:{value}")
    path = PurePosixPath(value)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DistributionError(f"archive_path_unsafe:{value}")
    if path.parts[0] != root_name or len(path.parts) < 2:
        raise DistributionError(f"archive_root_mismatch:{value}")
    return PurePosixPath(*path.parts[1:]).as_posix()


def _manifest_hash(manifest: dict[str, Any]) -> str:
    body = dict(manifest)
    body.pop("manifest_hash", None)
    body.pop("schema_version", None)
    return _sha256_bytes(_canonical_bytes(body))


def _validate_license_manifest(
    value: Any,
    rows: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    rows_by_path = {str(row.get("path")): row for row in rows}
    license_row = rows_by_path.get("LICENSE")
    sbom_row = rows_by_path.get(LICENSE_SBOM_PATH)
    if license_row is None or sbom_row is None:
        raise DistributionError(f"{label}_license_inventory_missing")
    expected = {
        "repository_posture": FIRST_PARTY_POLICY["posture"],
        "license_ref": FIRST_PARTY_POLICY["license_ref"],
        "license_path": "LICENSE",
        "license_sha256": license_row.get("sha256"),
        "sbom_path": LICENSE_SBOM_PATH,
        "sbom_sha256": sbom_row.get("sha256"),
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "release_clearance": "blocked",
        "release_blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
    }
    if value != expected:
        raise DistributionError(f"{label}_license_policy_invalid")


def _validate_packaged_license(
    manifest: dict[str, Any],
    payloads: dict[str, bytes],
    *,
    label: str,
) -> None:
    license_bytes = payloads.get("LICENSE")
    sbom_bytes = payloads.get(LICENSE_SBOM_PATH)
    if license_bytes is None or sbom_bytes is None:
        raise DistributionError(f"{label}_license_payload_missing")
    try:
        normalized_license = " ".join(license_bytes.decode("utf-8").split())
    except UnicodeDecodeError as error:
        raise DistributionError(f"{label}_license_not_utf8") from error
    if any(
        " ".join(str(fragment).split()) not in normalized_license
        for fragment in FIRST_PARTY_POLICY["required_notice_fragments"]
    ):
        raise DistributionError(f"{label}_license_no_grant_boundary_missing")

    sbom = _strict_json(sbom_bytes, f"{label}_license_sbom")
    first_party = sbom.get("first_party_license")
    release_clearance = sbom.get("release_clearance")
    workspace_packages = (
        first_party.get("workspace_packages")
        if isinstance(first_party, dict)
        else None
    )
    expected_release_clearance = {
        "status": "blocked",
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
    }
    if (
        sbom.get("schema_version") != "native-dependency-license-sbom.v2"
        or sbom.get("contract_pass") is not True
        or sbom.get("blockers") != []
        or not isinstance(first_party, dict)
        or first_party.get("contract_pass") is not True
        or first_party.get("posture") != FIRST_PARTY_POLICY["posture"]
        or first_party.get("license_ref") != FIRST_PARTY_POLICY["license_ref"]
        or first_party.get("repository_license")
        != {
            "path": "LICENSE",
            "sha256": _sha256_bytes(license_bytes),
        }
        or not isinstance(workspace_packages, list)
        or not workspace_packages
        or first_party.get("workspace_package_count") != len(workspace_packages)
        or any(
            not isinstance(row, dict)
            or row.get("license_expression") is not None
            or row.get("license_file") != "LICENSE"
            or row.get("inherits_workspace_license_file") is not True
            or row.get("license_file_matches_repository") is not True
            for row in workspace_packages
        )
        or release_clearance != expected_release_clearance
    ):
        raise DistributionError(f"{label}_license_sbom_contract_invalid")

    license_policy = manifest.get("license")
    if (
        not isinstance(license_policy, dict)
        or license_policy.get("license_sha256") != _sha256_bytes(license_bytes)
        or license_policy.get("sbom_sha256") != _sha256_bytes(sbom_bytes)
    ):
        raise DistributionError(f"{label}_license_binding_invalid")


def _validate_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "manifest_hash",
        "package_id",
        "package_version",
        "platform_tag",
        "source",
        "archive_profile",
        "build_profile",
        "binary",
        "license",
        "files",
        "authority",
        "claim_boundary",
    }
    if set(manifest) != required:
        raise DistributionError("manifest_fields_invalid")
    platform_tag = manifest.get("platform_tag")
    if platform_tag not in PLATFORMS:
        raise DistributionError("manifest_platform_invalid")
    expected_id = f"structural-frame-alpha-cli-{PACKAGE_VERSION}-{platform_tag}"
    if (
        manifest.get("schema_version") != MANIFEST_SCHEMA
        or manifest.get("package_id") != expected_id
        or manifest.get("package_version") != PACKAGE_VERSION
        or manifest.get("archive_profile") != "deterministic_zip_deflate.v1"
        or manifest.get("build_profile") != "rust_release_static_cpp_cpu.v1"
        or manifest.get("authority") != MANIFEST_AUTHORITY
        or manifest.get("claim_boundary") != MANIFEST_CLAIM
        or manifest.get("manifest_hash") != _manifest_hash(manifest)
    ):
        raise DistributionError("manifest_contract_invalid")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "commit_sha",
        "tree_sha",
        "binding_profile",
    }:
        raise DistributionError("manifest_source_invalid")
    _git_sha(str(source["commit_sha"]), "manifest_source_commit")
    _git_sha(str(source["tree_sha"]), "manifest_source_tree")
    if source["binding_profile"] != "verified_clean_git_checkout.v1":
        raise DistributionError("manifest_source_binding_profile_invalid")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 10:
        raise DistributionError("manifest_files_invalid")
    paths: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "media_type",
            "byte_length",
            "sha256",
            "executable",
        }:
            raise DistributionError("manifest_file_row_invalid")
        paths.append(str(row["path"]))
        if (
            not isinstance(row["byte_length"], int)
            or not 1 <= row["byte_length"] <= MAX_FILE_BYTES
        ):
            raise DistributionError("manifest_file_length_invalid")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(row["sha256"])) is None:
            raise DistributionError("manifest_file_hash_invalid")
        if not isinstance(row["executable"], bool):
            raise DistributionError("manifest_file_executable_invalid")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise DistributionError("manifest_file_paths_invalid")
    expected_paths = {
        "LICENSE",
        LICENSE_SBOM_PATH,
        "README.md",
        _binary_relative_path(platform_tag),
        "examples/frame-alpha-cantilever.model-ir.json",
        "schemas/frame_alpha_distribution_manifest_v1.schema.json",
        "schemas/frame_alpha_distribution_smoke_v1.schema.json",
        "schemas/external_linear_frame3d_reference_v1.schema.json",
        "schemas/linear_frame3d_comparison_ir_v1.schema.json",
        "schemas/native_linear_frame3d_job_submission_v1.schema.json",
    }
    if set(paths) != expected_paths:
        raise DistributionError("manifest_file_inventory_invalid")
    _validate_license_manifest(manifest.get("license"), rows, label="manifest")
    binary = manifest.get("binary")
    binary_row = next(
        row for row in rows if row["path"] == _binary_relative_path(platform_tag)
    )
    if not isinstance(binary, dict) or binary != {
        "path": binary_row["path"],
        "version": f"structural-cli {PACKAGE_VERSION}",
        "format": _binary_format(platform_tag),
        "sha256": binary_row["sha256"],
        "byte_length": binary_row["byte_length"],
    }:
        raise DistributionError("manifest_binary_invalid")


def _validate_workstation_manifest(manifest: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "manifest_hash",
        "package_id",
        "package_version",
        "platform_tag",
        "source",
        "archive_profile",
        "build_profile",
        "binary",
        "license",
        "workbench",
        "files",
        "authority",
        "claim_boundary",
    }
    if set(manifest) != required:
        raise DistributionError("workstation_manifest_fields_invalid")
    platform_tag = manifest.get("platform_tag")
    if platform_tag not in PLATFORMS:
        raise DistributionError("workstation_manifest_platform_invalid")
    expected_id = (
        f"structural-frame-alpha-workstation-{PACKAGE_VERSION}-{platform_tag}"
    )
    if (
        manifest.get("schema_version") != WORKSTATION_MANIFEST_SCHEMA
        or manifest.get("package_id") != expected_id
        or manifest.get("package_version") != PACKAGE_VERSION
        or manifest.get("archive_profile") != "deterministic_zip_deflate.v1"
        or manifest.get("build_profile")
        != "rust_release_static_cpp_cpu_plus_operator_supplied_vite.v2"
        or manifest.get("authority") != WORKSTATION_MANIFEST_AUTHORITY
        or manifest.get("claim_boundary") != WORKSTATION_MANIFEST_CLAIM
        or manifest.get("manifest_hash") != _manifest_hash(manifest)
    ):
        raise DistributionError("workstation_manifest_contract_invalid")
    source = manifest.get("source")
    if not isinstance(source, dict) or set(source) != {
        "commit_sha",
        "tree_sha",
        "binding_profile",
    }:
        raise DistributionError("workstation_manifest_source_invalid")
    _git_sha(str(source["commit_sha"]), "workstation_manifest_source_commit")
    _git_sha(str(source["tree_sha"]), "workstation_manifest_source_tree")
    if source["binding_profile"] != "verified_clean_git_checkout.v1":
        raise DistributionError("workstation_manifest_source_binding_profile_invalid")
    rows = manifest.get("files")
    if not isinstance(rows, list) or not 14 <= len(rows) <= MAX_WORKSTATION_FILES + 12:
        raise DistributionError("workstation_manifest_files_invalid")
    allowed_media_types = {
        "application/octet-stream",
        "application/json",
        "text/html; charset=utf-8",
        "text/javascript; charset=utf-8",
        "text/css; charset=utf-8",
        "text/markdown; charset=utf-8",
        "text/plain; charset=utf-8",
        "image/svg+xml",
        "image/png",
        "image/x-icon",
        "font/woff2",
    }
    paths: list[str] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "path",
            "media_type",
            "byte_length",
            "sha256",
            "executable",
        }:
            raise DistributionError("workstation_manifest_file_row_invalid")
        path = str(row["path"])
        pure = PurePosixPath(path)
        if (
            not path
            or "\\" in path
            or pure.is_absolute()
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            raise DistributionError("workstation_manifest_file_path_unsafe")
        paths.append(path)
        if (
            not isinstance(row["byte_length"], int)
            or not 1 <= row["byte_length"] <= MAX_FILE_BYTES
        ):
            raise DistributionError("workstation_manifest_file_length_invalid")
        if re.fullmatch(r"sha256:[0-9a-f]{64}", str(row["sha256"])) is None:
            raise DistributionError("workstation_manifest_file_hash_invalid")
        if row["media_type"] not in allowed_media_types:
            raise DistributionError("workstation_manifest_file_media_type_invalid")
        if not isinstance(row["executable"], bool):
            raise DistributionError("workstation_manifest_file_executable_invalid")
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise DistributionError("workstation_manifest_file_paths_invalid")
    control_paths = {
        "LICENSE",
        LICENSE_SBOM_PATH,
        "README.md",
        _binary_relative_path(platform_tag),
        "examples/frame-alpha-cantilever.model-ir.json",
        "schemas/external_linear_frame3d_reference_v1.schema.json",
        "schemas/frame_alpha_workstation_distribution_manifest_v2.schema.json",
        "schemas/frame_alpha_workstation_distribution_smoke_v2.schema.json",
        "schemas/linear_frame3d_comparison_ir_v1.schema.json",
        "schemas/native_linear_frame3d_job_event_v2.schema.json",
        "schemas/native_linear_frame3d_job_submission_v1.schema.json",
        "schemas/native_linear_frame3d_job_view_v2.schema.json",
    }
    workbench_rows = [row for row in rows if row["path"].startswith("workbench/")]
    if set(paths) != control_paths | {str(row["path"]) for row in workbench_rows}:
        raise DistributionError("workstation_manifest_file_inventory_invalid")
    _validate_license_manifest(
        manifest.get("license"), rows, label="workstation_manifest"
    )
    if len(workbench_rows) < 2 or len(workbench_rows) > MAX_WORKSTATION_FILES:
        raise DistributionError("workstation_manifest_workbench_inventory_invalid")
    index_rows = [
        row for row in workbench_rows if row["path"] == "workbench/index.html"
    ]
    if len(index_rows) != 1 or not any(
        str(row["path"]).startswith("workbench/assets/") for row in workbench_rows
    ):
        raise DistributionError("workstation_manifest_workbench_shape_invalid")
    binary = manifest.get("binary")
    binary_row = next(
        row for row in rows if row["path"] == _binary_relative_path(platform_tag)
    )
    if not isinstance(binary, dict) or binary != {
        "path": binary_row["path"],
        "version": f"structural-cli {PACKAGE_VERSION}",
        "format": _binary_format(platform_tag),
        "sha256": binary_row["sha256"],
        "byte_length": binary_row["byte_length"],
    }:
        raise DistributionError("workstation_manifest_binary_invalid")
    workbench = manifest.get("workbench")
    if not isinstance(workbench, dict) or workbench != {
        "root": "workbench",
        "index_path": "workbench/index.html",
        "index_sha256": index_rows[0]["sha256"],
        "file_count": len(workbench_rows),
        "byte_length": sum(int(row["byte_length"]) for row in workbench_rows),
        "submission_url": WORKBENCH_SUBMISSION_URL,
        "build_binding": "hash_bound_operator_supplied_vite_output.v1",
    }:
        raise DistributionError("workstation_manifest_workbench_invalid")
    if any(
        bool(row["executable"])
        != (row["path"] == _binary_relative_path(platform_tag))
        for row in rows
    ):
        raise DistributionError("workstation_manifest_executable_inventory_invalid")


def verify_distribution(*, archive_path: Path) -> dict[str, Any]:
    archive_bytes = _require_file(
        archive_path, "distribution_archive", maximum=MAX_ARCHIVE_BYTES
    )
    try:
        archive = zipfile.ZipFile(archive_path, mode="r")
    except zipfile.BadZipFile as error:
        raise DistributionError(f"archive_invalid:{error}") from error
    with archive:
        infos = archive.infolist()
        if archive.comment or len(infos) != 11:
            raise DistributionError("archive_shape_invalid")
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise DistributionError("archive_uncompressed_size_invalid")
        if any(
            info.file_size < 1
            or info.file_size > MAX_FILE_BYTES
            or info.flag_bits & 0x1
            or info.compress_type != zipfile.ZIP_DEFLATED
            or info.date_time != FIXED_ZIP_TIME
            or info.create_system != 3
            for info in infos
        ):
            raise DistributionError("archive_entry_profile_invalid")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise DistributionError("archive_duplicate_path")
        manifest_names = [name for name in names if name.endswith("/manifest.json")]
        if len(manifest_names) != 1:
            raise DistributionError("archive_manifest_count_invalid")
        root_name = PurePosixPath(manifest_names[0]).parts[0]
        relative_by_name = {name: _safe_archive_path(name, root_name) for name in names}
        manifest = _strict_json(
            archive.read(manifest_names[0]), "distribution_manifest"
        )
        _validate_manifest(manifest)
        if root_name != manifest["package_id"]:
            raise DistributionError("archive_package_root_invalid")
        expected_relative = {row["path"] for row in manifest["files"]} | {
            "manifest.json"
        }
        if set(relative_by_name.values()) != expected_relative:
            raise DistributionError("archive_inventory_invalid")
        expected_names = [f"{root_name}/{row['path']}" for row in manifest["files"]] + [
            f"{root_name}/manifest.json"
        ]
        if names != expected_names:
            raise DistributionError("archive_order_invalid")
        rows = {row["path"]: row for row in manifest["files"]}
        payloads: dict[str, bytes] = {}
        for info in infos:
            relative = relative_by_name[info.filename]
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) != stat.S_IFREG:
                raise DistributionError(f"archive_non_regular_entry:{relative}")
            executable = (
                rows[relative]["executable"] if relative != "manifest.json" else False
            )
            expected_permissions = 0o755 if executable else 0o644
            if stat.S_IMODE(mode) != expected_permissions:
                raise DistributionError(f"archive_mode_invalid:{relative}")
            payload = archive.read(info)
            if relative != "manifest.json":
                row = rows[relative]
                if (
                    len(payload) != row["byte_length"]
                    or _sha256_bytes(payload) != row["sha256"]
                ):
                    raise DistributionError(f"archive_file_binding_invalid:{relative}")
                payloads[relative] = payload

    _validate_packaged_license(
        manifest,
        payloads,
        label="distribution",
    )

    with tempfile.TemporaryDirectory(
        prefix="frame-alpha-distribution-smoke-"
    ) as directory:
        extracted = Path(directory) / root_name
        for relative, payload in payloads.items():
            target = extracted / PurePosixPath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if rows[relative]["executable"]:
                target.chmod(0o755)
        binary = extracted / PurePosixPath(manifest["binary"]["path"])
        example = extracted / "examples/frame-alpha-cantilever.model-ir.json"
        version = _command(
            [str(binary), "--version"], "extracted_binary_version", timeout=15
        )
        if version.stdout.strip() != f"structural-cli {PACKAGE_VERSION}":
            raise DistributionError("extracted_binary_version_invalid")
        validation = _command(
            [
                str(binary),
                "model",
                "validate",
                str(example),
                "--require-analysis-ready",
            ],
            "extracted_model_validation",
        )
        validation_payload = _strict_json(
            validation.stdout.encode("utf-8"), "model_validation"
        )
        if (
            validation_payload.get("contract_valid") is not True
            or validation_payload.get("analysis_ready") is not True
        ):
            raise DistributionError("extracted_model_not_analysis_ready")
        bundle = Path(directory) / "workbench-bundle"
        _command(
            [
                str(binary),
                "model",
                "analyze-frame3d",
                str(example),
                "--load-pattern",
                "LC_WEAK",
                "--result-id",
                "distribution.LC_WEAK",
                "--report-id",
                "distribution.LC_WEAK.report",
                "--output",
                "workbench-bundle",
                "--output-dir",
                str(bundle),
            ],
            "extracted_analysis",
        )
        bundle_manifest = _require_file(
            bundle / "manifest.json", "workbench_bundle_manifest"
        )
        bundle_payload = _strict_json(bundle_manifest, "workbench_bundle_manifest")
        if (
            bundle_payload.get("schema_version")
            != "structural-native-linear-frame3d-workbench-bundle.v1"
        ):
            raise DistributionError("workbench_bundle_schema_invalid")

    return {
        "schema_version": SMOKE_SCHEMA,
        "status": "pass",
        "archive": {
            "sha256": _sha256_bytes(archive_bytes),
            "byte_length": len(archive_bytes),
        },
        "manifest_hash": manifest["manifest_hash"],
        "source": manifest["source"],
        "platform_tag": manifest["platform_tag"],
        "checks": {
            "archive_paths_safe": True,
            "manifest_hashes_match": True,
            "license_no_grant_policy": "passed",
            "license_sbom": "passed",
            "release_clearance": "blocked",
            "binary_version": f"structural-cli {PACKAGE_VERSION}",
            "binary_format": _binary_format(manifest["platform_tag"]),
            "model_validation": "analysis_ready",
            "analysis_to_workbench_bundle": "passed",
            "bundle_manifest_sha256": _sha256_bytes(bundle_manifest),
        },
        "authority": SMOKE_AUTHORITY,
        "claim_boundary": SMOKE_CLAIM,
    }


def _read_startup_line(
    process: subprocess.Popen[str], timeout: float = 15.0
) -> str:
    if process.stdout is None:
        raise DistributionError("workstation_smoke_stdout_missing")
    lines: queue.Queue[str] = queue.Queue(maxsize=1)

    def read_line() -> None:
        assert process.stdout is not None
        lines.put(process.stdout.readline())

    reader = threading.Thread(target=read_line, daemon=True)
    reader.start()
    try:
        line = lines.get(timeout=timeout)
    except queue.Empty as error:
        raise DistributionError("workstation_smoke_startup_timeout") from error
    if not line:
        raise DistributionError("workstation_smoke_startup_missing")
    return line


def _http_get(url: str, label: str) -> tuple[bytes, str]:
    try:
        with urlopen(url, timeout=10) as response:  # noqa: S310 - fixed loopback origin
            if response.status != 200:
                raise DistributionError(f"{label}_status_invalid:{response.status}")
            return response.read(), response.headers.get("Content-Type", "")
    except (HTTPError, URLError, TimeoutError) as error:
        raise DistributionError(f"{label}_failed:{error}") from error


def _smoke_extracted_workstation(
    *, binary: Path, workbench: Path, directory: Path
) -> dict[str, Any]:
    process = subprocess.Popen(
        [
            str(binary),
            "workstation",
            "serve",
            "--store",
            str(directory / "jobs"),
            "--workbench",
            str(workbench),
            "--listen",
            "127.0.0.1:0",
            "--worker-timeout-seconds",
            "5",
            "--max-requests",
            "3",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        startup_line = _read_startup_line(process)
        startup = _strict_json(
            startup_line.encode("utf-8"), "workstation_startup_receipt"
        )
        if (
            startup.get("schema_version")
            == "structural-native-frame-alpha-workstation-host-failure.v1"
        ):
            issues = startup.get("issues")
            code = (
                str(issues[0].get("code", "unknown"))
                if isinstance(issues, list)
                and issues
                and isinstance(issues[0], dict)
                else "unknown"
            )
            raise DistributionError(f"workstation_smoke_host_failed:{code}")
        origin = startup.get("origin")
        if (
            startup.get("schema_version")
            != "structural-native-frame-alpha-workstation-host.v2"
            or startup.get("service_profile")
            != "loopback_worker_process_cancellation.v2"
            or not isinstance(origin, str)
            or re.fullmatch(r"http://127\.0\.0\.1:[0-9]+", origin) is None
            or startup.get("submission_url") != f"{origin}{WORKBENCH_SUBMISSION_URL}"
        ):
            raise DistributionError("workstation_startup_receipt_invalid")
        index, index_type = _http_get(f"{origin}/", "workstation_index")
        expected_index = _require_file(workbench / "index.html", "workstation_index")
        if index != expected_index or not index_type.startswith("text/html"):
            raise DistributionError("workstation_index_response_invalid")
        match = re.search(rb'(?:src|href)="(/assets/[^"?#]+)', index)
        if match is None:
            raise DistributionError("workstation_index_asset_missing")
        asset_path = match.group(1).decode("utf-8")
        asset, asset_type = _http_get(f"{origin}{asset_path}", "workstation_asset")
        expected_asset = _require_file(
            workbench / asset_path.lstrip("/"), "workstation_asset"
        )
        if asset != expected_asset or not asset_type:
            raise DistributionError("workstation_asset_response_invalid")
        capability_bytes, capability_type = _http_get(
            f"{origin}/api/v1/capabilities", "workstation_capabilities"
        )
        capabilities = _strict_json(capability_bytes, "workstation_capabilities")
        if (
            not capability_type.startswith("application/json")
            or capabilities.get("schema_version")
            != "structural-native-frame-alpha-workstation-capabilities.v2"
            or capabilities.get("service_profile")
            != "loopback_worker_process_cancellation.v2"
            or capabilities.get("browser_submission") is not True
            or capabilities.get("process_isolation") is not True
            or capabilities.get("cancellation") is not True
            or capabilities.get("resume") is not False
            or capabilities.get("crash_recovery") is not False
        ):
            raise DistributionError("workstation_capabilities_response_invalid")
        try:
            _stdout, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired as error:
            raise DistributionError("workstation_smoke_shutdown_timeout") from error
        if process.returncode != 0:
            raise DistributionError(
                f"workstation_smoke_failed:{process.returncode}:{stderr.strip()}"
            )
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    return {
        "startup_schema": "structural-native-frame-alpha-workstation-host.v2",
        "service_profile": "loopback_worker_process_cancellation.v2",
        "static_index": "passed",
        "static_asset": "passed",
        "capabilities": "passed",
        "index_sha256": _sha256_bytes(index),
        "asset_path": asset_path,
        "asset_sha256": _sha256_bytes(asset),
    }


def verify_workstation_distribution(*, archive_path: Path) -> dict[str, Any]:
    archive_bytes = _require_file(
        archive_path, "workstation_distribution_archive", maximum=MAX_ARCHIVE_BYTES
    )
    try:
        archive = zipfile.ZipFile(archive_path, mode="r")
    except zipfile.BadZipFile as error:
        raise DistributionError(f"workstation_archive_invalid:{error}") from error
    with archive:
        infos = archive.infolist()
        if archive.comment or not 15 <= len(infos) <= MAX_WORKSTATION_FILES + 13:
            raise DistributionError("workstation_archive_shape_invalid")
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise DistributionError("workstation_archive_uncompressed_size_invalid")
        if any(
            info.file_size < 1
            or info.file_size > MAX_FILE_BYTES
            or info.flag_bits & 0x1
            or info.compress_type != zipfile.ZIP_DEFLATED
            or info.date_time != FIXED_ZIP_TIME
            or info.create_system != 3
            for info in infos
        ):
            raise DistributionError("workstation_archive_entry_profile_invalid")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise DistributionError("workstation_archive_duplicate_path")
        manifest_names = [name for name in names if name.endswith("/manifest.json")]
        if len(manifest_names) != 1:
            raise DistributionError("workstation_archive_manifest_count_invalid")
        root_name = PurePosixPath(manifest_names[0]).parts[0]
        relative_by_name = {
            name: _safe_archive_path(name, root_name) for name in names
        }
        manifest = _strict_json(
            archive.read(manifest_names[0]), "workstation_distribution_manifest"
        )
        _validate_workstation_manifest(manifest)
        if root_name != manifest["package_id"]:
            raise DistributionError("workstation_archive_package_root_invalid")
        expected_relative = {row["path"] for row in manifest["files"]} | {
            "manifest.json"
        }
        if set(relative_by_name.values()) != expected_relative:
            raise DistributionError("workstation_archive_inventory_invalid")
        expected_names = [
            f"{root_name}/{row['path']}" for row in manifest["files"]
        ] + [f"{root_name}/manifest.json"]
        if names != expected_names:
            raise DistributionError("workstation_archive_order_invalid")
        rows = {row["path"]: row for row in manifest["files"]}
        payloads: dict[str, bytes] = {}
        for info in infos:
            relative = relative_by_name[info.filename]
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) != stat.S_IFREG:
                raise DistributionError(
                    f"workstation_archive_non_regular_entry:{relative}"
                )
            executable = (
                rows[relative]["executable"] if relative != "manifest.json" else False
            )
            expected_permissions = 0o755 if executable else 0o644
            if stat.S_IMODE(mode) != expected_permissions:
                raise DistributionError(f"workstation_archive_mode_invalid:{relative}")
            payload = archive.read(info)
            if relative != "manifest.json":
                row = rows[relative]
                if (
                    len(payload) != row["byte_length"]
                    or _sha256_bytes(payload) != row["sha256"]
                ):
                    raise DistributionError(
                        f"workstation_archive_file_binding_invalid:{relative}"
                    )
                payloads[relative] = payload

    _validate_packaged_license(
        manifest,
        payloads,
        label="workstation_distribution",
    )

    with tempfile.TemporaryDirectory(
        prefix="frame-alpha-workstation-distribution-smoke-"
    ) as directory_text:
        directory = Path(directory_text)
        extracted = directory / root_name
        for relative, payload in payloads.items():
            target = extracted / PurePosixPath(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            if rows[relative]["executable"]:
                target.chmod(0o755)
        binary = extracted / PurePosixPath(manifest["binary"]["path"])
        workbench = extracted / "workbench"
        example = extracted / "examples/frame-alpha-cantilever.model-ir.json"
        _verify_binary_format(binary.read_bytes(), manifest["platform_tag"])
        version = _command(
            [str(binary), "--version"], "workstation_extracted_binary_version", timeout=15
        )
        if version.stdout.strip() != f"structural-cli {PACKAGE_VERSION}":
            raise DistributionError("workstation_extracted_binary_version_invalid")
        validation = _command(
            [
                str(binary),
                "model",
                "validate",
                str(example),
                "--require-analysis-ready",
            ],
            "workstation_extracted_model_validation",
        )
        validation_payload = _strict_json(
            validation.stdout.encode("utf-8"), "workstation_model_validation"
        )
        if (
            validation_payload.get("contract_valid") is not True
            or validation_payload.get("analysis_ready") is not True
        ):
            raise DistributionError("workstation_extracted_model_not_analysis_ready")
        bundle = directory / "workbench-bundle"
        _command(
            [
                str(binary),
                "model",
                "analyze-frame3d",
                str(example),
                "--load-pattern",
                "LC_WEAK",
                "--result-id",
                "workstation-distribution.LC_WEAK",
                "--report-id",
                "workstation-distribution.LC_WEAK.report",
                "--output",
                "workbench-bundle",
                "--output-dir",
                str(bundle),
            ],
            "workstation_extracted_analysis",
        )
        bundle_manifest = _require_file(
            bundle / "manifest.json", "workstation_workbench_bundle_manifest"
        )
        bundle_payload = _strict_json(
            bundle_manifest, "workstation_workbench_bundle_manifest"
        )
        if (
            bundle_payload.get("schema_version")
            != "structural-native-linear-frame3d-workbench-bundle.v1"
        ):
            raise DistributionError("workstation_workbench_bundle_schema_invalid")
        javascript = b"\n".join(
            payload
            for path, payload in payloads.items()
            if path.startswith("workbench/") and path.endswith(".js")
        )
        if WORKBENCH_SUBMISSION_URL.encode("utf-8") not in javascript:
            raise DistributionError("workstation_submission_url_binding_invalid")
        host_checks = _smoke_extracted_workstation(
            binary=binary, workbench=workbench, directory=directory
        )

    return {
        "schema_version": WORKSTATION_SMOKE_SCHEMA,
        "status": "pass",
        "archive": {
            "sha256": _sha256_bytes(archive_bytes),
            "byte_length": len(archive_bytes),
        },
        "manifest_hash": manifest["manifest_hash"],
        "source": manifest["source"],
        "platform_tag": manifest["platform_tag"],
        "checks": {
            "archive_paths_safe": True,
            "manifest_hashes_match": True,
            "license_no_grant_policy": "passed",
            "license_sbom": "passed",
            "release_clearance": "blocked",
            "binary_version": f"structural-cli {PACKAGE_VERSION}",
            "binary_format": _binary_format(manifest["platform_tag"]),
            "model_validation": "analysis_ready",
            "analysis_to_workbench_bundle": "passed",
            "bundle_manifest_sha256": _sha256_bytes(bundle_manifest),
            "submission_url": WORKBENCH_SUBMISSION_URL,
            **host_checks,
        },
        "authority": WORKSTATION_SMOKE_AUTHORITY,
        "claim_boundary": WORKSTATION_SMOKE_CLAIM,
    }


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise DistributionError(f"output_must_not_exist:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--structural-cli", type=Path, required=True)
    build.add_argument("--platform-tag", choices=PLATFORMS, required=True)
    build.add_argument("--source-commit", required=True)
    build.add_argument("--source-tree", required=True)
    build.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--archive", type=Path, required=True)
    verify.add_argument("--receipt", type=Path, required=True)
    build_workstation = subparsers.add_parser("build-workstation")
    build_workstation.add_argument("--structural-cli", type=Path, required=True)
    build_workstation.add_argument("--workbench", type=Path, required=True)
    build_workstation.add_argument("--platform-tag", choices=PLATFORMS, required=True)
    build_workstation.add_argument("--source-commit", required=True)
    build_workstation.add_argument("--source-tree", required=True)
    build_workstation.add_argument("--output", type=Path, required=True)
    verify_workstation = subparsers.add_parser("verify-workstation")
    verify_workstation.add_argument("--archive", type=Path, required=True)
    verify_workstation.add_argument("--receipt", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        if arguments.command == "build":
            payload = build_distribution(
                structural_cli=arguments.structural_cli,
                platform_tag=arguments.platform_tag,
                source_commit=arguments.source_commit,
                source_tree=arguments.source_tree,
                output=arguments.output,
            )
            print(_canonical_bytes(payload).decode("utf-8"))
        elif arguments.command == "verify":
            payload = verify_distribution(archive_path=arguments.archive)
            _write_new(arguments.receipt, payload)
            print(_canonical_bytes(payload).decode("utf-8"))
        elif arguments.command == "build-workstation":
            payload = build_workstation_distribution(
                structural_cli=arguments.structural_cli,
                workbench=arguments.workbench,
                platform_tag=arguments.platform_tag,
                source_commit=arguments.source_commit,
                source_tree=arguments.source_tree,
                output=arguments.output,
            )
            print(_canonical_bytes(payload).decode("utf-8"))
        else:
            payload = verify_workstation_distribution(archive_path=arguments.archive)
            _write_new(arguments.receipt, payload)
            print(_canonical_bytes(payload).decode("utf-8"))
    except (
        DistributionError,
        OSError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
    ) as error:
        print(f"Frame Alpha distribution failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
