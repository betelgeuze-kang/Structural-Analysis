from __future__ import annotations

from implementation.phase1.design_optimization.entrypoint_appendix import (
    annotate_entrypoint_groups,
    build_entrypoint_detail_groups,
    render_entrypoint_markdown_appendix_lines,
    render_entrypoint_markdown_group_lines,
    render_entrypoint_markdown_sections,
)


def test_entrypoint_appendix_helper_adds_fail_count() -> None:
    groups = [
        {
            "group": "stage_a",
            "group_label": "Stage A",
            "entrypoint_count": 2,
            "report_count": 2,
            "pass_count": 1,
            "all_pass": False,
            "entrypoint_names": ["solver_loop", "solver_loop_long"],
        }
    ]
    rows = [
        {"name": "solver_loop", "group": "stage_a", "group_label": "Stage A", "contract_pass": True, "reason_code": "PASS", "primary_report": "a.json"},
        {"name": "solver_loop_long", "group": "stage_a", "group_label": "Stage A", "contract_pass": False, "reason_code": "ERR_FAIL", "primary_report": "b.json"},
    ]
    annotated = annotate_entrypoint_groups(groups)
    assert annotated[0]["fail_count"] == 1
    detail_groups = build_entrypoint_detail_groups(rows, groups)
    assert detail_groups[0]["reason_distribution"] == "ERR_FAIL:1, PASS:1"


def test_entrypoint_appendix_markdown_render_contains_reason_distribution() -> None:
    groups = [
        {
            "group": "profile",
            "group_label": "Profile",
            "entrypoint_count": 1,
            "report_count": 1,
            "pass_count": 1,
            "all_pass": True,
            "entrypoint_names": ["objective_profile"],
        }
    ]
    rows = [
        {
            "name": "objective_profile",
            "group": "profile",
            "group_label": "Profile",
            "contract_pass": True,
            "reason_code": "PASS",
            "primary_report": "profile.json",
        }
    ]
    group_lines = render_entrypoint_markdown_group_lines(groups, include_members=True)
    appendix_lines = render_entrypoint_markdown_appendix_lines(rows, groups)
    assert "fail=`0`" in group_lines[0]
    assert any("reasons=PASS:1" in line for line in appendix_lines)


def test_entrypoint_markdown_sections_render_group_and_appendix_headings() -> None:
    groups = [
        {
            "group": "ablation",
            "group_label": "Ablation",
            "entrypoint_count": 1,
            "report_count": 1,
            "pass_count": 1,
            "all_pass": True,
            "entrypoint_names": ["ablation"],
        }
    ]
    rows = [
        {
            "name": "ablation",
            "group": "ablation",
            "group_label": "Ablation",
            "contract_pass": True,
            "reason_code": "PASS",
            "primary_report": "ablation.json",
        }
    ]
    lines = render_entrypoint_markdown_sections(rows, groups, include_members=False)
    assert lines[0] == "## Design Optimization Entrypoint Groups"
    assert "## Appendix: Design Optimization Entrypoint Details" in lines
    assert any("Ablation (1 rows, pass=1, fail=0, reasons=PASS:1)" in line for line in lines)
