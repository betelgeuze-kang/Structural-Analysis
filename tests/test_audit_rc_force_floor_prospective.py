"""Synthetic packet integrity tests; no synthetic row is physical validation."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts import audit_rc_force_floor_prospective as audit


SOURCE = Path(__file__).resolve().parents[1]
CAMPAIGN = Path("examples/research/rc_reuse_campaign")
FLOOR = {
    "target_index": 2,
    "target_control_displacement_m": -0.00014,
    "minimum_load_factor": 180.0,
}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audit.canonical(value) + b"\n")


def git(repo, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=repo, text=True).strip()


def artifact(packet, prefix, candidate_id, filename, value):
    relative = f"{candidate_id}/{filename}"
    path = packet / prefix / relative
    write_json(path, value)
    data = path.read_bytes()
    return {"path": relative, "byte_length": len(data), "sha256": audit.sha(data)}


def make_result(candidate_id, factor, request, model_checksum, checkpoint_bytes):
    history, attempts = [], []
    for index, target in enumerate(request["targets_m"]):
        value = factor if index == FLOOR["target_index"] else factor * 0.5
        checkpoint_hash = audit.sha(f"checkpoint-{candidate_id}-{index}".encode())
        parent_hash = audit.sha(f"parent-{candidate_id}-{index}".encode())
        step_hash = audit.sha(f"step-{candidate_id}-{index}".encode())
        displacements = [0.0] * 12
        displacements[request["control_global_dof"]] = target
        attempts.append(
            {
                "committed": True,
                "target_control_displacement_m": target,
                "accepted_checkpoint_hash": checkpoint_hash,
                "parent_checkpoint_hash": parent_hash,
                "step": {
                    "step_hash": step_hash,
                    "accepted_checkpoint": {
                        "state_hash": checkpoint_hash,
                        "parent_state_hash": parent_hash,
                        "load_factor": value,
                        "global_displacements": displacements,
                    },
                },
            }
        )
        history.append(
            {
                "load_factor": value,
                "checkpoint_hash": checkpoint_hash,
                "parent_checkpoint_hash": parent_hash,
                "source_step_hash": step_hash,
                "node_displacements": [
                    {"node_id": "N4", "UX_m": 0.0, "UY_m": target, "UZ_m": 0.0}
                ],
                "fiber_results": [
                    {
                        "material_kind": "steel",
                        "strain": 0.00001,
                        "material_state": {"accumulated_plastic_strain": 0.0},
                    },
                    {
                        "material_kind": "concrete",
                        "strain": -0.00001,
                        "material_state": {
                            "tensile_damage": 0.0,
                            "compressive_damage": 0.0,
                        },
                    },
                ],
            }
        )
    work = {
        "attempted_step_count": 4,
        "known_linear_solve_count": 4,
        "known_newton_iteration_count": 4,
        "unknown_solver_work_attempt_count": 0,
    }
    result = {
        "contract_pass": True,
        "model": {"canonical_model_checksum": model_checksum},
        "request": audit.expected_result_request(
            request, reuse_line_search_assembly=False
        ),
        "control": {
            "global_dof": request["control_global_dof"],
            "component": "UY",
            "node_id": "N4",
        },
        "response_history": history,
        "path": {
            "accepted_target_prefix_m": request["targets_m"],
            "attempts": attempts,
            "metrics": {"total_work": work},
        },
        "checkpoint": {
            "sha256": audit.sha(checkpoint_bytes),
            "byte_length": len(checkpoint_bytes),
        },
        "metrics": {"control_work": work},
    }
    result["result_hash"] = audit.sha(audit.canonical(result))
    return result, work


def make_row(packet, comparison_name, candidate_id, factor, plan, model, pool_row):
    prefix = f"search/{comparison_name}"
    checkpoint = {"candidate_id": candidate_id, "kind": "synthetic-checkpoint"}
    checkpoint_bytes = audit.canonical(checkpoint) + b"\n"
    result, work = make_result(
        candidate_id,
        factor,
        plan["control_request"],
        pool_row["model_checksum"],
        checkpoint_bytes,
    )
    replay_work = dict(work)
    verification = {
        "status": "valid_artifact",
        "artifact_contract_pass": True,
        "contract_pass": True,
        "physical_path_complete": True,
        "fresh_source_execution_invoked": True,
        "solver_replay_performed": True,
        "verified_result_hash": result["result_hash"],
        "errors": [],
        "unavailable_execution_work": False,
        "replay_control_work": replay_work,
    }
    invocations, artifacts = [], {}
    artifacts["model"] = artifact(packet, prefix, candidate_id, "model.json", model)
    for phase, phase_work in (("analysis", work), ("verification", replay_work)):
        started = {
            "phase": phase,
            "status": "started",
            "work": None,
            "unknown_execution_work": True,
        }
        artifacts[phase + "_started"] = artifact(
            packet, prefix, candidate_id, phase + "-started.json", started
        )
        invocation = {
            "phase": phase,
            "status": "returned",
            "work": phase_work,
            "unknown_execution_work": False,
            "wall_ns": 1,
            "process_cpu_ns": 1,
        }
        invocations.append(invocation)
        artifacts[phase + "_outcome"] = artifact(
            packet, prefix, candidate_id, phase + "-outcome.json", invocation
        )
        if phase == "analysis":
            artifacts["result"] = artifact(
                packet, prefix, candidate_id, "result.json", result
            )
            artifacts["checkpoint"] = artifact(
                packet, prefix, candidate_id, "checkpoint.json", checkpoint
            )
        else:
            artifacts["verification"] = artifact(
                packet, prefix, candidate_id, "verification.json", verification
            )
    performance = audit.performance_from_history(result)
    performance["load_factor_at_target"] = factor
    screens = audit.screens_from_performance(performance, plan, factor)
    return {
        "candidate_id": candidate_id,
        "status": "verified",
        "artifacts": artifacts,
        "quantities": pool_row["quantities"],
        "material_estimate": pool_row["material_estimate"],
        "performance": performance,
        "screens": screens,
        "full_reference_verification_pass": True,
        "selection_eligible": all(
            screen["status"] == "pass" for screen in screens.values()
        ),
        "invocations": invocations,
        "failure": None,
    }


def comparison(packet, name, plan, models, candidate_ids, factors):
    prefix = f"search/{name}"
    by_id = {row["candidate_id"]: row for row in plan["pool"]}
    candidates = {row["candidate_id"]: row for row in plan["candidates"]}
    identity = {
        "schema_version": audit.COMPARISON_SCHEMA,
        "source_revision": plan["source_revision"],
        "baseline_checksum": plan["baseline_checksum"],
        "candidates": [candidates[candidate_id] for candidate_id in candidate_ids[1:]],
        "control_request": plan["control_request"],
        "force_response_floor": plan["force_response_floor"],
        "history_limits": plan["history_limits"],
        "material_limits": plan["material_limits"],
        "terminal_limits": plan["terminal_limits"],
        "prices": plan["prices"],
        "price_table_hash": plan["price_table_hash"],
    }
    write_json(packet / prefix / "request.json", identity)
    rows = [
        make_row(
            packet,
            name,
            candidate_id,
            factors[candidate_id],
            plan,
            models[candidate_id],
            by_id[candidate_id],
        )
        for candidate_id in candidate_ids
    ]
    eligible = {row["candidate_id"]: row["selection_eligible"] for row in rows}
    selected = min(
        (candidate_id for candidate_id in candidate_ids if eligible[candidate_id]),
        key=lambda candidate_id: (
            by_id[candidate_id]["material_estimate"]["total"],
            candidate_id,
        ),
        default=None,
    )
    report = identity | {
        "request_hash": audit.sha(audit.canonical(identity)),
        "rows": rows,
        "candidate_denominator": len(rows),
        "verified_count": len(rows),
        "selected_candidate_id": selected,
        "selection_status": "selected"
        if selected is not None
        else "no_verified_feasible_candidate",
        "status": "complete",
    }
    report["report_hash"] = audit.sha(audit.canonical(report))
    write_json(packet / prefix / "comparison.json", report)
    work = audit.work_from_rows(rows)
    outcome = {
        "status": "completed",
        "comparison_hash": report["report_hash"],
        "comparison_path": f"{name}/comparison.json",
        "request_count": len(rows),
        "selected_candidate_id": selected,
        "execution_work": work,
        "unknown_work_until_outcome": False,
    }
    write_json(
        packet / "search" / f"{name}-started.json",
        {
            "status": "started",
            "plan_hash": plan["plan_hash"],
            "candidate_ids": candidate_ids,
            "unknown_work_until_outcome": True,
        },
    )
    write_json(packet / "search" / f"{name}-outcome.json", outcome)
    return report, eligible, outcome


def seal(packet):
    runner = audit.load(packet, "runner.json")
    result = audit.load(packet, "search/result.json")
    runner["search_report_hash"] = result["report_hash"]
    runner["search_report_sha256"] = audit.sha(
        (packet / "search/result.json").read_bytes()
    )
    runner["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in runner.items() if key != "report_hash"}
        )
    )
    write_json(packet / "runner.json", runner)
    files = []
    for path in packet.rglob("*"):
        if path.is_file() and path.name != "inventory.json":
            relative = path.relative_to(packet).as_posix()
            raw = path.read_bytes()
            files.append([relative, len(raw), audit.sha(raw)])
    files.sort(key=lambda row: row[0])
    write_json(
        packet / "inventory.json",
        {
            "schema_version": audit.INVENTORY_SCHEMA,
            "files": files,
            "inventory_sha256": audit.sha(audit.canonical(files)),
        },
    )


def reseal_price_result(packet, candidate_id, mutate):
    """Reseal every receipt affected by one changed original analysis result."""
    prefix = packet / "search/price_order"
    report_path = prefix / "comparison.json"
    report = audit.load(packet, "search/price_order/comparison.json")
    row = next(item for item in report["rows"] if item["candidate_id"] == candidate_id)
    result_path = prefix / candidate_id / "result.json"
    result = json.loads(result_path.read_bytes())
    mutate(result, row)
    result["result_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in result.items() if key != "result_hash"}
        )
    )
    write_json(result_path, result)
    verification_path = prefix / candidate_id / "verification.json"
    verification = json.loads(verification_path.read_bytes())
    verification["verified_result_hash"] = result["result_hash"]
    write_json(verification_path, verification)
    analysis_outcome_path = prefix / candidate_id / "analysis-outcome.json"
    write_json(analysis_outcome_path, row["invocations"][0])
    for key, path in (
        ("result", result_path),
        ("verification", verification_path),
        ("analysis_outcome", analysis_outcome_path),
    ):
        raw = path.read_bytes()
        row["artifacts"][key]["byte_length"] = len(raw)
        row["artifacts"][key]["sha256"] = audit.sha(raw)
    report["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in report.items() if key != "report_hash"}
        )
    )
    write_json(report_path, report)
    outcome_path = packet / "search/price_order-outcome.json"
    outcome = json.loads(outcome_path.read_bytes())
    outcome["comparison_hash"] = report["report_hash"]
    outcome["execution_work"] = audit.work_from_rows(report["rows"])
    write_json(outcome_path, outcome)
    result_path = packet / "search/result.json"
    search_result = json.loads(result_path.read_bytes())
    search_result["arms"]["price_order"] = outcome
    search_result["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in search_result.items() if key != "report_hash"}
        )
    )
    write_json(result_path, search_result)
    seal(packet)


def make_packet(tmp_path):
    repo, packet = tmp_path / "source", tmp_path / "packet"
    repo.mkdir()
    packet.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Synthetic Packet")
    git(repo, "config", "user.email", "synthetic@example.invalid")
    model = json.loads(
        (SOURCE / CAMPAIGN / "pin-roller-replication.model.json").read_bytes()
    )
    request = json.loads(
        (SOURCE / CAMPAIGN / "pin-roller-replication.request.json").read_bytes()
    )
    experiment = {
        "schema_version": "rc-fiber-design-experiment.v3",
        "candidates": [
            {"candidate_id": name, "changes": [{"section_id": "RC1", "width_m": width}]}
            for name, width in (("w34", 0.34), ("w38", 0.38))
        ],
        "history_limits": {
            "maximum_translation_m": 1.0,
            "maximum_absolute_fiber_strain": 1.0,
        },
        "material_history_limits": {
            "maximum_steel_accumulated_plastic_strain": 1.0,
            "maximum_concrete_tensile_damage": 1.0,
            "maximum_concrete_compressive_damage": 1.0,
        },
        "terminal_limits": None,
        "prices": {
            "concrete_per_m3": 100,
            "rebar_per_kg": 1,
            "currency": "KRW",
            "as_of": "2026-09-29",
            "source": "synthetic",
        },
    }
    floor_input = {
        "schema_version": "experimental-rc-control-force-response-floor.v1",
        **FLOOR,
    }
    inputs = dict(zip(audit.ROLES, (model, request, experiment, floor_input)))
    references = {}
    for role, value in inputs.items():
        relative = f"examples/research/{role}.json"
        path = repo / relative
        write_json(path, value)
        raw = path.read_bytes()
        (packet / "inputs").mkdir(exist_ok=True)
        (packet / "inputs" / f"{role}.json").write_bytes(raw)
        references[role] = {"path": relative, "sha256": audit.sha(raw)}
    protocol_path = "examples/research/protocol.json"
    protocol = {
        "schema_version": audit.PROTOCOL_SCHEMA,
        "inputs": references,
        "full_analysis_budget": 2,
        "reuse_line_search_assembly": False,
    }
    write_json(repo / protocol_path, protocol)
    runner_source = repo / "scripts/run_rc_force_floor_prospective.py"
    runner_source.parent.mkdir()
    shutil.copyfile(SOURCE / "scripts/run_rc_force_floor_prospective.py", runner_source)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "frozen synthetic protocol")
    revision = git(repo, "rev-parse", "HEAD")
    paths = {role: refs["path"] for role, refs in references.items()}
    digests = {role: refs["sha256"] for role, refs in references.items()}
    runner_sha = audit.sha(runner_source.read_bytes())
    pre = {
        "schema_version": audit.PREDECLARATION_SCHEMA,
        "source_revision": revision,
        "source_checkout_clean": True,
        "protocol_commit": revision,
        "protocol_path": protocol_path,
        "protocol_sha256": audit.sha((repo / protocol_path).read_bytes()),
        "input_paths": paths,
        "input_sha256": digests,
        "full_analysis_budget": 2,
        "reuse_line_search_assembly": False,
        "search_mode": "price_order_then_exhaustive_oracle",
        "runner_sha256": runner_sha,
    }
    pre["plan_hash"] = audit.sha(audit.canonical(pre))
    write_json(packet / "plan.json", pre)
    binding = {
        key: pre[key]
        for key in (
            "protocol_commit",
            "protocol_path",
            "protocol_sha256",
            "input_sha256",
        )
    }
    prices = dict(experiment["prices"])
    prices["concrete_per_m3"] = float(prices["concrete_per_m3"])
    prices["rebar_per_kg"] = float(prices["rebar_per_kg"])
    price_hash = audit.sha(
        audit.canonical({"schema_version": "declared-rc-material-prices.v1", **prices})
    )
    models, pool = {}, []
    for candidate_id, width in (("baseline", None), ("w34", 0.34), ("w38", 0.38)):
        candidate_model = deepcopy(model)
        if width is not None:
            candidate_model["sections"][0]["width_m"] = width
        models[candidate_id] = candidate_model
        model_path = f"pool/{candidate_id}.json"
        write_json(packet / "search" / model_path, candidate_model)
        raw = (packet / "search" / model_path).read_bytes()
        quantities = audit.quantities_from_model(candidate_model)
        estimate = audit.estimate_from_quantities(quantities, prices, price_hash)
        pool.append(
            {
                "candidate_id": candidate_id,
                "model_identity": audit.sha(audit.canonical(candidate_model)),
                "model_checksum": audit.sha(audit.canonical(candidate_model)),
                "model_artifact": {
                    "path": model_path,
                    "byte_length": len(raw),
                    "sha256": audit.sha(raw),
                },
                "quantities": quantities,
                "material_estimate": estimate,
            }
        )
    by_id = {row["candidate_id"]: row for row in pool}
    ordering = sorted(
        ("w34", "w38"),
        key=lambda candidate_id: (
            by_id[candidate_id]["material_estimate"]["total"],
            candidate_id,
        ),
    )
    plan = {
        "schema_version": audit.PLAN_SCHEMA,
        "source_revision": revision,
        "source_revision_is_attestation": False,
        "baseline_checksum": pool[0]["model_checksum"],
        "candidates": experiment["candidates"],
        "control_request": request,
        "force_response_floor": FLOOR,
        "history_limits": experiment["history_limits"],
        "material_limits": experiment["material_history_limits"],
        "terminal_limits": None,
        "prices": prices,
        "price_table_hash": price_hash,
        "pool": pool,
        "plans": {"price_order": {"ordering": ordering, "shortlist": ordering[:1]}},
        "full_analysis_budget_including_baseline": 2,
        "oracle_after_online_arm": True,
        "learned_policy_used": False,
        "line_search_assembly_reuse": False,
        "protocol_binding": binding,
    }
    plan["plan_hash"] = audit.sha(audit.canonical(plan))
    write_json(packet / "search/plan.json", plan)
    factors = {"baseline": 210.0, "w34": 100.0, "w38": 220.0}
    price, price_eligible, price_outcome = comparison(
        packet, "price_order", plan, models, ["baseline", *ordering[:1]], factors
    )
    oracle, oracle_eligible, oracle_outcome = comparison(
        packet, "exhaustive_oracle", plan, models, ["baseline", *ordering], factors
    )
    estimates = {key: value["material_estimate"] for key, value in by_id.items()}
    cost = audit.expected_cost_audit(
        plan, price, oracle, estimates, price_eligible, oracle_eligible
    )
    result = {
        "schema_version": audit.SEARCH_SCHEMA,
        "source_revision": revision,
        "plan_hash": plan["plan_hash"],
        "force_response_floor": FLOOR,
        "candidate_denominator": 3,
        "arms": {"price_order": price_outcome},
        "oracle": oracle_outcome,
        "candidate_cost_optimality_audit": cost,
        "claims": {
            "known_pool_cost_optimality_only": True,
            "learned_policy_used": False,
            "net_ai_savings_proved": False,
            "independent_physical_validation": False,
            "confirmed_currency_savings": False,
        },
    }
    result["report_hash"] = audit.sha(audit.canonical(result))
    write_json(packet / "search/result.json", result)
    runner = {
        "schema_version": audit.RUNNER_SCHEMA,
        "source_revision": revision,
        "clean_source_checkout": True,
        "protocol_commit": revision,
        "protocol_path": protocol_path,
        "protocol_sha256": pre["protocol_sha256"],
        "input_paths": paths,
        "input_sha256": digests,
        "full_analysis_budget": 2,
        "reuse_line_search_assembly": False,
        "outer_plan_hash": pre["plan_hash"],
        "outer_plan_sha256": audit.sha((packet / "plan.json").read_bytes()),
        "search_plan_hash": plan["plan_hash"],
        "search_plan_sha256": audit.sha((packet / "search/plan.json").read_bytes()),
        "search_report_hash": result["report_hash"],
        "search_report_sha256": audit.sha((packet / "search/result.json").read_bytes()),
        "runner_sha256": runner_sha,
        "independent_physical_validation": False,
        "learned_policy_used": False,
        "ai_benefit_claimed": False,
    }
    runner["report_hash"] = audit.sha(audit.canonical(runner))
    write_json(packet / "runner.json", runner)
    seal(packet)
    return repo, packet


def test_synthetic_packet_recomputes_signed_floor_and_cost_gap(tmp_path):
    repo, packet = make_packet(tmp_path)
    result = audit.audit_packet(repo, packet)
    assert result["status"] == "verified_packet_integrity", result["violations"]
    assert result["unknown_execution_work"] is False
    assert result["selected_candidate_id"] == "baseline"
    assert result["oracle_selected_candidate_id"] == "w38"
    assert result["selected_minus_pool_minimum_estimate"] > 0
    assert result["independent_physical_validation"] is False


def test_coherently_resealed_false_floor_screen_and_selection_reject(tmp_path):
    repo, packet = make_packet(tmp_path)
    for name in ("price_order", "exhaustive_oracle"):
        report_path = packet / "search" / name / "comparison.json"
        report = json.loads(report_path.read_bytes())
        cheap = next(row for row in report["rows"] if row["candidate_id"] == "w34")
        cheap["screens"]["load_factor_at_target"]["status"] = "pass"
        cheap["selection_eligible"] = True
        report["selected_candidate_id"] = "w34"
        report["report_hash"] = audit.sha(
            audit.canonical(
                {key: value for key, value in report.items() if key != "report_hash"}
            )
        )
        write_json(report_path, report)
        outcome_path = packet / "search" / f"{name}-outcome.json"
        outcome = json.loads(outcome_path.read_bytes())
        outcome["comparison_hash"] = report["report_hash"]
        outcome["selected_candidate_id"] = "w34"
        write_json(outcome_path, outcome)
    result_path = packet / "search/result.json"
    result = json.loads(result_path.read_bytes())
    result["arms"]["price_order"] = json.loads(
        (packet / "search/price_order-outcome.json").read_bytes()
    )
    result["oracle"] = json.loads(
        (packet / "search/exhaustive_oracle-outcome.json").read_bytes()
    )
    result["candidate_cost_optimality_audit"]["pool_minimum_feasible_candidate_ids"] = [
        "w34"
    ]
    result["candidate_cost_optimality_audit"]["pool_minimum_feasible_estimate"] = 1
    result["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in result.items() if key != "report_hash"}
        )
    )
    write_json(result_path, result)
    seal(packet)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert any(
        "screens differ from original result" in reason
        for reason in audited["violations"]
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("maximum_reversals", 0),
        ("experimental_pin_roller_beam", False),
        ("restart_input_sha256", "sha256:" + "0" * 64),
    ],
)
def test_resealed_result_request_identity_mismatch_reject(tmp_path, field, value):
    repo, packet = make_packet(tmp_path)

    def mutate(result, _row):
        result["request"][field] = value

    reseal_price_result(packet, "baseline", mutate)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert any(
        "original result contract or source binding differs" in reason
        for reason in audited["violations"]
    )


def test_resealed_result_configuration_with_valid_new_hash_reject(tmp_path):
    repo, packet = make_packet(tmp_path)

    def mutate(result, _row):
        configuration = result["request"]["configuration"]
        configuration["newton"]["max_iterations"] += 1
        result["request"]["configuration_hash"] = audit.sha(
            audit.canonical(configuration)
        )

    reseal_price_result(packet, "baseline", mutate)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert any(
        "original result contract or source binding differs" in reason
        for reason in audited["violations"]
    )


@pytest.mark.parametrize("changed_field", ["node_id", "component"])
def test_resealed_control_coordinate_must_follow_model_dof(tmp_path, changed_field):
    repo, packet = make_packet(tmp_path)

    def mutate(result, _row):
        if changed_field == "node_id":
            result["control"]["node_id"] = "N3"
            for response in result["response_history"]:
                response["node_displacements"][0]["node_id"] = "N3"
        else:
            result["control"]["component"] = "UX"
            for target, response in zip(
                result["request"]["targets_m"], result["response_history"]
            ):
                node = response["node_displacements"][0]
                node["UX_m"] = target
                node["UY_m"] = 0.0

    reseal_price_result(packet, "baseline", mutate)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert any(
        "force response coordinate differs from authored target" in reason
        for reason in audited["violations"]
    )


def test_resealed_understated_work_differs_from_accepted_path(tmp_path):
    repo, packet = make_packet(tmp_path)

    def mutate(result, row):
        understated = dict(row["invocations"][0]["work"])
        understated["known_linear_solve_count"] = 0
        row["invocations"][0]["work"] = understated
        result["metrics"]["control_work"] = understated

    reseal_price_result(packet, "baseline", mutate)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert any(
        "original solver work differs from accepted path" in reason
        for reason in audited["violations"]
    )


def test_coherently_listed_orphan_execution_file_reject(tmp_path):
    repo, packet = make_packet(tmp_path)
    write_json(packet / "search/price_order/orphan-attempt.json", {"attempts": 1})
    seal(packet)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert audited["unknown_execution_work"] is True
    assert any(
        "undeclared or missing execution files" in reason
        for reason in audited["violations"]
    )


def test_resealed_missing_fresh_replay_is_rejected_with_unknown_work(tmp_path):
    repo, packet = make_packet(tmp_path)
    verification_path = packet / "search/price_order/w34/verification.json"
    verification = json.loads(verification_path.read_bytes())
    verification["solver_replay_performed"] = False
    write_json(verification_path, verification)
    comparison_path = packet / "search/price_order/comparison.json"
    report = json.loads(comparison_path.read_bytes())
    row = next(row for row in report["rows"] if row["candidate_id"] == "w34")
    row["artifacts"]["verification"]["byte_length"] = verification_path.stat().st_size
    row["artifacts"]["verification"]["sha256"] = audit.sha(
        verification_path.read_bytes()
    )
    report["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in report.items() if key != "report_hash"}
        )
    )
    write_json(comparison_path, report)
    outcome_path = packet / "search/price_order-outcome.json"
    outcome = json.loads(outcome_path.read_bytes())
    outcome["comparison_hash"] = report["report_hash"]
    write_json(outcome_path, outcome)
    result_path = packet / "search/result.json"
    result = json.loads(result_path.read_bytes())
    result["arms"]["price_order"] = outcome
    result["report_hash"] = audit.sha(
        audit.canonical(
            {key: value for key, value in result.items() if key != "report_hash"}
        )
    )
    write_json(result_path, result)
    seal(packet)
    audited = audit.audit_packet(repo, packet)
    assert audited["status"] == "incomplete_or_unverifiable"
    assert audited["unknown_execution_work"] is True
    assert any(
        "full fresh replay incomplete" in reason for reason in audited["violations"]
    )


def test_cli_writes_audit_outside_packet_only(tmp_path):
    repo, packet = make_packet(tmp_path)
    inventory_before = (packet / "inventory.json").read_bytes()
    with pytest.raises(SystemExit):
        audit.main(
            [
                "--source",
                str(repo),
                "--packet",
                str(packet),
                "--output",
                str(packet / "audit.json"),
            ]
        )
    assert not (packet / "audit.json").exists()
    output = tmp_path / "audit.json"
    assert (
        audit.main(
            [
                "--source",
                str(repo),
                "--packet",
                str(packet),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_bytes())["status"] == "verified_packet_integrity"
    assert (packet / "inventory.json").read_bytes() == inventory_before
    existing = tmp_path / "existing-audit.json"
    existing.write_bytes(b"preserve existing report")
    with pytest.raises(FileExistsError):
        audit.main(
            [
                "--source",
                str(repo),
                "--packet",
                str(packet),
                "--output",
                str(existing),
            ]
        )
    assert existing.read_bytes() == b"preserve existing report"
