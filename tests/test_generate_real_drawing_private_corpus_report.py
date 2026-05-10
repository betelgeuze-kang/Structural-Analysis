from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "implementation/phase1/generate_real_drawing_private_corpus_report.py"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _fixture_queue_rows() -> list[dict]:
    rows: list[dict] = []
    ready_nodes = [3000, 3000, 3000, 2887]
    ready_elements = [3300, 3300, 3300, 3359]
    for idx in range(4):
        rows.append(
            {
                "file_id": f"tower_mgt_{idx + 1}",
                "file_name": f"tower_{idx + 1}.mgt",
                "file_type": ".mgt",
                "optimization_status": "solver_graph_ready",
                "optimization_route": "midas_mgt_direct_parser",
                "ready_for_optimized_drawing_generation": True,
                "solver_exact": True,
                "mgt_hard_tier_ready": True,
                "model_asset_count": 1,
                "node_count": ready_nodes[idx],
                "element_count": ready_elements[idx],
            }
        )

    for idx in range(7):
        rows.append(
            {
                "file_id": f"building_ifc_{idx + 1}",
                "file_name": f"building_{idx + 1}.ifc",
                "file_type": ".ifc",
                "optimization_status": "ifc_proxy_graph_ready",
                "optimization_route": "ifc_to_structural_graph_adapter",
                "ready_for_optimized_drawing_generation": True,
                "model_asset_count": 1,
                "proxy_node_count": 100,
                "proxy_edge_count": 90,
                "solver_exact": False,
            }
        )

    zip_asset_counts = [2, 2, 2, 1, 1, 1, 1]
    for idx, model_asset_count in enumerate(zip_asset_counts, start=1):
        rows.append(
            {
                "file_id": f"archive_zip_{idx}",
                "file_name": f"archive_{idx}.zip",
                "file_type": ".zip",
                "optimization_status": "archive_decoded_preview_bridge_ready",
                "optimization_route": "midas_binary_decoded_preview_bridge",
                "ready_for_optimized_drawing_generation": True,
                "model_asset_count": model_asset_count,
                "node_count": 10,
                "element_count": 9,
                "solver_exact": False,
                "zip_member_count": model_asset_count + 1,
                "zip_model_member_count": model_asset_count,
            }
        )

    return rows


