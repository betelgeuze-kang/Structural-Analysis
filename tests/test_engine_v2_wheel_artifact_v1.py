from __future__ import annotations

import base64
import csv
from dataclasses import replace
import hashlib
import io
import os
from pathlib import Path
import stat
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from structural_analysis.engine_v2.evidence import wheel_artifact_v1 as artifact


_FILENAME = "demo_pkg-1.2.3-py3-none-any.whl"
_DIST_INFO = "demo_pkg-1.2.3.dist-info"


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _csv_bytes(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode("utf-8")


def _zip_info(name: str, *, mode: int = stat.S_IFREG | 0o644) -> ZipInfo:
    info = ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = mode << 16
    info.compress_type = ZIP_DEFLATED
    return info


def _build_wheel(
    root: Path,
    *,
    filename: str = _FILENAME,
    metadata_name: str = "demo-pkg",
    metadata_version: str = "1.2.3",
    requires_dist: tuple[str, ...] = (
        "NumPy >= 1.23",
        "typing_extensions ; python_version < '3.11'",
    ),
    wheel_tags: tuple[str, ...] = ("py3-none-any",),
    console_scripts: tuple[str, ...] = (),
    extra_entries: tuple[tuple[str, bytes, int], ...] = (),
    record_transform=None,
    metadata_override: bytes | None = None,
    wheel_metadata_override: bytes | None = None,
) -> Path:
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {metadata_name}\n"
        f"Version: {metadata_version}\n"
        + "".join(f"Requires-Dist: {item}\n" for item in requires_dist)
        + "\n"
    ).encode()
    wheel_metadata = (
        "Wheel-Version: 1.0\n"
        "Generator: wheel-artifact-test\n"
        "Root-Is-Purelib: true\n"
        + "".join(f"Tag: {tag}\n" for tag in wheel_tags)
        + "\n"
    ).encode()
    entries: list[tuple[str, bytes, int]] = [
        ("demo_pkg/__init__.py", b"VALUE = 7\n", stat.S_IFREG | 0o644),
        (
            f"{_DIST_INFO}/METADATA",
            metadata if metadata_override is None else metadata_override,
            stat.S_IFREG | 0o644,
        ),
        (
            f"{_DIST_INFO}/WHEEL",
            wheel_metadata
            if wheel_metadata_override is None
            else wheel_metadata_override,
            stat.S_IFREG | 0o644,
        ),
        *extra_entries,
    ]
    if console_scripts:
        entry_points = (
            "[console_scripts]\n"
            + "".join(f"{name} = demo_pkg:main\n" for name in console_scripts)
        ).encode()
        entries.append(
            (
                f"{_DIST_INFO}/entry_points.txt",
                entry_points,
                stat.S_IFREG | 0o644,
            )
        )
    rows = [[name, _record_hash(data), str(len(data))] for name, data, _ in entries]
    rows.append([f"{_DIST_INFO}/RECORD", "", ""])
    if record_transform is not None:
        rows = record_transform(rows)
    record = _csv_bytes(rows)
    entries.append((f"{_DIST_INFO}/RECORD", record, stat.S_IFREG | 0o644))
    path = root / filename
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
            for name, data, mode in entries:
                archive.writestr(_zip_info(name, mode=mode), data)
    return path


def _assert_code(path: Path, expected: str) -> None:
    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.inspect_wheel_artifact_v1(path)
    assert caught.value.code == expected
    assert caught.value.path.startswith("/")
    assert len(caught.value.message) <= 240


