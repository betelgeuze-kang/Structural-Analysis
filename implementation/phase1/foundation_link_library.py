from __future__ import annotations

from dataclasses import dataclass
import math

from implementation.phase1.special_link_library import LinkResponse


@dataclass(frozen=True)
class PySoilSpring:
    lateral_stiffness: float
    yield_force: float
    post_yield_ratio: float = 0.15
    link_name: str = "p-y"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        sign = 1.0 if disp >= 0.0 else -1.0
        abs_disp = abs(disp)
        yield_disp = float(self.yield_force) / max(float(self.lateral_stiffness), 1e-9)
        if abs_disp <= yield_disp:
            force = float(self.lateral_stiffness) * disp
            tangent = float(self.lateral_stiffness)
            state = "elastic"
        else:
            post_disp = abs_disp - yield_disp
            tangent = float(self.lateral_stiffness) * float(self.post_yield_ratio)
            force = sign * (float(self.yield_force) + tangent * post_disp)
            state = "plastic"
        mobilization = min(abs(force) / max(float(self.yield_force), 1e-9), 1.0)
        return LinkResponse(force=force, tangent=tangent, engaged=True, state_label=state, slip=disp, energy_like=0.5 * abs(force * disp), closure=mobilization)


@dataclass(frozen=True)
class TzSoilSpring:
    axial_stiffness: float
    shaft_capacity: float
    residual_ratio: float = 0.35
    link_name: str = "t-z"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        trial = float(self.axial_stiffness) * disp
        limit = float(self.shaft_capacity)
        if abs(trial) <= limit:
            return LinkResponse(force=trial, tangent=float(self.axial_stiffness), engaged=True, state_label="elastic", slip=disp, energy_like=0.5 * abs(trial * disp))
        force = (1.0 if trial >= 0.0 else -1.0) * limit * float(self.residual_ratio)
        return LinkResponse(force=force, tangent=0.0, engaged=True, state_label="residual", slip=disp, energy_like=abs(force * disp))


@dataclass(frozen=True)
class QzSoilSpring:
    tip_stiffness: float
    tip_capacity: float
    cap_ratio: float = 1.0
    link_name: str = "q-z"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = max(float(displacement), 0.0)
        cap = float(self.tip_capacity) * float(self.cap_ratio)
        trial = float(self.tip_stiffness) * disp
        if trial <= cap:
            return LinkResponse(force=trial, tangent=float(self.tip_stiffness), engaged=disp > 0.0, state_label="mobilizing", closure=disp, energy_like=0.5 * trial * disp)
        return LinkResponse(force=cap, tangent=0.0, engaged=True, state_label="capped", closure=disp, energy_like=cap * disp)


@dataclass(frozen=True)
class PileHeadSpring:
    rotational_stiffness: float
    yield_moment: float
    post_yield_ratio: float = 0.08
    link_name: str = "pile_head"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        rotation = float(displacement)
        sign = 1.0 if rotation >= 0.0 else -1.0
        yield_rotation = float(self.yield_moment) / max(float(self.rotational_stiffness), 1e-9)
        if abs(rotation) <= yield_rotation:
            moment = float(self.rotational_stiffness) * rotation
            tangent = float(self.rotational_stiffness)
            state = "elastic"
        else:
            tangent = float(self.rotational_stiffness) * float(self.post_yield_ratio)
            moment = sign * (float(self.yield_moment) + tangent * (abs(rotation) - yield_rotation))
            state = "post-yield"
        return LinkResponse(force=moment, tangent=tangent, engaged=True, state_label=state, slip=rotation, energy_like=0.5 * abs(moment * rotation))


DEFAULT_FOUNDATION_LINKS = {
    "p-y": PySoilSpring(lateral_stiffness=9.0e4, yield_force=180.0, post_yield_ratio=0.18),
    "t-z": TzSoilSpring(axial_stiffness=7.5e4, shaft_capacity=220.0, residual_ratio=0.4),
    "q-z": QzSoilSpring(tip_stiffness=1.4e5, tip_capacity=320.0, cap_ratio=1.0),
    "pile_head": PileHeadSpring(rotational_stiffness=4.0e4, yield_moment=140.0, post_yield_ratio=0.1),
}


