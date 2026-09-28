"""Original-file audit of RC held-out process and prior development costs.

This ledger adds measured enclosing intervals to the guarded slot audit. A
process interval replaces its nested slot interval; it is never added to it.
Original file integrity does not authenticate the producer, source rights, or
physical validity, and this module cannot promote a learned policy.
"""

from pathlib import Path, PurePosixPath

from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_heldout_runtime import (
    _read_receipt,
    audit_heldout_receipts,
)
from structural_analysis.benchmark.rc_control_process_costs import PROCESS_SCOPE


MANIFEST_SCHEMA = "rc-heldout-lifecycle-manifest.v1"
LAUNCHER_SCHEMA = "rc-heldout-launcher-observation.v1"


def _positive(value):
    return type(value) is int and value > 0


def _nonnegative(value):
    return type(value) is int and value >= 0


def _checked_self_hash(value, key):
    if type(value) is not dict or value.get(key) != _sha(
        _bytes({k: v for k, v in value.items() if k != key})
    ):
        raise ValueError(f"original {key} mismatch")


def _original_file(root, reference, used_paths):
    """Read one packet-local original with an exact, non-symlink byte binding."""
    if type(reference) is not dict or set(reference) != {"path", "sha256", "bytes"}:
        raise ValueError("exact original file reference required")
    relative = reference["path"]
    if type(relative) is not str or not relative or "\\" in relative:
        raise ValueError("packet-relative original path required")
    name = PurePosixPath(relative)
    if (
        name.is_absolute()
        or name.as_posix() != relative
        or any(part in ("", ".", "..") for part in relative.split("/"))
    ):
        raise ValueError("packet-relative original path required")
    if relative in used_paths:
        raise ValueError("duplicate original file reference")
    used_paths.add(relative)
    path = root
    for part in name.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("original file symlink is not allowed")
    if not path.is_file():
        raise ValueError("original file is missing")
    raw = path.read_bytes()
    if (
        not _nonnegative(reference["bytes"])
        or len(raw) != reference["bytes"]
        or reference["sha256"] != _sha(raw)
    ):
        raise ValueError("original file byte binding mismatch")
    return _read_receipt(path), raw


def _launcher(root, entry, plan, slot, used_paths):
    if type(entry) is not dict or set(entry) != {"slot_index", "file"}:
        raise ValueError("exact launcher entry required")
    if (
        type(entry["slot_index"]) is not int
        or entry["slot_index"] != slot["slot_index"]
    ):
        raise ValueError("launcher schedule mismatch")
    observed, raw = _original_file(root, entry["file"], used_paths)
    _checked_self_hash(observed, "launcher_hash")
    if (
        set(observed)
        != {
            "schema_version",
            "plan_hash",
            "source_revision",
            "slot_index",
            "process_identity",
            "started_file_sha256",
            "outcome_file_sha256",
            "return_code",
            "scope",
            "wall_ns",
            "cpu_ns",
            "launcher_hash",
        }
        or observed["schema_version"] != LAUNCHER_SCHEMA
        or observed["plan_hash"] != plan["plan_hash"]
        or observed["source_revision"] != plan["source_revision"]
        or observed["slot_index"] != slot["slot_index"]
        or type(observed["process_identity"]) is not list
        or len(observed["process_identity"]) != 2
        or any(not _positive(value) for value in observed["process_identity"])
        or observed["scope"] != PROCESS_SCOPE
        or type(observed["return_code"]) is not int
        or not _positive(observed["wall_ns"])
        or observed["cpu_ns"] is not None
    ):
        raise ValueError("invalid source-bound launcher observation")
    folder = root / f"slot-{slot['slot_index']:04d}"
    started_path = folder / "started.json"
    outcome_path = folder / "outcome.json"
    if folder.is_symlink() or started_path.is_symlink() or outcome_path.is_symlink():
        raise ValueError("original slot receipt symlink is not allowed")
    if not started_path.is_file():
        raise ValueError("launcher has no original slot start")
    started_raw = started_path.read_bytes()
    started = _read_receipt(started_path)
    if observed["started_file_sha256"] != _sha(started_raw) or observed[
        "process_identity"
    ] != started.get("process_identity"):
        raise ValueError("launcher and original slot start differ")
    if outcome_path.is_file():
        outcome_raw = outcome_path.read_bytes()
        outcome = _read_receipt(outcome_path)
        if (
            observed["outcome_file_sha256"] != _sha(outcome_raw)
            or observed["process_identity"] != outcome.get("process_identity")
            or observed["wall_ns"] < outcome.get("wall_ns", -1)
        ):
            raise ValueError("launcher does not enclose original slot")
    elif observed["outcome_file_sha256"] is not None:
        raise ValueError("launcher cites a missing terminal outcome")
    return {
        "slot_index": slot["slot_index"],
        "process_identity": observed["process_identity"],
        "launcher_file_sha256": _sha(raw),
        "return_code": observed["return_code"],
        "wall_ns": observed["wall_ns"],
        "cpu_ns": observed["cpu_ns"],
        "terminal_outcome_present": outcome_path.is_file(),
    }


