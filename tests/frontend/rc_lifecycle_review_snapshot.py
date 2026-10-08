"""Generate fresh genuine RC artifacts for socket-free cross-language review.

This companion exercises the HTTP adapter in-process, never opens a listener,
and does not claim browser/hosted evidence. Its output is computed on demand by
actual worker processes; no completed artifact is checked into the repository.
"""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path
import tempfile

from structural_analysis.execution.job_http_api import DurableJobHttpApi

from rc_lifecycle_http_fixture import (
    Supervisor,
    TENANTS,
    authored_request,
    canonical,
    digest,
    emit,
    forbid_numerical_calls,
    original_bytes,
    service,
    tenant,
)


def snapshot(output, request_bytes=None):
    with tempfile.TemporaryDirectory(prefix="structural-rc-browser-") as directory:
        workspace = Path(directory)
        supervisor = Supervisor(workspace)
        current = service(supervisor.store)
        api = DurableJobHttpApi(current)
        headers = {
            "X-Structural-Tenant": "a",
            "Authorization": f"Bearer {TENANTS['a']}",
        }
        try:
            submitted = api.handle(
                "POST",
                "/v1/jobs",
                headers={
                    **headers,
                    "Idempotency-Key": "generated-review-snapshot",
                },
                body=request_bytes
                if request_bytes is not None
                else canonical(authored_request()),
            )
            assert submitted.status == 202
            job_id = json.loads(submitted.body)["job_id"]
            # Persist the submitted numeric representation, not decoder defaults.
            submitted_values = (
                json.loads(request_bytes)
                if request_bytes is not None
                else authored_request()
            )
            expected_request_bytes = canonical(submitted_values)
            assert current.read_request(job_id, **tenant()) == expected_request_bytes
            assert json.loads(submitted.body)["request"]["content_hash"] == digest(
                expected_request_bytes
            )

            supervisor.command({"command": "first_checkpoint"})
            supervisor.command({"command": "kill_first"})
            supervisor.command({"command": "resume_ready"})
            supervisor.command({"command": "complete"})
            supervisor.command({"command": "begin_prices", "job_id": job_id})
            job = current.get_job(job_id, **tenant())
            with forbid_numerical_calls(workspace):
                for concrete in (120.0, 150.0):
                    response = api.handle(
                        "POST",
                        f"/v1/jobs/{job_id}/rc-quantity-reports",
                        headers=headers,
                        body=canonical(
                            {
                                "expected_request_hash": job.request.content_hash,
                                "expected_result_artifact_hash": job.result.content_hash,
                                "declared_prices": {
                                    "concrete_per_m3": concrete,
                                    "rebar_per_kg": 2.0,
                                    "currency": "USD",
                                    "as_of": "2026-10-07",
                                    "source": "generated cross-language review test declaration",
                                },
                            }
                        ),
                    )
                    assert response.status == 200, response.body
                reports = supervisor.command(
                    {"command": "verify_prices", "job_id": job_id}
                )["reports"]

                def encoded(raw):
                    return {
                        "base64": base64.b64encode(raw).decode("ascii"),
                        "bytes": len(raw),
                        "sha256": digest(raw),
                    }

                packet = {
                    "schema_version": "generated-rc-review-snapshot.v1",
                    "evidence_scope": "socket-free real worker process and adapter regression; not browser or hosted proof",
                    "tenant_id": "a",
                    "original_request_representation_retained": True,
                    "job": job.to_dict(),
                    "artifacts": {
                        role: encoded(original_bytes(current, getattr(job, role)))
                        for role in ("request", "checkpoint", "result", "evidence")
                    },
                    "reports": [
                        {
                            "reference": reference,
                            **encoded(
                                current.read_rc_quantity_report(
                                    job_id, reference["report_id"], **tenant()
                                )
                            ),
                        }
                        for reference in reports
                    ],
                }
        finally:
            supervisor.close()
        packet["proof"] = supervisor.proof
        output.write_bytes(canonical(packet))
        return {
            "path": str(output),
            "sha256": digest(output.read_bytes()),
            "job_id": job_id,
            "bytes": output.stat().st_size,
            "report_revisions": [reference["revision"] for reference in reports],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--request-file", type=Path)
    arguments = parser.parse_args()
    emit(
        snapshot(
            arguments.output,
            arguments.request_file.read_bytes() if arguments.request_file else None,
        )
    )
