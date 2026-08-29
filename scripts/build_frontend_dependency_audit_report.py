#!/usr/bin/env python3
"""Build and verify exact-source npm vulnerability audit evidence.

The report is a point-in-time npm registry audit of the dependency graph
described by ``package.json`` and ``package-lock.json``. It intentionally does
not grant license, SBOM, signing, release, or commercial authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any


SCHEMA_VERSION = "frontend-dependency-audit-report.v3"
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path(
    "implementation/phase1/release_evidence/productization/"
    "frontend_dependency_audit_report.json"
)
DEFAULT_PACKAGE_JSON = Path("package.json")
DEFAULT_PACKAGE_LOCK = Path("package-lock.json")
AUDIT_CAPTURE_FILES = {
    "source_before": "source-before.txt",
    "source_after": "source-after.txt",
    "node_version": "node-version.txt",
    "npm_version": "npm-version.txt",
    "effective_registry": "effective-registry.txt",
    "effective_strict_ssl": "effective-strict-ssl.txt",
    "effective_proxy": "effective-proxy.txt",
    "effective_https_proxy": "effective-https-proxy.txt",
    "effective_cafile": "effective-cafile.txt",
    "install_stdout": "npm-ci.stdout.txt",
    "install_stderr": "npm-ci.stderr.txt",
    "install_exit_code": "npm-ci.exit-code.txt",
    "audit_stdout": "npm-audit.stdout.json",
    "audit_exit_code": "npm-audit.exit-code.txt",
    "signatures_stdout": "npm-audit-signatures.stdout.json",
    "signatures_exit_code": "npm-audit-signatures.exit-code.txt",
    "trusted_node_path": "trusted-node-path.txt",
    "trusted_node_realpath": "trusted-node-realpath.txt",
    "trusted_node_sha256": "trusted-node-sha256.txt",
    "trusted_npm_cli_path": "trusted-npm-cli-path.txt",
    "trusted_npm_cli_realpath": "trusted-npm-cli-realpath.txt",
    "trusted_npm_cli_sha256": "trusted-npm-cli-sha256.txt",
    "trusted_git_path": "trusted-git-path.txt",
    "trusted_git_realpath": "trusted-git-realpath.txt",
    "trusted_git_sha256": "trusted-git-sha256.txt",
    "trusted_git_version": "trusted-git-version.txt",
    "node_archive_url": "node-archive-url.txt",
    "node_archive_sha256": "node-archive-sha256.txt",
    "node_shasums_url": "node-shasums-url.txt",
    "node_official_shasum_line": "node-official-shasum-line.txt",
}
VULNERABILITY_LEVELS = ("info", "low", "moderate", "high", "critical")
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
NPM_REGISTRY = "https://registry.npmjs.org/"
NPM_CONFIG_ARGS = (
    f"--registry={NPM_REGISTRY}",
    "--strict-ssl=true",
    "--include=prod",
    "--include=dev",
    "--include=optional",
    "--include=peer",
)
INSTALL_COMMAND = (
    "ci",
    "--ignore-scripts",
    "--engine-strict",
    *NPM_CONFIG_ARGS,
)
AUDIT_COMMAND = ("audit", "--json", "--audit-level=info", *NPM_CONFIG_ARGS)
SIGNATURE_COMMAND = ("audit", "signatures", "--json", *NPM_CONFIG_ARGS)
REQUIRED_AJV_VERSION = "8.20.0"
REQUIRED_NODE_VERSION = "v24.20.0"
REQUIRED_NPM_VERSION = "11.19.0"
NODE_DISTRIBUTION_NAME = "node-v24.20.0-linux-x64"
NODE_ARCHIVE_NAME = f"{NODE_DISTRIBUTION_NAME}.tar.xz"
NODE_ARCHIVE_URL = f"https://nodejs.org/dist/v24.20.0/{NODE_ARCHIVE_NAME}"
NODE_SHASUMS_URL = "https://nodejs.org/dist/v24.20.0/SHASUMS256.txt"
NODE_ARCHIVE_SHA256 = "2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2"
NODE_EXECUTABLE_SHA256 = (
    "89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7"
)
NPM_CLI_SHA256 = "8e5f6f3429f8cdbe693cdc29904e9d5a7b127a494bd15c804bd54c7403bfcbe7"
NODE_OFFICIAL_SHASUM_LINE = f"{NODE_ARCHIVE_SHA256}  {NODE_ARCHIVE_NAME}"
TRUSTED_GIT_PATH = Path("/usr/bin/git")
REQUIRED_PACKAGE_MANAGER = f"npm@{REQUIRED_NPM_VERSION}"
REQUIRED_FIRST_PARTY_LICENSE = "SEE LICENSE IN LICENSE"
REQUIRED_ENGINES = {
    "node": REQUIRED_NODE_VERSION.removeprefix("v"),
    "npm": REQUIRED_NPM_VERSION,
}
EXACT_SEMVER_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)
DIRECT_DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)
UNSUPPORTED_MANIFEST_FIELDS = {
    "bundleDependencies",
    "bundledDependencies",
    "overrides",
    "workspaces",
    "devEngines",
}
UNSUPPORTED_LOCK_ROW_FIELDS = {
    "bundleDependencies",
    "bundledDependencies",
    "inBundle",
    "link",
    "devEngines",
}
FORBIDDEN_PROJECT_SURFACES = (
    ".npmrc",
    ".pnpmfile.cjs",
    ".yarnrc",
    ".yarnrc.yml",
    "bun.lock",
    "bun.lockb",
    "bunfig.toml",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "yarn.lock",
)
FORBIDDEN_PROJECT_DIRECTORIES = (".yarn",)
SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
PROXY_ENVIRONMENT_NAMES = {"all_proxy", "http_proxy", "https_proxy"}
NPM_ENVIRONMENT_ALLOWLIST_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "NPM_CONFIG_CACHE",
    "NPM_CONFIG_GLOBALCONFIG",
    "NPM_CONFIG_USERCONFIG",
    "PATH",
    "TMPDIR",
)
CLAIM_BOUNDARY = {
    "allowed": [
        "point-in-time npm registry vulnerability audit",
        "exact source and package manifest byte binding",
        "zero reported vulnerabilities at audit execution time",
        "npm registry package-signature verification result at execution time",
    ],
    "not_granted": [
        "future vulnerability absence",
        "license or third-party redistribution clearance",
        "complete SBOM authority",
        "product signing or provenance authority",
        "release or commercial authority",
    ],
}


class FrontendDependencyAuditError(RuntimeError):
    """Raised when audit evidence cannot be built or verified exactly."""


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _dependency_surface_violations(package_json: Path) -> list[str]:
    project_root = package_json.resolve().parent
    violations: list[str] = []
    for name in FORBIDDEN_PROJECT_SURFACES:
        if _lexists(project_root / name):
            violations.append(f"forbidden_project_surface:{name}")
    for name in FORBIDDEN_PROJECT_DIRECTORIES:
        if _lexists(project_root / name):
            violations.append(f"forbidden_project_surface:{name}/")
    for ancestor in project_root.parents:
        candidate = ancestor / ".npmrc"
        if _lexists(candidate) and "forbidden_ancestor_npmrc" not in violations:
            violations.append("forbidden_ancestor_npmrc")
    ignored = {".git", "dist", "node_modules"}
    forbidden_names = set(FORBIDDEN_PROJECT_SURFACES) | set(
        FORBIDDEN_PROJECT_DIRECTORIES
    )
    for directory, names, files in os.walk(project_root, followlinks=False):
        names[:] = [name for name in names if name not in ignored]
        relative = Path(directory).relative_to(project_root)
        for name in [*names, *files]:
            if name in forbidden_names and relative != Path("."):
                violation = (
                    f"forbidden_descendant_surface:{(relative / name).as_posix()}"
                )
                if violation not in violations:
                    violations.append(violation)
    return violations


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _minimal_process_environment(*, home: Path, tmpdir: Path) -> dict[str, str]:
    """Return an env-i equivalent allowlist for trusted tool execution."""

    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(tmpdir),
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate_json_key:{key}")
        payload[key] = value
    return payload


def _load_json_text(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite:{token}")
            ),
        )
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _tool_sha(path: Path) -> str:
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        raise FrontendDependencyAuditError(f"trusted_tool_unsafe:{path}")
    if path.resolve() != path:
        raise FrontendDependencyAuditError(f"trusted_tool_realpath_mismatch:{path}")
    return _sha256_path(path)


def _git_environment() -> dict[str, str]:
    return {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
    }


def _git_text(*args: str, trusted_git: Path = TRUSTED_GIT_PATH) -> str:
    _tool_sha(trusted_git)
    try:
        return subprocess.check_output(
            [str(trusted_git), *args],
            cwd=REPO_ROOT,
            env=_git_environment(),
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError(
            f"git_identity_unavailable:{args[0]}"
        ) from exc


def git_identity(
    *,
    trusted_git: Path = TRUSTED_GIT_PATH,
    expected_git_sha256: str = "",
) -> dict[str, Any]:
    actual_git_sha256 = _tool_sha(trusted_git)
    if expected_git_sha256 and actual_git_sha256 != expected_git_sha256:
        raise FrontendDependencyAuditError("trusted_git_hash_mismatch")
    commit_sha = _git_text("rev-parse", "HEAD", trusted_git=trusted_git)
    tree_sha = _git_text("rev-parse", "HEAD^{tree}", trusted_git=trusted_git)
    if commit_sha == "0" * 40 or SHA_PATTERN.fullmatch(commit_sha) is None:
        raise FrontendDependencyAuditError("source_commit_sha_invalid")
    if tree_sha == "0" * 40 or SHA_PATTERN.fullmatch(tree_sha) is None:
        raise FrontendDependencyAuditError("source_tree_sha_invalid")
    try:
        status = subprocess.run(
            [
                str(trusted_git),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            cwd=REPO_ROOT,
            env=_git_environment(),
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError("source_status_unavailable") from exc
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "worktree_clean": not bool(status),
    }


def _default_tool_evidence() -> dict[str, Any]:
    """Synthetic canonical identities used only by pure report unit builders."""

    node = "/opt/trusted-node-v24.20.0/bin/node"
    npm_cli = "/opt/trusted-node-v24.20.0/lib/node_modules/npm/bin/npm-cli.js"
    return {
        "distribution": {
            "archive_url": NODE_ARCHIVE_URL,
            "archive_sha256": f"sha256:{NODE_ARCHIVE_SHA256}",
            "shasums_url": NODE_SHASUMS_URL,
            "official_shasum_line": NODE_OFFICIAL_SHASUM_LINE,
        },
        "node": {
            "path": node,
            "realpath": node,
            "sha256": f"sha256:{NODE_EXECUTABLE_SHA256}",
            "version": REQUIRED_NODE_VERSION,
        },
        "npm_cli": {
            "path": npm_cli,
            "realpath": npm_cli,
            "sha256": f"sha256:{NPM_CLI_SHA256}",
            "version": REQUIRED_NPM_VERSION,
        },
        "git": {
            "path": str(TRUSTED_GIT_PATH),
            "realpath": str(TRUSTED_GIT_PATH),
            "sha256": "sha256:" + "0" * 64,
            "version": "git version captured-by-builder",
        },
    }


def _validate_tool_evidence(
    tools: dict[str, Any], *, require_files: bool
) -> dict[str, Any]:
    if set(tools) != {"distribution", "node", "npm_cli", "git"}:
        raise FrontendDependencyAuditError("trusted_tool_evidence_fields_invalid")
    distribution = tools.get("distribution")
    expected_distribution = {
        "archive_url": NODE_ARCHIVE_URL,
        "archive_sha256": f"sha256:{NODE_ARCHIVE_SHA256}",
        "shasums_url": NODE_SHASUMS_URL,
        "official_shasum_line": NODE_OFFICIAL_SHASUM_LINE,
    }
    if distribution != expected_distribution:
        raise FrontendDependencyAuditError("trusted_node_distribution_invalid")
    for label, expected_sha, expected_version in (
        ("node", NODE_EXECUTABLE_SHA256, REQUIRED_NODE_VERSION),
        ("npm_cli", NPM_CLI_SHA256, REQUIRED_NPM_VERSION),
    ):
        row = tools.get(label)
        if not isinstance(row, dict) or set(row) != {
            "path",
            "realpath",
            "sha256",
            "version",
        }:
            raise FrontendDependencyAuditError(f"trusted_{label}_identity_invalid")
        path = row.get("path")
        realpath = row.get("realpath")
        if (
            not isinstance(path, str)
            or not Path(path).is_absolute()
            or not isinstance(realpath, str)
            or not Path(realpath).is_absolute()
            or path != realpath
            or row.get("sha256") != f"sha256:{expected_sha}"
            or row.get("version") != expected_version
        ):
            raise FrontendDependencyAuditError(f"trusted_{label}_identity_invalid")
        if require_files and _tool_sha(Path(path)) != row["sha256"]:
            raise FrontendDependencyAuditError(f"trusted_{label}_hash_mismatch")
    git = tools.get("git")
    if not isinstance(git, dict) or set(git) != {
        "path",
        "realpath",
        "sha256",
        "version",
    }:
        raise FrontendDependencyAuditError("trusted_git_identity_invalid")
    if (
        git.get("path") != str(TRUSTED_GIT_PATH)
        or git.get("realpath") != str(TRUSTED_GIT_PATH)
        or not isinstance(git.get("sha256"), str)
        or SHA256_PATTERN.fullmatch(str(git.get("sha256"))) is None
        or not isinstance(git.get("version"), str)
        or not str(git.get("version")).startswith("git version ")
    ):
        raise FrontendDependencyAuditError("trusted_git_identity_invalid")
    if require_files:
        if _tool_sha(TRUSTED_GIT_PATH) != git["sha256"]:
            raise FrontendDependencyAuditError("trusted_git_hash_mismatch")
        actual_version = subprocess.check_output(
            [str(TRUSTED_GIT_PATH), "--version"],
            env=_git_environment(),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if actual_version != git["version"]:
            raise FrontendDependencyAuditError("trusted_git_version_mismatch")
    return deepcopy(tools)


def trusted_tool_evidence(
    *, trusted_node: Path, trusted_npm_cli: Path, trusted_git: Path
) -> dict[str, Any]:
    if trusted_git != TRUSTED_GIT_PATH:
        raise FrontendDependencyAuditError("trusted_git_path_invalid")
    node_real = trusted_node.resolve(strict=True)
    npm_real = trusted_npm_cli.resolve(strict=True)
    git_real = trusted_git.resolve(strict=True)
    if (
        node_real != trusted_node
        or npm_real != trusted_npm_cli
        or git_real != trusted_git
    ):
        raise FrontendDependencyAuditError("trusted_tool_path_not_canonical_realpath")
    base = _default_tool_evidence()
    base["node"].update(
        {
            "path": str(node_real),
            "realpath": str(node_real),
            "sha256": _tool_sha(node_real),
        }
    )
    base["npm_cli"].update(
        {
            "path": str(npm_real),
            "realpath": str(npm_real),
            "sha256": _tool_sha(npm_real),
        }
    )
    git_version = subprocess.check_output(
        [str(git_real), "--version"],
        env=_git_environment(),
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()
    base["git"].update(
        {
            "path": str(git_real),
            "realpath": str(git_real),
            "sha256": _tool_sha(git_real),
            "version": git_version,
        }
    )
    return _validate_tool_evidence(base, require_files=True)


def _validate_identity(
    source_identity: dict[str, Any], expected_source_sha: str
) -> dict[str, Any]:
    commit_sha = source_identity.get("commit_sha")
    tree_sha = source_identity.get("tree_sha")
    expected = expected_source_sha or commit_sha
    if (
        not isinstance(commit_sha, str)
        or commit_sha == "0" * 40
        or SHA_PATTERN.fullmatch(commit_sha) is None
    ):
        raise FrontendDependencyAuditError("source_commit_sha_invalid")
    if (
        not isinstance(tree_sha, str)
        or tree_sha == "0" * 40
        or SHA_PATTERN.fullmatch(tree_sha) is None
    ):
        raise FrontendDependencyAuditError("source_tree_sha_invalid")
    if not isinstance(expected, str) or SHA_PATTERN.fullmatch(expected) is None:
        raise FrontendDependencyAuditError("expected_source_sha_invalid")
    return {
        "commit_sha": commit_sha,
        "tree_sha": tree_sha,
        "expected_commit_sha": expected,
        "worktree_clean": source_identity.get("worktree_clean") is True,
    }


def _file_binding(path: Path) -> dict[str, Any]:
    regular_file = path.is_file() and not path.is_symlink()
    return {
        "path": _display_path(path),
        "regular_file": regular_file,
        "bytes": path.stat().st_size if regular_file else None,
        "sha256": _sha256_path(path) if regular_file else None,
    }


def _json_object(path: Path) -> dict[str, Any]:
    try:
        payload = _load_json_text(path.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload


def _exact_direct_specs(rows: Any) -> bool:
    return bool(
        isinstance(rows, dict)
        and all(
            isinstance(name, str)
            and bool(name)
            and isinstance(spec, str)
            and EXACT_SEMVER_PATTERN.fullmatch(spec) is not None
            for name, spec in rows.items()
        )
    )


def _peer_meta_valid(peer_meta: Any, peer_dependencies: dict[str, Any]) -> bool:
    if not isinstance(peer_meta, dict):
        return False
    for name, metadata in peer_meta.items():
        if name not in peer_dependencies or not isinstance(metadata, dict):
            return False
        if set(metadata) != {"optional"} or not isinstance(
            metadata.get("optional"), bool
        ):
            return False
    return True


def _lock_graph_counts(lock: dict[str, Any]) -> dict[str, int] | None:
    packages = lock.get("packages")
    if not isinstance(packages, dict) or "" not in packages:
        return None
    counts = {
        "prod": 1,
        "dev": 0,
        "optional": 0,
        "peer": 0,
        "peerOptional": 0,
        "total": 0,
    }
    for path, row in packages.items():
        if path == "":
            continue
        if (
            not isinstance(path, str)
            or not path.startswith("node_modules/")
            or not isinstance(row, dict)
            or UNSUPPORTED_LOCK_ROW_FIELDS.intersection(row)
        ):
            return None
        for flag in ("dev", "optional", "devOptional", "peer"):
            if flag in row and not isinstance(row[flag], bool):
                return None
        version = row.get("version")
        if not isinstance(version, str) or not version:
            return None
        is_dev = row.get("dev") is True or row.get("devOptional") is True
        is_optional = row.get("optional") is True
        is_peer = row.get("peer") is True
        counts["total"] += 1
        counts["dev"] += int(is_dev)
        counts["prod"] += int(not is_dev)
        counts["optional"] += int(is_optional)
        counts["peer"] += int(is_peer)
        counts["peerOptional"] += int(is_peer and is_optional)
    return counts


def _manifest_lock_match(package_json: Path, package_lock: Path) -> bool:
    manifest = _json_object(package_json)
    lock = _json_object(package_lock)
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    if (
        not manifest
        or not isinstance(root, dict)
        or UNSUPPORTED_MANIFEST_FIELDS.intersection(manifest)
        or set(lock)
        != {"name", "version", "license", "lockfileVersion", "requires", "packages"}
        or type(lock.get("lockfileVersion")) is not int
        or lock.get("lockfileVersion") != 3
        or lock.get("requires") is not True
        or manifest.get("private") is not True
        or manifest.get("license") != REQUIRED_FIRST_PARTY_LICENSE
        or lock.get("license") != REQUIRED_FIRST_PARTY_LICENSE
        or root.get("license") != REQUIRED_FIRST_PARTY_LICENSE
        or manifest.get("packageManager") != REQUIRED_PACKAGE_MANAGER
        or manifest.get("engines") != REQUIRED_ENGINES
        or lock.get("name") != manifest.get("name")
        or lock.get("version") != manifest.get("version")
        or root.get("name") != manifest.get("name")
        or root.get("version") != manifest.get("version")
        or root.get("engines") != manifest.get("engines")
        or UNSUPPORTED_LOCK_ROW_FIELDS.intersection(root)
        or _lock_graph_counts(lock) is None
    ):
        return False
    for key in DIRECT_DEPENDENCY_FIELDS:
        manifest_rows = manifest.get(key, {})
        lock_rows = root.get(key, {})
        if (
            not _exact_direct_specs(manifest_rows)
            or not isinstance(lock_rows, dict)
            or manifest_rows != lock_rows
        ):
            return False
        for name, spec in manifest_rows.items():
            resolved = packages.get(f"node_modules/{name}")
            if not isinstance(resolved, dict) or resolved.get("version") != spec:
                return False
    manifest_peer = manifest.get("peerDependencies", {})
    manifest_peer_meta = manifest.get("peerDependenciesMeta", {})
    lock_peer_meta = root.get("peerDependenciesMeta", {})
    if (
        not isinstance(manifest_peer, dict)
        or not _peer_meta_valid(manifest_peer_meta, manifest_peer)
        or manifest_peer_meta != lock_peer_meta
    ):
        return False
    return True


def _ajv_exact_version_match(package_json: Path, package_lock: Path) -> bool:
    manifest = _json_object(package_json)
    lock = _json_object(package_lock)
    dependencies = manifest.get("dependencies")
    packages = lock.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    ajv = packages.get("node_modules/ajv") if isinstance(packages, dict) else None
    return bool(
        isinstance(dependencies, dict)
        and dependencies.get("ajv") == REQUIRED_AJV_VERSION
        and isinstance(root, dict)
        and isinstance(root.get("dependencies"), dict)
        and root["dependencies"].get("ajv") == REQUIRED_AJV_VERSION
        and isinstance(ajv, dict)
        and ajv.get("version") == REQUIRED_AJV_VERSION
    )


def _strict_vulnerability_counts(
    payload: dict[str, Any],
) -> tuple[dict[str, int], bool]:
    metadata = payload.get("metadata")
    values = metadata.get("vulnerabilities") if isinstance(metadata, dict) else None
    if not isinstance(values, dict) or set(values) != {
        *VULNERABILITY_LEVELS,
        "total",
    }:
        return {level: 0 for level in VULNERABILITY_LEVELS}, False
    counts: dict[str, int] = {}
    for level in VULNERABILITY_LEVELS:
        value = values.get(level)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return {name: 0 for name in VULNERABILITY_LEVELS}, False
        counts[level] = value
    total = values.get("total")
    valid = (
        not isinstance(total, bool)
        and isinstance(total, int)
        and total >= 0
        and total == sum(counts.values())
    )
    return counts, valid


def _vulnerability_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return []
    rows: list[dict[str, Any]] = []
    for name, row in sorted(vulnerabilities.items()):
        if not isinstance(name, str) or not isinstance(row, dict):
            continue
        via_rows: list[dict[str, Any]] = []
        via = row.get("via")
        if isinstance(via, list):
            for item in via:
                if isinstance(item, dict):
                    via_rows.append(
                        {
                            "title": str(item.get("title", "")),
                            "severity": str(item.get("severity", "")),
                            "url": str(item.get("url", "")),
                            "range": str(item.get("range", "")),
                        }
                    )
                elif isinstance(item, str):
                    via_rows.append(
                        {"title": item, "severity": "", "url": "", "range": ""}
                    )
        rows.append(
            {
                "name": str(row.get("name", name)),
                "severity": str(row.get("severity", "")),
                "range": str(row.get("range", "")),
                "is_direct": row.get("isDirect") is True,
                "fix_available": row.get("fixAvailable", False),
                "via": via_rows,
            }
        )
    return rows


def _audit_payload_contract(payload: dict[str, Any]) -> bool:
    vulnerabilities = payload.get("vulnerabilities")
    metadata = payload.get("metadata")
    dependencies = metadata.get("dependencies") if isinstance(metadata, dict) else None
    return bool(
        set(payload) == {"auditReportVersion", "vulnerabilities", "metadata"}
        and type(payload.get("auditReportVersion")) is int
        and payload.get("auditReportVersion") == 2
        and isinstance(vulnerabilities, dict)
        and all(
            isinstance(name, str) and isinstance(row, dict)
            for name, row in vulnerabilities.items()
        )
        and isinstance(metadata, dict)
        and set(metadata) == {"vulnerabilities", "dependencies"}
        and isinstance(dependencies, dict)
        and set(dependencies)
        == {"prod", "dev", "optional", "peer", "peerOptional", "total"}
        and all(
            not isinstance(value, bool) and isinstance(value, int) and value >= 0
            for value in dependencies.values()
        )
    )


def _audit_metadata_matches_lock_graph(
    payload: dict[str, Any], package_lock: Path
) -> bool:
    metadata = payload.get("metadata")
    dependencies = metadata.get("dependencies") if isinstance(metadata, dict) else None
    return bool(
        isinstance(dependencies, dict)
        and all(type(value) is int and value >= 0 for value in dependencies.values())
        and dependencies == _lock_graph_counts(_json_object(package_lock))
    )


def _signature_payload_contract(payload: dict[str, Any]) -> bool:
    return bool(
        set(payload) == {"invalid", "missing"}
        and isinstance(payload.get("invalid"), list)
        and isinstance(payload.get("missing"), list)
        and payload["invalid"] == []
        and payload["missing"] == []
    )


def _vulnerability_rows_match_metadata(payload: dict[str, Any]) -> bool:
    counts, metadata_valid = _strict_vulnerability_counts(payload)
    vulnerabilities = payload.get("vulnerabilities")
    if not metadata_valid or not isinstance(vulnerabilities, dict):
        return False
    actual = {level: 0 for level in VULNERABILITY_LEVELS}
    for row in vulnerabilities.values():
        if not isinstance(row, dict):
            return False
        severity = row.get("severity")
        if severity not in actual:
            return False
        actual[str(severity)] += 1
    return actual == counts


def _timestamp_is_utc(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(
        parsed
    )


def _evaluation(
    *,
    source: dict[str, Any],
    package_json_binding: dict[str, Any],
    package_lock_binding: dict[str, Any],
    dependency_surface_violations: list[str],
    manifest_lock_match: bool,
    ajv_exact_version_match: bool,
    audit_payload: dict[str, Any],
    audit_exit_code: int,
    install_exit_code: int,
    stdout_payload_match: bool,
    signatures_payload: dict[str, Any],
    signatures_exit_code: int,
    signatures_stdout_payload_match: bool,
    node_version: str,
    npm_version: str,
    effective_registry: str,
    effective_strict_ssl: str,
    effective_proxy: str,
    effective_https_proxy: str,
    effective_cafile: str,
    package_lock: Path,
    config_isolation: bool,
    isolated_working_copy: bool,
    execution_order: list[str],
    tools: dict[str, Any],
) -> tuple[dict[str, bool], list[str], dict[str, Any]]:
    counts, metadata_valid = _strict_vulnerability_counts(audit_payload)
    total = sum(counts.values())
    high_critical = counts["high"] + counts["critical"]
    checks = {
        "source_identity_valid": (
            isinstance(source.get("commit_sha"), str)
            and SHA_PATTERN.fullmatch(str(source.get("commit_sha"))) is not None
            and isinstance(source.get("tree_sha"), str)
            and SHA_PATTERN.fullmatch(str(source.get("tree_sha"))) is not None
        ),
        "source_commit_matches_expected": source.get("commit_sha")
        == source.get("expected_commit_sha"),
        "source_worktree_clean": source.get("worktree_clean") is True,
        "trusted_toolchain_exact": bool(
            _validate_tool_evidence(tools, require_files=False)
        ),
        "package_json_regular_file": package_json_binding.get("regular_file") is True,
        "package_lock_regular_file": package_lock_binding.get("regular_file") is True,
        "dependency_config_surface_clean": not dependency_surface_violations,
        "package_manifest_lock_root_match": manifest_lock_match,
        "npm_audit_metadata_matches_lock_graph": _audit_metadata_matches_lock_graph(
            audit_payload, package_lock
        ),
        "ajv_direct_runtime_fixed_exact_version": ajv_exact_version_match,
        "node_version_exact": node_version.strip() == REQUIRED_NODE_VERSION,
        "npm_version_exact": npm_version.strip() == REQUIRED_NPM_VERSION,
        "npm_registry_exact": effective_registry.strip() == NPM_REGISTRY,
        "npm_strict_ssl_enabled": effective_strict_ssl.strip() == "true",
        "npm_proxy_disabled": effective_proxy.strip() == "null",
        "npm_https_proxy_disabled": effective_https_proxy.strip() == "null",
        "npm_cafile_unset": effective_cafile.strip() == "null",
        "npm_config_isolated": config_isolation,
        "npm_isolated_clean_copy": isolated_working_copy,
        "npm_execution_order_exact": execution_order
        == ["clean-copy-npm-ci", "npm-audit", "npm-audit-signatures"],
        "npm_clean_install_exit_code_zero_pass": install_exit_code == 0,
        "npm_audit_payload_contract_pass": _audit_payload_contract(audit_payload),
        "npm_audit_stdout_payload_match": stdout_payload_match,
        "npm_audit_metadata_consistent": metadata_valid,
        "npm_audit_vulnerability_rows_match_metadata": (
            _vulnerability_rows_match_metadata(audit_payload)
        ),
        "dependency_vulnerability_total_zero_pass": metadata_valid and total == 0,
        "dependency_high_or_critical_zero_pass": metadata_valid and high_critical == 0,
        "npm_audit_exit_code_zero_pass": audit_exit_code == 0,
        "npm_signature_payload_contract_pass": _signature_payload_contract(
            signatures_payload
        ),
        "npm_signature_stdout_payload_match": signatures_stdout_payload_match,
        "npm_signature_exit_code_zero_pass": signatures_exit_code == 0,
    }
    blockers = [label for label, passed in checks.items() if not passed]
    summary = {
        "npm_clean_install_exit_code": install_exit_code,
        "npm_audit_exit_code": audit_exit_code,
        "vulnerability_total": total,
        "high_or_critical_vulnerability_count": high_critical,
        "signature_invalid_count": (
            len(signatures_payload.get("invalid", []))
            if isinstance(signatures_payload.get("invalid"), list)
            else -1
        ),
        "signature_missing_count": (
            len(signatures_payload.get("missing", []))
            if isinstance(signatures_payload.get("missing"), list)
            else -1
        ),
        **{
            f"{level}_vulnerability_count": counts[level]
            for level in VULNERABILITY_LEVELS
        },
    }
    return checks, blockers, summary


def build_report(
    *,
    audit_payload: dict[str, Any],
    audit_exit_code: int,
    audit_stdout: str,
    install_exit_code: int = 0,
    install_stdout: str = "",
    install_stderr: str = "",
    signatures_payload: dict[str, Any],
    signatures_exit_code: int,
    signatures_stdout: str,
    source_identity: dict[str, Any],
    expected_source_sha: str,
    node_version: str,
    npm_version: str,
    effective_registry: str = NPM_REGISTRY,
    effective_strict_ssl: str = "true",
    effective_proxy: str = "null",
    effective_https_proxy: str = "null",
    effective_cafile: str = "null",
    config_isolation: bool = True,
    isolated_working_copy: bool = True,
    execution_order: list[str] | None = None,
    tools: dict[str, Any] | None = None,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    tool_evidence = _validate_tool_evidence(
        tools if tools is not None else _default_tool_evidence(),
        require_files=False,
    )
    source = _validate_identity(source_identity, expected_source_sha)
    package_json_binding = _file_binding(package_json)
    package_lock_binding = _file_binding(package_lock)
    dependency_surface_violations = _dependency_surface_violations(package_json)
    manifest_lock_match = _manifest_lock_match(package_json, package_lock)
    stdout_payload_match = (
        bool(audit_payload) and _load_json_text(audit_stdout) == audit_payload
    )
    signatures_stdout_payload_match = bool(signatures_payload) and (
        _load_json_text(signatures_stdout) == signatures_payload
    )
    checks, blockers, summary = _evaluation(
        source=source,
        package_json_binding=package_json_binding,
        package_lock_binding=package_lock_binding,
        dependency_surface_violations=dependency_surface_violations,
        manifest_lock_match=manifest_lock_match,
        ajv_exact_version_match=_ajv_exact_version_match(package_json, package_lock),
        audit_payload=audit_payload,
        audit_exit_code=audit_exit_code,
        install_exit_code=install_exit_code,
        stdout_payload_match=stdout_payload_match,
        signatures_payload=signatures_payload,
        signatures_exit_code=signatures_exit_code,
        signatures_stdout_payload_match=signatures_stdout_payload_match,
        node_version=node_version,
        npm_version=npm_version,
        effective_registry=effective_registry,
        effective_strict_ssl=effective_strict_ssl,
        effective_proxy=effective_proxy,
        effective_https_proxy=effective_https_proxy,
        effective_cafile=effective_cafile,
        package_lock=package_lock,
        config_isolation=config_isolation,
        isolated_working_copy=isolated_working_copy,
        execution_order=execution_order
        or ["clean-copy-npm-ci", "npm-audit", "npm-audit-signatures"],
        tools=tool_evidence,
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": _now_utc_iso(),
        "source": source,
        "inputs": {
            "package_json": package_json_binding,
            "package_lock": package_lock_binding,
            "dependency_surface_violations": dependency_surface_violations,
        },
        "tools": tool_evidence,
        "audit": {
            "execution_order": execution_order
            or ["clean-copy-npm-ci", "npm-audit", "npm-audit-signatures"],
            "working_directory": "isolated-clean-copy",
            "install": {
                "command": [
                    tool_evidence["node"]["realpath"],
                    tool_evidence["npm_cli"]["realpath"],
                    *INSTALL_COMMAND,
                ],
                "exit_code": install_exit_code,
                "stdout": install_stdout,
                "stdout_bytes": len(install_stdout.encode("utf-8")),
                "stdout_sha256": _sha256_bytes(install_stdout.encode("utf-8")),
                "stderr": install_stderr,
                "stderr_bytes": len(install_stderr.encode("utf-8")),
                "stderr_sha256": _sha256_bytes(install_stderr.encode("utf-8")),
            },
            "command": [
                tool_evidence["node"]["realpath"],
                tool_evidence["npm_cli"]["realpath"],
                *AUDIT_COMMAND,
            ],
            "exit_code": audit_exit_code,
            "node_version": node_version.strip(),
            "npm_version": npm_version.strip(),
            "effective_registry": effective_registry.strip(),
            "effective_strict_ssl": effective_strict_ssl.strip(),
            "effective_proxy": effective_proxy.strip(),
            "effective_https_proxy": effective_https_proxy.strip(),
            "effective_cafile": effective_cafile.strip(),
            "config_isolation": {
                "environment_allowlist_only": config_isolation,
                "node_path_options_tls_ca_proxy_token_corepack_removed": config_isolation,
                "userconfig_dev_null": config_isolation,
                "globalconfig_dev_null": config_isolation,
                "explicit_registry_and_strict_ssl": config_isolation,
                "explicit_dependency_class_includes": config_isolation,
                "isolated_clean_copy": isolated_working_copy,
            },
            "environment_allowlist": list(NPM_ENVIRONMENT_ALLOWLIST_KEYS),
            "payload": audit_payload,
            "payload_sha256": _canonical_hash(audit_payload),
            "stdout": audit_stdout,
            "stdout_bytes": len(audit_stdout.encode("utf-8")),
            "stdout_sha256": _sha256_bytes(audit_stdout.encode("utf-8")),
            "signatures": {
                "command": [
                    tool_evidence["node"]["realpath"],
                    tool_evidence["npm_cli"]["realpath"],
                    *SIGNATURE_COMMAND,
                ],
                "exit_code": signatures_exit_code,
                "payload": signatures_payload,
                "payload_sha256": _canonical_hash(signatures_payload),
                "stdout": signatures_stdout,
                "stdout_bytes": len(signatures_stdout.encode("utf-8")),
                "stdout_sha256": _sha256_bytes(signatures_stdout.encode("utf-8")),
                "claim": "registry provenance check only; no product-signing authority",
            },
        },
        "contract_pass": not blockers,
        "reason_code": (
            "PASS" if not blockers else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED"
        ),
        "blockers": blockers,
        "checks": checks,
        "summary": {
            "package_json": package_json_binding["path"],
            "package_lock": package_lock_binding["path"],
            **summary,
        },
        "vulnerabilities": _vulnerability_rows(audit_payload),
        "claim_boundary": deepcopy(CLAIM_BOUNDARY),
    }
    payload["artifact_hash"] = _canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    return payload


def _sanitized_npm_environment(
    cache: Path,
    *,
    user_config: Path,
    global_config: Path,
    home: Path | None = None,
    tmpdir: Path | None = None,
) -> dict[str, str]:
    npm_env = _minimal_process_environment(
        home=home or cache.parent / "home",
        tmpdir=tmpdir or cache.parent / "tmp",
    )
    npm_env.update(
        {
            "NPM_CONFIG_USERCONFIG": str(user_config),
            "NPM_CONFIG_GLOBALCONFIG": str(global_config),
            "NPM_CONFIG_CACHE": str(cache),
        }
    )
    return npm_env


def run_audit(
    *,
    cwd: Path,
    package_json: Path,
    package_lock: Path,
    trusted_node: Path | None,
    trusted_npm_cli: Path | None,
    trusted_git: Path = TRUSTED_GIT_PATH,
) -> dict[str, Any]:
    source_package_json = (
        package_json if package_json.is_absolute() else cwd / package_json
    )
    source_package_lock = (
        package_lock if package_lock.is_absolute() else cwd / package_lock
    )
    if _dependency_surface_violations(source_package_json):
        raise FrontendDependencyAuditError("dependency_config_surface_not_clean")
    if (
        not source_package_json.is_file()
        or source_package_json.is_symlink()
        or not source_package_lock.is_file()
        or source_package_lock.is_symlink()
    ):
        raise FrontendDependencyAuditError("dependency_manifest_input_unsafe")
    if trusted_node is None or trusted_npm_cli is None:
        raise FrontendDependencyAuditError("trusted_node_toolchain_required")
    tools = trusted_tool_evidence(
        trusted_node=trusted_node,
        trusted_npm_cli=trusted_npm_cli,
        trusted_git=trusted_git,
    )
    node_command = tools["node"]["realpath"]
    npm_prefix = [node_command, tools["npm_cli"]["realpath"]]
    try:
        with tempfile.TemporaryDirectory(prefix="frontend-npm-audit-") as raw_tmp:
            raw_root = Path(raw_tmp)
            audit_cwd = raw_root / "clean-copy"
            audit_cwd.mkdir(mode=0o700)
            source_package_json = source_package_json.resolve()
            source_package_lock = source_package_lock.resolve()
            copied_package_json = audit_cwd / "package.json"
            copied_package_lock = audit_cwd / "package-lock.json"
            shutil.copyfile(source_package_json, copied_package_json)
            shutil.copyfile(source_package_lock, copied_package_lock)
            input_hashes = {
                "package_json": _sha256_path(source_package_json),
                "package_lock": _sha256_path(source_package_lock),
            }
            config_root = raw_root / "config"
            config_root.mkdir(mode=0o700)
            user_config = config_root / "user.npmrc"
            global_config = config_root / "global.npmrc"
            user_config.symlink_to(os.devnull)
            global_config.symlink_to(os.devnull)
            if not (
                os.path.samefile(user_config, os.devnull)
                and os.path.samefile(global_config, os.devnull)
            ):
                raise FrontendDependencyAuditError("npm_dev_null_config_alias_invalid")
            npm_env = _sanitized_npm_environment(
                raw_root / "cache",
                user_config=user_config,
                global_config=global_config,
                home=raw_root / "home",
                tmpdir=raw_root / "tmp",
            )
            Path(npm_env["HOME"]).mkdir(mode=0o700)
            Path(npm_env["TMPDIR"]).mkdir(mode=0o700)
            node_version = subprocess.check_output(
                [node_command, "--version"],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            npm_version = subprocess.check_output(
                [*npm_prefix, "--version"],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            effective_registry = subprocess.check_output(
                [*npm_prefix, "config", "get", "registry", *NPM_CONFIG_ARGS],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            effective_strict_ssl = subprocess.check_output(
                [*npm_prefix, "config", "get", "strict-ssl", *NPM_CONFIG_ARGS],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            effective_proxy = subprocess.check_output(
                [*npm_prefix, "config", "get", "proxy", *NPM_CONFIG_ARGS],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            effective_https_proxy = subprocess.check_output(
                [*npm_prefix, "config", "get", "https-proxy", *NPM_CONFIG_ARGS],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            effective_cafile = subprocess.check_output(
                [*npm_prefix, "config", "get", "cafile", *NPM_CONFIG_ARGS],
                cwd=audit_cwd,
                env=npm_env,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
            install = subprocess.run(
                [*npm_prefix, *INSTALL_COMMAND],
                cwd=audit_cwd,
                env=npm_env,
                check=False,
                text=True,
                capture_output=True,
            )
            result = subprocess.run(
                [*npm_prefix, *AUDIT_COMMAND],
                cwd=audit_cwd,
                env=npm_env,
                check=False,
                text=True,
                capture_output=True,
            )
            signatures = subprocess.run(
                [*npm_prefix, *SIGNATURE_COMMAND],
                cwd=audit_cwd,
                env=npm_env,
                check=False,
                text=True,
                capture_output=True,
            )
            copied_hashes = {
                "package_json": _sha256_path(copied_package_json),
                "package_lock": _sha256_path(copied_package_lock),
            }
            if copied_hashes != input_hashes:
                raise FrontendDependencyAuditError(
                    "isolated_package_copy_changed_during_audit"
                )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FrontendDependencyAuditError("npm_audit_execution_failed") from exc
    return {
        "payload": _load_json_text(result.stdout),
        "exit_code": int(result.returncode),
        "stdout": result.stdout,
        "install_exit_code": int(install.returncode),
        "install_stdout": install.stdout,
        "install_stderr": install.stderr,
        "signatures_payload": _load_json_text(signatures.stdout),
        "signatures_exit_code": int(signatures.returncode),
        "signatures_stdout": signatures.stdout,
        "node_version": node_version,
        "npm_version": npm_version,
        "effective_registry": effective_registry,
        "effective_strict_ssl": effective_strict_ssl,
        "effective_proxy": effective_proxy,
        "effective_https_proxy": effective_https_proxy,
        "effective_cafile": effective_cafile,
        "config_isolation": True,
        "isolated_working_copy": True,
        "execution_order": [
            "clean-copy-npm-ci",
            "npm-audit",
            "npm-audit-signatures",
        ],
        "tools": tools,
    }


def _capture_text(path: Path) -> str:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4_000_000:
        raise FrontendDependencyAuditError(f"audit_capture_file_invalid:{path.name}")
    return path.read_text(encoding="utf-8")


def _capture_exit_code(path: Path) -> int:
    value = _capture_text(path).strip()
    if not re.fullmatch(r"(?:0|[1-9][0-9]{0,2})", value):
        raise FrontendDependencyAuditError(f"audit_capture_exit_invalid:{path.name}")
    parsed = int(value)
    if parsed > 255:
        raise FrontendDependencyAuditError(f"audit_capture_exit_invalid:{path.name}")
    return parsed


def _capture_identity(path: Path) -> dict[str, Any]:
    rows = _capture_text(path).splitlines()
    if len(rows) != 3 or rows[2] not in {"clean", "dirty"}:
        raise FrontendDependencyAuditError(f"audit_capture_source_invalid:{path.name}")
    return _validate_identity(
        {
            "commit_sha": rows[0],
            "tree_sha": rows[1],
            "worktree_clean": rows[2] == "clean",
        },
        rows[0],
    )


def load_audit_capture(capture_dir: Path) -> dict[str, Any]:
    if not capture_dir.is_dir() or capture_dir.is_symlink():
        raise FrontendDependencyAuditError("audit_capture_directory_invalid")
    entries = list(capture_dir.iterdir())
    if {row.name for row in entries} != set(AUDIT_CAPTURE_FILES.values()) or any(
        not row.is_file() or row.is_symlink() for row in entries
    ):
        raise FrontendDependencyAuditError("audit_capture_file_set_invalid")
    paths = {label: capture_dir / name for label, name in AUDIT_CAPTURE_FILES.items()}
    audit_stdout = _capture_text(paths["audit_stdout"])
    signatures_stdout = _capture_text(paths["signatures_stdout"])
    tools = {
        "distribution": {
            "archive_url": _capture_text(paths["node_archive_url"]).strip(),
            "archive_sha256": _capture_text(paths["node_archive_sha256"]).strip(),
            "shasums_url": _capture_text(paths["node_shasums_url"]).strip(),
            "official_shasum_line": _capture_text(
                paths["node_official_shasum_line"]
            ).strip(),
        },
        "node": {
            "path": _capture_text(paths["trusted_node_path"]).strip(),
            "realpath": _capture_text(paths["trusted_node_realpath"]).strip(),
            "sha256": _capture_text(paths["trusted_node_sha256"]).strip(),
            "version": _capture_text(paths["node_version"]).strip(),
        },
        "npm_cli": {
            "path": _capture_text(paths["trusted_npm_cli_path"]).strip(),
            "realpath": _capture_text(paths["trusted_npm_cli_realpath"]).strip(),
            "sha256": _capture_text(paths["trusted_npm_cli_sha256"]).strip(),
            "version": _capture_text(paths["npm_version"]).strip(),
        },
        "git": {
            "path": _capture_text(paths["trusted_git_path"]).strip(),
            "realpath": _capture_text(paths["trusted_git_realpath"]).strip(),
            "sha256": _capture_text(paths["trusted_git_sha256"]).strip(),
            "version": _capture_text(paths["trusted_git_version"]).strip(),
        },
    }
    _validate_tool_evidence(tools, require_files=True)
    return {
        "payload": _load_json_text(audit_stdout),
        "exit_code": _capture_exit_code(paths["audit_exit_code"]),
        "stdout": audit_stdout,
        "install_exit_code": _capture_exit_code(paths["install_exit_code"]),
        "install_stdout": _capture_text(paths["install_stdout"]),
        "install_stderr": _capture_text(paths["install_stderr"]),
        "signatures_payload": _load_json_text(signatures_stdout),
        "signatures_exit_code": _capture_exit_code(paths["signatures_exit_code"]),
        "signatures_stdout": signatures_stdout,
        "node_version": _capture_text(paths["node_version"]).strip(),
        "npm_version": _capture_text(paths["npm_version"]).strip(),
        "effective_registry": _capture_text(paths["effective_registry"]).strip(),
        "effective_strict_ssl": _capture_text(paths["effective_strict_ssl"]).strip(),
        "effective_proxy": _capture_text(paths["effective_proxy"]).strip(),
        "effective_https_proxy": _capture_text(paths["effective_https_proxy"]).strip(),
        "effective_cafile": _capture_text(paths["effective_cafile"]).strip(),
        "config_isolation": True,
        "isolated_working_copy": True,
        "execution_order": [
            "clean-copy-npm-ci",
            "npm-audit",
            "npm-audit-signatures",
        ],
        "tools": tools,
        "capture_source_before": _capture_identity(paths["source_before"]),
        "capture_source_after": _capture_identity(paths["source_after"]),
    }


def verify_report(
    payload: dict[str, Any],
    *,
    source_identity: dict[str, Any],
    expected_source_sha: str,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
) -> dict[str, Any]:
    if set(payload) != {
        "schema_version",
        "generated_at",
        "source",
        "inputs",
        "tools",
        "audit",
        "contract_pass",
        "reason_code",
        "blockers",
        "checks",
        "summary",
        "vulnerabilities",
        "claim_boundary",
        "artifact_hash",
    }:
        raise FrontendDependencyAuditError("report_fields_invalid")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise FrontendDependencyAuditError("report_schema_version_invalid")
    expected_artifact_hash = _canonical_hash(
        {key: value for key, value in payload.items() if key != "artifact_hash"}
    )
    if payload.get("artifact_hash") != expected_artifact_hash:
        raise FrontendDependencyAuditError("report_artifact_hash_invalid")
    if not _timestamp_is_utc(payload.get("generated_at")):
        raise FrontendDependencyAuditError("report_generated_at_invalid")

    source = _validate_identity(source_identity, expected_source_sha)
    if payload.get("source") != source:
        raise FrontendDependencyAuditError("report_source_binding_invalid")
    inputs = payload.get("inputs")
    if not isinstance(inputs, dict):
        raise FrontendDependencyAuditError("report_input_bindings_invalid")
    package_json_binding = _file_binding(package_json)
    package_lock_binding = _file_binding(package_lock)
    dependency_surface_violations = _dependency_surface_violations(package_json)
    if inputs != {
        "package_json": package_json_binding,
        "package_lock": package_lock_binding,
        "dependency_surface_violations": dependency_surface_violations,
    }:
        raise FrontendDependencyAuditError("report_input_bindings_invalid")

    tools_value = payload.get("tools")
    if not isinstance(tools_value, dict):
        raise FrontendDependencyAuditError("report_toolchain_invalid")
    tools = _validate_tool_evidence(tools_value, require_files=False)
    npm_command_prefix = [
        tools["node"]["realpath"],
        tools["npm_cli"]["realpath"],
    ]

    audit = payload.get("audit")
    if not isinstance(audit, dict) or audit.get("command") != [
        *npm_command_prefix,
        *AUDIT_COMMAND,
    ]:
        raise FrontendDependencyAuditError("report_audit_contract_invalid")
    if set(audit) != {
        "command",
        "execution_order",
        "working_directory",
        "install",
        "exit_code",
        "node_version",
        "npm_version",
        "effective_registry",
        "effective_strict_ssl",
        "effective_proxy",
        "effective_https_proxy",
        "effective_cafile",
        "config_isolation",
        "environment_allowlist",
        "payload",
        "payload_sha256",
        "stdout",
        "stdout_bytes",
        "stdout_sha256",
        "signatures",
    }:
        raise FrontendDependencyAuditError("report_audit_contract_invalid")
    execution_order = audit.get("execution_order")
    if (
        execution_order != ["clean-copy-npm-ci", "npm-audit", "npm-audit-signatures"]
        or audit.get("working_directory") != "isolated-clean-copy"
    ):
        raise FrontendDependencyAuditError("report_execution_order_invalid")
    install = audit.get("install")
    if not isinstance(install, dict) or set(install) != {
        "command",
        "exit_code",
        "stdout",
        "stdout_bytes",
        "stdout_sha256",
        "stderr",
        "stderr_bytes",
        "stderr_sha256",
    }:
        raise FrontendDependencyAuditError("report_install_contract_invalid")
    install_stdout = install.get("stdout")
    install_stderr = install.get("stderr")
    install_exit_code = install.get("exit_code")
    if (
        install.get("command") != [*npm_command_prefix, *INSTALL_COMMAND]
        or isinstance(install_exit_code, bool)
        or not isinstance(install_exit_code, int)
        or not isinstance(install_stdout, str)
        or not isinstance(install_stderr, str)
        or install.get("stdout_bytes") != len(install_stdout.encode("utf-8"))
        or install.get("stdout_sha256") != _sha256_bytes(install_stdout.encode("utf-8"))
        or install.get("stderr_bytes") != len(install_stderr.encode("utf-8"))
        or install.get("stderr_sha256") != _sha256_bytes(install_stderr.encode("utf-8"))
    ):
        raise FrontendDependencyAuditError("report_install_binding_invalid")
    audit_payload = audit.get("payload")
    if not isinstance(audit_payload, dict):
        raise FrontendDependencyAuditError("report_audit_payload_invalid")
    if audit.get("payload_sha256") != _canonical_hash(audit_payload):
        raise FrontendDependencyAuditError("report_audit_payload_hash_invalid")
    audit_stdout = audit.get("stdout")
    if not isinstance(audit_stdout, str):
        raise FrontendDependencyAuditError("report_audit_stdout_invalid")
    stdout_bytes = audit_stdout.encode("utf-8")
    if (
        audit.get("stdout_bytes") != len(stdout_bytes)
        or audit.get("stdout_sha256") != _sha256_bytes(stdout_bytes)
        or _load_json_text(audit_stdout) != audit_payload
    ):
        raise FrontendDependencyAuditError("report_audit_stdout_binding_invalid")
    audit_exit_code = audit.get("exit_code")
    if isinstance(audit_exit_code, bool) or not isinstance(audit_exit_code, int):
        raise FrontendDependencyAuditError("report_audit_exit_code_invalid")
    node_version = audit.get("node_version")
    npm_version = audit.get("npm_version")
    if not isinstance(node_version, str) or not isinstance(npm_version, str):
        raise FrontendDependencyAuditError("report_toolchain_invalid")
    effective_registry = audit.get("effective_registry")
    effective_strict_ssl = audit.get("effective_strict_ssl")
    effective_proxy = audit.get("effective_proxy")
    effective_https_proxy = audit.get("effective_https_proxy")
    effective_cafile = audit.get("effective_cafile")
    expected_isolation = {
        "environment_allowlist_only": True,
        "node_path_options_tls_ca_proxy_token_corepack_removed": True,
        "userconfig_dev_null": True,
        "globalconfig_dev_null": True,
        "explicit_registry_and_strict_ssl": True,
        "explicit_dependency_class_includes": True,
        "isolated_clean_copy": True,
    }
    if (
        not isinstance(effective_registry, str)
        or not isinstance(effective_strict_ssl, str)
        or not isinstance(effective_proxy, str)
        or not isinstance(effective_https_proxy, str)
        or not isinstance(effective_cafile, str)
        or audit.get("config_isolation") != expected_isolation
        or audit.get("environment_allowlist") != list(NPM_ENVIRONMENT_ALLOWLIST_KEYS)
    ):
        raise FrontendDependencyAuditError("report_npm_config_invalid")
    signatures = audit.get("signatures")
    if not isinstance(signatures, dict) or set(signatures) != {
        "command",
        "exit_code",
        "payload",
        "payload_sha256",
        "stdout",
        "stdout_bytes",
        "stdout_sha256",
        "claim",
    }:
        raise FrontendDependencyAuditError("report_signature_contract_invalid")
    if signatures.get("command") != [*npm_command_prefix, *SIGNATURE_COMMAND]:
        raise FrontendDependencyAuditError("report_signature_contract_invalid")
    signatures_payload = signatures.get("payload")
    signatures_stdout = signatures.get("stdout")
    signatures_exit_code = signatures.get("exit_code")
    if (
        not isinstance(signatures_payload, dict)
        or not isinstance(signatures_stdout, str)
        or isinstance(signatures_exit_code, bool)
        or not isinstance(signatures_exit_code, int)
        or signatures.get("payload_sha256") != _canonical_hash(signatures_payload)
        or signatures.get("stdout_bytes") != len(signatures_stdout.encode("utf-8"))
        or signatures.get("stdout_sha256")
        != _sha256_bytes(signatures_stdout.encode("utf-8"))
        or _load_json_text(signatures_stdout) != signatures_payload
        or signatures.get("claim")
        != "registry provenance check only; no product-signing authority"
    ):
        raise FrontendDependencyAuditError("report_signature_binding_invalid")

    checks, blockers, summary = _evaluation(
        source=source,
        package_json_binding=package_json_binding,
        package_lock_binding=package_lock_binding,
        dependency_surface_violations=dependency_surface_violations,
        manifest_lock_match=_manifest_lock_match(package_json, package_lock),
        ajv_exact_version_match=_ajv_exact_version_match(package_json, package_lock),
        audit_payload=audit_payload,
        audit_exit_code=audit_exit_code,
        install_exit_code=install_exit_code,
        stdout_payload_match=True,
        signatures_payload=signatures_payload,
        signatures_exit_code=signatures_exit_code,
        signatures_stdout_payload_match=True,
        node_version=node_version,
        npm_version=npm_version,
        effective_registry=effective_registry,
        effective_strict_ssl=effective_strict_ssl,
        effective_proxy=effective_proxy,
        effective_https_proxy=effective_https_proxy,
        effective_cafile=effective_cafile,
        package_lock=package_lock,
        config_isolation=True,
        isolated_working_copy=True,
        execution_order=execution_order,
        tools=tools,
    )
    expected_summary = {
        "package_json": package_json_binding["path"],
        "package_lock": package_lock_binding["path"],
        **summary,
    }
    if (
        payload.get("checks") != checks
        or payload.get("blockers") != blockers
        or payload.get("contract_pass") is not (not blockers)
        or payload.get("reason_code")
        != ("PASS" if not blockers else "ERR_FRONTEND_DEPENDENCY_AUDIT_BLOCKED")
        or payload.get("summary") != expected_summary
        or payload.get("vulnerabilities") != _vulnerability_rows(audit_payload)
        or payload.get("claim_boundary") != CLAIM_BOUNDARY
    ):
        raise FrontendDependencyAuditError("report_semantics_invalid")
    if blockers:
        raise FrontendDependencyAuditError("report_contract_blocked")
    return payload


def build_current_report(
    *,
    out: Path,
    expected_source_sha: str = "",
    source_identity: dict[str, Any] | None = None,
    package_json: Path = DEFAULT_PACKAGE_JSON,
    package_lock: Path = DEFAULT_PACKAGE_LOCK,
    audit_capture_dir: Path | None = None,
    trusted_node: Path | None = None,
    trusted_npm_cli: Path | None = None,
) -> dict[str, Any]:
    observed_before = git_identity()
    identity = source_identity if source_identity is not None else observed_before
    if identity != observed_before:
        raise FrontendDependencyAuditError("supplied_source_identity_not_current")
    run = (
        load_audit_capture(audit_capture_dir)
        if audit_capture_dir is not None
        else (
            run_audit(
                cwd=REPO_ROOT,
                package_json=package_json,
                package_lock=package_lock,
                trusted_node=trusted_node,
                trusted_npm_cli=trusted_npm_cli,
            )
        )
    )
    tools = run.get("tools")
    if not isinstance(tools, dict):
        raise FrontendDependencyAuditError("trusted_tool_evidence_missing")
    _validate_tool_evidence(tools, require_files=True)
    if tools["git"]["sha256"] != _tool_sha(TRUSTED_GIT_PATH):
        raise FrontendDependencyAuditError("trusted_git_hash_mismatch")
    expected_capture_identity = _validate_identity(
        identity, str(identity["commit_sha"])
    )
    if audit_capture_dir is not None and (
        run.get("capture_source_before") != expected_capture_identity
        or run.get("capture_source_after") != expected_capture_identity
    ):
        raise FrontendDependencyAuditError("audit_capture_source_binding_invalid")
    if git_identity() != observed_before:
        raise FrontendDependencyAuditError("source_changed_during_npm_audit")
    payload = build_report(
        audit_payload=run["payload"],
        audit_exit_code=run["exit_code"],
        audit_stdout=run["stdout"],
        install_exit_code=run["install_exit_code"],
        install_stdout=run["install_stdout"],
        install_stderr=run["install_stderr"],
        signatures_payload=run["signatures_payload"],
        signatures_exit_code=run["signatures_exit_code"],
        signatures_stdout=run["signatures_stdout"],
        source_identity=identity,
        expected_source_sha=expected_source_sha,
        node_version=run["node_version"],
        npm_version=run["npm_version"],
        effective_registry=run["effective_registry"],
        effective_strict_ssl=run["effective_strict_ssl"],
        effective_proxy=run["effective_proxy"],
        effective_https_proxy=run["effective_https_proxy"],
        effective_cafile=run["effective_cafile"],
        config_isolation=run["config_isolation"] is True,
        isolated_working_copy=run["isolated_working_copy"] is True,
        execution_order=run["execution_order"],
        tools=tools,
        package_json=package_json,
        package_lock=package_lock,
    )
    if git_identity() != observed_before:
        raise FrontendDependencyAuditError("source_changed_during_report_build")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-json", type=Path, default=DEFAULT_PACKAGE_JSON)
    parser.add_argument("--package-lock", type=Path, default=DEFAULT_PACKAGE_LOCK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--expected-source-sha", default="")
    parser.add_argument("--audit-capture-dir", type=Path)
    parser.add_argument("--trusted-node", type=Path)
    parser.add_argument("--trusted-npm-cli", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        identity = git_identity()
        if args.verify:
            payload = _json_object(args.out)
            report_source = payload.get("source")
            report_source_sha = (
                report_source.get("commit_sha")
                if isinstance(report_source, dict)
                else ""
            )
            verify_report(
                payload,
                source_identity=(
                    report_source if isinstance(report_source, dict) else {}
                ),
                expected_source_sha=args.expected_source_sha or report_source_sha,
                package_json=args.package_json,
                package_lock=args.package_lock,
            )
            try:
                args.out.resolve(strict=True).relative_to(REPO_ROOT.resolve(strict=True))
            except (FileNotFoundError, RuntimeError, ValueError):
                pass
            else:
                from scripts import check_generated_artifact_dag

                binding_violations = (
                    check_generated_artifact_dag._validate_frontend_report_git_binding(
                        REPO_ROOT,
                        payload,
                        report_path=args.out,
                    )
                )
                if binding_violations:
                    raise FrontendDependencyAuditError(
                        "report_repository_binding_invalid:"
                        + ",".join(binding_violations)
                    )
        else:
            payload = build_current_report(
                out=args.out,
                expected_source_sha=args.expected_source_sha,
                source_identity=identity,
                package_json=args.package_json,
                package_lock=args.package_lock,
                audit_capture_dir=args.audit_capture_dir,
                trusted_node=args.trusted_node,
                trusted_npm_cli=args.trusted_npm_cli,
            )
    except (FrontendDependencyAuditError, OSError, ValueError) as exc:
        print(f"frontend dependency audit failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json
        else payload["summary"]
    )
    return 1 if args.fail_blocked and not payload["contract_pass"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
