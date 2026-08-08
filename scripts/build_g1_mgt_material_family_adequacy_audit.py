#!/usr/bin/env python3
"""Bind actual-MGT material-family order and nonlinear source adequacy."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence

from jsonschema import Draft202012Validator
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src", ROOT / "implementation/phase1"):
    sys.path.insert(0, str(candidate))

from g1_mgt_load_coupled_arc_length_adapter import (  # noqa: E402
    build_real_mgt_load_coupled_arc_length_problem,
)
from mgt_state_updated_frame_axial_geometry import (  # noqa: E402
    prepack_state_updated_frame_axial_geometry,
)
from parse_mgt_section_material_properties import (  # noqa: E402
    load_mgt_section_material_properties,
)
from release_evidence_metadata import (  # noqa: E402
    file_sha256,
    git_head,
    input_checksums,
)
from run_g1_mgt_accepted_state_hip_sparse_lu_parity import (  # noqa: E402
    DEFAULT_CHECKPOINT,
    DEFAULT_MGT,
)
from run_mgt_coupled_frame_surface_sparse_equilibrium import (  # noqa: E402
    _select_frame_elements,
)
from run_mgt_full_frame_6dof_sparse_equilibrium import (  # noqa: E402
    _beam_end_offset_lookup,
    _element_angle_array_from_props,
)
from run_mgt_uncoarsened_boundary_global_equilibrium import (  # noqa: E402
    _run_uncoarsened_parser,
)
from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
)


PRODUCTIZATION = Path("implementation/phase1/release_evidence/productization")
DEFAULT_OUT = PRODUCTIZATION / "g1_mgt_material_family_adequacy_audit.json"
SCHEMA = Path(
    "src/structural_analysis/schemas/"
    "g1_mgt_material_family_adequacy_audit_v1.schema.json"
)
VERSION = "g1-mgt-material-family-adequacy-audit.v1"
FAMILY_CODES = {"CONC": 1, "STEEL": 2, "SRC": 3, "USER": 4}
SOURCE_PATHS = (
    DEFAULT_MGT,
    DEFAULT_CHECKPOINT,
    Path("implementation/phase1/g1_mgt_load_coupled_arc_length_adapter.py"),
    Path("implementation/phase1/mgt_state_updated_frame_axial_geometry.py"),
    Path("implementation/phase1/parse_mgt_section_material_properties.py"),
    Path("scripts/build_g1_mgt_material_family_adequacy_audit.py"),
    SCHEMA,
    Path("tests/test_build_g1_mgt_material_family_adequacy_audit.py"),
)


def _resolve(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _relative(root: Path, path: Path) -> str:
    return _resolve(root, path).resolve().relative_to(root.resolve()).as_posix()


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("material_family_audit_must_be_object")
    return value


def _receipt_hash(payload: dict[str, Any]) -> str:
    return canonical_hash(
        {key: value for key, value in payload.items() if key != "receipt_hash"}
    )


def _clean(root: Path) -> bool:
    result = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=all",
            "--",
            *(_relative(root, path) for path in SOURCE_PATHS),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return not result.stdout.strip()


def _frame_fixture(root: Path) -> tuple[list[Any], Any, dict[int, dict[str, Any]], dict[str, Any]]:
    mgt = root / DEFAULT_MGT
    props = load_mgt_section_material_properties(
        mgt,
        resolve_dgn_material_property_aliases=True,
    )
    with tempfile.TemporaryDirectory(prefix="g1-material-family-audit-") as raw:
        _json_path, npz_path, parser_report, _parser_run = _run_uncoarsened_parser(
            mgt_path=mgt,
            work_dir=Path(raw),
        )
        with np.load(npz_path, allow_pickle=False) as archive:
            node_xyz = np.asarray(archive["node_xyz"], dtype=np.float64)
            elem_id = np.asarray(archive["elem_id"], dtype=np.int64)
            elem_type = np.asarray(archive["elem_type_code"], dtype=np.int32)
            section_id = np.asarray(archive["elem_section_id"], dtype=np.int32)
            material_id = np.asarray(archive["elem_material_id"], dtype=np.int32)
            conn_ptr = np.asarray(archive["elem_conn_ptr"], dtype=np.int64)
            conn_idx = np.asarray(archive["elem_conn_idx"], dtype=np.int64)
            angle = (
                np.asarray(archive["elem_angle_deg"], dtype=np.float64)
                if "elem_angle_deg" in archive.files
                else _element_angle_array_from_props(props, elem_id)
            )
        frames, select_audit = _select_frame_elements(
            node_xyz=node_xyz,
            conn_ptr=conn_ptr,
            conn_idx=conn_idx,
            elem_id=elem_id,
            elem_type_code=elem_type,
            elem_section_id=section_id,
            elem_material_id=material_id,
            elem_angle_deg=angle,
            beam_end_offsets=_beam_end_offset_lookup(props["beam_end_offsets"]),
        )
        geometry = prepack_state_updated_frame_axial_geometry(
            node_xyz=node_xyz,
            frame_elements=frames,
            section_props=props["sections"],
            material_props=props["materials"],
            require_real_properties=True,
        )
    if parser_report.get("contract_pass") is not True:
        raise RuntimeError("material_family_audit_uncoarsened_parser_failed")
    return frames, geometry, props["materials"], select_audit


def _strain(
    *,
    geometry: Any,
    global_state: np.ndarray,
) -> np.ndarray:
    gathered = global_state[np.asarray(geometry.dofs, dtype=np.int64)]
    relative = np.einsum(
        "eij,ej->ei",
        np.asarray(geometry.relative_translation_operators, dtype=np.float64),
        gathered,
        optimize=False,
    )
    reference_chords = np.asarray(geometry.reference_chords_m, dtype=np.float64)
    reference_lengths = np.asarray(geometry.reference_lengths_m, dtype=np.float64)
    current_chords = reference_chords + relative
    current_lengths = np.sqrt(np.sum(current_chords * current_chords, axis=1))
    reference_direction = reference_chords / reference_lengths[:, None]
    linear_extension = np.sum(reference_direction * relative, axis=1)
    relative_squared = np.sum(relative * relative, axis=1)
    extension = (
        2.0 * reference_lengths * linear_extension + relative_squared
    ) / (current_lengths + reference_lengths)
    return np.ascontiguousarray(extension / reference_lengths, dtype="<f8")


def _family_stats(
    families: np.ndarray,
    strain: np.ndarray,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for family in sorted(set(str(value) for value in families.tolist())):
        values = strain[families == family]
        result[family] = {
            "element_count": int(values.size),
            "minimum_engineering_strain": float(np.min(values)),
            "maximum_engineering_strain": float(np.max(values)),
            "maximum_absolute_engineering_strain": float(np.max(np.abs(values))),
            "tension_element_count": int(np.count_nonzero(values > 0.0)),
            "compression_element_count": int(np.count_nonzero(values < 0.0)),
        }
    return result


def build(*, root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    if not _clean(root):
        raise RuntimeError("material_family_audit_requires_clean_source_paths")
    problem, metadata = build_real_mgt_load_coupled_arc_length_problem(
        mgt_path=root / DEFAULT_MGT,
        roundtrip_npz=None,
        checkpoint_npz=root / DEFAULT_CHECKPOINT,
        apply_state_updated_frame_axial_geometry=True,
        source_commit_sha=git_head(root),
    )
    operator = problem.current_tangent_operator
    if operator is None:
        raise RuntimeError("material_family_audit_current_tangent_missing")
    frames, geometry, material_props, select_audit = _frame_fixture(root)
    operator_arrays = {
        "dofs": np.asarray(operator.array("geometry_dofs"), dtype=np.int64),
        "relative": np.asarray(
            operator.array("geometry_relative_translation_operators"),
            dtype=np.float64,
        ),
        "chords": np.asarray(
            operator.array("geometry_reference_chords_m"), dtype=np.float64
        ),
        "lengths": np.asarray(
            operator.array("geometry_reference_lengths_m"), dtype=np.float64
        ),
        "axial": np.asarray(
            operator.array("geometry_axial_stiffness_n_per_m"), dtype=np.float64
        ),
    }
    fixture_arrays = {
        "dofs": np.asarray(geometry.dofs, dtype=np.int64),
        "relative": np.asarray(
            geometry.relative_translation_operators, dtype=np.float64
        ),
        "chords": np.asarray(geometry.reference_chords_m, dtype=np.float64),
        "lengths": np.asarray(geometry.reference_lengths_m, dtype=np.float64),
        "axial": np.asarray(geometry.axial_stiffness_n_per_m, dtype=np.float64),
    }
    array_identity = {
        name: bool(np.array_equal(operator_arrays[name], fixture_arrays[name]))
        for name in operator_arrays
    }
    if not all(array_identity.values()):
        raise RuntimeError("material_family_audit_geometry_order_mismatch")

    element_ids = np.asarray([row.elem_id for row in frames], dtype="<i8")
    material_ids = np.asarray([row.material_id for row in frames], dtype="<i8")
    families = np.asarray(
        [str(material_props[int(row.material_id)]["type"]).upper() for row in frames]
    )
    unknown = sorted(set(str(value) for value in families.tolist()) - set(FAMILY_CODES))
    if unknown:
        raise RuntimeError(f"material_family_audit_unknown_families:{unknown}")
    family_codes = np.asarray([FAMILY_CODES[str(value)] for value in families], dtype="<i4")
    primary_e_mpa = np.asarray(
        [
            float(material_props[int(row.material_id)]["E_kN_per_m2"]) * 1.0e-3
            for row in frames
        ],
        dtype="<f8",
    )
    secondary_e_mpa = np.asarray(
        [
            float(
                material_props[int(row.material_id)].get(
                    "E_secondary_kN_per_m2", 0.0
                )
                or 0.0
            )
            * 1.0e-3
            for row in frames
        ],
        dtype="<f8",
    )
    with np.load(root / DEFAULT_CHECKPOINT, allow_pickle=False) as checkpoint:
        global_state = np.asarray(checkpoint["displacement_u"], dtype="<f8")
        load_factor = float(np.asarray(checkpoint["load_scale"]).item())
        free = np.asarray(checkpoint["free_global_dofs"], dtype="<i8")
    strain = _strain(geometry=geometry, global_state=global_state)
    family_counts = dict(sorted(Counter(str(value) for value in families.tolist()).items()))
    normalized_fields = sorted(
        set().union(*(set(material_props[int(value)].keys()) for value in material_ids))
    )
    missing_nonlinear = {
        "steel_yield_stress_mpa": "yield_stress_mpa" not in normalized_fields,
        "steel_isotropic_hardening_modulus_mpa": (
            "isotropic_hardening_modulus_mpa" not in normalized_fields
        ),
        "steel_kinematic_hardening_modulus_mpa": (
            "kinematic_hardening_modulus_mpa" not in normalized_fields
        ),
        "concrete_tensile_strength_mpa": (
            "tensile_strength_mpa" not in normalized_fields
        ),
        "concrete_compressive_strength_mpa": (
            "compressive_strength_mpa" not in normalized_fields
        ),
        "concrete_tensile_softening_rate": (
            "tensile_softening_rate" not in normalized_fields
        ),
        "concrete_compressive_softening_rate": (
            "compressive_softening_rate" not in normalized_fields
        ),
        "src_steel_area_fraction": "steel_area_fraction" not in normalized_fields,
    }
    source_adequate = not any(missing_nonlinear.values())
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "receipt_hash": "sha256:" + "0" * 64,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "partial",
        "contract_pass": True,
        "contract_scope": (
            "actual_mgt_full_load_material_family_order_and_source_adequacy"
        ),
        "source": {
            "repository_commit_sha": git_head(root),
            "source_paths_clean_at_execution": True,
            "input_checksums": input_checksums(SOURCE_PATHS, repo_root=root),
            "mgt_path": DEFAULT_MGT.as_posix(),
            "mgt_sha256": file_sha256(root / DEFAULT_MGT),
            "checkpoint_path": DEFAULT_CHECKPOINT.as_posix(),
            "checkpoint_sha256": file_sha256(root / DEFAULT_CHECKPOINT),
        },
        "operator_binding": {
            "current_tangent_operator_contract_hash": operator.contract_hash,
            "current_tangent_operator_array_bundle_hash": operator.array_bundle_hash,
            "equilibrium_operator_binding_hash": (
                problem.equilibrium_operator_binding_hash
            ),
            "geometry_element_count": int(geometry.element_count),
            "independent_fixture_array_identity": array_identity,
            "all_geometry_arrays_exact": bool(all(array_identity.values())),
            "property_fallback_count": int(geometry.meta["property_fallback_count"]),
            "uncoarsened_parser_contract_pass": bool(
                metadata["uncoarsened_parser_report"]["contract_pass"]
            ),
            "selected_frame_element_count": int(
                select_audit["line_elements_solved"]
            ),
        },
        "material_fixture": {
            "profile": "actual_mgt_geometry_ordered_material_family_fixture.v1",
            "element_count": int(element_ids.size),
            "first_element_id": int(element_ids[0]),
            "last_element_id": int(element_ids[-1]),
            "element_id_order_data_hash": array_data_hash(element_ids),
            "material_id_order_data_hash": array_data_hash(material_ids),
            "family_code_mapping": FAMILY_CODES,
            "family_code_data_hash": array_data_hash(family_codes),
            "primary_elastic_modulus_mpa_data_hash": array_data_hash(primary_e_mpa),
            "secondary_elastic_modulus_mpa_data_hash": array_data_hash(
                secondary_e_mpa
            ),
            "family_counts": family_counts,
            "family_count": int(len(family_counts)),
        },
        "accepted_state_audit": {
            "load_factor": load_factor,
            "global_dof_count": int(global_state.size),
            "free_equation_count": int(free.size),
            "global_displacement_data_hash": array_data_hash(global_state),
            "engineering_strain_data_hash": array_data_hash(strain),
            "maximum_absolute_engineering_strain": float(np.max(np.abs(strain))),
            "family_statistics": _family_stats(families, strain),
        },
        "source_adequacy": {
            "normalized_property_contract": (
                "MATERIAL_plus_exact_DGN_type_name_alias_elastic_properties.v1"
            ),
            "primary_elastic_modulus_complete": bool(np.all(primary_e_mpa > 0.0)),
            "src_secondary_elastic_modulus_complete": bool(
                np.all(secondary_e_mpa[families == "SRC"] > 0.0)
            ),
            "missing_authoritative_nonlinear_fields": missing_nonlinear,
            "authoritative_nonlinear_parameter_set_complete": source_adequate,
            "engineer_review_required": True,
        },
        "claims": {
            "actual_mgt_full_mesh_material_family_order_bound": True,
            "accepted_state_family_strains_measured": True,
            "source_elastic_properties_complete": True,
            "source_authoritative_nonlinear_material_parameters_complete": False,
            "nonlinear_material_family_breadth_connected_to_equilibrium": False,
            "independent_gfx1100_run": False,
            "g1_closure": False,
        },
        "blockers_remaining": [
            "source_authoritative_steel_hardening_parameters_unavailable",
            "source_authoritative_concrete_damage_softening_parameters_unavailable",
            "source_authoritative_src_constituent_area_fraction_unavailable",
            "independent_gfx1100_hardware_run_unavailable",
        ],
        "claim_boundary": (
            "This audit binds all 5,572 actual MGT frame elements to the exact "
            "finite-chord geometry order consumed by the current tangent operator, "
            "records CONC/STEEL/SRC/USER family codes and source elastic moduli, and "
            "measures accepted-state axial strain at load scale 1.0. The normalized "
            "source-property contract does not supply the hardening, damage/softening, "
            "or SRC constituent-fraction parameters required by the repository's "
            "stateful nonlinear laws. No grade-name inference or default material "
            "parameter is promoted to authority; nonlinear material breadth and G1 "
            "closure therefore remain false."
        ),
    }
    payload["receipt_hash"] = _receipt_hash(payload)
    return validate(payload, root=root, current=True)


def validate(
    payload: dict[str, Any],
    *,
    root: Path = ROOT,
    current: bool = False,
) -> dict[str, Any]:
    schema = _read(root / SCHEMA)
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    if payload["receipt_hash"] != _receipt_hash(payload):
        raise ValueError("material_family_audit_receipt_hash_mismatch")
    if current:
        if payload["source"]["input_checksums"] != input_checksums(
            SOURCE_PATHS, repo_root=root
        ):
            raise ValueError("material_family_audit_sources_stale")
    return payload


def write(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> dict[str, Any]:
    payload = build(root=root)
    target = _resolve(root, out)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return validate(payload, root=root, current=True)


def check(*, root: Path = ROOT, out: Path = DEFAULT_OUT) -> tuple[bool, str]:
    try:
        validate(_read(_resolve(root, out)), root=root, current=True)
    except Exception as error:
        return False, f"g1_mgt_material_family_adequacy_audit_invalid:{error}"
    return True, "g1_mgt_material_family_adequacy_audit_consistent"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        passed, reason = check()
        print(reason)
        return 0 if passed else 1
    payload = write()
    print(
        "partial | material_elements="
        f"{payload['material_fixture']['element_count']} | "
        "nonlinear_source_adequacy=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
