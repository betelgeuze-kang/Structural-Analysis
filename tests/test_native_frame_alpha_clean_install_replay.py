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


def _result() -> dict[str, object]:
    return {
        "schema_version": "structural-native-linear-frame3d-result-ir.v1",
        "result_id": "clean-install.LC_WEAK",
        "result_hash": "sha256:" + "1" * 64,
        "result_kind": "linear_static_frame3d",
        "authority_profile": "bounded_native_cpu_result_candidate.v1",
        "promotion_basis": "native_residual_free_residual_global_resultant_and_independent_recovery_gates.v1",
        "bindings": {
            "model_id": "frame-alpha-cantilever",
            "model_content_hash": "sha256:" + "2" * 64,
            "model_semantic_hash": "sha256:" + "3" * 64,
            "model_provenance_hash": "sha256:" + "4" * 64,
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
            "global_resultant_gate_passed": True,
            "independent_recovery_replay_passed": True,
            "fallback_count": 0,
            "regularization_count": 0,
        },
        "nodes": [{}, {}],
        "members": [{}],
    }


def _archive(tmp_path: Path, platform: str) -> Path:
    suffix = ".exe" if platform.startswith("windows") else ""
    binary_path = f"bin/structural-cli{suffix}"
    package_id = f"structural-frame-alpha-workstation-0.1.0-{platform}"
    result_bytes = json.dumps(_result(), sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    binary = b"#!/bin/sh\nprintf '%s\\n' '" + result_bytes + b"'\n"
    model = b'{"schema_version":"structural-model-ir.v2"}\n'
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
    assert payload["analysis_replay"]["result_hash"] == "sha256:" + "1" * 64
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
