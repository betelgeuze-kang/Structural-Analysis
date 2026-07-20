"""Immutable state for one stateful corotational 2D fiber beam."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any

import numpy as np

from structural_analysis.elements.stateful_corotational_fiber_beam2d_contract import (
    STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
)
from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)


_STATE_HASH_DOMAIN = (
    b"structural-analysis/stateful-corotational-fiber-beam2d-state/v1\0"
)


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _sha256_contract_hash(value: Any, *, name: str) -> str:
    normalized = str(value).strip()
    digest = normalized.removeprefix("sha256:")
    if (
        not normalized.startswith("sha256:")
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError(f"{name} must be a lowercase sha256 digest")
    return normalized


def _displacement_tuple(values: Any) -> tuple[float, ...]:
    try:
        vector = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("element_displacements must be a finite six-vector") from exc
    if vector.shape != (6,) or not np.all(np.isfinite(vector)):
        raise ValueError("element_displacements must be a finite six-vector")
    return tuple(float(value) for value in vector)


@dataclass(frozen=True)
class StatefulCorotationalFiberBeam2DState:
    """Committed element kinematics plus every integration-point state."""

    element_id: str
    element_contract_hash: str
    step_index: int
    element_displacements: tuple[float, ...]
    chord_rotation_change_rad: float
    basic_beam_state: StatefulFiberBeam2DState

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
            "element_displacements",
            _displacement_tuple(self.element_displacements),
        )
        try:
            chord_rotation = float(self.chord_rotation_change_rad)
        except (TypeError, ValueError) as exc:
            raise ValueError("chord_rotation_change_rad must be finite") from exc
        if isinstance(
            self.chord_rotation_change_rad, (bool, np.bool_)
        ) or not math.isfinite(chord_rotation):
            raise ValueError("chord_rotation_change_rad must be finite")
        object.__setattr__(
            self,
            "chord_rotation_change_rad",
            chord_rotation,
        )
        if type(self.basic_beam_state) is not StatefulFiberBeam2DState:
            raise ValueError("basic_beam_state must be StatefulFiberBeam2DState")
        if self.basic_beam_state.step_index != self.step_index:
            raise ValueError("basic beam and corotational step indices must match")

    def canonical_bytes(self) -> bytes:
        basic_state = self.basic_beam_state.canonical_bytes()
        return b"".join(
            (
                _STATE_HASH_DOMAIN,
                _pack_text(self.element_id),
                _pack_text(self.element_contract_hash),
                struct.pack(
                    "<Q7dQ",
                    self.step_index,
                    *self.element_displacements,
                    self.chord_rotation_change_rad,
                    len(basic_state),
                ),
                basic_state,
            )
        )

    @property
    def state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_COROTATIONAL_FIBER_BEAM2D_STATE_SCHEMA_VERSION,
            "element_id": self.element_id,
            "element_contract_hash": self.element_contract_hash,
            "step_index": self.step_index,
            "element_displacements": list(self.element_displacements),
            "chord_rotation_change_rad": self.chord_rotation_change_rad,
            "basic_beam_state": self.basic_beam_state.to_dict(),
            "state_hash": self.state_hash,
        }


__all__ = ["StatefulCorotationalFiberBeam2DState"]
