from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "materialize_release_asset_root.py"
assert SCRIPT_PATH.exists(), "scripts/materialize_release_asset_root.py must exist"
SPEC = importlib.util.spec_from_file_location("materialize_release_asset_root", SCRIPT_PATH)
assert SPEC is not None
materialize_release_asset_root = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(materialize_release_asset_root)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(tmp_path: Path, artifacts: list[dict]) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "structural_analysis_release_artifacts_manifest.v1",
                "release_tag": "test-release",
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


def _artifact(asset_name: str, local_path: str, payload: bytes, *, required: bool = True) -> dict:
    return {
        "asset_name": asset_name,
        "local_path": local_path,
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "required": required,
    }


def test_dry_run_plans_manifest_assets_without_writing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"fresh bundle"
    source = tmp_path / "implementation" / "phase1" / "release" / "nested" / "bundle.zip"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    optional_payload = b"optional"
    optional = tmp_path / "implementation" / "phase1" / "release" / "optional.pdf"
    optional.write_bytes(optional_payload)
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact("bundle.zip", "implementation/phase1/release/nested/bundle.zip", payload),
            _artifact(
                "optional.pdf",
                "implementation/phase1/release/optional.pdf",
                optional_payload,
                required=False,
            ),
        ],
    )
    artifact_root = tmp_path / "flat-assets"

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        artifact_root,
    )

    assert result["ok"] is True
    assert result["write"] is False
    assert result["release_tag"] == "test-release"
    assert result["required_only"] is False
    assert result["totals"]["selected_assets"] == 2
    assert {action["status"] for action in result["actions"]} == {"would_copy"}
    assert {action["asset_name"] for action in result["actions"]} == {"bundle.zip", "optional.pdf"}
    assert not artifact_root.exists()


def test_required_only_excludes_optional_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"fresh bundle"
    optional_payload = b"optional"
    release_dir = tmp_path / "implementation" / "phase1" / "release"
    release_dir.mkdir(parents=True)
    (release_dir / "bundle.zip").write_bytes(payload)
    (release_dir / "optional.pdf").write_bytes(optional_payload)
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact("bundle.zip", "implementation/phase1/release/bundle.zip", payload),
            _artifact(
                "optional.pdf",
                "implementation/phase1/release/optional.pdf",
                optional_payload,
                required=False,
            ),
        ],
    )

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        tmp_path / "flat-assets",
        required_only=True,
    )

    assert result["ok"] is True
    assert result["required_only"] is True
    assert result["totals"]["selected_assets"] == 1
    assert result["actions"][0]["asset_name"] == "bundle.zip"


def test_write_copies_manifest_sources_to_flat_asset_root(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"fresh registry"
    source = tmp_path / "implementation" / "phase1" / "release" / "signing" / "registry.sig"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    manifest_path = _write_manifest(
        tmp_path,
        [_artifact("registry.sig", "implementation/phase1/release/signing/registry.sig", payload)],
    )
    artifact_root = tmp_path / "flat-assets"

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        artifact_root,
        write=True,
    )

    assert result["ok"] is True
    assert result["actions"][0]["status"] == "copied"
    assert (artifact_root / "registry.sig").read_bytes() == payload
    assert result["actions"][0]["destination_sha256"] == _sha256(payload)
    assert result["actions"][0]["destination_bytes"] == len(payload)


def test_mismatched_source_fails_before_copying(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = tmp_path / "implementation" / "phase1" / "release" / "bundle.zip"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"stale")
    manifest_path = _write_manifest(
        tmp_path,
        [_artifact("bundle.zip", "implementation/phase1/release/bundle.zip", b"fresh bundle")],
    )
    artifact_root = tmp_path / "flat-assets"

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        artifact_root,
        write=True,
    )

    assert result["ok"] is False
    assert any("bytes mismatch for bundle.zip source" in error for error in result["errors"])
    assert any("sha256 mismatch for bundle.zip source" in error for error in result["errors"])
    assert not (artifact_root / "bundle.zip").exists()


def test_rejects_private_pem_and_allows_public_pem(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    public_payload = b"-----BEGIN PUBLIC KEY-----\nabc\n-----END PUBLIC KEY-----\n"
    private_payload = b"-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----\n"
    release_dir = tmp_path / "implementation" / "phase1" / "release" / "signing"
    release_dir.mkdir(parents=True)
    (release_dir / "allowed.pub.pem").write_bytes(public_payload)
    (release_dir / "secret.pem").write_bytes(private_payload)
    manifest_path = _write_manifest(
        tmp_path,
        [
            _artifact(
                "allowed.pub.pem",
                "implementation/phase1/release/signing/allowed.pub.pem",
                public_payload,
            ),
            _artifact("secret.pem", "implementation/phase1/release/signing/secret.pem", private_payload),
        ],
    )

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        tmp_path / "flat-assets",
        write=True,
    )

    assert result["ok"] is False
    assert any("unsafe private key-like PEM asset: secret.pem" in error for error in result["errors"])
    assert not (tmp_path / "flat-assets" / "allowed.pub.pem").exists()


def test_rejects_artifact_root_that_is_a_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    payload = b"fresh bundle"
    source = tmp_path / "implementation" / "phase1" / "release" / "bundle.zip"
    source.parent.mkdir(parents=True)
    source.write_bytes(payload)
    manifest_path = _write_manifest(
        tmp_path,
        [_artifact("bundle.zip", "implementation/phase1/release/bundle.zip", payload)],
    )
    artifact_root = tmp_path / "flat-assets"
    artifact_root.write_text("not a directory", encoding="utf-8")

    result = materialize_release_asset_root.materialize_release_asset_root(
        manifest_path,
        artifact_root,
        write=True,
    )

    assert result["ok"] is False
    assert result["errors"] == [f"artifact root exists and is not a directory: {artifact_root}"]


def test_cli_json_reports_failures(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_manifest(
        tmp_path,
        [_artifact("missing.zip", "implementation/phase1/release/missing.zip", b"missing")],
    )

    exit_code = materialize_release_asset_root.main(
        [
            "--manifest",
            str(manifest_path),
            "--artifact-root",
            str(tmp_path / "flat-assets"),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert captured.err == ""
    assert payload["ok"] is False
    assert payload["errors"] == [
        "source artifact missing for missing.zip: implementation/phase1/release/missing.zip"
    ]
