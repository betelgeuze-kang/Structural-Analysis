from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from implementation.phase1.project_ops_api_service import (
    build_project_ops_snapshot,
    create_project_ops_test_token,
    create_project_ops_server,
    write_project_ops_snapshot,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _headers(*, role: str = "viewer", tenant_id: str = "tenant-a", actor_id: str = "engineer-1") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_project_ops_test_token(tenant_id=tenant_id, actor_id=actor_id, roles=[role])}",
        "X-Tenant-ID": tenant_id,
        "X-Actor-ID": actor_id,
        "X-Request-ID": f"req-{role}-{tenant_id}",
    }


def _get_json(url: str, *, role: str = "viewer", tenant_id: str = "tenant-a") -> dict:
    request = Request(url, headers=_headers(role=role, tenant_id=tenant_id))
    with urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def _prepare_release_root(tmp_path: Path) -> Path:
    release_root = tmp_path / "release"
    portfolio_root = release_root / "authoring" / "portfolio"
    family_root = portfolio_root / "steel_braced_frame"
    committee_root = release_root / "committee_review"
    snapshot_root = release_root / "phase3_nightly_hardening_smoke"
    runtime_submission_json = portfolio_root / "native_authoring_runtime_submission_lane.json"
    runtime_writeback_depth_json = portfolio_root / "native_authoring_runtime_writeback_depth_report.json"
    multi_project_runtime_writeback_json = (
        portfolio_root / "native_authoring_multi_project_runtime_writeback_report.json"
    )
    solver_family_breadth_json = portfolio_root / "native_authoring_solver_family_breadth_report.json"
    local_runtime_scenario_depth_json = (
        portfolio_root / "native_authoring_local_runtime_scenario_depth_report.json"
    )

    project_registry_json = family_root / "native_authoring_project_registry.json"
    batch_report_json = family_root / "native_authoring_batch_job_report.json"
    runtime_submission_json = portfolio_root / "native_authoring_runtime_submission_lane.json"

    _write_json(
        portfolio_root / "native_authoring_ops_portfolio.json",
        {
            "contract_pass": True,
            "summary": {
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "family_count": 1,
                "complete_family_count": 1,
                "ready_family_count": 1,
                "family_track_count": 1,
                "runtime_ready_family_count": 1,
                "writeback_ready_family_count": 1,
                "full_lane_ready_family_count": 1,
                "narrowing_family_count": 0,
                "solver_combo_count": 14,
                "batch_snapshot_count": 2,
                "registry_project_count": 1,
                "registry_signature_verified_count": 1,
                "registry_reproducible_count": 1,
            },
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "draft_label": "steel-alt",
                    "contract_pass": True,
                    "reason_code": "PASS",
                    "commercialization_status": "ready",
                    "commercialization_score": 92,
                    "story_count": 8,
                    "member_count": 132,
                    "load_pattern_count": 6,
                    "solver_combo_count": 14,
                    "solver_mesh_request_count": 3,
                    "job_count": 2,
                    "snapshot_count": 2,
                    "workspace_ready": True,
                    "solver_ready": True,
                    "runtime_ready": True,
                    "ops_ready": True,
                    "batch_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "summary_line": "steel_braced_frame ready",
                    "artifacts": {
                        "project_registry_json": str(project_registry_json),
                        "batch_job_report_json": str(batch_report_json),
                    },
                }
            ],
            "summary_line": "Native authoring ops portfolio: PASS | families=1 | ready=1",
        },
    )
    _write_json(
        portfolio_root / "native_authoring_project_registry_index.json",
        {
            "contract_pass": True,
            "summary": {
                "project_count": 1,
                "family_count": 1,
                "portfolio_count": 1,
            },
            "project_rows": [
                {
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "registry_count": 1,
                    "all_contract_pass": True,
                    "latest_generated_at": "2026-04-19T13:00:00+00:00",
                    "latest_path": str(project_registry_json),
                    "latest_reason_code": "PASS",
                    "latest_signature_verified": True,
                    "latest_package_reproducible": True,
                    "latest_approval_count": 2,
                    "latest_approved_count": 2,
                    "latest_pending_count": 0,
                    "latest_audit_event_count": 4,
                    "latest_artifact_count": 3,
                    "latest_package_sha256": "sha-ops-001",
                    "latest_family_id": "steel_braced_frame",
                    "latest_portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "latest_draft_label": "steel-alt",
                    "registry_paths": [str(project_registry_json)],
                }
            ],
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_ids": ["native-authoring-steel-braced"],
                    "registry_count": 1,
                    "complete_registry_count": 1,
                    "signature_verified_count": 1,
                    "package_reproducible_count": 1,
                    "latest_generated_at": "2026-04-19T13:00:00+00:00",
                    "latest_path": str(project_registry_json),
                    "latest_project_id": "native-authoring-steel-braced",
                    "latest_project_name": "Native Authoring Steel Braced",
                }
            ],
        },
    )
    _write_json(
        runtime_submission_json,
        {
            "contract_pass": True,
            "summary": {
                "runtime_submission_ready": True,
                "submission_count": 1,
                "submission_ready_count": 1,
                "runtime_ready_count": 1,
                "ready_submission_count": 1,
                "writeback_ready_count": 1,
                "full_ready_count": 1,
                "queue_count": 0,
            },
            "submission_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "submission_status": "released",
                    "runtime_ready": True,
                    "submission_ready": True,
                    "writeback_ready": True,
                    "solver_combo_count": 14,
                    "solver_mesh_request_count": 3,
                    "job_count": 2,
                    "snapshot_count": 2,
                    "approval_count": 2,
                    "registry_package_sha256": "sha-ops-001",
                }
            ],
            "artifacts": {
                "native_authoring_runtime_submission_lane_json": str(runtime_submission_json),
            },
            "summary_line": "Native authoring runtime submission lane: READY | submissions=1 | ready=1 | writeback_ready=1 | queue=0",
        },
    )
    _write_json(
        runtime_writeback_depth_json,
        {
            "contract_pass": True,
            "summary": {
                "runtime_writeback_depth_ready": True,
                "family_count": 1,
                "depth_ready_family_count": 1,
                "targeted_family_count": 0,
                "signature_verified_family_count": 1,
                "package_reproducible_family_count": 1,
                "snapshot_ready_family_count": 1,
                "queue_clear_family_count": 1,
                "family_status_label": "steel_braced_frame:full",
            },
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "runtime_writeback_depth_status": "full",
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                }
            ],
            "artifacts": {
                "native_authoring_runtime_writeback_depth_report_json": str(runtime_writeback_depth_json),
            },
            "summary_line": "Native authoring runtime writeback depth: PASS | families=1 | full_depth=1 | targeted=0 | registry=1 | signature=1 | repro=1 | snapshot=1 | queue_clear=1",
        },
    )
    _write_json(
        multi_project_runtime_writeback_json,
        {
            "contract_pass": True,
            "summary": {
                "multi_project_runtime_writeback_ready": True,
                "project_count": 1,
                "family_count": 1,
                "project_family_count": 1,
                "full_depth_project_family_count": 1,
                "targeted_project_family_count": 0,
                "ready_project_count": 1,
                "signature_verified_project_count": 1,
                "package_reproducible_project_count": 1,
                "snapshot_ready_project_count": 1,
                "queue_clear_project_count": 1,
                "project_status_label": "native-authoring-steel-braced:ready",
            },
            "project_rows": [
                {
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "project_ready": True,
                    "signature_verified": True,
                    "package_reproducible": True,
                    "snapshot_ready": True,
                    "queue_clear": True,
                }
            ],
            "project_family_rows": [
                {
                    "project_id": "native-authoring-steel-braced",
                    "family_id": "steel_braced_frame",
                    "runtime_writeback_depth_status": "full",
                    "full_depth_ready": True,
                }
            ],
            "artifacts": {
                "native_authoring_multi_project_runtime_writeback_report_json": str(
                    multi_project_runtime_writeback_json
                ),
            },
            "summary_line": "Native authoring multi-project runtime/writeback: PASS | projects=1 | families=1 | project_families=1 | full_depth=1 | ready_projects=1 | signature=1 | repro=1 | snapshot=1 | queue_clear=1",
        },
    )
    _write_json(
        solver_family_breadth_json,
        {
            "contract_pass": True,
            "summary": {
                "solver_family_breadth_ready": True,
                "family_count": 1,
                "broad_ready_family_count": 1,
                "full_breadth_family_count": 1,
                "mesh_broad_family_count": 1,
                "member_multi_family_count": 1,
                "family_status_label": "steel_braced_frame:broad",
            },
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "solver_family_breadth_status": "broad",
                    "broad_solver_family_ready": True,
                    "full_solver_family_ready": True,
                    "member_family_breadth_ready": True,
                    "mesh_breadth_status": "broad",
                }
            ],
            "artifacts": {
                "native_authoring_solver_family_breadth_report_json": str(solver_family_breadth_json),
            },
            "summary_line": "Native authoring solver family breadth: PASS | families=1 | broad_ready=1 | full_breadth=1 | solver_ready=1 | combo_broad=1 | mesh_coverage=1 | mesh_broad=1 | member_multi=1 | queue=0",
        },
    )
    _write_json(
        local_runtime_scenario_depth_json,
        {
            "contract_pass": True,
            "summary": {
                "local_runtime_scenario_depth_ready": True,
                "family_count": 1,
                "depth_ready_family_count": 1,
                "trace_ready_family_count": 1,
                "mesh_trace_ready_family_count": 1,
                "runtime_ready_family_count": 1,
                "omitted_library_family_count": 0,
                "family_status_label": "steel_braced_frame:deep",
            },
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "local_runtime_scenario_depth_status": "deep",
                    "runtime_ready": True,
                    "trace_ready": True,
                    "mesh_trace_ready": True,
                    "omitted_library_combination_count": 0,
                }
            ],
            "artifacts": {
                "native_authoring_local_runtime_scenario_depth_report_json": str(
                    local_runtime_scenario_depth_json
                ),
            },
            "summary_line": "Native authoring local runtime scenario depth: PASS | families=1 | deep=1 | scenario_ready=1 | trace_ready=1 | mesh_ready=1 | runtime_ready=1 | omitted=0",
        },
    )
    _write_json(
        portfolio_root / "native_authoring_ops_portfolio_batch.json",
        {
            "contract_pass": True,
            "summary": {
                "job_count": 2,
                "snapshot_count": 2,
                "completed_count": 2,
                "failed_count": 0,
                "planned_count": 2,
                "blocked_count": 0,
                "rerun_requested_count": 0,
            },
            "summary_line": "Native authoring portfolio batch: PASS | jobs=2 | snapshots=2",
        },
    )
    _write_json(
        runtime_submission_json,
        {
            "contract_pass": True,
            "summary": {
                "runtime_submission_ready": True,
                "submission_count": 1,
                "submission_ready_count": 1,
                "runtime_ready_count": 1,
                "ready_submission_count": 1,
                "writeback_ready_count": 1,
                "full_ready_count": 1,
                "queue_count": 0,
            },
            "submission_rows": [
                {
                    "submission_id": "steel_braced_frame-runtime-001",
                    "family_id": "steel_braced_frame",
                    "portfolio_name": "phase1-native-authoring-ops-portfolio",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "submission_status": "released",
                    "runtime_ready": True,
                    "writeback_ready": True,
                    "registry_ready": True,
                    "signature_verified": True,
                    "contract_pass": True,
                    "submitted_at": "2026-04-19T14:30:00+00:00",
                }
            ],
            "artifacts": {
                "native_authoring_runtime_submission_lane_json": str(runtime_submission_json),
            },
            "summary_line": "Native authoring runtime submission lane: READY | submissions=1 | ready=1 | writeback_ready=1 | queue=0",
        },
    )
    _write_json(
        batch_report_json,
        {
            "contract_pass": True,
            "summary": {
                "job_count": 2,
                "snapshot_count": 2,
                "completed_count": 2,
                "failed_count": 0,
                "planned_count": 2,
                "blocked_count": 0,
                "rerun_requested_count": 0,
            },
            "summary_line": "Family batch: PASS | jobs=2 | snapshots=2",
        },
    )
    _write_json(
        project_registry_json,
        {
            "contract_pass": True,
            "summary": {
                "project_id": "native-authoring-steel-braced",
                "project_name": "Native Authoring Steel Braced",
                "family_id": "steel_braced_frame",
                "portfolio_name": "phase1-native-authoring-ops-portfolio",
                "draft_label": "steel-alt",
                "approval_count": 2,
                "approved_count": 2,
                "audit_event_count": 4,
                "artifact_count": 3,
                "package_sha256": "sha-ops-001",
            },
            "checks": {
                "signature_verified_pass": True,
                "package_reproducible_pass": True,
            },
        },
    )
    _write_json(
        release_root / "release_registry.json",
        {
            "contract_pass": True,
            "summary": {
                "artifact_count": 9,
                "deployment_model": "local-commercial",
                "project_registry_artifact_count": 3,
                "project_registry_approval_count": 2,
                "project_registry_package_sha256": "sha-ops-001",
                "project_registry_package_bytes": 4096,
                "signing_algorithm": "ed25519",
            },
            "checks": {
                "signature_verified_pass": True,
                "project_registry_signature_verified_pass": True,
            },
        },
    )
    _write_json(
        committee_root / "committee_summary.json",
        {
            "metrics": {
                "authority_catalog_diff_change_count": 1,
                "authority_catalog_routing_warning_active": False,
                "advanced_holdout_open_count": 0,
                "advanced_holdout_total_count": 4,
            }
        },
    )
    _write_json(
        release_root / "release_gap_report.json",
        {
            "summary": {
                "release_candidate_pass": True,
                "commercial_grade": "Commercial",
                "deployment_model": "local-commercial",
            }
        },
    )
    _write_json(
        snapshot_root / "snapshot_manifest.json",
        {
            "snapshot": "phase3_nightly_hardening_smoke",
            "generated_at": "2026-04-19T14:00:00+00:00",
            "files": ["release_gap_report.json", "release_registry.json"],
            "optional_files": ["structural_optimization_viewer.html"],
            "release_policy": {"policy_pass": True},
        },
    )
    return release_root


