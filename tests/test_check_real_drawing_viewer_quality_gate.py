from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "implementation/phase1/check_real_drawing_viewer_quality_gate.py"
SPEC = importlib.util.spec_from_file_location("check_real_drawing_viewer_quality_gate", SCRIPT_PATH)
assert SPEC is not None
quality_gate = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(quality_gate)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _asset(
    asset_ref: str,
    *,
    solver_exact: bool,
    segment_count: int,
    geometry_available: bool = True,
    quality_flags: list[str] | None = None,
    route: str = "midas_mgt_direct_parser",
    status: str = "solver_graph_ready",
) -> dict[str, object]:
    return {
        "asset_ref": asset_ref,
        "file_type": ".mgt" if solver_exact else ".ifc",
        "geometry_available": geometry_available,
        "geometry_mode": "solver_topology_xyz" if solver_exact else "ifc_proxy_topology_3d_layout",
        "metrics": {
            "edge_count": 0 if solver_exact else segment_count,
            "element_count": segment_count if solver_exact else 0,
            "node_count": segment_count + 1,
            "renderable_segment_count": segment_count,
        },
        "model_asset_count": 1,
        "quality_flags": quality_flags or [],
        "route": route,
        "segment_count": segment_count,
        "solver_exact": solver_exact,
        "status": status,
        "warning_label": "",
    }


