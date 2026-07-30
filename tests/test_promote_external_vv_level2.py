from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from jsonschema import Draft202012Validator

from structural_analysis.benchmark.acceptance import decide_benchmark
from structural_analysis.benchmark.verification_hierarchy import (
    build_verification_hierarchy_readiness,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "promote_external_vv_level2.py"
OPERATOR_TEST = ROOT / "tests" / "test_validate_external_vv_operator_attestation.py"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


module = _load_module("promote_external_vv_level2_tests", SCRIPT)
operator_fixture = _load_module(
    "operator_attestation_fixture_for_promotion", OPERATOR_TEST
)


def _write(path: Path, content: bytes) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": path.name,
        "file_sha256": module.file_sha256(path),
    }


def _runtime(receipt: dict, distribution: str) -> dict:
    return next(
        row for row in receipt["external_assets"] if row["distribution"] == distribution
    )


def _complete_matrix(bundle_root: Path, source_commit: str, attestation: dict) -> dict:
    matrix = module.vv_matrix.build_bounded_planar_external_vv_matrix(
        repo_root=ROOT,
        same_operator_supplemental_receipt_path=(
            bundle_root / "local-supplement-must-not-shadow-operator-evidence.json"
        ),
    )
    assert matrix["source_commit_sha"] == source_commit
    for binding in matrix["receipt_bindings"]:
        descriptor = attestation["bundle"][binding["receipt_id"]]
        binding.update(
            {
                "path": descriptor["path"],
                "file_sha256": descriptor["file_sha256"],
                "artifact_hash": descriptor["artifact_hash"],
                "source_commit_sha": source_commit,
            }
        )
        binding["fresh_current_source_external_execution"] = True

    dedicated_bindings = []
    dedicated_case_ids: set[str] = set()
    for receipt_id in (
        "bounded_planar_linear",
        "bounded_planar_modal_buckling",
        "bounded_planar_negative",
        "bounded_planar_scaling",
        "bounded_planar_nonlinear_material_recovery",
    ):
        descriptor = attestation["bundle"][receipt_id]["technical_receipt"]
        receipt_path = bundle_root / descriptor["path"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        case_ids = sorted(case["case_id"] for case in receipt["cases"])
        invoked_case_ids = sorted(
            case["case_id"]
            for case in receipt["cases"]
            if case.get("external_engine_invoked", True) is True
        )
        dedicated_case_ids.update(case_ids)
        package_binding = receipt.get("package_binding")
        source_binding_hash = (
            package_binding["artifact_hash"]
            if isinstance(package_binding, dict)
            else receipt.get("package_manifest_artifact_hash", receipt["artifact_hash"])
        )
        dedicated_bindings.append(
            {
                "receipt_id": receipt_id,
                "path": descriptor["path"],
                "file_sha256": descriptor["file_sha256"],
                "artifact_hash": descriptor["artifact_hash"],
                "source_commit_sha": source_commit,
                "source_binding_hash": source_binding_hash,
                "case_ids": case_ids,
                "external_engine_invoked_case_ids": invoked_case_ids,
                "technical_contract_pass": True,
                "current_product_replay_pass": True,
                "external_execution_reused": False,
                "fresh_current_source_external_execution": True,
            }
        )
    core_case_ids = {
        case_id
        for binding in matrix["receipt_bindings"]
        for case_id in binding["case_ids"]
    }
    all_required_case_ids = {
        case_id
        for row in matrix["requirements"]
        for case_id in row["required_external_case_ids"]
    }
    additional_case_ids = sorted(
        all_required_case_ids - core_case_ids - dedicated_case_ids
    )
    assert additional_case_ids == []
    attestation["bundle"].pop("additional_receipts", None)
    operator_fixture._resign(attestation, bundle_root)
    # This helper also builds deliberately invalid promotion candidates.  Bind
    # the candidate structurally here and leave fresh-execution verification to
    # promote_external_vv_level2(), which must reject the reused submission.
    signature = attestation["signature"]
    matrix["operator_intake_binding"] = {
        "status": "available",
        "attestation_id": attestation["attestation_id"],
        "attestation_sha256": module.sha256_bytes(
            module.canonical_bytes(attestation)
        ),
        "source_commit_sha": attestation["source_commit_sha"],
        "signed_payload_sha256": signature["signed_payload_sha256"],
        "public_key_sha256": signature["public_key_sha256"],
        "signature_sha256": signature["signature_sha256"],
        "intake_contract_pass": True,
        "fresh_external_runtime_execution": True,
        "cryptographic_signature_verified": True,
        "operator_independence_declared": True,
        "operator_identity_credentials_verified": False,
        "verification_level_2": False,
    }
    matrix["supplemental_receipt_bindings"] = dedicated_bindings
    all_bindings = [
        *matrix["receipt_bindings"],
        *matrix["supplemental_receipt_bindings"],
    ]
    for row in matrix["requirements"]:
        required = list(row["required_external_case_ids"])
        assert required
        binding = next(
            binding
            for binding in all_bindings
            if set(required).issubset(set(binding["case_ids"]))
        )
        verification_method = row["verification_method"]
        external_execution = bool(
            verification_method == "external_solver_execution"
            and set(required).issubset(
                set(binding["external_engine_invoked_case_ids"])
            )
        )
        row.update(
            {
                "technical_reference_present": True,
                "current_product_replay_pass": True,
                "fresh_current_source_technical_validation": True,
                "fresh_current_source_external_execution": external_execution,
                "status": (
                    "fresh_external_technical"
                    if external_execution
                    else "fresh_independent_preflight_technical"
                ),
                "evidence": [
                    {
                        "receipt_id": binding["receipt_id"],
                        "path": binding["path"],
                        "artifact_hash": binding["artifact_hash"],
                        "case_ids": required,
                    }
                ],
            }
        )
        row["blockers"] = [
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "scientific_promotion_decision_missing",
            "formal_level2_promotion_receipt_missing",
        ]
    matrix["summary"].update(
        {
            "technical_reference_present_count": 25,
            "fresh_current_source_technical_count": 25,
            "current_product_replay_only_count": 0,
            "fresh_external_technical_count": 24,
            "fresh_independent_preflight_technical_count": 1,
            "promotion_eligible_count": 0,
            "missing_count": 0,
        }
    )
    matrix["claims"]["recommended_matrix_technical_coverage_complete"] = True
    matrix["claims"]["fresh_current_source_technical_matrix_complete"] = True
    matrix["claims"]["fresh_current_source_external_matrix_complete"] = True
    matrix["blockers"] = [
        blocker
        for blocker in matrix["blockers"]
        if blocker
        not in {
            "recommended_external_vv_matrix_incomplete",
            "fresh_current_source_technical_matrix_incomplete",
            "fresh_current_source_external_matrix_incomplete",
        }
    ]
    matrix["artifact_hash"] = module.vv_matrix._artifact_hash(matrix)
    module.vv_matrix._validate_status(
        matrix,
        ROOT,
        verified_operator_context={
            "receipt_bindings": matrix["receipt_bindings"],
            "supplemental_receipt_bindings": matrix[
                "supplemental_receipt_bindings"
            ],
            "operator_intake_binding": matrix["operator_intake_binding"],
        },
    )
    path = bundle_root / "bounded-planar-external-vv-matrix.json"
    path.write_text(
        json.dumps(matrix, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "path": path.name,
        "file_sha256": module.file_sha256(path),
        "artifact_hash": matrix["artifact_hash"],
    }


def _resign_promotion(promotion: dict, bundle_root: Path) -> None:
    payload_path = bundle_root / "project-review-payload.json"
    signature_path = bundle_root / promotion["signature"]["signature_path"]
    private_key = bundle_root / "project-reviewer-private-key.pem"
    payload = module.promotion_signed_payload(promotion)
    payload_path.write_bytes(payload)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(payload_path),
        ],
        check=True,
        capture_output=True,
    )
    promotion["signature"]["signed_payload_sha256"] = module.sha256_bytes(payload)
    promotion["signature"]["signature_sha256"] = module.file_sha256(signature_path)


