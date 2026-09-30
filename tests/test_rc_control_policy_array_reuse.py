"""Exact numeric-policy reuse; dynamic solver inputs and authority are unchanged."""

from copy import deepcopy
from dataclasses import replace
import json

import numpy as np
import pytest

from tests.test_rc_control_learning import cases, polished_cases  # noqa: F401
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_history_features import (
    HISTORY_FEATURE_PROFILE,
    control_history_features,
)
from structural_analysis.benchmark.rc_control_material_features import (
    MATERIAL_FEATURE_PROFILE,
    material_control_features,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    RCControlSeedContext,
    benchmark_rc_control_seed_paths,
    secant_seed,
)


ARRAY_NAMES = (
    "feature_min",
    "feature_max",
    "feature_mean",
    "feature_scale",
    "weights",
    "target_scale",
)


def uncached_arrays(encoded):
    payload = json.loads(encoded)
    return {name: np.asarray(payload[name]) for name in ARRAY_NAMES}


@pytest.mark.parametrize("mixed", [False, True])
def test_numeric_storage_preserves_dtype_shape_bytes_and_isolates_all_views(mixed):
    value = 1.5 if mixed else 2
    payload = {name: [0, value, 3] for name in ARRAY_NAMES}
    payload["weights"] = [[0, value], [2, 3], [4, 5]]
    encoded = json.dumps(payload)
    learning._inference_policy_numeric_storage.cache_clear()
    storage = learning._inference_policy_numeric_storage(encoded)
    views = learning._inference_policy_arrays(encoded)
    with pytest.raises(TypeError):
        storage["weights"] = ()
    for name, original in uncached_arrays(encoded).items():
        data, dtype, shape = storage[name]
        assert type(data) is bytes and type(shape) is tuple
        assert dtype == original.dtype.str and shape == original.shape
        assert data == original.tobytes(order="C")
        view = views[name]
        assert view.dtype == original.dtype and view.shape == original.shape
        assert view.flags.c_contiguous and not view.flags.writeable
        assert view.tobytes(order="C") == original.tobytes(order="C")
        with pytest.raises(ValueError):
            view.flat[0] = 123
        with pytest.raises(ValueError):
            view.setflags(write=True)
        view.shape = (view.size,)
        view.dtype = np.uint8
        # NumPy exposes the uncached base view as well; its metadata is local too.
        assert isinstance(view.base, np.ndarray)
        view.base.shape = (view.base.size,)
        view.base.dtype = np.uint8
        with pytest.raises(ValueError):
            view.base.setflags(write=True)
        fresh = learning._inference_policy_arrays(encoded)[name]
        assert fresh is not view
        assert fresh.dtype == original.dtype and fresh.shape == original.shape
        assert fresh.tobytes(order="C") == original.tobytes(order="C")
    views.clear()
    assert set(learning._inference_policy_arrays(encoded)) == set(ARRAY_NAMES)
    learning._inference_policy_numeric_storage.cache_clear()


def test_numeric_storage_is_exact_content_keyed_and_bounded():
    learning._inference_policy_numeric_storage.cache_clear()
    payload = {name: [1] for name in ARRAY_NAMES}
    payload["weights"] = [[1]]
    encoded = json.dumps(payload)
    first = learning._inference_policy_numeric_storage(encoded)
    assert learning._inference_policy_numeric_storage(encoded) is first
    # Equal parsed values with different original bytes have distinct identities.
    spaced = json.dumps(payload, indent=2)
    assert learning._inference_policy_numeric_storage(spaced) is not first
    changed = deepcopy(payload)
    changed["weights"][0][0] = 2
    second = learning._inference_policy_numeric_storage(json.dumps(changed))
    assert second["weights"][0] != first["weights"][0]
    for value in range(8):
        changed["weights"][0][0] = value
        learning._inference_policy_numeric_storage(json.dumps(changed))
    info = learning._inference_policy_numeric_storage.cache_info()
    assert info.maxsize == 4 and info.currsize == 4
    learning._inference_policy_numeric_storage.cache_clear()


