from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "artifacts" / "manifests" / "capabilities.yaml"
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
REQUIRED_GRANULAR_ROWS = {
    "frame2d.rigid_offset",
    "frame2d.release.rz",
    "frame2d.uniform_member_load",
    "frame2d.prescribed_support_displacement",
    "frame2d.direct_displacement_control",
    "frame3d.corotational",
    "frame3d.stateful_fiber",
    "frame3d.direct_displacement_control",
    "material.confined_concrete",
    "material.bond_slip",
    "material.partial_composite",
    "analysis.nonlinear_transient_sdof",
}


def _load() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_v2_registry_splits_authority_axes_and_retains_all_product_rows() -> None:
    payload = _load()
    rows = {row["id"]: row for row in payload["capabilities"]}

    assert payload["schema_version"] == "structural-analysis-capabilities.v2"
    assert REQUIRED_GRANULAR_ROWS <= set(rows)
    assert len(rows) == 31
    for capability_id, row in rows.items():
        assert REQUIRED_AXES <= set(row), capability_id
        assert isinstance(row["external_vv_level"], int)
        assert 0 <= row["external_vv_level"] <= 3
        assert isinstance(row["limitations"], list) and row["limitations"]
        assert isinstance(row["evidence"], list) and row["evidence"]


def test_v2_registry_enforces_non_promoting_invariants() -> None:
    payload = _load()
    required_level = payload["authority_rules"]["release_requires_external_vv_level"]

    for row in payload["capabilities"]:
        if row["implemented"]:
            assert row["representable"] is True
        if row["executable"]:
            assert row["implemented"] is True
        if row["public"]:
            assert row["executable"] is True
        if row["release_eligible"]:
            assert row["public"] is True
            assert row["external_vv_level"] >= required_level

    granular = [
        row for row in payload["capabilities"] if row["id"] in REQUIRED_GRANULAR_ROWS
    ]
    assert all(row["implemented"] for row in granular)
    assert all(row["executable"] for row in granular)
    assert all(row["public"] is False for row in granular)
    assert all(row["external_vv_level"] == 0 for row in granular)
    assert all(row["release_eligible"] is False for row in granular)


def test_pr_227_member_features_are_granular_without_public_promotion() -> None:
    rows = {row["id"]: row for row in _load()["capabilities"]}

    for capability_id in (
        "frame2d.rigid_offset",
        "frame2d.release.rz",
        "frame2d.uniform_member_load",
    ):
        row = rows[capability_id]
        assert row["merged_pr"] == 227
        assert row["implementation_ref"] == ("ed7ea935f0318ba5102edd7f2a197a7beaf013f7")
        assert row["numerical_authority"] == "bounded_candidate"
        assert row["recovery_authority"] == "exact_bounded_candidate"
        assert row["release_eligible"] is False


def test_readme_and_generated_consumers_expose_axis_split_registry() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    api_doc = (ROOT / "docs/api-capabilities.md").read_text(encoding="utf-8")
    workbench = json.loads(
        (ROOT / "src/workbench-v2/model/generatedCapabilities.json").read_text(
            encoding="utf-8"
        )
    )

    assert "`implemented` and `executable` do not mean `public`" in readme
    assert "Numerical authority" in api_doc
    assert "Recovery authority" in api_doc
    assert workbench["schemaVersion"] == "structural-analysis-capabilities.v2"
    assert len(workbench["capabilities"]) == 31
