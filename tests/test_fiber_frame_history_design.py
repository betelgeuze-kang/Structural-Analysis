"""Public history authority and selection boundaries, with one physical source.

Selection probes inject producer rows explicitly; they are contract tests, not
additional solver observations or evidence of independently validated physics.
"""

from copy import copy, deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path

import pytest

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.assembly import (
    stateful_fiber_frame2d_nonlinear_history as core,
)
from structural_analysis.benchmark import fiber_frame_candidate_search as search
from structural_analysis.benchmark import fiber_frame_candidate_search_suite as suite
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.io.neutral.loader import load_neutral_json
from tests.test_fiber_frame_candidate_search import math_training_artifact


CONFIG = public_api.PublicRCFiberFrameConfig(load_steps=2)
PRICES = design.FiberFrameMaterialPrices(
    100.0, 2.0, "USD", "2026-09-08", "synthetic contract prices; not a quote"
)
TERMINAL_LIMITS = design.FiberFrameTerminalLimits(0.1, 0.1)
HISTORY_LIMITS = design.FiberFrameHistoryLimits(0.1, 0.1)
SOURCE = "a" * 40
CANDIDATES = (
    design.FiberFrameDesignCandidate(
        "narrow", (design.FiberFrameSectionChange("RC1", width_m=0.399),)
    ),
)


def _rehash(payload, key="report_hash"):
    payload[key] = canonical_hash(
        {name: value for name, value in payload.items() if name != key}
    )


def _rehashed_result(result, **changes):
    changed = replace(result, **changes)
    return replace(
        changed,
        result_hash=canonical_hash(
            public_api._public_result_payload(changed, include_hash=False)
        ),
    )


def _typed_sidecar(payload):
    return public_api.PublicRCFiberFrameResponseHistory(
        payload["status"],
        payload["contract_pass"],
        payload["report_hash"],
        json.dumps(payload, sort_keys=True, allow_nan=False),
    )


def _rehash_sidecar(payload):
    for step in payload["history"]["steps"]:
        _rehash(step, "recovery_hash")
    _rehash(payload["history"], "history_hash")
    payload["history_hash"] = payload["history"]["history_hash"]
    _rehash(payload)


@pytest.fixture(scope="module")
def physical(tmp_path_factory):
    model = load_neutral_json(
        Path(__file__).resolve().parents[1]
        / "examples/public_rc_fiber_frame_cantilever.json"
    )
    model.sections[0]["width_m"] = 0.401
    model.loads[0]["components"]["FY"] = -1.0
    result = public_api.analyze_public_rc_fiber_frame(model, CONFIG)
    assert result.contract_pass is True
    before = result.to_dict()
    checkpoint = result.checkpoint_artifact()
    prefix = result.checkpoint_artifact(1)
    history = public_api.recover_public_rc_fiber_frame_response_history(result)
    assert result.to_dict() == before
    sample = (
        tmp_path_factory.mktemp("public-history-integration") / "response-history.json"
    )
    sample.write_text(json.dumps(history.to_dict(), sort_keys=True), encoding="utf-8")
    sample.with_name("public-result.json").write_text(
        json.dumps(before, sort_keys=True), encoding="utf-8"
    )
    print(f"History sidecar fixture: {sample}")
    return model, result, history, checkpoint, prefix


@pytest.fixture(scope="module")
def verified_row(physical):
    model, result, history, _, _ = physical
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(public_api, "analyze_public_rc_fiber_frame", lambda *_: result)
        patch.setattr(
            public_api,
            "recover_public_rc_fiber_frame_response_history",
            lambda _: history,
        )
        row = design._evaluate_design(
            "baseline",
            model,
            CONFIG,
            PRICES,
            TERMINAL_LIMITS,
            7850.0,
            history_limits=HISTORY_LIMITS,
        )
    assert row["full_reference_verification_pass"] is True
    assert row["full_history_verification_pass"] is True
    return row


@pytest.fixture(scope="module")
def training():
    return math_training_artifact.__wrapped__()