def _write_report_fixture(
    tmp_path: Path,
    *,
    manifest_generated_at: str = "2026-05-06T00:00:00Z",
    queue_generated_at: str = "2026-05-06T00:00:00Z",
) -> tuple[Path, Path, Path, Path]:
    manifest = tmp_path / "redacted_manifest.json"
    queue = tmp_path / "model_optimization_intake_queue.json"
    out_json = tmp_path / "real_drawing_private_corpus_report.json"
    out_md = tmp_path / "real_drawing_private_corpus_report.md"

    _write_json(
        manifest,
        {
            "schema_version": "real-drawing-redacted-corpus-manifest.v1",
            "generated_at": manifest_generated_at,
            "contract_pass": True,
            "reason_code": "PASS",
            "policy": {
                "raw_redistribution_allowed": False,
                "release_surface_allowed": False,
                "storage_boundary": "private_corpus_only",
                "license_basis": "fixture private only",
            },
            "summary": {
                "project_count": 5,
                "file_count": 22,
                "downloaded_count": 22,
                "reused_private_file_count": 22,
                "blocked_count": 0,
                "total_bytes": 117800074,
                "drawing_review_candidate_count": 13,
                "downloaded_drawing_review_candidate_count": 13,
                "drawing_sheet_candidate_count": 78,
                "model_optimization_candidate_count": 18,
                "downloaded_model_optimization_candidate_count": 18,
                "model_optimization_asset_count": 21,
                "file_type_counts": {".ifc": 7, ".mgt": 4, ".pdf": 2, ".xlsx": 2, ".zip": 7},
                "downloaded_file_type_counts": {".ifc": 7, ".mgt": 4, ".pdf": 2, ".xlsx": 2, ".zip": 7},
                "model_optimization_candidate_file_type_counts": {".ifc": 7, ".mgt": 4, ".zip": 7},
                "raw_redistribution_allowed_count": 0,
                "release_surface_allowed_count": 0,
                "private_only": True,
            },
            "projects": [
                {
                    "project_id": "fixture_project",
                    "project_title": "Fixture project",
                    "files": [
                        {
                            "file_id": "fixture_file",
                            "file_name": "fixture.pdf",
                            "file_type": ".pdf",
                            "private_path": "/private/corpus/fixture.pdf",
                        }
                    ],
                }
            ],
        },
    )
    _write_json(
        queue,
        {
            "schema_version": "real-drawing-model-optimization-intake-queue.v1",
            "generated_at": queue_generated_at,
            "contract_pass": True,
            "reason_code": "PASS",
            "summary": {
                "candidate_file_count": 18,
                "candidate_model_asset_count": 21,
                "optimized_drawing_generation_ready_count": 18,
                "optimized_drawing_generation_ready_model_asset_count": 21,
                "direct_solver_graph_ready_count": 4,
                "direct_mgt_solver_exact_count": 4,
                "solver_exact_ready_count": 4,
                "mgt_hard_tier_ready_count": 4,
                "mgt_hard_tier_blocked_count": 0,
                "mgt_hard_tier_blocked_reason_counts": {},
                "solver_graph_ready_count": 4,
                "ifc_proxy_graph_ready_count": 7,
                "archive_decoded_preview_bridge_ready_count": 7,
                "archive_hard_tier_ready_count": 0,
                "archive_hard_tier_blocked_count": 7,
                "archive_exact_topology_candidate_count": 3,
                "archive_verified_geometry_preview_count": 1,
                "archive_hard_tier_blocked_reason_counts": {
                    "ERR_ARCHIVE_EXACT_TOPOLOGY_CANDIDATE_NOT_PROMOTED": 3,
                    "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT": 3,
                    "ERR_ARCHIVE_VERIFIED_GEOMETRY_NOT_SOLVER_TOPOLOGY": 1,
                },
                "proxy_or_preview_ready_count": 14,
                "ifc_adapter_required_count": 0,
                "archive_adapter_required_count": 0,
                "mgt_parser_pending_count": 0,
                "mgt_parser_failed_count": 0,
                "ready_node_count_total": 11957,
                "ready_element_count_total": 13322,
                "ready_ifc_proxy_node_count_total": 700,
                "ready_ifc_proxy_edge_count_total": 630,
                "status_counts": {
                    "archive_decoded_preview_bridge_ready": 7,
                    "ifc_proxy_graph_ready": 7,
                    "solver_graph_ready": 4,
                },
                "route_counts": {
                    "ifc_to_structural_graph_adapter": 7,
                    "midas_binary_decoded_preview_bridge": 7,
                    "midas_mgt_direct_parser": 4,
                },
            },
            "queue": _fixture_queue_rows(),
        },
    )
    return manifest, queue, out_json, out_md


