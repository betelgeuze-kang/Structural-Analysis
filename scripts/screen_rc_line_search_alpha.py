"""Source-bound, offline RC line-search decision screen; never calls a solver."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from pathlib import Path
from typing import Any


INVENTORY_SHA256 = "a2c9b9d141db3c4718d3d69e02590a82d91282ed1994bce2a11c8e39c20b8409"
SOURCE_REVISION = "80f9ff404dfa15f7048c21d673f348155f90d965"
GROUPS = tuple(
    tuple(f"train-{letter}-amp{amplitude}" for amplitude in ("050", "100", "150"))
    for letter in "abcde"
)
ALPHAS = tuple(2.0**-index for index in range(13))
FEATURE_NAMES = (
    "newton_iteration_index",
    "log10_relative_residual_before_trial",
    "log10_newton_increment_inf",
    "requested_target_increment_m",
    "previous_selected_alpha_index",
)
RIDGES = (10000.0, 1000000.0)
REPETITIONS = (0, 1, 2)
NEIGHBORS = 3


class TraceError(ValueError):
    """The original packet cannot support the declared screen."""

    def __init__(self, message: str, *, code: str = "trace_validation_failed") -> None:
        super().__init__(message)
        self.code = code


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_json(data: bytes) -> Any:
    def reject_constant(value: str) -> None:
        raise TraceError(f"nonfinite JSON constant: {value}", code="invalid_json")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TraceError(f"duplicate JSON key: {key}", code="invalid_json")
            result[key] = value
        return result

    try:
        return json.loads(
            data, parse_constant=reject_constant, object_pairs_hook=object_pairs
        )
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as exc:
        raise TraceError("invalid original JSON", code="invalid_json") from exc


def _self_hash(value: dict[str, Any], key: str) -> None:
    expected = "sha256:" + _hash(
        _json_bytes({k: v for k, v in value.items() if k != key})
    )
    if value.get(key) != expected:
        raise TraceError(f"{key} does not bind original content", code="content_binding_failed")


def _read_unlinked_regular_file(root: Path, relative: Path, description: str) -> bytes:
    """Read through no-follow directory handles, including the packet root."""
    if ".." in root.parts or relative.is_absolute() or ".." in relative.parts:
        raise TraceError(
            f"missing or linked {description}: {relative}", code="unsafe_or_missing_input"
        )
    components = (*root.parts[1:], *relative.parts)
    directory_fd = None
    try:
        directory_fd = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY)
        for part in components[:-1]:
            next_fd = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=directory_fd,
            )
            os.close(directory_fd)
            directory_fd = next_fd
        file_fd = os.open(
            components[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=directory_fd,
        )
        with os.fdopen(file_fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise TraceError(
                    f"missing or linked {description}: {relative}",
                    code="unsafe_or_missing_input",
                )
            return stream.read()
    except OSError as exc:
        raise TraceError(
            f"missing or linked {description}: {relative}", code="unsafe_or_missing_input"
        ) from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


class OriginalPacket:
    def __init__(self, root: Path) -> None:
        self.root = root.absolute()
        raw = _read_unlinked_regular_file(
            self.root, Path("inventory.json"), "inventory file"
        )
        if _hash(raw) != INVENTORY_SHA256:
            raise TraceError(
                "pooled packet inventory identity differs", code="inventory_identity_failed"
            )
        inventory = _strict_json(raw)
        files = inventory.get("files")
        if type(files) is not list:
            raise TraceError("inventory file list missing")
        self.files: dict[str, dict[str, Any]] = {}
        for row in files:
            if type(row) is not dict or type(row.get("path")) is not str:
                raise TraceError("invalid inventory entry")
            if row["path"] in self.files:
                raise TraceError("duplicate inventory path")
            self.files[row["path"]] = row
        self.consumed: set[str] = set()

    def read(self, relative: str) -> tuple[Any, str]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or relative not in self.files:
            raise TraceError(f"undeclared packet path: {relative}", code="undeclared_input")
        raw = _read_unlinked_regular_file(self.root, path, "original file")
        expected = self.files[relative]
        digest = _hash(raw)
        if len(raw) != expected.get("byte_length") or digest != expected.get("sha256"):
            raise TraceError(
                f"original bytes differ from inventory: {relative}",
                code="content_binding_failed",
            )
        self.consumed.add(relative)
        return _strict_json(raw), digest


def _finite_number(value: Any, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise TraceError(f"finite numeric {name} required")
    return float(value)


def _line_rows(
    step: dict[str, Any],
    context: dict[str, Any],
    *,
    case_id: str,
    target_index: int,
    step_path: str,
    step_sha256: str,
    context_path: str,
    context_sha256: str,
) -> list[dict[str, Any]]:
    """Use only values present before each trial; trial results are labels."""
    history = step["trial_solution"]["line_search_history"]
    convergence = step["trial_solution"]["convergence_history"]
    if type(history) is not list or type(convergence) is not list:
        raise TraceError("trial-level line-search and convergence history required")
    valid_convergence = [
        row
        for row in convergence
        if type(row) is dict and type(row.get("iteration")) is int
    ]
    by_iteration = {row["iteration"]: row for row in valid_convergence}
    if len(by_iteration) != len(valid_convergence):
        raise TraceError("duplicate convergence iteration")
    targets = context.get("accepted_targets_m")
    if type(targets) is not list or not targets:
        raise TraceError("causal accepted target prefix required")
    target = _finite_number(context.get("target_m"), "target")
    increment = target - _finite_number(targets[-1], "accepted target")
    if not math.isfinite(increment):
        raise TraceError("finite target increment required")
    rows: list[dict[str, Any]] = []
    previous_alpha_index = -1
    previous_iteration = -1
    for line in history:
        if type(line) is not dict:
            raise TraceError("line-search record required")
        iteration = line.get("iteration")
        if type(iteration) is not int or iteration < 0 or iteration not in by_iteration:
            raise TraceError("line-search iteration lacks causal convergence row")
        if iteration <= previous_iteration:
            raise TraceError("line-search iterations must be strictly increasing")
        previous_iteration = iteration
        before = by_iteration[iteration]
        if (
            line.get("starting_free_displacements_m")
            != before.get("free_displacements_m")
            or line.get("newton_increment_m") != before.get("newton_increment_m")
            or line.get("attempt_count") != before.get("line_search_attempt_count")
            or line.get("selected_alpha") != before.get("line_search_alpha")
        ):
            raise TraceError("pretrial state and convergence record differ")
        residual = _finite_number(before.get("relative_residual"), "pretrial residual")
        raw_before = before.get("residual_kn")
        vector = line.get("newton_increment_m")
        if (
            residual <= 0
            or type(raw_before) is not list
            or not raw_before
            or type(vector) is not list
            or not vector
        ):
            raise TraceError("positive pretrial residual and increment required")
        before_norm = max(
            abs(_finite_number(value, "pretrial raw residual")) for value in raw_before
        )
        if before_norm <= 0:
            raise TraceError("positive pretrial raw residual required")
        direction = max(abs(_finite_number(v, "Newton increment")) for v in vector)
        if direction <= 0:
            raise TraceError("positive Newton increment required")
        attempts = line.get("attempts")
        if type(attempts) is not list or not attempts or len(attempts) > len(ALPHAS):
            raise TraceError("complete bounded alpha-trial record required")
        if line.get("attempt_count") != len(attempts):
            raise TraceError("line-search attempt count differs")
        accepted_index: int | None = None
        for index, attempt in enumerate(attempts):
            if (
                type(attempt) is not dict
                or attempt.get("alpha") != ALPHAS[index]
                or type(attempt.get("accepted")) is not bool
            ):
                raise TraceError("original alpha prefix or acceptance flag differs")
            trial_relative = _finite_number(
                attempt.get("trial_relative_residual"), "trial residual"
            )
            raw_trial = attempt.get("trial_residual_kn")
            if (
                trial_relative < 0
                or type(raw_trial) is not list
                or len(raw_trial) != len(raw_before)
            ):
                raise TraceError("complete finite trial residual vector required")
            trial_norm = max(
                abs(_finite_number(value, "trial raw residual")) for value in raw_trial
            )
            if attempt["accepted"] != (trial_norm < before_norm):
                raise TraceError(
                    "trial acceptance differs from strict raw residual decrease"
                )
            if attempt["accepted"]:
                if accepted_index is not None or index != len(attempts) - 1:
                    raise TraceError("accepted trial must terminate original search")
                accepted_index = index
        expected_alpha = 0.0 if accepted_index is None else ALPHAS[accepted_index]
        if line.get("selected_alpha") != expected_alpha:
            raise TraceError("selected alpha differs from original trial history")
        row = {
            "case_id": case_id,
            "target_index": target_index,
            "newton_iteration_index": iteration,
            "features": [
                float(iteration),
                math.log10(residual),
                math.log10(direction),
                increment,
                float(previous_alpha_index),
            ],
            "first_accepted_index": accepted_index,
            "trial_count": len(attempts),
            "observed_failed_trial_count": (
                accepted_index if accepted_index is not None else len(attempts)
            ),
            "source_step": step_path,
            "source_step_sha256": step_sha256,
            "source_context": context_path,
            "source_context_sha256": context_sha256,
        }
        rows.append(row)
        previous_alpha_index = -1 if accepted_index is None else accepted_index
    return rows


def _predict_skip(
    training: list[dict[str, Any]], held: dict[str, Any]
) -> tuple[int, str]:
    """Fixed three-neighbor, train-only normalized conservative screen."""
    if len(training) < NEIGHBORS:
        return 0, "insufficient_training_rows"
    width = len(FEATURE_NAMES)
    columns = list(zip(*(row["features"] for row in training), strict=True))
    if len(columns) != width:
        raise TraceError("feature layout differs")
    means = [sum(column) / len(column) for column in columns]
    scales = [
        math.sqrt(sum((x - mean) ** 2 for x in column) / len(column)) or 1.0
        for column, mean in zip(columns, means, strict=True)
    ]
    values = held["features"]
    if any(
        value < min(column) or value > max(column)
        for value, column in zip(values, columns, strict=True)
    ):
        return 0, "outside_training_range"
    distances = []
    for row in training:
        distance = sum(
            ((a - b) / scale) ** 2
            for a, b, scale in zip(values, row["features"], scales, strict=True)
        )
        distances.append(
            (
                distance,
                row["case_id"],
                row["target_index"],
                row["newton_iteration_index"],
                row["first_accepted_index"],
            )
        )
    neighbors = sorted(distances)[:NEIGHBORS]
    if all(row[-1] is not None and row[-1] >= 1 for row in neighbors):
        return 1, "three_positive_neighbors"
    return 0, "neighbor_abstention"


def _cross_validate(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    group_of = {case: index for index, group in enumerate(GROUPS) for case in group}
    folds = []
    for held_group, cases in enumerate(GROUPS):
        training = [
            row
            for row in rows
            if group_of[row["case_id"]] != held_group
            and row["first_accepted_index"] is not None
        ]
        held = [row for row in rows if group_of[row["case_id"]] == held_group]
        if not training or not held:
            raise TraceError("empty whole-group split")
        counters = {
            "held_group": held_group,
            "held_cases": list(cases),
            "training_rows": len(training),
            "training_positive_rows": sum(
                row["first_accepted_index"] >= 1 for row in training
            ),
            "held_rows": len(held),
            "held_positive_rows": sum(
                row["first_accepted_index"] is not None
                and row["first_accepted_index"] >= 1
                for row in held
            ),
            "unverified_labels": 0,
            "predicted_skips": 0,
            "safe_predicted_skips": 0,
            "false_skips_unobserved_outcome": 0,
            "abstentions": 0,
        }
        for row in held:
            if row["first_accepted_index"] is None:
                counters["unverified_labels"] += 1
                continue
            prediction, _ = _predict_skip(training, row)
            if prediction == 0:
                counters["abstentions"] += 1
            else:
                counters["predicted_skips"] += 1
                if prediction <= row["first_accepted_index"]:
                    counters["safe_predicted_skips"] += 1
                else:
                    counters["false_skips_unobserved_outcome"] += 1
        folds.append(counters)
    decision = {
        "positive_label_groups": sum(row["held_positive_rows"] > 0 for row in folds),
        "safe_prediction_groups": sum(row["safe_predicted_skips"] > 0 for row in folds),
        "false_skips": sum(row["false_skips_unobserved_outcome"] for row in folds),
    }
    decision["supports_online_experiment_design"] = (
        decision["positive_label_groups"] >= 3
        and decision["safe_prediction_groups"] >= 3
        and decision["false_skips"] == 0
    )
    return folds, decision


def screen_packet(root: Path) -> dict[str, Any]:
    packet = OriginalPacket(root)
    plan, _ = packet.read("study/plan.json")
    if (
        plan.get("source_revision") != SOURCE_REVISION
        or plan.get("groups") != [list(group) for group in GROUPS]
        or plan.get("ridge_grid") != list(RIDGES)
        or plan.get("repetitions") != 3
        or plan.get("reserved_evaluation_executed") is not False
    ):
        raise TraceError("pooled development plan differs from frozen eligibility")
    cases = {case for group in GROUPS for case in group}
    roster: dict[tuple[str, float, int], dict[str, Any]] = {}
    fold_records = []
    canonical_rows: list[dict[str, Any]] = []
    for index in range(90):
        prefix = f"study/selection/fold-{index:04d}"
        outcome, _ = packet.read(prefix + "-outcome.json")
        case = outcome.get("withheld_training_case")
        ridge = outcome.get("ridge")
        repeat = outcome.get("repetition_index")
        key = (case, ridge, repeat)
        if (
            case not in cases
            or ridge not in RIDGES
            or repeat not in REPETITIONS
            or key in roster
            or outcome.get("status") != "completed"
        ):
            raise TraceError("fold roster or terminal status differs")
        request, _ = packet.read(prefix + "/request.json")
        comparison, _ = packet.read(prefix + "/comparison.json")
        path, _ = packet.read(prefix + "/secant/path.json")
        _self_hash(comparison, "report_hash")
        _self_hash(path, "path_hash")
        if (
            request.get("source_revision") != SOURCE_REVISION
            or comparison.get("source_revision") != SOURCE_REVISION
            or outcome.get("report_hash") != comparison["report_hash"]
            or comparison.get("arms", {}).get("secant", {}).get("path_hash")
            != path["path_hash"]
            or comparison.get("request") != request.get("request")
            or request["request"]["solver_config"]["newton"]["line_search_alphas"]
            != list(ALPHAS)
        ):
            raise TraceError(
                "source, request, comparison or secant path binding differs"
            )
        targets = request["request"]["targets_m"]
        entries = path.get("entries")
        if type(entries) is not list or len(entries) > len(targets):
            raise TraceError("bounded declared target roster required")
        issues = []
        failures = []

        def record_failure(code: str, message: str, **location: int) -> None:
            issues.append(message)
            failures.append({"code": code, **location})
        if len(entries) < len(targets):
            record_failure(
                "unattempted_targets",
                f"{len(targets) - len(entries)} unattempted targets",
                count=len(targets) - len(entries),
            )
        signature = []
        for target_index, entry in enumerate(entries):
            target = targets[target_index]
            if (
                type(entry) is not dict
                or entry.get("target_index") != target_index
                or entry.get("target_m") != target
            ):
                raise TraceError("path target and request differ")
            stem = f"{prefix}/secant/{target_index:03d}"
            context, context_sha = packet.read(stem + "-context.json")
            if context.get("target_m") != target or context.get(
                "problem_contract_hash"
            ) != request.get("compiled_problem_contract_hash"):
                raise TraceError("pre-solve context differs from target/model")
            invocations = entry.get("invocations")
            if type(invocations) is not list:
                raise TraceError("attempt list required")
            if not invocations:
                record_failure(
                    "missing_invocation", f"target {target_index}: no returned invocation",
                    target_index=target_index,
                )
                signature.append((context_sha, ()))
                continue
            if len(invocations) != 1:
                record_failure(
                    "multiple_invocations", f"target {target_index}: {len(invocations)} attempts",
                    target_index=target_index, count=len(invocations),
                )
            trial_signature = []
            for ordinal, invocation in enumerate(invocations, start=1):
                if invocation.get("ordinal") != ordinal:
                    raise TraceError("attempt ordinal differs")
                outcome_path = f"{stem}-{ordinal}-outcome.json"
                stored, _ = packet.read(outcome_path)
                if stored != invocation:
                    raise TraceError("attempt record differs from path")
                if stored.get("unknown_work") is not False:
                    record_failure(
                        "unknown_work",
                        f"target {target_index} attempt {ordinal}: unknown work",
                        target_index=target_index, ordinal=ordinal,
                    )
                if stored.get("status") != "returned":
                    record_failure(
                        "nonreturned_invocation",
                        f"target {target_index} attempt {ordinal}: nonreturned",
                        target_index=target_index, ordinal=ordinal,
                    )
                    trial_signature.append(None)
                    continue
                step_path = f"{stem}-{ordinal}-step.json"
                step, step_sha = packet.read(step_path)
                trial_signature.append(step_sha)
                if (
                    step.get("parent_checkpoint", {}).get("state_hash")
                    != entry.get("parent_hash")
                    or step.get("metrics", {}).get("target_control_displacement_m")
                    != target
                ):
                    raise TraceError("step parent or target binding differs")
                if (
                    step.get("committed") is not True
                    or stored.get("committed") is not True
                ):
                    record_failure(
                        "noncommitted_invocation",
                        f"target {target_index} attempt {ordinal}: noncommitted",
                        target_index=target_index, ordinal=ordinal,
                    )
                if ridge == RIDGES[0] and repeat == 0 and ordinal == 1:
                    try:
                        canonical_rows.extend(
                            _line_rows(
                                step,
                                context,
                                case_id=case,
                                target_index=target_index,
                                step_path=step_path,
                                step_sha256=step_sha,
                                context_path=stem + "-context.json",
                                context_sha256=context_sha,
                            )
                        )
                    except (KeyError, TypeError, TraceError) as exc:
                        record_failure(
                            "unverified_trial_history",
                            f"target {target_index} attempt {ordinal}: "
                            f"unverified trial history ({type(exc).__name__})",
                            target_index=target_index, ordinal=ordinal,
                        )
            signature.append((context_sha, tuple(trial_signature)))
        if (
            path.get("status") != "complete"
            or path.get("failure") is not None
            or path.get("accepted_target_count") != len(targets)
            or comparison.get("all_execution_work_reported") is not True
            or comparison.get("reference_repeat_exact") is not True
            or comparison.get("comparisons", {})
            .get("secant", {})
            .get("full_history_pass")
            is not True
        ):
            record_failure(
                "incomplete_physical_work_comparison",
                "complete physical/work comparison unavailable",
            )
        fold = {
            "index": index,
            "case_id": case,
            "ridge": ridge,
            "repetition": repeat,
            "report_hash": comparison["report_hash"],
            "secant_path_hash": path["path_hash"],
            "step_signature": signature,
            "issues": issues,
            "failures": failures,
        }
        roster[key] = fold
        fold_records.append(fold)
    expected = {
        (case, ridge, repeat)
        for case in cases
        for ridge in RIDGES
        for repeat in REPETITIONS
    }
    if set(roster) != expected:
        raise TraceError("incomplete five-group fold roster")
    repeat_mismatches = []
    for case in sorted(cases):
        original = roster[(case, RIDGES[0], 0)]["step_signature"]
        for ridge in RIDGES:
            for repeat in REPETITIONS:
                current = roster[(case, ridge, repeat)]
                if current["step_signature"] != original:
                    repeat_mismatches.append(
                        {"case_id": case, "ridge": ridge, "repetition": repeat}
                    )
    issues = [
        {
            "fold_index": fold["index"],
            "case_id": fold["case_id"],
            "issues": fold["issues"],
            "failures": fold["failures"],
        }
        for fold in fold_records
        if fold["issues"]
    ]
    if issues or repeat_mismatches:
        # Original failures remain visible, but cannot become fitting rows.
        status = "blocked_original_work_or_repeat_identity"
        folds, decision = [], {"supports_online_experiment_design": False}
    else:
        status = "complete"
        folds, decision = _cross_validate(canonical_rows)
    report = {
        "schema_version": "rc-line-search-alpha-offline-screen.v1",
        "status": status,
        "original_packet_inventory_sha256": INVENTORY_SHA256,
        "original_numerical_source_revision": SOURCE_REVISION,
        "source_bound_file_count": len(packet.consumed),
        "eligible_groups": [list(group) for group in GROUPS],
        "reserved_cases_read": 0,
        "solver_calls": 0,
        "offline_train_only_normalizations": len(folds),
        "structural_solver_or_seed_policy_fits": 0,
        "alpha_grid": list(ALPHAS),
        "feature_names": list(FEATURE_NAMES),
        "canonical_ridge": RIDGES[0],
        "canonical_repetition": 0,
        "folds_checked": len(fold_records),
        "canonical_cases": len(cases),
        "fold_issues": issues,
        "repeat_mismatches": repeat_mismatches,
        "fold_bindings": [
            {
                k: fold[k]
                for k in (
                    "index",
                    "case_id",
                    "ridge",
                    "repetition",
                    "report_hash",
                    "secant_path_hash",
                )
            }
            for fold in fold_records
        ],
        "rows": canonical_rows,
        "observed_line_search_events": len(canonical_rows),
        "observed_first_alpha_failures": sum(
            row["first_accepted_index"] is not None and row["first_accepted_index"] >= 1
            for row in canonical_rows
        ),
        "observed_failed_trial_evaluations": sum(
            row["observed_failed_trial_count"] for row in canonical_rows
        ),
        "null_labels": sum(
            row["first_accepted_index"] is None for row in canonical_rows
        ),
        "group_held_out_screen": folds,
        "screen_decision": decision,
        "cost_boundary": (
            "Trial counts are logged work proxies, not saved time. No new path or "
            "counterfactual alpha outcome was executed. Historical training, "
            "path, verification, and audit intervals are separate."
        ),
    }
    report["diagnostics"] = _diagnostics(report)
    report["report_hash"] = "sha256:" + _hash(_json_bytes(report))
    return report


def _diagnostics(report: dict[str, Any]) -> dict[str, Any]:
    """Describe existing gates without changing their authority or outcomes."""
    counts: dict[str, int] = {}
    for fold in report["fold_issues"]:
        for failure in fold["failures"]:
            code = failure["code"]
            counts[code] = counts.get(code, 0) + 1
    if report["repeat_mismatches"]:
        counts["repeat_identity_mismatch"] = len(report["repeat_mismatches"])
    decision = report["screen_decision"]
    if report["status"] != "complete":
        classification = "blocked_original_evidence"
        summary = "Blocked: original work or repeat identity is not verified."
    elif decision["supports_online_experiment_design"]:
        classification = "offline_design_support_only"
        summary = "Offline screen supports experiment design only; no online result is verified."
    elif decision["false_skips"]:
        classification = "false_skip_gate_failed"
        summary = "Offline screen does not support experiment design: false skips were observed."
    else:
        classification = "insufficient_group_support"
        summary = (
            "Offline screen does not support experiment design: "
            "group support is insufficient."
        )
    return {
        "schema_version": "rc-line-search-alpha-screen-diagnostics.v1",
        "classification": classification,
        "failure_counts": dict(sorted(counts.items())),
        "summary": summary,
        "boundary": "Zero solver calls; trial counts are work proxies, not measured time savings.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        report = screen_packet(args.packet_root)
    except TraceError as exc:
        print(json.dumps({
            "status": "rejected_input", "failure_code": exc.code,
            "summary": "Input rejected; no screen decision or report was produced.",
            "solver_calls": 0,
        }, sort_keys=True))
        print("Input rejected; no screen decision or report was produced.", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "events": report["observed_line_search_events"],
                "first_alpha_failures": report["observed_first_alpha_failures"],
                "screen_decision": report["screen_decision"],
                "diagnostics": report["diagnostics"],
            },
            sort_keys=True,
        )
    )
    print(report["diagnostics"]["summary"], file=sys.stderr)
    print(report["diagnostics"]["boundary"], file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
