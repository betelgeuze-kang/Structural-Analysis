"""Logical retained-payload bounds using real I/O and synthetic contract seams.

These tests establish storage/orchestration behavior, not solver or hardware truth.
"""

from dataclasses import replace
import errno
import hashlib
import sqlite3

import pytest

from structural_analysis.execution import job_service as implementation
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.rc_result_repository import RCResultRepository
from tests.test_rc_fiber_job_service import (
    Clock,
    OTHER,
    TENANT,
    WORKER,
    WORKER_B,
    admission_state_snapshot,
    canonical,
    claim,
    lease,
    outcome,
    prepare_synthetic_prefix_pending,
    record,
    request,
    request_blob_inventory,
    reserve,
    save_synthetic_checkpoint,
    service,
    sha,
    submit,
    synthetic_admission_artifacts,
    tenant,
)


def capped(root, limit, clock=None):
    return DurableJobService(
        root,
        tenant_tokens={"a": TENANT, "b": OTHER},
        worker_tokens={"worker-a": WORKER, "worker-b": WORKER_B},
        worker_tenants={"worker-a": {"a"}, "worker-b": {"a", "b"}},
        clock=clock,
        max_blob_payload_bytes=limit,
    )


def used(root):
    return sum(len(raw) for raw in request_blob_inventory(root).values())


def sql_state(root):
    with sqlite3.connect(root / "jobs.sqlite3") as connection:
        return {
            name: connection.execute(f"SELECT * FROM {name} ORDER BY rowid").fetchall()
            for name in ("jobs", "job_events", "job_execution_budgets")
        }


def retained(root, payload):
    """An actual orphan file, never an invented inventory amount."""
    digest = hashlib.sha256(payload).hexdigest()
    path = root / "blobs" / "sha256" / digest[:2] / digest
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.mark.parametrize("remaining", [0, -1])
def test_exact_request_cap_and_one_byte_over_store_no_denied_state(tmp_path, remaining):
    raw = canonical(request())
    s = capped(tmp_path, len(raw) + remaining)
    before = sql_state(tmp_path)
    if remaining == 0:
        submitted = submit(s)
        assert used(tmp_path) == len(raw)
        assert next(iter(request_blob_inventory(tmp_path).values())) == raw
        assert submit(s) == submitted
        assert used(tmp_path) == len(raw)
    else:
        with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
            submit(s)
        assert sql_state(tmp_path) == before
        assert request_blob_inventory(tmp_path) == {}


def test_real_orphan_dedup_and_exact_retry_work_above_cap(tmp_path):
    s = service(tmp_path)
    raw = canonical(request())
    path = retained(tmp_path, raw)
    other = retained(tmp_path, b"unreferenced retained bytes")
    before = request_blob_inventory(tmp_path)
    capped(tmp_path, 1)
    j = submit(s)  # An instance opened before adoption reads the persisted policy.
    assert submit(capped(tmp_path, None)) == j
    assert request_blob_inventory(tmp_path) == before
    assert path.stat().st_size == len(raw) and other.stat().st_size > 0


def test_corrupt_dedup_rejected_above_cap_without_repair(tmp_path):
    s = service(tmp_path)
    path = retained(tmp_path, canonical(request()))
    path.write_bytes(b"corrupt")
    capped(tmp_path, 1)
    before = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="artifact_integrity_failed"):
        submit(s)
    assert request_blob_inventory(tmp_path) == before
    assert sql_state(tmp_path)["jobs"] == []


@pytest.mark.parametrize("cap_offset", [0, -1])
def test_existing_request_missing_repair_is_charged(tmp_path, cap_offset):
    s = service(tmp_path)
    j = submit(s)
    raw = canonical(request())
    path = s._blob_path(j.request.content_hash)
    path.unlink()  # Controlled test fault: the existing retry permits repair.
    capped(tmp_path, len(raw) + cap_offset)
    before = sql_state(tmp_path)
    if cap_offset == 0:
        assert submit(s) == j
        assert path.read_bytes() == raw
    else:
        with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
            submit(s)
        assert not path.exists()
    assert sql_state(tmp_path) == before


