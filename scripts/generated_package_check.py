#!/usr/bin/env python3
"""Shared clean-generation checks for generated external V&V packages.

A PR/Nightly checkout intentionally does not retain the large execution-package
folders.  When a package CLI is invoked with the default ``--check`` target and
that target is absent, validate the producer in an isolated repository-local
temporary directory instead.  Explicit ``--out-dir`` checks and checks against
an existing default target retain their original strict file-set semantics.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]


def run_package_cli(core: ModuleType) -> int:
    argv = sys.argv[1:]
    if "--check" not in argv or "--out-dir" in argv:
        return int(core.main())

    default_target = core.DEFAULT_OUT_DIR
    target = default_target if default_target.is_absolute() else ROOT / default_target
    if target.exists():
        return int(core.main())

    ci_root = ROOT / ".ci"
    ci_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f"{core.PACKAGE_ID}-generator-check-",
        dir=ci_root,
    ) as temporary:
        out_dir = Path(temporary) / "package"
        core.write_package(repo_root=ROOT, out_dir=out_dir)
        ok, message = core.check_package(repo_root=ROOT, out_dir=out_dir)
        if ok and hasattr(core, "validate_package_directory"):
            core.validate_package_directory(repo_root=ROOT, out_dir=out_dir)
        print(message)
        return 0 if ok else 1


def _refresh_receipt(script: str, source: Path, output: Path, reason: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, output)
    subprocess.run(
        [
            sys.executable,
            script,
            "--out",
            str(output),
            "--refresh-product-replay",
            "--reuse-reason",
            reason,
        ],
        cwd=ROOT,
        check=True,
    )


def run_matrix_cli(core: ModuleType) -> int:
    argv = sys.argv[1:]
    if "--check" not in argv or "--out" in argv:
        return int(core.main())

    default_target = core.DEFAULT_OUT
    target = default_target if default_target.is_absolute() else ROOT / default_target
    if target.exists():
        return int(core.main())

    ci_root = ROOT / ".ci"
    ci_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="bounded-planar-vv-matrix-generator-check-",
        dir=ci_root,
    ) as temporary:
        temp_root = Path(temporary)
        code_receipt_path = temp_root / "code-to-code-receipt.json"
        modal_receipt_path = temp_root / "modal-buckling-receipt.json"
        _refresh_receipt(
            "scripts/run_external_code_to_code_technical_receipt.py",
            ROOT / core.DEFAULT_CODE_RECEIPT,
            code_receipt_path,
            "Clean generator contract replay; external execution bytes reused without freshness credit.",
        )
        _refresh_receipt(
            "scripts/run_external_modal_buckling_technical_receipt.py",
            ROOT / core.DEFAULT_MODAL_RECEIPT,
            modal_receipt_path,
            "Clean generator contract replay; external execution bytes reused without freshness credit.",
        )

        package_modules = (
            ("linear", core.linear_package),
            ("negative", core.negative_package),
            ("scaling", core.scaling_package),
            ("modal-buckling", core.modal_buckling_package),
            ("nonlinear", core.nonlinear_package),
        )
        manifest_paths: dict[str, Path] = {}
        for label, package in package_modules:
            out_dir = temp_root / label
            package.write_package(repo_root=ROOT, out_dir=out_dir)
            ok, message = package.check_package(repo_root=ROOT, out_dir=out_dir)
            if not ok:
                print(message, file=sys.stderr)
                return 1
            if hasattr(package, "validate_package_directory"):
                package.validate_package_directory(repo_root=ROOT, out_dir=out_dir)
            manifest_paths[label] = out_dir / package.MANIFEST_NAME

        payload = core.build_bounded_planar_external_vv_matrix(
            repo_root=ROOT,
            code_receipt_path=code_receipt_path,
            modal_receipt_path=modal_receipt_path,
            linear_case_package_path=manifest_paths["linear"],
            negative_case_package_path=manifest_paths["negative"],
            scaling_case_package_path=manifest_paths["scaling"],
            modal_buckling_case_package_path=manifest_paths["modal-buckling"],
            nonlinear_case_package_path=manifest_paths["nonlinear"],
        )
        matrix_path = temp_root / "matrix.json"
        matrix_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        actual = json.loads(matrix_path.read_text(encoding="utf-8"))
        if actual != payload or payload.get("contract_pass") is not True:
            print("bounded_planar_external_vv_matrix_generator_mismatch", file=sys.stderr)
            return 1
        print("bounded_planar_external_vv_matrix_generator_consistent")
        return 0
