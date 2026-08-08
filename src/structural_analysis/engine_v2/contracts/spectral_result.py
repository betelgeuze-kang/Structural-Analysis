"""Authoritative small-model modal and linear-buckling ResultIR contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from typing import Any, Literal

from jsonschema import Draft202012Validator

from ._canonical import canonical_hash


SPECTRAL_RESULT_IR_SCHEMA_VERSION = "structural-analysis-spectral-result-ir.v1"
SPECTRAL_CHECKPOINT_SCHEMA_VERSION = "structural-analysis-spectral-checkpoint.v1"
SPECTRAL_AUTHORITY_PROFILE = "authoritative_small_model_generalized_eigen.v1"
SPECTRAL_STORAGE_PROFILE = "inline_node_major_max_component_normalized_fp64.v1"
SPECTRAL_CLAIM_BOUNDARY = (
    "Authoritative bounded modal frequencies or linear-buckling load factors and "
    "node-major mode shapes. Engineering design, nonlinear stability, release "
    "readiness, and commercial equivalence are not authoritative."
)

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")


class SpectralResultIRError(ValueError):
    """Fail-closed spectral ResultIR error with a stable code and path."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class SpectralModeIR:
    mode_number: int
    eigenvalue: float
    frequency_hz: float | None
    load_factor: float | None
    residual_relative_inf: float
    node_shapes: tuple[tuple[float, float, float, float, float, float], ...]
    mode_shape_hash: str

    def to_manifest(self) -> dict[str, Any]:
        return {
            "mode_number": self.mode_number,
            "eigenvalue": self.eigenvalue,
            "frequency_hz": self.frequency_hz,
            "load_factor": self.load_factor,
            "residual_relative_inf": self.residual_relative_inf,
            "node_shapes": [list(row) for row in self.node_shapes],
            "mode_shape_hash": self.mode_shape_hash,
        }


@dataclass(frozen=True)
class SpectralResultIR:
    result_id: str
    analysis_type: Literal["modal", "linear_buckling"]
    model_ir_content_hash: str
    solver_id: str
    solver_receipt_hash: str
    stiffness_matrix_hash: str
    secondary_matrix_hash: str
    free_dof_map_hash: str
    node_ids: tuple[str, ...]
    tolerance: float
    modes: tuple[SpectralModeIR, ...]
    checkpoint_hash: str
    result_hash: str
    schema_version: str = SPECTRAL_RESULT_IR_SCHEMA_VERSION

    def to_manifest(self) -> dict[str, Any]:
        return _payload(self, include_result_hash=True)


def create_spectral_result_ir(
    *,
    result_id: str,
    analysis_type: Literal["modal", "linear_buckling"],
    model_ir_content_hash: str,
    solver_id: str,
    solver_receipt_hash: str,
    stiffness_matrix_hash: str,
    secondary_matrix_hash: str,
    free_dof_map_hash: str,
    node_ids: Sequence[str],
    tolerance: float,
    modes: Sequence[Mapping[str, Any]],
) -> SpectralResultIR:
    normalized_nodes = tuple(str(value) for value in node_ids)
    normalized_modes = tuple(
        _create_mode(row, analysis_type=analysis_type, node_count=len(normalized_nodes))
        for row in modes
    )
    checkpoint_payload = {
        "schema_version": SPECTRAL_CHECKPOINT_SCHEMA_VERSION,
        "analysis_type": analysis_type,
        "model_ir_content_hash": model_ir_content_hash,
        "solver_receipt_hash": solver_receipt_hash,
        "mode_count": len(normalized_modes),
        "terminal_mode_number": len(normalized_modes),
        "modes": [row.to_manifest() for row in normalized_modes],
    }
    provisional = SpectralResultIR(
        result_id=str(result_id),
        analysis_type=analysis_type,
        model_ir_content_hash=str(model_ir_content_hash),
        solver_id=str(solver_id),
        solver_receipt_hash=str(solver_receipt_hash),
        stiffness_matrix_hash=str(stiffness_matrix_hash),
        secondary_matrix_hash=str(secondary_matrix_hash),
        free_dof_map_hash=str(free_dof_map_hash),
        node_ids=normalized_nodes,
        tolerance=float(tolerance),
        modes=normalized_modes,
        checkpoint_hash=canonical_hash(checkpoint_payload),
        result_hash="sha256:" + "0" * 64,
    )
    result = replace(
        provisional,
        result_hash=canonical_hash(_payload(provisional, include_result_hash=False)),
    )
    return validate_spectral_result_ir(result)


