from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_bounded_planar_external_linear_case_package.py"
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_linear_case_package_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)


def _manifest() -> dict:
    path = ROOT / package.DEFAULT_OUT_DIR / package.MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def test_linear_case_package_schema_is_valid() -> None:
    schema = json.loads((ROOT / package.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    output_schema = json.loads(
        (ROOT / package.OUTPUT_SCHEMA_PATH).read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(output_schema)


def test_committed_linear_case_package_is_exact_and_non_promoting() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)
    package._validate_manifest(manifest, ROOT)

    assert manifest["summary"] == {
        "case_count": 2,
        "product_ready_count": 2,
        "external_ready_count": 0,
    }
    assert [row["requirement_id"] for row in manifest["cases"]] == [
        "linear.portal",
        "linear.multistory",
    ]
    assert all(
        row["product_execution_contract_pass"] is True
        and row["external_execution_status"] == "unavailable"
        and row["external_reference_attached"] is False
        for row in manifest["cases"]
    )
    assert manifest["claims"] == {
        "exact_model_ir_inputs": True,
        "current_product_execution": True,
        "opensees_runner_syntax_checked": True,
        "runtime_dependency_pinned": True,
        "output_authenticity_contract": True,
        "external_solver_execution": False,
        "external_reference_values": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }
    assert manifest["blockers"] == ["external_runtime_execution_missing"]
    package_root = ROOT / package.DEFAULT_OUT_DIR
    assert (package_root / manifest["external_result_schema"]["path"]).is_file()
    assert (package_root / manifest["python_requirements"]["path"]).read_bytes() == (
        package.locked_requirements_bytes()
    )
    assert (package_root / manifest["operator_readme"]["path"]).is_file()
    packaged_workflow = package_root / manifest["execution_workflow"]["path"]
    assert (
        packaged_workflow.read_bytes()
        == (ROOT / package.EXECUTION_WORKFLOW_PATH).read_bytes()
    )


def test_committed_linear_case_package_matches_current_builder() -> None:
    ok, message = package.check_package(repo_root=ROOT)

    assert ok is True
    assert message == "bounded_planar_external_linear_case_package_consistent"


def test_linear_case_package_detects_file_tampering(tmp_path: Path) -> None:
    source = ROOT / package.DEFAULT_OUT_DIR
    target = tmp_path / "linear-package"
    shutil.copytree(source, target)
    runner = target / "opensees" / "bounded_planar_linear_portal.py"
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    ok, message = package.check_package(repo_root=ROOT, out_dir=target)

    assert ok is False
    assert message == (
        "bounded_planar_external_linear_case_mismatch:"
        "opensees/bounded_planar_linear_portal.py"
    )


def test_opensees_runners_use_linear_transform_and_no_reference_values() -> None:
    manifest = _manifest()
    package_root = ROOT / package.DEFAULT_OUT_DIR

    for row in manifest["cases"]:
        runner = package_root / row["opensees_runner"]["path"]
        source = runner.read_text(encoding="utf-8")
        compile(source, str(runner), "exec")
        assert 'ops.geomTransf("Linear", 1)' in source
        assert "metadata.version('openseespy')" in source
        assert "runner_file_sha256" in source
        assert "source_model_file_sha256" in source
        assert "payload['artifact_hash'] = artifact_hash(payload)" in source
        assert "reference" not in row["metric_ids"]
