"""Run the CI wrapper with real APT parsing in an unprivileged temporary tree."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts/with-ubuntu-apt-sources.sh"


def _apt_tree(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    apt_root = tmp_path / "apt"
    (apt_root / "apt.conf.d").mkdir(parents=True)
    (apt_root / "sources.list.d").mkdir()
    (apt_root / "sources.list.d/ubuntu.sources").write_text(
        "Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\n"
        "Suites: noble noble-updates\nComponents: main universe\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    (apt_root / "sources.list.d/google-chrome.list").write_text(
        "deb https://dl.google.com/linux/chrome-stable/deb stable main\n"
    )
    (apt_root / "sources.list").write_text(
        "deb https://unrelated.invalid/deb stable main\n"
    )
    (apt_root / "apt.conf.d/20-original").write_text('Acquire::Retries "0";\n')
    loader = tmp_path / "apt-loader.conf"
    loader.write_text(f'Dir::Etc "{apt_root}";\n')
    environment = dict(os.environ, APT_CONFIG=str(loader))
    return apt_root, environment


def _run(apt_root: Path, environment: dict[str, str], command: list[str]):
    # Substitute privilege elevation only. All filesystem commands, traps, APT
    # configuration parsing and command argument forwarding execute unchanged.
    return subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; sudo() { "$@"; }; with_ubuntu_apt_sources "$@"',
            "test-wrapper",
            str(WRAPPER),
            str(apt_root),
            *command,
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )


@pytest.mark.parametrize("return_code", [0, 37])
def test_command_status_arguments_and_cleanup_are_preserved(tmp_path, return_code):
    apt_root, environment = _apt_tree(tmp_path)
    before = {
        p.relative_to(apt_root): p.read_bytes()
        for p in apt_root.rglob("*")
        if p.is_file()
    }
    completed = _run(
        apt_root,
        environment,
        [
            "bash",
            "-c",
            'printf "%s\\n" "$2"; test "$(find "$1/apt.conf.d" -name "zzzz-structural-browser-*" | wc -l)" = 1; exit "$3"',
            "child",
            str(apt_root),
            "space ; $(no-command) literal",
            str(return_code),
        ],
    )
    assert completed.returncode == return_code, completed.stderr
    assert completed.stdout == "space ; $(no-command) literal\n"
    assert before == {
        p.relative_to(apt_root): p.read_bytes()
        for p in apt_root.rglob("*")
        if p.is_file()
    }


def test_real_apt_uses_only_original_ubuntu_sources_then_restores(tmp_path):
    if not shutil.which("apt-get") or not shutil.which("apt-config"):
        pytest.skip("APT is required for the Linux configuration integration test")
    apt_root, environment = _apt_tree(tmp_path)
    apt_command = [
        "apt-get",
        "-o",
        f"Dir::State={tmp_path / 'state'}",
        "-o",
        "Debug::NoLocking=true",
        "--print-uris",
        "update",
    ]
    before = subprocess.run(
        apt_command, env=environment, capture_output=True, text=True, check=True
    )
    assert "dl.google.com" in before.stdout and "unrelated.invalid" in before.stdout
    restricted = _run(apt_root, environment, apt_command)
    assert restricted.returncode == 0, restricted.stderr
    assert "archive.ubuntu.com/ubuntu" in restricted.stdout
    assert "noble-updates" in restricted.stdout
    assert "dl.google.com" not in restricted.stdout
    assert "unrelated.invalid" not in restricted.stdout
    config = _run(apt_root, environment, ["apt-config", "dump"])
    assert config.returncode == 0, config.stderr
    assert (
        f'Dir::Etc::sourcelist "{apt_root}/sources.list.d/ubuntu.sources";'
        in config.stdout
    )
    assert 'Dir::Etc::sourceparts "-";' in config.stdout
    assert 'APT::Get::AllowUnauthenticated "true"' not in config.stdout
    assert 'Acquire::AllowInsecureRepositories "true"' not in config.stdout
    after = subprocess.run(
        apt_command, env=environment, capture_output=True, text=True, check=True
    )
    assert after.stdout == before.stdout


def test_missing_ubuntu_sources_does_not_run_command_or_modify_config(tmp_path):
    apt_root, environment = _apt_tree(tmp_path)
    (apt_root / "sources.list.d/ubuntu.sources").unlink()
    marker = tmp_path / "unexpected"
    completed = _run(apt_root, environment, ["touch", str(marker)])
    assert completed.returncode == 2
    assert not marker.exists()
    assert not list((apt_root / "apt.conf.d").glob("zzzz-structural-browser-*"))


def test_setup_failure_cleans_only_its_own_override(tmp_path):
    apt_root, environment = _apt_tree(tmp_path)
    marker = tmp_path / "unexpected"
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; shift; sudo() { if [[ "$1" == tee ]]; then return 41; fi; "$@"; }; with_ubuntu_apt_sources "$@"',
            "test-wrapper",
            str(WRAPPER),
            str(apt_root),
            "touch",
            str(marker),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 41
    assert not marker.exists()
    assert not list((apt_root / "apt.conf.d").glob("zzzz-structural-browser-*"))
    assert (
        apt_root / "apt.conf.d/20-original"
    ).read_text() == 'Acquire::Retries "0";\n'


def test_termination_cleans_temporary_override(tmp_path):
    apt_root, environment = _apt_tree(tmp_path)
    completed = _run(apt_root, environment, ["bash", "-c", 'kill -TERM "$PPID"'])
    assert completed.returncode == 143, completed.stderr
    assert not list((apt_root / "apt.conf.d").glob("zzzz-structural-browser-*"))
    assert (apt_root / "apt.conf.d/20-original").is_file()


def test_cli_rejects_local_workstations_before_any_elevation(tmp_path):
    environment = dict(
        os.environ,
        GITHUB_ACTIONS="false",
        RUNNER_ENVIRONMENT="self-hosted",
        RUNNER_OS="Linux",
    )
    marker = tmp_path / "unexpected"
    completed = subprocess.run(
        ["bash", str(WRAPPER), "touch", str(marker)],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "GitHub-hosted" in completed.stderr
    assert not marker.exists()


def test_all_browser_dependency_workflows_use_wrapper_and_watch_it():
    count = 0
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
        value = yaml.load(workflow.read_text(), Loader=yaml.BaseLoader)
        for job in value.get("jobs", {}).values():
            for step in job.get("steps", []):
                for line in step.get("run", "").splitlines():
                    if "install --with-deps chromium" not in line:
                        continue
                    count += 1
                    assert "bash scripts/with-ubuntu-apt-sources.sh " in line, workflow
                    assert job["runs-on"] == "ubuntu-24.04", workflow
                    for event in value["on"].values():
                        if isinstance(event, dict) and "paths" in event:
                            assert (
                                "scripts/with-ubuntu-apt-sources.sh" in event["paths"]
                            ), workflow
    assert count == 6
