"""Storey-band taxonomy for Korean medium/large building source targeting."""

from __future__ import annotations

from typing import Any

MEDIUM_STOREY_BANDS = frozenset({"mid_rise", "10_20", "20_30"})
LARGE_STOREY_BANDS = frozenset({"high_rise", "30_plus", "super_tall"})


def building_scale_band(storey_band: str) -> str:
    band = str(storey_band or "").strip()
    if band in MEDIUM_STOREY_BANDS:
        return "medium"
    if band in LARGE_STOREY_BANDS:
        return "large"
    if band == "low_rise":
        return "small"
    return "other"


def is_medium_or_large(record: dict[str, Any]) -> bool:
    band = str(record.get("storey_band") or "").strip()
    return building_scale_band(band) in {"medium", "large"}
