from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


SCRIPT = Path("implementation/phase1/run_midas_exact_roundtrip_closure_gate.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_gate(
    *,
    native_report: Path,
    interoperability_report: Path,
    diff_receipts_report: Path,
    corpus_manifest: Path,
    out: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--native-roundtrip-report",
            str(native_report),
            "--interoperability-report",
            str(interoperability_report),
            "--diff-receipts-report",
            str(diff_receipts_report),
            "--corpus-manifest",
            str(corpus_manifest),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )


def test_exact_roundtrip_closure_gate_passes_when_all_ready_cases_are_exact(tmp_path: Path) -> None:
    native_report = tmp_path / "native.json"
    interoperability_report = tmp_path / "interop.json"
    diff_receipts_report = tmp_path / "receipts.json"
    corpus_manifest = tmp_path / "manifest.json"
    out = tmp_path / "closure.json"

    _write_json(
        native_report,
        {
            "contract_pass": True,
            "summary_line": "MIDAS native roundtrip: PASS | ready=4 | loadcomb=4/4 exact",
            "summary": {
                "native_writeback_ready_count": 4,
                "pending_review_total": 0,
                "exact_topology_structural_preview_pending_candidate_count": 0,
                "exact_topology_structural_preview_candidate_total": 0,
                "taxonomy_case_counts": {
                    "preserved_exact": 4,
                    "canonical_rewrite": 0,
                    "lossy_rewrite": 0,
                    "unsupported_card": 0,
                    "manual_review_required": 0,
                    "parser_drop_suspected": 0,
                },
            },
        },
    )
    _write_json(
        interoperability_report,
        {
            "contract_pass": True,
            "summary_line": "MIDAS interoperability/export readiness: PASS | roundtrip=3/3",
            "summary": {
                "remaining_limits": [],
                "bounded_subset_mode": "full_exact_roundtrip",
                "roundtrip_exact_entry_row_coverage_min": 1.0,
                "roundtrip_exact_header_coverage_min": 1.0,
                "roundtrip_exact_factor_map_coverage_min": 1.0,
            },
        },
    )
    _write_json(diff_receipts_report, {})
    _write_json(corpus_manifest, {})

    proc = _run_gate(
        native_report=native_report,
        interoperability_report=interoperability_report,
        diff_receipts_report=diff_receipts_report,
        corpus_manifest=corpus_manifest,
        out=out,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["checks"]["all_ready_cases_exact_pass"] is True
    assert payload["checks"]["remaining_limits_zero_pass"] is True
    assert payload["summary"]["exact_case_count"] == 4
    assert payload["summary"]["exact_case_ratio"] == 1.0
    assert payload["summary_line"].startswith("MIDAS exact roundtrip closure: PASS")
    assert "limits=none" in payload["summary_line"]


def test_exact_roundtrip_closure_gate_keeps_real_canonical_blockers_in_scope(tmp_path: Path) -> None:
    native_report = tmp_path / "native.json"
    interoperability_report = tmp_path / "interop.json"
    diff_receipts_report = tmp_path / "receipts.json"
    corpus_manifest = tmp_path / "manifest.json"
    out = tmp_path / "closure.json"

    _write_json(
        native_report,
        {
            "contract_pass": True,
            "summary": {
                "native_writeback_ready_count": 2,
                "pending_review_total": 1,
                "exact_topology_structural_preview_pending_candidate_count": 0,
                "exact_topology_structural_preview_candidate_total": 0,
                "taxonomy_case_counts": {
                    "preserved_exact": 1,
                    "canonical_rewrite": 1,
                    "lossy_rewrite": 0,
                    "unsupported_card": 0,
                    "manual_review_required": 1,
                    "parser_drop_suspected": 0,
                },
            },
        },
    )
    _write_json(
        diff_receipts_report,
        {
            "receipt_rows": [
                {
                    "case_id": "real_exact_case",
                    "review_pending_count": 0,
                    "taxonomy": {
                        "counts": {
                            "preserved_exact": 1,
                            "canonical_rewrite": 0,
                            "lossy_rewrite": 0,
                            "unsupported_card": 0,
                            "manual_review_required": 0,
                            "parser_drop_suspected": 0,
                        }
                    },
                },
                {
                    "case_id": "real_manual_canonical_case",
                    "review_pending_count": 1,
                    "taxonomy": {
                        "counts": {
                            "preserved_exact": 0,
                            "canonical_rewrite": 1,
                            "lossy_rewrite": 0,
                            "unsupported_card": 0,
                            "manual_review_required": 1,
                            "parser_drop_suspected": 0,
                        }
                    },
                },
            ]
        },
    )
    _write_json(
        corpus_manifest,
        {
            "cases": [
                {"case_id": "real_exact_case", "native_writeback_ready": True},
                {
                    "case_id": "real_manual_canonical_case",
                    "native_writeback_ready": True,
                    "role": "native_writeback_public_derived",
                    "source_family": "public_native_text",
                    "writeback_mode": "identity_baseline",
                    "notes": "Real canonical drift that still needs review.",
                },
            ]
        },
    )
    _write_json(
        interoperability_report,
        {
            "contract_pass": True,
            "summary": {
                "remaining_limits": [],
                "bounded_subset_mode": "full_exact_roundtrip",
                "roundtrip_exact_entry_row_coverage_min": 1.0,
                "roundtrip_exact_header_coverage_min": 1.0,
                "roundtrip_exact_factor_map_coverage_min": 1.0,
            },
        },
    )

    proc = _run_gate(
        native_report=native_report,
        interoperability_report=interoperability_report,
        diff_receipts_report=diff_receipts_report,
        corpus_manifest=corpus_manifest,
        out=out,
    )

    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_EXACT_CLOSURE_PENDING"
    assert payload["checks"]["canonical_rewrite_zero_pass"] is False
    assert payload["checks"]["manual_review_zero_pass"] is False
    assert payload["checks"]["exact_queue_zero_pass"] is True
    assert payload["checks"]["remaining_limits_zero_pass"] is True
    assert payload["summary"]["canonical_rewrite_case_count"] == 1
    assert payload["summary"]["closure_scope_excluded_case_count"] == 0
    assert payload["summary_line"].startswith("MIDAS exact roundtrip closure: CHECK")
    assert "canonical=1" in payload["summary_line"]


def test_exact_roundtrip_closure_gate_excludes_optimized_and_parser_drop_scope_only(
    tmp_path: Path,
) -> None:
    native_report = tmp_path / "native.json"
    interoperability_report = tmp_path / "interop.json"
    diff_receipts_report = tmp_path / "receipts.json"
    corpus_manifest = tmp_path / "manifest.json"
    out = tmp_path / "closure.json"

    _write_json(
        native_report,
        {
            "contract_pass": True,
            "summary": {
                "native_writeback_ready_count": 6,
                "pending_review_total": 0,
                "exact_topology_structural_preview_pending_candidate_count": 0,
                "exact_topology_structural_preview_candidate_total": 0,
                "taxonomy_case_counts": {
                    "preserved_exact": 5,
                    "canonical_rewrite": 1,
                    "lossy_rewrite": 0,
                    "unsupported_card": 0,
                    "manual_review_required": 0,
                    "parser_drop_suspected": 1,
                },
            },
        },
    )
    _write_json(
        diff_receipts_report,
        {
            "receipt_rows": [
                {
                    "case_id": "exact_case_a",
                    "review_pending_count": 0,
                    "taxonomy": {"counts": {"preserved_exact": 1}},
                },
                {
                    "case_id": "exact_case_b",
                    "review_pending_count": 0,
                    "taxonomy": {"counts": {"preserved_exact": 1}},
                },
                {
                    "case_id": "exact_case_c",
                    "review_pending_count": 0,
                    "taxonomy": {"counts": {"preserved_exact": 1}},
                },
                {
                    "case_id": "exact_case_d",
                    "review_pending_count": 0,
                    "taxonomy": {"counts": {"preserved_exact": 1}},
                },
                {
                    "case_id": "midas_generator_33_github__optimized_writeback",
                    "review_pending_count": 0,
                    "taxonomy": {
                        "counts": {
                            "preserved_exact": 0,
                            "canonical_rewrite": 1,
                            "parser_drop_suspected": 0,
                        }
                    },
                },
                {
                    "case_id": "fixture_foundation_parser_drop_small__identity_writeback",
                    "review_pending_count": 0,
                    "taxonomy": {
                        "counts": {
                            "preserved_exact": 1,
                            "canonical_rewrite": 0,
                            "parser_drop_suspected": 1,
                        }
                    },
                },
            ]
        },
    )
    _write_json(
        corpus_manifest,
        {
            "cases": [
                {"case_id": "exact_case_a", "native_writeback_ready": True},
                {"case_id": "exact_case_b", "native_writeback_ready": True},
                {"case_id": "exact_case_c", "native_writeback_ready": True},
                {"case_id": "exact_case_d", "native_writeback_ready": True},
                {
                    "case_id": "midas_generator_33_github__optimized_writeback",
                    "role": "native_writeback_public_derived",
                    "source_family": "derived_native_writeback",
                    "provenance_class": "public_derived_writeback",
                    "native_writeback_ready": True,
                    "writeback_mode": "direct_patch_plus_audit_review_manifest",
                    "notes": "Derived native MIDAS write-back candidate tied to the real-source .mgt baseline.",
                    "metrics": {"direct_patch_change_count": 25},
                },
                {
                    "case_id": "fixture_foundation_parser_drop_small__identity_writeback",
                    "role": "native_writeback_fixture_derived",
                    "source_family": "foundation_parser_drop_fixture",
                    "source_class": "mgt_identity_fixture_writeback",
                    "native_writeback_ready": True,
                    "writeback_mode": "fixture_identity_baseline",
                    "notes": "Fixture-native identity/canonical roundtrip baseline for fixture_foundation_parser_drop_small.",
                    "checks": {"fixture_identity_mode": True},
                },
            ]
        },
    )
    _write_json(
        interoperability_report,
        {
            "contract_pass": True,
            "summary": {
                "remaining_limits": [
                    "solver_ready_reconstruction_pending",
                    "primitive_load_cards_pending",
                ],
                "bounded_subset_mode": "editor_seed+raw_recovery+preview_roundtrip",
                "roundtrip_exact_entry_row_coverage_min": 1.0,
                "roundtrip_exact_header_coverage_min": 1.0,
                "roundtrip_exact_factor_map_coverage_min": 1.0,
            },
        },
    )

    proc = _run_gate(
        native_report=native_report,
        interoperability_report=interoperability_report,
        diff_receipts_report=diff_receipts_report,
        corpus_manifest=corpus_manifest,
        out=out,
    )

    assert proc.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_EXACT_CLOSURE_PENDING"
    assert payload["checks"]["all_ready_cases_exact_pass"] is True
    assert payload["checks"]["canonical_rewrite_zero_pass"] is True
    assert payload["checks"]["parser_drop_suspected_zero_pass"] is True
    assert payload["checks"]["remaining_limits_zero_pass"] is False
    assert payload["summary"]["ready_case_count"] == 4
    assert payload["summary"]["exact_case_count"] == 4
    assert payload["summary"]["closure_scope_used_precise_receipts"] is True
    assert payload["summary"]["closure_scope_excluded_case_count"] == 2
    assert payload["summary"]["closure_scope_excluded_case_counts_by_reason"] == {
        "intentional_optimized_writeback": 1,
        "parser_drop_fixture": 1,
    }
    assert payload["summary"]["closure_scope_excluded_case_ids"] == [
        "midas_generator_33_github__optimized_writeback",
        "fixture_foundation_parser_drop_small__identity_writeback",
    ]
    assert "scope_excluded=2" in payload["summary_line"]
