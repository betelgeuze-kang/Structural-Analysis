"""Real bounded RC executions and explicit filesystem/process failure controls."""

from __future__ import annotations

from dataclasses import replace
import json
import os
import sqlite3
import subprocess
import sys

import pytest

from tests.test_rc_control_local_research import (
    SOURCE, ROOT, model as model, control_request as control_request,
    options as options, evaluate, experiment_file,
)
from structural_analysis.benchmark import rc_control_reuse as reuse
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.execution.job_service import DurableJobService, JobServiceError
from structural_analysis.execution.rc_result_repository import RCResultRepository, open_local_rc_repository


pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX local result store")
TOKEN = "test-only-authorized-research-token"


def repository(root, scope="research", **kwargs):
    service = DurableJobService(
        root, tenant_tokens={"lab": TOKEN, "other": TOKEN + "2"},
        worker_tokens={"worker": "test-only-worker-token"},
    )
    return RCResultRepository(
        service, tenant_id="lab", authorization_token=TOKEN, scope_id=scope, **kwargs
    )


def session(root, **kwargs):
    return reuse.RCControlResultSession(
        source_revision=SOURCE, scope_id="research", repository=repository(root), **kwargs
    )


def test_reopen_reprices_and_rescreens_without_numerical_work(model, control_request, options, tmp_path):
    first = evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "fresh")
    assert first["new_work"]["known_counters"]["attempted_step_count"] == 8
    second = evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "reopened",
                      allow_new_analysis=False, prices=replace(options["prices"], concrete_per_m3=150.0))
    assert second["reuse_origin"] == "durable_original"
    assert second["fresh_reference_verification_this_call"] is False
    assert second["new_work"]["api_invocation_count"] == 0
    assert second["original_work_not_recharged"] == first["new_work"]
    assert second["row"]["material_estimate"]["total"] - first["row"]["material_estimate"]["total"] == pytest.approx(36.0)
    for role, ref in first["row"]["artifacts"].items():
        assert (tmp_path / "fresh" / ref["path"]).read_bytes() == (tmp_path / "reopened" / second["row"]["artifacts"][role]["path"]).read_bytes()
    complete = json.loads((tmp_path / "reopened/completion.json").read_bytes())
    assert complete["wall_ns_before_completion_write"] >= second["total_wall_ns"]
    assert sum(second["stage_wall_ns"].values()) <= second["total_wall_ns"]
    assert json.loads((tmp_path / "reopened/persistence.json").read_bytes())["admitted"] is True


def test_changed_preload_does_not_reuse(model, control_request, options, tmp_path):
    evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "fresh")
    changed = replace(control_request, constant_nodal_loads=(("N2", -601.0, 0.0, 0.0),))
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(session(tmp_path / "store"), model, changed, options, tmp_path / "miss", allow_new_analysis=False)
    assert not (tmp_path / "miss").exists()


def test_capacity_refuses_admission_without_breaking_valid_solve(model, control_request, options, tmp_path):
    repo = repository(tmp_path / "store", max_bytes=1)
    s = reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research", repository=repo)
    result = evaluate(s, model, control_request, options, tmp_path / "out")
    assert result["row"]["full_reference_verification_pass"] is True
    assert json.loads((tmp_path / "out/persistence.json").read_bytes())["admitted"] is False
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "nohit", allow_new_analysis=False)


def test_output_publication_failure_does_not_register(model, control_request, options, tmp_path, monkeypatch):
    original = study._save

    def fail(root, relative, data):
        if relative == "evaluation.json":
            raise OSError("injected full disk during evaluation publication")
        return original(root, relative, data)

    with monkeypatch.context() as patch:
        patch.setattr(study, "_save", fail)
        with pytest.raises(OSError):
            evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "broken")
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "unregistered", allow_new_analysis=False)


