#!/usr/bin/env python3
"""Build the non-promoting bounded-planar external V&V matrix status."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, NoReturn

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
SRC_ROOT = ROOT / "src"
for search_root in (SCRIPT_DIR, SRC_ROOT):
    if str(search_root) not in sys.path:
        sys.path.insert(0, str(search_root))

import run_external_code_to_code_technical_receipt as code_receipt  # noqa: E402
import run_external_modal_buckling_technical_receipt as modal_receipt  # noqa: E402
import build_bounded_planar_external_linear_case_package as linear_package  # noqa: E402
import build_bounded_planar_external_negative_case_package as negative_package  # noqa: E402
import build_bounded_planar_external_scaling_case_package as scaling_package  # noqa: E402
import build_bounded_planar_external_modal_buckling_case_package as modal_buckling_package  # noqa: E402
import build_bounded_planar_external_nonlinear_material_recovery_case_package as nonlinear_package  # noqa: E402
import build_bounded_planar_same_operator_supplemental_execution as same_operator_supplement  # noqa: E402


SCHEMA_VERSION = "bounded-planar-external-vv-matrix-status.v1"
SCHEMA_PATH = Path(
    "src/structural_analysis/schemas/"
    "bounded_planar_external_vv_matrix_status_v1.schema.json"
)
PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_CODE_RECEIPT = (
    PRODUCTIZATION / "external_code_to_code_technical_execution_receipt.json"
)
DEFAULT_MODAL_RECEIPT = (
    PRODUCTIZATION / "external_modal_buckling_technical_execution_receipt.json"
)
DEFAULT_OUT = Path(
    "artifacts/manifests/bounded_planar_external_vv_matrix.current.v1.json"
)
DEFAULT_LINEAR_CASE_PACKAGE = (
    linear_package.DEFAULT_OUT_DIR / linear_package.MANIFEST_NAME
)
DEFAULT_NEGATIVE_CASE_PACKAGE = (
    negative_package.DEFAULT_OUT_DIR / negative_package.MANIFEST_NAME
)
DEFAULT_SCALING_CASE_PACKAGE = (
    scaling_package.DEFAULT_OUT_DIR / scaling_package.MANIFEST_NAME
)
DEFAULT_MODAL_BUCKLING_CASE_PACKAGE = (
    modal_buckling_package.DEFAULT_OUT_DIR / modal_buckling_package.MANIFEST_NAME
)
DEFAULT_NONLINEAR_CASE_PACKAGE = (
    nonlinear_package.DEFAULT_OUT_DIR / nonlinear_package.MANIFEST_NAME
)
CURRENT_SOURCE_WORKFLOW = Path(
    ".github/workflows/opensees-calculix-current-source.yml"
)
TRACKED_HISTORICAL_CLEAN_RUNNER_SUMMARY = Path(
    "artifacts/vv/opensees_calculix_clean_runner/clean_runner_receipt.json"
)
TRACKED_HISTORICAL_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT = (
    same_operator_supplement.DEFAULT_OUT_DIR / same_operator_supplement.RECEIPT_NAME
)
DEFAULT_CLEAN_RUNNER_SUMMARY = Path(
    ".ci/product-state-inputs/opensees-calculix-clean-runner/"
    "clean_runner_receipt.json"
)
DEFAULT_CLEAN_RUNNER_EVIDENCE_ROOT = Path(
    ".ci/product-state-inputs/opensees-calculix-clean-runner"
)
DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT = Path(
    ".ci/product-state-inputs/current-same-operator-supplemental/receipt.json"
)
CLEAN_RUNNER_MODULE_PATH = Path(
    "benchmarks/clean-runners/opensees-calculix/run_clean_runner.py"
)


REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "requirement_id": "linear.cantilever",
        "category": "linear",
        "label": "Linear cantilever",
        "receipt_id": "code_to_code",
        "case_ids": ("cantilever_tip_load",),
    },
    {
        "requirement_id": "linear.portal",
        "category": "linear",
        "label": "Linear portal",
        "case_ids": ("bounded_planar_linear_portal",),
    },
    {
        "requirement_id": "linear.multistory",
        "category": "linear",
        "label": "Linear multistory frame",
        "case_ids": ("bounded_planar_linear_multistory",),
    },
    {
        "requirement_id": "member_feature.release",
        "category": "member_feature",
        "label": "Member end release",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_member_feature_load_path",),
    },
    {
        "requirement_id": "member_feature.rigid_offset",
        "category": "member_feature",
        "label": "Finite rigid offset",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_member_feature_load_path",),
    },
    {
        "requirement_id": "member_feature.distributed_load",
        "category": "member_feature",
        "label": "Uniform distributed member load",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_member_feature_load_path",),
    },
    {
        "requirement_id": "boundary.settlement",
        "category": "boundary",
        "label": "Support settlement",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_prescribed_settlement_load_path",),
    },
    {
        "requirement_id": "boundary.prescribed_displacement",
        "category": "boundary",
        "label": "Prescribed displacement",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_prescribed_settlement_load_path",),
    },
    {
        "requirement_id": "modal.rigid_mode",
        "category": "modal",
        "label": "Rigid-body mode exclusion",
        "case_ids": ("bounded_planar_modal_rigid_mode",),
    },
    {
        "requirement_id": "modal.repeated_mode",
        "category": "modal",
        "label": "Repeated modal eigenspace",
        "case_ids": ("bounded_planar_modal_repeated_mode",),
    },
    {
        "requirement_id": "buckling.column",
        "category": "buckling",
        "label": "Column linear buckling",
        "receipt_id": "modal_buckling",
        "case_ids": ("whole_model_frame_repeated_mode_linear_buckling",),
    },
    {
        "requirement_id": "buckling.portal",
        "category": "buckling",
        "label": "Portal linear buckling",
        "case_ids": ("bounded_planar_buckling_portal",),
    },
    {
        "requirement_id": "geometric_nonlinear.p_delta",
        "category": "geometric_nonlinear",
        "label": "P-Delta response",
        "case_ids": ("bounded_planar_p_delta",),
        "preparation_blocker": "bounded_planar_public_p_delta_case_missing",
    },
    {
        "requirement_id": "geometric_nonlinear.snap_through",
        "category": "geometric_nonlinear",
        "label": "Snap-through response",
        "case_ids": ("bounded_planar_snap_through",),
        "preparation_blocker": (
            "bounded_planar_public_snap_through_case_missing"
        ),
    },
    {
        "requirement_id": "material.steel_yield",
        "category": "material",
        "label": "Steel yielding",
        "case_ids": ("bounded_planar_steel_yield",),
    },
    {
        "requirement_id": "material.rc_fiber",
        "category": "material",
        "label": "RC fiber response",
        "case_ids": ("bounded_planar_rc_fiber",),
    },
    {
        "requirement_id": "recovery.reaction",
        "category": "recovery",
        "label": "Support reaction recovery",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_member_feature_load_path",),
    },
    {
        "requirement_id": "recovery.member",
        "category": "recovery",
        "label": "Member end-force recovery",
        "receipt_id": "code_to_code",
        "case_ids": ("bounded_planar_member_feature_load_path",),
    },
    {
        "requirement_id": "recovery.section",
        "category": "recovery",
        "label": "Section recovery",
        "case_ids": ("bounded_planar_section_recovery",),
    },
    {
        "requirement_id": "recovery.fiber",
        "category": "recovery",
        "label": "Fiber recovery",
        "case_ids": ("bounded_planar_fiber_recovery",),
    },
    {
        "requirement_id": "negative.mechanism",
        "category": "negative",
        "label": "Mechanism rejection",
        "case_ids": ("bounded_planar_negative_mechanism",),
    },
    {
        "requirement_id": "negative.singular",
        "category": "negative",
        "label": "Singular-system rejection",
        "case_ids": ("bounded_planar_negative_singular",),
    },
    {
        "requirement_id": "negative.invalid_geometry",
        "category": "negative",
        "label": "Invalid-geometry rejection",
        "case_ids": ("bounded_planar_negative_invalid_geometry",),
        "verification_method": "independent_preflight",
    },
    {
        "requirement_id": "scaling.unit_invariance",
        "category": "scaling",
        "label": "Unit invariance",
        "case_ids": ("bounded_planar_scaling_unit_invariance",),
    },
    {
        "requirement_id": "scaling.characteristic_length_invariance",
        "category": "scaling",
        "label": "Characteristic-length invariance",
        "case_ids": ("bounded_planar_scaling_characteristic_length_invariance",),
    },
)


class BoundedPlanarVVMatrixError(ValueError):
    """Stable failure for invalid or stale matrix inputs."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _fail(code: str) -> NoReturn:
    raise BoundedPlanarVVMatrixError(code)


