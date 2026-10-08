"""RC cross-test helpers must collect at the repository package boundary."""

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
AFFECTED_TESTS = (
    "test_rc_fiber_quantity_report.py",
    "test_rc_fiber_quantity_report_service.py",
    "test_rc_original_artifact_reads.py",
)


@pytest.mark.parametrize(
    ("filenames", "extra_args"),
    [
        (AFFECTED_TESTS, ()),
        *(([filename], ()) for filename in AFFECTED_TESTS),
        (AFFECTED_TESTS, ("--import-mode=importlib",)),
    ],
)
def test_rc_tests_collect_from_outside_repository(tmp_path, filenames, extra_args):
    # Preserve the real package marker. Missing it can let pytest expose bare
    # test module names and hide cross-test imports that fail in the full repo.
    assert (ROOT / "tests" / "__init__.py").is_file()
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            *extra_args,
            *(str(ROOT / "tests" / filename) for filename in filenames),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, output
    assert "no tests collected" not in output, output
