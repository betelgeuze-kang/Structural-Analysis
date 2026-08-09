from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import struct
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton import (  # noqa: E402
    create_load_controlled_matrix_free_newton_checkpoint,
)
from structural_analysis.solvers.nonlinear.load_controlled_matrix_free_newton_checkpoint_io import (  # noqa: E402
    LoadControlledMatrixFreeNewtonCheckpointArtifactError,
    read_load_controlled_matrix_free_newton_checkpoint_artifact,
    write_load_controlled_matrix_free_newton_checkpoint_artifact,
)


PATH_HASH = "sha256:" + "1" * 64


@dataclass(frozen=True)
class _Problem:
    case_id: str = "n1-durable-checkpoint-test"


def _checkpoint():
    return create_load_controlled_matrix_free_newton_checkpoint(
        problem=_Problem(),
        path_contract_hash=PATH_HASH,
        step_index=4,
        load_factor=1.0,
        free_displacements_m=np.asarray(
            [0.0, -0.0, 0.125, -0.25, 1.5, -2.0],
            dtype=np.float64,
        ),
    )


def _write(tmp_path: Path):
    return write_load_controlled_matrix_free_newton_checkpoint_artifact(
        _checkpoint(),
        tmp_path / "checkpoint.json",
    )


def _read(tmp_path: Path):
    return read_load_controlled_matrix_free_newton_checkpoint_artifact(
        tmp_path / "checkpoint.json",
        expected_case_id=_Problem.case_id,
        expected_path_contract_hash=PATH_HASH,
        expected_equation_count=6,
    )


def test_durable_checkpoint_roundtrip_is_exact_little_endian_fp64(
    tmp_path: Path,
) -> None:
    artifact = _write(tmp_path)
    restored = _read(tmp_path)
    expected = _checkpoint()

    assert artifact.descriptor_hash == restored.descriptor_hash
    assert restored.checkpoint.state_hash == expected.state_hash
    assert restored.checkpoint.path_contract_hash == PATH_HASH
    assert restored.descriptor["displacement_artifact"]["dtype"] == "<f8"
    assert restored.descriptor["displacement_artifact"]["byte_order"] == "little"
    assert restored.displacement_path.read_bytes() == struct.pack(
        "<6d", *expected.free_displacements_m
    )
    np.testing.assert_array_equal(
        restored.checkpoint.free_displacements_m,
        expected.free_displacements_m,
    )


def test_durable_checkpoint_write_is_no_replace(tmp_path: Path) -> None:
    _write(tmp_path)
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="already exists",
    ):
        _write(tmp_path)


def test_descriptor_collision_rolls_back_vector_installed_by_this_call(
    tmp_path: Path,
) -> None:
    descriptor = tmp_path / "checkpoint.json"
    descriptor.write_bytes(b"pre-existing descriptor")
    assert not (tmp_path / "checkpoint.f64le").exists()

    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="already exists",
    ):
        write_load_controlled_matrix_free_newton_checkpoint_artifact(
            _checkpoint(),
            descriptor,
        )

    assert descriptor.read_bytes() == b"pre-existing descriptor"
    assert not (tmp_path / "checkpoint.f64le").exists()


def test_duplicate_key_and_nonfinite_json_fail_closed(tmp_path: Path) -> None:
    _write(tmp_path)
    descriptor_path = tmp_path / "checkpoint.json"
    raw = descriptor_path.read_text(encoding="utf-8")
    descriptor_path.write_text(
        raw.replace(
            "{",
            '{"schema_version":"load-controlled-matrix-free-newton-checkpoint-artifact.v1",',
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="duplicate key",
    ):
        _read(tmp_path)

    descriptor_path.unlink()
    (tmp_path / "checkpoint.f64le").unlink()
    _write(tmp_path)
    raw = descriptor_path.read_text(encoding="utf-8")
    descriptor_path.write_text(
        raw.replace('"load_factor":1.0', '"load_factor":NaN'),
        encoding="utf-8",
    )
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="non-finite token",
    ):
        _read(tmp_path)


def test_binary_hash_length_and_endianness_tamper_fail_closed(
    tmp_path: Path,
) -> None:
    artifact = _write(tmp_path)
    raw = artifact.displacement_path.read_bytes()
    artifact.displacement_path.write_bytes(raw[:-8])
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="byte length mismatch",
    ):
        _read(tmp_path)

    artifact.displacement_path.write_bytes(raw)
    descriptor = json.loads(artifact.descriptor_path.read_text(encoding="utf-8"))
    descriptor["displacement_artifact"]["dtype"] = ">f8"
    descriptor["descriptor_hash"] = "sha256:" + "0" * 64
    artifact.descriptor_path.write_text(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="schema validation failed",
    ):
        _read(tmp_path)


def test_cross_case_path_equation_and_detached_vector_fail_closed(
    tmp_path: Path,
) -> None:
    artifact = _write(tmp_path)
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="case_id",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            artifact.descriptor_path,
            expected_case_id="other-case",
            expected_path_contract_hash=PATH_HASH,
        )
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="path_contract_hash",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            artifact.descriptor_path,
            expected_case_id=_Problem.case_id,
            expected_path_contract_hash="sha256:" + "2" * 64,
        )
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="equation_count",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            artifact.descriptor_path,
            expected_case_id=_Problem.case_id,
            expected_path_contract_hash=PATH_HASH,
            expected_equation_count=12,
        )
    detached = tmp_path / "detached.f64le"
    detached.write_bytes(artifact.displacement_path.read_bytes())
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="detached",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            artifact.descriptor_path,
            expected_case_id=_Problem.case_id,
            expected_path_contract_hash=PATH_HASH,
            displacement_path=detached,
        )


def test_descriptor_and_vector_symlinks_fail_closed(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    artifact = write_load_controlled_matrix_free_newton_checkpoint_artifact(
        _checkpoint(),
        real / "checkpoint.json",
    )
    descriptor_link = tmp_path / "descriptor-link.json"
    descriptor_link.symlink_to(artifact.descriptor_path)
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="symlink",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            descriptor_link,
            expected_case_id=_Problem.case_id,
            expected_path_contract_hash=PATH_HASH,
        )

    vector_bytes = artifact.displacement_path.read_bytes()
    artifact.displacement_path.unlink()
    outside_vector = tmp_path / "outside.f64le"
    outside_vector.write_bytes(vector_bytes)
    artifact.displacement_path.symlink_to(outside_vector)
    with pytest.raises(
        LoadControlledMatrixFreeNewtonCheckpointArtifactError,
        match="symlink",
    ):
        read_load_controlled_matrix_free_newton_checkpoint_artifact(
            artifact.descriptor_path,
            expected_case_id=_Problem.case_id,
            expected_path_contract_hash=PATH_HASH,
        )
