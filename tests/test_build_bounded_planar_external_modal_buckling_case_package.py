from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_bounded_planar_external_modal_buckling_case_package.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_modal_buckling_case_package_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
package = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = package
SPEC.loader.exec_module(package)

RUNNER_SCRIPT = ROOT / "scripts" / "run_bounded_planar_external_modal_buckling_case.py"
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "run_bounded_planar_external_modal_buckling_case_tests", RUNNER_SCRIPT
)
assert RUNNER_SPEC is not None and RUNNER_SPEC.loader is not None
runner = importlib.util.module_from_spec(RUNNER_SPEC)
sys.modules[RUNNER_SPEC.name] = runner
RUNNER_SPEC.loader.exec_module(runner)


def _manifest() -> dict:
    return json.loads(
        (ROOT / package.DEFAULT_OUT_DIR / package.MANIFEST_NAME).read_text(
            encoding="utf-8"
        )
    )


def test_modal_buckling_case_schemas_are_valid() -> None:
    for relative in (
        package.SCHEMA_PATH,
        package.OUTPUT_SCHEMA_PATH,
        Path(
            "src/structural_analysis/schemas/"
            "bounded_planar_external_modal_buckling_execution_receipt_v1.schema.json"
        ),
    ):
        schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_committed_modal_buckling_package_is_exact_and_non_promoting() -> None:
    manifest = package.validate_package_directory(repo_root=ROOT)

    assert manifest["summary"] == {
        "case_count": 3,
        "product_ready_count": 3,
        "external_ready_count": 0,
    }
    assert [row["requirement_id"] for row in manifest["cases"]] == [
        "modal.rigid_mode",
        "modal.repeated_mode",
        "buckling.portal",
    ]
    assert manifest["claims"]["exact_canonical_model_inputs"] is True
    assert manifest["claims"]["current_product_replay"] is True
    assert manifest["claims"]["external_solver_execution"] is False
    assert manifest["claims"]["verification_matrix_credit"] is False
    assert manifest["claims"]["verification_level_2"] is False
    assert manifest["blockers"] == ["external_runtime_execution_missing"]
    assert all(
        row["current_product_contract_pass"] is True
        and row["external_execution_status"] == "unavailable"
        and row["external_reference_attached"] is False
        for row in manifest["cases"]
    )


def test_committed_modal_buckling_package_matches_current_builder() -> None:
    ok, message = package.check_package(repo_root=ROOT)

    assert ok is True
    assert message == "bounded_planar_external_modal_buckling_case_package_consistent"


