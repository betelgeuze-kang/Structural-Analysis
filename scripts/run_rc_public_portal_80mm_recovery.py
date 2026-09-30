"""One bounded off-product recovery study for the pinned public 80 mm portal.

The comparison runner owns all native invocations and persists each attempted
step. This wrapper binds the exact source bytes and checks the failure, frozen
parent, native confirmation, and work accounting before reporting an outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from time import perf_counter_ns, process_time_ns

from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.api.nonlinear_fiber_frame import (
    EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE,
)
from structural_analysis.benchmark.rc_control_seed_runtime import (
    benchmark_rc_control_seed_paths,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "examples/research/rc_internal_portal_20mm"
MODEL_NAME = "original-model.json"
REQUEST_NAME = "experimental-two-fixed-endpoints-derived-80mm-request.json"
MODEL_SHA256 = "6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6"
REQUEST_SHA256 = "abf8d1d84a6b05af107730494ae5440deb305ceae123b91ceb5c92eb5feea782"
TARGETS_M = (-0.04, -0.08, 0.04)
MAXIMUM_NATIVE_CALLS = 4 * (1 + 2 * len(TARGETS_M)) + 64 * len(TARGETS_M)


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _source_revision() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True, cwd=REPO_ROOT
    ).strip()


def _canonical(payload: object) -> bytes:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode()


def _write(path: Path, payload: object) -> None:
    path.write_bytes(_canonical(payload) + b"\n")


def _read_bound_trial(path: Path, binding: dict) -> dict:
    if path.name != binding["path"]:
        raise ValueError("continuation artifact path escapes its arm")
    raw = path.read_bytes()
    if len(raw) != binding["byte_length"] or "sha256:" + _hash(raw) != binding["sha256"]:
        raise ValueError("continuation artifact byte binding changed")
    return json.loads(raw)


def audit_trial_artifacts(report: dict, comparison_root: Path) -> dict[str, int]:
    """Check trial byte bindings and direct-step parent/rollback records."""
    proposal = report["arms"]["proposal"]
    direct_steps = continuation_trials = 0
    for index, entry in enumerate(proposal["entries"]):
        parent_hash = entry["parent_hash"]
        for ordinal, invocation in enumerate(entry["invocations"], 1):
            if invocation["status"] != "returned":
                continue
            step = json.loads(
                (comparison_root / "proposal" / f"{index:03d}-{ordinal}-step.json").read_bytes()
            )
            if (
                step["parent_checkpoint"]["state_hash"] != parent_hash
                or step["committed"] != invocation["committed"]
                or step["metrics"]["rollback_exact"] != invocation["rollback_exact"]
                or (
                    not step["committed"]
                    and step["accepted_checkpoint"] != step["parent_checkpoint"]
                )
            ):
                raise ValueError("native invocation parent/rollback artifact mismatch")
            direct_steps += 1
        numerical = entry.get("numerical_proposal")
        if numerical is None:
            continue
        if (
            numerical["parent_hash"] != parent_hash
            or numerical["parent_unchanged"] is not True
            or numerical["intermediate_material_checkpoints_adopted"] is not False
            or len(numerical["stages"]) != numerical["native_core_calls_attempted"]
        ):
            raise ValueError("continuation parent/count binding mismatch")
        for stage in numerical["stages"]:
            if stage["parent_hash"] != parent_hash:
                raise ValueError("continuation stage changed its parent")
            if "artifact" not in stage:
                if not stage["unknown_work"]:
                    raise ValueError("known continuation stage lacks its artifact")
                continue
            trial = _read_bound_trial(
                comparison_root / "proposal" / stage["artifact"]["path"],
                stage["artifact"],
            )
            if (
                trial["parent_checkpoint"]["state_hash"] != parent_hash
                or trial["committed"] != stage["committed"]
                or (
                    not trial["committed"]
                    and (
                        trial["accepted_checkpoint"] != trial["parent_checkpoint"]
                        or trial["metrics"]["rollback_exact"] is not True
                    )
                )
            ):
                raise ValueError("continuation trial parent/rollback artifact mismatch")
            continuation_trials += 1
    return {
        "continuation_trials_byte_bound_and_parent_rollback_checked": continuation_trials,
        "direct_steps_parent_rollback_checked": direct_steps,
    }


def pinned_inputs():
    model_bytes = (SOURCE_DIR / MODEL_NAME).read_bytes()
    request_bytes = (SOURCE_DIR / REQUEST_NAME).read_bytes()
    if _hash(model_bytes) != MODEL_SHA256 or _hash(request_bytes) != REQUEST_SHA256:
        raise ValueError("pinned portal source bytes changed")
    model = load_neutral_json_bytes(model_bytes)
    request = decode_bounded_rc_fiber_direct_control_request(request_bytes)
    if (
        request.targets_m != TARGETS_M
        or request.experimental_two_fixed_endpoints is not True
        or request.constant_nodal_loads
        != (("N3", 0.0, -25.0, 0.0), ("N4", 0.0, -25.0, 0.0))
        or request.control_global_dof != 9
    ):
        raise ValueError("pinned portal request contract changed")
    return model_bytes, request_bytes, model, request


def validate_comparison_source_binding(
    report: dict, comparison_root: Path, model, request, revision: str,
) -> None:
    """Bind the entire stored comparison to the pinned compiled input identity."""
    raw = (comparison_root / "comparison.json").read_bytes()
    identity = json.loads((comparison_root / "request.json").read_bytes())
    bindings = (
        report["source_revision"] == revision
        and report["source_revision_is_attestation"] is False
        and report["request"] == request.to_dict()
        and report["model_checksum"] == model.canonical_model_checksum
        and report["compiler_profile"]
        == EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE
        and identity["source_revision"] == revision
        and identity["request"] == request.to_dict()
        and identity["model_checksum"] == model.canonical_model_checksum
        and identity["compiler_profile"]
        == EXPERIMENTAL_RC_FIBER_FRAME_TWO_FIXED_ENDPOINT_CONTROL_PROFILE
        and (comparison_root / "model.json").read_bytes()
        == _canonical(model.canonical_payload())
    )
    body = {key: value for key, value in report.items() if key != "report_hash"}
    if (
        not bindings
        or raw != _canonical(report)
        or report["report_hash"] != "sha256:" + _hash(_canonical(body))
    ):
        raise ValueError("full comparison report source binding mismatch")


def summarize(report: dict) -> dict:
    """Keep blocked paths and proposal trials in the known-work denominator."""
    arms = {**report["arms"], "fresh-reference": report["fresh_reference"]}
    if set(arms) != {"reference", "secant", "proposal", "fresh-reference"}:
        raise ValueError("unexpected recovery arm set")
    original = arms["proposal"]["entries"][0]
    direct = original["invocations"][0]
    parent = original["parent_hash"]
    if (
        direct["seed_used"] is not False
        or direct["committed"] is not False
        or direct["rollback_exact"] is not True
        or direct["unknown_work"] is not False
        or direct["work"] is None
    ):
        raise ValueError("original failed native attempt was not retained")
    numerical = original.get("numerical_proposal")
    if numerical is None or numerical["parent_hash"] != parent:
        raise ValueError("failed-target recovery is not parent-bound")
    if (
        numerical["intermediate_material_checkpoints_adopted"] is not False
        or numerical["parent_unchanged"] is not True
        or any(stage["parent_hash"] != parent for stage in numerical["stages"])
    ):
        raise ValueError("frozen-parent recovery did not preserve exact rollback")
    if numerical["native_core_calls_attempted"] > 64:
        raise ValueError("first-target recovery exceeded its native budget")
    if numerical["seed"] is not None:
        confirmed = original["invocations"][1]
        if confirmed["seed_used"] is not True or confirmed["unknown_work"] is not False:
            raise ValueError("recovery seed lacked a known native confirmation")
    else:
        confirmed = None
    for entry in arms["proposal"]["entries"]:
        candidate = entry.get("numerical_proposal")
        if candidate is None:
            continue
        if (
            candidate["parent_hash"] != entry["parent_hash"]
            or candidate["parent_unchanged"] is not True
            or candidate["intermediate_material_checkpoints_adopted"] is not False
            or candidate["native_core_calls_attempted"] > 64
            or any(
                stage["parent_hash"] != entry["parent_hash"]
                for stage in candidate["stages"]
            )
        ):
            raise ValueError("later recovery changed its native parent or budget")

    calls = solves = iterations = unknown_attempts = 0
    unknown = False
    for arm in arms.values():
        invocations = [*arm.get("preload_invocations", [])]
        invocations.extend(
            invocation
            for entry in arm["entries"]
            for invocation in entry["invocations"]
        )
        for invocation in invocations:
            work = invocation.get("work")
            unknown |= invocation["unknown_work"] or work is None
            calls += 1
            if work is not None:
                if work["core_calls"] != 1:
                    raise ValueError("native invocation count binding mismatch")
                if (
                    type(work["linear_solves"]) is int
                    and type(work["newton_iterations"]) is int
                    and work["linear_solves"] >= 0
                    and work["newton_iterations"] >= 0
                ):
                    solves += work["linear_solves"]
                    iterations += work["newton_iterations"]
                else:
                    unknown = True
                    unknown_attempts += 1
            else:
                unknown_attempts += 1
    proposal_work = report["numerical_proposal_work"]
    stages = [
        stage
        for entry in arms["proposal"]["entries"]
        for stage in entry.get("numerical_proposal", {}).get("stages", [])
    ]
    if any(
        not stage["unknown_work"]
        and (
            type(stage.get("linear_solves")) is not int
            or type(stage.get("newton_iterations")) is not int
            or stage["linear_solves"] < 0
            or stage["newton_iterations"] < 0
        )
        for stage in stages
    ):
        raise ValueError("known continuation stage lacks valid solver work")

    def known_stage_total(key: str) -> int:
        return sum(
            value
            for stage in stages
            if type(value := stage.get(key)) is int and value >= 0
        )

    if (
        len(stages) != proposal_work["native_core_calls_attempted"]
        or known_stage_total("linear_solves") != proposal_work["known_linear_solves"]
        or known_stage_total("newton_iterations")
        != proposal_work["known_newton_iterations"]
    ):
        raise ValueError("proposal work differs from its retained stages")
    calls += proposal_work["native_core_calls_attempted"]
    solves += proposal_work["known_linear_solves"]
    iterations += proposal_work["known_newton_iterations"]
    unknown_stages = sum(stage["unknown_work"] for stage in stages)
    unknown_attempts += unknown_stages
    unknown |= (
        unknown_stages > 0
        or proposal_work["unknown_work"]
        or not report["all_execution_work_reported"]
    )
    if calls > MAXIMUM_NATIVE_CALLS:
        raise ValueError("whole study exceeded its native call bound")
    return {
        "schema_version": "rc-public-portal-80mm-frozen-parent-outcome.v1",
        "source_revision": report["source_revision"],
        "source_revision_is_attestation": False,
        "original_model_sha256": MODEL_SHA256,
        "original_80mm_request_sha256": REQUEST_SHA256,
        "comparison_report_hash": report["report_hash"],
        "requested_targets_m": list(TARGETS_M),
        "recovery_profile": report["numerical_proposal"]["identity"],
        "maximum_native_calls": MAXIMUM_NATIVE_CALLS,
        "known_native_calls_attempted": calls,
        "known_linear_solves": solves,
        "known_newton_iterations": iterations,
        "unknown_work": bool(unknown),
        "unknown_solver_work_attempt_count": unknown_attempts,
        "original_failed_attempt": {
            "target_m": original["target_m"],
            "parent_hash": parent,
            "rollback_exact": direct["rollback_exact"],
            "known_linear_solves": direct["work"]["linear_solves"],
        },
        "recovery_by_attempted_target": [
            {
                "target_m": entry["target_m"],
                "status": candidate["status"],
                "reason": candidate.get("reason"),
                "parent_hash": entry["parent_hash"],
                "native_trials": candidate["native_core_calls_attempted"],
                "parent_unchanged": candidate["parent_unchanged"],
                "intermediate_material_checkpoints_adopted": False,
                "native_confirmation_attempted": candidate["seed"] is not None,
                "native_confirmation_committed": (
                    entry["invocations"][1]["committed"]
                    if candidate["seed"] is not None else None
                ),
            }
            for entry in arms["proposal"]["entries"]
            if (candidate := entry.get("numerical_proposal")) is not None
        ],
        "arm_statuses": {name: arm["status"] for name, arm in arms.items()},
        "accepted_target_counts": {
            name: arm["accepted_target_count"] for name, arm in arms.items()
        },
        "public_80mm_completion_established": False,
        "independent_physical_validation": False,
        "performance_improvement_established": False,
    }


def run(output_directory: Path) -> dict:
    model_bytes, request_bytes, model, request = pinned_inputs()
    revision = _source_revision()
    root = output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    (root / MODEL_NAME).write_bytes(model_bytes)
    (root / REQUEST_NAME).write_bytes(request_bytes)
    _write(root / "started.json", {
        "status": "started", "source_revision": revision,
        "source_revision_is_attestation": False,
        "maximum_native_calls": MAXIMUM_NATIVE_CALLS,
        "work_unknown_until_comparison_return": True,
    })
    wall, cpu = perf_counter_ns(), process_time_ns()
    try:
        report = benchmark_rc_control_seed_paths(
            model, request,
            source_revision=revision,
            output_directory=root / "comparison",
            arm_order=("reference", "secant", "proposal"),
            frozen_parent_continuation=True,
            continuation_on_failure=True,
            continuation_all_failed_targets=True,
            continuation_adaptive=True,
            record_assembly_work=True,
        )
        if (
            (root / MODEL_NAME).read_bytes() != model_bytes
            or (root / REQUEST_NAME).read_bytes() != request_bytes
        ):
            raise ValueError("copied original portal input bytes changed")
        validate_comparison_source_binding(
            report, root / "comparison", model, request, revision
        )
        outcome = summarize(report)
        outcome["full_comparison_source_binding_verified"] = True
        outcome["trial_artifact_audit"] = audit_trial_artifacts(
            report, root / "comparison"
        )
        outcome["comparison_cost"] = {
            "wall_ns": perf_counter_ns() - wall,
            "process_cpu_ns": process_time_ns() - cpu,
            "scope": "benchmark_call_trial_audit_and_outcome_classification_excluding_outcome_write",
        }
    except Exception as exc:
        outcome = {
            "schema_version": "rc-public-portal-80mm-frozen-parent-outcome.v1",
            "status": "raised",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "unknown_work": True,
            "public_80mm_completion_established": False,
            "independent_physical_validation": False,
            "comparison_cost": {
                "wall_ns": perf_counter_ns() - wall,
                "process_cpu_ns": process_time_ns() - cpu,
                "scope": "benchmark_call_and_exception_classification_excluding_outcome_write",
            },
        }
    _write(root / "outcome.json", outcome)
    return outcome


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()
    outcome = run(args.output_directory)
    print(json.dumps({
        "output_directory": str(args.output_directory.resolve()),
        "arm_statuses": outcome.get("arm_statuses"),
        "unknown_work": outcome["unknown_work"],
        "known_native_calls_attempted": outcome.get("known_native_calls_attempted"),
    }))
    if outcome.get("status") == "raised":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
