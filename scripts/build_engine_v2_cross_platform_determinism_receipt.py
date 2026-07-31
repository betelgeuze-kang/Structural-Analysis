#!/usr/bin/env python3
"""Build and aggregate exact Engine v2 cross-platform determinism receipts."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform as platform_module
import re
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from structural_analysis.engine_v2.contracts._canonical import (  # noqa: E402
    array_data_hash,
    canonical_hash,
    sha256_prefixed,
)
from structural_analysis.engine_v2.contracts.equation_scaling import (  # noqa: E402
    bind_equation_scaling_to_execution_plan,
    create_equation_scaling,
    trace_scaled_residual,
)
from structural_analysis.engine_v2.contracts.execution_plan import (  # noqa: E402
    create_execution_plan,
)
from structural_analysis.engine_v2.contracts.execution_plan_reduced_csr import (  # noqa: E402
    create_execution_plan_reduced_csr,
)
from structural_analysis.engine_v2.contracts.state_ir import (  # noqa: E402
    create_initial_state,
)
from structural_analysis.engine_v2.contracts.state_ir_binary import (  # noqa: E402
    write_state_ir_binary_artifacts,
)
from structural_analysis.engine_v2.contracts.vector_artifact import (  # noqa: E402
    create_equation_scaling_vector_artifact_bundle,
    create_scaled_residual_vector_artifact_bundle,
    write_engine_v2_vector_artifacts,
)
from structural_analysis.engine_v2.cpu_fgmres import (  # noqa: E402
    run_cpu_fgmres,
    write_cpu_fgmres_solution_artifact,
)
from structural_analysis.api.nonlinear_frame import (  # noqa: E402
    COROTATIONAL_GENERAL_PROFILE,
    NonlinearFrameConfig,
    analyze_nonlinear_frame_model_ir,
    validate_nonlinear_frame_result,
)
from structural_analysis.model_ir import load_model_ir_v2  # noqa: E402
from structural_analysis.solvers.nonlinear.newton import (  # noqa: E402
    VECTOR_MATRIX_BACKEND,
)


RUN_SCHEMA_VERSION = "engine-v2-cross-platform-determinism-run-receipt.v1"
MATRIX_SCHEMA_VERSION = "engine-v2-cross-platform-determinism-matrix-receipt.v1"
MODEL_FIXTURE = Path("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
BOUNDED_PLANAR_FIXTURE = Path("examples/bounded_planar_frame_alpha.model-ir.v2.json")
BOUNDED_PLANAR_SETTLEMENT_FIXTURE = Path(
    "examples/bounded_planar_settlement.model-ir.v2.json"
)
EXPECTED_MODEL_FIXTURE_DATA_HASH = (
    "sha256:86459551b7607aeb0ce252340c6aa9a87c77645e2bc9817530b8cb16233314d9"
)
EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH = (
    "sha256:b568804a0aadb200d62fcdb4f664c98a7a3293d11fc5a8cb68501434866e906f"
)
EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH = (
    "sha256:c1a8a5a4ee59931f5ee4d40adde7d633687f6cdfc86fe745f00478546d53dbe8"
)
RUN_SCHEMA = Path(
    "src/structural_analysis/schemas/"
    "engine_v2_cross_platform_determinism_run_receipt_v1.schema.json"
)
MATRIX_SCHEMA = Path(
    "src/structural_analysis/schemas/"
    "engine_v2_cross_platform_determinism_matrix_receipt_v1.schema.json"
)
SUPPORTED_OS_LABELS = ("ubuntu-latest", "windows-latest")
SUPPORTED_PYTHON_VERSIONS = ("3.10", "3.12")
REQUIRED_COORDINATES = tuple(
    f"{os_label}|python-{python_version}"
    for os_label in SUPPORTED_OS_LABELS
    for python_version in SUPPORTED_PYTHON_VERSIONS
)
_EXPECTED_SYSTEM_BY_OS_LABEL = {
    "ubuntu-latest": "Linux",
    "windows-latest": "Windows",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{40}$")


EXPECTED_GOLDENS = {
    "model_ir_content_hash": (
        "sha256:43dfd7770d69075bc8f10ee6a7f903d6d66e39cf5d845eea78b976d04adb1610"
    ),
    "model_ir_semantic_hash": (
        "sha256:5a19491d252b3936135cc1da91338f23e6ca1db59e42b0cf2b4cbd0346e25cb2"
    ),
    "model_ir_provenance_hash": (
        "sha256:7af33051b9c4d241a5c8779006580e2de6b1727166f68a67385fff6412921c5c"
    ),
    "execution_plan_base_hash": (
        "sha256:60e4cc157967790e4e5174644b123883390cc7836716a9ff8e2d6cc0e0071e08"
    ),
    "execution_plan_bound_hash": (
        "sha256:cd36d0b85ca3e848ced0c9742794e32aed9565321e45d0ea494e4846121cbc58"
    ),
    "equation_scaling_hash": (
        "sha256:21c8fc1681f32f6c7d79346e4176d95d15f4628a5033ff10906cc9fda8174f80"
    ),
    "scale_vector_data_hash": (
        "sha256:38ace1f260bbd047b5e21c3b09ba090e7004b0751cbf07ec60a43e344c6b3ff5"
    ),
    "scale_vector_content_hash": (
        "sha256:a45fde62f21faab6b9c44c50c537ecde9df1147e4db229d1d4d89e78e4b390b8"
    ),
    "reduced_csr_identity_hash": (
        "sha256:48d4125e4955f94edb7cdc1307799cd4480b98e74f1cfec9eb440e54af97b43a"
    ),
    "state_ir_hash": (
        "sha256:8f822461444d60035971fa55800e140d9567cce86f00b678530eb22e8e390228"
    ),
    "state_binary_manifest_hash": (
        "sha256:2085ef5ead7a878c1f49fac008061e7834a857579cec7d940dc99fe255d3cc63"
    ),
    "scaled_residual_trace_hash": (
        "sha256:a223795a5c83356b67b7ee6892dfdbd00599d31b356768fac4e57d83ae664190"
    ),
    "scaling_vector_bundle_hash": (
        "sha256:7000220089feda744d8309c7ee375d8070953bdedabc9ff33c861dd8cd3892c1"
    ),
    "residual_vector_bundle_hash": (
        "sha256:b7bce23db6152a5b98e39e0acf5b55a8c4767208bbe90849b59ac3884bd98901"
    ),
    "cpu_fgmres_run_hash": (
        "sha256:4947e977ad88effbcf2daf2e6c04e7afe43ec864f856e49f79128d113713de9d"
    ),
    "cpu_fgmres_solution_data_hash": (
        "sha256:78c19f52f7328f8e639debdb3ea64e9779c3cc7d7c0690bf387009355df4bc2c"
    ),
    "bounded_planar_result_hash": (
        "sha256:117c90503a60a188758992fd0e1234796a1cb1913725ffa87f9d33b4f5f7c5b6"
    ),
    "bounded_planar_replay_result_hash": (
        "sha256:e1b1cc5400c072ebb18b0bcf7c6e455190c77e3ac088c805888f5c7d6a3772d6"
    ),
    "bounded_planar_checkpoint_artifact_hash": (
        "sha256:0d10a6029a91012164dc56098aaef790e57db5358b92de7b8255edfac3961547"
    ),
    "bounded_planar_checkpoint_chain_hash": (
        "sha256:cf48452dcb62e320b88406c56472c85dfbcf4c342e31ea1525d0e329e1b5cb90"
    ),
    "bounded_planar_engineering_result_hash": (
        "sha256:cc5bd7a004b0cb1de0c87982e8bb2f7fe83f7f97da8ee30725e8a10b55ae83aa"
    ),
    "bounded_planar_execution_topology_plan_hash": (
        "sha256:58c8f22de77b6474777cbaa1dbe5afc8b0b641314d0f4aea5bdbcebee1f51f94"
    ),
    "bounded_planar_equation_scaling_binding_hash": (
        "sha256:6e8421f1d94ea7726300baf1a60ecd8f2e80302a56e729e96487d3a4515e4f52"
    ),
    "bounded_planar_engine_equation_scaling_hash": (
        "sha256:2dd5dc37376146201d8203e38b2c9a872019a79142326952a176842d29d32f78"
    ),
    "bounded_planar_terminal_residual_trace_hash": (
        "sha256:3ff6e9971d4bd727ddff4507d18377e1f96d33031011765a3379638dcca5cc7c"
    ),
    "bounded_planar_model_ir_content_hash": (
        "sha256:4703d9137223345322db05cc37e8e53eb453d9bc67f12e88864c390ba3de66b7"
    ),
    "bounded_planar_model_ir_semantic_hash": (
        "sha256:fa0bfb2cf75d58ce406fe116dc4d463eac3568f3a8c32009afb51f5650daf08d"
    ),
    "bounded_planar_model_ir_provenance_hash": (
        "sha256:04a669a3a6deb764e9ea63d0215a563753a5bd74d0a68631001176821003938e"
    ),
    "bounded_planar_model_ir_adapter_hash": (
        "sha256:ddbd248df8b8340e14a11a88051e67dceddf0598270d77434ec67dbbcfa9be9d"
    ),
    "bounded_planar_execution_plan_binding_hash": (
        "sha256:bcc7c5c3e7b26c4c1d907e73ec352d4269f1be966c5e7f8e68132455ced6f1dd"
    ),
    "bounded_planar_settlement_result_hash": (
        "sha256:d1a1d9c51cf87d64b917ba789e4724b901ef2ca161d67943613248a98bbaf537"
    ),
    "bounded_planar_settlement_replay_result_hash": (
        "sha256:98e01640847327ca70cfac42cf89741235693cd1ba8b3638bceaf2df03eba006"
    ),
    "bounded_planar_settlement_checkpoint_artifact_hash": (
        "sha256:fbb7c5d068fc0ae8ad7a617e4f72d083e48a85f52644de25449767f1eafbbc13"
    ),
    "bounded_planar_settlement_checkpoint_chain_hash": (
        "sha256:e48590b945cffadbf5e4edac2288565793c39ea383416b76dad50d1794b2d477"
    ),
    "bounded_planar_settlement_engineering_result_hash": (
        "sha256:c0ea91d8b117f960350c784d17f74a17e0f39073f172dd3dae645d2fc18c5002"
    ),
    "bounded_planar_settlement_execution_topology_plan_hash": (
        "sha256:3dfd67bf543c98a63b2cb559857166e43c57dcfee616822e06749e283dd34fb6"
    ),
    "bounded_planar_settlement_equation_scaling_binding_hash": (
        "sha256:eadb3cad4c29768c70b2bd75e78500e95f21153913ec90b4681297c96ec203f5"
    ),
    "bounded_planar_settlement_engine_equation_scaling_hash": (
        "sha256:f36fc4a552c10a5c16cca842633bd0dbda813fcaf833627c41c249b35ac29efd"
    ),
    "bounded_planar_settlement_terminal_residual_trace_hash": (
        "sha256:9ee4b06c17f4c3a084c53732fa7a7457a6e005f0dc7d2bb2b2c2644b410f542a"
    ),
    "bounded_planar_settlement_model_ir_content_hash": (
        "sha256:a3745cf7a6e2023465bbcd232a620fa96e3bdf2a31976bb082a38f1e64176e06"
    ),
    "bounded_planar_settlement_model_ir_semantic_hash": (
        "sha256:5547a8be9e4fbf5ea2176e41adc9db3ec12931d3e327c1516c8b0cf11ab03b48"
    ),
    "bounded_planar_settlement_model_ir_provenance_hash": (
        "sha256:963127da36dd4de2004596ec523dec07099ad8bb652ead4686dd6a7f830fbc1c"
    ),
    "bounded_planar_settlement_model_ir_adapter_hash": (
        "sha256:effb190abe577aa11ad449bbfd16726a8df76c3420962489af36bd15baec309d"
    ),
    "bounded_planar_settlement_execution_plan_binding_hash": (
        "sha256:8ac07d8c1e940056a07c0434b75448551c2632dcc43ad80ab33e97e68fb7105a"
    ),
}

# Populated from canonical writer readback, then frozen as exact cross-platform
# byte goldens. The builder never derives expected values from the observation.
EXPECTED_BINARY_ARTIFACTS: dict[str, dict[str, Any]] = {
    "residual/raw_residual_si.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:196044e85112319248241e7575ed176d3e93ec3234fa07507ee53fa69db1344b"
        ),
    },
    "residual/scaled_residual.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:51be92e28d859bc49cf4896b33e0b2e12a7365e45b220a46021ef4b3fb7e9f60"
        ),
    },
    "scaling/scale_divisors_si.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:38ace1f260bbd047b5e21c3b09ba090e7004b0751cbf07ec60a43e344c6b3ff5"
        ),
    },
    "solution/solution_free.f64le": {
        "byte_length": 48,
        "data_hash": (
            "sha256:78c19f52f7328f8e639debdb3ea64e9779c3cc7d7c0690bf387009355df4bc2c"
        ),
    },
    "state/acceleration_si.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:2ea9ab9198d1638007400cd2c3bef1cc745b864b76011a0e1bc52180ac6452d4"
        ),
    },
    "state/constitutive_state.f64le": {
        "byte_length": 0,
        "data_hash": (
            "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ),
    },
    "state/displacement_si.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:2ea9ab9198d1638007400cd2c3bef1cc745b864b76011a0e1bc52180ac6452d4"
        ),
    },
    "state/velocity_si.f64le": {
        "byte_length": 96,
        "data_hash": (
            "sha256:2ea9ab9198d1638007400cd2c3bef1cc745b864b76011a0e1bc52180ac6452d4"
        ),
    },
}


def _hash(character: str) -> str:
    return "sha256:" + character * 64


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _git_head(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def _tracked_source_clean(repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "filter.lfs.process=",
                "-c",
                "filter.lfs.clean=cat",
                "-c",
                "filter.lfs.smudge=cat",
                "-c",
                "filter.lfs.required=false",
                "diff",
                "--quiet",
                "HEAD",
                "--",
            ],
            cwd=repo_root,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return False
    return result.returncode == 0


def _receipt_hash(payload: Mapping[str, Any]) -> str:
    without_hash = dict(payload)
    without_hash.pop("receipt_hash", None)
    return canonical_hash(without_hash)


def _with_receipt_hash(payload: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    result["receipt_hash"] = _receipt_hash(result)
    return result


def _schema_validator(repo_root: Path, schema_path: Path) -> Draft202012Validator:
    payload = json.loads((repo_root / schema_path).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(payload)
    return Draft202012Validator(payload)


def _validate_schema(
    payload: Mapping[str, Any], *, repo_root: Path, schema_path: Path
) -> None:
    validator = _schema_validator(repo_root, schema_path)
    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: tuple(str(item) for item in error.absolute_path),
    )
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(item) for item in first.absolute_path)
        raise ValueError(f"schema_invalid:{schema_path}:{path}:{first.message}")


def _record_artifact(
    output: dict[str, dict[str, Any]], *, key: str, path: Path
) -> None:
    data = path.read_bytes()
    output[key] = {
        "byte_length": len(data),
        "data_hash": sha256_prefixed(data),
    }


def _compute_bounded_planar_case_goldens(
    *,
    fixture: Path,
    golden_prefix: str,
    repo_root: Path = ROOT,
) -> dict[str, str]:
    """Replay one public ModelIR adapter case and its exact checkpoint bytes."""

    document = load_model_ir_v2(repo_root / fixture)
    config = NonlinearFrameConfig(
        profile=COROTATIONAL_GENERAL_PROFILE,
        load_steps=4,
        residual_tolerance=1.0e-9,
        maximum_iterations=60,
        matrix_backend=VECTOR_MATRIX_BACKEND,
    )
    result = analyze_nonlinear_frame_model_ir(document, config)
    if not validate_nonlinear_frame_result(result).contract_pass:
        raise RuntimeError(f"{golden_prefix}_cross_platform_result_blocked")
    checkpoint = result.checkpoint_artifact()
    replayed = analyze_nonlinear_frame_model_ir(
        document,
        config,
        restart_checkpoint_chain=checkpoint,
    )
    if not validate_nonlinear_frame_result(replayed).contract_pass:
        raise RuntimeError(f"{golden_prefix}_cross_platform_replay_blocked")
    if replayed.checkpoint_artifact() != checkpoint:
        raise RuntimeError(f"{golden_prefix}_cross_platform_checkpoint_replay_changed")
    if replayed.contract_bindings != result.contract_bindings:
        raise RuntimeError(f"{golden_prefix}_cross_platform_bindings_replay_changed")
    source_binding = result.contract_bindings.get("source_model_ir_adapter")
    if (
        not isinstance(source_binding, Mapping)
        or source_binding.get("model_ir_content_hash") != document.content_hash
        or source_binding.get("model_ir_semantic_hash") != document.semantic_hash
        or source_binding.get("model_ir_provenance_hash") != document.provenance_hash
    ):
        raise RuntimeError(f"{golden_prefix}_cross_platform_model_ir_binding_changed")
    for field_name in (
        "node_displacements",
        "support_reactions",
        "member_end_forces",
        "section_results",
        "fiber_results",
    ):
        if getattr(replayed, field_name) != getattr(result, field_name):
            raise RuntimeError(
                f"{golden_prefix}_cross_platform_recovery_replay_changed:{field_name}"
            )

    return {
        f"{golden_prefix}_result_hash": result.result_hash,
        f"{golden_prefix}_replay_result_hash": replayed.result_hash,
        f"{golden_prefix}_checkpoint_artifact_hash": sha256_prefixed(checkpoint),
        f"{golden_prefix}_checkpoint_chain_hash": str(result.checkpoint["chain_hash"]),
        f"{golden_prefix}_engineering_result_hash": str(
            result.contract_bindings["engineering_result_hash"]
        ),
        f"{golden_prefix}_execution_topology_plan_hash": str(
            result.contract_bindings["nonlinear_execution_topology_plan_hash"]
        ),
        f"{golden_prefix}_equation_scaling_binding_hash": str(
            result.contract_bindings["physical_equation_scaling_binding_hash"]
        ),
        f"{golden_prefix}_engine_equation_scaling_hash": str(
            result.contract_bindings["engine_equation_scaling_hash"]
        ),
        f"{golden_prefix}_terminal_residual_trace_hash": str(
            result.contract_bindings["terminal_physical_residual_trace_hash"]
        ),
        f"{golden_prefix}_model_ir_content_hash": document.content_hash,
        f"{golden_prefix}_model_ir_semantic_hash": document.semantic_hash,
        f"{golden_prefix}_model_ir_provenance_hash": document.provenance_hash,
        f"{golden_prefix}_model_ir_adapter_hash": str(source_binding["adapter_hash"]),
        f"{golden_prefix}_execution_plan_binding_hash": str(
            result.contract_bindings["bounded_planar_execution_plan"]["binding_hash"]
        ),
    }


def compute_bounded_planar_cross_platform_goldens(
    *,
    repo_root: Path = ROOT,
) -> dict[str, str]:
    """Replay both public bounded-planar member-feature and settlement cases."""

    return {
        **_compute_bounded_planar_case_goldens(
            fixture=BOUNDED_PLANAR_FIXTURE,
            golden_prefix="bounded_planar",
            repo_root=repo_root,
        ),
        **_compute_bounded_planar_case_goldens(
            fixture=BOUNDED_PLANAR_SETTLEMENT_FIXTURE,
            golden_prefix="bounded_planar_settlement",
            repo_root=repo_root,
        ),
    }


def compute_engine_v2_cross_platform_goldens(
    output_root: Path,
    *,
    repo_root: Path = ROOT,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Replay the fixed contract case and read back every binary artifact."""

    model = load_model_ir_v2(repo_root / MODEL_FIXTURE)
    dof_count = 12
    free = np.arange(6, dof_count, dtype="<i4")
    constrained = np.arange(6, dtype="<i4")
    global_to_free = np.full(dof_count, -1, dtype="<i4")
    global_to_free[free] = np.arange(free.size, dtype="<i4")
    base = create_execution_plan(
        model_ir_content_hash=model.content_hash,
        solver_buffer_schema_version="solver-model-buffers.v1",
        solver_numeric_buffer_hash=_hash("2"),
        solver_entity_mapping_hash=_hash("3"),
        solver_artifact_hash=_hash("4"),
        load_pattern_id="LC1",
        operator_id="linear-static-operator",
        operator_version="linear-static-operator.v1",
        operator_hash=_hash("5"),
        node_ids=("N1", "N2"),
        element_ids=("E1",),
        node_dof_indices=np.arange(dof_count, dtype="<i4").reshape(2, 6),
        global_to_free=global_to_free,
        element_global_dofs=np.arange(dof_count, dtype="<i4").reshape(1, 12),
        constrained_dofs=constrained,
        free_dofs=free,
        csr_row_ptr=np.arange(0, dof_count * dof_count + 1, dof_count, dtype="<i8"),
        csr_column_indices=np.tile(np.arange(dof_count, dtype="<i4"), dof_count),
    )
    coordinates = np.asarray([[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]], dtype="<f8")
    right_hand_side = np.zeros(dof_count, dtype="<f8")
    right_hand_side[6] = 4.0
    scaling = create_equation_scaling(
        execution_plan=base,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    bound = bind_equation_scaling_to_execution_plan(
        base,
        scaling,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
    )
    values = np.zeros(dof_count * dof_count, dtype="<f8")
    diagonal = [1.0] * 6 + [4.0, 4.0, 4.0, 8.0, 8.0, 8.0]
    for equation, value in enumerate(diagonal):
        values[equation * dof_count + equation] = value
    reduced = create_execution_plan_reduced_csr(
        bound,
        operator_numeric_values_hash=array_data_hash(values),
    )
    state = create_initial_state(bound)
    state_directory = output_root / "state"
    state_binary = write_state_ir_binary_artifacts(
        state,
        state_directory,
        artifact_uri_prefix="artifact://golden/state",
    )
    trace = trace_scaled_residual(
        execution_plan=bound,
        scaling=scaling,
        raw_residual_si=right_hand_side,
    )
    scaling_vectors = create_equation_scaling_vector_artifact_bundle(
        scaling, artifact_uri_prefix="artifact://golden/scaling"
    )
    scaling_directory = output_root / "scaling"
    write_engine_v2_vector_artifacts(scaling_vectors, scaling_directory)
    residual_vectors = create_scaled_residual_vector_artifact_bundle(
        trace, artifact_uri_prefix="artifact://golden/residual"
    )
    residual_directory = output_root / "residual"
    write_engine_v2_vector_artifacts(residual_vectors, residual_directory)
    fgmres = run_cpu_fgmres(
        execution_plan=bound,
        scaling=scaling,
        reduced_csr=reduced,
        node_coordinates_m=coordinates,
        reference_equation_load_si=right_hand_side,
        global_csr_values_si=values,
        right_hand_side_si=right_hand_side,
        solution_artifact_uri="artifact://golden/solution_free.f64le",
        max_iterations=6,
        restart_length=6,
        relative_tolerance_scaled_l2=1.0e-12,
        absolute_tolerance_scaled_l2=1.0e-14,
    )
    if fgmres.iteration_count != 1:
        raise RuntimeError("cross_platform_golden_iteration_count_changed")
    if fgmres.terminal_reason != "converged_scaled_residual":
        raise RuntimeError("cross_platform_golden_terminal_reason_changed")
    solution_path = output_root / "solution" / "solution_free.f64le"
    write_cpu_fgmres_solution_artifact(fgmres, solution_path)

    binary_artifacts: dict[str, dict[str, Any]] = {}
    for descriptor in state_binary.descriptors:
        filename = descriptor.artifact_uri.rsplit("/", 1)[-1]
        _record_artifact(
            binary_artifacts,
            key=f"state/{filename}",
            path=state_directory / filename,
        )
    for prefix, directory, bundle in (
        ("scaling", scaling_directory, scaling_vectors),
        ("residual", residual_directory, residual_vectors),
    ):
        for descriptor in bundle.descriptors:
            filename = descriptor.artifact_uri.rsplit("/", 1)[-1]
            _record_artifact(
                binary_artifacts,
                key=f"{prefix}/{filename}",
                path=directory / filename,
            )
    _record_artifact(
        binary_artifacts,
        key="solution/solution_free.f64le",
        path=solution_path,
    )

    goldens = {
        "model_ir_content_hash": model.content_hash,
        "model_ir_semantic_hash": model.semantic_hash,
        "model_ir_provenance_hash": model.provenance_hash,
        "execution_plan_base_hash": base.plan_hash,
        "execution_plan_bound_hash": bound.plan_hash,
        "equation_scaling_hash": scaling.scaling_hash,
        "scale_vector_data_hash": scaling.scale_vector_data_hash,
        "scale_vector_content_hash": scaling.scale_vector_content_hash,
        "reduced_csr_identity_hash": reduced.identity_hash,
        "state_ir_hash": state.state_hash,
        "state_binary_manifest_hash": state_binary.manifest_hash,
        "scaled_residual_trace_hash": trace.trace_hash,
        "scaling_vector_bundle_hash": scaling_vectors.bundle_hash,
        "residual_vector_bundle_hash": residual_vectors.bundle_hash,
        "cpu_fgmres_run_hash": fgmres.run_hash,
        "cpu_fgmres_solution_data_hash": fgmres.solution_descriptor.data_hash,
        **compute_bounded_planar_cross_platform_goldens(repo_root=repo_root),
    }
    return goldens, dict(sorted(binary_artifacts.items()))


def expected_golden_set_hash() -> str:
    return canonical_hash(
        {
            "model_fixture_data_hash": EXPECTED_MODEL_FIXTURE_DATA_HASH,
            "bounded_planar_fixture_data_hash": (
                EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH
            ),
            "bounded_planar_settlement_fixture_data_hash": (
                EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
            ),
            "goldens": EXPECTED_GOLDENS,
            "binary_artifacts": EXPECTED_BINARY_ARTIFACTS,
        }
    )


def _coordinate(os_label: str, python_version: str) -> str:
    return f"{os_label}|python-{python_version}"


def build_run_receipt(
    *,
    os_label: str,
    python_version: str,
    source_commit_sha: str,
    origin_kind: str = "local",
    run_id: str = "",
    run_attempt: int = 0,
    run_url: str = "",
    job: str = "",
    runner_name: str = "",
    repo_root: Path = ROOT,
    actual_system: str | None = None,
    actual_python_version: str | None = None,
    actual_python_implementation: str | None = None,
    platform_release: str | None = None,
    checkout_head_sha: str | None = None,
    tracked_source_clean: bool | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build one exact replay receipt; injectable identities are test seams."""

    repo_root = repo_root.resolve()
    system = actual_system or platform_module.system()
    actual_python = actual_python_version or platform_module.python_version()
    implementation = (
        actual_python_implementation or platform_module.python_implementation()
    )
    release = platform_release or platform_module.release()
    head_sha = (
        checkout_head_sha if checkout_head_sha is not None else _git_head(repo_root)
    )
    tracked_clean = (
        tracked_source_clean
        if tracked_source_clean is not None
        else _tracked_source_clean(repo_root)
    )
    with tempfile.TemporaryDirectory(prefix="engine-v2-cross-platform-golden-") as raw:
        observed_goldens, observed_binary_artifacts = (
            compute_engine_v2_cross_platform_goldens(
                Path(raw),
                repo_root=repo_root,
            )
        )
    observed_model_fixture_hash = sha256_prefixed(
        (repo_root / MODEL_FIXTURE).read_bytes()
    )
    observed_bounded_planar_fixture_hash = sha256_prefixed(
        (repo_root / BOUNDED_PLANAR_FIXTURE).read_bytes()
    )
    observed_bounded_planar_settlement_fixture_hash = sha256_prefixed(
        (repo_root / BOUNDED_PLANAR_SETTLEMENT_FIXTURE).read_bytes()
    )

    blockers: list[str] = []
    if os_label not in SUPPORTED_OS_LABELS:
        blockers.append(f"unsupported_os_label:{os_label}")
    expected_system = _EXPECTED_SYSTEM_BY_OS_LABEL.get(os_label)
    if expected_system is not None and system != expected_system:
        blockers.append(f"actual_system_mismatch:{system}!={expected_system}")
    if python_version not in SUPPORTED_PYTHON_VERSIONS:
        blockers.append(f"unsupported_python_version:{python_version}")
    actual_major_minor = ".".join(actual_python.split(".")[:2])
    if actual_major_minor != python_version:
        blockers.append(
            f"actual_python_version_mismatch:{actual_major_minor}!={python_version}"
        )
    if not _SHA256_RE.fullmatch(source_commit_sha):
        blockers.append("source_commit_sha_invalid")
    if head_sha != source_commit_sha:
        blockers.append("checkout_head_sha_mismatch")
    if not tracked_clean:
        blockers.append("tracked_source_tree_dirty")
    if observed_model_fixture_hash != EXPECTED_MODEL_FIXTURE_DATA_HASH:
        blockers.append("model_fixture_data_hash_mismatch")
    if (
        observed_bounded_planar_fixture_hash
        != EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH
    ):
        blockers.append("bounded_planar_fixture_data_hash_mismatch")
    if (
        observed_bounded_planar_settlement_fixture_hash
        != EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
    ):
        blockers.append("bounded_planar_settlement_fixture_data_hash_mismatch")
    for name in sorted(set(EXPECTED_GOLDENS) | set(observed_goldens)):
        if observed_goldens.get(name) != EXPECTED_GOLDENS.get(name):
            blockers.append(f"golden_hash_mismatch:{name}")
    for name in sorted(set(EXPECTED_BINARY_ARTIFACTS) | set(observed_binary_artifacts)):
        if observed_binary_artifacts.get(name) != EXPECTED_BINARY_ARTIFACTS.get(name):
            blockers.append(f"binary_artifact_mismatch:{name}")
    if origin_kind not in ("local", "github_actions"):
        blockers.append(f"origin_kind_invalid:{origin_kind}")
    if origin_kind == "github_actions":
        if not run_id:
            blockers.append("github_run_id_missing")
        if run_attempt < 1:
            blockers.append("github_run_attempt_invalid")
        if not run_url:
            blockers.append("github_run_url_missing")
        if not job:
            blockers.append("github_job_missing")

    exact_replay = not any(
        blocker.startswith(("golden_hash_mismatch:", "binary_artifact_mismatch:"))
        for blocker in blockers
    )
    contract_pass = not blockers
    receipt = _with_receipt_hash(
        {
            "schema_version": RUN_SCHEMA_VERSION,
            "generated_at": generated_at or _utc_now(),
            "source_commit_sha": source_commit_sha,
            "source_tree": {
                "checkout_head_sha": head_sha,
                "tracked_source_clean": tracked_clean,
            },
            "coordinate": {
                "coordinate_id": _coordinate(os_label, python_version),
                "os_label": os_label,
                "requested_python_version": python_version,
                "actual_system": system,
                "actual_python_version": actual_python,
                "python_implementation": implementation,
                "numpy_version": np.__version__,
                "platform_release": release,
            },
            "execution": {
                "origin_kind": origin_kind,
                "run_id": run_id,
                "run_attempt": run_attempt,
                "run_url": run_url,
                "job": job,
                "runner_name": runner_name,
            },
            "model_fixture": {
                "path": MODEL_FIXTURE.as_posix(),
                "expected_data_hash": EXPECTED_MODEL_FIXTURE_DATA_HASH,
                "observed_data_hash": observed_model_fixture_hash,
            },
            "bounded_planar_fixture": {
                "path": BOUNDED_PLANAR_FIXTURE.as_posix(),
                "expected_data_hash": EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH,
                "observed_data_hash": observed_bounded_planar_fixture_hash,
            },
            "bounded_planar_settlement_fixture": {
                "path": BOUNDED_PLANAR_SETTLEMENT_FIXTURE.as_posix(),
                "expected_data_hash": (
                    EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
                ),
                "observed_data_hash": (observed_bounded_planar_settlement_fixture_hash),
            },
            "golden_set_hash": expected_golden_set_hash(),
            "expected_goldens": dict(EXPECTED_GOLDENS),
            "observed_goldens": observed_goldens,
            "expected_binary_artifacts": dict(EXPECTED_BINARY_ARTIFACTS),
            "observed_binary_artifacts": observed_binary_artifacts,
            "contract_pass": contract_pass,
            "blockers": blockers,
            "claims": {
                "exact_contract_hash_replay": exact_replay,
                "canonical_binary_write_readback": (
                    observed_binary_artifacts == EXPECTED_BINARY_ARTIFACTS
                ),
                "github_actions_coordinate_execution": (
                    contract_pass and origin_kind == "github_actions"
                ),
                "bounded_planar_exact_replay": (
                    exact_replay
                    and observed_bounded_planar_fixture_hash
                    == EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH
                ),
                "bounded_planar_settlement_exact_replay": (
                    exact_replay
                    and observed_bounded_planar_settlement_fixture_hash
                    == EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
                ),
                "four_way_cross_platform_determinism": False,
                "cpu_hip_numerical_parity": False,
                "developer_preview_windows_gate": False,
            },
            "claim_boundary": (
                "This receipt covers one Engine v2 OS/Python coordinate, exact "
                "contract hashes, canonical binary write/readback, and exact public "
                "bounded-planar member-feature plus prescribed-settlement replay. "
                "A passing local receipt is local evidence only. A GitHub Actions "
                "coordinate receipt requires retained run provenance, and no single receipt "
                "proves the four-way matrix, CPU/HIP parity, hardware execution, "
                "or the Developer Preview Windows gate."
            ),
        }
    )
    _validate_schema(receipt, repo_root=repo_root, schema_path=RUN_SCHEMA)
    return receipt


def _load_run_receipts(
    receipts_directory: Path,
) -> tuple[list[tuple[Path, dict[str, Any]]], list[str]]:
    loaded: list[tuple[Path, dict[str, Any]]] = []
    blockers: list[str] = []
    for path in sorted(receipts_directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            blockers.append(
                f"receipt_json_invalid:{path.name}:{exc.__class__.__name__}"
            )
            continue
        if not isinstance(payload, dict):
            blockers.append(f"receipt_payload_invalid:{path.name}")
            continue
        loaded.append((path, payload))
    return loaded, blockers


def build_matrix_receipt(
    *,
    receipts_directory: Path,
    source_commit_sha: str,
    run_id: str,
    run_attempt: int,
    run_url: str,
    matrix_job_result: str,
    repo_root: Path = ROOT,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Aggregate exactly four retained GitHub Actions coordinate receipts."""

    repo_root = repo_root.resolve()
    loaded, blockers = _load_run_receipts(receipts_directory)
    if matrix_job_result != "success":
        blockers.append(f"matrix_job_result_not_success:{matrix_job_result}")
    if not _SHA256_RE.fullmatch(source_commit_sha):
        blockers.append("source_commit_sha_invalid")
    if not run_id:
        blockers.append("github_run_id_missing")
    if run_attempt < 1:
        blockers.append("github_run_attempt_invalid")
    if not run_url:
        blockers.append("github_run_url_missing")

    summaries: list[dict[str, Any]] = []
    coordinate_counts: dict[str, int] = {}
    for path, payload in loaded:
        try:
            _validate_schema(payload, repo_root=repo_root, schema_path=RUN_SCHEMA)
        except ValueError:
            blockers.append(f"run_receipt_schema_invalid:{path.name}")
            continue
        if payload.get("receipt_hash") != _receipt_hash(payload):
            blockers.append(f"run_receipt_hash_invalid:{path.name}")
            continue
        coordinate_payload = payload["coordinate"]
        coordinate = str(coordinate_payload["coordinate_id"])
        os_label = str(coordinate_payload["os_label"])
        requested_python = str(coordinate_payload["requested_python_version"])
        coordinate_counts[coordinate] = coordinate_counts.get(coordinate, 0) + 1
        if coordinate not in REQUIRED_COORDINATES:
            blockers.append(f"unexpected_coordinate:{coordinate}")
        if coordinate != _coordinate(os_label, requested_python):
            blockers.append(f"coordinate_identity_inconsistent:{coordinate}")
        expected_system = _EXPECTED_SYSTEM_BY_OS_LABEL.get(os_label)
        if coordinate_payload["actual_system"] != expected_system:
            blockers.append(f"coordinate_actual_system_invalid:{coordinate}")
        actual_major_minor = ".".join(
            str(coordinate_payload["actual_python_version"]).split(".")[:2]
        )
        if actual_major_minor != requested_python:
            blockers.append(f"coordinate_actual_python_invalid:{coordinate}")
        if not payload["contract_pass"]:
            blockers.append(f"coordinate_contract_blocked:{coordinate}")
        if not payload["claims"]["github_actions_coordinate_execution"]:
            blockers.append(f"coordinate_not_github_actions:{coordinate}")
        if not payload["claims"]["bounded_planar_exact_replay"]:
            blockers.append(f"coordinate_planar_replay_blocked:{coordinate}")
        if not payload["claims"]["bounded_planar_settlement_exact_replay"]:
            blockers.append(f"coordinate_planar_settlement_replay_blocked:{coordinate}")
        if payload["source_commit_sha"] != source_commit_sha:
            blockers.append(f"coordinate_source_commit_mismatch:{coordinate}")
        if payload["source_tree"]["checkout_head_sha"] != source_commit_sha:
            blockers.append(f"coordinate_checkout_head_mismatch:{coordinate}")
        if not payload["source_tree"]["tracked_source_clean"]:
            blockers.append(f"coordinate_source_tree_dirty:{coordinate}")
        execution = payload["execution"]
        if execution["origin_kind"] != "github_actions":
            blockers.append(f"coordinate_origin_invalid:{coordinate}")
        if execution["run_id"] != run_id:
            blockers.append(f"coordinate_run_id_mismatch:{coordinate}")
        if execution["run_attempt"] != run_attempt:
            blockers.append(f"coordinate_run_attempt_mismatch:{coordinate}")
        if execution["run_url"] != run_url:
            blockers.append(f"coordinate_run_url_mismatch:{coordinate}")
        if payload["golden_set_hash"] != expected_golden_set_hash():
            blockers.append(f"coordinate_golden_set_mismatch:{coordinate}")
        if payload["model_fixture"]["expected_data_hash"] != (
            EXPECTED_MODEL_FIXTURE_DATA_HASH
        ):
            blockers.append(f"coordinate_expected_fixture_mismatch:{coordinate}")
        if payload["model_fixture"]["observed_data_hash"] != (
            EXPECTED_MODEL_FIXTURE_DATA_HASH
        ):
            blockers.append(f"coordinate_observed_fixture_mismatch:{coordinate}")
        if payload["bounded_planar_fixture"]["expected_data_hash"] != (
            EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH
        ):
            blockers.append(f"coordinate_expected_planar_fixture_mismatch:{coordinate}")
        if payload["bounded_planar_fixture"]["observed_data_hash"] != (
            EXPECTED_BOUNDED_PLANAR_FIXTURE_DATA_HASH
        ):
            blockers.append(f"coordinate_observed_planar_fixture_mismatch:{coordinate}")
        if payload["bounded_planar_settlement_fixture"]["expected_data_hash"] != (
            EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
        ):
            blockers.append(
                f"coordinate_expected_planar_settlement_fixture_mismatch:{coordinate}"
            )
        if payload["bounded_planar_settlement_fixture"]["observed_data_hash"] != (
            EXPECTED_BOUNDED_PLANAR_SETTLEMENT_FIXTURE_DATA_HASH
        ):
            blockers.append(
                f"coordinate_observed_planar_settlement_fixture_mismatch:{coordinate}"
            )
        if payload["expected_goldens"] != EXPECTED_GOLDENS:
            blockers.append(f"coordinate_expected_goldens_mismatch:{coordinate}")
        if payload["observed_goldens"] != EXPECTED_GOLDENS:
            blockers.append(f"coordinate_observed_goldens_mismatch:{coordinate}")
        if payload["expected_binary_artifacts"] != EXPECTED_BINARY_ARTIFACTS:
            blockers.append(f"coordinate_expected_binary_mismatch:{coordinate}")
        if payload["observed_binary_artifacts"] != EXPECTED_BINARY_ARTIFACTS:
            blockers.append(f"coordinate_observed_binary_mismatch:{coordinate}")
        summaries.append(
            {
                "coordinate_id": coordinate,
                "receipt_file": path.name,
                "receipt_hash": payload["receipt_hash"],
                "contract_pass": payload["contract_pass"],
                "actual_system": payload["coordinate"]["actual_system"],
                "actual_python_version": payload["coordinate"]["actual_python_version"],
                "numpy_version": payload["coordinate"]["numpy_version"],
                "runner_name": execution["runner_name"],
            }
        )

    observed_coordinates = sorted(coordinate_counts)
    for coordinate in REQUIRED_COORDINATES:
        count = coordinate_counts.get(coordinate, 0)
        if count == 0:
            blockers.append(f"required_coordinate_missing:{coordinate}")
        elif count > 1:
            blockers.append(f"coordinate_duplicate:{coordinate}:{count}")
    if len(loaded) != len(REQUIRED_COORDINATES):
        blockers.append(
            f"run_receipt_count_mismatch:{len(loaded)}!={len(REQUIRED_COORDINATES)}"
        )

    blockers = sorted(set(blockers))
    contract_pass = not blockers
    receipt = _with_receipt_hash(
        {
            "schema_version": MATRIX_SCHEMA_VERSION,
            "generated_at": generated_at or _utc_now(),
            "source_commit_sha": source_commit_sha,
            "execution": {
                "origin_kind": "github_actions",
                "run_id": run_id,
                "run_attempt": run_attempt,
                "run_url": run_url,
                "matrix_job_result": matrix_job_result,
            },
            "required_coordinates": list(REQUIRED_COORDINATES),
            "observed_coordinates": observed_coordinates,
            "observed_coordinate_count": len(observed_coordinates),
            "golden_set_hash": expected_golden_set_hash(),
            "receipts": sorted(summaries, key=lambda row: row["coordinate_id"]),
            "contract_pass": contract_pass,
            "blockers": blockers,
            "claims": {
                "four_way_github_actions_exact_replay": contract_pass,
                "ubuntu_python_3_10_and_3_12_execution": contract_pass,
                "windows_python_3_10_and_3_12_execution": contract_pass,
                "cross_platform_contract_and_binary_hash_identity": contract_pass,
                "bounded_planar_four_way_exact_replay": contract_pass,
                "bounded_planar_settlement_four_way_exact_replay": contract_pass,
                "cpu_hip_numerical_parity": False,
                "developer_preview_windows_gate": False,
                "product_readiness": False,
            },
            "claim_boundary": (
                "A passing matrix receipt proves exact Engine v2 contract, "
                "canonical binary replay, and two solved bounded planar member-"
                "feature and prescribed-settlement result/checkpoint replays for "
                "the four hosted GitHub "
                "Actions Ubuntu/Windows and Python 3.10/3.12 coordinates from one "
                "clean source commit and one retained workflow run. The receipt remains "
                "dependent on the retained GitHub run and artifacts; it does not "
                "prove CPU/HIP parity, hardware execution, broader Linux/Windows "
                "product replay, Developer Preview closure, or product readiness."
            ),
        }
    )
    _validate_schema(receipt, repo_root=repo_root, schema_path=MATRIX_SCHEMA)
    return receipt


def _write_receipt(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(_json_text(payload))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Build one coordinate receipt.")
    run_parser.add_argument("--os-label", required=True, choices=SUPPORTED_OS_LABELS)
    run_parser.add_argument(
        "--python-version", required=True, choices=SUPPORTED_PYTHON_VERSIONS
    )
    run_parser.add_argument("--source-commit", required=True)
    run_parser.add_argument(
        "--origin-kind", choices=("local", "github_actions"), default="local"
    )
    run_parser.add_argument("--run-id", default="")
    run_parser.add_argument("--run-attempt", type=int, default=0)
    run_parser.add_argument("--run-url", default="")
    run_parser.add_argument("--job", default="")
    run_parser.add_argument("--runner-name", default="")
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--json", action="store_true")
    run_parser.add_argument("--fail-blocked", action="store_true")

    aggregate_parser = subparsers.add_parser(
        "aggregate", help="Aggregate the four GitHub Actions receipts."
    )
    aggregate_parser.add_argument("--receipts-dir", type=Path, required=True)
    aggregate_parser.add_argument("--source-commit", required=True)
    aggregate_parser.add_argument("--run-id", required=True)
    aggregate_parser.add_argument("--run-attempt", type=int, required=True)
    aggregate_parser.add_argument("--run-url", required=True)
    aggregate_parser.add_argument("--matrix-job-result", required=True)
    aggregate_parser.add_argument("--out", type=Path, required=True)
    aggregate_parser.add_argument("--json", action="store_true")
    aggregate_parser.add_argument("--fail-blocked", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        receipt = build_run_receipt(
            os_label=args.os_label,
            python_version=args.python_version,
            source_commit_sha=args.source_commit,
            origin_kind=args.origin_kind,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            run_url=args.run_url,
            job=args.job,
            runner_name=args.runner_name,
        )
    else:
        receipt = build_matrix_receipt(
            receipts_directory=args.receipts_dir,
            source_commit_sha=args.source_commit,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            run_url=args.run_url,
            matrix_job_result=args.matrix_job_result,
        )
    _write_receipt(args.out, receipt)
    if args.json:
        sys.stdout.write(_json_text(receipt))
    if args.fail_blocked and not receipt["contract_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
