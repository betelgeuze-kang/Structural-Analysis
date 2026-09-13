"""Bounded constitutive timing contracts; fixture clocks are not speed evidence."""

import itertools
import json
from dataclasses import replace

import pytest

from structural_analysis.elements.stateful_fiber_beam2d import StatefulFiberBeam2D
from structural_analysis.materials.concrete_damage import (
    AsymmetricConcreteDamageMaterial,
)
from structural_analysis.materials.stateful_fiber_section import (
    StatefulRCFiberSection,
    make_rectangular_stateful_rc_fiber_section,
)
from structural_analysis.materials.trial_runtime import (
    MATERIAL_TRIAL_TIMING_SCOPE,
    MaterialTrialRuntimeRecorder,
    MaterialTrialTimingError,
)
from structural_analysis.materials.uniaxial_plasticity import (
    BilinearCombinedHardeningSteel,
)


def _bytes(response):
    return json.dumps(response.to_dict(), sort_keys=True, allow_nan=False).encode()


def _recorder():
    return MaterialTrialRuntimeRecorder(clock_ns=itertools.count(step=10).__next__)


@pytest.mark.parametrize(
    "kind,material,strain",
    [
        ("steel", BilinearCombinedHardeningSteel(), 0.005),
        ("concrete", AsymmetricConcreteDamageMaterial(), -0.001),
    ],
)
def test_direct_material_observation_preserves_exact_response_and_parent(
    kind, material, strain
):
    parent = material.initial_state()
    original_parent = parent.canonical_bytes()
    expected = material.integrate(strain, parent)
    recorder = _recorder()
    observed = recorder.observe(kind, material.integrate, strain, parent)
    assert _bytes(observed) == _bytes(expected)
    assert observed.state.canonical_bytes() == expected.state.canonical_bytes()
    assert parent.canonical_bytes() == original_parent
    payload = recorder.to_dict()
    assert payload["scope"] == MATERIAL_TRIAL_TIMING_SCOPE
    assert payload["wall_ns"] == 10
    assert payload["call_count"] == 1
    assert payload["exception_count"] == 0
    assert payload["materials"][kind] == {
        "wall_ns": 10,
        "call_count": 1,
        "exception_count": 0,
    }
    payload["materials"][kind]["call_count"] = 999
    assert recorder.to_dict()["materials"][kind]["call_count"] == 1


def test_cyclic_section_trial_observation_preserves_all_parent_bytes_and_identities():
    section = make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2)
    reference_parent = section.initial_state()
    observed_parent = section.initial_state()
    contract = section.contract_hash
    recorder = _recorder()
    for strain in ((-3e-4, 6e-3), (0.0, 0.0), (-4e-4, -6e-3)):
        reference_bytes = reference_parent.canonical_bytes()
        observed_bytes = observed_parent.canonical_bytes()
        expected = section.integrate(strain, reference_parent)
        observed = section.integrate_with_material_runtime(
            strain, observed_parent, material_runtime=recorder
        )
        assert _bytes(observed) == _bytes(expected)
        assert observed.state.canonical_bytes() == expected.state.canonical_bytes()
        assert reference_parent.canonical_bytes() == reference_bytes
        assert observed_parent.canonical_bytes() == observed_bytes
        assert section.contract_hash == contract
        reference_parent, observed_parent = expected.state, observed.state
    payload = recorder.to_dict()
    assert payload["coverage_complete"] is True
    assert payload["instrumented_section_call_count"] == 3
    assert payload["call_count"] == 12
    assert payload["wall_ns"] == 120
    assert payload["materials"]["steel"]["call_count"] == 6
    assert payload["materials"]["concrete"]["call_count"] == 6


def test_beam_material_trial_observation_preserves_exact_response():
    element = StatefulFiberBeam2D(
        section=make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2),
        integration_order=2,
    )
    parent = element.initial_state()
    original_parent = parent.canonical_bytes()
    local = element.uniform_generalized_strain_displacements(-3e-4, 6e-3)
    expected = element.integrate(local, parent)
    recorder = _recorder()
    observed = element.integrate(local, parent, material_runtime=recorder)
    assert _bytes(observed) == _bytes(expected)
    assert parent.canonical_bytes() == original_parent
    assert recorder.call_count == 8
    assert recorder.instrumented_section_call_count == 2
    assert recorder.coverage_complete is True


