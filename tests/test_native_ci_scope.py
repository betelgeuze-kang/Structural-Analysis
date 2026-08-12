from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


scope = _load_script("classify_native_ci_scope")
boundary = _load_script("check_native_dependency_boundary")


def _write_compatibility_owners(root: Path) -> None:
    entries = []
    for legacy_manifest, owner in boundary.EXPECTED_COMPATIBILITY_OWNERS.items():
        manifest = root / legacy_manifest
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("[package]\nname = \"legacy\"\n", encoding="utf-8")
        entries.append(
            {
                "legacy_manifest": legacy_manifest,
                "migration_owner": owner,
                "legacy_abi_preserved": True,
                "removal_allowed": False,
            }
        )
    path = root / "native" / "compatibility-owners.json"
    path.write_text(
        json.dumps({"entries": entries}),
        encoding="utf-8",
    )


def test_scope_classifies_language_and_product_boundaries() -> None:
    payload = scope.classify_paths(
        [
            "native/Cargo.toml",
            "native/crates/structural-runtime/src/lib.rs",
            "native/cpp/include/structural/abi_v1.h",
            "native/cpp/src/model_ir/model.cpp",
            "native/cpp/hip/operators/residual.hip.cpp",
            "src/structural_analysis/model_ir/loader.py",
        ]
    )

    assert payload["changed_paths"] == sorted(payload["changed_paths"])
    for key in ("native", "rust", "cpp", "abi", "modelir", "runtime", "hip", "oracle"):
        assert payload[key] is True
    assert payload["protected_evidence"] is False
    assert payload["docs_only"] is False


def test_capability_promotion_routes_through_modelir_gates() -> None:
    payload = scope.classify_paths(["native/capabilities.json"])

    assert payload["native"] is True
    assert payload["modelir"] is True
    assert payload["applicable"] is True


