#!/usr/bin/env python3
"""Summarize the public PEER blind-prediction input bundle into a structured report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile


DEFAULT_ROOT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_SOURCE_MANIFEST = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json")
DEFAULT_OUT = Path("implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json")
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _xlsx_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    shared: list[str] = []
    for node in root.findall(f"{_NS}si"):
        shared.append("".join(text_node.text or "" for text_node in node.iter(f"{_NS}t")))
    return shared


def _xlsx_sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rel_map = {
        str(row.attrib.get("Id", "")): str(row.attrib.get("Target", ""))
        for row in rels
    }
    out: list[tuple[str, str]] = []
    sheets = workbook.find(f"{_NS}sheets")
    if sheets is None:
        return out
    for sheet in sheets:
        name = str(sheet.attrib.get("name", "") or "")
        rel_id = str(sheet.attrib.get(f"{_REL_NS}id", "") or "")
        target = rel_map.get(rel_id, "")
        if name and target:
            out.append((name, f"xl/{target}" if not target.startswith("xl/") else target))
    return out


def _xlsx_rows(zf: zipfile.ZipFile, target: str, shared: list[str], max_rows: int = 12) -> list[list[str]]:
    root = ET.fromstring(zf.read(target))
    rows: list[list[str]] = []
    for row in root.findall(f".//{_NS}row")[:max_rows]:
        values: list[str] = []
        for cell in row.findall(f"{_NS}c"):
            cell_type = str(cell.attrib.get("t", "") or "")
            value_node = cell.find(f"{_NS}v")
            value = str(value_node.text or "") if value_node is not None and value_node.text is not None else ""
            if cell_type == "s" and value:
                try:
                    value = shared[int(value)]
                except Exception:
                    pass
            values.append(value)
        rows.append(values)
    return rows


def _summarize_gm_workbook(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        shared = _xlsx_shared_strings(zf)
        sheet_targets = _xlsx_sheet_targets(zf)
        sheet_samples = {
            name: _xlsx_rows(zf, target, shared)
            for name, target in sheet_targets
        }
    gm_sequence_rows = sheet_samples.get("GM_Sequence", [])
    gms_rows = sheet_samples.get("GMs", [])
    spectra_rows = sheet_samples.get("Respspectra", [])
    gm_names = [token for token in (gms_rows[0] if gms_rows else []) if token]
    sequence_labels = [row[1] for row in gm_sequence_rows if len(row) >= 2 and row[1]]
    return {
        "path": str(path),
        "sheet_names": [name for name, _ in sheet_targets],
        "sequence_step_count": len(sequence_labels),
        "sequence_labels": sequence_labels[:12],
        "gm_name_count": len(gm_names),
        "gm_names": gm_names[:16],
        "sheet_samples": {
            "GM_Sequence": gm_sequence_rows[:8],
            "GMs": gms_rows[:6],
            "Respspectra": spectra_rows[:6],
        },
    }


def _summarize_materials_bundle(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        bundle_files = sorted(zf.namelist())
        workbook_name = next((name for name in bundle_files if name.lower().endswith(".xlsx")), "")
        workbook_summary: dict[str, Any] = {}
        if workbook_name:
            with zf.open(workbook_name) as handle:
                raw = handle.read()
            temp_path = path.parent / ".__peer_materials_tmp__.xlsx"
            temp_path.write_bytes(raw)
            try:
                with zipfile.ZipFile(temp_path) as wzf:
                    shared = _xlsx_shared_strings(wzf)
                    sheet_targets = _xlsx_sheet_targets(wzf)
                    sheet_samples = {
                        name: _xlsx_rows(wzf, target, shared)
                        for name, target in sheet_targets
                    }
                workbook_summary = {
                    "sheet_names": [name for name, _ in sheet_targets],
                    "sheet_samples": {name: rows[:6] for name, rows in sheet_samples.items()},
                }
            finally:
                if temp_path.exists():
                    temp_path.unlink()
    return {
        "path": str(path),
        "bundle_files": bundle_files,
        "materials_workbook": workbook_summary,
        "grout_datasheet_present": any(name.lower().endswith("grout_datasheet.pdf") for name in bundle_files),
    }


def build_report(root: Path, source_manifest: dict[str, Any]) -> dict[str, Any]:
    gm_path = root / "GMs.xlsx"
    materials_path = root / "Materials.zip"
    geometry_docs = sorted(
        path.name
        for path in root.glob("*.pdf")
        if path.name not in {"news_e-defense_blind_analysis_2009-article.pdf"}
    )
    expected_groups = source_manifest.get("expected_groups") if isinstance(source_manifest.get("expected_groups"), dict) else {}
    measured_group = expected_groups.get("measured_response") if isinstance(expected_groups.get("measured_response"), dict) else {}
    group_state = {
        "geometry_model": bool((expected_groups.get("geometry_model") or {}).get("present", False)),
        "material_properties": bool((expected_groups.get("material_properties") or {}).get("present", False)),
        "excitation_history": bool((expected_groups.get("excitation_history") or {}).get("present", False)),
        "measured_response": bool(measured_group.get("present", False)),
    }
    contract_pass = bool(group_state["geometry_model"] and group_state["material_properties"] and group_state["excitation_history"])
    measured_response_pending = not group_state["measured_response"]
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_root": str(root),
        "contract_pass": contract_pass,
        "reason_code": "PASS_INPUT_READY_MEASURED_PENDING" if contract_pass and measured_response_pending else ("PASS" if contract_pass else "ERR_PUBLIC_INPUT_BUNDLE_INCOMPLETE"),
        "reason": (
            "Public PEER blind-prediction input bundle is structured and ready; measured response remains a separate landing task."
            if contract_pass and measured_response_pending
            else "Public PEER blind-prediction input bundle is structured."
            if contract_pass
            else "Public PEER blind-prediction input bundle is missing geometry/material/excitation assets."
        ),
        "summary_line": (
            f"PEER blind input bundle: {'PASS' if contract_pass else 'CHECK'} | "
            f"geometry_docs={len(geometry_docs)} | materials={'yes' if materials_path.exists() else 'no'} | "
            f"gm_workbook={'yes' if gm_path.exists() else 'no'} | "
            f"measured_response={'pending' if measured_response_pending else 'ready'}"
        ),
        "summary": {
            "geometry_doc_count": len(geometry_docs),
            "material_bundle_present": bool(materials_path.exists()),
            "gm_workbook_present": bool(gm_path.exists()),
            "measured_response_pending": measured_response_pending,
        },
        "group_state": group_state,
        "geometry_docs": geometry_docs,
        "gm_workbook_summary": _summarize_gm_workbook(gm_path) if gm_path.exists() else {},
        "materials_bundle_summary": _summarize_materials_bundle(materials_path) if materials_path.exists() else {},
        "source_manifest_summary": source_manifest.get("summary") if isinstance(source_manifest.get("summary"), dict) else {},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_report(Path(args.root), _load_json(Path(args.source_manifest)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER blind public input bundle report: {out_path}")


if __name__ == "__main__":
    main()
