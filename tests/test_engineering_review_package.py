"""Contracts for the fail-closed P2 engineering-review package."""

from __future__ import annotations

import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_engineering_review_package.py"
OUTPUT = ROOT / "artifacts/review/engineering_review_package.candidate.json"
SPEC = importlib.util.spec_from_file_location(
    "build_engineering_review_package", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _stored() -> dict:
    value = json.loads(OUTPUT.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _key_material() -> tuple[Ed25519PrivateKey, bytes, bytes, str]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    public_pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    public_der = public.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private, public_pem, public_der, module._hash_bytes(public_der)


def _trusted_registry(public_der: bytes, public_hash: str) -> dict:
    return {
        "schema_version": module.REGISTRY_SCHEMA_VERSION,
        "status": "configured",
        "reviewers": [
            {
                "reviewer_id": "independent-engineer-test",
                "display_name": "Ephemeral Test Reviewer",
                "organization": "Test V&V Laboratory",
                "role": "licensed_structural_engineer",
                "license_jurisdiction": "TEST-ONLY",
                "license_identifier": "EPHEMERAL-NOT-AUTHORITY",
                "independent_from_implementation_team": True,
                "authorization_status": "approved",
                "authorized_review_scopes": ["P2"],
                "public_key_sha256": public_hash,
                "public_key_spki_base64": base64.b64encode(public_der).decode("ascii"),
                "approved_by": "test-fixture-only",
                "approved_at": "2026-07-22T00:00:00Z",
            }
        ],
        "private_keys_in_repository": False,
        "claim_boundary": (
            "This registry exists only inside an ephemeral unit-test value. It does "
            "not authorize a real engineering reviewer, grant product authority, or "
            "persist a private key. Production authority requires an owner-reviewed "
            "checked-in registry entry with real licensure and independence evidence."
        ),
    }


def test_stored_candidate_is_current_unsigned_and_nonpromoting() -> None:
    package = _stored()

    assert (
        module.validate_engineering_review_package(
            package,
            repo_root=ROOT,
            require_current_sources=True,
        )
        == package
    )
    assert package["status"] == "blocked"
    assert package["contract_pass"] is True
    assert len(package["review_material"]["evidence_inventory"]) >= 20
    assert package["signature"]["state"] == "unsigned"
    assert package["reviewer_assertion"] is None
    assert package["claims"]["evidence_inventory_current"] is True
    assert package["claims"]["exact_current_head"] is False
    assert package["claims"]["trusted_reviewer"] is False
    assert package["claims"]["signature_verified"] is False
    assert package["claims"]["signed_engineering_review"] is False
    assert package["claims"]["release_authority"] is False
    assert "candidate_worktree_not_clean" in package["blockers_remaining"]
    assert (
        "trusted_engineering_reviewer_not_attached" in (package["blockers_remaining"])
    )


def test_rehashed_evidence_inventory_tampering_is_rejected() -> None:
    tampered = deepcopy(_stored())
    tampered["review_material"]["evidence_inventory"][0]["sha256"] = (
        "sha256:" + "f" * 64
    )
    tampered["review_material"]["evidence_set_hash"] = module._hash_value(
        tampered["review_material"]["evidence_inventory"]
    )
    tampered["review_material_hash"] = module._hash_value(tampered["review_material"])
    tampered["package_hash"] = module._package_hash(tampered)

    with pytest.raises(
        module.EngineeringReviewPackageError,
        match="review_evidence_inventory_stale",
    ):
        module.validate_engineering_review_package(
            tampered,
            repo_root=ROOT,
            require_current_sources=True,
        )


def test_valid_signature_from_unregistered_reviewer_is_rejected() -> None:
    package = _stored()
    private, public_pem, _, _ = _key_material()
    assertion = module.build_reviewer_assertion(
        package,
        reviewer_id="unregistered-reviewer",
        reviewed_at="2026-07-22T00:00:00Z",
        disposition="changes_required",
        decisions={key: False for key in module.REQUIRED_DECISION_IDS},
        review_notes="Test-only untrusted assertion.",
    )
    signature = private.sign(module.reviewer_assertion_bytes(assertion))

    with pytest.raises(
        module.EngineeringReviewPackageError,
        match="reviewer_not_authorized",
    ):
        module.attach_engineering_review(
            package,
            assertion=assertion,
            signature_bytes=signature,
            public_key_pem=public_pem,
            repo_root=ROOT,
        )


def test_complete_ephemeral_signature_path_requires_every_gate() -> None:
    private, public_pem, public_der, public_hash = _key_material()
    registry = _trusted_registry(public_der, public_hash)
    roadmap = deepcopy(
        json.loads((ROOT / module.ROADMAP_STATUS_PATH).read_text(encoding="utf-8"))
    )
    roadmap["authoritative_release_snapshot"] = True
    for key in roadmap["required_external_evidence"]:
        roadmap["required_external_evidence"][key] = True
    hierarchy = {"highest_verified_level": 3}
    exact_sha = "a" * 40
    package = module.build_engineering_review_package(
        repo_root=ROOT,
        roadmap_status=roadmap,
        hierarchy_status=hierarchy,
        trusted_registry=registry,
        source_state={
            "source_commit_sha": exact_sha,
            "remote_default_branch_head": exact_sha,
            "worktree_clean": True,
            "authoritative_release_snapshot": True,
            "assessment_scope": "ephemeral_complete_test_fixture",
        },
        require_current_sources=False,
    )
    assert package["claims"]["ready_for_external_review"] is True
    assert package["claims"]["signed_engineering_review"] is False

    assertion = module.build_reviewer_assertion(
        package,
        reviewer_id="independent-engineer-test",
        reviewed_at="2026-07-22T00:00:00Z",
        disposition="approved_for_p2_closure",
        decisions={key: True for key in module.REQUIRED_DECISION_IDS},
        review_notes="Ephemeral positive-path contract test only.",
    )
    signature = private.sign(module.reviewer_assertion_bytes(assertion))
    signed = module.attach_engineering_review(
        package,
        assertion=assertion,
        signature_bytes=signature,
        public_key_pem=public_pem,
        repo_root=ROOT,
        trusted_registry=registry,
        require_current_sources=False,
    )

    assert signed["status"] == "approved"
    assert signed["blockers_remaining"] == []
    assert signed["claims"]["exact_current_head"] is True
    assert signed["claims"]["prerequisite_evidence_pass"] is True
    assert signed["claims"]["trusted_reviewer"] is True
    assert signed["claims"]["signature_verified"] is True
    assert signed["claims"]["required_decisions_approved"] is True
    assert signed["claims"]["signed_engineering_review"] is True
    assert signed["claims"]["release_authority"] is False

    tampered = deepcopy(signed)
    tampered["reviewer_assertion"]["review_notes"] = "tampered after signing"
    tampered["package_hash"] = module._package_hash(tampered)
    with pytest.raises(
        module.EngineeringReviewPackageError,
        match="review_signed_payload_hash_mismatch",
    ):
        module.validate_engineering_review_package(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
            trusted_registry=registry,
        )


def test_cli_check_validates_stored_candidate() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr + completed.stdout
    assert "engineering_review_package_current" in completed.stdout
