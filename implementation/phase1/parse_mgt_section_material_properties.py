#!/usr/bin/env python3
"""Parse *SECTION and *MATERIAL blocks from MIDAS Gen MGT text."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

_PIPE_NAME_RE = re.compile(
    r"P\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_RANGE_BY_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*$", re.IGNORECASE)
_SUPPORT_DOF_LABELS = ("Dx", "Dy", "Dz", "Rx", "Ry", "Rz")
_ELASTIC_LINK_DOF_LABELS = ("SDx", "SDy", "SDz", "SRx", "SRy", "SRz")


def _block_data_lines(mgt_text: str, tag: str) -> list[str]:
    """Return non-comment data lines for *TAG until the next *-block."""
    lines: list[str] = []
    in_block = False
    for raw in mgt_text.splitlines():
        stripped = raw.strip()
        if not in_block:
            if stripped.upper().startswith(f"*{tag.upper()}"):
                in_block = True
            continue
        if stripped.startswith("*"):
            break
        if stripped and not stripped.startswith(";"):
            lines.append(stripped)
    return lines


def _split_csv(line: str) -> list[str]:
    return [part.strip() for part in line.split(",")]


def _parse_int_token(token: str) -> int | None:
    try:
        value = float(str(token).strip())
    except ValueError:
        return None
    if abs(value - int(value)) <= 1.0e-9:
        return int(value)
    return None


def _expand_int_expr(expr: str) -> list[int]:
    out: list[int] = []
    tokens = str(expr).replace(",", " ").split()
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if idx + 2 < len(tokens) and tokens[idx + 1].lower() == "to":
            start = _parse_int_token(token)
            stop = _parse_int_token(tokens[idx + 2])
            step = 1
            consumed = 3
            if idx + 4 < len(tokens) and tokens[idx + 3].lower() == "by":
                parsed_step = _parse_int_token(tokens[idx + 4])
                if parsed_step is not None:
                    step = int(parsed_step)
                consumed = 5
            if start is not None and stop is not None and step > 0:
                if start <= stop:
                    out.extend(range(start, stop + 1, step))
                else:
                    out.extend(range(start, stop - 1, -step))
            idx += consumed
            continue
        by_match = _RANGE_BY_RE.match(token)
        if by_match:
            start = int(by_match.group(1))
            stop = int(by_match.group(2))
            step = int(by_match.group(3))
            if step <= 0:
                idx += 1
                continue
            if start <= stop:
                out.extend(range(start, stop + 1, step))
            else:
                out.extend(range(start, stop - 1, -step))
            idx += 1
            continue
        range_match = _RANGE_RE.match(token)
        if range_match:
            start = int(range_match.group(1))
            stop = int(range_match.group(2))
            if start <= stop:
                out.extend(range(start, stop + 1))
            else:
                out.extend(range(start, stop - 1, -1))
            idx += 1
            continue
        value = _parse_int_token(token)
        if value is not None:
            out.append(int(value))
        idx += 1
    return out


def _parse_float_token(token: str) -> float | None:
    try:
        return float(str(token).strip())
    except ValueError:
        return None


def _parse_pipe_from_name(name: str) -> dict[str, Any] | None:
    """Hollow circular pipe from labels like P 50x4 (mm outer diameter x wall thickness)."""
    match = _PIPE_NAME_RE.search(name)
    if not match:
        return None
    d_outer_m = float(match.group(1)) * 1.0e-3
    wall_m = float(match.group(2)) * 1.0e-3
    d_inner_m = max(d_outer_m - 2.0 * wall_m, 1.0e-6)
    if d_outer_m <= 0.0 or wall_m <= 0.0:
        return None
    area = math.pi / 4.0 * (d_outer_m**2 - d_inner_m**2)
    inertia = math.pi / 64.0 * (d_outer_m**4 - d_inner_m**4)
    return {
        "shape": "P",
        "B_m": d_outer_m,
        "H_m": wall_m,
        "A_m2": area,
        "Iy_m4": inertia,
        "Iz_m4": inertia,
    }


def _parse_sb_section(section_id: int, parts: list[str]) -> dict[str, Any] | None:
    shape_idx: int | None = None
    for idx, token in enumerate(parts):
        if token.upper() == "SB":
            shape_idx = idx
            break
    if shape_idx is None:
        return None
    try:
        dim_count = int(parts[shape_idx + 1])
        if dim_count < 2:
            return None
        h_m = float(parts[shape_idx + 2])
        b_m = float(parts[shape_idx + 3])
    except (IndexError, ValueError):
        return None
    if h_m <= 0.0 or b_m <= 0.0:
        return None
    area = b_m * h_m
    iy = b_m * h_m**3 / 12.0
    iz = h_m * b_m**3 / 12.0
    return {
        "shape": "SB",
        "B_m": b_m,
        "H_m": h_m,
        "A_m2": area,
        "Iy_m4": iy,
        "Iz_m4": iz,
    }


def _parse_section_row(parts: list[str]) -> dict[str, Any] | None:
    shape_tokens = {token.upper() for token in parts}
    if "SB" in shape_tokens:
        return _parse_sb_section(int(parts[0]), parts)
    if "P" in shape_tokens and len(parts) >= 3:
        return _parse_pipe_from_name(parts[2])
    return None


def parse_mgt_section_properties(mgt_text: str) -> dict[int, dict[str, Any]]:
    """Parse SB and P (*SECTION) entries; skip unknown shapes."""
    out: dict[int, dict[str, Any]] = {}
    for line in _block_data_lines(mgt_text, "SECTION"):
        parts = _split_csv(line)
        if not parts:
            continue
        try:
            section_id = int(parts[0])
        except ValueError:
            continue
        props = _parse_section_row(parts)
        if props is not None:
            out[section_id] = props
    return out


def _parse_thickness_row(parts: list[str]) -> dict[str, Any] | None:
    if len(parts) < 5:
        return None
    thickness_type = parts[1].strip().upper()
    if thickness_type != "VALUE":
        return None
    try:
        subtype = int(float(parts[2]))
        same_thickness = parts[3].strip().upper() in {"YES", "Y", "TRUE", "1"}
        thickness_in = float(parts[4])
        thickness_out = float(parts[5]) if len(parts) >= 6 and parts[5].strip() else 0.0
    except (IndexError, ValueError):
        return None
    if thickness_in <= 0.0 and thickness_out <= 0.0:
        return None
    effective = thickness_in if same_thickness or thickness_out <= 0.0 else 0.5 * (thickness_in + thickness_out)
    if effective <= 0.0:
        return None
    return {
        "type": thickness_type,
        "subtype": subtype,
        "same_thickness": same_thickness,
        "thickness_in_m": float(thickness_in),
        "thickness_out_m": float(thickness_out),
        "effective_thickness_m": float(effective),
    }


def parse_mgt_plate_thickness_properties(mgt_text: str) -> dict[int, dict[str, Any]]:
    """Parse *THICKNESS VALUE rows keyed by MIDAS plate thickness id."""
    out: dict[int, dict[str, Any]] = {}
    for line in _block_data_lines(mgt_text, "THICKNESS"):
        parts = _split_csv(line)
        if not parts:
            continue
        try:
            thickness_id = int(parts[0])
        except ValueError:
            continue
        props = _parse_thickness_row(parts)
        if props is not None:
            out[thickness_id] = props
    return out


def _elast_groups(parts: list[str]) -> list[tuple[float, float]]:
    """Find (E, poisson) pairs after MIDAS data-type token '2' (ELAST)."""
    groups: list[tuple[float, float]] = []
    for idx, token in enumerate(parts):
        if token != "2" or idx < 6:
            continue
        try:
            e_val = float(parts[idx + 1])
            nu_val = float(parts[idx + 2])
        except (IndexError, ValueError):
            continue
        if e_val <= 0.0:
            continue
        groups.append((e_val, nu_val))
    # Deduplicate consecutive identical parses from overlapping scans.
    deduped: list[tuple[float, float]] = []
    for pair in groups:
        if not deduped or pair != deduped[-1]:
            deduped.append(pair)
    # SRC rows contain two modulus groups; keep first two distinct E values.
    if len(deduped) >= 2 and deduped[0][0] == deduped[1][0]:
        deduped = [deduped[0], *deduped[2:]]
    return deduped


def _parse_material_row(parts: list[str]) -> dict[str, Any] | None:
    if len(parts) < 4:
        return None
    mat_type = parts[1].strip().upper()
    name = parts[2].strip()
    groups = _elast_groups(parts)
    if not groups:
        return None
    e_primary, poisson = groups[0]
    result: dict[str, Any] = {
        "type": mat_type,
        "name": name,
        "E_kN_per_m2": e_primary,
        "poisson": poisson,
    }
    if mat_type == "SRC" and len(groups) >= 2:
        result["E_secondary_kN_per_m2"] = groups[1][0]
    return result


def parse_mgt_material_properties(mgt_text: str) -> dict[int, dict[str, Any]]:
    """Parse *MATERIAL elastic moduli (kN/m²) and Poisson ratios."""
    out: dict[int, dict[str, Any]] = {}
    for line in _block_data_lines(mgt_text, "MATERIAL"):
        parts = _split_csv(line)
        if not parts:
            continue
        try:
            material_id = int(parts[0])
        except ValueError:
            continue
        props = _parse_material_row(parts)
        if props is not None:
            out[material_id] = props
    return out


def _parse_global_offset_row(parts: list[str]) -> dict[str, Any] | None:
    if len(parts) < 8:
        return None
    values = [_parse_float_token(part) for part in parts[2:8]]
    if any(value is None for value in values):
        return None
    floats = [float(value) for value in values if value is not None]
    return {
        "coordinate_system": "GLOBAL",
        "value_schema": "global_xyz_i_j",
        "i_offset_m": {"x": floats[0], "y": floats[1], "z": floats[2]},
        "j_offset_m": {"x": floats[3], "y": floats[4], "z": floats[5]},
        "offset_values_m": floats,
        "group": str(parts[8]).strip() if len(parts) >= 9 else "",
    }


def _parse_element_offset_row(parts: list[str]) -> dict[str, Any] | None:
    if len(parts) < 6:
        return None
    values = [_parse_float_token(part) for part in parts[2:6]]
    if any(value is None for value in values):
        return None
    floats = [float(value) for value in values if value is not None]
    return {
        "coordinate_system": "ELEMENT",
        "value_schema": "element_yz_i_j",
        "i_offset_m": {"y": floats[0], "z": floats[1]},
        "j_offset_m": {"y": floats[2], "z": floats[3]},
        "offset_values_m": floats,
        "group": str(parts[6]).strip() if len(parts) >= 7 else "",
    }


def parse_mgt_beam_end_offsets(mgt_text: str) -> list[dict[str, Any]]:
    """Parse MIDAS *OFFSET beam end offsets into typed runtime metadata.

    GLOBAL rows carry six xyz offsets: i-end xyz followed by j-end xyz.
    ELEMENT rows carry four local yz offsets: i-end yz followed by j-end yz.
    """
    out: list[dict[str, Any]] = []
    for row_index, line in enumerate(_block_data_lines(mgt_text, "OFFSET"), start=1):
        parts = _split_csv(line)
        if len(parts) < 2:
            continue
        element_ids = _expand_int_expr(parts[0])
        if not element_ids:
            continue
        offset_type = str(parts[1]).strip().upper()
        if offset_type == "GLOBAL":
            parsed = _parse_global_offset_row(parts)
        elif offset_type == "ELEMENT":
            parsed = _parse_element_offset_row(parts)
        else:
            numeric_values = [
                float(value)
                for value in (_parse_float_token(part) for part in parts[2:])
                if value is not None
            ]
            parsed = {
                "coordinate_system": offset_type or "UNKNOWN",
                "value_schema": "unknown_numeric_tail",
                "i_offset_m": {},
                "j_offset_m": {},
                "offset_values_m": numeric_values,
                "group": "",
            }
        if parsed is None:
            continue
        parsed.update(
            {
                "row_index": int(row_index),
                "element_ids": [int(element_id) for element_id in element_ids],
                "element_count": int(len(element_ids)),
                "raw": str(line).strip(),
            }
        )
        out.append(parsed)
    return out


def _parse_bool_token(token: str) -> bool | None:
    value = str(token).strip().upper()
    if value in {"YES", "Y", "TRUE", "T", "1"}:
        return True
    if value in {"NO", "N", "FALSE", "F", "0"}:
        return False
    return None


def _parse_restraint_code(token: str) -> tuple[str, dict[str, bool]] | None:
    code = "".join(ch for ch in str(token).strip() if ch in {"0", "1"})
    if len(code) < len(_SUPPORT_DOF_LABELS):
        return None
    code = code[: len(_SUPPORT_DOF_LABELS)]
    return code, {label: flag == "1" for label, flag in zip(_SUPPORT_DOF_LABELS, code, strict=True)}


def parse_mgt_support_constraints(mgt_text: str) -> list[dict[str, Any]]:
    """Parse MIDAS *CONSTRAINT support rows into typed node restraint metadata."""
    out: list[dict[str, Any]] = []
    for row_index, line in enumerate(_block_data_lines(mgt_text, "CONSTRAINT"), start=1):
        parts = _split_csv(line)
        if len(parts) < 2:
            continue
        node_ids = _expand_int_expr(parts[0])
        restraint = _parse_restraint_code(parts[1])
        if not node_ids or restraint is None:
            continue
        code, mask = restraint
        out.append(
            {
                "row_index": int(row_index),
                "node_ids": [int(node_id) for node_id in node_ids],
                "node_count": int(len(node_ids)),
                "restraint_code": code,
                "restraint_mask": mask,
                "restrained_dofs": [label for label, is_restrained in mask.items() if is_restrained],
                "released_dofs": [label for label, is_restrained in mask.items() if not is_restrained],
                "group": str(parts[2]).strip() if len(parts) >= 3 else "",
                "raw": str(line).strip(),
            }
        )
    return out


def _parse_elastic_link_row(parts: list[str], row_index: int, raw: str) -> dict[str, Any] | None:
    if len(parts) < 5:
        return None
    link_id = _parse_int_token(parts[0])
    node_i = _parse_int_token(parts[1])
    node_j = _parse_int_token(parts[2])
    if link_id is None or node_i is None or node_j is None:
        return None
    link_type = str(parts[3]).strip().upper()
    angle = _parse_float_token(parts[4])
    payload: dict[str, Any] = {
        "row_index": int(row_index),
        "id": int(link_id),
        "node_i": int(node_i),
        "node_j": int(node_j),
        "link_type": link_type,
        "angle_deg": float(angle) if angle is not None else 0.0,
        "group": "",
        "raw": str(raw).strip(),
    }
    if link_type == "GEN" and len(parts) >= 17:
        release_flags = {
            label: _parse_bool_token(parts[idx])
            for label, idx in zip(_ELASTIC_LINK_DOF_LABELS, range(5, 11), strict=True)
        }
        stiffness = {
            label: float(value)
            for label, value in zip(
                _ELASTIC_LINK_DOF_LABELS,
                (_parse_float_token(part) for part in parts[11:17]),
                strict=True,
            )
            if value is not None
        }
        shear_token = parts[17] if len(parts) >= 18 else ""
        dry = _parse_float_token(parts[18]) if len(parts) >= 19 else None
        drz = _parse_float_token(parts[19]) if len(parts) >= 20 else None
        payload.update(
            {
                "release_flags": release_flags,
                "stiffness": stiffness,
                "stiffness_abs_max": float(max((abs(v) for v in stiffness.values()), default=0.0)),
                "stiffness_abs_min_nonzero": float(
                    min((abs(v) for v in stiffness.values() if abs(v) > 0.0), default=0.0)
                ),
                "b_shear": _parse_bool_token(shear_token),
                "direction_ratio_y": float(dry) if dry is not None else None,
                "direction_ratio_z": float(drz) if drz is not None else None,
                "group": str(parts[20]).strip() if len(parts) >= 21 else "",
            }
        )
    else:
        numeric_tail = [
            float(value)
            for value in (_parse_float_token(part) for part in parts[5:])
            if value is not None
        ]
        payload.update(
            {
                "numeric_tail": numeric_tail,
                "stiffness_abs_max": float(max((abs(v) for v in numeric_tail), default=0.0)),
                "group": str(parts[-1]).strip() if len(parts) >= 6 else "",
            }
        )
    return payload


def parse_mgt_elastic_links(mgt_text: str) -> list[dict[str, Any]]:
    """Parse MIDAS *ELASTICLINK rows into typed link metadata."""
    out: list[dict[str, Any]] = []
    for row_index, line in enumerate(_block_data_lines(mgt_text, "ELASTICLINK"), start=1):
        parts = _split_csv(line)
        parsed = _parse_elastic_link_row(parts, row_index, line)
        if parsed is not None:
            out.append(parsed)
    return out


def parse_mgt_story_eccentricity(mgt_text: str) -> dict[str, Any]:
    """Parse MIDAS *STORY-ECCEN into typed seismic/wind eccentricity settings."""
    rows = _block_data_lines(mgt_text, "STORY-ECCEN")
    for row_index, line in enumerate(rows, start=1):
        parts = _split_csv(line)
        if len(parts) < 4:
            continue
        seismic_ecc = _parse_float_token(parts[2])
        wind_ecc = _parse_float_token(parts[3])
        return {
            "row_index": int(row_index),
            "include_seismic_eccentricity": bool(_parse_bool_token(parts[0])),
            "include_wind_eccentricity": bool(_parse_bool_token(parts[1])),
            "seismic_eccentricity_percent": float(seismic_ecc) if seismic_ecc is not None else 0.0,
            "wind_eccentricity_percent": float(wind_ecc) if wind_ecc is not None else 0.0,
            "raw": str(line).strip(),
        }
    return {}


def parse_mgt_boundary_groups(mgt_text: str) -> list[dict[str, Any]]:
    """Parse MIDAS *BNDR-GROUP rows into typed boundary group metadata."""
    out: list[dict[str, Any]] = []
    for row_index, line in enumerate(_block_data_lines(mgt_text, "BNDR-GROUP"), start=1):
        parts = _split_csv(line)
        if not parts or not parts[0].strip():
            continue
        auto_type = _parse_int_token(parts[1]) if len(parts) >= 2 else None
        out.append(
            {
                "row_index": int(row_index),
                "name": str(parts[0]).strip(),
                "auto_type": int(auto_type) if auto_type is not None else None,
                "raw": str(line).strip(),
            }
        )
    return out


def parse_mgt_element_local_axis_rows(mgt_text: str) -> list[dict[str, Any]]:
    """Parse frame ANGLE and planar LCAXIS-like fields from MIDAS *ELEMENT rows."""
    out: list[dict[str, Any]] = []
    line_types = {"BEAM", "TRUSS", "TENSTR", "COMPTR"}
    planar_types = {"PLATE", "WALL", "PLANE"}
    for row_index, line in enumerate(_block_data_lines(mgt_text, "ELEMENT"), start=1):
        parts = _split_csv(line)
        if len(parts) < 2:
            continue
        elem_id = _parse_int_token(parts[0])
        if elem_id is None:
            continue
        elem_type = str(parts[1]).strip().upper()
        if elem_type in line_types:
            angle = _parse_float_token(parts[6]) if len(parts) >= 7 else None
            sub_type = _parse_int_token(parts[7]) if len(parts) >= 8 else None
            out.append(
                {
                    "row_index": int(row_index),
                    "element_id": int(elem_id),
                    "type": elem_type,
                    "family": "line",
                    "angle_deg": float(angle) if angle is not None else 0.0,
                    "angle_token_present": bool(len(parts) >= 7),
                    "subtype": int(sub_type) if sub_type is not None else None,
                    "token_count": int(len(parts)),
                    "raw": str(line).strip(),
                }
            )
            continue
        if elem_type in planar_types:
            lcaxis = None
            lcaxis_source = "missing"
            lcaxis_token_present = False
            if len(parts) >= 11:
                lcaxis = _parse_int_token(parts[10])
                lcaxis_source = "explicit_lcaxis_token"
                lcaxis_token_present = True
            elif len(parts) >= 10:
                # Compact planar rows keep WIDTH_ID at parts[9] and omit the
                # trailing LCAXIS token. Treat LCAXIS as source-default instead
                # of aliasing WIDTH_ID into two fields.
                lcaxis = None
                lcaxis_source = "default_lcaxis_token_omitted"
            sub_type = _parse_int_token(parts[8]) if len(parts) >= 9 else None
            width_id = _parse_int_token(parts[9]) if len(parts) >= 10 else None
            out.append(
                {
                    "row_index": int(row_index),
                    "element_id": int(elem_id),
                    "type": elem_type,
                    "family": "surface",
                    "lcaxis_code": int(lcaxis) if lcaxis is not None else 0,
                    "lcaxis_token_present": lcaxis_token_present,
                    "lcaxis_source": lcaxis_source,
                    "subtype": int(sub_type) if sub_type is not None else None,
                    "width_id": int(width_id) if width_id is not None else None,
                    "token_count": int(len(parts)),
                    "raw": str(line).strip(),
                }
            )
    return out


def scan_mgt_opening_source_markers(mgt_text: str) -> dict[str, Any]:
    """Return a conservative source inventory for opening/hole/void MGT markers."""
    marker_tokens = ("OPEN", "HOLE", "VOID")
    block_names: list[str] = []
    marker_rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(mgt_text.splitlines(), start=1):
        stripped = raw.strip()
        upper = stripped.upper()
        if stripped.startswith("*"):
            block_name = upper.split(";", 1)[0].strip().lstrip("*")
            if any(token in block_name for token in marker_tokens):
                block_names.append(block_name)
        if any(token in upper for token in marker_tokens):
            marker_rows.append(
                {
                    "line_number": int(line_number),
                    "text": stripped[:240],
                }
            )
    return {
        "opening_marker_block_names": sorted(set(block_names)),
        "opening_marker_block_count": int(len(set(block_names))),
        "opening_marker_row_count": int(len(marker_rows)),
        "opening_marker_rows_head": marker_rows[:20],
    }


def load_mgt_section_material_properties(mgt_path: Path) -> dict[str, Any]:
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "sections": parse_mgt_section_properties(text),
        "materials": parse_mgt_material_properties(text),
        "plate_thicknesses": parse_mgt_plate_thickness_properties(text),
        "beam_end_offsets": parse_mgt_beam_end_offsets(text),
        "support_constraints": parse_mgt_support_constraints(text),
        "elastic_links": parse_mgt_elastic_links(text),
        "story_eccentricity": parse_mgt_story_eccentricity(text),
        "boundary_groups": parse_mgt_boundary_groups(text),
        "element_local_axes": parse_mgt_element_local_axis_rows(text),
        "opening_source_markers": scan_mgt_opening_source_markers(text),
    }
