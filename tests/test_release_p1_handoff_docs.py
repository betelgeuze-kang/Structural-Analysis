from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_doc(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def test_release_publication_runbook_names_the_p1_quality_slice() -> None:
    text = _read_doc("docs", "release-publication-runbook.md")

    assert "P1 quality/fallback/benchmark breadth" in text
    assert "check_p1_readiness_status.py" in text
    assert "check_p1_benchmark_breadth_status.py" in text
    assert "preview_external_benchmark_submission_after_review_updates.py" in text
    assert "--submission-updates" in text
    assert "materialize_p1_operational_queues.py" in text
    assert "receipt_template.json" in text
    assert "closure_packet_template.json" in text
    assert "residual_holdout_closure_updates.json" in text
    assert "last_checked_at_utc" in text
    assert "full_commercial_replacement_ready=false" in text
    assert "P0-1 is closed" in text


def test_readme_pins_the_current_commercial_scope_and_sidecar_closure() -> None:
    text = _read_doc("README.md")

    assert "Commercial" in text
    assert "engineer_in_loop_accelerated_coverage_ready=true" in text
    assert "full_commercial_replacement_ready=false" in text
    assert "EB receipt stays `0/4`" in text
    assert "RH closure evidence stays pending" in text
    assert "external_benchmark_submission_updates.json" in text
    assert "residual_holdout_closure_updates.json" in text
    assert "report_commercialization_level.py" in text
    assert "not full autonomous replacement" in text


def test_viewer_contract_surfaces_the_p1_handoff_slice() -> None:
    text = _read_doc("docs", "viewer-contract.md")

    assert "P1 quality/fallback/benchmark breadth slice" in text
    assert "check_p1_readiness_status.py" in text
    assert "check_p1_benchmark_breadth_status.py" in text
    assert "external submission receipts" in text
    assert "residual holdout closure packet templates" in text


def test_release_facing_docs_do_not_claim_published_release_is_missing() -> None:
    stale_phrases = [
        "publication is incomplete",
        "not yet published",
        "P0-1 is still open for one reason",
        "release P0-1만 아직 열려 있다",
        "업로드가 아직 완료되지 않았다",
        "overall P0는 아직 open",
    ]
    docs = [
        _read_doc("README.md"),
        _read_doc("docs", "release-publication-runbook.md"),
        _read_doc("docs", "viewer-contract.md"),
        _read_doc("docs", "commercialization-gap-current-state.md"),
        _read_doc("implementation", "phase1", "commercialization-execution-roadmap.md"),
    ]

    for text in docs:
        for phrase in stale_phrases:
            assert phrase not in text


def test_commercialization_gap_report_uses_the_full_p1_slice_name() -> None:
    text = _read_doc("docs", "commercialization-gap-current-state.md")

    assert "P1 quality/fallback/benchmark breadth" in text
    assert "P1 quality/fallback/benchmark breadth 상태" in text
    assert "P1 quality/fallback/benchmark breadth 실행" in text
    assert "preview_external_benchmark_submission_after_review_updates.py" in text
    assert "materialize_p1_operational_queues.py" in text
    assert "receipt_attached=0/4" in text
    assert "residual_holdout_closure_updates.json" in text


def test_release_facing_docs_keep_bounded_commercial_language() -> None:
    docs = [
        _read_doc("README.md"),
        _read_doc("docs", "release-publication-runbook.md"),
        _read_doc("docs", "commercialization-gap-current-state.md"),
    ]

    for text in docs:
        assert "Commercial" in text
        assert "engineer_in_loop_accelerated_coverage_ready=true" in text
        assert "full_commercial_replacement_ready=false" in text
