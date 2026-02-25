#!/usr/bin/env python3
"""Generate and statically validate dynamics/boundary contract artifact (Step 1)."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

INTERFACE_VERSION = "1.0.0"
SCHEMA_VERSION = "1.1"
RUN_ID = "phase1-dynamics-boundary-contract"

REASON = {
    "PASS": "contract satisfies required boundary/dynamics keys",
    "ERR_NODE_FIELD_MISSING": "node missing required field",
    "ERR_SUPPORT_TYPE_INVALID": "support_type not in enum",
    "ERR_DAMPING_INVALID": "damping parameters invalid",
    "ERR_DT_INVALID": "time_step_dt must be > 0",
}


def sample_payload() -> dict:
    return {
        "interface_version": INTERFACE_VERSION,
        "nodes": [
            {
                "node_id": "N1",
                "mass": 1e20,
                "is_fixed_mask": True,
                "support_type": "fixed",
                "dof_lock": {"ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
            },
            {
                "node_id": "N2",
                "mass": 1200.0,
                "is_fixed_mask": False,
                "support_type": "hinge",
                "dof_lock": {"ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False},
            },
        ],
        "dynamics": {
            "damping_model": "rayleigh",
            "alpha_m": 0.02,
            "beta_k": 0.001,
            "time_step_dt": 0.01,
            "external_force_profile": "combined",
        },
    }


def validate(payload: dict) -> str:
    for n in payload.get("nodes", []):
        for k in ("node_id", "mass", "is_fixed_mask", "support_type", "dof_lock"):
            if k not in n:
                return "ERR_NODE_FIELD_MISSING"
        if n["support_type"] not in {"fixed", "hinge", "roller", "free"}:
            return "ERR_SUPPORT_TYPE_INVALID"
    d = payload.get("dynamics", {})
    if d.get("damping_model") not in {"rayleigh", "modal", "none"}:
        return "ERR_DAMPING_INVALID"
    if float(d.get("alpha_m", -1)) < 0 or float(d.get("beta_k", -1)) < 0:
        return "ERR_DAMPING_INVALID"
    if float(d.get("time_step_dt", 0)) <= 0:
        return "ERR_DT_INVALID"
    return "PASS"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/dynamics_boundary_report.json")
    args = p.parse_args()

    payload = sample_payload()
    code = validate(payload)
    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interface_version": INTERFACE_VERSION,
        "supports_summary": {
            "node_count": len(payload["nodes"]),
            "support_types": sorted({n["support_type"] for n in payload["nodes"]}),
            "fixed_count": sum(1 for n in payload["nodes"] if n["is_fixed_mask"]),
        },
        "damping_summary": payload["dynamics"],
        "contract_pass": code == "PASS",
        "reason_code": code,
        "reason": REASON[code],
        "payload": payload,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote dynamics boundary report: {out}")
    if code != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
