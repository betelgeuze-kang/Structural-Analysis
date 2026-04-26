from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/run_midas_native_roundtrip_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_gate(corpus_manifest: Path, diff_receipts: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--corpus-manifest",
            str(corpus_manifest),
            "--diff-receipts-report",
            str(diff_receipts),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_midas_native_roundtrip_gate_passes_with_single_ready_case(tmp_path: Path) -> None:
    corpus_manifest = tmp_path / "midas_native_corpus_manifest.json"
    diff_receipts = tmp_path / "midas_native_writeback_diff_receipts_report.json"
    out = tmp_path / "midas_native_roundtrip_gate_report.json"
    exact_queue_json = tmp_path / "exact_topology_structural_preview_promotion_queue.json"
    exact_queue_md = tmp_path / "exact_topology_structural_preview_promotion_queue.md"
    exact_queue_json.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-07T00:00:00Z",
                "summary": {
                    "candidate_total": 4,
                    "pending_candidate_count": 1,
                    "promoted_candidate_count": 3,
                    "public_archive_promoted_candidate_count": 3,
                    "korean_candidate_total": 1,
                    "korean_pending_candidate_count": 1,
                    "state": "open",
                },
                "pending_candidate_rows": [
                    {"source_id": "ifc_public_award_structure", "candidate_origin": "korean_source_catalog"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    exact_queue_md.write_text("# queue\n", encoding="utf-8")

    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "summary": {
                "corpus_case_count": 8,
                "actual_source_count": 6,
                "quality_actual_source_count": 5,
                "public_raw_actual_source_count": 1,
                "native_text_case_count": 4,
                "public_native_text_case_count": 2,
                "public_raw_native_text_case_count": 1,
                "public_bridge_text_case_count": 1,
                "public_archive_preview_text_case_count": 1,
                "public_archive_structural_preview_text_case_count": 1,
                "fixture_native_text_case_count": 1,
                "archive_case_count": 4,
                "native_writeback_ready_count": 4,
                "public_native_writeback_ready_count": 2,
                "public_raw_native_writeback_ready_count": 1,
                "public_bridge_writeback_ready_count": 1,
                "public_archive_preview_writeback_ready_count": 1,
                "public_archive_structural_preview_writeback_ready_count": 1,
                "public_source_writeback_ready_count": 4,
                "fixture_native_writeback_ready_count": 1,
                "korean_source_catalog_record_count": 4,
                "korean_source_catalog_exact_topology_candidate_count": 1,
                "korean_solver_ready_reconstruction_candidate_count": 1,
                "korean_solver_ready_reconstruction_prepared_count": 0,
                "source_family_count": 2,
                "structure_type_count": 3,
            },
        },
    )
    _write_json(
        diff_receipts,
        {
            "contract_pass": True,
            "summary": {
                "ready_case_count": 4,
                "receipt_count": 4,
                "receipt_pass_count": 4,
                "topology_stable_case_count": 4,
                "load_contract_stable_case_count": 4,
                "loadcomb_exact_case_count": 4,
                "unknown_rows_zero_case_count": 4,
                "pending_review_total": 2,
                "exact_topology_structural_preview_candidate_total": 4,
                "exact_topology_structural_preview_pending_candidate_count": 1,
                "exact_topology_structural_preview_public_archive_promoted_candidate_count": 3,
                "exact_topology_structural_preview_korean_candidate_total": 1,
                "exact_topology_structural_preview_korean_pending_candidate_count": 1,
                "korean_structural_preview_promotion_receipt_count": 1,
                "structure_type_batch_count": 2,
                "taxonomy_case_counts": {
                    "preserved_exact": 3,
                    "canonical_rewrite": 1,
                    "lossy_rewrite": 0,
                    "unsupported_card": 0,
                    "manual_review_required": 1,
                    "parser_drop_suspected": 0,
                },
                "taxonomy_card_family_histogram": {
                    "supported_action_families": {"beam_section": 1},
                    "direct_patch_action_families": {"beam_section": 1},
                    "audit_only_action_families": {},
                    "audit_manifest_action_families": {},
                    "unsupported_reason_counts": {},
                },
            },
            "structure_type_batches": [
                {"batch_markdown": str(tmp_path / "beam.diff_batch.md")},
                {"batch_markdown": str(tmp_path / "building.diff_batch.md")},
            ],
            "unsupported_lossy_card_family_appendix_markdown": str(
                tmp_path / "unsupported_lossy_card_family_appendix.md"
            ),
            "unsupported_lossy_card_family_appendix_json": str(
                tmp_path / "unsupported_lossy_card_family_appendix.json"
            ),
            "exact_topology_structural_preview_promotion_queue_json": str(exact_queue_json),
            "exact_topology_structural_preview_promotion_queue_markdown": str(exact_queue_md),
            "exact_topology_structural_preview_pending_candidate_rows": [
                {"source_id": "ifc_public_award_structure", "candidate_origin": "korean_source_catalog"}
            ],
            "korean_structural_preview_promotion_receipt_rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "structural_preview_case_id": "ifc_public_award_structure__structural_preview_candidate",
                    "promotion_receipt_json": str(
                        tmp_path / "ifc_public_award_structure.structural_preview_promotion_receipt.json"
                    ),
                }
            ],
        },
    )

    proc = _run_gate(corpus_manifest, diff_receipts, out)

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["receipt_count"] == 4
    assert payload["summary"]["public_source_writeback_ready_count"] == 4
    assert payload["summary"]["public_raw_native_text_case_count"] == 1
    assert payload["summary"]["public_raw_native_writeback_ready_count"] == 1
    assert payload["summary"]["public_bridge_writeback_ready_count"] == 1
    assert payload["summary"]["public_archive_structural_preview_writeback_ready_count"] == 1
    assert payload["summary"]["exact_topology_structural_preview_pending_candidate_count"] == 1
    assert payload["summary"]["exact_topology_structural_preview_promoted_candidate_count"] == 3
    assert payload["summary"]["exact_topology_structural_preview_candidate_closure_ratio"] == 0.75
    assert payload["summary"]["exact_topology_structural_preview_korean_candidate_total"] == 1
    assert payload["summary"]["korean_exact_topology_promoted_candidate_count"] == 0
    assert payload["summary"]["korean_exact_topology_candidate_closure_ratio"] == 0.0
    assert payload["summary"]["korean_structural_preview_promotion_receipt_count"] == 1
    assert payload["summary"]["korean_solver_ready_reconstruction_candidate_count"] == 1
    assert payload["summary"]["korean_solver_ready_reconstruction_prepared_count"] == 0
    assert payload["summary"]["korean_solver_ready_reconstruction_gap_count"] == 1
    assert payload["summary"]["native_writeback_ready_gap_count"] == 0
    assert payload["summary"]["receipt_pass_gap_count"] == 0
    assert payload["summary"]["loadcomb_exact_gap_count"] == 0
    assert payload["summary"]["native_writeback_ready_coverage_ratio"] == 1.0
    assert payload["summary"]["public_source_writeback_ready_coverage_ratio"] == 1.0
    assert payload["summary"]["loadcomb_exact_roundtrip_coverage_ratio"] == 1.0
    assert payload["summary"]["korean_solver_ready_reconstruction_prepared_ratio"] == 0.0
    assert payload["summary"]["exact_topology_structural_preview_promotion_queue_json"].endswith(
        "exact_topology_structural_preview_promotion_queue.json"
    )
    assert payload["checks"]["public_source_writeback_ready_pass"] is True
    assert payload["checks"]["loadcomb_exact_roundtrip_pass"] is True
    assert payload["checks"]["exact_topology_structural_preview_queue_present_pass"] is True
    assert payload["checks"]["exact_topology_structural_preview_queue_summary_aligned_pass"] is True
    assert payload["checks"]["exact_topology_structural_preview_queue_rows_aligned_pass"] is True
    assert payload["checks"]["korean_exact_topology_candidates_accounted_pass"] is True
    assert payload["checks"]["korean_structural_preview_promotion_receipts_present_pass"] is True
    assert payload["checks"]["korean_structural_preview_promotion_receipt_rows_aligned_pass"] is True
    assert "exact_queue=1/4" in payload["summary_line"]
    assert "korean_reconstruction=0/1" in payload["summary_line"]
    assert "korean_promotions=1/1" in payload["summary_line"]
    assert "coverage=ready:100%,receipts:100%,loadcomb:100%,public_source:100%,exact_queue:75%,kr_recon:0%" in payload[
        "summary_line"
    ]
    assert "gaps=ready:0,receipts:0,topology:0,load:0,loadcomb:0,public_source:0,exact_queue:1,korean_reconstruction:1" in payload[
        "summary_line"
    ]


