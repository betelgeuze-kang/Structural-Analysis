"""Localize fixed 64/128-layer damage differences without new solves or gates."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)

SOURCES = {
    "coarse": (
        "structural-displacement-refinement-stpdjmzx",
        "e552852440e2ff8d98cc23a1283550c3d2dacf09de528e87794fbef22cc48932",
    ),
    "prefix": (
        "structural-plastic-onset-reference-zukafnjo",
        "bf45ac18cc8cba25df3d79df3753b8f72f27bbb6fe556629b2605942e533dcc2",
    ),
    "suffix": (
        "structural-128-resumed-displacement-tp205v5p",
        "468ab97a53f92305f0bfc84807f0fe88a773df3800255e362eff445c484f48a5",
    ),
}
FIELDS = ("tensile_damage", "compressive_damage")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_checked(path, digest):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, "source SHA-256 mismatch")
    return strict_json_object_bytes(raw, maximum_bytes=1024**3)


def validate_path(path):
    require(path["status"] == "ready" and path["contract_pass"] is True, "path failed")
    previous = path["initial_checkpoint"]
    require(
        len(path["steps"]) == len(path["target_control_displacements_m"]),
        "incomplete path",
    )
    for target, step in zip(
        path["target_control_displacements_m"], path["steps"], strict=True
    ):
        require(
            step["committed"] is True
            and step["metrics"]["solver_contract_pass"] is True,
            "step not accepted",
        )
        require(step["parent_checkpoint"] == previous, "checkpoint chain mismatch")
        require(
            step["metrics"]["target_control_displacement_m"] == target,
            "target mismatch",
        )
        previous = step["accepted_checkpoint"]
    require(path["final_checkpoint"] == previous, "final checkpoint mismatch")


def sections(step, layers):
    states = step["accepted_checkpoint"]["element_states"]
    accepted = {s["element_id"]: s for s in states}
    require(len(accepted) == len(states), "duplicate element")
    out = {}
    for member in step["trial_assembly"]["member_assemblies"]:
        mid = member["member_id"]
        element = member["element_response"]
        require(element["trial_state"] == accepted[mid], "element binding mismatch")
        beam = element["fiber_beam_response"]
        for j, (section, state, xi, weight) in enumerate(
            zip(
                beam["section_responses"],
                accepted[mid]["basic_beam_state"]["integration_point_states"],
                beam["integration_point_xi"],
                beam["integration_point_weights"],
                strict=True,
            )
        ):
            key = f"{mid}:gauss-{j}"
            require(key not in out, "duplicate section")
            require(section["trial_state"] == state, "section binding mismatch")
            require(
                len(state["fiber_states"])
                == len(section["fiber_responses"])
                == layers + 2,
                "fiber count mismatch",
            )
            values = []
            for i, (fiber, response) in enumerate(
                zip(
                    state["fiber_states"][:layers],
                    section["fiber_responses"][:layers],
                    strict=True,
                )
            ):
                require(
                    fiber["schema_version"]
                    == "uniaxial-asymmetric-concrete-damage-state.v1",
                    "concrete required",
                )
                require(response["trial_state"] == fiber, "fiber binding mismatch")
                g = section["generalized_strain"]
                y = -0.3 + (i + 0.5) * 0.6 / layers
                require(
                    math.isclose(
                        response["total_strain"],
                        g["axial_strain"] - g["curvature_z_per_m"] * y,
                        rel_tol=1e-12,
                        abs_tol=1e-14,
                    ),
                    "strain location mismatch",
                )
                values.append({field: fiber[field] for field in FIELDS})
            out[key] = {"xi": xi, "weight": weight, "values": values}
    require(len(out) == 18, "fixed model requires 18 sections")
    return out


def cell_metrics(coarse, fine):
    """Equal-area layer diagnostics. L1 is section area normalized, not volume."""
    require(
        bool(coarse) and len(fine) == 2 * len(coarse),
        "2:1 cell correspondence required",
    )
    require(
        all(
            type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 1
            for v in coarse + fine
        ),
        "finite damage in [0,1] required",
    )
    projected = [(fine[2 * i] + fine[2 * i + 1]) / 2 for i in range(len(coarse))]
    differences = [abs(a - b) for a, b in zip(coarse, projected, strict=True)]
    norm = max(max(projected), 1e-12)
    mixed = [(fine[2 * i] > 0) != (fine[2 * i + 1] > 0) for i in range(len(coarse))]
    total = math.fsum(differences)
    return {
        "cells": len(coarse),
        "section_relative_infinity_difference": max(differences) / norm,
        "section_mean_absolute_damage_difference": total / len(coarse),
        "coarse_section_mean_damage": math.fsum(coarse) / len(coarse),
        "fine_section_mean_damage": math.fsum(projected) / len(coarse),
        "cells_above_one_percent_section_norm": sum(
            d > 0.01 * norm for d in differences
        ),
        "mixed_onset_child_cells": sum(mixed),
        "mixed_onset_absolute_difference_share": math.fsum(
            d for d, m in zip(differences, mixed, strict=True) if m
        )
        / total
        if total
        else None,
        "cell_absolute_differences": differences,
        "cell_mixed_onset_children": mixed,
        "finer_projected_infinity_norm": max(projected),
    }


def audit(root):
    paths = {
        key: read_checked(root / folder / "repeat-0.json", digest)
        for key, (folder, digest) in SOURCES.items()
    }
    for path in paths.values():
        validate_path(path)
    require(
        paths["prefix"]["final_checkpoint"] == paths["suffix"]["initial_checkpoint"],
        "restart mismatch",
    )
    coarse = paths["coarse"]["steps"]
    fine = paths["prefix"]["steps"] + paths["suffix"]["steps"]
    expected = [i / 500 for i in range(1, 41)]
    require(
        [s["metrics"]["target_control_displacement_m"] for s in coarse] == expected,
        "fixed coarse targets required",
    )
    require(
        [s["metrics"]["target_control_displacement_m"] for s in fine] == expected,
        "fixed fine targets required",
    )
    rows = []
    for target, a, b in zip(expected, coarse, fine, strict=True):
        aa, bb = sections(a, 64), sections(b, 128)
        require(set(aa) == set(bb), "section correspondence mismatch")
        fields = {}
        for field in FIELDS:
            metrics = {}
            for key in sorted(aa):
                require(
                    (aa[key]["xi"], aa[key]["weight"])
                    == (bb[key]["xi"], bb[key]["weight"]),
                    "integration mismatch",
                )
                metrics[key] = cell_metrics(
                    [v[field] for v in aa[key]["values"]],
                    [v[field] for v in bb[key]["values"]],
                )
            norm = max(
                max(m["finer_projected_infinity_norm"] for m in metrics.values()), 1e-12
            )
            pairs = [
                (d, mixed)
                for m in metrics.values()
                for d, mixed in zip(
                    m["cell_absolute_differences"],
                    m["cell_mixed_onset_children"],
                    strict=True,
                )
            ]
            total = math.fsum(d for d, _ in pairs)
            fields[field] = {
                "group_relative_infinity_difference": max(d for d, _ in pairs) / norm,
                "group_cells_above_original_one_percent_norm": sum(
                    d > 0.01 * norm for d, _ in pairs
                ),
                "group_cells": len(pairs),
                "mixed_onset_absolute_difference_share": math.fsum(
                    d for d, m in pairs if m
                )
                / total
                if total
                else None,
                "sections": metrics,
            }
            for m in metrics.values():
                del m["cell_absolute_differences"], m["cell_mixed_onset_children"]
        rows.append({"target_m": target, "fields": fields})
    return {
        "schema": "fixed-planar-concrete-localization.v1",
        "source_revision": "3e2cc1dba5c6dac1b12eb1badc9b6df09337b847",
        "source_sha256": {k: v[1] for k, v in SOURCES.items()},
        "method": "Equal-area coarse midpoint versus mean of two fine children. Section mean absolute differences are not member-volume-weighted; mixed onset means exactly one fine child has positive damage. Additional descriptors do not replace the original group infinity screen.",
        "rows": rows,
        "structural_solves": 0,
        "training_fits": 0,
        "independent_physical_validation": False,
        "material_convergence_established": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
