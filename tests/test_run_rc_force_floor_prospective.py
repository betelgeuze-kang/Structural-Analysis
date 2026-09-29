"""A prospective runner must bind clean committed bytes before any solver call."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import run_rc_force_floor_prospective as runner


SOURCE = Path(__file__).resolve().parents[1]
CAMPAIGN = Path("examples/research/rc_reuse_campaign")
INPUT_NAMES = {
    "model": "pin-roller-replication.model.json",
    "request": "pin-roller-replication.request.json",
    "experiment": "force-floor-prospective.experiment.json",
    "floor_plan": "force-floor-prospective.floor.json",
}
PROTOCOL = CAMPAIGN / "force-floor-prospective.protocol.json"


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def committed_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str, Path]:
    # The tiny Git fixture holds only pinned inputs and the runner, while
    # source-package binding is checked independently below.
    monkeypatch.setattr(runner, "_require_runtime_source", lambda _repo: None)
    repo = tmp_path / "checkout"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Prospective Test")
    _git(repo, "config", "user.email", "prospective@example.invalid")
    script = repo / "scripts" / "run_rc_force_floor_prospective.py"
    script.parent.mkdir()
    shutil.copyfile(runner.__file__, script)
    references = {}
    for role, filename in INPUT_NAMES.items():
        relative = CAMPAIGN / filename
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, destination)
        references[role] = {
            "path": relative.as_posix(),
            "sha256": runner._sha(destination.read_bytes()),
        }
    protocol = {
        "schema_version": runner.PROTOCOL_SCHEMA,
        "inputs": references,
        "full_analysis_budget": 4,
        "reuse_line_search_assembly": False,
    }
    (repo / PROTOCOL).write_bytes(runner._canonical(protocol) + b"\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "freeze protocol inputs and runner")
    return repo, _git(repo, "rev-parse", "HEAD"), tmp_path / "packet"


def test_runtime_package_must_come_from_the_execution_checkout(tmp_path):
    with pytest.raises(ValueError, match="lacks the structural_analysis package"):
        runner._require_runtime_source(tmp_path)
    assert (SOURCE / "src" / "structural_analysis").is_dir()
    runner._require_runtime_source(SOURCE)


def _fake_search(study_inputs: dict, frozen: dict, binding: dict) -> dict:
    packet = frozen["output"]
    outer = json.loads((packet / "plan.json").read_bytes())
    assert outer["protocol_commit"] == binding["protocol_commit"]
    assert outer["protocol_sha256"] == binding["protocol_sha256"]
    assert outer["source_revision"] == frozen["source_revision"]
    assert outer["source_checkout_clean"] is True
    assert outer["search_mode"] == "price_order_then_exhaustive_oracle"
    assert outer["plan_hash"] == runner._sha(runner._canonical({
        key: value for key, value in outer.items() if key != "plan_hash"
    }))
    assert study_inputs["force_response_floor"]["minimum_load_factor"] == 180.0
    for role in runner.ROLES:
        assert (packet / "inputs" / f"{role}.json").read_bytes() == frozen["input_blobs"][role]

    search = packet / "search"
    search.mkdir()
    plan = {
        "schema_version": runner.SEARCH_PLAN_SCHEMA,
        "source_revision": frozen["source_revision"],
        "protocol_binding": binding,
        "learned_policy_used": False,
    }
    plan["plan_hash"] = runner._sha(runner._canonical(plan))
    runner._write_json(search / "plan.json", plan)
    result = {
        "schema_version": runner.SEARCH_REPORT_SCHEMA,
        "source_revision": frozen["source_revision"],
        "plan_hash": plan["plan_hash"],
        "claims": {
            "learned_policy_used": False,
            "independent_physical_validation": False,
            "net_ai_savings_proved": False,
            "confirmed_currency_savings": False,
        },
    }
    result["report_hash"] = runner._sha(runner._canonical(result))
    runner._write_json(search / "result.json", result)
    return result


def test_plan_is_frozen_before_search_and_receipts_cover_packet(
    committed_checkout, monkeypatch: pytest.MonkeyPatch,
):
    repo, commit, packet = committed_checkout
    monkeypatch.setattr(runner, "_execute_search", _fake_search)
    receipt = runner.run_packet(repo, PROTOCOL, commit, packet)
    plan = json.loads((packet / "plan.json").read_bytes())
    inventory = json.loads((packet / "inventory.json").read_bytes())
    assert plan["protocol_commit"] == commit
    assert plan["runner_sha256"] == runner._sha(
        (repo / "scripts" / "run_rc_force_floor_prospective.py").read_bytes()
    )
    assert receipt == json.loads((packet / "runner.json").read_bytes())
    assert receipt["report_hash"] == runner._sha(runner._canonical({
        key: value for key, value in receipt.items() if key != "report_hash"
    }))
    assert receipt["independent_physical_validation"] is False
    assert receipt["clean_source_checkout"] is True
    assert receipt["learned_policy_used"] is False
    assert receipt["ai_benefit_claimed"] is False
    assert inventory["inventory_sha256"] == runner._sha(runner._canonical(inventory["files"]))
    assert [row[0] for row in inventory["files"]] == sorted([
        "inputs/experiment.json", "inputs/floor_plan.json", "inputs/model.json",
        "inputs/request.json", "plan.json", "runner.json", "search/plan.json",
        "search/result.json",
    ])
    for relative, size, digest in inventory["files"]:
        raw = (packet / relative).read_bytes()
        assert size == len(raw)
        assert digest == runner._sha(raw)


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_dirty_or_untracked_source_rejected_before_output_or_solver(
    committed_checkout, monkeypatch: pytest.MonkeyPatch, dirty_kind: str,
):
    repo, commit, packet = committed_checkout
    path = repo / CAMPAIGN / INPUT_NAMES["request"] if dirty_kind == "tracked" else repo / "rogue.txt"
    path.write_bytes(path.read_bytes() + b" " if path.exists() else b"new")
    monkeypatch.setattr(runner, "_execute_search", lambda *_: pytest.fail("solver reached"))
    with pytest.raises(ValueError, match="clean source checkout"):
        runner.run_packet(repo, PROTOCOL, commit, packet)
    assert not packet.exists()


def test_nonancestor_protocol_commit_rejected_before_output_or_solver(
    committed_checkout, monkeypatch: pytest.MonkeyPatch,
):
    repo, _, packet = committed_checkout
    branch = _git(repo, "branch", "--show-current")
    _git(repo, "checkout", "-qb", "side")
    _git(repo, "commit", "--allow-empty", "-qm", "unrelated side revision")
    side_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", branch)
    monkeypatch.setattr(runner, "_execute_search", lambda *_: pytest.fail("solver reached"))
    with pytest.raises(ValueError, match="not an ancestor"):
        runner.run_packet(repo, PROTOCOL, side_commit, packet)
    assert not packet.exists()


@pytest.mark.parametrize("changed", ["protocol", "input"])
def test_descendant_checkout_with_changed_frozen_bytes_is_rejected(
    committed_checkout, monkeypatch: pytest.MonkeyPatch, changed: str,
):
    repo, protocol_commit, packet = committed_checkout
    relative = PROTOCOL if changed == "protocol" else CAMPAIGN / INPUT_NAMES["request"]
    path = repo / relative
    path.write_bytes(path.read_bytes() + b" ")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change pinned bytes after freeze")
    monkeypatch.setattr(runner, "_execute_search", lambda *_: pytest.fail("solver reached"))
    expected = "protocol bytes differ" if changed == "protocol" else "request input differs"
    with pytest.raises(ValueError, match=expected):
        runner.run_packet(repo, PROTOCOL, protocol_commit, packet)
    assert not packet.exists()


def test_wrong_declared_input_sha_rejected_before_output_or_solver(
    committed_checkout, monkeypatch: pytest.MonkeyPatch,
):
    repo, _, packet = committed_checkout
    path = repo / PROTOCOL
    protocol = json.loads(path.read_bytes())
    protocol["inputs"]["model"]["sha256"] = "sha256:" + "0" * 64
    path.write_bytes(runner._canonical(protocol) + b"\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "bad declared input digest")
    commit = _git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(runner, "_execute_search", lambda *_: pytest.fail("solver reached"))
    with pytest.raises(ValueError, match="model input differs"):
        runner.run_packet(repo, PROTOCOL, commit, packet)
    assert not packet.exists()


def test_source_change_during_search_blocks_completed_receipt(
    committed_checkout, monkeypatch: pytest.MonkeyPatch,
):
    repo, commit, packet = committed_checkout

    def changed_source(study_inputs, frozen, binding):
        result = _fake_search(study_inputs, frozen, binding)
        (repo / "unexpected.txt").write_text("source changed during run")
        return result

    monkeypatch.setattr(runner, "_execute_search", changed_source)
    with pytest.raises(ValueError, match="source checkout changed"):
        runner.run_packet(repo, PROTOCOL, commit, packet)
    assert (packet / "plan.json").exists()
    assert not (packet / "runner.json").exists()
    assert not (packet / "inventory.json").exists()
