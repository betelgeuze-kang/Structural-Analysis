"""Shared material loading-domain and path-admissibility contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Iterable


class MaterialPathNotAdmissibleError(ValueError):
    """Raised before a constitutive law is used outside its declared domain."""


@dataclass(frozen=True)
class MaterialAdmissibility:
    """Explicit loading-domain capabilities for a material contract."""

    loading_domain: str
    supports_monotonic: bool
    supports_unloading: bool
    supports_reversal: bool
    supports_cyclic: bool
    supports_tension: bool
    supports_compression: bool
    supports_multiaxial: bool
    supports_localization_regularization: bool

    def __post_init__(self) -> None:
        if not str(self.loading_domain).strip():
            raise ValueError("material loading_domain must be non-empty")
        for field_name, value in asdict(self).items():
            if field_name == "loading_domain":
                continue
            if type(value) is not bool:
                raise TypeError(f"material {field_name} must be boolean")
        if self.supports_cyclic and (
            not self.supports_monotonic
            or not self.supports_unloading
            or not self.supports_reversal
        ):
            raise ValueError(
                "supports_cyclic requires supports_monotonic, supports_unloading, "
                "and supports_reversal"
            )

    def to_dict(self) -> dict[str, str | bool]:
        """Return the stable JSON-ready material contract."""

        return dict(asdict(self))


@dataclass(frozen=True)
class ScalarLoadingPathDemand:
    """Loading-path features inferred from a finite scalar history."""

    value_count: int
    requires_monotonic: bool
    requires_tension: bool
    requires_compression: bool
    requires_unloading: bool
    requires_reversal: bool
    requires_cyclic: bool


def scalar_loading_path_demand(
    values: Iterable[float],
    *,
    prior_increment_sign: int = 0,
    zero_tolerance: float = 1.0e-12,
) -> ScalarLoadingPathDemand:
    """Infer path demand without executing a constitutive response."""

    history = tuple(float(value) for value in values)
    if not history:
        raise ValueError("material loading history must contain at least one value")
    if any(not isfinite(value) for value in history):
        raise ValueError("material loading history must contain only finite values")

    increment_signs: list[int] = []
    for previous, current in zip(history, history[1:]):
        increment = current - previous
        if increment > zero_tolerance:
            increment_signs.append(1)
        elif increment < -zero_tolerance:
            increment_signs.append(-1)

    effective_signs = list(increment_signs)
    if prior_increment_sign in {-1, 1}:
        effective_signs.insert(0, int(prior_increment_sign))
    reversal_count = sum(
        previous != current
        for previous, current in zip(effective_signs, effective_signs[1:])
    )
    requires_unloading = any(
        abs(current) + zero_tolerance < abs(previous)
        for previous, current in zip(history, history[1:])
    )
    requires_reversal = reversal_count > 0
    return ScalarLoadingPathDemand(
        value_count=len(history),
        requires_monotonic=True,
        requires_tension=any(value > zero_tolerance for value in history),
        requires_compression=any(value < -zero_tolerance for value in history),
        requires_unloading=requires_unloading,
        requires_reversal=requires_reversal,
        requires_cyclic=requires_reversal,
    )


def require_scalar_loading_path_admissible(
    admissibility: MaterialAdmissibility,
    values: Iterable[float],
    *,
    prior_increment_sign: int = 0,
    owner: str = "material",
) -> ScalarLoadingPathDemand:
    """Reject unsupported loading history before constitutive evaluation."""

    demand = scalar_loading_path_demand(
        values,
        prior_increment_sign=prior_increment_sign,
    )
    unsupported: list[str] = []
    if demand.requires_monotonic and not admissibility.supports_monotonic:
        unsupported.append("monotonic")
    if demand.requires_tension and not admissibility.supports_tension:
        unsupported.append("tension")
    if demand.requires_compression and not admissibility.supports_compression:
        unsupported.append("compression")
    if demand.requires_unloading and not admissibility.supports_unloading:
        unsupported.append("unloading")
    if demand.requires_reversal and not admissibility.supports_reversal:
        unsupported.append("reversal")
    if demand.requires_cyclic and not admissibility.supports_cyclic:
        unsupported.append("cyclic")
    if unsupported:
        kinds = ",".join(unsupported)
        raise MaterialPathNotAdmissibleError(
            "material_loading_path_not_admissible: "
            f"{owner} loading_domain={admissibility.loading_domain} "
            f"unsupported={kinds}"
        )
    return demand


__all__ = [
    "MaterialAdmissibility",
    "MaterialPathNotAdmissibleError",
    "ScalarLoadingPathDemand",
    "require_scalar_loading_path_admissible",
    "scalar_loading_path_demand",
]
