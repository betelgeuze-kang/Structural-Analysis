"""Backend-neutral array contract for one current-tangent operator.

The contract captures the exact parent arrays for the reduced reference CSR,
the load-coupled frame stiffness delta, and the conservative finite-chord
axial correction.  The NumPy evaluator is a host reference implementation;
HIP execution and CPU/HIP numerical parity remain separate evidence gates.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from functools import lru_cache
from importlib import resources
import json
import math
import re
from types import MappingProxyType
from typing import Any, Literal

from jsonschema import Draft202012Validator, validators
import numpy as np

from ._canonical import (
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION = (
    "structural-analysis-current-tangent-operator.v1"
)
CURRENT_TANGENT_OPERATOR_PROFILE = (
    "reference_csr_load_frame_delta_finite_chord_axial.v1"
)
CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR = (
    "numpy_fp64_array_formula_reference.v1"
)
CURRENT_TANGENT_OPERATOR_ACTION_EXPRESSION = (
    "K_reference_ff*v_f + load_factor*K_frame_delta*v_global + "
    "K_finite_chord_axial_correction(u_global)*v_global"
)
CURRENT_TANGENT_OPERATOR_CLAIM_BOUNDARY = (
    "This contract binds the current-tangent formula, equation order, and all "
    "numeric parent arrays to immutable canonical bytes. Its NumPy evaluator "
    "is a CPU reference path. It does not establish HIP execution, CPU/HIP "
    "numerical parity, cross-platform bit identity, performance, a production "
    "nonlinear solver, or G1 closure."
)

_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_STRICT_JSON_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer", lambda _checker, value: type(value) is int
).redefine("number", lambda _checker, value: type(value) in (int, float))
_StrictDraft202012Validator = validators.extend(
    Draft202012Validator,
    type_checker=_STRICT_JSON_TYPE_CHECKER,
)

_ARRAY_SPECS = (
    ("reference_row_pointer", "<i8", 1),
    ("reference_column_indices", "<i8", 1),
    ("reference_values_n_per_m", "<f8", 1),
    ("free_global_dofs", "<i8", 1),
    ("background_global_displacements_m", "<f8", 1),
    ("frame_dofs", "<i8", 2),
    ("frame_stiffness_delta_n_per_m", "<f8", 3),
    ("geometry_dofs", "<i8", 2),
    ("geometry_relative_translation_operators", "<f8", 3),
    ("geometry_reference_chords_m", "<f8", 2),
    ("geometry_reference_lengths_m", "<f8", 1),
    ("geometry_axial_stiffness_n_per_m", "<f8", 1),
)
_ARRAY_NAMES = tuple(name for name, _dtype, _rank in _ARRAY_SPECS)


class CurrentTangentOperatorError(ValueError):
    """Stable fail-closed error for current-tangent contracts."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.message = message
        super().__init__(f"{code}@{path}: {message}")


