"""Original bytes and conservative enclosing-cost accounting for held-out slots."""

from copy import deepcopy

import pytest

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark import rc_control_heldout_runtime as heldout
from structural_analysis.benchmark import rc_control_heldout_lifecycle_costs as costs
from structural_analysis.benchmark.rc_control_process_costs import PROCESS_SCOPE
from tests.test_rc_control_heldout_runtime import records as heldout_records
from tests.test_rc_control_runtime_selection import original as runtime_original


@pytest.fixture(scope="module")
def source(tmp_path_factory):
    return runtime_original.__wrapped__(tmp_path_factory)


def _sealed(value, key):
    value = deepcopy(value)
    value[key] = _sha(_bytes(value))
    return value


def _put(root, name, value):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _bytes(value)
    path.write_bytes(raw)
    return {"path": name, "sha256": _sha(raw), "bytes": len(raw)}


def _packet(root, policy):
    source_revision = "a" * 40
    selection = _sealed(
        {
            "schema_version": "rc-control-runtime-selection-result.v2",
            "source_revision": source_revision,
            "selected_strategy": "learned_svd",
            "selected_policy": policy.to_dict(),
            "validation_or_holdout_execution": False,
            "new_training_labels": 0,
            "timing_scope": "validation_fits_all_four_path_fold_runs_comparisons_and_intermediate_IO_excluding_final_result_write",
            "wall_ns": 100,
            "cpu_ns": 80,
        },
        "result_hash",
    )
    plan = {
        "plan_hash": _sha(b"frozen synthetic plan"),
        "source_revision": source_revision,
        "selection_result_hash": selection["result_hash"],
        "policy_hash": policy.policy_hash,
        "training_cost_reuse_assumption": None,
        "cases": [
            {"case_id": "train-a", "split": "train"},
            {"case_id": "train-b", "split": "train"},
            {"case_id": "validation", "split": "validation"},
        ],
        "schedule": [
            {"slot_index": index, "case_id": "validation"} for index in range(3)
        ],
    }
    launchers = []
    for index in range(3):
        identity = [100 + index, 200 + index]
        started = {
            "plan_hash": plan["plan_hash"],
            "slot": plan["schedule"][index],
            "process_identity": identity,
            "status": "started",
        }
        outcome = {**started, "status": "completed", "wall_ns": 90, "cpu_ns": 50}
        start_ref = _put(root, f"slot-{index:04d}/started.json", started)
        outcome_ref = _put(root, f"slot-{index:04d}/outcome.json", outcome)
        launcher = _sealed(
            {
                "schema_version": costs.LAUNCHER_SCHEMA,
                "plan_hash": plan["plan_hash"],
                "source_revision": source_revision,
                "slot_index": index,
                "process_identity": identity,
                "started_file_sha256": start_ref["sha256"],
                "outcome_file_sha256": outcome_ref["sha256"],
                "return_code": 0,
                "scope": PROCESS_SCOPE,
                "wall_ns": 120 + index,
                "cpu_ns": None,
            },
            "launcher_hash",
        )
        launchers.append(
            {
                "slot_index": index,
                "file": _put(root, f"launchers/slot-{index:04d}.json", launcher),
            }
        )
    labels = []
    for index, case_id in enumerate(("train-a", "train-b")):
        label = _sealed(
            {
                "schema_version": "experimental-rc-control-learning-study.v1",
                "source_revision": "b" * 40,
                "evaluation_deferred": True,
                "timing_scope": "preflight_all_generation_reference_secant_fresh_verification_fit_deferred_evaluation_receipts_and_io_excluding_final_report_write",
                "training_case_ids": [case_id],
                "whole_study_wall_ns": 20 + index,
                "whole_study_cpu_ns": 10 + index,
            },
            "report_hash",
        )
        labels.append(
            {
                "file": _put(root, f"prior/label-{index}.json", label),
                "source_revision": "b" * 40,
            }
        )
    manifest = {
        "schema_version": costs.MANIFEST_SCHEMA,
        "plan_hash": plan["plan_hash"],
        "source_revision": source_revision,
        "selection_result_hash": selection["result_hash"],
        "launchers": launchers,
        "selection_receipt": _put(root, "prior/selection.json", selection),
        "label_receipts": labels,
        "training_cost_reuse_count": None,
    }
    _save_manifest(root, manifest)
    return plan, manifest


