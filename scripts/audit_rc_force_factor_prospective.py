"""Read-only stdlib audit of a prospective signed force-factor learning packet.

The audit checks committed inputs, recorded solver/replay artifacts and a
separately recomputed ridge fit. It does not rerun the solver or establish
independent physical validation or independent-project generalization.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
import math
from pathlib import Path
import re
import subprocess


# Reuse the older independent *audit* arithmetic and artifact checks. This
# module never imports the producing structural_analysis package or NumPy.
_common_spec = spec_from_file_location(
    "_rc_force_floor_audit_common",
    Path(__file__).with_name("audit_rc_force_floor_prospective.py"),
)
assert _common_spec is not None and _common_spec.loader is not None
common = module_from_spec(_common_spec)
_common_spec.loader.exec_module(common)

AuditError = common.AuditError
require = common.require
canonical = common.canonical
sha = common.sha
same = common.same
decode = common.decode
file_bytes = common.file_bytes
load = common.load
check_self_hash = common.check_self_hash
finite = common.finite

PROTOCOL_SCHEMA = "experimental-rc-control-force-factor-protocol.v2"
PREDECLARATION_SCHEMA = "experimental-rc-control-force-factor-predeclaration.v2"
RUNNER_SCHEMA = "experimental-rc-control-force-factor-runner-receipt.v2"
INVENTORY_SCHEMA = "experimental-rc-control-force-factor-packet-inventory.v2"
TRAINING_PLAN_SCHEMA = "experimental-rc-control-force-factor-training-plan.v1"
TRAINING_SCHEMA = "experimental-rc-control-force-factor-training.v1"
POLICY_SCHEMA = "experimental-rc-control-force-factor-policy.v1"
SEARCH_PLAN_SCHEMA = "experimental-rc-control-force-floor-learned-search-plan.v2"
SEARCH_SCHEMA = "experimental-rc-control-force-floor-learned-search.v2"
COST_SCHEMA = "rc-control-candidate-cost-optimality.v4"
AUDIT_SCHEMA = "experimental-rc-control-force-factor-packet-audit.v2"
LEARNING_PLAN_SCHEMA = "experimental-rc-control-force-factor-learning-plan.v1"
ROLES = (
    "model",
    "request",
    "training_experiment",
    "experiment",
    "floor_plan",
    "learning_plan",
)
SCHEDULE = ["training", "price_order", "learned_order", "exhaustive_oracle"]
FIT_METHOD = "svd-ridge-unpenalized-intercept.v2"
RANKING = "feasibility_then_price.v1"
FLOOR_PROVENANCE = "posthoc_threshold_from_prior_force_floor_packet"
FEATURE_FIELDS = (
    "width_m",
    "depth_m",
    "cover_m",
    "top_bar_count",
    "bottom_bar_count",
    "bar_area_m2",
)
FEATURE_NAMES = [
    "member_count",
    "total_length_m",
    "gross_concrete_volume_m3",
    "longitudinal_rebar_volume_m3",
    "mean_width_m",
    "mean_depth_m",
    "mean_cover_m",
    "sum_rectangular_inertia_m4",
    "sum_top_bar_count",
    "sum_bottom_bar_count",
    "sum_bar_area_m2",
] + [f"member_{i}_{field}" for i in range(15) for field in FEATURE_FIELDS]
TARGETS = [
    "terminal_maximum_translation_m",
    "terminal_maximum_absolute_fiber_strain",
    "maximum_translation_m",
    "maximum_absolute_fiber_strain",
    "maximum_steel_accumulated_plastic_strain",
    "maximum_concrete_tensile_damage",
    "maximum_concrete_compressive_damage",
    "load_factor_at_target",
]
ROW_FILES = common.ROW_ARTIFACT_FILES
POLICY_KEYS = {
    "schema_version",
    "context_hash",
    "force_target",
    "features",
    "targets",
    "mean",
    "scale",
    "minimum",
    "maximum",
    "target_scale",
    "weights",
    "ridge",
    "ood_margin",
    "training_model_identities",
    "training_sample_hashes",
    "label_comparison_hash",
    "policy_hash",
}


def close(left, right, *, rel=2e-8, absolute=2e-9):
    return (
        finite(left)
        and finite(right)
        and math.isclose(left, right, rel_tol=rel, abs_tol=absolute)
    )


def vector_close(left, right, label):
    require(
        type(left) is list
        and len(left) == len(right)
        and all(close(a, b) for a, b in zip(left, right, strict=True)),
        f"{label} differs from independent arithmetic",
    )


def _normalized_prices(declared):
    """Mirror the public price parser's finite numeric normalization."""
    require(
        type(declared) is dict
        and set(declared)
        == {"concrete_per_m3", "rebar_per_kg", "currency", "as_of", "source"},
        "exact declared price table required",
    )
    prices = dict(declared)
    for key in ("concrete_per_m3", "rebar_per_kg"):
        require(
            finite(prices[key]) and prices[key] >= 0,
            f"nonnegative finite declared {key} required",
        )
        prices[key] = float(prices[key])
    return prices


def _git_blob(source, revision, relative):
    common.relative_path(relative)
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "invalid Git revision")
    return common.git_blob(source, revision, relative)


def _inventory(packet):
    inventory = load(packet, "inventory.json")
    require(
        inventory.get("schema_version") == INVENTORY_SCHEMA,
        "V2 inventory schema mismatch",
    )
    files = inventory.get("files")
    require(type(files) is list, "V2 inventory files missing")
    expected = []
    for path in packet.rglob("*"):
        require(not path.is_symlink(), f"packet contains symbolic link: {path.name}")
        if path.is_dir():
            continue
        require(path.is_file(), f"packet contains non-file: {path.name}")
        relative = path.relative_to(packet).as_posix()
        if relative in ("inventory.json", "audit.json"):
            continue
        raw = file_bytes(packet, relative)
        expected.append([relative, len(raw), sha(raw)])
    expected.sort(key=lambda row: row[0])
    require(same(files, expected), "V2 packet inventory differs from present files")
    require(
        inventory.get("inventory_sha256") == sha(canonical(files)),
        "V2 inventory hash mismatch",
    )
    return inventory


