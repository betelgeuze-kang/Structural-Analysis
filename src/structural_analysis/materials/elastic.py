"""Strict linear-elastic material model for the CPU reference solver."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping

from structural_analysis.materials.admissibility import MaterialAdmissibility


@dataclass(frozen=True)
class ElasticIsotropicMaterial:
    """Isotropic elastic properties in the canonical m/kN unit system."""

    material_id: str
    elastic_modulus: float
    poisson_ratio: float
    density: float | None = None
    loading_domain: str = "finite_linear_elastic_3d"
    supports_unloading: bool = True
    supports_reversal: bool = True
    supports_cyclic: bool = True
    supports_tension: bool = True
    supports_compression: bool = True
    supports_multiaxial: bool = True

    def __post_init__(self) -> None:
        if not self.material_id:
            raise ValueError("material id must be non-empty")
        if not isfinite(self.elastic_modulus) or self.elastic_modulus <= 0.0:
            raise ValueError(
                f"Material {self.material_id} elastic modulus must be finite and positive."
            )
        if not isfinite(self.poisson_ratio) or not (-1.0 < self.poisson_ratio < 0.5):
            raise ValueError(
                f"Material {self.material_id} Poisson ratio must be finite and between -1 and 0.5."
            )
        if self.density is not None and (
            not isfinite(self.density) or self.density <= 0.0
        ):
            raise ValueError(
                f"Material {self.material_id} density must be finite and positive."
            )

    @property
    def shear_modulus(self) -> float:
        return self.elastic_modulus / (2.0 * (1.0 + self.poisson_ratio))

    @property
    def admissibility(self) -> MaterialAdmissibility:
        return MaterialAdmissibility(
            loading_domain=self.loading_domain,
            supports_unloading=self.supports_unloading,
            supports_reversal=self.supports_reversal,
            supports_cyclic=self.supports_cyclic,
            supports_tension=self.supports_tension,
            supports_compression=self.supports_compression,
            supports_multiaxial=self.supports_multiaxial,
        )

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
