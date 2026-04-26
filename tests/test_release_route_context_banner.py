from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_html_surfaces_include_route_context_banner() -> None:
    viewer_html = (
        ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "visualization"
        / "structural_optimization_viewer.html"
    ).read_text(encoding="utf-8")
    drawing_html = (
        ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "visualization"
        / "optimized_drawing_review.html"
    ).read_text(encoding="utf-8")
    benchmark_html = (
        ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "visualization"
        / "benchmark_optimization_review.html"
    ).read_text(encoding="utf-8")
    committee_html = (
        ROOT
        / "implementation"
        / "phase1"
        / "release"
        / "committee_review"
        / "committee_review_dashboard.html"
    ).read_text(encoding="utf-8")

    for html in (viewer_html, drawing_html, benchmark_html, committee_html):
        assert "route-context-banner" in html
        assert "route-focus-target" in html
        assert "Connected Review Route" in html
        assert "route-context-title" in html
        assert "route-context-return" in html
        assert "route_title" in html
        assert "review_mode" in html
        assert "route_focus" in html
        assert "return_to" in html
        assert "return_label" in html
        assert "target_surface" in html
        assert "selection_status" in html
        assert "Structural Optimization Workbench" in html

    assert "viewer-interactive-3d" in viewer_html
    assert "viewer-results-explorer" in viewer_html
    assert "results_card" in viewer_html
    assert "results_companion" in viewer_html
    assert "results_detail_block" in viewer_html
    assert "codecheck_surface" in viewer_html
    assert "codecheck_detail_block" in viewer_html
    assert "codecheck_appendix_block" in viewer_html
    assert "route-selection-target" in drawing_html
    assert "drawing-member-review" in drawing_html
    assert "drawing-what-changed" in drawing_html
    assert "route_member_id" in drawing_html
    assert "route_story_band" in drawing_html
    assert "route_diff_index" in drawing_html
    assert "route_diff_row_id" in drawing_html
    assert "peer-benchmark" in benchmark_html
    assert "benchmark-peer-summary" in benchmark_html
    assert "route-selection-target" in benchmark_html
    assert "route_benchmark_family" in benchmark_html
    assert "route_projection" in benchmark_html
    assert "route_case_id" in benchmark_html
    assert "data-route-benchmark-family='peer'" in benchmark_html
    assert "committee-validation-table" in committee_html
    assert "committee-authority-benchmark" in committee_html
    assert "committee-authority-table" in committee_html
    assert "committee-selected-candidates" in committee_html
    assert "committee-design-change-table" in committee_html
    assert "committee-appendix-row-provenance" in committee_html
    assert "committee-appendix-native-roundtrip" in committee_html
    assert "committee-appendix-irregular-structure" in committee_html
    assert "Open Viewer Row" in committee_html
    assert "Open Viewer Slice" in committee_html
    assert "route-selection-target" in committee_html
    assert "route_track" in committee_html
    assert "route_candidate_id" in committee_html
    assert "route_appendix_block" in committee_html
    assert "route_combination_name" in committee_html
    assert "route_clause_label" in committee_html
    assert "route_hazard_type" in committee_html
    assert "route_rule_family" in committee_html


def test_generator_sources_emit_route_context_banner_contract() -> None:
    helper_source = (
        ROOT / "implementation" / "phase1" / "ui_layout_fragments.py"
    ).read_text(encoding="utf-8")
    viewer_generator = (
        ROOT / "implementation" / "phase1" / "generate_structural_optimization_visualization_viewer.py"
    ).read_text(encoding="utf-8")
    drawing_generator = (
        ROOT / "implementation" / "phase1" / "generate_optimized_drawing_review_ui.py"
    ).read_text(encoding="utf-8")
    benchmark_generator = (
        ROOT / "implementation" / "phase1" / "generate_benchmark_optimization_review_ui.py"
    ).read_text(encoding="utf-8")
    committee_generator = (
        ROOT / "implementation" / "phase1" / "generate_committee_review_package.py"
    ).read_text(encoding="utf-8")

    assert "route-context-banner" in helper_source
    assert "Connected Review Route" in helper_source
    assert "route-context-title" in helper_source
    assert "route-context-return" in helper_source
    assert "render_token_row" in helper_source
    assert "render_link_pills" in helper_source

    for source in (viewer_generator, drawing_generator, benchmark_generator, committee_generator):
        assert "render_route_context_banner" in source
        assert "route-focus-target" in source
        assert "route_title" in source
        assert "review_mode" in source
        assert "route_focus" in source
        assert "return_to" in source
        assert "return_label" in source
        assert "target_surface" in source
        assert "selection_status" in source

    assert "viewer-interactive-3d" in viewer_generator
    assert "render_token_row" in viewer_generator
    assert "render_link_pills" in viewer_generator
    assert "render_split_hero" in viewer_generator
    assert "results_card" in viewer_generator
    assert "results_companion" in viewer_generator
    assert "results_detail_block" in viewer_generator
    assert "codecheck_surface" in viewer_generator
    assert "codecheck_detail_block" in viewer_generator
    assert "codecheck_appendix_block" in viewer_generator
    assert "render_token_row" in drawing_generator
    assert "render_link_pills" in drawing_generator
    assert "render_split_hero" in drawing_generator
    assert "route-selection-target" in drawing_generator
    assert "drawing-member-review" in drawing_generator
    assert "route_member_id" in drawing_generator
    assert "route_story_band" in drawing_generator
    assert "route_diff_index" in drawing_generator
    assert "route_diff_row_id" in drawing_generator
    assert "peer-benchmark" in benchmark_generator
    assert "render_token_row" in benchmark_generator
    assert "render_link_pills" in benchmark_generator
    assert "render_split_hero" in benchmark_generator
    assert "route-selection-target" in benchmark_generator
    assert "route_benchmark_family" in benchmark_generator
    assert "route_projection" in benchmark_generator
    assert "route_case_id" in benchmark_generator
    assert "data-route-benchmark-family='peer'" in benchmark_generator
    assert "committee-validation-table" in committee_generator
    assert "committee-authority-table" in committee_generator
    assert "committee-selected-candidates" in committee_generator
    assert "committee-design-change-table" in committee_generator
    assert "committee-appendix-row-provenance" in committee_generator
    assert "committee-appendix-native-roundtrip" in committee_generator
    assert "committee-appendix-irregular-structure" in committee_generator
    assert "Open Viewer Row" in committee_generator
    assert "Open Viewer Slice" in committee_generator
    assert "data-authority-row=\"true\"" in committee_generator
    assert "data-candidate-row=\"true\"" in committee_generator
    assert "data-design-change-row=\"true\"" in committee_generator
    assert "route_track" in committee_generator
    assert "route_candidate_id" in committee_generator
    assert "route_appendix_block" in committee_generator
    assert "route_combination_name" in committee_generator
    assert "route_clause_label" in committee_generator
    assert "route_hazard_type" in committee_generator
    assert "route_rule_family" in committee_generator
