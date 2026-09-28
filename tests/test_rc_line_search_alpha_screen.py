from __future__ import annotations

import copy
import hashlib
import itertools
import json

import pytest

from scripts import screen_rc_line_search_alpha as screen
from scripts.screen_rc_line_search_alpha import (
    FEATURE_NAMES,
    TraceError,
    _cross_validate,
    _line_rows,
    _predict_skip,
)


def _step(*, accepted_index: int, trial_residual: float = 0.4):
    alphas = [1.0, 0.5, 0.25][: accepted_index + 1]
    attempts = [
        {
            "alpha": alpha,
            "accepted": index == accepted_index,
            "trial_relative_residual": (
                trial_residual if index == accepted_index else 0.6
            ),
        }
        for index, alpha in enumerate(alphas)
    ]
    return {
        "trial_solution": {
            "convergence_history": [
                {
                    "iteration": 0,
                    "free_displacements_m": [0.1, 0.2],
                    "newton_increment_m": [0.01, -0.02],
                    "relative_residual": 0.5,
                    "line_search_attempt_count": len(attempts),
                    "line_search_alpha": alphas[-1],
                }
            ],
            "line_search_history": [
                {
                    "iteration": 0,
                    "starting_free_displacements_m": [0.1, 0.2],
                    "newton_increment_m": [0.01, -0.02],
                    "attempt_count": len(attempts),
                    "selected_alpha": alphas[-1],
                    "attempts": attempts,
                }
            ],
        },
    }


def _rows(step):
    return _line_rows(
        step,
        {"target_m": -0.002, "accepted_targets_m": [0.0, -0.001]},
        case_id="train-a-amp050",
        target_index=1,
        step_path="step.json",
        step_sha256="abc",
        context_path="context.json",
        context_sha256="def",
    )


def test_extracts_only_pretrial_features_and_first_accepted_alpha():
    original = _step(accepted_index=1)
    first = _rows(original)
    changed_trial_result = copy.deepcopy(original)
    changed_trial_result["trial_solution"]["line_search_history"][0]["attempts"][1][
        "trial_relative_residual"
    ] = 0.0001
    second = _rows(changed_trial_result)
    assert len(first) == 1
    assert first[0]["features"] == second[0]["features"]
    assert len(first[0]["features"]) == len(FEATURE_NAMES)
    assert first[0]["first_accepted_index"] == 1
    assert first[0]["observed_failed_trial_count"] == 1


def test_missing_or_nonprefix_trials_do_not_create_labels():
    missing = _step(accepted_index=0)
    missing["trial_solution"]["line_search_history"][0].pop("attempts")
    with pytest.raises(TraceError, match="trial record"):
        _rows(missing)

    nonprefix = _step(accepted_index=1)
    nonprefix["trial_solution"]["line_search_history"][0]["attempts"][0]["alpha"] = 0.25
    with pytest.raises(TraceError, match="alpha prefix"):
        _rows(nonprefix)


def test_no_accepted_alpha_remains_unverified():
    blocked = _step(accepted_index=1)
    trial = blocked["trial_solution"]
    trial["line_search_history"][0]["attempts"][-1]["accepted"] = False
    trial["line_search_history"][0]["attempts"][-1]["trial_relative_residual"] = 0.6
    trial["line_search_history"][0]["selected_alpha"] = 0.0
    trial["convergence_history"][0]["line_search_alpha"] = 0.0
    row = _rows(blocked)[0]
    assert row["first_accepted_index"] is None
    assert row["observed_failed_trial_count"] == 2


@pytest.mark.parametrize("iterations", [(1, 0), (0, 0)])
def test_line_search_history_must_be_strictly_ordered(iterations):
    step = _step(accepted_index=0)
    trial = step["trial_solution"]
    second_line = copy.deepcopy(trial["line_search_history"][0])
    second_before = copy.deepcopy(trial["convergence_history"][0])
    second_line["iteration"] = 1
    second_before["iteration"] = 1
    trial["convergence_history"].append(second_before)
    trial["line_search_history"].append(second_line)
    for line, iteration in zip(trial["line_search_history"], iterations, strict=True):
        line["iteration"] = iteration
    with pytest.raises(TraceError, match="strictly increasing"):
        _rows(step)


