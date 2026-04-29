from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_global_authority_gate_opensees_pass(tmp_path: Path) -> None:
    out = tmp_path / "global_authority_gate_report.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        "implementation/phase1/open_data/global_authority/authority_source_catalog.json",
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["opensees_pass"] is True


def test_global_authority_gate_require_sac_fails(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "catalog.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tracks": {
                    "opensees": {"enabled": True, "models": []},
                    "sac": {"enabled": True, "cases": []},
                    "nheri": {"enabled": False, "cases": []},
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "global_authority_gate_report.fail.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        str(bad_catalog),
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--require-sac",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] in {"ERR_OPENSEES_FAIL", "ERR_SAC_MISSING"}


def test_global_authority_gate_require_all_pass(tmp_path: Path) -> None:
    out = tmp_path / "global_authority_gate_report.all.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        "implementation/phase1/open_data/global_authority/authority_source_catalog.json",
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--require-sac",
        "--require-nheri",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["opensees_pass"] is True
    assert report["checks"]["sac_pass"] is True
    assert report["checks"]["nheri_pass"] is True


def test_global_authority_gate_min_case_fail(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "catalog_min_cases.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "tracks": {
                    "opensees": {
                        "enabled": True,
                        "models": [
                            {
                                "id": "SCBF16B",
                                "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                                "real_source": True,
                                "require_shell_beam_mix": False,
                            }
                        ],
                    },
                    "sac": {
                        "enabled": True,
                        "cases": [
                            {
                                "case_id": "SAC_ONE",
                                "real_source": True,
                                "holdout_split": "holdout",
                                "source_url": "https://example.org/sac",
                                "source_file_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                                "source_sha256": "309234fd42a58369a6d41198290527c6a86fee7da38c38a2fcbf625318720b80",
                                "reference_metrics_path": "implementation/phase1/open_data/global_authority/sac/sac20_reference_metrics.json",
                            }
                        ],
                    },
                    "nheri": {"enabled": False, "cases": []},
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "global_authority_gate_report.min.fail.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        str(bad_catalog),
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--require-sac",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] == "ERR_SAC_MIN_CASES"


def test_global_authority_gate_require_sac_passes_without_optional_csv_paths(tmp_path: Path) -> None:
    catalog = json.loads(
        Path("implementation/phase1/open_data/global_authority/authority_source_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    catalog["tracks"]["nheri"] = {"enabled": False, "cases": []}
    for case in catalog["tracks"]["sac"]["cases"]:
        case.pop("hf_csv_path", None)
        case.pop("lf_csv_path", None)
        case.pop("hf_csv_sha256", None)
        case.pop("lf_csv_sha256", None)

    catalog_path = tmp_path / "catalog_sac_optional_csvs.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    out = tmp_path / "global_authority_gate_report.sac_optional_csvs.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        str(catalog_path),
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--require-sac",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["checks"]["sac_pass"] is True
    assert report["checks"]["sac_source_diversity_pass"] is True
    assert report["checks"]["sac_source_integrity_pass"] is True


def test_global_authority_gate_holdout_leak_fail(tmp_path: Path) -> None:
    split_manifest = tmp_path / "split_manifest.json"
    split_manifest.write_text(
        json.dumps(
            {
                "train": ["SAC20_LA_holdout_01"],
                "val": [],
                "test": [],
                "holdout": [],
            }
        ),
        encoding="utf-8",
    )
    bad_catalog = tmp_path / "catalog_holdout_fail.json"
    bad_catalog.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "split_manifest_path": str(split_manifest),
                "tracks": {
                    "opensees": {
                        "enabled": True,
                        "models": [
                            {
                                "id": "SCBF16B",
                                "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                                "real_source": True,
                                "require_shell_beam_mix": False,
                            }
                        ],
                    },
                    "sac": {
                        "enabled": True,
                        "cases": [
                            {
                                "case_id": "SAC20_LA_holdout_01",
                                "real_source": True,
                                "holdout_split": "holdout",
                                "source_url": "https://example.org/sac",
                                "source_file_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                                "source_sha256": "309234fd42a58369a6d41198290527c6a86fee7da38c38a2fcbf625318720b80",
                                "reference_metrics_path": "implementation/phase1/open_data/global_authority/sac/sac20_reference_metrics.json",
                            }
                        ],
                    },
                    "nheri": {"enabled": False, "cases": []},
                },
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "global_authority_gate_report.holdout.fail.json"
    cmd = [
        sys.executable,
        "implementation/phase1/run_global_authority_gate.py",
        "--catalog",
        str(bad_catalog),
        "--workdir-out",
        str(tmp_path / "run_artifacts"),
        "--require-sac",
        "--min-sac-cases",
        "1",
        "--out",
        str(out),
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    assert proc.returncode != 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["contract_pass"] is False
    assert report["reason_code"] in {"ERR_HOLDOUT_LEAK", "ERR_SAC_FAIL"}
