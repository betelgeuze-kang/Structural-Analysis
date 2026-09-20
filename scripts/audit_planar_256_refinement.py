"""Compare the fixed 128-layer history to the full 256-layer observation."""

import argparse
import json
import math
from pathlib import Path

from scripts.audit_planar_concrete_localization import (
    SOURCES,
    cell_metrics,
    read_checked,
    require,
    sections,
    validate_path,
)

PROTOCOL_SHA256 = "9f28f6fe758a6aebea9852bc2a48ec747479645b85db5153cbed540650de9e3a"
CONCRETE = (
    "tensile_history_strain",
    "compressive_history_strain",
    "tensile_damage",
    "compressive_damage",
    "dissipated_energy_density_mj_per_m3",
    "stress_mpa",
)
STEEL = (
    "plastic_strain",
    "accumulated_plastic_strain",
    "backstress_mpa",
    "dissipated_energy_density_mj_per_m3",
    "steel_stress_mpa",
)


def metric(coarse, fine, floor):
    require(bool(coarse) and len(coarse) == len(fine), "group correspondence mismatch")
    require(
        all(type(v) in (int, float) and math.isfinite(v) for v in coarse + fine),
        "finite group values required",
    )
    differences = [abs(a - b) for a, b in zip(coarse, fine, strict=True)]
    diff, norm = max(differences), max(abs(v) for v in fine)
    relative = diff / max(norm, floor)
    return {
        "absolute_difference": diff,
        "finer_infinity_norm": norm,
        "denominator_floor": floor,
        "relative_group_difference": relative,
        "within_exploratory_one_percent": relative <= 0.01,
        "witness_index": differences.index(diff),
    }


def nodal_steel(step, layers):
    gates = (
        "solver_contract_pass",
        "residual_gate_passed",
        "control_gate_passed",
        "increment_gate_passed",
        "parent_checkpoint_immutable",
        "section_and_element_parent_binding_passed",
        "solver_assembly_coordinate_residual_binding_passed",
    )
    require(
        all(step["metrics"][g] is True for g in gates),
        "accepted numerical gates failed",
    )
    steel = {}
    for member in step["trial_assembly"]["member_assemblies"]:
        mid = member["member_id"]
        beam = member["element_response"]["fiber_beam_response"]
        for j, section in enumerate(beam["section_responses"]):
            for i in (layers, layers + 1):
                fiber, response = (
                    section["trial_state"]["fiber_states"][i],
                    section["fiber_responses"][i],
                )
                require(fiber == response["trial_state"], "steel binding mismatch")
                key = f"{mid}:{j}:{i - layers}"
                require(key not in steel, "duplicate steel identity")
                steel[key] = {
                    k: response["stress_mpa"] if k == "steel_stress_mpa" else fiber[k]
                    for k in STEEL
                }
    require(len(steel) == 36, "expected 36 steel points")
    assembly = step["trial_assembly"]
    u, r = assembly["global_displacements"], assembly["reactions_global"]
    require(len(u) == len(r) == 18, "fixed model requires 18 DOFs")
    groups = {
        "translations": [v for i, v in enumerate(u) if i % 3 < 2],
        "rotations": [v for i, v in enumerate(u) if i % 3 == 2],
        "support_forces": [v for i, v in enumerate(r) if i % 3 < 2],
        "support_moments": [v for i, v in enumerate(r) if i % 3 == 2],
        "load_factor": [step["metrics"]["solved_load_factor"]],
    }
    groups.update({k: [steel[p][k] for p in sorted(steel)] for k in STEEL})
    return sorted(steel), groups


def step_features(steps, layers):
    """Keep only comparison values after callers validate the accepted path."""
    targets = [i / 500 for i in range(1, 41)]
    require(
        [s["metrics"]["target_control_displacement_m"] for s in steps] == targets,
        "full forty targets required",
    )
    return [
        {"target_m": target, "sections": sections(step, layers, CONCRETE),
         "nodal_steel": nodal_steel(step, layers)}
        for target, step in zip(targets, steps, strict=True)
    ]


def compare_steps(coarse, fine, coarse_layers):
    require(type(coarse_layers) is int and coarse_layers in (128, 256, 512, 1024),
            "fixed comparison layer count required")
    return compare_features(step_features(coarse, coarse_layers),
                            step_features(fine, 2 * coarse_layers), coarse_layers)