def _save_manifest(root, manifest):
    (root / "lifecycle-manifest.json").write_bytes(
        _bytes(_sealed(manifest, "manifest_hash"))
    )


@pytest.fixture
def packet(tmp_path, source, monkeypatch):
    plan, manifest = _packet(tmp_path, source[2])
    monkeypatch.setattr(
        costs,
        "audit_heldout_receipts",
        lambda _plan, _root: {"declared_denominator": 3, "unknown_or_missing_slots": 0},
    )
    return tmp_path, plan, manifest


def test_original_receipts_are_bound_and_process_enclosures_replace_slots(packet):
    root, plan, _ = packet
    audit = costs.audit_heldout_lifecycle_costs(plan, root)
    assert audit["all_declared_launcher_wall_ns_sum"] == 363
    assert audit["observed_launcher_wall_ns_sum"] == 363
    assert audit["launcher_cpu_ns_sum"] is None
    assert audit["prior_original_costs"]["known_prior_component_wall_ns_sum"] == 141
    assert audit["prior_original_costs"]["selection_nested_fits_added_again"] is False
    assert audit["launcher_intervals_are_campaign_elapsed_time"] is False
    assert audit["actual_total_evaluation_wall_ns"] is None
    assert audit["unknown_evaluation_cost"] is True
    assert audit["selected_strategy"] == "secant"
    assert audit["net_benefit_proved"] is False


def test_missing_launcher_keeps_denominator_and_total_unknown(packet):
    root, plan, manifest = packet
    manifest["launchers"].pop()
    _save_manifest(root, manifest)
    audit = costs.audit_heldout_lifecycle_costs(plan, root)
    assert audit["declared_denominator"] == 3
    assert len(audit["launcher_observations"]) == 2
    assert audit["all_declared_launcher_wall_ns_sum"] is None
    assert audit["launcher_observations_complete"] is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("source_revision", "c" * 40, "source-bound launcher"),
        ("wall_ns", 89, "does not enclose"),
        ("cpu_ns", 99, "source-bound launcher"),
        ("outcome_file_sha256", _sha(b"foreign"), "original slot"),
        ("scope", "slot_only", "source-bound launcher"),
    ],
)
def test_resealed_launcher_cannot_change_source_scope_or_containment(
    packet, field, value, message
):
    root, plan, manifest = packet
    entry = manifest["launchers"][0]
    launcher_path = root / entry["file"]["path"]
    launcher = costs._read_receipt(launcher_path)
    launcher[field] = value
    launcher.pop("launcher_hash")
    entry["file"] = _put(
        root, entry["file"]["path"], _sealed(launcher, "launcher_hash")
    )
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match=message):
        costs.audit_heldout_lifecycle_costs(plan, root)


def test_nonzero_launcher_exit_remains_measured_but_ineligible(packet):
    root, plan, manifest = packet
    entry = manifest["launchers"][1]
    launcher = costs._read_receipt(root / entry["file"]["path"])
    launcher["return_code"] = 2
    launcher.pop("launcher_hash")
    entry["file"] = _put(
        root, entry["file"]["path"], _sealed(launcher, "launcher_hash")
    )
    _save_manifest(root, manifest)
    audit = costs.audit_heldout_lifecycle_costs(plan, root)
    assert audit["all_declared_launcher_wall_ns_sum"] == 363
    assert audit["launcher_exits_successful"] is False
    assert audit["net_benefit_proved"] is False


def test_changed_original_bytes_and_undeclared_reuse_are_rejected(packet):
    root, plan, manifest = packet
    path = root / manifest["selection_receipt"]["path"]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="byte binding"):
        costs.audit_heldout_lifecycle_costs(plan, root)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    manifest["training_cost_reuse_count"] = 10
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match="frozen plan"):
        costs.audit_heldout_lifecycle_costs(plan, root)


def test_original_label_roster_and_canonical_paths_are_required(packet):
    root, plan, manifest = packet
    manifest["label_receipts"].pop()
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match="training roster"):
        costs.audit_heldout_lifecycle_costs(plan, root)
    manifest["label_receipts"] = [
        {
            "source_revision": "b" * 40,
            "file": {
                "path": "prior//label-0.json",
                "sha256": "sha256:" + "0" * 64,
                "bytes": 1,
            },
        }
    ]
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match="packet-relative"):
        costs.audit_heldout_lifecycle_costs(plan, root)