def _resolved(repo_root: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(path: Path, code: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundedPlanarVVMatrixError(code) from exc
    if not isinstance(payload, dict):
        _fail(code)
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _artifact_hash(payload: dict[str, Any]) -> str:
    body = deepcopy(payload)
    body.pop("artifact_hash", None)
    encoded = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _relative(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _receipt_binding(
    *, receipt_id: str, path: Path, payload: dict[str, Any]
) -> dict[str, Any]:
    replay = payload.get("replay_provenance")
    if not isinstance(replay, dict):
        _fail(f"matrix_{receipt_id}_replay_provenance_missing")
    fresh = bool(
        replay.get("external_runtime_executed_in_this_generation") is True
        and replay.get("external_execution_reused") is False
        and replay.get("current_product_replay_pass") is True
    )
    case_ids = sorted(
        str(row.get("case_id") or "")
        for row in payload.get("comparisons", [])
        if isinstance(row, dict)
        and row.get("contract_pass") is True
        and str(row.get("case_id") or "")
    )
    if not case_ids:
        _fail(f"matrix_{receipt_id}_case_inventory_missing")
    return {
        "receipt_id": receipt_id,
        "path": str(path),
        "file_sha256": _file_sha256(path),
        "artifact_hash": payload["artifact_hash"],
        "source_commit_sha": payload["source_commit_sha"],
        "source_set_hash": payload["internal_source"]["source_set_hash"],
        "case_ids": case_ids,
        "external_engine_invoked_case_ids": case_ids,
        "technical_contract_pass": payload["technical_contract_pass"] is True,
        "current_product_replay_pass": (
            replay.get("current_product_replay_pass") is True
        ),
        "fresh_current_source_external_execution": fresh,
    }


def _validated_receipts(
    repo_root: Path,
    code_path: Path,
    modal_path: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    code_payload = _load_json(code_path, "matrix_code_receipt_invalid")
    modal_payload = _load_json(modal_path, "matrix_modal_receipt_invalid")
    try:
        code_receipt.validate_external_code_to_code_technical_receipt(
            code_payload,
            repo_root=repo_root,
            require_current_sources=True,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_code_receipt_validation_failed"
        ) from exc
    try:
        modal_receipt.validate_external_modal_buckling_technical_receipt(
            modal_payload,
            repo_root=repo_root,
            require_current_sources=True,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_modal_receipt_validation_failed"
        ) from exc
    source_commits = {
        str(code_payload.get("source_commit_sha") or ""),
        str(modal_payload.get("source_commit_sha") or ""),
    }
    if len(source_commits) != 1:
        _fail("matrix_receipt_source_commit_mismatch")
    payloads = {
        "code_to_code": code_payload,
        "modal_buckling": modal_payload,
    }
    bindings = {
        "code_to_code": _receipt_binding(
            receipt_id="code_to_code", path=code_path, payload=code_payload
        ),
        "modal_buckling": _receipt_binding(
            receipt_id="modal_buckling", path=modal_path, payload=modal_payload
        ),
    }
    return payloads, bindings


def _load_clean_runner_module(repo_root: Path) -> ModuleType:
    module_path = (repo_root / CLEAN_RUNNER_MODULE_PATH).resolve()
    if not module_path.is_file():
        _fail("matrix_clean_runner_validator_missing")
    module_name = (
        "_bounded_planar_external_vv_clean_runner_"
        + hashlib.sha256(str(module_path).encode("utf-8")).hexdigest()[:12]
    )
    existing = sys.modules.get(module_name)
    if isinstance(existing, ModuleType):
        return existing
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        _fail("matrix_clean_runner_validator_import_invalid")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        sys.modules.pop(module_name, None)
        raise BoundedPlanarVVMatrixError(
            "matrix_clean_runner_validator_import_failed"
        ) from exc
    return module


def _unavailable_same_operator_execution_binding(reason: str) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "technical_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "same_operator_container_isolated_reproduction": False,
        "actual_external_solver_execution": False,
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }


def _clean_runner_evidence_root(
    *, repo_root: Path, summary_path: Path
) -> Path:
    default_summary = _resolved(repo_root, DEFAULT_CLEAN_RUNNER_SUMMARY).resolve()
    if summary_path.resolve() == default_summary:
        return _resolved(repo_root, DEFAULT_CLEAN_RUNNER_EVIDENCE_ROOT).resolve()
    return repo_root.resolve()


def _validated_same_operator_execution(
    *,
    repo_root: Path,
    summary_path: Path,
    expected_source_commit: str,
    evidence_root: Path | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]] | None,
    dict[str, dict[str, Any]] | None,
]:
    if not summary_path.is_file():
        return (
            _unavailable_same_operator_execution_binding(
                "fresh_same_operator_clean_runner_receipt_not_attached"
            ),
            None,
            None,
        )

    resolved_evidence_root = (evidence_root or repo_root).resolve()
    summary = _load_json(summary_path, "matrix_clean_runner_summary_invalid")
    runner = _load_clean_runner_module(repo_root)
    try:
        runner.validate_summary(
            summary,
            repo_root=repo_root,
            evidence_root=resolved_evidence_root,
        )
    except Exception as exc:
        if str(exc) == "summary_cross_environment_parity_invalid":
            return (
                _unavailable_same_operator_execution_binding(
                    "current_source_clean_runner_cross_environment_parity_missing"
                ),
                None,
                None,
            )
        raise BoundedPlanarVVMatrixError(
            "matrix_clean_runner_summary_validation_failed"
        ) from exc

    if summary.get("source_commit_sha") != expected_source_commit:
        _fail("matrix_clean_runner_source_commit_mismatch")
    claims = summary.get("claims")
    if not isinstance(claims, dict):
        _fail("matrix_clean_runner_claims_invalid")
    forbidden_claims = (
        "independent_operator_attestation",
        "product_legal_license_approval",
        "external_runtime_redistribution_approval",
        "verification_level_2",
        "commercial_equivalence",
        "design_authority",
        "release_readiness",
    )
    if not (
        summary.get("technical_contract_pass") is True
        and summary.get("isolation", {}).get("isolation_contract_pass") is True
        and claims.get("current_candidate_source_bytes_checksum_bound") is True
        and claims.get("actual_external_solver_execution") is True
        and all(claims.get(name) is False for name in forbidden_claims)
    ):
        _fail("matrix_clean_runner_claim_boundary_invalid")

    descriptors = summary.get("product_receipts")
    if not isinstance(descriptors, dict) or set(descriptors) != {
        "code_to_code",
        "modal_buckling",
    }:
        _fail("matrix_clean_runner_child_receipts_invalid")
    cross_environment_ready = bool(
        claims.get("cross_environment_numerical_parity") is True
    )
    fresh_execution = bool(
        cross_environment_ready
        and claims.get("same_operator_container_isolated_reproduction") is True
        and all(
            isinstance(descriptor, dict)
            and descriptor.get("fresh_external_runtime_execution") is True
            for descriptor in descriptors.values()
        )
    )
    if not fresh_execution:
        return (
            _unavailable_same_operator_execution_binding(
                (
                    "current_source_clean_runner_cross_environment_parity_missing"
                    if not cross_environment_ready
                    else "fresh_same_operator_clean_runner_execution_missing"
                )
            ),
            None,
            None,
        )

    child_paths: dict[str, Path] = {}
    for receipt_id, descriptor in descriptors.items():
        raw_path = Path(str(descriptor.get("path") or ""))
        if raw_path.is_absolute():
            _fail("matrix_clean_runner_child_receipt_path_absolute")
        child_path = (resolved_evidence_root / raw_path).resolve()
        try:
            child_path.relative_to(resolved_evidence_root)
        except ValueError:
            _fail("matrix_clean_runner_child_receipt_path_escape")
        if not child_path.is_file():
            _fail("matrix_clean_runner_child_receipt_missing")
        child_paths[receipt_id] = child_path

    payloads, bindings = _validated_receipts(
        repo_root,
        child_paths["code_to_code"],
        child_paths["modal_buckling"],
    )
    for receipt_id, descriptor in descriptors.items():
        binding = bindings[receipt_id]
        if (
            binding["source_commit_sha"] != expected_source_commit
            or binding["file_sha256"] != descriptor.get("file_sha256")
            or binding["artifact_hash"] != descriptor.get("artifact_hash")
            or binding["source_set_hash"] != descriptor.get("source_set_hash")
            or binding["fresh_current_source_external_execution"] is not True
        ):
            _fail("matrix_clean_runner_child_receipt_binding_invalid")

    return (
        {
            "status": "attached",
            "path": _relative(repo_root, summary_path),
            "file_sha256": _file_sha256(summary_path),
            "artifact_hash": summary["artifact_hash"],
            "source_commit_sha": summary["source_commit_sha"],
            "technical_contract_pass": True,
            "fresh_external_runtime_execution": True,
            "same_operator_container_isolated_reproduction": True,
            "actual_external_solver_execution": True,
            "cross_environment_numerical_parity": (
                claims.get("cross_environment_numerical_parity") is True
            ),
            "fresh_child_receipt_ids": ["code_to_code", "modal_buckling"],
            "independent_operator_attested": False,
            "product_legal_license_approval": False,
            "verification_level_2": False,
        },
        payloads,
        bindings,
    )


def _unavailable_same_operator_supplemental_execution_binding(
    reason: str,
) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": reason,
        "technical_contract_pass": False,
        "current_product_replay_pass": False,
        "historical_execution_input_binding_pass": False,
        "external_runtime_executed_in_this_generation": False,
        "external_execution_reused": False,
        "fresh_current_source_external_execution": False,
        "same_operator_local_execution": False,
        "container_isolated_reproduction": False,
        "actual_external_solver_execution": False,
        "runtime_asset_bytes_attached": False,
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }


def _supplemental_child_case_passes(
    child: dict[str, Any], case_ids: list[str]
) -> list[dict[str, Any]]:
    cases = child.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_same_operator_supplemental_child_case_set_invalid")
    rows: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            _fail("matrix_same_operator_supplemental_child_case_set_invalid")
        pass_values = [
            case[key]
            for key in (
                "technical_comparison_pass",
                "technical_rejection_pass",
                "technical_contract_pass",
            )
            if key in case
        ]
        if len(pass_values) != 1 or not isinstance(pass_values[0], bool):
            _fail("matrix_same_operator_supplemental_child_case_pass_invalid")
        rows.append(
            {
                "case_id": str(case.get("case_id") or ""),
                "contract_pass": pass_values[0],
            }
        )
    if [row["case_id"] for row in rows] != case_ids:
        _fail("matrix_same_operator_supplemental_child_case_set_invalid")
    return rows


