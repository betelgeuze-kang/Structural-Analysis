from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_release_publication_evidence_index.py"
SPEC = importlib.util.spec_from_file_location("build_release_publication_evidence_index", SCRIPT_PATH)
assert SPEC is not None
build_release_publication_evidence_index = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_release_publication_evidence_index)


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_release_publication_evidence_index_records_p0_and_handoff_paths(tmp_path: Path) -> None:
    manifest = _write_json(tmp_path / "candidate-manifest.json", {"release_tag": "test-release"})
    assets = _write_json(tmp_path / "release-assets.json", {"assets": []})
    upload_plan = _write_json(tmp_path / "upload-plan.json", {"ok": True})
    metadata = _write_json(tmp_path / "metadata-preflight.json", {"ok": True})
    p0_status = _write_json(
        tmp_path / "p0-status.json",
        {
            "p0_closed": True,
            "release_publication_closed": True,
            "core_evidence_closed": True,
        },
    )
    roundtrip = _write_json(tmp_path / "post-publish-roundtrip.json", {"ok": True})
    artifact_root = tmp_path / "release-root"
    artifact_root.mkdir()

    payload = build_release_publication_evidence_index.build_index(
        manifest=manifest,
        release_assets_json=assets,
        artifact_root=artifact_root,
        upload_plan_json=upload_plan,
        metadata_preflight_json=metadata,
        p0_status_json=p0_status,
        post_publish_roundtrip_json=roundtrip,
    )

    assert payload["schema_version"] == "release-publication-evidence-index.v1"
    assert payload["release_tag"] == "test-release"
    assert payload["p0_closed"] is True
    assert payload["release_publication_closed"] is True
    assert payload["paths"]["p0_status_json"] == str(p0_status)
    assert payload["paths"]["post_publish_roundtrip_json"] == str(roundtrip)
    assert payload["files"]["post_publish_roundtrip_json"]["exists"] is True
    assert payload["files"]["artifact_root"]["exists"] is True
    assert payload["handoff_commands"]["clean_checkout_chain"] == [
        "python3",
        "scripts/materialize_clean_checkout_evidence_chain.py",
        "--publication-evidence-index",
        "<release-publication-evidence-index.json>",
        "--json",
    ]
    assert payload["handoff_commands"]["post_publish_roundtrip"] == [
        "python3",
        "scripts/hydrate_github_release_assets.py",
        "--repo",
        "<owner/repo>",
        "--manifest",
        str(manifest),
        "--artifact-root",
        "<hydrated-release-root>",
        "--write",
        "--out",
        "<post-publish-roundtrip.json>",
    ]
