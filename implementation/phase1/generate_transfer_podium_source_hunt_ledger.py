#!/usr/bin/env python3
"""Generate a transfer-podium-specific author/source hunt ledger."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "implementation/phase1/open_data/irregular"
OUT_JSON = OUT_DIR / "transfer_podium_source_hunt_ledger.json"
OUT_MD = OUT_DIR / "transfer_podium_source_hunt_ledger.md"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    as_of = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    authors = [
        {
            "name": "John Wallace",
            "role": "Task 12 principal author; Chapter 4 co-author",
            "priority": 1,
            "affiliation": "UCLA",
            "evidence_basis": "Task 12 report authorship and Chapter 4 responsibility",
            "preferred_topic_match_order": [
                "core_wall_tower_with_podium",
                "backstay_effect",
                "transfer_diaphragms",
                "below_grade_structure",
            ],
            "checked_subtargets": [
                "https://seas.ucla.edu/~wallace/peer_center.htm",
                "https://seas.ucla.edu/~wallace/research.htm",
                "https://seas.ucla.edu/~wallace/earthquakes.htm",
            ],
            "publication_cv_candidates": [
                {
                    "kind": "research_page",
                    "url": "https://seas.ucla.edu/~wallace/research.htm",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip"],
                    "whitelist_keywords": ["transfer", "podium", "backstay", "girder", "diaphragm", "task12", "tbi"],
                    "follow_pdf_recursively": True,
                    "note": "Research page checked; no transfer podium benchmark-native package surfaced.",
                },
                {
                    "kind": "peer_center_page",
                    "url": "https://seas.ucla.edu/~wallace/peer_center.htm",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip"],
                    "whitelist_keywords": ["transfer", "podium", "task12", "tbi", "benchmark"],
                    "follow_pdf_recursively": True,
                    "note": "PEER center page checked; no task-level model package surfaced.",
                },
            ],
            "targets": [
                {
                    "kind": "personal_page",
                    "status": "checked_partial",
                    "url": "https://seas.ucla.edu/~wallace/",
                    "note": "Official UCLA faculty page confirmed; peer_center/research/earthquakes subpages were also checked, but no benchmark-native transfer podium package surfaced.",
                },
                {
                    "kind": "lab_site",
                    "status": "checked_partial",
                    "url": "https://www.seas.ucla.edu/",
                    "note": "Official UCLA domain confirmed; no benchmark-native transfer podium package identified on accessible lab pages in this round.",
                },
                {
                    "kind": "github_raw",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No verified benchmark-native transfer podium OpenSees package located on public GitHub in this round.",
                },
                {
                    "kind": "supplemental_zip",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No supplemental zip tied to the official PEER transfer podium case located in this round.",
                },
            ],
        },
        {
            "name": "Zeynep Tuna",
            "role": "Task 12 Chapter 4 co-author",
            "priority": 2,
            "affiliation": "UCLA / later academic profiles",
            "evidence_basis": "Task 12 report authorship and Chapter 4 responsibility",
            "preferred_topic_match_order": [
                "backstay_effect",
                "transfer_diaphragms",
                "core_wall_tower_with_podium",
            ],
            "checked_subtargets": [],
            "publication_cv_candidates": [],
            "targets": [
                {
                    "kind": "personal_page",
                    "status": "checked_partial",
                    "url": "",
                    "note": "No authoritative UCLA-era project page with benchmark-native transfer podium package identified in this round.",
                },
                {
                    "kind": "lab_site",
                    "status": "checked_partial",
                    "url": "",
                    "note": "Public academic traces exist, but not a verified task-level model package source.",
                },
                {
                    "kind": "github_raw",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No verified GitHub raw benchmark-native package found.",
                },
                {
                    "kind": "supplemental_zip",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No public supplemental zip found for the transfer podium task.",
                },
            ],
        },
        {
            "name": "Tony Yang",
            "role": "Task 12 principal author; tall-building simulation contributor",
            "priority": 3,
            "affiliation": "UBC",
            "evidence_basis": "Task 12 report authorship",
            "preferred_topic_match_order": [
                "multiple_towers_single_podium",
                "core_wall_tower_with_podium",
                "transfer_diaphragms",
                "transfer_girders",
            ],
            "checked_subtargets": [
                "https://smartstructures.civil.ubc.ca/opensees-navigator/",
                "https://smartstructures.civil.ubc.ca/ilee-eerf-collaboration/prototype-building/",
            ],
            "publication_cv_candidates": [
                {
                    "kind": "research_area_page",
                    "url": "https://civil.ubc.ca/research/research-areas/structural-earthquake-engineering/",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip"],
                    "whitelist_keywords": ["transfer", "podium", "benchmark", "opensees", "tower"],
                    "follow_pdf_recursively": True,
                    "note": "Structural & Earthquake Engineering area page checked as publication/research hub; no transfer podium package surfaced.",
                },
                {
                    "kind": "opensees_navigator_page",
                    "url": "https://smartstructures.civil.ubc.ca/opensees-navigator/",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip", ".tcl", ".inp"],
                    "whitelist_keywords": ["opensees", "transfer", "podium", "prototype", "tower"],
                    "follow_pdf_recursively": True,
                    "note": "OpenSees Navigator page checked; useful tool context, but not the target transfer podium benchmark package.",
                },
            ],
            "targets": [
                {
                    "kind": "personal_page",
                    "status": "checked_found",
                    "url": "https://civil.ubc.ca/tony-yang/",
                    "note": "Official UBC faculty page confirmed.",
                },
                {
                    "kind": "lab_site",
                    "status": "checked_found",
                    "url": "https://smartstructures.civil.ubc.ca/about/",
                    "note": "Official Smart Structures lab page confirmed; OpenSees Navigator and Prototype Building project pages were also checked, but no transfer podium benchmark-native package surfaced.",
                },
                {
                    "kind": "github_raw",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.",
                },
                {
                    "kind": "supplemental_zip",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No supplemental zip for the transfer podium benchmark located in this round.",
                },
            ],
        },
        {
            "name": "Farzin Zareian",
            "role": "Task 12 principal author",
            "priority": 4,
            "affiliation": "UC Irvine",
            "evidence_basis": "Task 12 report authorship",
            "preferred_topic_match_order": [
                "transfer_girders",
                "multiple_towers_single_podium",
                "core_wall_tower_with_podium",
            ],
            "checked_subtargets": [],
            "publication_cv_candidates": [
                {
                    "kind": "legacy_publications_page",
                    "url": "https://ics.uci.edu/~hjafarpo/Farzin/Publications.htm",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip"],
                    "whitelist_keywords": ["transfer", "podium", "task12", "tbi", "tower"],
                    "follow_pdf_recursively": True,
                    "note": "Legacy publications page checked as likely supplemental/publication hub; no verified transfer podium package surfaced in this round.",
                },
                {
                    "kind": "legacy_profile_page",
                    "url": "https://ics.uci.edu/~hjafarpo/Farzin/Dr.Zareian.htm",
                    "status": "checked_partial",
                    "whitelist_suffixes": [".pdf", ".zip"],
                    "whitelist_keywords": ["transfer", "podium", "tower", "benchmark"],
                    "follow_pdf_recursively": True,
                    "note": "Legacy profile page checked; no task-level benchmark package surfaced.",
                },
            ],
            "targets": [
                {
                    "kind": "personal_page",
                    "status": "checked_found",
                    "url": "https://engineering.uci.edu/users/farzin-zareian",
                    "note": "Official UCI faculty page confirmed.",
                },
                {
                    "kind": "lab_site",
                    "status": "checked_found",
                    "url": "https://ics.uci.edu/~hjafarpo/Farzin/Dr.Zareian.htm",
                    "note": "Legacy personal/lab-style page confirmed; no transfer podium benchmark package surfaced.",
                },
                {
                    "kind": "github_raw",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.",
                },
                {
                    "kind": "supplemental_zip",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No supplemental zip for the transfer podium benchmark located in this round.",
                },
            ],
        },
        {
            "name": "Pierson Jones",
            "role": "Task 12 principal author",
            "priority": 5,
            "affiliation": "UC Irvine / practice",
            "evidence_basis": "Task 12 report authorship",
            "preferred_topic_match_order": [
                "transfer_girders",
                "multiple_towers_single_podium",
                "backstay_effect",
            ],
            "checked_subtargets": [],
            "publication_cv_candidates": [],
            "targets": [
                {
                    "kind": "personal_page",
                    "status": "checked_found",
                    "url": "https://garciastructural.com/our-team/",
                    "note": "Professional biography confirmed computational seismic modeling of tall steel buildings.",
                },
                {
                    "kind": "lab_site",
                    "status": "checked_partial",
                    "url": "",
                    "note": "No active academic lab page with task-level source package found in this round.",
                },
                {
                    "kind": "github_raw",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.",
                },
                {
                    "kind": "supplemental_zip",
                    "status": "checked_no_verified_hit",
                    "url": "",
                    "note": "No supplemental zip for the transfer podium benchmark located in this round.",
                },
            ],
        },
    ]

    sequence = [
        "author_personal_page",
        "lab_site",
        "github_raw",
        "supplemental_zip",
    ]
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        "family_id": "transfer_podium_tower",
        "as_of_date": as_of,
        "official_task_report_url": "https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf",
        "official_final_report_url": "https://peer.berkeley.edu/sites/default/files/final_tbi_report_10.9.2017_0.pdf",
        "search_sequence": sequence,
        "status": "source_hunt_active",
        "canonical_status": "not_promoted",
        "audit_statement": f"official PEER docs checked, native package not found as of {as_of}",
        "task12_transfer_focus_topics": [
            {
                "topic_id": "multiple_towers_single_podium",
                "title": "multiple towers on a single podium",
                "why_it_matters": "Matches the target transfer/podium benchmark family and narrows supplemental hunts to podium-coupled tower publications.",
            },
            {
                "topic_id": "backstay_effect",
                "title": "Backstay Effect",
                "why_it_matters": "Strong transfer-podium modeling keyword for diaphragm and basement interaction source hunts.",
            },
            {
                "topic_id": "core_wall_tower_with_podium",
                "title": "Core-wall tower with podium having separate foundation system",
                "why_it_matters": "Figure/title directly aligned with transfer-podium benchmark geometry and SSI framing.",
            },
            {
                "topic_id": "transfer_diaphragms",
                "title": "transfer diaphragms",
                "why_it_matters": "Useful keyword for supplemental zips, appendices, and model package names.",
            },
            {
                "topic_id": "transfer_girders",
                "title": "transfer girders",
                "why_it_matters": "Targets vertical discontinuity cases where columns terminate on transfer girders.",
            },
            {
                "topic_id": "below_grade_structure",
                "title": "below-grade structure",
                "why_it_matters": "Narrows podium/basement interaction package hunts and figure appendix checks.",
            },
        ],
        "task12_publication_title_candidates": [
            {
                "title": "Tall Building Initiative Task 12",
                "match_basis": "official task report wording",
            },
            {
                "title": "Guidelines for Performance-Based Seismic Design of Tall Buildings",
                "match_basis": "official final report title",
            },
            {
                "title": "Core-wall tower with podium having separate foundation system",
                "match_basis": "Figure 4-8 title",
            },
            {
                "title": "multiple towers on a single podium",
                "match_basis": "transfer/podium family wording in final report",
            },
            {
                "title": "Backstay Effect",
                "match_basis": "glossary term tied to podium transfer mechanics",
            },
            {
                "title": "transfer diaphragms",
                "match_basis": "modeling guidance wording in Chapter 4",
            },
            {
                "title": "transfer girders",
                "match_basis": "vertical discontinuity wording in Chapter 4",
            },
            {
                "title": "below-grade structure",
                "match_basis": "substructure interaction wording in Chapter 4",
            },
        ],
        "supplemental_zip_hunt_patterns": [
            {
                "pattern_id": "task12_transfer_podium_zip",
                "regex": r"(?i)(task[_ -]?12|tbi).*(transfer|podium).*(zip|tcl|inp|ifc|mgt)$",
                "why_it_matters": "Direct Task 12 plus transfer/podium naming convention for model archives.",
            },
            {
                "pattern_id": "corewall_podium_zip",
                "regex": r"(?i)(core[-_ ]?wall|tower).*(podium|foundation).*(zip|tcl|inp|ifc|mgt)$",
                "why_it_matters": "Covers Figure 4-8 style package names for core-wall tower with podium system.",
            },
            {
                "pattern_id": "backstay_transfer_model",
                "regex": r"(?i)(backstay|transfer[_ -]?diaphragm|transfer[_ -]?girder).*(model|benchmark|analysis).*(zip|tcl|inp|ifc)$",
                "why_it_matters": "Targets publication supplements that use mechanism-level filenames instead of project names.",
            },
            {
                "pattern_id": "multiple_towers_podium_bundle",
                "regex": r"(?i)(multiple[_ -]?towers|tower[_ -]?podium|single[_ -]?podium).*(zip|tcl|inp|ifc|mgt)$",
                "why_it_matters": "Covers podium-coupled multi-tower bundle names from tall-building benchmark families.",
            },
            {
                "pattern_id": "belowgrade_foundation_package",
                "regex": r"(?i)(below[_ -]?grade|basement|foundation).*(podium|tower).*(zip|tcl|inp|ifc)$",
                "why_it_matters": "Captures basement/foundation companion packages tied to podium transfer cases.",
            },
        ],
        "reference_pdf_recursive_hunt_patterns": [
            {
                "pattern_id": "task12_transfer_appendix",
                "filename_tokens": ["task12", "transfer", "podium", "appendix"],
                "why_it_matters": "Covers report-adjacent appendix bundles named after Task 12 transfer cases.",
            },
            {
                "pattern_id": "backstay_corewall_supplement",
                "filename_tokens": ["backstay", "corewall", "podium", "tower", "supplement"],
                "why_it_matters": "Targets mechanism-level supplements derived from Chapter 4 podium behavior language.",
            },
            {
                "pattern_id": "transfer_girder_model",
                "filename_tokens": ["transfer", "girder", "model", "benchmark"],
                "why_it_matters": "Covers model bundle names using transfer-girder wording instead of project names.",
            },
            {
                "pattern_id": "multiple_tower_podium_package",
                "filename_tokens": ["multiple", "tower", "single", "podium", "package"],
                "why_it_matters": "Targets podium-coupled tower packages named after the system form.",
            },
        ],
        "publication_whitelist_scan_terms": [
            "publication",
            "publications",
            "research",
            "peer",
            "earthquake",
            "opensees",
            "prototype",
            "supplement",
            "appendix",
            "task12",
            "task_12",
            "tbi",
            "transfer",
            "podium",
            "backstay",
            "core-wall",
            "corewall",
        ],
        "raw_suffix_scan_suffixes": [".zip", ".tcl", ".inp", ".ifc", ".mgt", ".meb", ".pdf"],
        "search_findings": [
            "Wallace UCLA peer_center/research/earthquakes pages checked; no benchmark-native transfer package found.",
            "Tony Yang Smart Structures OpenSees Navigator and Prototype Building pages checked; no transfer podium package found.",
            "Wallace/Yang/Zareian publication or research hub pages were checked as supplemental/publication candidates; no verified transfer podium package surfaced.",
            "Public GitHub code search requires authentication; unauthenticated API returned 401, and public search-engine queries produced no verified raw hit.",
        ],
        "authors": authors,
        "summary_line": (
            f"Transfer podium source hunt ledger: ACTIVE | authors={len(authors)} | "
            f"sequence=personal_page>lab_site>github_raw>supplemental_zip | "
            f"official_docs_checked=yes | native_package_found=no | as_of={as_of}"
        ),
    }
    _write_json(OUT_JSON, payload)

    lines = [
        "# Transfer Podium Source Hunt Ledger",
        "",
        f"- `family_id`: `{payload['family_id']}`",
        f"- `as_of_date`: `{payload['as_of_date']}`",
        f"- `official_task_report_url`: `{payload['official_task_report_url']}`",
        f"- `official_final_report_url`: `{payload['official_final_report_url']}`",
        f"- `audit_statement`: `{payload['audit_statement']}`",
        f"- `summary_line`: `{payload['summary_line']}`",
        "",
        "## Task 12 Transfer Focus Topics",
        "",
    ]
    for topic in payload["task12_transfer_focus_topics"]:
        lines.append(f"- `{topic['title']}`: {topic['why_it_matters']}")
    lines.extend(["", "## Publication Title Candidates", ""])
    for candidate in payload["task12_publication_title_candidates"]:
        lines.append(f"- `{candidate['title']}`: {candidate['match_basis']}")
    lines.extend(["", "## Supplemental Zip Hunt Patterns", ""])
    for pattern in payload["supplemental_zip_hunt_patterns"]:
        lines.append(f"- `{pattern['pattern_id']}` | `{pattern['regex']}` | {pattern['why_it_matters']}")
    lines.extend(["", "## Reference PDF Recursive Hunt Patterns", ""])
    for pattern in payload["reference_pdf_recursive_hunt_patterns"]:
        token_blob = ", ".join(pattern["filename_tokens"])
        lines.append(f"- `{pattern['pattern_id']}` | `{token_blob}` | {pattern['why_it_matters']}")
    lines.extend(["", "## Publication Whitelist Scan Terms", ""])
    for term in payload["publication_whitelist_scan_terms"]:
        lines.append(f"- `{term}`")
    lines.extend(["", "## Raw Suffix Scan Suffixes", ""])
    for suffix in payload["raw_suffix_scan_suffixes"]:
        lines.append(f"- `{suffix}`")
    lines.extend(
        [
            "",
        "## Focused Findings",
        "",
        ]
    )
    for finding in payload["search_findings"]:
        lines.append(f"- {finding}")
    lines.extend(
        [
            "",
        "## Author-Priority Hunt List",
        "",
        "| Priority | Author | Role | Affiliation | Personal Page | Lab Site | GitHub Raw | Supplemental Zip |",
        "|---|---|---|---|---|---|---|---|",
        ]
    )
    for author in authors:
        targets = {item["kind"]: item for item in author["targets"]}
        lines.append(
            f"| {author['priority']} | {author['name']} | {author['role']} | {author['affiliation']} | "
            f"{targets['personal_page'].get('url') or targets['personal_page'].get('status')} | "
            f"{targets['lab_site'].get('url') or targets['lab_site'].get('status')} | "
            f"{targets['github_raw'].get('status')} | "
            f"{targets['supplemental_zip'].get('status')} |"
        )
    lines.extend(["", "## Notes", ""])
    for author in authors:
        lines.append(f"### {author['name']}")
        preferred_topic_match_order = author.get("preferred_topic_match_order") or []
        if preferred_topic_match_order:
            lines.append("- `preferred_topic_match_order`:")
            for topic_id in preferred_topic_match_order:
                lines.append(f"  - `{topic_id}`")
        checked_subtargets = author.get("checked_subtargets") or []
        if checked_subtargets:
            lines.append("- `checked_subtargets`:")
            for target_url in checked_subtargets:
                lines.append(f"  - `{target_url}`")
        publication_cv_candidates = author.get("publication_cv_candidates") or []
        if publication_cv_candidates:
            lines.append("- `publication_cv_candidates`:")
            for candidate in publication_cv_candidates:
                lines.append(
                    f"  - `{candidate.get('kind', 'candidate')}` | `{candidate.get('url', '')}` | "
                    f"`{candidate.get('status', '')}` | {candidate.get('note', '')}"
                )
                if candidate.get("whitelist_suffixes"):
                    lines.append(
                        "    - `whitelist_suffixes`: "
                        + ", ".join(f"`{suffix}`" for suffix in candidate["whitelist_suffixes"])
                    )
                if candidate.get("whitelist_keywords"):
                    lines.append(
                        "    - `whitelist_keywords`: "
                        + ", ".join(f"`{keyword}`" for keyword in candidate["whitelist_keywords"])
                    )
                if candidate.get("follow_pdf_recursively") is not None:
                    lines.append(
                        f"    - `follow_pdf_recursively`: `{bool(candidate['follow_pdf_recursively'])}`"
                    )
        for target in author["targets"]:
            lines.append(
                f"- `{target['kind']}`: `{target['status']}`"
                + (f" | `{target['url']}`" if target.get("url") else "")
                + (f" | {target['note']}" if target.get("note") else "")
            )
        lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote transfer podium source hunt ledger: {OUT_JSON}")
    print(f"Wrote transfer podium source hunt ledger markdown: {OUT_MD}")


if __name__ == "__main__":
    main()
