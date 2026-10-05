from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math

import pytest

from scripts import screen_rc_line_search_alpha as screen
from scripts.screen_rc_line_search_alpha import (
    FEATURE_NAMES,
    TraceError,
    _cross_validate,
    _line_rows,
    _predict_skip,
)


def _step(*, accepted_index: int, trial_residual_kn: float = 0.8):
    alphas = [1.0, 0.5, 0.25][: accepted_index + 1]
    attempts = [
        {
            "alpha": alpha,
            "accepted": index == accepted_index,
            "trial_residual_kn": [
                trial_residual_kn if index == accepted_index else 1.2,
                0.1,
            ],
            "trial_relative_residual": (
                trial_residual_kn if index == accepted_index else 1.2
            )
            / 2.0,
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
                    "residual_kn": [1.0, -0.2],
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
    ] = 0.05
    changed_trial_result["trial_solution"]["line_search_history"][0]["attempts"][1][
        "trial_residual_kn"
    ] = [0.1, 0.02]
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
    trial["line_search_history"][0]["attempts"][-1]["trial_residual_kn"] = [1.2, 0.1]
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
    "accepted,trial_residual_kn", [(False, 0.8), (True, 1.0), (True, 1.2)]
)
def test_trial_acceptance_must_match_strict_raw_residual_decrease(
    accepted, trial_residual_kn
):
    step = _step(accepted_index=0)
    attempt = step["trial_solution"]["line_search_history"][0]["attempts"][0]
    attempt["accepted"] = accepted
    attempt["trial_residual_kn"] = [trial_residual_kn, 0.1]
    attempt["trial_relative_residual"] = trial_residual_kn / 2.0
    with pytest.raises(TraceError, match="strict raw residual decrease"):
        _rows(step)


def test_raw_residual_decrease_survives_normalization_rounding():
    step = _step(accepted_index=0)
    before = step["trial_solution"]["convergence_history"][0]
    attempt = step["trial_solution"]["line_search_history"][0]["attempts"][0]
    raw_trial = math.nextafter(1.0, 0.0)
    before["relative_residual"] = 1.0 / 3.0
    attempt["trial_residual_kn"] = [raw_trial, 0.1]
    attempt["trial_relative_residual"] = raw_trial / 3.0
    assert attempt["trial_relative_residual"] == before["relative_residual"]
    assert _rows(step)[0]["first_accepted_index"] == 0


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


@pytest.mark.parametrize(
    "failure_code",
    [
        "unattempted_targets", "missing_invocation", "multiple_invocations",
        "unknown_work", "nonreturned_invocation", "noncommitted_invocation",
        "unverified_trial_history", "incomplete_physical_work_comparison",
    ],
)
def test_original_failures_survive_in_blocked_report(monkeypatch, tmp_path, failure_code):
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

    if failure_code != "unattempted_targets":
        prefix = "study/selection/fold-0000"
        path = records[prefix + "/secant/path.json"]
        entry = {"target_index": 0, "target_m": 0.1, "invocations": [], "parent_hash": "parent"}
        path["entries"] = [entry]
        records[prefix + "/secant/000-context.json"] = {
            "target_m": 0.1, "problem_contract_hash": "model", "accepted_targets_m": [0.0],
        }
        if failure_code != "missing_invocation":
            count = 2 if failure_code == "multiple_invocations" else 1
            for ordinal in range(1, count + 1):
                invocation = {
                    "ordinal": ordinal, "status": "returned", "committed": True,
                    "unknown_work": False,
                }
                step = _step(accepted_index=1)
                step.update({
                    "parent_checkpoint": {"state_hash": "parent"},
                    "metrics": {"target_control_displacement_m": 0.1}, "committed": True,
                })
                if failure_code == "unknown_work":
                    invocation["unknown_work"] = True
                elif failure_code == "nonreturned_invocation":
                    invocation["status"] = "unknown"
                elif failure_code == "noncommitted_invocation":
                    invocation["committed"] = False
                elif failure_code == "unverified_trial_history":
                    step["trial_solution"]["line_search_history"][0].pop("attempts")
                entry["invocations"].append(invocation)
                records[f"{prefix}/secant/000-{ordinal}-outcome.json"] = invocation
                if invocation["status"] == "returned":
                    records[f"{prefix}/secant/000-{ordinal}-step.json"] = step
        comparison = records[prefix + "/comparison.json"]
        if failure_code == "incomplete_physical_work_comparison":
            comparison["all_execution_work_reported"] = False
        path.pop("path_hash")
        path["path_hash"] = "sha256:" + screen._hash(screen._json_bytes(path))
        comparison["arms"]["secant"]["path_hash"] = path["path_hash"]
        comparison.pop("report_hash")
        comparison["report_hash"] = "sha256:" + screen._hash(screen._json_bytes(comparison))
        records[prefix + "-outcome.json"]["report_hash"] = comparison["report_hash"]

    class FakePacket:
        def __init__(self, root):
            self.consumed = set()

        def read(self, relative):
            assert relative.startswith(("study/plan.json", "study/selection/"))
            self.consumed.add(relative)
            value = copy.deepcopy(records[relative])
            return value, screen._hash(screen._json_bytes(value))

    monkeypatch.setattr(screen, "OriginalPacket", FakePacket)
    report = screen.screen_packet(tmp_path)
    assert report["status"] == "blocked_original_work_or_repeat_identity"
    if failure_code == "unattempted_targets":
        assert "1 unattempted targets" in report["fold_issues"][0]["issues"]
    assert failure_code in {row["code"] for row in report["fold_issues"][0]["failures"]}
    assert report["diagnostics"]["failure_counts"][failure_code] >= 1
    assert report["diagnostics"]["classification"] == "blocked_original_evidence"
    assert report["screen_decision"]["supports_online_experiment_design"] is False
    assert report["group_held_out_screen"] == []
    assert report["solver_calls"] == report["reserved_cases_read"] == 0
    screen._self_hash(report, "report_hash")


