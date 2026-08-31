from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import zipfile

import pytest

from scripts import build_g1_mgt_cross_device_gate as gate
from structural_analysis.engine_v2_backends.hip_residual_jvp_worker import (
    build_preexecution_receipt,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "12345"
RUN_ATTEMPT = 2
PREFIX = f"g1-mgt-gfx1100-{RUN_ID}-{RUN_ATTEMPT}"
EXPECTED_RUNNER = "external-gfx1100"
RECEIPT_RUNNER = f"{EXPECTED_RUNNER}::github_run_id={RUN_ID}::run_attempt={RUN_ATTEMPT}"
GATE_KWARGS = {
    "github_run_id": RUN_ID,
    "github_run_attempt": RUN_ATTEMPT,
    "artifact_prefix": PREFIX,
    "expected_runner_id": EXPECTED_RUNNER,
}


def _hash(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _device_receipt(
    *,
    architecture: str,
    source_sha: str,
    wheel_sha: str,
    signer: str,
    public_key_digit: str,
    organization: str,
    runner: str,
    independent: bool,
) -> dict:
    return {
        "receipt_hash": "sha256:" + architecture[-1] * 64,
        "evidence_payload": {
            "source": {
                "repository_commit_sha": source_sha,
                "source_set_hash": "sha256:" + "1" * 64,
            },
            "operator_context": {
                "organization_id": organization,
                "runner_id": runner,
                "execution_location": organization + "-site",
                "independent_from_local_gfx1030": independent,
            },
            "wheel": {"sha256": wheel_sha, "filename": "candidate.whl"},
            "fixture_identity": {"fixture": "bounded-66"},
            "hardware_execution": {
                "gcn_arch_name": architecture,
                "evidence_origin": "direct_device_runner",
            },
        },
        "signature": {
            "state": "verified",
            "signer_id": signer,
            "public_key_sha256": "sha256:" + public_key_digit * 64,
        },
        "claims": {
            "actual_hardware_execution": True,
            "numerical_parity": True,
            "checkpoint_resume_parity": True,
            "exact_source_commit": True,
            "wheel_identity_bound_at_execution": True,
            "signed_receipt": True,
        },
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def _complete_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    expected_signer_digit: str = "d",
    complete_source_set: bool = True,
    external_runner: str | None = None,
    worker_run_id: str = RUN_ID,
    invocation_run_id: str = RUN_ID,
) -> tuple[dict, Path, dict[str, Path]]:
    monkeypatch.setattr(
        gate.stage4_builder.device_runner,
        "validate_device_receipt",
        lambda payload, **_: payload,
    )
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    source_sha = gate.git_head(ROOT)
    paths = {
        "wheel": Path("candidate.whl"),
        "worker": Path(f"{PREFIX}.worker-contract.json"),
        "local": Path("gfx1030.device-receipt.json"),
        "external": Path(f"{PREFIX}.device-receipt.json"),
        "gate": Path(f"{PREFIX}.cross-device-gate.json"),
    }
    with zipfile.ZipFile(artifact_root / paths["wheel"], "w") as wheel:
        wheel.writestr("structural_analysis/__init__.py", b"__version__ = 'test'\n")
    wheel_sha = _hash((artifact_root / paths["wheel"]).read_bytes())
    source_files = {
        path.as_posix(): _hash((ROOT / path).read_bytes())
        for path in gate.worker_builder.SOURCE_PATHS
    }
    if not complete_source_set:
        first = next(iter(source_files))
        source_files = {first: source_files[first]}
    worker_prefix = f"g1-mgt-gfx1100-{worker_run_id}-{RUN_ATTEMPT}"
    worker_receipt_runner = (
        f"{EXPECTED_RUNNER}::github_run_id={worker_run_id}::run_attempt={RUN_ATTEMPT}"
    )
    worker = build_preexecution_receipt(
        source_commit_sha=source_sha,
        source_files=source_files,
        wheel_filename=paths["wheel"].name,
        wheel_sha256=wheel_sha,
        wheel_size_bytes=(artifact_root / paths["wheel"]).stat().st_size,
        expected_signer_public_key_sha256=("sha256:" + expected_signer_digit * 64),
        github_run_id=worker_run_id,
        github_run_attempt=RUN_ATTEMPT,
        artifact_prefix=worker_prefix,
        expected_runner_id=EXPECTED_RUNNER,
        receipt_runner_id=worker_receipt_runner,
    )
    _write_json(artifact_root / paths["worker"], worker)
    _write_json(
        artifact_root / paths["local"],
        _device_receipt(
            architecture="gfx1030",
            source_sha=source_sha,
            wheel_sha=wheel_sha,
            signer="local-signer",
            public_key_digit="c",
            organization="local-org",
            runner="local-gfx1030",
            independent=False,
        ),
    )
    _write_json(
        artifact_root / paths["external"],
        _device_receipt(
            architecture="gfx1100",
            source_sha=source_sha,
            wheel_sha=wheel_sha,
            signer="external-signer",
            public_key_digit="d",
            organization="external-org",
            runner=external_runner or worker_receipt_runner,
            independent=True,
        ),
    )
    retained = [paths[key] for key in ("wheel", "worker", "local", "external")]
    payload = gate.build_gate(
        root=ROOT,
        artifact_root=artifact_root,
        gfx1030_path=paths["local"],
        gfx1100_path=paths["external"],
        worker_contract_path=paths["worker"],
        retained_wheel_path=paths["wheel"],
        retained_paths=retained,
        github_run_id=invocation_run_id,
        github_run_attempt=RUN_ATTEMPT,
        artifact_prefix=f"g1-mgt-gfx1100-{invocation_run_id}-{RUN_ATTEMPT}",
        expected_runner_id=EXPECTED_RUNNER,
    )
    gate._write_atomic(artifact_root / paths["gate"], payload)
    return payload, artifact_root, paths


def test_missing_hardware_evidence_is_explicit_and_non_promoting(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    payload = gate.build_gate(
        root=ROOT,
        artifact_root=artifact_root,
        gfx1030_path=Path("missing-gfx1030.json"),
        gfx1100_path=Path("missing-gfx1100.json"),
        **GATE_KWARGS,
    )

    assert payload["status"] == "blocked"
    assert payload["stage4_diagnostic"]["diagnostic_only"] is True
    assert all(
        value is False for value in payload["stage4_diagnostic"]["authority"].values()
    )
    assert payload["claims"]["hardware_execution_proven"] is False
    assert payload["claims"]["signed_provenance"] is False
    blockers = set(payload["blockers_remaining"])
    assert "current_source_gfx1100_receipt_missing" in blockers
    assert "independently_attested_cpu_fallback_zero_missing" in blockers
    assert "gfx1030_gfx1100_terminal_resultir_diagnosticir_parity_missing" in blockers


def test_complete_pair_is_path_independent_and_non_promoting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, artifact_root, _paths = _complete_pair(tmp_path, monkeypatch)

    assert payload["claims"]["cross_device_pair_consistent"] is True
    assert payload["claims"]["exact_run_and_runner_identity_bound"] is True
    assert payload["claims"]["retained_gfx1100_wheel_bound"] is True
    for claim in (
        "hardware_execution_proven",
        "signed_provenance",
        "performance",
        "release",
        "production_ready",
    ):
        assert payload["claims"][claim] is False
    serialized = json.dumps(payload, sort_keys=True)
    assert artifact_root.as_posix() not in serialized
    assert '"status": "ready"' not in serialized
    for forbidden in gate.FORBIDDEN_AUTHORITY_KEYS:
        assert forbidden not in serialized


def test_gate_replays_after_artifact_root_relocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, artifact_root, _paths = _complete_pair(tmp_path, monkeypatch)
    relocated = tmp_path / "downloaded" / "artifact-root"
    relocated.parent.mkdir()
    shutil.copytree(artifact_root, relocated)

    gate.validate_gate(
        payload,
        root=ROOT,
        artifact_root=relocated,
        **GATE_KWARGS,
    )


def test_gate_validate_rejects_invocation_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, artifact_root, _paths = _complete_pair(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="gate_invocation_identity_mismatch"):
        gate.validate_gate(
            payload,
            root=ROOT,
            artifact_root=artifact_root,
            github_run_id="99999",
            github_run_attempt=1,
            artifact_prefix="g1-mgt-gfx1100-99999-1",
            expected_runner_id=EXPECTED_RUNNER,
        )


def test_deterministic_archive_exact_allowlist_and_relocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, artifact_root, paths = _complete_pair(tmp_path, monkeypatch)
    archive_one = tmp_path / "one.tar"
    archive_two = tmp_path / "two.tar"
    (artifact_root / "not-allowlisted.txt").write_text("must stay outside archive")
    gate.build_archive(
        artifact_root=artifact_root,
        gate_path=paths["gate"],
        payload=payload,
        out=archive_one,
    )
    gate.build_archive(
        artifact_root=artifact_root,
        gate_path=paths["gate"],
        payload=payload,
        out=archive_two,
    )
    assert archive_one.read_bytes() == archive_two.read_bytes()
    with tarfile.open(archive_one, "r:") as archive:
        names = archive.getnames()
    expected_names = sorted(
        [paths["gate"].as_posix(), *(row["path"] for row in payload["retained_files"])]
    )
    assert names == expected_names
    assert "not-allowlisted.txt" not in names
    gate.validate_archive(
        artifact_root=artifact_root,
        gate_path=paths["gate"],
        payload=payload,
        archive_path=archive_one,
    )

    relocated = tmp_path / "relocated"
    shutil.copytree(artifact_root, relocated)
    downloaded = tmp_path / "downloaded.tar"
    shutil.copy2(archive_one, downloaded)
    gate.validate_archive(
        artifact_root=relocated,
        gate_path=paths["gate"],
        payload=payload,
        archive_path=downloaded,
    )


@pytest.mark.parametrize(
    "appended",
    [b"trailing-bytes", b"-----BEGIN PRIVATE KEY-----\nsecret\n"],
)
def test_archive_rejects_any_appended_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    appended: bytes,
) -> None:
    payload, artifact_root, paths = _complete_pair(tmp_path, monkeypatch)
    archive = tmp_path / "evidence.tar"
    gate.build_archive(
        artifact_root=artifact_root,
        gate_path=paths["gate"],
        payload=payload,
        out=archive,
    )
    archive.write_bytes(archive.read_bytes() + appended)

    with pytest.raises(ValueError, match="archive_noncanonical_bytes"):
        gate.validate_archive(
            artifact_root=artifact_root,
            gate_path=paths["gate"],
            payload=payload,
            archive_path=archive,
        )


@pytest.mark.parametrize("parent_symlink", [False, True])
def test_archive_output_rejects_symlink_without_overwriting_victim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parent_symlink: bool,
) -> None:
    payload, artifact_root, paths = _complete_pair(tmp_path, monkeypatch)
    victim = tmp_path / "victim"
    victim.write_bytes(b"do-not-overwrite")
    if parent_symlink:
        real_parent = tmp_path / "real-parent"
        real_parent.mkdir()
        victim = real_parent / "evidence.tar"
        victim.write_bytes(b"do-not-overwrite")
        linked_parent = tmp_path / "linked-parent"
        linked_parent.symlink_to(real_parent, target_is_directory=True)
        out = linked_parent / "evidence.tar"
        error = "archive_output_parent_invalid"
    else:
        out = tmp_path / "evidence.tar"
        out.symlink_to(victim)
        error = "archive_output_leaf_invalid"

    with pytest.raises(ValueError, match=error):
        gate.build_archive(
            artifact_root=artifact_root,
            gate_path=paths["gate"],
            payload=payload,
            out=out,
        )
    assert victim.read_bytes() == b"do-not-overwrite"


def test_gate_rejects_cross_run_device_transplant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="cross_run_identity_mismatch"):
        _complete_pair(
            tmp_path,
            monkeypatch,
            external_runner=(f"{EXPECTED_RUNNER}::github_run_id=99999::run_attempt=1"),
        )


