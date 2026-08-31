from __future__ import annotations

import base64
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from structural_analysis.engine_v2_backends.hip_fgmres_recurrence import (
    HIP_FGMRES_OUTPUT_VERSION,
    build_cpu_hip_fgmres_recurrence_reference,
    fgmres_recurrence_receipt_hash,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_engine_v2_hip_fgmres_device_receipt.py"
SPEC = importlib.util.spec_from_file_location(
    "run_engine_v2_hip_fgmres_device_receipt",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _checkpoint_resume_output(reference) -> dict:
    checkpoint = reference.checkpoint
    run = reference.cpu_runs[1]
    return {
        "case_id": "restart_max_iterations",
        "runtime_status_code": 0,
        "artifact_loaded": True,
        "device_resident_suffix_recurrence": True,
        "completed_iteration_replay_count": 0,
        "resumed_from_iteration": checkpoint.iteration_count,
        "restart_index_base": checkpoint.next_restart_index,
        "terminal_reason": run.terminal_reason,
        "converged": run.converged,
        "iteration_count": run.iteration_count,
        "matvec_count": run.matvec_count,
        "suffix_restart_count": (
            len(run.restart_history) - checkpoint.next_restart_index
        ),
        "convergence_threshold_scaled_l2": (run.convergence_threshold_scaled_l2),
        "solution": [float(value) for value in run.solution_free],
        "scaled_l2_suffix_history": [
            row.scaled_l2 for row in run.observations[checkpoint.iteration_count :]
        ],
        "scaled_linf_suffix_history": [
            row.scaled_linf for row in run.observations[checkpoint.iteration_count :]
        ],
        "restart_suffix_history": [
            {
                "start_iteration": row.start_iteration,
                "end_iteration": row.end_iteration,
                "iteration_count": row.iteration_count,
                "disposition": row.disposition,
            }
            for row in run.restart_history[checkpoint.next_restart_index :]
        ],
    }


def _runtime_output(*, architecture: str = "gfx1030") -> dict:
    reference = build_cpu_hip_fgmres_recurrence_reference()
    cases = []
    for config, run in zip(
        reference.fixture.cases,
        reference.cpu_runs,
        strict=True,
    ):
        cases.append(
            {
                "case_id": config.case_id,
                "runtime_status_code": 0,
                "terminal_reason": run.terminal_reason,
                "converged": run.converged,
                "iteration_count": run.iteration_count,
                "matvec_count": run.matvec_count,
                "restart_count": len(run.restart_history),
                "convergence_threshold_scaled_l2": (
                    run.convergence_threshold_scaled_l2
                ),
                "solution": [float(value) for value in run.solution_free],
                "scaled_l2_history": [row.scaled_l2 for row in run.observations],
                "scaled_linf_history": [row.scaled_linf for row in run.observations],
                "restart_history": [
                    {
                        "start_iteration": row.start_iteration,
                        "end_iteration": row.end_iteration,
                        "iteration_count": row.iteration_count,
                        "disposition": row.disposition,
                    }
                    for row in run.restart_history
                ],
            }
        )
    return {
        "schema_version": HIP_FGMRES_OUTPUT_VERSION,
        "runtime_status": "success",
        "runtime_status_code": 0,
        "backend": "amd_rocm_hip",
        "cpu_backend": False,
        "same_stream_ordering": True,
        "mid_recurrence_host_transfer_count": 0,
        "blocking_d2h_synchronization_count": 1,
        "checkpoint_h2d_transfer_count": 1,
        "checkpoint_completed_iteration_replay_count": 0,
        "threads_per_case": 64,
        "kernel_invocation_count": 3710,
        "multi_block_kernel_invocation_count": 3710,
        "operator_blocks_per_case": 4,
        "recurrence_execution_profile": (
            "same_stream_fixed_kernel_sequence_device_guarded.v1"
        ),
        "device_resident_full_recurrence_probe": True,
        "production_recurrence_claim": False,
        "preconditioner_profile": ("operator_derived_left_scaled_jacobi_right.v1"),
        "reduction_profile": "fixed_block_binary_tree_fp64_probe.v1",
        "krylov_workspace_profile": "device_global_dynamic_dimension_fp64.v1",
        "workspace_dimension": reference.fixture.dimension,
        "workspace_doubles_per_case": 71 * reference.fixture.dimension,
        "cooperative_launch_supported": False,
        "device_status_to_terminal_state": True,
        "device_index": 0,
        "device_name": f"Synthetic {architecture}",
        "gcn_arch_name": architecture,
        "cases": cases,
        "checkpoint_hash": reference.checkpoint.checkpoint_hash,
        "checkpoint_artifact_data_hash": (
            reference.checkpoint.artifact_descriptor.data_hash
        ),
        "checkpoint_recurrence_contract_hash": (
            reference.checkpoint.recurrence_contract_hash
        ),
        "checkpoint_resume": _checkpoint_resume_output(reference),
    }


def _wheel(*, bound: bool = True) -> dict:
    return {
        "filename": "structural_optimization_workbench-1.0.0-py3-none-any.whl",
        "project_name": "structural-optimization-workbench",
        "project_version": "1.0.0",
        "sha256": "sha256:" + "a" * 64,
        "bound_at_execution": bound,
    }


def _compiler() -> dict:
    return {
        "path": "/opt/rocm/bin/hipcc",
        "version_first_line": "HIP version: 6.0.32831",
        "version_output_sha256": "sha256:" + "b" * 64,
    }


def _operator_context(*, architecture: str) -> dict:
    external = architecture == "gfx1100"
    return {
        "organization_id": "independent-lab-a" if external else "local-dev",
        "runner_id": f"runner-{architecture}",
        "execution_location": "external-lab" if external else "local",
        "independent_from_local_gfx1030": external,
    }


def _receipt(*, architecture: str = "gfx1030") -> dict:
    return module.build_device_receipt_from_runtime_output(
        _runtime_output(architecture=architecture),
        repo_root=ROOT,
        compiler=_compiler(),
        binary_sha256="sha256:" + "c" * 64,
        operator_context=_operator_context(architecture=architecture),
        wheel=_wheel(),
        evidence_origin="direct_device_runner",
        upstream_receipt_hash=None,
    )


def test_device_receipt_is_architecture_neutral_and_fail_closed() -> None:
    receipt = _receipt(architecture="gfx1100")

    assert receipt["contract_pass"] is True
    assert receipt["status"] == "partial"
    assert (
        receipt["evidence_payload"]["hardware_execution"]["gcn_arch_name"] == "gfx1100"
    )
    assert receipt["claims"]["actual_hardware_execution"] is True
    assert receipt["claims"]["numerical_parity"] is True
    assert receipt["claims"]["checkpoint_resume_parity"] is True
    assert receipt["claims"]["signed_receipt"] is False
    assert receipt["claims"]["cross_device_stage4"] is False
    assert receipt["claims"]["production_recurrence"] is False
    assert receipt["claims"]["performance"] is False
    assert "device_receipt_signature_not_attached" in (receipt["blockers_remaining"])
    assert (
        "production_preconditioner_apply_not_verified"
        not in (receipt["blockers_remaining"])
    )
    assert (
        "production_scale_preconditioner_effectiveness_not_verified"
        in (receipt["blockers_remaining"])
    )


def test_non_exact_device_receipt_is_bound_by_current_source_checksums(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module.local_runner, "_worktree_clean", lambda _: False)
    receipt = _receipt()
    source = receipt["evidence_payload"]["source"]
    assert source["exact_source_commit_claim"] is False
    source["repository_commit_sha"] = "0" * 40
    receipt["signature"]["signed_payload_hash"] = module._sha256_bytes(
        module.device_evidence_bytes(receipt)
    )
    receipt["receipt_hash"] = fgmres_recurrence_receipt_hash(receipt)

    assert (
        module.validate_device_receipt(
            receipt,
            repo_root=ROOT,
            require_current_sources=True,
        )
        == receipt
    )


def test_device_receipt_wraps_validated_runtime_without_relabeling_wheel() -> None:
    upstream = json.loads(
        (
            ROOT / "implementation/phase1/release_evidence/productization/"
            "engine_v2_cpu_hip_fgmres_recurrence_receipt.json"
        ).read_text(encoding="utf-8")
    )

    receipt = module.build_device_receipt_from_upstream(
        upstream,
        repo_root=ROOT,
        wheel=_wheel(),
        operator_context=_operator_context(architecture="gfx1030"),
    )

    execution = receipt["evidence_payload"]["hardware_execution"]
    assert execution["evidence_origin"] == "validated_upstream_runtime_receipt"
    assert execution["upstream_receipt_hash"] == upstream["receipt_hash"]
    assert receipt["evidence_payload"]["wheel"]["bound_at_execution"] is False
    assert receipt["claims"]["wheel_identity_bound_at_execution"] is False
    assert "wheel_identity_not_bound_at_execution" in receipt["blockers_remaining"]


def test_ed25519_signature_is_verified_over_evidence_payload() -> None:
    receipt = _receipt()
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signature = private_key.sign(module.device_evidence_bytes(receipt))

    signed = module.attach_ed25519_signature(
        receipt,
        signature_bytes=signature,
        public_key_pem=public_pem,
        signer_id="independent-lab-a",
        repo_root=ROOT,
    )

    assert signed["signature"]["state"] == "verified"
    assert signed["signature"]["algorithm"] == "ed25519"
    assert signed["signature"]["signer_id"] == "independent-lab-a"
    assert signed["claims"]["signed_receipt"] is True
    assert "device_receipt_signature_not_attached" not in (signed["blockers_remaining"])
    module.validate_device_receipt(
        signed,
        repo_root=ROOT,
        require_current_sources=True,
    )


def test_signature_validation_rejects_payload_tampering() -> None:
    receipt = _receipt()
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signed = module.attach_ed25519_signature(
        receipt,
        signature_bytes=private_key.sign(module.device_evidence_bytes(receipt)),
        public_key_pem=public_pem,
        signer_id="independent-lab-a",
        repo_root=ROOT,
    )
    tampered = deepcopy(signed)
    tampered["evidence_payload"]["wheel"]["filename"] = "tampered-1.0.whl"
    tampered["signature"]["signed_payload_hash"] = module._sha256_bytes(
        module.device_evidence_bytes(tampered)
    )
    tampered["receipt_hash"] = fgmres_recurrence_receipt_hash(tampered)

    with pytest.raises(ValueError, match="signature_invalid"):
        module.validate_device_receipt(
            tampered,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_device_receipt_validation_rejects_stale_hash() -> None:
    receipt = _receipt()
    receipt["evidence_payload"]["hardware_execution"]["binary_sha256"] = (
        "sha256:" + "d" * 64
    )

    with pytest.raises(ValueError, match="receipt_hash_mismatch"):
        module.validate_device_receipt(
            receipt,
            repo_root=ROOT,
            require_current_sources=False,
        )


def test_device_receipt_validation_rejects_stale_sources() -> None:
    receipt = _receipt()
    source = receipt["evidence_payload"]["source"]
    key = module.local_runner.MODULE_PATH.as_posix()
    source["input_checksums"][key] = "sha256:" + "0" * 64
    source["source_set_hash"] = module._source_set_hash(source["input_checksums"])
    receipt["signature"]["signed_payload_hash"] = module._sha256_bytes(
        module.device_evidence_bytes(receipt)
    )
    receipt["receipt_hash"] = fgmres_recurrence_receipt_hash(receipt)

    with pytest.raises(ValueError, match="sources_stale"):
        module.validate_device_receipt(
            receipt,
            repo_root=ROOT,
            require_current_sources=True,
        )


def test_wheel_identity_reads_metadata_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "example_project-2.3.4-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "example_project-2.3.4.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: example-project\nVersion: 2.3.4\n",
        )

    identity = module.wheel_identity(path)

    assert identity["filename"] == path.name
    assert identity["project_name"] == "example-project"
    assert identity["project_version"] == "2.3.4"
    assert identity["sha256"].startswith("sha256:")
    assert identity["bound_at_execution"] is False


def _generation_args(
    out: Path, wheel: Path, signing_out: Path | None = None
) -> list[str]:
    args = [
        "--out",
        str(out),
        "--wheel",
        str(wheel),
        "--organization-id",
        "independent-lab-a",
        "--runner-id",
        "runner-gfx1100",
        "--execution-location",
        "external-lab",
    ]
    if signing_out is not None:
        args.extend(["--signing-payload-out", str(signing_out)])
    return args


def test_device_receipt_output_rejects_leaf_symlink_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "run_hardware_device_receipt",
        lambda **_kwargs: _receipt(architecture="gfx1100"),
    )
    victim = tmp_path / "victim.json"
    victim.write_text("preserve", encoding="utf-8")
    out = tmp_path / "receipt.json"
    out.symlink_to(victim)

    with pytest.raises(ValueError, match="device_receipt_output_leaf_invalid"):
        module.main(_generation_args(out, tmp_path / "candidate.whl"))

    assert victim.read_text(encoding="utf-8") == "preserve"


def test_device_receipt_output_rejects_parent_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "run_hardware_device_receipt",
        lambda **_kwargs: _receipt(architecture="gfx1100"),
    )
    victim_dir = tmp_path / "victim-dir"
    victim_dir.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(victim_dir, target_is_directory=True)

    with pytest.raises(ValueError, match="device_receipt_output_parent_invalid"):
        module.main(
            _generation_args(
                linked_parent / "receipt.json",
                tmp_path / "candidate.whl",
            )
        )

    assert not (victim_dir / "receipt.json").exists()


