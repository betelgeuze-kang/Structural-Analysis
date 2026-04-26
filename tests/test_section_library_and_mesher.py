from __future__ import annotations

import json
from pathlib import Path

from implementation.phase1.section_library_and_mesher import (
    AuthoringModelDraft,
    LoadPatternDraft,
    LoadPrimitive,
    MemberDraft,
    MeshRefinementPoint,
    MeshRequest,
    NodeDraft,
    SectionTemplate,
    StoryLevel,
    build_authoring_bundle_summary,
    build_default_section_catalog,
    build_load_pattern_summary,
    export_scaffold_summary,
    load_section_catalog,
    validate_mesh_request,
)


def test_validate_mesh_request_and_export_summary() -> None:
    catalog = build_default_section_catalog()
    request = MeshRequest(
        request_id="mesh-001",
        section_id="rc_wall_300x3000",
        element_kind="shell",
        target_edge_length_m=0.25,
        minimum_divisions=3,
        refinement_points=(MeshRefinementPoint(0.5, 0.2),),
    )
    plan = validate_mesh_request(catalog=catalog, request=request)
    assert plan.section_id == "rc_wall_300x3000"
    assert plan.element_kind == "shell"
    assert plan.divisions_long >= 12
    assert plan.local_refinement_count == 1

    pattern = LoadPatternDraft(
        pattern_id="lp-gravity",
        label="Gravity + facade pressure",
        design_situation="ULS",
        primitives=(
            LoadPrimitive("self_weight", "D", "global", 1.0, direction="gravity"),
            LoadPrimitive("surface_pressure", "W+", "zone:facade_east", 2.4, direction="global_x"),
        ),
        tags=("gravity", "wind"),
    )
    payload = export_scaffold_summary(catalog=catalog, mesh_requests=(request,), load_patterns=(pattern,))
    assert payload["catalog"]["template_count"] >= 6
    assert payload["mesh_plan_summaries"][0]["estimated_cell_count"] >= plan.estimated_cell_count
    assert payload["load_pattern_summary"]["primitive_kind_counts"]["self_weight"] == 1
    assert payload["load_pattern_summary"]["case_counts"]["W+"] == 1


def test_load_section_catalog_from_json_payload(tmp_path: Path) -> None:
    payload = {
        "version": "0.1.1",
        "source_label": "unit-test",
        "templates": [
            SectionTemplate(
                section_id="steel_box_500x500x20",
                family="steel",
                shape="box",
                material_grade="SM570",
                dimensions_m={"width_m": 0.5, "depth_m": 0.5, "thickness_m": 0.02},
                default_mesh_size_m=0.05,
                placeholder_analysis_kind="frame_shell_hybrid",
                tags=("column",),
            ).to_payload()
        ],
    }
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    catalog = load_section_catalog(catalog_path)
    assert catalog.version == "0.1.1"
    assert catalog.source_label == "unit-test"
    assert catalog.template_ids() == ("steel_box_500x500x20",)

    summary = build_load_pattern_summary(
        (
            LoadPatternDraft(
                pattern_id="lp-temp",
                label="Thermal preload",
                design_situation="service",
                primitives=(LoadPrimitive("temperature", "TEMP", "member:girder_01", 12.0),),
            ),
        )
    )
    assert summary["pattern_count"] == 1
    assert summary["primitive_kind_counts"] == {"temperature": 1}


def test_authoring_bundle_summary_surfaces_solver_ready_contract() -> None:
    catalog = build_default_section_catalog()
    model = AuthoringModelDraft(
        model_id="tower-a",
        story_levels=(
            StoryLevel("L1", elevation_m=0.0, height_m=4.0),
            StoryLevel("L2", elevation_m=4.0, height_m=4.0),
        ),
        nodes=(
            NodeDraft("N1", 0.0, 0.0, 0.0, story_id="L1"),
            NodeDraft("N2", 6.0, 0.0, 0.0, story_id="L1"),
            NodeDraft("N3", 0.0, 0.0, 4.0, story_id="L2"),
            NodeDraft("N4", 6.0, 0.0, 4.0, story_id="L2"),
        ),
        members=(
            MemberDraft("C1", "column", "N1", "N3", "rc_column_700x700", analysis_kind="fiber_section"),
            MemberDraft("C2", "column", "N2", "N4", "rc_column_700x700", analysis_kind="fiber_section"),
            MemberDraft("B1", "beam", "N3", "N4", "steel_h_600x200", analysis_kind="frame"),
        ),
        load_patterns=(
            LoadPatternDraft(
                pattern_id="lp-gravity",
                label="Gravity",
                design_situation="ULS",
                primitives=(LoadPrimitive("self_weight", "D", "global", 1.0),),
            ),
        ),
    )

    summary = build_authoring_bundle_summary(catalog=catalog, model=model)
    assert summary.native_authoring_ready is True
    assert summary.story_count == 2
    assert summary.node_count == 4
    assert summary.member_count == 3
    assert summary.section_usage_counts == {"rc_column_700x700": 2, "steel_h_600x200": 1}
    assert summary.member_type_counts == {"beam": 1, "column": 2}
    assert summary.max_member_span_m == 6.0
    assert summary.solver_ready_score > 95.0

    payload = export_scaffold_summary(catalog=catalog, authoring_model=model)
    assert payload["authoring_model_summary"]["native_authoring_ready"] is True
    assert payload["authoring_model_summary"]["load_pattern_count"] == 1


def test_authoring_bundle_summary_flags_unsupported_sections_and_node_refs() -> None:
    catalog = build_default_section_catalog()
    model = AuthoringModelDraft(
        model_id="tower-b",
        story_levels=(StoryLevel("L1", elevation_m=0.0, height_m=4.0),),
        nodes=(NodeDraft("N1", 0.0, 0.0, 0.0, story_id="MISSING"),),
        members=(
            MemberDraft("B1", "beam", "N1", "N2", "unknown_section"),
        ),
    )

    summary = build_authoring_bundle_summary(catalog=catalog, model=model)
    assert summary.native_authoring_ready is False
    assert summary.unsupported_section_ids == ("unknown_section",)
    assert summary.unresolved_node_refs == ("B1",)
    assert summary.orphan_story_node_count == 1
    assert summary.solver_ready_score < 70.0
