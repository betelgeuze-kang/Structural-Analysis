from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "implementation" / "phase1"))

import run_mgt_frame_hotspot_diagonal_newton_probe as probe_module  # noqa: E402


def test_frame_hotspot_diagonal_newton_probe_repeats_gate_eligible_promotions(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.3], dtype=np.float64)

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        alpha_values=(0.5,),
        max_promotions=2,
        relative_increment_tolerance=1.0,
    )

    assert payload["status"] == "partial"
    assert payload["promoted_to_final_state"] is True
    assert payload["promotion_count"] == 2
    assert payload["max_promotions"] == 2
    assert payload["stop_reason"] == "max_promotions_exhausted"
    assert payload["base_direct_residual"]["direct_residual_inf_n"] == 2.0
    assert payload["final_direct_residual"]["direct_residual_inf_n"] == 0.5
    assert np.allclose(
        [row["actual_direct_residual_inf_n"] for row in payload["promotion_passes"]],
        [1.0, 0.5],
    )


def test_frame_hotspot_signed_displacement_probe_promotes_step_direction(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.3], dtype=np.float64)

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        promotion_mode="signed_displacement",
        step_values=(0.1,),
        max_promotions=2,
        relative_increment_tolerance=1.0,
    )

    assert payload["status"] == "ready"
    assert payload["promotion_mode"] == "signed_displacement"
    assert payload["promoted_to_final_state"] is True
    assert payload["promotion_count"] == 2
    assert payload["stop_reason"] == "direct_residual_gate_closed"
    assert payload["base_direct_residual"]["direct_residual_inf_n"] == 2.0
    assert abs(payload["final_direct_residual"]["direct_residual_inf_n"]) <= 1.0e-12
    assert [row["step_m"] for row in payload["promotion_passes"]] == [0.1, 0.1]
    assert payload["promotion_candidate"]["step_m"] == 0.1
    assert payload["frame_hotspot_diagonal_newton_sweep"] == {}
    assert payload["frame_hotspot_signed_displacement_sweep"]["evaluated"] is True


def test_frame_hotspot_block_lstsq_probe_promotes_coupled_correction(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(
        (
            [10.0, 5.0, 5.0, 10.0],
            ([0, 0, 1, 1], [0, 1, 0, 1]),
        ),
        shape=(2, 2),
    ).tocsc()
    free = np.asarray([0, 1], dtype=np.int64)
    u0 = np.asarray([0.1, 0.1], dtype=np.float64)

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0, 1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        promotion_mode="block_lstsq",
        alpha_values=(1.0,),
        max_rows=2,
        max_promotions=1,
        relative_increment_tolerance=1.0,
    )

    assert payload["status"] == "ready"
    assert payload["promotion_mode"] == "block_lstsq"
    assert payload["promoted_to_final_state"] is True
    assert payload["promotion_count"] == 1
    assert payload["stop_reason"] == "direct_residual_gate_closed"
    assert payload["final_direct_residual"]["direct_residual_inf_n"] <= 1.0e-12
    assert payload["frame_hotspot_block_lstsq_sweep"]["evaluated"] is True
    assert payload["frame_hotspot_block_lstsq_sweep"]["support_size"] == 2


