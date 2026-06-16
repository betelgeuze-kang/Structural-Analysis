from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "build_ux_release_readiness_report.py"
SPEC = importlib.util.spec_from_file_location("build_ux_release_readiness_report", SCRIPT_PATH)
assert SPEC is not None
build_ux_release_readiness_report = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_ux_release_readiness_report)


def _write(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_ux_release_readiness_accepts_claim_scoped_review_queue(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 1},
            "review_queue": [
                {
                    "asset_ref": "RD-001",
                    "quality_tier": "ifc_geometry_ready_load_review",
                    "quality_flags": ["not_solver_exact"],
                    "claim_quality_flags": ["ifc_load_model_missing"],
                    "recommended_action": "attach IFC load-model evidence before analysis claim",
                }
            ],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke={"return_code": 0, "elapsed_seconds": 120},
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["claim_scoped_review_item_count"] == 1
    assert payload["summary"]["blocking_review_item_count"] == 0
    assert payload["summary"]["sample_completion_minutes"] == 2.0


def test_ux_release_readiness_blocks_unscoped_review_queue(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS_WITH_REVIEW_QUEUE",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 1},
            "review_queue": [
                {
                    "asset_ref": "RD-002",
                    "quality_tier": "proxy_preview_review",
                    "quality_flags": ["proxy_layout_not_true_geometry"],
                    "claim_quality_flags": [],
                    "recommended_action": "replace proxy or preview topology with solver-exact structural geometry",
                }
            ],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke={"return_code": 0, "elapsed_seconds": 120},
    )

    assert payload["contract_pass"] is False
    assert "claim_scoped_review_queue_pass" in payload["blockers"]
    assert payload["summary"]["blocking_review_item_count"] == 1


def test_ux_release_readiness_blocks_missing_browser_rehearsal(tmp_path: Path) -> None:
    viewer_quality = _write(
        tmp_path / "viewer_quality.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "commercial_viewer_ready": True,
            "summary": {"hard_blocker_count": 0, "review_item_count": 0},
            "review_queue": [],
        },
    )
    viewer_perf = _write(tmp_path / "viewer_perf.json", {"contract_pass": True, "reason_code": "PASS"})

    payload = build_ux_release_readiness_report.build_report(
        viewer_quality_path=viewer_quality,
        viewer_performance_path=viewer_perf,
        max_sample_minutes=30.0,
        browser_smoke=None,
    )

    assert payload["contract_pass"] is False
    assert "browser_sample_rehearsal_pass" in payload["blockers"]
    assert "sample_completion_30min_pass" in payload["blockers"]
