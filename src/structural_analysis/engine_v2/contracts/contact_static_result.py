"""Authoritative ResultIR for bounded frictionless static contact."""

from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator

from ._canonical import canonical_hash


CONTACT_RESULT_IR_SCHEMA_VERSION = "structural-analysis-contact-result-ir.v1"
CONTACT_AUTHORITY_PROFILE = "authoritative_frictionless_unilateral_gap_kkt.v1"
CONTACT_CLAIM_BOUNDARY = (
    "Authoritative bounded small-displacement frictionless nodal upper-gap contact "
    "displacement, multiplier, nonpenetration, equilibrium, complementarity, active set, "
    "and exact checkpoint result. Surface discretization, friction, impact, large sliding, "
    "nonlinear material, engineering design, and release readiness are outside this contract."
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class ContactResultIRError(ValueError):
    pass


@dataclass(frozen=True)
class ContactResultIR:
    result_id: str
    model_ir_content_hash: str
    solver_result_hash: str
    stiffness_hash: str
    load_hash: str
    terminal_checkpoint_hash: str
    solver_id: str
    dof_ids: tuple[str, ...]
    contact_ids: tuple[str, ...]
    displacement_m: tuple[float, ...]
    contact_multiplier_n: tuple[float, ...]
    gap_remaining_m: tuple[float, ...]
    equilibrium_residual_n: tuple[float, ...]
    complementarity_n_m: tuple[float, ...]
    active_contact_ids: tuple[str, ...]
    maximum_equilibrium_residual_n: float
    maximum_penetration_m: float
    minimum_contact_multiplier_n: float
    maximum_complementarity_n_m: float
    result_hash: str
    schema_version: str = CONTACT_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_contact_result_ir(
    *, result_id: str, model_ir_content_hash: str, solver_result_hash: str,
    stiffness_hash: str, load_hash: str, terminal_checkpoint_hash: str,
    solver_id: str, dof_ids: Sequence[str], contact_ids: Sequence[str],
    displacement_m: Sequence[float], contact_multiplier_n: Sequence[float],
    gap_remaining_m: Sequence[float], equilibrium_residual_n: Sequence[float],
    complementarity_n_m: Sequence[float], active_contact_ids: Sequence[str],
    maximum_equilibrium_residual_n: float, maximum_penetration_m: float,
    minimum_contact_multiplier_n: float, maximum_complementarity_n_m: float,
) -> ContactResultIR:
    provisional = ContactResultIR(
        result_id=str(result_id), model_ir_content_hash=str(model_ir_content_hash),
        solver_result_hash=str(solver_result_hash), stiffness_hash=str(stiffness_hash),
        load_hash=str(load_hash), terminal_checkpoint_hash=str(terminal_checkpoint_hash),
        solver_id=str(solver_id), dof_ids=tuple(map(str, dof_ids)), contact_ids=tuple(map(str, contact_ids)),
        displacement_m=tuple(map(float, displacement_m)), contact_multiplier_n=tuple(map(float, contact_multiplier_n)),
        gap_remaining_m=tuple(map(float, gap_remaining_m)), equilibrium_residual_n=tuple(map(float, equilibrium_residual_n)),
        complementarity_n_m=tuple(map(float, complementarity_n_m)), active_contact_ids=tuple(map(str, active_contact_ids)),
        maximum_equilibrium_residual_n=float(maximum_equilibrium_residual_n), maximum_penetration_m=float(maximum_penetration_m),
        minimum_contact_multiplier_n=float(minimum_contact_multiplier_n), maximum_complementarity_n_m=float(maximum_complementarity_n_m),
        result_hash="sha256:" + "0" * 64,
    )
    result = replace(provisional, result_hash=canonical_hash(_payload(provisional, include_result_hash=False)))
    return validate_contact_result_ir(result)


def validate_contact_result_ir(result: ContactResultIR) -> ContactResultIR:
    if type(result) is not ContactResultIR or result.schema_version != CONTACT_RESULT_IR_SCHEMA_VERSION:
        raise ContactResultIRError("contact_result_type_or_version_invalid")
    if any(_ID.fullmatch(value) is None for value in (result.result_id, result.solver_id, *result.dof_ids, *result.contact_ids, *result.active_contact_ids)):
        raise ContactResultIRError("stable_id_invalid")
    size = len(result.dof_ids)
    if size < 1 or len(set(result.dof_ids)) != size or len(result.contact_ids) != size or len(set(result.contact_ids)) != size or not set(result.active_contact_ids).issubset(result.contact_ids):
        raise ContactResultIRError("contact_identity_invalid")
    if any(_HASH.fullmatch(value) is None for value in (result.model_ir_content_hash, result.solver_result_hash, result.stiffness_hash, result.load_hash, result.terminal_checkpoint_hash, result.result_hash)):
        raise ContactResultIRError("hash_invalid")
    vectors = (result.displacement_m, result.contact_multiplier_n, result.gap_remaining_m, result.equilibrium_residual_n, result.complementarity_n_m)
    if any(len(row) != size or any(not math.isfinite(value) for value in row) for row in vectors):
        raise ContactResultIRError("contact_vector_invalid")
    scalars = (result.maximum_equilibrium_residual_n, result.maximum_penetration_m, result.minimum_contact_multiplier_n, result.maximum_complementarity_n_m)
    if any(not math.isfinite(value) for value in scalars) or min(result.maximum_equilibrium_residual_n, result.maximum_penetration_m, result.minimum_contact_multiplier_n, result.maximum_complementarity_n_m) < 0.0:
        raise ContactResultIRError("contact_kkt_scalar_invalid")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        raise ContactResultIRError("result_hash_mismatch")
    validate_contact_result_ir_manifest(result.to_manifest())
    return result


def validate_contact_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(_schema_validator().iter_errors(payload), key=lambda error: tuple(map(str, error.absolute_path)))
    if errors:
        error = errors[0]
        raise ContactResultIRError(f"schema_invalid@/{'/'.join(map(str, error.absolute_path))}:{error.message}")
    return payload


def _payload(result: ContactResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version, "result_id": result.result_id, "analysis_type": "contact_frictionless_static",
        "authority": {"profile": CONTACT_AUTHORITY_PROFILE, "contact_response": "authoritative", "kkt_metrics": "authoritative", "checkpoint": "exact_hash_bound", "engineering_design": "not_authoritative", "release_readiness": "not_authoritative"},
        "bindings": {"model_ir_content_hash": result.model_ir_content_hash, "solver_result_hash": result.solver_result_hash, "stiffness_hash": result.stiffness_hash, "load_hash": result.load_hash},
        "solver": {"solver_id": result.solver_id, "fallback_used": False, "regularization_used": False},
        "dof_ids": list(result.dof_ids), "contact_ids": list(result.contact_ids),
        "displacement_m": list(result.displacement_m), "contact_multiplier_n": list(result.contact_multiplier_n),
        "gap_remaining_m": list(result.gap_remaining_m), "equilibrium_residual_n": list(result.equilibrium_residual_n),
        "complementarity_n_m": list(result.complementarity_n_m), "active_contact_ids": list(result.active_contact_ids),
        "kkt": {"maximum_equilibrium_residual_n": result.maximum_equilibrium_residual_n, "maximum_penetration_m": result.maximum_penetration_m, "minimum_contact_multiplier_n": result.minimum_contact_multiplier_n, "maximum_complementarity_n_m": result.maximum_complementarity_n_m},
        "checkpoint": {"terminal_checkpoint_hash": result.terminal_checkpoint_hash, "exact_restart_required": True},
        "claim_boundary": CONTACT_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    path = resources.files("structural_analysis.schemas").joinpath("contact_static_result_ir_v1.schema.json")
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


__all__ = ["CONTACT_AUTHORITY_PROFILE", "CONTACT_CLAIM_BOUNDARY", "CONTACT_RESULT_IR_SCHEMA_VERSION", "ContactResultIR", "ContactResultIRError", "create_contact_result_ir", "validate_contact_result_ir", "validate_contact_result_ir_manifest"]
