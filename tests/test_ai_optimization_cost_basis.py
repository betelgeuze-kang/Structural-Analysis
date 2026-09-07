"""Price changes must flow through quantity estimates and candidate ranking."""
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from implementation.phase1.cost_model import (
    CostModelCalibrator, MemberCostInput, RegionalPriceTable, build_price_provenance,
)
from implementation.phase1.design_optimization_env import aggregate_group_state, project_group_cost_proxy


def test_package_import_does_not_depend_on_test_path_injection() -> None:
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, "-c", "from implementation.phase1.design_optimization_env import aggregate_group_state"],
                          cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def dataset() -> dict[str, np.ndarray]:
    return {
        "group_index_per_member": np.array([0, 0, 1]),
        "unique_group_ids": np.array(["G0", "G1"]),
        "rebar_ratio": np.array([0.02, 0.03, 0.02]),
        "max_dcr": np.array([0.5, 0.5, 0.5]),
        "congestion_index": np.zeros(3),
        "lap_splice_ratio": np.zeros(3),
        "anchorage_complexity": np.zeros(3),
        "detailing_violation_ratio": np.zeros(3),
        "volume_m3": np.array([1.0, 2.0, 1.0]),
        "steel_mass_kg": np.array([10.0, 20.0, 10.0]),
        "member_types": np.array(["beam", "beam", "column"]),
        "drift_envelope_max_pct": np.ones(3),
        "residual_drift_pct_max_abs": np.zeros(3),
        "action_mask": np.ones((2, 2), dtype=bool),
    }


def members(data: dict[str, np.ndarray]) -> list[MemberCostInput]:
    return [MemberCostInput(str(i), str(data["member_types"][i]), 3.0,
                            float(data["volume_m3"][i]), float(data["steel_mass_kg"][i]),
                            float(data["rebar_ratio"][i])) for i in range(3)]


@pytest.mark.parametrize("rebar_price", [1.3, 5.2])
def test_group_material_cost_matches_member_estimate_and_candidate_repricing(rebar_price: float) -> None:
    price = RegionalPriceTable(concrete_per_m3=150.0, rebar_per_kg=rebar_price)
    data = dataset()
    state = aggregate_group_state(data, price_table=price)
    model = CostModelCalibrator(price)
    costs = [model.estimate_member_cost(m) for m in members(data)]
    material = [c.concrete_cost + c.steel_cost + c.rebar_cost for c in costs]
    np.testing.assert_allclose(state["group_cost_proxy"], [sum(material[:2]), material[2]])

    # The candidate uses the same price table and declared proportional changes.
    next_rebar = state["rebar_ratio"] * 0.8
    next_thickness = state["thickness_scale"] * 0.9
    projected = project_group_cost_proxy(state=state, rebar_ratio=next_rebar, thickness_scale=next_thickness)
    changed = [replace(m, volume_m3=m.volume_m3 * 0.9, steel_mass_kg=m.steel_mass_kg * 0.9,
                       rebar_ratio=m.rebar_ratio * 0.8) for m in members(data)]
    actual = model.estimate_project_cost(changed)
    assert projected.sum() == pytest.approx(actual["construction_cost"] - actual["labor_cost"])


def test_rebar_price_changes_savings_and_detail_quality_does_not_change_material_cost() -> None:
    savings = []
    for rebar_price in (1.3, 2.6):
        state = aggregate_group_state(dataset(), price_table=RegionalPriceTable(rebar_per_kg=rebar_price))
        next_cost = project_group_cost_proxy(state=state, rebar_ratio=state["rebar_ratio"] * 0.8)
        savings.append(float((state["group_cost_proxy"] - next_cost).sum()))
        unchanged = project_group_cost_proxy(state=state, rebar_ratio=state["rebar_ratio"],
                                             detailing_quality=state["detailing_quality"] * 0.5)
        np.testing.assert_allclose(unchanged, state["group_cost_proxy"])
    assert savings[1] == pytest.approx(2.0 * savings[0])


def test_repricing_is_path_independent_with_fixed_quantity_basis() -> None:
    state = aggregate_group_state(dataset())
    halfway = {key: value.copy() for key, value in state.items()}
    halfway["group_cost_proxy"] = project_group_cost_proxy(state=state, rebar_ratio=state["rebar_ratio"] * 0.9)
    halfway["rebar_ratio"] *= 0.9
    target = state["rebar_ratio"] * 0.8
    np.testing.assert_allclose(project_group_cost_proxy(state=halfway, rebar_ratio=target),
                               project_group_cost_proxy(state=state, rebar_ratio=target))


def test_zero_initial_reinforcement_can_be_estimated_without_division_by_zero() -> None:
    data = dataset()
    data["rebar_ratio"][:] = 0.0
    state = aggregate_group_state(data)
    np.testing.assert_allclose(project_group_cost_proxy(state=state, rebar_ratio=state["rebar_ratio"]),
                               state["group_cost_proxy"])
    projected = project_group_cost_proxy(state=state, rebar_ratio=np.full(2, 0.02))
    assert projected.sum() - state["group_cost_proxy"].sum() == pytest.approx(4.0 * 0.02 * 7850.0 * 1.3)


def test_construction_estimate_excludes_uncalibrated_penalties() -> None:
    model = CostModelCalibrator()
    ordinary = members(dataset())[0]
    detailed = replace(ordinary, congestion_index=0.8, detailing_violation_ratio=1.0)
    a, b = model.estimate_member_cost(ordinary), model.estimate_member_cost(detailed)
    assert b.construction_cost == a.construction_cost
    assert b.optimization_penalty > a.optimization_penalty
    assert b.total_cost == b.construction_cost + b.optimization_penalty
    project = model.estimate_project_cost([detailed])
    assert project["total_cost"] == pytest.approx(project["construction_cost"] + project["optimization_penalty"])


def test_price_identity_and_unpriced_monetary_boundary() -> None:
    default = build_price_provenance()
    assert default["currency"] is None
    assert default["value_kind"] == "uncalibrated_cost_index"
    assert default["verified_construction_savings"] is False
    declared = RegionalPriceTable(currency="KRW", source="synthetic test, not a quote", as_of="2026-09-07", table_version="test-v1")
    first = build_price_provenance(declared)
    second = build_price_provenance(replace(declared, rebar_per_kg=99.0))
    assert first["basis_sha256"] != second["basis_sha256"]
    assert first["verified_construction_savings"] is False


@pytest.mark.parametrize("changes", [{"rebar_per_kg": float("nan")}, {"steel_per_kg": -1.0},
                                     {"currency": "KRW"}, {"currency": "won"}, {"as_of": "2025-01-01"}])
def test_invalid_price_basis_is_rejected(changes: dict) -> None:
    with pytest.raises(ValueError):
        build_price_provenance(RegionalPriceTable(**changes))


def test_partial_quantity_basis_cannot_fall_back_to_legacy_proxy() -> None:
    state = aggregate_group_state(dataset())
    del state["cost_reference_steel"]
    with pytest.raises(ValueError, match="incomplete_cost_quantity_basis"):
        project_group_cost_proxy(state=state, rebar_ratio=state["rebar_ratio"])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_invalid_member_quantity_is_rejected(bad: float) -> None:
    data = dataset()
    data["volume_m3"][0] = bad
    with pytest.raises(ValueError, match="invalid_cost_member_quantities"):
        aggregate_group_state(data)
