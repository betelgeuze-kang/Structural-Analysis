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


def load_mgt_section_material_properties(mgt_path: Path) -> dict[str, Any]:
    text = mgt_path.read_text(encoding="utf-8", errors="ignore")
    return {
        "sections": parse_mgt_section_properties(text),
        "materials": parse_mgt_material_properties(text),
    }
