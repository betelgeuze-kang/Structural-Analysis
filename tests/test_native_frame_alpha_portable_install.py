from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import zipfile

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/manage_native_frame_alpha_portable_install.py"
SPEC = importlib.util.spec_from_file_location(
    "manage_native_frame_alpha_portable_install_test", SCRIPT
)
assert SPEC is not None and SPEC.loader is not None
portable = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = portable
SPEC.loader.exec_module(portable)


PLATFORM = "linux-x86_64-gnu"


def _source(commit_digit: str, tree_digit: str) -> dict[str, str]:
    return {
        "commit_sha": commit_digit * 40,
        "tree_sha": tree_digit * 40,
        "binding_profile": "verified_clean_git_checkout.v1",
    }


def _archive(
    tmp_path: Path,
    *,
    version: str,
    commit_digit: str,
    tree_digit: str,
    marker: str,
) -> Path:
    package_id = f"structural-frame-alpha-workstation-{version}-{PLATFORM}"
    files = {
        "bin/structural-cli": f"binary:{marker}\n".encode(),
        "workbench/index.html": f"<html>{marker}</html>\n".encode(),
    }
    rows = [
        {
            "path": path,
            "byte_length": len(content),
            "sha256": portable._sha256_bytes(content),
            "executable": path == "bin/structural-cli",
        }
        for path, content in sorted(files.items())
    ]
    manifest = {
        "schema_version": portable.WORKSTATION_MANIFEST_SCHEMA,
        "manifest_hash": "",
        "package_id": package_id,
        "package_version": version,
        "platform_tag": PLATFORM,
        "source": _source(commit_digit, tree_digit),
        "files": rows,
    }
    manifest["manifest_hash"] = portable._manifest_hash(manifest)
    output = tmp_path / f"{version}-{commit_digit}-{marker}.zip"
    with zipfile.ZipFile(output, mode="x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(f"{package_id}/{path}", content)
        archive.writestr(
            f"{package_id}/manifest.json",
            portable._canonical_bytes(manifest) + b"\n",
        )
    return output


def _manifest(archive_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(archive_path) as archive:
        name = next(
            name for name in archive.namelist() if name.endswith("/manifest.json")
        )
        return json.loads(archive.read(name))


def _fake_distribution() -> SimpleNamespace:
    def verify_workstation_distribution(*, archive_path: Path) -> dict[str, object]:
        manifest = _manifest(archive_path)
        return {
            "schema_version": "structural-frame-alpha-workstation-distribution-smoke.v2",
            "status": "pass",
            "source": manifest["source"],
            "platform_tag": manifest["platform_tag"],
            "manifest_hash": manifest["manifest_hash"],
        }

    return SimpleNamespace(
        verify_workstation_distribution=verify_workstation_distribution
    )


@pytest.fixture(autouse=True)
def fake_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(portable, "_load_distribution_module", _fake_distribution)


def _apply(
    archive: Path,
    install_root: Path,
    *,
    operation: str,
    allow_downgrade: bool = False,
) -> dict[str, object]:
    manifest = _manifest(archive)
    source = manifest["source"]
    assert isinstance(source, dict)
    return portable.apply_archive(
        operation=operation,
        archive_path=archive,
        install_root=install_root,
        expected_source_commit=str(source["commit_sha"]),
        expected_platform_tag=PLATFORM,
        allow_downgrade=allow_downgrade,
    )


def _schema() -> dict[str, object]:
    return json.loads(
        (
            ROOT
            / "native/distribution/frame_alpha_portable_install_state_v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


def test_install_is_source_bound_canonical_and_schema_valid(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    install_root = tmp_path / "installation"

    state = _apply(archive, install_root, operation="install")

    Draft202012Validator(_schema()).validate(state)
    assert state["revision"] == 1
    assert state["history"][0]["operation"] == "install"
    assert state["active_version"]["source"]["commit_sha"] == "1" * 40
    assert state["active_version"]["package"][
        "archive_sha256"
    ] == portable._sha256_bytes(archive.read_bytes())
    assert (install_root / portable.CURRENT_NAME).read_bytes() == portable._state_bytes(
        state
    )
    assert portable.verify_installation(install_root=install_root) == state
    retained = install_root / state["active_version"]["relative_path"]
    assert (retained / portable.DESCRIPTOR_NAME).is_file()
    assert (retained / "bin/structural-cli").read_bytes() == b"binary:one\n"


def test_install_state_is_deterministic_across_local_roots(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )

    first = _apply(archive, tmp_path / "first-root", operation="install")
    second = _apply(archive, tmp_path / "second-root", operation="install")

    assert first == second
    assert (tmp_path / "first-root" / portable.CURRENT_NAME).read_bytes() == (
        tmp_path / "second-root" / portable.CURRENT_NAME
    ).read_bytes()


def test_archive_verifier_failure_precedes_install_root_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    install_root = tmp_path / "must-not-exist"
    failing = SimpleNamespace(
        verify_workstation_distribution=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("failed smoke")
        )
    )
    monkeypatch.setattr(portable, "_load_distribution_module", lambda: failing)

    with pytest.raises(
        portable.PortableInstallError, match="archive_verification_failed"
    ):
        _apply(archive, install_root, operation="install")

    assert not install_root.exists()


def test_update_retains_old_version_and_rollback_is_explicit(tmp_path: Path) -> None:
    first = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    second = _archive(
        tmp_path,
        version="2.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="two",
    )
    install_root = tmp_path / "installation"
    installed = _apply(first, install_root, operation="install")
    old_key = str(installed["active_version_key"])

    updated = _apply(second, install_root, operation="update")

    assert updated["revision"] == 2
    assert len(updated["known_versions"]) == 2
    assert updated["history"][-1]["downgrade_policy"] == (
        "monotonic_or_same_version_source_update"
    )
    assert (install_root / "versions" / old_key).is_dir()

    rolled_back = portable.rollback(
        install_root=install_root,
        target_version_key=old_key,
    )

    Draft202012Validator(_schema()).validate(rolled_back)
    assert rolled_back["active_version_key"] == old_key
    assert rolled_back["revision"] == 3
    assert rolled_back["history"][-1]["operation"] == "rollback"
    assert rolled_back["history"][-1]["downgrade_policy"] == (
        "explicit_retained_version_rollback"
    )


def test_lower_version_is_rejected_without_explicit_policy_and_is_recoverable(
    tmp_path: Path,
) -> None:
    current = _archive(
        tmp_path,
        version="2.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="two",
    )
    older = _archive(
        tmp_path,
        version="1.5.0",
        commit_digit="3",
        tree_digit="c",
        marker="older",
    )
    install_root = tmp_path / "installation"
    _apply(current, install_root, operation="install")
    before = _snapshot(install_root)

    with pytest.raises(
        portable.PortableInstallError, match="downgrade_requires_explicit_allow"
    ):
        _apply(older, install_root, operation="update")

    assert _snapshot(install_root) == before
    state = _apply(
        older,
        install_root,
        operation="update",
        allow_downgrade=True,
    )
    assert state["history"][-1]["downgrade_policy"] == "explicit_allow_downgrade"


def test_same_semver_different_source_is_a_retained_source_update(
    tmp_path: Path,
) -> None:
    first = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    rebuilt = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="rebuilt",
    )
    install_root = tmp_path / "installation"
    _apply(first, install_root, operation="install")

    state = _apply(rebuilt, install_root, operation="update")

    assert len(state["known_versions"]) == 2
    assert state["active_version"]["source"]["commit_sha"] == "2" * 40
    assert state["history"][-1]["downgrade_policy"] == (
        "monotonic_or_same_version_source_update"
    )


def test_tampered_update_leaves_current_installation_byte_identical(
    tmp_path: Path,
) -> None:
    current = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    update = _archive(
        tmp_path,
        version="2.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="two",
    )
    tampered = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(update) as original,
        zipfile.ZipFile(
            tampered, mode="x", compression=zipfile.ZIP_DEFLATED
        ) as changed,
    ):
        for info in original.infolist():
            content = original.read(info)
            if info.filename.endswith("workbench/index.html"):
                content += b"tampered"
            changed.writestr(info, content)
    install_root = tmp_path / "installation"
    _apply(current, install_root, operation="install")
    before = _snapshot(install_root)

    with pytest.raises(
        portable.PortableInstallError, match="archive_file_binding_invalid"
    ):
        _apply(tampered, install_root, operation="update")

    assert _snapshot(install_root) == before


def test_failed_atomic_activation_removes_new_version_and_preserves_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    current = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    update = _archive(
        tmp_path,
        version="2.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="two",
    )
    install_root = tmp_path / "installation"
    _apply(current, install_root, operation="install")
    before = _snapshot(install_root)

    real_replace = portable.os.replace

    def fail_activation(source: Path, destination: Path) -> None:
        if Path(destination).name == portable.CURRENT_NAME:
            raise OSError("simulated pointer failure")
        real_replace(source, destination)

    monkeypatch.setattr(portable.os, "replace", fail_activation)
    with pytest.raises(OSError, match="simulated pointer failure"):
        _apply(update, install_root, operation="update")

    assert _snapshot(install_root) == before


def test_tampered_retained_version_blocks_rollback_without_pointer_change(
    tmp_path: Path,
) -> None:
    first = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    second = _archive(
        tmp_path,
        version="2.0.0",
        commit_digit="2",
        tree_digit="b",
        marker="two",
    )
    install_root = tmp_path / "installation"
    initial = _apply(first, install_root, operation="install")
    old_key = str(initial["active_version_key"])
    _apply(second, install_root, operation="update")
    old_binary = install_root / "versions" / old_key / "bin/structural-cli"
    old_binary.chmod(0o600)
    old_binary.write_bytes(b"tampered\n")
    current_before = (install_root / portable.CURRENT_NAME).read_bytes()

    with pytest.raises(
        portable.PortableInstallError, match="retained_payload_hash_mismatch"
    ):
        portable.rollback(install_root=install_root, target_version_key=old_key)

    assert (install_root / portable.CURRENT_NAME).read_bytes() == current_before


def test_unknown_rollback_and_active_reinstall_fail_closed(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    install_root = tmp_path / "installation"
    state = _apply(archive, install_root, operation="install")
    before = _snapshot(install_root)

    with pytest.raises(
        portable.PortableInstallError, match="target_version_already_active"
    ):
        _apply(archive, install_root, operation="update")
    with pytest.raises(
        portable.PortableInstallError, match="rollback_target_not_previously_verified"
    ):
        portable.rollback(
            install_root=install_root,
            target_version_key="v9.9.9--linux-x86_64-gnu--" + "9" * 40,
        )

    assert _snapshot(install_root) == before
    assert portable.verify_installation(install_root=install_root) == state


def test_state_schema_rejects_authority_promotion(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    state = _apply(archive, tmp_path / "installation", operation="install")
    promoted = deepcopy(state)
    promoted["authority"]["release_readiness"] = "authoritative"

    with pytest.raises(ValidationError):
        Draft202012Validator(_schema()).validate(promoted)
