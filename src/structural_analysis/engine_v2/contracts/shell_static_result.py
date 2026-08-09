"""Authoritative ResultIR for bounded linear shell static analysis."""

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


SHELL_RESULT_IR_SCHEMA_VERSION = "structural-analysis-shell-result-ir.v1"
SHELL_AUTHORITY_PROFILE = "authoritative_linear_cst_membrane_mindlin_shell.v1"
SHELL_CLAIM_BOUNDARY = (
    "Authoritative bounded small-displacement linear three-node shell displacement, "
    "reaction, physical equilibrium residual, membrane, bending, transverse shear, "
    "and exact checkpoint result. Shell nonlinearities, higher-order elements, "
    "openings, contact, engineering design, and release readiness are outside this contract."
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class ShellResultIRError(ValueError):
    pass


@dataclass(frozen=True)
class ShellResultIR:
    result_id: str
    model_ir_content_hash: str
    solver_result_hash: str
    stiffness_hash: str
    load_hash: str
    terminal_checkpoint_hash: str
    solver_id: str
    node_ids: tuple[str, ...]
    element_ids: tuple[str, ...]
    displacement_global: tuple[float, ...]
    reaction_global_n_nm: tuple[float, ...]
    equilibrium_residual_global_n_nm: tuple[float, ...]
    element_results: tuple[Mapping[str, Any], ...]
    maximum_free_residual: float
    strain_energy_j: float
    external_work_j: float
    result_hash: str
    schema_version: str = SHELL_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_shell_result_ir(
    *, result_id: str, model_ir_content_hash: str, solver_result_hash: str,
    stiffness_hash: str, load_hash: str, terminal_checkpoint_hash: str,
    solver_id: str, node_ids: Sequence[str], element_ids: Sequence[str],
    displacement_global: Sequence[float], reaction_global_n_nm: Sequence[float],
    equilibrium_residual_global_n_nm: Sequence[float],
    element_results: Sequence[Mapping[str, Any]], maximum_free_residual: float,
    strain_energy_j: float, external_work_j: float,
) -> ShellResultIR:
    provisional = ShellResultIR(
        result_id=str(result_id), model_ir_content_hash=str(model_ir_content_hash),
        solver_result_hash=str(solver_result_hash), stiffness_hash=str(stiffness_hash),
        load_hash=str(load_hash), terminal_checkpoint_hash=str(terminal_checkpoint_hash),
        solver_id=str(solver_id), node_ids=tuple(map(str, node_ids)),
        element_ids=tuple(map(str, element_ids)),
        displacement_global=tuple(map(float, displacement_global)),
        reaction_global_n_nm=tuple(map(float, reaction_global_n_nm)),
        equilibrium_residual_global_n_nm=tuple(map(float, equilibrium_residual_global_n_nm)),
        element_results=tuple(_element(row) for row in element_results),
        maximum_free_residual=float(maximum_free_residual),
        strain_energy_j=float(strain_energy_j), external_work_j=float(external_work_j),
        result_hash="sha256:" + "0" * 64,
    )
    result = replace(provisional, result_hash=canonical_hash(_payload(provisional, include_result_hash=False)))
    return validate_shell_result_ir(result)


def validate_shell_result_ir(result: ShellResultIR) -> ShellResultIR:
    if type(result) is not ShellResultIR or result.schema_version != SHELL_RESULT_IR_SCHEMA_VERSION:
        raise ShellResultIRError("shell_result_type_or_version_invalid")
    if any(_ID.fullmatch(value) is None for value in (result.result_id, result.solver_id, *result.node_ids, *result.element_ids)):
        raise ShellResultIRError("stable_id_invalid")
    if len(result.node_ids) < 3 or len(set(result.node_ids)) != len(result.node_ids) or not result.element_ids or len(set(result.element_ids)) != len(result.element_ids):
        raise ShellResultIRError("entity_identity_invalid")
    if any(_HASH.fullmatch(value) is None for value in (
        result.model_ir_content_hash, result.solver_result_hash, result.stiffness_hash,
        result.load_hash, result.terminal_checkpoint_hash, result.result_hash,
    )):
        raise ShellResultIRError("hash_invalid")
    dof_count = 6 * len(result.node_ids)
    vectors = (result.displacement_global, result.reaction_global_n_nm, result.equilibrium_residual_global_n_nm)
    if any(len(row) != dof_count or any(not math.isfinite(value) for value in row) for row in vectors):
        raise ShellResultIRError("nodal_vector_invalid")
    if len(result.element_results) != len(result.element_ids) or any(row["element_id"] != result.element_ids[index] for index, row in enumerate(result.element_results)):
        raise ShellResultIRError("element_result_identity_invalid")
    if any(not math.isfinite(value) for value in (result.maximum_free_residual, result.strain_energy_j, result.external_work_j)) or min(result.maximum_free_residual, result.strain_energy_j, result.external_work_j) < 0.0:
        raise ShellResultIRError("result_scalar_invalid")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        raise ShellResultIRError("result_hash_mismatch")
    validate_shell_result_ir_manifest(result.to_manifest())
    return result


def validate_shell_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(_schema_validator().iter_errors(payload), key=lambda error: tuple(map(str, error.absolute_path)))
    if errors:
        error = errors[0]
        raise ShellResultIRError(f"schema_invalid@/{'/'.join(map(str, error.absolute_path))}:{error.message}")
    return payload


def _vector(row: Mapping[str, Any], key: str, size: int) -> list[float]:
    values = [float(value) for value in row[key]]
    if len(values) != size or any(not math.isfinite(value) for value in values):
        raise ShellResultIRError(f"element_{key}_invalid")
    return values


def _element(row: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized: dict[str, Any] = {"element_id": str(row["element_id"])}
    for key, size in (
        ("membrane_strain", 3), ("membrane_resultant_n_per_m", 3),
        ("curvature_per_m", 3), ("bending_resultant_nm_per_m", 3),
        ("transverse_shear_strain", 2), ("transverse_shear_resultant_n_per_m", 2),
    ):
        normalized[key] = _vector(row, key, size)
    energy = float(row["strain_energy_j"])
    if not math.isfinite(energy) or energy < 0.0:
        raise ShellResultIRError("element_strain_energy_invalid")
    normalized["strain_energy_j"] = energy
    return normalized


def _payload(result: ShellResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version, "result_id": result.result_id,
        "analysis_type": "shell_linear_static",
        "authority": {
            "profile": SHELL_AUTHORITY_PROFILE, "nodal_response": "authoritative",
            "element_recovery": "authoritative", "checkpoint": "exact_hash_bound",
            "engineering_design": "not_authoritative", "release_readiness": "not_authoritative",
        },
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "solver_result_hash": result.solver_result_hash,
            "stiffness_hash": result.stiffness_hash, "load_hash": result.load_hash,
        },
        "solver": {
            "solver_id": result.solver_id, "maximum_free_residual": result.maximum_free_residual,
            "fallback_used": False, "regularization_used": False,
        },
        "node_ids": list(result.node_ids), "element_ids": list(result.element_ids),
        "displacement_global": list(result.displacement_global),
        "reaction_global_n_nm": list(result.reaction_global_n_nm),
        "equilibrium_residual_global_n_nm": list(result.equilibrium_residual_global_n_nm),
        "element_results": [dict(row) for row in result.element_results],
        "energy": {"strain_energy_j": result.strain_energy_j, "external_work_j": result.external_work_j},
        "checkpoint": {"terminal_checkpoint_hash": result.terminal_checkpoint_hash, "exact_restart_required": True},
        "claim_boundary": SHELL_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = resources.files("structural_analysis.schemas").joinpath("shell_static_result_ir_v1.schema.json")
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = [
    "SHELL_AUTHORITY_PROFILE", "SHELL_CLAIM_BOUNDARY", "SHELL_RESULT_IR_SCHEMA_VERSION",
    "ShellResultIR", "ShellResultIRError", "create_shell_result_ir",
    "validate_shell_result_ir", "validate_shell_result_ir_manifest",
]
