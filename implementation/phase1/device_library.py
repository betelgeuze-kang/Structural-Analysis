from __future__ import annotations

from dataclasses import dataclass

from implementation.phase1.special_link_library import LinkResponse


@dataclass(frozen=True)
class ViscousDamper:
    damping_coefficient: float
    exponent: float = 1.0
    link_name: str = "viscous_damper"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        vel = float(velocity)
        sign = 1.0 if vel >= 0.0 else -1.0
        force = sign * float(self.damping_coefficient) * (abs(vel) ** float(self.exponent))
        return LinkResponse(force=force, tangent=0.0, engaged=abs(vel) > 0.0, state_label="dissipating", slip=float(displacement), energy_like=abs(force * vel))


@dataclass(frozen=True)
class ViscoelasticDamper:
    stiffness: float
    damping_coefficient: float
    link_name: str = "viscoelastic_damper"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        vel = float(velocity)
        force = float(self.stiffness) * disp + float(self.damping_coefficient) * vel
        return LinkResponse(force=force, tangent=float(self.stiffness), engaged=abs(disp) > 0.0 or abs(vel) > 0.0, state_label="viscoelastic", slip=disp, energy_like=0.5 * abs(force * disp))


@dataclass(frozen=True)
class FrictionPendulumBearing:
    radius_m: float
    friction_coefficient: float
    vertical_load: float
    link_name: str = "friction_pendulum"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        restoring = float(self.vertical_load) * disp / max(float(self.radius_m), 1e-9)
        friction = float(self.friction_coefficient) * float(self.vertical_load)
        if abs(restoring) <= friction:
            return LinkResponse(force=restoring, tangent=float(self.vertical_load) / max(float(self.radius_m), 1e-9), engaged=True, state_label="stick", slip=disp, energy_like=0.5 * abs(restoring * disp))
        force = (1.0 if disp >= 0.0 else -1.0) * friction
        return LinkResponse(force=force, tangent=0.0, engaged=True, state_label="slide", slip=disp, energy_like=abs(force * disp))


@dataclass(frozen=True)
class LeadRubberBearing:
    elastic_stiffness: float
    yield_force: float
    post_yield_ratio: float = 0.12
    link_name: str = "lead_rubber_bearing"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        sign = 1.0 if disp >= 0.0 else -1.0
        yield_disp = float(self.yield_force) / max(float(self.elastic_stiffness), 1e-9)
        if abs(disp) <= yield_disp:
            return LinkResponse(force=float(self.elastic_stiffness) * disp, tangent=float(self.elastic_stiffness), engaged=abs(disp) > 0.0, state_label="elastic", slip=disp, energy_like=0.5 * abs(float(self.elastic_stiffness) * disp * disp))
        tangent = float(self.elastic_stiffness) * float(self.post_yield_ratio)
        force = sign * (float(self.yield_force) + tangent * (abs(disp) - yield_disp))
        return LinkResponse(force=force, tangent=tangent, engaged=True, state_label="yielded", slip=disp, energy_like=abs(force * disp))


@dataclass(frozen=True)
class TunedMassDamper:
    stiffness: float
    damping: float
    mass: float
    link_name: str = "tmd"

    def evaluate(self, displacement: float, velocity: float = 0.0) -> LinkResponse:
        disp = float(displacement)
        vel = float(velocity)
        force = float(self.stiffness) * disp + float(self.damping) * vel
        return LinkResponse(force=force, tangent=float(self.stiffness), engaged=abs(disp) > 0.0 or abs(vel) > 0.0, state_label="tracking", slip=disp, energy_like=0.5 * abs(force * disp) + 0.5 * float(self.mass) * vel * vel)


DEFAULT_DEVICES = {
    "viscous_damper": ViscousDamper(damping_coefficient=1400.0, exponent=0.35),
    "viscoelastic_damper": ViscoelasticDamper(stiffness=8000.0, damping_coefficient=600.0),
    "friction_pendulum": FrictionPendulumBearing(radius_m=3.2, friction_coefficient=0.05, vertical_load=1800.0),
    "lead_rubber_bearing": LeadRubberBearing(elastic_stiffness=9500.0, yield_force=180.0, post_yield_ratio=0.1),
    "tmd": TunedMassDamper(stiffness=2200.0, damping=180.0, mass=450.0),
}