def test_portal_model_and_calculix_runner_share_exact_b32_circle_mapping() -> None:
    manifest = _manifest()
    portal = manifest["cases"][2]
    model = json.loads(
        (ROOT / package.DEFAULT_OUT_DIR / portal["model"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    section = model["sections"][0]
    mapping = model["metadata"]["external_discretization"]

    expected_inertia = math.pi * 0.12**4 / 64.0
    assert section["width"] == section["depth"] == 0.12
    assert section["area"] == math.pi * 0.12**2 / 4.0
    assert section["iy"] == section["iz"] == expected_inertia
    assert section["torsional_constant"] == 2.0 * expected_inertia
    assert len(model["nodes"]) == 49
    assert len(model["elements"]) == 48
    assert mapping["schema_version"] == "bounded-planar-calculix-b32-mapping.v1"
    assert mapping["section_type"] == "CIRC"
    assert mapping["product_linear_elements_per_member"] == 16
    assert mapping["calculix_quadratic_elements_per_member"] == 8
    assert [row["member_id"] for row in mapping["member_paths"]] == [
        "C1",
        "B1",
        "C2",
    ]

    deck = runner._calculix_deck(model)
    assert "*ELEMENT, TYPE=B32, ELSET=EALL" in deck
    assert "*BEAM SECTION, ELSET=EALL, MATERIAL=MAT, SECTION=CIRC" in deck
    element_block = deck.split("*ELEMENT, TYPE=B32, ELSET=EALL\n", 1)[1].split(
        "*BEAM SECTION", 1
    )[0]
    assert len([line for line in element_block.splitlines() if line.strip()]) == 24


def test_calculix_b32_mapping_rejects_incomplete_product_edge_coverage() -> None:
    manifest = _manifest()
    portal = manifest["cases"][2]
    model = json.loads(
        (ROOT / package.DEFAULT_OUT_DIR / portal["model"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    tampered = deepcopy(model)
    tampered["elements"].pop()

    with pytest.raises(
        runner.PackagedExternalCaseError,
        match="calculix_b32_mapping_element_coverage_invalid",
    ):
        runner._calculix_deck(tampered)


def test_modal_model_binds_opensees_torsional_mass_equivalence() -> None:
    manifest = _manifest()
    rigid = manifest["cases"][0]
    model = json.loads(
        (ROOT / package.DEFAULT_OUT_DIR / rigid["model"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    section = model["sections"][0]

    assert section["torsional_constant"] == section["iy"] + section["iz"]
    assert model["metadata"]["external_modal_mass_equivalence"] == (
        "torsional_constant_equals_polar_area_moment"
    )


def test_package_runner_has_no_stored_external_result() -> None:
    manifest = _manifest()
    runner_path = (
        ROOT / package.DEFAULT_OUT_DIR / manifest["cases"][0]["external_runner"]["path"]
    )
    source = runner_path.read_text(encoding="utf-8")

    compile(source, str(runner_path), "exec")
    assert "openseespy.opensees" in source
    assert "subprocess.run" in source
    assert "external_reference" not in source
    assert "package_model_hash_invalid" in source
    assert "package_runner_hash_invalid" in source
    assert "object_pairs_hook=_unique_json_object" in source
    assert "parse_constant=_reject_json_constant" in source
    assert "parse_float=_finite_json_float" in source


@pytest.mark.parametrize(
    ("payload", "marker"),
    [
        ('{"case_id":"a","case_id":"b"}', "package_json_duplicate_key"),
        ('{"value":NaN}', "package_json_nonfinite"),
        ('{"value":Infinity}', "package_json_nonfinite"),
        ('{"value":1e9999}', "package_json_nonfinite"),
    ],
)
def test_packaged_runner_rejects_ambiguous_or_nonfinite_json(
    tmp_path: Path, payload: str, marker: str
) -> None:
    path = tmp_path / "attack.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(runner.PackagedExternalCaseError, match=marker):
        runner._load_json(path, "package_json_invalid")


def test_modal_buckling_package_detects_file_tampering(tmp_path: Path) -> None:
    source = ROOT / package.DEFAULT_OUT_DIR
    target = tmp_path / "modal-buckling-package"
    shutil.copytree(source, target)
    model = target / "models" / "bounded_planar_modal_rigid_mode.model.json"
    model.write_text(model.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    ok, message = package.check_package(repo_root=ROOT, out_dir=target)

    assert ok is False
    assert message == (
        "bounded_planar_external_modal_buckling_case_mismatch:"
        "models/bounded_planar_modal_rigid_mode.model.json"
    )


def test_execution_workflow_is_main_only_and_attested() -> None:
    source = (ROOT / package.EXECUTION_WORKFLOW_PATH).read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "pull_request:" not in source
    assert "schedule:" not in source
    assert "calculix-ccx=2.17-3" in source
    assert "bounded-planar-sealed-technical-attestor.yml" in source
    assert "actions/attest@" not in source
    assert "bounded_planar_runtime_lock.py prepare" in source
    assert "--network none --read-only" in source
    assert "apt-get download" in source
    assert "--runtime-blocker" not in source
    attestor = (
        ROOT / ".github/workflows/bounded-planar-sealed-technical-attestor.yml"
    ).read_text(encoding="utf-8")
    assert "--deny-self-hosted-runners" in attestor
    assert "--fail-technical-blocked" in source