def _install_wheel(
    wheel: Path,
    root: Path,
    *,
    extra: tuple[str, bytes] | None = None,
) -> None:
    with ZipFile(wheel) as archive:
        record_path = f"{_DIST_INFO}/RECORD"
        record = archive.read(record_path)
        for info in archive.infolist():
            if info.filename == record_path:
                continue
            destination = root.joinpath(*info.filename.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
    if extra is not None:
        extra_path, data = extra
        destination = root.joinpath(*extra_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        record += _csv_bytes([[extra_path, _record_hash(data), str(len(data))]])
    destination = root / _DIST_INFO / "RECORD"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(record)


def test_inspect_wheel_returns_frozen_complete_canonical_identity(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(tmp_path)

    identity = artifact.inspect_wheel_artifact_v1(wheel)

    assert identity.schema_version == artifact.WHEEL_ARTIFACT_SCHEMA_VERSION_V1
    assert identity.wheel_filename == _FILENAME
    assert identity.distribution_name == "demo-pkg"
    assert identity.canonical_distribution_name == "demo-pkg"
    assert identity.distribution_version == "1.2.3"
    assert identity.canonical_distribution_version == "1.2.3"
    assert identity.build_tag is None
    assert identity.wheel_tags == ("py3-none-any",)
    assert identity.requires_dist == (
        "numpy>=1.23",
        'typing-extensions; python_version < "3.11"',
    )
    assert identity.byte_count == wheel.stat().st_size
    assert identity.sha256 == f"sha256:{hashlib.sha256(wheel.read_bytes()).hexdigest()}"
    assert identity.member_count == 4
    assert identity.uncompressed_byte_count == sum(
        member.byte_count for member in identity.members
    )
    assert tuple(member.path for member in identity.members) == tuple(
        sorted(member.path for member in identity.members)
    )
    assert identity.to_dict()["identity_hash"] == identity.identity_hash
    artifact.validate_wheel_artifact_identity_v1(identity)
    with pytest.raises((AttributeError, TypeError)):
        identity.byte_count = 0  # type: ignore[misc]


def test_build_tag_and_compressed_filename_tags_are_cross_checked(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(
        tmp_path,
        filename="demo_pkg-1.2.3-7-py2.py3-none-any.whl",
        wheel_tags=("py2-none-any", "py3-none-any"),
    )

    identity = artifact.inspect_wheel_artifact_v1(wheel)

    assert identity.build_tag == "7"
    assert identity.wheel_tags == ("py2-none-any", "py3-none-any")


def test_inspector_uses_no_follow_close_on_exec_and_same_fd_for_zip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _build_wheel(tmp_path)
    real_open = artifact.os.open
    real_zip = artifact.ZipFile
    opened: list[tuple[int, int]] = []
    zip_fds: list[int] = []

    def tracking_open(path, flags, *args, **kwargs):
        fd = real_open(path, flags, *args, **kwargs)
        if os.fspath(path) == os.fspath(wheel):
            opened.append((fd, flags))
        return fd

    def tracking_zip(file, *args, **kwargs):
        zip_fds.append(file.fileno())
        return real_zip(file, *args, **kwargs)

    monkeypatch.setattr(artifact.os, "open", tracking_open)
    monkeypatch.setattr(artifact, "ZipFile", tracking_zip)

    artifact.inspect_wheel_artifact_v1(wheel)

    assert len(opened) == 1
    assert opened[0][1] & os.O_NOFOLLOW
    assert opened[0][1] & os.O_CLOEXEC
    assert zip_fds == [opened[0][0]]


def test_symlink_wheel_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    link_root = tmp_path / "links"
    link_root.mkdir()
    link = link_root / _FILENAME
    link.symlink_to(wheel)

    _assert_code(link, "wheel_artifact_symlink_forbidden")


def test_fifo_wheel_is_opened_nonblocking_and_rejected(tmp_path: Path) -> None:
    wheel = tmp_path / _FILENAME
    os.mkfifo(wheel)

    _assert_code(wheel, "wheel_artifact_not_regular")


def test_path_inode_replacement_during_parse_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _build_wheel(tmp_path)
    replacement_root = tmp_path / "replacement"
    replacement_root.mkdir()
    replacement = _build_wheel(replacement_root)
    real_zip = artifact.ZipFile
    replaced = False

    def replacing_zip(file, *args, **kwargs):
        nonlocal replaced
        if not replaced:
            os.replace(replacement, wheel)
            replaced = True
        return real_zip(file, *args, **kwargs)

    monkeypatch.setattr(artifact, "ZipFile", replacing_zip)

    _assert_code(wheel, "wheel_artifact_path_replaced")


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("../escape.py", "wheel_archive_path_traversal"),
        ("pkg/../escape.py", "wheel_archive_path_traversal"),
        ("pkg//escape.py", "wheel_archive_path_traversal"),
        ("/absolute.py", "wheel_archive_absolute_path"),
        ("C:/absolute.py", "wheel_archive_absolute_path"),
        ("pkg\\escape.py", "wheel_archive_backslash_forbidden"),
        ("pkg/control\n.py", "wheel_archive_member_name_invalid"),
        ("pkg/control\x7f.py", "wheel_archive_member_name_invalid"),
        ("pkg/cafe\u0301.py", "wheel_archive_nfc_invalid"),
    ],
)
def test_unsafe_archive_member_names_are_rejected(
    tmp_path: Path, name: str, expected: str
) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=((name, b"unsafe", stat.S_IFREG | 0o644),),
    )

    _assert_code(wheel, expected)


def test_nul_member_name_is_rejected_from_raw_central_directory(tmp_path: Path) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(("pkg/badXname.py", b"unsafe", stat.S_IFREG | 0o644),),
    )
    raw = wheel.read_bytes()
    assert raw.count(b"pkg/badXname.py") == 2
    wheel.write_bytes(raw.replace(b"pkg/badXname.py", b"pkg/bad\x00name.py"))

    _assert_code(wheel, "wheel_archive_nul_forbidden")