def _provenance(source, packet):
    pre, runner = load(packet, "plan.json"), load(packet, "runner.json")
    require(
        pre.get("schema_version") == PREDECLARATION_SCHEMA,
        "V2 predeclaration schema mismatch",
    )
    require(runner.get("schema_version") == RUNNER_SCHEMA, "V2 runner schema mismatch")
    check_self_hash(pre, "plan_hash", "V2 predeclaration")
    check_self_hash(runner, "report_hash", "V2 runner receipt")
    revision, commit = pre.get("source_revision"), pre.get("protocol_commit")
    require(
        type(revision) is str and re.fullmatch(r"[0-9a-f]{40}", revision),
        "invalid source revision",
    )
    require(
        type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit),
        "invalid protocol commit",
    )
    ancestor = subprocess.run(
        ["git", "-C", str(source), "merge-base", "--is-ancestor", commit, revision],
        capture_output=True,
        check=False,
    )
    require(ancestor.returncode == 0, "protocol commit is not an ancestor of source")
    protocol_path = pre.get("protocol_path")
    require(
        type(protocol_path) is str and protocol_path.startswith("examples/research/"),
        "protocol path outside research inputs",
    )
    original = _git_blob(source, commit, protocol_path)
    require(
        original == _git_blob(source, revision, protocol_path),
        "source changed committed V2 protocol bytes",
    )
    require(
        pre.get("protocol_sha256") == sha(original), "V2 protocol byte hash mismatch"
    )
    protocol = decode(original, protocol_path)
    require(
        type(protocol) is dict
        and set(protocol)
        == {
            "schema_version",
            "inputs",
            "baselines",
            "full_analysis_budget",
            "reuse_line_search_assembly",
            "schedule",
            "floor_selection_provenance",
            "independent_project_geometry_history_split",
        }
        and protocol["schema_version"] == PROTOCOL_SCHEMA,
        "exact V2 protocol fields required",
    )
    require(
        pre.get("source_checkout_clean") is True
        and runner.get("clean_source_checkout") is True,
        "clean source checkout receipts missing",
    )
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
    ):
        require(same(runner.get(key), pre.get(key)), f"runner {key} binding mismatch")
    for key in (
        "baselines",
        "schedule",
        "floor_selection_provenance",
        "full_analysis_budget",
        "reuse_line_search_assembly",
        "independent_project_geometry_history_split",
    ):
        require(
            same(pre.get(key), protocol.get(key)),
            f"predeclaration {key} differs from protocol",
        )
    require(
        pre["schedule"] == SCHEDULE
        and pre["floor_selection_provenance"] == FLOOR_PROVENANCE
        and pre["independent_project_geometry_history_split"] is False
        and pre.get("search_mode")
        == "price_order_and_learned_order_then_exhaustive_oracle"
        and type(pre["full_analysis_budget"]) is int
        and type(pre["reuse_line_search_assembly"]) is bool,
        "V2 schedule, budget, or evidence scope invalid",
    )
    baselines = pre["baselines"]
    require(
        type(baselines) is dict
        and set(baselines) == {"training", "evaluation"}
        and all(
            type(baselines[role]) is dict
            and set(baselines[role]) == {"section_id", "width_m"}
            and baselines[role]["section_id"] == "RC1"
            and finite(baselines[role]["width_m"])
            and baselines[role]["width_m"] > 0
            for role in ("training", "evaluation")
        )
        and baselines["training"]["width_m"] != baselines["evaluation"]["width_m"],
        "V2 training/evaluation baseline split invalid",
    )
    refs, paths, digests = (
        protocol["inputs"],
        pre.get("input_paths"),
        pre.get("input_sha256"),
    )
    require(
        type(refs) is dict
        and type(paths) is dict
        and type(digests) is dict
        and set(refs) == set(paths) == set(digests) == set(ROLES),
        "V2 protocol input roster mismatch",
    )
    inputs = {}
    for role in ROLES:
        reference = refs[role]
        require(
            type(reference) is dict
            and set(reference) == {"path", "sha256"}
            and reference["path"] == paths[role]
            and reference["sha256"] == digests[role]
            and paths[role].startswith("examples/research/"),
            f"V2 {role} input binding mismatch",
        )
        raw = file_bytes(packet, f"inputs/{role}.json")
        require(
            sha(raw) == digests[role]
            and raw == _git_blob(source, commit, paths[role])
            and raw == _git_blob(source, revision, paths[role]),
            f"V2 {role} differs from committed input",
        )
        inputs[role] = decode(raw, f"inputs/{role}.json")
    runner_raw = _git_blob(
        source, revision, "scripts/run_rc_force_factor_prospective.py"
    )
    require(
        pre.get("runner_sha256") == sha(runner_raw)
        and runner.get("runner_sha256") == sha(runner_raw),
        "V2 runner committed byte hash mismatch",
    )
    require(
        runner.get("outer_plan_hash") == pre["plan_hash"]
        and runner.get("outer_plan_sha256") == sha(file_bytes(packet, "plan.json")),
        "V2 runner outer plan binding mismatch",
    )
    require(
        runner.get("independent_physical_validation") is False
        and runner.get("independent_generalization") is False
        and runner.get("learned_policy_used") is True
        and runner.get("ai_benefit_claimed") is False,
        "V2 runner overclaims evidence",
    )
    return pre, runner, inputs


def _change_width(model, change):
    require(
        type(change) is dict
        and set(change) == {"section_id", "width_m"}
        and change["section_id"] == "RC1"
        and finite(change["width_m"])
        and change["width_m"] > 0,
        "baseline width declaration invalid",
    )
    result = deepcopy(model)
    sections = [
        section
        for section in result["sections"]
        if section["id"] == change["section_id"]
    ]
    require(len(sections) == 1, "authored RC1 section unavailable")
    sections[0]["width_m"] = change["width_m"]
    return result


def _candidate_model(baseline, candidate):
    result = deepcopy(baseline)
    sections = {section["id"]: section for section in result["sections"]}
    require(
        type(candidate) is dict
        and set(candidate) == {"candidate_id", "changes"}
        and type(candidate["changes"]) is list,
        "candidate declaration invalid",
    )
    for change in candidate["changes"]:
        require(
            type(change) is dict and change.get("section_id") in sections,
            "candidate section unavailable",
        )
        sections[change["section_id"]].update(
            {
                key: value
                for key, value in change.items()
                if key != "section_id" and value is not None
            }
        )
    return result


def _features(model):
    """Independently reconstruct this bounded RC section descriptor profile."""
    nodes = {row["id"]: row["coordinates"] for row in model["nodes"]}
    sections = {row["id"]: row for row in model["sections"]}
    members = sorted(
        model["elements"],
        key=lambda row: (tuple(nodes[row["nodes"][0]]), tuple(nodes[row["nodes"][1]])),
    )
    require(1 <= len(members) <= 15, "bounded feature member count required")
    assigned = [sections[row["section"]] for row in members]
    lengths = [
        math.dist(nodes[row["nodes"][0]], nodes[row["nodes"][1]]) for row in members
    ]
    n = len(members)

    def steel_area(section):
        common_area = section["bar_area_m2"]
        return (
            section["top_bar_count"] * section.get("top_bar_area_m2", common_area)
            + section["bottom_bar_count"]
            * section.get("bottom_bar_area_m2", common_area)
            + sum(
                layer["bar_count"] * common_area
                for layer in section.get("intermediate_steel_layers", [])
            )
        )

    values = [
        float(n),
        math.fsum(lengths),
        math.fsum(
            s["width_m"] * s["depth_m"] * length
            for s, length in zip(assigned, lengths, strict=True)
        ),
        math.fsum(
            steel_area(s) * length for s, length in zip(assigned, lengths, strict=True)
        ),
        *(
            math.fsum(float(s[key]) for s in assigned) / n
            for key in ("width_m", "depth_m", "cover_m")
        ),
        math.fsum(s["width_m"] * s["depth_m"] ** 3 / 12.0 for s in assigned),
        math.fsum(s["top_bar_count"] for s in assigned),
        math.fsum(s["bottom_bar_count"] for s in assigned),
        math.fsum(s["bar_area_m2"] for s in assigned),
        *(s[key] for s in assigned for key in FEATURE_FIELDS),
        *((0.0,) * ((15 - n) * len(FEATURE_FIELDS))),
    ]
    require(
        len(values) == len(FEATURE_NAMES) and all(finite(v) for v in values),
        "bounded finite feature vector unavailable",
    )
    return [float(value) for value in values]


def _solve_spd(matrix, vector):
    """Solve a small positive-definite ridge system without NumPy."""
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            residual = matrix[i][j] - math.fsum(
                lower[i][k] * lower[j][k] for k in range(j)
            )
            if i == j:
                require(
                    finite(residual) and residual > 0,
                    "ridge system not positive definite",
                )
                lower[i][j] = math.sqrt(residual)
            else:
                lower[i][j] = residual / lower[j][j]
    y = [0.0] * n
    for i in range(n):
        y[i] = (vector[i] - math.fsum(lower[i][k] * y[k] for k in range(i))) / lower[i][
            i
        ]
    x = [0.0] * n
    for i in reversed(range(n)):
        x[i] = (y[i] - math.fsum(lower[k][i] * x[k] for k in range(i + 1, n))) / lower[
            i
        ][i]
    return x