def compare_features(coarse, fine, coarse_layers):
    require(type(coarse_layers) is int and coarse_layers in (128, 256, 512, 1024),
            "fixed comparison layer count required")
    targets = [i / 500 for i in range(1, 41)]
    for features in (coarse, fine):
        require([row['target_m'] for row in features] == targets,
                "full forty targets required")
    rows = []
    for target, a, b in zip(targets, coarse, fine, strict=True):
        aa, bb = a["sections"], b["sections"]
        require(set(aa) == set(bb), "section correspondence mismatch")
        for key in aa:
            require(
                (aa[key]["xi"], aa[key]["weight"])
                == (bb[key]["xi"], bb[key]["weight"]),
                "integration mismatch",
            )
        ak, ag = a["nodal_steel"]
        bk, bg = b["nodal_steel"]
        require(ak == bk, "steel correspondence mismatch")
        metrics = {
            k: metric(
                ag[k],
                bg[k],
                1e-9
                if k
                in (
                    "support_forces",
                    "support_moments",
                    "backstress_mpa",
                    "steel_stress_mpa",
                )
                else 1e-12,
            )
            for k in ag
        }
        concrete = {}
        for field in CONCRETE:
            av, bv, keys = [], [], []
            localization = {}
            for key in sorted(aa):
                ac = [v[field] for v in aa[key]["values"]]
                bf = [v[field] for v in bb[key]["values"]]
                av.extend(ac)
                bv.extend((bf[2 * i] + bf[2 * i + 1]) / 2 for i in range(coarse_layers))
                keys.extend((key, i) for i in range(coarse_layers))
                if field in ("tensile_damage", "compressive_damage"):
                    m = cell_metrics(ac, bf)
                    del m["cell_absolute_differences"], m["cell_mixed_onset_children"]
                    localization[key] = m
            result = metric(av, bv, 1e-9 if field == "stress_mpa" else 1e-12)
            result["witness_section"], result["witness_cell"] = keys[
                result["witness_index"]
            ]
            result["cells_above_original_one_percent_norm"] = sum(
                abs(x - y)
                > 0.01 * max(result["finer_infinity_norm"], result["denominator_floor"])
                for x, y in zip(av, bv, strict=True)
            )
            result["cells"] = len(av)
            if localization:
                result["section_localization"] = localization
            concrete[field] = result
        rows.append({"target_m": target, "nodal_steel": metrics, "concrete": concrete})
    maxima = {
        kind: {
            field: max(
                (
                    {
                        "target_m": r["target_m"],
                        **{
                            k: v
                            for k, v in r[kind][field].items()
                            if k != "section_localization"
                        },
                    }
                    for r in rows
                ),
                key=lambda x: x["relative_group_difference"],
            )
            for field in rows[0][kind]
        }
        for kind in ("nodal_steel", "concrete")
    }
    return rows, maxima


def audit(original_parent, fine_root, fine_sha256):
    protocol = read_checked(fine_root / "protocol.json", PROTOCOL_SHA256)
    require(protocol["concrete_layer_count"] == 256, "fixed fine layer count required")
    paths = {
        key: read_checked(
            original_parent / SOURCES[key][0] / "repeat-0.json", SOURCES[key][1]
        )
        for key in ("prefix", "suffix")
    }
    paths["fine"] = read_checked(
        fine_root / "repeat-0.json", fine_sha256, maximum_bytes=2 * 1024**3
    )
    for path in paths.values():
        validate_path(path)
        require(path["control_global_dof"] == 15, "control DOF mismatch")
    require(
        paths["prefix"]["final_checkpoint"] == paths["suffix"]["initial_checkpoint"],
        "restart mismatch",
    )
    coarse, fine = (
        paths["prefix"]["steps"] + paths["suffix"]["steps"],
        paths["fine"]["steps"],
    )
    rows, maxima = compare_steps(coarse, fine, 128)
    return {
        "schema": "fixed-planar-128-256-comparison.v1",
        "source_revision": protocol["source_revision"],
        "source_sha256": {
            "prefix": SOURCES["prefix"][1],
            "suffix": SOURCES["suffix"][1],
            "fine": fine_sha256,
        },
        "protocol_sha256": PROTOCOL_SHA256,
        "comparison_layers": [128, 256],
        "matched_targets": 40,
        "original_group_screen": 0.01,
        "maxima": maxima,
        "comparisons": rows,
        "failed_group_counts": {
            kind: sum(
                not m["within_exploratory_one_percent"]
                for r in rows
                for m in r[kind].values()
            )
            for kind in ("nodal_steel", "concrete")
        },
        "composite_view_not_solver_artifact": True,
        "structural_solves": 0,
        "training_fits": 0,
        "independent_physical_validation": False,
        "public_api_extended": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original_parent", type=Path)
    parser.add_argument("fine_root", type=Path)
    parser.add_argument("fine_sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.original_parent, args.fine_root, args.fine_sha256)
    with args.output.open("x") as f:
        f.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
