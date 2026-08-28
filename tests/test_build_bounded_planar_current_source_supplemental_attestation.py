from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT / "scripts" / "build_bounded_planar_current_source_supplemental_attestation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_current_source_supplemental_attestation_tests",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
attestation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = attestation
SPEC.loader.exec_module(attestation)
MATRIX_SCRIPT = ROOT / "scripts" / "build_bounded_planar_external_vv_matrix.py"
MATRIX_SPEC = importlib.util.spec_from_file_location(
    "build_bounded_planar_external_vv_matrix_attested_supplement_tests",
    MATRIX_SCRIPT,
)
assert MATRIX_SPEC is not None and MATRIX_SPEC.loader is not None
matrix = importlib.util.module_from_spec(MATRIX_SPEC)
sys.modules[MATRIX_SPEC.name] = matrix
MATRIX_SPEC.loader.exec_module(matrix)


SOURCE_SHA = "a" * 40
HASH = "sha256:" + "b" * 64
REPOSITORY = "owner/repository"
STARTED = "2026-08-27T10:00:00+00:00"
COMPLETED = "2026-08-27T10:05:00+00:00"


def _family_row(family, run_id: int) -> dict:
    cases = []
    for case_id in family.case_ids:
        invoked = case_id != "bounded_planar_negative_invalid_geometry"
        cases.append(
            {
                "case_id": case_id,
                "technical_contract_pass": True,
                "verification_method": (
                    "external_solver_execution" if invoked else "independent_preflight"
                ),
                "external_engine_invoked": invoked,
                "result_path": f".ci/test/{family.family_id}/{case_id}.json",
                "result_file_sha256": HASH,
                "result_artifact_hash": HASH,
            }
        )
    return {
        "family_id": family.family_id,
        "artifact_root": f".ci/test/{family.family_id}/artifact",
        "artifact_name": f"{family.artifact_prefix}-{run_id}-1",
        "workflow": {
            "path": family.workflow_path,
            "name": family.workflow_name,
            "file_sha256": HASH,
            "run_metadata_path": f".ci/test/{family.family_id}/workflow-run.json",
            "run_metadata_file_sha256": HASH,
            "run_id": run_id,
            "run_attempt": 1,
            "event": "push",
            "run_started_at": STARTED,
            "completed_at": COMPLETED,
        },
        "technical_receipt": {
            "path": f".ci/test/{family.family_id}/technical-receipt.json",
            "file_sha256": HASH,
            "artifact_hash": HASH,
            "schema_version": family.receipt_schema_version,
        },
        "producer_seal": {
            "path": f".ci/test/{family.family_id}/producer-seal.json",
            "file_sha256": HASH,
            "artifact_hash": HASH,
        },
        "artifact_handoff": {
            "path": f".ci/test/{family.family_id}/artifact-handoff.json",
            "file_sha256": HASH,
        },
        "source_binding": {
            "source_tree_sha": "c" * 40,
            "tracked_tree_clean": True,
            "source_scope": "full_tracked_product_package_plus_family_control_plane",
            "tracked_product_file_count": 359,
            "tracked_product_python_count": 225,
            "source_file_count": 240,
        },
        "runtime_binding": {
            "all_external_runtime_assets_pre_execution_hash_locked": True,
            "runtime_asset_bytes_attached": True,
            "technical_authority_eligible": True,
            "wheel_asset_count": 2,
            "blockers": [],
        },
        "package_manifest": {
            "path": f".ci/test/{family.family_id}/manifest.json",
            "file_sha256": HASH,
            "artifact_hash": HASH,
        },
        "sigstore_bundle": {
            "path": f".ci/test/{family.family_id}/bundle.json",
            "file_sha256": HASH,
        },
        "attestation_verification": {
            "path": f".ci/test/{family.family_id}/verification.json",
            "file_sha256": HASH,
            "subject_sha256": HASH,
            "build_signer_uri": (
                f"https://github.com/{REPOSITORY}/{attestation.SIGNER_WORKFLOW_PATH}"
                "@refs/heads/main"
            ),
            "build_config_uri": (
                f"https://github.com/{REPOSITORY}/{family.workflow_path}"
                "@refs/heads/main"
            ),
            "source_repository_digest": SOURCE_SHA,
            "run_invocation_uri": (
                f"https://github.com/{REPOSITORY}/actions/runs/{run_id}/attempts/1"
            ),
            "runner_environment": "github-hosted",
        },
        "cases": cases,
        "technical_contract_pass": True,
        "fresh_current_source_technical_validation": True,
        "independent_operator_attested": False,
        "legal_use_approved": False,
        "verification_matrix_credit": False,
        "verification_level_2": False,
    }


