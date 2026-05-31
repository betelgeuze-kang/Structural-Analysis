#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

from kds_equivalent_static_cs import compute_equivalent_static_cs  # noqa: E402


def test_kds_cs_formula() -> None:
    payload = compute_equivalent_static_cs(height_m=9.0, params={"SDS": 0.30, "R": 5.0, "Ie": 1.0})
    assert abs(payload["cs"] - 0.06) < 1.0e-9
    assert payload["height_regime"] == "low_rise_gravity_dominant"


def test_kds_cs_derived_from_zone_and_fa() -> None:
    payload = compute_equivalent_static_cs(
        height_m=9.35,
        params={"zone_factor_Z": 0.11, "Fa": 1.4, "R": 3.0, "Ie": 1.0},
    )
    assert abs(payload["SDS"] - 0.385) < 1.0e-9
    assert abs(payload["cs"] - 0.385 / 3.0) < 1.0e-9
    assert payload["sds_derivation"]["sds_basis"] == "derived_2p5_Z_Fa"
