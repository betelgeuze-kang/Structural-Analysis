from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (
    fgmres_recurrence_receipt_hash,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_engine_v2_hip_fgmres_stage4_status.py"
SPEC = importlib.util.spec_from_file_location(
    "build_engine_v2_hip_fgmres_stage4_status",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _legacy_receipt() -> dict:
    return json.loads(
        (
            ROOT / "implementation/phase1/release_evidence/productization/"
            "engine_v2_cpu_hip_fgmres_recurrence_receipt.json"
        ).read_text(encoding="utf-8")
    )


def _operator_context(*, architecture: str) -> dict:
    external = architecture == "gfx1100"
    return {
        "organization_id": "external-lab" if external else "local-owner",
        "runner_id": f"runner-{architecture}",
        "execution_location": "external-site" if external else "local-site",
        "independent_from_local_gfx1030": external,
    }


def _unsigned_device_receipt(
    *,
    architecture: str,
    wheel_hash: str = "sha256:" + "a" * 64,
) -> dict:
    legacy = _legacy_receipt()
    hardware = legacy["hardware_execution"]
    runtime = deepcopy(hardware["runtime_output"])
    runtime["gcn_arch_name"] = architecture
    runtime["device_name"] = f"Synthetic {architecture}"
    receipt = module.device_runner.build_device_receipt_from_runtime_output(
        runtime,
        repo_root=ROOT,
        compiler=hardware["compiler"],
        binary_sha256=hardware["binary_sha256"],
        operator_context=_operator_context(architecture=architecture),
        wheel={
            "filename": ("structural_optimization_workbench-1.0.0-py3-none-any.whl"),
            "project_name": "structural-optimization-workbench",
            "project_version": "1.0.0",
            "sha256": wheel_hash,
            "bound_at_execution": True,
        },
        evidence_origin="direct_device_runner",
        upstream_receipt_hash=None,
    )
    source = receipt["evidence_payload"]["source"]
    source["worktree_clean"] = True
    source["exact_source_commit_claim"] = True
    receipt["signature"]["signed_payload_hash"] = module.device_runner._sha256_bytes(
        module.device_runner.device_evidence_bytes(receipt)
    )
    receipt["claims"] = module.device_runner._claims(
        exact_source_commit=True,
        wheel_bound_at_execution=True,
        signed_receipt=False,
    )
    receipt["blockers_remaining"] = module.device_runner._blockers(
        exact_source_commit=True,
        wheel_bound_at_execution=True,
        signed_receipt=False,
    )
    receipt["receipt_hash"] = fgmres_recurrence_receipt_hash(receipt)
    return receipt


def _signed_device_receipt(
    *,
    architecture: str,
    signer_id: str,
    private_key: Ed25519PrivateKey | None = None,
    wheel_hash: str = "sha256:" + "a" * 64,
) -> dict:
    receipt = _unsigned_device_receipt(
        architecture=architecture,
        wheel_hash=wheel_hash,
    )
    key = private_key or Ed25519PrivateKey.generate()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return module.device_runner.attach_ed25519_signature(
        receipt,
        signature_bytes=key.sign(module.device_runner.device_evidence_bytes(receipt)),
        public_key_pem=public_pem,
        signer_id=signer_id,
        repo_root=ROOT,
    )


def _write_receipt(path: Path, receipt: dict) -> None:
    path.write_text(module._json_text(receipt), encoding="utf-8")


def test_canonical_migrated_gfx1030_receipt_cannot_promote_stage4() -> None:
    status = module.build_stage4_status(repo_root=ROOT)
    local = status["device_receipts"]["gfx1030"]

    assert local["attached"] is True
    assert local["evidence_origin"] == "validated_upstream_runtime_receipt"
    assert local["exact_source_commit"] is False
    assert local["wheel_bound_at_execution"] is False
    assert local["signature_verified"] is False
    assert status["claims"]["stage4_cross_device_evidence"] is False
    assert status["claims"]["production_recurrence"] is False
    assert status["claims"]["performance"] is False
    for blocker in (
        "independent_gfx1100_device_receipt_not_attached",
        "direct_device_runner_pair_not_verified",
        "clean_exact_source_pair_not_verified",
        "wheel_bound_at_execution_pair_not_verified",
        "signed_receipt_pair_not_verified",
        "model_size_performance_sweep_not_executed",
    ):
        assert blocker in status["blockers_remaining"]


def test_stage4_status_keeps_missing_external_evidence_explicit(
    tmp_path: Path,
) -> None:
    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=tmp_path / "missing-gfx1030.json",
        gfx1100_device_path=tmp_path / "missing-gfx1100.json",
    )

    assert status["status"] == "partial"
    assert status["contract_pass"] is True
    assert status["claims"]["local_gfx1030_actual_hardware"] is True
    assert status["claims"]["independent_gfx1100_actual_hardware"] is False
    assert status["claims"]["stage4_cross_device_evidence"] is False
    assert status["claims"]["production_recurrence"] is False
    assert status["claims"]["performance"] is False
    assert (
        "signed_clean_gfx1030_device_receipt_not_attached"
        in (status["blockers_remaining"])
    )
    assert (
        "independent_gfx1100_device_receipt_not_attached"
        in (status["blockers_remaining"])
    )


def test_stage4_status_requires_complete_signed_independent_pair(
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "gfx1030.json"
    external_path = tmp_path / "gfx1100.json"
    _write_receipt(
        local_path,
        _signed_device_receipt(
            architecture="gfx1030",
            signer_id="local-signer",
        ),
    )
    _write_receipt(
        external_path,
        _signed_device_receipt(
            architecture="gfx1100",
            signer_id="external-signer",
        ),
    )

    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=local_path,
        gfx1100_device_path=external_path,
    )

    assert status["status"] == "ready"
    assert all(status["identity_gates"].values())
    assert status["claims"]["independent_gfx1100_actual_hardware"] is True
    assert status["claims"]["same_source_commit_cross_device"] is True
    assert status["claims"]["same_wheel_hash_cross_device"] is True
    assert status["claims"]["same_fixture_cross_device"] is True
    assert status["claims"]["signed_cross_device_receipts"] is True
    assert status["claims"]["stage4_cross_device_evidence"] is True
    assert "model_size_performance_sweep_not_executed" in (status["blockers_remaining"])


def test_stage4_status_rejects_same_signer_pair(tmp_path: Path) -> None:
    shared_key = Ed25519PrivateKey.generate()
    local_path = tmp_path / "gfx1030.json"
    external_path = tmp_path / "gfx1100.json"
    _write_receipt(
        local_path,
        _signed_device_receipt(
            architecture="gfx1030",
            signer_id="shared-signer",
            private_key=shared_key,
        ),
    )
    _write_receipt(
        external_path,
        _signed_device_receipt(
            architecture="gfx1100",
            signer_id="shared-signer",
            private_key=shared_key,
        ),
    )

    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=local_path,
        gfx1100_device_path=external_path,
    )

    assert status["status"] == "partial"
    assert status["identity_gates"]["distinct_signer_pair"] is False
    assert "distinct_signer_pair_not_verified" in status["blockers_remaining"]


