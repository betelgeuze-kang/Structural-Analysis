"""Run a committed RC force-factor learning protocol from exact clean source.

The protocol and all six input blobs must exist at the supplied ancestor
commit. The packet plan freezes both rosters before training or numerical work.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns, process_time_ns


PROTOCOL_SCHEMA = "experimental-rc-control-force-factor-protocol.v2"
PLAN_SCHEMA = "experimental-rc-control-force-factor-predeclaration.v2"
RUNNER_SCHEMA = "experimental-rc-control-force-factor-runner-receipt.v2"
INVENTORY_SCHEMA = "experimental-rc-control-force-factor-packet-inventory.v2"
SEARCH_PLAN_SCHEMA = "experimental-rc-control-force-floor-learned-search-plan.v2"
SEARCH_REPORT_SCHEMA = "experimental-rc-control-force-floor-learned-search.v2"
TRAINING_PLAN_SCHEMA = "experimental-rc-control-force-factor-training-plan.v1"
TRAINING_REPORT_SCHEMA = "experimental-rc-control-force-factor-training.v1"
ROLES = (
    "model",
    "request",
    "training_experiment",
    "experiment",
    "floor_plan",
    "learning_plan",
)
SCHEDULE = ("training", "price_order", "learned_order", "exhaustive_oracle")
FLOOR_PROVENANCE = "posthoc_threshold_from_prior_force_floor_packet"
LEARNING_PLAN_SCHEMA = "experimental-rc-control-force-factor-learning-plan.v1"
MAX_BYTES = {
    "protocol": 1024 * 1024,
    "model": 16 * 1024 * 1024,
    "request": 128 * 1024,
    "training_experiment": 1024 * 1024,
    "experiment": 1024 * 1024,
    "floor_plan": 128 * 1024,
    "learning_plan": 128 * 1024,
}
HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _strict_object(raw: bytes, name: str, maximum: int) -> dict:
    if len(raw) > maximum:
        raise ValueError(f"{name} exceeds the JSON byte bound")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key in {name}: {key}")
            value[key] = item
        return value

    def nonfinite(value):
        raise ValueError(f"nonfinite JSON token in {name}: {value}")

    result = json.loads(raw, object_pairs_hook=unique, parse_constant=nonfinite)
    if type(result) is not dict:
        raise ValueError(f"{name} must be a JSON object")
    return result


def _read(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(f"input exceeds byte bound: {path}")
    return raw


def _write_json(path: Path, value: dict) -> None:
    with path.open("xb") as stream:
        stream.write(_canonical(value) + b"\n")


def _git(repo: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"git command failed: {arguments[0]}")
    return (
        result.stdout.strip()
        if arguments[0] in ("rev-parse", "cat-file")
        else result.stdout
    )


def _committed_blob(repo: Path, revision: str, relative: str, maximum: int) -> bytes:
    object_name = f"{revision}:{relative}"
    if _git(repo, "cat-file", "-t", object_name) != b"blob":
        raise ValueError(f"committed input is not a blob: {relative}")
    size = int(_git(repo, "cat-file", "-s", object_name))
    if size > maximum:
        raise ValueError(f"committed input exceeds byte bound: {relative}")
    raw = _git(repo, "show", object_name)
    if len(raw) != size:
        raise ValueError(f"committed input byte length differs: {relative}")
    return raw


def _source_file(repo: Path, relative: str) -> Path:
    if (
        type(relative) is not str
        or not relative.startswith("examples/research/")
        or "\\" in relative
        or Path(relative).is_absolute()
        or ".." in Path(relative).parts
        or "." in Path(relative).parts
        or Path(relative).as_posix() != relative
    ):
        raise ValueError("source path must be repo-relative under examples/research/")
    path = repo / relative
    current = repo
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("source path contains a symlink")
    if not path.is_file() or not path.resolve().is_relative_to(repo.resolve()):
        raise ValueError(f"source file is unavailable: {relative}")
    return path


def _protocol_relative(repo: Path, argument: Path) -> str:
    if ".." in argument.parts:
        raise ValueError("protocol path traversal is not allowed")
    path = argument if argument.is_absolute() else repo / argument
    try:
        relative = path.relative_to(repo).as_posix()
    except ValueError as error:
        raise ValueError("protocol must be inside the source checkout") from error
    _source_file(repo, relative)
    return relative


def preflight_protocol(
    repo: Path,
    protocol_path: Path,
    protocol_commit: str,
    output: Path,
) -> dict:
    """Verify source, ancestor protocol, and every input before creating output."""
    repo = repo.resolve()
    output = output.resolve()
    if output == repo or output.is_relative_to(repo):
        raise ValueError("packet output must be outside the source checkout")
    if type(protocol_commit) is not str or REVISION.fullmatch(protocol_commit) is None:
        raise ValueError("40-character protocol commit required")
    if Path(_git(repo, "rev-parse", "--show-toplevel").decode()).resolve() != repo:
        raise ValueError("source path must be the Git checkout root")
    head = _git(repo, "rev-parse", "HEAD").decode()
    if REVISION.fullmatch(head) is None:
        raise ValueError("exact source HEAD required")
    if _git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("prospective run requires an exact clean source checkout")
    if _git(repo, "cat-file", "-t", protocol_commit) != b"commit":
        raise ValueError("protocol revision must be a commit")
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", protocol_commit, head],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if ancestor.returncode:
        raise ValueError("protocol commit is not an ancestor of source HEAD")
    relative = _protocol_relative(repo, protocol_path)
    working = _read(_source_file(repo, relative), MAX_BYTES["protocol"])
    frozen = _committed_blob(repo, protocol_commit, relative, MAX_BYTES["protocol"])
    if working != frozen:
        raise ValueError("protocol bytes differ from committed protocol")
    protocol = _strict_object(working, "protocol", MAX_BYTES["protocol"])
    if (
        set(protocol)
        != {
            "schema_version",
            "inputs",
            "baselines",
            "full_analysis_budget",
            "reuse_line_search_assembly",
            "schedule",
            "floor_selection_provenance",
            "independent_project_geometry_history_split",
        }
        or protocol["schema_version"] != PROTOCOL_SCHEMA
    ):
        raise ValueError("exact prospective protocol fields required")
    inputs = protocol["inputs"]
    if type(inputs) is not dict or set(inputs) != set(ROLES):
        raise ValueError("exact protocol input roles required")
    budget = protocol["full_analysis_budget"]
    if type(budget) is not int or not 2 <= budget <= 17:
        raise ValueError("bounded analysis budget required")
    if type(protocol["reuse_line_search_assembly"]) is not bool:
        raise ValueError("explicit line-search reuse boolean required")
    baselines = protocol["baselines"]
    if type(baselines) is not dict or set(baselines) != {"training", "evaluation"}:
        raise ValueError("exact training and evaluation baselines required")
    for role in ("training", "evaluation"):
        change = baselines[role]
        if (
            type(change) is not dict
            or set(change) != {"section_id", "width_m"}
            or change["section_id"] != "RC1"
            or type(change["width_m"]) not in (int, float)
            or not math.isfinite(change["width_m"])
            or change["width_m"] <= 0
        ):
            raise ValueError(f"exact positive {role} baseline width required")
    if (
        baselines["training"]["width_m"] == baselines["evaluation"]["width_m"]
        or protocol["schedule"] != list(SCHEDULE)
        or protocol["floor_selection_provenance"] != FLOOR_PROVENANCE
        or protocol["independent_project_geometry_history_split"] is not False
    ):
        raise ValueError("prospective split, schedule, or floor provenance invalid")
    paths, digests, blobs = {}, {}, {}
    for role in ROLES:
        reference = inputs[role]
        if type(reference) is not dict or set(reference) != {"path", "sha256"}:
            raise ValueError(f"exact {role} input reference required")
        relative_input = reference["path"]
        expected = reference["sha256"]
        if type(expected) is not str or HASH.fullmatch(expected) is None:
            raise ValueError(f"valid {role} input SHA256 required")
        working_input = _read(_source_file(repo, relative_input), MAX_BYTES[role])
        committed_input = _committed_blob(
            repo, protocol_commit, relative_input, MAX_BYTES[role]
        )
        if working_input != committed_input or _sha(working_input) != expected:
            raise ValueError(f"{role} input differs from committed protocol")
        paths[role] = relative_input
        digests[role] = expected
        blobs[role] = working_input
    runner_relative = "scripts/run_rc_force_factor_prospective.py"
    runner_raw = _read(repo / runner_relative, 1024 * 1024)
    if runner_raw != _committed_blob(repo, head, runner_relative, 1024 * 1024):
        raise ValueError("runner source differs from exact HEAD")
    return {
        "repo": repo,
        "output": output,
        "source_revision": head,
        "protocol_commit": protocol_commit,
        "protocol_path": relative,
        "protocol_sha256": _sha(working),
        "input_paths": paths,
        "input_sha256": digests,
        "input_blobs": blobs,
        "full_analysis_budget": budget,
        "reuse_line_search_assembly": protocol["reuse_line_search_assembly"],
        "baselines": baselines,
        "schedule": list(SCHEDULE),
        "floor_selection_provenance": FLOOR_PROVENANCE,
        "runner_sha256": _sha(runner_raw),
    }


def _decoded_inputs(frozen: dict) -> dict:
    """Derive and check both committed rosters without a numerical solve."""
    from structural_analysis.ai.fiber_frame_candidate_learning import (
        candidate_model_identity,
    )
    from structural_analysis.api.rc_fiber_frame_direct_control_request import (
        decode_bounded_rc_fiber_direct_control_request,
    )
    from structural_analysis.benchmark import fiber_frame_design as design
    from structural_analysis.benchmark.fiber_frame_design_cli import (
        read_design_experiment_with_material_history,
    )
    from structural_analysis.benchmark.rc_control_design import (
        _validated_force_response_floor,
    )
    from structural_analysis.benchmark.rc_control_force_floor_cli import (
        read_force_response_floor,
    )
    from structural_analysis.benchmark.rc_control_force_factor_learning import (
        control_force_factor_features,
    )
    from structural_analysis.io.neutral.loader import load_neutral_json_bytes

    paths = frozen["input_paths"]
    source_model = load_neutral_json_bytes(
        frozen["input_blobs"]["model"], source_path=paths["model"]
    )
    request = decode_bounded_rc_fiber_direct_control_request(
        frozen["input_blobs"]["request"]
    )
    if not request.experimental_pin_roller_beam or request.constant_nodal_loads:
        raise ValueError("fixed pin/roller control request without preload required")
    if source_model.units.force != "kN" or not source_model.loads:
        raise ValueError("positive kN reference-load model required")
    with TemporaryDirectory(prefix="rc-force-factor-inputs-") as directory:
        temporary = Path(directory)
        training_experiment = temporary / "training_experiment.json"
        experiment = temporary / "experiment.json"
        floor_plan = temporary / "floor_plan.json"
        training_experiment.write_bytes(frozen["input_blobs"]["training_experiment"])
        experiment.write_bytes(frozen["input_blobs"]["experiment"])
        floor_plan.write_bytes(frozen["input_blobs"]["floor_plan"])
        (
            train_candidates,
            train_prices,
            train_terminal,
            train_history,
            train_material,
        ) = read_design_experiment_with_material_history(training_experiment)
        candidates, prices, terminal, history, material = (
            read_design_experiment_with_material_history(experiment)
        )
        floor = read_force_response_floor(floor_plan)
    if (
        prices is None
        or history is None
        or material is None
        or train_prices is None
        or train_history is None
        or train_material is None
        or asdict(train_prices) != asdict(prices)
        or asdict(train_history) != asdict(history)
        or asdict(train_material) != asdict(material)
        or train_terminal != terminal
    ):
        raise ValueError("both rosters require identical declared prices and limits")
    if frozen["full_analysis_budget"] >= len(candidates) + 1:
        raise ValueError("online budget must be smaller than the full pool")
    learning = _strict_object(
        frozen["input_blobs"]["learning_plan"],
        "learning plan",
        MAX_BYTES["learning_plan"],
    )
    if (
        set(learning)
        != {
            "schema_version",
            "fit_method",
            "ridge",
            "ood_margin",
            "ranking_strategy",
        }
        or learning["schema_version"] != LEARNING_PLAN_SCHEMA
        or learning["fit_method"] != "svd-ridge-unpenalized-intercept.v2"
        or learning["ranking_strategy"] != "feasibility_then_price.v1"
        or type(learning["ridge"]) not in (int, float)
        or not math.isfinite(learning["ridge"])
        or learning["ridge"] <= 0
        or type(learning["ood_margin"]) not in (int, float)
        or not math.isfinite(learning["ood_margin"])
        or not 0 <= learning["ood_margin"] <= 1
    ):
        raise ValueError("exact bounded signed-factor learning plan required")

    def derive_baseline(role: str):
        change = frozen["baselines"][role]
        return design.apply_fiber_frame_section_changes(
            source_model,
            design.FiberFrameDesignCandidate(
                f"{role}_baseline",
                (design.FiberFrameSectionChange(**change),),
            ),
        )

    training_baseline = derive_baseline("training")
    evaluation_baseline = derive_baseline("evaluation")
    for baseline in (training_baseline, evaluation_baseline):
        _validated_force_response_floor(floor, baseline, request)

    def identities(baseline, alternatives):
        models = [baseline] + [
            design.apply_fiber_frame_section_changes(baseline, candidate)
            for candidate in alternatives
        ]
        physical = [
            candidate_model_identity(model, experimental_pin_roller_beam=True)
            for model in models
        ]
        contexts = {
            control_force_factor_features(model, request, floor)[1] for model in models
        }
        if len(set(physical)) != len(physical) or len(contexts) != 1:
            raise ValueError("unique physical models in one fixed context required")
        return physical, contexts.pop()

    training_ids, training_context = identities(training_baseline, train_candidates)
    evaluation_ids, evaluation_context = identities(evaluation_baseline, candidates)
    if (
        set(training_ids) & set(evaluation_ids)
        or training_context != evaluation_context
    ):
        raise ValueError("training/evaluation overlap or fixed context mismatch")
    return {
        "training": {
            "baseline": training_baseline,
            "candidates": train_candidates,
            "request": request,
            "force_response_floor": floor,
            "history_limits": train_history,
            "material_limits": train_material,
        },
        "search": {
            "baseline": evaluation_baseline,
            "candidates": candidates,
            "request": request,
            "force_response_floor": floor,
            "history_limits": history,
            "material_limits": material,
            "terminal_limits": terminal,
            "prices": prices,
        },
        "learning_plan": learning,
        "training_candidate_ids": [
            "baseline",
            *(c.candidate_id for c in train_candidates),
        ],
        "evaluation_candidate_ids": ["baseline", *(c.candidate_id for c in candidates)],
        "training_model_identities": training_ids,
        "evaluation_model_identities": evaluation_ids,
        "context_hash": training_context,
    }


def _require_runtime_source(repo: Path) -> None:
    """Load the solver package from this checkout, never an ambient install."""
    package_root = (repo / "src" / "structural_analysis").resolve()
    if not package_root.is_dir():
        raise ValueError("source checkout lacks the structural_analysis package")
    sys.path.insert(0, str(repo / "src"))
    importlib.import_module("structural_analysis")
    for name, module in tuple(sys.modules.items()):
        if name != "structural_analysis" and not name.startswith(
            "structural_analysis."
        ):
            continue
        origin = getattr(module, "__file__", None)
        if origin is None or not Path(origin).resolve().is_relative_to(package_root):
            raise ValueError(f"runtime package came from another checkout: {name}")


def _execute_training(study_inputs: dict, frozen: dict) -> tuple[object, dict]:
    from structural_analysis.benchmark.rc_control_force_factor_learning import (
        train_rc_control_force_factor_policy,
    )

    learning = study_inputs["learning_plan"]
    return train_rc_control_force_factor_policy(
        **study_inputs["training"],
        source_revision=frozen["source_revision"],
        output_directory=frozen["output"] / "training",
        ridge=learning["ridge"],
        ood_margin=learning["ood_margin"],
        fit_method=learning["fit_method"],
    )


def _checked_training(
    frozen: dict,
    study_inputs: dict,
    policy: object,
    returned: dict,
) -> tuple[dict, dict, str, str, str]:
    from structural_analysis.benchmark.rc_control_force_factor_learning import (
        RCControlForceFactorPolicy,
    )

    training = frozen["output"] / "training"
    plan_raw = _read(training / "plan.json", 16 * 1024 * 1024)
    policy_raw = _read(training / "policy.json", 2 * 1024 * 1024)
    report_raw = _read(training / "training.json", 16 * 1024 * 1024)
    plan = _strict_object(plan_raw, "training plan", 16 * 1024 * 1024)
    policy_saved = _strict_object(policy_raw, "training policy", 2 * 1024 * 1024)
    report = _strict_object(report_raw, "training report", 16 * 1024 * 1024)
    expected_floor = study_inputs["training"]["force_response_floor"]
    if (
        type(policy) is not RCControlForceFactorPolicy
        or policy_saved != policy.to_dict()
        or plan.get("schema_version") != TRAINING_PLAN_SCHEMA
        or plan.get("source_revision") != frozen["source_revision"]
        or plan.get("training_model_identities")
        != study_inputs["training_model_identities"]
        or plan.get("context_hash") != study_inputs["context_hash"]
        or plan.get("force_response_floor") != expected_floor
        or any(
            plan.get(key) != study_inputs["learning_plan"][key]
            for key in ("ridge", "ood_margin", "fit_method")
        )
        or report.get("schema_version") != TRAINING_REPORT_SCHEMA
        or report.get("source_revision") != frozen["source_revision"]
        or report.get("force_response_floor") != expected_floor
        or report.get("policy_hash") != policy.policy_hash
        or report.get("report_hash")
        != _sha(
            _canonical(
                {key: value for key, value in report.items() if key != "report_hash"}
            )
        )
        or _canonical(returned) != _canonical(report)
        or report.get("sample_count") != len(study_inputs["training_model_identities"])
        or report.get("fit", {}).get("status") != "completed"
        or report.get("fit", {}).get("unknown_fit_work_until_outcome") is not False
        or report.get("independent_generalization") is not False
        or report.get("net_savings_proved") is not False
    ):
        raise ValueError(
            "saved training differs from frozen protocol or has unknown work"
        )
    invocations = report.get("label_invocations")
    if (
        type(invocations) is not list
        or len(invocations) != 2 * report["sample_count"]
        or any(
            type(row) is not dict
            or row.get("unknown_execution_work") is not False
            or type(row.get("work")) is not dict
            or any(
                type(row["work"].get(key)) is not int or row["work"][key] < 0
                for key in (
                    "attempted_step_count",
                    "known_linear_solve_count",
                    "known_newton_iteration_count",
                    "unknown_solver_work_attempt_count",
                )
            )
            or row["work"]["unknown_solver_work_attempt_count"] != 0
            for row in invocations
        )
    ):
        raise ValueError("training analysis or fresh-replay work is unknown")
    return (policy_saved, report, _sha(plan_raw), _sha(policy_raw), _sha(report_raw))


def _execute_search(
    study_inputs: dict,
    frozen: dict,
    binding: dict,
    policy: object,
    training_report: dict,
) -> dict:
    from structural_analysis.benchmark.rc_control_force_floor_search import (
        compare_rc_control_force_floor_learned_search,
    )

    return compare_rc_control_force_floor_learned_search(
        **study_inputs["search"],
        policy=policy,
        training_report=training_report,
        source_revision=frozen["source_revision"],
        output_directory=frozen["output"] / "search",
        full_analysis_budget=frozen["full_analysis_budget"],
        reuse_line_search_assembly=frozen["reuse_line_search_assembly"],
        protocol_binding=binding,
    )


def _assert_source_unchanged(frozen: dict) -> None:
    repo = frozen["repo"]
    if _git(repo, "rev-parse", "HEAD").decode() != frozen["source_revision"] or _git(
        repo, "status", "--porcelain", "--untracked-files=all"
    ):
        raise ValueError("source checkout changed during prospective search")


def _checked_search(
    frozen: dict,
    binding: dict,
    returned: dict,
    policy: dict,
    training_report: dict,
) -> tuple[dict, dict, str, str]:
    search = frozen["output"] / "search"
    plan_raw = _read(search / "plan.json", 16 * 1024 * 1024)
    result_raw = _read(search / "result.json", 16 * 1024 * 1024)
    plan = _strict_object(plan_raw, "search plan", 16 * 1024 * 1024)
    result = _strict_object(result_raw, "search result", 16 * 1024 * 1024)
    if (
        plan.get("schema_version") != SEARCH_PLAN_SCHEMA
        or result.get("schema_version") != SEARCH_REPORT_SCHEMA
        or plan.get("source_revision") != frozen["source_revision"]
        or result.get("source_revision") != frozen["source_revision"]
        or plan.get("protocol_binding") != binding
        or plan.get("plan_hash")
        != _sha(
            _canonical(
                {key: value for key, value in plan.items() if key != "plan_hash"}
            )
        )
        or result.get("plan_hash") != plan["plan_hash"]
        or result.get("report_hash")
        != _sha(
            _canonical(
                {key: value for key, value in result.items() if key != "report_hash"}
            )
        )
        or _canonical(returned) != _canonical(result)
        or plan.get("learned_policy_used") is not True
        or plan.get("policy_hash") != policy["policy_hash"]
        or plan.get("training_report_hash") != training_report["report_hash"]
        or plan.get("full_analysis_budget_including_baseline_per_arm")
        != frozen["full_analysis_budget"]
        or plan.get("oracle_after_online_arms") is not True
        or set(plan.get("plans", {})) != {"price_order", "learned_order"}
        or plan.get("ranking_strategy") != "feasibility_then_price.v1"
        or plan.get("independent_project_geometry_history_split") is not False
        or result.get("claims", {}).get("learned_policy_used") is not True
        or result.get("claims", {}).get("independent_physical_validation") is not False
        or result.get("claims", {}).get("independent_generalization") is not False
        or result.get("claims", {}).get("net_ai_savings_proved") is not False
        or result.get("claims", {}).get("confirmed_currency_savings") is not False
        or result.get("historical_training_cost_counted_once_outside_online_arms")
        is not True
        or result.get("historical_training_execution_work", {}).get("unknown_work")
        is not False
        or set(result.get("arms", {})) != {"price_order", "learned_order"}
        or any(
            arm.get("unknown_work_until_outcome") is not False
            for arm in result.get("arms", {}).values()
        )
        or result.get("oracle", {}).get("unknown_work_until_outcome") is not False
    ):
        raise ValueError("saved search differs from frozen source/protocol binding")
    for field, filename, value in (
        ("policy_artifact", "policy.json", policy),
        ("historical_training_artifact", "historical-training.json", training_report),
    ):
        raw = _read(search / filename, 16 * 1024 * 1024)
        if (
            plan.get(field)
            != {"path": filename, "byte_length": len(raw), "sha256": _sha(raw)}
            or _strict_object(raw, filename, 16 * 1024 * 1024) != value
        ):
            raise ValueError(f"search {field} differs from completed training")
    return plan, result, _sha(plan_raw), _sha(result_raw)


def _inventory(packet: Path) -> dict:
    files = []
    for path in packet.rglob("*"):
        if path.is_symlink():
            raise ValueError("packet contains a symlink")
        if path.is_file() and path.relative_to(packet).as_posix() not in (
            "inventory.json",
            "audit.json",
        ):
            raw = path.read_bytes()
            files.append([path.relative_to(packet).as_posix(), len(raw), _sha(raw)])
    files.sort(key=lambda row: row[0])
    return {
        "schema_version": INVENTORY_SCHEMA,
        "files": files,
        "inventory_sha256": _sha(_canonical(files)),
    }


def run_packet(
    repo: Path, protocol_path: Path, protocol_commit: str, output: Path
) -> dict:
    runner_wall, runner_cpu = perf_counter_ns(), process_time_ns()
    frozen = preflight_protocol(repo, protocol_path, protocol_commit, output)
    _require_runtime_source(frozen["repo"])
    study_inputs = _decoded_inputs(frozen)
    packet = frozen["output"]
    packet.mkdir(parents=True, exist_ok=False)
    inputs = packet / "inputs"
    inputs.mkdir()
    for role in ROLES:
        with (inputs / f"{role}.json").open("xb") as stream:
            stream.write(frozen["input_blobs"][role])
    binding = {
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_sha256": frozen["input_sha256"],
    }
    plan = {
        "schema_version": PLAN_SCHEMA,
        "source_revision": frozen["source_revision"],
        "source_checkout_clean": True,
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_paths": frozen["input_paths"],
        "input_sha256": frozen["input_sha256"],
        "baselines": frozen["baselines"],
        "training_candidate_ids": study_inputs["training_candidate_ids"],
        "evaluation_candidate_ids": study_inputs["evaluation_candidate_ids"],
        "training_model_identities": study_inputs["training_model_identities"],
        "evaluation_model_identities": study_inputs["evaluation_model_identities"],
        "context_hash": study_inputs["context_hash"],
        "learning_plan": study_inputs["learning_plan"],
        "full_analysis_budget": frozen["full_analysis_budget"],
        "reuse_line_search_assembly": frozen["reuse_line_search_assembly"],
        "schedule": frozen["schedule"],
        "floor_selection_provenance": frozen["floor_selection_provenance"],
        "independent_project_geometry_history_split": False,
        "search_mode": "price_order_and_learned_order_then_exhaustive_oracle",
        "runner_sha256": frozen["runner_sha256"],
    }
    plan["plan_hash"] = _sha(_canonical(plan))
    _write_json(packet / "plan.json", plan)
    training_wall, training_cpu = perf_counter_ns(), process_time_ns()
    _write_json(
        packet / "training-started.json",
        {
            "status": "started",
            "outer_plan_hash": plan["plan_hash"],
            "unknown_work_until_outcome": True,
        },
    )
    try:
        policy, training_returned = _execute_training(study_inputs, frozen)
        _assert_source_unchanged(frozen)
        (
            policy_saved,
            training_report,
            training_plan_sha,
            training_policy_sha,
            training_report_sha,
        ) = _checked_training(frozen, study_inputs, policy, training_returned)
    except BaseException as error:
        _write_json(
            packet / "training-outcome.json",
            {
                "status": "interrupted"
                if isinstance(error, KeyboardInterrupt)
                else "raised",
                "exception_kind": type(error).__name__,
                "unknown_work_until_outcome": True,
                "wall_ns": perf_counter_ns() - training_wall,
                "process_cpu_ns": process_time_ns() - training_cpu,
                "timing_scope": "start_marker_training_labels_fit_source_and_artifact_checks_excluding_outcome_write",
            },
        )
        raise
    _write_json(
        packet / "training-outcome.json",
        {
            "status": "completed",
            "policy_hash": policy.policy_hash,
            "training_report_hash": training_report["report_hash"],
            "sample_count": training_report["sample_count"],
            "unknown_work_until_outcome": False,
            "wall_ns": perf_counter_ns() - training_wall,
            "process_cpu_ns": process_time_ns() - training_cpu,
            "timing_scope": "start_marker_training_labels_fit_source_and_artifact_checks_excluding_outcome_write",
        },
    )
    search_wall, search_cpu = perf_counter_ns(), process_time_ns()
    _write_json(
        packet / "search-started.json",
        {
            "status": "started",
            "outer_plan_hash": plan["plan_hash"],
            "training_report_hash": training_report["report_hash"],
            "unknown_work_until_outcome": True,
        },
    )
    try:
        returned = _execute_search(
            study_inputs, frozen, binding, policy, training_report
        )
        _assert_source_unchanged(frozen)
        search_plan, result, search_plan_sha, search_report_sha = _checked_search(
            frozen, binding, returned, policy_saved, training_report
        )
    except BaseException as error:
        _write_json(
            packet / "search-outcome.json",
            {
                "status": "interrupted"
                if isinstance(error, KeyboardInterrupt)
                else "raised",
                "exception_kind": type(error).__name__,
                "unknown_work_until_outcome": True,
                "wall_ns": perf_counter_ns() - search_wall,
                "process_cpu_ns": process_time_ns() - search_cpu,
                "timing_scope": "start_marker_search_arms_oracle_source_and_artifact_checks_excluding_outcome_write",
            },
        )
        raise
    _write_json(
        packet / "search-outcome.json",
        {
            "status": "completed",
            "search_plan_hash": search_plan["plan_hash"],
            "search_report_hash": result["report_hash"],
            "unknown_work_until_outcome": False,
            "wall_ns": perf_counter_ns() - search_wall,
            "process_cpu_ns": process_time_ns() - search_cpu,
            "timing_scope": "start_marker_search_arms_oracle_source_and_artifact_checks_excluding_outcome_write",
        },
    )
    receipt = {
        "schema_version": RUNNER_SCHEMA,
        "source_revision": frozen["source_revision"],
        "clean_source_checkout": True,
        "protocol_commit": frozen["protocol_commit"],
        "protocol_path": frozen["protocol_path"],
        "protocol_sha256": frozen["protocol_sha256"],
        "input_paths": frozen["input_paths"],
        "input_sha256": frozen["input_sha256"],
        "baselines": frozen["baselines"],
        "schedule": frozen["schedule"],
        "floor_selection_provenance": frozen["floor_selection_provenance"],
        "full_analysis_budget": frozen["full_analysis_budget"],
        "reuse_line_search_assembly": frozen["reuse_line_search_assembly"],
        "outer_plan_hash": plan["plan_hash"],
        "outer_plan_sha256": _sha((packet / "plan.json").read_bytes()),
        "training_plan_sha256": training_plan_sha,
        "training_policy_hash": policy_saved["policy_hash"],
        "training_policy_sha256": training_policy_sha,
        "training_report_hash": training_report["report_hash"],
        "training_report_sha256": training_report_sha,
        "search_plan_hash": search_plan["plan_hash"],
        "search_plan_sha256": search_plan_sha,
        "search_report_hash": result["report_hash"],
        "search_report_sha256": search_report_sha,
        "runner_sha256": frozen["runner_sha256"],
        "runner_wall_ns": perf_counter_ns() - runner_wall,
        "runner_process_cpu_ns": process_time_ns() - runner_cpu,
        "runner_timing_scope": "preflight_decode_plan_training_search_phase_markers_and_IO_excluding_final_receipt_inventory_write",
        "unknown_execution_work": False,
        "independent_physical_validation": False,
        "independent_generalization": False,
        "learned_policy_used": True,
        "ai_benefit_claimed": False,
    }
    receipt["report_hash"] = _sha(_canonical(receipt))
    _write_json(packet / "runner.json", receipt)
    _write_json(packet / "inventory.json", _inventory(packet))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--protocol-commit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    receipt = run_packet(repo, args.protocol, args.protocol_commit, args.output)
    print(
        json.dumps(
            {
                "source_revision": receipt["source_revision"],
                "protocol_sha256": receipt["protocol_sha256"],
                "search_report_hash": receipt["search_report_hash"],
                "report_hash": receipt["report_hash"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
