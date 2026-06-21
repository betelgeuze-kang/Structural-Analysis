from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_independent_product_readiness.py"
SPEC = importlib.util.spec_from_file_location("check_independent_product_readiness", SCRIPT_PATH)
assert SPEC is not None
check_independent_product_readiness = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_independent_product_readiness)


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _allowlist(path: Path) -> Path:
    return _write_json(path, {"schema_version": "source-boundary-allowlist.v1", "records": []})


def _closed_core(tmp_path: Path) -> dict[str, Path]:
    return {
        "p0": _write_json(
            tmp_path / "p0.json",
            {
                "schema_version": "p0-closure-status.v1",
                "p0_closed": True,
                "release_publication_closed": True,
                "core_evidence_closed": True,
            },
        ),
        "p1": _write_json(
            tmp_path / "p1.json",
            {
                "schema_version": "p1-readiness-status.v1",
                "p1_inputs_ready": True,
                "p1_execution_unblocked": True,
            },
        ),
        "p1_breadth": _write_json(
            tmp_path / "p1-breadth.json",
            {
                "schema_version": "p1-benchmark-breadth-status.v1",
                "benchmark_breadth_inputs_ready": True,
                "p1_benchmark_execution_unblocked": True,
            },
        ),
    }


def _strict_preflight(path: Path, *, contract_pass: bool) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "p1-evidence-sidecar-intake-preflight.v1",
            "contract_pass": contract_pass,
            "reason_code": "PASS" if contract_pass else "ERR_P1_EVIDENCE_SIDECAR_INTAKE_PENDING",
            "blockers": [] if contract_pass else ["external_receipt_or_closure_pending:hardest_external_10case"],
            "summary": {
                "external_receipt_attached_count": 4 if contract_pass else 0,
                "external_expected_queue_count": 4,
                "residual_closed_count": 3 if contract_pass else 0,
                "residual_expected_work_item_count": 3,
            },
        },
    )


def _commercialization(path: Path, *, strict_closed: bool, full_replacement: bool = False) -> Path:
    return _write_json(
        path,
        {
            "schema_version": "commercialization-level-report.v1",
            "contract_pass": True,
            "strict_evidence_closed": strict_closed,
            "strict_evidence_blockers": [] if strict_closed else ["external_submission_receipts_pending"],
            "recommended_claim": (
                "independent commercial structural analysis product with engineer sign-off boundary"
                if strict_closed
                else "engineer-in-loop commercial assist only; strict external/RH evidence remains pending."
            ),
            "commercial_scope": {
                "full_commercial_replacement_ready": full_replacement,
            },
        },
    )


def test_independent_product_readiness_blocks_current_missing_strict_and_ops_gates(tmp_path: Path) -> None:
    core = _closed_core(tmp_path)
    api = _write_text(
        tmp_path / "project_ops_api_service.py",
        'Authorization = "Bearer token"\nX_Tenant_ID = "X-Tenant-ID"\n'
        'def write_audit_event(): pass\nroute = "/audit/events"\n'
        'secret = "project-ops-dev-secret"\n',
    )
    claim_doc = _write_text(
        tmp_path / "docs" / "commercialization-improvement-priority-assessment.md",
        "현재 단계는 92%라고도 쓰고, 보수적 제품화 관점은 75%라고도 쓴다.",
    )

    payload = check_independent_product_readiness.build_report(
        p0_status=core["p0"],
        p1_readiness_status=core["p1"],
        p1_benchmark_breadth_status=core["p1_breadth"],
        commercialization_status=_commercialization(tmp_path / "commercial.json", strict_closed=False),
        strict_evidence_preflight=_strict_preflight(tmp_path / "preflight.json", contract_pass=False),
        claim_docs=(claim_doc,),
        independent_plan=tmp_path / "missing-plan.md",
        production_security_doc=tmp_path / "missing-security.md",
        runtime_packaging_doc=tmp_path / "missing-runtime-doc.md",
        project_ops_api=api,
        runtime_strict_probe=tmp_path / "missing-probe.json",
        runtime_packaging_manifest=tmp_path / "missing-runtime-manifest.json",
        support_bundle_manifest=tmp_path / "missing-support.json",
        viewer_performance_budget_manifest=tmp_path / "missing-viewer-performance-budget.json",
        viewer_browser_performance_probe=tmp_path / "missing-viewer-browser-performance.json",
        viewer_visual_regression_baseline=tmp_path / "missing-viewer-visual-regression.json",
        workstation_delivery_readiness=tmp_path / "missing-workstation-readiness.json",
        source_boundary_allowlist=_allowlist(tmp_path / "allowlist.json"),
        tracked_files=[],
    )

    assert payload["contract_pass"] is False
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert "workstation delivery-service gate does not close" in payload["claim_boundary"]
    assert payload["independent_commercial_product_ready"] is False
    assert payload["full_autonomous_replacement_ready"] is False
    assert "Strict external and residual holdout evidence::external_submission_receipts_pending" in payload["blockers"]
    assert "Runtime production path::runtime_strict_probe_missing" in payload["blockers"]
    assert "Production API security and operations::project_ops_dev_secret_default_present" in payload["blockers"]
    assert "Commercial claim governance::commercialization_percentage_claims_conflict" in payload["blockers"]
    assert payload["workstation_delivery_service"]["status"] == "blocked"
    assert not any("Workstation delivery service" in blocker for blocker in payload["blockers"])
    assert any("Attach real EB receipt" in action for action in payload["next_actions"])


