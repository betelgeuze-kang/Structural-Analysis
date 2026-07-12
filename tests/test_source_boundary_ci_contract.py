from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_ci_runs_source_boundary_inventory_as_a_candidate_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    nightly = (ROOT / ".github" / "workflows" / "nightly-full-quality.yml").read_text(
        encoding="utf-8"
    )
    heavy_nightly = (ROOT / ".github" / "workflows" / "nightly-heavy-solver.yml").read_text(
        encoding="utf-8"
    )

    assert "PR quality gate" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow
    assert "group: ci-${{ github.workflow }}-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "python -m pytest -q --junitxml" not in workflow

    assert "Deterministic repository quality gate" in nightly
    assert "scripts/verify_quality_gate.py --mode pr" in nightly
    assert "Deterministic Python regression suite" in nightly
    assert "tests/test_build_product_readiness_snapshot.py" in nightly
    assert "tests/test_build_ci_streak_intake_packet.py" in nightly
    assert "python -m pytest -q\n" not in nightly
    assert "group: nightly-full-quality-${{ github.ref }}" in nightly
    assert "cancel-in-progress: true" in nightly

    assert "Full workstation/release quality gate" in heavy_nightly
    assert "scripts/verify_quality_gate.py --mode full" in heavy_nightly
    assert "group: nightly-heavy-solver-${{ github.ref }}" in heavy_nightly
    assert "self-hosted" in heavy_nightly
    assert "cancel-in-progress: true" in heavy_nightly

    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    assert "scripts/plan_source_boundary_cleanup.py" in gate
    assert "scripts/report_source_boundary_footprint.py" in gate
    assert "scripts/check_structural_scope_contamination.py" in gate
    assert "--tracked-only" in gate
    assert "--fail-blocked" in gate
    assert "--large-file-threshold-mib" in gate
    assert '"10"' in gate
    assert "--allowlist-manifest" in gate
    assert "implementation/phase1/source_boundary_allowlist.json" in gate
    assert "--fail-on-candidates" in gate

    runbook = (ROOT / "docs" / "source-boundary-restore-runbook.md").read_text(
        encoding="utf-8"
    )
    assert "Do not rewrite history" in runbook
    assert "git rm --cached" in runbook
    assert "non-destructive" in runbook