def test_original_slot_symlink_cannot_supply_launcher_binding(packet):
    root, plan, _ = packet
    (root / "slot-0000").rename(root / "moved-slot")
    (root / "slot-0000").symlink_to("moved-slot", target_is_directory=True)
    with pytest.raises(ValueError, match="slot receipt symlink"):
        costs.audit_heldout_lifecycle_costs(plan, root)


def test_distinct_fresh_process_identity_is_required_even_after_resealing(packet):
    root, plan, manifest = packet
    identity = costs._read_receipt(root / "slot-0000/started.json")["process_identity"]
    index = 1
    started_path = root / f"slot-{index:04d}/started.json"
    outcome_path = root / f"slot-{index:04d}/outcome.json"
    started = costs._read_receipt(started_path)
    outcome = costs._read_receipt(outcome_path)
    started["process_identity"] = identity
    outcome["process_identity"] = identity
    start_ref = _put(root, f"slot-{index:04d}/started.json", started)
    outcome_ref = _put(root, f"slot-{index:04d}/outcome.json", outcome)
    entry = manifest["launchers"][index]
    launcher = costs._read_receipt(root / entry["file"]["path"])
    launcher.update(
        process_identity=identity,
        started_file_sha256=start_ref["sha256"],
        outcome_file_sha256=outcome_ref["sha256"],
    )
    launcher.pop("launcher_hash")
    entry["file"] = _put(
        root, entry["file"]["path"], _sealed(launcher, "launcher_hash")
    )
    _save_manifest(root, manifest)
    with pytest.raises(ValueError, match="identities must be distinct"):
        costs.audit_heldout_lifecycle_costs(plan, root)


def test_actual_original_slot_audit_precedes_lifecycle_cost_accounting(
    tmp_path, source, monkeypatch
):
    selection = _sealed(
        {
            "source_revision": "a" * 40,
            "selected_strategy": "learned_svd",
            "selected_policy": source[2].to_dict(),
            "validation_or_holdout_execution": False,
        },
        "result_hash",
    )
    plan = heldout.declare_heldout_runtime(
        source[0],
        selection,
        heldout_records(source),
        source_revision="a" * 40,
        evaluation_case_ids=["validation"],
        arithmetic_profile="retained-twofold-refinement.v1",
    )
    monkeypatch.setattr(heldout, "_require_clean_source", lambda _: None)
    monkeypatch.setattr(heldout, "_CLAIMED_PROCESS_ID", None)
    outcome = heldout.run_heldout_slot(
        plan,
        source[0],
        selection,
        slot_index=0,
        output_directory=tmp_path / "slot-0000",
    )
    assert outcome["status"] == "completed"
    started_raw = (tmp_path / "slot-0000/started.json").read_bytes()
    outcome_raw = (tmp_path / "slot-0000/outcome.json").read_bytes()
    launcher = _sealed(
        {
            "schema_version": costs.LAUNCHER_SCHEMA,
            "plan_hash": plan["plan_hash"],
            "source_revision": plan["source_revision"],
            "slot_index": 0,
            "process_identity": outcome["process_identity"],
            "started_file_sha256": _sha(started_raw),
            "outcome_file_sha256": _sha(outcome_raw),
            "return_code": 0,
            "scope": PROCESS_SCOPE,
            "wall_ns": outcome["wall_ns"] + 100,
            "cpu_ns": None,
        },
        "launcher_hash",
    )
    manifest = {
        "schema_version": costs.MANIFEST_SCHEMA,
        "plan_hash": plan["plan_hash"],
        "source_revision": plan["source_revision"],
        "selection_result_hash": plan["selection_result_hash"],
        "launchers": [
            {
                "slot_index": 0,
                "file": _put(tmp_path, "launchers/slot-0000.json", launcher),
            }
        ],
        "selection_receipt": None,
        "label_receipts": [],
        "training_cost_reuse_count": None,
    }
    _save_manifest(tmp_path, manifest)
    audit = costs.audit_heldout_lifecycle_costs(plan, tmp_path)
    assert audit["original_slot_audit"]["complete_verified_slots"] == 1
    assert audit["declared_denominator"] == 3
    assert audit["all_declared_launcher_wall_ns_sum"] is None
    assert audit["prior_original_costs"] is None
    assert audit["net_benefit_proved"] is False
