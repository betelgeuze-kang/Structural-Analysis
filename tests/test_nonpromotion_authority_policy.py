from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from scripts import build_product_state
from scripts import build_product_state_provenance_bundle as provenance
from scripts.nonpromotion_authority_policy import (
    AuthorityPolicyError,
    POLICY_PATH,
    load_authority_policy,
    promoted_authority_violations,
)


ROOT = Path(__file__).resolve().parents[1]


def test_production_policy_contains_current_authority_boundary() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)

    assert {
        "commercial_use_authority",
        "formal_verification_level_2",
        "independent_operator_attestation",
        "independent_operator_attested",
        "independent_operator_identity_authentication",
        "independent_verification_level_2",
        "legal_authority",
        "paid_pilot",
        "paid_pilot_ready",
        "product_legal_approval",
        "redistribution_authority",
        "release_allowed",
        "release_authority",
        "release_eligible",
        "third_party_material_redistribution_approved",
        "verification_level_2",
    } <= policy.prohibited_keys
    assert {
        "actual_external_solver_execution",
        "fresh_current_source_external_matrix_complete",
        "fresh_current_source_technical_matrix_complete",
        "internal_due_diligence_complete",
        "license_inventory_complete",
        "recommended_matrix_technical_coverage_complete",
        "redistribution_boundaries_explicit",
        "source_use_declarations_complete",
        "spdx_notices_complete",
    } <= policy.allowed_true_technical_completeness
    assert policy.allowed_technical_grants == {
        "bounded_developer_preview_technical_claims"
    }
    assert policy.negative_authority_token_containers == {
        "does_not_grant",
        "required_for",
    }
    assert policy.safe_statuses == {
        "blocked",
        "denied",
        "false",
        "not_established",
        "not_granted",
        "pending",
        "unavailable",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"RELEASE_AUTHORITY": True},
        {"ＲＥＬＥＡＳＥ_authority": True},
        {"releаse_authority": True},  # Cyrillic small a.
        {"release_authority\u200b": True},
        {"release_authority\n": True},
        {"releaseAuthority": True},
        {"releaseAUTHORity": True},
        {"releaseAUTHORity": False},
        {"release-authority": True},
        {"re-lease-authority": True},
        {"re-lease-authority": False},
        {"release_authority_confirmed": True},
        {"is_release_authority": True},
        {"paid_pilot_ready_flag": True},
        {"independent_verification_level_2_status": True},
        {"paid_pilot": True},
        {"paid_pilot_ready": True},
        {"commercial": True},
        {"independent": True},
        {"legal": True},
        {"nested": [{"commercialAUTHORity": True}]},
        {"nested": [{"legal-authority": True}]},
        {"nested": [{"Independent_Operator_Attested": True}]},
        {"evidence": ["releaseAuthority"]},
        {"evidence": ["RELEASE-AUTHORITY"]},
        {"evidence": ["releаse_authority"]},
        {"evidence": ["indepen-dent-verification-level-2"]},
        {"evidence": ["paid-pilot"]},
        {"evidence": ["release_authority_confirmed"]},
        {"grants": ["release_authority"]},
        {"grants": ["unreviewed_technical_authority"]},
        {"grants": "bounded_developer_preview_technical_claims"},
        {"grants": [{"bounded_developer_preview_technical_claims": True}]},
        {"does_not_grant": ["ReleaseAuthority"]},
        {"does-not-grant": ["indepen-dent-verification-level-2"]},
        {"does_not_grant": ["release_authority_confirmed"]},
        {"does_not_grant": "release_authority"},
        {"does_not_grant": [{"release_authority": False}]},
        {
            "release_authority": {
                "status": "unavailable",
                "value": True,
            }
        },
        {"claims": {"unregistered_technical_completion": True}},
        {"stored_claims": {"future_release_alias": True}},
        {"effective_claims": {"sale_ready": 1}},
    ],
)
def test_production_policy_rejects_recursive_authority_bypasses(
    payload: dict[str, object],
) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)

    assert promoted_authority_violations(payload, policy)


