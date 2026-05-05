from __future__ import annotations

import json
import subprocess
import sys
import zipfile
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
            {"id": "licensed_engineer_review_required", "owner": "licensed_engineer"},
            {"id": "legacy_tool_cross_validation_required", "owner": "legacy_tool_owner"},
            {"id": "legal_authority_signoff_required", "owner": "authority_workflow_owner"},
        ],
    }


def _external_submission() -> dict:
    rows = []
    for index, queue_id in enumerate(
        ["hardest_external_10case", "tpu_hffb", "peer_spd_hinge", "korean_public_structures"],
        start=1,
    ):
        rows.append(
            {
                "work_item_id": f"EB-{index:03d}",
                "queue_id": queue_id,
                "submission_id": f"p1-{queue_id}",
                "submission_scope": "full_external_submission_package",
                "owner": f"{queue_id}_owner",
                "status": "ready_for_full_submission",
                "queue_status": "ready_for_full_submission",
                "submission_lifecycle_status": "ready_to_submit",
                "submission_status": "ready_to_submit",
                "submission_owner_action": "submit_external_benchmark_package_and_attach_receipt",
                "submission_receipt": "pending",
                "submission_receipt_status": "pending_external_submission_receipt",
                "receipt_status": "pending_external_submission_receipt",
                "receipt_url": "",
                "onepage_attestation": f"{queue_id} one-page attestation",
                "onepage_attestation_status": "ready_for_full_submission",
                "dry_run_evidence": f"{queue_id}: PASS",
                "closure_evidence_required": f"{queue_id}_submission_receipt",
                "closure_evidence_path": "",
                "closure_evidence_status": "pending",
                "status_lifecycle": {"current_status": "ready_for_full_submission"},
            }
        )
    return {
        "schema_version": "1.0",
        "contract_pass": True,
        "reason_code": "PASS_START_NOW_FULL",
        "summary": {
            "submission_queue_count": 4,
            "submission_queue_ready_count": 4,
            "submission_queue_review_pending_count": 0,
            "submission_queue_blocked_count": 0,
            "onepage_attestation_status": "ready_for_full_submission",
        },
        "submission_queue": rows,
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
    external_submission = tmp_path / "release_evidence" / "external" / "external_benchmark_submission_readiness.json"
    external_updates = tmp_path / "release_evidence" / "productization" / "external_benchmark_submission_updates.json"
    residual_updates = tmp_path / "release_evidence" / "productization" / "residual_holdout_closure_updates.json"
    midas_target = tmp_path / "generated" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_target = tmp_path / "generated" / "commercial_readiness_report.json"
    coverage = tmp_path / "generated" / "real_project_parser_coverage_matrix.json"
    peer = tmp_path / "generated" / "peer_tbi_benchmark_metric_records.json"
    row_provenance = tmp_path / "generated" / "real_project_row_provenance_report.json"
    p1_status = tmp_path / "generated" / "p1-readiness-status.json"
    p1_breadth = tmp_path / "generated" / "p1-benchmark-breadth-status.json"
    p1_operational = tmp_path / "generated" / "p1-operational-queues" / "p1_operational_queues.json"
    p1_operational_md = tmp_path / "generated" / "p1-operational-queues" / "p1_operational_queues.md"
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
    _write_json(external_submission, _external_submission())
    _write_json(
        external_updates,
        {
            "schema_version": "external-benchmark-submission-updates.v1",
            "updates": {
                queue_id: {
                    "receipt_status": "pending_external_submission_receipt",
                    "closure_evidence_status": "pending",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                }
                for queue_id in (
                    "hardest_external_10case",
                    "tpu_hffb",
                    "peer_spd_hinge",
                    "korean_public_structures",
                )
            },
        },
    )
    _write_json(
        residual_updates,
        {
            "schema_version": "residual-holdout-closure-updates.v1",
            "updates": {
                "RH-001": {
                    "status": "closed",
                    "closure_evidence_path": "release_evidence/productization/RH-001.closure.json",
                    "closure_evidence_status": "attached",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                },
                "RH-002": {
                    "closure_evidence_status": "pending",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                },
                "RH-003": {
                    "closure_evidence_status": "pending",
                    "last_checked_at_utc": "2026-05-05T04:05:06Z",
                },
            },
        },
    )

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
        "--external-benchmark-submission-readiness",
        str(external_submission),
        "--external-benchmark-submission-updates",
        str(external_updates),
        "--residual-holdout-closure-updates",
        str(residual_updates),
        "--p1-readiness-out",
        str(p1_status),
        "--p1-benchmark-out",
        str(p1_breadth),
        "--p1-operational-queues-out",
        str(p1_operational),
        "--p1-operational-queues-out-md",
        str(p1_operational_md),
        "--json",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["inputs_contract_pass"] is True
    assert payload["p0_closure_evidence_consumed"] is True
    assert payload["midas_kds_validation"]["ok"] is True
    assert payload["commercial_readiness"]["commercial_scope"]["full_commercial_replacement_ready"] is False
    assert payload["commercial_readiness"]["commercial_scope"]["engineer_in_loop_accelerated_coverage_ready"] is True
    assert payload["artifacts"]["p0_status"] == str(p0_status)
    assert payload["artifacts"]["publication_evidence_index"] == str(evidence_index)
    assert payload["p0_release_blocker"] is False
    assert payload["p1_execution_unblocked"] is True
    assert payload["p1_benchmark_execution_unblocked"] is True
    assert payload["publication_sidecars_pass"] is True
    assert payload["external_benchmark_submission_updates"]["all_expected_updates_present"] is True
    assert payload["residual_holdout_closure_updates"]["all_expected_updates_present"] is True
    assert payload["p1_operational_queues_pass"] is True
    assert payload["p1_operational_queues"]["summary"]["external_submission_queue_count"] == 4
    assert payload["p1_operational_queues"]["summary"]["external_submission_updates_applied_count"] == 4
    assert payload["p1_operational_queues"]["summary"]["residual_holdout_work_item_count"] == 3
    assert payload["p1_operational_queues"]["summary"]["residual_holdout_open_count"] == 2
    assert payload["p1_operational_queues"]["summary"]["residual_holdout_closure_evidence_attached_count"] == 1
    assert payload["artifacts"]["residual_holdout_closure_updates"] == str(residual_updates)
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
    assert p1_operational.exists()
    assert p1_operational_md.exists()


def test_materialize_clean_checkout_evidence_chain_hydrates_external_submission_from_release_package(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "real_project_corpus_seed_manifest.json"
    p0_status = tmp_path / "published" / "p0-status.json"
    artifact_root = tmp_path / "published" / "hydrated_release_assets"
    evidence_index = tmp_path / "published" / "release-publication-evidence-index.json"
    midas_source = tmp_path / "release_evidence" / "midas" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_source = tmp_path / "release_evidence" / "commercial" / "commercial_readiness_report.json"
    external_submission = tmp_path / "generated" / "external_benchmark_submission_readiness.json"
    external_updates = tmp_path / "generated" / "external_benchmark_submission_updates.json"
    residual_updates = tmp_path / "generated" / "residual_holdout_closure_updates.json"
    midas_target = tmp_path / "generated" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_target = tmp_path / "generated" / "commercial_readiness_report.json"
    coverage = tmp_path / "generated" / "real_project_parser_coverage_matrix.json"
    peer = tmp_path / "generated" / "peer_tbi_benchmark_metric_records.json"
    row_provenance = tmp_path / "generated" / "real_project_row_provenance_report.json"
    p1_status = tmp_path / "generated" / "p1-readiness-status.json"
    p1_breadth = tmp_path / "generated" / "p1-benchmark-breadth-status.json"
    p1_operational = tmp_path / "generated" / "p1-operational-queues" / "p1_operational_queues.json"
    out = tmp_path / "generated" / "clean-checkout-evidence-chain.json"

    _write_json(manifest, _manifest())
    _write_json(p0_status, _p0_status())
    _write_json(
        evidence_index,
        {
            "schema_version": "release-publication-evidence-index.v1",
            "paths": {
                "p0_status_json": str(p0_status),
                "artifact_root": str(artifact_root),
            },
        },
    )
    _write_json(midas_source, _midas_report())
    _write_json(commercial_source, _commercial_report())
    artifact_root.mkdir(parents=True)
    with zipfile.ZipFile(artifact_root / "project_package.zip", "w") as archive:
        archive.writestr(
            "artifacts/external_benchmark_submission_readiness.json",
            json.dumps(_external_submission()),
        )
        archive.writestr(
            "artifacts/external_benchmark_submission_updates.json",
            json.dumps(
                {
                    "schema_version": "external-benchmark-submission-updates.v1",
                    "updates": {
                        "hardest_external_10case": {
                            "receipt_status": "attached",
                            "receipt_url": "https://bench.example.test/receipts/EB-001",
                            "submitted_at_utc": "2026-05-05T05:04:53Z",
                            "closure_evidence_status": "attached",
                            "last_checked_at_utc": "2026-05-05T05:05:53Z",
                        },
                        "tpu_hffb": {
                            "receipt_status": "pending_external_submission_receipt",
                            "closure_evidence_status": "pending",
                            "last_checked_at_utc": "2026-05-05T05:05:53Z",
                        },
                        "peer_spd_hinge": {
                            "receipt_status": "pending_external_submission_receipt",
                            "closure_evidence_status": "pending",
                            "last_checked_at_utc": "2026-05-05T05:05:53Z",
                        },
                        "korean_public_structures": {
                            "receipt_status": "pending_external_submission_receipt",
                            "closure_evidence_status": "pending",
                            "last_checked_at_utc": "2026-05-05T05:05:53Z",
                        },
                    },
                }
            ),
        )
        archive.writestr(
            "artifacts/residual_holdout_closure_updates.json",
            json.dumps(
                {
                    "schema_version": "residual-holdout-closure-updates.v1",
                    "updates": {
                        "RH-001": {
                            "closure_evidence_status": "pending",
                            "last_checked_at_utc": "2026-05-05T05:06:07Z",
                        },
                        "RH-002": {
                            "closure_evidence_path": "release_evidence/productization/RH-002.cross_validation.json",
                            "closure_evidence_status": "attached",
                            "last_checked_at_utc": "2026-05-05T05:06:07Z",
                        },
                        "RH-003": {
                            "closure_evidence_status": "pending",
                            "last_checked_at_utc": "2026-05-05T05:06:07Z",
                        },
                    },
                }
            ),
        )

    proc = subprocess.run(
        [
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
            "--external-benchmark-submission-readiness",
            str(external_submission),
            "--external-benchmark-submission-updates",
            str(external_updates),
            "--residual-holdout-closure-updates",
            str(residual_updates),
            "--p1-readiness-out",
            str(p1_status),
            "--p1-benchmark-out",
            str(p1_breadth),
            "--p1-operational-queues-out",
            str(p1_operational),
            "--json",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert external_submission.exists()
    assert external_updates.exists()
    assert residual_updates.exists()
    external_step = next(
        step for step in payload["steps"] if step["label"] == "external benchmark submission readiness"
    )
    external_updates_step = next(
        step for step in payload["steps"] if step["label"] == "external benchmark submission updates"
    )
    residual_updates_step = next(
        step for step in payload["steps"] if step["label"] == "residual holdout closure updates"
    )
    assert external_step["hydrated_from_source"] is True
    assert external_step["source_evidence"].endswith("project_package.zip")
    assert external_updates_step["hydrated_from_source"] is True
    assert residual_updates_step["hydrated_from_source"] is True
    assert payload["publication_sidecars_pass"] is True
    assert external_updates_step["all_expected_updates_present"] is True
    assert residual_updates_step["all_expected_updates_present"] is True
    assert payload["artifacts"]["external_benchmark_submission_readiness"] == str(external_submission)
    assert payload["artifacts"]["external_benchmark_submission_updates"] == str(external_updates)
    assert payload["artifacts"]["residual_holdout_closure_updates"] == str(residual_updates)
    assert payload["p1_operational_queues"]["summary"]["external_submission_queue_count"] == 4
    assert payload["p1_operational_queues"]["summary"]["external_submission_updates_applied_count"] == 4
    assert payload["p1_operational_queues"]["summary"]["external_submission_receipt_attached_count"] == 1
    assert payload["p1_benchmark_breadth_status"]["summary"]["external_benchmark_submission"][
        "external_benchmark_submission_updates_applied_count"
    ] == 4
    assert payload["p1_benchmark_breadth_status"]["summary"]["external_benchmark_submission"][
        "submission_receipt_attached_count"
    ] == 1
    assert payload["p1_operational_queues"]["summary"]["residual_holdout_closure_evidence_attached_count"] == 1


def test_materialize_clean_checkout_evidence_chain_keeps_contract_blocked_without_p0_closure(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "real_project_corpus_seed_manifest.json"
    midas_source = tmp_path / "release_evidence" / "midas" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_source = tmp_path / "release_evidence" / "commercial" / "commercial_readiness_report.json"
    external_submission = tmp_path / "release_evidence" / "external" / "external_benchmark_submission_readiness.json"
    midas_target = tmp_path / "generated" / "midas_kds_geometry_bridge_validation_report.json"
    commercial_target = tmp_path / "generated" / "commercial_readiness_report.json"
    coverage = tmp_path / "generated" / "real_project_parser_coverage_matrix.json"
    peer = tmp_path / "generated" / "peer_tbi_benchmark_metric_records.json"
    row_provenance = tmp_path / "generated" / "real_project_row_provenance_report.json"
    out = tmp_path / "generated" / "clean-checkout-evidence-chain.json"

    _write_json(manifest, _manifest())
    _write_json(midas_source, _midas_report())
    _write_json(commercial_source, _commercial_report())
    _write_json(external_submission, _external_submission())

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--manifest",
            str(manifest),
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
            "--external-benchmark-submission-readiness",
            str(external_submission),
            "--json",
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["inputs_contract_pass"] is True
    assert payload["contract_pass"] is False
    assert payload["p0_closure_evidence_consumed"] is False
    assert payload["p0_release_blocker"] is True
