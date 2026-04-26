#!/usr/bin/env python3
"""Generate and statically validate dynamics/boundary contract artifact (Step 1).

Supports domain types: building, track, tunnel, coupled.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

INTERFACE_VERSION = "1.1.0"
SCHEMA_VERSION = "1.2"
RUN_ID = "phase1-dynamics-boundary-contract"

VALID_SUPPORT_TYPES = {
    "fixed", "hinge", "roller", "free",
    "elastic_foundation", "segment_joint", "rail_fastener",
}
VALID_DAMPING_MODELS = {"rayleigh", "modal", "none", "track_vti", "tunnel_ssi"}
VALID_FORCE_PROFILES = {
    "dead", "wind", "seismic", "combined",
    "train_passage", "track_irregularity", "tunnel_pressure_wave",
}
VALID_DOMAIN_TYPES = {"building", "track", "tunnel", "coupled"}

REASON = {
    "PASS": "contract satisfies required boundary/dynamics keys",
    "ERR_NODE_FIELD_MISSING": "node missing required field",
    "ERR_SUPPORT_TYPE_INVALID": "support_type not in enum",
    "ERR_DAMPING_INVALID": "damping parameters invalid",
    "ERR_DT_INVALID": "time_step_dt must be > 0",
    "ERR_DOMAIN_TYPE_MISSING": "domain_type missing or invalid",
    "ERR_VEHICLE_REF_MISSING": "domain=track/coupled but vehicle reference missing",
    "ERR_TUNNEL_REF_MISSING": "domain=tunnel/coupled but tunnel reference missing",
    "ERR_FOUNDATION_STIFFNESS_INVALID": "elastic_foundation node has missing/negative stiffness",
    "ERR_IMPEDANCE_RANGE_INVALID": "frequency-dependent impedance range error",
}


# ---------------------------------------------------------------------------
# Sample payloads per domain
# ---------------------------------------------------------------------------

def sample_payload_building() -> dict:
    return {
        "interface_version": INTERFACE_VERSION,
        "domain_type": "building",
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


def sample_payload_track() -> dict:
    return {
        "interface_version": INTERFACE_VERSION,
        "domain_type": "track",
        "nodes": [
            {
                "node_id": "R1",
                "mass": 60.34,
                "is_fixed_mask": False,
                "support_type": "elastic_foundation",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": True},
                "foundation_stiffness": {
                    "k_vertical": 1.3e8,
                    "k_shear": 5.0e6,
                    "c_vertical": 5.0e4,
                },
            },
            {
                "node_id": "R2",
                "mass": 60.34,
                "is_fixed_mask": False,
                "support_type": "rail_fastener",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": True},
            },
            {
                "node_id": "R3",
                "mass": 300.0,
                "is_fixed_mask": True,
                "support_type": "fixed",
                "dof_lock": {"ux": True, "uy": True, "uz": True, "rx": True, "ry": True, "rz": True},
            },
        ],
        "dynamics": {
            "damping_model": "track_vti",
            "alpha_m": 0.01,
            "beta_k": 0.0005,
            "time_step_dt": 0.0005,
            "external_force_profile": "train_passage",
        },
        "vehicle": {
            "vehicle_schema_ref": "vehicle_model_schema.json",
        },
    }


def sample_payload_tunnel() -> dict:
    return {
        "interface_version": INTERFACE_VERSION,
        "domain_type": "tunnel",
        "nodes": [
            {
                "node_id": "T1",
                "mass": 8500.0,
                "is_fixed_mask": False,
                "support_type": "segment_joint",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False},
            },
            {
                "node_id": "T2",
                "mass": 8500.0,
                "is_fixed_mask": False,
                "support_type": "elastic_foundation",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False},
                "foundation_stiffness": {
                    "k_vertical": 5.0e7,
                    "k_shear": 2.0e7,
                    "c_vertical": 1.0e5,
                },
            },
        ],
        "dynamics": {
            "damping_model": "tunnel_ssi",
            "alpha_m": 0.015,
            "beta_k": 0.001,
            "time_step_dt": 0.002,
            "external_force_profile": "train_passage",
        },
        "tunnel": {
            "tunnel_schema_ref": "tunnel_lining_schema.json",
        },
    }


def sample_payload_coupled() -> dict:
    return {
        "interface_version": INTERFACE_VERSION,
        "domain_type": "coupled",
        "nodes": [
            {
                "node_id": "C1_BLD",
                "mass": 4200.0,
                "is_fixed_mask": False,
                "support_type": "hinge",
                "dof_lock": {"ux": True, "uy": True, "uz": True, "rx": False, "ry": False, "rz": False},
            },
            {
                "node_id": "C2_TRK",
                "mass": 60.34,
                "is_fixed_mask": False,
                "support_type": "elastic_foundation",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": True},
                "foundation_stiffness": {
                    "k_vertical": 1.2e8,
                    "k_shear": 4.0e6,
                    "c_vertical": 4.0e4,
                },
            },
            {
                "node_id": "C3_TUN",
                "mass": 8500.0,
                "is_fixed_mask": False,
                "support_type": "segment_joint",
                "dof_lock": {"ux": False, "uy": False, "uz": False, "rx": False, "ry": False, "rz": False},
            },
        ],
        "dynamics": {
            "damping_model": "modal",
            "alpha_m": 0.01,
            "beta_k": 0.0008,
            "time_step_dt": 0.001,
            "external_force_profile": "train_passage",
        },
        "vehicle": {
            "vehicle_schema_ref": "vehicle_model_schema.json",
        },
        "tunnel": {
            "tunnel_schema_ref": "tunnel_lining_schema.json",
        },
    }


DOMAIN_SAMPLES = {
    "building": sample_payload_building,
    "track": sample_payload_track,
    "tunnel": sample_payload_tunnel,
    "coupled": sample_payload_coupled,
}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(payload: dict) -> str:
    # Domain type
    domain = payload.get("domain_type")
    if domain not in VALID_DOMAIN_TYPES:
        return "ERR_DOMAIN_TYPE_MISSING"

    # Nodes
    for n in payload.get("nodes", []):
        for k in ("node_id", "mass", "is_fixed_mask", "support_type", "dof_lock"):
            if k not in n:
                return "ERR_NODE_FIELD_MISSING"
        if n["support_type"] not in VALID_SUPPORT_TYPES:
            return "ERR_SUPPORT_TYPE_INVALID"
        # Foundation stiffness check for elastic_foundation nodes
        if n["support_type"] == "elastic_foundation":
            fs = n.get("foundation_stiffness", {})
            if not fs:
                return "ERR_FOUNDATION_STIFFNESS_INVALID"
            for key in ("k_vertical",):
                v = fs.get(key)
                if v is None or v < 0:
                    return "ERR_FOUNDATION_STIFFNESS_INVALID"

    # Dynamics
    d = payload.get("dynamics", {})
    if d.get("damping_model") not in VALID_DAMPING_MODELS:
        return "ERR_DAMPING_INVALID"
    if float(d.get("alpha_m", -1)) < 0 or float(d.get("beta_k", -1)) < 0:
        return "ERR_DAMPING_INVALID"
    if float(d.get("time_step_dt", 0)) <= 0:
        return "ERR_DT_INVALID"

    # Cross-domain reference checks
    if domain in ("track", "coupled"):
        if not payload.get("vehicle", {}).get("vehicle_schema_ref"):
            return "ERR_VEHICLE_REF_MISSING"
    if domain in ("tunnel", "coupled"):
        if not payload.get("tunnel", {}).get("tunnel_schema_ref"):
            return "ERR_TUNNEL_REF_MISSING"

    return "PASS"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="implementation/phase1/dynamics_boundary_report.json")
    p.add_argument(
        "--domain",
        choices=["building", "track", "tunnel", "coupled", "all"],
        default="all",
        help="Which domain sample(s) to generate and validate",
    )
    args = p.parse_args()

    domains = list(DOMAIN_SAMPLES.keys()) if args.domain == "all" else [args.domain]
    all_pass = True

    for domain in domains:
        payload = DOMAIN_SAMPLES[domain]()
        code = validate(payload)
        report = {
            "schema_version": SCHEMA_VERSION,
            "run_id": f"{RUN_ID}-{domain}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interface_version": INTERFACE_VERSION,
            "domain_type": domain,
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

        if args.domain == "all":
            outpath = Path(args.out).parent / f"dynamics_boundary_report.{domain}.json"
        else:
            outpath = Path(args.out)
        outpath.parent.mkdir(parents=True, exist_ok=True)
        outpath.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{domain}] {code} -> {outpath}")
        if code != "PASS":
            all_pass = False

    # Also write the combined building report to the legacy path for backward compat
    if args.domain == "all":
        payload = DOMAIN_SAMPLES["building"]()
        code = validate(payload)
        combined = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "interface_version": INTERFACE_VERSION,
            "domain_type": "building",
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
        legacy = Path(args.out)
        legacy.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")

    if not all_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
