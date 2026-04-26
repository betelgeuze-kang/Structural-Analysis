from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.build_wind_raw_mapping_artifact import _resolve_midas_json_path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_wind_raw_mapping_artifact_emits_traceable_mapping(tmp_path: Path) -> None:
    raw = tmp_path / "wind.csv"
    raw.write_text("time_s,across_wind_force_kN,along_wind_force_kN\n0,1.0,0.4\n1,2.0,0.5\n2,3.0,0.6\n", encoding="utf-8")
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
    conversion = tmp_path / "midas_conversion_report.json"
    _write_json(
        conversion,
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
    out = tmp_path / "wind_tunnel_raw_mapping.json"
    proc = subprocess.run(
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
            str(conversion),
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
    assert payload["summary"]["pressure_loaded_element_count"] == 2
    assert payload["summary"]["pressure_case_counts"] == {"DEAD": 1, "LIVE": 1}
    assert payload["checks"]["raw_manifest_verified"] is True
    assert payload["checks"]["pressure_rows_present"] is True
    assert payload["checks"]["element_to_node_backreference_present"] is True
    assert payload["checks"]["floor_proxy_present"] is True


def test_build_wind_raw_mapping_artifact_resolves_repo_fallback_midas_json() -> None:
    resolved = _resolve_midas_json_path("implementation/phase1/midas_model.json")
    assert resolved.exists()
    assert resolved.as_posix().endswith("implementation/phase1/open_data/midas/midas_model.json")
