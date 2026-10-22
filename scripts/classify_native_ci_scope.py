#!/usr/bin/env python3
"""Classify changed paths for the staged native CI lanes.

The classifier intentionally uses only the Python standard library so the gate
bootstrap can run before the Rust/C++ workspace exists.  Python is a CI control
plane dependency here; it is not part of the native product runtime.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
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
        "LICENSE",
        ".github/workflows/native-pr-fast.yml",
        ".github/workflows/native-nightly-quality.yml",
        "scripts/check_native_ci_contract.py",
        "scripts/check_native_capabilities.py",
        "scripts/check_native_dependency_boundary.py",
        "scripts/check_native_dependency_licenses.py",
        "scripts/build_native_frame_alpha_distribution.py",
        "scripts/classify_native_ci_scope.py",
        "tests/test_native_ci_scope.py",
        "tests/test_native_capability_manifest.py",
        "tests/test_native_ci_workflow_contract.py",
        "tests/test_native_dependency_license.py",
        "tests/test_native_frame_alpha_distribution.py",
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
        "tests/test_native_model_ir_rust_parity.py",
    }
)
FRAME3D_ORACLE_PATHS = frozenset(
    {
        "scripts/run_native_frame3d_modelir_parity.py",
        "scripts/build_native_frame3d_reference_inventory.py",
        "src/structural_analysis/adapters/bounded_native_frame3d_source_units.py",
        "src/structural_analysis/elements/frame3d.py",
        "src/structural_analysis/elements/timoshenko_frame3d.py",
        "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v1.schema.json",
        "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v2.schema.json",
        "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v3.schema.json",
        "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v4.schema.json",
        "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json",
        "src/structural_analysis/schemas/native_frame3d_reference_inventory_v3.schema.json",
        "src/structural_analysis/schemas/native_frame3d_reference_inventory_v4.schema.json",
        "tests/test_native_frame3d_modelir_parity_pack.py",
        "tests/test_native_linear_frame3d.py",
    }
)
WORKSTATION_PACKAGE_PATHS = frozenset(
    {
        "index.html",
        "package.json",
        "package-lock.json",
        "vite.config.ts",
        "src/main.tsx",
    }
)
WORKSTATION_PACKAGE_PREFIXES = ("src/workbench-v2/", "src/structure-viewer/")


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
    frame3d_oracle_paths = [path for path in paths if path in FRAME3D_ORACLE_PATHS]
    workstation_package_paths = [
        path
        for path in paths
        if path in WORKSTATION_PACKAGE_PATHS
        or _starts_with_any(path, WORKSTATION_PACKAGE_PREFIXES)
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
        if path == "native/capabilities.json"
        or "model_ir" in path
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
    applicable = bool(
        native_paths
        or modelir_oracle_paths
        or frame3d_oracle_paths
        or ci_control_paths
        or workstation_package_paths
    )
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
        "oracle": bool(modelir_oracle_paths or frame3d_oracle_paths),
        "ci_control": bool(ci_control_paths),
        "workstation_package": bool(workstation_package_paths),
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
            "-m",
            "--no-commit-id",
            "--name-only",
            "-z",
            "-r",
            "--diff-filter=ACMRTD",
            "--no-renames",
            head,
        ]
    else:
        command = [
            "git",
            "diff",
            "--name-only",
            "-z",
            "--diff-filter=ACMRTD",
            "--no-renames",
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


# This is a proposed change to the pre-merge admission policy, not an exemption
# from the protected-evidence classification. It must be approved before use.
_METADATA_PREFIX = "implementation/phase1/release_evidence/productization/"
_CANONICAL_INPUT = "src/structural_analysis/engine_v2/contracts/_canonical.py"
_COMMON_ARC_INPUTS = frozenset(
    {
        "src/structural_analysis/engine_v2/contracts/equation_scaling.py",
        "src/structural_analysis/engine_v2/contracts/execution_plan.py",
    }
)
METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS = {
    _METADATA_PREFIX + "phase2_sparse_chain_cpu_fgmres_arc_length_summary.json": (
        _COMMON_ARC_INPUTS
        | {"tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py"}
    ),
    _METADATA_PREFIX + "phase2_load_coupled_sparse_chain_arc_length_summary.json": (
        _COMMON_ARC_INPUTS
        | {"tests/test_build_phase2_load_coupled_sparse_chain_arc_length_artifacts.py"}
    ),
    _METADATA_PREFIX + "g1_mgt_matrix_free_preconditioner_candidate_audit.json": (
        frozenset({_CANONICAL_INPUT})
    ),
    _METADATA_PREFIX
    + "g1_mgt_state_updated_frame_axial_geometry_adapter_receipt.json": (
        frozenset({_CANONICAL_INPUT})
    ),
    _METADATA_PREFIX
    + "g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.json": (
        frozenset({_CANONICAL_INPUT})
    ),
}
_MAX_RECEIPT_BYTES = 1024 * 1024
_MAX_SOFTWARE_INPUT_BYTES = 16 * 1024 * 1024
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_METADATA_BOUNDARY = (
    "Only the five finite software metadata projections are compared. Changed "
    "software checksum leaves bind exact head bytes; unchanged input references "
    "bind equal base/head Git blob identities only, including LFS pointers. "
    "This does not revalidate their contents, replay builders, or establish "
    "numerical, physical, hardware, readiness, release or commercial authority."
)


class MetadataValidationError(ValueError):
    """Fail closed when immutable metadata validation cannot be established."""


def _metadata_git(repo_root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=False, capture_output=True
    )
    if result.returncode:
        # Do not expose arbitrary Git output, receipt contents, or dependency data.
        raise MetadataValidationError("immutable_git_object_unavailable")
    return result.stdout


def _metadata_commit(repo_root: Path, revision: str) -> str:
    if not isinstance(revision, str) or _HEX40.fullmatch(revision) is None:
        raise MetadataValidationError("full_immutable_commit_sha_required")
    actual = _metadata_git(repo_root, "rev-parse", "--verify", revision + "^{commit}")
    if actual.decode("ascii").strip() != revision:
        raise MetadataValidationError("immutable_commit_identity_mismatch")
    return revision


def _metadata_reference(repo_root: Path, revision: str, path: str) -> tuple[str, str]:
    if not isinstance(path, str) or _normalize_path(path) != path:
        raise MetadataValidationError("noncanonical_input_reference_path")
    # A checksum reference must never cause secret contents to be read.
    for part in PurePosixPath(path).parts:
        if part != ".env.example" and (
            part == ".env"
            or part.startswith(".env.")
            or part.endswith(".env")
            or ".env." in part
        ):
            raise MetadataValidationError("secret_input_reference_forbidden")
    raw = _metadata_git(repo_root, "ls-tree", "-z", revision, "--", path)
    entries = [item for item in raw.split(b"\0") if item]
    if len(entries) != 1:
        raise MetadataValidationError("input_reference_missing_or_nonregular")
    descriptor, actual_path = entries[0].split(b"\t", 1)
    mode, kind, oid = descriptor.decode("ascii").split(" ")
    if (
        actual_path.decode("utf-8", "surrogateescape") != path
        or kind != "blob"
        or mode not in {"100644", "100755"}
        or _HEX40.fullmatch(oid) is None
    ):
        raise MetadataValidationError("input_reference_missing_or_nonregular")
    return mode, oid


def _metadata_blob(repo_root: Path, oid: str, limit: int) -> bytes:
    size = int(_metadata_git(repo_root, "cat-file", "-s", oid))
    if size < 0 or size > limit:
        raise MetadataValidationError("immutable_blob_exceeds_validation_budget")
    raw = _metadata_git(repo_root, "cat-file", "blob", oid)
    if len(raw) != size:
        raise MetadataValidationError("immutable_blob_size_mismatch")
    return raw


def _metadata_json(raw: bytes) -> dict[str, object]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise MetadataValidationError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise MetadataValidationError("nonfinite_json_number")

    def finite_float(token):
        number = float(token)
        if not math.isfinite(number):
            raise MetadataValidationError("nonfinite_json_number")
        return number

    try:
        result = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=invalid_constant,
            parse_float=finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise MetadataValidationError("invalid_receipt_json") from exc
    if not isinstance(result, dict):
        raise MetadataValidationError("receipt_json_object_required")
    return result


def _metadata_diff(left, right, path=()):
    if type(left) is not type(right):
        raise MetadataValidationError("receipt_type_changed")
    if isinstance(left, dict):
        if left.keys() != right.keys():
            raise MetadataValidationError("receipt_keys_changed")
        return [
            leaf
            for key in left
            for leaf in _metadata_diff(left[key], right[key], (*path, key))
        ]
    if isinstance(left, list):
        if len(left) != len(right):
            raise MetadataValidationError("receipt_array_shape_changed")
        return [
            leaf
            for index, (a, b) in enumerate(zip(left, right))
            for leaf in _metadata_diff(a, b, (*path, index))
        ]
    if isinstance(left, float):
        return [] if left.hex() == right.hex() else [path]
    return [] if left == right else [path]


def _metadata_timestamp(value) -> None:
    if not isinstance(value, str) or len(value) > 64:
        raise MetadataValidationError("metadata_timestamp_invalid")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MetadataValidationError("metadata_timestamp_invalid") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != timezone.utc.utcoffset(
        None
    ):
        raise MetadataValidationError("metadata_timestamp_must_be_utc")


def validate_protected_metadata_changes(
    *, base: str, head: str, repo_root: Path, protected_paths: Iterable[str]
) -> dict[str, object]:
    """Validate immutable finite software metadata; never qualify physical data.

    All unknown protected paths, unsupported Git modes and indeterminate shallow
    ancestry remain blocked. No PR number, fixed source SHA, environment approval,
    broad metadata suffix, or generic checksum exception is accepted.
    """
    result: dict[str, object] = {
        "schema_version": "native-protected-software-metadata.v1",
        "status": "blocked",
        "contract_pass": False,
        "validated_receipts": [],
        "blockers": [],
        "authority_boundary": _METADATA_BOUNDARY,
    }
    try:
        _metadata_commit(repo_root, base)
        _metadata_commit(repo_root, head)
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base, head],
            cwd=repo_root,
            check=False,
            capture_output=True,
        )
        if ancestry.returncode:
            raise MetadataValidationError("base_ancestry_not_proven")
        # --no-renames exposes both old and new names of a protected rename.
        raw = _metadata_git(
            repo_root, "diff", "--name-only", "--no-renames", "-z", base, head
        )
        changed = [p.decode("utf-8", "surrogateescape") for p in raw.split(b"\0") if p]
        if any(_normalize_path(path) != path for path in changed):
            raise MetadataValidationError("noncanonical_changed_git_path")
        actual_protected = classify_paths(changed)["protected_evidence_paths"]
        requested = sorted(set(protected_paths))
        if requested != actual_protected or not requested:
            raise MetadataValidationError("protected_diff_inventory_mismatch")
        if any(p not in METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS for p in requested):
            raise MetadataValidationError("unknown_protected_path")
        for path in requested:
            base_ref = _metadata_reference(repo_root, base, path)
            head_ref = _metadata_reference(repo_root, head, path)
            if base_ref[0] != "100644" or head_ref[0] != "100644":
                raise MetadataValidationError("receipt_mode_must_be_regular_100644")
            before = _metadata_json(
                _metadata_blob(repo_root, base_ref[1], _MAX_RECEIPT_BYTES)
            )
            after = _metadata_json(
                _metadata_blob(repo_root, head_ref[1], _MAX_RECEIPT_BYTES)
            )
            changed_leaves = _metadata_diff(before, after)
            allowed = {("generated_at",), ("source_commit_sha",)} | {
                ("input_checksums", key)
                for key in METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]
            }
            if any(leaf not in allowed for leaf in changed_leaves):
                raise MetadataValidationError("nonmetadata_receipt_value_changed")
            _metadata_timestamp(after.get("generated_at"))
            producer = after.get("source_commit_sha")
            _metadata_commit(repo_root, producer)
            producer_ancestry = subprocess.run(
                ["git", "merge-base", "--is-ancestor", producer, head],
                cwd=repo_root,
                check=False,
                capture_output=True,
            )
            if producer_ancestry.returncode:
                raise MetadataValidationError("receipt_source_ancestry_not_proven")
            old_inputs = before.get("input_checksums")
            new_inputs = after.get("input_checksums")
            if not isinstance(old_inputs, dict) or not isinstance(new_inputs, dict):
                raise MetadataValidationError("input_checksum_objects_required")
            if old_inputs.keys() != new_inputs.keys():
                raise MetadataValidationError("input_checksum_key_set_changed")
            references = []
            for source_path, checksum in new_inputs.items():
                if not isinstance(checksum, str) or _SHA256.fullmatch(checksum) is None:
                    raise MetadataValidationError("input_checksum_invalid")
                old_ref = _metadata_reference(repo_root, base, source_path)
                new_ref = _metadata_reference(repo_root, head, source_path)
                if old_inputs[source_path] != checksum:
                    if source_path not in METADATA_ONLY_SOFTWARE_CHECKSUM_KEYS[path]:
                        raise MetadataValidationError(
                            "unapproved_input_checksum_changed"
                        )
                    raw_input = _metadata_blob(
                        repo_root, new_ref[1], _MAX_SOFTWARE_INPUT_BYTES
                    )
                    if raw_input.startswith(
                        b"version https://git-lfs.github.com/spec/v1\n"
                    ):
                        raise MetadataValidationError(
                            "changed_software_input_is_lfs_pointer"
                        )
                    if "sha256:" + hashlib.sha256(raw_input).hexdigest() != checksum:
                        raise MetadataValidationError(
                            "changed_software_checksum_head_bytes_mismatch"
                        )
                    binding = "changed_software_exact_head_bytes"
                else:
                    if old_ref != new_ref:
                        raise MetadataValidationError(
                            "unchanged_checksum_reference_blob_changed"
                        )
                    # No content read, even for LFS pointers or protected inputs.
                    binding = "unchanged_reference_git_blob_identity_only"
                references.append(
                    {
                        "path": source_path,
                        "mode": new_ref[0],
                        "blob_sha": new_ref[1],
                        "binding": binding,
                    }
                )
            result["validated_receipts"].append(
                {
                    "path": path,
                    "base_blob_sha": base_ref[1],
                    "head_blob_sha": head_ref[1],
                    "source_commit_sha": producer,
                    "changed_leaves": [list(leaf) for leaf in changed_leaves],
                    "input_references": references,
                }
            )
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        OverflowError,
        RecursionError,
    ) as exc:
        result["blockers"] = [
            str(exc)
            if isinstance(exc, MetadataValidationError)
            else "metadata_validation_indeterminate"
        ]
        return result
    result["status"] = "pass"
    result["contract_pass"] = True
    return result


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
        "workstation_package",
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
            + json.dumps(
                payload["changed_paths"], ensure_ascii=True, separators=(",", ":")
            )
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

    metadata_pass = False
    if args.fail_protected_evidence and payload["protected_evidence"]:
        if args.paths is not None:
            validation = {
                "status": "blocked",
                "contract_pass": False,
                "blockers": ["immutable_git_diff_required_instead_of_path_override"],
                "authority_boundary": _METADATA_BOUNDARY,
            }
        else:
            validation = validate_protected_metadata_changes(
                base=args.base,
                head=args.head,
                repo_root=args.repo_root.resolve(),
                protected_paths=payload["protected_evidence_paths"],
            )
        payload["metadata_only_validation"] = validation
        metadata_pass = validation["contract_pass"] is True
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    if args.github_output is not None:
        _write_github_outputs(args.github_output, payload)
    if (
        args.fail_protected_evidence
        and payload["protected_evidence"]
        and not metadata_pass
    ):
        print(
            "native CI scope includes unvalidated protected evidence: "
            + ", ".join(payload["protected_evidence_paths"]),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
