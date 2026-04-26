from __future__ import annotations

import json
from functools import partial
import http.server
import importlib
from pathlib import Path
import socketserver
import threading
import zipfile

collector_module = importlib.import_module("implementation.phase1.open_data.irregular.collect_irregular_public_structures")
from implementation.phase1.open_data.irregular import collect_irregular_public_structures


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True


def _serve_directory(directory: Path) -> tuple[_ThreadingTCPServer, str]:
    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = _ThreadingTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_collect_irregular_public_structures_mixed_local_formats(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    mgt_path = source_dir / "tower_case.mgt"
    mgt_path.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")

    ifc_path = source_dir / "atrium.ifc"
    ifc_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    csv_path = source_dir / "sensor_tables.csv"
    csv_path.write_text("node_id,ux,uy\n1,0.0,0.0\n", encoding="utf-8")

    zip_path = source_dir / "mixed_bundle.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_file:
        zip_file.writestr("frame/model.inp", "*HEADING\n")
        zip_file.writestr("meta/notes.txt", "bundle notes\n")

    catalog = tmp_path / "irregular_public_structure_source_catalog.json"
    out_dir = tmp_path / "out"
    report_out = tmp_path / "irregular_public_structure_corpus_report.json"
    _write_json(
        catalog,
        {
            "schema_version": "1.0",
            "sources": [
                {
                    "source_id": "tower_case",
                    "url": str(mgt_path),
                    "format": "mgt",
                    "metadata": {"jurisdiction": "KR"},
                },
                {
                    "source_id": "atrium_case",
                    "url": ifc_path.as_uri(),
                    "metadata": {"discipline": "bim"},
                },
                {
                    "source_id": "sensor_case",
                    "path": "sources/sensor_tables.csv",
                    "format": "csv_tables",
                },
                {
                    "source_id": "bundle_case",
                    "url": zip_path.as_uri(),
                },
            ],
        },
    )

    report = collect_irregular_public_structures(
        catalog_path=catalog,
        out_dir=out_dir,
        report_out=report_out,
    )

    assert report["contract_pass"] is True
    assert report["reason_code"] == "PASS"
    assert report["summary"]["source_count"] == 4
    assert report["summary"]["collected_count"] == 4
    assert report["summary"]["rejected_count"] == 0
    assert report["summary"]["local_path_count"] == 2
    assert report["summary"]["file_url_count"] == 2
    assert report["summary"]["declared_format_count"] == 2
    assert report["summary"]["inferred_format_count"] == 2
    assert report["summary"]["format_counts"]["mgt"] == 1
    assert report["summary"]["format_counts"]["ifc"] == 1
    assert report["summary"]["format_counts"]["csv_tables"] == 1
    assert report["summary"]["format_counts"]["zip_bundle"] == 1
    assert report["summary"]["total_bytes_copied"] > 0

    written_report = json.loads(report_out.read_text(encoding="utf-8"))
    assert written_report["summary"] == report["summary"]
    assert len(written_report["records"]) == 4

    record_by_id = {record["source_id"]: record for record in written_report["records"]}
    assert Path(record_by_id["tower_case"]["artifacts"]["copied_source_path"]).exists()
    assert Path(record_by_id["atrium_case"]["artifacts"]["source_metadata_path"]).exists()
    assert record_by_id["bundle_case"]["zip_bundle"]["member_count"] == 2
    assert record_by_id["sensor_case"]["source_format"] == "csv_tables"


def test_collect_irregular_public_structures_accepts_catalog_source_records_and_remote_candidates(tmp_path: Path) -> None:
    source_dir = tmp_path / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)

    graph_path = source_dir / "tower_graph.json"
    graph_path.write_text("{\"nodes\": [], \"elements\": []}\n", encoding="utf-8")

    catalog = tmp_path / "irregular_structure_source_catalog.json"
    out_dir = tmp_path / "out"
    report_out = tmp_path / "irregular_structure_collection_report.json"
    _write_json(
        catalog,
        {
            "schema_version": "1.0",
            "source_records": [
                {
                    "source_id": "local_graph_case",
                    "source_name": "Local graph case",
                    "family_id": "twisted_tapered_tower",
                    "primary_format": "json_graph",
                    "source_urls": ["https://example.com/local-graph"],
                    "local_path": str(graph_path),
                },
                {
                    "source_id": "remote_only_case",
                    "source_name": "Remote only case",
                    "family_id": "bridge_skewed_support_span",
                    "primary_format": "mgt",
                    "source_urls": ["https://example.com/bridge.mgt"],
                },
            ],
        },
    )

    report = collect_irregular_public_structures(catalog, out_dir, report_out)

    assert report["contract_pass"] is True
    assert report["summary"]["source_count"] == 2
    assert report["summary"]["collected_count"] == 1
    assert report["summary"]["metadata_only_remote_candidate_count"] == 1
    assert report["summary"]["remote_reference_count"] == 1
    assert report["summary"]["format_counts"]["json_graph"] == 1
    assert report["summary"]["format_counts"]["mgt"] == 1

    records = {row["source_id"]: row for row in report["records"]}
    assert records["local_graph_case"]["status"] == "collected"
    assert records["remote_only_case"]["status"] == "metadata_only_remote_candidate"


