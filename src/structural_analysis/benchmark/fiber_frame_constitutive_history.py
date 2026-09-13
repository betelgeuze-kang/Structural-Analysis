"""Source-bound constitutive memory observations beside public RC response history.

The existing public history accessor owns all physical validation. This companion
only summarizes retained material states; state changes are not inferred Newton
yield events, independent validation, or cyclic-loading evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import math
from typing import Any

from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.concrete_damage import ConcreteDamageState
from structural_analysis.materials.stateful_fiber_section import StatefulRCFiberSection
from structural_analysis.materials.uniaxial_plasticity import UniaxialPlasticityState


SCHEMA_VERSION = "public-rc-fiber-frame-constitutive-history.v1"
_FIELDS = {
    "steel": {
        "accumulated_plastic_strain": ("1", "accumulated_plastic_memory"),
        "plastic_strain": ("1", "signed_plastic_strain"),
        "backstress_mpa": ("MPa", "signed_backstress"),
        "dissipated_energy_density_mj_per_m3": ("MJ/m^3", "cumulative_density"),
    },
    "concrete": {
        "tensile_history_strain": ("1", "maximum_tensile_history"),
        "compressive_history_strain": ("1", "maximum_compressive_history_magnitude"),
        "tensile_damage": ("1", "damage_memory"),
        "compressive_damage": ("1", "damage_memory"),
        "dissipated_energy_density_mj_per_m3": ("MJ/m^3", "cumulative_density"),
    },
}
_CLAIMS = {
    "independent_physical_validation": False,
    "cyclic_loading_verified": False,
    "production_promotion_eligible": False,
    "state_changes_identify_solver_yield_events": False,
    "density_sum_is_total_energy": False,
}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True)
class FiberFrameConstitutiveHistory:
    status: str
    contract_pass: bool
    report_hash: str
    _report_json: str = field(repr=False)

    def __post_init__(self) -> None:
        self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        """Check the local seal and claims; do not revalidate retained source.

        Source validation is an explicit, separate companion-validator call.
        """
        value = json.loads(self._report_json)
        if (
            type(value) is not dict
            or self.status != "ready"
            or self.contract_pass is not True
            or value.get("schema_version") != SCHEMA_VERSION
            or value.get("status") != self.status
            or value.get("contract_pass") is not True
            or value.get("report_hash") != self.report_hash
            or _json_bytes(value.get("claim_boundary")) != _json_bytes(_CLAIMS)
            or canonical_hash({k: v for k, v in value.items() if k != "report_hash"})
            != self.report_hash
        ):
            raise ValueError("constitutive history report integrity mismatch")
        return value


def _material_points(problem, checkpoint) -> tuple[tuple[tuple[Any, ...], dict], ...]:
    points = []
    for member, element in zip(problem.members, checkpoint.element_states, strict=True):
        section = member.element.section
        if type(section) is not StatefulRCFiberSection:
            raise ValueError("exact RC fiber section required")
        if len(element.integration_point_states) != len(member.element.quadrature[0]):
            raise ValueError("material integration-point coverage mismatch")
        for ip, state in enumerate(element.integration_point_states):
            section.validate_state(state)
            for index, (fiber, material) in enumerate(
                zip(section.fibers, state.fiber_states, strict=True)
            ):
                expected = {
                    "steel": UniaxialPlasticityState,
                    "concrete": ConcreteDamageState,
                }
                if (
                    fiber.material_kind not in expected
                    or type(material) is not expected[fiber.material_kind]
                ):
                    raise ValueError("unsupported constitutive state type")
                replace(material)
                values = {
                    name: getattr(material, name)
                    for name in _FIELDS[fiber.material_kind]
                }
                if any(
                    type(v) is not float or not math.isfinite(v)
                    for v in values.values()
                ):
                    raise ValueError("nonfinite or noncanonical constitutive value")
                label = (
                    member.member_id,
                    ip,
                    index,
                    fiber.fiber_id,
                    fiber.material_kind,
                )
                points.append((label, values))
    if not points or len({label for label, _ in points}) != len(points):
        raise ValueError("nonempty unique material-point identities required")
    return tuple(points)


def _summarize_points(points, previous=None) -> dict[str, Any]:
    """Compare matching native values directly; never sum densities or epochs."""
    if previous is not None and [p[0] for p in previous] != [p[0] for p in points]:
        raise ValueError("material-point identity/order changed between checkpoints")
    materials = {}
    for kind, fields in _FIELDS.items():
        indices = [i for i, point in enumerate(points) if point[0][-1] == kind]
        statistics = {}
        for name, (unit, interpretation) in fields.items():
            values = [points[i][1][name] for i in indices]
            prior = (
                None if previous is None else [previous[i][1][name] for i in indices]
            )
            statistics[name] = {
                "unit": unit,
                "interpretation": interpretation,
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
                "maximum_absolute": max(map(abs, values)) if values else None,
                "positive_value_point_count": sum(v > 0.0 for v in values),
                "changed_from_parent_point_count": None
                if prior is None
                else sum(a != b for a, b in zip(values, prior, strict=True)),
                "increased_from_parent_point_count": None
                if prior is None
                else sum(a > b for a, b in zip(values, prior, strict=True)),
                "decreased_from_parent_point_count": None
                if prior is None
                else sum(a < b for a, b in zip(values, prior, strict=True)),
                "parent_comparison_reason": "genesis_has_no_parent"
                if prior is None
                else None,
            }
        materials[kind] = {"point_count": len(indices), "fields": statistics}
    return {"material_point_count": len(points), "materials": materials}


def _source_snapshot(result):
    if result._problem is None or result._checkpoint_chain is None:
        raise ValueError(
            "retained public problem and complete checkpoint chain required"
        )
    return (
        json.dumps(
            public_api.PublicRCFiberFrameResult.to_dict(result),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8"),
        result._problem.contract_hash,
        public_api.PublicRCFiberFrameResult.checkpoint_artifact(result),
    )


def inspect_public_rc_fiber_frame_constitutive_history(
    result: public_api.PublicRCFiberFrameResult,
) -> FiberFrameConstitutiveHistory:
    """Validate the existing response history once, then summarize its source.

    Material points are member × integration point × modeled fiber, not individual
    reinforcing bars. Positive stored values and increases from the preceding
    checkpoint are distinct observations. Total MJ comes only from each original
    engineering recovery; genesis has no such recovery and remains unavailable.
    """
    if type(result) is not public_api.PublicRCFiberFrameResult:
        raise ValueError("exact PublicRCFiberFrameResult required")
    before = _source_snapshot(result)
    response = public_api.recover_public_rc_fiber_frame_response_history(
        result
    ).to_dict()
    if _source_snapshot(result) != before:
        raise ValueError("public response recovery mutated retained source")
    history = response["history"]
    chain = result._checkpoint_chain
    if (
        response["status"] != "ready"
        or response["contract_pass"] is not True
        or response["source_result_hash"] != result.result_hash
        or history["bindings"]["checkpoint_chain_hash"] != chain.chain_hash
        or len(history["steps"]) != len(chain.checkpoints) - 1
    ):
        raise ValueError("constitutive observation history/source binding mismatch")
    rows = []
    previous = None
    for index, checkpoint in enumerate(chain.checkpoints):
        points = _material_points(result._problem, checkpoint)
        engineering = None if index == 0 else history["steps"][index - 1]
        if engineering is not None and (
            engineering["epoch"] != checkpoint.epoch
            or engineering["step_index"] != checkpoint.step_index
            or engineering["target_load_factor"] != checkpoint.load_factor
            or engineering["bindings"]["checkpoint_state_hash"] != checkpoint.state_hash
            or engineering["bindings"]["parent_checkpoint_state_hash"]
            != checkpoint.parent_state_hash
        ):
            raise ValueError("constitutive observation epoch/recovery binding mismatch")
        total = (
            None
            if engineering is None
            else engineering["metrics"]["total_dissipated_energy_mj"]
        )
        if engineering is not None and (
            type(total) not in (int, float) or not math.isfinite(total) or total < 0.0
        ):
            raise ValueError("invalid source dissipated energy")
        rows.append(
            {
                "epoch": checkpoint.epoch,
                "step_index": checkpoint.step_index,
                "load_factor": checkpoint.load_factor,
                "checkpoint_state_hash": checkpoint.state_hash,
                "parent_checkpoint_state_hash": checkpoint.parent_state_hash,
                "engineering_recovery_hash": None
                if engineering is None
                else engineering["recovery_hash"],
                "total_dissipated_energy_mj": total,
                "engineering_recovery_reason": "genesis_has_no_engineering_recovery"
                if engineering is None
                else None,
                **_summarize_points(points, previous),
            }
        )
        previous = points
    if _source_snapshot(result) != before:
        raise ValueError("constitutive aggregation mutated retained source")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        "bindings": {
            "source_result_hash": result.result_hash,
            "canonical_model_checksum": result.canonical_model_checksum,
            "input_checksum": result.input_checksum,
            "problem_contract_hash": result._problem.contract_hash,
            "checkpoint_chain_hash": chain.chain_hash,
            "checkpoint_artifact_hash": result.checkpoint["artifact_hash"],
            "checkpoint_artifact_byte_length": len(before[2]),
            "response_history_report_hash": response["report_hash"],
            "engineering_history_hash": history["history_hash"],
        },
        "accepted_epoch_count": len(rows) - 1,
        "states": rows,
        "scope": {
            "validation": "existing_full_public_response_history_accessor_then_retained_material_memory_aggregation",
            "material_point": "member_integration_point_modeled_fiber_not_individual_bar",
            "state_value_counts": "strictly_positive_native_values_not_current_step_yield_events",
            "transition_counts": "exact_comparison_with_immediately_preceding_accepted_state",
            "total_energy": "original_per_epoch_engineering_recovery_MJ_not_density_or_epoch_sum",
        },
        "claim_boundary": dict(_CLAIMS),
    }
    payload["report_hash"] = canonical_hash(payload)
    return FiberFrameConstitutiveHistory(
        "ready",
        True,
        payload["report_hash"],
        json.dumps(payload, sort_keys=True, allow_nan=False),
    )


def validate_public_rc_fiber_frame_constitutive_history(
    report: FiberFrameConstitutiveHistory,
    result: public_api.PublicRCFiberFrameResult,
) -> FiberFrameConstitutiveHistory:
    """Explicitly rebuild from retained source and require exact report content.

    This incurs the existing full public-history accessor's validation cost once.
    It supplies no independent physical or cyclic-loading validation.
    """
    if type(report) is not FiberFrameConstitutiveHistory:
        raise ValueError("exact FiberFrameConstitutiveHistory required")
    if type(result) is not public_api.PublicRCFiberFrameResult:
        raise ValueError("exact PublicRCFiberFrameResult required")
    payload = report.to_dict()
    expected = inspect_public_rc_fiber_frame_constitutive_history(result)
    if _json_bytes(payload) != _json_bytes(expected.to_dict()):
        raise ValueError(
            "constitutive history does not match exact retained public source"
        )
    return report


__all__ = [
    "FiberFrameConstitutiveHistory",
    "inspect_public_rc_fiber_frame_constitutive_history",
    "validate_public_rc_fiber_frame_constitutive_history",
]