def validate_spectral_result_ir(result: SpectralResultIR) -> SpectralResultIR:
    if type(result) is not SpectralResultIR:
        _fail("spectral_result_type_invalid", "/", "Expected SpectralResultIR.")
    if result.schema_version != SPECTRAL_RESULT_IR_SCHEMA_VERSION:
        _fail("schema_version_invalid", "/schema_version", "Unsupported schema version.")
    _stable_id(result.result_id, "/result_id")
    _stable_id(result.solver_id, "/solver/solver_id")
    if result.analysis_type not in ("modal", "linear_buckling"):
        _fail("analysis_type_invalid", "/analysis_type", "Unsupported analysis type.")
    if not result.node_ids or len(set(result.node_ids)) != len(result.node_ids):
        _fail("node_ids_invalid", "/bindings/node_ids", "Node ids must be nonempty and unique.")
    for index, node_id in enumerate(result.node_ids):
        _stable_id(node_id, f"/bindings/node_ids/{index}")
    for path, value in (
        ("/bindings/model_ir_content_hash", result.model_ir_content_hash),
        ("/bindings/solver_receipt_hash", result.solver_receipt_hash),
        ("/bindings/stiffness_matrix_hash", result.stiffness_matrix_hash),
        ("/bindings/secondary_matrix_hash", result.secondary_matrix_hash),
        ("/bindings/free_dof_map_hash", result.free_dof_map_hash),
        ("/checkpoint/checkpoint_hash", result.checkpoint_hash),
        ("/result_hash", result.result_hash),
    ):
        _hash(value, path)
    if not math.isfinite(result.tolerance) or result.tolerance <= 0.0:
        _fail("tolerance_invalid", "/solver/tolerance", "Tolerance must be finite and positive.")
    if not result.modes:
        _fail("modes_empty", "/modes", "At least one mode is required.")
    previous = -math.inf
    for index, mode in enumerate(result.modes):
        _validate_mode(
            mode,
            path=f"/modes/{index}",
            analysis_type=result.analysis_type,
            node_count=len(result.node_ids),
            expected_number=index + 1,
            tolerance=result.tolerance,
        )
        if mode.eigenvalue <= previous:
            _fail("eigenvalues_not_strictly_increasing", f"/modes/{index}/eigenvalue", "Eigenvalues must increase.")
        previous = mode.eigenvalue
    checkpoint_payload = {
        "schema_version": SPECTRAL_CHECKPOINT_SCHEMA_VERSION,
        "analysis_type": result.analysis_type,
        "model_ir_content_hash": result.model_ir_content_hash,
        "solver_receipt_hash": result.solver_receipt_hash,
        "mode_count": len(result.modes),
        "terminal_mode_number": len(result.modes),
        "modes": [row.to_manifest() for row in result.modes],
    }
    if result.checkpoint_hash != canonical_hash(checkpoint_payload):
        _fail("checkpoint_hash_mismatch", "/checkpoint/checkpoint_hash", "Checkpoint hash mismatch.")
    if result.result_hash != canonical_hash(_payload(result, include_result_hash=False)):
        _fail("result_hash_mismatch", "/result_hash", "Result hash mismatch.")
    validate_spectral_result_ir_manifest(result.to_manifest())
    return result


def validate_spectral_result_ir_manifest(payload: Any) -> Mapping[str, Any]:
    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail("spectral_result_schema_invalid", path or "/", error.message)
    if not isinstance(payload, Mapping):  # pragma: no cover
        _fail("spectral_result_schema_invalid", "/", "Expected an object.")
    return payload


def _create_mode(row: Mapping[str, Any], *, analysis_type: str, node_count: int) -> SpectralModeIR:
    raw_shapes = row.get("node_shapes")
    if not isinstance(raw_shapes, Sequence) or isinstance(raw_shapes, (str, bytes)):
        _fail("node_shapes_invalid", "/modes/node_shapes", "Expected node-major shapes.")
    shapes = tuple(tuple(float(value) for value in shape) for shape in raw_shapes)
    mode = SpectralModeIR(
        mode_number=int(row["mode_number"]),
        eigenvalue=float(row["eigenvalue"]),
        frequency_hz=None if row.get("frequency_hz") is None else float(row["frequency_hz"]),
        load_factor=None if row.get("load_factor") is None else float(row["load_factor"]),
        residual_relative_inf=float(row["residual_relative_inf"]),
        node_shapes=shapes,  # type: ignore[arg-type]
        mode_shape_hash=canonical_hash([list(shape) for shape in shapes]),
    )
    _validate_mode(mode, path="/modes", analysis_type=analysis_type, node_count=node_count, expected_number=mode.mode_number, tolerance=math.inf)
    return mode


