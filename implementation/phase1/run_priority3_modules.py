#!/usr/bin/env python3
"""Run and validate the three advanced Phase-1 modules in one command.

Modules:
1) zero_copy_bridge_stub.py
2) orthogonal_krylov_projection.py
3) kbc_md_material_parser.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-priority3-summary"

REASON_CODES = {
    "PASS": "all three modules passed with metadata-compatible versions",
    "ERR_MODULE_FAIL": "one or more modules failed",
    "ERR_METADATA_VERSION_MISMATCH": "module metadata major versions mismatch",
}


def run_cmd(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _major(v: str | None) -> str:
    if not isinstance(v, str) or not v:
        return "unknown"
    return v.split(".")[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="implementation/phase1")
    parser.add_argument("--alpha", type=float, default=0.35)
    parser.add_argument("--m", type=int, default=4)
    py = sys.executable
    parser.add_argument("--bridge-producer-cmd", default=f"{py} implementation/phase1/engine_hook_stub.py")
    parser.add_argument("--operator-source", choices=["matrix", "hook"], default="hook")
    parser.add_argument("--operator-cmd", default=f"{py} implementation/phase1/engine_hook_stub.py")
    parser.add_argument("--material-input", default="implementation/phase1/material_input_sample.csv")
    parser.add_argument("--reduction-threshold", type=float, default=0.98)
    parser.add_argument("--orthogonality-threshold", type=float, default=1e-6)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    zc = out_dir / "zero_copy_bridge_report.json"
    kp = out_dir / "krylov_projection_report.json"
    mm = out_dir / "material_map_report.json"

    run_cmd([
        sys.executable,
        "implementation/phase1/zero_copy_bridge_stub.py",
        "--out",
        str(zc),
        "--producer-cmd",
        args.bridge_producer_cmd,
    ])
    run_cmd([
        sys.executable,
        "implementation/phase1/orthogonal_krylov_projection.py",
        "--out",
        str(kp),
        "--alpha",
        str(args.alpha),
        "--m",
        str(args.m),
        "--operator-source",
        args.operator_source,
        "--operator-cmd",
        args.operator_cmd,
        "--reduction-threshold",
        str(args.reduction_threshold),
        "--orthogonality-threshold",
        str(args.orthogonality_threshold),
    ])
    run_cmd([
        sys.executable,
        "implementation/phase1/kbc_md_material_parser.py",
        "--input",
        args.material_input,
        "--out",
        str(mm),
    ])

    zc_data = json.loads(zc.read_text(encoding="utf-8"))
    kp_data = json.loads(kp.read_text(encoding="utf-8"))
    mm_data = json.loads(mm.read_text(encoding="utf-8"))

    pq = kp_data.get("projection_quality", {})
    pass_projection = bool(pq.get("threshold_pass", False) and pq.get("orthogonality_pass", False))
    pass_material = bool(mm_data.get("parser_quality_pass", False))
    pass_bridge = bool(
        zc_data.get("roundtrip_success", False)
        and zc_data.get("shared_storage", False)
        and int(zc_data.get("host_copy_bytes", 1)) == 0
    )

    module_versions = {
        "zero_copy": zc_data.get("schema_version", "1.0"),
        "krylov": kp_data.get("schema_version", "1.0"),
        "material": mm_data.get("schema_version", "1.0"),
    }
    major_set = {_major(v) for v in module_versions.values()}
    metadata_compatible = len(major_set) == 1

    module_pass = pass_bridge and pass_projection and pass_material
    if not module_pass:
        reason_code = "ERR_MODULE_FAIL"
    elif not metadata_compatible:
        reason_code = "ERR_METADATA_VERSION_MISMATCH"
    else:
        reason_code = "PASS"

    summary = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "module1_zero_copy_bridge": pass_bridge,
        "module2_krylov_projection": pass_projection,
        "module3_material_parser": pass_material,
        "module_metadata": {
            "versions": module_versions,
            "major_versions": {k: _major(v) for k, v in module_versions.items()},
            "metadata_compatible": metadata_compatible,
        },
        "all_pass": module_pass and metadata_compatible,
        "reason_code": reason_code,
        "reason": REASON_CODES[reason_code],
        "artifacts": {
            "zero_copy": str(zc),
            "krylov": str(kp),
            "material": str(mm),
        },
    }

    summary_path = out_dir / "priority3_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote priority-3 summary: {summary_path}")
    print(json.dumps(summary, indent=2))

    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
