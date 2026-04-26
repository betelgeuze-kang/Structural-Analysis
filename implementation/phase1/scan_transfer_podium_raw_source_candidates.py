#!/usr/bin/env python3
"""Scan transfer-podium author/lab/publication pages for raw-file suffix candidates."""

from __future__ import annotations

import io
import json
import re
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from urllib3.exceptions import InsecureRequestWarning


REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_JSON = REPO_ROOT / "implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.json"
OUT_JSON = REPO_ROOT / "implementation/phase1/open_data/irregular/transfer_podium_raw_source_candidate_scan_report.json"
OUT_MD = REPO_ROOT / "implementation/phase1/open_data/irregular/transfer_podium_raw_source_candidate_scan_report.md"
RAW_SUFFIXES = (".zip", ".tcl", ".inp", ".ifc", ".mgt", ".meb", ".pdf")
STRONG_SUFFIXES = (".zip", ".tcl", ".inp", ".ifc", ".mgt", ".meb")
KEYWORDS = (
    "transfer",
    "podium",
    "task12",
    "task_12",
    "tbi",
    "backstay",
    "corewall",
    "core-wall",
    "diaphragm",
    "girder",
    "tower",
    "building",
    "benchmark",
    "opensees",
    "supplement",
)
WHITELIST_HTML_HINTS = (
    "publication",
    "publications",
    "research",
    "peer",
    "report",
    "paper",
    "supplement",
    "appendix",
    "prototype",
    "opensees",
    "task12",
    "task_12",
    "tbi",
    "transfer",
    "podium",
    "backstay",
)
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
RELATIVE_FILE_RE = re.compile(
    r"(?i)(?:[\w./-]*?(?:transfer|podium|task[_ -]?12|tbi|backstay|core[-_ ]?wall|diaphragm|girder|benchmark|supplement)[\w./-]*\.(?:zip|tcl|inp|ifc|mgt|meb|pdf))"
)
PDF_SCAN_MAX_PAGES = 2
MAX_GUESSED_URLS_PER_PDF = 3
warnings.filterwarnings("ignore", category=InsecureRequestWarning)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_fetch(url: str) -> dict:
    response = requests.get(
        url,
        timeout=(2, 3),
        verify=False,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return {
        "url": response.url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "text": response.text,
        "content": response.content,
    }


def _default_probe(url: str) -> dict:
    response = requests.head(
        url,
        timeout=(0.5, 0.75),
        verify=False,
        allow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return {
        "url": response.url,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", ""),
        "text": "",
        "content": b"",
    }


def _collect_seed_urls(ledger: dict) -> list[dict]:
    seeds: list[dict] = []
    seen: dict[str, dict] = {}

    def add(
        url: str,
        source_kind: str,
        owner: str,
        note: str = "",
        whitelist_suffixes: list[str] | None = None,
        whitelist_keywords: list[str] | None = None,
        follow_pdf_recursively: bool | None = None,
    ) -> None:
        clean = str(url or "").strip()
        if not clean:
            return
        existing = seen.get(clean)
        if existing is not None:
            existing["note"] = existing.get("note") or note
            existing["whitelist_suffixes"] = sorted(
                set(existing.get("whitelist_suffixes", []) or [])
                | set(list(whitelist_suffixes or []))
            )
            existing["whitelist_keywords"] = sorted(
                set(existing.get("whitelist_keywords", []) or [])
                | set(list(whitelist_keywords or []))
            )
            if follow_pdf_recursively:
                existing["follow_pdf_recursively"] = True
            if existing.get("source_kind") == "checked_subtarget" and source_kind == "publication_cv_candidate":
                existing["source_kind"] = source_kind
            return
        seeds.append(
            {
                "url": clean,
                "source_kind": source_kind,
                "owner": owner,
                "note": note,
                "whitelist_suffixes": list(whitelist_suffixes) if whitelist_suffixes is not None else [],
                "whitelist_keywords": list(whitelist_keywords) if whitelist_keywords is not None else [],
                "follow_pdf_recursively": None if follow_pdf_recursively is None else bool(follow_pdf_recursively),
            }
        )
        seen[clean] = seeds[-1]

    for author in ledger.get("authors", []) or []:
        owner = str(author.get("name", "") or "unknown")
        for url in author.get("checked_subtargets", []) or []:
            add(url, "checked_subtarget", owner)
        for candidate in author.get("publication_cv_candidates", []) or []:
            add(
                candidate.get("url", ""),
                "publication_cv_candidate",
                owner,
                candidate.get("kind", "candidate"),
                candidate.get("whitelist_suffixes"),
                candidate.get("whitelist_keywords"),
                candidate.get("follow_pdf_recursively"),
            )
        for target in author.get("targets", []) or []:
            add(target.get("url", ""), target.get("kind", "target"), owner, target.get("status", ""))
    return seeds


def _load_hunt_regexes(ledger: dict) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    for row in ledger.get("supplemental_zip_hunt_patterns", []) or []:
        regex = str(row.get("regex", "") or "").strip()
        if not regex:
            continue
        try:
            patterns.append(re.compile(regex))
        except re.error:
            continue
    return patterns


def _match_reasons(url: str, text: str, hunt_regexes: list[re.Pattern[str]]) -> list[str]:
    blob = f"{url} {text}".lower()
    reasons: list[str] = []
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in STRONG_SUFFIXES:
        reasons.append("strong_suffix")
    elif suffix == ".pdf":
        reasons.append("reference_pdf")
    matched_keywords = [keyword for keyword in KEYWORDS if keyword in blob]
    if matched_keywords:
        reasons.append("keywords:" + ",".join(sorted(set(matched_keywords))))
    for pattern in hunt_regexes:
        if pattern.search(f"{url} {text}"):
            reasons.append(f"ledger_regex:{pattern.pattern}")
    return reasons


def _candidate_strength(url: str, text: str) -> str:
    lower = f"{url} {text}".lower()
    if any(lower.endswith(ext) for ext in STRONG_SUFFIXES):
        return "strong_raw_suffix"
    if any(ext in lower for ext in STRONG_SUFFIXES):
        return "strong_raw_suffix"
    if ".pdf" in lower:
        return "reference_pdf"
    return "keyword_only"


def _should_keep_candidate(
    url: str,
    text: str,
    hunt_regexes: list[re.Pattern[str]],
    *,
    extra_keywords: tuple[str, ...] = (),
    extra_suffixes: tuple[str, ...] = (),
) -> bool:
    blob = f"{url} {text}".lower()
    suffix = Path(urlparse(url).path).suffix.lower()
    return (
        suffix in RAW_SUFFIXES
        or suffix in extra_suffixes
        or any(keyword in blob for keyword in KEYWORDS)
        or any(keyword in blob for keyword in extra_keywords)
        or any(pattern.search(f"{url} {text}") for pattern in hunt_regexes)
    )


def _extract_textual_raw_candidates(
    base_url: str,
    text_blob: str,
    hunt_regexes: list[re.Pattern[str]],
    *,
    discovered_from: str,
    parent_url: str,
    extra_keywords: tuple[str, ...] = (),
    extra_suffixes: tuple[str, ...] = (),
    require_raw_suffix: bool = False,
) -> list[dict]:
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    snippets = list(URL_RE.findall(text_blob or "")) + list(RELATIVE_FILE_RE.findall(text_blob or ""))
    for snippet in snippets:
        href = urljoin(base_url, snippet.strip())
        text = snippet.strip()
        if not _should_keep_candidate(
            href,
            text,
            hunt_regexes,
            extra_keywords=extra_keywords,
            extra_suffixes=extra_suffixes,
        ):
            continue
        key = (href, text)
        if key in seen:
            continue
        seen.add(key)
        suffix = Path(urlparse(href).path).suffix.lower()
        if require_raw_suffix and suffix not in RAW_SUFFIXES and suffix not in extra_suffixes:
            continue
        candidates.append(
            {
                "href": href,
                "text": text,
                "suffix": suffix or "n/a",
                "strength": _candidate_strength(href, text),
                "looks_raw_package": suffix in STRONG_SUFFIXES,
                "discovered_from": discovered_from,
                "parent_url": parent_url,
                "match_reasons": _match_reasons(href, text, hunt_regexes),
            }
        )
    return candidates


def _dedupe_candidates(candidates: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        key = (
            str(item.get("href", "")),
            str(item.get("suffix", "")),
            str(item.get("discovered_from", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _extract_pdf_text(fetched: dict) -> str:
    content = fetched.get("content")
    if isinstance(content, (bytes, bytearray)) and content:
        try:
            reader = PdfReader(io.BytesIO(content))
            page_texts = []
            for page in reader.pages[:PDF_SCAN_MAX_PAGES]:
                try:
                    page_texts.append(page.extract_text() or "")
                except Exception:
                    continue
            text = "\n".join(page_texts).strip()
            if text:
                return text
        except Exception:
            pass
    return str(fetched.get("text", "") or "")


def _slugify_token(token: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(token or "").lower()).strip("_")


def _build_pdf_guess_urls(pdf_url: str, ledger: dict) -> list[str]:
    base_dir = pdf_url.rsplit("/", 1)[0] + "/"
    stems: list[str] = []
    for row in ledger.get("reference_pdf_recursive_hunt_patterns", []) or []:
        token_slugs = [_slugify_token(token) for token in row.get("filename_tokens", []) or [] if token]
        if not token_slugs:
            continue
        stems.extend(
            [
                "_".join(token_slugs),
                "-".join(token_slugs),
                "_".join(token_slugs[:3]),
                "-".join(token_slugs[:3]),
            ]
        )
    for row in ledger.get("task12_publication_title_candidates", []) or []:
        title_slug = _slugify_token(row.get("title", ""))
        if title_slug:
            stems.append(title_slug)
    stems = [stem for stem in stems if stem]
    stems = list(dict.fromkeys(stems))
    suffixes = ledger.get("reference_pdf_recursive_suffixes", []) or list(STRONG_SUFFIXES)
    guesses: list[str] = []
    for stem in stems:
        for suffix in suffixes:
            guesses.append(urljoin(base_dir, f"{stem}{suffix}"))
            if len(guesses) >= MAX_GUESSED_URLS_PER_PDF:
                return guesses
    return guesses


def _probe_candidate_urls(urls: list[str], fetcher: Callable[[str], dict], hunt_regexes: list[re.Pattern[str]]) -> list[dict]:
    records: list[dict] = []
    for url in urls:
        try:
            fetched = _default_probe(url) if fetcher is _default_fetch else fetcher(url)
        except Exception as exc:  # pragma: no cover - network failure path
            records.append(
                {
                    "url": url,
                    "status_code": 0,
                    "content_type": "",
                    "exists": False,
                    "error": repr(exc),
                }
            )
            continue
        status_code = int(fetched.get("status_code", 0) or 0)
        content_type = str(fetched.get("content_type", "") or "")
        suffix = Path(urlparse(url).path).suffix.lower()
        exists = status_code == 200 and (
            suffix in STRONG_SUFFIXES
            or "application/" in content_type.lower()
        )
        records.append(
            {
                "url": url,
                "status_code": status_code,
                "content_type": content_type,
                "exists": exists,
                "match_reasons": _match_reasons(url, "", hunt_regexes),
            }
        )
    return records


def _inspect_reference_pdf_candidate(
    pdf_url: str,
    fetched: dict,
    ledger: dict,
    hunt_regexes: list[re.Pattern[str]],
    fetcher: Callable[[str], dict],
) -> dict:
    text = _extract_pdf_text(fetched)
    extracted = _extract_textual_raw_candidates(
        pdf_url,
        text,
        hunt_regexes,
        discovered_from="reference_pdf_text",
        parent_url=pdf_url,
        require_raw_suffix=True,
    )
    topic_hits = [keyword for keyword in KEYWORDS if keyword in text.lower()]
    extracted_urls = sorted({candidate["href"] for candidate in extracted if candidate.get("href")})
    focus_blob = f"{pdf_url} {text[:4000]}".lower()
    should_probe_guesses = any(
        token in focus_blob
        for token in ("transfer", "podium", "backstay", "diaphragm", "girder", "benchmark", "opensees", "task12", "tbi")
    )
    guessed_urls = _build_pdf_guess_urls(pdf_url, ledger) if should_probe_guesses else []
    guessed_probe_records = _probe_candidate_urls(guessed_urls, fetcher, hunt_regexes) if guessed_urls else []
    guessed_hits = [row for row in guessed_probe_records if row.get("exists")]
    return {
        "pdf_url": pdf_url,
        "extracted_url_count": len(extracted_urls),
        "topic_hits": sorted(set(topic_hits)),
        "guessed_url_count": len(guessed_urls),
        "guessed_hit_count": len(guessed_hits),
        "extracted_candidates": extracted[:30],
        "guessed_probe_records": guessed_probe_records,
    }


def _is_whitelist_html_followup(seed: dict, candidate: dict) -> bool:
    if candidate.get("suffix") in RAW_SUFFIXES:
        return False
    href = str(candidate.get("href", "") or "")
    text = str(candidate.get("text", "") or "")
    blob = f"{href} {text}".lower()
    seed_hints = [str(item).lower() for item in (seed.get("whitelist_keywords") or []) if str(item).strip()]
    if not any(hint in blob for hint in (WHITELIST_HTML_HINTS + tuple(seed_hints))):
        return False
    source_kind = str(seed.get("source_kind", "") or "")
    if source_kind in {"publication_cv_candidate", "checked_subtarget"}:
        return True
    return any(token in blob for token in ("publication", "research", "supplement", "appendix"))


def _extract_raw_suffix_candidates(
    base_url: str,
    html_text: str,
    hunt_regexes: list[re.Pattern[str]],
    *,
    extra_keywords: tuple[str, ...] = (),
    extra_suffixes: tuple[str, ...] = (),
    require_raw_suffix: bool = False,
) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"])
        text = " ".join(anchor.get_text(" ", strip=True).split())
        if not _should_keep_candidate(
            href,
            text,
            hunt_regexes,
            extra_keywords=extra_keywords,
            extra_suffixes=extra_suffixes,
        ):
            continue
        key = (href, text)
        if key in seen:
            continue
        seen.add(key)
        parsed = urlparse(href)
        suffix = Path(parsed.path).suffix.lower()
        if require_raw_suffix and suffix not in RAW_SUFFIXES and suffix not in extra_suffixes:
            continue
        candidates.append(
            {
                "href": href,
                "text": text,
                "suffix": suffix or "n/a",
                "strength": _candidate_strength(href, text),
                "looks_raw_package": suffix in STRONG_SUFFIXES,
                "discovered_from": "html_anchor",
                "parent_url": base_url,
                "match_reasons": _match_reasons(href, text, hunt_regexes),
            }
        )
    return candidates


def build_transfer_podium_raw_source_scan_payload(
    ledger: dict,
    fetcher: Callable[[str], dict] = _default_fetch,
) -> dict:
    seeds = _collect_seed_urls(ledger)
    hunt_regexes = _load_hunt_regexes(ledger)
    records: list[dict] = []
    reference_pdf_records: list[dict] = []
    strong_candidate_count = 0
    reference_pdf_count = 0
    recursive_reference_scan_count = 0
    whitelist_followup_scan_count = 0
    guessed_pdf_url_count = 0
    guessed_pdf_hit_count = 0
    def _scan(seed: dict) -> dict:
        url = seed["url"]
        try:
            fetched = fetcher(url)
            status_code = int(fetched.get("status_code", 0) or 0)
            content_type = str(fetched.get("content_type", "") or "")
            html_text = str(fetched.get("text", "") or "")
            is_html = "html" in content_type.lower()
            extra_keywords = tuple(str(item).lower() for item in (seed.get("whitelist_keywords") or []))
            extra_suffixes = tuple(str(item).lower() for item in (seed.get("whitelist_suffixes") or []))
            candidates = (
                _extract_raw_suffix_candidates(
                    url,
                    html_text,
                    hunt_regexes,
                    extra_keywords=extra_keywords,
                    extra_suffixes=extra_suffixes,
                )
                if is_html
                else []
            )
            candidates.extend(
                _extract_textual_raw_candidates(
                    url,
                    html_text,
                    hunt_regexes,
                    discovered_from="page_text",
                    parent_url=url,
                    extra_keywords=extra_keywords,
                    extra_suffixes=extra_suffixes,
                )
            )
            recursive_scans = 0
            whitelist_scans = 0
            recursive_candidates: list[dict] = []
            pdf_records: list[dict] = []
            for candidate in list(candidates):
                if candidate.get("suffix") != ".pdf":
                    if _is_whitelist_html_followup(seed, candidate):
                        try:
                            nested = fetcher(candidate["href"])
                        except Exception:
                            continue
                        nested_type = str(nested.get("content_type", "") or "")
                        if "html" not in nested_type.lower():
                            continue
                        whitelist_scans += 1
                        nested_text = str(nested.get("text", "") or "")
                        recursive_candidates.extend(
                            _extract_raw_suffix_candidates(
                                candidate["href"],
                                nested_text,
                                hunt_regexes,
                                extra_keywords=extra_keywords,
                                extra_suffixes=extra_suffixes,
                                require_raw_suffix=True,
                            )
                        )
                        recursive_candidates.extend(
                            _extract_textual_raw_candidates(
                                candidate["href"],
                                nested_text,
                                hunt_regexes,
                                discovered_from="whitelist_html_text",
                                parent_url=candidate["href"],
                                extra_keywords=extra_keywords,
                                extra_suffixes=extra_suffixes,
                                require_raw_suffix=True,
                            )
                        )
                    continue
                if seed.get("follow_pdf_recursively") is False:
                    continue
                try:
                    nested = fetcher(candidate["href"])
                except Exception:
                    continue
                recursive_scans += 1
                pdf_record = _inspect_reference_pdf_candidate(
                    candidate["href"],
                    nested,
                    ledger,
                    hunt_regexes,
                    fetcher,
                )
                pdf_records.append(pdf_record)
                recursive_candidates.extend(pdf_record.get("extracted_candidates", []) or [])
                for guessed_hit in pdf_record.get("guessed_probe_records", []) or []:
                    if not guessed_hit.get("exists"):
                        continue
                    guessed_url = str(guessed_hit.get("url", "") or "")
                    suffix = Path(urlparse(guessed_url).path).suffix.lower()
                    recursive_candidates.append(
                        {
                            "href": guessed_url,
                            "text": guessed_url.rsplit("/", 1)[-1],
                            "suffix": suffix or "n/a",
                            "strength": _candidate_strength(guessed_url, ""),
                            "looks_raw_package": suffix in STRONG_SUFFIXES,
                            "discovered_from": "reference_pdf_guessed_filename",
                            "parent_url": candidate["href"],
                            "match_reasons": guessed_hit.get("match_reasons", []),
                        }
                    )
            candidates.extend(recursive_candidates)
            candidates = _dedupe_candidates(candidates)
            return {
                **seed,
                "status_code": status_code,
                "content_type": content_type,
                "scan_status": "scanned_html" if is_html else "reference_or_non_html",
                "candidate_count": len(candidates),
                "strong_raw_candidate_count": sum(1 for item in candidates if item.get("looks_raw_package")),
                "reference_pdf_candidate_count": sum(1 for item in candidates if item.get("suffix") == ".pdf"),
                "recursive_reference_scan_count": recursive_scans,
                "whitelist_followup_scan_count": whitelist_scans,
                "reference_pdf_records": pdf_records,
                "guessed_pdf_url_count": sum(int(item.get("guessed_url_count", 0) or 0) for item in pdf_records),
                "guessed_pdf_hit_count": sum(int(item.get("guessed_hit_count", 0) or 0) for item in pdf_records),
                "candidates": candidates[:80],
            }
        except Exception as exc:  # pragma: no cover - network failure path
            return {
                **seed,
                "scan_status": "fetch_error",
                "error": repr(exc),
                "candidate_count": 0,
                "strong_raw_candidate_count": 0,
                "reference_pdf_candidate_count": 0,
                "recursive_reference_scan_count": 0,
                "whitelist_followup_scan_count": 0,
                "reference_pdf_records": [],
                "guessed_pdf_url_count": 0,
                "guessed_pdf_hit_count": 0,
                "candidates": [],
            }

    max_workers = min(6, max(1, len(seeds)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(_scan, seed): seed for seed in seeds}
        for future in as_completed(future_map):
            row = future.result()
            records.append(row)
            strong_candidate_count += int(row.get("strong_raw_candidate_count", 0) or 0)
            reference_pdf_count += int(row.get("reference_pdf_candidate_count", 0) or 0)
            recursive_reference_scan_count += int(row.get("recursive_reference_scan_count", 0) or 0)
            whitelist_followup_scan_count += int(row.get("whitelist_followup_scan_count", 0) or 0)
            guessed_pdf_url_count += int(row.get("guessed_pdf_url_count", 0) or 0)
            guessed_pdf_hit_count += int(row.get("guessed_pdf_hit_count", 0) or 0)
            reference_pdf_records.extend(row.get("reference_pdf_records", []) or [])

    records.sort(key=lambda row: (str(row.get("owner", "")), str(row.get("source_kind", "")), str(row.get("url", ""))))

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "family_id": "transfer_podium_tower",
        "as_of_date": datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat(),
        "summary": {
            "seed_url_count": len(seeds),
            "scanned_record_count": len(records),
            "strong_raw_candidate_count": strong_candidate_count,
            "reference_pdf_candidate_count": reference_pdf_count,
            "recursive_reference_scan_count": recursive_reference_scan_count,
            "whitelist_followup_scan_count": whitelist_followup_scan_count,
            "guessed_pdf_url_count": guessed_pdf_url_count,
            "guessed_pdf_hit_count": guessed_pdf_hit_count,
            "verified_native_package_found": False,
            "summary_line": (
                "Transfer podium raw source scan: CHECK | "
                f"seed_urls={len(seeds)} | scanned={len(records)} | "
                f"strong_candidates={strong_candidate_count} | reference_pdfs={reference_pdf_count} | "
                f"recursive_reference_scans={recursive_reference_scan_count} | "
                f"whitelist_html_scans={whitelist_followup_scan_count} | "
                f"guessed_pdf_urls={guessed_pdf_url_count} | guessed_pdf_hits={guessed_pdf_hit_count} | "
                "verified_native_package_found=no"
            ),
        },
        "records": records,
        "reference_pdf_records": reference_pdf_records,
    }
    return payload


def _render_markdown(payload: dict) -> str:
    lines = [
        "# Transfer Podium Raw Source Candidate Scan",
        "",
        f"- `family_id`: `{payload.get('family_id', '')}`",
        f"- `as_of_date`: `{payload.get('as_of_date', '')}`",
        f"- `summary_line`: `{((payload.get('summary') or {}).get('summary_line', ''))}`",
        "",
        "| Seed URL | Owner | Source Kind | Scan Status | Strong Raw Candidates | Candidate Count |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in payload.get("records", []) or []:
        lines.append(
            f"| {row.get('url', '')} | {row.get('owner', '')} | {row.get('source_kind', '')} | "
            f"{row.get('scan_status', '')} | {row.get('strong_raw_candidate_count', 0)} | {row.get('candidate_count', 0)} |"
        )
    lines.extend(["", "## Candidate Details", ""])
    for row in payload.get("records", []) or []:
        lines.append(f"### {row.get('owner', '')} | {row.get('url', '')}")
        if row.get("note"):
            lines.append(f"- `note`: {row.get('note')}")
        if row.get("error"):
            lines.append(f"- `error`: {row.get('error')}")
        if row.get("recursive_reference_scan_count"):
            lines.append(f"- `recursive_reference_scan_count`: {row.get('recursive_reference_scan_count')}")
        if row.get("whitelist_followup_scan_count"):
            lines.append(f"- `whitelist_followup_scan_count`: {row.get('whitelist_followup_scan_count')}")
        for candidate in row.get("candidates", []) or []:
            lines.append(
                f"- `{candidate.get('strength', '')}` | `{candidate.get('suffix', '')}` | "
                f"`{candidate.get('href', '')}` | {candidate.get('text', '') or '[no text]'} | "
                f"from `{candidate.get('discovered_from', '')}` via `{candidate.get('parent_url', '')}`"
                + (
                    f" | reasons=`{','.join(candidate.get('match_reasons', []) or [])}`"
                    if candidate.get("match_reasons")
                    else ""
                )
            )
        if not (row.get("candidates") or []):
            lines.append("- no raw-suffix candidate links surfaced")
        lines.append("")
    lines.extend(["", "## Reference PDF Recursive Details", ""])
    for row in payload.get("reference_pdf_records", []) or []:
        lines.append(f"### `{row.get('pdf_url', '')}`")
        lines.append(f"- `extracted_url_count`: `{row.get('extracted_url_count', 0)}`")
        lines.append(f"- `topic_hits`: `{', '.join(row.get('topic_hits', []) or [])}`")
        lines.append(f"- `guessed_url_count`: `{row.get('guessed_url_count', 0)}`")
        lines.append(f"- `guessed_hit_count`: `{row.get('guessed_hit_count', 0)}`")
        for probe in row.get("guessed_probe_records", [])[:8]:
            lines.append(
                f"- `guess` | `{probe.get('status_code', 0)}` | `{probe.get('url', '')}`"
            )
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ledger = json.loads(LEDGER_JSON.read_text(encoding="utf-8"))
    payload = build_transfer_podium_raw_source_scan_payload(ledger)
    _write_json(OUT_JSON, payload)
    OUT_MD.write_text(_render_markdown(payload), encoding="utf-8")
    print(f"Wrote transfer podium raw source scan: {OUT_JSON}")
    print(f"Wrote transfer podium raw source scan markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
