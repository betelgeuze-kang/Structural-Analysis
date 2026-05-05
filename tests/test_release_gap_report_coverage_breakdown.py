from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_release_gap_report_emits_time_saved_and_holdout_split(tmp_path: Path) -> None:
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
    _write(
        ci,
        {
            "contract_pass": True,
            "summary": {},
            "checks": {},
            "global_metrics": {},
            "grade": {},
            "frontend_payload": {},
            "workflow_productization_report": {
                "summary": {
                    "results_explorer_traceability_contact_coupling_summary_label": "support families=2 | proxy families=2 | assembled depth=5",
                    "results_explorer_contact_coupling_pass": True,
                }
            },
            "support_search_summary_line": "Support search: PASS | support_search=9 | node_surface_proxy=5 | support_depth=21",
            "general_fe_contact_matrix_summary_line": "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21",
        },
    )
    _write(static, {"pass": True})
    _write(
        committee,
        {
            "midas_kds_row_provenance_export_summary_line": "MIDAS KDS row provenance export: PASS | combos=6 | rows=144 | members=12 | clauses=6 | exact_rows=144",
            "midas_kds_row_provenance_export_row_count": 144,
            "midas_kds_row_provenance_export_exact_row_count": 144,
            "midas_kds_row_provenance_preview_rows": [
                {
                    "combination_name": "gLCB1",
                    "member_id": "C-TST-003",
                    "clause_label": "KDS-MOMENT-Y-001",
                    "baseline_focus_member_id": "27441",
                    "bridge_row_provenance_mode_label": "exact row-level provenance",
                    "clause_provenance_summary_label": "rows=12 | members=12 | rules=1 | hazards=3",
                    "bridge_member_inventory_summary_label": "review=C-TST-003 | case=C-TST-003 | baseline=27441 | member_types=column",
                }
            ],
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
                "recommended_use": "Automate repeated analysis while preserving residual holdout.",
            },
            "residual_holdout_categories": [
                {"id": "licensed_engineer_review_required", "label": "Licensed Engineer Review", "owner": "기술사", "scope": "final judgment"},
                {"id": "legacy_tool_cross_validation_required", "label": "Legacy Tool Cross-Validation", "owner": "기존툴+기술사", "scope": "cross-check"},
                {"id": "legal_authority_signoff_required", "label": "Legal Sign-Off", "owner": "기술사/기존 승인 workflow", "scope": "formal sign-off"},
            ],
        },
    )

    proc = subprocess.run(
        [
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
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out_json.read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["estimated_time_saved_pct_range"] == [70, 90]
    assert "Heuristic estimate" in summary["estimated_time_saved_basis"]
    assert summary["workflow_contact_coupling_summary"] == {
        "summary_label": "support families=2 | proxy families=2 | assembled depth=5",
        "pass": True,
        "support_family_count": 2,
        "proxy_family_count": 2,
        "assembled_depth_value": 5,
    }
    assert summary["general_fe_contact_matrix_summary"] == {
        "summary_label": "ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | "
        "support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21",
        "pass": True,
        "support_search_count": 9,
        "node_surface_proxy_count": 5,
        "support_depth_score": 21,
    }
    assert summary["workflow_contact_coupling_summary_line"] == "Workflow contact coupling: PASS | support families=2 | proxy families=2 | assembled depth=5"
    assert summary["general_fe_contact_matrix_summary_line"] == "General FE contact matrix: PASS | ready=10/10 | direct=6/6 | foundation=yes | interface=yes | ssi=yes | soil_tunnel=yes | support=contact:6,foundation:4,device:5 | support_search=9 | node_surface_proxy=5 | support_depth=21"
    assert (
        summary["commercial_scope_summary_line"]
        == "Commercial scope: grade=Commercial | engineer_in_loop_accelerated_coverage_ready=True | "
        "full_commercial_replacement_ready=False | accelerated_coverage=95-99% | residual_holdout=1-5%"
    )
    assert (
        summary["commercial_reliability_breadth_summary_line"]
        == "Commercial reliability breadth: PASS | grade=Commercial | exact_row_coverage=144/144 | "
        "evidence_rows=1 | evidence_present=True"
    )
    assert summary["midas_kds_row_provenance_export_exact_row_count"] == 144
    assert summary["midas_kds_row_provenance_preview_row_count"] == 1
    assert summary["midas_kds_row_provenance_preview_rows_present"] is True

    buckets = payload["residual_holdout_buckets"]
    assert [row["relative_share_pct"] for row in buckets] == [50, 30, 20]
    assert sum(int(row["relative_share_pct"]) for row in buckets) == 100
    assert buckets[0]["absolute_project_pct_range"] == [0.5, 2.5]
    assert buckets[1]["absolute_project_pct_range"] == [0.3, 1.5]
    assert buckets[2]["absolute_project_pct_range"] == [0.2, 1.0]
    assert [row["queue_name"] for row in buckets] == [
        "licensed_engineer_review_queue",
        "legacy_tool_cross_validation_queue",
        "legal_authority_signoff_queue",
    ]
    assert [row["queue_status"] for row in buckets] == [
        "pending_review",
        "pending_cross_validation",
        "pending_signoff",
    ]
    assert [row["status"] for row in buckets] == ["open", "open", "open"]

    markdown = out_md.read_text(encoding="utf-8")
    assert "Estimated time saved" in markdown
    assert "Relative Share" in markdown
    assert "Commercial scope" in markdown
    assert "Commercial reliability breadth" in markdown