def _payload() -> dict:
    families = [
        _family_row(family, 1000 + index)
        for index, family in enumerate(attestation.FAMILIES)
    ]
    payload = {
        "schema_version": attestation.SCHEMA_VERSION,
        "source_commit_sha": SOURCE_SHA,
        "repository": REPOSITORY,
        "input_root": ".ci/test",
        "generated_at": "2026-08-27T10:06:00+00:00",
        "execution_window": {"started_at": STARTED, "completed_at": COMPLETED},
        "families": families,
        "summary": {
            "family_count": 5,
            "attestation_count": 5,
            "case_count": 16,
            "technical_pass_count": 16,
            "external_engine_invoked_case_count": 15,
            "independent_preflight_case_ids": [
                "bounded_planar_negative_invalid_geometry"
            ],
        },
        "status": "technical_pass_non_promoting",
        "technical_contract_pass": True,
        "claims": {
            "exact_current_source_bound": True,
            "github_hosted_execution": True,
            "sigstore_attestations_reverified": True,
            "fresh_current_source_technical_validation": True,
            "fresh_current_source_external_execution_for_engine_cases": True,
            "same_operator_execution": True,
            "external_execution_reused": False,
            "actual_external_solver_execution": True,
            "producer_signing_privilege_separated": True,
            "runtime_byte_lock_complete": True,
            "independent_operator_attested": False,
            "legal_use_approved": False,
            "formal_promotion_receipt_attached": False,
            "verification_level_2": False,
            "design_authority": False,
            "commercial_equivalence": False,
            "release_readiness": False,
        },
        "blockers": [
            "independent_operator_attestation_missing",
            "product_legal_license_approval_missing",
            "scientific_promotion_decision_missing",
            "formal_level2_promotion_receipt_missing",
            "bounded_planar_profile_level2_not_achieved",
        ],
        "claim_boundary": "same-operator technical evidence only; no promotion authority",
        "execution_binding_hash": attestation.ZERO_HASH,
        "artifact_hash": attestation.ZERO_HASH,
    }
    payload["execution_binding_hash"] = attestation._execution_binding_hash(
        source_commit_sha=SOURCE_SHA,
        repository=REPOSITORY,
        families=families,
    )
    payload["artifact_hash"] = attestation._artifact_hash(payload)
    return payload


def _rehash(payload: dict) -> None:
    payload["execution_binding_hash"] = attestation._execution_binding_hash(
        source_commit_sha=payload["source_commit_sha"],
        repository=payload["repository"],
        families=payload["families"],
    )
    payload["artifact_hash"] = attestation._artifact_hash(payload)


def test_current_source_supplemental_attestation_schema_is_valid() -> None:
    schema = json.loads((ROOT / attestation.SCHEMA_PATH).read_text())
    Draft202012Validator.check_schema(schema)


def test_receipt_preserves_exact_technical_and_nonpromotion_boundary() -> None:
    payload = _payload()

    attestation._validate_receipt_structure(payload, repo_root=ROOT)

    assert payload["summary"]["technical_pass_count"] == 16
    assert payload["summary"]["external_engine_invoked_case_count"] == 15
    assert payload["summary"]["independent_preflight_case_ids"] == [
        "bounded_planar_negative_invalid_geometry"
    ]
    assert payload["claims"]["fresh_current_source_technical_validation"] is True
    assert payload["claims"]["independent_operator_attested"] is False
    assert payload["claims"]["legal_use_approved"] is False
    assert payload["claims"]["verification_level_2"] is False
    assert payload["claims"]["release_readiness"] is False


def test_public_validator_has_no_unverified_mode() -> None:
    with pytest.raises(TypeError, match="revalidate_inputs"):
        attestation.validate_receipt(
            _payload(),
            repo_root=ROOT,
            revalidate_inputs=False,
        )


