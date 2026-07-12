"""Canonical model dataclasses used across Developer Preview entry points."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

from structural_analysis.model.entities import (
    ElasticMaterial,
    FrameElement,
    FrameSection,
    NodalLoad,
    Node,
    Support,
    TypedModelEntities,
    typed_model_entities,
)
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
            coordinate_system=CoordinateSystem(
                axis_order=("X", "Y", "Z"),
                up_axis="Z",
            ),
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

    @property
    def typed_entities(self) -> TypedModelEntities:
        """Return immutable typed projections without breaking legacy dict consumers."""

        return typed_model_entities(
            nodes=self.nodes,
            loads=self.loads,
            supports=self.supports,
            materials=self.materials,
            sections=self.sections,
            elements=self.elements,
        )

    @property
    def node_entities(self) -> tuple[Node, ...]:
        return self.typed_entities.nodes

    @property
    def load_entities(self) -> tuple[NodalLoad, ...]:
        return self.typed_entities.loads

    @property
    def support_entities(self) -> tuple[Support, ...]:
        return self.typed_entities.supports

    @property
    def elastic_material_entities(self) -> tuple[ElasticMaterial, ...]:
        return self.typed_entities.elastic_materials

    @property
    def frame_section_entities(self) -> tuple[FrameSection, ...]:
        return self.typed_entities.frame_sections

    @property
    def frame_element_entities(self) -> tuple[FrameElement, ...]:
        return self.typed_entities.frame_elements

    def canonical_payload(self) -> dict[str, Any]:
        """Return the source-independent canonical JSON payload."""

        return {
            "schema_version": self.schema_version,
            "units": self.units.to_dict(),
            "coordinate_system": self.coordinate_system.to_dict(),
            "nodes": json.loads(json.dumps(self.nodes)),
            "elements": json.loads(json.dumps(self.elements)),
            "materials": json.loads(json.dumps(self.materials)),
            "sections": json.loads(json.dumps(self.sections)),
            "loads": json.loads(json.dumps(self.loads)),
            "supports": json.loads(json.dumps(self.supports)),
            "unsupported_features": json.loads(
                json.dumps(self.unsupported_features)
            ),
            "warnings": list(self.warnings),
            "metadata": json.loads(json.dumps(self.metadata)),
        }

    @property
    def canonical_model_checksum(self) -> str:
        """Hash normalized model semantics separately from the source-file checksum."""

        encoded = json.dumps(
            self.canonical_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["canonical_model_checksum"] = self.canonical_model_checksum
        return payload
