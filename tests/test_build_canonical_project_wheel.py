from __future__ import annotations

import base64
import csv
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import zipfile

from jsonschema import Draft202012Validator
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_canonical_project_wheel.py"
SPEC = importlib.util.spec_from_file_location("canonical_project_wheel", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_lock_and_wheelhouse(tmp_path: Path) -> tuple[Path, Path]:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    rows: list[str] = []
    for package in ("numpy", "scipy", "setuptools", "wheel"):
        payload = f"{package}-wheel".encode()
        (wheelhouse / f"{package}-1.0-py3-none-any.whl").write_bytes(payload)
        rows.append(f"{package}==1.0 --hash=sha256:{_digest(payload)}")
    lock = tmp_path / "requirements.lock"
    lock.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return lock, wheelhouse


def _record_hash(payload: bytes) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
    )


def _write_valid_wheel(
    path: Path,
    *,
    source_sha: str = "a" * 40,
    source_date_epoch: int = 123,
    extra_payloads: tuple[tuple[str, bytes], ...] = (),
) -> None:
    identity_name = "structural_analysis/_canonical_build_identity.py"
    identity = (
        "# Generated only inside the exact canonical wheel build.\n"
        f'SOURCE_COMMIT_SHA = "{source_sha}"\n'
        f"SOURCE_DATE_EPOCH = {source_date_epoch}\n"
    ).encode()
    init = b"__version__ = 'test'\n"
    record_name = "structural_analysis-0.3.0.dist-info/RECORD"
    payloads = (
        ("structural_analysis/__init__.py", init),
        (identity_name, identity),
        *extra_payloads,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    for name, payload in payloads:
        writer.writerow([name, f"sha256={_record_hash(payload)}", len(payload)])
    writer.writerow([record_name, "", ""])
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in payloads:
            archive.writestr(name, payload)
        archive.writestr(record_name, buffer.getvalue())


def test_locked_wheelhouse_requires_exact_complete_hash_set(tmp_path: Path) -> None:
    lock, wheelhouse = _write_lock_and_wheelhouse(tmp_path)

    manifest = module.validate_locked_wheelhouse(wheelhouse, lock)

    assert set(manifest) == {"numpy", "scipy", "setuptools", "wheel"}
    assert all(row["sha256"].startswith("sha256:") for row in manifest.values())
    (wheelhouse / "numpy-1.0-py3-none-any.whl").write_bytes(b"tampered")
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="locked_wheelhouse_hash_set_mismatch",
    ):
        module.validate_locked_wheelhouse(wheelhouse, lock)

    (wheelhouse / "unlocked-build-dependency.tar.gz").write_bytes(b"sdist")
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="locked_wheelhouse_unadmitted_entries",
    ):
        module.validate_locked_wheelhouse(wheelhouse, lock)


def test_build_command_is_no_index_pep517_isolated_and_uses_epoch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = list(command)
        observed["environment"] = dict(kwargs["env"])
        wheel_dir = Path(command[command.index("--wheel-dir") + 1])
        wheel_dir.mkdir(parents=True, exist_ok=True)
        (wheel_dir / "structural_analysis-0.3.0-py3-none-any.whl").write_bytes(b"wheel")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    wheel = module._run_build(
        source_root=tmp_path,
        wheel_dir=tmp_path / "out",
        wheelhouse=tmp_path / "wheelhouse",
        source_date_epoch=123,
        environ={"PYTHONHASHSEED": "0"},
    )

    command = observed["command"]
    assert "--no-build-isolation" not in command
    assert "--no-index" in command
    assert "--only-binary=:all:" in command
    assert "--no-cache-dir" in command
    assert "--find-links" in command
    assert observed["environment"]["SOURCE_DATE_EPOCH"] == "123"
    assert observed["environment"]["PIP_NO_CACHE_DIR"] == "1"
    assert wheel.name == "structural_analysis-0.3.0-py3-none-any.whl"


def test_wheel_record_and_generated_source_identity_are_verified(
    tmp_path: Path,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    _write_valid_wheel(wheel)

    record = module.validate_wheel_record(
        wheel,
        source_sha="a" * 40,
        source_date_epoch=123,
    )

    assert record["all_payload_entries_sha256_verified"] is True
    assert record["entry_count"] == 3
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="wheel_record_source_sha_unbound",
    ):
        module.validate_wheel_record(
            wheel,
            source_sha="b" * 40,
            source_date_epoch=123,
        )

    with zipfile.ZipFile(wheel, "a") as archive:
        archive.writestr("structural_analysis/unrecorded.py", b"untrusted = True\n")
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="wheel_record_path_set_mismatch",
    ):
        module.validate_wheel_record(
            wheel,
            source_sha="a" * 40,
            source_date_epoch=123,
        )


