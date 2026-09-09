"""Actual long histories, full replay, original recovery and failure ledgers."""

from pathlib import Path

import pytest

from structural_analysis.api import rc_fiber_frame_direct_control as bounded
from structural_analysis.execution import rc_fiber_history_archive as archive
from structural_analysis.io.neutral.loader import load_neutral_json


REVISION = "1" * 40  # Explicit fixture attestation, not a real source execution claim.
TARGETS = (-1e-6, -2e-6, -1e-6, -3e-6)


@pytest.fixture(scope="module")
def model():
    return load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )


def _run(model, root, targets=TARGETS, **options):
    return archive.run_rc_fiber_history_archive(
        model,
        targets,
        control_global_dof=4,
        output_directory=root,
        source_revision=REVISION,
        allow_reversals=True,
        maximum_reversals=4,
        **options,
    )


def test_each_archived_response_and_terminal_match_original_bounded_api(
    model, tmp_path
):
    original = bounded.analyze_bounded_rc_fiber_direct_control(
        model,
        TARGETS,
        control_global_dof=4,
        allow_reversals=True,
        maximum_reversals=4,
    ).to_dict()
    assert original["status"] == "ready"
    result = _run(model, tmp_path / "archive")
    assert result["complete"] and result["checkpoint_epoch"] == 4
    responses = [
        archive._read(path)["response"]
        for path in sorted((tmp_path / "archive/accepted").iterdir())
    ]
    assert archive._json(responses) == archive._json(original["response_history"])
    work = archive.inspect_rc_fiber_history_archive_work(tmp_path / "archive")
    assert work["reserved_step_invocations"] == 4
    assert work["reported_work"]["suffix"]["attempted_step_count"] == 4
    assert work["unavailable_core_invocations"] == []
    assert work["unavailable_recovery_outcomes"] == []


def test_300_targets_resume_with_exact_full_prefix_and_no_epoch_reset(model, tmp_path):
    targets = tuple(-(i + 1) * 1e-7 for i in range(300))
    complete_root, resumed_root = tmp_path / "complete", tmp_path / "resumed"
    complete = _run(model, complete_root, targets)
    prefix = _run(model, resumed_root, targets, stop_after=123)
    assert prefix["status"] == "paused" and prefix["checkpoint_epoch"] == 123
    resumed = _run(model, resumed_root, targets, resume=True)
    assert complete["complete"] and resumed["complete"]
    assert complete["checkpoint_epoch"] == resumed["checkpoint_epoch"] == 300
    assert complete["checkpoint_sha256"] == resumed["checkpoint_sha256"]
    for i in range(300):
        full = archive._read(complete_root / "accepted" / f"{i:05d}.json")
        replayed = archive._read(resumed_root / "accepted" / f"{i:05d}.json")
        assert archive._json(full["response"]) == archive._json(replayed["response"])
        assert full["response"]["epoch"] == i + 1
    work = archive.inspect_rc_fiber_history_archive_work(resumed_root)
    assert work["reserved_step_invocations"] == 423
    assert work["reported_work"]["suffix"]["attempted_step_count"] == 300
    assert work["reported_work"]["prefix_replay"]["attempted_step_count"] == 123
    assert work["unavailable_core_invocations"] == []


def test_changed_complete_request_rejects_before_prefix_solves(
    model, tmp_path, monkeypatch
):
    root = tmp_path / "archive"
    _run(model, root, stop_after=1)
    monkeypatch.setattr(
        archive, "_execute_raw", lambda *a, **k: pytest.fail("unexpected solve")
    )
    with pytest.raises(ValueError, match="identity changed"):
        _run(model, root, (*TARGETS[:-1], -4e-6), resume=True)


