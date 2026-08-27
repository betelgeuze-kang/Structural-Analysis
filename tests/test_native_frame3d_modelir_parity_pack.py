from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, ValidationError
import pytest

from structural_analysis.adapters import (
    BoundedNativeFrame3DSourceNormalizationError,
)
from structural_analysis.model_ir import parse_model_ir_v2, validate_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_native_frame3d_modelir_parity.py"
SCHEMA_V1 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v1.schema.json"
)
SCHEMA_V2 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v2.schema.json"
)
SCHEMA_V3 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v3.schema.json"
)
SCHEMA_V4 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v4.schema.json"
)
INVENTORY_SCHEMA_V2 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json"
)
INVENTORY_SCHEMA_V3 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_reference_inventory_v3.schema.json"
)
INVENTORY_SCHEMA_V4 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_reference_inventory_v4.schema.json"
)
INVENTORY_BUILDER = ROOT / "scripts/build_native_frame3d_reference_inventory.py"
SPEC = importlib.util.spec_from_file_location(
    "native_frame3d_parity_runner_tests", RUNNER
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)
INVENTORY_SPEC = importlib.util.spec_from_file_location(
    "native_frame3d_reference_inventory_tests", INVENTORY_BUILDER
)
assert INVENTORY_SPEC is not None and INVENTORY_SPEC.loader is not None
inventory_builder = importlib.util.module_from_spec(INVENTORY_SPEC)
sys.modules[INVENTORY_SPEC.name] = inventory_builder
INVENTORY_SPEC.loader.exec_module(inventory_builder)


