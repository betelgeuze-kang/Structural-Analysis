from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "implementation/phase1/structural_svg_generator.py"
SPEC = importlib.util.spec_from_file_location("structural_svg_generator", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
StructuralSVGGenerator = MODULE.StructuralSVGGenerator


def _build_tight_grid_model() -> dict:
    nodes = []
    nid = 1
    grid_x = [0.0, 0.25, 0.5, 0.75]
    grid_y = [0.0, 0.2, 0.4, 0.6]
    stories = [0.0, 0.5, 1.0, 1.5]
    for z in stories:
        for x in grid_x:
            for y in grid_y:
                nodes.append({"id": nid, "x": x, "y": y, "z": z})
                nid += 1
    return {
        "nodes": nodes,
        "elements": [
            {"id": 1, "type": "beam", "node_ids": [17, 21], "section": "H-400", "dcr": 0.82},
            {"id": 2, "type": "beam", "node_ids": [21, 25], "section": "H-400", "dcr": 0.77},
            {"id": 3, "type": "beam", "node_ids": [25, 29], "section": "H-400", "dcr": 0.73},
            {"id": 4, "type": "column", "node_ids": [1, 17], "section": "C-450", "dcr": 0.64},
            {"id": 5, "type": "column", "node_ids": [2, 18], "section": "C-450", "dcr": 0.59},
        ],
        "meta": {
            "name": "Atlas Tower",
            "title_block": {
                "project": "Atlas Permit Review",
                "revision": "R2",
                "status": "REVIEW",
                "issued_by": "Unit Test",
            },
        },
    }


def _build_tight_story_model() -> dict:
    nodes = []
    nid = 1
    grid_x = [0.0, 0.5]
    grid_y = [0.0, 0.5]
    stories = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    for z in stories:
        for x in grid_x:
            for y in grid_y:
                nodes.append({"id": nid, "x": x, "y": y, "z": z})
                nid += 1
    elements = []
    for i in range(len(stories) - 1):
        elements.append({"id": i + 1, "type": "column", "node_ids": [i * 4 + 1, (i + 1) * 4 + 1], "dcr": 0.5})
    return {
        "nodes": nodes,
        "elements": elements,
        "meta": {"name": "Story Stack"},
    }


def _build_sheet_callout_model() -> dict:
    model = _build_tight_grid_model()
    title_block = model["meta"]["title_block"]
    title_block.update(
        {
            "sheet_set": "Permit Set",
            "sheet_index": 2,
            "sheet_total": 6,
            "revision_status": "Issued for review",
            "date": "2026-04-14",
        }
    )
    model["meta"]["revision_history"] = [
        {"revision": "R1", "status": "For Comment", "date": "2026-04-01"},
    ]
    model["meta"]["callouts"] = [
        {
            "member_id": 1,
            "sheet_key": "plan_z0.5",
            "label": "Reduce beam demand",
            "note": "Check governing span",
            "priority": 2,
        },
        {
            "member_id": 2,
            "sheet_key": "plan_z0.5",
            "label": "Coordinate splice",
            "note": "Confirm peer review route",
            "priority": 1,
        },
        {
            "member_id": 4,
            "view": "iso",
            "label": "Column transfer review",
            "note": "Follow linked 3D member focus",
            "tone": "review",
        },
    ]
    return model


def test_plan_and_isometric_render_title_block_metadata():
    generator = StructuralSVGGenerator(_build_tight_grid_model())

    plan_svg = generator.plan_view(story_z=0.5, width=420, height=280)
    iso_svg = generator.isometric_view(width=420, height=320)

    assert "class='title-block'" in plan_svg
    assert "Atlas Permit Review" in plan_svg
    assert "PLAN-Z0.5" in plan_svg
    assert "R2" in plan_svg
    assert "REVIEW" in plan_svg

    assert "class='title-block'" in iso_svg
    assert "data-sheet-code='ISO'" in iso_svg
    assert "Atlas Permit Review" in iso_svg


def test_svg_sheet_revision_and_callout_contract():
    generator = StructuralSVGGenerator(_build_sheet_callout_model())

    plan_svg = generator.plan_view(story_z=0.5, width=420, height=280)
    iso_svg = generator.isometric_view(width=420, height=320)

    assert "data-sheet-set='Permit Set'" in plan_svg
    assert "data-sheet-index='2'" in plan_svg
    assert "data-sheet-total='6'" in plan_svg
    assert "data-sheet-register='Permit Set | SHEET PLAN-Z0.5 / 6'" in plan_svg
    assert "data-revision-code='R2'" in plan_svg
    assert "data-revision-status='Issued for review'" in plan_svg
    assert "data-revision-date='2026-04-14'" in plan_svg
    assert "Permit Set | SHEET PLAN-Z0.5 / 6 · 2026-04-14" in plan_svg
    assert "R1 · For Comment · 2026-04-01" in plan_svg

    assert "class='member-callout'" in plan_svg
    assert "class='member-link member-callout-link'" in plan_svg
    assert "data-callout-sheet='plan_z0.5'" in plan_svg
    assert "data-callout-member-id='1'" in plan_svg
    assert "Reduce beam demand" in plan_svg
    assert "Check governing span" in plan_svg
    callout_lanes = [int(match) for match in re.findall(r"class='member-callout'[^>]*data-callout-lane='(\d+)'", plan_svg)]
    assert callout_lanes
    assert max(callout_lanes) >= 1

    assert "data-sheet-register='Permit Set | SHEET ISO / 6'" in iso_svg
    assert "data-callout-member-id='4'" in iso_svg
    assert "Column transfer review" in iso_svg
    assert "Follow linked 3D member focus" in iso_svg


def test_dimension_labels_use_multiple_lanes_when_spacing_is_tight():
    generator = StructuralSVGGenerator(_build_tight_grid_model())
    elevation_generator = StructuralSVGGenerator(_build_tight_story_model())

    plan_svg = generator.plan_view(story_z=0.5, width=180, height=260)
    elevation_svg = elevation_generator.elevation_view(axis="x", width=360, height=160)

    plan_lanes = [int(match) for match in re.findall(r"data-dim-axis='x' data-dim-lane='(\d+)'", plan_svg)]
    elevation_lanes = [int(match) for match in re.findall(r"data-dim-axis='z' data-dim-lane='(\d+)'", elevation_svg)]

    assert plan_lanes
    assert elevation_lanes
    assert max(plan_lanes) >= 1
    assert max(elevation_lanes) >= 1
    assert "class='dimension-label dimension-label-y'" in plan_svg
    assert "class='dimension-label dimension-label-z'" in elevation_svg


def test_svg_drawings_embed_member_deep_links_and_query_highlight_contract():
    generator = StructuralSVGGenerator(_build_tight_grid_model())

    plan_svg = generator.plan_view(story_z=0.5, width=420, height=280)
    iso_svg = generator.isometric_view(width=420, height=320)

    assert "data-viewer-base-url='../../../src/structure-viewer/index.html'" in plan_svg
    assert "data-sheet-key='plan_z0.5'" in plan_svg
    assert "class='member-link'" in plan_svg
    assert "data-viewer-member-id='1'" in plan_svg
    assert "drawing_sheet=plan_z0.5" in plan_svg
    assert "svg-review-toolbar" in plan_svg
    assert "Open 3D Viewer" in plan_svg
    assert "node.classList.toggle('is-active'" in plan_svg
    assert "drawing_view=Plan+View" in plan_svg

    assert "data-sheet-key='isometric'" in iso_svg
    assert "drawing_sheet=isometric" in iso_svg
