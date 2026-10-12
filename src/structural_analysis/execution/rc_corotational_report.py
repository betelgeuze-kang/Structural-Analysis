"""Deterministic nodal report derived from service-authenticated saved originals.

This consumer never executes analysis, numerical replay or a current source
fingerprint. Nested member/material responses are deliberately not projected
into engineering tables. The service owns original artifact and ledger custody.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .rc_corotational_job_contract import RC_COROTATIONAL_JOB_AUTHORITY
from .rc_corotational_job_request import (
    RCCorotationalJobRequest,
    rc_corotational_job_canonical_bytes,
)


RC_COROTATIONAL_REPORT_SCHEMA_VERSION = "durable-rc-corotational-report.v1"
RC_COROTATIONAL_REPORT_MAX_BYTES = 64 * 1024 * 1024
RC_COROTATIONAL_REPORT_CLAIM_BOUNDARY = (
    "Saved experimental corotational RC nodal accepted-history and recorded "
    "execution observations only. Preload and accepted subdivision states are "
    "separate from authored targets and spent control attempts. Source revision "
    "is a caller declaration; recorded source hashes establish integrity, not "
    "independent execution authentication. Pending reservations and unavailable "
    "work remain unknown. No fresh analysis, verification or source fingerprint "
    "is performed; no independent physical validation, design approval, material "
    "quantity/price qualification, or release readiness is granted."
)


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


class RCCorotationalReportTooLargeError(ValueError):
    """The deterministic export exceeds its independent transport byte cap."""


def build_rc_corotational_report(
    *,
    request: RCCorotationalJobRequest,
    result: dict[str, Any],
    bindings: dict[str, Any],
    invocations: list[dict[str, Any]],
) -> bytes:
    """Export bounded canonical bytes after the service's single-snapshot checks.

    Returned bytes include a semantic self-hash. The transport's separate raw
    body hash identifies ``rcc_<hex>`` without a self-referential JSON identifier.
    """
    if type(request) is not RCCorotationalJobRequest:
        raise ValueError("corotational report requires an immutable typed request")
    if result["authority"] != RC_COROTATIONAL_JOB_AUTHORITY:
        raise ValueError("corotational report cannot change structural authority")
    authored = request.to_dict()
    model = authored["model"]
    budget = result["execution_budget"]
    present = {row["ordinal"] for row in invocations}
    pending = [
        ordinal
        for ordinal in range(1, budget["reserved_attempts"] + 1)
        if ordinal not in present
    ]
    known = {
        key: 0
        for key in (
            "preload_solver_calls",
            "restart_replay_solver_calls",
            "control_solver_calls",
        )
    }
    unknown = bool(pending)
    for invocation in invocations:
        unknown |= invocation["unavailable_execution_work"]
        work = invocation["work"]
        if work is not None:
            unknown |= work["unavailable_execution_work"]
            for key in known:
                known[key] += work[key]
    control_index = [row["id"] for row in model["nodes"]].index(
        request.config.control_node_id
    )
    component_index = int(request.config.control_component == "UY")
    responses = [
        {
            "state_index": index,
            **{
                key: row[key]
                for key in (
                    "phase",
                    "checkpoint_hash",
                    "parent_checkpoint_hash",
                    "load_factor",
                )
            },
            "control_displacement_m": row["nodes"][control_index][
                "displacements_m_rad"
            ][component_index],
            "nodes": row["nodes"],
        }
        for index, row in enumerate(result["api_result"]["responses"])
    ]
    payload = {
        "schema_version": RC_COROTATIONAL_REPORT_SCHEMA_VERSION,
        "bindings": bindings,
        "declarations": {
            "control": {
                "node_id": request.config.control_node_id,
                "component": request.config.control_component,
                "unit": "m",
            },
            "targets_m": authored["config"]["targets_m"],
            "fixed_nodal_loads": authored["config"]["fixed_nodal_loads"],
            "reference_loads": model["loads"],
            "supports": model["supports"],
            "model_units": model["units"],
            "coordinate_system": model["coordinate_system"],
            "model_metadata": model["metadata"],
            "config": authored["config"],
            "execution_config": authored["execution_config"],
        },
        "progress": {
            "control_solver_attempts": {
                "completed": result["progress_completed"],
                "maximum": result["progress_total"],
            },
            "authored_targets": {
                "completed": result["completed_target_count"],
                "total": result["total_target_count"],
            },
            "accepted_response_states": len(responses),
        },
        "units": {
            "frame": "global",
            "displacement_components": ["UX", "UY", "RZ"],
            "displacement_units": ["m", "m", "rad"],
            "load_components": ["FX", "FY", "MZ"],
            "load_units": ["kN", "kN", "kN*m"],
            "load_factor": "1",
            "reaction_definition": "internal_minus_external_on_constrained_dofs;free_dofs_zero",
        },
        "responses": responses,
        "execution": {
            "unit": "reserved_api_invocations",
            "budget": budget,
            "recorded_invocation_count": len(invocations),
            "pending_ordinals": pending,
            "unknown_execution_work": unknown,
            "known_work": known,
            "invocations": invocations,
        },
        "structural_authority": dict(result["authority"]),
        "derivation": {
            "version": "rc_corotational_nodal_report.v1",
            "fresh_analysis_invocations": 0,
            "fresh_verification_invocations": 0,
            "source_fingerprint_invocations": 0,
            "new_structural_authority": False,
        },
        "claim_boundary": RC_COROTATIONAL_REPORT_CLAIM_BOUNDARY,
    }
    raw = rc_corotational_job_canonical_bytes(
        {**payload, "report_hash": _sha(rc_corotational_job_canonical_bytes(payload))}
    )
    if len(raw) > RC_COROTATIONAL_REPORT_MAX_BYTES:
        raise RCCorotationalReportTooLargeError(
            "corotational report exceeds its byte bound"
        )
    return raw
