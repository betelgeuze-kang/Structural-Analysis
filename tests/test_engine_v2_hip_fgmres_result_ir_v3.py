from __future__ import annotations

import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

from jsonschema import Draft202012Validator
import numpy as np
import pytest

from structural_analysis.engine_v2.assembly_backend import (
    fgmres_result_ir_v3 as result_ir_v3,
)
from structural_analysis.engine_v2.assembly_backend.fgmres_model_case_terminal_metric_parity_v2 import (
    replay_hip_fgmres_detached_terminal_metric_parity_v2,
)
from structural_analysis.engine_v2.contracts._canonical import sha256_prefixed
from structural_analysis.engine_v2.contracts.result_ir_v2 import (
    ResultIRV2Error,
    SourceProvenance,
    _build_result_ir_v2_unvalidated_physics,
    validate_result_ir_v2_physics,
)
from structural_analysis.engine_v2.contracts.state_ir import (
    commit_trial_state,
    create_initial_state,
    open_trial_state,
)

from tests.test_engine_v2_fp64_csr_residual_normwise_v1 import _terminal_case


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = (
    ROOT / "src/structural_analysis/schemas" / "hip_fgmres_result_ir_v3.schema.json"
)


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode("utf-8")).hexdigest()


def _sources() -> tuple[object, ...]:
    plan, cpu, solution_x, true_residual, outcome, _row = _terminal_case(
        load_scale=10000.0,
        perturbation_fraction=0.25,
    )
    terminal = replay_hip_fgmres_detached_terminal_metric_parity_v2(
        execution_plan=plan,
        cpu_result=cpu,
        solution_x=solution_x,
        true_residual=true_residual,
        outcome=outcome,
    )
    free = plan.array("free_dofs")
    constrained = plan.array("constrained_dofs")
    solution = np.frombuffer(solution_x, dtype="<f8")
    exported = np.frombuffer(true_residual, dtype="<f8")
    displacement = np.zeros(plan.dof_count, dtype="<f8")
    displacement[free] = solution
    displacement[constrained] = 0.0
    initial = create_initial_state(plan)
    trial = open_trial_state(
        initial,
        displacement,
        load_step=1,
        iteration=cpu.iteration_count,
        load_factor=1.0,
        expected_plan=plan,
    )
    committed = commit_trial_state(initial, trial, expected_plan=plan)
    provenance = SourceProvenance(
        case_id=_hash("case"),
        case_parity_receipt_hash=_hash("case-receipt"),
        terminal_observation_receipt_hash=_hash("observation"),
        completion_export_receipt_hash=_hash("export-receipt"),
        completion_export_payload_hash=_hash("export-payload"),
        device_identity_receipt_hash=_hash("device"),
        solution_payload_sha256=sha256_prefixed(solution_x),
        exported_free_residual_payload_sha256=sha256_prefixed(true_residual),
        compiled_architecture="gfx1030",
        runtime_architecture_base="gfx1030",
        device_ordinal=0,
        device_uuid_bytes_hex="0123456789abcdef0123456789abcdef",
        device_pci_bdf="0000:03:00.0",
    )
    base = _build_result_ir_v2_unvalidated_physics(
        plan,
        trial,
        committed,
        displacement,
        exported,
        provenance,
        result_id="Result.synthetic-high-load.v2",
    )
    roundoff, witness = result_ir_v3._residual_chain_and_physics_witness(
        plan=plan,
        base=base,
        terminal=terminal,
        solution_x=solution_x,
        true_residual=true_residual,
        evaluated_trial_state=trial,
        committed_state=committed,
    )
    receipt = result_ir_v3._build_receipt(
        plan=plan,
        base=base,
        witness=witness,
        terminal=terminal,
        fsum_to_plan=roundoff,
        solution_x=solution_x,
        true_residual=true_residual,
    )
    return (
        plan,
        initial,
        trial,
        committed,
        base,
        terminal,
        roundoff,
        witness,
        receipt,
        solution_x,
        true_residual,
    )


