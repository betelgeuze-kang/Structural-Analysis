"""Actual tiny managed corotational workflow snapshot for browser review tests.

The authored example is software workflow evidence, never a measured specimen.
Only explicitly spawned worker processes perform numerical work. Saved-report
reads forbid numerical APIs, replay and current source fingerprint computation.
"""

from __future__ import annotations

import argparse
import base64
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import select
import signal
import sqlite3
import subprocess
import sys
from unittest.mock import patch

from structural_analysis.api.strict_json import strict_json_object_bytes

from structural_analysis.execution.job_execution_authority import JobExecutionAuthority
from structural_analysis.execution.job_http_api import DurableJobHttpApi
from structural_analysis.execution.job_managed_restore import activate_managed_restore
from structural_analysis.execution.job_service import JobServiceError
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)
from structural_analysis.execution.job_worker import execute_job_claim
from structural_analysis.execution.rc_corotational_job_request import (
    rc_corotational_job_canonical_bytes,
)

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_rc_corotational_managed_restore import helpers, service  # noqa: E402


LIMIT = 10_000_000
TABLES = ("jobs", "job_events", "job_execution_budgets", "job_rc_invocation_outcomes")


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def authored_request(profile="v7", *, linear_observation=False):
    payload = helpers.request()
    # Tiny positive/negative control demonstrates signed load-factor export;
    # the settings and fixed load come from the existing stable tiny fixture.
    payload["config"]["targets_m"] = [-1e-6, -2e-6, 1e-6]
    payload["execution_config"].update(
        attempt_limit_per_call=2, maximum_api_invocations=6
    )
    if linear_observation:
        payload["config"].pop("control_node_id")
        payload["config"].pop("control_component")
        payload["config"]["control_observation"] = {
            "schema_version": "linear-physical-displacement-observation.v1",
            "terms": [
                {"node_id": "N3", "component": "UY", "coefficient": 1.0},
                {"node_id": "N1", "component": "UY", "coefficient": -1.0},
                {"node_id": "N1", "component": "RZ", "coefficient": -0.5},
                {"node_id": "N3", "component": "RZ", "coefficient": 0.2},
            ],
        }
    if profile == "v7":
        payload["schema_version"] = "structural-analysis-job-request.v7"
        payload["execution_config"]["phase_execution_policy"] = {
            "schema_version": "bounded-rc-corotational-phase-execution-policy.v1",
            "analysis_timeout_ms": 60_000,
            "verification_timeout_ms": 60_000,
            "termination_grace_ms": 500,
        }
    return payload


def numerical_state(store):
    with sqlite3.connect(Path(store) / "jobs.sqlite3") as connection:
        return sha(
            rc_corotational_job_canonical_bytes(
                {
                    table: [
                        list(row)
                        for row in connection.execute(
                            f"SELECT * FROM {table} ORDER BY 1,2"
                        )
                    ]
                    for table in TABLES
                }
            )
        )


def forbid_report_execution(*args, **kwargs):
    raise RuntimeError("saved report attempted numerical or current source execution")


def read_without_execution(current, job, *, detail=False):
    with ExitStack() as stack:
        for name in (
            "structural_analysis.api.rc_corotational_control.analyze_rc_corotational_control",
            "structural_analysis.api.rc_corotational_control.validate_rc_corotational_control_artifacts",
            "structural_analysis.api.rc_corotational_control.solve_stateful_corotational_fiber_frame2d_load_step",
            "structural_analysis.api.rc_corotational_control.run_corotational_control_subdivision",
            "structural_analysis.api.rc_corotational_control._source_identity",
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision._source_identity",
            "structural_analysis.assembly.stateful_corotational_fiber_frame2d_control_subdivision.solve_stateful_corotational_fiber_frame2d_displacement_control_step",
        ):
            stack.enter_context(patch(name, forbid_report_execution))
        return DurableJobHttpApi(current).handle(
            "GET",
            f"/v1/jobs/{job.job_id}/rc-corotational-{'detail-report' if detail else 'report'}",
            headers={
                "X-Structural-Tenant": helpers.TENANT["tenant_id"],
                "Authorization": "Bearer " + helpers.TENANT["authorization_token"],
                "X-Structural-Expected-Request-Hash": job.request.content_hash,
                "X-Structural-Expected-Result-Hash": job.result.content_hash,
                "X-Structural-Expected-Evidence-Hash": job.evidence.content_hash,
            },
        )


def worker_process(store, identity, *, hold=False):
    command = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
        "worker",
        "--store",
        str(store),
        "--identity",
        identity,
    ]
    if hold:
        command.append("--hold")
    return subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=ROOT,
    )


