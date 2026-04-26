from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/parse_midas_mgt_to_json_npz.py"
    )
    spec = importlib.util.spec_from_file_location("parse_midas_module_for_axis_tests", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_derive_named_axis_refs_from_sections_recovers_labeled_refs() -> None:
    module = _load_module()
    axis_refs = module._derive_named_axis_refs_from_sections(
        {
            "GRID-X": ["A, 0.0", "B, 8.0"],
            "GRID-Y": ["1, 0.0", "2, 6.0"],
            "LEVEL": ["B2, -6.0", "L1, 0.0", "L2, 3.6"],
            "STORY-ECCEN": ["YES, NO, 5, 15"],
        }
    )

    assert [row["label"] for row in axis_refs["x"]] == ["A", "B"]
    assert [row["label"] for row in axis_refs["y"]] == ["1", "2"]
    assert [row["label"] for row in axis_refs["z"]] == ["B2", "L1", "L2"]


def test_curated_mgt_fixture_exposes_named_axis_refs() -> None:
    module = _load_module()
    fixture = (
        Path(__file__).resolve().parents[1]
        / "implementation/phase1/open_data/midas/curated/midas_axis_named_reference_case.mgt"
    )
    sections, _, _ = module._parse_sections(fixture)
    axis_refs = module._derive_named_axis_refs_from_sections(sections)

    assert [row["label"] for row in axis_refs["x"]] == ["A", "B", "C"]
    assert [row["label"] for row in axis_refs["y"]] == ["1", "2"]
    assert [row["label"] for row in axis_refs["z"]] == ["L1", "L2"]
