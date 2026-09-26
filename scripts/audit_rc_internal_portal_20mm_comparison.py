"""Read-only diagnostic projection of the existing RC research response rule.

This audits one pinned internal-corotational packet. It does not replay a solve,
establish public portal admission, or qualify physical accuracy or speed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from structural_analysis.benchmark import (
    rc_internal_portal_20mm_comparison as portal_runner,
)
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_checkpoint_io import (
    load_stateful_corotational_fiber_frame2d_checkpoint_bytes,
)
from structural_analysis.benchmark.fiber_frame_runtime import (
    _numeric_payload_difference,
)
from structural_analysis.benchmark.rc_internal_portal_20mm_comparison import (
    ARM_ORDERS,
    CANDIDATE_MODEL_HASH,
    INTERNAL_PROBLEM_HASH,
    MODE_ORDERS,
    ORIGINAL_MODEL_SHA256,
    ORIGINAL_REQUEST_SHA256,
    PREFLIGHT_PRELOAD_HASH,
    TARGETS_M,
    prepare_case,
)


SCHEMA_VERSION = "internal-rc-portal-20mm-response-diagnostic.v1"
PACKET_SOURCE_REVISION = "1500212a51992a43ccf1dbbe1b6af5c50e8b8cf5"
PLAN_FILE_HASH = (
    "sha256:9d9287503cc99bdff63e46691949b1ec12f669e8eddf84a9d15468f2d4b315ff"
)
OUTCOME_FILE_HASH = (
    "sha256:2b58e829e27faa90ca853dca6a6ca2977d04062f4fb4a5b174907af680817df7"
)
ABSOLUTE_TOLERANCE = 1.0e-10
RELATIVE_TOLERANCE = 1.0e-8
_MAX_JSON_BYTES = 16 * 1024 * 1024
_RESPONSE_GROUPS = (
    "load_factor",
    "node_displacements",
    "support_reactions",
    "member_end_forces",
    "section_results",
    "fiber_results",
    "accepted_section_states",
)


class PortalResponseAuditError(ValueError):
    """A stored packet or its aligned accepted response is not trustworthy."""


def _canonical(payload: Any) -> bytes:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PortalResponseAuditError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PortalResponseAuditError(f"non-finite JSON constant: {value}")


def _read_verified(path: Path, expected_byte_hash: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if not raw or len(raw) > _MAX_JSON_BYTES or _sha(raw) != expected_byte_hash:
        raise PortalResponseAuditError(f"artifact byte hash or size mismatch: {path}")
    try:
        value = json.loads(
            raw, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
        if type(value) is not dict or _canonical(value) != raw:
            raise PortalResponseAuditError(f"artifact is not canonical JSON: {path}")
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, PortalResponseAuditError):
            raise
        raise PortalResponseAuditError(f"invalid artifact JSON: {path}") from exc
    return value


def _self_hash(payload: dict[str, Any], key: str) -> str:
    expected = payload.get(key)
    if type(expected) is not str:
        raise PortalResponseAuditError(f"missing {key}")
    actual = _sha(
        _canonical({name: value for name, value in payload.items() if name != key})
    )
    if actual != expected:
        raise PortalResponseAuditError(f"{key} does not match payload")
    return actual


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PortalResponseAuditError(message)


def _validated_projection(step: dict[str, Any], case: Any) -> dict[str, Any]:
    """Project accepted response fields analogous to the old public RC roster."""

    _require(step.get("committed") is True, "response step is not committed")
    checkpoint = step["accepted_checkpoint"]
    parent = step["parent_checkpoint"]
    assembly = step["trial_assembly"]
    native = load_stateful_corotational_fiber_frame2d_checkpoint_bytes(
        _canonical(checkpoint), case.problem
    )
    _require(
        native.state_hash == checkpoint["state_hash"], "native checkpoint hash changed"
    )
    _require(
        checkpoint["parent_state_hash"] == parent["state_hash"]
        and assembly["parent_checkpoint_hash"] == parent["state_hash"]
        and assembly["target_load_factor"] == checkpoint["load_factor"]
        and assembly["global_displacements"] == checkpoint["global_displacements"],
        "accepted response does not bind to its parent and assembly",
    )
    displacements = checkpoint["global_displacements"]
    reactions = assembly["reactions_global"]
    _require(
        len(displacements) == len(reactions) == 12, "portal response DOF count changed"
    )
    node_ids = ("N1", "N2", "N3", "N4")
    node_displacements = [
        {
            "node_id": node,
            "UX_m": displacements[3 * index],
            "UY_m": displacements[3 * index + 1],
            "RZ_rad": displacements[3 * index + 2],
        }
        for index, node in enumerate(node_ids)
    ]
    support_reactions = [
        {
            "node_id": node,
            "FX_N": reactions[3 * index] * 1000.0,
            "FY_N": reactions[3 * index + 1] * 1000.0,
            "MZ_Nm": reactions[3 * index + 2] * 1000.0,
        }
        for index, node in enumerate(node_ids[:2])
    ]
    members: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    fibers: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    member_assemblies = assembly["member_assemblies"]
    element_states = checkpoint["element_states"]
    _require(
        len(member_assemblies) == len(element_states) == len(case.problem.members) == 3,
        "portal member roster changed",
    )
    for member, member_assembly, element_state in zip(
        case.problem.members, member_assemblies, element_states, strict=True
    ):
        _require(
            member_assembly["member_id"] == member.member_id, "member identity changed"
        )
        response = member_assembly["element_response"]
        beam = response["fiber_beam_response"]
        _require(
            element_state == response["trial_state"],
            "element trial state differs from accepted state",
        )
        local_force = beam["internal_force_local"]
        _require(len(local_force) == 6, "member end-force roster changed")
        members.append(
            {
                "member_id": member.member_id,
                "node_i": node_ids[member.node_i],
                "node_j": node_ids[member.node_j],
                "local_end_i": dict(
                    zip(
                        ("FX_N", "FY_N", "MZ_Nm"),
                        (value * 1000.0 for value in local_force[:3]),
                        strict=True,
                    )
                ),
                "local_end_j": dict(
                    zip(
                        ("FX_N", "FY_N", "MZ_Nm"),
                        (value * 1000.0 for value in local_force[3:]),
                        strict=True,
                    )
                ),
                "dissipated_energy_MJ": beam["dissipated_energy_mj"],
            }
        )
        section_states = element_state["basic_beam_state"]["integration_point_states"]
        section_responses = beam["section_responses"]
        xi = beam["integration_point_xi"]
        weights = beam["integration_point_weights"]
        _require(
            len(section_states) == len(section_responses) == len(xi) == len(weights),
            "integration-point roster changed",
        )
        states.append(
            {"member_id": member.member_id, "integration_point_states": section_states}
        )
        for point_index, (
            section_state,
            section_response,
            location,
            weight,
        ) in enumerate(
            zip(section_states, section_responses, xi, weights, strict=True)
        ):
            _require(
                section_state == section_response["trial_state"],
                "section trial state differs from accepted state",
            )
            resultants = section_response["resultants"]
            strain = section_response["generalized_strain"]
            sections.append(
                {
                    "member_id": member.member_id,
                    "integration_point_index": point_index,
                    "xi": location,
                    "weight": weight,
                    "axial_strain": strain["axial_strain"],
                    "curvature_z_per_m": strain["curvature_z_per_m"],
                    "axial_force_N": resultants["axial_force_kn"] * 1000.0,
                    "moment_z_Nm": resultants["moment_z_kn_m"] * 1000.0,
                    "dissipated_energy_MJ_per_m": section_response[
                        "dissipated_energy_mj_per_m"
                    ],
                    "section_state_hash": section_state["state_hash"],
                }
            )
            fiber_states = section_state["fiber_states"]
            fiber_strains = section_response["fiber_strains"]
            fiber_stresses = section_response["fiber_stresses_mpa"]
            fiber_responses = section_response["fiber_responses"]
            fiber_definitions = member.element.section.fibers
            _require(
                len(fiber_states)
                == len(fiber_strains)
                == len(fiber_stresses)
                == len(fiber_responses)
                == len(fiber_definitions),
                "fiber roster changed",
            )
            for fiber_index, (
                fiber,
                material,
                fiber_strain,
                stress,
                fiber_response,
            ) in enumerate(
                zip(
                    fiber_definitions,
                    fiber_states,
                    fiber_strains,
                    fiber_stresses,
                    fiber_responses,
                    strict=True,
                )
            ):
                _require(
                    material == fiber_response["trial_state"],
                    "fiber trial state differs from accepted state",
                )
                fibers.append(
                    {
                        "member_id": member.member_id,
                        "integration_point_index": point_index,
                        "fiber_index": fiber_index,
                        "fiber_id": fiber.fiber_id,
                        "material_kind": fiber.material_kind,
                        "y_m": fiber.y_m,
                        "area_m2": fiber.area_m2,
                        "strain": fiber_strain,
                        "stress_MPa": stress,
                        "dissipated_energy_density_MJ_per_m3": material[
                            "dissipated_energy_density_mj_per_m3"
                        ],
                        "material_state": material,
                    }
                )
    return {
        "load_factor": checkpoint["load_factor"],
        "node_displacements": node_displacements,
        "support_reactions": support_reactions,
        "member_end_forces": members,
        "section_results": sections,
        "fiber_results": fibers,
        "accepted_section_states": states,
        "material_point_count": len(fibers),
        "epoch": checkpoint["epoch"],
        "step_index": checkpoint["step_index"],
        "checkpoint_hash": checkpoint["state_hash"],
        "parent_checkpoint_hash": checkpoint["parent_state_hash"],
    }


def _compare_projection(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    schedule_identity_exact = (
        reference["epoch"] == candidate["epoch"]
        and reference["step_index"] == candidate["step_index"]
    )
    material_point_count_exact = (
        reference["material_point_count"] == candidate["material_point_count"]
    )
    groups: dict[str, dict[str, Any]] = {}
    for field in _RESPONSE_GROUPS:
        structure, maximum_absolute, maximum_relative, within = (
            _numeric_payload_difference(
                reference[field],
                candidate[field],
                absolute_tolerance=ABSOLUTE_TOLERANCE,
                relative_tolerance=RELATIVE_TOLERANCE,
            )
        )
        groups[field] = {
            "structure_and_non_numeric_identity_match": structure,
            "within_existing_research_tolerance": within,
            "maximum_absolute_difference_mixed_SI_fields": (
                maximum_absolute if math.isfinite(maximum_absolute) else None
            ),
            "maximum_relative_difference": maximum_relative
            if math.isfinite(maximum_relative)
            else None,
        }
    return {
        "schedule_identity_exact": schedule_identity_exact,
        "material_point_count": reference["material_point_count"],
        "material_point_count_exact": material_point_count_exact,
        "checkpoint_hash_exact": reference["checkpoint_hash"]
        == candidate["checkpoint_hash"],
        "parent_checkpoint_hash_exact": (
            reference["parent_checkpoint_hash"] == candidate["parent_checkpoint_hash"]
        ),
        "nested_hash_identities": _hash_identity_report(reference, candidate),
        "groups": groups,
        "diagnostic_response_match": schedule_identity_exact
        and material_point_count_exact
        and all(
            row["structure_and_non_numeric_identity_match"]
            and row["within_existing_research_tolerance"]
            for row in groups.values()
        ),
    }


def _hash_identity_report(reference: Any, candidate: Any) -> dict[str, Any]:
    compared = 0
    mismatched = 0
    examples: list[list[str | int]] = []

    def walk(left: Any, right: Any, path: tuple[str | int, ...]) -> None:
        nonlocal compared, mismatched
        if type(left) is dict and type(right) is dict:
            for key in sorted(set(left) | set(right)):
                if key.endswith(("hash", "hashes")):
                    compared += 1
                    if key not in left or key not in right or left[key] != right[key]:
                        mismatched += 1
                        if len(examples) < 12:
                            examples.append([*path, key])
                elif key in left and key in right:
                    walk(left[key], right[key], (*path, key))
        elif type(left) is list and type(right) is list:
            for index, (left_item, right_item) in enumerate(zip(left, right)):
                walk(left_item, right_item, (*path, index))

    walk(reference, candidate, ())
    return {
        "compared_fields": compared,
        "mismatched_fields": mismatched,
        "mismatch_path_examples": examples,
        "examples_truncated": mismatched > len(examples),
        "excluded_from_numeric_tolerance_gate": True,
    }


def _verified_arm(
    root: Path, row: dict[str, Any], arm: str, case: Any
) -> dict[str, Any]:
    arm_root = root / f"{row['identity']}-{arm}"
    path_raw = (arm_root / "path.json").read_bytes()
    path = _read_verified(arm_root / "path.json", _sha(path_raw))
    _require(
        _self_hash(path, "path_hash") == row["arm_path_hashes"][arm],
        "path hash differs from comparison row",
    )
    _require(
        path["status"] == "complete"
        and path["work_complete"]
        and path["unknown_work"] is False,
        "path is not complete with known work",
    )
    _require(
        path["arm"] == arm and path["mode"] == row["mode"], "path arm or mode changed"
    )
    _require(
        path["preload_reexecuted_from_fresh_genesis"] is True, "fresh preload missing"
    )
    preload = path["preload"]
    _require(
        preload["status"] == "ready"
        and preload["checkpoint_hash"] == PREFLIGHT_PRELOAD_HASH,
        "pinned preload failed",
    )
    preload_step = _read_verified(
        arm_root / "preload-step.json", preload["step_artifact_hash"]
    )
    _require(
        preload_step["accepted_checkpoint"]["state_hash"] == preload["checkpoint_hash"],
        "preload step hash binding changed",
    )
    _require(
        preload_step["parent_checkpoint"]["state_hash"] == preload["genesis_hash"],
        "preload genesis binding changed",
    )
    projections = [_validated_projection(preload_step, case)]
    attempts: list[list[dict[str, Any]]] = []
    previous_hash = preload["checkpoint_hash"]
    histories = path["target_history"]
    _require(
        len(histories) == len(TARGETS_M) == len(path["accepted_checkpoint_hashes"]),
        "target history length changed",
    )
    for target_index, (target, history) in enumerate(
        zip(TARGETS_M, histories, strict=True)
    ):
        _require(
            history["target_index"] == target_index and history["target_m"] == target,
            "target schedule changed",
        )
        _require(history["parent_hash"] == previous_hash, "target parent chain changed")
        target_attempts: list[dict[str, Any]] = []
        accepted: list[dict[str, Any]] = []
        for attempt_index, record in enumerate(history["invocations"]):
            _require(
                record["status"] == "returned" and record["unknown_work"] is False,
                "attempt work is unknown",
            )
            step = _read_verified(
                arm_root
                / f"target-{target_index:03d}-attempt-{attempt_index}-step.json",
                record["step_artifact_hash"],
            )
            _require(
                step["parent_checkpoint"]["state_hash"] == previous_hash,
                "attempt parent changed",
            )
            _require(
                step["committed"] is record["committed"],
                "attempt commit status changed",
            )
            if step["committed"]:
                accepted.append(step)
            else:
                _require(
                    step["accepted_checkpoint"]["state_hash"] == previous_hash
                    and step["metrics"]["rollback_exact"] is True,
                    "failed attempt did not retain its parent",
                )
            target_attempts.append(
                {
                    "committed": record["committed"],
                    "terminal_reason": record["terminal_reason"],
                    "work": record["work"],
                    "step_artifact_hash": record["step_artifact_hash"],
                }
            )
        _require(
            len(accepted) == 1, "target does not have exactly one accepted attempt"
        )
        selected = accepted[0]
        accepted_hash = selected["accepted_checkpoint"]["state_hash"]
        _require(
            accepted_hash
            == history["accepted_checkpoint_hash"]
            == path["accepted_checkpoint_hashes"][target_index],
            "accepted target hash chain changed",
        )
        _require(
            selected["accepted_checkpoint"]["global_displacements"][9] == target,
            "accepted control coordinate changed",
        )
        projections.append(_validated_projection(selected, case))
        attempts.append(target_attempts)
        previous_hash = accepted_hash
    _require(
        path["final_checkpoint_hash"] == previous_hash, "path final checkpoint changed"
    )
    _require(
        all(not entry["recovery_stages"] for entry in histories),
        "unmodeled continuation stages present",
    )
    return {
        "path_hash": path["path_hash"],
        "accepted_checkpoint_hashes": path["accepted_checkpoint_hashes"],
        "known_work_lower_bound": path["known_work_lower_bound"],
        "attempts_by_target": attempts,
        "projections": projections,
    }


def audit_packet(root: Path) -> dict[str, Any]:
    """Validate the pinned packet and compare aligned accepted response fields."""

    plan = _read_verified(root / "plan.json", PLAN_FILE_HASH)
    outcome = _read_verified(root / "outcome.json", OUTCOME_FILE_HASH)
    _require(
        _self_hash(plan, "plan_hash") == outcome["plan_hash"],
        "plan/outcome binding changed",
    )
    _self_hash(outcome, "outcome_hash")
    _require(
        plan["source_revision"] == PACKET_SOURCE_REVISION,
        "packet source revision changed",
    )
    _require(
        plan["original_model_hash"] == "sha256:" + ORIGINAL_MODEL_SHA256
        and plan["original_request_hash"] == "sha256:" + ORIGINAL_REQUEST_SHA256
        and plan["candidate_model_hash"] == CANDIDATE_MODEL_HASH
        and plan["internal_problem_contract_hash"] == INTERNAL_PROBLEM_HASH,
        "packet input identity changed",
    )
    _require(
        _sha(Path(portal_runner.__file__).read_bytes()) == plan["runner_source_hash"],
        "local runner source differs from packet",
    )
    _require(
        outcome["source_unchanged"] is True
        and outcome["exact_source_comparison_eligible"] is True
        and outcome["observations_complete"] is True
        and outcome["completed_paths"] == 16,
        "packet was not complete at its pinned source",
    )
    _require(
        outcome["qualified_fixed_adaptive_timing_ratio"] is None
        and outcome["learned_benefit_conclusion"] is None,
        "packet qualification boundary changed",
    )
    _require(len(outcome["rows"]) == 4, "comparison roster changed")
    case = prepare_case()
    _require(
        case.problem.contract_hash == plan["internal_problem_contract_hash"],
        "local problem contract changed",
    )
    rows: list[dict[str, Any]] = []
    verified_step_artifacts = 0
    for repeat, mode_order in enumerate(MODE_ORDERS):
        for mode in mode_order:
            identity = f"20mm-r{repeat}-{mode}"
            row = outcome["rows"][len(rows)]
            _require(
                row["identity"] == identity
                and row["status"] == "returned"
                and row["unknown_work"] is False
                and row["arm_order"] == list(ARM_ORDERS[repeat])
                and row["recovery_exercised"] is False,
                "comparison row roster or status changed",
            )
            _require(
                set(row["arm_statuses"])
                == set(row["arm_path_hashes"])
                == set(ARM_ORDERS[repeat])
                and all(
                    status == "complete" for status in row["arm_statuses"].values()
                ),
                "comparison arm status or hash roster changed",
            )
            arms = {
                arm: _verified_arm(root, row, arm, case) for arm in ARM_ORDERS[repeat]
            }
            reference = arms["fresh_reference"]["projections"]
            comparisons: dict[str, Any] = {}
            for arm in ARM_ORDERS[repeat]:
                candidate = arms[arm]["projections"]
                steps = [
                    {
                        **_compare_projection(left, right),
                        "phase": "preload" if index == 0 else "target",
                        "target_m": None if index == 0 else TARGETS_M[index - 1],
                    }
                    for index, (left, right) in enumerate(
                        zip(reference, candidate, strict=True)
                    )
                ]
                comparisons[arm] = {
                    "preload_and_target_steps": steps,
                    "diagnostic_full_accepted_response_match": all(
                        step["diagnostic_response_match"] for step in steps
                    ),
                    "accepted_checkpoint_hashes_exact": (
                        arms[arm]["accepted_checkpoint_hashes"]
                        == arms["fresh_reference"]["accepted_checkpoint_hashes"]
                    ),
                    "known_work_lower_bound": arms[arm]["known_work_lower_bound"],
                    "attempts_by_target": arms[arm]["attempts_by_target"],
                    "path_hash": arms[arm]["path_hash"],
                }
                verified_step_artifacts += 1 + sum(
                    len(target_attempts)
                    for target_attempts in arms[arm]["attempts_by_target"]
                )
            rows.append(
                {"identity": identity, "comparisons_to_fresh_reference": comparisons}
            )
    _require(verified_step_artifacts == 68, "step artifact roster changed")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "read_only_diagnostic_projection",
        "auditor_source_hash": _sha(Path(__file__).read_bytes()),
        "packet_source_revision": PACKET_SOURCE_REVISION,
        "plan_hash": plan["plan_hash"],
        "outcome_hash": outcome["outcome_hash"],
        "comparison_rule_source": "rc_control_seed_runtime.py defaults; fiber_frame_runtime.py numeric payload rule",
        "absolute_tolerance": ABSOLUTE_TOLERANCE,
        "relative_tolerance": RELATIVE_TOLERANCE,
        "tolerance_rule": "abs_delta <= atol + rtol * max(abs(left), abs(right))",
        "scope": "preload plus every accepted target response; no attempt-sequence equivalence",
        "excluded_from_numeric_projection": [
            "Newton and line-search histories",
            "algorithmic tangents and Jacobians",
            "checkpoint and parent hash identities (reported separately)",
            "attempt work and timing (reported without speed credit)",
        ],
        "verified_step_artifacts": verified_step_artifacts,
        "rows": rows,
        "all_diagnostic_accepted_response_matches": all(
            comparison["diagnostic_full_accepted_response_match"]
            for row in rows
            for comparison in row["comparisons_to_fresh_reference"].values()
        ),
        "qualified_fixed_adaptive_timing_ratio": None,
        "learned_benefit_conclusion": None,
        "independent_physical_validation": False,
        "public_portal_admission": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("packet_directory", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_packet(args.packet_directory)
    except (PortalResponseAuditError, OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"audit failed closed: {type(exc).__name__}: {exc}\n")
    raw = _canonical(report) + b"\n"
    if args.output is None:
        print(raw.decode("utf-8"), end="")
    else:
        _require(
            not args.output.resolve().is_relative_to(args.packet_directory.resolve()),
            "audit output may not modify the source packet",
        )
        with args.output.open("xb") as handle:
            handle.write(raw)
        print(
            json.dumps(
                {"output": str(args.output), "report_sha256": _sha(raw)}, sort_keys=True
            )
        )
    if not report["all_diagnostic_accepted_response_matches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
