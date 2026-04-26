from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fetch_peer_spd_specimen_pages_parses_fixture_html(tmp_path: Path) -> None:
    fixture_html = Path("tests/fixtures/peer_spd/specimen_121.html").resolve()
    candidate_report = tmp_path / "candidates.json"
    candidate_report.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "seed_id": "peer_spd_rc_column_rectangular_seed_01",
                        "holdout_split": "train",
                        "selected_candidate": {
                            "specimen_id": "121",
                            "specimen_name": "Galeota et al. 1996, AB1",
                            "specimen_display_url": fixture_html.as_uri(),
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "specimens"
    out_report = tmp_path / "specimen_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_peer_spd_specimen_pages.py",
            "--candidates",
            str(candidate_report),
            "--out-dir",
            str(out_dir),
            "--out-report",
            str(out_report),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    report = _load(out_report)
    assert report["contract_pass"] is True
    assert report["summary"]["selected_seed_count"] == 1
    assert report["summary"]["fetch_pass_count"] == 1
    assert report["summary"]["parse_pass_count"] == 1
    row = report["rows"][0]
    assert row["resource_link_count"] == 2
    assert row["hysteresis_link_candidate_count"] >= 1
    raw_json = _load(Path(row["raw_json_path"]))
    assert raw_json["sections"]["Specimen Information"]["Name"] == "Galeota et al. 1996, AB1"
    assert raw_json["sections"]["Test Results"]["Failure Type"] == "Flexure"
    assert len(raw_json["resource_links"]) == 2

