from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread, current_thread
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
TRANSITION_SCRIPT = (
    ROOT / "scripts/build_native_frame_alpha_portable_transition_evidence.py"
)
TRANSITION_SPEC = importlib.util.spec_from_file_location(
    "build_native_frame_alpha_portable_transition_evidence_test",
    TRANSITION_SCRIPT,
)
assert TRANSITION_SPEC is not None and TRANSITION_SPEC.loader is not None
transition = importlib.util.module_from_spec(TRANSITION_SPEC)
sys.modules[TRANSITION_SPEC.name] = transition
TRANSITION_SPEC.loader.exec_module(transition)


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
            "archive": {
                "sha256": portable._sha256_bytes(archive_path.read_bytes()),
                "byte_length": archive_path.stat().st_size,
            },
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
        expected_source_tree=str(source["tree_sha"]),
        expected_archive_sha256=portable._sha256_bytes(archive.read_bytes()),
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


def _transition_schema() -> dict[str, object]:
    return json.loads(
        (
            ROOT
            / "native/distribution/frame_alpha_portable_transition_replay_v1.schema.json"
        ).read_text(encoding="utf-8")
    )


def _snapshot(root: Path) -> dict[str, bytes | None]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in sorted(root.rglob("*"))
    }


def _run_same_target_concurrently(
    *,
    archive: Path,
    install_root: Path,
    operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, tuple[str, object]]:
    real_atomic_activate = portable._atomic_activate
    real_try_lock = portable._try_acquire_file_lock
    winner_at_activation = Event()
    release_winner = Event()
    contender_attempted_lock = Event()
    results: dict[str, tuple[str, object]] = {}

    def observed_try_lock(descriptor: int) -> None:
        if current_thread().name == "portable-contender":
            contender_attempted_lock.set()
        real_try_lock(descriptor)

    def paused_atomic_activate(**kwargs: object) -> None:
        if current_thread().name == "portable-winner":
            winner_at_activation.set()
            if not release_winner.wait(timeout=5.0):
                raise AssertionError("concurrent-operation test release timed out")
        real_atomic_activate(**kwargs)

    monkeypatch.setattr(portable, "_try_acquire_file_lock", observed_try_lock)
    monkeypatch.setattr(portable, "_atomic_activate", paused_atomic_activate)

    def invoke(label: str) -> None:
        try:
            results[label] = (
                "ok",
                _apply(archive, install_root, operation=operation),
            )
        except Exception as error:  # noqa: BLE001 - capture the losing operation
            results[label] = ("error", error)

    winner = Thread(
        target=invoke,
        args=("winner",),
        name="portable-winner",
    )
    contender = Thread(
        target=invoke,
        args=("contender",),
        name="portable-contender",
    )
    winner.start()
    assert winner_at_activation.wait(timeout=5.0)
    contender.start()
    assert contender_attempted_lock.wait(timeout=5.0)
    assert contender.is_alive()
    release_winner.set()
    winner.join(timeout=5.0)
    contender.join(timeout=5.0)
    assert not winner.is_alive()
    assert not contender.is_alive()
    return results


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


@pytest.mark.parametrize(
    ("override", "expected_error"),
    (
        ({"expected_archive_sha256": "sha256:" + "0" * 64}, "trusted_sha256"),
        ({"expected_source_commit": "9" * 40}, "trusted_coordinates"),
        ({"expected_source_tree": "9" * 40}, "trusted_coordinates"),
        ({"expected_platform_tag": "windows-x86_64-msvc"}, "trusted_coordinates"),
    ),
)
def test_trusted_coordinate_preflight_rejects_before_binary_verifier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: dict[str, str],
    expected_error: str,
) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    arguments = {
        "operation": "install",
        "archive_path": archive,
        "install_root": tmp_path / "must-not-exist",
        "expected_source_commit": "1" * 40,
        "expected_source_tree": "a" * 40,
        "expected_archive_sha256": portable._sha256_bytes(archive.read_bytes()),
        "expected_platform_tag": PLATFORM,
    }
    arguments.update(override)
    monkeypatch.setattr(
        portable,
        "_load_distribution_module",
        lambda: (_ for _ in ()).throw(AssertionError("binary verifier executed")),
    )

    with pytest.raises(portable.PortableInstallError, match=expected_error):
        portable.apply_archive(**arguments)

    assert not (tmp_path / "must-not-exist").exists()


