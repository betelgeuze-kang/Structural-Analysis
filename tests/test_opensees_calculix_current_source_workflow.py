from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import textwrap
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/opensees-calculix-current-source.yml"
ATTESTOR = ROOT / ".github/workflows/opensees-calculix-clean-runner-attestor.yml"


def _inline_attestor_verifier() -> str:
    source = ATTESTOR.read_text(encoding="utf-8")
    return textwrap.dedent(source.split("<<'PY'\n", 1)[1].split("\n          PY", 1)[0])


def _run_inline_attestor(
    tmp_path: Path, archive: bytes
) -> subprocess.CompletedProcess[str]:
    source_sha = "a" * 40
    digest = hashlib.sha256(archive).hexdigest()
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    run = {
        "id": 456,
        "run_attempt": 1,
        "head_sha": source_sha,
        "head_branch": "main",
        "event": "push",
        "path": ".github/workflows/opensees-calculix-current-source.yml",
        "repository": {"full_name": "owner/repository"},
        "head_repository": {"full_name": "owner/repository"},
    }
    jobs = {
        "jobs": [
            {"labels": ["ubuntu-22.04"], "run_attempt": 1},
            {"labels": ["ubuntu-24.04"], "run_attempt": 1},
        ]
    }
    artifact = {
        "id": 123,
        "name": "opensees-calculix-current-source-candidate-456-1",
        "digest": "sha256:" + digest,
        "expired": False,
        "size_in_bytes": len(archive),
        "archive_download_url": (
            "https://api.github.com/repos/owner/repository/actions/artifacts/123/zip"
        ),
        "workflow_run": {"id": 456, "head_sha": source_sha, "head_branch": "main"},
    }
    for name, payload in (("run.json", run), ("jobs.json", jobs), ("artifact.json", artifact)):
        (inputs / name).write_text(json.dumps(payload), encoding="utf-8")
    (inputs / "candidate.zip").write_bytes(archive)
    env = {
        "SOURCE_SHA": source_sha,
        "PRODUCER_ARTIFACT_ID": "123",
        "PRODUCER_ARTIFACT_DIGEST": digest,
        "CANDIDATE_ARTIFACT_NAME": artifact["name"],
        "FINAL_ARTIFACT_NAME": "opensees-calculix-current-source-456-1",
        "GITHUB_RUN_ID": "456",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_REPOSITORY": "owner/repository",
    }
    return subprocess.run(
        [sys.executable, "-I", "-", str(inputs), str(tmp_path / "output")],
        input=_inline_attestor_verifier(),
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def test_workflow_runs_exact_current_main_in_isolated_clean_runner() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'branches: ["main"]' in source
    assert "workflow_dispatch:" in source
    assert "pull_request:" not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert "runs-on: ubuntu-22.04" in source
    assert "ref: ${{ env.SOURCE_SHA }}" in source
    assert "scripts/run_external_vv_clean_runner.sh" in source
    assert '"$EXTERNAL_ASSET_DIR"' in source
    assert "--network none" not in source  # enforced inside the reviewed wrapper
    assert "same_operator_container_isolated_reproduction" in source
    assert "actual_external_solver_execution" in source
    assert "external_runtime_current_source_rerun_missing" in source


def test_workflow_pins_assets_and_never_uploads_solver_packages() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    for name, digest in {
        "openseespy-3.7.1.2-py3-none-any.whl": (
            "1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
        ),
        "openseespylinux-3.7.1.2-py3-none-any.whl": (
            "63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
        ),
        "calculix-ccx_2.17-3_amd64.deb": (
            "3e2001110e080e8cd01176ca171ee73993fa3a23e73e9febda3241b031a2b65e"
        ),
        "libarpack2_3.8.0-1_amd64.deb": (
            "07a4b576bd52ae9b0f487a3739b8922183ac88ceb1b2f2e943e3e68b8a12108a"
        ),
        "libspooles2.2_2.2-14_amd64.deb": (
            "34dd2bf283347402d49b7a9f3e07dc118385e62d8f63ce3fe245b612d2f3a917"
        ),
    }.items():
        assert name in source
        assert digest in source
    assert 'EXTERNAL_ASSET_DIR: "/tmp/' in source
    assert "path: ${{ env.RECEIPT_DIR }}" in source
    upload_section = source.split(
        "- name: Upload unprivileged receipts without external runtime assets", 1
    )[1]
    assert "EXTERNAL_ASSET_DIR" not in upload_section
    assert "-candidate-${{ github.run_id }}-${{ github.run_attempt }}" in source
    assert "retention-days: 7" in upload_section


def test_workflow_attests_without_promoting_level2() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    attestor_source = ATTESTOR.read_text(encoding="utf-8")
    workflow_header = source.split("jobs:", 1)[0]
    producer, attestor = source.split("\n  attest:\n", 1)

    assert "id-token: write" not in workflow_header
    assert "attestations: write" not in workflow_header
    assert "id-token: write" not in producer
    assert "attestations: write" not in producer
    assert "artifact-metadata: write" not in producer
    assert "id-token: write" in attestor
    assert "opensees-calculix-clean-runner-attestor.yml" in attestor
    assert "actions/checkout@v" not in source
    assert "actions/setup-python@v" not in source
    assert "actions/checkout@" not in attestor_source
    assert "actions/setup-python@" not in attestor_source
    assert "pip install" not in attestor_source
    assert "producer_artifact_metadata_invalid" in attestor_source
    assert "workflow_job_runner_invalid" in attestor_source
    assert "candidate_file_set_invalid" in attestor_source
    assert 'get("verification_level_2") is not False' in attestor_source
    assert "clean_runner_handoff.sigstore.json" in attestor_source
    assert "--deny-self-hosted-runners" in attestor_source
    assert 'certificate.get("runInvocationURI") == invocation' in attestor_source
    assert 'get("invocationId") == invocation' in attestor_source
    assert 'statement.get("subject") == expected_subject' in attestor_source
    for workflow_source in (source, attestor_source):
        assert "actions/checkout@v" not in workflow_source
        assert "actions/setup-python@v" not in workflow_source
        assert "actions/upload-artifact@v" not in workflow_source
        assert "actions/attest@v" not in workflow_source


@pytest.mark.parametrize(
    "malicious_name",
    ["control\nname.json", "control\u0007name.json", "control\u200dname.json", "e\u0301.json"],
)
def test_clean_runner_attestor_rejects_control_format_and_non_nfc_names(
    tmp_path: Path, malicious_name: str
) -> None:
    archive_path = tmp_path / "attack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(malicious_name, "{}")

    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())

    assert completed.returncode != 0
    assert "producer_artifact_archive_entry_invalid" in completed.stderr


