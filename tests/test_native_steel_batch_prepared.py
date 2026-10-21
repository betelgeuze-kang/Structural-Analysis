"""Prepared packing and point batches of the existing FP64 steel law."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import gc
from pathlib import Path
import os
import shutil
import subprocess
import sys
from threading import Event
import weakref

import numpy as np
import pytest

from structural_analysis.materials.native_steel_batch import NativeSteelBatch
from structural_analysis.materials import native_steel_batch as native_module
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    supplied = os.environ.get("SA_PREPARED_STEEL_LIBRARY")
    if supplied:
        return Path(supplied).resolve(strict=True)
    compiler = shutil.which("g++")
    if compiler is None or sys.platform != "linux":
        pytest.skip("optional Linux OpenMP backend requires g++")
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("prepared-steel-native") / "libsteel.so"
    subprocess.run(
        [
            compiler,
            "-std=c++20",
            "-O2",
            "-shared",
            "-fPIC",
            "-fopenmp",
            "-ffp-contract=off",
            str(root / "native/cpp/src/materials/steel_batch.cpp"),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output


def material_rows():
    return tuple(
        BilinearCombinedHardeningSteel(
            yield_stress_mpa=100.0 + 25.0 * index,
            isotropic_hardening_modulus_mpa=1000.0 + 50.0 * index,
            material_id=f"prepared-steel-{index}",
        )
        for index in range(4)
    )


def test_repeated_exact_law_signature_is_fresh_per_call_and_detached():
    material = BilinearCombinedHardeningSteel()
    reference = weakref.ref(material)
    first = native_module._steel_material_signature((material,) * 16)
    assert all(row is first[0] for row in first)
    object.__setattr__(material, "yield_stress_mpa", 300.0)
    second = native_module._steel_material_signature((material,) * 16)
    assert second != first
    assert second[0] is not first[0]
    assert all(row is second[0] for row in second)
    del material
    gc.collect()
    assert reference() is None


def test_signature_sharing_limit_does_not_drop_or_reorder_current_values(monkeypatch):
    monkeypatch.setattr(native_module, "_SIGNATURE_ROW_SHARING_LIMIT", 2)
    materials = material_rows()
    signature = native_module._steel_material_signature(
        (*materials, materials[0], materials[2])
    )
    assert signature[0] is signature[4]
    assert signature[2] == signature[5]
    assert signature[2] is not signature[5]
    expected = tuple(
        native_module._steel_material_signature((value,))[0] for value in materials
    )
    assert signature == (*expected, expected[0], expected[2])


@pytest.mark.parametrize("custom_access", ["descriptor", "getattribute"])
def test_signature_keeps_custom_field_access_per_occurrence(monkeypatch, custom_access):
    material = BilinearCombinedHardeningSteel()
    observed = []

    def value(instance):
        observed.append(instance)
        return 250.0 + len(observed)

    if custom_access == "descriptor":
        monkeypatch.setattr(
            BilinearCombinedHardeningSteel, "yield_stress_mpa", property(value)
        )
    else:

        def access(instance, name):
            return (
                value(instance)
                if name == "yield_stress_mpa"
                else object.__getattribute__(instance, name)
            )

        monkeypatch.setattr(BilinearCombinedHardeningSteel, "__getattribute__", access)
    signature = native_module._steel_material_signature((material, material))
    assert signature[0] != signature[1]
    assert len(observed) == 2


def test_prepared_array_subclasses_preserve_original_scalar_access(library):
    class ScalarAccessArray(np.ndarray):
        def tolist(self):
            raise AssertionError("subclass bulk conversion must remain unused")

    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    buffers = plan._workspace.trial_buffers(1, backend)
    buffers.strains = buffers.strains.view(ScalarAccessArray)
    buffers.output = buffers.output.view(ScalarAccessArray)
    parents = tuple(material.initial_state() for material in materials)
    actual = plan.integrate((0.002,) * 4, parents)
    expected = tuple(
        material.integrate(0.002, parent)
        for material, parent in zip(materials, parents, strict=True)
    )
    assert tuple(response.to_dict() for response in actual) == tuple(
        response.to_dict() for response in expected
    )
    assert not plan._workspace.lock.locked()


def test_response_detachment_cap_keeps_boundary_and_large_fallback_exact(
    library, monkeypatch
):
    monkeypatch.setattr(native_module, "_BULK_RESPONSE_LIMIT", 4)
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    raw = NativeSteelBatch(library)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    saved_parents = tuple(parent.canonical_bytes() for parent in parents)
    first = None
    first_bytes = None
    for groups in (1, 2):
        strains = tuple((0.0, -0.0, 0.002, -0.003) for _ in range(groups))
        actual = plan.integrate_many(strains, (parents,) * groups)
        expected = tuple(
            raw.integrate(materials, values, parents) for values in strains
        )
        assert response_dicts(actual) == response_dicts(expected)
        assert saved_parents == tuple(parent.canonical_bytes() for parent in parents)
        assert all(
            type(response.total_strain) is float for row in actual for response in row
        )
        if first is None:
            first, first_bytes = actual, response_dicts(actual)
        else:
            assert response_dicts(first) == first_bytes
    assert backend.calls == backend.prepared_calls == 2
    assert backend.points == backend.prepared_points == 12
    assert backend.group_calls == 1
    assert backend.buffer_allocations == 2
    assert backend.plan_builds == 1
    assert not plan._workspace.lock.locked()


def response_dicts(groups):
    return tuple(tuple(response.to_dict() for response in group) for group in groups)


def test_prepared_execution_is_explicit_and_configuration_is_counter_independent(
    library,
):
    materials = material_rows()
    old = NativeSteelBatch(library)
    assert old.prepared is False
    with pytest.raises(ValueError, match="prepared=True"):
        old.prepare(materials)
    with pytest.raises(ValueError, match="boolean"):
        NativeSteelBatch(library, prepared=1)
    backend = NativeSteelBatch(library, prepared=True)
    before = backend.execution_configuration()
    parents = tuple(material.initial_state() for material in materials)
    backend.integrate(materials, (0.0,) * 4, parents)
    assert backend.execution_configuration() == before
    assert before["prepared"] is True
    assert not {"calls", "points", "buffer_allocations"}.intersection(before)
    assert backend.metadata()["prepared_calls"] == 1


@pytest.mark.parametrize("workers", [1, 2])
def test_point_major_cyclic_trials_match_scalar_and_leave_every_parent_immutable(
    library, workers
):
    if workers > (os.cpu_count() or 1):
        pytest.skip("thread count exceeds this runner's CPUs")
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True, workers=workers)
    parents = tuple(
        tuple(material.initial_state() for material in materials) for _ in range(3)
    )
    first_result = None
    first_snapshot = None
    for factor in (0.0, 0.0001, 0.002, -0.003, 0.004, 0.0, -0.004):
        strains = tuple(
            tuple(factor * (1.0 + point / 3 + index / 4) for index in range(4))
            for point in range(3)
        )
        before = tuple(
            tuple(parent.canonical_bytes() for parent in group) for group in parents
        )
        expected = tuple(
            tuple(
                material.integrate(strain, parent)
                for material, strain, parent in zip(
                    materials, strain_group, parent_group, strict=True
                )
            )
            for strain_group, parent_group in zip(strains, parents, strict=True)
        )
        actual = backend.integrate_many(materials, strains, parents)
        assert response_dicts(actual) == response_dicts(expected)
        assert before == tuple(
            tuple(parent.canonical_bytes() for parent in group) for group in parents
        )
        for parent_group, response_group in zip(parents, actual, strict=True):
            for parent, response in zip(parent_group, response_group, strict=True):
                if not response.yielded:
                    assert response.state is parent
        if first_result is None:
            first_result, first_snapshot = actual, response_dicts(actual)
        assert response_dicts(first_result) == first_snapshot
        parents = tuple(tuple(response.state for response in group) for group in actual)
    assert (backend.calls, backend.points, backend.group_calls) == (7, 84, 7)
    assert backend.plan_builds == backend.buffer_allocations == 1


def test_prepared_arrays_are_reused_without_retaining_old_material_objects(library):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    first = plan.integrate((0.002,) * 4, parents)
    saved = tuple(response.to_dict() for response in first)
    buffers = plan._workspace.buffers[1]
    pointers = tuple(
        array.ctypes.data
        for array in (
            buffers.materials,
            buffers.strains,
            buffers.parents,
            buffers.output,
        )
    )
    with pytest.raises(ValueError):
        buffers.materials.setflags(write=True)
    copied = backend.prepare(deepcopy(materials))
    assert copied._workspace is plan._workspace
    copied.integrate((-0.003,) * 4, parents)
    assert pointers == tuple(
        array.ctypes.data
        for array in (
            buffers.materials,
            buffers.strains,
            buffers.parents,
            buffers.output,
        )
    )
    assert tuple(response.to_dict() for response in first) == saved
    object.__setattr__(materials[0], "yield_stress_mpa", 300.0)
    with pytest.raises(ValueError, match="values changed"):
        plan.integrate((0.002,) * 4, parents)
    # A value-equal fresh law list can still use the old workspace safely.
    copied.integrate((0.001,) * 4, parents)
    assert backend.plan_builds == backend.buffer_allocations == 1


def test_law_changes_make_old_plan_reject_and_fresh_prepare_select_new_values(library):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    object.__setattr__(materials[0], "yield_stress_mpa", 300.0)
    with pytest.raises(ValueError, match="values changed"):
        plan.integrate((0.002,) * 4, parents)
    fresh = backend.prepare(materials)
    assert fresh._workspace is not plan._workspace
    actual = fresh.integrate((0.002,) * 4, parents)
    expected = tuple(
        material.integrate(0.002, parent)
        for material, parent in zip(materials, parents, strict=True)
    )
    assert tuple(response.to_dict() for response in actual) == tuple(
        response.to_dict() for response in expected
    )


def test_plan_keys_keep_scalar_types_and_signed_zero_bits_distinct(library):
    material = BilinearCombinedHardeningSteel(isotropic_hardening_modulus_mpa=0.0)
    backend = NativeSteelBatch(library, prepared=True)
    positive = backend.prepare((material,))
    object.__setattr__(material, "isotropic_hardening_modulus_mpa", -0.0)
    negative = backend.prepare((material,))
    assert positive._workspace is not negative._workspace
    assert np.signbit(negative._workspace.materials[0, 2])
    workspaces = []
    for value in (True, 1, 1.0):
        object.__setattr__(material, "material_id", value)
        workspaces.append(backend.prepare((material,))._workspace)
    assert len({id(workspace) for workspace in workspaces}) == 3


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_bad_strain_does_not_enter_native_and_plan_recovers(library, bad):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    before = tuple(parent.canonical_bytes() for parent in parents)
    with pytest.raises(ValueError):
        plan.integrate((0.0, bad, 0.0, 0.0), parents)
    assert backend.calls == 0
    assert before == tuple(parent.canonical_bytes() for parent in parents)
    assert len(plan.integrate((0.0,) * 4, parents)) == 4


def test_invalid_parent_and_native_rejection_leave_accepted_objects_unchanged(library):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    corrupt = (replace(parents[0], backstress_mpa=1.0), *parents[1:])
    before = tuple(parent.canonical_bytes() for parent in parents)
    with pytest.raises(ValueError, match="backstress"):
        plan.integrate((0.0,) * 4, corrupt)
    assert backend.calls == 0
    object.__setattr__(materials[0], "elastic_modulus_mpa", -1.0)
    invalid = backend.prepare(materials)
    with pytest.raises(ValueError, match="status=2 index=0"):
        invalid.integrate((0.0,) * 4, parents)
    assert before == tuple(parent.canonical_bytes() for parent in parents)


@pytest.mark.parametrize(
    "damage", ["short_output", "alias_output", "readonly_parents", "alias_inputs"]
)
def test_damaged_prepared_buffers_reject_before_packing_or_native(library, damage):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    buffers = plan._workspace.trial_buffers(1, backend)
    if damage == "short_output":
        buffers.output = np.empty((4, 10))
    elif damage == "alias_output":
        storage = np.full(44, 17.0)
        buffers.output = storage.reshape(4, 11)
        buffers.parents = storage[:16].reshape(4, 4)
    elif damage == "readonly_parents":
        buffers.parents.setflags(write=False)
    else:
        buffers.strains = buffers.parents.ravel()[:4]
    before = buffers.parents.tobytes()
    with pytest.raises(ValueError, match="shape|alias|writable|independent"):
        plan.integrate((0.0,) * 4, parents)
    assert buffers.parents.tobytes() == before
    assert backend.calls == 0


@pytest.mark.parametrize(
    "groups", [((), ()), (((0.0,),), ((None,),)), (((0.0,) * 4,), ())]
)
def test_group_shape_guards_precede_native(library, groups):
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(material_rows())
    with pytest.raises(ValueError, match="fiber layout"):
        plan.integrate_many(*groups)
    assert backend.calls == 0


def test_shared_prepared_workspace_rejects_concurrent_use_and_releases_lock(
    library, monkeypatch
):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    first, second = backend.prepare(materials), backend.prepare(deepcopy(materials))
    parents = tuple(material.initial_state() for material in materials)
    entered, release = Event(), Event()
    original = backend._evaluate_arrays_into

    def blocked(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError("test release timeout")
        return original(*args, **kwargs)

    monkeypatch.setattr(backend, "_evaluate_arrays_into", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first.integrate, (0.002,) * 4, parents)
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(ValueError, match="already in use"):
                second.integrate((0.003,) * 4, parents)
        finally:
            release.set()
        assert len(future.result(timeout=5)) == 4
    assert len(second.integrate((0.001,) * 4, parents)) == 4


@pytest.mark.parametrize("invalid", [float("nan"), 2.0])
def test_invalid_native_output_is_not_consumed_or_exposed(
    library, monkeypatch, invalid
):
    materials = material_rows()
    backend = NativeSteelBatch(library, prepared=True)
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    before = tuple(parent.canonical_bytes() for parent in parents)
    accepted = plan.integrate((0.002,) * 4, parents)
    saved = tuple(response.to_dict() for response in accepted)

    def bad_output(count, strains, laws, states, workers, output, bad):
        array = np.ctypeslib.as_array(output, shape=(count * 11,))
        array[:] = 0.0
        array[10] = invalid
        return 0

    monkeypatch.setattr(backend, "_call", bad_output)
    with pytest.raises(ValueError, match="invalid values"):
        plan.integrate((0.002,) * 4, parents)
    assert before == tuple(parent.canonical_bytes() for parent in parents)
    assert tuple(response.to_dict() for response in accepted) == saved
    assert not plan._workspace.lock.locked()


def test_default_array_entrypoint_preserves_memmap_input_admission(library, tmp_path):
    strains = np.memmap(
        tmp_path / "strains.bin", mode="w+", dtype=np.float64, shape=(4,)
    )
    strains[:] = 0.0001
    materials = np.tile([200000.0, 250.0, 3000.0, 5000.0, 1.0e-10], (4, 1))
    parents = np.zeros((4, 4))
    backend = NativeSteelBatch(library)
    before = strains.tobytes()
    output = backend.evaluate_arrays(strains, materials, parents)
    np.testing.assert_array_equal(output[:, 0], np.full(4, 20.0))
    assert strains.tobytes() == before
    assert not output.flags.writeable


def test_prepared_workspace_and_group_buffer_caches_are_entry_bounded(library):
    backend = NativeSteelBatch(library, prepared=True)
    for index in range(10):
        backend.prepare(
            (BilinearCombinedHardeningSteel(yield_stress_mpa=100.0 + index),)
        )
    assert len(backend._prepared_workspaces) == 8
    materials = material_rows()
    plan = backend.prepare(materials)
    parents = tuple(material.initial_state() for material in materials)
    for groups in (1, 2, 3):
        plan.integrate_many(((0.0,) * 4,) * groups, (parents,) * groups)
    assert len(plan._workspace.buffers) == 2
    assert tuple(plan._workspace.buffers) == (2, 3)