def _prior_costs(root, manifest, plan, used_paths):
    selection_ref = manifest["selection_receipt"]
    labels = manifest["label_receipts"]
    if selection_ref is None and not labels:
        return None
    if selection_ref is None or type(labels) is not list:
        raise ValueError(
            "selection and label original receipts must be supplied together"
        )
    selection, raw = _original_file(root, selection_ref, used_paths)
    _checked_self_hash(selection, "result_hash")
    if (
        selection.get("schema_version")
        not in (
            "rc-control-runtime-selection-result.v1",
            "rc-control-runtime-selection-result.v2",
        )
        or selection.get("result_hash") != plan["selection_result_hash"]
        or selection.get("source_revision") != plan["source_revision"]
        or selection.get("selected_strategy") != "learned_svd"
        or selection.get("validation_or_holdout_execution") is not False
        or selection.get("new_training_labels") != 0
        or selection.get("timing_scope")
        != "validation_fits_all_four_path_fold_runs_comparisons_and_intermediate_IO_excluding_final_result_write"
        or selection.get("selected_policy") is None
        or not _positive(selection.get("wall_ns"))
        or not _nonnegative(selection.get("cpu_ns"))
    ):
        raise ValueError("original development selection differs from plan")
    policy = learning.RCControlSeedPolicy(_bytes(selection["selected_policy"]).decode())
    if policy.policy_hash != plan["policy_hash"]:
        raise ValueError("original development policy differs from plan")
    training = {row["case_id"] for row in plan["cases"] if row["split"] == "train"}
    seen = set()
    label_rows = []
    for source in labels:
        if type(source) is not dict or set(source) != {"file", "source_revision"}:
            raise ValueError("exact original label source binding required")
        label, label_raw = _original_file(root, source["file"], used_paths)
        _checked_self_hash(label, "report_hash")
        case_ids = label.get("training_case_ids")
        if (
            label.get("schema_version") != "experimental-rc-control-learning-study.v1"
            or label.get("evaluation_deferred") is not True
            or label.get("timing_scope")
            != "preflight_all_generation_reference_secant_fresh_verification_fit_deferred_evaluation_receipts_and_io_excluding_final_report_write"
            or not _positive(label.get("whole_study_wall_ns"))
            or not _nonnegative(label.get("whole_study_cpu_ns"))
            or type(case_ids) is not list
            or not case_ids
            or any(
                type(case_id) is not str or case_id not in training or case_id in seen
                for case_id in case_ids
            )
            or len(set(case_ids)) != len(case_ids)
            or label.get("source_revision") != source["source_revision"]
        ):
            raise ValueError("invalid original training-label receipt")
        seen.update(case_ids)
        label_rows.append(
            {
                "report_hash": label["report_hash"],
                "file_sha256": _sha(label_raw),
                "source_revision": label["source_revision"],
                "wall_ns": label["whole_study_wall_ns"],
                "cpu_ns": label["whole_study_cpu_ns"],
                "training_case_ids": case_ids,
            }
        )
    if seen != training:
        raise ValueError("original label receipts do not cover training roster")
    label_wall = sum(row["wall_ns"] for row in label_rows)
    return {
        "selection_result_hash": selection["result_hash"],
        "selection_file_sha256": _sha(raw),
        "selection_wall_ns": selection["wall_ns"],
        "selection_cpu_ns": selection["cpu_ns"],
        "label_receipts": label_rows,
        "label_wall_ns_sum": label_wall,
        "known_prior_component_wall_ns_sum": label_wall + selection["wall_ns"],
        "selection_nested_fits_added_again": False,
        "complete_lifecycle_cost": False,
    }