def test_child_receipt_validation_uses_requested_repository_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = attestation.FAMILIES[0]
    observed: list[Path] = []
    monkeypatch.setattr(
        family.ingest_module,
        "_validate_receipt",
        lambda _receipt, repo_root: observed.append(repo_root),
    )

    attestation._receipt_validator(family, {}, repo_root=tmp_path)

    assert observed == [tmp_path]


def test_receipt_hash_tamper_fails_closed() -> None:
    payload = _payload()
    payload["families"][0]["workflow"]["run_id"] += 1

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="current_source_supplemental_attestation_hash_invalid",
    ):
        attestation._validate_receipt_structure(payload, repo_root=ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        "source_digest",
        "workflow_path",
        "invalid_geometry_invocation",
        "promotion_claim",
        "case_set",
    ],
)
def test_semantic_forgery_fails_closed(mutation: str) -> None:
    payload = _payload()
    if mutation == "source_digest":
        payload["families"][0]["attestation_verification"][
            "source_repository_digest"
        ] = "c" * 40
    elif mutation == "workflow_path":
        payload["families"][0]["workflow"]["path"] = ".github/workflows/forged.yml"
    elif mutation == "invalid_geometry_invocation":
        invalid = next(
            case
            for case in payload["families"][1]["cases"]
            if case["case_id"] == "bounded_planar_negative_invalid_geometry"
        )
        invalid["external_engine_invoked"] = True
        invalid["verification_method"] = "external_solver_execution"
        payload["summary"]["external_engine_invoked_case_count"] = 16
        payload["summary"]["independent_preflight_case_ids"] = []
    elif mutation == "promotion_claim":
        payload["claims"]["independent_operator_attested"] = True
    else:
        payload["families"][0]["cases"][0]["case_id"] = "forged_case"
    _rehash(payload)

    with pytest.raises(attestation.CurrentSourceSupplementalAttestationError):
        attestation._validate_receipt_structure(payload, repo_root=ROOT)


def _run(family) -> dict:
    return {
        "id": 12345,
        "run_attempt": 2,
        "name": family.workflow_name,
        "path": family.workflow_path,
        "event": "push",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": SOURCE_SHA,
        "run_started_at": STARTED,
        "updated_at": COMPLETED,
        "repository": {"full_name": REPOSITORY},
        "head_repository": {"full_name": REPOSITORY},
    }


def _verification(
    family,
    receipt_path: Path,
    bundle: dict,
    run: dict,
    *,
    repository: str = REPOSITORY,
    source_sha: str = SOURCE_SHA,
) -> list:
    source_uri = f"https://github.com/{repository}"
    signer_workflow_uri = (
        f"{source_uri}/{attestation.SIGNER_WORKFLOW_PATH}@refs/heads/main"
    )
    caller_workflow_uri = f"{source_uri}/{family.workflow_path}@refs/heads/main"
    invocation = f"{source_uri}/actions/runs/{run['id']}/attempts/{run['run_attempt']}"
    subject_hash = attestation._file_hash(receipt_path).removeprefix("sha256:")
    return [
        {
            "attestation": {"bundle": bundle},
            "verificationResult": {
                "mediaType": (
                    "application/vnd.dev.sigstore.verificationresult+json;version=0.1"
                ),
                "signature": {
                    "certificate": {
                        "subjectAlternativeName": signer_workflow_uri,
                        "githubWorkflowSHA": source_sha,
                        "githubWorkflowName": family.workflow_name,
                        "githubWorkflowRepository": repository,
                        "githubWorkflowRef": "refs/heads/main",
                        "buildSignerURI": signer_workflow_uri,
                        "buildSignerDigest": source_sha,
                        "buildConfigURI": caller_workflow_uri,
                        "buildConfigDigest": source_sha,
                        "sourceRepositoryURI": source_uri,
                        "sourceRepositoryDigest": source_sha,
                        "sourceRepositoryRef": "refs/heads/main",
                        "runnerEnvironment": "github-hosted",
                        "buildTrigger": run["event"],
                        "githubWorkflowTrigger": run["event"],
                        "runInvocationURI": invocation,
                    }
                },
                "verifiedIdentity": {"runnerEnvironment": "github-hosted"},
                "verifiedTimestamps": [
                    {"type": "Tlog", "timestamp": "2026-08-27T10:04:59Z"}
                ],
                "statement": {
                    "_type": "https://in-toto.io/Statement/v1",
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "subject": [
                        {
                            "name": "technical-receipt.json",
                            "digest": {"sha256": subject_hash},
                        }
                    ],
                    "predicate": {
                        "buildDefinition": {
                            "externalParameters": {
                                "workflow": {
                                    "path": family.workflow_path,
                                    "ref": "refs/heads/main",
                                    "repository": source_uri,
                                }
                            },
                            "resolvedDependencies": [
                                {
                                    "uri": f"git+{source_uri}@refs/heads/main",
                                    "digest": {"gitCommit": source_sha},
                                }
                            ],
                            "internalParameters": {
                                "github": {
                                    "event_name": run["event"],
                                    "runner_environment": "github-hosted",
                                }
                            },
                        },
                        "runDetails": {
                            "builder": {"id": signer_workflow_uri},
                            "metadata": {"invocationId": invocation},
                        },
                    },
                },
            },
        }
    ]


