from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_p0_closure_status.py"
SPEC = importlib.util.spec_from_file_location("check_p0_closure_status", SCRIPT_PATH)
assert SPEC is not None
check_p0_closure_status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_p0_closure_status)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _report(path: Path, *, summary_line: str = "PASS") -> Path:
    return _write_json(
        path,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "summary_line": summary_line,
        },
    )


def _reports(tmp_path: Path) -> dict[str, Path]:
    return {
        key: _report(tmp_path / f"{key}.json", summary_line=f"{key}: PASS")
        for key in check_p0_closure_status.DEFAULT_REPORTS
    }


def _release_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    payload = b"release"
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(payload)
    manifest = _write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": "structural_analysis_release_artifacts_manifest.v1",
            "release_tag": "test-release",
            "artifacts": [
                {
                    "asset_name": "bundle.zip",
                    "local_path": "implementation/phase1/release/bundle.zip",
                    "bytes": len(payload),
                    "sha256": _sha256(payload),
                    "required": True,
                }
            ],
        },
    )
    assets_json = _write_json(tmp_path / "assets.json", {"assets": [{"name": "bundle.zip", "size": len(payload)}]})
    return manifest, artifact_root, assets_json


def _upload_plan_json(tmp_path: Path) -> Path:
    payload = b"release"
    return _write_json(
        tmp_path / "upload-plan.json",
        {
            "ok": True,
            "release_tag": "test-release",
            "artifact_root": str(tmp_path / "assets"),
            "upload_assets": [
                {
                    "asset_name": "bundle.zip",
                    "path": str(tmp_path / "assets" / "bundle.zip"),
                    "bytes": len(payload),
                    "sha256": _sha256(payload),
                    "required": True,
                }
            ],
            "extra_files": [],
            "errors": [],
            "totals": {
                "manifest_assets": 1,
                "selected_assets": 1,
                "upload_assets": 1,
                "extra_files": 0,
                "errors": 0,
            },
        },
    )


def _metadata_preflight_json(tmp_path: Path) -> Path:
    payload = b"release"
    return _write_json(
        tmp_path / "metadata-preflight.json",
        {
            "ok": True,
            "mode": "artifact_root",
            "manifest_errors": [],
            "present": [
                {
                    "asset_name": "bundle.zip",
                    "required": True,
                    "hydrate_target": str(tmp_path / "assets" / "bundle.zip"),
                    "expected_bytes": len(payload),
                    "expected_sha256": _sha256(payload),
                    "status": "present",
                    "actual_bytes": len(payload),
                }
            ],
            "required_missing": [],
            "optional_missing": [],
            "totals": {
                "manifest_assets": 1,
                "present": 1,
                "required_missing": 0,
                "optional_missing": 0,
            },
        },
    )


def _post_publish_roundtrip_json(tmp_path: Path) -> Path:
    payload = b"release"
    return _write_json(
        tmp_path / "post-publish-roundtrip.json",
        {
            "ok": True,
            "release_tag": "test-release",
            "manifest": str(tmp_path / "manifest.json"),
            "artifact_root": str(tmp_path / "hydrated"),
            "actions": [
                {
                    "asset_name": "bundle.zip",
                    "status": "downloaded",
                    "manifest_bytes": len(payload),
                    "manifest_sha256": _sha256(payload),
                    "downloaded_bytes": len(payload),
                    "downloaded_sha256": _sha256(payload),
                    "required": True,
                }
            ],
            "errors": [],
            "totals": {"selected_assets": 1, "downloaded": 1, "already_present": 0, "errors": 0},
        },
    )


def _non_exact_release_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    required_payload = b"release"
    optional_payload = b"datasheet"
    artifact_root = tmp_path / "assets"
    artifact_root.mkdir()
    (artifact_root / "bundle.zip").write_bytes(required_payload)
    (artifact_root / "datasheet.pdf").write_bytes(optional_payload)
    manifest = _write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": "structural_analysis_release_artifacts_manifest.v1",
            "release_tag": "test-release",
            "artifacts": [
                {
                    "asset_name": "bundle.zip",
                    "local_path": "implementation/phase1/release/bundle.zip",
                    "bytes": len(required_payload),
                    "sha256": _sha256(required_payload),
                    "required": True,
                },
                {
                    "asset_name": "datasheet.pdf",
                    "local_path": "implementation/phase1/release/datasheet.pdf",
                    "bytes": len(optional_payload),
                    "sha256": _sha256(optional_payload),
                    "required": False,
                },
            ],
        },
    )
    assets_json = _write_json(
        tmp_path / "assets.json",
        {
            "assets": [
                {"name": "bundle.zip", "size": len(required_payload)},
                {"name": "extra.txt", "size": 1},
            ]
        },
    )
    return manifest, artifact_root, assets_json


