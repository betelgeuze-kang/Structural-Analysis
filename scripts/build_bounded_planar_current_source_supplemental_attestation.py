#!/usr/bin/env python3
"""Aggregate five exact-source, Sigstore-verified supplemental V&V runs.

The child technical receipts intentionally cannot claim freshness before they are
attested.  This downstream receipt is the narrow trust transition: it requires
the exact GitHub workflow run, exact signed receipt bytes, the Sigstore bundle,
and reruns ``gh attestation verify`` itself on every authoritative validation.
The retained verification JSON is an audit cache and never the trust source.
It grants current-source technical credit only.  It never grants independent
operator, legal, promotion, Level 2, design, commercial, or release authority.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from types import ModuleType
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SRC_ROOT = ROOT / "src"
for search_root in (SCRIPT_DIR, SRC_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import build_bounded_planar_external_linear_case_package as linear_package  # noqa: E402
import build_bounded_planar_external_modal_buckling_case_package as modal_package  # noqa: E402
import build_bounded_planar_external_negative_case_package as negative_package  # noqa: E402
import build_bounded_planar_external_nonlinear_material_recovery_case_package as nonlinear_package  # noqa: E402
import build_bounded_planar_external_scaling_case_package as scaling_package  # noqa: E402
import ingest_bounded_planar_external_linear_results as linear_ingest  # noqa: E402
import ingest_bounded_planar_external_modal_buckling_results as modal_ingest  # noqa: E402
import ingest_bounded_planar_external_negative_results as negative_ingest  # noqa: E402
import ingest_bounded_planar_external_nonlinear_material_recovery_results as nonlinear_ingest  # noqa: E402
import ingest_bounded_planar_external_scaling_results as scaling_ingest  # noqa: E402


SCHEMA_VERSION = "bounded-planar-current-source-supplemental-attestation.v2"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_current_source_supplemental_attestation_v2.schema.json"
)
DEFAULT_INPUT_ROOT = Path(
    ".ci/product-state-inputs/bounded-planar-supplemental-attestations"
)
DEFAULT_OUT = Path(
    ".ci/product-state-inputs/current-same-operator-supplemental/receipt.json"
)
RECEIPT_NAME = "receipt.json"
ZERO_HASH = "sha256:" + "0" * 64
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
LIVE_ATTESTATION_VERIFY_TIMEOUT_SECONDS = 120


class CurrentSourceSupplementalAttestationError(ValueError):
    """Stable fail-closed error for the attested supplemental aggregation."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise CurrentSourceSupplementalAttestationError(code)


@dataclass(frozen=True)
class Family:
    family_id: str
    workflow_path: str
    workflow_name: str
    artifact_prefix: str
    artifact_receipt_path: str
    package_module: ModuleType
    ingest_module: ModuleType
    receipt_schema_version: str
    case_ids: tuple[str, ...]
    pass_key: str
    model_descriptor_key: str
    runner_descriptor_key: str

    @property
    def artifact_bundle_path(self) -> str:
        return self.artifact_receipt_path.replace(
            "technical-receipt.json", "technical-receipt.sigstore.json"
        )

    @property
    def results_path(self) -> str:
        return str(Path(self.artifact_receipt_path).parent / "results")


