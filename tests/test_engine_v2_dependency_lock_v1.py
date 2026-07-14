from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import stat
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from structural_analysis.engine_v2.contracts._canonical import (
    canonical_hash,
    canonical_json_bytes,
)
from structural_analysis.engine_v2.evidence.dependency_lock_v1 import (
    DEPENDENCY_LOCK_SCHEMA_VERSION_V1,
    DependencyLockV1Error,
    validate_dependency_lock_receipt_v1,
    verify_dependency_artifact_lock_v1,
)
from structural_analysis.engine_v2.evidence.wheel_artifact_v1 import (
    inspect_wheel_artifact_v1,
)


def _record_hash(data: bytes) -> str:
    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _csv_bytes(rows: list[list[str]]) -> bytes:
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode("utf-8")


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = ZIP_DEFLATED
    return info


def _build_wheel(
    root: Path,
    *,
    name: str,
    version: str,
    requires_dist: tuple[str, ...] = (),
) -> Path:
    filename_name = name.replace("-", "_")
    filename = f"{filename_name}-{version}-py3-none-any.whl"
    dist_info = f"{filename_name}-{version}.dist-info"
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        + "".join(f"Requires-Dist: {value}\n" for value in requires_dist)
        + "\n"
    ).encode()
    wheel_metadata = (
        "Wheel-Version: 1.0\n"
        "Generator: dependency-lock-test\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n\n"
    ).encode()
    entries = [
        (f"{filename_name}/__init__.py", b"VALUE = 1\n"),
        (f"{dist_info}/METADATA", metadata),
        (f"{dist_info}/WHEEL", wheel_metadata),
    ]
    record_rows = [[path, _record_hash(data), str(len(data))] for path, data in entries]
    record_path = f"{dist_info}/RECORD"
    record_rows.append([record_path, "", ""])
    entries.append((record_path, _csv_bytes(record_rows)))
    destination = root / filename
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path, data in entries:
            archive.writestr(_zip_info(path), data)
    return destination


def _environment(*, python_version: str = "3.10") -> dict[str, str]:
    full_version = f"{python_version}.12"
    return {
        "implementation_name": "cpython",
        "implementation_version": full_version,
        "os_name": "posix",
        "platform_machine": "x86_64",
        "platform_python_implementation": "CPython",
        "platform_release": "6.8.0",
        "platform_system": "Linux",
        "platform_version": "test-kernel",
        "python_full_version": full_version,
        "python_version": python_version,
        "sys_platform": "linux",
    }


def _row(path: Path, *, direct: bool) -> dict[str, object]:
    identity = inspect_wheel_artifact_v1(path)
    return {
        "name": identity.canonical_distribution_name,
        "version": identity.canonical_distribution_version,
        "filename": identity.wheel_filename,
        "byte_count": identity.byte_count,
        "sha256": identity.sha256,
        "direct": direct,
    }


def _lock_bytes(
    rows: list[dict[str, object]],
    *,
    environment: dict[str, str] | None = None,
) -> bytes:
    payload: dict[str, object] = {
        "schema_version": DEPENDENCY_LOCK_SCHEMA_VERSION_V1,
        "target_environment": _environment() if environment is None else environment,
        "artifacts": rows,
    }
    payload["lock_hash"] = canonical_hash(payload)
    return canonical_json_bytes(payload)


def _root_identity(
    tmp_path: Path,
    *,
    requires_dist: tuple[str, ...],
):
    root = tmp_path / "root"
    root.mkdir()
    return inspect_wheel_artifact_v1(
        _build_wheel(
            root,
            name="solver-root",
            version="1.0.0",
            requires_dist=requires_dist,
        )
    )


def _assert_code(
    raw_lock: bytes,
    *,
    artifact_root: Path,
    root_identity,
    expected: str,
) -> None:
    with pytest.raises(DependencyLockV1Error) as caught:
        verify_dependency_artifact_lock_v1(
            raw_lock,
            artifact_root=artifact_root,
            root_wheel_identity=root_identity,
        )
    assert caught.value.code == expected
    assert caught.value.path.startswith("/")