def test_build_project_ops_snapshot_aggregates_release_ops_surfaces(tmp_path: Path) -> None:
    release_root = _prepare_release_root(tmp_path)

    payload = build_project_ops_snapshot(
        release_root=release_root,
        generated_at="2026-04-19T15:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["project_count"] == 1
    assert payload["summary"]["family_count"] == 1
    assert payload["summary"]["portfolio_count"] == 1
    assert payload["summary"]["batch_job_count"] == 2
    assert payload["summary"]["batch_snapshot_count"] == 2
    assert payload["summary"]["submission_count"] == 1
    assert payload["summary"]["ready_submission_count"] == 1
    assert payload["summary"]["runtime_ready_family_count"] == 1
    assert payload["summary"]["writeback_ready_family_count"] == 1
    assert payload["summary"]["full_ready_family_count"] == 1
    assert payload["summary"]["ready_family_label"] == "1/1 ready families"
    assert payload["summary"]["runtime_ready_family_label"] == "1/1 runtime-ready families"
    assert payload["summary"]["writeback_ready_submission_count"] == 1
    assert payload["summary"]["writeback_ready_submission_label"] == "1/1 writeback-ready submissions"
    assert payload["summary"]["runtime_writeback_depth_ready"] is True
    assert payload["summary"]["runtime_writeback_depth_family_count"] == 1
    assert payload["summary"]["runtime_writeback_depth_full_count"] == 1
    assert payload["summary"]["multi_project_runtime_writeback_ready"] is True
    assert payload["summary"]["multi_project_runtime_writeback_project_count"] == 1
    assert payload["summary"]["multi_project_runtime_writeback_project_family_count"] == 1
    assert payload["summary"]["multi_project_runtime_writeback_ready_project_count"] == 1
    assert payload["summary"]["local_runtime_scenario_depth_ready"] is True
    assert payload["summary"]["local_runtime_scenario_depth_family_count"] == 1
    assert payload["summary"]["local_runtime_scenario_depth_ready_count"] == 1
    assert payload["summary"]["solver_family_breadth_ready"] is True
    assert payload["summary"]["solver_family_breadth_family_count"] == 1
    assert payload["summary"]["solver_family_breadth_broad_ready_count"] == 1
    assert payload["summary"]["family_runtime_writeback_alignment_pass"] is True
    assert payload["summary"]["family_runtime_writeback_alignment_count"] == 1
    assert payload["summary"]["family_runtime_writeback_alignment_label"] == "PASS 1/1 ready families aligned"
    assert "writeback_ready_submissions=1" in payload["summary"]["family_runtime_writeback_alignment_evidence"]
    assert payload["summary"]["queued_submission_count"] == 0
    assert payload["summary"]["endpoint_count"] == 14
    assert payload["summary"]["service_ready"] is True
    assert payload["summary"]["release_candidate_pass"] is True
    assert payload["summary"]["commercial_grade"] == "Commercial"
    assert payload["release_governance"]["release_registry"]["signature_verified"] is True
    assert payload["release_governance"]["latest_release_snapshot"]["snapshot"] == "phase3_nightly_hardening_smoke"
    assert payload["projects"][0]["project_id"] == "native-authoring-steel-braced"
    assert payload["families"][0]["family_id"] == "steel_braced_frame"
    assert payload["portfolios"][0]["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
    assert payload["submissions"][0]["family_id"] == "steel_braced_frame"
    assert payload["runtime_submissions"]["summary"]["submission_count"] == 1
    assert payload["runtime_submissions"]["summary"]["runtime_ready_count"] == 1
    assert payload["runtime_submissions"]["summary"]["full_ready_count"] == 1
    assert payload["artifacts"]["native_authoring_solver_family_breadth_report_json"].endswith(
        "native_authoring_solver_family_breadth_report.json"
    )
    assert payload["artifacts"]["native_authoring_runtime_writeback_depth_report_json"].endswith(
        "native_authoring_runtime_writeback_depth_report.json"
    )
    assert payload["artifacts"]["native_authoring_multi_project_runtime_writeback_report_json"].endswith(
        "native_authoring_multi_project_runtime_writeback_report.json"
    )
    assert payload["artifacts"]["native_authoring_local_runtime_scenario_depth_report_json"].endswith(
        "native_authoring_local_runtime_scenario_depth_report.json"
    )
    assert payload["artifacts"]["runtime_submission_json"].endswith("native_authoring_runtime_submission_lane.json")
    assert payload["health"]["missing_inputs"] == []
    assert payload["artifacts"]["portfolio_json"].endswith("native_authoring_ops_portfolio.json")


def test_write_project_ops_snapshot_and_http_endpoints(tmp_path: Path) -> None:
    release_root = _prepare_release_root(tmp_path)
    snapshot_out = release_root / "project_ops_service_snapshot.json"

    written = write_project_ops_snapshot(
        snapshot_out,
        release_root=release_root,
        generated_at="2026-04-19T15:30:00+00:00",
    )
    assert written["contract_pass"] is True
    assert written["artifacts"]["project_ops_service_snapshot_json"] == str(snapshot_out)
    assert written["paths"]["snapshot_json"] == str(snapshot_out)
    persisted = json.loads(snapshot_out.read_text(encoding="utf-8"))
    assert persisted["summary"]["project_count"] == 1
    assert persisted["summary"]["submission_count"] == 1
    assert persisted["summary"]["multi_project_runtime_writeback_ready"] is True
    assert persisted["summary"]["multi_project_runtime_writeback_project_count"] == 1
    assert persisted["summary"]["local_runtime_scenario_depth_ready"] is True

    audit_log = tmp_path / "audit" / "project_ops.jsonl"
    server = create_project_ops_server(
        release_root=release_root,
        port=0,
        allowed_tenants=["tenant-a"],
        audit_log_path=audit_log,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        base = f"http://{host}:{port}"

        root_payload = _get_json(f"{base}/")
        assert "/submissions" in root_payload["endpoints"]
        assert "/submissions/{family_id}" in root_payload["endpoints"]
        assert "/audit/events" in root_payload["endpoints"]

        summary_payload = _get_json(f"{base}/summary")
        assert summary_payload["contract_pass"] is True
        assert summary_payload["tenant_id"] == "tenant-a"
        assert summary_payload["summary"]["project_count"] == 1
        assert summary_payload["summary"]["submission_count"] == 1
        assert summary_payload["summary"]["family_runtime_writeback_alignment_pass"] is True
        assert summary_payload["summary"]["runtime_writeback_depth_ready"] is True
        assert summary_payload["summary"]["multi_project_runtime_writeback_ready"] is True
        assert summary_payload["summary"]["multi_project_runtime_writeback_project_count"] == 1
        assert summary_payload["summary"]["local_runtime_scenario_depth_ready"] is True
        assert summary_payload["summary"]["solver_family_breadth_ready"] is True
        assert summary_payload["runtime_submissions"]["summary"]["submission_count"] == 1
        assert summary_payload["runtime_submissions"]["summary"]["runtime_ready_count"] == 1

        project_payload = _get_json(f"{base}/projects?family_id=steel_braced_frame")
        assert project_payload["count"] == 1
        assert project_payload["items"][0]["project_id"] == "native-authoring-steel-braced"

        family_payload = _get_json(f"{base}/families/steel_braced_frame")
        assert family_payload["family_id"] == "steel_braced_frame"
        assert family_payload["project_count"] == 1
        assert family_payload["runtime_ready"] is True

        portfolio_payload = _get_json(f"{base}/portfolios/phase1-native-authoring-ops-portfolio")
        assert portfolio_payload["portfolio_name"] == "phase1-native-authoring-ops-portfolio"
        assert portfolio_payload["family_count"] == 1

        submission_payload = _get_json(f"{base}/submissions")
        assert submission_payload["count"] == 1
        assert submission_payload["items"][0]["submission_status"] == "released"

        family_submission_payload = _get_json(f"{base}/submissions/steel_braced_frame")
        assert family_submission_payload["family_id"] == "steel_braced_frame"
        assert family_submission_payload["runtime_ready"] is True

        license_payload = _get_json(f"{base}/license")
        assert license_payload["license"]["status"] == "active"
        assert license_payload["license"]["telemetry_enabled"] is False
        version_payload = _get_json(f"{base}/version")
        assert version_payload["version"] == "project-ops-api-service.v1"
        update_payload = _get_json(f"{base}/update-channel")
        assert update_payload["channel"] == "stable"
        audit_payload = _get_json(f"{base}/audit/events", role="admin")
        assert audit_payload["tenant_id"] == "tenant-a"
        assert audit_payload["count"] >= 1
        assert all("Authorization" not in json.dumps(row) for row in audit_payload["items"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_project_ops_api_rejects_missing_auth_and_invalid_tenant(tmp_path: Path) -> None:
    release_root = _prepare_release_root(tmp_path)
    server = create_project_ops_server(release_root=release_root, port=0, allowed_tenants=["tenant-a"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        base = f"http://{host}:{port}"
        try:
            urlopen(f"{base}/health")
            raise AssertionError("missing auth should fail")
        except HTTPError as error:
            assert error.code == 401
        try:
            _get_json(f"{base}/health", tenant_id="tenant-b")
            raise AssertionError("invalid tenant should fail")
        except HTTPError as error:
            assert error.code == 403
        try:
            _get_json(f"{base}/audit/events", role="viewer")
            raise AssertionError("viewer role should not read audit events")
        except HTTPError as error:
            assert error.code == 403
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_project_ops_api_surfaces_expired_license_as_degraded(tmp_path: Path) -> None:
    release_root = _prepare_release_root(tmp_path)
    license_status = tmp_path / "license.json"
    _write_json(
        license_status,
        {
            "status": "active",
            "tier": "enterprise",
            "expires_at": "2020-01-01T00:00:00+00:00",
        },
    )
    server = create_project_ops_server(
        release_root=release_root,
        port=0,
        allowed_tenants=["tenant-a"],
        license_status_path=license_status,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        payload = _get_json(f"http://{host}:{port}/license")
        assert payload["license"]["status"] == "expired"
        assert payload["license"]["degraded"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
