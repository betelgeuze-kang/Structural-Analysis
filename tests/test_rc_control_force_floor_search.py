"""Prospectively frozen price search changes real eligible selections."""

import json
from pathlib import Path

import pytest

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark import rc_control_design as study
from structural_analysis.benchmark import rc_control_force_floor_search as search
from structural_analysis.benchmark import rc_control_force_factor_learning as learning
from structural_analysis.benchmark.rc_control_force_floor_cli import (
    FLOOR_INPUT_SCHEMA,
    read_force_response_floor,
)
from structural_analysis.io.neutral.loader import load_neutral_json
from structural_analysis.ai.fiber_frame_candidate_learning import (
    candidate_model_identity,
)


def inputs():
    root = Path("examples/research/rc_reuse_campaign")
    return {
        "baseline": load_neutral_json(root / "pin-roller-replication.model.json"),
        "candidates": tuple(
            design.FiberFrameDesignCandidate(
                candidate_id, (design.FiberFrameSectionChange("RC1", width_m=width),)
            )
            for candidate_id, width in (("w34", 0.34), ("w42", 0.42))
        ),
        "request": decode_bounded_rc_fiber_direct_control_request(
            (root / "pin-roller-replication.request.json").read_bytes()
        ),
        "force_response_floor": {
            "target_index": 2,
            "target_control_displacement_m": -0.00014,
            "minimum_load_factor": 180.0,
        },
        "history_limits": design.FiberFrameHistoryLimits(1.0, 1.0),
        "material_limits": design.FiberFrameMaterialHistoryLimits(1.0, 1.0, 1.0),
        "prices": design.FiberFrameMaterialPrices(
            100, 1, "KRW", "2026-09-29", "invented regression arithmetic"
        ),
        "source_revision": "a" * 40,
        "full_analysis_budget": 3,
    }


def test_price_and_oracle_use_frozen_floor_before_first_solve(tmp_path, monkeypatch):
    args = inputs()
    output = tmp_path / "search"
    solver = study.api.analyze_bounded_rc_fiber_direct_control
    seen = []

    def checked_solver(*solver_args, **solver_kwargs):
        plan = json.loads((output / "plan.json").read_bytes())
        assert plan["force_response_floor"] == args["force_response_floor"]
        assert plan["plans"]["price_order"]["shortlist"] == ["w34", "w42"]
        seen.append(plan["plan_hash"])
        return solver(*solver_args, **solver_kwargs)

    monkeypatch.setattr(
        study.api, "analyze_bounded_rc_fiber_direct_control", checked_solver
    )
    report = search.compare_rc_control_force_floor_price_search(
        **args, output_directory=output
    )
    plan = json.loads((output / "plan.json").read_bytes())
    assert seen and set(seen) == {plan["plan_hash"]}
    assert report["plan_hash"] == plan["plan_hash"]
    assert plan["learned_policy_used"] is False
    assert report["schema_version"] == search.SEARCH_SCHEMA
    assert report["arms"]["price_order"]["selected_candidate_id"] == "w42"
    assert report["oracle"]["selected_candidate_id"] == "w42"
    assert report["candidate_cost_optimality_audit"]["status"] == "complete"
    assert report["candidate_cost_optimality_audit"][
        "pool_minimum_feasible_candidate_ids"
    ] == ["w42"]
    assert (
        report["candidate_cost_optimality_audit"]["arms"]["price_order"][
            "matches_pool_minimum"
        ]
        is True
    )
    assert report["claims"]["net_ai_savings_proved"] is False
    for name in ("price_order", "exhaustive_oracle"):
        comparison = json.loads((output / name / "comparison.json").read_bytes())
        assert comparison["force_response_floor"] == plan["force_response_floor"]
        assert comparison["selected_candidate_id"] == "w42"


def test_bad_floor_and_budget_reject_before_any_search_output(tmp_path):
    args = inputs()
    for change in (
        {
            "force_response_floor": args["force_response_floor"]
            | {"minimum_load_factor": 0}
        },
        {"full_analysis_budget": True},
        {"full_analysis_budget": 4},
        {"protocol_binding": {"protocol_commit": "a" * 40}},
    ):
        output = tmp_path / f"bad-{len(list(tmp_path.iterdir()))}"
        with pytest.raises(ValueError):
            search.compare_rc_control_force_floor_price_search(
                **(args | change), output_directory=output
            )
        assert not output.exists()


