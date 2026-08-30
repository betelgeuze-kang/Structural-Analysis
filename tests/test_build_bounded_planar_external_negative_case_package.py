from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_bounded_planar_external_negative_case_package.py"
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_negative_case_package_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)


def _manifest() -> dict:
    return json.loads(
        (ROOT / package.DEFAULT_OUT_DIR / package.MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )


def test_negative_case_schemas_are_valid() -> None:
    for relative in (package.SCHEMA_PATH, package.OUTPUT_SCHEMA_PATH):
        schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_committed_negative_case_package_is_exact_and_non_promoting() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)

    assert manifest["summary"] == {
        "case_count": 3,
        "product_rejection_ready_count": 3,
        "external_ready_count": 0,
    }
    assert [row["requirement_id"] for row in manifest["cases"]] == [
        "negative.mechanism",
        "negative.singular",
        "negative.invalid_geometry",
    ]
    assert manifest["claims"]["current_product_rejection"] is True
    assert manifest["claims"]["external_solver_execution"] is False
    assert manifest["claims"]["external_reference_attached"] is False
    assert manifest["claims"]["verification_matrix_credit"] is False
    assert manifest["claims"]["verification_level_2"] is False
    assert manifest["blockers"] == ["external_runtime_execution_missing"]
    assert all(
        row["product_rejection_contract_pass"] is True
        and row["external_execution_status"] == "unavailable"
        and row["external_result_attached"] is False
        for row in manifest["cases"]
    )


def test_committed_negative_case_package_matches_current_builder() -> None:
    ok, message = package.check_package(repo_root=ROOT)

    assert ok is True
    assert message == "bounded_planar_external_negative_case_package_consistent"


def test_product_rejections_distinguish_all_three_layers() -> None:
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR
    products = {}
    for row in manifest["cases"]:
        products[row["requirement_id"]] = json.loads(
            (package_root / row["product_result"]["path"]).read_text(encoding="utf-8")
        )

    mechanism = products["negative.mechanism"]
    assert (
        mechanism["rejection_layer"],
        mechanism["reason_code"],
        mechanism["solver_executed"],
    ) == ("solver", "mechanism_detected", True)
    singular = products["negative.singular"]
    assert (
        singular["rejection_layer"],
        singular["reason_code"],
        singular["solver_executed"],
    ) == ("solver_preflight", "singular_system_detected", False)
    invalid = products["negative.invalid_geometry"]
    assert (
        invalid["rejection_layer"],
        invalid["kind"],
        invalid["solver_executed"],
    ) == (
        "model_ir_validation",
        "bounded_planar_node_coordinate_duplicate",
        False,
    )
    assert all(
        result["fallback_count"] == 0
        and result["regularization_count"] == 0
        and result["contract_pass"] is True
        for result in products.values()
    )


def test_negative_runners_bind_actual_model_and_do_not_invent_external_results() -> (
    None
):
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR

    for row in manifest["cases"]:
        runner = package_root / row["opensees_runner"]["path"]
        source = runner.read_text(encoding="utf-8")
        compile(source, str(runner), "exec")
        assert "source_model_file_sha256 = hash_bytes(model_bytes)" in source
        assert "source_model_hash_mismatch" in source
        assert "EXPECTED_OPENSEESPY_VERSION = '3.7.1.2'" in source
        assert "EXPECTED_OPENSEES_CORE_VERSION = '3.7.1'" in source
        assert 'payload["artifact_hash"] = artifact_hash(payload)' in source
    invalid_runner = package_root / manifest["cases"][2]["opensees_runner"]["path"]
    source = invalid_runner.read_text(encoding="utf-8")
    assert 'if REQUIREMENT_ID == "negative.invalid_geometry":' in source
    assert "engine_invoked = False" in source
    singular_runner = package_root / manifest["cases"][1]["opensees_runner"]["path"]
    singular_source = singular_runner.read_text(encoding="utf-8")
    assert 'ops.printA("-ret")' in singular_source
    assert "TANGENT_RELATIVE_PIVOT_TOLERANCE = 1.0e-12" in singular_source
    assert '"rank_deficient": numerical_rank < equation_count' in singular_source


def test_negative_case_package_detects_tampering(tmp_path: Path) -> None:
    source = ROOT / package.DEFAULT_OUT_DIR
    target = tmp_path / "negative-package"
    shutil.copytree(source, target)
    runner = target / "opensees/bounded_planar_negative_singular.py"
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    ok, message = package.check_package(repo_root=ROOT, out_dir=target)

    assert ok is False
    assert message == (
        "bounded_planar_external_negative_case_mismatch:"
        "opensees/bounded_planar_negative_singular.py"
    )


def test_negative_execution_workflow_is_main_only_and_attested() -> None:
    source = (ROOT / package.EXECUTION_WORKFLOW_PATH).read_text(encoding="utf-8")
    runner = (
        ROOT / "benchmarks/clean-runners/bounded-planar-supplemental/run_family.py"
    ).read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "pull_request:" not in source
    assert "schedule:" not in source
    assert "build_bounded_planar_external_negative_case_package.py" in source
    assert "--check" in source
    assert "bounded-planar-sealed-technical-attestor.yml" in source
    assert "actions/attest@" not in source
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source
    for case_id in (
        "bounded_planar_negative_mechanism",
        "bounded_planar_negative_singular",
        "bounded_planar_negative_invalid_geometry",
    ):
        assert case_id in runner