def test_production_policy_allows_only_declared_technical_completeness() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"claims": {key: True for key in policy.allowed_true_technical_completeness}}
    payload["release_authority"] = {"status": "unavailable"}
    payload["grants"] = ["bounded_developer_preview_technical_claims"]
    payload["does_not_grant"] = [
        "release_authority",
        "product_legal_license_approval",
        "independent_verification_level_2",
    ]
    payload["blockers_remaining"] = [
        "release_authority_confirmed_missing",
        "paid_pilot_ready_flag_not_established",
    ]

    assert promoted_authority_violations(payload, policy) == []


@pytest.mark.parametrize("wrapper", ["future", "evidence", "nested_claims"])
def test_allowlisted_true_claim_cannot_be_transplanted(wrapper: str) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {wrapper: {"actual_external_solver_execution": True}}

    assert promoted_authority_violations(payload, policy)


@pytest.mark.parametrize("key", ["actualExternalSolverExecution", "actual-external-solver-execution", "ACTUAL_EXTERNAL_SOLVER_EXECUTION"])
def test_allowlisted_claim_key_must_itself_be_canonical(key: str) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)

    assert promoted_authority_violations({"claims": {key: True}}, policy)


@pytest.mark.parametrize(
    "key",
    [
        "release_ready",
        "release_permitted",
        "go_live",
        "scientific_validation",
        "scientific_decision_pass",
        "commercially_ready",
        "redistributable",
        "production_ready",
        "general_availability",
        "level2_eligible",
        "operator_identity_credentials_verified",
        "certified_for_design",
    ],
)
def test_future_semantic_authority_aliases_are_rejected_at_arbitrary_paths(
    key: str,
) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)

    assert promoted_authority_violations({"future": {key: True}}, policy)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("release_files", ["artifact.json"]),
        ("release_tag", "v0.4.0"),
        ("release_version", "0.4.0"),
        ("scientific_metric_count", 12),
        ("production_runtime_hash", "sha256:" + "0" * 64),
    ],
)
def test_neutral_technical_metadata_is_not_a_semantic_authority_alias(
    key: str, value: object
) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)

    assert promoted_authority_violations({"future": {key: value}}, policy) == []


@pytest.mark.parametrize("value", [True, 1, "approved", {"status": "ready"}, ["ready"]])
@pytest.mark.parametrize(
    "path",
    ["quality_evidence", "bounded_planar_external_vv", "internal_license_evidence"],
)
def test_open_product_objects_reject_unknown_truthy_values(path: str, value: object) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    if path == "internal_license_evidence":
        payload = {"authority_tracks": {"internal_license_due_diligence": {"evidence": {"go_live_authority": value}}}}
    else:
        payload = {path: {"go_live_authority": value}}

    assert promoted_authority_violations(payload, policy)


@pytest.mark.parametrize("metadata_key", ["workflow_name", "head_sha", "run_id"])
def test_allowed_quality_metadata_rejects_nested_authority_payload(metadata_key: str) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"quality_evidence": {metadata_key: {"future_go_live": True}}}

    assert promoted_authority_violations(payload, policy)


@pytest.mark.parametrize("value", [1, "1", {"count": 1}, [1]])
def test_result_authority_counts_reject_unknown_or_wrong_shape(value: object) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"result_authority": {"numerical_authority_counts": {"release_grade": value}}}

    assert promoted_authority_violations(payload, policy)


@pytest.mark.parametrize("value", [True, 1, "ready", {"status": "ready"}, ["ready"]])
def test_bounded_planar_nested_metadata_rejects_unknown_truthy_descendants(value: object) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"bounded_planar_external_vv": {"operator_intake_binding": {"future_go_live": value}}}

    assert promoted_authority_violations(payload, policy)


@pytest.mark.parametrize("key", ["level2_eligible", "scientific_decision_pass", "attestation_attached", "operator_identity_credentials_verified"])
def test_bounded_summary_rejects_transplanted_known_keys(key: str) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    assert promoted_authority_violations({"bounded_planar_external_vv": {"summary": {key: True}}}, policy)


def test_execution_package_rejects_sigstore_field_transplant() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"bounded_planar_external_vv": {"execution_package_binding": {"sigstore_attestations_reverified": True}}}
    assert promoted_authority_violations(payload, policy)