def test_duplicate_archive_member_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(("demo_pkg/__init__.py", b"duplicate", stat.S_IFREG | 0o644),),
    )

    _assert_code(wheel, "wheel_archive_member_duplicate")


def test_casefold_archive_collision_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(("DEMO_PKG/__INIT__.PY", b"collision", stat.S_IFREG | 0o644),),
    )

    _assert_code(wheel, "wheel_archive_casefold_collision")


def test_file_and_implicit_directory_prefix_collision_is_rejected(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(("demo_pkg", b"not-a-directory", stat.S_IFREG | 0o644),),
    )

    _assert_code(wheel, "wheel_archive_path_prefix_collision")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (stat.S_IFLNK | 0o777, "wheel_archive_symlink_forbidden"),
        (stat.S_IFIFO | 0o600, "wheel_archive_non_regular_member"),
        (stat.S_IFDIR | 0o755, "wheel_archive_non_regular_member"),
    ],
)
def test_non_regular_archive_members_are_rejected(
    tmp_path: Path, mode: int, expected: str
) -> None:
    name = "bad"
    wheel = _build_wheel(
        tmp_path,
        extra_entries=((name, b"target", mode),),
    )

    _assert_code(wheel, expected)


def test_encrypted_flag_is_rejected_before_member_read(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    raw = bytearray(wheel.read_bytes())
    for signature, flag_offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = 0
        while True:
            index = raw.find(signature, start)
            if index < 0:
                break
            flags = int.from_bytes(
                raw[index + flag_offset : index + flag_offset + 2], "little"
            )
            raw[index + flag_offset : index + flag_offset + 2] = (flags | 1).to_bytes(
                2, "little"
            )
            start = index + 4
    wheel.write_bytes(raw)

    _assert_code(wheel, "wheel_archive_encrypted_member")


def test_local_header_only_encrypted_flag_is_also_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    raw = bytearray(wheel.read_bytes())
    index = raw.find(b"PK\x03\x04")
    assert index >= 0
    flags = int.from_bytes(raw[index + 6 : index + 8], "little")
    raw[index + 6 : index + 8] = (flags | 1).to_bytes(2, "little")
    wheel.write_bytes(raw)

    _assert_code(wheel, "wheel_archive_encrypted_member")


def test_high_ratio_zip_bomb_is_rejected_by_fixed_bound(tmp_path: Path) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(
            ("demo_pkg/zeros.bin", b"\x00" * (8 * 1024 * 1024), stat.S_IFREG | 0o644),
        ),
    )

    _assert_code(wheel, "wheel_archive_compression_ratio_exceeded")


def test_member_count_is_bounded_before_zipfile_allocates_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wheel = _build_wheel(tmp_path)
    monkeypatch.setattr(artifact, "WHEEL_ARTIFACT_MAX_MEMBER_COUNT_V1", 3)

    def zipfile_must_not_run(*args, **kwargs):
        raise AssertionError("EOCD preflight must reject before ZipFile construction")

    monkeypatch.setattr(artifact, "ZipFile", zipfile_must_not_run)

    _assert_code(wheel, "wheel_archive_member_count_exceeded")


def test_trailing_bytes_after_eocd_are_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    wheel.write_bytes(wheel.read_bytes() + b"trailing-ambiguity")

    _assert_code(wheel, "wheel_archive_invalid")