@pytest.fixture(scope="module")
def parity_receipts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    temporary = tmp_path_factory.mktemp("native-frame3d-modelir-parity")
    target = temporary / "cargo-target"
    subprocess.run(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(ROOT / "native/Cargo.toml"),
            "--package",
            "structural-cli",
            "--locked",
            "--target-dir",
            str(target),
        ],
        cwd=ROOT,
        check=True,
        timeout=600,
    )
    executable = target / "debug/structural-cli"
    receipts: dict[str, bytes] = {}
    for profile, arguments in (
        ("v1", []),
        ("v2", ["--profile", "expanded-v2"]),
        ("v3", ["--profile", "alpha-upper-v3"]),
        ("v4", ["--profile", "pm1-core-v4"]),
    ):
        outputs = [
            temporary / f"{profile}-first.json",
            temporary / f"{profile}-second.json",
        ]
        for output in outputs:
            subprocess.run(
                [
                    "python3",
                    str(RUNNER),
                    *arguments,
                    "--structural-cli",
                    str(executable),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                timeout=120,
            )
        receipts[profile] = outputs[0].read_bytes()
        assert receipts[profile] == outputs[1].read_bytes()

    for version in ("v2", "v3", "v4"):
        inventory_outputs = [
            temporary / f"inventory-{version}-first.json",
            temporary / f"inventory-{version}-second.json",
        ]
        for output in inventory_outputs:
            subprocess.run(
                [
                    "python3",
                    str(INVENTORY_BUILDER),
                    "--parity-receipt",
                    str(temporary / f"{version}-first.json"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                timeout=60,
            )
        receipts[f"inventory-{version}"] = inventory_outputs[0].read_bytes()
        assert receipts[f"inventory-{version}"] == inventory_outputs[1].read_bytes()
    return receipts


def _validator(path: Path) -> Draft202012Validator:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_parity_pack_is_deterministic_schema_valid_and_feature_complete(
    parity_receipts: dict[str, bytes],
) -> None:
    payload = json.loads(parity_receipts["v1"])
    _validator(SCHEMA_V1).validate(payload)

    assert [case["case_id"] for case in payload["cases"]] == [
        "rotated_offset_mixed_load",
        "released_uniform_member_load",
        "nested_linear_combination",
    ]
    features = {feature for case in payload["cases"] for feature in case["features"]}
    assert {
        "self_weight",
        "rigid_end_offset",
        "rotational_release",
        "nested_linear_combination",
    } <= features
    assert payload["authority"] == {
        "implementation_verification": "bounded_cross_implementation",
        "external_code_comparison": "not_evaluated",
        "experimental_validation": "not_established",
        "engineering_design": "not_authoritative",
        "release_readiness": "not_authoritative",
    }


def test_parity_pack_schema_rejects_authority_promotion(
    parity_receipts: dict[str, bytes],
) -> None:
    promoted = deepcopy(json.loads(parity_receipts["v1"]))
    promoted["authority"]["release_readiness"] = "authoritative"

    with pytest.raises(ValidationError):
        _validator(SCHEMA_V1).validate(promoted)


def test_expanded_pack_verifies_four_multi_member_topologies(
    parity_receipts: dict[str, bytes],
) -> None:
    payload = json.loads(parity_receipts["v2"])
    _validator(SCHEMA_V2).validate(payload)

    assert [row["case_id"] for row in payload["cases"]] == [
        "rotated_offset_mixed_load",
        "released_uniform_member_load",
        "nested_linear_combination",
        "two_member_spatial_chain",
        "planar_portal_multi_support",
        "spatial_corner_roll_offset",
        "continuous_line_multiple_support",
    ]
    assert all(row["status"] == "pass" for row in payload["cases"])
    assert sum("multi_member" in row["features"] for row in payload["cases"]) == 4
    assert payload["authority"]["external_code_comparison"] == "not_evaluated"


def test_expanded_schema_pins_independent_reference_source_paths(
    parity_receipts: dict[str, bytes],
) -> None:
    payload = json.loads(parity_receipts["v2"])
    payload["reference_source_hashes"][0]["path"] = "unrelated/reference.py"

    with pytest.raises(ValidationError):
        _validator(SCHEMA_V2).validate(payload)


def test_reference_inventory_counts_only_executed_rows(
    parity_receipts: dict[str, bytes],
) -> None:
    payload = json.loads(parity_receipts["inventory-v2"])
    _validator(INVENTORY_SCHEMA_V2).validate(payload)

    assert payload["status"] == "partial"
    assert payload["target_case_count"] == 60
    assert payload["verified_case_count"] == 7
    assert payload["remaining_case_count"] == 53
    assert len(payload["cases"]) == 60
    assert sum(row["credit_eligible"] for row in payload["cases"]) == 7
    assert payload["alpha_upper_envelope"]["verified_case_count"] == 0
    assert payload["authority"]["commercial_code_comparison"] == "not_evaluated"


def test_alpha_upper_pack_and_inventory_verify_five_bounded_cases(
    parity_receipts: dict[str, bytes],
) -> None:
    parity = json.loads(parity_receipts["v3"])
    _validator(SCHEMA_V3).validate(parity)
    assert [row["case_id"] for row in parity["cases"][-5:]] == [
        "alpha_upper_moment_frame",
        "alpha_upper_braced_frame",
        "alpha_upper_irregular_spatial",
        "alpha_upper_multiple_support",
        "alpha_upper_mixed_feature",
    ]
    assert len(parity["cases"]) == 12
    assert all(row["status"] == "pass" for row in parity["cases"])
    assert "not_industry_medium" in parity["claim_boundary"]

    inventory = json.loads(parity_receipts["inventory-v3"])
    _validator(INVENTORY_SCHEMA_V3).validate(inventory)
    assert inventory["verified_case_count"] == 12
    assert inventory["remaining_case_count"] == 48
    assert inventory["alpha_upper_envelope"]["verified_case_count"] == 5
    assert sum(row["credit_eligible"] for row in inventory["cases"]) == 12
    assert inventory["authority"]["commercial_code_comparison"] == "not_evaluated"


def test_alpha_upper_schema_pins_order_sources_and_authority(
    parity_receipts: dict[str, bytes],
) -> None:
    payload = json.loads(parity_receipts["v3"])
    payload["cases"][7], payload["cases"][8] = payload["cases"][8], payload["cases"][7]
    with pytest.raises(ValidationError):
        _validator(SCHEMA_V3).validate(payload)

    payload = json.loads(parity_receipts["v3"])
    payload["reference_source_hashes"][2]["path"] = "unrelated/runner.py"
    with pytest.raises(ValidationError):
        _validator(SCHEMA_V3).validate(payload)

    payload = json.loads(parity_receipts["v3"])
    payload["authority"]["external_code_comparison"] = "pass"
    with pytest.raises(ValidationError):
        _validator(SCHEMA_V3).validate(payload)


def test_pm1_core_v4_closes_basic_and_negative_metamorphic_families(
    parity_receipts: dict[str, bytes],
) -> None:
    parity = json.loads(parity_receipts["v4"])
    _validator(SCHEMA_V4).validate(parity)

    assert len(parity["cases"]) == 32
    assert parity["verification_summary"] == {
        "numerical_differential_count": 20,
        "basic_closed_form_count": 8,
        "metamorphic_invariance_count": 8,
        "fail_closed_negative_count": 4,
        "verified_case_count": 32,
        "family_verified_counts": {
            "basic_response": 12,
            "orientation_local_axis": 3,
            "member_load_self_weight": 1,
            "release_rigid_offset": 3,
            "load_combination": 1,
            "negative_metamorphic": 12,
        },
    }
    basic = parity["cases"][12:20]
    assert [row["case_id"] for row in basic] == list(
        inventory_builder.FAMILIES["basic_response"][:8]
    )
    assert all(
        row["analytic_checks"]["tip_displacement_scaled_linf"] <= 5.0e-9
        and row["analytic_checks"]["base_reaction_scaled_linf"] <= 5.0e-9
        for row in basic
    )

    metamorphic = parity["cases"][20:28]
    assert [row["case_id"] for row in metamorphic] == list(
        inventory_builder.FAMILIES["negative_metamorphic"][:8]
    )
    assert all(
        row["verification_kind"] == "metamorphic_invariance" for row in metamorphic
    )
    assert all(
        row["checks"]["displacement_scaled_linf"] <= 1.0e-8
        and row["checks"]["reaction_scaled_linf"] <= 1.0e-8
        for row in metamorphic
    )
    assert (
        sum(
            row["checks"]["member_force_policy"] == "direct_local"
            for row in metamorphic
        )
        == 6
    )
    replay = metamorphic[-1]["checks"]
    assert replay["model_identity"] == "same"
    assert replay["result_identity"] == "same"
    assert replay["native_payload_identity"] == "same"

    unit_conversion = metamorphic[3]
    assert unit_conversion["checks"]["model_identity"] == "different"
    assert unit_conversion["checks"]["model_semantic_identity"] == "same"
    assert unit_conversion["checks"]["model_provenance_identity"] == "different"
    normalization = unit_conversion["source_normalization"]
    assert (
        normalization["normalized_model_content_hash"]
        == unit_conversion["transformed"]["model_content_hash"]
    )
    assert (
        normalization["normalized_model_semantic_hash"]
        == unit_conversion["baseline"]["model_semantic_hash"]
    )
    assert (
        normalization["normalized_model_semantic_hash"]
        == unit_conversion["transformed"]["model_semantic_hash"]
    )
    assert (
        normalization["normalized_model_provenance_hash"]
        == unit_conversion["transformed"]["model_provenance_hash"]
    )
    assert normalization["unit_conversions"]["length_mm_to_m"] == 1.0e-3
    assert normalization["unit_conversions"]["moment_n_mm_to_n_m"] == 1.0e-3

    negative = parity["cases"][28:]
    assert [row["case_id"] for row in negative] == list(
        inventory_builder.FAMILIES["negative_metamorphic"][-4:]
    )
    assert all(row["verification_kind"] == "fail_closed_negative" for row in negative)
    assert all(row["replay_byte_identical"] for row in negative)
    assert all(row["result_emitted"] is False for row in negative)
    assert [
        (
            row["observed"]["exit_code"],
            row["observed"]["issue_code"],
            row["observed"]["issue_path"],
            row["observed"]["native_status_code"],
        )
        for row in negative
    ] == [
        (1, "native_runtime_error", "/analysis", 1101),
        (2, "model_ir_schema_invalid", "/", None),
        (1, "native_runtime_error", "/analysis", 1101),
        (1, "native_runtime_error", "/analysis", 1102),
    ]
    root_cause = negative[0]["root_cause"]
    assert root_cause["exit_code"] == 2
    assert root_cause["failure_schema"] == "structural-model-ir-cpp-validation.v1"
    assert root_cause["issue_code"] == "duplicate_id"
    assert root_cause["issue_path"] == "/nodes"
    assert root_cause["dangling_reference_issue_count"] == 0
    assert root_cause["replay_byte_identical"] is True


def test_pm1_unit_case_uses_raw_source_normalizer_and_exact_modelir_binding() -> None:
    baseline, transformed, raw_source, normalization = runner._unit_conversion_cases()
    baseline_document = parse_model_ir_v2(baseline[2])
    transformed_document = parse_model_ir_v2(transformed[2])
    normalized = normalization.document.to_dict()

    assert raw_source["node_j"]["coordinates_mm"] == [2_000.0, 0.0, 0.0]
    assert raw_source["material"]["elastic_modulus_mpa"] == 200_000.0
    assert raw_source["load_pattern"]["nodal_load"]["moment_n_mm"] == {
        "MX": 1_200_000.0,
        "MY": -1_800_000.0,
        "MZ": 2_500_000.0,
    }
    assert normalized["nodes"][1]["coordinates_m"] == [2.0, 0.0, 0.0]
    assert normalized["materials"][0]["parameters"]["elastic_modulus_pa"] == (
        200_000_000_000.0
    )
    assert normalized["sections"][0]["parameters"] == {
        "area_m2": 0.02,
        "iy_m4": 8.0e-5,
        "iz_m4": 5.0e-5,
        "shear_area_y_m2": 0.016,
        "shear_area_z_m2": 0.016,
        "torsional_constant_m4": 1.0e-5,
    }
    assert normalized["load_patterns"][0]["nodal_loads"][0]["components_si"] == {
        "FX": 12_500.0,
        "FY": -7_000.0,
        "FZ": 9_000.0,
        "MX": 1_200.0,
        "MY": -1_800.0,
        "MZ": 2_500.0,
    }
    assert baseline_document.content_hash != transformed_document.content_hash
    assert baseline_document.semantic_hash == transformed_document.semantic_hash
    assert baseline_document.provenance_hash != transformed_document.provenance_hash
    assert normalization.raw_source_sha256 == normalized["provenance"]["source_sha256"]
    assert (
        normalization.normalized_model_content_hash == transformed_document.content_hash
    )

    changed_source = deepcopy(raw_source)
    changed_source["node_j"]["coordinates_mm"][0] = 2_500.0
    changed = runner.normalize_bounded_native_frame3d_n_mm_mpa_source_v1(changed_source)
    assert changed.raw_source_sha256 != normalization.raw_source_sha256
    assert (
        changed.normalized_model_semantic_hash
        != normalization.normalized_model_semantic_hash
    )
    assert changed.document.to_dict()["nodes"][1]["coordinates_m"][0] == 2.5

    extra_field_source = deepcopy(raw_source)
    extra_field_source["node_j"]["coordinates_m"] = [2.0, 0.0, 0.0]
    with pytest.raises(
        BoundedNativeFrame3DSourceNormalizationError,
        match="bounded_native_frame3d_source_fields_invalid@/node_j",
    ):
        runner.normalize_bounded_native_frame3d_n_mm_mpa_source_v1(extra_field_source)

    forged = replace(normalization, raw_source_sha256="sha256:" + "0" * 64)
    with pytest.raises(
        BoundedNativeFrame3DSourceNormalizationError,
        match="bounded_native_frame3d_raw_source_binding_mismatch",
    ):
        runner.validate_bounded_native_frame3d_source_normalization(
            forged,
            raw_source=raw_source,
        )


def test_duplicate_stable_id_negative_has_no_dangling_reference_competitor() -> None:
    duplicate = runner._negative_case_definitions()[0]["model"]
    node_ids = [row["id"] for row in duplicate["nodes"]]
    referenced_node_ids = {
        *(node_id for row in duplicate["elements"] for node_id in row["node_ids"]),
        *(row["node_id"] for row in duplicate["constraints"]),
        *(
            load["node_id"]
            for pattern in duplicate["load_patterns"]
            for load in pattern["nodal_loads"]
        ),
    }

    assert node_ids == ["N1", "N2", "N1"]
    assert referenced_node_ids <= set(node_ids)
    report = validate_model_ir_v2(duplicate)
    assert [(issue.code, issue.path, issue.message) for issue in report.issues] == [
        ("duplicate_id", "/nodes", "nodes id values must be unique.")
    ]


def test_pm1_core_v4_schema_rejects_credit_without_the_required_checks(
    parity_receipts: dict[str, bytes],
) -> None:
    validator = _validator(SCHEMA_V4)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][12].pop("analytic_checks")
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][20]["checks"]["displacement_scaled_linf"] = 1.1e-8
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][28]["result_emitted"] = True
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][23].pop("source_normalization")
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][28]["root_cause"]["issue_code"] = "dangling_reference"
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["cases"][28]["root_cause"]["issue_detail_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValidationError):
        validator.validate(payload)

    payload = json.loads(parity_receipts["v4"])
    payload["verification_summary"]["verified_case_count"] = 33
    with pytest.raises(ValidationError):
        validator.validate(payload)


def test_pm1_core_v4_inventory_credits_only_schema_bound_receipts(
    parity_receipts: dict[str, bytes], tmp_path: Path
) -> None:
    inventory = json.loads(parity_receipts["inventory-v4"])
    _validator(INVENTORY_SCHEMA_V4).validate(inventory)
    assert inventory["verified_case_count"] == 32
    assert inventory["remaining_case_count"] == 28
    assert inventory["family_verified_counts"]["basic_response"] == 12
    assert inventory["family_verified_counts"]["negative_metamorphic"] == 12
    assert inventory["verification_kind_counts"] == {
        "numerical_differential": 20,
        "metamorphic_invariance": 8,
        "fail_closed_negative": 4,
    }
    verified = [row for row in inventory["cases"] if row["credit_eligible"]]
    assert len(verified) == 32
    assert all(
        row["evidence"]["receipt_row_sha256"].startswith("sha256:") for row in verified
    )
    parity_by_id = {
        row["case_id"]: row for row in json.loads(parity_receipts["v4"])["cases"]
    }
    assert all(
        row["evidence"]["receipt_row_sha256"]
        == inventory_builder._sha256_bytes(
            inventory_builder._canonical_bytes(parity_by_id[row["case_id"]])
        )
        for row in verified
    )

    unbacked_inventory = deepcopy(inventory)
    verified_row = next(
        row for row in unbacked_inventory["cases"] if row["credit_eligible"]
    )
    verified_row["evidence"] = None
    with pytest.raises(ValidationError):
        _validator(INVENTORY_SCHEMA_V4).validate(unbacked_inventory)

    forged = json.loads(parity_receipts["v4"])
    forged["cases"][20]["verification_kind"] = "numerical_differential"
    forged_path = tmp_path / "forged-v4-kind.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValidationError):
        inventory_builder.build_inventory(forged_path)


def test_reference_inventory_rejects_duplicate_and_wrong_case_sets(
    parity_receipts: dict[str, bytes], tmp_path: Path
) -> None:
    duplicated = json.loads(parity_receipts["v2"])
    duplicated["cases"][1]["case_id"] = duplicated["cases"][0]["case_id"]
    duplicate_path = tmp_path / "duplicate-case-id.json"
    duplicate_path.write_text(json.dumps(duplicated), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate case ids"):
        inventory_builder.build_inventory(duplicate_path)

    wrong_set = json.loads(parity_receipts["v2"])
    wrong_set["cases"][0]["case_id"] = "basic_axial_tension"
    wrong_set_path = tmp_path / "wrong-case-set.json"
    wrong_set_path.write_text(json.dumps(wrong_set), encoding="utf-8")
    with pytest.raises(ValidationError):
        inventory_builder.build_inventory(wrong_set_path)


def test_v3_inventory_rejects_duplicate_and_wrong_case_sets(
    parity_receipts: dict[str, bytes], tmp_path: Path
) -> None:
    duplicated = json.loads(parity_receipts["v3"])
    duplicated["cases"][8]["case_id"] = duplicated["cases"][7]["case_id"]
    duplicate_path = tmp_path / "duplicate-v3-case-id.json"
    duplicate_path.write_text(json.dumps(duplicated), encoding="utf-8")
    with pytest.raises(ValidationError):
        inventory_builder.build_inventory(duplicate_path)

    wrong_set = json.loads(parity_receipts["v3"])
    wrong_set["cases"][-1]["case_id"] = "basic_axial_tension"
    wrong_set_path = tmp_path / "wrong-v3-case-set.json"
    wrong_set_path.write_text(json.dumps(wrong_set), encoding="utf-8")
    with pytest.raises(ValidationError):
        inventory_builder.build_inventory(wrong_set_path)


def test_stable_id_alignment_rejects_duplicate_and_missing_rows() -> None:
    expected = ["N1", "N2"]
    rows = [{"node_id": "N2", "value": 2}, {"node_id": "N1", "value": 1}]
    assert [
        row["value"] for row in runner._rows_by_stable_id(rows, "node_id", expected)
    ] == [
        1,
        2,
    ]
    with pytest.raises(RuntimeError, match="duplicate"):
        runner._rows_by_stable_id(
            [{"node_id": "N1"}, {"node_id": "N1"}], "node_id", expected
        )
    with pytest.raises(RuntimeError, match="set mismatch"):
        runner._rows_by_stable_id([{"node_id": "N1"}], "node_id", expected)
