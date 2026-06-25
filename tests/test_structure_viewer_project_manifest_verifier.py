from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_structure_viewer_project_manifest_verifier_reports_registered_release_triples() -> None:
    result = subprocess.run(
        ["node", "scripts/verify-structure-viewer-project-manifest.mjs", "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["contract_pass"] is True
    assert payload["summary"]["projectCount"] >= 3
    assert payload["summary"]["drawingCount"] >= 11
    assert payload["summary"]["variantCount"] >= 32
    assert payload["releaseTripleCount"] >= 8
    assert payload["missingPathCount"] == 0
    assert payload["artifactCountCheckCount"] >= 9
    assert payload["artifactCountMismatchCount"] == 0
    assert {
        "baselineManifest": 11334,
        "optimizedManifest": 2242,
        "baselineArtifact": 11334,
        "optimizedArtifact": 2242,
    }.items() <= next(
        check
        for check in payload["artifactCountChecks"]
        if check["label"] == "midas33_release/midas33_optimized"
    ).items()
    assert {
        "baselineManifest": 800,
        "optimizedManifest": 96,
        "baselineArtifact": 800,
        "optimizedArtifact": 96,
    }.items() <= next(
        check
        for check in payload["artifactCountChecks"]
        if check["label"] == "release_visualization/opstool_606m_megatall_model_00020"
    ).items()
    assert payload["errors"] == []


def test_structure_viewer_project_manifest_verifier_is_wired_to_package_script_and_quality_gate() -> None:
    package_json = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    gate = (ROOT / "scripts" / "verify_quality_gate.py").read_text(encoding="utf-8")
    contract = (ROOT / "scripts" / "verify-frontend-build-contract.mjs").read_text(encoding="utf-8")

    assert (
        package_json["scripts"]["verify:viewer-manifest"]
        == "node ./scripts/verify-structure-viewer-project-manifest.mjs"
    )
    assert "verify:viewer-manifest" in gate
    assert gate.index("verify:viewer-manifest") < gate.index("scripts/verify_structure_viewer_contracts.py")
    assert "scripts/verify-structure-viewer-project-manifest.mjs" in contract


def test_structure_viewer_project_manifest_verifier_tolerates_absent_generated_release_artifacts() -> None:
    """Generated release artifacts under implementation/phase1/release/ are gitignored
    and absent on clean checkouts (CI). The verifier must still pass on structure while
    surfacing their absence as warnings rather than hard errors."""
    entries = ROOT / "implementation/phase1/release/visualization/entries"
    relocated = ROOT / "implementation/phase1/release/visualization/.entries_relocated_for_test"

    moved = False
    if entries.exists():
        entries.rename(relocated)
        moved = True
    try:
        result = subprocess.run(
            ["node", "scripts/verify-structure-viewer-project-manifest.mjs", "--json"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        # Structure checks stay strict even when generated artifacts are absent.
        assert payload["contract_pass"] is True
        assert payload["errors"] == []
        assert payload["summary"]["projectCount"] >= 3
        assert payload["releaseTripleCount"] >= 8
        if moved:
            # The relocated generated artifacts should be reported as warnings, not errors.
            assert any("generated release artifact" in str(item) for item in payload["warnings"])
            assert payload["missingPathCount"] > 0
    finally:
        if moved:
            relocated.rename(entries)
