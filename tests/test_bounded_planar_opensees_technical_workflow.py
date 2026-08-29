from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import textwrap
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/bounded-planar-opensees-technical.yml"
ATTESTOR = ROOT / ".github/workflows/bounded-planar-sealed-technical-attestor.yml"
DOC = ROOT / "docs/bounded-planar-opensees-technical-workflow.md"
TECHNICAL_WORKFLOWS = [
    ROOT / ".github/workflows/bounded-planar-opensees-technical.yml",
    ROOT / ".github/workflows/bounded-planar-negative-opensees-technical.yml",
    ROOT / ".github/workflows/bounded-planar-scaling-opensees-technical.yml",
    ROOT / ".github/workflows/bounded-planar-modal-buckling-technical.yml",
    ROOT / ".github/workflows/bounded-planar-nonlinear-material-recovery-technical.yml",
]


def _inline_attestor_verifier() -> str:
    source = ATTESTOR.read_text(encoding="utf-8")
    return textwrap.dedent(source.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0])


def _run_inline_attestor(
    tmp_path: Path, archive: bytes, *, claimed_digest: str | None = None
) -> subprocess.CompletedProcess[str]:
    source_sha = "a" * 40
    artifact_digest = claimed_digest or hashlib.sha256(archive).hexdigest()
    main = tmp_path / "main.json"
    tree = tmp_path / "tree.json"
    metadata = tmp_path / "metadata.json"
    archive_path = tmp_path / "candidate.zip"
    main.write_text(json.dumps({"object": {"sha": source_sha}}), encoding="utf-8")
    tree.write_text(
        json.dumps({"sha": "b" * 40, "truncated": False, "tree": []}),
        encoding="utf-8",
    )
    metadata.write_text(
        json.dumps(
            {
                "id": 123,
                "name": "bounded-planar-opensees-technical-candidate-456-1",
                "digest": "sha256:" + artifact_digest,
                "expired": False,
                "size_in_bytes": len(archive),
                "workflow_run": {
                    "id": 456,
                    "head_sha": source_sha,
                    "head_branch": "main",
                },
            }
        ),
        encoding="utf-8",
    )
    archive_path.write_bytes(archive)
    env = {
        "SOURCE_SHA": source_sha,
        "FAMILY_ID": "linear",
        "CALLER_WORKFLOW_PATH": (
            ".github/workflows/bounded-planar-opensees-technical.yml"
        ),
        "RECEIPT_PATH": ".ci/bounded-planar-opensees/technical-receipt.json",
        "SEAL_PATH": ".ci/bounded-planar-opensees/producer-seal.json",
        "HANDOFF_PATH": ".ci/bounded-planar-opensees/artifact-handoff.json",
        "ATTESTATION_BUNDLE_PATH": (
            ".ci/bounded-planar-opensees/artifact-handoff.sigstore.json"
        ),
        "ATTESTATION_VERIFICATION_PATH": (
            ".ci/bounded-planar-opensees/attestation-verification.json"
        ),
        "CANDIDATE_ARTIFACT_NAME": (
            "bounded-planar-opensees-technical-candidate-456-1"
        ),
        "FINAL_ARTIFACT_NAME": "bounded-planar-opensees-technical-456-1",
        "PRODUCER_ARTIFACT_ID": "123",
        "PRODUCER_ARTIFACT_DIGEST": artifact_digest,
        "GITHUB_RUN_ID": "456",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "owner/repository",
    }
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-",
            str(tmp_path / "extracted"),
            str(main),
            str(tree),
            str(metadata),
            str(archive_path),
        ],
        input=_inline_attestor_verifier(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_workflow_executes_exact_main_package_and_fails_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert 'python-version: "3.12.11"' in source
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in source
    assert "--require-hashes --no-deps" in source
    assert (
        "PACKAGE_DIR: artifacts/vv/bounded_planar_external_linear_case_package"
        in source
    )
    assert '"$PACKAGE_DIR/requirements.txt"' in source
    assert "build_bounded_planar_external_linear_case_package.py" in source
    assert "--check" in source
    assert "bounded_planar_linear_portal.py" in source
    assert "bounded_planar_linear_multistory.py" in source
    assert "ingest_bounded_planar_external_linear_results.py" in source
    assert "--fail-technical-blocked" in source
    assert "continue-on-error" not in source


def test_workflow_attests_receipt_without_promoting_level2() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    attestor = ATTESTOR.read_text(encoding="utf-8")
    documentation = DOC.read_text(encoding="utf-8")

    assert "contents: read" in source
    producer = source.split("  attest:", 1)[0]
    assert "id-token: write" not in producer
    assert "attestations: write" not in producer
    assert "artifact-metadata: write" not in producer
    assert "bounded-planar-sealed-technical-attestor.yml" in source
    assert "actions/attest@" not in source
    assert "actions/checkout@" not in attestor
    assert "actions/setup-python@" not in attestor
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in attestor
    assert "subject-path: candidate/${{ inputs.handoff-path }}" in attestor
    assert "steps.attest_handoff.outputs.bundle-path" in attestor
    assert "gh attestation verify" in attestor
    assert '--bundle "candidate/$ATTESTATION_BUNDLE_PATH"' in attestor
    assert "--signer-workflow" in attestor
    assert '--source-digest "$SOURCE_SHA"' in attestor
    assert "--source-ref refs/heads/main" in attestor
    assert "--deny-self-hosted-runners" in attestor
    assert '--format json > "candidate/$ATTESTATION_VERIFICATION_PATH"' in attestor
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in source
    assert "if-no-files-found: error" in source
    assert "gh attestation verify" in documentation
    assert "--signer-workflow" in documentation
    assert "independent-operator reproduction" in documentation
    assert "Verification Level 2" in documentation


@pytest.mark.parametrize("workflow", TECHNICAL_WORKFLOWS, ids=lambda path: path.stem)
def test_every_technical_producer_is_unprivileged_and_uses_immutable_handoff(
    workflow: Path,
) -> None:
    source = workflow.read_text(encoding="utf-8")
    producer, attestor_call = source.split("\n  attest:\n", 1)

    assert "id-token: write" not in producer
    assert "attestations: write" not in producer
    assert "artifact-metadata: write" not in producer
    assert "actions/attest@" not in source
    assert "bounded-planar-sealed-technical-attestor.yml" in attestor_call
    assert "producer-artifact-id:" in attestor_call
    assert "producer-artifact-digest:" in attestor_call
    assert "canonical/requirements-cp312-manylinux2014-x86_64.lock" in producer
    assert "--require-hashes --no-deps" in producer
    assert "pip install --no-deps --no-build-isolation -e ." not in producer
    assert "LD_LIBRARY_PATH" in producer
    assert "openseespylinux.__file__" in producer
    assert "sudo apt-get update" in producer
    assert any(
        command in producer
        for command in (
            "sudo apt-get install --yes --no-install-recommends libblas3 liblapack3",
            "sudo apt-get install --yes --no-install-recommends "
            "calculix-ccx=2.17-3 libblas3 liblapack3",
        )
    )
    assert producer.index("libblas3 liblapack3") < producer.index(
        "import openseespylinux"
    )
    assert "--untracked-files=all" in producer
    assert "WHEEL_DIR: /tmp/structural-analysis-" in producer
    upload_section = producer.split(
        "- name: Upload immutable unprivileged candidate", 1
    )[1]
    assert "WHEEL_DIR" not in upload_section
    for action, revision in re.findall(r"uses: (actions/[^@\s]+)@([^\s]+)", producer):
        assert re.fullmatch(r"[0-9a-f]{40}", revision), action


def test_fresh_attestor_has_no_checkout_repo_code_or_dependency_install() -> None:
    source = ATTESTOR.read_text(encoding="utf-8")

    assert "actions/checkout@" not in source
    assert "actions/setup-python@" not in source
    assert "actions/download-artifact@" not in source
    assert "pip install" not in source
    assert "python3 -I -" in source
    assert "actions/artifacts/$PRODUCER_ARTIFACT_ID/zip" in source
    assert "PRODUCER_ARTIFACT_DIGEST" in source
    assert "actions/artifacts/$PRODUCER_ARTIFACT_ID" in source
    assert 'artifact_metadata.get("digest") != "sha256:" + artifact_digest' in source
    assert "producer_artifact_archive_digest_invalid" in source
    assert "zipfile.ZipFile" in source
    assert "full_tracked_product_package_plus_family_control_plane" in source
    assert 'tree.get("truncated") is not False' in source
    assert "artifact_path_contract_invalid" in source
    assert "calculix_apt_transitive_bytes_not_pre_execution_hash_locked" in source
    for action, revision in re.findall(r"uses: (actions/[^@\s]+)@([^\s]+)", source):
        assert re.fullmatch(r"[0-9a-f]{40}", revision), action


def test_fresh_attestor_rejects_archive_digest_mismatch(tmp_path: Path) -> None:
    completed = _run_inline_attestor(
        tmp_path,
        b"tampered artifact archive",
        claimed_digest="0" * 64,
    )

    assert completed.returncode != 0
    assert "producer_artifact_archive_digest_invalid" in completed.stderr


def test_fresh_attestor_rejects_zip_path_escape(tmp_path: Path) -> None:
    archive_path = tmp_path / "attack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.json", "{}")

    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())

    assert completed.returncode != 0
    assert "producer_artifact_archive_entry_invalid" in completed.stderr
    assert not (tmp_path / "escape.json").exists()


def test_fresh_attestor_rejects_zip_symlink(tmp_path: Path) -> None:
    archive_path = tmp_path / "attack.zip"
    symlink = zipfile.ZipInfo(".ci/linked.json")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(symlink, "../../escape.json")

    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())

    assert completed.returncode != 0
    assert "producer_artifact_archive_entry_invalid" in completed.stderr


@pytest.mark.parametrize(
    "malicious_name",
    [
        ".ci/control\nname.json",
        ".ci/control\u0007name.json",
        ".ci/control\u200dname.json",
        ".ci/decomposed-e\u0301.json",
    ],
)
def test_fresh_attestor_rejects_control_format_and_non_nfc_zip_names(
    tmp_path: Path, malicious_name: str
) -> None:
    archive_path = tmp_path / "attack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(malicious_name, "{}")

    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())

    assert completed.returncode != 0
    assert "producer_artifact_archive_entry_invalid" in completed.stderr
