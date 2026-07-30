from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "build_bounded_planar_external_nonlinear_material_recovery_case_package.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_nonlinear_material_recovery_case_package_tests",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)


def test_nonlinear_material_recovery_package_schema_is_valid() -> None:
    schema = json.loads((ROOT / package.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_committed_package_binds_six_exact_nonpromoting_cases() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)

    assert manifest["summary"] == {
        "case_count": 6,
        "product_ready_count": 6,
        "external_ready_count": 0,
    }
    assert [row["case_id"] for row in manifest["cases"]] == [
        "bounded_planar_p_delta",
        "bounded_planar_snap_through",
        "bounded_planar_steel_yield",
        "bounded_planar_rc_fiber",
        "bounded_planar_section_recovery",
        "bounded_planar_fiber_recovery",
    ]
    assert all(row["current_product_contract_pass"] for row in manifest["cases"])
    assert all(row["metric_ids"] for row in manifest["cases"])
    assert manifest["claims"]["external_solver_execution"] is False
    assert manifest["claims"]["verification_matrix_credit"] is False
    assert manifest["claims"]["verification_level_2"] is False
    assert manifest["artifact_hash"] == package._artifact_hash(manifest)


def test_product_references_bind_expected_physical_signatures() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)
    rows = {row["case_id"]: row for row in manifest["cases"]}

    p_delta = json.loads(
        (
            ROOT
            / package.DEFAULT_OUT_DIR
            / rows["bounded_planar_p_delta"]["product_result"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert p_delta["metrics"]["pdelta.amplification.ratio_0p95"] > 19.0
    snap = json.loads(
        (
            ROOT
            / package.DEFAULT_OUT_DIR
            / rows["bounded_planar_snap_through"]["product_result"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert snap["metrics"]["snap.first_limit.load_factor"] == pytest.approx(
        18.658629816710672
    )
    steel = json.loads(
        (
            ROOT
            / package.DEFAULT_OUT_DIR
            / rows["bounded_planar_steel_yield"]["product_result"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert steel["metrics"]["steel.yielded_point_count"] == 2.0
    rc = json.loads(
        (
            ROOT
            / package.DEFAULT_OUT_DIR
            / rows["bounded_planar_rc_fiber"]["product_result"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert rc["metrics"]["rc.yielded_steel_fiber_count"] == 1.0
    assert rc["metrics"]["rc.nonlinear_concrete_fiber_count"] == 2.0


def test_packaged_runner_is_standalone_and_source_exact() -> None:
    runner = ROOT / package.DEFAULT_OUT_DIR / package.PACKAGED_RUNNER_PATH
    source = ROOT / package.RUNNER_SOURCE_PATH

    assert runner.read_bytes() == source.read_bytes()
    text = runner.read_text(encoding="utf-8")
    assert "structural_analysis" not in text
    compile(text, str(runner), "exec")


def test_tampered_package_file_fails_closed(tmp_path: Path) -> None:
    source = ROOT / package.DEFAULT_OUT_DIR
    target = tmp_path / "package"
    shutil.copytree(source, target)
    runner = target / package.PACKAGED_RUNNER_PATH
    runner.write_text(runner.read_text(encoding="utf-8") + "# tampered\n")

    with pytest.raises(
        package.ExternalNonlinearMaterialRecoveryCasePackageError,
        match="external_nonlinear_case_file_hash_invalid",
    ):
        package.validate_package_directory(repo_root=ROOT, out_dir=target)


def test_committed_package_is_current_and_cli_check_passes() -> None:
    assert package.check_package(repo_root=ROOT) == (
        True,
        "bounded_planar_external_nonlinear_case_package_consistent",
    )
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "package_consistent" in completed.stdout
