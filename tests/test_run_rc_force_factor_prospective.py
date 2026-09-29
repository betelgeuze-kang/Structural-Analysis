"""V2 protocol binding and packet sequencing without numerical execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from scripts import run_rc_force_factor_prospective as runner


SOURCE = Path(__file__).resolve().parents[1]
PROTOCOL = Path(
    "examples/research/rc_reuse_campaign/force-factor-prospective.protocol.json"
)


def git(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=repo, text=True).strip()


@pytest.fixture
def committed_checkout(tmp_path: Path) -> tuple[Path, str, Path]:
    repo = tmp_path / "checkout"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Force Factor Test")
    git(repo, "config", "user.email", "force-factor@example.invalid")
    for relative in (PROTOCOL, Path("scripts/run_rc_force_factor_prospective.py")):
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, destination)
    protocol = json.loads((SOURCE / PROTOCOL).read_bytes())
    for ref in protocol["inputs"].values():
        relative = Path(ref["path"])
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, destination)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "freeze exact protocol inputs and runner")
    return repo, git(repo, "rev-parse", "HEAD"), tmp_path / "packet"


def test_preregistered_roles_hashes_and_disjoint_rosters() -> None:
    protocol = json.loads((SOURCE / PROTOCOL).read_bytes())
    assert protocol["schema_version"] == runner.PROTOCOL_SCHEMA
    assert set(protocol["inputs"]) == set(runner.ROLES)
    assert protocol["schedule"] == list(runner.SCHEDULE)
    assert protocol["floor_selection_provenance"] == runner.FLOOR_PROVENANCE
    assert protocol["independent_project_geometry_history_split"] is False
    for ref in protocol["inputs"].values():
        assert (
            ref["sha256"]
            == "sha256:"
            + hashlib.sha256((SOURCE / ref["path"]).read_bytes()).hexdigest()
        )
    training = json.loads(
        (SOURCE / protocol["inputs"]["training_experiment"]["path"]).read_bytes()
    )
    evaluation = json.loads(
        (SOURCE / protocol["inputs"]["experiment"]["path"]).read_bytes()
    )
    training_widths = [row["changes"][0]["width_m"] for row in training["candidates"]]
    evaluation_widths = [
        row["changes"][0]["width_m"] for row in evaluation["candidates"]
    ]
    assert training_widths == [0.32, 0.36, 0.40, 0.48, 0.52, 0.56]
    assert evaluation_widths == [
        0.33,
        0.35,
        0.37,
        0.39,
        0.41,
        0.43,
        0.45,
        0.47,
        0.49,
        0.51,
        0.53,
        0.55,
    ]
    assert set(training_widths + [0.44]).isdisjoint(evaluation_widths + [0.50])


def test_source_package_must_be_from_execution_checkout(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="lacks the structural_analysis package"):
        runner._require_runtime_source(tmp_path)
    runner._require_runtime_source(SOURCE)


def test_plan_and_six_inputs_are_frozen_before_training_and_search(
    committed_checkout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, packet = committed_checkout
    monkeypatch.setattr(runner, "_require_runtime_source", lambda _repo: None)
    calls = []

    def decoded(frozen):
        calls.append("decode")
        assert not frozen["output"].exists()
        return {
            "training": {},
            "search": {},
            "training_candidate_ids": ["baseline", "w32"],
            "evaluation_candidate_ids": ["baseline", "w33"],
            "training_model_identities": ["train-base", "train-32"],
            "evaluation_model_identities": ["eval-base", "eval-33"],
            "context_hash": "sha256:" + "a" * 64,
            "learning_plan": {"fit_method": "svd-ridge-unpenalized-intercept.v2"},
        }

    def train(_study, frozen):
        calls.append("train")
        outer = json.loads((packet / "plan.json").read_bytes())
        assert outer["protocol_commit"] == commit
        assert outer["schedule"] == list(runner.SCHEDULE)
        assert outer["source_checkout_clean"] is True
        assert outer["training_candidate_ids"] == ["baseline", "w32"]
        assert outer["evaluation_candidate_ids"] == ["baseline", "w33"]
        assert outer["floor_selection_provenance"] == runner.FLOOR_PROVENANCE
        assert outer["plan_hash"] == runner._sha(
            runner._canonical(
                {key: value for key, value in outer.items() if key != "plan_hash"}
            )
        )
        assert (packet / "training-started.json").exists()
        assert not (packet / "search-started.json").exists()
        for role in runner.ROLES:
            assert (packet / "inputs" / f"{role}.json").read_bytes() == (
                frozen["input_blobs"][role]
            )
        return SimpleNamespace(policy_hash="sha256:" + "b" * 64), {}

    def checked_training(*_arguments):
        calls.append("check_train")
        return (
            {"policy_hash": "sha256:" + "b" * 64},
            {"report_hash": "sha256:" + "c" * 64, "sample_count": 2},
            "sha256:" + "d" * 64,
            "sha256:" + "e" * 64,
            "sha256:" + "f" * 64,
        )

    def search(_study, _frozen, binding, _policy, _training):
        calls.append("search")
        assert set(binding["input_sha256"]) == set(runner.ROLES)
        assert (
            json.loads((packet / "training-outcome.json").read_bytes())[
                "unknown_work_until_outcome"
            ]
            is False
        )
        assert (packet / "search-started.json").exists()
        return {}

    def checked_search(*_arguments):
        calls.append("check_search")
        return (
            {"plan_hash": "sha256:" + "1" * 64},
            {"report_hash": "sha256:" + "2" * 64},
            "sha256:" + "3" * 64,
            "sha256:" + "4" * 64,
        )

    monkeypatch.setattr(runner, "_decoded_inputs", decoded)
    monkeypatch.setattr(runner, "_execute_training", train)
    monkeypatch.setattr(runner, "_checked_training", checked_training)
    monkeypatch.setattr(runner, "_execute_search", search)
    monkeypatch.setattr(runner, "_checked_search", checked_search)
    receipt = runner.run_packet(repo, PROTOCOL, commit, packet)
    assert calls == ["decode", "train", "check_train", "search", "check_search"]
    assert receipt["learned_policy_used"] is True
    assert receipt["ai_benefit_claimed"] is False
    assert receipt["training_report_hash"] == "sha256:" + "c" * 64
    assert receipt["unknown_execution_work"] is False
    assert type(receipt["runner_wall_ns"]) is int
    assert receipt["runner_wall_ns"] >= 0
    assert type(receipt["runner_process_cpu_ns"]) is int
    assert receipt["runner_process_cpu_ns"] >= 0
    assert "preflight" in receipt["runner_timing_scope"]
    assert receipt["report_hash"] == runner._sha(
        runner._canonical(
            {key: value for key, value in receipt.items() if key != "report_hash"}
        )
    )
    inventory = json.loads((packet / "inventory.json").read_bytes())
    assert inventory["inventory_sha256"] == runner._sha(
        runner._canonical(inventory["files"])
    )
    for relative, size, digest in inventory["files"]:
        raw = (packet / relative).read_bytes()
        assert size == len(raw)
        assert digest == runner._sha(raw)
    for phase in ("training", "search"):
        outcome = json.loads((packet / f"{phase}-outcome.json").read_bytes())
        assert outcome["unknown_work_until_outcome"] is False
        assert type(outcome["wall_ns"]) is int and outcome["wall_ns"] >= 0
        assert type(outcome["process_cpu_ns"]) is int and outcome["process_cpu_ns"] >= 0
        assert outcome["timing_scope"].startswith("start_marker_")


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_dirty_source_rejected_before_output_or_work(
    committed_checkout,
    monkeypatch: pytest.MonkeyPatch,
    dirty_kind: str,
) -> None:
    repo, commit, packet = committed_checkout
    path = repo / PROTOCOL if dirty_kind == "tracked" else repo / "unexpected.txt"
    path.write_bytes(path.read_bytes() + b" " if path.exists() else b"dirty")
    monkeypatch.setattr(
        runner, "_decoded_inputs", lambda *_: pytest.fail("work reached")
    )
    with pytest.raises(ValueError, match="clean source checkout"):
        runner.run_packet(repo, PROTOCOL, commit, packet)
    assert not packet.exists()


def test_changed_committed_input_rejected_before_output_or_work(
    committed_checkout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, protocol_commit, packet = committed_checkout
    protocol = json.loads((repo / PROTOCOL).read_bytes())
    request = repo / protocol["inputs"]["request"]["path"]
    request.write_bytes(request.read_bytes() + b" ")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "mutate frozen request")
    monkeypatch.setattr(
        runner, "_decoded_inputs", lambda *_: pytest.fail("work reached")
    )
    with pytest.raises(ValueError, match="request input differs"):
        runner.run_packet(repo, PROTOCOL, protocol_commit, packet)
    assert not packet.exists()


def test_nonancestor_protocol_rejected_before_output_or_work(
    committed_checkout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _, packet = committed_checkout
    branch = git(repo, "branch", "--show-current")
    git(repo, "checkout", "-qb", "side")
    git(repo, "commit", "--allow-empty", "-qm", "side")
    side = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", branch)
    monkeypatch.setattr(
        runner, "_decoded_inputs", lambda *_: pytest.fail("work reached")
    )
    with pytest.raises(ValueError, match="not an ancestor"):
        runner.run_packet(repo, PROTOCOL, side, packet)
    assert not packet.exists()


def test_interrupted_training_retains_unknown_work_and_no_search(
    committed_checkout,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, commit, packet = committed_checkout
    monkeypatch.setattr(runner, "_require_runtime_source", lambda _repo: None)
    monkeypatch.setattr(
        runner,
        "_decoded_inputs",
        lambda *_: {
            "training": {},
            "search": {},
            "training_candidate_ids": [],
            "evaluation_candidate_ids": [],
            "training_model_identities": [],
            "evaluation_model_identities": [],
            "context_hash": "test",
            "learning_plan": {},
        },
    )

    def interrupted(*_arguments):
        raise RuntimeError("training stopped")

    monkeypatch.setattr(runner, "_execute_training", interrupted)
    monkeypatch.setattr(
        runner, "_execute_search", lambda *_: pytest.fail("search reached")
    )
    with pytest.raises(RuntimeError, match="training stopped"):
        runner.run_packet(repo, PROTOCOL, commit, packet)
    outcome = json.loads((packet / "training-outcome.json").read_bytes())
    assert outcome["unknown_work_until_outcome"] is True
    assert outcome["status"] == "raised"
    assert type(outcome["wall_ns"]) is int and outcome["wall_ns"] >= 0
    assert type(outcome["process_cpu_ns"]) is int
    assert outcome["process_cpu_ns"] >= 0
    assert not (packet / "search-started.json").exists()
    assert not (packet / "runner.json").exists()
    assert not (packet / "inventory.json").exists()
