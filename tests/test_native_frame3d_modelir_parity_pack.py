from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator, ValidationError
import pytest


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
INVENTORY_SCHEMA_V2 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json"
)
INVENTORY_SCHEMA_V3 = (
    ROOT
    / "src/structural_analysis/schemas/native_frame3d_reference_inventory_v3.schema.json"
)
INVENTORY_BUILDER = ROOT / "scripts/build_native_frame3d_reference_inventory.py"
SPEC = importlib.util.spec_from_file_location("native_frame3d_parity_runner_tests", RUNNER)
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
                timeout=60,
            )
        receipts[profile] = outputs[0].read_bytes()
        assert receipts[profile] == outputs[1].read_bytes()

    for version in ("v2", "v3"):
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
    assert [row["value"] for row in runner._rows_by_stable_id(rows, "node_id", expected)] == [
        1,
        2,
    ]
    with pytest.raises(RuntimeError, match="duplicate"):
        runner._rows_by_stable_id(
            [{"node_id": "N1"}, {"node_id": "N1"}], "node_id", expected
        )
    with pytest.raises(RuntimeError, match="set mismatch"):
        runner._rows_by_stable_id([{"node_id": "N1"}], "node_id", expected)
