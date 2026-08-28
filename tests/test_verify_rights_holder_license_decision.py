from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

from tests.license_decision_test_support import (
    DECISION_ID,
    EXPIRES_AT_UTC,
    ISSUED_AT_UTC,
    PRODUCT_SCOPE,
    RIGHTS_HOLDER_ID,
    build_signed_decision_repository,
    sign_decision,
    write_json,
)
from verify_rights_holder_license_decision import (
    inspect_rights_holder_license_decision,
)
import verify_rights_holder_license_decision as decision_verifier


def _inspect(fixture: dict, **overrides: object) -> dict:
    arguments = {
        "decision_path": fixture["decision_path"],
        "trust_root_path": fixture["trust_root_path"],
        "repo_root": fixture["repo_root"],
        "expected_source_commit_sha": fixture["source_commit_sha"],
        "expected_decision_id": DECISION_ID,
        "expected_license_id": "LIC-001",
        "expected_tier": "limited-commercial",
        "expected_approver_role": "product_owner",
        "expected_product_scope": list(PRODUCT_SCOPE),
        "expected_rights_holder_id": RIGHTS_HOLDER_ID,
        "expected_approved_at_utc": ISSUED_AT_UTC,
        "expected_expires_at_utc": EXPIRES_AT_UTC,
    }
    arguments.update(overrides)
    return inspect_rights_holder_license_decision(**arguments)