def test_generate_real_drawing_private_corpus_report_emits_release_safe_summary(tmp_path: Path) -> None:
    manifest, queue, out_json, out_md = _write_report_fixture(tmp_path)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--intake-queue",
            str(queue),
            "--out",
            str(out_json),
            "--out-md",
            str(out_md),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["release_surface_allowed_count"] == 0
    assert payload["summary"]["direct_mgt_ready_count"] == 4
    assert payload["summary"]["direct_mgt_solver_exact_count"] == 4
    assert payload["summary"]["solver_exact_ready_count"] == 4
    assert payload["summary"]["mgt_hard_tier_ready_count"] == 4
    assert payload["summary"]["mgt_hard_tier_blocked_count"] == 0
    assert payload["summary"]["hard_solver_graph_ready_count"] == 4
    assert payload["summary"]["ifc_proxy_graph_ready_count"] == 7
    assert payload["summary"]["archive_decoded_preview_bridge_ready_count"] == 7
    assert payload["summary"]["archive_hard_tier_ready_count"] == 0
    assert payload["summary"]["archive_hard_tier_blocked_count"] == 7
    assert payload["summary"]["archive_exact_topology_candidate_count"] == 3
    assert payload["summary"]["archive_verified_geometry_preview_count"] == 1
    assert payload["summary"]["proxy_or_preview_ready_count"] == 14
    assert payload["summary"]["ifc_adapter_required_count"] == 0
    assert payload["summary"]["archive_adapter_required_count"] == 0
    assert payload["summary"]["model_asset_count"] == 21
    assert payload["summary"]["drawing_sheet_candidate_count"] == 78
    assert payload["summary"]["real_data_route_ready_count"] == 18
    assert payload["summary"]["ready_model_asset_count"] == 21
    assert payload["summary"]["eb_rh_external_validation_status"] == "pending"
    assert payload["summary"]["l3_claim_state"] == "maintained"
    assert payload["summary"]["tier_count"] == 3
    assert payload["summary"]["tier_acceptance_pass_count"] == 3
    assert payload["summary"]["tier_acceptance_all_pass"] is True
    assert payload["summary"]["readiness_state"] == "blocked"
    assert payload["summary"]["readiness_lane_count"] == 7
    assert payload["summary"]["readiness_lane_state_counts"] == {
        "all-pass": 4,
        "blocked": 2,
        "pending": 1,
    }
    assert payload["summary"]["evidence_checklist_state_counts"] == {
        "all-pass": 7,
        "blocked": 2,
        "pending": 1,
    }
    assert payload["summary"]["readiness_summary_line"] == (
        "Real drawing private corpus readiness: blocked | lanes=all-pass=4, blocked=2, pending=1 | "
        "checklist=all-pass=7, blocked=2, pending=1"
    )
    assert payload["summary"]["input_artifact_freshness_status"] == "all-pass"
    assert payload["summary"]["input_artifact_freshness_skew_seconds"] == 0
    assert payload["summary"]["stale_artifact_detected"] is False
    assert payload["summary"]["evidence_checklist_count"] == 10
    assert payload["summary"]["evidence_checklist_pass_count"] == 7
    assert payload["summary"]["evidence_checklist_pending_count"] == 1
    assert payload["summary"]["evidence_checklist_blocked_count"] == 2
    assert payload["summary"]["remaining_blockers"] == [
        "ifc_geometry_material_load_solver_exact_adapter_required",
        "archive_native_solver_topology_promotion_required",
        "eb_rh_external_validation_hold",
    ]
    assert payload["summary"]["remaining_blocker_count"] == 3
    assert payload["summary"]["blocker_register_count"] == 3
    assert payload["summary"]["remaining_blocker_details"] == [
        {
            "blocker": "ifc_geometry_material_load_solver_exact_adapter_required",
            "exactness_policy": "solver_exact",
            "next_action": "promote IFC proxy rows to solver-exact adapter output",
            "owner": "ifc_adapter_owner",
            "source_check_id": "ifc_solver_exact_hard_tier",
            "source_check_label": "IFC solver exact hard tier",
            "state": "blocked",
        },
        {
            "blocker": "archive_native_solver_topology_promotion_required",
            "exactness_policy": "solver_exact",
            "next_action": "promote archive preview bridges to exact topology",
            "owner": "archive_adapter_owner",
            "source_check_id": "archive_native_solver_exact_hard_tier",
            "source_check_label": "Archive native solver exact hard tier",
            "state": "blocked",
        },
        {
            "blocker": "eb_rh_external_validation_hold",
            "exactness_policy": "external_validation_hold",
            "next_action": "wait for EB/RH external validation to clear the hold",
            "owner": "eb_rh_validation_owner",
            "source_check_id": "eb_rh_external_validation_hold",
            "source_check_label": "EB/RH external validation hold",
            "state": "pending",
        },
    ]
    readiness_lanes = payload["summary"]["readiness_lanes"]
    assert [row["lane_id"] for row in readiness_lanes] == [
        "direct_mgt",
        "ifc_proxy_graph",
        "archive_preview_bridge",
        "mgt_direct_solver_exact_hard_tier",
        "ifc_solver_exact_hard_tier",
        "archive_native_solver_exact_hard_tier",
        "eb_rh_external_validation",
    ]
    assert readiness_lanes[0]["exactness_policy"] == "solver_exact"
    assert readiness_lanes[1]["exactness_policy"] == "proxy_graph"
    assert readiness_lanes[2]["exactness_policy"] == "decoded_preview"
    assert readiness_lanes[3]["readiness_state"] == "all-pass"
    assert readiness_lanes[4]["readiness_state"] == "blocked"
    assert readiness_lanes[-1]["readiness_state"] == "pending"
    blocker_register = payload["summary"]["blocker_register"]
    assert [row["blocker_id"] for row in blocker_register] == payload["summary"]["remaining_blockers"]
    assert blocker_register[0]["owner"] == "hard_implementation"
    assert "solver_exact=true" in blocker_register[0]["acceptance"]
    assert blocker_register[-1]["status"] == "pending_user_skipped"
    tier_acceptance = payload["summary"]["tier_acceptance"]
    assert [item["tier_id"] for item in tier_acceptance] == [
        "direct_mgt",
        "ifc_proxy_graph",
        "archive_preview_bridge",
    ]
    assert [item["status"] for item in tier_acceptance] == ["pass", "pass", "pass"]
    assert [item["accepted"] for item in tier_acceptance] == [True, True, True]
    assert [item["remaining_blockers"] for item in tier_acceptance] == [[], [], []]
    assert tier_acceptance[0]["exactness_policy"] == "solver_exact"
    assert tier_acceptance[1]["owner"] == "ifc_adapter_owner"
    assert tier_acceptance[2]["next_action"] == "keep archive preview bridge intake-ready; exact topology promotion remains separate"
    assert tier_acceptance[0]["signals"]["ready_count"] == 4
    assert tier_acceptance[1]["signals"]["route_name"] == "ifc_to_structural_graph_adapter"
    assert tier_acceptance[2]["signals"]["status_label"] == "archive_decoded_preview_bridge_ready"
    checklist = payload["summary"]["evidence_checklist"]
    assert [item["check_id"] for item in checklist] == [
        "report_contract",
        "input_artifact_freshness",
        "release_surface_redaction",
        "direct_mgt_acceptance",
        "ifc_proxy_graph_acceptance",
        "archive_preview_bridge_acceptance",
        "mgt_direct_solver_exact_hard_tier",
        "ifc_solver_exact_hard_tier",
        "archive_native_solver_exact_hard_tier",
        "eb_rh_external_validation_hold",
    ]
    assert checklist[0]["accepted"] is True
    assert checklist[1]["check_id"] == "input_artifact_freshness"
    assert checklist[1]["status"] == "pass"
    assert checklist[1]["readiness_state"] == "all-pass"
    assert checklist[1]["owner"] == "report_publisher"
    assert checklist[2]["signals"]["release_surface_allowed_count"] == 0
    assert checklist[6]["status"] == "pass"
    assert checklist[6]["readiness_state"] == "all-pass"
    assert checklist[6]["signals"]["mgt_hard_tier_ready_count"] == 4
    assert checklist[7]["status"] == "blocked"
    assert checklist[7]["owner"] == "ifc_adapter_owner"
    assert checklist[7]["next_action"] == "promote IFC proxy rows to solver-exact adapter output"
    assert checklist[8]["signals"]["archive_hard_tier_blocked_count"] == 7
    assert checklist[8]["status"] == "blocked"
    assert checklist[8]["remaining_blockers"] == ["archive_native_solver_topology_promotion_required"]
    assert checklist[9]["status"] == "pending"
    assert checklist[9]["owner"] == "eb_rh_validation_owner"
    assert checklist[9]["remaining_blockers"] == ["eb_rh_external_validation_hold"]
    assert payload["queue_breakdown"]["direct_mgt_ready_count"] == 4
    assert payload["queue_breakdown"]["mgt_hard_tier_ready_count"] == 4
    assert payload["queue_breakdown"]["mgt_hard_tier_blocked_count"] == 0
    assert payload["queue_breakdown"]["hard_solver_graph_ready_count"] == 4
    assert payload["queue_breakdown"]["ifc_proxy_graph_ready_count"] == 7
    assert payload["queue_breakdown"]["archive_decoded_preview_bridge_ready_count"] == 7
    assert payload["queue_breakdown"]["archive_hard_tier_ready_count"] == 0
    assert payload["queue_breakdown"]["archive_hard_tier_blocked_count"] == 7
    assert payload["queue_breakdown"]["proxy_or_preview_ready_count"] == 14
    assert payload["queue_breakdown"]["ifc_adapter_required_count"] == 0
    assert payload["queue_breakdown"]["archive_adapter_required_count"] == 0
    assert payload["queue_breakdown"]["model_asset_count"] == 21
    assert payload["queue_breakdown"]["drawing_sheet_candidate_count"] == 78
    assert payload["consistency"]["manifest_contract_pass"] is True
    assert payload["consistency"]["queue_contract_pass"] is True
    assert payload["consistency"]["counts_consistent"] is True
    assert payload["consistency"]["ready_count_match"] is True
    assert payload["consistency"]["input_artifact_freshness_pass"] is True
    assert payload["consistency"]["stale_artifact_detected"] is False

    assert "private raw 금지" in markdown
    assert "readiness_state" in markdown
    assert "readiness_summary_line" in markdown
    assert "Readiness Lanes" in markdown
    assert "| Lane | Readiness | Policy | Owner | Next action | Blockers |" in markdown
    assert "release_surface_allowed=0" in markdown
    assert "EB/RH 외부 검증 보류" in markdown
    assert "L3 claim 유지" in markdown
    assert "real-data route ready count" in markdown
    assert "Tier Acceptance" in markdown
    assert "Evidence Checklist" in markdown
    assert "Remaining Blockers" in markdown
    assert "Blocker Register" in markdown
    assert "pending_user_skipped" in markdown
    assert "| Check | Readiness | Status | Policy | Owner | Next action | Signals | Blockers |" in markdown
    assert "| Blocker | State | Owner | Next action |" in markdown
    assert "eb_rh_external_validation_hold" in markdown
    assert "pending" in markdown
    assert "ifc_geometry_material_load_solver_exact_adapter_required" in markdown
    assert "archive_native_solver_topology_promotion_required" in markdown
    assert "archive_native_solver_exact_hard_tier" in markdown
    assert "Archive hard tier blocked" in markdown
    assert "hard solver graph ready" in markdown
    assert "mgt_direct_solver_exact_hard_tier" in markdown
    assert "MGT hard tier ready" in markdown
    assert "Direct MGT ready" in markdown
    assert "IFC proxy graph ready" in markdown
    assert "Archive preview bridge ready" in markdown
    assert "IFC adapter required" in markdown
    assert "Archive adapter required" in markdown
    assert "Drawing sheets" in markdown
    assert "stale_artifact_detected" in markdown
    assert "private_path" not in markdown
    assert "source_private_manifest" not in markdown
    assert "private_path" not in json.dumps(payload, ensure_ascii=False)
    assert "source_private_manifest" not in json.dumps(payload, ensure_ascii=False)