@dataclass(frozen=True)
class CurrentTangentArrayDescriptor:
    """Canonical byte identity for one operator array."""

    name: str
    dtype: str
    shape: tuple[int, ...]
    layout: Literal["C"]
    byte_length: int
    data_hash: str
    content_hash: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class CurrentTangentOperatorContract:
    """Immutable current-tangent parent arrays and CPU reference evaluator."""

    schema_version: str
    contract_hash: str
    array_bundle_hash: str
    profile: str
    case_id: str
    residual_formula_hash: str
    source_action_contract: str
    equation_count: int
    global_dof_count: int
    reference_nnz: int
    frame_element_count: int
    geometry_element_count: int
    descriptors: tuple[CurrentTangentArrayDescriptor, ...]
    _arrays: Mapping[str, np.ndarray]

    def array(self, name: str) -> np.ndarray:
        try:
            return self._arrays[name]
        except KeyError as exc:
            raise KeyError(f"Unknown current-tangent array: {name}") from exc

    def to_manifest(self) -> dict[str, Any]:
        validate_current_tangent_operator(self)
        return _contract_payload(self, include_contract_hash=True)

    def apply_n_per_m(
        self,
        free_displacements_m: Any,
        load_factor: float,
        free_direction_m: Any,
    ) -> np.ndarray:
        """Evaluate the contract action in N/m in free-equation order."""

        state = _finite_vector(
            free_displacements_m,
            dimension=self.equation_count,
            path="/apply/free_displacements_m",
        )
        direction = _finite_vector(
            free_direction_m,
            dimension=self.equation_count,
            path="/apply/free_direction_m",
        )
        try:
            factor = float(load_factor)
        except (TypeError, ValueError) as exc:
            _fail(
                "current_tangent_load_factor_invalid",
                "/apply/load_factor",
                "Load factor must be finite.",
                cause=exc,
            )
        if not math.isfinite(factor):
            _fail(
                "current_tangent_load_factor_invalid",
                "/apply/load_factor",
                "Load factor must be finite.",
            )

        free = self.array("free_global_dofs")
        global_state = np.array(
            self.array("background_global_displacements_m"),
            dtype=np.float64,
            copy=True,
        )
        global_state[free] = state
        global_direction = np.zeros(self.global_dof_count, dtype=np.float64)
        global_direction[free] = direction

        action = _reference_csr_action(
            self.array("reference_row_pointer"),
            self.array("reference_column_indices"),
            self.array("reference_values_n_per_m"),
            direction,
        )
        if self.frame_element_count:
            action += factor * _frame_delta_action(
                self.array("frame_dofs"),
                self.array("frame_stiffness_delta_n_per_m"),
                global_direction,
                free,
                self.global_dof_count,
            )
        if self.geometry_element_count:
            action += _finite_chord_geometry_action(
                dofs=self.array("geometry_dofs"),
                relative_operators=self.array(
                    "geometry_relative_translation_operators"
                ),
                reference_chords_m=self.array(
                    "geometry_reference_chords_m"
                ),
                reference_lengths_m=self.array(
                    "geometry_reference_lengths_m"
                ),
                axial_stiffness_n_per_m=self.array(
                    "geometry_axial_stiffness_n_per_m"
                ),
                global_state_m=global_state,
                global_direction_m=global_direction,
                free_global_dofs=free,
                global_dof_count=self.global_dof_count,
            )
        result = np.ascontiguousarray(action, dtype="<f8")
        if not np.all(np.isfinite(result)):
            _fail(
                "current_tangent_action_nonfinite",
                "/apply/output",
                "Current-tangent action contains a non-finite value.",
            )
        return result


def create_current_tangent_operator(
    *,
    case_id: str,
    residual_formula_hash: str,
    source_action_contract: str,
    reference_row_pointer: Any,
    reference_column_indices: Any,
    reference_values_n_per_m: Any,
    free_global_dofs: Any,
    background_global_displacements_m: Any,
    frame_dofs: Any,
    frame_stiffness_delta_n_per_m: Any,
    geometry_dofs: Any,
    geometry_relative_translation_operators: Any,
    geometry_reference_chords_m: Any,
    geometry_reference_lengths_m: Any,
    geometry_axial_stiffness_n_per_m: Any,
) -> CurrentTangentOperatorContract:
    """Create and validate one immutable backend-neutral operator contract."""

    raw_arrays = {
        "reference_row_pointer": reference_row_pointer,
        "reference_column_indices": reference_column_indices,
        "reference_values_n_per_m": reference_values_n_per_m,
        "free_global_dofs": free_global_dofs,
        "background_global_displacements_m": (
            background_global_displacements_m
        ),
        "frame_dofs": frame_dofs,
        "frame_stiffness_delta_n_per_m": frame_stiffness_delta_n_per_m,
        "geometry_dofs": geometry_dofs,
        "geometry_relative_translation_operators": (
            geometry_relative_translation_operators
        ),
        "geometry_reference_chords_m": geometry_reference_chords_m,
        "geometry_reference_lengths_m": geometry_reference_lengths_m,
        "geometry_axial_stiffness_n_per_m": (
            geometry_axial_stiffness_n_per_m
        ),
    }
    try:
        arrays = MappingProxyType(
            {
                name: immutable_array(raw_arrays[name], dtype=dtype)
                for name, dtype, _rank in _ARRAY_SPECS
            }
        )
    except CanonicalContractError as exc:
        _fail(
            "current_tangent_array_canonicalization_failed",
            "/arrays",
            str(exc),
            cause=exc,
        )
    descriptors = tuple(
        _array_descriptor(name, arrays[name]) for name in _ARRAY_NAMES
    )
    descriptor_payload = [row.to_dict() for row in descriptors]
    equation_count = int(arrays["free_global_dofs"].size)
    global_dof_count = int(
        arrays["background_global_displacements_m"].size
    )
    provisional = CurrentTangentOperatorContract(
        schema_version=CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION,
        contract_hash="sha256:" + "0" * 64,
        array_bundle_hash=canonical_hash(descriptor_payload),
        profile=CURRENT_TANGENT_OPERATOR_PROFILE,
        case_id=str(case_id).strip(),
        residual_formula_hash=str(residual_formula_hash).strip(),
        source_action_contract=str(source_action_contract).strip(),
        equation_count=equation_count,
        global_dof_count=global_dof_count,
        reference_nnz=int(arrays["reference_column_indices"].size),
        frame_element_count=int(arrays["frame_dofs"].shape[0]),
        geometry_element_count=int(arrays["geometry_dofs"].shape[0]),
        descriptors=descriptors,
        _arrays=arrays,
    )
    contract = replace(
        provisional,
        contract_hash=canonical_hash(
            _contract_payload(provisional, include_contract_hash=False)
        ),
    )
    return validate_current_tangent_operator(contract)


