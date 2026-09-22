"""Bounded independent-candidate threads over existing local durable leases.

This is a candidate batch, not a fair algorithm benchmark. No thread/process CPU
intervals are summed and no GPU/VRAM or hard-RSS limit is claimed. The caller can
stop reservation of NEW candidates; in-flight chunks finish under their leases.
"""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from threading import Event
from time import perf_counter_ns, process_time_ns

from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark.rc_control_durable import (
    DurableRCControlResultSession,
)
from structural_analysis.model.schema import CanonicalModel


def run_local_rc_batch(
    models: dict[str, CanonicalModel],
    request,
    *,
    session,
    scope_id,
    output_directory: Path,
    history_limits,
    material_limits,
    prices,
    terminal_limits=None,
    max_workers: int = 1,
    max_requested_models: int = 17,
    stop_event: Event | None = None,
):
    if type(session) is not DurableRCControlResultSession:
        raise ValueError("durable local session required")
    if type(models) is not dict or not 1 <= len(models) <= 17:
        raise ValueError("one to seventeen authored models required")
    if type(max_workers) is not int or not 1 <= max_workers <= 4:
        raise ValueError("max_workers must be in [1, 4]")
    if type(max_requested_models) is not int or not 0 <= max_requested_models <= 17:
        raise ValueError("max_requested_models must be in [0, 17]")
    if stop_event is not None and not isinstance(stop_event, Event):
        raise ValueError("threading.Event required")
    snapshots = {}
    seen = set()
    for name, model in models.items():
        design._identifier(name, "candidate_id")
        if type(model) is not CanonicalModel:
            raise ValueError("canonical model required")
        snapshot = model.detached_analysis_snapshot()
        key = study._sha(study._bytes(snapshot.to_dict()))
        if key in seen:
            raise ValueError("duplicate physical input in one parallel batch")
        seen.add(key)
        snapshots[name] = snapshot
    # Validate all common options before scheduling any numerical execution.
    from structural_analysis.benchmark.rc_control_reuse import _inputs

    for model in snapshots.values():
        _inputs(
            model, request, history_limits, material_limits, terminal_limits, prices
        )
    session._check_context(scope_id)
    root = Path(output_directory)
    root.mkdir(parents=True, exist_ok=False)
    wall, cpu = perf_counter_ns(), process_time_ns()
    names = list(snapshots)
    records = {name: {"status": "unrequested"} for name in names}
    scheduled = 0
    stopped = False

    def evaluate(name):
        return session.evaluate(
            snapshots[name],
            request,
            scope_id=scope_id,
            output_directory=root / name,
            history_limits=history_limits,
            material_limits=material_limits,
            prices=prices,
            terminal_limits=terminal_limits,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as workers:
        active = {}
        while active or (
            scheduled < min(len(names), max_requested_models) and not stopped
        ):
            stopped = stopped or (stop_event is not None and stop_event.is_set())
            while (
                len(active) < max_workers
                and scheduled < min(len(names), max_requested_models)
                and not stopped
            ):
                name = names[scheduled]
                scheduled += 1
                active[workers.submit(evaluate, name)] = name
            if not active:
                break
            done, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in done:
                name = active.pop(future)
                try:
                    result = future.result()
                except Exception as exc:
                    # Do not speculate about work after an unexpected failure.
                    records[name] = {
                        "status": "interrupted_or_failed",
                        "error_type": type(exc).__name__,
                        "unknown_work": True,
                    }
                    stopped = True
                else:
                    records[name] = {
                        "status": result["job"]["status"],
                        "evaluation_path": name + "/evaluation.json",
                        "report_hash": result["report_hash"],
                        "new_work": result["new_work"],
                        "verified": result["row"]["full_reference_verification_pass"],
                    }
                    stopped = stopped or result["historical_unknown_work"]
    report = {
        "schema_version": "local-durable-rc-batch.v1",
        "candidate_denominator": len(names),
        "requested_count": scheduled,
        "records": records,
        "max_workers": max_workers,
        "reservation_stopped": stopped,
        "wall_ns": perf_counter_ns() - wall,
        "whole_process_cpu_ns": process_time_ns() - cpu,
        "claims": {
            "hard_memory_limit": False,
            "gpu_execution": False,
            "performance_improvement": False,
            "strategy_comparison": False,
        },
    }
    report["report_hash"] = study._sha(study._bytes(report))
    study._save(root, "batch.json", study._bytes(report))
    return report
