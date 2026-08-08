"""Authoritative vector-history ResultIR for bounded linear MDOF transients."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from typing import Any

from jsonschema import Draft202012Validator

from ._canonical import canonical_hash


MDOF_TRANSIENT_RESULT_IR_SCHEMA_VERSION = "structural-analysis-mdof-transient-result-ir.v1"
MDOF_TRANSIENT_AUTHORITY_PROFILE = "authoritative_source_authenticated_linear_mdof_history.v1"
MDOF_TRANSIENT_STORAGE_PROFILE = "inline_time_major_vector_fp64_si.v1"
MDOF_TRANSIENT_CLAIM_BOUNDARY = (
    "Authoritative bounded force-driven linear MDOF displacement, velocity, "
    "acceleration, force-balance, and energy history with source-authenticated "
    "checkpoint replay. Nonlinear response, support excitation, shell, contact, "
    "engineering design, and release readiness are outside this contract."
)
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class MDOFTransientResultIRError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code, self.path, self.message = code, path, message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class MDOFTransientSampleIR:
    step_index: int
    time_s: float
    applied_force_n: tuple[float, ...]
    displacement_m: tuple[float, ...]
    velocity_m_per_s: tuple[float, ...]
    acceleration_m_per_s2: tuple[float, ...]
    restoring_force_n: tuple[float, ...]
    damping_force_n: tuple[float, ...]
    inertia_force_n: tuple[float, ...]
    equilibrium_residual_n: tuple[float, ...]
    relative_residual: float
    kinetic_energy_j: float
    strain_energy_j: float
    external_work_j: float
    damping_dissipation_j: float
    energy_balance_error_j: float
    linear_solve_count: int

    def to_manifest(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "applied_force_n", "displacement_m", "velocity_m_per_s",
            "acceleration_m_per_s2", "restoring_force_n", "damping_force_n",
            "inertia_force_n", "equilibrium_residual_n",
        ):
            payload[key] = list(payload[key])
        return payload


@dataclass(frozen=True)
class MDOFTransientResultIR:
    result_id: str
    model_ir_content_hash: str
    force_history_hash: str
    solver_id: str
    solver_result_hash: str
    integration_contract_hash: str
    terminal_checkpoint_hash: str
    checkpoint_authority_receipt_hash: str
    dof_ids: tuple[str, ...]
    time_step_s: float
    residual_relative_tolerance: float
    samples: tuple[MDOFTransientSampleIR, ...]
    result_hash: str
    schema_version: str = MDOF_TRANSIENT_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_mdof_transient_result_ir(
    *, result_id: str, model_ir_content_hash: str, force_history_hash: str,
    solver_id: str, solver_result_hash: str, integration_contract_hash: str,
    terminal_checkpoint_hash: str, checkpoint_authority_receipt_hash: str,
    dof_ids: Sequence[str], time_step_s: float, residual_relative_tolerance: float,
    samples: Sequence[Mapping[str, Any]],
) -> MDOFTransientResultIR:
    vector_fields = (
        "applied_force_n", "displacement_m", "velocity_m_per_s",
        "acceleration_m_per_s2", "restoring_force_n", "damping_force_n",
        "inertia_force_n", "equilibrium_residual_n",
    )
    normalized = []
    for row in samples:
        vectors = {name: tuple(float(value) for value in row[name]) for name in vector_fields}
        normalized.append(MDOFTransientSampleIR(
            step_index=int(row["step_index"]), time_s=float(row["time_s"]),
            **vectors, relative_residual=float(row["relative_residual"]),
            kinetic_energy_j=float(row["kinetic_energy_j"]),
            strain_energy_j=float(row["strain_energy_j"]),
            external_work_j=float(row["external_work_j"]),
            damping_dissipation_j=float(row["damping_dissipation_j"]),
            energy_balance_error_j=float(row["energy_balance_error_j"]),
            linear_solve_count=int(row["linear_solve_count"]),
        ))
    provisional = MDOFTransientResultIR(
        result_id=str(result_id), model_ir_content_hash=str(model_ir_content_hash),
        force_history_hash=str(force_history_hash), solver_id=str(solver_id),
        solver_result_hash=str(solver_result_hash), integration_contract_hash=str(integration_contract_hash),
        terminal_checkpoint_hash=str(terminal_checkpoint_hash),
        checkpoint_authority_receipt_hash=str(checkpoint_authority_receipt_hash),
        dof_ids=tuple(str(value) for value in dof_ids), time_step_s=float(time_step_s),
        residual_relative_tolerance=float(residual_relative_tolerance),
        samples=tuple(normalized), result_hash="sha256:" + "0" * 64,
    )
    result = replace(provisional, result_hash=canonical_hash(_payload(provisional, include_result_hash=False)))
    return validate_mdof_transient_result_ir(result)


def validate_mdof_transient_result_ir(result: MDOFTransientResultIR) -> MDOFTransientResultIR:
    if type(result) is not MDOFTransientResultIR:
        _fail("mdof_result_type_invalid", "/", "Expected MDOFTransientResultIR.")
    if result.schema_version != MDOF_TRANSIENT_RESULT_IR_SCHEMA_VERSION:
        _fail("schema_version_invalid", "/schema_version", "Unsupported schema version.")
    _stable_id(result.result_id, "/result_id")
    _stable_id(result.solver_id, "/solver/solver_id")
    if len(result.dof_ids) < 2 or len(set(result.dof_ids)) != len(result.dof_ids):
        _fail("dof_ids_invalid", "/dof_ids", "At least two unique DOF IDs are required.")
    for index, value in enumerate(result.dof_ids):
        _stable_id(value, f"/dof_ids/{index}")
    for path, value in (
        ("/bindings/model_ir_content_hash", result.model_ir_content_hash),
        ("/bindings/force_history_hash", result.force_history_hash),
        ("/bindings/solver_result_hash", result.solver_result_hash),
        ("/bindings/integration_contract_hash", result.integration_contract_hash),
        ("/checkpoint/terminal_checkpoint_hash", result.terminal_checkpoint_hash),
        ("/checkpoint/authority_receipt_hash", result.checkpoint_authority_receipt_hash),
        ("/result_hash", result.result_hash),
    ):
        _hash(value, path)
    if not math.isfinite(result.time_step_s) or result.time_step_s <= 0.0:
        _fail("time_step_invalid", "/solver/time_step_s", "Time step must be positive.")
    if not math.isfinite(result.residual_relative_tolerance) or result.residual_relative_tolerance <= 0.0:
        _fail("residual_tolerance_invalid", "/solver/residual_relative_tolerance", "Tolerance must be positive.")
    if not result.samples:
        _fail("history_empty", "/history", "History must be nonempty.")
    size = len(result.dof_ids)
    for index, sample in enumerate(result.samples):
        if sample.step_index != index or not math.isclose(sample.time_s, index * result.time_step_s, rel_tol=0.0, abs_tol=1.0e-12):
            _fail("history_index_invalid", f"/history/{index}", "Step/time indices are not contiguous.")
        for field in (
            "applied_force_n", "displacement_m", "velocity_m_per_s",
            "acceleration_m_per_s2", "restoring_force_n", "damping_force_n",
            "inertia_force_n", "equilibrium_residual_n",
        ):
            vector = getattr(sample, field)
            if len(vector) != size or any(not math.isfinite(value) for value in vector):
                _fail("history_vector_invalid", f"/history/{index}/{field}", "Vector dimension/value invalid.")
        scalars = (
            sample.relative_residual, sample.kinetic_energy_j, sample.strain_energy_j,
            sample.external_work_j, sample.damping_dissipation_j,
            sample.energy_balance_error_j,
        )
        if any(not math.isfinite(value) for value in scalars):
            _fail("history_nonfinite", f"/history/{index}", "History contains non-finite values.")
        if sample.relative_residual < 0.0 or sample.relative_residual > result.residual_relative_tolerance:
            _fail("history_residual_failed", f"/history/{index}/relative_residual", "Residual gate failed.")
        if min(sample.kinetic_energy_j, sample.strain_energy_j, sample.damping_dissipation_j) < 0.0 or sample.linear_solve_count < 0:
            _fail("history_energy_or_count_invalid", f"/history/{index}", "Energy/count is invalid.")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        _fail("result_hash_mismatch", "/result_hash", "Result hash mismatch.")
    validate_mdof_transient_result_ir_manifest(result.to_manifest())
    return result


def validate_mdof_transient_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(_schema_validator().iter_errors(payload), key=lambda error: tuple(str(value) for value in error.absolute_path))
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("mdof_result_schema_invalid", path or "/", error.message)
    return payload


def _payload(result: MDOFTransientResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version, "result_id": result.result_id,
        "analysis_type": "mdof_linear_transient",
        "authority": {
            "profile": MDOF_TRANSIENT_AUTHORITY_PROFILE,
            "response_history": "authoritative", "checkpoint": "source_authenticated",
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
        "dof_ids": list(result.dof_ids), "storage_profile": MDOF_TRANSIENT_STORAGE_PROFILE,
        "history": [sample.to_manifest() for sample in result.samples],
        "checkpoint": {
            "authority": "source_authenticated_checkpoint",
            "terminal_checkpoint_hash": result.terminal_checkpoint_hash,
            "authority_receipt_hash": result.checkpoint_authority_receipt_hash,
        },
        "claim_boundary": MDOF_TRANSIENT_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath("mdof_transient_result_ir_v1.schema.json")
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _hash(value: Any, path: str) -> None:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        _fail("hash_invalid", path, "Expected sha256:<64 lowercase hex>.")


def _stable_id(value: Any, path: str) -> None:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        _fail("stable_id_invalid", path, "Expected a stable identifier.")


def _fail(code: str, path: str, message: str) -> None:
    raise MDOFTransientResultIRError(code, path, message)


__all__ = [
    "MDOF_TRANSIENT_AUTHORITY_PROFILE", "MDOF_TRANSIENT_CLAIM_BOUNDARY",
    "MDOF_TRANSIENT_RESULT_IR_SCHEMA_VERSION", "MDOF_TRANSIENT_STORAGE_PROFILE",
    "MDOFTransientResultIR", "MDOFTransientResultIRError", "MDOFTransientSampleIR",
    "create_mdof_transient_result_ir", "validate_mdof_transient_result_ir",
    "validate_mdof_transient_result_ir_manifest",
]
