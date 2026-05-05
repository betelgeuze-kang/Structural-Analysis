from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_release_publication_candidate.py"
assert SCRIPT_PATH.exists(), "scripts/build_release_publication_candidate.py must exist"
SPEC = importlib.util.spec_from_file_location("build_release_publication_candidate", SCRIPT_PATH)
assert SPEC is not None
build_release_publication_candidate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_release_publication_candidate)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(tmp_path: Path, artifacts: list[dict], *, generated_at: str = "2026-04-26T00:00:00+09:00") -> Path:
    manifest = tmp_path / "release_artifacts_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "structural_analysis_release_artifacts_manifest.v1",
                "generated_at": generated_at,
                "release_tag": "test-release",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _artifact(asset_name: str, local_path: str, payload: bytes, *, required: bool = True) -> dict:
    return {
        "asset_name": asset_name,
        "local_path": local_path,
        "sha256": _sha256(b"stale-" + payload),
        "bytes": len(payload) + 99,
        "required": required,
    }


def test_publication_candidate_copies_generated_and_local_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    work_dir = tmp_path / "work"
    artifact_root = tmp_path / "upload-root"
    generated_payload = b"fresh package"
    local_payload = b"viewer html"
    generated = work_dir / "project_package.zip"
    generated.parent.mkdir(parents=True)
    generated.write_bytes(generated_payload)
    local = tmp_path / "implementation" / "phase1" / "release" / "visualization" / "viewer.html"
    local.parent.mkdir(parents=True)
    local.write_bytes(local_payload)
    manifest = _write_manifest(
        tmp_path,
        [
            _artifact("project_package.zip", "implementation/phase1/release/project_package.zip", generated_payload),
            _artifact("viewer.html", "implementation/phase1/release/visualization/viewer.html", local_payload),
        ],
    )
    manifest_out = tmp_path / "candidate-manifest.json"

    result = build_release_publication_candidate.build_release_publication_candidate(
        manifest_path=manifest,
        artifact_root=artifact_root,
        work_dir=work_dir,
        manifest_out=manifest_out,
        write=True,
        skip_registry_generation=True,
    )

    assert result["ok"] is True
    assert result["generated_at"] == "2026-04-26T00:00:00+09:00"
    assert (artifact_root / "project_package.zip").read_bytes() == generated_payload
    assert (artifact_root / "viewer.html").read_bytes() == local_payload
    candidate = json.loads(manifest_out.read_text(encoding="utf-8"))
    rows = {row["asset_name"]: row for row in candidate["artifacts"]}
    assert rows["project_package.zip"]["sha256"] == _sha256(generated_payload)
    assert rows["project_package.zip"]["bytes"] == len(generated_payload)
    assert rows["viewer.html"]["sha256"] == _sha256(local_payload)
    assert candidate["publication_candidate"]["registry_generated"] is False