def _centered_ridge(samples, ridge):
    """Dual ridge fit, algebraically equivalent to the producer's centered SVD."""
    x = [row["features"] for row in samples]
    y = [row["targets"] for row in samples]
    n, features, targets = len(x), len(x[0]), len(y[0])
    require(
        2 <= n <= 17
        and features == len(FEATURE_NAMES)
        and targets == len(TARGETS)
        and finite(ridge)
        and ridge > 0,
        "bounded centered ridge sample set required",
    )
    for row in x + y:
        require(all(finite(value) for value in row), "nonfinite policy training sample")
    minimum = [min(row[j] for row in x) for j in range(features)]
    maximum = [max(row[j] for row in x) for j in range(features)]
    mean = [math.fsum(row[j] for row in x) / n for j in range(features)]
    scale = [
        math.sqrt(math.fsum((row[j] - mean[j]) ** 2 for row in x) / n)
        for j in range(features)
    ]
    for j in range(features):
        if minimum[j] == maximum[j]:
            mean[j], scale[j] = minimum[j], 1.0
        elif scale[j] == 0:
            scale[j] = 1.0
    target_mean = [math.fsum(row[k] for row in y) / n for k in range(targets)]
    target_scale = [
        math.sqrt(math.fsum((row[k] - target_mean[k]) ** 2 for row in y) / n)
        for k in range(targets)
    ]
    for k in range(targets):
        if min(row[k] for row in y) == max(row[k] for row in y):
            target_mean[k], target_scale[k] = y[0][k], 1.0
        elif target_scale[k] == 0:
            target_scale[k] = 1.0
    z = [[(row[j] - mean[j]) / scale[j] for j in range(features)] for row in x]
    z_mean = [math.fsum(row[j] for row in z) / n for j in range(features)]
    centered = [[row[j] - z_mean[j] for j in range(features)] for row in z]
    gram = [
        [
            math.fsum(centered[i][j] * centered[h][j] for j in range(features))
            + (ridge if i == h else 0.0)
            for h in range(n)
        ]
        for i in range(n)
    ]
    weights = [[0.0] * targets for _ in range(features + 1)]
    for k in range(targets):
        scaled = [(row[k] - target_mean[k]) / target_scale[k] for row in y]
        dual = _solve_spd(gram, scaled)
        for j in range(features):
            weights[j][k] = math.fsum(centered[i][j] * dual[i] for i in range(n))
        weights[features][k] = target_mean[k] / target_scale[k] - math.fsum(
            z_mean[j] * weights[j][k] for j in range(features)
        )
    return {
        "minimum": minimum,
        "maximum": maximum,
        "mean": mean,
        "scale": scale,
        "target_scale": target_scale,
        "weights": weights,
    }


def check_policy_fit(policy, samples, learning):
    """Reject a coherently resealed policy whose weights do not fit its labels."""
    require(
        type(policy) is dict
        and set(policy) == POLICY_KEYS
        and policy.get("schema_version") == POLICY_SCHEMA,
        "force-factor policy schema mismatch",
    )
    check_self_hash(policy, "policy_hash", "force-factor policy")
    require(
        policy.get("features") == FEATURE_NAMES
        and policy.get("targets") == TARGETS
        and policy.get("ridge") == learning["ridge"]
        and policy.get("ood_margin") == learning["ood_margin"],
        "force-factor policy fit profile differs from frozen learning plan",
    )
    expected = _centered_ridge(samples, learning["ridge"])
    for key in ("minimum", "maximum", "mean", "scale", "target_scale"):
        vector_close(policy.get(key), expected[key], f"policy {key}")
    actual_weights = policy.get("weights")
    require(
        type(actual_weights) is list
        and len(actual_weights) == len(expected["weights"]),
        "policy weight dimensions differ from frozen features",
    )
    for actual, expected_row in zip(actual_weights, expected["weights"], strict=True):
        vector_close(actual, expected_row, "policy weights")
    return expected


def _check_row(packet, prefix, row, plan, model, estimate):
    """Audit one original analysis and fresh replay against its saved result."""
    candidate_id = row["candidate_id"]
    artifacts = row.get("artifacts")
    required = {
        "model": "model.json",
        "analysis_started": "analysis-started.json",
        "analysis_outcome": "analysis-outcome.json",
        "result": "result.json",
        "checkpoint": "checkpoint.json",
        "verification_started": "verification-started.json",
        "verification_outcome": "verification-outcome.json",
        "verification": "verification.json",
    }
    require(
        type(artifacts) is dict and set(artifacts) == set(required),
        f"{prefix}/{candidate_id}: original artifact roster incomplete",
    )
    values = {}
    for key, filename in required.items():
        descriptor = artifacts[key]
        require(
            type(descriptor) is dict
            and descriptor.get("path") == f"{candidate_id}/{filename}",
            f"{prefix}/{candidate_id}: {key} artifact path changed",
        )
        values[key] = common.check_artifact(packet, prefix, descriptor)
    require(
        same(values["model"], model),
        f"{prefix}/{candidate_id}: model differs from frozen input",
    )
    require(
        same(row.get("quantities"), common.quantities_from_model(model)),
        f"{prefix}/{candidate_id}: quantities differ from model",
    )
    require(
        same(row.get("material_estimate"), estimate),
        f"{prefix}/{candidate_id}: estimate differs from frozen price table",
    )
    invocations = row.get("invocations")
    require(
        type(invocations) is list and len(invocations) == 2,
        f"{prefix}/{candidate_id}: analysis and fresh replay required",
    )
    for phase, invocation in zip(
        ("analysis", "verification"), invocations, strict=True
    ):
        require(
            invocation.get("phase") == phase
            and invocation.get("status") == "returned"
            and invocation.get("unknown_execution_work") is False
            and same(values[phase + "_outcome"], invocation)
            and values[phase + "_started"].get("status") == "started"
            and values[phase + "_started"].get("unknown_execution_work") is True,
            f"{prefix}/{candidate_id}: {phase} work receipt unknown",
        )
    common.work_from_rows([row])
    result, checkpoint, verification = (
        values[key] for key in ("result", "checkpoint", "verification")
    )
    check_self_hash(result, "result_hash", f"{prefix}/{candidate_id} result")
    require(
        result.get("contract_pass") is True
        and result.get("model", {}).get("canonical_model_checksum")
        == sha(canonical(model))
        and same(
            result.get("request"),
            common.expected_result_request(
                plan["control_request"],
                reuse_line_search_assembly=plan["line_search_assembly_reuse"],
            ),
        ),
        f"{prefix}/{candidate_id}: original result contract differs",
    )
    require(
        same(result.get("metrics", {}).get("control_work"), invocations[0]["work"])
        and same(
            result.get("path", {}).get("metrics", {}).get("total_work"),
            invocations[0]["work"],
        )
        and invocations[0]["work"]["attempted_step_count"]
        >= len(plan["control_request"]["targets_m"]),
        f"{prefix}/{candidate_id}: original solver work differs",
    )
    checkpoint_raw = file_bytes(packet, f"{prefix}/{artifacts['checkpoint']['path']}")
    require(
        result.get("checkpoint")
        == {"sha256": sha(checkpoint_raw), "byte_length": len(checkpoint_raw)}
        and type(checkpoint) is dict,
        f"{prefix}/{candidate_id}: checkpoint binding mismatch",
    )
    require(
        verification.get("status") == "valid_artifact"
        and all(
            verification.get(key) is True
            for key in (
                "artifact_contract_pass",
                "contract_pass",
                "physical_path_complete",
                "fresh_source_execution_invoked",
                "solver_replay_performed",
            )
        )
        and verification.get("verified_result_hash") == result["result_hash"]
        and verification.get("errors") == []
        and verification.get("unavailable_execution_work") is False
        and same(verification.get("replay_control_work"), invocations[1]["work"])
        and row.get("full_reference_verification_pass") is True
        and row.get("status") == "verified",
        f"{prefix}/{candidate_id}: fresh reference replay incomplete",
    )
    factor = common.indexed_factor(
        result, plan["control_request"], plan["force_response_floor"], model
    )
    performance = common.performance_from_history(result)
    performance["load_factor_at_target"] = factor
    screens = common.screens_from_performance(performance, plan, factor)
    require(
        same(row.get("performance"), performance),
        f"{prefix}/{candidate_id}: performance differs from original history",
    )
    require(
        same(row.get("screens"), screens),
        f"{prefix}/{candidate_id}: screens differ from original indexed factor",
    )
    eligible = all(screen["status"] == "pass" for screen in screens.values())
    require(
        row.get("selection_eligible") is eligible,
        f"{prefix}/{candidate_id}: eligibility differs from screens",
    )
    return eligible


