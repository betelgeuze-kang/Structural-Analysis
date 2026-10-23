"""Descriptor-only byte reuse; array data and validation remain live."""

from copy import deepcopy
import gc
import hashlib
import json
import weakref

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import _canonical as module


def descriptor(**changes):
    return {
        "name": "values",
        "dtype": "<f8",
        "shape": [2],
        "layout": "C",
        "byte_length": 16,
        **changes,
    }


def uncached(metadata, array):
    return (
        "sha256:"
        + hashlib.sha256(
            module.canonical_json_bytes(metadata) + b"\0" + array.tobytes(order="C")
        ).hexdigest()
    )


@pytest.fixture(autouse=True)
def clear_cache():
    module._cached_array_metadata_bytes.cache_clear()
    yield
    module._cached_array_metadata_bytes.cache_clear()


def test_equal_fresh_descriptor_values_share_bytes_without_retaining_input():
    first = descriptor()
    expected = module.canonical_json_bytes(first)
    assert module._array_metadata_bytes(first) == expected
    second = {key: deepcopy(value) for key, value in reversed(tuple(first.items()))}
    second["shape"] = (2,)
    assert module._array_metadata_bytes(second) == expected
    info = module._cached_array_metadata_bytes.cache_info()
    assert (info.misses, info.hits, info.currsize, info.maxsize) == (1, 1, 1, 128)
    first["shape"][0] = 3
    assert (
        module._array_metadata_bytes(first)
        == module.canonical_json_bytes(first)
        != expected
    )
    assert module._array_metadata_bytes(descriptor()) == expected


@pytest.mark.parametrize(
    "name,value",
    [
        ("name", "other"),
        ("dtype", "<i8"),
        ("shape", [1, 2]),
        ("layout", "F"),
        ("byte_length", 24),
        ("state_hash", "sha256:changed"),
        ("equation_order_hash", "sha256:order"),
    ],
)
def test_every_current_descriptor_field_changes_the_value_key(name, value):
    before = module._array_metadata_bytes(descriptor())
    metadata = descriptor(**{name: value})
    assert (
        module._array_metadata_bytes(metadata)
        == module.canonical_json_bytes(metadata)
        != before
    )


@pytest.mark.parametrize("value", [True, 2.0, np.int64(2)])
def test_nonexact_shape_types_use_uncached_canonical_semantics(value):
    metadata = descriptor(shape=[value])
    assert module._array_metadata_bytes(metadata) == module.canonical_json_bytes(
        metadata
    )
    assert module._cached_array_metadata_bytes.cache_info().currsize == 0


@pytest.mark.parametrize(
    "metadata",
    [
        descriptor(byte_length=True),
        descriptor(byte_length=16.0),
        descriptor(byte_length=2**100),
        descriptor(shape=list(range(33))),
        descriptor(name="x" * 4097),
        descriptor(extension={"custom": [1, -0.0]}),
        {"unknown": True},
    ],
)
def test_unusual_large_or_extension_metadata_uses_original_path(metadata):
    assert module._array_metadata_bytes(metadata) == module.canonical_json_bytes(
        metadata
    )
    assert module._cached_array_metadata_bytes.cache_info().currsize == 0


def test_mapping_subclass_preserves_custom_access_trace_without_speculative_reads():
    events = []

    class Custom(dict):
        def __getitem__(self, key):
            events.append(key)
            return super().__getitem__(key)

    metadata = Custom(descriptor())
    expected = module.canonical_json_bytes(metadata)
    expected_events = events[:]
    events.clear()
    assert module._array_metadata_bytes(metadata) == expected
    assert events == expected_events
    assert module._cached_array_metadata_bytes.cache_info().currsize == 0


def test_ineligible_metadata_does_not_run_the_serializer_cache_guard(monkeypatch):
    metadata = descriptor(extension={"keep": [True, 1, 1.0]})
    expected = module.canonical_json_bytes(metadata)

    def forbidden():
        raise AssertionError("ineligible metadata paid for the cache guard")

    monkeypatch.setattr(module, "_canonical_cache_eligible", forbidden)
    assert module._array_metadata_bytes(metadata) == expected