def test_floor_cli_rejects_ambiguous_json(tmp_path):
    input_path = tmp_path / "floor.json"
    input_path.write_text(
        '{"schema_version":"' + FLOOR_INPUT_SCHEMA + '",'
        '"target_index":2,"target_index":3,'
        '"target_control_displacement_m":-0.00014,"minimum_load_factor":180}'
    )
    with pytest.raises(ValueError, match="duplicate"):
        read_force_response_floor(input_path)


def _synthetic_policy_and_training(args, *, overlap=False, wrong_context=False):
    """Small serialized artifacts for search logic, without any training solve."""
    _, context = learning.control_force_factor_features(
        args["baseline"], args["request"], args["force_response_floor"]
    )
    if wrong_context:
        context = "sha256:" + "7" * 64
    n, m = len(learning.FEATURE_NAMES), len(learning.FORCE_FACTOR_TARGETS)
    identities = ["sha256:" + "1" * 64, "sha256:" + "2" * 64]
    if overlap:
        identities[0] = candidate_model_identity(
            args["baseline"], experimental_pin_roller_beam=True
        )
    payload = {
        "schema_version": learning.FORCE_FACTOR_POLICY_SCHEMA,
        "context_hash": context,
        "force_target": {
            "target_index": args["force_response_floor"]["target_index"],
            "target_control_displacement_m": args["force_response_floor"][
                "target_control_displacement_m"
            ],
        },
        "features": list(learning.FEATURE_NAMES),
        "targets": list(learning.FORCE_FACTOR_TARGETS),
        "mean": [0.0] * n,
        "scale": [1.0] * n,
        "minimum": [-1e9] * n,
        "maximum": [1e9] * n,
        "target_scale": [1.0] * m,
        "weights": [[0.0] * m for _ in range(n + 1)],
        "ridge": 1.0,
        "ood_margin": 0.0,
        "training_model_identities": identities,
        "training_sample_hashes": ["sha256:" + "3" * 64, "sha256:" + "4" * 64],
        "label_comparison_hash": "sha256:" + "5" * 64,
    }
    payload["policy_hash"] = study._sha(study._bytes(payload))
    policy = learning.RCControlForceFactorPolicy(study._bytes(payload).decode())
    invocation = {
        "unknown_execution_work": False,
        "work": {
            "attempted_step_count": 1,
            "known_linear_solve_count": 1,
            "known_newton_iteration_count": 1,
            "unknown_solver_work_attempt_count": 0,
        },
    }
    training = {
        "schema_version": learning.FORCE_FACTOR_TRAINING_SCHEMA,
        "force_response_floor": dict(args["force_response_floor"]),
        "policy_hash": policy.policy_hash,
        "label_comparison_hash": payload["label_comparison_hash"],
        "sample_count": 2,
        "fit": {
            "status": "completed",
            "unknown_fit_work_until_outcome": False,
            "wall_ns": 5,
            "cpu_ns": 4,
        },
        "label_invocations": [dict(invocation) for _ in range(4)],
        "label_generation_wall_ns": 20,
        "wall_ns": 30,
        "cpu_ns": 24,
    }
    training["report_hash"] = study._sha(study._bytes(training))
    return policy, training


