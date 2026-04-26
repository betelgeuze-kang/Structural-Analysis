#!/usr/bin/env python3
"""Track the manual landing status for E-Defense / PEER measured-response artifacts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MANIFEST = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json")
DEFAULT_INPUT_ROOT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_OUT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_status(source_manifest: dict[str, Any], input_root: Path) -> dict[str, Any]:
    expected_groups = source_manifest.get("expected_groups") if isinstance(source_manifest.get("expected_groups"), dict) else {}
    measured_group = expected_groups.get("measured_response") if isinstance(expected_groups.get("measured_response"), dict) else {}
    patterns = [str(item) for item in (measured_group.get("patterns") or []) if str(item or "")]
    public_landing_present = bool(
        measured_group.get("public_landing_present", measured_group.get("present", False))
    )
    matched_files = [str(item) for item in (measured_group.get("matched_files") or []) if str(item or "")]
    workbook_candidate_count = int(measured_group.get("workbook_candidate_count", 0) or 0)
    csv_like_candidate_count = int(measured_group.get("csv_like_candidate_count", 0) or 0)
    archive_candidate_count = int(measured_group.get("archive_candidate_count", 0) or 0)
    json_candidate_count = int(measured_group.get("json_candidate_count", 0) or 0)
    explicit_channel_claims = (
        measured_group.get("explicit_channel_claims")
        if isinstance(measured_group.get("explicit_channel_claims"), dict)
        else {}
    )
    acceleration_claimed = bool(explicit_channel_claims.get("acceleration", False))
    drift_claimed = bool(explicit_channel_claims.get("drift", False))
    sensor_manifest_claimed = bool(explicit_channel_claims.get("sensor_manifest", False))
    measured_response_present = bool(
        public_landing_present
        and (
            csv_like_candidate_count > 0
            or archive_candidate_count > 0
            or json_candidate_count > 0
            or acceleration_claimed
            or drift_claimed
            or sensor_manifest_claimed
        )
    )
    landing_mode = str(measured_group.get("public_landing_mode", "") or "missing")
    channel_inventory_claimed = bool(
        acceleration_claimed
        or drift_claimed
        or sensor_manifest_claimed
        or csv_like_candidate_count > 0
        or archive_candidate_count > 0
        or json_candidate_count > 0
    )
    contract_pass = public_landing_present
    if contract_pass and measured_response_present:
        reason_code = "PASS"
    elif contract_pass:
        reason_code = "PASS_PUBLIC_LANDING_RECORDED_CHANNELS_UNVERIFIED"
    else:
        reason_code = "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING"
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(DEFAULT_SOURCE_MANIFEST),
        "input_root": str(input_root),
        "public_landing_present": public_landing_present,
        "measured_response_present": measured_response_present,
        "channel_inventory_claimed": channel_inventory_claimed,
        "channel_claim_basis": str(explicit_channel_claims.get("basis", "") or "filename_inventory_only"),
        "contract_pass": contract_pass,
        "reason_code": reason_code,
        "reason": (
            "Measured response public landing is recorded and explicit channel evidence is available."
            if contract_pass and measured_response_present
            else "Measured response public landing is recorded, but acceleration/drift/sensor availability still needs normalization."
            if contract_pass
            else "Measured response bundle is still missing from the public PEER/E-Defense landing root and needs manual placement."
        ),
        "summary_line": (
            f"E-Defense/PEER measured-response landing: {'PASS' if contract_pass else 'PENDING'} | "
            f"matched={len(matched_files)} | workbooks={workbook_candidate_count} | csv_like={csv_like_candidate_count} | "
            f"channels={'claimed' if channel_inventory_claimed else 'unverified'} | root={input_root.name}"
        ),
        "expected_patterns": patterns,
        "matched_files": matched_files,
        "landing_mode": landing_mode,
        "summary": {
            "matched_file_count": len(matched_files),
            "workbook_candidate_count": workbook_candidate_count,
            "csv_like_candidate_count": csv_like_candidate_count,
            "archive_candidate_count": archive_candidate_count,
            "json_candidate_count": json_candidate_count,
            "acceleration_claimed": acceleration_claimed,
            "drift_claimed": drift_claimed,
            "sensor_manifest_claimed": sensor_manifest_claimed,
        },
        "next_action": (
            "Normalize the landed workbook/bundle to verify acceleration/drift/sensor coverage."
            if contract_pass and not measured_response_present
            else "Rerun benchmark-case normalization with the landed measured-response bundle."
            if contract_pass
            else "Place measured response workbook/CSV/measurement/sensor files under the landing root, then rerun prepare_edefense_peer_blind_prediction_source_manifest.py."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_status(_load_json(Path(args.source_manifest)), Path(args.input_root))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense/PEER measured-response landing status: {out_path}")


if __name__ == "__main__":
    main()
