"""Verify the retained 2048-layer path and extract compact comparison features.

This observer performs no structural solve. Its packet can become a pinned
coarse input to a separate 2048/4096 comparison after the packet is produced
and its byte digests are independently recorded.
"""

import argparse
from pathlib import Path

from scripts.audit_planar_256_refinement import CONCRETE, nodal_steel
from scripts.audit_planar_concrete_localization import read_checked, require, sections
from scripts.read_planar_path_artifacts import read_path_artifacts
from scripts.run_planar_256_refinement import file_sha256, write_json

COARSE_SHA = "434faa33ae5360b332897d3e0c7171844a95182630082d9f9689a885d7ff71f6"
COARSE_INDEX_SHA = "e1fabd392c7a32648cac7afd610483940fff467cdcf0413bce2e1a057a66878d"
COARSE_PROTOCOL_SHA = "6508da674654590141a1b4084b9f59069a70db834da8c4070be153f0dccf9e43"
MAX_FEATURE_BYTES = 1024**3


def extract(source_root, output_root):
    protocol = read_checked(source_root / "protocol.json", COARSE_PROTOCOL_SHA)
    require(
        protocol["concrete_layer_count"] == 2048
        and protocol["comparison_layer_count"] == 1024,
        "fixed 2048-layer protocol required",
    )

    def feature(step, ordinal):
        return {
            "target_m": step["metrics"]["target_control_displacement_m"],
            "sections": sections(step, 2048, CONCRETE),
            "nodal_steel": nodal_steel(step, 2048),
        }

    features = read_path_artifacts(source_root, COARSE_INDEX_SHA, COARSE_SHA, feature)
    require(
        [row["target_m"] for row in features] == [i / 500 for i in range(1, 41)],
        "full forty feature targets required",
    )

    output_root.mkdir()
    feature_path = output_root / "features.json"
    write_json(
        feature_path,
        features,
        maximum_bytes=MAX_FEATURE_BYTES,
        label="2048 comparison features JSON",
    )
    result = {
        "schema": "fixed-planar-2048-comparison-features.v1",
        "source_revision": protocol["source_revision"],
        "original_full_sha256": COARSE_SHA,
        "original_index_sha256": COARSE_INDEX_SHA,
        "protocol_sha256": COARSE_PROTOCOL_SHA,
        "features_sha256": file_sha256(feature_path),
        "verified_steps": len(features),
        "structural_solves": 0,
        "training_fits": 0,
        "physical_validation": False,
    }
    result_path = output_root / "result.json"
    write_json(result_path, result)
    write_json(
        output_root / "inventory.json",
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
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    extract(args.source_root, args.output_root)