def test_cli_requires_tree_and_trusted_archive_digest() -> None:
    with pytest.raises(SystemExit):
        portable.main(
            [
                "install",
                "--archive",
                "candidate.zip",
                "--install-root",
                "installation",
                "--expected-source-commit",
                "1" * 40,
                "--platform-tag",
                PLATFORM,
            ]
        )


def test_windows_mode_profile_is_content_only_and_explicit() -> None:
    assert portable._mode_integrity_profile("windows-x86_64-msvc") == (
        "windows_content_bound_pe_execution_semantics.v1"
    )


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


def test_transition_receipt_binds_distinct_generations_and_final_rollback(
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
    installed = _apply(first, install_root, operation="install")
    updated = _apply(second, install_root, operation="update")
    rolled_back = portable.rollback(
        install_root=install_root,
        target_version_key=str(installed["active_version_key"]),
    )
    state_paths = []
    for name, state in (
        ("install", installed),
        ("update", updated),
        ("rollback", rolled_back),
    ):
        path = tmp_path / f"{name}.json"
        path.write_bytes(portable._state_bytes(state))
        state_paths.append(path)
    generations = []
    for role, archive_path, ephemeral in (
        ("baseline", first, False),
        ("ephemeral_update", second, True),
    ):
        manifest = _manifest(archive_path)
        generations.append(
            {
                "role": role,
                "archive_filename": archive_path.name,
                "archive_sha256": portable._sha256_bytes(archive_path.read_bytes()),
                "archive_byte_length": archive_path.stat().st_size,
                "package_version": manifest["package_version"],
                "source": manifest["source"],
                "ephemeral_test_generation": ephemeral,
                "release_candidate": False,
            }
        )
    trust = {
        "schema_version": transition.TRUST_SCHEMA,
        "platform_tag": PLATFORM,
        "transport_profile": "github_actions_immutable_artifact.v1",
        "generations": generations,
        "claim_boundary": transition.TRUST_CLAIM,
    }
    trust_path = tmp_path / "trust.json"
    trust_path.write_bytes(transition._canonical_bytes(trust) + b"\n")

    receipt = transition.build_receipt(
        trust_input_path=trust_path,
        install_state_path=state_paths[0],
        update_state_path=state_paths[1],
        rollback_state_path=state_paths[2],
        install_root=install_root,
        platform_tag=PLATFORM,
    )

    Draft202012Validator(_transition_schema()).validate(receipt)
    assert receipt["receipt_hash"] == transition._receipt_hash(receipt)
    assert receipt["checks"]["install_update_rollback_lineage"] is True
    assert receipt["authority"]["derived_update_generation"] == (
        "ephemeral_test_only_not_release_candidate"
    )
    assert receipt["authority"]["release_readiness"] == "not_authoritative"


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


def test_concurrent_same_target_install_is_serialized_without_orphaning_active_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    install_root = tmp_path / "installation"

    results = _run_same_target_concurrently(
        archive=archive,
        install_root=install_root,
        operation="install",
        monkeypatch=monkeypatch,
    )

    assert results["winner"][0] == "ok"
    assert results["contender"][0] == "error"
    assert isinstance(results["contender"][1], portable.PortableInstallError)
    assert "installation_already_initialized_use_update" in str(
        results["contender"][1]
    )
    state = portable.verify_installation(install_root=install_root)
    assert (install_root / state["active_version"]["relative_path"]).is_dir()


def test_concurrent_same_target_update_is_serialized_without_deleting_active_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    initial = _archive(
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
    _apply(initial, install_root, operation="install")

    results = _run_same_target_concurrently(
        archive=update,
        install_root=install_root,
        operation="update",
        monkeypatch=monkeypatch,
    )

    assert results["winner"][0] == "ok"
    assert results["contender"][0] == "error"
    assert isinstance(results["contender"][1], portable.PortableInstallError)
    assert "target_version_already_active" in str(results["contender"][1])
    state = portable.verify_installation(install_root=install_root)
    assert state["active_version"]["package"]["package_version"] == "2.0.0"
    assert (install_root / state["active_version"]["relative_path"]).is_dir()


def test_installation_lock_timeout_is_bounded_and_fail_closed(tmp_path: Path) -> None:
    install_root = tmp_path / "installation"
    observed: list[Exception] = []

    def contend() -> None:
        try:
            with portable._installation_lock(
                install_root,
                create_root=False,
                timeout_seconds=0.05,
            ):
                raise AssertionError("contender unexpectedly acquired installation lock")
        except Exception as error:  # noqa: BLE001 - assert exact error below
            observed.append(error)

    with portable._installation_lock(install_root, create_root=True):
        contender = Thread(target=contend, name="portable-timeout-contender")
        contender.start()
        contender.join(timeout=2.0)
        assert not contender.is_alive()

    assert len(observed) == 1
    assert isinstance(observed[0], portable.PortableInstallError)
    assert str(observed[0]) == "installation_lock_timeout"


def test_installation_lock_excludes_a_separate_process(tmp_path: Path) -> None:
    install_root = tmp_path / "installation"
    contender = """
import importlib.util
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("portable_lock_contender", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
try:
    with module._installation_lock(
        Path(sys.argv[2]), create_root=False, timeout_seconds=0.1
    ):
        raise SystemExit(4)
except module.PortableInstallError as error:
    raise SystemExit(0 if str(error) == "installation_lock_timeout" else 3)
"""

    with portable._installation_lock(install_root, create_root=True):
        completed = subprocess.run(
            [sys.executable, "-c", contender, str(SCRIPT), str(install_root)],
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )

    assert completed.returncode == 0, completed.stderr


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


def test_verifier_executes_private_snapshot_and_detects_source_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    captured = source.read_bytes()

    def verify_and_replace(*, archive_path: Path) -> dict[str, object]:
        assert archive_path != source
        assert archive_path.read_bytes() == captured
        manifest = _manifest(archive_path)
        source.write_bytes(b"replaced while verifier was running")
        return {
            "status": "pass",
            "source": manifest["source"],
            "platform_tag": manifest["platform_tag"],
            "manifest_hash": manifest["manifest_hash"],
        }

    monkeypatch.setattr(
        portable,
        "_load_distribution_module",
        lambda: SimpleNamespace(
            verify_workstation_distribution=verify_and_replace
        ),
    )

    with pytest.raises(
        portable.PortableInstallError,
        match="archive_changed_during_verification",
    ):
        portable.apply_archive(
            operation="install",
            archive_path=source,
            install_root=tmp_path / "installation",
            expected_source_commit="1" * 40,
            expected_source_tree="a" * 40,
            expected_archive_sha256=portable._sha256_bytes(captured),
            expected_platform_tag=PLATFORM,
        )

    assert not (tmp_path / "installation").exists()


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
    old_binary.chmod(0o555)
    current_before = (install_root / portable.CURRENT_NAME).read_bytes()

    with pytest.raises(
        portable.PortableInstallError, match="retained_payload_hash_mismatch"
    ):
        portable.rollback(install_root=install_root, target_version_key=old_key)

    assert (install_root / portable.CURRENT_NAME).read_bytes() == current_before


def test_posix_executable_mode_tamper_fails_closed(tmp_path: Path) -> None:
    archive = _archive(
        tmp_path,
        version="1.0.0",
        commit_digit="1",
        tree_digit="a",
        marker="one",
    )
    install_root = tmp_path / "installation"
    state = _apply(archive, install_root, operation="install")
    retained = install_root / str(state["active_version"]["relative_path"])
    binary = retained / "bin/structural-cli"
    binary.chmod(0o444)

    with pytest.raises(
        portable.PortableInstallError,
        match="retained_payload_mode_mismatch:bin/structural-cli",
    ):
        portable.verify_installation(install_root=install_root)


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
