"""Typed opt-in recovery entry point over the unchanged historical runtime.

Keep the large runtime and its legacy import/signature behavior unchanged.
Only normalize explicit recovery configuration before delegating to it.
"""
from __future__ import annotations

from structural_analysis.benchmark.rc_control_recovery_strategy import (
    RCControlRecoveryStrategy, resolve_rc_recovery_strategy,
)
from structural_analysis.benchmark import rc_control_seed_runtime as runtime

_NAMES = (
    'trust_region_reversal', 'frozen_parent_continuation', 'continuation_on_failure',
    'continuation_all_failed_targets', 'continuation_adaptive',
)


def benchmark_rc_control_seed_paths(
    model, request, *, recovery_strategy: RCControlRecoveryStrategy | None = None, **options,
):
    """Legacy flags or one typed profile, never ambiguous active selectors."""
    flags = {name: options.pop(name, False) for name in _NAMES}
    strategy = resolve_rc_recovery_strategy(recovery_strategy, **flags)
    return runtime.benchmark_rc_control_seed_paths(
        model, request, **strategy.legacy_options(), **options,
    )
