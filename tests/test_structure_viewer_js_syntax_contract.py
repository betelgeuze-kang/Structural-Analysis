from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
SYNTAX_COMMAND = (
    "cargo run --quiet --locked --manifest-path native/Cargo.toml "
    "-p structural-frontend-contract -- viewer-js-syntax --root ."
)


def test_viewer_js_syntax_ci_gate_is_rust_owned() -> None:
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    workflow = (ROOT / ".github/workflows/runtime-input-viewer-ci.yml").read_text(
        encoding="utf-8"
    )
    source_map = json.loads(
        (
            ROOT / "native/decommission/legacy-frontend-build-contract-v1.json"
        ).read_text(encoding="utf-8")
    )

    assert package["scripts"]["verify:viewer-js-syntax"] == SYNTAX_COMMAND
    assert "Rust-orchestrated Viewer JavaScript syntax gate" in workflow
    assert "npm run verify:viewer-js-syntax" in workflow
    assert "node --check" not in workflow
    contract = source_map["viewer_js_syntax_contract"]
    assert contract["schema_version"] == "structural-native-viewer-js-syntax-contract.v1"
    assert len(contract["syntax_paths"]) == 10
    assert len(set(contract["syntax_paths"])) == 10


def test_viewer_js_syntax_dry_run_is_canonical_and_process_free() -> None:
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
            "viewer-js-syntax",
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
    assert payload["schema_version"] == "structural-native-viewer-js-syntax-receipt.v1"
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["syntax_source_count"] == 10
    assert len(payload["source_identities"]) == 10
    assert payload["node_runtime_required"] is True
    assert payload["browser_runtime_required"] is False
    assert payload["rust_owned_listener_count"] == 0
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_codes"] == []
    assert payload["external_network_access_accounting"] == "none_syntax_check_only"
    receipt_hash = payload.pop("receipt_hash")
    canonical = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert receipt_hash == f"sha256:{hashlib.sha256(canonical).hexdigest()}"
