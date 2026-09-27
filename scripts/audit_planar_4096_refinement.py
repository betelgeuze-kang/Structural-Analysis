"""Bounded 2048/4096 comparison using a separately pinned coarse feature packet."""

import argparse
import hashlib
import os
from pathlib import Path
import re

from scripts.audit_planar_256_refinement import CONCRETE, compare_features, nodal_steel
from scripts.audit_planar_concrete_localization import read_checked, require, sections
from scripts.extract_planar_2048_features import (
    COARSE_INDEX_SHA,
    COARSE_PROTOCOL_SHA,
    COARSE_SHA,
    MAX_FEATURE_BYTES,
)
from scripts.read_planar_path_artifacts import read_path_artifacts
from scripts.run_planar_256_refinement import write_json
from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)

FINE_PROTOCOL_SHA = "7f30057cd8b26b0706c96bf84d5fc81842c4dbfc319f8abfc5c618793d459881"
PROTOCOL_FIELDS = (
    "source_revision",
    "source_manifest_sha256",
    "input_sha256",
    "target_displacements_m",
    "control_global_dof",
    "configuration",
    "same_proportional_force_vector",
    "constant_axial_load",
)


def _digest(value):
    require(
        type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value),
        "explicit SHA-256 digest required",
    )
    return value


def coarse_features(root, feature_sha256, inventory_sha256, source_revision):
    feature_sha256, inventory_sha256 = (
        _digest(feature_sha256),
        _digest(inventory_sha256),
    )
    inventory = read_checked(
        root / "inventory.json", inventory_sha256, maximum_bytes=128 * 1024
    )
    require(
        inventory["schema"] == "fixed-planar-2048-comparison-feature-inventory.v1"
        and type(inventory["files"]) is list
        and len(inventory["files"]) == 2,
        "coarse feature inventory mismatch",
    )
    entries = inventory["files"]
    require(
        all(
            type(entry) is dict
            and set(entry) == {"path", "bytes", "sha256"}
            and type(entry["path"]) is str
            and type(entry["bytes"]) is int
            and 0 < entry["bytes"] <= MAX_FEATURE_BYTES
            and type(entry["sha256"]) is str
            and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            for entry in entries
        ),
        "invalid coarse feature inventory entry",
    )
    files = {entry["path"]: entry for entry in entries}
    require(
        set(files) == {"features.json", "result.json"}, "coarse feature files mismatch"
    )
    receipt = read_checked(
        root / "result.json", files["result.json"]["sha256"], maximum_bytes=16 * 1024
    )
    require(
        (root / "result.json").stat().st_size == files["result.json"]["bytes"],
        "coarse receipt size mismatch",
    )
    require(
        receipt
        == {
            "schema": "fixed-planar-2048-comparison-features.v1",
            "source_revision": source_revision,
            "original_full_sha256": COARSE_SHA,
            "original_index_sha256": COARSE_INDEX_SHA,
            "protocol_sha256": COARSE_PROTOCOL_SHA,
            "features_sha256": feature_sha256,
            "verified_steps": 40,
            "structural_solves": 0,
            "training_fits": 0,
            "physical_validation": False,
        },
        "coarse feature provenance mismatch",
    )
    require(
        files["features.json"]["sha256"] == feature_sha256,
        "coarse feature digest mismatch",
    )
    with (root / "features.json").open("rb") as stream:
        size = os.fstat(stream.fileno()).st_size
        require(
            size == files["features.json"]["bytes"] and size <= MAX_FEATURE_BYTES,
            "coarse feature size mismatch",
        )
        raw = stream.read(size + 1)
    require(
        len(raw) == size and hashlib.sha256(raw).hexdigest() == feature_sha256,
        "coarse feature bytes or digest mismatch",
    )
    features = strict_json_object_bytes(
        b'{"features":' + raw + b"}", maximum_bytes=MAX_FEATURE_BYTES + 16
    )["features"]
    require(
        type(features) is list
        and [row["target_m"] for row in features] == [i / 500 for i in range(1, 41)],
        "full coarse feature targets required",
    )
    return features


def audit(
    coarse_root,
    feature_root,
    fine_root,
    fine_sha256,
    fine_index_sha256,
    feature_sha256,
    feature_inventory_sha256,
):
    fine_sha256, fine_index_sha256 = _digest(fine_sha256), _digest(fine_index_sha256)
    coarse_protocol = read_checked(coarse_root / "protocol.json", COARSE_PROTOCOL_SHA)
    fine_protocol = read_checked(fine_root / "protocol.json", FINE_PROTOCOL_SHA)
    require(
        coarse_protocol["concrete_layer_count"] == 2048
        and coarse_protocol["comparison_layer_count"] == 1024
        and fine_protocol["concrete_layer_count"] == 4096
        and fine_protocol["comparison_layer_count"] == 2048,
        "fixed comparison layers required",
    )
    for field in PROTOCOL_FIELDS:
        require(
            coarse_protocol[field] == fine_protocol[field],
            "protocol mismatch: " + field,
        )
    coarse = coarse_features(
        feature_root,
        feature_sha256,
        feature_inventory_sha256,
        coarse_protocol["source_revision"],
    )

    def feature(step, ordinal):
        return {
            "target_m": step["metrics"]["target_control_displacement_m"],
            "sections": sections(step, 4096, CONCRETE),
            "nodal_steel": nodal_steel(step, 4096),
        }

    fine = read_path_artifacts(fine_root, fine_index_sha256, fine_sha256, feature)
    rows, maxima = compare_features(coarse, fine, 2048)
    return {
        "schema": "fixed-planar-2048-4096-comparison.v1",
        "source_revision": fine_protocol["source_revision"],
        "source_sha256": {"coarse": COARSE_SHA, "fine": fine_sha256},
        "protocol_sha256": {"coarse": COARSE_PROTOCOL_SHA, "fine": FINE_PROTOCOL_SHA},
        "coarse_index_sha256": COARSE_INDEX_SHA,
        "coarse_features_sha256": feature_sha256,
        "coarse_verification_inventory_sha256": feature_inventory_sha256,
        "fine_index_sha256": fine_index_sha256,
        "comparison_layers": [2048, 4096],
        "matched_targets": 40,
        "original_group_screen": 0.01,
        "maxima": maxima,
        "comparisons": rows,
        "failed_group_counts": {
            kind: sum(
                not metric["within_exploratory_one_percent"]
                for row in rows
                for metric in row[kind].values()
            )
            for kind in ("nodal_steel", "concrete")
        },
        "composite_view_not_solver_artifact": True,
        "structural_solves": 0,
        "training_fits": 0,
        "independent_physical_validation": False,
        "public_api_extended": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("coarse_root", type=Path)
    parser.add_argument("feature_root", type=Path)
    parser.add_argument("fine_root", type=Path)
    parser.add_argument("fine_sha256")
    parser.add_argument("fine_index_sha256")
    parser.add_argument("feature_sha256")
    parser.add_argument("feature_inventory_sha256")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_json(
        args.output,
        audit(
            args.coarse_root,
            args.feature_root,
            args.fine_root,
            args.fine_sha256,
            args.fine_index_sha256,
            args.feature_sha256,
            args.feature_inventory_sha256,
        ),
    )
