#!/usr/bin/env python3
"""Pragmatic section-library and meshing scaffold for productization work.

This module does not try to be a full CAD/FE mesher. It provides:

- a typed section catalog with placeholder steel/RC/composite templates
- JSON-friendly catalog loading and serialization helpers
- mesh request validation and deterministic meshing summary estimates
- load pattern editor draft objects that other modules can serialize/consume

The goal is to give upcoming UI, interoperability, and solver modules a stable
data contract before the full authoring stack exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path
from typing import Any


SECTION_FAMILIES = {"steel", "rc", "composite"}
SECTION_SHAPES = {
    "h_beam",
    "box",
    "pipe",
    "rect_column",
    "wall_strip",
    "slab_strip",
    "cft_box",
    "src_beam",
    "composite_deck_beam",
}
ELEMENT_KINDS = {"frame", "fiber_section", "shell", "solid"}
LOAD_PRIMITIVE_KINDS = {"self_weight", "surface_pressure", "line_load", "point_load", "temperature", "displacement"}
AUTHORING_MEMBER_TYPES = {"beam", "column", "brace", "wall", "slab", "foundation", "connection", "generic_frame"}


def _safe_positive(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _safe_nonnegative(value: float, *, field_name: str) -> float:
    numeric = float(value)
    if numeric < 0.0:
        raise ValueError(f"{field_name} must be nonnegative")
    return numeric


def _sorted_unique_text(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))


@dataclass(frozen=True)
class SectionTemplate:
    section_id: str
    family: str
    shape: str
    material_grade: str
    dimensions_m: dict[str, float]
    default_mesh_size_m: float
    placeholder_analysis_kind: str
    tags: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def __post_init__(self) -> None:
        if self.family not in SECTION_FAMILIES:
            raise ValueError(f"unsupported family: {self.family}")
        if self.shape not in SECTION_SHAPES:
            raise ValueError(f"unsupported shape: {self.shape}")
        if not str(self.section_id).strip():
            raise ValueError("section_id is required")
        if not str(self.material_grade).strip():
            raise ValueError("material_grade is required")
        if not str(self.placeholder_analysis_kind).strip():
            raise ValueError("placeholder_analysis_kind is required")
        object.__setattr__(self, "section_id", str(self.section_id).strip())
        object.__setattr__(self, "material_grade", str(self.material_grade).strip())
        object.__setattr__(self, "placeholder_analysis_kind", str(self.placeholder_analysis_kind).strip())
        object.__setattr__(self, "notes", str(self.notes).strip())
        object.__setattr__(self, "tags", _sorted_unique_text(self.tags))

        cleaned_dimensions: dict[str, float] = {}
        for key, value in self.dimensions_m.items():
            normalized_key = str(key).strip()
            if not normalized_key:
                continue
            cleaned_dimensions[normalized_key] = _safe_positive(float(value), field_name=f"dimensions_m.{normalized_key}")
        if not cleaned_dimensions:
            raise ValueError("dimensions_m must contain at least one positive value")
        object.__setattr__(self, "dimensions_m", cleaned_dimensions)
        object.__setattr__(self, "default_mesh_size_m", _safe_positive(self.default_mesh_size_m, field_name="default_mesh_size_m"))

    @property
    def width_m(self) -> float:
        return float(
            self.dimensions_m.get("width_m")
            or self.dimensions_m.get("flange_width_m")
            or self.dimensions_m.get("diameter_m")
            or self.dimensions_m.get("deck_width_m")
            or 0.0
        )

    @property
    def depth_m(self) -> float:
        return float(
            self.dimensions_m.get("depth_m")
            or self.dimensions_m.get("wall_length_m")
            or self.dimensions_m.get("diameter_m")
            or self.dimensions_m.get("slab_width_m")
            or 0.0
        )

    @property
    def thickness_m(self) -> float:
        return float(
            self.dimensions_m.get("thickness_m")
            or self.dimensions_m.get("wall_thickness_m")
            or self.dimensions_m.get("flange_thickness_m")
            or self.dimensions_m.get("deck_thickness_m")
            or 0.0
        )

    def planar_extents_m(self) -> tuple[float, float]:
        long_dim = max(self.width_m, self.depth_m, self.thickness_m, self.default_mesh_size_m)
        short_dim = max(min(value for value in (self.width_m, self.depth_m, self.thickness_m) if value > 0.0), self.default_mesh_size_m)
        return float(long_dim), float(short_dim)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectionCatalog:
    version: str
    source_label: str
    templates: tuple[SectionTemplate, ...]

    def __post_init__(self) -> None:
        if not str(self.version).strip():
            raise ValueError("version is required")
        if not str(self.source_label).strip():
            raise ValueError("source_label is required")
        ids = [row.section_id for row in self.templates]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate section_id in catalog")
        object.__setattr__(self, "version", str(self.version).strip())
        object.__setattr__(self, "source_label", str(self.source_label).strip())

    def template_ids(self) -> tuple[str, ...]:
        return tuple(row.section_id for row in self.templates)

    def get_template(self, section_id: str) -> SectionTemplate:
        normalized = str(section_id).strip()
        for row in self.templates:
            if row.section_id == normalized:
                return row
        raise KeyError(f"unknown section_id: {section_id}")

    def family_counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in self.templates:
            out[row.family] = int(out.get(row.family, 0) + 1)
        return out

    def to_payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_label": self.source_label,
            "template_count": len(self.templates),
            "family_counts": self.family_counts(),
            "templates": [row.to_payload() for row in self.templates],
        }


@dataclass(frozen=True)
class MeshRefinementPoint:
    x_ratio: float
    y_ratio: float
    radius_ratio: float = 0.15

    def __post_init__(self) -> None:
        for name in ("x_ratio", "y_ratio", "radius_ratio"):
            value = float(getattr(self, name))
            if name == "radius_ratio":
                if value <= 0.0:
                    raise ValueError("radius_ratio must be positive")
            elif not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")

    def to_payload(self) -> dict[str, float]:
        return {"x_ratio": float(self.x_ratio), "y_ratio": float(self.y_ratio), "radius_ratio": float(self.radius_ratio)}


@dataclass(frozen=True)
class MeshRequest:
    request_id: str
    section_id: str
    element_kind: str
    target_edge_length_m: float | None = None
    minimum_divisions: int = 4
    through_thickness_layers: int = 1
    refinement_points: tuple[MeshRefinementPoint, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.request_id).strip():
            raise ValueError("request_id is required")
        if not str(self.section_id).strip():
            raise ValueError("section_id is required")
        if self.element_kind not in ELEMENT_KINDS:
            raise ValueError(f"unsupported element_kind: {self.element_kind}")
        if int(self.minimum_divisions) < 1:
            raise ValueError("minimum_divisions must be >= 1")
        if int(self.through_thickness_layers) < 1:
            raise ValueError("through_thickness_layers must be >= 1")
        if self.target_edge_length_m is not None:
            _safe_positive(self.target_edge_length_m, field_name="target_edge_length_m")
        object.__setattr__(self, "request_id", str(self.request_id).strip())
        object.__setattr__(self, "section_id", str(self.section_id).strip())
        object.__setattr__(self, "minimum_divisions", int(self.minimum_divisions))
        object.__setattr__(self, "through_thickness_layers", int(self.through_thickness_layers))
        object.__setattr__(self, "refinement_points", tuple(self.refinement_points))

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "section_id": self.section_id,
            "element_kind": self.element_kind,
            "target_edge_length_m": None if self.target_edge_length_m is None else float(self.target_edge_length_m),
            "minimum_divisions": int(self.minimum_divisions),
            "through_thickness_layers": int(self.through_thickness_layers),
            "refinement_points": [point.to_payload() for point in self.refinement_points],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MeshPlanSummary:
    request_id: str
    section_id: str
    family: str
    element_kind: str
    divisions_long: int
    divisions_short: int
    through_thickness_layers: int
    estimated_cell_count: int
    target_edge_length_m: float
    local_refinement_count: int

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoadPrimitive:
    kind: str
    case_name: str
    target_scope: str
    magnitude: float
    direction: str = "global_z"
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in LOAD_PRIMITIVE_KINDS:
            raise ValueError(f"unsupported load primitive kind: {self.kind}")
        if not str(self.case_name).strip():
            raise ValueError("case_name is required")
        if not str(self.target_scope).strip():
            raise ValueError("target_scope is required")
        if self.kind != "self_weight":
            _safe_nonnegative(abs(float(self.magnitude)), field_name="magnitude")
        object.__setattr__(self, "case_name", str(self.case_name).strip())
        object.__setattr__(self, "target_scope", str(self.target_scope).strip())
        object.__setattr__(self, "direction", str(self.direction).strip() or "global_z")
        object.__setattr__(self, "notes", str(self.notes).strip())

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class LoadPatternDraft:
    pattern_id: str
    label: str
    design_situation: str
    primitives: tuple[LoadPrimitive, ...]
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not str(self.pattern_id).strip():
            raise ValueError("pattern_id is required")
        if not str(self.label).strip():
            raise ValueError("label is required")
        if not str(self.design_situation).strip():
            raise ValueError("design_situation is required")
        if not self.primitives:
            raise ValueError("at least one load primitive is required")
        object.__setattr__(self, "pattern_id", str(self.pattern_id).strip())
        object.__setattr__(self, "label", str(self.label).strip())
        object.__setattr__(self, "design_situation", str(self.design_situation).strip())
        object.__setattr__(self, "tags", _sorted_unique_text(self.tags))

    def primitive_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.primitives:
            counts[item.kind] = int(counts.get(item.kind, 0) + 1)
        return counts

    def to_payload(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "label": self.label,
            "design_situation": self.design_situation,
            "primitive_count": len(self.primitives),
            "primitive_counts": self.primitive_counts(),
            "tags": list(self.tags),
            "primitives": [item.to_payload() for item in self.primitives],
        }


@dataclass(frozen=True)
class StoryLevel:
    story_id: str
    elevation_m: float
    height_m: float
    label: str = ""

    def __post_init__(self) -> None:
        if not str(self.story_id).strip():
            raise ValueError("story_id is required")
        object.__setattr__(self, "story_id", str(self.story_id).strip())
        object.__setattr__(self, "label", str(self.label).strip() or str(self.story_id))
        object.__setattr__(self, "elevation_m", float(self.elevation_m))
        object.__setattr__(self, "height_m", _safe_positive(self.height_m, field_name="height_m"))

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NodeDraft:
    node_id: str
    x_m: float
    y_m: float
    z_m: float
    story_id: str = ""

    def __post_init__(self) -> None:
        if not str(self.node_id).strip():
            raise ValueError("node_id is required")
        object.__setattr__(self, "node_id", str(self.node_id).strip())
        object.__setattr__(self, "story_id", str(self.story_id).strip())
        object.__setattr__(self, "x_m", float(self.x_m))
        object.__setattr__(self, "y_m", float(self.y_m))
        object.__setattr__(self, "z_m", float(self.z_m))

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MemberDraft:
    member_id: str
    member_type: str
    start_node_id: str
    end_node_id: str
    section_id: str
    analysis_kind: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not str(self.member_id).strip():
            raise ValueError("member_id is required")
        if self.member_type not in AUTHORING_MEMBER_TYPES:
            raise ValueError(f"unsupported member_type: {self.member_type}")
        if not str(self.start_node_id).strip() or not str(self.end_node_id).strip():
            raise ValueError("member node ids are required")
        if not str(self.section_id).strip():
            raise ValueError("section_id is required")
        object.__setattr__(self, "member_id", str(self.member_id).strip())
        object.__setattr__(self, "start_node_id", str(self.start_node_id).strip())
        object.__setattr__(self, "end_node_id", str(self.end_node_id).strip())
        object.__setattr__(self, "section_id", str(self.section_id).strip())
        object.__setattr__(self, "analysis_kind", str(self.analysis_kind).strip())
        object.__setattr__(self, "tags", _sorted_unique_text(self.tags))

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuthoringModelDraft:
    model_id: str
    story_levels: tuple[StoryLevel, ...]
    nodes: tuple[NodeDraft, ...]
    members: tuple[MemberDraft, ...]
    load_patterns: tuple[LoadPatternDraft, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.model_id).strip():
            raise ValueError("model_id is required")
        story_ids = [row.story_id for row in self.story_levels]
        node_ids = [row.node_id for row in self.nodes]
        member_ids = [row.member_id for row in self.members]
        if len(story_ids) != len(set(story_ids)):
            raise ValueError("duplicate story_id in authoring model")
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("duplicate node_id in authoring model")
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("duplicate member_id in authoring model")
        object.__setattr__(self, "model_id", str(self.model_id).strip())

    def to_payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "story_levels": [row.to_payload() for row in self.story_levels],
            "nodes": [row.to_payload() for row in self.nodes],
            "members": [row.to_payload() for row in self.members],
            "load_patterns": [row.to_payload() for row in self.load_patterns],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AuthoringBundleSummary:
    model_id: str
    story_count: int
    node_count: int
    member_count: int
    load_pattern_count: int
    section_usage_counts: dict[str, int]
    member_type_counts: dict[str, int]
    unsupported_section_ids: tuple[str, ...]
    unresolved_node_refs: tuple[str, ...]
    orphan_story_node_count: int
    max_member_span_m: float
    bounding_box_m: dict[str, float]
    native_authoring_ready: bool
    solver_ready_score: float
    summary_line: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "story_count": int(self.story_count),
            "node_count": int(self.node_count),
            "member_count": int(self.member_count),
            "load_pattern_count": int(self.load_pattern_count),
            "section_usage_counts": {str(k): int(v) for k, v in sorted(self.section_usage_counts.items())},
            "member_type_counts": {str(k): int(v) for k, v in sorted(self.member_type_counts.items())},
            "unsupported_section_ids": list(self.unsupported_section_ids),
            "unresolved_node_refs": list(self.unresolved_node_refs),
            "orphan_story_node_count": int(self.orphan_story_node_count),
            "max_member_span_m": float(self.max_member_span_m),
            "bounding_box_m": {str(k): float(v) for k, v in sorted(self.bounding_box_m.items())},
            "native_authoring_ready": bool(self.native_authoring_ready),
            "solver_ready_score": float(self.solver_ready_score),
            "summary_line": str(self.summary_line),
        }


def default_section_templates() -> tuple[SectionTemplate, ...]:
    """Return a small but realistic starter catalog."""

    return (
        SectionTemplate(
            section_id="steel_h_600x200",
            family="steel",
            shape="h_beam",
            material_grade="SM490",
            dimensions_m={"depth_m": 0.600, "flange_width_m": 0.200, "web_thickness_m": 0.011, "flange_thickness_m": 0.017},
            default_mesh_size_m=0.050,
            placeholder_analysis_kind="frame_fiber_ready",
            tags=("beam", "rolled"),
            notes="Starter steel H-beam placeholder for building frame members.",
        ),
        SectionTemplate(
            section_id="steel_box_400x400x16",
            family="steel",
            shape="box",
            material_grade="SM570",
            dimensions_m={"width_m": 0.400, "depth_m": 0.400, "thickness_m": 0.016},
            default_mesh_size_m=0.040,
            placeholder_analysis_kind="frame_shell_hybrid",
            tags=("column", "tube"),
        ),
        SectionTemplate(
            section_id="rc_column_700x700",
            family="rc",
            shape="rect_column",
            material_grade="C40/SD500",
            dimensions_m={"width_m": 0.700, "depth_m": 0.700, "cover_m": 0.050},
            default_mesh_size_m=0.060,
            placeholder_analysis_kind="fiber_section",
            tags=("column", "ductile_frame"),
        ),
        SectionTemplate(
            section_id="rc_wall_300x3000",
            family="rc",
            shape="wall_strip",
            material_grade="C35/SD400",
            dimensions_m={"wall_length_m": 3.000, "wall_thickness_m": 0.300},
            default_mesh_size_m=0.120,
            placeholder_analysis_kind="layered_shell_wall",
            tags=("wall", "core"),
        ),
        SectionTemplate(
            section_id="cft_box_700x700",
            family="composite",
            shape="cft_box",
            material_grade="SM570+C50",
            dimensions_m={"width_m": 0.700, "depth_m": 0.700, "thickness_m": 0.020},
            default_mesh_size_m=0.050,
            placeholder_analysis_kind="composite_fiber_section",
            tags=("mega_column", "cft"),
        ),
        SectionTemplate(
            section_id="deck_beam_500x250",
            family="composite",
            shape="composite_deck_beam",
            material_grade="SM490+C30",
            dimensions_m={"depth_m": 0.500, "deck_width_m": 2.500, "deck_thickness_m": 0.120},
            default_mesh_size_m=0.080,
            placeholder_analysis_kind="beam_shell_composite",
            tags=("floor", "deck"),
        ),
    )


def build_default_section_catalog(*, version: str = "0.1.0", source_label: str = "phase1_scaffold") -> SectionCatalog:
    return SectionCatalog(version=version, source_label=source_label, templates=default_section_templates())


def catalog_from_payload(payload: dict[str, Any]) -> SectionCatalog:
    templates_payload = payload.get("templates") if isinstance(payload.get("templates"), list) else []
    templates = tuple(
        SectionTemplate(
            section_id=str(row.get("section_id", "") or ""),
            family=str(row.get("family", "") or ""),
            shape=str(row.get("shape", "") or ""),
            material_grade=str(row.get("material_grade", "") or ""),
            dimensions_m={str(k): float(v) for k, v in (row.get("dimensions_m") or {}).items()},
            default_mesh_size_m=float(row.get("default_mesh_size_m", 0.0) or 0.0),
            placeholder_analysis_kind=str(row.get("placeholder_analysis_kind", "") or ""),
            tags=tuple(str(item) for item in (row.get("tags") or [])),
            notes=str(row.get("notes", "") or ""),
        )
        for row in templates_payload
        if isinstance(row, dict)
    )
    return SectionCatalog(
        version=str(payload.get("version", "") or ""),
        source_label=str(payload.get("source_label", "") or ""),
        templates=templates,
    )


def load_section_catalog(source: str | Path | dict[str, Any] | None = None) -> SectionCatalog:
    """Load a section catalog from JSON payload/path or fall back to defaults."""

    if source is None:
        return build_default_section_catalog()
    if isinstance(source, dict):
        return catalog_from_payload(source)
    path = Path(source)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("catalog payload must be a JSON object")
    return catalog_from_payload(payload)


def validate_mesh_request(*, catalog: SectionCatalog, request: MeshRequest) -> MeshPlanSummary:
    template = catalog.get_template(request.section_id)
    long_dim, short_dim = template.planar_extents_m()
    edge_length = float(request.target_edge_length_m or template.default_mesh_size_m)
    edge_length = _safe_positive(edge_length, field_name="target_edge_length_m")
    long_divisions = max(int(request.minimum_divisions), int(math.ceil(long_dim / edge_length)))
    short_divisions = max(int(request.minimum_divisions), int(math.ceil(short_dim / edge_length)))
    thickness_layers = int(request.through_thickness_layers)
    if request.element_kind == "frame":
        estimated_cells = max(long_divisions, short_divisions)
        thickness_layers = 1
    elif request.element_kind == "shell":
        estimated_cells = long_divisions * short_divisions
        thickness_layers = 1
    else:
        estimated_cells = long_divisions * short_divisions * thickness_layers
    if request.refinement_points:
        estimated_cells = int(math.ceil(estimated_cells * (1.0 + 0.15 * len(request.refinement_points))))
    return MeshPlanSummary(
        request_id=request.request_id,
        section_id=template.section_id,
        family=template.family,
        element_kind=request.element_kind,
        divisions_long=long_divisions,
        divisions_short=short_divisions,
        through_thickness_layers=thickness_layers,
        estimated_cell_count=int(max(1, estimated_cells)),
        target_edge_length_m=edge_length,
        local_refinement_count=len(request.refinement_points),
    )


def build_load_pattern_summary(patterns: list[LoadPatternDraft] | tuple[LoadPatternDraft, ...]) -> dict[str, Any]:
    counts_by_kind: dict[str, int] = {}
    counts_by_case: dict[str, int] = {}
    for pattern in patterns:
        for primitive in pattern.primitives:
            counts_by_kind[primitive.kind] = int(counts_by_kind.get(primitive.kind, 0) + 1)
            counts_by_case[primitive.case_name] = int(counts_by_case.get(primitive.case_name, 0) + 1)
    return {
        "pattern_count": len(patterns),
        "primitive_count": int(sum(counts_by_kind.values())),
        "primitive_kind_counts": dict(sorted(counts_by_kind.items())),
        "case_counts": dict(sorted(counts_by_case.items())),
        "patterns": [pattern.to_payload() for pattern in patterns],
    }


def build_authoring_bundle_summary(
    *,
    catalog: SectionCatalog,
    model: AuthoringModelDraft,
) -> AuthoringBundleSummary:
    node_lookup = {row.node_id: row for row in model.nodes}
    story_ids = {row.story_id for row in model.story_levels}
    section_usage_counts: dict[str, int] = {}
    member_type_counts: dict[str, int] = {}
    unsupported_sections: list[str] = []
    unresolved_node_refs: list[str] = []
    max_span_m = 0.0

    orphan_story_node_count = sum(
        1
        for node in model.nodes
        if node.story_id and node.story_id not in story_ids
    )

    for member in model.members:
        member_type_counts[member.member_type] = int(member_type_counts.get(member.member_type, 0) + 1)
        section_usage_counts[member.section_id] = int(section_usage_counts.get(member.section_id, 0) + 1)
        try:
            catalog.get_template(member.section_id)
        except KeyError:
            unsupported_sections.append(member.section_id)
        start = node_lookup.get(member.start_node_id)
        end = node_lookup.get(member.end_node_id)
        if start is None or end is None:
            unresolved_node_refs.append(member.member_id)
            continue
        dx = float(end.x_m) - float(start.x_m)
        dy = float(end.y_m) - float(start.y_m)
        dz = float(end.z_m) - float(start.z_m)
        max_span_m = max(max_span_m, math.sqrt(dx * dx + dy * dy + dz * dz))

    if model.nodes:
        xs = [float(node.x_m) for node in model.nodes]
        ys = [float(node.y_m) for node in model.nodes]
        zs = [float(node.z_m) for node in model.nodes]
        bounding_box = {
            "x_span_m": max(xs) - min(xs),
            "y_span_m": max(ys) - min(ys),
            "z_span_m": max(zs) - min(zs),
        }
    else:
        bounding_box = {"x_span_m": 0.0, "y_span_m": 0.0, "z_span_m": 0.0}

    unique_unsupported = tuple(sorted(set(unsupported_sections)))
    unique_unresolved = tuple(sorted(set(unresolved_node_refs)))
    section_coverage_ratio = 1.0 - (len(unique_unsupported) / max(len(section_usage_counts), 1))
    node_ref_ratio = 1.0 - (len(unique_unresolved) / max(len(model.members), 1))
    story_ratio = 1.0 - (orphan_story_node_count / max(len(model.nodes), 1))
    load_ratio = 1.0 if model.load_patterns else 0.6
    solver_ready_score = 100.0 * (
        0.35 * section_coverage_ratio
        + 0.35 * node_ref_ratio
        + 0.15 * story_ratio
        + 0.15 * load_ratio
    )
    native_authoring_ready = bool(
        model.members
        and model.nodes
        and not unique_unsupported
        and not unique_unresolved
        and orphan_story_node_count == 0
    )
    summary_line = (
        f"Native authoring bundle: {'PASS' if native_authoring_ready else 'CHECK'} | "
        f"stories={len(model.story_levels)} | nodes={len(model.nodes)} | members={len(model.members)} | "
        f"loads={len(model.load_patterns)} | unsupported={len(unique_unsupported)} | "
        f"unresolved={len(unique_unresolved)} | score={solver_ready_score:.1f}"
    )
    return AuthoringBundleSummary(
        model_id=model.model_id,
        story_count=len(model.story_levels),
        node_count=len(model.nodes),
        member_count=len(model.members),
        load_pattern_count=len(model.load_patterns),
        section_usage_counts=section_usage_counts,
        member_type_counts=member_type_counts,
        unsupported_section_ids=unique_unsupported,
        unresolved_node_refs=unique_unresolved,
        orphan_story_node_count=int(orphan_story_node_count),
        max_member_span_m=float(max_span_m),
        bounding_box_m=bounding_box,
        native_authoring_ready=bool(native_authoring_ready),
        solver_ready_score=float(solver_ready_score),
        summary_line=summary_line,
    )


def export_scaffold_summary(
    *,
    catalog: SectionCatalog,
    mesh_requests: list[MeshRequest] | tuple[MeshRequest, ...] = (),
    load_patterns: list[LoadPatternDraft] | tuple[LoadPatternDraft, ...] = (),
    authoring_model: AuthoringModelDraft | None = None,
) -> dict[str, Any]:
    mesh_plans = [validate_mesh_request(catalog=catalog, request=request).to_payload() for request in mesh_requests]
    authoring_summary = (
        build_authoring_bundle_summary(catalog=catalog, model=authoring_model).to_payload()
        if isinstance(authoring_model, AuthoringModelDraft)
        else {}
    )
    return {
        "catalog": catalog.to_payload(),
        "mesh_requests": [request.to_payload() for request in mesh_requests],
        "mesh_plan_summaries": mesh_plans,
        "load_pattern_summary": build_load_pattern_summary(load_patterns),
        "authoring_model_summary": authoring_summary,
    }


__all__ = [
    "ELEMENT_KINDS",
    "LOAD_PRIMITIVE_KINDS",
    "AUTHORING_MEMBER_TYPES",
    "AuthoringBundleSummary",
    "AuthoringModelDraft",
    "SECTION_FAMILIES",
    "SECTION_SHAPES",
    "LoadPatternDraft",
    "LoadPrimitive",
    "MemberDraft",
    "MeshPlanSummary",
    "MeshRefinementPoint",
    "MeshRequest",
    "NodeDraft",
    "SectionCatalog",
    "SectionTemplate",
    "StoryLevel",
    "build_authoring_bundle_summary",
    "build_default_section_catalog",
    "build_load_pattern_summary",
    "catalog_from_payload",
    "default_section_templates",
    "export_scaffold_summary",
    "load_section_catalog",
    "validate_mesh_request",
]