def _build_promotion(
    root: Path, *, fresh_operator_execution: bool = True
) -> tuple[dict, Path]:
    attestation, bundle_root = operator_fixture._build_submission(
        root, fresh=fresh_operator_execution
    )
    operator_fixture._attach_linear_supplement(attestation, bundle_root)
    operator_fixture._attach_modal_buckling_supplement(attestation, bundle_root)
    operator_fixture._attach_negative_supplement(attestation, bundle_root)
    operator_fixture._attach_scaling_supplement(attestation, bundle_root)
    operator_fixture._attach_nonlinear_material_recovery_supplement(
        attestation, bundle_root
    )
    code = json.loads(
        (bundle_root / attestation["bundle"]["code_to_code"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    source_commit = attestation["source_commit_sha"]
    verification_matrix = _complete_matrix(bundle_root, source_commit, attestation)
    attestation_path = bundle_root / "operator-attestation.json"
    attestation_path.write_text(
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    identity = _write(
        bundle_root / "identity-review.txt", b"credential review passed\n"
    )
    opensees_license = _write(
        bundle_root / "opensees-legal-review.txt",
        b"approved for local commercial use\n",
    )
    calculix_license = _write(
        bundle_root / "calculix-legal-review.txt",
        b"approved for local commercial use\n",
    )
    private_key = bundle_root / "project-reviewer-private-key.pem"
    public_key = bundle_root / "project-reviewer-public-key.pem"
    signature_path = bundle_root / "project-review.sig"
    subprocess.run(
        [
            "openssl",
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private_key),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "openssl",
            "pkey",
            "-in",
            str(private_key),
            "-pubout",
            "-out",
            str(public_key),
        ],
        check=True,
        capture_output=True,
    )
    public_hash = module.file_sha256(public_key)
    opensees_runtime = _runtime(code, "openseespylinux")
    calculix_runtime = _runtime(code, "calculix-ccx")
    artifacts = [
        deepcopy(attestation["bundle"]["code_to_code"]),
        deepcopy(attestation["bundle"]["modal_buckling"]),
    ]
    promotion = {
        "schema_version": module.SCHEMA_VERSION,
        "promotion_id": "bounded-planar-level2-test",
        "source_commit_sha": source_commit,
        "reviewed_at": "2026-07-29T02:00:00+00:00",
        "operator_attestation": {
            "path": attestation_path.name,
            "file_sha256": module.file_sha256(attestation_path),
            "artifact_hash": module.artifact_hash(attestation),
        },
        "verification_matrix": verification_matrix,
        "project_reviewer": {
            "name": "Authorized Project Reviewer",
            "organization": "Structural Analysis Project",
            "role": "Verification authority reviewer",
            "contact": "reviewer@example.test",
            "authorized_for_project": True,
            "independent_from_operator": True,
            "signer_public_key_sha256": public_hash,
        },
        "identity_review": {
            "operator_identity_authenticated": True,
            "credentials_reference": "ticket://external-vv-identity-42",
            "credential_evidence": identity,
            "conflict_review_passed": True,
            "review_notes": "Credential ownership and organizational independence reviewed.",
        },
        "license_reviews": [
            {
                "solver": "OpenSees",
                "license_id": "OpenSees-license-project-review-v1",
                "approval_status": "approved",
                "local_execution_allowed": True,
                "commercial_use_allowed": True,
                "redistribution_allowed": False,
                "evidence": opensees_license,
            },
            {
                "solver": "CalculiX",
                "license_id": "CalculiX-GPL-project-review-v1",
                "approval_status": "approved",
                "local_execution_allowed": True,
                "commercial_use_allowed": True,
                "redistribution_allowed": False,
                "evidence": calculix_license,
            },
        ],
        "scientific_reviews": [
            {
                "category": "opensees_code_to_code",
                "reference": {
                    "name": "OpenSeesPy Linux runtime",
                    "version": opensees_runtime["version"],
                    "version_verified": True,
                    "independent_from_product": True,
                },
                "source": {
                    "url_or_doi": opensees_runtime["authority_url"],
                    "sha256": opensees_runtime["sha256"],
                },
                "artifacts": deepcopy(artifacts),
                "decision": decide_benchmark(
                    [
                        {
                            "metric_family": "opensees_external_comparison",
                            "contract_pass": True,
                        }
                    ],
                    decision="PASS",
                    evaluated_at="2026-07-29T01:55:00+00:00",
                ),
            },
            {
                "category": "second_solver_code_to_code",
                "reference": {
                    "name": "CalculiX ccx",
                    "version": calculix_runtime["version"],
                    "version_verified": True,
                    "independent_from_product": True,
                },
                "source": {
                    "url_or_doi": calculix_runtime["authority_url"],
                    "sha256": calculix_runtime["sha256"],
                },
                "artifacts": deepcopy(artifacts),
                "decision": decide_benchmark(
                    [
                        {
                            "metric_family": "calculix_external_comparison",
                            "contract_pass": True,
                        }
                    ],
                    decision="PASS",
                    evaluated_at="2026-07-29T01:56:00+00:00",
                ),
            },
        ],
        "declarations": {
            "operator_identity_authenticated": True,
            "conflict_review_passed": True,
            "legal_use_approved": True,
            "scientific_review_completed": True,
            "formal_level_2_promotion_approved": True,
            "release_authority_granted": False,
            "design_authority_granted": False,
        },
        "signature": {
            "algorithm": "rsa-sha256",
            "signed_payload_sha256": "sha256:" + "0" * 64,
            "public_key_path": public_key.name,
            "public_key_sha256": public_hash,
            "signature_path": signature_path.name,
            "signature_sha256": "sha256:" + "0" * 64,
        },
        "contract_pass": True,
        "claim_boundary": (
            "This project review authorizes only exact Verification Level 2 evidence "
            "slots for the signed bundle and source commit; it grants no design, release, "
            "commercial-equivalence, redistribution, or higher-level authority."
        ),
    }
    signed_payload = bundle_root / "project-review-payload.json"
    payload = module.promotion_signed_payload(promotion)
    signed_payload.write_bytes(payload)
    subprocess.run(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-sign",
            str(private_key),
            "-out",
            str(signature_path),
            str(signed_payload),
        ],
        check=True,
        capture_output=True,
    )
    promotion["signature"]["signed_payload_sha256"] = module.sha256_bytes(payload)
    promotion["signature"]["signature_sha256"] = module.file_sha256(signature_path)
    return promotion, bundle_root


def test_level2_promotion_schema_is_valid() -> None:
    schema = json.loads((ROOT / module.SCHEMA_PATH).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def test_complete_signed_review_emits_two_ready_level2_rows(tmp_path: Path) -> None:
    promotion, bundle_root = _build_promotion(tmp_path / "bundle")

    result = module.promote_external_vv_level2(
        promotion,
        bundle_root=bundle_root,
        expected_source_commit_sha=promotion["source_commit_sha"],
        repo_root=ROOT,
    )

    assert result["receipt"]["contract_pass"] is True
    assert result["receipt"]["verification_hierarchy_level_2_evidence_eligible"] is True
    assert result["receipt"]["verification_matrix_complete"] is True
    assert result["receipt"]["verification_matrix"]["requirement_count"] == 25
    assert result["receipt"]["claims"]["release_readiness"] is False
    assert {row["category"] for row in result["manifest"]["evidence"]} == {
        "opensees_code_to_code",
        "second_solver_code_to_code",
    }
    readiness = build_verification_hierarchy_readiness(result["manifest"]["evidence"])
    level_two = readiness["level_rows"][1]
    assert level_two["intrinsic_contract_pass"] is True
    assert level_two["promotion_contract_pass"] is False
    assert level_two["status"] == "blocked_by_prerequisite"


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (
            lambda value: value["identity_review"].update(
                {"operator_identity_authenticated": False}
            ),
            "level2_promotion_schema_invalid",
        ),
        (
            lambda value: value["scientific_reviews"][0]["source"].update(
                {"sha256": "sha256:" + "1" * 64}
            ),
            "level2_promotion_reference_runtime_binding_invalid",
        ),
        (
            lambda value: value["scientific_reviews"][1]["decision"].update(
                {"benchmark_credit": False}
            ),
            "level2_promotion_scientific_decision_invalid",
        ),
    ],
)
def test_identity_runtime_or_scientific_tamper_fails_closed(
    tmp_path: Path, mutation, error: str
) -> None:
    promotion, bundle_root = _build_promotion(tmp_path / error.replace(":", "-"))
    mutation(promotion)

    with pytest.raises(module.ExternalVVLevel2PromotionError, match=error):
        module.promote_external_vv_level2(
            promotion,
            bundle_root=bundle_root,
            expected_source_commit_sha=promotion["source_commit_sha"],
            repo_root=ROOT,
        )

    fresh, fresh_root = _build_promotion(tmp_path / "wrong-commit")
    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_source_commit_mismatch",
    ):
        module.promote_external_vv_level2(
            fresh,
            bundle_root=fresh_root,
            expected_source_commit_sha="0" * 40,
            repo_root=ROOT,
        )


