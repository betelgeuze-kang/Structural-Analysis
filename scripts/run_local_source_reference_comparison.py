"""Compare all existing cases using an explicitly local modified reference.

This local artifact profile is not an accepted replacement for the official
wheel receipt or independent operator evidence. It pins the previously audited
build packet; another build needs its own reviewed provenance profile.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter_ns
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_external_code_to_code_technical_receipt as base  # noqa: E402


PROFILE_ID = "local-opensees371-corot2d-rationalized.v1"
REFERENCE_NAME = "OpenSees 3.7.1 local corot2d-rationalized build"
SCHEMA_VERSION = "local-source-reference-comparison.v1"
PROFILE_PATH = Path(__file__).with_name("local_source_reference_profile.json")
INVENTORY_HASH = "bc7e9bf83cb1b7fa20d11b44b6fade66fad54c99efdbdf3113d69aa553585eaa"
BINARY_HASH = "c88c80e2bd2e8aa430cd831091dc8b1c3d22656d508f91d76cebdaf286b6326f"
AUTHORITY = {
    "official_wheel_execution": False,
    "reference_profile_adopted": False,
    "independent_operator_verification": False,
    "product_legal_approval": False,
    "commercial_redistribution_approved": False,
    "verification_hierarchy_credit": False,
    "release_readiness": False,
}


def _sha(path: Path) -> str:
    if (
        path.name == ".env"
        or path.name.startswith(".env.")
        or path.name.endswith(".env")
        or ".env." in path.name
    ):
        raise ValueError("environment_file_not_allowed")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def _save(path: Path, value: Any) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def validate_build_packet(root: Path) -> dict[str, Any]:
    inventory = Path(str(root) + ".inventory.json")
    if _sha(inventory) != INVENTORY_HASH:
        raise ValueError("source_build_inventory_not_reviewed")
    data = json.loads(inventory.read_bytes())
    if root.resolve() != Path(data["root"]):
        raise ValueError("source_build_local_dependency_location_changed")
    for row in data["entries"]:
        path = root / row["path"]
        if row["type"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != row["target"]:
                raise ValueError("source_build_link_changed:" + row["path"])
        elif (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size != row["bytes"]
            or _sha(path) != row["sha256"]
        ):
            raise ValueError("source_build_packet_changed:" + row["path"])
    if _sha(root / "modified/opensees.so") != BINARY_HASH:
        raise ValueError("source_build_binary_changed")
    dependencies = json.loads((root / "runtime-dependency-hashes.json").read_bytes())[
        "modified"
    ]
    for name, expected in dependencies.items():
        if _sha(Path(name)) != expected:
            raise ValueError("source_build_dependency_changed:" + name)
    return {
        "profile_id": PROFILE_ID,
        "upstream_revision": "fe578a5b51333e5489097f327f89d16de0797f56",
        "inventory_sha256": INVENTORY_HASH,
        "binary_sha256": BINARY_HASH,
        "patch_sha256": _sha(root / "arithmetic-diagnostic.patch"),
        "source_archive_sha256": _sha(root / "opensees-v3.7.1.tar.gz"),
        "dependency_hashes": dependencies,
        "fresh_build_performed": False,
        "build_origin": "previously_audited_local_modified_build",
    }


def _run_source_opensees(
    root: Path, output: Path, python: Path, profile: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    driver = base.OPENSEES_DRIVER.replace(
        "import openseespy.opensees as ops", "import opensees as ops"
    )
    if driver == base.OPENSEES_DRIVER:
        raise ValueError("source_driver_import_adapter_not_applied")
    environment = dict(os.environ)
    for key in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"):
        environment.pop(key, None)
    manifest = json.loads((root / "modified/manifest.json").read_bytes())
    environment["LD_LIBRARY_PATH"] = manifest["environment_overrides"][
        "LD_LIBRARY_PATH"
    ]
    bootstrap = (
        "import sys,hashlib,json\nfrom pathlib import Path\n"
        "root=Path(sys.argv[1]); binary=root/'opensees.so'\n"
        "def verify():\n"
        " assert not binary.is_symlink()\n"
        " assert hashlib.sha256(binary.read_bytes()).hexdigest()==sys.argv[2]\n"
        "verify()\nsys.path.insert(0,str(root))\nimport opensees\n"
        "assert Path(opensees.__file__).resolve()==binary\n"
        "exec(compile(sys.argv[3],'<local-source-reference>','exec'),{'__name__':'__main__'})\n"
        "verify()\nassert Path(opensees.__file__).resolve()==binary\n"
        "print('SOURCE_BUILD_BINDING='+json.dumps({'profile_id':sys.argv[4],"
        "'binary_sha256':sys.argv[2],'module_origin':'opensees.so'}))\n"
    )
    started = perf_counter_ns()
    with TemporaryDirectory(prefix="opensees-local-source-") as temporary:
        stage = Path(temporary)
        shutil.copyfile(root / "modified/opensees.so", stage / "opensees.so")
        completed = subprocess.run(
            [
                str(python.resolve()),
                "-I",
                "-S",
                "-B",
                "-c",
                bootstrap,
                str(stage),
                BINARY_HASH,
                driver,
                PROFILE_ID,
            ],
            cwd=stage,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    for name, text in (
        ("source-opensees.stdout", completed.stdout),
        ("source-opensees.stderr", completed.stderr),
    ):
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text)
    result = [
        json.loads(line.split("=", 1)[1])
        for line in completed.stdout.splitlines()
        if line.startswith("CODE_TO_CODE_JSON=")
    ]
    bindings = [
        json.loads(line.split("=", 1)[1])
        for line in completed.stdout.splitlines()
        if line.startswith("SOURCE_BUILD_BINDING=")
    ]
    expected = {
        "profile_id": PROFILE_ID,
        "binary_sha256": BINARY_HASH,
        "module_origin": "opensees.so",
    }
    if completed.returncode != 0 or len(result) != 1 or bindings != [expected]:
        raise ValueError("local_source_execution_failed_or_unbound")
    for name, expected_hash in profile["dependency_hashes"].items():
        if _sha(Path(name)) != expected_hash:
            raise ValueError("source_build_dependency_changed_during_run:" + name)
    if result[0].get("runtime_version") != "3.7.1":
        raise ValueError("local_source_runtime_version_changed")
    return result[0], {
        "return_code": completed.returncode,
        "stdout_sha256": base._text_hash(completed.stdout),
        "stderr_sha256": base._text_hash(completed.stderr),
        "driver_sha256": base._text_hash(driver),
        "parent_wall_ns": perf_counter_ns() - started,
        "binding": bindings[0],
    }


def _comparison_schema(repo: Path) -> dict[str, Any]:
    original = json.loads((repo / base.SCHEMA_PATH).read_bytes())
    choice = next(
        row
        for row in original["properties"]["comparisons"]["oneOf"]
        if row.get("minItems") == 12
    )
    schema = {**deepcopy(choice), "$defs": deepcopy(original["$defs"])}

    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: (
                    {"type": "integer"}
                    if key == "external_return_code"
                    else replace(item)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [replace(item) for item in value]
        return REFERENCE_NAME if value == "OpenSees 3.7.1" else value

    return replace(schema)


def validate_report(report: dict[str, Any], repo: Path) -> None:
    expected_keys = {
        "schema_version",
        "artifact_hash",
        "source_commit_sha",
        "source_checksums",
        "profile",
        "authority",
        "reference_assets",
        "executions",
        "comparisons",
        "comparison_pass",
        "raw_files",
        "parent_wall_ns",
    }
    if set(report) != expected_keys:
        raise ValueError("local_reference_shape_invalid")
    if report["schema_version"] != SCHEMA_VERSION or base._hash_value(
        report["authority"]
    ) != base._hash_value(AUTHORITY):
        raise ValueError("local_reference_authority_invalid")
    if base._hash_value(report["profile"]) != base._hash_value(
        json.loads(PROFILE_PATH.read_bytes())
    ):
        raise ValueError("local_reference_profile_invalid")
    expected_assets = {
        name: row["sha256"]
        for name, row in base.EXTERNAL_ASSET_POLICY.items()
        if name.endswith(".deb")
    }
    if report["reference_assets"] != expected_assets:
        raise ValueError("local_reference_assets_invalid")
    if report["artifact_hash"] != base._artifact_hash(report):
        raise ValueError("local_reference_hash_invalid")
    outputs = report["executions"]["opensees"]
    if (
        type(outputs["return_code"]) is not int
        or outputs["return_code"] != 0
        or outputs["binding"]
        != {
            "profile_id": PROFILE_ID,
            "binary_sha256": BINARY_HASH,
            "module_origin": "opensees.so",
        }
        or outputs["driver_sha256"]
        != base._text_hash(
            base.OPENSEES_DRIVER.replace(
                "import openseespy.opensees as ops", "import opensees as ops"
            )
        )
    ):
        raise ValueError("local_reference_execution_binding_invalid")
    if set(report["executions"]) != {
        "opensees",
        "calculix",
        "product_comparison_parent_wall_ns",
    }:
        raise ValueError("local_reference_execution_shape_invalid")
    for value in (
        outputs["parent_wall_ns"],
        report["executions"]["calculix"]["parent_wall_ns"],
        report["executions"]["product_comparison_parent_wall_ns"],
        report["parent_wall_ns"],
    ):
        if type(value) is not int or value <= 0:
            raise ValueError("local_reference_cost_invalid")
    raw = report["raw_files"]
    for name, digest in raw.items():
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None
        ):
            raise ValueError("local_reference_raw_file_invalid")
    for key, filename in (
        ("stdout_sha256", "source-opensees.stdout"),
        ("stderr_sha256", "source-opensees.stderr"),
    ):
        if outputs[key] != raw.get(filename):
            raise ValueError("local_reference_raw_binding_invalid")
    calculix = report["executions"]["calculix"]
    schema = json.loads((repo / base.SCHEMA_PATH).read_bytes())
    calc_schema = {**schema["$defs"]["calculixOutputs"], "$defs": schema["$defs"]}
    Draft202012Validator(calc_schema).validate(
        {
            k: v
            for k, v in calculix.items()
            if k not in ("parent_wall_ns", "binary_sha256")
        }
    )
    for prefix, stem in (("", "axial"), ("spatial_truss_", "spatial_truss")):
        for key, suffix in (
            ("stdout_sha256", "stdout"),
            ("stderr_sha256", "stderr"),
            ("input_deck_sha256", "inp"),
            ("dat_sha256", "dat"),
            ("frd_sha256", "frd"),
        ):
            if calculix[prefix + key] != raw.get("calculix/" + stem + "." + suffix):
                raise ValueError("local_reference_raw_binding_invalid")
    Draft202012Validator(_comparison_schema(repo)).validate(report["comparisons"])
    base.validate_external_comparison_cases(report["comparisons"])
    if report["comparison_pass"] is not all(
        row["contract_pass"] for row in report["comparisons"]
    ):
        raise ValueError("local_reference_pass_invalid")


def run_comparison(
    *,
    repo: Path,
    build_packet: Path,
    debs: list[Path],
    output: Path,
    python: Path = Path(sys.executable),
) -> dict[str, Any]:
    started = perf_counter_ns()
    profile = validate_build_packet(build_packet)
    if base._hash_value(profile) != base._hash_value(
        json.loads(PROFILE_PATH.read_bytes())
    ):
        raise ValueError("source_build_profile_not_reviewed")
    expected = {
        name: row
        for name, row in base.EXTERNAL_ASSET_POLICY.items()
        if name.endswith(".deb")
    }
    by_name = {path.name: path for path in debs}
    if len(debs) != len(by_name) or set(by_name) != set(expected):
        raise ValueError("calculix_asset_set_invalid")
    for name, path in by_name.items():
        if "sha256:" + _sha(path) != expected[name]["sha256"]:
            raise ValueError("calculix_asset_hash_invalid:" + name)
    output.mkdir(parents=True, exist_ok=False)
    source_paths = (
        *base.SOURCE_PATHS,
        Path("scripts/run_local_source_reference_comparison.py"),
        Path("scripts/local_source_reference_profile.json"),
        Path("tests/test_local_source_reference_comparison.py"),
    )
    sources = base.input_checksums(
        base.expand_local_python_sources(source_paths, repo_root=repo), repo_root=repo
    )
    _save(
        output / "protocol.json",
        {
            "source_commit_sha": base.git_head(repo),
            "source_checksums": sources,
            "profile": profile,
            "authority": AUTHORITY,
            "scope": "all 12 existing cases; unchanged metrics/tolerances; fresh product and external execution",
            "shared_build_validation_wall_ns": perf_counter_ns() - started,
        },
    )
    opensees, opensees_outputs = _run_source_opensees(
        build_packet, output, python, profile
    )
    _save(output / "source-opensees-result.json", opensees)
    with TemporaryDirectory(prefix="calculix-local-reference-") as temporary:
        stage = Path(temporary)
        for path in by_name.values():
            subprocess.run(
                ["dpkg-deb", "-x", str(path), str(stage)],
                check=True,
                capture_output=True,
            )
        libraries = stage / "usr/lib/x86_64-linux-gnu"
        for name, checksum in profile["dependency_hashes"].items():
            if Path(name).name in ("libblas.so.3", "liblapack.so.3"):
                if _sha(Path(name)) != checksum:
                    raise ValueError("calculix_blas_dependency_changed")
                shutil.copyfile(name, libraries / Path(name).name)
        environment = dict(os.environ)
        for key in ("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"):
            environment.pop(key, None)
        tick = perf_counter_ns()
        calculix, calculix_outputs = base._run_calculix(
            binary=stage / "usr/bin/ccx",
            library_dir=libraries,
            raw_output_dir=output / "calculix",
            runtime_environment=environment,
        )
        calculix_outputs["parent_wall_ns"] = perf_counter_ns() - tick
        calculix_outputs["binary_sha256"] = "sha256:" + _sha(stage / "usr/bin/ccx")
    _save(output / "calculix-result.json", calculix)
    tick = perf_counter_ns()
    cases = base.calculate_external_reference_comparisons(
        repo_root=repo,
        opensees=opensees,
        opensees_outputs=opensees_outputs,
        calculix=calculix,
        calculix_outputs=calculix_outputs,
        opensees_reference_name=REFERENCE_NAME,
    )
    product_wall_ns = perf_counter_ns() - tick
    current = base.input_checksums(
        base.expand_local_python_sources(source_paths, repo_root=repo), repo_root=repo
    )
    if sources != current:
        raise ValueError("local_reference_product_source_changed")
    report = {
        "schema_version": SCHEMA_VERSION,
        "artifact_hash": "sha256:" + "0" * 64,
        "source_commit_sha": base.git_head(repo),
        "source_checksums": sources,
        "profile": profile,
        "authority": dict(AUTHORITY),
        "reference_assets": {
            name: expected[name]["sha256"] for name in sorted(expected)
        },
        "executions": {
            "opensees": opensees_outputs,
            "calculix": calculix_outputs,
            "product_comparison_parent_wall_ns": product_wall_ns,
        },
        "comparisons": cases,
        "comparison_pass": all(row["contract_pass"] for row in cases),
        "raw_files": {
            str(path.relative_to(output)): "sha256:" + _sha(path)
            for path in sorted(output.rglob("*"))
            if path.is_file()
        },
        "parent_wall_ns": perf_counter_ns() - started,
    }
    report["artifact_hash"] = base._artifact_hash(report)
    validate_report(report, repo)
    _save(output / "comparison.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--build-packet", type=Path, required=True)
    parser.add_argument("--deb", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run_comparison(
        repo=args.repo_root.resolve(),
        build_packet=args.build_packet.resolve(),
        debs=[p.resolve() for p in args.deb],
        output=args.output_dir.resolve(),
    )
    print(
        json.dumps(
            {
                "comparison_pass": result["comparison_pass"],
                "case_count": len(result["comparisons"]),
                "authority": result["authority"],
            },
            indent=2,
        )
    )
    raise SystemExit(0 if result["comparison_pass"] else 1)
