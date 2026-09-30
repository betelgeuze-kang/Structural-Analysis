"""Exact recovery over every positive committed epoch of one bounded path.

The complete J1--J5 adapter is validated before any epoch is selected. Each
epoch then independently replays its constitutive and engineering transition
from the original Newton coordinates and its exact accepted parent. Extrema
cover the discrete committed states of the validated monotonic static path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
from types import MappingProxyType
from typing import Any

import numpy as np

from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_recovery import (
    FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES,
    FiberFrameNonlinearRecoveryError,
    _replay_epoch_engineering_outputs,
)
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_result_adapter import (
    FiberFrameNonlinearNumericalResultAdapter,
    validate_fiber_frame_nonlinear_numerical_result_adapter,
)
from structural_analysis.engine_v2.contracts._canonical import canonical_hash


FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-nonlinear-engineering-history.v1"
)
FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCOPE = MappingProxyType(
    {
        "committed_epochs_only": True,
        "genesis_included": False,
        "genesis_exclusion_reason": "zero_unforced_initial_state_has_no_accepted_transition",
        "complete_monotonic_static_load_path": True,
        "between_step_extrema_verified": False,
        "cyclic_or_dynamic_history_verified": False,
        "constitutive_law_independently_verified": False,
        "engineering_design_verified": False,
        "code_compliance_verified": False,
        "production_promotion_eligible": False,
    }
)


@dataclass(frozen=True)
class FiberFrameNonlinearEngineeringHistory:
    """Immutable, hash-bound recovery observations with detached JSON exports."""

    history_hash: str
    _payload_json: str = field(repr=False)

    def to_dict(self) -> dict[str, Any]:
        payload = json.loads(self._payload_json)
        if (
            payload.get("history_hash") != self.history_hash
            or canonical_hash(
                {key: value for key, value in payload.items() if key != "history_hash"}
            )
            != self.history_hash
        ):
            raise FiberFrameNonlinearRecoveryError(
                "fiber_frame_history_hash_mismatch",
                "/history_hash",
                "History bytes do not match the retained history hash.",
            )
        return payload


def create_fiber_frame_nonlinear_engineering_history(
    source_adapter: FiberFrameNonlinearNumericalResultAdapter,
) -> FiberFrameNonlinearEngineeringHistory:
    """Validate one complete source, then recover all its committed epochs.

    The adapter validation retains the existing full Newton replay boundary.
    Epoch recovery performs constitutive/assembly replay only; it does not
    repeat the complete Newton path for each epoch.
    """
    adapter = validate_fiber_frame_nonlinear_numerical_result_adapter(source_adapter)
    source = adapter.source_binding
    steps = [
        _recover_step(adapter, epoch) for epoch in range(1, source.terminal_epoch + 1)
    ]
    translation = max(steps, key=lambda row: row["envelope"]["maximum_translation_m"])
    fiber = max(steps, key=lambda row: row["envelope"]["maximum_absolute_fiber_strain"])
    payload = {
        "schema_version": FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCHEMA_VERSION,
        "status": "ready",
        "contract_pass": True,
        "bindings": {
            "source_result_adapter_hash": adapter.adapter_hash,
            "source_binding_hash": source.binding_hash,
            "source_numerical_result_hash": adapter.numerical_result.result_hash,
            "problem_contract_hash": source.problem_contract_hash,
            "model_ir_content_hash": source.model_ir_content_hash,
            "execution_topology_plan_hash": source.execution_topology_plan_hash,
            "physical_equation_scaling_binding_hash": source.physical_equation_scaling_binding_hash,
            "execution_state_binding_hash": source.execution_state_binding_hash,
            "checkpoint_chain_hash": source.checkpoint_chain_hash,
            "root_checkpoint_state_hash": source._checkpoint_chain.root_checkpoint.state_hash,
            "terminal_checkpoint_state_hash": source.terminal_checkpoint_state_hash,
            "kinematic_state_chain_hash": source.kinematic_state_chain_hash,
            "material_state_projection_chain_hash": source.material_state_projection_chain_hash,
            "terminal_receipt_hash": source.terminal_receipt_hash,
            "path_history_hash": source.path_history_hash,
        },
        "source_terminal_receipt": source._terminal_receipt.to_manifest(),
        "scope": dict(FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCOPE),
        "authority": dict(FIBER_FRAME_NONLINEAR_ENGINEERING_AUTHORITY_AXES),
        "epoch_count": len(steps),
        "terminal_epoch": source.terminal_epoch,
        "terminal_load_factor": source.terminal_load_factor,
        "steps": steps,
        "envelope": {
            "maximum_translation_m": translation["envelope"]["maximum_translation_m"],
            "maximum_absolute_fiber_strain": fiber["envelope"][
                "maximum_absolute_fiber_strain"
            ],
            "governing_translation": translation["envelope"]["governing_translation"],
            "governing_fiber_strain": fiber["envelope"]["governing_fiber_strain"],
        },
    }
    payload["history_hash"] = canonical_hash(payload)
    return FiberFrameNonlinearEngineeringHistory(
        payload["history_hash"], json.dumps(payload, sort_keys=True, allow_nan=False)
    )


def _recover_step(
    adapter: FiberFrameNonlinearNumericalResultAdapter, epoch: int
) -> dict[str, Any]:
    replay = _replay_epoch_engineering_outputs(adapter, epoch)
    source = adapter.source_binding
    checkpoint = source._checkpoint_chain.checkpoints[epoch]
    kinematic = source._kinematic_chain.committed_states[epoch]
    projection = source._material_chain.projections[epoch]
    epoch_binding = source._execution_state_binding.epoch_bindings[epoch]
    receipt = source._terminal_receipt.step_receipts[epoch - 1]
    displacement = kinematic.array("canonical_displacement_si")
    node_rows = [
        {
            "node_id": node_id,
            **dict(
                zip(
                    ("UX_m", "UY_m", "UZ_m", "RX_rad", "RY_rad", "RZ_rad"),
                    map(float, values),
                    strict=True,
                )
            ),
        }
        for node_id, values in zip(
            source._topology_plan.node_ids,
            np.asarray(displacement).reshape((-1, 6)),
            strict=True,
        )
    ]
    arrays = replay.arrays
    fiber_rows = [
        {
            "member_id": label["member_id"],
            "integration_point_index": label["integration_point_index"],
            "fiber_index": label["fiber_index"],
            "fiber_id": label["fiber_id"],
            "material_kind": label["material_kind"],
            "y_m": float(arrays["fiber_y_m"][index]),
            "area_m2": float(arrays["fiber_area_m2"][index]),
            "strain": float(arrays["fiber_strain"][index]),
            "stress_MPa": float(arrays["fiber_stress_mpa"][index]),
            "dissipated_energy_density_MJ_per_m3": float(
                arrays["fiber_dissipated_energy_density_mj_per_m3"][index]
            ),
        }
        for index, label in enumerate(replay.fiber_labels)
    ]
    row = {
        "epoch": epoch,
        "step_index": checkpoint.step_index,
        "target_load_factor": checkpoint.load_factor,
        "bindings": {
            "checkpoint_state_hash": checkpoint.state_hash,
            "parent_checkpoint_state_hash": checkpoint.parent_state_hash,
            "kinematic_state_hash": kinematic.state_hash,
            "material_projection_receipt_hash": projection.receipt.receipt_hash,
            "material_state_bundle_hash": projection.bundle.bundle_hash,
            "execution_epoch_binding_hash": epoch_binding.epoch_binding_hash,
            "step_receipt_hash": receipt.step_receipt_hash,
            "source_solution_data_hash": receipt.source_solution_data_hash,
        },
        "array_bundle_hash": replay.array_bundle_hash,
        "orders": dict(replay.orders),
        "metrics": dict(replay.metrics),
        "recovery_arrays": {name: values.tolist() for name, values in arrays.items()},
        "recovery_array_descriptors": [
            descriptor.to_dict() for descriptor in replay.descriptors
        ],
        "displacement_canonical_si": displacement.tolist(),
        "displacement_array_descriptor": next(
            descriptor.to_dict()
            for descriptor in kinematic.descriptors
            if descriptor.name == "canonical_displacement_si"
        ),
        "node_displacements": node_rows,
        "fiber_results": fiber_rows,
        "envelope": _envelope(epoch, node_rows, fiber_rows),
    }
    row["recovery_hash"] = canonical_hash(row)
    return row


def _envelope(
    epoch: int, nodes: list[dict[str, Any]], fibers: list[dict[str, Any]]
) -> dict[str, Any]:
    def translation(row: dict[str, Any]) -> float:
        return math.hypot(row["UX_m"], row["UY_m"], row["UZ_m"])

    node = max(nodes, key=translation)
    fiber = max(fibers, key=lambda row: abs(row["strain"]))
    return {
        "maximum_translation_m": translation(node),
        "maximum_absolute_fiber_strain": abs(fiber["strain"]),
        "governing_translation": {
            "epoch": epoch,
            **node,
            "translation_m": translation(node),
        },
        "governing_fiber_strain": {
            "epoch": epoch,
            **fiber,
            "absolute_strain": abs(fiber["strain"]),
        },
    }


__all__ = [
    "FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCHEMA_VERSION",
    "FIBER_FRAME_NONLINEAR_ENGINEERING_HISTORY_SCOPE",
    "FiberFrameNonlinearEngineeringHistory",
    "create_fiber_frame_nonlinear_engineering_history",
]
