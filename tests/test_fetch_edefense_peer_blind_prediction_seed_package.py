import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PHASE1_DIR = Path(__file__).resolve().parents[1] / "implementation/phase1"
if str(PHASE1_DIR) not in sys.path:
    sys.path.insert(0, str(PHASE1_DIR))

import fetch_edefense_peer_blind_prediction_seed_package as fetcher  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: bytes, *, status: int = 200, content_type: str = "application/octet-stream") -> None:
        self._payload = payload
        self.status = status
        self.headers = {"Content-Type": content_type}

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_target_name_normalizes_spaces() -> None:
    assert (
        fetcher._target_name("https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Construction%20Drawings.pdf")
        == "Construction_Drawings.pdf"
    )


def test_probe_rows_prefer_expanded_direct_download_rows() -> None:
    payload = {
        "direct_download_rows": [
            {
                "url": "https://example.test/Experimentalresults.xlsx",
                "artifact_class": "measured_response_dataset",
                "anchor_text": "Experimental Results",
                "page_sources": ["https://example.test/results"],
                "reachable": True,
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "content_length": 35158,
                "last_modified": "Thu, 25 Jan 2018 16:02:34 GMT",
            },
            {
                "url": "https://example.test/QA_blindprediction-1.pdf",
                "artifact_class": "measured_response_support_doc",
                "anchor_text": "Questions & Answers",
                "page_sources": ["https://example.test/qa"],
                "reachable": True,
                "content_type": "application/pdf",
                "content_length": 99898,
                "last_modified": "Thu, 24 Apr 2025 20:12:14 GMT",
            },
        ],
        "direct_downloads": [
            "https://example.test/Experimentalresults.xlsx",
            "https://example.test/QA_blindprediction-1.pdf",
        ],
    }

    rows = fetcher._probe_rows(payload)

    assert len(rows) == 2
    assert rows[0]["artifact_class"] == "measured_response_dataset"
    assert rows[0]["anchor_text"] == "Experimental Results"
    assert rows[0]["page_sources"] == ["https://example.test/results"]
    assert rows[1]["artifact_class"] == "measured_response_support_doc"
    assert rows[1]["probe_content_type"] == "application/pdf"


def test_assign_target_names_resolves_duplicate_basenames_stably() -> None:
    planned, collision_count = fetcher._assign_target_names(
        [
            {"url": "https://example.test/one/Results.pdf", "artifact_class": "measured_response_support_doc"},
            {"url": "https://mirror.test/two/Results.pdf", "artifact_class": "official_reference_doc"},
        ]
    )

    assert collision_count == 1
    assert planned[0]["target_name"] == "Results.pdf"
    assert planned[1]["target_name"].startswith("Results.")
    assert planned[1]["target_name"].endswith(".pdf")
    assert planned[1]["target_name"] != planned[0]["target_name"]


def test_fetch_script_reports_existing_and_downloaded_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    probe_json = tmp_path / "probe.json"
    out_dir = tmp_path / "landing"
    report_out = tmp_path / "fetch_report.json"
    existing_name = "Existing_Drawing.pdf"
    existing_path = out_dir / existing_name
    existing_path.parent.mkdir(parents=True, exist_ok=True)
    existing_path.write_bytes(b"existing-pdf")

    probe_json.write_text(
        json.dumps(
            {
                "direct_download_rows": [
                    {
                        "url": f"https://example.test/{existing_name}",
                        "artifact_class": "geometry_input",
                        "anchor_text": "Existing Drawing",
                        "page_sources": ["https://example.test/input"],
                        "reachable": True,
                        "content_type": "application/pdf",
                        "content_length": len(b"existing-pdf"),
                        "last_modified": "Thu, 24 Apr 2025 20:12:14 GMT",
                    },
                    {
                        "url": "https://example.test/Experimentalresults.xlsx",
                        "artifact_class": "measured_response_dataset",
                        "anchor_text": "Experimental Results",
                        "page_sources": ["https://example.test/results"],
                        "reachable": True,
                        "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "content_length": 35158,
                        "last_modified": "Thu, 25 Jan 2018 16:02:34 GMT",
                    },
                    {
                        "url": "https://example.test/QA_blindprediction-1.pdf",
                        "artifact_class": "measured_response_support_doc",
                        "anchor_text": "Questions & Answers",
                        "page_sources": ["https://example.test/qa"],
                        "reachable": True,
                        "content_type": "application/pdf",
                        "content_length": 99898,
                        "last_modified": "Thu, 24 Apr 2025 20:12:14 GMT",
                    },
                ],
                "direct_downloads": [
                    f"https://example.test/{existing_name}",
                    "https://example.test/Experimentalresults.xlsx",
                    "https://example.test/QA_blindprediction-1.pdf",
                ]
            }
        ),
        encoding="utf-8",
    )

    def _fake_urlopen(req, timeout=0):  # noqa: ANN001
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url == "https://example.test/Experimentalresults.xlsx":
            return _FakeResponse(
                b"xlsx-bytes",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        if url == "https://example.test/QA_blindprediction-1.pdf":
            return _FakeResponse(b"pdf-bytes", content_type="application/pdf")
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(
        fetcher,
        "argparse",
        SimpleNamespace(
            ArgumentParser=lambda: SimpleNamespace(
                add_argument=lambda *args, **kwargs: None,
                parse_args=lambda: SimpleNamespace(
                    probe_json=str(probe_json),
                    out_dir=str(out_dir),
                    report_out=str(report_out),
                ),
            )
        ),
    )

    fetcher.main()

    payload = json.loads(report_out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["requested_url_count"] == 3
    assert payload["summary"]["downloaded_count"] == 2
    assert payload["summary"]["existing_count"] == 1
    assert payload["summary"]["measured_response_dataset_count"] == 1
    assert payload["summary"]["measured_response_support_doc_count"] == 1
    assert payload["summary"]["artifact_class_counts"] == {
        "geometry_input": 1,
        "measured_response_dataset": 1,
        "measured_response_support_doc": 1,
    }
    assert payload["summary"]["stable_target_collision_count"] == 0

    rows = payload["download_rows"]
    assert rows[0]["fetch_state"] == "existing"
    assert rows[0]["status"] == "existing"
    assert rows[0]["artifact_class"] == "geometry_input"
    assert rows[0]["target"].endswith(existing_name)
    assert rows[1]["downloaded"] is True
    assert rows[1]["artifact_class"] == "measured_response_dataset"
    assert rows[1]["target_name"] == "Experimentalresults.xlsx"
    assert rows[1]["content_type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert Path(rows[1]["target"]).read_bytes() == b"xlsx-bytes"
    assert rows[2]["downloaded"] is True
    assert rows[2]["artifact_class"] == "measured_response_support_doc"
    assert rows[2]["target_name"] == "QA_blindprediction-1.pdf"
    assert Path(rows[2]["target"]).read_bytes() == b"pdf-bytes"
