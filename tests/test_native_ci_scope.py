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
        manifest.write_text('[package]\nname = "legacy"\n', encoding="utf-8")
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


def test_distribution_control_change_routes_through_native_ci() -> None:
    payload = scope.classify_paths(
        [
            "scripts/build_native_frame_alpha_distribution.py",
            "tests/test_native_frame_alpha_distribution.py",
        ]
    )

    assert payload["ci_control"] is True
    assert payload["applicable"] is True


def test_workbench_package_source_change_routes_through_native_distribution() -> None:
    payload = scope.classify_paths(
        ["src/workbench-v2/WorkbenchPage.tsx", "src/structure-viewer/index.html"]
    )

    assert payload["workstation_package"] is True
    assert payload["applicable"] is True
    assert payload["native"] is False


def test_frame3d_reference_change_routes_through_oracle_without_modelir_scope() -> None:
    payload = scope.classify_paths(
        [
            "scripts/run_native_frame3d_modelir_parity.py",
            "scripts/build_native_frame3d_reference_inventory.py",
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v1.schema.json",
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v2.schema.json",
            "src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v3.schema.json",
            "src/structural_analysis/schemas/native_frame3d_reference_inventory_v2.schema.json",
            "src/structural_analysis/schemas/native_frame3d_reference_inventory_v3.schema.json",
            "tests/test_native_frame3d_modelir_parity_pack.py",
            "tests/test_native_linear_frame3d.py",
        ]
    )

    assert payload["oracle"] is True
    assert payload["modelir"] is False
    assert payload["applicable"] is True


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
    (tmp_path / "native" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
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
