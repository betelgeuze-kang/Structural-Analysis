"""Immutable state and canonical serialization for a stateful fiber beam."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import struct
from typing import Any

import numpy as np

from structural_analysis.elements.axial_curvature_section import (
    AxialCurvatureSectionState,
)
from structural_analysis.elements.stateful_fiber_beam2d_contract import (
    STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
)


_STATE_HASH_DOMAIN = b"structural-analysis/stateful-fiber-beam2d-state/v1\0"


def _sha256_contract_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    prefix = "sha256:"
    digest = normalized.removeprefix(prefix)
    if (
        not normalized.startswith(prefix)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _local_displacement_tuple(values: Any) -> tuple[float, ...]:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("local_displacements must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError("local_displacements must be a finite six-vector")
    return tuple(float(value) for value in vector)


@dataclass(frozen=True)
class StatefulFiberBeam2DState:
    element_id: str
    element_contract_hash: str
    step_index: int
    local_displacements: tuple[float, ...]
    integration_point_states: tuple[AxialCurvatureSectionState, ...]

    def __post_init__(self) -> None:
        normalized_id = str(self.element_id).strip()
        if not normalized_id:
            raise ValueError("element_id must be non-empty")
        object.__setattr__(self, "element_id", normalized_id)
        object.__setattr__(
            self,
            "element_contract_hash",
            _sha256_contract_hash(
                self.element_contract_hash,
                name="element_contract_hash",
            ),
        )
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        object.__setattr__(
            self,
            "local_displacements",
            _local_displacement_tuple(self.local_displacements),
        )
        if (
            not isinstance(self.integration_point_states, tuple)
            or not self.integration_point_states
            or not all(
                isinstance(state, AxialCurvatureSectionState)
                for state in self.integration_point_states
            )
        ):
            raise ValueError(
                "integration_point_states must satisfy AxialCurvatureSectionState"
            )

    def canonical_bytes(self) -> bytes:
        element_id = self.element_id.encode("utf-8")
        contract_hash = self.element_contract_hash.encode("ascii")
        chunks = [
            _STATE_HASH_DOMAIN,
            struct.pack("<Q", len(element_id)),
            element_id,
            struct.pack("<Q", len(contract_hash)),
            contract_hash,
            struct.pack(
                "<Q6dQ",
                self.step_index,
                *self.local_displacements,
                len(self.integration_point_states),
            ),
        ]
        for state in self.integration_point_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
            "element_id": self.element_id,
            "element_contract_hash": self.element_contract_hash,
            "step_index": self.step_index,
            "local_displacements": list(self.local_displacements),
            "integration_point_states": [
                state.to_dict() for state in self.integration_point_states
            ],
            "state_hash": self.state_hash,
        }


__all__ = ["StatefulFiberBeam2DState"]
