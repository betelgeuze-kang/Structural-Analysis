#!/usr/bin/env python3
"""Normalize external solver-verified panel-zone rows into a canonical bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


SOURCE_KIND_CONFIG = {
    "panel_zone_joint_geometry_3d": {
        "required_fields": ("member_id", "joint_id"),
        "upstream_tier": "solver_verified_3d_source",
    },
    "panel_zone_rebar_anchorage_3d": {
        "required_fields": ("member_id", "available_anchorage_length_mm", "required_anchorage_length_mm"),
        "upstream_tier": "solver_verified_3d_source",
    },
    "panel_zone_clash_verification_3d": {
        "required_fields": ("member_id", "clash_count", "clearance_mm"),
        "upstream_tier": "solver_verified_3d_source",
    },
}

SOURCE_ROW_KEYS = (
    "rows",
    "source_rows",
    "verified_rows",
    "candidate_rows",
    "joint_rows",
    "anchorage_rows",
    "clash_rows",
    "interference_rows",
)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_member_mapping_sidecar(path: Path) -> dict[str, Any]:
    payload = _load_json(path) if path.exists() else {}
    mapping_rows: list[dict[str, str]] = []
    member_map: dict[str, str] = {}
    if isinstance(payload, dict):
        raw_map = payload.get("member_map")
        if isinstance(raw_map, dict):
            for source_member_id, candidate_member_id in raw_map.items():
                source_key = str(source_member_id or "").strip()
                candidate_value = str(candidate_member_id or "").strip()
                if not source_key or not candidate_value:
                    continue
                member_map[source_key] = candidate_value
                mapping_rows.append(
                    {
                        "source_member_id": source_key,
                        "candidate_member_id": candidate_value,
                    }
                )
        raw_rows = payload.get("rows")
        if isinstance(raw_rows, list):
            for row in raw_rows:
                if not isinstance(row, dict):
                    continue
                source_member_id = str(
                    row.get("source_member_id")
                    or row.get("solver_member_id")
                    or row.get("member_id")
                    or ""
                ).strip()
                candidate_member_id = str(
                    row.get("candidate_member_id")
                    or row.get("mapped_member_id")
                    or row.get("active_member_id")
                    or ""
                ).strip()
                if not source_member_id or not candidate_member_id:
                    continue
                if source_member_id not in member_map:
                    member_map[source_member_id] = candidate_member_id
                    mapping_rows.append(
                        {
                            "source_member_id": source_member_id,
                            "candidate_member_id": candidate_member_id,
                        }
                    )
    return {
        "present": bool(path.exists() and member_map),
        "path": str(path),
        "mapping_mode": str(payload.get("mapping_mode", "") or "explicit_member_id_map").strip() if isinstance(payload, dict) else "explicit_member_id_map",
        "row_count": int(len(mapping_rows)),
        "member_map": member_map,
        "rows": mapping_rows,
    }


def _field_present(row: dict[str, Any], key: str) -> bool:
    if key not in row:
        return False
    value = row.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in SOURCE_ROW_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, dict):
        for key in SOURCE_ROW_KEYS:
            rows = artifacts.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_source(
    *,
    path: Path,
    source_kind: str,
    producer_backend: str,
    source_bundle_mode: str,
    source_origin_class: str,
    evidence_model: str,
    rebar_delivery_mode: str,
) -> tuple[dict[str, Any], list[str]]:
    payload = _load_json(path) if path.exists() else {}
    raw_rows = _extract_rows(payload)
    required_fields = SOURCE_KIND_CONFIG[source_kind]["required_fields"]
    valid_rows: list[dict[str, Any]] = []
    invalid_member_ids: list[str] = []
    for row in raw_rows:
        member_id = str(row.get("member_id", "") or "").strip()
        if member_id and all(_field_present(row, key) for key in required_fields):
            valid_rows.append(row)
        else:
            invalid_member_ids.append(member_id or "<missing-member-id>")
    upstream_tier = str(SOURCE_KIND_CONFIG[source_kind]["upstream_tier"])
    return (
        {
            "contract_pass": bool(valid_rows),
            "source_kind": source_kind,
            "verification_tier": upstream_tier,
            "summary": {
                "source_kind": source_kind,
                "producer_backend": producer_backend,
                "source_bundle_mode": source_bundle_mode,
                "source_origin_class": source_origin_class,
                "topology_projected": False,
                "solver_verified": True,
                "verification_tier": upstream_tier,
                "source_input_path": str(path),
                "source_row_count": len(raw_rows),
                "valid_source_row_count": len(valid_rows),
                "invalid_source_row_count": len(raw_rows) - len(valid_rows),
                "instruction_sidecar_evidence_model": evidence_model,
                "instruction_sidecar_rebar_delivery_mode": rebar_delivery_mode,
            },
            "rows": valid_rows,
            "artifacts": {
                "invalid_member_ids_head": invalid_member_ids[:16],
            },
        },
        invalid_member_ids,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--joint-geometry-source", required=True)
    parser.add_argument("--rebar-anchorage-source", required=True)
    parser.add_argument("--clash-verification-source", required=True)
    parser.add_argument("--solver-name", default="panel_zone_external_solver")
    parser.add_argument("--producer-backend", default="panel_zone_external_solver")
    parser.add_argument("--source-bundle-mode", default="nested_solver_export")
    parser.add_argument("--source-origin-class", default="unclassified_external_source")
    parser.add_argument("--verification-tier", default="solver_verified_3d_source_bundle")
    parser.add_argument("--evidence-model", default="direct_solver_export")
    parser.add_argument("--rebar-delivery-mode", default="solver_verified_layout_rows")
    parser.add_argument("--member-mapping-sidecar", default="")
    parser.add_argument("--out", default="implementation/phase1/panel_zone_solver_verified_export_bundle.json")
    args = parser.parse_args()

    producer_backend = str(args.producer_backend).strip() or "panel_zone_external_solver"
    source_bundle_mode = str(args.source_bundle_mode).strip() or "nested_solver_export"
    source_origin_class = str(args.source_origin_class).strip() or "unclassified_external_source"
    evidence_model = str(args.evidence_model).strip() or "direct_solver_export"
    rebar_delivery_mode = str(args.rebar_delivery_mode).strip() or "solver_verified_layout_rows"
    member_mapping_sidecar = _normalize_member_mapping_sidecar(Path(args.member_mapping_sidecar)) if str(args.member_mapping_sidecar).strip() else {
        "present": False,
        "path": str(args.member_mapping_sidecar or ""),
        "mapping_mode": "",
        "row_count": 0,
        "member_map": {},
        "rows": [],
    }

    joint_payload, joint_invalid = _normalize_source(
        path=Path(args.joint_geometry_source),
        source_kind="panel_zone_joint_geometry_3d",
        producer_backend=producer_backend,
        source_bundle_mode=source_bundle_mode,
        source_origin_class=source_origin_class,
        evidence_model=evidence_model,
        rebar_delivery_mode=rebar_delivery_mode,
    )
    anchorage_payload, anchorage_invalid = _normalize_source(
        path=Path(args.rebar_anchorage_source),
        source_kind="panel_zone_rebar_anchorage_3d",
        producer_backend=producer_backend,
        source_bundle_mode=source_bundle_mode,
        source_origin_class=source_origin_class,
        evidence_model=evidence_model,
        rebar_delivery_mode=rebar_delivery_mode,
    )
    clash_payload, clash_invalid = _normalize_source(
        path=Path(args.clash_verification_source),
        source_kind="panel_zone_clash_verification_3d",
        producer_backend=producer_backend,
        source_bundle_mode=source_bundle_mode,
        source_origin_class=source_origin_class,
        evidence_model=evidence_model,
        rebar_delivery_mode=rebar_delivery_mode,
    )

    bundle_contract_pass = bool(
        joint_payload["contract_pass"] and anchorage_payload["contract_pass"] and clash_payload["contract_pass"]
    )
    invalid_counts = {
        "panel_zone_joint_geometry_3d": len(joint_invalid),
        "panel_zone_rebar_anchorage_3d": len(anchorage_invalid),
        "panel_zone_clash_verification_3d": len(clash_invalid),
    }
    reason_code = "PASS" if bundle_contract_pass else "ERR_SOURCE_ROWS_INVALID"
    reason = (
        "solver-verified panel-zone bundle normalized from external source rows"
        if bundle_contract_pass
        else "one or more solver-verified panel-zone source inputs were missing required rows or fields"
    )

    payload = {
        "schema_version": "1.0",
        "run_id": "phase1-panel-zone-solver-verified-export-bundle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "solver": {
            "name": str(args.solver_name).strip() or "panel_zone_external_solver",
            "backend": producer_backend,
            "export_version": "1.0",
        },
        "summary": {
            "producer_backend": producer_backend,
            "source_bundle_mode": source_bundle_mode,
            "source_origin_class": source_origin_class,
            "topology_projected": False,
            "solver_verified": True,
            "verification_tier": str(args.verification_tier).strip() or "solver_verified_3d_source_bundle",
            "required_sources_complete": bool(bundle_contract_pass),
            "source_row_counts": {
                "panel_zone_joint_geometry_3d": int(joint_payload["summary"]["valid_source_row_count"]),
                "panel_zone_rebar_anchorage_3d": int(anchorage_payload["summary"]["valid_source_row_count"]),
                "panel_zone_clash_verification_3d": int(clash_payload["summary"]["valid_source_row_count"]),
            },
            "invalid_source_row_counts": invalid_counts,
            "source_input_paths": {
                "panel_zone_joint_geometry_3d": str(args.joint_geometry_source),
                "panel_zone_rebar_anchorage_3d": str(args.rebar_anchorage_source),
                "panel_zone_clash_verification_3d": str(args.clash_verification_source),
            },
            "instruction_sidecar_evidence_model": evidence_model,
            "instruction_sidecar_rebar_delivery_mode": rebar_delivery_mode,
            "member_mapping_sidecar_present": bool(member_mapping_sidecar["present"]),
            "member_mapping_sidecar_path": str(member_mapping_sidecar["path"] or ""),
            "member_mapping_sidecar_mode": str(member_mapping_sidecar["mapping_mode"] or ""),
            "member_mapping_sidecar_row_count": int(member_mapping_sidecar["row_count"]),
        },
        "panel_zone_3d_results": {
            "panel_zone_joint_geometry_3d": joint_payload,
            "panel_zone_rebar_anchorage_3d": anchorage_payload,
            "panel_zone_clash_verification_3d": clash_payload,
        },
        "member_mapping_sidecar": {
            "present": bool(member_mapping_sidecar["present"]),
            "path": str(member_mapping_sidecar["path"] or ""),
            "mapping_mode": str(member_mapping_sidecar["mapping_mode"] or ""),
            "row_count": int(member_mapping_sidecar["row_count"]),
            "rows": list(member_mapping_sidecar["rows"]),
            "member_map": dict(member_mapping_sidecar["member_map"]),
        },
        "contract_pass": bool(bundle_contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone solver-verified export bundle: {out}")


if __name__ == "__main__":
    main()
