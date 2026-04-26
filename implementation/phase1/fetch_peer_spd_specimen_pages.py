#!/usr/bin/env python3
"""Fetch and parse selected PEER SPD specimen pages for hinge benchmark intake."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import time
from typing import Any
from urllib.request import Request, urlopen


RUN_ID = "phase1-fetch-peer-spd-specimen-pages"
SCHEMA_VERSION = "1.0"

REASONS = {
    "PASS": "Selected PEER SPD specimen pages were fetched and parsed into raw intake bundles.",
    "ERR_CANDIDATES_INVALID": "PEER SPD seed candidate report is missing or invalid.",
    "ERR_FETCH_FAILED": "One or more selected specimen pages could not be fetched.",
    "ERR_PARSE_FAILED": "One or more specimen pages was fetched but could not be parsed into section metadata.",
}


class _SpecimenPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._title_chunks: list[str] = []

        self.sections: dict[str, dict[str, str]] = {}
        self.current_section = "Specimen Information"
        self.current_row_key = ""
        self._current_td_chunks: list[str] = []
        self._current_td_link_hrefs: list[str] = []
        self._captured_tds: list[tuple[str, list[str]]] = []
        self._in_td = False
        self._td_is_section = False
        self._in_strong = False
        self._strong_chunks: list[str] = []
        self._current_href: str | None = None

        self.resource_links: list[dict[str, str]] = []
        self.all_links: list[dict[str, str]] = []

    def _flush_td(self) -> None:
        if not self._in_td and not self._current_td_chunks and not self._current_td_link_hrefs:
            return
        text = " ".join("".join(self._current_td_chunks).replace("\xa0", " ").split()).strip()
        self._captured_tds.append((text, list(self._current_td_link_hrefs)))
        if self._td_is_section and self._strong_chunks:
            section = " ".join("".join(self._strong_chunks).split()).strip()
            if section:
                self.current_section = section
                self.sections.setdefault(section, {})
        self._in_td = False
        self._current_td_chunks = []
        self._current_td_link_hrefs = []
        self._td_is_section = False

    def _flush_tr(self) -> None:
        if len(self._captured_tds) >= 2:
            key = self._captured_tds[0][0].rstrip(":").strip()
            value = self._captured_tds[1][0].strip()
            if key and value:
                section_map = self.sections.setdefault(self.current_section, {})
                section_map[key] = value
                for href in self._captured_tds[1][1]:
                    link_row = {"href": href, "text": value, "section": self.current_section, "row_key": key}
                    self.all_links.append(link_row)
                    if key.lower() == "resources":
                        self.resource_links.append(link_row)
        self._captured_tds = []
        self.current_row_key = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
            self._title_chunks = []
        elif tag == "tr":
            self._flush_td()
            self._flush_tr()
        elif tag == "td":
            self._in_td = True
            self._current_td_chunks = []
            self._current_td_link_hrefs = []
            self._td_is_section = attr_map.get("colspan", "") == "2"
        elif tag == "strong":
            self._in_strong = True
            self._strong_chunks = []
        elif tag == "a":
            self._current_href = attr_map.get("href", "")
            if self._in_td and self._current_href:
                self._current_td_link_hrefs.append(self._current_href)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
            self.title = "".join(self._title_chunks).strip()
        elif tag == "strong":
            self._in_strong = False
        elif tag == "td":
            self._flush_td()
        elif tag == "tr":
            self._flush_td()
            self._flush_tr()
        elif tag == "a":
            self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_chunks.append(data)
        if self._in_td:
            self._current_td_chunks.append(data)
        if self._in_strong:
            self._strong_chunks.append(data)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _fetch_text(url: str) -> tuple[str | None, str]:
    last_error = ""
    for _attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 Codex/PEER-SPD-Fetch"})
            with urlopen(req, timeout=20) as response:
                return response.read().decode("utf-8", "ignore"), ""
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.5)
    return None, last_error


def _select_rows(candidate_report: dict[str, Any], allowed_seed_ids: set[str]) -> list[dict[str, Any]]:
    rows = candidate_report.get("rows")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        seed_id = str(row.get("seed_id", "")).strip()
        if allowed_seed_ids and seed_id not in allowed_seed_ids:
            continue
        selected = row.get("selected_candidate")
        if not isinstance(selected, dict) or not str(selected.get("specimen_display_url", "")).strip():
            continue
        out.append(row)
    return out


def _hysteresis_candidates(links: list[dict[str, str]]) -> list[dict[str, str]]:
    tokens = ("hyster", "cyclic", "load", "disp", "response", "force")
    out = []
    for link in links:
        hay = f"{link.get('href', '')} {link.get('text', '')}".lower()
        if any(token in hay for token in tokens):
            out.append(link)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", default="implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json")
    parser.add_argument("--seed-id", action="append", default=[])
    parser.add_argument("--out-dir", default="implementation/phase1/open_data/pbd_hinge/peer_spd_specimens")
    parser.add_argument("--out-report", default="implementation/phase1/open_data/pbd_hinge/peer_spd_specimen_pages_report.json")
    parser.add_argument("--prefer-cache", action=argparse.BooleanOptionalAction, default=False)
    args = parser.parse_args()

    candidate_report = _load_json(Path(args.candidates))
    seed_ids = {str(seed_id).strip() for seed_id in args.seed_id if str(seed_id).strip()}
    selected_rows = _select_rows(candidate_report, seed_ids)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not selected_rows:
        reason_code = "ERR_CANDIDATES_INVALID"
        payload = {
            "schema_version": SCHEMA_VERSION,
            "run_id": RUN_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "contract_pass": False,
            "reason_code": reason_code,
            "reason": REASONS[reason_code],
            "inputs": {"candidates": str(args.candidates), "seed_ids": sorted(seed_ids), "out_dir": str(out_dir)},
            "summary": {"selected_seed_count": 0, "fetch_pass_count": 0, "parse_pass_count": 0},
            "rows": [],
        }
        Path(args.out_report).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote PEER SPD specimen page report: {args.out_report}")
        return

    rows_out: list[dict[str, Any]] = []
    fetch_failures = 0
    parse_failures = 0
    for row in selected_rows:
        seed_id = str(row.get("seed_id", "")).strip()
        holdout_split = str(row.get("holdout_split", "")).strip()
        selected = row.get("selected_candidate") if isinstance(row.get("selected_candidate"), dict) else {}
        specimen_id = str(selected.get("specimen_id", "")).strip()
        specimen_url = str(selected.get("specimen_display_url", "")).strip()
        html_path = out_dir / f"{seed_id}.specimen_page.html"
        raw_json_path = out_dir / f"{seed_id}.specimen_page.json"
        html_text: str | None = None
        error = ""
        cache_reused = False
        if bool(args.prefer_cache) and html_path.exists():
            html_text = html_path.read_text(encoding="utf-8", errors="ignore")
            cache_reused = True
        else:
            html_text, error = _fetch_text(specimen_url)
        fetch_pass = html_text is not None
        parse_pass = False
        sections: dict[str, dict[str, str]] = {}
        resource_links: list[dict[str, str]] = []
        all_links: list[dict[str, str]] = []
        title = ""
        if not fetch_pass and html_path.exists():
            html_text = html_path.read_text(encoding="utf-8", errors="ignore")
            fetch_pass = True
            cache_reused = True
        if fetch_pass and html_text is not None:
            html_path.write_text(html_text, encoding="utf-8")
            parser_impl = _SpecimenPageParser()
            parser_impl.feed(html_text)
            sections = parser_impl.sections
            resource_links = parser_impl.resource_links
            all_links = parser_impl.all_links
            title = parser_impl.title
            parse_pass = bool(title or sections)
            if parse_pass:
                raw_payload = {
                    "schema_version": SCHEMA_VERSION,
                    "run_id": RUN_ID,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "seed_id": seed_id,
                    "holdout_split": holdout_split,
                    "specimen_id": specimen_id,
                    "specimen_display_url": specimen_url,
                    "source_origin_class": "official_external_benchmark",
                    "selection_mode": "properties_based_preselection_plus_specimen_page_snapshot",
                    "page_title": title,
                    "sections": sections,
                    "resource_links": resource_links,
                    "hysteresis_link_candidates": _hysteresis_candidates(resource_links or all_links),
                    "contract_pass": True,
                    "reason_code": "PASS",
                }
                raw_json_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if not fetch_pass:
            fetch_failures += 1
        elif not parse_pass:
            parse_failures += 1
        rows_out.append(
            {
                "seed_id": seed_id,
                "holdout_split": holdout_split,
                "specimen_id": specimen_id,
                "specimen_name": str(selected.get("specimen_name", "")),
                "specimen_display_url": specimen_url,
                "html_snapshot_path": str(html_path),
                "raw_json_path": str(raw_json_path),
                "fetch_pass": fetch_pass,
                "parse_pass": parse_pass,
                "page_title": title,
                "resource_link_count": int(len(resource_links)),
                "hysteresis_link_candidate_count": int(len(_hysteresis_candidates(resource_links or all_links))),
                "error": error,
                "cache_reused": cache_reused,
            }
        )

    reason_code = "PASS"
    if fetch_failures > 0:
        reason_code = "ERR_FETCH_FAILED"
    elif parse_failures > 0:
        reason_code = "ERR_PARSE_FAILED"

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": RUN_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contract_pass": bool(reason_code == "PASS"),
        "reason_code": reason_code,
        "reason": REASONS[reason_code],
        "inputs": {
            "candidates": str(args.candidates),
            "seed_ids": sorted(seed_ids),
            "out_dir": str(out_dir),
            "out_report": str(args.out_report),
        },
        "summary": {
            "selected_seed_count": int(len(rows_out)),
            "fetch_pass_count": int(sum(1 for row in rows_out if bool(row.get("fetch_pass", False)))),
            "parse_pass_count": int(sum(1 for row in rows_out if bool(row.get("parse_pass", False)))),
            "cache_reuse_count": int(sum(1 for row in rows_out if bool(row.get("cache_reused", False)))),
            "resource_link_count_total": int(sum(int(row.get("resource_link_count", 0) or 0) for row in rows_out)),
            "hysteresis_link_candidate_count_total": int(sum(int(row.get("hysteresis_link_candidate_count", 0) or 0) for row in rows_out)),
        },
        "rows": rows_out,
    }
    out_report = Path(args.out_report)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote PEER SPD specimen page report: {args.out_report}")


if __name__ == "__main__":
    main()