def _supplemental_child_fresh_execution(
    *, family_id: str, child: dict[str, Any]
) -> bool:
    claims = child.get("claims")
    if not isinstance(claims, dict):
        _fail("matrix_same_operator_supplemental_child_claims_invalid")
    key = (
        "fresh_external_solver_execution"
        if family_id == "modal_buckling"
        else "fresh_current_source_external_execution"
    )
    value = claims.get(key)
    if not isinstance(value, bool):
        _fail("matrix_same_operator_supplemental_child_freshness_invalid")
    return value


def _validated_same_operator_supplemental_execution(
    *,
    repo_root: Path,
    receipt_path: Path,
    expected_source_commit: str,
) -> tuple[
    dict[str, Any],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, str],
]:
    if not receipt_path.is_file():
        return (
            _unavailable_same_operator_supplemental_execution_binding(
                "same_operator_supplemental_execution_receipt_not_attached"
            ),
            {},
            {},
            {},
        )
    if receipt_path.name != same_operator_supplement.RECEIPT_NAME:
        _fail("matrix_same_operator_supplemental_receipt_name_invalid")
    try:
        receipt = same_operator_supplement.validate_bundle(
            repo_root=repo_root,
            out_dir=receipt_path.parent,
        )
    except Exception as exc:
        reason = str(exc)
        if reason in {
            "external_modal_buckling_case_source_files_stale",
            "external_nonlinear_case_source_files_stale",
        }:
            return (
                _unavailable_same_operator_supplemental_execution_binding(
                    "current_source_same_operator_supplemental_package_stale"
                ),
                {},
                {},
                {},
            )
        raise BoundedPlanarVVMatrixError(
            "matrix_same_operator_supplemental_execution_validation_failed"
        ) from exc
    if receipt.get("source_commit_sha") != expected_source_commit:
        _fail("matrix_same_operator_supplemental_source_commit_mismatch")
    claims = receipt.get("claims")
    replay = receipt.get("replay_provenance")
    if not isinstance(claims, dict) or not (
        receipt.get("technical_contract_pass") is True
        and isinstance(replay, dict)
        and replay.get("execution_mode") == "current_product_replay_only"
        and replay.get("external_runtime_executed_in_this_generation") is False
        and replay.get("external_execution_reused") is True
        and replay.get("historical_execution_input_binding_pass") is True
        and replay.get("metric_semantics_match") is True
        and replay.get("current_product_replay_pass") is True
        and claims.get("current_source_package_bytes_authenticated") is True
        and claims.get("raw_external_results_attached") is True
        and claims.get("historical_execution_input_bytes_attached") is True
        and claims.get("raw_execution_binding_pass") is True
        and claims.get("metric_semantics_match") is True
        and claims.get("current_product_replay_pass") is True
        and claims.get("external_runtime_executed_in_this_generation") is False
        and claims.get("external_execution_reused") is True
        and claims.get("same_operator_local_execution") is True
        and claims.get("actual_external_solver_execution") is True
        and claims.get("fresh_current_source_external_execution") is False
        and claims.get("runtime_asset_bytes_attached") is False
        and claims.get("container_isolated_reproduction") is False
        and claims.get("independent_operator_attested") is False
        and claims.get("legal_use_approved") is False
        and claims.get("formal_promotion_receipt_attached") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
        and claims.get("design_authority") is False
        and claims.get("commercial_equivalence") is False
        and claims.get("release_readiness") is False
    ):
        _fail("matrix_same_operator_supplemental_claim_boundary_invalid")

    family_rows = receipt.get("families")
    if not isinstance(family_rows, list):
        _fail("matrix_same_operator_supplemental_family_set_invalid")
    family_ids = [str(row.get("family_id") or "") for row in family_rows]
    if family_ids != [
        "linear",
        "negative",
        "scaling",
        "modal_buckling",
        "nonlinear_material_recovery",
    ]:
        _fail("matrix_same_operator_supplemental_family_set_invalid")

    payloads: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    requirement_receipts: dict[str, str] = {}
    all_case_ids: list[str] = []
    for family in family_rows:
        family_id = str(family["family_id"])
        receipt_id = f"same_operator_supplemental_{family_id}"
        case_ids = [str(case_id) for case_id in family.get("case_ids", [])]
        results = family.get("results")
        technical_receipt = family.get("technical_receipt")
        if (
            not case_ids
            or not isinstance(results, list)
            or [str(row.get("case_id") or "") for row in results] != case_ids
            or not isinstance(technical_receipt, dict)
            or family.get("technical_contract_pass") is not True
            or family.get("raw_execution_binding_pass") is not True
            or family.get("metric_semantics_match") is not True
            or family.get("current_product_replay_pass") is not True
            or family.get("external_runtime_executed_in_this_generation") is not False
            or family.get("external_execution_reused") is not True
            or family.get("fresh_current_source_external_execution") is not False
            or family.get("independent_operator_attested") is not False
            or family.get("verification_matrix_credit") is not False
        ):
            _fail("matrix_same_operator_supplemental_family_invalid")
        if any(
            not isinstance(result, dict)
            or not isinstance(result.get("external_engine_invoked"), bool)
            for result in results
        ):
            _fail("matrix_same_operator_supplemental_engine_invocation_invalid")
        external_engine_invoked_case_ids = [
            str(result["case_id"])
            for result in results
            if result["external_engine_invoked"] is True
        ]
        child_path = _resolved(
            repo_root, Path(str(technical_receipt.get("path") or ""))
        )
        try:
            child_path.relative_to(repo_root.resolve())
        except ValueError:
            _fail("matrix_same_operator_supplemental_child_path_escape")
        child = _load_json(
            child_path,
            "matrix_same_operator_supplemental_child_receipt_invalid",
        )
        if (
            not child_path.is_file()
            or technical_receipt.get("file_sha256") != _file_sha256(child_path)
            or technical_receipt.get("artifact_hash") != child.get("artifact_hash")
            or child.get("artifact_hash") != _artifact_hash(child)
            or child.get("source_commit_sha") != expected_source_commit
            or child.get("technical_contract_pass") is not True
            or _supplemental_child_fresh_execution(
                family_id=family_id, child=child
            )
        ):
            _fail("matrix_same_operator_supplemental_child_binding_invalid")
        child_comparisons = _supplemental_child_case_passes(child, case_ids)
        if not all(row["contract_pass"] for row in child_comparisons):
            _fail("matrix_same_operator_supplemental_child_case_blocked")
        payloads[receipt_id] = {
            "comparisons": child_comparisons
        }
        bindings[receipt_id] = {
            "receipt_id": receipt_id,
            "path": str(child_path),
            "file_sha256": technical_receipt["file_sha256"],
            "artifact_hash": technical_receipt["artifact_hash"],
            "source_commit_sha": expected_source_commit,
            "source_binding_hash": receipt["execution_binding_hash"],
            "case_ids": case_ids,
            "external_engine_invoked_case_ids": (
                external_engine_invoked_case_ids
            ),
            "technical_contract_pass": True,
            "current_product_replay_pass": family[
                "current_product_replay_pass"
            ],
            "external_execution_reused": family[
                "external_execution_reused"
            ],
            "fresh_current_source_external_execution": family[
                "fresh_current_source_external_execution"
            ],
        }
        all_case_ids.extend(case_ids)
        for requirement in REQUIREMENTS:
            requirement_case_ids = tuple(
                str(case_id) for case_id in requirement.get("case_ids", ())
            )
            if (
                not isinstance(requirement.get("receipt_id"), str)
                and requirement_case_ids
                and set(requirement_case_ids).issubset(case_ids)
            ):
                requirement_receipts[str(requirement["requirement_id"])] = receipt_id

    expected_requirement_ids = {
        "linear.portal",
        "linear.multistory",
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
        "geometric_nonlinear.p_delta",
        "geometric_nonlinear.snap_through",
        "material.steel_yield",
        "material.rc_fiber",
        "recovery.section",
        "recovery.fiber",
    }
    if set(requirement_receipts) != expected_requirement_ids:
        _fail("matrix_same_operator_supplemental_requirement_mapping_invalid")
    binding = {
        "status": "attached_replay_only",
        "path": _relative(repo_root, receipt_path),
        "file_sha256": _file_sha256(receipt_path),
        "artifact_hash": receipt["artifact_hash"],
        "execution_binding_hash": receipt["execution_binding_hash"],
        "historical_execution_binding_hash": receipt[
            "historical_execution_binding_hash"
        ],
        "current_product_replay_binding_hash": receipt[
            "current_product_replay_binding_hash"
        ],
        "source_commit_sha": receipt["source_commit_sha"],
        "external_execution_source_commit_sha": receipt[
            "external_execution_source_commit_sha"
        ],
        "execution_window": receipt["execution_window"],
        "technical_contract_pass": True,
        "current_product_replay_pass": True,
        "historical_execution_input_binding_pass": True,
        "external_runtime_executed_in_this_generation": False,
        "external_execution_reused": True,
        "fresh_current_source_external_execution": False,
        "same_operator_local_execution": True,
        "container_isolated_reproduction": False,
        "actual_external_solver_execution": True,
        "runtime_asset_bytes_attached": False,
        "family_ids": family_ids,
        "case_ids": all_case_ids,
        "external_engine_invoked_case_count": receipt["summary"][
            "external_engine_invoked_case_count"
        ],
        "independent_preflight_case_ids": [
            case_id
            for case_id in all_case_ids
            if case_id
            not in {
                invoked_case_id
                for child_binding in bindings.values()
                for invoked_case_id in child_binding[
                    "external_engine_invoked_case_ids"
                ]
            }
        ],
        "independent_operator_attested": False,
        "product_legal_license_approval": False,
        "verification_level_2": False,
    }
    return binding, payloads, bindings, requirement_receipts