def test_generate_real_drawing_private_corpus_report_flags_stale_inputs(tmp_path: Path) -> None:
    manifest, queue, out_json, out_md = _write_report_fixture(
        tmp_path,
        manifest_generated_at="2026-05-06T00:00:00Z",
        queue_generated_at="2026-05-06T01:00:00Z",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--intake-queue",
            str(queue),
            "--out",
            str(out_json),
            "--out-md",
            str(out_md),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")

    assert payload["summary"]["readiness_state"] == "blocked"
    assert payload["summary"]["input_artifact_freshness_status"] == "blocked"
    assert payload["summary"]["input_artifact_freshness_skew_seconds"] == 3600
    assert payload["summary"]["stale_artifact_detected"] is True
    assert payload["summary"]["evidence_checklist_state_counts"] == {
        "all-pass": 6,
        "blocked": 3,
        "pending": 1,
    }
    assert payload["summary"]["remaining_blockers"][0] == "stale_artifact_generation_wave_mismatch"
    assert payload["summary"]["remaining_blocker_details"][0] == {
        "blocker": "stale_artifact_generation_wave_mismatch",
        "exactness_policy": "freshness_guard",
        "next_action": "regenerate manifest and queue from the same generation wave before publishing",
        "owner": "report_publisher",
        "source_check_id": "input_artifact_freshness",
        "source_check_label": "Input artifact freshness",
        "state": "blocked",
    }
    assert payload["summary"]["evidence_checklist"][1]["status"] == "blocked"
    assert payload["summary"]["evidence_checklist"][1]["readiness_state"] == "blocked"
    assert payload["summary"]["evidence_checklist"][1]["remaining_blockers"] == [
        "stale_artifact_generation_wave_mismatch"
    ]
    assert "stale_artifact_detected" in markdown
    assert "stale_artifact_generation_wave_mismatch" in markdown


def test_generate_real_drawing_private_corpus_report_closes_promoted_archive_candidates(
    tmp_path: Path,
) -> None:
    manifest, queue, out_json, out_md = _write_report_fixture(tmp_path)
    queue_payload = json.loads(queue.read_text(encoding="utf-8"))
    queue_payload["summary"].update(
        {
            "solver_exact_ready_count": 7,
            "solver_graph_ready_count": 7,
            "archive_decoded_preview_bridge_ready_count": 4,
            "archive_solver_graph_ready_count": 3,
            "archive_solver_exact_count": 3,
            "archive_hard_tier_ready_count": 3,
            "archive_hard_tier_blocked_count": 4,
            "archive_hard_tier_blocked_reason_counts": {
                "ERR_ARCHIVE_PREVIEW_NOT_SOLVER_EXACT": 3,
                "ERR_ARCHIVE_VERIFIED_GEOMETRY_NOT_SOLVER_TOPOLOGY": 1,
            },
            "proxy_or_preview_ready_count": 11,
            "status_counts": {
                "archive_decoded_preview_bridge_ready": 4,
                "archive_solver_graph_ready": 3,
                "ifc_proxy_graph_ready": 7,
                "solver_graph_ready": 4,
            },
            "route_counts": {
                "ifc_to_structural_graph_adapter": 7,
                "midas_binary_archive_exact_topology_promoted": 3,
                "midas_binary_decoded_preview_bridge": 4,
                "midas_mgt_direct_parser": 4,
            },
        }
    )
    promoted = 0
    for row in queue_payload["queue"]:
        if row.get("file_type") != ".zip" or promoted >= 3:
            continue
        promoted += 1
        row.update(
            {
                "optimization_status": "archive_solver_graph_ready",
                "optimization_route": "midas_binary_archive_exact_topology_promoted",
                "solver_exact": True,
                "archive_hard_tier_ready": True,
                "archive_hard_tier_reason_code": "PASS_ARCHIVE_EXACT_TOPOLOGY_PROMOTED",
                "exact_topology_candidate": True,
                "exact_topology_promoted": True,
            }
        )
    _write_json(queue, queue_payload)

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--redacted-manifest",
            str(manifest),
            "--intake-queue",
            str(queue),
            "--out",
            str(out_json),
            "--out-md",
            str(out_md),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    checklist = payload["summary"]["evidence_checklist"]
    archive_check = next(
        item for item in checklist if item["check_id"] == "archive_native_solver_exact_hard_tier"
    )
    assert archive_check["status"] == "pass"
    assert archive_check["readiness_state"] == "all-pass"
    assert archive_check["signals"]["exact_candidate_promotion_complete"] is True
    assert archive_check["signals"]["exact_candidate_blocked_reason_counts"] == {}
    assert payload["summary"]["solver_exact_ready_count"] == 7
    assert payload["summary"]["hard_solver_graph_ready_count"] == 7
    assert payload["summary"]["remaining_blockers"] == [
        "ifc_geometry_material_load_solver_exact_adapter_required",
        "eb_rh_external_validation_hold",
    ]
    assert [row["blocker_id"] for row in payload["summary"]["blocker_register"]] == [
        "ifc_geometry_material_load_solver_exact_adapter_required",
        "eb_rh_external_validation_hold",
    ]
