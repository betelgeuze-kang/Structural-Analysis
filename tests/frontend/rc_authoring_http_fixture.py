"""Bounded real-core authoring/scenario test driver, without production control routes.

Only four enumerated tiny software requests may be computed. The browser submits
them to the actual HTTP adapter; stdin explicitly starts one disposable worker.
HTTP and driver processes retain the existing zero-numerical-call guard.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import signal
import subprocess
import sys

from rc_lifecycle_http_fixture import (
    Supervisor,
    TENANTS,
    authored_explicit_layers_request,
    digest,
    emit,
    execute_rc_fiber_direct_control_claim,
    forbid_numerical_calls,
    original_bytes,
    service,
    tenant,
    valid_workspace,
    worker,
)
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    RCFiberDirectControlWorkerError,
)


def requests():
    baseline = authored_explicit_layers_request()
    baseline["case_id"] = "authoring-baseline"
    wider = deepcopy(baseline)
    wider["case_id"] = "authoring-wider"
    wider["model"]["sections"][0]["width_m"] *= 1.1
    failed = deepcopy(baseline)
    failed["case_id"] = "authoring-budget-limited"
    failed["execution_config"]["maximum_api_invocations"] = 2
    repaired = deepcopy(failed)
    repaired["execution_config"]["maximum_api_invocations"] = 8
    return {
        "baseline": baseline,
        "wider": wider,
        "failed": failed,
        "repaired": repaired,
    }


def execute_one(workspace):
    current = service(workspace / "store")
    claim = current.claim_next(**worker("fresh"), lease_seconds=60)
    assert claim is not None, "an explicitly submitted queued job is required"
    authored = json.loads(claim.request_bytes)
    assert authored in requests().values(), "only enumerated bounded inputs may run"
    job_id = claim.job.job_id
    request_hash = claim.job.request.content_hash
    for _ in range(2):
        assert (
            claim.job.job_id == job_id
            and claim.job.request.content_hash == request_hash
        )
        try:
            execute_rc_fiber_direct_control_claim(
                current, claim, **worker("fresh"), lease_seconds=60
            )
        except RCFiberDirectControlWorkerError as error:
            # A numerical or unrelated worker error must not masquerade as the
            # intended resource-budget failure.
            assert authored == requests()["failed"]
            assert error.code == "execution_attempt_budget_exhausted"
        job = current.get_job(job_id, **tenant())
        if job.status in {"failed", "succeeded"}:
            break
        assert job.status == "checkpointed"
        claim = current.claim_next(**worker("fresh"), lease_seconds=60)
        assert claim is not None
    expected = "failed" if authored == requests()["failed"] else "succeeded"
    assert job.status == expected
    if expected == "failed":
        assert job.error_code == "execution_attempt_budget_exhausted"
    emit(
        {
            "job": job.to_dict(),
            "invocations": current.read_rc_invocation_evidence(job.job_id, **tenant()),
        }
    )


def drive(workspace):
    supervisor = Supervisor(workspace)
    emit(
        {
            "ready": True,
            "requests": requests(),
            "credentials": {"tenantId": "a", "bearerToken": TENANTS["a"]},
        }
    )
    executions = 0
    try:
        with forbid_numerical_calls(workspace):
            for line in sys.stdin:
                message = json.loads(line)
                command = message["command"]
                if command == "start_http":
                    result = supervisor.command(message)
                elif command == "execute_one":
                    assert executions < 4
                    index = len(supervisor.processes)
                    errors = (
                        workspace / f"process-{index}-authoring-worker-stderr.txt"
                    ).open("w")
                    child = subprocess.Popen(
                        [
                            sys.executable,
                            "-B",
                            str(Path(__file__).resolve()),
                            "worker",
                            "--workspace",
                            str(workspace),
                        ],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=errors,
                        text=True,
                    )
                    process = {
                        "role": "authoring-worker",
                        "child": child,
                        "stderr": errors,
                        "stdout_path": workspace
                        / f"process-{index}-authoring-worker-stdout.jsonl",
                    }
                    supervisor.processes.append(process)
                    try:
                        result = supervisor.read(process, timeout=90)
                        assert child.wait(timeout=10) == 0
                    finally:
                        supervisor.stop(process)
                    executions += 1
                    result["process"] = {
                        "pid": child.pid,
                        "returncode": child.returncode,
                        "reaped": child.poll() is not None,
                    }
                elif command == "inspect_job":
                    current = service(workspace / "store")
                    job = current.get_job(message["job_id"], **tenant())
                    raw = original_bytes(current, job.request)
                    assert json.loads(raw) in requests().values()
                    result = {
                        "job": job.to_dict(),
                        "original_request": json.loads(raw),
                        "original_request_hash": digest(raw),
                    }
                elif command == "stop":
                    emit(
                        {
                            "id": message["id"],
                            "ok": True,
                            "result": {"executions": executions},
                        }
                    )
                    break
                else:
                    raise AssertionError("unknown authoring fixture command")
                emit({"id": message["id"], "ok": True, "result": result})
    finally:
        supervisor.close()
    assert not (workspace / "http-numerical-attempts.jsonl").exists()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("driver", "worker"))
    parser.add_argument("--workspace", required=True, type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not valid_workspace(workspace, args.mode):
        parser.error(
            "an existing disposable structural-rc-browser-* workspace is required"
        )
    if args.mode == "driver":
        assert not any(workspace.iterdir())
        drive(workspace)
    else:
        execute_one(workspace)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    main()