def test_track_python_parity_boundary_routes_through_the_oracle_gate() -> None:
    payload = scope.classify_paths(
        ["tests/test_native_track_point_load_python_parity.py"]
    )

    assert payload["modelir"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_nonlinear_python_parity_boundary_routes_through_the_oracle_gate() -> None:
    payload = scope.classify_paths(
        [
            "tests/native_oracles/nonlinear_ndtha_story_frame.py",
            "tests/native_oracles/nonlinear_static_story_frame.py",
            "tests/test_native_nonlinear_ndtha_python_parity.py",
            "tests/test_native_nonlinear_static_python_parity.py",
        ]
    )

    assert payload["modelir"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_mgt_import_oracle_and_fixture_route_through_modelir_gates() -> None:
    payload = scope.classify_paths(
        [
            "src/structural_analysis/io/midas/raw_parser.py",
            "tests/fixtures/foundation_realish/foundation_small.mgt",
            "native/tests/golden/mgt_import_health_v1.json",
            "tests/test_native_mgt_import_health_python_parity.py",
            "scripts/check_native_mgt_import.py",
        ]
    )

    assert payload["modelir"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_reference_element_sources_route_through_cpp_abi_and_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/elements/reference_elements.cpp",
            "native/cpp/src/materials/materials.cpp",
            "native/cpp/tests/abi/reference_elements_contract_test.cpp",
            "native/crates/structural-ffi/tests/reference_elements_parity.rs",
            "tests/test_native_reference_elements_python_parity.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["abi"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_reference_hip_sources_route_through_dedicated_hip_and_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/hip/reference_elements_hip.hip.cpp",
            "native/cpp/tests/hip/reference_elements_hip_parity_test.hip.cpp",
            ".github/workflows/native-hip-dedicated.yml",
            "scripts/check_native_reference_elements_hip.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["hip"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_sparse_linear_sources_route_through_cpp_and_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/solver_cpu/sparse_linear.cpp",
            "native/cpp/tests/solver_cpu/sparse_linear_test.cpp",
            "native/cpp/tests/abi/sparse_linear_contract_test.cpp",
            "native/crates/structural-ffi-sys/src/sparse_linear.rs",
            "native/crates/structural-ffi/tests/sparse_linear_parity.rs",
            "tests/test_native_sparse_linear_python_parity.py",
            "scripts/check_native_sparse_linear.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["rust"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_sparse_linear_hip_sources_route_through_protected_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/hip/sparse_linear_hip.hip.cpp",
            "native/cpp/tests/hip/sparse_linear_hip_parity_test.hip.cpp",
            ".github/workflows/native-hip-dedicated.yml",
            "scripts/check_native_sparse_linear_hip.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["hip"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_generalized_eigen_sources_route_through_cpp_and_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/solver_cpu/generalized_eigen.cpp",
            "native/cpp/tests/solver_cpu/generalized_eigen_test.cpp",
            "native/cpp/tests/fuzz/generalized_eigen_fuzz.cpp",
            "tests/test_native_generalized_eigen_python_parity.py",
            "scripts/check_native_generalized_eigen.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_generalized_eigen_hip_sources_route_through_protected_oracle_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/cpp/src/hip/generalized_eigen_hip.hip.cpp",
            "native/cpp/tests/hip/generalized_eigen_hip_parity_test.hip.cpp",
            ".github/workflows/native-hip-dedicated.yml",
            "scripts/check_native_generalized_eigen_hip.py",
        ]
    )

    assert payload["native"] is True
    assert payload["cpp"] is True
    assert payload["hip"] is True
    assert payload["oracle"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_generalized_eigen_product_contract_routes_through_runtime_ci_gates() -> None:
    payload = scope.classify_paths(
        [
            "native/crates/structural-runtime/src/spectral_checkpoint.rs",
            "native/crates/structural-cli/tests/dense_spectral_product_cli.rs",
            "scripts/check_native_generalized_eigen_product.py",
            "tests/test_native_generalized_eigen_product_contract.py",
        ]
    )

    assert payload["native"] is True
    assert payload["rust"] is True
    assert payload["runtime"] is True
    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_legacy_runtime_compatibility_member_routes_through_rust_runtime_gates() -> None:
    payload = scope.classify_paths(
        ["implementation/phase1/structural_runtime_ffi/src/lib.rs"]
    )

    assert payload["native"] is True
    assert payload["rust"] is True
    assert payload["runtime"] is True
    assert payload["applicable"] is True
    assert payload["abi"] is True
    assert payload["hip"] is False


def test_scope_detects_protected_evidence_even_in_a_native_diff() -> None:
    payload = scope.classify_paths(
        [
            "native/Cargo.toml",
            "implementation/phase1/release_evidence/productization/receipt.json",
            "docs/commercial-structural-solver-product-gap-ledger.md",
        ]
    )

    assert payload["protected_evidence"] is True
    assert payload["protected_evidence_paths"] == [
        "docs/commercial-structural-solver-product-gap-ledger.md",
        "implementation/phase1/release_evidence/productization/receipt.json",
    ]


def test_scope_rejects_paths_that_escape_the_repository() -> None:
    with pytest.raises(ValueError, match="escapes repository root"):
        scope.classify_paths(["../outside"])


def test_dependency_boundary_requires_one_workspace_lockfile(tmp_path: Path) -> None:
    (tmp_path / "native").mkdir()
    (tmp_path / "native" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    _write_compatibility_owners(tmp_path)

    payload = boundary.check_boundary(tmp_path)

    assert payload["contract_pass"] is False
    assert payload["blockers"] == [
        "native_workspace_must_own_exactly_one_root_lockfile:none"
    ]


def test_dependency_boundary_ignores_generated_package_lockfile(tmp_path: Path) -> None:
    (tmp_path / "native" / "target" / "package" / "crate").mkdir(parents=True)
    (tmp_path / "native" / "Cargo.toml").write_text(
        "[workspace]\n", encoding="utf-8"
    )
    (tmp_path / "native" / "Cargo.lock").write_text("", encoding="utf-8")
    (tmp_path / "native" / "target" / "package" / "crate" / "Cargo.lock").write_text(
        "", encoding="utf-8"
    )
    _write_compatibility_owners(tmp_path)

    payload = boundary.check_boundary(tmp_path)

    assert payload["cargo_lockfiles"] == ["native/Cargo.lock"]
    assert payload["contract_pass"] is True


def test_dependency_boundary_rejects_python_runtime_calls(tmp_path: Path) -> None:
    source = tmp_path / "native" / "crates" / "structural-runtime" / "src"
    source.mkdir(parents=True)
    (tmp_path / "native" / "Cargo.lock").write_text("", encoding="utf-8")
    (tmp_path / "native" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    _write_compatibility_owners(tmp_path)
    (source / "lib.rs").write_text(
        'std::process::Command::new("python3");\n',
        encoding="utf-8",
    )

    payload = boundary.check_boundary(tmp_path)

    assert payload["contract_pass"] is False
    assert payload["blockers"] == [
        "python_runtime_call_in_native_product_source:"
        "native/crates/structural-runtime/src/lib.rs"
    ]
