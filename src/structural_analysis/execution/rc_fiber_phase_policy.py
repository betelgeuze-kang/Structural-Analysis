"""Authored bounds for optional isolated RC analysis and verification phases.

This portable input contract grants no operating-system or solver authority. The
worker checks platform support before reserving or launching isolated work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RC_FIBER_PHASE_POLICY_SCHEMA_VERSION = "bounded-rc-fiber-phase-execution-policy.v1"
_POLICY_KEYS = {
    "schema_version",
    "analysis_timeout_ms",
    "verification_timeout_ms",
    "termination_grace_ms",
}


@dataclass(frozen=True, slots=True)
class RCFiberPhasePolicy:
    analysis_timeout_ms: int
    verification_timeout_ms: int
    termination_grace_ms: int

    def __post_init__(self) -> None:
        for value, maximum in (
            (self.analysis_timeout_ms, 3_600_000),
            (self.verification_timeout_ms, 3_600_000),
            (self.termination_grace_ms, 5_000),
        ):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("invalid RC fiber phase execution policy")

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
            "schema_version": RC_FIBER_PHASE_POLICY_SCHEMA_VERSION,
            "analysis_timeout_ms": self.analysis_timeout_ms,
            "verification_timeout_ms": self.verification_timeout_ms,
            "termination_grace_ms": self.termination_grace_ms,
        }


def decode_rc_fiber_phase_policy(value: Any) -> RCFiberPhasePolicy:
    if (
        type(value) is not dict
        or set(value) != _POLICY_KEYS
        or type(value["schema_version"]) is not str
        or value["schema_version"] != RC_FIBER_PHASE_POLICY_SCHEMA_VERSION
    ):
        raise ValueError("invalid RC fiber phase execution policy")
    return RCFiberPhasePolicy(
        analysis_timeout_ms=value["analysis_timeout_ms"],
        verification_timeout_ms=value["verification_timeout_ms"],
        termination_grace_ms=value["termination_grace_ms"],
    )
