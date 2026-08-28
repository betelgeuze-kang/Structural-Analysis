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
CARGO_LOCK_PATH = Path("native/Cargo.lock")
PACKAGED_CARGO_LOCK_PATH = "native/Cargo.lock"
PACKAGED_POLICY_PATH = "native/dependency-policy.json"
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
APPROVED_LICENSE_IDS = (
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MIT",
    "Unicode-3.0",
    "Zlib",
)
APPROVED_EXCEPTIONS: tuple[dict[str, object], ...] = ()
APPROVED_LICENSE_EXCEPTION_IDS: frozenset[str] = frozenset()
PINNED_CARGO_LOCK_SHA256 = (
    "sha256:55f07cfee535965e777f16ec6958ae3af92d49a6164d03c249e21b05d1ab127c"
)
PINNED_DEPENDENCY_POLICY_SHA256 = (
    "sha256:8c10f666d01806acc1dec86fbdf8d7e252b4419dd1aba73e349e693dadd4671d"
)
# Technical input baseline only. Matching this digest does not approve the terms,
# grant rights, or change the fail-closed release-clearance fields below.
PINNED_REPOSITORY_LICENSE_SHA256 = (
    "sha256:2cb0e9dff0aa63dee5f398a0dd7f3471d67a94178c935b5fb6b94a6ac5fd7778"
)
PINNED_PACKAGE_COUNT = 115
PINNED_EXTERNAL_DEPENDENCY_COUNT = 109
PINNED_FIRST_PARTY_PACKAGES = (
    "structural-cli@0.1.0",
    "structural-contracts@0.1.0",
    "structural-ffi-sys@0.1.0",
    "structural-ffi@0.1.0",
    "structural-report@0.1.0",
    "structural-runtime@0.1.0",
)
SBOM_CLAIM_BOUNDARY = (
    "This SBOM checks first-party Cargo package metadata against the repository "
    "no-grant license file and binds the exact repository license plus the complete "
    "locked Cargo package graph to code-pinned technical baselines. Declared "
    "licenses and MSRVs are checked against the packaged dependency policy; "
    "authenticating upstream license metadata still requires the checksum-addressed "
    "upstream crate source. A technical pass grants no use or redistribution "
    "permission, is not legal advice, and does not establish third-party clearance, "
    "product-license approval, vulnerability clearance, commercial authority, or "
    "release readiness."
)