@pytest.fixture(
    params=[
        (profile, arithmetic)
        for profile in (None, HISTORY_FEATURE_PROFILE, MATERIAL_FEATURE_PROFILE)
        for arithmetic in ("binary64", learning.RETAINED_LEARNING_ARITHMETIC_PROFILE)
    ]
)
def actual_policy_inputs(tmp_path, request):
    profile, arithmetic = request.param
    roster = request.getfixturevalue("cases")
    selected = polished_cases(roster) if arithmetic != "binary64" else roster
    folder = tmp_path / "labels"
    report = learning.run_rc_control_learning_study(
        selected,
        source_revision="a" * 40,
        output_directory=folder,
        arithmetic_profile=arithmetic,
        fit_solver=learning.SVD_RIDGE_FIT_PROFILE,
        ood_margin=1.0,
        defer_evaluation=True,
        **({"feature_profile": profile} if profile is not None else {}),
    )
    assert report["evaluation_deferred"] is True
    assert report["evaluation_work"]["known_work"]["core_calls"] == 0
    samples = json.loads((folder / "training-samples.json").read_bytes())
    sample = next(row for row in samples if row["case_id"] == "train-a")
    policy = learning.RCControlSeedPolicy(learning._bytes(report["policy"]).decode())
    _, compiled, features, _, _ = learning._preflight(selected, arithmetic)["train-a"]
    context = RCControlSeedContext(**sample["context"])
    return selected[0], compiled, features, context, policy, profile, arithmetic


def original_expression(policy, context, features, profile, coordinate_scale):
    payload = policy.to_dict()
    scales = 1.0
    if profile == MATERIAL_FEATURE_PROFILE:
        x, _ = material_control_features(context, features)
    elif profile == HISTORY_FEATURE_PROFILE:
        x, scales = control_history_features(context, features, coordinate_scale)
    else:
        x = learning._features(context, features)
    # Preserve the uncached arithmetic expression independently of cached views.
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        z = (x - payload["feature_mean"]) / payload["feature_scale"]
        value = (
            np.asarray(secant_seed(context))
            + (np.append(z, 1.0) @ np.asarray(payload["weights"]))
            * payload["target_scale"]
            * scales
        )
        value[context.control_free_index] = context.target_m
    return tuple(float(item) for item in value)


