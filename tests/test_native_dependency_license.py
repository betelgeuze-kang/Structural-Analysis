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


def test_dependency_license_check_is_not_applicable_before_workspace() -> None:
    payload = licenses.check_dependency_licenses(ROOT)

    assert payload["workspace_present"] is False
    assert payload["contract_pass"] is True
    assert payload["package_count"] == 0
