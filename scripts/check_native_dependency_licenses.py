#!/usr/bin/env python3
"""Check locked Rust dependency sources and SPDX license policy for native code."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = Path("native/dependency-policy.json")
SPDX_OPERATORS = frozenset({"AND", "OR", "WITH"})
SPDX_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*")
SPDX_EXPRESSION_TOKEN_RE = re.compile(
    r"\(|\)|/|[A-Za-z0-9][A-Za-z0-9.+-]*"
)
RUST_VERSION_RE = re.compile(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:[-+].*)?$")
ALLOWED_REGISTRY_SOURCES = frozenset(
    {
        "registry+https://github.com/rust-lang/crates.io-index",
        "sparse+https://index.crates.io/",
    }
)
FIRST_PARTY_POLICY = {
    "repository_license_path": "LICENSE",
    "workspace_license_file": "../LICENSE",
    "posture": "all_rights_reserved_no_license_granted",
    "license_ref": "LicenseRef-Repository-Default-No-License",
    "required_notice_fragments": [
        "No permission is granted",
        "except under a separate written agreement",
        "not evidence of product-license approval",
    ],
    "product_license_approval": False,
    "commercial_redistribution_approved": False,
    "third_party_redistribution_clearance": "not_established",
    "release_blockers": [
        "product_license_approval_not_established",
        "commercial_redistribution_approval_not_established",
        "third_party_redistribution_clearance_not_established",
    ],
}


def _load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("native dependency policy must be a JSON object")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"sha256:{digest}"


def _load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return "<outside-repository>"


def _license_ids(expression: str) -> set[str]:
    return {
        token
        for token in SPDX_TOKEN_RE.findall(expression)
        if token.upper() not in SPDX_OPERATORS
    }


def _license_expression_allowed(expression: str, allowed_ids: set[str]) -> bool:
    """Evaluate the bounded SPDX AND/OR/WITH grammar against an allowlist."""

    tokens = SPDX_EXPRESSION_TOKEN_RE.findall(expression)
    remainder = SPDX_EXPRESSION_TOKEN_RE.sub("", expression)
    if not tokens or remainder.strip():
        return False
    position = 0

    def parse_primary() -> bool:
        nonlocal position
        if position >= len(tokens):
            raise ValueError("unexpected end of SPDX expression")
        token = tokens[position]
        if token == "(":
            position += 1
            value = parse_or()
            if position >= len(tokens) or tokens[position] != ")":
                raise ValueError("unbalanced SPDX expression")
            position += 1
            return value
        if token in {"AND", "OR", "WITH", ")", "/"}:
            raise ValueError("unexpected SPDX operator")
        position += 1
        return token in allowed_ids

    def parse_with() -> bool:
        nonlocal position
        value = parse_primary()
        while position < len(tokens) and tokens[position] == "WITH":
            position += 1
            value = parse_primary() and value
        return value

    def parse_and() -> bool:
        nonlocal position
        value = parse_with()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            value = parse_with() and value
        return value

    def parse_or() -> bool:
        nonlocal position
        value = parse_and()
        while position < len(tokens) and tokens[position] in {"OR", "/"}:
            position += 1
            value = parse_and() or value
        return value

    try:
        result = parse_or()
    except ValueError:
        return False
    return result and position == len(tokens)


def _rust_version_key(value: str) -> tuple[int, int, int] | None:
    match = RUST_VERSION_RE.fullmatch(value.strip())
    if match is None:
        return None
    return tuple(int(part or 0) for part in match.groups())


def _validate_policy(policy: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if policy.get("schema_version") != "native-dependency-policy.v2":
        blockers.append("native_dependency_policy_schema_version_invalid")
    maximum = str(policy.get("maximum_rust_version", "")).strip()
    if not maximum:
        blockers.append("native_dependency_policy_maximum_rust_version_missing")
    elif _rust_version_key(maximum) is None:
        blockers.append(
            f"native_dependency_policy_maximum_rust_version_invalid:{maximum}"
        )
    allowed = policy.get("allowed_license_ids")
    if not isinstance(allowed, list) or not allowed:
        blockers.append("native_dependency_policy_license_allowlist_invalid")
    if not isinstance(policy.get("exceptions"), list):
        blockers.append("native_dependency_policy_exceptions_invalid")
    if policy.get("first_party_license") != FIRST_PARTY_POLICY:
        blockers.append("native_first_party_license_policy_invalid")
    return blockers


def _unavailable_first_party_license(
    *, status: str, contract_pass: bool
) -> dict[str, object]:
    return {
        "status": status,
        "contract_pass": contract_pass,
        "posture": FIRST_PARTY_POLICY["posture"],
        "license_ref": FIRST_PARTY_POLICY["license_ref"],
        "repository_license": {
            "path": FIRST_PARTY_POLICY["repository_license_path"],
            "sha256": None,
        },
        "workspace_manifest": "native/Cargo.toml",
        "workspace_license_file": FIRST_PARTY_POLICY["workspace_license_file"],
        "workspace_package_count": 0,
        "workspace_packages": [],
    }


def evaluate_first_party_license(
    metadata: dict[str, Any],
    policy: dict[str, Any],
    *,
    repo_root: Path,
    workspace: Path,
) -> tuple[dict[str, object], list[str]]:
    """Verify that every workspace package inherits the repository no-grant file."""

    configured = policy.get("first_party_license")
    if not isinstance(configured, dict):
        return (
            _unavailable_first_party_license(
                status="blocked",
                contract_pass=False,
            ),
            ["native_first_party_license_policy_invalid"],
        )

    blockers: list[str] = []
    repository_license = repo_root / str(configured["repository_license_path"])
    license_text = ""
    license_sha256: str | None = None
    if repository_license.is_symlink() or not repository_license.is_file():
        blockers.append("repository_license_missing_or_not_regular")
    else:
        license_text = repository_license.read_text(encoding="utf-8")
        normalized_license_text = " ".join(license_text.split())
        license_sha256 = _sha256(repository_license)
        for fragment in configured["required_notice_fragments"]:
            if " ".join(str(fragment).split()) not in normalized_license_text:
                blockers.append(f"repository_license_notice_missing:{fragment}")

    workspace_payload = _load_toml(workspace)
    workspace_table = workspace_payload.get("workspace")
    workspace_package = (
        workspace_table.get("package") if isinstance(workspace_table, dict) else None
    )
    if not isinstance(workspace_package, dict):
        workspace_package = {}
    if workspace_package.get("license") is not None:
        blockers.append("workspace_spdx_license_expression_forbidden")
    if workspace_package.get("license-file") != configured[
        "workspace_license_file"
    ]:
        blockers.append("workspace_license_file_not_repository_authority")

    packages_by_id = {
        str(row.get("id", "")): row
        for row in metadata.get("packages", [])
        if isinstance(row, dict)
    }
    workspace_rows: list[dict[str, object]] = []
    for package_id in metadata.get("workspace_members", []):
        package = packages_by_id.get(str(package_id))
        if package is None:
            blockers.append(f"workspace_package_metadata_missing:{package_id}")
            continue
        name = str(package.get("name", ""))
        version = str(package.get("version", ""))
        package_name = f"{name}@{version}"
        manifest_value = str(package.get("manifest_path") or "")
        manifest = Path(manifest_value) if manifest_value else Path()
        manifest_section: dict[str, Any] = {}
        if not manifest_value or manifest.is_symlink() or not manifest.is_file():
            blockers.append(f"workspace_package_manifest_invalid:{package_name}")
        else:
            manifest_payload = _load_toml(manifest)
            candidate_section = manifest_payload.get("package")
            if isinstance(candidate_section, dict):
                manifest_section = candidate_section
        inherits_license_file = (
            manifest_section.get("license-file") == {"workspace": True}
        )
        if not inherits_license_file:
            blockers.append(
                f"workspace_package_license_file_not_inherited:{package_name}"
            )
        if manifest_section.get("license") is not None:
            blockers.append(
                f"workspace_package_spdx_license_expression_forbidden:{package_name}"
            )

        license_expression = str(package.get("license") or "").strip()
        if license_expression:
            blockers.append(
                "workspace_package_effective_spdx_license_forbidden:"
                f"{package_name}:{license_expression}"
            )
        license_file_value = str(package.get("license_file") or "")
        license_file = Path(license_file_value) if license_file_value else None
        if (
            license_file is not None
            and not license_file.is_absolute()
            and manifest_value
        ):
            license_file = manifest.parent / license_file
        license_file_matches = bool(
            license_file is not None
            and license_file.resolve() == repository_license.resolve()
        )
        if not license_file_matches:
            blockers.append(
                f"workspace_package_license_file_mismatch:{package_name}"
            )
        workspace_rows.append(
            {
                "package": package_name,
                "manifest_path": (
                    _relative_path(manifest, repo_root) if manifest_value else None
                ),
                "license_expression": license_expression or None,
                "license_file": (
                    _relative_path(license_file, repo_root)
                    if license_file is not None
                    else None
                ),
                "inherits_workspace_license_file": inherits_license_file,
                "license_file_matches_repository": license_file_matches,
            }
        )

    workspace_rows.sort(key=lambda row: str(row["package"]))
    blockers = sorted(dict.fromkeys(blockers))
    contract_pass = not blockers
    return (
        {
            "status": "pass" if contract_pass else "blocked",
            "contract_pass": contract_pass,
            "posture": configured["posture"],
            "license_ref": configured["license_ref"],
            "repository_license": {
                "path": configured["repository_license_path"],
                "sha256": license_sha256,
            },
            "workspace_manifest": _relative_path(workspace, repo_root),
            "workspace_license_file": configured["workspace_license_file"],
            "workspace_package_count": len(workspace_rows),
            "workspace_packages": workspace_rows,
        },
        blockers,
    )


def evaluate_metadata(
    metadata: dict[str, Any],
    policy: dict[str, Any],
) -> tuple[list[dict[str, object]], list[str]]:
    allowed_licenses = {
        str(value) for value in policy.get("allowed_license_ids", []) if str(value)
    }
    maximum_rust_version = str(policy.get("maximum_rust_version", "")).strip()
    maximum_rust_key = _rust_version_key(maximum_rust_version)
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
        rust_version = str(package.get("rust_version") or "").strip()
        rust_version_key = _rust_version_key(rust_version) if rust_version else None
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
            or _license_expression_allowed(license_expression, allowed_licenses)
            or bool(exception and exception.get("allow_license") is True)
        )
        msrv_allowed = (
            not external
            or maximum_rust_key is None
            or rust_version_key is None
            or rust_version_key <= maximum_rust_key
            or bool(exception and exception.get("allow_msrv") is True)
        )
        if external and not license_expression:
            blockers.append(f"dependency_license_missing:{package_id}")
        elif external and not license_allowed:
            blockers.append(
                f"dependency_license_not_allowed:{package_id}:{license_expression}"
            )
        if external and not source_allowed:
            blockers.append(f"dependency_source_not_allowed:{package_id}:{source}")
        if external and not msrv_allowed:
            blockers.append(
                "dependency_msrv_exceeds_workspace:"
                f"{package_id}:{rust_version}>{maximum_rust_version}"
            )
        rows.append(
            {
                "package": package_id,
                "external": external,
                "source": source,
                "source_allowed": source_allowed,
                "license": license_expression,
                "license_ids": license_ids,
                "license_allowed": license_allowed,
                "rust_version": rust_version or None,
                "msrv_allowed": msrv_allowed,
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
        return _report(
            rows=[],
            blockers=[],
            workspace_present=False,
            first_party_license=_unavailable_first_party_license(
                status="not_applicable",
                contract_pass=True,
            ),
        )

    resolved_policy = policy_path if policy_path.is_absolute() else repo_root / policy_path
    if not resolved_policy.is_file():
        return _report(
            rows=[],
            blockers=["native_dependency_policy_missing:native/dependency-policy.json"],
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    try:
        policy = _load_policy(resolved_policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return _report(
            rows=[],
            blockers=[f"native_dependency_policy_invalid:{exc}"],
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    policy_blockers = _validate_policy(policy)
    if policy_blockers:
        return _report(
            rows=[],
            blockers=policy_blockers,
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
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
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return _report(
            rows=[],
            blockers=[f"cargo_metadata_invalid_json:{exc}"],
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    rows, blockers = evaluate_metadata(metadata, policy)
    first_party_license, first_party_blockers = evaluate_first_party_license(
        metadata,
        policy,
        repo_root=repo_root,
        workspace=workspace,
    )
    return _report(
        rows=rows,
        blockers=[*blockers, *first_party_blockers],
        workspace_present=True,
        first_party_license=first_party_license,
    )


def _report(
    *,
    rows: list[dict[str, object]],
    blockers: list[str],
    workspace_present: bool,
    first_party_license: dict[str, object],
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-dependency-license-sbom.v2",
        "sbom_profile": "locked_cargo_metadata_plus_repository_license.v1",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "workspace_present": workspace_present,
        "package_count": len(rows),
        "external_dependency_count": sum(bool(row["external"]) for row in rows),
        "first_party_license": first_party_license,
        "packages": rows,
        "blockers": blockers,
        "release_clearance": {
            "status": "blocked",
            "product_license_approval": False,
            "commercial_redistribution_approved": False,
            "third_party_redistribution_clearance": "not_established",
            "blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
        },
        "claim_boundary": (
            "This SBOM checks first-party Cargo package metadata against the repository "
            "no-grant license file and checks locked third-party dependency declarations "
            "against source and SPDX allowlists. A technical pass grants no use or "
            "redistribution permission, is not legal advice, and does not establish "
            "third-party clearance, product-license approval, vulnerability clearance, "
            "commercial authority, or release readiness."
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
