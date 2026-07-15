from __future__ import annotations

import hashlib
from importlib import resources
import inspect
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_fixture_registry_v1 as registry_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_model_family_v1 as family_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_all_converged_result_ir_v1 as aggregate_module,
)
from structural_analysis.engine_v2.assembly_backend import (
    fgmres_fixture_registry_v1 as termination_registry_module,
)


ROOT = Path(__file__).resolve().parents[1]


def test_all_converged_public_names_are_identity_exported_from_both_namespaces() -> (
    None
):
    modules = (registry_module, family_module, aggregate_module)
    public_names = tuple(name for module in modules for name in module.__all__)

    assert len(public_names) == 42
    assert len(set(public_names)) == len(public_names)
    for module in modules:
        for name in module.__all__:
            value = getattr(module, name)
            assert getattr(assembly_backend, name) is value
            assert getattr(engine_v2, name) is value
            assert name in assembly_backend.__all__
            assert name in engine_v2.__all__


def test_all_converged_public_surface_excludes_private_authority_issuers() -> None:
    forbidden = {
        "_ISSUANCES",
        "_capture_case_source",
        "_capture_family_source",
        "_capture_hip_fgmres_all_converged_family_live_binding_v1",
        "_evaluate",
        "_evaluate_cases",
        "_FamilyIssuanceV1",
        "_AggregateIssuanceV1",
        "_FixedRegistryReplayTransactionIssuanceV1",
        "_FixedRegistryReplayTransactionV1",
        "_TRANSACTION_ISSUANCES",
        "_capture_family_live_binding_with_exact_registry_transaction_v1",
        "_issue_fixed_registry_replay_transaction_v1",
        "_recapture_family_live_binding_with_refreshed_registry_transaction_v1",
        "_refresh_family_registry_transaction_v1",
        "_refresh_fixed_registry_replay_transaction_v1",
        "_registry_from_fixed_replay_transaction_v1",
    }
    for namespace in (assembly_backend, engine_v2):
        assert forbidden.isdisjoint(namespace.__all__)
        assert all(not hasattr(namespace, name) for name in forbidden)


def test_all_converged_factories_do_not_accept_resource_or_policy_overrides() -> None:
    assert (
        inspect.signature(
            registry_module.load_hip_fgmres_all_converged_fixture_registry_v1
        ).parameters
        == {}
    )
    assert tuple(
        inspect.signature(
            registry_module.validate_hip_fgmres_all_converged_fixture_registry_result_v1
        ).parameters
    ) == ("result",)
    assert tuple(
        inspect.signature(
            family_module.attest_hip_fgmres_all_converged_model_family_v1
        ).parameters
    ) == ("case_results",)
    assert tuple(
        inspect.signature(
            aggregate_module.attest_hip_fgmres_all_converged_result_ir_v1
        ).parameters
    ) == ("family_result", "result_ir_bridges")


def test_all_converged_schemas_and_fixed_fixture_resources_are_packaged(
    tmp_path: Path,
) -> None:
    schema_root = resources.files("structural_analysis.schemas")
    schema_names = (
        "hip_fgmres_all_converged_fixture_registry_v1.schema.json",
        "hip_fgmres_all_converged_model_family_v1.schema.json",
        "hip_fgmres_all_converged_result_ir_v1.schema.json",
    )
    for schema_name in schema_names:
        assert schema_root.joinpath(schema_name).is_file()

    fixture_root = resources.files(
        "structural_analysis.engine_v2.assembly_backend.fixtures."
        "fgmres_all_converged_v1"
    )
    resources_found = tuple(
        sorted(
            entry.name
            for entry in fixture_root.iterdir()
            if entry.name.endswith(".json")
        )
    )
    assert resources_found == tuple(
        sorted(
            (
                "registry.v1.json",
                *(
                    f"{slot_id}.model.json"
                    for slot_id in registry_module.HIP_FGMRES_ALL_CONVERGED_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1
                ),
            )
        )
    )

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
            str(tmp_path),
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = tuple(tmp_path.glob("*.whl"))
    assert len(wheels) == 1

    fixture_package_path = (
        "structural_analysis/engine_v2/assembly_backend/fixtures/"
        "fgmres_all_converged_v1"
    )
    expected_sources = {
        **{
            f"{fixture_package_path}/{resource_name}": (
                ROOT / "src" / fixture_package_path / resource_name
            )
            for resource_name in resources_found
        },
        **{
            f"structural_analysis/schemas/{schema_name}": (
                ROOT / "src/structural_analysis/schemas" / schema_name
            )
            for schema_name in schema_names
        },
    }
    assert len(expected_sources) == 14
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        assert expected_sources.keys() <= names
        for archive_path, source_path in expected_sources.items():
            assert archive.read(archive_path) == source_path.read_bytes()


def test_historical_termination_registry_public_contract_remains_unchanged() -> None:
    package = resources.files(
        "structural_analysis.engine_v2.assembly_backend.fixtures.fgmres_family_v2"
    )
    digest = (
        "sha256:"
        + hashlib.sha256(package.joinpath("registry.v1.json").read_bytes()).hexdigest()
    )
    assert digest == (
        "sha256:bc12d11a15d23f2768e4c27e5f8449f88d26453f9579ebb741861a3176eae2fa"
    )
    assert digest == termination_registry_module._REGISTRY_RESOURCE_BYTES_SHA256
    assert termination_registry_module.HIP_FGMRES_FIXTURE_REGISTRY_REQUIRED_SLOT_IDS_V1[
        -2:
    ] == (
        "recurrence_later_restart_partial_final_cycle",
        "recurrence_exact_full_final_cycle_guard",
    )
