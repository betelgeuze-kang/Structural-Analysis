from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
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


def _policy() -> dict[str, object]:
    return {
        "schema_version": "native-dependency-policy.v2",
        "maximum_rust_version": "1.77",
        "first_party_license": dict(licenses.FIRST_PARTY_POLICY),
        "allowed_license_ids": ["MIT", "Apache-2.0"],
        "exceptions": [],
    }


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
        "native_first_party_license_policy_invalid",
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


def test_first_party_workspace_inherits_repository_no_grant_license(
    tmp_path: Path,
) -> None:
    repository_license = tmp_path / "LICENSE"
    repository_license.write_text(
        (ROOT / "LICENSE").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    workspace = tmp_path / "native/Cargo.toml"
    workspace.parent.mkdir()
    workspace.write_text(
        "[workspace]\nmembers = [\"crates/example\"]\n\n"
        "[workspace.package]\nversion = \"0.1.0\"\n"
        "license-file = \"../LICENSE\"\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "native/crates/example/Cargo.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "[package]\nname = \"example\"\nversion.workspace = true\n"
        "license-file.workspace = true\n",
        encoding="utf-8",
    )
    package_id = "path+file:///example#0.1.0"
    metadata = {
        "workspace_members": [package_id],
        "packages": [
            {
                "id": package_id,
                "name": "example",
                "version": "0.1.0",
                "manifest_path": str(manifest),
                "license": None,
                "license_file": str(repository_license),
            }
        ],
    }

    report, blockers = licenses.evaluate_first_party_license(
        metadata,
        _policy(),
        repo_root=tmp_path,
        workspace=workspace,
    )

    assert blockers == []
    assert report["contract_pass"] is True
    assert report["posture"] == "all_rights_reserved_no_license_granted"
    assert report["repository_license"]["path"] == "LICENSE"
    assert report["workspace_packages"] == [
        {
            "package": "example@0.1.0",
            "manifest_path": "native/crates/example/Cargo.toml",
            "license_expression": None,
            "license_file": "LICENSE",
            "inherits_workspace_license_file": True,
            "license_file_matches_repository": True,
        }
    ]


def test_first_party_workspace_rejects_permissive_metadata_and_manifest(
    tmp_path: Path,
) -> None:
    repository_license = tmp_path / "LICENSE"
    repository_license.write_text(
        (ROOT / "LICENSE").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    workspace = tmp_path / "native/Cargo.toml"
    workspace.parent.mkdir()
    workspace.write_text(
        "[workspace]\nmembers = [\"crates/example\"]\n\n"
        "[workspace.package]\nlicense = \"MIT OR Apache-2.0\"\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "native/crates/example/Cargo.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "[package]\nname = \"example\"\nlicense.workspace = true\n",
        encoding="utf-8",
    )
    package_id = "path+file:///example#0.1.0"
    metadata = {
        "workspace_members": [package_id],
        "packages": [
            {
                "id": package_id,
                "name": "example",
                "version": "0.1.0",
                "manifest_path": str(manifest),
                "license": "MIT OR Apache-2.0",
                "license_file": None,
            }
        ],
    }

    report, blockers = licenses.evaluate_first_party_license(
        metadata,
        _policy(),
        repo_root=tmp_path,
        workspace=workspace,
    )

    assert report["contract_pass"] is False
    assert blockers == [
        "workspace_license_file_not_repository_authority",
        "workspace_package_effective_spdx_license_forbidden:"
        "example@0.1.0:MIT OR Apache-2.0",
        "workspace_package_license_file_mismatch:example@0.1.0",
        "workspace_package_license_file_not_inherited:example@0.1.0",
        "workspace_package_spdx_license_expression_forbidden:example@0.1.0",
        "workspace_spdx_license_expression_forbidden",
    ]


def test_repository_native_license_sbom_is_consistent_and_non_promoting() -> None:
    payload = licenses.check_dependency_licenses(ROOT)

    assert payload["schema_version"] == "native-dependency-license-sbom.v2"
    assert payload["contract_pass"] is True
    assert payload["first_party_license"]["workspace_package_count"] == 6
    assert payload["first_party_license"]["contract_pass"] is True
    assert payload["release_clearance"] == {
        "status": "blocked",
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "blockers": list(licenses.FIRST_PARTY_POLICY["release_blockers"]),
    }


def test_cargo_package_includes_root_license_for_every_workspace_crate() -> None:
    payload = licenses.check_dependency_licenses(ROOT)
    packages = payload["first_party_license"]["workspace_packages"]

    assert packages
    for package in packages:
        completed = subprocess.run(
            [
                "cargo",
                "package",
                "--manifest-path",
                str(ROOT / package["manifest_path"]),
                "--allow-dirty",
                "--locked",
                "--list",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert "LICENSE" in completed.stdout.splitlines()
