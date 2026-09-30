"""Invocation-local recovery reuse keeps fresh before/after source authority."""

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import numpy as np
import pytest

from structural_analysis.assembly import (
    stateful_corotational_fiber_frame2d_engineering_recovery as recovery,
    stateful_corotational_fiber_frame2d_general as general,
    stateful_corotational_fiber_frame2d_j1_j5 as portal,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_solver import (
    run_stateful_corotational_fiber_frame2d_load_path,
)
from structural_analysis.engine_v2.contracts._canonical import (
    array_content_hash,
    array_data_hash,
    canonical_hash,
    immutable_array,
)
from structural_analysis.solvers.nonlinear.newton import (
    NewtonRaphsonConfig,
    VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
)
from tests.test_corotational_fiber_frame_general import _problem as _general_problem
from tests.test_corotational_fiber_frame_j1_j5 import _portal_problem


@pytest.fixture(scope="module", params=("portal", "general"))
def source_case(request):
    """Two small, two-target paths; all mutations reuse these accepted sources."""
    kind = request.param
    problem = _portal_problem() if kind == "portal" else _general_problem()
    module = portal if kind == "portal" else general
    compile_source = (
        portal.compile_corotational_fiber_frame_portal_profile
        if kind == "portal"
        else general.compile_corotational_fiber_frame_general_profile
    )
    create_adapter = (
        portal.create_corotational_fiber_frame_j1_j5_adapter
        if kind == "portal"
        else general.create_corotational_fiber_frame_general_j1_j5_adapter
    )
    validator_name = (
        "validate_corotational_fiber_frame_j1_j5_adapter"
        if kind == "portal"
        else "validate_corotational_fiber_frame_general_j1_j5_adapter"
    )
    compilation = compile_source(
        problem, model_content_hash=canonical_hash({"fixture": kind})
    )
    path = run_stateful_corotational_fiber_frame2d_load_path(
        problem,
        (0.5, 1.0),
        config=NewtonRaphsonConfig(
            residual_tolerance=1e-9,
            matrix_backend=VECTOR_EXTENDED_SPARSE_MATRIX_BACKEND,
        ),
    )
    assert path.contract_pass
    adapter = create_adapter(compilation, path)
    result = recovery.create_corotational_fiber_frame_engineering_result_ir(
        engineering_result_id=f"{kind}.invocation.reuse", source_adapter=adapter
    )
    return {
        "module": module,
        "validator_name": validator_name,
        "adapter": adapter,
        "result": result,
        "manifest": result.to_manifest(),
        "array_bytes": {
            name: array.tobytes() for name, array in result._arrays.items()
        },
        "checkpoint_bytes": tuple(
            checkpoint.canonical_bytes()
            for checkpoint in (
                path.initial_checkpoint,
                *(step.accepted_checkpoint for step in path.steps),
            )
        ),
    }


def _observe_real_boundaries(monkeypatch, source_case):
    events = []
    module = source_case["module"]
    validate = getattr(module, source_case["validator_name"])
    build_stages = module._build_stage_receipts
    assemble = recovery.assemble_stateful_corotational_fiber_frame2d_sparse_state

    def observed_validate(adapter):
        events.append("source")
        return validate(adapter)

    def observed_stages(*args, **kwargs):
        events.append("all-epoch-replay")
        return build_stages(*args, **kwargs)

    def observed_terminal(*args, **kwargs):
        events.append("terminal-recovery")
        return assemble(*args, **kwargs)

    monkeypatch.setattr(module, source_case["validator_name"], observed_validate)
    monkeypatch.setattr(module, "_build_stage_receipts", observed_stages)
    monkeypatch.setattr(
        recovery,
        "assemble_stateful_corotational_fiber_frame2d_sparse_state",
        observed_terminal,
    )
    return events


@pytest.mark.parametrize("entry", ("create", "validate", "manifest"))
def test_each_public_entry_keeps_fresh_source_boundaries_and_one_recovery(
    source_case, monkeypatch, entry
):
    events = _observe_real_boundaries(monkeypatch, source_case)
    original = source_case["result"]
    if entry == "create":
        actual = recovery.create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id=original.engineering_result_id,
            source_adapter=source_case["adapter"],
        )
    elif entry == "validate":
        actual = recovery.validate_corotational_fiber_frame_engineering_result_ir(
            original
        )
        assert actual is original
    else:
        assert original.to_manifest() == source_case["manifest"]
        actual = original
    assert events == [
        "source",
        "all-epoch-replay",
        "terminal-recovery",
        "source",
        "all-epoch-replay",
    ]
    assert actual.engineering_result_hash == original.engineering_result_hash
    assert actual.descriptors == original.descriptors
    assert actual.array_bundle_hash == original.array_bundle_hash
    assert actual._adapter is source_case["adapter"]
    assert {
        name: array.tobytes() for name, array in actual._arrays.items()
    } == source_case["array_bytes"]
    path = actual._adapter._path
    assert (
        tuple(
            checkpoint.canonical_bytes()
            for checkpoint in (
                path.initial_checkpoint,
                *(step.accepted_checkpoint for step in path.steps),
            )
        )
        == source_case["checkpoint_bytes"]
    )


def test_repeated_public_validation_does_not_cache_a_previous_success(
    source_case, monkeypatch
):
    events = _observe_real_boundaries(monkeypatch, source_case)
    for repeat in (1, 2):
        recovery.validate_corotational_fiber_frame_engineering_result_ir(
            source_case["result"]
        )
        assert events.count("source") == 2 * repeat
        assert events.count("all-epoch-replay") == 2 * repeat
        assert events.count("terminal-recovery") == repeat