def test_resealed_response_tampering_fails_real_replay_before_new_acceptance(
    model, tmp_path
):
    root = tmp_path / "archive"
    _run(model, root, stop_after=1)
    path = root / "accepted/00000.json"
    record = archive._read(path)
    record.pop("artifact_hash")
    record["response"]["load_factor"] += 1.0
    # Deliberately corrupt this test-owned artifact, including its public hash.
    path.write_bytes(
        archive._json(record | {"artifact_hash": archive._hash(archive._json(record))})
    )
    result = _run(model, root, resume=True)
    assert result["status"] == "blocked"
    assert result["failure"]["stage"] == "recovery_or_prefix_verification"
    assert result["verified_target_count"] == 0
    assert len(list((root / "accepted").iterdir())) == 1


def test_recovery_failure_keeps_original_solver_work_and_last_verified_state(
    model, tmp_path, monkeypatch
):
    root = tmp_path / "archive"
    recover = archive._recover_step

    def fail_second(*args, **kwargs):
        if args[1].epoch == 1:
            raise ValueError("injected recovery failure")
        return recover(*args, **kwargs)

    monkeypatch.setattr(archive, "_recover_step", fail_second)
    result = _run(model, root)
    assert result["status"] == "blocked" and result["checkpoint_epoch"] == 1
    work = archive.inspect_rc_fiber_history_archive_work(root)
    assert work["reported_work"]["suffix"]["attempted_step_count"] == 2
    assert work["unavailable_core_invocations"] == []
    assert len(work["unavailable_recovery_outcomes"]) == 1
    monkeypatch.setattr(archive, "_recover_step", recover)
    result = _run(model, root, resume=True)
    assert result["complete"]
    total = archive.inspect_rc_fiber_history_archive_work(root)
    assert total["reserved_step_invocations"] == 6  # Failed recovery is still charged.
    assert len(total["unavailable_recovery_outcomes"]) == 1


def test_interruption_after_reservation_remains_unknown_in_later_total(
    model, tmp_path, monkeypatch
):
    root = tmp_path / "archive"
    original = archive._execute_raw

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(archive, "_execute_raw", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _run(model, root)
    work = archive.inspect_rc_fiber_history_archive_work(root)
    assert len(work["unavailable_core_invocations"]) == 1
    assert len(work["runs_without_terminal_record"]) == 1
    monkeypatch.setattr(archive, "_execute_raw", original)
    assert _run(model, root, resume=True)["complete"]
    total = archive.inspect_rc_fiber_history_archive_work(root)
    assert total["reserved_step_invocations"] == 5
    assert len(total["unavailable_core_invocations"]) == 1


def test_original_255_target_api_limit_is_not_silently_changed(model):
    with pytest.raises(ValueError, match="maximum_targets"):
        bounded.analyze_bounded_rc_fiber_direct_control(
            model, (-1e-6,), control_global_dof=4, maximum_targets=300
        )


def test_interrupted_unpublished_accepted_file_is_retained_but_not_promoted(
    model, tmp_path
):
    root = tmp_path / "archive"
    _run(model, root, stop_after=1)
    pending = root / "accepted" / (".pending-" + "0" * 32)
    pending.write_bytes(b"unfinished publication")
    assert _run(model, root, resume=True)["complete"]
    assert pending.read_bytes() == b"unfinished publication"
    work = archive.inspect_rc_fiber_history_archive_work(root)
    assert work["unpublished_accepted_temporaries"] == [pending.name]
    assert work["preflight_wall_ns"] > 0


def test_publishing_never_replaces_an_accepted_artifact(tmp_path):
    path = tmp_path / "accepted.json"
    original = archive._publish(path, {"test": "original"})
    with pytest.raises(FileExistsError):
        archive._publish(path, {"test": "replacement"})
    assert archive._read(path) == original
    assert list(tmp_path.glob(".pending-*")) == []


@pytest.mark.parametrize("targets", [(float("nan"),), (-1e-6, -1e-6), ()])
def test_invalid_complete_sequence_rejects_before_core_and_archive_creation(
    model, tmp_path, monkeypatch, targets
):
    root = tmp_path / "archive"
    monkeypatch.setattr(
        archive, "_execute_raw", lambda *a, **k: pytest.fail("unexpected solve")
    )
    with pytest.raises(ValueError):
        _run(model, root, targets)
    assert not root.exists()
