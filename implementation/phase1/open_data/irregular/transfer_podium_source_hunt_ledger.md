# Transfer Podium Source Hunt Ledger

- `family_id`: `transfer_podium_tower`
- `as_of_date`: `2026-04-11`
- `official_task_report_url`: `https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf`
- `official_final_report_url`: `https://peer.berkeley.edu/sites/default/files/final_tbi_report_10.9.2017_0.pdf`
- `audit_statement`: `official PEER docs checked, native package not found as of 2026-04-11`
- `summary_line`: `Transfer podium source hunt ledger: ACTIVE | authors=5 | sequence=personal_page>lab_site>github_raw>supplemental_zip | official_docs_checked=yes | native_package_found=no | as_of=2026-04-11`

## Task 12 Transfer Focus Topics

- `multiple towers on a single podium`: Matches the target transfer/podium benchmark family and narrows supplemental hunts to podium-coupled tower publications.
- `Backstay Effect`: Strong transfer-podium modeling keyword for diaphragm and basement interaction source hunts.
- `Core-wall tower with podium having separate foundation system`: Figure/title directly aligned with transfer-podium benchmark geometry and SSI framing.
- `transfer diaphragms`: Useful keyword for supplemental zips, appendices, and model package names.
- `transfer girders`: Targets vertical discontinuity cases where columns terminate on transfer girders.
- `below-grade structure`: Narrows podium/basement interaction package hunts and figure appendix checks.

## Publication Title Candidates

- `Tall Building Initiative Task 12`: official task report wording
- `Guidelines for Performance-Based Seismic Design of Tall Buildings`: official final report title
- `Core-wall tower with podium having separate foundation system`: Figure 4-8 title
- `multiple towers on a single podium`: transfer/podium family wording in final report
- `Backstay Effect`: glossary term tied to podium transfer mechanics
- `transfer diaphragms`: modeling guidance wording in Chapter 4
- `transfer girders`: vertical discontinuity wording in Chapter 4
- `below-grade structure`: substructure interaction wording in Chapter 4

## Supplemental Zip Hunt Patterns

- `task12_transfer_podium_zip` | `(?i)(task[_ -]?12|tbi).*(transfer|podium).*(zip|tcl|inp|ifc|mgt)$` | Direct Task 12 plus transfer/podium naming convention for model archives.
- `corewall_podium_zip` | `(?i)(core[-_ ]?wall|tower).*(podium|foundation).*(zip|tcl|inp|ifc|mgt)$` | Covers Figure 4-8 style package names for core-wall tower with podium system.
- `backstay_transfer_model` | `(?i)(backstay|transfer[_ -]?diaphragm|transfer[_ -]?girder).*(model|benchmark|analysis).*(zip|tcl|inp|ifc)$` | Targets publication supplements that use mechanism-level filenames instead of project names.
- `multiple_towers_podium_bundle` | `(?i)(multiple[_ -]?towers|tower[_ -]?podium|single[_ -]?podium).*(zip|tcl|inp|ifc|mgt)$` | Covers podium-coupled multi-tower bundle names from tall-building benchmark families.
- `belowgrade_foundation_package` | `(?i)(below[_ -]?grade|basement|foundation).*(podium|tower).*(zip|tcl|inp|ifc)$` | Captures basement/foundation companion packages tied to podium transfer cases.

## Reference PDF Recursive Hunt Patterns

- `task12_transfer_appendix` | `task12, transfer, podium, appendix` | Covers report-adjacent appendix bundles named after Task 12 transfer cases.
- `backstay_corewall_supplement` | `backstay, corewall, podium, tower, supplement` | Targets mechanism-level supplements derived from Chapter 4 podium behavior language.
- `transfer_girder_model` | `transfer, girder, model, benchmark` | Covers model bundle names using transfer-girder wording instead of project names.
- `multiple_tower_podium_package` | `multiple, tower, single, podium, package` | Targets podium-coupled tower packages named after the system form.

## Publication Whitelist Scan Terms

- `publication`
- `publications`
- `research`
- `peer`
- `earthquake`
- `opensees`
- `prototype`
- `supplement`
- `appendix`
- `task12`
- `task_12`
- `tbi`
- `transfer`
- `podium`
- `backstay`
- `core-wall`
- `corewall`

## Raw Suffix Scan Suffixes