@pytest.mark.parametrize("role", ["checkpoint", "outcome"])
def test_role_growth_denial_preserves_state_and_reserved_work(
    tmp_path, monkeypatch, role
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    if role == "checkpoint":
        payload, *_ = synthetic_admission_artifacts(s, c, monkeypatch)
    else:
        ordinal = reserve(s, c)
        value = outcome(c)
        payload = canonical(value)
    capped(tmp_path, used(tmp_path) + len(payload) - 1)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        if role == "checkpoint":
            save_synthetic_checkpoint(s, c, payload)
        else:
            record(s, c, ordinal, value)
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs


@pytest.mark.parametrize("fits", [False, True])
def test_completion_union_includes_evidence_before_first_write(
    tmp_path, monkeypatch, fits
):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    _, _, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    evidence_raw = canonical(proof)
    limit = used(tmp_path) + len(raw) + (len(evidence_raw) if fits else 0)
    capped(tmp_path, limit)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)

    def complete():
        return s.complete_job(
            c.job.job_id,
            **lease(c),
            result_bytes=raw,
            result_media_type="application/json",
            evidence=proof,
        )

    if fits:
        completed = complete()
        assert completed.status == "succeeded"
        assert used(tmp_path) == limit
        assert s.read_result(c.job.job_id, **tenant()) == raw
    else:
        with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
            complete()
        assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
        assert request_blob_inventory(tmp_path) == blobs


def test_real_evidence_fsync_failure_orphan_consumes_next_growth(tmp_path, monkeypatch):
    s = service(tmp_path)
    submit(s)
    c = claim(s)
    prefix, _, _, raw, _, proof = prepare_synthetic_prefix_pending(s, c, monkeypatch)
    initial = used(tmp_path)
    capacity = initial + len(raw) + len(canonical(proof))
    capped(tmp_path, capacity)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    put = s._put_blob

    def fail_evidence(value, **kwargs):
        if kwargs["role"] == "evidence":

            def no_space(_fd):
                raise OSError(errno.ENOSPC, "injected file fsync boundary")

            with monkeypatch.context() as isolated:
                isolated.setattr(implementation.os, "fsync", no_space)
                return put(value, **kwargs)
        return put(value, **kwargs)

    with monkeypatch.context() as isolated:
        isolated.setattr(s, "_put_blob", fail_evidence)
        with pytest.raises(JobServiceError, match="artifact_write_failed"):
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    reopened = capped(tmp_path, None)
    assert admission_state_snapshot(reopened, tmp_path, c.job.job_id) == before
    assert reopened.read_checkpoint(c.job.job_id, **tenant()) == prefix
    after = request_blob_inventory(tmp_path)
    assert [value for path, value in after.items() if path not in blobs] == [raw]
    orphan = reopened._blob_path(sha(raw))
    assert orphan.read_bytes() == raw and orphan.stat().st_size == len(raw)
    assert not list((tmp_path / "blobs").rglob(".job-blob-*"))
    # A new schema-valid request is larger than the remaining evidence allowance.
    value = request()
    value["case_id"] = "new-after-orphan"
    new_raw = canonical(value)
    assert initial + len(new_raw) <= capacity < used(tmp_path) + len(new_raw)
    with pytest.raises(JobServiceError, match="blob_payload_budget_exceeded"):
        submit(reopened, value, "new-after-orphan")
    assert request_blob_inventory(tmp_path) == after
    assert admission_state_snapshot(reopened, tmp_path, c.job.job_id) == before


@pytest.mark.parametrize("role", ["checkpoint", "result", "evidence"])
def test_admitted_real_write_expiry_rolls_back_authority_but_retains_payload(
    tmp_path, monkeypatch, role
):
    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    prefix, checkpoint, _, raw, _, proof = prepare_synthetic_prefix_pending(
        s, c, monkeypatch
    )
    growth = (
        len(checkpoint) if role == "checkpoint" else len(raw) + len(canonical(proof))
    )
    capped(tmp_path, used(tmp_path) + growth, clock)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    put = s._put_blob

    def expire_after_real_write(value, **kwargs):
        ref = put(value, **kwargs)
        if kwargs["role"] == role:
            clock.advance()
        return ref

    monkeypatch.setattr(s, "_put_blob", expire_after_real_write)
    with pytest.raises(JobServiceError, match="lease_expired"):
        if role == "checkpoint":
            save_synthetic_checkpoint(s, c, checkpoint, progress=2)
        else:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert s.read_checkpoint(c.job.job_id, **tenant()) == prefix
    added = [
        value
        for path, value in request_blob_inventory(tmp_path).items()
        if path not in blobs
    ]
    assert sorted(added) == sorted(
        [checkpoint]
        if role == "checkpoint"
        else [raw]
        if role == "result"
        else [raw, canonical(proof)]
    )
    assert before["invocations"]["pending_ordinals"] == [3]
    successor = claim(capped(tmp_path, None, clock), worker="worker-b")
    assert successor.checkpoint_bytes == prefix
    assert successor.job.progress_completed == 1


