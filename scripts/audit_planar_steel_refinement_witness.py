"""Reproduce the fixed 32/64-layer accepted steel witness; no solves or admission."""

import argparse
import hashlib
import json
from pathlib import Path


COARSE_SHA256 = "6d685a2e3d7e2b56bf21714705c2e543e94088c9da6c9e209e337cf34f81de65"
FINE_SHA256 = "e552852440e2ff8d98cc23a1283550c3d2dacf09de528e87794fbef22cc48932"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_checked(path: Path, digest: str) -> dict:
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, "source SHA-256 mismatch")
    return json.loads(raw)


def steel_points(step: dict, layers: int) -> dict:
    require(step["committed"] is True, "uncommitted step is not an observation")
    states = step["accepted_checkpoint"]["element_states"]
    accepted = {s["element_id"]: s for s in states}
    require(len(accepted) == len(states), "duplicate accepted element identity")
    out = {}
    for member in step["trial_assembly"]["member_assemblies"]:
        mid = member["member_id"]
        element = member["element_response"]
        require(
            element["trial_state"] == accepted[mid], "element state binding mismatch"
        )
        beam = element["fiber_beam_response"]
        for index, (section, state) in enumerate(
            zip(
                beam["section_responses"],
                accepted[mid]["basic_beam_state"]["integration_point_states"],
                strict=True,
            )
        ):
            require(section["trial_state"] == state, "section state binding mismatch")
            require(len(state["fiber_states"]) == layers + 2, "fiber count mismatch")
            require(
                len(section["fiber_responses"]) == layers + 2, "response count mismatch"
            )
            for i in range(layers, layers + 2):
                fiber = state["fiber_states"][i]
                response = section["fiber_responses"][i]
                require(
                    response["trial_state"] == fiber, "steel state binding mismatch"
                )
                side = "bottom" if i == layers else "top"
                key = f"{mid}:gauss-{index}:{side}"
                require(key not in out, "duplicate steel observation identity")
                out[key] = {
                    "integration_xi": beam["integration_point_xi"][index],
                    "plastic_strain": fiber["plastic_strain"],
                    "accumulated_plastic_strain": fiber["accumulated_plastic_strain"],
                    "total_strain": response["total_strain"],
                    "stress_mpa": response["stress_mpa"],
                    "yielded": response["yielded"],
                    "section_generalized_strain": section["generalized_strain"],
                }
    require(len(out) == 36, "expected 36 steel observations for the fixed model")
    return out


def audit(coarse_path: Path, fine_path: Path) -> dict:
    paths = {
        32: read_checked(coarse_path, COARSE_SHA256),
        64: read_checked(fine_path, FINE_SHA256),
    }
    observations = {}
    targets = [i / 500 for i in range(1, 41)]
    for layers, path in paths.items():
        require(
            path["status"] == "ready" and path["contract_pass"] is True, "path failed"
        )
        require(
            path["target_control_displacements_m"] == targets, "target path mismatch"
        )
        require(len(path["steps"]) == 40, "incomplete observation history")
        previous = path["initial_checkpoint"]
        points = []
        for target, step in zip(targets, path["steps"], strict=True):
            require(step["parent_checkpoint"] == previous, "checkpoint chain mismatch")
            require(
                step["metrics"]["target_control_displacement_m"] == target,
                "step target mismatch",
            )
            points.append(steel_points(step, layers))
            previous = step["accepted_checkpoint"]
        require(path["final_checkpoint"] == previous, "final checkpoint mismatch")
        observations[layers] = points
    coarse, fine = observations[32][11], observations[64][11]
    require(set(coarse) == set(fine), "steel correspondence mismatch")
    witness = max(
        coarse,
        key=lambda key: abs(
            coarse[key]["plastic_strain"] - fine[key]["plastic_strain"]
        ),
    )
    rows = []
    for index, target in enumerate(targets):
        a, b = observations[32][index], observations[64][index]
        require(set(a) == set(b), "steel correspondence mismatch")
        require(
            all(a[k]["integration_xi"] == b[k]["integration_xi"] for k in a),
            "integration location mismatch",
        )
        rows.append(
            {
                "target_m": target,
                "coarse_witness": a[witness],
                "fine_witness": b[witness],
                "coarse_yielded_points": sum(v["yielded"] for v in a.values()),
                "fine_yielded_points": sum(v["yielded"] for v in b.values()),
            }
        )
    return {
        "schema": "fixed-planar-steel-refinement-witness.v1",
        "coarse_sha256": COARSE_SHA256,
        "fine_sha256": FINE_SHA256,
        "witness": witness,
        "witness_selection_target_m": 0.024,
        "first_nonzero_witness_plastic_target_m": {
            str(layers): next(
                (
                    targets[i]
                    for i, points in enumerate(values)
                    if points[witness]["accumulated_plastic_strain"] > 0
                ),
                None,
            )
            for layers, values in observations.items()
        },
        "rows": rows,
        "accepted_state_binding_checked": True,
        "structural_solves": 0,
        "training_fits": 0,
        "training_admission_granted": False,
        "independent_physical_validation": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coarse_path", type=Path)
    parser.add_argument("fine_path", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(audit(args.coarse_path, args.fine_path), indent=2, allow_nan=False)
    )