def _mock_comparison(output, args, calls, *, unknown_first=False):
    """Explicitly synthetic oracle rows exercise ordering and audit plumbing."""

    def compare(_baseline, candidates, request, **kwargs):
        plan = json.loads((output / "plan.json").read_bytes())
        assert set(plan["plans"]) == {"price_order", "learned_order"}
        assert plan["plans"]["price_order"]["shortlist"] == ["w34"]
        assert plan["plans"]["learned_order"]["shortlist"] == ["w42"]
        name = kwargs["output_directory"].name
        calls.append(name)
        assert kwargs["force_response_floor"] == plan["force_response_floor"]
        assert request.to_dict() == plan["control_request"]
        if name == "price_order":
            assert not (output / "learned_order-started.json").exists()
            assert not (output / "exhaustive_oracle-started.json").exists()
        ids = ["baseline", *(candidate.candidate_id for candidate in candidates)]
        by_id = {row["candidate_id"]: row for row in plan["pool"]}
        rows = []
        for candidate_id in ids:
            factor = 200.0 if candidate_id == "w42" else 100.0
            performance = {key: 0.0 for key in learning.TARGETS} | {
                "load_factor_at_target": factor
            }
            screens = study._screens(
                performance, args["history_limits"], args["material_limits"]
            )
            minimum = plan["force_response_floor"]["minimum_load_factor"]
            screens["load_factor_at_target"] = {
                "value": factor,
                "limit": minimum,
                "status": "pass" if factor >= minimum else "fail",
                "comparison": "at_least",
            }
            work = {
                "attempted_step_count": 1,
                "known_linear_solve_count": 1,
                "known_newton_iteration_count": 1,
                "unknown_solver_work_attempt_count": 0,
            }
            if unknown_first and name == "price_order":
                work["unknown_solver_work_attempt_count"] = 1
            rows.append(
                {
                    "candidate_id": candidate_id,
                    "material_estimate": by_id[candidate_id]["material_estimate"],
                    "full_reference_verification_pass": True,
                    "screens": screens,
                    "invocations": [{"unknown_execution_work": False, "work": work}],
                }
            )
        report = {
            "schema_version": "experimental-rc-control-design-comparison.v2",
            "source_revision": args["source_revision"],
            "baseline_checksum": plan["baseline_checksum"],
            "control_request": plan["control_request"],
            "force_response_floor": plan["force_response_floor"],
            "price_table_hash": plan["price_table_hash"],
            "rows": rows,
            "selected_candidate_id": "w42" if "w42" in ids else None,
        }
        report["report_hash"] = study._sha(study._bytes(report))
        kwargs["output_directory"].mkdir()
        study._save(kwargs["output_directory"], "comparison.json", study._bytes(report))
        return report

    return compare


def test_learned_floor_order_and_equal_budget_frozen_before_synthetic_comparisons(
    tmp_path, monkeypatch
):
    args = inputs() | {"full_analysis_budget": 2}
    policy, training = _synthetic_policy_and_training(args)
    model_ids = {
        candidate.candidate_id: design.apply_fiber_frame_section_changes(
            args["baseline"], candidate
        ).canonical_model_checksum
        for candidate in args["candidates"]
    }

    def predicted(self, model, _request, _floor):
        factor = 200.0 if model.canonical_model_checksum == model_ids["w42"] else 100.0
        return {
            "policy_hash": self.policy_hash,
            "abstained": False,
            "performance": {key: 0.0 for key in learning.TARGETS}
            | {"load_factor_at_target": factor},
            "physical_result_authority": False,
            "uncertainty_calibrated": False,
        }

    monkeypatch.setattr(learning.RCControlForceFactorPolicy, "predict", predicted)
    output, calls = tmp_path / "learned", []
    monkeypatch.setattr(
        study, "compare_rc_control_designs", _mock_comparison(output, args, calls)
    )
    result = search.compare_rc_control_force_floor_learned_search(
        **args, policy=policy, training_report=training, output_directory=output
    )
    plan = json.loads((output / "plan.json").read_bytes())
    assert calls == ["price_order", "learned_order", "exhaustive_oracle"]
    assert result["schema_version"] == search.LEARNED_SEARCH_SCHEMA
    assert plan["schema_version"] == search.FORCE_FLOOR_LEARNED_PLAN
    assert [
        plan["plans"][arm]["shortlist"] for arm in ("price_order", "learned_order")
    ] == [["w34"], ["w42"]]
    assert all(result["arms"][arm]["request_count"] == 2 for arm in result["arms"])
    assert result["oracle"]["request_count"] == 3
    assert result["arms"]["price_order"]["selected_candidate_id"] is None
    assert result["arms"]["learned_order"]["selected_candidate_id"] == "w42"
    assert result["candidate_cost_optimality_audit"]["schema_version"].endswith(".v4")
    assert result["candidate_cost_optimality_audit"]["status"] == "complete"
    assert result["historical_training_execution_work"]["api_invocation_count"] == 4
    assert result["historical_training_cost_counted_once_outside_online_arms"] is True
    assert result["claims"]["net_ai_savings_proved"] is False
    for field in ("policy_artifact", "historical_training_artifact"):
        artifact = plan[field]
        raw = (output / artifact["path"]).read_bytes()
        assert len(raw) == artifact["byte_length"]
        assert study._sha(raw) == artifact["sha256"]


