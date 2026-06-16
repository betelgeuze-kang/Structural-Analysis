from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from implementation.phase1.open_data.korea.generate_korean_source_catalog import (
    build_korean_source_catalog,
    load_merged_korean_seed_rows,
)
from implementation.phase1.open_data.korea.korean_building_scale import building_scale_band, is_medium_or_large

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "report_medium_large_korean_sources.py"


def test_combined_catalog_has_medium_and_large_records() -> None:
    rows = load_merged_korean_seed_rows()
    catalog = build_korean_source_catalog(rows, generated_at_utc="2026-05-31T00:00:00Z")
    scales = {building_scale_band(str(row.get("storey_band") or "")) for row in catalog["source_records"]}
    medium_large = [row for row in catalog["source_records"] if is_medium_or_large(row)]
    assert "medium" in scales
    assert "large" in scales
    assert len(medium_large) >= 2
    assert sum(1 for row in medium_large if building_scale_band(str(row["storey_band"])) == "medium") >= 1
    assert sum(1 for row in medium_large if building_scale_band(str(row["storey_band"])) == "large") >= 1


def test_report_medium_large_cli_on_repo_catalog(tmp_path: Path) -> None:
    catalog_path = REPO_ROOT / "implementation/phase1/open_data/korea/korean_source_catalog.json"
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_korean_source_catalog.py")],
        cwd=REPO_ROOT,
        check=True,
    )
    out_json = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--catalog",
            str(catalog_path),
            "--output-json",
            str(out_json),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["summary"]["medium_large_source_count"] >= 2
    assert payload["summary"]["medium_count"] >= 1
    assert payload["summary"]["large_count"] >= 1