def validate_current_tangent_operator(
    contract: CurrentTangentOperatorContract,
) -> CurrentTangentOperatorContract:
    """Fail closed on stale metadata, mutable bytes, or invalid topology."""

    if type(contract) is not CurrentTangentOperatorContract:
        _fail(
            "current_tangent_contract_type_invalid",
            "/",
            "Expected CurrentTangentOperatorContract.",
        )
    if contract.schema_version != CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION:
        _fail(
            "current_tangent_schema_version_invalid",
            "/schema_version",
            "Unsupported schema version.",
        )
    if contract.profile != CURRENT_TANGENT_OPERATOR_PROFILE:
        _fail(
            "current_tangent_profile_invalid",
            "/profile",
            "Unsupported current-tangent profile.",
        )
    if not contract.case_id:
        _fail(
            "current_tangent_case_id_missing",
            "/case_id",
            "case_id is required.",
        )
    _require_hash(contract.contract_hash, "/contract_hash")
    _require_hash(contract.array_bundle_hash, "/array_bundle_hash")
    _require_hash(contract.residual_formula_hash, "/residual_formula_hash")
    if not contract.source_action_contract:
        _fail(
            "current_tangent_source_action_contract_missing",
            "/source_action_contract",
            "source_action_contract is required.",
        )
    if not isinstance(contract._arrays, MappingProxyType):
        _fail(
            "current_tangent_array_map_mutable",
            "/arrays",
            "Array map must be immutable.",
        )
    if tuple(contract._arrays) != _ARRAY_NAMES:
        _fail(
            "current_tangent_array_set_invalid",
            "/arrays",
            "Array set or order is invalid.",
        )
    if (
        type(contract.descriptors) is not tuple
        or tuple(row.name for row in contract.descriptors) != _ARRAY_NAMES
        or any(
            type(row) is not CurrentTangentArrayDescriptor
            for row in contract.descriptors
        )
    ):
        _fail(
            "current_tangent_descriptor_set_invalid",
            "/array_descriptors",
            "Descriptor set or order is invalid.",
        )
    descriptor_by_name = {row.name: row for row in contract.descriptors}
    for name, dtype, rank in _ARRAY_SPECS:
        array = contract.array(name)
        _validate_array(array, dtype=dtype, rank=rank, path=f"/arrays/{name}")
        if descriptor_by_name[name] != _array_descriptor(name, array):
            _fail(
                "current_tangent_descriptor_mismatch",
                f"/array_descriptors/{name}",
                "Descriptor does not match immutable array bytes.",
            )

    row_pointer = contract.array("reference_row_pointer")
    columns = contract.array("reference_column_indices")
    values = contract.array("reference_values_n_per_m")
    free = contract.array("free_global_dofs")
    background = contract.array("background_global_displacements_m")
    equation_count = int(free.size)
    global_dof_count = int(background.size)
    reference_nnz = int(columns.size)
    if equation_count < 1 or global_dof_count < equation_count:
        _fail(
            "current_tangent_dimensions_invalid",
            "/dimensions",
            "Equation and global DOF counts must be positive and consistent.",
        )
    if (
        row_pointer.shape != (equation_count + 1,)
        or values.shape != (reference_nnz,)
        or int(row_pointer[0]) != 0
        or int(row_pointer[-1]) != reference_nnz
        or np.any(np.diff(row_pointer) < 0)
    ):
        _fail(
            "current_tangent_reference_csr_invalid",
            "/arrays/reference_row_pointer",
            "Reference CSR row pointer or numeric length is invalid.",
        )
    if reference_nnz < 1 or np.any(columns < 0) or np.any(
        columns >= equation_count
    ):
        _fail(
            "current_tangent_reference_columns_invalid",
            "/arrays/reference_column_indices",
            "Reference CSR columns must be in free-equation range.",
        )
    for row in range(equation_count):
        start = int(row_pointer[row])
        stop = int(row_pointer[row + 1])
        if stop - start > 1 and np.any(np.diff(columns[start:stop]) <= 0):
            _fail(
                "current_tangent_reference_row_order_invalid",
                f"/arrays/reference_column_indices/{row}",
                "Each CSR row must have strictly increasing columns.",
            )
    if (
        np.any(free < 0)
        or np.any(free >= global_dof_count)
        or np.any(np.diff(free) <= 0)
    ):
        _fail(
            "current_tangent_free_order_invalid",
            "/arrays/free_global_dofs",
            "Free global DOFs must be strictly increasing and in range.",
        )
    if np.any(background[free] != 0.0):
        _fail(
            "current_tangent_background_free_entries_nonzero",
            "/arrays/background_global_displacements_m",
            "Background displacement must be zero at every free DOF.",
        )

    frame_dofs = contract.array("frame_dofs")
    frame_delta = contract.array("frame_stiffness_delta_n_per_m")
    frame_count = int(frame_dofs.shape[0])
    if frame_dofs.shape != (frame_count, 12) or frame_delta.shape != (
        frame_count,
        12,
        12,
    ):
        _fail(
            "current_tangent_frame_shapes_invalid",
            "/arrays/frame_dofs",
            "Frame arrays must have shapes (E,12) and (E,12,12).",
        )
    if frame_count and (
        np.any(frame_dofs < 0) or np.any(frame_dofs >= global_dof_count)
    ):
        _fail(
            "current_tangent_frame_dofs_invalid",
            "/arrays/frame_dofs",
            "Frame DOFs must be in global range.",
        )

    geometry_dofs = contract.array("geometry_dofs")
    relative = contract.array("geometry_relative_translation_operators")
    chords = contract.array("geometry_reference_chords_m")
    lengths = contract.array("geometry_reference_lengths_m")
    axial = contract.array("geometry_axial_stiffness_n_per_m")
    geometry_count = int(geometry_dofs.shape[0])
    expected_geometry_shapes = (
        geometry_dofs.shape == (geometry_count, 12)
        and relative.shape == (geometry_count, 3, 12)
        and chords.shape == (geometry_count, 3)
        and lengths.shape == (geometry_count,)
        and axial.shape == (geometry_count,)
    )
    if not expected_geometry_shapes:
        _fail(
            "current_tangent_geometry_shapes_invalid",
            "/arrays/geometry_dofs",
            "Finite-chord geometry array shapes are inconsistent.",
        )
    if geometry_count and (
        np.any(geometry_dofs < 0)
        or np.any(geometry_dofs >= global_dof_count)
        or np.any(lengths <= 1.0e-12)
        or np.any(axial <= 0.0)
    ):
        _fail(
            "current_tangent_geometry_values_invalid",
            "/arrays/geometry_dofs",
            "Geometry DOFs, lengths, or axial stiffness are invalid.",
        )
    if geometry_count and not np.allclose(
        np.linalg.norm(chords, axis=1),
        lengths,
        rtol=1.0e-13,
        atol=1.0e-13,
    ):
        _fail(
            "current_tangent_geometry_chord_length_mismatch",
            "/arrays/geometry_reference_lengths_m",
            "Reference chord norms do not match reference lengths.",
        )

    expected_counts = (
        contract.equation_count == equation_count
        and contract.global_dof_count == global_dof_count
        and contract.reference_nnz == reference_nnz
        and contract.frame_element_count == frame_count
        and contract.geometry_element_count == geometry_count
    )
    if not expected_counts:
        _fail(
            "current_tangent_count_metadata_stale",
            "/dimensions",
            "Dimension metadata does not match array shapes.",
        )
    descriptor_payload = [row.to_dict() for row in contract.descriptors]
    if contract.array_bundle_hash != canonical_hash(descriptor_payload):
        _fail(
            "current_tangent_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Array bundle hash is stale.",
        )
    manifest = _contract_payload(contract, include_contract_hash=True)
    validate_current_tangent_operator_manifest(manifest)
    if contract.contract_hash != canonical_hash(
        _contract_payload(contract, include_contract_hash=False)
    ):
        _fail(
            "current_tangent_contract_hash_mismatch",
            "/contract_hash",
            "Current-tangent contract hash is stale.",
        )
    return contract