- `.zip`
- `.tcl`
- `.inp`
- `.ifc`
- `.mgt`
- `.meb`
- `.pdf`

## Focused Findings

- Wallace UCLA peer_center/research/earthquakes pages checked; no benchmark-native transfer package found.
- Tony Yang Smart Structures OpenSees Navigator and Prototype Building pages checked; no transfer podium package found.
- Wallace/Yang/Zareian publication or research hub pages were checked as supplemental/publication candidates; no verified transfer podium package surfaced.
- Public GitHub code search requires authentication; unauthenticated API returned 401, and public search-engine queries produced no verified raw hit.

## Author-Priority Hunt List

| Priority | Author | Role | Affiliation | Personal Page | Lab Site | GitHub Raw | Supplemental Zip |
|---|---|---|---|---|---|---|---|
| 1 | John Wallace | Task 12 principal author; Chapter 4 co-author | UCLA | https://seas.ucla.edu/~wallace/ | https://www.seas.ucla.edu/ | checked_no_verified_hit | checked_no_verified_hit |
| 2 | Zeynep Tuna | Task 12 Chapter 4 co-author | UCLA / later academic profiles | checked_partial | checked_partial | checked_no_verified_hit | checked_no_verified_hit |
| 3 | Tony Yang | Task 12 principal author; tall-building simulation contributor | UBC | https://civil.ubc.ca/tony-yang/ | https://smartstructures.civil.ubc.ca/about/ | checked_no_verified_hit | checked_no_verified_hit |
| 4 | Farzin Zareian | Task 12 principal author | UC Irvine | https://engineering.uci.edu/users/farzin-zareian | https://ics.uci.edu/~hjafarpo/Farzin/Dr.Zareian.htm | checked_no_verified_hit | checked_no_verified_hit |
| 5 | Pierson Jones | Task 12 principal author | UC Irvine / practice | https://garciastructural.com/our-team/ | checked_partial | checked_no_verified_hit | checked_no_verified_hit |

## Notes

### John Wallace
- `preferred_topic_match_order`:
  - `core_wall_tower_with_podium`
  - `backstay_effect`
  - `transfer_diaphragms`
  - `below_grade_structure`
- `checked_subtargets`:
  - `https://seas.ucla.edu/~wallace/peer_center.htm`
  - `https://seas.ucla.edu/~wallace/research.htm`
  - `https://seas.ucla.edu/~wallace/earthquakes.htm`
- `publication_cv_candidates`:
  - `research_page` | `https://seas.ucla.edu/~wallace/research.htm` | `checked_partial` | Research page checked; no transfer podium benchmark-native package surfaced.
    - `whitelist_suffixes`: `.pdf`, `.zip`
    - `whitelist_keywords`: `transfer`, `podium`, `backstay`, `girder`, `diaphragm`, `task12`, `tbi`
    - `follow_pdf_recursively`: `True`
  - `peer_center_page` | `https://seas.ucla.edu/~wallace/peer_center.htm` | `checked_partial` | PEER center page checked; no task-level model package surfaced.
    - `whitelist_suffixes`: `.pdf`, `.zip`
    - `whitelist_keywords`: `transfer`, `podium`, `task12`, `tbi`, `benchmark`
    - `follow_pdf_recursively`: `True`
- `personal_page`: `checked_partial` | `https://seas.ucla.edu/~wallace/` | Official UCLA faculty page confirmed; peer_center/research/earthquakes subpages were also checked, but no benchmark-native transfer podium package surfaced.
- `lab_site`: `checked_partial` | `https://www.seas.ucla.edu/` | Official UCLA domain confirmed; no benchmark-native transfer podium package identified on accessible lab pages in this round.
- `github_raw`: `checked_no_verified_hit` | No verified benchmark-native transfer podium OpenSees package located on public GitHub in this round.
- `supplemental_zip`: `checked_no_verified_hit` | No supplemental zip tied to the official PEER transfer podium case located in this round.

### Zeynep Tuna
- `preferred_topic_match_order`:
  - `backstay_effect`
  - `transfer_diaphragms`
  - `core_wall_tower_with_podium`
- `personal_page`: `checked_partial` | No authoritative UCLA-era project page with benchmark-native transfer podium package identified in this round.
- `lab_site`: `checked_partial` | Public academic traces exist, but not a verified task-level model package source.
- `github_raw`: `checked_no_verified_hit` | No verified GitHub raw benchmark-native package found.
- `supplemental_zip`: `checked_no_verified_hit` | No public supplemental zip found for the transfer podium task.