def test_collect_irregular_public_structures_fetches_only_clear_remote_raw_assets(tmp_path: Path) -> None:
    source_dir = tmp_path / "remote"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_mgt = source_dir / "bridge_case.mgt"
    raw_mgt.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    landing = source_dir / "download"
    landing.write_text("not a direct asset\n", encoding="utf-8")

    server, base_url = _serve_directory(source_dir)
    try:
        catalog = tmp_path / "irregular_structure_source_catalog.json"
        out_dir = tmp_path / "out"
        report_out = tmp_path / "irregular_structure_collection_report.json"
        _write_json(
            catalog,
            {
                "schema_version": "1.0",
                "source_records": [
                    {
                        "source_id": "remote_raw_case",
                        "source_name": "Remote raw case",
                        "family_id": "curved_plan_bridge_torsion",
                        "primary_format": "mgt",
                        "url": f"{base_url}/bridge_case.mgt",
                        "source_urls": [f"{base_url}/bridge_case.mgt"],
                    },
                    {
                        "source_id": "remote_metadata_case",
                        "source_name": "Remote metadata case",
                        "family_id": "bridge_skewed_support_span",
                        "primary_format": "mgt",
                        "url": f"{base_url}/download",
                        "source_urls": [f"{base_url}/download"],
                    },
                ],
            },
        )

        report = collect_irregular_public_structures(catalog, out_dir, report_out)
    finally:
        server.shutdown()
        server.server_close()

    assert report["contract_pass"] is True
    assert report["summary"]["source_count"] == 2
    assert report["summary"]["collected_count"] == 1
    assert report["summary"]["metadata_only_remote_candidate_count"] == 1
    assert report["summary"]["remote_reference_count"] == 2
    assert report["summary"]["format_counts"]["mgt"] == 2

    records = {row["source_id"]: row for row in report["records"]}
    assert records["remote_raw_case"]["status"] == "collected"
    assert Path(records["remote_raw_case"]["artifacts"]["copied_source_path"]).read_text(encoding="utf-8") == "*NODE\n1,0,0,0\n"
    metadata = json.loads(Path(records["remote_raw_case"]["artifacts"]["source_metadata_path"]).read_text(encoding="utf-8"))
    assert metadata["download_mode"] == "remote_provider_asset"
    assert records["remote_metadata_case"]["status"] == "metadata_only_remote_candidate"


