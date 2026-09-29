"""Held-out admission and full-path receipt accounting without reserved runs."""

from copy import deepcopy
import json

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark import rc_control_heldout_runtime as heldout
from tests.test_rc_control_runtime_selection import original as runtime_original


@pytest.fixture(autouse=True)
def reset_synthetic_process_claim(monkeypatch):
    monkeypatch.setattr(heldout, "_CLAIMED_PROCESS_ID", None)


@pytest.fixture(scope="module")
def original(tmp_path_factory):
    return runtime_original.__wrapped__(tmp_path_factory)


def selected(original, *, reuse_assembly=False):
    policy = original[2]
    result = {
        "source_revision": "a" * 40,
        "selected_strategy": "learned_svd",
        "selected_policy": policy.to_dict(),
        "validation_or_holdout_execution": False,
    }
    if reuse_assembly:
        result["line_search_assembly_reuse"] = "rc-control-immediate-line-search-reuse.v1"
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


def plan(original, *, reuse_assembly=False):
    return heldout.declare_heldout_runtime(
        original[0], selected(original, reuse_assembly=reuse_assembly), records(original),
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


@pytest.mark.parametrize("reuse_mode", ["legacy", False, True])
def test_one_actual_full_path_slot_and_missing_repetitions_remain_in_denominator(
    original, tmp_path, monkeypatch, reuse_mode
):
    reuse = reuse_mode is True
    choice = selected(original, reuse_assembly=reuse)
    frozen = plan(original, reuse_assembly=reuse)
    if reuse_mode == "legacy":
        frozen["schema_version"] = "rc-heldout-runtime-plan.v1"
        frozen.pop("execution_profile")
        frozen["plan_hash"] = _sha(_bytes({
            k: v for k, v in frozen.items() if k != "plan_hash"
        }))
    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: None)
    outcome = heldout.run_heldout_slot(
        frozen, original[0], choice, slot_index=0,
        output_directory=tmp_path / "slot-0000",
    )
    assert outcome["status"] == "completed"
    assert outcome["report_hash"]
    assert (tmp_path / "slot-0000/benchmark/comparison.json").exists()
    with pytest.raises(ValueError, match="fresh process"):
        heldout.run_heldout_slot(
            frozen, original[0], choice, slot_index=1,
            output_directory=tmp_path / "slot-0001",
        )
    assert not (tmp_path / "slot-0001").exists()
    summary = heldout.summarize_heldout_runtime(frozen, {0: outcome})
    assert summary["declared_denominator"] == 3
    assert summary["unknown_or_missing_slots"] == 2
    assert summary["selected_strategy"] == "secant"
    assert not summary["net_benefit_proved"]
    audited = heldout.audit_heldout_receipts(frozen, tmp_path)
    assert audited["declared_denominator"] == 3
    assert audited["cases"][0]["mean_path_ratio"] is None
    assert audited["separate_audit"]["wall_ns"] > 0
    step_path = next((tmp_path / "slot-0000/benchmark/secant").glob("*-step.json"))
    step_bytes = step_path.read_bytes()
    step_path.write_bytes(step_bytes + b"\n")
    with pytest.raises(ValueError, match="original slot receipt inventory"):
        heldout.audit_heldout_receipts(frozen, tmp_path)
    step_path.write_bytes(step_bytes)
    report_path = tmp_path / "slot-0000/benchmark/comparison.json"
    report_bytes = report_path.read_bytes()
    changed = json.loads(report_path.read_text())
    changed["model_checksum"] = "sha256:" + "0" * 64
    report_path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="original slot receipt inventory"):
        heldout.audit_heldout_receipts(frozen, tmp_path)
    report_path.write_bytes(report_bytes)

    # A coherent report/outcome/inventory reseal cannot change the frozen
    # assembly profile, in either direction or for a historical v1 plan.
    original_report = json.loads(report_bytes)
    assert ("line_search_assembly_reuse" in original_report) is reuse
    assert all(row["full_history_pass"] for row in original_report["comparisons"].values())
    outcome_path = tmp_path / "slot-0000/outcome.json"
    inventory_path = tmp_path / "slot-0000/receipt-inventory.json"
    original_outcome = outcome_path.read_bytes()
    original_inventory = inventory_path.read_bytes()
    profile_tampered = deepcopy(original_report)
    if reuse:
        profile_tampered.pop("line_search_assembly_reuse")
    else:
        profile_tampered["line_search_assembly_reuse"] = (
            "rc-control-immediate-line-search-reuse.v1"
        )
    profile_tampered["report_hash"] = _sha(_bytes({
        k: v for k, v in profile_tampered.items() if k != "report_hash"
    }))
    report_path.write_bytes(_bytes(profile_tampered))
    changed_outcome = json.loads(original_outcome)
    changed_outcome["report_hash"] = profile_tampered["report_hash"]
    inventory = heldout._receipt_inventory(tmp_path / "slot-0000", frozen["plan_hash"], 0)
    inventory_path.write_bytes(_bytes(inventory))
    changed_outcome["receipt_inventory_hash"] = inventory["inventory_hash"]
    outcome_path.write_bytes(_bytes(changed_outcome))
    with pytest.raises(ValueError, match="full-path original report binding mismatch"):
        heldout.audit_heldout_receipts(frozen, tmp_path)
    report_path.write_bytes(report_bytes)
    outcome_path.write_bytes(original_outcome)
    inventory_path.write_bytes(original_inventory)

    # request.json is the independently stored producer identity. A coherent
    # inventory/outcome reseal cannot contradict the authenticated comparison,
    # including historical identity fields and either assembly-profile value.
    request_path = tmp_path / "slot-0000/benchmark/request.json"
    request_bytes = request_path.read_bytes()
    original_request = json.loads(request_bytes)
    assert ("line_search_assembly_reuse" in original_request) is reuse
    request_mutations = []
    for key in original_request:
        missing = deepcopy(original_request)
        missing.pop(key)
        request_mutations.append(("missing " + key, missing))
        changed_identity = deepcopy(original_request)
        changed_identity[key] = None
        request_mutations.append(("null " + key, changed_identity))
    for marker in (False, True, "unknown-profile", "rc-control-immediate-line-search-reuse.v1"):
        if marker == original_request.get("line_search_assembly_reuse"):
            continue
        changed_identity = deepcopy(original_request)
        changed_identity["line_search_assembly_reuse"] = marker
        request_mutations.append(("profile " + str(marker), changed_identity))
    changed_identity = deepcopy(original_request)
    changed_identity["unexpected_original_field"] = False
    request_mutations.append(("extra identity field", changed_identity))
    # Python equality treats False == 0: identity binding must preserve the
    # producer's actual JSON types as well as its values.
    changed_identity = deepcopy(original_request)
    changed_identity["source_revision_is_attestation"] = 0
    request_mutations.append(("changed JSON type", changed_identity))
    for _mutation, changed_identity in request_mutations:
        request_path.write_bytes(_bytes(changed_identity))
        inventory = heldout._receipt_inventory(tmp_path / "slot-0000", frozen["plan_hash"], 0)
        inventory_path.write_bytes(_bytes(inventory))
        changed_outcome = json.loads(original_outcome)
        changed_outcome["receipt_inventory_hash"] = inventory["inventory_hash"]
        outcome_path.write_bytes(_bytes(changed_outcome))
        with pytest.raises(ValueError, match="original benchmark request differs"):
            heldout.audit_heldout_receipts(frozen, tmp_path)
        request_path.write_bytes(request_bytes)
        outcome_path.write_bytes(original_outcome)
        inventory_path.write_bytes(original_inventory)
    assert report_path.read_bytes() == report_bytes
    assert heldout.audit_heldout_receipts(frozen, tmp_path)["declared_denominator"] == 3

    # Rehashing a forged report and its file inventory still cannot forge the
    # independently recomputed verdict over the original response histories.
    changed = json.loads(report_bytes)
    changed["comparisons"]["secant"]["mismatch_locations"]["mismatch_count"] += 1
    changed["report_hash"] = _sha(_bytes({
        key: value for key, value in changed.items() if key != "report_hash"
    }))
    report_path.write_bytes(_bytes(changed))
    outcome_path = tmp_path / "slot-0000/outcome.json"
    stored = json.loads(outcome_path.read_bytes())
    stored["report_hash"] = changed["report_hash"]
    inventory = heldout._receipt_inventory(tmp_path / "slot-0000", frozen["plan_hash"], 0)
    (tmp_path / "slot-0000/receipt-inventory.json").write_bytes(_bytes(inventory))
    stored["receipt_inventory_hash"] = inventory["inventory_hash"]
    outcome_path.write_bytes(_bytes(stored))
    with pytest.raises(ValueError, match="stored comparison differs from original full histories"):
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
        {"proposal_decision": "proposed", "proposal": [0.0],
         "invocations": [{"seed_used": True, "status": "returned"}]},
        {"proposal_decision": "proposed", "proposal": [0.0],
         "invocations": [{"seed_used": True, "status": "raised"}]},
        {"proposal_decision": "proposed", "proposal": [0.0], "invocations": []},
        {"proposal_decision": "invalid_proposal_to_reference", "proposal": None},
        {"proposal_decision": "abstained_to_secant", "proposal": [0.0],
         "invocations": [{"seed_used": True, "status": "returned"}]},
    ]}}}
    assert heldout._actual_proposal_count(report) == 2


