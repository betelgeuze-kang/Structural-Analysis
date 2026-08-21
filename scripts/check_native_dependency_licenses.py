#!/usr/bin/env python3
"""Check locked Rust dependency sources and SPDX license policy for native code."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("native/dependency-policy.json")
SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})
SPDX_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
ALLOWED_REGISTRY_SOURCES = frozenset(
    {
        "registry+https://github.com/rust-lang/crates.io-index",
        "sparse+https://index.crates.io/",
    }
)


def _load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("native dependency policy must be a JSON object")
    return payload


def _license_ids(expression: str) -> set[str]:
    return {
        token
        for token in SPDX_TOKEN_RE.findall(expression)
        if token.upper() not in SPDX_OPERATORS
    }


def evaluate_metadata(
    metadata: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, object]], list[str]]:
    allowed_licenses = {
        str(value) for value in policy.get("allowed_license_ids", []) if str(value)
    }
    exceptions = {
        str(row.get("package", "")): row
        for row in policy.get("exceptions", [])
        if isinstance(row, dict) and str(row.get("package", ""))
    }
    blockers: list[str] = []
    rows: list[dict[str, object]] = []
    for package in sorted(
        metadata.get("packages", []),
        key=lambda row: (str(row.get("name", "")), str(row.get("version", ""))),
    ):
        name = str(package.get("name", ""))
        version = str(package.get("version", ""))
        package_id = f"{name}@{version}"
        source = package.get("source")
        license_expression = str(package.get("license") or "").strip()
        exception = exceptions.get(package_id)
        external = source is not None
        license_ids = sorted(_license_ids(license_expression))
        source_allowed = (
            not external
            or str(source) in ALLOWED_REGISTRY_SOURCES
            or bool(exception and exception.get("allow_source") is True)
        )
        license_allowed = (
            not external
            or bool(license_ids and set(license_ids) <= allowed_licenses)
            or bool(exception and exception.get("allow_license") is True)
        )
        if external and not license_expression:
            blockers.append(f"dependency_license_missing:{package_id}")
        elif external and not license_allowed:
            blockers.append(
                f"dependency_license_not_allowed:{package_id}:{license_expression}"
            )
        if external and not source_allowed:
            blockers.append(f"dependency_source_not_allowed:{package_id}:{source}")
        rows.append(
            {
                "package": package_id,
                "external": external,
                "source": source,
                "source_allowed": source_allowed,
                "license": license_expression,
                "license_ids": license_ids,
                "license_allowed": license_allowed,
                "exception": exception is not None,
            }
        )
    return rows, sorted(dict.fromkeys(blockers))


def check_dependency_licenses(
    repo_root: Path = ROOT,
    policy_path: Path = DEFAULT_POLICY,
) -> dict[str, object]:
    repo_root = repo_root.resolve()
    workspace = repo_root / "native" / "Cargo.toml"
    if not workspace.exists():
        return _report(rows=[], blockers=[], workspace_present=False)

    resolved_policy = policy_path if policy_path.is_absolute() else repo_root / policy_path
    if not resolved_policy.is_file():
        return _report(
            rows=[],
            blockers=["native_dependency_policy_missing:native/dependency-policy.json"],
            workspace_present=True,
        )
    try:
        policy = _load_policy(resolved_policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _report(
            rows=[],
            blockers=[f"native_dependency_policy_invalid:{exc}"],
            workspace_present=True,
        )

    completed = subprocess.run(
        [
            "cargo",
            "metadata",
            "--manifest-path",
            str(workspace),
            "--format-version",
            "1",
            "--locked",
        ],
        cwd=repo_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        summary = detail[-1] if detail else f"exit_{completed.returncode}"
        return _report(
            rows=[],
            blockers=[f"cargo_metadata_failed:{summary}"],
            workspace_present=True,
        )
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _report(
            rows=[],
            blockers=[f"cargo_metadata_invalid_json:{exc}"],
            workspace_present=True,
        )
    rows, blockers = evaluate_metadata(metadata, policy)
    return _report(rows=rows, blockers=blockers, workspace_present=True)


def _report(
    *,
    rows: list[dict[str, object]],
    blockers: list[str],
    workspace_present: bool,
) -> dict[str, object]:
    return {
        "schema_version": "native-dependency-license-report.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "workspace_present": workspace_present,
        "package_count": len(rows),
        "packages": rows,
        "blockers": blockers,
        "claim_boundary": (
            "This report checks the locked Cargo graph against repository source and "
            "SPDX allowlists. It is not legal advice and does not replace dependency "
            "vulnerability scanning."
        ),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = check_dependency_licenses(args.repo_root, args.policy)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"Native dependency licenses: {payload['status']}")
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
