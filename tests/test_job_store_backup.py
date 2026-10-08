"""Fresh queued-job storage only: no worker, solver, or historical fixture run."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.job_store_backup import (
    backup_job_store,
    restore_job_store,
)

TOKEN = "test-backup-tenant-token-0123456789"
LIMIT = 10 * 1024 * 1024


def service(root):
    return DurableJobService(
        root,
        tenant_tokens={"tenant": TOKEN},
        worker_tokens={"worker": "test-worker-backup-0123456789"},
    )


@pytest.fixture
def store(tmp_path):
    original = service(tmp_path / "source")
    request = {
        "schema_version": "structural-analysis-job-request.v1",
        "operation": "nonlinear_frame",
        "case_id": "backup-queued-only",
        "model": json.loads(
            (
                Path(__file__).resolve().parents[1]
                / "examples/public_corotational_rc_portal.json"
            ).read_text()
        ),
        "config": {
            "profile": "corotational_one_bay_portal.v1",
            "load_steps": 4,
            "residual_tolerance": 1e-10,
            "increment_tolerance_m": 1e-12,
            "maximum_iterations": 40,
            "matrix_backend": "scipy_sparse_spsolve_cpu",
            "control_mode": "load_control",
        },
        "result_contract": "unified-nonlinear-frame-result.v1",
    }
    job = original.submit_job(
        tenant_id="tenant",
        authorization_token=TOKEN,
        idempotency_key="new-backup-test",
        request=request,
    )
    return original, job


def saved(store, tmp_path):
    original, _ = store
    receipt = backup_job_store(original.root, tmp_path / "backup", maximum_bytes=LIMIT)
    return tmp_path / "backup", receipt


def test_backup_restore_reopens_same_queued_job_and_integrity(store, tmp_path):
    original, job = store
    (original.root / "operator-note.txt").write_text("not part of backup")
    before = original.validate_integrity(
        job.job_id, tenant_id="tenant", authorization_token=TOKEN
    )
    source, receipt = saved(store, tmp_path)
    assert not (source / "operator-note.txt").exists()
    result = restore_job_store(
        source,
        tmp_path / "restored",
        manifest_sha256=receipt["manifest_sha256"],
        maximum_bytes=LIMIT,
    )
    restored = service(tmp_path / "restored")
    assert (
        restored.get_job(
            job.job_id, tenant_id="tenant", authorization_token=TOKEN
        ).to_dict()
        == job.to_dict()
    )
    assert (
        restored.validate_integrity(
            job.job_id, tenant_id="tenant", authorization_token=TOKEN
        )
        == before
    )
    assert (
        original.validate_integrity(
            job.job_id, tenant_id="tenant", authorization_token=TOKEN
        )
        == before
    )
    assert (
        result["application_integrity_checked"] is False
    )  # API receipt itself makes no solver claim.


def test_busy_writer_refuses_without_destination(store, tmp_path):
    with closing(
        sqlite3.connect(store[0].root / "jobs.sqlite3", isolation_level=None)
    ) as writer:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError):
            saved(store, tmp_path)
        assert not (tmp_path / "backup").exists()
        writer.rollback()


def test_committed_wal_data_is_in_database_snapshot(store, tmp_path):
    # Keep a WAL reader open so close/checkpoint cannot turn this into a main-file copy test.
    with closing(sqlite3.connect(store[0].root / "jobs.sqlite3")) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT COUNT(*) FROM jobs").fetchone()
        with closing(sqlite3.connect(store[0].root / "jobs.sqlite3")) as writer:
            writer.execute("UPDATE jobs SET progress_completed=1")
            writer.commit()
        assert (store[0].root / "jobs.sqlite3-wal").stat().st_size > 0
        source, _ = saved(store, tmp_path)
        with closing(sqlite3.connect(source / "jobs.sqlite3")) as restored:
            assert restored.execute(
                "SELECT progress_completed FROM jobs"
            ).fetchone() == (1,)


@pytest.mark.parametrize("kind", ["changed", "missing", "symlink"])
def test_source_blob_corruption_never_produces_manifest(store, tmp_path, kind):
    blob = next((store[0].root / "blobs/sha256").glob("*/*"))
    if kind == "changed":
        blob.write_bytes(b"changed")
    elif kind == "missing":
        blob.unlink()
    else:
        blob.unlink()
        blob.symlink_to(tmp_path / "missing-target")
    with pytest.raises((ValueError, OSError)):
        saved(store, tmp_path)
    assert not (tmp_path / "backup/backup-manifest.json").exists()


def test_backup_payload_bound_prevents_complete_manifest(store, tmp_path):
    with pytest.raises(ValueError):
        backup_job_store(store[0].root, tmp_path / "backup", maximum_bytes=1)
    assert not (tmp_path / "backup/backup-manifest.json").exists()


def test_restore_rejects_changed_blob(store, tmp_path):
    source, receipt = saved(store, tmp_path)
    blob = next((source / "blobs/sha256").glob("*/*"))
    blob.write_bytes(b"tampered")
    with pytest.raises(ValueError):
        restore_job_store(
            source,
            tmp_path / "restored",
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )


def test_manifest_digest_cannot_be_replaced_with_payloads(store, tmp_path):
    source, receipt = saved(store, tmp_path)
    path = source / "backup-manifest.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="manifest digest"):
        restore_job_store(
            source,
            tmp_path / "restored",
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )
    assert not (tmp_path / "restored").exists()


def test_even_trusted_manifest_cannot_escape_destination(store, tmp_path):
    source, _ = saved(store, tmp_path)
    path = source / "backup-manifest.json"
    value = json.loads(path.read_bytes())
    value["files"]["../outside"] = {
        "bytes": 0,
        "sha256": hashlib.sha256(b"").hexdigest(),
    }
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="member path"):
        restore_job_store(
            source,
            tmp_path / "restored",
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            maximum_bytes=LIMIT,
        )
    assert not (tmp_path / "restored").exists()


def test_existing_destination_is_preserved(store, tmp_path):
    target = tmp_path / "backup"
    target.mkdir()
    (target / "keep").write_text("keep")
    with pytest.raises(ValueError):
        saved(store, tmp_path)
    assert (target / "keep").read_text() == "keep"


def test_historical_event_reference_must_exist(store, tmp_path):
    with closing(sqlite3.connect(store[0].root / "jobs.sqlite3")) as db:
        db.execute(
            "UPDATE job_events SET payload_json=?",
            (
                json.dumps(
                    {
                        "checkpoint": {
                            "content_hash": "sha256:" + "a" * 64,
                            "byte_length": 3,
                        }
                    }
                ),
            ),
        )
        db.commit()
    with pytest.raises(ValueError, match="reference missing"):
        saved(store, tmp_path)
    assert not (tmp_path / "backup/backup-manifest.json").exists()


def test_duplicate_manifest_keys_rejected_even_with_matching_digest(store, tmp_path):
    source, _ = saved(store, tmp_path)
    path = source / "backup-manifest.json"
    raw = path.read_bytes().replace(
        b'{"application_integrity_checked":false,',
        b'{"application_integrity_checked":true,"application_integrity_checked":false,',
    )
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="duplicate"):
        restore_job_store(
            source,
            tmp_path / "restored",
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            maximum_bytes=LIMIT,
        )
    assert not (tmp_path / "restored").exists()


def test_restored_job_reopens_in_a_separate_process(store, tmp_path):
    import subprocess
    import sys

    source, receipt = saved(store, tmp_path)
    target = tmp_path / "restored"
    restore_job_store(
        source, target, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=LIMIT
    )
    code = """import json,sys