### Tony Yang
- `preferred_topic_match_order`:
  - `multiple_towers_single_podium`
  - `core_wall_tower_with_podium`
  - `transfer_diaphragms`
  - `transfer_girders`
- `checked_subtargets`:
  - `https://smartstructures.civil.ubc.ca/opensees-navigator/`
  - `https://smartstructures.civil.ubc.ca/ilee-eerf-collaboration/prototype-building/`
- `publication_cv_candidates`:
  - `research_area_page` | `https://civil.ubc.ca/research/research-areas/structural-earthquake-engineering/` | `checked_partial` | Structural & Earthquake Engineering area page checked as publication/research hub; no transfer podium package surfaced.
    - `whitelist_suffixes`: `.pdf`, `.zip`
    - `whitelist_keywords`: `transfer`, `podium`, `benchmark`, `opensees`, `tower`
    - `follow_pdf_recursively`: `True`
  - `opensees_navigator_page` | `https://smartstructures.civil.ubc.ca/opensees-navigator/` | `checked_partial` | OpenSees Navigator page checked; useful tool context, but not the target transfer podium benchmark package.
    - `whitelist_suffixes`: `.pdf`, `.zip`, `.tcl`, `.inp`
    - `whitelist_keywords`: `opensees`, `transfer`, `podium`, `prototype`, `tower`
    - `follow_pdf_recursively`: `True`
- `personal_page`: `checked_found` | `https://civil.ubc.ca/tony-yang/` | Official UBC faculty page confirmed.
- `lab_site`: `checked_found` | `https://smartstructures.civil.ubc.ca/about/` | Official Smart Structures lab page confirmed; OpenSees Navigator and Prototype Building project pages were also checked, but no transfer podium benchmark-native package surfaced.
- `github_raw`: `checked_no_verified_hit` | No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.
- `supplemental_zip`: `checked_no_verified_hit` | No supplemental zip for the transfer podium benchmark located in this round.

### Farzin Zareian
- `preferred_topic_match_order`:
  - `transfer_girders`
  - `multiple_towers_single_podium`
  - `core_wall_tower_with_podium`
- `publication_cv_candidates`:
  - `legacy_publications_page` | `https://ics.uci.edu/~hjafarpo/Farzin/Publications.htm` | `checked_partial` | Legacy publications page checked as likely supplemental/publication hub; no verified transfer podium package surfaced in this round.
    - `whitelist_suffixes`: `.pdf`, `.zip`
    - `whitelist_keywords`: `transfer`, `podium`, `task12`, `tbi`, `tower`
    - `follow_pdf_recursively`: `True`
  - `legacy_profile_page` | `https://ics.uci.edu/~hjafarpo/Farzin/Dr.Zareian.htm` | `checked_partial` | Legacy profile page checked; no task-level benchmark package surfaced.
    - `whitelist_suffixes`: `.pdf`, `.zip`
    - `whitelist_keywords`: `transfer`, `podium`, `tower`, `benchmark`
    - `follow_pdf_recursively`: `True`
- `personal_page`: `checked_found` | `https://engineering.uci.edu/users/farzin-zareian` | Official UCI faculty page confirmed.
- `lab_site`: `checked_found` | `https://ics.uci.edu/~hjafarpo/Farzin/Dr.Zareian.htm` | Legacy personal/lab-style page confirmed; no transfer podium benchmark package surfaced.
- `github_raw`: `checked_no_verified_hit` | No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.
- `supplemental_zip`: `checked_no_verified_hit` | No supplemental zip for the transfer podium benchmark located in this round.

### Pierson Jones
- `preferred_topic_match_order`:
  - `transfer_girders`
  - `multiple_towers_single_podium`
  - `backstay_effect`
- `personal_page`: `checked_found` | `https://garciastructural.com/our-team/` | Professional biography confirmed computational seismic modeling of tall steel buildings.
- `lab_site`: `checked_partial` | No active academic lab page with task-level source package found in this round.
- `github_raw`: `checked_no_verified_hit` | No verified GitHub raw package found in this round; unauthenticated GitHub code search API returned 401 and public search-engine queries produced no verified raw hit.
- `supplemental_zip`: `checked_no_verified_hit` | No supplemental zip for the transfer podium benchmark located in this round.
