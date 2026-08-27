from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from jsonschema import Draft202012Validator, ValidationError


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "compare_native_frame_alpha_clean_install_replays.py"
SPEC = importlib.util.spec_from_file_location(
    "compare_native_frame_alpha_clean_install_replays_test", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
comparison = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = comparison
SPEC.loader.exec_module(comparison)


SOURCE_COMMIT = "a" * 40
SOURCE_TREE = "b" * 40


def _replay(platform: str) -> dict[str, object]:
    return {
        "schema_version": "structural-frame-alpha-clean-install-replay.v1",
        "status": "pass",
        "source": {
            "commit_sha": SOURCE_COMMIT,
            "tree_sha": SOURCE_TREE,
            "binding_profile": "verified_clean_git_checkout.v1",
        },
        "platform_tag": platform,
        "runner": {
            "profile": "github_hosted_ephemeral",
            "fresh_extraction_directory": True,
            "source_build_output_used": False,
            "network_isolation": "not_enforced",
            "network_observation": "not_performed",
            "network_used_during_replay": None,
        },
        "archive": {
            "sha256": "sha256:" + ("1" if platform.startswith("linux") else "2") * 64,
            "byte_length": 1000,
            "package_id": f"structural-frame-alpha-workstation-0.1.0-{platform}",
            "manifest_hash": "sha256:"
            + ("3" if platform.startswith("linux") else "4") * 64,
        },
        "package_smoke": {
            "schema_version": "structural-frame-alpha-workstation-distribution-smoke.v2",
            "receipt_sha256": "sha256:" + "5" * 64,
            "loopback_static_and_capability_smoke": "passed",
        },
        "analysis_replay": {
            "repeat_count": 2,
            "byte_identical": True,
            "canonical_result_sha256": "sha256:" + "6" * 64,
            "result_schema_sha256": "sha256:" + "b" * 64,
            "schema_and_hash_validation": "passed",
            "persisted_result_contract_replay": "passed",
            "packaged_example_identity_binding": "passed",
            "schema_version": "structural-native-linear-frame3d-result-ir.v1",
            "authority_profile": "bounded_native_cpu_result_candidate.v1",
            "result_id": "clean-install.LC_WEAK",
            "model_id": "frame-alpha-distribution-cantilever",
            "result_hash": "sha256:" + "7" * 64,
            "model_content_hash": "sha256:" + "8" * 64,
            "model_semantic_hash": "sha256:" + "9" * 64,
            "model_provenance_hash": "sha256:" + "a" * 64,
            "load_pattern_id": "LC_WEAK",
            "load_combination_id": None,
            "native_abi_version": 65541,
            "solver": {
                "formulation": "linear_timoshenko_frame3d",
                "backend": "cpu_reference_dense",
                "residual_sign": "internal_minus_external",
                "unit_profile": "node_m_rad_force_n_nm_member_local_n_nm.v1",
            },
            "node_count": 2,
            "member_count": 1,
        },
        "authority": {
            "portable_clean_runner_installation": "passed",
            "same_source_linux_windows_parity": "not_established_by_one_receipt",
            "browser_execution": "not_evaluated",
            "os_code_signing": "not_evaluated",
            "artifact_attestation": "not_evaluated_in_runner_receipt",
            "automatic_update": "not_implemented",
            "rollback": "not_implemented",
            "engineering_design": "not_authoritative",
            "commercial_use": "not_authoritative",
            "release_readiness": "not_authoritative",
        },
        "claim_boundary": (
            "one_source_bound_portable_workstation_archive_verified_and_replayed_twice_"
            "from_a_fresh_extraction_on_one_runner_without_network_isolation_or_offline_"
            "observation_not_cross_platform_browser_code_signing_update_rollback_or_"
            "release_authority"
        ),
    }


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _schema() -> dict[str, object]:
    return json.loads(
        (
            ROOT
            / "native/distribution/frame_alpha_clean_install_cross_platform_v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def test_compare_replays_requires_exact_same_source_result(
    tmp_path: Path,
) -> None:
    paths = [
        _write(tmp_path / "linux.json", _replay("linux-x86_64-gnu")),
        _write(tmp_path / "windows.json", _replay("windows-x86_64-msvc")),
    ]
    payload = comparison.compare_replays(
        receipt_paths=paths, expected_source_commit=SOURCE_COMMIT
    )

    Draft202012Validator(_schema()).validate(payload)
    assert all(payload["matching"].values())
    assert payload["authority"]["same_source_linux_windows_result_parity"] == "passed"
    assert payload["authority"]["os_code_signing"] == "not_evaluated"


def test_compare_replays_rejects_result_drift(tmp_path: Path) -> None:
    windows = _replay("windows-x86_64-msvc")
    windows["analysis_replay"]["result_hash"] = "sha256:" + "f" * 64
    paths = [
        _write(tmp_path / "linux.json", _replay("linux-x86_64-gnu")),
        _write(tmp_path / "windows.json", windows),
    ]
    with pytest.raises(
        comparison.CrossPlatformReplayError,
        match="cross_platform_result_mismatch:result_hash",
    ):
        comparison.compare_replays(
            receipt_paths=paths, expected_source_commit=SOURCE_COMMIT
        )


def test_compare_replays_rejects_duplicate_coordinate(tmp_path: Path) -> None:
    paths = [
        _write(tmp_path / "linux-1.json", _replay("linux-x86_64-gnu")),
        _write(tmp_path / "linux-2.json", _replay("linux-x86_64-gnu")),
    ]
    with pytest.raises(
        comparison.CrossPlatformReplayError, match="receipt_contract_invalid"
    ):
        comparison.compare_replays(
            receipt_paths=paths, expected_source_commit=SOURCE_COMMIT
        )


def test_cross_platform_schema_rejects_code_signing_promotion(
    tmp_path: Path,
) -> None:
    payload = comparison.compare_replays(
        receipt_paths=[
            _write(tmp_path / "linux.json", _replay("linux-x86_64-gnu")),
            _write(tmp_path / "windows.json", _replay("windows-x86_64-msvc")),
        ],
        expected_source_commit=SOURCE_COMMIT,
    )
    promoted = deepcopy(payload)
    promoted["authority"]["os_code_signing"] = "passed"
    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(promoted)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda receipt: receipt.pop("package_smoke"),
        lambda receipt: receipt["archive"].update({"sha256": "not-a-hash"}),
        lambda receipt: receipt["runner"].update(
            {"network_used_during_replay": True}
        ),
        lambda receipt: receipt["authority"].update(
            {"release_readiness": "passed"}
        ),
        lambda receipt: receipt["analysis_replay"].pop(
            "packaged_example_identity_binding"
        ),
    ],
)
def test_compare_replays_rejects_any_input_receipt_schema_violation(
    tmp_path: Path, mutation
) -> None:
    linux = _replay("linux-x86_64-gnu")
    mutation(linux)
    paths = [
        _write(tmp_path / "linux.json", linux),
        _write(tmp_path / "windows.json", _replay("windows-x86_64-msvc")),
    ]
    with pytest.raises(
        comparison.CrossPlatformReplayError, match="receipt_schema_invalid"
    ):
        comparison.compare_replays(
            receipt_paths=paths, expected_source_commit=SOURCE_COMMIT
        )


def test_compare_replays_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    valid = json.dumps(_replay("linux-x86_64-gnu"), separators=(",", ":"))
    duplicate = valid.replace(
        '"schema_version":"structural-frame-alpha-clean-install-replay.v1"',
        '"schema_version":"structural-frame-alpha-clean-install-replay.v1",'
        '"schema_version":"structural-frame-alpha-clean-install-replay.v1"',
        1,
    )
    linux = tmp_path / "linux.json"
    linux.write_text(duplicate, encoding="utf-8")
    windows = _write(
        tmp_path / "windows.json", _replay("windows-x86_64-msvc")
    )
    with pytest.raises(comparison.CrossPlatformReplayError, match="invalid_receipt"):
        comparison.compare_replays(
            receipt_paths=[linux, windows], expected_source_commit=SOURCE_COMMIT
        )