FOUNDATION_SUPPORT_SEARCH_METADATA = {
    "p-y": {
        "support_role": "soil_lateral_support",
        "search_surface_mode": "node_to_soil_surface_proxy",
        "search_family": "foundation_support_search",
        "node_to_surface_proxy": True,
        "support_search_ready": True,
        "support_depth_rank": 3,
        "sample_displacement": 0.006,
        "sample_velocity": 0.0,
    },
    "t-z": {
        "support_role": "shaft_friction_transfer",
        "search_surface_mode": "node_to_shaft_surface_proxy",
        "search_family": "foundation_support_search",
        "node_to_surface_proxy": True,
        "support_search_ready": True,
        "support_depth_rank": 3,
        "sample_displacement": 0.005,
        "sample_velocity": 0.0,
    },
    "q-z": {
        "support_role": "tip_bearing_transfer",
        "search_surface_mode": "node_to_tip_surface_proxy",
        "search_family": "foundation_support_search",
        "node_to_surface_proxy": True,
        "support_search_ready": True,
        "support_depth_rank": 3,
        "sample_displacement": 0.004,
        "sample_velocity": 0.0,
    },
    "pile_head": {
        "support_role": "head_fixity_transfer",
        "search_surface_mode": "support_head_rotation_search",
        "search_family": "foundation_support_search",
        "node_to_surface_proxy": False,
        "support_search_ready": True,
        "support_depth_rank": 2,
        "sample_displacement": 0.004,
        "sample_velocity": 0.0,
    },
}


def build_default_foundation_link_library() -> dict[str, object]:
    return dict(DEFAULT_FOUNDATION_LINKS)


def _sample_capacity_value(link: object) -> float:
    for field_name in ("yield_force", "shaft_capacity", "tip_capacity", "yield_moment"):
        value = getattr(link, field_name, None)
        if value is not None:
            return max(float(value), 1e-9)
    return 1.0


def _foundation_search_geometry(
    *,
    link_name: str,
    pile_diameter_m: float,
    embedment_depth_m: float,
    support_spacing_m: float,
) -> dict[str, object]:
    diameter = max(float(pile_diameter_m), 1e-6)
    embedment = max(float(embedment_depth_m), diameter)
    spacing = max(float(support_spacing_m), diameter)
    radius = 0.5 * diameter

    if link_name == "p-y":
        return {
            "contact_family": "soil_lateral_interface",
            "contact_search_axis": "local-x",
            "search_normal": [1.0, 0.0, 0.0],
            "search_patch_area_m2": diameter * embedment,
            "tributary_length_m": embedment,
            "search_radius_m": radius,
        }
    if link_name == "t-z":
        return {
            "contact_family": "shaft_friction_interface",
            "contact_search_axis": "local-z",
            "search_normal": [0.0, 0.0, 1.0],
            "search_patch_area_m2": math.pi * diameter * embedment,
            "tributary_length_m": math.pi * diameter,
            "search_radius_m": radius,
        }
    if link_name == "q-z":
        return {
            "contact_family": "tip_bearing_interface",
            "contact_search_axis": "local-z",
            "search_normal": [0.0, 0.0, 1.0],
            "search_patch_area_m2": math.pi * radius * radius,
            "tributary_length_m": diameter,
            "search_radius_m": radius,
        }
    return {
        "contact_family": "pile_head_fixity_interface",
        "contact_search_axis": "rotation-y",
        "search_normal": [0.0, 0.0, 1.0],
        "search_patch_area_m2": spacing * spacing,
        "tributary_length_m": spacing,
        "search_radius_m": 0.5 * spacing,
    }