@pytest.mark.parametrize(
    "accepted,trial_residual", [(False, 0.4), (True, 0.5), (True, 0.6)]
)
def test_trial_acceptance_must_match_strict_residual_decrease(accepted, trial_residual):
    step = _step(accepted_index=0)
    attempt = step["trial_solution"]["line_search_history"][0]["attempts"][0]
    attempt["accepted"] = accepted
    attempt["trial_relative_residual"] = trial_residual
    with pytest.raises(TraceError, match="strict residual decrease"):
        _rows(step)


def test_held_features_cannot_change_training_normalization():
    train = [
        {
            "features": [float(i), 0.0, 0.0, 0.0, 0.0],
            "first_accepted_index": 1,
            "case_id": "train-a-amp050",
            "target_index": i,
            "newton_iteration_index": 0,
        }
        for i in range(3)
    ]
    held = {"features": [1.0, 0.0, 0.0, 0.0, 0.0]}
    assert _predict_skip(train, held)[0] == 1
    held["features"][0] = 1000.0
    assert _predict_skip(train, held) == (0, "outside_training_range")


def test_group_split_excludes_every_held_case_and_counts_false_skip():
    rows = []
    for letter in "abcde":
        for amplitude in ("050", "100", "150"):
            rows.append(
                {
                    "case_id": f"train-{letter}-amp{amplitude}",
                    "target_index": 0,
                    "newton_iteration_index": 0,
                    "features": [1.0, 0.0, 0.0, 0.0, 0.0],
                    "first_accepted_index": 0 if letter == "e" else 1,
                }
            )
    folds, decision = _cross_validate(rows)
    assert len(folds) == 5
    for index, fold in enumerate(folds):
        assert fold["training_rows"] == 12
        assert fold["held_rows"] == 3
        assert all(
            case.startswith(f"train-{'abcde'[index]}-") for case in fold["held_cases"]
        )
    assert folds[4]["false_skips_unobserved_outcome"] == 3
    assert decision["supports_online_experiment_design"] is False


