from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "run_g1_full_load_hip_newton_lane.py"
)
SPEC = importlib.util.spec_from_file_location("run_g1_full_load_hip_newton_lane", SCRIPT_PATH)
assert SPEC is not None
run_g1_full_load_hip_newton_lane = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = run_g1_full_load_hip_newton_lane
SPEC.loader.exec_module(run_g1_full_load_hip_newton_lane)


def _checkpoint(path: Path, *, load_scale: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        checkpoint_schema=np.asarray("mgt-direct-residual-newton-state.v1"),
        load_scale=np.asarray(load_scale, dtype=np.float64),
        displacement_u=np.zeros(12, dtype=np.float64),
    )
    return path


def test_sub_full_load_checkpoint_blocks_before_execution(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.656)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["reused_evidence"] is False
    assert payload["checkpoint"]["load_scale"] == 0.656
    assert payload["full_load_input_pass"] is False
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    assert payload["child_exit_code"] is None


def test_full_load_dry_run_builds_hip_required_direct_probe_command(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=tmp_path / "child.json",
        dry_run=True,
    )

    command = payload["command"]
    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["contract_pass"] is False
    assert payload["full_load_input_pass"] is True
    assert "--matrix-free-global-krylov-require-hip-batch-replay" in command
    assert "--current-tangent-residual-row-require-hip-batch-replay" in command
    assert "--allow-state-dependent-shell-material-tangent-hip-replay" in command
    assert "hip_full_residual_resident" in command
    assert "hip_full_residual" in command
    assert "child_material_newton_breadth_passed" in payload["child_safety_requirements"]
    assert "material Newton breadth" in payload["claim_boundary"]


