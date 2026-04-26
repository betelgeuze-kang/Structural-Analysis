#!/usr/bin/env python3
"""Probe official Canton Tower reduced SHM benchmark pages and emit a download plan."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import ssl
from typing import Any
from urllib.parse import urljoin
import urllib.request


RUN_ID = "phase1-probe-canton-tower-reduced-shm-sources"
DEFAULT_OUT = Path("implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.download_probe.json")
SOURCE_PAGES = [
    "https://polyucee.hk/ceyxia/benchmark/benchmark.htm",
    "https://polyucee.hk/ceyxia/benchmark/tvtower.htm",
    "https://polyucee.hk/ceyxia/benchmark/task_i.htm",
]


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _fetch(url: str, *, insecure_ssl: bool) -> str:
    context = ssl._create_unverified_context() if insecure_ssl else None
    with urllib.request.urlopen(url, timeout=30, context=context) as response:  # nosec B310
        return response.read().decode("utf-8", errors="replace")


def _extract_links(base_url: str, html: str) -> list[str]:
    parser = _HrefParser()
    parser.feed(html)
    seen: set[str] = set()
    out: list[str] = []
    for href in parser.hrefs:
        full = urljoin(base_url, href)
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def _classify(url: str) -> str:
    lower = url.lower()
    if lower.endswith("system_matrices.mat"):
        return "system_matrices"
    if lower.endswith(".pdf"):
        return "benchmark_docs"
    if lower.endswith(".zip") or lower.endswith(".csv") or lower.endswith(".txt"):
        return "measured_response"
    return "other"


def build_probe(*, insecure_ssl: bool = True) -> dict[str, Any]:
    page_rows: list[dict[str, Any]] = []
    all_links: list[str] = []
    seen: set[str] = set()

    for url in SOURCE_PAGES:
        html = _fetch(url, insecure_ssl=insecure_ssl)
        links = _extract_links(url, html)
        page_rows.append(
            {
                "page_url": url,
                "link_count": len(links),
                "links": links,
            }
        )
        for link in links:
            if link not in seen:
                seen.add(link)
                all_links.append(link)

    artifact_groups = {
        "system_matrices": [],
        "benchmark_docs": [],
        "measured_response": [],
        "other": [],
    }
    for link in all_links:
        artifact_groups[_classify(link)].append(link)

    recommended_downloads = {
        "minimum_viable_package": [
            link
            for link in all_links
            if any(
                token in link.lower()
                for token in (
                    "phase_i_measurement%20description.pdf",
                    "phase_i_fe_model_description.pdf",
                    "system_matrices.mat",
                    "phase%20i%20data_all.zip",
                )
            )
        ],
        "hourly_acceleration_archives": [
            link for link in all_links if "accdata_" in link.lower() and link.lower().endswith(".zip")
        ],
        "auxiliary_environmental_channels": [
            link
            for link in all_links
            if any(token in link.lower() for token in ("wind%20direction", "wind%20speed", "temperature%2024%20hours"))
        ],
    }

    return {
        "schema_version": "1.0",
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_pages": SOURCE_PAGES,
        "ssl_mode": "insecure_unverified_context" if insecure_ssl else "default",
        "page_rows": page_rows,
        "artifact_groups": artifact_groups,
        "recommended_downloads": recommended_downloads,
        "summary": {
            "page_count": len(page_rows),
            "unique_link_count": len(all_links),
            "system_matrices_count": len(artifact_groups["system_matrices"]),
            "benchmark_docs_count": len(artifact_groups["benchmark_docs"]),
            "measured_response_count": len(artifact_groups["measured_response"]),
        },
        "contract_pass": bool(artifact_groups["system_matrices"] and artifact_groups["benchmark_docs"] and artifact_groups["measured_response"]),
        "reason": "Official Canton Tower benchmark pages probed and grouped into a concrete download plan.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--default-ssl", action="store_true", help="Use default SSL verification instead of the unverified fallback.")
    args = parser.parse_args()

    payload = build_probe(insecure_ssl=not bool(args.default_ssl))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote Canton Tower source probe: {out_path}")


if __name__ == "__main__":
    main()