def test_execution_workflow_integrity_digest_is_allowed_only_at_exact_path() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    digest = "sha256:" + "a" * 64
    exact = {
        "bounded_planar_external_vv": {
            "execution_package_binding": {
                "execution_workflow": {
                    "repository_path": ".github/workflows/external-vv.yml",
                    "packaged_path": "workflow/external-vv.yml",
                    "file_sha256": digest,
                }
            }
        }
    }
    transplanted = deepcopy(exact)
    workflow = transplanted["bounded_planar_external_vv"][
        "execution_package_binding"
    ]["execution_workflow"]
    workflow["future_file_sha256"] = workflow.pop("file_sha256")

    assert promoted_authority_violations(exact, policy) == []
    assert promoted_authority_violations(transplanted, policy)


def test_internal_license_claims_reject_external_execution_claim() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {"authority_tracks": {"internal_license_due_diligence": {"claims": {"actual_external_solver_execution": True}}}}
    assert promoted_authority_violations(payload, policy)


def test_production_policy_allows_only_allowlisted_true_open_claims() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = {
        "claims": {
            "actual_external_solver_execution": True,
            "recommended_matrix_technical_coverage_complete": True,
            "release_authority": False,
        },
        "stored_claims": {},
        "effective_claims": {"release_authority": False},
    }

    assert promoted_authority_violations(payload, policy) == []


@pytest.mark.parametrize(
    "relative_path",
    [
        "implementation/phase1/release_evidence/productization/"
        "external_code_to_code_technical_execution_receipt.json",
        "implementation/phase1/release_evidence/productization/"
        "external_modal_buckling_technical_execution_receipt.json",
    ],
)
def test_current_external_receipt_true_claims_are_explicitly_allowlisted(
    relative_path: str,
) -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    payload = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))

    assert promoted_authority_violations(payload, policy) == []


def test_actual_generated_product_state_passes_shared_policy() -> None:
    policy = load_authority_policy(ROOT / POLICY_PATH)
    current, _ = build_product_state.build_product_state(ROOT)

    assert promoted_authority_violations(current, policy) == []


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload["authority_tracks"][
            "solo_developer_technical"
        ].__setitem__("grants", ["release_authority"]),
        lambda payload: payload["authority_tracks"][
            "solo_developer_technical"
        ].__setitem__("grants", ["product_legal_license_approval"]),
        lambda payload: payload["authority_tracks"][
            "solo_developer_technical"
        ].__setitem__("grants", ["independent_verification_level_2"]),
        lambda payload: payload["quality_evidence"].update(
            independentVerificationLevel2=True
        ),
        lambda payload: payload["quality_evidence"].update(releaseAuthority=True),
        lambda payload: payload["authority_tracks"][
            "internal_license_due_diligence"
        ]["claims"].update(release_authority_confirmed=True),
        lambda payload: payload["authority_tracks"][
            "internal_license_due_diligence"
        ]["claims"].update(is_release_authority=True),
        lambda payload: payload["authority_tracks"][
            "internal_license_due_diligence"
        ]["claims"].update(paid_pilot_ready_flag=True),
        lambda payload: payload["authority_tracks"][
            "internal_license_due_diligence"
        ]["claims"].update(independent_verification_level_2_status=True),
        lambda payload: payload["authority_tracks"][
            "internal_license_due_diligence"
        ]["claims"].update(unregistered_future_claim=True),
    ],
)
def test_actual_product_schema_cannot_bypass_production_authority_policy(
    mutation,
) -> None:
    current, _ = build_product_state.build_product_state(ROOT)
    payload = deepcopy(current)
    mutation(payload)
    schema = json.loads(
        (ROOT / "canonical/product-state.current.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator(schema).validate(payload)
    overlay = {
        "external_vv_nonpromotion": {
            "effective_claims": {
                key: False for key in provenance.NONPROMOTING_EFFECTIVE_CLAIMS
            }
        }
    }

    with pytest.raises(
        provenance.ProductStateProvenanceError,
        match="product_state_high_risk_authority_value",
    ):
        provenance._validate_product_state_authority(payload, overlay)


def test_production_policy_rejects_noncanonical_policy_key(tmp_path: Path) -> None:
    source = (ROOT / POLICY_PATH).read_text(encoding="utf-8")
    target = tmp_path / "policy.json"
    target.write_text(
        source.replace('"release_authority"', '"ＲＥＬＥＡＳＥ_authority"'),
        encoding="utf-8",
    )

    with pytest.raises(
        AuthorityPolicyError, match="prohibited_keys_invalid|key_invalid"
    ):
        load_authority_policy(target)
