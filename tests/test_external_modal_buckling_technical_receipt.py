from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/run_external_modal_buckling_technical_receipt.py"
RECEIPT = (
    ROOT
    / "implementation/phase1/release_evidence/productization/"
    "external_modal_buckling_technical_execution_receipt.json"
)
spec = importlib.util.spec_from_file_location(
    "run_external_modal_buckling_technical_receipt",
    SCRIPT,
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _payload() -> dict:
    return json.loads(RECEIPT.read_text(encoding="utf-8"))


def test_stored_receipt_is_current_schema_valid_and_nonpromoting() -> None:
    payload = _payload()

    validated = module.validate_external_modal_buckling_technical_receipt(
        payload,
        repo_root=ROOT,
        require_current_sources=True,
    )

    assert validated["status"] == "partial"
    assert validated["technical_contract_pass"] is True
    assert validated["verification_hierarchy_credit"] is False
    assert validated["verification_hierarchy_operator_manifest_attached"] is False
    assert validated["claims"] == {
        "actual_external_solver_execution": True,
        "whole_model_frame_modal_technical_comparison": True,
        "modal_mac_comparison": True,
        "whole_model_frame_buckling_technical_comparison": True,
        "buckling_repeated_mode_subspace_comparison": True,
        "product_legal_license_approval": False,
        "external_runtime_redistribution_approval": False,
        "verification_level_2": False,
        "commercial_equivalence": False,
        "release_readiness": False,
    }
    assert len(validated["comparisons"]) == 2
    assert all(row["contract_pass"] for row in validated["comparisons"])
    assert validated["mode_vector_storage_profile"] == (
        "canonical_little_endian_fp64_binary.v1"
    )
    assert len(validated["mode_vector_artifacts"]) == 4
    assert all("values" not in row for row in validated["mode_vector_artifacts"])
    source_checksums = validated["internal_source"]["input_checksums"]
    assert "scripts/source_bound_python_inventory.py" in source_checksums
    assert "src/structural_analysis/solvers/equation_scaling_6dof.py" in (
        source_checksums
    )
    assert "src/structural_analysis/model_ir/validation.py" in source_checksums


def test_modal_mac_and_buckling_subspace_metrics_are_recomputed_from_binary() -> None:
    payload = _payload()
    modal = payload["comparisons"][0]
    buckling = payload["comparisons"][1]
    modal_thresholds = [
        row
        for row in modal["metrics"]
        if row["metric_kind"] == "minimum_threshold"
    ]
    buckling_factor_rows = [
        row
        for row in buckling["metrics"]
        if row["metric_kind"] == "value_error"
    ]
    subspace = next(
        row
        for row in buckling["metrics"]
        if row["metric_kind"] == "minimum_threshold"
    )

    assert [row["observed_value"] for row in modal_thresholds] == pytest.approx(
        [1.0, 1.0], abs=1.0e-14
    )
    assert max(row["relative_error"] for row in buckling_factor_rows) < 0.01
    assert subspace["observed_value"] > 0.99999999
    assert subspace["minimum_accepted"] == module.BUCKLING_SUBSPACE_CORRELATION_MINIMUM


def test_mode_similarity_helpers_are_sign_and_basis_invariant() -> None:
    modal_product = np.asarray([[1.0, 0.25], [0.7, 1.0]], dtype=np.float64)
    modal_reference = modal_product @ np.diag([-3.0, 2.0])
    assert module._modal_assurance(modal_product, modal_reference) == pytest.approx(
        [1.0, 1.0]
    )

    x = np.linspace(0.0, np.pi, 17)
    product = np.column_stack(
        [
            np.ravel(np.column_stack([np.sin(x), np.zeros_like(x)])),
            np.ravel(np.column_stack([np.zeros_like(x), np.sin(x)])),
        ]
    )
    rotation = np.asarray([[0.6, -0.8], [0.8, 0.6]])
    reference = product @ rotation
    assert module._subspace_principal_correlations_squared(
        product, reference
    ) == pytest.approx([1.0, 1.0], abs=1.0e-14)


def test_current_product_replay_accepts_semantic_hash_only_platform_drift() -> None:
    payload = _payload()
    product = module._current_product_evidence()
    product["modal_result"]["metrics"]["semantic_result_hash"] = "sha256:" + "1" * 64
    product["buckling_result"]["metrics"]["semantic_result_hash"] = (
        "sha256:" + "2" * 64
    )
    matrices = {
        row["name"]: module._load_matrix_artifact(
            repo_root=ROOT,
            descriptor=row,
        )
        for row in payload["mode_vector_artifacts"]
    }

    module._validate_current_product_replay(
        payload=payload,
        matrices=matrices,
        product=product,
    )

    product["modal_result"]["metrics"]["modes"][0][
        "eigenvalue_rad2_per_s2"
    ] += 1.0e-6
    with pytest.raises(
        module.ExternalModalBucklingReceiptError,
        match="product_modal_metric_stale",
    ):
        module._validate_current_product_replay(
            payload=payload,
            matrices=matrices,
            product=product,
        )


def test_offline_validator_rejects_tampered_mode_vector_bytes(
    tmp_path: Path,
) -> None:
    payload = deepcopy(_payload())
    schema_target = tmp_path / module.SCHEMA_PATH
    schema_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / module.SCHEMA_PATH, schema_target)
    for descriptor in payload["mode_vector_artifacts"]:
        relative = Path(descriptor["artifact_path"])
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    tampered = tmp_path / payload["mode_vector_artifacts"][0]["artifact_path"]
    raw = bytearray(tampered.read_bytes())
    raw[-1] ^= 1
    tampered.write_bytes(raw)

    with pytest.raises(
        module.ExternalModalBucklingReceiptError,
        match="mode_vector_data_hash_invalid",
    ):
        module.validate_external_modal_buckling_technical_receipt(
            payload,
            repo_root=tmp_path,
            require_current_sources=False,
        )


def test_schema_and_offline_cli_check() -> None:
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(_payload())

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "external_modal_buckling_technical_receipt_consistent" in completed.stdout