def test_collect_irregular_public_structures_uses_provider_metadata_hints_and_rejects_lfs_pointer(tmp_path: Path) -> None:
    source_dir = tmp_path / "remote"
    source_dir.mkdir(parents=True, exist_ok=True)
    github_tcl = source_dir / "ConstructBrace.tcl"
    github_tcl.write_text("model BasicBuilder -ndm 3 -ndf 6\n", encoding="utf-8")
    zenodo_ifc = source_dir / "tower.ifc"
    zenodo_ifc.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    designsafe_pdf = source_dir / "reference.pdf"
    designsafe_pdf.write_bytes(b"%PDF-1.4\n%mock\n")
    lfs_pointer = source_dir / "lfs.ifc"
    lfs_pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:deadbeef\nsize 123\n",
        encoding="utf-8",
    )

    server, base_url = _serve_directory(source_dir)
    try:
        catalog = tmp_path / "irregular_structure_source_catalog.json"
        out_dir = tmp_path / "out"
        report_out = tmp_path / "irregular_structure_collection_report.json"
        _write_json(
            catalog,
            {
                "schema_version": "1.0",
                "source_records": [
                    {
                        "source_id": "github_hint_case",
                        "source_name": "GitHub metadata-hint case",
                        "family_id": "discontinuous_braced_frame_tower",
                        "primary_format": "tcl",
                        "source_urls": [f"{base_url}/github/project"],
                        "metadata": {
                            "github_download_url": f"{base_url}/ConstructBrace.tcl",
                        },
                    },
                    {
                        "source_id": "zenodo_hint_case",
                        "source_name": "Zenodo metadata-hint case",
                        "family_id": "twisted_tapered_tower",
                        "primary_format": "ifc",
                        "source_urls": [f"{base_url}/records/12345"],
                        "metadata": {
                            "zenodo_download_url": f"{base_url}/tower.ifc?download=1",
                        },
                    },
                    {
                        "source_id": "designsafe_hint_case",
                        "source_name": "DesignSafe metadata-hint case",
                        "family_id": "soft_story_podium_tower",
                        "primary_format": "report_pdf",
                        "source_urls": [f"{base_url}/designsafe/browser/case"],
                        "metadata": {
                            "designsafe_download_url": f"{base_url}/reference.pdf",
                        },
                    },
                    {
                        "source_id": "github_lfs_case",
                        "source_name": "GitHub LFS pointer case",
                        "family_id": "reentrant_corner_tower",
                        "primary_format": "ifc",
                        "source_urls": [f"{base_url}/github/lfs/blob"],
                        "metadata": {
                            "github_download_url": f"{base_url}/lfs.ifc",
                        },
                    },
                ],
            },
        )

        report = collect_irregular_public_structures(catalog, out_dir, report_out)
    finally:
        server.shutdown()
        server.server_close()

    assert report["contract_pass"] is True
    assert report["summary"]["source_count"] == 4
    assert report["summary"]["collected_count"] == 3
    assert report["summary"]["metadata_only_remote_candidate_count"] == 1

    records = {row["source_id"]: row for row in report["records"]}
    assert records["github_hint_case"]["status"] == "collected"
    assert records["zenodo_hint_case"]["status"] == "collected"
    assert records["designsafe_hint_case"]["status"] == "collected"
    assert records["github_lfs_case"]["status"] == "metadata_only_remote_candidate"
    assert records["github_lfs_case"]["remote_fetch_note"] == "git_lfs_pointer_detected"


def test_github_candidate_urls_accepts_contents_api_list(monkeypatch) -> None:
    def _fake_fetch_remote_json(_: str) -> list[dict[str, str]]:
        return [
            {"download_url": "https://raw.githubusercontent.com/example/repo/main/README.md"},
            {"download_url": "https://raw.githubusercontent.com/example/repo/main/irregular.ifc"},
        ]

    monkeypatch.setattr(collector_module, "_fetch_remote_json", _fake_fetch_remote_json)
    urls = collector_module._github_candidate_urls(
        "https://api.github.com/repos/example/repo/contents/models",
        "ifc",
    )
    assert urls == ["https://raw.githubusercontent.com/example/repo/main/irregular.ifc"]
