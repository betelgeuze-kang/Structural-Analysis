"""Existing-owner observation must not repair, spend, or admit another run."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import sqlite3
import sys

import pytest

from structural_analysis.execution.job_execution_authority import (
    ExecutionAuthorityError,
    ExistingOrdinalTrialMember,
    JobExecutionAuthority,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux authority")


@pytest.fixture
def existing_trial(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "original-store"
    )
    members = tuple(
        ExistingOrdinalTrialMember(
            "job_" + letter * 32,
            "sha256:" + request * 64,
            "sha256:" + context * 64,
        )
        for letter, request, context in (("a", "b", "d"), ("b", "c", "e"))
    )
    for member in members:
        authority.register_job(binding, member.job_id, member.request_hash, 8)
        authority.register_ordinal_credits(
            binding, member.job_id, member.request_hash, member.context_hash, 512, 512
        )
    # A valid existing adoption has no invented reservation or outcome history.
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute(
            "UPDATE budgets SET spent=2,adopted_spent=2 WHERE job_id=?",
            (members[0].job_id,),
        )
    for member, ceilings in zip(members, ((255, 0), (11, 17)), strict=True):
        for phase, ceiling in zip(
            ("production", "verification"), ceilings, strict=True
        ):
            ordinal = authority.reserve(binding, member.job_id, member.request_hash)
            authority.reserve_ordinal_credits(
                binding,
                member.job_id,
                member.request_hash,
                member.context_hash,
                api_ordinal=ordinal,
                phase=phase,
                ceiling=ceiling,
                completed_before=0,
                prior_checkpoint_hash=None,
                native_input_sha256=None,
                record_limit=255,
                worker_id="fixture-worker",
                lease_token_hash="sha256:" + "f" * 64,
            )
    # Failure before a phase grant or launch still consumes this API reservation.
    authority.reserve(binding, members[0].job_id, members[0].request_hash)
    return authority, binding, members


def pins(directory):
    return {
        str(path.relative_to(directory)): (
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_mode,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
        for path in (directory, *directory.rglob("*"))
    }


def test_snapshot_preserves_unknown_zero_and_adopted_costs_without_writes(
    existing_trial, monkeypatch
):
    authority, binding, members = existing_trial
    before = pins(authority.directory)
    opened = []
    real_open = os.open

    def readonly_open(path, flags, *args, **kwargs):
        opened.append((str(path), flags))
        assert flags & (os.O_RDWR | os.O_WRONLY | os.O_CREAT | os.O_TRUNC) == 0
        return real_open(path, flags, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        pytest.fail("observation entered a writable or recovery path")

    monkeypatch.setattr(os, "open", readonly_open)
    for name in (
        "_connection",
        "register_job",
        "register_ordinal_credits",
        "reserve",
        "reserve_ordinal_credits",
        "activate",
        "execution_permit",
    ):
        monkeypatch.setattr(authority, name, forbidden)
    snapshot = authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert opened
    assert snapshot["aggregate"]["api"] == {
        "maximum_attempts": 16,
        "reserved_attempts": 7,
        "remaining_attempts": 9,
        "adopted_reserved_attempts": 2,
    }
    assert snapshot["aggregate"]["production"] == {
        "maximum": 1024,
        "reserved": 266,
        "remaining": 758,
    }
    assert snapshot["aggregate"]["verification"] == {
        "maximum": 1024,
        "reserved": 17,
        "remaining": 1007,
    }
    assert [row["ordinal_grant_count"] for row in snapshot["members"]] == [2, 2]
    assert all(row["numerical_work"] == "unknown" for row in snapshot["members"])
    assert snapshot["read_only"] is True
    assert snapshot["reconciled"] is snapshot["new_run_admitted"] is False
    assert "claims" in snapshot["unobserved"]
    assert pins(authority.directory) == before


@pytest.mark.parametrize(
    "scope", ["list", "duplicate", "missing", "request", "context"]
)
def test_membership_or_historical_context_cannot_be_reinterpreted(
    existing_trial, scope
):
    authority, binding, members = existing_trial
    changed = {
        "list": list(members),
        "duplicate": (members[0], members[0]),
        "missing": members[:1],
        "request": (replace(members[0], request_hash="sha256:" + "f" * 64), members[1]),
        "context": (replace(members[0], context_hash="sha256:" + "f" * 64), members[1]),
    }[scope]
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError):
        authority.read_existing_ordinal_trial_snapshot(binding, changed)
    assert pins(authority.directory) == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecars_are_rejected_without_stale_immutable_recovery(existing_trial, suffix):
    authority, binding, members = existing_trial
    sidecar = Path(str(authority.directory / "authority.sqlite3") + suffix)
    sidecar.write_bytes(b"existing unknown journal state")
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError, match="journal or WAL"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


@pytest.mark.parametrize("member", ["authority.lock", "authority.sqlite3", "permit"])
def test_missing_existing_files_are_not_recreated(existing_trial, member):
    authority, binding, members = existing_trial
    path = authority.directory / member
    if member == "permit":
        path = authority.permit_directory / (members[0].job_id + ".lock")
    path.unlink()
    before = pins(authority.directory)
    with pytest.raises(ValueError):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE budgets SET spent=0",
        "DELETE FROM ordinal_credit_reservations",
        "CREATE TABLE surprise(value)",
        "PRAGMA journal_mode=WAL",
        "PRAGMA query_only=OFF",
    ],
)
def test_sql_authorizer_rejects_mutations_before_files_change(existing_trial, sql):
    authority, _binding, _members = existing_trial
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError):
        with authority._readonly_connection() as db:
            db.execute(sql)
    assert pins(authority.directory) == before


def test_generation_fence_blocks_activation_during_complete_read(
    existing_trial, monkeypatch
):
    authority, binding, members = existing_trial
    real_budget = authority._budget
    attempted = []

    def checked_budget(*args, **kwargs):
        if not attempted:
            attempted.append(True)
            with pytest.raises(ExecutionAuthorityError, match="busy"):
                JobExecutionAuthority(authority.directory).activate(
                    binding, authority.directory.parent / "restored"
                )
        return real_budget(*args, **kwargs)

    before = pins(authority.directory)
    monkeypatch.setattr(authority, "_budget", checked_budget)
    snapshot = authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert attempted and snapshot["authority_generation"] == binding.generation
    assert pins(authority.directory) == before


def test_stale_binding_cannot_be_adopted_by_an_observation(existing_trial):
    authority, old, members = existing_trial
    current = authority.activate(old, authority.directory.parent / "restored")
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError, match="stale"):
        authority.read_existing_ordinal_trial_snapshot(old, members)
    assert (
        authority.read_existing_ordinal_trial_snapshot(current, members)[
            "authority_generation"
        ]
        == current.generation
    )
    assert pins(authority.directory) == before


def test_unexpected_registered_job_is_not_omitted(existing_trial):
    authority, binding, members = existing_trial
    authority.register_job(binding, "job_" + "c" * 32, "sha256:" + "a" * 64, 1)
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError, match="membership differs"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


def test_historical_observation_never_rebuilds_a_numerical_source_context(
    existing_trial, monkeypatch
):
    from structural_analysis.assembly import (
        stateful_corotational_fiber_frame2d_control_subdivision as numerical,
    )
    import subprocess

    authority, binding, members = existing_trial

    def forbidden(*_args, **_kwargs):
        pytest.fail("historical observation attempted source reconstruction or launch")

    monkeypatch.setattr(numerical, "_source_identity", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    snapshot = authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert tuple(row["context_hash"] for row in snapshot["members"]) == tuple(
        member.context_hash for member in members
    )
    assert "source_bytes" in snapshot["unobserved"]
    assert snapshot["new_run_admitted"] is False


def test_replaced_permit_file_is_not_accepted_or_repaired(existing_trial):
    authority, binding, members = existing_trial
    path = authority.permit_directory / (members[0].job_id + ".lock")
    held = path.open("rb")
    try:
        path.unlink()
        path.write_bytes(b"")
        before = pins(authority.directory)
        with pytest.raises(ValueError, match="pin"):
            authority.read_existing_ordinal_trial_snapshot(binding, members)
        assert pins(authority.directory) == before
    finally:
        held.close()


@pytest.mark.parametrize("table", ["reservations", "ordinal_credit_reservations"])
def test_orphan_reservations_are_rejected_without_omitting_unknown_work(
    existing_trial, table
):
    authority, binding, members = existing_trial
    orphan = "job_" + "f" * 32
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        if table == "reservations":
            db.execute(
                "INSERT INTO reservations VALUES (?,1,?,?)",
                (orphan, binding.generation, binding.root),
            )
        else:
            db.execute(
                "INSERT INTO ordinal_credit_reservations VALUES (?,1,1,'production',"
                "255,'{}',?)",
                (orphan, "sha256:" + "f" * 64),
            )
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError, match="orphan work"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


def test_pinned_job_without_budget_is_not_omitted(existing_trial):
    authority, binding, members = existing_trial
    orphan = "job_" + "c" * 32
    request = "sha256:" + "a" * 64
    authority.register_job(binding, orphan, request, 1)
    authority.register_ordinal_credits(
        binding, orphan, request, "sha256:" + "b" * 64, 1, 1
    )
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DELETE FROM budgets WHERE job_id=?", (orphan,))
        db.execute("DELETE FROM ordinal_credit_budgets WHERE job_id=?", (orphan,))
    before = pins(authority.directory)
    with pytest.raises(ExecutionAuthorityError, match="permit membership differs"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


@pytest.mark.parametrize("table", ["reservations", "ordinal_credit_reservations"])
def test_oversized_journal_is_rejected_before_member_decoding(
    existing_trial, monkeypatch, table
):
    authority, binding, members = existing_trial
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute(f"DELETE FROM {table}")
        if table == "reservations":
            db.executemany(
                "INSERT INTO reservations VALUES (?,?,?,?)",
                (
                    (members[0].job_id, index, binding.generation, binding.root)
                    for index in range(1, 4098)
                ),
            )
        else:
            db.executemany(
                "INSERT INTO ordinal_credit_reservations VALUES (?,?,?,'production',"
                "0,'{}',?)",
                (
                    (members[0].job_id, index, index, "sha256:" + "f" * 64)
                    for index in range(1, 4098)
                ),
            )
    before = pins(authority.directory)

    def forbidden(*_args, **_kwargs):
        pytest.fail("oversized journal entered unbounded member decoding")

    monkeypatch.setattr(authority, "_budget", forbidden)
    with pytest.raises(ExecutionAuthorityError, match="journal too large"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


@pytest.mark.parametrize("scope", ["multibyte_payload", "total_payload"])
def test_payload_byte_limit_precedes_json_and_member_decoding(
    existing_trial, monkeypatch, scope
):
    authority, binding, members = existing_trial
    count, payload = (
        (1, "é" * 8193) if scope == "multibyte_payload" else (257, "x" * 16384)
    )
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("DELETE FROM ordinal_credit_reservations")
        db.executemany(
            "INSERT INTO ordinal_credit_reservations VALUES (?,?,?,'production',0,?,?)",
            (
                (members[0].job_id, index, index, payload, "sha256:" + "f" * 64)
                for index in range(1, count + 1)
            ),
        )
    before = pins(authority.directory)

    def forbidden(*_args, **_kwargs):
        pytest.fail("oversized byte payload entered JSON or member decoding")

    monkeypatch.setattr(authority, "_budget", forbidden)
    with pytest.raises(ExecutionAuthorityError, match="payload too large"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before


def test_closed_wal_database_rejected_before_sqlite_can_create_sidecars(
    existing_trial, monkeypatch
):
    authority, binding, members = existing_trial
    path = authority.directory / "authority.sqlite3"
    db = sqlite3.connect(path)
    try:
        assert db.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
    finally:
        db.close()
    assert path.read_bytes()[18:20] == b"\x02\x02"
    assert not any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm"))
    before = pins(authority.directory)

    def forbidden(*_args, **_kwargs):
        pytest.fail("persisted WAL was opened by SQLite before rejection")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    with pytest.raises(ExecutionAuthorityError, match="persisted rollback"):
        authority.read_existing_ordinal_trial_snapshot(binding, members)
    assert pins(authority.directory) == before
