"""Authority primitive only; service/worker integration remains mandatory."""

from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import os
import sqlite3
import subprocess
import sys

import pytest

from structural_analysis.execution.job_execution_authority import (
    ExecutionAuthorityError,
    JobExecutionAuthority,
)

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux authority")
JOB = "job_" + "a" * 32
REQUEST = "sha256:" + "b" * 64


def reserve_one(directory, binding):
    try:
        return JobExecutionAuthority(directory).reserve(binding, JOB, REQUEST)
    except ExecutionAuthorityError as error:
        return str(error)


def hold_in_child(directory, binding, ready, release):
    with JobExecutionAuthority(directory).execution(binding):
        ready.set()
        assert release.wait(15)


def reserve_then_crash(directory, binding):
    JobExecutionAuthority(directory).reserve(binding, JOB, REQUEST)
    os._exit(19)  # No caller-side persistence, outcome, or cleanup executes.


def activate_contender(directory, binding, destination, ready, go, results):
    ready.put(True)
    assert go.wait(15)
    try:
        result = JobExecutionAuthority(directory).activate(binding, destination)
    except ExecutionAuthorityError as error:
        result = str(error)
    results.put(result)


def test_restore_keeps_spent_ordinals_and_fences_original(tmp_path):
    authority, old = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(old, JOB, REQUEST, 8, initial_spent=3)
    assert authority.reserve(old, JOB, REQUEST) == 4
    # No outcome/local DB write follows this reservation: spend stays unknown.
    new = authority.activate(old, tmp_path / "restored")
    reopened = JobExecutionAuthority(tmp_path / "authority")
    assert reopened.register_job(new, JOB, REQUEST, 8, initial_spent=1) == 4
    for ordinal in range(5, 9):
        assert reopened.reserve(new, JOB, REQUEST) == ordinal
    with pytest.raises(ExecutionAuthorityError, match="budget exhausted"):
        reopened.reserve(new, JOB, REQUEST)
    for operation in (
        lambda: authority.reserve(old, JOB, REQUEST),
        lambda: authority.register_job(old, JOB, REQUEST, 8),
        lambda: authority.activate(old, tmp_path / "another"),
    ):
        with pytest.raises(ExecutionAuthorityError, match="stale"):
            operation()
    with pytest.raises(ExecutionAuthorityError, match="stale"):
        with authority.execution(old):
            pytest.fail("stale computation entered")


def test_live_computation_blocks_activation_across_processes(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(
        target=hold_in_child, args=(authority.directory, binding, ready, release)
    )
    child.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ExecutionAuthorityError, match="busy"):
            authority.activate(binding, tmp_path / "restored")
    finally:
        release.set()
        child.join(15)
        if child.is_alive():
            child.kill()
            child.join()
    assert child.exitcode == 0
    assert authority.activate(binding, tmp_path / "restored").generation == 2


