"""Exact-byte equivalence and extension behavior for plain normalization."""

from collections.abc import Mapping
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts import _canonical as canonical


def legacy_bytes(payload):
    normalized = canonical._NORMALIZER_REFERENCE(payload, path="/")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        True,
        False,
        0,
        -(10**200),
        '한글/é/\n/"/\\/\u0000',
        -0.0,
        0.0,
        sys.float_info.max,
        math.nextafter(0.0, 1.0),
        [],
        {},
        (),
        {"z": [None, True, 7, -0.0], "a": ({"é": 1.25}, [], ())},
        [{"b": {"x": (1, False)}, "a": [[], {}]}, (0.25, -3)],
    ],
)
def test_plain_bytes_and_prefixed_hash_equal_the_original(payload):
    expected = legacy_bytes(payload)
    assert canonical.canonical_json_bytes(payload) == expected
    assert (
        canonical.canonical_hash(payload)
        == "sha256:" + hashlib.sha256(expected).hexdigest()
    )


def test_plain_containers_are_fresh_sorted_and_observe_later_input_edits():
    shared = [{"z": -0.0, "a": [1]}]
    payload = {"z": shared, "a": [shared, (shared,)]}
    expected = legacy_bytes(payload)
    normalized = canonical._normalize_plain_json_value(payload, 0)
    assert list(normalized) == ["a", "z"]
    assert normalized == canonical._NORMALIZER_REFERENCE(payload, path="/")
    assert normalized is not payload and normalized["z"] is not shared
    assert normalized["a"][0] is not normalized["z"]
    assert normalized["a"][1][0] is not normalized["a"][0]
    assert normalized["z"][0]["a"] is not shared[0]["a"]
    assert math.copysign(1.0, normalized["z"][0]["z"]) == 1.0
    assert canonical.canonical_json_bytes(payload) == expected
    shared[0]["a"].append(2)
    assert normalized["z"][0]["a"] == [1]
    assert canonical.canonical_json_bytes(payload) == legacy_bytes(payload) != expected


def test_independently_rebuilt_payloads_and_order_permutations_are_equivalent():
    rows = [{"b": [index, -0.0], "a": (None, True)} for index in range(64)]
    first = {"rows": rows, "empty": {}}
    fresh = {
        "empty": {},
        "rows": [{"a": (None, True), "b": [i, 0.0]} for i in range(64)],
    }
    assert first is not fresh and first["rows"] is not fresh["rows"]
    assert canonical.canonical_json_bytes(first) == legacy_bytes(fresh)
    assert canonical.canonical_hash(first) == canonical.canonical_hash(fresh)


class IntegerSubclass(int):
    def __int__(self):
        return 91


class FloatSubclass(float):
    def __float__(self):
        return 2.5


class StringSubclass(str):
    pass


@pytest.mark.parametrize(
    "payload",
    [
        np.int64(12),
        np.float32(-0.0),
        np.bool_(True),
        np.array([[1.0, -0.0], [2.5, 3.0]]),
        np.array([np.int64(4), {"a": [True]}], dtype=object),
        {"a": IntegerSubclass(7), "b": FloatSubclass(8.0)},
        {StringSubclass("a"): StringSubclass("value")},
    ],
)
def test_supported_nonplain_extensions_use_original_normalization(payload):
    assert canonical.canonical_json_bytes(payload) == legacy_bytes(payload)


class ObservedMapping(Mapping):
    def __init__(self, events):
        self.events = events
        self.values = {"z": [np.int64(2)], "a": {"x": -0.0}}

    def __iter__(self):
        self.events.append("iter")
        return iter(self.values)

    def __len__(self):
        self.events.append("len")
        return len(self.values)

    def __getitem__(self, key):
        self.events.append(("get", key))
        return self.values[key]


class ObservedDict(dict):
    def __init__(self, events):
        super().__init__({"z": 3, "a": [np.float64(4.0)]})
        self.events = events

    def __iter__(self):
        self.events.append("iter")
        return super().__iter__()

    def __getitem__(self, key):
        self.events.append(("get", key))
        return super().__getitem__(key)


