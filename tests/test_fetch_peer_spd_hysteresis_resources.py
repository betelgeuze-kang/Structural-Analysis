from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fetch_peer_spd_hysteresis_resources_from_cached_text(tmp_path: Path) -> None:
    raw_out = tmp_path / "seed.raw.json"
    seed_manifest = tmp_path / "seed_manifest.json"
    seed_manifest.write_text(
        json.dumps(
            {
                "seed_cases": [
                    {
                        "seed_id": "seed_01",
                        "holdout_split": "train",
                        "expected_local_targets": {"raw_json": str(raw_out)},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    candidates = tmp_path / "candidates.json"
    candidates.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "seed_id": "seed_01",
                        "selected_candidate": {
                            "specimen_id": "121",
                            "specimen_name": "Specimen 121",
                            "family_name": "Family A",
                            "column_shape": "rectangular",
                            "confinement_type": "tied",
                            "confinement_detail": "RI",
                            "axial_load_kn": 1000.0,
                            "axial_load_ratio": 0.2,
                            "longitudinal_rebar_ratio": 0.06,
                            "transverse_reinforcement_ratio": 0.012,
                            "fc_mpa": 80.0,
                            "section_width_mm": 250.0,
                            "section_depth_mm": 250.0,
                            "source_url": "https://example.test/specimens",
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    page_json = tmp_path / "seed_01.specimen_page.json"
    page_json.write_text(
        json.dumps(
            {
                "seed_id": "seed_01",
                "specimen_id": "121",
                "specimen_display_url": "https://example.test/specimen/121",
                "page_title": "PEER Structural Performance Database",
                "sections": {"Geometry": {"Length": "L-Inflection: 1,140 (mm) L-Measured: 1,140 (mm)"}},
                "hysteresis_link_candidates": [
                    {"href": "https://example.test/gal96ab1.txt", "text": "Force Displacement Data (data)"}
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    pages_report = tmp_path / "specimen_pages_report.json"
    pages_report.write_text(
        json.dumps(
            {"rows": [{"seed_id": "seed_01", "raw_json_path": str(page_json)}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "resources"
    out_dir.mkdir(parents=True, exist_ok=True)
    cached_txt = out_dir / "seed_01.hysteresis.txt"
    cached_txt.write_text(
        'Galeota 1996 Specimen AB1\n4\n0\t0\n1.14\t10.0\n-1.14\t-9.5\n2.28\t18.0\n',
        encoding="utf-8",
    )
    out_report = tmp_path / "fetch_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_peer_spd_hysteresis_resources.py",
            "--seed-manifest",
            str(seed_manifest),
            "--candidates",
            str(candidates),
            "--specimen-pages-report",
            str(pages_report),
            "--seed-id",
            "seed_01",
            "--out-dir",
            str(out_dir),
            "--out-report",
            str(out_report),
            "--prefer-cache",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    report = _load(out_report)
    raw = _load(raw_out)
    assert report["contract_pass"] is True
    assert report["summary"]["parse_pass_count"] == 1
    assert raw["contract_pass"] is True
    assert raw["specimen"]["height_mm"] == 1140.0
    assert raw["hysteresis"]["point_count_parsed"] == 4
    assert raw["hysteresis"]["rows"][1]["drift_ratio"] == 0.001

