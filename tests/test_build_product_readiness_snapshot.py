from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_product_readiness_snapshot.py"
SPEC = importlib.util.spec_from_file_location("build_product_readiness_snapshot", SCRIPT_PATH)
assert SPEC is not None
build_product_readiness_snapshot = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = build_product_readiness_snapshot
SPEC.loader.exec_module(build_product_readiness_snapshot)


SnapshotInputPaths = build_product_readiness_snapshot.SnapshotInputPaths


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _paths(tmp_path: Path) -> SnapshotInputPaths:
    return SnapshotInputPaths(
        readme=Path("README.md"),
        current_state=Path("docs/commercialization-gap-current-state.md"),
        pm_report=Path("pm_release_gate_report.json"),
        gap_closure_status=Path("gap_closure_status.json"),
        fresh_full_validation=Path("fresh_full_validation_lane_status.json"),
        g1_terminal_gate=Path("mgt_g1_direct_residual_terminal_gate_report.json"),
        g1_full_load_hip_newton_lane=Path("g1_full_load_hip_newton_lane_report.json"),
        customer_shadow=Path("customer_shadow_evidence_status.json"),
        workstation_delivery=Path("workstation_delivery_readiness.json"),
        independent_product=Path("independent_product_readiness.json"),
        blocker_action_register=Path("pm_release_blocker_action_register.json"),
        github_actions_ci_streak=Path("github_actions_ci_streak_evidence.json"),
        ux_new_user_observation=Path("ux_new_user_observation_report.json"),
        license_status_closure=Path("license_status_closure_report.json"),
        external_benchmark_submission_readiness=Path("external_benchmark_submission_readiness.json"),
        external_benchmark_submission_updates=Path("external_benchmark_submission_updates.json"),
        self_hosted_runner_status=Path("github_actions_self_hosted_runner_status.json"),
        package_json=Path("package.json"),
        pyproject_toml=Path("pyproject.toml"),
        github_workflows=Path(".github/workflows"),
    )


def _write_common_metadata(tmp_path: Path, *, commit: str = "abc123") -> None:
    _write_json(tmp_path / "gap_closure_status.json", {
        "schema_version": "gap-closure-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
    })
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "blockers": [],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": [],
    })
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", {
        "schema_version": "github-actions-ci-streak-evidence.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "pr_threshold_pass": True,
            "nightly_threshold_pass": True,
            "pr_consecutive_pass_count": 30,
            "nightly_consecutive_pass_count": 30,
        },
        "lanes": {
            "pr": {"blockers": []},
            "nightly": {"blockers": []},
        },
    })
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "full_load_input_pass": True,
        "blockers": [],
    })
    _write_json(tmp_path / "ux_new_user_observation_report.json", {
        "schema_version": "ux-new-user-observation-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "completion_minutes": 24.0,
            "max_completion_minutes": 30.0,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "license_status_closure_report.json", {
        "schema_version": "license-status-closure-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"status": "active"},
        "blockers": [],
    })
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 4,
            "submission_receipt_pending_count": 0,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_url": f"https://example.invalid/eb/{idx}",
                "receipt_status": "attached",
                "closure_evidence_status": "attached",
            }
            for idx in range(1, 5)
        },
    })
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.0.0",
    })
    _write_json(tmp_path / "github_actions_self_hosted_runner_status.json", {
        "schema_version": "github-actions-self-hosted-runner-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "contract_pass": True,
        "status": "ready",
        "required_labels": ["self-hosted", "linux", "x64"],
        "ready_runner_count": 1,
        "blockers": [],
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.0.0"\n',
    )
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            "'[\"self-hosted\",\"linux\",\"x64\"]') }}\n"
        ),
    )


def _write_stable_non_receipt_inputs(tmp_path: Path) -> None:
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.0.0",
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.0.0"\n',
    )
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        (
            "name: CI\n"
            "jobs:\n"
            "  verify:\n"
            "    runs-on: ${{ fromJSON(vars.STRUCTURAL_ACTIONS_RUNNER_LABELS || "
            "'[\"self-hosted\",\"linux\",\"x64\"]') }}\n"
        ),
    )


def _write_ready_snapshot_inputs(tmp_path: Path, *, commit: str) -> None:
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": (
            "Full-mesh/full-load physical residual+increment/material Newton gate "
            "is closed with fallback_count=0."
        ),
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.check_call(["git", "init"], cwd=tmp_path, stdout=subprocess.DEVNULL)
    subprocess.check_call(
        ["git", "config", "user.email", "test@example.com"],
        cwd=tmp_path,
    )
    subprocess.check_call(["git", "config", "user.name", "Test"], cwd=tmp_path)


