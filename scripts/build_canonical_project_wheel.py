#!/usr/bin/env python3
"""Build and replay one exact, reproducible canonical project wheel."""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any, Mapping, Sequence
import zipfile


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_canonical_verification_receipt import load_lock  # noqa: E402
from verify_bounded_planar_wheel_smoke import run_wheel_smoke  # noqa: E402


SCHEMA_VERSION = "canonical-project-wheel-contract.v1"
HASH_PREFIX = "sha256:"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1\n"
IDENTITY_MODULE = Path("src/structural_analysis/_canonical_build_identity.py")
REPLAY_CASE_IDS = ("member_feature", "prescribed_settlement")
REPLAY_HASH_FIELDS = (
    "result_hash",
    "engineering_result_hash",
    "checkpoint_sha256",
)


class CanonicalProjectWheelError(RuntimeError):
    """Raised when the canonical project-wheel contract cannot be proven."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return HASH_PREFIX + digest.hexdigest()


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return HASH_PREFIX + hashlib.sha256(encoded).hexdigest()


def _git_command(repo_root: Path, *arguments: str) -> list[str]:
    return [
        "git",
        "-c",
        f"safe.directory={repo_root.resolve()}",
        *arguments,
    ]


def _git_text(repo_root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        _git_command(repo_root, *arguments),
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise CanonicalProjectWheelError(
            "git_command_failed:" + " ".join(arguments) + ":" + completed.stderr.strip()
        )
    return completed.stdout.strip()


def _source_commit_timestamp(repo_root: Path, source_sha: str) -> int:
    value = _git_text(repo_root, "show", "-s", "--format=%ct", source_sha)
    if not value.isdigit() or int(value) <= 0:
        raise CanonicalProjectWheelError("source_commit_timestamp_invalid")
    return int(value)


def _validate_source_tree(repo_root: Path, source_sha: str) -> None:
    if not SHA_RE.fullmatch(source_sha):
        raise CanonicalProjectWheelError("source_commit_sha_invalid")
    if _git_text(repo_root, "rev-parse", "HEAD") != source_sha:
        raise CanonicalProjectWheelError("source_checkout_head_mismatch")
    tree = _git_text(repo_root, "ls-tree", "-r", source_sha)
    if any(line.startswith("160000 commit ") for line in tree.splitlines()):
        raise CanonicalProjectWheelError("source_tree_submodule_unsupported")


def _safe_extract_git_archive(
    repo_root: Path, source_sha: str, destination: Path
) -> None:
    archive_path = destination.parent / f"{destination.name}.tar"
    with archive_path.open("wb") as handle:
        completed = subprocess.run(
            _git_command(repo_root, "archive", "--format=tar", source_sha),
            cwd=repo_root,
            check=False,
            stdout=handle,
            stderr=subprocess.PIPE,
        )
    if completed.returncode != 0:
        raise CanonicalProjectWheelError(
            "git_archive_failed:"
            + completed.stderr.decode("utf-8", errors="replace").strip()
        )
    destination.mkdir(parents=True)
    with tarfile.open(archive_path, mode="r:") as archive:
        for member in archive.getmembers():
            member_path = Path(member.name)
            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or member.issym()
                or member.islnk()
            ):
                raise CanonicalProjectWheelError(
                    f"git_archive_member_unsafe:{member.name}"
                )
        archive.extractall(destination)  # noqa: S202 - members are checked above.
    archive_path.unlink()


def _prepare_source_export(
    repo_root: Path,
    source_sha: str,
    source_date_epoch: int,
    destination: Path,
) -> None:
    _safe_extract_git_archive(repo_root, source_sha, destination)
    required = (
        Path("pyproject.toml"),
        Path("README.md"),
        Path("src/structural_analysis/__init__.py"),
        Path("src/structural_analysis/generated_capabilities.py"),
    )
    for relative in required:
        if not (destination / relative).is_file():
            raise CanonicalProjectWheelError(
                f"canonical_wheel_source_missing:{relative.as_posix()}"
            )
    package_inputs = [destination / "README.md", destination / "pyproject.toml"]
    package_inputs.extend(
        path
        for path in (destination / "src/structural_analysis").rglob("*")
        if path.is_file()
    )
    for path in package_inputs:
        with path.open("rb") as handle:
            if handle.read(len(LFS_POINTER_HEADER)) == LFS_POINTER_HEADER:
                relative = path.relative_to(destination).as_posix()
                raise CanonicalProjectWheelError(
                    f"canonical_wheel_lfs_pointer_input:{relative}"
                )
    identity = destination / IDENTITY_MODULE
    identity.write_text(
        "# Generated only inside the exact canonical wheel build.\n"
        f'SOURCE_COMMIT_SHA = "{source_sha}"\n'
        f"SOURCE_DATE_EPOCH = {source_date_epoch}\n",
        encoding="utf-8",
    )


def validate_locked_wheelhouse(
    wheelhouse: Path,
    lock_path: Path,
) -> dict[str, dict[str, Any]]:
    locked = load_lock(lock_path)
    entries = sorted(wheelhouse.iterdir()) if wheelhouse.is_dir() else []
    unadmitted = [
        path.name
        for path in entries
        if path.is_symlink() or not path.is_file() or path.suffix != ".whl"
    ]
    if unadmitted:
        raise CanonicalProjectWheelError(
            f"locked_wheelhouse_unadmitted_entries:{unadmitted}"
        )
    wheels = entries
    by_hash: dict[str, list[Path]] = {}
    for wheel in wheels:
        by_hash.setdefault(_sha256(wheel).removeprefix(HASH_PREFIX), []).append(wheel)
    expected_hashes = {row["wheel_sha256"] for row in locked.values()}
    if set(by_hash) != expected_hashes:
        missing = sorted(expected_hashes - set(by_hash))
        extra = sorted(set(by_hash) - expected_hashes)
        raise CanonicalProjectWheelError(
            f"locked_wheelhouse_hash_set_mismatch:missing={missing}:extra={extra}"
        )
    manifest: dict[str, dict[str, Any]] = {}
    for package, contract in sorted(locked.items()):
        matches = by_hash[contract["wheel_sha256"]]
        if len(matches) != 1:
            raise CanonicalProjectWheelError(
                f"locked_wheelhouse_duplicate:{package}:{len(matches)}"
            )
        wheel = matches[0]
        manifest[package] = {
            "filename": wheel.name,
            "version": contract["version"],
            "sha256": HASH_PREFIX + contract["wheel_sha256"],
            "byte_length": wheel.stat().st_size,
        }
    return manifest


def _run_build(
    *,
    source_root: Path,
    wheel_dir: Path,
    wheelhouse: Path,
    source_date_epoch: int,
    environ: Mapping[str, str],
) -> Path:
    wheel_dir.mkdir(parents=True)
    environment = dict(environ)
    environment.update(
        {
            "SOURCE_DATE_EPOCH": str(source_date_epoch),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_CACHE_DIR": "1",
        }
    )
    command = [
        sys.executable,
        "-m",
        "pip",
        "wheel",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--no-deps",
        "--no-index",
        "--only-binary=:all:",
        "--find-links",
        str(wheelhouse),
        "--wheel-dir",
        str(wheel_dir),
        str(source_root),
    ]
    if "--no-build-isolation" in command:
        raise CanonicalProjectWheelError("pep517_build_isolation_disabled")
    completed = subprocess.run(
        command,
        cwd=source_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise CanonicalProjectWheelError(
            "canonical_wheel_build_failed:"
            + completed.stdout[-4000:]
            + completed.stderr[-4000:]
        )
    wheels = sorted(wheel_dir.glob("structural_analysis-*.whl"))
    if len(wheels) != 1:
        raise CanonicalProjectWheelError(
            f"canonical_wheel_artifact_count_invalid:{len(wheels)}"
        )
    return wheels[0]


def validate_wheel_record(
    wheel: Path,
    *,
    source_sha: str,
    source_date_epoch: int,
) -> dict[str, Any]:
    with zipfile.ZipFile(wheel) as archive:
        members = archive.infolist()
        names = [member.filename for member in members]
        if len(names) != len(set(names)):
            raise CanonicalProjectWheelError("wheel_archive_duplicate_member")
        for member in members:
            name = member.filename
            path = PurePosixPath(name)
            canonical_name = path.as_posix() + ("/" if member.is_dir() else "")
            unix_mode = (member.external_attr >> 16) & 0xFFFF
            file_type = stat.S_IFMT(unix_mode)
            if (
                not name
                or "\x00" in name
                or "\\" in name
                or canonical_name != name
                or path.is_absolute()
                or ".." in path.parts
                or re.match(r"^[A-Za-z]:", name)
                or (
                    file_type
                    and not stat.S_ISREG(unix_mode)
                    and not stat.S_ISDIR(unix_mode)
                )
            ):
                raise CanonicalProjectWheelError(f"wheel_archive_member_unsafe:{name}")
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise CanonicalProjectWheelError(
                f"wheel_record_count_invalid:{len(record_names)}"
            )
        record_name = record_names[0]
        record_bytes = archive.read(record_name)
        rows = list(csv.reader(io.StringIO(record_bytes.decode("utf-8"))))
        if not rows:
            raise CanonicalProjectWheelError("wheel_record_empty")
        recorded_paths: set[str] = set()
        for row in rows:
            if len(row) != 3:
                raise CanonicalProjectWheelError("wheel_record_row_invalid")
            path, encoded_hash, raw_size = row
            if path in recorded_paths:
                raise CanonicalProjectWheelError(f"wheel_record_duplicate:{path}")
            recorded_paths.add(path)
            if path == record_name:
                if encoded_hash or raw_size:
                    raise CanonicalProjectWheelError("wheel_record_self_hash_present")
                continue
            if path not in names or not encoded_hash.startswith("sha256="):
                raise CanonicalProjectWheelError(f"wheel_record_entry_invalid:{path}")
            payload = archive.read(path)
            if raw_size != str(len(payload)):
                raise CanonicalProjectWheelError(f"wheel_record_size_mismatch:{path}")
            expected = encoded_hash.split("=", 1)[1]
            observed = (
                base64.urlsafe_b64encode(hashlib.sha256(payload).digest())
                .decode("ascii")
                .rstrip("=")
            )
            if observed != expected:
                raise CanonicalProjectWheelError(f"wheel_record_hash_mismatch:{path}")
        archive_payload_paths = {name for name in names if not name.endswith("/")}
        if recorded_paths != archive_payload_paths:
            unrecorded = sorted(archive_payload_paths - recorded_paths)
            nonexistent = sorted(recorded_paths - archive_payload_paths)
            raise CanonicalProjectWheelError(
                "wheel_record_path_set_mismatch:"
                f"unrecorded={unrecorded}:nonexistent={nonexistent}"
            )
        identity_names = [
            name for name in names if name.endswith(IDENTITY_MODULE.as_posix()[4:])
        ]
        if len(identity_names) != 1 or identity_names[0] not in recorded_paths:
            raise CanonicalProjectWheelError("wheel_source_identity_missing")
        identity_text = archive.read(identity_names[0]).decode("utf-8")
        if f'SOURCE_COMMIT_SHA = "{source_sha}"' not in identity_text:
            raise CanonicalProjectWheelError("wheel_record_source_sha_unbound")
        if f"SOURCE_DATE_EPOCH = {source_date_epoch}" not in identity_text:
            raise CanonicalProjectWheelError("wheel_record_source_date_epoch_unbound")
    return {
        "path": record_name,
        "sha256": HASH_PREFIX + hashlib.sha256(record_bytes).hexdigest(),
        "entry_count": len(rows),
        "all_payload_entries_sha256_verified": True,
        "source_identity_member": identity_names[0],
    }


def _installed_replay_projection(
    replay: Mapping[str, Any], *, cases_key: str = "cases"
) -> dict[str, Any]:
    cases = replay.get(cases_key)
    if not isinstance(cases, Mapping) or set(cases) != set(REPLAY_CASE_IDS):
        raise CanonicalProjectWheelError("installed_wheel_replay_cases_missing")
    projected_cases: dict[str, dict[str, Any]] = {}
    for case_id in REPLAY_CASE_IDS:
        row = cases.get(case_id)
        if not isinstance(row, Mapping):
            raise CanonicalProjectWheelError(
                f"installed_wheel_replay_case_invalid:{case_id}"
            )
        projected_cases[case_id] = {}
        for key in REPLAY_HASH_FIELDS:
            value = row.get(key)
            if not isinstance(value, str) or not HASH_RE.fullmatch(value):
                raise CanonicalProjectWheelError(
                    f"installed_wheel_replay_case_hash_invalid:{case_id}:{key}"
                )
            projected_cases[case_id][key] = value
    return {
        "wheel_sha256": replay.get("wheel_sha256"),
        "installed_source_commit_sha": replay.get("installed_source_commit_sha"),
        "installed_source_date_epoch": replay.get("installed_source_date_epoch"),
        "cases": projected_cases,
    }


def build_contract(
    *,
    repo_root: Path,
    source_sha: str,
    source_date_epoch: int,
    dependency_lock: Path,
    wheelhouse: Path,
    output_wheel_dir: Path,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    wheelhouse = wheelhouse.resolve()
    output_wheel_dir = output_wheel_dir.resolve()
    environment = os.environ if environ is None else environ
    _validate_source_tree(repo_root, source_sha)
    expected_epoch = _source_commit_timestamp(repo_root, source_sha)
    if source_date_epoch != expected_epoch:
        raise CanonicalProjectWheelError("source_date_epoch_not_commit_timestamp")
    if environment.get("SOURCE_DATE_EPOCH") != str(source_date_epoch):
        raise CanonicalProjectWheelError("source_date_epoch_environment_mismatch")
    wheelhouse_manifest = validate_locked_wheelhouse(wheelhouse, dependency_lock)
    if output_wheel_dir.exists() and any(output_wheel_dir.glob("*.whl")):
        raise CanonicalProjectWheelError("canonical_output_wheel_dir_not_empty")
    output_wheel_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="canonical-project-wheel-") as raw:
        work = Path(raw)
        source_a = work / "source-a"
        source_b = work / "source-b"
        _prepare_source_export(repo_root, source_sha, source_date_epoch, source_a)
        _prepare_source_export(repo_root, source_sha, source_date_epoch, source_b)
        wheel_a = _run_build(
            source_root=source_a,
            wheel_dir=work / "wheel-a",
            wheelhouse=wheelhouse,
            source_date_epoch=source_date_epoch,
            environ=environment,
        )
        wheel_b = _run_build(
            source_root=source_b,
            wheel_dir=work / "wheel-b",
            wheelhouse=wheelhouse,
            source_date_epoch=source_date_epoch,
            environ=environment,
        )
        first_hash = _sha256(wheel_a)
        second_hash = _sha256(wheel_b)
        if wheel_a.name != wheel_b.name or first_hash != second_hash:
            raise CanonicalProjectWheelError("canonical_wheel_reproducibility_mismatch")
        if wheel_a.stat().st_size != wheel_b.stat().st_size:
            raise CanonicalProjectWheelError("canonical_wheel_byte_length_mismatch")
        wheel_record = validate_wheel_record(
            wheel_a,
            source_sha=source_sha,
            source_date_epoch=source_date_epoch,
        )
        retained_wheel = output_wheel_dir / wheel_a.name
        shutil.copyfile(wheel_a, retained_wheel)

    replay = run_wheel_smoke(
        repo_root=repo_root,
        wheel_path=retained_wheel,
        expected_wheel_sha256=first_hash,
        inherit_runtime=True,
        expected_source_sha=source_sha,
        expected_source_date_epoch=source_date_epoch,
    )
    if replay.get("contract_pass") is not True:
        raise CanonicalProjectWheelError("installed_wheel_replay_blocked")
    if replay.get("wheel_sha256") != first_hash:
        raise CanonicalProjectWheelError("installed_wheel_replay_hash_mismatch")
    repeat_replay = run_wheel_smoke(
        repo_root=repo_root,
        wheel_path=retained_wheel,
        expected_wheel_sha256=first_hash,
        inherit_runtime=True,
        expected_source_sha=source_sha,
        expected_source_date_epoch=source_date_epoch,
    )
    if repeat_replay.get("contract_pass") is not True:
        raise CanonicalProjectWheelError("installed_wheel_repeat_replay_blocked")
    first_projection = _installed_replay_projection(replay)
    repeat_projection = _installed_replay_projection(repeat_replay)
    if first_projection != repeat_projection:
        raise CanonicalProjectWheelError(
            "canonical_installed_wheel_replay_reproducibility_mismatch"
        )
    replay = {
        **replay,
        "execution_count": 2,
        "exact_repeat_match": True,
        "first_projection_sha256": _canonical_hash(first_projection),
        "repeat_projection_sha256": _canonical_hash(repeat_projection),
        "cases": first_projection["cases"],
        "repeat_cases": repeat_projection["cases"],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "source_commit_sha": source_sha,
        "source_date_epoch": source_date_epoch,
        "build": {
            "pep517_isolation": True,
            "dependency_index_access": False,
            "pip_cache": False,
            "source_export": "git-archive-exact-commit",
            "submodules_allowed": False,
            "lfs_pointer_package_inputs_allowed": False,
            "repeated_build_count": 2,
            "reproducible_wheel_bytes": True,
        },
        "dependency_wheelhouse": {
            "lock_path": dependency_lock.relative_to(repo_root).as_posix(),
            "package_count": len(wheelhouse_manifest),
            "manifest_sha256": _canonical_hash(wheelhouse_manifest),
            "all_locked_hashes_verified": True,
        },
        "wheel": {
            "filename": retained_wheel.name,
            "sha256": first_hash,
            "byte_length": retained_wheel.stat().st_size,
            "repeat_sha256": second_hash,
            "record": wheel_record,
        },
        "installed_replay": replay,
        "contract_pass": True,
        "violations": [],
        "claim_boundary": (
            "This receipt proves a repeatable exact-source canonical wheel build and "
            "installed-wheel replay for the two bounded planar fixtures. It does not "
            "grant release, design, or external-validation authority."
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    temporary.replace(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument(
        "--dependency-lock",
        type=Path,
        default=ROOT / "canonical/requirements-cp312-manylinux2014-x86_64.lock",
    )
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--write", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_contract(
        repo_root=args.repo_root,
        source_sha=args.source_sha,
        source_date_epoch=args.source_date_epoch,
        dependency_lock=args.dependency_lock.resolve(),
        wheelhouse=args.wheelhouse,
        output_wheel_dir=args.wheel_dir,
    )
    _write_json(args.write, payload)
    print(
        "canonical project wheel: pass | "
        f"sha256={payload['wheel']['sha256']} | "
        f"source={payload['source_commit_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