def test_packet_reader_rejects_linked_parent_before_read(tmp_path, monkeypatch):
    root = tmp_path / "packet"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    raw = b'{"value":1}'
    (outside / "data.json").write_bytes(raw)
    (root / "link").symlink_to(outside, target_is_directory=True)
    inventory = {
        "files": [
            {
                "path": "link/data.json",
                "byte_length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ]
    }
    inventory_raw = json.dumps(inventory).encode()
    (root / "inventory.json").write_bytes(inventory_raw)
    monkeypatch.setattr(
        screen, "INVENTORY_SHA256", hashlib.sha256(inventory_raw).hexdigest()
    )
    with pytest.raises(TraceError, match="missing or linked"):
        screen.OriginalPacket(root).read("link/data.json")


def test_packet_reader_rejects_in_root_parent_link(tmp_path, monkeypatch):
    root = tmp_path / "packet"
    real = root / "real"
    real.mkdir(parents=True)
    raw = b'{"value":1}'
    (real / "data.json").write_bytes(raw)
    (root / "link").symlink_to(real, target_is_directory=True)
    inventory = {
        "files": [
            {
                "path": "link/data.json",
                "byte_length": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        ]
    }
    inventory_raw = json.dumps(inventory).encode()
    (root / "inventory.json").write_bytes(inventory_raw)
    monkeypatch.setattr(
        screen, "INVENTORY_SHA256", hashlib.sha256(inventory_raw).hexdigest()
    )
    with pytest.raises(TraceError, match="missing or linked original file"):
        screen.OriginalPacket(root).read("link/data.json")


def test_packet_reader_rejects_linked_inventory_before_read(tmp_path, monkeypatch):
    root = tmp_path / "packet"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_bytes(b'{"files":[]}')
    (root / "inventory.json").symlink_to(outside)
    monkeypatch.setattr(
        screen, "INVENTORY_SHA256", hashlib.sha256(outside.read_bytes()).hexdigest()
    )
    with pytest.raises(TraceError, match="missing or linked inventory file"):
        screen.OriginalPacket(root)


def test_packet_reader_rejects_linked_root_before_inventory_read(tmp_path, monkeypatch):
    real_root = tmp_path / "real"
    real_root.mkdir()
    inventory_raw = b'{"files":[]}'
    (real_root / "inventory.json").write_bytes(inventory_raw)
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    monkeypatch.setattr(
        screen, "INVENTORY_SHA256", hashlib.sha256(inventory_raw).hexdigest()
    )
    with pytest.raises(TraceError, match="missing or linked inventory file"):
        screen.OriginalPacket(linked_root)


def test_packet_reader_keeps_byte_hash_check(tmp_path, monkeypatch):
    root = tmp_path / "packet"
    root.mkdir()
    (root / "data.json").write_bytes(b'{"value":2}')
    expected = b'{"value":1}'
    inventory = {
        "files": [
            {
                "path": "data.json",
                "byte_length": len(expected),
                "sha256": hashlib.sha256(expected).hexdigest(),
            }
        ]
    }
    inventory_raw = json.dumps(inventory).encode()
    (root / "inventory.json").write_bytes(inventory_raw)
    monkeypatch.setattr(
        screen, "INVENTORY_SHA256", hashlib.sha256(inventory_raw).hexdigest()
    )
    with pytest.raises(TraceError, match="original bytes differ from inventory"):
        screen.OriginalPacket(root).read("data.json")


def test_unattempted_target_survives_in_blocked_report(monkeypatch, tmp_path):
    records = {
        "study/plan.json": {
            "source_revision": screen.SOURCE_REVISION,
            "groups": [list(group) for group in screen.GROUPS],
            "ridge_grid": list(screen.RIDGES),
            "repetitions": 3,
            "reserved_evaluation_executed": False,
        }
    }
    cases = [case for group in screen.GROUPS for case in group]
    for index, (case, ridge, repeat) in enumerate(
        itertools.product(cases, screen.RIDGES, screen.REPETITIONS)
    ):
        prefix = f"study/selection/fold-{index:04d}"
        request_body = {
            "targets_m": [0.1],
            "solver_config": {"newton": {"line_search_alphas": list(screen.ALPHAS)}},
        }
        request = {
            "source_revision": screen.SOURCE_REVISION,
            "request": request_body,
            "compiled_problem_contract_hash": "model",
        }
        entries = (
            []
            if index == 0
            else [{"target_index": 0, "target_m": 0.1, "invocations": []}]
        )
        path = {
            "entries": entries,
            "status": "complete",
            "failure": None,
            "accepted_target_count": 1,
        }
        path["path_hash"] = "sha256:" + screen._hash(screen._json_bytes(path))
        comparison = {
            "source_revision": screen.SOURCE_REVISION,
            "request": request_body,
            "arms": {"secant": {"path_hash": path["path_hash"]}},
            "all_execution_work_reported": True,
            "reference_repeat_exact": True,
            "comparisons": {"secant": {"full_history_pass": True}},
        }
        comparison["report_hash"] = "sha256:" + screen._hash(
            screen._json_bytes(comparison)
        )
        records[prefix + "-outcome.json"] = {
            "withheld_training_case": case,
            "ridge": ridge,
            "repetition_index": repeat,
            "status": "completed",
            "report_hash": comparison["report_hash"],
        }
        records[prefix + "/request.json"] = request
        records[prefix + "/comparison.json"] = comparison
        records[prefix + "/secant/path.json"] = path
        if entries:
            records[prefix + "/secant/000-context.json"] = {
                "target_m": 0.1,
                "problem_contract_hash": "model",
            }

    class FakePacket:
        def __init__(self, root):
            self.consumed = set()

        def read(self, relative):
            self.consumed.add(relative)
            value = copy.deepcopy(records[relative])
            return value, screen._hash(screen._json_bytes(value))

    monkeypatch.setattr(screen, "OriginalPacket", FakePacket)
    report = screen.screen_packet(tmp_path)
    assert report["status"] == "blocked_original_work_or_repeat_identity"
    assert "1 unattempted targets" in report["fold_issues"][0]["issues"]
    assert report["screen_decision"]["supports_online_experiment_design"] is False
