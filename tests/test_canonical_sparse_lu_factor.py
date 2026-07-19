from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import numpy as np
import pytest
from scipy.sparse import csc_matrix
from scipy.sparse.linalg import splu

from structural_analysis.engine_v2.contracts._canonical import (
    has_immutable_bytes_backing,
)
from structural_analysis.solvers.nonlinear.canonical_sparse_lu import (
    CANONICAL_SPARSE_LU_APPLY_PROFILE,
    CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION,
    CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE,
    CANONICAL_SPARSE_LU_PROFILE,
    CanonicalSparseLUError,
    create_canonical_sparse_lu_binary_artifact_bundle,
    create_canonical_sparse_lu_factor,
    read_canonical_sparse_lu_binary_artifacts,
    validate_canonical_sparse_lu_binary_artifact_bytes,
    validate_canonical_sparse_lu_binary_artifact_manifest,
    validate_canonical_sparse_lu_factor,
    write_canonical_sparse_lu_binary_artifacts,
)


SOURCE_PATTERN_HASH = "sha256:" + "1" * 64
SOURCE_VALUES_HASH = "sha256:" + "2" * 64
ROOT = Path(__file__).resolve().parents[1]
BINARY_SCHEMA = (
    ROOT
    / "src/structural_analysis/schemas/"
    "canonical_sparse_lu_binary_artifacts_v1.schema.json"
)


def _from_superlu(matrix: np.ndarray):
    factorization = splu(csc_matrix(matrix), permc_spec="COLAMD")
    lower = factorization.L.tocsr()
    upper = factorization.U.tocsr()
    lower.sort_indices()
    upper.sort_indices()
    factor = create_canonical_sparse_lu_factor(
        lower_row_pointer=lower.indptr,
        lower_column_indices=lower.indices,
        lower_numeric_values=lower.data,
        upper_row_pointer=upper.indptr,
        upper_column_indices=upper.indices,
        upper_numeric_values=upper.data,
        row_permutation=factorization.perm_r,
        column_permutation=factorization.perm_c,
        source_operator_pattern_hash=SOURCE_PATTERN_HASH,
        source_operator_numeric_values_hash=SOURCE_VALUES_HASH,
    )
    return factor, factorization


def _identity_factor(**overrides):
    kwargs = {
        "lower_row_pointer": np.array([0, 1, 2]),
        "lower_column_indices": np.array([0, 1]),
        "lower_numeric_values": np.array([1.0, 1.0]),
        "upper_row_pointer": np.array([0, 1, 2]),
        "upper_column_indices": np.array([0, 1]),
        "upper_numeric_values": np.array([2.0, 4.0]),
        "row_permutation": np.array([0, 1]),
        "column_permutation": np.array([0, 1]),
        "source_operator_pattern_hash": SOURCE_PATTERN_HASH,
        "source_operator_numeric_values_hash": SOURCE_VALUES_HASH,
    }
    kwargs.update(overrides)
    return create_canonical_sparse_lu_factor(**kwargs)


def test_canonical_factor_replays_superlu_with_ordered_triangular_apply() -> None:
    matrix = np.array(
        [
            [8.0, 2.0, 0.0, 0.0, 1.0],
            [2.0, 7.0, 3.0, 0.0, 0.0],
            [0.0, 3.0, 9.0, 1.0, 0.0],
            [0.0, 0.0, 1.0, 6.0, 2.0],
            [1.0, 0.0, 0.0, 2.0, 5.0],
        ],
        dtype=np.float64,
    )
    factor, superlu = _from_superlu(matrix)
    right_hand_side_kn = np.array([1.25, -0.5, 0.75, 2.0, -1.0])

    solution = factor.solve_kn_to_m(right_hand_side_kn)
    repeated = factor.solve_kn_to_m(right_hand_side_kn)
    expected = superlu.solve(right_hand_side_kn * 1000.0)

    np.testing.assert_allclose(solution, expected, rtol=1.0e-14, atol=1.0e-12)
    np.testing.assert_allclose(
        matrix @ solution,
        right_hand_side_kn * 1000.0,
        rtol=1.0e-13,
        atol=1.0e-10,
    )
    assert np.array_equal(solution, repeated)

    manifest = factor.manifest()
    assert manifest["profile"] == CANONICAL_SPARSE_LU_PROFILE
    assert manifest["contract_hash"] == factor.contract_hash
    assert manifest["dimension"] == 5
    assert manifest["factor_nnz"] == (
        factor.lower_numeric_values.size + factor.upper_numeric_values.size
    )
    assert manifest["array_count"] == 8
    assert manifest["total_byte_length"] == sum(
        row["byte_length"] for row in manifest["arrays"].values()
    )
    assert manifest["apply_contract"]["profile"] == (
        CANONICAL_SPARSE_LU_APPLY_PROFILE
    )
    assert manifest["apply_contract"]["row_permutation_application"] == (
        "inverse_gather_rhs"
    )
    assert manifest["apply_contract"]["column_permutation_application"] == (
        "forward_gather_solution"
    )
    for name, row in manifest["arrays"].items():
        assert row["name"] == name
        assert row["dtype"] in {"<f8", "<i8"}
        assert row["byte_length"] > 0
        assert row["data_hash"].startswith("sha256:")
        assert row["content_hash"].startswith("sha256:")