def test_second_dist_info_directory_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(
        tmp_path,
        extra_entries=(("other-1.0.dist-info/METADATA", b"x", stat.S_IFREG | 0o644),),
    )

    _assert_code(wheel, "wheel_dist_info_invalid")


@pytest.mark.parametrize(
    ("transform", "expected"),
    [
        (lambda rows: rows[:-1], "wheel_record_self_invalid"),
        (
            lambda rows: [*rows[:-1], [rows[-1][0], "sha256=bad", "1"]],
            "wheel_record_self_invalid",
        ),
        (
            lambda rows: [[rows[0][0], rows[0][1] + "=", rows[0][2]], *rows[1:]],
            "wheel_record_hash_invalid",
        ),
        (
            lambda rows: [[rows[0][0], rows[0][1], "0" + rows[0][2]], *rows[1:]],
            "wheel_record_size_invalid",
        ),
        (
            lambda rows: [[rows[0][0], _record_hash(b"wrong"), rows[0][2]], *rows[1:]],
            "wheel_record_hash_mismatch",
        ),
        (
            lambda rows: [
                [rows[0][0], rows[0][1], str(int(rows[0][2]) + 1)],
                *rows[1:],
            ],
            "wheel_record_size_mismatch",
        ),
        (
            lambda rows: [*rows, ["ghost.py", _record_hash(b"ghost"), "5"]],
            "wheel_record_member_set_mismatch",
        ),
        (
            lambda rows: [[*rows[0], "fourth"], *rows[1:]],
            "wheel_record_row_invalid",
        ),
    ],
)
def test_strict_record_rejects_adversarial_rows(
    tmp_path: Path, transform, expected: str
) -> None:
    wheel = _build_wheel(tmp_path, record_transform=transform)

    _assert_code(wheel, expected)


def test_record_must_cover_every_archive_regular_member_once(tmp_path: Path) -> None:
    def omit_package(rows: list[list[str]]) -> list[list[str]]:
        return [row for row in rows if row[0] != "demo_pkg/__init__.py"]

    wheel = _build_wheel(tmp_path, record_transform=omit_package)

    _assert_code(wheel, "wheel_record_member_set_mismatch")


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"metadata_name": "other"}, "wheel_metadata_name_mismatch"),
        ({"metadata_version": "2.0"}, "wheel_metadata_version_mismatch"),
        ({"wheel_tags": ("cp311-cp311-linux_x86_64",)}, "wheel_tag_mismatch"),
        ({"filename": "not-a-wheel.whl"}, "wheel_filename_invalid"),
    ],
)
def test_metadata_name_version_tag_and_filename_are_cross_validated(
    tmp_path: Path, kwargs: dict[str, object], expected: str
) -> None:
    wheel = _build_wheel(tmp_path, **kwargs)

    _assert_code(wheel, expected)


def test_invalid_and_duplicate_requires_dist_are_rejected(tmp_path: Path) -> None:
    invalid = _build_wheel(tmp_path, requires_dist=("not a valid requirement ???",))
    _assert_code(invalid, "wheel_metadata_dependency_invalid")

    invalid.unlink()
    duplicate = _build_wheel(tmp_path, requires_dist=("NumPy>=1", "numpy >= 1"))
    _assert_code(duplicate, "wheel_metadata_dependency_invalid")


def test_identity_structural_validator_rejects_hash_and_semantic_tamper(
    tmp_path: Path,
) -> None:
    identity = artifact.inspect_wheel_artifact_v1(_build_wheel(tmp_path))

    with pytest.raises(artifact.WheelArtifactV1Error) as hash_error:
        artifact.validate_wheel_artifact_identity_v1(
            replace(identity, identity_hash="sha256:" + "0" * 64)
        )
    assert hash_error.value.code == "wheel_identity_hash_mismatch"

    with pytest.raises(artifact.WheelArtifactV1Error) as semantic_error:
        artifact.validate_wheel_artifact_identity_v1(
            replace(identity, wheel_tags=("cp311-cp311-linux_x86_64",))
        )
    assert semantic_error.value.code == "wheel_identity_semantics_invalid"

    oversized_members = tuple(
        artifact.WheelArtifactMemberIdentityV1(
            path=f"oversized/{index}.bin",
            byte_count=artifact.WHEEL_ARTIFACT_MAX_MEMBER_BYTES_V1,
            sha256="sha256:" + f"{index + 1:064x}",
        )
        for index in range(5)
    )
    with pytest.raises(artifact.WheelArtifactV1Error) as extent_error:
        artifact.validate_wheel_artifact_identity_v1(
            replace(
                identity,
                members=oversized_members,
                member_count=len(oversized_members),
                uncompressed_byte_count=sum(
                    member.byte_count for member in oversized_members
                ),
            )
        )
    assert extent_error.value.code == "wheel_identity_semantics_invalid"