def test_p0_status_reports_core_closed_and_release_open_without_listing(tmp_path: Path) -> None:
    status = check_p0_closure_status.build_status(
        manifest=tmp_path / "missing-release-manifest.json",
        reports=_reports(tmp_path),
    )

    assert status["p0_closed"] is False
    assert status["release_publication_closed"] is False
    assert status["core_evidence_closed"] is True
    assert status["next_action"] == "run Publish Release Assets workflow or provide release asset listing"


def test_p0_status_uses_checked_in_fallbacks_when_generated_reports_are_absent(tmp_path: Path, monkeypatch) -> None:
    missing_reports = {
        key: tmp_path / "generated" / f"{key}.json"
        for key in check_p0_closure_status.DEFAULT_REPORTS
    }
    fallback_reports = {
        key: (_report(tmp_path / "release_evidence" / f"{key}.json", summary_line=f"{key}: fallback PASS"),)
        for key in check_p0_closure_status.DEFAULT_REPORTS
    }
    monkeypatch.setattr(check_p0_closure_status, "DEFAULT_REPORTS", missing_reports)
    monkeypatch.setattr(check_p0_closure_status, "DEFAULT_REPORT_FALLBACKS", fallback_reports)

    status = check_p0_closure_status.build_status(manifest=tmp_path / "missing-release-manifest.json")

    assert status["core_evidence_closed"] is True
    geometry_gate = next(gate for gate in status["gates"] if gate["label"] == "P0-4 MIDAS-KDS geometry identity")
    assert geometry_gate["status"] == "closed"
    assert geometry_gate["path"].endswith("release_evidence/p0_4_midas_kds_geometry_identity.json")
    assert geometry_gate["primary_path"].endswith("generated/p0_4_midas_kds_geometry_identity.json")


def test_p0_status_closes_when_release_and_core_evidence_pass(tmp_path: Path) -> None:
    manifest, artifact_root, assets_json = _release_fixture(tmp_path)

    status = check_p0_closure_status.build_status(
        manifest=manifest,
        release_assets_json=assets_json,
        artifact_root=artifact_root,
        tag_ref_present=True,
        reports=_reports(tmp_path),
    )

    assert status["p0_closed"] is True
    assert status["release_publication_closed"] is True
    assert status["core_evidence_closed"] is True
    assert status["next_action"] == "promote release manifest and proceed to P1/P2 breadth work"


def test_p0_status_can_read_release_publication_evidence_index(tmp_path: Path) -> None:
    manifest, artifact_root, assets_json = _release_fixture(tmp_path)
    upload_plan_json = _upload_plan_json(tmp_path)
    metadata_preflight_json = _metadata_preflight_json(tmp_path)
    roundtrip_json = _post_publish_roundtrip_json(tmp_path)
    p0_status_json = _write_json(tmp_path / "p0-status.json", {"p0_closed": True})
    evidence_index = _write_json(
        tmp_path / "release-publication-evidence-index.json",
        {
            "schema_version": "release-publication-evidence-index.v1",
            "tag_ref_present": True,
            "paths": {
                "manifest": str(manifest),
                "release_assets_json": str(assets_json),
                "artifact_root": str(artifact_root),
                "upload_plan_json": str(upload_plan_json),
                "metadata_preflight_json": str(metadata_preflight_json),
                "post_publish_roundtrip_json": str(roundtrip_json),
                "p0_status_json": str(p0_status_json),
            },
        },
    )

    status = check_p0_closure_status.build_status(
        manifest=tmp_path / "stale-local-manifest.json",
        publication_evidence_index=evidence_index,
        reports=_reports(tmp_path),
    )

    assert status["p0_closed"] is True
    assert status["publication_evidence_index"] == str(evidence_index)
    release_gate = status["gates"][0]
    assert release_gate["manifest"] == str(manifest)
    assert release_gate["release_assets_json"] == str(assets_json)
    assert release_gate["details"]["tag_ref"]["present"] is True
    assert release_gate["details"]["post_publish_roundtrip"]["ok"] is True
    assert release_gate["details"]["post_publish_roundtrip"]["evidence_json"] == str(roundtrip_json)


