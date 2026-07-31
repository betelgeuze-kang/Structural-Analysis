#!/usr/bin/env python3
"""Build a source-bound receipt for the pinned canonical verification runtime."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import locale
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "canonical/verification-environment.v1.json"
LOCK_ROW = re.compile(
    r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[^ ]+) --hash=sha256:(?P<hash>[0-9a-f]{64})$"
)


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


def build_receipt(
    config: dict[str, Any],
    *,
    repo_root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    source_sha: str | None = None,
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

    libc_name, libc_version = platform.libc_ver()
    receipt = {
        "schema_version": "canonical-verification-receipt.v1",
        "source_commit_sha": source_sha or _git_source_sha(repo_root),
        "container": dict(config["container"]),
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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", type=Path, metavar="PATH")
    mode.add_argument("--check", type=Path, metavar="PATH")
    parser.add_argument("--enforce", action="store_true")
    args = parser.parse_args(argv)

    config = load_config(args.config, repo_root=args.repo_root)
    receipt = build_receipt(
        config,
        repo_root=args.repo_root,
        source_sha=args.source_sha,
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