DEVICE_SUPPORT_SEARCH_METADATA = {
    "viscous_damper": {
        "device_family": "damper",
        "support_role": "energy_dissipation_path",
        "search_surface_mode": "brace_end_support_search",
        "search_family": "device_support_search",
        "contact_integration_surface": "brace_end_support_link",
        "node_to_surface_proxy": False,
        "support_search_ready": True,
        "support_depth_rank": 1,
        "sample_displacement": 0.0,
        "sample_velocity": 0.35,
    },
    "viscoelastic_damper": {
        "device_family": "damper",
        "support_role": "stiffness_damping_coupler",
        "search_surface_mode": "brace_end_support_search",
        "search_family": "device_support_search",
        "contact_integration_surface": "brace_end_support_link",
        "node_to_surface_proxy": False,
        "support_search_ready": True,
        "support_depth_rank": 2,
        "sample_displacement": 0.012,
        "sample_velocity": 0.18,
    },
    "friction_pendulum": {
        "device_family": "isolation_bearing",
        "support_role": "isolation_interface",
        "search_surface_mode": "node_to_surface_isolation_proxy",
        "search_family": "device_support_search",
        "contact_integration_surface": "node_to_surface_proxy",
        "node_to_surface_proxy": True,
        "support_search_ready": True,
        "support_depth_rank": 3,
        "sample_displacement": 0.08,
        "sample_velocity": 0.0,
    },
    "lead_rubber_bearing": {
        "device_family": "isolation_bearing",
        "support_role": "isolation_bearing_support",
        "search_surface_mode": "node_to_surface_isolation_proxy",
        "search_family": "device_support_search",
        "contact_integration_surface": "node_to_surface_proxy",
        "node_to_surface_proxy": True,
        "support_search_ready": True,
        "support_depth_rank": 3,
        "sample_displacement": 0.03,
        "sample_velocity": 0.0,
    },
    "tmd": {
        "device_family": "tuned_mass",
        "support_role": "secondary_mass_tuning",
        "search_surface_mode": "tuned_mass_attachment_search",
        "search_family": "device_support_search",
        "contact_integration_surface": "secondary_mass_attachment",
        "node_to_surface_proxy": False,
        "support_search_ready": True,
        "support_depth_rank": 1,
        "sample_displacement": 0.01,
        "sample_velocity": 0.15,
    },
}


def build_default_device_library() -> dict[str, object]:
    return dict(DEFAULT_DEVICES)


def describe_device_library() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key, device in DEFAULT_DEVICES.items():
        row = {"link_name": key, "implementation_class": type(device).__name__}
        row.update(
            {
                field: float(getattr(device, field))
                for field in getattr(device, "__dataclass_fields__", {})
                if field != "link_name"
            }
        )
        meta = DEVICE_SUPPORT_SEARCH_METADATA.get(key, {})
        disp = float(meta.get("sample_displacement", 0.0))
        vel = float(meta.get("sample_velocity", 0.0))
        probe = device.evaluate(displacement=disp, velocity=vel)
        row.update(
            {
                "device_family": str(meta.get("device_family", "")),
                "support_role": str(meta.get("support_role", "")),
                "search_surface_mode": str(meta.get("search_surface_mode", "")),
                "search_family": str(meta.get("search_family", "")),
                "contact_integration_surface": str(meta.get("contact_integration_surface", "")),
                "node_to_surface_proxy": bool(meta.get("node_to_surface_proxy", False)),
                "support_search_ready": bool(meta.get("support_search_ready", False)),
                "support_depth_rank": int(meta.get("support_depth_rank", 0)),
                "sample_probe_displacement": disp,
                "sample_probe_velocity": vel,
                "sample_probe_state": str(probe.state_label),
                "sample_probe_engaged": bool(probe.engaged),
                "sample_probe_force": float(probe.force),
                "sample_probe_tangent": float(probe.tangent),
                "sample_probe_energy_like": float(probe.energy_like),
                "contact_proxy_ready": bool(
                    meta.get("support_search_ready", False)
                    and (meta.get("node_to_surface_proxy", False) or probe.engaged)
                ),
                "search_ready_signature": (
                    f"{str(meta.get('device_family', '')).strip()}:"
                    f"{str(meta.get('search_surface_mode', '')).strip()}:"
                    f"{str(meta.get('contact_integration_surface', '')).strip()}"
                ).strip(":"),
            }
        )
        out[key] = row
    return out


