from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "fetch_github_release_assets.py"
SPEC = importlib.util.spec_from_file_location("fetch_github_release_assets", SCRIPT_PATH)
assert SPEC is not None
fetch_github_release_assets = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(fetch_github_release_assets)


class _Response:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_fetch_release_assets_normalizes_metadata_and_uses_github_token(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _Response(
            {
                "tag_name": "v1.0.0",
                "html_url": "https://github.com/acme/widgets/releases/tag/v1.0.0",
                "assets": [
                    {"name": "bundle.zip", "size": 123, "browser_download_url": "unused"},
                    {"name": "report.pdf", "size": 45},
                ],
            }
        )

    monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
    monkeypatch.delenv("GH_TOKEN", raising=False)

    payload = fetch_github_release_assets.fetch_release_assets(
        "acme/widgets",
        "v1.0.0",
        urlopen=fake_urlopen,
    )

    assert captured["url"] == "https://api.github.com/repos/acme/widgets/releases/tags/v1.0.0"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"
    assert captured["headers"]["Accept"] == "application/vnd.github+json"
    assert captured["timeout"] == 30
    assert payload == {
        "assets": [
            {"name": "bundle.zip", "size": 123},
            {"name": "report.pdf", "size": 45},
        ],
        "html_url": "https://github.com/acme/widgets/releases/tag/v1.0.0",
        "tag_name": "v1.0.0",
    }


def test_fetch_release_assets_falls_back_to_gh_token(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        return _Response({"tag_name": "v1", "assets": []})

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GH_TOKEN", "fallback-token")

    fetch_github_release_assets.fetch_release_assets("acme/widgets", "v1", urlopen=fake_urlopen)

    assert captured["headers"]["Authorization"] == "Bearer fallback-token"


def test_fetch_release_assets_omits_authorization_when_no_token(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        return _Response({"tag_name": "v1", "assets": []})

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    fetch_github_release_assets.fetch_release_assets("acme/widgets", "v1", urlopen=fake_urlopen)

    assert "Authorization" not in captured["headers"]


def test_fetch_release_assets_404_has_clear_private_missing_auth_message(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "Not Found", hdrs=None, fp=None)

    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)

    with pytest.raises(fetch_github_release_assets.FetchReleaseAssetsError) as excinfo:
        fetch_github_release_assets.fetch_release_assets("acme/widgets", "missing", urlopen=fake_urlopen)

    message = str(excinfo.value)
    assert "GitHub release was not found" in message
    assert "private repository" in message
    assert "missing release/tag" in message
    assert "auth token" in message


def test_fetch_release_assets_rejects_bad_asset_schema(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        return _Response({"tag_name": "v1", "assets": [{"name": "bad.zip", "size": "123"}]})

    with pytest.raises(fetch_github_release_assets.FetchReleaseAssetsError, match="assets\\[0\\].size"):
        fetch_github_release_assets.fetch_release_assets("acme/widgets", "v1", urlopen=fake_urlopen)


def test_cli_writes_json_output_file(tmp_path: Path, monkeypatch, capsys) -> None:
    def fake_fetch_release_assets(repo, tag, *, token_env, urlopen=None):
        assert repo == "acme/widgets"
        assert tag == "v1"
        assert token_env == "CUSTOM_TOKEN"
        return {"assets": [{"name": "bundle.zip", "size": 123}], "tag_name": "v1"}

    out_path = tmp_path / "assets.json"
    monkeypatch.setattr(fetch_github_release_assets, "fetch_release_assets", fake_fetch_release_assets)

    exit_code = fetch_github_release_assets.main(
        ["--repo", "acme/widgets", "--tag", "v1", "--token-env", "CUSTOM_TOKEN", "--out", str(out_path)]
    )

    assert exit_code == 0
    assert json.loads(out_path.read_text(encoding="utf-8")) == {
        "assets": [{"name": "bundle.zip", "size": 123}],
        "tag_name": "v1",
    }
    assert captured_json(capsys) == {
        "assets": [{"name": "bundle.zip", "size": 123}],
        "tag_name": "v1",
    }


def captured_json(capsys) -> object:
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out)
