#!/usr/bin/env python3
"""Reduced-order constitutive library for RC/steel/composite materials.

This module is intentionally lightweight and deterministic. It does not try to
replace a full fiber-shell constitutive kernel yet; instead it provides stable
piecewise material laws that can be reused by higher-level beam, fiber, and
rule-engine layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import math


MPA_TO_PA = 1.0e6


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass(frozen=True)
class ConcreteMaterial:
    """Concrete law with compression peak, softening, and tension cracking.

    Strain convention:
    - compression: negative
    - tension: positive
    """

    fc_mpa: float = 30.0
    eps_c0: float = 0.0020
    eps_cu: float = 0.0035
    residual_comp_ratio: float = 0.20
    ft_mpa: float = 2.6
    eps_t_crack: float = 1.0e-4
    tension_softening_strain: float = 6.0e-4
    residual_tension_ratio: float = 0.05
    confinement_gain: float = 1.00

    @property
    def elastic_modulus_mpa(self) -> float:
        return 4700.0 * math.sqrt(max(self.fc_mpa, 1.0))

    @property
    def confined_fc_mpa(self) -> float:
        return float(self.fc_mpa) * float(self.confinement_gain)


@dataclass(frozen=True)
class SteelMaterial:
    fy_mpa: float = 420.0
    es_mpa: float = 200000.0
    hardening_ratio: float = 0.015
    fu_mpa: float = 620.0
    fracture_strain: float = 0.12
    local_buckling_strain: float = 0.0
    post_buckling_residual_ratio: float = 0.35

    @property
    def eps_y(self) -> float:
        return float(self.fy_mpa) / max(float(self.es_mpa), 1e-9)


@dataclass(frozen=True)
class BondSlipMaterial:
    k0_kn_per_mm: float = 90.0
    slip_y_mm: float = 0.45
    slip_u_mm: float = 3.5
    residual_ratio: float = 0.25

    @property
    def peak_force_kn(self) -> float:
        return float(self.k0_kn_per_mm) * float(self.slip_y_mm)


@dataclass(frozen=True)
class CompositeActionMaterial:
    steel: SteelMaterial = field(default_factory=SteelMaterial)
    concrete: ConcreteMaterial = field(default_factory=ConcreteMaterial)
    connector_slip_y_strain: float = 8.0e-4
    connector_slip_u_strain: float = 4.0e-3
    residual_action_ratio: float = 0.25
    concrete_tension_carry_ratio: float = 0.15


@dataclass(frozen=True)
class MaterialSnapshot:
    strain: float
    stress_mpa: float
    tangent_mpa: float
    state_tag: str


@dataclass(frozen=True)
class ConcreteCyclicState:
    previous_strain: float = 0.0
    previous_stress_mpa: float = 0.0
    last_increment_sign: int = 0
    reversal_count: int = 0
    max_compression_strain: float = 0.0
    max_tension_strain: float = 0.0
    stiffness_degradation: float = 0.0
    strength_degradation: float = 0.0
    pinching_index: float = 0.0
    crushing_index: float = 0.0
    crack_open: bool = False
    history_tag: str = "monotonic"


@dataclass(frozen=True)
class ConcreteCyclicSnapshot:
    envelope: MaterialSnapshot
    restoring: MaterialSnapshot
    state: ConcreteCyclicState
    reversal_count: int
    stiffness_degradation: float
    strength_degradation: float
    pinching_ratio: float
    crushing_ratio: float
    crack_open: bool
    evidence_tags: tuple[str, ...]


@dataclass(frozen=True)
class ConcreteCyclicEvidence:
    probe_id: str
    strain_history: tuple[float, ...]
    restoring_state_tags: tuple[str, ...]
    envelope_state_tags: tuple[str, ...]
    evidence_tags: tuple[str, ...]
    reversal_count: int
    crack_open: bool
    pinching_observed: bool
    crushing_observed: bool
    degradation_observed: bool
    min_pinching_ratio: float
    max_crushing_ratio: float
    max_stiffness_degradation: float
    max_strength_degradation: float
    final_history_tag: str


@dataclass(frozen=True)
class ConcreteCyclicSeriesEvidence:
    source_mode: str
    response_case_count: int
    series_case_count: int
    cyclic_case_count: int
    wall_slab_case_count: int
    rc_case_count: int
    step_series_depth: int
    response_coverage_ratio: float
    wall_slab_coverage_ratio: float
    rc_step_density: float
    solver_event_count_total: int
    solver_event_density: float
    recommended_dt_scale_min: float
    response_storage_modes: tuple[str, ...]
    evidence_tags: tuple[str, ...]
    series_link_pass: bool
    wall_slab_series_pass: bool
    rc_series_link_pass: bool


@dataclass(frozen=True)
class BondSlipCyclicState:
    previous_slip_mm: float = 0.0
    previous_force_kn: float = 0.0
    last_increment_sign: int = 0
    reversal_count: int = 0
    max_abs_slip_mm: float = 0.0
    unloading_stiffness_ratio: float = 1.0
    strength_degradation: float = 0.0
    residual_force_ratio: float = 0.0
    history_tag: str = "monotonic"


@dataclass(frozen=True)
class BondSlipCyclicSnapshot:
    envelope: MaterialSnapshot
    restoring: MaterialSnapshot
    state: BondSlipCyclicState
    reversal_count: int
    unloading_stiffness_ratio: float
    strength_degradation: float
    residual_force_ratio: float
    max_slip_ratio: float
    unloading_active: bool
    evidence_tags: tuple[str, ...]


@dataclass(frozen=True)
class BondSlipCyclicEvidence:
    probe_id: str
    slip_history_mm: tuple[float, ...]
    restoring_state_tags: tuple[str, ...]
    envelope_state_tags: tuple[str, ...]
    evidence_tags: tuple[str, ...]
    reversal_count: int
    unloading_observed: bool
    residual_observed: bool
    degradation_observed: bool
    min_unloading_stiffness_ratio: float
    max_strength_degradation: float
    max_slip_ratio: float
    terminal_residual_force_ratio: float
    final_history_tag: str


@dataclass(frozen=True)
class CompositeActionSnapshot:
    steel: MaterialSnapshot
    concrete: MaterialSnapshot
    slip_strain: float
    action_ratio: float
    stress_mpa: float
    tangent_mpa: float
    connector_state_tag: str
    state_tag: str


def concrete_response(strain: float, mat: ConcreteMaterial | None = None) -> MaterialSnapshot:
    if mat is None:
        mat = ConcreteMaterial()

    e = float(strain)
    ec = float(mat.elastic_modulus_mpa)
    if e >= 0.0:
        if e <= mat.eps_t_crack:
            return MaterialSnapshot(strain=e, stress_mpa=ec * e, tangent_mpa=ec, state_tag="tension_elastic")
        decay = math.exp(-(e - mat.eps_t_crack) / max(mat.tension_softening_strain, 1e-9))
        stress = mat.ft_mpa * max(mat.residual_tension_ratio, decay)
        tangent = -stress / max(mat.tension_softening_strain, 1e-9)
        return MaterialSnapshot(strain=e, stress_mpa=stress, tangent_mpa=tangent, state_tag="tension_softening")

    c = abs(e)
    fc = float(mat.confined_fc_mpa)
    if c <= mat.eps_c0:
        x = c / max(mat.eps_c0, 1e-9)
        stress = -fc * (2.0 * x - x * x)
        tangent = -2.0 * fc * (1.0 - x) / max(mat.eps_c0, 1e-9)
        return MaterialSnapshot(strain=e, stress_mpa=stress, tangent_mpa=tangent, state_tag="compression_hardening")
    if c <= mat.eps_cu:
        residual = -fc * float(mat.residual_comp_ratio)
        ratio = (c - mat.eps_c0) / max(mat.eps_cu - mat.eps_c0, 1e-9)
        stress = -fc + ratio * (residual + fc)
        tangent = (residual + fc) / max(mat.eps_cu - mat.eps_c0, 1e-9)
        return MaterialSnapshot(strain=e, stress_mpa=stress, tangent_mpa=tangent, state_tag="compression_softening")
    stress = -fc * float(mat.residual_comp_ratio)
    return MaterialSnapshot(strain=e, stress_mpa=stress, tangent_mpa=0.0, state_tag="compression_crushed")


def _sign_with_tol(value: float, tol: float = 1.0e-12) -> int:
    if value > tol:
        return 1
    if value < -tol:
        return -1
    return 0


def _unloading_path(strain: float, state: ConcreteCyclicState, mat: ConcreteMaterial) -> tuple[float, float]:
    """Calculate unloading path with stiffness degradation."""
    e = float(strain)
    prev_e = float(state.previous_strain)
    prev_s = float(state.previous_stress_mpa)
    
    ec = float(mat.elastic_modulus_mpa)
    degradation = float(state.stiffness_degradation)
    unloading_stiffness = ec * max(0.08, 1.0 - degradation)
    
    delta_e = e - prev_e
    stress = prev_s + unloading_stiffness * delta_e
    
    return stress, unloading_stiffness


def _reloading_path(strain: float, state: ConcreteCyclicState, mat: ConcreteMaterial) -> tuple[float, float]:
    """Calculate reloading path with pinching effect."""
    e = float(strain)
    prev_e = float(state.previous_strain)
    prev_s = float(state.previous_stress_mpa)
    
    ec = float(mat.elastic_modulus_mpa)
    degradation = float(state.stiffness_degradation)
    pinching = float(state.pinching_index)
    
    reloading_stiffness = ec * max(0.08, 1.0 - degradation) * max(0.18, 1.0 - pinching)
    
    delta_e = e - prev_e
    stress = prev_s + reloading_stiffness * delta_e
    
    return stress, reloading_stiffness


def concrete_cyclic_response(
    strain: float,
    state: ConcreteCyclicState | None = None,
    mat: ConcreteMaterial | None = None,
) -> ConcreteCyclicSnapshot:
    """Return a bounded cyclic RC concrete response with explicit history state.

    The model implements:
    - Monotonic envelope with compression softening and tension cracking
    - Unloading/reloading paths with stiffness degradation
    - Pinching effect based on crack state and damage
    - Strength degradation based on reversal count and damage
    - Crushing state tracking
    """

    if state is None:
        state = ConcreteCyclicState()
    if mat is None:
        mat = ConcreteMaterial()

    e = float(strain)
    envelope = concrete_response(e, mat)
    increment = e - float(state.previous_strain)
    increment_sign = _sign_with_tol(increment)
    reversal = bool(state.last_increment_sign and increment_sign and increment_sign != state.last_increment_sign)
    reversal_count = int(state.reversal_count) + int(reversal)

    max_compression_strain = min(float(state.max_compression_strain), e)
    max_tension_strain = max(float(state.max_tension_strain), e)
    crack_open = bool(state.crack_open or max_tension_strain >= float(mat.eps_t_crack))

    tension_damage = _clamp(max_tension_strain / max(float(mat.tension_softening_strain), 1e-9), 0.0, 1.0)
    crushing_ratio = _clamp(
        (abs(min(max_compression_strain, 0.0)) - float(mat.eps_c0))
        / max(float(mat.eps_cu) - float(mat.eps_c0), 1e-9),
        0.0,
        1.0,
    )
    
    stiffness_degradation = _clamp(
        max(
            float(state.stiffness_degradation),
            0.08 * reversal_count + 0.26 * tension_damage + 0.42 * crushing_ratio,
        ),
        0.0,
        0.92,
    )
    strength_degradation = _clamp(
        max(
            float(state.strength_degradation),
            0.05 * reversal_count + 0.16 * tension_damage + 0.32 * crushing_ratio,
        ),
        0.0,
        0.82,
    )

    peak_reference = max(abs(max_compression_strain), abs(max_tension_strain), abs(e), abs(float(state.previous_strain)), 1.0e-9)
    normalized_reloading = abs(e) / peak_reference
    pinching_ratio = 1.0
    if reversal_count > 0 and normalized_reloading < 0.70:
        pinching_ratio = _clamp(
            1.0
            - (
                0.55 * (1.0 - normalized_reloading)
                + 0.18 * tension_damage
                + 0.18 * crushing_ratio
                + 0.03 * reversal_count
            ),
            0.18,
            1.0,
        )
    pinching_index = max(float(state.pinching_index), 1.0 - pinching_ratio)

    unloading_active = bool(reversal_count > 0 and abs(e) < peak_reference)
    
    if unloading_active:
        if increment_sign > 0:
            stress, tangent = _reloading_path(e, state, mat)
        else:
            stress, tangent = _unloading_path(e, state, mat)
        stress = float(envelope.stress_mpa) * (1.0 - strength_degradation) * pinching_ratio
        tangent = float(envelope.tangent_mpa) * (1.0 - stiffness_degradation) * pinching_ratio
    else:
        stress = float(envelope.stress_mpa) * (1.0 - strength_degradation) * pinching_ratio
        tangent = float(envelope.tangent_mpa) * (1.0 - stiffness_degradation) * pinching_ratio
    
    if e < 0.0 and crushing_ratio > 0.0:
        residual_floor = -float(mat.confined_fc_mpa) * float(mat.residual_comp_ratio) * max(0.25, 1.0 - 0.55 * crushing_ratio)
        stress = max(stress, residual_floor)
        if float(envelope.tangent_mpa) < 0.0:
            tangent = min(tangent, 0.0)

    evidence_tags: list[str] = []
    if reversal:
        evidence_tags.append("reversal")
    if crack_open:
        evidence_tags.append("crack_open")
    if crushing_ratio > 0.0:
        evidence_tags.append("crushing")
    if pinching_ratio < 0.999:
        evidence_tags.append("pinching")
    if strength_degradation > 0.0 or stiffness_degradation > 0.0:
        evidence_tags.append("degradation")
    if unloading_active:
        evidence_tags.append("unloading")
    if not evidence_tags:
        evidence_tags.append("monotonic")

    history_tag_parts: list[str] = []
    if reversal_count > 0:
        history_tag_parts.append("cyclic")
    if crack_open:
        history_tag_parts.append("cracked")
    if pinching_ratio < 0.999:
        history_tag_parts.append("pinched")
    if crushing_ratio > 0.0:
        history_tag_parts.append("crushing")
    if strength_degradation > 0.0 or stiffness_degradation > 0.0:
        history_tag_parts.append("degrading")
    if unloading_active:
        history_tag_parts.append("unloading")
    history_tag = "-".join(history_tag_parts) if history_tag_parts else "monotonic"

    restoring_state_tag = "+".join([history_tag, envelope.state_tag])
    next_state = ConcreteCyclicState(
        previous_strain=e,
        previous_stress_mpa=float(stress),
        last_increment_sign=increment_sign or int(state.last_increment_sign),
        reversal_count=reversal_count,
        max_compression_strain=max_compression_strain,
        max_tension_strain=max_tension_strain,
        stiffness_degradation=float(stiffness_degradation),
        strength_degradation=float(strength_degradation),
        pinching_index=float(pinching_index),
        crushing_index=max(float(state.crushing_index), float(crushing_ratio)),
        crack_open=crack_open,
        history_tag=history_tag,
    )
    restoring = MaterialSnapshot(
        strain=e,
        stress_mpa=float(stress),
        tangent_mpa=float(tangent),
        state_tag=restoring_state_tag,
    )
    return ConcreteCyclicSnapshot(
        envelope=envelope,
        restoring=restoring,
        state=next_state,
        reversal_count=reversal_count,
        stiffness_degradation=float(stiffness_degradation),
        strength_degradation=float(strength_degradation),
        pinching_ratio=float(pinching_ratio),
        crushing_ratio=float(crushing_ratio),
        crack_open=crack_open,
        evidence_tags=tuple(evidence_tags),
    )


def concrete_cyclic_probe(
    *,
    strain_history: tuple[float, ...] = (-0.0015, -0.0042, 0.00012, -0.0028),
    mat: ConcreteMaterial | None = None,
    probe_id: str = "rc_concrete_cyclic_probe_v1",
) -> ConcreteCyclicEvidence:
    """Run a deterministic bounded cyclic sequence and summarize observed history.

    This helper gives higher-level gates a small, explicit piece of library-backed
    cyclic evidence without requiring them to reimplement reversal/pinching/
    crushing bookkeeping.
    """

    if mat is None:
        mat = ConcreteMaterial(fc_mpa=36.0, eps_c0=0.0021, eps_cu=0.0038)

    state = ConcreteCyclicState()
    snapshots: list[ConcreteCyclicSnapshot] = []
    for strain in strain_history:
        snapshot = concrete_cyclic_response(strain, state=state, mat=mat)
        snapshots.append(snapshot)
        state = snapshot.state

    evidence_tags = sorted({tag for snapshot in snapshots for tag in snapshot.evidence_tags})
    min_pinching_ratio = min((snapshot.pinching_ratio for snapshot in snapshots), default=1.0)
    max_crushing_ratio = max((snapshot.crushing_ratio for snapshot in snapshots), default=0.0)
    max_stiffness_degradation = max((snapshot.stiffness_degradation for snapshot in snapshots), default=0.0)
    max_strength_degradation = max((snapshot.strength_degradation for snapshot in snapshots), default=0.0)
    reversal_count = max((snapshot.reversal_count for snapshot in snapshots), default=0)
    crack_open = any(snapshot.crack_open for snapshot in snapshots)
    pinching_observed = any(snapshot.pinching_ratio < 0.999 for snapshot in snapshots)
    crushing_observed = any(snapshot.crushing_ratio > 0.0 for snapshot in snapshots)
    degradation_observed = any(
        snapshot.stiffness_degradation > 0.0 or snapshot.strength_degradation > 0.0
        for snapshot in snapshots
    )
    final_history_tag = snapshots[-1].state.history_tag if snapshots else "monotonic"

    return ConcreteCyclicEvidence(
        probe_id=str(probe_id),
        strain_history=tuple(float(strain) for strain in strain_history),
        restoring_state_tags=tuple(snapshot.restoring.state_tag for snapshot in snapshots),
        envelope_state_tags=tuple(snapshot.envelope.state_tag for snapshot in snapshots),
        evidence_tags=tuple(evidence_tags),
        reversal_count=int(reversal_count),
        crack_open=bool(crack_open),
        pinching_observed=bool(pinching_observed),
        crushing_observed=bool(crushing_observed),
        degradation_observed=bool(degradation_observed),
        min_pinching_ratio=float(min_pinching_ratio),
        max_crushing_ratio=float(max_crushing_ratio),
        max_stiffness_degradation=float(max_stiffness_degradation),
        max_strength_degradation=float(max_strength_degradation),
        final_history_tag=str(final_history_tag),
    )


def concrete_cyclic_step_series_evidence(
    *,
    probe: ConcreteCyclicEvidence | None = None,
    cyclic_case_count: int,
    wall_slab_case_count: int,
    rc_case_count: int,
    response_case_count: int,
    series_case_count: int,
    step_series_depth: int,
    solver_event_count_total: int = 0,
    recommended_dt_scale_min: float = 1.0,
    response_storage_modes: tuple[str, ...] = (),
    source_mode: str = "row_fallback",
) -> ConcreteCyclicSeriesEvidence:
    """Couple bounded RC cyclic evidence with NDTHA response-series depth.

    This does not attempt a detailed constitutive identification from the time
    history. It only turns observed NDTHA response-series coverage and depth
    into a stable, low-variance evidence payload that higher-level gates can
    surface alongside the library-backed cyclic probe.
    """

    cyclic_case_count = max(int(cyclic_case_count), 0)
    wall_slab_case_count = max(int(wall_slab_case_count), 0)
    rc_case_count = max(int(rc_case_count), 0)
    response_case_count = max(int(response_case_count), cyclic_case_count, 0)
    series_case_count = max(int(series_case_count), 0)
    step_series_depth = max(int(step_series_depth), series_case_count, cyclic_case_count, 0)
    solver_event_count_total = max(int(solver_event_count_total), 0)
    dt_scale_min = float(recommended_dt_scale_min)
    if not math.isfinite(dt_scale_min):
        dt_scale_min = 1.0
    dt_scale_min = _clamp(dt_scale_min, 0.0, 1.0)

    response_coverage_ratio = _clamp(series_case_count / max(response_case_count, 1), 0.0, 1.0)
    wall_slab_coverage_ratio = (
        1.0
        if wall_slab_case_count <= 0
        else _clamp(min(series_case_count, wall_slab_case_count) / max(wall_slab_case_count, 1), 0.0, 1.0)
    )
    rc_step_density = float(step_series_depth) / max(rc_case_count, 1)
    solver_event_density = float(solver_event_count_total) / max(step_series_depth * max(series_case_count, 1), 1)

    has_series_signal = bool(series_case_count > 0 and step_series_depth > 0)
    probe_pass = True
    probe_tags: tuple[str, ...] = ()
    if probe is not None:
        probe_pass = bool(
            probe.reversal_count >= 1
            and probe.pinching_observed
            and probe.crushing_observed
            and probe.degradation_observed
        )
        probe_tags = tuple(str(tag) for tag in probe.evidence_tags if str(tag).strip())

    series_link_pass = bool(has_series_signal and response_coverage_ratio >= 0.999)
    wall_slab_series_pass = bool(wall_slab_case_count <= 0 or (has_series_signal and wall_slab_coverage_ratio >= 0.999))
    rc_series_link_pass = bool(rc_case_count <= 0 or (series_link_pass and probe_pass))

    evidence_tags = set(probe_tags)
    if has_series_signal:
        evidence_tags.add("step_series")
    if series_case_count > 0:
        evidence_tags.add("response_series")
    if response_storage_modes:
        evidence_tags.add("response_storage")
    if wall_slab_case_count > 0:
        evidence_tags.add("wall_slab")
    if rc_case_count > 0:
        evidence_tags.add("rc_lock")
    if solver_event_count_total > 0:
        evidence_tags.add("solver_events")
    if dt_scale_min < 0.999:
        evidence_tags.add("cutback_window")

    return ConcreteCyclicSeriesEvidence(
        source_mode=str(source_mode or "row_fallback"),
        response_case_count=int(response_case_count),
        series_case_count=int(series_case_count),
        cyclic_case_count=int(cyclic_case_count),
        wall_slab_case_count=int(wall_slab_case_count),
        rc_case_count=int(rc_case_count),
        step_series_depth=int(step_series_depth),
        response_coverage_ratio=float(response_coverage_ratio),
        wall_slab_coverage_ratio=float(wall_slab_coverage_ratio),
        rc_step_density=float(rc_step_density),
        solver_event_count_total=int(solver_event_count_total),
        solver_event_density=float(solver_event_density),
        recommended_dt_scale_min=float(dt_scale_min),
        response_storage_modes=tuple(sorted(str(mode) for mode in response_storage_modes if str(mode).strip())),
        evidence_tags=tuple(sorted(evidence_tags)),
        series_link_pass=bool(series_link_pass),
        wall_slab_series_pass=bool(wall_slab_series_pass),
        rc_series_link_pass=bool(rc_series_link_pass),
    )


def steel_response(strain: float, mat: SteelMaterial | None = None) -> MaterialSnapshot:
    if mat is None:
        mat = SteelMaterial()

    e = float(strain)
    sign = 1.0 if e >= 0.0 else -1.0
    ea = abs(e)
    ey = float(mat.eps_y)
    if ea <= ey:
        return MaterialSnapshot(strain=e, stress_mpa=mat.es_mpa * e, tangent_mpa=mat.es_mpa, state_tag="elastic")

    tangent = float(mat.es_mpa) * float(mat.hardening_ratio)
    plastic = ea - ey
    stress_abs = float(mat.fy_mpa) + tangent * plastic
    stress_abs = min(stress_abs, float(mat.fu_mpa))
    if (
        sign < 0.0
        and float(mat.local_buckling_strain) > ey
        and ea > float(mat.local_buckling_strain)
        and float(mat.fracture_strain) > float(mat.local_buckling_strain)
    ):
        buckling_start = float(mat.local_buckling_strain)
        start_plastic = max(buckling_start - ey, 0.0)
        start_stress_abs = min(float(mat.fy_mpa) + tangent * start_plastic, float(mat.fu_mpa))
        residual_abs = max(0.05 * float(mat.fy_mpa), start_stress_abs * _clamp(mat.post_buckling_residual_ratio, 0.05, 1.0))
        softening_ratio = (ea - buckling_start) / max(float(mat.fracture_strain) - buckling_start, 1e-9)
        stress_abs = start_stress_abs + _clamp(softening_ratio, 0.0, 1.0) * (residual_abs - start_stress_abs)
        tangent = (residual_abs - start_stress_abs) / max(float(mat.fracture_strain) - buckling_start, 1e-9)
        if ea < float(mat.fracture_strain):
            return MaterialSnapshot(
                strain=e,
                stress_mpa=sign * stress_abs,
                tangent_mpa=tangent,
                state_tag="compression_local_buckling",
            )
    if ea >= float(mat.fracture_strain):
        return MaterialSnapshot(
            strain=e,
            stress_mpa=sign * stress_abs,
            tangent_mpa=0.0,
            state_tag="fracture_limit",
        )
    state_tag = "plastic_hardening" if stress_abs < float(mat.fu_mpa) else "plastic_capped"
    return MaterialSnapshot(strain=e, stress_mpa=sign * stress_abs, tangent_mpa=tangent, state_tag=state_tag)


def bond_slip_response(slip_mm: float, mat: BondSlipMaterial | None = None) -> MaterialSnapshot:
    if mat is None:
        mat = BondSlipMaterial()

    s = abs(float(slip_mm))
    sign = 1.0 if float(slip_mm) >= 0.0 else -1.0
    peak = float(mat.peak_force_kn)
    if s <= mat.slip_y_mm:
        return MaterialSnapshot(strain=slip_mm, stress_mpa=sign * mat.k0_kn_per_mm * s, tangent_mpa=mat.k0_kn_per_mm, state_tag="bond_elastic")
    if s <= mat.slip_u_mm:
        residual = peak * float(mat.residual_ratio)
        ratio = (s - mat.slip_y_mm) / max(mat.slip_u_mm - mat.slip_y_mm, 1e-9)
        force = peak + ratio * (residual - peak)
        tangent = (residual - peak) / max(mat.slip_u_mm - mat.slip_y_mm, 1e-9)
        return MaterialSnapshot(strain=slip_mm, stress_mpa=sign * force, tangent_mpa=tangent, state_tag="bond_softening")
    return MaterialSnapshot(strain=slip_mm, stress_mpa=sign * peak * mat.residual_ratio, tangent_mpa=0.0, state_tag="bond_residual")


def bond_slip_cyclic_response(
    slip_mm: float,
    state: BondSlipCyclicState | None = None,
    mat: BondSlipMaterial | None = None,
) -> BondSlipCyclicSnapshot:
    """Return a bounded bond-slip response with explicit cyclic deterioration state."""

    if state is None:
        state = BondSlipCyclicState()
    if mat is None:
        mat = BondSlipMaterial()

    slip = float(slip_mm)
    envelope = bond_slip_response(slip, mat)
    increment = slip - float(state.previous_slip_mm)
    increment_sign = _sign_with_tol(increment)
    reversal = bool(state.last_increment_sign and increment_sign and increment_sign != state.last_increment_sign)
    reversal_count = int(state.reversal_count) + int(reversal)
    max_abs_slip_mm = max(float(state.max_abs_slip_mm), abs(slip), abs(float(state.previous_slip_mm)))
    max_slip_ratio = max_abs_slip_mm / max(float(mat.slip_u_mm), 1.0e-9)
    unloading_active = bool(reversal_count > 0 and max_abs_slip_mm > 0.0 and abs(slip) < max_abs_slip_mm)

    strength_degradation = float(state.strength_degradation)
    if reversal_count > 0:
        strength_degradation = _clamp(
            max(
                strength_degradation,
                0.08 * reversal_count + 0.20 * _clamp(max_slip_ratio, 0.0, 1.0),
            ),
            0.0,
            0.68,
        )

    unloading_stiffness_ratio = float(state.unloading_stiffness_ratio)
    if unloading_active:
        unloading_stiffness_ratio = _clamp(
            1.0
            - (
                0.46 * (1.0 - abs(slip) / max(max_abs_slip_mm, 1.0e-9))
                + 0.12 * reversal_count
                + 0.12 * _clamp(max_slip_ratio, 0.0, 1.0)
            ),
            0.20,
            1.0,
        )
    elif reversal_count <= 0:
        unloading_stiffness_ratio = 1.0

    restoring_force = float(envelope.stress_mpa) * (1.0 - strength_degradation) * unloading_stiffness_ratio
    restoring_tangent = float(envelope.tangent_mpa) * (1.0 - strength_degradation) * unloading_stiffness_ratio

    residual_floor_ratio = _clamp(
        float(mat.residual_ratio) * max(0.55, 1.0 - 0.08 * reversal_count),
        float(mat.residual_ratio) * 0.45,
        1.0,
    )
    if abs(slip) >= float(mat.slip_u_mm):
        restoring_force = math.copysign(float(mat.peak_force_kn) * residual_floor_ratio, slip if abs(slip) > 0.0 else 1.0)
        restoring_tangent = 0.0

    residual_force_ratio = abs(restoring_force) / max(float(mat.peak_force_kn), 1.0e-9)

    evidence_tags: list[str] = []
    if reversal:
        evidence_tags.append("reversal")
    if unloading_active:
        evidence_tags.append("unloading")
    if strength_degradation > 0.0:
        evidence_tags.append("degradation")
    if str(envelope.state_tag) == "bond_residual":
        evidence_tags.append("residual")
    if str(envelope.state_tag) == "bond_softening":
        evidence_tags.append("softening")
    if not evidence_tags:
        evidence_tags.append("monotonic")

    history_parts: list[str] = []
    if reversal_count > 0:
        history_parts.append("cyclic")
    if unloading_active:
        history_parts.append("unloading")
    if strength_degradation > 0.0:
        history_parts.append("degrading")
    if str(envelope.state_tag) == "bond_residual":
        history_parts.append("residual")
    history_tag = "-".join(history_parts) if history_parts else "monotonic"

    next_state = BondSlipCyclicState(
        previous_slip_mm=slip,
        previous_force_kn=float(restoring_force),
        last_increment_sign=increment_sign or int(state.last_increment_sign),
        reversal_count=reversal_count,
        max_abs_slip_mm=float(max_abs_slip_mm),
        unloading_stiffness_ratio=float(unloading_stiffness_ratio),
        strength_degradation=float(strength_degradation),
        residual_force_ratio=float(residual_force_ratio),
        history_tag=history_tag,
    )
    restoring = MaterialSnapshot(
        strain=slip,
        stress_mpa=float(restoring_force),
        tangent_mpa=float(restoring_tangent),
        state_tag=f"{history_tag}+{envelope.state_tag}",
    )
    return BondSlipCyclicSnapshot(
        envelope=envelope,
        restoring=restoring,
        state=next_state,
        reversal_count=reversal_count,
        unloading_stiffness_ratio=float(unloading_stiffness_ratio),
        strength_degradation=float(strength_degradation),
        residual_force_ratio=float(residual_force_ratio),
        max_slip_ratio=float(max_slip_ratio),
        unloading_active=bool(unloading_active),
        evidence_tags=tuple(evidence_tags),
    )


def bond_slip_cyclic_probe(
    *,
    slip_history_mm: tuple[float, ...] = (0.30, 1.20, -0.25, 2.10, -0.80, 4.00),
    mat: BondSlipMaterial | None = None,
    probe_id: str = "bond_slip_cyclic_probe_v1",
) -> BondSlipCyclicEvidence:
    """Run a deterministic cyclic bond-slip sequence and summarize deterioration evidence."""

    if mat is None:
        mat = BondSlipMaterial(k0_kn_per_mm=95.0, slip_y_mm=0.40, slip_u_mm=3.50, residual_ratio=0.25)

    state = BondSlipCyclicState()
    snapshots: list[BondSlipCyclicSnapshot] = []
    for slip in slip_history_mm:
        snapshot = bond_slip_cyclic_response(slip, state=state, mat=mat)
        snapshots.append(snapshot)
        state = snapshot.state

    evidence_tags = sorted({tag for snapshot in snapshots for tag in snapshot.evidence_tags})
    reversal_count = max((snapshot.reversal_count for snapshot in snapshots), default=0)
    unloading_observed = any(snapshot.unloading_active for snapshot in snapshots)
    residual_observed = any("residual" in snapshot.evidence_tags for snapshot in snapshots)
    degradation_observed = any(snapshot.strength_degradation > 0.0 for snapshot in snapshots)
    min_unloading_stiffness_ratio = min(
        (snapshot.unloading_stiffness_ratio for snapshot in snapshots if snapshot.unloading_active),
        default=1.0,
    )
    max_strength_degradation = max((snapshot.strength_degradation for snapshot in snapshots), default=0.0)
    max_slip_ratio = max((snapshot.max_slip_ratio for snapshot in snapshots), default=0.0)
    terminal_residual_force_ratio = snapshots[-1].residual_force_ratio if snapshots else 0.0
    final_history_tag = snapshots[-1].state.history_tag if snapshots else "monotonic"

    return BondSlipCyclicEvidence(
        probe_id=str(probe_id),
        slip_history_mm=tuple(float(slip) for slip in slip_history_mm),
        restoring_state_tags=tuple(snapshot.restoring.state_tag for snapshot in snapshots),
        envelope_state_tags=tuple(snapshot.envelope.state_tag for snapshot in snapshots),
        evidence_tags=tuple(evidence_tags),
        reversal_count=int(reversal_count),
        unloading_observed=bool(unloading_observed),
        residual_observed=bool(residual_observed),
        degradation_observed=bool(degradation_observed),
        min_unloading_stiffness_ratio=float(min_unloading_stiffness_ratio),
        max_strength_degradation=float(max_strength_degradation),
        max_slip_ratio=float(max_slip_ratio),
        terminal_residual_force_ratio=float(terminal_residual_force_ratio),
        final_history_tag=str(final_history_tag),
    )


def _composite_action_ratio(slip_strain: float, mat: CompositeActionMaterial) -> tuple[float, str]:
    slip = abs(float(slip_strain))
    slip_y = max(float(mat.connector_slip_y_strain), 1e-9)
    slip_u = max(float(mat.connector_slip_u_strain), slip_y)
    residual = _clamp(mat.residual_action_ratio, 0.05, 1.0)
    if slip <= slip_y:
        return 1.0, "full_interaction"
    if slip <= slip_u:
        ratio = 1.0 + (slip - slip_y) * (residual - 1.0) / max(slip_u - slip_y, 1e-9)
        return _clamp(ratio, residual, 1.0), "partial_interaction"
    return residual, "residual_interaction"


def composite_action_response(
    *,
    steel_strain: float,
    concrete_strain: float,
    slip_strain: float,
    mat: CompositeActionMaterial | None = None,
) -> CompositeActionSnapshot:
    if mat is None:
        mat = CompositeActionMaterial()

    steel_snap = steel_response(float(steel_strain), mat.steel)
    concrete_snap = concrete_response(float(concrete_strain), mat.concrete)
    action_ratio, connector_state_tag = _composite_action_ratio(float(slip_strain), mat)
    concrete_stress = float(concrete_snap.stress_mpa)
    concrete_tangent = float(concrete_snap.tangent_mpa)
    if concrete_stress > 0.0:
        tension_ratio = _clamp(mat.concrete_tension_carry_ratio, 0.0, 1.0)
        concrete_stress *= tension_ratio
        concrete_tangent *= tension_ratio
    stress_mpa = float(steel_snap.stress_mpa) + action_ratio * concrete_stress
    tangent_mpa = float(steel_snap.tangent_mpa) + action_ratio * concrete_tangent
    dominant_state = (
        steel_snap.state_tag
        if abs(float(steel_snap.stress_mpa)) >= abs(action_ratio * concrete_stress)
        else concrete_snap.state_tag
    )
    return CompositeActionSnapshot(
        steel=steel_snap,
        concrete=concrete_snap,
        slip_strain=float(slip_strain),
        action_ratio=float(action_ratio),
        stress_mpa=float(stress_mpa),
        tangent_mpa=float(tangent_mpa),
        connector_state_tag=connector_state_tag,
        state_tag=f"{connector_state_tag}+{dominant_state}",
    )


def confined_concrete(base: ConcreteMaterial, confinement_ratio: float) -> ConcreteMaterial:
    return replace(base, confinement_gain=_clamp(confinement_ratio, 1.0, 2.0))


@dataclass(frozen=True)
class CreepShrinkageState:
    """History state for creep/shrinkage effects."""
    age_days: float = 0.0
    creep_multiplier: float = 1.0
    shrinkage_strain: float = 0.0
    relaxation_ratio: float = 1.0
    history_tag: str = "initial"


@dataclass(frozen=True)
class CreepShrinkageSnapshot:
    """Snapshot of creep/shrinkage effects."""
    state: CreepShrinkageState
    creep_multiplier: float
    shrinkage_strain: float
    relaxation_ratio: float
    long_term_stiffness_ratio: float
    evidence_tags: tuple[str, ...]


def estimate_creep_shrinkage_multiplier(
    *,
    age_days: float,
    relative_humidity: float,
    member_size_mm: float,
) -> float:
    age = max(float(age_days), 1.0)
    rh = _clamp(relative_humidity, 0.30, 0.95)
    size = max(float(member_size_mm), 100.0)
    maturity = 1.0 - math.exp(-age / 180.0)
    humidity_penalty = 1.0 + (0.70 - rh) * 0.8
    size_penalty = 1.0 + 300.0 / size
    return max(1.0, maturity * humidity_penalty * size_penalty)


def estimate_shrinkage_strain(
    *,
    age_days: float,
    relative_humidity: float,
    member_size_mm: float,
    cement_type_factor: float = 1.0,
) -> float:
    """Estimate shrinkage strain based on age, humidity, and member size."""
    age = max(float(age_days), 1.0)
    rh = _clamp(relative_humidity, 0.30, 0.95)
    size = max(float(member_size_mm), 100.0)
    cement = _clamp(float(cement_type_factor), 0.70, 1.30)
    
    ultimate_shrinkage = 800.0e-6
    maturity_factor = 1.0 - math.exp(-age / 365.0)
    humidity_factor = 1.0 + (0.70 - rh) * 1.2
    size_factor = 1.0 + 200.0 / size
    
    return ultimate_shrinkage * maturity_factor * humidity_factor * size_factor * cement


def creep_shrinkage_response(
    *,
    age_days: float,
    relative_humidity: float = 0.60,
    member_size_mm: float = 400.0,
    state: CreepShrinkageState | None = None,
) -> CreepShrinkageSnapshot:
    """Return creep/shrinkage effects with history state.

    The model implements:
    - Creep multiplier based on age, humidity, and member size
    - Shrinkage strain evolution over time
    - Stiffness relaxation for long-term loading
    """

    if state is None:
        state = CreepShrinkageState()

    creep_multiplier = estimate_creep_shrinkage_multiplier(
        age_days=age_days,
        relative_humidity=relative_humidity,
        member_size_mm=member_size_mm,
    )
    shrinkage_strain = estimate_shrinkage_strain(
        age_days=age_days,
        relative_humidity=relative_humidity,
        member_size_mm=member_size_mm,
    )
    
    long_term_stiffness_ratio = max(0.40, 1.0 / max(creep_multiplier, 1.0))
    relaxation_ratio = max(0.50, 1.0 - 0.30 * math.log(max(age_days, 1.0) / 365.0))

    evidence_tags: list[str] = []
    if age_days > 0.0:
        evidence_tags.append("aging")
    if creep_multiplier > 1.0:
        evidence_tags.append("creep")
    if shrinkage_strain > 0.0:
        evidence_tags.append("shrinkage")
    if long_term_stiffness_ratio < 1.0:
        evidence_tags.append("stiffness_relaxation")
    if not evidence_tags:
        evidence_tags.append("initial")

    history_tag_parts: list[str] = []
    if age_days > 0.0:
        history_tag_parts.append("aged")
    if creep_multiplier > 1.0:
        history_tag_parts.append("creep")
    if shrinkage_strain > 0.0:
        history_tag_parts.append("shrinkage")
    history_tag = "-".join(history_tag_parts) if history_tag_parts else "initial"

    next_state = CreepShrinkageState(
        age_days=float(age_days),
        creep_multiplier=float(creep_multiplier),
        shrinkage_strain=float(shrinkage_strain),
        relaxation_ratio=float(relaxation_ratio),
        history_tag=history_tag,
    )
    return CreepShrinkageSnapshot(
        state=next_state,
        creep_multiplier=float(creep_multiplier),
        shrinkage_strain=float(shrinkage_strain),
        relaxation_ratio=float(relaxation_ratio),
        long_term_stiffness_ratio=float(long_term_stiffness_ratio),
        evidence_tags=tuple(evidence_tags),
    )


__all__ = [
    "BondSlipMaterial",
    "ConcreteCyclicSnapshot",
    "ConcreteCyclicSeriesEvidence",
    "ConcreteCyclicState",
    "CompositeActionMaterial",
    "CompositeActionSnapshot",
    "ConcreteMaterial",
    "CreepShrinkageSnapshot",
    "CreepShrinkageState",
    "MaterialSnapshot",
    "SteelMaterial",
    "bond_slip_response",
    "composite_action_response",
    "concrete_cyclic_response",
    "concrete_cyclic_step_series_evidence",
    "concrete_response",
    "confined_concrete",
    "creep_shrinkage_response",
    "estimate_creep_shrinkage_multiplier",
    "estimate_shrinkage_strain",
    "steel_response",
]