def test_signed_rights_holder_decision_requires_all_exact_bindings(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is True
    assert payload["blockers"] == []
    assert payload["signature_verified"] is True
    assert payload["decision_id_binding_pass"] is True
    assert payload["subject_binding_pass"] is True
    assert payload["repository_license_source_binding_pass"] is True
    assert payload["trust_root_source_binding_pass"] is True
    assert payload["canonical_trust_root_pass"] is True
    assert payload["public_key_source_binding_pass"] is True
    assert payload["license_policy_source_binding_pass"] is True
    assert payload["license_policy_version"] == "test-policy-v1"
    assert payload["covered_first_party_paths"]
    assert payload["public_key_bits"] == 2048
    assert payload["public_key_exponent"] == 65537
    assert payload["timeline_and_expiry_pass"] is True
    assert payload["replay_scope_pass"] is True
    assert payload["commercial_use_approved"] is True
    assert payload["redistribution_approved"] is True
    assert payload["third_party_material_redistribution_approved"] is False
    assert payload["release_authority"] is False


@pytest.mark.parametrize(
    ("mutation", "overrides", "expected_blocker"),
    [
        (
            lambda decision: decision["subject"].update(source_commit_sha="0" * 40),
            {},
            "rights_holder_decision_subject_binding_mismatch",
        ),
        (
            lambda decision: decision["subject"].update(
                repository_license_sha256="sha256:" + "0" * 64
            ),
            {},
            "rights_holder_decision_subject_binding_mismatch",
        ),
        (
            lambda decision: decision.update(decision_id="RH-LICENSE-DECISION-OTHER"),
            {},
            "rights_holder_decision_id_binding_mismatch",
        ),
        (
            lambda decision: decision["subject"].update(approver_role="legal_counsel"),
            {},
            "rights_holder_decision_subject_binding_mismatch",
        ),
        (
            lambda decision: decision.update(replay_policy="unbounded"),
            {},
            "rights_holder_decision_replay_policy_invalid",
        ),
        (
            lambda decision: decision["grants"].update(commercial_use_approved=False),
            {},
            "rights_holder_decision_grants_invalid",
        ),
        (
            lambda decision: decision.update(
                expires_at_utc="2021-06-10T00:00:00+00:00"
            ),
            {"expected_expires_at_utc": "2021-06-10T00:00:00+00:00"},
            "rights_holder_decision_timeline_invalid_or_expired",
        ),
    ],
)
def test_signed_decision_rejects_policy_subject_replay_or_expiry_mismatch(
    tmp_path: Path,
    mutation,
    overrides: dict,
    expected_blocker: str,
) -> None:
    fixture = build_signed_decision_repository(tmp_path, mutate_decision=mutation)

    payload = _inspect(fixture, **overrides)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert expected_blocker in payload["blockers"]
    assert payload["commercial_use_approved"] is False
    assert payload["redistribution_approved"] is False


def test_signed_decision_rejects_tampered_payload_and_signature(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    decision = json.loads(fixture["decision_path"].read_text(encoding="utf-8"))
    decision["subject"]["tier"] = "paid-pilot"
    write_json(fixture["decision_path"], decision)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is False
    assert "rights_holder_decision_signed_payload_hash_mismatch" in payload["blockers"]
    assert "rights_holder_decision_signature_not_verified" in payload["blockers"]


@pytest.mark.parametrize(
    ("fixture_options", "expected_blocker"),
    [
        (
            {"approve_signer": False},
            "rights_holder_decision_signer_not_uniquely_approved",
        ),
        (
            {"revoke_signer": True},
            "rights_holder_decision_signer_revoked",
        ),
        (
            {"revoke_decision": True},
            "rights_holder_decision_revoked",
        ),
    ],
)
def test_signed_decision_rejects_unapproved_or_revoked_authority(
    tmp_path: Path,
    fixture_options: dict,
    expected_blocker: str,
) -> None:
    fixture = build_signed_decision_repository(tmp_path, **fixture_options)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert expected_blocker in payload["blockers"]
    assert payload["commercial_use_approved"] is False
    assert payload["release_authority"] is False


@pytest.mark.parametrize(
    "mutate_signer",
    [
        lambda signer: signer.update(allowed_license_ids=["LIC-OTHER"]),
        lambda signer: signer.update(allowed_tiers=["paid-pilot"]),
        lambda signer: signer.update(allowed_approver_roles=["legal_counsel"]),
        lambda signer: signer.update(
            allowed_repository_license_sha256="sha256:" + "0" * 64
        ),
        lambda signer: signer["allowed_license_policy"].update(
            version="different-policy-v2"
        ),
    ],
)
def test_approved_signer_must_be_enrolled_for_exact_license_policy(
    tmp_path: Path,
    mutate_signer,
) -> None:
    fixture = build_signed_decision_repository(tmp_path, mutate_signer=mutate_signer)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert payload["signer_policy_authorized_pass"] is False
    assert "rights_holder_signer_policy_not_authorized" in payload["blockers"]


def test_trust_root_must_be_exact_blob_from_subject_source_commit(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fixture["trust_root_path"].write_text(
        fixture["trust_root_path"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert payload["trust_root_source_binding_pass"] is False
    assert "rights_holder_trust_root_not_exact_source_blob" in payload["blockers"]


def test_root_license_and_public_key_must_be_exact_source_blobs(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fixture["license_path"].write_text(
        fixture["license_path"].read_text(encoding="utf-8") + "changed\n",
        encoding="utf-8",
    )
    fixture["public_key"].write_text(
        fixture["public_key"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert "repository_license_not_exact_source_blob" in payload["blockers"]
    assert "rights_holder_public_key_not_exact_source_blob" in payload["blockers"]
    assert "rights_holder_public_key_hash_mismatch" in payload["blockers"]


def test_rsa_key_smaller_than_2048_bits_is_rejected(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path, rsa_bits=1024)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is False
    assert "rights_holder_public_key_too_small" in payload["blockers"]


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_entire_source_worktree_must_match_subject_commit(
    tmp_path: Path,
    dirty_kind: str,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    if dirty_kind == "tracked":
        (tmp_path / ".gitignore").write_text(
            "license_status.json\ntest-private-key.pem\nchanged\n",
            encoding="utf-8",
        )
    else:
        source = tmp_path / "src" / "product.py"
        source.parent.mkdir(parents=True)
        source.write_text("release_authority = True\n", encoding="utf-8")
        exclude = tmp_path / ".git" / "info" / "exclude"
        exclude.write_text("src/product.py\n", encoding="utf-8")

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert payload["source_worktree_binding_pass"] is False
    assert "repository_worktree_not_exact_source_commit" in payload["blockers"]


def test_assume_unchanged_cannot_hide_modified_tracked_source(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    subprocess.run(
        ["git", "update-index", "--assume-unchanged", ".gitignore"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / ".gitignore").write_text("malicious\n", encoding="utf-8")

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["source_worktree_binding_pass"] is False
    assert "repository_worktree_not_exact_source_commit" in payload["blockers"]


def test_local_core_worktree_redirect_cannot_hide_dirty_source(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path / "repo")
    clean_mirror = tmp_path / "clean-mirror"
    subprocess.run(
        ["git", "clone", "-q", str(fixture["repo_root"]), str(clean_mirror)],
        check=True,
    )
    subprocess.run(
        ["git", "config", "core.worktree", str(clean_mirror)],
        cwd=fixture["repo_root"],
        check=True,
    )
    (fixture["repo_root"] / ".gitignore").write_text("malicious\n", encoding="utf-8")

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["source_worktree_binding_pass"] is False


def test_ignored_untracked_implementation_source_is_rejected(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    source = tmp_path / "implementation" / "phase1" / "evil.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("release_authority = True\n", encoding="utf-8")
    (tmp_path / ".git" / "info" / "exclude").write_text(
        "implementation/phase1/evil.py\n", encoding="utf-8"
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["source_worktree_binding_pass"] is False


def test_only_canonical_repository_trust_root_is_eligible(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    alternate = tmp_path / "canonical" / "alternate-trust.json"
    alternate.write_bytes(fixture["trust_root_path"].read_bytes())
    canonical = json.loads(fixture["trust_root_path"].read_text(encoding="utf-8"))
    canonical["approved_signers"] = []
    write_json(fixture["trust_root_path"], canonical)
    subprocess.run(
        [
            "git",
            "add",
            "canonical/alternate-trust.json",
            "canonical/rights-holder-license-trust-root.v1.json",
        ],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "canonical root remains empty"],
        cwd=tmp_path,
        check=True,
    )
    fixture["source_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    fixture["decision"]["subject"]["source_commit_sha"] = fixture["source_commit_sha"]
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])

    payload = _inspect(fixture, trust_root_path=alternate)

    assert payload["contract_pass"] is False
    assert payload["canonical_trust_root_pass"] is False
    assert "rights_holder_trust_root_not_canonical" in payload["blockers"]


def test_license_policy_artifact_is_exactly_source_bound(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fixture["license_policy"].write_text("changed policy terms\n", encoding="utf-8")

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["license_policy_source_binding_pass"] is False
    assert "rights_holder_license_policy_hash_mismatch" in payload["blockers"]
    assert "rights_holder_license_policy_not_exact_source_blob" in payload["blockers"]


def test_decision_validity_window_cannot_exceed_90_days(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    long_expiry = "2099-01-01T00:00:00+00:00"
    fixture["decision"]["expires_at_utc"] = long_expiry
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])

    payload = _inspect(fixture, expected_expires_at_utc=long_expiry)

    assert payload["contract_pass"] is False
    assert payload["timeline_and_expiry_pass"] is False
    assert "rights_holder_decision_timeline_invalid_or_expired" in payload["blockers"]


def test_invalid_unicode_payload_is_blocked_without_verifier_exception(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fixture["decision"]["claim_boundary"] = "\ud800" * 80
    fixture["decision_path"].write_text(
        json.dumps(fixture["decision"], ensure_ascii=True),
        encoding="utf-8",
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is False
    assert "rights_holder_decision_canonical_payload_invalid" in payload["blockers"]


def test_expanded_git_lfs_object_matches_committed_pointer(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    expanded = b"bounded release evidence\n" * 64
    import hashlib

    pointer = (
        "version https://git-lfs.github.com/spec/v1\n"
        f"oid sha256:{hashlib.sha256(expanded).hexdigest()}\n"
        f"size {len(expanded)}\n"
    )
    lfs_path = tmp_path / "artifacts" / "evidence.bin"
    lfs_path.parent.mkdir(parents=True, exist_ok=True)
    lfs_path.write_text(pointer, encoding="ascii")
    subprocess.run(["git", "add", "artifacts/evidence.bin"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "test lfs pointer"],
        cwd=tmp_path,
        check=True,
    )
    fixture["source_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    lfs_path.write_bytes(expanded)
    fixture["decision"]["subject"]["source_commit_sha"] = fixture[
        "source_commit_sha"
    ]
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])

    payload = _inspect(fixture)

    assert payload["contract_pass"] is True
    assert payload["source_worktree_binding_pass"] is True


def test_symlinked_decision_cannot_escape_repository(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path / "repo")
    outside = tmp_path / "outside-decision.json"
    outside.write_bytes(fixture["decision_path"].read_bytes())
    symlink = fixture["repo_root"] / "symlinked-decision.json"
    symlink.symlink_to(outside)

    payload = _inspect(fixture, decision_path=symlink)

    assert payload["contract_pass"] is False
    assert "rights_holder_decision_symlink_not_allowed" in payload["blockers"]
    assert payload["signature_verified"] is False


def test_resigned_policy_change_still_requires_exact_status_binding(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    decision = fixture["decision"]
    decision["subject"]["product_scope"] = list(reversed(PRODUCT_SCOPE))
    sign_decision(decision, private_key=fixture["private_key"])
    write_json(fixture["decision_path"], decision)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert "rights_holder_decision_subject_binding_mismatch" in payload["blockers"]


def test_verifier_does_not_accept_caller_selected_crypto_or_clock(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)

    with pytest.raises(TypeError):
        _inspect(fixture, openssl="/bin/true")
    with pytest.raises(TypeError):
        _inspect(fixture, now="2020-01-01T00:00:00+00:00")


def test_source_binding_ignores_ambient_path_and_git_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_signed_decision_repository(tmp_path / "repo")
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))
    monkeypatch.setenv("GIT_DIR", str(tmp_path / "malicious-git-dir"))
    monkeypatch.setenv("GIT_REPLACE_REF_BASE", "refs/malicious/")

    payload = _inspect(fixture)

    assert payload["contract_pass"] is True
    assert payload["source_worktree_binding_pass"] is True


def test_git_replace_cannot_substitute_trust_root_blob(tmp_path: Path) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    source_commit = fixture["source_commit_sha"]
    fixture["trust_root_path"].write_text(
        fixture["trust_root_path"].read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "canonical/rights-holder-license-trust-root.v1.json"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "replacement trust root"],
        cwd=tmp_path,
        check=True,
    )
    replacement_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    subprocess.run(
        ["git", "update-ref", "HEAD", source_commit], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "replace", source_commit, replacement_commit],
        cwd=tmp_path,
        check=True,
    )
    replaced_blob = subprocess.check_output(
        [
            "git",
            "show",
            f"{source_commit}:canonical/rights-holder-license-trust-root.v1.json",
        ],
        cwd=tmp_path,
    )
    assert replaced_blob == fixture["trust_root_path"].read_bytes()

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is True
    assert payload["trust_root_source_binding_pass"] is False
    assert "rights_holder_trust_root_not_exact_source_blob" in payload["blockers"]


def test_duplicate_json_keys_are_rejected_before_signature_verification(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    original = fixture["decision_path"].read_text(encoding="utf-8")
    duplicate_grants = (
        '"grants": {"repository_use_approved": true, '
        '"commercial_use_approved": true, "redistribution_approved": true, '
        '"third_party_material_redistribution_approved": true, '
        '"release_authority_granted": true},\n  "grants": {'
    )
    fixture["decision_path"].write_text(
        original.replace('"grants": {', duplicate_grants, 1),
        encoding="utf-8",
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is False
    assert "rights_holder_decision_schema_invalid:$" in payload["blockers"]


def test_duplicate_trust_root_keys_cannot_select_an_ambient_signer(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    original = fixture["trust_root_path"].read_text(encoding="utf-8")
    fixture["trust_root_path"].write_text(
        original.replace(
            '"approved_signers": [',
            '"approved_signers": [],\n  "approved_signers": [',
            1,
        ),
        encoding="utf-8",
    )

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert "rights_holder_trust_root_schema_invalid:$" in payload["blockers"]
    assert payload["commercial_use_approved"] is False


@pytest.mark.parametrize(
    ("fixture_key", "expected_blocker"),
    [
        ("decision_path", "rights_holder_decision_unsafe_owner_or_permissions"),
        ("trust_root_path", "rights_holder_trust_root_unsafe_owner_or_permissions"),
    ],
)
def test_world_writable_authority_files_are_rejected(
    tmp_path: Path,
    fixture_key: str,
    expected_blocker: str,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fixture[fixture_key].chmod(0o666)

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert expected_blocker in payload["blockers"]
    assert payload["commercial_use_approved"] is False


def test_nonexistent_license_coverage_cannot_authorize_product_tree(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    fake_coverage = ["nonexistent/only/**"]
    fixture["decision"]["subject"]["license_policy"][
        "covered_first_party_paths"
    ] = fake_coverage
    fixture["trust_root"]["approved_signers"][0]["allowed_license_policy"][
        "covered_first_party_paths"
    ] = fake_coverage
    write_json(fixture["trust_root_path"], fixture["trust_root"])
    subprocess.run(
        ["git", "add", "canonical/rights-holder-license-trust-root.v1.json"],
        cwd=tmp_path,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "invalid narrow coverage"],
        cwd=tmp_path,
        check=True,
    )
    fixture["source_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    fixture["decision"]["subject"]["source_commit_sha"] = fixture[
        "source_commit_sha"
    ]
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert "rights_holder_license_policy_coverage_invalid" in payload["blockers"]
    assert payload["commercial_use_approved"] is False
    assert payload["redistribution_approved"] is False


def test_source_commit_with_uncovered_path_cannot_receive_repository_authority(
    tmp_path: Path,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    (tmp_path / "new-unclassified-root.txt").write_text(
        "first-party file outside the signed path inventory\n",
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "new-unclassified-root.txt"], cwd=tmp_path, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "unclassified source path"],
        cwd=tmp_path,
        check=True,
    )
    fixture["source_commit_sha"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True
    ).strip()
    fixture["decision"]["subject"]["source_commit_sha"] = fixture[
        "source_commit_sha"
    ]
    sign_decision(fixture["decision"], private_key=fixture["private_key"])
    write_json(fixture["decision_path"], fixture["decision"])

    payload = _inspect(fixture)

    assert payload["contract_pass"] is False
    assert payload["source_tree_coverage_pass"] is False
    assert "rights_holder_license_policy_source_tree_not_covered" in payload[
        "blockers"
    ]


def test_ambient_fake_cryptography_cannot_accept_invalid_signature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_signed_decision_repository(tmp_path / "repo")
    signature = base64.b64decode(
        fixture["decision"]["signature"]["value_base64"]
    )
    fixture["decision"]["signature"]["value_base64"] = base64.b64encode(
        bytes([signature[0] ^ 1]) + signature[1:]
    ).decode("ascii")
    write_json(fixture["decision_path"], fixture["decision"])
    fake_package = tmp_path / "ambient" / "cryptography"
    fake_package.mkdir(parents=True)
    (fake_package / "__init__.py").write_text(
        "# A malicious ambient package must never own signature truth.\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(fake_package.parent))
    spec = importlib.util.spec_from_file_location(
        "isolated_license_decision_verifier",
        Path(decision_verifier.__file__),
    )
    assert spec is not None and spec.loader is not None
    isolated_verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(isolated_verifier)

    payload = isolated_verifier.inspect_rights_holder_license_decision(
        decision_path=fixture["decision_path"],
        trust_root_path=fixture["trust_root_path"],
        repo_root=fixture["repo_root"],
        expected_source_commit_sha=fixture["source_commit_sha"],
        expected_decision_id=DECISION_ID,
        expected_license_id="LIC-001",
        expected_tier="limited-commercial",
        expected_approver_role="product_owner",
        expected_product_scope=list(PRODUCT_SCOPE),
        expected_rights_holder_id=RIGHTS_HOLDER_ID,
        expected_approved_at_utc=ISSUED_AT_UTC,
        expected_expires_at_utc=EXPIRES_AT_UTC,
    )

    assert payload["contract_pass"] is False
    assert payload["signature_verified"] is False
    assert "rights_holder_decision_signature_not_verified" in payload["blockers"]


def test_cross_tree_change_during_final_metadata_recheck_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_signed_decision_repository(tmp_path)
    original = decision_verifier._worktree_entry_metadata_signature
    changed = False

    def mutate_then_recheck(relative: Path, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            (tmp_path / ".gitignore").write_text(
                "license_status.json\nconcurrent-dirty-change\n",
                encoding="utf-8",
            )
        return original(relative, **kwargs)

    monkeypatch.setattr(
        decision_verifier,
        "_worktree_entry_metadata_signature",
        mutate_then_recheck,
    )

    payload = _inspect(fixture)

    assert changed is True
    assert payload["contract_pass"] is False
    assert payload["source_worktree_binding_pass"] is False
    assert "repository_worktree_not_exact_source_commit" in payload["blockers"]