def _manifest(assets: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    solver_exact_count = sum(1 for asset in assets if bool(asset["solver_exact"]))
    payload: dict[str, object] = {
        "asset_count": len(assets),
        "assets": assets,
        "output_html": "",
        "output_viewer_sidecar": "src/structure-viewer/index.real_drawing_private.data.js",
        "proxy_or_preview_asset_count": len(assets) - solver_exact_count,
        "renderable_asset_count": sum(
            1
            for asset in assets
            if bool(asset["geometry_available"]) and int(asset["segment_count"]) > 0
        ),
        "route_counts": {"midas_mgt_direct_parser": solver_exact_count},
        "schema_version": "real-drawing-private-3d-webviewer.v1",
        "solver_exact_asset_count": solver_exact_count,
        "status_counts": {"solver_graph_ready": solver_exact_count},
        "structure_viewer_href": "src/structure-viewer/index.html?preset=real_drawing_private_3d",
        "structure_viewer_preset": "real_drawing_private_3d",
        "surface": "private_local_derived_geometry",
    }
    payload.update(overrides)
    return payload


def test_quality_gate_passes_with_review_queue_for_proxy_assets(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(
            [
                _asset("RD-001", solver_exact=True, segment_count=12),
                _asset(
                    "RD-002",
                    solver_exact=False,
                    segment_count=8,
                    quality_flags=["proxy_layout_not_true_geometry", "not_solver_exact", "sparse_preview"],
                    route="ifc_to_structural_graph_adapter",
                    status="ifc_proxy_graph_ready",
                ),
            ]
        ),
    )

    report = quality_gate.build_quality_gate(manifest_path)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS_WITH_REVIEW_QUEUE"
    assert report["commercial_viewer_ready"] is True
    assert report["full_solver_exact_ready"] is False
    assert report["summary"]["asset_count"] == 2
    assert report["summary"]["renderable_asset_count"] == 2
    assert report["summary"]["solver_exact_asset_count"] == 1
    assert report["summary"]["proxy_or_preview_asset_count"] == 1
    assert report["summary"]["review_queue_asset_count"] == 1
    assert report["summary"]["hard_blocker_count"] == 0
    assert report["quality_flag_counts"] == {
        "not_solver_exact": 1,
        "proxy_layout_not_true_geometry": 1,
        "sparse_preview": 1,
    }
    assert report["asset_quality_rows"][0]["quality_tier"] == "solver_exact_ready"
    assert report["asset_quality_rows"][1]["quality_tier"] == "sparse_preview_review"


def test_quality_gate_treats_solver_exact_sparse_archive_as_compact_ready(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(
            [
                _asset(
                    "RD-001",
                    solver_exact=True,
                    segment_count=3,
                    quality_flags=["sparse_preview"],
                    route="midas_binary_archive_exact_topology_promoted",
                    status="archive_solver_graph_ready",
                ),
            ],
            route_counts={"midas_binary_archive_exact_topology_promoted": 1},
            status_counts={"archive_solver_graph_ready": 1},
        ),
    )

    report = quality_gate.build_quality_gate(manifest_path)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["full_solver_exact_ready"] is True
    assert report["summary"]["review_queue_asset_count"] == 0
    assert report["review_queue"] == []
    assert report["asset_quality_rows"][0]["quality_tier"] == "solver_exact_ready"


def test_quality_gate_accepts_sampled_solver_exact_with_full_detail_lod_evidence(tmp_path: Path) -> None:
    asset = _asset(
        "RD-001",
        solver_exact=True,
        segment_count=3,
        quality_flags=["sampled_dense_model"],
    )
    asset["metrics"]["renderable_segment_count"] = 7
    asset["lod_evidence"] = {
        "contract_pass": True,
        "reason_code": "PASS_FULL_DETAIL_LOD_EVIDENCE_ATTACHED",
        "full_detail_segment_count": 7,
        "viewer_sample_segment_count": 3,
    }
    manifest_path = _write_json(tmp_path / "manifest.json", _manifest([asset]))

    report = quality_gate.build_quality_gate(manifest_path)

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["review_queue_asset_count"] == 0
    assert report["review_queue"] == []
    assert report["asset_quality_rows"][0]["quality_tier"] == "solver_exact_ready"
    assert report["asset_quality_rows"][0]["full_detail_lod_ready"] is True


def test_quality_gate_blocks_nonrenderable_and_sensitive_manifest(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(
            [
                _asset("RD-001", solver_exact=True, segment_count=20),
                _asset("RD-002", solver_exact=False, segment_count=0, geometry_available=False),
            ],
            source_url="https://example.invalid/private.ifc",
        ),
    )

    report = quality_gate.build_quality_gate(manifest_path)

    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_REAL_DRAWING_VIEWER_HARD_BLOCKERS"
    assert report["commercial_viewer_ready"] is False
    reason_codes = {row["reason_code"] for row in report["hard_blockers"]}
    assert "ERR_REAL_DRAWING_VIEWER_ASSET_NOT_RENDERABLE" in reason_codes
    assert "ERR_REAL_DRAWING_VIEWER_ZERO_SEGMENTS" in reason_codes
    assert "ERR_REAL_DRAWING_VIEWER_SENSITIVE_FIELD_PRESENT" in reason_codes
    assert report["summary"]["hard_blocker_count"] == 3
    assert report["asset_quality_rows"][1]["quality_tier"] == "hard_blocker"


def test_quality_gate_cli_writes_outputs_and_can_fail_on_blocker(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest([_asset("RD-001", solver_exact=False, segment_count=0, geometry_available=False)]),
    )
    out_path = tmp_path / "quality.json"
    out_md_path = tmp_path / "quality.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--viewer-manifest",
            str(manifest_path),
            "--out",
            str(out_path),
            "--out-md",
            str(out_md_path),
            "--json",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    stdout_report = json.loads(result.stdout)
    disk_report = json.loads(out_path.read_text(encoding="utf-8"))
    assert stdout_report["contract_pass"] is False
    assert disk_report["reason_code"] == "ERR_REAL_DRAWING_VIEWER_HARD_BLOCKERS"
    assert "Real Drawing Viewer Quality Gate" in out_md_path.read_text(encoding="utf-8")

    strict_result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--viewer-manifest",
            str(manifest_path),
            "--out",
            str(tmp_path / "strict.json"),
            "--out-md",
            str(tmp_path / "strict.md"),
            "--fail-on-hard-blocker",
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert strict_result.returncode == 2
