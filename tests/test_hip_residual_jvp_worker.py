from __future__ import annotations

from copy import deepcopy
import hashlib
import os
from pathlib import Path

import pytest

from scripts import build_g1_hip_residual_jvp_worker_contract as builder
import structural_analysis.engine_v2_backends.hip_residual_jvp_worker as worker


ROOT = Path(__file__).resolve().parents[1]
RUN_KWARGS = {
    "github_run_id": "12345",
    "github_run_attempt": 2,
    "artifact_prefix": "g1-mgt-gfx1100-12345-2",
    "expected_runner_id": "runner-gfx1100",
    "receipt_runner_id": ("runner-gfx1100::github_run_id=12345::run_attempt=2"),
}


def _receipt() -> dict:
    return worker.build_preexecution_receipt(
        source_commit_sha="a" * 40,
        source_files={
            "implementation/phase1/hip_kernels/engine_v2_fgmres_recurrence.hip.cpp": (
                "sha256:" + "b" * 64
            ),
            "scripts/run_engine_v2_hip_fgmres_device_receipt.py": (
                "sha256:" + "c" * 64
            ),
        },
        wheel_filename="structural_analysis-0.4.0-py3-none-any.whl",
        wheel_sha256="sha256:" + "d" * 64,
        wheel_size_bytes=1234,
        expected_signer_public_key_sha256="sha256:" + "e" * 64,
        **RUN_KWARGS,
    )


def test_preexecution_contract_binds_inputs_without_hardware_authority() -> None:
    receipt = _receipt()

    worker.validate_preexecution_receipt(receipt)
    assert receipt["target"] == {
        "device_architecture": "gfx1100",
        "required_runner_labels": list(worker.REQUIRED_RUNNER_LABELS),
    }
    assert receipt["retained_wheel"] == {
        "filename": "structural_analysis-0.4.0-py3-none-any.whl",
        "sha256": "sha256:" + "d" * 64,
        "size_bytes": 1234,
    }
    assert receipt["claims"] == {
        "hardware_execution_proven": False,
        "signed_provenance": False,
        "release": False,
        "performance": False,
        "production_ready": False,
    }
    assert list(worker.BLOCKERS) == receipt["blockers_remaining"]


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("source_commit_sha", "a" * 39, "source_commit_sha_invalid"),
        (
            "expected_device_architecture",
            "gfx1030",
            "expected_device_architecture_invalid",
        ),
        ("wheel_filename", "dist/candidate.whl", "wheel_filename_invalid"),
        ("wheel_sha256", "sha256:bad", "wheel_sha256_invalid"),
        ("wheel_size_bytes", True, "wheel_size_bytes_invalid"),
        (
            "wheel_size_bytes",
            worker.MAX_RETAINED_WHEEL_BYTES + 1,
            "wheel_size_bytes_invalid",
        ),
        (
            "required_runner_labels",
            ("self-hosted", "linux", "x64"),
            "required_runner_labels_invalid",
        ),
    ],
)
def test_preexecution_contract_rejects_identity_drift(
    field: str,
    value: object,
    error: str,
) -> None:
    kwargs = {
        "source_commit_sha": "a" * 40,
        "source_files": {"source.py": "sha256:" + "b" * 64},
        "wheel_filename": "candidate.whl",
        "wheel_sha256": "sha256:" + "c" * 64,
        "wheel_size_bytes": 1,
        "expected_signer_public_key_sha256": "sha256:" + "d" * 64,
        **RUN_KWARGS,
    }
    kwargs[field] = value
    with pytest.raises(worker.HIPResidualJVPWorkerContractError, match=error):
        worker.build_preexecution_receipt(**kwargs)


