from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fetch_tpu_case_mat_succeeds_with_local_html_and_local_mat(tmp_path: Path) -> None:
    case_html = tmp_path / "case.html"
    case_html.write_text(
        "<html><head><title>TPU Case Alpha</title></head>"
        "<body><a href=\"https://minio.wind.arch.t-kougei.ac.jp/web/media/case/Alpha/time_series_1_0.mat\">mat</a></body></html>",
        encoding="utf-8",
    )
    local_mat = tmp_path / "alpha.mat"
    local_mat.write_bytes(b"MATLAB 5.0 MAT-file test payload")
    out_mat = tmp_path / "out" / "alpha.mat"
    out_manifest = tmp_path / "out" / "alpha.manifest.json"
    out_report = tmp_path / "out" / "alpha.report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_tpu_case_mat.py",
            "--case-page-html",
            str(case_html),
            "--mat-url",
            str(local_mat),
            "--out-mat",
            str(out_mat),
            "--source-manifest-out",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr

    manifest = _load(out_manifest)
    report = _load(out_report)
    assert out_mat.read_bytes() == local_mat.read_bytes()
    assert manifest["contract_pass"] is True
    assert manifest["source_name"] == "TPU Case Alpha"
    assert manifest["source_origin_class"] == "official_external_benchmark"
    assert manifest["mat_source_resolved"] == str(local_mat.resolve())
    assert manifest["size_bytes"] == len(local_mat.read_bytes())
    assert len(manifest["sha256"]) == 64
    assert report["contract_pass"] is True
    assert report["summary"]["mat_link_count"] == 1
    assert report["summary"]["candidate_mat_urls_head"] == [
        "https://minio.wind.arch.t-kougei.ac.jp/web/media/case/Alpha/time_series_1_0.mat"
    ]
    assert report["summary"]["resolved_case_page"] == str(case_html.resolve())
    assert report["summary"]["size_bytes"] == len(local_mat.read_bytes())


def test_fetch_tpu_case_mat_fails_without_input_mode(tmp_path: Path) -> None:
    out_manifest = tmp_path / "manifest.json"
    out_report = tmp_path / "report.json"
    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_tpu_case_mat.py",
            "--source-manifest-out",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode != 0
    report = _load(out_report)
    assert report["reason_code"] == "ERR_INPUT_MODE"
    assert report["contract_pass"] is False


def test_fetch_tpu_case_mat_fails_for_empty_mat(tmp_path: Path) -> None:
    case_html = tmp_path / "case.html"
    case_html.write_text(
        "<html><head><title>TPU Case Empty</title></head><body></body></html>",
        encoding="utf-8",
    )
    empty_mat = tmp_path / "empty.mat"
    empty_mat.write_bytes(b"")
    out_manifest = tmp_path / "empty.manifest.json"
    out_mat = tmp_path / "empty.out.mat"
    out_report = tmp_path / "empty.report.json"

    proc = subprocess.run(
        [
            sys.executable,
            "implementation/phase1/fetch_tpu_case_mat.py",
            "--case-page-html",
            str(case_html),
            "--mat-url",
            str(empty_mat),
            "--out-mat",
            str(out_mat),
            "--source-manifest-out",
            str(out_manifest),
            "--out-report",
            str(out_report),
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    assert proc.returncode != 0
    manifest = _load(out_manifest)
    report = _load(out_report)
    assert manifest["reason_code"] == "ERR_MAT_EMPTY"
    assert report["reason_code"] == "ERR_MAT_EMPTY"
    assert report["summary"]["size_bytes"] == 0