def test_factor_arrays_are_detached_and_immutably_byte_backed() -> None:
    lower_values = np.array([1.0, 1.0])
    factor = _identity_factor(lower_numeric_values=lower_values)
    lower_values[0] = 99.0

    assert factor.lower_numeric_values.tolist() == [1.0, 1.0]
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
        assert has_immutable_bytes_backing(array)
        with pytest.raises(ValueError):
            array.setflags(write=True)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        (
            {"row_permutation": np.array([0, 0])},
            "row_permutation is not a permutation",
        ),
        (
            {"lower_row_pointer": np.array([0, 1])},
            "lower row pointer dimension mismatch",
        ),
        (
            {"lower_column_indices": np.array([1, 1])},
            "lower row 0 is not lower triangular",
        ),
        (
            {"lower_numeric_values": np.array([2.0, 1.0])},
            "lower row 0 lacks an explicit unit diagonal",
        ),
        (
            {"upper_numeric_values": np.array([0.0, 4.0])},
            "upper row 0 has an invalid diagonal",
        ),
        (
            {"source_operator_pattern_hash": "not-a-hash"},
            "source_operator_pattern_hash must be a prefixed SHA-256",
        ),
    ],
)
def test_factor_creation_fails_closed(override, message: str) -> None:
    with pytest.raises(CanonicalSparseLUError, match=message):
        _identity_factor(**override)


def test_apply_fails_closed_for_bad_right_hand_side() -> None:
    factor = _identity_factor()

    with pytest.raises(CanonicalSparseLUError, match="dimension mismatch"):
        factor.solve_kn_to_m([1.0])
    with pytest.raises(CanonicalSparseLUError, match="must be finite"):
        factor.solve_kn_to_m([1.0, np.nan])


def test_contract_hash_is_stable_and_unit_conversion_is_explicit() -> None:
    first = _identity_factor()
    second = _identity_factor()

    assert first.contract_hash == second.contract_hash
    np.testing.assert_array_equal(
        first.solve_kn_to_m([2.0, 4.0]),
        np.array([1000.0, 1000.0]),
    )
    manifest = first.manifest()
    assert manifest["apply_contract"]["factor_force_unit"] == "N"
    assert manifest["apply_contract"]["input_force_unit"] == "kN"
    assert manifest["apply_contract"]["output_displacement_unit"] == "m"
    assert manifest["apply_contract"]["input_conversion_to_n"] == 1000.0


def test_binary_bundle_writes_reloads_and_replays_exact_factor(
    tmp_path: Path,
) -> None:
    matrix = np.array(
        [
            [8.0, 2.0, 0.0, 1.0],
            [2.0, 7.0, 3.0, 0.0],
            [0.0, 3.0, 9.0, 1.0],
            [1.0, 0.0, 1.0, 6.0],
        ],
        dtype=np.float64,
    )
    factor, _superlu = _from_superlu(matrix)
    bundle = create_canonical_sparse_lu_binary_artifact_bundle(
        factor,
        artifact_uri_prefix="artifact://case/factor/",
    )
    payload = bundle.to_manifest()
    schema = json.loads(BINARY_SCHEMA.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    assert payload["schema_version"] == (
        CANONICAL_SPARSE_LU_BINARY_ARTIFACT_SCHEMA_VERSION
    )
    assert payload["storage_profile"] == (
        CANONICAL_SPARSE_LU_BINARY_STORAGE_PROFILE
    )
    assert payload["factor_contract_hash"] == factor.contract_hash
    assert payload["artifact_count"] == 8
    assert payload["total_byte_length"] == sum(
        row["byte_length"] for row in payload["artifacts"]
    )

    output = tmp_path / "factor"
    write_canonical_sparse_lu_binary_artifacts(bundle, output)
    replay = read_canonical_sparse_lu_binary_artifacts(bundle, output)
    right_hand_side = np.array([1.25, -0.5, 0.75, 2.0])

    assert replay.contract_hash == factor.contract_hash
    np.testing.assert_array_equal(
        replay.solve_kn_to_m(right_hand_side),
        factor.solve_kn_to_m(right_hand_side),
    )
    for descriptor in bundle.descriptors:
        filename = descriptor.artifact_uri.rsplit("/", 1)[-1]
        validate_canonical_sparse_lu_binary_artifact_bytes(
            bundle,
            name=descriptor.name,
            data=(output / filename).read_bytes(),
        )


def test_binary_artifacts_reject_tamper_overwrite_and_manifest_forgery(
    tmp_path: Path,
) -> None:
    factor = _identity_factor()
    bundle = create_canonical_sparse_lu_binary_artifact_bundle(
        factor,
        artifact_uri_prefix="artifact://case/factor",
    )
    output = tmp_path / "factor"
    write_canonical_sparse_lu_binary_artifacts(bundle, output)

    tampered = bytearray((output / "upper_numeric_values.f64le").read_bytes())
    tampered[-1] ^= 1
    with pytest.raises(CanonicalSparseLUError, match="hash mismatch"):
        validate_canonical_sparse_lu_binary_artifact_bytes(
            bundle,
            name="upper_numeric_values",
            data=tampered,
        )
    with pytest.raises(CanonicalSparseLUError, match="refusing to overwrite"):
        write_canonical_sparse_lu_binary_artifacts(bundle, output)

    stale = deepcopy(bundle.to_manifest())
    stale["artifacts"][0]["artifact_uri"] = "artifact://wrong/file.bin"
    with pytest.raises(CanonicalSparseLUError, match="descriptor"):
        validate_canonical_sparse_lu_binary_artifact_manifest(stale)


def test_factor_validator_rejects_stale_contract_hash() -> None:
    factor = _identity_factor()

    with pytest.raises(CanonicalSparseLUError, match="contract hash is stale"):
        validate_canonical_sparse_lu_factor(
            replace(factor, contract_hash="sha256:" + "9" * 64)
        )
