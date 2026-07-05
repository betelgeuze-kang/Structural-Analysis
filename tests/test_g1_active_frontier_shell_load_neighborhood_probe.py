from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


PHASE1 = Path(__file__).resolve().parent.parent / "implementation" / "phase1"
if str(PHASE1) not in sys.path:
    sys.path.insert(0, str(PHASE1))

SCRIPT_PATH = PHASE1 / "run_g1_active_frontier_shell_load_neighborhood_probe.py"
SPEC = importlib.util.spec_from_file_location(
    "run_g1_active_frontier_shell_load_neighborhood_probe", SCRIPT_PATH
)
assert SPEC is not None
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_translate_ownership_rows_for_shell_helpers_normalizes_row_shape() -> None:
    rows = [
        {
            "reduced_index": 7,
            "global_dof": 14,
            "node_index": 2,
            "dof_label": "UZ",
            "dominant_internal_component": "shell_bending_drilling",
            "residual_n": -0.4,
            "inferred_external_load_n": 0.6,
            "component_values_n": {"shell_bending_drilling": 0.2},
        }
    ]

    translated = probe.translate_ownership_rows_for_shell_helpers(rows)

    assert translated == [
        {
            "free_row": 7,
            "global_dof": 14,
            "node_index": 2,
            "dof": "uz",
            "dominant_component": "shell_bending_drilling",
            "residual_n": -0.4,
            "external_load_n": 0.6,
            "component_values_n": {"shell_bending_drilling": 0.2},
        }
    ]


def test_shell_setup_meta_from_closure_meta_maps_shell_inputs() -> None:
    node_xyz = np.zeros((2, 3), dtype=np.float64)
    node_id = np.asarray([101, 102], dtype=np.int64)
    elem_id = np.asarray([201], dtype=np.int64)
    elem_type_code = np.asarray([2], dtype=np.int32)
    conn_ptr = np.asarray([0, 2], dtype=np.int64)
    conn_idx = np.asarray([0, 1], dtype=np.int64)

    setup = probe.shell_setup_meta_from_closure_meta(
        {
            "shell_inputs": {
                "node_xyz": node_xyz,
                "node_id": node_id,
                "elem_id": elem_id,
                "elem_type_code": elem_type_code,
                "elem_section_id": np.asarray([1], dtype=np.int32),
                "elem_material_id": np.asarray([2], dtype=np.int32),
                "conn_ptr": conn_ptr,
                "conn_idx": conn_idx,
                "material_props": {2: {"E_kN_per_m2": 1.0}},
                "plate_thickness_props": {1: {"effective_thickness_m": 0.2}},
                "frame_elements": [],
                "restrained_dofs": np.asarray([0, 1], dtype=np.int64),
                "load_scale": 1.0,
                "free": np.asarray([2], dtype=np.int64),
            }
        }
    )

    assert setup["_node_xyz"] is node_xyz
    assert setup["_node_id"] is node_id
    assert setup["_elem_id"] is elem_id
    assert setup["_elem_type_code"] is elem_type_code
    assert setup["_conn_ptr"] is conn_ptr
    assert setup["_conn_idx"] is conn_idx
    assert setup["load_scale"] == 1.0
