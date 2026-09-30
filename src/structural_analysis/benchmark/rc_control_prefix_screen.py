"""Verified short-history screening; acceptance always needs the full request."""

from dataclasses import asdict, replace
import math

from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_candidate_search import _work


def run_prefix_screen(
    model, request, count, root, prices, history_limits, material_limits
):
    """Retain originals and reject only observed cumulative-history violations.

    Terminal limits are deliberately absent. Failure and unavailable work are
    not evidence that a candidate is physically infeasible.
    """
    if type(count) is not int or not 1 <= count < len(request.targets_m):
        raise ValueError("proper nonempty request prefix required")
    prefix = replace(request, targets_m=request.targets_m[:count])
    root.mkdir(parents=True, exist_ok=False)
    request_ref = study._save(root, "request.json", study._bytes(prefix.to_dict()))
    row = study._reference_design_row(
        model,
        None,
        prefix,
        root,
        prefix.api_kwargs() | {"restart": None},
        prices,
        history_limits,
        material_limits,
        None,
    )
    row_ref = study._save(root, "row.json", study._bytes(row))
    work = _work({"rows": [row]})
    limits = asdict(history_limits) | asdict(material_limits)
    violations = []
    if row["full_reference_verification_pass"] is True and not work["unknown_work"]:
        for key, limit in limits.items():
            value = (row.get("performance") or {}).get(key)
            if (
                key.startswith("maximum_")
                and isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
                and value > limit
            ):
                violations.append({"metric": key, "value": value, "limit": limit})
    decision = {
        "schema_version": "experimental-rc-layout-prefix-screen.v1",
        "full_request_hash": study._sha(study._bytes(request.to_dict())),
        "prefix_request": request_ref,
        "prefix_row": row_ref,
        "model_checksum": model.canonical_model_checksum,
        "prefix_target_count": count,
        "prefix_verified": row["full_reference_verification_pass"],
        "history_maximum_violations": violations,
        "action": "stop_unknown_work"
        if work["unknown_work"]
        else "reject_history_maximum"
        if violations
        else "execute_full_reference",
        "full_history_acceptance": False,
        "terminal_limits_used": False,
        "execution_work": work,
    }
    decision["decision_hash"] = study._sha(study._bytes(decision))
    ref = study._save(root, "decision.json", study._bytes(decision))
    return row, decision, ref
