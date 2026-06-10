from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "build_mgt_opening_source_noop_ready_receipt.py"
DEFAULT_OUT = (
    REPO_ROOT
    / "implementation/phase1/release_evidence/productization/mgt_opening_source_noop_ready_receipt.json"
)


def _ensure_dependencies() -> None:
    """Make sure the upstream receipts exist before we build the no-op receipt."""
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_mgt_element_local_axis_opening_semantics_receipt.py"),
        ],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "run_mgt_surface_shell_bending_tangent.py"),
        ],
        check=False,
        capture_output=True,
    )


def test_opening_source_noop_ready_receipt_default(tmp_path: Path) -> None:
    _ensure_dependencies()
    out = DEFAULT_OUT
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-json", str(out)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "mgt-opening-source-noop-ready-receipt.v1"
    assert payload["status"] == "ready"
    assert payload["current_source_opening_marker_count"] == 0
    assert payload["current_source_opening_noop_ready"] is True
    assert payload["generic_opening_cutout_ready"] is False
    assert payload["checks"]["opening_marker_count_zero"] is True
    assert payload["checks"]["opening_rows_absent_in_local_axis"] is True
    assert "closed" in payload["claim_boundary"]
    assert "not_closed" in payload["claim_boundary"]
    assert payload["blockers"] == []


def test_opening_source_noop_ready_receipt_fails_without_local_axis(tmp_path: Path) -> None:
    out = tmp_path / "noop.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--local-axis-opening-json",
            str(tmp_path / "missing.json"),
            "--output-json",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["checks"]["local_axis_opening_noop_runtime_ready"] is False
    assert "local_axis_opening_noop_runtime_not_ready" in payload["blockers"]
    assert payload["status"] == "partial"


def test_opening_source_noop_ready_receipt_fails_with_present_marker() -> None:
    """Synthesize a local-axis opening receipt that reports opening rows present."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_local_axis = tmp_path / "local_axis.json"
        fake_local_axis.write_text(
            json.dumps(
                {
                    "support": {
                        "current_source_opening_noop_runtime_ready": False,
                        "opening_source_rows_present": True,
                        "generic_opening_cutout_runtime_semantics_ready": False,
                    },
                    "summary": {
                        "opening_marker_row_count": 1,
                    },
                    "opening_source_scan": {"opening_marker_row_count": 1},
                }
            ),
            encoding="utf-8",
        )
        fake_shell = tmp_path / "shell.json"
        fake_shell.write_text(
            json.dumps(
                {
                    "anisotropy": {"mode": "isotropic"},
                    "opening_source_inventory": {
                        "current_source_opening_marker_count": 1,
                        "current_source_opening_noop_ready": False,
                        "generic_opening_cutout_runtime_ready": False,
                    },
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "noop.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--local-axis-opening-json",
                str(fake_local_axis),
                "--shell-bending-tangent-json",
                str(fake_shell),
                "--output-json",
                str(out),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["current_source_opening_marker_count"] == 1
        assert payload["current_source_opening_noop_ready"] is False
        assert "opening_source_rows_present_but_noop_not_armed" in payload["blockers"]
        assert payload["status"] == "partial"