def audit_heldout_lifecycle_costs(plan, root):
    """Audit bounded costs; never turn timing observations into net-benefit proof.

    The caller places `lifecycle-manifest.json` and its referenced original files
    under root after execution. A missing launcher remains unknown. Elapsed
    campaign time cannot be inferred from independent process clock domains.
    """
    root = Path(root)
    slot_audit = audit_heldout_receipts(plan, root)
    manifest_path = root / "lifecycle-manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("lifecycle manifest symlink is not allowed")
    manifest = _read_receipt(manifest_path)
    _checked_self_hash(manifest, "manifest_hash")
    if (
        set(manifest)
        != {
            "schema_version",
            "plan_hash",
            "source_revision",
            "selection_result_hash",
            "launchers",
            "selection_receipt",
            "label_receipts",
            "training_cost_reuse_count",
            "manifest_hash",
        }
        or manifest["schema_version"] != MANIFEST_SCHEMA
        or manifest["plan_hash"] != plan["plan_hash"]
        or manifest["source_revision"] != plan["source_revision"]
        or manifest["selection_result_hash"] != plan["selection_result_hash"]
        or manifest["training_cost_reuse_count"]
        != plan["training_cost_reuse_assumption"]
        or type(manifest["launchers"]) is not list
        or type(manifest["label_receipts"]) is not list
    ):
        raise ValueError("lifecycle manifest differs from frozen plan")
    reuse_count = manifest["training_cost_reuse_count"]
    if reuse_count is not None and not _positive(reuse_count):
        raise ValueError("positive predeclared training reuse count required")
    by_slot = {}
    for entry in manifest["launchers"]:
        if type(entry) is not dict or type(entry.get("slot_index")) is not int:
            raise ValueError("declared launcher slot index required")
        index = entry["slot_index"]
        if index in by_slot or not 0 <= index < len(plan["schedule"]):
            raise ValueError("duplicate or undeclared launcher slot")
        by_slot[index] = entry
    used_paths = {"lifecycle-manifest.json"}
    launchers = [
        _launcher(root, by_slot[index], plan, slot, used_paths)
        for index, slot in enumerate(plan["schedule"])
        if index in by_slot
    ]
    process_identities = [tuple(row["process_identity"]) for row in launchers]
    if len(set(process_identities)) != len(process_identities):
        raise ValueError("launcher process identities must be distinct")
    prior = _prior_costs(root, manifest, plan, used_paths)
    all_launchers = len(launchers) == len(plan["schedule"])
    all_terminal = all(row["terminal_outcome_present"] for row in launchers)
    all_success = all(row["return_code"] == 0 for row in launchers)
    return {
        "schema_version": "rc-heldout-lifecycle-cost-audit.v1",
        "plan_hash": plan["plan_hash"],
        "manifest_hash": manifest["manifest_hash"],
        "declared_denominator": len(plan["schedule"]),
        "original_slot_audit": slot_audit,
        "launcher_observations": launchers,
        "launcher_observations_complete": all_launchers and all_terminal,
        "launcher_exits_successful": all_launchers and all_terminal and all_success,
        "observed_launcher_wall_ns_sum": sum(row["wall_ns"] for row in launchers),
        "all_declared_launcher_wall_ns_sum": (
            sum(row["wall_ns"] for row in launchers) if all_launchers else None
        ),
        "launcher_cpu_ns_sum": None,
        "launcher_scope": PROCESS_SCOPE,
        "launcher_observations_are_attestation": False,
        "launcher_intervals_replace_nested_slot_intervals": True,
        "launcher_intervals_are_campaign_elapsed_time": False,
        "prior_original_costs": prior,
        "training_cost_reuse_count_predeclared": reuse_count,
        "projected_operational_break_even_count": None,
        "actual_total_evaluation_wall_ns": None,
        "unknown_evaluation_cost": True,
        "lifecycle_costs_audited": False,
        "source_rights_and_lineage_independently_authenticated": False,
        "net_benefit_proved": False,
        "selected_strategy": "secant",
    }
