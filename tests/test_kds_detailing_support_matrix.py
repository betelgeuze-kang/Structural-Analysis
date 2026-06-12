"""Tests for KDS/detailing support matrix evidence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_kds_detailing_support_matrix_is_ready(tmp_path: Path) -> None:
    out = tmp_path / "kds_detailing_support_matrix.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/build_kds_detailing_support_matrix.py"),
            "--output-json",
            str(out),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "kds-detailing-support-matrix.v1"
    assert payload["status"] == "ready"
    assert payload["clause_breadth_ready"] is True
    assert payload["optimization_rows_guarded"] is True
    assert payload["trace_ready"] is True
    assert payload["unsupported_queue_ready"] is True
    assert payload["clause_inventory"]["clause_count"] >= 20
    assert set(payload["clause_inventory"]["required_rc_families"]) <= set(
        payload["clause_inventory"]["covered_rc_families"]
    )
    assert payload["broader_unsupported_claim_queue"]
