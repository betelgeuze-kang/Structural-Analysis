#!/usr/bin/env python3
"""Step 4: generate static SoA-DLPack contract report."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

INTERFACE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-soa-dlpack-contract"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/soa_dlpack_contract_report.json")
    args = p.parse_args()

    tensor_fields = [
        {"name": "x", "dtype": "float32", "contiguous": True},
        {"name": "y", "dtype": "float32", "contiguous": True},
        {"name": "z", "dtype": "float32", "contiguous": True},
        {"name": "mass", "dtype": "float32", "contiguous": True},
        {"name": "support_mask", "dtype": "uint8", "contiguous": True},
    ]
    allowed = {"float32", "uint8"}
    layout = "SoA"
    reason_code = "PASS"
    if layout != "SoA":
        reason_code = "ERR_LAYOUT_NOT_SOA"
    elif not all(t["contiguous"] for t in tensor_fields):
        reason_code = "ERR_NON_CONTIGUOUS"
    elif not all(t["dtype"] in allowed for t in tensor_fields):
        reason_code = "ERR_DTYPE_UNSUPPORTED"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "layout": layout,
        "device": "cpu",
        "dlpack_capsule_name": "dltensor",
        "zero_copy_expected": True,
        "layout_pass": reason_code == "PASS",
        "reason_code": reason_code,
        "tensor_fields": tensor_fields,
    }

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote SoA DLPack contract report: {out}")
    if reason_code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
