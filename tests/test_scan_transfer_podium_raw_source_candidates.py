import json

from implementation.phase1.scan_transfer_podium_raw_source_candidates import (
    build_transfer_podium_raw_source_scan_payload,
)


def test_build_transfer_podium_raw_source_scan_payload_extracts_raw_suffix_candidates() -> None:
    ledger = {
        "official_task_report_url": "https://peer.example/task12.pdf",
        "official_final_report_url": "https://peer.example/final.pdf",
        "publication_whitelist_scan_terms": ["supplement", "appendix", "publication", "research"],
        "reference_pdf_recursive_suffixes": [".zip", ".tcl"],
        "reference_pdf_recursive_hunt_patterns": [
            {
                "pattern_id": "task12_transfer_appendix",
                "filename_tokens": ["task12", "transfer", "appendix"],
            }
        ],
        "task12_publication_title_candidates": [{"title": "transfer podium appendix"}],
        "supplemental_zip_hunt_patterns": [
            {
                "regex": "(?i)(backstay|transfer[_ -]?diaphragm|transfer[_ -]?girder).*(model|benchmark|analysis).*(zip|tcl|inp|ifc)$"
            }
        ],
        "authors": [
            {
                "name": "John Wallace",
                "checked_subtargets": ["https://example.com/wallace/research.html"],
                "publication_cv_candidates": [
                    {
                        "url": "https://example.com/wallace/publications.html",
                        "kind": "research_page",
                        "whitelist_suffixes": [".pdf", ".zip", ".tcl"],
                        "whitelist_keywords": ["transfer", "podium", "task12"],
                        "follow_pdf_recursively": True,
                    }
                ],
                "targets": [
                    {"kind": "personal_page", "url": "https://example.com/wallace/"},
                    {"kind": "lab_site", "url": "https://example.com/lab/"},
                ],
            }
        ],
    }

    html_map = {
        "https://example.com/wallace/research.html": """
            <html><body>
            <a href=\"transfer_podium_task12.zip\">Task 12 transfer bundle</a>
            <a href=\"notes.pdf\">notes</a>
            <a href=\"supplemental.html\">Supplemental appendix</a>
            </body></html>
        """,
        "https://example.com/wallace/publications.html": """
            <html><body>
            <a href=\"supplemental/transfer_model.tcl\">OpenSees model</a>
            <a href=\"task12_report.pdf\">Task 12 report</a>
            </body></html>
        """,
        "https://example.com/wallace/supplemental.html": """
            <html><body>
            <a href=\"appendix/task12_transfer_model.inp\">Appendix model</a>
            </body></html>
        """,
        "https://example.com/wallace/": "<html><body><a href='cv.pdf'>CV</a></body></html>",
        "https://example.com/lab/": "<html><body><a href='project.html'>Project</a></body></html>",
    }

    def fake_fetch(url: str) -> dict:
        if url.endswith("task12_report.pdf"):
            return {
                "url": url,
                "status_code": 200,
                "content_type": "application/pdf",
                "text": "",
                "content": b"https://example.com/wallace/task12_transfer_appendix.zip",
            }
        if url.endswith("notes.pdf"):
            return {
                "url": url,
                "status_code": 200,
                "content_type": "application/pdf",
                "text": "See supplemental archive https://example.com/files/backstay_transfer_model.zip and appendix/transfer_model.inp",
                "content": b"https://example.com/files/backstay_transfer_model.zip appendix/transfer_model.inp",
            }
        if url.endswith("task12_transfer_appendix.zip"):
            return {"url": url, "status_code": 200, "content_type": "application/zip", "text": "", "content": b"zip"}
        if url.endswith(".pdf"):
            return {"url": url, "status_code": 200, "content_type": "application/pdf", "text": "", "content": b""}
        return {
            "url": url,
            "status_code": 200,
            "content_type": "text/html; charset=utf-8",
            "text": html_map.get(url, "<html></html>"),
            "content": html_map.get(url, "<html></html>").encode(),
        }

    payload = build_transfer_podium_raw_source_scan_payload(ledger, fetcher=fake_fetch)

    assert payload["family_id"] == "transfer_podium_tower"
    assert payload["summary"]["seed_url_count"] >= 4
    assert payload["summary"]["scanned_record_count"] >= 4
    assert payload["summary"]["recursive_reference_scan_count"] >= 1
    assert payload["summary"]["whitelist_followup_scan_count"] >= 1
    assert payload["summary"]["guessed_pdf_url_count"] >= 1
    assert payload["summary"]["verified_native_package_found"] is False
    research_row = next(
        row for row in payload["records"] if row["url"] == "https://example.com/wallace/research.html"
    )
    assert research_row["candidate_count"] >= 3
    assert research_row["recursive_reference_scan_count"] >= 1
    assert research_row["whitelist_followup_scan_count"] >= 1
    assert any(
        candidate["discovered_from"] == "reference_pdf_text" and candidate["suffix"] == ".zip"
        for candidate in research_row["candidates"]
    )
    assert any(
        candidate["discovered_from"] == "whitelist_html_text" and candidate["suffix"] == ".inp"
        for candidate in research_row["candidates"]
    )
    assert any(
        "ledger_regex:" in " ".join(candidate.get("match_reasons", []))
        for candidate in research_row["candidates"]
    )
    publication_row = next(
        row for row in payload["records"] if row["url"] == "https://example.com/wallace/publications.html"
    )
    assert any(candidate["suffix"] == ".tcl" for candidate in publication_row["candidates"])
    assert publication_row["guessed_pdf_url_count"] >= 1
    assert any(candidate["href"].endswith("task12_transfer_appendix.zip") for candidate in publication_row["candidates"])
    assert any(pdf_row["guessed_url_count"] >= 1 for pdf_row in publication_row["reference_pdf_records"])
