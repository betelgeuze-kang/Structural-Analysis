#!/usr/bin/env python3
"""Generate a deterministic native authoring workspace summary artifact."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.section_library_and_mesher import (
        AuthoringModelDraft,
        LoadPatternDraft,
        LoadPrimitive,
        MemberDraft,
        NodeDraft,
        StoryLevel,
        build_authoring_bundle_summary,
        build_default_section_catalog,
    )
except ImportError:  # pragma: no cover
    from section_library_and_mesher import (  # type: ignore
        AuthoringModelDraft,
        LoadPatternDraft,
        LoadPrimitive,
        MemberDraft,
        NodeDraft,
        StoryLevel,
        build_authoring_bundle_summary,
        build_default_section_catalog,
    )


DEFAULT_OUT = Path("implementation/phase1/release/authoring/native_authoring_workspace_summary.json")

DEFAULT_STORY_COUNT = 5
DEFAULT_BAY_COUNT = 3
DEFAULT_FLOOR_HEIGHT_M = 3.9
DEFAULT_LOAD_PATTERN_COUNT = 4
DEFAULT_SECTION_ID = "steel_h_600x200"
DEFAULT_BAY_WIDTH_M = 8.0
DEFAULT_FAMILY_ID = "sample_tower"

_MAX_STORY_COUNT = 40
_MAX_BAY_COUNT = 12
_MAX_LOAD_PATTERN_COUNT = 12
_MIN_FLOOR_HEIGHT_M = 2.5
_MAX_FLOOR_HEIGHT_M = 6.0
_CONTROL_KEYS = (
    "familyId",
    "family_id",
    "authoringFamilyId",
    "authoring_family_id",
    "storyCount",
    "story_count",
    "bayCount",
    "bay_count",
    "floorHeightM",
    "floor_height_m",
    "loadPatternCount",
    "load_pattern_count",
    "sectionId",
    "section_id",
    "default_section_id",
)


@dataclass(frozen=True)
class NativeAuthoringFamilyTemplate:
    family_id: str
    label: str
    description: str
    default_section_id: str
    preferred_design_family: str
    default_bay_width_m: float
    default_story_count: int
    default_bay_count: int
    default_floor_height_m: float
    default_load_pattern_count: int
    representative_member_types: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "family_id": str(self.family_id),
            "label": str(self.label),
            "description": str(self.description),
            "default_section_id": str(self.default_section_id),
            "preferred_design_family": str(self.preferred_design_family),
            "default_bay_width_m": float(self.default_bay_width_m),
            "default_story_count": int(self.default_story_count),
            "default_bay_count": int(self.default_bay_count),
            "default_floor_height_m": float(self.default_floor_height_m),
            "default_load_pattern_count": int(self.default_load_pattern_count),
            "representative_member_types": [str(item) for item in self.representative_member_types],
        }


_AUTHORING_FAMILY_TEMPLATES = {
    "sample_tower": NativeAuthoringFamilyTemplate(
        family_id="sample_tower",
        label="Sample Tower",
        description="Baseline mixed RC-steel tower scaffold with RC columns and frame beams.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022",
        default_bay_width_m=8.0,
        default_story_count=5,
        default_bay_count=3,
        default_floor_height_m=3.9,
        default_load_pattern_count=4,
        representative_member_types=("column", "beam"),
    ),
    "steel_braced_frame": NativeAuthoringFamilyTemplate(
        family_id="steel_braced_frame",
        label="Steel Braced Frame",
        description="Lateral steel braced frame with tube columns, frame beams, deck strips, and X braces.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022-STEEL-BASIC",
        default_bay_width_m=8.5,
        default_story_count=6,
        default_bay_count=4,
        default_floor_height_m=4.5,
        default_load_pattern_count=6,
        representative_member_types=("column", "beam", "brace", "slab"),
    ),
    "rc_wall_core": NativeAuthoringFamilyTemplate(
        family_id="rc_wall_core",
        label="RC Wall Core",
        description="RC wall-core scaffold with shell walls, coupling/gravity members, and slab strips.",
        default_section_id="rc_column_700x700",
        preferred_design_family="KDS-2022",
        default_bay_width_m=7.2,
        default_story_count=9,
        default_bay_count=4,
        default_floor_height_m=3.2,
        default_load_pattern_count=6,
        representative_member_types=("wall", "column", "beam", "slab"),
    ),
    "composite_podium": NativeAuthoringFamilyTemplate(
        family_id="composite_podium",
        label="Composite Podium",
        description="Composite podium scaffold with CFT columns, composite beams, and slab strips.",
        default_section_id="deck_beam_500x250",
        preferred_design_family="KDS-2022-STEEL-BASIC",
        default_bay_width_m=9.0,
        default_story_count=7,
        default_bay_count=4,
        default_floor_height_m=4.2,
        default_load_pattern_count=6,
        representative_member_types=("column", "beam", "slab"),
    ),
    "outrigger_transfer_tower": NativeAuthoringFamilyTemplate(
        family_id="outrigger_transfer_tower",
        label="Outrigger Transfer Tower",
        description="Composite mega-columns with outrigger transfer beams, braces, and deck diaphragms.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022-STEEL-BASIC",
        default_bay_width_m=8.8,
        default_story_count=10,
        default_bay_count=5,
        default_floor_height_m=4.1,
        default_load_pattern_count=6,
        representative_member_types=("column", "beam", "brace", "slab"),
    ),
    "dual_system_hospital": NativeAuthoringFamilyTemplate(
        family_id="dual_system_hospital",
        label="Dual-System Hospital",
        description="RC wall-core and gravity frame hospital scaffold with mixed RC/CFT supports and floor shells.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022",
        default_bay_width_m=8.2,
        default_story_count=8,
        default_bay_count=5,
        default_floor_height_m=4.0,
        default_load_pattern_count=6,
        representative_member_types=("wall", "column", "beam", "slab"),
    ),
    "belt_truss_mega_frame": NativeAuthoringFamilyTemplate(
        family_id="belt_truss_mega_frame",
        label="Belt-Truss Mega Frame",
        description="RC core walls with composite perimeter mega-columns, steel belt truss braces, and deck floors.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022-STEEL-BASIC",
        default_bay_width_m=9.2,
        default_story_count=12,
        default_bay_count=6,
        default_floor_height_m=4.2,
        default_load_pattern_count=6,
        representative_member_types=("wall", "column", "beam", "brace", "slab"),
    ),
    "deep_transfer_basement": NativeAuthoringFamilyTemplate(
        family_id="deep_transfer_basement",
        label="Deep Transfer Basement",
        description="Deep transfer podium and basement scaffold with solid foundations, RC walls, mixed columns, and steel girders.",
        default_section_id="steel_h_600x200",
        preferred_design_family="KDS-2022",
        default_bay_width_m=8.4,
        default_story_count=6,
        default_bay_count=4,
        default_floor_height_m=4.4,
        default_load_pattern_count=6,
        representative_member_types=("foundation", "wall", "column", "beam", "slab"),
    ),
}


@dataclass(frozen=True)
class NativeAuthoringControls:
    family_id: str = DEFAULT_FAMILY_ID
    story_count: int = DEFAULT_STORY_COUNT
    bay_count: int = DEFAULT_BAY_COUNT
    floor_height_m: float = DEFAULT_FLOOR_HEIGHT_M
    load_pattern_count: int = DEFAULT_LOAD_PATTERN_COUNT
    section_id: str = DEFAULT_SECTION_ID

    def to_frontend_payload(self) -> dict[str, Any]:
        return {
            "familyId": str(self.family_id),
            "storyCount": int(self.story_count),
            "bayCount": int(self.bay_count),
            "floorHeightM": float(self.floor_height_m),
            "loadPatternCount": int(self.load_pattern_count),
            "sectionId": str(self.section_id),
        }

    def to_draft_payload(
        self,
        *,
        section_palette: tuple[str, ...] | list[str] = (),
    ) -> dict[str, Any]:
        payload = {
            "family_id": str(self.family_id),
            "story_count": int(self.story_count),
            "bay_count": int(self.bay_count),
            "floor_height_m": float(self.floor_height_m),
            "load_pattern_count": int(self.load_pattern_count),
            "section_id": str(self.section_id),
        }
        palette = [str(item).strip() for item in section_palette if str(item).strip()]
        if palette:
            payload["section_palette"] = palette
        return payload


def create_default_authoring_controls() -> NativeAuthoringControls:
    return NativeAuthoringControls()


def _normalize_family_id(value: Any) -> str:
    token = str(value or "").strip().lower()
    return token if token in _AUTHORING_FAMILY_TEMPLATES else DEFAULT_FAMILY_ID


def get_native_authoring_family_template(family_id: str | None = None) -> NativeAuthoringFamilyTemplate:
    return _AUTHORING_FAMILY_TEMPLATES[_normalize_family_id(family_id)]


def list_native_authoring_family_templates() -> tuple[NativeAuthoringFamilyTemplate, ...]:
    return tuple(_AUTHORING_FAMILY_TEMPLATES[key] for key in _AUTHORING_FAMILY_TEMPLATES)


def _is_record(value: Any) -> bool:
    return isinstance(value, dict)


def _record_has_authoring_controls(value: Any) -> bool:
    return _is_record(value) and any(value.get(key) is not None for key in _CONTROL_KEYS)


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric == numeric and numeric not in {float("inf"), float("-inf")} else None
    if isinstance(value, str) and value.strip():
        try:
            numeric = float(value)
        except ValueError:
            return None
        return numeric if numeric == numeric and numeric not in {float("inf"), float("-inf")} else None
    return None


def _first_number(*values: Any) -> float | None:
    for value in values:
        numeric = _coerce_number(value)
        if numeric is not None:
            return numeric
    return None


def _token_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = _coerce_number(value)
        return "" if numeric is None else str(int(numeric) if numeric.is_integer() else numeric)
    return ""


def _clamp_number(value: Any, fallback: float, minimum: float, maximum: float) -> float:
    numeric = _coerce_number(value)
    if numeric is None:
        numeric = float(fallback)
    return max(minimum, min(maximum, float(numeric)))


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("authoring draft payload must be a JSON object")
    return payload


def _authoring_control_source(source: Any) -> dict[str, Any]:
    if isinstance(source, NativeAuthoringControls):
        return source.to_frontend_payload()
    if not _is_record(source):
        return {}
    candidates = [
        source.get("authoring_controls"),
        source.get("authoringControls"),
        source.get("editor_controls"),
        source,
    ]
    for candidate in candidates:
        if _record_has_authoring_controls(candidate):
            return dict(candidate)
    return {}


def normalize_authoring_controls(
    source: Any = None,
    *,
    fallback: NativeAuthoringControls | None = None,
) -> NativeAuthoringControls:
    defaults = fallback or create_default_authoring_controls()
    control_source = _authoring_control_source(source)
    if not control_source:
        return defaults
    family_id = _normalize_family_id(
        control_source.get("familyId")
        or control_source.get("family_id")
        or control_source.get("authoringFamilyId")
        or control_source.get("authoring_family_id")
        or defaults.family_id
    )
    family_template = get_native_authoring_family_template(family_id)
    family_defaults = NativeAuthoringControls(
        family_id=family_id,
        story_count=family_template.default_story_count,
        bay_count=family_template.default_bay_count,
        floor_height_m=family_template.default_floor_height_m,
        load_pattern_count=family_template.default_load_pattern_count,
        section_id=family_template.default_section_id,
    )
    fallback_defaults = defaults if defaults.family_id == family_id else family_defaults
    return NativeAuthoringControls(
        family_id=family_id,
        story_count=int(
            _clamp_number(
                _first_number(control_source.get("storyCount"), control_source.get("story_count")),
                fallback_defaults.story_count,
                1,
                _MAX_STORY_COUNT,
            )
        ),
        bay_count=int(
            _clamp_number(
                _first_number(control_source.get("bayCount"), control_source.get("bay_count")),
                fallback_defaults.bay_count,
                1,
                _MAX_BAY_COUNT,
            )
        ),
        floor_height_m=float(
            _clamp_number(
                _first_number(control_source.get("floorHeightM"), control_source.get("floor_height_m")),
                fallback_defaults.floor_height_m,
                _MIN_FLOOR_HEIGHT_M,
                _MAX_FLOOR_HEIGHT_M,
            )
        ),
        load_pattern_count=int(
            _clamp_number(
                _first_number(control_source.get("loadPatternCount"), control_source.get("load_pattern_count")),
                fallback_defaults.load_pattern_count,
                1,
                _MAX_LOAD_PATTERN_COUNT,
            )
        ),
        section_id=(
            _token_string(control_source.get("sectionId"))
            or _token_string(control_source.get("section_id"))
            or _token_string(control_source.get("default_section_id"))
            or family_template.default_section_id
            or fallback_defaults.section_id
        ),
    )


def resolve_authoring_controls(
    *,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> NativeAuthoringControls:
    source: Any = None
    if authoring_controls is not None:
        source = authoring_controls
    elif draft_payload is not None:
        source = draft_payload
    elif draft_json_path is not None:
        source = _load_json_object(draft_json_path)

    controls = normalize_authoring_controls(source)
    overrides: dict[str, Any] = {}
    if family_id is not None:
        overrides["familyId"] = family_id
    if story_count is not None:
        overrides["storyCount"] = story_count
    if bay_count is not None:
        overrides["bayCount"] = bay_count
    if floor_height_m is not None:
        overrides["floorHeightM"] = floor_height_m
    if load_pattern_count is not None:
        overrides["loadPatternCount"] = load_pattern_count
    if section_id is not None:
        overrides["sectionId"] = section_id
    return normalize_authoring_controls(overrides, fallback=controls) if overrides else controls


def _slug_token(value: str) -> str:
    token = "".join(character if character.isalnum() else "-" for character in str(value).strip().lower())
    collapsed = "-".join(part for part in token.split("-") if part)
    return collapsed or "default"


def _model_id_for_controls(controls: NativeAuthoringControls) -> str:
    if controls == create_default_authoring_controls():
        return "native-authoring-sample-tower"
    floor_token = f"{int(round(float(controls.floor_height_m) * 10.0)):03d}"
    family_prefix = "" if controls.family_id == DEFAULT_FAMILY_ID else f"{_slug_token(controls.family_id)}-"
    return (
        f"native-authoring-{family_prefix}{controls.story_count:02d}s-{controls.bay_count:02d}b-"
        f"{floor_token}h-{controls.load_pattern_count:02d}lp-{_slug_token(controls.section_id)}"
    )


def _build_load_pattern_library(*, story_count: int, floor_height_m: float) -> dict[str, LoadPatternDraft]:
    top_story_id = f"L{max(int(story_count), 1)}"
    roof_scope = f"story:{top_story_id}"
    roof_displacement = max(0.006, round(float(floor_height_m) * 0.0045, 4))

    patterns = (
        LoadPatternDraft(
            pattern_id="lp-dead",
            label="Dead load",
            design_situation="ULS",
            primitives=(LoadPrimitive("self_weight", "D", "global", 1.0),),
            tags=("gravity",),
        ),
        LoadPatternDraft(
            pattern_id="lp-live",
            label="Live load",
            design_situation="SLS",
            primitives=(
                LoadPrimitive("surface_pressure", "L", "floor", 3.5),
                LoadPrimitive("point_load", "L", "equipment-node", 12.0, direction="global_z"),
            ),
            tags=("gravity", "service"),
        ),
        LoadPatternDraft(
            pattern_id="lp-windx",
            label="Wind +X",
            design_situation="ULS",
            primitives=(LoadPrimitive("line_load", "Wx", "frame-east", 22.0, direction="global_x"),),
            tags=("wind",),
        ),
        LoadPatternDraft(
            pattern_id="lp-seisx",
            label="Seismic X",
            design_situation="ULS",
            primitives=(LoadPrimitive("displacement", "Ex", roof_scope, roof_displacement, direction="global_x"),),
            tags=("seismic",),
        ),
        LoadPatternDraft(
            pattern_id="lp-windy",
            label="Wind +Y",
            design_situation="ULS",
            primitives=(LoadPrimitive("line_load", "Wy", "frame-north", 20.0, direction="global_y"),),
            tags=("wind",),
        ),
        LoadPatternDraft(
            pattern_id="lp-seisy",
            label="Seismic Y",
            design_situation="ULS",
            primitives=(LoadPrimitive("displacement", "Ey", roof_scope, roof_displacement, direction="global_y"),),
            tags=("seismic",),
        ),
        LoadPatternDraft(
            pattern_id="lp-roof-live",
            label="Roof live",
            design_situation="SLS",
            primitives=(LoadPrimitive("surface_pressure", "Lr", "roof", 1.5),),
            tags=("gravity", "roof"),
        ),
        LoadPatternDraft(
            pattern_id="lp-snow",
            label="Snow",
            design_situation="ULS",
            primitives=(LoadPrimitive("surface_pressure", "S", "roof", 1.2),),
            tags=("roof", "environment"),
        ),
        LoadPatternDraft(
            pattern_id="lp-live-partition",
            label="Partition live",
            design_situation="SLS",
            primitives=(LoadPrimitive("surface_pressure", "L", "corridor", 1.5),),
            tags=("gravity", "service", "fitout"),
        ),
        LoadPatternDraft(
            pattern_id="lp-windx-drift",
            label="Wind drift +X",
            design_situation="SLS",
            primitives=(LoadPrimitive("displacement", "Wx", roof_scope, roof_displacement * 0.5, direction="global_x"),),
            tags=("wind", "drift"),
        ),
        LoadPatternDraft(
            pattern_id="lp-dead-facade",
            label="Facade dead",
            design_situation="ULS",
            primitives=(LoadPrimitive("line_load", "D", "perimeter", 4.5, direction="global_z"),),
            tags=("gravity", "facade"),
        ),
        LoadPatternDraft(
            pattern_id="lp-seisx-drift",
            label="Seismic drift X",
            design_situation="SLS",
            primitives=(LoadPrimitive("displacement", "Ex", roof_scope, roof_displacement * 0.7, direction="global_x"),),
            tags=("seismic", "drift"),
        ),
    )
    return {row.pattern_id: row for row in patterns}


_FAMILY_LOAD_PATTERN_IDS = {
    "sample_tower": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-seisx",
        "lp-windy",
        "lp-seisy",
        "lp-roof-live",
        "lp-snow",
        "lp-live-partition",
        "lp-windx-drift",
        "lp-dead-facade",
        "lp-seisx-drift",
    ),
    "steel_braced_frame": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
        "lp-dead-facade",
        "lp-live-partition",
    ),
    "rc_wall_core": (
        "lp-dead",
        "lp-live",
        "lp-dead-facade",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-live-partition",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
    ),
    "composite_podium": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-roof-live",
        "lp-snow",
        "lp-live-partition",
        "lp-dead-facade",
        "lp-windx-drift",
        "lp-seisx-drift",
    ),
    "outrigger_transfer_tower": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
        "lp-dead-facade",
        "lp-live-partition",
    ),
    "dual_system_hospital": (
        "lp-dead",
        "lp-live",
        "lp-dead-facade",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-live-partition",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
    ),
    "belt_truss_mega_frame": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
        "lp-dead-facade",
        "lp-live-partition",
    ),
    "deep_transfer_basement": (
        "lp-dead",
        "lp-live",
        "lp-windx",
        "lp-windy",
        "lp-seisx",
        "lp-seisy",
        "lp-dead-facade",
        "lp-live-partition",
        "lp-windx-drift",
        "lp-seisx-drift",
        "lp-roof-live",
        "lp-snow",
    ),
}


def _build_story_levels(controls: NativeAuthoringControls) -> tuple[StoryLevel, ...]:
    return tuple(
        StoryLevel(
            story_id=f"L{index + 1}",
            elevation_m=float(index * controls.floor_height_m),
            height_m=float(controls.floor_height_m),
            label=f"Level {index + 1}",
        )
        for index in range(controls.story_count)
    )


def _build_frame_nodes(
    *,
    controls: NativeAuthoringControls,
    story_levels: tuple[StoryLevel, ...],
    bay_width_m: float,
) -> tuple[NodeDraft, ...]:
    nodes: list[NodeDraft] = []
    for story_index in range(controls.story_count + 1):
        elevation = float(story_index * controls.floor_height_m)
        story_id = story_levels[min(story_index, controls.story_count - 1)].story_id if story_levels else ""
        for bay_index in range(controls.bay_count + 1):
            nodes.append(
                NodeDraft(
                    node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    x_m=float(bay_index * bay_width_m),
                    y_m=0.0,
                    z_m=elevation,
                    story_id=story_id,
                )
            )
    return tuple(nodes)


def _build_sample_tower_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    for story_index in range(controls.story_count):
        for bay_index in range(controls.bay_count + 1):
            members.append(
                MemberDraft(
                    member_id=f"C-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id="rc_column_700x700",
                    analysis_kind="fiber_section",
                    tags=("gravity", "lateral"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"B-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("gravity",),
                )
            )
    return tuple(members)


def _build_steel_braced_frame_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    for story_index in range(controls.story_count):
        for bay_index in range(controls.bay_count + 1):
            members.append(
                MemberDraft(
                    member_id=f"SC-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id="steel_box_400x400x16",
                    analysis_kind="frame",
                    tags=("lateral", "gravity", "steel"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"SB-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("gravity", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"SF-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("floor", "shell", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"BRX-{story_index + 1:02d}-{bay_index + 1:02d}-A",
                    member_type="brace",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("lateral", "brace", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"BRX-{story_index + 1:02d}-{bay_index + 1:02d}-B",
                    member_type="brace",
                    start_node_id=f"N-{story_index:02d}-{bay_index + 1:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("lateral", "brace", "steel"),
                )
            )
    return tuple(members)


def _build_rc_wall_core_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    for story_index in range(controls.story_count):
        members.append(
            MemberDraft(
                member_id=f"W-{story_index + 1:02d}-01",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-00",
                end_node_id=f"N-{story_index + 1:02d}-00",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("core", "wall", "lateral"),
            )
        )
        members.append(
            MemberDraft(
                member_id=f"W-{story_index + 1:02d}-02",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-{controls.bay_count:02d}",
                end_node_id=f"N-{story_index + 1:02d}-{controls.bay_count:02d}",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("core", "wall", "lateral"),
            )
        )
        for bay_index in range(1, controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"GC-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id="rc_column_700x700",
                    analysis_kind="fiber_section",
                    tags=("gravity", "core"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"CB-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="fiber_section",
                    tags=("gravity", "coupling"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"CS-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("core", "floor", "slab"),
                )
            )
    return tuple(members)


def _build_composite_podium_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    for story_index in range(controls.story_count):
        for bay_index in range(controls.bay_count + 1):
            members.append(
                MemberDraft(
                    member_id=f"CC-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id="cft_box_700x700",
                    analysis_kind="fiber_section",
                    tags=("composite", "gravity", "lateral"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"CBM-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("composite", "floor"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"SL-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="shell",
                    tags=("composite", "slab", "floor"),
                )
            )
    return tuple(members)


def _build_outrigger_transfer_tower_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    outrigger_levels = {
        max(0, controls.story_count // 3 - 1),
        max(0, (2 * controls.story_count) // 3 - 1),
    }
    for story_index in range(controls.story_count):
        is_outrigger_story = story_index in outrigger_levels
        for bay_index in range(controls.bay_count + 1):
            members.append(
                MemberDraft(
                    member_id=f"OT-C-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id="cft_box_700x700",
                    analysis_kind="fiber_section",
                    tags=("tower", "outrigger", "composite"),
                )
            )
        for bay_index in range(controls.bay_count):
            beam_section_id = "steel_box_400x400x16" if is_outrigger_story else str(controls.section_id)
            members.append(
                MemberDraft(
                    member_id=f"OT-B-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=beam_section_id,
                    analysis_kind="frame",
                    tags=("tower", "transfer", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"OT-S-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("tower", "floor", "shell"),
                )
            )
            if is_outrigger_story:
                members.append(
                    MemberDraft(
                        member_id=f"OT-X-{story_index + 1:02d}-{bay_index + 1:02d}",
                        member_type="brace",
                        start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                        end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                        section_id="steel_box_400x400x16",
                        analysis_kind="frame",
                        tags=("tower", "outrigger", "brace"),
                    )
                )
    return tuple(members)


def _build_dual_system_hospital_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    for story_index in range(controls.story_count):
        members.append(
            MemberDraft(
                member_id=f"DH-W-{story_index + 1:02d}-01",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-00",
                end_node_id=f"N-{story_index + 1:02d}-00",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("hospital", "core", "wall"),
            )
        )
        members.append(
            MemberDraft(
                member_id=f"DH-W-{story_index + 1:02d}-02",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-{controls.bay_count:02d}",
                end_node_id=f"N-{story_index + 1:02d}-{controls.bay_count:02d}",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("hospital", "core", "wall"),
            )
        )
        for bay_index in range(controls.bay_count + 1):
            column_section_id = "cft_box_700x700" if bay_index in {0, controls.bay_count} else "rc_column_700x700"
            members.append(
                MemberDraft(
                    member_id=f"DH-C-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id=column_section_id,
                    analysis_kind="fiber_section",
                    tags=("hospital", "gravity", "mixed"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"DH-B-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("hospital", "gravity", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"DH-S-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("hospital", "floor", "shell"),
                )
            )
    return tuple(members)


def _build_belt_truss_mega_frame_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    belt_levels = {
        max(0, controls.story_count // 3 - 1),
        max(0, (2 * controls.story_count) // 3 - 1),
        max(0, controls.story_count - 2),
    }
    for story_index in range(controls.story_count):
        members.append(
            MemberDraft(
                member_id=f"BT-W-{story_index + 1:02d}-01",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-00",
                end_node_id=f"N-{story_index + 1:02d}-00",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("belt_truss", "core", "wall"),
            )
        )
        members.append(
            MemberDraft(
                member_id=f"BT-W-{story_index + 1:02d}-02",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-{controls.bay_count:02d}",
                end_node_id=f"N-{story_index + 1:02d}-{controls.bay_count:02d}",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("belt_truss", "core", "wall"),
            )
        )
        for bay_index in range(controls.bay_count + 1):
            section_id = "cft_box_700x700" if bay_index in {0, controls.bay_count} else "rc_column_700x700"
            members.append(
                MemberDraft(
                    member_id=f"BT-C-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id=section_id,
                    analysis_kind="fiber_section",
                    tags=("belt_truss", "mega_frame", "gravity"),
                )
            )
        for bay_index in range(controls.bay_count):
            members.append(
                MemberDraft(
                    member_id=f"BT-B-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=str(controls.section_id),
                    analysis_kind="frame",
                    tags=("belt_truss", "transfer", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"BT-S-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("belt_truss", "floor", "deck"),
                )
            )
            if story_index in belt_levels:
                members.append(
                    MemberDraft(
                        member_id=f"BT-X-{story_index + 1:02d}-{bay_index + 1:02d}",
                        member_type="brace",
                        start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                        end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                        section_id="steel_box_400x400x16",
                        analysis_kind="frame",
                        tags=("belt_truss", "brace", "steel"),
                    )
                )
    return tuple(members)


def _build_deep_transfer_basement_members(controls: NativeAuthoringControls) -> tuple[MemberDraft, ...]:
    members: list[MemberDraft] = []
    transfer_levels = {0, max(0, controls.story_count // 2 - 1)}
    for story_index in range(controls.story_count):
        members.append(
            MemberDraft(
                member_id=f"TB-W-{story_index + 1:02d}-01",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-00",
                end_node_id=f"N-{story_index + 1:02d}-00",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("transfer", "basement", "wall"),
            )
        )
        members.append(
            MemberDraft(
                member_id=f"TB-W-{story_index + 1:02d}-02",
                member_type="wall",
                start_node_id=f"N-{story_index:02d}-{controls.bay_count:02d}",
                end_node_id=f"N-{story_index + 1:02d}-{controls.bay_count:02d}",
                section_id="rc_wall_300x3000",
                analysis_kind="shell",
                tags=("transfer", "basement", "wall"),
            )
        )
        for bay_index in range(controls.bay_count + 1):
            section_id = "cft_box_700x700" if bay_index in {0, controls.bay_count} else "rc_column_700x700"
            members.append(
                MemberDraft(
                    member_id=f"TB-C-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="column",
                    start_node_id=f"N-{story_index:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    section_id=section_id,
                    analysis_kind="fiber_section",
                    tags=("transfer", "basement", "gravity"),
                )
            )
        for bay_index in range(controls.bay_count):
            beam_section_id = "steel_box_400x400x16" if story_index in transfer_levels else str(controls.section_id)
            members.append(
                MemberDraft(
                    member_id=f"TB-B-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="beam",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id=beam_section_id,
                    analysis_kind="frame",
                    tags=("transfer", "girder", "steel"),
                )
            )
            members.append(
                MemberDraft(
                    member_id=f"TB-S-{story_index + 1:02d}-{bay_index + 1:02d}",
                    member_type="slab",
                    start_node_id=f"N-{story_index + 1:02d}-{bay_index:02d}",
                    end_node_id=f"N-{story_index + 1:02d}-{bay_index + 1:02d}",
                    section_id="deck_beam_500x250",
                    analysis_kind="shell",
                    tags=("transfer", "floor", "deck"),
                )
            )
    for bay_index in range(controls.bay_count):
        members.append(
            MemberDraft(
                member_id=f"TB-F-{bay_index + 1:02d}",
                member_type="foundation",
                start_node_id=f"N-00-{bay_index:02d}",
                end_node_id=f"N-00-{bay_index + 1:02d}",
                section_id="rc_wall_300x3000",
                analysis_kind="solid",
                tags=("transfer", "basement", "foundation"),
            )
        )
    return tuple(members)


def _build_family_load_patterns(
    *,
    family_id: str,
    story_count: int,
    floor_height_m: float,
    load_pattern_count: int,
) -> tuple[LoadPatternDraft, ...]:
    catalog = _build_load_pattern_library(story_count=story_count, floor_height_m=floor_height_m)
    ordered_ids = _FAMILY_LOAD_PATTERN_IDS.get(family_id, _FAMILY_LOAD_PATTERN_IDS[DEFAULT_FAMILY_ID])
    return tuple(catalog[pattern_id] for pattern_id in ordered_ids[:load_pattern_count] if pattern_id in catalog)


def build_sample_authoring_model(
    *,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    bay_width_m: float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> AuthoringModelDraft:
    controls = resolve_authoring_controls(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    family_template = get_native_authoring_family_template(controls.family_id)
    effective_bay_width_m = float(bay_width_m or 0.0) if float(bay_width_m or 0.0) > 0.0 else family_template.default_bay_width_m
    story_levels = _build_story_levels(controls)
    nodes = _build_frame_nodes(controls=controls, story_levels=story_levels, bay_width_m=effective_bay_width_m)
    member_builder = {
        "sample_tower": _build_sample_tower_members,
        "steel_braced_frame": _build_steel_braced_frame_members,
        "rc_wall_core": _build_rc_wall_core_members,
        "composite_podium": _build_composite_podium_members,
        "outrigger_transfer_tower": _build_outrigger_transfer_tower_members,
        "dual_system_hospital": _build_dual_system_hospital_members,
        "belt_truss_mega_frame": _build_belt_truss_mega_frame_members,
        "deep_transfer_basement": _build_deep_transfer_basement_members,
    }.get(controls.family_id, _build_sample_tower_members)
    members = member_builder(controls)
    load_patterns = _build_family_load_patterns(
        family_id=controls.family_id,
        story_count=controls.story_count,
        floor_height_m=controls.floor_height_m,
        load_pattern_count=controls.load_pattern_count,
    )

    return AuthoringModelDraft(
        model_id=_model_id_for_controls(controls),
        story_levels=story_levels,
        nodes=nodes,
        members=members,
        load_patterns=load_patterns,
        metadata={
            "floor_height_m": float(controls.floor_height_m),
            "bay_width_m": float(effective_bay_width_m),
            "authoring_mode": "interactive_scaffold",
            "authoring_family_id": str(family_template.family_id),
            "authoring_family_label": str(family_template.label),
            "preferred_design_family": str(family_template.preferred_design_family),
            "authoring_controls": controls.to_draft_payload(),
        },
    )


def build_native_authoring_workspace_payload(
    *,
    generated_at: str | None = None,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    catalog = build_default_section_catalog()
    controls = resolve_authoring_controls(
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    model = build_sample_authoring_model(authoring_controls=controls)
    summary = build_authoring_bundle_summary(catalog=catalog, model=model)
    timestamp = str(generated_at or "").strip() or datetime.now(timezone.utc).isoformat()
    section_palette = list(catalog.template_ids())
    family_templates = [row.to_payload() for row in list_native_authoring_family_templates()]
    selected_family = get_native_authoring_family_template(controls.family_id).to_payload()
    return {
        "schema_version": "1.0",
        "report_family": "native_authoring_workspace",
        "generated_at": timestamp,
        "authoring_controls": controls.to_draft_payload(section_palette=section_palette),
        "selected_family": selected_family,
        "summary": summary.to_payload(),
        "model_preview": {
            "story_levels": [row.to_payload() for row in model.story_levels],
            "member_preview_rows": [row.to_payload() for row in model.members[:8]],
            "load_patterns": [row.to_payload() for row in model.load_patterns],
        },
        "editor_controls": {
            **controls.to_draft_payload(section_palette=section_palette),
            "bay_width_m": float(selected_family["default_bay_width_m"]),
            "default_section_id": str(controls.section_id),
            "default_family_id": str(controls.family_id),
            "family_palette": family_templates,
        },
        "summary_line": f"{summary.summary_line} | family={controls.family_id}",
        "contract_pass": bool(summary.native_authoring_ready),
        "reason_code": "PASS" if summary.native_authoring_ready else "CHECK",
        "reason": "native authoring workspace summary generated",
    }


def materialize_native_authoring_workspace_summary(
    *,
    out_path: Path = DEFAULT_OUT,
    generated_at: str | None = None,
    authoring_controls: Any = None,
    draft_payload: dict[str, Any] | None = None,
    draft_json_path: str | Path | None = None,
    family_id: str | None = None,
    story_count: int | float | None = None,
    bay_count: int | float | None = None,
    floor_height_m: int | float | None = None,
    load_pattern_count: int | float | None = None,
    section_id: str | None = None,
) -> dict[str, Any]:
    payload = build_native_authoring_workspace_payload(
        generated_at=generated_at,
        authoring_controls=authoring_controls,
        draft_payload=draft_payload,
        draft_json_path=draft_json_path,
        family_id=family_id,
        story_count=story_count,
        bay_count=bay_count,
        floor_height_m=floor_height_m,
        load_pattern_count=load_pattern_count,
        section_id=section_id,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--draft-json", default="")
    parser.add_argument("--family-id", default=None)
    parser.add_argument("--story-count", type=float, default=None)
    parser.add_argument("--bay-count", type=float, default=None)
    parser.add_argument("--floor-height-m", type=float, default=None)
    parser.add_argument("--load-pattern-count", type=float, default=None)
    parser.add_argument("--section-id", default=None)
    args = parser.parse_args()

    payload = materialize_native_authoring_workspace_summary(
        out_path=Path(args.out),
        generated_at=str(args.generated_at).strip() or None,
        draft_json_path=str(args.draft_json).strip() or None,
        family_id=str(args.family_id).strip() if isinstance(args.family_id, str) and args.family_id.strip() else None,
        story_count=args.story_count,
        bay_count=args.bay_count,
        floor_height_m=args.floor_height_m,
        load_pattern_count=args.load_pattern_count,
        section_id=str(args.section_id).strip() if isinstance(args.section_id, str) and args.section_id.strip() else None,
    )
    print(payload["summary_line"])


if __name__ == "__main__":
    main()
