"""Disposable loopback test mount: built Workbench plus the real durable WSGI API.

All tokens are synthetic test data. No worker is launched and no solve runs.
This is a test fixture, not an application listener or deployment prescription.
"""

from __future__ import annotations

import json
import mimetypes
import signal
from pathlib import Path
import tempfile
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.execution.job_http_api import DurableJobWSGIApplication
from structural_analysis.execution.job_service import DurableJobService


def forbidden(*args, **kwargs):
    raise AssertionError("The transport fixture must execute zero numerical calls")


def stop(signum, frame):
    raise SystemExit(0)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    root = Path(__file__).resolve().parents[2]
    dist = root / "dist"
    with tempfile.TemporaryDirectory(prefix="structural-job-browser-") as temporary:
        service = DurableJobService(
            temporary,
            tenant_tokens={
                "transport-test": "synthetic-memory-only-token",
                "other-tenant": "synthetic-other-tenant-token",
            },
            worker_tokens={"worker": "synthetic-worker-not-launched"},
        )
        job = service.submit_job(
            tenant_id="transport-test",
            authorization_token="synthetic-memory-only-token",
            idempotency_key="browser-transport-fixture",
            request={
                "schema_version": "structural-analysis-job-request.v3",
                "operation": "bounded_rc_fiber_direct_control",
                "case_id": "browser-transport-only",
                "source_revision": "b" * 40,
                "model": json.loads(
                    (
                        root
                        / "examples/public_rc_fiber_frame_l_frame_material_history.json"
                    ).read_bytes()
                ),
                "config": BoundedRCFiberDirectControlRequest(
                    7, (-0.0001, -0.0002, -0.0003)
                ).to_dict(),
                "result_contract": "bounded-rc-fiber-job-result.v1",
                "execution_config": {
                    "chunk_target_count": 1,
                    "maximum_api_invocations": 6,
                },
            },
        )
        api = DurableJobWSGIApplication(service)

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

        with make_server(
            "127.0.0.1", 0, application, handler_class=QuietHandler
        ) as server:
            print(
                json.dumps(
                    {
                        "origin": f"http://127.0.0.1:{server.server_port}",
                        "job": job.to_dict(),
                    }
                ),
                flush=True,
            )
            server.serve_forever()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    with patch(
        "structural_analysis.api.rc_fiber_frame_direct_control."
        "run_stateful_fiber_frame2d_control_path",
        forbidden,
    ):
        main()