def test_child_probe_result_must_report_full_load_and_fallback_zero(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        lane_source_commit = run_g1_full_load_hip_newton_lane._git_head()
        child.write_text(
            json.dumps(
                {
                    "schema_version": "mgt-direct-residual-newton-probe.v1",
                    "source_commit_sha": lane_source_commit,
                    "reused_evidence": False,
                    "direct_residual_newton_ready": True,
                    "residual_contract": {
                        "hip_residual_engine_contract_passed": True,
                        "consistent_residual_jacobian_newton_gate_passed": True,
                    },
                    "gate_assessment": {
                        "full_load_closure_passed": True,
                        "fallback_zero_passed": True,
                        "material_newton_breadth_passed": True,
                        "consistent_residual_jacobian_newton_passed": True,
                        "full_load_closure_gate": {
                            "observed_load_scale": 1.0,
                            "required_load_scale": 1.0,
                        },
                        "cpu_acceptance_refresh_closure_blocked": False,
                    },
                    "blockers": [],
                }
            ),
            encoding="utf-8",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 0
    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["child_exit_code"] == 0
    assert payload["blockers"] == []


def _write_acceptance_child(
    child: Path,
    *,
    source_commit_sha: str,
    reused_evidence: bool,
    hip_engine_passed: bool,
    observed_load_scale: float,
    material_newton_breadth_passed: bool = True,
    consistent_residual_jacobian_newton_passed: bool = True,
    cpu_acceptance_refresh_closure_blocked: bool = False,
) -> None:
    child.write_text(
        json.dumps(
            {
                "schema_version": "mgt-direct-residual-newton-probe.v1",
                "source_commit_sha": source_commit_sha,
                "reused_evidence": reused_evidence,
                "direct_residual_newton_ready": True,
                "residual_contract": {
                    "hip_residual_engine_contract_passed": hip_engine_passed,
                    "consistent_residual_jacobian_newton_gate_passed": (
                        consistent_residual_jacobian_newton_passed
                    ),
                },
                "gate_assessment": {
                    "full_load_closure_passed": True,
                    "fallback_zero_passed": True,
                    "material_newton_breadth_passed": material_newton_breadth_passed,
                    "consistent_residual_jacobian_newton_passed": (
                        consistent_residual_jacobian_newton_passed
                    ),
                    "full_load_closure_gate": {
                        "observed_load_scale": observed_load_scale,
                        "required_load_scale": 1.0,
                    },
                    "cpu_acceptance_refresh_closure_blocked": (
                        cpu_acceptance_refresh_closure_blocked
                    ),
                },
                "blockers": [],
            }
        ),
        encoding="utf-8",
    )


def test_child_reused_evidence_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=True,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_reused_evidence_not_false" in payload["blockers"]


def test_child_source_commit_mismatch_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha="stale-child-commit",
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)
    monkeypatch.setattr(
        run_g1_full_load_hip_newton_lane, "_git_head", lambda: "lane-head-commit"
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_source_commit_sha_mismatch" in payload["blockers"]


def test_child_missing_source_commit_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha="",
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_source_commit_sha_missing" in payload["blockers"]


def test_child_observed_load_scale_below_required_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=0.656,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_observed_load_scale_below_required_full_load" in payload["blockers"]


def test_child_invalid_observed_load_scale_blocks_without_crashing(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale="not-a-number",
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_observed_load_scale_below_required_full_load" in payload["blockers"]


def test_child_hip_residual_engine_contract_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=False,
            observed_load_scale=1.0,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_hip_residual_engine_contract_not_proven" in payload["blockers"]


def test_child_cpu_acceptance_refresh_blocked_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            cpu_acceptance_refresh_closure_blocked=True,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_cpu_acceptance_refresh_closure_blocked" in payload["blockers"]


def test_child_material_newton_breadth_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            material_newton_breadth_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert "child_material_newton_breadth_not_proven" in payload["blockers"]


def test_child_consistent_residual_jacobian_not_proven_blocks_lane_promotion(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
        )
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["contract_pass"] is False
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )


def test_child_diagnostic_jacobian_inclusion_does_not_prove_consistency(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=1.0)
    child = tmp_path / "child.json"

    class Result:
        returncode = 0

    def fake_run(command: list[str], *, check: bool) -> Result:
        assert check is False
        _write_acceptance_child(
            child,
            source_commit_sha=run_g1_full_load_hip_newton_lane._git_head(),
            reused_evidence=False,
            hip_engine_passed=True,
            observed_load_scale=1.0,
            consistent_residual_jacobian_newton_passed=False,
        )
        payload = json.loads(child.read_text(encoding="utf-8"))
        payload["residual_contract"][
            "matrix_free_consistent_jacobian_subspace_included"
        ] = True
        payload["residual_contract"][
            "finite_difference_residual_row_jacobian_included"
        ] = True
        child.write_text(json.dumps(payload), encoding="utf-8")
        return Result()

    monkeypatch.setattr(run_g1_full_load_hip_newton_lane.subprocess, "run", fake_run)

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=checkpoint,
        output_json=child,
        dry_run=False,
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert (
        "child_consistent_residual_jacobian_newton_not_proven"
        in payload["blockers"]
    )


def test_cli_writes_blocked_receipt_and_fails_when_requested(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path / "state.npz", load_scale=0.75)
    out = tmp_path / "lane.json"

    exit_code = run_g1_full_load_hip_newton_lane.main(
        [
            "--checkpoint-npz",
            str(checkpoint),
            "--out",
            str(out),
            "--fail-blocked",
        ]
    )

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]


def _write_evidence_source(
    source: Path,
    *,
    candidates: list[Path],
    prefix_keys: tuple[str, ...] = ("compact_checkpoint", "retained_checkpoint_npz"),
) -> None:
    payload: dict[str, Any] = {
        "schema_version": "test-evidence-source.v1",
        "entries": [{key: str(path) for key in prefix_keys} for path in candidates],
    }
    flat: dict[str, Any] = {}
    for path in candidates:
        flat[f"entry_{path.stem}"] = {
            "compact_checkpoint": str(path),
            "retained_checkpoint_npz": {"path": str(path)},
        }
    payload.update(flat)
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_auto_select_picks_full_load_candidate(tmp_path: Path) -> None:
    sub = _checkpoint(tmp_path / "sub.npz", load_scale=0.4)
    full = _checkpoint(tmp_path / "full.npz", load_scale=1.0)
    medium = _checkpoint(tmp_path / "medium.npz", load_scale=0.7)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[sub, medium, full],
        prefix_keys=("compact_checkpoint",),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=True,
        evidence_sources=(source,),
    )

    assert exit_code == 0
    assert payload["status"] == "ready_to_run"
    assert payload["full_load_input_pass"] is True
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["candidate_count"] == 3
    assert resolution["selection"]["loadable_count"] == 3
    assert resolution["selection"]["highest_observed_load_scale"] == 1.0
    assert resolution["selection"]["selected_checkpoint"]["path"] == str(full)
    assert resolution["selection"]["selection_reason"] == "full_load_candidate_selected"
    assert Path(payload["checkpoint"]["path"]) == full


