"""Original-record cost pruning admission, without numerical execution."""

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_cost_dominance import (
    layout_cost_dominance,
)
from structural_analysis.execution.rc_search_http import _document, _META_MAX


def _same(actual, expected, message):
    if study._bytes(actual) != study._bytes(expected):
        raise ValueError(message)


def check_pruning_policy(plan, result):
    expected = {
        "profile": "verified-incumbent-strict-cost.v1",
        "consideration_horizon": "frozen_shortlist_including_baseline",
        "unused_analysis_budget_reallocated": False,
        "unevaluated_physical_feasibility": "unknown",
    }
    for document in (plan, result):
        _same(document.get("execution_policy"), expected, "cost pruning policy differs")


def _original_row(read, name, row, model, request, *, allow_unverified=False):
    """Bind incumbent metadata to original records, without granting solver authority."""
    if row.get("full_reference_verification_pass") is not True:
        if row.get("selection_eligible") is not False:
            raise ValueError("unverified pruning row cannot be eligible")
        if not allow_unverified:
            return
    verified = row.get("full_reference_verification_pass") is True
    refs = row["artifacts"]

    def raw(role):
        return read(f"{name}/{refs[role]['path']}", 128 * 1024**2, refs[role])

    result = _document(raw("result"), "result_hash")
    verification = strict_json_object_bytes(
        raw("verification"), maximum_bytes=_META_MAX
    )
    checkpoint_raw = raw("checkpoint") if "checkpoint" in refs else None
    if checkpoint_raw is not None:
        _document(checkpoint_raw, "artifact_hash")
    _same(
        result.get("checkpoint"),
        {"sha256": study._sha(checkpoint_raw), "byte_length": len(checkpoint_raw)}
        if checkpoint_raw is not None
        else None,
        "pruning result checkpoint differs",
    )
    expected_request = {
        "targets_m": list(request.targets_m),
        "control_global_dof": request.control_global_dof,
        "configuration": request.solver_config.to_manifest(),
        "configuration_hash": request.solver_config.contract_hash,
        "allow_reversals": request.allow_reversals,
        "maximum_reversals": request.maximum_reversals,
        "maximum_targets": request.maximum_targets,
        "restart_input_sha256": None,
    }
    if request.constant_nodal_loads:
        expected_request["constant_nodal_loads"] = request.to_dict()[
            "constant_nodal_loads"
        ]
    _same(result.get("request"), expected_request, "pruning original request differs")
    if (
        result.get("model", {}).get("canonical_model_checksum")
        != model.canonical_model_checksum
    ):
        raise ValueError("pruning original result model differs")
    if verified and (
        result.get("contract_pass") is not True
        or len(result.get("response_history", [])) != len(request.targets_m)
    ):
        raise ValueError("pruning original path incomplete")
    if (
        verified
        and any(
            verification.get(k) is not True
            for k in (
                "artifact_contract_pass",
                "contract_pass",
                "physical_path_complete",
                "fresh_source_execution_invoked",
                "solver_replay_performed",
            )
        )
        or verification.get("verified_result_hash") != result["result_hash"]
        or verified
        and verification.get("errors") != []
        or verification.get("unavailable_execution_work") is not False
    ):
        raise ValueError("pruning original verification incomplete")
    invocations = row.get("invocations")
    if type(invocations) is not list or len(invocations) != 2:
        raise ValueError("pruning original invocations incomplete")
    for inv, phase in zip(invocations, ("analysis", "verification"), strict=True):
        original = strict_json_object_bytes(
            raw(phase + "_outcome"), maximum_bytes=_META_MAX
        )
        _same(inv, original, "pruning invocation differs from original outcome")
        if (
            inv.get("phase") != phase
            or inv.get("status") != "returned"
            or inv.get("unknown_execution_work") is not False
        ):
            raise ValueError("pruning original invocation did not return known work")
        work = (
            result["metrics"]["control_work"]
            if phase == "analysis"
            else verification["replay_control_work"]
        )
        _same(inv.get("work"), work, "pruning original work binding differs")
        minimum_steps = (
            (len(request.targets_m) + bool(request.constant_nodal_loads))
            if verified
            else 0
        )
        if (
            type(work.get("attempted_step_count")) is not int
            or work["attempted_step_count"] < minimum_steps
        ):
            raise ValueError("pruning original work excludes complete path")
    if not verified:
        if row.get("performance") is not None or row.get("screens") is not None:
            raise ValueError("unverified prefix cannot carry response screens")
        return
    history = result["response_history"]
    if request.constant_nodal_loads:
        history = [result["preload_response"], *history]
    _same(
        row.get("performance"),
        study._performance(history),
        "pruning performance differs from original history",
    )


