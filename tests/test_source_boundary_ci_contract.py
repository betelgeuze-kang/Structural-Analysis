from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_source_boundary_inventory_as_a_candidate_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    nightly = (ROOT / ".github" / "workflows" / "nightly-full-quality.yml").read_text(encoding="utf-8")

    assert "PR quality gate" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow
    assert "Full quality gate" in nightly
    assert "scripts/verify_quality_gate.py --mode full" in nightly

    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    assert "scripts/plan_source_boundary_cleanup.py" in gate
    assert "scripts/report_source_boundary_footprint.py" in gate
    assert "--large-file-threshold-mib" in gate
    assert '"10"' in gate
    assert "--allowlist-manifest" in gate
    assert "implementation/phase1/source_boundary_allowlist.json" in gate
    assert "--fail-on-candidates" in gate

    runbook = (ROOT / "docs" / "source-boundary-restore-runbook.md").read_text(encoding="utf-8")
    assert "Do not rewrite history" in runbook
    assert "git rm --cached" in runbook
    assert "non-destructive" in runbook