def test_exact_runtime_closure_replays_wheels_markers_and_dependency_extras(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    alpha = _build_wheel(
        wheelhouse,
        name="alpha",
        version="1.2.0",
        requires_dist=("beta[fast]==2.0.0",),
    )
    beta = _build_wheel(
        wheelhouse,
        name="beta",
        version="2.0.0",
        requires_dist=(
            'gamma==3.0.0; extra == "fast"',
            'never-installed==1.0; extra == "slow"',
        ),
    )
    gamma = _build_wheel(wheelhouse, name="gamma", version="3.0.0")
    root = _root_identity(
        tmp_path,
        requires_dist=(
            'alpha>=1.0; python_version >= "3.10"',
            'inactive==1.0; python_version < "3.0"',
        ),
    )
    rows = sorted(
        [
            _row(alpha, direct=True),
            _row(beta, direct=False),
            _row(gamma, direct=False),
        ],
        key=lambda item: str(item["name"]),
    )

    receipt = verify_dependency_artifact_lock_v1(
        _lock_bytes(rows),
        artifact_root=wheelhouse,
        root_wheel_identity=root,
    )

    assert receipt.artifact_count == 3
    assert receipt.direct_dependency_names == ("alpha",)
    assert receipt.transitive_dependency_names == ("beta", "gamma")
    assert receipt.root_requirements_matched is True
    assert receipt.transitive_closure_matched is True
    assert receipt.claims.build_dependencies_verified is False
    assert receipt.claims.source_build_reproducibility_proven is False
    assert receipt.claims.environment_reproducibility_proven is False
    assert receipt.to_dict()["receipt_hash"] == receipt.receipt_hash
    assert validate_dependency_lock_receipt_v1(receipt) is receipt


def test_marker_environment_selects_only_active_dependencies(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    root = _root_identity(
        tmp_path,
        requires_dist=('future-dep==1.0.0; python_version >= "3.11"',),
    )

    receipt = verify_dependency_artifact_lock_v1(
        _lock_bytes([], environment=_environment(python_version="3.10")),
        artifact_root=wheelhouse,
        root_wheel_identity=root,
    )

    assert receipt.artifact_count == 0
    assert receipt.direct_dependency_names == ()


def test_wheelhouse_rejects_unlisted_subdirectories(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    nested = wheelhouse / "unlisted"
    nested.mkdir()
    _build_wheel(nested, name="evil", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=())

    _assert_code(
        _lock_bytes([]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_wheelhouse_entry_invalid",
    )


def test_locked_version_must_satisfy_every_active_requirement(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    dependency = _build_wheel(wheelhouse, name="alpha", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=("alpha>=2.0.0",))

    _assert_code(
        _lock_bytes([_row(dependency, direct=True)]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_requirement_version_mismatch",
    )


def test_missing_active_dependency_is_rejected_without_allowlist(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    root = _root_identity(tmp_path, requires_dist=("setuptools>=70",))

    _assert_code(
        _lock_bytes([]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_dependency_missing",
    )


def test_extra_locked_dependency_and_extra_wheelhouse_file_are_rejected(
    tmp_path: Path,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    dependency = _build_wheel(wheelhouse, name="unused", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=())
    row = _row(dependency, direct=False)

    _assert_code(
        _lock_bytes([row]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_dependency_extra",
    )

    _assert_code(
        _lock_bytes([]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_wheelhouse_artifact_extra",
    )


def test_artifact_byte_tamper_is_detected_by_reinspection(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    dependency = _build_wheel(wheelhouse, name="alpha", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=("alpha==1.0.0",))
    raw_lock = _lock_bytes([_row(dependency, direct=True)])
    dependency.write_bytes(dependency.read_bytes() + b"tamper")

    _assert_code(
        raw_lock,
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_artifact_identity_mismatch",
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("noncanonical", "dependency_lock_json_not_canonical"),
        ("duplicate", "dependency_lock_json_duplicate_key"),
        ("nonfinite", "dependency_lock_json_invalid"),
        ("path", "dependency_lock_artifact_filename_unsafe"),
        ("name-alias", "dependency_lock_distribution_name_alias"),
        ("version-alias", "dependency_lock_distribution_version_alias"),
    ],
)
def test_noncanonical_duplicate_nonfinite_path_and_alias_inputs_fail_closed(
    tmp_path: Path,
    mutation: str,
    expected: str,
) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    dependency = _build_wheel(wheelhouse, name="alpha", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=("alpha==1.0.0",))
    row = _row(dependency, direct=True)
    raw = _lock_bytes([row])
    if mutation == "noncanonical":
        raw = raw + b"\n"
    elif mutation == "duplicate":
        raw = raw.replace(b'"artifacts":[', b'"artifacts":[],"artifacts":[')
    elif mutation == "nonfinite":
        raw = raw.replace(
            f'"byte_count":{row["byte_count"]}'.encode(),
            b'"byte_count":NaN',
        )
    else:
        changed = dict(row)
        if mutation == "path":
            changed["filename"] = "../alpha.whl"
        elif mutation == "name-alias":
            changed["name"] = "Alpha_Pkg"
        else:
            changed["version"] = "v1.0.0"
        raw = _lock_bytes([changed])

    _assert_code(
        raw,
        artifact_root=wheelhouse,
        root_identity=root,
        expected=expected,
    )


def test_lock_hash_and_direct_flag_are_derived_not_trusted(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    dependency = _build_wheel(wheelhouse, name="alpha", version="1.0.0")
    root = _root_identity(tmp_path, requires_dist=("alpha==1.0.0",))
    row = _row(dependency, direct=False)

    _assert_code(
        _lock_bytes([row]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_direct_flag_mismatch",
    )

    parsed = json.loads(_lock_bytes([{**row, "direct": True}]))
    parsed["lock_hash"] = "sha256:" + "0" * 64
    _assert_code(
        canonical_json_bytes(parsed),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_hash_mismatch",
    )


def test_artifact_rows_are_unique_and_canonically_ordered(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    alpha = _build_wheel(wheelhouse, name="alpha", version="1.0.0")
    beta = _build_wheel(wheelhouse, name="beta", version="1.0.0")
    root = _root_identity(
        tmp_path,
        requires_dist=("alpha==1.0.0", "beta==1.0.0"),
    )
    alpha_row = _row(alpha, direct=True)
    beta_row = _row(beta, direct=True)

    _assert_code(
        _lock_bytes([beta_row, alpha_row]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_artifact_order_invalid",
    )
    alpha.unlink()
    _assert_code(
        _lock_bytes([beta_row, beta_row]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_artifact_name_duplicate",
    )


def test_wheelhouse_symlink_entry_is_never_followed(tmp_path: Path) -> None:
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    dependency = _build_wheel(outside, name="alpha", version="1.0.0")
    link = wheelhouse / dependency.name
    link.symlink_to(dependency)
    root = _root_identity(tmp_path, requires_dist=("alpha==1.0.0",))

    _assert_code(
        _lock_bytes([_row(dependency, direct=True)]),
        artifact_root=wheelhouse,
        root_identity=root,
        expected="dependency_lock_wheelhouse_symlink_forbidden",
    )