def check_pruned_comparison(
    read, plan, name, comparison, outcome, models, request, *, prefix_check=None
):
    rows = comparison["rows"]
    for row in rows:
        _original_row(read, name, row, models[row["candidate_id"]], request)
    pruning = comparison.get("cost_pruning")
    if type(pruning) is not dict:
        raise ValueError("original pruning records required")
    _same(outcome.get("cost_pruning"), pruning, "pruning outcome differs")
    considered = ["baseline", *plan["plans"][name]["shortlist"]]
    decisions = pruning.get("decisions")
    if type(decisions) is not list or len(decisions) != len(considered):
        raise ValueError("complete pruning decisions required")
    evaluated: list[dict] = []
    skipped = []
    for ordinal, (key, record) in enumerate(zip(considered, decisions, strict=True)):
        bound = layout_cost_dominance(plan, evaluated)
        skip = key in bound["cost_dominated_unevaluated_candidate_ids"]
        action = (
            "skip_cost_dominated"
            if skip
            else "execute_prefix_screen"
            if prefix_check is not None and key != "baseline"
            else "execute_full_reference"
        )
        if type(record) is not dict or set(record) != {
            "candidate_id",
            "action",
            "artifact",
        }:
            raise ValueError("pruning decision reference invalid")
        ref = record["artifact"]
        path = f"decisions/{ordinal:02d}.json"
        if (
            type(ref) is not dict
            or set(ref) != {"path", "sha256", "byte_length"}
            or ref.get("path") != path
        ):
            raise ValueError("pruning decision path differs")
        decision = _document(read(f"{name}/{path}", _META_MAX, ref), "decision_hash")
        expected = {
            "schema_version": "experimental-rc-layout-staged-cost-decision.v1"
            if prefix_check is not None
            else "experimental-rc-layout-cost-pruning-decision.v1",
            "candidate_id": key,
            "evaluated_candidate_ids_before": [r["candidate_id"] for r in evaluated],
            "action": action,
            "bound": bound,
            "physical_feasibility_at_decision": "unknown",
        }
        expected["decision_hash"] = study._sha(study._bytes(expected))
        _same(decision, expected, "pruning decision differs from prior original rows")
        _same(
            {k: record[k] for k in ("candidate_id", "action")},
            {"candidate_id": key, "action": action},
            "pruning decision index differs",
        )
        if skip:
            skipped.append(key)
        else:
            if prefix_check is not None and key != "baseline" and prefix_check(key):
                continue
            if (
                len(evaluated) >= len(rows)
                or rows[len(evaluated)]["candidate_id"] != key
            ):
                raise ValueError("pruning removed a required original evaluation")
            evaluated.append(rows[len(evaluated)])
    if len(evaluated) != len(rows):
        raise ValueError("pruning includes an unexpected evaluation")
    cost = pruning.get("decision_wall_ns")
    if type(cost) is not int or cost < 0 or cost > outcome["wall_ns"]:
        raise ValueError("known pruning decision cost required within arm interval")
    evaluated_ids = [r["candidate_id"] for r in evaluated]
    ids = [r["candidate_id"] for r in plan["pool"]]
    _same(
        pruning,
        {
            "profile": plan["execution_policy"]["profile"],
            "considered_candidate_ids": considered,
            "evaluated_candidate_ids": evaluated_ids,
            "skipped_cost_dominated_candidate_ids": skipped,
            "outside_consideration_horizon_candidate_ids": [
                k for k in ids if k not in considered
            ],
            "unevaluated_candidate_ids": [k for k in ids if k not in evaluated_ids],
            "decisions": decisions,
            "decision_wall_ns": cost,
            "unevaluated_physical_feasibility": "unknown",
            "global_cost_optimality_proved": False,
        },
        "pruning coverage or authority differs",
    )
