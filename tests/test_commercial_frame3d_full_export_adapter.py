from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
for candidate in (REPO_ROOT, REPO_ROOT / "scripts", REPO_ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from build_phase4_commercial_operator_reference_ingest_validator import (  # noqa: E402
    validate_operator_reference_package,
)
from ingest_commercial_frame3d_full_export import _write_outputs_fail_closed  # noqa: E402
from structural_analysis.model_ir import canonicalize_model_ir_v2  # noqa: E402
from structural_analysis.validation.commercial_frame3d_export import (  # noqa: E402
    CommercialExportError,
    _canonical_json_bytes,
    build_comparison_ir_with_native_cli,
    build_reference_ir,
    load_json_strict,
)


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fixture(tmp_path: Path, tool: str = "midas_gen") -> tuple[Path, Path, dict, dict]:
    root = tmp_path / "operator"
    model = root / "raw" / "model.input"
    displacements = root / "raw" / "displacements.csv"
    reactions = root / "raw" / "reactions.csv"
    member_forces = root / "raw" / "member-forces.csv"
    _write(model, "operator model bytes\n")
    if tool == "midas_gen":
        _write(
            displacements,
            "Node,Load,DX,DY,DZ,RX,RY,RZ\n"
            "101,LC-A,1,2,3,0.1,0.2,0.3\n"
            "102,LC-A,4,5,6,0.4,0.5,0.6\n"
            "101,OTHER,999,999,999,9,9,9\n",
        )
        _write(
            reactions,
            "Node,Load,FX,FY,FZ,MX,MY,MZ\n"
            "101,LC-A,10,20,30,40,50,60\n"
            "102,LC-A,11,21,31,41,51,61\n",
        )
        _write(
            member_forces,
            "Element,Part,Load,FX,FY,FZ,MX,MY,MZ\n"
            "501,I,LC-A,100,200,300,400,500,600\n"
            "501,J,LC-A,101,201,301,401,501,601\n",
        )
        columns = {
            "node_id": "Node",
            "ux": "DX",
            "uy": "DY",
            "uz": "DZ",
            "rx": "RX",
            "ry": "RY",
            "rz": "RZ",
        }
        reaction_columns = {
            "node_id": "Node",
            "fx": "FX",
            "fy": "FY",
            "fz": "FZ",
            "mx": "MX",
            "my": "MY",
            "mz": "MZ",
        }
        force_columns = {
            "member_id": "Element",
            "end": "Part",
            "fx": "FX",
            "fy": "FY",
            "fz": "FZ",
            "mx": "MX",
            "my": "MY",
            "mz": "MZ",
        }
        version = "GEN-NX-2026"
    else:
        _write(
            displacements,
            "Joint,OutputCase,U1,U2,U3,R1,R2,R3\n"
            "101,LC-A,1,2,3,0.1,0.2,0.3\n"
            "102,LC-A,4,5,6,0.4,0.5,0.6\n",
        )
        _write(
            reactions,
            "Joint,OutputCase,F1,F2,F3,M1,M2,M3\n"
            "101,LC-A,10,20,30,40,50,60\n"
            "102,LC-A,11,21,31,41,51,61\n",
        )
        _write(
            member_forces,
            "Frame,End,OutputCase,P,V2,V3,T,M2,M3\n"
            "501,I,LC-A,100,200,300,400,500,600\n"
            "501,J,LC-A,101,201,301,401,501,601\n",
        )
        columns = {
            "node_id": "Joint",
            "ux": "U1",
            "uy": "U2",
            "uz": "U3",
            "rx": "R1",
            "ry": "R2",
            "rz": "R3",
        }
        reaction_columns = {
            "node_id": "Joint",
            "fx": "F1",
            "fy": "F2",
            "fz": "F3",
            "mx": "M1",
            "my": "M2",
            "mz": "M3",
        }
        force_columns = {
            "member_id": "Frame",
            "end": "End",
            "fx": "P",
            "fy": "V2",
            "fz": "V3",
            "mx": "T",
            "my": "M2",
            "mz": "M3",
        }
        version = "v26"

    raw_paths = [
        "raw/model.input",
        "raw/displacements.csv",
        "raw/reactions.csv",
        "raw/member-forces.csv",
    ]
    package = {
        "case_id": "case-a",
        "modeling_convention_id": "case-a.linear-static.v1",
        "permission_scope": {
            "comparison_use_allowed": True,
            "redistribution_allowed": False,
            "approval_receipt": "operator-ticket-123",
        },
        "reference_solvers": [
            {
                "engine_name": "MIDAS GEN NX",
                "engine_version": "GEN-NX-2026",
                "normalized_result_file": "normalized/midas.reference.json",
            },
            {
                "engine_name": "SAP2000",
                "engine_version": "v26",
                "normalized_result_file": "normalized/sap.reference.json",
            },
        ],
        "raw_input_files": [raw_paths[0]],
        "raw_result_files": raw_paths[1:],
        "file_checksums": {
            raw_paths[0]: _hash(model),
            raw_paths[1]: _hash(displacements),
            raw_paths[2]: _hash(reactions),
            raw_paths[3]: _hash(member_forces),
        },
        "modeling_convention": {
            "unit_system": "mm-kN",
            "local_axis_convention": "manifest-mapped",
            "rigid_offset_policy": "manifest-matched",
            "end_release_policy": "manifest-matched",
            "diaphragm_policy": "none",
            "mass_source_policy": "not-participating-in-static",
            "self_weight_policy": "contained-in-load-case",
            "material_modulus_convention": "same-model-map",
            "shell_formulation": "not-applicable",
            "mesh_density": "same-model-map",
            "damping_policy": "not-applicable",
            "p_delta_policy": "disabled",
            "eigen_solver": "not-applicable",
            "load_combinations": ["LC-A"],
            "convergence_tolerance": "direct-linear-solve",
        },
        "unsupported_features": [],
        "warnings": [],
    }
    package_path = root / "operator-package.json"
    _write_json(package_path, package)

    model_hash = "sha256:" + "a" * 64
    identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
    table_common = {
        "encoding": "utf-8",
        "delimiter": ",",
        "header_row": 1,
        "filters": {"Load" if tool == "midas_gen" else "OutputCase": "LC-A"},
        "load_filter_column": "Load" if tool == "midas_gen" else "OutputCase",
    }
    release = [False, False, False, True, False, False]
    manifest = {
        "schema_version": "commercial-frame3d-full-result-export-adapter.v1",
        "adapter_id": f"case-a.{tool}.adapter",
        "case_id": "case-a",
        "modeling_convention_id": "case-a.linear-static.v1",
        "reference_id": f"case-a.{tool}.reference",
        "solver": {
            "tool": tool,
            "version": version,
            "run_id": f"{tool}-run-1",
            "origin": "operator_attached_external",
        },
        "bindings": {
            "model_content_hash": model_hash,
            "load_pattern_id": "LC1",
            "load_combination_id": None,
        },
        "raw_files": {
            "model_input": {"path": raw_paths[0], "sha256": package["file_checksums"][raw_paths[0]]},
            "node_displacements": {
                "path": raw_paths[1],
                "sha256": package["file_checksums"][raw_paths[1]],
            },
            "node_reactions": {
                "path": raw_paths[2],
                "sha256": package["file_checksums"][raw_paths[2]],
            },
            "member_end_forces": {
                "path": raw_paths[3],
                "sha256": package["file_checksums"][raw_paths[3]],
            },
        },
        "units": {"translation": "mm", "rotation": "rad", "force": "kN", "moment": "kN*m"},
        "axes": {
            "node_displacement_coordinate_system": "global",
            "node_reaction_coordinate_system": "global",
            "member_end_force_coordinate_system": "member_local",
            "member_end_force_action": "native_result_ir_compatible",
            "raw_global_to_canonical_transform": identity,
        },
        "entity_mapping": {
            "nodes": [
                {"external_id": "101", "canonical_id": "N1"},
                {"external_id": "102", "canonical_id": "N2"},
            ],
            "members": [
                {
                    "external_id": "501",
                    "canonical_id": "E1",
                    "raw_i_end": "I",
                    "raw_j_end": "J",
                    "raw_i_maps_to": "i",
                    "raw_local_to_canonical_transform": identity,
                }
            ],
        },
        "semantic_mapping": {
            "releases": [
                {
                    "external_member_id": "501",
                    "raw_i": release,
                    "raw_j": [False] * 6,
                    "canonical_i": release,
                    "canonical_j": [False] * 6,
                }
            ],
            "rigid_offsets": [
                {
                    "external_member_id": "501",
                    "coordinate_system": "global",
                    "raw_unit": "mm",
                    "raw_i": [10, 0, 0],
                    "raw_j": [0, 20, 0],
                    "canonical_i_m": [0.01, 0, 0],
                    "canonical_j_m": [0, 0.02, 0],
                }
            ],
            "load": {
                "external_case": "LC-A",
                "canonical_load_pattern_id": "LC1",
                "canonical_load_combination_id": None,
                "equivalent": True,
            },
            "mass_source": {
                "participates_in_static_solution": False,
                "external_definition": "default mass source ignored by linear static case",
                "canonical_definition": "mass source not consumed by Frame Alpha static solve",
                "equivalent": True,
            },
            "solver_settings": {
                "analysis_type": "linear_static",
                "geometric_nonlinearity": False,
                "material_nonlinearity": False,
                "p_delta": False,
                "shear_deformation": "timoshenko_enabled",
                "equation_solver": "vendor direct sparse",
                "equivalent": True,
            },
            "unmapped_records": [],
        },
        "tables": {
            "node_displacements": {**table_common, "path": raw_paths[1], "columns": columns},
            "node_reactions": {**table_common, "path": raw_paths[2], "columns": reaction_columns},
            "member_end_forces": {**table_common, "path": raw_paths[3], "columns": force_columns},
        },
        "unsupported_features": [],
        "warnings": [],
    }
    manifest_path = root / "adapter-manifest.json"
    _write_json(manifest_path, manifest)
    return package_path, manifest_path, package, manifest


def _native_result(tmp_path: Path) -> Path:
    value = {
        "schema_version": "structural-native-linear-frame3d-result-ir.v1",
        "result_id": "case-a.result",
        "result_kind": "linear_static_frame3d",
        "authority_profile": "bounded_native_cpu_result_candidate.v1",
        "promotion_basis": "native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1",
        "bindings": {
            "model_id": "case-a",
            "model_content_hash": "sha256:" + "a" * 64,
            "model_semantic_hash": "sha256:" + "b" * 64,
            "model_provenance_hash": "sha256:" + "c" * 64,
            "load_pattern_id": "LC1",
            "load_combination_id": None,
            "native_abi_version": 65541,
        },
        "solver": {
            "formulation": "linear_timoshenko_frame3d",
            "backend": "cpu_reference_dense",
            "residual_sign": "internal_minus_external",
            "unit_profile": "node_m_rad_force_n_nm_member_local_n_nm.v1",
        },
        "gates": {
            "native_residual_gate_passed": True,
            "free_residual_scaled_linf": 0,
            "free_residual_scaled_linf_tolerance": 1e-9,
            "global_force_balance_scaled_linf": 0,
            "global_force_balance_scaled_linf_tolerance": 1e-9,
            "global_moment_balance_scaled_linf": 0,
            "global_moment_balance_scaled_linf_tolerance": 1e-9,
            "global_resultant_gate_passed": True,
            "independent_recovery_replay_passed": True,
            "member_force_replay_scaled_linf": 0,
            "member_force_replay_scaled_linf_tolerance": 1e-9,
            "zero_prescribed_displacement_gate_passed": True,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "nodes": [
            {"node_id": "N1", "displacement_m_rad": [0] * 6, "reaction_n_nm": [0] * 6},
            {"node_id": "N2", "displacement_m_rad": [0] * 6, "reaction_n_nm": [0] * 6},
        ],
        "members": [
            {"member_id": "E1", "end_i_force_n_nm": [0] * 6, "end_j_force_n_nm": [0] * 6}
        ],
        "authority": {
            "numerical_state": "bounded_candidate",
            "convergence": "bounded_candidate",
            "displacement": "bounded_candidate",
            "reaction": "bounded_candidate",
            "member_force": "bounded_candidate",
            "engineering_design": "not_authoritative",
            "code_compliance": "not_authoritative",
            "release_readiness": "not_authoritative",
            "commercial_use": "not_authoritative",
        },
        "claim_boundary": {
            "bounded_linear_static_timoshenko_frame3d": True,
            "cpu_only": True,
            "zero_prescribed_displacement_only": True,
            "nodal_load_only": False,
            "uniform_member_load_initial_local": True,
            "self_weight_standard_gravity": True,
            "linear_load_combination_superposition": True,
            "member_end_rotational_release": True,
            "rigid_member_end_offset": True,
            "reaction_from_global_residual": True,
            "member_force_from_native_local_recovery": True,
            "independent_recovery_replay": True,
            "cpu_hip_parity_established": False,
            "external_validation_established": False,
            "workbench_e2e": False,
            "release_readiness": False,
            "commercial_claim": False,
        },
    }
    value["result_hash"] = "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()
    path = tmp_path / "native-result.json"
    _write_json(path, value)
    return path


@pytest.mark.parametrize("tool", ["midas_gen", "sap2000"])
def test_full_result_exports_normalize_to_strict_reference_ir(tmp_path: Path, tool: str) -> None:
    package_path, manifest_path, _, _ = _fixture(tmp_path, tool)

    reference, receipt = build_reference_ir(
        operator_package_path=package_path,
        adapter_manifest_path=manifest_path,
    )

    reference_schema = json.loads(
        (
            REPO_ROOT
            / "native/crates/structural-contracts/schemas/external_linear_frame3d_reference_v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    jsonschema.Draft202012Validator(reference_schema).validate(reference)
    assert reference["schema_version"] == "structural-external-linear-frame3d-reference.v1"
    assert reference["source"]["tool"] == tool
    assert reference["source"]["origin"] == "operator_attached_external"
    assert reference["source"]["export_sha256"].startswith("sha256:")
    assert reference["bindings"]["model_content_hash"] == "sha256:" + "a" * 64
    assert reference["bindings"]["load_pattern_id"] == "LC1"
    assert reference["nodes"] == [
        {"node_id": "N1", "displacement": [1.0, 2.0, 3.0, 0.1, 0.2, 0.3], "reaction": [10, 20, 30, 40, 50, 60]},
        {"node_id": "N2", "displacement": [4.0, 5.0, 6.0, 0.4, 0.5, 0.6], "reaction": [11, 21, 31, 41, 51, 61]},
    ]
    assert reference["members"] == [
        {
            "member_id": "E1",
            "end_i_force": [100, 200, 300, 400, 500, 600],
            "end_j_force": [101, 201, 301, 401, 501, 601],
        }
    ]
    assert receipt["semantic_gates"]["end_releases"] == "operator_declared_transform_consistent"
    assert receipt["semantic_gates"]["rigid_offsets"] == "operator_declared_transform_consistent"
    assert len(receipt["source_commit_sha"]) == 40
    assert receipt["adapter_implementation_sha256"].startswith("sha256:")
    assert receipt["reference_schema_sha256"].startswith("sha256:")
    expected_reference_hash = "sha256:" + hashlib.sha256(
        canonicalize_model_ir_v2(reference).encode("utf-8")
    ).hexdigest()
    assert receipt["reference_ir_canonical_sha256"] == expected_reference_hash
    assert receipt["authority"]["external_validation"] == "not_established"
    assert receipt["authority"]["comparison"] == "not_executed"
    assert receipt["trust_state"] == "untrusted_operator_preflight_only"
    assert receipt["normalization_only"] is True
    assert receipt["vendor_model_parsed_by_adapter"] is False
    assert receipt["repository_owned_trust_anchor_used"] is False
    assert receipt["caller_provided_trust_material_consumed"] is False
    assert receipt["semantic_equivalence_prerequisite_passed"] is False
    assert receipt["eligible_as_semantically_bound_comparison_input"] is False
    assert receipt["eligible_for_external_vv_credit"] is False
    assert receipt["eligible_for_promotion"] is False
    assert receipt["eligible_for_release"] is False
    assert receipt["positive_authority_path"] == {
        "status": "blocked_not_implemented",
        "repository_owned_trust_registry": False,
        "full_canonical_vendor_semantic_projection": False,
        "vendor_executable_and_runtime_manifest_byte_replay": False,
        "isolated_transitive_runtime": False,
        "blocked_reasons": [
            "repository_owned_trust_registry_not_implemented",
            "full_canonical_vendor_semantic_projection_not_implemented",
            "vendor_executable_and_runtime_manifest_byte_replay_not_implemented",
            "isolated_transitive_runtime_not_implemented",
            "independent_operator_identity_not_established",
        ],
    }


def test_axis_and_reversed_member_mapping_are_applied(tmp_path: Path) -> None:
    package_path, manifest_path, _, manifest = _fixture(tmp_path)
    transform = [[0, -1, 0], [1, 0, 0], [0, 0, 1]]
    manifest["axes"]["raw_global_to_canonical_transform"] = transform
    member = manifest["entity_mapping"]["members"][0]
    member["raw_i_maps_to"] = "j"
    member["raw_local_to_canonical_transform"] = transform
    release = manifest["semantic_mapping"]["releases"][0]
    release["canonical_i"] = release["raw_j"]
    release["canonical_j"] = [False, False, False, False, True, False]
    offset = manifest["semantic_mapping"]["rigid_offsets"][0]
    offset["canonical_i_m"] = [-0.02, 0, 0]
    offset["canonical_j_m"] = [0, 0.01, 0]
    _write_json(manifest_path, manifest)

    reference, _ = build_reference_ir(
        operator_package_path=package_path,
        adapter_manifest_path=manifest_path,
    )

    assert reference["nodes"][0]["displacement"] == [-2.0, 1.0, 3.0, -0.2, 0.1, 0.3]
    assert reference["members"][0]["end_i_force"] == [-201.0, 101.0, 301.0, -501.0, 401.0, 601.0]
    assert reference["members"][0]["end_j_force"] == [-200.0, 100.0, 300.0, -500.0, 400.0, 600.0]


def test_reference_canonical_bytes_match_rust_number_profile() -> None:
    assert _canonical_json_bytes({"integral": 1.0, "signed_zero": -0.0}) == (
        b'{"integral":1,"signed_zero":0}'
    )


def test_direct_comparison_wrapper_is_disabled_in_favor_of_distributed_cli(tmp_path: Path) -> None:
    package_path, manifest_path, _, _ = _fixture(tmp_path)
    reference, _ = build_reference_ir(
        operator_package_path=package_path,
        adapter_manifest_path=manifest_path,
    )
    result_path = _native_result(tmp_path)
    fake_cli = tmp_path / "fake-structural-cli"
    _write(
        fake_cli,
        "#!/bin/sh\nprintf '%s\\n' '{\"schema_version\":\"structural-native-linear-frame3d-comparison-ir.v1\"}'\n",
    )
    fake_cli.chmod(0o755)

    with pytest.raises(CommercialExportError) as raised:
        build_comparison_ir_with_native_cli(
            reference_ir=reference,
            native_result_path=result_path,
            native_result_sha256=_hash(result_path),
            structural_cli_path=fake_cli,
            structural_cli_sha256=_hash(fake_cli),
            comparison_id="case-a.fake",
        )

    assert raised.value.code == "direct_comparison_wrapper_disabled"


@pytest.mark.parametrize(
    ("mutation", "error_code"),
    [
        (lambda manifest: manifest["semantic_mapping"]["releases"][0].__setitem__("canonical_i", [False] * 6), "release_mapping_not_equivalent"),
        (lambda manifest: manifest["semantic_mapping"]["rigid_offsets"][0].__setitem__("canonical_i_m", [999, 0, 0]), "offset_mapping_not_equivalent"),
        (lambda manifest: manifest["semantic_mapping"]["mass_source"].__setitem__("participates_in_static_solution", True), "mass_source_affects_static_solution"),
        (lambda manifest: manifest["semantic_mapping"]["solver_settings"].__setitem__("p_delta", True), "solver_setting_unsupported"),
        (lambda manifest: manifest["semantic_mapping"]["releases"][0]["raw_i"].__setitem__(0, True), "translational_release_unsupported"),
        (lambda manifest: manifest.__setitem__("unsupported_features", ["shell-result-row"]), "unsupported_features_present"),
    ],
)
def test_semantic_mismatches_fail_closed(tmp_path: Path, mutation, error_code: str) -> None:
    package_path, manifest_path, _, manifest = _fixture(tmp_path)
    mutation(manifest)
    _write_json(manifest_path, manifest)

    with pytest.raises(CommercialExportError, match=error_code) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == error_code


def test_unknown_or_duplicate_result_rows_fail_closed(tmp_path: Path) -> None:
    package_path, manifest_path, package, manifest = _fixture(tmp_path)
    displacement_path = package_path.parent / "raw/displacements.csv"
    with displacement_path.open("a", encoding="utf-8") as handle:
        handle.write("999,LC-A,1,2,3,4,5,6\n")
    new_hash = _hash(displacement_path)
    package["file_checksums"]["raw/displacements.csv"] = new_hash
    manifest["raw_files"]["node_displacements"]["sha256"] = new_hash
    _write_json(package_path, package)
    _write_json(manifest_path, manifest)

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "unknown_external_node"


def test_raw_checksum_tamper_fails_before_parsing(tmp_path: Path) -> None:
    package_path, manifest_path, _, _ = _fixture(tmp_path)
    with (package_path.parent / "raw/reactions.csv").open("a", encoding="utf-8") as handle:
        handle.write("tamper\n")

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "operator_package_raw_preflight_failed"
    assert "checksum_mismatch:raw/reactions.csv" in raised.value.detail


def test_operator_package_unsupported_feature_fails_raw_preflight(tmp_path: Path) -> None:
    package_path, manifest_path, package, _ = _fixture(tmp_path)
    package["unsupported_features"] = ["diaphragm-constraint"]
    _write_json(package_path, package)

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "operator_package_raw_preflight_failed"
    assert "unsupported_features_present" in raised.value.detail


def test_operator_package_escape_and_symlink_escape_fail_closed(tmp_path: Path) -> None:
    package_path, manifest_path, package, manifest = _fixture(tmp_path)
    outside = tmp_path / "outside.csv"
    _write(outside, "secret\n")
    link = package_path.parent / "raw/escape.csv"
    link.symlink_to(outside)
    package["raw_result_files"][0] = "raw/escape.csv"
    package["file_checksums"]["raw/escape.csv"] = _hash(outside)
    manifest["raw_files"]["node_displacements"] = {
        "path": "raw/escape.csv",
        "sha256": _hash(outside),
    }
    manifest["tables"]["node_displacements"]["path"] = "raw/escape.csv"
    _write_json(package_path, package)
    _write_json(manifest_path, manifest)

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "operator_package_raw_preflight_failed"
    assert "operator_file_outside_package:raw/escape.csv" in raised.value.detail


def test_generic_validator_default_still_requires_normalized_results(tmp_path: Path) -> None:
    package_path, _, package, _ = _fixture(tmp_path)

    raw = validate_operator_reference_package(
        package,
        package_root=package_path.parent,
        verify_file_hashes=True,
        require_normalized_results=False,
    )
    complete = validate_operator_reference_package(
        package,
        package_root=package_path.parent,
        verify_file_hashes=True,
    )

    assert raw["status"] == "raw_preflight_pass"
    assert raw["raw_preflight_pass"] is True
    assert raw["contract_pass"] is False
    assert any(item.startswith("checksum_missing:normalized/") for item in complete["blockers"])


def test_one_solver_can_normalize_but_does_not_pass_final_phase4_preflight(tmp_path: Path) -> None:
    package_path, manifest_path, package, _ = _fixture(tmp_path, "midas_gen")
    package["reference_solvers"] = package["reference_solvers"][:1]
    _write_json(package_path, package)

    reference, receipt = build_reference_ir(
        operator_package_path=package_path,
        adapter_manifest_path=manifest_path,
    )
    final_preflight = validate_operator_reference_package(
        package,
        package_root=package_path.parent,
        verify_file_hashes=True,
    )

    assert reference["source"]["tool"] == "midas_gen"
    assert receipt["authority"]["external_validation"] == "not_established"
    assert "two_reference_solver_comparison_not_available" in final_preflight["blockers"]


def test_duplicate_manifest_key_fails_closed(tmp_path: Path) -> None:
    package_path, manifest_path, _, _ = _fixture(tmp_path)
    text = manifest_path.read_text(encoding="utf-8")
    manifest_path.write_text(text.replace("{", '{"schema_version":"duplicate",', 1), encoding="utf-8")

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "duplicate_json_key"


@pytest.mark.parametrize(
    ("payload", "error_code"),
    [
        ('{"a":1,"a":2}', "duplicate_json_key"),
        ('{"a":NaN}', "non_finite_json_number"),
        ('{"a":Infinity}', "non_finite_json_number"),
        ('{"a":1e9999}', "json_number_overflow"),
        ('{"a":-1e9999}', "json_number_overflow"),
        ('{"a":9223372036854775808}', "json_integer_out_of_range"),
    ],
)
def test_strict_json_rejects_duplicate_nonfinite_and_overflow(
    tmp_path: Path, payload: str, error_code: str
) -> None:
    path = tmp_path / "malicious.json"
    _write(path, payload)

    with pytest.raises(CommercialExportError) as raised:
        load_json_strict(path)

    assert raised.value.code == error_code


def test_arbitrary_model_and_caller_key_material_never_create_vv_credit(tmp_path: Path) -> None:
    package_path, manifest_path, package, manifest = _fixture(tmp_path)
    model_path = package_path.parent / "raw/model.input"
    model_path.write_bytes(b"NOT A MIDAS OR SAP MODEL\x00UNTRUSTED\n")
    model_hash = _hash(model_path)
    package["file_checksums"]["raw/model.input"] = model_hash
    package["claimed_trust_registry"] = {
        "public_key": "attacker-controlled-key",
        "semantic_equivalence": True,
        "promotion_eligible": True,
    }
    package["semantic_equivalence_receipt"] = {
        "signature_valid": True,
        "independent_reviewer": "self-declared",
    }
    manifest["raw_files"]["model_input"]["sha256"] = model_hash
    _write_json(package_path, package)
    _write_json(manifest_path, manifest)

    _, receipt = build_reference_ir(
        operator_package_path=package_path,
        adapter_manifest_path=manifest_path,
    )

    assert receipt["vendor_model_parsed_by_adapter"] is False
    assert receipt["caller_provided_trust_material_consumed"] is False
    assert receipt["semantic_equivalence_prerequisite_passed"] is False
    assert receipt["eligible_as_semantically_bound_comparison_input"] is False
    assert receipt["eligible_for_external_vv_credit"] is False
    assert receipt["eligible_for_promotion"] is False
    assert receipt["eligible_for_release"] is False


def test_in_root_raw_symlink_is_rejected_even_when_bytes_match(tmp_path: Path) -> None:
    package_path, manifest_path, package, manifest = _fixture(tmp_path)
    target = package_path.parent / "raw/displacements-target.csv"
    original = package_path.parent / "raw/displacements.csv"
    target.write_bytes(original.read_bytes())
    link = package_path.parent / "raw/displacements-link.csv"
    link.symlink_to(target.name)
    checksum = _hash(target)
    package["raw_result_files"][0] = "raw/displacements-link.csv"
    package["file_checksums"]["raw/displacements-link.csv"] = checksum
    manifest["raw_files"]["node_displacements"] = {
        "path": "raw/displacements-link.csv",
        "sha256": checksum,
    }
    manifest["tables"]["node_displacements"]["path"] = "raw/displacements-link.csv"
    _write_json(package_path, package)
    _write_json(manifest_path, manifest)

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "operator_package_raw_preflight_failed"
    assert "operator_file_outside_package:raw/displacements-link.csv" in raised.value.detail


def test_control_character_in_solver_version_fails_before_reference_ir(tmp_path: Path) -> None:
    package_path, manifest_path, _, manifest = _fixture(tmp_path)
    manifest["solver"]["version"] = "GEN\u0007NX"
    _write_json(manifest_path, manifest)

    with pytest.raises(CommercialExportError) as raised:
        build_reference_ir(operator_package_path=package_path, adapter_manifest_path=manifest_path)

    assert raised.value.code == "string_control_character"


def test_cli_writes_no_overwrite_reference_and_receipt(tmp_path: Path) -> None:
    package_path, manifest_path, _, _ = _fixture(tmp_path, "sap2000")
    reference_out = tmp_path / "out/reference.json"
    receipt_out = tmp_path / "out/receipt.json"
    command = [
        sys.executable,
        str(REPO_ROOT / "scripts/ingest_commercial_frame3d_full_export.py"),
        "--operator-package",
        str(package_path),
        "--adapter-manifest",
        str(manifest_path),
        "--reference-out",
        str(reference_out),
        "--receipt-out",
        str(receipt_out),
    ]

    first = subprocess.run(command, check=False, capture_output=True, text=True)
    second = subprocess.run(command, check=False, capture_output=True, text=True)

    assert first.returncode == 0, first.stderr
    assert "tool=sap2000" in first.stdout
    assert "semantic-equivalence=false vv-credit=false promotion=false" in first.stdout
    assert json.loads(reference_out.read_text(encoding="utf-8"))["source"]["tool"] == "sap2000"
    assert json.loads(receipt_out.read_text(encoding="utf-8"))["authority"]["external_validation"] == (
        "not_established"
    )
    assert second.returncode == 1
    assert "output_exists" in second.stderr


def test_multi_output_commit_failure_removes_partial_artifacts(tmp_path: Path, monkeypatch) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    real_link = __import__("os").link
    calls = 0

    def fail_second_link(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second-output failure")
        real_link(source, target)

    monkeypatch.setattr("ingest_commercial_frame3d_full_export.os.link", fail_second_link)

    with pytest.raises(OSError, match="simulated"):
        _write_outputs_fail_closed([(first, {"a": 1}), (second, {"b": 2})])

    assert not first.exists()
    assert not second.exists()
    assert list(tmp_path.glob("*.tmp")) == []
