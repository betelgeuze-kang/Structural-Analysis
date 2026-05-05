from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_release_gap_report import _foundation_member_count_from_counts
from tests.test_foundation_realish_fixture import (
    _run_dataset_fixture,
    _run_foundation_artifact_and_report,
    _run_parser_fixture,
)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _foundation_fixture_path(name: str) -> Path:
    return Path(__file__).resolve().parent / "fixtures" / "foundation_realish" / name


def _run_realish_foundation_release_fixture(tmp_path: Path) -> tuple[Path, Path]:
    model_out = tmp_path / "foundation_model.json"
    dataset_out = tmp_path / "foundation_dataset_report.json"
    dataset_npz = tmp_path / "foundation_dataset.npz"
    artifact_out = tmp_path / "foundation_optimization_artifact.json"
    report_out = tmp_path / "foundation_optimization_report.json"
    changes_out = tmp_path / "design_optimization_cost_reduction_changes.json"
    blocked_out = tmp_path / "design_optimization_cost_reduction_blocked_actions.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/parse_midas_mgt_to_json_npz.py",
            "--mgt",
            str(_foundation_fixture_path("foundation_small.mgt")),
            "--json-out",
            str(model_out),
            "--npz-out",
            str(tmp_path / "foundation_model.npz"),
            "--edge-list-out",
            str(tmp_path / "foundation_edges.json"),
            "--report-out",
            str(tmp_path / "foundation_parse_report.json"),
            "--min-nodes",
            "4",
            "--min-elements",
            "2",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_design_optimization_dataset.py",
            "--midas-model",
            str(model_out),
            "--code-check",
            str(_foundation_fixture_path("foundation_small_code_check.json")),
            "--pbd-review",
            str(_foundation_fixture_path("foundation_small_pbd.json")),
            "--ndtha-residual",
            str(_foundation_fixture_path("foundation_small_ndtha.json")),
            "--dataset-npz-out",
            str(dataset_npz),
            "--summary-out",
            str(dataset_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    dataset = json.loads(dataset_out.read_text(encoding="utf-8"))
    foundation_rows = [row for row in dataset["rows_head"] if str(row.get("member_type")) == "foundation"]
    assert foundation_rows
    first = foundation_rows[0]
    _write(
        changes_out,
        {
            "changes": [
                {
                    "group_id": str(first.get("group_id", "")),
                    "member_type": str(first.get("member_type", "")),
                    "semantic_group": str(first.get("semantic_group", "")),
                    "action_name": "mat_down",
                }
            ]
        },
    )
    _write(blocked_out, {"blocked_rows": []})

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_artifact.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--design-optimization-npz",
            str(dataset_npz),
            "--midas-model",
            str(model_out),
            "--cost-reduction-changes",
            str(changes_out),
            "--cost-reduction-blocked-actions",
            str(blocked_out),
            "--out",
            str(artifact_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_foundation_optimization_report.py",
            "--design-optimization-dataset",
            str(dataset_out),
            "--foundation-optimization-artifact",
            str(artifact_out),
            "--out",
            str(report_out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return dataset_out, report_out


def test_release_gap_report_uses_engineer_in_loop_holdout_model(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
                "recommended_use": "Automate the dominant repeated analysis workload while keeping a residual engineer holdout.",
            },
            "residual_holdout_categories": [
                {"id": "licensed_engineer_review_required", "label": "Licensed Engineer Review", "owner": "기술사", "scope": "final judgment"},
                {"id": "legacy_tool_cross_validation_required", "label": "Legacy Tool Cross-Validation", "owner": "기존툴+기술사", "scope": "cross-check"},
                {"id": "legal_authority_signoff_required", "label": "Legal Sign-Off", "owner": "기술사/기존 승인 workflow", "scope": "formal sign-off"},
            ],
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["deployment_model"] == "engineer_in_the_loop_accelerated_coverage"
    assert summary["accelerated_coverage_target_pct_range"] == [95, 99]
    assert summary["residual_holdout_target_pct_range"] == [1, 5]
    assert summary["engineer_in_loop_accelerated_coverage_ready"] is True
    assert "residual engineer holdout" in summary["time_saving_focus"]
    assert summary["full_commercial_replacement_ready"] is False
    assert summary["p0_closed"] is True
    assert summary["p0_closure_status"] == "closed"
    assert summary["p1_unblocked"] is True
    assert summary["p1_handoff_status"] == "unblocked"
    bucket_ids = {row["id"] for row in payload["residual_holdout_buckets"]}
    assert bucket_ids == {
        "licensed_engineer_review_required",
        "legacy_tool_cross_validation_required",
        "legal_authority_signoff_required",
    }
    work_items = {row["work_item_id"]: row for row in payload["residual_holdout_work_items"]}
    assert set(work_items) == {"RH-001", "RH-002", "RH-003"}
    assert work_items["RH-001"]["queue_name"] == "licensed_engineer_review_queue"
    assert work_items["RH-001"]["status"] == "open"
    assert work_items["RH-001"]["sla_label"] == "72h"
    assert work_items["RH-001"]["due_date"] == "assignment_plus_3_business_days"
    assert work_items["RH-001"]["closure_evidence_required"] == "signed_engineer_review_packet"
    assert work_items["RH-001"]["closure_evidence_status"] == "pending"
    assert work_items["RH-002"]["queue_status"] == "pending_cross_validation"
    assert work_items["RH-003"]["owner"] == "기술사/기존 승인 workflow"
    assert summary["residual_holdout_work_item_count"] == 3
    markdown = out_md.read_text(encoding="utf-8")
    assert "P0 closure status: `closed`" in markdown
    assert "P1 handoff status: `unblocked`" in markdown
    assert "Residual Holdout Model" in markdown
    assert "RH-001" in markdown
    assert "Engineer-in-loop accelerated coverage ready" in markdown


def test_release_gap_foundation_member_count_normalizes_hyphenated_keys() -> None:
    assert _foundation_member_count_from_counts({"beam": 4, "pile-cap": 2, "raft": 1}) == 3


def test_release_gap_report_emits_authority_catalog_warning_from_committee_summary(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        committee,
        {
            "authority_catalog_routing_diff": {
                "baseline_seeded": False,
                "change_count": 2,
                "added_count": 1,
                "removed_count": 1,
                "unchanged_count": 0,
                "diff_rows": [],
            }
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["authority_catalog_routing_warning_active"] is True
    assert payload["summary"]["authority_catalog_diff_change_count"] == 2
    assert payload["warnings"][0]["id"] == "authority_catalog_routing_change"
    markdown = out_md.read_text(encoding="utf-8")
    assert "Active Warnings" in markdown
    assert "authority_catalog_routing_change" in markdown


def test_release_gap_report_includes_promotion_hold_manifest(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, authority, hip, midas, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        promotion,
        {
            "contract_pass": False,
            "reason_code": "HOLD_FOR_REVIEW",
            "hold_review_manifest": str(tmp_path / "hold_review_manifest.json"),
            "hold_review_packet_md": str(tmp_path / "hold_review_packet.md"),
            "hold_review_packet_pdf": str(tmp_path / "hold_review_packet.pdf"),
            "hold_review_ack_json": str(tmp_path / "hold_review_ack.json"),
        },
    )
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["promotion_hold_for_review"] is True
    assert payload["summary"]["hold_review_manifest"].endswith("hold_review_manifest.json")
    assert payload["summary"]["hold_review_packet_md"].endswith("hold_review_packet.md")
    assert payload["summary"]["hold_review_packet_pdf"].endswith("hold_review_packet.pdf")
    assert payload["summary"]["hold_review_ack_json"].endswith("hold_review_ack.json")
    assert payload["artifacts"]["hold_review_manifest"].endswith("hold_review_manifest.json")
    assert payload["artifacts"]["hold_review_packet_md"].endswith("hold_review_packet.md")
    assert payload["artifacts"]["hold_review_packet_pdf"].endswith("hold_review_packet.pdf")
    assert payload["artifacts"]["hold_review_ack_json"].endswith("hold_review_ack.json")
    assert payload["warnings"][0]["id"] == "promotion_hold_for_review"
    assert payload["warnings"][0]["manifest"].endswith("hold_review_manifest.json")
    assert payload["warnings"][0]["packet"].endswith("hold_review_packet.md")
    assert payload["warnings"][0]["packet_pdf"].endswith("hold_review_packet.pdf")
    assert payload["warnings"][0]["ack"].endswith("hold_review_ack.json")
    markdown = out_md.read_text(encoding="utf-8")
    assert "manifest:" in markdown
    assert "packet:" in markdown
    assert "packet_pdf:" in markdown
    assert "ack:" in markdown


def test_release_gap_report_exposes_midas_semantic_binding_and_exporter_gap(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "element_rows_skipped": 0,
                "use_stld_block_count": 2,
                "semantic_load_case_count": 2,
                "semantic_load_combination_count": 1,
                "bound_nodal_load_row_count": 2,
                "bound_selfweight_row_count": 1,
                "bound_pressure_row_count": 1,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
            },
            "parser_diagnostics": {
                "unknown_row_total": 0,
                "unknown_section_count": 0,
                "typed_row_total": 12,
            },
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["midas_semantic_load_binding_pass"] is True
    assert summary["midas_use_stld_block_count"] == 2
    assert summary["midas_semantic_load_case_count"] == 2
    assert summary["midas_semantic_load_combination_count"] == 1
    assert summary["midas_bound_nodal_load_row_count"] == 2
    assert summary["mgt_export_artifact_exists"] is True
    assert summary["mgt_export_contract_pass"] is True
    assert summary["mgt_export_support_mode"] == "native_authoring_supported_changeset"
    assert summary["mgt_export_supported_change_count"] >= 1
    assert summary["mgt_export_unsupported_change_count"] >= 0
    gap_ids = {row["id"] for row in payload["remaining_gaps"]}
    assert "GAP-P0-000" in gap_ids
    markdown = out_md.read_text(encoding="utf-8")
    assert "MIDAS semantic load binding" in markdown
    assert "MIDAS optimized export artifact present" in markdown
    assert "support_mode=`native_authoring_supported_changeset`" in markdown


def test_release_gap_report_reads_custom_mgt_export_paths(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"
    custom_output_mgt = tmp_path / "custom.optimized.mgt"
    custom_export_report = tmp_path / "custom.optimized.export_report.json"
    custom_queue_manifest = tmp_path / "custom.optimized.audit_review_queue.json"
    custom_followup_manifest = tmp_path / "custom.optimized.audit_review_followup_manifest.json"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "element_rows_skipped": 0,
                "use_stld_block_count": 1,
                "semantic_load_case_count": 1,
                "semantic_load_combination_count": 1,
                "bound_nodal_load_row_count": 1,
                "bound_selfweight_row_count": 0,
                "bound_pressure_row_count": 0,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
            },
            "parser_diagnostics": {"unknown_row_total": 0},
        },
    )
    custom_output_mgt.write_text("*UNIT\n", encoding="utf-8")
    _write(
        custom_export_report,
        {
            "contract_pass": True,
            "summary": {
                "support_mode": "custom_override_test",
                "supported_change_count": 7,
                "unsupported_change_count": 2,
                "direct_patch_change_count": 4,
                "instruction_sidecar_change_count": 3,
                "group_local_rebar_payload_row_count": 9,
                "group_local_rebar_payload_available_count": 8,
                "group_local_connection_detailing_payload_row_count": 3,
                "group_local_connection_detailing_payload_available_count": 2,
                "group_local_detailing_payload_row_count": 4,
                "group_local_detailing_payload_available_count": 3,
                "connection_detailing_payload_namespace_mode": "group_local",
                "connection_detailing_payload_group_local_namespace_present": True,
                "detailing_payload_namespace_mode": "group_local",
                "detailing_payload_group_local_namespace_present": True,
                "connection_detailing_structured_payload_mapped_change_count": 2,
                "connection_detailing_direct_patch_eligible_change_count": 1,
                "detailing_direct_patch_eligible_change_count": 2,
                "detailing_structured_payload_mapped_change_count": 3,
                "connection_detailing_delivery_mode": "structured_group_local_payload_plus_sidecar",
                "detailing_delivery_mode": "direct_patch_metadata_plus_sidecar",
                "rebar_direct_patch_eligible_change_count": 6,
                "patched_material_row_count": 11,
                "cloned_material_count": 12,
                "audit_review_queue_item_count": 2,
                "audit_review_queue_pending_count": 2,
                "audit_review_queue_acknowledged_count": 0,
                "audit_review_queue_status_counts": {"pending_review": 2},
                "audit_review_queue_action_family_counts": {"connection_detailing": 1, "detailing": 1},
            },
        },
    )
    _write(
        custom_queue_manifest,
        {
            "schema_version": "1.0",
            "audit_review_queue_items": [],
            "audit_review_queue_status_directory": str(tmp_path / "queue_status"),
            "summary": {
                "audit_review_queue_item_count": 2,
                "audit_review_queue_pending_count": 1,
                "audit_review_queue_acknowledged_count": 1,
                "audit_review_queue_approved_count": 1,
                "audit_review_queue_status_counts": {"approved": 1, "pending_review": 1},
                "audit_review_queue_action_family_counts": {"connection_detailing": 1, "detailing": 1},
                "audit_review_queue_status_mode": "refreshed_from_status_files",
            },
        },
    )
    _write(
        custom_followup_manifest,
        {
            "schema_version": "1.0",
            "audit_review_followup_rows": [],
            "summary": {
                "audit_review_followup_item_count": 2,
                "audit_review_followup_open_item_count": 1,
                "audit_review_followup_closed_item_count": 1,
                "audit_review_followup_action_counts": {"close_packet": 1, "wait_for_review": 1},
                "audit_review_followup_action_label": "close_packet=1, wait_for_review=1",
                "audit_review_followup_owner_counts": {"licensed_engineer": 1, "none": 1},
                "audit_review_followup_owner_label": "licensed_engineer=1, none=1",
                "audit_review_followup_status_counts": {"approved": 1, "pending_review": 1},
                "audit_review_followup_status_label": "approved=1, pending_review=1",
                "audit_review_followup_mode": "queue_status_projected_followup_actions",
            },
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--mgt-export-output-mgt",
        str(custom_output_mgt),
        "--mgt-export-report",
        str(custom_export_report),
        "--mgt-export-audit-review-queue-manifest",
        str(custom_queue_manifest),
        "--mgt-export-audit-review-followup-manifest",
        str(custom_followup_manifest),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["mgt_export_artifact_exists"] is True
    assert summary["mgt_export_contract_pass"] is True
    assert summary["mgt_export_support_mode"] == "custom_override_test"
    assert summary["mgt_export_supported_change_count"] == 7
    assert summary["mgt_export_unsupported_change_count"] == 2
    assert summary["mgt_export_group_local_rebar_payload_row_count"] == 9
    assert summary["mgt_export_group_local_rebar_payload_available_count"] == 8
    assert summary["mgt_export_group_local_connection_detailing_payload_row_count"] == 3
    assert summary["mgt_export_group_local_connection_detailing_payload_available_count"] == 2
    assert summary["mgt_export_group_local_detailing_payload_row_count"] == 4
    assert summary["mgt_export_group_local_detailing_payload_available_count"] == 3
    assert summary["mgt_export_connection_detailing_direct_patch_eligible_change_count"] == 1
    assert summary["mgt_export_detailing_direct_patch_eligible_change_count"] == 2
    assert summary["mgt_export_connection_detailing_delivery_mode"] == "structured_group_local_payload_plus_sidecar"
    assert summary["mgt_export_detailing_delivery_mode"] == "direct_patch_metadata_plus_sidecar"
    assert summary["mgt_export_rebar_direct_patch_eligible_change_count"] == 6
    assert summary["mgt_export_patched_material_row_count"] == 11
    assert summary["mgt_export_cloned_material_count"] == 12
    assert summary["mgt_export_audit_review_queue_item_count"] == 2
    assert summary["mgt_export_audit_review_queue_pending_count"] == 1
    assert summary["mgt_export_audit_review_queue_acknowledged_count"] == 1
    assert summary["mgt_export_audit_review_queue_status_label"] == "approved=1, pending_review=1"
    assert summary["mgt_export_audit_review_followup_item_count"] == 2
    assert summary["mgt_export_audit_review_followup_open_item_count"] == 1
    assert summary["mgt_export_audit_review_followup_closed_item_count"] == 1
    assert summary["mgt_export_audit_review_followup_action_label"] == "close_packet=1, wait_for_review=1"
    assert summary["mgt_export_audit_review_followup_owner_label"] == "licensed_engineer=1, none=1"
    assert summary["mgt_export_audit_review_followup_status_label"] == "approved=1, pending_review=1"


def test_release_gap_report_emits_advanced_holdout_readiness(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd = tmp_path / "pbd.json"
    dataset = tmp_path / "dataset.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "element_rows_skipped": 0,
                "element_skip_ratio": 0.0,
                "use_stld_block_count": 2,
                "semantic_load_case_count": 6,
                "semantic_load_combination_count": 8,
                "bound_nodal_load_row_count": 2,
                "bound_selfweight_row_count": 1,
                "bound_pressure_row_count": 10,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
                "pressure_load_row_count": 10,
            },
            "parser_diagnostics": {
                "unknown_row_total": 0,
                "unknown_section_count": 0,
                "typed_row_total": 12,
            },
        },
    )
    _write(
        committee,
        {
            "metrics": {
                "design_opt_blocked_constructability_hard_gate": 6,
                "design_opt_blocked_illegal_by_mask": 0,
                "design_opt_blocked_constructability_hard_gate_family_label": "detailing=4",
            }
        },
    )
    _write(
        pbd,
        {
            "contract_pass": True,
            "summary": {"response_storage": "npz_external+inline_summary", "case_metrics_npz_case_count": 7},
            "artifacts": {"hinge_proxy_3d_png": "hinge_proxy_3d.png", "hinge_proxy_timeline_png": "hinge_proxy_timeline.png"},
        },
    )
    _write(dataset, {"contract_pass": True, "summary": {"member_type_counts": {"beam": 10, "wall": 4}}})

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    release_status = payload["release_status"]
    assert summary["pbd_dynamic_hinge_refresh_ready"] is True
    assert summary["pbd_hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert summary["pbd_hinge_refresh_artifact_present"] is True
    assert summary["pbd_hinge_refresh_artifact_kind"] == "hinge_refresh_projected_from_optimization_changes"
    assert summary["pbd_hinge_refresh_source_mode"] == "rebar_sensitive_member_local_refresh"
    assert summary["pbd_hinge_refresh_overlap_member_count"] > 0
    assert summary["pbd_hinge_refresh_rebar_sensitive_member_count"] > 0
    assert summary["panel_zone_3d_clash_ready"] is True
    assert summary["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert summary["panel_zone_internal_engine_complete"] is False
    assert summary["panel_zone_external_validation_pending"] is False
    assert summary["panel_zone_validation_boundary"] == "solver_verified"
    assert summary["panel_zone_external_validation_status_label"] == "verified"
    assert summary["panel_zone_external_validation_advisory_only"] is False
    assert summary["panel_zone_external_validation_release_blocking"] is False
    assert summary["panel_zone_status_label"] == "release_ready"
    assert summary["panel_zone_advisory_only"] is False
    assert summary["panel_zone_release_blocking"] is False
    assert summary["panel_zone_external_validation_provenance_summary_label"].startswith(
        "validated_sources=3/3 | exact_sources=3/3 | fallback_sources=0/3"
    )
    assert "closure_mode=closed_exact_validated" in summary["panel_zone_external_validation_closing_summary_label"]
    assert "inbox=empty_after_successful_consume" in summary["panel_zone_external_validation_closing_summary_label"]
    assert release_status["panel_zone_external_validation_status_label"] == "verified"
    assert release_status["panel_zone_external_validation_advisory_only"] is False
    assert release_status["panel_zone_external_validation_release_blocking"] is False
    assert release_status["panel_zone_status_label"] == "release_ready"
    assert release_status["panel_zone_advisory_only"] is False
    assert release_status["panel_zone_release_blocking"] is False
    assert summary["foundation_optimization_ready"] is True
    assert summary["foundation_member_type_present"] is True
    assert summary["wind_tunnel_raw_mapping_ready"] is True
    advanced_ids = {row["id"] for row in payload["advanced_holdouts"]}
    assert {
        "pbd_dynamic_hinge_refresh",
        "panel_zone_3d_clash_and_anchorage",
        "foundation_mat_pile_optimization",
        "wind_tunnel_raw_mapping",
    } <= advanced_ids
    markdown = out_md.read_text(encoding="utf-8")
    assert "Advanced Holdouts" in markdown
    assert "Dynamic plastic-hinge refresh" in markdown
    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    remaining = {str(row.get("id")): row for row in payload["remaining_gaps"]}
    assert advanced["wind_tunnel_raw_mapping"]["ready"] is True
    assert advanced["panel_zone_3d_clash_and_anchorage"]["status"] == "closed"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["status_label"] == "release_ready"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["advisory_only"] is False
    assert advanced["panel_zone_3d_clash_and_anchorage"]["release_blocking"] is False
    assert "status_label=release_ready" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "advisory_only=False" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "release_blocking=False" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "closure_mode=closed_exact_validated" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert remaining["GAP-P0-003"]["status"] == "closed"
    assert remaining["GAP-P0-003"]["status_label"] == "release_ready"
    assert remaining["GAP-P0-003"]["advisory_only"] is False
    assert remaining["GAP-P0-003"]["release_blocking"] is False
    assert "artifact_present=True" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "artifact_kind=hinge_refresh_projected_from_optimization_changes" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "source_mode=rebar_sensitive_member_local_refresh" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "overlap_members=" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "rebar_sensitive_members=" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]


def test_release_gap_report_emits_advanced_holdout_readiness_positive_path(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd = tmp_path / "pbd.json"
    dataset = tmp_path / "dataset.json"
    pbd_hinge = tmp_path / "pbd_hinge_refresh.json"
    panel_zone = tmp_path / "panel_zone_clash.json"
    foundation = tmp_path / "foundation_optimization.json"
    wind_raw_mapping = tmp_path / "wind_raw_mapping.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "element_rows_skipped": 0,
                "element_skip_ratio": 0.0,
                "use_stld_block_count": 2,
                "semantic_load_case_count": 6,
                "semantic_load_combination_count": 8,
                "bound_nodal_load_row_count": 2,
                "bound_selfweight_row_count": 1,
                "bound_pressure_row_count": 10,
                "unbound_nodal_load_row_count": 0,
                "unbound_selfweight_row_count": 0,
                "unbound_pressure_row_count": 0,
                "pressure_load_row_count": 10,
            },
            "parser_diagnostics": {
                "unknown_row_total": 0,
                "unknown_section_count": 0,
                "typed_row_total": 12,
            },
        },
    )
    _write(
        committee,
        {
            "metrics": {
                "design_opt_blocked_constructability_hard_gate": 0,
                "design_opt_blocked_illegal_by_mask": 0,
                "design_opt_blocked_constructability_hard_gate_family_label": "",
            }
        },
    )
    _write(
        pbd,
        {
            "contract_pass": True,
            "summary": {"response_storage": "npz_external+inline_summary", "case_metrics_npz_case_count": 11},
            "artifacts": {"hinge_proxy_3d_png": "hinge_proxy_3d.png", "hinge_proxy_timeline_png": "hinge_proxy_timeline.png"},
        },
    )
    _write(dataset, {"contract_pass": True, "summary": {"member_type_counts": {"beam": 10, "wall": 4, "foundation": 3}}})
    _write(
        pbd_hinge,
        {
            "contract_pass": True,
            "summary": {
                "hinge_state_mode": "computed_member_local_hinge_refresh",
                "reason": "dynamic hinge-refresh evidence is attached",
                "hinge_refresh_artifact_present": True,
                "hinge_refresh_artifact_kind": "hinge_refresh_source_json",
                "hinge_refresh_source_mode": "rebar_sensitive_member_local_refresh",
                "hinge_refresh_overlap_member_count": 2,
                "hinge_refresh_rebar_sensitive_member_count": 2,
            },
        },
    )
    _write(
        panel_zone,
        {
            "contract_pass": True,
            "summary": {
                "constructability_mode": "panel_zone_3d_clash_and_anchorage_verified",
                "reason": "panel-zone 3D clash artifact is attached",
            },
        },
    )
    _write(
        foundation,
        {
            "contract_pass": True,
            "summary": {
                "optimization_mode": "active_foundation_member_optimization",
                "reason": "foundation optimization artifact is attached",
            },
        },
    )
    _write(
        wind_raw_mapping,
        {
            "contract_pass": True,
            "summary": {
                "mapping_mode": "raw_hffb_node_pressure_mapping",
                "reason": "raw wind-tunnel mapping artifact is attached",
            },
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset),
        "--pbd-hinge-refresh-report",
        str(pbd_hinge),
        "--panel-zone-clash-report",
        str(panel_zone),
        "--foundation-optimization-report",
        str(foundation),
        "--wind-raw-mapping-report",
        str(wind_raw_mapping),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    release_status = payload["release_status"]
    assert summary["pbd_dynamic_hinge_refresh_ready"] is True
    assert summary["pbd_hinge_state_mode"] == "computed_member_local_hinge_refresh"
    assert "hinge-refresh evidence" in summary["pbd_hinge_refresh_reason"]
    assert summary["pbd_hinge_refresh_artifact_present"] is True
    assert summary["pbd_hinge_refresh_artifact_kind"] == "hinge_refresh_source_json"
    assert summary["pbd_hinge_refresh_source_mode"] == "rebar_sensitive_member_local_refresh"
    assert summary["pbd_hinge_refresh_overlap_member_count"] == 2
    assert summary["pbd_hinge_refresh_rebar_sensitive_member_count"] == 2
    assert summary["panel_zone_3d_clash_ready"] is True
    assert summary["panel_zone_constructability_mode"] == "panel_zone_3d_clash_and_anchorage_verified"
    assert "panel-zone 3D clash artifact" in summary["panel_zone_constructability_reason"]
    assert summary["panel_zone_external_validation_status_label"] == "not_applicable"
    assert summary["panel_zone_external_validation_advisory_only"] is False
    assert summary["panel_zone_external_validation_release_blocking"] is False
    assert summary["panel_zone_status_label"] == "release_ready"
    assert summary["panel_zone_advisory_only"] is False
    assert summary["panel_zone_release_blocking"] is False
    assert summary["panel_zone_external_validation_required_evidence"] == "solver_verified_3d_clash_and_anchorage_artifact"
    assert summary["panel_zone_external_validation_local_closure_state"] == "awaiting_release_refresh_after_successful_consume"
    assert release_status["panel_zone_external_validation_status_label"] == "not_applicable"
    assert release_status["panel_zone_external_validation_advisory_only"] is False
    assert release_status["panel_zone_external_validation_release_blocking"] is False
    assert release_status["panel_zone_status_label"] == "release_ready"
    assert release_status["panel_zone_advisory_only"] is False
    assert release_status["panel_zone_release_blocking"] is False
    assert summary["foundation_optimization_ready"] is True
    assert summary["foundation_member_type_present"] is True
    assert summary["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert "foundation optimization artifact" in summary["foundation_optimization_reason"]
    assert summary["wind_tunnel_raw_mapping_ready"] is True
    assert summary["wind_tunnel_mapping_mode"] == "raw_hffb_node_pressure_mapping"
    assert "raw wind-tunnel mapping artifact" in summary["wind_tunnel_mapping_reason"]

    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    assert advanced["pbd_dynamic_hinge_refresh"]["ready"] is True
    assert "artifact_present=True" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "artifact_kind=hinge_refresh_source_json" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "source_mode=rebar_sensitive_member_local_refresh" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "overlap_members=2" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert "rebar_sensitive_members=2" in advanced["pbd_dynamic_hinge_refresh"]["evidence"]
    assert advanced["panel_zone_3d_clash_and_anchorage"]["ready"] is True
    assert advanced["panel_zone_3d_clash_and_anchorage"]["status_label"] == "release_ready"
    assert advanced["panel_zone_3d_clash_and_anchorage"]["advisory_only"] is False
    assert advanced["panel_zone_3d_clash_and_anchorage"]["release_blocking"] is False
    assert "status_label=release_ready" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert advanced["foundation_mat_pile_optimization"]["ready"] is True
    assert advanced["wind_tunnel_raw_mapping"]["ready"] is True


def test_release_gap_report_propagates_open_advanced_holdout_modes_from_reports(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd = tmp_path / "pbd.json"
    dataset = tmp_path / "dataset.json"
    panel_zone = tmp_path / "panel_zone_clash.json"
    panel_zone_inbox_status = tmp_path / "panel_zone_inbox_status.json"
    foundation = tmp_path / "foundation_optimization.json"
    wind_raw_mapping = tmp_path / "wind_raw_mapping.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "bound_pressure_row_count": 10,
                "pressure_load_row_count": 10,
            },
            "parser_diagnostics": {
                "unknown_row_total": 0,
                "unknown_section_count": 0,
                "typed_row_total": 12,
            },
        },
    )
    _write(committee, {"metrics": {}})
    _write(
        pbd,
        {
            "contract_pass": True,
            "summary": {"response_storage": "npz_external+inline_summary", "case_metrics_npz_case_count": 11},
            "artifacts": {"hinge_proxy_3d_png": "hinge_proxy_3d.png"},
        },
    )
    _write(dataset, {"contract_pass": True, "summary": {"member_type_counts": {"beam": 10, "wall": 4}}})
    _write(
        panel_zone,
        {
            "contract_pass": False,
            "reason": "member-local panel-zone proxy artifact is attached, but 3D clash verification is still missing",
            "summary": {
                "constructability_mode": "proxy_artifact_attached_but_not_3d_verified",
                "panel_zone_proxy_candidate_count": 45,
                "panel_zone_source_artifact_kind": "design_optimization_dataset_npz",
                "panel_zone_source_contract_mode": "topology_capable_proxy_scan",
                "panel_zone_source_valid_row_counts": {
                    "panel_zone_joint_geometry_3d": 2,
                    "panel_zone_rebar_anchorage_3d": 1,
                    "panel_zone_clash_verification_3d": 2,
                },
                "panel_zone_source_overlap_member_counts": {
                    "panel_zone_joint_geometry_3d": 1,
                    "panel_zone_rebar_anchorage_3d": 1,
                    "panel_zone_clash_verification_3d": 1,
                },
                "panel_zone_source_candidate_scan_modes": {
                    "panel_zone_joint_geometry_3d": "npz_full",
                    "panel_zone_rebar_anchorage_3d": "npz_full",
                    "panel_zone_clash_verification_3d": "npz_full",
                },
                "panel_zone_instruction_sidecar_present": True,
                "panel_zone_instruction_sidecar_change_count": 17,
                "panel_zone_instruction_sidecar_candidate_overlap_mode": "section_signature",
                "panel_zone_instruction_sidecar_overlap_row_count": 4,
                "panel_zone_instruction_sidecar_overlap_member_count": 11,
                "panel_zone_instruction_sidecar_overlap_group_count": 3,
                "panel_zone_member_mapping_sidecar_present": True,
                "panel_zone_member_mapping_sidecar_mode": "explicit_member_id_map",
                "panel_zone_member_mapping_sidecar_row_count": 1,
                "panel_zone_member_mapping_sidecar_applied_row_count": 1,
                "panel_zone_member_mapping_sidecar_unmapped_source_member_count": 0,
                "panel_zone_validated_source_row_count_total": 5,
                "panel_zone_validated_source_overlap_member_count_min": 1,
                "panel_zone_topology_capable_input": True,
                "panel_zone_missing_required_sources": [
                    "panel_zone_joint_geometry_3d",
                    "panel_zone_rebar_anchorage_3d",
                    "panel_zone_clash_verification_3d",
                ],
            },
        },
    )
    _write(
        panel_zone_inbox_status,
        {
            "contract_pass": True,
            "summary": {
                "panel_zone_solver_verified_inbox_status_mode": "pending_raw_triplet",
                "panel_zone_solver_verified_inbox_has_input": True,
                "panel_zone_solver_verified_pending_input": True,
                "panel_zone_solver_verified_input_mode_detected": "raw_triplet",
                "panel_zone_solver_verified_latest_consume_report_present": True,
                "panel_zone_solver_verified_latest_consume_contract_pass": False,
                "panel_zone_solver_verified_latest_consume_reason_code": "ERR_HANDOFF_FAILED",
                "panel_zone_solver_verified_source_origin_class": "fixture_sample",
                "panel_zone_solver_verified_release_refresh_source_allowed": False,
                "panel_zone_solver_verified_recommended_action": "consume_pending_input",
            },
        },
    )
    _write(
        foundation,
        {
            "contract_pass": False,
            "reason": "foundation members are represented by artifact scan, but no dedicated optimization artifact is attached",
            "summary": {
                "optimization_mode": "foundation_members_present_but_no_active_optimization",
                "foundation_member_type_count": 2,
                "foundation_scope_source": "artifact_scan",
                "foundation_artifact_scan_mode": "npz_full_scan",
                "upstream_foundation_label_count": 3,
                "upstream_foundation_provenance_mode": "parsed_model_labels_present",
            },
        },
    )
    _write(
        wind_raw_mapping,
        {
            "contract_pass": False,
            "reason": "raw wind manifest is missing or failed verification",
            "summary": {
                "mapping_mode": "raw_hffb_node_pressure_mapping",
            },
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset),
        "--panel-zone-clash-report",
        str(panel_zone),
        "--panel-zone-solver-verified-inbox-status-report",
        str(panel_zone_inbox_status),
        "--foundation-optimization-report",
        str(foundation),
        "--wind-raw-mapping-report",
        str(wind_raw_mapping),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    release_status = payload["release_status"]
    assert summary["panel_zone_3d_clash_ready"] is False
    assert summary["panel_zone_constructability_mode"] == "proxy_artifact_attached_but_not_3d_verified"
    assert "3D clash verification is still missing" in summary["panel_zone_constructability_reason"]
    assert summary["panel_zone_external_validation_status_label"] == "not_applicable"
    assert summary["panel_zone_external_validation_advisory_only"] is False
    assert summary["panel_zone_external_validation_release_blocking"] is False
    assert summary["panel_zone_status_label"] == "release_blocking"
    assert summary["panel_zone_advisory_only"] is False
    assert summary["panel_zone_release_blocking"] is True
    assert release_status["panel_zone_external_validation_status_label"] == "not_applicable"
    assert release_status["panel_zone_external_validation_advisory_only"] is False
    assert release_status["panel_zone_external_validation_release_blocking"] is False
    assert release_status["panel_zone_status_label"] == "release_blocking"
    assert release_status["panel_zone_advisory_only"] is False
    assert release_status["panel_zone_release_blocking"] is True
    assert summary["panel_zone_proxy_candidate_count"] == 45
    assert summary["panel_zone_source_artifact_kind"] == "design_optimization_dataset_npz"
    assert summary["panel_zone_source_contract_mode"] == "topology_capable_proxy_scan"
    assert summary["panel_zone_source_valid_row_counts"]["panel_zone_joint_geometry_3d"] == 2
    assert summary["panel_zone_source_overlap_member_counts"]["panel_zone_clash_verification_3d"] == 1
    assert summary["panel_zone_source_candidate_scan_modes"]["panel_zone_rebar_anchorage_3d"] == "npz_full"
    assert summary["panel_zone_instruction_sidecar_present"] is True
    assert summary["panel_zone_instruction_sidecar_change_count"] == 17
    assert summary["panel_zone_instruction_sidecar_candidate_overlap_mode"] == "section_signature"
    assert summary["panel_zone_instruction_sidecar_overlap_row_count"] == 4
    assert summary["panel_zone_instruction_sidecar_overlap_member_count"] == 11
    assert summary["panel_zone_member_mapping_sidecar_present"] is True
    assert summary["panel_zone_member_mapping_sidecar_mode"] == "explicit_member_id_map"
    assert summary["panel_zone_member_mapping_sidecar_row_count"] == 1
    assert summary["panel_zone_member_mapping_sidecar_applied_row_count"] == 1
    assert summary["panel_zone_validated_source_row_count_total"] == 5
    assert summary["panel_zone_validated_source_overlap_member_count_min"] == 1
    assert summary["panel_zone_topology_capable_input"] is True
    assert summary["panel_zone_missing_required_sources"] == [
        "panel_zone_joint_geometry_3d",
        "panel_zone_rebar_anchorage_3d",
        "panel_zone_clash_verification_3d",
    ]
    assert summary["panel_zone_solver_verified_inbox_status_mode"] == "pending_raw_triplet"
    assert summary["panel_zone_solver_verified_pending_input"] is True
    assert summary["panel_zone_solver_verified_latest_consume_contract_pass"] is False
    assert summary["panel_zone_solver_verified_source_origin_class"] == "fixture_sample"
    assert summary["panel_zone_solver_verified_release_refresh_source_allowed"] is False
    assert summary["panel_zone_solver_verified_recommended_action"] == "consume_pending_input"
    assert "pending consume into the live release chain" in summary["panel_zone_constructability_reason"]
    assert summary["foundation_optimization_ready"] is False
    assert summary["foundation_member_type_present"] is True
    assert summary["foundation_optimization_mode"] == "foundation_members_present_but_no_active_optimization"
    assert "artifact scan" in summary["foundation_optimization_reason"]
    assert summary["foundation_scope_source"] == "artifact_scan"
    assert summary["foundation_artifact_scan_mode"] == "npz_full_scan"
    assert summary["upstream_foundation_label_count"] == 3
    assert summary["upstream_foundation_provenance_mode"] == "parsed_model_labels_present"
    assert summary["wind_tunnel_raw_mapping_ready"] is False
    assert summary["wind_tunnel_mapping_mode"] == "raw_hffb_node_pressure_mapping"
    assert "manifest" in summary["wind_tunnel_mapping_reason"]
    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    assert "proxy_candidates=45" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "validated_rows=5" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "min_overlap=1" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "sidecar_present=True" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "sidecar_changes=17" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "sidecar_mode=section_signature" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "sidecar_overlap_rows=4" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "sidecar_overlap_members=11" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "status_label=release_blocking" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "advisory_only=False" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "release_blocking=True" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "inbox_status=pending_raw_triplet" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "inbox_origin=fixture_sample" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "latest_consume=False:ERR_HANDOFF_FAILED" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "scan_modes=panel_zone_clash_verification_3d:npz_full" in advanced["panel_zone_3d_clash_and_anchorage"]["evidence"]
    assert "scope_source=artifact_scan" in advanced["foundation_mat_pile_optimization"]["evidence"]


def test_release_gap_report_surfaces_foundation_parser_drop_provenance(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd = tmp_path / "pbd.json"
    dataset = tmp_path / "dataset.json"
    foundation = tmp_path / "foundation_optimization.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "bound_pressure_row_count": 10,
                "pressure_load_row_count": 10,
            },
            "parser_diagnostics": {
                "unknown_row_total": 0,
                "unknown_section_count": 0,
                "typed_row_total": 12,
            },
        },
    )
    _write(committee, {"metrics": {}})
    _write(
        pbd,
        {
            "contract_pass": True,
            "summary": {"response_storage": "npz_external+inline_summary", "case_metrics_npz_case_count": 11},
            "artifacts": {"hinge_proxy_3d_png": "hinge_proxy_3d.png"},
        },
    )
    _write(dataset, {"contract_pass": True, "summary": {"member_type_counts": {"beam": 10, "wall": 4}}})
    _write(
        foundation,
        {
            "contract_pass": False,
            "reason": (
                "Raw MIDAS source still contains foundation-like labels, but the parsed model and active "
                "design-optimization dataset expose none. raw_labels=3, parsed_labels=0, scan=npz_full_empty."
            ),
            "summary": {
                "optimization_mode": "foundation_scope_lost_between_raw_source_and_parsed_model",
                "foundation_member_type_count": 0,
                "foundation_scope_source": "artifact_empty_scan",
                "foundation_artifact_scan_mode": "npz_full_empty",
                "upstream_foundation_label_count": 0,
                "raw_source_foundation_label_count": 3,
                "upstream_foundation_provenance_mode": "parser_drop_suspected",
            },
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset),
        "--foundation-optimization-report",
        str(foundation),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["foundation_optimization_ready"] is False
    assert summary["foundation_member_type_present"] is False
    assert summary["foundation_optimization_mode"] == "foundation_scope_lost_between_raw_source_and_parsed_model"
    assert "raw_labels=3" in summary["foundation_optimization_reason"]
    assert summary["raw_source_foundation_label_count"] == 3
    assert summary["upstream_foundation_provenance_mode"] == "parser_drop_suspected"

    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    evidence = advanced["foundation_mat_pile_optimization"]["evidence"]
    assert "raw_source_labels=3" in evidence
    assert "upstream_mode=parser_drop_suspected" in evidence


def test_release_gap_report_surfaces_realish_foundation_fixture_provenance(tmp_path: Path) -> None:
    model_out, parse_report = _run_parser_fixture(tmp_path)
    dataset_out, npz_out = _run_dataset_fixture(tmp_path, model_path=model_out)
    _run_foundation_artifact_and_report(
        tmp_path=tmp_path,
        dataset_out=dataset_out,
        npz_out=npz_out,
        model_path=model_out,
    )

    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    pbd = tmp_path / "pbd.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(committee, {"metrics": {}})
    _write(
        pbd,
        {
            "contract_pass": True,
            "summary": {"response_storage": "npz_external+inline_summary", "case_metrics_npz_case_count": 11},
            "artifacts": {"hinge_proxy_3d_png": "hinge_proxy_3d.png"},
        },
    )

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(parse_report),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--pbd-package",
        str(pbd),
        "--design-opt-dataset-report",
        str(dataset_out),
        "--foundation-optimization-report",
        str(tmp_path / "foundation_optimization_report.json"),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["foundation_optimization_ready"] is True
    assert summary["foundation_member_type_present"] is True
    assert summary["foundation_member_type_count"] == 2
    assert summary["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert summary["foundation_scope_source"] == "dataset_summary"
    assert summary["foundation_artifact_scan_mode"] == "npz_full"
    assert summary["upstream_foundation_label_count"] >= summary["raw_source_foundation_label_count"]
    assert summary["raw_source_foundation_label_count"] == 3
    assert summary["upstream_foundation_provenance_mode"] == "dataset_scope_only"
    assert "foundation optimization artifact" in summary["foundation_optimization_reason"]

    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    foundation = advanced["foundation_mat_pile_optimization"]
    assert foundation["ready"] is True
    assert foundation["mode"] == "active_foundation_member_optimization"
    assert "foundation_member_type_count=2" in foundation["evidence"]
    assert "scope_source=dataset_summary" in foundation["evidence"]
    assert "raw_source_labels=3" in foundation["evidence"]
    assert "upstream_labels=" in foundation["evidence"]
    assert "upstream_mode=dataset_scope_only" in foundation["evidence"]


def test_release_gap_report_surfaces_realish_foundation_fixture_summary(tmp_path: Path) -> None:
    nightly = tmp_path / "nightly.json"
    ci = tmp_path / "ci.json"
    static = tmp_path / "static.json"
    freeze = tmp_path / "freeze.json"
    promotion = tmp_path / "promotion.json"
    commercial = tmp_path / "commercial.json"
    authority = tmp_path / "authority.json"
    hip = tmp_path / "hip.json"
    midas = tmp_path / "midas.json"
    construction = tmp_path / "construction.json"
    diaphragm = tmp_path / "diaphragm.json"
    repro = tmp_path / "repro.json"
    registry = tmp_path / "registry.json"
    kds = tmp_path / "kds.json"
    solver_hip = tmp_path / "solver_hip.json"
    rc = tmp_path / "rc.json"
    quality = tmp_path / "quality.json"
    committee = tmp_path / "committee.json"
    out_json = tmp_path / "gap.json"
    out_md = tmp_path / "gap.md"

    dataset, foundation = _run_realish_foundation_release_fixture(tmp_path)

    _write(nightly, {"contract_pass": True, "reason_code": "PASS"})
    for path in [ci, freeze, promotion, authority, hip, construction, diaphragm, repro, registry, kds, solver_hip, rc, quality]:
        _write(path, {"contract_pass": True, "summary": {}, "checks": {}, "global_metrics": {}, "grade": {}, "frontend_payload": {}})
    _write(static, {"pass": True})
    _write(
        commercial,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {"label": "commercial"},
            "deployment_model": {
                "mode": "engineer_in_the_loop_accelerated_coverage",
                "accelerated_coverage_target_pct_range": [95, 99],
                "residual_holdout_target_pct_range": [1, 5],
                "engineer_in_loop_accelerated_coverage_ready": True,
                "full_commercial_replacement_ready": False,
            },
            "residual_holdout_categories": [],
        },
    )
    _write(
        midas,
        {
            "contract_pass": True,
            "metrics": {"bound_pressure_row_count": 0, "pressure_load_row_count": 0},
            "parser_diagnostics": {"unknown_row_total": 0, "unknown_section_count": 0, "typed_row_total": 7},
        },
    )
    _write(committee, {"metrics": {}})

    cmd = [
        sys.executable,
        "implementation/phase1/generate_release_gap_report.py",
        "--nightly-release",
        str(nightly),
        "--ci-gate",
        str(ci),
        "--static-validation",
        str(static),
        "--freeze-report",
        str(freeze),
        "--promotion-report",
        str(promotion),
        "--commercial-readiness",
        str(commercial),
        "--global-authority",
        str(authority),
        "--hip-kernel-smoke",
        str(hip),
        "--midas-conversion",
        str(midas),
        "--construction-sequence",
        str(construction),
        "--flexible-diaphragm",
        str(diaphragm),
        "--repro-version-lock",
        str(repro),
        "--release-registry",
        str(registry),
        "--kds-compliance",
        str(kds),
        "--solver-hip-e2e",
        str(solver_hip),
        "--rc-benchmark-lock",
        str(rc),
        "--quality-mgt-corpus",
        str(quality),
        "--committee-summary",
        str(committee),
        "--design-opt-dataset-report",
        str(dataset),
        "--foundation-optimization-report",
        str(foundation),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["foundation_optimization_ready"] is True
    assert summary["foundation_member_type_present"] is True
    assert summary["foundation_member_type_count"] == 2
    assert summary["foundation_optimization_mode"] == "active_foundation_member_optimization"
    assert summary["foundation_scope_source"] == "dataset_summary"
    assert summary["foundation_artifact_scan_mode"] == "npz_full"
    assert summary["upstream_foundation_provenance_mode"] == "dataset_scope_only"
    assert summary["raw_source_foundation_label_count"] > 0
    advanced = {str(row.get("id")): row for row in payload["advanced_holdouts"]}
    assert advanced["foundation_mat_pile_optimization"]["ready"] is True
    assert "scope_source=dataset_summary" in advanced["foundation_mat_pile_optimization"]["evidence"]
    assert "raw_source_labels=" in advanced["foundation_mat_pile_optimization"]["evidence"]
