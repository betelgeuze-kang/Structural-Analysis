"""Experimental prescribed-history admission; no numerical acceptance authority."""

import math

from structural_analysis.benchmark.rc_control_seed_runtime import RCControlSeedContext

ENVELOPE_ADMISSION_PROFILE = "strict-new-absolute-control-envelope.v1"


def control_envelope_admission(context):
    """Use only the current arm's past prescribed targets and next known target.

    A true result permits consulting an existing seed policy, whose model/range
    guards still apply. False means abstain through the caller's normal fallback.
    This manual rule has no independently validated runtime or physical benefit.
    Material capture performed before this callback remains an incurred cost.
    """
    if type(context) is not RCControlSeedContext:
        raise ValueError("exact control seed context required")
    past = context.accepted_targets_m
    if type(past) is not tuple or not 1 <= len(past) <= 4097:
        raise ValueError("bounded nonempty accepted target prefix required")
    try:
        finite = all(
            type(value) in (int, float) and math.isfinite(value)
            for value in (*past, context.target_m)
        )
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("finite numeric control targets required")
    previous_maximum = max(abs(value) for value in past)
    return {
        "profile": ENVELOPE_ADMISSION_PROFILE,
        "accepted_prefix_count": len(past),
        "target_m": context.target_m,
        "previous_maximum_absolute_target_m": previous_maximum,
        "consult_policy": abs(context.target_m) > previous_maximum,
        "physical_acceptance_authorized": False,
        "prospective_policy_validated": False,
    }
