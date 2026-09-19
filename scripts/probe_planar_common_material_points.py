"""Post-hoc common-coordinate diagnostic at two declared refinement witnesses.

This evaluates the frozen material law on accepted section-strain histories.
Derived fine-point responses are not solver-issued accepted fiber states.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from scripts.audit_planar_concrete_localization import (
    SOURCES,
    read_checked,
    require,
    validate_path,
)

FINE_SHA256 = "ae168bdad5cc4d23f0b246df39b84b1b800458033fe4ba0c9f4acaed7d98b695"
REVISION = "3e2cc1dba5c6dac1b12eb1badc9b6df09337b847"
WITNESSES = (("E3", 0, 101), ("E3", 2, 14))
FIELDS = (
    "tensile_history_strain",
    "compressive_history_strain",
    "tensile_damage",
    "compressive_damage",
    "dissipated_energy_density_mj_per_m3",
)


def material_class(root):
    path = root / "source/structural_analysis/materials/concrete_damage.py"
    raw = path.read_bytes()
    original = subprocess.check_output(
        [
            "git",
            "show",
            REVISION + ":src/structural_analysis/materials/concrete_damage.py",
        ]
    )
    require(raw == original, "frozen material source differs from Git")
    spec = importlib.util.spec_from_file_location("frozen_point_probe_concrete", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.AsymmetricConcreteDamageMaterial, hashlib.sha256(raw).hexdigest()


def section_at(step, mid, index):
    members = [
        m for m in step["trial_assembly"]["member_assemblies"] if m["member_id"] == mid
    ]
    states = [
        s
        for s in step["accepted_checkpoint"]["element_states"]
        if s["element_id"] == mid
    ]
    require(len(members) == len(states) == 1, "unique accepted member required")
    element = members[0]["element_response"]
    require(element["trial_state"] == states[0], "member binding mismatch")
    section = element["fiber_beam_response"]["section_responses"][index]
    require(
        section["trial_state"]
        == states[0]["basic_beam_state"]["integration_point_states"][index],
        "section binding mismatch",
    )
    return section


def probe(parent, fine_root):
    cls, material_sha = material_class(fine_root)
    model = read_checked(
        fine_root / "input.json",
        "34822feaee8f569712b46e5842f5fcc3253a9a851bb9a13c92624be238b4c23e",
    )
    parameters = next(
        m["parameters"] for m in model["materials"] if m["id"] == "concrete"
    )
    material = cls(
        elastic_modulus_mpa=parameters["elastic_modulus_pa"] / 1e6,
        tensile_strength_mpa=parameters["tensile_strength_pa"] / 1e6,
        compressive_strength_mpa=parameters["compressive_strength_pa"] / 1e6,
        tensile_softening_rate=parameters["tensile_softening_rate"],
        compressive_softening_rate=parameters["compressive_softening_rate"],
        history_tolerance=parameters["history_tolerance"],
    )
    paths = {
        k: read_checked(parent / SOURCES[k][0] / "repeat-0.json", SOURCES[k][1])
        for k in ("prefix", "suffix")
    }
    paths["fine"] = read_checked(
        fine_root / "repeat-0.json", FINE_SHA256, maximum_bytes=2 * 1024**3
    )
    for path in paths.values():
        validate_path(path)
    require(
        paths["prefix"]["final_checkpoint"] == paths["suffix"]["initial_checkpoint"],
        "restart mismatch",
    )
    coarse = paths["prefix"]["steps"] + paths["suffix"]["steps"]
    fine = paths["fine"]["steps"]
    require(len(coarse) == len(fine) == 40, "forty accepted targets required")
    out = []
    for mid, gauss, cell in WITNESSES:
        y = -0.3 + (cell + 0.5) * 0.6 / 128
        cp, fp = material.initial_state(), material.initial_state()
        rows = []
        for a, b in zip(coarse, fine, strict=True):
            target = a["metrics"]["target_control_displacement_m"]
            require(
                target == b["metrics"]["target_control_displacement_m"],
                "target mismatch",
            )
            ac, bc = section_at(a, mid, gauss), section_at(b, mid, gauss)
            cg, fg = ac["generalized_strain"], bc["generalized_strain"]
            ce, fe = (
                cg["axial_strain"] - cg["curvature_z_per_m"] * y,
                fg["axial_strain"] - fg["curvature_z_per_m"] * y,
            )
            cr, fr = material.integrate(ce, cp), material.integrate(fe, fp)
            cp, fp = cr.state, fr.state
            actual = ac["trial_state"]["fiber_states"][cell]
            require(
                ac["fiber_responses"][cell]["trial_state"] == actual,
                "actual fiber binding mismatch",
            )
            # Exact reproduction is required before accepting this diagnostic.
            require(cp.to_dict() == actual, "coarse witness material replay not exact")
            require(
                cr.stress_mpa == ac["fiber_responses"][cell]["stress_mpa"],
                "coarse witness stress replay not exact",
            )
            coarse_values = {
                **{k: getattr(cp, k) for k in FIELDS},
                "stress_mpa": cr.stress_mpa,
            }
            fine_values = {
                **{k: getattr(fp, k) for k in FIELDS},
                "stress_mpa": fr.stress_mpa,
            }
            rows.append(
                {
                    "target_m": target,
                    "coarse_strain": ce,
                    "derived_fine_point_strain": fe,
                    "coarse_accepted_values": coarse_values,
                    "derived_fine_point_values": fine_values,
                    "absolute_differences": {
                        k: abs(coarse_values[k] - fine_values[k]) for k in coarse_values
                    },
                }
            )
        out.append(
            {
                "member": mid,
                "gauss": gauss,
                "coarse_cell": cell,
                "y_m": y,
                "coarse_replay_exact": True,
                "rows": rows,
            }
        )
    return {
        "schema": "posthoc-common-material-point-probe.v1",
        "source_revision": REVISION,
        "material_sha256": material_sha,
        "fine_sha256": FINE_SHA256,
        "witnesses": out,
        "selection": "Two witnesses chosen from the completed 128/256 projection audit; not an untouched evaluation or all-field convergence test.",
        "derived_fine_values_are_solver_accepted_fibers": False,
        "structural_solves": 0,
        "material_integrations": 160,
        "physical_validation": False,
        "original_projection_screen_replaced": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", type=Path)
    parser.add_argument("fine_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = probe(args.parent, args.fine_root)
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
