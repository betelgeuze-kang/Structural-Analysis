"""Synthetic binding tests for the retained-path feature extractor."""

import json

import pytest

from scripts import extract_planar_2048_features as extractor
from scripts.audit_planar_concrete_localization import read_checked
from scripts.run_planar_256_refinement import (
    file_sha256,
    write_json,
    write_path_artifacts,
)


def source_packet(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    targets = [i / 500 for i in range(1, 41)]
    protocol = {
        "source_revision": "synthetic-source",
        "concrete_layer_count": 2048,
        "comparison_layer_count": 1024,
    }
    write_json(source / "protocol.json", protocol)
    metadata = {
        "status": "ready",
        "contract_pass": True,
        "control_global_dof": 15,
        "steps": [],
        "initial_checkpoint": {"ordinal": 0},
        "final_checkpoint": {"ordinal": 40},
        "target_control_displacements_m": targets,
    }
    steps = [
        {
            "committed": True,
            "metrics": {
                "solver_contract_pass": True,
                "target_control_displacement_m": target,
            },
            "parent_checkpoint": {"ordinal": ordinal},
            "accepted_checkpoint": {"ordinal": ordinal + 1},
        }
        for ordinal, target in enumerate(targets)
    ]
    index = write_path_artifacts(source, metadata, steps)
    monkeypatch.setattr(
        extractor, "COARSE_PROTOCOL_SHA", file_sha256(source / "protocol.json")
    )
    monkeypatch.setattr(
        extractor, "COARSE_INDEX_SHA", file_sha256(source / "path-index.json")
    )
    monkeypatch.setattr(extractor, "COARSE_SHA", index["full"]["sha256"])

    def sections(step, layers, fields):
        assert layers == 2048
        return {
            "E1:gauss-0": {
                "xi": 0.0,
                "weight": 1.0,
                "values": [dict.fromkeys(fields, 0.0)] * layers,
            }
        }

    def nodal_steel(step, layers):
        assert layers == 2048
        return (
            ["E1:0:0"],
            {"translations": [step["metrics"]["target_control_displacement_m"]]},
        )

    monkeypatch.setattr(extractor, "sections", sections)
    monkeypatch.setattr(extractor, "nodal_steel", nodal_steel)
    return source


def test_extract_2048_features_binds_full_path_and_inventory(tmp_path, monkeypatch):
    from scripts import audit_planar_4096_refinement as comparison

    source = source_packet(tmp_path, monkeypatch)
    output = tmp_path / "features"
    receipt = extractor.extract(source, output)
    inventory_sha = file_sha256(output / "inventory.json")
    inventory = read_checked(output / "inventory.json", inventory_sha)
    entries = {entry["path"]: entry for entry in inventory["files"]}
    assert inventory["schema"] == "fixed-planar-2048-comparison-feature-inventory.v1"
    assert set(entries) == {"features.json", "result.json"}
    for name, entry in entries.items():
        assert entry["sha256"] == file_sha256(output / name)
        assert entry["bytes"] == (output / name).stat().st_size
    assert (
        read_checked(output / "result.json", entries["result.json"]["sha256"])
        == receipt
    )
    assert receipt["original_full_sha256"] == extractor.COARSE_SHA
    assert receipt["original_index_sha256"] == extractor.COARSE_INDEX_SHA
    assert receipt["protocol_sha256"] == extractor.COARSE_PROTOCOL_SHA
    assert receipt["features_sha256"] == entries["features.json"]["sha256"]
    assert receipt["verified_steps"] == 40
    assert receipt["structural_solves"] == receipt["training_fits"] == 0
    features = json.loads((output / "features.json").read_text())
    assert [row["target_m"] for row in features] == [i / 500 for i in range(1, 41)]
    monkeypatch.setattr(comparison, "COARSE_SHA", extractor.COARSE_SHA)
    monkeypatch.setattr(comparison, "COARSE_INDEX_SHA", extractor.COARSE_INDEX_SHA)
    monkeypatch.setattr(
        comparison, "COARSE_PROTOCOL_SHA", extractor.COARSE_PROTOCOL_SHA
    )
    monkeypatch.setattr(comparison, "COARSE_FEATURE_SHA", receipt["features_sha256"])
    monkeypatch.setattr(comparison, "COARSE_FEATURE_INVENTORY_SHA", inventory_sha)
    assert (
        comparison.coarse_features(
            output, receipt["features_sha256"], inventory_sha, "synthetic-source"
        )
        == features
    )


@pytest.mark.parametrize(
    "changed", ["protocol.json", "path-index.json", "repeat-0.json", "steps/0000.json"]
)
def test_extract_2048_features_rejects_changed_source_before_output(
    tmp_path, monkeypatch, changed
):
    source = source_packet(tmp_path, monkeypatch)
    with (source / changed).open("ab") as stream:
        stream.write(b" ")
    output = tmp_path / "features"
    with pytest.raises(ValueError):
        extractor.extract(source, output)
    assert not output.exists()
