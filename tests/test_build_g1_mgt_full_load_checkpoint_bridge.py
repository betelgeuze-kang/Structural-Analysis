from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_g1_mgt_full_load_checkpoint_bridge.py"
SPEC = importlib.util.spec_from_file_location(
    "build_g1_mgt_full_load_checkpoint_bridge",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _binding() -> dict[str, object]:
    return {
        "source_commit_sha": "a" * 40,
        "model_source_sha256": "sha256:" + "b" * 64,
        "equilibrium_operator_binding_hash": "sha256:" + "c" * 64,
        "complete": True,
    }


def test_checkpoint_projection_and_npz_encoding_are_byte_deterministic() -> None:
    arrays = module._checkpoint_arrays(
        node_id=np.asarray([11, 12], dtype=np.int64),
        free_global_dofs=np.asarray([0, 7, 11], dtype=np.int64),
        free_displacements_m=np.asarray([0.1, -0.2, 0.3]),
        residual_inf_n=4.0e-4,
        final_increment_inf_m=1.0e-8,
        final_relative_increment=2.0e-5,
        state_hash="sha256:" + "d" * 64,
        source_binding=_binding(),
    )
    first = module.deterministic_npz_bytes(arrays)
    second = module.deterministic_npz_bytes(arrays)

    assert first == second
    with np.load(BytesIO(first), allow_pickle=False) as archive:
        assert archive["checkpoint_schema"].item() == module.CHECKPOINT_SCHEMA
        assert archive["load_scale"].item() == 1.0
        assert archive["dof_per_node"].item() == 6
        assert archive["displacement_u"].shape == (12,)
        assert archive["displacement_u"].tolist() == [
            0.1,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            0.0,
            -0.2,
            0.0,
            0.0,
            0.0,
            0.3,
        ]
        assert archive["source_commit_sha"].item() == "a" * 40
        assert archive["accepted_state_hash"].item() == "sha256:" + "d" * 64


def test_committed_bridge_receipt_and_checkpoint_are_bound() -> None:
    receipt_path = ROOT / module.DEFAULT_RECEIPT_OUT
    checkpoint_path = ROOT / module.DEFAULT_CHECKPOINT_OUT
    if not receipt_path.is_file() or not checkpoint_path.is_file():
        return
    payload = module._read_json(receipt_path)

    assert payload["status"] == "ready"
    assert payload["contract_pass"] is True
    assert payload["source_commit_exact_replay_claim"] is True
    assert payload["checkpoint"]["load_scale"] == 1.0
    assert payload["checkpoint"]["global_dof_count"] == 78_282
    assert payload["checkpoint"]["free_equation_count"] == 70_560
    assert payload["checkpoint"]["exact_restart_binding"]["complete"] is True
    assert payload["solver"]["residual_and_increment_acceptance_gate"] is True
    assert payload["solver"]["fallback_count"] == 0
    assert payload["solver"]["regularization_count"] == 0
    assert module.file_sha256(checkpoint_path) == payload["checkpoint"]["sha256"]
    with np.load(checkpoint_path, allow_pickle=False) as archive:
        assert archive["load_scale"].item() == 1.0
        assert archive["displacement_u"].shape == (78_282,)
        assert archive["free_displacements_m"].shape == (70_560,)