def test_wheel_record_rejects_duplicate_archive_member(tmp_path: Path) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    _write_valid_wheel(wheel)
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(wheel, "a") as archive:
            archive.writestr("structural_analysis/__init__.py", b"duplicate = True\n")

    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="wheel_archive_duplicate_member",
    ):
        module.validate_wheel_record(
            wheel,
            source_sha="a" * 40,
            source_date_epoch=123,
        )


@pytest.mark.parametrize(
    "unsafe_name",
    (
        "../escape.py",
        "/absolute.py",
        "C:/drive.py",
        "back\\slash.py",
        "structural_analysis/./alias.py",
        "structural_analysis//alias.py",
    ),
)
def test_wheel_record_rejects_unsafe_archive_path(
    tmp_path: Path,
    unsafe_name: str,
) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    _write_valid_wheel(wheel, extra_payloads=((unsafe_name, b"unsafe = True\n"),))

    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="wheel_archive_member_unsafe",
    ):
        module.validate_wheel_record(
            wheel,
            source_sha="a" * 40,
            source_date_epoch=123,
        )


def test_wheel_record_rejects_symlink_member(tmp_path: Path) -> None:
    wheel = tmp_path / "structural_analysis-0.3.0-py3-none-any.whl"
    _write_valid_wheel(wheel)
    with zipfile.ZipFile(wheel, "a") as archive:
        member = zipfile.ZipInfo("structural_analysis/linked.py")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "../outside.py")

    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="wheel_archive_member_unsafe",
    ):
        module.validate_wheel_record(
            wheel,
            source_sha="a" * 40,
            source_date_epoch=123,
        )


def test_source_export_rejects_lfs_pointer_in_package_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_extract(repo_root: Path, source_sha: str, destination: Path) -> None:
        del repo_root, source_sha
        package = destination / "src/structural_analysis"
        package.mkdir(parents=True)
        (destination / "pyproject.toml").write_text("[build-system]\n")
        (destination / "README.md").write_text("readme\n")
        (package / "__init__.py").write_text("\n")
        (package / "generated_capabilities.py").write_text("ROWS = ()\n")
        (package / "payload.bin").write_bytes(
            module.LFS_POINTER_HEADER + b"oid sha256:" + b"0" * 64 + b"\n"
        )

    monkeypatch.setattr(module, "_safe_extract_git_archive", fake_extract)

    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="canonical_wheel_lfs_pointer_input",
    ):
        module._prepare_source_export(
            ROOT,
            "a" * 40,
            123,
            tmp_path / "source",
        )


def test_source_tree_rejects_submodules_and_wrong_checkout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        module,
        "_git_text",
        lambda repo_root, *args: "b" * 40 if args == ("rev-parse", "HEAD") else "",
    )
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="source_checkout_head_mismatch",
    ):
        module._validate_source_tree(ROOT, "a" * 40)

    def submodule_tree(repo_root: Path, *args: str) -> str:
        del repo_root
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        return "160000 commit " + "b" * 40 + "\tvendor/example"

    monkeypatch.setattr(module, "_git_text", submodule_tree)
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="source_tree_submodule_unsupported",
    ):
        module._validate_source_tree(ROOT, "a" * 40)


