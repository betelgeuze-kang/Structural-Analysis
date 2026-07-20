"""Committed checkpoint bundle for a bounded stateful 2D fiber frame."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct
from typing import Any, Literal

from structural_analysis.elements.stateful_fiber_beam2d_state import (
    StatefulFiberBeam2DState,
)


STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION = (
    "stateful-fiber-frame2d-checkpoint.v1"
)
_CHECKPOINT_HASH_DOMAIN = b"structural-analysis/stateful-fiber-frame2d-checkpoint/v1\0"


def _pack_text(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _sha256_hash(value: Any, *, name: str) -> str:
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


@dataclass(frozen=True)
class StatefulFiberFrame2DCheckpoint:
    """One immutable committed frame state with explicit ancestry and epoch."""

    case_id: str
    problem_contract_hash: str
    epoch: int
    step_index: int
    load_factor: float
    parent_state_hash: str | None
    global_displacements: tuple[float, ...]
    element_states: tuple[StatefulFiberBeam2DState, ...]
    role: Literal["committed"] = "committed"
    state_hash: str = ""

    def __post_init__(self) -> None:
        normalized_case_id = str(self.case_id).strip()
        if not normalized_case_id:
            raise ValueError("case_id must be non-empty")
        object.__setattr__(self, "case_id", normalized_case_id)
        object.__setattr__(
            self,
            "problem_contract_hash",
            _sha256_hash(
                self.problem_contract_hash,
                name="problem_contract_hash",
            ),
        )
        if self.role != "committed":
            raise ValueError("checkpoint role must be committed")
        if type(self.epoch) is not int or self.epoch < 0:
            raise ValueError("epoch must be a non-negative integer")
        if type(self.step_index) is not int or self.step_index < 0:
            raise ValueError("step_index must be a non-negative integer")
        if self.step_index != self.epoch:
            raise ValueError("step_index must equal epoch for this bounded path")
        if not math.isfinite(float(self.load_factor)):
            raise ValueError("load_factor must be finite")
        object.__setattr__(self, "load_factor", float(self.load_factor))
        if self.epoch == 0:
            if self.parent_state_hash is not None:
                raise ValueError("epoch-zero checkpoint must be unparented")
        elif self.parent_state_hash is None:
            raise ValueError("positive-epoch checkpoint must have a parent hash")
        else:
            object.__setattr__(
                self,
                "parent_state_hash",
                _sha256_hash(
                    self.parent_state_hash,
                    name="parent_state_hash",
                ),
            )
        if (
            not isinstance(self.global_displacements, tuple)
            or not self.global_displacements
            or len(self.global_displacements) % 3 != 0
        ):
            raise ValueError(
                "global_displacements must be a non-empty 3-DOF-node tuple"
            )
        normalized_displacements = tuple(
            float(value) for value in self.global_displacements
        )
        if not all(math.isfinite(value) for value in normalized_displacements):
            raise ValueError("global_displacements must be finite")
        object.__setattr__(
            self,
            "global_displacements",
            normalized_displacements,
        )
        if (
            not isinstance(self.element_states, tuple)
            or not self.element_states
            or not all(
                type(state) is StatefulFiberBeam2DState for state in self.element_states
            )
        ):
            raise ValueError(
                "element_states must be a non-empty tuple of "
                "StatefulFiberBeam2DState values"
            )
        computed = self.compute_state_hash()
        if self.state_hash and self.state_hash != computed:
            raise ValueError("checkpoint state_hash does not match canonical bytes")
        if not self.state_hash:
            object.__setattr__(self, "state_hash", computed)
        elif self.parent_state_hash == self.state_hash:
            raise ValueError("checkpoint cannot be its own parent")

    def canonical_bytes(self) -> bytes:
        parent = "" if self.parent_state_hash is None else self.parent_state_hash
        chunks = [
            _CHECKPOINT_HASH_DOMAIN,
            _pack_text(self.role),
            _pack_text(self.case_id),
            _pack_text(self.problem_contract_hash),
            struct.pack(
                "<QQd",
                self.epoch,
                self.step_index,
                self.load_factor,
            ),
            _pack_text(parent),
            struct.pack("<Q", len(self.global_displacements)),
            struct.pack(
                f"<{len(self.global_displacements)}d",
                *self.global_displacements,
            ),
            struct.pack("<Q", len(self.element_states)),
        ]
        for state in self.element_states:
            encoded = state.canonical_bytes()
            chunks.extend((struct.pack("<Q", len(encoded)), encoded))
        return b"".join(chunks)

    def compute_state_hash(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION,
            "role": self.role,
            "case_id": self.case_id,
            "problem_contract_hash": self.problem_contract_hash,
            "epoch": self.epoch,
            "step_index": self.step_index,
            "load_factor": self.load_factor,
            "parent_state_hash": self.parent_state_hash,
            "global_displacements": list(self.global_displacements),
            "element_states": [state.to_dict() for state in self.element_states],
            "state_hash": self.state_hash,
        }


__all__ = [
    "STATEFUL_FIBER_FRAME2D_CHECKPOINT_SCHEMA_VERSION",
    "StatefulFiberFrame2DCheckpoint",
]
