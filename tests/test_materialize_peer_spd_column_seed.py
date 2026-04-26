from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_materialize_peer_spd_column_seed_from_cached_resource(tmp_path: Path) -> None:
    raw_out = tmp_path / "seed.raw.json"
    fixture_out = tmp_path / "seed.hinge_fixture.json"
    source_manifest_out = tmp_path / "seed.source_manifest.json"
    seed_manifest = tmp_path / "seed_manifest.json"
    seed_manifest.write_text(
        json.dumps(
            {
                "source_name": "PEER SPD",
                "source_urls": ["https://example.test/specimens"],
                "seed_cases": [
                    {
                        "seed_id": "peer_spd_rc_column_rebar_sensitive_seed_01",
                        "holdout_split": "val",
                        "selection_filters": {"rebar_ratio_band": "higher"},
                        "expected_local_targets": {
                            "raw_json": str(raw_out),
                            "hinge_fixture": str(fixture_out),
                            "source_manifest": str(source_manifest_out),
                        },
                    }
                ],
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
                        "seed_id": "peer_spd_rc_column_rebar_sensitive_seed_01",
                        "selected_candidate": {
                            "specimen_id": "121",
                            "specimen_name": "Specimen 121",
                            "family_name": "Family A",
                            "column_shape": "rectangular",
                            "confinement_type": "tied",
                            "confinement_detail": "RI",
                            "axial_load_kn": 1000.0,
                            "axial_load_ratio": 0.2,
                            "longitudinal_rebar_ratio": 0.0603,
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
    page_json = tmp_path / "seed.specimen_page.json"
    page_json.write_text(
        json.dumps(
            {
                "seed_id": "peer_spd_rc_column_rebar_sensitive_seed_01",
                "specimen_id": "121",
                "specimen_display_url": "https://example.test/specimen/121",
                "page_title": "PEER Structural Performance Database",
                "sections": {"Geometry": {"Length": "L-Measured: 1,140 (mm)"}},
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
            {"rows": [{"seed_id": "peer_spd_rc_column_rebar_sensitive_seed_01", "raw_json_path": str(page_json)}]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    resource_dir = tmp_path / "resources"
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / "peer_spd_rc_column_rebar_sensitive_seed_01.hysteresis.txt").write_text(
        'Specimen 121\n4\n0\t0\n1.14\t10\n-1.14\t-9\n2.28\t18\n',
        encoding="utf-8",
    )
    fetch_report = tmp_path / "hysteresis_report.json"
    out_report = tmp_path / "materialize_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/materialize_peer_spd_column_seed.py",
            "--seed-manifest",
            str(seed_manifest),
            "--candidates",
            str(candidates),
            "--specimen-pages-report",
            str(pages_report),
            "--seed-id",
            "peer_spd_rc_column_rebar_sensitive_seed_01",
            "--resource-out-dir",
            str(resource_dir),
            "--fetch-report",
            str(fetch_report),
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
    fixture = _load(fixture_out)
    assert report["contract_pass"] is True
    assert report["summary"]["normalized_seed_count"] == 1
    assert fixture["contract_pass"] is True
    assert fixture["seed_id"] == "peer_spd_rc_column_rebar_sensitive_seed_01"
    assert fixture["hysteresis_summary"]["point_count"] == 4
    assert fixture["hinge_refresh_targets"]["rebar_sensitive_expected"] is True
