#!/usr/bin/env python3
"""Prepare a local source-manifest for the Canton Tower reduced SHM benchmark."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from implementation.phase1.canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices
except ImportError:  # pragma: no cover - direct script execution fallback
    from canton_tower_reduced_order_utils import summarize_canton_tower_system_matrices


RUN_ID = "phase1-prepare-canton-tower-reduced-shm-source-manifest"
DEFAULT_INPUT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm")
DEFAULT_OUT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json")
DEFAULT_PROBE = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.download_probe.json")
SOURCE_URLS = [
    "https://polyucee.hk/ceyxia/benchmark/benchmark.htm",
    "https://polyucee.hk/ceyxia/benchmark/tvtower.htm",
    "https://polyucee.hk/ceyxia/benchmark/task_i.htm",
]

EXPECTED_GROUPS: dict[str, dict[str, Any]] = {
    "system_matrices": {
        "required": True,
        "patterns": ["system_matrices.mat"],
        "description": "Official reduced-order system matrices for the benchmark model.",
    },
    "benchmark_docs": {
        "required": True,
        "patterns": [
            "*phase*i*fe*description*.pdf",
            "*measurement*description*.pdf",
            "*benchmark*.pdf",
            "*.pdf",
        ],
        "description": "Benchmark documentation PDFs describing channels and FE assumptions.",
    },
    "measured_response": {
        "required": True,
        "patterns": [
            "data_all.zip",
            "*data_all.zip",
            "*acceler*.zip",
            "*accel*.zip",
            "*wind*.zip",
            "*temperature*.zip",
            "*.csv",
        ],
        "description": "Measured acceleration / wind / temperature packages or extracted CSVs.",
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

    expected_groups = {
        group: {
            "required": bool(meta["required"]),
            "description": str(meta["description"]),
            "patterns": list(meta["patterns"]),
            "matched_file_count": len(group_hits[group]),
            "matched_files": group_hits[group],
            "present": bool(group_hits[group]),
        }
        for group, meta in EXPECTED_GROUPS.items()
    }
    required_groups = [group for group, meta in EXPECTED_GROUPS.items() if meta["required"]]
    contract_pass = all(expected_groups[group]["present"] for group in required_groups)
    matrix_summary: dict[str, Any] = {}
    matrix_path = input_root / "system_matrices.mat"
    if matrix_path.exists():
        try:
            matrix_summary = summarize_canton_tower_system_matrices(matrix_path)
        except Exception:
            matrix_summary = {}

    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_family": "canton_tower_reduced_shm",
        "seed_id": "canton_tower_reduced_shm_seed_01",
        "source_name": "Canton Tower reduced-order SHM benchmark",
        "source_urls": SOURCE_URLS,
        "source_origin_class": "official_public_benchmark_reference",
        "benchmark_track": "megastructure_shm",
        "landing_track": "implementation/phase1/open_data/megastructure",
        "benchmark_model_class": "official_reduced_order_shm",
        "local_input_root": str(input_root),
        "download_probe_report": str(DEFAULT_PROBE),
        "matrix_summary": matrix_summary,
        "expected_groups": expected_groups,
        "local_file_inventory": inventory,
        "summary": {
            "file_count": len(inventory),
            "required_group_count": len(required_groups),
            "required_group_pass_count": sum(1 for group in required_groups if expected_groups[group]["present"]),
            "matrix_key_count": int(matrix_summary.get("matrix_key_count", 0) or 0),
            "global_dof_count": int(matrix_summary.get("global_dof_count", 0) or 0),
            "segment_matrix_pair_count": int(matrix_summary.get("segment_matrix_pair_count", 0) or 0),
        },
        "contract_pass": bool(contract_pass),
        "reason": (
            "Local Canton Tower reduced SHM intake package is present and covers the required artifact groups."
            if contract_pass
            else "Manifest scaffold prepared, but one or more required Canton Tower artifact groups are still missing."
        ),
        "next_action": (
            "Run build_cases_from_megastructure_open.py against the prepared local package once measured CSV/ZIP assets are in place."
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
    print(f"Wrote Canton Tower reduced SHM source manifest: {out_path}")


if __name__ == "__main__":
    main()
