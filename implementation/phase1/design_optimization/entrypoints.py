"""Stable entrypoint metadata for bounded refactor and reporting."""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import (
    ABLATION_REPORT_JSON,
    BUDGETED_REPORT_JSON,
    COST_REDUCTION_REPORT_JSON,
    DATASET_REPORT_JSON,
    OBJECTIVE_PROFILE_REPORT_JSON,
    SOLVER_LOOP_LONG_REPORT_JSON,
    SOLVER_LOOP_REPORT_JSON,
)


@dataclass(frozen=True)
class Entrypoint:
    name: str
    script: str
    primary_report: str
    purpose: str
    group: str
    group_label: str


ENTRYPOINTS: dict[str, Entrypoint] = {
    "dataset": Entrypoint(
        name="dataset",
        script="implementation/phase1/generate_design_optimization_dataset.py",
        primary_report=DATASET_REPORT_JSON,
        purpose="Generate grouped optimization dataset schema v2.",
        group="dataset",
        group_label="Dataset",
    ),
    "solver_loop": Entrypoint(
        name="solver_loop",
        script="implementation/phase1/run_design_optimization_solver_loop.py",
        primary_report=SOLVER_LOOP_REPORT_JSON,
        purpose="Stage A feasibility repair runner.",
        group="stage_a",
        group_label="Stage A",
    ),
    "solver_loop_long": Entrypoint(
        name="solver_loop_long",
        script="implementation/phase1/run_design_optimization_solver_loop_long.py",
        primary_report=SOLVER_LOOP_LONG_REPORT_JSON,
        purpose="Long-budget feasibility repair reference runner.",
        group="stage_a",
        group_label="Stage A",
    ),
    "budgeted": Entrypoint(
        name="budgeted",
        script="implementation/phase1/run_design_optimization_budgeted.py",
        primary_report=BUDGETED_REPORT_JSON,
        purpose="Unified Stage A/B/C budget runner.",
        group="stage_abc",
        group_label="Stage A/B/C",
    ),
    "cost_reduction": Entrypoint(
        name="cost_reduction",
        script="implementation/phase1/run_design_optimization_cost_reduction.py",
        primary_report=COST_REDUCTION_REPORT_JSON,
        purpose="Stage B cost recovery and explain output.",
        group="stage_b",
        group_label="Stage B",
    ),
    "ablation": Entrypoint(
        name="ablation",
        script="implementation/phase1/run_design_optimization_ablation.py",
        primary_report=ABLATION_REPORT_JSON,
        purpose="Action-family ablation and bias checks.",
        group="ablation",
        group_label="Ablation",
    ),
    "objective_profile": Entrypoint(
        name="objective_profile",
        script="implementation/phase1/generate_design_objective_calibration.py",
        primary_report=OBJECTIVE_PROFILE_REPORT_JSON,
        purpose="Objective calibration base + profile overlay.",
        group="profile",
        group_label="Profile",
    ),
}


def entrypoint_rows() -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "script": item.script,
            "primary_report": item.primary_report,
            "purpose": item.purpose,
            "group": item.group,
            "group_label": item.group_label,
        }
        for item in ENTRYPOINTS.values()
    ]