def _check_training(packet, pre, inputs):
    model, experiment = inputs["model"], inputs["training_experiment"]
    request = inputs["request"]
    floor = {
        key: value
        for key, value in inputs["floor_plan"].items()
        if key != "schema_version"
    }
    learning = inputs["learning_plan"]
    require(
        learning.get("schema_version") == LEARNING_PLAN_SCHEMA
        and set(learning)
        == {
            "schema_version",
            "fit_method",
            "ridge",
            "ood_margin",
            "ranking_strategy",
        }
        and learning["fit_method"] == FIT_METHOD
        and learning["ranking_strategy"] == RANKING
        and finite(learning["ridge"])
        and learning["ridge"] > 0
        and finite(learning["ood_margin"])
        and 0 <= learning["ood_margin"] <= 1
        and same(pre.get("learning_plan"), learning),
        "frozen learning plan mismatch",
    )
    require(
        experiment.get("schema_version") == "rc-fiber-design-experiment.v3",
        "training experiment schema mismatch",
    )
    candidates = experiment["candidates"]
    ids = ["baseline", *(candidate["candidate_id"] for candidate in candidates)]
    require(
        2 <= len(ids) <= 17
        and len(set(ids)) == len(ids)
        and pre.get("training_candidate_ids") == ids,
        "training candidate roster differs from predeclaration",
    )
    baseline = _change_width(model, pre["baselines"]["training"])
    models = {"baseline": baseline}
    for candidate in candidates:
        models[candidate["candidate_id"]] = _candidate_model(baseline, candidate)
    require(
        len({sha(canonical(value)) for value in models.values()}) == len(models),
        "duplicate training models",
    )
    training_plan = load(packet, "training/plan.json")
    require(
        training_plan.get("schema_version") == TRAINING_PLAN_SCHEMA
        and training_plan.get("source_revision") == pre["source_revision"]
        and training_plan.get("control_request") == request
        and training_plan.get("force_response_floor") == floor
        and training_plan.get("context_hash") == pre["context_hash"]
        and training_plan.get("training_model_identities")
        == pre["training_model_identities"]
        and len(pre["training_model_identities"]) == len(ids)
        and training_plan.get("fit_method") == FIT_METHOD
        and training_plan.get("ridge") == learning["ridge"]
        and training_plan.get("ood_margin") == learning["ood_margin"]
        and training_plan.get("independent_project_geometry_history_split") is False,
        "training plan differs from frozen inputs",
    )
    label_plan = {
        "source_revision": pre["source_revision"],
        "baseline_checksum": sha(canonical(baseline)),
        "control_request": request,
        "force_response_floor": floor,
        "history_limits": experiment["history_limits"],
        "material_limits": experiment["material_history_limits"],
        "terminal_limits": None,
        "prices": None,
        "price_table_hash": None,
        "line_search_assembly_reuse": False,
    }
    identity = load(packet, "training/labels/request.json")
    labels = load(packet, "training/labels/comparison.json")
    require(
        labels.get("schema_version") == common.COMPARISON_SCHEMA
        and identity.get("schema_version") == common.COMPARISON_SCHEMA,
        "training label comparison schema mismatch",
    )
    check_self_hash(labels, "report_hash", "training label comparison")
    require(
        labels.get("request_hash") == sha(canonical(identity)),
        "training label request hash mismatch",
    )
    for key, value in label_plan.items():
        if key == "line_search_assembly_reuse":
            require(
                "line_search_assembly_reuse" not in identity,
                "unplanned training line-search reuse",
            )
            continue
        require(
            same(identity.get(key), value) and same(labels.get(key), value),
            f"training label {key} differs from frozen plan",
        )
    require(
        [common.normalized_candidate(row) for row in identity.get("candidates", [])]
        == [common.normalized_candidate(row) for row in candidates]
        and [common.normalized_candidate(row) for row in labels.get("candidates", [])]
        == [common.normalized_candidate(row) for row in candidates],
        "training label candidate roster changed",
    )
    rows = labels.get("rows")
    require(
        type(rows) is list and [row.get("candidate_id") for row in rows] == ids,
        "training label row order changed",
    )
    for row in rows:
        _check_row(
            packet,
            "training/labels",
            row,
            label_plan,
            models[row["candidate_id"]],
            None,
        )
    require(
        labels.get("status") == "complete"
        and labels.get("verified_count") == len(ids)
        and labels.get("candidate_denominator") == len(ids)
        and labels.get("selected_candidate_id") is None
        and labels.get("selection_status") == "prices_unavailable",
        "training labels not complete or price-free",
    )
    require(
        identity.get("source_revision_is_attestation") is False
        and labels.get("source_revision_is_attestation") is False,
        "training labels overstate source revision authority",
    )
    samples = load(packet, "training/training-samples.json")
    require(
        type(samples) is list and len(samples) == len(ids),
        "training samples incomplete",
    )
    for row, sample, candidate_id, identity_hash in zip(
        rows, samples, ids, pre["training_model_identities"], strict=True
    ):
        require(
            type(sample) is dict
            and set(sample)
            == {
                "model_identity",
                "features",
                "targets",
                "result_sha256",
                "verification_sha256",
                "sample_hash",
            }
            and sample["model_identity"] == identity_hash,
            f"training {candidate_id} sample identity mismatch",
        )
        check_self_hash(sample, "sample_hash", f"training {candidate_id} sample")
        vector_close(
            sample["features"],
            _features(models[candidate_id]),
            f"training {candidate_id} features",
        )
        require(
            sample["targets"] == [row["performance"][key] for key in TARGETS]
            and sample["result_sha256"] == row["artifacts"]["result"]["sha256"]
            and sample["verification_sha256"]
            == row["artifacts"]["verification"]["sha256"],
            f"training {candidate_id} labels differ from original result",
        )
    policy = load(packet, "training/policy.json")
    check_policy_fit(policy, samples, learning)
    require(
        policy.get("context_hash") == pre["context_hash"]
        and policy.get("force_target")
        == {
            "target_index": floor["target_index"],
            "target_control_displacement_m": floor["target_control_displacement_m"],
        }
        and policy.get("training_model_identities") == pre["training_model_identities"]
        and policy.get("training_sample_hashes")
        == [sample["sample_hash"] for sample in samples]
        and policy.get("label_comparison_hash") == labels["report_hash"],
        "policy linkage to original training labels differs",
    )
    fit_started, fit_outcome = (
        load(packet, "training/fit-started.json"),
        load(packet, "training/fit-outcome.json"),
    )
    require(
        fit_started == {"status": "started", "unknown_fit_work_until_outcome": True}
        and fit_outcome.get("status") == "completed"
        and fit_outcome.get("unknown_fit_work_until_outcome") is False
        and fit_outcome.get("method") == FIT_METHOD
        and all(
            type(fit_outcome.get(key)) is int and fit_outcome[key] >= 0
            for key in ("wall_ns", "cpu_ns")
        ),
        "training fit work unknown",
    )
    report = load(packet, "training/training.json")
    require(
        report.get("schema_version") == TRAINING_SCHEMA,
        "training report schema mismatch",
    )
    check_self_hash(report, "report_hash", "training report")
    require(
        report.get("source_revision") == pre["source_revision"]
        and same(report.get("force_response_floor"), floor)
        and report.get("label_comparison_hash") == labels["report_hash"]
        and report.get("policy_hash") == policy["policy_hash"]
        and report.get("sample_count") == len(ids)
        and same(report.get("fit"), fit_outcome)
        and report.get("label_generation_wall_ns") == labels["total_wall_ns"]
        and report.get("label_invocations")
        == [inv for row in rows for inv in row["invocations"]]
        and report.get("independent_generalization") is False
        and report.get("net_savings_proved") is False
        and all(
            type(report.get(key)) is int and report[key] >= 0
            for key in ("wall_ns", "cpu_ns")
        ),
        "training report or historical cost differs from originals",
    )
    require(
        report["wall_ns"] >= report["label_generation_wall_ns"]
        and report["wall_ns"] >= fit_outcome["wall_ns"]
        and report["cpu_ns"] >= fit_outcome["cpu_ns"],
        "training enclosing timing does not contain recorded nested work",
    )
    common.work_from_rows(rows)
    return policy, report, models, rows


