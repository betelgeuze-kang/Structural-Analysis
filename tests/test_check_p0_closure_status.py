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


def test_p0_status_reports_core_closed_and_release_open_without_listing(tmp_path: Path) -> None:
    status = check_p0_closure_status.build_status(
        manifest=tmp_path / "missing-release-manifest.json",
        reports=_reports(tmp_path),
    )

    assert status["p0_closed"] is False
    assert status["release_publication_closed"] is False
    assert status["core_evidence_closed"] is True
    assert status["next_action"] == "run Publish Release Assets workflow or provide release asset listing"


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