def test_selected_assembly_reuse_reaches_slot_benchmark(original, tmp_path, monkeypatch):
    frozen = plan(original, reuse_assembly=True)
    observed = []

    def observe(*args, **kwargs):
        observed.append(kwargs.get("reuse_line_search_assembly", False))
        raise RuntimeError("stop after observing execution profile")

    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: None)
    monkeypatch.setattr(heldout.learning, "benchmark_rc_control_seed_paths", observe)
    outcome = heldout.run_heldout_slot(
        frozen, original[0], selected(original, reuse_assembly=True), slot_index=0,
        output_directory=tmp_path / "slot-0000",
    )
    assert observed == [True]
    assert outcome["status"] == "raised"
    assert outcome["unknown_work_until_outcome"] is True
    summary = heldout.audit_heldout_receipts(frozen, tmp_path)
    assert summary["declared_denominator"] == 3
    assert summary["unknown_or_missing_slots"] == 3
    assert summary["actual_total_evaluation_wall_ns"] is None
    assert summary["selected_strategy"] == "secant"


@pytest.mark.parametrize("reuse", [False, True])
def test_new_plan_binds_explicit_versioned_execution_profile(original, reuse):
    frozen = plan(original, reuse_assembly=reuse)
    assert frozen["schema_version"] == "rc-heldout-runtime-plan.v2"
    assert frozen["execution_profile"] == {
        "schema_version": "rc-heldout-execution-profile.v1",
        "reuse_line_search_assembly": reuse,
    }
    assert frozen["plan_hash"] == _sha(_bytes({
        k: v for k, v in frozen.items() if k != "plan_hash"
    }))


