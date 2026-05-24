from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_json(relative_path: str) -> dict[str, object]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def test_frontend_package_manifest_is_pinned_to_the_workbench_shell() -> None:
    package_json = _read_json("package.json")

    assert package_json["name"] == "structural-optimization-workbench"
    assert package_json["packageManager"] == "npm@10.8.2"
    assert package_json["scripts"]["verify:frontend-contract"] == "node ./scripts/verify-frontend-build-contract.mjs"
    assert package_json["scripts"]["verify:frontend-smoke"] == "node ./scripts/verify-frontend-smoke.mjs"
    assert package_json["scripts"]["verify:viewer-manifest"] == "node ./scripts/verify-structure-viewer-project-manifest.mjs"
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
        "react": "18.2.0",
        "react-dom": "18.2.0",
    }
    assert package_json["devDependencies"] == {
        "@playwright/test": "1.56.1",
        "@types/react": "18.2.15",
        "@types/react-dom": "18.2.7",
        "@vitejs/plugin-react": "6.0.1",
        "typescript": "5.0.2",
        "vite": "8.0.8",
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


def test_frontend_smoke_helper_advertises_deterministic_steps() -> None:
    result = subprocess.run(
        ["node", "scripts/verify-frontend-smoke.mjs", "--dry-run"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "npm ci" in result.stdout
    assert "npm run build" in result.stdout
