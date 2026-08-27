from __future__ import annotations

from copy import deepcopy
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


def test_dependency_policy_rejects_allowlist_or_exception_self_approval() -> None:
    policy = _policy()
    policy["allowed_license_ids"] = [*licenses.APPROVED_LICENSE_IDS, "UNKNOWN"]
    assert "native_dependency_policy_license_allowlist_invalid" in (
        licenses._validate_policy(policy)  # noqa: SLF001 - focused policy unit
    )

    policy = _policy()
    policy["allowed_license_ids"] = list(licenses.APPROVED_LICENSE_IDS)
    policy["exceptions"] = [
        {"package": "evil@9.9.9", "allow_source": True, "allow_license": True}
    ]
    assert "native_dependency_policy_exceptions_invalid" in (
        licenses._validate_policy(policy)  # noqa: SLF001 - focused policy unit
    )


def test_spdx_parser_rejects_license_id_used_as_with_exception() -> None:
    assert not licenses._license_expression_allowed(  # noqa: SLF001
        "MIT WITH Apache-2.0", {"MIT", "Apache-2.0"}
    )
    assert licenses._license_expression_allowed(  # noqa: SLF001
        "Apache-2.0 WITH LLVM-exception OR MIT", {"MIT", "Apache-2.0"}
    )


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


