"""Real physical targets, snapshot isolation, and incomplete dataset behavior."""

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.ai.fiber_frame_warm_start_data import (
    FiberFrameWarmStartDataCase,
    FiberFrameWarmStartDataError,
    collect_fiber_frame_warm_start_data,
)
from structural_analysis.ai.fiber_frame_warm_start_learning import (
    train_fiber_frame_warm_start_policy,
)
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


_REVISION = "a" * 40
_EXAMPLE = (
    Path(__file__).resolve().parents[1]
    / "examples/public_rc_fiber_frame_cantilever.json"
)


def _model(index: int = 0, *, unsupported: bool = False, load_kn: float = -1.0):
    payload = json.loads(_EXAMPLE.read_text(encoding="utf-8"))
    payload["metadata"]["case_id"] = f"research-{index}"
    payload["sections"][0]["width_m"] = 0.4 + index * 0.001
    payload["loads"][0]["components"]["FY"] = load_kn
    if unsupported:
        payload["elements"][0]["release_i"] = ["RZ"]
    return load_neutral_json_bytes(json.dumps(payload).encode())


def _case(index: int, split: str, *, unsupported: bool = False):
    return FiberFrameWarmStartDataCase(
        case_id=f"case-{index}",
        project_id=f"project-{index}",
        geometry_family_id=f"declared-geometry-{index}",
        load_history_id=f"history-{index}",
        split=split,
        model=_model(index, unsupported=unsupported),
        config=public_api.PublicRCFiberFrameConfig(load_steps=2),
    )


@pytest.fixture(scope="module")
def collected():
    cases = (_case(0, "train"), _case(1, "validation"), _case(2, "holdout"))
    actual_results = {}
    analyze = public_api.analyze_public_rc_fiber_frame

    def record_result(model, config):
        result = analyze(model, config)
        actual_results[model.canonical_model_checksum] = result
        return result

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(public_api, "analyze_public_rc_fiber_frame", record_result)
        result = collect_fiber_frame_warm_start_data(cases, source_revision=_REVISION)
    return cases, result, actual_results


def test_collects_real_accepted_targets_from_three_distinct_physical_cases(
    collected,
) -> None:
    cases, result, actual = collected
    report = result.to_dict()
    assert result.status == "ready", report["blockers"]
    assert report["dataset_complete"] is True
    assert report["sample_count"] == 6
    assert report["dataset_report"]["split_counts"] == {
        "train": 2,
        "validation": 2,
        "holdout": 2,
    }
    assert len({row["physical_model_identity_hash"] for row in report["cases"]}) == 3
    assert report["data_generation_wall_ns"] > 0
    assert all(row["validation_report"]["contract_pass"] for row in report["cases"])
    assert report["claim_boundary"]["split_labels_prove_independent_projects"] is False
    assert report["claim_boundary"]["external_provenance_verified"] is False
    assert report["claim_boundary"]["production_promotion_eligible"] is False
    for case in cases:
        physical = actual[case.model.canonical_model_checksum]
        assert physical.status == "ready"
        expected_chain = physical._checkpoint_chain
        assert expected_chain is not None
        case_rows = [
            row
            for row in report["sample_source_bindings"]
            if row["case_id"] == case.case_id
        ]
        assert [row["target_epoch"] for row in case_rows] == [1, 2]
        assert all(
            row["public_result_hash"] == physical.result_hash for row in case_rows
        )
        assert all(
            row["checkpoint_chain_hash"] == expected_chain.chain_hash
            for row in case_rows
        )
        assert case_rows[0]["previous_checkpoint_state_hash"] is None
        assert (
            case_rows[1]["previous_checkpoint_state_hash"]
            == expected_chain.root_checkpoint.state_hash
        )
        assert (
            case_rows[0]["target_checkpoint_state_hash"]
            == case_rows[1]["parent_checkpoint_state_hash"]
        )


