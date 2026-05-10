from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/build_real_drawing_optimization_intake_queue.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_build_real_drawing_optimization_intake_queue_splits_ready_and_adapter_lanes(tmp_path: Path) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    parse_dir = tmp_path / "mgt_parse"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "tower_mgt",
                            "file_name": "tower.mgt",
                            "file_type": ".mgt",
                            "role": "midas_mgt_model",
                            "bytes": 123,
                            "sha256": "abc",
                            "source_url": "https://example.invalid/tower.mgt",
                            "model_optimization_candidate": True,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        },
                        {
                            "file_id": "building_ifc",
                            "file_name": "building.ifc",
                            "file_type": ".ifc",
                            "role": "bim_ifc_model",
                            "bytes": 456,
                            "sha256": "def",
                            "source_url": "https://example.invalid/building.ifc",
                            "model_optimization_candidate": True,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        },
                        {
                            "file_id": "archive_zip",
                            "file_name": "archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "bytes": 789,
                            "sha256": "ghi",
                            "source_url": "https://example.invalid/archive.zip",
                            "model_optimization_candidate": True,
                            "zip_model_member_count": 2,
                            "zip_member_count": 3,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        },
                    ],
                }
            ],
        },
    )
    _write_json(
        parse_dir / "tower.report.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "metrics": {
                "node_count": 12,
                "element_count": 9,
                "beam_element_count": 9,
                "shell_element_count": 0,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
            },
            "artifacts": {
                "json_out": str(parse_dir / "tower.json"),
                "npz_out": str(parse_dir / "tower.npz"),
            },
        },
    )
    (parse_dir / "tower.json").write_text("{}", encoding="utf-8")
    (parse_dir / "tower.npz").write_bytes(b"fixture")

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--mgt-parse-report-dir",
            str(parse_dir),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["candidate_file_count"] == 3
    assert payload["summary"]["candidate_model_asset_count"] == 4
    assert payload["summary"]["optimized_drawing_generation_ready_count"] == 1
    assert payload["summary"]["ready_node_count_total"] == 12
    assert payload["summary"]["mgt_hard_tier_ready_count"] == 1
    assert payload["summary"]["mgt_hard_tier_blocked_count"] == 0
    assert payload["summary"]["direct_mgt_solver_exact_count"] == 1
    assert payload["summary"]["solver_exact_ready_count"] == 1
    assert payload["summary"]["solver_graph_ready_count"] == 1
    assert payload["summary"]["ifc_adapter_required_count"] == 1
    assert payload["summary"]["archive_adapter_required_count"] == 1
    rows = {row["file_id"]: row for row in payload["queue"]}
    assert rows["tower_mgt"]["optimization_status"] == "solver_graph_ready"
    assert rows["tower_mgt"]["solver_exact"] is True
    assert rows["tower_mgt"]["mgt_hard_tier_ready"] is True
    assert rows["tower_mgt"]["mgt_hard_tier_reason_code"] == "PASS_MGT_DIRECT_SOLVER_GRAPH_EXACT"
    assert rows["tower_mgt"]["solver_graph_model_json"] == str(parse_dir / "tower.json")
    assert rows["tower_mgt"]["solver_graph_dataset_npz"] == str(parse_dir / "tower.npz")
    assert rows["tower_mgt"]["hard_evidence_tier"] == "direct_native_mgt_parser"
    assert rows["tower_mgt"]["hard_evidence_report"] == str(parse_dir / "tower.report.json")
    assert rows["tower_mgt"]["hard_evidence_artifacts"]["model_json"] == str(parse_dir / "tower.json")
    assert rows["tower_mgt"]["hard_evidence_artifacts"]["dataset_npz"] == str(parse_dir / "tower.npz")
    assert rows["tower_mgt"]["hard_evidence_checks"]["contract_pass"] is True
    assert rows["building_ifc"]["optimization_route"] == "ifc_to_structural_graph_adapter"
    assert rows["archive_zip"]["model_asset_count"] == 2


