# Irregular Benchmark Receipt: transfer_podium_tower

- `benchmark_readiness_tier`: `bridged`
- `execution_status`: `ready`
- `input_artifact`: `implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/model.json`
- `source_origin_class`: `repo_local_bridged_irregular`
- `recommended_source_kind`: `repo_local_bridged`
- `recommended_evidence_class`: `repo_local_bridged_graph`
- `readiness_statement`: `Local input is executable, but it is a bridged transformation of an upstream benchmark or source model.`
- `non_overstatement_guardrail`: `Bridged means adapter or conversion evidence exists and must not be presented as the untouched canonical source.`

## KPI

## Why Still Bridged

- `current_source_id`: `transfer_podium_tower_proxy_local`
- `native_support_summary`: `native MEB support via midas_multifamily_building_meb_local; official benchmark documentation via peer_transfer_podium_tower_remote`
- `official_support_summary`: `official benchmark documentation via peer_transfer_podium_tower_remote`
- `next_source_id`: `peer_transfer_podium_tower_remote`
- `next_source_url`: `https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf`
- `blocker`: `Canonical benchmark model has not been collected yet; current local evidence is a bridged decoded-preview graph with native MEB support, while official PEER documentation is collected separately as reference-only evidence.`
- `audit_note`: `official PEER docs checked, native package not found as of 2026-04-05`
- `source_hunt_summary`: `Checked John Wallace UCLA peer_center/research/earthquakes pages and Tony Yang Smart Structures OpenSees Navigator/prototype-building pages, plus Wallace/Yang/Zareian publication or research hubs. Task 12 transfer focus topics include multiple towers on a single podium, backstay effect, core-wall tower with podium having separate foundation system, transfer diaphragms, and transfer girders. Official documentation was confirmed, but no benchmark-native transfer package surfaced. Public GitHub code search required authentication and no verified raw hit surfaced through public search-engine queries.`

## Transfer Hunt Summary

- `ledger_json`: `implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.json`
- `ledger_md`: `implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.md`
- `ledger_audit_statement`: `official PEER docs checked, native package not found as of 2026-04-05`
- `search_sequence`: `author_personal_page>lab_site>github_raw>supplemental_zip`
- `scan_report_status`: `present`

### Reference PDF Hunt

- `candidate_count`: `9`
- `author_count`: `3`
- `recursive_reference_scan_count`: `9`
- `recursive_raw_candidate_count`: `0`
- `samples`: `Farzin Zareian: MSE 298 Seminars (https://engineering.uci.edu/files/fall_2024-_seminar_series_flyer.pdf) ; Farzin Zareian: Travel Tips (https://engineering.uci.edu/files/travelers-guidelines-2022.pdf) ; Farzin Zareian: Walking Map (http://www.eng.uci.edu/files/UCI_walking_map.pdf)`

### Author Whitelist Scan

- `candidate_count`: `0`
- `author_count`: `0`
- `whitelist_followup_scan_count`: `14`
- `topic`: `multiple towers on a single podium` | Matches the target transfer/podium benchmark family and narrows supplemental hunts to podium-coupled tower publications.
- `topic`: `Backstay Effect` | Strong transfer-podium modeling keyword for diaphragm and basement interaction source hunts.
- `topic`: `Core-wall tower with podium having separate foundation system` | Figure/title directly aligned with transfer-podium benchmark geometry and SSI framing.
- `topic`: `transfer diaphragms` | Useful keyword for supplemental zips, appendices, and model package names.
- `topic`: `transfer girders` | Targets vertical discontinuity cases where columns terminate on transfer girders.
- `topic`: `below-grade structure` | Narrows podium/basement interaction package hunts and figure appendix checks.
- `author`: `John Wallace` | `priority=1` | `subtargets=3` | `cv_candidates=2`
- `author`: `Zeynep Tuna` | `priority=2` | `subtargets=0` | `cv_candidates=0`
- `author`: `Tony Yang` | `priority=3` | `subtargets=2` | `cv_candidates=2`
- `author`: `Farzin Zareian` | `priority=4` | `subtargets=0` | `cv_candidates=2`
- `author`: `Pierson Jones` | `priority=5` | `subtargets=0` | `cv_candidates=0`
- `scan_report_json`: `implementation/phase1/open_data/irregular/transfer_podium_raw_source_candidate_scan_report.json`
- `scan_report_md`: `implementation/phase1/open_data/irregular/transfer_podium_raw_source_candidate_scan_report.md`
- `source_hunt_ledger_json`: `implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.json`
- `source_hunt_ledger_md`: `implementation/phase1/open_data/irregular/transfer_podium_source_hunt_ledger.md`

