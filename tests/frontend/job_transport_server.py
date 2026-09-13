"""Disposable loopback test mount: built Workbench plus the real durable WSGI API.

All tokens are synthetic test data. The default fixture runs no solver.
The explicit --nonlinear-failure option executes one real blocked planar solve;
its adversarial browser payloads never overwrite the durable source artifacts.
This is a test fixture, not an application listener or deployment prescription.
"""

from __future__ import annotations

import json
import mimetypes
import signal
import sys
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


def main(*, nonlinear_failure=False):
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
        # Exercise an actual durable failure transition without executing a solver.
        claim = service.claim_next(
            worker_id="worker", authorization_token="synthetic-worker-not-launched"
        )
        assert claim is not None
        failed_job = service.fail_job(
            claim.job.job_id,
            worker_id="worker",
            authorization_token="synthetic-worker-not-launched",
            lease_token=claim.lease_token,
            error_code="synthetic_transport_failure",
        )
        mutants = {}
        if nonlinear_failure:
            import base64
            import hashlib
            from structural_analysis.engine_v2.contracts._canonical import (
                canonical_hash,
                canonical_json_bytes,
            )
            from structural_analysis.execution.nonlinear_frame_worker import (
                execute_nonlinear_frame_claim,
                NonlinearFrameWorkerError,
            )

            model = json.loads(
                (root / "examples/planar_frame_rc_portal.json").read_bytes()
            )
            for pattern in model["load_patterns"]:
                for load in pattern["nodal_loads"]:
                    for key in load["components_si"]:
                        load["components_si"][key] *= 40
            model["provenance"]["source_sha256"] = canonical_hash(
                {key: value for key, value in model.items() if key != "provenance"}
            )
            actual = service.submit_job(
                tenant_id="transport-test",
                authorization_token="synthetic-memory-only-token",
                idempotency_key="actual-nonlinear-failure",
                request={
                    "schema_version": "structural-analysis-job-request.v1",
                    "operation": "nonlinear_frame",
                    "case_id": "actual-planar-failure",
                    "model": model,
                    "config": {
                        "profile": "corotational_connected_frame2d.v1",
                        "load_steps": 4,
                        "residual_tolerance": 1e-10,
                        "increment_tolerance_m": 1e-12,
                        "maximum_iterations": 40,
                        "matrix_backend": "numpy_linalg_solve_dense",
                        "control_mode": "load_control",
                    },
                    "result_contract": "unified-nonlinear-frame-result.v1",
                },
            )
            actual_claim = service.claim_next(
                worker_id="worker", authorization_token="synthetic-worker-not-launched"
            )
            assert actual_claim is not None and actual_claim.job.job_id == actual.job_id
            try:
                execute_nonlinear_frame_claim(
                    service,
                    actual_claim,
                    worker_id="worker",
                    authorization_token="synthetic-worker-not-launched",
                )
            except NonlinearFrameWorkerError as exc:
                assert exc.code == "worker_result_contract_blocked"
            else:
                raise AssertionError("Expected actual nonlinear failure")
            failed_job = service.get_job(
                actual.job_id,
                tenant_id="transport-test",
                authorization_token="synthetic-memory-only-token",
            )
            diagnostic = service.read_failure_diagnostic(
                actual.job_id,
                attempt=1,
                tenant_id="transport-test",
                authorization_token="synthetic-memory-only-token",
            )
            # Coherently rehashed adversarial transport, never written to the service.
            for kind in (
                "wrong_total",
                "float_count",
                "unknown_work",
                "rollback_false",
            ):
                envelope = json.loads(diagnostic)
                source = json.loads(base64.b64decode(envelope["result_bytes_base64"]))
                path = source["metrics"]["observed_load_path"]
                if kind == "wrong_total":
                    path["convergence_history_row_count"] += 1
                elif kind == "float_count":
                    path["attempted_step_count"] = float(path["attempted_step_count"])
                elif kind == "unknown_work":
                    source["metrics"]["observed_load_path"] = None
                else:
                    path["steps"][-1]["failed_step_rollback_exact"] = False
                source.pop("result_hash")
                source["result_hash"] = canonical_hash(source)
                raw = canonical_json_bytes(source)
                envelope.update(
                    result_bytes_base64=base64.b64encode(raw).decode(),
                    result_byte_length=len(raw),
                    result_artifact_hash="sha256:" + hashlib.sha256(raw).hexdigest(),
                    source_result_hash=source["result_hash"],
                )
                mutants[kind] = json.dumps(envelope)
        job = service.submit_job(
            tenant_id="transport-test",
            authorization_token="synthetic-memory-only-token",
            idempotency_key="browser-queued-transport-fixture",
            request=json.loads(claim.request_bytes),
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
                        "failed_job": failed_job.to_dict(),
                        "mutants": mutants,
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
        main(nonlinear_failure="--nonlinear-failure" in sys.argv)
