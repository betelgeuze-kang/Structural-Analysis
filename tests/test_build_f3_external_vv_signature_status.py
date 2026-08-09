from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_f3_external_vv_signature_status.py"
SPEC = importlib.util.spec_from_file_location(
    "build_f3_external_vv_signature_status", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)

AUTHORITY_RECEIPT_SHA256 = "sha256:" + "a" * 64


def _key_material() -> tuple[object, bytes]:
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return key, public_pem


def _signed_envelope(
    stage: str = "frame3d_linear",
    *,
    organization_id: str = "independent-vv-lab",
    signer_id: str = "vv-lab-key-1",
    authority_receipt_sha256: str | None = AUTHORITY_RECEIPT_SHA256,
) -> dict[str, object]:
    key, public_pem = _key_material()
    unsigned = module.create_unsigned_envelope(
        stage=stage,
        organization_id=organization_id,
        signer_id=signer_id,
        independent_from_repository_operator=True,
        independence_authority_receipt_sha256=authority_receipt_sha256,
        root=ROOT,
    )
    return module.attach_signature(
        unsigned,
        signature_bytes=key.sign(module.envelope_evidence_bytes(unsigned)),
        public_key_pem=public_pem,
    )


def test_committed_status_replays_all_ten_nine_surface_receipts() -> None:
    module.validate_status(
        json.loads((ROOT / module.DEFAULT_OUT).read_text(encoding="utf-8")),
        root=ROOT,
    )


def test_ephemeral_ed25519_envelope_is_crypto_valid_but_not_trusted() -> None:
    signed = _signed_envelope()

    validated = module.validate_envelope(signed, root=ROOT)
    trust = module.classify_envelope_trust(validated, root=ROOT)

    assert validated["signature"]["state"] == "verified"
    assert trust == {
        "cryptographic_signature_valid": True,
        "public_key_sha256": validated["signature"]["public_key_sha256"],
        "trusted_signer_allowlisted": False,
        "independence_authority_bound": False,
        "independently_trusted": False,
    }


def test_exact_builder_owned_anchor_can_classify_identity() -> None:
    signed = _signed_envelope()
    signature = signed["signature"]
    anchor = module.TrustedSignerAnchor(
        organization_id="independent-vv-lab",
        signer_id="vv-lab-key-1",
        public_key_sha256=signature["public_key_sha256"],
        independence_authority_receipt_sha256=AUTHORITY_RECEIPT_SHA256,
    )

    trust = module.classify_envelope_trust(
        signed,
        root=ROOT,
        trusted_signer_anchors=(anchor,),
    )

    assert trust["trusted_signer_allowlisted"] is True
    assert trust["independence_authority_bound"] is True
    assert trust["independently_trusted"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("organization_id", "different-lab"),
        ("signer_id", "different-key"),
        ("independence_authority_receipt_sha256", "sha256:" + "b" * 64),
    ],
)
def test_trust_requires_exact_identity_and_authority(field: str, value: str) -> None:
    signed = _signed_envelope()
    signature = signed["signature"]
    attestation = signed["evidence_payload"]["signer_attestation"]
    anchor_values = {
        "organization_id": attestation["organization_id"],
        "signer_id": attestation["signer_id"],
        "public_key_sha256": signature["public_key_sha256"],
        "independence_authority_receipt_sha256": attestation[
            "independence_authority_receipt_sha256"
        ],
    }
    anchor_values[field] = value
    anchor = module.TrustedSignerAnchor(**anchor_values)

    trust = module.classify_envelope_trust(
        signed,
        root=ROOT,
        trusted_signer_anchors=(anchor,),
    )

    assert trust["independently_trusted"] is False


@pytest.mark.parametrize(
    "receipt_path",
    [
        "/tmp/alternate-stage-receipt.json",
        "../alternate-stage-receipt.json",
        "implementation/phase1/release_evidence/productization/other.json",
    ],
)
def test_signature_envelope_requires_exact_canonical_stage_path(
    receipt_path: str,
) -> None:
    unsigned = module.create_unsigned_envelope(
        stage="frame3d_linear",
        organization_id="independent-vv-lab",
        signer_id="vv-lab-key-1",
        independent_from_repository_operator=True,
        root=ROOT,
    )
    tampered = deepcopy(unsigned)
    tampered["evidence_payload"]["stage_receipt_path"] = receipt_path
    tampered["signature"]["signed_payload_hash"] = module._sha_bytes(
        module.envelope_evidence_bytes(tampered)
    )
    tampered["receipt_hash"] = module._receipt_hash(tampered)

    with pytest.raises(ValueError, match="stage_evidence_replay_mismatch"):
        module.validate_envelope(tampered, root=ROOT)


