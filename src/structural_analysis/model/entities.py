"""Immutable typed projections for the canonical structural model."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
import json
from math import isfinite
from typing import Any, ClassVar

from structural_analysis.materials.admissibility import MaterialAdmissibility


FRAME_DOF_LABELS = ("UX", "UY", "UZ", "RX", "RY", "RZ")
LOAD_COMPONENT_LABELS = ("FX", "FY", "FZ", "MX", "MY", "MZ")


def _extras_json(payload: Mapping[str, Any], known: set[str]) -> str:
    extras = {str(key): value for key, value in payload.items() if key not in known}
    return json.dumps(
        extras,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _extras_payload(extras_json: str) -> dict[str, Any]:
    value = json.loads(extras_json)
    if not isinstance(value, dict):
        raise ValueError("entity extras must decode to a JSON object")
    return value


def _nonempty_text(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field_name} must be a non-empty string")
    return text


def _finite_float(value: Any, *, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be numeric") from exc
    if not isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _optional_finite_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    return _finite_float(value, field_name=field_name)


class CanonicalEntity(Mapping[str, Any]):
    """Mapping-compatible immutable canonical entity base class."""

    entity_kind: ClassVar[str]

    def to_dict(self) -> dict[str, Any]:
        raise NotImplementedError

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())


@dataclass(frozen=True)
class Node(CanonicalEntity):
    entity_kind: ClassVar[str] = "node"
    id: str
    coordinates: tuple[float, float, float]
    extras_json: str = field(default="{}", repr=False)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Node":
        node_id = _nonempty_text(payload.get("id"), field_name="node.id")
        raw = payload.get("coordinates")
        if not isinstance(raw, (list, tuple)) or len(raw) != 3:
            raise ValueError(f"node {node_id} coordinates must contain three values")
        coordinates = tuple(
            _finite_float(value, field_name=f"node {node_id} coordinates")
            for value in raw
        )
        return cls(
            id=node_id,
            coordinates=coordinates,  # type: ignore[arg-type]
            extras_json=_extras_json(payload, {"id", "coordinates"}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "coordinates": list(self.coordinates),
            **_extras_payload(self.extras_json),
        }


@dataclass(frozen=True)
class NodalLoad(CanonicalEntity):
    entity_kind: ClassVar[str] = "nodal_load"
    node: str
    components: tuple[float, float, float, float, float, float]
    load_case: str | None = None
    extras_json: str = field(default="{}", repr=False)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "NodalLoad":
        node = _nonempty_text(
            payload.get("node", payload.get("node_id")),
            field_name="load.node",
        )
        raw = payload.get("components")
        if isinstance(raw, Mapping):
            values = [
                raw.get(label, raw.get(label.lower(), 0.0))
                for label in LOAD_COMPONENT_LABELS
            ]
        elif isinstance(raw, (list, tuple)) and len(raw) in {3, 6}:
            values = list(raw)
            if len(values) == 3:
                values.extend([0.0, 0.0, 0.0])
        elif raw is None:
            values = [
                payload.get(label, payload.get(label.lower(), 0.0))
                for label in LOAD_COMPONENT_LABELS
            ]
        else:
            raise ValueError("load.components must be a mapping or 3/6-value sequence")
        components = tuple(
            _finite_float(value, field_name=f"load.{label}")
            for label, value in zip(LOAD_COMPONENT_LABELS, values, strict=True)
        )
        raw_case = payload.get("load_case", payload.get("case"))
        load_case = str(raw_case).strip() if raw_case is not None else None
        load_case = load_case or None
        known = {
            "node",
            "node_id",
            "components",
            "load_case",
            "case",
            *LOAD_COMPONENT_LABELS,
            *(label.lower() for label in LOAD_COMPONENT_LABELS),
        }
        return cls(
            node=node,
            components=components,  # type: ignore[arg-type]
            load_case=load_case,
            extras_json=_extras_json(payload, known),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "node": self.node,
            "components": {
                label: self.components[index]
                for index, label in enumerate(LOAD_COMPONENT_LABELS)
            },
            **_extras_payload(self.extras_json),
        }
        if self.load_case is not None:
            payload["load_case"] = self.load_case
        return payload


@dataclass(frozen=True)
class Support(CanonicalEntity):
    entity_kind: ClassVar[str] = "support"
    node: str
    dofs: tuple[str, ...]
    all_dofs: bool = False
    extras_json: str = field(default="{}", repr=False)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "Support":
        node = _nonempty_text(
            payload.get("node", payload.get("node_id")),
            field_name="support.node",
        )
        raw = payload.get("dofs", payload.get("restrained_dofs", []))
        all_dofs = raw == "all"
        if all_dofs:
            dofs = FRAME_DOF_LABELS
        elif isinstance(raw, (list, tuple)):
            dofs = tuple(str(value).strip().upper() for value in raw)
        else:
            raise ValueError("support.dofs must be 'all' or a sequence")
        invalid = [dof for dof in dofs if dof not in FRAME_DOF_LABELS]
        if invalid:
            raise ValueError(f"support {node} has unsupported DOFs: {invalid}")
        return cls(
            node=node,
            dofs=dofs,
            all_dofs=all_dofs,
            extras_json=_extras_json(
                payload,
                {"node", "node_id", "dofs", "restrained_dofs"},
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "dofs": "all" if self.all_dofs else list(self.dofs),
            **_extras_payload(self.extras_json),
        }


@dataclass(frozen=True)
class ElasticMaterial(CanonicalEntity):
    entity_kind: ClassVar[str] = "elastic_material"
    id: str
    elastic_modulus: float
    poisson_ratio: float | None = None
    density: float | None = None
    material_type: str = "elastic"
    loading_domain: str = "finite_linear_elastic_3d"
    supports_monotonic: bool = True
    supports_unloading: bool = True
    supports_reversal: bool = True
    supports_cyclic: bool = True
    supports_tension: bool = True
    supports_compression: bool = True
    supports_multiaxial: bool = True
    supports_localization_regularization: bool = False
    extras_json: str = field(default="{}", repr=False)

    @property
    def admissibility(self) -> MaterialAdmissibility:
        return MaterialAdmissibility(
            loading_domain=self.loading_domain,
            supports_monotonic=self.supports_monotonic,
            supports_unloading=self.supports_unloading,
            supports_reversal=self.supports_reversal,
            supports_cyclic=self.supports_cyclic,
            supports_tension=self.supports_tension,
            supports_compression=self.supports_compression,
            supports_multiaxial=self.supports_multiaxial,
            supports_localization_regularization=(
                self.supports_localization_regularization
            ),
        )

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ElasticMaterial":
        material_id = _nonempty_text(payload.get("id"), field_name="material.id")
        material_type = str(payload.get("type", "elastic") or "elastic").strip()
        if material_type.lower() != "elastic":
            raise ValueError(
                f"material {material_id} is not an elastic material: {material_type}"
            )
        modulus = payload.get("elastic_modulus", payload.get("E_kN_per_m2"))
        return cls(
            id=material_id,
            material_type=material_type,
            elastic_modulus=_finite_float(
                modulus,
                field_name=f"material {material_id} elastic_modulus",
            ),
            poisson_ratio=_optional_finite_float(
                payload.get("poisson_ratio"),
                field_name=f"material {material_id} poisson_ratio",
            ),
            density=_optional_finite_float(
                payload.get("density"),
                field_name=f"material {material_id} density",
            ),
            extras_json=_extras_json(
                payload,
                {
                    "id",
                    "type",
                    "elastic_modulus",
                    "E_kN_per_m2",
                    "poisson_ratio",
                    "density",
                },
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.material_type,
            "elastic_modulus": self.elastic_modulus,
            **_extras_payload(self.extras_json),
        }
        if self.poisson_ratio is not None:
            payload["poisson_ratio"] = self.poisson_ratio
        if self.density is not None:
            payload["density"] = self.density
        return payload


@dataclass(frozen=True)
class FrameSection(CanonicalEntity):
    entity_kind: ClassVar[str] = "frame_section"
    id: str
    section_type: str
    area: float | None = None
    iy: float | None = None
    iz: float | None = None
    torsional_constant: float | None = None
    extras_json: str = field(default="{}", repr=False)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FrameSection":
        section_id = _nonempty_text(payload.get("id"), field_name="section.id")
        section_type = str(payload.get("type", "frame") or "frame").strip()
        return cls(
            id=section_id,
            section_type=section_type,
            area=_optional_finite_float(
                payload.get("area", payload.get("A_m2")),
                field_name=f"section {section_id} area",
            ),
            iy=_optional_finite_float(
                payload.get("iy", payload.get("Iy_m4")),
                field_name=f"section {section_id} iy",
            ),
            iz=_optional_finite_float(
                payload.get("iz", payload.get("Iz_m4")),
                field_name=f"section {section_id} iz",
            ),
            torsional_constant=_optional_finite_float(
                payload.get("torsional_constant", payload.get("J_m4")),
                field_name=f"section {section_id} torsional_constant",
            ),
            extras_json=_extras_json(
                payload,
                {
                    "id",
                    "type",
                    "area",
                    "A_m2",
                    "iy",
                    "Iy_m4",
                    "iz",
                    "Iz_m4",
                    "torsional_constant",
                    "J_m4",
                },
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.section_type,
            **_extras_payload(self.extras_json),
        }
        for key, value in (
            ("area", self.area),
            ("iy", self.iy),
            ("iz", self.iz),
            ("torsional_constant", self.torsional_constant),
        ):
            if value is not None:
                payload[key] = value
        return payload


@dataclass(frozen=True)
class FrameElement(CanonicalEntity):
    entity_kind: ClassVar[str] = "frame_element"
    id: str
    nodes: tuple[str, str]
    section: str
    material: str
    element_type: str = "frame"
    local_axis_angle_deg: float | None = None
    extras_json: str = field(default="{}", repr=False)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "FrameElement":
        element_id = _nonempty_text(payload.get("id"), field_name="element.id")
        raw_nodes = payload.get("nodes")
        if not isinstance(raw_nodes, (list, tuple)) or len(raw_nodes) != 2:
            raise ValueError(f"frame element {element_id} must reference two nodes")
        element_type = str(payload.get("type", "frame") or "frame").strip()
        if element_type.lower() not in {"frame", "beam", "column"}:
            raise ValueError(
                f"element {element_id} is not a frame-family element: {element_type}"
            )
        raw_angle = payload.get(
            "local_axis_angle_deg",
            payload.get("angle_deg"),
        )
        return cls(
            id=element_id,
            nodes=(
                _nonempty_text(raw_nodes[0], field_name=f"element {element_id} node I"),
                _nonempty_text(raw_nodes[1], field_name=f"element {element_id} node J"),
            ),
            section=_nonempty_text(
                payload.get("section"),
                field_name=f"element {element_id} section",
            ),
            material=_nonempty_text(
                payload.get("material"),
                field_name=f"element {element_id} material",
            ),
            element_type=element_type,
            local_axis_angle_deg=_optional_finite_float(
                raw_angle,
                field_name=f"element {element_id} local_axis_angle_deg",
            ),
            extras_json=_extras_json(
                payload,
                {
                    "id",
                    "nodes",
                    "section",
                    "material",
                    "type",
                    "local_axis_angle_deg",
                    "angle_deg",
                },
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "type": self.element_type,
            "nodes": list(self.nodes),
            "section": self.section,
            "material": self.material,
            **_extras_payload(self.extras_json),
        }
        if self.local_axis_angle_deg is not None:
            payload["local_axis_angle_deg"] = self.local_axis_angle_deg
        return payload


@dataclass(frozen=True)
class TypedModelEntities:
    nodes: tuple[Node, ...]
    loads: tuple[NodalLoad, ...]
    supports: tuple[Support, ...]
    elastic_materials: tuple[ElasticMaterial, ...]
    frame_sections: tuple[FrameSection, ...]
    frame_elements: tuple[FrameElement, ...]


def typed_model_entities(
    *,
    nodes: list[dict[str, Any]],
    loads: list[dict[str, Any]],
    supports: list[dict[str, Any]],
    materials: list[dict[str, Any]],
    sections: list[dict[str, Any]],
    elements: list[dict[str, Any]],
) -> TypedModelEntities:
    return TypedModelEntities(
        nodes=tuple(Node.from_mapping(row) for row in nodes),
        loads=tuple(NodalLoad.from_mapping(row) for row in loads),
        supports=tuple(Support.from_mapping(row) for row in supports),
        elastic_materials=tuple(
            ElasticMaterial.from_mapping(row)
            for row in materials
            if str(row.get("type", "elastic")).lower() == "elastic"
        ),
        frame_sections=tuple(FrameSection.from_mapping(row) for row in sections),
        frame_elements=tuple(
            FrameElement.from_mapping(row)
            for row in elements
            if str(row.get("type", "")).lower() in {"frame", "beam", "column"}
        ),
    )


def to_legacy_mapping(entity: CanonicalEntity) -> dict[str, Any]:
    """Return a fresh JSON-compatible mapping for legacy dict consumers."""

    return entity.to_dict()
