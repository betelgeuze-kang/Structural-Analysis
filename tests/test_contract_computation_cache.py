from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import runpy

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts._canonical import (
    CanonicalContractError,
    canonical_hash,
)
from structural_analysis.engine_v2.contracts._computation_cache import (
    canonical_hash_cached,
    reuse_contract_computations,
)
from structural_analysis.engine_v2.contracts import _computation_cache as cache
from structural_analysis.engine_v2.contracts import equation_scaling as scaling_module
from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.materials.stateful_fiber_section import (
    make_rectangular_stateful_rc_fiber_section,
)


@pytest.mark.parametrize(
    "value",
    [
        None,
        True,
        1,
        1.0,
        -0.0,
        0.0,
        "한글",
        [1, True, 1.0],
        {"nested": (1.0, {"value": False})},
        np.array([1.0, 2.0]),
    ],
)
def test_cached_digest_preserves_the_original_serialization(value):
    assert canonical_hash_cached(value) == canonical_hash(value)
    assert canonical_hash_cached(value) == canonical_hash(value)


def test_hash_keys_distinguish_equal_python_numeric_types_and_current_mutations():
    assert len({canonical_hash_cached({"v": v}) for v in (True, 1, 1.0)}) == 3
    value = {"nested": [{"v": 1}]}
    old = canonical_hash_cached(value)
    value["nested"][0]["v"] = 2
    assert canonical_hash_cached(value) == canonical_hash(value) != old


@pytest.mark.parametrize("value", [float("nan"), float("inf"), {False: "bad key"}])
def test_invalid_values_retain_original_rejection(value):
    with pytest.raises(CanonicalContractError):
        canonical_hash_cached(value)


def test_large_and_custom_inputs_use_original_digest_semantics():
    class MappingSubclass(dict):
        pass

    for value in (MappingSubclass(v=1), {"v": "x" * 65537}, list(range(2200))):
        assert canonical_hash_cached(value) == canonical_hash(value)


@pytest.mark.parametrize(
    "initial,expected_remaining,succeeds",
    [
        ([3, 1], [0, 0], True),
        ([2, 1], [-1, 0], False),
        ([1, 0], [-1, 0], False),
        ([2, 0], [0, -1], False),
        ([0, 9], [-1, 9], False),
    ],
)
def test_dictionary_key_admission_retains_budget_and_failure_order(
    initial, expected_remaining, succeeds
):
    remaining = initial.copy()
    if succeeds:
        assert cache._snapshot({"a": None}, remaining) == (
            dict,
            (("a", (type(None), None)),),
        )
    else:
        with pytest.raises(cache._Uncacheable):
            cache._snapshot({"a": None}, remaining)
    assert remaining == expected_remaining


def test_nested_snapshot_retains_type_tags_signed_zero_and_character_budget():
    remaining = [12, 4]
    assert cache._snapshot(
        {"a": [True, 1, 1.0, -0.0, 0.0], "b": (None, "한글")}, remaining
    ) == (
        dict,
        (
            (
                "a",
                (
                    list,
                    (
                        (bool, True),
                        (int, 1),
                        (float, "0x1.0000000000000p+0"),
                        (float, "-0x0.0p+0"),
                        (float, "0x0.0p+0"),
                    ),
                ),
            ),
            ("b", (tuple, ((type(None), None), (str, "한글")))),
        ),
    )
    assert remaining == [0, 0]


def test_complete_dictionary_key_precheck_does_not_invoke_foreign_key_hooks():
    observations = []

    class ForeignKey(str):
        def __hash__(self):
            observations.append("hash")
            return str.__hash__(self)

        def __len__(self):
            observations.append("len")
            raise AssertionError("foreign key was inspected")

        def __str__(self):
            observations.append("str")
            raise AssertionError("foreign key was converted")

    payload = {"plain": object(), ForeignKey("foreign"): None}
    observations.clear()  # Dictionary construction itself hashes its keys.
    remaining = [20, 30]
    with pytest.raises(cache._Uncacheable):
        cache._snapshot(payload, remaining)
    assert remaining == [19, 30]
    assert observations == []


@pytest.mark.parametrize(
    "payload,cacheable",
    [
        ({"x" * 65536: None}, True),
        ({"x" * 65537: None}, False),
        ({"k": [None] * 2045}, True),
        ({"k": [None] * 2046}, False),
    ],
    ids=["exact-string-limit", "string-fallback", "exact-node-limit", "node-fallback"],
)
def test_dictionary_snapshot_limits_keep_original_public_digest(
    payload, cacheable, monkeypatch
):
    original_digest = cache._digest
    observed = []

    def digest(key):
        observed.append(key)
        return original_digest(key)

    monkeypatch.setattr(cache, "_digest", digest)
    assert canonical_hash_cached(payload) == canonical_hash(payload)
    assert len(observed) == int(cacheable)


def test_beam_contract_rechecks_current_section_and_declared_values():
    section = make_rectangular_stateful_rc_fiber_section()
    beam = StatefulFiberBeam2D(section)
    old = beam.contract_hash
    assert deepcopy(beam).contract_hash == old
    assert replace(beam, length_m=4.0).contract_hash != old
    object.__setattr__(section.steel, "yield_stress_mpa", 125.0)
    assert beam.contract_hash != old


def _scaling_fixture():
    return runpy.run_path(
        str(Path(__file__).with_name("test_engine_v2_equation_scaling_v1.py"))
    )["_scaling"]()


def test_scoped_schema_reuse_never_reuses_semantic_array_commitments(monkeypatch):
    scaling = _scaling_fixture()
    payload = scaling_module._scaling_payload(scaling, include_scaling_hash=True)
    with reuse_contract_computations():
        scaling_module.validate_equation_scaling_manifest(payload)
        scaling_module.validate_equation_scaling_manifest(payload)
        monkeypatch.setattr(
            scaling_module, "array_data_hash", lambda _: "sha256:" + "0" * 64
        )
        with pytest.raises(
            scaling_module.EquationScalingError, match="Raw vector hash is stale"
        ):
            scaling_module.validate_equation_scaling_manifest(payload)


def test_warm_schema_scope_rejects_changed_manifest_and_live_mutable_array():
    scaling = _scaling_fixture()
    payload = scaling_module._scaling_payload(scaling, include_scaling_hash=True)
    with reuse_contract_computations():
        scaling_module.validate_equation_scaling_manifest(payload)
        changed = deepcopy(payload)
        changed["dof_count"] = True
        with pytest.raises(scaling_module.EquationScalingError):
            scaling_module.validate_equation_scaling_manifest(changed)
        changed = deepcopy(payload)
        changed["scale_vector"]["values"][0] *= 2
        with pytest.raises(scaling_module.EquationScalingError):
            scaling_module.validate_equation_scaling_manifest(changed)
        mutable = np.array(scaling._scale_divisors_si, copy=True)
        mutable.setflags(write=False)
        with pytest.raises(scaling_module.EquationScalingError):
            scaling_module.validate_equation_scaling(
                replace(scaling, _scale_divisors_si=mutable)
            )
