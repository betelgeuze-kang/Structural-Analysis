from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CAPTURE_COMMAND = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- viewer-readme-capture --root ."
)


def test_readme_capture_product_entrypoint_is_rust_owned() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    source_map = (
        ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
    ).read_text(encoding="utf-8")
    transition = (ROOT / "docs/native/workbench-ui-transition-v1.md").read_text(
        encoding="utf-8"
    )

    assert package["scripts"]["capture:readme-viewer-image"] == CAPTURE_COMMAND
    assert "node ./scripts/capture-readme-viewer-image.mjs" not in package["scripts"].values()
    assert "viewer_readme_capture_contract" in source_map
    assert "native/crates/structural-frontend-contract/src/viewer_readme_capture.rs" in source_map
    assert "native/crates/structural-frontend-contract/src/verified_publication.rs" in source_map
    assert "viewer-readme-capture" in transition


def test_readme_capture_dry_run_is_canonical_process_free_and_non_mutating() -> None:
    tracked_output = ROOT / "docs/assets/commercialization-status-card.png"
    before = tracked_output.read_bytes()
    result = subprocess.run(
        [
            "cargo",
            "run",
            "--quiet",
            "--locked",
            "--manifest-path",
            "native/Cargo.toml",
            "-p",
            "structural-frontend-contract",
            "--",
            "viewer-readme-capture",
            "--root",
            ".",
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-viewer-readme-capture-receipt.v1"
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["requested_output"] == "docs/assets/commercialization-status-card.png"
    assert payload["published_output_path"] is None
    assert payload["previous_output_state"] == "regular_file"
    assert payload["previous_output_byte_length"] == len(before)
    assert payload["previous_output_sha256"] == f"sha256:{hashlib.sha256(before).hexdigest()}"
    assert payload["viewport_width"] == 1600
    assert payload["viewport_height"] == 900
    assert payload["view_preset"] == "review"
    assert payload["camera_x"] == -0.55
    assert payload["camera_y"] == 0.85
    assert payload["camera_z"] == 0.35
    assert payload["png_sha256"] is None
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_codes"] == []
    assert len(payload["source_identities"]) == 3
    assert [row["label"] for row in payload["source_identities"]] == [
        "viewer_index",
        "readme_capture",
        "canvas_frame_probe",
    ]
    receipt_hash = payload.pop("receipt_hash")
    canonical = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert receipt_hash == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
    assert tracked_output.read_bytes() == before
