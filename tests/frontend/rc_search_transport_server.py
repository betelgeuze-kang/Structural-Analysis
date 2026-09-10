"""Disposable real loopback mount for the built Workbench and RC search API.

Credentials are synthetic. The actual WSGI artifact application serves immutable
snapshots; browser requests are never intercepted or fulfilled by Playwright.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
from pathlib import Path
import resource
import signal
import time
from unittest.mock import patch
from wsgiref.simple_server import WSGIRequestHandler, make_server

from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    RcSearchArtifactWSGIApplication,
)


def forbidden(*args, **kwargs):
    raise AssertionError("transport-only observation cannot execute numerical work")


def stop(signum, frame):
    raise SystemExit(0)


class QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    dist = root / "dist"
    before = time.perf_counter_ns()
    cpu = time.process_time_ns()
    snapshot_root = root / "tests/frontend/fixtures/rc-control-search"
    expected = json.loads((snapshot_root / "result.json").read_bytes())["report_hash"]
    bundle = RcSearchArtifactBundle.from_directory(
        snapshot_root, expected_report_hash=expected
    )
    load_ns = time.perf_counter_ns() - before
    creds = {
        "transport-test": "synthetic-search-memory-token",
        "other-tenant": "synthetic-other-search-token",
    }

    def authorize(tenant, token):
        expected = creds.get(tenant)
        return expected is not None and hmac.compare_digest(expected, token)

    api = RcSearchArtifactWSGIApplication(
        {("transport-test", "regression"): bundle}, authorize=authorize
    )
    records = []

    def application(environ, start_response):
        path = environ["PATH_INFO"]
        if path.startswith("/v1/"):
            response_status = []

            def record_start(status, headers):
                response_status.append(status)
                start_response(status, headers)

            chunks = list(api(environ, record_start))
            body = b"".join(chunks)
            records.append(
                {
                    "method": environ["REQUEST_METHOD"],
                    "path": path,
                    "status": int(response_status[0].split()[0]),
                    "bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                }
            )
            return chunks
        target = (dist / path.lstrip("/")).resolve()
        if not target.is_relative_to(dist) or target.suffix not in {
            "",
            ".html",
            ".js",
            ".css",
            ".json",
            ".svg",
            ".png",
            ".jpg",
            ".ico",
            ".woff",
            ".woff2",
        }:
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not found"]
        if not target.is_file():
            target = dist / "index.html"
        body = target.read_bytes()
        start_response(
            "200 OK",
            [
                (
                    "Content-Type",
                    mimetypes.guess_type(target)[0] or "application/octet-stream",
                ),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    try:
        with make_server(
            "127.0.0.1", 0, application, handler_class=QuietHandler
        ) as server:
            print(
                json.dumps(
                    {
                        "origin": f"http://127.0.0.1:{server.server_port}",
                        "pid": os.getpid(),
                        "report_hash": expected,
                        "artifact_count": len(bundle.artifacts),
                        "snapshot_bytes": sum(map(len, bundle.artifacts.values())),
                    }
                ),
                flush=True,
            )
            server.serve_forever()
    finally:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        with args.receipt.open("x") as f:
            json.dump(
                {
                    "schema_version": "rc-search-real-http-browser-observation.v1",
                    "pid": os.getpid(),
                    "report_hash": expected,
                    "snapshot_artifact_count": len(bundle.artifacts),
                    "snapshot_bytes": sum(map(len, bundle.artifacts.values())),
                    "snapshot_load_ns": load_ns,
                    "wall_ns": time.perf_counter_ns() - before,
                    "cpu_ns": time.process_time_ns() - cpu,
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "requests": records,
                    "new_solver_calls": 0,
                    "new_fits": 0,
                    "independent_physical_validation": False,
                },
                f,
                indent=2,
            )


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    with (
        patch(
            "structural_analysis.api.rc_fiber_frame_direct_control.run_stateful_fiber_frame2d_control_path",
            forbidden,
        ),
        patch(
            "structural_analysis.benchmark.rc_control_candidate_learning.train_rc_control_candidate_policy",
            forbidden,
        ),
    ):
        main()
