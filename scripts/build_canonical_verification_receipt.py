#!/usr/bin/env python3
"""Build a source-bound receipt for the pinned canonical verification runtime."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import locale
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping
import zipfile

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "canonical/verification-environment.v1.json"
DEFAULT_PROJECT_WHEEL_SCHEMA = (
    ROOT / "canonical/canonical-project-wheel-contract.v1.schema.json"
)
LOCK_ROW = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^ ]+) --hash=sha256:(?P<hash>[0-9a-f]{64})$"
)
HASH_PREFIX = "sha256:"
INSTALLED_WHEEL_PROFILE = "p0-canonical-installed-wheel.v1"
REPLAY_CASE_IDS = ("member_feature", "prescribed_settlement")
REPLAY_HASH_FIELDS = (
    "result_hash",
    "engineering_result_hash",
    "checkpoint_sha256",
)
LINEAR_ALGEBRA_ROLE_KEYS = (
    "name",
    "version",
    "found",
    "detection method",
    "openblas configuration",
)
LINEAR_ALGEBRA_LIBRARY_KEYS = (
    "filename",
    "sha256",
    "distribution",
    "member",
    "wheel_filename",
    "wheel_sha256",
)
LINEAR_ALGEBRA_LOADED_LIBRARY_KEYS = (
    "path",
    *LINEAR_ALGEBRA_LIBRARY_KEYS,
)
LINEAR_ALGEBRA_RAW_LIBRARY_KEYS = ("path", "sha256")


class CanonicalEnvironmentError(ValueError):
    """Raised when a canonical environment declaration is invalid."""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CanonicalEnvironmentError(f"{path}: root must be an object")
    return payload


def load_config(
    path: Path = DEFAULT_CONFIG, *, repo_root: Path = ROOT
) -> dict[str, Any]:
    config = _read_json(path)
    if config.get("schema_version") != "canonical-verification-environment.v1":
        raise CanonicalEnvironmentError("unsupported canonical environment schema")
    container = config.get("container")
    if not isinstance(container, dict):
        raise CanonicalEnvironmentError("container must be an object")
    digest = str(container.get("digest", ""))
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise CanonicalEnvironmentError(
            "container.digest must be an immutable sha256 digest"
        )
    python_contract = config.get("python")
    if not isinstance(python_contract, dict) or not re.fullmatch(
        r"\d+\.\d+\.\d+", str(python_contract.get("version", ""))
    ):
        raise CanonicalEnvironmentError("python.version must pin a patch release")
    lock_contract = config.get("dependency_lock")
    if not isinstance(lock_contract, dict):
        raise CanonicalEnvironmentError("dependency_lock must be an object")
    lock_path = repo_root / str(lock_contract.get("path", ""))
    load_lock(lock_path)
    determinism = config.get("determinism")
    if not isinstance(determinism, dict) or not determinism:
        raise CanonicalEnvironmentError("determinism variables are required")
    project_wheel = config.get("project_wheel")
    if (
        not isinstance(project_wheel, dict)
        or project_wheel.get("contract_schema_version")
        != "canonical-project-wheel-contract.v1"
    ):
        raise CanonicalEnvironmentError("project_wheel contract is required")
    linear_algebra = config.get("linear_algebra")
    if not isinstance(linear_algebra, dict):
        raise CanonicalEnvironmentError("linear_algebra contract is required")
    if linear_algebra.get("provider_family") != "openblas":
        raise CanonicalEnvironmentError("linear_algebra provider must be openblas")
    distributions = linear_algebra.get("wheel_bound_distributions")
    if distributions != ["numpy", "scipy"]:
        raise CanonicalEnvironmentError(
            "linear_algebra wheel-bound distributions must be numpy and scipy"
        )
    return config


def load_lock(path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = LOCK_ROW.fullmatch(line)
        if match is None:
            raise CanonicalEnvironmentError(
                f"{path}:{line_number}: dependency is not exactly hashed"
            )
        normalized = match.group("name").lower().replace("_", "-")
        if normalized in rows:
            raise CanonicalEnvironmentError(
                f"{path}:{line_number}: duplicate dependency {normalized}"
            )
        rows[normalized] = {
            "version": match.group("version"),
            "wheel_sha256": match.group("hash"),
        }
    for required in ("numpy", "scipy", "setuptools", "wheel"):
        if required not in rows:
            raise CanonicalEnvironmentError(f"dependency lock is missing {required}")
    return rows


def _git_source_sha(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    sha = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise CanonicalEnvironmentError("git did not return an exact source SHA")
    return sha


def _numpy_build_dependency(name: str) -> dict[str, Any]:
    import numpy as np

    config = getattr(np.__config__, "CONFIG", {})
    dependencies = (
        config.get("Build Dependencies", {}) if isinstance(config, dict) else {}
    )
    value = dependencies.get(name, {}) if isinstance(dependencies, dict) else {}
    if isinstance(value, dict):
        return {str(key): item for key, item in sorted(value.items())}
    return {"identity": str(value)}


def _linear_algebra_libraries() -> list[dict[str, str]]:
    # Importing NumPy above causes its linked BLAS/LAPACK objects to appear here.
    maps = Path("/proc/self/maps")
    if not maps.is_file():
        return []
    candidates: set[Path] = set()
    for line in maps.read_text(encoding="utf-8", errors="replace").splitlines():
        path_text = line.rsplit(" ", 1)[-1]
        lowered = path_text.lower()
        if path_text.startswith("/") and any(
            token in lowered for token in ("blas", "lapack", "mkl")
        ):
            candidates.add(Path(path_text))
    rows: list[dict[str, str]] = []
    for path in sorted(candidates):
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            continue
        rows.append({"path": str(path), "sha256": digest})
    return rows


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return HASH_PREFIX + digest.hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def _installed_replay_projection(
    replay: Mapping[str, Any], *, cases_key: str = "cases"
) -> dict[str, Any]:
    cases = replay.get(cases_key)
    cases = cases if isinstance(cases, Mapping) else {}
    return {
        "wheel_sha256": replay.get("wheel_sha256"),
        "installed_source_commit_sha": replay.get("installed_source_commit_sha"),
        "installed_source_date_epoch": replay.get("installed_source_date_epoch"),
        "cases": {
            case_id: {
                key: (
                    cases[case_id].get(key)
                    if isinstance(cases.get(case_id), Mapping)
                    else None
                )
                for key in REPLAY_HASH_FIELDS
            }
            for case_id in REPLAY_CASE_IDS
        },
    }


def _source_commit_timestamp(repo_root: Path, source_sha: str) -> int:
    result = subprocess.run(
        ["git", "show", "-s", "--format=%ct", source_sha],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if result.returncode != 0 or not value.isdigit() or int(value) <= 0:
        raise CanonicalEnvironmentError("source commit timestamp is unavailable")
    return int(value)


def validate_project_wheel_contract(
    contract: Mapping[str, Any],
    *,
    wheel_path: Path | None,
    source_sha: str,
    source_date_epoch: int,
) -> list[str]:
    violations: list[str] = []
    schema = _read_json(DEFAULT_PROJECT_WHEEL_SCHEMA)
    if list(Draft202012Validator(schema).iter_errors(dict(contract))):
        violations.append("project_wheel_schema_invalid")
    if contract.get("schema_version") != "canonical-project-wheel-contract.v1":
        violations.append("project_wheel_schema_mismatch")
    if contract.get("contract_pass") is not True or contract.get("violations") != []:
        violations.append("project_wheel_contract_blocked")
    if contract.get("source_commit_sha") != source_sha:
        violations.append("project_wheel_source_sha_mismatch")
    if contract.get("source_date_epoch") != source_date_epoch:
        violations.append("project_wheel_source_date_epoch_mismatch")
    build = contract.get("build")
    if not isinstance(build, Mapping):
        violations.append("project_wheel_build_contract_missing")
    else:
        expected_build = {
            "pep517_isolation": True,
            "dependency_index_access": False,
            "pip_cache": False,
            "source_export": "git-archive-exact-commit",
            "submodules_allowed": False,
            "lfs_pointer_package_inputs_allowed": False,
            "repeated_build_count": 2,
            "reproducible_wheel_bytes": True,
        }
        for key, expected in expected_build.items():
            if build.get(key) != expected:
                violations.append(f"project_wheel_build_mismatch:{key}")
    wheelhouse = contract.get("dependency_wheelhouse")
    if (
        not isinstance(wheelhouse, Mapping)
        or wheelhouse.get("all_locked_hashes_verified") is not True
    ):
        violations.append("project_wheel_dependency_wheelhouse_unverified")
    wheel = contract.get("wheel")
    if not isinstance(wheel, Mapping):
        violations.append("project_wheel_identity_missing")
        wheel = {}
    expected_hash = wheel.get("sha256")
    if not isinstance(expected_hash, str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", expected_hash
    ):
        violations.append("project_wheel_sha256_invalid")
    if wheel.get("repeat_sha256") != expected_hash:
        violations.append("project_wheel_repeat_sha256_mismatch")
    record = wheel.get("record")
    if (
        not isinstance(record, Mapping)
        or record.get("all_payload_entries_sha256_verified") is not True
    ):
        violations.append("project_wheel_record_unverified")
    if wheel_path is None or not wheel_path.is_file():
        violations.append("project_wheel_artifact_missing")
    else:
        if wheel_path.name != wheel.get("filename"):
            violations.append("project_wheel_filename_mismatch")
        if _sha256(wheel_path) != expected_hash:
            violations.append("project_wheel_artifact_sha256_mismatch")
        if wheel_path.stat().st_size != wheel.get("byte_length"):
            violations.append("project_wheel_artifact_size_mismatch")
    replay = contract.get("installed_replay")
    if not isinstance(replay, Mapping):
        violations.append("installed_wheel_replay_missing")
    else:
        if replay.get("schema_version") != "bounded-planar-wheel-smoke.v2":
            violations.append("installed_wheel_replay_schema_mismatch")
        if replay.get("contract_pass") is not True:
            violations.append("installed_wheel_replay_blocked")
        if replay.get("execution_count") != 2:
            violations.append("installed_wheel_replay_execution_count_mismatch")
        if replay.get("exact_repeat_match") is not True:
            violations.append("installed_wheel_replay_repeat_mismatch")
        first_projection_sha256 = str(replay.get("first_projection_sha256", ""))
        repeat_projection_sha256 = str(replay.get("repeat_projection_sha256", ""))
        first_projection = _installed_replay_projection(replay)
        repeat_projection = _installed_replay_projection(
            replay, cases_key="repeat_cases"
        )
        if first_projection_sha256 != _canonical_hash(first_projection):
            violations.append("installed_wheel_replay_projection_hash_mismatch")
        if not re.fullmatch(
            r"sha256:[0-9a-f]{64}", repeat_projection_sha256
        ) or repeat_projection_sha256 != _canonical_hash(repeat_projection):
            violations.append("installed_wheel_replay_projection_hash_invalid")
        if first_projection != repeat_projection:
            violations.append("installed_wheel_replay_repeat_evidence_mismatch")
        if replay.get("wheel_origin") != "prebuilt_exact_artifact":
            violations.append("installed_wheel_replay_origin_mismatch")
        if replay.get("wheel_sha256") != expected_hash:
            violations.append("installed_wheel_replay_sha256_mismatch")
        if replay.get("installed_source_commit_sha") != source_sha:
            violations.append("installed_wheel_replay_source_sha_mismatch")
        if replay.get("installed_source_date_epoch") != source_date_epoch:
            violations.append("installed_wheel_replay_source_date_epoch_mismatch")
        cases = replay.get("cases")
        if not isinstance(cases, Mapping) or set(cases) != set(REPLAY_CASE_IDS):
            violations.append("installed_wheel_replay_case_set_mismatch")
        repeat_cases = replay.get("repeat_cases")
        if not isinstance(repeat_cases, Mapping) or set(repeat_cases) != set(
            REPLAY_CASE_IDS
        ):
            violations.append("installed_wheel_replay_repeat_case_set_mismatch")
    return violations


def validate_persisted_canonical_bundle(
    *,
    repo_root: Path = ROOT,
    receipt_path: Path,
    project_wheel_contract_path: Path,
    project_wheel_path: Path,
    source_sha: str | None = None,
    source_date_epoch: int | None = None,
) -> list[str]:
    """Revalidate retained canonical evidence without recreating its runtime.

    The canonical job is the authority for the runtime observation. This validator
    rechecks every retained byte that can be verified outside that container: the
    receipt schema/declarations, exact-source binding, embedded wheel contract,
    raw wheel hash/size/RECORD, and repeat-replay projection hashes.
    """

    def resolved(path: Path) -> Path:
        return path if path.is_absolute() else repo_root / path

    violations: list[str] = []
    try:
        receipt = _read_json(resolved(receipt_path))
    except (OSError, json.JSONDecodeError, CanonicalEnvironmentError):
        return ["canonical_receipt_json_invalid"]
    try:
        project_wheel_contract = _read_json(resolved(project_wheel_contract_path))
    except (OSError, json.JSONDecodeError, CanonicalEnvironmentError):
        return ["project_wheel_contract_json_invalid"]

    observed_source_sha = source_sha
    if observed_source_sha is None:
        try:
            observed_source_sha = _git_source_sha(repo_root)
        except (OSError, subprocess.SubprocessError, CanonicalEnvironmentError):
            return ["canonical_source_sha_unavailable"]
    if not re.fullmatch(r"[0-9a-f]{40}", observed_source_sha):
        return ["canonical_source_sha_invalid"]

    observed_source_date_epoch = source_date_epoch
    if observed_source_date_epoch is None:
        try:
            observed_source_date_epoch = _source_commit_timestamp(
                repo_root, observed_source_sha
            )
        except (OSError, subprocess.SubprocessError, CanonicalEnvironmentError):
            return ["canonical_source_date_epoch_unavailable"]

    try:
        config = load_config(
            repo_root / "canonical/verification-environment.v1.json",
            repo_root=repo_root,
        )
        receipt_schema = _read_json(
            repo_root / "canonical/canonical-verification-receipt.v1.schema.json"
        )
        receipt_schema_errors = list(
            Draft202012Validator(receipt_schema).iter_errors(receipt)
        )
    except (OSError, json.JSONDecodeError, CanonicalEnvironmentError):
        return ["canonical_declaration_validation_failed"]
    if receipt_schema_errors:
        violations.append("canonical_receipt_schema_invalid")

    if receipt.get("contract_profile") != INSTALLED_WHEEL_PROFILE:
        violations.append("canonical_receipt_profile_mismatch")
    if receipt.get("contract_pass") is not True or receipt.get("violations") != []:
        violations.append("canonical_receipt_contract_blocked")
    for key in ("source_commit_sha", "source_checkout_head_sha"):
        if receipt.get(key) != observed_source_sha:
            violations.append(f"canonical_receipt_{key}_mismatch")
    if receipt.get("source_date_epoch") != observed_source_date_epoch:
        violations.append("canonical_receipt_source_date_epoch_mismatch")
    if receipt.get("container") != config.get("container"):
        violations.append("canonical_receipt_container_mismatch")
    if receipt.get("project_wheel") != project_wheel_contract:
        violations.append("canonical_receipt_project_wheel_mismatch")

    runtime = receipt.get("runtime")
    if not isinstance(runtime, Mapping):
        runtime = {}
        violations.append("canonical_receipt_runtime_missing")
    python_identity = runtime.get("python")
    if not isinstance(python_identity, Mapping):
        python_identity = {}
    expected_python = config["python"]
    for key in ("implementation", "version", "abi"):
        if python_identity.get(key) != expected_python.get(key):
            violations.append(f"canonical_receipt_python_{key}_mismatch")

    locked = load_lock(repo_root / str(config["dependency_lock"]["path"]))
    packages = runtime.get("packages")
    if not isinstance(packages, Mapping):
        packages = {}
    for package_name, contract in sorted(locked.items()):
        package = packages.get(package_name)
        expected = {
            "version": contract["version"],
            "expected_version": contract["version"],
            "wheel_sha256": contract["wheel_sha256"],
        }
        if package != expected:
            violations.append(
                f"canonical_receipt_dependency_identity_mismatch:{package_name}"
            )
    if runtime.get("numpy_runtime_version") != locked["numpy"]["version"]:
        violations.append("canonical_receipt_numpy_runtime_version_mismatch")
    if runtime.get("scipy_runtime_version") != locked["scipy"]["version"]:
        violations.append("canonical_receipt_scipy_runtime_version_mismatch")

    determinism = config["determinism"]
    expected_threads = {
        key: determinism.get(key)
        for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")
    }
    if runtime.get("thread_limits") != expected_threads:
        violations.append("canonical_receipt_thread_limits_mismatch")
    locale_identity = runtime.get("locale")
    if not isinstance(locale_identity, Mapping):
        locale_identity = {}
    for key in ("LANG", "LC_ALL"):
        if locale_identity.get(key) != determinism.get(key):
            violations.append(f"canonical_receipt_locale_{key}_mismatch")
    if runtime.get("timezone") != determinism.get("TZ"):
        violations.append("canonical_receipt_timezone_mismatch")
    if runtime.get("python_hash_seed") != determinism.get("PYTHONHASHSEED"):
        violations.append("canonical_receipt_python_hash_seed_mismatch")

    linear_algebra_identity = runtime.get("linear_algebra_identity")
    if not isinstance(linear_algebra_identity, Mapping):
        linear_algebra_identity = {}
    violations.extend(
        _validate_persisted_linear_algebra_identity(
            runtime=runtime,
            identity=linear_algebra_identity,
            config=config,
            locked=locked,
        )
    )

    wheel_path = resolved(project_wheel_path)
    violations.extend(
        validate_project_wheel_contract(
            project_wheel_contract,
            wheel_path=wheel_path,
            source_sha=observed_source_sha,
            source_date_epoch=observed_source_date_epoch,
        )
    )
    try:
        from build_canonical_project_wheel import (
            CanonicalProjectWheelError,
            validate_wheel_record,
        )

        observed_record = validate_wheel_record(
            wheel_path,
            source_sha=observed_source_sha,
            source_date_epoch=observed_source_date_epoch,
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        zipfile.BadZipFile,
        CanonicalProjectWheelError,
    ):
        violations.append("project_wheel_record_validation_failed")
    else:
        wheel_identity = project_wheel_contract.get("wheel")
        expected_record = (
            wheel_identity.get("record")
            if isinstance(wheel_identity, Mapping)
            else None
        )
        if observed_record != expected_record:
            violations.append("project_wheel_record_identity_mismatch")
    return list(dict.fromkeys(violations))


def _exercise_linear_algebra() -> None:
    import numpy as np
    import scipy.linalg

    matrix = np.asarray([[4.0, 1.0], [1.0, 3.0]], dtype=np.float64)
    vector = np.asarray([1.0, 2.0], dtype=np.float64)
    np.linalg.solve(matrix, vector)
    scipy.linalg.solve(matrix, vector, assume_a="pos")


def _linear_algebra_role_identity(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value.get(key) for key in LINEAR_ALGEBRA_ROLE_KEYS}


def _linear_algebra_role_matches_provider(
    value: Mapping[str, Any], provider_family: object
) -> bool:
    if not isinstance(provider_family, str) or not provider_family:
        return False
    expected = provider_family.casefold()
    return any(
        expected in field.casefold()
        for field in (
            value.get("name"),
            value.get("openblas configuration"),
        )
        if isinstance(field, str)
    )


def _exact_mapping_keys(value: object, expected: tuple[str, ...]) -> bool:
    return isinstance(value, Mapping) and set(value) == set(expected)


def _valid_library_member(member: object, filename: str) -> bool:
    if not isinstance(member, str) or not member or "\\" in member:
        return False
    path = PurePosixPath(member)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.name == filename
        and any(token in member.lower() for token in ("blas", "lapack", "mkl"))
    )


def _validate_persisted_linear_algebra_identity(
    *,
    runtime: Mapping[str, Any],
    identity: Mapping[str, Any],
    config: Mapping[str, Any],
    locked: Mapping[str, Mapping[str, str]],
) -> list[str]:
    """Recompute all relationships in the retained BLAS/LAPACK identity."""

    violations: list[str] = []
    linear_algebra = config.get("linear_algebra")
    determinism = config.get("determinism")
    linear_algebra = linear_algebra if isinstance(linear_algebra, Mapping) else {}
    determinism = determinism if isinstance(determinism, Mapping) else {}
    expected_provider = linear_algebra.get("provider_family")
    expected_coretype = determinism.get("OPENBLAS_CORETYPE")
    distributions_value = linear_algebra.get("wheel_bound_distributions")
    expected_distributions = (
        tuple(str(value) for value in distributions_value)
        if isinstance(distributions_value, list)
        else ()
    )

    if identity.get("provider_family") != expected_provider:
        violations.append("canonical_receipt_linear_algebra_provider_mismatch")
    if identity.get("openblas_coretype") != expected_coretype:
        violations.append("canonical_receipt_linear_algebra_coretype_mismatch")

    claimed_roles = identity.get("roles")
    if not isinstance(claimed_roles, Mapping) or set(claimed_roles) != {
        "blas",
        "lapack",
    }:
        violations.append("canonical_receipt_linear_algebra_roles_shape_mismatch")
        claimed_roles = {}
    for role in ("blas", "lapack"):
        runtime_role = runtime.get(role)
        claimed_role = claimed_roles.get(role)
        if not isinstance(runtime_role, Mapping):
            violations.append(
                f"canonical_receipt_linear_algebra_runtime_role_missing:{role}"
            )
            continue
        if not _exact_mapping_keys(claimed_role, LINEAR_ALGEBRA_ROLE_KEYS):
            violations.append(
                f"canonical_receipt_linear_algebra_role_shape_mismatch:{role}"
            )
        if claimed_role != _linear_algebra_role_identity(runtime_role):
            violations.append(
                f"canonical_receipt_linear_algebra_role_runtime_mismatch:{role}"
            )
        if not isinstance(claimed_role, Mapping):
            continue
        if claimed_role.get("found") is not True:
            violations.append(f"canonical_receipt_linear_algebra_role_not_found:{role}")
        if not _linear_algebra_role_matches_provider(claimed_role, expected_provider):
            violations.append(
                f"canonical_receipt_linear_algebra_role_provider_mismatch:{role}"
            )

    raw_libraries = runtime.get("linear_algebra_shared_libraries")
    if not isinstance(raw_libraries, list) or not raw_libraries:
        violations.append(
            "canonical_receipt_linear_algebra_shared_libraries_shape_mismatch"
        )
        raw_libraries = []
    normalized_raw: list[dict[str, str]] = []
    for index, row in enumerate(raw_libraries):
        if not _exact_mapping_keys(row, LINEAR_ALGEBRA_RAW_LIBRARY_KEYS):
            violations.append(
                "canonical_receipt_linear_algebra_shared_library_shape_mismatch:"
                f"{index}"
            )
            continue
        path = row.get("path")
        digest = row.get("sha256")
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or "\\" in path
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        ):
            violations.append(
                "canonical_receipt_linear_algebra_shared_library_identity_invalid:"
                f"{index}"
            )
            continue
        normalized_raw.append({"path": path, "sha256": HASH_PREFIX + digest})
    if len({(row["path"], row["sha256"]) for row in normalized_raw}) != len(
        normalized_raw
    ):
        violations.append("canonical_receipt_linear_algebra_shared_library_duplicate")

    loaded_libraries = identity.get("loaded_libraries")
    if not isinstance(loaded_libraries, list) or not loaded_libraries:
        violations.append(
            "canonical_receipt_linear_algebra_loaded_libraries_shape_mismatch"
        )
        loaded_libraries = []
    normalized_loaded: list[dict[str, str]] = []
    observed_distributions: set[str] = set()
    wheel_filenames: dict[str, set[str]] = {
        distribution: set() for distribution in expected_distributions
    }
    for index, row in enumerate(loaded_libraries):
        if not _exact_mapping_keys(row, LINEAR_ALGEBRA_LOADED_LIBRARY_KEYS):
            violations.append(
                "canonical_receipt_linear_algebra_loaded_library_shape_mismatch:"
                f"{index}"
            )
            continue
        path = row.get("path")
        filename = row.get("filename")
        digest = row.get("sha256")
        distribution = row.get("distribution")
        member = row.get("member")
        wheel_filename = row.get("wheel_filename")
        wheel_sha256 = row.get("wheel_sha256")
        scalar_values = (
            path,
            filename,
            digest,
            distribution,
            member,
            wheel_filename,
            wheel_sha256,
        )
        if not all(isinstance(value, str) and value for value in scalar_values):
            violations.append(
                "canonical_receipt_linear_algebra_loaded_library_identity_invalid:"
                f"{index}"
            )
            continue
        assert isinstance(path, str)
        assert isinstance(filename, str)
        assert isinstance(digest, str)
        assert isinstance(distribution, str)
        assert isinstance(member, str)
        assert isinstance(wheel_filename, str)
        assert isinstance(wheel_sha256, str)
        if not path.startswith("/") or "\\" in path or Path(path).name != filename:
            violations.append(
                f"canonical_receipt_linear_algebra_path_filename_mismatch:{index}"
            )
        if not _valid_library_member(member, filename):
            violations.append(
                f"canonical_receipt_linear_algebra_member_filename_mismatch:{index}"
            )
        if re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            violations.append(
                f"canonical_receipt_linear_algebra_library_sha256_invalid:{index}"
            )
        if distribution not in expected_distributions:
            violations.append(
                f"canonical_receipt_linear_algebra_distribution_invalid:{index}"
            )
        else:
            observed_distributions.add(distribution)
            expected_wheel_sha256 = HASH_PREFIX + locked[distribution]["wheel_sha256"]
            if wheel_sha256 != expected_wheel_sha256:
                violations.append(
                    "canonical_receipt_linear_algebra_locked_wheel_sha256_mismatch:"
                    f"{distribution}"
                )
            expected_wheel_prefix = f"{distribution}-{locked[distribution]['version']}-"
            if (
                PurePosixPath(wheel_filename).name != wheel_filename
                or "\\" in wheel_filename
                or not wheel_filename.startswith(expected_wheel_prefix)
                or not wheel_filename.endswith(".whl")
            ):
                violations.append(
                    "canonical_receipt_linear_algebra_locked_wheel_filename_mismatch:"
                    f"{distribution}"
                )
            wheel_filenames[distribution].add(wheel_filename)
        normalized_loaded.append(
            {key: str(row[key]) for key in LINEAR_ALGEBRA_LOADED_LIBRARY_KEYS}
        )
    if len({(row["path"], row["sha256"]) for row in normalized_loaded}) != len(
        normalized_loaded
    ):
        violations.append("canonical_receipt_linear_algebra_loaded_library_duplicate")
    if normalized_raw != [
        {"path": row["path"], "sha256": row["sha256"]} for row in normalized_loaded
    ]:
        violations.append("canonical_receipt_linear_algebra_runtime_binding_mismatch")

    if observed_distributions != set(expected_distributions):
        violations.append(
            "canonical_receipt_linear_algebra_distribution_coverage_mismatch"
        )
    for distribution, filenames in wheel_filenames.items():
        if len(filenames) != 1:
            violations.append(
                "canonical_receipt_linear_algebra_locked_wheel_coverage_mismatch:"
                f"{distribution}"
            )

    expected_libraries = [
        {key: row[key] for key in LINEAR_ALGEBRA_LIBRARY_KEYS}
        for row in sorted(
            normalized_loaded,
            key=lambda item: (
                item["distribution"],
                item["filename"],
                item["sha256"],
            ),
        )
    ]
    libraries = identity.get("libraries")
    if not isinstance(libraries, list) or any(
        not _exact_mapping_keys(row, LINEAR_ALGEBRA_LIBRARY_KEYS) for row in libraries
    ):
        violations.append("canonical_receipt_linear_algebra_libraries_shape_mismatch")
    if libraries != expected_libraries:
        violations.append(
            "canonical_receipt_linear_algebra_libraries_projection_mismatch"
        )

    stable_projection = {
        key: identity.get(key)
        for key in ("provider_family", "openblas_coretype", "roles", "libraries")
    }
    if identity.get("fingerprint_sha256") != _canonical_hash(stable_projection):
        violations.append("canonical_receipt_linear_algebra_fingerprint_mismatch")
    if identity.get("wheel_membership_verified") is not True:
        violations.append("canonical_receipt_linear_algebra_wheel_binding_missing")
    return list(dict.fromkeys(violations))


def _exact_locked_wheels(
    *,
    wheelhouse: Path | None,
    locked: Mapping[str, Mapping[str, str]],
    distributions: list[str],
) -> tuple[dict[str, Path], list[str]]:
    violations: list[str] = []
    if wheelhouse is None or not wheelhouse.is_dir():
        return {}, ["linear_algebra_wheelhouse_missing"]
    wheels = sorted(wheelhouse.glob("*.whl"))
    observed: dict[str, list[Path]] = {}
    for wheel in wheels:
        observed.setdefault(_sha256(wheel), []).append(wheel)
    matched: dict[str, Path] = {}
    for distribution in distributions:
        expected = HASH_PREFIX + locked[distribution]["wheel_sha256"]
        candidates = observed.get(expected, [])
        if len(candidates) != 1:
            violations.append(
                f"linear_algebra_locked_wheel_count:{distribution}:{len(candidates)}"
            )
        else:
            matched[distribution] = candidates[0]
    return matched, violations


def build_linear_algebra_identity(
    config: Mapping[str, Any],
    *,
    locked: Mapping[str, Mapping[str, str]],
    wheelhouse: Path | None,
    openblas_coretype: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    _exercise_linear_algebra()
    raw_roles = {
        "blas": _numpy_build_dependency("blas"),
        "lapack": _numpy_build_dependency("lapack"),
    }
    roles = {
        name: _linear_algebra_role_identity(value)
        for name, value in sorted(raw_roles.items())
    }
    violations: list[str] = []
    provider_family = str(config["linear_algebra"]["provider_family"])
    for role, identity in roles.items():
        if identity.get("found") is not True:
            violations.append(f"linear_algebra_role_not_found:{role}")
        for key in LINEAR_ALGEBRA_ROLE_KEYS:
            if key == "found":
                continue
            if not isinstance(identity.get(key), str) or not identity[key]:
                violations.append(f"linear_algebra_role_identity_invalid:{role}:{key}")
        if not _linear_algebra_role_matches_provider(identity, provider_family):
            violations.append(f"linear_algebra_provider_mismatch:{role}")
    distributions = [
        str(value) for value in config["linear_algebra"]["wheel_bound_distributions"]
    ]
    exact_wheels, wheel_violations = _exact_locked_wheels(
        wheelhouse=wheelhouse,
        locked=locked,
        distributions=distributions,
    )
    violations.extend(wheel_violations)
    allowed_members: dict[str, list[dict[str, str]]] = {}
    for distribution, wheel in sorted(exact_wheels.items()):
        expected_wheel_prefix = f"{distribution}-{locked[distribution]['version']}-"
        if (
            "\\" in wheel.name
            or not wheel.name.startswith(expected_wheel_prefix)
            or not wheel.name.endswith(".whl")
        ):
            violations.append(f"linear_algebra_locked_wheel_filename:{distribution}")
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                lowered = member.lower()
                if not any(token in lowered for token in ("blas", "lapack", "mkl")):
                    continue
                if member.endswith("/"):
                    continue
                if not _valid_library_member(member, PurePosixPath(member).name):
                    violations.append(
                        f"linear_algebra_wheel_member_invalid:{distribution}"
                    )
                    continue
                digest = HASH_PREFIX + hashlib.sha256(archive.read(member)).hexdigest()
                allowed_members.setdefault(digest, []).append(
                    {
                        "distribution": distribution,
                        "member": member,
                        "wheel_filename": wheel.name,
                        "wheel_sha256": _sha256(wheel),
                    }
                )
    loaded = _linear_algebra_libraries()
    verified_libraries: list[dict[str, str]] = []
    matched_distributions: set[str] = set()
    if not loaded:
        violations.append("linear_algebra_shared_library_not_loaded")
    for library in loaded:
        digest = HASH_PREFIX + library["sha256"]
        candidates = allowed_members.get(digest, [])
        basename = Path(library["path"]).name
        matches = [
            candidate
            for candidate in candidates
            if Path(candidate["member"]).name == basename
        ]
        if len(matches) != 1:
            violations.append(f"linear_algebra_library_not_wheel_bound:{basename}")
            continue
        match = matches[0]
        matched_distributions.add(match["distribution"])
        verified_libraries.append(
            {
                "path": library["path"],
                "filename": basename,
                "sha256": digest,
                **match,
            }
        )
    for distribution in distributions:
        if distribution not in matched_distributions:
            violations.append(
                f"linear_algebra_distribution_library_not_loaded:{distribution}"
            )
    stable_projection = {
        "provider_family": provider_family,
        "openblas_coretype": openblas_coretype,
        "roles": roles,
        "libraries": [
            {key: row[key] for key in LINEAR_ALGEBRA_LIBRARY_KEYS}
            for row in sorted(
                verified_libraries,
                key=lambda item: (
                    item["distribution"],
                    item["filename"],
                    item["sha256"],
                ),
            )
        ],
    }
    return (
        {
            **stable_projection,
            "fingerprint_sha256": HASH_PREFIX
            + hashlib.sha256(
                json.dumps(
                    stable_projection,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest(),
            "loaded_libraries": verified_libraries,
            "wheel_membership_verified": not any(
                violation.startswith("linear_algebra_") for violation in violations
            ),
        },
        violations,
    )


def build_receipt(
    config: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    source_sha: str | None = None,
    project_wheel_contract: Mapping[str, Any] | None = None,
    project_wheel_path: Path | None = None,
    dependency_wheelhouse: Path | None = None,
) -> dict[str, Any]:
    import numpy as np
    import scipy

    env = os.environ if environ is None else environ
    lock_path = repo_root / str(config["dependency_lock"]["path"])
    locked = load_lock(lock_path)
    packages: dict[str, dict[str, str | None]] = {}
    violations: list[str] = []
    for package_name, contract in sorted(locked.items()):
        try:
            installed = metadata.version(package_name)
        except metadata.PackageNotFoundError:
            installed = None
        packages[package_name] = {
            "version": installed,
            "expected_version": contract["version"],
            "wheel_sha256": contract["wheel_sha256"],
        }
        if installed != contract["version"]:
            violations.append(f"dependency_version_mismatch:{package_name}:{installed}")

    observed_source_sha = source_sha or _git_source_sha(repo_root)
    if not re.fullmatch(r"[0-9a-f]{40}", observed_source_sha):
        violations.append("source_commit_sha_invalid")
    checkout_head_sha = _git_source_sha(repo_root)
    if observed_source_sha != checkout_head_sha:
        violations.append(
            f"source_checkout_head_mismatch:{observed_source_sha}:{checkout_head_sha}"
        )

    expected_python = str(config["python"]["version"])
    actual_python = platform.python_version()
    if actual_python != expected_python:
        violations.append(f"python_version_mismatch:{actual_python}")
    if platform.python_implementation() != config["python"]["implementation"]:
        violations.append(
            f"python_implementation_mismatch:{platform.python_implementation()}"
        )

    expected_env = config["determinism"]
    for key, expected in sorted(expected_env.items()):
        if env.get(key) != expected:
            violations.append(f"environment_mismatch:{key}:{env.get(key)}")

    try:
        source_date_epoch = _source_commit_timestamp(repo_root, observed_source_sha)
    except CanonicalEnvironmentError:
        source_date_epoch = 0
        violations.append("source_commit_timestamp_unavailable")
    if env.get("SOURCE_DATE_EPOCH") != str(source_date_epoch):
        violations.append(
            f"environment_mismatch:SOURCE_DATE_EPOCH:{env.get('SOURCE_DATE_EPOCH')}"
        )
    if project_wheel_contract is None:
        project_wheel_payload: dict[str, Any] = {"status": "missing"}
        violations.append("project_wheel_contract_missing")
    else:
        project_wheel_payload = dict(project_wheel_contract)
        violations.extend(
            validate_project_wheel_contract(
                project_wheel_contract,
                wheel_path=project_wheel_path,
                source_sha=observed_source_sha,
                source_date_epoch=source_date_epoch,
            )
        )
    linear_algebra_identity, linear_algebra_violations = build_linear_algebra_identity(
        config,
        locked=locked,
        wheelhouse=dependency_wheelhouse,
        openblas_coretype=env.get("OPENBLAS_CORETYPE"),
    )
    violations.extend(linear_algebra_violations)

    libc_name, libc_version = platform.libc_ver()
    receipt = {
        "schema_version": "canonical-verification-receipt.v1",
        "contract_profile": INSTALLED_WHEEL_PROFILE,
        "source_commit_sha": observed_source_sha,
        "source_checkout_head_sha": checkout_head_sha,
        "source_date_epoch": source_date_epoch,
        "container": dict(config["container"]),
        "project_wheel": project_wheel_payload,
        "runtime": {
            "python": {
                "implementation": platform.python_implementation(),
                "version": actual_python,
                "abi": config["python"]["abi"],
                "executable": sys.executable,
            },
            "packages": packages,
            "os": {
                "system": platform.system(),
                "release": platform.release(),
                "machine": platform.machine(),
                "platform": platform.platform(),
            },
            "libc": {"name": libc_name, "version": libc_version},
            "blas": _numpy_build_dependency("blas"),
            "lapack": _numpy_build_dependency("lapack"),
            "linear_algebra_shared_libraries": _linear_algebra_libraries(),
            "linear_algebra_identity": linear_algebra_identity,
            "thread_limits": {
                key: env.get(key)
                for key in (
                    "OPENBLAS_NUM_THREADS",
                    "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS",
                )
            },
            "locale": {
                "LANG": env.get("LANG"),
                "LC_ALL": env.get("LC_ALL"),
                "active": locale.setlocale(locale.LC_ALL, None),
            },
            "timezone": env.get("TZ"),
            "python_hash_seed": env.get("PYTHONHASHSEED"),
            "numpy_runtime_version": np.__version__,
            "scipy_runtime_version": scipy.__version__,
        },
        "contract_pass": not violations,
        "violations": violations,
    }
    return receipt


def _serialized(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-sha")
    parser.add_argument("--project-wheel-contract", type=Path)
    parser.add_argument("--project-wheel-dir", type=Path)
    parser.add_argument("--dependency-wheelhouse", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", type=Path, metavar="PATH")
    mode.add_argument("--check", type=Path, metavar="PATH")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config, repo_root=args.repo_root)
    project_wheel_contract = (
        _read_json(args.project_wheel_contract)
        if args.project_wheel_contract is not None
        else None
    )
    project_wheel_path: Path | None = None
    if project_wheel_contract is not None and args.project_wheel_dir is not None:
        wheel = project_wheel_contract.get("wheel")
        if isinstance(wheel, Mapping):
            project_wheel_path = args.project_wheel_dir / str(wheel.get("filename", ""))
    receipt = build_receipt(
        config,
        repo_root=args.repo_root,
        source_sha=args.source_sha,
        project_wheel_contract=project_wheel_contract,
        project_wheel_path=project_wheel_path,
        dependency_wheelhouse=args.dependency_wheelhouse,
    )
    text = _serialized(receipt)
    if args.write:
        _atomic_write(args.write, text)
    elif args.check:
        with tempfile.TemporaryDirectory(
            prefix="canonical-receipt-check-"
        ) as directory:
            candidate = Path(directory) / "receipt.json"
            candidate.write_text(text, encoding="utf-8")
            if not args.check.is_file() or args.check.read_text(
                encoding="utf-8"
            ) != candidate.read_text(encoding="utf-8"):
                print(f"stale canonical receipt: {args.check}", file=sys.stderr)
                return 1
    else:
        print(text, end="")
    return 1 if args.enforce and not receipt["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