def test_first_party_license_rejects_appended_grant_despite_required_fragments(
    tmp_path: Path,
) -> None:
    repository_license = tmp_path / "LICENSE"
    repository_license.write_bytes(
        (ROOT / "LICENSE").read_bytes()
        + b"\nPermission is hereby granted to use this software.\n"
    )
    workspace = tmp_path / "native/Cargo.toml"
    workspace.parent.mkdir()
    workspace.write_text(
        "[workspace]\nmembers = [\"crates/example\"]\n\n"
        "[workspace.package]\nlicense-file = \"../LICENSE\"\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "native/crates/example/Cargo.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "[package]\nname = \"example\"\nversion = \"0.1.0\"\n"
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
                "source": None,
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

    assert report["contract_pass"] is False
    assert blockers == ["repository_license_not_pinned_trusted_baseline"]


def test_first_party_license_rejects_excluded_source_null_path_crate(
    tmp_path: Path,
) -> None:
    repository_license = tmp_path / "LICENSE"
    repository_license.write_bytes((ROOT / "LICENSE").read_bytes())
    workspace = tmp_path / "native/Cargo.toml"
    workspace.parent.mkdir()
    workspace.write_text(
        "[workspace]\nmembers = [\"crates/example\"]\n\n"
        "[workspace.package]\nlicense-file = \"../LICENSE\"\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "native/crates/example/Cargo.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "[package]\nname = \"example\"\nversion = \"0.1.0\"\n"
        "license-file.workspace = true\n",
        encoding="utf-8",
    )
    excluded_manifest = tmp_path / "native/local/excluded/Cargo.toml"
    excluded_manifest.parent.mkdir(parents=True)
    excluded_manifest.write_text(
        "[package]\nname = \"excluded\"\nversion = \"9.9.9\"\n"
        "license = \"MIT\"\n",
        encoding="utf-8",
    )
    member_id = "path+file:///example#0.1.0"
    excluded_id = "path+file:///excluded#9.9.9"
    metadata = {
        "workspace_members": [member_id],
        "packages": [
            {
                "id": member_id,
                "name": "example",
                "version": "0.1.0",
                "source": None,
                "manifest_path": str(manifest),
                "license": None,
                "license_file": str(repository_license),
            },
            {
                "id": excluded_id,
                "name": "excluded",
                "version": "9.9.9",
                "source": None,
                "manifest_path": str(excluded_manifest),
                "license": "MIT",
                "license_file": None,
            },
        ],
    }

    report, blockers = licenses.evaluate_first_party_license(
        metadata,
        _policy(),
        repo_root=tmp_path,
        workspace=workspace,
    )

    assert report["contract_pass"] is False
    assert blockers == ["non_workspace_path_dependency_forbidden:excluded@9.9.9"]
    assert report["workspace_package_count"] == 1


def test_repository_native_license_sbom_is_consistent_and_non_promoting() -> None:
    payload = licenses.check_dependency_licenses(ROOT)

    assert payload["schema_version"] == "native-dependency-license-sbom.v2"
    assert payload["contract_pass"] is True
    assert payload["package_count"] == 115
    assert payload["external_dependency_count"] == 109
    assert len(payload["packages"]) == 115
    assert payload["inputs"]["cargo_lock"]["package_count"] == 115
    assert all(row["source_allowed"] for row in payload["packages"])
    assert all(row["license_allowed"] for row in payload["packages"])
    assert all(row["msrv_allowed"] for row in payload["packages"])
    assert payload["first_party_license"]["workspace_package_count"] == 6
    assert payload["first_party_license"]["contract_pass"] is True
    assert payload["release_clearance"] == {
        "status": "blocked",
        "product_license_approval": False,
        "commercial_redistribution_approved": False,
        "third_party_redistribution_clearance": "not_established",
        "blockers": list(licenses.FIRST_PARTY_POLICY["release_blockers"]),
    }


def test_repository_dependency_inputs_match_trusted_verifier_pins() -> None:
    lock_bytes = (ROOT / "native/Cargo.lock").read_bytes()
    policy_bytes = (ROOT / "native/dependency-policy.json").read_bytes()
    locked_rows, blockers = licenses._locked_package_rows(  # noqa: SLF001
        licenses._load_lock_bytes(lock_bytes)  # noqa: SLF001
    )

    assert blockers == []
    assert licenses._validate_pinned_dependency_inputs(  # noqa: SLF001
        lock_bytes=lock_bytes,
        policy_bytes=policy_bytes,
        locked_rows=locked_rows,
    ) == []
    assert licenses._sha256_bytes(lock_bytes) == licenses.PINNED_CARGO_LOCK_SHA256  # noqa: SLF001
    assert (
        licenses._sha256_bytes(policy_bytes)  # noqa: SLF001
        == licenses.PINNED_DEPENDENCY_POLICY_SHA256
    )
    assert (
        licenses._sha256_bytes((ROOT / "LICENSE").read_bytes())  # noqa: SLF001
        == licenses.PINNED_REPOSITORY_LICENSE_SHA256
    )
    assert len(locked_rows) == licenses.PINNED_PACKAGE_COUNT == 115
    assert (
        sum(bool(row["external"]) for row in locked_rows)
        == licenses.PINNED_EXTERNAL_DEPENDENCY_COUNT
        == 109
    )
    assert tuple(
        sorted(
            str(row["package"])
            for row in locked_rows
            if row["external"] is False
        )
    ) == tuple(sorted(licenses.PINNED_FIRST_PARTY_PACKAGES))


def test_packaged_sbom_rejects_coherently_rehashed_appended_license_grant() -> None:
    payload = deepcopy(licenses.check_dependency_licenses(ROOT))
    tampered_license = (
        (ROOT / "LICENSE").read_bytes()
        + b"\nPermission is hereby granted to use this software.\n"
    )
    payload["first_party_license"]["repository_license"]["sha256"] = (
        licenses._sha256_bytes(tampered_license)  # noqa: SLF001
    )

    blockers = licenses.validate_packaged_sbom(
        payload,
        license_bytes=tampered_license,
        cargo_lock_bytes=(ROOT / "native/Cargo.lock").read_bytes(),
        policy_bytes=(ROOT / "native/dependency-policy.json").read_bytes(),
    )

    assert blockers == [
        "packaged_repository_license_not_pinned_trusted_baseline"
    ]


def test_build_time_checker_rejects_nonpinned_lock_and_policy_bytes(
    tmp_path: Path,
) -> None:
    native = tmp_path / "native"
    native.mkdir()
    (native / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    policy_bytes = (ROOT / "native/dependency-policy.json").read_bytes()
    (native / "dependency-policy.json").write_bytes(policy_bytes)
    (native / "Cargo.lock").write_text(
        'version = 3\n\n[[package]]\nname = "invented"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )

    report = licenses.check_dependency_licenses(tmp_path)

    assert report["contract_pass"] is False
    assert "cargo_lock_not_pinned_trusted_baseline" in report["blockers"]
    assert "cargo_lock_pinned_package_count_mismatch:1!=115" in report["blockers"]

    (native / "Cargo.lock").write_bytes((ROOT / "native/Cargo.lock").read_bytes())
    (native / "dependency-policy.json").write_bytes(policy_bytes + b"\n")

    report = licenses.check_dependency_licenses(tmp_path)

    assert report["contract_pass"] is False
    assert (
        "native_dependency_policy_not_pinned_trusted_baseline"
        in report["blockers"]
    )


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
