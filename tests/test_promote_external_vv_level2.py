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
    attestation["bundle"].pop("additional_receipts", None)
    operator_fixture._resign(attestation, bundle_root)
    try:
        matrix = module.operator_matrix.build_operator_attested_matrix(
            attestation,
            bundle_root=bundle_root,
            expected_source_commit_sha=source_commit,
            repo_root=ROOT,
        )
    except module.operator_matrix.OperatorMatrixBuildError:
        # Deliberately stale operator fixtures must reach the promotion entry
        # point so that its attestation gate is exercised. The matrix carries
        # no promotion authority in that negative path.
        matrix = module.vv_matrix.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            same_operator_supplemental_receipt_path=(
                bundle_root / "intentionally-unavailable-supplement.json"
            ),
        )
    assert matrix["source_commit_sha"] == source_commit
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


def test_bundle_supplied_reviewer_key_cannot_self_promote() -> None:
    attacker_key = "sha256:" + "9" * 64
    promotion = {
        "signature": {"public_key_sha256": attacker_key},
    }
    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_project_signer_not_approved",
    ):
        module._require_repo_owned_signer(promotion, repo_root=ROOT)


def test_level2_trust_registry_is_empty_deny_by_default() -> None:
    registry = json.loads((ROOT / module.TRUST_REGISTRY_PATH).read_text())
    assert registry["approved_signers"] == []
    assert registry["revocations"] == []


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        (
            lambda registry: registry["revocations"].append(
                {
                    "public_key_sha256": "sha256:" + "1" * 64,
                    "revoked_at_epoch": 2,
                }
            ),
            "level2_promotion_project_signer_revoked",
        ),
        (
            lambda registry: registry["approved_signers"][0].update(
                {"source_commit_sha": "2" * 40}
            ),
            "level2_promotion_trusted_decision_binding_invalid",
        ),
        (
            lambda registry: registry["approved_signers"][0]["runtime_assets"][0].update(
                {"sha256": "sha256:" + "3" * 64}
            ),
            "level2_promotion_trusted_runtime_binding_invalid",
        ),
        (
            lambda registry: registry["approved_signers"][0]["license_reviews"][0].update(
                {"commercial_use_allowed": False}
            ),
            "level2_promotion_trusted_license_decision_invalid",
        ),
    ],
)
def test_trust_registry_revocation_source_and_runtime_are_exact(
    monkeypatch: pytest.MonkeyPatch, mutation, error: str
) -> None:
    key_hash = "sha256:" + "1" * 64
    source = "a" * 40
    reviewer = {
        "name": "Authorized Project Reviewer",
        "organization": "Structural Analysis Project",
        "role": "Verification authority reviewer",
        "contact": "reviewer@example.test",
        "authorized_for_project": True,
        "independent_from_operator": True,
        "signer_public_key_sha256": key_hash,
    }
    license_rows = [
        {
            "solver": solver,
            "license_id": f"{solver}-review-v1",
            "approval_status": "approved",
            "local_execution_allowed": True,
            "commercial_use_allowed": True,
            "redistribution_allowed": False,
            "evidence": {"file_sha256": "sha256:" + digit * 64},
        }
        for solver, digit in (("OpenSees", "4"), ("CalculiX", "5"))
    ]
    runtime_assets = [
        {
            "distribution": distribution,
            "version": "1.0",
            "sha256": "sha256:" + digit * 64,
            "authority_url": f"https://example.test/{distribution}",
        }
        for distribution, digit in (("openseespylinux", "6"), ("calculix-ccx", "7"))
    ]
    promotion = {
        "source_commit_sha": source,
        "signature": {"public_key_sha256": key_hash},
        "project_reviewer": reviewer,
        "identity_review": {
            "credential_evidence": {"file_sha256": "sha256:" + "8" * 64}
        },
        "license_reviews": license_rows,
    }
    registry = {
        "schema_version": "external-vv-level2-trust-registry.v1",
        "registry_epoch": 2,
        "approved_signers": [
            {
                "public_key_sha256": key_hash,
                "approval_epoch": 2,
                "source_commit_sha": source,
                "reviewer": reviewer,
                "identity_evidence_sha256": "sha256:" + "8" * 64,
                "license_reviews": [
                    {
                        "solver": row["solver"],
                        "license_id": row["license_id"],
                        "local_execution_allowed": True,
                        "commercial_use_allowed": True,
                        "redistribution_allowed": False,
                        "evidence_sha256": row["evidence"]["file_sha256"],
                    }
                    for row in license_rows
                ],
                "runtime_assets": deepcopy(runtime_assets),
            }
        ],
        "revocations": [],
        "claim_boundary": "test registry",
    }
    mutation(registry)
    monkeypatch.setattr(module, "_load_trust_registry", lambda _repo_root: registry)
    with pytest.raises(module.ExternalVVLevel2PromotionError, match=error):
        module._validate_repo_owned_trust(
            promotion,
            child_receipts=[{"external_assets": runtime_assets}],
            repo_root=ROOT,
        )


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
        match="level2_promotion_verification_matrix_replay_mismatch",
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


@pytest.mark.parametrize(
    "payload",
    [
        '{"promotion_id":"a","promotion_id":"b"}',
        '{"value":NaN}',
        '{"value":Infinity}',
        '{"value":1e9999}',
    ],
)
def test_level2_promotion_rejects_ambiguous_json_at_first_boundary(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "promotion.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(module.ExternalVVLevel2PromotionError):
        module._load_json(path, "level2_promotion_json_invalid")


def test_level2_promotion_rejects_intermediate_symlink(tmp_path: Path) -> None:
    root = tmp_path / "bundle"
    real = root / "real"
    real.mkdir(parents=True)
    (real / "matrix.json").write_text("{}\n", encoding="utf-8")
    (root / "linked").symlink_to(real, target_is_directory=True)

    with pytest.raises(
        module.ExternalVVLevel2PromotionError,
        match="level2_promotion_symlink_rejected",
    ):
        module._bundle_file(root, "linked/matrix.json")
