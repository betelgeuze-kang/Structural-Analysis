from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    CanonicalContractError,
    array_content_hash,
    array_data_hash,
    canonical_hash,
    canonical_json_bytes,
    has_immutable_bytes_backing,
    immutable_array,
)


def test_canonical_json_is_order_independent_utf8_and_normalizes_signed_zero() -> None:
    first = {"한글": [1, -0.0], "a": {"z": 2, "b": True}}
    second = {"a": {"b": True, "z": 2}, "한글": [1, 0.0]}

    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_hash(first) == canonical_hash(second)
    assert canonical_json_bytes(first).decode("utf-8") == (
        '{"a":{"b":true,"z":2},"한글":[1,0.0]}'
    )


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_canonical_json_and_arrays_reject_nonfinite_values(value: float) -> None:
    with pytest.raises(CanonicalContractError):
        canonical_json_bytes({"value": value})
    with pytest.raises(CanonicalContractError):
        immutable_array([value], dtype="<f8")


def test_canonical_arrays_are_little_endian_bytes_backed_and_zero_stable() -> None:
    positive = immutable_array([0.0, 1.0, 2.0], dtype="<f8")
    negative = immutable_array([-0.0, 1.0, 2.0], dtype=">f8")

    assert positive.dtype.str == negative.dtype.str == "<f8"
    assert positive.flags.c_contiguous and not positive.flags.writeable
    assert has_immutable_bytes_backing(positive)
    assert array_data_hash(positive) == array_data_hash(negative)
    assert array_content_hash(
        {"name": "values", "dtype": "<f8", "shape": [3]}, positive
    ) == array_content_hash({"shape": [3], "dtype": "<f8", "name": "values"}, negative)
    with pytest.raises(ValueError):
        positive.setflags(write=True)


def test_empty_canonical_array_hashes_are_stable() -> None:
    first = immutable_array(np.empty((0, 12), dtype=np.int64), dtype="<i8")
    second = immutable_array(np.empty((0, 12), dtype=">i8"), dtype="<i8")
    metadata = {"name": "empty", "dtype": "<i8", "shape": [0, 12]}

    assert array_data_hash(first) == array_data_hash(second)
    assert array_content_hash(metadata, first) == array_content_hash(
        metadata,
        second,
    )


def test_object_arrays_and_non_string_mapping_keys_fail_closed() -> None:
    with pytest.raises(CanonicalContractError):
        immutable_array([object()], dtype=object)
    with pytest.raises(CanonicalContractError):
        canonical_hash({1: "not-a-json-object-key"})


@pytest.mark.parametrize(
    ("value", "dtype"),
    [
        ([1.5], "<i4"),
        ([True], "<i4"),
        ([1], "<?"),
        ([2**31], "<i4"),
        ([-1], "<u4"),
        ([2**53 + 1], "<f8"),
        ([1.1], "<f4"),
        ([1.0 + 2.0j], "<f8"),
        (["1"], "<i4"),
    ],
)
def test_canonical_array_conversion_rejects_kind_changes_and_value_loss(
    value, dtype: str
) -> None:
    with pytest.raises(CanonicalContractError):
        immutable_array(value, dtype=dtype)


def test_canonical_array_conversion_allows_lossless_width_and_endian_changes() -> None:
    integers = immutable_array(
        np.asarray([1, 2, 3], dtype=">i8"),
        dtype="<i4",
    )
    floating = immutable_array(
        np.asarray([1.5, -2.25], dtype="<f4"),
        dtype="<f8",
    )

    assert integers.dtype.str == "<i4"
    assert floating.dtype.str == "<f8"
    np.testing.assert_array_equal(integers, [1, 2, 3])
    np.testing.assert_array_equal(floating, [1.5, -2.25])


def test_complex_array_hash_normalizes_signed_zero_in_each_component() -> None:
    positive = immutable_array(
        [complex(1.0, 0.0), complex(0.0, 2.0)],
        dtype="<c16",
    )
    negative = immutable_array(
        [complex(1.0, -0.0), complex(-0.0, 2.0)],
        dtype=">c16",
    )

    assert array_data_hash(positive) == array_data_hash(negative)
    assert not np.any(np.signbit(negative.real[negative.real == 0]))
    assert not np.any(np.signbit(negative.imag[negative.imag == 0]))


def test_canonical_json_and_array_hashes_reproduce_across_processes() -> None:
    script = """
import numpy as np
from structural_analysis.engine_v2.contracts._canonical import (
    array_data_hash,
    canonical_hash,
    immutable_array,
)
print(canonical_hash({"z": [3, -0.0], "a": {"한글": True}}))
print(array_data_hash(immutable_array([0.0, 1.5, -2.0], dtype="<f8")))
"""
    outputs = []
    for seed in ("1", "8675309"):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(SRC_ROOT), "PYTHONHASHSEED": seed},
        )
        outputs.append(completed.stdout)

    assert outputs[0] == outputs[1]