def test_failed_constitutive_trial_preserves_parent_and_counts_actual_attempt(
    monkeypatch,
):
    section = make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2)
    parent = section.initial_state()
    parent_bytes = parent.canonical_bytes()
    error = ValueError("bounded constitutive failure")

    def fail(*args, **kwargs):
        raise error

    monkeypatch.setattr(AsymmetricConcreteDamageMaterial, "integrate", fail)
    recorder = _recorder()
    with pytest.raises(ValueError) as caught:
        section.integrate_with_material_runtime(
            (0.0, 0.0), parent, material_runtime=recorder
        )
    assert caught.value is error
    assert parent.canonical_bytes() == parent_bytes
    assert recorder.call_count == recorder.exception_count == 1
    assert recorder.wall_ns == 10
    assert recorder.to_dict()["materials"]["concrete"]["exception_count"] == 1
    assert recorder.to_dict()["materials"]["steel"]["call_count"] == 0


@pytest.mark.parametrize(
    "kind,material",
    [
        ("steel", BilinearCombinedHardeningSteel()),
        ("concrete", AsymmetricConcreteDamageMaterial()),
    ],
)
def test_actual_invalid_material_trial_counts_each_kind_failure(kind, material):
    parent = material.initial_state()
    original_parent = parent.canonical_bytes()
    recorder = _recorder()
    with pytest.raises(ValueError):
        recorder.observe(kind, material.integrate, float("nan"), parent)
    assert parent.canonical_bytes() == original_parent
    assert recorder.call_count == recorder.exception_count == 1
    assert recorder.to_dict()["materials"][kind] == {
        "wall_ns": 10,
        "call_count": 1,
        "exception_count": 1,
    }


class _SectionProxy:
    def __init__(self):
        self.delegate = make_rectangular_stateful_rc_fiber_section(
            concrete_layer_count=2
        )

    @property
    def contract_hash(self):
        return self.delegate.contract_hash

    def initial_state(self):
        return self.delegate.initial_state()

    def validate_state(self, state):
        self.delegate.validate_state(state)

    def integrate(self, strain, state):
        return self.delegate.integrate(strain, state)

    def dissipated_energy_mj_per_m(self, state):
        return self.delegate.dissipated_energy_mj_per_m(state)


class _UnobservedCapabilityProxy(_SectionProxy):
    def integrate_with_material_runtime(self, strain, state, *, material_runtime):
        return self.delegate.integrate(strain, state)


@pytest.mark.parametrize("section_type", [_SectionProxy, _UnobservedCapabilityProxy])
def test_uninstrumented_custom_section_retains_response_and_explicit_incomplete_coverage(
    section_type,
):
    element = StatefulFiberBeam2D(section=section_type(), integration_order=2)
    parent = element.initial_state()
    local = element.uniform_generalized_strain_displacements(-3e-4, 6e-3)
    expected = element.integrate(local, parent)

    def clock_must_not_run():
        pytest.fail("unsupported constituent calls cannot claim clock observations")

    recorder = MaterialTrialRuntimeRecorder(clock_ns=clock_must_not_run)
    observed = element.integrate(local, parent, material_runtime=recorder)
    assert _bytes(observed) == _bytes(expected)
    assert recorder.coverage_complete is False
    assert recorder.call_count == recorder.wall_ns == 0
    assert recorder.unmeasured_section_call_count == 2
    assert recorder.to_dict()["unavailable_reasons"] == [
        "section_material_trial_instrumentation_unavailable"
    ]


def test_mixed_section_coverage_keeps_observed_subset_without_promoting_total():
    supported = StatefulFiberBeam2D(
        section=make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2),
        integration_order=2,
    )
    unsupported = StatefulFiberBeam2D(section=_SectionProxy(), integration_order=2)
    recorder = _recorder()
    for element in (supported, unsupported):
        element.integrate([0.0] * 6, element.initial_state(), material_runtime=recorder)
    payload = recorder.to_dict()
    assert payload["coverage_complete"] is False
    assert payload["wall_ns"] == 80
    assert payload["call_count"] == 8
    assert payload["instrumented_section_call_count"] == 2
    assert payload["unmeasured_section_call_count"] == 2


def test_inherited_capability_preserves_custom_section_integrate_override():
    class CustomSection(StatefulRCFiberSection):
        def integrate(self, generalized_strain, committed_state):
            response = super().integrate(generalized_strain, committed_state)
            return replace(response, axial_force_kn=response.axial_force_kn + 1.0)

    base = make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2)
    section = CustomSection(
        fibers=base.fibers, steel=base.steel, concrete=base.concrete
    )
    element = StatefulFiberBeam2D(section=section, integration_order=2)
    parent = element.initial_state()
    expected = element.integrate([0.0] * 6, parent)
    recorder = _recorder()
    observed = element.integrate([0.0] * 6, parent, material_runtime=recorder)
    assert _bytes(observed) == _bytes(expected)
    assert recorder.call_count == recorder.wall_ns == 0
    assert recorder.coverage_complete is False
    assert recorder.unmeasured_section_call_count == 2


