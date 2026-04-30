from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "check_git_remote_safety.py"
SPEC = importlib.util.spec_from_file_location("check_git_remote_safety", SCRIPT_PATH)
assert SPEC is not None
check_git_remote_safety = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(check_git_remote_safety)


def _write_remote_fixture(tmp_path: Path, text: str) -> Path:
    fixture = tmp_path / "remotes.txt"
    fixture.write_text(text, encoding="utf-8")
    return fixture


def _run_remote_check(remote_fixture: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--remote-file",
            str(remote_fixture),
            *args,
        ],
        cwd=str(REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def test_canonical_slug_supports_https_and_ssh_forms() -> None:
    assert (
        check_git_remote_safety.canonical_slug("https://github.com/betelgeuze-kang/Structural-Analysis.git")
        == "betelgeuze-kang/Structural-Analysis"
    )
    assert (
        check_git_remote_safety.canonical_slug("git@github.com:betelgeuze-kang/Structural-Analysis.git")
        == "betelgeuze-kang/Structural-Analysis"
    )
    assert (
        check_git_remote_safety.canonical_slug(
            "https://github.com/betelgeuze-kang/Structural-Analysis.git (push)"
        )
        == "betelgeuze-kang/Structural-Analysis"
    )


def test_expected_origin_passes(tmp_path: Path) -> None:
    fixture = _write_remote_fixture(
        tmp_path,
        "\n".join(
            [
                "origin\thttps://github.com/betelgeuze-kang/Structural-Analysis.git (fetch)",
                "origin\thttps://github.com/betelgeuze-kang/Structural-Analysis.git (push)",
            ]
        ),
    )

    proc = _run_remote_check(fixture, "--json")

    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert proc.stderr == ""


def test_wrong_origin_is_blocked_even_when_structural_remote_exists(tmp_path: Path) -> None:
    fixture = _write_remote_fixture(
        tmp_path,
        "\n".join(
            [
                "origin\thttps://github.com/betelgeuze-kang/Monet-wedding.git (fetch)",
                "origin\thttps://github.com/betelgeuze-kang/Monet-wedding.git (push)",
                "structural\tgit@github.com:betelgeuze-kang/Structural-Analysis.git (fetch)",
                "structural\tgit@github.com:betelgeuze-kang/Structural-Analysis.git (push)",
            ]
        ),
    )

    proc = _run_remote_check(fixture, "--json")

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert payload["errors"] == [
        (
            "forbidden remote target configured: origin -> "
            "https://github.com/betelgeuze-kang/Monet-wedding.git"
        ),
        (
            "protected remote `origin` must point to "
            "betelgeuze-kang/Structural-Analysis: "
            "https://github.com/betelgeuze-kang/Monet-wedding.git"
        ),
    ]


def test_missing_expected_remote_is_blocked(tmp_path: Path) -> None:
    fixture = _write_remote_fixture(
        tmp_path,
        "origin\thttps://github.com/example/other.git (fetch)\n",
    )

    proc = _run_remote_check(fixture, "--json")

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["errors"] == [
        "protected remote `origin` must point to betelgeuze-kang/Structural-Analysis: https://github.com/example/other.git",
        "expected remote target not configured: betelgeuze-kang/Structural-Analysis",
    ]