def _validate_mode(mode: SpectralModeIR, *, path: str, analysis_type: str, node_count: int, expected_number: int, tolerance: float) -> None:
    if type(mode) is not SpectralModeIR or mode.mode_number != expected_number:
        _fail("mode_number_invalid", f"{path}/mode_number", "Mode numbers must be contiguous from one.")
    if not math.isfinite(mode.eigenvalue) or mode.eigenvalue <= 0.0:
        _fail("eigenvalue_invalid", f"{path}/eigenvalue", "Eigenvalue must be finite and positive.")
    if analysis_type == "modal":
        if mode.frequency_hz is None or mode.load_factor is not None:
            _fail("modal_quantity_invalid", path, "Modal modes require frequency only.")
        if not math.isclose(mode.eigenvalue, (2.0 * math.pi * mode.frequency_hz) ** 2, rel_tol=2.0e-12):
            _fail("modal_frequency_mismatch", f"{path}/frequency_hz", "Frequency does not match eigenvalue.")
    elif mode.load_factor is None or mode.frequency_hz is not None or not math.isclose(mode.eigenvalue, mode.load_factor, rel_tol=1.0e-15):
        _fail("buckling_quantity_invalid", path, "Buckling modes require matching load factor only.")
    if not math.isfinite(mode.residual_relative_inf) or not 0.0 <= mode.residual_relative_inf <= tolerance:
        _fail("mode_residual_invalid", f"{path}/residual_relative_inf", "Mode residual exceeds tolerance.")
    if len(mode.node_shapes) != node_count or any(len(row) != 6 for row in mode.node_shapes):
        _fail("mode_shape_invalid", f"{path}/node_shapes", "Mode shape must be node_count by six.")
    flat = [value for row in mode.node_shapes for value in row]
    if any(not math.isfinite(value) for value in flat) or not math.isclose(max(map(abs, flat)), 1.0, rel_tol=0.0, abs_tol=1.0e-12):
        _fail("mode_shape_normalization_invalid", f"{path}/node_shapes", "Mode shape must be finite and max-component normalized.")
    expected_hash = canonical_hash([list(row) for row in mode.node_shapes])
    if mode.mode_shape_hash != expected_hash:
        _fail("mode_shape_hash_mismatch", f"{path}/mode_shape_hash", "Mode shape hash mismatch.")


def _payload(result: SpectralResultIR, *, include_result_hash: bool) -> dict[str, Any]:
    payload = {
        "schema_version": result.schema_version,
        "result_id": result.result_id,
        "analysis_type": result.analysis_type,
        "authority": {
            "profile": SPECTRAL_AUTHORITY_PROFILE,
            "eigenvalues": "authoritative",
            "mode_shapes": "authoritative",
            "frequencies": "authoritative" if result.analysis_type == "modal" else "not_applicable",
            "load_factors": "authoritative" if result.analysis_type == "linear_buckling" else "not_applicable",
            "engineering_design": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "bindings": {
            "model_ir_content_hash": result.model_ir_content_hash,
            "solver_receipt_hash": result.solver_receipt_hash,
            "stiffness_matrix_hash": result.stiffness_matrix_hash,
            "secondary_matrix_hash": result.secondary_matrix_hash,
            "free_dof_map_hash": result.free_dof_map_hash,
            "node_ids": list(result.node_ids),
        },
        "solver": {
            "solver_id": result.solver_id,
            "tolerance": result.tolerance,
            "fallback_used": False,
            "regularization_used": False,
        },
        "storage_profile": SPECTRAL_STORAGE_PROFILE,
        "modes": [row.to_manifest() for row in result.modes],
        "checkpoint": {
            "schema_version": SPECTRAL_CHECKPOINT_SCHEMA_VERSION,
            "mode_count": len(result.modes),
            "terminal_mode_number": len(result.modes),
            "checkpoint_hash": result.checkpoint_hash,
        },
        "claim_boundary": SPECTRAL_CLAIM_BOUNDARY,
    }
    if include_result_hash:
        payload["result_hash"] = result.result_hash
    return payload


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath("spectral_result_ir_v1.schema.json")
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
    raise SpectralResultIRError(code, path, message)


__all__ = [
    "SPECTRAL_AUTHORITY_PROFILE",
    "SPECTRAL_CHECKPOINT_SCHEMA_VERSION",
    "SPECTRAL_CLAIM_BOUNDARY",
    "SPECTRAL_RESULT_IR_SCHEMA_VERSION",
    "SPECTRAL_STORAGE_PROFILE",
    "SpectralModeIR",
    "SpectralResultIR",
    "SpectralResultIRError",
    "create_spectral_result_ir",
    "validate_spectral_result_ir",
    "validate_spectral_result_ir_manifest",
]