def test_features_are_prior_state_only_and_actual_training_accepts_collected_targets(
    collected,
) -> None:
    _, result, _ = collected
    training = train_fiber_frame_warm_start_policy(result.samples)
    train_rows = [row for row in result.samples if row.split == "train"]
    first, second = train_rows
    assert first.runtime_input.previous_free_coordinates_m is None
    assert set(first.runtime_input.parent_free_coordinates_m) == {0.0}
    assert np.linalg.norm(first.accepted_target_free_coordinates_m) > 0
    assert (
        second.runtime_input.parent_free_coordinates_m
        == first.accepted_target_free_coordinates_m
    )
    assert (
        second.runtime_input.previous_free_coordinates_m
        == first.runtime_input.parent_free_coordinates_m
    )
    assert second.runtime_input.target_load_factor == 1.0
    proposal = training.policy.propose(first.runtime_input)
    assert proposal.ood is False
    np.testing.assert_allclose(
        proposal.free_coordinates_m,
        first.accepted_target_free_coordinates_m,
        atol=1.0e-8,
    )
    for row in result.samples:
        assert np.all(
            np.isfinite(training.policy.propose(row.runtime_input).free_coordinates_m)
        )


def test_case_model_snapshot_and_result_report_are_detached(collected) -> None:
    cases, result, _ = collected
    source = _model()
    case = FiberFrameWarmStartDataCase(
        "snapshot",
        "project-snapshot",
        "geometry-snapshot",
        "history-snapshot",
        "train",
        source,
        public_api.PublicRCFiberFrameConfig(load_steps=2),
    )
    checksum = case.model.canonical_model_checksum
    source.nodes[1]["coordinates"][0] = 500.0
    case.model.nodes[1]["coordinates"][0] = 600.0
    assert case.model.canonical_model_checksum == checksum
    report = result.to_dict()
    collection_hash = report["collection_hash"]
    report["cases"][0]["status"] = "tampered"
    report["samples"][0]["accepted_target_free_coordinates_m"][0] = 999.0
    assert result.to_dict()["collection_hash"] == collection_hash
    assert result.to_dict()["cases"][0]["status"] == "ready"
    assert cases[0].model.nodes[1]["coordinates"][0] == 3.0


def test_unsupported_case_is_retained_without_failed_prefix_targets() -> None:
    result = collect_fiber_frame_warm_start_data(
        [_case(8, "holdout", unsupported=True)], source_revision=_REVISION
    )
    report = result.to_dict()
    assert result.status == "blocked"
    assert result.samples == ()
    assert report["failed_case_count"] == 1
    assert report["cases"][0]["solver_executed"] is False
    assert report["cases"][0]["blockers"] == ["rc_fiber_frame_row_keys_invalid"]


def test_real_nonconvergent_case_retains_failure_without_targets() -> None:
    case = FiberFrameWarmStartDataCase(
        "nonconvergent",
        "nonconvergent",
        "nonconvergent",
        "nonconvergent",
        "train",
        _model(load_kn=-100.0),
        public_api.PublicRCFiberFrameConfig(load_steps=2, maximum_iterations=1),
    )
    result = collect_fiber_frame_warm_start_data([case], source_revision=_REVISION)
    report = result.to_dict()
    assert result.status == "blocked"
    assert result.samples == ()
    assert report["cases"][0]["solver_executed"] is True
    assert report["cases"][0]["sample_count"] == 0
    assert report["cases"][0]["validation_report"]["contract_pass"] is False


def test_collection_identity_excludes_elapsed_timing(collected, monkeypatch) -> None:
    cases, first, actual = collected
    monkeypatch.setattr(
        public_api,
        "analyze_public_rc_fiber_frame",
        lambda model, _config: actual[model.canonical_model_checksum],
    )
    second = collect_fiber_frame_warm_start_data(cases, source_revision=_REVISION)
    assert first.to_dict()["collection_hash"] == second.to_dict()["collection_hash"]
    assert tuple(row.sample_hash for row in first.samples) == tuple(
        row.sample_hash for row in second.samples
    )


