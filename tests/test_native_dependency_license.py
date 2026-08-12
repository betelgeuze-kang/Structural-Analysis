from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_dependency_licenses.py"
SPEC = importlib.util.spec_from_file_location("check_native_dependency_licenses", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
licenses = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = licenses
SPEC.loader.exec_module(licenses)


def _metadata(*packages: dict[str, object]) -> dict[str, object]:
    return {"packages": list(packages)}


def test_dependency_license_policy_accepts_locked_permissive_registry_package() -> None:
    rows, blockers = licenses.evaluate_metadata(
        _metadata(
            {
                "name": "serde",
                "version": "1.0.0",
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "license": "MIT OR Apache-2.0",
            }
        ),
        {"allowed_license_ids": ["MIT", "Apache-2.0"], "exceptions": []},
    )

    assert blockers == []
    assert rows[0]["license_ids"] == ["Apache-2.0", "MIT"]
    assert rows[0]["license_allowed"] is True
    assert rows[0]["source_allowed"] is True


def test_dependency_license_policy_accepts_one_allowed_or_branch() -> None:
    rows, blockers = licenses.evaluate_metadata(
        _metadata(
            {
                "name": "dual",
                "version": "1.0.0",
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "license": (
                    "Apache-2.0 WITH LLVM-exception OR Apache-2.0 OR MIT"
                ),
                "rust_version": "1.71",
            }
        ),
        {
            "maximum_rust_version": "1.77",
            "allowed_license_ids": ["MIT", "Apache-2.0"],
            "exceptions": [],
        },
    )

    assert blockers == []
    assert rows[0]["license_allowed"] is True
    assert rows[0]["msrv_allowed"] is True


def test_dependency_license_policy_requires_every_and_branch() -> None:
    rows, blockers = licenses.evaluate_metadata(
        _metadata(
            {
                "name": "combined",
                "version": "1.0.0",
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "license": "MIT AND Proprietary-1.0",
            }
        ),
        {"allowed_license_ids": ["MIT"], "exceptions": []},
    )

    assert rows[0]["license_allowed"] is False
    assert blockers == [
        "dependency_license_not_allowed:combined@1.0.0:MIT AND Proprietary-1.0"
    ]


def test_dependency_policy_rejects_locked_package_above_workspace_msrv() -> None:
    rows, blockers = licenses.evaluate_metadata(
        _metadata(
            {
                "name": "future",
                "version": "2.0.0",
                "source": "registry+https://github.com/rust-lang/crates.io-index",
                "license": "MIT",
                "rust_version": "1.82.0",
            }
        ),
        {
            "maximum_rust_version": "1.77",
            "allowed_license_ids": ["MIT"],
            "exceptions": [],
        },
    )

    assert rows[0]["msrv_allowed"] is False
    assert blockers == [
        "dependency_msrv_exceeds_workspace:future@2.0.0:1.82.0>1.77"
    ]


def test_dependency_policy_requires_a_valid_msrv_and_spdx_allowlist() -> None:
    assert licenses._validate_policy(  # noqa: SLF001 - focused policy unit
        {
            "schema_version": "wrong",
            "maximum_rust_version": "latest",
            "allowed_license_ids": [],
            "exceptions": {},
        }
    ) == [
        "native_dependency_policy_schema_version_invalid",
        "native_dependency_policy_maximum_rust_version_invalid:latest",
        "native_dependency_policy_license_allowlist_invalid",
        "native_dependency_policy_exceptions_invalid",
    ]


def test_dependency_license_policy_rejects_unapproved_license_and_git_source() -> None:
    rows, blockers = licenses.evaluate_metadata(
        _metadata(
            {
                "name": "unknown",
                "version": "2.0.0",
                "source": "git+https://example.invalid/repository",
                "license": "AGPL-3.0-only",
            }
        ),
        {"allowed_license_ids": ["MIT"], "exceptions": []},
    )

    assert rows[0]["license_allowed"] is False
    assert rows[0]["source_allowed"] is False
    assert blockers == [
        "dependency_license_not_allowed:unknown@2.0.0:AGPL-3.0-only",
        "dependency_source_not_allowed:unknown@2.0.0:"
        "git+https://example.invalid/repository",
    ]


def test_dependency_license_check_is_not_applicable_before_workspace(
    tmp_path: Path,
) -> None:
    payload = licenses.check_dependency_licenses(tmp_path)

    assert payload["workspace_present"] is False
    assert payload["contract_pass"] is True
    assert payload["package_count"] == 0
    assert payload["checked_manifests"] == []


def test_repository_policy_checks_product_and_standalone_rollback_locks() -> None:
    payload = licenses.check_dependency_licenses(ROOT)

    assert payload["contract_pass"] is True, payload["blockers"]
    assert payload["checked_manifests"] == [
        "native/Cargo.toml",
        "implementation/phase1/structural_runtime_ffi/Cargo.toml",
    ]
    assert any(
        row["package"] == "structural_runtime_ffi@0.1.0"
        for row in payload["packages"]
    )
