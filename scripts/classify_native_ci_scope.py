#!/usr/bin/env python3
"""Classify changed paths for the staged native CI lanes.

The classifier intentionally uses only the Python standard library so the gate
bootstrap can run before the Rust/C++ workspace exists.  Python is a CI control
plane dependency here; it is not part of the native product runtime.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

PROTECTED_EVIDENCE_PREFIXES = (
    ".betelgeuze/",
    "implementation/phase1/release_evidence/productization/",
)
PROTECTED_EVIDENCE_PATHS = frozenset(
    {
        "docs/commercial-structural-solver-product-gap-ledger.md",
        "docs/structural-analysis-ai-engine-gap-ledger.md",
    }
)

NATIVE_CI_CONTROL_PATHS = frozenset(
    {
        ".github/workflows/native-pr-fast.yml",
        ".github/workflows/native-nightly-quality.yml",
        "scripts/check_native_ci_contract.py",
        "scripts/check_native_capabilities.py",
        "scripts/check_native_dependency_boundary.py",
        "scripts/check_native_dependency_licenses.py",
        "scripts/classify_native_ci_scope.py",
        "tests/test_native_ci_scope.py",
        "tests/test_native_capability_manifest.py",
        "tests/test_native_ci_workflow_contract.py",
        "tests/test_native_dependency_license.py",
    }
)

MODELIR_ORACLE_PREFIXES = (
    "src/structural_analysis/model_ir/",
    "tests/fixtures/model_ir_v2/",
)
MODELIR_ORACLE_PATHS = frozenset(
    {
        "src/structural_analysis/schemas/model_ir_v2.schema.json",
        "tests/test_model_ir_v2_contract.py",
    }
)


def _normalize_path(raw: str) -> str:
    value = raw.replace("\\", "/").strip()
    if not value:
        raise ValueError("changed path must not be empty")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"changed path escapes repository root: {raw!r}")
    normalized = path.as_posix()
    if normalized == ".":
        raise ValueError("changed path must name a repository entry")
    return normalized


def _starts_with_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path.startswith(prefix) for prefix in prefixes)


def classify_paths(raw_paths: Iterable[str]) -> dict[str, object]:
    """Return deterministic applicability flags for one changed-path set."""

    paths = sorted({_normalize_path(path) for path in raw_paths})
    native_paths = [path for path in paths if path.startswith("native/")]
    ci_control_paths = [path for path in paths if path in NATIVE_CI_CONTROL_PATHS]
    protected_paths = [
        path
        for path in paths
        if path in PROTECTED_EVIDENCE_PATHS
        or _starts_with_any(path, PROTECTED_EVIDENCE_PREFIXES)
    ]
    modelir_oracle_paths = [
        path
        for path in paths
        if path in MODELIR_ORACLE_PATHS
        or _starts_with_any(path, MODELIR_ORACLE_PREFIXES)
        or (path.startswith("examples/") and ".model-ir.v2." in path)
    ]

    rust_paths = [
        path
        for path in native_paths
        if path in {"native/Cargo.toml", "native/Cargo.lock"}
        or path.startswith("native/crates/")
    ]
    cpp_paths = [
        path
        for path in native_paths
        if path.startswith("native/cpp/") or path.startswith("native/cmake/")
    ]
    abi_paths = [
        path
        for path in native_paths
        if path == "native/cpp/include/structural/abi_v1.h"
        or path.startswith("native/cpp/src/abi/")
        or path.startswith("native/tests/abi/")
        or path.startswith("native/crates/structural-ffi")
    ]
    modelir_paths = [
        path
        for path in native_paths
        if "model_ir" in path
        or "modelir" in path.lower()
        or path.startswith("native/crates/structural-contracts/")
        or path.startswith("native/tests/fixtures/")
    ]
    runtime_paths = [
        path
        for path in native_paths
        if path.startswith("native/crates/structural-runtime/")
        or path.startswith("native/crates/structural-report/")
        or path.startswith("native/crates/structural-cli/")
        or path.startswith("native/tests/integration/")
    ]
    hip_paths = [
        path
        for path in native_paths
        if path.startswith("native/cpp/hip/")
        or path.endswith((".hip", ".hip.cpp", ".hip.hpp"))
    ]

    docs_only = bool(paths) and all(path.startswith("docs/") for path in paths)
    applicable = bool(native_paths or modelir_oracle_paths or ci_control_paths)
    return {
        "schema_version": "native-ci-scope.v1",
        "changed_paths": paths,
        "changed_path_count": len(paths),
        "native": bool(native_paths),
        "rust": bool(rust_paths),
        "cpp": bool(cpp_paths),
        "abi": bool(abi_paths),
        "modelir": bool(modelir_paths or modelir_oracle_paths),
        "runtime": bool(runtime_paths),
        "hip": bool(hip_paths),
        "oracle": bool(modelir_oracle_paths),
        "ci_control": bool(ci_control_paths),
        "applicable": applicable,
        "docs_only": docs_only,
        "protected_evidence": bool(protected_paths),
        "protected_evidence_paths": protected_paths,
    }


def _git_changed_paths(*, base: str, head: str, repo_root: Path) -> list[str]:
    if not head:
        raise ValueError("head commit is required when --path is not used")
    zero_base = bool(base) and set(base) == {"0"}
    if not base:
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", f"{head}^"],
            cwd=repo_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        base = parent.stdout.strip() if parent.returncode == 0 else ""
    if zero_base or not base:
        command = [
            "git",
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-z",
            "-r",
            "--diff-filter=ACMRD",
            head,
        ]
    else:
        command = [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRD",
            f"{base}...{head}",
        ]
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        path
        for path in completed.stdout.decode("utf-8", "surrogateescape").split("\0")
        if path
    ]


def _write_github_outputs(path: Path, payload: dict[str, object]) -> None:
    boolean_keys = (
        "native",
        "rust",
        "cpp",
        "abi",
        "modelir",
        "runtime",
        "hip",
        "oracle",
        "ci_control",
        "applicable",
        "docs_only",
        "protected_evidence",
    )
    with path.open("a", encoding="utf-8") as stream:
        for key in boolean_keys:
            stream.write(f"{key}={str(bool(payload[key])).lower()}\n")
        stream.write(f"changed_path_count={payload['changed_path_count']}\n")
        stream.write(
            "changed_paths_json="
            + json.dumps(payload["changed_paths"], ensure_ascii=True, separators=(",", ":"))
            + "\n"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=os.environ.get("NATIVE_CI_BASE_SHA", ""))
    parser.add_argument("--head", default=os.environ.get("NATIVE_CI_HEAD_SHA", ""))
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--path", action="append", dest="paths")
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--fail-protected-evidence", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        changed_paths = (
            args.paths
            if args.paths is not None
            else _git_changed_paths(
                base=args.base,
                head=args.head,
                repo_root=args.repo_root.resolve(),
            )
        )
        payload = classify_paths(changed_paths)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"native CI scope classification failed: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.github_output is not None:
        _write_github_outputs(args.github_output, payload)
    if args.fail_protected_evidence and payload["protected_evidence"]:
        print(
            "native CI scope includes protected evidence: "
            + ", ".join(payload["protected_evidence_paths"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