def _validated_execution_package(
    *, repo_root: Path, manifest_path: Path, source_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(
        manifest_path, "matrix_linear_execution_package_manifest_invalid"
    )
    try:
        linear_package._validate_manifest(manifest, repo_root)
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_linear_execution_package_validation_failed"
        ) from exc
    if manifest.get("source_commit_sha") != source_commit:
        _fail("matrix_linear_execution_package_source_commit_mismatch")
    claims = manifest.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_model_ir_inputs") is True
        and claims.get("current_product_execution") is True
        and claims.get("opensees_runner_syntax_checked") is True
        and claims.get("runtime_dependency_pinned") is True
        and claims.get("output_authenticity_contract") is True
        and claims.get("external_solver_execution") is False
        and claims.get("external_reference_values") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail("matrix_linear_execution_package_claim_boundary_invalid")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_linear_execution_package_cases_invalid")
    requirement_ids = [str(row.get("requirement_id") or "") for row in cases]
    if requirement_ids != ["linear.portal", "linear.multistory"]:
        _fail("matrix_linear_execution_package_requirement_set_invalid")

    package_root = manifest_path.parent.resolve()
    expected_paths = {linear_package.MANIFEST_NAME}
    for field in (
        "external_result_schema",
        "python_requirements",
        "operator_readme",
        "execution_workflow",
    ):
        descriptor = manifest.get(field)
        if not isinstance(descriptor, dict):
            _fail("matrix_linear_execution_package_descriptor_invalid")
        relative = Path(str(descriptor.get("path") or ""))
        target = (package_root / relative).resolve()
        try:
            target.relative_to(package_root)
        except ValueError:
            _fail("matrix_linear_execution_package_path_escape")
        if not target.is_file():
            _fail("matrix_linear_execution_package_file_missing")
        expected_paths.add(relative.as_posix())
        if descriptor.get("file_sha256") != _file_sha256(target):
            _fail("matrix_linear_execution_package_file_hash_invalid")
    for row in cases:
        if not isinstance(row, dict):
            _fail("matrix_linear_execution_package_case_invalid")
        if row.get("product_execution_contract_pass") is not True:
            _fail("matrix_linear_execution_package_product_result_invalid")
        if row.get("external_execution_status") != "unavailable":
            _fail("matrix_linear_execution_package_external_status_invalid")
        for field in ("model_ir", "opensees_runner", "product_result"):
            descriptor = row.get(field)
            if not isinstance(descriptor, dict):
                _fail("matrix_linear_execution_package_descriptor_invalid")
            relative = Path(str(descriptor.get("path") or ""))
            target = (package_root / relative).resolve()
            try:
                target.relative_to(package_root)
            except ValueError:
                _fail("matrix_linear_execution_package_path_escape")
            if not target.is_file():
                _fail("matrix_linear_execution_package_file_missing")
            expected_paths.add(relative.as_posix())
            if descriptor.get("file_sha256") != _file_sha256(target):
                _fail("matrix_linear_execution_package_file_hash_invalid")
            artifact_hash = descriptor.get("artifact_hash")
            if artifact_hash is not None:
                payload = _load_json(
                    target, "matrix_linear_execution_package_json_invalid"
                )
                if artifact_hash != _artifact_hash(payload):
                    _fail("matrix_linear_execution_package_artifact_hash_invalid")
    actual_paths = {
        path.relative_to(package_root).as_posix()
        for path in package_root.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_paths:
        _fail("matrix_linear_execution_package_file_set_invalid")
    binding = {
        "package_id": manifest["package_id"],
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_sha256(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "execution_workflow": {
            "repository_path": linear_package.EXECUTION_WORKFLOW_PATH.as_posix(),
            "packaged_path": manifest["execution_workflow"]["path"],
            "file_sha256": manifest["execution_workflow"]["file_sha256"],
        },
        "requirement_ids": requirement_ids,
        "contract_pass": manifest.get("contract_pass") is True,
        "external_solver_execution": False,
        "verification_matrix_credit": False,
    }
    return manifest, binding


def _validated_negative_execution_package(
    *, repo_root: Path, manifest_path: Path, source_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = negative_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_negative_execution_package_validation_failed"
        ) from exc
    if manifest_path.name != negative_package.MANIFEST_NAME:
        _fail("matrix_negative_execution_package_manifest_name_invalid")
    if manifest.get("source_commit_sha") != source_commit:
        _fail("matrix_negative_execution_package_source_commit_mismatch")
    claims = manifest.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_model_ir_inputs") is True
        and claims.get("current_product_rejection") is True
        and claims.get("opensees_runner_syntax_checked") is True
        and claims.get("runtime_dependency_pinned") is True
        and claims.get("output_authenticity_contract") is True
        and claims.get("external_solver_execution") is False
        and claims.get("external_reference_attached") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail("matrix_negative_execution_package_claim_boundary_invalid")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_negative_execution_package_cases_invalid")
    requirement_ids = [str(row.get("requirement_id") or "") for row in cases]
    if requirement_ids != [
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
    ]:
        _fail("matrix_negative_execution_package_requirement_set_invalid")
    return manifest, {
        "package_id": manifest["package_id"],
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_sha256(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "execution_workflow": {
            "repository_path": negative_package.EXECUTION_WORKFLOW_PATH.as_posix(),
            "packaged_path": manifest["execution_workflow"]["path"],
            "file_sha256": manifest["execution_workflow"]["file_sha256"],
        },
        "requirement_ids": requirement_ids,
        "contract_pass": manifest.get("contract_pass") is True,
        "external_solver_execution": False,
        "verification_matrix_credit": False,
    }


def _validated_scaling_execution_package(
    *, repo_root: Path, manifest_path: Path, source_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = scaling_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_scaling_execution_package_validation_failed"
        ) from exc
    if manifest_path.name != scaling_package.MANIFEST_NAME:
        _fail("matrix_scaling_execution_package_manifest_name_invalid")
    if manifest.get("source_commit_sha") != source_commit:
        _fail("matrix_scaling_execution_package_source_commit_mismatch")
    claims = manifest.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_model_ir_inputs") is True
        and claims.get("current_product_invariance_replay") is True
        and claims.get("opensees_runner_syntax_checked") is True
        and claims.get("runtime_dependency_pinned") is True
        and claims.get("output_authenticity_contract") is True
        and claims.get("external_solver_execution") is False
        and claims.get("external_reference_attached") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail("matrix_scaling_execution_package_claim_boundary_invalid")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_scaling_execution_package_cases_invalid")
    requirement_ids = [str(row.get("requirement_id") or "") for row in cases]
    if requirement_ids != [
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ]:
        _fail("matrix_scaling_execution_package_requirement_set_invalid")
    return manifest, {
        "package_id": manifest["package_id"],
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_sha256(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "execution_workflow": {
            "repository_path": scaling_package.EXECUTION_WORKFLOW_PATH.as_posix(),
            "packaged_path": manifest["execution_workflow"]["path"],
            "file_sha256": manifest["execution_workflow"]["file_sha256"],
        },
        "requirement_ids": requirement_ids,
        "contract_pass": manifest.get("contract_pass") is True,
        "external_solver_execution": False,
        "verification_matrix_credit": False,
    }


def _validated_modal_buckling_execution_package(
    *, repo_root: Path, manifest_path: Path, source_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = modal_buckling_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_modal_buckling_execution_package_validation_failed"
        ) from exc
    if manifest_path.name != modal_buckling_package.MANIFEST_NAME:
        _fail("matrix_modal_buckling_execution_package_manifest_name_invalid")
    if manifest.get("source_commit_sha") != source_commit:
        _fail("matrix_modal_buckling_execution_package_source_commit_mismatch")
    claims = manifest.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_canonical_model_inputs") is True
        and claims.get("current_product_replay") is True
        and claims.get("external_runner_syntax_checked") is True
        and claims.get("runtime_dependencies_pinned") is True
        and claims.get("output_authenticity_contract") is True
        and claims.get("external_solver_execution") is False
        and claims.get("external_reference_attached") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail("matrix_modal_buckling_execution_package_claim_boundary_invalid")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_modal_buckling_execution_package_cases_invalid")
    requirement_ids = [str(row.get("requirement_id") or "") for row in cases]
    if requirement_ids != [
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
    ]:
        _fail("matrix_modal_buckling_execution_package_requirement_set_invalid")
    return manifest, {
        "package_id": manifest["package_id"],
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_sha256(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "execution_workflow": {
            "repository_path": (
                modal_buckling_package.EXECUTION_WORKFLOW_PATH.as_posix()
            ),
            "packaged_path": manifest["execution_workflow"]["path"],
            "file_sha256": manifest["execution_workflow"]["file_sha256"],
        },
        "requirement_ids": requirement_ids,
        "contract_pass": manifest.get("contract_pass") is True,
        "external_solver_execution": False,
        "verification_matrix_credit": False,
    }


def _validated_nonlinear_execution_package(
    *, repo_root: Path, manifest_path: Path, source_commit: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = nonlinear_package.validate_package_directory(
            repo_root=repo_root,
            out_dir=manifest_path.parent,
        )
    except Exception as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_nonlinear_execution_package_validation_failed"
        ) from exc
    if manifest_path.name != nonlinear_package.MANIFEST_NAME:
        _fail("matrix_nonlinear_execution_package_manifest_name_invalid")
    if manifest.get("source_commit_sha") != source_commit:
        _fail("matrix_nonlinear_execution_package_source_commit_mismatch")
    claims = manifest.get("claims")
    if not isinstance(claims, dict) or not (
        claims.get("exact_case_inputs") is True
        and claims.get("current_product_replay") is True
        and claims.get("external_runner_syntax_checked") is True
        and claims.get("runtime_dependency_pinned") is True
        and claims.get("output_authenticity_contract") is True
        and claims.get("external_solver_execution") is False
        and claims.get("external_reference_attached") is False
        and claims.get("verification_matrix_credit") is False
        and claims.get("verification_level_2") is False
    ):
        _fail("matrix_nonlinear_execution_package_claim_boundary_invalid")
    cases = manifest.get("cases")
    if not isinstance(cases, list):
        _fail("matrix_nonlinear_execution_package_cases_invalid")
    requirement_ids = [str(row.get("requirement_id") or "") for row in cases]
    if requirement_ids != [
        "geometric_nonlinear.p_delta",
        "geometric_nonlinear.snap_through",
        "material.steel_yield",
        "material.rc_fiber",
        "recovery.section",
        "recovery.fiber",
    ]:
        _fail("matrix_nonlinear_execution_package_requirement_set_invalid")
    return manifest, {
        "package_id": manifest["package_id"],
        "path": _relative(repo_root, manifest_path),
        "file_sha256": _file_sha256(manifest_path),
        "artifact_hash": manifest["artifact_hash"],
        "source_commit_sha": manifest["source_commit_sha"],
        "execution_workflow": {
            "repository_path": nonlinear_package.EXECUTION_WORKFLOW_PATH.as_posix(),
            "packaged_path": manifest["execution_workflow"]["path"],
            "file_sha256": manifest["execution_workflow"]["file_sha256"],
        },
        "requirement_ids": requirement_ids,
        "contract_pass": manifest.get("contract_pass") is True,
        "external_solver_execution": False,
        "verification_matrix_credit": False,
    }


def _current_source_workflow_binding(*, repo_root: Path) -> dict[str, Any]:
    workflow_path = repo_root / CURRENT_SOURCE_WORKFLOW
    if not workflow_path.is_file():
        _fail("matrix_current_source_workflow_missing")
    prepared_requirements = [
        requirement
        for requirement in REQUIREMENTS
        if isinstance(requirement.get("receipt_id"), str)
    ]
    return {
        "workflow_id": "opensees-calculix-current-source-clean-runner",
        "repository_path": CURRENT_SOURCE_WORKFLOW.as_posix(),
        "file_sha256": _file_sha256(workflow_path),
        "trigger_branch": "main",
        "external_solver_ids": ["OpenSees", "CalculiX"],
        "prepared_requirement_ids": [
            str(requirement["requirement_id"])
            for requirement in prepared_requirements
        ],
        "prepared_case_ids": sorted(
            {
                str(case_id)
                for requirement in prepared_requirements
                for case_id in requirement.get("case_ids", ())
            }
        ),
        "contract_pass": True,
        "current_source_execution_attached": False,
        "same_operator_execution_attached": False,
        "attestation_required": True,
        "attestation_attached": False,
        "independent_operator_attested": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }


def _unavailable_operator_intake_binding() -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": "signed_operator_bundle_not_attached",
        "intake_contract_pass": False,
        "fresh_external_runtime_execution": False,
        "cryptographic_signature_verified": False,
        "operator_independence_declared": False,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }


def _requirement_row(
    requirement: dict[str, Any],
    *,
    repo_root: Path,
    payloads: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    supplemental_requirement_receipts: dict[str, str],
    execution_package_requirement_ids: set[str],
    current_source_prepared_requirement_ids: set[str],
) -> dict[str, Any]:
    verification_method = str(
        requirement.get("verification_method") or "external_solver_execution"
    )
    if verification_method not in {
        "external_solver_execution",
        "independent_preflight",
    }:
        _fail("matrix_requirement_verification_method_invalid")
    receipt_id = requirement.get("receipt_id")
    if not isinstance(receipt_id, str):
        receipt_id = supplemental_requirement_receipts.get(
            str(requirement["requirement_id"])
        )
    case_ids = tuple(str(item) for item in requirement.get("case_ids", ()))
    evidence: list[dict[str, Any]] = []
    technical_present = False
    replay_pass = False
    fresh_technical = False
    fresh_external = False
    execution_package_available = (
        requirement["requirement_id"] in execution_package_requirement_ids
    )
    current_source_execution_prepared = (
        requirement["requirement_id"]
        in current_source_prepared_requirement_ids
    )
    if isinstance(receipt_id, str) and case_ids:
        payload = payloads[receipt_id]
        binding = bindings[receipt_id]
        cases = {
            str(row.get("case_id") or ""): row
            for row in payload.get("comparisons", [])
            if isinstance(row, dict)
        }
        technical_present = all(
            case_id in cases and cases[case_id].get("contract_pass") is True
            for case_id in case_ids
        )
        replay_pass = bool(technical_present and binding["current_product_replay_pass"])
        binding_fresh = bool(
            replay_pass
            and binding["fresh_current_source_external_execution"]
            and binding.get("external_execution_reused") is not True
        )
        invoked_case_ids = set(binding["external_engine_invoked_case_ids"])
        if verification_method == "external_solver_execution":
            fresh_external = bool(
                binding_fresh and set(case_ids).issubset(invoked_case_ids)
            )
            fresh_technical = fresh_external
        else:
            fresh_technical = bool(
                binding_fresh and set(case_ids).isdisjoint(invoked_case_ids)
            )
        if technical_present:
            evidence.append(
                {
                    "receipt_id": receipt_id,
                    "path": _relative(repo_root, Path(binding["path"])),
                    "artifact_hash": binding["artifact_hash"],
                    "case_ids": list(case_ids),
                }
            )
    blockers: list[str] = []
    if not technical_present:
        status = "missing"
        preparation_blocker = requirement.get("preparation_blocker")
        if isinstance(preparation_blocker, str) and preparation_blocker:
            blockers.append(preparation_blocker)
        blockers.append(
            "external_execution_package_available_but_external_result_missing"
            if execution_package_available
            else "external_technical_case_missing"
        )
    elif not fresh_technical:
        status = "current_product_replay_only"
        blockers.append(
            "fresh_current_source_external_execution_missing"
            if verification_method == "external_solver_execution"
            else "fresh_current_source_independent_preflight_missing"
        )
    elif verification_method == "independent_preflight":
        status = "fresh_independent_preflight_technical"
    else:
        status = "fresh_external_technical"
    blockers.extend(
        [
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "scientific_promotion_decision_missing",
            "formal_level2_promotion_receipt_missing",
        ]
    )
    return {
        "requirement_id": requirement["requirement_id"],
        "category": requirement["category"],
        "label": requirement["label"],
        "required_external_case_ids": list(case_ids),
        "verification_method": verification_method,
        "execution_package_available": execution_package_available,
        "current_source_execution_prepared": current_source_execution_prepared,
        "technical_reference_present": technical_present,
        "current_product_replay_pass": replay_pass,
        "fresh_current_source_technical_validation": fresh_technical,
        "fresh_current_source_external_execution": fresh_external,
        "independent_operator_attested": False,
        "legal_use_approved": False,
        "scientific_decision_pass": False,
        "formal_promotion_receipt_attached": False,
        "level2_eligible": False,
        "status": status,
        "evidence": evidence,
        "blockers": sorted(set(blockers)),
    }


def _validate_status(
    payload: dict[str, Any],
    repo_root: Path,
    *,
    verified_operator_context: dict[str, Any] | None = None,
    verified_current_build_context: dict[str, Any] | None = None,
) -> None:
    schema = _load_json(repo_root / SCHEMA_PATH, "matrix_status_schema_unreadable")
    try:
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(payload)
    except (SchemaError, ValidationError) as exc:
        raise BoundedPlanarVVMatrixError(
            "matrix_status_schema_validation_failed"
        ) from exc
    if payload["artifact_hash"] != _artifact_hash(payload):
        _fail("matrix_status_artifact_hash_invalid")
    workflow_binding = payload["current_source_workflow_binding"]
    workflow_path = repo_root / workflow_binding["repository_path"]
    if (
        not workflow_path.is_file()
        or workflow_binding["file_sha256"] != _file_sha256(workflow_path)
    ):
        _fail("matrix_status_current_source_workflow_hash_invalid")
    expected_prepared_requirement_ids = [
        str(requirement["requirement_id"])
        for requirement in REQUIREMENTS
        if isinstance(requirement.get("receipt_id"), str)
    ]
    expected_prepared_case_ids = sorted(
        {
            str(case_id)
            for requirement in REQUIREMENTS
            if isinstance(requirement.get("receipt_id"), str)
            for case_id in requirement.get("case_ids", ())
        }
    )
    if (
        workflow_binding["prepared_requirement_ids"]
        != expected_prepared_requirement_ids
        or workflow_binding["prepared_case_ids"] != expected_prepared_case_ids
    ):
        _fail("matrix_status_current_source_workflow_coverage_invalid")
    if (
        verified_operator_context is not None
        and verified_current_build_context is not None
    ):
        _fail("matrix_status_verification_context_conflict")
    expected_core_binding_rows: list[dict[str, Any]] | None = None
    if verified_current_build_context is not None:
        if set(verified_current_build_context) != {
            "receipt_bindings",
            "same_operator_supplemental_execution_binding",
            "supplemental_receipt_bindings",
        }:
            _fail("matrix_status_current_build_context_invalid")
        expected_core_binding_rows = list(
            verified_current_build_context["receipt_bindings"]
        )
    same_operator_binding = payload["same_operator_execution_binding"]
    if same_operator_binding["status"] == "attached":
        expected_binding, _fresh_payloads, fresh_bindings = (
            _validated_same_operator_execution(
                repo_root=repo_root,
                summary_path=_resolved(
                    repo_root, Path(same_operator_binding["path"])
                ),
                expected_source_commit=payload["source_commit_sha"],
                evidence_root=_clean_runner_evidence_root(
                    repo_root=repo_root,
                    summary_path=_resolved(
                        repo_root, Path(same_operator_binding["path"])
                    ),
                ),
            )
        )
        if expected_binding != same_operator_binding:
            _fail("matrix_status_same_operator_execution_binding_invalid")
        if fresh_bindings is None:
            _fail("matrix_status_same_operator_child_bindings_missing")
        expected_core_binding_rows = [
            {
                **fresh_bindings[receipt_id],
                "path": _relative(
                    repo_root, Path(fresh_bindings[receipt_id]["path"])
                ),
            }
            for receipt_id in ("code_to_code", "modal_buckling")
        ]
    supplemental_execution_binding = payload[
        "same_operator_supplemental_execution_binding"
    ]
    if (
        verified_current_build_context is not None
        and supplemental_execution_binding
        != verified_current_build_context[
            "same_operator_supplemental_execution_binding"
        ]
    ):
        _fail("matrix_status_current_build_supplemental_binding_invalid")
    if (
        supplemental_execution_binding["status"] == "attached_replay_only"
        and verified_current_build_context is not None
    ):
        if payload["supplemental_receipt_bindings"] != (
            verified_current_build_context["supplemental_receipt_bindings"]
        ):
            _fail("matrix_status_supplemental_receipt_bindings_invalid")
    elif supplemental_execution_binding["status"] == "attached_replay_only":
        (
            expected_supplemental_execution_binding,
            _supplemental_payloads,
            expected_supplemental_bindings,
            _supplemental_requirement_receipts,
        ) = _validated_same_operator_supplemental_execution(
            repo_root=repo_root,
            receipt_path=_resolved(
                repo_root, Path(supplemental_execution_binding["path"])
            ),
            expected_source_commit=payload["source_commit_sha"],
        )
        if (
            expected_supplemental_execution_binding
            != supplemental_execution_binding
        ):
            _fail(
                "matrix_status_same_operator_supplemental_execution_binding_invalid"
            )
        expected_supplemental_binding_rows = [
            {
                **expected_supplemental_bindings[receipt_id],
                "path": _relative(
                    repo_root,
                    Path(expected_supplemental_bindings[receipt_id]["path"]),
                ),
            }
            for receipt_id in (
                "same_operator_supplemental_linear",
                "same_operator_supplemental_negative",
                "same_operator_supplemental_scaling",
                "same_operator_supplemental_modal_buckling",
                "same_operator_supplemental_nonlinear_material_recovery",
            )
        ]
        if payload["supplemental_receipt_bindings"] != (
            expected_supplemental_binding_rows
        ):
            _fail("matrix_status_supplemental_receipt_bindings_invalid")
    elif (
        supplemental_execution_binding
        not in (
            _unavailable_same_operator_supplemental_execution_binding(
                "same_operator_supplemental_execution_receipt_not_attached"
            ),
            _unavailable_same_operator_supplemental_execution_binding(
                "current_source_same_operator_supplemental_package_stale"
            ),
        )
        or (
            payload["supplemental_receipt_bindings"]
            and payload["operator_intake_binding"]["status"] != "available"
        )
    ):
        _fail(
            "matrix_status_same_operator_supplemental_execution_binding_invalid"
        )
    operator_intake_binding = payload["operator_intake_binding"]
    if operator_intake_binding["status"] == "available":
        if (
            not isinstance(verified_operator_context, dict)
            or set(verified_operator_context)
            != {
                "receipt_bindings",
                "supplemental_receipt_bindings",
                "operator_intake_binding",
            }
            or verified_operator_context["operator_intake_binding"]
            != operator_intake_binding
            or verified_operator_context["receipt_bindings"]
            != payload["receipt_bindings"]
            or verified_operator_context["supplemental_receipt_bindings"]
            != payload["supplemental_receipt_bindings"]
        ):
            _fail("matrix_status_operator_intake_revalidation_required")
        expected_core_binding_rows = list(
            verified_operator_context["receipt_bindings"]
        )
    elif verified_operator_context is not None:
        _fail("matrix_status_unexpected_operator_verification_context")
    if expected_core_binding_rows is None:
        core_binding_by_id = {
            str(binding.get("receipt_id") or ""): binding
            for binding in payload["receipt_bindings"]
        }
        if set(core_binding_by_id) != {"code_to_code", "modal_buckling"}:
            _fail("matrix_status_core_receipt_binding_set_invalid")
        _host_payloads, host_bindings = _validated_receipts(
            repo_root,
            _resolved(
                repo_root, Path(core_binding_by_id["code_to_code"]["path"])
            ),
            _resolved(
                repo_root, Path(core_binding_by_id["modal_buckling"]["path"])
            ),
        )
        expected_core_binding_rows = [
            {
                **host_bindings[receipt_id],
                "path": _relative(
                    repo_root, Path(host_bindings[receipt_id]["path"])
                ),
            }
            for receipt_id in ("code_to_code", "modal_buckling")
        ]
    if payload["receipt_bindings"] != expected_core_binding_rows:
        _fail("matrix_status_core_receipt_bindings_invalid")
    execution_bindings = [
        payload["execution_package_binding"],
        *payload["supplemental_execution_package_bindings"],
    ]
    package_ids = [str(binding["package_id"]) for binding in execution_bindings]
    if len(package_ids) != len(set(package_ids)):
        _fail("matrix_status_execution_package_ids_duplicate")
    packaged_requirement_ids: set[str] = set()
    for binding in execution_bindings:
        if binding["source_commit_sha"] != payload["source_commit_sha"]:
            _fail("matrix_status_execution_package_source_commit_mismatch")
        manifest_path = repo_root / binding["path"]
        manifest = _load_json(
            manifest_path, "matrix_status_execution_package_manifest_invalid"
        )
        if (
            not manifest_path.is_file()
            or binding["file_sha256"] != _file_sha256(manifest_path)
            or binding["artifact_hash"] != manifest.get("artifact_hash")
            or manifest.get("artifact_hash") != _artifact_hash(manifest)
        ):
            _fail("matrix_status_execution_package_binding_invalid")
        workflow = binding["execution_workflow"]
        repository_workflow = repo_root / workflow["repository_path"]
        package_workflow = manifest_path.parent / workflow["packaged_path"]
        if (
            not repository_workflow.is_file()
            or not package_workflow.is_file()
            or workflow["file_sha256"] != _file_sha256(repository_workflow)
            or workflow["file_sha256"] != _file_sha256(package_workflow)
        ):
            _fail("matrix_status_execution_package_workflow_binding_invalid")
        requirement_ids = [str(item) for item in binding["requirement_ids"]]
        if packaged_requirement_ids.intersection(requirement_ids):
            _fail("matrix_status_execution_package_requirement_overlap")
        packaged_requirement_ids.update(requirement_ids)
    ids = [row["requirement_id"] for row in payload["requirements"]]
    if len(ids) != len(set(ids)):
        _fail("matrix_status_requirement_ids_duplicate")
    expected_ids = [str(row["requirement_id"]) for row in REQUIREMENTS]
    if ids != expected_ids:
        _fail("matrix_status_requirement_set_invalid")
    rows = payload["requirements"]
    core_bindings = payload["receipt_bindings"]
    supplemental_bindings = payload["supplemental_receipt_bindings"]
    if any(
        binding["external_execution_reused"] is True
        and binding["fresh_current_source_external_execution"] is True
        for binding in supplemental_bindings
    ):
        _fail("matrix_status_supplemental_reused_fresh_conflict")
    all_bindings = [*core_bindings, *supplemental_bindings]
    binding_ids = [str(binding["receipt_id"]) for binding in all_bindings]
    if len(binding_ids) != len(set(binding_ids)):
        _fail("matrix_status_receipt_binding_ids_duplicate")
    binding_by_id = {
        str(binding["receipt_id"]): binding for binding in all_bindings
    }
    if any(
        binding["source_commit_sha"] != payload["source_commit_sha"]
        for binding in all_bindings
    ):
        _fail("matrix_status_receipt_source_commit_mismatch")
    expected_case_ids = {
        str(requirement["requirement_id"]): [
            str(case_id) for case_id in requirement.get("case_ids", ())
        ]
        for requirement in REQUIREMENTS
    }
    expected_summary = {
        "requirement_count": len(rows),
        "technical_reference_present_count": sum(
            1 for row in rows if row["technical_reference_present"]
        ),
        "fresh_current_source_technical_count": sum(
            1
            for row in rows
            if row["fresh_current_source_technical_validation"]
        ),
        "current_product_replay_only_count": sum(
            1 for row in rows if row["status"] == "current_product_replay_only"
        ),
        "fresh_external_technical_count": sum(
            1 for row in rows if row["status"] == "fresh_external_technical"
        ),
        "fresh_independent_preflight_technical_count": sum(
            1
            for row in rows
            if row["status"] == "fresh_independent_preflight_technical"
        ),
        "promotion_eligible_count": sum(
            1 for row in rows if row["status"] == "promotion_eligible"
        ),
        "missing_count": sum(1 for row in rows if row["status"] == "missing"),
        "execution_package_available_count": sum(
            1 for row in rows if row["execution_package_available"]
        ),
        "current_source_execution_prepared_count": sum(
            1 for row in rows if row["current_source_execution_prepared"]
        ),
    }
    if payload["summary"] != expected_summary:
        _fail("matrix_status_summary_invalid")
    for row in rows:
        requirement_id = str(row["requirement_id"])
        required_case_ids = row["required_external_case_ids"]
        expected_verification_method = str(
            next(
                requirement
                for requirement in REQUIREMENTS
                if requirement["requirement_id"] == requirement_id
            ).get("verification_method")
            or "external_solver_execution"
        )
        if required_case_ids != expected_case_ids[requirement_id] or not required_case_ids:
            _fail("matrix_status_required_case_set_invalid")
        if row["verification_method"] != expected_verification_method:
            _fail("matrix_status_verification_method_invalid")
        if row["technical_reference_present"] is not bool(row["evidence"]):
            _fail("matrix_status_evidence_presence_invalid")
        if row["execution_package_available"] is not (
            requirement_id in packaged_requirement_ids
        ):
            _fail("matrix_status_execution_package_availability_invalid")
        if row["current_source_execution_prepared"] is not (
            requirement_id in set(expected_prepared_requirement_ids)
        ):
            _fail("matrix_status_current_source_execution_prepared_invalid")
        if row["status"] == "missing" and row["technical_reference_present"]:
            _fail("matrix_status_missing_row_has_technical_evidence")
        if row["status"] == "current_product_replay_only" and not (
            row["technical_reference_present"]
            and row["current_product_replay_pass"]
            and not row["fresh_current_source_technical_validation"]
        ):
            _fail("matrix_status_replay_only_row_invalid")
        if row["status"] == "fresh_external_technical" and not (
            row["technical_reference_present"]
            and row["current_product_replay_pass"]
            and row["fresh_current_source_technical_validation"]
            and row["fresh_current_source_external_execution"]
            and row["verification_method"] == "external_solver_execution"
        ):
            _fail("matrix_status_fresh_external_row_invalid")
        if row["status"] == "fresh_independent_preflight_technical" and not (
            row["technical_reference_present"]
            and row["current_product_replay_pass"]
            and row["fresh_current_source_technical_validation"]
            and not row["fresh_current_source_external_execution"]
            and row["verification_method"] == "independent_preflight"
        ):
            _fail("matrix_status_fresh_preflight_row_invalid")
        evidence_case_ids: set[str] = set()
        evidence_bindings: list[dict[str, Any]] = []
        for evidence in row["evidence"]:
            receipt_id = str(evidence["receipt_id"])
            binding = binding_by_id.get(receipt_id)
            if binding is None:
                _fail("matrix_status_evidence_receipt_binding_missing")
            if (
                evidence["path"] != binding["path"]
                or evidence["artifact_hash"] != binding["artifact_hash"]
                or not set(evidence["case_ids"]).issubset(set(binding["case_ids"]))
            ):
                _fail("matrix_status_evidence_receipt_binding_invalid")
            evidence_case_ids.update(str(case_id) for case_id in evidence["case_ids"])
            evidence_bindings.append(binding)
        if row["technical_reference_present"] and evidence_case_ids != set(
            required_case_ids
        ):
            _fail("matrix_status_evidence_case_set_invalid")
        if evidence_bindings:
            binding_replay = all(
                binding["current_product_replay_pass"]
                for binding in evidence_bindings
            )
            binding_fresh = bool(
                binding_replay
                and all(
                    binding["fresh_current_source_external_execution"]
                    and binding.get("external_execution_reused") is not True
                    for binding in evidence_bindings
                )
            )
            invoked_case_ids = {
                case_id
                for binding in evidence_bindings
                for case_id in binding["external_engine_invoked_case_ids"]
            }
            expected_external = bool(
                binding_fresh
                and row["verification_method"] == "external_solver_execution"
                and set(required_case_ids).issubset(invoked_case_ids)
            )
            expected_fresh_technical = bool(
                expected_external
                if row["verification_method"] == "external_solver_execution"
                else binding_fresh
                and set(required_case_ids).isdisjoint(invoked_case_ids)
            )
            if (
                not all(
                    binding["technical_contract_pass"]
                    for binding in evidence_bindings
                )
                or row["current_product_replay_pass"] is not binding_replay
                or row["fresh_current_source_technical_validation"]
                is not expected_fresh_technical
                or row["fresh_current_source_external_execution"]
                is not expected_external
            ):
                _fail("matrix_status_evidence_authority_invalid")
        if row["level2_eligible"] is True:
            required = (
                (
                    row["fresh_current_source_external_execution"]
                    if row["verification_method"] == "external_solver_execution"
                    else row["fresh_current_source_technical_validation"]
                ),
                row["independent_operator_attested"],
                row["legal_use_approved"],
                row["scientific_decision_pass"],
                row["formal_promotion_receipt_attached"],
            )
            if not all(required) or row["status"] != "promotion_eligible":
                _fail("matrix_status_level2_eligibility_invalid")
    claims = payload["claims"]
    if claims["recommended_matrix_technical_coverage_complete"] is not all(
        row["technical_reference_present"] for row in rows
    ):
        _fail("matrix_status_technical_coverage_claim_invalid")
    if claims["fresh_current_source_technical_matrix_complete"] is not all(
        row["fresh_current_source_technical_validation"] for row in rows
    ):
        _fail("matrix_status_fresh_technical_coverage_claim_invalid")
    external_rows = [
        row
        for row in rows
        if row["verification_method"] == "external_solver_execution"
    ]
    if claims["fresh_current_source_external_matrix_complete"] is not all(
        row["fresh_current_source_external_execution"] for row in external_rows
    ):
        _fail("matrix_status_fresh_external_coverage_claim_invalid")


def build_bounded_planar_external_vv_matrix(
    *,
    repo_root: Path = ROOT,
    code_receipt_path: Path = DEFAULT_CODE_RECEIPT,
    modal_receipt_path: Path = DEFAULT_MODAL_RECEIPT,
    linear_case_package_path: Path = DEFAULT_LINEAR_CASE_PACKAGE,
    negative_case_package_path: Path = DEFAULT_NEGATIVE_CASE_PACKAGE,
    scaling_case_package_path: Path = DEFAULT_SCALING_CASE_PACKAGE,
    modal_buckling_case_package_path: Path = DEFAULT_MODAL_BUCKLING_CASE_PACKAGE,
    nonlinear_case_package_path: Path = DEFAULT_NONLINEAR_CASE_PACKAGE,
    clean_runner_summary_path: Path = DEFAULT_CLEAN_RUNNER_SUMMARY,
    same_operator_supplemental_receipt_path: Path = (
        DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
    ),
) -> dict[str, Any]:
    """Build current evidence coverage without promoting missing authority."""

    code_path = _resolved(repo_root, code_receipt_path)
    modal_path = _resolved(repo_root, modal_receipt_path)
    resolved_clean_runner_summary = _resolved(
        repo_root, clean_runner_summary_path
    )
    if resolved_clean_runner_summary.is_file():
        clean_runner_header = _load_json(
            resolved_clean_runner_summary,
            "matrix_clean_runner_summary_invalid",
        )
        clean_runner_source_commit = str(
            clean_runner_header.get("source_commit_sha") or ""
        )
    else:
        clean_runner_source_commit = ""
    same_operator_execution_binding, fresh_payloads, fresh_bindings = (
        _validated_same_operator_execution(
            repo_root=repo_root,
            summary_path=resolved_clean_runner_summary,
            expected_source_commit=clean_runner_source_commit,
            evidence_root=_clean_runner_evidence_root(
                repo_root=repo_root,
                summary_path=resolved_clean_runner_summary,
            ),
        )
    )
    if fresh_payloads is not None and fresh_bindings is not None:
        payloads = fresh_payloads
        bindings = fresh_bindings
        source_commit = clean_runner_source_commit
    else:
        payloads, bindings = _validated_receipts(repo_root, code_path, modal_path)
        # Preserve only each host receipt's explicit fresh/reused provenance.
        # The separate same-operator clean-runner binding remains unavailable,
        # so local execution cannot inherit container-isolation authority.
        source_commit = str(payloads["code_to_code"]["source_commit_sha"])
    resolved_same_operator_supplemental = _resolved(
        repo_root, same_operator_supplemental_receipt_path
    )
    (
        same_operator_supplemental_execution_binding,
        supplemental_payloads,
        supplemental_bindings,
        supplemental_requirement_receipts,
    ) = _validated_same_operator_supplemental_execution(
        repo_root=repo_root,
        receipt_path=resolved_same_operator_supplemental,
        expected_source_commit=source_commit,
    )
    row_payloads = {**payloads, **supplemental_payloads}
    row_bindings = {**bindings, **supplemental_bindings}
    package_path = _resolved(repo_root, linear_case_package_path)
    _package, package_binding = _validated_execution_package(
        repo_root=repo_root,
        manifest_path=package_path,
        source_commit=source_commit,
    )
    negative_path = _resolved(repo_root, negative_case_package_path)
    _negative_package, negative_package_binding = (
        _validated_negative_execution_package(
            repo_root=repo_root,
            manifest_path=negative_path,
            source_commit=source_commit,
        )
    )
    scaling_path = _resolved(repo_root, scaling_case_package_path)
    _scaling_package, scaling_package_binding = (
        _validated_scaling_execution_package(
            repo_root=repo_root,
            manifest_path=scaling_path,
            source_commit=source_commit,
        )
    )
    modal_buckling_path = _resolved(repo_root, modal_buckling_case_package_path)
    _modal_buckling_package, modal_buckling_package_binding = (
        _validated_modal_buckling_execution_package(
            repo_root=repo_root,
            manifest_path=modal_buckling_path,
            source_commit=source_commit,
        )
    )
    nonlinear_path = _resolved(repo_root, nonlinear_case_package_path)
    _nonlinear_package, nonlinear_package_binding = (
        _validated_nonlinear_execution_package(
            repo_root=repo_root,
            manifest_path=nonlinear_path,
            source_commit=source_commit,
        )
    )
    package_requirement_ids = {
        *package_binding["requirement_ids"],
        *negative_package_binding["requirement_ids"],
        *scaling_package_binding["requirement_ids"],
        *modal_buckling_package_binding["requirement_ids"],
        *nonlinear_package_binding["requirement_ids"],
    }
    current_source_workflow_binding = _current_source_workflow_binding(
        repo_root=repo_root
    )
    current_source_prepared_requirement_ids = set(
        current_source_workflow_binding["prepared_requirement_ids"]
    )
    rows = [
        _requirement_row(
            dict(requirement),
            repo_root=repo_root,
            payloads=row_payloads,
            bindings=row_bindings,
            supplemental_requirement_receipts=(
                supplemental_requirement_receipts
            ),
            execution_package_requirement_ids=package_requirement_ids,
            current_source_prepared_requirement_ids=(
                current_source_prepared_requirement_ids
            ),
        )
        for requirement in REQUIREMENTS
    ]
    technical_count = sum(1 for row in rows if row["technical_reference_present"])
    fresh_technical_count = sum(
        1 for row in rows if row["fresh_current_source_technical_validation"]
    )
    replay_only_count = sum(
        1 for row in rows if row["status"] == "current_product_replay_only"
    )
    fresh_count = sum(1 for row in rows if row["status"] == "fresh_external_technical")
    fresh_preflight_count = sum(
        1
        for row in rows
        if row["status"] == "fresh_independent_preflight_technical"
    )
    missing_count = sum(1 for row in rows if row["status"] == "missing")
    matrix_complete = technical_count == len(rows)
    fresh_technical_complete = bool(
        matrix_complete
        and all(
            row["fresh_current_source_technical_validation"] for row in rows
        )
    )
    fresh_external_complete = bool(
        matrix_complete
        and all(
            row["fresh_current_source_external_execution"]
            for row in rows
            if row["verification_method"] == "external_solver_execution"
        )
    )
    blockers = [
        *(["recommended_external_vv_matrix_incomplete"] if not matrix_complete else []),
        *(
            ["fresh_current_source_technical_matrix_incomplete"]
            if not fresh_technical_complete
            else []
        ),
        *(
            ["fresh_current_source_external_matrix_incomplete"]
            if not fresh_external_complete
            else []
        ),
        "independent_operator_attestation_missing",
        "product_legal_license_approval_missing",
        "scientific_promotion_decision_missing",
        "formal_level2_promotion_receipt_missing",
        "bounded_planar_profile_level2_not_achieved",
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_commit,
        "receipt_bindings": [
            {
                **bindings[receipt_id],
                "path": _relative(repo_root, Path(bindings[receipt_id]["path"])),
            }
            for receipt_id in ("code_to_code", "modal_buckling")
        ],
        "supplemental_receipt_bindings": [
            {
                **supplemental_bindings[receipt_id],
                "path": _relative(
                    repo_root, Path(supplemental_bindings[receipt_id]["path"])
                ),
            }
            for receipt_id in (
                "same_operator_supplemental_linear",
                "same_operator_supplemental_negative",
                "same_operator_supplemental_scaling",
                "same_operator_supplemental_modal_buckling",
                "same_operator_supplemental_nonlinear_material_recovery",
            )
            if receipt_id in supplemental_bindings
        ],
        "execution_package_binding": package_binding,
        "supplemental_execution_package_bindings": [
            negative_package_binding,
            scaling_package_binding,
            modal_buckling_package_binding,
            nonlinear_package_binding,
        ],
        "current_source_workflow_binding": current_source_workflow_binding,
        "same_operator_execution_binding": same_operator_execution_binding,
        "same_operator_supplemental_execution_binding": (
            same_operator_supplemental_execution_binding
        ),
        "operator_intake_binding": _unavailable_operator_intake_binding(),
        "requirements": rows,
        "summary": {
            "requirement_count": len(rows),
            "technical_reference_present_count": technical_count,
            "fresh_current_source_technical_count": fresh_technical_count,
            "current_product_replay_only_count": replay_only_count,
            "fresh_external_technical_count": fresh_count,
            "fresh_independent_preflight_technical_count": (
                fresh_preflight_count
            ),
            "promotion_eligible_count": 0,
            "missing_count": missing_count,
            "execution_package_available_count": sum(
                1 for row in rows if row["execution_package_available"]
            ),
            "current_source_execution_prepared_count": sum(
                1 for row in rows if row["current_source_execution_prepared"]
            ),
        },
        "status": "blocked",
        "contract_pass": True,
        "blockers": sorted(set(blockers)),
        "claims": {
            "recommended_matrix_technical_coverage_complete": matrix_complete,
            "fresh_current_source_technical_matrix_complete": (
                fresh_technical_complete
            ),
            "fresh_current_source_external_matrix_complete": (
                fresh_external_complete
            ),
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "formal_promotion_receipt_attached": False,
            "bounded_planar_profile_level_2": False,
        },
        "claim_boundary": (
            "This status validates current-source product replay and enumerates exact "
            "technical external case coverage for the bounded planar recommendation "
            "matrix. Fresh technical coverage distinguishes actual external-engine "
            "execution from an explicitly non-engine independent preflight; the latter "
            "cannot be described or counted as external solver execution. A checksum-bound "
            "same-operator receipt may establish these exact technical rows, but it does "
            "not establish "
            "independent operation, legal approval, scientific promotion, Verification "
            "Level 2, design authority, commercial equivalence, or release readiness."
        ),
        "artifact_hash": "sha256:" + "0" * 64,
    }
    payload["artifact_hash"] = _artifact_hash(payload)
    _validate_status(
        payload,
        repo_root,
        verified_current_build_context={
            "receipt_bindings": payload["receipt_bindings"],
            "same_operator_supplemental_execution_binding": payload[
                "same_operator_supplemental_execution_binding"
            ],
            "supplemental_receipt_bindings": payload[
                "supplemental_receipt_bindings"
            ],
        },
    )
    return payload


def write_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    code_receipt_path: Path = DEFAULT_CODE_RECEIPT,
    modal_receipt_path: Path = DEFAULT_MODAL_RECEIPT,
    clean_runner_summary_path: Path = DEFAULT_CLEAN_RUNNER_SUMMARY,
    same_operator_supplemental_receipt_path: Path = (
        DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
    ),
) -> dict[str, Any]:
    payload = build_bounded_planar_external_vv_matrix(
        repo_root=repo_root,
        code_receipt_path=code_receipt_path,
        modal_receipt_path=modal_receipt_path,
        clean_runner_summary_path=clean_runner_summary_path,
        same_operator_supplemental_receipt_path=(
            same_operator_supplemental_receipt_path
        ),
    )
    target = _resolved(repo_root, out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def check_status(
    *,
    repo_root: Path = ROOT,
    out_path: Path = DEFAULT_OUT,
    code_receipt_path: Path = DEFAULT_CODE_RECEIPT,
    modal_receipt_path: Path = DEFAULT_MODAL_RECEIPT,
    clean_runner_summary_path: Path = DEFAULT_CLEAN_RUNNER_SUMMARY,
    same_operator_supplemental_receipt_path: Path = (
        DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT
    ),
) -> tuple[bool, str]:
    target = _resolved(repo_root, out_path)
    if not target.exists():
        return False, "bounded_planar_external_vv_matrix_status_missing"
    expected = build_bounded_planar_external_vv_matrix(
        repo_root=repo_root,
        code_receipt_path=code_receipt_path,
        modal_receipt_path=modal_receipt_path,
        clean_runner_summary_path=clean_runner_summary_path,
        same_operator_supplemental_receipt_path=(
            same_operator_supplemental_receipt_path
        ),
    )
    actual = _load_json(target, "bounded_planar_external_vv_matrix_status_invalid")
    if actual != expected:
        return False, "bounded_planar_external_vv_matrix_status_mismatch"
    return True, "bounded_planar_external_vv_matrix_status_consistent"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--code-receipt", type=Path, default=DEFAULT_CODE_RECEIPT
    )
    parser.add_argument(
        "--modal-receipt", type=Path, default=DEFAULT_MODAL_RECEIPT
    )
    parser.add_argument(
        "--clean-runner-summary",
        type=Path,
        default=DEFAULT_CLEAN_RUNNER_SUMMARY,
    )
    parser.add_argument(
        "--same-operator-supplemental-receipt",
        type=Path,
        default=DEFAULT_SAME_OPERATOR_SUPPLEMENTAL_RECEIPT,
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        ok, message = check_status(
            out_path=args.out,
            code_receipt_path=args.code_receipt,
            modal_receipt_path=args.modal_receipt,
            clean_runner_summary_path=args.clean_runner_summary,
            same_operator_supplemental_receipt_path=(
                args.same_operator_supplemental_receipt
            ),
        )
        print(message)
        return 0 if ok else 1
    payload = write_status(
        out_path=args.out,
        code_receipt_path=args.code_receipt,
        modal_receipt_path=args.modal_receipt,
        clean_runner_summary_path=args.clean_runner_summary,
        same_operator_supplemental_receipt_path=(
            args.same_operator_supplemental_receipt
        ),
    )
    summary = payload["summary"]
    print(
        "bounded planar external V&V matrix: blocked | "
        f"technical={summary['technical_reference_present_count']}/"
        f"{summary['requirement_count']} | "
        f"fresh_technical={summary['fresh_current_source_technical_count']} | "
        f"external_engine={summary['fresh_external_technical_count']} | "
        f"preflight={summary['fresh_independent_preflight_technical_count']} | "
        f"eligible={summary['promotion_eligible_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