def test_run_midas_native_roundtrip_gate_fails_when_exact_queue_summary_drift_is_detected(tmp_path: Path) -> None:
    corpus_manifest = tmp_path / "midas_native_corpus_manifest.json"
    diff_receipts = tmp_path / "midas_native_writeback_diff_receipts_report.json"
    out = tmp_path / "midas_native_roundtrip_gate_report.json"
    exact_queue_json = tmp_path / "exact_topology_structural_preview_promotion_queue.json"
    exact_queue_md = tmp_path / "exact_topology_structural_preview_promotion_queue.md"
    exact_queue_json.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-07T00:00:00Z",
                "summary": {
                    "candidate_total": 4,
                    "pending_candidate_count": 2,
                    "promoted_candidate_count": 2,
                    "public_archive_promoted_candidate_count": 2,
                    "korean_candidate_total": 1,
                    "korean_pending_candidate_count": 1,
                    "state": "open",
                },
                "pending_candidate_rows": [
                    {"source_id": "ifc_public_award_structure", "candidate_origin": "korean_source_catalog"},
                    {"source_id": "ifc_public_other_structure", "candidate_origin": "korean_source_catalog"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    exact_queue_md.write_text("# queue\n", encoding="utf-8")

    _write_json(
        corpus_manifest,
        {
            "contract_pass": True,
            "summary": {
                "corpus_case_count": 8,
                "actual_source_count": 6,
                "quality_actual_source_count": 5,
                "public_raw_actual_source_count": 1,
                "native_text_case_count": 4,
                "public_native_text_case_count": 2,
                "public_raw_native_text_case_count": 1,
                "public_bridge_text_case_count": 1,
                "public_archive_preview_text_case_count": 1,
                "public_archive_structural_preview_text_case_count": 1,
                "fixture_native_text_case_count": 1,
                "archive_case_count": 4,
                "native_writeback_ready_count": 4,
                "public_native_writeback_ready_count": 2,
                "public_raw_native_writeback_ready_count": 1,
                "public_bridge_writeback_ready_count": 1,
                "public_archive_preview_writeback_ready_count": 1,
                "public_archive_structural_preview_writeback_ready_count": 1,
                "public_source_writeback_ready_count": 4,
                "fixture_native_writeback_ready_count": 1,
                "korean_source_catalog_record_count": 4,
                "korean_source_catalog_exact_topology_candidate_count": 1,
                "korean_solver_ready_reconstruction_candidate_count": 1,
                "korean_solver_ready_reconstruction_prepared_count": 0,
                "source_family_count": 2,
                "structure_type_count": 3,
            },
        },
    )
    _write_json(
        diff_receipts,
        {
            "contract_pass": True,
            "summary": {
                "ready_case_count": 4,
                "receipt_count": 4,
                "receipt_pass_count": 4,
                "topology_stable_case_count": 4,
                "load_contract_stable_case_count": 4,
                "loadcomb_exact_case_count": 4,
                "unknown_rows_zero_case_count": 4,
                "pending_review_total": 2,
                "exact_topology_structural_preview_candidate_total": 4,
                "exact_topology_structural_preview_pending_candidate_count": 1,
                "exact_topology_structural_preview_public_archive_promoted_candidate_count": 3,
                "exact_topology_structural_preview_korean_candidate_total": 1,
                "exact_topology_structural_preview_korean_pending_candidate_count": 1,
                "korean_structural_preview_promotion_receipt_count": 1,
                "structure_type_batch_count": 2,
                "taxonomy_case_counts": {
                    "preserved_exact": 3,
                    "canonical_rewrite": 1,
                    "lossy_rewrite": 0,
                    "unsupported_card": 0,
                    "manual_review_required": 1,
                    "parser_drop_suspected": 0,
                },
                "taxonomy_card_family_histogram": {
                    "supported_action_families": {"beam_section": 1},
                    "direct_patch_action_families": {"beam_section": 1},
                    "audit_only_action_families": {},
                    "audit_manifest_action_families": {},
                    "unsupported_reason_counts": {},
                },
            },
            "structure_type_batches": [
                {"batch_markdown": str(tmp_path / "beam.diff_batch.md")},
                {"batch_markdown": str(tmp_path / "building.diff_batch.md")},
            ],
            "unsupported_lossy_card_family_appendix_markdown": str(
                tmp_path / "unsupported_lossy_card_family_appendix.md"
            ),
            "unsupported_lossy_card_family_appendix_json": str(
                tmp_path / "unsupported_lossy_card_family_appendix.json"
            ),
            "exact_topology_structural_preview_promotion_queue_json": str(exact_queue_json),
            "exact_topology_structural_preview_promotion_queue_markdown": str(exact_queue_md),
            "exact_topology_structural_preview_pending_candidate_rows": [
                {"source_id": "ifc_public_award_structure", "candidate_origin": "korean_source_catalog"}
            ],
            "korean_structural_preview_promotion_receipt_rows": [
                {
                    "source_id": "ifc_public_award_structure",
                    "structural_preview_case_id": "ifc_public_award_structure__structural_preview_candidate",
                    "promotion_receipt_json": str(
                        tmp_path / "ifc_public_award_structure.structural_preview_promotion_receipt.json"
                    ),
                }
            ],
        },
    )

    proc = _run_gate(corpus_manifest, diff_receipts, out)

    assert proc.returncode == 1
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_WRITEBACK"
    assert payload["checks"]["exact_topology_structural_preview_queue_present_pass"] is True
    assert payload["checks"]["exact_topology_structural_preview_queue_summary_aligned_pass"] is False
    assert payload["checks"]["exact_topology_structural_preview_queue_rows_aligned_pass"] is False