def _cached_core(monkeypatch, physical):
    _, result, sidecar, _, _ = physical
    payload = sidecar.to_dict()["history"]
    cached = core.FiberFrameNonlinearEngineeringHistory(
        payload["history_hash"], json.dumps(payload, sort_keys=True)
    )

    def recover(adapter):
        assert adapter is result._authority_adapter
        return cached

    monkeypatch.setattr(
        core, "create_fiber_frame_nonlinear_engineering_history", recover
    )


def test_public_accessor_keeps_terminal_json_and_checkpoint_bytes(physical):
    _, result, sidecar, checkpoint, prefix = physical
    payload = sidecar.to_dict()
    assert sidecar.status == "ready" and sidecar.contract_pass is True
    assert payload["source_result_hash"] == result.result_hash
    assert payload["canonical_model_checksum"] == result.canonical_model_checksum
    assert payload["history_hash"] == payload["history"]["history_hash"]
    assert payload["report_hash"] == canonical_hash(
        {key: value for key, value in payload.items() if key != "report_hash"}
    )
    assert payload["history"]["steps"][-1]["node_displacements"] == [
        dict(row) for row in result.node_displacements
    ]
    assert payload["history"]["steps"][-1]["fiber_results"] == [
        dict(row) for row in result.fiber_results
    ]
    assert [step["epoch"] for step in payload["history"]["steps"]] == [1, 2]
    assert result.checkpoint_artifact() == checkpoint
    assert result.checkpoint_artifact(1) == prefix
    assert "history" not in result.to_dict()
    payload["history"]["steps"][0]["node_displacements"][0]["UX_m"] = 999.0
    assert (
        sidecar.to_dict()["history"]["steps"][0]["node_displacements"][0]["UX_m"]
        != 999.0
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "model",
        "adapter",
        "numerical",
        "checkpoint",
        "terminal_node",
        "terminal_fiber",
        "load_factors",
    ],
)
def test_public_accessor_rejects_rehashed_source_mismatch(
    physical, monkeypatch, mutation
):
    _cached_core(monkeypatch, physical)
    _, result, _, _, _ = physical
    if mutation == "model":
        changed = _rehashed_result(
            result, canonical_model_checksum="sha256:" + "f" * 64
        )
    elif mutation in ("adapter", "numerical"):
        bindings = dict(result.contract_bindings)
        key = (
            "source_result_adapter_hash"
            if mutation == "adapter"
            else "numerical_result_hash"
        )
        bindings[key] = "sha256:" + "f" * 64
        changed = _rehashed_result(result, contract_bindings=bindings)
    elif mutation == "checkpoint":
        changed = _rehashed_result(
            result,
            checkpoint={
                **result.checkpoint,
                "terminal_state_hash": "sha256:" + "f" * 64,
            },
        )
    elif mutation == "terminal_node":
        rows = [dict(row) for row in result.node_displacements]
        rows[-1]["UY_m"] += 1e-4
        changed = _rehashed_result(result, node_displacements=tuple(rows))
    elif mutation == "terminal_fiber":
        rows = [dict(row) for row in result.fiber_results]
        rows[0]["fiber_id"] = "unbound-fiber"
        changed = _rehashed_result(result, fiber_results=tuple(rows))
    else:
        changed = _rehashed_result(
            result,
            configuration={**result.configuration, "target_load_factors": [0.25, 1.0]},
        )
    with pytest.raises(ValueError):
        public_api.recover_public_rc_fiber_frame_response_history(changed)


def test_public_accessor_requires_matching_retained_checkpoint_bytes(
    physical, monkeypatch
):
    _cached_core(monkeypatch, physical)
    _, result, _, _, _ = physical
    detached_chain = copy(result._checkpoint_chain)
    checkpoint = copy(detached_chain.checkpoints[1])
    values = list(checkpoint.global_displacements)
    values[-2] += 1e-4
    object.__setattr__(checkpoint, "global_displacements", tuple(values))
    object.__setattr__(
        detached_chain,
        "checkpoints",
        (detached_chain.checkpoints[0], checkpoint, detached_chain.checkpoints[2]),
    )
    changed = replace(result, _checkpoint_chain=detached_chain)
    with pytest.raises(ValueError):
        public_api.recover_public_rc_fiber_frame_response_history(changed)


