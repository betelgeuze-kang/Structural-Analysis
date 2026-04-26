#!/usr/bin/env python3
"""Generate a bounded contract JSON for one panel-zone 3D source artifact.

This is intentionally a contract producer, not a geometry engine.
It accepts one of the three panel-zone 3D source kinds and validates that the
optional upstream artifact matches the expected kind before upgrading the
contract to PASS.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SOURCE_KIND_MAP = {
    "joint_geometry": "panel_zone_joint_geometry_3d",
    "rebar_anchorage": "panel_zone_rebar_anchorage_3d",
    "clash_verification": "panel_zone_clash_verification_3d",
}

REASONS = {
    "PASS": "panel-zone 3D source contract is attached and validated",
    "ERR_SOURCE_ARTIFACT_MISSING": "expected upstream 3D source artifact is missing",
    "ERR_SOURCE_ARTIFACT_INVALID": "upstream 3D source artifact is present but invalid",
    "ERR_SOURCE_KIND_MISMATCH": "upstream 3D source artifact kind does not match the requested contract",
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"1", "y", "yes", "true", "on"}:
            return True
        if v in {"0", "n", "no", "false", "off"}:
            return False
    try:
        return bool(value)
    except Exception:
        return bool(default)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _extract_source_provenance(payload: dict) -> dict[str, Any]:
    source_provenance = payload.get("source_provenance", {})
    if not isinstance(source_provenance, dict):
        return {}
    return source_provenance


def _extract_kind(payload: dict) -> str:
    source_provenance = _extract_source_provenance(payload)
    return str(
        payload.get("source_kind")
        or source_provenance.get("source_kind")
        or source_provenance.get("source_artifact_kind")
        or payload.get("kind")
        or ""
    ).strip()


def _extract_verification_tier(payload: dict) -> str:
    source_provenance = _extract_source_provenance(payload)
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    return str(
        payload.get("verification_tier")
        or summary.get("verification_tier")
        or source_provenance.get("verification_tier")
        or summary.get("artifact_mode")
        or ""
    ).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-kind", choices=sorted(SOURCE_KIND_MAP), required=True)
    parser.add_argument(
        "--source-artifact",
        default="",
        help="Optional upstream source artifact JSON to validate and wrap in a contract.",
    )
    parser.add_argument(
        "--out",
        default="implementation/phase1/panel_zone_3d_source_contract.json",
    )
    args = parser.parse_args()

    expected_kind = SOURCE_KIND_MAP[args.source_kind]
    source_path = Path(args.source_artifact) if str(args.source_artifact).strip() else Path()
    source_present = bool(str(args.source_artifact).strip()) and source_path.exists()
    source_payload = _load_json(source_path) if source_present else {}
    source_contract_pass = bool(_safe_bool(source_payload.get("contract_pass", False)))
    source_kind = _extract_kind(source_payload)
    source_kind_match = bool(source_present and (not source_kind or source_kind == expected_kind))
    upstream_verification_tier = _extract_verification_tier(source_payload)
    upstream_source_provenance = _extract_source_provenance(source_payload)
    source_row_count = _safe_int(upstream_source_provenance.get("source_row_count", 0))
    valid_source_row_count = _safe_int(upstream_source_provenance.get("valid_source_row_count", 0))
    invalid_source_row_count = _safe_int(upstream_source_provenance.get("invalid_source_row_count", 0))
    candidate_member_count = _safe_int(upstream_source_provenance.get("candidate_member_count", 0))
    overlap_member_count = _safe_int(upstream_source_provenance.get("overlap_member_count", 0))
    candidate_scan_mode = str(upstream_source_provenance.get("candidate_scan_mode", "") or "")
    topology_capable_input = bool(_safe_bool(upstream_source_provenance.get("topology_capable_input", False)))
    producer_backend = str(upstream_source_provenance.get("producer_backend", "") or "")
    source_bundle_mode = str(upstream_source_provenance.get("source_bundle_mode", "") or "")
    topology_projected = bool(_safe_bool(upstream_source_provenance.get("topology_projected", False)))
    solver_verified = bool(_safe_bool(upstream_source_provenance.get("solver_verified", False)))
    instruction_sidecar_present = bool(_safe_bool(upstream_source_provenance.get("instruction_sidecar_present", False)))
    instruction_sidecar_change_count = _safe_int(upstream_source_provenance.get("instruction_sidecar_change_count", 0))
    instruction_sidecar_candidate_overlap_mode = str(
        upstream_source_provenance.get("instruction_sidecar_candidate_overlap_mode", "") or ""
    )
    instruction_sidecar_overlap_row_count = _safe_int(upstream_source_provenance.get("instruction_sidecar_overlap_row_count", 0))
    instruction_sidecar_overlap_member_count = _safe_int(
        upstream_source_provenance.get("instruction_sidecar_overlap_member_count", 0)
    )
    instruction_sidecar_overlap_group_count = _safe_int(
        upstream_source_provenance.get("instruction_sidecar_overlap_group_count", 0)
    )
    instruction_sidecar_evidence_model = str(
        upstream_source_provenance.get("instruction_sidecar_evidence_model", "") or ""
    )
    instruction_sidecar_rebar_delivery_mode = str(
        upstream_source_provenance.get("instruction_sidecar_rebar_delivery_mode", "") or ""
    )
    member_mapping_sidecar_present = bool(
        _safe_bool(upstream_source_provenance.get("member_mapping_sidecar_present", False))
    )
    member_mapping_sidecar_path = str(
        upstream_source_provenance.get("member_mapping_sidecar_path", "") or ""
    )
    member_mapping_sidecar_mode = str(
        upstream_source_provenance.get("member_mapping_sidecar_mode", "") or ""
    )
    member_mapping_sidecar_row_count = _safe_int(
        upstream_source_provenance.get("member_mapping_sidecar_row_count", 0)
    )
    member_mapping_sidecar_applied_row_count = _safe_int(
        upstream_source_provenance.get("member_mapping_sidecar_applied_row_count", 0)
    )
    member_mapping_sidecar_unmapped_source_member_count = _safe_int(
        upstream_source_provenance.get("member_mapping_sidecar_unmapped_source_member_count", 0)
    )
    required_source_fields = list(upstream_source_provenance.get("required_source_fields", []) or [])
    source_input_path = str(upstream_source_provenance.get("source_input_path", "") or "")
    candidate_member_ids_head = list(upstream_source_provenance.get("candidate_member_ids_head", []) or [])
    source_member_ids_head = list(upstream_source_provenance.get("source_member_ids_head", []) or [])
    overlap_member_ids_head = list(upstream_source_provenance.get("overlap_member_ids_head", []) or [])

    if not source_present:
        reason_code = "ERR_SOURCE_ARTIFACT_MISSING"
        reason = "expected upstream 3D source artifact is missing"
    elif not source_contract_pass:
        reason_code = "ERR_SOURCE_ARTIFACT_INVALID"
        reason = "upstream 3D source artifact is present but invalid"
    elif source_kind and source_kind != expected_kind:
        reason_code = "ERR_SOURCE_KIND_MISMATCH"
        reason = "upstream 3D source artifact kind does not match the requested contract"
    else:
        reason_code = "PASS"
        reason = "panel-zone 3D source contract is attached and validated"

    contract_pass = reason_code == "PASS"
    payload = {
        "schema_version": "1.0",
        "run_id": f"phase1-panel-zone-{args.source_kind}-source-contract",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_kind": expected_kind,
        "source_provenance": {
            "source_kind": expected_kind,
            "source_artifact_path": str(source_path) if source_present else str(args.source_artifact or ""),
            "source_artifact_present": bool(source_present),
            "source_artifact_contract_pass": bool(source_contract_pass),
            "source_artifact_kind": source_kind,
            "source_kind_match": bool(source_kind_match),
            "verification_tier": upstream_verification_tier or f"{expected_kind}_contract_stub",
            "source_row_count": int(source_row_count),
            "valid_source_row_count": int(valid_source_row_count),
            "invalid_source_row_count": int(invalid_source_row_count),
            "candidate_member_count": int(candidate_member_count),
            "overlap_member_count": int(overlap_member_count),
            "candidate_scan_mode": candidate_scan_mode,
            "topology_capable_input": bool(topology_capable_input),
            "producer_backend": producer_backend,
            "source_bundle_mode": source_bundle_mode,
            "upstream_verification_tier": upstream_verification_tier,
            "topology_projected": bool(topology_projected),
            "solver_verified": bool(solver_verified),
            "instruction_sidecar_present": bool(instruction_sidecar_present),
            "instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
            "member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "member_mapping_sidecar_path": member_mapping_sidecar_path,
            "member_mapping_sidecar_mode": member_mapping_sidecar_mode,
            "member_mapping_sidecar_row_count": int(member_mapping_sidecar_row_count),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_sidecar_applied_row_count),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_sidecar_unmapped_source_member_count
            ),
            "required_source_fields": required_source_fields,
            "source_input_path": source_input_path,
            "candidate_member_ids_head": candidate_member_ids_head[:16],
            "source_member_ids_head": source_member_ids_head[:16],
            "overlap_member_ids_head": overlap_member_ids_head[:16],
            "required_source_missing": not source_present,
        },
        "summary": {
            "source_kind": expected_kind,
            "source_status": "validated" if contract_pass else "open",
            "verification_tier": f"{expected_kind}_contract_validated" if contract_pass else f"{expected_kind}_contract_stub",
            "upstream_verification_tier": upstream_verification_tier,
            "source_artifact_present": bool(source_present),
            "source_artifact_contract_pass": bool(source_contract_pass),
            "source_kind_match": bool(source_kind_match),
            "source_row_count": int(source_row_count),
            "valid_source_row_count": int(valid_source_row_count),
            "invalid_source_row_count": int(invalid_source_row_count),
            "candidate_member_count": int(candidate_member_count),
            "overlap_member_count": int(overlap_member_count),
            "candidate_scan_mode": candidate_scan_mode,
            "topology_capable_input": bool(topology_capable_input),
            "producer_backend": producer_backend,
            "source_bundle_mode": source_bundle_mode,
            "topology_projected": bool(topology_projected),
            "solver_verified": bool(solver_verified),
            "instruction_sidecar_present": bool(instruction_sidecar_present),
            "instruction_sidecar_change_count": int(instruction_sidecar_change_count),
            "instruction_sidecar_candidate_overlap_mode": instruction_sidecar_candidate_overlap_mode,
            "instruction_sidecar_overlap_row_count": int(instruction_sidecar_overlap_row_count),
            "instruction_sidecar_overlap_member_count": int(instruction_sidecar_overlap_member_count),
            "instruction_sidecar_overlap_group_count": int(instruction_sidecar_overlap_group_count),
            "instruction_sidecar_evidence_model": instruction_sidecar_evidence_model,
            "instruction_sidecar_rebar_delivery_mode": instruction_sidecar_rebar_delivery_mode,
            "member_mapping_sidecar_present": bool(member_mapping_sidecar_present),
            "member_mapping_sidecar_mode": member_mapping_sidecar_mode,
            "member_mapping_sidecar_row_count": int(member_mapping_sidecar_row_count),
            "member_mapping_sidecar_applied_row_count": int(member_mapping_sidecar_applied_row_count),
            "member_mapping_sidecar_unmapped_source_member_count": int(
                member_mapping_sidecar_unmapped_source_member_count
            ),
        },
        "checks": {
            "source_artifact_present": bool(source_present),
            "source_artifact_contract_pass": bool(source_contract_pass),
            "source_kind_match": bool(source_kind_match),
            "source_contract_valid": bool(contract_pass),
            "source_overlap_present": bool(overlap_member_count > 0),
        },
        "contract_pass": bool(contract_pass),
        "reason_code": reason_code,
        "reason": reason,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote panel-zone 3D source contract: {out}")


if __name__ == "__main__":
    main()
