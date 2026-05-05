from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_release_p0_closure.py"
SPEC = importlib.util.spec_from_file_location("check_release_p0_closure", SCRIPT_PATH)
assert SPEC is not None
check_release_p0_closure = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_release_p0_closure)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _manifest(tmp_path: Path) -> Path:
    required_payload = b"required"
    optional_payload = b"optional"
    return _write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": check_release_p0_closure.RELEASE_MANIFEST_SCHEMA_VERSION,
            "release_tag": "structural-analysis-artifacts-test",
            "artifacts": [
                {
                    "asset_name": "required.zip",
                    "local_path": "implementation/phase1/release/required.zip",
                    "bytes": len(required_payload),
                    "sha256": _sha256(required_payload),
                    "required": True,
                },
                {
                    "asset_name": "optional.pdf",
                    "local_path": "implementation/phase1/release/optional.pdf",
                    "bytes": len(optional_payload),
                    "sha256": _sha256(optional_payload),
                    "required": False,
                },
            ],
        },
    )


def _artifact_root(tmp_path: Path) -> Path:
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"required")
    (artifact_root / "optional.pdf").write_bytes(b"optional")
    return artifact_root


def _assets_json(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "assets.json",
        [
            {"name": "required.zip", "size": len(b"required")},
            {"name": "optional.pdf", "size": len(b"optional")},
        ],
    )


def _upload_plan_json(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "upload-plan.json",
        {
            "ok": True,
            "release_tag": "structural-analysis-artifacts-test",
            "artifact_root": str(tmp_path / "assets"),
            "upload_assets": [
                {
                    "asset_name": "required.zip",
                    "path": str(tmp_path / "assets" / "required.zip"),
                    "bytes": len(b"required"),
                    "sha256": _sha256(b"required"),
                    "required": True,
                },
                {
                    "asset_name": "optional.pdf",
                    "path": str(tmp_path / "assets" / "optional.pdf"),
                    "bytes": len(b"optional"),
                    "sha256": _sha256(b"optional"),
                    "required": False,
                },
            ],
            "extra_files": [],
            "errors": [],
            "totals": {
                "manifest_assets": 2,
                "selected_assets": 2,
                "upload_assets": 2,
                "extra_files": 0,
                "errors": 0,
            },
        },
    )


def _metadata_preflight_json(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "metadata-preflight.json",
        {
            "ok": True,
            "mode": "artifact_root",
            "manifest_errors": [],
            "present": [
                {
                    "asset_name": "required.zip",
                    "required": True,
                    "hydrate_target": str(tmp_path / "assets" / "required.zip"),
                    "expected_bytes": len(b"required"),
                    "expected_sha256": _sha256(b"required"),
                    "status": "present",
                    "actual_bytes": len(b"required"),
                },
                {
                    "asset_name": "optional.pdf",
                    "required": False,
                    "hydrate_target": str(tmp_path / "assets" / "optional.pdf"),
                    "expected_bytes": len(b"optional"),
                    "expected_sha256": _sha256(b"optional"),
                    "status": "present",
                    "actual_bytes": len(b"optional"),
                },
            ],
            "required_missing": [],
            "optional_missing": [],
            "totals": {
                "manifest_assets": 2,
                "present": 2,
                "required_missing": 0,
                "optional_missing": 0,
            },
        },
    )


def _post_publish_roundtrip_json(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "post-publish-roundtrip.json",
        {
            "ok": True,
            "release_tag": "structural-analysis-artifacts-test",
            "manifest": str(tmp_path / "manifest.json"),
            "artifact_root": str(tmp_path / "hydrated"),
            "actions": [
                {
                    "asset_name": "required.zip",
                    "status": "downloaded",
                    "manifest_bytes": len(b"required"),
                    "manifest_sha256": _sha256(b"required"),
                    "downloaded_bytes": len(b"required"),
                    "downloaded_sha256": _sha256(b"required"),
                    "required": True,
                },
                {
                    "asset_name": "optional.pdf",
                    "status": "already_present",
                    "manifest_bytes": len(b"optional"),
                    "manifest_sha256": _sha256(b"optional"),
                    "destination_bytes": len(b"optional"),
                    "destination_sha256": _sha256(b"optional"),
                    "required": False,
                },
            ],
            "errors": [],
            "totals": {
                "selected_assets": 2,
                "already_present": 1,
                "downloaded": 1,
                "errors": 0,
            },
        },
    )


