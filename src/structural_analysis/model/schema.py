"""Canonical model dataclasses used across Developer Preview entry points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from structural_analysis.units.schema import CoordinateSystem, UnitSystem

CANONICAL_MODEL_SCHEMA_VERSION = "structural-analysis-canonical-model.v1"


@dataclass(frozen=True)
class CanonicalModel:
    schema_version: str
    source_path: str
    source_format: str
    input_checksum: str
    units: UnitSystem
    coordinate_system: CoordinateSystem
    nodes: list[dict[str, Any]] = field(default_factory=list)
    elements: list[dict[str, Any]] = field(default_factory=list)
    materials: list[dict[str, Any]] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)
    loads: list[dict[str, Any]] = field(default_factory=list)
    supports: list[dict[str, Any]] = field(default_factory=list)
    unsupported_features: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def unsupported_import(
        cls,
        source_path: Path,
        source_format: str,
        reason: str,
    ) -> "CanonicalModel":
        from structural_analysis.io.neutral.loader import checksum_for_path

        return cls(
            schema_version=CANONICAL_MODEL_SCHEMA_VERSION,
            source_path=str(source_path),
            source_format=source_format,
            input_checksum=checksum_for_path(source_path),
            units=UnitSystem(length="unknown", force="unknown"),
            coordinate_system=CoordinateSystem(axis_order=("X", "Y", "Z"), up_axis="Z"),
            unsupported_features=[
                {
                    "kind": f"{source_format}_import_not_implemented",
                    "detail": reason,
                }
            ],
            warnings=[
                "Input checksum was recorded, but this source format is not converted "
                "by the first core API slice."
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
