from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_wind_tunnel_raw_mapping_report_flags_missing_mapping(tmp_path: Path) -> None:
    raw = tmp_path / "wind.csv"
    raw.write_text("time_s,across_wind_force_kN\n0,1.0\n1,2.0\n", encoding="utf-8")
    manifest = tmp_path / "wind.manifest.json"
    _write_json(
        manifest,
        {
            "real_source": True,
            "data_path": str(raw),
            "source_url": "https://example.com/wind-source",
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        },
    )
    midas = tmp_path / "midas.json"
    _write_json(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "semantic_load_case_count": 2,
                "use_stld_block_count": 1,
                "bound_pressure_row_count": 8,
                "unbound_pressure_row_count": 0,
            },
        },
    )
    out = tmp_path / "wind_raw_mapping_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_wind_tunnel_raw_mapping_report.py",
            "--raw-wind",
            str(raw),
            "--raw-wind-manifest",
            str(manifest),
            "--wind-raw-mapping",
            str(tmp_path / "missing_mapping.csv"),
            "--midas-conversion",
            str(midas),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_MAPPING_MISSING"
    assert payload["checks"]["wind_raw_mapping_available"]["status"] == "open"
    assert payload["summary"]["mapping_row_count"] == 0
    assert payload["summary"]["manifest_verified"] is True


def test_wind_tunnel_raw_mapping_report_passes_with_traceable_inputs(tmp_path: Path) -> None:
    raw = tmp_path / "wind.csv"
    raw.write_text("time_s,across_wind_force_kN\n0,1.0\n1,2.0\n2,3.0\n", encoding="utf-8")
    manifest = tmp_path / "wind.manifest.json"
    _write_json(
        manifest,
        {
            "real_source": True,
            "data_path": str(raw),
            "source_url": "https://example.com/wind-source",
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        },
    )
    mapping = tmp_path / "mapping.csv"
    mapping.write_text("node_id,target_node_id,floor_id\n1,101,10\n2,102,11\n", encoding="utf-8")
    midas = tmp_path / "midas.json"
    _write_json(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "semantic_load_case_count": 2,
                "use_stld_block_count": 1,
                "bound_pressure_row_count": 8,
                "unbound_pressure_row_count": 0,
            },
        },
    )
    out = tmp_path / "wind_raw_mapping_report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_wind_tunnel_raw_mapping_report.py",
            "--raw-wind",
            str(raw),
            "--raw-wind-manifest",
            str(manifest),
            "--wind-raw-mapping",
            str(mapping),
            "--midas-conversion",
            str(midas),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["mapping_mode"] == "csv_mapping_rows"
    assert payload["summary"]["raw_row_count"] == 3
    assert payload["summary"]["mapping_row_count"] == 2
    assert payload["summary"]["mapped_node_row_count"] == 2
    assert payload["summary"]["mapped_floor_row_count"] == 2
    assert payload["summary"]["midas_bound_pressure_row_count"] == 8
    assert payload["summary"]["midas_unbound_pressure_row_count"] == 0
    assert payload["summary"]["manifest_verified"] is True


def test_wind_tunnel_raw_mapping_report_passes_with_generated_json_artifact(tmp_path: Path) -> None:
    raw = tmp_path / "wind.csv"
    raw.write_text("time_s,across_wind_force_kN,along_wind_force_kN\n0,1.0,0.5\n1,2.0,0.6\n2,3.0,0.7\n", encoding="utf-8")
    manifest = tmp_path / "wind.manifest.json"
    _write_json(
        manifest,
        {
            "real_source": True,
            "data_path": str(raw),
            "source_url": "https://example.com/wind-source",
            "sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        },
    )
    roundtrip = tmp_path / "midas_roundtrip.json"
    _write_json(
        roundtrip,
        {
            "model": {
                "nodes": [
                    {"id": 1, "x": 0.0, "y": 0.0, "z": 0.0},
                    {"id": 2, "x": 0.0, "y": 0.0, "z": 3.0},
                    {"id": 3, "x": 0.0, "y": 0.0, "z": 6.0},
                ],
                "elements": [
                    {"id": 101, "node_ids": [1, 2]},
                    {"id": 102, "node_ids": [2, 3]},
                ],
                "loads": {
                    "pressure_loads": [
                        {"element_ids": [101], "load_case": "DEAD", "element_type": "PLATE", "load_type": "FACE"},
                        {"element_ids": [102], "load_case": "LIVE", "element_type": "PLATE", "load_type": "FACE"},
                    ]
                },
            }
        },
    )
    midas = tmp_path / "midas.json"
    _write_json(
        midas,
        {
            "contract_pass": True,
            "metrics": {
                "semantic_load_case_count": 2,
                "use_stld_block_count": 1,
                "bound_pressure_row_count": 2,
                "unbound_pressure_row_count": 0,
            },
        },
    )
    mapping = tmp_path / "wind_tunnel_raw_mapping.json"
    build_proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/build_wind_raw_mapping_artifact.py",
            "--raw-wind",
            str(raw),
            "--raw-wind-manifest",
            str(manifest),
            "--midas-json",
            str(roundtrip),
            "--midas-conversion",
            str(midas),
            "--out",
            str(mapping),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert build_proc.returncode == 0, build_proc.stderr

    out = tmp_path / "wind_raw_mapping_report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/generate_wind_tunnel_raw_mapping_report.py",
            "--raw-wind",
            str(raw),
            "--raw-wind-manifest",
            str(manifest),
            "--wind-raw-mapping",
            str(mapping),
            "--midas-conversion",
            str(midas),
            "--out",
            str(out),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["summary"]["mapping_mode"] == "raw_hffb_node_pressure_mapping"
    assert payload["summary"]["mapping_row_count"] == 2
    assert payload["summary"]["mapped_node_row_count"] == 3
    assert payload["summary"]["mapped_floor_row_count"] == 2
