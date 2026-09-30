"""Actual tiny RC full/chunk regression under an inherited payload policy.

These are authored software examples with mandatory fresh solver verification,
not experiment labels, independent physical validation or performance evidence.
"""

import hashlib
import json

from structural_analysis.api import rc_fiber_frame_direct_control as api
from structural_analysis.execution import job_worker
from structural_analysis.execution.job_service import DurableJobService
from tests.test_rc_fiber_durable_worker import (
    Clock,
    TARGETS,
    TENANT_AUTH,
    WORKER_AUTH,
    _bytes,
    _claim,
    _evidence,
    _native,
    _request,
    _submit,
)


def test_opted_in_full_and_reopened_chunks_preserve_fresh_verified_state(
    tmp_path, monkeypatch
):
    cap = 64 * 1024 * 1024
    calls = {"analysis": 0, "verification": 0}
    analyze = api.analyze_bounded_rc_fiber_direct_control
    verify = api.validate_bounded_rc_fiber_direct_control_artifacts

    def observed_analysis(*args, **kwargs):
        calls["analysis"] += 1
        return analyze(*args, **kwargs)

    def observed_verification(*args, **kwargs):
        calls["verification"] += 1
        return verify(*args, **kwargs)

    monkeypatch.setattr(
        api, "analyze_bounded_rc_fiber_direct_control", observed_analysis
    )
    monkeypatch.setattr(
        api, "validate_bounded_rc_fiber_direct_control_artifacts", observed_verification
    )

    def service(root, configured=False):
        options = {"max_blob_payload_bytes": cap} if configured else {}
        return DurableJobService(
            root,
            tenant_tokens={"tenant": TENANT_AUTH["authorization_token"]},
            worker_tokens={"worker": WORKER_AUTH["authorization_token"]},
            worker_tenants={"worker": {"tenant"}},
            clock=Clock(),
            **options,
        )

    arms = {}
    attempted_targets = 0
    for name, chunk, count in (("full", len(TARGETS), 1), ("split", 1, len(TARGETS))):
        root = tmp_path / name
        current = service(root, configured=True)
        submitted = _submit(current, _request(chunk_size=chunk))
        for index in range(count):
            # Omission must inherit the persisted root policy after every reopen.
            current = service(root)
            claim = _claim(current)
            assert claim.job.job_id == submitted.job_id
            if index:
                assert claim.checkpoint_bytes is not None
                saved = json.loads(claim.checkpoint_bytes)
                assert saved["completed_target_count"] == index
            job = job_worker.execute_job_claim(current, claim, **WORKER_AUTH)
            assert job.progress_completed == min((index + 1) * chunk, len(TARGETS))
            assert job.status == ("succeeded" if index + 1 == count else "checkpointed")
            assert current.validate_integrity(job.job_id, **TENANT_AUTH)[
                "contract_pass"
            ]
        result = json.loads(current.read_result(submitted.job_id, **TENANT_AUTH))
        evidence = _evidence(current, submitted.job_id, **TENANT_AUTH)
        assert evidence["pending_ordinals"] == []
        assert len(evidence["records"]) == 2 * count
        for receipt in result["receipts"]:
            assert (
                receipt["validation_report"]["fresh_source_execution_invoked"] is True
            )
            assert receipt["validation_report"]["physical_path_complete"] is True
            attempted_targets += receipt["analysis_metrics"]["control_work"][
                "attempted_step_count"
            ]
            attempted_targets += receipt["verification_metrics"]["replay_control_work"][
                "attempted_step_count"
            ]
        payload_bytes = 0
        for path in (root / "blobs" / "sha256").rglob("*"):
            if not path.is_file():
                continue
            raw = path.read_bytes()
            assert path.name == hashlib.sha256(raw).hexdigest()
            assert path.stat().st_size == len(raw)
            payload_bytes += len(raw)
        assert 0 < payload_bytes <= cap
        assert not list((root / "blobs").rglob(".job-blob-*"))
        arms[name] = result
        (tmp_path / f"{name}-result.json").write_bytes(_bytes(result))
        (tmp_path / f"{name}-evidence.json").write_bytes(_bytes(evidence))

    assert calls == {"analysis": 4, "verification": 4}
    assert attempted_targets == 18
    assert _native(arms["full"]) == _native(arms["split"])
    for field in (
        "response_history",
        "terminal_response",
        "checkpoint",
        "model",
        "claims",
    ):
        assert _bytes(arms["full"]["api_result"][field]) == _bytes(
            arms["split"]["api_result"][field]
        )