def test_public_accessor_cannot_promote_result_without_private_adapter(
    physical, monkeypatch
):
    def forbidden(*_):
        raise AssertionError("no history replay without source")

    monkeypatch.setattr(
        core, "create_fiber_frame_nonlinear_engineering_history", forbidden
    )
    with pytest.raises(ValueError, match="retained engineering source"):
        public_api.recover_public_rc_fiber_frame_response_history(
            replace(physical[1], _authority_adapter=None)
        )


@pytest.mark.parametrize(
    "mutation", ["schema", "earlier_array", "envelope", "source", "state_type"]
)
def test_public_history_validator_rejects_fully_rehashed_detached_changes(
    physical, monkeypatch, mutation
):
    _cached_core(monkeypatch, physical)
    _, result, sidecar, _, _ = physical
    assert (
        public_api.validate_public_rc_fiber_frame_response_history(sidecar, result)
        is sidecar
    )
    payload = sidecar.to_dict()
    if mutation == "schema":
        payload["history"]["schema_version"] = "detached-history.v1"
    elif mutation == "earlier_array":
        payload["history"]["steps"][0]["recovery_arrays"]["fiber_strain"][0] += 0.01
    elif mutation == "envelope":
        payload["history"]["envelope"]["maximum_translation_m"] = 0.0
    elif mutation == "source":
        payload["source_result_hash"] = "sha256:" + "f" * 64
    else:
        payload["contract_pass"] = 1
    _rehash_sidecar(payload)
    with pytest.raises(ValueError):
        public_api.validate_public_rc_fiber_frame_response_history(
            _typed_sidecar(payload), result
        )


def test_design_checks_history_envelope_when_terminal_screen_passes(
    physical, monkeypatch
):
    model, result, sidecar, _, _ = physical
    payload = sidecar.to_dict()
    # Explicit producer-boundary scenario; this modified peak is not a solver observation.
    payload["history"]["envelope"]["maximum_translation_m"] = 0.2
    payload["history"]["envelope"]["governing_translation"]["epoch"] = 1
    _rehash_sidecar(payload)
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", lambda *_: result)
    monkeypatch.setattr(
        public_api,
        "recover_public_rc_fiber_frame_response_history",
        lambda _: _typed_sidecar(payload),
    )
    row = design._evaluate_design(
        "baseline",
        model,
        CONFIG,
        PRICES,
        TERMINAL_LIMITS,
        7850.0,
        history_limits=HISTORY_LIMITS,
    )
    assert row["terminal_limit_status"] == "pass"
    assert row["history_limit_status"] == "fail"
    assert row["full_reference_verification_pass"] is True
    assert row["full_history_verification_pass"] is True
    assert row["violated_history_limits"] == ["history_maximum_translation_m"]
    assert row["performance"]["history_maximum_translation_m"] == 0.2


def test_history_recovery_failure_retains_verified_terminal_quantities(
    physical, verified_row, monkeypatch
):
    model, result, _, _, _ = physical
    monkeypatch.setattr(public_api, "analyze_public_rc_fiber_frame", lambda *_: result)

    def failed(_):
        raise RuntimeError("synthetic recovery failure")

    monkeypatch.setattr(
        public_api, "recover_public_rc_fiber_frame_response_history", failed
    )
    row = design._evaluate_design(
        "baseline",
        model,
        CONFIG,
        PRICES,
        TERMINAL_LIMITS,
        7850.0,
        history_limits=HISTORY_LIMITS,
    )
    assert row["full_reference_verification_pass"] is True
    assert row["terminal_limit_status"] == "pass"
    assert row["result"] == verified_row["result"]
    assert row["quantities"] == verified_row["quantities"]
    assert row["material_estimate"] == verified_row["material_estimate"]
    assert row["full_history_verification_pass"] is False
    assert row["history_limit_status"] == "unavailable"
    assert row["response_history"] is None
    assert row["history_failure"]["kind"] == "history_recovery_failed"
    assert not any(key.startswith("history_") for key in row["performance"])
    assert set(design._difference(verified_row, row)["terminal_performance_delta"]) == {
        "terminal_maximum_translation_m",
        "terminal_maximum_absolute_fiber_strain",
    }