def test_status_reports_closed_when_all_required_offline_checks_pass(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = _artifact_root(tmp_path)
    assets_path = _assets_json(tmp_path)

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=assets_path,
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is True
    assert status["status"] == "closed"
    assert status["manifest"]["ok"] is True
    assert status["tag_ref"]["present"] is True
    assert status["upload_plan"]["ok"] is True
    assert status["asset_listing"]["ok"] is True
    assert status["asset_listing"]["counts"]["matched"] == 2
    assert status["asset_listing"]["require_exact"] is True


def test_status_validates_upload_plan_and_metadata_preflight_evidence(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = _artifact_root(tmp_path)
    assets_path = _assets_json(tmp_path)
    upload_plan_path = _upload_plan_json(tmp_path)
    preflight_path = _metadata_preflight_json(tmp_path)
    roundtrip_path = _post_publish_roundtrip_json(tmp_path)

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=assets_path,
        upload_plan_json=upload_plan_path,
        metadata_preflight_json=preflight_path,
        post_publish_roundtrip_json=roundtrip_path,
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is True
    assert status["upload_plan"]["evidence_json"] == str(upload_plan_path)
    assert status["upload_plan"]["evidence_ok"] is True
    assert status["metadata_preflight"]["evidence_json"] == str(preflight_path)
    assert status["metadata_preflight"]["ok"] is True
    assert status["metadata_preflight"]["counts"]["present"] == 2
    assert status["post_publish_roundtrip"]["evidence_json"] == str(roundtrip_path)
    assert status["post_publish_roundtrip"]["ok"] is True
    assert status["post_publish_roundtrip"]["counts"]["downloaded"] == 1


def test_status_keeps_p0_open_when_post_publish_roundtrip_sha_does_not_match_manifest(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = _artifact_root(tmp_path)
    assets_path = _assets_json(tmp_path)
    roundtrip_path = _post_publish_roundtrip_json(tmp_path)
    roundtrip = json.loads(roundtrip_path.read_text(encoding="utf-8"))
    roundtrip["actions"][0]["downloaded_sha256"] = "0" * 64
    roundtrip_path.write_text(json.dumps(roundtrip), encoding="utf-8")

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=assets_path,
        upload_plan_json=_upload_plan_json(tmp_path),
        metadata_preflight_json=_metadata_preflight_json(tmp_path),
        post_publish_roundtrip_json=roundtrip_path,
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["post_publish_roundtrip"]["ok"] is False
    assert any(
        "post-publish roundtrip actual sha256 mismatch for required.zip" in error
        for error in status["post_publish_roundtrip"]["errors"]
    )


def test_status_can_close_against_promoted_manifest_when_local_manifest_is_stale(tmp_path: Path) -> None:
    local_manifest_path = _manifest(tmp_path)
    promoted_manifest_path = tmp_path / "promoted-manifest.json"
    promoted_manifest_path.write_text(local_manifest_path.read_text(encoding="utf-8"), encoding="utf-8")
    local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
    local_manifest["artifacts"][0]["bytes"] = 999
    local_manifest["artifacts"][0]["sha256"] = "0" * 64
    local_manifest_path.write_text(json.dumps(local_manifest), encoding="utf-8")

    status = check_release_p0_closure.build_status(
        manifest_path=local_manifest_path,
        promoted_manifest_json=promoted_manifest_path,
        artifact_root=_artifact_root(tmp_path),
        assets_json=_assets_json(tmp_path),
        upload_plan_json=_upload_plan_json(tmp_path),
        metadata_preflight_json=_metadata_preflight_json(tmp_path),
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is True
    assert status["source_manifest"] == str(local_manifest_path)
    assert status["publication_manifest"] == str(promoted_manifest_path)
    assert status["publication_manifest_source"] == "promoted"


def test_status_keeps_p0_open_when_upload_plan_evidence_sha_does_not_match_manifest(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = _artifact_root(tmp_path)
    assets_path = _assets_json(tmp_path)
    upload_plan_path = _upload_plan_json(tmp_path)
    upload_plan = json.loads(upload_plan_path.read_text(encoding="utf-8"))
    upload_plan["upload_assets"][0]["sha256"] = "0" * 64
    upload_plan_path.write_text(json.dumps(upload_plan), encoding="utf-8")

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=assets_path,
        upload_plan_json=upload_plan_path,
        metadata_preflight_json=_metadata_preflight_json(tmp_path),
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["upload_plan"]["ok"] is False
    assert any("upload plan sha256 mismatch for required.zip" in error for error in status["upload_plan"]["errors"])


def test_status_keeps_p0_open_when_metadata_preflight_evidence_bytes_do_not_match_manifest(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = _artifact_root(tmp_path)
    assets_path = _assets_json(tmp_path)
    preflight_path = _metadata_preflight_json(tmp_path)
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    preflight["present"][1]["expected_bytes"] = 999
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=assets_path,
        upload_plan_json=_upload_plan_json(tmp_path),
        metadata_preflight_json=preflight_path,
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["metadata_preflight"]["ok"] is False
    assert any(
        "metadata preflight bytes mismatch for optional.pdf" in error
        for error in status["metadata_preflight"]["errors"]
    )


def test_require_exact_keeps_p0_open_for_missing_optional_and_extra_assets(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _write_json(
        tmp_path / "assets.json",
        [
            {"name": "required.zip", "size": len(b"required")},
            {"name": "extra.txt", "size": 1},
        ],
    )

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=None,
        assets_json=assets_path,
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["asset_listing"]["ok"] is False
    assert status["asset_listing"]["require_exact"] is True
    assert status["asset_listing"]["counts"]["missing_required"] == 0
    assert status["asset_listing"]["counts"]["missing_optional"] == 1
    assert status["asset_listing"]["counts"]["extra_assets"] == 1


def test_p0_closure_defaults_to_exact_asset_listing(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _write_json(
        tmp_path / "assets.json",
        [
            {"name": "required.zip", "size": len(b"required")},
            {"name": "extra.txt", "size": 1},
        ],
    )

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        assets_json=assets_path,
        require_all=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["asset_listing"]["ok"] is False
    assert status["asset_listing"]["require_exact"] is True
    assert status["asset_listing"]["counts"]["missing_optional"] == 1
    assert status["asset_listing"]["counts"]["extra_assets"] == 1


def test_cli_defaults_to_exact_asset_listing_for_p0_closure(tmp_path: Path, capsys) -> None:
    manifest_path = _manifest(tmp_path)
    assets_path = _write_json(
        tmp_path / "assets.json",
        [
            {"name": "required.zip", "size": len(b"required")},
            {"name": "extra.txt", "size": 1},
        ],
    )

    exit_code = check_release_p0_closure.main(
        [
            "--manifest",
            str(manifest_path),
            "--assets-json",
            str(assets_path),
            "--require-all",
            "--tag-ref-present",
            "true",
            "--fail-unclosed",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["p0_closed"] is False
    assert payload["asset_listing"]["require_exact"] is True
    assert payload["asset_listing"]["counts"]["missing_optional"] == 1
    assert payload["asset_listing"]["counts"]["extra_assets"] == 1
    assert captured.err == ""


def test_fail_unclosed_returns_nonzero_when_tag_ref_fixture_is_missing(tmp_path: Path, capsys) -> None:
    exit_code = check_release_p0_closure.main(
        [
            "--manifest",
            str(_manifest(tmp_path)),
            "--artifact-root",
            str(_artifact_root(tmp_path)),
            "--assets-json",
            str(_assets_json(tmp_path)),
            "--require-all",
            "--require-exact",
            "--tag-ref-present",
            "false",
            "--fail-unclosed",
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["p0_closed"] is False
    assert payload["tag_ref"]["status"] == "missing"
    assert captured.err == ""


def test_stale_artifact_root_reports_upload_plan_errors_without_traceback(tmp_path: Path) -> None:
    manifest_path = _manifest(tmp_path)
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "required.zip").write_bytes(b"stale")

    status = check_release_p0_closure.build_status(
        manifest_path=manifest_path,
        artifact_root=artifact_root,
        assets_json=_assets_json(tmp_path),
        require_all=True,
        require_exact=True,
        tag_ref_present=True,
    )

    assert status["p0_closed"] is False
    assert status["upload_plan"]["ok"] is False
    assert any("bytes mismatch for required.zip" in error for error in status["upload_plan"]["errors"])
    assert any("missing asset: optional.pdf" in error for error in status["upload_plan"]["errors"])


def test_missing_assets_json_reports_asset_listing_error_without_traceback(tmp_path: Path, capsys) -> None:
    exit_code = check_release_p0_closure.main(
        [
            "--manifest",
            str(_manifest(tmp_path)),
            "--assets-json",
            str(tmp_path / "missing-assets.json"),
            "--require-all",
            "--require-exact",
            "--tag-ref-present",
            "true",
            "--fail-unclosed",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Asset listing: error" in captured.out
    assert "missing-assets.json" in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_structure_only_source_repo_mode_is_unknown_but_successful_without_fail_gate(tmp_path: Path, capsys) -> None:
    exit_code = check_release_p0_closure.main(["--manifest", str(_manifest(tmp_path))])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "P0 closure: unclosed" in captured.out
    assert "Tag ref: unknown" in captured.out
    assert "Asset listing: not checked" in captured.out
    assert "Upload plan: not checked" in captured.out
