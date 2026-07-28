"""Shared material loading-domain and path-admissibility contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable


UNSUPPORTED_CONSTITUTIVE_PATH = "unsupported_constitutive_path"


class MaterialPathNotAdmissibleError(ValueError):
    """Raised before a constitutive law is used outside its declared domain."""

    code = UNSUPPORTED_CONSTITUTIVE_PATH


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
        for name, value in asdict(self).items():
            if name != "loading_domain" and type(value) is not bool:
                raise TypeError(f"material {name} must be boolean")
        if self.supports_cyclic and (
            not self.supports_monotonic
            or not self.supports_unloading
            or not self.supports_reversal
        ):
            raise ValueError(
                "supports_cyclic requires monotonic, unloading, and reversal support"
            )

    def to_dict(self) -> dict[str, str | bool]:
        return dict(asdict(self))


@dataclass(frozen=True)
class ScalarLoadingPathDemand:
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
    """Infer loading-path demands without evaluating a constitutive law."""

    history = tuple(float(value) for value in values)
    if not history or any(not math.isfinite(value) for value in history):
        raise ValueError("material loading history must contain finite values")
    if prior_increment_sign not in (-1, 0, 1):
        raise ValueError("prior_increment_sign must be -1, 0, or 1")
    tolerance = float(zero_tolerance)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("zero_tolerance must be finite and non-negative")

    increment_signs: list[int] = []
    for previous, current in zip(history, history[1:]):
        increment = current - previous
        if increment > tolerance:
            increment_signs.append(1)
        elif increment < -tolerance:
            increment_signs.append(-1)
    effective_signs = list(increment_signs)
    if prior_increment_sign:
        effective_signs.insert(0, prior_increment_sign)
    reversal_count = sum(
        previous != current
        for previous, current in zip(effective_signs, effective_signs[1:])
    )
    unloading = any(
        abs(current) + tolerance < abs(previous)
        for previous, current in zip(history, history[1:])
    )
    return ScalarLoadingPathDemand(
        value_count=len(history),
        requires_monotonic=True,
        requires_tension=any(value > tolerance for value in history),
        requires_compression=any(value < -tolerance for value in history),
        requires_unloading=unloading,
        requires_reversal=reversal_count > 0,
        requires_cyclic=reversal_count > 0,
    )


def require_scalar_loading_path_admissible(
    admissibility: MaterialAdmissibility,
    values: Iterable[float],
    *,
    prior_increment_sign: int = 0,
    owner: str = "material",
) -> ScalarLoadingPathDemand:
    """Reject an unsupported path before constitutive evaluation."""

    if type(admissibility) is not MaterialAdmissibility:
        raise TypeError("admissibility must be an exact MaterialAdmissibility")
    demand = scalar_loading_path_demand(
        values,
        prior_increment_sign=prior_increment_sign,
    )
    unsupported: list[str] = []
    for required, supported, label in (
        (demand.requires_monotonic, admissibility.supports_monotonic, "monotonic"),
        (demand.requires_tension, admissibility.supports_tension, "tension"),
        (
            demand.requires_compression,
            admissibility.supports_compression,
            "compression",
        ),
        (demand.requires_unloading, admissibility.supports_unloading, "unloading"),
        (demand.requires_reversal, admissibility.supports_reversal, "reversal"),
        (demand.requires_cyclic, admissibility.supports_cyclic, "cyclic"),
    ):
        if required and not supported:
            unsupported.append(label)
    if unsupported:
        raise MaterialPathNotAdmissibleError(
            f"{UNSUPPORTED_CONSTITUTIVE_PATH}: owner={owner} "
            f"loading_domain={admissibility.loading_domain} "
            f"unsupported={','.join(unsupported)}"
        )
    return demand


__all__ = [
    "MaterialAdmissibility",
    "MaterialPathNotAdmissibleError",
    "ScalarLoadingPathDemand",
    "UNSUPPORTED_CONSTITUTIVE_PATH",
    "require_scalar_loading_path_admissible",
    "scalar_loading_path_demand",
]
