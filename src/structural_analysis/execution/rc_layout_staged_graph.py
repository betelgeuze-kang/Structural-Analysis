"""Admit bound prefix rejection and full work without invoking a solver."""

from dataclasses import replace

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_candidate_search import _work
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.execution.rc_search_http import _document, _META_MAX, _ROLES
from structural_analysis.execution.rc_layout_cost_pruning_graph import (
    _same,
    _original_row,
    check_pruned_comparison,
)


def check_staged_policy(plan, result, request):
    policy = plan.get("prefix_screening")
    if type(policy) is not dict:
        raise ValueError("staged prefix policy required")
    count = policy.get("target_count")
    if type(count) is not int or not 1 <= count < len(request.targets_m):
        raise ValueError("proper staged prefix target count required")
    expected = {
        "profile": "verified-history-maximum-prefix.v1",
        "target_count": count,
        "baseline": "full_reference_without_prefix",
        "prefix_pass_is_full_acceptance": False,
        "reuse_prefix_checkpoint": False,
        "terminal_limits_used": False,
    }
    _same(policy, expected, "staged prefix policy differs")
    _same(result.get("prefix_screening"), expected, "staged result policy differs")


def check_staged_comparison(read, plan, name, comparison, outcome, models, request):
    info = comparison.get("prefix_screening")
    if type(info) is not dict or type(info.get("decisions")) is not list:
        raise ValueError("original prefix decisions required")
    _same(outcome.get("prefix_screening"), info, "prefix outcome differs")
    count = plan["prefix_screening"]["target_count"]
    expected_request = replace(request, targets_m=request.targets_m[:count])
    prefix_rows = []
    rejected = []
    cursor = 0
    pool = {r["candidate_id"]: r for r in plan["pool"]}
    hl = design.FiberFrameHistoryLimits(**plan["history_limits"])
    ml = design.FiberFrameMaterialHistoryLimits(**plan["material_limits"])

    def original_ref(folder, ref, path, maximum=_META_MAX):
        if (
            type(ref) is not dict
            or set(ref) != {"path", "sha256", "byte_length"}
            or ref.get("path") != path
        ):
            raise ValueError("prefix original artifact path differs")
        return read(f"{folder}/{path}", maximum, ref)

    def prefix_check(key):
        nonlocal cursor
        if cursor >= len(info["decisions"]):
            raise ValueError("required prefix decision missing")
        record = info["decisions"][cursor]
        cursor += 1
        if (
            type(record) is not dict
            or set(record) != {"candidate_id", "action", "artifact"}
            or record.get("candidate_id") != key
        ):
            raise ValueError("prefix decision order differs")
        folder = f"{name}/prefix/{key}"
        decision = _document(
            original_ref(name, record["artifact"], f"prefix/{key}/decision.json"),
            "decision_hash",
        )
        raw_request = original_ref(
            folder, decision.get("prefix_request"), "request.json"
        )
        prefix = decode_bounded_rc_fiber_direct_control_request(raw_request)
        _same(
            prefix.to_dict(),
            expected_request.to_dict(),
            "prefix changes full request context",
        )
        row = strict_json_object_bytes(
            original_ref(folder, decision.get("prefix_row"), "row.json"),
            maximum_bytes=_META_MAX,
        )
        if (
            row.get("candidate_id") != "baseline"
            or type(row.get("full_reference_verification_pass")) is not bool
        ):
            raise ValueError("prefix original row identity or verification differs")
        refs = row.get("artifacts")
        if (
            type(refs) is not dict
            or not {
                "model",
                "result",
                "verification",
                "analysis_outcome",
                "verification_outcome",
            }
            <= set(refs)
            <= _ROLES
        ):
            raise ValueError("prefix original artifact roles incomplete")
        if row["full_reference_verification_pass"] and set(refs) != _ROLES:
            raise ValueError("verified prefix requires every original artifact")
        for role, ref in refs.items():
            original_ref(
                folder,
                ref,
                f"baseline/{role.replace('_', '-')}.json",
                (128 if role == "checkpoint" else 64 if role == "result" else 16)
                * 1024**2,
            )
        _same(
            {k: v for k, v in refs["model"].items() if k != "path"},
            {k: v for k, v in pool[key]["model_artifact"].items() if k != "path"},
            "prefix model differs from pool",
        )
        _same(
            row.get("quantities"), pool[key]["quantities"], "prefix quantities differ"
        )
        _same(
            row.get("material_estimate"),
            pool[key]["material_estimate"],
            "prefix estimate differs",
        )
        work = _work({"rows": [row]})
        if work["unknown_work"] or work["api_invocation_count"] != 2:
            raise ValueError("prefix has unknown or incomplete work")
        _original_row(
            read,
            f"{name}/prefix/{key}",
            row,
            models[key],
            prefix,
            allow_unverified=True,
        )
        violations = []
        if row["full_reference_verification_pass"]:
            screens = study._screens(row["performance"], hl, ml)
            _same(
                row.get("screens"),
                screens,
                "prefix screens differ from original history",
            )
            _same(
                row.get("selection_eligible"),
                all(v["status"] == "pass" for v in screens.values()),
                "prefix eligibility differs",
            )
            violations = [
                {"metric": k, "value": v["value"], "limit": v["limit"]}
                for k, v in screens.items()
                if k.startswith("maximum_") and v["status"] == "fail"
            ]
        action = "reject_history_maximum" if violations else "execute_full_reference"
        expected = {
            "schema_version": "experimental-rc-layout-prefix-screen.v1",
            "full_request_hash": study._sha(study._bytes(request.to_dict())),
            "prefix_request": decision["prefix_request"],
            "prefix_row": decision["prefix_row"],
            "model_checksum": models[key].canonical_model_checksum,
            "prefix_target_count": count,
            "prefix_verified": row["full_reference_verification_pass"],
            "history_maximum_violations": violations,
            "action": action,
            "full_history_acceptance": False,
            "terminal_limits_used": False,
            "execution_work": work,
        }
        expected["decision_hash"] = study._sha(study._bytes(expected))
        _same(decision, expected, "prefix decision differs from original evidence")
        if record["action"] != action:
            raise ValueError("prefix action index differs")
        prefix_rows.append(row)
        if violations:
            rejected.append(key)
        return bool(violations)

    check_pruned_comparison(
        read,
        plan,
        name,
        comparison,
        outcome,
        models,
        request,
        prefix_check=prefix_check,
    )
    if cursor != len(info["decisions"]):
        raise ValueError("unexpected prefix decisions")
    expected = {
        "prefix_request_count": len(prefix_rows),
        "full_reference_request_count": len(comparison["rows"]),
        "decisions": info["decisions"],
        "rejected_history_maximum_candidate_ids": rejected,
        "prefix_execution_work": _work({"rows": prefix_rows}),
        "full_reference_execution_work": _work(comparison),
        "full_history_acceptance_from_prefix": False,
    }
    _same(info, expected, "prefix coverage or accounting differs")
    return _work({"rows": [*comparison["rows"], *prefix_rows]})
