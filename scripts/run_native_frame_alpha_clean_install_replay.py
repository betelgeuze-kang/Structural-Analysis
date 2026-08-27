#!/usr/bin/env python3
"""Replay a source-bound Frame Alpha workstation ZIP on a clean runner."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from typing import Any, Sequence
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DISTRIBUTION_SCRIPT = ROOT / "scripts" / "build_native_frame_alpha_distribution.py"
SCHEMA_VERSION = "structural-frame-alpha-clean-install-replay.v1"
PLATFORMS = ("linux-x86_64-gnu", "windows-x86_64-msvc")
RUNNER_PROFILES = ("github_hosted_ephemeral", "local_isolated_test")
RESULT_SCHEMA = "structural-native-linear-frame3d-result-ir.v1"
RESULT_AUTHORITY = "bounded_native_cpu_result_candidate.v1"
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024


class CleanInstallReplayError(RuntimeError):
    """Raised when a clean-runner package replay cannot be credited."""


def _load_distribution_module() -> Any:
    spec = importlib.util.spec_from_file_location(
        "build_native_frame_alpha_distribution_clean_replay", DISTRIBUTION_SCRIPT
    )
    if spec is None or spec.loader is None:
        raise CleanInstallReplayError("distribution_verifier_import_failed")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def _load_object(value: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise CleanInstallReplayError(f"{label}_duplicate_key:{key}")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                CleanInstallReplayError(f"{label}_nonfinite:{token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CleanInstallReplayError(f"{label}_invalid_json") from error
    if not isinstance(payload, dict):
        raise CleanInstallReplayError(f"{label}_must_be_object")
    return payload


def _git_sha(value: str, label: str) -> str:
    if re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise CleanInstallReplayError(f"{label}_invalid")
    return value


def _command(command: list[str], label: str) -> bytes:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise CleanInstallReplayError(f"{label}_execution_failed") from error
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).decode(
            "utf-8", errors="replace"
        )
        raise CleanInstallReplayError(
            f"{label}_failed:{completed.returncode}:{detail.strip()}"
        )
    return completed.stdout


def _write_new(path: Path, payload: dict[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        raise CleanInstallReplayError(f"output_must_not_exist:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_canonical_bytes(payload) + b"\n")


def _extract_verified_archive(
    *, archive_path: Path, destination: Path
) -> tuple[Path, dict[str, Any]]:
    with zipfile.ZipFile(archive_path, mode="r") as archive:
        manifest_names = [
            info.filename
            for info in archive.infolist()
            if info.filename.endswith("/manifest.json")
        ]
        if len(manifest_names) != 1:
            raise CleanInstallReplayError("archive_manifest_count_invalid")
        manifest_name = manifest_names[0]
        manifest = _load_object(archive.read(manifest_name), "package_manifest")
        root_name = PurePosixPath(manifest_name).parts[0]
        package_root = destination / root_name
        for info in archive.infolist():
            parts = PurePosixPath(info.filename).parts
            if (
                not parts
                or parts[0] != root_name
                or any(part in {"", ".", ".."} for part in parts)
            ):
                raise CleanInstallReplayError("archive_path_invalid_after_verification")
            target = destination.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))
            if info.filename == manifest_name:
                continue
            relative = PurePosixPath(*parts[1:]).as_posix()
            rows = {
                str(row["path"]): row
                for row in manifest.get("files", [])
                if isinstance(row, dict) and isinstance(row.get("path"), str)
            }
            row = rows.get(relative)
            if row is None:
                raise CleanInstallReplayError(
                    f"archive_inventory_changed_after_verification:{relative}"
                )
            target.chmod(0o755 if row.get("executable") is True else 0o644)
        return package_root, manifest


def _result_identity(payload: dict[str, Any]) -> dict[str, Any]:
    bindings = payload.get("bindings")
    gates = payload.get("gates")
    if (
        payload.get("schema_version") != RESULT_SCHEMA
        or payload.get("authority_profile") != RESULT_AUTHORITY
        or not isinstance(bindings, dict)
        or not isinstance(gates, dict)
        or gates.get("native_residual_gate_passed") is not True
        or gates.get("global_resultant_gate_passed") is not True
        or gates.get("independent_recovery_replay_passed") is not True
        or gates.get("fallback_count") != 0
        or gates.get("regularization_count") != 0
    ):
        raise CleanInstallReplayError("result_authority_or_gate_invalid")
    required = (
        "model_content_hash",
        "model_semantic_hash",
        "model_provenance_hash",
    )
    if any(
        not isinstance(bindings.get(key), str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", str(bindings.get(key))) is None
        for key in required
    ):
        raise CleanInstallReplayError("result_model_binding_invalid")
    result_hash = payload.get("result_hash")
    if (
        not isinstance(result_hash, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", result_hash) is None
    ):
        raise CleanInstallReplayError("result_hash_invalid")
    return {
        "schema_version": payload["schema_version"],
        "authority_profile": payload["authority_profile"],
        "result_hash": result_hash,
        "model_content_hash": bindings["model_content_hash"],
        "model_semantic_hash": bindings["model_semantic_hash"],
        "model_provenance_hash": bindings["model_provenance_hash"],
        "load_pattern_id": bindings.get("load_pattern_id"),
        "load_combination_id": bindings.get("load_combination_id"),
        "native_abi_version": bindings.get("native_abi_version"),
        "solver": payload.get("solver"),
        "node_count": len(payload.get("nodes", [])),
        "member_count": len(payload.get("members", [])),
    }


def run_clean_install_replay(
    *,
    archive_path: Path,
    expected_source_commit: str,
    expected_platform_tag: str,
    runner_profile: str,
) -> dict[str, Any]:
    if expected_platform_tag not in PLATFORMS:
        raise CleanInstallReplayError("platform_tag_invalid")
    if runner_profile not in RUNNER_PROFILES:
        raise CleanInstallReplayError("runner_profile_invalid")
    expected_source_commit = _git_sha(expected_source_commit, "expected_source_commit")
    if archive_path.is_symlink() or not archive_path.is_file():
        raise CleanInstallReplayError("archive_must_be_regular_file")
    archive_bytes = archive_path.read_bytes()
    if not 0 < len(archive_bytes) <= MAX_ARCHIVE_BYTES:
        raise CleanInstallReplayError("archive_size_invalid")

    distribution = _load_distribution_module()
    try:
        package_smoke = distribution.verify_workstation_distribution(
            archive_path=archive_path
        )
    except Exception as error:
        raise CleanInstallReplayError(
            f"package_verification_failed:{type(error).__name__}:{error}"
        ) from error
    if archive_path.read_bytes() != archive_bytes:
        raise CleanInstallReplayError("archive_changed_during_verification")
    source = package_smoke.get("source")
    if (
        package_smoke.get("status") != "pass"
        or package_smoke.get("platform_tag") != expected_platform_tag
        or not isinstance(source, dict)
        or source.get("commit_sha") != expected_source_commit
    ):
        raise CleanInstallReplayError("package_source_or_platform_mismatch")

    with tempfile.TemporaryDirectory(
        prefix="frame-alpha-clean-install-replay-"
    ) as directory_text:
        directory = Path(directory_text)
        package_root, manifest = _extract_verified_archive(
            archive_path=archive_path, destination=directory
        )
        if manifest.get("source") != source:
            raise CleanInstallReplayError("manifest_source_changed_after_verification")
        binary_meta = manifest.get("binary")
        if not isinstance(binary_meta, dict) or not isinstance(
            binary_meta.get("path"), str
        ):
            raise CleanInstallReplayError("manifest_binary_invalid")
        binary = package_root / PurePosixPath(binary_meta["path"])
        if not binary.is_file() or binary.is_symlink():
            raise CleanInstallReplayError("installed_binary_missing")
        if expected_platform_tag == "linux-x86_64-gnu":
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        example = package_root / "examples/frame-alpha-cantilever.model-ir.json"
        command = [
            str(binary),
            "model",
            "analyze-frame3d",
            str(example),
            "--load-pattern",
            "LC_WEAK",
            "--result-id",
            "clean-install.LC_WEAK",
            "--output",
            "result-ir",
        ]
        first = _command(command, "clean_install_analysis_first")
        second = _command(command, "clean_install_analysis_second")
        if first != second:
            raise CleanInstallReplayError(
                "installed_analysis_replay_not_byte_identical"
            )
        result = _load_object(first, "clean_install_result")
        result_identity = _result_identity(result)

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "source": source,
        "platform_tag": expected_platform_tag,
        "runner": {
            "profile": runner_profile,
            "fresh_extraction_directory": True,
            "source_build_output_used": False,
            "network_used_during_replay": False,
        },
        "archive": {
            "sha256": _sha256_bytes(archive_bytes),
            "byte_length": len(archive_bytes),
            "package_id": manifest.get("package_id"),
            "manifest_hash": package_smoke.get("manifest_hash"),
        },
        "package_smoke": {
            "schema_version": package_smoke.get("schema_version"),
            "receipt_sha256": _sha256_bytes(_canonical_bytes(package_smoke)),
            "loopback_static_and_capability_smoke": "passed",
        },
        "analysis_replay": {
            "repeat_count": 2,
            "byte_identical": True,
            "canonical_result_sha256": _sha256_bytes(first),
            **result_identity,
        },
        "authority": {
            "portable_clean_runner_installation": "passed",
            "same_source_linux_windows_parity": "not_established_by_one_receipt",
            "browser_execution": "not_evaluated",
            "os_code_signing": "not_evaluated",
            "artifact_attestation": "not_evaluated_in_runner_receipt",
            "automatic_update": "not_implemented",
            "rollback": "not_implemented",
            "engineering_design": "not_authoritative",
            "commercial_use": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "one_source_bound_portable_workstation_archive_verified_and_replayed_twice_"
            "from_a_fresh_extraction_on_one_runner_not_cross_platform_browser_code_"
            "signing_update_rollback_or_release_authority"
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--platform-tag", choices=PLATFORMS, required=True)
    parser.add_argument("--runner-profile", choices=RUNNER_PROFILES, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        payload = run_clean_install_replay(
            archive_path=arguments.archive,
            expected_source_commit=arguments.expected_source_commit,
            expected_platform_tag=arguments.platform_tag,
            runner_profile=arguments.runner_profile,
        )
        _write_new(arguments.receipt, payload)
    except (CleanInstallReplayError, OSError, zipfile.BadZipFile) as error:
        print(f"Frame Alpha clean-install replay failed: {error}", file=sys.stderr)
        return 1
    print(_canonical_bytes(payload).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
