"""Units and coordinate-system contracts for canonical models."""

from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LENGTH_UNITS = {"m", "mm", "cm", "ft", "in", "unknown"}
SUPPORTED_FORCE_UNITS = {"N", "kN", "MN", "lbf", "kip", "unknown"}
SUPPORTED_AXES = {"X", "Y", "Z"}


@dataclass(frozen=True)
class UnitSystem:
    length: str
    force: str

    def __post_init__(self) -> None:
        if self.length not in SUPPORTED_LENGTH_UNITS:
            raise ValueError(f"Unsupported length unit: {self.length}")
        if self.force not in SUPPORTED_FORCE_UNITS:
            raise ValueError(f"Unsupported force unit: {self.force}")


@dataclass(frozen=True)
class CoordinateSystem:
    axis_order: tuple[str, str, str]
    up_axis: str

    def __post_init__(self) -> None:
        if len(self.axis_order) != 3:
            raise ValueError("axis_order must contain exactly three axes.")
        if set(self.axis_order) != SUPPORTED_AXES:
            raise ValueError("axis_order must be a permutation of X, Y, Z.")
        if self.up_axis not in SUPPORTED_AXES:
            raise ValueError(f"Unsupported up_axis: {self.up_axis}")
