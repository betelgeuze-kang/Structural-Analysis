"""Full-reference section comparisons on an explicitly authored RC control path.

This experimental study reuses physical changes/quantities/prices, but does not
inherit public load-control authority or reuse a prior design's material state.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re
from time import perf_counter_ns, process_time_ns
from typing import Any

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.model.schema import CanonicalModel


SCHEMA = "experimental-rc-control-design-comparison.v1"


def _bytes(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: bytes):
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _save(root, relative, data):
    target = root / relative
    target.parent.mkdir(exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
    return {"path": relative, "byte_length": len(data), "sha256": _sha(data)}


def _performance(history):
    """Aggregate every accepted epoch, with unavailable material families explicit."""
    if not history:
        raise ValueError("complete accepted history is required")
    points = [point for row in history for point in row["fiber_results"]]
    steel = [p["material_state"] for p in points if p["material_kind"] == "steel"]
    concrete = [p["material_state"] for p in points if p["material_kind"] == "concrete"]
    result = {
        "maximum_translation_m": max(
            math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
            for row in history
            for node in row["node_displacements"]
        ),
        "maximum_absolute_fiber_strain": max(abs(p["strain"]) for p in points),
        "terminal_maximum_translation_m": max(
            math.hypot(node["UX_m"], node["UY_m"], node["UZ_m"])
            for node in history[-1]["node_displacements"]
        ),
        "terminal_maximum_absolute_fiber_strain": max(
            abs(p["strain"]) for p in history[-1]["fiber_results"]
        ),
        "maximum_steel_accumulated_plastic_strain": max(
            (p["accumulated_plastic_strain"] for p in steel), default=None
        ),
        "maximum_concrete_tensile_damage": max(
            (p["tensile_damage"] for p in concrete), default=None
        ),
        "maximum_concrete_compressive_damage": max(
            (p["compressive_damage"] for p in concrete), default=None
        ),
        "terminal_load_factor": history[-1]["load_factor"],
        "minimum_load_factor": min(row["load_factor"] for row in history),
        "maximum_load_factor": max(row["load_factor"] for row in history),
        "accepted_epoch_count": len(history),
    }
    design._finite_tree(result)
    return result


def _screens(performance, history_limits, material_limits, terminal_limits=None):
    limits = asdict(history_limits) | asdict(material_limits)
    if terminal_limits is not None:
        limits.update({f"terminal_{k}": v for k, v in asdict(terminal_limits).items()})
    return {
        key: {
            "value": performance[key],
            "limit": limit,
            "status": "unavailable"
            if performance[key] is None
            else "pass"
            if performance[key] <= limit
            else "fail",
        }
        for key, limit in limits.items()
    }


def compare_rc_control_designs(
    baseline: CanonicalModel,
    candidates: tuple[design.FiberFrameDesignCandidate, ...],
    request: BoundedRCFiberDirectControlRequest,
    *,
    history_limits: design.FiberFrameHistoryLimits,
    material_limits: design.FiberFrameMaterialHistoryLimits,
    prices: design.FiberFrameMaterialPrices | None,
    source_revision: str,
    output_directory: Path,
    terminal_limits: design.FiberFrameTerminalLimits | None = None,
) -> dict:
    """Analyze and freshly reverify baseline and every candidate from epoch zero.

    Writes originals into a new, exclusive directory. Failed alternatives stay in
    the denominator; quantities survive numerical failure. An I/O failure aborts
    publication instead of silently losing an original numerical artifact.
    """
    if type(baseline) is not CanonicalModel:
        raise ValueError("exact canonical baseline required")
    if type(request) is not BoundedRCFiberDirectControlRequest:
        raise ValueError("exact RC control request required")
    request = decode_bounded_rc_fiber_direct_control_request(_bytes(request.to_dict()))
    if not request.targets_m:
        raise ValueError("at least one authored target required")
    if type(candidates) is not tuple or not 1 <= len(candidates) <= 16:
        raise ValueError("one to sixteen candidates required")
    if any(type(c) is not design.FiberFrameDesignCandidate for c in candidates):
        raise ValueError("exact section-change candidates required")
    if len({c.candidate_id for c in candidates}) != len(candidates):
        raise ValueError("candidate identities must be unique")
    if type(history_limits) is not design.FiberFrameHistoryLimits:
        raise ValueError("explicit full-history screens required")
    if type(material_limits) is not design.FiberFrameMaterialHistoryLimits:
        raise ValueError("explicit full-material-history screens required")
    if (
        terminal_limits is not None
        and type(terminal_limits) is not design.FiberFrameTerminalLimits
    ):
        raise ValueError("exact terminal screens required")
    if prices is not None and type(prices) is not design.FiberFrameMaterialPrices:
        raise ValueError("exact common price table required")
    candidates = tuple(
        design.FiberFrameDesignCandidate(
            c.candidate_id,
            tuple(
                design.FiberFrameSectionChange(**asdict(change)) for change in c.changes
            ),
        )
        for c in candidates
    )
    history_limits = design.FiberFrameHistoryLimits(**asdict(history_limits))
    material_limits = design.FiberFrameMaterialHistoryLimits(**asdict(material_limits))
    terminal_limits = (
        None
        if terminal_limits is None
        else design.FiberFrameTerminalLimits(**asdict(terminal_limits))
    )
    prices = (
        None if prices is None else design.FiberFrameMaterialPrices(**asdict(prices))
    )
    if not isinstance(source_revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", source_revision
    ):
        raise ValueError("40-character caller source revision required")
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    start_wall, start_cpu = perf_counter_ns(), process_time_ns()
    identity = {
        "schema_version": SCHEMA,
        "baseline_checksum": baseline.canonical_model_checksum,
        "candidates": [asdict(candidate) for candidate in candidates],
        "control_request": request.to_dict(),
        "history_limits": asdict(history_limits),
        "material_limits": asdict(material_limits),
        "terminal_limits": None if terminal_limits is None else asdict(terminal_limits),
        "prices": None if prices is None else asdict(prices),
        "price_table_hash": None if prices is None else prices.price_table_hash,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
    }
    _save(root, "request.json", _bytes(identity))
    kwargs = request.api_kwargs() | {"restart": None}
    rows = []
    for candidate in (None, *candidates):
        candidate_id = "baseline" if candidate is None else candidate.candidate_id
        row: dict[str, Any] = {
            "candidate_id": candidate_id,
            "status": "invalid_candidate",
            "artifacts": {},
            "quantities": None,
            "material_estimate": None,
            "performance": None,
            "screens": None,
            "full_reference_verification_pass": False,
            "selection_eligible": False,
            "invocations": [],
            "failure": None,
        }
        rows.append(row)
        try:
            model = (
                baseline.detached_analysis_snapshot()
                if candidate is None
                else design.apply_fiber_frame_section_changes(baseline, candidate)
            )
            row["quantities"] = design.calculate_fiber_frame_member_quantities(model)
            row["material_estimate"] = design._estimate(row["quantities"], prices)
            model_bytes = _bytes(model.canonical_payload())
        except (ValueError, TypeError, KeyError) as error:
            row["failure"] = {
                "phase": "preparation",
                "kind": type(error).__name__,
                "detail": str(error),
            }
            continue
        row["artifacts"]["model"] = _save(
            root, f"{candidate_id}/model.json", model_bytes
        )
        result, raw, checkpoint = None, None, None
        payload: dict[str, Any] | None = None
        validation: dict[str, Any] | None = None
        for phase in ("analysis", "verification"):
            invocation: dict[str, Any] = {
                "phase": phase,
                "status": "started",
                "work": None,
                "unknown_execution_work": True,
            }
            row["invocations"].append(invocation)
            row["artifacts"][f"{phase}_started"] = _save(
                root, f"{candidate_id}/{phase}-started.json", _bytes(invocation)
            )
            wall, cpu = perf_counter_ns(), process_time_ns()
            try:
                if phase == "analysis":
                    result = api.analyze_bounded_rc_fiber_direct_control(
                        model, request.targets_m, **kwargs
                    )
                    raw = result.result_artifact_bytes()
                    payload = json.loads(raw)
                    checkpoint = (
                        result.checkpoint_artifact_bytes()
                        if payload["checkpoint"] is not None
                        else None
                    )
                    invocation["work"] = payload["metrics"]["control_work"]
                else:
                    if raw is None:
                        raise ValueError("original result required for verification")
                    validation = api.validate_bounded_rc_fiber_direct_control_artifacts(
                        model,
                        request.targets_m,
                        result=raw,
                        checkpoint=checkpoint,
                        **kwargs,
                    ).to_dict()
                    invocation["work"] = validation["replay_control_work"]
                invocation["status"] = "returned"
                invocation["unknown_execution_work"] = (
                    invocation["work"] is None
                    or invocation["work"].get("unknown_solver_work_attempt_count", 0)
                    > 0
                )
            except Exception as error:
                invocation["status"] = "raised"
                row["failure"] = {
                    "phase": phase,
                    "kind": type(error).__name__,
                    "detail": str(error),
                }
                row["status"] = "execution_error"
            finally:
                invocation["wall_ns"] = perf_counter_ns() - wall
                invocation["process_cpu_ns"] = process_time_ns() - cpu
            row["artifacts"][f"{phase}_outcome"] = _save(
                root, f"{candidate_id}/{phase}-outcome.json", _bytes(invocation)
            )
            # Artifact writes are outside the numerical exception handler: an
            # export failure must not masquerade as a solver failure.
            if phase == "analysis" and raw is not None:
                row["artifacts"]["result"] = _save(
                    root, f"{candidate_id}/result.json", raw
                )
                if checkpoint is not None:
                    row["artifacts"]["checkpoint"] = _save(
                        root, f"{candidate_id}/checkpoint.json", checkpoint
                    )
            elif validation is not None:
                row["artifacts"]["verification"] = _save(
                    root, f"{candidate_id}/verification.json", _bytes(validation)
                )
            if invocation["status"] == "raised":
                break
        if validation is None or payload is None:
            continue
        verified = (
            all(
                validation.get(key) is True
                for key in (
                    "artifact_contract_pass",
                    "contract_pass",
                    "physical_path_complete",
                    "fresh_source_execution_invoked",
                    "solver_replay_performed",
                )
            )
            and validation.get("verified_result_hash") == payload["result_hash"]
            and validation.get("errors") == []
            and validation.get("unavailable_execution_work") is False
        )
        verified = (
            verified
            and payload["contract_pass"] is True
            and len(payload["response_history"]) == len(request.targets_m)
        )
        row["full_reference_verification_pass"] = verified
        row["status"] = "verified" if verified else "verification_blocked"
        if not verified:
            row["failure"] = {
                "phase": "verification",
                "kind": "full_reference_blocked",
                "api_status": payload["status"],
                "errors": validation["errors"],
            }
            continue
        history = payload["response_history"]
        if request.constant_nodal_loads:
            history = [payload["preload_response"], *history]
        row["performance"] = _performance(history)
        row["screens"] = _screens(
            row["performance"], history_limits, material_limits, terminal_limits
        )
        row["selection_eligible"] = all(
            screen["status"] == "pass" for screen in row["screens"].values()
        )
    eligible = [row for row in rows if row["selection_eligible"]]
    selected = (
        min(
            eligible,
            key=lambda row: (row["material_estimate"]["total"], row["candidate_id"]),
        )
        if prices is not None and eligible
        else None
    )
    base = rows[0]
    for row in rows:
        row["quantity_delta"] = (
            None
            if row["quantities"] is None or base["quantities"] is None
            else {
                key: value - base["quantities"]["totals"][key]
                for key, value in row["quantities"]["totals"].items()
            }
        )
        row["scoped_estimate_reduction"] = (
            None
            if row["material_estimate"] is None or base["material_estimate"] is None
            else base["material_estimate"]["total"] - row["material_estimate"]["total"]
        )
    report = {
        **identity,
        "request_hash": _sha(_bytes(identity)),
        "rows": rows,
        "candidate_denominator": len(rows),
        "verified_count": sum(row["full_reference_verification_pass"] for row in rows),
        "selected_candidate_id": None if selected is None else selected["candidate_id"],
        "selection_basis": "minimum_common_scoped_estimate_among_full_reference_and_all_screen_passes",
        "selection_status": "prices_unavailable"
        if prices is None
        else "no_verified_feasible_candidate"
        if selected is None
        else "selected",
        "status": "complete"
        if all(row["full_reference_verification_pass"] for row in rows)
        else "incomplete",
        "total_wall_ns": perf_counter_ns() - start_wall,
        "total_process_cpu_ns": process_time_ns() - start_cpu,
        "timing_scope": "serial_study_including_preparation_original_analysis_fresh_verification_and_artifact_io_excluding_final_report_write",
        "claims": {
            "experimental_rc_control": True,
            "independent_physical_validation": False,
            "design_authority": False,
            "confirmed_currency_savings": False,
            "performance_improvement": False,
            "release_approved": False,
        },
    }
    design._finite_tree(report)
    report["report_hash"] = _sha(_bytes(report))
    _save(root, "comparison.json", _bytes(report))
    return report
