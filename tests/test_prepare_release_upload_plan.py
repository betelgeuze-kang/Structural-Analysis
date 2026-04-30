from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "prepare_release_upload_plan.py"
SPEC = importlib.util.spec_from_file_location("prepare_release_upload_plan", SCRIPT_PATH)
assert SPEC is not None
prepare_release_upload_plan = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(prepare_release_upload_plan)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest(tmp_path: Path) -> Path:
    required_payload = b"required"
    optional_payload = b"optional"
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps(
            {
                "release_tag": "test-release",
                "artifacts": [
                    {
                        "asset_name": "required.zip",
                        "bytes": len(required_payload),
                        "sha256": _sha256(required_payload),
                        "required": True,
                    },
                    {
                        "asset_name": "optional.pdf",
                        "bytes": len(optional_payload),
                        "sha256": _sha256(optional_payload),
                        "required": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_prepare_plan_includes_manifest_assets_and_reports_extras(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"required")
    (artifact_root / "optional.pdf").write_bytes(b"optional")
    (artifact_root / "private.pem").write_text("do-not-upload", encoding="utf-8")

    plan = prepare_release_upload_plan.prepare_release_upload_plan(manifest_path, artifact_root)

    assert plan["ok"] is True
    assert plan["release_tag"] == "test-release"
    assert [row["asset_name"] for row in plan["upload_assets"]] == ["required.zip", "optional.pdf"]
    assert plan["extra_files"] == ["private.pem"]
    assert plan["totals"] == {
        "manifest_assets": 2,
        "selected_assets": 2,
        "upload_assets": 2,
        "extra_files": 1,
        "errors": 0,
    }


def test_required_only_omits_optional_manifest_asset(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"required")
    (artifact_root / "optional.pdf").write_bytes(b"optional")

    plan = prepare_release_upload_plan.prepare_release_upload_plan(
        manifest_path,
        artifact_root,
        required_only=True,
    )

    assert [row["asset_name"] for row in plan["upload_assets"]] == ["required.zip"]
    assert plan["extra_files"] == ["optional.pdf"]


def test_prepare_plan_rejects_missing_and_mismatched_assets(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"stale")

    try:
        prepare_release_upload_plan.prepare_release_upload_plan(manifest_path, artifact_root)
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected ValueError")

    assert "bytes mismatch for required.zip" in message
    assert "missing asset: optional.pdf" in message


def test_cli_writes_plan_file(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"required")
    (artifact_root / "optional.pdf").write_bytes(b"optional")
    out_path = tmp_path / "plan.json"

    exit_code = prepare_release_upload_plan.main(
        [
            "--manifest",
            str(manifest_path),
            "--artifact-root",
            str(artifact_root),
            "--out",
            str(out_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(out_path.read_text(encoding="utf-8"))["release_tag"] == "test-release"
    assert json.loads(captured.out)["release_tag"] == "test-release"
