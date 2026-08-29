from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import zipfile

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_native_frame_alpha_clean_install_replay.py"
SPEC = importlib.util.spec_from_file_location(
    "run_native_frame_alpha_clean_install_replay_test", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = replay
SPEC.loader.exec_module(replay)


SOURCE_COMMIT = "a" * 40
SOURCE_TREE = "b" * 40
MODEL_BYTES = (
    ROOT / "native/distribution/frame-alpha-cantilever.model-ir.json"
).read_bytes()
MODEL_PAYLOAD = replay._load_object(MODEL_BYTES, "test_model")
MODEL_IDENTITY = replay.clean_contract.derive_model_ir_identity(
    MODEL_PAYLOAD, expected_load_pattern_id="LC_WEAK"
)


def _result() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "structural-native-linear-frame3d-result-ir.v1",
        "result_id": "clean-install.LC_WEAK",
        "result_hash": "sha256:" + "0" * 64,
        "result_kind": "linear_static_frame3d",
        "authority_profile": "bounded_native_cpu_result_candidate.v1",
        "promotion_basis": "native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1",
        "bindings": {
            **MODEL_IDENTITY,
            "load_pattern_id": "LC_WEAK",
            "load_combination_id": None,
            "native_abi_version": 65541,
        },
        "solver": {
            "formulation": "linear_timoshenko_frame3d",
            "backend": "cpu_reference_dense",
            "residual_sign": "internal_minus_external",
            "unit_profile": "node_m_rad_force_n_nm_member_local_n_nm.v1",
        },
        "gates": {
            "native_residual_gate_passed": True,
            "free_residual_scaled_linf": 0.0,
            "free_residual_scaled_linf_tolerance": 1.0e-9,
            "global_force_balance_scaled_linf": 0.0,
            "global_force_balance_scaled_linf_tolerance": 1.0e-9,
            "global_moment_balance_scaled_linf": 0.0,
            "global_moment_balance_scaled_linf_tolerance": 1.0e-9,
            "global_resultant_gate_passed": True,
            "independent_recovery_replay_passed": True,
            "member_force_replay_scaled_linf": 0.0,
            "member_force_replay_scaled_linf_tolerance": 1.0e-9,
            "zero_prescribed_displacement_gate_passed": True,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "nodes": [
            {
                "node_id": "N1",
                "displacement_m_rad": [0.0] * 6,
                "reaction_n_nm": [0.0, 10_000.0, 0.0, 0.0, 0.0, 20_000.0],
            },
            {
                "node_id": "N2",
                "displacement_m_rad": [0.0, -0.01, 0.0, 0.0, 0.0, -0.005],
                "reaction_n_nm": [0.0] * 6,
            },
        ],
        "members": [
            {
                "member_id": "E1",
                "end_i_force_n_nm": [0.0, 10_000.0, 0.0, 0.0, 0.0, 20_000.0],
                "end_j_force_n_nm": [0.0, -10_000.0, 0.0, 0.0, 0.0, 0.0],
            }
        ],
        "authority": {
            "numerical_state": "bounded_candidate",
            "convergence": "bounded_candidate",
            "displacement": "bounded_candidate",
            "reaction": "bounded_candidate",
            "member_force": "bounded_candidate",
            "engineering_design": "not_authoritative",
            "code_compliance": "not_authoritative",
            "release_readiness": "not_authoritative",
            "commercial_use": "not_authoritative",
        },
        "claim_boundary": {
            "bounded_linear_static_timoshenko_frame3d": True,
            "cpu_only": True,
            "zero_prescribed_displacement_only": True,
            "nodal_load_only": False,
            "uniform_member_load_initial_local": True,
            "self_weight_standard_gravity": True,
            "linear_load_combination_superposition": True,
            "member_end_rotational_release": True,
            "rigid_member_end_offset": True,
            "reaction_from_global_residual": True,
            "member_force_from_native_local_recovery": True,
            "independent_recovery_replay": True,
            "cpu_hip_parity_established": False,
            "external_validation_established": False,
            "workbench_e2e": False,
            "release_readiness": False,
            "commercial_claim": False,
        },
    }
    _rehash(payload)
    return payload


def _rehash(payload: dict[str, object]) -> None:
    body = deepcopy(payload)
    body.pop("result_hash", None)
    payload["result_hash"] = replay._sha256_bytes(replay._canonical_bytes(body))


def _archive(
    tmp_path: Path,
    platform: str,
    *,
    result: dict[str, object] | None = None,
    result_schema: bytes | None = None,
) -> Path:
    suffix = ".exe" if platform.startswith("windows") else ""
    binary_path = f"bin/structural-cli{suffix}"
    package_id = f"structural-frame-alpha-workstation-0.1.0-{platform}"
    result_payload = result or _result()
    result_bytes = replay._canonical_bytes(result_payload)
    report = {
        "schema_version": "structural-native-linear-frame3d-report-ir.v1",
        "report_id": "clean-install.LC_WEAK.report",
        "source_result": {
            "schema_version": result_payload["schema_version"],
            "result_id": result_payload["result_id"],
            "result_hash": result_payload["result_hash"],
        },
    }
    report_bytes = replay._canonical_bytes(report)
    binary = (
        b"#!/bin/sh\n"
        b"test -f manifest.json || exit 91\n"
        b"if [ \"$1\" = result ]; then\n"
        b"  printf '%s\\n' '"
        + report_bytes
        + b"'\n"
        b"else\n"
        b"  printf '%s\\n' '"
        + result_bytes
        + b"'\n"
        b"fi\n"
    )
    model = MODEL_BYTES
    schema = result_schema or replay.RESULT_SCHEMA_PATH.read_bytes()
    manifest = {
        "package_id": package_id,
        "platform_tag": platform,
        "source": {
            "commit_sha": SOURCE_COMMIT,
            "tree_sha": SOURCE_TREE,
            "binding_profile": "verified_clean_git_checkout.v1",
        },
        "binary": {"path": binary_path},
        "files": [
            {"path": binary_path, "executable": True},
            {
                "path": "examples/frame-alpha-cantilever.model-ir.json",
                "executable": False,
            },
            {
                "path": "schemas/linear_frame3d_result_ir_v1.schema.json",
                "executable": False,
            },
        ],
    }
    archive = tmp_path / f"frame-alpha-workstation-{platform}.zip"
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as package:
        executable = zipfile.ZipInfo(f"{package_id}/{binary_path}")
        executable.external_attr = (stat.S_IFREG | 0o755) << 16
        package.writestr(executable, binary)
        example = zipfile.ZipInfo(
            f"{package_id}/examples/frame-alpha-cantilever.model-ir.json"
        )
        example.external_attr = (stat.S_IFREG | 0o644) << 16
        package.writestr(example, model)
        result_schema_info = zipfile.ZipInfo(
            f"{package_id}/schemas/linear_frame3d_result_ir_v1.schema.json"
        )
        result_schema_info.external_attr = (stat.S_IFREG | 0o644) << 16
        package.writestr(result_schema_info, schema)
        manifest_info = zipfile.ZipInfo(f"{package_id}/manifest.json")
        manifest_info.external_attr = (stat.S_IFREG | 0o644) << 16
        package.writestr(manifest_info, json.dumps(manifest).encode("utf-8"))
    return archive


def _fake_distribution(platform: str) -> SimpleNamespace:
    return SimpleNamespace(
        verify_workstation_distribution=lambda **_kwargs: {
            "schema_version": "structural-frame-alpha-workstation-distribution-smoke.v2",
            "status": "pass",
            "source": {
                "commit_sha": SOURCE_COMMIT,
                "tree_sha": SOURCE_TREE,
                "binding_profile": "verified_clean_git_checkout.v1",
            },
            "platform_tag": platform,
            "manifest_hash": "sha256:" + "5" * 64,
        }
    )


def _schema() -> dict[str, object]:
    return json.loads(
        (
            ROOT / "native/distribution/frame_alpha_clean_install_replay_v1.schema.json"
        ).read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("platform", ["linux-x86_64-gnu", "windows-x86_64-msvc"])
def test_clean_install_replay_is_source_bound_and_schema_valid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    archive = _archive(tmp_path, platform)
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )

    payload = replay.run_clean_install_replay(
        archive_path=archive,
        expected_source_commit=SOURCE_COMMIT,
        expected_platform_tag=platform,
        runner_profile="github_hosted_ephemeral",
    )

    Draft202012Validator(_schema()).validate(payload)
    assert payload["analysis_replay"]["byte_identical"] is True
    assert payload["analysis_replay"]["result_hash"] == _result()["result_hash"]
    assert payload["analysis_replay"]["result_id"] == "clean-install.LC_WEAK"
    assert payload["analysis_replay"]["model_id"] == MODEL_IDENTITY["model_id"]
    assert payload["analysis_replay"]["schema_and_hash_validation"] == "passed"
    assert payload["analysis_replay"]["persisted_result_contract_replay"] == "passed"
    assert payload["analysis_replay"]["packaged_example_identity_binding"] == "passed"
    assert payload["runner"]["network_isolation"] == "not_enforced"
    assert payload["runner"]["network_observation"] == "not_performed"
    assert payload["runner"]["network_used_during_replay"] is None
    assert payload["authority"]["portable_clean_runner_installation"] == "passed"
    assert payload["authority"]["release_readiness"] == "not_authoritative"


def test_clean_install_replay_rejects_source_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = "linux-x86_64-gnu"
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(
        replay.CleanInstallReplayError, match="package_source_or_platform_mismatch"
    ):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform),
            expected_source_commit="c" * 40,
            expected_platform_tag=platform,
            runner_profile="github_hosted_ephemeral",
        )


