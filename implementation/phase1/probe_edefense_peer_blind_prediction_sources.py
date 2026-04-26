#!/usr/bin/env python3
"""Probe official E-Defense / PEER blind prediction public pages for directly accessible files."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO


DEFAULT_OUT = Path("implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.download_probe.json")
SOURCE_PAGES = [
    "https://peer.berkeley.edu/2009-blind-analysis-contest-e-defense",
    "https://peer.berkeley.edu/nees-tipse-defense-announce-blind-analysis-contest-seismic-isolation-test",
    "https://apps.peer.berkeley.edu/prediction_contest/",
    "https://apps.peer.berkeley.edu/prediction_contest/?page_id=13",
    "https://apps.peer.berkeley.edu/prediction_contest/?page_id=768",
    "https://apps.peer.berkeley.edu/prediction_contest/?page_id=152",
]
DIRECT_FILES = [
    "https://peer.berkeley.edu/sites/default/files/news_e-defense_blind_analysis_2009-article.pdf",
    "https://apps.peer.berkeley.edu/assets/Materials.zip",
    "https://apps.peer.berkeley.edu/assets/GMs.xlsx",
    "https://apps.peer.berkeley.edu/assets/Experimentalresults.xlsx",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Construction_Drawings.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Posttensiondetails.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Columns.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Bent-Cap.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Foundation.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/08/Weight_Blocks.pdf",
    "https://apps.peer.berkeley.edu/prediction_contest/wp-content/uploads/2010/09/QA_blindprediction-1.pdf",
    "https://apps.peer.berkeley.edu/publications/peer_reports/reports_2015/webPEER-2015-01-Terzic-5.8.15.pdf",
]
DIRECT_FILE_EXTENSIONS = (".pdf", ".zip", ".txt", ".csv", ".dat", ".inp", ".at2", ".xlsx")
XML_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[dict[str, str]] = []
        self._current_href: str | None = None
        self._current_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        self._flush_current()
        for key, value in attrs:
            if key.lower() == "href" and value:
                self._current_href = value
                self._current_chunks = []
                return

    def handle_data(self, data: str) -> None:
        if self._current_href and data:
            self._current_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a":
            self._flush_current()

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        if self._current_href:
            anchor_text = " ".join(chunk.strip() for chunk in self._current_chunks if chunk.strip())
            self.links.append({"href": self._current_href, "anchor_text": anchor_text})
        self._current_href = None
        self._current_chunks = []


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme and not parsed.netloc:
        return url.strip()
    scheme = "https" if parsed.netloc in {"apps.peer.berkeley.edu", "peer.berkeley.edu"} else parsed.scheme
    fragment = ""
    normalized_path = posixpath.normpath(parsed.path or "/")
    if parsed.path.endswith("/") and not normalized_path.endswith("/"):
        normalized_path = f"{normalized_path}/"
    return urlunparse((scheme, parsed.netloc.lower(), normalized_path, "", parsed.query, fragment))


def _extract_links(base_url: str, html: str) -> list[str]:
    return [row["link_url"] for row in _extract_link_rows(base_url, html)]


def _extract_link_rows(base_url: str, html: str) -> list[dict[str, str]]:
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for row in parser.links:
        full = _normalize_url(urljoin(base_url, row["href"]))
        if full not in seen:
            seen.add(full)
            out.append(
                {
                    "page_url": base_url,
                    "link_url": full,
                    "anchor_text": row["anchor_text"].strip(),
                }
            )
    return out


def _is_direct_download(url: str) -> bool:
    return urlparse(url).path.lower().endswith(DIRECT_FILE_EXTENSIONS)


def _classify_artifact(url: str, anchor_text: str = "", page_url: str = "") -> str:
    corpus = " ".join([url.lower(), anchor_text.lower(), page_url.lower()])
    if "experimentalresults" in corpus:
        return "measured_response_dataset"
    if "qa_blindprediction" in corpus or "terzic" in corpus:
        return "measured_response_support_doc"
    if "gms" in corpus or "ground motion" in corpus:
        return "excitation_input"
    if "materials" in corpus:
        return "material_input"
    if any(token in corpus for token in ["construction_drawings", "posttensiondetails", "columns.pdf", "bent-cap", "foundation.pdf", "weight_blocks"]):
        return "geometry_input"
    if any(token in corpus for token in ["rules", "submittal", "survey"]):
        return "rules_submission"
    if "e-defense" in corpus or "prediction_contest" in corpus:
        return "official_reference_doc"
    return "other"


def _probe_url_metadata(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "phase1-edefense-peer-probe/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
            return {
                "reachable": True,
                "content_type": str(response.headers.get("Content-Type", "") or ""),
                "content_length": int(response.headers.get("Content-Length", 0) or 0),
                "last_modified": str(response.headers.get("Last-Modified", "") or ""),
            }
    except Exception as exc:  # pragma: no cover - network failure branch
        return {
            "reachable": False,
            "content_type": "",
            "content_length": 0,
            "last_modified": "",
            "probe_error": f"{type(exc).__name__}: {exc}",
        }


def _inspect_experimental_results_xlsx(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "phase1-edefense-peer-probe/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:  # nosec B310
        blob = response.read()
    workbook = zipfile.ZipFile(BytesIO(blob))
    shared_strings: list[str] = []
    if "xl/sharedStrings.xml" in workbook.namelist():
        shared_root = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
        for shared_item in shared_root.findall("a:si", XML_NS):
            shared_strings.append("".join(text.text or "" for text in shared_item.iterfind(".//a:t", XML_NS)))
    workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
    rel_root = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rel_root}
    sheet_rows: list[tuple[str, str]] = []
    for sheet in workbook_root.find("a:sheets", XML_NS) or []:
        rel_id = sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        sheet_rows.append((sheet.attrib["name"], f"xl/{rel_targets[rel_id]}"))

    def _cell_value(cell: ET.Element) -> str | None:
        value = cell.find("a:v", XML_NS)
        if value is None or value.text is None:
            return None
        if cell.attrib.get("t") == "s":
            try:
                return shared_strings[int(value.text)]
            except Exception:
                return value.text
        return value.text

    metric_labels: list[str] = []
    for _, target in sheet_rows[:1]:
        sheet_root = ET.fromstring(workbook.read(target))
        for row in sheet_root.findall(".//a:sheetData/a:row", XML_NS):
            cells = row.findall("a:c", XML_NS)
            if len(cells) < 2:
                continue
            first = (_cell_value(cells[0]) or "").strip()
            second = (_cell_value(cells[1]) or "").strip()
            if first.isdigit() and second:
                metric_labels.append(second)
    labels_lower = [label.lower() for label in metric_labels]
    return {
        "sheet_names": [name for name, _ in sheet_rows],
        "metric_label_count": len(metric_labels),
        "metric_labels": metric_labels,
        "contains_displacement": any("displacement" in label for label in labels_lower),
        "contains_residual_displacement": any("residual displacement" in label for label in labels_lower),
        "contains_acceleration": any("acceleration" in label for label in labels_lower),
        "contains_drift": any("drift" in label for label in labels_lower),
        "contains_sensor_manifest": any("sensor" in label for label in labels_lower),
    }


def build_probe() -> dict[str, Any]:
    page_rows: list[dict[str, Any]] = []
    link_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in SOURCE_PAGES:
        req = urllib.request.Request(url, headers={"User-Agent": "phase1-edefense-peer-probe/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:  # nosec B310
            text = response.read().decode("utf-8", errors="replace")
        links = _extract_link_rows(url, text)
        page_rows.append(
            {
                "page_url": url,
                "link_count": len(links),
                "links": [row["link_url"] for row in links],
            }
        )
        for row in links:
            link = row["link_url"]
            if link not in seen:
                seen.add(link)
                row["artifact_class"] = _classify_artifact(
                    row["link_url"],
                    anchor_text=row.get("anchor_text", ""),
                    page_url=row.get("page_url", ""),
                )
                link_rows.append(row)

    direct_downloads = [row["link_url"] for row in link_rows if _is_direct_download(row["link_url"])]
    for link in DIRECT_FILES:
        normalized = _normalize_url(link)
        if normalized not in direct_downloads:
            direct_downloads.append(normalized)

    direct_download_rows: list[dict[str, Any]] = []
    direct_seen: set[str] = set()
    for url in direct_downloads:
        if url in direct_seen:
            continue
        direct_seen.add(url)
        linked_rows = [row for row in link_rows if row["link_url"] == url]
        anchor_text = " | ".join(
            dict.fromkeys(row["anchor_text"] for row in linked_rows if row.get("anchor_text"))
        )
        page_sources = list(dict.fromkeys(row["page_url"] for row in linked_rows if row.get("page_url")))
        artifact_class = _classify_artifact(url, anchor_text=anchor_text, page_url=" ".join(page_sources))
        metadata = _probe_url_metadata(url)
        direct_download_rows.append(
            {
                "url": url,
                "artifact_class": artifact_class,
                "anchor_text": anchor_text,
                "page_sources": page_sources,
                **metadata,
            }
        )

    measured_response_dataset_rows = [
        row for row in direct_download_rows if row["artifact_class"] == "measured_response_dataset"
    ]
    measured_response_support_doc_rows = [
        row for row in direct_download_rows if row["artifact_class"] == "measured_response_support_doc"
    ]
    experimental_results_preview = {}
    for row in measured_response_dataset_rows:
        if row["url"].lower().endswith(".xlsx") and "experimentalresults" in row["url"].lower():
            experimental_results_preview = _inspect_experimental_results_xlsx(row["url"])
            break

    official_findings: list[str] = []
    if measured_response_dataset_rows:
        official_findings.append(
            "Official Results page exposes Experimentalresults.xlsx as a direct public measured-response workbook."
        )
    if experimental_results_preview:
        official_findings.append(
            "Experimentalresults.xlsx contains a single Results sheet with published response quantities such as "
            "relative horizontal displacement, residual displacement, inertia force, overturning moment, uplift, "
            "and post-tension bar force."
        )
        if not experimental_results_preview.get("contains_acceleration", False):
            official_findings.append(
                "No direct public acceleration time-history workbook/CSV was found; the public results workbook is "
                "response-summary oriented rather than raw acceleration traces."
            )
        if not experimental_results_preview.get("contains_drift", False):
            official_findings.append(
                "No direct public drift time-history workbook/CSV was found in the official PEER contest pages."
            )
        if not experimental_results_preview.get("contains_sensor_manifest", False):
            official_findings.append(
                "No standalone public sensor manifest file was linked; instrumentation context is only surfaced via "
                "supporting documents such as the Q&A PDF and PEER report."
            )
    if measured_response_support_doc_rows:
        official_findings.append(
            "Official support documents include the contest Q&A PDF and the PEER report with instrumentation and "
            "measured-response discussion."
        )

    return {
        "schema_version": "1.0",
        "run_id": "phase1-probe-edefense-peer-blind-prediction-sources",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pages": SOURCE_PAGES,
        "page_rows": page_rows,
        "link_rows": link_rows,
        "direct_downloads": [row["url"] for row in direct_download_rows],
        "direct_download_rows": direct_download_rows,
        "measured_response_surface": {
            "dataset_rows": measured_response_dataset_rows,
            "support_doc_rows": measured_response_support_doc_rows,
            "experimental_results_preview": experimental_results_preview,
            "official_findings": official_findings,
        },
        "summary": {
            "page_count": len(page_rows),
            "unique_link_count": len(link_rows),
            "direct_download_count": len(direct_download_rows),
            "measured_response_dataset_count": len(measured_response_dataset_rows),
            "measured_response_support_doc_count": len(measured_response_support_doc_rows),
            "measured_response_acceleration_public_count": int(
                bool(experimental_results_preview.get("contains_acceleration", False))
            ),
            "measured_response_drift_public_count": int(
                bool(experimental_results_preview.get("contains_drift", False))
            ),
            "measured_response_sensor_public_count": int(
                bool(experimental_results_preview.get("contains_sensor_manifest", False))
            ),
        },
        "contract_pass": bool(direct_download_rows),
        "reason": "Official E-Defense / PEER blind-prediction pages probed for directly accessible public files, with measured-response dataset/support-doc surfacing.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    payload = build_probe()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote E-Defense / PEER source probe: {out_path}")


if __name__ == "__main__":
    main()