def _check_predictions(plan, policy, models, estimates):
    predictions = plan.get("predictions")
    ids = [
        row["candidate_id"] for row in plan["pool"] if row["candidate_id"] != "baseline"
    ]
    require(
        type(predictions) is list
        and [row.get("candidate_id") for row in predictions] == ids,
        "V2 prediction roster differs from frozen evaluation pool",
    )
    for row in predictions:
        candidate_id = row["candidate_id"]
        values = _features(models[candidate_id])
        bounds = policy["ood_margin"]
        outside = any(
            value < low - bounds * (high - low) or value > high + bounds * (high - low)
            for value, low, high in zip(
                values, policy["minimum"], policy["maximum"], strict=True
            )
        )
        expected = {}
        if not outside:
            for k, name in enumerate(TARGETS):
                scaled = (
                    math.fsum(
                        (values[j] - policy["mean"][j])
                        / policy["scale"][j]
                        * policy["weights"][j][k]
                        for j in range(len(FEATURE_NAMES))
                    )
                    + policy["weights"][-1][k]
                )
                expected[name] = scaled * policy["target_scale"][k]
        valid = (
            not outside
            and all(finite(value) for value in expected.values())
            and all(expected[key] >= 0 for key in TARGETS[:-1])
            and expected[TARGETS[0]] <= expected[TARGETS[2]]
            and expected[TARGETS[1]] <= expected[TARGETS[3]]
            and expected[TARGETS[5]] <= 1
            and expected[TARGETS[6]] <= 1
        )
        prediction = row.get("prediction")
        require(
            type(prediction) is dict
            and prediction.get("policy_hash") == policy["policy_hash"]
            and prediction.get("physical_result_authority") is False
            and prediction.get("uncertainty_calibrated") is False
            and prediction.get("abstained") is (not valid),
            f"{candidate_id}: policy prediction authority or abstention differs",
        )
        require(
            row.get("estimate") == estimates[candidate_id]["total"],
            f"{candidate_id}: ranking estimate differs from declared price",
        )
        if not valid:
            reason = (
                "outside_training_feature_bounds"
                if outside
                else "prediction_nonfinite_or_inconsistent"
            )
            require(
                prediction.get("performance") is None
                and prediction.get("reason") == reason
                and row.get("predicted_screens") is None
                and row.get("predicted_force_floor_status") == "unavailable"
                and row.get("ranking_tier") == 1,
                f"{candidate_id}: abstention handling differs",
            )
            continue
        observed = prediction.get("performance")
        require(
            type(observed) is dict
            and set(observed) == set(TARGETS)
            and all(
                close(observed[key], expected[key], rel=2e-8, absolute=2e-8)
                for key in TARGETS
            )
            and prediction.get("reason") == "in_training_feature_bounds_uncalibrated"
            and row.get("predicted_force_floor_status") == "available",
            f"{candidate_id}: prediction differs from frozen fit and features",
        )
        expected_screens = common.screens_from_performance(
            observed, plan, observed["load_factor_at_target"]
        )
        require(
            same(row.get("predicted_screens"), expected_screens),
            f"{candidate_id}: predicted floor/upper screens differ",
        )
        tier = (
            0
            if all(screen["status"] == "pass" for screen in expected_screens.values())
            else 2
        )
        require(
            row.get("ranking_tier") == tier,
            f"{candidate_id}: ranking tier differs from signed factor screen",
        )
    price_order = sorted(
        ids, key=lambda candidate_id: (estimates[candidate_id]["total"], candidate_id)
    )
    learned_order = [
        row["candidate_id"]
        for row in sorted(
            predictions,
            key=lambda row: (row["ranking_tier"], row["estimate"], row["candidate_id"]),
        )
    ]
    budget = plan["full_analysis_budget_including_baseline_per_arm"] - 1
    require(
        plan.get("plans")
        == {
            "price_order": {"ordering": price_order, "shortlist": price_order[:budget]},
            "learned_order": {
                "ordering": learned_order,
                "shortlist": learned_order[:budget],
            },
        },
        "price/learned ordering or equal-budget shortlist differs",
    )
    return price_order, learned_order