def test_clean_install_schema_rejects_release_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = "linux-x86_64-gnu"
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    payload = replay.run_clean_install_replay(
        archive_path=_archive(tmp_path, platform),
        expected_source_commit=SOURCE_COMMIT,
        expected_platform_tag=platform,
        runner_profile="local_isolated_test",
    )
    promoted = deepcopy(payload)
    promoted["authority"]["release_readiness"] = "passed"
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(promoted)


def test_replay_rejects_stale_result_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = "linux-x86_64-gnu"
    result = _result()
    result["nodes"][1]["displacement_m_rad"][1] = -0.02
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(replay.CleanInstallReplayError, match="result_hash_mismatch"):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform, result=result),
            expected_source_commit=SOURCE_COMMIT,
            expected_platform_tag=platform,
            runner_profile="local_isolated_test",
        )


@pytest.mark.parametrize(
    "mutation,expected",
    [
        (
            lambda result: result["nodes"][0].pop("reaction_n_nm"),
            "clean_install_result_schema_required",
        ),
        (
            lambda result: result["authority"].update(
                {"release_readiness": "passed"}
            ),
            "clean_install_result_schema_const",
        ),
    ],
)
def test_replay_rejects_schema_invalid_result_even_with_coherent_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation,
    expected: str,
) -> None:
    platform = "linux-x86_64-gnu"
    result = _result()
    mutation(result)
    _rehash(result)
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(replay.CleanInstallReplayError, match=expected):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform, result=result),
            expected_source_commit=SOURCE_COMMIT,
            expected_platform_tag=platform,
            runner_profile="local_isolated_test",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda result: result.update({"result_id": "foreign-result"}),
        lambda result: result["bindings"].update({"model_id": "foreign-model"}),
        lambda result: result["bindings"].update(
            {"model_content_hash": "sha256:" + "f" * 64}
        ),
        lambda result: result["bindings"].update({"load_pattern_id": "LC_OTHER"}),
    ],
)
def test_replay_rejects_valid_result_not_bound_to_requested_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation
) -> None:
    platform = "linux-x86_64-gnu"
    result = _result()
    mutation(result)
    _rehash(result)
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(
        replay.CleanInstallReplayError,
        match="result_requested_example_binding_invalid",
    ):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform, result=result),
            expected_source_commit=SOURCE_COMMIT,
            expected_platform_tag=platform,
            runner_profile="local_isolated_test",
        )


def test_replay_rejects_duplicate_entity_identity_after_schema_and_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = "linux-x86_64-gnu"
    result = _result()
    result["nodes"][1]["node_id"] = "N1"
    _rehash(result)
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(replay.CleanInstallReplayError, match="result_duplicate_node_id"):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform, result=result),
            expected_source_commit=SOURCE_COMMIT,
            expected_platform_tag=platform,
            runner_profile="local_isolated_test",
        )


def test_replay_rejects_packaged_result_schema_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform = "linux-x86_64-gnu"
    schema = replay.RESULT_SCHEMA_PATH.read_bytes() + b"\n"
    monkeypatch.setattr(
        replay, "_load_distribution_module", lambda: _fake_distribution(platform)
    )
    with pytest.raises(
        replay.CleanInstallReplayError, match="packaged_result_schema_source_mismatch"
    ):
        replay.run_clean_install_replay(
            archive_path=_archive(tmp_path, platform, result_schema=schema),
            expected_source_commit=SOURCE_COMMIT,
            expected_platform_tag=platform,
            runner_profile="local_isolated_test",
        )
