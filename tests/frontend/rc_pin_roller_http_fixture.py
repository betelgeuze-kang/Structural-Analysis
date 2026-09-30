"""Disposable real HTTP/RC fixture; serve never executes a numerical routine.

Only the explicit worker mode may dispatch one actual no-preload RC chunk.
All credentials are synthetic, listeners are loopback, and stores are fresh /tmp
test directories. This harness is software evidence, not a service launcher.
"""

from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import gzip
import hashlib
import json
import mimetypes
from pathlib import Path
import signal
import subprocess
import tempfile
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from structural_analysis.api import rc_fiber_frame_direct_control as rc_api
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.assembly import stateful_fiber_frame2d_control_path as paths
from structural_analysis.execution.job_http_api import DurableJobWSGIApplication
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.job_worker import execute_job_claim

TENANT = "rc-live-test"
TOKEN = "synthetic-rc-live-tenant-token"
WORKER = "rc-live-worker"
WORKER_TOKEN = "synthetic-rc-live-worker-token"


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def service(store):
    return DurableJobService(
        store,
        tenant_tokens={TENANT: TOKEN, "other-tenant": "synthetic-other-tenant-token"},
        worker_tokens={WORKER: WORKER_TOKEN},
        worker_tenants={WORKER: {TENANT}},
    )


def prepared_requests(root, store):
    packet = json.loads(
        gzip.decompress(
            (
                root / "tests/frontend/fixtures/rc-pin-roller-design-artifacts.json.gz"
            ).read_bytes()
        )
    )
    row = packet["files"]["no-preload/baseline/model.json"]
    raw = base64.b64decode(row["base64"], validate=True)
    assert len(raw) == row["bytes"]
    assert hashlib.sha256(raw).hexdigest() == row["sha256"]
    source = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    request = {
        "schema_version": "structural-analysis-job-request.v3",
        "operation": "bounded_rc_fiber_direct_control",
        "case_id": "actual-http-pin-roller-two-chunks",
        "source_revision": source,  # Caller declaration, not hardware attestation.
        "model": json.loads(raw),
        "config": BoundedRCFiberDirectControlRequest(
            10, (-1e-6, -2e-6), experimental_pin_roller_beam=True
        ).to_dict(),
        "result_contract": "bounded-rc-fiber-job-result.v1",
        "execution_config": {"chunk_target_count": 1, "maximum_api_invocations": 4},
    }
    full = deepcopy(request)
    full["case_id"] = "actual-http-pin-roller-full-reference"
    full["execution_config"] = {"chunk_target_count": 2, "maximum_api_invocations": 2}
    conflict = deepcopy(request)
    conflict["case_id"] = "different-immutable-request"
    preload = deepcopy(request)
    preload["config"] = BoundedRCFiberDirectControlRequest(
        10,
        (-1e-6, -2e-6),
        experimental_pin_roller_beam=True,
        constant_nodal_loads=(("N4", 0.0, -0.01, 0.0),),
    ).to_dict()
    preload["result_contract"] = "bounded-rc-fiber-job-result.v2"
    wrong_profile = deepcopy(request)
    wrong_profile["config"] = BoundedRCFiberDirectControlRequest(
        10, (-1e-6, -2e-6), experimental_two_fixed_endpoints=True
    ).to_dict()
    result = {}
    for name, value in {
        "request": request,
        "full": full,
        "conflict": conflict,
        "preload": preload,
        "wrong-profile": wrong_profile,
    }.items():
        path = store / f"{name}.json"
        body = canonical(value)
        if path.exists():
            assert path.read_bytes() == body, (
                "restart must preserve original request bytes"
            )
        else:
            path.write_bytes(body)
        result[name] = {
            "path": str(path),
            "bytes": len(body),
            "sha256": "sha256:" + hashlib.sha256(body).hexdigest(),
        }
    return result


def forbidden(*args, **kwargs):
    raise AssertionError("The HTTP process must execute zero numerical calls")


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def serve(root, store):
    originals = prepared_requests(root, store)
    api = DurableJobWSGIApplication(service(store))
    dist = root / "dist"

    def application(environ, start_response):
        path = environ["PATH_INFO"]
        if path.startswith("/v1/"):
            return api(environ, start_response)
        target = (dist / path.lstrip("/")).resolve()
        if not target.is_relative_to(dist):
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        if not target.is_file():
            target = dist / "index.html"
        body = target.read_bytes()
        start_response(
            "200 OK",
            [
                ("Content-Type", mimetypes.guess_type(target)[0] or "text/plain"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    with patch.object(rc_api, "run_stateful_fiber_frame2d_control_path", forbidden):
        with make_server(
            "127.0.0.1", 0, application, handler_class=QuietHandler
        ) as server:
            print(
                json.dumps(
                    {
                        "origin": f"http://127.0.0.1:{server.server_port}",
                        "originals": originals,
                    }
                ),
                flush=True,
            )
            server.serve_forever()


def run_worker(root, store):
    prepared = prepared_requests(root, store)
    admitted = {
        Path(prepared[name]["path"]).read_bytes() for name in ("request", "full")
    }
    # Observational call-throughs preserve the production functions and all args.
    counts = {
        "analysis": 0,
        "verification": 0,
        "core_targets": 0,
        "core_by_phase": {"analysis": 0, "verification": 0},
    }
    phase = ["analysis"]
    originals = {
        "analysis": rc_api.analyze_bounded_rc_fiber_direct_control,
        "verification": rc_api.validate_bounded_rc_fiber_direct_control_artifacts,
        "core": paths.solve_stateful_fiber_frame2d_displacement_control_step,
    }

    def analyze(*args, **kwargs):
        if phase[0] == "analysis":
            counts["analysis"] += 1
        return originals["analysis"](*args, **kwargs)

    def verify(*args, **kwargs):
        counts["verification"] += 1
        previous = phase[0]
        phase[0] = "verification"
        try:
            return originals["verification"](*args, **kwargs)
        finally:
            phase[0] = previous

    def core(*args, **kwargs):
        counts["core_targets"] += 1
        counts["core_by_phase"][phase[0]] += 1
        return originals["core"](*args, **kwargs)

    actual_service = service(store)
    claim = actual_service.claim_next(
        worker_id=WORKER, authorization_token=WORKER_TOKEN, lease_seconds=300
    )
    assert claim is not None
    assert claim.request_bytes in admitted, (
        "explicit worker opt-in permits only the prepared tiny v4 pin/roller requests"
    )
    with (
        patch.object(rc_api, "analyze_bounded_rc_fiber_direct_control", analyze),
        patch.object(
            rc_api, "validate_bounded_rc_fiber_direct_control_artifacts", verify
        ),
        patch.object(
            paths, "solve_stateful_fiber_frame2d_displacement_control_step", core
        ),
    ):
        job = execute_job_claim(
            actual_service, claim, worker_id=WORKER, authorization_token=WORKER_TOKEN
        )
    print(json.dumps({"job": job.to_dict(), "actual_calls": counts}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("serve", "worker"))
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--execute-rc-pin-roller", action="store_true")
    args = parser.parse_args()
    store = args.store.resolve()
    if not store.is_relative_to(
        Path(tempfile.gettempdir()).resolve()
    ) or not store.name.startswith("structural-rc-live-http-"):
        parser.error("a disposable structural-rc-live-http-* /tmp store is required")
    if args.execute_rc_pin_roller != (args.mode == "worker"):
        parser.error("only worker mode requires --execute-rc-pin-roller")
    store.mkdir(exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    if args.mode == "serve":
        serve(root, store)
    else:
        run_worker(root, store)


def stop(signum, frame):
    raise SystemExit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    main()
