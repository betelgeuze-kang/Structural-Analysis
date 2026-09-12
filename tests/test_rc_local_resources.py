"""Cooperative budgets do not change a physical model or interrupt a trial state."""

from __future__ import annotations

import json

import pytest

from test_rc_control_local_research import (
    SOURCE, model as model, control_request as control_request,
    options as options, candidate,
)
from structural_analysis.benchmark import rc_control_reuse as reuse
from structural_analysis.benchmark import rc_control_cost_search as search
from structural_analysis.execution.local_runtime_doctor import inspect_local_runtime


def run(model, request, options, path, **kwargs):
    return search.run_rc_control_cost_search(
        model, (candidate("cheap", 0.35), candidate("expensive", 0.5)), request,
        session=reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research"),
        scope_id="research", output_directory=path, **options, **kwargs,
    )


def test_cancel_before_numerical_execution(model, control_request, options, tmp_path):
    result = run(model, control_request, options, tmp_path / "cancelled", stop_requested=lambda: True)
    assert result["status"] == "cancelled_between_models"
    assert result["new_model_evaluations"] == 0
    assert all(value is None for value in result["outcomes"].values())
    assert all(row["status"] == "not_run_after_cooperative_stop" for row in result["records"])


def test_stop_after_baseline_preserves_verified_result_and_unresolved_cheaper(model, control_request, options, tmp_path):
    calls = 0

    def stop():
        nonlocal calls
        calls += 1
        return calls > 1

    result = run(model, control_request, options, tmp_path / "partial", stop_requested=stop)
    assert result["status"] == "cancelled_between_models"
    assert result["new_model_evaluations"] == 1
    assert result["new_work"]["known_counters"]["attempted_step_count"] == 8
    assert result["outcomes"]["baseline"] is True
    assert result["outcomes"]["cheap"] is None
    assert result["cost_bound"]["pool_minimum_feasible_estimate"] is None


def test_small_wall_budget_stops_only_between_models(model, control_request, options, tmp_path):
    result = run(model, control_request, options, tmp_path / "time", maximum_wall_seconds=1e-12)
    assert result["status"] == "wall_budget_exhausted_between_models"
    assert result["new_model_evaluations"] == 0
    plan = json.loads((tmp_path / "time/plan.json").read_bytes())
    assert plan["wall_budget_scope"] == "cooperative_between_models_not_a_solver_timeout"


@pytest.mark.parametrize("limit", [True, 0, -1, float("nan"), float("inf"), 86401, "1"])
def test_invalid_wall_budget(model, control_request, options, tmp_path, limit):
    with pytest.raises(ValueError, match="budget"):
        run(model, control_request, options, tmp_path / "invalid", maximum_wall_seconds=limit)
    assert not (tmp_path / "invalid").exists()


def test_stop_callback_must_return_bool(model, control_request, options, tmp_path):
    with pytest.raises(ValueError, match="boolean"):
        run(model, control_request, options, tmp_path / "badstop", stop_requested=lambda: "false")


def test_doctor_no_device_never_reports_gpu_support(tmp_path):
    report = inspect_local_runtime(sysfs_root=tmp_path / "absent", dev_root=tmp_path)
    assert report["amd_display_devices"] == []
    assert report["qualified_gpu_solver_profiles"] == []
    assert report["hardware_kernel_executed"] is False
    assert report["gpu_performance_measured"] is False


def test_amd_sysfs_is_inventory_not_kernel_evidence(tmp_path):
    cards = tmp_path / "drm"
    device = cards / "card1/device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n")
    (device / "device").write_text("0x73bf\n")
    # Connector entries must not duplicate card-level devices.
    connector = cards / "card1-HDMI-A-1/device"
    connector.mkdir(parents=True)
    (connector / "vendor").write_text("0x1002")
    (tmp_path / "kfd").touch()
    report = inspect_local_runtime(sysfs_root=cards, dev_root=tmp_path)
    assert report["amd_display_devices"] == [{"card": "card1", "vendor_id": "0x1002", "device_id": "0x73bf"}]
    assert report["kfd_node_present"] is True
    assert report["hardware_kernel_executed"] is False
    assert report["gpu_numerical_parity_verified"] is False
    assert report["automatic_gpu_selection"] is False


def test_malformed_inventory_value_is_not_trusted(tmp_path):
    device = tmp_path / "card0/device"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002")
    (device / "device").write_bytes(b"x" * 300)
    report = inspect_local_runtime(sysfs_root=tmp_path, dev_root=tmp_path / "none")
    assert report["amd_display_devices"][0]["device_id"] is None
