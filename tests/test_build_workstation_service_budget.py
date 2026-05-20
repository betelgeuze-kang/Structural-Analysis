from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_workstation_service_budget.py"
SPEC = importlib.util.spec_from_file_location("build_workstation_service_budget", SCRIPT_PATH)
assert SPEC is not None
build_workstation_service_budget = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_workstation_service_budget)


def test_service_budget_tier_classification() -> None:
    assert build_workstation_service_budget.classify_project_size(nodes=1000, elements=2000) == "small"
    assert build_workstation_service_budget.classify_project_size(nodes=70000, elements=140000) == "medium"
    assert build_workstation_service_budget.classify_project_size(nodes=100000, elements=250000) == "large"
    assert build_workstation_service_budget.classify_project_size(nodes=200000, elements=400000) == "oversize"


def test_service_budget_uses_hardware_and_viewer_probe() -> None:
    payload = build_workstation_service_budget.build_workstation_service_budget(
        hardware_payload={
            "contract_pass": True,
            "hardware_profile": {"memory": {"total_gib": 31.1}},
        },
        viewer_probe_payload={
            "contract_pass": True,
            "summary_line": "viewer pass",
            "budgets": {"max_ready_ms": 60000, "min_average_fps": 5},
            "probe": {"readyMs": 4443, "rafSample": {"averageFps": 38.9}},
        },
        visual_payload={"contract_pass": True},
    )

    assert payload["schema_version"] == "workstation-service-budget.v1"
    assert payload["contract_pass"] is True
    assert payload["performance_budget"]["viewer_ready_ms"] == 4443
    assert payload["performance_budget"]["viewer_average_fps"] == 38.9
    assert payload["project_size_tiers"][0]["tier"] == "small"
    assert "customer-device FPS" in payload["claim_boundary"]


def test_service_budget_blocks_missing_viewer_probe() -> None:
    payload = build_workstation_service_budget.build_workstation_service_budget(
        hardware_payload={
            "contract_pass": True,
            "hardware_profile": {"memory": {"total_gib": 31.1}},
        },
        viewer_probe_payload={},
        visual_payload={},
    )

    assert payload["contract_pass"] is False
    assert "viewer_browser_performance_probe_missing" in payload["blockers"]