def test_clean_runner_attestor_rejects_self_hosted_producer_job(tmp_path: Path) -> None:
    archive_path = tmp_path / "attack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("README.md", "candidate")
    inputs = tmp_path / "inputs"
    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())
    jobs_path = inputs / "jobs.json"
    jobs = json.loads(jobs_path.read_text(encoding="utf-8"))
    jobs["jobs"][0]["labels"] = ["self-hosted", "ubuntu-22.04"]
    jobs_path.write_text(json.dumps(jobs), encoding="utf-8")
    completed = subprocess.run(
        completed.args,
        input=_inline_attestor_verifier(),
        text=True,
        capture_output=True,
        env={
            "SOURCE_SHA": "a" * 40,
            "PRODUCER_ARTIFACT_ID": "123",
            "PRODUCER_ARTIFACT_DIGEST": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "CANDIDATE_ARTIFACT_NAME": "opensees-calculix-current-source-candidate-456-1",
            "FINAL_ARTIFACT_NAME": "opensees-calculix-current-source-456-1",
            "GITHUB_RUN_ID": "456",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_REPOSITORY": "owner/repository",
        },
        check=False,
    )

    assert completed.returncode != 0
    assert "workflow_job_runner_invalid" in completed.stderr


def test_clean_runner_attestor_does_not_trust_candidate_technical_pass(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "self-certified.zip"
    files = {
        "README.md": b"candidate\n",
        "clean_runner_receipt.json": b"{}\n",
        "external_code_to_code_receipt.json": json.dumps(
            {
                "schema_version": "external-code-to-code-technical-execution.v1",
                "source_commit_sha": "a" * 40,
                "technical_contract_pass": True,
                "claims": {"verification_level_2": False},
            }
        ).encode(),
        "external_modal_buckling_receipt.json": b"{}\n",
        "mode_vectors/calculix_buckling_modes.f64le": b"0" * 8,
        "mode_vectors/opensees_modal_modes.f64le": b"0" * 8,
        "mode_vectors/product_buckling_modes.f64le": b"0" * 8,
        "mode_vectors/product_modal_modes.f64le": b"0" * 8,
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        for name, raw in files.items():
            archive.writestr(name, raw)

    completed = _run_inline_attestor(tmp_path, archive_path.read_bytes())

    assert completed.returncode != 0
    assert "child_receipt_contract_invalid" in completed.stderr
