from __future__ import annotations

import inspect
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (
    ROOT
    / "src/structural_analysis/engine_v2/assembly_backend/fixtures"
    / "fgmres_high_load_compatibility_v1"
)


def test_high_load_registry_and_aggregate_public_exports_preserve_identity() -> None:
    from structural_analysis import engine_v2
    from structural_analysis.engine_v2 import assembly_backend
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_high_load_compatibility_registry_v1 as registry,
    )
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_high_load_result_ir_aggregate_v1 as aggregate,
    )

    expected = {
        "HipFgmresHighLoadCompatibilityRegistryResultV1": (
            registry.HipFgmresHighLoadCompatibilityRegistryResultV1
        ),
        "load_hip_fgmres_high_load_compatibility_registry_v1": (
            registry.load_hip_fgmres_high_load_compatibility_registry_v1
        ),
        "HipFgmresHighLoadResultIRAggregateResultV1": (
            aggregate.HipFgmresHighLoadResultIRAggregateResultV1
        ),
        "attest_hip_fgmres_high_load_result_ir_aggregate_v1": (
            aggregate.attest_hip_fgmres_high_load_result_ir_aggregate_v1
        ),
    }
    for name, value in expected.items():
        assert getattr(engine_v2, name) is value
        assert getattr(assembly_backend, name) is value
        assert name in engine_v2.__all__
        assert name in assembly_backend.__all__
    assert len(engine_v2.__all__) == 1196
    assert len(assembly_backend.__all__) == 1004
    assert len(engine_v2.__all__) == len(set(engine_v2.__all__))
    assert len(assembly_backend.__all__) == len(set(assembly_backend.__all__))
    assert "_HighLoadRegistryTransactionV1" not in registry.__all__
    assert "_AggregateIssuanceV1" not in aggregate.__all__


def test_high_load_registry_and_aggregate_wheel_resources_and_isolated_replay(
    tmp_path: Path,
) -> None:
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_high_load_compatibility_registry_v1 as registry,
    )
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_high_load_result_ir_aggregate_v1 as aggregate,
    )
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_restart_trace_ir_v1 as trace_v1,
    )
    from structural_analysis.engine_v2.assembly_backend import (
        fgmres_external_trust_anchor_registry_v3 as registry_v3,
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
        "structural_analysis/engine_v2/assembly_backend/fgmres_high_load_compatibility_registry_v1.py": Path(
            inspect.getsourcefile(registry) or ""
        ),
        "structural_analysis/engine_v2/assembly_backend/fgmres_high_load_result_ir_aggregate_v1.py": Path(
            inspect.getsourcefile(aggregate) or ""
        ),
        "structural_analysis/engine_v2/assembly_backend/fgmres_restart_trace_ir_v1.py": Path(
            inspect.getsourcefile(trace_v1) or ""
        ),
        "structural_analysis/engine_v2/assembly_backend/fgmres_external_trust_anchor_registry_v3.py": Path(
            inspect.getsourcefile(registry_v3) or ""
        ),
        "structural_analysis/schemas/hip_fgmres_high_load_compatibility_registry_v1.schema.json": (
            ROOT
            / "src/structural_analysis/schemas"
            / "hip_fgmres_high_load_compatibility_registry_v1.schema.json"
        ),
        "structural_analysis/schemas/hip_fgmres_high_load_result_ir_aggregate_v1.schema.json": (
            ROOT
            / "src/structural_analysis/schemas"
            / "hip_fgmres_high_load_result_ir_aggregate_v1.schema.json"
        ),
        **{
            "structural_analysis/schemas/" + name: (
                ROOT / "src/structural_analysis/schemas" / name
            )
            for name in (
                "hip_fgmres_checkpoint_history_plan_v1.schema.json",
                "cpu_fgmres_checkpoint_history_v2.schema.json",
                "hip_fgmres_checkpoint_history_context_v1.schema.json",
                "hip_fgmres_completion_export_v2.schema.json",
                "hip_fgmres_general_history_parity_v2.schema.json",
                "hip_fgmres_restart_trace_ir_v1.schema.json",
                "hip_fgmres_external_trust_anchor_registry_v3.schema.json",
            )
        },
        "structural_analysis/engine_v2/assembly_backend/kernels/engine_v2_fgmres_checkpoint_history_v1.hip.cpp": (
            ROOT
            / "src/structural_analysis/engine_v2/assembly_backend/kernels"
            / "engine_v2_fgmres_checkpoint_history_v1.hip.cpp"
        ),
        **{
            "structural_analysis/engine_v2/assembly_backend/fixtures/fgmres_high_load_compatibility_v1/"
            + path.name: path
            for path in sorted(FIXTURE_DIR.glob("*.json"))
        },
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
    script = r"""
import importlib.resources
import inspect
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from structural_analysis import engine_v2
from structural_analysis.engine_v2 import assembly_backend
from structural_analysis.engine_v2.assembly_backend import fgmres_high_load_compatibility_registry_v1 as registry
from structural_analysis.engine_v2.assembly_backend import fgmres_high_load_result_ir_aggregate_v1 as aggregate
from structural_analysis.engine_v2.assembly_backend import fgmres_restart_trace_ir_v1 as trace_v1
from structural_analysis.engine_v2.assembly_backend import fgmres_external_trust_anchor_registry_v3 as registry_v3

assert engine_v2.load_hip_fgmres_high_load_compatibility_registry_v1 is registry.load_hip_fgmres_high_load_compatibility_registry_v1
assert assembly_backend.attest_hip_fgmres_high_load_result_ir_aggregate_v1 is aggregate.attest_hip_fgmres_high_load_result_ir_aggregate_v1
assert engine_v2.build_hip_fgmres_restart_trace_ir_v1 is trace_v1.build_hip_fgmres_restart_trace_ir_v1
assert assembly_backend.validate_hip_fgmres_restart_trace_ir_receipt_v1 is trace_v1.validate_hip_fgmres_restart_trace_ir_receipt_v1
assert engine_v2.verify_hip_fgmres_external_trust_anchor_registry_activation_v3 is registry_v3.verify_hip_fgmres_external_trust_anchor_registry_activation_v3
assert str(Path(inspect.getsourcefile(registry)).resolve()).startswith(str(root))
schemas = importlib.resources.files("structural_analysis.schemas")
for name in (
    "hip_fgmres_high_load_compatibility_registry_v1.schema.json",
    "hip_fgmres_high_load_result_ir_aggregate_v1.schema.json",
    "hip_fgmres_checkpoint_history_plan_v1.schema.json",
    "cpu_fgmres_checkpoint_history_v2.schema.json",
    "hip_fgmres_checkpoint_history_context_v1.schema.json",
    "hip_fgmres_completion_export_v2.schema.json",
    "hip_fgmres_general_history_parity_v2.schema.json",
    "hip_fgmres_restart_trace_ir_v1.schema.json",
    "hip_fgmres_external_trust_anchor_registry_v3.schema.json",
):
    json.loads(schemas.joinpath(name).read_text(encoding="utf-8"))
replayed = registry.load_hip_fgmres_high_load_compatibility_registry_v1()
assert len(replayed.slots) == 3
assert sum(slot.execution_plan.dof_count for slot in replayed.slots) == 78
print(len(engine_v2.__all__), len(assembly_backend.__all__), replayed.registry_hash)
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
    assert isolated.stdout.strip() == (
        "1196 1004 sha256:72ea556471edb72a2262f870e76d4fc423e9d665da82f6d8e4d03dd6ae953f9e"
    )
