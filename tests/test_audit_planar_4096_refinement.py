"""Synthetic 2048/4096 comparison packet tests, not numerical evidence."""

from copy import deepcopy

import pytest

from scripts import audit_planar_4096_refinement as audit
from scripts.run_planar_256_refinement import file_sha256, write_json


def feature_packet(root, *, source_revision="synthetic-source", mutation=None):
    root.mkdir()
    features = [{"target_m": i / 500} for i in range(1, 41)]
    if mutation == "targets":
        features.pop()
    feature_path = root / "features.json"
    write_json(feature_path, features)
    feature_sha = file_sha256(feature_path)
    receipt = {
        "schema": "fixed-planar-2048-comparison-features.v1",
        "source_revision": source_revision,
        "original_full_sha256": audit.COARSE_SHA,
        "original_index_sha256": audit.COARSE_INDEX_SHA,
        "protocol_sha256": audit.COARSE_PROTOCOL_SHA,
        "features_sha256": feature_sha,
        "verified_steps": 40,
        "structural_solves": 0,
        "training_fits": 0,
        "physical_validation": False,
    }
    if mutation == "source":
        receipt["original_full_sha256"] = "0" * 64
    elif mutation == "index":
        receipt["original_index_sha256"] = "0" * 64
    result_path = root / "result.json"
    write_json(result_path, receipt)
    write_json(
        root / "inventory.json",
        {
            "schema": "fixed-planar-2048-comparison-feature-inventory.v1",
            "files": [
                {
                    "path": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": file_sha256(path),
                }
                for path in (feature_path, result_path)
            ],
        },
    )
    return feature_sha, file_sha256(root / "inventory.json"), features


@pytest.mark.parametrize("mutation", [None, "source", "index", "targets", "bytes"])
def test_4096_audit_requires_pinned_2048_features(tmp_path, monkeypatch, mutation):
    root = tmp_path / "features"
    feature_sha, inventory_sha, features = feature_packet(root, mutation=mutation)
    monkeypatch.setattr(audit, "COARSE_FEATURE_SHA", feature_sha)
    monkeypatch.setattr(audit, "COARSE_FEATURE_INVENTORY_SHA", inventory_sha)
    if mutation == "bytes":
        with (root / "features.json").open("ab") as stream:
            stream.write(b" ")
    if mutation is None:
        assert (
            audit.coarse_features(root, feature_sha, inventory_sha, "synthetic-source")
            == features
        )
    else:
        with pytest.raises(ValueError, match="provenance|targets|size|digest"):
            audit.coarse_features(root, feature_sha, inventory_sha, "synthetic-source")


def test_4096_audit_rejects_wrong_inventory_or_unpinned_digest(tmp_path, monkeypatch):
    root = tmp_path / "features"
    feature_sha, inventory_sha, _ = feature_packet(root)
    monkeypatch.setattr(audit, "COARSE_FEATURE_SHA", feature_sha)
    monkeypatch.setattr(audit, "COARSE_FEATURE_INVENTORY_SHA", inventory_sha)
    with pytest.raises(ValueError, match="pinned 2048 feature inventory"):
        audit.coarse_features(root, feature_sha, "0" * 64, "synthetic-source")
    with pytest.raises(ValueError, match="explicit SHA-256"):
        audit.coarse_features(root, feature_sha, "not-a-digest", "synthetic-source")
    assert inventory_sha != "0" * 64


def test_4096_audit_rejects_self_consistent_unpinned_feature_packet(
    tmp_path, monkeypatch
):
    root = tmp_path / "features"
    feature_sha, inventory_sha, _ = feature_packet(root)
    assert feature_sha != audit.COARSE_FEATURE_SHA
    assert inventory_sha != audit.COARSE_FEATURE_INVENTORY_SHA
    with pytest.raises(ValueError, match="pinned 2048 feature digest"):
        audit.coarse_features(root, feature_sha, inventory_sha, "synthetic-source")

    values = iter(protocols())
    monkeypatch.setattr(audit, "read_checked", lambda *args, **kwargs: next(values))
    monkeypatch.setattr(
        audit, "coarse_features", lambda *args: pytest.fail("must reject unpinned input")
    )
    with pytest.raises(ValueError, match="pinned 2048 feature digest"):
        audit.audit(
            tmp_path, root, tmp_path, "1" * 64, "2" * 64,
            feature_sha, inventory_sha,
        )
    monkeypatch.setattr(audit, "COARSE_FEATURE_SHA", feature_sha)
    values = iter(protocols())
    with pytest.raises(ValueError, match="pinned 2048 feature inventory"):
        audit.audit(
            tmp_path, root, tmp_path, "1" * 64, "2" * 64,
            feature_sha, inventory_sha,
        )