def read_ready(process):
    if not select.select([process.stdout], [], [], 120)[0]:
        raise RuntimeError("tiny numerical worker did not reach its bounded barrier")
    line = process.stdout.readline()
    if not line:
        raise RuntimeError(
            "tiny numerical worker failed: " + process.stderr.read()[:2000]
        )
    return json.loads(line)


def stop_owned(process):
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
    assert not Path(f"/proc/{process.pid}").exists()


def generate_snapshot(
    workspace: Path,
    profile="v7",
    submitted_bytes: bytes | None = None,
    *,
    linear_observation=False,
):
    """Compute, terminate, restore and reopen one real tiny managed job."""
    payload = (
        authored_request(profile, linear_observation=linear_observation)
        if submitted_bytes is None
        else strict_json_object_bytes(submitted_bytes)
    )
    if payload != authored_request(profile, linear_observation=linear_observation):
        raise ValueError(
            "snapshot fixture accepts only its authored tiny request values"
        )
    submitted_bytes = submitted_bytes or rc_corotational_job_canonical_bytes(payload)
    workspace.mkdir(parents=True, exist_ok=False)
    source, backup, restored = (
        workspace / name for name in ("source", "backup", "restored")
    )
    authority, binding = JobExecutionAuthority.create(workspace / "authority", source)
    current = service(source, execution_authority=authority, execution_binding=binding)
    job = current.submit_job(
        **helpers.TENANT, idempotency_key="actual-corotational-report", request=payload
    )
    assert (
        current.submit_job(
            **helpers.TENANT,
            idempotency_key="actual-corotational-report",
            request=payload,
        ).job_id
        == job.job_id
    )
    first = worker_process(source, "worker", hold=True)
    try:
        saved = read_ready(first)
        assert (
            saved["status"] == "checkpointed"
            and saved["progress"]["completed_steps"] == 2
        )
        retained_checkpoint = current.read_checkpoint(job.job_id, **helpers.TENANT)
        receipt = backup_job_store(source, backup, maximum_bytes=LIMIT)
        options = {
            "manifest_sha256": receipt["manifest_sha256"],
            "maximum_bytes": LIMIT,
        }
        live = current.claim_next(**helpers.SECOND, lease_seconds=300)
        assert live is not None
        credentials = dict(helpers.SECOND, lease_token=live.lease_token)
        assert current.reserve_execution_attempt(job.job_id, **credentials) == 3
        stop_owned(first)
        assert first.returncode == -signal.SIGKILL
        restore_job_store(backup, restored, **options)
        activation = activate_managed_restore(backup, restored, **options)
        assert activation["generation"] == 2
        try:
            current.heartbeat(job.job_id, **credentials)
        except JobServiceError as error:
            assert error.code == "execution_authority_rejected"
        else:
            raise AssertionError("retired root retained execution authority")
        fresh = service(restored)
        assert (
            fresh.read_checkpoint(job.job_id, **helpers.TENANT) == retained_checkpoint
        )
        second = worker_process(restored, "second")
        try:
            completed_view = read_ready(second)
            second.wait(timeout=120)
            assert second.returncode == 0
            assert not Path(f"/proc/{second.pid}").exists()
        finally:
            if second.poll() is None:
                stop_owned(second)
        assert completed_view["status"] == "succeeded"
        completed = fresh.get_job(job.job_id, **helpers.TENANT)
        assert (completed.progress_completed, completed.progress_total) == (3, 255)
        assert fresh.read_request(
            job.job_id, **helpers.TENANT
        ) == current_request_bytes(payload)
        before = numerical_state(restored)
        response = read_without_execution(fresh, completed)
        assert response.status == 200, response.body.decode()
        detail_response = read_without_execution(fresh, completed, detail=True)
        assert detail_response.status == 200, detail_response.body.decode()
        reopened = service(restored)
        repeated = read_without_execution(reopened, completed)
        assert repeated.status == 200 and repeated.body == response.body
        assert repeated.headers == response.headers
        repeated_detail = read_without_execution(reopened, completed, detail=True)
        assert repeated_detail.status == 200
        assert repeated_detail.body == detail_response.body
        assert repeated_detail.headers == detail_response.headers
        assert numerical_state(restored) == before
        report = json.loads(response.body)
        detail_report = json.loads(detail_response.body)
        assert detail_report["nodal_report_hash"] == report["report_hash"]
        assert detail_report["bindings"] == report["bindings"]
        assert report["execution"]["budget"] == {
            "maximum_attempts": 6,
            "reserved_attempts": 5,
            "remaining_attempts": 1,
        }
        assert report["execution"]["pending_ordinals"] == [3]
        assert report["execution"]["unknown_execution_work"] is True
        originals = {
            "request": reopened.read_request(job.job_id, **helpers.TENANT),
            "checkpoint": reopened.read_checkpoint(job.job_id, **helpers.TENANT),
            "result": reopened.read_result(job.job_id, **helpers.TENANT),
            "evidence": reopened.read_evidence(job.job_id, **helpers.TENANT),
        }
        for role, raw in originals.items():
            assert sha(raw) == completed_view[role]["content_hash"]
        assert response.headers["x-structural-report-sha256"] == sha(response.body)
        assert (
            response.headers["x-structural-report-id"]
            == "rcc_" + sha(response.body)[7:]
        )
        assert detail_response.headers["x-structural-report-sha256"] == sha(
            detail_response.body
        )
        assert (
            detail_response.headers["x-structural-report-id"]
            == "rcd_" + sha(detail_response.body)[7:]
        )
        child_observations = [
            row["phase_supervision"]["supervisor"]
            for row in report["execution"]["invocations"]
            if row["phase_supervision"] is not None
        ]
        for observation in child_observations:
            assert observation["direct_child_reaped"] is True
            assert observation["child_returncode"] == 0
            assert not Path(f"/proc/{observation['child_pid']}").exists()
        return {
            "schema_version": "rc-corotational-review-snapshot.v1",
            "profile": profile,
            "tenant_id": helpers.TENANT["tenant_id"],
            "job": completed_view,
            "request": json.loads(originals["request"]),
            "submitted_request_base64": base64.b64encode(submitted_bytes).decode(
                "ascii"
            ),
            "artifacts": {
                role: base64.b64encode(raw).decode("ascii")
                for role, raw in originals.items()
            },
            "report": {
                "status": response.status,
                "headers": dict(response.headers),
                "body_base64": base64.b64encode(response.body).decode("ascii"),
            },
            "detail_report": {
                "status": detail_response.status,
                "headers": dict(detail_response.headers),
                "body_base64": base64.b64encode(detail_response.body).decode("ascii"),
            },
            "proof": {
                "claim_boundary": "actual tiny authored example workflow only; no measured specimen, independent physical validation, design approval or release qualification",
                "checkout_sha": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                ).strip(),
                "source_revision_caller_declaration": payload["source_revision"],
                "recorded_package_source_identity": report["bindings"][
                    "recorded_source_identity"
                ],
                "submitted_raw_sha256": sha(submitted_bytes),
                "original_artifact_hashes": {
                    role: sha(raw) for role, raw in originals.items()
                },
                "backup_manifest_sha256": receipt["manifest_sha256"],
                "activated_generation": activation["generation"],
                "restored_checkpoint_byte_identical": True,
                "retired_source_rejected": True,
                "first_worker": {
                    "pid": first.pid,
                    "returncode": first.returncode,
                    "reaped": True,
                },
                "fresh_worker": {
                    "pid": second.pid,
                    "returncode": second.returncode,
                    "reaped": True,
                },
                "numerical_children": child_observations,
                "numerical_state_before_report_sha256": before,
                "numerical_state_after_report_sha256": numerical_state(restored),
                "report_reads_numerical_invocations": 0,
                "report_reads_source_fingerprint_invocations": 0,
                "reopened_report_byte_identical": True,
                "reopened_detail_report_byte_identical": True,
                "independent_physical_validation": False,
                "design_authority": False,
                "release_approved": False,
            },
        }
    finally:
        if first.poll() is None:
            stop_owned(first)


