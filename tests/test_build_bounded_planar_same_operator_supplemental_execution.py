from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts"
    / "build_bounded_planar_same_operator_supplemental_execution.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_same_operator_supplemental_execution_tests", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
bundle = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bundle
SPEC.loader.exec_module(bundle)
pytestmark = pytest.mark.skipif(
    not (ROOT / bundle.DEFAULT_OUT_DIR / bundle.RECEIPT_NAME).is_file(),
    reason="optional same-operator replay bundle is not source-controlled",
)


def _receipt() -> dict:
    return json.loads(
        (ROOT / bundle.DEFAULT_OUT_DIR / bundle.RECEIPT_NAME).read_text(
            encoding="utf-8"
        )
    )


def test_same_operator_supplemental_execution_schema_is_valid() -> None:
    schema = json.loads((ROOT / bundle.SCHEMA_PATH).read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)


def test_committed_same_operator_bundle_replays_sixteen_exact_cases() -> None:
    receipt = bundle.validate_bundle(repo_root=ROOT)

    assert receipt["summary"] == {
        "family_count": 5,
        "case_count": 16,
        "technical_pass_count": 16,
        "external_engine_invoked_case_count": 15,
    }
    assert [row["family_id"] for row in receipt["families"]] == [
        "linear",
        "negative",
        "scaling",
        "modal_buckling",
        "nonlinear_material_recovery",
    ]
    assert sum(len(row["case_ids"]) for row in receipt["families"]) == 16
    assert all(row["technical_contract_pass"] for row in receipt["families"])
    assert all(
        row["current_product_replay_pass"] is True
        and row["external_execution_reused"] is True
        and row["external_runtime_executed_in_this_generation"] is False
        and row["fresh_current_source_external_execution"] is False
        for row in receipt["families"]
    )
    assert all(
        row["historical_package_binding"]["file_count"]
        == len(row["historical_package_binding"]["files"])
        for row in receipt["families"]
    )
    assert receipt["execution_binding_hash"].startswith("sha256:")


def test_same_operator_bundle_preserves_non_promotion_boundary() -> None:
    receipt = _receipt()
    claims = receipt["claims"]

    assert claims["same_operator_local_execution"] is True
    assert claims["actual_external_solver_execution"] is True
    assert claims["historical_execution_input_bytes_attached"] is True
    assert claims["raw_execution_binding_pass"] is True
    assert claims["metric_semantics_match"] is True
    assert claims["current_product_replay_pass"] is True
    assert claims["external_runtime_executed_in_this_generation"] is False
    assert claims["external_execution_reused"] is True
    assert claims["fresh_current_source_external_execution"] is False
    assert claims["container_isolated_reproduction"] is False
    assert claims["independent_operator_attested"] is False
    assert claims["legal_use_approved"] is False
    assert claims["verification_matrix_credit"] is False
    assert claims["verification_level_2"] is False
    assert claims["design_authority"] is False
    assert claims["commercial_equivalence"] is False
    assert claims["release_readiness"] is False
    assert all(asset["bytes_attached"] is False for asset in receipt["runtime_assets"])
    assert receipt["replay_provenance"]["execution_mode"] == (
        "current_product_replay_only"
    )
    assert "external_runtime_current_source_rerun_missing" in receipt["blockers"]


def test_invalid_geometry_is_bound_as_preflight_not_solver_invocation() -> None:
    receipt = _receipt()
    negative = next(
        row for row in receipt["families"] if row["family_id"] == "negative"
    )
    invalid = next(
        row
        for row in negative["results"]
        if row["case_id"] == "bounded_planar_negative_invalid_geometry"
    )

    assert invalid["external_solver"] == "independent_preflight"
    assert invalid["external_engine_invoked"] is False
    assert receipt["summary"]["external_engine_invoked_case_count"] == 15


def test_same_operator_receipt_promotion_forgery_fails_closed() -> None:
    forged = deepcopy(_receipt())
    forged["claims"]["independent_operator_attested"] = True
    forged["artifact_hash"] = bundle._artifact_hash(forged)

    with pytest.raises(
        bundle.SameOperatorSupplementalExecutionError,
        match="same_operator_execution_receipt_schema_invalid",
    ):
        bundle.validate_receipt(forged, repo_root=ROOT)


def test_same_operator_receipt_hash_tamper_fails_closed() -> None:
    forged = deepcopy(_receipt())
    forged["summary"]["technical_pass_count"] = 15

    with pytest.raises(bundle.SameOperatorSupplementalExecutionError):
        bundle.validate_receipt(forged, repo_root=ROOT)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fresh_current_source_external_execution", True),
        ("external_execution_reused", False),
        ("current_product_replay_pass", False),
    ],
)
def test_same_operator_replay_provenance_forgery_fails_closed(
    field: str, value: bool
) -> None:
    forged = deepcopy(_receipt())
    forged["claims"][field] = value
    forged["artifact_hash"] = bundle._artifact_hash(forged)

    with pytest.raises(bundle.SameOperatorSupplementalExecutionError):
        bundle.validate_receipt(forged, repo_root=ROOT)


def test_same_operator_raw_result_tamper_fails_closed(tmp_path: Path) -> None:
    copied = tmp_path / "bundle"
    shutil.copytree(ROOT / bundle.DEFAULT_OUT_DIR, copied)
    result_path = (
        copied
        / "results"
        / "linear"
        / "bounded_planar_linear_portal.json"
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["metrics"]["node.N3.UX_m"] *= 2.0
    result["artifact_hash"] = bundle._artifact_hash(result)
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(bundle.SameOperatorSupplementalExecutionError):
        bundle.validate_bundle(repo_root=ROOT, out_dir=copied)


def test_same_operator_bundle_root_symlink_fails_closed(tmp_path: Path) -> None:
    linked = tmp_path / "linked-bundle"
    linked.symlink_to(ROOT / bundle.DEFAULT_OUT_DIR, target_is_directory=True)

    with pytest.raises(
        bundle.SameOperatorSupplementalExecutionError,
        match="same_operator_execution_bundle_root_symlink",
    ):
        bundle.validate_bundle(repo_root=ROOT, out_dir=linked)
