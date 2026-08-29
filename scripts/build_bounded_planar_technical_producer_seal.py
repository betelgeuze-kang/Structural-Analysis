#!/usr/bin/env python3
"""Seal one unprivileged bounded-planar producer artifact for isolated signing.

The producer has no OIDC or attestation permission.  This script snapshots the
full tracked product package plus the family control plane, proves the checkout
is the exact clean commit tree, verifies the hash-locked OpenSees wheels, and
creates a manifest of every candidate byte.  A separate no-checkout job replays
these checks before it is allowed to attest the immutable handoff.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, NoReturn


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from bounded_planar_runtime_lock import (  # noqa: E402
    EXPECTED_WHEEL_HASHES,
    EXPECTED_WHEEL_SOURCES,
    validate_requirements_text,
)
from strict_json import StrictJSONError, strict_json_load_path  # noqa: E402


SCHEMA_VERSION = "bounded-planar-technical-producer-seal.v1"
ZERO_HASH = "sha256:" + "0" * 64
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")

FAMILY_PATHS = {
    "linear": {
        "workflow": ".github/workflows/bounded-planar-opensees-technical.yml",
        "builder": "scripts/build_bounded_planar_external_linear_case_package.py",
        "ingest": "scripts/ingest_bounded_planar_external_linear_results.py",
        "schemas": (
            "src/structural_analysis/schemas/bounded_planar_external_linear_case_package_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_opensees_linear_result_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_linear_execution_receipt_v1.schema.json",
        ),
    },
    "negative": {
        "workflow": ".github/workflows/bounded-planar-negative-opensees-technical.yml",
        "builder": "scripts/build_bounded_planar_external_negative_case_package.py",
        "ingest": "scripts/ingest_bounded_planar_external_negative_results.py",
        "dependencies": (
            "scripts/build_bounded_planar_external_linear_case_package.py",
        ),
        "schemas": (
            "src/structural_analysis/schemas/bounded_planar_external_negative_case_package_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_opensees_negative_result_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_negative_execution_receipt_v1.schema.json",
        ),
    },
    "scaling": {
        "workflow": ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
        "builder": "scripts/build_bounded_planar_external_scaling_case_package.py",
        "ingest": "scripts/ingest_bounded_planar_external_scaling_results.py",
        "dependencies": (
            "scripts/build_bounded_planar_external_linear_case_package.py",
        ),
        "schemas": (
            "src/structural_analysis/schemas/bounded_planar_external_scaling_case_package_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_opensees_scaling_result_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_scaling_execution_receipt_v1.schema.json",
        ),
    },
    "modal_buckling": {
        "workflow": ".github/workflows/bounded-planar-modal-buckling-technical.yml",
        "builder": "scripts/build_bounded_planar_external_modal_buckling_case_package.py",
        "ingest": "scripts/ingest_bounded_planar_external_modal_buckling_results.py",
        "runners": ("scripts/run_bounded_planar_external_modal_buckling_case.py",),
        "schemas": (
            "src/structural_analysis/schemas/bounded_planar_external_modal_buckling_case_package_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_modal_buckling_result_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_modal_buckling_execution_receipt_v1.schema.json",
        ),
    },
    "nonlinear_material_recovery": {
        "workflow": ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
        "builder": "scripts/build_bounded_planar_external_nonlinear_material_recovery_case_package.py",
        "ingest": "scripts/ingest_bounded_planar_external_nonlinear_material_recovery_results.py",
        "runners": (
            "scripts/run_bounded_planar_external_nonlinear_material_recovery_case.py",
        ),
        "schemas": (
            "src/structural_analysis/schemas/bounded_planar_external_nonlinear_material_recovery_case_package_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_opensees_nonlinear_material_recovery_result_v1.schema.json",
            "src/structural_analysis/schemas/bounded_planar_external_nonlinear_material_recovery_execution_receipt_v1.schema.json",
        ),
    },
}

COMMON_SOURCE_PATHS = (
    ".github/workflows/bounded-planar-sealed-technical-attestor.yml",
    "canonical/requirements-cp312-manylinux2014-x86_64.lock",
    "pyproject.toml",
    "scripts/bounded_planar_runtime_lock.py",
    "scripts/strict_json.py",
    "scripts/build_bounded_planar_technical_producer_seal.py",
)

OPENSEES_APT_RUNTIME_BLOCKER = (
    "opensees_blas_lapack_apt_transitive_bytes_not_pre_execution_hash_locked"
)

MANDATORY_RUNTIME_BLOCKERS = {
    "linear": (OPENSEES_APT_RUNTIME_BLOCKER,),
    "negative": (OPENSEES_APT_RUNTIME_BLOCKER,),
    "scaling": (OPENSEES_APT_RUNTIME_BLOCKER,),
    "modal_buckling": ("calculix_apt_transitive_bytes_not_pre_execution_hash_locked",),
    "nonlinear_material_recovery": (OPENSEES_APT_RUNTIME_BLOCKER,),
}


class ProducerSealError(ValueError):
    pass


def _fail(code: str) -> NoReturn:
    raise ProducerSealError(code)


def _run_git(*args: str, repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        _fail("producer_source_git_query_failed")
    return completed.stdout.strip()


def execution_source_paths(repo_root: Path, family_id: str) -> list[str]:
    """Return the conservative tracked source closure for one producer.

    Python imports are dynamic, so a hand-maintained import list is not an
    adequate security boundary.  The closure intentionally includes every
    tracked product-package file in addition to the family control plane.
    """

    family = FAMILY_PATHS.get(family_id)
    if family is None:
        _fail("producer_family_invalid")
    tracked_product_files = {
        line
        for line in _run_git(
            "ls-files", "--", "src/structural_analysis", repo_root=repo_root
        ).splitlines()
        if line
    }
    return sorted(
        {
            *COMMON_SOURCE_PATHS,
            str(family["workflow"]),
            str(family["builder"]),
            str(family["ingest"]),
            *(str(path) for path in family.get("dependencies", ())),
            *(str(path) for path in family.get("runners", ())),
            *(str(path) for path in family["schemas"]),
            *tracked_product_files,
        }
    )


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_binding(repo_root: Path, path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    try:
        relative = resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        _fail("producer_candidate_file_outside_repository")
    if path.is_symlink() or not resolved.is_file():
        _fail("producer_candidate_file_invalid")
    raw = resolved.read_bytes()
    return {"path": relative, "file_sha256": _hash_bytes(raw), "size": len(raw)}


def _external_runtime_binding(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or not resolved.is_file():
        _fail("producer_runtime_asset_invalid")
    raw = resolved.read_bytes()
    return {
        "filename": resolved.name,
        "file_sha256": _hash_bytes(raw),
        "size": len(raw),
    }


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _safe_relative(repo_root: Path, value: str, code: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != value:
        _fail(code)
    candidate = repo_root / relative
    cursor = repo_root
    for part in relative.parts:
        cursor /= part
        if cursor.is_symlink():
            _fail(code)
    try:
        candidate.resolve(strict=True).relative_to(repo_root.resolve())
    except (OSError, ValueError):
        _fail(code)
    return candidate


def _external_runtime_dir(repo_root: Path, value: Path) -> Path:
    if not value.is_absolute():
        _fail("producer_wheel_dir_must_be_external")
    try:
        resolved = value.resolve(strict=True)
    except OSError:
        _fail("producer_wheel_dir_invalid")
    if not resolved.is_dir() or value.is_symlink():
        _fail("producer_wheel_dir_invalid")
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return resolved
    _fail("producer_wheel_dir_must_be_external")


def _tree_files(
    repo_root: Path, roots: list[Path], excluded: Path
) -> list[dict[str, Any]]:
    files: dict[str, dict[str, Any]] = {}
    excluded_resolved = excluded.resolve()
    for root in roots:
        if root.is_symlink() or not root.is_dir():
            _fail("producer_candidate_root_invalid")
        for path in root.rglob("*"):
            if path.is_symlink():
                _fail("producer_candidate_symlink_forbidden")
            if path.is_dir():
                continue
            if path.resolve() == excluded_resolved:
                continue
            binding = _file_binding(repo_root, path)
            if binding["path"] in files:
                _fail("producer_candidate_duplicate_path")
            if path.suffix == ".json":
                try:
                    strict_json_load_path(path)
                except StrictJSONError as exc:
                    raise ProducerSealError(
                        f"producer_candidate_json_invalid:{binding['path']}"
                    ) from exc
            files[binding["path"]] = binding
    return [files[key] for key in sorted(files)]


def build_seal(
    *,
    repo_root: Path,
    family_id: str,
    receipt_path: Path,
    package_dir: Path,
    wheel_dir: Path,
    out_path: Path,
    source_commit_sha: str,
    source_tree_sha: str,
    repository: str,
    run_id: str,
    run_attempt: str,
    workflow_sha: str,
    candidate_artifact_name: str,
    runtime_blockers: list[str],
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    family = FAMILY_PATHS.get(family_id)
    if family is None:
        _fail("producer_family_invalid")
    if not SHA1.fullmatch(source_commit_sha) or workflow_sha != source_commit_sha:
        _fail("producer_source_commit_invalid")
    if not SHA1.fullmatch(source_tree_sha):
        _fail("producer_source_tree_invalid")
    if _run_git("rev-parse", "HEAD", repo_root=repo_root) != source_commit_sha:
        _fail("producer_source_commit_mismatch")
    if _run_git("rev-parse", "HEAD^{tree}", repo_root=repo_root) != source_tree_sha:
        _fail("producer_source_tree_mismatch")
    if _run_git(
        "status", "--porcelain=v1", "--untracked-files=all", repo_root=repo_root
    ):
        _fail("producer_tracked_source_dirty")
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or not re.fullmatch(
        r"[1-9][0-9]*", run_attempt
    ):
        _fail("producer_workflow_run_identity_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        _fail("producer_repository_invalid")

    receipt = _safe_relative(
        repo_root, receipt_path.as_posix(), "producer_receipt_invalid"
    )
    package = _safe_relative(
        repo_root, package_dir.as_posix(), "producer_package_invalid"
    )
    wheels = _external_runtime_dir(repo_root, wheel_dir)
    out = repo_root / out_path
    if out.is_symlink():
        _fail("producer_seal_output_invalid")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        out.resolve().relative_to(receipt.parent.resolve())
    except ValueError:
        _fail("producer_seal_output_invalid")

    loaded_receipt = strict_json_load_path(receipt)
    if not isinstance(loaded_receipt, dict):
        _fail("producer_receipt_invalid")
    claims = loaded_receipt.get("claims")
    if (
        loaded_receipt.get("source_commit_sha") != source_commit_sha
        or loaded_receipt.get("technical_contract_pass") is not True
        or not isinstance(claims, dict)
        or claims.get("independent_operator_attested") is not False
        or claims.get("legal_use_approved") is not False
        or any(
            claims.get(key) is True
            for key in (
                "verification_level_2",
                "design_authority",
                "commercial_equivalence",
                "release_readiness",
            )
        )
    ):
        _fail("producer_receipt_authority_invalid")

    requirements = package / "requirements.txt"
    try:
        requirements_text = requirements.read_text(encoding="utf-8")
        validate_requirements_text(requirements_text)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ProducerSealError("producer_python_runtime_lock_invalid") from exc

    expected_wheel_names = {
        "openseespy": "openseespy-3.7.1.2-py3-none-any.whl",
        "openseespylinux": "openseespylinux-3.7.1.2-py3-none-any.whl",
    }
    wheel_assets: list[dict[str, Any]] = []
    actual_wheel_names = sorted(path.name for path in wheels.glob("*.whl"))
    if actual_wheel_names != sorted(expected_wheel_names.values()):
        _fail("producer_python_runtime_wheel_set_invalid")
    for package_name, filename in sorted(expected_wheel_names.items()):
        binding = _external_runtime_binding(wheels / filename)
        if binding["file_sha256"] != "sha256:" + EXPECTED_WHEEL_HASHES[package_name]:
            _fail("producer_python_runtime_wheel_hash_invalid")
        binding["package"] = package_name
        binding["version"] = "3.7.1.2"
        binding["source"] = EXPECTED_WHEEL_SOURCES[package_name]
        wheel_assets.append(binding)

    source_paths = execution_source_paths(repo_root, family_id)
    snapshot_root = receipt.parent / "source-snapshot"
    if snapshot_root.exists():
        _fail("producer_source_snapshot_already_exists")
    source_files: list[dict[str, Any]] = []
    for relative in source_paths:
        source = _safe_relative(repo_root, relative, "producer_source_file_invalid")
        destination = snapshot_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        binding = _file_binding(repo_root, source)
        binding["git_blob_sha1"] = hashlib.sha1(
            f"blob {binding['size']}\0".encode("ascii") + source.read_bytes()
        ).hexdigest()
        binding["snapshot_path"] = destination.relative_to(repo_root).as_posix()
        source_files.append(binding)

    candidate_files = _tree_files(repo_root, [receipt.parent, package], out)
    product_runtime_lock = snapshot_root / (
        "canonical/requirements-cp312-manylinux2014-x86_64.lock"
    )
    blockers = sorted(
        {
            *runtime_blockers,
            *MANDATORY_RUNTIME_BLOCKERS.get(family_id, ()),
        }
    )
    runtime_complete = not blockers
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "family_id": family_id,
        "source_binding": {
            "source_commit_sha": source_commit_sha,
            "source_tree_sha": source_tree_sha,
            "workflow_sha": workflow_sha,
            "tracked_tree_clean": True,
            "source_scope": ("full_tracked_product_package_plus_family_control_plane"),
            "tracked_product_file_count": sum(
                row["path"].startswith("src/structural_analysis/")
                for row in source_files
            ),
            "tracked_product_python_count": sum(
                row["path"].startswith("src/structural_analysis/")
                and row["path"].endswith(".py")
                for row in source_files
            ),
            "source_files": source_files,
        },
        "execution_binding": {
            "repository": repository,
            "workflow_path": family["workflow"],
            "run_id": int(run_id),
            "run_attempt": int(run_attempt),
            "runner_environment": "github-hosted",
            "candidate_artifact_name": candidate_artifact_name,
        },
        "runtime_binding": {
            "product_runtime_lock": _file_binding(repo_root, product_runtime_lock),
            "python_requirements": _file_binding(repo_root, requirements),
            "wheel_assets": wheel_assets,
            "all_external_runtime_assets_pre_execution_hash_locked": runtime_complete,
            "runtime_asset_bytes_attached": False,
            "runtime_asset_metadata_sealed": True,
            "technical_authority_eligible": runtime_complete,
            "blockers": blockers,
        },
        "technical_receipt": _file_binding(repo_root, receipt),
        "candidate_files": candidate_files,
        "claims": {
            "same_operator_technical_evidence_only": True,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "formal_promotion_receipt_attached": False,
            "verification_level_2": False,
            "design_authority": False,
            "commercial_equivalence": False,
            "release_readiness": False,
        },
        "artifact_hash": ZERO_HASH,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    return payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-id", required=True, choices=sorted(FAMILY_PATHS))
    parser.add_argument("--receipt-path", required=True, type=Path)
    parser.add_argument("--package-dir", required=True, type=Path)
    parser.add_argument("--wheel-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-tree-sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--candidate-artifact-name", required=True)
    parser.add_argument("--runtime-blocker", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    payload = build_seal(
        repo_root=ROOT,
        family_id=args.family_id,
        receipt_path=args.receipt_path,
        package_dir=args.package_dir,
        wheel_dir=args.wheel_dir,
        out_path=args.out,
        source_commit_sha=args.source_sha,
        source_tree_sha=args.source_tree_sha,
        repository=args.repository,
        run_id=args.run_id,
        run_attempt=args.run_attempt,
        workflow_sha=args.workflow_sha,
        candidate_artifact_name=args.candidate_artifact_name,
        runtime_blockers=args.runtime_blocker,
    )
    out = ROOT / args.out
    out.write_text(
        json.dumps(
            payload, allow_nan=False, ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"bounded planar producer seal: {payload['family_id']} | "
        f"runtime_locked={payload['runtime_binding']['technical_authority_eligible']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
