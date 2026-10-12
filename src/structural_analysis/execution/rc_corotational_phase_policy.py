"""Strict authored deadlines for isolated corotational RC numerical phases.

This portable input contract provides no process isolation, resource quota or
solver authority. The worker must establish platform and child-reaping support
before reserving or launching work under this policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from structural_analysis.api.strict_json import strict_json_object_bytes


RC_COROTATIONAL_PHASE_POLICY_SCHEMA_VERSION = (
    "bounded-rc-corotational-phase-execution-policy.v1"
)
RC_COROTATIONAL_PHASE_POLICY_MAX_BYTES = 4096
RC_COROTATIONAL_PHASE_TIMEOUT_MAX_MS = 3_600_000
RC_COROTATIONAL_PHASE_TERMINATION_GRACE_MAX_MS = 5_000
_POLICY_KEYS = {
    "schema_version",
    "analysis_timeout_ms",
    "verification_timeout_ms",
    "termination_grace_ms",
}


@dataclass(frozen=True, slots=True)
class RCCorotationalPhasePolicy:
    analysis_timeout_ms: int
    verification_timeout_ms: int
    termination_grace_ms: int

    def __post_init__(self) -> None:
        for value, maximum in (
            (self.analysis_timeout_ms, RC_COROTATIONAL_PHASE_TIMEOUT_MAX_MS),
            (self.verification_timeout_ms, RC_COROTATIONAL_PHASE_TIMEOUT_MAX_MS),
            (
                self.termination_grace_ms,
                RC_COROTATIONAL_PHASE_TERMINATION_GRACE_MAX_MS,
            ),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid corotational phase execution policy")

    @property
    def analysis_timeout_seconds(self) -> float:
        return self.analysis_timeout_ms / 1_000

    @property
    def verification_timeout_seconds(self) -> float:
        return self.verification_timeout_ms / 1_000

    @property
    def termination_grace_seconds(self) -> float:
        return self.termination_grace_ms / 1_000

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema_version": RC_COROTATIONAL_PHASE_POLICY_SCHEMA_VERSION,
            "analysis_timeout_ms": self.analysis_timeout_ms,
            "verification_timeout_ms": self.verification_timeout_ms,
            "termination_grace_ms": self.termination_grace_ms,
        }


def decode_rc_corotational_phase_policy(value: Any) -> RCCorotationalPhasePolicy:
    """Decode exact fields and integer bounds, without executing a phase."""
    payload = (
        strict_json_object_bytes(
            value, maximum_bytes=RC_COROTATIONAL_PHASE_POLICY_MAX_BYTES
        )
        if type(value) is bytes
        else value
    )
    if (
        type(payload) is not dict
        or any(type(key) is not str for key in payload)
        or set(payload) != _POLICY_KEYS
        or type(payload["schema_version"]) is not str
        or payload["schema_version"] != RC_COROTATIONAL_PHASE_POLICY_SCHEMA_VERSION
    ):
        raise ValueError("invalid corotational phase execution policy")
    return RCCorotationalPhasePolicy(
        analysis_timeout_ms=payload["analysis_timeout_ms"],
        verification_timeout_ms=payload["verification_timeout_ms"],
        termination_grace_ms=payload["termination_grace_ms"],
    )
