from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import ctypes
import os
import runpy
import shutil
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis.materials.native_steel_batch import (
    NativeSteelBatch,
    active_native_steel_batch,
    use_native_steel_batch,
)
from structural_analysis.materials.stateful_fiber_section import (
    FiberSectionNewtonConfig,
    make_rectangular_stateful_rc_fiber_section,
    solve_stateful_fiber_section_resultants,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    compiler = shutil.which("g++")
    if compiler is None or sys.platform != "linux":
        pytest.skip("optional Linux OpenMP backend requires g++")
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("steel-native") / "libsteel.so"
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


@pytest.mark.parametrize("workers", [1, 2, 4])
def test_cyclic_scalar_parity_and_immutable_parents(library, workers):
    if workers > (os.cpu_count() or 1):
        pytest.skip("thread count exceeds this runner's CPUs")
    backend = NativeSteelBatch(library, workers=workers)
    materials = [
        BilinearCombinedHardeningSteel(
            yield_stress_mpa=100 + 10 * i,
            isotropic_hardening_modulus_mpa=1000 + i * 100,
        )
        for i in range(16)
    ]
    parents = [m.initial_state() for m in materials]
    for strain in [0.0, 0.0001, 0.002, -0.003, 0.004, 0.0, -0.004]:
        strains = [strain * (1 + i / 16) for i in range(16)]
        before = [p.canonical_bytes() for p in parents]
        expected = [m.integrate(s, p) for m, s, p in zip(materials, strains, parents)]
        actual = backend.integrate(materials, strains, parents)
        assert [x.to_dict() for x in actual] == [x.to_dict() for x in expected]
        assert before == [p.canonical_bytes() for p in parents]
        for old, response in zip(parents, actual):
            if not response.yielded:
                assert response.state is old
        parents = [x.state for x in actual]


def test_mixed_section_reversal_rollback_and_context_restoration(library):
    base = make_rectangular_stateful_rc_fiber_section()
    section = replace(
        base,
        steel_overrides=(
            ("steel-top-layer", BilinearCombinedHardeningSteel(yield_stress_mpa=100)),
        ),
    )
    assert deepcopy(section).contract_hash == section.contract_hash
    assert asdict(deepcopy(section)) == asdict(section)
    parent = section.initial_state()
    backend = NativeSteelBatch(library, workers=min(2, os.cpu_count() or 1))
    other = NativeSteelBatch(library)
    assert active_native_steel_batch() is None
    with use_native_steel_batch(backend):
        with pytest.raises(RuntimeError), use_native_steel_batch(other):
            assert active_native_steel_batch() is other
            raise RuntimeError("test restoration")
        assert active_native_steel_batch() is backend
        for strain in [(0.00075, 0), (-0.003, 0.004), (0.002, -0.006)]:
            with use_native_steel_batch(other):
                actual = section.integrate(strain, parent)
            # Compare the independently retained Python execution branch.
            from structural_analysis.materials import native_steel_batch as module

            token = module._ACTIVE.set(None)
            try:
                expected = section.integrate(strain, parent)
            finally:
                module._ACTIVE.reset(token)
            assert actual.to_dict() == expected.to_dict()
            parent = expected.state
        before = parent.canonical_bytes()
        failed = solve_stateful_fiber_section_resultants(
            section,
            parent,
            target_resultants=(1e6, 1e6),
            config=FiberSectionNewtonConfig(maximum_iterations=0),
        )
        assert not failed.committed and failed.accepted_state is parent
        assert parent.canonical_bytes() == before
    assert active_native_steel_batch() is None


@pytest.mark.parametrize("bad", [np.nan, np.inf, -1.0])
def test_native_rejects_whole_batch_without_mutating_parent(library, bad):
    backend = NativeSteelBatch(library)
    states = np.zeros((4, 4))
    before = states.tobytes()
    laws = np.tile([200000.0, 250.0, 3000.0, 5000.0, 1e-10], (4, 1))
    laws[2, 0] = bad
    with pytest.raises(ValueError, match="index=2"):
        backend.evaluate_arrays(np.zeros(4), laws, states)
    assert states.tobytes() == before


def test_native_shape_and_worker_guards(library):
    for workers in (True, 0, -1, 10000):
        with pytest.raises(ValueError):
            NativeSteelBatch(library, workers=workers)
    backend = NativeSteelBatch(library)
    with pytest.raises(ValueError, match="shape"):
        backend.evaluate_arrays(np.zeros(2), np.zeros((1, 5)), np.zeros((2, 4)))


def test_native_rejects_overflowed_expected_state(library):
    backend = NativeSteelBatch(library)
    with pytest.raises(ValueError, match="index=0"):
        backend.evaluate_arrays(
            np.array([2.0]),
            np.array([[1.0, 1.0, 0.0, 1e308, 0.0]]),
            np.array([[2.0, 0.0, 2.0, 2.0]]),
        )


def test_unaligned_numpy_view_is_copied_and_raw_pointer_is_rejected(library):
    backend = NativeSteelBatch(library)
    buffer = bytearray(4 * 8 + 1)
    strains = np.frombuffer(buffer, dtype=np.float64, count=4, offset=1)
    assert not strains.flags.aligned
    laws = np.tile([200000.0, 250.0, 3000.0, 5000.0, 1e-10], (4, 1))
    parents = np.zeros((4, 4))
    result = backend.evaluate_arrays(strains, laws, parents)
    assert result.shape == (4, 11) and backend.last_observed_workers == 1
    pointer = ctypes.POINTER(ctypes.c_double)
    output = np.zeros((4, 11))
    bad = ctypes.c_size_t(123)
    before = bytes(buffer)
    status = backend._call(
        4,
        strains.ctypes.data_as(pointer),
        laws.ctypes.data_as(pointer),
        parents.ctypes.data_as(pointer),
        1,
        output.ctypes.data_as(pointer),
        ctypes.byref(bad),
    )
    assert status != 0 and bytes(buffer) == before and bad.value == 123


def test_raw_abi_refuses_output_or_status_alias_without_mutation(library):
    backend = NativeSteelBatch(library)
    shared = np.zeros(22)
    laws = np.tile([200000.0, 250.0, 3000.0, 5000.0, 1e-10], (2, 1))
    strains = np.zeros(2)
    pointer = ctypes.POINTER(ctypes.c_double)
    bad = ctypes.c_size_t(123)
    before = shared.tobytes()
    status = backend._call(
        2,
        strains.ctypes.data_as(pointer),
        laws.ctypes.data_as(pointer),
        shared.ctypes.data_as(pointer),
        2,
        shared.ctypes.data_as(pointer),
        ctypes.byref(bad),
    )
    assert status != 0 and shared.tobytes() == before
    status_alias = ctypes.cast(shared.ctypes.data, ctypes.POINTER(ctypes.c_size_t))
    output = np.empty((2, 11))
    status = backend._call(
        2,
        strains.ctypes.data_as(pointer),
        laws.ctypes.data_as(pointer),
        shared.ctypes.data_as(pointer),
        1,
        output.ctypes.data_as(pointer),
        status_alias,
    )
    assert status != 0 and shared.tobytes() == before


def test_public_rc_result_and_restart_match_python(library, tmp_path):
    _write_model = runpy.run_path(
        str(Path(__file__).with_name("test_public_rc_fiber_frame_api.py"))
    )["_write_model"]
    from structural_analysis.api.nonlinear_fiber_frame import (
        PublicRCFiberFrameConfig,
        analyze_public_rc_fiber_frame,
    )

    model = _write_model(tmp_path / "rc.json")
    config = PublicRCFiberFrameConfig(load_steps=2)
    expected = analyze_public_rc_fiber_frame(model, config)
    workers = min(2, os.cpu_count() or 1)
    backend = NativeSteelBatch(library, workers=workers)
    with use_native_steel_batch(backend):
        actual = analyze_public_rc_fiber_frame(model, config)
    assert actual.status == expected.status
    for name in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
        "convergence_history",
        "checkpoint",
    ):
        assert getattr(actual, name) == getattr(expected, name)
    assert actual.checkpoint_artifact() == expected.checkpoint_artifact()
    with use_native_steel_batch(backend):
        restarted = analyze_public_rc_fiber_frame(
            model,
            config,
            restart_checkpoint_chain=expected.checkpoint_artifact(epoch=1),
        )
    assert restarted.checkpoint_artifact() == expected.checkpoint_artifact()
    assert backend.calls > 0
    assert actual.configuration["material_execution_backend"]["workers"] == workers