def test_frame_hotspot_block_lstsq_can_target_nonframe_translation_hotspots(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.1], dtype=np.float64)

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([2.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"shell_membrane": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        promotion_mode="block_lstsq",
        alpha_values=(1.0,),
        max_rows=1,
        max_promotions=1,
        relative_increment_tolerance=1.0,
        block_lstsq_component_filter="translation",
    )

    sweep = payload["frame_hotspot_block_lstsq_sweep"]
    assert payload["status"] == "ready"
    assert sweep["evaluated"] is True
    assert sweep["component_filter"] == "translation"
    assert sweep["direction"] == "block_lstsq_on_translation_hotspots"
    assert sweep["selected_hotspot_dominant_component_counts"] == {"shell_membrane": 1}
    assert payload["final_direct_residual"]["direct_residual_inf_n"] <= 1.0e-12


def test_frame_hotspot_block_lstsq_probe_exposes_support_and_svd_controls(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(
        (
            [10.0, 5.0, 2.0, 5.0, 10.0, 3.0, 2.0, 3.0, 9.0],
            ([0, 0, 0, 1, 1, 1, 2, 2, 2], [0, 1, 2, 0, 1, 2, 0, 1, 2]),
        ),
        shape=(3, 3),
    ).tocsc()
    free = np.asarray([0, 1, 2], dtype=np.int64)
    u0 = np.asarray([0.1, 0.1, 0.1], dtype=np.float64)

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0, 1.0, 1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        promotion_mode="block_lstsq",
        alpha_values=(0.5,),
        max_rows=1,
        max_promotions=1,
        relative_increment_tolerance=1.0,
        block_lstsq_support_columns_per_row=2,
        block_lstsq_svd_max_condition=1234.0,
        block_lstsq_include_gate_limited_alpha=True,
    )

    sweep = payload["frame_hotspot_block_lstsq_sweep"]
    assert sweep["support_columns_per_row"] == 2
    assert sweep["include_gate_limited_alpha"] is True
    assert sweep["linear_solve"]["svd_max_condition"] == 1234.0
    assert sweep["support_size"] >= 2
    assert len(sweep["candidate_rows"]) == 2


def test_frame_hotspot_probe_can_write_progress_artifacts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.3], dtype=np.float64)
    checkpoint_calls: list[Path] = []

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    def write_checkpoint(**kwargs):
        path = Path(kwargs["path"])
        checkpoint_calls.append(path)
        path.write_bytes(b"progress-checkpoint")
        return {"path": str(path), "progress_checkpoint": True}

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )
    monkeypatch.setattr(probe_module, "_write_checkpoint", write_checkpoint)

    output_json = tmp_path / "probe.json"
    output_checkpoint = tmp_path / "probe_checkpoint.npz"
    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=output_json,
        output_final_checkpoint_npz=output_checkpoint,
        alpha_values=(0.5,),
        max_promotions=2,
        relative_increment_tolerance=1.0,
        write_progress_artifacts=True,
    )

    assert payload["promotion_count"] == 2
    assert output_checkpoint.read_bytes() == b"progress-checkpoint"
    assert len(checkpoint_calls) == 3
    on_disk = json.loads(output_json.read_text(encoding="utf-8"))
    assert on_disk["stop_reason"] == "max_promotions_exhausted"
    assert on_disk["promotion_count"] == 2


def test_frame_hotspot_probe_writes_bounded_wall_time_partial(
    monkeypatch,
) -> None:
    stiffness = coo_matrix(([10.0], ([0], [0])), shape=(1, 1)).tocsc()
    free = np.asarray([0], dtype=np.int64)
    u0 = np.asarray([0.3], dtype=np.float64)
    assemble_call_count = 0

    def load_checkpoint(_checkpoint_npz: Path):
        return (
            {"load_scale": 1.0, "path": "fixture.npz"},
            u0.copy(),
            None,
            None,
        )

    def build_direct_residual_assembler(**_kwargs):
        def assemble_residual(u: np.ndarray, *, include_component_forces: bool = False):
            nonlocal assemble_call_count
            assemble_call_count += 1
            internal = np.asarray(stiffness @ u, dtype=np.float64)
            rhs = np.asarray([1.0], dtype=np.float64)
            residual = internal - rhs
            meta = {}
            if include_component_forces:
                meta["component_forces"] = {"frame": internal.copy()}
            return stiffness, rhs.copy(), free.copy(), residual, rhs.copy(), meta

        return assemble_residual, {
            "u0": u0.copy(),
            "checkpoint": {"path": "fixture.npz"},
            "load_scale": 1.0,
        }

    monkeypatch.setattr(probe_module, "_load_checkpoint", load_checkpoint)
    monkeypatch.setattr(
        probe_module,
        "build_direct_residual_assembler",
        build_direct_residual_assembler,
    )

    payload = probe_module.run_mgt_frame_hotspot_diagonal_newton_probe(
        checkpoint_npz=Path("fixture.npz"),
        output_json=None,
        output_final_checkpoint_npz=None,
        alpha_values=(0.5,),
        max_promotions=2,
        relative_increment_tolerance=1.0,
        max_wall_seconds=0.0,
    )

    assert payload["status"] == "partial"
    assert payload["promotion_count"] == 0
    assert payload["stop_reason"] == "max_wall_seconds_exceeded"
    assert payload["base_direct_residual"]["direct_residual_inf_n"] == 2.0
    assert payload["final_direct_residual"]["direct_residual_inf_n"] == 2.0
    assert payload["runtime_metrics"]["max_wall_seconds"] == 0.0
    assert "frontier_probe_wall_time_exceeded" in payload["blockers"]
    assert assemble_call_count == 1
