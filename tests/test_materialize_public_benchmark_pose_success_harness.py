from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "materialize_public_benchmark_pose_success_harness.py"
)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_pose_success_harness", SCRIPT_PATH
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _pose_packet(*, source_family: str = "CASF/PDBBind") -> dict[str, object]:
    return {
        "schema_version": "public-benchmark-pose-validity-packet.v1",
        "status": "ready",
        "contract_pass": True,
        "posebusters_validity_ready": True,
        "real_benchmark_case_count": 0 if source_family == "synthetic" else 1,
        "dry_run_case_count": 1 if source_family == "synthetic" else 0,
        "case_rows": [
            {
                "case_id": "case_a",
                "source_family": source_family,
                "benchmark_split": (
                    "synthetic-dry-run"
                    if source_family == "synthetic"
                    else "CASF-core"
                ),
                "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                "subset_manifest_case_checksum": "sha256:case-a",
                "status": "pass",
                "pass": True,
                "pose_success": True,
                "check_results": [
                    {
                        "check_id": "coordinate_finiteness",
                        "status": "pass",
                        "required": True,
                        "blockers": [],
                    }
                ],
                "blockers": [],
            }
        ],
        "blockers": [],
    }


def _rmsd_scorecard(
    *,
    source_family: str = "CASF/PDBBind",
    pose_success: bool = True,
) -> dict[str, object]:
    return {
        "schema_version": "public-benchmark-symmetry-rmsd-scorecard.v1",
        "status": "ready",
        "contract_pass": True,
        "scorecard_ready": True,
        "real_benchmark_case_count": 0 if source_family == "synthetic" else 1,
        "dry_run_case_count": 1 if source_family == "synthetic" else 0,
        "rows": [
            {
                "case_id": "case_a",
                "source_family": source_family,
                "benchmark_split": (
                    "synthetic-dry-run"
                    if source_family == "synthetic"
                    else "CASF-core"
                ),
                "subset_manifest_case_checksum": "sha256:case-a",
                "score": {
                    "best_rmsd_angstrom": 0.42 if pose_success else 2.5,
                    "threshold_angstrom": 2.0,
                    "best_permutation": [0, 1],
                    "pose_success": pose_success,
                },
            }
        ],
        "blockers": [],
    }


def test_pose_success_harness_materializer_builds_ready_real_case() -> None:
    harness = module.materialize_pose_success_harness(
        _pose_packet(),
        _rmsd_scorecard(),
        repo_root=REPO_ROOT,
    )

    assert harness["schema_version"] == "public-benchmark-pose-success-harness.v1"
    assert harness["status"] == "ready"
    assert harness["pose_success_harness_ready"] is True
    assert harness["real_benchmark_case_count"] == 1
    assert harness["dry_run_case_count"] == 0
    assert harness["pose_success_count"] == 1
    assert harness["pose_failure_count"] == 0
    assert harness["pose_success_rate"] == 1.0
    assert harness["blockers"] == []
    row = harness["case_rows"][0]
    assert row["case_id"] == "case_a"
    assert row["status"] == "pass"
    assert row["pose_validity_pass"] is True
    assert row["pose_success"] is True
    assert row["symmetry_aware_ligand_rmsd_angstrom"] == 0.42
    assert row["rmsd_threshold_angstrom"] == 2.0


def test_pose_success_harness_records_pose_failure_without_blocking() -> None:
    harness = module.materialize_pose_success_harness(
        _pose_packet(),
        _rmsd_scorecard(pose_success=False),
        repo_root=REPO_ROOT,
    )

    assert harness["pose_success_harness_ready"] is True
    assert harness["pose_success_count"] == 0
    assert harness["pose_failure_count"] == 1
    assert harness["case_rows"][0]["status"] == "pose_failed"
    assert harness["blockers"] == []


def test_pose_success_harness_blocks_missing_rmsd_case_row() -> None:
    scorecard = _rmsd_scorecard()
    scorecard["rows"] = []

    harness = module.materialize_pose_success_harness(
        _pose_packet(),
        scorecard,
        repo_root=REPO_ROOT,
    )

    assert harness["pose_success_harness_ready"] is False
    assert harness["status"] == "pose_success_harness_materialization_required"
    assert "symmetry_rmsd_scorecard_rows_missing" in harness["blockers"]
    assert "case_a:symmetry_rmsd_row_missing" in harness["blockers"]
    assert harness["case_rows"][0]["status"] == "blocked"


def test_pose_success_harness_blocks_dry_run_only_input() -> None:
    harness = module.materialize_pose_success_harness(
        _pose_packet(source_family="synthetic"),
        _rmsd_scorecard(source_family="synthetic"),
        repo_root=REPO_ROOT,
    )

    assert harness["pose_success_harness_ready"] is False
    assert harness["real_benchmark_case_count"] == 0
    assert harness["dry_run_case_count"] == 1
    assert harness["blockers"] == ["real_benchmark_pose_success_cases_missing"]


def test_pose_success_harness_cli_writes_harness_and_report(tmp_path: Path) -> None:
    pose_packet = tmp_path / "pose_packet.json"
    rmsd_scorecard = tmp_path / "rmsd_scorecard.json"
    out_harness = tmp_path / "pose_success_harness.json"
    out_report = tmp_path / "pose_success_harness_report.json"
    pose_packet.write_text(json.dumps(_pose_packet()), encoding="utf-8")
    rmsd_scorecard.write_text(json.dumps(_rmsd_scorecard()), encoding="utf-8")

    assert (
        module.main(
            [
                "--pose-validity-packet",
                str(pose_packet),
                "--rmsd-scorecard",
                str(rmsd_scorecard),
                "--out-harness",
                str(out_harness),
                "--out-report",
                str(out_report),
                "--repo-root",
                str(REPO_ROOT),
                "--fail-blocked",
            ]
        )
        == 0
    )

    harness = json.loads(out_harness.read_text(encoding="utf-8"))
    report = json.loads(out_report.read_text(encoding="utf-8"))
    assert harness["pose_success_harness_ready"] is True
    assert report["pose_success_harness_ready"] is True