def test_roundoff_aware_v3_preserves_frozen_v2_failure_and_validates_two_stage_chain() -> (
    None
):
    (
        plan,
        _initial,
        trial,
        committed,
        base,
        terminal,
        roundoff,
        witness,
        receipt,
        _solution_x,
        _true_residual,
    ) = _sources()

    with pytest.raises(ResultIRV2Error) as fixed:
        validate_result_ir_v2_physics(
            base,
            expected_plan=plan,
            expected_evaluated_trial_state=trial,
            expected_committed_state=committed,
        )
    assert fixed.value.code == "result_ir_v2_exported_residual_sign_mismatch"

    assert witness.result_ir_hash == (
        receipt.bindings.fixed_physics_witness_result_ir_hash
    )
    assert roundoff.receipt.summary.componentwise_bound_passed
    assert terminal.roundoff_replay.candidate_vs_independent_replay.receipt.summary.componentwise_bound_passed
    assert receipt.residual_validation.exported_to_fsum_componentwise_bound_verified
    assert (
        receipt.residual_validation.fsum_to_result_ir_plan_componentwise_bound_verified
    )
    assert receipt.residual_validation.fixed_physics_witness_verified
    assert not receipt.compatibility.retained_base_result_ir_ready
    assert not receipt.compatibility.result_ir_v2_fixed_residual_policy_relaxed


def test_v3_receipt_schema_is_strict_ready_scoped_and_nonpromoting() -> None:
    receipt = _sources()[8]
    assert result_ir_v3.validate_hip_fgmres_result_ir_receipt_v3(receipt) is receipt
    Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8"))).validate(
        receipt.to_dict()
    )
    assert receipt.claims.result_ir_v3_ready
    assert receipt.claims.exported_residual_roundoff_chain_verified
    assert not receipt.claims.general_restart_history_v2_verified
    assert not receipt.claims.commercial_ready
    assert not receipt.claims.promotion_eligible


def test_v3_result_requires_exact_factory_issuance_after_full_detached_replay() -> None:
    (
        plan,
        initial,
        trial,
        committed,
        base,
        terminal,
        roundoff,
        _witness,
        receipt,
        solution_x,
        true_residual,
    ) = _sources()
    direct = result_ir_v3.HipFgmresResultIRResultV3(
        receipt=receipt,
        base_result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_result_ir_plan_roundoff=roundoff,
        _source_execution_plan=plan,
        _source_solution_x=solution_x,
        _source_true_residual=true_residual,
        _source_case_identity_token=object(),
    )
    with pytest.raises(result_ir_v3.HipFgmresResultIRV3Error) as caught:
        result_ir_v3.validate_hip_fgmres_result_ir_v3(direct)
    assert caught.value.code == "hip_fgmres_result_ir_v3_issuance_unavailable"


def test_v3_validator_rejects_retained_export_payload_tamper_before_issuance() -> None:
    (
        plan,
        initial,
        trial,
        committed,
        base,
        terminal,
        roundoff,
        _witness,
        receipt,
        solution_x,
        true_residual,
    ) = _sources()
    tampered = bytearray(true_residual)
    tampered[0] ^= 1
    direct = result_ir_v3.HipFgmresResultIRResultV3(
        receipt=receipt,
        base_result_ir_v2=base,
        accepted_state=initial,
        evaluated_trial_state=trial,
        committed_state=committed,
        terminal_metric_parity=terminal,
        fsum_to_result_ir_plan_roundoff=roundoff,
        _source_execution_plan=plan,
        _source_solution_x=solution_x,
        _source_true_residual=bytes(tampered),
        _source_case_identity_token=object(),
    )
    with pytest.raises(result_ir_v3.HipFgmresResultIRV3Error) as caught:
        result_ir_v3.validate_hip_fgmres_result_ir_v3(direct)
    assert caught.value.code == "hip_fgmres_result_ir_v3_base_payload_mismatch"


