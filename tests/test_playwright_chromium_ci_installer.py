from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/install-playwright-chromium-ci.sh"
WORKFLOW = ROOT / ".github/workflows/frontend-web-ci.yml"


def _harness(tmp_path: Path, phase: str = "install-deps", mode: str = "success"):
    apt = tmp_path / "apt"
    (apt / "sources.list.d").mkdir(parents=True)
    (apt / "apt.conf.d").mkdir()
    sources = apt / "sources.list.d/ubuntu.sources"
    sources.write_text(
        "Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    existing = apt / "apt.conf.d/99-existing"
    existing.write_text('APT::Keep-Downloaded-Packages "false";\n')
    tools = tmp_path / "tools"
    tools.mkdir()
    sudo_log = tmp_path / "sudo.jsonl"
    sudo = tools / "sudo"
    sudo.write_text(
        "#!/usr/bin/python3\n"
        "import json, os, sys\n"
        f"with open({str(sudo_log)!r}, 'a') as log: log.write(json.dumps(sys.argv[1:])+'\\n')\n"
        "assert sys.argv[1:3] == ['-n', '--']\n"
        "os.execvp(sys.argv[3], sys.argv[3:])\n"
    )
    sudo.chmod(0o755)
    node = tools / "node"
    calls = tmp_path / "phases.jsonl"
    pids = tmp_path / "pids.json"
    node.write_text(
        "#!/usr/bin/python3\n"
        "import json, os, pathlib, signal, subprocess, sys, time\n"
        "phase = sys.argv[2]\n"
        "print('mock-installer-output ' + phase, flush=True)\n"
        f"apt = pathlib.Path({str(apt)!r})\n"
        "config = next((apt/'apt.conf.d').glob('zzzz-structural-browser-*')).read_text()\n"
        f"with open({str(calls)!r}, 'a') as log:\n"
        " log.write(json.dumps({'phase':phase, 'env':dict(os.environ), 'config':config})+'\\n')\n"
        f"if phase == {phase!r} and {mode!r} != 'success':\n"
        f" if {mode!r}.startswith('exit:'): sys.exit(int({mode!r}.split(':')[1]))\n"
        f" if {mode!r} == 'change_source':\n"
        "  with (apt/'sources.list.d/ubuntu.sources').open('a') as source: source.write('# changed by fixture\\n')\n"
        "  sys.exit(0)\n"
        f" if {mode!r} == 'ignore_term': signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f" child_code = 'import signal,time; ' + ('signal.signal(signal.SIGTERM,signal.SIG_IGN); ' if {mode!r} == 'ignore_term' else '') + 'time.sleep(60)'\n"
        " child = subprocess.Popen([sys.executable, '-c', child_code])\n"
        f" pathlib.Path({str(pids)!r}).write_text(json.dumps([os.getpid(), child.pid]))\n"
        " while True: time.sleep(1)\n"
    )
    node.chmod(0o755)
    cli = tmp_path / "audited-cli.js"
    cli.write_text("// executable mock Node handles this fixture\n")
    home = tmp_path / "repository-home"
    temp = tmp_path / "repository-tmp"
    home.mkdir()
    temp.mkdir()
    return {
        "apt": apt,
        "sources": sources,
        "existing": existing,
        "tools": tools,
        "node": node,
        "cli": cli,
        "home": home,
        "temp": temp,
        "diagnostic": tmp_path / "diagnostics/install.log",
        "calls": calls,
        "pids": pids,
        "sudo_log": sudo_log,
    }


def _run(harness):
    env = dict(os.environ)
    env["PATH"] = f"{harness['tools']}:/usr/bin:/bin"
    command = [
        "bash",
        "-c",
        'source "$1"; shift; install_playwright_chromium_ci "$@"',
        "installer-test",
        str(INSTALLER),
        *(
            str(harness[k])
            for k in ["apt", "node", "cli", "home", "temp", "diagnostic"]
        ),
        "1s",
        "1s",
        "1s",
    ]
    return subprocess.run(command, env=env, capture_output=True, text=True, timeout=10)


def _calls(harness):
    return [json.loads(line) for line in harness["calls"].read_text().splitlines()]


def _assert_cleanup(harness):
    assert [p.name for p in (harness["apt"] / "apt.conf.d").iterdir()] == [
        "99-existing"
    ]
    assert list(harness["temp"].iterdir()) == []
    assert harness["sources"].read_text() == (
        "Types: deb\nURIs: https://archive.ubuntu.com/ubuntu\n"
        "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    )
    assert harness["existing"].read_text() == (
        'APT::Keep-Downloaded-Packages "false";\n'
    )


def _running(pid: int) -> bool:
    try:
        # A terminated orphan may remain a zombie until the host reaps it.
        return Path(f"/proc/{pid}/stat").read_text().split(") ", 1)[1][0] != "Z"
    except FileNotFoundError:
        return False


def test_installation_phases_preserve_source_bytes_and_isolate_privileges(tmp_path):
    harness = _harness(tmp_path)
    result = _run(harness)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(harness)
    assert [c["phase"] for c in calls] == ["install-deps", "install"]
    for call in calls:
        assert set(call["env"]) == {"PATH", "HOME", "TMPDIR", "LANG", "LC_ALL"}
        assert 'Acquire::http::Timeout "30";' in call["config"]
        assert 'Acquire::https::Timeout "30";' in call["config"]
        assert 'Acquire::Retries "0";' in call["config"]
        assert 'Dir::Etc::sourceparts "-";' in call["config"]
        assert (
            f'Dir::Etc::sourcelist "{harness["apt"]}/sources.list.d/ubuntu.sources";'
            in call["config"]
        )
        assert "AllowUnauthenticated" not in call["config"]
    assert calls[0]["env"]["HOME"] != str(harness["home"])
    assert calls[0]["env"]["TMPDIR"] != str(harness["temp"])
    assert calls[1]["env"]["HOME"] == str(harness["home"])
    sudo_calls = [
        json.loads(line) for line in harness["sudo_log"].read_text().splitlines()
    ]
    supervised = [c for c in sudo_calls if "/usr/bin/timeout" in c]
    assert len(supervised) == 1
    assert supervised[0][-2:] == ["install-deps", "chromium"]
    expected_digest = hashlib.sha256(harness["sources"].read_bytes()).hexdigest()
    diagnostics = harness["diagnostic"].read_text()
    assert diagnostics.count(f"ubuntu_sources_sha256={expected_digest}") == 2
    assert "source_bytes=unchanged" in diagnostics
    _assert_cleanup(harness)


@pytest.mark.parametrize(("phase", "code"), [("install-deps", 37), ("install", 29)])
def test_installer_failure_survives_output_and_cleanup_logging_failure(
    tmp_path, phase, code
):
    harness = _harness(tmp_path, phase, f"exit:{code}")
    tee = harness["tools"] / "tee"
    output_marker = f"mock-installer-output {phase}\n".encode()
    tee.write_text(
        "#!/usr/bin/python3\n"
        "import subprocess, sys\n"
        "content = sys.stdin.buffer.read()\n"
        f"if {output_marker!r} in content or "
        f"b'status={code}' in content: sys.exit(1)\n"
        "sys.exit(subprocess.run(['/usr/bin/tee', *sys.argv[1:]], input=content).returncode)\n"
    )
    tee.chmod(0o755)
    result = _run(harness)
    assert result.returncode == code
    assert f"status={code}" in result.stderr
    _assert_cleanup(harness)


@pytest.mark.parametrize(("phase", "code"), [("install-deps", 37), ("install", 29)])
def test_install_failure_preserves_status_and_phase_boundary(tmp_path, phase, code):
    harness = _harness(tmp_path, phase, f"exit:{code}")
    result = _run(harness)
    assert result.returncode == code
    assert [c["phase"] for c in _calls(harness)] == (
        ["install-deps"] if phase == "install-deps" else ["install-deps", "install"]
    )
    assert f"status={code}" in harness["diagnostic"].read_text()
    _assert_cleanup(harness)


@pytest.mark.parametrize("phase", ["install-deps", "install"])
@pytest.mark.parametrize(("mode", "expected"), [("hang", 124), ("ignore_term", 137)])
def test_hung_ordinary_process_tree_is_bounded_and_cleanup_survives(
    tmp_path, phase, mode, expected
):
    harness = _harness(tmp_path, phase, mode)
    started = time.monotonic()
    try:
        result = _run(harness)
        assert result.returncode == expected, result.stdout + result.stderr
        assert time.monotonic() - started < 6
        pids = json.loads(harness["pids"].read_text())
        for _ in range(50):
            if not any(_running(pid) for pid in pids):
                break
            time.sleep(0.02)
        assert not any(_running(pid) for pid in pids)
        if phase == "install-deps":
            assert [c["phase"] for c in _calls(harness)] == ["install-deps"]
        assert f"status={expected}" in harness["diagnostic"].read_text()
        _assert_cleanup(harness)
    finally:
        # Only fixture-owned runner-user processes; no host APT process exists.
        if harness["pids"].is_file():
            for pid in json.loads(harness["pids"].read_text()):
                if _running(pid):
                    os.kill(pid, signal.SIGKILL)


def test_missing_ubuntu_source_is_rejected_before_commands(tmp_path):
    harness = _harness(tmp_path)
    harness["sources"].unlink()
    result = _run(harness)
    assert result.returncode == 2
    assert not harness["sudo_log"].exists()


def test_source_change_during_installation_is_reported_as_failure(tmp_path):
    harness = _harness(tmp_path, "install", "change_source")
    result = _run(harness)
    assert result.returncode == 1
    assert "source_bytes=changed" in harness["diagnostic"].read_text()
    assert list(harness["temp"].iterdir()) == []
    assert list((harness["apt"] / "apt.conf.d").iterdir()) == [harness["existing"]]


def test_cli_rejects_local_host_before_privileged_commands():
    env = dict(os.environ)
    for key in ["GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "RUNNER_OS"]:
        env.pop(key, None)
    result = subprocess.run(
        ["bash", str(INSTALLER)], env=env, capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 2
    assert "restricted to GitHub-hosted Linux CI" in result.stderr


def test_workflow_bounds_install_and_retains_strict_required_failure():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    frontend = jobs["frontend"]
    assert frontend["timeout-minutes"] == 45
    steps = frontend["steps"]
    install = next(s for s in steps if s["name"] == "Install Playwright browser")
    assert install["id"] == "playwright_install"
    assert install["timeout-minutes"] == 17
    assert "continue-on-error" not in install
    assert "scripts/install-playwright-chromium-ci.sh" in install["run"]
    diagnostics = next(
        s for s in steps if s["name"] == "Preserve browser install diagnostics"
    )
    assert (
        diagnostics["if"]
        == "failure() && steps.playwright_install.outcome == 'failure'"
    )
    assert diagnostics["uses"] == (
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    )
    assert diagnostics["with"]["path"] == (
        "${{ runner.temp }}/frontend-browser-install/install.log"
    )
    assert steps.index(install) < steps.index(diagnostics)
    required = jobs["frontend-required"]
    assert required["if"] == "always()"
    assert required["needs"] == ["frontend"]
    assert required["steps"][0]["run"] == 'test "$FRONTEND_RESULT" = success'
