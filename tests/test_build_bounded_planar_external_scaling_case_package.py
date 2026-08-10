from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator
import pytest

from structural_analysis.model_ir.loader import parse_model_ir_v2


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "build_bounded_planar_external_scaling_case_package.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_scaling_case_package_tests",
    SCRIPT,
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


def test_scaling_case_schemas_are_valid() -> None:
    for relative in (package.SCHEMA_PATH, package.OUTPUT_SCHEMA_PATH):
        schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_committed_scaling_package_is_exact_and_non_promoting() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)

    assert manifest["summary"] == {
        "case_count": 2,
        "product_ready_count": 2,
        "external_ready_count": 0,
    }
    assert [row["requirement_id"] for row in manifest["cases"]] == [
        "scaling.unit_invariance",
        "scaling.characteristic_length_invariance",
    ]
    assert manifest["claims"] == {
        "exact_model_ir_inputs": True,
        "current_product_invariance_replay": True,
        "opensees_runner_syntax_checked": True,
        "runtime_dependency_pinned": True,
        "output_authenticity_contract": True,
        "external_solver_execution": False,
        "external_reference_attached": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }
    assert manifest["blockers"] == ["external_runtime_execution_missing"]
    assert all(
        row["product_invariance_contract_pass"] is True
        and row["external_execution_status"] == "unavailable"
        and row["external_reference_attached"] is False
        for row in manifest["cases"]
    )


def test_committed_scaling_package_matches_current_builder() -> None:
    ok, message = package.check_package(repo_root=ROOT)

    assert ok is True
    assert message == "bounded_planar_external_scaling_case_package_consistent"


def test_unit_pair_changes_provenance_without_changing_semantics() -> None:
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR
    row = manifest["cases"][0]
    pair = json.loads(
        (package_root / row["model_pair"]["path"]).read_text(encoding="utf-8")
    )
    first, second = (
        parse_model_ir_v2(variant["model_ir"])
        for variant in pair["variants"]
    )

    assert first.semantic_hash == second.semantic_hash
    assert first.content_hash != second.content_hash
    assert first.provenance_hash != second.provenance_hash
    assert pair["variants"][0]["model_ir"]["provenance"]["source_units"][
        "length"
    ] == "m"
    assert pair["variants"][1]["model_ir"]["provenance"]["source_units"][
        "length"
    ] == "mm"


def test_characteristic_length_pair_obeys_similarity_contract() -> None:
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR
    row = manifest["cases"][1]
    pair = json.loads(
        (package_root / row["model_pair"]["path"]).read_text(encoding="utf-8")
    )
    product = json.loads(
        (package_root / row["product_result"]["path"]).read_text(encoding="utf-8")
    )

    assert [
        variant["characteristic_scale"] for variant in pair["variants"]
    ] == [1.0, 4.0]
    assert product["contract_pass"] is True
    assert (
        product["maximum_relative_difference"]
        <= product["relative_tolerance"]
        == package._INVARIANCE_RELATIVE_TOLERANCE
    )
    assert product["maximum_relative_difference"] > 0.0
    assert product["maximum_relative_difference"] <= (
        0.2 * package._INVARIANCE_RELATIVE_TOLERANCE
    )
    assert package._PRODUCT_SOLVER_RESIDUAL_TOLERANCE == 2.0e-8
    assert (
        package._PRODUCT_SOLVER_RESIDUAL_TOLERANCE
        < package._INVARIANCE_RELATIVE_TOLERANCE
    )


def test_loose_solver_tolerance_cannot_bypass_similarity_gate(monkeypatch) -> None:
    monkeypatch.setattr(package, "_PRODUCT_SOLVER_RESIDUAL_TOLERANCE", 5.0e-8)
    case = package.CASE_DEFINITIONS[1]

    with pytest.raises(
        package.ExternalScalingCasePackageError,
        match="external_scaling_product_invariance_failed",
    ):
        package._product_result(case, package._model_pair(case))


def test_scaling_runners_are_source_bound_without_stored_external_values() -> None:
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR

    for row in manifest["cases"]:
        runner = package_root / row["opensees_runner"]["path"]
        source = runner.read_text(encoding="utf-8")
        compile(source, str(runner), "exec")
        assert "MODEL_PAIR_FILE_SHA256 = 'sha256:" in source
        assert "EXPECTED_OPENSEESPY_VERSION = '3.7.1.2'" in source
        assert "EXPECTED_OPENSEES_CORE_VERSION = '3.7.1'" in source
        assert "ops.geomTransf(\"Linear\", 1)" in source
        assert 'payload["artifact_hash"] = artifact_hash(payload)' in source
        assert "external_reference" not in source


def test_scaling_package_detects_file_tampering(tmp_path: Path) -> None:
    source = ROOT / package.DEFAULT_OUT_DIR
    target = tmp_path / "scaling-package"
    shutil.copytree(source, target)
    runner = (
        target
        / "opensees"
        / "bounded_planar_scaling_unit_invariance.py"
    )
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    ok, message = package.check_package(repo_root=ROOT, out_dir=target)

    assert ok is False
    assert message == (
        "bounded_planar_external_scaling_case_mismatch:"
        "opensees/bounded_planar_scaling_unit_invariance.py"
    )


def test_scaling_execution_workflow_is_main_only_and_source_bound() -> None:
    source = (ROOT / package.EXECUTION_WORKFLOW_PATH).read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "pull_request:" not in source
    assert "schedule:" not in source
    assert "build_bounded_planar_external_scaling_case_package.py" in source
    assert "--check" in source
    assert "actions/attest@v4" in source
    assert "actions/upload-artifact@v7" in source
    for case_id in (
        "bounded_planar_scaling_unit_invariance",
        "bounded_planar_scaling_characteristic_length_invariance",
    ):
        assert case_id in source