def test_sigstore_verification_binds_subject_signer_source_and_hosted_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]
    family_root = tmp_path / family.family_id
    artifact_root = family_root / "artifact"
    receipt_path = artifact_root / family.artifact_receipt_path
    bundle_path = artifact_root / family.artifact_bundle_path
    verification_path = family_root / "product-state-attestation-verification.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text('{"technical":true}\n')
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    bundle_path.write_text(json.dumps(bundle))
    run = _run(family)
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verified = _verification(family, receipt_path, bundle, run)
    verification_path.write_text(json.dumps(verified))
    monkeypatch.setattr(
        attestation,
        "_run_live_attestation_verification",
        lambda **_kwargs: verified,
    )

    _bundle, _verification_path, binding = attestation._validate_attestation(
        repo_root=tmp_path,
        family_root=family_root,
        artifact_root=artifact_root,
        family=family,
        repository=REPOSITORY,
        source_commit_sha=SOURCE_SHA,
        run=run,
        handoff_path=receipt_path,
    )

    assert binding["subject_sha256"] == attestation._file_hash(receipt_path)
    assert binding["runner_environment"] == "github-hosted"
    assert binding["source_repository_digest"] == SOURCE_SHA
    assert binding["build_signer_uri"].endswith(
        "/.github/workflows/bounded-planar-sealed-technical-attestor.yml@refs/heads/main"
    )
    assert binding["build_config_uri"].endswith(
        "/.github/workflows/bounded-planar-opensees-technical.yml@refs/heads/main"
    )

    bundle_path.write_text(json.dumps({"mediaType": "forged"}))
    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_attestation_bundle_binding_invalid:linear",
    ):
        attestation._validate_attestation(
            repo_root=tmp_path,
            family_root=family_root,
            artifact_root=artifact_root,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            run=run,
            handoff_path=receipt_path,
        )
    bundle_path.write_text(json.dumps(bundle))

    forged = _verification(family, receipt_path, bundle, run)
    forged[0]["verificationResult"]["signature"]["certificate"]["runnerEnvironment"] = (
        "self-hosted"
    )
    verification_path.write_text(json.dumps(forged))
    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_attestation_identity_invalid:linear",
    ):
        attestation._validate_attestation(
            repo_root=tmp_path,
            family_root=family_root,
            artifact_root=artifact_root,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            run=run,
            handoff_path=receipt_path,
        )


