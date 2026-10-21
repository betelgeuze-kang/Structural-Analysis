from dataclasses import replace
from pathlib import Path
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.materials.native_steel_batch import (
    NativeSteelBatch,
    use_native_steel_batch,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    make_rectangular_stateful_rc_fiber_section,
)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    supplied = os.environ.get("SA_PREPARED_STEEL_LIBRARY")
    if supplied:
        return Path(supplied).resolve(strict=True)
    compiler = shutil.which("g++")
    if compiler is None or sys.platform != "linux":
        pytest.skip("optional OpenMP point batch requires Linux g++")
    root = Path(__file__).resolve().parents[1]
    output = tmp_path_factory.mktemp("point-batch") / "libsteel.so"
    subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c++20",
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


def test_section_points_share_one_call_without_changing_full_responses(library):
    section = make_rectangular_stateful_rc_fiber_section()
    parents = (
        section.initial_state(),
        section.initial_state(),
        section.initial_state(),
    )
    strains = ((0.002, 0.004), (-0.003, 0.002), (0.0, 0.0))
    saved = tuple(parent.canonical_bytes() for parent in parents)
    expected = section.integrate_many(strains, parents)
    backend = NativeSteelBatch(
        library, workers=min(2, os.cpu_count() or 1), prepared=True
    )
    config = backend.execution_configuration()
    with use_native_steel_batch(backend):
        actual = section.integrate_many(strains, parents)
    assert backend.calls == 1
    assert [response.to_dict() for response in actual] == [
        response.to_dict() for response in expected
    ]
    assert tuple(parent.canonical_bytes() for parent in parents) == saved
    assert backend.execution_configuration() == config


@pytest.mark.parametrize("order", [2, 3])
def test_beam_batches_quadrature_points_and_preserves_reversal_states(library, order):
    section = make_rectangular_stateful_rc_fiber_section()
    beam = StatefulFiberBeam2D(section, integration_order=order)
    parent = beam.initial_state()
    backend = NativeSteelBatch(library, prepared=True)
    for scale in (1.0, -1.5, 0.5):
        local = scale * np.asarray([0.0, 0.0, 0.0, 0.0075, 0.001, 0.002])
        saved = parent.canonical_bytes()
        expected = beam.integrate(local, parent)
        calls = backend.calls
        with use_native_steel_batch(backend):
            actual = beam.integrate(local, parent)
        assert backend.calls == calls + 1
        assert actual.to_dict() == expected.to_dict()
        assert parent.canonical_bytes() == saved
        parent = actual.state


def test_invalid_later_point_is_rejected_before_any_native_call(library):
    section = make_rectangular_stateful_rc_fiber_section()
    parent = section.initial_state()
    bad = replace(parent, section_contract_hash="sha256:" + "0" * 64)
    backend = NativeSteelBatch(library, prepared=True)
    before = parent.canonical_bytes()
    with (
        use_native_steel_batch(backend),
        pytest.raises(ValueError, match="contract_hash"),
    ):
        section.integrate_many(((0.0, 0.0), (0.0, 0.0)), (parent, bad))
    assert backend.calls == 0 and parent.canonical_bytes() == before


@pytest.mark.parametrize("values,parents", [((), ()), (((0.0, 0.0),), ())])
def test_invalid_batch_counts_rejected(values, parents):
    with pytest.raises(ValueError):
        make_rectangular_stateful_rc_fiber_section().integrate_many(values, parents)


@pytest.mark.parametrize("legacy_native", [False, True])
def test_default_beam_protocol_does_not_probe_new_batch_capabilities(
    library, legacy_native
):
    base = make_rectangular_stateful_rc_fiber_section()
    reads = []

    class ExistingSection:
        def __getattr__(self, name):
            if name in ("integrate_many", "supports_native_steel_point_batch"):
                reads.append(name)
                raise AssertionError("new capability was probed on the default path")
            return getattr(base, name)

    beam = StatefulFiberBeam2D(ExistingSection())
    parent = beam.initial_state()
    local = np.asarray([0.0, 0.0, 0.0, 0.001, 0.0002, 0.0001])
    expected = StatefulFiberBeam2D(base).integrate(local, parent)
    if legacy_native:
        with use_native_steel_batch(NativeSteelBatch(library)):
            actual = beam.integrate(local, parent)
    else:
        actual = beam.integrate(local, parent)
    assert actual.to_dict() == expected.to_dict()
    assert reads == []


def observed_section(calls):
    class ExistingSubclass(StatefulRCFiberSection):
        def integrate(self, generalized_strain, committed_state):
            calls.append(committed_state.state_hash)
            return super().integrate(generalized_strain, committed_state)

    base = make_rectangular_stateful_rc_fiber_section()
    return ExistingSubclass(
        fibers=base.fibers,
        steel=base.steel,
        concrete=base.concrete,
        section_id=base.section_id,
    )


@pytest.mark.parametrize("order", [2, 3])
def test_inherited_capability_does_not_bypass_existing_subclass_integrate(
    library, order
):
    calls = []
    section = observed_section(calls)
    assert "supports_native_steel_point_batch" not in type(section).__dict__
    beam = StatefulFiberBeam2D(section, integration_order=order)
    parent = beam.initial_state()
    local = np.asarray([0.0, 0.0, 0.0, 0.001, 0.0002, 0.0001])
    expected = beam.integrate(local, parent)
    assert len(calls) == order
    calls.clear()
    backend = NativeSteelBatch(library, prepared=True)
    before = parent.canonical_bytes()
    with use_native_steel_batch(backend):
        actual = beam.integrate(local, parent)
    assert actual.to_dict() == expected.to_dict()
    assert len(calls) == backend.calls == order
    assert backend.group_calls == 0
    assert parent.canonical_bytes() == before


def test_direct_inherited_section_batch_preserves_existing_subclass_integrate(library):
    calls = []
    section = observed_section(calls)
    parents = (section.initial_state(), section.initial_state())
    values = ((0.002, 0.001), (-0.003, 0.002))
    expected = section.integrate_many(values, parents)
    assert len(calls) == 2
    calls.clear()
    backend = NativeSteelBatch(library, prepared=True)
    with use_native_steel_batch(backend):
        actual = section.integrate_many(values, parents)
    assert [response.to_dict() for response in actual] == [
        response.to_dict() for response in expected
    ]
    assert len(calls) == backend.calls == 2
    assert backend.group_calls == 0