def test_signing_payload_output_rejects_leaf_symlink_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "run_hardware_device_receipt",
        lambda **_kwargs: _receipt(architecture="gfx1100"),
    )
    victim = tmp_path / "victim.bin"
    victim.write_bytes(b"preserve")
    signing_out = tmp_path / "signing.json"
    signing_out.symlink_to(victim)

    with pytest.raises(ValueError, match="device_signing_payload_output_leaf_invalid"):
        module.main(
            _generation_args(
                tmp_path / "receipt.json",
                tmp_path / "candidate.whl",
                signing_out,
            )
        )

    assert victim.read_bytes() == b"preserve"


def test_device_receipt_cli_check(tmp_path: Path, capsys) -> None:
    path = tmp_path / "device-receipt.json"
    path.write_text(module._json_text(_receipt()), encoding="utf-8")

    assert module.main(["--out", str(path), "--check"]) == 0
    assert "device_receipt_consistent" in capsys.readouterr().out


def test_signature_encoding_is_canonical_base64() -> None:
    receipt = _receipt()
    private_key = Ed25519PrivateKey.generate()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    signed = module.attach_ed25519_signature(
        receipt,
        signature_bytes=private_key.sign(module.device_evidence_bytes(receipt)),
        public_key_pem=public_pem,
        signer_id="lab",
        repo_root=ROOT,
    )

    assert base64.b64decode(signed["signature"]["signature_base64"], validate=True)
