"""Canonical sparse-LU factor arrays and an ordered CPU apply contract.

The factor *construction* backend is deliberately outside this module.  Once
lower/upper CSR arrays and SuperLU-style row/column permutations are supplied,
the factory copies them into immutable little-endian arrays, validates the
triangular/permutation invariants, and hashes every artifact component.  The
apply path then uses a fixed row/column order and :func:`math.fsum`; it does not
call SciPy or another sparse solver backend.

This is a backend-neutral factor/apply *contract*, not evidence that factor
construction is cross-platform deterministic, that factor bytes are persisted,
or that an equivalent HIP triangular solve has executed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    has_immutable_bytes_backing,
    immutable_array,
)


CANONICAL_SPARSE_LU_SCHEMA_VERSION = "canonical-sparse-lu-factor.v1"
CANONICAL_SPARSE_LU_PROFILE = "canonical_csr_sparse_lu_factor.v1"
CANONICAL_SPARSE_LU_APPLY_PROFILE = (
    "inverse_row_permutation_csr_forward_backward_"
    "column_permutation_python_fsum_fp64.v1"
)
CANONICAL_SPARSE_LU_CLAIM_BOUNDARY = (
    "Canonical little-endian factor arrays, permutation semantics, and ordered "
    "CPU triangular apply are in contract. Factor construction, artifact "
    "persistence, cross-platform replay, HIP apply parity, and performance are "
    "not established by this contract."
)
CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION = (
    "canonical-sparse-lu-binary-artifacts.v1"
)
CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE = (
    "canonical_little_endian_sparse_lu_arrays.v1"
)

_ZERO_HASH = "sha256:" + "0" * 64
_BINARY_ARRAY_SPECS = (
    ("lower_row_pointer", "lower_row_pointer.i64le"),
    ("lower_column_indices", "lower_column_indices.i64le"),
    ("lower_numeric_values", "lower_numeric_values.f64le"),
    ("upper_row_pointer", "upper_row_pointer.i64le"),
    ("upper_column_indices", "upper_column_indices.i64le"),
    ("upper_numeric_values", "upper_numeric_values.f64le"),
    ("row_permutation", "row_permutation.i64le"),
    ("column_permutation", "column_permutation.i64le"),
)

_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class CanonicalSparseLUError(ValueError):
    """Raised when factor arrays or an apply request violate the contract."""


@dataclass(frozen=True)
class CanonicalSparseLUBinaryArtifactDescriptor:
    name: str
    dtype: str
    shape: tuple[int, ...]
    byte_length: int
    data_hash: str
    content_hash: str
    artifact_uri: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["shape"] = list(self.shape)
        return payload


@dataclass(frozen=True)
class CanonicalSparseLUBinaryArtifactBundle:
    schema_version: str
    storage_profile: str
    bundle_hash: str
    factor_contract_hash: str
    dimension: int
    source_operator_pattern_hash: str
    source_operator_numeric_values_hash: str
    total_byte_length: int
    descriptors: tuple[CanonicalSparseLUBinaryArtifactDescriptor, ...]
    _factor: CanonicalSparseLUFactor

    def to_manifest(self) -> dict[str, Any]:
        validate_canonical_sparse_lu_binary_artifact_bundle(self)
        return _binary_bundle_payload(self, include_bundle_hash=True)


def _sha256(value: Any, *, name: str) -> str:
    text = str(value)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise CanonicalSparseLUError(f"{name} must be a prefixed SHA-256")
    return text


def _vector(value: Any, *, dtype: Any, name: str) -> np.ndarray:
    try:
        result = immutable_array(value, dtype=dtype)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CanonicalSparseLUError(f"{name} is not canonical") from exc
    if result.ndim != 1:
        raise CanonicalSparseLUError(f"{name} must be one-dimensional")
    return result


def _validate_permutation(
    permutation: np.ndarray,
    *,
    dimension: int,
    name: str,
) -> None:
    if permutation.size != dimension:
        raise CanonicalSparseLUError(f"{name} dimension mismatch")
    if not np.array_equal(np.sort(permutation), np.arange(dimension)):
        raise CanonicalSparseLUError(f"{name} is not a permutation")


def _validate_triangular_csr(
    *,
    row_pointer: np.ndarray,
    column_indices: np.ndarray,
    numeric_values: np.ndarray,
    dimension: int,
    lower: bool,
) -> None:
    label = "lower" if lower else "upper"
    if row_pointer.size != dimension + 1:
        raise CanonicalSparseLUError(f"{label} row pointer dimension mismatch")
    if row_pointer[0] != 0 or row_pointer[-1] != column_indices.size:
        raise CanonicalSparseLUError(f"{label} row pointer bounds are invalid")
    if np.any(row_pointer[1:] < row_pointer[:-1]):
        raise CanonicalSparseLUError(f"{label} row pointer is not monotonic")
    if numeric_values.size != column_indices.size:
        raise CanonicalSparseLUError(f"{label} CSR arrays have unequal lengths")
    if column_indices.size < dimension:
        raise CanonicalSparseLUError(f"{label} CSR lacks diagonal entries")
    if np.any(column_indices < 0) or np.any(column_indices >= dimension):
        raise CanonicalSparseLUError(f"{label} column index is out of range")

    for row in range(dimension):
        start = int(row_pointer[row])
        stop = int(row_pointer[row + 1])
        if stop <= start:
            raise CanonicalSparseLUError(f"{label} row {row} is empty")
        row_columns = column_indices[start:stop]
        if np.any(row_columns[1:] <= row_columns[:-1]):
            raise CanonicalSparseLUError(
                f"{label} row {row} columns are not strictly ordered"
            )
        if lower:
            if row_columns[-1] != row or np.any(row_columns > row):
                raise CanonicalSparseLUError(
                    f"lower row {row} is not lower triangular"
                )
            if numeric_values[stop - 1] != 1.0:
                raise CanonicalSparseLUError(
                    f"lower row {row} lacks an explicit unit diagonal"
                )
        else:
            if row_columns[0] != row or np.any(row_columns < row):
                raise CanonicalSparseLUError(
                    f"upper row {row} is not upper triangular"
                )
            diagonal = float(numeric_values[start])
            if not math.isfinite(diagonal) or diagonal == 0.0:
                raise CanonicalSparseLUError(
                    f"upper row {row} has an invalid diagonal"
                )


def _array_manifest(name: str, array: np.ndarray) -> dict[str, Any]:
    metadata = {
        "name": name,
        "dtype": array.dtype.str,
        "shape": [int(value) for value in array.shape],
        "byte_length": int(array.nbytes),
    }
    return {
        **metadata,
        "data_hash": array_data_hash(array),
        "content_hash": array_content_hash(metadata, array),
    }


def _ordered_triangular_solve(
    *,
    row_pointer: np.ndarray,
    column_indices: np.ndarray,
    numeric_values: np.ndarray,
    right_hand_side: np.ndarray,
    lower: bool,
) -> np.ndarray:
    dimension = int(right_hand_side.size)
    solution = np.zeros(dimension, dtype=np.float64)
    rows = range(dimension) if lower else range(dimension - 1, -1, -1)
    for row in rows:
        start = int(row_pointer[row])
        stop = int(row_pointer[row + 1])
        if lower:
            tail = math.fsum(
                float(numeric_values[position])
                * float(solution[int(column_indices[position])])
                for position in range(start, stop - 1)
            )
            diagonal = 1.0
        else:
            diagonal = float(numeric_values[start])
            tail = math.fsum(
                float(numeric_values[position])
                * float(solution[int(column_indices[position])])
                for position in range(start + 1, stop)
            )
        solution[row] = (float(right_hand_side[row]) - tail) / diagonal
    if not np.all(np.isfinite(solution)):
        raise CanonicalSparseLUError(
            "ordered sparse triangular solve produced non-finite values"
        )
    return solution


def _canonical_factor_contract_hash(
    *,
    dimension: int,
    source_operator_pattern_hash: str,
    source_operator_numeric_values_hash: str,
    lower_row_pointer: np.ndarray,
    lower_column_indices: np.ndarray,
    lower_numeric_values: np.ndarray,
    upper_row_pointer: np.ndarray,
    upper_column_indices: np.ndarray,
    upper_numeric_values: np.ndarray,
    row_permutation: np.ndarray,
    column_permutation: np.ndarray,
) -> str:
    array_hashes = {
        "lower_row_pointer": array_data_hash(lower_row_pointer),
        "lower_column_indices": array_data_hash(lower_column_indices),
        "lower_numeric_values": array_data_hash(lower_numeric_values),
        "upper_row_pointer": array_data_hash(upper_row_pointer),
        "upper_column_indices": array_data_hash(upper_column_indices),
        "upper_numeric_values": array_data_hash(upper_numeric_values),
        "row_permutation": array_data_hash(row_permutation),
        "column_permutation": array_data_hash(column_permutation),
    }
    return canonical_hash(
        {
            "schema_version": CANONICAL_SPARSE_LU_SCHEMA_VERSION,
            "profile": CANONICAL_SPARSE_LU_PROFILE,
            "apply_profile": CANONICAL_SPARSE_LU_APPLY_PROFILE,
            "dimension": dimension,
            "source_operator_pattern_hash": source_operator_pattern_hash,
            "source_operator_numeric_values_hash": (
                source_operator_numeric_values_hash
            ),
            "array_data_hashes": array_hashes,
            "row_permutation_application": "inverse_gather_rhs",
            "column_permutation_application": "forward_gather_solution",
            "factor_force_unit": "N",
            "input_force_unit": "kN",
            "output_displacement_unit": "m",
        }
    )


@dataclass(frozen=True)
class CanonicalSparseLUFactor:
    """Immutable canonical CSR sparse-LU factor and ordered apply."""

    dimension: int
    source_operator_pattern_hash: str
    source_operator_numeric_values_hash: str
    lower_row_pointer: np.ndarray
    lower_column_indices: np.ndarray
    lower_numeric_values: np.ndarray
    upper_row_pointer: np.ndarray
    upper_column_indices: np.ndarray
    upper_numeric_values: np.ndarray
    row_permutation: np.ndarray
    column_permutation: np.ndarray
    inverse_row_permutation: np.ndarray
    contract_hash: str

    def solve_kn_to_m(self, right_hand_side_kn: Any) -> np.ndarray:
        """Apply the factor to a kN right-hand side and return metres."""

        try:
            right_hand_side = np.ascontiguousarray(
                right_hand_side_kn,
                dtype=np.float64,
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise CanonicalSparseLUError(
                "right-hand side cannot be represented as float64"
            ) from exc
        if right_hand_side.ndim != 1 or right_hand_side.size != self.dimension:
            raise CanonicalSparseLUError("right-hand side dimension mismatch")
        if not np.all(np.isfinite(right_hand_side)):
            raise CanonicalSparseLUError("right-hand side must be finite")
        right_hand_side_n = right_hand_side * 1000.0
        permuted = right_hand_side_n[self.inverse_row_permutation]
        lower_solution = _ordered_triangular_solve(
            row_pointer=self.lower_row_pointer,
            column_indices=self.lower_column_indices,
            numeric_values=self.lower_numeric_values,
            right_hand_side=permuted,
            lower=True,
        )
        upper_solution = _ordered_triangular_solve(
            row_pointer=self.upper_row_pointer,
            column_indices=self.upper_column_indices,
            numeric_values=self.upper_numeric_values,
            right_hand_side=lower_solution,
            lower=False,
        )
        solution = np.ascontiguousarray(
            upper_solution[self.column_permutation],
            dtype=np.float64,
        )
        if not np.all(np.isfinite(solution)):
            raise CanonicalSparseLUError(
                "canonical sparse-LU apply produced non-finite values"
            )
        return solution

    def manifest(self) -> dict[str, Any]:
        """Return the self-describing binary-array factor manifest."""

        arrays = {
            "lower_row_pointer": _array_manifest(
                "lower_row_pointer",
                self.lower_row_pointer,
            ),
            "lower_column_indices": _array_manifest(
                "lower_column_indices",
                self.lower_column_indices,
            ),
            "lower_numeric_values": _array_manifest(
                "lower_numeric_values",
                self.lower_numeric_values,
            ),
            "upper_row_pointer": _array_manifest(
                "upper_row_pointer",
                self.upper_row_pointer,
            ),
            "upper_column_indices": _array_manifest(
                "upper_column_indices",
                self.upper_column_indices,
            ),
            "upper_numeric_values": _array_manifest(
                "upper_numeric_values",
                self.upper_numeric_values,
            ),
            "row_permutation": _array_manifest(
                "row_permutation",
                self.row_permutation,
            ),
            "column_permutation": _array_manifest(
                "column_permutation",
                self.column_permutation,
            ),
        }
        return {
            "schema_version": CANONICAL_SPARSE_LU_SCHEMA_VERSION,
            "profile": CANONICAL_SPARSE_LU_PROFILE,
            "contract_hash": self.contract_hash,
            "dimension": self.dimension,
            "source_operator_pattern_hash": (
                self.source_operator_pattern_hash
            ),
            "source_operator_numeric_values_hash": (
                self.source_operator_numeric_values_hash
            ),
            "lower_nnz": int(self.lower_numeric_values.size),
            "upper_nnz": int(self.upper_numeric_values.size),
            "factor_nnz": int(
                self.lower_numeric_values.size
                + self.upper_numeric_values.size
            ),
            "array_count": len(arrays),
            "total_byte_length": int(
                sum(row["byte_length"] for row in arrays.values())
            ),
            "arrays": arrays,
            "apply_contract": {
                "profile": CANONICAL_SPARSE_LU_APPLY_PROFILE,
                "factor_force_unit": "N",
                "input_force_unit": "kN",
                "output_displacement_unit": "m",
                "input_conversion_to_n": 1000.0,
                "row_permutation_application": "inverse_gather_rhs",
                "column_permutation_application": (
                    "forward_gather_solution"
                ),
                "lower_diagonal": "explicit_unit",
                "upper_diagonal": "explicit_nonzero",
                "row_order": "lower_ascending_upper_descending",
                "within_row_accumulation": (
                    "ascending_column_python_fsum_fp64"
                ),
            },
            "claim_boundary": CANONICAL_SPARSE_LU_CLAIM_BOUNDARY,
        }


def create_canonical_sparse_lu_factor(
    *,
    lower_row_pointer: Any,
    lower_column_indices: Any,
    lower_numeric_values: Any,
    upper_row_pointer: Any,
    upper_column_indices: Any,
    upper_numeric_values: Any,
    row_permutation: Any,
    column_permutation: Any,
    source_operator_pattern_hash: str,
    source_operator_numeric_values_hash: str,
) -> CanonicalSparseLUFactor:
    """Validate and freeze one backend-produced sparse-LU factor."""

    lower_indptr = _vector(
        lower_row_pointer,
        dtype="<i8",
        name="lower_row_pointer",
    )
    lower_indices = _vector(
        lower_column_indices,
        dtype="<i8",
        name="lower_column_indices",
    )
    lower_values = _vector(
        lower_numeric_values,
        dtype="<f8",
        name="lower_numeric_values",
    )
    upper_indptr = _vector(
        upper_row_pointer,
        dtype="<i8",
        name="upper_row_pointer",
    )
    upper_indices = _vector(
        upper_column_indices,
        dtype="<i8",
        name="upper_column_indices",
    )
    upper_values = _vector(
        upper_numeric_values,
        dtype="<f8",
        name="upper_numeric_values",
    )
    row_perm = _vector(
        row_permutation,
        dtype="<i8",
        name="row_permutation",
    )
    column_perm = _vector(
        column_permutation,
        dtype="<i8",
        name="column_permutation",
    )
    dimension = int(row_perm.size)
    if dimension < 1:
        raise CanonicalSparseLUError("factor dimension must be positive")
    _validate_permutation(
        row_perm,
        dimension=dimension,
        name="row_permutation",
    )
    _validate_permutation(
        column_perm,
        dimension=dimension,
        name="column_permutation",
    )
    _validate_triangular_csr(
        row_pointer=lower_indptr,
        column_indices=lower_indices,
        numeric_values=lower_values,
        dimension=dimension,
        lower=True,
    )
    _validate_triangular_csr(
        row_pointer=upper_indptr,
        column_indices=upper_indices,
        numeric_values=upper_values,
        dimension=dimension,
        lower=False,
    )
    source_pattern_hash = _sha256(
        source_operator_pattern_hash,
        name="source_operator_pattern_hash",
    )
    source_values_hash = _sha256(
        source_operator_numeric_values_hash,
        name="source_operator_numeric_values_hash",
    )
    inverse_row = np.empty(dimension, dtype=np.int64)
    inverse_row[np.asarray(row_perm, dtype=np.int64)] = np.arange(
        dimension,
        dtype=np.int64,
    )
    inverse_row = immutable_array(inverse_row, dtype="<i8")

    contract_hash = _canonical_factor_contract_hash(
        dimension=dimension,
        source_operator_pattern_hash=source_pattern_hash,
        source_operator_numeric_values_hash=source_values_hash,
        lower_row_pointer=lower_indptr,
        lower_column_indices=lower_indices,
        lower_numeric_values=lower_values,
        upper_row_pointer=upper_indptr,
        upper_column_indices=upper_indices,
        upper_numeric_values=upper_values,
        row_permutation=row_perm,
        column_permutation=column_perm,
    )
    factor = CanonicalSparseLUFactor(
        dimension=dimension,
        source_operator_pattern_hash=source_pattern_hash,
        source_operator_numeric_values_hash=source_values_hash,
        lower_row_pointer=lower_indptr,
        lower_column_indices=lower_indices,
        lower_numeric_values=lower_values,
        upper_row_pointer=upper_indptr,
        upper_column_indices=upper_indices,
        upper_numeric_values=upper_values,
        row_permutation=row_perm,
        column_permutation=column_perm,
        inverse_row_permutation=inverse_row,
        contract_hash=contract_hash,
    )
    for array in (
        factor.lower_row_pointer,
        factor.lower_column_indices,
        factor.lower_numeric_values,
        factor.upper_row_pointer,
        factor.upper_column_indices,
        factor.upper_numeric_values,
        factor.row_permutation,
        factor.column_permutation,
        factor.inverse_row_permutation,
    ):
        if not has_immutable_bytes_backing(array):
            raise CanonicalSparseLUError("factor array is not immutable")
    return factor


def validate_canonical_sparse_lu_factor(
    factor: CanonicalSparseLUFactor,
) -> CanonicalSparseLUFactor:
    if type(factor) is not CanonicalSparseLUFactor:
        raise CanonicalSparseLUError("expected CanonicalSparseLUFactor")
    if factor.dimension < 1:
        raise CanonicalSparseLUError("factor dimension must be positive")
    source_pattern_hash = _sha256(
        factor.source_operator_pattern_hash,
        name="source_operator_pattern_hash",
    )
    source_values_hash = _sha256(
        factor.source_operator_numeric_values_hash,
        name="source_operator_numeric_values_hash",
    )
    _validate_canonical_factor_array(
        factor.lower_row_pointer,
        dtype="<i8",
        name="lower_row_pointer",
    )
    _validate_canonical_factor_array(
        factor.lower_column_indices,
        dtype="<i8",
        name="lower_column_indices",
    )
    _validate_canonical_factor_array(
        factor.lower_numeric_values,
        dtype="<f8",
        name="lower_numeric_values",
    )
    _validate_canonical_factor_array(
        factor.upper_row_pointer,
        dtype="<i8",
        name="upper_row_pointer",
    )
    _validate_canonical_factor_array(
        factor.upper_column_indices,
        dtype="<i8",
        name="upper_column_indices",
    )
    _validate_canonical_factor_array(
        factor.upper_numeric_values,
        dtype="<f8",
        name="upper_numeric_values",
    )
    _validate_canonical_factor_array(
        factor.row_permutation,
        dtype="<i8",
        name="row_permutation",
    )
    _validate_canonical_factor_array(
        factor.column_permutation,
        dtype="<i8",
        name="column_permutation",
    )
    _validate_canonical_factor_array(
        factor.inverse_row_permutation,
        dtype="<i8",
        name="inverse_row_permutation",
    )
    _validate_permutation(
        factor.row_permutation,
        dimension=factor.dimension,
        name="row_permutation",
    )
    _validate_permutation(
        factor.column_permutation,
        dimension=factor.dimension,
        name="column_permutation",
    )
    _validate_permutation(
        factor.inverse_row_permutation,
        dimension=factor.dimension,
        name="inverse_row_permutation",
    )
    expected_inverse = np.empty(factor.dimension, dtype=np.int64)
    expected_inverse[np.asarray(factor.row_permutation)] = np.arange(
        factor.dimension,
        dtype=np.int64,
    )
    if not np.array_equal(factor.inverse_row_permutation, expected_inverse):
        raise CanonicalSparseLUError("inverse row permutation is stale")
    _validate_triangular_csr(
        row_pointer=factor.lower_row_pointer,
        column_indices=factor.lower_column_indices,
        numeric_values=factor.lower_numeric_values,
        dimension=factor.dimension,
        lower=True,
    )
    _validate_triangular_csr(
        row_pointer=factor.upper_row_pointer,
        column_indices=factor.upper_column_indices,
        numeric_values=factor.upper_numeric_values,
        dimension=factor.dimension,
        lower=False,
    )
    expected_hash = _canonical_factor_contract_hash(
        dimension=factor.dimension,
        source_operator_pattern_hash=source_pattern_hash,
        source_operator_numeric_values_hash=source_values_hash,
        lower_row_pointer=factor.lower_row_pointer,
        lower_column_indices=factor.lower_column_indices,
        lower_numeric_values=factor.lower_numeric_values,
        upper_row_pointer=factor.upper_row_pointer,
        upper_column_indices=factor.upper_column_indices,
        upper_numeric_values=factor.upper_numeric_values,
        row_permutation=factor.row_permutation,
        column_permutation=factor.column_permutation,
    )
    if factor.contract_hash != expected_hash:
        raise CanonicalSparseLUError("factor contract hash is stale")
    return factor


def create_canonical_sparse_lu_binary_artifact_bundle(
    factor: CanonicalSparseLUFactor,
    *,
    artifact_uri_prefix: str,
) -> CanonicalSparseLUBinaryArtifactBundle:
    validated = validate_canonical_sparse_lu_factor(factor)
    prefix = _binary_artifact_uri_prefix(artifact_uri_prefix)
    arrays = _binary_factor_arrays(validated)
    descriptors = tuple(
        _binary_artifact_descriptor(
            name=name,
            array=arrays[name],
            artifact_uri=f"{prefix}/{filename}",
        )
        for name, filename in _BINARY_ARRAY_SPECS
    )
    provisional = CanonicalSparseLUBinaryArtifactBundle(
        schema_version=CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION,
        storage_profile=CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE,
        bundle_hash=_ZERO_HASH,
        factor_contract_hash=validated.contract_hash,
        dimension=validated.dimension,
        source_operator_pattern_hash=(
            validated.source_operator_pattern_hash
        ),
        source_operator_numeric_values_hash=(
            validated.source_operator_numeric_values_hash
        ),
        total_byte_length=int(sum(row.byte_length for row in descriptors)),
        descriptors=descriptors,
        _factor=validated,
    )
    bundle = replace(
        provisional,
        bundle_hash=canonical_hash(
            _binary_bundle_payload(provisional, include_bundle_hash=False)
        ),
    )
    return validate_canonical_sparse_lu_binary_artifact_bundle(bundle)


def validate_canonical_sparse_lu_binary_artifact_bundle(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
) -> CanonicalSparseLUBinaryArtifactBundle:
    if type(bundle) is not CanonicalSparseLUBinaryArtifactBundle:
        raise CanonicalSparseLUError(
            "expected CanonicalSparseLUBinaryArtifactBundle"
        )
    factor = validate_canonical_sparse_lu_factor(bundle._factor)
    if (
        bundle.schema_version
        != CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION
        or bundle.storage_profile
        != CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE
        or bundle.factor_contract_hash != factor.contract_hash
        or bundle.dimension != factor.dimension
        or bundle.source_operator_pattern_hash
        != factor.source_operator_pattern_hash
        or bundle.source_operator_numeric_values_hash
        != factor.source_operator_numeric_values_hash
    ):
        raise CanonicalSparseLUError("binary artifact source binding is stale")
    if (
        type(bundle.descriptors) is not tuple
        or len(bundle.descriptors) != len(_BINARY_ARRAY_SPECS)
        or any(
            type(row) is not CanonicalSparseLUBinaryArtifactDescriptor
            for row in bundle.descriptors
        )
    ):
        raise CanonicalSparseLUError("binary artifact descriptor set is invalid")
    arrays = _binary_factor_arrays(factor)
    expected_names = tuple(name for name, _filename in _BINARY_ARRAY_SPECS)
    if tuple(row.name for row in bundle.descriptors) != expected_names:
        raise CanonicalSparseLUError("binary artifact descriptor order is invalid")
    uris: list[str] = []
    for descriptor, (name, filename) in zip(
        bundle.descriptors,
        _BINARY_ARRAY_SPECS,
        strict=True,
    ):
        expected = _binary_artifact_descriptor(
            name=name,
            array=arrays[name],
            artifact_uri=descriptor.artifact_uri,
        )
        if descriptor != expected or not descriptor.artifact_uri.endswith(
            f"/{filename}"
        ):
            raise CanonicalSparseLUError(
                f"binary artifact descriptor {name} is stale"
            )
        uris.append(descriptor.artifact_uri)
    if len(set(uris)) != len(uris):
        raise CanonicalSparseLUError("binary artifact URIs are not unique")
    expected_total = int(sum(row.byte_length for row in bundle.descriptors))
    if bundle.total_byte_length != expected_total:
        raise CanonicalSparseLUError("binary artifact byte length is stale")
    validate_canonical_sparse_lu_binary_artifact_manifest(
        _binary_bundle_payload(bundle, include_bundle_hash=True)
    )
    return bundle


def validate_canonical_sparse_lu_binary_artifact_manifest(
    payload: Any,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CanonicalSparseLUError("binary artifact manifest must be an object")
    required = {
        "schema_version",
        "storage_profile",
        "bundle_hash",
        "factor_contract_hash",
        "dimension",
        "source_operator_pattern_hash",
        "source_operator_numeric_values_hash",
        "artifact_count",
        "total_byte_length",
        "artifacts",
        "claim_boundary",
    }
    if set(payload) != required:
        raise CanonicalSparseLUError("binary artifact manifest fields are invalid")
    if (
        payload["schema_version"]
        != CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION
        or payload["storage_profile"]
        != CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE
        or type(payload["dimension"]) is not int
        or payload["dimension"] < 1
        or payload["artifact_count"] != len(_BINARY_ARRAY_SPECS)
        or type(payload["total_byte_length"]) is not int
        or payload["total_byte_length"] < 1
    ):
        raise CanonicalSparseLUError("binary artifact manifest semantics are invalid")
    _sha256(payload["bundle_hash"], name="bundle_hash")
    _sha256(payload["factor_contract_hash"], name="factor_contract_hash")
    _sha256(
        payload["source_operator_pattern_hash"],
        name="source_operator_pattern_hash",
    )
    _sha256(
        payload["source_operator_numeric_values_hash"],
        name="source_operator_numeric_values_hash",
    )
    artifacts = payload["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != len(
        _BINARY_ARRAY_SPECS
    ):
        raise CanonicalSparseLUError("binary artifact descriptor list is invalid")
    total = 0
    for descriptor, (name, filename) in zip(
        artifacts,
        _BINARY_ARRAY_SPECS,
        strict=True,
    ):
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("name") != name
            or not str(descriptor.get("artifact_uri", "")).endswith(
                f"/{filename}"
            )
        ):
            raise CanonicalSparseLUError(
                f"binary artifact manifest descriptor {name} is invalid"
            )
        total += int(descriptor["byte_length"])
    if total != payload["total_byte_length"]:
        raise CanonicalSparseLUError("binary artifact manifest byte length is stale")
    without_hash = dict(payload)
    claimed_hash = without_hash.pop("bundle_hash")
    if claimed_hash != canonical_hash(without_hash):
        raise CanonicalSparseLUError("binary artifact bundle hash is stale")
    return payload


def write_canonical_sparse_lu_binary_artifacts(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
    output_directory: str | Path,
) -> CanonicalSparseLUBinaryArtifactBundle:
    validated = validate_canonical_sparse_lu_binary_artifact_bundle(bundle)
    directory = Path(output_directory)
    directory.mkdir(parents=True, exist_ok=True)
    arrays = _binary_factor_arrays(validated._factor)
    targets = {
        name: directory / filename
        for name, filename in _BINARY_ARRAY_SPECS
    }
    for name, target in targets.items():
        if target.exists():
            raise CanonicalSparseLUError(
                f"refusing to overwrite binary factor artifact {name}"
            )
    created: list[Path] = []
    try:
        for name, target in targets.items():
            with target.open("xb") as handle:
                created.append(target)
                handle.write(memoryview(arrays[name]).cast("B"))
            _validate_canonical_sparse_lu_binary_artifact_bytes(
                validated,
                name=name,
                data=target.read_bytes(),
            )
    except Exception:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise
    return validated


def read_canonical_sparse_lu_binary_artifacts(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
    input_directory: str | Path,
) -> CanonicalSparseLUFactor:
    validated = validate_canonical_sparse_lu_binary_artifact_bundle(bundle)
    directory = Path(input_directory)
    descriptor_by_name = {row.name: row for row in validated.descriptors}
    arrays: dict[str, np.ndarray] = {}
    for name, filename in _BINARY_ARRAY_SPECS:
        raw = (directory / filename).read_bytes()
        _validate_canonical_sparse_lu_binary_artifact_bytes(
            validated,
            name=name,
            data=raw,
        )
        descriptor = descriptor_by_name[name]
        arrays[name] = np.frombuffer(raw, dtype=descriptor.dtype).reshape(
            descriptor.shape
        )
    replay = create_canonical_sparse_lu_factor(
        lower_row_pointer=arrays["lower_row_pointer"],
        lower_column_indices=arrays["lower_column_indices"],
        lower_numeric_values=arrays["lower_numeric_values"],
        upper_row_pointer=arrays["upper_row_pointer"],
        upper_column_indices=arrays["upper_column_indices"],
        upper_numeric_values=arrays["upper_numeric_values"],
        row_permutation=arrays["row_permutation"],
        column_permutation=arrays["column_permutation"],
        source_operator_pattern_hash=(
            validated.source_operator_pattern_hash
        ),
        source_operator_numeric_values_hash=(
            validated.source_operator_numeric_values_hash
        ),
    )
    if replay.contract_hash != validated.factor_contract_hash:
        raise CanonicalSparseLUError(
            "reloaded binary factor contract hash is stale"
        )
    return replay


def validate_canonical_sparse_lu_binary_artifact_bytes(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
    *,
    name: str,
    data: bytes | bytearray | memoryview,
) -> None:
    validated = validate_canonical_sparse_lu_binary_artifact_bundle(bundle)
    _validate_canonical_sparse_lu_binary_artifact_bytes(
        validated,
        name=name,
        data=data,
    )


def _validate_canonical_sparse_lu_binary_artifact_bytes(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
    *,
    name: str,
    data: bytes | bytearray | memoryview,
) -> None:
    descriptor_by_name = {row.name: row for row in bundle.descriptors}
    if name not in descriptor_by_name:
        raise CanonicalSparseLUError("unknown binary factor artifact")
    descriptor = descriptor_by_name[name]
    raw = bytes(data)
    if len(raw) != descriptor.byte_length:
        raise CanonicalSparseLUError(
            f"binary factor artifact {name} byte length mismatch"
        )
    array = np.frombuffer(raw, dtype=descriptor.dtype).reshape(
        descriptor.shape
    )
    expected = _binary_artifact_descriptor(
        name=name,
        array=array,
        artifact_uri=descriptor.artifact_uri,
    )
    if expected != descriptor:
        raise CanonicalSparseLUError(
            f"binary factor artifact {name} hash mismatch"
        )


def _validate_canonical_factor_array(
    value: Any,
    *,
    dtype: str,
    name: str,
) -> None:
    if (
        not isinstance(value, np.ndarray)
        or value.ndim != 1
        or value.dtype.str != dtype
        or not value.flags.c_contiguous
        or not has_immutable_bytes_backing(value)
        or (value.dtype.kind == "f" and not np.all(np.isfinite(value)))
    ):
        raise CanonicalSparseLUError(f"{name} is not immutable canonical {dtype}")


def _binary_factor_arrays(
    factor: CanonicalSparseLUFactor,
) -> dict[str, np.ndarray]:
    return {
        name: getattr(factor, name)
        for name, _filename in _BINARY_ARRAY_SPECS
    }


def _binary_artifact_descriptor(
    *,
    name: str,
    array: np.ndarray,
    artifact_uri: str,
) -> CanonicalSparseLUBinaryArtifactDescriptor:
    row = _array_manifest(name, array)
    return CanonicalSparseLUBinaryArtifactDescriptor(
        name=name,
        dtype=row["dtype"],
        shape=tuple(row["shape"]),
        byte_length=row["byte_length"],
        data_hash=row["data_hash"],
        content_hash=row["content_hash"],
        artifact_uri=artifact_uri,
    )


def _binary_artifact_uri_prefix(value: Any) -> str:
    if type(value) is not str:
        raise CanonicalSparseLUError("artifact URI prefix must be text")
    normalized = value.rstrip("/")
    if not normalized or any(ord(character) < 32 for character in normalized):
        raise CanonicalSparseLUError("artifact URI prefix is invalid")
    return normalized


def _binary_bundle_payload(
    bundle: CanonicalSparseLUBinaryArtifactBundle,
    *,
    include_bundle_hash: bool,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": bundle.schema_version,
        "storage_profile": bundle.storage_profile,
        "factor_contract_hash": bundle.factor_contract_hash,
        "dimension": bundle.dimension,
        "source_operator_pattern_hash": (
            bundle.source_operator_pattern_hash
        ),
        "source_operator_numeric_values_hash": (
            bundle.source_operator_numeric_values_hash
        ),
        "artifact_count": len(bundle.descriptors),
        "total_byte_length": bundle.total_byte_length,
        "artifacts": [row.to_dict() for row in bundle.descriptors],
        "claim_boundary": {
            "descriptor_only_manifest": True,
            "canonical_little_endian_binary": True,
            "writer_and_byte_validation_required": True,
            "readback_reconstructs_factor_contract": True,
            "artifact_presence_proven_by_manifest": False,
            "hip_execution_proven_by_manifest": False,
        },
    }
    if include_bundle_hash:
        payload["bundle_hash"] = bundle.bundle_hash
    return payload


__all__ = [
    "CANONICAL_SPARSE_LU_APPLY_PROFILE",
    "CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION",
    "CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE",
    "CANONICAL_SPARSE_LU_CLAIM_BOUNDARY",
    "CANONICAL_SPARSE_LU_PROFILE",
    "CANONICAL_SPARSE_LU_SCHEMA_VERSION",
    "CanonicalSparseLUError",
    "CanonicalSparseLUFactor",
    "CanonicalSparseLUBinaryArtifactBundle",
    "CanonicalSparseLUBinaryArtifactDescriptor",
    "create_canonical_sparse_lu_factor",
    "create_canonical_sparse_lu_binary_artifact_bundle",
    "read_canonical_sparse_lu_binary_artifacts",
    "validate_canonical_sparse_lu_binary_artifact_bundle",
    "validate_canonical_sparse_lu_binary_artifact_bytes",
    "validate_canonical_sparse_lu_binary_artifact_manifest",
    "validate_canonical_sparse_lu_factor",
    "write_canonical_sparse_lu_binary_artifacts",
]
