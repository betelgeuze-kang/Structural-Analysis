from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_canonical_ci_owns_structural_core_lane() -> None:
    workflow = _read("ci.yml")

    assert "name: CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "scripts/check_product_ci_boundaries.py" in workflow
    assert "scripts/run_product_ci_lane.py --lane core" in workflow
    assert "scripts/verify_quality_gate.py --mode pr" in workflow


def test_legacy_evidence_has_independent_hosted_lane() -> None:
    workflow = _read("legacy-evidence-ci.yml")

    assert "name: Legacy Evidence CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "scripts/run_product_ci_lane.py" in workflow
    assert "--lane legacy_evidence" in workflow
    assert "tests/test_build_product_readiness_snapshot.py" in workflow


def test_molecular_code_is_checked_only_as_quarantine() -> None:
    workflow = _read("science-quarantine-ci.yml")

    assert "name: Molecular Quarantine CI" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "--lane molecular_quarantine" in workflow
    assert "--collect-only" in workflow
    assert "without product promotion" in workflow


def test_quarantine_control_plane_path_does_not_match_product_tokens() -> None:
    assert not (WORKFLOWS / "molecular-quarantine-ci.yml").exists()
    assert (WORKFLOWS / "science-quarantine-ci.yml").exists()


def test_pr_quality_gate_no_longer_lints_all_product_domains_together() -> None:
    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(
        encoding="utf-8"
    )

    assert '"scripts/check_product_ci_boundaries.py"' in gate
    assert '_lane_command("core")' in gate
    assert '[_python(), "-m", "ruff", "check", "."]' not in gate
    assert '_lane_command("legacy_evidence")' in gate
    assert '_lane_command("molecular_quarantine")' in gate


def test_runner_policy_allowlists_all_deterministic_product_lanes() -> None:
    policy = (
        ROOT / "scripts" / "check_github_actions_runner_policy.py"
    ).read_text(encoding="utf-8")

    assert '".github/workflows/ci.yml"' in policy
    assert '".github/workflows/legacy-evidence-ci.yml"' in policy
    assert '".github/workflows/science-quarantine-ci.yml"' in policy
    assert '".github/workflows/molecular-quarantine-ci.yml"' not in policy
