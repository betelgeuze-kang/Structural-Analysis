from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _read_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_frontend_package_manifest_is_pinned_to_the_workbench_shell() -> None:
    package_json = _read_json("package.json")

    assert package_json["name"] == "structural-analysis"
    assert package_json["packageManager"] == "npm@11.19.0"
    assert package_json["engines"] == {"node": "24.20.0", "npm": "11.19.0"}
    assert (
        package_json["scripts"]["verify:frontend-contract"]
        == "node ./scripts/verify-frontend-build-contract.mjs"
    )
    assert (
        package_json["scripts"]["verify:frontend-smoke"]
        == "node ./scripts/verify-frontend-smoke.mjs"
    )
    assert (
        package_json["scripts"]["verify:viewer-manifest"]
        == "node ./scripts/verify-structure-viewer-project-manifest.mjs"
    )
    assert (
        package_json["scripts"]["verify:frontend-browser-smoke"]
        == "node ./scripts/verify-frontend-browser-smoke.mjs"
    )
    assert (
        package_json["scripts"]["verify:viewer-report-pdf"]
        == "node ./scripts/verify-structure-viewer-report-pdf.mjs"
    )
    assert (
        package_json["scripts"]["verify:viewer-performance-probe"]
        == "node ./scripts/measure-structure-viewer-performance.mjs --verify --fail-blocked"
    )
    assert (
        package_json["scripts"]["verify:viewer-visual-regression"]
        == "node ./scripts/measure-structure-viewer-visual-regression.mjs --verify --fail-blocked"
    )
    assert package_json["dependencies"] == {
        "ajv": "8.20.0",
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
    docs_text = (ROOT / "docs" / "frontend-build-reproducibility.md").read_text(
        encoding="utf-8"
    )

    assert package_lock["lockfileVersion"] == 3
    assert package_lock["requires"] is True
    assert package_lock["name"] == package_json["name"]
    assert package_lock["version"] == package_json["version"]
    assert package_lock["packages"][""]["name"] == package_json["name"]
    assert package_lock["packages"][""]["dependencies"] == package_json["dependencies"]
    assert (
        package_lock["packages"][""]["devDependencies"]
        == package_json["devDependencies"]
    )
    assert package_lock["packages"][""]["engines"] == package_json["engines"]
    assert "npm run verify:frontend-contract" in docs_text
    assert "npm run verify:frontend-smoke" in docs_text
    assert "npm run verify:frontend-browser-smoke" in docs_text
    assert "npm run verify:viewer-manifest" in docs_text
    assert "npm run verify:viewer-report-pdf" in docs_text
    assert "npm run verify:viewer-performance-probe" in docs_text
    assert "npm run verify:viewer-visual-regression" in docs_text
    assert "package-lock.json" in docs_text


def test_frontend_contract_helper_runs_without_installed_packages() -> None:
    result = subprocess.run(
        ["node", "scripts/verify-frontend-build-contract.mjs"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Frontend build contract OK" in result.stdout
    assert "npm run" not in result.stdout
    assert "hash-verified absolute Node 24.20.0" in result.stdout


def test_frontend_smoke_helper_advertises_deterministic_steps(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_node = fake_bin / "node"
    fake_node.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    fake_node.chmod(0o755)
    result = subprocess.run(
        [node, "scripts/verify-frontend-smoke.mjs", "--dry-run"],
        cwd=ROOT,
        env={"PATH": str(fake_bin)},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "npm-cli.js ci" in result.stdout
    assert "npm-cli.js audit --json --audit-level=info" in result.stdout
    assert "npm-cli.js audit signatures --json" in result.stdout
    assert "--ignore-scripts --engine-strict" in result.stdout
    assert "node_modules/typescript/bin/tsc --noEmit" in result.stdout
    assert "node_modules/vite/bin/vite.js build" in result.stdout
    assert "scripts/verify-workbench-viewer-delivery.mjs" in result.stdout
    assert "npm-cli.js run build" not in result.stdout


@pytest.mark.parametrize("attack", [".npmrc", "devEngines", "package-symlink"])
def test_frontend_smoke_preflight_rejects_dependency_surface_attacks(
    tmp_path: Path, attack: str
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy2(ROOT / "scripts/verify-frontend-smoke.mjs", scripts)
    shutil.copy2(ROOT / "scripts/trusted-frontend-runtime.mjs", scripts)
    manifest = {
        "name": "fixture",
        "version": "1.0.0",
        "packageManager": "npm@11.19.0",
        "engines": {"node": "24.20.0", "npm": "11.19.0"},
    }
    lock = {
        "name": "fixture",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {
            "": {
                "name": "fixture",
                "version": "1.0.0",
                "engines": manifest["engines"],
            }
        },
    }
    (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    if attack == ".npmrc":
        (tmp_path / "nested").mkdir()
        (tmp_path / "nested/.npmrc").write_text("registry=https://evil.invalid\n")
    elif attack == "devEngines":
        manifest["devEngines"] = {"runtime": {"name": "node"}}
        (tmp_path / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (tmp_path / "real-package.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (tmp_path / "package.json").unlink()
        (tmp_path / "package.json").symlink_to(tmp_path / "real-package.json")

    result = subprocess.run(
        ["node", "scripts/verify-frontend-smoke.mjs", "--dry-run"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_frontend_smoke_trusted_launcher_drops_hostile_node_options_and_path(
    tmp_path: Path,
) -> None:
    node = shutil.which("node")
    assert node is not None
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_node_marker = tmp_path / "fake-node-ran"
    fake_node = fake_bin / "node"
    fake_node.write_text(
        f"#!/bin/sh\ntouch {fake_node_marker}\nexit 0\n", encoding="utf-8"
    )
    fake_node.chmod(0o755)
    injected_marker = tmp_path / "node-options-ran"
    injection = tmp_path / "inject.cjs"
    injection.write_text(
        f"require('node:fs').writeFileSync({str(injected_marker)!r}, 'ran')\n",
        encoding="utf-8",
    )
    environment = {
        "NODE_OPTIONS": f"--require={injection}",
        "PATH": str(fake_bin),
    }

    result = subprocess.run(
        [
            "/usr/bin/env",
            "-i",
            "PATH=/usr/bin:/bin",
            f"HOME={tmp_path}",
            f"TMPDIR={tmp_path}",
            "LANG=C.UTF-8",
            "LC_ALL=C.UTF-8",
            node,
            "scripts/verify-frontend-smoke.mjs",
            "--dry-run",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not injected_marker.exists()
    assert not fake_node_marker.exists()


def test_browser_helpers_spawn_only_trusted_node_with_sanitized_environment() -> None:
    for relative in (
        "scripts/verify-frontend-browser-smoke.mjs",
        "scripts/verify-workbench-prototype-browser-smoke.mjs",
        "scripts/verify-workbench-v2-e2e.mjs",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "...process.env" not in text
        assert "NODE_OPTIONS" not in text
        assert "node_modules/.bin" not in text
        assert "spawn('npm'" not in text
        assert "spawn(\"npm\"" not in text
        assert "trustedNode()" in text
        assert "sanitizedFrontendEnvironment" in text

    workbench = (ROOT / "scripts/verify-workbench-v2-e2e.mjs").read_text(
        encoding="utf-8"
    )
    assert "node_modules/typescript/bin/tsc" in workbench
    assert "node_modules/vite/bin/vite.js" in workbench
    assert "node_modules/playwright/cli.js" in workbench
