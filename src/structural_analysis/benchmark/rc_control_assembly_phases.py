"""Diagnostic phase counts from complete or failed recorded control paths."""

from collections import Counter

from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.solvers.nonlinear.assembly_work import ASSEMBLY_TIMING_SCOPE


def summarize_rc_control_assembly_phases(path):
    """Retain failed dispatches; missing/in-flight records never become zero work.

    A matching path hash checks internal consistency, not source provenance or
    physical authority. Counts cover Newton assembly dispatches only.
    """
    payload = dict(path)
    if payload.pop("path_hash", None) != _sha(_bytes(payload)):
        raise ValueError("control path hash differs")
    phases, statuses = Counter(), Counter()
    missing = in_flight = reuse = invocations = 0
    phase_times = Counter()
    timed_invocations = 0
    groups = [path.get("preload_invocations", [])] + [
        entry["invocations"] for entry in path["entries"]
    ]
    for group in groups:
        for invocation in group:
            invocations += 1
            work = invocation.get("newton_assembly_work")
            if work is None:
                missing += 1
                continue
            if work.get("schema_version") != "vector-newton-assembly-dispatch-work.v1":
                raise ValueError("unsupported assembly dispatch record")
            calls = work["calls"]
            timed = work.get("timing_scope") is not None
            if timed and work["timing_scope"] != ASSEMBLY_TIMING_SCOPE:
                raise ValueError("unsupported assembly timing scope")
            timed_invocations += int(timed)
            elapsed = 0
            counts = Counter()
            for ordinal, call in enumerate(calls, 1):
                if type(call["ordinal"]) is not int or call["ordinal"] != ordinal:
                    raise ValueError("ordered assembly dispatches required")
                phase, status = call["phase"], call["status"]
                if (
                    type(phase) is not str
                    or not phase
                    or status not in ("returned", "raised", "started")
                ):
                    raise ValueError("explicit phase and dispatch status required")
                phases[phase] += 1
                counts[status] += 1
                if timed:
                    duration = call.get("wall_ns")
                    if status == "started":
                        if duration is not None:
                            raise ValueError(
                                "in-flight assembly duration must be unknown"
                            )
                    elif type(duration) is not int or duration < 0:
                        raise ValueError(
                            "nonnegative completed assembly duration required"
                        )
                    else:
                        phase_times[phase] += duration
                        elapsed += duration
            if timed:
                total = work.get("wall_ns")
                if counts["started"]:
                    if total is not None:
                        raise ValueError("in-flight assembly total must be unknown")
                elif type(total) is not int or total != elapsed:
                    raise ValueError("assembly timing total differs")
            for key, expected in (
                ("call_count", len(calls)),
                ("returned_count", counts["returned"]),
                ("exception_count", counts["raised"]),
                ("in_flight_count", counts["started"]),
            ):
                if type(work[key]) is not int or work[key] != expected:
                    raise ValueError("assembly dispatch total differs")
            hits = work.get("line_search_reuse_hit_count", 0)
            if type(hits) is not int or hits < 0:
                raise ValueError("nonnegative assembly reuse count required")
            reuse += hits
            in_flight += counts["started"]
            statuses.update(counts)
    complete = missing == in_flight == 0
    return {
        "schema_version": "rc-control-assembly-phase-summary.v1",
        "source_path_hash": path["path_hash"],
        "path_status": path["status"],
        "invocation_count": invocations,
        "missing_record_count": missing,
        "in_flight_count": in_flight,
        "raised_dispatch_count": statuses["raised"],
        "observed_phase_counts": dict(sorted(phases.items())),
        "phase_counts": dict(sorted(phases.items())) if complete else None,
        "dispatch_count": sum(phases.values()) if complete else None,
        "observed_line_search_reuse_hits": reuse,
        "phase_wall_ns": dict(sorted(phase_times.items()))
        if complete and invocations > 0 and timed_invocations == invocations
        else None,
        **({"timing_scope": ASSEMBLY_TIMING_SCOPE} if timed_invocations else {}),
        "outside_newton_assembly_calls": None,
        "physical_validation": False,
        "source_file_authentication": False,
    }