def test_gate_rejects_coordinated_old_run_worker_and_device_transplant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="worker_invocation_identity_mismatch"):
        _complete_pair(
            tmp_path,
            monkeypatch,
            worker_run_id="99999",
            invocation_run_id=RUN_ID,
        )


def test_gate_rejects_verified_signer_policy_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="signer_policy_mismatch"):
        _complete_pair(tmp_path, monkeypatch, expected_signer_digit="b")


def test_gate_keeps_incomplete_worker_source_set_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload, _artifact_root, _paths = _complete_pair(
        tmp_path,
        monkeypatch,
        complete_source_set=False,
    )
    assert payload["claims"]["retained_gfx1100_wheel_bound"] is False
    assert "preexecution_worker_source_set_not_current" in payload["blockers_remaining"]


def test_gate_schema_locks_product_claims_false(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    payload = gate.build_gate(
        root=ROOT,
        artifact_root=artifact_root,
        gfx1030_path=Path("missing-gfx1030.json"),
        gfx1100_path=Path("missing-gfx1100.json"),
        **GATE_KWARGS,
    )
    promoted = deepcopy(payload)
    promoted["claims"]["production_ready"] = True
    promoted["receipt_hash"] = gate._receipt_hash(promoted)

    with pytest.raises(Exception, match="False was expected"):
        gate._validate_schema_and_hash(promoted, root=ROOT)


@pytest.mark.parametrize("blocker", gate.AUTHORITY_BLOCKERS)
def test_gate_schema_requires_every_authority_blocker(
    tmp_path: Path,
    blocker: str,
) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    payload = gate.build_gate(
        root=ROOT,
        artifact_root=artifact_root,
        gfx1030_path=Path("missing-gfx1030.json"),
        gfx1100_path=Path("missing-gfx1100.json"),
        **GATE_KWARGS,
    )
    payload["blockers_remaining"].remove(blocker)
    payload["receipt_hash"] = gate._receipt_hash(payload)

    with pytest.raises(Exception):
        gate._validate_schema_and_hash(payload, root=ROOT)


@pytest.mark.parametrize("kind", ["symlink", "fifo"])
def test_artifact_contract_rejects_non_regular_files(
    tmp_path: Path,
    kind: str,
) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    target = artifact_root / "target"
    target.write_bytes(b"retained")
    candidate = artifact_root / kind
    if kind == "symlink":
        candidate.symlink_to(target)
    else:
        os.mkfifo(candidate)

    with pytest.raises(ValueError, match="retained_regular_file_required"):
        gate.build_gate(
            root=ROOT,
            artifact_root=artifact_root,
            gfx1030_path=Path("missing-gfx1030.json"),
            gfx1100_path=Path("missing-gfx1100.json"),
            retained_paths=(Path(kind),),
            **GATE_KWARGS,
        )


def test_artifact_contract_rejects_absolute_and_parent_paths(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    for invalid in (tmp_path / "absolute.json", Path("../escape.json")):
        with pytest.raises(ValueError, match="artifact_relative_path_required"):
            gate.build_gate(
                root=ROOT,
                artifact_root=artifact_root,
                gfx1030_path=invalid,
                gfx1100_path=Path("missing-gfx1100.json"),
                **GATE_KWARGS,
            )


def test_archive_rejects_allowlisted_private_key_material(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact-root"
    artifact_root.mkdir()
    private = Path("operator-private.key")
    (artifact_root / private).write_text("-----BEGIN PRIVATE KEY-----\nsecret\n")
    payload = gate.build_gate(
        root=ROOT,
        artifact_root=artifact_root,
        gfx1030_path=Path("missing-gfx1030.json"),
        gfx1100_path=Path("missing-gfx1100.json"),
        retained_paths=(private,),
        **GATE_KWARGS,
    )
    gate_path = Path("gate.json")
    gate._write_atomic(artifact_root / gate_path, payload)

    with pytest.raises(ValueError, match="archive_private_key_forbidden"):
        gate.build_archive(
            artifact_root=artifact_root,
            gate_path=gate_path,
            payload=payload,
            out=tmp_path / "evidence.tar",
        )