@pytest.mark.parametrize("extension", [ObservedMapping, ObservedDict])
def test_custom_access_order_is_not_duplicated_before_full_fallback(extension):
    expected_events = []
    actual_events = []
    expected = legacy_bytes({"z": [1, 2], "a": extension(expected_events)})
    actual = canonical.canonical_json_bytes(
        {"z": [1, 2], "a": extension(actual_events)}
    )
    assert actual == expected and actual_events == expected_events


@pytest.mark.parametrize("base", [list, tuple])
def test_sequence_subclass_iteration_behavior_is_not_bypassed(base):
    events = []

    class ObservedSequence(base):
        def __iter__(self):
            events.append("iter")
            return iter([np.int64(5), {"zero": -0.0}])

    payload = {"sequence": ObservedSequence([1, 2, 3])}
    expected = legacy_bytes(payload)
    expected_events = events.copy()
    events.clear()
    assert canonical.canonical_json_bytes(payload) == expected
    assert events == expected_events == ["iter"]


def exception_signature(call):
    with pytest.raises(Exception) as caught:
        call()
    error = caught.value
    return (
        type(error),
        str(error),
        type(error.__context__),
        type(error.__cause__),
        error.__suppress_context__,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"outer": [0, float("nan")]},
        {"outer": (float("inf"),)},
        {"outer": [float("-inf")]},
        {"z": object(), "a": {"b": float("nan")}},
        {"z": {1: "bad key"}, "a": object()},
        {"outer": {1: float("nan"), "a": 1}},
        {"outer": Path("relative-only")},
        {"outer": np.array([float("nan")])},
        {"outer": np.array([object()], dtype=object)},
        {"outer": complex(1, 2)},
    ],
)
def test_original_exception_class_text_and_context_are_preserved(payload):
    assert exception_signature(
        lambda: canonical.canonical_json_bytes(payload)
    ) == exception_signature(lambda: legacy_bytes(payload))


def nested_payload(depth):
    result = {"leaf": -0.0}
    for index in range(depth):
        result = [result] if index % 2 else {"child": result}
    return result


@pytest.mark.parametrize("depth", [62, 63, 64, 65, 90])
def test_depth_bound_does_not_change_valid_deep_input(depth):
    payload = nested_payload(depth)
    assert canonical.canonical_json_bytes(payload) == legacy_bytes(payload)


@pytest.mark.parametrize("container", [list, dict])
def test_cycles_keep_the_original_root_fallback_error(monkeypatch, container):
    payload = container()
    if container is list:
        payload.append(payload)
    else:
        payload["self"] = payload
    actual = exception_signature(lambda: canonical.canonical_json_bytes(payload))

    def force_reference(value, depth):
        raise canonical._PlainNormalizationFallback

    monkeypatch.setattr(canonical, "_normalize_plain_json_value", force_reference)
    assert actual == exception_signature(
        lambda: canonical.canonical_json_bytes(payload)
    )
    assert actual[0] is RecursionError and actual[2] is type(None)


def test_rebound_original_normalizer_remains_authoritative(monkeypatch):
    def replacement(value, *, path):
        return {"rebound": value, "path": path}

    monkeypatch.setattr(canonical, "_normalize_json_value", replacement)
    assert canonical.canonical_json_bytes(7) == b'{"path":"/","rebound":7}'


def test_original_normalizer_code_change_remains_authoritative(monkeypatch):
    def replacement(value, *, path):
        return {"new_code": path}

    monkeypatch.setattr(
        canonical._NORMALIZER_REFERENCE, "__code__", replacement.__code__
    )
    assert canonical.canonical_json_bytes([1, 2]) == b'{"new_code":"/"}'


def test_rebound_finite_predicate_runs_once_in_original_order(monkeypatch):
    calls = []
    original = math.isfinite

    def replacement(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(canonical.math, "isfinite", replacement)
    signature = exception_signature(
        lambda: canonical.canonical_json_bytes({"z": 1.0, "a": float("inf")})
    )
    assert signature[0] is canonical.CanonicalContractError
    assert calls == [float("inf")]


def test_large_integer_encoder_rejection_is_unchanged():
    if not hasattr(sys, "get_int_max_str_digits") or sys.get_int_max_str_digits() == 0:
        pytest.skip("interpreter integer string limit is disabled")
    payload = 10 ** (sys.get_int_max_str_digits() + 1)
    assert exception_signature(
        lambda: canonical.canonical_json_bytes(payload)
    ) == exception_signature(lambda: legacy_bytes(payload))
