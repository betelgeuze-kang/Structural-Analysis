#!/usr/bin/env python3
"""Validate and bind four retained bounded-planar wheel smoke artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence


HASH_PREFIX = "sha256:"
SCHEMA_VERSION = "bounded-planar-wheel-smoke-four-way.v1"
RECEIPT_SCHEMA_VERSION = "bounded-planar-wheel-smoke.v4"
EXPECTED_COORDINATES = (
    "ubuntu-latest|python-3.10",
    "ubuntu-latest|python-3.12",
    "windows-latest|python-3.10",
    "windows-latest|python-3.12",
)
EXPECTED_RUNTIME_VERSIONS = {
    "numpy": "1.26.4",
    "scipy": "1.12.0",
    "matplotlib": "3.10.3",
    "jsonschema": "4.24.0",
}
EXPECTED_BUILD_SYSTEM_REQUIREMENTS = [
    "setuptools==80.9.0",
    "wheel==0.45.1",
    "packaging==26.2",
    "tomli==2.4.1; python_version < '3.11'",
]
EXPECTED_RUNTIME_CONSTRAINTS_PATH = "ci/bounded-planar-wheel-smoke.constraints.txt"
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_WHEEL_FILENAME_RE = re.compile(
    r"^structural_analysis-[A-Za-z0-9_.+]+-py3-none-any\.whl$"
)


class WheelSmokeManifestError(RuntimeError):
    """Raised when retained wheel evidence is missing or inconsistent."""


def _sha256(path: Path) -> str:
    return HASH_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()


def _content_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def _serialized(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(_serialized(payload))
        temporary = Path(handle.name)
    temporary.replace(path)


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WheelSmokeManifestError(f"receipt_invalid:{path.as_posix()}") from error
    if not isinstance(payload, dict):
        raise WheelSmokeManifestError(f"receipt_not_object:{path.as_posix()}")
    return payload


def _require_hash(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith(HASH_PREFIX)
        or len(value) != len(HASH_PREFIX) + 64
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise WheelSmokeManifestError(f"hash_invalid:{field}")
    return value


def _artifact_directory(receipts_directory: Path, receipt_path: Path) -> str:
    relative = receipt_path.relative_to(receipts_directory)
    if len(relative.parts) < 2:
        raise WheelSmokeManifestError(
            f"receipt_artifact_directory_missing:{relative.as_posix()}"
        )
    return relative.parts[0]


def build_manifest(
    *,
    artifacts_directory: Path,
    source_commit_sha: str,
) -> dict[str, Any]:
    artifacts_directory = artifacts_directory.resolve()
    if not _GIT_SHA_RE.fullmatch(source_commit_sha):
        raise WheelSmokeManifestError("source_commit_sha_invalid")
    receipt_paths = sorted(artifacts_directory.glob("*/receipt.json"))
    if len(receipt_paths) != len(EXPECTED_COORDINATES):
        raise WheelSmokeManifestError(
            f"receipt_count_invalid:{len(receipt_paths)}!={len(EXPECTED_COORDINATES)}"
        )

    observed: dict[str, dict[str, Any]] = {}
    source_tree_shas: set[str] = set()
    runtime_constraint_hashes: set[str] = set()
    for receipt_path in receipt_paths:
        payload = _load_receipt(receipt_path)
        if payload.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise WheelSmokeManifestError(f"receipt_schema_invalid:{receipt_path.name}")
        if payload.get("contract_pass") is not True:
            raise WheelSmokeManifestError(
                f"receipt_contract_blocked:{receipt_path.name}"
            )
        if payload.get("source_commit_sha") != source_commit_sha:
            raise WheelSmokeManifestError(
                f"receipt_source_commit_mismatch:{receipt_path.name}"
            )
        source_tree_sha = str(payload.get("source_tree_sha", ""))
        if not _GIT_SHA_RE.fullmatch(source_tree_sha):
            raise WheelSmokeManifestError(
                f"receipt_source_tree_invalid:{receipt_path.name}"
            )
        source_tree_shas.add(source_tree_sha)
        if payload.get("build_system_requirements") != (
            EXPECTED_BUILD_SYSTEM_REQUIREMENTS
        ):
            raise WheelSmokeManifestError(
                f"build_system_requirements_mismatch:{receipt_path.name}"
            )
        runtime_constraints = payload.get("runtime_constraints")
        if not isinstance(runtime_constraints, Mapping):
            raise WheelSmokeManifestError(
                f"runtime_constraints_missing:{receipt_path.name}"
            )
        if runtime_constraints.get("path") != EXPECTED_RUNTIME_CONSTRAINTS_PATH:
            raise WheelSmokeManifestError(
                f"runtime_constraints_path_mismatch:{receipt_path.name}"
            )
        runtime_constraint_hashes.add(
            _require_hash(
                runtime_constraints.get("sha256"),
                field=f"runtime_constraints:{receipt_path.name}",
            )
        )

        coordinate_payload = payload.get("coordinate")
        if not isinstance(coordinate_payload, Mapping):
            raise WheelSmokeManifestError(
                f"receipt_coordinate_missing:{receipt_path.name}"
            )
        coordinate = str(coordinate_payload.get("coordinate_id", ""))
        if coordinate not in EXPECTED_COORDINATES:
            raise WheelSmokeManifestError(f"coordinate_unexpected:{coordinate}")
        if coordinate in observed:
            raise WheelSmokeManifestError(f"coordinate_duplicate:{coordinate}")
        expected_os, expected_python = coordinate.split("|python-", maxsplit=1)
        if coordinate_payload.get("os_label") != expected_os:
            raise WheelSmokeManifestError(f"coordinate_os_mismatch:{coordinate}")
        if coordinate_payload.get("requested_python_version") != expected_python:
            raise WheelSmokeManifestError(
                f"coordinate_python_request_mismatch:{coordinate}"
            )

        artifact_directory = _artifact_directory(
            artifacts_directory,
            receipt_path,
        )
        expected_artifact_directory = (
            f"bounded-planar-wheel-smoke-{expected_os}-python-{expected_python}"
        )
        if artifact_directory != expected_artifact_directory:
            raise WheelSmokeManifestError(
                f"artifact_coordinate_mismatch:{artifact_directory}"
            )
        if payload.get("same_run_build_count") != 2:
            raise WheelSmokeManifestError(f"build_count_invalid:{coordinate}")
        if payload.get("same_run_wheel_byte_identical") is not True:
            raise WheelSmokeManifestError(f"same_run_identity_blocked:{coordinate}")
        builds = payload.get("wheel_builds")
        if not isinstance(builds, list) or len(builds) != 2:
            raise WheelSmokeManifestError(f"wheel_builds_invalid:{coordinate}")
        wheel_filename = str(payload.get("wheel_filename", ""))
        if not _WHEEL_FILENAME_RE.fullmatch(wheel_filename):
            raise WheelSmokeManifestError(
                f"wheel_filename_invalid:{coordinate}:{wheel_filename}"
            )
        wheel_hash = _require_hash(
            payload.get("wheel_sha256"),
            field=f"wheel_sha256:{coordinate}",
        )
        for build_number, build in enumerate(builds, start=1):
            if not isinstance(build, Mapping):
                raise WheelSmokeManifestError(f"wheel_build_invalid:{coordinate}")
            if build.get("build_number") != build_number:
                raise WheelSmokeManifestError(
                    f"wheel_build_number_invalid:{coordinate}"
                )
            if build.get("wheel_filename") != wheel_filename:
                raise WheelSmokeManifestError(
                    f"wheel_build_filename_mismatch:{coordinate}"
                )
            if build.get("wheel_sha256") != wheel_hash:
                raise WheelSmokeManifestError(f"wheel_build_hash_mismatch:{coordinate}")

        wheels = sorted(receipt_path.parent.rglob(wheel_filename))
        if len(wheels) != 1:
            raise WheelSmokeManifestError(
                f"preserved_wheel_count_invalid:{coordinate}:{len(wheels)}"
            )
        wheel_path = wheels[0]
        if _sha256(wheel_path) != wheel_hash:
            raise WheelSmokeManifestError(f"preserved_wheel_hash_mismatch:{coordinate}")
        if payload.get("installed_console_script_executed") is not True:
            raise WheelSmokeManifestError(
                f"installed_console_script_not_executed:{coordinate}"
            )

        runtime = payload.get("runtime")
        if not isinstance(runtime, Mapping):
            raise WheelSmokeManifestError(f"runtime_missing:{coordinate}")
        actual_python = str(runtime.get("python_version", ""))
        if ".".join(actual_python.split(".")[:2]) != expected_python:
            raise WheelSmokeManifestError(
                f"runtime_python_mismatch:{coordinate}:{actual_python}"
            )
        expected_system = "Linux" if expected_os == "ubuntu-latest" else "Windows"
        if runtime.get("system") != expected_system:
            raise WheelSmokeManifestError(f"runtime_system_mismatch:{coordinate}")
        packages = runtime.get("packages")
        if not isinstance(packages, Mapping):
            raise WheelSmokeManifestError(f"runtime_packages_missing:{coordinate}")
        for distribution, expected_version in EXPECTED_RUNTIME_VERSIONS.items():
            if packages.get(distribution) != expected_version:
                raise WheelSmokeManifestError(
                    "runtime_package_mismatch:"
                    f"{coordinate}:{distribution}:{packages.get(distribution)}"
                )
        if not isinstance(packages.get("pip"), str) or not packages["pip"]:
            raise WheelSmokeManifestError(f"runtime_pip_missing:{coordinate}")

        observed[coordinate] = {
            "coordinate_id": coordinate,
            "artifact_directory": artifact_directory,
            "receipt_file": receipt_path.name,
            "receipt_sha256": _sha256(receipt_path),
            "wheel_file": wheel_path.relative_to(receipt_path.parent).as_posix(),
            "wheel_filename": wheel_filename,
            "wheel_sha256": wheel_hash,
            "wheel_byte_length": wheel_path.stat().st_size,
            "runtime": runtime,
        }

    missing = sorted(set(EXPECTED_COORDINATES) - set(observed))
    if missing:
        raise WheelSmokeManifestError(
            "required_coordinates_missing:" + ",".join(missing)
        )
    if len(source_tree_shas) != 1:
        raise WheelSmokeManifestError("source_tree_sha_not_uniform")
    if len(runtime_constraint_hashes) != 1:
        raise WheelSmokeManifestError("runtime_constraints_hash_not_uniform")

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit_sha,
        "source_tree_sha": next(iter(source_tree_shas)),
        "build_system_requirements": EXPECTED_BUILD_SYSTEM_REQUIREMENTS,
        "runtime_constraints": {
            "path": EXPECTED_RUNTIME_CONSTRAINTS_PATH,
            "sha256": next(iter(runtime_constraint_hashes)),
        },
        "required_coordinates": list(EXPECTED_COORDINATES),
        "observed_coordinate_count": len(observed),
        "coordinates": [observed[key] for key in EXPECTED_COORDINATES],
        "contract_pass": True,
        "blockers": [],
        "claims": {
            "each_coordinate_same_run_wheel_byte_identity": True,
            "four_coordinate_preserved_wheel_hashes_verified": True,
            "installed_console_script_executed_on_all_coordinates": True,
        },
        "claim_boundary": (
            "This manifest binds four exact-source workflow artifacts and verifies "
            "that each retained wheel matches two byte-identical builds within its "
            "own execution coordinate. It does not claim future-run or cross-platform "
            "wheel byte equality, canonical-environment identity, or release readiness."
        ),
    }
    manifest["manifest_sha256"] = _content_hash(manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    payload = build_manifest(
        artifacts_directory=args.artifacts_dir,
        source_commit_sha=args.source_commit,
    )
    _atomic_write_json(args.out, payload)
    if args.json:
        print(_serialized(payload), end="")
    else:
        print(
            "bounded planar wheel smoke manifest: pass | "
            f"coordinates={payload['observed_coordinate_count']} | "
            f"manifest={payload['manifest_sha256']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
