#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def vec_norm(x: float, y: float, z: float) -> float:
    return math.sqrt(x * x + y * y + z * z)


def make_sample_payload(steps: int) -> dict:
    fx, fy, fz = 12.0, -3.2, 1.8
    payload = {
        "nodes": [
            {
                "node_id": "N1",
                "ux": 0.0,
                "uy": 0.0,
                "uz": 0.0,
                "f_unbalanced": {
                    "fx": 0.0,
                    "fy": 0.0,
                    "fz": 0.0,
                    "norm": 0.0,
                },
                "bc_type": "fixed",
            },
            {
                "node_id": "N2",
                "ux": 0.0013,
                "uy": -0.0008,
                "uz": 0.0004,
                "f_unbalanced": {
                    "fx": fx,
                    "fy": fy,
                    "fz": fz,
                    "norm": vec_norm(fx, fy, fz),
                },
                "bc_type": "free",
            },
        ],
        "edges": [
            {
                "edge_id": "E1",
                "from": "N1",
                "to": "N2",
                "axial_force": 221.4,
                "shear_force": 43.9,
                "moment": 18.3,
                "local_stiffness": 1.27e7,
                "yield_index": 0.62,
            }
        ],
        "meta": {
            "unit_system": "SI",
            "residual_force_tolerance": 1e-3,
            "solver": "FIRE",
            "converged": True,
            "steps": steps,
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="implementation/phase1/lf_output_sample.json")
    parser.add_argument("--steps", type=int, default=120)
    args = parser.parse_args()

    payload = make_sample_payload(args.steps)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote sample LF output to: {out_path}")


if __name__ == "__main__":
    main()
