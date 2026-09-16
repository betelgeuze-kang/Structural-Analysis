"""Keep current-source analytic evidence in every full Python test shard."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/python-test-collection.yml"
BUILD = "python scripts/build_analytic_frame_verification_artifact.py"


def _workflow():
    # BaseLoader preserves GitHub's `on` key rather than YAML 1.1 booleans.
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_each_full_shard_rebuilds_and_checks_analytic_receipt():
    workflow = _workflow()
    job = workflow["jobs"]["full_shards"]
    assert job["strategy"]["matrix"]["shard"] == ["0", "1", "2", "3"]
    step = next(s for s in job["steps"] if s["name"] == "Materialize exact current-source test evidence")
    commands = [line.strip() for line in step["run"].splitlines()]
    assert commands.count(BUILD) == 1
    assert commands.count(BUILD + " --check") == 1
    assert commands.index(BUILD) < commands.index(BUILD + " --check")
    assert step.get("continue-on-error", "false") != "true"


def test_snapshot_precedes_materialization_and_complete_test_execution():
    steps = _workflow()["jobs"]["full_shards"]["steps"]
    names = [s["name"] for s in steps]
    assert names.index("Validate pristine commercial gap ledger") < names.index("Materialize exact current-source test evidence")
    assert names.index("Materialize exact current-source test evidence") < names.index("Run materialized repository test suite shard")
    run = next(s["run"] for s in steps if s["name"] == "Run materialized repository test suite shard")
    assert "scripts/run_pytest_shard.py" in run
    assert "--shard-count 4" in run
    # Retain the two existing deselections; this fix must not add exclusions.
    assert run.count("--deselect") == 2
    assert "test_current_hierarchy" not in run


def test_aggregate_still_requires_all_shards():
    workflow = _workflow()
    full = workflow["jobs"]["full"]
    assert full["needs"] == "full_shards"
    assert full["if"] == "${{ always() }}"
    assert full["steps"][0]["run"] == 'test "$FULL_SHARDS_RESULT" = "success"'
    assert workflow["permissions"]["contents"] == "read"


# These subprocess cases validate the CI shell wrapper, not solver physics.
TEST_STEP = "Run materialized repository test suite shard"
UPLOAD_STEP = "Upload repository Python shard diagnostics"
BASH = shutil.which("bash")


def _step(name):
    return next(s for s in _workflow()["jobs"]["full_shards"]["steps"] if s["name"] == name)


def test_diagnostics_upload_is_always_scoped_and_unique():
    steps = _workflow()["jobs"]["full_shards"]["steps"]
    names = [s["name"] for s in steps]
    upload = _step(UPLOAD_STEP)
    assert names.index("Audit analytic evidence after tests") < names.index(UPLOAD_STEP)
    assert upload["if"] == "${{ always() }}"
    assert upload.get("continue-on-error", "false") == "false"
    assert upload["uses"] == "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a"
    options = upload["with"]
    for token in ("github.sha", "github.run_id", "github.run_attempt", "matrix.shard"):
        assert "${{ " + token + " }}" in options["name"]
    assert set(options["path"].splitlines()) == {
        "artifacts/ci/analytic-before.json", "artifacts/ci/analytic-after.json",
        "artifacts/ci/pytest-shard.xml", "artifacts/ci/pytest-shard.log",
    }
    assert options["retention-days"] == "14"
    # Setup may fail before any report exists. This cannot clear earlier failures.
    assert options["if-no-files-found"] == "warn"
    assert options.get("overwrite", "false") == "false"
    assert options.get("include-hidden-files", "false") == "false"
    assert _workflow()["permissions"] == {"contents": "read"}


def test_logging_keeps_fail_closed_shell_and_full_tracebacks():
    step = _step(TEST_STEP)
    assert step["shell"] == "bash"
    assert "set -o pipefail" in step["run"]
    assert "--tb=long" in step["run"]
    assert "--junitxml artifacts/ci/pytest-shard.xml" in step["run"]
    assert "2>&1 | tee artifacts/ci/pytest-shard.log" in step["run"]
    assert step.get("continue-on-error", "false") == "false"


def _run_wrapper(tmp_path, exit_code, *, fail_tee=False):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    runner = scripts / "run_pytest_shard.py"
    runner.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "Path('args.json').write_text(json.dumps(sys.argv[1:]))\n"
        "print('shard standard output')\n"
        "print('shard standard error', file=sys.stderr)\n"
        "if '--junitxml' in sys.argv:\n"
        "    report = Path(sys.argv[sys.argv.index('--junitxml') + 1])\n"
        "    report.parent.mkdir(parents=True, exist_ok=True)\n"
        "    report.write_text('<testsuites/>')\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    if fail_tee:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        tee = bin_dir / "tee"
        tee.write_text("#!/bin/sh\ncat >/dev/null\nexit 9\n", encoding="utf-8")
        tee.chmod(0o755)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    script = _step(TEST_STEP)["run"].replace("${{ matrix.shard }}", "3")
    script = script.replace("python scripts/", shlex.quote(sys.executable) + " scripts/")
    return subprocess.run(
        [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )


@pytest.mark.skipif(BASH is None, reason="Ubuntu CI shell contract requires bash")
@pytest.mark.parametrize("exit_code", [0, 1, 2, 5, 7])
def test_logged_shard_retains_exit_code_arguments_and_both_streams(tmp_path, exit_code):
    result = _run_wrapper(tmp_path, exit_code)
    assert result.returncode == exit_code, result.stdout + result.stderr
    log = (tmp_path / "artifacts/ci/pytest-shard.log").read_text(encoding="utf-8")
    assert "shard standard output" in log
    assert "shard standard error" in log
    assert (tmp_path / "artifacts/ci/pytest-shard.xml").read_text() == "<testsuites/>"
    arguments = json.loads((tmp_path / "args.json").read_text())
    assert arguments == [
        "--shard-index", "3", "--shard-count", "4", "--", "-q", "--tb=long",
        "--junitxml", "artifacts/ci/pytest-shard.xml",
        "--deselect",
        "tests/test_commercial_gap_ledger_status.py::test_commercial_gap_ledger_status_is_honest_about_current_blockers",
        "--deselect",
        "tests/test_build_g1_mgt_hip_current_tangent_host_parser_receipt.py::test_committed_receipt_is_reproducible",
    ]


@pytest.mark.skipif(BASH is None, reason="Ubuntu CI shell contract requires bash")
def test_log_writer_failure_also_fails_the_step(tmp_path):
    result = _run_wrapper(tmp_path, 0, fail_tee=True)
    assert result.returncode == 9, result.stdout + result.stderr


@pytest.mark.skipif(BASH is None, reason="Ubuntu CI shell contract requires bash")
@pytest.mark.parametrize("passes", [True, False])
def test_real_pytest_shard_preserves_result_and_junit(tmp_path, passes):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/run_pytest_shard.py", scripts / "run_pytest_shard.py")
    tests = tmp_path / "tests"
    tests.mkdir()
    relative = "tests/test_wrapper_sentinel.py"
    (tmp_path / relative).write_text(f"def test_sentinel():\n    assert {passes!r}\n", encoding="utf-8")
    digest = hashlib.sha256(relative.encode("utf-8")).digest()
    index = int.from_bytes(digest[:8], byteorder="big") % 4
    script = _step(TEST_STEP)["run"].replace("${{ matrix.shard }}", str(index))
    script = script.replace("python scripts/", shlex.quote(sys.executable) + " scripts/")
    env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1")
    env.pop("PYTEST_ADDOPTS", None)
    result = subprocess.run(
        [BASH, "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode == (0 if passes else 1), result.stdout + result.stderr
    diagnostics = tmp_path / "artifacts/ci"
    log = (diagnostics / "pytest-shard.log").read_text(encoding="utf-8")
    assert "pytest_shard_v1" in log
    assert ("1 passed" if passes else "1 failed") in log
    suite = ET.parse(diagnostics / "pytest-shard.xml").getroot().find("testsuite")
    assert suite is not None
    assert suite.get("tests") == "1"
    assert suite.get("failures") == ("0" if passes else "1")
