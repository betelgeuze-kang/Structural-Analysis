"""Gross member quantities and caller-declared prices; never a numerical solve."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
import math
import re
from typing import Any
from structural_analysis.api import nonlinear_fiber_frame as public_api
from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.rc_reinforcement_quantity import (
    longitudinal_rebar_area_m2,
)
from structural_analysis.model.schema import CanonicalModel

QUANTITY_SCOPE = "gross_concrete_and_straight_authored_longitudinal_rebar.v1"


_EXCLUDED_COST_ITEMS = (
    "transverse_reinforcement",
    "laps_anchorage_hooks",
    "waste",
    "formwork",
    "labor",
    "fabrication",
    "transport",
    "tax",
)


class FiberFrameDesignError(ValueError):
    """Invalid bounded design experiment inputs."""


@dataclass(frozen=True)
class FiberFrameMaterialPrices:
    concrete_per_m3: float
    rebar_per_kg: float
    currency: str
    as_of: str
    source: str

    def __post_init__(self) -> None:
        for name in ("concrete_per_m3", "rebar_per_kg"):
            object.__setattr__(
                self, name, _number(getattr(self, name), name, zero=True)
            )
        if not isinstance(self.currency, str) or not re.fullmatch(
            r"[A-Z]{3}", self.currency
        ):
            raise FiberFrameDesignError(
                "currency must be a three-letter uppercase code"
            )
        if not isinstance(self.as_of, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", self.as_of
        ):
            raise FiberFrameDesignError("as_of must be YYYY-MM-DD")
        try:
            date.fromisoformat(self.as_of)
        except ValueError as exc:
            raise FiberFrameDesignError("as_of must be a valid date") from exc
        if (
            not isinstance(self.source, str)
            or not self.source.strip()
            or len(self.source) > 1000
        ):
            raise FiberFrameDesignError("price source must be nonempty and bounded")

    @property
    def price_table_hash(self) -> str:
        return canonical_hash(
            {"schema_version": "declared-rc-material-prices.v1", **asdict(self)}
        )


def calculate_fiber_frame_member_quantities(
    model: CanonicalModel,
    *,
    rebar_density_kg_per_m3: float = 7850.0,
    experimental_pin_roller_beam: bool = False,
) -> dict[str, Any]:
    """Calculate explicit geometry quantities once per member, never per Gauss point."""
    if type(model) is not CanonicalModel:
        raise FiberFrameDesignError("model must be a CanonicalModel")
    density = _number(rebar_density_kg_per_m3, "rebar_density_kg_per_m3")
    snapshot = model.detached_analysis_snapshot()
    compiled, unsupported, _ = public_api._compile(
        snapshot, experimental_pin_roller_beam=experimental_pin_roller_beam
    )
    if compiled is None:
        raise FiberFrameDesignError(
            f"unsupported quantity model: {unsupported[0]['kind']}"
        )
    nodes = {node["id"]: node["coordinates"] for node in snapshot.nodes}
    sections = {section["id"]: section for section in snapshot.sections}
    members = []
    for member in snapshot.elements:
        section = sections[member["section"]]
        length = math.dist(nodes[member["nodes"][0]], nodes[member["nodes"][1]])
        gross_area = section["width_m"] * section["depth_m"]
        bar_area = longitudinal_rebar_area_m2(section)
        row = {
            "member_id": member["id"],
            "section_id": member["section"],
            "length_m": length,
            "gross_concrete_volume_m3": gross_area * length,
            "longitudinal_rebar_volume_m3": bar_area * length,
            "longitudinal_rebar_mass_kg": bar_area * length * density,
        }
        _finite_tree(row)
        members.append(row)
    payload = {
        "schema_version": "public-rc-fiber-member-quantities.v1",
        "model_checksum": snapshot.canonical_model_checksum,
        "scope": QUANTITY_SCOPE,
        "rebar_density_kg_per_m3": density,
        "concrete_basis": "gross_section_volume_without_rebar_displacement_deduction",
        "reinforcement_basis": "authored_longitudinal_bars_times_member_length",
        "detailed_takeoff": False,
        "excluded_items": list(_EXCLUDED_COST_ITEMS),
        "members": members,
        "totals": {
            name: math.fsum(row[name] for row in members)
            for name in (
                "gross_concrete_volume_m3",
                "longitudinal_rebar_volume_m3",
                "longitudinal_rebar_mass_kg",
            )
        },
    }
    _finite_tree(payload)
    return {**payload, "quantity_hash": canonical_hash(payload)}


def _estimate(
    quantities: Mapping[str, Any], prices: FiberFrameMaterialPrices | None
) -> dict[str, Any] | None:
    if prices is None:
        return None
    members = [
        {
            "member_id": row["member_id"],
            "concrete": row["gross_concrete_volume_m3"] * prices.concrete_per_m3,
            "longitudinal_rebar": row["longitudinal_rebar_mass_kg"]
            * prices.rebar_per_kg,
        }
        for row in quantities["members"]
    ]
    payload = {
        "scope": QUANTITY_SCOPE,
        "currency": prices.currency,
        "price_table_hash": prices.price_table_hash,
        "quantity_hash": quantities["quantity_hash"],
        "members": members,
        "total": math.fsum(
            row["concrete"] + row["longitudinal_rebar"] for row in members
        ),
        "excluded_items": list(_EXCLUDED_COST_ITEMS),
        "verified_quote": False,
        "confirmed_currency_savings": False,
    }
    _finite_tree(payload)
    return payload


def _number(value: Any, name: str, *, zero: bool = False) -> float:
    if type(value) not in (int, float):
        raise FiberFrameDesignError(f"{name} must be a real number")
    try:
        result = float(value)
    except OverflowError as exc:
        raise FiberFrameDesignError(f"{name} must be finite") from exc
    if not math.isfinite(result) or (result < 0 if zero else result <= 0):
        raise FiberFrameDesignError(
            f"{name} must be finite and {'nonnegative' if zero else 'positive'}"
        )
    return result


def _finite_tree(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise FiberFrameDesignError("derived quantity/cost/response is nonfinite")
    if isinstance(value, Mapping):
        for item in value.values():
            _finite_tree(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _finite_tree(item)
