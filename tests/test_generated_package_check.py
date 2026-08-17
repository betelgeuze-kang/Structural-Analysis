from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import scripts.generated_package_check as generated_check


def test_missing_default_package_check_rebuilds_in_temporary_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls: list[tuple[str, Path]] = []

    def write_package(*, repo_root: Path, out_dir: Path):
        calls.append(("write", out_dir))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "manifest.json").write_text("{}", encoding="utf-8")
        return {}

    def check_package(*, repo_root: Path, out_dir: Path):
        calls.append(("check", out_dir))
        return (out_dir / "manifest.json").is_file(), "generator_consistent"

    def validate_package_directory(*, repo_root: Path, out_dir: Path):
        calls.append(("validate", out_dir))
        return {}

    core = SimpleNamespace(
        PACKAGE_ID="example-package",
        DEFAULT_OUT_DIR=Path("artifacts/generated/example-package"),
        write_package=write_package,
        check_package=check_package,
        validate_package_directory=validate_package_directory,
        main=lambda: 99,
    )
    monkeypatch.setattr(generated_check, "ROOT", tmp_path)
    monkeypatch.setattr(generated_check.sys, "argv", ["package.py", "--check"])

    assert generated_check.run_package_cli(core) == 0
    assert [name for name, _ in calls] == ["write", "check", "validate"]
    assert not (tmp_path / "artifacts/generated/example-package").exists()


def test_explicit_output_check_preserves_original_cli_semantics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    core = SimpleNamespace(
        PACKAGE_ID="example-package",
        DEFAULT_OUT_DIR=Path("artifacts/generated/example-package"),
        main=lambda: 7,
    )
    monkeypatch.setattr(generated_check, "ROOT", tmp_path)
    monkeypatch.setattr(
        generated_check.sys,
        "argv",
        ["package.py", "--check", "--out-dir", "missing"],
    )

    assert generated_check.run_package_cli(core) == 7