def test_diagnostic_failure_codes_preserve_unknown_work_and_repeat_boundaries():
    report = {
        "status": "blocked_original_work_or_repeat_identity",
        "fold_issues": [{"failures": [
            {"code": "unknown_work", "target_index": 0, "ordinal": 1},
            {"code": "unknown_work", "target_index": 1, "ordinal": 1},
            {"code": "nonreturned_invocation", "target_index": 1, "ordinal": 1},
        ]}],
        "repeat_mismatches": [{"case_id": "train-a-amp050"}],
        "screen_decision": {"supports_online_experiment_design": False},
    }
    before = copy.deepcopy(report)
    diagnostics = screen._diagnostics(report)
    assert report == before
    assert diagnostics["classification"] == "blocked_original_evidence"
    assert diagnostics["failure_counts"] == {
        "unknown_work": 2, "nonreturned_invocation": 1, "repeat_identity_mismatch": 1,
    }
    assert "not measured time savings" in diagnostics["boundary"]


@pytest.mark.parametrize(
    "support,false_skips,classification",
    [
        (True, 0, "offline_design_support_only"),
        (False, 1, "false_skip_gate_failed"),
        (False, 0, "insufficient_group_support"),
    ],
)
def test_diagnostics_describe_existing_decision_without_promoting_it(
    support, false_skips, classification
):
    report = {
        "status": "complete", "fold_issues": [], "repeat_mismatches": [],
        "screen_decision": {
            "supports_online_experiment_design": support, "false_skips": false_skips,
        },
    }
    diagnostics = screen._diagnostics(report)
    assert diagnostics["classification"] == classification
    assert diagnostics["failure_counts"] == {}
    assert "Zero solver calls" in diagnostics["boundary"]
    if support:
        assert "no online result is verified" in diagnostics["summary"]


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{', b'"\xff"'])
def test_invalid_json_has_stable_failure_code(data):
    with pytest.raises(TraceError) as failure:
        screen._strict_json(data)
    assert failure.value.code == "invalid_json"


def test_content_binding_failure_has_stable_code():
    with pytest.raises(TraceError) as failure:
        screen._self_hash({"value": 1, "report_hash": "sha256:wrong"}, "report_hash")
    assert failure.value.code == "content_binding_failed"


def test_cli_rejected_input_is_json_and_creates_no_report(tmp_path, monkeypatch, capsys):
    output = tmp_path / "uncreated" / "report.json"
    monkeypatch.setattr(
        screen.sys, "argv", ["screen", str(tmp_path / "missing"), str(output)]
    )
    assert screen.main() == 2
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["status"] == "rejected_input"
    assert record["failure_code"] == "unsafe_or_missing_input"
    assert record["solver_calls"] == 0
    assert "screen_decision" not in record
    assert "no screen decision" in captured.err
    assert not output.parent.exists()


def test_cli_does_not_overwrite_existing_report(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    output.write_text("existing report")
    monkeypatch.setattr(screen.sys, "argv", ["screen", str(tmp_path), str(output)])
    monkeypatch.setattr(screen, "screen_packet", lambda root: {})
    with pytest.raises(FileExistsError):
        screen.main()
    assert output.read_text() == "existing report"


def test_packet_reader_rejects_fifo_without_blocking(tmp_path):
    fifo = tmp_path / "inventory.json"
    screen.os.mkfifo(fifo)
    with pytest.raises(TraceError) as failure:
        screen.OriginalPacket(tmp_path)
    assert failure.value.code == "unsafe_or_missing_input"


def test_packet_reader_rejects_parent_traversal_before_open(tmp_path, monkeypatch):
    def forbidden_open(*args, **kwargs):
        pytest.fail("traversal must be rejected before opening any path")

    monkeypatch.setattr(screen.os, "open", forbidden_open)
    with pytest.raises(TraceError) as failure:
        screen._read_unlinked_regular_file(tmp_path, screen.Path("../data.json"), "input")
    assert failure.value.code == "unsafe_or_missing_input"


def test_complete_alpha_prefix_without_acceptance_stays_unknown():
    step = _step(accepted_index=0)
    line = step["trial_solution"]["line_search_history"][0]
    line["attempts"] = [
        {"alpha": alpha, "accepted": False, "trial_residual_kn": [1.0, 0.1],
         "trial_relative_residual": 0.5}
        for alpha in screen.ALPHAS
    ]
    line["attempt_count"] = len(screen.ALPHAS)
    line["selected_alpha"] = 0.0
    before = step["trial_solution"]["convergence_history"][0]
    before["line_search_attempt_count"] = len(screen.ALPHAS)
    before["line_search_alpha"] = 0.0
    row = _rows(step)[0]
    assert row["first_accepted_index"] is None
    assert row["trial_count"] == len(screen.ALPHAS)
    line["attempts"].append(copy.deepcopy(line["attempts"][-1]))
    line["attempt_count"] += 1
    before["line_search_attempt_count"] += 1
    with pytest.raises(TraceError, match="bounded alpha-trial"):
        _rows(step)


def test_cli_rejection_does_not_echo_private_or_multiline_input(tmp_path, monkeypatch, capsys):
    secret = "private-packet-key\nsecond-line"

    def rejected(root):
        raise TraceError(f"duplicate JSON key: {secret}", code="invalid_json")

    output = tmp_path / "report.json"
    monkeypatch.setattr(screen, "screen_packet", rejected)
    monkeypatch.setattr(screen.sys, "argv", ["screen", str(tmp_path / secret), str(output)])
    assert screen.main() == 2
    captured = capsys.readouterr()
    assert "private-packet-key" not in captured.out + captured.err
    assert "second-line" not in captured.out + captured.err
    assert json.loads(captured.out)["failure_code"] == "invalid_json"
    assert len(captured.out.splitlines()) == 1
    assert not output.exists()


def test_cli_complete_report_keeps_json_stdout_and_human_stderr(tmp_path, monkeypatch, capsys):
    report = {
        "status": "complete", "fold_issues": [], "repeat_mismatches": [],
        "observed_line_search_events": 7, "observed_first_alpha_failures": 2,
        "screen_decision": {"supports_online_experiment_design": False, "false_skips": 1},
    }
    report["diagnostics"] = screen._diagnostics(report)
    output = tmp_path / "report.json"
    monkeypatch.setattr(screen, "screen_packet", lambda root: report)
    monkeypatch.setattr(screen.sys, "argv", ["screen", str(tmp_path), str(output)])
    assert screen.main() == 0
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["events"] == 7
    assert record["first_alpha_failures"] == 2
    assert record["screen_decision"] == report["screen_decision"]
    assert "false skips were observed" in captured.err
    assert "not measured time savings" in captured.err
    assert json.loads(output.read_text()) == report
