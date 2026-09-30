"""The 80 mm research receipt keeps failed work and frozen parents visible."""

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_rc_public_portal_80mm_recovery.py"
SPEC = importlib.util.spec_from_file_location("portal_recovery_80mm", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def _invocation(*, committed=False, seed=False):
    return {
        "status": "returned",
        "seed_used": seed,
        "committed": committed,
        "rollback_exact": not committed,
        "unknown_work": False,
        "work": {"core_calls": 1, "linear_solves": 1, "newton_iterations": 1},
    }


def _numerical(parent, *, seed):
    return {
        "parent_hash": parent,
        "parent_unchanged": True,
        "intermediate_material_checkpoints_adopted": False,
        "status": "returned" if seed else "blocked",
        "reason": None if seed else "minimum_fraction_increment",
        "seed": [0.0] if seed else None,
        "native_core_calls_attempted": 1,
        "stages": [{
            "parent_hash": parent, "unknown_work": False,
            "linear_solves": 1, "newton_iterations": 1,
        }],
    }


def _report():
    first, second = "sha256:first", "sha256:second"
    ordinary = {
        "status": "incomplete",
        "accepted_target_count": 0,
        "preload_invocations": [_invocation(committed=True)],
        "entries": [{"invocations": [_invocation()]}],
    }
    proposal = {
        "status": "incomplete",
        "accepted_target_count": 1,
        "preload_invocations": [_invocation(committed=True)],
        "entries": [
            {
                "target_m": -0.04,
                "parent_hash": first,
                "invocations": [_invocation(), _invocation(committed=True, seed=True)],
                "numerical_proposal": _numerical(first, seed=True),
            },
            {
                "target_m": -0.08,
                "parent_hash": second,
                "invocations": [_invocation()],
                "numerical_proposal": _numerical(second, seed=False),
            },
        ],
    }
    return {
        "arms": {"reference": deepcopy(ordinary), "secant": deepcopy(ordinary), "proposal": proposal},
        "fresh_reference": deepcopy(ordinary),
        "source_revision": "0" * 40,
        "report_hash": "sha256:synthetic",
        "all_execution_work_reported": True,
        "numerical_proposal": {"identity": "synthetic-frozen-parent"},
        "numerical_proposal_work": {
            "native_core_calls_attempted": 2,
            "known_linear_solves": 2,
            "known_newton_iterations": 2,
            "unknown_work": False,
        },
    }


def test_pinned_public_portal_inputs_retain_exact_model_and_80mm_request():
    model_bytes, request_bytes, _, request = study.pinned_inputs()
    assert study._hash(model_bytes) == study.MODEL_SHA256
    assert study._hash(request_bytes) == study.REQUEST_SHA256
    assert request.targets_m == study.TARGETS_M


def test_source_revision_uses_the_script_repository_from_any_cwd(monkeypatch, tmp_path):
    observed = {}

    def fake_check_output(command, *, text, cwd):
        observed.update(command=command, text=text, cwd=cwd)
        return "a" * 40 + "\n"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(study.subprocess, "check_output", fake_check_output)
    assert study._source_revision() == "a" * 40
    assert observed == {
        "command": ["git", "rev-parse", "HEAD"],
        "text": True,
        "cwd": study.REPO_ROOT,
    }


def test_whole_comparison_source_binding_rejects_rewritten_request(tmp_path):
    _, _, model, request = study.pinned_inputs()
    revision = "0" * 40
    identity = {
        "source_revision": revision,
        "source_revision_is_attestation": False,
        "request": request.to_dict(),
        "model_checksum": model.canonical_model_checksum,
        "compiler_profile": study.EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE,
    }
    report = dict(identity)
    report["report_hash"] = "sha256:" + study._hash(study._canonical(identity))
    (tmp_path / "request.json").write_bytes(study._canonical(identity))
    (tmp_path / "model.json").write_bytes(study._canonical(model.canonical_payload()))
    (tmp_path / "comparison.json").write_bytes(study._canonical(report))
    study.validate_comparison_source_binding(report, tmp_path, model, request, revision)
    modified = deepcopy(report)
    modified["request"]["targets_m"][0] = -0.01
    modified["report_hash"] = "sha256:" + study._hash(
        study._canonical({key: value for key, value in modified.items() if key != "report_hash"})
    )
    (tmp_path / "comparison.json").write_bytes(study._canonical(modified))
    with pytest.raises(ValueError, match="source binding"):
        study.validate_comparison_source_binding(modified, tmp_path, model, request, revision)


def test_outcome_charges_all_arms_and_failed_second_target():
    receipt = study.summarize(_report())
    assert receipt["known_native_calls_attempted"] == 12
    assert receipt["known_linear_solves"] == 12
    assert receipt["unknown_solver_work_attempt_count"] == 0
    assert receipt["accepted_target_counts"]["proposal"] == 1
    assert receipt["original_failed_attempt"]["rollback_exact"] is True
    assert [row["status"] for row in receipt["recovery_by_attempted_target"]] == [
        "returned", "blocked"
    ]
    assert receipt["public_80mm_completion_established"] is False


def test_unknown_solver_counts_keep_call_reservation_and_other_known_work():
    report = _report()
    invocation = report["arms"]["secant"]["entries"][0]["invocations"][0]
    invocation["unknown_work"] = True
    invocation["work"]["linear_solves"] = None
    invocation["work"]["newton_iterations"] = None
    report["all_execution_work_reported"] = False
    receipt = study.summarize(report)
    assert receipt["known_native_calls_attempted"] == 12
    assert receipt["known_linear_solves"] == 11
    assert receipt["unknown_solver_work_attempt_count"] == 1
    assert receipt["unknown_work"] is True


def test_unknown_continuation_counts_keep_trial_reservation_and_known_work():
    report = _report()
    stage = report["arms"]["proposal"]["entries"][1]["numerical_proposal"]["stages"][0]
    stage.update(unknown_work=True, linear_solves=None, newton_iterations=None)
    proposal_work = report["numerical_proposal_work"]
    proposal_work.update(
        known_linear_solves=1,
        known_newton_iterations=1,
        unknown_work=True,
    )
    report["all_execution_work_reported"] = False
    receipt = study.summarize(report)
    assert receipt["known_native_calls_attempted"] == 12
    assert receipt["known_linear_solves"] == 11
    assert receipt["known_newton_iterations"] == 11
    assert receipt["unknown_solver_work_attempt_count"] == 1
    assert receipt["unknown_work"] is True


def test_trial_artifact_audit_rejects_a_rebound_failed_checkpoint(tmp_path):
    report = _report()
    proposal = report["arms"]["proposal"]
    proposal["entries"] = proposal["entries"][:1]
    entry = proposal["entries"][0]
    entry["invocations"] = [_invocation()]
    entry["numerical_proposal"]["seed"] = None
    arm = tmp_path / "proposal"
    arm.mkdir()
    parent = {"state_hash": entry["parent_hash"]}
    failed = {
        "parent_checkpoint": parent,
        "accepted_checkpoint": parent,
        "committed": False,
        "metrics": {"rollback_exact": True},
    }
    study._write(arm / "000-1-step.json", failed)
    stage_path = arm / "000-continuation-000.json"
    study._write(stage_path, failed)
    raw = stage_path.read_bytes()
    stage = entry["numerical_proposal"]["stages"][0]
    stage.update(
        committed=False,
        artifact={
            "path": stage_path.name,
            "byte_length": len(raw),
            "sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
        },
    )
    assert study.audit_trial_artifacts(report, tmp_path) == {
        "continuation_trials_byte_bound_and_parent_rollback_checked": 1,
        "direct_steps_parent_rollback_checked": 1,
    }
    tampered = json.loads(raw)
    tampered["accepted_checkpoint"] = {"state_hash": "sha256:wrong"}
    study._write(stage_path, tampered)
    raw = stage_path.read_bytes()
    stage["artifact"].update(
        byte_length=len(raw), sha256="sha256:" + hashlib.sha256(raw).hexdigest()
    )
    with pytest.raises(ValueError, match="rollback"):
        study.audit_trial_artifacts(report, tmp_path)


@pytest.mark.parametrize("mutation", ["direct_rollback", "stage_parent", "adopted_state"])
def test_outcome_rejects_erased_failure_or_mutable_parent(mutation):
    report = _report()
    first = report["arms"]["proposal"]["entries"][0]
    if mutation == "direct_rollback":
        first["invocations"][0]["rollback_exact"] = False
    elif mutation == "stage_parent":
        first["numerical_proposal"]["stages"][0]["parent_hash"] = "sha256:other"
    else:
        first["numerical_proposal"]["intermediate_material_checkpoints_adopted"] = True
    with pytest.raises(ValueError):
        study.summarize(report)