def test_v2_model_case_and_v3_result_ir_public_exports_preserve_identity() -> None:
    from structural_analysis import engine_v2
    from structural_analysis.engine_v2 import assembly_backend
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_model_case_parity_v2 as model_case_v2,
    )

    expected = {
        "HipFgmresModelCaseParityResultV2": (
            model_case_v2.HipFgmresModelCaseParityResultV2
        ),
        "attest_hip_fgmres_model_case_parity_v2": (
            model_case_v2.attest_hip_fgmres_model_case_parity_v2
        ),
        "HipFgmresResultIRResultV3": result_ir_v3.HipFgmresResultIRResultV3,
        "build_hip_fgmres_result_ir_v3": result_ir_v3.build_hip_fgmres_result_ir_v3,
    }
    for name, value in expected.items():
        assert getattr(engine_v2, name) is value
        assert getattr(assembly_backend, name) is value
        assert name in engine_v2.__all__
        assert name in assembly_backend.__all__

    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))


def test_v2_model_case_and_v3_result_ir_package_bytes_and_isolated_exports(
    tmp_path: Path,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_model_case_parity_v2 as model_case_v2,
    )

    wheel_dir = tmp_path / "wheel"
    wheel_dir.mkdir()
    completed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-build-isolation",
            "-w",
            str(wheel_dir),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = tuple(wheel_dir.glob("*.whl"))
    assert len(wheels) == 1
    expected = {
        "structural_analysis/engine_v2/assembly_backend/fgmres_model_case_parity_v2.py": Path(
            inspect.getsourcefile(model_case_v2) or ""
        ),
        "structural_analysis/engine_v2/assembly_backend/fgmres_result_ir_v3.py": Path(
            inspect.getsourcefile(result_ir_v3) or ""
        ),
        "structural_analysis/schemas/hip_fgmres_model_case_parity_v2.schema.json": (
            ROOT
            / "src/structural_analysis/schemas"
            / "hip_fgmres_model_case_parity_v2.schema.json"
        ),
        "structural_analysis/schemas/hip_fgmres_result_ir_v3.schema.json": SCHEMA,
    }
    with ZipFile(wheels[0]) as archive:
        assert expected.keys() <= set(archive.namelist())
        for archive_path, source_path in expected.items():
            assert archive.read(archive_path) == source_path.read_bytes()

    install_root = tmp_path / "install"
    installed = subprocess.run(
        (
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_root),
            str(wheels[0]),
        ),
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr
    script = """
import importlib.resources
import inspect
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from structural_analysis import engine_v2
from structural_analysis.engine_v2 import assembly_backend
from structural_analysis.engine_v2.assembly_backend import fgmres_model_case_parity_v2 as model_case_v2
from structural_analysis.engine_v2.assembly_backend import fgmres_result_ir_v3 as result_ir_v3

expected = {
    "HipFgmresModelCaseParityResultV2": model_case_v2.HipFgmresModelCaseParityResultV2,
    "attest_hip_fgmres_model_case_parity_v2": model_case_v2.attest_hip_fgmres_model_case_parity_v2,
    "HipFgmresResultIRResultV3": result_ir_v3.HipFgmresResultIRResultV3,
    "build_hip_fgmres_result_ir_v3": result_ir_v3.build_hip_fgmres_result_ir_v3,
}
for name, value in expected.items():
    assert getattr(engine_v2, name) is value
    assert getattr(assembly_backend, name) is value
assert str(Path(inspect.getsourcefile(result_ir_v3)).resolve()).startswith(str(root))
schemas = importlib.resources.files("structural_analysis.schemas")
for name in ("hip_fgmres_model_case_parity_v2.schema.json", "hip_fgmres_result_ir_v3.schema.json"):
    json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))
print(len(engine_v2.__all__), len(assembly_backend.__all__))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    isolated = subprocess.run(
        (sys.executable, "-c", script, str(install_root)),
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert isolated.returncode == 0, isolated.stdout + isolated.stderr
    assert isolated.stdout.strip() == "1263 1071"
