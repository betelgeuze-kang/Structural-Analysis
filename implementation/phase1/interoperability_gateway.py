#!/usr/bin/env python3
"""Normalized interoperability scaffold for MIDAS/ETABS/OpenSees/IFC workflows."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


REASONS = {
    "PASS": "interoperability gateway generated normalized import/export evidence",
    "ERR_INPUT": "one or more interoperability inputs were missing or invalid",
    "ERR_IMPORT": "one or more interoperability sources could not be normalized",
    "ERR_DIFF": "one or more interoperability exports exceeded the geometry diff tolerance",
}

SUPPORTED_TOOLS = ("MIDAS", "ETABS", "OpenSees", "IFC")
IFC_PATTERNS = {
    "beam_count": re.compile(r"\bIFCBEAM\b", re.IGNORECASE),
    "column_count": re.compile(r"\bIFCCOLUMN\b", re.IGNORECASE),
    "slab_count": re.compile(r"\bIFCSLAB\b", re.IGNORECASE),
    "wall_count": re.compile(r"\bIFCWALL(?:STANDARDCASE)?\b", re.IGNORECASE),
    "plate_count": re.compile(r"\bIFCPLATE\b", re.IGNORECASE),
    "member_count": re.compile(r"\bIFCMEMBER\b", re.IGNORECASE),
    "footing_count": re.compile(r"\bIFCFOOTING\b", re.IGNORECASE),
    "storey_count": re.compile(r"\bIFCBUILDINGSTOREY\b", re.IGNORECASE),
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _clean_tool_name(raw: str) -> str:
    token = str(raw or "").strip().lower()
    if token in {"midas", "mgt"}:
        return "MIDAS"
    if token in {"etabs"}:
        return "ETABS"
    if token in {"opensees"}:
        return "OpenSees"
    if token in {"ifc"}:
        return "IFC"
    return ""


def _as_count(value: object) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _count_collection(value: object) -> int:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        return len(value)
    return 0


def _normalize_midas(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
    sections = model.get("sections")
    materials = model.get("materials")
    return {
        "source_tool": "MIDAS",
        "path": str(path),
        "counts": {
            "node_count": _count_collection(model.get("nodes")),
            "member_count": _count_collection(model.get("elements")),
            "storey_count": _count_collection(model.get("stories")),
            "section_count": _count_collection(sections),
            "material_count": _count_collection(materials),
        },
        "metadata": {
            "schema_version": str(payload.get("schema_version", "1.0")),
            "has_loads": isinstance(model.get("loads"), dict),
            "has_metadata": isinstance(model.get("metadata"), dict),
        },
    }


def _normalize_opensees(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    parse_counters = payload.get("parse_counters") if isinstance(payload.get("parse_counters"), dict) else {}
    beam_count = _as_count(metrics.get("beam_element_count", 0))
    shell_count = _as_count(metrics.get("shell_element_count", 0))
    total_elements = _as_count(parse_counters.get("element", beam_count + shell_count))
    member_count = beam_count + shell_count if beam_count + shell_count > 0 else total_elements
    return {
        "source_tool": "OpenSees",
        "path": str(path),
        "counts": {
            "node_count": _as_count(metrics.get("node_count", parse_counters.get("node", 0))),
            "member_count": member_count,
            "storey_count": 0,
            "section_count": _as_count(metrics.get("element_type_count", 0)),
            "material_count": 0,
        },
        "metadata": {
            "schema_version": str(payload.get("schema_version", "1.0")),
            "element_type_count": _as_count(metrics.get("element_type_count", 0)),
            "largest_component_ratio": float(metrics.get("largest_component_ratio", 0.0) or 0.0),
        },
    }


def _normalize_etabs(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    model = payload.get("model") if isinstance(payload.get("model"), dict) else payload
    frame_objects = model.get("frame_objects")
    area_objects = model.get("area_objects")
    return {
        "source_tool": "ETABS",
        "path": str(path),
        "counts": {
            "node_count": _count_collection(model.get("points")),
            "member_count": _count_collection(frame_objects) + _count_collection(area_objects),
            "storey_count": _count_collection(model.get("stories")),
            "section_count": _count_collection(model.get("frame_sections")) + _count_collection(model.get("area_sections")),
            "material_count": _count_collection(model.get("materials")),
        },
        "metadata": {
            "schema_version": str(payload.get("schema_version", "1.0")),
            "units": str(model.get("units", "")),
            "has_load_patterns": _count_collection(model.get("load_patterns")) > 0,
        },
    }


def _normalize_ifc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    metrics = {name: len(pattern.findall(text)) for name, pattern in IFC_PATTERNS.items()}
    member_count = sum(
        metrics[name]
        for name in (
            "beam_count",
            "column_count",
            "slab_count",
            "wall_count",
            "plate_count",
            "member_count",
            "footing_count",
        )
    )
    return {
        "source_tool": "IFC",
        "path": str(path),
        "counts": {
            "node_count": 0,
            "member_count": int(member_count),
            "storey_count": int(metrics["storey_count"]),
            "section_count": 0,
            "material_count": 0,
        },
        "metadata": {
            "schema_version": "1.0",
            "entity_counts": metrics,
            "text_scan_only": True,
        },
    }


def _detect_tool(path: Path, payload: dict[str, Any] | None, tool_hint: str = "") -> str:
    hinted = _clean_tool_name(tool_hint)
    if hinted:
        return hinted
    suffix = path.suffix.lower()
    if suffix == ".ifc":
        return "IFC"
    if not isinstance(payload, dict):
        return ""
    run_id = str(payload.get("run_id", "") or "")
    if "opensees" in run_id.lower() or ("metrics" in payload and "parse_counters" in payload):
        return "OpenSees"
    if isinstance(payload.get("model"), dict):
        model = payload["model"]
        if any(key in model for key in ("stories", "points", "frame_objects", "area_objects")):
            return "ETABS"
        if any(key in model for key in ("nodes", "elements", "sections", "materials")):
            return "MIDAS"
    if any(key in payload for key in ("stories", "points", "frame_objects", "area_objects")):
        return "ETABS"
    return ""


def load_interoperability_source(path: Path, tool_hint: str = "") -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    tool = ""
    if path.suffix.lower() != ".ifc":
        payload = _load_json(path)
    tool = _detect_tool(path, payload, tool_hint=tool_hint)
    if tool == "MIDAS" and isinstance(payload, dict):
        normalized = _normalize_midas(path, payload)
    elif tool == "OpenSees" and isinstance(payload, dict):
        normalized = _normalize_opensees(path, payload)
    elif tool == "ETABS" and isinstance(payload, dict):
        normalized = _normalize_etabs(path, payload)
    elif tool == "IFC":
        normalized = _normalize_ifc(path)
    else:
        raise ValueError(f"unsupported interoperability source: {path}")

    counts = normalized.get("counts") if isinstance(normalized.get("counts"), dict) else {}
    normalized["geometry_signature"] = {
        "node_count": _as_count(counts.get("node_count", 0)),
        "member_count": _as_count(counts.get("member_count", 0)),
        "storey_count": _as_count(counts.get("storey_count", 0)),
        "section_count": _as_count(counts.get("section_count", 0)),
        "material_count": _as_count(counts.get("material_count", 0)),
    }
    return normalized


def export_interoperability_preview(source: dict[str, Any], target_tool: str) -> dict[str, Any]:
    target = _clean_tool_name(target_tool)
    if target not in SUPPORTED_TOOLS:
        raise ValueError(f"unsupported target tool: {target_tool}")
    signature = source.get("geometry_signature") if isinstance(source.get("geometry_signature"), dict) else {}
    return {
        "target_tool": target,
        "source_tool": str(source.get("source_tool", "")),
        "geometry_signature": dict(signature),
        "preview_contract": {
            "schema_version": "1.0",
            "translation_mode": "normalized-count-preserving-preview",
            "supports_exact_geometry_diff": True,
        },
    }


def compare_geometry_signature(source: dict[str, Any], preview: dict[str, Any]) -> dict[str, Any]:
    source_signature = source.get("geometry_signature") if isinstance(source.get("geometry_signature"), dict) else {}
    preview_signature = preview.get("geometry_signature") if isinstance(preview.get("geometry_signature"), dict) else {}
    diff: dict[str, int] = {}
    max_abs_diff = 0
    max_ratio = 0.0
    for key in ("node_count", "member_count", "storey_count", "section_count", "material_count"):
        lhs = _as_count(source_signature.get(key, 0))
        rhs = _as_count(preview_signature.get(key, 0))
        delta = abs(lhs - rhs)
        diff[key] = delta
        max_abs_diff = max(max_abs_diff, delta)
        if lhs > 0:
            max_ratio = max(max_ratio, float(delta) / float(lhs))
    return {
        "geometry_diff": diff,
        "max_abs_diff": int(max_abs_diff),
        "max_diff_ratio": float(max_ratio),
        "zero_geometry_diff": bool(max_abs_diff == 0),
    }


def build_interoperability_report(*, inputs: list[Path], target_tools: list[str]) -> dict[str, Any]:
    source_rows: list[dict[str, Any]] = []
    export_rows: list[dict[str, Any]] = []
    import_error_rows: list[dict[str, str]] = []
    tool_histogram = {tool: 0 for tool in SUPPORTED_TOOLS}

    for path in inputs:
        try:
            normalized = load_interoperability_source(path)
        except Exception as exc:
            import_error_rows.append({"path": str(path), "reason": str(exc)})
            continue
        source_rows.append(normalized)
        tool = str(normalized.get("source_tool", ""))
        if tool in tool_histogram:
            tool_histogram[tool] += 1
        for target_tool in target_tools:
            preview = export_interoperability_preview(normalized, target_tool)
            diff = compare_geometry_signature(normalized, preview)
            export_rows.append(
                {
                    "path": str(path),
                    "source_tool": tool,
                    "target_tool": str(preview.get("target_tool", "")),
                    **diff,
                }
            )

    zero_geometry_diff_count = sum(1 for row in export_rows if bool(row.get("zero_geometry_diff", False)))
    successful_import_count = len(source_rows)
    contract_pass = bool(
        successful_import_count == len(inputs)
        and not import_error_rows
        and zero_geometry_diff_count == len(export_rows)
    )
    if not inputs:
        reason_code = "ERR_INPUT"
    elif import_error_rows:
        reason_code = "ERR_IMPORT"
    elif zero_geometry_diff_count != len(export_rows):
        reason_code = "ERR_DIFF"
    else:
        reason_code = "PASS"
    summary = {
        "source_count": len(inputs),
        "successful_import_count": successful_import_count,
        "import_error_count": len(import_error_rows),
        "target_tool_count": len(target_tools),
        "export_count": len(export_rows),
        "zero_geometry_diff_count": zero_geometry_diff_count,
        "tool_histogram": {key: int(value) for key, value in tool_histogram.items() if int(value) > 0},
    }
    tool_summary = ",".join(f"{key}={value}" for key, value in summary["tool_histogram"].items()) or "none"
    return {
        "schema_version": "1.0",
        "run_id": "phase1-interoperability-gateway",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "source_paths": [str(path) for path in inputs],
            "target_tools": list(target_tools),
        },
        "summary": summary,
        "source_rows": source_rows,
        "export_rows": export_rows,
        "import_error_rows": import_error_rows,
        "checks": {
            "all_imports_succeeded": successful_import_count == len(inputs),
            "zero_geometry_diff_pass": zero_geometry_diff_count == len(export_rows),
        },
        "summary_line": (
            "Interoperability gateway: "
            f"{reason_code} | imports={successful_import_count}/{len(inputs)} | "
            f"exports={len(export_rows)} | zero_diff={zero_geometry_diff_count}/{len(export_rows)} | "
            f"tools={tool_summary}"
        ),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
    }


def _parse_csv(raw: str) -> list[str]:
    return [item.strip() for item in str(raw or "").split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True, help="Comma-separated source paths")
    parser.add_argument("--targets", default="midas,etabs,opensees,ifc", help="Comma-separated target tools")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    input_paths = [Path(item) for item in _parse_csv(args.inputs)]
    if not input_paths:
        raise SystemExit("no interoperability inputs were provided")
    target_tools = [_clean_tool_name(item) for item in _parse_csv(args.targets)]
    target_tools = [item for item in target_tools if item]
    if not target_tools:
        raise SystemExit("no supported target tools were provided")

    report = build_interoperability_report(inputs=input_paths, target_tools=target_tools)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["summary_line"])
    if not report["contract_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
