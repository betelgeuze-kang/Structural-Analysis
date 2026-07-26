"""Tests for the same-operator container-isolated external V&V candidate."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "benchmarks/clean-runners/opensees-calculix"
RUNNER = PACKAGE / "run_clean_runner.py"
DOCKERFILE = PACKAGE / "Dockerfile"
OUTPUT = ROOT / "artifacts/vv/opensees_calculix_clean_runner"
SUMMARY = OUTPUT / "clean_runner_receipt.json"
CODE_RECEIPT = OUTPUT / "external_code_to_code_receipt.json"
MODAL_RECEIPT = OUTPUT / "external_modal_buckling_receipt.json"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


runner = _load_module("external_vv_clean_runner", RUNNER)
code_module = _load_module(
    "external_vv_code_receipt",
    ROOT / "scripts/run_external_code_to_code_technical_receipt.py",
)
modal_module = _load_module(
    "external_vv_modal_receipt",
    ROOT / "scripts/run_external_modal_buckling_technical_receipt.py",
)


def _json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_clean_runner_summary_is_current_schema_valid_and_nonpromoting() -> None:
    payload = _json(SUMMARY)
    schema = _json(ROOT / runner.SCHEMA_RELATIVE_PATH)

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)
    runner.validate_summary(payload, repo_root=ROOT)

    assert payload["status"] == "partial"
    assert payload["technical_contract_pass"] is True
    assert payload["isolation"] == {
        "repository_mount_read_only": True,
        "runtime_default_network_route_present": False,
        "designated_output_mount_writable": True,
        "isolation_contract_pass": True,
    }
    assert payload["runner"]["base_image"] == runner.BASE_IMAGE
    assert payload["runner"]["runner_source_sha256"] == runner._file_hash(RUNNER)
    assert payload["runner"]["schema_sha256"] == runner._file_hash(
        ROOT / runner.SCHEMA_RELATIVE_PATH
    )
    assert payload["external_assets"] == [
        {
            "filename": name,
            "sha256": "sha256:" + runner.ASSET_POLICY[name],
            "bundled_in_repository": False,
        }
        for name in sorted(runner.ASSET_POLICY)
    ]
    assert payload["claims"]["same_operator_container_isolated_reproduction"] is True
    assert payload["claims"]["actual_external_solver_execution"] is True
    for forbidden in (
        "independent_operator_attestation",
        "product_legal_license_approval",
        "external_runtime_redistribution_approval",
        "verification_level_2",
        "commercial_equivalence",
        "design_authority",
        "release_readiness",
    ):
        assert payload["claims"][forbidden] is False
    assert "independent_operator_attestation_missing" in payload["blockers_remaining"]


def test_embedded_product_receipts_and_mode_vectors_validate_against_current_sources() -> (
    None
):
    summary = _json(SUMMARY)
    code = _json(CODE_RECEIPT)
    modal = _json(MODAL_RECEIPT)

    code_module.validate_external_code_to_code_technical_receipt(
        code,
        repo_root=ROOT,
        require_current_sources=True,
    )
    modal_module.validate_external_modal_buckling_technical_receipt(
        modal,
        repo_root=ROOT,
        require_current_sources=False,
    )
    assert modal["internal_source"][
        "input_checksums"
    ] == modal_module._source_checksums(ROOT)

    for name, receipt, path in (
        ("code_to_code", code, CODE_RECEIPT),
        ("modal_buckling", modal, MODAL_RECEIPT),
    ):
        descriptor = summary["product_receipts"][name]
        assert descriptor["file_sha256"] == runner._file_hash(path)
        assert descriptor["artifact_hash"] == receipt["artifact_hash"]
        assert (
            descriptor["source_set_hash"]
            == receipt["internal_source"]["source_set_hash"]
        )
        assert descriptor["technical_contract_pass"] is True
        assert descriptor["fresh_external_runtime_execution"] is True
        assert receipt["replay_provenance"]["external_execution_reused"] is False
        assert receipt["claims"]["verification_level_2"] is False

    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    assert summary["source_commit_sha"] == head
    assert code["source_commit_sha"] == head
    assert modal["source_commit_sha"] == head

    parity = summary["cross_environment_parity"]
    assert parity["numerical_contract_pass"] is True
    assert parity["scalar_comparison_count"] == 55
    assert parity["maximum_absolute_delta"] <= (
        parity["absolute_tolerance"] + parity["relative_tolerance"] * 10.0
    )
    assert parity["semantic_hash_matches"]["modal_model_hash"] is True
    assert parity["semantic_hash_matches"]["buckling_model_hash"] is True
    assert parity["semantic_hash_matches"]["buckling_semantic_result_hash"] is False
    assert parity["exact_semantic_hash_parity"] is False
    assert summary["claims"]["cross_environment_numerical_parity"] is True


def test_rehashed_level2_or_independent_operator_promotion_is_rejected() -> None:
    payload = deepcopy(_json(SUMMARY))
    payload["claims"]["verification_level_2"] = True
    payload["claims"]["independent_operator_attestation"] = True
    payload["artifact_hash"] = runner._artifact_hash(payload)

    with pytest.raises(ValidationError):
        runner.validate_summary(payload, repo_root=ROOT)


def test_runner_package_pins_the_base_and_keeps_output_scope_explicit() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    readme = (PACKAGE / "README.md").read_text(encoding="utf-8")

    assert f"FROM {runner.BASE_IMAGE.removeprefix('docker.io/library/')}" in dockerfile
    assert "numpy==1.26.4" in dockerfile
    assert "scipy==1.12.0" in dockerfile
    assert "libopenmpi3" in dockerfile
    assert "--provenance=false" in (
        ROOT / "scripts/run_external_vv_clean_runner.sh"
    ).read_text(encoding="utf-8")
    assert "--network none" in readme
    assert "--read-only" in readme
    assert "independent_operator_attestation" in readme

    with pytest.raises(
        runner.CleanRunnerError, match="output_directory_must_be_inside_repo"
    ):
        runner._relative_to_repo(Path("/tmp/out"), ROOT)