def test_live_verifier_uses_exact_fail_closed_gh_arguments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]
    receipt_path = tmp_path / "technical-receipt.json"
    bundle_path = tmp_path / "technical-receipt.sigstore.json"
    receipt_path.write_text('{"technical":true}\n')
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    bundle_path.write_text(json.dumps(bundle))
    run = _run(family)
    verified = _verification(family, receipt_path, bundle, run)
    expected_command = [
        "gh",
        "attestation",
        "verify",
        str(receipt_path),
        "--repo",
        REPOSITORY,
        "--bundle",
        str(bundle_path),
        "--signer-workflow",
        f"{REPOSITORY}/{attestation.SIGNER_WORKFLOW_PATH}",
        "--signer-digest",
        SOURCE_SHA,
        "--source-digest",
        SOURCE_SHA,
        "--source-ref",
        "refs/heads/main",
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]

    def fake_run(command, **kwargs):
        assert command == expected_command
        assert kwargs == {
            "cwd": tmp_path,
            "check": False,
            "capture_output": True,
            "text": True,
            "timeout": attestation.LIVE_ATTESTATION_VERIFY_TIMEOUT_SECONDS,
        }
        return attestation.subprocess.CompletedProcess(
            command, 0, stdout=json.dumps(verified), stderr=""
        )

    monkeypatch.setattr(attestation.subprocess, "run", fake_run)

    assert (
        attestation._run_live_attestation_verification(
            repo_root=tmp_path,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            subject_path=receipt_path,
            bundle_path=bundle_path,
        )
        == verified
    )


def test_fake_bundle_and_fake_cache_cannot_replace_live_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]
    family_root = tmp_path / family.family_id
    artifact_root = family_root / "artifact"
    receipt_path = artifact_root / family.artifact_receipt_path
    bundle_path = artifact_root / family.artifact_bundle_path
    verification_path = family_root / "product-state-attestation-verification.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text('{"technical":true}\n')
    fake_bundle = {"mediaType": "fabricated", "fabricated": True}
    bundle_path.write_text(json.dumps(fake_bundle))
    run = _run(family)
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_path.write_text(
        json.dumps(_verification(family, receipt_path, fake_bundle, run))
    )
    monkeypatch.setattr(
        attestation.subprocess,
        "run",
        lambda command, **_kwargs: attestation.subprocess.CompletedProcess(
            command, 1, stdout="", stderr="failed cryptographic verification"
        ),
    )

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_live_attestation_verification_failed:linear",
    ):
        attestation._validate_attestation(
            repo_root=tmp_path,
            family_root=family_root,
            artifact_root=artifact_root,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            run=run,
            handoff_path=receipt_path,
        )


def test_fake_run_metadata_and_matching_cache_cannot_override_live_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]
    family_root = tmp_path / family.family_id
    artifact_root = family_root / "artifact"
    receipt_path = artifact_root / family.artifact_receipt_path
    bundle_path = artifact_root / family.artifact_bundle_path
    verification_path = family_root / "product-state-attestation-verification.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text('{"technical":true}\n')
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    bundle_path.write_text(json.dumps(bundle))
    real_run = _run(family)
    forged_run = {**real_run, "id": 999999999}
    verification_path.parent.mkdir(parents=True, exist_ok=True)
    verification_path.write_text(
        json.dumps(_verification(family, receipt_path, bundle, forged_run))
    )
    live_result = _verification(family, receipt_path, bundle, real_run)
    monkeypatch.setattr(
        attestation,
        "_run_live_attestation_verification",
        lambda **_kwargs: live_result,
    )

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_attestation_identity_invalid:linear",
    ):
        attestation._validate_attestation(
            repo_root=tmp_path,
            family_root=family_root,
            artifact_root=artifact_root,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            run=forged_run,
            handoff_path=receipt_path,
        )


@pytest.mark.parametrize("mutation", ["repo", "signer", "source", "ref"])
def test_live_result_with_wrong_identity_filter_fails_closed(
    tmp_path: Path, mutation: str
) -> None:
    family = attestation.FAMILIES[0]
    receipt_path = tmp_path / "technical-receipt.json"
    receipt_path.write_text('{"technical":true}\n')
    bundle = {"mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json"}
    run = _run(family)
    forged = deepcopy(_verification(family, receipt_path, bundle, run))
    certificate = forged[0]["verificationResult"]["signature"]["certificate"]
    if mutation == "repo":
        certificate["githubWorkflowRepository"] = "evil/repository"
    elif mutation == "signer":
        certificate["buildSignerURI"] = "https://evil.example/forged"
    elif mutation == "source":
        certificate["sourceRepositoryDigest"] = "c" * 40
    else:
        certificate["sourceRepositoryRef"] = "refs/heads/evil"

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_attestation_identity_invalid:linear",
    ):
        attestation._validated_verification_document(
            verification_loaded=forged,
            bundle_loaded=bundle,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            run=run,
            subject_path=receipt_path,
        )


