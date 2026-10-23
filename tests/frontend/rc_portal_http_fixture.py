"""One authored portal through actual HTTP, worker loss and fresh workers.

Only the checked-in tiny elastic-range software example may execute. The
browser submits it. Stdin controls disposable processes, never production
routes. SIGKILL occurs after a committed checkpoint, not within a solver step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys

from rc_lifecycle_http_fixture import (
    ROOT,
    Supervisor,
    TENANTS,
    canonical,
    digest,
    emit,
    forbid_numerical_calls,
    numerical_rows,
    original_bytes,
    service,
    tenant,
    valid_workspace,
    worker,
)
from structural_analysis.execution.job_worker import execute_job_claim


def authored_request():
    return json.loads(
        (
            ROOT / "examples/public_rc_portal_frame_corotational_request.json"
        ).read_bytes()
    )


def run_worker(workspace, name):
    current = service(workspace / "store")
    claim = current.claim_next(**worker(name), lease_seconds=120)
    assert claim is not None
    assert json.loads(claim.request_bytes) == authored_request()
    job_id = claim.job.job_id
    original_hash = claim.job.request.content_hash
    starting_checkpoint = claim.job.checkpoint
    if name == "fresh":
        assert starting_checkpoint is not None
    for _ in range(3):
        job = execute_job_claim(current, claim, **worker(name), lease_seconds=120)
        assert job.request.content_hash == original_hash
        if name == "first":
            assert job.status == "checkpointed" and job.checkpoint is not None
            emit({"job": job.to_dict(), "checkpoint_hash": job.checkpoint.content_hash})
            # The driver kills this process only after receiving the receipt.
            assert sys.stdin.readline() == "unexpected continuation\n"
        if job.status == "succeeded":
            break
        assert job.status == "checkpointed"
        claim = current.claim_next(**worker(name), lease_seconds=120)
        assert claim is not None and claim.job.job_id == job_id
    assert job.status == "succeeded"
    assert current.validate_integrity(job_id, **tenant())["contract_pass"]
    emit(
        {
            "job": job.to_dict(),
            "resumed_checkpoint_hash": starting_checkpoint.content_hash,
            "invocations": current.read_rc_invocation_evidence(job_id, **tenant()),
        }
    )


def spawn_worker(supervisor, name):
    index = len(supervisor.processes)
    errors = (supervisor.workspace / f"process-{index}-portal-stderr.txt").open("w")
    child = subprocess.Popen(
        [
            sys.executable,
            "-B",
            str(Path(__file__).resolve()),
            "worker",
            "--workspace",
            str(supervisor.workspace),
            "--name",
            name,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=errors,
        text=True,
    )
    process = {
        "role": "portal-worker",
        "child": child,
        "stderr": errors,
        "stdout_path": supervisor.workspace / f"process-{index}-portal-stdout.jsonl",
    }
    supervisor.processes.append(process)
    return process


def drive(workspace):
    supervisor = Supervisor(workspace)
    first = None
    completed = False
    before_reads = None
    emit(
        {
            "ready": True,
            "request": authored_request(),
            "credentials": {"tenantId": "a", "bearerToken": TENANTS["a"]},
        }
    )
    try:
        with forbid_numerical_calls(workspace):
            for line in sys.stdin:
                message = json.loads(line)
                command = message["command"]
                if command in {"start_http", "restart_http"}:
                    result = supervisor.command(message)
                elif command == "first_checkpoint":
                    assert first is None
                    first = spawn_worker(supervisor, "first")
                    result = supervisor.read(first)
                    result["pid"] = first["child"].pid
                elif command == "kill_first":
                    assert first is not None and first["child"].poll() is None
                    first["child"].kill()
                    code = first["child"].wait(timeout=10)
                    assert code == -signal.SIGKILL
                    result = {
                        "pid": first["child"].pid,
                        "returncode": code,
                        "reaped": True,
                        "barrier": "committed checkpoint",
                    }
                elif command == "finish":
                    assert (
                        first is not None and first["child"].poll() == -signal.SIGKILL
                    )
                    assert not completed
                    fresh = spawn_worker(supervisor, "fresh")
                    result = supervisor.read(fresh)
                    assert fresh["child"].wait(timeout=10) == 0
                    result["pid"] = fresh["child"].pid
                    assert result["pid"] != first["child"].pid
                    supervisor.stop(fresh)
                    completed = True
                    before_reads = numerical_rows(supervisor.store)
                elif command == "inspect_job":
                    current = service(supervisor.store)
                    job = current.get_job(message["job_id"], **tenant())
                    raw = original_bytes(current, job.request)
                    assert json.loads(raw) == authored_request()
                    result = {"job": job.to_dict(), "request_hash": digest(raw)}
                elif command == "verify_reads":
                    assert (
                        completed and numerical_rows(supervisor.store) == before_reads
                    )
                    assert not (workspace / "http-numerical-attempts.jsonl").exists()
                    result = {
                        "http_numerical_calls": 0,
                        "numerical_state_unchanged": True,
                        "state_hash": digest(canonical(before_reads)),
                    }
                elif command == "stop":
                    emit(
                        {
                            "id": message["id"],
                            "ok": True,
                            "result": {"completed": completed},
                        }
                    )
                    break
                else:
                    raise AssertionError("unknown portal fixture command")
                emit({"id": message["id"], "ok": True, "result": result})
    finally:
        supervisor.close()
    assert not (workspace / "http-numerical-attempts.jsonl").exists()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("driver", "worker"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--name", choices=("first", "fresh"))
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
        assert args.name is not None
        run_worker(workspace, args.name)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))
    main()
