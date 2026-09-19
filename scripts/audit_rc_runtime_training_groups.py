"""Read a pinned original runtime packet and audit its training exclusion groups.

No saved script is executed, no policy is fitted, no solver is called and no
source packet is modified. The output is a separate new JSON file.
"""

import argparse
import hashlib
import json
from pathlib import Path

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    decode_bounded_rc_fiber_direct_control_request,
)
from structural_analysis.benchmark.rc_control_learning import RCControlLearningCase
from structural_analysis.benchmark.rc_control_learning_split import (
    control_training_exclusion_groups,
)
from structural_analysis.io.neutral.loader import load_neutral_json_bytes


def audit(root, expected_protocol_sha256):
    raw = (root / "protocol.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_protocol_sha256:
        raise ValueError("pinned original protocol mismatch")
    protocol = strict_json_object_bytes(raw, maximum_bytes=2 * 1024 * 1024)
    refs = {r["destination"]: r for r in protocol["original_files"]}
    if len(refs) != len(protocol["original_files"]):
        raise ValueError("ambiguous original references")
    checked = []

    def read(name):
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".json":
            raise ValueError("local original JSON required")
        if name != "original-plan.json" and (
            len(path.parts) != 2 or path.parts[0] != "inputs"
        ):
            raise ValueError("original model/request input required")
        ref = refs[name]
        content = (root / path).read_bytes()
        if (
            len(content) != ref["bytes"]
            or hashlib.sha256(content).hexdigest() != ref["sha256"]
        ):
            raise ValueError("original input mismatch")
        checked.append(
            {"path": name, "sha256": ref["sha256"], "byte_length": len(content)}
        )
        return content

    plan = strict_json_object_bytes(
        read("original-plan.json"), maximum_bytes=2 * 1024 * 1024
    )
    cases = []
    for c in plan["cases"]:
        cases.append(
            RCControlLearningCase(
                c["case_id"],
                c["project_id"],
                c["geometry_family_id"],
                c["load_history_id"],
                c["split"],
                load_neutral_json_bytes(read("inputs/" + c["model_path"])),
                decode_bounded_rc_fiber_direct_control_request(
                    read("inputs/" + c["request_path"])
                ),
            )
        )
    groups = control_training_exclusion_groups(cases)
    return {
        "schema_version": "rc-runtime-original-training-group-audit.v1",
        "original_source_revision": protocol["source_revision"],
        "protocol_sha256": expected_protocol_sha256,
        "checked_inputs": checked,
        "training_case_count": sum(c.split == "train" for c in cases),
        "evaluation_case_ids_not_grouped": [
            c.case_id for c in cases if c.split != "train"
        ],
        "group_screen": groups,
        "group_withholding_can_leave_training_data": len(groups["groups"]) >= 2,
        "fit_count": 0,
        "solver_call_count": 0,
        "independent_project_provenance": False,
        "previous_runtime_results_recomputed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.packet, args.expected_protocol_sha256)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(
        json.dumps(
            {
                "training_cases": result["training_case_count"],
                "groups": result["group_screen"]["groups"],
                "usable_for_grouped_tuning": result[
                    "group_withholding_can_leave_training_data"
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