def test_signature_and_stage_receipt_tampering_fail_closed() -> None:
    unsigned = module.create_unsigned_envelope(
        stage="frame3d_linear",
        organization_id="independent-vv-lab",
        signer_id="vv-lab-key-1",
        independent_from_repository_operator=True,
        root=ROOT,
    )
    tampered = deepcopy(unsigned)
    tampered["evidence_payload"]["external_vv_artifact_sha256"] = "sha256:" + "f" * 64
    tampered["signature"]["signed_payload_hash"] = module._sha_bytes(
        module.envelope_evidence_bytes(tampered)
    )
    tampered["receipt_hash"] = module._receipt_hash(tampered)

    with pytest.raises(ValueError, match="stage_evidence_replay_mismatch"):
        module.validate_envelope(tampered, root=ROOT)


def test_independence_attestation_is_required() -> None:
    unsigned = module.create_unsigned_envelope(
        stage="contact",
        organization_id="repository-operator",
        signer_id="self",
        independent_from_repository_operator=False,
        root=ROOT,
    )

    with pytest.raises(ValueError, match="independence_not_attested"):
        module.validate_envelope(unsigned, root=ROOT)


def test_source_binding_replays_git_ancestry_tree_blobs_and_inputs() -> None:
    evidence_rows = [
        module.stage_evidence_payload(stage, root=ROOT)
        for stage in module.F3_STAGE_ORDER
    ]
    linear, load_control, *later = evidence_rows

    assert linear["source_commit_is_ancestor_of_aggregate"] is True
    assert linear["canonical_stage_receipt_bound"] is True
    assert linear["source_input_binding"]["recorded_source_inputs_match"] is True
    assert linear["source_input_binding"]["aggregate_source_inputs_match"] is True
    assert linear["predecessor_binding"]["binding_pass"] is True
    assert linear["current_source_binding_pass"] is True
    assert linear["vertical_stage_contract_passed"] is True
    assert linear["recorded_public_product_promotion_passed"] is False

    assert (
        load_control["predecessor_binding"]["semantic_replay_hash_recomputed"] is True
    )
    assert load_control["predecessor_binding"]["semantic_replay_hash_matches"] is True
    assert load_control["predecessor_binding"]["binding_pass"] is True
    assert all(
        row["predecessor_binding"]["semantic_replay_hash_recomputed"] is True
        and row["predecessor_binding"]["semantic_replay_hash_matches"] is True
        and row["predecessor_binding"]["binding_pass"] is True
        and row["source_input_binding"]["recorded_source_inputs_match"] is True
        and row["source_input_binding"]["aggregate_source_inputs_match"] is True
        and row["current_source_binding_pass"] is True
        for row in later
    )


def test_predecessor_path_and_replay_hash_are_canonical() -> None:
    path = ROOT / module.STAGE_RECEIPTS["frame3d_load_control"]
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["predecessor_replay"]["source_receipt_path"] = "../linear.json"

    with pytest.raises(ValueError, match="predecessor_path_not_canonical"):
        module._predecessor_binding(
            stage="frame3d_load_control",
            receipt=receipt,
            root=ROOT,
            aggregate_source_commit_sha=module._git_commit(ROOT),
        )


def test_recomputable_predecessor_replay_hash_tamper_fails_closed() -> None:
    path = ROOT / module.STAGE_RECEIPTS["frame3d_load_control"]
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["stage_gate"]["predecessor_receipt_sha256"] = "sha256:" + "f" * 64

    with pytest.raises(ValueError, match="predecessor_replay_hash_mismatch"):
        module._predecessor_binding(
            stage="frame3d_load_control",
            receipt=receipt,
            root=ROOT,
            aggregate_source_commit_sha=module._git_commit(ROOT),
        )


def test_later_predecessor_gate_hash_tamper_fails_closed() -> None:
    path = ROOT / module.STAGE_RECEIPTS["frame3d_direct_control"]
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["stage_gate"]["predecessor_receipt_sha256"] = "sha256:" + "f" * 64

    with pytest.raises(ValueError, match="predecessor_replay_hash_mismatch"):
        module._predecessor_binding(
            stage="frame3d_direct_control",
            receipt=receipt,
            root=ROOT,
            aggregate_source_commit_sha=module._git_commit(ROOT),
        )


