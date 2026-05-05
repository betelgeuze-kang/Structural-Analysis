from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path("scripts/materialize_clean_checkout_evidence_chain.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manifest() -> dict:
    return {
        "schema_version": "real_project_corpus_seed_manifest.v1",
        "generated_at": "2026-05-03T00:00:00+00:00",
        "source_families": [
            {
                "source_id": "koneps_turnkey_design_docs",
                "source_label": "KONEPS turnkey design docs",
                "source_kind": "public_procurement_metadata",
                "jurisdiction": "KR",
                "official_entrypoint_url": "https://example.test/koneps",
                "priority_phase": "P1",
                "access_policy": {
                    "classification": "metadata_only",
                    "redistribution_allowed": False,
                    "requires_manual_review": True,
                    "license_basis": "manual review",
                },
            },
            {
                "source_id": "peer_tbi_tall_buildings",
                "source_label": "PEER TBI",
                "source_kind": "public_benchmark_citation",
                "jurisdiction": "US",
                "official_entrypoint_url": "https://example.test/peer-tbi",
                "priority_phase": "P1",
                "access_policy": {
                    "classification": "citation_seed",
                    "redistribution_allowed": False,
                    "requires_manual_review": True,
                    "license_basis": "citation only",
                },
            },
        ],
    }


def _midas_report() -> dict:
    return {
        "contract_pass": True,
        "reason_code": "PASS",
        "run_id": "phase1-midas-kds-geometry-bridge-validation",
        "summary": {
            "artifact_count": 3,
            "exact_geometry_bridge_pass_count": 3,
            "review_row_count_total": 12,
            "exact_mapped_row_provenance_count_total": 12,
            "full_member_crosswalk_count_total": 12,
            "full_section_crosswalk_count_total": 9,
            "full_load_crosswalk_count_total": 6,
        },
    }


def _commercial_report() -> dict:
    checks = {
        "real_source_pass": True,
        "benchmark_breadth_pass": True,
        "measured_dynamic_targets_pass": True,
        "measured_source_family_pass": True,
        "measured_case_count_pass": True,
        "accuracy_pass": True,
        "noise_robustness_pass": True,
        "ood_safety_pass": True,
        "gpu_strict_pass": True,
    }
    return {
        "contract_pass": True,
        "reason_code": "PASS",
        "checks": checks,
        "grade": {
            "label": "Commercial",
            "commercial_pass": True,
        },
        "deployment_model": {
            "mode": "engineer_in_the_loop_accelerated_coverage",
            "accelerated_coverage_target_pct_range": [95, 99],
            "residual_holdout_target_pct_range": [1, 5],
            "engineer_in_loop_accelerated_coverage_ready": True,
            "full_commercial_replacement_ready": False,
        },
        "residual_holdout_categories": [
            {"id": "licensed_engineer_review_required"},
            {"id": "legacy_tool_cross_validation_required"},
            {"id": "legal_authority_signoff_required"},
        ],
    }


def _p0_status() -> dict:
    return {
        "schema_version": "p0-closure-status.v1",
        "status": "closed",
        "p0_closed": True,
        "core_evidence_closed": True,
        "release_publication_closed": True,
        "gates": [],
        "next_action": "promote release manifest and proceed to P1/P2 breadth work",
    }


def test_materialize_clean_checkout_evidence_chain_hydrates_and_generates_ordered_reports(tmp_path: Path) -> None:
    manifest = tmp_path / "real_project_corpus_seed_manifest.json"
    p0_status = tmp_path / "published" / "p0-status.json"
    evidence_index = tmp_path / "published" / "release-publication-evidence-index.json"
    midas_source = tmp_path / "release_evidence" / "midas" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_source = tmp_path / "release_evidence" / "commercial" / "commercial_readiness_report.json"
    midas_target = tmp_path / "generated" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_target = tmp_path / "generated" / "commercial_readiness_report.json"
    coverage = tmp_path / "generated" / "real_project_parser_coverage_matrix.json"
    peer = tmp_path / "generated" / "peer_tbi_benchmark_metric_records.json"
    row_provenance = tmp_path / "generated" / "real_project_row_provenance_report.json"
    p1_status = tmp_path / "generated" / "p1-readiness-status.json"
    p1_breadth = tmp_path / "generated" / "p1-benchmark-breadth-status.json"
    out = tmp_path / "generated" / "clean-checkout-evidence-chain.json"

    _write_json(manifest, _manifest())
    _write_json(p0_status, _p0_status())
    _write_json(
        evidence_index,
        {
            "schema_version": "release-publication-evidence-index.v1",
            "paths": {"p0_status_json": str(p0_status)},
        },
    )
    _write_json(midas_source, _midas_report())
    _write_json(commercial_source, _commercial_report())

    cmd = [
        sys.executable,
        str(SCRIPT),
        "--manifest",
        str(manifest),
        "--publication-evidence-index",
        str(evidence_index),
        "--coverage-matrix",
        str(coverage),
        "--peer-metric-records",
        str(peer),
        "--row-provenance",
        str(row_provenance),
        "--midas-kds-validation-report",
        str(midas_target),
        "--midas-kds-source-evidence",
        str(midas_source),
        "--commercial-readiness",
        str(commercial_target),
        "--commercial-readiness-source-evidence",
        str(commercial_source),
        "--p1-readiness-out",
        str(p1_status),
        "--p1-benchmark-out",
        str(p1_breadth),
        "--json",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["midas_kds_validation"]["ok"] is True
    assert payload["commercial_readiness"]["commercial_scope"]["full_commercial_replacement_ready"] is False
    assert payload["commercial_readiness"]["commercial_scope"]["engineer_in_loop_accelerated_coverage_ready"] is True
    assert payload["artifacts"]["p0_status"] == str(p0_status)
    assert payload["artifacts"]["publication_evidence_index"] == str(evidence_index)
    assert payload["p0_release_blocker"] is False
    assert payload["p1_execution_unblocked"] is True
    assert payload["p1_benchmark_execution_unblocked"] is True
    assert payload["p1_readiness_status"]["p1_inputs_ready"] is True
    assert payload["p1_readiness_status"]["p1_execution_unblocked"] is True
    assert payload["p1_benchmark_breadth_status"]["benchmark_breadth_inputs_ready"] is True

    assert midas_target.exists()
    assert commercial_target.exists()
    assert coverage.exists()
    assert peer.exists()
    row_payload = json.loads(row_provenance.read_text(encoding="utf-8"))
    assert row_payload["summary"]["midas_kds_validation_present"] is True
    assert row_payload["summary"]["midas_kds_exact_row_provenance_count"] == 12
    assert p1_status.exists()
    assert p1_breadth.exists()
