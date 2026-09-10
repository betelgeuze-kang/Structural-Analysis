"""Bind local reference execution to the two reviewed OpenSees wheels.

Isolation here prevents accidental import/path drift. It is not an operating
system sandbox or independent operator attestation.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
import zipfile


WHEEL_HASHES = {
    "openseespy-3.7.1.2-py3-none-any.whl": (
        "sha256:1f16bc7466c252e432ac2ca69f4e9ca08f6c053e8b977157c6dccba3dfa19e65"
    ),
    "openseespylinux-3.7.1.2-py3-none-any.whl": (
        "sha256:63d919a3ed06bd00e7e09ce55afac6394ad82fd89180e046070b19d68717308a"
    ),
}
MEMBERS_PATH = Path(__file__).with_name("pinned_opensees_wheel_members.json")
MODULE_PATHS = {
    "openseespy": "openseespy/__init__.py",
    "openseespy.opensees": "openseespy/opensees/__init__.py",
    "openseespylinux": "openseespylinux/__init__.py",
    "openseespylinux.opensees": "openseespylinux/opensees.so",
}
BINDING_PREFIX = "OPENSEES_WHEEL_BINDING="


class PinnedOpenSeesRuntimeError(ValueError):
    """The supplied or actually loaded runtime is not the pinned payload."""

    def __init__(
        self,
        message: str,
        *,
        completed: subprocess.CompletedProcess[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.completed = completed


def _hash_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _hash_value(value: Any) -> str:
    return _hash_bytes(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return "sha256:" + digest.hexdigest()


def _members() -> dict[str, dict[str, Any]]:
    return json.loads(MEMBERS_PATH.read_bytes())


def expected_binding() -> dict[str, Any]:
    members = _members()
    value = {
        "schema_version": "pinned-opensees-wheel-execution.v1",
        "wheel_hashes": dict(WHEEL_HASHES),
        "member_manifest_hash": _hash_value(members),
        "member_count": len(members),
        "module_origins": {
            name: {"path": path, "sha256": members[path]["sha256"]}
            for name, path in MODULE_PATHS.items()
        },
        "isolated_interpreter": True,
        "private_wheel_extraction": True,
        "members_verified_before_and_after": True,
    }
    return {**value, "binding_hash": _hash_value(value)}


def validate_binding(value: Any) -> None:
    try:
        valid = isinstance(value, dict) and _hash_value(value) == _hash_value(
            expected_binding()
        )
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise PinnedOpenSeesRuntimeError("opensees_wheel_binding_invalid")


def _verify_supplied_members(root: Path, members: dict[str, dict[str, Any]]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise PinnedOpenSeesRuntimeError("opensees_runtime_root_invalid")
    for name, row in members.items():
        # pip may regenerate dist-info/RECORD. Runtime code/data must be exact;
        # metadata is taken from the verified archive in the private execution.
        if ".dist-info/" in name:
            continue
        path = root / name
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise PinnedOpenSeesRuntimeError("opensees_runtime_symlink_invalid:" + name)
        if (
            not path.is_file()
            or path.stat().st_size != row["bytes"]
            or _hash_file(path) != row["sha256"]
        ):
            raise PinnedOpenSeesRuntimeError("opensees_runtime_member_mismatch:" + name)


_BOOTSTRAP = r"""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
members = json.loads(sys.argv[2])
module_paths = json.loads(sys.argv[3])
driver = sys.argv[4]
binding = json.loads(sys.argv[5])

def verify_members():
    for name, row in members.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('opensees_staged_member_invalid:' + name)
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            while data := stream.read(1024 * 1024):
                digest.update(data)
        if path.stat().st_size != row['bytes'] or 'sha256:' + digest.hexdigest() != row['sha256']:
            raise RuntimeError('opensees_staged_member_mismatch:' + name)

def verify_origins():
    for name, relative in module_paths.items():
        module = sys.modules.get(name)
        if module is None or Path(module.__file__).resolve() != root / relative:
            raise RuntimeError('opensees_loaded_origin_invalid:' + name)

verify_members()
sys.path.insert(0, str(root))
import openseespy.opensees
verify_origins()
exec(compile(driver, '<pinned-opensees-driver>', 'exec'), {'__name__': '__main__'})
verify_origins()
verify_members()
print('OPENSEES_WHEEL_BINDING=' + json.dumps(binding, sort_keys=True, allow_nan=False))
"""


def execute_pinned_opensees(
    *,
    python_executable: Path,
    supplied_runtime_root: Path,
    wheels: list[Path],
    driver: str,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    """Reject code drift before launching; execute only verified wheel members."""
    by_name = {p.name: p for p in wheels}
    if len(by_name) != len(wheels) or set(by_name) != set(WHEEL_HASHES):
        raise PinnedOpenSeesRuntimeError("opensees_wheel_set_invalid")
    for name, path in by_name.items():
        if not path.is_file() or _hash_file(path) != WHEEL_HASHES[name]:
            raise PinnedOpenSeesRuntimeError("opensees_wheel_hash_invalid:" + name)
    members = _members()
    _verify_supplied_members(supplied_runtime_root, members)
    binding = expected_binding()
    environment = dict(os.environ)
    for key in ("LD_PRELOAD", "LD_LIBRARY_PATH", "LD_AUDIT"):
        environment.pop(key, None)
    # Import path and site initialization are disabled by -I -S. Extract from
    # verified archives, so extra modules, caches or metadata at the supplied
    # path cannot become executable input to this reference run.
    with TemporaryDirectory(prefix="opensees-pinned-runtime-") as temporary:
        stage = Path(temporary)
        for wheel_name, wheel in by_name.items():
            with zipfile.ZipFile(wheel) as archive:
                expected = {
                    name for name, row in members.items() if row["wheel"] == wheel_name
                }
                names = archive.namelist()
                if len(names) != len(set(names)) or set(names) != expected:
                    raise PinnedOpenSeesRuntimeError("opensees_wheel_members_invalid")
                for name in names:
                    data = archive.read(name)
                    row = members[name]
                    if len(data) != row["bytes"] or _hash_bytes(data) != row["sha256"]:
                        raise PinnedOpenSeesRuntimeError(
                            "opensees_wheel_member_hash_invalid"
                        )
                    destination = stage / name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
        completed = subprocess.run(
            [
                str(python_executable.resolve()),
                "-I",
                "-S",
                "-B",
                "-c",
                _BOOTSTRAP,
                str(stage),
                json.dumps(members),
                json.dumps(MODULE_PATHS),
                driver,
                json.dumps(binding),
            ],
            cwd=stage,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        rows = [
            line[len(BINDING_PREFIX) :]
            for line in completed.stdout.splitlines()
            if line.startswith(BINDING_PREFIX)
        ]
        if completed.returncode != 0 or len(rows) != 1:
            raise PinnedOpenSeesRuntimeError(
                "opensees_bound_execution_failed", completed=completed
            )
        try:
            actual = json.loads(rows[0])
        except json.JSONDecodeError as exc:
            raise PinnedOpenSeesRuntimeError("opensees_wheel_binding_invalid") from exc
        validate_binding(actual)
        _verify_supplied_members(stage, members)
    return completed, actual