def _check_search_plan(packet, pre, inputs, policy, training_report, training_models):
    plan = load(packet, "search/plan.json")
    require(
        plan.get("schema_version") == SEARCH_PLAN_SCHEMA,
        "V2 search plan schema mismatch",
    )
    check_self_hash(plan, "plan_hash", "V2 search plan")
    request, floor_input, experiment = (
        inputs["request"],
        inputs["floor_plan"],
        inputs["experiment"],
    )
    floor = {
        key: value for key, value in floor_input.items() if key != "schema_version"
    }
    require(
        floor_input.get("schema_version")
        == "experimental-rc-control-force-response-floor.v1"
        and set(floor)
        == {"target_index", "target_control_displacement_m", "minimum_load_factor"}
        and type(floor["target_index"]) is int
        and 0 <= floor["target_index"] < len(request["targets_m"])
        and floor["target_control_displacement_m"]
        == request["targets_m"][floor["target_index"]]
        and finite(floor["minimum_load_factor"])
        and floor["minimum_load_factor"] > 0
        and request.get("experimental_pin_roller_beam") is True
        and not request.get("constant_nodal_loads")
        and bool(inputs["model"].get("loads")),
        "frozen signed factor or pin/roller loading scope invalid",
    )
    require(
        experiment.get("schema_version") == "rc-fiber-design-experiment.v3",
        "evaluation experiment schema mismatch",
    )
    training_experiment = inputs["training_experiment"]
    for key in (
        "prices",
        "history_limits",
        "material_history_limits",
        "terminal_limits",
    ):
        require(
            same(training_experiment.get(key), experiment.get(key)),
            f"training/evaluation {key} declaration differs",
        )
    candidates = experiment["candidates"]
    ids = ["baseline", *(candidate["candidate_id"] for candidate in candidates)]
    require(
        2 <= len(ids) <= 17
        and len(set(ids)) == len(ids)
        and pre.get("evaluation_candidate_ids") == ids
        and 2 <= pre["full_analysis_budget"] < len(ids),
        "evaluation candidate roster or online budget invalid",
    )
    require(
        plan.get("source_revision") == pre["source_revision"]
        and plan.get("source_revision_is_attestation") is False
        and plan.get("control_request") == request
        and plan.get("force_response_floor") == floor
        and plan.get("history_limits") == experiment["history_limits"]
        and plan.get("material_limits") == experiment["material_history_limits"]
        and plan.get("terminal_limits") == experiment["terminal_limits"]
        and plan.get("prices") == experiment["prices"]
        and plan.get("full_analysis_budget_including_baseline_per_arm")
        == pre["full_analysis_budget"]
        and plan.get("line_search_assembly_reuse") is pre["reuse_line_search_assembly"]
        and plan.get("oracle_after_online_arms") is True
        and plan.get("learned_policy_used") is True
        and plan.get("original_training_and_pool_models_disjoint") is True
        and plan.get("independent_project_geometry_history_split") is False
        and plan.get("ranking_strategy") == RANKING
        and plan.get("policy_hash") == policy["policy_hash"]
        and plan.get("training_report_hash") == training_report["report_hash"],
        "V2 search plan differs from frozen protocol/training",
    )
    require(
        [common.normalized_candidate(row) for row in plan.get("candidates", [])]
        == [common.normalized_candidate(row) for row in candidates],
        "V2 search candidate declarations changed",
    )
    expected_binding = {
        key: pre[key]
        for key in (
            "protocol_commit",
            "protocol_path",
            "protocol_sha256",
            "input_sha256",
        )
    }
    require(
        same(plan.get("protocol_binding"), expected_binding),
        "V2 search plan protocol binding mismatch",
    )
    prices = _normalized_prices(experiment["prices"])
    require(
        same(plan.get("prices"), prices),
        "evaluation prices differ from parser-normalized declaration",
    )
    price_hash = sha(
        canonical({"schema_version": "declared-rc-material-prices.v1", **prices})
    )
    require(
        plan.get("price_table_hash") == price_hash,
        "evaluation price table hash mismatch",
    )
    for field, filename, expected in (
        ("policy_artifact", "policy.json", policy),
        ("historical_training_artifact", "historical-training.json", training_report),
    ):
        raw = file_bytes(packet, f"search/{filename}")
        require(
            plan.get(field)
            == {"path": filename, "byte_length": len(raw), "sha256": sha(raw)}
            and same(decode(raw, filename), expected),
            f"V2 search {field} differs from completed training",
        )
    baseline = _change_width(inputs["model"], pre["baselines"]["evaluation"])
    require(
        plan.get("baseline_checksum") == sha(canonical(baseline)),
        "evaluation baseline checksum mismatch",
    )
    models = {"baseline": baseline}
    for candidate in candidates:
        models[candidate["candidate_id"]] = _candidate_model(baseline, candidate)
    require(
        len({sha(canonical(value)) for value in models.values()}) == len(ids)
        and not (
            {sha(canonical(value)) for value in models.values()}
            & {sha(canonical(value)) for value in training_models.values()}
        ),
        "training/evaluation physical model bytes overlap",
    )
    pool = plan.get("pool")
    require(
        type(pool) is list and [row["candidate_id"] for row in pool] == ids,
        "V2 pool roster differs from evaluation input",
    )
    require(
        len(pre["evaluation_model_identities"]) == len(ids)
        and not (
            set(pre["evaluation_model_identities"])
            & set(pre["training_model_identities"])
        ),
        "claimed training/evaluation identities overlap",
    )
    estimates = {}
    for row, identity_hash in zip(
        pool, pre["evaluation_model_identities"], strict=True
    ):
        candidate_id = row["candidate_id"]
        raw = file_bytes(packet, f"search/pool/{candidate_id}.json")
        require(
            row.get("model_artifact")
            == {
                "path": f"pool/{candidate_id}.json",
                "byte_length": len(raw),
                "sha256": sha(raw),
            }
            and same(decode(raw, f"pool/{candidate_id}"), models[candidate_id])
            and row.get("model_checksum") == sha(canonical(models[candidate_id]))
            and row.get("model_identity") == identity_hash,
            f"{candidate_id}: evaluation pool model differs from frozen roster",
        )
        quantities = common.quantities_from_model(models[candidate_id])
        estimate = common.estimate_from_quantities(quantities, prices, price_hash)
        require(
            same(row.get("quantities"), quantities)
            and same(row.get("material_estimate"), estimate),
            f"{candidate_id}: pool quantities or synthetic price differ",
        )
        estimates[candidate_id] = estimate
    price_order, learned_order = _check_predictions(plan, policy, models, estimates)
    return plan, models, estimates, price_order, learned_order


def _expected_cost(plan, comparisons, eligible, estimates):
    ids = [row["candidate_id"] for row in plan["pool"]]
    oracle = comparisons["exhaustive_oracle"]
    feasible = [
        candidate_id
        for candidate_id in ids
        if eligible["exhaustive_oracle"][candidate_id]
    ]
    status = "complete" if feasible else "no_feasible_candidate"
    minimum = min(
        (estimates[candidate_id]["total"] for candidate_id in feasible), default=None
    )
    winners = (
        sorted(
            candidate_id
            for candidate_id in feasible
            if estimates[candidate_id]["total"] == minimum
        )
        if minimum is not None
        else None
    )
    predicted_failures = {
        row["candidate_id"]
        for row in plan["predictions"]
        if not row["prediction"]["abstained"]
        and any(
            screen["status"] == "fail" for screen in row["predicted_screens"].values()
        )
    }
    arms = {}
    for name in ("price_order", "learned_order"):
        selected = comparisons[name]["selected_candidate_id"]
        arm_status = status
        if status == "complete":
            arm_status = (
                "no_verified_selection"
                if selected is None
                else "selection_not_confirmed_by_oracle"
                if not eligible["exhaustive_oracle"][selected]
                else "compared"
            )
        selected_estimate = None if selected is None else estimates[selected]["total"]
        gap = selected_estimate - minimum if arm_status == "compared" else None
        requested = {"baseline", *plan["plans"][name]["shortlist"]}
        missed = (
            [
                candidate_id
                for candidate_id in ids
                if candidate_id not in requested
                and eligible["exhaustive_oracle"][candidate_id]
                and estimates[candidate_id]["total"] < selected_estimate
            ]
            if arm_status == "compared"
            else None
        )
        false_negative = (
            [
                candidate_id
                for candidate_id in missed
                if candidate_id in predicted_failures
            ]
            if missed is not None and name == "learned_order"
            else None
        )
        arms[name] = {
            "status": arm_status,
            "selected_candidate_id": selected,
            "selected_estimate": selected_estimate,
            "selected_minus_pool_minimum_estimate": gap,
            "matches_pool_minimum": None if gap is None else gap == 0,
            "missed_cheaper_feasible_count": None if missed is None else len(missed),
            "missed_cheaper_feasible_candidate_ids": missed,
            "missed_cheaper_false_negative_count": None
            if false_negative is None
            else len(false_negative),
            "missed_cheaper_false_negative_candidate_ids": false_negative,
        }
    first = estimates[ids[0]]
    return {
        "schema_version": COST_SCHEMA,
        "status": status,
        "candidate_denominator": len(ids),
        "baseline_included": True,
        "price_table_hash": plan["price_table_hash"],
        "currency": first["currency"],
        "quantity_scope": first["scope"],
        "oracle_comparison_hash": oracle["report_hash"],
        "oracle_unverifiable_candidate_ids": [],
        "pool_minimum_feasible_estimate": minimum,
        "pool_minimum_feasible_candidate_ids": winners,
        "arms": arms,
        "global_design_optimality_proved": False,
        "confirmed_currency_savings": False,
        "independent_physical_validation": False,
        "force_response_floor": plan["force_response_floor"],
    }


