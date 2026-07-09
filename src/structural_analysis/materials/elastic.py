"""Strict linear-elastic material model for the CPU reference solver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ElasticIsotropicMaterial:
    """Isotropic elastic properties in the canonical m/kN unit system."""

    material_id: str
    elastic_modulus: float
    poisson_ratio: float
    density: float | None = None

    def __post_init__(self) -> None:
        if not self.material_id:
            raise ValueError("material id must be non-empty")
        if self.elastic_modulus <= 0.0:
            raise ValueError(f"Material {self.material_id} elastic modulus must be positive.")
        if not (-1.0 < self.poisson_ratio < 0.5):
            raise ValueError(
                f"Material {self.material_id} Poisson ratio must be between -1 and 0.5."
            )
        if self.density is not None and self.density <= 0.0:
            raise ValueError(f"Material {self.material_id} density must be positive.")

    @property
    def shear_modulus(self) -> float:
        return self.elastic_modulus / (2.0 * (1.0 + self.poisson_ratio))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ElasticIsotropicMaterial":
        material_id = str(payload.get("id", "")).strip()
        elastic_modulus = _required_number(
            payload,
            ("elastic_modulus", "E_kN_per_m2"),
            label="elastic_modulus",
            owner=f"Material {material_id or '<unknown>'}",
        )
        poisson_ratio = _required_number(
            payload,
            ("poisson_ratio", "poisson"),
            label="poisson_ratio",
            owner=f"Material {material_id or '<unknown>'}",
        )
        density = _optional_number(payload, ("density", "density_kg_per_m3"))
        return cls(
            material_id=material_id,
            elastic_modulus=elastic_modulus,
            poisson_ratio=poisson_ratio,
            density=density,
        )


def _required_number(
    payload: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    label: str,
    owner: str,
) -> float:
    value = _optional_number(payload, keys)
    if value is None:
        raise ValueError(f"{owner} requires explicit {label}; production fallback is disabled.")
    return value


def _optional_number(payload: Mapping[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key not in payload or payload.get(key) is None:
            continue
        try:
            return float(payload[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} must be numeric.") from exc
    return None