def test_current_steel_lookup_replace_and_deepcopy_need_no_private_index():
    default = BilinearCombinedHardeningSteel(elastic_modulus_mpa=100_000.0)
    override = BilinearCombinedHardeningSteel(elastic_modulus_mpa=150_000.0)
    section = replace(
        make_rectangular_stateful_rc_fiber_section(),
        steel=default,
        steel_overrides=(("steel-top-layer", override),),
    )
    for current in (section, deepcopy(section)):
        assert current.steel_material_for("steel-bottom-layer") == default
        assert current.steel_material_for("steel-top-layer") == override
        assert "_steel_ids_sorted" not in vars(current)
        assert "_steel_materials_sorted" not in vars(current)
        parent = current.initial_state()
        current.validate_state(parent)
        response = current.integrate((1.0e-4, 0.0), parent)
        for fiber, stress in zip(current.fibers, response.fiber_stresses_mpa, strict=True):
            if fiber.material_kind == "steel":
                expected = current.steel_material_for(fiber.fiber_id).elastic_modulus_mpa * 1.0e-4
                assert stress == expected


def test_legacy_private_steel_index_tampering_has_no_physical_effect():
    section = make_rectangular_stateful_rc_fiber_section()
    parent = section.initial_state()
    expected = section.integrate((1.0e-4, 0.0), parent)
    physical_hash = section.contract_hash
    fake = BilinearCombinedHardeningSteel(elastic_modulus_mpa=50_000.0)
    object.__setattr__(section, "_steel_ids_sorted", ("nonexistent",))
    object.__setattr__(section, "_steel_materials_sorted", (fake,))
    assert section.contract_hash == physical_hash
    section.validate_state(parent)
    assert section.integrate((1.0e-4, 0.0), parent).to_dict() == expected.to_dict()


def test_forced_public_steel_replacement_uses_current_law_and_new_parent():
    section = make_rectangular_stateful_rc_fiber_section()
    prior = section.initial_state()
    replacement = BilinearCombinedHardeningSteel(elastic_modulus_mpa=50_000.0)
    object.__setattr__(section, "steel", replacement)
    with pytest.raises(ValueError, match="section_contract_hash"):
        section.validate_state(prior)
    parent = section.initial_state()
    assert parent.section_contract_hash == section.contract_hash
    actual = section.integrate((1.0e-4, 0.0), parent)
    fresh = replace(section)
    assert actual.to_dict() == fresh.integrate((1.0e-4, 0.0), fresh.initial_state()).to_dict()
    for fiber, stress in zip(section.fibers, actual.fiber_stresses_mpa, strict=True):
        if fiber.material_kind == "steel":
            assert stress == 5.0