def _load_policy(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("native dependency policy must be a JSON object")
    return payload


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


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
        if position < len(tokens) and tokens[position] == "WITH":
            position += 1
            if position >= len(tokens):
                raise ValueError("missing SPDX exception")
            exception = tokens[position]
            if exception in {"AND", "OR", "WITH", "(", ")", "/"}:
                raise ValueError("invalid SPDX exception")
            position += 1
            value = value and exception in APPROVED_LICENSE_EXCEPTION_IDS
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
    if allowed != list(APPROVED_LICENSE_IDS):
        blockers.append("native_dependency_policy_license_allowlist_invalid")
    if policy.get("exceptions") != list(APPROVED_EXCEPTIONS):
        blockers.append("native_dependency_policy_exceptions_invalid")
    if policy.get("first_party_license") != FIRST_PARTY_POLICY:
        blockers.append("native_first_party_license_policy_invalid")
    return blockers


def _load_lock_bytes(value: bytes) -> dict[str, Any]:
    try:
        decoded = value.decode("utf-8")
        payload = tomllib.loads(decoded)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Cargo.lock invalid: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Cargo.lock must be a TOML table")
    return payload


def _locked_package_rows(
    payload: dict[str, Any],
) -> tuple[list[dict[str, object]], list[str]]:
    """Return a canonical package graph reconstructed only from Cargo.lock."""

    blockers: list[str] = []
    if payload.get("version") != 3 or set(payload) != {"version", "package"}:
        blockers.append("cargo_lock_contract_invalid")
    packages = payload.get("package")
    if not isinstance(packages, list) or not packages:
        return [], [*blockers, "cargo_lock_packages_invalid"]
    rows: list[dict[str, object]] = []
    identities: set[str] = set()
    allowed_fields = {"name", "version", "source", "checksum", "dependencies"}
    for item in packages:
        if not isinstance(item, dict) or not set(item).issubset(allowed_fields):
            blockers.append("cargo_lock_package_row_invalid")
            continue
        name = item.get("name")
        version = item.get("version")
        source = item.get("source")
        checksum = item.get("checksum")
        dependencies = item.get("dependencies", [])
        if (
            not isinstance(name, str)
            or not name
            or "@" in name
            or not isinstance(version, str)
            or not version
            or (source is not None and not isinstance(source, str))
            or (checksum is not None and not isinstance(checksum, str))
            or not isinstance(dependencies, list)
            or any(not isinstance(value, str) or not value for value in dependencies)
            or len(dependencies) != len(set(dependencies))
        ):
            blockers.append("cargo_lock_package_row_invalid")
            continue
        package = f"{name}@{version}"
        if package in identities:
            blockers.append(f"cargo_lock_package_identity_ambiguous:{package}")
            continue
        identities.add(package)
        external = source is not None
        if external and re.fullmatch(r"[0-9a-f]{64}", str(checksum or "")) is None:
            blockers.append(f"cargo_lock_external_checksum_invalid:{package}")
        if not external and checksum is not None:
            blockers.append(f"cargo_lock_path_checksum_forbidden:{package}")
        rows.append(
            {
                "package": package,
                "external": external,
                "source": source,
                "checksum": checksum,
                "dependencies": sorted(dependencies),
            }
        )

    rows.sort(key=lambda row: str(row["package"]))
    rows_by_name: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        name = str(row["package"]).rsplit("@", 1)[0]
        rows_by_name.setdefault(name, []).append(row)
    for row in rows:
        for dependency in row["dependencies"]:
            parts = str(dependency).split()
            candidates = rows_by_name.get(parts[0], [])
            if len(parts) >= 2:
                candidates = [
                    candidate
                    for candidate in candidates
                    if str(candidate["package"]).rsplit("@", 1)[1] == parts[1]
                ]
            if len(parts) >= 3:
                expected_source = " ".join(parts[2:])
                if expected_source.startswith("(") and expected_source.endswith(")"):
                    expected_source = expected_source[1:-1]
                candidates = [
                    candidate
                    for candidate in candidates
                    if candidate["source"] == expected_source
                ]
            if len(candidates) != 1:
                blockers.append(
                    f"cargo_lock_dependency_unresolved:{row['package']}:{dependency}"
                )
    return rows, sorted(dict.fromkeys(blockers))


def _bind_rows_to_lock(
    rows: list[dict[str, object]],
    locked_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[str]]:
    blockers: list[str] = []
    metadata_by_package: dict[str, dict[str, object]] = {}
    for row in rows:
        package = str(row.get("package", ""))
        if package in metadata_by_package:
            blockers.append(f"cargo_metadata_package_identity_ambiguous:{package}")
        metadata_by_package[package] = row
    lock_by_package = {str(row["package"]): row for row in locked_rows}
    missing = sorted(set(lock_by_package) - set(metadata_by_package))
    extra = sorted(set(metadata_by_package) - set(lock_by_package))
    blockers.extend(f"cargo_metadata_package_missing:{value}" for value in missing)
    blockers.extend(f"cargo_metadata_package_not_locked:{value}" for value in extra)
    enriched: list[dict[str, object]] = []
    for package, row in sorted(metadata_by_package.items()):
        locked = lock_by_package.get(package)
        result = dict(row)
        result["checksum"] = locked.get("checksum") if locked else None
        result["dependencies"] = locked.get("dependencies", []) if locked else []
        if locked is not None and (
            row.get("external") != locked.get("external")
            or row.get("source") != locked.get("source")
        ):
            blockers.append(f"cargo_metadata_lock_source_mismatch:{package}")
        enriched.append(result)
    return enriched, sorted(dict.fromkeys(blockers))


def _input_bindings(
    lock_bytes: bytes,
    policy_bytes: bytes,
    locked_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "cargo_lock": {
            "path": PACKAGED_CARGO_LOCK_PATH,
            "sha256": _sha256_bytes(lock_bytes),
            "format_version": 3,
            "package_count": len(locked_rows),
        },
        "dependency_policy": {
            "path": PACKAGED_POLICY_PATH,
            "sha256": _sha256_bytes(policy_bytes),
            "schema_version": "native-dependency-policy.v2",
        },
    }


def _validate_pinned_dependency_inputs(
    *,
    lock_bytes: bytes,
    policy_bytes: bytes,
    locked_rows: list[dict[str, object]],
) -> list[str]:
    """Bind packaged dependency inputs to the reviewed trusted-verifier baseline."""

    blockers: list[str] = []
    if _sha256_bytes(lock_bytes) != PINNED_CARGO_LOCK_SHA256:
        blockers.append("cargo_lock_not_pinned_trusted_baseline")
    if _sha256_bytes(policy_bytes) != PINNED_DEPENDENCY_POLICY_SHA256:
        blockers.append("native_dependency_policy_not_pinned_trusted_baseline")
    external_count = sum(bool(row.get("external")) for row in locked_rows)
    first_party_packages = tuple(
        sorted(
            str(row.get("package"))
            for row in locked_rows
            if row.get("external") is False
        )
    )
    if len(locked_rows) != PINNED_PACKAGE_COUNT:
        blockers.append(
            "cargo_lock_pinned_package_count_mismatch:"
            f"{len(locked_rows)}!={PINNED_PACKAGE_COUNT}"
        )
    if external_count != PINNED_EXTERNAL_DEPENDENCY_COUNT:
        blockers.append(
            "cargo_lock_pinned_external_count_mismatch:"
            f"{external_count}!={PINNED_EXTERNAL_DEPENDENCY_COUNT}"
        )
    if first_party_packages != tuple(sorted(PINNED_FIRST_PARTY_PACKAGES)):
        blockers.append("cargo_lock_pinned_first_party_inventory_mismatch")
    return sorted(dict.fromkeys(blockers))


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
    """Verify the exact repository notice and every source-null Cargo package."""

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
    license_sha256: str | None = None
    if repository_license.is_symlink() or not repository_license.is_file():
        blockers.append("repository_license_missing_or_not_regular")
    else:
        try:
            license_bytes = repository_license.read_bytes()
        except OSError:
            blockers.append("repository_license_unreadable")
        else:
            license_sha256 = _sha256_bytes(license_bytes)
            if license_sha256 != PINNED_REPOSITORY_LICENSE_SHA256:
                blockers.append("repository_license_not_pinned_trusted_baseline")
            try:
                normalized_license_text = " ".join(
                    license_bytes.decode("utf-8").split()
                )
            except UnicodeDecodeError:
                blockers.append("repository_license_not_utf8")
            else:
                for fragment in configured["required_notice_fragments"]:
                    if (
                        " ".join(str(fragment).split())
                        not in normalized_license_text
                    ):
                        blockers.append(
                            f"repository_license_notice_missing:{fragment}"
                        )

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
    workspace_member_ids = {
        str(package_id) for package_id in metadata.get("workspace_members", [])
    }
    for package in packages_by_id.values():
        if package.get("source") is not None:
            continue
        package_id = str(package.get("id", ""))
        package_name = (
            f"{str(package.get('name', ''))}@{str(package.get('version', ''))}"
        )
        if not package_id:
            blockers.append(f"source_null_package_id_missing:{package_name}")
        elif package_id not in workspace_member_ids:
            blockers.append(
                f"non_workspace_path_dependency_forbidden:{package_name}"
            )
    workspace_rows: list[dict[str, object]] = []
    for package_id in sorted(workspace_member_ids):
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
        policy_bytes = resolved_policy.read_bytes()
        policy = _strict_json_object_bytes(policy_bytes, "native dependency policy")
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

    lock_path = repo_root / CARGO_LOCK_PATH
    if lock_path.is_symlink() or not lock_path.is_file():
        return _report(
            rows=[],
            blockers=["cargo_lock_missing_or_not_regular:native/Cargo.lock"],
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    try:
        lock_bytes = lock_path.read_bytes()
        lock_payload = _load_lock_bytes(lock_bytes)
        locked_rows, lock_blockers = _locked_package_rows(lock_payload)
        lock_blockers.extend(
            _validate_pinned_dependency_inputs(
                lock_bytes=lock_bytes,
                policy_bytes=policy_bytes,
                locked_rows=locked_rows,
            )
        )
    except (OSError, ValueError) as exc:
        return _report(
            rows=[],
            blockers=[f"cargo_lock_invalid:{exc}"],
            workspace_present=True,
            first_party_license=_unavailable_first_party_license(
                status="blocked", contract_pass=False
            ),
        )
    if lock_blockers:
        return _report(
            rows=[],
            blockers=lock_blockers,
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
    rows, lock_binding_blockers = _bind_rows_to_lock(rows, locked_rows)
    first_party_license, first_party_blockers = evaluate_first_party_license(
        metadata,
        policy,
        repo_root=repo_root,
        workspace=workspace,
    )
    return _report(
        rows=rows,
        blockers=[*blockers, *lock_binding_blockers, *first_party_blockers],
        workspace_present=True,
        first_party_license=first_party_license,
        inputs=_input_bindings(
            lock_bytes,
            policy_bytes,
            locked_rows,
        ),
    )


def _report(
    *,
    rows: list[dict[str, object]],
    blockers: list[str],
    workspace_present: bool,
    first_party_license: dict[str, object],
    inputs: dict[str, object] | None = None,
) -> dict[str, object]:
    blockers = sorted(dict.fromkeys(blockers))
    return {
        "schema_version": "native-dependency-license-sbom.v2",
        "sbom_profile": "locked_cargo_graph_plus_repository_license.v2",
        "status": "pass" if not blockers else "blocked",
        "contract_pass": not blockers,
        "workspace_present": workspace_present,
        "package_count": len(rows),
        "external_dependency_count": sum(bool(row["external"]) for row in rows),
        "inputs": inputs,
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
        "claim_boundary": SBOM_CLAIM_BOUNDARY,
    }


def _strict_json_object_bytes(value: bytes, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"{label} duplicate key: {key}")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"{label} nonfinite value: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def validate_packaged_sbom(
    payload: dict[str, Any],
    *,
    license_bytes: bytes,
    cargo_lock_bytes: bytes,
    policy_bytes: bytes,
) -> list[str]:
    """Validate an extracted SBOM solely against hash-bound package inputs.

    This validates completeness, graph/source/checksum identity, reported license/MSRV
    policy outcomes, and the non-promoting first-party boundary. Cargo.lock does not
    carry upstream license metadata, so the checksum-addressed crate remains the
    upstream authority for the license string reported by cargo metadata.
    """

    blockers: list[str] = []
    try:
        policy = _strict_json_object_bytes(policy_bytes, "dependency policy")
        blockers.extend(_validate_policy(policy))
        lock_payload = _load_lock_bytes(cargo_lock_bytes)
        locked_rows, lock_blockers = _locked_package_rows(lock_payload)
        blockers.extend(lock_blockers)
        blockers.extend(
            _validate_pinned_dependency_inputs(
                lock_bytes=cargo_lock_bytes,
                policy_bytes=policy_bytes,
                locked_rows=locked_rows,
            )
        )
    except (KeyError, TypeError, ValueError) as exc:
        return [f"packaged_sbom_input_invalid:{exc}"]

    expected_fields = {
        "schema_version",
        "sbom_profile",
        "status",
        "contract_pass",
        "workspace_present",
        "package_count",
        "external_dependency_count",
        "inputs",
        "first_party_license",
        "packages",
        "blockers",
        "release_clearance",
        "claim_boundary",
    }
    if set(payload) != expected_fields:
        blockers.append("packaged_sbom_fields_invalid")
    if (
        payload.get("schema_version") != "native-dependency-license-sbom.v2"
        or payload.get("sbom_profile")
        != "locked_cargo_graph_plus_repository_license.v2"
        or payload.get("status") != "pass"
        or payload.get("contract_pass") is not True
        or payload.get("workspace_present") is not True
        or payload.get("blockers") != []
        or payload.get("claim_boundary") != SBOM_CLAIM_BOUNDARY
    ):
        blockers.append("packaged_sbom_contract_invalid")

    if payload.get("inputs") != _input_bindings(
        cargo_lock_bytes, policy_bytes, locked_rows
    ):
        blockers.append("packaged_sbom_input_binding_invalid")

    packages = payload.get("packages")
    expected_packages: list[dict[str, object]] = []
    package_blockers: list[str] = []
    if not isinstance(packages, list):
        blockers.append("packaged_sbom_packages_invalid")
        packages = []
    else:
        package_fields = {
            "package",
            "external",
            "source",
            "source_allowed",
            "license",
            "license_ids",
            "license_allowed",
            "rust_version",
            "msrv_allowed",
            "exception",
            "checksum",
            "dependencies",
        }
        metadata_packages: list[dict[str, object]] = []
        for row in packages:
            if not isinstance(row, dict) or set(row) != package_fields:
                package_blockers.append("packaged_sbom_package_row_invalid")
                continue
            identity = row.get("package")
            if not isinstance(identity, str) or identity.count("@") != 1:
                package_blockers.append("packaged_sbom_package_identity_invalid")
                continue
            name, version = identity.rsplit("@", 1)
            metadata_packages.append(
                {
                    "name": name,
                    "version": version,
                    "source": row.get("source"),
                    "license": row.get("license"),
                    "rust_version": row.get("rust_version"),
                }
            )
        evaluated_rows, evaluation_blockers = evaluate_metadata(
            {"packages": metadata_packages}, policy
        )
        expected_packages, binding_blockers = _bind_rows_to_lock(
            evaluated_rows, locked_rows
        )
        package_blockers.extend(evaluation_blockers)
        package_blockers.extend(binding_blockers)
        if packages != expected_packages:
            package_blockers.append("packaged_sbom_package_inventory_mismatch")
    blockers.extend(package_blockers)

    if (
        payload.get("package_count") != len(locked_rows)
        or payload.get("package_count") != len(packages)
        or payload.get("external_dependency_count")
        != sum(bool(row.get("external")) for row in expected_packages)
    ):
        blockers.append("packaged_sbom_package_counts_invalid")

    try:
        normalized_license = " ".join(license_bytes.decode("utf-8").split())
    except UnicodeDecodeError:
        normalized_license = ""
        blockers.append("packaged_repository_license_not_utf8")
    if any(
        " ".join(str(fragment).split()) not in normalized_license
        for fragment in FIRST_PARTY_POLICY["required_notice_fragments"]
    ):
        blockers.append("packaged_repository_license_notice_missing")
    if _sha256_bytes(license_bytes) != PINNED_REPOSITORY_LICENSE_SHA256:
        blockers.append("packaged_repository_license_not_pinned_trusted_baseline")

    first_party = payload.get("first_party_license")
    expected_first_party_names = sorted(
        str(row["package"])
        for row in expected_packages
        if row.get("external") is False
    )
    if not isinstance(first_party, dict):
        blockers.append("packaged_first_party_license_invalid")
    else:
        workspace_packages = first_party.get("workspace_packages")
        expected_workspace_rows = [
            {
                "package": package,
                "manifest_path": (
                    f"native/crates/{package.rsplit('@', 1)[0]}/Cargo.toml"
                ),
                "license_expression": None,
                "license_file": "LICENSE",
                "inherits_workspace_license_file": True,
                "license_file_matches_repository": True,
            }
            for package in expected_first_party_names
        ]
        expected_first_party = {
            "status": "pass",
            "contract_pass": True,
            "posture": FIRST_PARTY_POLICY["posture"],
            "license_ref": FIRST_PARTY_POLICY["license_ref"],
            "repository_license": {
                "path": "LICENSE",
                "sha256": _sha256_bytes(license_bytes),
            },
            "workspace_manifest": "native/Cargo.toml",
            "workspace_license_file": "../LICENSE",
            "workspace_package_count": len(expected_workspace_rows),
            "workspace_packages": expected_workspace_rows,
        }
        if first_party != expected_first_party or workspace_packages != expected_workspace_rows:
            blockers.append("packaged_first_party_license_contract_invalid")

    expected_release_clearance = {
        "status": "blocked",
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "blockers": list(FIRST_PARTY_POLICY["release_blockers"]),
    }
    if payload.get("release_clearance") != expected_release_clearance:
        blockers.append("packaged_release_clearance_invalid")
    return sorted(dict.fromkeys(blockers))


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
