#!/usr/bin/env python3
"""Run one bounded-planar family inside the locked no-network container."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import NoReturn


REPO_ROOT = Path("/workspace")
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import bounded_planar_runtime_lock as runtime_lock  # noqa: E402


class IsolatedFamilyError(RuntimeError):
    """Fail-closed isolated runner error."""


def _fail(code: str) -> NoReturn:
    raise IsolatedFamilyError(code)


def _load(path: Path) -> dict:
    payload = runtime_lock.load_preexecution_lock(path)
    if not isinstance(payload, dict):
        _fail("isolated_runtime_lock_invalid")
    return payload


def _network_default_route_present() -> bool:
    route_path = Path("/proc/net/route")
    if not route_path.is_file():
        return True
    for line in route_path.read_text(encoding="utf-8").splitlines()[1:]:
        columns = line.split()
        if len(columns) >= 2 and columns[1] == "00000000":
            return True
    return False


def _run(command: list[str], *, env: dict[str, str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        _fail("isolated_external_case_failed")


def _install_opensees(asset_dir: Path, scratch: Path) -> tuple[Path, Path]:
    target = scratch / "opensees-runtime"
    target.mkdir()
    wheels = [
        asset_dir / runtime_lock.EXTERNAL_ASSET_POLICY[asset_id]["filename"]
        for asset_id in runtime_lock.OPENSEES_ASSET_IDS
    ]
    environment = dict(os.environ)
    environment["PIP_NO_INDEX"] = "1"
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-deps",
            "--target",
            str(target),
            *(str(path) for path in wheels),
        ],
        env=environment,
        cwd=scratch,
    )
    return target, target / "openseespylinux/lib"


def _extract_calculix(asset_dir: Path, scratch: Path) -> tuple[Path, Path]:
    root = scratch / "calculix-root"
    root.mkdir()
    environment = dict(os.environ)
    for asset_id in ("calculix-ccx", "libarpack2", "libspooles2.2"):
        package = asset_dir / runtime_lock.EXTERNAL_ASSET_POLICY[asset_id]["filename"]
        _run(
            ["dpkg-deb", "--extract", str(package), str(root)],
            env=environment,
            cwd=scratch,
        )
    return root / "usr/bin/ccx", root / "usr/lib/x86_64-linux-gnu"


def _commands(
    *, family_id: str, package_dir: Path, result_dir: Path, calculix_binary: Path
) -> list[list[str]]:
    python = sys.executable
    if family_id == "linear":
        ids = ("bounded_planar_linear_portal", "bounded_planar_linear_multistory")
        return [
            [
                python,
                str(package_dir / f"opensees/{case_id}.py"),
                str(result_dir / f"{case_id}.json"),
            ]
            for case_id in ids
        ]
    if family_id == "negative":
        ids = (
            "bounded_planar_negative_mechanism",
            "bounded_planar_negative_singular",
            "bounded_planar_negative_invalid_geometry",
        )
        return [
            [
                python,
                str(package_dir / f"opensees/{case_id}.py"),
                str(result_dir / f"{case_id}.json"),
            ]
            for case_id in ids
        ]
    if family_id == "scaling":
        ids = (
            "bounded_planar_scaling_unit_invariance",
            "bounded_planar_scaling_characteristic_length_invariance",
        )
        return [
            [
                python,
                str(package_dir / f"opensees/{case_id}.py"),
                str(result_dir / f"{case_id}.json"),
            ]
            for case_id in ids
        ]
    if family_id == "nonlinear_material_recovery":
        ids = (
            "bounded_planar_p_delta",
            "bounded_planar_snap_through",
            "bounded_planar_steel_yield",
            "bounded_planar_rc_fiber",
            "bounded_planar_section_recovery",
            "bounded_planar_fiber_recovery",
        )
        return [
            [
                python,
                str(package_dir / "runner/run_case.py"),
                "--case-id",
                case_id,
                "--model",
                str(package_dir / f"models/{case_id}.case.json"),
                "--out",
                str(result_dir / f"{case_id}.json"),
            ]
            for case_id in ids
        ]
    if family_id == "modal_buckling":
        commands = []
        for case_id in (
            "bounded_planar_modal_rigid_mode",
            "bounded_planar_modal_repeated_mode",
        ):
            commands.append(
                [
                    python,
                    str(package_dir / "runner/run_case.py"),
                    "--case-id",
                    case_id,
                    "--model",
                    str(package_dir / f"models/{case_id}.model.json"),
                    "--out",
                    str(result_dir / f"{case_id}.json"),
                ]
            )
        case_id = "bounded_planar_buckling_portal"
        commands.append(
            [
                python,
                str(package_dir / "runner/run_case.py"),
                "--case-id",
                case_id,
                "--model",
                str(package_dir / f"models/{case_id}.model.json"),
                "--out",
                str(result_dir / f"{case_id}.json"),
                "--calculix-binary",
                str(calculix_binary),
            ]
        )
        return commands
    _fail("isolated_family_invalid")


def run_family(
    *,
    family_id: str,
    package_dir: Path,
    result_dir: Path,
    asset_dir: Path,
    runtime_manifest: Path,
    derived_image_id: str,
) -> None:
    if not (os.statvfs(REPO_ROOT).f_flag & os.ST_RDONLY):
        _fail("isolated_repository_mount_not_read_only")
    if _network_default_route_present():
        _fail("isolated_runtime_network_enabled")
    payload = runtime_lock.validate_preexecution_lock_payload(
        _load(runtime_manifest),
        repo_root=REPO_ROOT,
        family_id=family_id,
        asset_dir=asset_dir,
    )
    if payload["container_image"]["derived_image_id"] != derived_image_id:
        _fail("isolated_runtime_image_id_mismatch")
    if not package_dir.is_dir() or not result_dir.is_dir():
        _fail("isolated_execution_directory_invalid")
    scratch = Path("/tmp/bounded-planar-supplemental")
    scratch.mkdir()
    opensees_runtime, opensees_library = _install_opensees(asset_dir, scratch)
    calculix_binary = Path("/nonexistent/ccx")
    library_paths = [opensees_library]
    if family_id == "modal_buckling":
        calculix_binary, calculix_library = _extract_calculix(asset_dir, scratch)
        library_paths.append(calculix_library)
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(opensees_runtime)
    environment["LD_LIBRARY_PATH"] = ":".join(str(path) for path in library_paths)
    for command in _commands(
        family_id=family_id,
        package_dir=package_dir,
        result_dir=result_dir,
        calculix_binary=calculix_binary,
    ):
        _run(command, env=environment, cwd=package_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family-id", choices=sorted(runtime_lock.FAMILY_ASSET_IDS), required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--result-dir", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--derived-image-id", required=True)
    args = parser.parse_args()
    try:
        run_family(
            family_id=args.family_id,
            package_dir=args.package_dir,
            result_dir=args.result_dir,
            asset_dir=args.asset_dir,
            runtime_manifest=args.runtime_manifest,
            derived_image_id=args.derived_image_id,
        )
    except (IsolatedFamilyError, runtime_lock.RuntimeLockError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