def _source_with_live_early_metrics(adapter):
    path = adapter._path
    metrics = dict(path.steps[0].metrics)
    first = replace(path.steps[0], metrics=metrics)
    return replace(
        adapter, _path=replace(path, steps=(first, *path.steps[1:]))
    ), metrics


@pytest.mark.parametrize("shadow_method", (False, True))
def test_post_recovery_revalidates_early_epoch_even_with_shadowed_manifest(
    source_case, monkeypatch, shadow_method
):
    adapter, early_metrics = _source_with_live_early_metrics(source_case["adapter"])
    valid_manifest = type(adapter).to_manifest(adapter)
    if shadow_method:
        # A frozen dataclass can still be manipulated by hostile retained state.
        # The public class validator, rather than this forged callback, is required.
        object.__setattr__(adapter, "to_manifest", lambda: deepcopy(valid_manifest))
    assemble = recovery.assemble_stateful_corotational_fiber_frame2d_sparse_state
    calls = []

    def mutate_after_independent_terminal_replay(*args, **kwargs):
        assembled = assemble(*args, **kwargs)
        calls.append("terminal")
        early_metrics["target_load_factor"] += 0.125
        return assembled

    monkeypatch.setattr(
        recovery,
        "assemble_stateful_corotational_fiber_frame2d_sparse_state",
        mutate_after_independent_terminal_replay,
    )
    with pytest.raises(ValueError, match="exact solver state"):
        recovery.create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id="mutated.during.recovery", source_adapter=adapter
        )
    assert calls == ["terminal"]


@pytest.mark.parametrize("entry", ("create", "validate", "manifest"))
def test_later_public_entry_rejects_early_mutation_and_forged_manifest(
    source_case, monkeypatch, entry
):
    adapter, early_metrics = _source_with_live_early_metrics(source_case["adapter"])
    result = replace(source_case["result"], _adapter=adapter)
    recovery.validate_corotational_fiber_frame_engineering_result_ir(result)
    snapshot = type(adapter).to_manifest(adapter)
    early_metrics["target_load_factor"] += 0.125
    object.__setattr__(adapter, "to_manifest", lambda: deepcopy(snapshot))

    def forbidden_recovery(*args, **kwargs):
        pytest.fail("invalid early source must fail before terminal recovery")

    monkeypatch.setattr(
        recovery,
        "assemble_stateful_corotational_fiber_frame2d_sparse_state",
        forbidden_recovery,
    )
    with pytest.raises(ValueError, match="exact solver state"):
        if entry == "create":
            recovery.create_corotational_fiber_frame_engineering_result_ir(
                engineering_result_id=result.engineering_result_id,
                source_adapter=adapter,
            )
        elif entry == "validate":
            recovery.validate_corotational_fiber_frame_engineering_result_ir(result)
        else:
            result.to_manifest()


def test_creator_reuse_cannot_attach_a_different_source_with_the_same_compilation(
    source_case, monkeypatch
):
    adapter = source_case["adapter"]
    changed_adapter, early_metrics = _source_with_live_early_metrics(adapter)
    early_metrics["target_load_factor"] += 0.125
    assert changed_adapter is not adapter
    assert changed_adapter._compilation is adapter._compilation
    original_replace = recovery.replace

    def swap_result_source(value, **changes):
        if type(value) is recovery.CorotationalFiberFrameEngineeringResultIR:
            changes["_adapter"] = changed_adapter
        return original_replace(value, **changes)

    monkeypatch.setattr(recovery, "replace", swap_result_source)
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="binding_mismatch",
    ):
        recovery.create_corotational_fiber_frame_engineering_result_ir(
            engineering_result_id="swapped.source", source_adapter=adapter
        )


def test_rehashed_one_ulp_artifact_still_requires_independent_recovery(source_case):
    original = source_case["result"]
    arrays = dict(original._arrays)
    name = "fiber_stress_pa"
    changed = np.array(arrays[name], copy=True)
    changed[0] = np.nextafter(changed[0], np.inf)
    arrays[name] = immutable_array(changed, dtype="<f8")
    assert arrays[name].tobytes() != original._arrays[name].tobytes()
    descriptors = []
    for row in original.descriptors:
        if row.name == name:
            metadata = row.to_dict()
            metadata.pop("data_hash")
            metadata.pop("content_hash")
            row = replace(
                row,
                data_hash=array_data_hash(arrays[name]),
                content_hash=array_content_hash(metadata, arrays[name]),
            )
        descriptors.append(row)
    manifest = deepcopy(source_case["manifest"])
    manifest["array_descriptors"] = [row.to_dict() for row in descriptors]
    manifest["array_bundle_hash"] = canonical_hash(manifest["array_descriptors"])
    manifest["engineering_result_hash"] = canonical_hash(
        {
            key: value
            for key, value in manifest.items()
            if key != "engineering_result_hash"
        }
    )
    # Detached hash/schema consistency is not the authority to accept altered arrays.
    recovery.validate_corotational_fiber_frame_engineering_result_manifest(manifest)
    forged = replace(
        original,
        _arrays=MappingProxyType(arrays),
        descriptors=tuple(descriptors),
        array_bundle_hash=manifest["array_bundle_hash"],
        engineering_result_hash=manifest["engineering_result_hash"],
    )
    with pytest.raises(
        recovery.CorotationalFiberFrameEngineeringRecoveryError,
        match="binding_mismatch",
    ):
        recovery.validate_corotational_fiber_frame_engineering_result_ir(forged)
