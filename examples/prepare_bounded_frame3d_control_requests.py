"""Prepare portable requests for the existing bounded experimental 3D model.

No solver executes here. Request hashes retain the full default solver settings
and the explicitly selected reversal policy.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path

from structural_analysis.api.frame3d_direct_control import (
    BoundedFrame3DDirectControlConfig,
)
from structural_analysis.api.frame3d_direct_control_request import (
    bounded_frame3d_direct_control_request_payload,
)
from structural_analysis.assembly.stateful_corotational_frame3d_displacement_control import (
    StatefulCorotationalFrame3DDisplacementControlConfig,
)


TARGETS = (0.003, 0.006, 0.001, -0.004, 0.002)


def prepare(output: Path) -> Path:
    """Copy the authored model and four complete control requests into a new directory."""
    output.mkdir(mode=0o700, exist_ok=False)
    source = Path(__file__).with_name(
        "bounded_frame3d_direct_control_axial_yield.model-ir.v2.json"
    )
    (output / "model.json").write_bytes(source.read_bytes())
    full = BoundedFrame3DDirectControlConfig(
        control_node_id="N2",
        control_dof="UX",
        control_targets=TARGETS,
        solver_config=StatefulCorotationalFrame3DDisplacementControlConfig(
            allow_direction_reversal=True,
            maximum_direction_reversals=4,
        ),
    )
    requests = {
        "cyclic-full": full,
        "cyclic-prefix": replace(full, control_targets=TARGETS[:2]),
        "cyclic-suffix": replace(full, control_targets=TARGETS[2:]),
        "monotonic": BoundedFrame3DDirectControlConfig(
            control_node_id="N2", control_dof="UX", control_targets=TARGETS[:2]
        ),
    }
    for name, config in requests.items():
        payload = bounded_frame3d_direct_control_request_payload(config)
        (output / f"{name}.request.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output_directory))