def _stub_evaluation(template, candidate_id, model, history_failed):
    """Selection-only row; it grants no fresh physical-result authority."""
    row = deepcopy(template)
    row.update(
        candidate_id=candidate_id,
        model_checksum=model.canonical_model_checksum,
        canonical_model=model.canonical_payload(),
    )
    row["quantities"] = design.calculate_fiber_frame_member_quantities(model)
    row["material_estimate"] = design._estimate(row["quantities"], PRICES)
    if history_failed:
        row.update(
            full_history_verification_pass=False,
            response_history=None,
            history_limit_status="unavailable",
            violated_history_limits=[],
            history_failure={"kind": "synthetic_history_failure"},
        )
        row["performance"] = {
            key: value
            for key, value in row["performance"].items()
            if key.startswith("terminal_")
        }
    return row


def test_public_comparison_blocks_choice_when_baseline_history_is_unavailable(
    physical, verified_row, monkeypatch
):
    def evaluate(candidate_id, model, *_args, history_limits=None):
        assert history_limits == HISTORY_LIMITS
        return _stub_evaluation(
            verified_row, candidate_id, model, candidate_id == "baseline"
        )

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    report = design.compare_public_rc_fiber_frame_designs(
        physical[0],
        CANDIDATES,
        CONFIG,
        prices=PRICES,
        terminal_limits=TERMINAL_LIMITS,
        history_limits=HISTORY_LIMITS,
        source_revision=SOURCE,
    ).to_dict()
    assert report["schema_version"].endswith(".v2")
    assert report["status"] == "partial"
    assert report["selection"]["candidate_id"] is None
    assert report["rows"][1]["history_limit_status"] == "pass"
    assert report["rows"][1]["difference_from_baseline"] is not None
    assert report["claims"]["all_requested_history_verified"] is False


def test_history_failure_is_unverifiable_not_a_false_terminal_safety_prediction():
    pool = [
        {"candidate_id": name, "predicted_terminal_safe": True}
        for name in ("unknown", "history-fail", "feasible", "terminal-fail")
    ]
    rows = [
        {
            "candidate_id": name,
            "full_reference_verification_pass": True,
            "terminal_limit_status": terminal,
            "full_history_verification_pass": verified,
            "history_limit_status": history,
        }
        for name, terminal, verified, history in (
            ("unknown", "pass", False, "unavailable"),
            ("history-fail", "pass", True, "fail"),
            ("feasible", "pass", True, "pass"),
            ("terminal-fail", "fail", True, "pass"),
        )
    ]
    audit = search._audit_outcomes(pool, [], rows, history_required=True)
    assert audit["false_safe_candidate_ids"] == ["terminal-fail"]
    assert audit["missed_feasible_candidate_ids"] == ["feasible"]
    assert audit["oracle_verified_candidate_count"] == 4
    assert audit["oracle_combined_verified_candidate_count"] == 3
    assert audit["oracle_combined_unverifiable_candidate_count"] == 1
    assert audit["predicted_history_safety_available"] is False


