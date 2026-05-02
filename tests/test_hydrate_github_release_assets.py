from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "hydrate_github_release_assets.py"
assert SCRIPT_PATH.exists(), "scripts/hydrate_github_release_assets.py must exist"
SPEC = importlib.util.spec_from_file_location("hydrate_github_release_assets", SCRIPT_PATH)
assert SPEC is not None
hydrate_github_release_assets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(hydrate_github_release_assets)


class _Response:
    def __init__(self, payload: object | bytes) -> None:
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_manifest(tmp_path: Path, artifacts: list[dict], *, tag: str = "test-release") -> Path:
    manifest = tmp_path / "release_artifacts_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "structural_analysis_release_artifacts_manifest.v1",
                "release_tag": tag,
                "artifacts": artifacts,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _artifact(asset_name: str, payload: bytes, *, required: bool = True) -> dict:
    return {
        "asset_name": asset_name,
        "local_path": f"implementation/phase1/release/{asset_name}",
        "bytes": len(payload),
        "sha256": _sha256(payload),
        "required": required,
    }


def _fake_release(asset_payloads: dict[str, bytes], *, token: str = "secret-token"):
    calls: list[tuple[str, str, dict[str, str]]] = []

    def fake_urlopen(request, timeout):
        calls.append((request.get_method(), request.full_url, dict(request.header_items())))
        assert timeout == hydrate_github_release_assets.DEFAULT_TIMEOUT_SECONDS
        parsed = urlparse(request.full_url)
        headers = dict(request.header_items())
        assert headers.get("Authorization") == f"Bearer {token}"
        if parsed.path.endswith("/releases/tags/test-release"):
            return _Response(
                {
                    "tag_name": "test-release",
                    "assets": [
                        {
                            "name": name,
                            "size": len(payload),
                            "url": f"https://api.github.com/repos/acme/widgets/releases/assets/{index + 1}",
                        }
                        for index, (name, payload) in enumerate(asset_payloads.items())
                    ],
                }
            )
        if "/releases/assets/" in parsed.path:
            assert headers.get("Accept") == "application/octet-stream"
            asset_index = int(parsed.path.rsplit("/", 1)[-1]) - 1
            return _Response(list(asset_payloads.values())[asset_index])
        raise AssertionError(f"unexpected request: {request.get_method()} {request.full_url}")

    return fake_urlopen, calls


def test_hydrates_manifest_assets_from_github_release(tmp_path: Path, monkeypatch) -> None:
    payloads = {"bundle.zip": b"bundle bytes", "report.json": b'{"ok": true}'}
    manifest = _write_manifest(tmp_path, [_artifact(name, payload) for name, payload in payloads.items()])
    fake_urlopen, calls = _fake_release(payloads)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
        write=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["totals"]["downloaded"] == 2
    assert (tmp_path / "hydrated" / "bundle.zip").read_bytes() == payloads["bundle.zip"]
    assert (tmp_path / "hydrated" / "report.json").read_bytes() == payloads["report.json"]
    assert calls[0][0] == "GET"
    assert calls[1][0] == "GET"


def test_existing_matching_asset_is_not_downloaded(tmp_path: Path, monkeypatch) -> None:
    payloads = {"bundle.zip": b"bundle bytes"}
    manifest = _write_manifest(tmp_path, [_artifact("bundle.zip", payloads["bundle.zip"])])
    artifact_root = tmp_path / "hydrated"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(payloads["bundle.zip"])
    fake_urlopen, calls = _fake_release(payloads)
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=artifact_root,
        write=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is True
    assert result["totals"]["already_present"] == 1
    assert result["totals"]["downloaded"] == 0
    assert len(calls) == 1


def test_missing_release_asset_fails_before_download(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_manifest(tmp_path, [_artifact("missing.zip", b"missing")])
    fake_urlopen, calls = _fake_release({"other.zip": b"other"})
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
        write=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is False
    assert result["errors"] == ["release asset missing for missing.zip"]
    assert len(calls) == 1
    assert not (tmp_path / "hydrated").exists()


def test_release_size_mismatch_fails_before_download(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_manifest(tmp_path, [_artifact("bundle.zip", b"expected")])
    fake_urlopen, calls = _fake_release({"bundle.zip": b"wrong-size"})
    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")

    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
        write=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is False
    assert result["errors"] == ["release asset size mismatch for bundle.zip: manifest=8 actual=10"]
    assert len(calls) == 1


def test_downloaded_sha_mismatch_removes_tmp_file(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_manifest(tmp_path, [_artifact("bundle.zip", b"expected")])

    def fake_urlopen(request, timeout):
        parsed = urlparse(request.full_url)
        if parsed.path.endswith("/releases/tags/test-release"):
            return _Response(
                {
                    "tag_name": "test-release",
                    "assets": [
                        {
                            "name": "bundle.zip",
                            "size": len(b"expected"),
                            "url": "https://api.github.com/repos/acme/widgets/releases/assets/1",
                        }
                    ],
                }
            )
        return _Response(b"wrong-sh")

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
        write=True,
        urlopen=fake_urlopen,
    )

    assert result["ok"] is False
    assert any("downloaded asset failed verification for bundle.zip" in error for error in result["errors"])
    assert not (tmp_path / "hydrated" / "bundle.zip").exists()
    assert not (tmp_path / "hydrated" / ".bundle.zip.tmp").exists()


def test_private_key_like_manifest_asset_is_rejected(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        [
            {
                "asset_name": "release_registry_ed25519.pem",
                "local_path": "implementation/phase1/release/signing/release_registry_ed25519.pem",
                "bytes": 10,
                "sha256": "0" * 64,
                "required": True,
            }
        ],
    )

    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
    )

    assert result["ok"] is False
    assert result["errors"] == ["unsafe private key-like asset name: release_registry_ed25519.pem"]


def test_404_release_error_is_actionable(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_manifest(tmp_path, [_artifact("bundle.zip", b"bundle")])

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    result = hydrate_github_release_assets.hydrate_github_release_assets(
        repo="acme/widgets",
        manifest_path=manifest,
        artifact_root=tmp_path / "hydrated",
        urlopen=fake_urlopen,
    )

    assert result["ok"] is False
    assert result["errors"] == [
        "GitHub release was not found. Check the tag, repository visibility, and token permissions."
    ]


def test_cli_json_reports_hydration_plan(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest = _write_manifest(tmp_path, [_artifact("bundle.zip", b"bundle bytes")])

    def fake_hydrate(**kwargs):
        assert kwargs["repo"] == "acme/widgets"
        assert kwargs["manifest_path"] == manifest
        assert kwargs["artifact_root"] == tmp_path / "hydrated"
        return {
            "ok": True,
            "write": False,
            "repo": "acme/widgets",
            "manifest": str(manifest),
            "artifact_root": str(tmp_path / "hydrated"),
            "release_tag": "test-release",
            "actions": [{"asset_name": "bundle.zip", "status": "would_download"}],
            "errors": [],
            "totals": {"would_download": 1},
        }

    monkeypatch.setattr(hydrate_github_release_assets, "hydrate_github_release_assets", fake_hydrate)

    exit_code = hydrate_github_release_assets.main(
        [
            "--repo",
            "acme/widgets",
            "--manifest",
            str(manifest),
            "--artifact-root",
            str(tmp_path / "hydrated"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["totals"]["would_download"] == 1
