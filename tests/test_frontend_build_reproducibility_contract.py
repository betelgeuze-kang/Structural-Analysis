from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_frontend_package_manifest_is_pinned_to_the_workbench_shell() -> None:
    package_json = _read_json("package.json")

    assert package_json["name"] == "structural-analysis"
    assert package_json["packageManager"] == "npm@10.8.2"
    assert (
        package_json["scripts"]["verify:frontend-contract"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- check --root ."
    )
    assert (
        package_json["scripts"]["verify:workbench-viewer-delivery"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- delivery --root ."
    )
    assert package_json["scripts"]["build"].endswith(
        "structural-frontend-contract -- delivery --root ."
    )
    assert (
        package_json["scripts"]["verify:frontend-smoke"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- smoke --root ."
    )
    assert (
        package_json["scripts"]["verify:viewer-manifest"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-manifest --root ."
    )
    assert (
        package_json["scripts"]["verify:workbench-prototype-dom-contract"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- prototype --root ."
    )
    assert (
        package_json["scripts"]["verify:workbench-prototype-browser-smoke"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- prototype-browser-smoke --root ."
    )
    assert (
        package_json["scripts"]["verify:workbench-v2-e2e"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- workbench-v2-browser-smoke --root ."
    )
    assert not (ROOT / "scripts" / "verify-workbench-v2-e2e.mjs").exists()
    assert (
        package_json["scripts"]["serve:viewer"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- serve --root ."
    )
    assert (
        package_json["scripts"]["verify:frontend-browser-smoke"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- browser-smoke --root ."
    )
    assert (
        package_json["scripts"]["capture:readme-viewer-image"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-readme-capture --root ."
    )
    assert (
        package_json["scripts"]["export:viewer-report-pdf"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-export --root ."
    )
    assert (
        package_json["scripts"]["verify:viewer-report-pdf"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-report-pdf-smoke --root ."
    )
    assert not (ROOT / "scripts" / "verify-structure-viewer-report-pdf.mjs").exists()
    assert (
        package_json["scripts"]["verify:viewer-performance-probe"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-performance-probe --root ."
    )
    assert (
        package_json["scripts"]["verify:viewer-visual-regression"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-visual-regression --root ."
    )
    assert (
        package_json["scripts"]["verify:viewer-sample-workflow"]
        == "cargo run --quiet --locked --manifest-path native/Cargo.toml "
        "-p structural-frontend-contract -- viewer-sample-workflow --root ."
    )
    assert package_json["dependencies"] == {
        "react": "18.2.0",
        "react-dom": "18.2.0",
    }
    assert package_json["devDependencies"] == {
        "@playwright/test": "1.56.1",
        "@types/react": "18.2.15",
        "@types/react-dom": "18.2.7",
        "@vitejs/plugin-react": "6.0.1",
        "postcss": "8.5.26",
        "typescript": "5.0.2",
        "vite": "8.0.16",
    }
    assert not (ROOT / "pakage.json").exists()


def test_frontend_lockfile_and_docs_match_the_contract() -> None:
    package_json = _read_json("package.json")
    package_lock = _read_json("package-lock.json")
    docs_text = (ROOT / "docs" / "frontend-build-reproducibility.md").read_text(encoding="utf-8")

    assert package_lock["lockfileVersion"] >= 3
    assert package_lock["name"] == package_json["name"]
    assert package_lock["version"] == package_json["version"]
    assert package_lock["packages"][""]["name"] == package_json["name"]
    assert package_lock["packages"][""]["dependencies"] == package_json["dependencies"]
    assert package_lock["packages"][""]["devDependencies"] == package_json["devDependencies"]
    assert "npm run verify:frontend-contract" in docs_text
    assert "npm run verify:frontend-smoke" in docs_text
    assert "structural-frontend-contract delivery" in docs_text
    assert "npm run verify:frontend-browser-smoke" in docs_text
    assert "npm run verify:workbench-prototype-dom-contract" in docs_text
    assert "structural-frontend-contract prototype" in docs_text
    assert "npm run verify:workbench-prototype-browser-smoke" in docs_text
    assert "structural-frontend-contract prototype-browser-smoke" in docs_text
    assert "npm run verify:workbench-v2-e2e" in docs_text
    assert "structural-frontend-contract workbench-v2-browser-smoke" in docs_text
    assert "npm run serve:viewer" in docs_text
    assert "--dry-run" in docs_text
    assert "npm run verify:viewer-manifest" in docs_text
    assert "structural-frontend-contract viewer-manifest" in docs_text
    assert "npm run verify:viewer-report-pdf" in docs_text
    assert "structural-frontend-contract viewer-report-pdf-smoke" in docs_text
    assert "npm run export:viewer-report-pdf" in docs_text
    assert "structural-frontend-contract viewer-report-pdf-export" in docs_text
    assert "npm run capture:readme-viewer-image" in docs_text
    assert "structural-frontend-contract viewer-readme-capture" in docs_text
    assert "npm run verify:viewer-performance-probe" in docs_text
    assert "structural-frontend-contract viewer-performance-probe" in docs_text
    assert "npm run verify:viewer-visual-regression" in docs_text
    assert "structural-frontend-contract viewer-visual-regression" in docs_text
    assert "npm run verify:viewer-sample-workflow" in docs_text
    assert "structural-frontend-contract viewer-sample-workflow" in docs_text
    assert "package-lock.json" in docs_text


def test_native_frontend_contract_helper_runs_without_installed_packages() -> None:
    result = subprocess.run(
        ["npm", "run", "verify:frontend-contract", "--silent"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-frontend-contract-receipt.v1"
    assert payload["commands_executed"] == 0
    assert payload["network_access_count"] == 0


def test_native_frontend_smoke_dry_run_is_process_free_and_self_hashed() -> None:
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
            "smoke",
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
    assert payload["schema_version"] == "structural-native-frontend-smoke-receipt.v1"
    assert payload["mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["logical_commands"] == [["npm", "ci"], ["npm", "run", "build"]]
    assert payload["direct_processes_spawned"] == 0
    assert payload["delivery_receipt_hash"] is None
    assert payload["network_access_accounting"] == "not_instrumented_npm_ci_may_access_registry"
    assert payload["receipt_hash"].startswith("sha256:")


def test_native_viewer_browser_smoke_dry_run_is_listener_and_process_free() -> None:
    result = subprocess.run(
        [
            "npm",
            "run",
            "verify:frontend-browser-smoke",
            "--silent",
            "--",
            "--mode",
            "minimal",
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-viewer-browser-smoke-receipt.v1"
    assert payload["execution_mode"] == "dry_run"
    assert payload["browser_smoke_mode"] == "minimal"
    assert payload["status"] == "planned"
    assert payload["logical_command"] == [
        "node",
        "node_modules/@playwright/test/cli.js",
        "test",
        "tests/frontend/structure-viewer-smoke.spec.ts",
        "--reporter=line",
    ]
    assert payload["node_runtime_required"] is True
    assert payload["browser_runtime_required"] is True
    assert payload["loopback_listener_count"] == 0
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_code"] is None
    assert payload["frontend_contract_receipt_hash"].startswith("sha256:")
    assert payload["playwright_cli_sha256"] is None
    assert payload["external_network_access_accounting"] == (
        "not_instrumented_browser_page_requests"
    )
    assert payload["receipt_hash"].startswith("sha256:")


def test_native_workbench_prototype_contract_runs_without_a_dom_or_browser() -> None:
    result = subprocess.run(
        ["npm", "run", "verify:workbench-prototype-dom-contract", "--silent"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-workbench-prototype-receipt.v1"
    assert payload["status_states"] == {
        "gpu": "MISSING",
        "p0": "UNAVAILABLE",
        "p1": "UNAVAILABLE",
        "solver_connected": "BLOCKED",
    }
    assert payload["commands_executed"] == 0
    assert payload["network_access_count"] == 0
    assert payload["browser_executed"] is False
    assert payload["receipt_hash"].startswith("sha256:")


def test_native_workbench_prototype_browser_smoke_dry_run_is_process_free() -> None:
    result = subprocess.run(
        [
            "npm",
            "run",
            "verify:workbench-prototype-browser-smoke",
            "--silent",
            "--",
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == (
        "structural-native-workbench-prototype-browser-smoke-receipt.v1"
    )
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["logical_command"] == [
        "node",
        "node_modules/@playwright/test/cli.js",
        "test",
        "tests/frontend/workbench-prototype-smoke.spec.ts",
        "--reporter=line",
    ]
    assert payload["server_path_prefix"] == "prototype/structural-workbench/"
    assert payload["base_url_environment"] == "WORKBENCH_PROTOTYPE_BASE_URL"
    assert payload["loopback_listener_count"] == 0
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_code"] is None
    assert payload["prototype_contract_receipt_hash"].startswith("sha256:")
    assert payload["playwright_cli_sha256"] is None
    assert payload["receipt_hash"].startswith("sha256:")


def test_native_workbench_v2_browser_smoke_dry_run_is_process_free() -> None:
    result = subprocess.run(
        [
            "npm",
            "run",
            "verify:workbench-v2-e2e",
            "--silent",
            "--",
            "--dry-run",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == (
        "structural-native-workbench-v2-browser-smoke-receipt.v1"
    )
    assert payload["execution_mode"] == "dry_run"
    assert payload["status"] == "planned"
    assert payload["build_command"] == ["npm", "run", "build"]
    assert payload["build_environment"] == {"VITE_BASE_PATH": "/"}
    assert payload["playwright_command"] == [
        "node",
        "node_modules/@playwright/test/cli.js",
        "test",
        "tests/frontend/workbench-v2-e2e.spec.ts",
        "tests/frontend/workbench-v2-unit-coordinate-guard.spec.ts",
        "tests/frontend/workbench-v2-live-provider-guard.spec.ts",
        "tests/frontend/workbench-v2-job-contract.spec.ts",
        "tests/frontend/workbench-v2-engineering-value-state.spec.ts",
        "tests/frontend/workbench-v2-status-taxonomy.spec.ts",
        "--reporter=line",
    ]
    assert payload["node_environment"] == {
        "NODE_OPTIONS": "--loader=./scripts/json-module-loader.mjs"
    }
    assert len(payload["specifications"]) == 6
    assert payload["loopback_listener_count"] == 0
    assert payload["direct_processes_spawned"] == 0
    assert payload["successful_exit_codes"] == []
    assert payload["delivery_receipt_hash"] is None
    assert payload["playwright_cli_sha256"] is None
    assert payload["receipt_hash"].startswith("sha256:")


def test_native_viewer_server_dry_run_is_loopback_only_and_listener_free() -> None:
    result = subprocess.run(
        ["npm", "run", "serve:viewer", "--silent", "--", "--dry-run"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "structural-native-viewer-server-receipt.v1"
    assert payload["loopback_only"] is True
    assert payload["listener_count"] == 0
    assert payload["external_network_access_count"] == 0
    assert payload["commands_executed"] == 0
    assert payload["viewer_url"].startswith("http://127.0.0.1:8765/")