def test_concurrent_reservations_never_exceed_limit(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    with ProcessPoolExecutor(
        max_workers=4, mp_context=multiprocessing.get_context("spawn")
    ) as pool:
        results = list(
            pool.map(reserve_one, [authority.directory] * 16, [binding] * 16)
        )
    assert sorted(x for x in results if type(x) is int) == list(range(1, 9))
    assert sum(x == "execution budget exhausted or invalid" for x in results) == 8


@pytest.mark.parametrize("member", ["authority.lock", "authority.sqlite3"])
def test_missing_authority_is_not_recreated(tmp_path, member):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    (authority.directory / member).unlink()
    with pytest.raises(ExecutionAuthorityError):
        with authority.execution(binding):
            pytest.fail("missing authority admitted")
    assert not (authority.directory / member).exists()


def test_corrupt_authority_and_job_identity_are_rejected(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    with pytest.raises(ExecutionAuthorityError, match="mismatch"):
        authority.register_job(binding, JOB, "sha256:" + "c" * 64, 8)
    with pytest.raises(ExecutionAuthorityError, match="mismatch"):
        authority.register_job(binding, JOB, REQUEST, 9)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute("UPDATE budgets SET spent=-1")
    with pytest.raises(ExecutionAuthorityError):
        authority.reserve(binding, JOB, REQUEST)
    (authority.directory / "authority.sqlite3").write_bytes(b"corrupt")
    with pytest.raises(ExecutionAuthorityError):
        with authority.execution(binding):
            pytest.fail("corrupt authority admitted")


def test_authority_must_be_outside_copied_store(tmp_path):
    with pytest.raises(ExecutionAuthorityError, match="external"):
        JobExecutionAuthority.create(
            tmp_path / "store" / "authority", tmp_path / "store"
        )
    assert not (tmp_path / "store").exists()


@pytest.mark.parametrize(
    "maximum,spent", [(True, 0), (8, True), (8, -1), (8, 9), (0, 0)]
)
def test_invalid_budget_rejected_before_enrollment(tmp_path, maximum, spent):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    with pytest.raises(ExecutionAuthorityError):
        authority.register_job(binding, JOB, REQUEST, maximum, initial_spent=spent)
    assert authority.register_job(binding, JOB, REQUEST, 8) == 0


def test_process_death_after_reservation_preserves_spend_on_restore(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    child = multiprocessing.get_context("spawn").Process(
        target=reserve_then_crash, args=(authority.directory, binding)
    )
    child.start()
    child.join(15)
    if child.is_alive():
        child.kill()
        child.join()
        pytest.fail("reservation child did not finish")
    assert child.exitcode == 19
    restored = authority.activate(binding, tmp_path / "restored")
    assert authority.register_job(restored, JOB, REQUEST, 8, initial_spent=0) == 1
    assert authority.read_budget(restored, JOB, REQUEST) == {
        "maximum_attempts": 8,
        "reserved_attempts": 1,
        "remaining_attempts": 7,
        "adopted_reserved_attempts": 0,
    }
    assert authority.reserve(restored, JOB, REQUEST) == 2


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE budgets SET spent=2",
        "DELETE FROM reservations",
        "UPDATE reservations SET ordinal=3",
        "UPDATE reservations SET generation=99",
        "UPDATE reservations SET root='relative'",
    ],
)
def test_journal_corruption_rejected_before_more_spend(tmp_path, sql):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    authority.reserve(binding, JOB, REQUEST)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute(sql)
    for action in (
        lambda: authority.read_budget(binding, JOB, REQUEST),
        lambda: authority.register_job(binding, JOB, REQUEST, 8),
        lambda: authority.reserve(binding, JOB, REQUEST),
    ):
        with pytest.raises(ExecutionAuthorityError):
            action()


def test_reservation_counter_and_journal_commit_together(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    with sqlite3.connect(authority.directory / "authority.sqlite3") as db:
        db.execute(
            "CREATE TRIGGER reject_journal BEFORE INSERT ON reservations BEGIN SELECT RAISE(ABORT, 'injected write failure'); END"
        )
    with pytest.raises(ExecutionAuthorityError):
        authority.reserve(binding, JOB, REQUEST)
    assert authority.read_budget(binding, JOB, REQUEST)["reserved_attempts"] == 0


def test_concurrent_activation_has_one_winner(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    ctx = multiprocessing.get_context("spawn")
    ready, results, go = ctx.Queue(), ctx.Queue(), ctx.Event()
    children = [
        ctx.Process(
            target=activate_contender,
            args=(
                authority.directory,
                binding,
                tmp_path / f"restored-{i}",
                ready,
                go,
                results,
            ),
        )
        for i in range(2)
    ]
    for child in children:
        child.start()
    try:
        for _ in children:
            assert ready.get(timeout=10)
        go.set()
        replies = [results.get(timeout=10) for _ in children]
    finally:
        go.set()
        for child in children:
            child.join(15)
            if child.is_alive():
                child.kill()
                child.join()
        ready.close()
        results.close()
    assert all(child.exitcode == 0 for child in children)
    winners = [r for r in replies if not isinstance(r, str)]
    assert len(winners) == 1
    assert winners[0].generation == 2
    assert (
        sum(isinstance(r, str) and ("busy" in r or "stale" in r) for r in replies) == 1
    )
    assert authority.reserve(winners[0], JOB, REQUEST) == 1
    with pytest.raises(ExecutionAuthorityError, match="stale"):
        authority.activate(binding, tmp_path / "late-retry")


def test_killed_direct_execution_holder_releases_lock_after_reap(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    authority.register_job(binding, JOB, REQUEST, 8)
    authority.reserve(binding, JOB, REQUEST)
    ctx = multiprocessing.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    child = ctx.Process(
        target=hold_in_child, args=(authority.directory, binding, ready, release)
    )
    child.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ExecutionAuthorityError, match="busy"):
            authority.activate(binding, tmp_path / "restored")
    finally:
        if child.is_alive():
            child.kill()
        child.join(15)
    assert child.exitcode == -9
    new = authority.activate(binding, tmp_path / "restored")
    assert authority.read_budget(new, JOB, REQUEST)["reserved_attempts"] == 1


def test_inherited_child_lock_outlives_parent_context(tmp_path):
    authority, binding = JobExecutionAuthority.create(
        tmp_path / "authority", tmp_path / "source"
    )
    child = None
    try:
        with authority.execution(binding) as fd:
            assert not os.get_inheritable(fd)
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import os,sys; os.fstat(int(sys.argv[1])); os.write(1,b'ready\\n'); sys.stdin.buffer.read(1)",
                    str(fd),
                ],
                pass_fds=(fd,),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
            assert child.stdout.readline() == b"ready\n"
        # Parent-side context is gone; the explicit child still owns the lock.
        with pytest.raises(ExecutionAuthorityError, match="busy"):
            authority.activate(binding, tmp_path / "restored")
    finally:
        if child is not None:
            try:
                child.communicate(input=b"x", timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                raise
    assert child.returncode == 0
    assert authority.activate(binding, tmp_path / "restored").generation == 2