def protocols():
    common = {
        "source_revision": "synthetic-source",
        "source_manifest_sha256": "a" * 64,
        "input_sha256": "b" * 64,
        "target_displacements_m": [i / 500 for i in range(1, 41)],
        "control_global_dof": 15,
        "configuration": {"fixed": True},
        "same_proportional_force_vector": True,
        "constant_axial_load": False,
    }
    return (
        {**common, "concrete_layer_count": 2048, "comparison_layer_count": 1024},
        {**common, "concrete_layer_count": 4096, "comparison_layer_count": 2048},
    )


def test_4096_audit_rejects_protocol_change_before_features(tmp_path, monkeypatch):
    coarse, fine = protocols()
    fine["configuration"] = {"changed": True}
    values = iter((coarse, fine))
    monkeypatch.setattr(audit, "read_checked", lambda *args, **kwargs: next(values))
    monkeypatch.setattr(
        audit,
        "coarse_features",
        lambda *args: pytest.fail("must reject before feature read"),
    )
    with pytest.raises(ValueError, match="protocol mismatch: configuration"):
        audit.audit(
            tmp_path, tmp_path, tmp_path, "1" * 64, "2" * 64, "3" * 64, "4" * 64
        )


def test_4096_audit_binds_confirmed_protocol_and_comparison_inputs(
    tmp_path, monkeypatch
):
    from scripts.run_planar_256_refinement import PROTOCOL_SHA256

    assert audit.FINE_PROTOCOL_SHA == PROTOCOL_SHA256[4096]
    coarse, fine = protocols()
    values = iter((coarse, fine))
    monkeypatch.setattr(audit, "read_checked", lambda *args, **kwargs: next(values))
    coarse_features = [{"target_m": i / 500} for i in range(1, 41)]
    fine_features = deepcopy(coarse_features)

    def read_coarse(root, feature_sha, inventory_sha, revision):
        assert (feature_sha, inventory_sha, revision) == (
            audit.COARSE_FEATURE_SHA,
            audit.COARSE_FEATURE_INVENTORY_SHA,
            "synthetic-source",
        )
        return coarse_features

    def read_fine(root, index_sha, full_sha, consume_step):
        assert (index_sha, full_sha) == ("2" * 64, "1" * 64)
        return fine_features

    def compare(left, right, layers):
        assert left is coarse_features and right is fine_features and layers == 2048
        rows = [
            {
                "target_m": target,
                "nodal_steel": {
                    "translations": {"within_exploratory_one_percent": True}
                },
                "concrete": {
                    "tensile_damage": {"within_exploratory_one_percent": False}
                },
            }
            for target in (i / 500 for i in range(1, 41))
        ]
        return rows, {"synthetic": True}

    monkeypatch.setattr(audit, "coarse_features", read_coarse)
    monkeypatch.setattr(audit, "read_path_artifacts", read_fine)
    monkeypatch.setattr(audit, "compare_features", compare)
    result = audit.audit(
        tmp_path, tmp_path, tmp_path, "1" * 64, "2" * 64,
        audit.COARSE_FEATURE_SHA, audit.COARSE_FEATURE_INVENTORY_SHA,
    )
    assert result["schema"] == "fixed-planar-2048-4096-comparison.v1"
    assert result["source_sha256"] == {"coarse": audit.COARSE_SHA, "fine": "1" * 64}
    assert result["comparison_layers"] == [2048, 4096]
    assert result["original_group_screen"] == 0.01
    assert result["failed_group_counts"] == {"nodal_steel": 0, "concrete": 40}
    assert result["structural_solves"] == result["training_fits"] == 0
    assert result["independent_physical_validation"] is False