def test_stage4_status_rejects_wheel_hash_drift(tmp_path: Path) -> None:
    local_path = tmp_path / "gfx1030.json"
    external_path = tmp_path / "gfx1100.json"
    _write_receipt(
        local_path,
        _signed_device_receipt(
            architecture="gfx1030",
            signer_id="local-signer",
            wheel_hash="sha256:" + "a" * 64,
        ),
    )
    _write_receipt(
        external_path,
        _signed_device_receipt(
            architecture="gfx1100",
            signer_id="external-signer",
            wheel_hash="sha256:" + "b" * 64,
        ),
    )

    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=local_path,
        gfx1100_device_path=external_path,
    )

    assert status["status"] == "partial"
    assert status["identity_gates"]["same_wheel_hash"] is False
    assert "same_wheel_hash_not_verified" in status["blockers_remaining"]


def test_stage4_status_validation_rejects_stale_hash(tmp_path: Path) -> None:
    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=tmp_path / "missing-gfx1030.json",
        gfx1100_device_path=tmp_path / "missing-gfx1100.json",
    )
    tampered = deepcopy(status)
    tampered["claims"]["performance"] = True

    with pytest.raises(Exception):
        module.validate_stage4_status(tampered, repo_root=ROOT)


def test_stage4_status_check_round_trip(tmp_path: Path) -> None:
    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=tmp_path / "missing-gfx1030.json",
        gfx1100_device_path=tmp_path / "missing-gfx1100.json",
    )

    assert module.validate_stage4_status(status, repo_root=ROOT) == status


def test_stage4_status_check_allows_non_claim_generation_context(
    tmp_path: Path,
) -> None:
    status = module.build_stage4_status(
        repo_root=ROOT,
        gfx1030_device_path=tmp_path / "missing-gfx1030.json",
        gfx1100_device_path=tmp_path / "missing-gfx1100.json",
    )
    status["source"]["repository_commit_sha"] = "f" * 40
    status["source"]["worktree_clean"] = not status["source"]["worktree_clean"]
    status["status_hash"] = module._status_hash(status)

    assert module.validate_stage4_status(status, repo_root=ROOT) == status
