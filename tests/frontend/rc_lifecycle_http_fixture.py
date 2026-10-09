"""Hosted-only Workbench lifecycle fixture with real HTTP and RC processes.

The browser owns job submission and both price declarations. This test driver
only controls processes and inspects their durable evidence over stdin/stdout;
there is no fixture control route in the production HTTP adapter. The HTTP
process forbids numerical calls, and only the two explicitly started worker
processes may execute the fixed, tiny authored RC request. No completed result,
checkpoint, browser Worker, or review response is synthesized.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from structural_analysis.api import rc_fiber_frame_direct_control as rc_api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.execution.job_http_api import DurableJobWSGIApplication
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.rc_fiber_direct_control_worker import (
    execute_rc_fiber_direct_control_claim,
)
from structural_analysis.solvers.nonlinear import newton


ROOT = Path(__file__).resolve().parents[2]
TENANTS = {name: f"synthetic-rc-browser-{name}-token" for name in ("a", "b")}
WORKERS = {name: f"synthetic-rc-browser-{name}-token" for name in ("first", "fresh")}
SOURCE_REVISION = "a" * 40  # Explicit caller declaration, never checkout identity.
LEASE_SECONDS = 5
NUMERICAL_TABLES = (
    "jobs",
    "job_events",
    "job_rc_invocation_outcomes",
    "job_execution_budgets",
)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def emit(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def service(store):
    return DurableJobService(
        store,
        tenant_tokens=TENANTS,
        worker_tokens=WORKERS,
        worker_tenants={name: {"a"} for name in WORKERS},
    )


def tenant():
    return {"tenant_id": "a", "authorization_token": TENANTS["a"]}


def worker(name):
    return {"worker_id": name, "authorization_token": WORKERS[name]}


def authored_request():
    return {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "hosted-workbench-process-recovery",
        "model": json.loads(
            (ROOT / "examples/public_rc_fiber_frame_cantilever.json").read_text()
        ),
        "config": BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6)).to_dict(),
        "source_revision": SOURCE_REVISION,
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 8},
    }


def authored_explicit_layers_request():
    request = authored_request()
    request["case_id"] = "hosted-workbench-explicit-steel-layers"
    request["model"] = json.loads(
        (ROOT / "examples/public_rc_fiber_frame_explicit_layers.json").read_text()
    )
    return request


def is_authored_request(value):
    return value in (
        authored_request(),
        authored_explicit_layers_request(),
        authored_pin_roller_request(),
        authored_pin_roller_layers_request(),
        authored_isolated_request("explicit-layers"),
        authored_isolated_request("pin-roller-layers"),
        authored_prescribed_trial_request(),
    )


def authored_prescribed_trial_request():
    request = authored_isolated_request("explicit-layers")
    request["config"]["solver_config"]["initial_trial_policy"] = "prescribed_control"
    return request


def authored_pin_roller_request():
    request = authored_request()
    request["schema_version"] = "structural-analysis-job-request.v4"
    request["case_id"] = "synthetic-pin-roller-browser"
    request["config"].update(
        schema_version="bounded-rc-fiber-direct-control-request.v4",
        experimental_pin_roller_beam=True,
        control_global_dof=10,
    )
    model = request["model"]
    stations = (0.0, 0.2, 0.7, 0.95, 1.2, 1.7, 1.9)
    model["nodes"] = [
        {"id": f"N{i + 1}", "coordinates": [x, 0.0, 0.0]}
        for i, x in enumerate(stations)
    ]
    model["elements"] = [
        dict(model["elements"][0], id=f"M{i + 1}", nodes=[f"N{i + 1}", f"N{i + 2}"])
        for i in range(6)
    ]
    model["supports"] = [
        {"node": "N2", "dofs": ["UX", "UY"]},
        {"node": "N6", "dofs": ["UY"]},
    ]
    model["loads"] = [
        dict(deepcopy(model["loads"][0]), node=node) for node in ("N3", "N5")
    ]
    return request


def authored_pin_roller_layers_request():
    request = authored_pin_roller_request()
    request["case_id"] = "synthetic-pin-roller-explicit-layers"
    layers = authored_explicit_layers_request()["model"]
    request["model"]["materials"] = layers["materials"]
    request["model"]["sections"] = layers["sections"]
    return request


def authored_isolated_request(profile):
    request = (authored_explicit_layers_request() if profile == "explicit-layers"
               else authored_pin_roller_layers_request())
    request["execution_config"]["phase_execution_policy"] = {
        "schema_version": "bounded-rc-fiber-phase-execution-policy.v1",
        "analysis_timeout_ms": 30000, "verification_timeout_ms": 30000,
        "termination_grace_ms": 100,
    }
    return request


def append_receipt(path, value):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, allow_nan=False) + "\n")


@contextmanager
def forbid_numerical_calls(workspace):
    """Attempt receipts survive even if an application catches our exception."""

    def forbidden(*args, **kwargs):
        append_receipt(
            workspace / "http-numerical-attempts.jsonl", {"pid": os.getpid()}
        )
        raise AssertionError("HTTP/report paths must execute zero numerical calls")

    with ExitStack() as stack:
        for module, name in (
            (rc_api, "analyze_bounded_rc_fiber_direct_control"),
            (rc_api, "validate_bounded_rc_fiber_direct_control_artifacts"),
            (paths, "_execute_raw"),
            (newton, "newton_raphson_vector"),
        ):
            stack.enter_context(patch.object(module, name, forbidden))
        yield


def numerical_rows(store):
    with sqlite3.connect(store / "jobs.sqlite3") as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in NUMERICAL_TABLES
        }


def original_bytes(current, reference):
    assert reference is not None
    # Read-only test inspection of the actual content-addressed storage, never a
    # new HTTP route. Recheck its persisted length and hash before returning it.
    raw = current._blob_path(reference.content_hash).read_bytes()
    assert len(raw) == reference.byte_length
    assert digest(raw) == reference.content_hash
    return raw


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def build_application(workspace):
    """Only actual /v1 API routes and built dist files are served."""
    api = DurableJobWSGIApplication(service(workspace / "store"))
    dist = (ROOT / "dist").resolve()

    def application(environ, start_response):
        path = environ["PATH_INFO"]
        if path.startswith("/v1/"):

            def record_response(status, headers):
                append_receipt(
                    workspace / "http-requests.jsonl",
                    {
                        "pid": os.getpid(),
                        "method": environ["REQUEST_METHOD"],
                        "path": path,
                        "status": int(status.split(" ")[0]),
                    },
                )
                return start_response(status, headers)

            return api(environ, record_response)
        target = (dist / path.lstrip("/")).resolve()
        if not target.is_relative_to(dist):
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        if not target.is_file():
            target = dist / "index.html"
        if not target.is_file():
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Build dist before starting this fixture"]
        raw = target.read_bytes()
        start_response(
            "200 OK",
            [
                (
                    "Content-Type",
                    mimetypes.guess_type(target)[0] or "application/octet-stream",
                ),
                ("Content-Length", str(len(raw))),
                ("Cache-Control", "no-store"),
            ],
        )
        return [raw]

    return application


def serve(workspace, port):
    assert (ROOT / "dist/index.html").is_file(), "build the actual frontend first"
    with forbid_numerical_calls(workspace):
        with make_server(
            "127.0.0.1", port, build_application(workspace), handler_class=QuietHandler
        ) as server:
            emit(
                {
                    "pid": os.getpid(),
                    "origin": f"http://127.0.0.1:{server.server_port}",
                    "port": server.server_port,
                }
            )
            server.serve_forever()


def run_worker(workspace, name):
    current = service(workspace / "store")
    # Only the two fixed, tiny, UI-submitted requests are authorized here.
    deadline = time.monotonic() + 20
    claim = None
    while claim is None:
        claim = current.claim_next(
            **worker(name), lease_seconds=60 if name == "fresh" else LEASE_SECONDS
        )
        if claim is None:
            assert name == "fresh" and time.monotonic() < deadline
            time.sleep(0.1)  # Wait for the dead process's actual lease to expire.
    assert is_authored_request(json.loads(claim.request_bytes))
    counts = {"analysis": 0, "verification": 0}
    isolated = "phase_execution_policy" in json.loads(claim.request_bytes)["execution_config"]
    from structural_analysis.execution import rc_fiber_phase_supervisor as supervisor
    phase_receipts = []
    original_phase = supervisor.run_rc_fiber_phase

    def observed_phase(**kwargs):
        reply = original_phase(**kwargs)
        phase_receipts.append({"phase": kwargs["phase"], "status": reply.status,
                               "supervision": reply.supervisor_timing})
        return reply
    phase = ["analysis"]
    analyze_original = rc_api.analyze_bounded_rc_fiber_direct_control
    verify_original = rc_api.validate_bounded_rc_fiber_direct_control_artifacts

    def analyze(*args, **kwargs):
        if phase[0] == "analysis":
            counts["analysis"] += 1
        return analyze_original(*args, **kwargs)

    def verify(*args, **kwargs):
        counts["verification"] += 1
        phase[0] = "verification"
        try:
            return verify_original(*args, **kwargs)
        finally:
            phase[0] = "analysis"

    if name == "fresh":
        assert claim.job.progress_completed == 1 and claim.checkpoint_bytes is not None
        assert digest(claim.checkpoint_bytes) == claim.job.checkpoint.content_hash
        emit(
            {
                "pid": os.getpid(),
                "job_id": claim.job.job_id,
                "progress": claim.job.progress_completed,
                "checkpoint_hash": digest(claim.checkpoint_bytes),
                "request_hash": digest(claim.request_bytes),
                "actual_calls": dict(counts),
                "isolated_phases": list(phase_receipts),
            }
        )
        assert sys.stdin.readline() == "continue\n"
        # This stdin barrier verifies restoration before any resumed numerical
        # call. A longer fresh lease avoids a slow browser expiring the barrier.
        current.heartbeat(
            claim.job.job_id,
            **worker(name),
            lease_token=claim.lease_token,
            lease_seconds=60,
        )
    else:
        assert claim.job.progress_completed == 0 and claim.checkpoint_bytes is None
    with (
        patch.object(supervisor, "run_rc_fiber_phase", observed_phase),
        patch.object(rc_api, "analyze_bounded_rc_fiber_direct_control", analyze),
        patch.object(
            rc_api, "validate_bounded_rc_fiber_direct_control_artifacts", verify
        ),
    ):
        result = execute_rc_fiber_direct_control_claim(
            current, claim, **worker(name), lease_seconds=60
        )
    assert counts == {"analysis": 0 if isolated else 1, "verification": 0 if isolated else 1}
    assert [item["phase"] for item in phase_receipts] == (["analysis", "verification"] if isolated else [])
    for item in phase_receipts:
        assert item["status"] == "returned"
        assert item["supervision"]["direct_child_reaped"]
        assert item["supervision"]["child_returncode"] == 0
    if name == "first":
        assert result.status == "checkpointed" and result.progress_completed == 1
        abandoned = current.claim_next(**worker(name), lease_seconds=LEASE_SECONDS)
        assert abandoned is not None and abandoned.job.job_id == result.job_id
        ordinal = current.reserve_execution_attempt(
            result.job_id, **worker(name), lease_token=abandoned.lease_token
        )
        assert ordinal == 3
        emit(
            {
                "pid": os.getpid(),
                "job_id": result.job_id,
                "checkpoint_hash": result.checkpoint.content_hash,
                "abandoned_ordinal": ordinal,
                "actual_calls": counts,
                "isolated_phases": list(phase_receipts),
            }
        )
        while True:
            time.sleep(60)  # Parent must SIGKILL, not a graceful exit.
    assert result.status == "succeeded" and result.progress_completed == 2
    emit({"pid": os.getpid(), "job": result.to_dict(), "actual_calls": counts, "isolated_phases": list(phase_receipts)})


class Supervisor:
    """Control/inspection only. No job submission or report writes live here."""

    def __init__(self, workspace):
        self.workspace = workspace
        self.runtime_workspace = workspace
        self.original_store = self.original_rows = None
        self.store = workspace / "store"
        assert not self.store.exists(), "an empty isolated durable store is required"
        service(self.store)
        self.processes = []
        self.http = self.first = self.fresh = None
        self.port = 0
        self.before_prices = None
        self.prices_job_id = None
        self.reports_before_restart = None
        try:
            checkout = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=ROOT,
                text=True,
                stderr=subprocess.DEVNULL,
            ).strip()
        except (OSError, subprocess.CalledProcessError):
            checkout = None
        self.proof = {
            "schema_version": "workbench-real-rc-process-lifecycle.v1",
            "checkout_sha": checkout,
            "github_sha": os.environ.get("GITHUB_SHA"),
            "github_run_id": os.environ.get("GITHUB_RUN_ID"),
            "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "source_revision_caller_declaration": SOURCE_REVISION,
            "independent_physical_validation": False,
            "design_authority": False,
            "commands": [],
        }
        self.save_proof()

    def save_proof(self):
        self.proof["processes"] = [
            {
                "role": record["role"],
                "pid": record["child"].pid,
                "returncode": record["child"].poll(),
            }
            for record in self.processes
        ]
        (self.workspace / "driver-proof.json").write_text(
            json.dumps(self.proof, indent=2, sort_keys=True), encoding="utf-8"
        )

    def spawn(self, role, *arguments):
        index = len(self.processes)
        errors = (self.workspace / f"process-{index}-{role}-stderr.txt").open("w")
        child = subprocess.Popen(
            [
                sys.executable,
                "-B",
                str(Path(__file__).resolve()),
                role,
                "--workspace",
                str(self.runtime_workspace),
                *arguments,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=errors,
            text=True,
        )
        record = {
            "role": role,
            "child": child,
            "stderr": errors,
            "stdout_path": self.workspace / f"process-{index}-{role}-stdout.jsonl",
        }
        self.processes.append(record)
        return record

    def read(self, record, timeout=90):
        child = record["child"]
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout), f"{record['role']} process timed out"
        line = child.stdout.readline()
        assert line, (
            f"{record['role']} exited before its evidence barrier; inspect stderr"
        )
        with record["stdout_path"].open("a") as stream:
            stream.write(line)
        return json.loads(line)

    @staticmethod
    def stop(record):
        if record is None:
            return
        child = record["child"]
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        record["stderr"].close()
        for stream in (child.stdin, child.stdout):
            if stream is not None:
                stream.close()

    def inspect_job(self, job_id):
        current = service(self.store)
        job = current.get_job(job_id, **tenant())
        request = original_bytes(current, job.request)
        assert is_authored_request(json.loads(request))
        result = {
            "job": job.to_dict(),
            "original_request": json.loads(request),
            "original_request_hash": digest(request),
        }
        if job.checkpoint is not None:
            checkpoint = original_bytes(current, job.checkpoint)
            result["checkpoint_hash"] = digest(checkpoint)
        if job.status == "succeeded":
            raw = current.read_result(job_id, **tenant())
            payload = json.loads(raw)
            evidence = current.read_rc_invocation_evidence(job_id, **tenant())
            assert payload["completed_target_count"] == 2
            assert len(payload["receipts"]) == 2
            assert payload["receipts"][1]["restart_input_sha256"] is not None
            assert payload["execution_budget"]["reserved_attempts"] == 5
            assert evidence["pending_ordinals"] == [3]
            assert evidence["pending_execution_work"] == "unknown"
            assert [item["ordinal"] for item in evidence["invocations"]] == [1, 2, 4, 5]
            result.update({"result_hash": digest(raw), "invocation_evidence": evidence})
        return result

    def reports(self, job_id):
        current = service(self.store)
        page = current.list_rc_quantity_reports(job_id, **tenant())
        reports = page["reports"]
        for report in reports:
            raw = current.read_rc_quantity_report(
                job_id, report["report_id"], **tenant()
            )
            assert digest(raw) == report["content_hash"]
        return reports

    def command(self, message):
        command = message["command"]
        if command in {"start_http", "restart_http"}:
            if command == "start_http":
                assert self.http is None
            else:
                assert self.http is not None
                previous_pid = self.http["child"].pid
                self.stop(self.http)
                assert self.http["child"].poll() is not None
            self.http = self.spawn("http", "--port", str(self.port))
            result = self.read(self.http, timeout=20)
            self.port = result["port"]
            if command == "restart_http":
                assert result["pid"] != previous_pid
                result["previous_pid"] = previous_pid
        elif command == "inspect_job":
            result = self.inspect_job(message["job_id"])
        elif command == "first_checkpoint":
            assert self.first is None
            self.first = self.spawn("worker", "--name", "first")
            result = self.read(self.first)
            assert result["abandoned_ordinal"] == 3
            self.proof["first_checkpoint"] = result
        elif command == "kill_first":
            assert self.first is not None and self.first["child"].poll() is None
            self.first["child"].kill()
            code = self.first["child"].wait(timeout=10)
            assert code == -signal.SIGKILL
            result = {
                "pid": self.first["child"].pid,
                "returncode": code,
                "signal": "SIGKILL",
            }
            self.proof["first_worker_death"] = result
        elif command == "backup_restore":
            # Private test-driver operation, never a production HTTP route.
            # The operator stops all original writers before activating a copy.
            from structural_analysis.execution.job_store_backup import (
                backup_job_store,
                restore_job_store,
                verify_job_store_backup,
            )

            assert (
                self.first is not None and self.first["child"].poll() == -signal.SIGKILL
            )
            assert self.fresh is None and self.original_store is None
            assert self.http is not None
            self.stop(self.http)
            assert self.http["child"].poll() is not None
            self.original_store = self.store
            self.original_rows = numerical_rows(self.store)
            limit = 10 * 1024 * 1024
            sealed = self.workspace / "sealed-backup"
            receipt = backup_job_store(self.store, sealed, maximum_bytes=limit)
            verified = verify_job_store_backup(
                sealed, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=limit
            )
            self.runtime_workspace = self.workspace / "recovered-runtime"
            self.runtime_workspace.mkdir()
            self.store = self.runtime_workspace / "store"
            restore_job_store(
                sealed,
                self.store,
                manifest_sha256=receipt["manifest_sha256"],
                maximum_bytes=limit,
            )
            assert numerical_rows(self.store) == self.original_rows
            result = {
                "manifest_sha256": receipt["manifest_sha256"],
                "source_store": str(self.original_store),
                "restored_store": str(self.store),
                "original_worker_returncode": self.first["child"].poll(),
                "original_http_returncode": self.http["child"].poll(),
                "restored_rows_equal": True,
                "automatic_original_writer_fencing": verified["recovery_snapshot"][
                    "original_writers_fenced"
                ],
            }
            self.proof["operator_backup_restore"] = result
        elif command == "resume_ready":
            assert self.fresh is None and self.first["child"].poll() == -signal.SIGKILL
            self.fresh = self.spawn("worker", "--name", "fresh")
            result = self.read(self.fresh)
            assert result["pid"] != self.first["child"].pid
            assert (
                result["checkpoint_hash"]
                == self.proof["first_checkpoint"]["checkpoint_hash"]
            )
            assert result["progress"] == 1
            assert result["actual_calls"] == {"analysis": 0, "verification": 0}
            self.proof["restored_before_numerical_calls"] = result
        elif command == "complete":
            assert self.fresh is not None and self.fresh["child"].poll() is None
            self.fresh["child"].stdin.write("continue\n")
            self.fresh["child"].stdin.flush()
            result = self.read(self.fresh)
            assert self.fresh["child"].wait(timeout=90) == 0
            self.proof["completed_worker"] = result
            self.proof["durable_completion"] = self.inspect_job(result["job"]["job_id"])
        elif command == "begin_prices":
            assert self.before_prices is None and self.fresh["child"].poll() == 0
            self.inspect_job(message["job_id"])
            assert self.reports(message["job_id"]) == []
            self.prices_job_id = message["job_id"]
            self.before_prices = numerical_rows(self.store)
            result = {
                "numerical_state_hash": digest(canonical(self.before_prices)),
                "reports": [],
            }
        elif command == "verify_prices":
            assert (
                self.before_prices is not None
                and message["job_id"] == self.prices_job_id
            )
            assert numerical_rows(self.store) == self.before_prices
            assert not any(
                (root / "http-numerical-attempts.jsonl").exists()
                for root in (self.workspace, self.runtime_workspace)
            )
            if self.original_store is not None:
                assert numerical_rows(self.original_store) == self.original_rows
            reports = self.reports(message["job_id"])
            assert [report["revision"] for report in reports] == [1, 2]
            if self.reports_before_restart is not None:
                assert reports == self.reports_before_restart
            self.reports_before_restart = reports
            result = {
                "reports": reports,
                "numerical_state_unchanged": True,
                "http_numerical_calls": 0,
                "original_store_unchanged": True
                if self.original_store is not None
                else None,
                "numerical_state_hash": digest(canonical(self.before_prices)),
            }
            self.proof["price_only_evidence"] = result
        elif command == "inspect_report":
            assert message["job_id"] == self.prices_job_id
            current = service(self.store)
            raw = current.read_rc_quantity_report(
                message["job_id"], message["report_id"], **tenant()
            )
            result = {
                "base64": base64.b64encode(raw).decode("ascii"),
                "sha256": digest(raw),
                "bytes": len(raw),
            }
        elif command == "stop":
            self.close()
            result = {
                "reaped": all(row["child"].poll() is not None for row in self.processes)
            }
        else:
            raise ValueError(f"unsupported stdin command: {command}")
        self.proof["commands"].append(command)
        self.save_proof()
        return result

    def close(self):
        for record in reversed(self.processes):
            self.stop(record)
        self.save_proof()


def run_driver(workspace):
    current = Supervisor(workspace)
    emit(
        {
            "ready": True,
            "request": authored_request(),
            "explicit_layers_request": authored_explicit_layers_request(),
            "pin_roller_layers_request": authored_pin_roller_layers_request(),
            "credentials": {"tenantId": "a", "bearerToken": TENANTS["a"]},
            "other_credentials": {"tenantId": "b", "bearerToken": TENANTS["b"]},
            "proof": current.proof,
        }
    )
    try:
        with forbid_numerical_calls(workspace):
            for line in sys.stdin:
                message = json.loads(line)
                try:
                    result = current.command(message)
                    emit({"id": message["id"], "ok": True, "result": result})
                except Exception as error:
                    traceback.print_exc(file=sys.stderr)
                    emit(
                        {
                            "id": message["id"],
                            "ok": False,
                            "error": f"{type(error).__name__}: {error}",
                        }
                    )
                    return 1
                if message["command"] == "stop":
                    break
    finally:
        current.close()
    return 0


def valid_workspace(workspace, mode):
    """Keep all child runtimes inside the driver's disposable temporary root."""
    workspace = workspace.resolve()
    root = workspace
    if mode != "driver" and workspace.name == "recovered-runtime":
        root = workspace.parent
    return (
        root.parent == Path(tempfile.gettempdir()).resolve()
        and root.name.startswith("structural-rc-browser-")
        and workspace.is_dir()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("driver", "http", "worker"))
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--name", choices=tuple(WORKERS))
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    if not valid_workspace(workspace, args.mode):
        parser.error(
            "an existing disposable /tmp/structural-rc-browser-* directory is required"
        )
    if args.mode == "driver":
        if any(workspace.iterdir()):
            parser.error("driver requires an empty workspace")
        return run_driver(workspace)
    if args.mode == "http":
        serve(workspace, args.port)
    else:
        if args.name is None:
            parser.error("worker mode requires --name")
        run_worker(workspace, args.name)
    return 0


def stop(signum, frame):
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    raise SystemExit(main())