def test_preexecution_contract_rejects_claim_and_byte_tampering() -> None:
    receipt = _receipt()
    promoted = deepcopy(receipt)
    promoted["claims"]["hardware_execution_proven"] = True
    with pytest.raises(
        worker.HIPResidualJVPWorkerContractError, match="claims_invalid"
    ):
        worker.validate_preexecution_receipt(promoted)

    changed = deepcopy(receipt)
    changed["retained_wheel"]["size_bytes"] += 1
    with pytest.raises(
        worker.HIPResidualJVPWorkerContractError, match="receipt_hash_mismatch"
    ):
        worker.validate_preexecution_receipt(changed)


def test_preexecution_contract_rejects_parent_source_path_on_replay() -> None:
    receipt = _receipt()
    receipt["source"]["input_checksums"] = {
        "../outside.py": "sha256:" + "b" * 64,
    }

    with pytest.raises(
        worker.HIPResidualJVPWorkerContractError,
        match="source_file_path_invalid",
    ):
        worker.validate_preexecution_receipt(receipt)


def test_public_worker_surface_has_no_execution_or_promotion_api() -> None:
    assert "execute_hip_residual_jvp_worker_probe" not in worker.__all__
    assert "attach_signature" not in worker.__all__
    assert "promote" not in worker.__all__
    assert not hasattr(worker, "execute_hip_residual_jvp_worker_probe")


def test_builder_binds_current_head_and_exact_wheel_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder, "_worktree_clean", lambda _root: True)
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"retained-current-source-wheel")
    source_sha = builder.git_head(ROOT)

    receipt = builder.build(
        root=ROOT,
        source_sha=source_sha,
        wheel=wheel,
        expected_signer_public_key_sha256="sha256:" + "f" * 64,
        **RUN_KWARGS,
    )

    assert receipt["source"]["repository_commit_sha"] == source_sha
    assert receipt["retained_wheel"]["filename"] == wheel.name
    assert receipt["retained_wheel"]["size_bytes"] == len(wheel.read_bytes())
    assert receipt["retained_wheel"]["sha256"] == (
        "sha256:" + hashlib.sha256(wheel.read_bytes()).hexdigest()
    )
    worker.validate_preexecution_receipt(receipt)


def test_builder_fails_closed_on_source_identity_and_cleanliness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"wheel")
    kwargs = {
        "root": ROOT,
        "wheel": wheel,
        "expected_signer_public_key_sha256": "sha256:" + "f" * 64,
        **RUN_KWARGS,
    }

    with pytest.raises(ValueError, match="source_sha_not_head"):
        builder.build(source_sha="0" * 40, **kwargs)

    monkeypatch.setattr(builder, "_worktree_clean", lambda _root: False)
    with pytest.raises(ValueError, match="source_not_clean"):
        builder.build(source_sha=builder.git_head(ROOT), **kwargs)


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_builder_rejects_non_regular_wheel_without_opening_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
) -> None:
    monkeypatch.setattr(builder, "_worktree_clean", lambda _root: True)
    target = tmp_path / "target.whl"
    target.write_bytes(b"wheel")
    wheel = tmp_path / "candidate.whl"
    if kind == "symlink":
        wheel.symlink_to(target)
    else:
        os.mkfifo(wheel)

    with pytest.raises(ValueError, match="wheel_regular_file_required"):
        builder.build(
            root=ROOT,
            source_sha=builder.git_head(ROOT),
            wheel=wheel,
            expected_signer_public_key_sha256="sha256:" + "f" * 64,
            **RUN_KWARGS,
        )


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("github_run_id", "other", "github_run_id_invalid"),
        ("github_run_attempt", 0, "github_run_attempt_invalid"),
        ("artifact_prefix", "g1-mgt-gfx1100-999-1", "artifact_prefix_invalid"),
        (
            "receipt_runner_id",
            "runner-gfx1100::github_run_id=999::run_attempt=1",
            "receipt_runner_id_invalid",
        ),
    ],
)
def test_preexecution_contract_rejects_cross_run_identity(
    field: str,
    value: object,
    error: str,
) -> None:
    kwargs = {
        "source_commit_sha": "a" * 40,
        "source_files": {"source.py": "sha256:" + "b" * 64},
        "wheel_filename": "candidate.whl",
        "wheel_sha256": "sha256:" + "c" * 64,
        "wheel_size_bytes": 1,
        "expected_signer_public_key_sha256": "sha256:" + "d" * 64,
        **RUN_KWARGS,
    }
    kwargs[field] = value
    with pytest.raises(worker.HIPResidualJVPWorkerContractError, match=error):
        worker.build_preexecution_receipt(**kwargs)