@pytest.mark.parametrize("operation", ["checkpoint", "completion"])
def test_slow_real_dedup_read_precedes_fresh_lease_gate(
    tmp_path, monkeypatch, operation
):
    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    checkpoint, _, raw, _, proof = synthetic_admission_artifacts(s, c, monkeypatch)
    retained(tmp_path, checkpoint if operation == "checkpoint" else raw)
    capped(tmp_path, used(tmp_path) + len(canonical(proof)), clock)
    target = sha(checkpoint if operation == "checkpoint" else raw)
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    read = s._read_blob

    def expire_after_read(digest, *args, **kwargs):
        result = read(digest, *args, **kwargs)
        if digest == target:
            clock.advance()
        return result

    monkeypatch.setattr(s, "_read_blob", expire_after_read)
    with pytest.raises(JobServiceError, match="lease_expired"):
        if operation == "checkpoint":
            save_synthetic_checkpoint(s, c, checkpoint)
        else:
            s.complete_job(
                c.job.job_id,
                **lease(c),
                result_bytes=raw,
                result_media_type="application/json",
                evidence=proof,
            )
    assert request_blob_inventory(tmp_path) == blobs
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before


def test_central_guard_rejects_unbound_unplanned_foreign_and_retired_plans(tmp_path):
    s = capped(tmp_path / "one", 30)
    other = capped(tmp_path / "two", 30)
    payload = b"planned"

    def put(owner, raw, **kwargs):
        return owner._put_blob(
            raw,
            role="evidence",
            media_type="application/json",
            maximum_bytes=30,
            **kwargs,
        )

    with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
        put(s, payload)
    with s._transaction() as connection:
        plan = s._admit_blob_payloads(connection, (payload,))
        with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
            put(s, b"unplanned", admission=plan)
        with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
            put(other, payload, admission=plan)
        with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
            put(s, payload, admission=replace(plan))
        # Replacement prevents two independently preflighted unwritten groups
        # from holding simultaneous capacity reservations in one transaction.
        new_plan = s._admit_blob_payloads(connection, (b"replacement",))
        with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
            put(s, payload, admission=plan)
        put(s, b"replacement", admission=new_plan)
    with pytest.raises(JobServiceError, match="blob_payload_admission_required"):
        put(s, b"replacement", admission=new_plan)
    assert list(request_blob_inventory(s.root).values()) == [b"replacement"]
    assert request_blob_inventory(other.root) == {}


def snapshot(artifacts=(("first", b"original"), ("second", b"original"))):
    """An explicitly synthetic, sealed transport snapshot; no physics is run."""
    from structural_analysis.benchmark.rc_control_reuse import _Snapshot

    key = sha(b"synthetic-transport-key")
    row = {
        "status": "verified",
        "full_reference_verification_pass": True,
        "synthetic_transport_only": True,
        "invocations": [],
        "artifacts": {
            name: {"sha256": sha(raw), "byte_length": len(raw)}
            for name, raw in artifacts
        },
    }
    raw = canonical(row)
    seal = sha(
        canonical(
            {
                "key": key,
                "row_hash": sha(raw),
                "artifacts": [
                    (name, sha(value), len(value)) for name, value in artifacts
                ],
            }
        )
    )
    result = _Snapshot(key, raw, tuple(artifacts), seal)
    result.check()
    return result


def repository(s):
    return RCResultRepository(
        s, tenant_id="a", authorization_token=TENANT, scope_id="synthetic-transport"
    )


def manifest_bytes(entry):
    def ref(raw):
        return {"hash": sha(raw), "size": len(raw)}

    return canonical(
        {
            "schema": "persistent-rc-original.v1",
            "key": entry.key,
            "tenant": "a",
            "scope": "synthetic-transport",
            "row": ref(entry.row_bytes),
            "artifacts": {name: ref(raw) for name, raw in entry.artifacts},
            "seal": entry.seal,
            "size": entry.byte_length,
        }
    )


@pytest.mark.parametrize("fits", [False, True])
def test_repository_union_deduplicates_roles_and_counts_manifest(tmp_path, fits):
    s = service(tmp_path)
    repo = repository(s)
    entry = snapshot()
    manifest = manifest_bytes(entry)
    distinct = {
        sha(raw): raw
        for raw in (entry.row_bytes, *(raw for _, raw in entry.artifacts), manifest)
    }
    total = sum(len(raw) for raw in distinct.values())
    cap = total if fits else total - len(manifest)
    capped(tmp_path, cap)
    assert repo._publish(entry, repo.scope_id) is fits
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        rows = db.execute("SELECT * FROM rc_verified_result_index_v1").fetchall()
    if fits:
        assert used(tmp_path) == total == cap
        assert len(request_blob_inventory(tmp_path)) == 3
        assert (
            rows[0][-1] == entry.byte_length
        )  # Referenced cap still counts both roles.
        assert repo._publish(entry, repo.scope_id)
        assert repo._load(entry.key, repo.scope_id) == entry
    else:
        assert rows == [] and request_blob_inventory(tmp_path) == {}