def _expected_coverage(plan, oracle, eligible):
    ids = [
        row["candidate_id"] for row in plan["pool"] if row["candidate_id"] != "baseline"
    ]
    predictions = {row["candidate_id"]: row for row in plan["predictions"]}
    details = []
    for candidate_id in ids:
        prediction = predictions[candidate_id]
        screens = prediction["predicted_screens"]
        predicted_pass = (
            None
            if prediction["prediction"]["abstained"] or screens is None
            else all(screen["status"] == "pass" for screen in screens.values())
        )
        details.append(
            {
                "candidate_id": candidate_id,
                "predicted_all_requested_limits_pass": predicted_pass,
                "oracle_all_requested_limits_pass": eligible[candidate_id],
                "shortlisted_by": [
                    name
                    for name, arm in plan["plans"].items()
                    if candidate_id in arm["shortlist"]
                ],
            }
        )
    audits = {}
    for name in ("price_order", "learned_order"):
        missed = [
            row["candidate_id"]
            for row in details
            if row["oracle_all_requested_limits_pass"] is True
            and name not in row["shortlisted_by"]
        ]
        false_safe = (
            [
                row["candidate_id"]
                for row in details
                if row["predicted_all_requested_limits_pass"] is True
                and row["oracle_all_requested_limits_pass"] is False
            ]
            if name == "learned_order"
            else None
        )
        false_negative = (
            [
                row["candidate_id"]
                for row in details
                if row["predicted_all_requested_limits_pass"] is False
                and row["oracle_all_requested_limits_pass"] is True
            ]
            if name == "learned_order"
            else None
        )
        groups = {
            "missed_feasible": missed,
            "oracle_unverifiable": [],
            "false_safe": false_safe,
            "predicted_safe_unverifiable": [] if name == "learned_order" else None,
            "false_negative": false_negative,
        }
        audits[name] = {
            key + suffix: (
                None if value is None else len(value) if suffix == "_count" else value
            )
            for key, value in groups.items()
            for suffix in ("_count", "_candidate_ids")
        }
    return {
        "schema_version": "rc-control-force-floor-candidate-coverage-audit.v2",
        "status": "compared_with_separate_full_reference_oracle",
        "alternative_denominator": len(ids),
        "baseline_excluded": True,
        "oracle_comparison_hash": oracle["report_hash"],
        "definitions": {
            "missed_feasible": "oracle_verified_all_requested_limits_pass_but_not_shortlisted",
            "false_safe": "predicted_all_requested_limits_pass_but_oracle_verified_limit_failure",
            "predicted_safe_unverifiable": "predicted_all_requested_limits_pass_but_oracle_unverifiable",
            "false_negative": "predicted_limit_failure_but_oracle_verified_all_requested_limits_pass",
            "deterministic_prediction_counts": "not_applicable_strategy_makes_no_predictions",
            "unavailable_counts": "null_does_not_mean_zero",
        },
        "candidates": details,
        "arms": audits,
        "independent_physical_validation": False,
        "force_response_floor": plan["force_response_floor"],
    }


def _check_packet_paths(inventory, pre, plan):
    expected = {
        "plan.json",
        "runner.json",
        "training-started.json",
        "training-outcome.json",
        "search-started.json",
        "search-outcome.json",
        "training/plan.json",
        "training/labels/request.json",
        "training/labels/comparison.json",
        "training/training-samples.json",
        "training/fit-started.json",
        "training/fit-outcome.json",
        "training/policy.json",
        "training/training.json",
        "search/plan.json",
        "search/result.json",
        "search/policy.json",
        "search/historical-training.json",
        *(f"inputs/{role}.json" for role in ROLES),
        *(f"search/pool/{row['candidate_id']}.json" for row in plan["pool"]),
    }
    for candidate_id in pre["training_candidate_ids"]:
        expected.update(
            f"training/labels/{candidate_id}/{filename}" for filename in ROW_FILES
        )
    for name, ids in (
        ("price_order", ["baseline", *plan["plans"]["price_order"]["shortlist"]]),
        ("learned_order", ["baseline", *plan["plans"]["learned_order"]["shortlist"]]),
        ("exhaustive_oracle", ["baseline", *plan["plans"]["price_order"]["ordering"]]),
    ):
        expected.update(
            {
                f"search/{name}-started.json",
                f"search/{name}-outcome.json",
                f"search/{name}/request.json",
                f"search/{name}/comparison.json",
            }
        )
        expected.update(
            f"search/{name}/{candidate_id}/{filename}"
            for candidate_id in ids
            for filename in ROW_FILES
        )
    actual = {row[0] for row in inventory["files"]}
    require(
        actual == expected and len(inventory["files"]) == len(expected),
        "V2 packet contains undeclared or missing execution files",
    )


def _phase_marker(
    packet, name, pre, *, training_report=None, search_plan=None, result=None
):
    started, outcome = (
        load(packet, f"{name}-started.json"),
        load(packet, f"{name}-outcome.json"),
    )
    require(
        started.get("status") == "started"
        and started.get("outer_plan_hash") == pre["plan_hash"]
        and started.get("unknown_work_until_outcome") is True
        and outcome.get("status") == "completed"
        and outcome.get("unknown_work_until_outcome") is False
        and all(
            type(outcome.get(key)) is int and outcome[key] >= 0
            for key in ("wall_ns", "process_cpu_ns")
        ),
        f"{name}: enclosing phase outcome unknown",
    )
    if name == "training":
        require(
            outcome.get("policy_hash") == training_report["policy_hash"]
            and outcome.get("training_report_hash") == training_report["report_hash"]
            and outcome.get("sample_count") == training_report["sample_count"]
            and outcome.get("timing_scope")
            == "start_marker_training_labels_fit_source_and_artifact_checks_excluding_outcome_write",
            "training phase marker differs from completed originals",
        )
    else:
        require(
            started.get("training_report_hash") == training_report["report_hash"]
            and outcome.get("search_plan_hash") == search_plan["plan_hash"]
            and outcome.get("search_report_hash") == result["report_hash"]
            and outcome.get("timing_scope")
            == "start_marker_search_arms_oracle_source_and_artifact_checks_excluding_outcome_write",
            "search phase marker differs from completed originals",
        )