def test_record_parser_rejects_rows_beyond_explicit_bound() -> None:
    record_path = f"{_DIST_INFO}/RECORD"
    data = _csv_bytes(
        [
            ["demo_pkg/__init__.py", _record_hash(b"x"), "1"],
            [record_path, "", ""],
        ]
    )

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact._parse_record(
            data,
            record_path=record_path,
            installed=False,
            max_rows=1,
        )
    assert caught.value.code == "wheel_record_invalid"


def test_installed_root_replay_verifies_wheel_bytes_and_aggregates_extras(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    extra_path = "demo_pkg/__pycache__/__init__.cpython-311.pyc"
    _install_wheel(wheel, installed, extra=(extra_path, b"generated-bytecode"))

    replay = artifact.replay_installed_wheel_artifact_v1(
        wheel_path=wheel,
        installed_root=installed,
    )

    assert replay.schema_version == artifact.INSTALLED_WHEEL_REPLAY_SCHEMA_VERSION_V1
    assert replay.verified_wheel_member_count == replay.wheel_identity.member_count - 1
    assert replay.extra_file_count == 1
    assert replay.extra_byte_count == len(b"generated-bytecode")
    assert replay.extra_files[0].path == extra_path
    assert replay.to_dict()["replay_hash"] == replay.replay_hash
    artifact.validate_installed_wheel_replay_v1(replay)


def test_installed_fifo_member_is_opened_nonblocking_and_rejected(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    member = installed / "demo_pkg" / "__init__.py"
    member.unlink()
    os.mkfifo(member)

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert caught.value.code == "installed_wheel_file_not_regular"


def test_venv_scripts_are_limited_to_declared_entry_points_and_explicit_root(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(
        tmp_path,
        console_scripts=("structural-analysis", "structural-analysis-benchmark"),
    )
    site_packages = tmp_path / "venv" / "lib" / "python3.10" / "site-packages"
    scripts_root = tmp_path / "venv" / "bin"
    _install_wheel(wheel, site_packages)
    scripts_root.mkdir(parents=True)
    record = site_packages / _DIST_INFO / "RECORD"
    script_rows: list[list[str]] = []
    for name in ("structural-analysis", "structural-analysis-benchmark"):
        data = f"#!/bin/sh\nexec {name}\n".encode()
        (scripts_root / name).write_bytes(data)
        record_path = os.path.relpath(scripts_root / name, site_packages).replace(
            os.sep, "/"
        )
        script_rows.append([record_path, _record_hash(data), str(len(data))])
    record.write_bytes(record.read_bytes() + _csv_bytes(script_rows))

    identity = artifact.inspect_wheel_artifact_v1(wheel)
    assert identity.console_scripts == (
        "structural-analysis",
        "structural-analysis-benchmark",
    )
    with pytest.raises(artifact.WheelArtifactV1Error) as missing_root:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=site_packages,
        )
    assert missing_root.value.code == "installed_scripts_root_missing"

    replay = artifact.replay_installed_wheel_artifact_v1(
        wheel_path=wheel,
        installed_root=site_packages,
        installed_scripts_root=scripts_root,
    )

    assert replay.extra_file_count == 0
    assert replay.script_file_count == 2
    assert {item.entry_point_name for item in replay.script_files} == {
        "structural-analysis",
        "structural-analysis-benchmark",
    }
    assert all(
        item.record_path.startswith("../") and "/bin/" in item.record_path
        for item in replay.script_files
    )
    artifact.validate_installed_wheel_replay_v1(replay)


def test_only_declared_script_basename_may_escape_installed_root(
    tmp_path: Path,
) -> None:
    wheel = _build_wheel(tmp_path, console_scripts=("allowed-command",))
    site_packages = tmp_path / "venv" / "lib" / "python3.10" / "site-packages"
    scripts_root = tmp_path / "venv" / "bin"
    _install_wheel(wheel, site_packages)
    scripts_root.mkdir(parents=True)
    rogue = scripts_root / "rogue-command"
    rogue.write_bytes(b"rogue")
    record = site_packages / _DIST_INFO / "RECORD"
    rogue_record_path = os.path.relpath(rogue, site_packages).replace(os.sep, "/")
    record.write_bytes(
        record.read_bytes()
        + _csv_bytes([[rogue_record_path, _record_hash(b"rogue"), "5"]])
    )

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=site_packages,
            installed_scripts_root=scripts_root,
        )
    assert caught.value.code == "installed_record_path_escape"


def test_installed_root_replay_rejects_changed_wheel_file(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    (installed / "demo_pkg" / "__init__.py").write_bytes(b"tampered")

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert caught.value.code == "installed_wheel_file_size_mismatch"


def test_installed_record_wheel_rows_must_remain_exact(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    record = installed / _DIST_INFO / "RECORD"
    rows = list(csv.reader(io.StringIO(record.read_text(), newline="")))
    rows[0][1] = _record_hash(b"different")
    record.write_bytes(_csv_bytes(rows))

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert caught.value.code == "installed_record_member_mismatch"


def test_installed_record_root_escape_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    record = installed / _DIST_INFO / "RECORD"
    record.write_bytes(
        record.read_bytes()
        + _csv_bytes([["../escape.py", _record_hash(b"escape"), "6"]])
    )

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert caught.value.code == "installed_record_path_escape"


def test_installed_symlink_file_and_root_are_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    package_file = installed / "demo_pkg" / "__init__.py"
    outside = tmp_path / "outside.py"
    outside.write_bytes(b"VALUE = 7\n")
    package_file.unlink()
    package_file.symlink_to(outside)

    with pytest.raises(artifact.WheelArtifactV1Error) as file_error:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert file_error.value.code == "installed_wheel_file_symlink_forbidden"

    root_link = tmp_path / "installed-link"
    root_link.symlink_to(installed, target_is_directory=True)
    with pytest.raises(artifact.WheelArtifactV1Error) as root_error:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=root_link,
        )
    assert root_error.value.code == "installed_root_symlink_forbidden"


def test_installed_intermediate_symlink_directory_is_rejected(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    outside_package = tmp_path / "outside-package"
    outside_package.mkdir()
    (outside_package / "__init__.py").write_bytes(b"VALUE = 7\n")
    package = installed / "demo_pkg"
    (package / "__init__.py").unlink()
    package.rmdir()
    package.symlink_to(outside_package, target_is_directory=True)

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.replay_installed_wheel_artifact_v1(
            wheel_path=wheel,
            installed_root=installed,
        )
    assert caught.value.code == "installed_wheel_file_symlink_forbidden"


def test_installed_replay_structural_validator_rejects_tamper(tmp_path: Path) -> None:
    wheel = _build_wheel(tmp_path)
    installed = tmp_path / "installed"
    _install_wheel(wheel, installed)
    replay = artifact.replay_installed_wheel_artifact_v1(
        wheel_path=wheel,
        installed_root=installed,
    )

    with pytest.raises(artifact.WheelArtifactV1Error) as caught:
        artifact.validate_installed_wheel_replay_v1(
            replace(replay, replay_hash="sha256:" + "f" * 64)
        )
    assert caught.value.code == "installed_wheel_replay_hash_mismatch"


def test_stable_error_code_registry_covers_emitted_public_errors() -> None:
    expected = {
        "wheel_artifact_symlink_forbidden",
        "wheel_archive_member_duplicate",
        "wheel_archive_nfc_invalid",
        "wheel_archive_casefold_collision",
        "wheel_archive_path_traversal",
        "wheel_archive_backslash_forbidden",
        "wheel_archive_nul_forbidden",
        "wheel_archive_absolute_path",
        "wheel_archive_symlink_forbidden",
        "wheel_archive_encrypted_member",
        "wheel_archive_compression_ratio_exceeded",
        "wheel_record_self_invalid",
        "wheel_record_hash_mismatch",
        "wheel_record_size_mismatch",
        "wheel_identity_hash_mismatch",
        "installed_record_path_escape",
        "installed_wheel_replay_hash_mismatch",
    }
    assert expected <= artifact.WHEEL_ARTIFACT_STABLE_ERROR_CODES_V1