def _commit_all(tmp_path: Path, message: str) -> str:
    subprocess.check_call(["git", "add", "."], cwd=tmp_path)
    subprocess.check_call(["git", "commit", "-m", message], cwd=tmp_path, stdout=subprocess.DEVNULL)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()


def test_snapshot_marks_doc_json_conflicts_stale_or_inconsistent(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `13/16` green. Current action register has `17` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `12/16` green. The open blocker total is `20`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": False,
        "release_area_gate_ready": False,
        "full_release_gate_ready": False,
        "release_area_matrix": [{"ok": True} for _ in range(12)] + [{"ok": False} for _ in range(4)],
        "release_area_blockers": ["basic_ci::missing"],
        "full_release_blockers": ["basic_ci::missing"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 21},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 0, "fresh_validation_receipt_pass_count": 0},
        "blockers": ["commercial_benchmark_torch::fresh_validation_receipt_missing"],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"completed_shadow_case_count": 0, "min_completed_shadow_cases": 3},
        "blockers": ["completed_shadow_case_count_below_minimum"],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "This does not close full-mesh/full-load nonlinear equilibrium.",
    })
    _write_common_metadata(tmp_path, commit=commit)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert "stale_or_inconsistent:release_area_count_conflict" in payload["blockers"]
    assert "stale_or_inconsistent:open_blocker_count_conflict" in payload["blockers"]
    assert "g1_full_mesh_full_load_not_closed" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False