def test_auto_select_picks_highest_sub_full_load_candidate(tmp_path: Path) -> None:
    low = _checkpoint(tmp_path / "low.npz", load_scale=0.4)
    medium = _checkpoint(tmp_path / "medium.npz", load_scale=0.7)
    higher_sub = _checkpoint(tmp_path / "higher_sub.npz", load_scale=0.95)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[low, medium, higher_sub],
        prefix_keys=("compact_checkpoint",),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert payload["full_load_input_pass"] is False
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["highest_observed_load_scale"] == 0.95
    assert (
        resolution["selection"]["selected_checkpoint"]["path"] == str(higher_sub)
    )
    assert (
        resolution["selection"]["selection_reason"]
        == "highest_sub_full_load_candidate_selected"
    )
    assert payload["checkpoint"]["load_scale"] == 0.95


def test_explicit_checkpoint_overrides_auto_selection(tmp_path: Path) -> None:
    explicit = _checkpoint(tmp_path / "explicit.npz", load_scale=0.656)
    full = _checkpoint(tmp_path / "full.npz", load_scale=1.0)
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[full],
        prefix_keys=("compact_checkpoint",),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        checkpoint_npz=explicit,
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
    )

    assert exit_code == 1
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "explicit"
    assert resolution["selection"] is None
    assert resolution["requested_path"] == str(explicit)
    assert Path(payload["checkpoint"]["path"]) == explicit
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]


def test_auto_select_ignores_generic_npz_path_records(tmp_path: Path) -> None:
    generic = _checkpoint(tmp_path / "generic_deleted_candidate.npz", load_scale=1.0)
    frontier = _checkpoint(tmp_path / "frontier.npz", load_scale=0.8)
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "test-evidence-source.v1",
                "documented_deleted_checkpoint_candidates": [
                    {"path": str(generic)},
                ],
                "latest_frontier_compact_checkpoint": str(frontier),
            }
        ),
        encoding="utf-8",
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=False,
        evidence_sources=(source,),
    )

    assert exit_code == 1
    selection = payload["checkpoint_resolution"]["selection"]
    assert selection["candidate_count"] == 1
    assert selection["selected_checkpoint"]["path"] == str(frontier)
    assert selection["highest_observed_load_scale"] == 0.8
    assert "checkpoint_load_scale_below_required_full_load" in payload["blockers"]


def test_auto_select_with_no_loadable_candidates_blocks(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    _write_evidence_source(
        source,
        candidates=[],
        prefix_keys=("compact_checkpoint",),
    )

    payload, exit_code = run_g1_full_load_hip_newton_lane.build_lane_report(
        output_json=tmp_path / "child.json",
        dry_run=True,
        evidence_sources=(source,),
    )

    assert exit_code == 1
    assert payload["status"] == "blocked"
    assert "auto_select_no_loadable_candidates" in payload["blockers"]
    resolution = payload["checkpoint_resolution"]
    assert resolution["mode"] == "auto_select"
    assert resolution["selection"]["selection_reason"] == "no_loadable_candidates"
    assert resolution["selection"]["selected_checkpoint"] is None


def test_cli_auto_select_default_and_auto_arg_use_evidence_scan(tmp_path: Path) -> None:
    out = tmp_path / "lane.json"
    default_args = run_g1_full_load_hip_newton_lane.build_parser().parse_args(
        ["--dry-run", "--out", str(out)]
    )
    assert default_args.checkpoint_npz is None

    args = run_g1_full_load_hip_newton_lane.build_parser().parse_args(
        ["--checkpoint-npz", "auto", "--dry-run", "--out", str(out)]
    )
    assert args.checkpoint_npz is None
    assert args.dry_run is True