def test_partial_and_exception_rows_preserve_successful_cases(
    collected, monkeypatch
) -> None:
    cases, _, actual = collected

    def known_or_failed(model, _config):
        if model.canonical_model_checksum in actual:
            return actual[model.canonical_model_checksum]
        raise ArithmeticError("synthetic failed solve")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", known_or_failed)
    result = collect_fiber_frame_warm_start_data(
        [cases[0], _case(9, "holdout")], source_revision=_REVISION
    )
    report = result.to_dict()
    assert result.status == "partial"
    assert report["dataset_complete"] is False
    assert len(result.samples) == 2
    assert report["cases"][1]["exception_type"] == "ArithmeticError"
    assert report["cases"][1]["sample_count"] == 0
    assert report["dataset_report"] is None
    assert "one_or_more_physical_cases_blocked" in report["blockers"]


def test_metadata_relabel_does_not_create_new_physical_holdout(
    collected, monkeypatch
) -> None:
    cases, _, actual = collected
    model = cases[0].model
    model.metadata["case_id"] = "relabeled-only"
    relabeled = FiberFrameWarmStartDataCase(
        "alias",
        "other-project",
        "other-geometry",
        "other-history",
        "holdout",
        model,
        cases[0].config,
    )
    # Real solve the relabeled model to preserve its own result/checkpoint bindings.
    solve = public_api.analyze_public_rc_fiber_frame

    def cached_or_real(model, config):
        return actual.get(model.canonical_model_checksum) or solve(model, config)

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", cached_or_real)
    result = collect_fiber_frame_warm_start_data(
        [cases[0], cases[1], relabeled], source_revision=_REVISION
    )
    report = result.to_dict()
    assert result.status == "blocked"
    assert report["failed_case_count"] == 0
    assert any(
        "split_leakage: model_identity_hash" in blocker
        for blocker in report["blockers"]
    )
    assert report["dataset_complete"] is False


@pytest.mark.parametrize("revision", ["abc1234", "A" * 40, "sha256:" + "a" * 64, None])
def test_invalid_source_revision_fails_before_execution(revision, monkeypatch) -> None:
    def forbidden(*_args):
        raise AssertionError("solver must not run")

    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", forbidden)
    with pytest.raises(FiberFrameWarmStartDataError, match="full lowercase Git SHA"):
        collect_fiber_frame_warm_start_data(
            [_case(0, "train")], source_revision=revision
        )


def test_duplicate_case_ids_and_nonfinite_model_are_rejected() -> None:
    case = _case(0, "train")
    with pytest.raises(FiberFrameWarmStartDataError, match="duplicate case_id"):
        collect_fiber_frame_warm_start_data([case, case], source_revision=_REVISION)
    model = _model()
    model.sections[0]["width_m"] = float("nan")
    with pytest.raises(FiberFrameWarmStartDataError, match="finite JSON model"):
        FiberFrameWarmStartDataCase(
            "bad", "bad", "bad", "bad", "train", model, case.config
        )


def test_invalid_ready_envelope_cannot_supply_targets(collected, monkeypatch) -> None:
    cases, _, actual = collected
    tampered = replace(
        actual[cases[0].model.canonical_model_checksum],
        result_hash="sha256:" + "0" * 64,
    )
    monkeypatch.setattr(
        public_api, "analyze_public_rc_fiber_frame", lambda *_args: tampered
    )
    result = collect_fiber_frame_warm_start_data([cases[0]], source_revision=_REVISION)
    assert result.samples == ()
    assert result.to_dict()["cases"][0]["blockers"] == ["physical_collection_failed"]


def test_valid_result_for_another_model_cannot_supply_mislabeled_targets(
    collected, monkeypatch
) -> None:
    cases, _, actual = collected
    other_model_result = actual[cases[0].model.canonical_model_checksum]
    monkeypatch.setattr(
        public_api, "analyze_public_rc_fiber_frame", lambda *_args: other_model_result
    )
    result = collect_fiber_frame_warm_start_data(
        [_case(99, "train")], source_revision=_REVISION
    )
    assert result.samples == ()
    assert (
        result.to_dict()["cases"][0]["exception_type"] == "FiberFrameWarmStartDataError"
    )
