"""Independent V2 provenance and fit checks without new evaluation solves."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
import pytest

from scripts import audit_rc_force_factor_prospective as audit
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark import fiber_frame_design as design
from structural_analysis.benchmark.rc_control_candidate_learning import (
    _candidate_fit_parameters,
)
from structural_analysis.benchmark.rc_control_force_factor_learning import (
    control_force_factor_features,
    load_rc_control_force_factor_policy,
)
from structural_analysis.io.neutral.loader import load_neutral_json


SOURCE = Path(__file__).resolve().parents[1]
CAMPAIGN = Path("examples/research/rc_reuse_campaign")
PROTOCOL = CAMPAIGN / "force-factor-prospective.protocol.json"
LEARNING = {
    "schema_version": audit.LEARNING_PLAN_SCHEMA,
    "fit_method": audit.FIT_METHOD,
    "ridge": 1.0,
    "ood_margin": 0.0,
    "ranking_strategy": audit.RANKING,
}


def _training_samples():
    source = load_neutral_json(SOURCE / CAMPAIGN / "pin-roller-replication.model.json")
    request = decode_bounded_rc_fiber_direct_control_request(
        (SOURCE / CAMPAIGN / "pin-roller-replication.request.json").read_bytes()
    )
    floor = json.loads(
        (SOURCE / CAMPAIGN / "force-factor-prospective.floor.json").read_bytes()
    )
    floor.pop("schema_version")
    samples, context = [], None
    for width in (0.32, 0.36, 0.40, 0.44, 0.48, 0.52, 0.56):
        model = (
            source
            if width == 0.4
            else design.apply_fiber_frame_section_changes(
                source,
                design.FiberFrameDesignCandidate(
                    f"w{round(width * 100)}",
                    (design.FiberFrameSectionChange("RC1", width_m=width),),
                ),
            )
        )
        producer, current_context = control_force_factor_features(model, request, floor)
        auditor = audit._features(model.canonical_payload())
        assert producer == tuple(auditor)
        context = current_context if context is None else context
        assert current_context == context
        targets = [
            0.001 + width * 0.00001,
            0.0001 + width * 0.00001,
            0.002 + width * 0.00001,
            0.0002 + width * 0.00001,
            0.1 + width * 0.01,
            0.2 + width * 0.01,
            0.3 + width * 0.01,
            170 + width * 100,
        ]
        samples.append({"features": auditor, "targets": targets})
    return samples, context, floor


def _policy(samples, context, floor):
    parameters = _candidate_fit_parameters(
        np.asarray([row["features"] for row in samples]),
        np.asarray([row["targets"] for row in samples]),
        1.0,
        audit.FIT_METHOD,
    )
    policy = {
        "schema_version": audit.POLICY_SCHEMA,
        "context_hash": context,
        "force_target": {
            "target_index": floor["target_index"],
            "target_control_displacement_m": floor["target_control_displacement_m"],
        },
        "features": audit.FEATURE_NAMES,
        "targets": audit.TARGETS,
        **parameters,
        "ridge": 1.0,
        "ood_margin": 0.0,
        "training_model_identities": [
            "sha256:" + f"{i:064x}" for i in range(len(samples))
        ],
        "training_sample_hashes": [
            "sha256:" + f"{i + 20:064x}" for i in range(len(samples))
        ],
        "label_comparison_hash": "sha256:" + "a" * 64,
    }
    policy["policy_hash"] = audit.sha(audit.canonical(policy))
    return policy


def test_training_family_features_and_stdlib_fit_match_producer():
    samples, context, floor = _training_samples()
    policy = _policy(samples, context, floor)
    expected = audit.check_policy_fit(policy, samples, LEARNING)
    for actual, independently_fitted in zip(
        policy["weights"], expected["weights"], strict=True
    ):
        assert all(
            abs(a - b) < 1e-10
            for a, b in zip(actual, independently_fitted, strict=True)
        )


def test_integer_declared_prices_match_parser_normalized_price_hash():
    experiment = json.loads(
        (SOURCE / CAMPAIGN / "force-factor-prospective.experiment.json").read_bytes()
    )
    raw = experiment["prices"]
    assert type(raw["concrete_per_m3"]) is int
    assert type(raw["rebar_per_kg"]) is int
    normalized = audit._normalized_prices(raw)
    assert type(normalized["concrete_per_m3"]) is float
    assert type(normalized["rebar_per_kg"]) is float
    producer = design.FiberFrameMaterialPrices(**raw)
    assert (
        audit.sha(
            audit.canonical(
                {"schema_version": "declared-rc-material-prices.v1", **normalized}
            )
        )
        == producer.price_table_hash
    )


def test_coherently_resealed_policy_weight_change_is_rejected():
    samples, context, floor = _training_samples()
    forged = _policy(samples, context, floor)
    forged["weights"][0][-1] += 1.0
    forged["policy_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in forged.items() if key != "policy_hash"}
        )
    )
    with pytest.raises(audit.AuditError, match="policy weights"):
        audit.check_policy_fit(forged, samples, LEARNING)


def test_near_constant_real_packet_strain_uses_physical_unit_fit():
    samples, context, floor = _training_samples()
    # The seven frozen exact-source training labels differed by only float ulps.
    # That one-ulp reduction-order difference changes a normalized ~1e15
    # intercept while preserving the physical response to ~4e-20.
    strain_labels = (
        0.00012073302191879279,
        0.00012073302191879279,
        0.00012073302191879279,
        0.00012073302191879277,
        0.000120733021918793,
        0.00012073302191879299,
        0.00012073302191879299,
    )
    for sample, value in zip(samples, strain_labels, strict=True):
        sample["targets"][3] = value
    policy = _policy(samples, context, floor)
    independent = audit._centered_ridge(samples, 1.0)
    assert abs(policy["weights"][-1][3] - independent["weights"][-1][3]) > 1e9
    audit.check_policy_fit(policy, samples, LEARNING)
    forged = json.loads(audit.canonical(policy))
    forged["weights"][0][7] += 1.0  # Signed force factor remains strictly checked.
    forged["policy_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in forged.items() if key != "policy_hash"}
        )
    )
    with pytest.raises(audit.AuditError, match="policy weights"):
        audit.check_policy_fit(forged, samples, LEARNING)


def test_resealed_prediction_and_ranking_cannot_change_signed_factor():
    samples, context, floor = _training_samples()
    policy = _policy(samples, context, floor)
    producer_policy = load_rc_control_force_factor_policy(audit.canonical(policy))
    source = load_neutral_json(SOURCE / CAMPAIGN / "pin-roller-replication.model.json")
    request = decode_bounded_rc_fiber_direct_control_request(
        (SOURCE / CAMPAIGN / "pin-roller-replication.request.json").read_bytes()
    )
    models, estimates, predictions = {}, {}, []
    plan = {
        "force_response_floor": floor,
        "history_limits": {
            "maximum_translation_m": 1.0,
            "maximum_absolute_fiber_strain": 1.0,
        },
        "material_limits": {
            "maximum_steel_accumulated_plastic_strain": 1.0,
            "maximum_concrete_tensile_damage": 1.0,
            "maximum_concrete_compressive_damage": 1.0,
        },
        "terminal_limits": None,
        "full_analysis_budget_including_baseline_per_arm": 2,
        "pool": [{"candidate_id": "baseline"}],
    }
    for width, estimate in ((0.33, 10.0), (0.55, 20.0)):
        candidate_id = f"w{round(width * 100)}"
        model = design.apply_fiber_frame_section_changes(
            source,
            design.FiberFrameDesignCandidate(
                candidate_id,
                (design.FiberFrameSectionChange("RC1", width_m=width),),
            ),
        )
        models[candidate_id] = model.canonical_payload()
        estimates[candidate_id] = {"total": estimate}
        predicted = producer_policy.predict(model, request, floor)
        screens = (
            None
            if predicted["abstained"]
            else audit.common.screens_from_performance(
                predicted["performance"],
                plan,
                predicted["performance"]["load_factor_at_target"],
            )
        )
        tier = (
            1
            if screens is None
            else 0
            if all(screen["status"] == "pass" for screen in screens.values())
            else 2
        )
        predictions.append(
            {
                "candidate_id": candidate_id,
                "prediction": predicted,
                "predicted_screens": screens,
                "predicted_force_floor_status": "unavailable"
                if screens is None
                else "available",
                "ranking_tier": tier,
                "estimate": estimate,
            }
        )
        plan["pool"].append({"candidate_id": candidate_id})
    assert all(row["predicted_screens"] is not None for row in predictions)
    price_order = ["w33", "w55"]
    learned_order = [
        row["candidate_id"]
        for row in sorted(
            predictions,
            key=lambda row: (row["ranking_tier"], row["estimate"], row["candidate_id"]),
        )
    ]
    plan["predictions"] = predictions
    plan["plans"] = {
        "price_order": {"ordering": price_order, "shortlist": price_order[:1]},
        "learned_order": {"ordering": learned_order, "shortlist": learned_order[:1]},
    }
    assert audit._check_predictions(plan, policy, models, estimates) == (
        price_order,
        learned_order,
    )
    forged = json.loads(audit.canonical(plan))
    changed = forged["predictions"][0]
    changed["prediction"]["performance"]["load_factor_at_target"] += 10.0
    changed["predicted_screens"]["load_factor_at_target"]["value"] += 10.0
    forged["plan_hash"] = audit.sha(audit.canonical(forged))
    with pytest.raises(audit.AuditError, match="prediction differs"):
        audit._check_predictions(forged, policy, models, estimates)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def committed_packet(tmp_path):
    repo, packet = tmp_path / "checkout", tmp_path / "packet"
    repo.mkdir()
    packet.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "Audit Test")
    _git(repo, "config", "user.email", "audit@example.invalid")
    runner = repo / "scripts" / "run_rc_force_factor_prospective.py"
    runner.parent.mkdir()
    shutil.copyfile(SOURCE / "scripts/run_rc_force_factor_prospective.py", runner)
    protocol = json.loads((SOURCE / PROTOCOL).read_bytes())
    for role, reference in protocol["inputs"].items():
        relative = Path(reference["path"])
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, destination)
        assert audit.sha(destination.read_bytes()) == reference["sha256"]
        copied = packet / "inputs" / f"{role}.json"
        copied.parent.mkdir(exist_ok=True)
        shutil.copyfile(destination, copied)
    protocol_destination = repo / PROTOCOL
    shutil.copyfile(SOURCE / PROTOCOL, protocol_destination)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "freeze test V2 protocol")
    commit = _git(repo, "rev-parse", "HEAD")
    pre = {
        "schema_version": audit.PREDECLARATION_SCHEMA,
        "source_revision": commit,
        "source_checkout_clean": True,
        "protocol_commit": commit,
        "protocol_path": PROTOCOL.as_posix(),
        "protocol_sha256": audit.sha(protocol_destination.read_bytes()),
        "input_paths": {role: ref["path"] for role, ref in protocol["inputs"].items()},
        "input_sha256": {
            role: ref["sha256"] for role, ref in protocol["inputs"].items()
        },
        "baselines": protocol["baselines"],
        "schedule": protocol["schedule"],
        "floor_selection_provenance": protocol["floor_selection_provenance"],
        "full_analysis_budget": protocol["full_analysis_budget"],
        "reuse_line_search_assembly": protocol["reuse_line_search_assembly"],
        "independent_project_geometry_history_split": False,
        "search_mode": "price_order_and_learned_order_then_exhaustive_oracle",
        "runner_sha256": audit.sha(runner.read_bytes()),
    }
    pre["plan_hash"] = audit.sha(audit.canonical(pre))
    (packet / "plan.json").write_bytes(audit.canonical(pre) + b"\n")
    receipt = {
        "schema_version": audit.RUNNER_SCHEMA,
        **{
            key: pre[key]
            for key in (
                "source_revision",
                "protocol_commit",
                "protocol_path",
                "protocol_sha256",
                "input_paths",
                "input_sha256",
                "baselines",
                "schedule",
                "floor_selection_provenance",
                "full_analysis_budget",
                "reuse_line_search_assembly",
            )
        },
        "clean_source_checkout": True,
        "runner_sha256": pre["runner_sha256"],
        "outer_plan_hash": pre["plan_hash"],
        "outer_plan_sha256": audit.sha((packet / "plan.json").read_bytes()),
        "independent_physical_validation": False,
        "independent_generalization": False,
        "learned_policy_used": True,
        "ai_benefit_claimed": False,
    }
    receipt["report_hash"] = audit.sha(audit.canonical(receipt))
    (packet / "runner.json").write_bytes(audit.canonical(receipt) + b"\n")
    return repo, packet, pre, receipt


def test_protocol_source_and_six_input_bytes_bind_to_ancestor_commit(committed_packet):
    repo, packet, pre, receipt = committed_packet
    actual_plan, actual_receipt, inputs = audit._provenance(repo, packet)
    assert actual_plan == pre
    assert actual_receipt == receipt
    assert set(inputs) == set(audit.ROLES)


def test_resealed_packet_input_cannot_replace_committed_blob(committed_packet):
    repo, packet, pre, receipt = committed_packet
    path = packet / "inputs/floor_plan.json"
    forged = json.loads(path.read_bytes())
    forged["minimum_load_factor"] += 1
    path.write_bytes(audit.canonical(forged) + b"\n")
    digest = audit.sha(path.read_bytes())
    pre["input_sha256"]["floor_plan"] = digest
    pre["plan_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in pre.items() if key != "plan_hash"}
        )
    )
    (packet / "plan.json").write_bytes(audit.canonical(pre) + b"\n")
    receipt["input_sha256"]["floor_plan"] = digest
    receipt["outer_plan_hash"] = pre["plan_hash"]
    receipt["outer_plan_sha256"] = audit.sha((packet / "plan.json").read_bytes())
    receipt["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in receipt.items() if key != "report_hash"}
        )
    )
    (packet / "runner.json").write_bytes(audit.canonical(receipt) + b"\n")
    with pytest.raises(audit.AuditError, match="floor_plan input binding"):
        audit._provenance(repo, packet)


def test_incomplete_packet_fails_closed(committed_packet):
    repo, packet, _, _ = committed_packet
    report = audit.audit_packet(repo, packet)
    assert report["status"] == "incomplete_or_unverifiable"
    assert report["unknown_execution_work"] is True
    assert report["net_ai_savings_proved"] is False