def current_request_bytes(payload):
    return rc_corotational_job_canonical_bytes(payload)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", nargs="?", choices=["snapshot", "worker"], default="snapshot"
    )
    parser.add_argument(
        "--output", "--output-path", "--outputpath", dest="output", type=Path
    )
    parser.add_argument("--profile", choices=["v6", "v7"], default="v7")
    parser.add_argument("--request-file", type=Path)
    parser.add_argument("--linear-observation", action="store_true")
    parser.add_argument("--store", type=Path)
    parser.add_argument("--identity", choices=["worker", "second"])
    parser.add_argument("--hold", action="store_true")
    args = parser.parse_args()
    if args.mode == "worker":
        current = service(args.store)
        identity = helpers.WORKER if args.identity == "worker" else helpers.SECOND
        claim = current.claim_next(**identity, lease_seconds=300)
        assert claim is not None
        view = execute_job_claim(current, claim, **identity)
        print(json.dumps(view.to_dict(), sort_keys=True, allow_nan=False), flush=True)
        if args.hold:
            sys.stdin.read(1)
        return
    if args.output is None:
        parser.error("--output is required for an explicitly retained snapshot")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(
            "snapshot output already exists; retain the previous receipt"
        )
    snapshot = generate_snapshot(
        args.output.with_suffix(".workflow"),
        args.profile,
        args.request_file.read_bytes() if args.request_file else None,
        linear_observation=args.linear_observation,
    )
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "snapshot": str(args.output.resolve()),
                "profile": args.profile,
                "report_id": snapshot["report"]["headers"]["x-structural-report-id"],
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
