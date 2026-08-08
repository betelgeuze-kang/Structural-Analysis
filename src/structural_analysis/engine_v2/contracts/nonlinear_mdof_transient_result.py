"""Authoritative ResultIR for bounded nonlinear MDOF transient histories."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from typing import Any

from jsonschema import Draft202012Validator

from ._canonical import canonical_hash


NONLINEAR_MDOF_RESULT_IR_SCHEMA_VERSION = "structural-analysis-nonlinear-mdof-result-ir.v1"
NONLINEAR_MDOF_AUTHORITY_PROFILE = "authoritative_source_authenticated_nonlinear_mdof_history.v1"
NONLINEAR_MDOF_STORAGE_PROFILE = "inline_time_major_vector_material_fp64_si.v1"
NONLINEAR_MDOF_CLAIM_BOUNDARY = (
    "Authoritative bounded force-driven nonlinear MDOF displacement, velocity, "
    "acceleration, story force, energy, and committed bilinear material history "
    "with source-authenticated checkpoint replay. Support excitation, shell, "
    "contact, engineering design, and release readiness are outside this contract."
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class NonlinearMDOFResultIRError(ValueError):
    pass


@dataclass(frozen=True)
class NonlinearMDOFResultIR:
    result_id: str
    model_ir_content_hash: str
    force_history_hash: str
    solver_id: str
    solver_result_hash: str
    integration_contract_hash: str
    terminal_checkpoint_hash: str
    checkpoint_authority_receipt_hash: str
    dof_ids: tuple[str, ...]
    story_ids: tuple[str, ...]
    time_step_s: float
    residual_relative_tolerance: float
    samples: tuple[Mapping[str, Any], ...]
    terminal_story_material_states: tuple[Mapping[str, Any], ...]
    result_hash: str
    schema_version: str = NONLINEAR_MDOF_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_nonlinear_mdof_result_ir(
    *, result_id: str, model_ir_content_hash: str, force_history_hash: str,
    solver_id: str, solver_result_hash: str, integration_contract_hash: str,
    terminal_checkpoint_hash: str, checkpoint_authority_receipt_hash: str,
    dof_ids: Sequence[str], story_ids: Sequence[str], time_step_s: float,
    residual_relative_tolerance: float, samples: Sequence[Mapping[str, Any]],
    terminal_story_material_states: Sequence[Mapping[str, Any]],
) -> NonlinearMDOFResultIR:
    provisional = NonlinearMDOFResultIR(
        result_id=str(result_id), model_ir_content_hash=str(model_ir_content_hash),
        force_history_hash=str(force_history_hash), solver_id=str(solver_id),
        solver_result_hash=str(solver_result_hash), integration_contract_hash=str(integration_contract_hash),
        terminal_checkpoint_hash=str(terminal_checkpoint_hash),
        checkpoint_authority_receipt_hash=str(checkpoint_authority_receipt_hash),
        dof_ids=tuple(map(str, dof_ids)), story_ids=tuple(map(str, story_ids)),
        time_step_s=float(time_step_s), residual_relative_tolerance=float(residual_relative_tolerance),
        samples=tuple(_normalize_sample(row) for row in samples),
        terminal_story_material_states=tuple(_normalize_state(row) for row in terminal_story_material_states),
        result_hash="sha256:" + "0" * 64,
    )
    result = replace(provisional, result_hash=canonical_hash(_payload(provisional, include_result_hash=False)))
    return validate_nonlinear_mdof_result_ir(result)


def validate_nonlinear_mdof_result_ir(result: NonlinearMDOFResultIR) -> NonlinearMDOFResultIR:
    if type(result) is not NonlinearMDOFResultIR:
        raise NonlinearMDOFResultIRError("nonlinear_mdof_result_type_invalid")
    if result.schema_version != NONLINEAR_MDOF_RESULT_IR_SCHEMA_VERSION:
        raise NonlinearMDOFResultIRError("schema_version_invalid")
    for value in (result.result_id, result.solver_id, *result.dof_ids, *result.story_ids):
        if _ID.fullmatch(value) is None:
            raise NonlinearMDOFResultIRError("stable_id_invalid")
    if len(result.dof_ids) < 2 or len(result.story_ids) != len(result.dof_ids) or len(set(result.dof_ids)) != len(result.dof_ids) or len(set(result.story_ids)) != len(result.story_ids):
        raise NonlinearMDOFResultIRError("dof_story_identity_invalid")
    for value in (
        result.model_ir_content_hash, result.force_history_hash, result.solver_result_hash,
        result.integration_contract_hash, result.terminal_checkpoint_hash,
        result.checkpoint_authority_receipt_hash, result.result_hash,
    ):
        if _HASH.fullmatch(value) is None:
            raise NonlinearMDOFResultIRError("hash_invalid")
    if not math.isfinite(result.time_step_s) or result.time_step_s <= 0.0 or not math.isfinite(result.residual_relative_tolerance) or result.residual_relative_tolerance <= 0.0:
        raise NonlinearMDOFResultIRError("solver_tolerance_invalid")
    if not result.samples:
        raise NonlinearMDOFResultIRError("history_empty")
    vector_fields = (
        "applied_force_n", "displacement_m", "velocity_m_per_s",
        "acceleration_m_per_s2", "story_drift_m", "story_force_n",
        "equilibrium_residual_n",
    )
    for index, row in enumerate(result.samples):
        if row["step_index"] != index or not math.isclose(row["time_s"], index * result.time_step_s, rel_tol=0.0, abs_tol=1.0e-12):
            raise NonlinearMDOFResultIRError("history_index_invalid")
        if any(len(row[field]) != len(result.dof_ids) or any(not math.isfinite(value) for value in row[field]) for field in vector_fields):
            raise NonlinearMDOFResultIRError("history_vector_invalid")
        if row["relative_residual"] < 0.0 or row["relative_residual"] > result.residual_relative_tolerance:
            raise NonlinearMDOFResultIRError("history_residual_failed")
        scalars = tuple(row[key] for key in (
            "kinetic_energy_j", "stored_energy_j", "external_work_j",
            "damping_dissipation_j", "plastic_dissipation_j", "energy_balance_error_j",
        ))
        if any(not math.isfinite(value) for value in scalars) or min(row["kinetic_energy_j"], row["stored_energy_j"], row["damping_dissipation_j"], row["plastic_dissipation_j"]) < 0.0:
            raise NonlinearMDOFResultIRError("history_energy_invalid")
        if row["newton_iterations"] < 0 or row["yielded_story_count"] < 0:
            raise NonlinearMDOFResultIRError("history_iteration_invalid")
    if len(result.terminal_story_material_states) != len(result.story_ids):
        raise NonlinearMDOFResultIRError("terminal_material_state_count_invalid")
    if any(state["story_id"] != result.story_ids[index] for index, state in enumerate(result.terminal_story_material_states)):
        raise NonlinearMDOFResultIRError("terminal_material_state_identity_invalid")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        raise NonlinearMDOFResultIRError("result_hash_mismatch")
    validate_nonlinear_mdof_result_ir_manifest(result.to_manifest())
    return result


def validate_nonlinear_mdof_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(_schema_validator().iter_errors(payload), key=lambda error: tuple(map(str, error.absolute_path)))
    if errors:
        error = errors[0]
        raise NonlinearMDOFResultIRError(f"schema_invalid@/{'/'.join(map(str, error.absolute_path))}:{error.message}")
    return payload


def _normalize_sample(row: Mapping[str, Any]) -> Mapping[str, Any]:
    vector_fields = (
        "applied_force_n", "displacement_m", "velocity_m_per_s",
        "acceleration_m_per_s2", "story_drift_m", "story_force_n",
        "equilibrium_residual_n",
    )
    payload: dict[str, Any] = {field: [float(value) for value in row[field]] for field in vector_fields}
    payload.update({
        "step_index": int(row["step_index"]), "time_s": float(row["time_s"]),
        "relative_residual": float(row["relative_residual"]),
        "newton_iterations": int(row["newton_iterations"]),
        "yielded_story_count": int(row["yielded_story_count"]),
    })
    for key in (
        "kinetic_energy_j", "stored_energy_j", "external_work_j",
        "damping_dissipation_j", "plastic_dissipation_j", "energy_balance_error_j",
    ):
        payload[key] = float(row[key])
    return payload


def _normalize_state(row: Mapping[str, Any]) -> Mapping[str, Any]:
    return {
        "story_id": str(row["story_id"]),
        "plastic_displacement_m": float(row["plastic_displacement_m"]),
        "backstress_n": float(row["backstress_n"]),
        "cumulative_plastic_displacement_m": float(row["cumulative_plastic_displacement_m"]),
        "plastic_dissipation_j": float(row["plastic_dissipation_j"]),
    }


def _payload(result: NonlinearMDOFResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version, "result_id": result.result_id,
        "analysis_type": "nonlinear_mdof_transient",
        "authority": {
            "profile": NONLINEAR_MDOF_AUTHORITY_PROFILE, "response_history": "authoritative",
            "material_state": "authoritative", "checkpoint": "source_authenticated",
            "engineering_design": "not_authoritative", "release_readiness": "not_authoritative",
        },
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "force_history_hash": result.force_history_hash,
            "solver_result_hash": result.solver_result_hash,
            "integration_contract_hash": result.integration_contract_hash,
        },
        "solver": {
            "solver_id": result.solver_id, "time_step_s": result.time_step_s,
            "residual_relative_tolerance": result.residual_relative_tolerance,
            "fallback_used": False, "regularization_used": False,
        },
        "dof_ids": list(result.dof_ids), "story_ids": list(result.story_ids),
        "storage_profile": NONLINEAR_MDOF_STORAGE_PROFILE,
        "history": [dict(row) for row in result.samples],
        "terminal_story_material_states": [dict(row) for row in result.terminal_story_material_states],
        "checkpoint": {
            "authority": "source_authenticated_checkpoint",
            "terminal_checkpoint_hash": result.terminal_checkpoint_hash,
            "authority_receipt_hash": result.checkpoint_authority_receipt_hash,
        },
        "claim_boundary": NONLINEAR_MDOF_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = resources.files("structural_analysis.schemas").joinpath("nonlinear_mdof_transient_result_ir_v1.schema.json")
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "NONLINEAR_MDOF_AUTHORITY_PROFILE", "NONLINEAR_MDOF_CLAIM_BOUNDARY",
    "NONLINEAR_MDOF_RESULT_IR_SCHEMA_VERSION", "NONLINEAR_MDOF_STORAGE_PROFILE",
    "NonlinearMDOFResultIR", "NonlinearMDOFResultIRError",
    "create_nonlinear_mdof_result_ir", "validate_nonlinear_mdof_result_ir",
    "validate_nonlinear_mdof_result_ir_manifest",
]