@pytest.mark.parametrize("value", [float("nan"), object(), {1: "bad-key"}])
def test_invalid_metadata_keeps_original_exception_type_text_and_context(value):
    metadata = descriptor(extension=value)
    with pytest.raises(module.CanonicalContractError) as expected:
        module.canonical_json_bytes(metadata)
    with pytest.raises(type(expected.value)) as actual:
        module._array_metadata_bytes(metadata)
    assert str(actual.value) == str(expected.value)
    assert actual.value.__context__ is expected.value.__context__ is None


def test_cycle_uses_original_recursion_error_without_internal_fallback_context():
    metadata = descriptor()
    metadata["extension"] = metadata
    with pytest.raises(RecursionError) as actual:
        module._array_metadata_bytes(metadata)
    assert actual.value.__context__ is None


@pytest.mark.parametrize(
    "change",
    [
        "normalizer",
        "normalizer_code",
        "dumps",
        "encoder",
        "encoder_code",
        "encoder_defaults",
    ],
)
def test_warm_bytes_do_not_hide_serializer_changes(monkeypatch, change):
    metadata = descriptor()
    before = module._array_metadata_bytes(metadata)
    if change == "normalizer":
        monkeypatch.setattr(
            module, "_normalize_json_value", lambda value, *, path: {"changed": True}
        )
    elif change == "normalizer_code":

        def replacement(value, *, path):
            return {"changed": True}

        monkeypatch.setattr(
            module._normalize_json_value, "__code__", replacement.__code__
        )
    elif change == "dumps":
        monkeypatch.setattr(json, "dumps", lambda *args, **kwargs: '"changed"')
    elif change in ("encoder", "encoder_code"):

        def replacement(self, value, _one_shot=False):
            return iter(('"changed"',))

        if change == "encoder":
            monkeypatch.setattr(json.JSONEncoder, "iterencode", replacement)
        else:
            monkeypatch.setattr(
                json.JSONEncoder.iterencode, "__code__", replacement.__code__
            )
    else:
        # An existing supported function's mutable keyword defaults are live.
        monkeypatch.setitem(json.dumps.__kwdefaults__, "indent", 2)
    assert not module._canonical_cache_eligible()
    current = module.canonical_json_bytes(metadata)
    assert module._array_metadata_bytes(metadata) == current != before
    assert module._cached_array_metadata_bytes.cache_info().hits == 0


def test_arrays_are_revalidated_and_actual_bytes_are_rehashed_on_every_call():
    metadata = descriptor()
    array = np.array([1.0, 2.0], dtype="<f8")
    first = module.array_content_hash(metadata, array)
    assert first == uncached(metadata, array)
    array[0] = 4.0
    assert (
        module.array_content_hash(metadata, array) == uncached(metadata, array) != first
    )
    with pytest.raises(module.CanonicalContractError, match="C-contiguous"):
        module.array_content_hash(metadata, np.arange(4.0)[::2])
    with pytest.raises(module.CanonicalContractError, match="Object arrays"):
        module.array_content_hash(metadata, np.array([object()], dtype=object))
    with pytest.raises(module.CanonicalContractError, match="Expected a NumPy array"):
        module.array_content_hash(metadata, [1, 2])
    reference = weakref.ref(array)
    del array
    gc.collect()
    assert reference() is None


def test_cache_is_bounded_and_descriptor_warming_does_not_change_stage1_guard():
    from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_terminal_receipt import (
        _AUDIT_IMPLEMENTATION,
    )

    assert _AUDIT_IMPLEMENTATION.unchanged()
    for index in range(140):
        metadata = descriptor(name=f"descriptor-{index}")
        assert module._array_metadata_bytes(metadata) == module.canonical_json_bytes(
            metadata
        )
    assert module._cached_array_metadata_bytes.cache_info().currsize == 128
    assert _AUDIT_IMPLEMENTATION.unchanged()