def test_reused_operator_execution_and_wrong_commit_fail_closed(tmp_path: Path) -> None:
    promotion, bundle_root = _build_promotion(
        tmp_path / "reused", fresh_operator_execution=False
    )
    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_operator_attestation_invalid",
    ):
        module.promote_external_vv_level2(
            promotion,
            bundle_root=bundle_root,
            expected_source_commit_sha=promotion["source_commit_sha"],
            repo_root=ROOT,
        )


def test_deliberately_incomplete_matrix_cannot_be_promoted(tmp_path: Path) -> None:
    promotion, bundle_root = _build_promotion(tmp_path / "incomplete-matrix")
    matrix = module.vv_matrix.build_bounded_planar_external_vv_matrix(
        repo_root=ROOT,
        same_operator_supplemental_receipt_path=(
            bundle_root / "intentionally-missing-supplemental-receipt.json"
        ),
    )
    path = bundle_root / promotion["verification_matrix"]["path"]
    path.write_text(
        json.dumps(matrix, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    promotion["verification_matrix"].update(
        {
            "file_sha256": module.file_sha256(path),
            "artifact_hash": matrix["artifact_hash"],
        }
    )
    _resign_promotion(promotion, bundle_root)

    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_verification_matrix_incomplete",
    ):
        module.promote_external_vv_level2(
            promotion,
            bundle_root=bundle_root,
            expected_source_commit_sha=promotion["source_commit_sha"],
            repo_root=ROOT,
        )


def test_project_signature_tamper_fails_closed(tmp_path: Path) -> None:
    promotion, bundle_root = _build_promotion(tmp_path / "signature")
    signature = bundle_root / promotion["signature"]["signature_path"]
    signature.write_bytes(signature.read_bytes() + b"tamper")

    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_signature_artifact_hash_mismatch",
    ):
        module.promote_external_vv_level2(
            promotion,
            bundle_root=bundle_root,
            expected_source_commit_sha=promotion["source_commit_sha"],
            repo_root=ROOT,
        )