def test_failed_blob_publication_rolls_back_catalog(model, control_request, options, tmp_path, monkeypatch):
    repo = repository(tmp_path / "store")
    original = repo._service._put_blob
    count = 0

    def fail(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 3:
            raise OSError("injected disk write failure")
        return original(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(repo._service, "_put_blob", fail)
        with pytest.raises(OSError):
            evaluate(reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research", repository=repo), model, control_request, options, tmp_path / "broken")
    with sqlite3.connect(tmp_path / "store/jobs.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM rc_verified_result_index_v1").fetchone()[0] == 0
    assert list((tmp_path / "store/blobs").rglob("*"))  # Orphans are not trusted index entries.
    with pytest.raises(reuse.NewAnalysisRequired):
        evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "miss", allow_new_analysis=False)


def test_corrupt_original_blocks_reuse_without_new_solver_call(model, control_request, options, tmp_path, monkeypatch):
    repo = repository(tmp_path / "store")
    first = evaluate(reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research", repository=repo), model, control_request, options, tmp_path / "first")
    digest = first["row"]["artifacts"]["result"]["sha256"]
    repo._service._blob_path(digest).write_bytes(b"corrupt")

    def forbidden(*args, **kwargs):
        raise AssertionError("must not repair corruption by solving silently")

    monkeypatch.setattr(study, "_evaluate_design_row", forbidden)
    with pytest.raises(JobServiceError, match="integrity"):
        evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "corrupt")
    assert not (tmp_path / "corrupt").exists()


def test_tenant_and_scope_boundaries(model, control_request, options, tmp_path):
    repo = repository(tmp_path / "store")
    first = evaluate(reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research", repository=repo), model, control_request, options, tmp_path / "first")
    with pytest.raises(JobServiceError):
        RCResultRepository(repo._service, tenant_id="lab", authorization_token="wrong-token-over-16", scope_id="research")
    other = RCResultRepository(repo._service, tenant_id="other", authorization_token=TOKEN + "2", scope_id="research")
    assert other._load(first["physics_key"], "research") is None
    with pytest.raises(ValueError, match="ownership"):
        repo._load(first["physics_key"], "different")
    assert TOKEN not in "".join(p.read_text(errors="ignore") for p in (tmp_path / "first").rglob("*.json"))


def test_local_cli_owner_cannot_be_reconfigured(tmp_path):
    root = tmp_path / "store"
    open_local_rc_repository(root, tenant_id="lab", authorization_token=TOKEN, scope_id="research")
    open_local_rc_repository(root, tenant_id="lab", authorization_token=TOKEN, scope_id="research")
    with pytest.raises(ValueError, match="authorization"):
        open_local_rc_repository(root, tenant_id="lab", authorization_token=TOKEN + "changed", scope_id="research")
    with pytest.raises(ValueError, match="ownership"):
        open_local_rc_repository(root, tenant_id="other", authorization_token=TOKEN, scope_id="research")
    assert TOKEN not in (root / "rc-local-owner.json").read_text()


def test_subprocess_cli_restart_has_zero_new_work(control_request, options, tmp_path):
    req = tmp_path / "request.json"
    req.write_bytes(study._bytes(control_request.to_dict()))
    exp = experiment_file(tmp_path / "scenario.json", options)
    root = tmp_path / "store"
    prefix = [sys.executable, "-m", "structural_analysis.benchmark.rc_control_local_search_cli", "--model", str(ROOT / "examples/public_rc_fiber_frame_cantilever.json"), "--request", str(req), "--experiment", str(exp), "--source-revision", SOURCE, "--store-root", str(root)]
    env = os.environ | {"STRUCTURAL_RC_STORE_TOKEN": TOKEN}
    reports = []
    for suffix, budget in (("first", "2"), ("second", "0")):
        result = subprocess.run(prefix + ["--output", str(tmp_path / suffix), "--max-new-model-analyses", budget], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        reports.append(json.loads(result.stdout))
    assert reports[0]["scenarios"][0]["new_model_evaluations"] == 2
    assert reports[1]["scenarios"][0]["new_model_evaluations"] == 0
    assert reports[1]["scenarios"][0]["reused_model_evaluations"] == 2
    assert reports[1]["scenarios"][0]["new_work"]["api_invocation_count"] == 0
    assert reports[1]["persistent_cache"] is True


def test_process_death_releases_reservation(tmp_path):
    repo = repository(tmp_path / "store", lock_timeout_seconds=0.1)
    key = "sha256:" + "a" * 64
    child = '''
from pathlib import Path
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.execution.rc_result_repository import RCResultRepository
import sys,time
service=DurableJobService(sys.argv[1],tenant_tokens={"lab":sys.argv[2]},worker_tokens={"worker":"test-only-worker-token"})
repo=RCResultRepository(service,tenant_id="lab",authorization_token=sys.argv[2],scope_id="research")
with repo.reservation("sha256:"+"a"*64,"research"):
    print("locked",flush=True)
    time.sleep(30)
'''
    process = subprocess.Popen([sys.executable, "-c", child, str(tmp_path / "store"), TOKEN], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        import select
        assert select.select([process.stdout], [], [], 10)[0]
        assert process.stdout.readline().strip() == "locked"
        with pytest.raises(TimeoutError):
            with repo.reservation(key, "research"):
                pass
    finally:
        process.kill()
        process.communicate(timeout=5)
    with repo.reservation(key, "research"):
        assert repo._load(key, "research") is None


@pytest.mark.parametrize("field,value", [("max_entries", True), ("max_entries", 0), ("max_bytes", 0), ("max_bytes", True), ("lock_timeout_seconds", 0), ("lock_timeout_seconds", float("nan"))])
def test_repository_bounds(tmp_path, field, value):
    with pytest.raises(ValueError):
        repository(tmp_path / "store", **{field: value})


def test_forced_replay_retains_first_persistent_original(model, control_request, options, tmp_path):
    repo = repository(tmp_path / "store")
    s = reuse.RCControlResultSession(source_revision=SOURCE, scope_id="research", repository=repo)
    first = evaluate(s, model, control_request, options, tmp_path / "one")
    original = repo._load(first["physics_key"], "research")
    fresh = evaluate(s, model, control_request, options, tmp_path / "two", fresh=True)
    assert fresh["new_work"]["known_counters"]["attempted_step_count"] == 8
    assert repo._load(first["physics_key"], "research").seal == original.seal


def test_separate_sessions_serialize_same_key(model, control_request, options, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    one = session(tmp_path / "store")
    two = session(tmp_path / "store")
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(evaluate, s, model, control_request, options, tmp_path / str(i))
                   for i, s in enumerate((one, two))]
        results = [future.result(timeout=30) for future in futures]
    assert sorted(result["mode"] for result in results) == ["fresh_reference_and_replay", "verified_original_reused"]
    assert sum(result["new_work"]["known_counters"]["attempted_step_count"] for result in results) == 8


def test_real_child_exit_during_persistence_leaves_no_catalog_entry(control_request, options, tmp_path):
    req = tmp_path / "request.json"
    req.write_bytes(study._bytes(control_request.to_dict()))
    exp = experiment_file(tmp_path / "scenario.json", options)
    store = tmp_path / "store"
    open_local_rc_repository(store, tenant_id="local-research", authorization_token=TOKEN, scope_id="local-research")
    code = '''
import os,sys
from structural_analysis.execution.job_service import DurableJobService
from structural_analysis.benchmark.rc_control_local_search_cli import main
original=DurableJobService._put_blob
count=0
def crash(self,*a,**k):
    global count
    count+=1
    result=original(self,*a,**k)
    if count==2:
        os._exit(73)
    return result
DurableJobService._put_blob=crash
raise SystemExit(main(sys.argv[1:]))
'''
    args = ["--model", str(ROOT / "examples/public_rc_fiber_frame_cantilever.json"), "--request", str(req), "--experiment", str(exp), "--source-revision", SOURCE, "--store-root", str(store)]
    env = os.environ | {"STRUCTURAL_RC_STORE_TOKEN": TOKEN}
    result = subprocess.run([sys.executable, "-c", code, *args, "--output", str(tmp_path / "crashed")], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 73, result.stderr
    with sqlite3.connect(store / "jobs.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM rc_verified_result_index_v1").fetchone()[0] == 0
    result = subprocess.run([sys.executable, "-m", "structural_analysis.benchmark.rc_control_local_search_cli", *args, "--output", str(tmp_path / "no-budget"), "--max-new-model-analyses", "0"], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 2, result.stderr
    summary = json.loads(result.stdout)
    assert summary["scenarios"][0]["new_model_evaluations"] == 0
    assert summary["scenarios"][0]["cost_bound"]["pool_minimum_feasible_estimate"] is None


def test_persistent_rescreen_and_tenant_report_no_new_credit(model, control_request, options, tmp_path):
    first = evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "first")
    from structural_analysis.benchmark.fiber_frame_design import FiberFrameHistoryLimits

    limit = first["row"]["performance"]["maximum_absolute_fiber_strain"] / 2
    result = evaluate(session(tmp_path / "store"), model, control_request, options, tmp_path / "rescreen",
                      history_limits=FiberFrameHistoryLimits(0.1, limit), allow_new_analysis=False)
    assert result["row"]["selection_eligible"] is False
    assert result["row"]["full_reference_verification_pass"] is True
    assert result["fresh_reference_verification_this_call"] is False
    assert result["new_work"]["api_invocation_count"] == 0


def test_symlink_store_is_rejected(tmp_path):
    destination = tmp_path / "actual"
    destination.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        open_local_rc_repository(link, tenant_id="lab", authorization_token=TOKEN, scope_id="research")
    assert not list(destination.iterdir())


def _owner_record(tenant="lab", token=TOKEN):
    from structural_analysis.execution.rc_result_repository import _digest

    return {
        "schema": "local-rc-owner.v1",
        "tenant": tenant,
        "token_hash": _digest(
            b"local-rc-owner.v1\0" + tenant.encode() + b"\0" + token.encode()
        ),
    }


def test_owner_failure_before_publish_leaves_no_partial_authority(tmp_path, monkeypatch):
    from structural_analysis.execution import rc_result_repository as repository_module

    root = tmp_path / "owner"
    original_fsync = repository_module.os.fsync

    def reject_fsync(descriptor):
        raise OSError("injected owner flush failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(repository_module.os, "fsync", reject_fsync)
        with pytest.raises(OSError, match="flush"):
            open_local_rc_repository(
                root, tenant_id="lab", authorization_token=TOKEN, scope_id="research"
            )
    assert not (root / "rc-local-owner.json").exists()
    assert not list(root.glob(".rc-owner-*"))
    assert repository_module.os.fsync is original_fsync
    open_local_rc_repository(
        root, tenant_id="lab", authorization_token=TOKEN, scope_id="research"
    )
    assert json.loads((root / "rc-local-owner.json").read_bytes()) == _owner_record()


@pytest.mark.parametrize("same_credentials", [True, False])
def test_first_owner_race_never_replaces_winner(tmp_path, monkeypatch, same_credentials):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from structural_analysis.execution import rc_result_repository as repository_module

    original_link = repository_module.os.link
    barrier = Barrier(2)
    root = tmp_path / "race"
    root.mkdir()
    expected = [
        _owner_record(),
        _owner_record(token=TOKEN if same_credentials else TOKEN + "different"),
    ]

    def simultaneous_publish(*args, **kwargs):
        barrier.wait(timeout=10)
        return original_link(*args, **kwargs)

    def initialize(record):
        try:
            repository_module._initialize_local_owner(root, record)
        except ValueError as error:
            return str(error)
        return "ok"

    monkeypatch.setattr(repository_module.os, "link", simultaneous_publish)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(initialize, expected))
    winner = json.loads((root / "rc-local-owner.json").read_bytes())
    assert winner in expected
    if same_credentials:
        assert results == ["ok", "ok"]
    else:
        assert sorted(results) == ["local repository authorization failed", "ok"]
        assert results[expected.index(winner)] == "ok"
    assert not list(root.glob(".rc-owner-*"))
    assert (root / "rc-local-owner.json").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("content", [b"", b"{", b"{}", b"x" * 4097])
def test_existing_malformed_owner_is_not_replaced(tmp_path, content):
    root = tmp_path / "bad-owner"
    root.mkdir()
    owner = root / "rc-local-owner.json"
    owner.write_bytes(content)
    with pytest.raises(ValueError):
        open_local_rc_repository(
            root, tenant_id="lab", authorization_token=TOKEN, scope_id="research"
        )
    assert owner.read_bytes() == content
    assert not (root / "jobs.sqlite3").exists()


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_nonregular_owner_rejects_without_blocking(tmp_path, kind):
    from structural_analysis.execution import rc_result_repository as repository_module

    root = tmp_path / "nonregular"
    root.mkdir()
    owner = root / "rc-local-owner.json"
    if kind == "fifo":
        os.mkfifo(owner)
    else:
        destination = tmp_path / "target"
        destination.write_text("{}")
        owner.symlink_to(destination)
    with pytest.raises((ValueError, OSError)):
        repository_module._initialize_local_owner(root, _owner_record())
    assert not list(root.glob(".rc-owner-*"))


@pytest.mark.parametrize("token", ["short", "x" * 4097, None])
def test_owner_token_bounds_before_filesystem(tmp_path, token):
    root = tmp_path / "invalid-token"
    with pytest.raises(ValueError, match="token"):
        open_local_rc_repository(
            root, tenant_id="lab", authorization_token=token, scope_id="research"
        )
    assert not root.exists()


def test_unsupported_owner_platform_before_filesystem(tmp_path, monkeypatch):
    from structural_analysis.execution import rc_result_repository as repository_module

    root = tmp_path / "unsupported"
    with monkeypatch.context() as scoped:
        scoped.setattr(repository_module.os, "name", "nt")
        with pytest.raises(ValueError, match="POSIX"):
            open_local_rc_repository(
                root, tenant_id="lab", authorization_token=TOKEN, scope_id="research"
            )
    assert not root.exists()


def test_child_death_before_owner_publication_does_not_poison_store(tmp_path):
    import select

    root = tmp_path / "crashed-initialization"
    script = '''
import os, sys, time
from pathlib import Path
from structural_analysis.execution.rc_result_repository import open_local_rc_repository
original_link = os.link
def stop_before_publication(*args, **kwargs):
    print("complete-temp-only", flush=True)
    time.sleep(30)
    return original_link(*args, **kwargs)
os.link = stop_before_publication
open_local_rc_repository(Path(sys.argv[1]), tenant_id="lab",
    authorization_token=os.environ["RC_TEST_OWNER_TOKEN"], scope_id="research")
'''
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(root)],
        env=os.environ | {"RC_TEST_OWNER_TOKEN": TOKEN},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        assert select.select([process.stdout], [], [], 10)[0]
        assert process.stdout.readline().strip() == "complete-temp-only"
        assert not (root / "rc-local-owner.json").exists()
    finally:
        process.kill()
        process.communicate(timeout=5)
    leftovers = list(root.glob(".rc-owner-*"))
    assert len(leftovers) == 1
    # A crash orphan has no authority and need not be deleted to reopen safely.
    open_local_rc_repository(
        root, tenant_id="lab", authorization_token=TOKEN, scope_id="research"
    )
    assert json.loads((root / "rc-local-owner.json").read_bytes()) == _owner_record()
    assert leftovers[0].exists()