@pytest.mark.parametrize("profile", [None, False, True, "unknown-profile"])
def test_unknown_selected_assembly_profile_is_not_treated_as_false(original, profile):
    choice = selected(original)
    choice["line_search_assembly_reuse"] = profile
    choice["result_hash"] = _sha(_bytes({
        k: v for k, v in choice.items() if k != "result_hash"
    }))
    with pytest.raises(ValueError, match="unsupported selected line-search"):
        heldout.declare_heldout_runtime(
            original[0], choice, records(original), source_revision="a" * 40,
            evaluation_case_ids=["validation"],
            arithmetic_profile="retained-twofold-refinement.v1",
        )


@pytest.mark.parametrize("downgrade", [False, True])
def test_resealed_or_legacy_plan_cannot_drop_selected_reuse_before_start(
    original, tmp_path, monkeypatch, downgrade
):
    choice = selected(original, reuse_assembly=True)
    frozen = plan(original, reuse_assembly=True)
    if downgrade:
        frozen["schema_version"] = "rc-heldout-runtime-plan.v1"
        frozen.pop("execution_profile")
    else:
        frozen["execution_profile"]["reuse_line_search_assembly"] = False
    frozen["plan_hash"] = _sha(_bytes({
        k: v for k, v in frozen.items() if k != "plan_hash"
    }))
    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: pytest.fail("source check reached"))
    with pytest.raises(ValueError, match="execution profile differs"):
        heldout.run_heldout_slot(
            frozen, original[0], choice, slot_index=0,
            output_directory=tmp_path / "slot-0000",
        )
    assert not (tmp_path / "slot-0000").exists()


@pytest.mark.parametrize("mutation", ["unknown-plan", "unknown-profile", "integer", "extra", "v1-profile"])
def test_malformed_profile_is_rejected_even_for_empty_audit(original, tmp_path, mutation):
    frozen = plan(original)
    if mutation == "unknown-plan":
        frozen["schema_version"] = "rc-heldout-runtime-plan.v999"
    elif mutation == "unknown-profile":
        frozen["execution_profile"]["schema_version"] = "unknown"
    elif mutation == "integer":
        frozen["execution_profile"]["reuse_line_search_assembly"] = 0
    elif mutation == "extra":
        frozen["execution_profile"]["unknown"] = False
    else:
        frozen["schema_version"] = "rc-heldout-runtime-plan.v1"
    frozen["plan_hash"] = _sha(_bytes({
        k: v for k, v in frozen.items() if k != "plan_hash"
    }))
    with pytest.raises(ValueError, match="schema|execution profile"):
        heldout.audit_heldout_receipts(frozen, tmp_path)
