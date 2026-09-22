"""Explicit recovery profiles with a compatible legacy-Boolean adapter.

This configuration selects existing numerical proposals only. It grants no
solver acceptance, changes no budgets/tolerances, and adopts no trial state.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from structural_analysis.benchmark.rc_control_frozen_continuation import (
    ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
    FROZEN_CONTINUATION_FAILURE_IDENTITY,
    FROZEN_CONTINUATION_IDENTITY,
    FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY,
)
from structural_analysis.benchmark.rc_control_trust_region import TRUST_REGION_REVERSAL_IDENTITY

RecoveryMode = Literal[
    "none", "trust-region-reversal", "frozen-reversal",
    "frozen-failed-reversal", "frozen-failed-target", "adaptive-failed-target",
]
# Tuple order is the five legacy flags, not a new numerical protocol.
_PROFILES = {
    "none": (False, False, False, False, False),
    "trust-region-reversal": (True, False, False, False, False),
    "frozen-reversal": (False, True, False, False, False),
    "frozen-failed-reversal": (False, True, True, False, False),
    "frozen-failed-target": (False, True, True, True, False),
    "adaptive-failed-target": (False, True, True, True, True),
}
_IDENTITIES = {
    "none": None,
    "trust-region-reversal": TRUST_REGION_REVERSAL_IDENTITY,
    "frozen-reversal": FROZEN_CONTINUATION_IDENTITY,
    "frozen-failed-reversal": FROZEN_CONTINUATION_FAILURE_IDENTITY,
    "frozen-failed-target": FROZEN_CONTINUATION_TARGET_FAILURE_IDENTITY,
    "adaptive-failed-target": ADAPTIVE_FROZEN_CONTINUATION_IDENTITY,
}
_NAMES = (
    "trust_region_reversal", "frozen_parent_continuation",
    "continuation_on_failure", "continuation_all_failed_targets", "continuation_adaptive",
)


@dataclass(frozen=True)
class RCControlRecoveryStrategy:
    """One validated existing strategy; all returned mappings are detached."""

    mode: RecoveryMode = "none"

    def __post_init__(self) -> None:
        if type(self.mode) is not str or self.mode not in _PROFILES:
            raise ValueError("supported explicit RC recovery mode required")

    @property
    def identity(self) -> str | None:
        return _IDENTITIES[self.mode]

    def legacy_options(self) -> dict[str, bool]:
        return dict(zip(_NAMES, _PROFILES[self.mode], strict=True))

    @classmethod
    def from_identity(cls, identity: str) -> RCControlRecoveryStrategy:
        if type(identity) is str:
            for mode, candidate in _IDENTITIES.items():
                if candidate == identity:
                    return cls(mode)
        raise ValueError("known RC recovery identity required")


def resolve_rc_recovery_strategy(
    strategy: RCControlRecoveryStrategy | None = None, *,
    trust_region_reversal: bool = False,
    frozen_parent_continuation: bool = False,
    continuation_on_failure: bool = False,
    continuation_all_failed_targets: bool = False,
    continuation_adaptive: bool = False,
) -> RCControlRecoveryStrategy:
    """Preserve valid legacy combinations; reject ambiguous mixed selectors."""
    if type(trust_region_reversal) is not bool:
        raise ValueError("explicit boolean trust-region reversal option required")
    if type(frozen_parent_continuation) is not bool:
        raise ValueError("explicit boolean frozen-parent continuation option required")
    if type(continuation_on_failure) is not bool or (
        continuation_on_failure and not frozen_parent_continuation
    ):
        raise ValueError("failure-only continuation requires the explicit frozen-parent strategy")
    if type(continuation_all_failed_targets) is not bool or (
        continuation_all_failed_targets and not continuation_on_failure
    ):
        raise ValueError("all-target continuation requires the explicit failure-only strategy")
    if type(continuation_adaptive) is not bool or (
        continuation_adaptive and not continuation_all_failed_targets
    ):
        raise ValueError("adaptive continuation requires explicit all-target failure recovery")
    if trust_region_reversal and frozen_parent_continuation:
        raise ValueError("one numerical reversal strategy required")
    flags = (
        trust_region_reversal, frozen_parent_continuation, continuation_on_failure,
        continuation_all_failed_targets, continuation_adaptive,
    )
    if strategy is not None:
        if type(strategy) is not RCControlRecoveryStrategy:
            raise ValueError("exact RCControlRecoveryStrategy required")
        if any(flags):
            raise ValueError("explicit strategy and legacy recovery flags must not be mixed")
        return strategy
    for mode, candidate in _PROFILES.items():
        if flags == candidate:
            return RCControlRecoveryStrategy(mode)
    raise ValueError("unsupported legacy recovery configuration")