def build_foundation_support_search_candidates(
    *,
    pile_diameter_m: float = 0.8,
    embedment_depth_m: float = 8.0,
    support_spacing_m: float = 3.0,
) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for key, link in DEFAULT_FOUNDATION_LINKS.items():
        meta = FOUNDATION_SUPPORT_SEARCH_METADATA.get(key, {})
        disp = float(meta.get("sample_displacement", 0.0))
        vel = float(meta.get("sample_velocity", 0.0))
        probe = link.evaluate(displacement=disp, velocity=vel)
        geometry = _foundation_search_geometry(
            link_name=key,
            pile_diameter_m=pile_diameter_m,
            embedment_depth_m=embedment_depth_m,
            support_spacing_m=support_spacing_m,
        )
        capacity = _sample_capacity_value(link)
        patch_area = float(geometry.get("search_patch_area_m2", 0.0) or 0.0)
        candidates.append(
            {
                "link_name": key,
                "support_role": str(meta.get("support_role", "")),
                "search_surface_mode": str(meta.get("search_surface_mode", "")),
                "search_family": str(meta.get("search_family", "")),
                "node_to_surface_proxy": bool(meta.get("node_to_surface_proxy", False)),
                "support_search_ready": bool(meta.get("support_search_ready", False)),
                "support_depth_rank": int(meta.get("support_depth_rank", 0)),
                "contact_family": str(geometry.get("contact_family", "")),
                "contact_search_axis": str(geometry.get("contact_search_axis", "")),
                "search_normal": list(geometry.get("search_normal", [0.0, 0.0, 1.0])),
                "search_patch_area_m2": patch_area,
                "tributary_length_m": float(geometry.get("tributary_length_m", 0.0) or 0.0),
                "search_radius_m": float(geometry.get("search_radius_m", 0.0) or 0.0),
                "support_candidate_ready": bool(meta.get("support_search_ready", False) and patch_area > 0.0),
                "sample_probe_state": str(probe.state_label),
                "sample_probe_engaged": bool(probe.engaged),
                "sample_probe_force": float(probe.force),
                "sample_probe_tangent": float(probe.tangent),
                "sample_probe_closure": float(probe.closure),
                "sample_probe_energy_like": float(probe.energy_like),
                "sample_response_ratio": abs(float(probe.force)) / capacity,
            }
        )
    return candidates


def describe_foundation_link_library() -> dict[str, dict[str, object]]:
    support_candidates = {
        str(row.get("link_name", "")).strip(): row for row in build_foundation_support_search_candidates()
    }
    out: dict[str, dict[str, object]] = {}
    for key, link in DEFAULT_FOUNDATION_LINKS.items():
        row = {"link_name": key, "implementation_class": type(link).__name__}
        row.update(
            {
                field: float(getattr(link, field))
                for field in getattr(link, "__dataclass_fields__", {})
                if field != "link_name"
            }
        )
        meta = FOUNDATION_SUPPORT_SEARCH_METADATA.get(key, {})
        disp = float(meta.get("sample_displacement", 0.0))
        vel = float(meta.get("sample_velocity", 0.0))
        probe = link.evaluate(displacement=disp, velocity=vel)
        row.update(
            {
                "support_role": str(meta.get("support_role", "")),
                "search_surface_mode": str(meta.get("search_surface_mode", "")),
                "search_family": str(meta.get("search_family", "")),
                "node_to_surface_proxy": bool(meta.get("node_to_surface_proxy", False)),
                "support_search_ready": bool(meta.get("support_search_ready", False)),
                "support_depth_rank": int(meta.get("support_depth_rank", 0)),
                "sample_probe_state": str(probe.state_label),
                "sample_probe_engaged": bool(probe.engaged),
                "sample_probe_force": float(probe.force),
            }
        )
        candidate = support_candidates.get(key, {})
        row.update(
            {
                "contact_family": str(candidate.get("contact_family", "")),
                "contact_search_axis": str(candidate.get("contact_search_axis", "")),
                "search_normal": list(candidate.get("search_normal", [0.0, 0.0, 1.0])),
                "search_patch_area_m2": float(candidate.get("search_patch_area_m2", 0.0) or 0.0),
                "tributary_length_m": float(candidate.get("tributary_length_m", 0.0) or 0.0),
                "search_radius_m": float(candidate.get("search_radius_m", 0.0) or 0.0),
                "support_candidate_ready": bool(candidate.get("support_candidate_ready", False)),
                "sample_probe_tangent": float(candidate.get("sample_probe_tangent", 0.0) or 0.0),
                "sample_probe_closure": float(candidate.get("sample_probe_closure", 0.0) or 0.0),
                "sample_probe_energy_like": float(candidate.get("sample_probe_energy_like", 0.0) or 0.0),
                "sample_response_ratio": float(candidate.get("sample_response_ratio", 0.0) or 0.0),
            }
        )
        out[key] = row
    return out


__all__ = [
    "DEFAULT_FOUNDATION_LINKS",
    "PileHeadSpring",
    "PySoilSpring",
    "QzSoilSpring",
    "TzSoilSpring",
    "build_default_foundation_link_library",
    "build_foundation_support_search_candidates",
    "describe_foundation_link_library",
]