@pytest.mark.parametrize("case", ["final", "inside_parent", "outside_parent"])
def test_repository_target_rejects_every_symlink_component(
    tmp_path: Path,
    case: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    real_inside = repository / "real-inside"
    real_inside.mkdir()
    real_outside = tmp_path / "real-outside"
    real_outside.mkdir()

    if case == "final":
        real_file = real_inside / "receipt.json"
        real_file.write_text("{}", encoding="utf-8")
        candidate = Path("receipt.json")
        (repository / candidate).symlink_to(real_file)
    elif case == "inside_parent":
        candidate = Path("inside-link/receipt.json")
        (repository / "inside-link").symlink_to(
            real_inside,
            target_is_directory=True,
        )
    else:
        candidate = Path("outside-link/receipt.json")
        (repository / "outside-link").symlink_to(
            real_outside,
            target_is_directory=True,
        )

    with pytest.raises(ValueError, match="path_symlink_component"):
        module._repository_target(repository, candidate)


def test_git_execution_is_argv_based_and_never_uses_a_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout=b"ok\n", stderr=b"")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    completed = module._git(ROOT, "status", "--porcelain")

    assert completed.returncode == 0
    assert observed["command"][:3] == ["git", "-C", str(ROOT.resolve())]
    assert observed["command"][3:] == ["status", "--porcelain"]
    assert observed["shell"] is False


def test_all_arbitrary_signatures_remain_non_promotable(tmp_path: Path) -> None:
    for index, stage in enumerate(module.F3_STAGE_ORDER):
        signed = _signed_envelope(stage, signer_id=f"untrusted-key-{index}")
        (tmp_path / f"{stage}.json").write_text(
            json.dumps(signed, sort_keys=True, allow_nan=False),
            encoding="utf-8",
        )

    status = module.build_status(
        root=ROOT,
        generated_at="2026-08-09T00:00:00Z",
        _signature_dir_override=tmp_path,
    )

    assert status["status"] == "partial"
    assert status["public_product_promotion_passed"] is False
    assert status["vertical_stage_contract_pass_count"] == 10
    assert status["recorded_public_product_promotion_count"] == 0
    assert status["cryptographically_verified_stage_count"] == 10
    assert status["independently_signed_stage_count"] == 0
    assert status["claims"]["trusted_signer_policy_configured"] is False
    assert status["claims"]["all_independent_external_vv_signatures_verified"] is False
    assert status["claims"]["f3_signed_promotion_closure"] is False
    assert all(
        row["trusted_signer_allowlisted"] is False
        and row["independent_signature_verified"] is False
        for row in status["stage_rows"]
    )


def test_ephemeral_status_validates_and_v2_schema_rejects_promotion() -> None:
    status = module.build_status(
        root=ROOT,
        generated_at="2026-08-09T00:00:00Z",
    )
    schema = json.loads((ROOT / module.SCHEMA).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    validator.validate(status)
    module.validate_status(status, root=ROOT)
    assert status["status"] == "partial"
    assert status["schema_version"] == "f3-external-vv-signature-status.v2"
    assert status["public_product_promotion_passed"] is False
    assert status["trusted_signer_policy_anchor_count"] == 0
    assert status["independently_signed_stage_count"] == 0
    assert status["vertical_stage_contract_pass_count"] == 10
    assert status["recorded_public_product_promotion_count"] == 0
    assert status["current_source_bound_stage_count"] == 10
    assert status["aggregate_source"]["exact_source_binding"] is True
    assert status["claims"]["all_vertical_stage_contracts_passed"] is True
    assert status["claims"]["no_stage_self_promoted"] is True
    assert status["claims"]["planar_product_replay_prerequisite_bound"] is False
    assert status["claims"]["planar_external_vv_prerequisite_bound"] is False
    assert status["blockers_remaining"][:2] == [
        "planar_product_replay_prerequisite_not_bound",
        "planar_external_vv_prerequisite_not_bound",
    ]
    assert all(
        row["vertical_stage_contract_passed"] is True
        and row["recorded_public_product_promotion_passed"] is False
        and row["stage_technical_blockers"] == []
        and row["current_source_binding_pass"] is True
        for row in status["stage_rows"]
    )

    promoted = deepcopy(status)
    promoted["status"] = "ready"
    promoted["public_product_promotion_passed"] = True
    promoted["claims"]["all_independent_external_vv_signatures_verified"] = True
    promoted["claims"]["f3_signed_promotion_closure"] = True
    promoted["receipt_hash"] = module._receipt_hash(promoted)
    errors = list(validator.iter_errors(promoted))
    assert errors


def test_status_replay_uses_fixed_signature_directory() -> None:
    status = module.build_status(
        root=ROOT,
        generated_at="2026-08-09T00:00:00Z",
    )
    status["stage_rows"][0]["signature_envelope_path"] = (
        "/tmp/attacker-controlled-signature.json"
    )
    status["receipt_hash"] = module._receipt_hash(status)

    with pytest.raises(ValueError, match="status_replay_mismatch"):
        module.validate_status(status, root=ROOT)