def test_repository_unsafe_inventory_is_error_and_keeps_source_bytes(tmp_path):
    s = capped(tmp_path, 4096)
    repo = repository(s)
    bad = tmp_path / "blobs" / "sha256" / "unexpected"
    bad.write_bytes(b"preserve")
    with pytest.raises(JobServiceError, match="blob_payload_inventory_invalid"):
        repo._publish(snapshot(), repo.scope_id)
    assert bad.read_bytes() == b"preserve"
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        assert db.execute("SELECT * FROM rc_verified_result_index_v1").fetchall() == []


@pytest.mark.parametrize(
    "artifacts",
    [
        (("bad-role", b"original"),),
        (("same", b"original"), ("same", b"original")),
        tuple((f"role_{index}", b"original") for index in range(17)),
    ],
)
def test_repository_invalid_roles_fail_before_cap_and_writes(tmp_path, artifacts):
    s = capped(tmp_path, 1)
    repo = repository(s)
    entry = snapshot(artifacts)
    with pytest.raises(ValueError, match="invalid persistent artifact roles"):
        repo._publish(entry, repo.scope_id)
    assert request_blob_inventory(tmp_path) == {}
    with sqlite3.connect(tmp_path / "jobs.sqlite3") as db:
        assert db.execute("SELECT * FROM rc_verified_result_index_v1").fetchall() == []


@pytest.mark.parametrize("race", ["capacity", "dedup_expiry", "postwrite_expiry"])
def test_diagnostic_growth_respects_cap_and_fresh_lease(tmp_path, monkeypatch, race):
    from structural_analysis.execution import nonlinear_failure_diagnostic as diagnostic

    clock = Clock()
    s = service(tmp_path, clock)
    submit(s)
    c = claim(s)
    raw = canonical({"synthetic_diagnostic_storage_only": True})
    monkeypatch.setattr(
        diagnostic,
        "build_nonlinear_job_failure_diagnostic",
        lambda *args, **kwargs: raw,
    )
    if race == "dedup_expiry":
        retained(tmp_path, raw)
    capped(
        tmp_path,
        used(tmp_path) + (len(raw) - 1 if race == "capacity" else len(raw)),
        clock,
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    if race == "dedup_expiry":
        read = s._read_blob

        def expire_after_dedup(digest, *args, **kwargs):
            result = read(digest, *args, **kwargs)
            if digest == sha(raw):
                clock.advance()
            return result

        monkeypatch.setattr(s, "_read_blob", expire_after_dedup)
    elif race == "postwrite_expiry":
        put = s._put_blob

        def expire_after_storage(value, **kwargs):
            result = put(value, **kwargs)
            clock.advance()
            return result

        monkeypatch.setattr(s, "_put_blob", expire_after_storage)
    with pytest.raises(
        JobServiceError,
        match="blob_payload_budget_exceeded" if race == "capacity" else "lease_expired",
    ):
        s.fail_job(
            c.job.job_id,
            **lease(c),
            error_code="synthetic_failure",
            nonlinear_failure_result_bytes=b"synthetic-input",
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    after = request_blob_inventory(tmp_path)
    if race == "postwrite_expiry":
        assert [value for path, value in after.items() if path not in blobs] == [raw]
    else:
        assert after == blobs


def test_inventory_traversal_error_fails_closed_without_writes(tmp_path, monkeypatch):
    s = capped(tmp_path, 4096)
    before = sql_state(tmp_path)
    scan = implementation.os.scandir

    def denied(path):
        if path == s._blob_root:
            raise PermissionError("injected denied directory traversal")
        return scan(path)

    with monkeypatch.context() as isolated:
        isolated.setattr(implementation.os, "scandir", denied)
        with pytest.raises(JobServiceError, match="blob_payload_inventory_invalid"):
            submit(s)
    assert sql_state(tmp_path) == before
    assert request_blob_inventory(tmp_path) == {}


def test_diagnostic_individual_size_error_precedes_root_capacity(tmp_path, monkeypatch):
    from structural_analysis.execution import nonlinear_failure_diagnostic as diagnostic

    s = service(tmp_path)
    submit(s)
    c = claim(s)
    capped(tmp_path, 1)
    monkeypatch.setattr(diagnostic, "MAX_DIAGNOSTIC_BYTES", 8)
    monkeypatch.setattr(
        diagnostic,
        "build_nonlinear_job_failure_diagnostic",
        lambda *args, **kwargs: b"ninebytes",
    )
    before = admission_state_snapshot(s, tmp_path, c.job.job_id)
    blobs = request_blob_inventory(tmp_path)
    with pytest.raises(JobServiceError, match="artifact_size_out_of_bounds"):
        s.fail_job(
            c.job.job_id,
            **lease(c),
            error_code="synthetic_failure",
            nonlinear_failure_result_bytes=b"synthetic-input",
        )
    assert admission_state_snapshot(s, tmp_path, c.job.job_id) == before
    assert request_blob_inventory(tmp_path) == blobs
