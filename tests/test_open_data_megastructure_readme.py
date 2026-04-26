from __future__ import annotations

from pathlib import Path


def test_megastructure_readme_mentions_family_and_row_provenance_sync() -> None:
    readme = (
        Path(__file__).resolve().parents[1]
        / "implementation"
        / "phase1"
        / "open_data"
        / "megastructure"
        / "README.md"
    )
    text = readme.read_text(encoding="utf-8")

    assert "Constitutive/interaction families" in text
    assert "expanded constitutive/interaction families" in text
    assert "Row-provenance sync" in text
    assert "row-provenance appendix" in text
    assert "bidirectionally aligned" in text
    assert "explicit `viewer_row_url` / `viewer_slice_url` reverse-sync links" in text
    assert "viewer_row_url" in text
    assert "viewer_slice_url" in text