def test_search_and_suite_propagate_history_scope_and_preserve_failed_attempts(
    physical, verified_row, training, monkeypatch
):
    calls = []

    def evaluate(candidate_id, model, *_args, history_limits=None):
        assert history_limits == HISTORY_LIMITS
        calls.append(candidate_id)
        return _stub_evaluation(verified_row, candidate_id, model, True)

    monkeypatch.setattr(design, "_evaluate_design", evaluate)
    case = suite.FiberFrameCandidateSearchCase(
        "history-contract",
        physical[0],
        CANDIDATES,
        training,
        PRICES,
        TERMINAL_LIMITS,
        config=CONFIG,
        full_analysis_budget=2,
        exploration_slots=1,
        history_limits=HISTORY_LIMITS,
    )
    core_results = []

    def runner(*args, **kwargs):
        result = search.compare_fiber_frame_candidate_search(*args, **kwargs)
        core_results.append(result)
        return result

    observed = suite.benchmark_fiber_frame_candidate_search_suite(
        [case],
        source_revision=SOURCE,
        repetitions=2,
        warmups=0,
        oracle_audit=True,
        runner=runner,
    )
    report = observed.to_dict()
    assert report["claims"]["report_contract_pass"] is True
    assert report["status"] == "incomplete"
    assert report["claims"]["local_timing_evidence_eligible"] is False
    assert report["declaration"]["cases"][0]["history_limits"] == asdict(HISTORY_LIMITS)
    assert len(report["runs"]) == 2
    assert [row["execution_order"] for row in report["runs"]] == [
        ["deterministic", "learned"],
        ["learned", "deterministic"],
    ]
    for run in report["runs"]:
        payload = run["comparison_report"]
        assert payload["schema_version"].endswith(".v3")
        assert run["status"] == "blocked"
        assert payload["cost_accounting"]["online_full_analysis_request_count"] == 4
        assert payload["oracle"]["full_analysis_request_count"] == 2
        for arm in payload["arms"]:
            assert arm["final_selection"] is None
            assert (
                arm["oracle_audit"]["oracle_combined_unverifiable_candidate_count"] == 1
            )
            assert arm["oracle_audit"]["predicted_history_safety_available"] is False
    assert len(calls) == 12
    assert (
        report["cost_accounting"][
            "total_analysis_request_count_including_training_warmups_and_oracles"
        ]
        == 16
    )
    for repetition, result in enumerate(core_results):
        for arm in ("deterministic", "learned"):
            saved = observed.design_comparison(case.case_id, arm, repetition=repetition)
            assert type(saved) is design.FiberFrameDesignComparison
            assert saved.to_dict() == result.design_comparison(arm).to_dict()
            changed = saved.to_dict()
            changed["rows"][0]["candidate_id"] = "tampered"
            assert (
                observed.design_comparison(
                    case.case_id, arm, repetition=repetition
                ).to_dict()["rows"][0]["candidate_id"]
                == "baseline"
            )
    for case_id, arm, repetition in (
        ("absent", "deterministic", 0),
        (case.case_id, "oracle", 0),
        (case.case_id, "learned", -1),
        (case.case_id, "learned", True),
        (case.case_id, "learned", 2),
    ):
        with pytest.raises(ValueError):
            observed.design_comparison(case_id, arm, repetition=repetition)
    assert len(calls) == 12


def test_suite_accepts_actual_source_bound_history_row(verified_row):
    suite._validate_history_row(
        verified_row,
        {"configuration": asdict(CONFIG), "history_limits": asdict(HISTORY_LIMITS)},
    )


@pytest.mark.parametrize(
    "mutation", ["missing_epoch", "model_binding", "envelope", "unavailable_credit"]
)
def test_suite_rejects_rehashed_history_scope_or_coverage_mismatch(
    verified_row, mutation
):
    row = deepcopy(verified_row)
    sidecar = row["response_history"]
    if mutation == "missing_epoch":
        sidecar["history"]["steps"].pop(0)
    elif mutation == "model_binding":
        sidecar["history"]["bindings"]["model_ir_content_hash"] = "sha256:" + "f" * 64
    elif mutation == "envelope":
        sidecar["history"]["envelope"]["maximum_translation_m"] = 0.0
    else:
        row["full_history_verification_pass"] = False
    _rehash_sidecar(sidecar)
    with pytest.raises(ValueError):
        suite._validate_history_row(
            row,
            {"configuration": asdict(CONFIG), "history_limits": asdict(HISTORY_LIMITS)},
        )
