"""Held-out admission and full-path receipt accounting without reserved runs."""

from copy import deepcopy
import json

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark import rc_control_heldout_runtime as heldout
from tests.test_rc_control_runtime_selection import original as runtime_original


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    return runtime_original.__wrapped__(tmp_path_factory)


def selected(original):
    policy = original[2]
    result = {
        "source_revision": "a" * 40,
        "selected_strategy": "learned_svd",
        "selected_policy": policy.to_dict(),
        "validation_or_holdout_execution": False,
    }
    result["result_hash"] = _sha(_bytes(result))
    return result


def records(original):
    return {
        case.case_id: {
            "original_record_hash": _sha(case.case_id.encode()),
            "rights_review_hash": _sha((case.case_id + "-review").encode()),
            "lineage_group_id": case.case_id,
            "rights_status": "training_permitted" if case.split == "train" else "evaluation_permitted",
            "source_role": "original",
        }
        for case in original[0]
    }


def plan(original):
    return heldout.declare_heldout_runtime(
        original[0], selected(original), records(original),
        source_revision="a" * 40, evaluation_case_ids=["validation"],
        arithmetic_profile="retained-twofold-refinement.v1",
    )


def test_admission_freezes_balanced_roster_and_rejects_ineligible_policy(original):
    frozen = plan(original)
    assert frozen["failure_denominator"] == 3
    assert [slot["arm_order"] for slot in frozen["schedule"]] == [
        ["reference", "secant", "proposal"],
        ["secant", "proposal", "reference"],
        ["proposal", "reference", "secant"],
    ]
    rejected = selected(original)
    rejected["selected_strategy"] = "secant"
    rejected["selected_policy"] = None
    rejected["result_hash"] = _sha(_bytes({k: v for k, v in rejected.items() if k != "result_hash"}))
    with pytest.raises(ValueError, match="learned development selection"):
        heldout.declare_heldout_runtime(
            original[0], rejected, records(original),
            source_revision="a" * 40, evaluation_case_ids=["validation"],
        )
    connected = records(original)
    connected["validation"]["lineage_group_id"] = "train-a"
    with pytest.raises(ValueError, match="lineage group crosses"):
        heldout.declare_heldout_runtime(
            original[0], selected(original), connected,
            source_revision="a" * 40, evaluation_case_ids=["validation"],
            arithmetic_profile="retained-twofold-refinement.v1",
        )


def test_one_actual_full_path_slot_and_missing_repetitions_remain_in_denominator(
    original, tmp_path, monkeypatch
):
    frozen = plan(original)
    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: None)
    outcome = heldout.run_heldout_slot(
        frozen, original[0], selected(original), slot_index=0,
        output_directory=tmp_path / "slot-0000",
    )
    assert outcome["status"] == "completed"
    assert outcome["report_hash"]
    assert (tmp_path / "slot-0000/benchmark/comparison.json").exists()
    summary = heldout.summarize_heldout_runtime(frozen, {0: outcome})
    assert summary["declared_denominator"] == 3
    assert summary["unknown_or_missing_slots"] == 2
    assert summary["selected_strategy"] == "secant"
    assert not summary["net_benefit_proved"]
    audited = heldout.audit_heldout_receipts(frozen, tmp_path)
    assert audited["declared_denominator"] == 3
    assert audited["cases"][0]["mean_path_ratio"] is None
    report_path = tmp_path / "slot-0000/benchmark/comparison.json"
    changed = json.loads(report_path.read_text())
    changed["model_checksum"] = "sha256:" + "0" * 64
    report_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="original report binding"):
        heldout.audit_heldout_receipts(frozen, tmp_path)


def test_raised_slot_and_fallback_only_never_receive_ratio(original, tmp_path, monkeypatch):
    frozen = plan(original)
    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: None)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic interruption")

    monkeypatch.setattr(heldout.learning, "benchmark_rc_control_seed_paths", fail)
    outcome = heldout.run_heldout_slot(
        frozen, original[0], selected(original), slot_index=0,
        output_directory=tmp_path / "slot-0000",
    )
    assert outcome["status"] == "raised"
    assert outcome["unknown_work_until_outcome"]
    assert (tmp_path / "slot-0000/started.json").exists()
    assert (tmp_path / "slot-0000/outcome.json").exists()
    summary = heldout.summarize_heldout_runtime(frozen, {0: outcome})
    assert summary["slots"][0]["path_ratio"] is None
    assert summary["unknown_or_missing_slots"] == 3
    assert heldout.audit_heldout_receipts(frozen, tmp_path)["unknown_or_missing_slots"] == 3
    (tmp_path / "slot-0000/outcome.json").unlink()
    interrupted = heldout.audit_heldout_receipts(frozen, tmp_path)
    assert interrupted["slots"][0]["status"] == "interrupted"
    assert interrupted["unknown_or_missing_slots"] == 3
    fallback = deepcopy(outcome)
    fallback.update(
        status="completed", unknown_work_until_outcome=False,
        score={"full_comparison_pass": True,
               "execution_work": {"unknown_work": False},
               "proposed_count": 0,
               "proposal_over_secant_path_wall_ratio": 0.5},
    )
    assert heldout.summarize_heldout_runtime(frozen, {0: fallback})["slots"][0]["path_ratio"] is None


def test_only_attempted_learned_seeds_count_as_actual_proposals():
    report = {"arms": {"proposal": {"entries": [
        {"proposal_decision": "proposed", "proposal": [0.0]},
        {"proposal_decision": "invalid_proposal_to_reference", "proposal": None},
        {"proposal_decision": "abstained_to_secant", "proposal": [0.0]},
    ]}}}
    assert heldout._actual_proposal_count(report) == 1