def test_independent_product_readiness_passes_when_product_gates_close(tmp_path: Path) -> None:
    core = _closed_core(tmp_path)
    api = _write_text(
        tmp_path / "project_ops_api_service.py",
        'Authorization = "Bearer token"\nX_Tenant_ID = "X-Tenant-ID"\n'
        'def write_audit_event(): pass\nroute = "/audit/events"\n'
        'def check_rate_limit(): raise TOO_MANY_REQUESTS\nerror = "rate_limited"\n'
        'request_metadata_byte_limit = 8192\nerror = "request_metadata_too_large"\n'
        'route = "/audit/digest"\naudit_log_sha256 = "sha"\n'
        'route = "/ops/policy"\nschema = "project-ops-policy.v1"\n'
        'audit_retention_days = 365\nbackup_policy = "daily"\ntenant_delete_policy = "ticket"\n',
    )
    claim_doc = _write_text(tmp_path / "claim.md", "engineer-in-loop boundary with strict evidence closed.")
    production_doc = _write_text(tmp_path / "production-security.md", "production security runbook")
    runtime_doc = _write_text(tmp_path / "runtime-packaging.md", "runtime packaging runbook")
    plan = _write_text(tmp_path / "independent-plan.md", "independent product plan")
    ops_drill = _write_json(
        tmp_path / "project-ops-drill.json",
        {"contract_pass": True, "drill_mode": "dry_run_contract"},
    )
    runtime_probe = _write_json(tmp_path / "runtime-probe.json", {"strict_rust_hip_pass": True})
    runtime_manifest = _write_json(tmp_path / "runtime-manifest.json", {"contract_pass": True})
    support_manifest = _write_json(tmp_path / "support-manifest.json", {"contract_pass": True})
    onprem_manifest = _write_json(tmp_path / "onprem-manifest.json", {"contract_pass": True})
    viewer_performance_manifest = _write_json(
        tmp_path / "viewer-performance-budget.json",
        {"contract_pass": True, "budget_mode": "static_contract", "live_performance_claim": False},
    )
    viewer_browser_performance = _write_json(
        tmp_path / "viewer-browser-performance.json",
        {"contract_pass": True, "performance_probe_mode": "local_browser_smoke", "live_performance_claim": False},
    )
    viewer_visual_regression = _write_json(
        tmp_path / "viewer-visual-regression.json",
        {"contract_pass": True, "visual_regression_mode": "local_canvas_signature_baseline"},
    )
    workstation_delivery_readiness = _write_json(
        tmp_path / "workstation-readiness.json",
        {"contract_pass": True, "summary_line": "Workstation delivery readiness: PASS"},
    )

    payload = check_independent_product_readiness.build_report(
        p0_status=core["p0"],
        p1_readiness_status=core["p1"],
        p1_benchmark_breadth_status=core["p1_breadth"],
        commercialization_status=_commercialization(tmp_path / "commercial.json", strict_closed=True),
        strict_evidence_preflight=_strict_preflight(tmp_path / "preflight.json", contract_pass=True),
        claim_docs=(claim_doc,),
        independent_plan=plan,
        production_security_doc=production_doc,
        runtime_packaging_doc=runtime_doc,
        project_ops_api=api,
        project_ops_deployment_drill=ops_drill,
        runtime_strict_probe=runtime_probe,
        runtime_packaging_manifest=runtime_manifest,
        support_bundle_manifest=support_manifest,
        onprem_deployment_packaging_manifest=onprem_manifest,
        viewer_performance_budget_manifest=viewer_performance_manifest,
        viewer_browser_performance_probe=viewer_browser_performance,
        viewer_visual_regression_baseline=viewer_visual_regression,
        workstation_delivery_readiness=workstation_delivery_readiness,
        source_boundary_allowlist=_allowlist(tmp_path / "allowlist.json"),
        tracked_files=[],
    )

    assert payload["contract_pass"] is True
    assert payload["source_commit_sha"]
    assert payload["engine_version"] == "structural-optimization-workbench@1.0.0"
    assert payload["reused_evidence"] is False
    assert payload["independent_commercial_product_ready"] is True
    assert payload["full_autonomous_replacement_ready"] is False
    assert payload["readiness_score"] == 100.0
    assert payload["blockers"] == []
    packaging_gate = next(gate for gate in payload["gates"] if gate["label"] == "Deployment packaging and support bundle")
    assert packaging_gate["viewer_browser_performance_probe_pass"] is True
    assert packaging_gate["viewer_visual_regression_baseline_pass"] is True
    assert payload["workstation_delivery_service"]["status"] == "ready"
