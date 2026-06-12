#!/usr/bin/env python3
"""Parse MIDAS .mgt model text into AI-friendly JSON + NPZ graph tensors.

This parser intentionally handles field-export variance while staying strict on
graph topology extraction:
- strict element node-slot parsing (prevents non-node ints from polluting graph)
- rigid-link resolution / dummy-node coarsening
- source-provenance and contract report output
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from runtime_contracts import InputContractError, get_logger, log_event, validate_input_contract
try:
    from section_library_and_mesher import (
        LoadPatternDraft,
        LoadPrimitive,
        SectionCatalog,
        SectionTemplate,
        build_load_pattern_summary,
    )
except ImportError:  # pragma: no cover - package import fallback for test/module usage
    from implementation.phase1.section_library_and_mesher import (
        LoadPatternDraft,
        LoadPrimitive,
        SectionCatalog,
        SectionTemplate,
        build_load_pattern_summary,
    )


REASONS = {
    "PASS": "midas mgt conversion passed",
    "ERR_INVALID_INPUT": "invalid converter input",
    "ERR_FILE_MISSING": "mgt input file missing",
    "ERR_PARSE_FAIL": "failed to parse essential node/element blocks",
    "ERR_SYNTHETIC_SOURCE": "synthetic/toy source blocked in strict mode",
    "ERR_SHELL_BEAM_MIX": "shell-beam mix requirement not satisfied",
    "ERR_UNKNOWN_SECTION": "unknown section(s) blocked by strict section policy",
    "ERR_ELEMENT_SKIP_BUDGET": "element skip budget exceeded",
}

INPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mgt", "json_out", "npz_out", "report_out"],
    "properties": {
        "mgt": {"type": "string", "minLength": 1},
        "json_out": {"type": "string", "minLength": 1},
        "npz_out": {"type": "string", "minLength": 1},
        "report_out": {"type": "string", "minLength": 1},
        "edge_list_out": {"type": "string"},
        "forbid_synthetic_source": {"type": "boolean"},
        "require_shell_beam_mix": {"type": "boolean"},
        "min_nodes": {"type": "integer", "minimum": 2},
        "min_elements": {"type": "integer", "minimum": 1},
        "resolve_rigid_links": {"type": "boolean"},
        "rigid_stiffness_threshold": {"type": "number", "minimum": 0.0},
        "drop_unreferenced_nodes": {"type": "boolean"},
        "strict_unknown_sections": {"type": "boolean"},
        "max_element_skip_count": {"type": "integer", "minimum": 0},
        "max_element_skip_ratio": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}

_SYNTHETIC_MARKER_RE = re.compile(r"(toy|sample|atwood|synthetic|mock)", re.IGNORECASE)
_RANGE_BY_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*by\s*(\d+)\s*$", re.IGNORECASE)
_RANGE_RE = re.compile(r"^\s*(\d+)\s*to\s*(\d+)\s*$", re.IGNORECASE)
_KNOWN_SECTIONS = {
    "ROOT",
    "UNIT",
    "NODE",
    "ELEMENT",
    "MATERIAL",
    "SECTION",
    "CONSTRAINT",
    "ELASTICLINK",
    "BOUNDARY",
    "SUPPORT",
    "LOAD",
    "LOADCASE",
    "LOADCOMB",
    "USE-STLD",
    "STATICLOAD",
    "DYNAMICLOAD",
    "MASS",
    "NODALMASS",
    "DAMPING",
    "CONLOAD",
    "OFFSET",
    "PRESSURE",
    "SELFWEIGHT",
    "STLDCASE",
    "ANALYSIS",
    "ENDDATA",
    "BNDR-GROUP",
    "DGN-MATL",
    "DGN-SECT",
    "DOMAIN-ELEMENT",
    "EIGEN-CTRL",
    "GROUP",
    "LC-COLOR",
    "LENGTH",
    "MAIN-DOMAIN",
    "MATL-COLOR",
    "MEMBER",
    "REBAR-MATL-CODE",
    "SECT-COLOR",
    "SECT-SCALE",
    "STORY-ECCEN",
    "STRUCTYPE",
    "THICKNESS",
    "THIK-COLOR",
    "VERSION",
}
_STEEL_SECTION_MARKERS = {"SB", "H", "I", "BOX", "PIPE", "TUBE", "PLATE-GIRDER", "STEEL", "BH"}
_RC_SECTION_MARKERS = {"RC", "CONC", "SLAB", "WALL", "MAT", "PLATE"}
_COMPOSITE_SECTION_MARKERS = {"CFT", "SRC", "COMPOSITE", "DECK", "COMPO"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _clean_line(s: str) -> str:
    raw = str(s).rstrip()
    stripped = raw.lstrip()
    if not stripped:
        return ""
    if stripped.startswith("#") or stripped.startswith("$"):
        return ""
    if ";" in raw:
        raw = raw.split(";", 1)[0]
    return raw.strip()


def _split_csv_like(s: str) -> list[str]:
    return [tok.strip() for tok in s.split(",") if tok.strip()]


def _as_int(tok: str) -> int | None:
    t = tok.strip()
    if not t:
        return None
    try:
        v = float(t)
        if abs(v - int(v)) <= 1e-9:
            return int(v)
    except Exception:
        return None
    return None


def _as_float(tok: str) -> float | None:
    t = tok.strip()
    if not t:
        return None
    try:
        return float(t)
    except Exception:
        return None


def _is_truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _token_has_payload_value(tok: str) -> bool:
    text = str(tok).strip()
    if not text:
        return False
    if text.upper() in {"NO", "NONE", "N/A"}:
        return False
    if text in {"0", "0.0", "0.00", "0.0000", "0.0000E+00", "0.0000e+00"}:
        return False
    try:
        return abs(float(text)) > 1.0e-12
    except Exception:
        return True


def _parse_design_material_rebar_payloads(rows: list[dict]) -> list[dict]:
    payloads: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        material_id = int(row.get("material_id", 0) or 0)
        row_tokens = row.get("row_tokens") if isinstance(row.get("row_tokens"), list) else []
        first = row_tokens[0] if row_tokens and isinstance(row_tokens[0], list) else []
        material_type = str(first[1]).strip().upper() if len(first) >= 2 else ""
        material_name = str(first[2]).strip() if len(first) >= 3 else ""
        payload = {
            "material_id": material_id,
            "material_type": material_type,
            "material_name": material_name,
            "payload_basis": "unsupported_material_type",
            "payload_present": False,
            "rbcode": "",
            "rbmain": "",
            "rbsub": "",
            "fy_r": None,
            "fys": None,
        }
        if material_type == "CONC" and len(first) >= 14:
            rbcode = str(first[9]).strip()
            rbmain = str(first[10]).strip()
            rbsub = str(first[11]).strip()
            fy_r = _as_float(str(first[12]))
            fys = _as_float(str(first[13]))
            payload.update(
                {
                    "payload_basis": "concrete_r_data",
                    "rbcode": rbcode,
                    "rbmain": rbmain,
                    "rbsub": rbsub,
                    "fy_r": float(fy_r) if fy_r is not None else None,
                    "fys": float(fys) if fys is not None else None,
                }
            )
            payload["payload_present"] = bool(
                _token_has_payload_value(rbcode)
                or _token_has_payload_value(rbmain)
                or _token_has_payload_value(rbsub)
                or (fy_r is not None and abs(float(fy_r)) > 1.0e-12)
                or (fys is not None and abs(float(fys)) > 1.0e-12)
            )
        payloads.append(payload)
    return payloads


def _element_arity_hint(etype: str) -> int | None:
    k = str(etype).strip().upper()
    if any(x in k for x in ("PLATE", "SHELL", "WALL", "QUAD")):
        return 4
    if "TRI" in k:
        return 3
    if any(x in k for x in ("SOLID", "BRICK", "HEX")):
        return 8
    if any(x in k for x in ("BEAM", "TRUSS", "FRAME", "COLUMN", "LINK", "COMPTR")):
        return 2
    return None


def _canonical_element_family(etype: str) -> str:
    k = str(etype).strip().upper()
    if any(x in k for x in ("PLATE", "SHELL", "WALL", "QUAD", "TRI", "SOLID", "BRICK", "HEX")):
        return "shell"
    if any(x in k for x in ("BEAM", "TRUSS", "FRAME", "COLUMN", "LINK", "COMPTR")):
        return "beam"
    return "other"


def _parse_sections(path: Path) -> tuple[dict[str, list[str]], list[dict[str, object]], int]:
    sections: dict[str, list[str]] = defaultdict(list)
    blocks: list[dict[str, object]] = []
    current = "ROOT"
    current_block: dict[str, object] | None = None
    line_count = 0
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line_count += 1
        line = _clean_line(raw)
        if not line:
            continue
        if line.startswith("*"):
            header = line[1:].strip()
            key = header.split(",", 1)[0].strip().upper() or "ROOT"
            args = [tok.strip() for tok in header.split(",")[1:] if tok.strip()] if "," in header else []
            current = key
            current_block = {"key": current, "args": args, "rows": []}
            blocks.append(current_block)
            continue
        sections[current].append(line)
        if current_block is None:
            current_block = {"key": current, "args": [], "rows": []}
            blocks.append(current_block)
        rows = current_block.get("rows")
        if isinstance(rows, list):
            rows.append(line)
    return dict(sections), blocks, line_count


def _collect_parser_diagnostics(
    *,
    sections: dict[str, list[str]],
    node_rows: int,
    node_count: int,
    element_rows: int,
    element_count: int,
    material_rows: int,
    material_count: int,
    section_rows: int,
    section_count: int,
    constraint_rows: int,
    elastic_link_rows: int,
    typed_section_rows: dict[str, int] | None = None,
    element_parse_diag: dict[str, object] | None = None,
) -> dict[str, object]:
    unknown_sections = sorted([k for k in sections.keys() if k not in _KNOWN_SECTIONS])
    unknown_section_rows = {k: int(len(sections.get(k, []))) for k in unknown_sections}
    unknown_row_total = int(sum(unknown_section_rows.values()))
    typed_section_rows = {str(k): int(v) for k, v in (typed_section_rows or {}).items() if int(v) > 0}
    warnings: list[str] = []
    element_parse_diag = element_parse_diag if isinstance(element_parse_diag, dict) else {}
    element_rows_skipped = int(element_parse_diag.get("skipped_count", max(0, element_rows - element_count)))
    if unknown_sections:
        warnings.append(
            "unknown sections preserved as raw text: "
            + ",".join(unknown_sections[:16])
            + ("..." if len(unknown_sections) > 16 else "")
        )
    if node_rows > node_count:
        warnings.append(f"node rows skipped: {int(node_rows - node_count)}")
    if element_rows_skipped > 0:
        warnings.append(f"element rows skipped: {int(element_rows_skipped)}")
    return {
        "known_section_count": int(sum(1 for k in sections.keys() if k in _KNOWN_SECTIONS)),
        "unknown_section_count": int(len(unknown_sections)),
        "unknown_sections": unknown_sections,
        "unknown_section_row_count": unknown_section_rows,
        "unknown_row_total": int(unknown_row_total),
        "typed_section_count": int(len(typed_section_rows)),
        "typed_section_row_count": typed_section_rows,
        "typed_row_total": int(sum(typed_section_rows.values())),
        "row_parse": {
            "node_rows": int(node_rows),
            "node_rows_parsed": int(node_count),
            "node_rows_skipped": int(max(0, node_rows - node_count)),
            "element_rows": int(element_rows),
            "element_rows_parsed": int(element_count),
            "element_rows_skipped": int(element_rows_skipped),
            "element_skip_ratio": float(element_rows_skipped / max(1, element_rows)),
            "material_rows": int(material_rows),
            "material_rows_parsed": int(material_count),
            "section_rows": int(section_rows),
            "section_rows_parsed": int(section_count),
            "constraint_rows": int(constraint_rows),
            "elastic_link_rows": int(elastic_link_rows),
        },
        "element_skip_reason_count": {
            str(k): int(v)
            for k, v in sorted((element_parse_diag.get("skip_reason_count") or {}).items())
        },
        "unsupported_element_type_count": {
            str(k): int(v)
            for k, v in sorted((element_parse_diag.get("unsupported_type_count") or {}).items())
        },
        "unresolved_elements_head": list(element_parse_diag.get("unresolved_head") or []),
        "warnings_head": warnings[:16],
    }


def _parse_nodes(rows: list[str]) -> dict[int, tuple[float, float, float]]:
    nodes: dict[int, tuple[float, float, float]] = {}
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 4:
            continue
        nid = _as_int(toks[0])
        if nid is None:
            continue
        x = _as_float(toks[1])
        y = _as_float(toks[2])
        z = _as_float(toks[3])
        if x is None or y is None or z is None:
            continue
        nodes[int(nid)] = (float(x), float(y), float(z))
    return nodes


def _extract_node_span(token: str) -> list[int]:
    tok = token.strip()
    if not tok:
        return []
    m = _RANGE_BY_RE.match(tok)
    if m:
        a, b, step = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if step <= 0:
            return []
        if a <= b:
            return list(range(a, b + 1, step))
        return list(range(a, b - 1, -step))
    m = _RANGE_RE.match(tok)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            return list(range(a, b + 1))
        return list(range(a, b - 1, -1))
    v = _as_int(tok)
    return [int(v)] if v is not None else []


def _expand_node_expr(expr: str) -> list[int]:
    out: list[int] = []
    for tok in str(expr).replace(",", " ").split():
        out.extend(_extract_node_span(tok))
    return out


def _parse_constraint_rows(rows: list[str], node_ids: set[int]) -> dict[str, object]:
    support_nodes: set[int] = set()
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 2:
            continue
        nlist = _expand_node_expr(toks[0])
        for nid in nlist:
            if int(nid) in node_ids:
                support_nodes.add(int(nid))
    return {
        "constraint_row_count": int(len(rows)),
        "support_node_count": int(len(support_nodes)),
        "support_nodes": sorted(support_nodes),
    }


def _parse_static_load_cases(rows: list[str]) -> list[dict]:
    cases: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if not toks:
            continue
        name = str(toks[0]).strip()
        if not name:
            continue
        cases.append(
            {
                "name": name,
                "type": str(toks[1]).strip() if len(toks) >= 2 else "",
                "description": str(toks[2]).strip() if len(toks) >= 3 else "",
            }
        )
    return cases


def _parse_loadcase_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if not toks:
            continue
        name = str(toks[0]).strip()
        if not name:
            continue
        category = str(toks[1]).strip() if len(toks) >= 2 else ""
        subtype = str(toks[2]).strip() if len(toks) >= 3 else ""
        scale = _as_float(toks[3]) if len(toks) >= 4 else None
        load_refs = [str(tok).strip() for tok in toks[4:] if str(tok).strip()]
        out.append(
            {
                "name": name,
                "category": category,
                "subtype": subtype,
                "scale": float(scale) if scale is not None else 1.0,
                "load_refs": load_refs,
                "raw_token_count": int(len(toks)),
                "raw": str(row).strip(),
            }
        )
    return out


_LOADCASE_ALIAS = {
    "D": "DEAD",
    "DL": "DEAD",
    "L": "LIVE",
    "LL": "LIVE",
    "LLR": "ROOF_LIVE",
    "R": "ROOF_LIVE",
    "S": "SNOW",
    "E": "SEISMIC",
    "EX": "SEISMIC_X",
    "EY": "SEISMIC_Y",
    "WX": "WIND_X",
    "WY": "WIND_Y",
}


def _normalize_load_reference(token: str) -> str:
    text = str(token).strip()
    if not text:
        return ""
    text = text.replace(" ", "")
    if text.upper().startswith("NAME="):
        text = text.split("=", 1)[1].strip()
    upper = text.upper()
    return _LOADCASE_ALIAS.get(upper, upper)


def _normalize_combination_reference(token: str) -> str:
    text = str(token).strip()
    if not text:
        return ""
    if text.upper().startswith("NAME="):
        text = text.split("=", 1)[1].strip()
    return text


def _extract_expression_components(expression: str) -> list[dict]:
    expr = str(expression or "").strip()
    if not expr:
        return []
    cleaned = re.sub(r"(?i)\bSERV\s*:", "", expr).strip()

    def _merge_nested_factor(match: re.Match[str]) -> str:
        outer = _as_float(str(match.group(1)))
        inner = _as_float(str(match.group(2)))
        case_name = str(match.group(3)).strip()
        factor = float((outer if outer is not None else 1.0) * (inner if inner is not None else 1.0))
        return f"{factor:.12g}({case_name})"

    cleaned = re.sub(
        r"([+-]?\d+(?:\.\d+)?)\s*\(\s*([+-]?\d+(?:\.\d+)?)\s*\)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)",
        _merge_nested_factor,
        cleaned,
    )
    parts: list[dict] = []
    for match in re.finditer(r"([+-]?\s*(?:\d+(?:\.\d+)?)?)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", cleaned):
        raw_factor = str(match.group(1) or "").replace(" ", "")
        if raw_factor in {"", "+"}:
            factor = 1.0
        elif raw_factor == "-":
            factor = -1.0
        else:
            parsed = _as_float(raw_factor)
            factor = float(parsed) if parsed is not None else 1.0
        case_name = _normalize_load_reference(str(match.group(2)))
        if case_name:
            parts.append(
                {
                    "kind": "case",
                    "name": case_name,
                    "factor": float(factor),
                }
            )
    return parts


def _build_case_factor_map(expression_components: list[dict], entries: list[dict]) -> dict[str, float]:
    factor_map: dict[str, float] = {}
    st_entries = [
        entry
        for entry in entries
        if str(entry.get("reference_kind", "")).upper() == "ST"
    ]
    cb_entries = [
        entry
        for entry in entries
        if str(entry.get("reference_kind", "")).upper() == "CB"
    ]
    if st_entries:
        for entry in st_entries:
            name = _normalize_load_reference(str(entry.get("reference_name", "")))
            if not name:
                continue
            factor_map[name] = float(factor_map.get(name, 0.0) + float(entry.get("factor", 0.0)))
        return {str(k): float(v) for k, v in sorted(factor_map.items())}
    if cb_entries:
        return {}
    if expression_components:
        for item in expression_components:
            if str(item.get("kind", "")).lower() != "case":
                continue
            name = _normalize_load_reference(str(item.get("name", "")))
            if not name:
                continue
            factor_map[name] = float(factor_map.get(name, 0.0) + float(item.get("factor", 0.0)))
        return {str(k): float(v) for k, v in sorted(factor_map.items())}
    return {str(k): float(v) for k, v in sorted(factor_map.items())}


def _build_load_combination_graph(load_combinations: list[dict]) -> dict[str, object]:
    combo_by_name = {str(row.get("name", "")).strip(): row for row in load_combinations if str(row.get("name", "")).strip()}
    edge_rows: list[dict] = []
    case_nodes: set[str] = set()
    combo_nodes: set[str] = set(combo_by_name.keys())
    for combo_name, combo in combo_by_name.items():
        for case_name, factor in sorted((combo.get("factor_map") or {}).items()):
            case_nodes.add(str(case_name))
            edge_rows.append(
                {
                    "src": f"COMBO:{combo_name}",
                    "dst": f"CASE:{case_name}",
                    "kind": "case_factor",
                    "factor": float(factor),
                }
            )
        for child in combo.get("referenced_combinations") or []:
            edge_rows.append(
                {
                    "src": f"COMBO:{combo_name}",
                    "dst": f"COMBO:{child}",
                    "kind": "combo_ref",
                    "factor": 1.0,
                }
            )

    cache: dict[str, dict[str, object]] = {}

    def _resolve(name: str, stack: tuple[str, ...]) -> dict[str, object]:
        if name in cache:
            return cache[name]
        if name in stack:
            return {
                "expanded_factor_map": {},
                "expansion_mode": "cycle_blocked",
                "expansion_depth": int(len(stack)),
                "referenced_leaf_cases": [],
            }
        combo = combo_by_name.get(name, {})
        direct = {str(k): float(v) for k, v in sorted((combo.get("factor_map") or {}).items())}
        refs = [str(v) for v in combo.get("referenced_combinations") or [] if str(v).strip()]
        if refs and not direct:
            merged: dict[str, float] = {}
            depth = 0
            for child in refs:
                child_resolved = _resolve(child, stack + (name,))
                depth = max(depth, int(child_resolved.get("expansion_depth", 0)))
                for case_name, factor in (child_resolved.get("expanded_factor_map") or {}).items():
                    merged[str(case_name)] = max(float(merged.get(str(case_name), 0.0)), float(factor))
            result = {
                "expanded_factor_map": {str(k): float(v) for k, v in sorted(merged.items())},
                "expansion_mode": "envelope_union",
                "expansion_depth": int(depth + 1),
                "referenced_leaf_cases": sorted(merged.keys()),
            }
        elif refs:
            merged = dict(direct)
            depth = 0
            for child in refs:
                child_resolved = _resolve(child, stack + (name,))
                depth = max(depth, int(child_resolved.get("expansion_depth", 0)))
                for case_name, factor in (child_resolved.get("expanded_factor_map") or {}).items():
                    merged[str(case_name)] = float(merged.get(str(case_name), 0.0) + float(factor))
            result = {
                "expanded_factor_map": {str(k): float(v) for k, v in sorted(merged.items())},
                "expansion_mode": "linear_plus_refs",
                "expansion_depth": int(depth + 1),
                "referenced_leaf_cases": sorted(merged.keys()),
            }
        else:
            result = {
                "expanded_factor_map": direct,
                "expansion_mode": "linear_combination",
                "expansion_depth": 1,
                "referenced_leaf_cases": sorted(direct.keys()),
            }
        cache[name] = result
        return result

    combo_summaries: list[dict] = []
    for name, combo in combo_by_name.items():
        resolved = _resolve(name, tuple())
        combo["expanded_factor_map"] = dict(resolved["expanded_factor_map"])
        combo["expansion_mode"] = str(resolved["expansion_mode"])
        combo["expansion_depth"] = int(resolved["expansion_depth"])
        combo["referenced_leaf_cases"] = list(resolved["referenced_leaf_cases"])
        combo_summaries.append(
            {
                "name": name,
                "expansion_mode": combo["expansion_mode"],
                "expansion_depth": combo["expansion_depth"],
                "expanded_factor_map": dict(combo["expanded_factor_map"]),
                "referenced_leaf_cases": list(combo["referenced_leaf_cases"]),
            }
        )
    return {
        "node_count": int(len(combo_nodes) + len(case_nodes)),
        "edge_count": int(len(edge_rows)),
        "combo_node_count": int(len(combo_nodes)),
        "case_node_count": int(len(case_nodes)),
        "nodes": [
            *(
                {
                    "id": f"COMBO:{name}",
                    "kind": "combo",
                    "name": str(name),
                }
                for name in sorted(combo_nodes)
            ),
            *(
                {
                    "id": f"CASE:{name}",
                    "kind": "case",
                    "name": str(name),
                }
                for name in sorted(case_nodes)
            ),
        ],
        "edges": edge_rows,
        "combo_summaries": combo_summaries,
    }


def _extract_combination_expression(toks: list[str]) -> str:
    candidates = [str(tok).strip() for tok in toks[3:] if str(tok).strip()]
    best = ""
    for token in candidates:
        if "(" in token and ")" in token and any(ch.isalpha() for ch in token):
            if len(token) > len(best):
                best = token
    return best


def _parse_loadcomb_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    current: dict | None = None

    def _flush_current() -> None:
        nonlocal current
        if current is None:
            return
        case_refs = sorted({entry["reference_name"] for entry in current["entries"] if entry["reference_kind"] == "ST"})
        combo_refs = sorted({entry["reference_name"] for entry in current["entries"] if entry["reference_kind"] == "CB"})
        factor_map = _build_case_factor_map(current["expression_components"], current["entries"])
        current["referenced_cases"] = case_refs
        current["referenced_combinations"] = combo_refs
        current["factor_map"] = factor_map
        current["entry_count"] = int(len(current["entries"]))
        current["expression_component_count"] = int(len(current["expression_components"]))
        out.append(current)
        current = None

    for joined, line_span in _join_continuation_rows(rows):
        toks = _split_csv_like(joined)
        if not toks:
            continue
        head = str(toks[0]).strip()
        if not head:
            continue
        head_upper = head.upper()
        if head_upper.startswith("NAME="):
            _flush_current()
            expression = _extract_combination_expression(toks)
            current = {
                "name": head.split("=", 1)[1].strip(),
                "combination_type": str(toks[1]).strip() if len(toks) >= 2 else "",
                "limit_state": str(toks[2]).strip() if len(toks) >= 3 else "",
                "generator_tokens": [str(tok).strip() for tok in toks[3:]],
                "expression": expression,
                "expression_components": _extract_expression_components(expression),
                "entries": [],
                "entry_line_count": 0,
                "raw_token_count": int(len(toks)),
                "raw_rows": [str(joined).strip()],
                "line_span_total": int(line_span),
            }
            continue

        if head_upper in {"ST", "CB"} and current is not None:
            entry_blocks = toks
            i = 0
            while i + 2 < len(entry_blocks):
                ref_kind = str(entry_blocks[i]).strip().upper()
                if ref_kind not in {"ST", "CB"}:
                    i += 1
                    continue
                if ref_kind == "CB":
                    ref_name = _normalize_combination_reference(str(entry_blocks[i + 1]))
                else:
                    ref_name = _normalize_load_reference(str(entry_blocks[i + 1]))
                parsed = _as_float(entry_blocks[i + 2])
                factor = float(parsed) if parsed is not None else 1.0
                current["entries"].append(
                    {
                        "reference_kind": ref_kind,
                        "reference_name": ref_name,
                        "factor": float(factor),
                    }
                )
                i += 3
            current["entry_line_count"] = int(current["entry_line_count"]) + 1
            current["raw_token_count"] = int(current["raw_token_count"]) + int(len(toks))
            current["line_span_total"] = int(current["line_span_total"]) + int(line_span)
            current["raw_rows"].append(str(joined).strip())
            continue

        _flush_current()
        name = head
        combo_type = str(toks[1]).strip() if len(toks) >= 2 else ""
        limit_state = str(toks[2]).strip() if len(toks) >= 3 else ""
        expression = _extract_combination_expression(toks)
        expression_components = _extract_expression_components(expression)
        entries: list[dict] = []
        tail = toks[3:] if len(toks) >= 4 else []
        if not expression_components:
            i = 0
            while i < len(tail):
                load_name = _normalize_load_reference(str(tail[i]))
                factor = 1.0
                if i + 1 < len(tail):
                    parsed = _as_float(tail[i + 1])
                    if parsed is not None:
                        factor = float(parsed)
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
                if load_name:
                    entries.append(
                        {
                            "reference_kind": "ST",
                            "reference_name": load_name,
                            "factor": float(factor),
                        }
                    )
        current = {
            "name": name,
            "combination_type": combo_type,
            "limit_state": limit_state,
            "generator_tokens": [str(tok).strip() for tok in toks[3:]],
            "expression": expression,
            "expression_components": expression_components,
            "entries": entries,
            "entry_line_count": 0,
            "raw_token_count": int(len(toks)),
            "raw_rows": [str(joined).strip()],
            "line_span_total": int(line_span),
        }
    _flush_current()
    return out


def _parse_selfweight_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 3:
            continue
        fx = _as_float(toks[0])
        fy = _as_float(toks[1])
        fz = _as_float(toks[2])
        if fx is None or fy is None or fz is None:
            continue
        out.append(
            {
                "gx": float(fx),
                "gy": float(fy),
                "gz": float(fz),
                "group": str(toks[3]).strip() if len(toks) >= 4 else "",
            }
        )
    return out


def _join_continuation_rows(rows: list[str]) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    buf: list[str] = []
    physical_count = 0
    for raw in rows:
        line = str(raw).rstrip()
        if not line:
            continue
        has_cont = line.endswith("\\")
        piece = line[:-1].rstrip() if has_cont else line
        buf.append(piece)
        physical_count += 1
        if not has_cont:
            joined = " ".join(part.strip() for part in buf if part.strip())
            if joined:
                out.append((joined, physical_count))
            buf = []
            physical_count = 0
    if buf:
        joined = " ".join(part.strip() for part in buf if part.strip())
        if joined:
            out.append((joined, physical_count))
    return out


def _parse_member_rows(rows: list[str], element_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for joined, line_span in _join_continuation_rows(rows):
        toks = _split_csv_like(joined)
        if len(toks) < 3:
            continue
        member_id = _as_int(toks[0])
        element_seed = _as_int(toks[1])
        if member_id is None:
            continue
        element_refs = [int(v) for v in (_as_int(tok) for tok in toks[3:]) if v is not None]
        mapped = [eid for eid in element_refs if eid in element_ids]
        out.append(
            {
                "id": int(member_id),
                "element_seed": int(element_seed) if element_seed is not None else -1,
                "reverse": str(toks[2]).strip().upper(),
                "element_ids": mapped,
                "element_ids_head": mapped[:32],
                "element_count": int(len(mapped)),
                "raw_token_count": int(len(toks)),
                "physical_line_span": int(line_span),
            }
        )
    return out


def _parse_group_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for joined, line_span in _join_continuation_rows(rows):
        toks = _split_csv_like(joined)
        if not toks:
            continue
        name = str(toks[0]).strip()
        if not name:
            continue
        node_expr = str(toks[1]).strip() if len(toks) >= 2 else ""
        elem_expr = str(toks[2]).strip() if len(toks) >= 3 else ""
        plane_type = ",".join(str(tok).strip() for tok in toks[3:]) if len(toks) >= 4 else ""
        node_ids = _expand_node_expr(node_expr)
        element_ids = _expand_node_expr(elem_expr)
        out.append(
            {
                "name": name,
                "node_expr": node_expr,
                "element_expr": elem_expr,
                "plane_type": plane_type,
                "node_count": int(len(node_ids)),
                "element_count": int(len(element_ids)),
                "node_ids": [int(v) for v in node_ids],
                "element_ids": [int(v) for v in element_ids],
                "node_ids_head": [int(v) for v in node_ids[:64]],
                "element_ids_head": [int(v) for v in element_ids[:64]],
                "physical_line_span": int(line_span),
            }
        )
    return out


def _parse_grouped_metadata_rows(rows: list[str], *, key_field: str) -> list[dict]:
    out: list[dict] = []
    current: dict | None = None
    for row in rows:
        toks = _split_csv_like(row)
        if not toks:
            continue
        key = _as_int(toks[0])
        if key is not None:
            if current is not None:
                out.append(current)
            current = {
                key_field: int(key),
                "row_tokens": [toks],
                "raw_row_count": 1,
            }
            continue
        if current is None:
            current = {
                key_field: -1,
                "row_tokens": [toks],
                "raw_row_count": 1,
            }
            continue
        current["row_tokens"].append(toks)
        current["raw_row_count"] = int(current.get("raw_row_count", 0)) + 1
    if current is not None:
        out.append(current)
    return out


def _parse_color_rows(rows: list[str], *, key_name: str) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 11:
            continue
        key = _as_int(toks[0])
        if key is None:
            continue
        rgb = [_as_int(tok) for tok in toks[1:10]]
        if any(v is None for v in rgb):
            continue
        out.append(
            {
                key_name: int(key),
                "wire_rgb": [int(rgb[0]), int(rgb[1]), int(rgb[2])],
                "fill_rgb": [int(rgb[3]), int(rgb[4]), int(rgb[5])],
                "highlight_rgb": [int(rgb[6]), int(rgb[7]), int(rgb[8])],
                "blend": str(toks[10]).strip().upper() if len(toks) >= 11 else "",
                "factor": float(_as_float(toks[11]) or 0.0) if len(toks) >= 12 else 0.0,
            }
        )
    return out


def _parse_scale_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = [tok.strip() for tok in str(row).split(",")]
        if len(toks) < 8:
            continue
        sec_id = _as_int(toks[0])
        values = [_as_float(tok) for tok in toks[1:8]]
        if sec_id is None or any(v is None for v in values):
            continue
        out.append(
            {
                "section_id": int(sec_id),
                "area_sf": float(values[0]),
                "asy_sf": float(values[1]),
                "asz_sf": float(values[2]),
                "ixx_sf": float(values[3]),
                "iyy_sf": float(values[4]),
                "izz_sf": float(values[5]),
                "weight_sf": float(values[6]),
                "group": str(toks[8]).strip() if len(toks) >= 9 else "",
                "part_id": int(_as_int(toks[9]) or 0) if len(toks) >= 10 else 0,
            }
        )
    return out


def _parse_token_rows(rows: list[str]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = [tok.strip() for tok in str(row).split(",")]
        toks = [tok for tok in toks if tok]
        if not toks:
            continue
        item = {
            "tokens": toks,
            "raw": str(row).strip(),
        }
        key = _as_int(toks[0])
        if key is not None:
            item["id"] = int(key)
        out.append(item)
    return out


def _axis_dimension_from_section_name(section_name: str) -> str:
    text = str(section_name or "").strip().upper().replace("_", "-")
    if not text or text in {"STORY-ECCEN"}:
        return ""
    if any(token in text for token in ("LEVEL", "STORY", "ELEV")):
        return "z"
    if any(token in text for token in ("AXIS-X", "X-AXIS", "GRID-X", "X-GRID", "GLINE-X", "X-LINE")):
        return "x"
    if any(token in text for token in ("AXIS-Y", "Y-AXIS", "GRID-Y", "Y-GRID", "GLINE-Y", "Y-LINE")):
        return "y"
    return ""


def _coerce_named_axis_ref_row(tokens: list[str], *, dimension: str) -> dict[str, object] | None:
    clean_tokens = [str(token).strip() for token in tokens if str(token).strip()]
    if len(clean_tokens) < 2 or dimension not in {"x", "y", "z"}:
        return None
    candidate_pairs = [(0, 1), (1, 0)]
    for label_index, value_index in candidate_pairs:
        if label_index >= len(clean_tokens) or value_index >= len(clean_tokens):
            continue
        label = clean_tokens[label_index]
        value = _as_float(clean_tokens[value_index])
        if not label or value is None:
            continue
        numeric_label = _as_float(label)
        if numeric_label is not None and dimension not in {"y", "z"}:
            continue
        if label.upper() in {"YES", "NO"}:
            continue
        return {
            "label": label,
            "value": round(float(value), 3),
            "count": 1,
        }
    return None


def _merge_named_axis_ref_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    merged: dict[tuple[str, float], dict[str, object]] = {}
    for row in rows:
        label = str(row.get("label", "") or "").strip()
        if not label:
            continue
        try:
            value = round(float(row.get("value", 0.0)), 3)
        except Exception:
            continue
        try:
            count = max(int(row.get("count", 1) or 1), 1)
        except Exception:
            count = 1
        key = (label, value)
        if key not in merged:
            merged[key] = {
                "label": label,
                "value": value,
                "count": count,
            }
            continue
        try:
            existing_count = max(int(merged[key].get("count", 1) or 1), 1)
        except Exception:
            existing_count = 1
        merged[key]["count"] = max(existing_count, count)
    return sorted(
        merged.values(),
        key=lambda item: (
            float(item.get("value", 0.0) or 0.0),
            str(item.get("label", "")),
        ),
    )


def _derive_named_axis_refs_from_sections(sections: dict[str, list[str]]) -> dict[str, list[dict[str, object]]]:
    found: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "z": []}
    for section_name, raw_rows in sections.items():
        dimension = _axis_dimension_from_section_name(section_name)
        if not dimension:
            continue
        for raw_row in raw_rows:
            axis_row = _coerce_named_axis_ref_row(_split_csv_like(raw_row), dimension=dimension)
            if axis_row is not None:
                found[dimension].append(axis_row)
    return {
        dimension: _merge_named_axis_ref_rows(rows)
        for dimension, rows in found.items()
    }


def _normalize_named_axis_refs_payload(axis_refs: object) -> dict[str, list[dict[str, object]]]:
    normalized: dict[str, list[dict[str, object]]] = {"x": [], "y": [], "z": []}
    if not isinstance(axis_refs, dict):
        return normalized
    for dimension in ("x", "y", "z"):
        rows = axis_refs.get(dimension)
        if not isinstance(rows, list):
            continue
        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label", "") or "").strip()
            if not label:
                continue
            try:
                value = round(float(row.get("value")), 3)
            except Exception:
                continue
            try:
                count = max(int(row.get("count", 1) or 1), 1)
            except Exception:
                count = 1
            normalized_rows.append(
                {
                    "label": label,
                    "value": value,
                    "count": count,
                }
            )
        normalized[dimension] = _merge_named_axis_ref_rows(normalized_rows)
    return normalized


def _extract_named_axis_refs_from_model_payload(model_payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {"x": [], "y": [], "z": []}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    if not isinstance(metadata, dict):
        return {"x": [], "y": [], "z": []}
    bridge_payload = metadata.get("kds_geometry_bridge") if isinstance(metadata.get("kds_geometry_bridge"), dict) else {}
    if isinstance(bridge_payload.get("axis_refs"), dict):
        return _normalize_named_axis_refs_payload(bridge_payload.get("axis_refs"))
    return _normalize_named_axis_refs_payload(metadata.get("named_axis_refs"))


def _parse_nodal_mass_rows(rows: list[str], node_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 7:
            continue
        nodes = [int(nid) for nid in _expand_node_expr(toks[0]) if int(nid) in node_ids]
        if not nodes:
            continue
        values = [_as_float(tok) for tok in toks[1:7]]
        if any(v is None for v in values):
            continue
        out.append(
            {
                "node_ids": nodes,
                "mx": float(values[0]),
                "my": float(values[1]),
                "mz": float(values[2]),
                "rmx": float(values[3]),
                "rmy": float(values[4]),
                "rmz": float(values[5]),
            }
        )
    return out


def _parse_nodal_load_rows(rows: list[str], node_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 7:
            continue
        nodes = [int(nid) for nid in _expand_node_expr(toks[0]) if int(nid) in node_ids]
        if not nodes:
            continue
        values = [_as_float(tok) for tok in toks[1:7]]
        if any(v is None for v in values):
            continue
        out.append(
            {
                "node_ids": nodes,
                "fx": float(values[0]),
                "fy": float(values[1]),
                "fz": float(values[2]),
                "mx": float(values[3]),
                "my": float(values[4]),
                "mz": float(values[5]),
                "group": str(toks[7]).strip() if len(toks) >= 8 else "",
                "load_case": str(toks[8]).strip() if len(toks) >= 9 else "",
            }
        )
    return out


def _parse_offset_rows(rows: list[str], element_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 3:
            continue
        elems = [int(eid) for eid in _expand_node_expr(toks[0]) if int(eid) in element_ids]
        if not elems:
            continue
        numeric_tail = [float(v) for v in (_as_float(tok) for tok in toks[2:8]) if v is not None]
        out.append(
            {
                "element_ids": elems,
                "type": str(toks[1]).strip().upper(),
                "offset_values": numeric_tail,
                "group": str(toks[8]).strip() if len(toks) >= 9 else "",
            }
        )
    return out


def _parse_pressure_rows(rows: list[str], element_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 4:
            continue
        elems = [int(eid) for eid in _expand_node_expr(toks[0]) if int(eid) in element_ids]
        if not elems:
            continue
        numeric_tail = [float(v) for v in (_as_float(tok) for tok in toks[4:]) if v is not None]
        out.append(
            {
                "element_ids": elems,
                "command": str(toks[1]).strip().upper() if len(toks) >= 2 else "",
                "element_type": str(toks[2]).strip().upper() if len(toks) >= 3 else "",
                "load_type": str(toks[3]).strip().upper() if len(toks) >= 4 else "",
                "tag_tokens": [str(tok).strip() for tok in toks[4:] if _as_float(tok) is None][:6],
                "numeric_values": numeric_tail,
                "raw_token_count": int(len(toks)),
            }
        )
    return out


def _attach_load_case(rows: list[dict], *, load_case: str, source: str) -> list[dict]:
    normalized = _normalize_load_reference(load_case)
    out: list[dict] = []
    for row in rows:
        item = dict(row)
        existing = _normalize_load_reference(str(item.get("load_case", "")))
        resolved = existing or normalized
        item["load_case"] = str(resolved)
        item["load_case_source"] = "row_token" if existing else source if resolved else "unbound"
        out.append(item)
    return out


def _parse_contextual_load_blocks(
    *,
    blocks: list[dict[str, object]],
    node_ids: set[int],
    element_ids: set[int],
) -> dict[str, object]:
    active_static_case = ""
    static_case_sequence: list[str] = []
    nodal_loads: list[dict] = []
    selfweight_rows: list[dict] = []
    pressure_rows: list[dict] = []
    for block in blocks:
        key = str(block.get("key", "")).strip().upper()
        args = [str(v).strip() for v in (block.get("args") or []) if str(v).strip()]
        rows = [str(v) for v in (block.get("rows") or [])]
        if key == "USE-STLD":
            active_static_case = _normalize_load_reference(args[0] if args else "")
            if active_static_case and active_static_case not in static_case_sequence:
                static_case_sequence.append(active_static_case)
            continue
        if key == "CONLOAD":
            parsed = _parse_nodal_load_rows(rows, node_ids)
            nodal_loads.extend(_attach_load_case(parsed, load_case=active_static_case, source="use_stld"))
            continue
        if key == "SELFWEIGHT":
            parsed = _parse_selfweight_rows(rows)
            selfweight_rows.extend(_attach_load_case(parsed, load_case=active_static_case, source="use_stld"))
            continue
        if key == "PRESSURE":
            parsed = _parse_pressure_rows(rows, element_ids)
            pressure_rows.extend(_attach_load_case(parsed, load_case=active_static_case, source="use_stld"))
            continue
    return {
        "active_static_case_sequence": static_case_sequence,
        "nodal_loads": nodal_loads,
        "selfweight": selfweight_rows,
        "pressure_loads": pressure_rows,
    }


def _build_semantic_load_summary(
    *,
    static_load_cases: list[dict],
    nodal_loads: list[dict],
    selfweight_rows: list[dict],
    pressure_loads: list[dict],
    load_combinations: list[dict],
) -> dict[str, object]:
    case_order: list[str] = []
    for row in static_load_cases:
        name = _normalize_load_reference(str(row.get("name", "")))
        if name and name not in case_order:
            case_order.append(name)
    for rows in (nodal_loads, selfweight_rows, pressure_loads):
        for row in rows:
            name = _normalize_load_reference(str(row.get("load_case", "")))
            if name and name not in case_order:
                case_order.append(name)
    case_summaries: dict[str, dict[str, object]] = {
        name: {
            "load_case": str(name),
            "nodal_load_row_count": 0,
            "nodal_target_node_count": 0,
            "nodal_force_sum": {"fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
            "selfweight_row_count": 0,
            "selfweight_vector": {"gx": 0.0, "gy": 0.0, "gz": 0.0},
            "pressure_row_count": 0,
            "pressure_target_element_count": 0,
            "pressure_scalar_sum": 0.0,
            "body_load_assembly_pending": False,
            "surface_load_assembly_pending": False,
            "semantic_status": "nodal_only_ready",
        }
        for name in case_order
    }

    for row in nodal_loads:
        load_case = _normalize_load_reference(str(row.get("load_case", "")))
        if not load_case:
            continue
        entry = case_summaries.setdefault(
            load_case,
            {
                "load_case": str(load_case),
                "nodal_load_row_count": 0,
                "nodal_target_node_count": 0,
                "nodal_force_sum": {"fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
                "selfweight_row_count": 0,
                "selfweight_vector": {"gx": 0.0, "gy": 0.0, "gz": 0.0},
                "pressure_row_count": 0,
                "pressure_target_element_count": 0,
                "pressure_scalar_sum": 0.0,
                "body_load_assembly_pending": False,
                "surface_load_assembly_pending": False,
                "semantic_status": "nodal_only_ready",
            },
        )
        node_count = len(row.get("node_ids", [])) if isinstance(row.get("node_ids"), list) else 0
        entry["nodal_load_row_count"] = int(entry["nodal_load_row_count"]) + 1
        entry["nodal_target_node_count"] = int(entry["nodal_target_node_count"]) + int(node_count)
        for key in ("fx", "fy", "fz", "mx", "my", "mz"):
            entry["nodal_force_sum"][key] = float(entry["nodal_force_sum"][key]) + float(row.get(key, 0.0) or 0.0) * float(node_count)

    for row in selfweight_rows:
        load_case = _normalize_load_reference(str(row.get("load_case", "")))
        if not load_case:
            continue
        entry = case_summaries.setdefault(load_case, dict(case_summaries.get(case_order[0], {})) if case_order else {})
        entry.setdefault("load_case", str(load_case))
        entry.setdefault("selfweight_vector", {"gx": 0.0, "gy": 0.0, "gz": 0.0})
        entry["selfweight_row_count"] = int(entry.get("selfweight_row_count", 0)) + 1
        for key in ("gx", "gy", "gz"):
            entry["selfweight_vector"][key] = float(entry["selfweight_vector"].get(key, 0.0)) + float(row.get(key, 0.0) or 0.0)
        entry["body_load_assembly_pending"] = True

    for row in pressure_loads:
        load_case = _normalize_load_reference(str(row.get("load_case", "")))
        if not load_case:
            continue
        entry = case_summaries.setdefault(load_case, dict(case_summaries.get(case_order[0], {})) if case_order else {})
        entry.setdefault("load_case", str(load_case))
        entry["pressure_row_count"] = int(entry.get("pressure_row_count", 0)) + 1
        element_count = len(row.get("element_ids", [])) if isinstance(row.get("element_ids"), list) else 0
        entry["pressure_target_element_count"] = int(entry.get("pressure_target_element_count", 0)) + int(element_count)
        entry["pressure_scalar_sum"] = float(entry.get("pressure_scalar_sum", 0.0)) + float(sum(float(v) for v in (row.get("numeric_values") or [])))
        entry["surface_load_assembly_pending"] = True

    case_rows: list[dict] = []
    for name in case_order:
        entry = case_summaries.get(name, {"load_case": str(name)})
        body_pending = bool(entry.get("body_load_assembly_pending", False))
        surface_pending = bool(entry.get("surface_load_assembly_pending", False))
        if body_pending and surface_pending:
            status = "nodal_plus_body_surface_pending"
        elif body_pending:
            status = "nodal_plus_body_pending"
        elif surface_pending:
            status = "nodal_plus_surface_pending"
        else:
            status = "nodal_only_ready"
        entry["semantic_status"] = status
        case_rows.append(entry)

    combo_rows: list[dict] = []
    for combo in load_combinations:
        factor_map = combo.get("expanded_factor_map") if isinstance(combo.get("expanded_factor_map"), dict) else {}
        nodal_sum = {"fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0}
        selfweight_sum = {"gx": 0.0, "gy": 0.0, "gz": 0.0}
        pressure_sum = 0.0
        body_pending = False
        surface_pending = False
        referenced_cases: list[str] = []
        for raw_case_name, factor in sorted(factor_map.items()):
            case_name = _normalize_load_reference(str(raw_case_name))
            if not case_name:
                continue
            referenced_cases.append(case_name)
            case_entry = case_summaries.get(case_name)
            if not case_entry:
                continue
            scalar = float(factor)
            for key in nodal_sum:
                nodal_sum[key] += scalar * float((case_entry.get("nodal_force_sum") or {}).get(key, 0.0))
            for key in selfweight_sum:
                selfweight_sum[key] += scalar * float((case_entry.get("selfweight_vector") or {}).get(key, 0.0))
            pressure_sum += scalar * float(case_entry.get("pressure_scalar_sum", 0.0) or 0.0)
            body_pending = body_pending or bool(case_entry.get("body_load_assembly_pending", False))
            surface_pending = surface_pending or bool(case_entry.get("surface_load_assembly_pending", False))
        combo_rows.append(
            {
                "name": str(combo.get("name", "")),
                "limit_state": str(combo.get("limit_state", "") or str(combo.get("combination_type", ""))),
                "referenced_cases": referenced_cases,
                "combined_nodal_force_sum": {str(k): float(v) for k, v in nodal_sum.items()},
                "combined_selfweight_vector": {str(k): float(v) for k, v in selfweight_sum.items()},
                "combined_pressure_scalar_sum": float(pressure_sum),
                "body_load_assembly_pending": bool(body_pending),
                "surface_load_assembly_pending": bool(surface_pending),
            }
        )

    bound_nodal = sum(1 for row in nodal_loads if str(row.get("load_case", "")).strip())
    bound_selfweight = sum(1 for row in selfweight_rows if str(row.get("load_case", "")).strip())
    bound_pressure = sum(1 for row in pressure_loads if str(row.get("load_case", "")).strip())
    return {
        "case_count": int(len(case_rows)),
        "combination_count": int(len(combo_rows)),
        "bound_nodal_load_row_count": int(bound_nodal),
        "bound_selfweight_row_count": int(bound_selfweight),
        "bound_pressure_row_count": int(bound_pressure),
        "unbound_nodal_load_row_count": int(len(nodal_loads) - bound_nodal),
        "unbound_selfweight_row_count": int(len(selfweight_rows) - bound_selfweight),
        "unbound_pressure_row_count": int(len(pressure_loads) - bound_pressure),
        "body_load_pending_case_count": int(sum(1 for row in case_rows if bool(row.get("body_load_assembly_pending", False)))),
        "surface_load_pending_case_count": int(sum(1 for row in case_rows if bool(row.get("surface_load_assembly_pending", False)))),
        "case_force_summaries": case_rows,
        "combination_force_summaries": combo_rows,
    }


def _parse_elements(rows: list[str], node_ids: set[int]) -> tuple[list[dict], dict[str, object]]:
    out: list[dict] = []
    skip_reason_count: Counter[str] = Counter()
    unsupported_type_count: Counter[str] = Counter()
    line_angle_token_count = 0
    line_nonzero_angle_count = 0
    line_max_abs_angle_deg = 0.0
    surface_lcaxis_token_count = 0
    surface_nonzero_lcaxis_count = 0
    surface_compact_lcaxis_token_count = 0
    unresolved_head: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 6:
            skip_reason_count["too_short"] += 1
            if len(unresolved_head) < 64:
                unresolved_head.append({"raw": row, "reason": "too_short"})
            continue
        eid = _as_int(toks[0])
        if eid is None:
            skip_reason_count["bad_id"] += 1
            if len(unresolved_head) < 64:
                unresolved_head.append({"raw": row, "reason": "bad_id"})
            continue
        etype = str(toks[1]).strip() if len(toks) >= 2 else "UNKNOWN"
        arity = _element_arity_hint(etype)
        if arity is None:
            key = f"unsupported_type:{str(etype).upper()}"
            skip_reason_count[key] += 1
            unsupported_type_count[str(etype).upper()] += 1
            if len(unresolved_head) < 64:
                unresolved_head.append(
                    {
                        "id": int(eid),
                        "type": str(etype),
                        "raw": row,
                        "reason": key,
                    }
                )
            continue

        mat = _as_int(toks[2])
        sec = _as_int(toks[3])
        node_conn: list[int] = []
        parse_reason = ""
        min_nodes_required = 3 if arity >= 3 else 2
        for i in range(arity):
            j = 4 + i
            if j >= len(toks):
                parse_reason = "missing_node_slot"
                break
            nid = _as_int(toks[j])
            if nid is None:
                parse_reason = "bad_node_slot"
                break
            if int(nid) == 0:
                if arity >= 3 and len(node_conn) >= 3:
                    break
                parse_reason = "zero_before_min_nodes"
                break
            if int(nid) not in node_ids:
                parse_reason = "unknown_node_ref"
                break
            node_conn.append(int(nid))
        if len(node_conn) < min_nodes_required:
            if not parse_reason:
                parse_reason = "insufficient_node_count"
            key = f"{parse_reason}:{str(etype).upper()}"
            skip_reason_count[key] += 1
            if len(unresolved_head) < 64:
                unresolved_head.append(
                    {
                        "id": int(eid),
                        "type": str(etype),
                        "raw": row,
                        "reason": key,
                        "token_head": toks[:12],
                    }
                )
            continue

        node_conn_unique: list[int] = []
        seen: set[int] = set()
        for nid in node_conn:
            if nid in seen:
                continue
            node_conn_unique.append(nid)
            seen.add(nid)
        if len(node_conn_unique) < 2:
            key = f"degenerate_conn:{str(etype).upper()}"
            skip_reason_count[key] += 1
            if len(unresolved_head) < 64:
                unresolved_head.append(
                    {
                        "id": int(eid),
                        "type": str(etype),
                        "raw": row,
                        "reason": key,
                    }
                )
            continue

        fam = _canonical_element_family(etype)
        element = {
            "id": int(eid),
            "type": str(etype),
            "family": fam,
            "node_ids": node_conn_unique,
            "section_id": int(sec) if sec is not None else -1,
            "material_id": int(mat) if mat is not None else -1,
        }
        etype_upper = str(etype).strip().upper()
        if fam == "beam" and etype_upper in {"BEAM", "TRUSS", "TENSTR", "COMPTR"}:
            angle = _as_float(toks[6]) if len(toks) >= 7 else None
            angle_deg = float(angle) if angle is not None else 0.0
            if len(toks) >= 7:
                line_angle_token_count += 1
            if abs(angle_deg) > 1.0e-12:
                line_nonzero_angle_count += 1
                line_max_abs_angle_deg = max(line_max_abs_angle_deg, abs(angle_deg))
            element["angle_deg"] = angle_deg
            element["angle_token_present"] = bool(len(toks) >= 7)
        elif fam == "shell":
            lcaxis = None
            lcaxis_source = "missing"
            lcaxis_token_present = False
            if len(toks) >= 11:
                lcaxis = _as_int(toks[10])
                lcaxis_source = "explicit_lcaxis_token"
                lcaxis_token_present = True
                surface_lcaxis_token_count += 1
            elif len(toks) >= 10:
                lcaxis_source = "default_lcaxis_token_omitted"
                surface_compact_lcaxis_token_count += 1
            width_id = _as_int(toks[9]) if len(toks) >= 10 else None
            lcaxis_code = int(lcaxis) if lcaxis is not None else 0
            if lcaxis_code != 0:
                surface_nonzero_lcaxis_count += 1
            element["lcaxis_code"] = lcaxis_code
            element["lcaxis_token_present"] = lcaxis_token_present
            element["lcaxis_source"] = lcaxis_source
            element["width_id"] = int(width_id) if width_id is not None else None
        out.append(element)
    return out, {
        "skipped_count": int(sum(skip_reason_count.values())),
        "skip_reason_count": {str(k): int(v) for k, v in sorted(skip_reason_count.items())},
        "unsupported_type_count": {str(k): int(v) for k, v in sorted(unsupported_type_count.items())},
        "line_angle_token_count": int(line_angle_token_count),
        "line_nonzero_angle_count": int(line_nonzero_angle_count),
        "line_max_abs_angle_deg": float(line_max_abs_angle_deg),
        "surface_lcaxis_token_count": int(surface_lcaxis_token_count),
        "surface_nonzero_lcaxis_count": int(surface_nonzero_lcaxis_count),
        "surface_compact_lcaxis_token_count": int(surface_compact_lcaxis_token_count),
        "unresolved_head": unresolved_head,
    }


def _parse_materials(rows: list[str]) -> list[dict]:
    mats: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if not toks:
            continue
        mid = _as_int(toks[0])
        if mid is None:
            continue
        mats.append(
            {
                "id": int(mid),
                "name": str(toks[1]) if len(toks) >= 2 else "",
                "raw_tokens": toks[2:] if len(toks) >= 3 else [],
            }
        )
    return mats


def _parse_sections_table(rows: list[str]) -> list[dict]:
    secs: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if not toks:
            continue
        sid = _as_int(toks[0])
        if sid is None:
            continue
        secs.append(
            {
                "id": int(sid),
                "name": str(toks[1]) if len(toks) >= 2 else "",
                "raw_tokens": toks[2:] if len(toks) >= 3 else [],
            }
        )
    return secs


def _normalize_nominal_dimension_m(value: float) -> float:
    numeric = float(value)
    if numeric <= 0.0:
        return 0.0
    if numeric > 100.0:
        return float(numeric / 1000.0)
    if numeric > 20.0:
        return float(numeric / 1000.0)
    return float(numeric)


def _extract_section_dimension_candidates(section_row: dict) -> list[float]:
    raw_tokens = section_row.get("raw_tokens") if isinstance(section_row.get("raw_tokens"), list) else []
    preferred: list[float] = []
    fallback: list[float] = []
    if isinstance(raw_tokens, list):
        tail_tokens = raw_tokens[10:] if len(raw_tokens) > 10 else raw_tokens
        for tok in tail_tokens:
            parsed = _as_float(str(tok))
            if parsed is None:
                continue
            dim = _normalize_nominal_dimension_m(parsed)
            if dim > 0.0:
                preferred.append(dim)
        for tok in raw_tokens:
            text = str(tok).strip()
            for left, right in re.findall(r"(\d+(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)", text):
                for item in (left, right):
                    parsed = _as_float(item)
                    if parsed is None:
                        continue
                    dim = _normalize_nominal_dimension_m(parsed)
                    if dim > 0.0:
                        fallback.append(dim)
    dims = [value for value in preferred if value <= 20.0]
    if len(dims) >= 2:
        return dims
    dims.extend([value for value in fallback if value > 0.0])
    unique: list[float] = []
    for value in dims:
        if all(abs(value - existing) > 1.0e-9 for existing in unique):
            unique.append(float(value))
    return unique


def _infer_section_family_and_shape(section_row: dict, usage_families: set[str]) -> tuple[str | None, str | None]:
    name = str(section_row.get("name", "") or "").strip().upper()
    raw_tokens = section_row.get("raw_tokens") if isinstance(section_row.get("raw_tokens"), list) else []
    joined = " ".join([name] + [str(tok).strip().upper() for tok in raw_tokens if str(tok).strip()])
    markers = set(re.findall(r"[A-Z][A-Z0-9\-_/+]*", joined))
    family: str | None
    if markers & _COMPOSITE_SECTION_MARKERS:
        family = "composite"
    elif markers & _RC_SECTION_MARKERS:
        family = "rc"
    elif markers & _STEEL_SECTION_MARKERS:
        family = "steel"
    elif usage_families == {"shell"}:
        family = "rc"
    elif usage_families == {"beam"}:
        family = "steel"
    elif usage_families:
        family = "composite"
    else:
        family = None

    shape: str | None = None
    if any(marker in joined for marker in ("PIPE", "TUBE", "P ")):
        shape = "pipe"
    elif "BOX" in joined:
        shape = "box"
    elif any(marker in joined for marker in ("WALL",)):
        shape = "wall_strip"
    elif any(marker in joined for marker in ("SLAB", "PLATE", "MAT")):
        shape = "slab_strip"
    elif "CFT" in joined:
        shape = "cft_box"
    elif "SRC" in joined:
        shape = "src_beam"
    elif any(marker in joined for marker in ("DECK", "COMPOSITE")):
        shape = "composite_deck_beam"
    elif any(marker in joined for marker in ("SB", "H-", " H", "BH", " I")):
        shape = "h_beam"
    elif family == "rc" and usage_families == {"shell"}:
        shape = "slab_strip"
    elif family == "steel":
        shape = "h_beam"
    elif family == "composite":
        shape = "composite_deck_beam"
    return family, shape


def _build_section_dimensions(section_row: dict, family: str | None, shape: str | None, usage_families: set[str]) -> dict[str, float]:
    dims = _extract_section_dimension_candidates(section_row)
    if shape == "pipe":
        diameter = dims[0] if dims else 0.5
        thickness = dims[1] if len(dims) >= 2 else max(0.012, diameter * 0.04)
        return {"diameter_m": float(diameter), "thickness_m": float(thickness)}
    if shape == "box":
        width = dims[0] if dims else 0.5
        depth = dims[1] if len(dims) >= 2 else width
        thickness = dims[2] if len(dims) >= 3 else max(0.016, min(width, depth) * 0.04)
        return {"width_m": float(width), "depth_m": float(depth), "thickness_m": float(thickness)}
    if shape == "wall_strip":
        length = max(dims[0], dims[1]) if len(dims) >= 2 else (dims[0] if dims else 3.0)
        thickness = min(dims[0], dims[1]) if len(dims) >= 2 else (dims[1] if len(dims) >= 2 else 0.3)
        return {"wall_length_m": float(max(length, 0.5)), "wall_thickness_m": float(max(thickness, 0.12))}
    if shape == "slab_strip":
        width = max(dims[0], dims[1]) if len(dims) >= 2 else (dims[0] if dims else 3.0)
        thickness = min(dims[0], dims[1]) if len(dims) >= 2 else 0.2
        return {"slab_width_m": float(max(width, 0.5)), "thickness_m": float(max(thickness, 0.10))}
    if shape == "cft_box":
        width = dims[0] if dims else 0.7
        depth = dims[1] if len(dims) >= 2 else width
        thickness = dims[2] if len(dims) >= 3 else max(0.02, min(width, depth) * 0.03)
        return {"width_m": float(width), "depth_m": float(depth), "thickness_m": float(thickness)}
    if shape in {"src_beam", "composite_deck_beam"}:
        depth = dims[0] if dims else 0.6
        width = dims[1] if len(dims) >= 2 else 0.25
        deck_thickness = dims[2] if len(dims) >= 3 else 0.12
        return {"depth_m": float(depth), "deck_width_m": float(max(width, 0.25)), "deck_thickness_m": float(max(deck_thickness, 0.08))}
    if shape in {"h_beam", "rect_column"} or family in {"steel", "rc", "composite"}:
        depth = dims[0] if dims else (0.6 if usage_families != {"shell"} else 0.3)
        width = dims[1] if len(dims) >= 2 else depth
        if family == "rc":
            return {"width_m": float(max(width, 0.25)), "depth_m": float(max(depth, 0.25)), "cover_m": 0.05}
        return {"depth_m": float(max(depth, 0.2)), "flange_width_m": float(max(width, 0.15))}
    return {}


def _placeholder_analysis_kind(family: str | None, usage_families: set[str]) -> str:
    if usage_families == {"shell"}:
        return "layered_shell_wall" if family == "rc" else "shell_surface_placeholder"
    if usage_families == {"beam"}:
        return "frame_fiber_ready" if family in {"steel", "rc"} else "beam_shell_composite"
    if usage_families:
        return "beam_shell_hybrid"
    return "section_placeholder"


def _default_mesh_size_for_shape(shape: str | None, dimensions: dict[str, float]) -> float:
    positives = [float(value) for value in dimensions.values() if float(value) > 0.0]
    base = min(positives) if positives else 0.25
    if shape in {"wall_strip", "slab_strip"}:
        return float(max(0.08, min(base * 0.5, 0.30)))
    return float(max(0.03, min(base * 0.25, 0.15)))


def _derive_section_productization_metadata(
    *,
    sections: list[dict],
    elements: list[dict],
    design_section_rows: list[dict],
    section_color_rows: list[dict],
    section_scale_rows: list[dict],
) -> dict[str, object]:
    usage_counter: dict[int, Counter[str]] = defaultdict(Counter)
    for element in elements:
        section_id = int(element.get("section_id", -1) or -1)
        if section_id < 0:
            continue
        usage_counter[section_id][str(element.get("family", "other") or "other")] += 1

    design_section_ids = {int(row.get("section_id", -1) or -1) for row in design_section_rows if int(row.get("section_id", -1) or -1) >= 0}
    color_section_ids = {int(row.get("section_id", -1) or -1) for row in section_color_rows if int(row.get("section_id", -1) or -1) >= 0}
    scale_section_ids = {int(row.get("section_id", -1) or -1) for row in section_scale_rows if int(row.get("section_id", -1) or -1) >= 0}

    usage_rows: list[dict[str, object]] = []
    templates: list[SectionTemplate] = []
    family_counter: Counter[str] = Counter()
    shape_counter: Counter[str] = Counter()

    for section_row in sections:
        section_id = int(section_row.get("id", -1) or -1)
        family_counts = usage_counter.get(section_id, Counter())
        usage_families = {str(key) for key, value in family_counts.items() if int(value) > 0}
        inferred_family, inferred_shape = _infer_section_family_and_shape(section_row, usage_families)
        dimensions = _build_section_dimensions(section_row, inferred_family, inferred_shape, usage_families)
        derivation_confidence = "usage_only"
        if dimensions and inferred_family and inferred_shape:
            derivation_confidence = "name_token+usage"
        elif inferred_family or inferred_shape:
            derivation_confidence = "heuristic"
        row_payload = {
            "section_id": int(section_id),
            "name": str(section_row.get("name", "") or ""),
            "usage_count": int(sum(family_counts.values())),
            "element_family_counts": {str(k): int(v) for k, v in sorted(family_counts.items())},
            "inferred_family": inferred_family or "",
            "inferred_shape": inferred_shape or "",
            "dimensions_m": {str(k): float(v) for k, v in sorted(dimensions.items())},
            "has_design_section_row": bool(section_id in design_section_ids),
            "has_section_color_row": bool(section_id in color_section_ids),
            "has_section_scale_row": bool(section_id in scale_section_ids),
            "source_provenance": "derived_from_midas_section_row_name_raw_tokens_and_element_usage",
            "limitations": "Nominal productization metadata only. Dimensions and family/shape may be heuristic placeholders until a dedicated MIDAS section decoder is added.",
            "derivation_confidence": derivation_confidence,
        }
        usage_rows.append(row_payload)
        if inferred_family and inferred_shape and dimensions:
            try:
                template = SectionTemplate(
                    section_id=f"midas:{section_id}",
                    family=str(inferred_family),
                    shape=str(inferred_shape),
                    material_grade="MIDAS_IMPORTED_PLACEHOLDER",
                    dimensions_m=dimensions,
                    default_mesh_size_m=_default_mesh_size_for_shape(inferred_shape, dimensions),
                    placeholder_analysis_kind=_placeholder_analysis_kind(inferred_family, usage_families),
                    tags=tuple(sorted(usage_families)) or ("unused",),
                    notes=(
                        f"MIDAS section {section_id} imported from parser heuristics. "
                        "Use as UI/productization seed only until exact section decoder is available."
                    ),
                )
            except Exception:
                template = None
            if template is not None:
                templates.append(template)
                family_counter[template.family] += 1
                shape_counter[template.shape] += 1

    catalog = SectionCatalog(
        version="0.1.0",
        source_label="midas_parser_derived",
        templates=tuple(templates),
    )
    return {
        "contract_version": "0.1.0",
        "provenance": "parser_additive_metadata",
        "limitations": [
            "Exact MIDAS section semantics are not fully decoded yet.",
            "Derived catalog entries are placeholders for future UI/mesher/productization work.",
            "Unusable or ambiguous rows remain in usage_summary even if no template was emitted.",
        ],
        "usage_summary": usage_rows,
        "derived_catalog": catalog.to_payload(),
        "summary": {
            "section_row_count": int(len(sections)),
            "used_section_count": int(sum(1 for row in usage_rows if int(row.get("usage_count", 0)) > 0)),
            "unused_section_count": int(sum(1 for row in usage_rows if int(row.get("usage_count", 0)) == 0)),
            "derived_template_count": int(len(templates)),
            "family_counts": {str(k): int(v) for k, v in sorted(family_counter.items())},
            "shape_counts": {str(k): int(v) for k, v in sorted(shape_counter.items())},
        },
    }


def _dominant_global_direction(vector_map: dict[str, object], *, keys: tuple[str, ...]) -> str:
    best_key = ""
    best_value = -1.0
    for key in keys:
        value = abs(float(vector_map.get(key, 0.0) or 0.0))
        if value > best_value:
            best_key = key
            best_value = value
    if best_key.endswith("x"):
        return "global_x"
    if best_key.endswith("y"):
        return "global_y"
    return "global_z"


def _load_pattern_design_situation(case_name: str, *, static_type: str = "", category: str = "") -> str:
    label = _normalize_load_reference(case_name)
    upper_static = str(static_type or "").strip().upper()
    upper_category = str(category or "").strip().upper()
    tokens = {label, upper_static, upper_category}
    if any(token in {"DEAD", "D"} for token in tokens):
        return "permanent_gravity"
    if any(token in {"LIVE", "L", "LL", "ROOF_LIVE", "R"} for token in tokens):
        return "variable_imposed"
    if any(token in {"WIND", "WIND_X", "WIND_Y", "WX", "WY"} for token in tokens):
        return "lateral_wind"
    if any(token in {"SEISMIC", "SEISMIC_X", "SEISMIC_Y", "EX", "EY", "E"} for token in tokens):
        return "seismic"
    if "TEMP" in label or "TEMP" in upper_static or "TEMP" in upper_category:
        return "thermal"
    return "service"


def _derive_load_pattern_productization_metadata(
    *,
    static_load_cases: list[dict],
    loadcase_rows: list[dict],
    load_combinations: list[dict],
    nodal_loads: list[dict],
    selfweight_rows: list[dict],
    pressure_loads: list[dict],
    semantic_load_summary: dict[str, object],
    load_color_rows: list[dict],
) -> dict[str, object]:
    static_case_by_name = {
        _normalize_load_reference(str(row.get("name", ""))): row
        for row in static_load_cases
        if _normalize_load_reference(str(row.get("name", "")))
    }
    loadcase_by_name = {
        _normalize_load_reference(str(row.get("name", ""))): row
        for row in loadcase_rows
        if _normalize_load_reference(str(row.get("name", "")))
    }
    semantic_case_rows = [
        row for row in (semantic_load_summary.get("case_force_summaries") or []) if isinstance(row, dict)
    ] if isinstance(semantic_load_summary, dict) else []
    semantic_case_by_name = {
        _normalize_load_reference(str(row.get("load_case", ""))): row
        for row in semantic_case_rows
        if _normalize_load_reference(str(row.get("load_case", "")))
    }
    case_order: list[str] = []
    for collection in (static_load_cases, semantic_case_rows, loadcase_rows):
        for row in collection:
            name = _normalize_load_reference(str(row.get("name", row.get("load_case", ""))))
            if name and name not in case_order:
                case_order.append(name)

    patterns: list[LoadPatternDraft] = []
    design_situation_counts: Counter[str] = Counter()
    semantic_status_counts: Counter[str] = Counter()
    for case_name in case_order:
        case_nodal_rows = [row for row in nodal_loads if _normalize_load_reference(str(row.get("load_case", ""))) == case_name]
        case_selfweight_rows = [row for row in selfweight_rows if _normalize_load_reference(str(row.get("load_case", ""))) == case_name]
        case_pressure_rows = [row for row in pressure_loads if _normalize_load_reference(str(row.get("load_case", ""))) == case_name]
        if not case_nodal_rows and not case_selfweight_rows and not case_pressure_rows:
            continue
        static_case = static_case_by_name.get(case_name, {})
        loadcase_row = loadcase_by_name.get(case_name, {})
        semantic_case = semantic_case_by_name.get(case_name, {})
        design_situation = _load_pattern_design_situation(
            case_name,
            static_type=str(static_case.get("type", "")),
            category=str(loadcase_row.get("category", "")),
        )
        design_situation_counts[design_situation] += 1
        semantic_status = str(semantic_case.get("semantic_status", "unclassified") or "unclassified")
        semantic_status_counts[semantic_status] += 1
        primitives: list[LoadPrimitive] = []
        if case_selfweight_rows:
            gx = sum(float(row.get("gx", 0.0) or 0.0) for row in case_selfweight_rows)
            gy = sum(float(row.get("gy", 0.0) or 0.0) for row in case_selfweight_rows)
            gz = sum(float(row.get("gz", 0.0) or 0.0) for row in case_selfweight_rows)
            primitives.append(
                LoadPrimitive(
                    kind="self_weight",
                    case_name=case_name,
                    target_scope=f"global gravity | rows={len(case_selfweight_rows)}",
                    magnitude=float((gx ** 2 + gy ** 2 + gz ** 2) ** 0.5),
                    direction=_dominant_global_direction({"gx": gx, "gy": gy, "gz": gz}, keys=("gx", "gy", "gz")),
                    notes="Derived from MIDAS SELFWEIGHT block; body-load assembly remains productization work.",
                )
            )
        if case_nodal_rows:
            force_sum = {
                key: sum(float(row.get(key, 0.0) or 0.0) * len(row.get("node_ids", []) or []) for row in case_nodal_rows)
                for key in ("fx", "fy", "fz", "mx", "my", "mz")
            }
            target_nodes = sum(len(row.get("node_ids", []) or []) for row in case_nodal_rows)
            dominant = max(abs(value) for value in force_sum.values()) if force_sum else 0.0
            primitives.append(
                LoadPrimitive(
                    kind="point_load",
                    case_name=case_name,
                    target_scope=f"nodes={int(target_nodes)} | rows={len(case_nodal_rows)}",
                    magnitude=float(dominant),
                    direction=_dominant_global_direction(force_sum, keys=("fx", "fy", "fz", "mx", "my", "mz")),
                    notes="Aggregated nodal force/moment primitive for authoring/editor preview.",
                )
            )
        if case_pressure_rows:
            first_direction = "global_z"
            for row in case_pressure_rows:
                tags = [str(token).strip().upper() for token in (row.get("tag_tokens") or []) if str(token).strip()]
                for token in tags:
                    if token in {"GX", "GY", "GZ"}:
                        first_direction = f"global_{token[-1].lower()}"
                        break
                if first_direction != "global_z":
                    break
            target_elements = sum(len(row.get("element_ids", []) or []) for row in case_pressure_rows)
            magnitude = sum(abs(float(value)) for row in case_pressure_rows for value in (row.get("numeric_values") or []))
            primitives.append(
                LoadPrimitive(
                    kind="surface_pressure",
                    case_name=case_name,
                    target_scope=f"elements={int(target_elements)} | rows={len(case_pressure_rows)}",
                    magnitude=float(magnitude),
                    direction=first_direction,
                    notes="Aggregated shell/plate pressure primitive for future surface load editor work.",
                )
            )
        try:
            pattern = LoadPatternDraft(
                pattern_id=f"midas:{case_name}",
                label=case_name,
                design_situation=design_situation,
                primitives=tuple(primitives),
                tags=tuple(
                    tag
                    for tag in (
                        design_situation,
                        semantic_status,
                        str(static_case.get("type", "") or "").strip().lower(),
                        str(loadcase_row.get("category", "") or "").strip().lower(),
                    )
                    if tag
                ),
            )
        except Exception:
            continue
        patterns.append(pattern)

    combination_rows = [row for row in load_combinations if isinstance(row, dict)]
    limit_state_counts: Counter[str] = Counter()
    expansion_mode_counts: Counter[str] = Counter()
    referenced_case_union: set[str] = set()
    referenced_leaf_case_union: set[str] = set()
    max_expansion_depth = 0
    nested_combination_count = 0
    for row in combination_rows:
        limit_state = str(row.get("limit_state", "") or row.get("combination_type", "") or "unspecified").strip() or "unspecified"
        limit_state_counts[limit_state] += 1
        expansion_mode = str(row.get("expansion_mode", "") or "linear_combination").strip() or "linear_combination"
        expansion_mode_counts[expansion_mode] += 1
        try:
            expansion_depth_value = int(row.get("expansion_depth", 0) or 0)
        except (TypeError, ValueError):
            expansion_depth_value = 0
        max_expansion_depth = max(max_expansion_depth, expansion_depth_value)
        if row.get("referenced_combinations"):
            nested_combination_count += 1
        for case_name in (row.get("referenced_cases") or []):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                referenced_case_union.add(normalized)
        for case_name in (row.get("referenced_leaf_cases") or row.get("referenced_cases") or []):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                referenced_leaf_case_union.add(normalized)

    return {
        "contract_version": "0.1.0",
        "provenance": "parser_additive_metadata",
        "limitations": [
            "Load primitives are aggregated authoring seeds, not exact solver load cards.",
            "Body/surface load assembly is still represented as productization metadata, not a native commercial editor.",
            "Combination expansion is summary-grade and should not replace final code-check load assembly.",
        ],
        "pattern_summary": build_load_pattern_summary(patterns),
        "case_semantic_rows": semantic_case_rows,
        "combination_summary": {
            "combination_count": int(len(combination_rows)),
            "limit_state_counts": {str(key): int(value) for key, value in sorted(limit_state_counts.items())},
            "expansion_mode_counts": {str(key): int(value) for key, value in sorted(expansion_mode_counts.items())},
            "max_expansion_depth": int(max_expansion_depth),
            "nested_combination_count": int(nested_combination_count),
            "referenced_case_union": sorted(referenced_case_union),
            "referenced_leaf_case_union": sorted(referenced_leaf_case_union),
            "combination_names": [str(row.get("name", "") or "") for row in combination_rows if str(row.get("name", "") or "")],
        },
        "summary": {
            "pattern_count": int(len(patterns)),
            "primitive_count": int(sum(len(pattern.primitives) for pattern in patterns)),
            "design_situation_counts": {str(key): int(value) for key, value in sorted(design_situation_counts.items())},
            "semantic_status_counts": {str(key): int(value) for key, value in sorted(semantic_status_counts.items())},
            "load_color_row_count": int(len(load_color_rows)),
        },
    }


def _derive_load_combination_editor_seed(
    *,
    load_combinations: list[dict],
    load_combination_graph: dict[str, object],
    load_pattern_library: dict[str, object],
    semantic_load_summary: dict[str, object],
) -> dict[str, object]:
    combination_rows = [row for row in load_combinations if isinstance(row, dict)]
    graph = load_combination_graph if isinstance(load_combination_graph, dict) else {}
    if not combination_rows and not graph:
        return {}

    pattern_summary = load_pattern_library.get("pattern_summary") if isinstance(load_pattern_library.get("pattern_summary"), dict) else {}
    pattern_rows = [row for row in (pattern_summary.get("patterns") or []) if isinstance(row, dict)]
    pattern_rows_by_case = {
        _normalize_load_reference(str(row.get("label", ""))): row
        for row in pattern_rows
        if _normalize_load_reference(str(row.get("label", "")))
    }
    semantic_case_rows = [
        row for row in (semantic_load_summary.get("case_force_summaries") or [])
        if isinstance(row, dict)
    ] if isinstance(semantic_load_summary, dict) else []
    semantic_case_by_name = {
        _normalize_load_reference(str(row.get("load_case", ""))): row
        for row in semantic_case_rows
        if _normalize_load_reference(str(row.get("load_case", "")))
    }
    combo_rows_by_name = {
        str(row.get("name", "") or "").strip(): row
        for row in combination_rows
        if str(row.get("name", "") or "").strip()
    }
    combo_summaries_by_name = {
        str(row.get("name", "") or "").strip(): row
        for row in (graph.get("combo_summaries") or [])
        if isinstance(row, dict) and str(row.get("name", "") or "").strip()
    }

    case_names: set[str] = set()
    combo_names: set[str] = set(combo_rows_by_name)
    for row in combination_rows:
        for case_name in (row.get("referenced_leaf_cases") or row.get("referenced_cases") or []):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                case_names.add(normalized)
        combo_names.update(
            str(item).strip()
            for item in (row.get("referenced_combinations") or [])
            if str(item).strip()
        )
    for node in (graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        node_kind = str(node.get("kind", "") or "").strip().lower()
        node_name = str(node.get("name", "") or "").strip()
        node_id = str(node.get("id", "") or "").strip()
        if node_kind == "case":
            normalized = _normalize_load_reference(node_name or node_id.replace("CASE:", ""))
            if normalized:
                case_names.add(normalized)
        elif node_kind == "combo":
            combo_name = node_name or node_id.replace("COMBO:", "")
            if combo_name:
                combo_names.add(combo_name)

    case_nodes = []
    for case_name in sorted(case_names):
        pattern_row = pattern_rows_by_case.get(case_name, {})
        semantic_row = semantic_case_by_name.get(case_name, {})
        primitive_counts = {
            str(key): int(value)
            for key, value in (pattern_row.get("primitive_counts") or {}).items()
            if str(key)
        } if isinstance(pattern_row.get("primitive_counts"), dict) else {}
        primitive_labels = sorted(primitive_counts)
        case_nodes.append(
            {
                "id": f"CASE:{case_name}",
                "name": case_name,
                "kind": "case",
                "editor_stage": 0,
                "design_situation": str(pattern_row.get("design_situation", "") or "service"),
                "semantic_status": str(semantic_row.get("semantic_status", "") or "unclassified"),
                "primitive_count": int(pattern_row.get("primitive_count", 0) or 0),
                "primitive_kind_counts": primitive_counts,
                "primitive_kind_labels": primitive_labels,
                "primitive_scope_preview": " | ".join(
                    str(item.get("target_scope", "") or "scope n/a")
                    for item in (pattern_row.get("primitives") or [])[:2]
                    if isinstance(item, dict)
                ) or "scope n/a",
            }
        )

    limit_state_counts: Counter[str] = Counter()
    expansion_mode_counts: Counter[str] = Counter()
    combination_nodes = []
    for combo_name in sorted(
        combo_names,
        key=lambda value: (
            -int(
                combo_rows_by_name.get(value, {}).get("expansion_depth")
                or combo_summaries_by_name.get(value, {}).get("expansion_depth")
                or 0
            ),
            value,
        ),
    ):
        combo_row = combo_rows_by_name.get(combo_name, {})
        combo_summary = combo_summaries_by_name.get(combo_name, {})
        expansion_depth = int(combo_row.get("expansion_depth", combo_summary.get("expansion_depth", 0)) or 0)
        expansion_mode = str(combo_row.get("expansion_mode", "") or combo_summary.get("expansion_mode", "") or "linear_combination").strip() or "linear_combination"
        limit_state = str(combo_row.get("limit_state", "") or combo_row.get("combination_type", "") or "unspecified").strip() or "unspecified"
        referenced_leaf_cases = [
            _normalize_load_reference(str(item))
            for item in (
                combo_summary.get("referenced_leaf_cases")
                or combo_row.get("referenced_leaf_cases")
                or combo_row.get("referenced_cases")
                or []
            )
            if _normalize_load_reference(str(item))
        ]
        referenced_combinations = [
            str(item).strip()
            for item in (combo_row.get("referenced_combinations") or [])
            if str(item).strip()
        ]
        factor_map = combo_summary.get("expanded_factor_map") if isinstance(combo_summary.get("expanded_factor_map"), dict) else (
            combo_row.get("expanded_factor_map") if isinstance(combo_row.get("expanded_factor_map"), dict) else {}
        )
        entry_rows = []
        for entry in (combo_row.get("entries") or []):
            if not isinstance(entry, dict):
                continue
            reference_kind = str(entry.get("reference_kind", "") or "").strip().upper()
            reference_name = str(entry.get("reference_name", "") or "").strip()
            if reference_kind not in {"ST", "CB"} or not reference_name:
                continue
            entry_rows.append(
                {
                    "reference_kind": reference_kind,
                    "reference_name": reference_name,
                    "factor": float(entry.get("factor", 0.0) or 0.0),
                }
            )
        if not entry_rows:
            entry_rows.extend(
                {
                    "reference_kind": "CB",
                    "reference_name": reference_name,
                    "factor": 1.0,
                }
                for reference_name in referenced_combinations
            )
            if not referenced_combinations:
                entry_rows.extend(
                    {
                        "reference_kind": "ST",
                        "reference_name": str(case_name),
                        "factor": float(value),
                    }
                    for case_name, value in sorted(factor_map.items())
                    if str(case_name)
                )
        limit_state_counts[limit_state] += 1
        expansion_mode_counts[expansion_mode] += 1
        combination_nodes.append(
            {
                "id": f"COMBO:{combo_name}",
                "name": combo_name,
                "kind": "combo",
                "editor_stage": max(expansion_depth, 1),
                "limit_state": limit_state,
                "combination_type": str(combo_row.get("combination_type", "") or "GEN"),
                "expression": str(combo_row.get("expression", "") or "expression n/a"),
                "entry_count": int(combo_row.get("entry_count", len(combo_row.get("entries") or [])) or 0),
                "expansion_mode": expansion_mode,
                "expansion_depth": expansion_depth,
                "referenced_combinations": referenced_combinations,
                "referenced_leaf_cases": referenced_leaf_cases,
                "factor_map": {str(key): float(value) for key, value in sorted(factor_map.items()) if str(key)},
                "entry_rows": entry_rows,
                "node_role": "nested_combo" if referenced_combinations else "direct_combo",
            }
        )

    edge_rows = []
    for edge in (graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("src", "") or "").strip()
        dst = str(edge.get("dst", "") or "").strip()
        if not src or not dst:
            continue
        src_kind = "combo" if src.startswith("COMBO:") else "case" if src.startswith("CASE:") else "unknown"
        dst_kind = "combo" if dst.startswith("COMBO:") else "case" if dst.startswith("CASE:") else "unknown"
        edge_rows.append(
            {
                "src": src,
                "dst": dst,
                "src_kind": src_kind,
                "dst_kind": dst_kind,
                "src_name": src.split(":", 1)[-1],
                "dst_name": dst.split(":", 1)[-1],
                "kind": str(edge.get("kind", "") or "edge"),
                "factor": float(edge.get("factor", 0.0) or 0.0),
            }
        )
    if not edge_rows:
        for combo_name, combo_row in combo_rows_by_name.items():
            factor_map = combo_row.get("factor_map") if isinstance(combo_row.get("factor_map"), dict) else {}
            for ref_name in (
                str(item).strip()
                for item in (combo_row.get("referenced_combinations") or [])
                if str(item).strip()
            ):
                edge_rows.append(
                    {
                        "src": f"COMBO:{combo_name}",
                        "dst": f"COMBO:{ref_name}",
                        "src_kind": "combo",
                        "dst_kind": "combo",
                        "src_name": combo_name,
                        "dst_name": ref_name,
                        "kind": "combo_ref",
                        "factor": 1.0,
                    }
                )
            for case_name in (
                _normalize_load_reference(str(item))
                for item in (combo_row.get("referenced_cases") or [])
                if _normalize_load_reference(str(item))
            ):
                edge_rows.append(
                    {
                        "src": f"COMBO:{combo_name}",
                        "dst": f"CASE:{case_name}",
                        "src_kind": "combo",
                        "dst_kind": "case",
                        "src_name": combo_name,
                        "dst_name": case_name,
                        "kind": "case_factor",
                        "factor": float(factor_map.get(case_name, 1.0) or 1.0),
                    }
                )

    stage_count = len(
        {
            int(row.get("editor_stage", 0) or 0)
            for row in [*case_nodes, *combination_nodes]
            if isinstance(row, dict)
        }
    )
    max_expansion_depth = max(
        [int(row.get("expansion_depth", 0) or 0) for row in combination_nodes] or [0]
    )
    return {
        "contract_version": "0.1.0",
        "provenance": "parser_additive_metadata",
        "seed_kind": "midas_load_combination_editor_seed",
        "limitations": [
            "Editor seed rows are deterministic authoring contracts, not final solver-ready code-check assemblies.",
            "Graph layout/order is suitable for browser/editor preview and may differ from final commercial UI presentation.",
            "Expanded factor maps should be treated as normalized references until round-trip export is fully wired.",
        ],
        "summary": {
            "combination_count": int(len(combination_nodes)),
            "case_count": int(len(case_nodes)),
            "graph_edge_count": int(len(edge_rows)),
            "stage_count": int(stage_count),
            "max_expansion_depth": int(max_expansion_depth),
            "nested_combination_count": int(sum(1 for row in combination_nodes if row.get("referenced_combinations"))),
            "limit_state_counts": {str(key): int(value) for key, value in sorted(limit_state_counts.items())},
            "expansion_mode_counts": {str(key): int(value) for key, value in sorted(expansion_mode_counts.items())},
        },
        "case_nodes": case_nodes,
        "combination_nodes": combination_nodes,
        "graph_edges": edge_rows,
    }


def derive_section_productization_for_model_payload(model_payload: dict) -> dict[str, object]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    sections = [row for row in (model.get("sections") or []) if isinstance(row, dict)]
    elements = [row for row in (model.get("elements") or []) if isinstance(row, dict)]
    if not sections or not elements:
        return {}
    return _derive_section_productization_metadata(
        sections=sections,
        elements=elements,
        design_section_rows=[row for row in (metadata.get("design_sections") or []) if isinstance(row, dict)],
        section_color_rows=[row for row in (metadata.get("section_colors") or []) if isinstance(row, dict)],
        section_scale_rows=[row for row in (metadata.get("section_scales") or []) if isinstance(row, dict)],
    )


def derive_load_pattern_productization_for_model_payload(model_payload: dict) -> dict[str, object]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    if not loads:
        recovered = derive_load_productization_from_raw_combination_payload(model_payload)
        return recovered.get("load_pattern_library") if isinstance(recovered.get("load_pattern_library"), dict) else {}
    return _derive_load_pattern_productization_metadata(
        static_load_cases=[row for row in (loads.get("static_load_cases") or []) if isinstance(row, dict)],
        loadcase_rows=[row for row in (loads.get("load_cases") or []) if isinstance(row, dict)],
        load_combinations=[row for row in (loads.get("load_combinations") or []) if isinstance(row, dict)],
        nodal_loads=[row for row in (loads.get("nodal_loads") or []) if isinstance(row, dict)],
        selfweight_rows=[row for row in (loads.get("selfweight") or []) if isinstance(row, dict)],
        pressure_loads=[row for row in (loads.get("pressure_loads") or []) if isinstance(row, dict)],
        semantic_load_summary=loads.get("semantic_load_summary") if isinstance(loads.get("semantic_load_summary"), dict) else {},
        load_color_rows=[row for row in (metadata.get("load_colors") or []) if isinstance(row, dict)],
    )


def derive_load_combination_editor_seed_for_model_payload(model_payload: dict) -> dict[str, object]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    if not loads:
        recovered = derive_load_productization_from_raw_combination_payload(model_payload)
        return recovered.get("load_combination_editor_seed") if isinstance(recovered.get("load_combination_editor_seed"), dict) else {}
    load_pattern_library = metadata.get("load_pattern_library") if isinstance(metadata.get("load_pattern_library"), dict) else {}
    if not load_pattern_library:
        load_pattern_library = derive_load_pattern_productization_for_model_payload(model_payload)
    return _derive_load_combination_editor_seed(
        load_combinations=[row for row in (loads.get("load_combinations") or []) if isinstance(row, dict)],
        load_combination_graph=loads.get("load_combination_graph") if isinstance(loads.get("load_combination_graph"), dict) else {},
        load_pattern_library=load_pattern_library if isinstance(load_pattern_library, dict) else {},
        semantic_load_summary=loads.get("semantic_load_summary") if isinstance(loads.get("semantic_load_summary"), dict) else {},
    )


def _representative_baseline_member_id(member_row: dict[str, object]) -> str:
    seed = str(member_row.get("element_seed", "") or "").strip()
    if seed:
        return seed
    element_ids = [
        str(item).strip()
        for item in (member_row.get("element_ids") or [])
        if str(item).strip()
    ]
    return element_ids[0] if element_ids else ""


def _normalized_bridge_section_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(text))
    except (TypeError, ValueError):
        return text


def _normalized_bridge_name_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _normalized_bridge_section_id_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        text = _normalized_bridge_section_id(value)
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _merge_normalized_bridge_names(*value_sets: object) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for values in value_sets:
        for text in _normalized_bridge_name_list(values):
            if text in seen:
                continue
            seen.add(text)
            ordered.append(text)
    return ordered


def _merge_normalized_bridge_section_ids(*value_sets: object) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for values in value_sets:
        for text in _normalized_bridge_section_id_list(values):
            if text in seen:
                continue
            seen.add(text)
            ordered.append(text)
    return ordered


def _geometry_bridge_group_names(geometry_kind: str) -> list[str]:
    normalized = str(geometry_kind or "").strip().lower()
    if normalized in {"x_beam", "y_beam"}:
        return ["horizontal_beam"]
    if normalized == "vertical":
        return ["vertical"]
    if normalized == "plan_diagonal":
        return ["plan_diagonal"]
    if normalized:
        return ["other"]
    return []


def _build_geometry_bridge_full_inventory_indexes(
    member_catalog: list[dict[str, object]],
    element_index: dict[str, dict[str, object]],
    node_index: dict[str, tuple[float, float, float]],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    member_handles_by_group: dict[str, list[str]] = defaultdict(list)
    section_ids_by_group: dict[str, list[str]] = defaultdict(list)
    section_ids_by_handle: dict[str, list[str]] = defaultdict(list)
    for row in member_catalog:
        handle = str(row.get("aggregate_member_id", "") or "").strip()
        section_id = _normalized_bridge_section_id(row.get("section_id"))
        for group_name in _geometry_bridge_group_names(str(row.get("geometry_kind", "") or "")):
            if handle and handle not in member_handles_by_group[group_name]:
                member_handles_by_group[group_name].append(handle)
            if section_id and section_id not in section_ids_by_group[group_name]:
                section_ids_by_group[group_name].append(section_id)
        if handle and section_id and section_id not in section_ids_by_handle[handle]:
            section_ids_by_handle[handle].append(section_id)
    for row in element_index.values():
        if not isinstance(row, dict):
            continue
        section_id = _normalized_bridge_section_id(row.get("section_id"))
        if not section_id:
            continue
        geometry_kind = _bridge_element_geometry_kind(row, node_index)
        for group_name in _geometry_bridge_group_names(geometry_kind):
            if section_id not in section_ids_by_group[group_name]:
                section_ids_by_group[group_name].append(section_id)
    return member_handles_by_group, section_ids_by_group, section_ids_by_handle


def _candidate_exact_bridge_registry_paths() -> list[Path]:
    phase1_root = Path(__file__).resolve().parent
    return [phase1_root / "open_data" / "midas" / "kds_geometry_bridge_registry.exact.json"]


def _load_exact_kds_geometry_bridge_mappings() -> list[dict[str, object]]:
    cached = getattr(_load_exact_kds_geometry_bridge_mappings, "_cache", None)
    if isinstance(cached, list):
        return cached
    mappings: list[dict[str, object]] = []
    for path in _candidate_exact_bridge_registry_paths():
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        candidate_rows = [row for row in (payload.get("mappings") or []) if isinstance(row, dict)]
        if candidate_rows:
            mappings = candidate_rows
            break
    _load_exact_kds_geometry_bridge_mappings._cache = mappings
    return mappings


def _build_exact_kds_geometry_bridge_mapping_index() -> dict[tuple[str, ...], dict[str, object]]:
    index: dict[tuple[str, ...], dict[str, object]] = {}
    for row in _load_exact_kds_geometry_bridge_mappings():
        review_member_id = str(row.get("review_member_id", "") or "").strip()
        review_case_id = str(row.get("review_case_id", "") or "").strip()
        if review_member_id or review_case_id:
            index.setdefault(("pair", review_member_id, review_case_id), row)
        review_keys = tuple(_merge_normalized_bridge_names(row.get("review_keys")))
        if review_keys:
            index.setdefault(("keys",) + review_keys, row)
        focus_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
        source_member_type = str(row.get("source_member_type", "") or "").strip()
        source_topology_type = str(row.get("source_topology_type", "") or "").strip()
        source_hazard_type = str(row.get("source_hazard_type", "") or "").strip()
        source_element_mix = str(row.get("source_element_mix", "") or "").strip()
        if focus_member_id:
            index.setdefault(
                (
                    "focus",
                    focus_member_id,
                    source_member_type,
                    source_topology_type,
                    source_hazard_type,
                    source_element_mix,
                ),
                row,
            )
    return index


def _lookup_exact_kds_geometry_bridge_mapping(
    row: dict[str, object],
    mapping_index: dict[tuple[str, ...], dict[str, object]],
) -> dict[str, object]:
    def _is_compatible(candidate: dict[str, object]) -> bool:
        fields = (
            "baseline_focus_member_id",
            "source_member_type",
            "source_topology_type",
            "source_hazard_type",
            "source_element_mix",
        )
        for field in fields:
            row_value = str(row.get(field, "") or "").strip()
            candidate_value = str(candidate.get(field, "") or "").strip()
            if row_value and candidate_value and row_value != candidate_value:
                return False
        return True

    review_member_id = str(row.get("review_member_id", "") or "").strip()
    review_case_id = str(row.get("review_case_id", "") or "").strip()
    if review_member_id or review_case_id:
        matched = mapping_index.get(("pair", review_member_id, review_case_id))
        if isinstance(matched, dict) and _is_compatible(matched):
            return matched
    review_keys = tuple(_merge_normalized_bridge_names(row.get("review_keys")))
    if review_keys:
        matched = mapping_index.get(("keys",) + review_keys)
        if isinstance(matched, dict) and _is_compatible(matched):
            return matched
    focus_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
    if focus_member_id:
        matched = mapping_index.get(
            (
                "focus",
                focus_member_id,
                str(row.get("source_member_type", "") or "").strip(),
                str(row.get("source_topology_type", "") or "").strip(),
                str(row.get("source_hazard_type", "") or "").strip(),
                str(row.get("source_element_mix", "") or "").strip(),
            )
        )
        if isinstance(matched, dict) and _is_compatible(matched):
            return matched
    return {}


def _bridge_element_geometry_kind(element_row: dict[str, object], node_index: dict[str, tuple[float, float, float]]) -> str:
    node_ids = [str(item).strip() for item in (element_row.get("node_ids") or []) if str(item).strip()]
    if len(node_ids) != 2:
        return "other"
    p0 = node_index.get(node_ids[0])
    p1 = node_index.get(node_ids[1])
    if p0 is None or p1 is None:
        return "other"
    dx = float(p1[0]) - float(p0[0])
    dy = float(p1[1]) - float(p0[1])
    dz = float(p1[2]) - float(p0[2])
    adx, ady, adz = abs(dx), abs(dy), abs(dz)
    horiz = math.hypot(dx, dy)
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length <= 1.0e-9:
        return "point"
    if adz / length > 0.85 and horiz / length < 0.3:
        return "vertical"
    if adz / length < 0.15 and horiz / length > 0.85:
        if horiz <= 1.0e-9:
            return "point"
        if adx / horiz > 0.85:
            return "x_beam"
        if ady / horiz > 0.85:
            return "y_beam"
        return "plan_diagonal"
    return "space_diagonal"


def _build_geometry_bridge_node_index(model_payload: dict[str, object]) -> dict[str, tuple[float, float, float]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    out: dict[str, tuple[float, float, float]] = {}
    for row in (model.get("nodes") or []):
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("id", "") or "").strip()
        if not node_id:
            continue
        out[node_id] = (
            float(row.get("x", 0.0) or 0.0),
            float(row.get("y", 0.0) or 0.0),
            float(row.get("z", 0.0) or 0.0),
        )
    return out


def _geometry_bridge_selector_kind(
    source_member_type: str,
    source_topology_type: str,
    source_element_mix: str,
) -> str:
    member = str(source_member_type or "").strip().lower()
    topology = str(source_topology_type or "").strip().lower()
    mix = str(source_element_mix or "").strip().lower()
    if member == "brace" or topology == "truss":
        return "plan_diagonal_surrogate"
    if member == "wall" or topology == "wall-frame":
        return "vertical_perimeter_surrogate"
    if member == "column" or topology == "outrigger" or mix == "shell_beam_mix":
        return "vertical_core_surrogate"
    return "x_beam_surrogate"


def _build_geometry_bridge_member_catalog(
    model_payload: dict[str, object],
) -> tuple[dict[str, dict[str, str]], list[dict[str, object]], dict[str, dict[str, object]], set[str], set[str], set[str], str]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}, [], {}, set(), set(), set(), "aggregate_member_id"
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    element_rows = [row for row in (model.get("elements") or []) if isinstance(row, dict)]
    element_index = {
        str(row.get("id", "") or "").strip(): row
        for row in element_rows
        if str(row.get("id", "") or "").strip()
    }
    expected_section_ids = {
        _normalized_bridge_section_id(row.get("section_id"))
        for row in element_rows
        if _normalized_bridge_section_id(row.get("section_id"))
    }
    node_index = _build_geometry_bridge_node_index(model_payload)
    member_rows = [row for row in (metadata.get("members") or []) if isinstance(row, dict)]
    member_lookup: dict[str, dict[str, str]] = {}
    member_catalog: list[dict[str, object]] = []
    expected_member_handles: set[str] = set()
    expected_load_names: set[str] = set()
    loads = model.get("loads") if isinstance(model.get("loads"), dict) else {}
    for row in (loads.get("load_combinations") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if name:
            expected_load_names.add(name)
    metadata_load_seed = metadata.get("load_combination_editor_seed") if isinstance(metadata.get("load_combination_editor_seed"), dict) else {}
    for row in (metadata_load_seed.get("combination_nodes") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "") or "").strip()
        if name:
            expected_load_names.add(name)
    for row in member_rows:
        aggregate_id = str(row.get("id", "") or "").strip()
        if not aggregate_id:
            continue
        expected_member_handles.add(aggregate_id)
        raw_element_ids = _normalized_bridge_name_list(
            [row.get("element_seed")] + list(row.get("element_ids") or [])
        )
        representative_element_id = ""
        representative_element: dict[str, object] | None = None
        for element_id in raw_element_ids:
            element = element_index.get(element_id)
            if isinstance(element, dict):
                representative_element_id = element_id
                representative_element = element
                break
        if representative_element is None:
            continue
        geometry_kind = _bridge_element_geometry_kind(representative_element, node_index)
        node_ids = [str(item).strip() for item in (representative_element.get("node_ids") or []) if str(item).strip()]
        midpoint = (0.0, 0.0, 0.0)
        length = 0.0
        if len(node_ids) >= 2 and node_ids[0] in node_index and node_ids[1] in node_index:
            p0 = node_index[node_ids[0]]
            p1 = node_index[node_ids[1]]
            midpoint = (
                (float(p0[0]) + float(p1[0])) / 2.0,
                (float(p0[1]) + float(p1[1])) / 2.0,
                (float(p0[2]) + float(p1[2])) / 2.0,
            )
            length = math.dist(p0, p1)
        member_catalog.append(
            {
                "aggregate_member_id": aggregate_id,
                "element_id": representative_element_id,
                "geometry_kind": geometry_kind,
                "section_id": _normalized_bridge_section_id(representative_element.get("section_id")),
                "midpoint": midpoint,
                "length": float(length),
            }
        )
        for element_id in raw_element_ids:
            member_lookup.setdefault(
                element_id,
                {
                    "aggregate_member_id": aggregate_id,
                    "representative_element_id": representative_element_id,
                },
            )
    handle_kind = "aggregate_member_id"
    if not expected_member_handles:
        handle_kind = "element_id"
        for element_id, representative_element in element_index.items():
            geometry_kind = _bridge_element_geometry_kind(representative_element, node_index)
            if geometry_kind in {"other", "point"}:
                continue
            node_ids = [str(item).strip() for item in (representative_element.get("node_ids") or []) if str(item).strip()]
            midpoint = (0.0, 0.0, 0.0)
            length = 0.0
            if len(node_ids) >= 2 and node_ids[0] in node_index and node_ids[1] in node_index:
                p0 = node_index[node_ids[0]]
                p1 = node_index[node_ids[1]]
                midpoint = (
                    (float(p0[0]) + float(p1[0])) / 2.0,
                    (float(p0[1]) + float(p1[1])) / 2.0,
                    (float(p0[2]) + float(p1[2])) / 2.0,
                )
                length = math.dist(p0, p1)
            expected_member_handles.add(element_id)
            member_catalog.append(
                {
                    "aggregate_member_id": element_id,
                    "element_id": element_id,
                    "geometry_kind": geometry_kind,
                    "section_id": _normalized_bridge_section_id(representative_element.get("section_id")),
                    "midpoint": midpoint,
                    "length": float(length),
                }
            )
            member_lookup.setdefault(
                element_id,
                {
                    "aggregate_member_id": element_id,
                    "representative_element_id": element_id,
                },
            )
    return member_lookup, member_catalog, element_index, expected_member_handles, expected_section_ids, expected_load_names, handle_kind


def _candidate_geometry_kinds_for_selector(selector_kind: str) -> list[str]:
    if selector_kind == "plan_diagonal_surrogate":
        return ["plan_diagonal", "space_diagonal", "x_beam", "y_beam"]
    if selector_kind in {"vertical_core_surrogate", "vertical_perimeter_surrogate"}:
        return ["vertical", "x_beam", "y_beam", "plan_diagonal"]
    return ["x_beam", "y_beam", "plan_diagonal", "space_diagonal", "vertical"]


def _full_crosswalk_groups_and_geometry_kinds(
    selector_kind: str,
    source_member_type: str,
    source_topology_type: str,
    source_element_mix: str,
    focus_geometry_kind: str,
) -> tuple[list[str], list[str]]:
    member_type = str(source_member_type or "").strip().lower()
    topology_type = str(source_topology_type or "").strip().lower()
    element_mix = str(source_element_mix or "").strip().lower()
    geometry_kind = str(focus_geometry_kind or "").strip().lower()
    if selector_kind == "plan_diagonal_surrogate" or member_type == "brace" or topology_type == "truss":
        return ["plan_diagonal"], ["plan_diagonal", "space_diagonal"]
    if (
        selector_kind in {"vertical_core_surrogate", "vertical_perimeter_surrogate"}
        or member_type in {"column", "wall"}
        or topology_type in {"wall-frame", "outrigger"}
        or element_mix == "shell_beam_mix"
        or geometry_kind == "vertical"
    ):
        return ["vertical_member"], ["vertical"]
    if geometry_kind in {"x_beam", "y_beam", "plan_diagonal", "space_diagonal"} or member_type in {"beam", "girder"}:
        return ["horizontal_beam"], ["x_beam", "y_beam"]
    return ["all_members"], ["x_beam", "y_beam", "plan_diagonal", "space_diagonal", "vertical"]


def _focus_geometry_signature(
    baseline_focus_member_id: str,
    element_index: dict[str, dict[str, object]],
    node_index: dict[str, tuple[float, float, float]],
    snapshot: dict[str, object],
) -> dict[str, object]:
    element = element_index.get(baseline_focus_member_id, {})
    normalized_section_id = _normalized_bridge_section_id(
        (snapshot.get("section_id") if isinstance(snapshot, dict) else "")
        or element.get("section_id")
    )
    geometry_kind = _bridge_element_geometry_kind(element, node_index) if isinstance(element, dict) else "other"
    midpoint = (0.0, 0.0, 0.0)
    node_ids = [str(item).strip() for item in (element.get("node_ids") or []) if str(item).strip()]
    if len(node_ids) >= 2 and node_ids[0] in node_index and node_ids[1] in node_index:
        midpoint = (
            (node_index[node_ids[0]][0] + node_index[node_ids[1]][0]) / 2.0,
            (node_index[node_ids[0]][1] + node_index[node_ids[1]][1]) / 2.0,
            (node_index[node_ids[0]][2] + node_index[node_ids[1]][2]) / 2.0,
        )
    return {
        "section_id": normalized_section_id,
        "geometry_kind": geometry_kind,
        "midpoint": midpoint,
    }


def enrich_kds_geometry_bridge_full_crosswalk_metadata(
    model_payload: dict[str, object],
    bridge_payload: dict[str, object] | None,
) -> dict[str, object]:
    bridge = bridge_payload if isinstance(bridge_payload, dict) else {}
    bridge_rows = [row for row in (bridge.get("bridge_rows") or []) if isinstance(row, dict)]
    if not bridge_rows:
        return bridge
    member_lookup, member_catalog, element_index, expected_member_handles, expected_section_ids, expected_load_names, member_handle_kind = _build_geometry_bridge_member_catalog(
        model_payload
    )
    node_index = _build_geometry_bridge_node_index(model_payload)
    member_handles_by_group, section_ids_by_group, section_ids_by_handle = _build_geometry_bridge_full_inventory_indexes(
        member_catalog,
        element_index,
        node_index,
    )
    exact_mapping_index = _build_exact_kds_geometry_bridge_mapping_index()
    used_member_handles: set[str] = set()
    used_section_ids: set[str] = set()
    enriched_rows: list[dict[str, object]] = []
    for row in bridge_rows:
        normalized_row = dict(row)
        exact_row = _lookup_exact_kds_geometry_bridge_mapping(normalized_row, exact_mapping_index)
        baseline_focus_member_id = str(normalized_row.get("baseline_focus_member_id", "") or "").strip()
        snapshot = normalized_row.get("review_geometry_snapshot") if isinstance(normalized_row.get("review_geometry_snapshot"), dict) else {}
        direct_lookup = member_lookup.get(baseline_focus_member_id, {})
        existing_member_handle = str(
            normalized_row.get("full_crosswalk_target_member_handle", "")
            or normalized_row.get("surrogate_aggregate_member_id", "")
            or (
                direct_lookup.get("aggregate_member_id", "")
                if member_handle_kind != "element_id" and isinstance(direct_lookup, dict)
                else ""
            )
            or ""
        ).strip()
        if member_handle_kind == "element_id" and existing_member_handle == baseline_focus_member_id:
            existing_member_handle = ""
        selector_kind = _geometry_bridge_selector_kind(
            str(normalized_row.get("source_member_type", "") or ""),
            str(normalized_row.get("source_topology_type", "") or ""),
            str(normalized_row.get("source_element_mix", "") or ""),
        )
        focus_signature = _focus_geometry_signature(
            baseline_focus_member_id,
            element_index,
            node_index,
            snapshot,
        )
        candidate_geometry_kinds = _candidate_geometry_kinds_for_selector(selector_kind)
        candidate_pool = [row for row in member_catalog if str(row.get("geometry_kind", "") or "") in candidate_geometry_kinds]
        if not candidate_pool:
            candidate_pool = list(member_catalog)
        focus_section_id = str(focus_signature.get("section_id", "") or "")
        focus_geometry_kind = str(focus_signature.get("geometry_kind", "") or "")
        focus_midpoint = focus_signature.get("midpoint")
        if not isinstance(focus_midpoint, tuple) or len(focus_midpoint) != 3:
            focus_midpoint = (0.0, 0.0, 0.0)
        inventory_groups, inventory_geometry_kinds = _full_crosswalk_groups_and_geometry_kinds(
            selector_kind,
            str(normalized_row.get("source_member_type", "") or ""),
            str(normalized_row.get("source_topology_type", "") or ""),
            str(normalized_row.get("source_element_mix", "") or ""),
            focus_geometry_kind,
        )
        inventory_pool = [
            candidate for candidate in member_catalog if str(candidate.get("geometry_kind", "") or "") in inventory_geometry_kinds
        ]
        if not inventory_pool:
            inventory_pool = list(candidate_pool)
        if not inventory_pool:
            inventory_pool = list(member_catalog)

        def _candidate_sort_key(candidate: dict[str, object]) -> tuple[int, int, int, float, float, str]:
            candidate_handle = str(candidate.get("aggregate_member_id", "") or "").strip()
            candidate_midpoint = candidate.get("midpoint")
            if not isinstance(candidate_midpoint, tuple) or len(candidate_midpoint) != 3:
                candidate_midpoint = (0.0, 0.0, 0.0)
            candidate_distance = math.dist(
                tuple(float(item) for item in focus_midpoint),
                tuple(float(item) for item in candidate_midpoint),
            )
            candidate_section_id = str(candidate.get("section_id", "") or "").strip()
            candidate_geometry_kind = str(candidate.get("geometry_kind", "") or "").strip()
            return (
                1 if candidate_handle in used_member_handles else 0,
                1 if candidate_section_id in used_section_ids and candidate_section_id else 0,
                0 if candidate_geometry_kind == focus_geometry_kind and focus_geometry_kind else 1,
                0.0 if candidate_section_id == focus_section_id and focus_section_id else 1.0,
                float(candidate_distance),
                candidate_handle,
            )

        best_candidate = min(candidate_pool, key=_candidate_sort_key) if candidate_pool else {}
        best_candidate_handle = str(best_candidate.get("aggregate_member_id", "") or "").strip()
        if best_candidate_handle and not existing_member_handle:
            existing_member_handle = best_candidate_handle
        if existing_member_handle:
            used_member_handles.add(existing_member_handle)
        load_names = _merge_normalized_bridge_names(
            normalized_row.get("full_crosswalk_load_combination_names"),
            normalized_row.get("row_provenance_combination_names"),
            [item.get("combination") for item in (normalized_row.get("row_provenance_rows") or []) if isinstance(item, dict)],
            exact_row.get("full_crosswalk_load_combination_names") if isinstance(exact_row, dict) else [],
        )
        full_section_id = _normalized_bridge_section_id(
            normalized_row.get("full_crosswalk_target_section_id")
            or best_candidate.get("section_id")
            or (snapshot.get("section_id") if isinstance(snapshot, dict) else "")
            or focus_section_id
        )
        normalized_row["surrogate_aggregate_member_id"] = str(
            normalized_row.get("surrogate_aggregate_member_id", "") or best_candidate_handle
        ).strip()
        normalized_row["full_crosswalk_target_member_handle"] = existing_member_handle
        normalized_row["full_crosswalk_target_section_id"] = full_section_id
        normalized_row["full_crosswalk_load_combination_names"] = load_names
        normalized_row["full_crosswalk_target_selector_kind"] = selector_kind
        normalized_row["full_crosswalk_target_geometry_kind"] = str(
            best_candidate.get("geometry_kind", "") or focus_geometry_kind
        ).strip()
        normalized_row["full_crosswalk_target_element_id"] = str(
            best_candidate.get("element_id", "") or baseline_focus_member_id
        ).strip()
        candidate_midpoint = best_candidate.get("midpoint")
        if isinstance(candidate_midpoint, tuple) and len(candidate_midpoint) == 3:
            normalized_row["full_crosswalk_target_distance"] = float(
                math.dist(
                    tuple(float(item) for item in focus_midpoint),
                    tuple(float(item) for item in candidate_midpoint),
                )
            )
        normalized_row["full_crosswalk_target_basis"] = (
            "aggregate_member_surrogate_inventory" if best_candidate_handle else "focus_member_snapshot"
        )
        exact_member_groups = _merge_normalized_bridge_names(
            normalized_row.get("full_crosswalk_member_groups"),
            exact_row.get("full_crosswalk_member_groups") if isinstance(exact_row, dict) else [],
        )
        if not exact_member_groups:
            exact_member_groups = list(inventory_groups)
        exact_section_groups = _merge_normalized_bridge_names(
            normalized_row.get("full_crosswalk_section_groups"),
            exact_row.get("full_crosswalk_section_groups") if isinstance(exact_row, dict) else [],
        )
        if not exact_section_groups:
            exact_section_groups = list(exact_member_groups or inventory_groups)
        derived_member_handles = _merge_normalized_bridge_names(
            [candidate.get("aggregate_member_id") for candidate in inventory_pool],
            [existing_member_handle],
            [normalized_row.get("surrogate_aggregate_member_id", "")],
        )
        if member_handle_kind == "aggregate_member_id":
            derived_member_handles = _merge_normalized_bridge_names(
                derived_member_handles,
                exact_row.get("full_crosswalk_member_handles") if isinstance(exact_row, dict) else [],
            )
        else:
            for group_name in exact_member_groups:
                derived_member_handles = _merge_normalized_bridge_names(
                    derived_member_handles,
                    member_handles_by_group.get(group_name, []),
                )
        derived_section_ids = _merge_normalized_bridge_section_ids(
            [_normalized_bridge_section_id(candidate.get("section_id")) for candidate in inventory_pool],
            normalized_row.get("full_crosswalk_section_ids"),
            [full_section_id],
            exact_row.get("full_crosswalk_section_ids") if isinstance(exact_row, dict) else [],
        )
        for member_handle in derived_member_handles:
            derived_section_ids = _merge_normalized_bridge_section_ids(
                derived_section_ids,
                section_ids_by_handle.get(member_handle, []),
            )
        for group_name in exact_section_groups:
            derived_section_ids = _merge_normalized_bridge_section_ids(
                derived_section_ids,
                section_ids_by_group.get(group_name, []),
            )
        normalized_row["full_crosswalk_member_groups"] = exact_member_groups
        normalized_row["full_crosswalk_member_handles"] = derived_member_handles
        normalized_row["full_crosswalk_section_groups"] = exact_section_groups
        normalized_row["full_crosswalk_section_ids"] = derived_section_ids
        if full_section_id:
            used_section_ids.add(full_section_id)
        enriched_rows.append(normalized_row)

    full_member_crosswalk_handles = {
        handle
        for row in enriched_rows
        for handle in _normalized_bridge_name_list(
            row.get("full_crosswalk_member_handles")
            or [
                row.get("full_crosswalk_target_member_handle", ""),
                row.get("surrogate_aggregate_member_id", ""),
            ]
        )
        if handle
    }
    full_section_crosswalk_ids = {
        section_id
        for row in enriched_rows
        for section_id in _normalized_bridge_section_id_list(
            row.get("full_crosswalk_section_ids")
            or [
                _normalized_bridge_section_id(
                    row.get("full_crosswalk_target_section_id")
                    or (
                        (row.get("review_geometry_snapshot") or {}).get("section_id")
                        if isinstance(row.get("review_geometry_snapshot"), dict)
                        else ""
                    )
                )
            ]
        )
        if section_id
    }
    full_load_crosswalk_names = {
        name
        for row in enriched_rows
        for name in _normalized_bridge_name_list(
            row.get("full_crosswalk_load_combination_names")
            or row.get("row_provenance_combination_names")
            or []
        )
    }
    expected_load_names = set(full_load_crosswalk_names) if full_load_crosswalk_names else set(expected_load_names)
    full_member_crosswalk_count = len(full_member_crosswalk_handles & expected_member_handles)
    full_section_crosswalk_count = len(full_section_crosswalk_ids & expected_section_ids)
    full_load_crosswalk_count = len(full_load_crosswalk_names & expected_load_names)
    full_member_crosswalk_expected = len(expected_member_handles)
    full_section_crosswalk_expected = len(expected_section_ids)
    full_load_crosswalk_expected = len(expected_load_names)
    summary = dict(bridge.get("summary") if isinstance(bridge.get("summary"), dict) else {})
    summary.update(
        {
            "full_member_crosswalk_count": int(full_member_crosswalk_count),
            "full_member_crosswalk_expected": int(full_member_crosswalk_expected),
            "full_member_crosswalk_status": (
                "PASS" if full_member_crosswalk_expected == 0 or full_member_crosswalk_count >= full_member_crosswalk_expected else "CHECK"
            ),
            "full_member_crosswalk_handle_kind": member_handle_kind,
            "full_member_crosswalk_handles": sorted(full_member_crosswalk_handles),
            "full_section_crosswalk_count": int(full_section_crosswalk_count),
            "full_section_crosswalk_expected": int(full_section_crosswalk_expected),
            "full_section_crosswalk_status": (
                "PASS" if full_section_crosswalk_expected == 0 or full_section_crosswalk_count >= full_section_crosswalk_expected else "CHECK"
            ),
            "full_section_crosswalk_ids": sorted(full_section_crosswalk_ids),
            "full_load_crosswalk_count": int(full_load_crosswalk_count),
            "full_load_crosswalk_expected": int(full_load_crosswalk_expected),
            "full_load_crosswalk_status": (
                "PASS" if full_load_crosswalk_expected == 0 or full_load_crosswalk_count >= full_load_crosswalk_expected else "CHECK"
            ),
            "full_load_crosswalk_names": sorted(full_load_crosswalk_names),
            "full_crosswalk_summary_label": (
                f"members={full_member_crosswalk_count}/{full_member_crosswalk_expected} "
                f"{'PASS' if full_member_crosswalk_expected == 0 or full_member_crosswalk_count >= full_member_crosswalk_expected else 'CHECK'} | "
                f"sections={full_section_crosswalk_count}/{full_section_crosswalk_expected} "
                f"{'PASS' if full_section_crosswalk_expected == 0 or full_section_crosswalk_count >= full_section_crosswalk_expected else 'CHECK'} | "
                f"loads={full_load_crosswalk_count}/{full_load_crosswalk_expected} "
                f"{'PASS' if full_load_crosswalk_expected == 0 or full_load_crosswalk_count >= full_load_crosswalk_expected else 'CHECK'}"
            ),
        }
    )
    enriched_bridge = dict(bridge)
    enriched_bridge["summary"] = summary
    enriched_bridge["bridge_rows"] = enriched_rows
    return enriched_bridge


def _build_kds_geometry_bridge_index(model_payload: dict[str, object]) -> dict[str, dict[str, str]]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    metadata = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
    element_rows = [row for row in (model.get("elements") or []) if isinstance(row, dict)]
    member_rows = [row for row in (metadata.get("members") or []) if isinstance(row, dict)]

    bridge_index: dict[str, dict[str, str]] = {}
    for row in element_rows:
        element_id = str(row.get("id", "") or "").strip()
        if not element_id:
            continue
        bridge_index.setdefault(
            element_id,
            {
                "baseline_focus_member_id": element_id,
                "match_strategy": "element_id_direct",
                "match_confidence": "exact_id",
            },
        )

    for row in member_rows:
        representative_id = _representative_baseline_member_id(row)
        if not representative_id:
            continue
        aggregate_id = str(row.get("id", "") or "").strip()
        if aggregate_id:
            bridge_index.setdefault(
                aggregate_id,
                {
                    "baseline_focus_member_id": representative_id,
                    "match_strategy": "member_aggregate_seed",
                    "match_confidence": "aggregate_to_seed",
                },
            )
        element_seed = str(row.get("element_seed", "") or "").strip()
        if element_seed:
            bridge_index.setdefault(
                element_seed,
                {
                    "baseline_focus_member_id": element_seed,
                    "match_strategy": "element_seed_direct",
                    "match_confidence": "exact_id",
                },
            )
        for element_id in (
            str(item).strip()
            for item in (row.get("element_ids") or [])
            if str(item).strip()
        ):
            bridge_index.setdefault(
                element_id,
                {
                    "baseline_focus_member_id": element_id,
                    "match_strategy": "member_element_direct",
                    "match_confidence": "exact_id",
                },
            )
    return bridge_index


def _build_external_kds_geometry_bridge_index(
    bridge_registry: dict[str, object] | None,
) -> tuple[dict[str, dict[str, object]], dict[str, object]]:
    registry = bridge_registry if isinstance(bridge_registry, dict) else {}
    rows = registry.get("mappings")
    if not isinstance(rows, list):
        rows = registry.get("bridge_rows")
    if not isinstance(rows, list):
        rows = []
    if registry:
        source_label = str(
            registry.get("source", "") or registry.get("provenance", "") or registry.get("registry_kind", "") or "external_registry"
        ).strip() or "external_registry"
        contract_version = str(registry.get("contract_version", "") or "0.1.0").strip() or "0.1.0"
    else:
        source_label = "none"
        contract_version = "0.1.0"
    registry_index: dict[str, dict[str, object]] = {}
    usable_rows = 0
    exact_row_count = 0
    heuristic_row_count = 0
    source_counts: Counter[str] = Counter()

    def _is_heuristic_match(match_row: dict[str, str]) -> bool:
        confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
        return confidence.startswith("heuristic")

    def _is_reviewer_verified_match(match_row: dict[str, str]) -> bool:
        if _is_truthy(match_row.get("reviewer_verified")):
            return True
        strategy = str(match_row.get("match_strategy", "") or "").strip().lower()
        confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
        row_source = str(match_row.get("registry_source_label", "") or source_label).strip().lower()
        return any(
            token in strategy or token in confidence or token in row_source
            for token in ("reviewer_verified", "manual_verified", "external_registry_manual")
        )

    def _match_priority(match_row: dict[str, str]) -> tuple[int, int, str, str]:
        heuristic = _is_heuristic_match(match_row)
        reviewer_verified = _is_reviewer_verified_match(match_row)
        strategy = str(match_row.get("match_strategy", "") or "").strip().lower()
        confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
        if reviewer_verified and not heuristic:
            band = 4
        elif not heuristic:
            band = 3
        else:
            band = 2
        directness = 1 if strategy.endswith("direct") or confidence == "exact_id" else 0
        return (band, directness, confidence, strategy)

    for row in rows:
        if not isinstance(row, dict):
            continue
        baseline_focus_member_id = str(row.get("baseline_focus_member_id", "") or "").strip()
        if not baseline_focus_member_id:
            continue
        review_keys = {
            str(row.get("review_member_id", "") or "").strip(),
            str(row.get("review_case_id", "") or "").strip(),
        }
        review_keys.update(
            str(item).strip()
            for item in (row.get("review_keys") or [])
            if str(item).strip()
        )
        review_keys.discard("")
        if not review_keys:
            continue
        usable_rows += 1
        match_strategy = str(row.get("match_strategy", "") or "external_registry").strip() or "external_registry"
        match_confidence = str(row.get("match_confidence", "") or "external_map").strip() or "external_map"
        row_source_label = str(row.get("registry_source_label", "") or source_label).strip() or source_label
        row_contract_version = str(row.get("registry_contract_version", "") or contract_version).strip() or contract_version
        reviewer_verified = _is_truthy(row.get("reviewer_verified")) or _is_reviewer_verified_match(
            {
                "match_strategy": match_strategy,
                "match_confidence": match_confidence,
                "registry_source_label": row_source_label,
                "reviewer_verified": row.get("reviewer_verified"),
            }
        )
        note = str(row.get("note", "") or "").strip()
        selector_kind = str(row.get("selector_kind", "") or "").strip()
        source_family = str(row.get("source_family", "") or "").strip()
        source_topology_type = str(row.get("source_topology_type", "") or "").strip()
        source_member_type = str(row.get("source_member_type", "") or "").strip()
        source_hazard_type = str(row.get("source_hazard_type", "") or "").strip()
        source_element_mix = str(row.get("source_element_mix", "") or "").strip()
        surrogate_geometry_kind = str(row.get("surrogate_geometry_kind", "") or "").strip()
        surrogate_aggregate_member_id = str(row.get("surrogate_aggregate_member_id", "") or "").strip()
        normalized_row = {
            "baseline_focus_member_id": baseline_focus_member_id,
            "match_strategy": match_strategy,
            "match_confidence": match_confidence,
            "note": note,
            "selector_kind": selector_kind,
            "source_family": source_family,
            "source_topology_type": source_topology_type,
            "source_member_type": source_member_type,
            "source_hazard_type": source_hazard_type,
            "source_element_mix": source_element_mix,
            "surrogate_geometry_kind": surrogate_geometry_kind,
            "surrogate_aggregate_member_id": surrogate_aggregate_member_id,
            "registry_source_label": row_source_label,
            "registry_contract_version": row_contract_version,
            "reviewer_verified": reviewer_verified,
        }
        review_geometry_snapshot = row.get("review_geometry_snapshot")
        if isinstance(review_geometry_snapshot, dict) and review_geometry_snapshot:
            normalized_row["review_geometry_snapshot"] = dict(review_geometry_snapshot)
        if _is_heuristic_match(normalized_row):
            heuristic_row_count += 1
        else:
            exact_row_count += 1
        source_counts[row_source_label] += 1
        for review_key in sorted(review_keys):
            existing = registry_index.get(review_key)
            if existing is None or _match_priority(normalized_row) > _match_priority(existing):
                registry_index[review_key] = dict(normalized_row)
    return registry_index, {
        "source_label": source_label,
        "contract_version": contract_version,
        "row_count": str(len(rows)),
        "usable_row_count": str(usable_rows),
        "exact_row_count": str(exact_row_count),
        "heuristic_row_count": str(heuristic_row_count),
        "source_counts": {str(key): int(value) for key, value in sorted(source_counts.items())},
    }


def _is_heuristic_bridge_match(match_row: dict[str, object]) -> bool:
    confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
    return confidence.startswith("heuristic")


def _is_reviewer_verified_bridge_match(match_row: dict[str, object]) -> bool:
    if _is_truthy(match_row.get("reviewer_verified")):
        return True
    strategy = str(match_row.get("match_strategy", "") or "").strip().lower()
    confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
    source_label = str(match_row.get("registry_source_label", "") or "").strip().lower()
    return any(
        token in strategy or token in confidence or token in source_label
        for token in ("reviewer_verified", "manual_verified", "external_registry_manual")
    )


def _bridge_match_priority(match_row: dict[str, object], *, external: bool = False) -> tuple[int, int, int, str, str]:
    heuristic = _is_heuristic_bridge_match(match_row)
    reviewer_verified = _is_reviewer_verified_bridge_match(match_row)
    confidence = str(match_row.get("match_confidence", "") or "").strip().lower()
    strategy = str(match_row.get("match_strategy", "") or "").strip().lower()
    if reviewer_verified and not heuristic:
        band = 4
    elif external and not heuristic:
        band = 3
    elif not heuristic:
        band = 2
    else:
        band = 1
    directness = 1 if strategy.endswith("direct") or confidence == "exact_id" else 0
    return (band, directness, 1 if str(match_row.get("baseline_focus_member_id", "") or "").strip() else 0, confidence, strategy)


def derive_kds_geometry_bridge_for_model_payload(
    model_payload: dict[str, object],
    *,
    code_check_report: dict[str, object] | None = None,
    bridge_registry: dict[str, object] | None = None,
) -> dict[str, object]:
    report = code_check_report if isinstance(code_check_report, dict) else {}
    named_axis_refs = _extract_named_axis_refs_from_model_payload(model_payload)
    named_axis_available = any(named_axis_refs.values())
    member_check_rows = [
        row
        for row in (report.get("member_check_rows") or [])
        if isinstance(row, dict)
    ]
    if not member_check_rows:
        return {}

    bridge_index = _build_kds_geometry_bridge_index(model_payload)
    registry_index, registry_meta = _build_external_kds_geometry_bridge_index(bridge_registry)
    unique_review_rows: list[dict[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()
    review_rows_by_pair: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in member_check_rows:
        review_member_id = str(row.get("member_id", "") or "").strip()
        review_case_id = str(row.get("case_id", "") or review_member_id).strip()
        pair = (review_member_id, review_case_id)
        review_rows_by_pair.setdefault(pair, []).append(row)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        unique_review_rows.append(
            {
                "review_member_id": review_member_id,
                "review_case_id": review_case_id,
            }
        )

    strategy_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    bridge_rows: list[dict[str, object]] = []
    mapped_review_id_count = 0
    exact_mapped_review_id_count = 0
    heuristic_mapped_review_id_count = 0
    mapped_row_provenance_count = 0
    exact_mapped_row_provenance_count = 0
    heuristic_mapped_row_provenance_count = 0
    for row in unique_review_rows:
        review_member_id = str(row.get("review_member_id", "") or "").strip()
        review_case_id = str(row.get("review_case_id", "") or "").strip()
        review_keys = [key for key in [review_member_id, review_case_id] if key]
        provenance_rows = list(review_rows_by_pair.get((review_member_id, review_case_id), []))
        ordered_provenance_rows = sorted(
            provenance_rows,
            key=lambda item: (
                -float(item.get("dcr", 0.0) or 0.0),
                str(item.get("combination", "") or ""),
                str(item.get("component", "") or ""),
            ),
        )
        matched: dict[str, object] | None = None
        matched_external = False
        for candidate in review_keys:
            for candidate_row, is_external in (
                (registry_index.get(candidate), True),
                (bridge_index.get(candidate), False),
            ):
                if not isinstance(candidate_row, dict):
                    continue
                if matched is None or _bridge_match_priority(candidate_row, external=is_external) > _bridge_match_priority(matched, external=matched_external):
                    matched = candidate_row
                    matched_external = is_external
        baseline_focus_member_id = str((matched or {}).get("baseline_focus_member_id", "") or "").strip()
        match_strategy = str((matched or {}).get("match_strategy", "") or "unmapped").strip() or "unmapped"
        match_confidence = str((matched or {}).get("match_confidence", "") or "none").strip() or "none"
        if baseline_focus_member_id:
            mapped_review_id_count += 1
            if _is_heuristic_bridge_match(matched or {}):
                heuristic_mapped_review_id_count += 1
                heuristic_mapped_row_provenance_count += len(ordered_provenance_rows)
            else:
                exact_mapped_review_id_count += 1
                exact_mapped_row_provenance_count += len(ordered_provenance_rows)
            mapped_row_provenance_count += len(ordered_provenance_rows)
        strategy_counts[match_strategy] += 1
        confidence_counts[match_confidence] += 1
        combination_names = sorted(
            {
                str(item.get("combination", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("combination", "") or "").strip()
            }
        )
        clause_names = sorted(
            {
                str(item.get("clause", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("clause", "") or "").strip()
            }
        )
        component_names = sorted(
            {
                str(item.get("component", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("component", "") or "").strip()
            }
        )
        rule_family_names = sorted(
            {
                str(item.get("rule_family", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("rule_family", "") or "").strip()
            }
        )
        hazard_names = sorted(
            {
                str(item.get("hazard_type", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("hazard_type", "") or "").strip()
            }
        )
        topology_names = sorted(
            {
                str(item.get("topology_type", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("topology_type", "") or "").strip()
            }
        )
        top_provenance_row = ordered_provenance_rows[0] if ordered_provenance_rows else {}
        top_provenance_label = (
            f"{str(top_provenance_row.get('combination', '') or 'n/a')} | "
            f"{str(top_provenance_row.get('component', '') or 'component n/a')} | "
            f"{str(top_provenance_row.get('clause', '') or 'clause n/a')} | "
            f"D/C={float(top_provenance_row.get('dcr', 0.0) or 0.0):.3f}"
            if top_provenance_row
            else "no row-level provenance rows"
        )
        member_type_names = sorted(
            {
                str(item.get("member_type", "") or "").strip()
                for item in ordered_provenance_rows
                if str(item.get("member_type", "") or "").strip()
            }
        )
        row_provenance_rows = [
            {
                "member_id": str(item.get("member_id", "") or "").strip(),
                "case_id": str(item.get("case_id", "") or "").strip(),
                "member_type": str(item.get("member_type", "") or "").strip(),
                "combination": str(item.get("combination", "") or "").strip(),
                "combination_scale": float(item.get("combination_scale", 0.0) or 0.0),
                "component": str(item.get("component", "") or "").strip(),
                "clause": str(item.get("clause", "") or "").strip(),
                "rule_family": str(item.get("rule_family", "") or "").strip(),
                "hazard_type": str(item.get("hazard_type", "") or "").strip(),
                "topology_type": str(item.get("topology_type", "") or "").strip(),
                "demand": float(item.get("demand", 0.0) or 0.0),
                "capacity": float(item.get("capacity", 0.0) or 0.0),
                "dcr": float(item.get("dcr", 0.0) or 0.0),
            }
            for item in ordered_provenance_rows
        ]
        review_keys_label = ", ".join(review_keys) or "none"
        member_type_label = ", ".join(member_type_names) or "unknown"
        member_inventory_summary_label = (
            f"review={review_member_id or 'n/a'} | case={review_case_id or 'n/a'} | "
            f"baseline={baseline_focus_member_id or 'n/a'} | member_types={member_type_label}"
        )
        clause_provenance_summary_label = (
            f"clauses={len(clause_names)} | rules={len(rule_family_names)} | "
            f"hazards={len(hazard_names)} | top={top_provenance_label}"
        )
        bridge_rows.append(
            {
                "review_member_id": review_member_id,
                "review_case_id": review_case_id,
                "review_keys": review_keys,
                "review_keys_label": review_keys_label,
                "baseline_focus_member_id": baseline_focus_member_id,
                "match_strategy": match_strategy,
                "match_confidence": match_confidence,
                "selector_kind": str((matched or {}).get("selector_kind", "") or "").strip(),
                "source_family": str((matched or {}).get("source_family", "") or "").strip(),
                "source_topology_type": str((matched or {}).get("source_topology_type", "") or "").strip(),
                "source_member_type": str((matched or {}).get("source_member_type", "") or "").strip(),
                "source_hazard_type": str((matched or {}).get("source_hazard_type", "") or "").strip(),
                "source_element_mix": str((matched or {}).get("source_element_mix", "") or "").strip(),
                "surrogate_geometry_kind": str((matched or {}).get("surrogate_geometry_kind", "") or "").strip(),
                "surrogate_aggregate_member_id": str((matched or {}).get("surrogate_aggregate_member_id", "") or "").strip(),
                "review_geometry_snapshot": dict((matched or {}).get("review_geometry_snapshot", {}))
                if isinstance((matched or {}).get("review_geometry_snapshot"), dict)
                else {},
                "full_crosswalk_member_groups": _normalized_bridge_name_list(
                    (matched or {}).get("full_crosswalk_member_groups")
                ),
                "full_crosswalk_member_handles": _normalized_bridge_name_list(
                    (matched or {}).get("full_crosswalk_member_handles")
                ),
                "full_crosswalk_section_groups": _normalized_bridge_name_list(
                    (matched or {}).get("full_crosswalk_section_groups")
                ),
                "full_crosswalk_section_ids": _normalized_bridge_name_list(
                    (matched or {}).get("full_crosswalk_section_ids")
                ),
                "full_crosswalk_load_combination_names": _normalized_bridge_name_list(
                    (matched or {}).get("full_crosswalk_load_combination_names")
                ),
                "full_crosswalk_target_member_handle": str(
                    (matched or {}).get("full_crosswalk_target_member_handle", "") or ""
                ).strip(),
                "full_crosswalk_target_section_id": _normalized_bridge_section_id(
                    (matched or {}).get("full_crosswalk_target_section_id")
                ),
                "registry_source_label": str((matched or {}).get("registry_source_label", "") or "").strip(),
                "registry_contract_version": str((matched or {}).get("registry_contract_version", "") or "").strip(),
                "reviewer_verified": _is_truthy((matched or {}).get("reviewer_verified")),
                "mapped": bool(baseline_focus_member_id),
                "member_inventory_count": int(1 if (review_member_id or review_case_id) else 0),
                "member_inventory_member_type_names": member_type_names,
                "member_inventory_member_type_label": member_type_label,
                "member_inventory_summary_label": member_inventory_summary_label,
                "row_provenance_row_count": int(len(row_provenance_rows)),
                "row_provenance_combination_count": int(len(combination_names)),
                "row_provenance_clause_count": int(len(clause_names)),
                "row_provenance_component_count": int(len(component_names)),
                "row_provenance_rule_family_count": int(len(rule_family_names)),
                "row_provenance_hazard_count": int(len(hazard_names)),
                "row_provenance_topology_count": int(len(topology_names)),
                "row_provenance_combination_names": combination_names,
                "row_provenance_clause_names": clause_names,
                "row_provenance_component_names": component_names,
                "row_provenance_rule_family_names": rule_family_names,
                "row_provenance_hazard_names": hazard_names,
                "row_provenance_topology_names": topology_names,
                "row_provenance_top_row_label": top_provenance_label,
                "row_provenance_summary_label": (
                    f"rows={len(row_provenance_rows)} | combos={len(combination_names)} | clauses={len(clause_names)} | top={top_provenance_label}"
                ),
                "clause_provenance_summary_label": clause_provenance_summary_label,
                "clause_provenance_clause_names": clause_names,
                "clause_provenance_rule_family_names": rule_family_names,
                "clause_provenance_hazard_names": hazard_names,
                "clause_provenance_topology_names": topology_names,
                "row_provenance_rows": row_provenance_rows,
                "note": (
                    str((matched or {}).get("note", "") or "").strip()
                    or f"explicit bridge to baseline member {baseline_focus_member_id}"
                    if baseline_focus_member_id
                    else "no explicit geometry bridge in current artifact; semantic review ids still need an external map."
                ),
            }
        )

    review_id_count = len(unique_review_rows)
    unmapped_review_id_count = max(review_id_count - mapped_review_id_count, 0)
    review_row_count = int(len(member_check_rows))
    unmapped_row_provenance_count = max(review_row_count - mapped_row_provenance_count, 0)
    limitations: list[str] = []
    if heuristic_mapped_review_id_count:
        limitations.append(
            "heuristic semantic-case bridge rows are surrogate links, not reviewer-verified exact geometry ids; use them as guided navigation rather than exact member authority."
        )
    if int(registry_meta.get("exact_row_count", "0") or 0):
        limitations.append(
            "external reviewer/exact registry rows override heuristic bridge rows for overlapping review ids when a verified mapping is available."
        )
    if unmapped_review_id_count:
        limitations.append(
            "current bridge contract only resolves explicit/direct ids; semantic review ids such as C-TST-003 still require an external map."
        )
    if registry_index:
        limitations.append(
            f"external registry rows were applied from {registry_meta['source_label']}; unmapped semantic ids still need additional registry coverage."
        )
    else:
        limitations.append(
            "no external KDS geometry bridge registry was provided; semantic review ids remain unmapped until an external registry is attached."
        )
    if not bridge_index:
        limitations.append("baseline artifact has no member/element bridge index, so only external mapping can resolve review ids.")

    return enrich_kds_geometry_bridge_full_crosswalk_metadata(
        model_payload,
        {
        "contract_version": "0.3.0",
        "provenance": "kds_codecheck_bridge_metadata",
        "bridge_kind": "kds_geometry_bridge",
        "registry_source_label": registry_meta.get("source_label", "none"),
        "registry_contract_version": registry_meta.get("contract_version", "0.1.0"),
        "axis_refs": named_axis_refs,
        "axis_ref_source_mode": "metadata_named_axis_refs" if named_axis_available else "none",
        "axis_ref_note": (
            "Named axis/grid references were carried through from MIDAS metadata into the geometry bridge."
            if named_axis_available
            else "Named axis/grid references are unavailable in the current MIDAS source artifact."
        ),
        "summary": {
            "review_row_count": review_row_count,
            "review_id_count": int(review_id_count),
            "mapped_review_id_count": int(mapped_review_id_count),
            "exact_mapped_review_id_count": int(exact_mapped_review_id_count),
            "heuristic_mapped_review_id_count": int(heuristic_mapped_review_id_count),
            "unmapped_review_id_count": int(unmapped_review_id_count),
            "mapped_row_provenance_count": int(mapped_row_provenance_count),
            "exact_mapped_row_provenance_count": int(exact_mapped_row_provenance_count),
            "heuristic_mapped_row_provenance_count": int(heuristic_mapped_row_provenance_count),
            "unmapped_row_provenance_count": int(unmapped_row_provenance_count),
            "strategy_counts": {str(key): int(value) for key, value in sorted(strategy_counts.items())},
            "confidence_counts": {str(key): int(value) for key, value in sorted(confidence_counts.items())},
            "external_registry_row_count": int(registry_meta.get("row_count", "0") or 0),
            "external_registry_usable_row_count": int(registry_meta.get("usable_row_count", "0") or 0),
            "external_registry_exact_row_count": int(registry_meta.get("exact_row_count", "0") or 0),
            "external_registry_heuristic_row_count": int(registry_meta.get("heuristic_row_count", "0") or 0),
            "external_registry_source_counts": registry_meta.get("source_counts", {}) if isinstance(registry_meta.get("source_counts"), dict) else {},
            "axis_ref_counts": {
                dimension: int(len(named_axis_refs.get(dimension, [])))
                for dimension in ("x", "y", "z")
            },
        },
        "bridge_rows": bridge_rows,
        "limitations": limitations,
        },
    )


def derive_load_productization_from_raw_combination_payload(model_payload: dict) -> dict[str, object]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    minimal_structured_loads = derive_minimal_structured_loads_from_raw_combination_payload(model_payload)
    if not minimal_structured_loads:
        return {}

    load_combinations = [
        row for row in (minimal_structured_loads.get("load_combinations") or [])
        if isinstance(row, dict)
    ]
    load_combination_graph = (
        minimal_structured_loads.get("load_combination_graph")
        if isinstance(minimal_structured_loads.get("load_combination_graph"), dict)
        else {}
    )
    semantic_load_summary = (
        minimal_structured_loads.get("semantic_load_summary")
        if isinstance(minimal_structured_loads.get("semantic_load_summary"), dict)
        else {}
    )
    static_load_cases = [
        row for row in (minimal_structured_loads.get("static_load_cases") or [])
        if isinstance(row, dict)
    ]

    case_reference_counts: Counter[str] = Counter()
    limit_state_counts: Counter[str] = Counter()
    expansion_mode_counts: Counter[str] = Counter()
    design_situation_counts: Counter[str] = Counter()
    semantic_status_counts: Counter[str] = Counter()
    referenced_case_union: set[str] = set()
    referenced_leaf_case_union: set[str] = set()
    max_expansion_depth = 0
    nested_combination_count = 0

    for row in load_combinations:
        limit_state = str(row.get("limit_state", "") or row.get("combination_type", "") or "unspecified").strip() or "unspecified"
        limit_state_counts[limit_state] += 1
        expansion_mode = str(row.get("expansion_mode", "") or "linear_combination").strip() or "linear_combination"
        expansion_mode_counts[expansion_mode] += 1
        try:
            expansion_depth_value = int(row.get("expansion_depth", 0) or 0)
        except (TypeError, ValueError):
            expansion_depth_value = 0
        max_expansion_depth = max(max_expansion_depth, expansion_depth_value)
        if row.get("referenced_combinations"):
            nested_combination_count += 1
        reference_names: set[str] = set()
        for case_name in (row.get("referenced_cases") or []):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                referenced_case_union.add(normalized)
                reference_names.add(normalized)
        for case_name in (row.get("referenced_leaf_cases") or row.get("referenced_cases") or []):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                referenced_leaf_case_union.add(normalized)
                reference_names.add(normalized)
        for case_name in (row.get("factor_map") or {}):
            normalized = _normalize_load_reference(str(case_name))
            if normalized:
                referenced_case_union.add(normalized)
                referenced_leaf_case_union.add(normalized)
                reference_names.add(normalized)
        for case_name in sorted(reference_names):
            case_reference_counts[case_name] += 1
    case_order = [
        _normalize_load_reference(str(row.get("name", "")))
        for row in static_load_cases
        if _normalize_load_reference(str(row.get("name", "")))
    ]

    semantic_case_rows = []
    pattern_rows = []
    for case_name in case_order:
        design_situation = _load_pattern_design_situation(case_name)
        semantic_status = "combination_only_raw_recovery"
        design_situation_counts[design_situation] += 1
        semantic_status_counts[semantic_status] += 1
        reference_count = int(case_reference_counts.get(case_name, 0) or 0)
        semantic_case_rows.append(
            {
                "load_case": case_name,
                "semantic_status": semantic_status,
                "reference_count": reference_count,
                "notes": "Recovered from raw LOADCOMB rows because a structured loads block was unavailable.",
            }
        )
        pattern_rows.append(
            {
                "pattern_id": f"midas:raw:{case_name}",
                "label": case_name,
                "design_situation": design_situation,
                "primitive_count": 0,
                "primitive_counts": {},
                "tags": [design_situation, semantic_status, "raw_combination_recovery"],
                "primitives": [],
            }
        )

    load_pattern_library = {
        "contract_version": "0.1.0",
        "provenance": "combination_only_raw_recovery",
        "limitations": [
            "Recovered from raw LOADCOMB rows because a structured loads block was unavailable.",
            "Load primitives are unavailable in this recovery path and are represented as zero-primitive authoring seeds.",
            "Combination expansion is suitable for browser/editor continuity, not a final solver-side load card reconstruction.",
        ],
        "pattern_summary": {
            "pattern_count": int(len(pattern_rows)),
            "primitive_count": 0,
            "primitive_kind_counts": {},
            "case_counts": {str(key): int(value) for key, value in sorted(case_reference_counts.items())},
            "patterns": pattern_rows,
        },
        "case_semantic_rows": semantic_case_rows,
        "combination_summary": {
            "combination_count": int(len(load_combinations)),
            "limit_state_counts": {str(key): int(value) for key, value in sorted(limit_state_counts.items())},
            "expansion_mode_counts": {str(key): int(value) for key, value in sorted(expansion_mode_counts.items())},
            "max_expansion_depth": int(max_expansion_depth),
            "nested_combination_count": int(nested_combination_count),
            "referenced_case_union": sorted(referenced_case_union),
            "referenced_leaf_case_union": sorted(referenced_leaf_case_union),
            "combination_names": [str(row.get("name", "") or "") for row in load_combinations if str(row.get("name", "") or "")],
        },
        "summary": {
            "pattern_count": int(len(pattern_rows)),
            "primitive_count": 0,
            "design_situation_counts": {str(key): int(value) for key, value in sorted(design_situation_counts.items())},
            "semantic_status_counts": {str(key): int(value) for key, value in sorted(semantic_status_counts.items())},
            "load_color_row_count": 0,
        },
    }
    load_combination_editor_seed = _derive_load_combination_editor_seed(
        load_combinations=load_combinations,
        load_combination_graph=load_combination_graph,
        load_pattern_library=load_pattern_library,
        semantic_load_summary=semantic_load_summary,
    )
    if load_combination_editor_seed:
        load_combination_editor_seed = dict(load_combination_editor_seed)
        load_combination_editor_seed["provenance"] = "combination_only_raw_recovery"
        load_combination_editor_seed["limitations"] = [
            "Recovered from raw LOADCOMB rows because a structured loads block was unavailable.",
            *[
                str(item)
                for item in (load_combination_editor_seed.get("limitations") or [])
                if str(item)
            ],
        ][:4]

    return {
        "loads": minimal_structured_loads,
        "load_pattern_library": load_pattern_library,
        "load_combination_editor_seed": load_combination_editor_seed,
        "recovery_summary": {
            "mode": "combination_only_raw_recovery",
            "raw_row_count": int(len(model.get("load_combinations_raw") or [])),
            "combination_count": int(len(load_combinations)),
            "case_count": int(len(case_order)),
            "graph_edge_count": int((load_combination_graph.get("edge_count") or len(load_combination_graph.get("edges") or [])) or 0),
        },
    }


def derive_minimal_structured_loads_from_raw_combination_payload(model_payload: dict) -> dict[str, object]:
    model = model_payload.get("model") if isinstance(model_payload.get("model"), dict) else model_payload
    if not isinstance(model, dict):
        return {}
    raw_rows = [
        str(row).strip()
        for row in (model.get("load_combinations_raw") or [])
        if str(row).strip()
    ]
    if not raw_rows:
        return {}

    load_combinations = _parse_loadcomb_rows(raw_rows)
    if not load_combinations:
        return {}
    load_combination_graph = _build_load_combination_graph(load_combinations)

    case_order: list[str] = []
    seen_cases: set[str] = set()
    for combo in load_combinations:
        reference_names: list[str] = []
        reference_names.extend(
            _normalize_load_reference(str(item))
            for item in (combo.get("referenced_leaf_cases") or combo.get("referenced_cases") or [])
        )
        reference_names.extend(
            _normalize_load_reference(str(item))
            for item in ((combo.get("factor_map") or {}).keys() if isinstance(combo.get("factor_map"), dict) else [])
        )
        for case_name in reference_names:
            if case_name and case_name not in seen_cases:
                seen_cases.add(case_name)
                case_order.append(case_name)

    static_load_cases = [
        {
            "name": case_name,
            "type": str(_load_pattern_design_situation(case_name)).upper(),
            "description": "Recovered minimal static case from raw LOADCOMB references.",
        }
        for case_name in case_order
    ]
    load_cases = [
        {
            "name": case_name,
            "category": str(_load_pattern_design_situation(case_name)).upper(),
            "subtype": "RAW_COMBINATION_RECOVERY",
            "scale": 1.0,
            "load_refs": [case_name],
            "raw_token_count": 0,
            "raw": "recovered_from_loadcomb",
        }
        for case_name in case_order
    ]
    semantic_case_rows = [
        {
            "load_case": case_name,
            "nodal_load_row_count": 0,
            "nodal_target_node_count": 0,
            "nodal_force_sum": {"fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
            "selfweight_row_count": 0,
            "selfweight_vector": {"gx": 0.0, "gy": 0.0, "gz": 0.0},
            "pressure_row_count": 0,
            "pressure_target_element_count": 0,
            "pressure_scalar_sum": 0.0,
            "body_load_assembly_pending": False,
            "surface_load_assembly_pending": False,
            "semantic_status": "combination_only_raw_recovery",
            "notes": "Recovered from raw LOADCOMB rows because a structured loads block was unavailable.",
        }
        for case_name in case_order
    ]
    combination_force_rows = [
        {
            "name": str(combo.get("name", "") or ""),
            "limit_state": str(combo.get("limit_state", "") or str(combo.get("combination_type", "")) or ""),
            "referenced_cases": [
                _normalize_load_reference(str(item))
                for item in (combo.get("referenced_leaf_cases") or combo.get("referenced_cases") or [])
                if _normalize_load_reference(str(item))
            ],
            "combined_nodal_force_sum": {"fx": 0.0, "fy": 0.0, "fz": 0.0, "mx": 0.0, "my": 0.0, "mz": 0.0},
            "combined_selfweight_vector": {"gx": 0.0, "gy": 0.0, "gz": 0.0},
            "combined_pressure_scalar_sum": 0.0,
            "body_load_assembly_pending": False,
            "surface_load_assembly_pending": False,
        }
        for combo in load_combinations
    ]
    semantic_load_summary = {
        "case_count": int(len(semantic_case_rows)),
        "combination_count": int(len(combination_force_rows)),
        "bound_nodal_load_row_count": 0,
        "bound_selfweight_row_count": 0,
        "bound_pressure_row_count": 0,
        "unbound_nodal_load_row_count": 0,
        "unbound_selfweight_row_count": 0,
        "unbound_pressure_row_count": 0,
        "body_load_pending_case_count": 0,
        "surface_load_pending_case_count": 0,
        "case_force_summaries": semantic_case_rows,
        "combination_force_summaries": combination_force_rows,
    }

    return {
        "static_load_cases": static_load_cases,
        "active_static_case_sequence": list(case_order),
        "load_cases": load_cases,
        "load_combinations": load_combinations,
        "load_combination_graph": load_combination_graph,
        "semantic_load_summary": semantic_load_summary,
        "selfweight": [],
        "nodal_loads": [],
        "nodal_masses": [],
        "beam_offsets": [],
        "pressure_loads": [],
        "recovery_contract": {
            "mode": "combination_only_raw_recovery",
            "notes": "Minimal structured loads contract recovered from raw LOADCOMB rows.",
            "raw_row_count": int(len(raw_rows)),
            "combination_count": int(len(load_combinations)),
            "case_count": int(len(case_order)),
        },
    }


def _parse_elastic_links(rows: list[str], node_ids: set[int]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        toks = _split_csv_like(row)
        if len(toks) < 4:
            continue
        lid = _as_int(toks[0])
        n1 = _as_int(toks[1])
        n2 = _as_int(toks[2])
        if lid is None or n1 is None or n2 is None:
            continue
        if int(n1) not in node_ids or int(n2) not in node_ids:
            continue
        link_type = str(toks[3]).strip().upper()
        numeric_tail = [float(v) for v in (_as_float(t) for t in toks[4:]) if v is not None]
        stiffness_indicator = max((abs(v) for v in numeric_tail), default=0.0)
        out.append(
            {
                "id": int(lid),
                "node1": int(n1),
                "node2": int(n2),
                "type": link_type,
                "stiffness_indicator": float(stiffness_indicator),
                "raw": row,
            }
        )
    return out


class _DSU:
    def __init__(self, nodes: set[int]) -> None:
        self.parent = {int(n): int(n) for n in nodes}

    def find(self, x: int) -> int:
        p = self.parent[int(x)]
        if p != x:
            self.parent[int(x)] = self.find(p)
        return self.parent[int(x)]

    def union(self, a: int, b: int) -> bool:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return False
        # keep lower node id as master representative.
        if ra < rb:
            self.parent[rb] = ra
        else:
            self.parent[ra] = rb
        return True


def _resolve_rigid_links(
    *,
    nodes: dict[int, tuple[float, float, float]],
    elements: list[dict],
    elastic_links: list[dict],
    support_nodes: set[int],
    rigid_stiffness_threshold: float,
    drop_unreferenced_nodes: bool,
) -> tuple[dict[int, tuple[float, float, float]], list[dict], dict[str, object]]:
    degree: Counter[int] = Counter()
    for e in elements:
        for nid in e.get("node_ids", []):
            degree[int(nid)] += 1

    dsu = _DSU(set(nodes.keys()))
    rigid_like_count = 0
    merge_pair_count = 0
    merged_link_ids: list[int] = []

    for link in elastic_links:
        n1 = int(link["node1"])
        n2 = int(link["node2"])
        lt = str(link.get("type", "")).upper()
        stiff = float(link.get("stiffness_indicator", 0.0))

        rigid_by_type = lt in {"RIGID", "SADDLE"}
        rigid_by_gen = lt == "GEN" and stiff >= float(rigid_stiffness_threshold) and (
            int(degree.get(n1, 0)) <= 1 or int(degree.get(n2, 0)) <= 1
        )
        is_rigid_like = bool(rigid_by_type or rigid_by_gen)
        link["is_rigid_like"] = is_rigid_like
        if not is_rigid_like:
            continue
        rigid_like_count += 1
        if dsu.union(n1, n2):
            merge_pair_count += 1
        merged_link_ids.append(int(link["id"]))

    map_old_to_new = {int(n): int(dsu.find(n)) for n in nodes}
    merged_node_count = sum(1 for k, v in map_old_to_new.items() if k != v)

    remapped_elements: list[dict] = []
    dropped_degenerate_elements = 0
    for e in elements:
        mapped: list[int] = []
        seen: set[int] = set()
        for nid in e.get("node_ids", []):
            nn = int(map_old_to_new.get(int(nid), int(nid)))
            if nn in seen:
                continue
            mapped.append(nn)
            seen.add(nn)
        if len(mapped) < 2:
            dropped_degenerate_elements += 1
            continue
        ee = dict(e)
        ee["node_ids"] = mapped
        remapped_elements.append(ee)

    used_nodes = {int(n) for e in remapped_elements for n in e.get("node_ids", [])}
    mapped_support_nodes = {int(map_old_to_new.get(n, n)) for n in support_nodes}
    keep_nodes = set(used_nodes)
    if not bool(drop_unreferenced_nodes):
        keep_nodes = {int(map_old_to_new.get(n, n)) for n in nodes}
    keep_nodes.update(mapped_support_nodes)

    new_nodes: dict[int, tuple[float, float, float]] = {}
    for nid in sorted(keep_nodes):
        src = int(nid)
        if src in nodes:
            new_nodes[src] = nodes[src]
            continue
        # fallback: locate any original node that mapped to this representative.
        for old, new in map_old_to_new.items():
            if int(new) == src and int(old) in nodes:
                new_nodes[src] = nodes[int(old)]
                break

    stats = {
        "elastic_link_count": int(len(elastic_links)),
        "rigid_like_link_count": int(rigid_like_count),
        "merge_pair_count": int(merge_pair_count),
        "merged_link_ids_head": merged_link_ids[:64],
        "merged_node_count": int(merged_node_count),
        "dropped_degenerate_elements": int(dropped_degenerate_elements),
        "node_count_pre": int(len(nodes)),
        "node_count_post": int(len(new_nodes)),
        "element_count_pre": int(len(elements)),
        "element_count_post": int(len(remapped_elements)),
        "dummy_node_removed_count": int(max(0, len(nodes) - len(new_nodes))),
        "support_node_count": int(len(support_nodes)),
        "support_node_count_mapped": int(len(mapped_support_nodes)),
    }
    return new_nodes, remapped_elements, stats


def _extract_edges(elements: list[dict]) -> list[tuple[int, int]]:
    edges: set[tuple[int, int]] = set()
    for elem in elements:
        nids = [int(v) for v in elem.get("node_ids", [])]
        if len(nids) == 2:
            a, b = nids
            if a != b:
                edges.add((a, b) if a < b else (b, a))
            continue
        for i in range(len(nids)):
            a = nids[i]
            b = nids[(i + 1) % len(nids)]
            if a == b:
                continue
            edges.add((a, b) if a < b else (b, a))
    return sorted(edges)


def _make_npz(npz_out: Path, nodes: dict[int, tuple[float, float, float]], elements: list[dict], edges: list[tuple[int, int]]) -> dict[str, int]:
    node_ids = sorted(nodes.keys())
    n = len(node_ids)
    idx = {nid: i for i, nid in enumerate(node_ids)}

    node_xyz = np.zeros((n, 3), dtype=np.float64)
    for i, nid in enumerate(node_ids):
        node_xyz[i, :] = np.asarray(nodes[nid], dtype=np.float64)

    edge_index = np.zeros((2, len(edges) * 2), dtype=np.int64)
    for i, (a, b) in enumerate(edges):
        ia = idx[int(a)]
        ib = idx[int(b)]
        edge_index[:, 2 * i] = np.asarray([ia, ib], dtype=np.int64)
        edge_index[:, 2 * i + 1] = np.asarray([ib, ia], dtype=np.int64)

    elem_ids = np.asarray([int(e["id"]) for e in elements], dtype=np.int64)
    fam_code = {"beam": 1, "shell": 2, "other": 0}
    elem_type_code = np.asarray([fam_code.get(str(e.get("family", "other")), 0) for e in elements], dtype=np.int32)
    elem_section_id = np.asarray([int(e.get("section_id", -1)) for e in elements], dtype=np.int64)
    elem_material_id = np.asarray([int(e.get("material_id", -1)) for e in elements], dtype=np.int64)
    elem_angle_deg = np.asarray([float(e.get("angle_deg", 0.0) or 0.0) for e in elements], dtype=np.float64)
    elem_lcaxis_code = np.asarray([int(e.get("lcaxis_code", 0) or 0) for e in elements], dtype=np.int32)

    conn_ptr = [0]
    conn_idx: list[int] = []
    for e in elements:
        for nid in e.get("node_ids", []):
            if int(nid) in idx:
                conn_idx.append(int(idx[int(nid)]))
        conn_ptr.append(len(conn_idx))
    elem_conn_ptr = np.asarray(conn_ptr, dtype=np.int64)
    elem_conn_idx = np.asarray(conn_idx, dtype=np.int64)

    npz_out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        npz_out,
        node_id=np.asarray(node_ids, dtype=np.int64),
        node_xyz=node_xyz,
        edge_index=edge_index,
        elem_id=elem_ids,
        elem_type_code=elem_type_code,
        elem_section_id=elem_section_id,
        elem_material_id=elem_material_id,
        elem_angle_deg=elem_angle_deg,
        elem_lcaxis_code=elem_lcaxis_code,
        elem_conn_ptr=elem_conn_ptr,
        elem_conn_idx=elem_conn_idx,
    )
    return {
        "node_count": int(n),
        "edge_count_directed": int(edge_index.shape[1]),
        "element_count": int(len(elements)),
        "elem_conn_index_count": int(elem_conn_idx.size),
        "elem_angle_nonzero_count": int(np.count_nonzero(np.abs(elem_angle_deg) > 1.0e-12)),
        "elem_angle_max_abs_deg": float(np.max(np.abs(elem_angle_deg))) if elem_angle_deg.size else 0.0,
        "elem_lcaxis_nonzero_count": int(np.count_nonzero(elem_lcaxis_code != 0)),
    }


def _write_edge_list_json(edge_out: Path, nodes: dict[int, tuple[float, float, float]], edges: list[tuple[int, int]]) -> dict[str, int]:
    node_ids = sorted(nodes.keys())
    idx = {int(nid): i for i, nid in enumerate(node_ids)}
    mapped_edges: list[list[int]] = []
    for a, b in edges:
        ia = idx.get(int(a))
        ib = idx.get(int(b))
        if ia is None or ib is None or ia == ib:
            continue
        mapped_edges.append([int(ia), int(ib)])

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-midas-mgt-edge-list",
        "source_family": "midas_mgt",
        "node_count": int(len(node_ids)),
        "edge_count_undirected": int(len(mapped_edges)),
        "edges": mapped_edges,
        "node_id_sample_head": [int(v) for v in node_ids[:32]],
    }
    edge_out.parent.mkdir(parents=True, exist_ok=True)
    edge_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "node_count": int(len(node_ids)),
        "edge_count_undirected": int(len(mapped_edges)),
    }


def main() -> None:
    logger = get_logger("phase1.parse_midas_mgt_to_json_npz")
    p = argparse.ArgumentParser()
    p.add_argument("--mgt", required=True)
    p.add_argument("--json-out", default="implementation/phase1/open_data/midas/midas_model.json")
    p.add_argument("--npz-out", default="implementation/phase1/open_data/midas/midas_graph.npz")
    p.add_argument("--report-out", default="implementation/phase1/midas_mgt_conversion_report.json")
    p.add_argument("--edge-list-out", default="")
    p.add_argument("--forbid-synthetic-source", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--require-shell-beam-mix", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--min-nodes", type=int, default=8)
    p.add_argument("--min-elements", type=int, default=4)
    p.add_argument("--resolve-rigid-links", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--rigid-stiffness-threshold", type=float, default=1.0e5)
    p.add_argument("--drop-unreferenced-nodes", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--strict-unknown-sections", action=argparse.BooleanOptionalAction, default=False)
    p.add_argument("--max-element-skip-count", type=int, default=0)
    p.add_argument("--max-element-skip-ratio", type=float, default=0.0)
    args = p.parse_args()

    input_payload = {
        "mgt": str(args.mgt),
        "json_out": str(args.json_out),
        "npz_out": str(args.npz_out),
        "report_out": str(args.report_out),
        "edge_list_out": str(args.edge_list_out),
        "forbid_synthetic_source": bool(args.forbid_synthetic_source),
        "require_shell_beam_mix": bool(args.require_shell_beam_mix),
        "min_nodes": int(args.min_nodes),
        "min_elements": int(args.min_elements),
        "resolve_rigid_links": bool(args.resolve_rigid_links),
        "rigid_stiffness_threshold": float(args.rigid_stiffness_threshold),
        "drop_unreferenced_nodes": bool(args.drop_unreferenced_nodes),
        "strict_unknown_sections": bool(args.strict_unknown_sections),
        "max_element_skip_count": int(args.max_element_skip_count),
        "max_element_skip_ratio": float(args.max_element_skip_ratio),
    }

    report_out = Path(args.report_out)
    report_out.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate_input_contract(input_payload, INPUT_SCHEMA, label="phase1.parse_midas_mgt_to_json_npz")
        src = Path(args.mgt)
        if not src.exists():
            raise RuntimeError("ERR_FILE_MISSING")
        if bool(args.forbid_synthetic_source) and _SYNTHETIC_MARKER_RE.search(str(src)):
            raise RuntimeError("ERR_SYNTHETIC_SOURCE")

        sections, blocks, line_count = _parse_sections(src)
        raw_nodes = _parse_nodes(sections.get("NODE", []))
        raw_elems, element_parse_diag = _parse_elements(sections.get("ELEMENT", []), set(raw_nodes.keys()))
        mats = _parse_materials(sections.get("MATERIAL", []))
        secs = _parse_sections_table(sections.get("SECTION", []))
        constraint_info = _parse_constraint_rows(sections.get("CONSTRAINT", []), set(raw_nodes.keys()))
        elastic_links = _parse_elastic_links(sections.get("ELASTICLINK", []), set(raw_nodes.keys()))
        static_load_cases = _parse_static_load_cases(sections.get("STLDCASE", []))
        contextual_loads = _parse_contextual_load_blocks(
            blocks=blocks,
            node_ids=set(raw_nodes.keys()),
            element_ids={int(e["id"]) for e in raw_elems},
        )
        nodal_loads = list(contextual_loads.get("nodal_loads", []))
        nodal_masses = _parse_nodal_mass_rows(sections.get("NODALMASS", []), set(raw_nodes.keys()))
        selfweight_rows = list(contextual_loads.get("selfweight", []))
        loadcase_rows = _parse_loadcase_rows(sections.get("LOADCASE", []))
        loadcomb_rows = _parse_loadcomb_rows(sections.get("LOADCOMB", []))
        loadcomb_graph = _build_load_combination_graph(loadcomb_rows)
        beam_offsets = _parse_offset_rows(sections.get("OFFSET", []), {int(e["id"]) for e in raw_elems})
        pressure_loads = list(contextual_loads.get("pressure_loads", []))
        semantic_load_summary = _build_semantic_load_summary(
            static_load_cases=static_load_cases,
            nodal_loads=nodal_loads,
            selfweight_rows=selfweight_rows,
            pressure_loads=pressure_loads,
            load_combinations=loadcomb_rows,
        )
        member_rows = _parse_member_rows(sections.get("MEMBER", []), {int(e["id"]) for e in raw_elems})
        group_rows = _parse_group_rows(sections.get("GROUP", []))
        thickness_rows = _parse_grouped_metadata_rows(sections.get("THICKNESS", []), key_field="thickness_id")
        design_section_rows = _parse_grouped_metadata_rows(sections.get("DGN-SECT", []), key_field="section_id")
        section_color_rows = _parse_color_rows(sections.get("SECT-COLOR", []), key_name="section_id")
        section_scale_rows = _parse_scale_rows(sections.get("SECT-SCALE", []))
        section_productization = _derive_section_productization_metadata(
            sections=secs,
            elements=raw_elems,
            design_section_rows=design_section_rows,
            section_color_rows=section_color_rows,
            section_scale_rows=section_scale_rows,
        )
        design_material_rows = _parse_grouped_metadata_rows(sections.get("DGN-MATL", []), key_field="material_id")
        design_material_rebar_payload_rows = _parse_design_material_rebar_payloads(design_material_rows)
        material_color_rows = _parse_color_rows(sections.get("MATL-COLOR", []), key_name="material_id")
        boundary_group_rows = _parse_token_rows(sections.get("BNDR-GROUP", []))
        domain_element_rows = _parse_token_rows(sections.get("DOMAIN-ELEMENT", []))
        eigen_control_rows = _parse_token_rows(sections.get("EIGEN-CTRL", []))
        load_color_rows = _parse_token_rows(sections.get("LC-COLOR", []))
        load_pattern_productization = _derive_load_pattern_productization_metadata(
            static_load_cases=static_load_cases,
            loadcase_rows=loadcase_rows,
            load_combinations=loadcomb_rows,
            nodal_loads=nodal_loads,
            selfweight_rows=selfweight_rows,
            pressure_loads=pressure_loads,
            semantic_load_summary=semantic_load_summary,
            load_color_rows=load_color_rows,
        )
        load_combination_editor_seed = _derive_load_combination_editor_seed(
            load_combinations=loadcomb_rows,
            load_combination_graph=loadcomb_graph,
            load_pattern_library=load_pattern_productization,
            semantic_load_summary=semantic_load_summary,
        )
        length_rows = _parse_token_rows(sections.get("LENGTH", []))
        main_domain_rows = _parse_token_rows(sections.get("MAIN-DOMAIN", []))
        rebar_material_code_rows = _parse_token_rows(sections.get("REBAR-MATL-CODE", []))
        story_eccen_rows = _parse_token_rows(sections.get("STORY-ECCEN", []))
        structure_type_rows = _parse_token_rows(sections.get("STRUCTYPE", []))
        thickness_color_rows = _parse_token_rows(sections.get("THIK-COLOR", []))
        version_rows = _parse_token_rows(sections.get("VERSION", []))
        named_axis_refs = _derive_named_axis_refs_from_sections(sections)
        typed_section_rows = {
            "STLDCASE": len(static_load_cases),
            "LOADCASE": len(loadcase_rows),
            "LOADCOMB": len(loadcomb_rows),
            "USE-STLD": sum(1 for block in blocks if str(block.get("key", "")).strip().upper() == "USE-STLD"),
            "CONLOAD": len(nodal_loads),
            "NODALMASS": len(nodal_masses),
            "SELFWEIGHT": len(selfweight_rows),
            "OFFSET": len(beam_offsets),
            "PRESSURE": len(pressure_loads),
            "MEMBER": len(sections.get("MEMBER", [])),
            "GROUP": len(sections.get("GROUP", [])),
            "THICKNESS": len(sections.get("THICKNESS", [])),
            "DGN-SECT": len(sections.get("DGN-SECT", [])),
            "SECT-COLOR": len(sections.get("SECT-COLOR", [])),
            "SECT-SCALE": len(sections.get("SECT-SCALE", [])),
            "DGN-MATL": len(sections.get("DGN-MATL", [])),
            "MATL-COLOR": len(sections.get("MATL-COLOR", [])),
            "BNDR-GROUP": len(sections.get("BNDR-GROUP", [])),
            "DOMAIN-ELEMENT": len(sections.get("DOMAIN-ELEMENT", [])),
            "EIGEN-CTRL": len(sections.get("EIGEN-CTRL", [])),
            "LC-COLOR": len(sections.get("LC-COLOR", [])),
            "LENGTH": len(sections.get("LENGTH", [])),
            "MAIN-DOMAIN": len(sections.get("MAIN-DOMAIN", [])),
            "REBAR-MATL-CODE": len(sections.get("REBAR-MATL-CODE", [])),
            "STORY-ECCEN": len(sections.get("STORY-ECCEN", [])),
            "STRUCTYPE": len(sections.get("STRUCTYPE", [])),
            "THIK-COLOR": len(sections.get("THIK-COLOR", [])),
            "VERSION": len(sections.get("VERSION", [])),
        }
        parser_diagnostics = _collect_parser_diagnostics(
            sections=sections,
            node_rows=len(sections.get("NODE", [])),
            node_count=len(raw_nodes),
            element_rows=len(sections.get("ELEMENT", [])),
            element_count=len(raw_elems),
            material_rows=len(sections.get("MATERIAL", [])),
            material_count=len(mats),
            section_rows=len(sections.get("SECTION", [])),
            section_count=len(secs),
            constraint_rows=len(sections.get("CONSTRAINT", [])),
            elastic_link_rows=len(sections.get("ELASTICLINK", [])),
            typed_section_rows=typed_section_rows,
            element_parse_diag=element_parse_diag,
        )

        nodes = raw_nodes
        elems = raw_elems
        coarsening = {
            "applied": False,
            "elastic_link_count": int(len(elastic_links)),
            "rigid_like_link_count": 0,
            "merge_pair_count": 0,
            "merged_node_count": 0,
            "dummy_node_removed_count": 0,
            "dropped_degenerate_elements": 0,
            "support_node_count": int(constraint_info.get("support_node_count", 0)),
            "support_node_count_mapped": int(constraint_info.get("support_node_count", 0)),
            "node_count_pre": int(len(raw_nodes)),
            "node_count_post": int(len(raw_nodes)),
            "element_count_pre": int(len(raw_elems)),
            "element_count_post": int(len(raw_elems)),
        }

        if bool(args.resolve_rigid_links):
            nodes, elems, coarsening_stats = _resolve_rigid_links(
                nodes=raw_nodes,
                elements=raw_elems,
                elastic_links=elastic_links,
                support_nodes=set(int(v) for v in constraint_info.get("support_nodes", [])),
                rigid_stiffness_threshold=float(args.rigid_stiffness_threshold),
                drop_unreferenced_nodes=bool(args.drop_unreferenced_nodes),
            )
            coarsening = {"applied": True, **coarsening_stats}

        edges = _extract_edges(elems)
        beam_count = sum(1 for e in elems if str(e.get("family")) == "beam")
        shell_count = sum(1 for e in elems if str(e.get("family")) == "shell")
        shell_beam_mix_pass = bool(beam_count > 0 and shell_count > 0)

        element_rows_total = int(len(sections.get("ELEMENT", [])))
        element_rows_skipped = int((parser_diagnostics.get("row_parse") or {}).get("element_rows_skipped", 0))
        element_skip_ratio = float((parser_diagnostics.get("row_parse") or {}).get("element_skip_ratio", 0.0))
        checks = {
            "has_nodes": bool(len(nodes) >= int(args.min_nodes)),
            "has_elements": bool(len(elems) >= int(args.min_elements)),
            "shell_beam_mix_pass": bool(shell_beam_mix_pass),
            "synthetic_source_blocked": True,
            "strict_element_slot_parse": True,
            "rigid_link_resolution_applied": bool(coarsening.get("applied", False)),
            "dummy_node_removed": bool(int(coarsening.get("dummy_node_removed_count", 0)) > 0),
            "unknown_section_policy_pass": bool(
                (not bool(args.strict_unknown_sections))
                or int(parser_diagnostics.get("unknown_section_count", 0)) == 0
            ),
            "element_skip_budget_pass": bool(
                element_rows_skipped <= int(args.max_element_skip_count)
                and element_skip_ratio <= float(args.max_element_skip_ratio)
            ),
        }
        contract_pass = bool(
            checks["has_nodes"]
            and checks["has_elements"]
            and (checks["shell_beam_mix_pass"] or not bool(args.require_shell_beam_mix))
            and checks["unknown_section_policy_pass"]
            and checks["element_skip_budget_pass"]
        )

        if not checks["has_nodes"] or not checks["has_elements"]:
            reason_code = "ERR_PARSE_FAIL"
        elif bool(args.require_shell_beam_mix) and not checks["shell_beam_mix_pass"]:
            reason_code = "ERR_SHELL_BEAM_MIX"
        elif bool(args.strict_unknown_sections) and not checks["unknown_section_policy_pass"]:
            reason_code = "ERR_UNKNOWN_SECTION"
        elif not checks["element_skip_budget_pass"]:
            reason_code = "ERR_ELEMENT_SKIP_BUDGET"
        else:
            reason_code = "PASS"

        npz_summary = {
            "node_count": 0,
            "edge_count_directed": 0,
            "element_count": 0,
            "elem_conn_index_count": 0,
        }
        json_out = Path(args.json_out)
        npz_out = Path(args.npz_out)
        edge_list_summary = {
            "node_count": 0,
            "edge_count_undirected": 0,
        }
        if checks["has_nodes"] and checks["has_elements"]:
            json_out.parent.mkdir(parents=True, exist_ok=True)
            payload_model = {
                "schema_version": "1.0",
                "run_id": "phase1-midas-mgt-model",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": {
                    "path": str(src),
                    "sha256": _sha256(src),
                    "size_bytes": int(src.stat().st_size),
                    "format": "midas_mgt",
                    "source_family": "midas_mgt",
                },
                "parser": {
                    "line_count": int(line_count),
                    "section_counts": {k: int(len(v)) for k, v in sections.items()},
                    "strict_element_slot_parse": True,
                    "coarsening": coarsening,
                    "constraint_summary": constraint_info,
                    "diagnostics": parser_diagnostics,
                },
                "model": {
                    "nodes": [{"id": int(nid), "x": float(x), "y": float(y), "z": float(z)} for nid, (x, y, z) in sorted(nodes.items())],
                    "elements": elems,
                    "materials": mats,
                    "sections": secs,
                    "loads": {
                        "static_load_cases": static_load_cases,
                        "active_static_case_sequence": list(contextual_loads.get("active_static_case_sequence", [])),
                        "load_cases": loadcase_rows,
                        "load_combinations": loadcomb_rows,
                        "load_combination_graph": loadcomb_graph,
                        "semantic_load_summary": semantic_load_summary,
                        "selfweight": selfweight_rows,
                        "nodal_loads": nodal_loads,
                        "nodal_masses": nodal_masses,
                        "beam_offsets": beam_offsets,
                        "pressure_loads": pressure_loads,
                    },
                    "metadata": {
                        "members": member_rows,
                        "groups": group_rows,
                        "thickness": thickness_rows,
                        "design_sections": design_section_rows,
                        "section_colors": section_color_rows,
                        "section_scales": section_scale_rows,
                        "section_library": section_productization,
                        "load_pattern_library": load_pattern_productization,
                        "load_combination_editor_seed": load_combination_editor_seed,
                        "design_materials": design_material_rows,
                        "design_material_rebar_payloads": design_material_rebar_payload_rows,
                        "group_local_rebar_payloads": [],
                        "material_colors": material_color_rows,
                        "boundary_groups": boundary_group_rows,
                        "domain_elements": domain_element_rows,
                        "eigen_controls": eigen_control_rows,
                        "load_colors": load_color_rows,
                        "length_units": length_rows,
                        "main_domains": main_domain_rows,
                        "rebar_material_codes": rebar_material_code_rows,
                        "story_eccentricity": story_eccen_rows,
                        "structure_type": structure_type_rows,
                        "thickness_colors": thickness_color_rows,
                        "version": version_rows,
                        "named_axis_refs": named_axis_refs,
                    },
                    "load_cases_raw": sections.get("LOADCASE", []),
                    "load_combinations_raw": sections.get("LOADCOMB", []),
                },
                "topology_metrics": {
                    "node_count": int(len(nodes)),
                    "element_count": int(len(elems)),
                    "edge_count_undirected": int(len(edges)),
                    "beam_element_count": int(beam_count),
                    "shell_element_count": int(shell_count),
                    "node_count_pre_coarsening": int(coarsening.get("node_count_pre", len(nodes))),
                    "element_count_pre_coarsening": int(coarsening.get("element_count_pre", len(elems))),
                },
            }
            json_out.write_text(json.dumps(payload_model, indent=2), encoding="utf-8")
            npz_summary = _make_npz(npz_out, nodes, elems, edges)
            if str(args.edge_list_out).strip():
                edge_list_summary = _write_edge_list_json(Path(args.edge_list_out), nodes, edges)

        summary = {
            "schema_version": "1.1",
            "run_id": "phase1-midas-mgt-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "source_provenance": {
                "source_family": "midas_mgt",
                "path": str(src),
                "sha256": _sha256(src),
                "size_bytes": int(src.stat().st_size),
            },
            "metrics": {
                "line_count": int(line_count),
                "section_count": int(len(sections)),
                "node_count": int(len(nodes)),
                "element_count": int(len(elems)),
                "edge_count_undirected": int(len(edges)),
                "element_rows_total": int(element_rows_total),
                "element_rows_skipped": int(element_rows_skipped),
                "element_skip_ratio": float(element_skip_ratio),
                "beam_element_count": int(beam_count),
                "shell_element_count": int(shell_count),
                "node_count_pre_coarsening": int(coarsening.get("node_count_pre", len(nodes))),
                "element_count_pre_coarsening": int(coarsening.get("element_count_pre", len(elems))),
                "rigid_like_link_count": int(coarsening.get("rigid_like_link_count", 0)),
                "merged_node_count": int(coarsening.get("merged_node_count", 0)),
                "dummy_node_removed_count": int(coarsening.get("dummy_node_removed_count", 0)),
                "typed_section_count": int(parser_diagnostics.get("typed_section_count", 0)),
                "typed_row_total": int(parser_diagnostics.get("typed_row_total", 0)),
                "unknown_section_count": int(parser_diagnostics.get("unknown_section_count", 0)),
                "unknown_row_total": int(parser_diagnostics.get("unknown_row_total", 0)),
                "static_load_case_count": int(len(static_load_cases)),
                "load_case_row_count": int(len(loadcase_rows)),
                "load_combination_row_count": int(len(loadcomb_rows)),
                "load_combination_graph_node_count": int(loadcomb_graph.get("node_count", 0)),
                "load_combination_graph_edge_count": int(loadcomb_graph.get("edge_count", 0)),
                "use_stld_block_count": int(sum(1 for block in blocks if str(block.get("key", "")).strip().upper() == "USE-STLD")),
                "active_static_case_sequence_count": int(len(contextual_loads.get("active_static_case_sequence", []))),
                "nodal_load_row_count": int(len(nodal_loads)),
                "nodal_mass_row_count": int(len(nodal_masses)),
                "selfweight_row_count": int(len(selfweight_rows)),
                "offset_row_count": int(len(beam_offsets)),
                "pressure_load_row_count": int(len(pressure_loads)),
                "semantic_load_case_count": int(semantic_load_summary.get("case_count", 0)),
                "semantic_load_combination_count": int(semantic_load_summary.get("combination_count", 0)),
                "load_pattern_count": int((load_pattern_productization.get("summary") or {}).get("pattern_count", 0)),
                "load_pattern_primitive_count": int((load_pattern_productization.get("summary") or {}).get("primitive_count", 0)),
                "load_pattern_combination_count": int(((load_pattern_productization.get("combination_summary") or {}).get("combination_count", 0))),
                "load_combination_editor_combo_count": int((load_combination_editor_seed.get("summary") or {}).get("combination_count", 0)),
                "load_combination_editor_case_count": int((load_combination_editor_seed.get("summary") or {}).get("case_count", 0)),
                "load_combination_editor_edge_count": int((load_combination_editor_seed.get("summary") or {}).get("graph_edge_count", 0)),
                "bound_nodal_load_row_count": int(semantic_load_summary.get("bound_nodal_load_row_count", 0)),
                "bound_selfweight_row_count": int(semantic_load_summary.get("bound_selfweight_row_count", 0)),
                "bound_pressure_row_count": int(semantic_load_summary.get("bound_pressure_row_count", 0)),
                "unbound_nodal_load_row_count": int(semantic_load_summary.get("unbound_nodal_load_row_count", 0)),
                "unbound_selfweight_row_count": int(semantic_load_summary.get("unbound_selfweight_row_count", 0)),
                "unbound_pressure_row_count": int(semantic_load_summary.get("unbound_pressure_row_count", 0)),
                "body_load_pending_case_count": int(semantic_load_summary.get("body_load_pending_case_count", 0)),
                "surface_load_pending_case_count": int(semantic_load_summary.get("surface_load_pending_case_count", 0)),
                "member_row_count": int(len(member_rows)),
                "group_row_count": int(len(group_rows)),
                "thickness_row_count": int(len(thickness_rows)),
                "design_section_row_count": int(len(design_section_rows)),
                "section_color_row_count": int(len(section_color_rows)),
                "section_scale_row_count": int(len(section_scale_rows)),
                "section_usage_summary_count": int(len(section_productization.get("usage_summary", []) or [])),
                "used_section_count": int((section_productization.get("summary") or {}).get("used_section_count", 0)),
                "unused_section_count": int((section_productization.get("summary") or {}).get("unused_section_count", 0)),
                "derived_section_template_count": int((section_productization.get("summary") or {}).get("derived_template_count", 0)),
                "derived_load_pattern_count": int((load_pattern_productization.get("summary") or {}).get("pattern_count", 0)),
                "derived_load_pattern_primitive_count": int((load_pattern_productization.get("summary") or {}).get("primitive_count", 0)),
                "design_material_row_count": int(len(design_material_rows)),
                "design_material_rebar_payload_row_count": int(len(design_material_rebar_payload_rows)),
                "design_material_rebar_payload_available_count": int(
                    sum(1 for row in design_material_rebar_payload_rows if bool(row.get("payload_present", False)))
                ),
                "group_local_rebar_payload_row_count": 0,
            },
            "coarsening": coarsening,
            "parser_diagnostics": parser_diagnostics,
            "section_productization": section_productization.get("summary", {}),
            "load_pattern_productization": {
                "pattern_count": int((load_pattern_productization.get("summary") or {}).get("pattern_count", 0)),
                "primitive_count": int((load_pattern_productization.get("summary") or {}).get("primitive_count", 0)),
                "combination_count": int(((load_pattern_productization.get("combination_summary") or {}).get("combination_count", 0))),
                "primitive_kind_counts": dict((((load_pattern_productization.get("pattern_summary") or {}).get("primitive_kind_counts")) or {})),
            },
            "load_combination_editor_seed": {
                "combination_count": int((load_combination_editor_seed.get("summary") or {}).get("combination_count", 0)),
                "case_count": int((load_combination_editor_seed.get("summary") or {}).get("case_count", 0)),
                "graph_edge_count": int((load_combination_editor_seed.get("summary") or {}).get("graph_edge_count", 0)),
                "stage_count": int((load_combination_editor_seed.get("summary") or {}).get("stage_count", 0)),
            },
            "checks": checks,
            "artifacts": {
                "json_out": str(args.json_out),
                "npz_out": str(args.npz_out),
                "edge_list_out": str(args.edge_list_out),
                "edge_list_summary": edge_list_summary,
                "npz_summary": npz_summary,
            },
            "contract_pass": bool(contract_pass),
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
        }
        report_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        log_event(logger, 20, "mgt_parser.completed", contract_pass=bool(contract_pass), reason_code=reason_code)
        print(f"Wrote MIDAS MGT conversion report: {report_out}")
        if not contract_pass:
            raise SystemExit(1)
    except (InputContractError, ValueError) as exc:
        payload = {
            "schema_version": "1.1",
            "run_id": "phase1-midas-mgt-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": "ERR_INVALID_INPUT",
            "reason": f"{REASONS['ERR_INVALID_INPUT']}: {exc}",
        }
        report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, 40, "mgt_parser.invalid_input", error=str(exc))
        print(f"Wrote MIDAS MGT conversion report: {report_out}")
        raise SystemExit(1)
    except RuntimeError as exc:
        code = str(exc)
        if code not in REASONS:
            code = "ERR_PARSE_FAIL"
        payload = {
            "schema_version": "1.1",
            "run_id": "phase1-midas-mgt-converter",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "inputs": input_payload,
            "contract_pass": False,
            "reason_code": code,
            "reason": REASONS[code],
        }
        report_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        log_event(logger, 40, "mgt_parser.runtime_error", reason_code=code)
        print(f"Wrote MIDAS MGT conversion report: {report_out}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