def test_build_real_drawing_optimization_intake_queue_promotes_archive_preview_bridge(tmp_path: Path) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    parse_dir = tmp_path / "mgt_parse"
    ifc_dir = tmp_path / "ifc_adapter"
    archive_report = tmp_path / "midas_archive_adapter_report.json"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "archive_zip",
                            "file_name": "archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "bytes": 789,
                            "sha256": "ghi",
                            "source_url": "https://example.invalid/archive.zip",
                            "model_optimization_candidate": True,
                            "zip_model_member_count": 2,
                            "zip_member_count": 3,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        archive_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "archives": [
                {
                    "file_id": "archive_zip",
                    "status": "decoded_preview_bridge_ready",
                    "bridge_report": "tmp/archive_zip/decoded_preview_bridge_report.json",
                    "model_json": "tmp/archive_zip/model.json",
                    "dataset_npz": "tmp/archive_zip/model.npz",
                    "viewer_ready": True,
                    "node_count": 8,
                    "element_count": 7,
                    "preview_exactness_tier": "raw-preview",
                    "preview_surface_bucket": "raw-preview",
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--mgt-parse-report-dir",
            str(parse_dir),
            "--ifc-adapter-report-dir",
            str(ifc_dir),
            "--midas-archive-adapter-report",
            str(archive_report),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["optimized_drawing_generation_ready_count"] == 1
    assert payload["summary"]["archive_decoded_preview_bridge_ready_count"] == 1
    assert payload["summary"]["archive_solver_graph_ready_count"] == 0
    assert payload["summary"]["archive_hard_tier_blocked_count"] == 1
    assert payload["summary"]["archive_adapter_required_count"] == 0
    assert payload["summary"]["proxy_or_preview_ready_count"] == 1
    row = payload["queue"][0]
    assert row["optimization_status"] == "archive_decoded_preview_bridge_ready"
    assert row["ready_for_optimized_drawing_generation"] is True
    assert row["solver_exact"] is False
    assert row["archive_hard_tier_ready"] is False
    assert row["archive_hard_tier_reason_code"] == "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT"
    assert "not solver-exact" in row["readiness_note"]


def test_build_real_drawing_optimization_intake_queue_blocks_mgt_hard_tier_without_artifacts(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    parse_dir = tmp_path / "mgt_parse"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "tower_mgt",
                            "file_name": "tower.mgt",
                            "file_type": ".mgt",
                            "role": "midas_mgt_model",
                            "bytes": 123,
                            "sha256": "abc",
                            "source_url": "https://example.invalid/tower.mgt",
                            "model_optimization_candidate": True,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        parse_dir / "tower.report.json",
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "metrics": {
                "node_count": 12,
                "element_count": 9,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
            },
            "artifacts": {
                "json_out": str(parse_dir / "missing.json"),
                "npz_out": str(parse_dir / "missing.npz"),
            },
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--mgt-parse-report-dir",
            str(parse_dir),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["optimized_drawing_generation_ready_count"] == 1
    assert payload["summary"]["direct_solver_graph_ready_count"] == 1
    assert payload["summary"]["mgt_hard_tier_ready_count"] == 0
    assert payload["summary"]["mgt_hard_tier_blocked_count"] == 1
    assert payload["summary"]["solver_graph_ready_count"] == 0
    row = payload["queue"][0]
    assert row["optimization_status"] == "solver_graph_ready"
    assert row["solver_exact"] is False
    assert row["mgt_hard_tier_reason_code"] == "ERR_MGT_SOLVER_ARTIFACTS_MISSING"


def test_build_real_drawing_optimization_intake_queue_promotes_archive_exact_topology_hard_tier(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    archive_report = tmp_path / "midas_archive_adapter_report.json"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "archive_zip",
                            "file_name": "archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "bytes": 789,
                            "sha256": "ghi",
                            "source_url": "https://example.invalid/archive.zip",
                            "model_optimization_candidate": True,
                            "zip_model_member_count": 1,
                            "zip_member_count": 1,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        archive_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "archives": [
                {
                    "file_id": "archive_zip",
                    "status": "decoded_preview_bridge_ready",
                    "bridge_report": "tmp/archive_zip/decoded_preview_bridge_report.json",
                    "model_json": "tmp/archive_zip/model.json",
                    "dataset_npz": "tmp/archive_zip/model.npz",
                    "viewer_ready": True,
                    "node_count": 4,
                    "element_count": 3,
                    "preview_exactness_tier": "exact-topology-promoted",
                    "preview_exactness_label": "exact topology promoted",
                    "preview_surface_bucket": "table-local-preview",
                    "topology_preview_ready": True,
                    "exact_topology_candidate": True,
                    "exact_topology_promoted": True,
                    "topology_node_count": 4,
                    "topology_edge_count": 3,
                    "missing_member_path_count": 0,
                    "missing_member_reference_count": 0,
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--midas-archive-adapter-report",
            str(archive_report),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["archive_decoded_preview_bridge_ready_count"] == 0
    assert payload["summary"]["archive_solver_graph_ready_count"] == 1
    assert payload["summary"]["archive_hard_tier_ready_count"] == 1
    assert payload["summary"]["archive_hard_tier_blocked_count"] == 0
    assert payload["summary"]["solver_graph_ready_count"] == 1
    assert payload["summary"]["proxy_or_preview_ready_count"] == 0
    row = payload["queue"][0]
    assert row["optimization_status"] == "archive_solver_graph_ready"
    assert row["optimization_route"] == "midas_binary_archive_exact_topology_promoted"
    assert row["ready_for_optimized_drawing_generation"] is True
    assert row["solver_exact"] is True
    assert row["archive_hard_tier_ready"] is True
    assert row["archive_hard_tier_reason_code"] == "PASS_ARCHIVE_EXACT_TOPOLOGY_PROMOTED"
    assert row["archive_solver_graph_model_json"] == "tmp/archive_zip/model.json"
    assert row["archive_solver_graph_dataset_npz"] == "tmp/archive_zip/model.npz"


def test_build_real_drawing_optimization_intake_queue_blocks_unpromoted_archive_exact_topology_candidate(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "redacted_manifest.json"
    archive_report = tmp_path / "midas_archive_adapter_report.json"
    out = tmp_path / "queue.json"
    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "projects": [
                {
                    "project_id": "project_a",
                    "project_title": "Project A",
                    "source_family": "fixture",
                    "files": [
                        {
                            "file_id": "archive_zip",
                            "file_name": "archive.zip",
                            "file_type": ".zip",
                            "role": "midas_model_archive",
                            "bytes": 789,
                            "sha256": "ghi",
                            "source_url": "https://example.invalid/archive.zip",
                            "model_optimization_candidate": True,
                            "zip_model_member_count": 1,
                            "zip_member_count": 1,
                            "raw_redistribution_allowed": False,
                            "release_surface_allowed": False,
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        archive_report,
        {
            "contract_pass": True,
            "reason_code": "PASS",
            "archives": [
                {
                    "file_id": "archive_zip",
                    "status": "decoded_preview_bridge_ready",
                    "bridge_report": "tmp/archive_zip/decoded_preview_bridge_report.json",
                    "model_json": "tmp/archive_zip/model.json",
                    "viewer_ready": True,
                    "node_count": 4,
                    "element_count": 3,
                    "preview_exactness_tier": "exact-topology-candidate",
                    "preview_surface_bucket": "table-local-preview",
                    "topology_preview_ready": True,
                    "exact_topology_candidate": True,
                    "exact_topology_promoted": False,
                    "topology_node_count": 6,
                    "topology_edge_count": 5,
                    "missing_member_path_count": 0,
                    "missing_member_reference_count": 0,
                }
            ],
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--midas-archive-adapter-report",
            str(archive_report),
            "--out",
            str(out),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["archive_solver_graph_ready_count"] == 0
    assert payload["summary"]["archive_hard_tier_blocked_reason_counts"] == {
        "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_GRAPH_PARITY_MISMATCH": 1
    }
    row = payload["queue"][0]
    assert row["optimization_status"] == "archive_decoded_preview_bridge_ready"
    assert row["solver_exact"] is False
    assert row["archive_hard_tier_ready"] is False
    assert row["archive_hard_tier_reason_code"] == "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_GRAPH_PARITY_MISMATCH"
    assert "preview graph counts do not match" in row["archive_hard_tier_note"]
