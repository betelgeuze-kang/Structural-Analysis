#!/usr/bin/env python3
"""Record measured-response landing provenance for the E-Defense / PEER blind-prediction family."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_MANIFEST = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json"
)
DEFAULT_INPUT_ROOT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_OUT = Path(
    "implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json"
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _scan_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _match_patterns(path: Path, patterns: list[str]) -> bool:
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def _read_csv_preview(path: Path, sample_rows: int = 3) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            headers = list(reader.fieldnames or [])
            rows: list[dict[str, str]] = []
            row_count = 0
            for row in reader:
                row_count += 1
                if len(rows) < sample_rows:
                    rows.append({str(key): str(value) for key, value in row.items()})
    except Exception:
        return {"headers": [], "sample_rows": [], "row_count": 0}
    return {"headers": headers, "sample_rows": rows, "row_count": row_count}


def build_manifest(source_manifest: dict[str, Any], input_root: Path) -> dict[str, Any]:
    expected_groups = source_manifest.get("expected_groups") if isinstance(source_manifest.get("expected_groups"), dict) else {}
    measured_group = expected_groups.get("measured_response") if isinstance(expected_groups.get("measured_response"), dict) else {}
    patterns = [str(item) for item in (measured_group.get("patterns") or []) if str(item or "")]
    files = _scan_files(input_root)
    matched_paths = [path for path in files if _match_patterns(path, patterns)]

    inventory: list[dict[str, Any]] = []
    acceleration_candidates = 0
    drift_candidates = 0
    sensor_candidates = 0
    csv_count = 0
    for path in matched_paths:
        rel_path = path.relative_to(input_root).as_posix()
        lower_name = path.name.lower()
        is_csv = path.suffix.lower() == ".csv"
        if is_csv:
            csv_count += 1
        if "accel" in lower_name or "response" in lower_name:
            acceleration_candidates += 1
        if "drift" in lower_name:
            drift_candidates += 1
        if "sensor" in lower_name or "measurement" in lower_name:
            sensor_candidates += 1
        csv_preview = _read_csv_preview(path) if is_csv else {"headers": [], "sample_rows": [], "row_count": 0}
        inventory.append(
            {
                "path": rel_path,
                "bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
                "csv_preview": csv_preview,
            }
        )

    landed = bool(matched_paths)
    reason_code = "PASS" if landed else "ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING"
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_manifest": str(DEFAULT_SOURCE_MANIFEST),
        "input_root": str(input_root),
        "contract_pass": landed,
        "landing_state": "recorded" if landed else "pending",
        "reason_code": reason_code,
        "reason": (
            "Measured-response landing provenance is recorded and ready for normalization."
            if landed
            else "Measured-response landing provenance is pending because no measured-response bundle has been placed yet."
        ),
        "summary_line": (
            f"E-Defense/PEER measured-response landing manifest: {'RECORDED' if landed else 'PENDING'} | "
            f"matched={len(matched_paths)} | csv={csv_count} | accel_candidates={acceleration_candidates} | "
            f"drift_candidates={drift_candidates} | sensors={sensor_candidates}"
        ),
        "summary": {
            "matched_file_count": len(matched_paths),
            "csv_file_count": csv_count,
            "acceleration_candidate_count": acceleration_candidates,
            "drift_candidate_count": drift_candidates,
            "sensor_candidate_count": sensor_candidates,
        },
        "expected_patterns": patterns,
        "matched_files": [path.relative_to(input_root).as_posix() for path in matched_paths],
        "file_inventory": inventory,
        "next_action": (
            "Rerun measured-response normalize/build/compare steps."
            if landed
            else "Place official measured-response CSV/measurement/sensor files under the landing root, then rerun this manifest."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-manifest", default=str(DEFAULT_SOURCE_MANIFEST))
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT_ROOT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_manifest(_load_json(Path(args.source_manifest)), Path(args.input_root))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense/PEER measured-response landing manifest: {out_path}")


if __name__ == "__main__":
    main()
