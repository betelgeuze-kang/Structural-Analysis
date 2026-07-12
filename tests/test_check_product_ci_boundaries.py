from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "check_product_ci_boundaries.py"
)
SPEC = importlib.util.spec_from_file_location(
    "check_product_ci_boundaries",
    SCRIPT_PATH,
)
assert SPEC is not None
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _write_workflows(root: Path) -> None:
    for path, lane in module.REQUIRED_WORKFLOW_LANES.items():
        workflow = root / path
        workflow.parent.mkdir(parents=True, exist_ok=True)
        workflow.write_text(
            (
                f"name: {lane}\n"
                "jobs:\n"
                "  verify:\n"
                "    runs-on: ubuntu-latest\n"
                "    steps:\n"
                f"      - run: python scripts/run_product_ci_lane.py --lane {lane}\n"
            ),
            encoding="utf-8",
        )


def _write_manifest(root: Path, paths: list[str]) -> Path:
    manifest = root / module.DEFAULT_QUARANTINE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "path_count": len(paths),
                "paths": [
                    {
                        "path": path,
                        "excluded_from_structural_release_surface": True,
                    }
                    for path in paths
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_classification_assigns_exact_product_ownership() -> None:
    quarantined = {"scripts/materialize_gpcr_rows.py"}

    assert module.classify_path(
        "src/structural_analysis/api/core.py",
        quarantined_paths=quarantined,
    ) == "core"
    assert module.classify_path(
        "scripts/build_phase2_linear_reference_artifacts.py",
        quarantined_paths=quarantined,
    ) == "legacy_evidence"
    assert module.classify_path(
        "scripts/materialize_gpcr_rows.py",
        quarantined_paths=quarantined,
    ) == "molecular_quarantine"
    assert module.classify_path(
        "tests/test_pocketmd_contract.py",
        quarantined_paths=set(),
    ) == "molecular_quarantine"


def test_boundary_report_accepts_complete_three_lane_partition(
    tmp_path: Path,
) -> None:
    molecular = "scripts/materialize_gpcr_rows.py"
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [molecular])
    tracked = [
        "src/structural_analysis/api/core.py",
        "scripts/build_phase2_linear_reference_artifacts.py",
        molecular,
    ]

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=tracked,
    )

    assert payload["contract_pass"] is True
    assert payload["status"] == "ready"
    assert payload["lane_counts"] == {
        "core": 1,
        "legacy_evidence": 1,
        "molecular_quarantine": 1,
    }
    assert payload["blockers"] == []


def test_boundary_report_blocks_unmanifested_molecular_python(
    tmp_path: Path,
) -> None:
    _write_workflows(tmp_path)
    manifest = _write_manifest(tmp_path, [])

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["tests/test_gpcr_contract.py"],
    )

    assert payload["contract_pass"] is False
    assert payload["blockers"] == [
        "molecular_python_path_missing_from_quarantine_manifest:"
        "tests/test_gpcr_contract.py"
    ]


def test_boundary_report_blocks_missing_lane_workflow(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path, [])

    payload = module.build_report(
        repo_root=tmp_path,
        quarantine_manifest=manifest,
        tracked_python_paths=["src/structural_analysis/api/core.py"],
    )

    assert payload["contract_pass"] is False
    assert any(
        blocker == "workflow_missing:.github/workflows/ci.yml"
        for blocker in payload["blockers"]
    )