def test_snapshot_passes_happy_path_when_all_readiness_inputs_agree(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is True
    assert payload["reused_evidence"] is False
    assert payload["evidence_fresh"] is True
    assert payload["paid_pilot_ready"] is True
    assert payload["independent_product_ready"] is True
    assert payload["ga_enterprise_ready"] is True
    assert payload["release_ready"] is True
    assert payload["blocker_count"] == 0
    assert payload["blockers"] == []


def test_snapshot_reads_project_identity_from_structured_pyproject_toml(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "pyproject.toml",
        (
            "[tool.example]\n"
            'name = "not-the-product-name"\n'
            "\n"
            "[project]\n"
            'name = "structural-optimization-workbench" # canonical package name\n'
            'version = "1.0.0" # canonical package version\n'
        ),
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["product_identity"] == {
        "package_json": {
            "name": "structural-optimization-workbench",
            "version": "1.0.0",
        },
        "pyproject": {
            "name": "structural-optimization-workbench",
            "version": "1.0.0",
        },
        "name_matches": True,
        "version_matches": True,
        "matches": True,
    }
    assert "product_identity_name_mismatch:package_json_vs_pyproject" not in payload["blockers"]
    assert "product_identity_version_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_blocks_package_pyproject_name_mismatch(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench-ui",
        "version": "1.0.0",
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "blocked"
    assert payload["paid_pilot_ready"] is False
    assert payload["components"]["product_identity"]["name_matches"] is False
    assert payload["components"]["product_identity"]["version_matches"] is True
    assert "product_identity_name_mismatch:package_json_vs_pyproject" in payload["blockers"]
    assert "product_identity_version_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_blocks_package_pyproject_version_mismatch(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "0.1.0"\n',
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "blocked"
    assert payload["paid_pilot_ready"] is False
    assert payload["components"]["product_identity"]["name_matches"] is True
    assert payload["components"]["product_identity"]["version_matches"] is False
    assert "product_identity_version_mismatch:package_json_vs_pyproject" in payload["blockers"]
    assert "product_identity_name_mismatch:package_json_vs_pyproject" not in payload["blockers"]


def test_snapshot_accepts_receipt_only_commit_as_fresh(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    receipt_commit = _commit_all(tmp_path, "receipt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == receipt_commit
    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_accepts_dispatch_prompt_commit_as_receipt_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(
        tmp_path / "docs/ai/dispatch/g1_runtime_blocker_probe.md",
        "Goal: inspect runtime blocker propagation.\n",
    )
    dispatch_commit = _commit_all(tmp_path, "dispatch prompt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["source_commit_sha"] == dispatch_commit
    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "ready"
    assert metadata_rows["pm_release_gate_report"]["source_commit_matches_head"] is False
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is True
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )
    assert (
        "docs/ai/dispatch/g1_runtime_blocker_probe.md"
        in metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"]
    )
    assert not [
        blocker
        for blocker in payload["blockers"]
        if blocker.startswith("stale_or_inconsistent:source_commit_mismatch")
    ]


def test_snapshot_blocks_non_receipt_changes_after_source_commit(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(tmp_path / "solver_core.py", "print('changed after evidence')\n")
    _commit_all(tmp_path, "solver code change")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    metadata_rows = {
        row["artifact"]: row
        for row in payload["state_consistency"]["metadata_rows"]
    }

    assert payload["status"] == "stale_or_inconsistent"
    assert payload["evidence_fresh"] is False
    assert (
        "stale_or_inconsistent:source_commit_mismatch:pm_release_gate_report"
        in payload["blockers"]
    )
    assert metadata_rows["pm_release_gate_report"]["source_state_fresh"] is False
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "non_receipt_paths_changed"
    )
    assert metadata_rows["pm_release_gate_report"]["changed_paths_since_source_commit"] == [
        "solver_core.py",
    ]


def test_snapshot_blocks_stale_workstation_and_independent_inputs(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": "old-workstation",
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "blockers": [],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": "old-independent",
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["status"] == "stale_or_inconsistent"
    assert "stale_or_inconsistent:source_commit_mismatch:workstation_delivery_readiness" in payload["blockers"]
    assert "stale_or_inconsistent:source_commit_mismatch:independent_product_readiness" in payload["blockers"]
    assert payload["evidence_fresh"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["ga_enterprise_ready"] is False


def test_snapshot_does_not_promote_ready_status_with_component_blockers(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "workstation_delivery_readiness.json", {
        "schema_version": "workstation-delivery-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "blockers": ["delivery_blocker_still_present"],
    })
    _write_json(tmp_path / "independent_product_readiness.json", {
        "schema_version": "independent-commercial-product-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "independent_commercial_product_ready": True,
        "status": "ready",
        "blockers": ["independent_blocker_still_present"],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["workstation_delivery_ready"] is False
    assert payload["independent_product_ready"] is False
    assert "workstation_delivery::delivery_blocker_still_present" in payload["blockers"]
    assert "independent_product::independent_blocker_still_present" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


def test_snapshot_blocks_github_hosted_actions_runner_policy(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_text(
        tmp_path / ".github/workflows/ci.yml",
        "name: CI\njobs:\n  verify:\n    runs-on: ubuntu-latest\n",
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_runner_policy"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert any(
        blocker.startswith("runner_policy::.github/workflows/ci.yml:4:github_hosted_runner_label")
        for blocker in payload["blockers"]
    )


def test_snapshot_blocks_missing_self_hosted_runner_status(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"lane_count": 8, "fresh_validation_receipt_present_count": 8, "fresh_validation_receipt_pass_count": 8},
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    (tmp_path / "github_actions_self_hosted_runner_status.json").unlink()

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_self_hosted_runner"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert "missing_artifact:github_actions_self_hosted_runner_status.json" in payload["blockers"]
    assert "self_hosted_runner:not_ready" in payload["blockers"]


def test_snapshot_surfaces_release_operation_evidence_blockers(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", {
        "schema_version": "github-actions-ci-streak-evidence.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {
            "pr_threshold_pass": False,
            "nightly_threshold_pass": False,
            "pr_consecutive_pass_count": 0,
            "nightly_consecutive_pass_count": 0,
        },
        "lanes": {
            "pr": {"blockers": ["pr_github_actions_30_consecutive_pass_evidence_missing"]},
            "nightly": {"blockers": ["nightly_github_actions_30_consecutive_pass_evidence_missing"]},
        },
    })
    _write_json(tmp_path / "ux_new_user_observation_report.json", {
        "schema_version": "ux-new-user-observation-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"completion_minutes": None, "max_completion_minutes": 30.0},
        "blockers": ["observation_file_missing"],
    })
    _write_json(tmp_path / "license_status_closure_report.json", {
        "schema_version": "license-status-closure-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": False,
        "summary": {"status": "not_configured"},
        "blockers": ["license_status_not_active"],
    })
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 0,
            "submission_receipt_pending_count": 4,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_status": "pending_external_submission_receipt",
                "closure_evidence_status": "pending",
            }
            for idx in range(1, 5)
        },
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["github_actions_ci_streak"]["ready"] is False
    assert payload["components"]["human_ux_observation"]["ready"] is False
    assert payload["components"]["license_status"]["ready"] is False
    assert payload["components"]["external_benchmark_receipts"]["ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "ci_streak::pr::pr_github_actions_30_consecutive_pass_evidence_missing"
        in payload["blockers"]
    )
    assert "human_ux::observation_file_missing" in payload["blockers"]
    assert "license::license_status_not_active" in payload["blockers"]
    assert "external_benchmark::submission_receipts_pending=4" in payload["blockers"]


def test_snapshot_rejects_reused_external_benchmark_receipt_sidecar(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": True,
        "full_g1_closure_blockers": [],
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "external_benchmark_submission_readiness.json", {
        "schema_version": "external-benchmark-submission-readiness.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "summary": {
            "submission_queue_count": 4,
            "submission_receipt_attached_count": 4,
            "submission_receipt_pending_count": 0,
        },
    })
    _write_json(tmp_path / "external_benchmark_submission_updates.json", {
        "schema_version": "external-benchmark-submission-updates.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "updates": {
            f"EB-{idx:03d}": {
                "receipt_url": f"https://example.invalid/eb/{idx}",
                "receipt_status": "attached",
                "closure_evidence_status": "attached",
            }
            for idx in range(1, 5)
        },
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["external_benchmark_receipts"]["updates_fresh"] is False
    assert payload["components"]["external_benchmark_receipts"]["ready"] is False
    assert (
        "external_benchmark::submission_updates_reused_evidence_not_fresh"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_requires_schema_versions_for_release_operation_inputs(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    ci_payload = json.loads((tmp_path / "github_actions_ci_streak_evidence.json").read_text(encoding="utf-8"))
    ci_payload.pop("schema_version")
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", ci_payload)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "schema_invalid:missing_schema_version:github_actions_ci_streak_evidence"
        in payload["blockers"]
    )


def test_snapshot_surfaces_g1_full_load_lane_blocker(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": False,
        "full_g1_closure_blockers": ["full_load_gate_not_closed"],
        "claim_boundary": "Terminal checkpoint only; does not close full-mesh/full-load.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": False,
        "status": "blocked",
        "checkpoint": {"load_scale": 0.656},
        "full_load_input_pass": False,
        "blockers": ["checkpoint_load_scale_below_required_full_load"],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"]["full_load_hip_newton_lane_status"] == "blocked"
    assert (
        "g1_full_load_lane::checkpoint_load_scale_below_required_full_load"
        in payload["blockers"]
    )
    assert "g1_full_load_lane::full_load_input_not_pass" in payload["blockers"]
    assert (
        "g1_full_load_lane::observed_load_scale_below_required_full_load"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_requires_fresh_full_load_g1_lane_for_paid_pilot(tmp_path: Path) -> None:
    commit = "abc123"
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `16/16` green. Current action register has `0` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `16/16` green. The open blocker total is `0`.\n",
    )
    _write_json(tmp_path / "pm_release_gate_report.json", {
        "schema_version": "pm-release-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "limited_commercial_release_ready": True,
        "release_area_gate_ready": True,
        "full_release_gate_ready": True,
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(16)],
        "release_area_blockers": [],
        "full_release_blockers": [],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 0},
    })
    _write_json(tmp_path / "fresh_full_validation_lane_status.json", {
        "schema_version": "fresh-full-validation-lane-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {
            "lane_count": 8,
            "fresh_validation_receipt_present_count": 8,
            "fresh_validation_receipt_pass_count": 8,
        },
        "blockers": [],
    })
    _write_json(tmp_path / "customer_shadow_evidence_status.json", {
        "schema_version": "customer-shadow-evidence-status.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "summary": {"completed_shadow_case_count": 3, "min_completed_shadow_cases": 3},
        "blockers": [],
    })
    _write_json(tmp_path / "mgt_g1_direct_residual_terminal_gate_report.json", {
        "schema_version": "mgt-g1-direct-residual-terminal-gate-report.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "full_g1_closure_ready": True,
        "full_g1_closure_blockers": [],
        "claim_boundary": "Full-mesh/full-load physical residual+increment/material Newton gate is closed with fallback_count=0.",
        "blockers": [],
    })
    _write_common_metadata(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": True,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_mesh_full_load_ready"] is True
    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        payload["components"]["g1"]["full_load_hip_newton_lane_reused_evidence"]
        is True
    )
    assert "g1_full_load_lane::reused_evidence_not_false" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False