def test_missing_or_incompatible_gh_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]
    receipt_path = tmp_path / "technical-receipt.json"
    bundle_path = tmp_path / "technical-receipt.sigstore.json"
    receipt_path.write_text("{}\n")
    bundle_path.write_text("{}\n")
    monkeypatch.setattr(
        attestation.subprocess,
        "run",
        lambda command, **_kwargs: attestation.subprocess.CompletedProcess(
            command, 1, stdout="", stderr='unknown command "attestation"'
        ),
    )

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_live_attestation_verification_failed:linear",
    ):
        attestation._run_live_attestation_verification(
            repo_root=tmp_path,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            subject_path=receipt_path,
            bundle_path=bundle_path,
        )


def test_missing_gh_binary_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = attestation.FAMILIES[0]

    def missing_binary(*_args, **_kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(attestation.subprocess, "run", missing_binary)
    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_live_attestation_verifier_unavailable:linear",
    ):
        attestation._run_live_attestation_verification(
            repo_root=tmp_path,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
            subject_path=tmp_path / "technical-receipt.json",
            bundle_path=tmp_path / "technical-receipt.sigstore.json",
        )


def test_unsuccessful_or_wrong_source_workflow_run_fails_closed(
    tmp_path: Path,
) -> None:
    family = attestation.FAMILIES[0]
    run_path = tmp_path / "workflow-run.json"
    run = _run(family)
    run["conclusion"] = "failure"
    run_path.write_text(json.dumps(run))

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_workflow_run_contract_invalid:linear",
    ):
        attestation._validate_workflow_run(
            run_path=run_path,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
        )


@pytest.mark.parametrize("field", ["id", "run_attempt"])
def test_boolean_workflow_run_identity_fails_closed(
    tmp_path: Path,
    field: str,
) -> None:
    family = attestation.FAMILIES[0]
    run_path = tmp_path / "workflow-run.json"
    run = _run(family)
    run[field] = True
    run_path.write_text(json.dumps(run))

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_workflow_run_contract_invalid:linear",
    ):
        attestation._validate_workflow_run(
            run_path=run_path,
            family=family,
            repository=REPOSITORY,
            source_commit_sha=SOURCE_SHA,
        )


