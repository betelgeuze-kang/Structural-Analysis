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


def _g1_child_hip_refresh_evidence(*, ready: bool = True) -> dict:
    component = {
        "present": True,
        "ready": ready,
        "hip_required": True,
        "promoted_to_final_state": ready,
        "accepted_state_refresh_backend": "hip_full_residual",
        "accepted_state_refresh_hip_used": ready,
        "accepted_state_refresh_cpu_used": False,
    }
    return {
        "schema_version": "g1-child-hip-residual-refresh-evidence.v1",
        "ready": ready,
        "blockers": [] if ready else [
            "child_current_tangent_residual_row_not_promoted_to_final_state"
        ],
        "components": {
            "matrix_free_global_krylov": {
                **component,
                "accepted_state_refresh_backend": "hip_full_residual_resident",
            },
            "current_tangent_residual_row_correction": component,
        },
    }


def _g1_child_gate_evidence(*, ready: bool = True) -> dict:
    return {
        "schema_version": "g1-child-gate-evidence.v1",
        "ready": ready,
        "blockers": [] if ready else [
            "child_direct_residual_gate_not_proven",
            "child_relative_increment_gate_not_proven",
        ],
        "direct_residual_newton_ready": ready,
        "full_load_closure_passed": ready,
        "direct_residual_gate_passed": ready,
        "relative_increment_gate_passed": ready,
        "fallback_zero_passed": ready,
        "material_newton_breadth_passed": ready,
        "consistent_residual_jacobian_newton_passed": ready,
        "observed_load_scale": 1.0 if ready else 0.656,
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "load_scale_passed": ready,
    }


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
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": _g1_child_gate_evidence(),
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