def _check_search_result(
    packet,
    pre,
    runner,
    plan,
    models,
    estimates,
    training_report,
    training_rows,
    price_order,
):
    comparisons, eligibility, outcomes = {}, {}, {}
    for name, candidate_ids in (
        ("price_order", ["baseline", *plan["plans"]["price_order"]["shortlist"]]),
        ("learned_order", ["baseline", *plan["plans"]["learned_order"]["shortlist"]]),
        ("exhaustive_oracle", ["baseline", *price_order]),
    ):
        started = load(packet, f"search/{name}-started.json")
        outcome = load(packet, f"search/{name}-outcome.json")
        require(
            started.get("status") == "started"
            and started.get("plan_hash") == plan["plan_hash"]
            and started.get("candidate_ids") == candidate_ids
            and started.get("unknown_work_until_outcome") is True,
            f"{name}: frozen start receipt mismatch",
        )
        report, eligible = common.check_comparison(
            packet, name, plan, models, estimates, candidate_ids
        )
        work = common.work_from_rows(report["rows"])
        selected = report["selected_candidate_id"]
        require(
            outcome.get("status") == "completed"
            and outcome.get("comparison_hash") == report["report_hash"]
            and outcome.get("comparison_path") == f"{name}/comparison.json"
            and outcome.get("request_count") == len(candidate_ids)
            and outcome.get("selected_candidate_id") == selected
            and outcome.get("selected_estimate")
            == (None if selected is None else estimates[selected]["total"])
            and outcome.get("selected_full_reference_verified")
            is (selected is not None)
            and same(outcome.get("execution_work"), work)
            and outcome.get("unknown_work_until_outcome") is False
            and all(
                type(outcome.get(key)) is int and outcome[key] >= 0
                for key in ("wall_ns", "cpu_ns")
            ),
            f"{name}: comparison outcome or work unknown",
        )
        comparisons[name], eligibility[name], outcomes[name] = report, eligible, outcome
    expected_cost = _expected_cost(plan, comparisons, eligibility, estimates)
    expected_coverage = _expected_coverage(
        plan, comparisons["exhaustive_oracle"], eligibility["exhaustive_oracle"]
    )
    result = load(packet, "search/result.json")
    require(
        result.get("schema_version") == SEARCH_SCHEMA,
        "V2 search report schema mismatch",
    )
    check_self_hash(result, "report_hash", "V2 search report")
    require(
        result.get("source_revision") == pre["source_revision"]
        and result.get("plan_hash") == plan["plan_hash"]
        and result.get("force_response_floor") == plan["force_response_floor"]
        and result.get("candidate_denominator") == len(plan["pool"])
        and result.get("arms")
        == {name: outcomes[name] for name in ("price_order", "learned_order")}
        and result.get("oracle") == outcomes["exhaustive_oracle"]
        and same(result.get("candidate_cost_optimality_audit"), expected_cost)
        and same(result.get("candidate_coverage_audit"), expected_coverage),
        "V2 search report, coverage, or cost differs from original rows",
    )
    historical_work = common.work_from_rows(training_rows)
    require(
        same(result.get("historical_training_cost"), training_report)
        and same(result.get("historical_training_execution_work"), historical_work)
        and result.get("historical_training_cost_counted_once_outside_online_arms")
        is True
        and all(
            type(result.get(key)) is int and result[key] >= 0
            for key in (
                "ranking_wall_ns",
                "online_and_oracle_wall_ns",
                "online_and_oracle_cpu_ns",
            )
        ),
        "historical training work/cost count differs or is unknown",
    )
    claims = result.get("claims") or {}
    require(
        claims.get("known_pool_cost_optimality_only") is True
        and claims.get("learned_policy_used") is True
        and claims.get("net_ai_savings_proved") is False
        and claims.get("independent_physical_validation") is False
        and claims.get("independent_generalization") is False
        and claims.get("confirmed_currency_savings") is False,
        "V2 result overclaims learned or physical evidence",
    )
    require(
        runner.get("search_plan_hash") == plan["plan_hash"]
        and runner.get("search_plan_sha256")
        == sha(file_bytes(packet, "search/plan.json"))
        and runner.get("search_report_hash") == result["report_hash"]
        and runner.get("search_report_sha256")
        == sha(file_bytes(packet, "search/result.json")),
        "runner search bindings mismatch",
    )
    return result, comparisons, expected_cost


def audit_contents(source, packet):
    inventory = _inventory(packet)
    pre, runner, inputs = _provenance(source, packet)
    policy, training_report, training_models, training_rows = _check_training(
        packet, pre, inputs
    )
    require(
        runner.get("training_plan_sha256")
        == sha(file_bytes(packet, "training/plan.json"))
        and runner.get("training_policy_hash") == policy["policy_hash"]
        and runner.get("training_policy_sha256")
        == sha(file_bytes(packet, "training/policy.json"))
        and runner.get("training_report_hash") == training_report["report_hash"]
        and runner.get("training_report_sha256")
        == sha(file_bytes(packet, "training/training.json")),
        "runner training fit/report bindings mismatch",
    )
    _phase_marker(packet, "training", pre, training_report=training_report)
    plan, models, estimates, price_order, _ = _check_search_plan(
        packet, pre, inputs, policy, training_report, training_models
    )
    _check_packet_paths(inventory, pre, plan)
    result, comparisons, cost = _check_search_result(
        packet,
        pre,
        runner,
        plan,
        models,
        estimates,
        training_report,
        training_rows,
        price_order,
    )
    _phase_marker(
        packet,
        "search",
        pre,
        training_report=training_report,
        search_plan=plan,
        result=result,
    )
    require(
        runner.get("unknown_execution_work") is False
        and all(
            type(runner.get(key)) is int and runner[key] >= 0
            for key in ("runner_wall_ns", "runner_process_cpu_ns")
        )
        and runner.get("runner_timing_scope")
        == "preflight_decode_plan_training_search_phase_markers_and_IO_excluding_final_receipt_inventory_write",
        "runner enclosing work/cost unknown",
    )
    return {
        "source_revision": pre["source_revision"],
        "protocol_commit": pre["protocol_commit"],
        "protocol_sha256": pre["protocol_sha256"],
        "training_policy_hash": policy["policy_hash"],
        "training_report_hash": training_report["report_hash"],
        "search_plan_hash": plan["plan_hash"],
        "search_report_hash": result["report_hash"],
        "oracle_comparison_hash": comparisons["exhaustive_oracle"]["report_hash"],
        "candidate_denominator": len(plan["pool"]),
        "price_selected_candidate_id": comparisons["price_order"][
            "selected_candidate_id"
        ],
        "learned_selected_candidate_id": comparisons["learned_order"][
            "selected_candidate_id"
        ],
        "oracle_selected_candidate_id": comparisons["exhaustive_oracle"][
            "selected_candidate_id"
        ],
        "pool_minimum_feasible_estimate": cost["pool_minimum_feasible_estimate"],
        "cost_audit_status": cost["status"],
    }


def audit_packet(source, packet):
    """Return bounded packet-integrity evidence without modifying either input."""
    source, packet = Path(source).resolve(), Path(packet).resolve()
    report = {
        "schema_version": AUDIT_SCHEMA,
        "status": "incomplete_or_unverifiable",
        "packet_path": str(packet),
        "violations": [],
        "unknown_execution_work": True,
        "independent_physical_validation": False,
        "independent_project_geometry_history_split": False,
        "confirmed_currency_savings": False,
        "net_ai_savings_proved": False,
        "fit_recomputed_independently_of_numpy": False,
        "physical_model_identity_recomputed": False,
        "historical_checkout_cleanliness_independently_reconstructible": False,
    }
    try:
        require(
            packet.is_dir() and source.is_dir(), "V2 source or packet directory missing"
        )
        details = audit_contents(source, packet)
    except (
        AuditError,
        KeyError,
        TypeError,
        IndexError,
        ValueError,
        OSError,
        AttributeError,
        OverflowError,
        ZeroDivisionError,
    ) as error:
        report["violations"].append(str(error))
        return report
    report.update(details)
    report["status"] = "verified_packet_integrity"
    report["unknown_execution_work"] = False
    report["fit_recomputed_independently_of_numpy"] = True
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = audit_packet(args.source, args.packet)
    data = canonical(result) + b"\n"
    if args.output is None:
        print(data.decode("utf-8"), end="")
    else:
        output, packet = args.output.resolve(), args.packet.resolve()
        if output == packet or packet in output.parents:
            parser.error("audit output must be outside packet")
        with output.open("xb") as stream:
            stream.write(data)
    return 0 if result["status"] == "verified_packet_integrity" else 1


if __name__ == "__main__":
    raise SystemExit(main())