def test_actual_policy_reuse_preserves_seeds_guards_and_complete_paths(
    tmp_path, actual_policy_inputs, monkeypatch
):
    case, compiled, features, context, policy, profile, arithmetic = (
        actual_policy_inputs
    )
    encoded = policy._json
    frozen = learning._bytes(policy.to_dict())
    options = {
        "arithmetic_profile": arithmetic,
        "load_factor_coordinate_scale_m": case.request.solver_config.load_factor_coordinate_scale_m,
    }
    args = (
        features,
        compiled.problem.free_global_dofs,
        case.request.solver_config.contract_hash,
    )
    learning._inference_policy_numeric_storage.cache_clear()

    def forbidden(*args, **kwargs):
        pytest.fail("numeric preparation ran before an existing abstention guard")

    short = replace(
        context,
        accepted_targets_m=context.accepted_targets_m[:1],
        accepted_augmented_coordinates_m=context.accepted_augmented_coordinates_m[:1],
    )
    with monkeypatch.context() as patcher:
        patcher.setattr(learning, "_inference_policy_arrays", forbidden)
        assert policy.propose(short, *args, **options) is None
        assert (
            policy.propose(context, *args[:-1], "sha256:" + "f" * 64, **options) is None
        )
        wrong = dict(
            options,
            arithmetic_profile=(
                "binary64"
                if arithmetic != "binary64"
                else learning.RETAINED_LEARNING_ARITHMETIC_PROFILE
            ),
        )
        assert policy.propose(context, *args, **wrong) is None
        if profile == MATERIAL_FEATURE_PROFILE:
            assert (
                policy.propose(
                    replace(context, committed_material_state_json=None),
                    *args,
                    **options,
                )
                is None
            )
        if profile == HISTORY_FEATURE_PROFILE:
            assert (
                policy.propose(
                    context, *args, **dict(options, load_factor_coordinate_scale_m=0.25)
                )
                is None
            )
    assert learning._inference_policy_numeric_storage.cache_info().currsize == 0

    payload = learning._inference_policy_payload(encoded)
    identities = {id(payload[name]): name for name in ARRAY_NAMES}
    actual_asarray = np.asarray
    conversions = []

    def observed_asarray(value, *args, **kwargs):
        if id(value) in identities:
            conversions.append(identities[id(value)])
        return actual_asarray(value, *args, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(learning.np, "asarray", observed_asarray)
        first = policy.propose(context, *args, **options)
        assert first is not None
        assert sorted(conversions) == sorted(ARRAY_NAMES)
        for _ in range(3):
            repeated = policy.propose(context, *args, **options)
            assert np.asarray(repeated).tobytes() == np.asarray(first).tobytes()
        assert len(conversions) == len(ARRAY_NAMES)
    expected = original_expression(
        policy, context, features, profile, options["load_factor_coordinate_scale_m"]
    )
    assert np.asarray(first).tobytes() == np.asarray(expected).tobytes()
    assert policy.propose(replace(context, target_m=1e3), *args, **options) is None
    detached = policy.to_dict()
    detached["weights"][0][0] += 123
    assert learning._bytes(policy.to_dict()) == frozen
    assert (
        np.asarray(policy.propose(context, *args, **options)).tobytes()
        == np.asarray(first).tobytes()
    )

    # A cache hit cannot replace the public constructor's strict parse/validation.
    strict_decode = learning.strict_json_object_bytes
    strict_calls = []

    def observed_strict_decode(value, **kwargs):
        strict_calls.append(value)
        return strict_decode(value, **kwargs)

    with monkeypatch.context() as patcher:
        patcher.setattr(learning, "strict_json_object_bytes", observed_strict_decode)
        reconstructed = learning.RCControlSeedPolicy(encoded)
    assert strict_calls[0] == encoded.encode()
    assert learning._bytes(reconstructed.to_dict()) == frozen

    for mixed in (False, True):
        typed = policy.to_dict()
        width = len(typed["feature_mean"])
        count = len(typed["target_scale"])
        typed.update(
            feature_min=[-(10**12)] * width,
            feature_max=[10**12] * width,
            feature_mean=[0] * width,
            feature_scale=[1] * width,
            target_scale=[1] * count,
            weights=[[0] * count for _ in range(width + 1)],
        )
        typed["weights"][-1][0] = 1
        if mixed:
            typed["feature_mean"][0] = 0.5
            typed["weights"][0][0] = 0.25
            typed["target_scale"][0] = 1.5
        typed.pop("policy_hash")
        typed["policy_hash"] = learning._sha(learning._bytes(typed))
        typed_policy = learning.RCControlSeedPolicy(learning._bytes(typed).decode())
        observed = typed_policy.propose(context, *args, **options)
        expected_typed = original_expression(
            typed_policy,
            context,
            features,
            profile,
            options["load_factor_coordinate_scale_m"],
        )
        assert np.asarray(observed).tobytes() == np.asarray(expected_typed).tobytes()
        for name, original in uncached_arrays(typed_policy._json).items():
            reused = learning._inference_policy_arrays(typed_policy._json)[name]
            assert reused.dtype == original.dtype
            assert reused.shape == original.shape
            assert reused.tobytes() == original.tobytes()

    for name, replacement in (
        ("weights", [[True]]),
        ("feature_mean", [float("nan")]),
        ("target_scale", [0]),
        ("feature_max", []),
    ):
        malformed = policy.to_dict()
        malformed[name] = replacement
        malformed.pop("policy_hash")
        malformed["policy_hash"] = (
            learning._sha(learning._bytes(malformed))
            if name != "feature_mean"
            else policy.policy_hash
        )
        raw = json.dumps(malformed)
        with pytest.raises(ValueError):
            learning.RCControlSeedPolicy(raw)
    duplicate = encoded.replace('"ridge":', '"ridge":123,"ridge":', 1)
    with pytest.raises(ValueError):
        learning.RCControlSeedPolicy(duplicate)

    def propose(value):
        return policy.propose(value, *args, **options)

    results = {}
    for cached in (False, True):
        with monkeypatch.context() as patcher:
            if not cached:
                patcher.setattr(learning, "_inference_policy_arrays", uncached_arrays)
            results[cached] = benchmark_rc_control_seed_paths(
                case.model,
                case.request,
                source_revision="a" * 40,
                output_directory=tmp_path / ("cached" if cached else "uncached"),
                proposal=propose,
                proposal_identity=policy.policy_hash,
                proposal_abstention_strategy="secant",
                capture_material_state=profile == MATERIAL_FEATURE_PROFILE,
                material_capture_scope="proposal-only"
                if profile == MATERIAL_FEATURE_PROFILE
                else "all-arms",
                **learning._arithmetic_kwargs(arithmetic),
            )
        assert results[cached]["reference_repeat_exact"]
        assert results[cached]["all_execution_work_reported"]
        assert all(
            row["full_history_pass"] for row in results[cached]["comparisons"].values()
        )
        assert learning._bytes(policy.to_dict()) == frozen
    originals = sorted((tmp_path / "uncached").glob("*/*-context.json"))
    originals += sorted((tmp_path / "uncached").glob("*/*-step.json"))
    assert len(originals) == 48
    for original in originals:
        relative = original.relative_to(tmp_path / "uncached")
        assert (tmp_path / "cached" / relative).read_bytes() == original.read_bytes()
    learning._inference_policy_numeric_storage.cache_clear()
