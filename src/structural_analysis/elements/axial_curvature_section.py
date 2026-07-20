"""Structural protocol for stateful axial-force/curvature sections."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class AxialCurvatureSectionState(Protocol):
    """Immutable section state consumed by a beam integration point."""

    step_index: int
    axial_strain: float
    curvature_z_per_m: float

    @property
    def state_hash(self) -> str: ...

    def canonical_bytes(self) -> bytes: ...

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class AxialCurvatureSectionResponse(Protocol):
    """Conjugate ``[N, M]`` response with a consistent ``2 x 2`` tangent."""

    parent_state_hash: str
    consistent_tangent: np.ndarray
    yielded_steel_fiber_count: int
    damaged_concrete_fiber_count: int
    dissipated_energy_mj_per_m: float
    state: AxialCurvatureSectionState

    @property
    def resultants(self) -> np.ndarray: ...

    def to_dict(self) -> dict[str, Any]: ...


@runtime_checkable
class AxialCurvatureSection(Protocol):
    """Minimal stateful section contract required by the beam kernel."""

    @property
    def contract_hash(self) -> str: ...

    def initial_state(self) -> AxialCurvatureSectionState: ...

    def validate_state(self, state: AxialCurvatureSectionState) -> None: ...

    def integrate(
        self,
        generalized_strain: Any,
        committed_state: AxialCurvatureSectionState,
    ) -> AxialCurvatureSectionResponse: ...

    def dissipated_energy_mj_per_m(
        self,
        state: AxialCurvatureSectionState,
    ) -> float: ...


__all__ = [
    "AxialCurvatureSection",
    "AxialCurvatureSectionResponse",
    "AxialCurvatureSectionState",
]