def describe_device_support_surface() -> dict[str, object]:
    catalog = describe_device_library()
    support_search_model_types = sorted(
        {
            str(name).strip()
            for name, row in catalog.items()
            if isinstance(row, dict) and bool(row.get("support_search_ready", False)) and str(name).strip()
        }
    )
    node_to_surface_proxy_model_types = sorted(
        {
            str(name).strip()
            for name, row in catalog.items()
            if isinstance(row, dict) and bool(row.get("node_to_surface_proxy", False)) and str(name).strip()
        }
    )
    device_family_counts: dict[str, int] = {}
    search_surface_mode_counts: dict[str, int] = {}
    search_family_counts: dict[str, int] = {}
    contact_integration_surface_counts: dict[str, int] = {}
    support_depth_score = 0
    evidence_rows: list[dict[str, object]] = []
    for name, row in catalog.items():
        if not isinstance(row, dict):
            continue
        device_family = str(row.get("device_family", "")).strip()
        mode = str(row.get("search_surface_mode", "")).strip()
        family = str(row.get("search_family", "")).strip()
        integration_surface = str(row.get("contact_integration_surface", "")).strip()
        if device_family:
            device_family_counts[device_family] = int(device_family_counts.get(device_family, 0) + 1)
        if mode:
            search_surface_mode_counts[mode] = int(search_surface_mode_counts.get(mode, 0) + 1)
        if family:
            search_family_counts[family] = int(search_family_counts.get(family, 0) + 1)
        if integration_surface:
            contact_integration_surface_counts[integration_surface] = int(
                contact_integration_surface_counts.get(integration_surface, 0) + 1
            )
        support_depth_score += int(row.get("support_depth_rank", 0) or 0)
        evidence_rows.append(
            {
                "link_name": str(name),
                "device_family": device_family,
                "search_surface_mode": mode,
                "contact_integration_surface": integration_surface,
                "node_to_surface_proxy": bool(row.get("node_to_surface_proxy", False)),
                "support_search_ready": bool(row.get("support_search_ready", False)),
                "contact_proxy_ready": bool(row.get("contact_proxy_ready", False)),
                "sample_probe_state": str(row.get("sample_probe_state", "")),
                "sample_probe_engaged": bool(row.get("sample_probe_engaged", False)),
            }
        )
    summary_line = (
        f"Device support surface: {'PASS' if support_search_model_types else 'CHECK'} | "
        f"device={len(catalog)} | "
        f"support_search={len(support_search_model_types)} | "
        f"node_surface_proxy={len(node_to_surface_proxy_model_types)} | "
        f"support_depth={support_depth_score}"
    )
    return {
        "device_model_types": sorted(str(name).strip() for name in catalog if str(name).strip()),
        "support_search_model_types": support_search_model_types,
        "node_to_surface_proxy_model_types": node_to_surface_proxy_model_types,
        "search_surface_mode_counts": search_surface_mode_counts,
        "search_family_counts": search_family_counts,
        "device_family_counts": device_family_counts,
        "contact_integration_surface_counts": contact_integration_surface_counts,
        "support_depth_score": int(support_depth_score),
        "support_link_group_counts": {"device": len(catalog)},
        "support_search_surface_pass": bool(support_search_model_types),
        "node_to_surface_proxy_pass": bool(node_to_surface_proxy_model_types),
        "support_search_evidence_rows": evidence_rows[:24],
        "summary_line": summary_line,
    }


__all__ = [
    "DEFAULT_DEVICES",
    "DEVICE_SUPPORT_SEARCH_METADATA",
    "FrictionPendulumBearing",
    "LeadRubberBearing",
    "TunedMassDamper",
    "ViscoelasticDamper",
    "ViscousDamper",
    "build_default_device_library",
    "describe_device_library",
    "describe_device_support_surface",
]
