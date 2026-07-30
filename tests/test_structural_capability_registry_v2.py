from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = (
    ROOT
    / "validation"
    / "capabilities"
    / "structural_capability_registry.v2.json"
)
REQUIRED_AXES = {
    "representable",
    "implemented",
    "executable",
    "public",
    "numerical_authority",
    "recovery_authority",
    "external_vv_level",
    "release_eligible",
}
REQUIRED_ROWS = {
    "frame2d.rigid_offset",
    "frame2d.release.rz",
    "frame2d.uniform_member_load",
    "frame2d.direct_displacement_control",
    "frame3d.corotational",
    "frame3d.stateful_fiber",
    "material.confined_concrete",
    "material.bond_slip",
    "material.partial_composite",
    "analysis.nonlinear_transient_sdof",
}


def _load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_capability_registry_v2_splits_authority_axes_and_required_rows() -> None:
    payload = _load()
    rows = {row["id"]: row for row in payload["capabilities"]}

    assert payload["schema_version"] == "structural-analysis-capability-registry.v2"
    assert REQUIRED_ROWS == set(rows)
    assert payload["rules"]["implemented_does_not_imply_public"] is True
    assert payload["rules"]["candidate_result_authority_does_not_imply_release_eligibility"] is True
    for capability_id, row in rows.items():
        assert REQUIRED_AXES <= set(row), capability_id
        assert isinstance(row["external_vv_level"], int)
        assert 0 <= row["external_vv_level"] <= 3
        assert isinstance(row["limitations"], list) and row["limitations"]
        assert isinstance(row["source_paths_at_ref"], list) and row["source_paths_at_ref"]
        assert isinstance(row["verification_paths_at_ref"], list) and row["verification_paths_at_ref"]


def test_capability_registry_v2_enforces_non_promoting_invariants() -> None:
    payload = _load()

    for row in payload["capabilities"]:
        if row["implemented"]:
            assert row["representable"] is True
        if row["executable"]:
            assert row["implemented"] is True
        if row["public"]:
            assert row["executable"] is True
        if row["release_eligible"]:
            assert row["public"] is True
            assert row["external_vv_level"] >= payload["rules"][
                "release_requires_external_vv_level"
            ]

    assert all(row["implemented"] for row in payload["capabilities"])
    assert all(row["executable"] for row in payload["capabilities"])
    assert all(row["public"] is False for row in payload["capabilities"])
    assert all(row["external_vv_level"] == 0 for row in payload["capabilities"])
    assert all(row["release_eligible"] is False for row in payload["capabilities"])


def test_frame2d_member_feature_rows_bind_merged_pr_227_without_promotion() -> None:
    rows = {row["id"]: row for row in _load()["capabilities"]}

    for capability_id in (
        "frame2d.rigid_offset",
        "frame2d.release.rz",
        "frame2d.uniform_member_load",
    ):
        row = rows[capability_id]
        assert row["merged_pr"] == 227
        assert row["implementation_ref"] == (
            "ed7ea935f0318ba5102edd7f2a197a7beaf013f7"
        )
        assert row["numerical_authority"] == "bounded_candidate"
        assert row["recovery_authority"] == "exact_bounded_candidate"
        assert row["release_eligible"] is False


def test_readme_points_to_axis_split_registry_without_future_work_drift() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "structural_capability_registry.v2.json" in readme
    assert "implemented` and `executable` do not mean `public`" in readme