def test_built_contract_matches_schema_and_binds_replay(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_sha = "a" * 40
    epoch = 123
    monkeypatch.setattr(module, "_validate_source_tree", lambda *args: None)
    monkeypatch.setattr(module, "_source_commit_timestamp", lambda *args: epoch)
    monkeypatch.setattr(module, "_prepare_source_export", lambda *args: None)
    monkeypatch.setattr(
        module,
        "validate_locked_wheelhouse",
        lambda *args: {
            "numpy": {
                "filename": "numpy.whl",
                "version": "1",
                "sha256": "sha256:" + "1" * 64,
                "byte_length": 1,
            }
        },
    )

    def fake_build(**kwargs) -> Path:
        wheel_dir = kwargs["wheel_dir"]
        wheel_dir.mkdir(parents=True)
        wheel = wheel_dir / "structural_analysis-0.3.0-py3-none-any.whl"
        wheel.write_bytes(b"same exact wheel")
        return wheel

    monkeypatch.setattr(module, "_run_build", fake_build)
    monkeypatch.setattr(
        module,
        "validate_wheel_record",
        lambda *args, **kwargs: {
            "path": "structural_analysis-0.3.0.dist-info/RECORD",
            "sha256": "sha256:" + "2" * 64,
            "entry_count": 3,
            "all_payload_entries_sha256_verified": True,
            "source_identity_member": (
                "structural_analysis/_canonical_build_identity.py"
            ),
        },
    )
    wheel_hash = "sha256:" + hashlib.sha256(b"same exact wheel").hexdigest()
    smoke_calls: list[dict[str, object]] = []

    def fake_smoke(**kwargs):
        smoke_calls.append(dict(kwargs))
        case = {
            "result_hash": "sha256:" + "3" * 64,
            "engineering_result_hash": "sha256:" + "4" * 64,
            "checkpoint_sha256": "sha256:" + "5" * 64,
            "sample": "examples/member_feature.json",
            "checkpoint_byte_length": 123,
        }
        return {
            "schema_version": "bounded-planar-wheel-smoke.v2",
            "contract_pass": True,
            "wheel_origin": "prebuilt_exact_artifact",
            "wheel_filename": "structural_analysis-0.3.0-py3-none-any.whl",
            "wheel_sha256": wheel_hash,
            "installed_module": (
                "lib/python3.12/site-packages/structural_analysis/__init__.py"
            ),
            "installed_schema": (
                "lib/python3.12/site-packages/structural_analysis/"
                "schemas/model_ir_v2.schema.json"
            ),
            "installed_source_commit_sha": source_sha,
            "installed_source_date_epoch": epoch,
            "cases": {"member_feature": case, "prescribed_settlement": case},
            "claim_boundary": "test boundary",
        }

    monkeypatch.setattr(module, "run_wheel_smoke", fake_smoke)

    payload = module.build_contract(
        repo_root=ROOT,
        source_sha=source_sha,
        source_date_epoch=epoch,
        dependency_lock=(
            ROOT / "canonical/requirements-cp312-manylinux2014-x86_64.lock"
        ),
        wheelhouse=tmp_path / "wheelhouse",
        output_wheel_dir=tmp_path / "out",
        environ={"SOURCE_DATE_EPOCH": str(epoch)},
    )

    schema = json.loads(
        (ROOT / "canonical/canonical-project-wheel-contract.v1.schema.json").read_text()
    )
    Draft202012Validator(schema).validate(payload)
    assert payload["wheel"]["sha256"] == wheel_hash
    assert payload["wheel"]["repeat_sha256"] == wheel_hash
    assert payload["installed_replay"]["installed_source_commit_sha"] == source_sha
    assert payload["installed_replay"]["execution_count"] == 2
    assert payload["installed_replay"]["exact_repeat_match"] is True
    replay = payload["installed_replay"]
    assert replay["repeat_cases"] == replay["cases"]
    assert set(replay["repeat_cases"]) == {
        "member_feature",
        "prescribed_settlement",
    }
    for case_set in (replay["cases"], replay["repeat_cases"]):
        assert all(
            set(case)
            == {
                "result_hash",
                "engineering_result_hash",
                "checkpoint_sha256",
            }
            for case in case_set.values()
        )
    assert replay["first_projection_sha256"] == module._canonical_hash(
        module._installed_replay_projection(replay)
    )
    assert replay["repeat_projection_sha256"] == module._canonical_hash(
        module._installed_replay_projection(replay, cases_key="repeat_cases")
    )
    assert len(smoke_calls) == 2

    mismatch_calls = 0

    def mismatched_smoke(**kwargs):
        nonlocal mismatch_calls
        mismatch_calls += 1
        candidate = json.loads(json.dumps(fake_smoke(**kwargs)))
        if mismatch_calls == 2:
            candidate["cases"]["member_feature"]["checkpoint_sha256"] = (
                "sha256:" + "9" * 64
            )
        return candidate

    monkeypatch.setattr(module, "run_wheel_smoke", mismatched_smoke)
    with pytest.raises(
        module.CanonicalProjectWheelError,
        match="canonical_installed_wheel_replay_reproducibility_mismatch",
    ):
        module.build_contract(
            repo_root=ROOT,
            source_sha=source_sha,
            source_date_epoch=epoch,
            dependency_lock=(
                ROOT / "canonical/requirements-cp312-manylinux2014-x86_64.lock"
            ),
            wheelhouse=tmp_path / "wheelhouse",
            output_wheel_dir=tmp_path / "out-mismatch",
            environ={"SOURCE_DATE_EPOCH": str(epoch)},
        )