def test_source_path_closure_covers_imports_contracts_and_packaging() -> None:
    paths = set(builder.SOURCE_PATHS)
    assert set(builder.recurrence_runner._source_paths()) <= paths
    assert set(builder.device_runner._device_source_paths()) <= paths
    assert set(builder.LANE_SOURCE_PATHS) <= paths
    assert set(builder.PACKAGING_INPUTS) <= paths
    assert set(builder.CONTRACT_SOURCE_PATHS) <= paths
    assert set(builder.CONTRACT_SCHEMA_PATHS) <= paths
    assert set(builder.IMPORT_CLOSURE_PATHS) <= paths
    assert Path("scripts/release_evidence_metadata.py") in paths
    for required in (
        "src/structural_analysis/__init__.py",
        "src/structural_analysis/engine_v2/contracts/_canonical.py",
        "src/structural_analysis/engine_v2/contracts/equation_scaling.py",
        "src/structural_analysis/engine_v2/contracts/execution_plan.py",
        "src/structural_analysis/engine_v2/contracts/execution_plan_reduced_csr.py",
        "src/structural_analysis/schemas/equation_scaling_v1.schema.json",
        "src/structural_analysis/schemas/execution_plan_v1.schema.json",
        "src/structural_analysis/schemas/execution_plan_reduced_csr_v1.schema.json",
    ):
        assert Path(required) in paths
    assert (
        tuple(sorted(paths, key=lambda path: path.as_posix())) == builder.SOURCE_PATHS
    )
    seeds = tuple(
        path for path in builder.DECLARED_SOURCE_PATHS if path.suffix == ".py"
    )
    assert (
        builder.repo_local_import_closure(ROOT, seeds) == builder.IMPORT_CLOSURE_PATHS
    )


def test_builder_rejects_missing_source_union_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(builder, "_worktree_clean", lambda _root: True)
    original = builder.input_checksums

    def missing(paths: object, *, repo_root: Path) -> dict[str, str]:
        checksums = original(paths, repo_root=repo_root)
        checksums[builder.SOURCE_PATHS[0].as_posix()] = "missing"
        return checksums

    monkeypatch.setattr(builder, "input_checksums", missing)
    wheel = tmp_path / "candidate.whl"
    wheel.write_bytes(b"wheel")
    with pytest.raises(ValueError, match="source_inputs_missing"):
        builder.build(
            root=ROOT,
            source_sha=builder.git_head(ROOT),
            wheel=wheel,
            expected_signer_public_key_sha256="sha256:" + "f" * 64,
            **RUN_KWARGS,
        )


@pytest.mark.parametrize("parent_symlink", [False, True])
def test_worker_output_rejects_symlink_without_overwriting_victim(
    tmp_path: Path,
    parent_symlink: bool,
) -> None:
    victim = tmp_path / "victim.json"
    victim.write_bytes(b"do-not-overwrite")
    if parent_symlink:
        real_parent = tmp_path / "real-parent"
        real_parent.mkdir()
        victim = real_parent / "worker.json"
        victim.write_bytes(b"do-not-overwrite")
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        out = linked_parent / "worker.json"
        error = "worker_output_parent_invalid"
    else:
        out = tmp_path / "worker.json"
        out.symlink_to(victim)
        error = "worker_output_leaf_invalid"

    with pytest.raises(ValueError, match=error):
        builder._write_atomic(out, _receipt())
    assert victim.read_bytes() == b"do-not-overwrite"
