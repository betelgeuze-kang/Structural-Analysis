#!/usr/bin/env python3
"""Fail closed on native workspace ownership and Python-runtime violations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_SOURCE_ROOTS = (
    Path("native/crates"),
    Path("native/cpp/include"),
    Path("native/cpp/src"),
    Path("native/cpp/hip"),
)
SOURCE_SUFFIXES = frozenset({".rs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp"})
PYTHON_RUNTIME_PATTERNS = (
    re.compile(r"#\s*include\s*[<\"]Python\.h[>\"]"),
    re.compile(r"\bPy_(?:Initialize|Run|Import|Finalize)\w*\s*\("),
    re.compile(
        r"(?:std::process::)?Command::new\s*\(\s*[\"']python(?:3(?:\.\d+)?)?[\"']"
    ),
    re.compile(r"\b(?:exec|spawn|system)\s*\([^\n]*[\"']python(?:3)?[\"']"),
)


def check_boundary(repo_root: Path = ROOT) -> dict[str, object]:
    repo_root = repo_root.resolve()
    native_root = repo_root / "native"
    blockers: list[str] = []

    lockfiles = sorted(
        path.relative_to(repo_root).as_posix()
        for path in native_root.rglob("Cargo.lock")
    ) if native_root.exists() else []
    cargo_workspace = native_root / "Cargo.toml"
    if cargo_workspace.exists() and lockfiles != ["native/Cargo.lock"]:
        blockers.append(
            "native_workspace_must_own_exactly_one_root_lockfile:"
            + (",".join(lockfiles) if lockfiles else "none")
        )

    python_files = sorted(
        path.relative_to(repo_root).as_posix()
        for root in PRODUCT_SOURCE_ROOTS
        for path in (repo_root / root).rglob("*.py")
        if (repo_root / root).exists()
    )
    blockers.extend(f"python_file_in_native_product_source:{path}" for path in python_files)

    scanned_files = 0
    for relative_root in PRODUCT_SOURCE_ROOTS:
        source_root = repo_root / relative_root
        if not source_root.exists():
            continue
        for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
            if path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            scanned_files += 1
            text = path.read_text(encoding="utf-8", errors="replace")
            if any(pattern.search(text) for pattern in PYTHON_RUNTIME_PATTERNS):
                blockers.append(
                    "python_runtime_call_in_native_product_source:"
                    + path.relative_to(repo_root).as_posix()
                )

    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-dependency-boundary.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "cargo_workspace_present": cargo_workspace.exists(),
        "cargo_lockfiles": lockfiles,
        "scanned_product_source_files": scanned_files,
        "blockers": blockers,
        "claim_boundary": (
            "This check proves repository ownership and absence of direct Python runtime "
            "calls in native product source. It does not prove numerical parity or C6 "
            "Python decommission."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_boundary(args.repo_root)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native dependency boundary: {payload['status']}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
