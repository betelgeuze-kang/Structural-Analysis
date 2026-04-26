from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Protocol


# Supported nonlinear structural-contact links:
# gap, uplift, compression-only, bearing, friction, pounding.
SUPPORTED_LINKS = ["gap", "uplift", "compression-only", "bearing", "friction", "pounding"]
SUPPORTED_LINK_KEYWORDS = "gap uplift compression-only bearing friction pounding"


@dataclass(frozen=True)
class LinkResponse:
    force: float
    tangent: float
    engaged: bool
    state_label: str
    slip: float = 0.0
    closure: float = 0.0
    energy_like: float = 0.0


class ScalarLink(Protocol):
    link_name: str

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse: ...


@dataclass(frozen=True)
class GapLink:
    stiffness: float
    gap_opening: float = 0.0
    link_name: str = "gap"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        closure = max(float(displacement) - float(self.gap_opening), 0.0)
        engaged = closure > 0.0
        force = float(self.stiffness) * closure
        return LinkResponse(
            force=force,
            tangent=float(self.stiffness) if engaged else 0.0,
            engaged=engaged,
            state_label="closed" if engaged else "open",
            closure=closure,
            energy_like=0.5 * float(self.stiffness) * closure * closure,
        )


@dataclass(frozen=True)
class UpliftLink:
    stiffness: float
    seating_tolerance: float = 0.0
    link_name: str = "uplift"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        # Negative displacement means compression toward the support seat.
        closure = max(-(float(displacement) + float(self.seating_tolerance)), 0.0)
        engaged = closure > 0.0
        force = float(self.stiffness) * closure
        return LinkResponse(
            force=force,
            tangent=float(self.stiffness) if engaged else 0.0,
            engaged=engaged,
            state_label="seated" if engaged else "uplifted",
            closure=closure,
            energy_like=0.5 * float(self.stiffness) * closure * closure,
        )


@dataclass(frozen=True)
class CompressionOnlyLink:
    stiffness: float
    preload: float = 0.0
    link_name: str = "compression-only"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        closure = max(float(displacement), 0.0)
        engaged = closure > 0.0 or float(self.preload) > 0.0
        force = float(self.preload) + float(self.stiffness) * closure if engaged else 0.0
        return LinkResponse(
            force=force,
            tangent=float(self.stiffness) if closure > 0.0 else 0.0,
            engaged=engaged,
            state_label="compression" if engaged else "released",
            closure=closure,
            energy_like=0.5 * float(self.stiffness) * closure * closure,
        )


@dataclass(frozen=True)
class BearingLink:
    elastic_stiffness: float
    yield_force: float
    post_yield_ratio: float = 0.1
    link_name: str = "bearing"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        closure = max(float(displacement), 0.0)
        if closure <= 0.0:
            return LinkResponse(0.0, 0.0, False, "released")
        elastic_limit = float(self.yield_force) / max(float(self.elastic_stiffness), 1e-9)
        if closure <= elastic_limit:
            force = float(self.elastic_stiffness) * closure
            tangent = float(self.elastic_stiffness)
            state = "elastic"
        else:
            post = closure - elastic_limit
            tangent = float(self.elastic_stiffness) * float(self.post_yield_ratio)
            force = float(self.yield_force) + tangent * post
            state = "post-yield"
        return LinkResponse(
            force=force,
            tangent=tangent,
            engaged=True,
            state_label=state,
            closure=closure,
            energy_like=force * closure * 0.5,
        )


@dataclass(frozen=True)
class FrictionLink:
    tangential_stiffness: float
    friction_coefficient: float
    normal_force: float
    link_name: str = "friction"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        slip = float(displacement)
        limit = abs(float(self.friction_coefficient) * float(self.normal_force))
        trial = float(self.tangential_stiffness) * slip
        engaged = abs(float(self.normal_force)) > 0.0
        if not engaged:
            return LinkResponse(0.0, 0.0, False, "released")
        if abs(trial) <= limit:
            force = trial
            tangent = float(self.tangential_stiffness)
            state = "stick"
        else:
            force = math.copysign(limit, slip if slip != 0.0 else velocity if velocity != 0.0 else trial)
            tangent = 0.0
            state = "slip"
        return LinkResponse(
            force=force,
            tangent=tangent,
            engaged=True,
            state_label=state,
            slip=slip,
            energy_like=abs(force * slip),
        )


@dataclass(frozen=True)
class PoundingLink:
    contact_stiffness: float
    damping: float
    impact_gap: float = 0.0
    link_name: str = "pounding"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        overlap = max(float(displacement) - float(self.impact_gap), 0.0)
        engaged = overlap > 0.0
        if not engaged:
            return LinkResponse(0.0, 0.0, False, "separated")
        # Damping acts only during approach to avoid nonphysical tensile contact.
        damping_force = float(self.damping) * max(float(velocity), 0.0)
        force = float(self.contact_stiffness) * overlap + damping_force
        return LinkResponse(
            force=force,
            tangent=float(self.contact_stiffness),
            engaged=True,
            state_label="impact",
            closure=overlap,
            energy_like=0.5 * float(self.contact_stiffness) * overlap * overlap,
        )


DEFAULT_SPECIAL_LINKS = {
    "gap": GapLink(stiffness=8.0e4, gap_opening=0.004),
    "uplift": UpliftLink(stiffness=7.5e4, seating_tolerance=0.0),
    "compression-only": CompressionOnlyLink(stiffness=9.0e4, preload=0.0),
    "bearing": BearingLink(elastic_stiffness=1.2e5, yield_force=180.0, post_yield_ratio=0.12),
    "friction": FrictionLink(tangential_stiffness=6.0e4, friction_coefficient=0.42, normal_force=320.0),
    "pounding": PoundingLink(contact_stiffness=1.8e5, damping=220.0, impact_gap=0.003),
}


def build_default_special_link_library() -> dict[str, ScalarLink]:
    return dict(DEFAULT_SPECIAL_LINKS)


def describe_special_link_library() -> dict[str, dict[str, float | str]]:
    description: dict[str, dict[str, float | str]] = {}
    for key, link in DEFAULT_SPECIAL_LINKS.items():
        row = {"link_name": key, "implementation_class": type(link).__name__}
        row.update({field: float(getattr(link, field)) for field in getattr(link, '__dataclass_fields__', {}) if field not in {'link_name'}})
        description[key] = row
    return description
