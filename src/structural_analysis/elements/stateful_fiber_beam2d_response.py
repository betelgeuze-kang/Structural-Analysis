"""Element response container for the stateful 2D fiber beam."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from structural_analysis.elements.axial_curvature_section import (
    AxialCurvatureSectionResponse,
)
from structural_analysis.elements.stateful_fiber_beam2d_contract import (
    STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
    STATEFUL_FIBER_BEAM2D_KINEMATICS,
    STATEFUL_FIBER_BEAM2D_TANGENT,
)
from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)


@dataclass(frozen=True)
class StatefulFiberBeam2DResponse:
    parent_state_hash: str
    local_displacements: np.ndarray
    internal_force_local: np.ndarray
    consistent_tangent_local: np.ndarray
    integration_point_xi: np.ndarray
    integration_point_weights: np.ndarray
    generalized_strains: np.ndarray
    section_responses: tuple[AxialCurvatureSectionResponse, ...]
    yielded_integration_point_count: int
    damaged_integration_point_count: int
    dissipated_energy_mj: float
    state: StatefulFiberBeam2DState

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "parent_state_hash": self.parent_state_hash,
            "local_displacements": self.local_displacements.tolist(),
            "internal_force_local": self.internal_force_local.tolist(),
            "generalized_strains": self.generalized_strains.tolist(),
            "integration_point_state_hashes": [
                response.state.state_hash for response in self.section_responses
            ],
            "yielded_integration_point_count": (self.yielded_integration_point_count),
            "damaged_integration_point_count": (self.damaged_integration_point_count),
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "trial_state_hash": self.state.state_hash,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_state_hash": self.parent_state_hash,
            "local_displacements": self.local_displacements.tolist(),
            "internal_force_local": self.internal_force_local.tolist(),
            "consistent_tangent_local": self.consistent_tangent_local.tolist(),
            "integration_point_xi": self.integration_point_xi.tolist(),
            "integration_point_weights": self.integration_point_weights.tolist(),
            "generalized_strains": self.generalized_strains.tolist(),
            "section_responses": [
                response.to_dict() for response in self.section_responses
            ],
            "yielded_integration_point_count": (self.yielded_integration_point_count),
            "damaged_integration_point_count": (self.damaged_integration_point_count),
            "dissipated_energy_mj": self.dissipated_energy_mj,
            "kinematics": STATEFUL_FIBER_BEAM2D_KINEMATICS,
            "internal_force_definition": STATEFUL_FIBER_BEAM2D_INTERNAL_FORCE,
            "tangent_definition": STATEFUL_FIBER_BEAM2D_TANGENT,
            "trial_state": self.state.to_dict(),
        }


__all__ = ["StatefulFiberBeam2DResponse"]
