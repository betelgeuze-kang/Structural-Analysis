"""Pure full-source report with retained per-window mechanical originals.

The service supplies authenticated original outcomes. No scalar force conversion,
experimental tare, fitted material law, or numerical replay is inferred here.
"""

from __future__ import annotations

import json

from structural_analysis.execution.rc_corotational_job_request import (
    _sha,
    rc_corotational_job_canonical_bytes,
)
from structural_analysis.execution.rc_corotational_ordinal_job_contract import (
    AUTHORITY,
    ORDINAL_JOB_MAX_BYTES,
    build_ordinal_job_receipt,
    validate_ordinal_invocation_outcome,
)
from structural_analysis.execution.rc_corotational_ordinal_job_request import (
    RCCorotationalOrdinalJobRequest,
)


def build_ordinal_report(request, result, evidence, **source_refs) -> bytes:
    """Retain all source rows and reference immutable nodal/window outputs.

    ``evidence['invocations']`` streams owner-recorded {ordinal,outcome} rows;
    ``validation_report`` is the service's pure final contract report. Full
    nodal arrays remain in original content-addressed outcomes, never sampled.
    """
    if (
        type(request) is not RCCorotationalOrdinalJobRequest
        or result.get("authority") != AUTHORITY
    ):
        raise ValueError(
            "ordinal report requires immutable original request and authority"
        )
    if type(evidence) is not dict or set(evidence) != {
        "invocations",
        "validation_report",
    }:
        raise ValueError("ordinal report requires authenticated invocation originals")
    # Retain at most one accepted phase pair, never all full window originals.
    invocations = iter(evidence["invocations"])
    by_production = {r["production_ordinal"]: r for r in result["receipts"]}
    by_verification = {r["verification_ordinal"]: r for r in result["receipts"]}
    grants = {
        g["api_ordinal"]: g for g in result["solver_credit_budget"]["reservations"]
    }
    pending = None
    paired = 0
    previous_ordinal = 0
    unknown_recorded = set()
    windows = []
    known = {"production": 0, "verification": 0}
    recorded = set()
    samples = []
    observed = json.loads(request.observed_force_reference_bytes)

    def retain_window(receipt, outcome):
        ordinal = receipt["production_ordinal"]
        api = outcome["api_result"]
        windows.append(
            {
                "production_api_ordinal": ordinal,
                "verification_api_ordinal": receipt["verification_ordinal"],
                "production_outcome_sha256": receipt["production_outcome_hash"],
                "verification_outcome_sha256": receipt["verification_outcome_hash"],
                "source_ordinal_start": receipt["completed_before"],
                "source_ordinal_end_exclusive": receipt["actual_after"],
                "event_count": len(api["events"]),
                "contains_all_native_events_and_nodal_arrays": True,
            }
        )
        for event in api["events"]:
            if event["kind"] == "verified_hold" or (
                event["kind"] == "mechanical_commit"
                and event.get("position_numerator") == 1
                and event.get("position_depth") == 0
            ):
                source_ordinal = event["ordinal"]
                row = request.plan.rows[source_ordinal]
                accepted = event["accepted_state"]
                samples.append(
                    {
                        **row.to_dict(),
                        "kind": event["kind"],
                        "achieved_observation_m": accepted["achieved_observation_m"],
                        "load_factor": accepted["load_factor"],
                        "observed_force_kn": None
                        if observed is None
                        else observed["rows"][source_ordinal]["observed_force_kn"],
                        "production_api_ordinal": ordinal,
                        "mechanical_state_hash": event["mechanical_state_hash"],
                    }
                )

    for entry in invocations:
        ordinal = entry["ordinal"]
        if (
            type(ordinal) is not int
            or ordinal <= previous_ordinal
            or ordinal not in grants
        ):
            raise ValueError(
                "ordinal report requires an ordered owner invocation stream"
            )
        previous_ordinal = ordinal
        outcome = validate_ordinal_invocation_outcome(
            entry["outcome"], request, request.request_hash
        )
        if outcome["grant"] != grants[ordinal]:
            raise ValueError("ordinal report outcome differs from external owner grant")
        recorded.add(ordinal)
        if outcome["unavailable_execution_work"]:
            unknown_recorded.add(ordinal)
        used = outcome["credits_used"]
        if used is not None:
            known[outcome["phase"]] += used
        if ordinal in by_production:
            if pending is not None:
                raise ValueError("ordinal report phase pairs are interleaved")
            pending = outcome
        elif ordinal in by_verification:
            receipt = by_verification[ordinal]
            if (
                pending is None
                or pending["grant"]["api_ordinal"] != receipt["production_ordinal"]
            ):
                raise ValueError(
                    "ordinal report is missing the recorded production original"
                )
            expected = build_ordinal_job_receipt(
                request,
                production_ordinal=receipt["production_ordinal"],
                verification_ordinal=ordinal,
                production_outcome=pending,
                verification_outcome=outcome,
            )
            if rc_corotational_job_canonical_bytes(
                expected
            ) != rc_corotational_job_canonical_bytes(receipt):
                raise ValueError(
                    "ordinal report receipt differs from immutable recorded pair"
                )
            retain_window(receipt, pending)
            pending = None
            paired += 1
    if pending is not None or paired != len(result["receipts"]):
        raise ValueError("ordinal report is missing accepted invocation originals")
    if [s["ordinal"] for s in samples] != list(range(request.progress_total)):
        raise ValueError(
            "ordinal completed report omitted or reordered an authored source row"
        )
    unknown_solver = [
        g["api_ordinal"]
        for g in grants.values()
        if g["api_ordinal"] not in recorded or g["api_ordinal"] in unknown_recorded
    ]
    unknown_api = [
        ordinal
        for ordinal in range(1, result["execution_budget"]["reserved_attempts"] + 1)
        if ordinal not in recorded or ordinal in unknown_recorded
    ]
    payload = {
        "schema_version": "rc-corotational-ordinal-report.v1",
        "request_hash": request.request_hash,
        "context_hash": request.context_hash,
        "result_hash": result["result_hash"],
        "source_references": source_refs,
        "source_revision": request.source_revision,
        "source_revision_is_execution_attestation": False,
        "initialization": request.config.initialization,
        "initialization_is_experimental_tare": False,
        "full_history_plan": request.plan.to_dict(),
        "samples": samples,
        "native_window_originals": windows,
        "node_ids": [row["id"] for row in request.model.nodes],
        "global_dof_order": "node-major UX UY RZ",
        "displacement_component_units": ["m", "m", "rad"],
        "load_component_units": ["kN", "kN", "kN*m"],
        "control_observation": request.config.observation_dict(),
        "axial_load_pattern": request.to_dict()["config"]["axial_load_pattern"],
        "independent_axial_load_role": request.config.independent_axial_load_role,
        "observed_force_reference": observed,
        "force_comparison_status": "explicit_force_observer_not_admitted",
        "execution_budget": result["execution_budget"],
        "solver_credit_budget": result["solver_credit_budget"],
        "known_solver_invocations": known,
        "unknown_reserved_api_ordinals": unknown_api,
        "unknown_solver_grant_api_ordinals": unknown_solver,
        "credits_are_nonrefundable_reserved_ceilings": True,
        "validation_report": evidence["validation_report"],
        "authority": dict(AUTHORITY),
    }
    payload["report_hash"] = _sha(rc_corotational_job_canonical_bytes(payload))
    raw = rc_corotational_job_canonical_bytes(payload)
    if len(raw) > ORDINAL_JOB_MAX_BYTES:
        raise ValueError("ordinal complete report exceeds bounded export bytes")
    return raw