def test_unlisted_package_child_symlink_escape_fails_closed(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifact"
    package_root = artifact_root / "package"
    outside_root = tmp_path / "outside"
    package_root.mkdir(parents=True)
    outside_root.mkdir()
    (outside_root / "payload.json").write_text("{}")
    try:
        (package_root / "unlisted").symlink_to(
            outside_root,
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_package_file_set_invalid:linear",
    ):
        attestation._contained_tree_files(
            package_root,
            artifact_root,
            "supplemental_package_file_set_invalid:linear",
        )


def test_package_root_intermediate_symlink_escape_fails_closed(
    tmp_path: Path,
) -> None:
    family = attestation.FAMILIES[0]
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()
    try:
        (artifact_root / "artifacts").symlink_to(
            ROOT / "artifacts",
            target_is_directory=True,
        )
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(
        attestation.CurrentSourceSupplementalAttestationError,
        match="supplemental_package_root_invalid:linear",
    ):
        attestation._validate_package(
            repo_root=ROOT,
            artifact_root=artifact_root,
            family=family,
            source_commit_sha=SOURCE_SHA,
        )


def test_matrix_credits_sixteen_attested_rows_without_promoting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _payload()
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text("{}")
    for family in payload["families"]:
        child = {
            "source_commit_sha": SOURCE_SHA,
            "technical_contract_pass": True,
            "artifact_hash": matrix.ZERO_HASH
            if hasattr(matrix, "ZERO_HASH")
            else "sha256:" + "0" * 64,
        }
        child["artifact_hash"] = matrix._artifact_hash(child)
        child_path = tmp_path / f"{family['family_id']}.json"
        child_path.write_text(json.dumps(child))
        family["technical_receipt"].update(
            {
                "path": str(child_path),
                "file_sha256": matrix._file_sha256(child_path),
                "artifact_hash": child["artifact_hash"],
            }
        )
    payload["execution_binding_hash"] = attestation._execution_binding_hash(
        source_commit_sha=SOURCE_SHA,
        repository=REPOSITORY,
        families=payload["families"],
    )
    payload["artifact_hash"] = attestation._artifact_hash(payload)
    receipt_path.write_text(json.dumps(payload))
    monkeypatch.setattr(
        matrix.current_source_supplement,
        "validate_bundle",
        lambda **_kwargs: payload,
    )

    binding, child_payloads, child_bindings, requirements = (
        matrix._validated_attested_current_source_supplemental_execution(
            repo_root=tmp_path,
            receipt_path=receipt_path,
            expected_source_commit=SOURCE_SHA,
        )
    )

    assert binding["status"] == "attached_attested_current_source"
    assert binding["family_attestation_count"] == 5
    assert binding["external_engine_invoked_case_count"] == 15
    assert binding["independent_preflight_case_ids"] == [
        "bounded_planar_negative_invalid_geometry"
    ]
    assert binding["independent_operator_attested"] is False
    assert binding["product_legal_license_approval"] is False
    assert binding["verification_level_2"] is False
    matrix_schema = json.loads((ROOT / matrix.SCHEMA_PATH).read_text())
    Draft202012Validator(
        {
            "$ref": "#/$defs/currentSourceSupplementalBinding",
            "$defs": matrix_schema["$defs"],
        }
    ).validate(binding)
    assert len(child_payloads) == 5
    assert all(
        child["fresh_current_source_external_execution"] is True
        and child["external_execution_reused"] is False
        for child in child_bindings.values()
    )
    assert len(requirements) == 16

    core_case_ids = {
        "code_to_code": [
            "bounded_planar_member_feature_load_path",
            "bounded_planar_prescribed_settlement_load_path",
            "cantilever_tip_load",
        ],
        "modal_buckling": [
            "whole_model_frame_repeated_mode_linear_buckling",
        ],
    }
    core_payloads = {
        receipt_id: {
            "comparisons": [
                {"case_id": case_id, "contract_pass": True} for case_id in case_ids
            ]
        }
        for receipt_id, case_ids in core_case_ids.items()
    }
    core_bindings = {
        receipt_id: {
            "receipt_id": receipt_id,
            "path": str(tmp_path / f"{receipt_id}.json"),
            "artifact_hash": HASH,
            "technical_contract_pass": True,
            "current_product_replay_pass": True,
            "external_execution_reused": False,
            "fresh_current_source_external_execution": True,
            "external_engine_invoked_case_ids": case_ids,
        }
        for receipt_id, case_ids in core_case_ids.items()
    }
    rows = [
        matrix._requirement_row(
            dict(requirement),
            repo_root=tmp_path,
            payloads={**core_payloads, **child_payloads},
            bindings={**core_bindings, **child_bindings},
            supplemental_requirement_receipts=requirements,
            execution_package_requirement_ids=set(),
            current_source_prepared_requirement_ids=set(),
        )
        for requirement in matrix.REQUIREMENTS
    ]
    assert len(rows) == 25
    assert sum(row["fresh_current_source_technical_validation"] for row in rows) == 25
    assert sum(row["fresh_current_source_external_execution"] for row in rows) == 24
    assert (
        sum(row["status"] == "fresh_independent_preflight_technical" for row in rows)
        == 1
    )
    assert all(
        row["independent_operator_attested"] is False
        and row["legal_use_approved"] is False
        and row["scientific_decision_pass"] is False
        and row["formal_promotion_receipt_attached"] is False
        and row["level2_eligible"] is False
        for row in rows
    )


@pytest.mark.skipif(
    not (ROOT / attestation.DEFAULT_OUT).is_file(),
    reason="exact-SHA supplemental GitHub artifacts are not materialized locally",
)
def test_materialized_exact_sha_bundle_revalidates() -> None:
    payload = attestation.validate_bundle(repo_root=ROOT)

    assert payload["summary"]["technical_pass_count"] == 16
    assert payload["summary"]["external_engine_invoked_case_count"] == 15
    assert payload["claims"]["verification_level_2"] is False
    assert datetime.fromisoformat(payload["generated_at"]).tzinfo == timezone.utc