def test_publication_candidate_rejects_private_key_content(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    work_dir = tmp_path / "work"
    artifact_root = tmp_path / "upload-root"
    source = work_dir / "signing" / "project_registry_ed25519.pub.pem"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n")
    manifest = _write_manifest(
        tmp_path,
        [
            _artifact(
                "project_registry_ed25519.pub.pem",
                "implementation/phase1/release/signing/project_registry_ed25519.pub.pem",
                b"not used",
            )
        ],
    )

    result = build_release_publication_candidate.build_release_publication_candidate(
        manifest_path=manifest,
        artifact_root=artifact_root,
        work_dir=work_dir,
        write=True,
        skip_registry_generation=True,
    )

    assert result["ok"] is False
    assert result["totals"]["copied"] == 0
    assert any("unsafe private key-like asset source" in error for error in result["errors"])
    assert not artifact_root.exists()


def test_publication_candidate_dry_run_does_not_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _write_manifest(
        tmp_path,
        [_artifact("project_package.zip", "implementation/phase1/release/project_package.zip", b"pkg")],
    )

    result = build_release_publication_candidate.build_release_publication_candidate(
        manifest_path=manifest,
        artifact_root=tmp_path / "upload-root",
        write=False,
    )

    assert result["ok"] is True
    assert result["write"] is False
    assert result["totals"]["selected_assets"] == 1
    assert result["actions"][0]["status"] == "planned"
    assert not (tmp_path / "upload-root").exists()


def test_publication_candidate_rejects_manifest_out_inside_artifact_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _write_manifest(
        tmp_path,
        [_artifact("project_package.zip", "implementation/phase1/release/project_package.zip", b"pkg")],
    )
    artifact_root = tmp_path / "upload-root"

    result = build_release_publication_candidate.build_release_publication_candidate(
        manifest_path=manifest,
        artifact_root=artifact_root,
        manifest_out=artifact_root / "candidate-manifest.json",
        write=True,
        skip_registry_generation=True,
    )

    assert result["ok"] is False
    assert result["errors"] == [f"manifest_out must not be inside artifact_root: {artifact_root / 'candidate-manifest.json'}"]


def test_publication_candidate_cli_json_reports_missing_source(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    manifest = _write_manifest(
        tmp_path,
        [_artifact("missing.html", "implementation/phase1/release/visualization/missing.html", b"missing")],
    )

    exit_code = build_release_publication_candidate.main(
        [
            "--manifest",
            str(manifest),
            "--artifact-root",
            str(tmp_path / "upload-root"),
            "--skip-registry-generation",
            "--write",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["ok"] is False
    assert payload["errors"] == [
        "source artifact missing for missing.html: implementation/phase1/release/visualization/missing.html"
    ]


def test_registry_generation_runs_twice_to_stabilize_key_metadata(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(build_release_publication_candidate.subprocess, "run", fake_run)

    command = build_release_publication_candidate._run_registry_generation(
        work_dir=tmp_path / "work",
        generated_at="2026-04-26T00:00:00+09:00",
        python_executable="python",
    )

    assert len(calls) == 2
    assert calls[0] == calls[1] == command
    assert command[-2:] == ["--generated-at", "2026-04-26T00:00:00+09:00"]


def test_registry_generation_forwards_release_facing_manifest_assets(tmp_path: Path, monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(build_release_publication_candidate.subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)
    sidecar_root = tmp_path / "implementation" / "phase1" / "release_evidence" / "productization"
    sidecar_root.mkdir(parents=True)
    (sidecar_root / "external_benchmark_submission_updates.json").write_text(
        json.dumps({"updates": {"hardest_external_10case": {"receipt_status": "pending"}}}),
        encoding="utf-8",
    )
    (sidecar_root / "residual_holdout_closure_updates.json").write_text(
        json.dumps({"updates": {"RH-001": {"closure_evidence_status": "pending"}}}),
        encoding="utf-8",
    )
    artifacts = [
        _artifact(
            "external_benchmark_kickoff_package.json",
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_kickoff_package.json",
            b"kickoff",
        ),
        _artifact(
            "external_benchmark_kickoff_package.md",
            "implementation/phase1/release/external_benchmark_kickoff/external_benchmark_kickoff_package.md",
            b"kickoff-md",
        ),
        _artifact(
            "case_onepage_attestation_index.json",
            "implementation/phase1/release/external_benchmark_kickoff/case_onepage_attestation_index.json",
            b"case-index",
        ),
        _artifact(
            "case_onepage_attestation_index.md",
            "implementation/phase1/release/external_benchmark_kickoff/case_onepage_attestation_index.md",
            b"case-index-md",
        ),
        _artifact(
            "exact_topology_structural_preview_promotion_queue.json",
            "implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.json",
            b"queue",
        ),
        _artifact(
            "exact_topology_structural_preview_promotion_queue.md",
            "implementation/phase1/release/midas_native_roundtrip/exact_topology_structural_preview_promotion_queue.md",
            b"queue-md",
        ),
    ]

    command = build_release_publication_candidate._run_registry_generation(
        work_dir=tmp_path / "work",
        generated_at="",
        python_executable="python",
        manifest_artifacts=artifacts,
    )

    assert len(calls) == 2
    assert calls[0] == calls[1] == command
    assert "--external-benchmark-submission-updates" in command
    assert "--residual-holdout-closure-updates" in command
    assert "--external-benchmark-kickoff-package" in command
    assert "--external-benchmark-kickoff-markdown" in command
    assert "--case-onepage-attestation-index" in command
    assert "--case-onepage-attestation-index-markdown" in command
    assert "--exact-topology-structural-preview-promotion-queue" in command
    assert "--exact-topology-structural-preview-promotion-queue-markdown" in command
