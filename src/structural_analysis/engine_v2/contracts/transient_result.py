"""Authoritative source-authenticated SDOF transient ResultIR contract."""

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


TRANSIENT_RESULT_IR_SCHEMA_VERSION = "structural-analysis-transient-result-ir.v1"
TRANSIENT_AUTHORITY_PROFILE = "authoritative_source_authenticated_sdof_history.v1"
TRANSIENT_STORAGE_PROFILE = "inline_time_major_fp64_si.v1"
TRANSIENT_CLAIM_BOUNDARY = (
    "Authoritative bounded force-driven SDOF displacement, velocity, acceleration, "
    "restoring-force, energy, and committed material history with a complete "
    "source-authenticated checkpoint chain. MDOF, ground-motion support motion, "
    "engineering design, and release readiness are outside this contract."
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class TransientResultIRError(ValueError):
    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class TransientSampleIR:
    step_index: int
    time_s: float
    applied_force_n: float
    displacement_m: float
    velocity_m_per_s: float
    acceleration_m_per_s2: float
    restoring_force_n: float
    equilibrium_residual_n: float
    relative_residual: float
    kinetic_energy_j: float
    stored_energy_j: float
    external_work_j: float
    damping_dissipation_j: float
    plastic_dissipation_j: float
    yielded: bool
    newton_iterations: int

    def to_manifest(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransientResultIR:
    result_id: str
    model_ir_content_hash: str
    force_history_hash: str
    solver_id: str
    solver_result_hash: str
    integration_contract_hash: str
    terminal_checkpoint_hash: str
    checkpoint_authority_receipt_hash: str
    time_step_s: float
    residual_relative_tolerance: float
    samples: tuple[TransientSampleIR, ...]
    terminal_material_state: tuple[tuple[str, float], ...]
    result_hash: str
    schema_version: str = TRANSIENT_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_transient_result_ir(
    *,
    result_id: str,
    model_ir_content_hash: str,
    force_history_hash: str,
    solver_id: str,
    solver_result_hash: str,
    integration_contract_hash: str,
    terminal_checkpoint_hash: str,
    checkpoint_authority_receipt_hash: str,
    time_step_s: float,
    residual_relative_tolerance: float,
    samples: Sequence[Mapping[str, Any]],
    terminal_material_state: Mapping[str, Any],
) -> TransientResultIR:
    normalized_samples = tuple(
        TransientSampleIR(
            step_index=int(row["step_index"]),
            time_s=float(row["time_s"]),
            applied_force_n=float(row["applied_force_n"]),
            displacement_m=float(row["displacement_m"]),
            velocity_m_per_s=float(row["velocity_m_per_s"]),
            acceleration_m_per_s2=float(row["acceleration_m_per_s2"]),
            restoring_force_n=float(row["restoring_force_n"]),
            equilibrium_residual_n=float(row["equilibrium_residual_n"]),
            relative_residual=float(row["relative_residual"]),
            kinetic_energy_j=float(row["kinetic_energy_j"]),
            stored_energy_j=float(row["stored_energy_j"]),
            external_work_j=float(row["external_work_j"]),
            damping_dissipation_j=float(row["damping_dissipation_j"]),
            plastic_dissipation_j=float(row["plastic_dissipation_j"]),
            yielded=bool(row["yielded"]),
            newton_iterations=int(row["newton_iterations"]),
        )
        for row in samples
    )
    state = tuple(sorted((str(key), float(value)) for key, value in terminal_material_state.items()))
    provisional = TransientResultIR(
        result_id=str(result_id),
        model_ir_content_hash=str(model_ir_content_hash),
        force_history_hash=str(force_history_hash),
        solver_id=str(solver_id),
        solver_result_hash=str(solver_result_hash),
        integration_contract_hash=str(integration_contract_hash),
        terminal_checkpoint_hash=str(terminal_checkpoint_hash),
        checkpoint_authority_receipt_hash=str(checkpoint_authority_receipt_hash),
        time_step_s=float(time_step_s),
        residual_relative_tolerance=float(residual_relative_tolerance),
        samples=normalized_samples,
        terminal_material_state=state,
        result_hash="sha256:" + "0" * 64,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(_payload(provisional, include_result_hash=False)),
    )
    return validate_transient_result_ir(result)


def validate_transient_result_ir(result: TransientResultIR) -> TransientResultIR:
    if type(result) is not TransientResultIR:
        _fail("transient_result_type_invalid", "/", "Expected TransientResultIR.")
    if result.schema_version != TRANSIENT_RESULT_IR_SCHEMA_VERSION:
        _fail("schema_version_invalid", "/schema_version", "Unsupported schema version.")
    _stable_id(result.result_id, "/result_id")
    _stable_id(result.solver_id, "/solver/solver_id")
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
    tolerance = result.residual_relative_tolerance
    if not math.isfinite(tolerance) or tolerance <= 0.0:
        _fail("residual_tolerance_invalid", "/solver/residual_relative_tolerance", "Tolerance must be positive.")
    if not result.samples:
        _fail("history_empty", "/history", "Transient history must be nonempty.")
    for index, sample in enumerate(result.samples):
        _validate_sample(sample, index=index, time_step=result.time_step_s, tolerance=tolerance)
    required_state = {
        "plastic_displacement_m",
        "backstress_n",
        "cumulative_plastic_displacement_m",
        "plastic_dissipation_j",
    }
    state = dict(result.terminal_material_state)
    if set(state) != required_state or any(not math.isfinite(value) for value in state.values()):
        _fail("terminal_material_state_invalid", "/terminal_material_state", "Material state fields are invalid.")
    if state["cumulative_plastic_displacement_m"] < 0.0 or state["plastic_dissipation_j"] < 0.0:
        _fail("terminal_material_state_negative", "/terminal_material_state", "History measures must be nonnegative.")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        _fail("result_hash_mismatch", "/result_hash", "Result hash mismatch.")
    validate_transient_result_ir_manifest(result.to_manifest())
    return result


def validate_transient_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("transient_result_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("transient_result_schema_invalid", "/", "Expected an object.")
    return payload


def _validate_sample(sample: TransientSampleIR, *, index: int, time_step: float, tolerance: float) -> None:
    path = f"/history/{index}"
    if type(sample) is not TransientSampleIR or sample.step_index != index:
        _fail("step_index_invalid", f"{path}/step_index", "Step indices must be contiguous from zero.")
    if not math.isclose(sample.time_s, index * time_step, rel_tol=0.0, abs_tol=1.0e-12):
        _fail("time_index_mismatch", f"{path}/time_s", "Time does not match step index.")
    values = asdict(sample)
    numeric = [value for key, value in values.items() if key not in {"step_index", "yielded", "newton_iterations"}]
    if any(not math.isfinite(float(value)) for value in numeric):
        _fail("history_nonfinite", path, "History contains a non-finite value.")
    if sample.relative_residual < 0.0 or sample.relative_residual > tolerance:
        _fail("history_residual_failed", f"{path}/relative_residual", "Residual gate failed.")
    if sample.newton_iterations < 0:
        _fail("newton_iterations_invalid", f"{path}/newton_iterations", "Iteration count is negative.")
    if min(sample.kinetic_energy_j, sample.stored_energy_j, sample.damping_dissipation_j, sample.plastic_dissipation_j) < 0.0:
        _fail("history_energy_negative", path, "Dissipative/mechanical energies must be nonnegative.")


def _payload(result: TransientResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "analysis_type": "sdof_nonlinear_transient",
        "authority": {
            "profile": TRANSIENT_AUTHORITY_PROFILE,
            "response_history": "authoritative",
            "material_state": "authoritative",
            "checkpoint": "source_authenticated",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "force_history_hash": result.force_history_hash,
            "solver_result_hash": result.solver_result_hash,
            "integration_contract_hash": result.integration_contract_hash,
        },
        "solver": {
            "solver_id": result.solver_id,
            "time_step_s": result.time_step_s,
            "residual_relative_tolerance": result.residual_relative_tolerance,
            "fallback_used": False,
            "regularization_used": False,
        },
        "storage_profile": TRANSIENT_STORAGE_PROFILE,
        "history": [sample.to_manifest() for sample in result.samples],
        "terminal_material_state": dict(result.terminal_material_state),
        "checkpoint": {
            "authority": "source_authenticated_checkpoint",
            "terminal_checkpoint_hash": result.terminal_checkpoint_hash,
            "authority_receipt_hash": result.checkpoint_authority_receipt_hash,
        },
        "claim_boundary": TRANSIENT_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath("transient_result_ir_v1.schema.json")
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
    raise TransientResultIRError(code, path, message)


__all__ = [
    "TRANSIENT_AUTHORITY_PROFILE",
    "TRANSIENT_CLAIM_BOUNDARY",
    "TRANSIENT_RESULT_IR_SCHEMA_VERSION",
    "TRANSIENT_STORAGE_PROFILE",
    "TransientResultIR",
    "TransientResultIRError",
    "TransientSampleIR",
    "create_transient_result_ir",
    "validate_transient_result_ir",
    "validate_transient_result_ir_manifest",
]