def test_snapshot_does_not_promote_pm_contract_pass_to_release_ready(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_text(
        tmp_path / "README.md",
        "PM release areas are `15/16` green. Current action register has `1` open blocker handoffs.\n",
    )
    _write_text(
        tmp_path / "docs/commercialization-gap-current-state.md",
        "PM release areas are `15/16` green. The open blocker total is `1`.\n",
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
        "paid_pilot_candidate": True,
        "ga_enterprise_ready": True,
        "release_area_matrix": [{"ok": True} for _ in range(15)] + [{"ok": False}],
        "release_area_blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
        "full_release_blockers": ["basic_ci::pr_ci_30_consecutive_pass_evidence_missing"],
    })
    _write_json(tmp_path / "pm_release_blocker_action_register.json", {
        "schema_version": "pm-release-blocker-action-register.v1",
        "summary": {"open_blocker_count": 1},
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["schema_valid"] is True
    assert payload["evidence_fresh"] is True
    assert payload["status"] == "blocked"
    assert payload["components"]["pm_release"]["contract_pass"] is True
    assert payload["components"]["pm_release"]["full_release_gate_ready"] is False
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False
    assert (
        "pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing"
        in payload["blockers"]
    )
    assert "contract_pass fields are component contract results" in (
        payload["claim_boundary"]["contract_pass_vs_release_ready"]
    )


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


def test_snapshot_engine_version_tracks_canonical_product_identity(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "package.json", {
        "name": "structural-optimization-workbench",
        "version": "1.2.3",
    })
    _write_text(
        tmp_path / "pyproject.toml",
        '[project]\nname = "structural-optimization-workbench"\nversion = "1.2.3"\n',
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["engine_version"] == "structural-optimization-workbench@1.2.3"
    assert payload["components"]["product_identity"]["matches"] is True
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


def test_snapshot_blocks_dirty_worktree_even_when_committed_boundary_is_receipt_only(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    _write_text(tmp_path / "solver_core.py", "print('uncommitted solver change')\n")

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
    assert "stale_or_inconsistent:worktree_dirty" in payload["blockers"]
    assert payload["state_consistency"]["worktree"]["dirty"] is True
    assert payload["state_consistency"]["worktree"]["status_rows"] == [
        "?? solver_core.py",
    ]
    assert payload["state_consistency"]["worktree"]["dirty_paths"] == [
        "solver_core.py",
    ]
    assert payload["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == [
        "solver_core.py",
    ]
    assert (
        metadata_rows["pm_release_gate_report"]["source_state_kind"]
        == "receipt_only_commit"
    )


def test_snapshot_allows_dirty_receipt_only_worktree_as_refresh_boundary(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    _commit_all(tmp_path, "receipt")
    pm_report = json.loads((tmp_path / "pm_release_gate_report.json").read_text())
    pm_report["generated_at"] = "2026-06-21T00:00:01+00:00"
    _write_json(tmp_path / "pm_release_gate_report.json", pm_report)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )

    assert "stale_or_inconsistent:worktree_dirty" not in payload["blockers"]
    assert payload["state_consistency"]["worktree"]["dirty"] is False
    assert payload["state_consistency"]["worktree"]["status_rows"] == [
        " M pm_release_gate_report.json",
    ]
    assert payload["state_consistency"]["worktree"]["dirty_paths"] == [
        "pm_release_gate_report.json",
    ]
    assert payload["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == []
    assert payload["status"] == "ready"
    assert payload["evidence_fresh"] is True


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


def test_snapshot_rejects_fresh_validation_summary_when_row_receipt_reused(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
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
        "rows": [
            {
                "lane_id": f"lane_{index}",
                "pass": True,
                "fresh_validation_receipt_fresh": index != 0,
                "fresh_validation_receipt_contract_pass": True,
            }
            for index in range(8)
        ],
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["fresh_full_validation"]["row_count"] == 8
    assert payload["components"]["fresh_full_validation"]["row_pass_count"] == 8
    assert payload["components"]["fresh_full_validation"]["row_fresh_receipt_count"] == 7
    assert payload["components"]["fresh_full_validation"]["ready"] is False
    assert (
        "fresh_full_validation::row_fresh_receipt_count_below_lane_count"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


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


def test_snapshot_blocks_unexpected_g1_full_load_lane_schema(tmp_path: Path) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    g1_lane = json.loads(
        (tmp_path / "g1_full_load_hip_newton_lane_report.json").read_text(
            encoding="utf-8"
        )
    )
    g1_lane["schema_version"] = "g1-full-load-hip-newton-lane.v0"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", g1_lane)

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert (
        "schema_invalid:unexpected_schema_version:g1_full_load_hip_newton_lane_report"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False
    assert payload["release_ready"] is False


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


def test_snapshot_blocks_ready_g1_lane_without_child_hip_refresh_evidence(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    g1_component = payload["components"]["g1"]
    assert g1_component["full_load_hip_newton_lane_ready"] is False
    assert (
        g1_component[
            "full_load_hip_newton_child_hip_residual_refresh_ready"
        ]
        is False
    )
    assert (
        "g1_full_load_lane::child_hip_residual_refresh_evidence_missing"
        in payload["blockers"]
    )
    assert (
        "g1_full_load_lane::matrix_free_global_krylov_child_hip_residual_refresh_not_ready"
        in payload["blockers"]
    )
    assert (
        "g1_full_load_lane::current_tangent_residual_row_correction_child_hip_residual_refresh_not_ready"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_with_invalid_child_hip_refresh_schema(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_hip_refresh = _g1_child_hip_refresh_evidence()
    child_hip_refresh["schema_version"] = "wrong-schema.v1"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": child_hip_refresh,
        "child_gate_evidence": _g1_child_gate_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        payload["components"]["g1"][
            "full_load_hip_newton_child_hip_residual_refresh_ready"
        ]
        is False
    )
    assert (
        "g1_full_load_lane::child_hip_residual_refresh_evidence_schema_invalid"
        in payload["blockers"]
    )
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_without_child_gate_evidence(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    g1_component = payload["components"]["g1"]
    assert g1_component["full_load_hip_newton_lane_ready"] is False
    assert g1_component["full_load_hip_newton_child_gate_ready"] is False
    assert "g1_full_load_lane::child_gate_evidence_missing" in payload["blockers"]
    assert "g1_full_load_lane::child_direct_residual_gate_not_proven" in payload["blockers"]
    assert "g1_full_load_lane::child_relative_increment_gate_not_proven" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False


def test_snapshot_blocks_ready_g1_lane_with_invalid_child_gate_schema(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_gate_evidence = _g1_child_gate_evidence()
    child_gate_evidence["schema_version"] = "wrong-schema.v1"
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": True,
        "status": "ready",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": child_gate_evidence,
        "blockers": [],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert payload["components"]["g1"]["full_load_hip_newton_child_gate_ready"] is False
    assert "g1_full_load_lane::child_gate_evidence_schema_invalid" in payload["blockers"]
    assert payload["paid_pilot_ready"] is False


def test_snapshot_surfaces_g1_child_contract_gate_conflict_blockers(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    child_gate_evidence = _g1_child_gate_evidence(ready=False)
    child_gate_evidence["blockers"].extend([
        "child_material_newton_contract_gate_conflict",
        "child_consistent_residual_jacobian_contract_gate_conflict",
    ])
    _write_json(tmp_path / "g1_full_load_hip_newton_lane_report.json", {
        "schema_version": "g1-full-load-hip-newton-lane.v1",
        "generated_at": "2026-06-21T00:00:00+00:00",
        "source_commit_sha": commit,
        "reused_evidence": False,
        "contract_pass": False,
        "status": "blocked",
        "checkpoint": {"load_scale": 1.0},
        "required_load_scale": 1.0,
        "full_load_tolerance": 1.0e-12,
        "full_load_input_pass": True,
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": child_gate_evidence,
        "blockers": [
            "child_direct_residual_gate_not_proven",
            "child_relative_increment_gate_not_proven",
            "child_material_newton_contract_gate_conflict",
            "child_consistent_residual_jacobian_contract_gate_conflict",
        ],
    })

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert payload["components"]["g1"]["full_load_hip_newton_lane_ready"] is False
    assert (
        "g1_full_load_lane::child_material_newton_contract_gate_conflict"
        in payload["blockers"]
    )
    assert (
        "g1_full_load_lane::child_direct_residual_gate_not_proven"
        in payload["blockers"]
    )
    assert (
        "g1_full_load_lane::child_relative_increment_gate_not_proven"
        in payload["blockers"]
    )
    assert (
        "g1_full_load_lane::child_consistent_residual_jacobian_contract_gate_conflict"
        in payload["blockers"]
    )
    child_gate = payload["components"]["g1"]["full_load_hip_newton_child_gate"]
    assert "child_material_newton_contract_gate_conflict" in child_gate["blockers"]
    assert (
        "child_consistent_residual_jacobian_contract_gate_conflict"
        in child_gate["blockers"]
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
        "child_hip_residual_refresh_evidence": _g1_child_hip_refresh_evidence(),
        "child_gate_evidence": _g1_child_gate_evidence(),
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


def test_snapshot_check_passes_when_stored_snapshot_matches_current_inputs(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Simulate the volatile generated_at advancing on a subsequent regeneration.
    existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
    existing["generated_at"] = "2099-01-01T00:00:00+00:00"
    snapshot_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["release_ready"] is True


def test_snapshot_check_fails_when_stored_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_missing:")
    assert "product_readiness_snapshot.json" in message
    assert generated is None
    assert snapshot_path.exists() is False


def test_snapshot_check_fails_when_stored_snapshot_is_unreadable(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text("{ this is not valid json", encoding="utf-8")

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_unreadable:")
    assert "product_readiness_snapshot.json" in message
    assert generated is None


def test_snapshot_check_fails_when_stored_snapshot_is_semantically_different(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    # Inject a stale semantic change that must be detected by --check.
    payload["status"] = "ready"
    payload["evidence_fresh"] = True
    payload["release_ready"] = True
    payload["blockers"] = []
    payload["blocker_count"] = 0
    payload["components"]["pm_release"]["release_area_green_count"] = 0
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "components.pm_release.release_area_green_count" in message
    assert generated is not None
    assert generated["status"] == "ready"
    assert generated["components"]["pm_release"]["release_area_green_count"] == 16


def test_snapshot_check_fails_when_stored_snapshot_blocks_count_drifts(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["blockers"] = []
    payload["blocker_count"] = 0
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    # Change an upstream input so the freshly generated snapshot accumulates a
    # new blocker. The stored snapshot must be reported as stale.
    ci_payload = json.loads(
        (tmp_path / "github_actions_ci_streak_evidence.json").read_text(encoding="utf-8")
    )
    ci_payload["contract_pass"] = False
    ci_payload["summary"]["pr_threshold_pass"] = False
    ci_payload["summary"]["nightly_threshold_pass"] = False
    ci_payload["lanes"] = {
        "pr": {"blockers": ["pr_github_actions_30_consecutive_pass_evidence_missing"]},
        "nightly": {"blockers": ["nightly_github_actions_30_consecutive_pass_evidence_missing"]},
    }
    _write_json(tmp_path / "github_actions_ci_streak_evidence.json", ci_payload)

    ok, message, _generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "blockers" in message
    assert "components.github_actions_ci_streak.ready" in message


def test_snapshot_check_ignores_volatile_generated_at_only(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    existing = json.loads(snapshot_path.read_text(encoding="utf-8"))
    # Top-level and nested generated_at must be ignored, every other field
    # must still match.
    existing["generated_at"] = "1900-01-01T00:00:00+00:00"
    for row in existing["state_consistency"]["metadata_rows"]:
        row["generated_at"] = "1900-01-01T00:00:00+00:00"
    snapshot_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, _generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True
    assert message == "snapshot_consistent"


def test_snapshot_check_ignores_top_level_snapshot_source_commit_only(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["source_commit_sha"] = "new-wrapper-commit-after-snapshot-was-checked-in"
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["source_commit_sha"] == commit


def test_snapshot_check_keeps_nested_source_commit_rows_semantic(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["state_consistency"]["metadata_rows"][0]["source_commit_sha"] = (
        "stale-upstream-evidence-commit"
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "state_consistency.metadata_rows" in message
    assert generated is not None


def test_snapshot_check_ignores_receipt_only_worktree_diagnostics(
    tmp_path: Path,
) -> None:
    _init_git_repo(tmp_path)
    _write_stable_non_receipt_inputs(tmp_path)
    source_commit = _commit_all(tmp_path, "source")
    _write_ready_snapshot_inputs(tmp_path, commit=source_commit)
    snapshot_path = (
        tmp_path
        / "implementation"
        / "phase1"
        / "release_evidence"
        / "productization"
        / "product_readiness_snapshot.json"
    )
    _write_json(snapshot_path, {"schema_version": "product-readiness-snapshot.v1"})
    _commit_all(tmp_path, "receipt")

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
    )
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
    )

    assert ok is True
    assert message == "snapshot_consistent"
    assert generated is not None
    assert generated["state_consistency"]["worktree"]["dirty"] is False
    assert generated["state_consistency"]["worktree"]["status_rows"] == [
        " M implementation/phase1/release_evidence/productization/product_readiness_snapshot.json",
    ]
    assert generated["state_consistency"]["worktree"]["non_receipt_dirty_paths"] == []


def test_snapshot_check_does_not_ignore_unrelated_status_rows(
    tmp_path: Path,
) -> None:
    commit = "abc123"
    _write_ready_snapshot_inputs(tmp_path, commit=commit)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"

    payload = build_product_readiness_snapshot.build_snapshot(
        repo_root=tmp_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )
    payload["components"]["github_actions_runner_policy"]["status_rows"] = [
        "stale semantic row",
    ]
    snapshot_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ok, message, generated = build_product_readiness_snapshot.check_snapshot_consistency(
        repo_root=tmp_path,
        out_path=snapshot_path,
        paths=_paths(tmp_path),
        source_commit_sha=commit,
    )

    assert ok is False
    assert message.startswith("snapshot_semantic_mismatch:")
    assert "components.github_actions_runner_policy.status_rows" in message
    assert generated is not None


def test_main_check_returns_zero_on_match_and_writes_nothing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.write_text('{"schema_version":"product-readiness-snapshot.v1"}\n', encoding="utf-8")

    monkeypatch.setattr(
        build_product_readiness_snapshot, "ROOT", tmp_path
    )

    def fake_check_snapshot_consistency(
        *,
        repo_root,
        out_path,
        paths=build_product_readiness_snapshot.SnapshotInputPaths(),
        source_commit_sha=None,
    ):
        assert repo_root == tmp_path
        assert out_path == snapshot_path
        return True, "snapshot_consistent", {"release_ready": True}

    monkeypatch.setattr(
        build_product_readiness_snapshot,
        "check_snapshot_consistency",
        fake_check_snapshot_consistency,
    )
    mtime_before = snapshot_path.stat().st_mtime_ns
    contents_before = snapshot_path.read_text(encoding="utf-8")

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--check",
        ]
    )

    assert exit_code == 0
    assert snapshot_path.stat().st_mtime_ns == mtime_before
    assert snapshot_path.read_text(encoding="utf-8") == contents_before


def test_main_no_write_prints_snapshot_without_touching_out(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    snapshot_path.write_text(
        '{"schema_version":"existing-product-readiness-snapshot.v1"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(build_product_readiness_snapshot, "ROOT", tmp_path)

    def fake_build_snapshot():
        return {
            "schema_version": "product-readiness-snapshot.v1",
            "status": "ready",
            "release_ready": True,
        }

    monkeypatch.setattr(
        build_product_readiness_snapshot,
        "build_snapshot",
        fake_build_snapshot,
    )
    mtime_before = snapshot_path.stat().st_mtime_ns
    contents_before = snapshot_path.read_text(encoding="utf-8")

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--json",
            "--no-write",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["schema_version"] == "product-readiness-snapshot.v1"
    assert snapshot_path.stat().st_mtime_ns == mtime_before
    assert snapshot_path.read_text(encoding="utf-8") == contents_before


def test_help_documents_non_mutating_snapshot_modes(capsys) -> None:
    try:
        build_product_readiness_snapshot.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    output = capsys.readouterr().out
    normalized = " ".join(output.split())
    assert "--no-write" in output
    assert "protected evidence files are not refreshed accidentally" in normalized
    assert "top-level source_commit_sha wrapper" in normalized


def test_main_check_returns_nonzero_on_missing_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    _write_ready_snapshot_inputs(tmp_path, commit="abc123")
    monkeypatch.setattr(build_product_readiness_snapshot, "ROOT", tmp_path)
    snapshot_path = tmp_path / "product_readiness_snapshot.json"
    assert not snapshot_path.exists()

    exit_code = build_product_readiness_snapshot.main(
        [
            "--out",
            "product_readiness_snapshot.json",
            "--check",
        ]
    )

    assert exit_code == 2
    assert not snapshot_path.exists()