- `transfer-story demand ratio; column discontinuity penalty; load-path continuity`

## Supporting Artifacts

- `/home/betelgeuze/건축구조분석/implementation/phase1/open_data/irregular/collected/artifacts/transfer_podium_tower_proxy_local/model.json` | exists=`True` | sha256=`09c40b61837fdcd2b5157ebfbc604fe74111ab45b7fffd9727729432f96d4ef5`
- `/home/betelgeuze/건축구조분석/implementation/phase1/open_data/irregular/collected/artifacts/midas_multifamily_building_meb_local/C07_T01_P000_RC_01_┤┘░í▒╕_┴╓┼├.meb` | exists=`True` | sha256=`36b60663aca159c066c51f2c13bd0076ae4d05056e0a86e9e424a90f046ec07a`
- `/home/betelgeuze/건축구조분석/implementation/phase1/open_data/irregular/collected/artifacts/peer_transfer_podium_tower_remote/final_tbi_report_10.9.2017_0.pdf` | exists=`True` | sha256=`2d8ba0cc836ab3f6f488d37c534f6dfd6d3a1133761a1ef3ed0572b74849e510`
- `implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/bridge_report.json` | exists=`True` | sha256=`81acb0cc41728bde300f8f46de2bac5db140cb9d4caaf93b77951f59e12d0062`
- `implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/dataset.npz` | exists=`True` | sha256=`956c36520a37f15c463983861ecc7e0e616fc0e5ec268b1c16606e6b681858de`
- `implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_multifamily_building_archive/adapter_manifest.json` | exists=`True` | sha256=`173c714f5199a63d9ae201603988ec8e0da45a7e630b18c07b214b9cfdd0299e`
- `implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_multifamily_building_archive/meb_decoded_inventory_report.json` | exists=`True` | sha256=`39d5c26df634db547e42594cc63b0625a3e5a9870c4f3b0484a0fab2fb05bf7e`
- `implementation/phase1/open_data/midas/quality_corpus/raw/midas_support_multifamily_building_archive.zip` | exists=`True` | sha256=`eed5b5f99fca712ad210353e24c37d7ab01a895017e3a7235a488b671ad81263`
- `implementation/phase1/open_data/irregular/collected/reports/midas_multifamily_building_meb_local.json` | exists=`True` | sha256=`ce742eaddcba1648d02f1d7dd007813226ffa728b6944390b24215e06f943582`
- `implementation/phase1/open_data/irregular/collected/reports/peer_transfer_podium_tower_remote.json` | exists=`True` | sha256=`f44042f413b5e9559abfce0f553ccb38c57623c13c4aa419d06dfd6aecebecc3`
- `implementation/phase1/open_data/irregular/collected/reports/transfer_podium_tower_proxy_local.json` | exists=`True` | sha256=`081ed0bd7e6bef0e3acee593b69fd540c97e6916fc3af9876cb8c65fe10d13ad`
- `implementation/phase1/open_data/irregular/collected/artifacts/midas_multifamily_building_meb_local/source_metadata.json` | exists=`True` | sha256=`03f90ffcd3cd7741531065ad8443a9dbff6277bfd5d18b49a7b276e69f52d12d`
- `implementation/phase1/open_data/irregular/collected/artifacts/peer_transfer_podium_tower_remote/source_metadata.json` | exists=`True` | sha256=`d8e9445000bf9f81646786da92cfac5c50b569e828355a76823fa682c17c13e1`
- `implementation/phase1/open_data/irregular/collected/artifacts/transfer_podium_tower_proxy_local/source_metadata.json` | exists=`True` | sha256=`9945c897c4d4c4822bec7180bb4a523844bbc4ed69013077b1ca6ed23d1cd6d8`
