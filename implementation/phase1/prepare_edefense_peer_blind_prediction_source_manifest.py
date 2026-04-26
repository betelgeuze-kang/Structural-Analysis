#!/usr/bin/env python3
"""Prepare a local source-manifest for one E-Defense / PEER blind prediction family."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any


RUN_ID = "phase1-prepare-edefense-peer-blind-prediction-source-manifest"
DEFAULT_INPUT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01")
DEFAULT_OUT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json")
SOURCE_URLS = [
    "https://peer.berkeley.edu/2009-blind-analysis-contest-e-defense",
    "https://peer.berkeley.edu/sites/default/files/news_e-defense_blind_analysis_2009-article.pdf",
    "https://peer.berkeley.edu/nees-tipse-defense-announce-blind-analysis-contest-seismic-isolation-test",
    "https://apps.peer.berkeley.edu/prediction_contest/",
    "https://apps.peer.berkeley.edu/prediction_contest/?page_id=13",
]

EXPECTED_GROUPS: dict[str, dict[str, Any]] = {
    "geometry_model": {
        "required": True,
        "patterns": [
            "*geometry*.json",
            "*geometry*.csv",
            "*.tcl",
            "*.inp",
            "*.dat",
            "*.mgt",
            "*construction*drawings*.pdf",
            "*columns*.pdf",
            "*bent-cap*.pdf",
            "*foundation*.pdf",
            "*weight_blocks*.pdf",
        ],
        "description": "Specimen or frame geometry / model definition files.",
    },
    "material_properties": {
        "required": True,
        "patterns": [
            "*material*.json",
            "*material*.csv",
            "*section*.json",
            "*section*.csv",
            "*property*.csv",
            "*materials.zip",
            "*posttensiondetails*.pdf",
        ],
        "description": "Member, section, and constitutive property tables.",
    },
    "excitation_history": {
        "required": True,
        "patterns": ["*ground*motion*.csv", "*excitation*.csv", "*input*.csv", "*accel*.csv", "*.at2", "*gms*.xlsx"],
        "description": "Input excitation or ground-motion histories used in the blind prediction task.",
    },
    "measured_response": {
        "required": True,
        "patterns": [
            "*response*.csv",
            "*response*.tsv",
            "*response*.txt",
            "*response*.json",
            "*response*.zip",
            "*measurement*.csv",
            "*measurement*.tsv",
            "*measurement*.txt",
            "*measurement*.json",
            "*measurement*.zip",
            "*sensor*.csv",
            "*sensor*.tsv",
            "*sensor*.txt",
            "*sensor*.json",
            "*sensor*.zip",
            "*drift*.csv",
            "*drift*.tsv",
            "*drift*.txt",
            "*drift*.json",
            "*drift*.zip",
            "*accel*.csv",
            "*accel*.tsv",
            "*accel*.txt",
            "*accel*.json",
            "*accel*.zip",
            "*response*.xlsx",
            "*measurement*.xlsx",
            "*sensor*.xlsx",
            "*drift*.xlsx",
            "*accel*.xlsx",
            "*experimentalresults*.xlsx",
            "*experimental*results*.xlsx",
            "*experimentalresults*.zip",
        ],
        "description": "Measured response channels for compare/report/viewer validation.",
    },
    "reference_docs": {
        "required": False,
        "patterns": ["*.pdf", "*readme*.txt", "*readme*.md"],
        "description": "Contest notes, benchmark instructions, or reference PDFs.",
    },
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _matches_any(path: Path, patterns: list[str]) -> bool:
    name = path.name.lower()
    return any(fnmatch.fnmatch(name, pattern.lower()) for pattern in patterns)


def _scan_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file())


def _build_measured_response_metadata(matched_files: list[str]) -> dict[str, Any]:
    workbook_suffixes = {".xlsx", ".xlsm", ".xls", ".ods"}
    csv_like_suffixes = {".csv", ".tsv", ".txt"}

    workbook_files: list[str] = []
    csv_like_files: list[str] = []
    archive_files: list[str] = []
    json_files: list[str] = []
    acceleration_claim = False
    drift_claim = False
    sensor_claim = False

    for rel in matched_files:
        path = Path(rel)
        lower_name = path.name.lower()
        suffix = path.suffix.lower()
        if suffix in workbook_suffixes:
            workbook_files.append(rel)
        elif suffix in csv_like_suffixes:
            csv_like_files.append(rel)
        elif suffix == ".zip":
            archive_files.append(rel)
        elif suffix == ".json":
            json_files.append(rel)

        if any(token in lower_name for token in ("accel", "acceleration")):
            acceleration_claim = True
        if "drift" in lower_name:
            drift_claim = True
        if any(token in lower_name for token in ("sensor", "channel", "layout", "manifest")):
            sensor_claim = True

    if workbook_files and not (csv_like_files or archive_files or json_files):
        public_landing_mode = "workbook_only"
    elif csv_like_files:
        public_landing_mode = "csv_like"
    elif archive_files:
        public_landing_mode = "archive_only"
    elif json_files:
        public_landing_mode = "json_only"
    elif matched_files:
        public_landing_mode = "other"
    else:
        public_landing_mode = "missing"

    return {
        "public_landing_present": bool(matched_files),
        "public_landing_mode": public_landing_mode,
        "workbook_candidate_count": len(workbook_files),
        "csv_like_candidate_count": len(csv_like_files),
        "archive_candidate_count": len(archive_files),
        "json_candidate_count": len(json_files),
        "workbook_files": workbook_files,
        "csv_like_files": csv_like_files,
        "archive_files": archive_files,
        "json_files": json_files,
        "explicit_channel_claims": {
            "acceleration": acceleration_claim,
            "drift": drift_claim,
            "sensor_manifest": sensor_claim,
            "basis": "filename_inventory_only",
        },
    }


def build_manifest(input_root: Path) -> dict[str, Any]:
    files = _scan_files(input_root)
    rel_files = [path.relative_to(input_root).as_posix() for path in files]

    inventory: list[dict[str, Any]] = []
    group_hits: dict[str, list[str]] = {group: [] for group in EXPECTED_GROUPS}
    for path, rel in zip(files, rel_files):
        matched_groups = [
            group
            for group, meta in EXPECTED_GROUPS.items()
            if _matches_any(path, meta["patterns"])
        ]
        for group in matched_groups:
            group_hits[group].append(rel)
        inventory.append(
            {
                "path": rel,
                "bytes": int(path.stat().st_size),
                "sha256": _sha256(path),
                "matched_groups": matched_groups,
            }
        )

    expected_groups: dict[str, dict[str, Any]] = {}
    for group, meta in EXPECTED_GROUPS.items():
        payload = {
            "required": bool(meta["required"]),
            "description": str(meta["description"]),
            "patterns": list(meta["patterns"]),
            "matched_file_count": len(group_hits[group]),
            "matched_files": group_hits[group],
            "present": bool(group_hits[group]),
        }
        if group == "measured_response":
            payload.update(_build_measured_response_metadata(group_hits[group]))
        expected_groups[group] = payload
    required_groups = [group for group, meta in EXPECTED_GROUPS.items() if meta["required"]]
    contract_pass = all(expected_groups[group]["present"] for group in required_groups)

    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": "edefense_peer_blind_prediction",
        "seed_id": "edefense_peer_blind_prediction_seed_01",
        "source_name": "E-Defense / PEER blind prediction benchmark",
        "source_urls": SOURCE_URLS,
        "source_origin_class": "official_external_benchmark",
        "benchmark_track": "blind_prediction_dynamic_holdout",
        "landing_track": "implementation/phase1/open_data/pbd_hinge",
        "local_input_root": str(input_root),
        "expected_groups": expected_groups,
        "local_file_inventory": inventory,
        "summary": {
            "file_count": len(inventory),
            "required_group_count": len(required_groups),
            "required_group_pass_count": sum(1 for group in required_groups if expected_groups[group]["present"]),
        },
        "contract_pass": bool(contract_pass),
        "reason": (
            "Local E-Defense / PEER blind-prediction package covers the required onboarding artifact groups."
            if contract_pass
            else "Manifest scaffold prepared, but one or more required blind-prediction artifact groups are still missing."
        ),
        "next_action": (
            "Normalize this first blind-prediction family into source_manifest -> benchmark_case -> compare_report -> viewer_entry."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", default=str(DEFAULT_INPUT))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    input_root = Path(args.input_root)
    payload = build_manifest(input_root)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense / PEER blind-prediction source manifest: {out_path}")


if __name__ == "__main__":
    main()