FAMILIES = (
    Family(
        family_id="linear",
        workflow_path=".github/workflows/bounded-planar-opensees-technical.yml",
        workflow_name="Bounded Planar OpenSees Technical Execution",
        artifact_prefix="bounded-planar-opensees-technical",
        artifact_receipt_path=(
            ".ci/bounded-planar-opensees/technical-receipt.json"
        ),
        package_module=linear_package,
        ingest_module=linear_ingest,
        receipt_schema_version=(
            "bounded-planar-external-linear-execution-receipt.v1"
        ),
        case_ids=(
            "bounded_planar_linear_portal",
            "bounded_planar_linear_multistory",
        ),
        pass_key="technical_comparison_pass",
        model_descriptor_key="model_ir",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="negative",
        workflow_path=(
            ".github/workflows/bounded-planar-negative-opensees-technical.yml"
        ),
        workflow_name="Bounded Planar Negative OpenSees Technical Execution",
        artifact_prefix="bounded-planar-negative-opensees",
        artifact_receipt_path=(
            ".ci/bounded-planar-negative-opensees/technical-receipt.json"
        ),
        package_module=negative_package,
        ingest_module=negative_ingest,
        receipt_schema_version=(
            "bounded-planar-external-negative-execution-receipt.v1"
        ),
        case_ids=(
            "bounded_planar_negative_mechanism",
            "bounded_planar_negative_singular",
            "bounded_planar_negative_invalid_geometry",
        ),
        pass_key="technical_rejection_pass",
        model_descriptor_key="model_ir",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="scaling",
        workflow_path=(
            ".github/workflows/bounded-planar-scaling-opensees-technical.yml"
        ),
        workflow_name="Bounded Planar Scaling OpenSees Technical Execution",
        artifact_prefix="bounded-planar-scaling-opensees",
        artifact_receipt_path=(
            ".ci/bounded-planar-scaling-opensees/technical-receipt.json"
        ),
        package_module=scaling_package,
        ingest_module=scaling_ingest,
        receipt_schema_version=(
            "bounded-planar-external-scaling-execution-receipt.v1"
        ),
        case_ids=(
            "bounded_planar_scaling_unit_invariance",
            "bounded_planar_scaling_characteristic_length_invariance",
        ),
        pass_key="technical_comparison_pass",
        model_descriptor_key="model_pair",
        runner_descriptor_key="opensees_runner",
    ),
    Family(
        family_id="modal_buckling",
        workflow_path=(
            ".github/workflows/bounded-planar-modal-buckling-technical.yml"
        ),
        workflow_name="Bounded Planar Modal Buckling Technical Execution",
        artifact_prefix="bounded-planar-modal-buckling",
        artifact_receipt_path=(
            ".ci/bounded-planar-modal-buckling/technical-receipt.json"
        ),
        package_module=modal_package,
        ingest_module=modal_ingest,
        receipt_schema_version=(
            "bounded-planar-external-modal-buckling-execution-receipt.v1"
        ),
        case_ids=(
            "bounded_planar_modal_rigid_mode",
            "bounded_planar_modal_repeated_mode",
            "bounded_planar_buckling_portal",
        ),
        pass_key="technical_contract_pass",
        model_descriptor_key="model",
        runner_descriptor_key="external_runner",
    ),
    Family(
        family_id="nonlinear_material_recovery",
        workflow_path=(
            ".github/workflows/"
            "bounded-planar-nonlinear-material-recovery-technical.yml"
        ),
        workflow_name=(
            "Bounded Planar Nonlinear Material Recovery Technical Execution"
        ),
        artifact_prefix="bounded-planar-nonlinear-material-recovery",
        artifact_receipt_path=(
            ".ci/bounded-planar-nonlinear-material-recovery/"
            "technical-receipt.json"
        ),
        package_module=nonlinear_package,
        ingest_module=nonlinear_ingest,
        receipt_schema_version=(
            "bounded-planar-external-nonlinear-material-recovery-"
            "execution-receipt.v1"
        ),
        case_ids=(
            "bounded_planar_p_delta",
            "bounded_planar_snap_through",
            "bounded_planar_steel_yield",
            "bounded_planar_rc_fiber",
            "bounded_planar_section_recovery",
            "bounded_planar_fiber_recovery",
        ),
        pass_key="technical_comparison_pass",
        model_descriptor_key="model",
        runner_descriptor_key="external_runner",
    ),
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _hash_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    return _hash_bytes(_canonical_bytes(body))


def _load_json(path: Path, code: str) -> dict[str, Any] | list[Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurrentSourceSupplementalAttestationError(code) from exc
    if not isinstance(value, (dict, list)):
        _fail(code)
    return value


def _resolved(repo_root: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (repo_root / path).resolve()


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _safe_file(root: Path, relative: str, code: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.as_posix() != relative:
        _fail(code)
    path = root / raw
    if path.is_symlink():
        _fail(code)
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise CurrentSourceSupplementalAttestationError(code) from exc
    if not resolved.is_file():
        _fail(code)
    return resolved


def _safe_directory(root: Path, relative: str, code: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts or raw.as_posix() != relative:
        _fail(code)
    path = root / raw
    if path.is_symlink():
        _fail(code)
    try:
        root_resolved = root.resolve(strict=True)
        resolved = path.resolve(strict=True)
        resolved.relative_to(root_resolved)
    except (OSError, ValueError) as exc:
        raise CurrentSourceSupplementalAttestationError(code) from exc
    if not resolved.is_dir():
        _fail(code)
    return resolved


def _parse_timestamp(value: object, code: str) -> datetime:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CurrentSourceSupplementalAttestationError(code) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _fail(code)
    return parsed


def _receipt_validator(
    family: Family,
    receipt: dict[str, Any],
    *,
    repo_root: Path,
) -> None:
    validator = getattr(family.ingest_module, "_validate_receipt", None)
    if validator is None:
        _fail(f"supplemental_receipt_validator_missing:{family.family_id}")
    try:
        validator(receipt, repo_root)
    except Exception as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_receipt_contract_invalid:{family.family_id}"
        ) from exc


def _package_descriptors(
    family: Family, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    descriptors: list[dict[str, Any]] = []
    for key in (
        "operator_readme",
        "python_requirements",
        "execution_workflow",
        "external_result_schema",
    ):
        descriptor = manifest.get(key)
        if not isinstance(descriptor, dict):
            _fail(f"supplemental_package_descriptor_invalid:{family.family_id}")
        descriptors.append(descriptor)
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail(f"supplemental_package_case_set_invalid:{family.family_id}")
    for case in cases:
        if not isinstance(case, dict):
            _fail(f"supplemental_package_case_set_invalid:{family.family_id}")
        for key in (
            family.model_descriptor_key,
            family.runner_descriptor_key,
            "product_result",
        ):
            descriptor = case.get(key)
            if not isinstance(descriptor, dict):
                _fail(
                    f"supplemental_package_case_descriptor_invalid:"
                    f"{family.family_id}"
                )
            descriptors.append(descriptor)
    return descriptors


def _validate_package(
    *,
    repo_root: Path,
    artifact_root: Path,
    family: Family,
    source_commit_sha: str,
) -> tuple[Path, dict[str, Any], dict[str, dict[str, Any]]]:
    package_root = _safe_directory(
        artifact_root,
        family.package_module.DEFAULT_OUT_DIR.as_posix(),
        f"supplemental_package_root_invalid:{family.family_id}",
    )
    manifest_path = _safe_file(
        package_root,
        family.package_module.MANIFEST_NAME,
        f"supplemental_package_manifest_missing:{family.family_id}",
    )
    loaded = _load_json(
        manifest_path, f"supplemental_package_manifest_invalid:{family.family_id}"
    )
    if not isinstance(loaded, dict):
        _fail(f"supplemental_package_manifest_invalid:{family.family_id}")
    manifest = loaded
    try:
        family.package_module._validate_manifest(manifest, repo_root)
    except Exception as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_package_manifest_contract_invalid:{family.family_id}"
        ) from exc
    if manifest.get("source_commit_sha") != source_commit_sha:
        _fail(f"supplemental_package_source_mismatch:{family.family_id}")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or [
        str(row.get("case_id") or "") for row in cases if isinstance(row, dict)
    ] != list(family.case_ids):
        _fail(f"supplemental_package_case_set_invalid:{family.family_id}")

    expected_paths = {family.package_module.MANIFEST_NAME}
    for descriptor in _package_descriptors(family, manifest):
        relative = descriptor.get("path")
        if not isinstance(relative, str):
            _fail(f"supplemental_package_descriptor_invalid:{family.family_id}")
        path = _safe_file(
            package_root,
            relative,
            f"supplemental_package_file_invalid:{family.family_id}",
        )
        expected_paths.add(relative)
        if descriptor.get("file_sha256") != _file_hash(path):
            _fail(f"supplemental_package_file_hash_invalid:{family.family_id}")
        expected_artifact_hash = descriptor.get("artifact_hash")
        if expected_artifact_hash is not None:
            payload = _load_json(
                path, f"supplemental_package_json_invalid:{family.family_id}"
            )
            if not isinstance(payload, dict) or (
                expected_artifact_hash != _artifact_hash(payload)
            ):
                _fail(
                    f"supplemental_package_artifact_hash_invalid:"
                    f"{family.family_id}"
                )
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail(f"supplemental_package_file_set_invalid:{family.family_id}")

    workflow_descriptor = manifest["execution_workflow"]
    workflow_path = _safe_file(
        package_root,
        str(workflow_descriptor["path"]),
        f"supplemental_packaged_workflow_invalid:{family.family_id}",
    )
    repository_workflow = _safe_file(
        repo_root,
        family.workflow_path,
        f"supplemental_repository_workflow_invalid:{family.family_id}",
    )
    if (
        _file_hash(workflow_path) != _file_hash(repository_workflow)
        or workflow_descriptor["file_sha256"] != _file_hash(repository_workflow)
    ):
        _fail(f"supplemental_workflow_bytes_mismatch:{family.family_id}")
    return manifest_path, manifest, {
        str(row["case_id"]): row for row in cases if isinstance(row, dict)
    }


def _receipt_package_binding(
    family: Family, receipt: dict[str, Any]
) -> tuple[str, str]:
    if family.family_id == "modal_buckling":
        file_hash = receipt.get("package_manifest_file_sha256")
        artifact_hash = receipt.get("package_manifest_artifact_hash")
    else:
        binding = receipt.get("package_binding")
        if not isinstance(binding, dict):
            _fail(f"supplemental_receipt_package_binding_invalid:{family.family_id}")
        file_hash = binding.get("file_sha256")
        artifact_hash = binding.get("artifact_hash")
    if not isinstance(file_hash, str) or not isinstance(artifact_hash, str):
        _fail(f"supplemental_receipt_package_binding_invalid:{family.family_id}")
    return file_hash, artifact_hash


def _result_descriptor(
    family: Family, receipt_case: dict[str, Any]
) -> tuple[str, str, str, bool]:
    if family.family_id == "modal_buckling":
        path = receipt_case.get("result_path")
        file_hash = receipt_case.get("result_file_sha256")
        artifact_hash = receipt_case.get("result_artifact_hash")
        invoked = True
    else:
        result = receipt_case.get("external_result")
        if not isinstance(result, dict):
            _fail(f"supplemental_result_descriptor_invalid:{family.family_id}")
        path = result.get("path")
        file_hash = result.get("file_sha256")
        artifact_hash = result.get("artifact_hash")
        invoked = result.get("external_engine_invoked", True)
    if not all(isinstance(value, str) for value in (path, file_hash, artifact_hash)):
        _fail(f"supplemental_result_descriptor_invalid:{family.family_id}")
    if not isinstance(invoked, bool):
        _fail(f"supplemental_result_invocation_invalid:{family.family_id}")
    return str(path), str(file_hash), str(artifact_hash), invoked


def _validate_receipt_and_results(
    *,
    repo_root: Path,
    artifact_root: Path,
    family: Family,
    source_commit_sha: str,
) -> tuple[Path, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    receipt_path = _safe_file(
        artifact_root,
        family.artifact_receipt_path,
        f"supplemental_receipt_missing:{family.family_id}",
    )
    loaded = _load_json(
        receipt_path, f"supplemental_receipt_invalid:{family.family_id}"
    )
    if not isinstance(loaded, dict):
        _fail(f"supplemental_receipt_invalid:{family.family_id}")
    receipt = loaded
    _receipt_validator(family, receipt, repo_root=repo_root)
    claims = receipt.get("claims")
    if not isinstance(claims, dict) or not (
        receipt.get("schema_version") == family.receipt_schema_version
        and receipt.get("source_commit_sha") == source_commit_sha
        and receipt.get("technical_contract_pass") is True
        and claims.get("independent_operator_attested") is False
        and claims.get("legal_use_approved") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail(f"supplemental_receipt_claim_boundary_invalid:{family.family_id}")
    freshness_key = (
        "fresh_external_solver_execution"
        if family.family_id == "modal_buckling"
        else "fresh_current_source_external_execution"
    )
    if claims.get(freshness_key) is not False:
        _fail(f"supplemental_receipt_preattestation_invalid:{family.family_id}")

    manifest_path, manifest, manifest_cases = _validate_package(
        repo_root=repo_root,
        artifact_root=artifact_root,
        family=family,
        source_commit_sha=source_commit_sha,
    )
    package_file_hash, package_artifact_hash = _receipt_package_binding(
        family, receipt
    )
    if (
        package_file_hash != _file_hash(manifest_path)
        or package_artifact_hash != manifest.get("artifact_hash")
    ):
        _fail(f"supplemental_receipt_package_binding_invalid:{family.family_id}")

    receipt_cases = receipt.get("cases")
    if not isinstance(receipt_cases, list) or [
        str(row.get("case_id") or "")
        for row in receipt_cases
        if isinstance(row, dict)
    ] != list(family.case_ids):
        _fail(f"supplemental_receipt_case_set_invalid:{family.family_id}")
    results_root = _safe_directory(
        artifact_root,
        family.results_path,
        f"supplemental_results_root_invalid:{family.family_id}",
    )
    expected_names = {f"{case_id}.json" for case_id in family.case_ids}
    actual_names = {
        path.name for path in results_root.iterdir() if path.is_file()
    }
    if actual_names != expected_names:
        _fail(f"supplemental_result_file_set_invalid:{family.family_id}")

    case_rows: list[dict[str, Any]] = []
    for receipt_case in receipt_cases:
        if not isinstance(receipt_case, dict):
            _fail(f"supplemental_receipt_case_set_invalid:{family.family_id}")
        case_id = str(receipt_case["case_id"])
        if receipt_case.get(family.pass_key) is not True:
            _fail(f"supplemental_receipt_case_blocked:{case_id}")
        path_value, file_hash, result_artifact_hash, invoked = _result_descriptor(
            family, receipt_case
        )
        expected_result_path = (
            Path(family.results_path) / f"{case_id}.json"
        ).as_posix()
        if path_value != expected_result_path:
            _fail(f"supplemental_result_path_invalid:{case_id}")
        result_path = _safe_file(
            artifact_root,
            expected_result_path,
            f"supplemental_result_missing:{case_id}",
        )
        result_loaded = _load_json(
            result_path, f"supplemental_result_invalid:{case_id}"
        )
        if not isinstance(result_loaded, dict):
            _fail(f"supplemental_result_invalid:{case_id}")
        result = result_loaded
        if (
            _file_hash(result_path) != file_hash
            or result.get("artifact_hash") != result_artifact_hash
            or _artifact_hash(result) != result_artifact_hash
            or result.get("case_id") != case_id
        ):
            _fail(f"supplemental_result_binding_invalid:{case_id}")
        manifest_case = manifest_cases.get(case_id)
        if not isinstance(manifest_case, dict):
            _fail(f"supplemental_package_case_missing:{case_id}")
        model_hash = result.get(
            "source_model_file_sha256",
            result.get("source_model_pair_file_sha256"),
        )
        if (
            result.get("runner_file_sha256")
            != manifest_case[family.runner_descriptor_key]["file_sha256"]
            or model_hash
            != manifest_case[family.model_descriptor_key]["file_sha256"]
        ):
            _fail(f"supplemental_result_source_binding_invalid:{case_id}")
        if family.family_id == "negative":
            if result.get("external_engine_invoked") is not invoked:
                _fail(f"supplemental_result_invocation_invalid:{case_id}")
        elif invoked is not True:
            _fail(f"supplemental_result_invocation_invalid:{case_id}")
        case_rows.append(
            {
                "case_id": case_id,
                "technical_contract_pass": True,
                "verification_method": (
                    "external_solver_execution"
                    if invoked
                    else "independent_preflight"
                ),
                "external_engine_invoked": invoked,
                "result_path": _relative(repo_root, result_path),
                "result_file_sha256": file_hash,
                "result_artifact_hash": result_artifact_hash,
            }
        )
    return receipt_path, receipt, {
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_hash(manifest_path),
        "artifact_hash": str(manifest["artifact_hash"]),
    }, case_rows


def _validate_workflow_run(
    *,
    run_path: Path,
    family: Family,
    repository: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    loaded = _load_json(
        run_path, f"supplemental_workflow_run_invalid:{family.family_id}"
    )
    if not isinstance(loaded, dict):
        _fail(f"supplemental_workflow_run_invalid:{family.family_id}")
    run = loaded
    if not (
        isinstance(run.get("id"), int)
        and run["id"] > 0
        and isinstance(run.get("run_attempt"), int)
        and run["run_attempt"] > 0
        and run.get("name") == family.workflow_name
        and run.get("path") == family.workflow_path
        and run.get("event") in {"push", "workflow_dispatch"}
        and run.get("status") == "completed"
        and run.get("conclusion") == "success"
        and run.get("head_branch") == "main"
        and run.get("head_sha") == source_commit_sha
        and run.get("repository", {}).get("full_name") == repository
        and run.get("head_repository", {}).get("full_name") == repository
    ):
        _fail(f"supplemental_workflow_run_contract_invalid:{family.family_id}")
    started = _parse_timestamp(
        run.get("run_started_at"),
        f"supplemental_workflow_run_timestamp_invalid:{family.family_id}",
    )
    completed = _parse_timestamp(
        run.get("updated_at"),
        f"supplemental_workflow_run_timestamp_invalid:{family.family_id}",
    )
    if completed < started:
        _fail(f"supplemental_workflow_run_timestamp_invalid:{family.family_id}")
    return run


def _run_live_attestation_verification(
    *,
    repo_root: Path,
    family: Family,
    repository: str,
    source_commit_sha: str,
    receipt_path: Path,
    bundle_path: Path,
) -> list[Any]:
    """Run the cryptographic verifier; cached JSON is never authority."""

    command = [
        "gh",
        "attestation",
        "verify",
        str(receipt_path),
        "--repo",
        repository,
        "--bundle",
        str(bundle_path),
        "--signer-workflow",
        f"{repository}/{family.workflow_path}",
        "--signer-digest",
        source_commit_sha,
        "--source-digest",
        source_commit_sha,
        "--source-ref",
        "refs/heads/main",
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=LIVE_ATTESTATION_VERIFY_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_live_attestation_verifier_unavailable:{family.family_id}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_live_attestation_verification_timeout:{family.family_id}"
        ) from exc
    except OSError as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_live_attestation_verifier_unavailable:{family.family_id}"
        ) from exc
    if completed.returncode != 0:
        _fail(f"supplemental_live_attestation_verification_failed:{family.family_id}")
    try:
        loaded = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CurrentSourceSupplementalAttestationError(
            f"supplemental_live_attestation_verification_invalid:{family.family_id}"
        ) from exc
    if not isinstance(loaded, list) or len(loaded) != 1:
        _fail(f"supplemental_live_attestation_verification_invalid:{family.family_id}")
    return loaded


def _validated_verification_document(
    *,
    verification_loaded: object,
    bundle_loaded: dict[str, Any],
    family: Family,
    repository: str,
    source_commit_sha: str,
    run: dict[str, Any],
    receipt_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not (
        isinstance(verification_loaded, list) and len(verification_loaded) == 1
    ):
        _fail(f"supplemental_attestation_verification_invalid:{family.family_id}")
    row = verification_loaded[0]
    if not isinstance(row, dict):
        _fail(f"supplemental_attestation_verification_invalid:{family.family_id}")
    attestation = row.get("attestation")
    result = row.get("verificationResult")
    if (
        not isinstance(attestation, dict)
        or attestation.get("bundle") != bundle_loaded
        or not isinstance(result, dict)
    ):
        _fail(f"supplemental_attestation_bundle_binding_invalid:{family.family_id}")

    signature = result.get("signature")
    certificate = signature.get("certificate") if isinstance(signature, dict) else None
    statement = result.get("statement")
    if not isinstance(certificate, dict) or not isinstance(statement, dict):
        _fail(f"supplemental_attestation_contract_invalid:{family.family_id}")
    workflow_uri = (
        f"https://github.com/{repository}/{family.workflow_path}"
        "@refs/heads/main"
    )
    source_uri = f"https://github.com/{repository}"
    invocation_uri = (
        f"{source_uri}/actions/runs/{run['id']}/attempts/{run['run_attempt']}"
    )
    if not (
        result.get("mediaType")
        == "application/vnd.dev.sigstore.verificationresult+json;version=0.1"
        and certificate.get("subjectAlternativeName") == workflow_uri
        and certificate.get("githubWorkflowSHA") == source_commit_sha
        and certificate.get("githubWorkflowName") == family.workflow_name
        and certificate.get("githubWorkflowRepository") == repository
        and certificate.get("githubWorkflowRef") == "refs/heads/main"
        and certificate.get("buildSignerURI") == workflow_uri
        and certificate.get("buildSignerDigest") == source_commit_sha
        and certificate.get("buildConfigURI") == workflow_uri
        and certificate.get("buildConfigDigest") == source_commit_sha
        and certificate.get("sourceRepositoryURI") == source_uri
        and certificate.get("sourceRepositoryDigest") == source_commit_sha
        and certificate.get("sourceRepositoryRef") == "refs/heads/main"
        and certificate.get("runnerEnvironment") == "github-hosted"
        and certificate.get("buildTrigger") == run["event"]
        and certificate.get("githubWorkflowTrigger") == run["event"]
        and certificate.get("runInvocationURI") == invocation_uri
    ):
        _fail(f"supplemental_attestation_identity_invalid:{family.family_id}")
    identity = result.get("verifiedIdentity")
    if not isinstance(identity, dict) or identity.get("runnerEnvironment") != (
        "github-hosted"
    ):
        _fail(f"supplemental_attestation_runner_invalid:{family.family_id}")
    timestamps = result.get("verifiedTimestamps")
    if not isinstance(timestamps, list) or not timestamps:
        _fail(f"supplemental_attestation_timestamp_missing:{family.family_id}")
    if any(
        not isinstance(item, dict)
        or item.get("type") != "Tlog"
        or not isinstance(item.get("timestamp"), str)
        for item in timestamps
    ):
        _fail(f"supplemental_attestation_timestamp_invalid:{family.family_id}")
    verified_times = [
        _parse_timestamp(
            item["timestamp"],
            f"supplemental_attestation_timestamp_invalid:{family.family_id}",
        )
        for item in timestamps
    ]
    run_started = _parse_timestamp(
        run["run_started_at"],
        f"supplemental_attestation_timestamp_invalid:{family.family_id}",
    )
    run_completed = _parse_timestamp(
        run["updated_at"],
        f"supplemental_attestation_timestamp_invalid:{family.family_id}",
    )
    if min(verified_times) < run_started or max(verified_times) > run_completed:
        _fail(f"supplemental_attestation_timestamp_invalid:{family.family_id}")

    subject = statement.get("subject")
    predicate = statement.get("predicate")
    build_definition = (
        predicate.get("buildDefinition") if isinstance(predicate, dict) else None
    )
    external_parameters = (
        build_definition.get("externalParameters")
        if isinstance(build_definition, dict)
        else None
    )
    statement_workflow = (
        external_parameters.get("workflow")
        if isinstance(external_parameters, dict)
        else None
    )
    dependencies = (
        build_definition.get("resolvedDependencies")
        if isinstance(build_definition, dict)
        else None
    )
    internal_parameters = (
        build_definition.get("internalParameters")
        if isinstance(build_definition, dict)
        else None
    )
    internal_github = (
        internal_parameters.get("github")
        if isinstance(internal_parameters, dict)
        else None
    )
    run_details = statement.get("predicate", {}).get("runDetails")
    builder = (
        run_details.get("builder") if isinstance(run_details, dict) else None
    )
    metadata = (
        run_details.get("metadata") if isinstance(run_details, dict) else None
    )
    expected_subject_digest = _file_hash(receipt_path).removeprefix("sha256:")
    expected_dependency = {
        "uri": f"git+{source_uri}@refs/heads/main",
        "digest": {"gitCommit": source_commit_sha},
    }
    if not (
        statement.get("_type") == "https://in-toto.io/Statement/v1"
        and statement.get("predicateType") == "https://slsa.dev/provenance/v1"
        and subject
        == [
            {
                "name": "technical-receipt.json",
                "digest": {"sha256": expected_subject_digest},
            }
        ]
        and isinstance(statement_workflow, dict)
        and statement_workflow.get("path") == family.workflow_path
        and statement_workflow.get("ref") == "refs/heads/main"
        and statement_workflow.get("repository") == source_uri
        and dependencies == [expected_dependency]
        and isinstance(internal_github, dict)
        and internal_github.get("event_name") == run["event"]
        and internal_github.get("runner_environment") == "github-hosted"
        and isinstance(builder, dict)
        and builder.get("id") == workflow_uri
        and isinstance(metadata, dict)
        and metadata.get("invocationId") == invocation_uri
    ):
        _fail(f"supplemental_attestation_statement_invalid:{family.family_id}")
    binding = {
        "subject_sha256": f"sha256:{expected_subject_digest}",
        "build_signer_uri": workflow_uri,
        "source_repository_digest": source_commit_sha,
        "run_invocation_uri": invocation_uri,
        "runner_environment": "github-hosted",
    }
    audit_projection = {
        "binding": binding,
        "verified_timestamps_utc": sorted(
            value.astimezone(timezone.utc).isoformat()
            for value in verified_times
        ),
        "statement_subject": subject,
        "statement_predicate_type": statement.get("predicateType"),
    }
    return binding, audit_projection


def _validate_attestation(
    *,
    repo_root: Path,
    family_root: Path,
    artifact_root: Path,
    family: Family,
    repository: str,
    source_commit_sha: str,
    run: dict[str, Any],
    receipt_path: Path,
) -> tuple[Path, Path, dict[str, Any]]:
    bundle_path = _safe_file(
        artifact_root,
        family.artifact_bundle_path,
        f"supplemental_sigstore_bundle_missing:{family.family_id}",
    )
    verification_path = _safe_file(
        family_root,
        "product-state-attestation-verification.json",
        f"supplemental_attestation_verification_missing:{family.family_id}",
    )
    bundle_loaded = _load_json(
        bundle_path, f"supplemental_sigstore_bundle_invalid:{family.family_id}"
    )
    cached_verification = _load_json(
        verification_path,
        f"supplemental_attestation_verification_invalid:{family.family_id}",
    )
    if not isinstance(bundle_loaded, dict):
        _fail(f"supplemental_sigstore_bundle_invalid:{family.family_id}")

    live_verification = _run_live_attestation_verification(
        repo_root=repo_root,
        family=family,
        repository=repository,
        source_commit_sha=source_commit_sha,
        receipt_path=receipt_path,
        bundle_path=bundle_path,
    )
    live_binding, live_projection = _validated_verification_document(
        verification_loaded=live_verification,
        bundle_loaded=bundle_loaded,
        family=family,
        repository=repository,
        source_commit_sha=source_commit_sha,
        run=run,
        receipt_path=receipt_path,
    )
    _cached_binding, cached_projection = _validated_verification_document(
        verification_loaded=cached_verification,
        bundle_loaded=bundle_loaded,
        family=family,
        repository=repository,
        source_commit_sha=source_commit_sha,
        run=run,
        receipt_path=receipt_path,
    )
    if cached_projection != live_projection:
        _fail(f"supplemental_attestation_audit_cache_mismatch:{family.family_id}")
    return bundle_path, verification_path, live_binding


def _family_row(
    *,
    repo_root: Path,
    input_root: Path,
    family: Family,
    repository: str,
    source_commit_sha: str,
) -> tuple[dict[str, Any], datetime, datetime]:
    family_root = _safe_directory(
        input_root,
        family.family_id,
        f"supplemental_family_root_invalid:{family.family_id}",
    )
    artifact_root = _safe_directory(
        family_root,
        "artifact",
        f"supplemental_family_root_invalid:{family.family_id}",
    )
    run_path = _safe_file(
        family_root,
        "workflow-run.json",
        f"supplemental_workflow_run_missing:{family.family_id}",
    )
    run = _validate_workflow_run(
        run_path=run_path,
        family=family,
        repository=repository,
        source_commit_sha=source_commit_sha,
    )
    receipt_path, receipt, package_binding, cases = _validate_receipt_and_results(
        repo_root=repo_root,
        artifact_root=artifact_root,
        family=family,
        source_commit_sha=source_commit_sha,
    )
    bundle_path, verification_path, attestation = _validate_attestation(
        repo_root=repo_root,
        family_root=family_root,
        artifact_root=artifact_root,
        family=family,
        repository=repository,
        source_commit_sha=source_commit_sha,
        run=run,
        receipt_path=receipt_path,
    )
    started = _parse_timestamp(
        run["run_started_at"],
        f"supplemental_workflow_run_timestamp_invalid:{family.family_id}",
    )
    completed = _parse_timestamp(
        run["updated_at"],
        f"supplemental_workflow_run_timestamp_invalid:{family.family_id}",
    )
    row = {
        "family_id": family.family_id,
        "artifact_root": _relative(repo_root, artifact_root),
        "artifact_name": (
            f"{family.artifact_prefix}-{run['id']}-{run['run_attempt']}"
        ),
        "workflow": {
            "path": family.workflow_path,
            "name": family.workflow_name,
            "file_sha256": _file_hash(repo_root / family.workflow_path),
            "run_metadata_path": _relative(repo_root, run_path),
            "run_metadata_file_sha256": _file_hash(run_path),
            "run_id": run["id"],
            "run_attempt": run["run_attempt"],
            "event": run["event"],
            "run_started_at": run["run_started_at"],
            "completed_at": run["updated_at"],
        },
        "technical_receipt": {
            "path": _relative(repo_root, receipt_path),
            "file_sha256": _file_hash(receipt_path),
            "artifact_hash": receipt["artifact_hash"],
            "schema_version": receipt["schema_version"],
        },
        "package_manifest": package_binding,
        "sigstore_bundle": {
            "path": _relative(repo_root, bundle_path),
            "file_sha256": _file_hash(bundle_path),
        },
        "attestation_verification": {
            "path": _relative(repo_root, verification_path),
            "file_sha256": _file_hash(verification_path),
            **attestation,
        },
        "cases": cases,
        "technical_contract_pass": True,
        "fresh_current_source_technical_validation": True,
        "independent_operator_attested": False,
        "legal_use_approved": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }
    return row, started, completed


def _execution_binding_hash(
    *, source_commit_sha: str, repository: str, families: list[dict[str, Any]]
) -> str:
    return _hash_bytes(
        _canonical_bytes(
            {
                "source_commit_sha": source_commit_sha,
                "repository": repository,
                "families": families,
            }
        )
    )


def _load_schema(repo_root: Path) -> dict[str, Any]:
    loaded = _load_json(
        repo_root / SCHEMA_PATH,
        "current_source_supplemental_attestation_schema_unreadable",
    )
    if not isinstance(loaded, dict):
        _fail("current_source_supplemental_attestation_schema_invalid")
    return loaded


def _validate_receipt_structure(
    payload: dict[str, Any], *, repo_root: Path = ROOT
) -> None:
    """Validate derived fields only after an authoritative input replay."""

    try:
        schema = _load_schema(repo_root)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(
            schema, format_checker=FormatChecker()
        ).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise CurrentSourceSupplementalAttestationError(
            "current_source_supplemental_attestation_schema_invalid"
        ) from exc
    if payload.get("artifact_hash") != _artifact_hash(payload):
        _fail("current_source_supplemental_attestation_hash_invalid")
    families = payload.get("families")
    if not isinstance(families, list) or [
        str(row.get("family_id") or "") for row in families if isinstance(row, dict)
    ] != [family.family_id for family in FAMILIES]:
        _fail("current_source_supplemental_attestation_family_set_invalid")
    for family, row in zip(FAMILIES, families, strict=True):
        cases = row.get("cases")
        workflow = row.get("workflow")
        technical_receipt = row.get("technical_receipt")
        attestation = row.get("attestation_verification")
        if (
            not isinstance(cases, list)
            or [str(case.get("case_id") or "") for case in cases]
            != list(family.case_ids)
            or not all(
                isinstance(case, dict)
                and case.get("technical_contract_pass") is True
                and isinstance(case.get("external_engine_invoked"), bool)
                for case in cases
            )
            or not isinstance(workflow, dict)
            or workflow.get("path") != family.workflow_path
            or workflow.get("name") != family.workflow_name
            or workflow.get("event") not in {"push", "workflow_dispatch"}
            or not isinstance(workflow.get("run_id"), int)
            or not isinstance(workflow.get("run_attempt"), int)
            or row.get("artifact_name")
            != (
                f"{family.artifact_prefix}-{workflow.get('run_id')}-"
                f"{workflow.get('run_attempt')}"
            )
            or not isinstance(technical_receipt, dict)
            or technical_receipt.get("schema_version")
            != family.receipt_schema_version
            or not isinstance(attestation, dict)
            or attestation.get("subject_sha256")
            != technical_receipt.get("file_sha256")
            or attestation.get("source_repository_digest")
            != payload.get("source_commit_sha")
            or attestation.get("runner_environment") != "github-hosted"
            or row.get("technical_contract_pass") is not True
            or row.get("fresh_current_source_technical_validation") is not True
            or row.get("independent_operator_attested") is not False
            or row.get("legal_use_approved") is not False
            or row.get("verification_matrix_credit") is not False
            or row.get("verification_level_2") is not False
        ):
            _fail(
                "current_source_supplemental_attestation_family_contract_invalid:"
                f"{family.family_id}"
            )
        expected_invocations = [
            case_id != "bounded_planar_negative_invalid_geometry"
            for case_id in family.case_ids
        ]
        if [case["external_engine_invoked"] for case in cases] != (
            expected_invocations
        ) or [case["verification_method"] for case in cases] != [
            "external_solver_execution" if invoked else "independent_preflight"
            for invoked in expected_invocations
        ]:
            _fail(
                "current_source_supplemental_attestation_case_authority_invalid:"
                f"{family.family_id}"
            )
    all_cases = [case for family in families for case in family["cases"]]
    external_count = sum(case["external_engine_invoked"] for case in all_cases)
    preflight_ids = [
        case["case_id"]
        for case in all_cases
        if case["verification_method"] == "independent_preflight"
    ]
    expected_summary = {
        "family_count": 5,
        "attestation_count": 5,
        "case_count": 16,
        "technical_pass_count": 16,
        "external_engine_invoked_case_count": external_count,
        "independent_preflight_case_ids": preflight_ids,
    }
    if payload.get("summary") != expected_summary:
        _fail("current_source_supplemental_attestation_summary_invalid")
    execution_window = payload.get("execution_window")
    if not isinstance(execution_window, dict):
        _fail("current_source_supplemental_attestation_window_invalid")
    started_values = [
        _parse_timestamp(
            family["workflow"]["run_started_at"],
            "current_source_supplemental_attestation_window_invalid",
        )
        for family in families
    ]
    completed_values = [
        _parse_timestamp(
            family["workflow"]["completed_at"],
            "current_source_supplemental_attestation_window_invalid",
        )
        for family in families
    ]
    if (
        _parse_timestamp(
            execution_window.get("started_at"),
            "current_source_supplemental_attestation_window_invalid",
        )
        != min(started_values)
        or _parse_timestamp(
            execution_window.get("completed_at"),
            "current_source_supplemental_attestation_window_invalid",
        )
        != max(completed_values)
        or _parse_timestamp(
            payload.get("generated_at"),
            "current_source_supplemental_attestation_generated_at_invalid",
        )
        < max(completed_values)
    ):
        _fail("current_source_supplemental_attestation_window_invalid")
    if (
        external_count != 15
        or preflight_ids != ["bounded_planar_negative_invalid_geometry"]
        or payload.get("execution_binding_hash")
        != _execution_binding_hash(
            source_commit_sha=payload["source_commit_sha"],
            repository=payload["repository"],
            families=families,
        )
    ):
        _fail("current_source_supplemental_attestation_binding_invalid")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_current_source_bound") is True
        and claims.get("github_hosted_execution") is True
        and claims.get("sigstore_attestations_reverified") is True
        and claims.get("fresh_current_source_technical_validation") is True
        and claims.get("fresh_current_source_external_execution_for_engine_cases")
        is True
        and claims.get("same_operator_execution") is True
        and claims.get("external_execution_reused") is False
        and claims.get("actual_external_solver_execution") is True
        and claims.get("independent_operator_attested") is False
        and claims.get("legal_use_approved") is False
        and claims.get("formal_promotion_receipt_attached") is False
        and claims.get("verification_level_2") is False
        and claims.get("design_authority") is False
        and claims.get("commercial_equivalence") is False
        and claims.get("release_readiness") is False
    ):
        _fail("current_source_supplemental_attestation_claim_boundary_invalid")


def validate_receipt(
    payload: dict[str, Any], *, repo_root: Path = ROOT
) -> None:
    """Authoritatively validate the receipt and rerun every Sigstore check."""

    _validate_receipt_structure(payload, repo_root=repo_root)
    input_root = _resolved(repo_root, Path(payload["input_root"]))
    rebuilt_rows = [
        _family_row(
            repo_root=repo_root,
            input_root=input_root,
            family=family,
            repository=payload["repository"],
            source_commit_sha=payload["source_commit_sha"],
        )[0]
        for family in FAMILIES
    ]
    if rebuilt_rows != payload["families"]:
        _fail("current_source_supplemental_attestation_input_binding_invalid")


def build_receipt(
    *,
    source_commit_sha: str,
    repository: str,
    input_root: Path = DEFAULT_INPUT_ROOT,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    if not SHA_PATTERN.fullmatch(source_commit_sha):
        _fail("current_source_supplemental_attestation_source_invalid")
    if not REPOSITORY_PATTERN.fullmatch(repository):
        _fail("current_source_supplemental_attestation_repository_invalid")
    resolved_input = _resolved(repo_root, input_root)
    if resolved_input.is_symlink() or not resolved_input.is_dir():
        _fail("current_source_supplemental_attestation_input_root_invalid")
    actual_family_dirs = {
        path.name for path in resolved_input.iterdir() if path.is_dir()
    }
    if actual_family_dirs != {family.family_id for family in FAMILIES}:
        _fail("current_source_supplemental_attestation_input_family_set_invalid")

    family_rows: list[dict[str, Any]] = []
    starts: list[datetime] = []
    completions: list[datetime] = []
    for family in FAMILIES:
        row, started, completed = _family_row(
            repo_root=repo_root,
            input_root=resolved_input,
            family=family,
            repository=repository,
            source_commit_sha=source_commit_sha,
        )
        family_rows.append(row)
        starts.append(started)
        completions.append(completed)
    all_cases = [case for row in family_rows for case in row["cases"]]
    preflight_ids = [
        case["case_id"]
        for case in all_cases
        if case["verification_method"] == "independent_preflight"
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit_sha,
        "repository": repository,
        "input_root": _relative(repo_root, resolved_input),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "execution_window": {
            "started_at": min(starts).isoformat(),
            "completed_at": max(completions).isoformat(),
        },
        "families": family_rows,
        "summary": {
            "family_count": len(family_rows),
            "attestation_count": len(family_rows),
            "case_count": len(all_cases),
            "technical_pass_count": sum(
                case["technical_contract_pass"] for case in all_cases
            ),
            "external_engine_invoked_case_count": sum(
                case["external_engine_invoked"] for case in all_cases
            ),
            "independent_preflight_case_ids": preflight_ids,
        },
        "status": "technical_pass_non_promoting",
        "technical_contract_pass": True,
        "claims": {
            "exact_current_source_bound": True,
            "github_hosted_execution": True,
            "sigstore_attestations_reverified": True,
            "fresh_current_source_technical_validation": True,
            "fresh_current_source_external_execution_for_engine_cases": True,
            "same_operator_execution": True,
            "external_execution_reused": False,
            "actual_external_solver_execution": True,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "formal_promotion_receipt_attached": False,
            "verification_level_2": False,
            "design_authority": False,
            "commercial_equivalence": False,
            "release_readiness": False,
        },
        "blockers": [
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "scientific_promotion_decision_missing",
            "formal_level2_promotion_receipt_missing",
            "bounded_planar_profile_level2_not_achieved",
        ],
        "claim_boundary": (
            "Five exact-source GitHub-hosted workflow receipts were independently "
            "re-verified by the downstream Product State job against their retained "
            "Sigstore bundles, signer workflows, source digest, main ref, and hosted "
            "runner identity. This grants current-source technical credit for fifteen "
            "external-engine cases and one independent invalid-geometry preflight. "
            "It does not establish an independent operator, legal approval, scientific "
            "promotion, Verification Level 2, design authority, commercial "
            "equivalence, or release readiness."
        ),
        "execution_binding_hash": ZERO_HASH,
        "artifact_hash": ZERO_HASH,
    }
    payload["execution_binding_hash"] = _execution_binding_hash(
        source_commit_sha=source_commit_sha,
        repository=repository,
        families=family_rows,
    )
    payload["artifact_hash"] = _artifact_hash(payload)
    _validate_receipt_structure(payload, repo_root=repo_root)
    return payload


def write_receipt(
    *,
    source_commit_sha: str,
    repository: str,
    input_root: Path = DEFAULT_INPUT_ROOT,
    out_path: Path = DEFAULT_OUT,
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    payload = build_receipt(
        source_commit_sha=source_commit_sha,
        repository=repository,
        input_root=input_root,
        repo_root=repo_root,
    )
    target = _resolved(repo_root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validate_bundle(repo_root=repo_root, receipt_path=target)
    return payload


def validate_bundle(
    *, repo_root: Path = ROOT, receipt_path: Path = DEFAULT_OUT
) -> dict[str, Any]:
    resolved = _resolved(repo_root, receipt_path)
    loaded = _load_json(
        resolved, "current_source_supplemental_attestation_receipt_unreadable"
    )
    if not isinstance(loaded, dict):
        _fail("current_source_supplemental_attestation_receipt_invalid")
    validate_receipt(loaded, repo_root=repo_root)
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.check:
            payload = validate_bundle(receipt_path=args.out)
            if (
                payload["source_commit_sha"] != args.source_commit
                or payload["repository"] != args.repository
            ):
                _fail("current_source_supplemental_attestation_identity_mismatch")
        else:
            payload = write_receipt(
                source_commit_sha=args.source_commit,
                repository=args.repository,
                input_root=args.input_root,
                out_path=args.out,
            )
    except CurrentSourceSupplementalAttestationError as exc:
        print(exc.code, file=sys.stderr)
        return 1
    summary = payload["summary"]
    print(
        "bounded planar current-source supplemental attestation: "
        f"technical={summary['technical_pass_count']}/{summary['case_count']} | "
        f"external_engine={summary['external_engine_invoked_case_count']} | "
        "promotion=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