def test_p0_status_surfaces_upload_plan_and_metadata_preflight_evidence(tmp_path: Path) -> None:
    manifest, artifact_root, assets_json = _release_fixture(tmp_path)
    upload_plan_json = _upload_plan_json(tmp_path)
    metadata_preflight_json = _metadata_preflight_json(tmp_path)
    roundtrip_json = _post_publish_roundtrip_json(tmp_path)

    status = check_p0_closure_status.build_status(
        manifest=manifest,
        release_assets_json=assets_json,
        artifact_root=artifact_root,
        upload_plan_json=upload_plan_json,
        metadata_preflight_json=metadata_preflight_json,
        post_publish_roundtrip_json=roundtrip_json,
        tag_ref_present=True,
        reports=_reports(tmp_path),
    )

    release_gate = status["gates"][0]
    assert status["p0_closed"] is True
    assert release_gate["details"]["upload_plan"]["evidence_json"] == str(upload_plan_json)
    assert release_gate["details"]["upload_plan"]["evidence_ok"] is True
    assert release_gate["details"]["metadata_preflight"]["evidence_json"] == str(metadata_preflight_json)
    assert release_gate["details"]["metadata_preflight"]["ok"] is True
    assert release_gate["details"]["post_publish_roundtrip"]["evidence_json"] == str(roundtrip_json)
    assert release_gate["details"]["post_publish_roundtrip"]["ok"] is True


def test_p0_status_can_use_promoted_manifest_when_local_manifest_is_stale(tmp_path: Path) -> None:
    local_manifest, artifact_root, assets_json = _release_fixture(tmp_path)
    promoted_manifest = tmp_path / "promoted-manifest.json"
    promoted_manifest.write_text(local_manifest.read_text(encoding="utf-8"), encoding="utf-8")
    stale_payload = json.loads(local_manifest.read_text(encoding="utf-8"))
    stale_payload["artifacts"][0]["bytes"] = 999
    stale_payload["artifacts"][0]["sha256"] = "0" * 64
    local_manifest.write_text(json.dumps(stale_payload), encoding="utf-8")

    status = check_p0_closure_status.build_status(
        manifest=local_manifest,
        promoted_manifest_json=promoted_manifest,
        release_assets_json=assets_json,
        artifact_root=artifact_root,
        upload_plan_json=_upload_plan_json(tmp_path),
        metadata_preflight_json=_metadata_preflight_json(tmp_path),
        tag_ref_present=True,
        reports=_reports(tmp_path),
    )

    release_gate = status["gates"][0]
    assert status["p0_closed"] is True
    assert release_gate["promoted_manifest_json"] == str(promoted_manifest)
    assert release_gate["details"]["publication_manifest_source"] == "promoted"


def test_p0_status_keeps_release_open_when_listing_is_not_exact(tmp_path: Path) -> None:
    manifest, artifact_root, assets_json = _non_exact_release_fixture(tmp_path)

    status = check_p0_closure_status.build_status(
        manifest=manifest,
        release_assets_json=assets_json,
        artifact_root=artifact_root,
        tag_ref_present=True,
        reports=_reports(tmp_path),
    )

    asset_listing = status["gates"][0]["details"]["asset_listing"]
    assert status["p0_closed"] is False
    assert status["release_publication_closed"] is False
    assert status["core_evidence_closed"] is True
    assert asset_listing["require_exact"] is True
    assert asset_listing["counts"]["missing_optional"] == 1
    assert asset_listing["counts"]["extra_assets"] == 1


def test_cli_writes_markdown_and_can_fail_open(tmp_path: Path, capsys) -> None:
    out_md = tmp_path / "status.md"

    exit_code = check_p0_closure_status.main(
        [
            "--manifest",
            str(tmp_path / "missing-release-manifest.json"),
            "--out-md",
            str(out_md),
            "--fail-open",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "P0 Closure Status" in captured.out
    assert "P0 Closure Status" in out_md.read_text(encoding="utf-8")