def test_learned_floor_overlap_rejects_before_output(tmp_path):
    args = inputs() | {"full_analysis_budget": 2}
    policy, training = _synthetic_policy_and_training(args, overlap=True)
    output = tmp_path / "overlap"
    with pytest.raises(ValueError, match="overlap"):
        search.compare_rc_control_force_floor_learned_search(
            **args, policy=policy, training_report=training, output_directory=output
        )
    assert not output.exists()


def test_learned_floor_context_mismatch_rejects_before_output(tmp_path):
    args = inputs() | {"full_analysis_budget": 2}
    policy, training = _synthetic_policy_and_training(args, wrong_context=True)
    output = tmp_path / "context"
    with pytest.raises(ValueError, match="context mismatch"):
        search.compare_rc_control_force_floor_learned_search(
            **args, policy=policy, training_report=training, output_directory=output
        )
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["unknown_work", "nested_timing"])
def test_learned_floor_training_cost_preflight_rejects_unknown_or_impossible_work(
    tmp_path, mutation
):
    args = inputs() | {"full_analysis_budget": 2}
    policy, training = _synthetic_policy_and_training(args)
    if mutation == "unknown_work":
        training["label_invocations"][0]["work"][
            "unknown_solver_work_attempt_count"
        ] = 1
    else:
        training["fit"]["wall_ns"] = training["wall_ns"] + 1
    training["report_hash"] = study._sha(
        study._bytes(
            {key: value for key, value in training.items() if key != "report_hash"}
        )
    )
    output = tmp_path / mutation
    with pytest.raises(ValueError, match="unknown historical|timing exceeds"):
        search.compare_rc_control_force_floor_learned_search(
            **args, policy=policy, training_report=training, output_directory=output
        )
    assert not output.exists()


def test_learned_floor_unknown_work_stops_before_second_arm(tmp_path, monkeypatch):
    args = inputs() | {"full_analysis_budget": 2}
    policy, training = _synthetic_policy_and_training(args)
    monkeypatch.setattr(
        learning.RCControlForceFactorPolicy,
        "predict",
        lambda self, _model, _request, _floor: {
            "policy_hash": self.policy_hash,
            "abstained": True,
            "performance": None,
            "physical_result_authority": False,
        },
    )
    output, calls = tmp_path / "unknown", []

    # The mock checks a distinct learned shortlist; choose a synthetic ranking
    # here only for the unknown-work gate, before any learned arm can execute.
    def unknown_compare(*_positional, **kwargs):
        calls.append(kwargs["output_directory"].name)
        return {
            "rows": [
                {
                    "candidate_id": "baseline",
                    "invocations": [
                        {
                            "unknown_execution_work": False,
                            "work": {
                                "attempted_step_count": 1,
                                "known_linear_solve_count": 1,
                                "known_newton_iteration_count": 1,
                                "unknown_solver_work_attempt_count": 1,
                            },
                        }
                    ],
                }
            ],
            "selected_candidate_id": None,
            "report_hash": "sha256:" + "9" * 64,
        }

    monkeypatch.setattr(study, "compare_rc_control_designs", unknown_compare)
    with pytest.raises(ValueError, match="unknown numerical work"):
        search.compare_rc_control_force_floor_learned_search(
            **args, policy=policy, training_report=training, output_directory=output
        )
    assert calls == ["price_order"]
    assert (
        json.loads((output / "price_order-outcome.json").read_bytes())[
            "unknown_work_until_outcome"
        ]
        is True
    )
    assert all(
        row["predicted_force_floor_status"] == "unavailable"
        for row in json.loads((output / "plan.json").read_bytes())["predictions"]
    )
    assert not (output / "learned_order-started.json").exists()