def validate_current_tangent_operator_manifest(
    payload: Any,
) -> Mapping[str, Any]:
    """Validate a transport manifest without requiring its array bytes."""

    errors = sorted(
        _schema_validator().iter_errors(payload),
        key=lambda error: tuple(str(value) for value in error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = "/" + "/".join(str(value) for value in error.absolute_path)
        _fail(
            "current_tangent_manifest_schema_invalid",
            path or "/",
            error.message,
        )
    if not isinstance(payload, Mapping):  # pragma: no cover - schema invariant
        _fail(
            "current_tangent_manifest_type_invalid",
            "/",
            "Expected an object.",
        )
    descriptors = payload["array_descriptors"]
    if [row["name"] for row in descriptors] != list(_ARRAY_NAMES):
        _fail(
            "current_tangent_manifest_array_order_invalid",
            "/array_descriptors",
            "Manifest array names or order are invalid.",
        )
    expected_dtype_rank = {
        name: (dtype, rank) for name, dtype, rank in _ARRAY_SPECS
    }
    for index, descriptor in enumerate(descriptors):
        dtype, rank = expected_dtype_rank[descriptor["name"]]
        if descriptor["dtype"] != dtype or len(descriptor["shape"]) != rank:
            _fail(
                "current_tangent_manifest_descriptor_invalid",
                f"/array_descriptors/{index}",
                "Descriptor dtype or rank is invalid.",
            )
        element_count = math.prod(descriptor["shape"])
        if descriptor["byte_length"] != 8 * element_count:
            _fail(
                "current_tangent_manifest_descriptor_length_invalid",
                f"/array_descriptors/{index}/byte_length",
                "Descriptor byte length does not match shape and dtype.",
            )
    if payload["array_bundle_hash"] != canonical_hash(descriptors):
        _fail(
            "current_tangent_array_bundle_hash_mismatch",
            "/array_bundle_hash",
            "Manifest array bundle hash is stale.",
        )
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("contract_hash")
    if claimed_hash != canonical_hash(without_hash):
        _fail(
            "current_tangent_contract_hash_mismatch",
            "/contract_hash",
            "Manifest contract hash is stale.",
        )
    return payload


def _reference_csr_action(
    row_pointer: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    direction: np.ndarray,
) -> np.ndarray:
    products = np.asarray(values * direction[columns], dtype=np.float64)
    result = np.zeros(row_pointer.size - 1, dtype=np.float64)
    starts = row_pointer[:-1]
    stops = row_pointer[1:]
    nonempty_rows = np.flatnonzero(stops > starts)
    if nonempty_rows.size:
        result[nonempty_rows] = np.add.reduceat(
            products,
            starts[nonempty_rows],
        )
    return result


def _frame_delta_action(
    dofs: np.ndarray,
    stiffness_delta: np.ndarray,
    global_direction: np.ndarray,
    free_global_dofs: np.ndarray,
    global_dof_count: int,
) -> np.ndarray:
    gathered = global_direction[dofs]
    element_actions = np.einsum(
        "eij,ej->ei",
        stiffness_delta,
        gathered,
        optimize=True,
    )
    global_action = np.zeros(global_dof_count, dtype=np.float64)
    np.add.at(global_action, dofs.ravel(), element_actions.ravel())
    return np.asarray(global_action[free_global_dofs], dtype=np.float64)


def _finite_chord_geometry_action(
    *,
    dofs: np.ndarray,
    relative_operators: np.ndarray,
    reference_chords_m: np.ndarray,
    reference_lengths_m: np.ndarray,
    axial_stiffness_n_per_m: np.ndarray,
    global_state_m: np.ndarray,
    global_direction_m: np.ndarray,
    free_global_dofs: np.ndarray,
    global_dof_count: int,
) -> np.ndarray:
    gathered_state = global_state_m[dofs]
    relative_translation = np.einsum(
        "eij,ej->ei",
        relative_operators,
        gathered_state,
        optimize=True,
    )
    current_chords = reference_chords_m + relative_translation
    current_lengths = np.linalg.norm(current_chords, axis=1)
    if np.any(current_lengths <= 1.0e-12):
        element = int(np.flatnonzero(current_lengths <= 1.0e-12)[0])
        _fail(
            "current_tangent_geometry_chord_collapsed",
            f"/apply/geometry/{element}",
            "Finite-chord axial element collapsed.",
        )
    current_directions = current_chords / current_lengths[:, None]
    reference_directions = (
        reference_chords_m / reference_lengths_m[:, None]
    )
    linear_extensions_m = np.einsum(
        "ei,ei->e",
        reference_directions,
        relative_translation,
        optimize=True,
    )
    relative_translation_squared_m2 = np.einsum(
        "ei,ei->e",
        relative_translation,
        relative_translation,
        optimize=True,
    )
    extensions_m = (
        2.0 * reference_lengths_m * linear_extensions_m
        + relative_translation_squared_m2
    ) / (current_lengths + reference_lengths_m)

    gathered_direction = global_direction_m[dofs]
    relative_direction = np.einsum(
        "eij,ej->ei",
        relative_operators,
        gathered_direction,
        optimize=True,
    )
    direction_delta = current_directions - reference_directions
    current_projection = np.einsum(
        "ei,ei->e",
        current_directions,
        relative_direction,
        optimize=True,
    )
    projection_delta = np.einsum(
        "ei,ei->e",
        direction_delta,
        relative_direction,
        optimize=True,
    )
    material_correction = axial_stiffness_n_per_m[:, None] * (
        projection_delta[:, None] * reference_directions
        + current_projection[:, None] * direction_delta
    )
    geometric_correction = (
        axial_stiffness_n_per_m * extensions_m / current_lengths
    )[:, None] * (
        relative_direction
        - current_projection[:, None] * current_directions
    )
    element_end_actions = material_correction + geometric_correction
    element_nodal_actions = np.einsum(
        "eij,ei->ej",
        relative_operators,
        element_end_actions,
        optimize=True,
    )
    global_action = np.zeros(global_dof_count, dtype=np.float64)
    np.add.at(global_action, dofs.ravel(), element_nodal_actions.ravel())
    return np.asarray(global_action[free_global_dofs], dtype=np.float64)


def _finite_vector(values: Any, *, dimension: int, path: str) -> np.ndarray:
    try:
        array = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        _fail(
            "current_tangent_apply_vector_invalid",
            path,
            f"Expected a finite FP64 vector of length {dimension}.",
            cause=exc,
        )
    if array.shape != (dimension,) or not np.all(np.isfinite(array)):
        _fail(
            "current_tangent_apply_vector_invalid",
            path,
            f"Expected a finite FP64 vector of length {dimension}.",
        )
    return np.ascontiguousarray(array, dtype=np.float64)


def _array_descriptor(
    name: str,
    array: np.ndarray,
) -> CurrentTangentArrayDescriptor:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": list(array.shape),
        "layout": "C",
        "byte_length": int(array.nbytes),
    }
    return CurrentTangentArrayDescriptor(
        name=name,
        dtype=array.dtype.str,
        shape=tuple(int(value) for value in array.shape),
        layout="C",
        byte_length=int(array.nbytes),
        data_hash=array_data_hash(array),
        content_hash=array_content_hash(metadata, array),
    )


def _validate_array(
    array: Any,
    *,
    dtype: str,
    rank: int,
    path: str,
) -> None:
    if (
        type(array) is not np.ndarray
        or array.dtype.str != dtype
        or array.ndim != rank
    ):
        _fail(
            "current_tangent_array_contract_invalid",
            path,
            f"Expected rank-{rank} canonical {dtype} array.",
        )
    if not array.flags.c_contiguous or not has_immutable_bytes_backing(array):
        _fail(
            "current_tangent_array_mutable",
            path,
            "Array requires immutable C-order bytes backing.",
        )


def _contract_payload(
    contract: CurrentTangentOperatorContract,
    *,
    include_contract_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": contract.schema_version,
        "profile": contract.profile,
        "case_id": contract.case_id,
        "residual_formula_hash": contract.residual_formula_hash,
        "source_action_contract": contract.source_action_contract,
        "array_bundle_hash": contract.array_bundle_hash,
        "dimensions": {
            "equation_count": contract.equation_count,
            "global_dof_count": contract.global_dof_count,
            "reference_nnz": contract.reference_nnz,
            "frame_element_count": contract.frame_element_count,
            "geometry_element_count": contract.geometry_element_count,
        },
        "units": {
            "force": "N",
            "displacement": "m",
            "tangent_action": "N/m",
            "load_factor": "dimensionless",
        },
        "evaluation_contract": {
            "action_expression": CURRENT_TANGENT_OPERATOR_ACTION_EXPRESSION,
            "reference_evaluator": (
                CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR
            ),
            "state_embedding": (
                "background_global_displacements_plus_free_scatter"
            ),
            "direction_embedding": "zero_global_vector_plus_free_scatter",
            "reference_csr_action": (
                "row_major_stored_entry_numpy_add_reduceat_fp64"
            ),
            "frame_load_delta_action": (
                "load_factor_times_prepacked_12x12_stiffness_delta"
            ),
            "geometry_action": (
                "stable_finite_chord_conservative_axial_correction_tangent"
            ),
            "element_scatter": "element_then_local_dof_numpy_add_at",
            "output_order": "free_global_dofs",
        },
        "array_descriptors": [
            row.to_dict() for row in contract.descriptors
        ],
        "claim_boundary": {
            "description": CURRENT_TANGENT_OPERATOR_CLAIM_BOUNDARY,
            "immutable_backend_neutral_parent_arrays": True,
            "cpu_reference_evaluator": True,
            "hip_execution": False,
            "cpu_hip_numerical_parity": False,
            "cross_platform_bit_identity": False,
            "performance": False,
            "production_nonlinear_solver": False,
            "g1_closure": False,
        },
    }
    if include_contract_hash:
        payload["contract_hash"] = contract.contract_hash
    return payload


def _require_hash(value: Any, path: str) -> str:
    if type(value) is not str or _HASH_PATTERN.fullmatch(value) is None:
        _fail("current_tangent_hash_invalid", path, "Expected canonical SHA-256.")
    return value


@lru_cache(maxsize=1)
def _schema_validator() -> Draft202012Validator:
    resource = resources.files("structural_analysis.schemas").joinpath(
        "current_tangent_operator_v1.schema.json"
    )
    with resource.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return _StrictDraft202012Validator(schema)


def _fail(
    code: str,
    path: str,
    message: str,
    *,
    cause: BaseException | None = None,
) -> None:
    error = CurrentTangentOperatorError(code, path, message)
    if cause is None:
        raise error
    raise error from cause


__all__ = [
    "CURRENT_TANGENT_OPERATOR_ACTION_EXPRESSION",
    "CURRENT_TANGENT_OPERATOR_CLAIM_BOUNDARY",
    "CURRENT_TANGENT_OPERATOR_PROFILE",
    "CURRENT_TANGENT_OPERATOR_REFERENCE_EVALUATOR",
    "CURRENT_TANGENT_OPERATOR_SCHEMA_VERSION",
    "CurrentTangentArrayDescriptor",
    "CurrentTangentOperatorContract",
    "CurrentTangentOperatorError",
    "create_current_tangent_operator",
    "validate_current_tangent_operator",
    "validate_current_tangent_operator_manifest",
]
