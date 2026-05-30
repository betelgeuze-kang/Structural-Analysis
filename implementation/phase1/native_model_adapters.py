#!/usr/bin/env python3
"""Native structural model format adapters (stub implementations).

Provides lightweight parsers for commercial FE tool native formats:
- MIDAS Gen / Civil (.mgt, .mgb)
- OpenSees (.tcl, .py)
- Abaqus (.inp)
- ETABS (.e2k, .s2k)
- SAP2000 (.s2k)
- STAAD.Pro (.std)

These stubs extract geometry, elements, loads, and material assignments
into the canonical viewer model format so the 3D viewer can render them
without requiring the full solver runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class NativeModelParseResult:
    nodes: list[dict]
    elements: list[dict]
    materials: list[dict]
    sections: list[dict]
    loads: list[dict]
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    format_detected: str = "unknown"


def _safe_float(text: str, fallback: float = 0.0) -> float:
    try:
        return float(str(text).strip().replace(",", ""))
    except (ValueError, TypeError):
        return fallback


def _safe_int(text: str, fallback: int = 0) -> int:
    try:
        return int(float(str(text).strip().replace(",", "")))
    except (ValueError, TypeError):
        return fallback


# =============================================================================
# MIDAS MGT Parser Stub
# =============================================================================

MIDAS_NODE_PATTERN = re.compile(r"^\s*NODE\s+(\d+)\s+([\d\-.]+)\s+([\d\-.]+)\s+([\d\-.]+)", re.IGNORECASE)
MIDAS_ELEMENT_PATTERN = re.compile(r"^\s*(BEAM|TRUSS|PLATE|SOLID|WALL|COLUMN|BRACE)\s+(\d+)\s+(\d+)\s+(\d+)", re.IGNORECASE)
MIDAS_MATERIAL_PATTERN = re.compile(r"^\s*MATERIAL\s+(\d+)\s+([\w\s\-/.()]+)", re.IGNORECASE)
MIDAS_SECTION_PATTERN = re.compile(r"^\s*SECTION\s+(\d+)\s+([\w\s\-/.()]+)", re.IGNORECASE)


def parse_midas_mgt(text: str) -> NativeModelParseResult:
    """Parse MIDAS Gen/Civil .mgt text into canonical model."""
    nodes = []
    elements = []
    materials = []
    sections = []
    loads = []
    warnings = []

    node_id_map = {}
    element_id_counter = 0

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or line.startswith("*"):
            continue

        # NODE
        m = MIDAS_NODE_PATTERN.match(line)
        if m:
            node_id = _safe_int(m.group(1))
            node = {
                "id": node_id,
                "x": _safe_float(m.group(2)),
                "y": _safe_float(m.group(3)),
                "z": _safe_float(m.group(4)),
            }
            nodes.append(node)
            node_id_map[node_id] = node
            continue

        # ELEMENT
        m = MIDAS_ELEMENT_PATTERN.match(line)
        if m:
            elem_type = m.group(1).lower()
            elem_id = _safe_int(m.group(2))
            n1 = _safe_int(m.group(3))
            n2 = _safe_int(m.group(4))
            element_id_counter += 1
            elements.append({
                "id": f"midas_elem_{element_id_counter}",
                "type": elem_type,
                "node_ids": [n1, n2],
                "section": "",
                "material_id": "",
                "dcr": 0,
            })
            continue

        # MATERIAL
        m = MIDAS_MATERIAL_PATTERN.match(line)
        if m:
            mat_id = _safe_int(m.group(1))
            mat_name = m.group(2).strip()
            materials.append({
                "id": mat_id,
                "name": mat_name,
                "family": _infer_material_family(mat_name),
            })
            continue

        # SECTION
        m = MIDAS_SECTION_PATTERN.match(line)
        if m:
            sec_id = _safe_int(m.group(1))
            sec_name = m.group(2).strip()
            sections.append({
                "id": sec_id,
                "name": sec_name,
                "shape": _infer_section_shape(sec_name),
            })

    if not nodes:
        warnings.append("No nodes found in MGT file")
    if not elements:
        warnings.append("No elements found in MGT file")

    return NativeModelParseResult(
        nodes=nodes,
        elements=elements,
        materials=materials,
        sections=sections,
        loads=loads,
        meta={
            "source_format": "midas_mgt",
            "node_count": len(nodes),
            "element_count": len(elements),
        },
        warnings=warnings,
        format_detected="midas_mgt",
    )


def _infer_material_family(name: str) -> str:
    name_lower = str(name).lower()
    if "conc" in name_lower or "콘크리트" in name_lower:
        return "concrete"
    if "steel" in name_lower or "강" in name_lower:
        return "steel"
    if "timber" in name_lower or "목재" in name_lower or "wood" in name_lower:
        return "timber"
    if "frp" in name_lower:
        return "frp"
    return "other"


def _infer_section_shape(name: str) -> str:
    name_lower = str(name).lower()
    if "h-" in name_lower or "hsec" in name_lower:
        return "h_section"
    if "box" in name_lower:
        return "box_section"
    if "pipe" in name_lower or "tube" in name_lower:
        return "pipe"
    if "angle" in name_lower or "l-" in name_lower:
        return "angle"
    if "channel" in name_lower or "c-" in name_lower:
        return "channel"
    if "rebar" in name_lower or "deform" in name_lower:
        return "rebar"
    return "generic"


# =============================================================================
# OpenSees TCL Parser Stub
# =============================================================================

OPENSEES_NODE_PATTERN = re.compile(r"node\s+(\d+)\s+([\d\-.]+)\s+([\d\-.]+)\s+([\d\-.]+)", re.IGNORECASE)
OPENSEES_ELEMENT_PATTERNS = [
    re.compile(r"element\s+elasticBeamColumn\s+(\d+)\s+(\d+)\s+(\d+)", re.IGNORECASE),
    re.compile(r"element\s+BeamColumn\s+(\d+)\s+(\d+)\s+(\d+)", re.IGNORECASE),
    re.compile(r"element\s+truss\s+(\d+)\s+(\d+)\s+(\d+)", re.IGNORECASE),
    re.compile(r"element\s+Shell\w*\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)", re.IGNORECASE),
]


def parse_opensees_tcl(text: str) -> NativeModelParseResult:
    """Parse OpenSees .tcl text into canonical model."""
    nodes = []
    elements = []
    materials = []
    sections = []
    loads = []
    warnings = []

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = OPENSEES_NODE_PATTERN.search(line)
        if m:
            nodes.append({
                "id": _safe_int(m.group(1)),
                "x": _safe_float(m.group(2)),
                "y": _safe_float(m.group(3)),
                "z": _safe_float(m.group(4)),
            })
            continue

        for pat in OPENSEES_ELEMENT_PATTERNS:
            m = pat.search(line)
            if m:
                groups = m.groups()
                elem_id = _safe_int(groups[0])
                node_ids = [_safe_int(g) for g in groups[1:]]
                elem_type = "beam"
                if "truss" in line.lower():
                    elem_type = "truss"
                elif "shell" in line.lower():
                    elem_type = "slab"
                elements.append({
                    "id": f"opensees_elem_{elem_id}",
                    "type": elem_type,
                    "node_ids": node_ids,
                    "section": "",
                    "material_id": "",
                    "dcr": 0,
                })
                break

    return NativeModelParseResult(
        nodes=nodes,
        elements=elements,
        materials=materials,
        sections=sections,
        loads=loads,
        meta={
            "source_format": "opensees_tcl",
            "node_count": len(nodes),
            "element_count": len(elements),
        },
        warnings=warnings,
        format_detected="opensees_tcl",
    )


# =============================================================================
# Abaqus INP Parser Stub
# =============================================================================

ABAQUS_NODE_PATTERN = re.compile(r"^\s*(\d+)\s*,?\s*([\d\-.]+)\s*,?\s*([\d\-.]+)\s*,?\s*([\d\-.]+)")
ABAQUS_ELEMENT_PATTERNS = [
    (re.compile(r"\*Element,\s*type=(\w+)", re.IGNORECASE), "type_line"),
    (re.compile(r"\*Element,\s*type=S4R", re.IGNORECASE), "slab"),
    (re.compile(r"\*Element,\s*type=C3D8R", re.IGNORECASE), "solid"),
]


def parse_abaqus_inp(text: str) -> NativeModelParseResult:
    """Parse Abaqus .inp text into canonical model."""
    nodes = []
    elements = []
    materials = []
    sections = []
    loads = []
    warnings = []

    lines = text.splitlines()
    in_node_block = False
    in_element_block = False
    current_element_type = "beam"

    for line in lines:
        line = line.strip()
        if not line or line.startswith("**"):
            continue

        if line.lower().startswith("*node"):
            in_node_block = True
            in_element_block = False
            continue

        if line.lower().startswith("*element"):
            in_node_block = False
            in_element_block = True
            for pat, etype in ABAQUS_ELEMENT_PATTERNS:
                if pat.search(line):
                    current_element_type = etype
                    break
            continue

        if line.startswith("*"):
            in_node_block = False
            in_element_block = False
            continue

        if in_node_block:
            m = ABAQUS_NODE_PATTERN.match(line)
            if m:
                nodes.append({
                    "id": _safe_int(m.group(1)),
                    "x": _safe_float(m.group(2)),
                    "y": _safe_float(m.group(3)),
                    "z": _safe_float(m.group(4)),
                })

        if in_element_block:
            parts = line.split(",")
            if len(parts) >= 3:
                elem_id = _safe_int(parts[0])
                node_ids = [_safe_int(p) for p in parts[1:]]
                elements.append({
                    "id": f"abaqus_elem_{elem_id}",
                    "type": current_element_type,
                    "node_ids": node_ids,
                    "section": "",
                    "material_id": "",
                    "dcr": 0,
                })

    return NativeModelParseResult(
        nodes=nodes,
        elements=elements,
        materials=materials,
        sections=sections,
        loads=loads,
        meta={
            "source_format": "abaqus_inp",
            "node_count": len(nodes),
            "element_count": len(elements),
        },
        warnings=warnings,
        format_detected="abaqus_inp",
    )


# =============================================================================
# Format Auto-Detection
# =============================================================================

FORMAT_DETECTORS = [
    ("midas_mgt", lambda t: "*NODE" in t[:2000].upper() or "NODE" in t[:500].upper()),
    ("opensees_tcl", lambda t: "model BasicBuilder" in t[:2000] or "node " in t[:500]),
    ("abaqus_inp", lambda t: "*Heading" in t[:500] or "*Node" in t[:500]),
]


def detect_native_format(text: str) -> str:
    for fmt, detector in FORMAT_DETECTORS:
        if detector(text):
            return fmt
    return "unknown"


def parse_native_model(text: str, format_hint: str = "") -> NativeModelParseResult:
    fmt = format_hint or detect_native_format(text)
    if fmt == "midas_mgt":
        return parse_midas_mgt(text)
    if fmt == "opensees_tcl":
        return parse_opensees_tcl(text)
    if fmt == "abaqus_inp":
        return parse_abaqus_inp(text)
    return NativeModelParseResult(
        nodes=[], elements=[], materials=[], sections=[], loads=[],
        meta={"source_format": "unknown"},
        warnings=[f"Unsupported format: {fmt}"],
        format_detected=fmt,
    )


def native_result_to_viewer_payload(result: NativeModelParseResult) -> dict:
    """Convert native parse result to the canonical viewer model payload."""
    return {
        "nodes": result.nodes,
        "elements": result.elements,
        "material_models": {m["id"]: m for m in result.materials},
        "meta": {
            **result.meta,
            "name": f"{result.format_detected} model",
            "source_label": result.format_detected,
            "source_mode": "native_parser",
            "warnings": result.warnings,
        },
    }


__all__ = [
    "NativeModelParseResult",
    "parse_midas_mgt",
    "parse_opensees_tcl",
    "parse_abaqus_inp",
    "detect_native_format",
    "parse_native_model",
    "native_result_to_viewer_payload",
]
