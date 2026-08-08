from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pytest

from structural_analysis.engine_v2.contracts.shell_static_result import (
    ShellResultIRError,
    create_shell_result_ir,
    validate_shell_result_ir,
)
from structural_analysis.model_ir import load_model_ir_v2
from structural_analysis.solvers.linear.shell_static import ShellStaticModel, solve_shell_static


def _result():
    document = load_model_ir_v2(Path("tests/fixtures/model_ir_v2/shell_square_linear_static.json"))
    payload = document.to_dict(); load = np.zeros(24); load[14] = load[20] = -1_000.0
    model = ShellStaticModel(
        model_id=document.model_id, node_ids=tuple(row["id"] for row in payload["nodes"]),
        node_coordinates_m=tuple(row["coordinates_m"] for row in payload["nodes"]),
        element_ids=tuple(row["id"] for row in payload["elements"]),
        element_connectivity=((0, 2, 3), (0, 3, 1)), elastic_modulus_pa=210.0e9,
        poisson_ratio=0.3, thickness_m=0.1, restrained_dofs=tuple(range(12)),
        load_global_n_nm=load,
    )
    solved = solve_shell_static(model)
    return create_shell_result_ir(
        result_id="f3.shell", model_ir_content_hash=document.content_hash,
        solver_result_hash=solved.result_hash, stiffness_hash=solved.stiffness_hash,
        load_hash=solved.load_hash, terminal_checkpoint_hash=solved.checkpoint.checkpoint_hash,
        solver_id="dense.direct.shell3.v1", node_ids=model.node_ids, element_ids=model.element_ids,
        displacement_global=solved.displacement_global, reaction_global_n_nm=solved.reaction_global_n_nm,
        equilibrium_residual_global_n_nm=solved.equilibrium_residual_global_n_nm,
        element_results=[asdict(row) for row in solved.element_results],
        maximum_free_residual=solved.maximum_free_residual,
        strain_energy_j=solved.strain_energy_j, external_work_j=solved.external_work_j,
    )


def test_shell_result_ir_is_hash_bound_and_authoritative() -> None:
    result = _result()
    assert validate_shell_result_ir(result) == result
    assert result.to_manifest()["authority"]["element_recovery"] == "authoritative"


def test_shell_result_ir_rejects_tampering() -> None:
    result = _result()
    with pytest.raises(ShellResultIRError, match="result_hash_mismatch"):
        validate_shell_result_ir(replace(result, maximum_free_residual=1.0))
