from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_source_boundary_inventory_as_a_candidate_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "Source boundary inventory" in workflow
    assert "scripts/plan_source_boundary_cleanup.py" in workflow
    assert "--large-file-threshold-mib 25" in workflow
    assert "--fail-on-candidates" in workflow
    assert "--out /tmp/source-boundary-cleanup-plan.json" in workflow
    assert "--out-md /tmp/source-boundary-cleanup-plan.md" in workflow
