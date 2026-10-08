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


def secant_trace_snapshot(output):
    """Fresh numerical trace projection for the narrow trial auditor only.

    This intentionally is not a complete API result or a publishable job artifact.
    """
    from structural_analysis.api.nonlinear_fiber_frame import _compile
    from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
        run_stateful_fiber_frame2d_control_path,
    )
    from structural_analysis.assembly.stateful_fiber_frame2d_displacement_control import (
        StatefulFiberFrame2DDisplacementControlConfig,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes
    from structural_analysis.solvers.nonlinear.newton import NewtonRaphsonConfig

    root = Path(__file__).resolve().parents[2]
    model = load_neutral_json_bytes(
        (root / "tests/fixtures/rc_mathern_nominal_uncalibrated.json").read_bytes()
    )
    compiled, blockers, _ = _compile(model, experimental_pin_roller_beam=True)
    assert compiled is not None and not blockers
    config = StatefulFiberFrame2DDisplacementControlConfig(
        initial_trial_policy="accepted_then_prescribed_then_secant",
        newton=NewtonRaphsonConfig(
            max_iterations=100, line_search_alphas=tuple(2.0**-i for i in range(16))
        ),
    )
    targets = (
        (-1e-5, -0.0001, -0.00025, -0.0005)
        + tuple(-i / 2000 for i in range(2, 51))
        + tuple(-i / 400 for i in range(9, -1, -1))
        + (0.0025,)
    )
    result = run_stateful_fiber_frame2d_control_path(
        compiled.problem,
        targets,
        control_global_dof=10,
        config=config,
        allow_reversals=True,
        maximum_reversals=2,
    )
    assert result.status == "ready"
    path = result.to_dict()
    assert len(path["attempts"][-1]["step"]["initial_trial_search"]["trials"]) == 3
    attempts = []
    for row in path["attempts"]:
        step = row["step"]
        parent = step["parent_checkpoint"]
        attempts.append(
            {
                key: row[key]
                for key in (
                    "committed",
                    "parent_checkpoint_hash",
                    "target_control_displacement_m",
                    "solver_work",
                )
            }
            | {
                "step": {
                    "committed": step["committed"],
                    "metrics": {"config": step["metrics"]["config"]},
                    "parent_checkpoint": {
                        key: parent[key]
                        for key in (
                            "state_hash",
                            "parent_state_hash",
                            "global_displacements",
                        )
                    },
                    "initial_trial_search": step["initial_trial_search"],
                    "trial_solution": step["trial_solution"],
                }
            }
        )
    packet = {
        "scope": "trial-audit projection; not a complete product artifact",
        "config": {
            "solver_config": {"initial_trial_policy": config.initial_trial_policy},
            "control_global_dof": 10,
        },
        "api": {
            "request": {"configuration": config.to_manifest()},
            "path": {
                "attempts": attempts,
                "replay_attempts": path["replay_attempts"],
                "metrics": path["metrics"],
            },
            "metrics": {"control_work": path["metrics"]["total_work"]},
        },
    }
    output.write_bytes(canonical(packet))
    return {
        "path": str(output),
        "bytes": output.stat().st_size,
        "scope": packet["scope"],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--secant-trace", action="store_true")
    arguments = parser.parse_args()
    if arguments.secant_trace:
        if arguments.request_file is not None:
            parser.error("secant trace does not accept a request override")
        emit(secant_trace_snapshot(arguments.output))
        raise SystemExit(0)
    emit(
        snapshot(
            arguments.output,
            arguments.request_file.read_bytes() if arguments.request_file else None,
        )
    )