def test_omitted_material_recorder_never_accesses_trial_clock(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("default numerical path must not observe material clocks")

    monkeypatch.setattr(MaterialTrialRuntimeRecorder, "observe", forbidden)
    section = make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2)
    section.integrate((-3e-4, 6e-3), section.initial_state())
    element = StatefulFiberBeam2D(section=section, integration_order=2)
    element.integrate([0.0] * 6, element.initial_state())


@pytest.mark.parametrize("value", [True, 1.5, -1, None])
def test_invalid_material_clock_type_fails_as_runtime_error_before_trial(value):
    recorder = MaterialTrialRuntimeRecorder(clock_ns=lambda: value)

    def forbidden():
        pytest.fail("invalid start clock must fail before constitutive call")

    with pytest.raises(MaterialTrialTimingError, match="clock_ns"):
        recorder.observe("steel", forbidden)
    assert recorder.call_count == recorder.exception_count == 0
    assert recorder.timing_error_count == 1
    assert recorder.coverage_complete is False


def test_regressing_material_clock_retains_attempt_count_and_releases_recorder():
    clock = iter((10, 5, 20, 30))
    recorder = MaterialTrialRuntimeRecorder(clock_ns=clock.__next__)
    with pytest.raises(MaterialTrialTimingError, match="monotonic"):
        recorder.observe("steel", lambda: object())
    assert recorder.call_count == 1
    assert recorder.exception_count == 0
    assert recorder.wall_ns == 0
    assert recorder.coverage_complete is False
    sentinel = object()
    assert recorder.observe("concrete", lambda: sentinel) is sentinel
    assert recorder.call_count == 2
    assert recorder.wall_ns == 10
    assert recorder.timing_error_count == 1


def test_raising_material_clock_never_becomes_physical_value_error():
    def clock():
        raise ValueError("clock source failure")

    recorder = MaterialTrialRuntimeRecorder(clock_ns=clock)
    with pytest.raises(MaterialTrialTimingError, match="clock_ns"):
        recorder.observe("steel", lambda: None)
    assert recorder.timing_error_count == 1


def test_invalid_end_clock_keeps_actual_attempt_count_and_distinct_timing_error():
    recorder = MaterialTrialRuntimeRecorder(clock_ns=iter((0, False)).__next__)
    with pytest.raises(MaterialTrialTimingError, match="clock_ns"):
        recorder.observe("steel", lambda: None)
    assert recorder.call_count == 1
    assert recorder.exception_count == 0
    assert recorder.wall_ns == 0
    assert recorder.timing_error_count == 1
    assert recorder.coverage_complete is False


def test_reentrant_material_observation_is_distinct_instrumentation_failure():
    recorder = _recorder()
    with pytest.raises(MaterialTrialTimingError, match="already active"):
        recorder.observe("concrete", lambda: recorder.observe("steel", lambda: None))
    assert recorder.call_count == recorder.exception_count == 1
    assert recorder.to_dict()["materials"]["steel"]["call_count"] == 0
    assert recorder.timing_error_count == 1
    assert recorder.coverage_complete is False


def test_operation_runtime_error_is_preserved_without_reclassifying_as_clock_error():
    error = RuntimeError("original operation failure")

    def operation():
        raise error

    recorder = _recorder()
    with pytest.raises(RuntimeError) as caught:
        recorder.observe("steel", operation)
    assert caught.value is error
    assert not isinstance(caught.value, MaterialTrialTimingError)
    assert recorder.call_count == recorder.exception_count == 1
    assert recorder.timing_error_count == 0


def test_material_recorder_rejects_wrong_type_at_section_and_beam_boundary():
    section = make_rectangular_stateful_rc_fiber_section(concrete_layer_count=2)
    with pytest.raises(ValueError, match="material_runtime"):
        section.integrate_with_material_runtime(
            (0.0, 0.0), section.initial_state(), material_runtime=object()
        )
    element = StatefulFiberBeam2D(section=section, integration_order=2)
    with pytest.raises(ValueError, match="material_runtime"):
        element.integrate([0.0] * 6, element.initial_state(), material_runtime=object())
