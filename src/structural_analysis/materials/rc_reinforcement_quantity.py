"""Authored longitudinal steel area, after public section validation."""

from collections.abc import Mapping
import math
from typing import Any


def longitudinal_rebar_area_m2(section: Mapping[str, Any]) -> float:
    """Keep legacy arithmetic exact when all authored bars share one area."""
    common = section["bar_area_m2"]
    top = section.get("top_bar_area_m2", common)
    bottom = section.get("bottom_bar_area_m2", common)
    intermediate_count = sum(
        layer["bar_count"] for layer in section.get("intermediate_steel_layers", [])
    )
    if top == common and bottom == common:
        count = section["top_bar_count"] + section["bottom_bar_count"] + intermediate_count
        return count * common
    return math.fsum((
        section["top_bar_count"] * top,
        section["bottom_bar_count"] * bottom,
        intermediate_count * common,
    ))