from structural_analysis.execution.job_service import DurableJobService
v=json.load(sys.stdin)
s=DurableJobService(v['root'],tenant_tokens={'tenant':'test-backup-tenant-token-0123456789'},worker_tokens={'worker':'test-worker-backup-0123456789'})
a={'tenant_id':'tenant','authorization_token':'test-backup-tenant-token-0123456789'}
print(json.dumps({'view':s.get_job(v['job'],**a).to_dict(),'integrity':s.validate_integrity(v['job'],**a)},sort_keys=True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps({"root": str(target), "job": store[1].job_id}),
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    value = json.loads(result.stdout)
    assert value["view"] == store[1].to_dict()
    assert value["integrity"] == store[0].validate_integrity(
        store[1].job_id, tenant_id="tenant", authorization_token=TOKEN
    )


def test_manifest_cannot_rebind_a_content_address_to_other_bytes(store, tmp_path):
    source, _ = saved(store, tmp_path)
    path = source / "backup-manifest.json"
    value = json.loads(path.read_bytes())
    name = next(name for name in value["files"] if name.startswith("blobs/"))
    changed = b"other bytes"
    (source / name).write_bytes(changed)
    value["files"][name] = {
        "bytes": len(changed),
        "sha256": hashlib.sha256(changed).hexdigest(),
    }
    raw = json.dumps(value).encode()
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="content address"):
        restore_job_store(
            source,
            tmp_path / "restored",
            manifest_sha256=hashlib.sha256(raw).hexdigest(),
            maximum_bytes=LIMIT,
        )
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize(
    "marker",
    [".job-store-backup.pending", ".job-store-restore.pending", "backup-manifest.json"],
)
def test_service_refuses_incomplete_or_sealed_store_before_database_changes(
    store, marker
):
    from structural_analysis.execution.job_service import JobServiceError

    root = store[0].root
    before = (root / "jobs.sqlite3").read_bytes()
    (root / marker).write_text("reserved marker")
    with pytest.raises(JobServiceError) as error:
        service(root)
    assert error.value.code == "job_store_not_activated"
    assert (root / "jobs.sqlite3").read_bytes() == before


def test_dangling_pending_marker_also_blocks_service(store):
    from structural_analysis.execution.job_service import JobServiceError

    (store[0].root / ".job-store-restore.pending").symlink_to("missing")
    with pytest.raises(JobServiceError):
        service(store[0].root)


def test_failed_restore_stays_quarantined(store, tmp_path):
    from structural_analysis.execution.job_service import JobServiceError

    source, receipt = saved(store, tmp_path)
    blob = next((source / "blobs/sha256").glob("*/*"))
    blob.write_bytes(b"changed")
    target = tmp_path / "restored"
    with pytest.raises(ValueError):
        restore_job_store(
            source,
            target,
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )
    assert (target / ".job-store-restore.pending").exists()
    with pytest.raises(JobServiceError):
        service(target)


def test_cli_backup_restore_produces_receipt_without_starting_service(
    store, tmp_path, capsys
):
    from structural_analysis.execution.job_store_backup_cli import main

    backup = tmp_path / "backup"
    target = tmp_path / "restored"
    assert (
        main(["backup", str(store[0].root), str(backup), "--maximum-bytes", str(LIMIT)])
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    assert first["service_started"] is False
    assert (
        main(
            [
                "restore",
                str(backup),
                str(target),
                "--maximum-bytes",
                str(LIMIT),
                "--manifest-sha256",
                first["manifest_sha256"],
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["service_started"] is False
    assert not (target / ".job-store-restore.pending").exists()
    receipt = json.loads((target / "restore-receipt.json").read_text())
    assert receipt["manifest_sha256"] == first["manifest_sha256"]
    assert (
        service(target)
        .get_job(store[1].job_id, tenant_id="tenant", authorization_token=TOKEN)
        .to_dict()
        == store[1].to_dict()
    )


def test_cli_failure_does_not_print_underlying_exception(capsys, monkeypatch):
    from structural_analysis.execution import job_store_backup_cli as cli

    def fail(*args, **kwargs):
        raise OSError("private-path-sentinel")

    monkeypatch.setattr(cli, "backup_job_store", fail)
    assert cli.main(["backup", "source", "new-target", "--maximum-bytes", "100"]) == 1
    output = capsys.readouterr().out
    assert "private-path-sentinel" not in output
    assert json.loads(output)["status"] == "failed"


def test_cli_restore_requires_separately_held_digest():
    from structural_analysis.execution.job_store_backup_cli import main

    with pytest.raises(SystemExit) as error:
        main(["restore", "backup", "new-target", "--maximum-bytes", "100"])
    assert error.value.code == 2


def test_finalization_sync_failure_restores_quarantine(store, tmp_path, monkeypatch):
    from structural_analysis.execution import job_store_backup as backup_module
    from structural_analysis.execution.job_service import JobServiceError

    source, receipt = saved(store, tmp_path)
    target = tmp_path / "restored"
    original = backup_module._sync_directory
    failed = False

    def sync(path):
        nonlocal failed
        if (
            path == target
            and (target / "restore-receipt.json").exists()
            and not (target / backup_module.RESTORE_PENDING).exists()
            and not failed
        ):
            failed = True
            raise OSError("synthetic final sync failure")
        return original(path)

    monkeypatch.setattr(backup_module, "_sync_directory", sync)
    with pytest.raises(OSError):
        restore_job_store(
            source,
            target,
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )
    assert failed and (target / backup_module.RESTORE_PENDING).exists()
    with pytest.raises(JobServiceError):
        service(target)


def test_verify_sealed_backup_without_writes_or_destination(
    store, tmp_path, monkeypatch
):
    from structural_analysis.execution import job_store_backup as backup

    source, receipt = saved(store, tmp_path)
    before = {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    real_connect = backup.sqlite3.connect
    observed = []

    def connect(database, **kwargs):
        observed.append(database)
        assert database.endswith("?mode=ro&immutable=1")
        return real_connect(database, **kwargs)

    monkeypatch.setattr(backup.sqlite3, "connect", connect)
    result = backup.verify_job_store_backup(
        source, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=LIMIT
    )
    assert observed
    assert result["files"] == receipt["files"]
    assert result["payload_bytes"] == receipt["payload_bytes"]
    assert result["application_integrity_checked"] is False
    assert result["service_started"] is False
    assert before == {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "name",
    [
        ".job-store-backup.pending",
        ".job-store-restore.pending",
        "jobs.sqlite3-wal",
        "jobs.sqlite3-shm",
        "jobs.sqlite3-journal",
    ],
)
def test_verify_rejects_incomplete_or_unsealed_backup(store, tmp_path, name):
    from structural_analysis.execution.job_store_backup import verify_job_store_backup

    source, receipt = saved(store, tmp_path)
    (source / name).symlink_to(source / "missing")
    with pytest.raises(ValueError):
        verify_job_store_backup(
            source, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=LIMIT
        )


@pytest.mark.parametrize("change", ["digest", "bytes", "budget", "link"])
def test_verify_rejects_mismatch_and_budget(store, tmp_path, change):
    from structural_analysis.execution.job_store_backup import verify_job_store_backup

    source, receipt = saved(store, tmp_path)
    digest = receipt["manifest_sha256"]
    limit = LIMIT
    if change == "digest":
        digest = "0" * 64
    elif change == "budget":
        limit = 1
    else:
        blob = next((source / "blobs/sha256").glob("*/*"))
        if change == "bytes":
            data = blob.read_bytes()
            blob.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        else:
            blob.unlink()
            blob.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        verify_job_store_backup(source, manifest_sha256=digest, maximum_bytes=limit)


def test_cli_verify_accepts_no_destination_and_requires_digest(store, tmp_path, capsys):
    from structural_analysis.execution.job_store_backup_cli import main

    source, receipt = saved(store, tmp_path)
    args = ["verify", str(source), "--maximum-bytes", str(LIMIT)]
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert exc.value.code == 2
    args += ["--manifest-sha256", receipt["manifest_sha256"]]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["operation"] == "verify"
    with pytest.raises(SystemExit) as exc:
        main(args + [str(tmp_path / "unwanted")])
    assert exc.value.code == 2
    assert not (tmp_path / "unwanted").exists()


@pytest.mark.parametrize("claim_job", [False, True])
def test_verification_reports_recovery_counts_without_token_material(
    store, tmp_path, claim_job
):
    from structural_analysis.execution.job_store_backup import verify_job_store_backup

    original, job = store
    claim = (
        original.claim_next(
            worker_id="worker", authorization_token="test-worker-backup-0123456789"
        )
        if claim_job
        else None
    )
    source, receipt = saved(store, tmp_path)
    result = verify_job_store_backup(
        source, manifest_sha256=receipt["manifest_sha256"], maximum_bytes=LIMIT
    )
    snapshot = result["recovery_snapshot"]
    assert sum(snapshot["job_status_counts"].values()) == 1
    assert snapshot["job_status_counts"]["running" if claim_job else "queued"] == 1
    assert snapshot["recorded_leases"] == int(claim_job)
    assert snapshot["lease_expiry_evaluated"] is False
    assert snapshot["original_writers_fenced"] is False
    text = json.dumps(result)
    assert job.job_id not in text
    assert TOKEN not in text
    if claim:
        assert claim.lease_token not in text


def test_restored_running_job_preserves_expiry_and_rejects_old_token_after_reclaim(
    store, tmp_path
):
    from datetime import datetime, timedelta, timezone
    from structural_analysis.execution.job_service import JobServiceError

    original, job = store
    now = [datetime(2026, 10, 8, tzinfo=timezone.utc)]

    def open_at_clock(root):
        return DurableJobService(
            root,
            tenant_tokens={"tenant": TOKEN},
            worker_tokens={"worker": "test-worker-backup-0123456789"},
            clock=lambda: now[0],
        )

    live = open_at_clock(original.root)
    worker = dict(
        worker_id="worker", authorization_token="test-worker-backup-0123456789"
    )
    old = live.claim_next(**worker, lease_seconds=60)
    assert old is not None
    before = live.get_job(
        job.job_id, tenant_id="tenant", authorization_token=TOKEN
    ).to_dict()
    source, receipt = saved(store, tmp_path)
    destination = tmp_path / "restored-running"
    restore_job_store(
        source,
        destination,
        manifest_sha256=receipt["manifest_sha256"],
        maximum_bytes=LIMIT,
    )
    restored = open_at_clock(destination)
    assert (
        restored.get_job(
            job.job_id, tenant_id="tenant", authorization_token=TOKEN
        ).to_dict()
        == before
    )
    assert restored.claim_next(**worker) is None
    now[0] += timedelta(seconds=60)
    new = restored.claim_next(**worker)
    assert new is not None and new.job.job_id == job.job_id
    assert new.job.attempt == old.job.attempt + 1
    assert new.lease_token != old.lease_token
    with pytest.raises(JobServiceError) as exc:
        restored.heartbeat(job.job_id, **worker, lease_token=old.lease_token)
    assert exc.value.code == "lease_unauthorized"
    renewed = restored.heartbeat(job.job_id, **worker, lease_token=new.lease_token)
    assert renewed.status == "running"
    restored.validate_integrity(
        job.job_id, tenant_id="tenant", authorization_token=TOKEN
    )
    assert (
        live.get_job(
            job.job_id, tenant_id="tenant", authorization_token=TOKEN
        ).to_dict()
        == before
    )


@pytest.mark.parametrize(
    "member",
    [
        ".job-store-backup.pending",
        ".job-store-restore.pending",
        "jobs.sqlite3-wal",
        "jobs.sqlite3-shm",
        "jobs.sqlite3-journal",
    ],
)
@pytest.mark.parametrize("dangling", [False, True])
def test_restore_rejects_unsealed_source_before_destination_creation(
    store, tmp_path, member, dangling
):
    source, receipt = saved(store, tmp_path)
    marker = source / member
    if dangling:
        marker.symlink_to(tmp_path / "absent-marker-target")
    else:
        marker.write_bytes(b"unfinished")
    destination = tmp_path / "must-not-be-created"
    original_db = (source / "jobs.sqlite3").read_bytes()
    with pytest.raises(ValueError, match="incomplete|not sealed"):
        restore_job_store(
            source,
            destination,
            manifest_sha256=receipt["manifest_sha256"],
            maximum_bytes=LIMIT,
        )
    assert not destination.exists()
    assert (source / "jobs.sqlite3").read_bytes() == original_db
    assert marker.is_symlink() if dangling else marker.read_bytes() == b"unfinished"
