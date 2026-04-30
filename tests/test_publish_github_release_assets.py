from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "publish_github_release_assets.py"
SPEC = importlib.util.spec_from_file_location("publish_github_release_assets", SCRIPT_PATH)
assert SPEC is not None
publish_github_release_assets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(publish_github_release_assets)


class _Response:
    def __init__(self, payload: object | None = None) -> None:
        self._payload = {} if payload is None else payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest_and_assets(tmp_path: Path) -> tuple[Path, Path]:
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(b"bundle")
    (artifact_root / "report.json").write_bytes(b"report")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "release_tag": "test-release",
                "artifacts": [
                    {
                        "asset_name": "bundle.zip",
                        "bytes": len(b"bundle"),
                        "sha256": _sha256(b"bundle"),
                        "required": True,
                    },
                    {
                        "asset_name": "report.json",
                        "bytes": len(b"report"),
                        "sha256": _sha256(b"report"),
                        "required": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest_path, artifact_root


def test_dry_run_validates_upload_plan_without_token(tmp_path: Path, monkeypatch) -> None:
    manifest_path, artifact_root = _manifest_and_assets(tmp_path)
    assets_out = tmp_path / "assets.json"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    summary = publish_github_release_assets.publish_release_assets(
        repo="acme/widgets",
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        dry_run=True,
        assets_out=assets_out,
    )

    assert summary["ok"] is True
    assert summary["dry_run"] is True
    assert [row["asset_name"] for row in summary["upload_assets"]] == ["bundle.zip", "report.json"]
    assert json.loads(assets_out.read_text(encoding="utf-8")) == {
        "assets": [
            {"name": "bundle.zip", "size": len(b"bundle")},
            {"name": "report.json", "size": len(b"report")},
        ],
        "tag_name": "test-release",
    }


def test_missing_token_blocks_non_dry_run_before_api_calls(tmp_path: Path, monkeypatch) -> None:
    manifest_path, artifact_root = _manifest_and_assets(tmp_path)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with pytest.raises(publish_github_release_assets.PublishReleaseError, match="Missing GitHub token"):
        publish_github_release_assets.publish_release_assets(
            repo="acme/widgets",
            manifest_path=manifest_path,
            artifact_root=artifact_root,
        )


def test_publish_creates_release_and_uploads_manifest_assets(tmp_path: Path, monkeypatch) -> None:
    manifest_path, artifact_root = _manifest_and_assets(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    calls: list[tuple[str, str]] = []
    uploaded: list[dict[str, object]] = []

    def fake_urlopen(request, timeout):
        calls.append((request.get_method(), request.full_url))
        assert timeout == publish_github_release_assets.DEFAULT_TIMEOUT_SECONDS
        assert dict(request.header_items())["Authorization"] == "Bearer secret"
        parsed = urlparse(request.full_url)
        method = request.get_method()

        if method == "GET" and parsed.path.endswith("/git/ref/tags/test-release"):
            return _Response({"ref": "refs/tags/test-release", "object": {"sha": "abc"}})

        if method == "GET" and parsed.path.endswith("/releases/tags/test-release"):
            if not any(call[0] == "POST" and call[1].endswith("/releases") for call in calls):
                raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)
            return _Response(
                {
                    "id": 42,
                    "tag_name": "test-release",
                    "html_url": "https://github.com/acme/widgets/releases/tag/test-release",
                    "assets": uploaded,
                }
            )

        if method == "POST" and parsed.path.endswith("/releases"):
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["tag_name"] == "test-release"
            return _Response({"id": 42, "tag_name": "test-release", "assets": []})

        if method == "POST" and parsed.netloc == "uploads.github.com":
            name = parse_qs(parsed.query)["name"][0]
            uploaded.append({"id": 100 + len(uploaded), "name": name, "size": len(request.data)})
            return _Response(uploaded[-1])

        raise AssertionError(f"unexpected request: {method} {request.full_url}")

    summary = publish_github_release_assets.publish_release_assets(
        repo="acme/widgets",
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        urlopen=fake_urlopen,
        assets_out=tmp_path / "release-assets.json",
    )

    assert summary["ok"] is True
    assert summary["release_created"] is True
    assert [row["name"] for row in summary["uploaded_assets"]] == ["bundle.zip", "report.json"]
    assert summary["totals"]["listed_assets"] == 2
    assert calls[0][0] == "GET"
    assert calls[1][0] == "GET"
    assert calls[2][0] == "POST"


def test_existing_release_asset_requires_replace_existing(tmp_path: Path, monkeypatch) -> None:
    manifest_path, artifact_root = _manifest_and_assets(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "secret")

    def fake_urlopen(request, timeout):
        parsed = urlparse(request.full_url)
        if request.get_method() == "GET" and parsed.path.endswith("/git/ref/tags/test-release"):
            return _Response({"ref": "refs/tags/test-release", "object": {"sha": "abc"}})
        if request.get_method() == "GET" and parsed.path.endswith("/releases/tags/test-release"):
            return _Response(
                {
                    "id": 42,
                    "tag_name": "test-release",
                    "assets": [{"id": 1, "name": "bundle.zip", "size": len(b"old")}],
                }
            )
        raise AssertionError(f"unexpected request: {request.get_method()} {request.full_url}")

    with pytest.raises(publish_github_release_assets.PublishReleaseError, match="--replace-existing"):
        publish_github_release_assets.publish_release_assets(
            repo="acme/widgets",
            manifest_path=manifest_path,
            artifact_root=artifact_root,
            urlopen=fake_urlopen,
        )
