#!/usr/bin/env python3
"""Generate a deterministic irregular-structure source catalog and triage outputs."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
IRREGULAR_DIR = REPO_ROOT / "implementation/phase1/open_data/irregular"
DEFAULT_CATALOG_PATH = IRREGULAR_DIR / "irregular_structure_source_catalog.json"
DEFAULT_TRIAGE_PATH = IRREGULAR_DIR / "irregular_structure_triage_report.json"
DEFAULT_PRIORITY_PATH = IRREGULAR_DIR / "priority_irregular_structure_families.json"
DEFAULT_SOURCE_SEED_PATH = IRREGULAR_DIR / "irregular_structure_source_seed.json"
SCHEMA_VERSION = "1.0"
CATALOG_VERSION = "0.4.0"
PURPOSE = (
    "Curated irregular-structure source catalog for authority-grade benchmark discovery, "
    "native-roundtrip candidate scouting, and AI-learning oriented irregular-topology intake."
)
BRIDGED_SOURCE_KIND = "repo_local_bridged"
BRIDGED_EVIDENCE_CLASS = "repo_local_bridged_graph"

SOURCE_ROWS: list[dict[str, Any]] = [
    {
        "source_id": "peer_transfer_podium_tower_remote",
        "title": "PEER transfer podium tower benchmark candidate",
        "family_id": "transfer_podium_tower",
        "source_kind": "official_remote_candidate",
        "formats": ["report_pdf", "model_text"],
        "source_urls": [
            "https://peer.berkeley.edu/research/building-systems/tall-buildings-initiative",
            "https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf",
            "https://peer.berkeley.edu/sites/default/files/final_tbi_report_10.9.2017_0.pdf",
        ],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "official_benchmark_remote",
        "metadata": {
            "official_task_url": "https://peer.berkeley.edu/research/building-systems/tall-buildings-initiative/tasks",
            "official_task12_report_url": "https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf",
            "official_final_report_url": "https://peer.berkeley.edu/sites/default/files/final_tbi_report_10.9.2017_0.pdf",
        },
        "notes": "High-value authority benchmark candidate for transfer-story load-path discontinuity.",
    },
    {
        "source_id": "transfer_podium_tower_proxy_local",
        "title": "Transfer podium tower local bridged graph from MIDAS multifamily building archive",
        "family_id": "transfer_podium_tower",
        "source_kind": BRIDGED_SOURCE_KIND,
        "formats": ["json_graph", "npz"],
        "local_path": "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/model.json",
        "companion_paths": [
            "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/dataset.npz",
            "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_multifamily_building_archive_decoded_preview/bridge_report.json",
        ],
        "source_urls": ["https://support.midasuser.com/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": BRIDGED_EVIDENCE_CLASS,
        "metadata": {
            "canonical_promotion_priority": 1,
            "canonical_promotion_status": "source_hunt_pending",
            "canonical_promotion_next_source_id": "peer_transfer_podium_tower_remote",
            "canonical_promotion_next_source_url": "https://peer.berkeley.edu/sites/default/files/webpeer-2011-05-tbi_task12.pdf",
            "canonical_promotion_blocker": "Canonical benchmark model has not been collected yet; current local evidence is a bridged decoded-preview graph with native MEB support, while official PEER documentation is collected separately as reference-only evidence.",
        },
        "notes": "Execution-ready bridged local graph derived from a decoded MIDAS support archive preview. Stronger than a proxy, but still not a canonical PEER replacement.",
    },
    {
        "source_id": "midas_multifamily_building_meb_local",
        "title": "MIDAS multifamily building original native MEB",
        "family_id": "transfer_podium_tower",
        "source_kind": "repo_local_native_binary_support",
        "priority": 0,
        "formats": ["meb", "zip_bundle"],
        "local_path": "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_multifamily_building_archive/C07_T01_P000_RC_01_┤┘░í▒╕_┴╓┼├.meb",
        "companion_paths": [
            "implementation/phase1/open_data/midas/quality_corpus/raw/midas_support_multifamily_building_archive.zip",
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_multifamily_building_archive/adapter_manifest.json",
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_multifamily_building_archive/meb_decoded_inventory_report.json"
        ],
        "source_urls": ["https://support.midasuser.com/"],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "repo_local_native_binary_model",
        "metadata": {
            "native_binary_header": "MBDG",
            "alternate_authority_candidate_source_id": "peer_transfer_podium_tower_remote",
            "benchmark_canonical_eligible": False,
            "native_local_scope": "native_roundtrip_only",
            "benchmark_canonical_blocker": "Original MIDAS native binary is useful for roundtrip/native-source coverage, but this track still requires a benchmark-native IFC/TCL/MGT/INP source for canonical authority-grade promotion."
        },
        "notes": "Original MIDAS native binary model harvested from the public multifamily building support archive. Keep this for native roundtrip coverage, but do not treat it as canonical for the authority-grade irregular benchmark track until an original benchmark-native IFC/TCL/MGT/INP source is harvested.",
    },
    {
        "source_id": "nheri_soft_story_podium_remote",
        "title": "DesignSafe OpenSees pilotis RC frame package",
        "family_id": "soft_story_podium_tower",
        "source_kind": "public_native_source",
        "formats": ["tcl", "model_text"],
        "source_urls": [
            "https://www.designsafe-ci.org/api/publications/v2/PRJ-4831",
            "https://www.designsafe-ci.org/data/browser/public/designsafe.storage.published/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7%20Infilled%20Frame/Fly%20Ash%20Brick%20Infill/Pilotis",
        ],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "official_benchmark_native_text",
        "metadata": {
            "designsafe_project_id": "PRJ-4831",
            "designsafe_listing_path": "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis",
            "designsafe_primary_preview_path": "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/main.tcl",
            "designsafe_preview_paths": [
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/analysis_steps.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/definitions.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/elements.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/main.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/materials.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/nodes.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/RCJointModel3D.tcl",
                "/published-data/PRJ-4831/Simulation--fly-ash-brick-and-aac-block-masonry-infilled-rc-frame-buildings-opensees-models-and-responses/data/Model--opensees-model-data/data/G+7 Infilled Frame/Fly Ash Brick Infill/Pilotis/sections.tcl",
            ],
            "provider_asset_kind": "official_native_text_preview_bundle",
            "designsafe_model_variant": "G+7 Infilled Frame / Fly Ash Brick Infill / Pilotis",
        },
        "notes": "Published DesignSafe OpenSees package for a G+7 pilotis soft-story RC frame. This is benchmark-native TCL text and is eligible for canonical promotion once harvested locally.",
    },
    {
        "source_id": "soft_story_podium_tower_proxy_local",
        "title": "Soft-story podium tower local bridged graph from MIDAS neighborhood facility archive",
        "family_id": "soft_story_podium_tower",
        "source_kind": BRIDGED_SOURCE_KIND,
        "formats": ["json_graph", "npz"],
        "local_path": "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_neighborhood_facility_archive_decoded_preview/model.json",
        "companion_paths": [
            "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_neighborhood_facility_archive_decoded_preview/dataset.npz",
            "implementation/phase1/open_data/midas/quality_corpus/bridged/midas_support_neighborhood_facility_archive_decoded_preview/bridge_report.json",
        ],
        "source_urls": ["https://support.midasuser.com/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": BRIDGED_EVIDENCE_CLASS,
        "metadata": {
            "canonical_promotion_priority": 2,
            "canonical_promotion_status": "source_hunt_pending",
            "canonical_promotion_next_source_id": "nheri_soft_story_podium_remote",
            "canonical_promotion_next_source_url": "https://www.designsafe-ci.org/api/publications/v2/PRJ-4831",
            "canonical_promotion_blocker": "Measured or model-text upstream source is not collected locally; current local evidence is a bridged decoded-preview graph.",
        },
        "notes": "Execution-ready bridged local graph derived from a decoded MIDAS support archive preview. Stronger than a proxy, but still not the measured NHERI source.",
    },
    {
        "source_id": "midas_neighborhood_facility_meb_local",
        "title": "MIDAS neighborhood facility original native MEB",
        "family_id": "soft_story_podium_tower",
        "source_kind": "repo_local_native_binary_support",
        "priority": 0,
        "formats": ["meb", "zip_bundle"],
        "local_path": "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_neighborhood_facility_archive/C07_T02_P000_RC_02_▒┘╕░╗²╚░╜├.meb",
        "companion_paths": [
            "implementation/phase1/open_data/midas/quality_corpus/raw/midas_support_neighborhood_facility_archive.zip",
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_neighborhood_facility_archive/adapter_manifest.json",
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_neighborhood_facility_archive/meb_decoded_inventory_report.json"
        ],
        "source_urls": ["https://support.midasuser.com/"],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "repo_local_native_binary_model",
        "metadata": {
            "native_binary_header": "MBDG",
            "alternate_authority_candidate_source_id": "nheri_soft_story_podium_remote",
            "benchmark_canonical_eligible": False,
            "native_local_scope": "native_roundtrip_only",
            "benchmark_canonical_blocker": "Original MIDAS native binary is useful for roundtrip/native-source coverage, but this track still requires a benchmark-native IFC/TCL/MGT/INP source for canonical authority-grade promotion."
        },
        "notes": "Original MIDAS native binary model harvested from the public neighborhood facility support archive. Keep this for native roundtrip coverage, but do not treat it as canonical for the authority-grade irregular benchmark track until an original benchmark-native IFC/TCL/MGT/INP source is harvested.",
    },
    {
        "source_id": "tpu_interference_highrise_local",
        "title": "TPU interference highrise response proxy",
        "family_id": "torsionally_eccentric_core_tower",
        "source_kind": "repo_local_proxy",
        "formats": ["csv_tables"],
        "local_path": "implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.csv",
        "source_urls": ["https://db.wind.arch.t-kougei.ac.jp/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "repo_local_proxy",
        "notes": "Wind-response proxy for asymmetric tall-building response patterns; useful for learning, not a direct structural benchmark replacement.",
    },
    {
        "source_id": "offset_core_megatall_torsion_bridged_local",
        "title": "Offset-core megatall torsion bridged graph",
        "family_id": "torsionally_eccentric_core_tower",
        "source_kind": BRIDGED_SOURCE_KIND,
        "formats": ["json_graph", "npz"],
        "local_path": "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/model.json",
        "companion_paths": [
            "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/dataset.npz",
            "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/bridge_report.json",
        ],
        "source_urls": [
            "https://github.com/yexiang92/opstool",
            "http://www.luxinzheng.net/download/OpenSEES/Mega-tall_Building_Benchmark_OpenSees.htm",
        ],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": BRIDGED_EVIDENCE_CLASS,
        "metadata": {
            "canonical_promotion_priority": 3,
            "canonical_promotion_status": "promoted_to_canonical",
            "canonical_promotion_promoted_source_id": "luxinzheng_megatall_tcl_model1_local",
            "canonical_promotion_blocker": "Resolved by harvested public OpenSees TCL source from the published 606 m mega-tall building benchmark package.",
        },
        "notes": "Execution-ready bridged graph for offset-core torsion and modal-coupling rehearsal. This remains useful for bridge-evidence runs, but canonical promotion is now backed by a harvested public TCL source.",
    },
    {
        "source_id": "luxinzheng_megatall_tcl_model1_local",
        "title": "OpenSees 606 m mega-tall building Model 1 TCL",
        "family_id": "torsionally_eccentric_core_tower",
        "source_kind": "public_native_source",
        "priority": 0,
        "formats": ["tcl", "zip", "pdf"],
        "local_path": "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/extracted/OpenSees_Model/Model1/opensees.tcl",
        "companion_paths": [
            "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/OpenSees-Mega-tall-Building.zip",
            "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/extracted/OpenSees_Model/Model2/opensees.tcl",
            "implementation/phase1/open_data/irregular/harvested/torsionally_eccentric_core_tower/extracted/Introduction of the benchmark model-v0.1b.pdf"
        ],
        "source_urls": [
            "http://www.luxinzheng.net/download/OpenSEES/Mega-tall_Building_Benchmark_OpenSees.htm",
            "http://www.thu-civil.net/download/OpenSees-Mega-tall-Building.zip"
        ],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "official_benchmark_native_text",
        "metadata": {
            "benchmark_variant": "Model1",
            "upstream_provider": "Tsinghua University benchmark page referenced by opstool docs",
            "model_mesh_note": "Model 1 coarse mesh; package also includes Model 2 refined mesh."
        },
        "notes": "Harvested public OpenSees TCL package for the 606 m mega-tall building benchmark. This is benchmark-native model text and qualifies as canonical evidence for the torsionally eccentric core tower family.",
    },
    {
        "source_id": "peer_setback_tower_remote",
        "title": "PEER setback tower candidate",
        "family_id": "setback_tower",
        "source_kind": "official_remote_candidate",
        "formats": ["report_pdf", "model_text"],
        "source_urls": ["https://peer.berkeley.edu/research/building-systems/tall-buildings-initiative"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "official_benchmark_remote",
        "notes": "Strong candidate for mode-shape discontinuity and mass/stiffness redistribution across setbacks.",
    },
    {
        "source_id": "setback_tower_proxy_local",
        "title": "Setback tower local proxy from twisted tapered IFC",
        "family_id": "setback_tower",
        "source_kind": "collected_remote_proxy",
        "formats": ["ifc"],
        "local_path": "implementation/phase1/open_data/irregular/collected/artifacts/twisted_tapered_tower_remote/DS3_TalTech_V4.ifc",
        "source_urls": ["https://zenodo.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "geometry_exchange_remote",
        "notes": "Execution-ready local geometry proxy for stiffness/mass redistribution across tapered setback-like towers. Geometry-only proxy, not a canonical PEER setback model.",
    },
    {
        "source_id": "peer_reentrant_corner_remote",
        "title": "PEER re-entrant corner tower candidate",
        "family_id": "reentrant_corner_tower",
        "source_kind": "official_remote_candidate",
        "formats": ["report_pdf", "ifc"],
        "source_urls": ["https://peer.berkeley.edu/"],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "official_reference_remote",
        "notes": "Good plan-irregularity family for diaphragm discontinuity and corner demand concentration.",
    },
    {
        "source_id": "reentrant_corner_tower_proxy_local",
        "title": "Re-entrant corner local proxy from skewed column IFC",
        "family_id": "reentrant_corner_tower",
        "source_kind": "collected_remote_proxy",
        "formats": ["ifc"],
        "local_path": "implementation/phase1/open_data/irregular/collected/artifacts/skewed_column_frame_remote/a4.ifc",
        "source_urls": ["https://zenodo.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "geometry_exchange_remote",
        "notes": "Execution-ready plan-irregularity proxy for corner concentration and diaphragm discontinuity rehearsal. Geometry proxy only; not the canonical PEER re-entrant case.",
    },
    {
        "source_id": "opstool_606m_megatall_model_local",
        "title": "Opstool 606m megatall bridged model",
        "family_id": "outrigger_megatall_offset_core",
        "source_kind": "repo_local_bridged",
        "formats": ["json_graph", "npz"],
        "local_path": "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/model.json",
        "companion_paths": [
            "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/dataset.npz",
            "implementation/phase1/open_data/megastructure/bridged/opstool_606m_megatall_model/bridge_report.json"
        ],
        "source_urls": ["https://github.com/utopiatek/opstool"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "repo_local_bridged_graph",
        "notes": "Best local megatall graph proxy for outrigger and offset-core style learning and benchmark rehearsal.",
    },
    {
        "source_id": "scbf16b_shell_beam_mix_local",
        "title": "SCBF16B shell-beam mixed OpenSees model",
        "family_id": "discontinuous_braced_frame_tower",
        "source_kind": "repo_local_source",
        "formats": ["tcl"],
        "local_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
        "source_urls": ["https://opensees.berkeley.edu/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "repo_local_text_model",
        "notes": "Useful local text model for shell-beam mixed lateral systems and brace discontinuity proxy tasks.",
    },
    {
        "source_id": "amaelkady_constructbrace_github_remote",
        "title": "ConstructBrace OpenSees GitHub raw proxy",
        "family_id": "discontinuous_braced_frame_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["tcl"],
        "source_urls": ["https://github.com/amaelkady/OpenSEES_Models_CBF"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "academic_raw_model_remote",
        "metadata": {
            "github_download_url": "https://raw.githubusercontent.com/amaelkady/OpenSEES_Models_CBF/main/Models%20and%20Tcl%20Files/ConstructBrace.tcl",
            "github_api_url": "https://api.github.com/repos/amaelkady/OpenSEES_Models_CBF/contents/Models%20and%20Tcl%20Files",
        },
        "notes": "Direct GitHub raw Tcl proxy for brace-driven irregularity workflows; useful for collector and parser coverage.",
    },
    {
        "source_id": "amaelkady_scbf16cg_github_remote",
        "title": "SCBF16CG OpenSees GitHub raw benchmark candidate",
        "family_id": "discontinuous_braced_frame_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["tcl"],
        "source_urls": ["https://api.github.com/repos/amaelkady/OpenSEES_Models_CBF/contents/Models%20and%20Tcl%20Files"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "academic_raw_model_remote",
        "metadata": {
            "github_download_url": "https://raw.githubusercontent.com/amaelkady/OpenSEES_Models_CBF/main/Models%20and%20Tcl%20Files/SCBF16CG.tcl",
            "github_api_url": "https://api.github.com/repos/amaelkady/OpenSEES_Models_CBF/contents/Models%20and%20Tcl%20Files",
            "provider_asset_kind": "opensees_tcl_benchmark",
        },
        "notes": "Direct GitHub raw Tcl benchmark to widen irregular braced-frame collection beyond helper-only brace construction scripts.",
    },
    {
        "source_id": "hanging_column_tower_remote",
        "title": "Hanging-column tower benchmark candidate",
        "family_id": "hanging_column_podium_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["report_pdf", "ifc"],
        "source_urls": ["https://www.designsafe-ci.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "academic_appendix_remote",
        "notes": "Suspended floor and hanging-column systems are visually strong and provide reverse load-path examples.",
    },
    {
        "source_id": "diagrid_exoskeleton_remote",
        "title": "Diagrid exoskeleton asymmetric tower candidate",
        "family_id": "diagrid_exoskeleton_asymmetric_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "json_graph"],
        "source_urls": ["https://www.ctbuh.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "academic_geometry_remote",
        "notes": "Good for perimeter-stiffness reasoning and non-orthogonal member graph learning.",
    },
    {
        "source_id": "split_core_linked_towers_remote",
        "title": "Split-core linked towers candidate",
        "family_id": "split_core_linked_towers",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "dxf"],
        "source_urls": ["https://www.ctbuh.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "concept_geometry_remote",
        "notes": "Linked towers and skybridges are strong coupled-system learning cases even when benchmark maturity is limited.",
    },
    {
        "source_id": "cantilevered_upper_volume_remote",
        "title": "Cantilevered upper-volume tower candidate",
        "family_id": "cantilevered_upper_volume_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "dxf"],
        "source_urls": ["https://www.structurae.net/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "concept_geometry_remote",
        "notes": "Good overhang and load-reversal family; needs benchmark-quality response data later.",
    },
    {
        "source_id": "vertical_mass_jump_remote",
        "title": "Vertical mass jump tower candidate",
        "family_id": "vertical_mass_jump_tower",
        "source_kind": "official_remote_candidate",
        "formats": ["sensor_csv", "metadata_json"],
        "source_urls": ["https://www.usgs.gov/programs/earthquake-hazards/nsmp-national-strong-motion-project"],
        "authority_fit": "high",
        "ai_learning_fit": "very-high",
        "evidence_class": "measured_response_remote",
        "notes": "Measured building-response track for mass discontinuity and mode-shape shift.",
    },
    {
        "source_id": "atrium_void_ring_remote",
        "title": "Atrium void ring tower candidate",
        "family_id": "atrium_void_ring_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "json_graph"],
        "source_urls": ["https://www.buildingsmart.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "bim_geometry_remote",
        "notes": "Large diaphragm voids are excellent for graph learning and diaphragm force-flow tracing.",
    },
    {
        "source_id": "twisted_tapered_tower_remote",
        "title": "Twisted tapered tower candidate",
        "family_id": "twisted_tapered_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "iges", "step"],
        "source_urls": ["https://www.rhino3d.com/inside/revit/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "geometry_exchange_remote",
        "metadata": {
            "zenodo_download_url": "https://zenodo.org/records/15782433/files/DS3_TalTech_V4.ifc?download=1",
            "provider_asset_kind": "ifc_geometry_proxy",
        },
        "notes": "Strong geometry-irregularity family for shape-aware AI models and meshing workflows.",
    },
    {
        "source_id": "sloped_site_stepped_podium_remote",
        "title": "Sloped-site stepped podium tower candidate",
        "family_id": "sloped_site_stepped_podium_tower",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "dxf"],
        "source_urls": ["https://www.structurae.net/"],
        "authority_fit": "medium",
        "ai_learning_fit": "high",
        "evidence_class": "site_geometry_remote",
        "notes": "Useful family for terrain-driven podium stepping and nonuniform support conditions.",
    },
    {
        "source_id": "skewed_column_frame_remote",
        "title": "Skewed-column frame candidate",
        "family_id": "skewed_column_frame",
        "source_kind": "academic_remote_candidate",
        "formats": ["ifc", "step"],
        "source_urls": ["https://www.buildingsmart.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "geometry_exchange_remote",
        "metadata": {
            "zenodo_download_url": "https://zenodo.org/records/5047709/files/a4.ifc?download=1",
            "provider_asset_kind": "ifc_geometry_proxy",
        },
        "notes": "Good non-orthogonal frame family for local-coordinate and support-skew learning.",
    },
    {
        "source_id": "gtc_public_bridge_bearing_c04_local",
        "title": "GTC public bridge bearing C04 raw MIDAS model",
        "family_id": "bridge_skewed_support_span",
        "source_kind": "public_native_source",
        "formats": ["mgt"],
        "local_path": "implementation/phase1/open_data/midas/public_native_corpus/raw/gtc_public_bridge_bearing_c04.mgt",
        "source_urls": ["https://gtc.midasuser.com/"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "public_native_mgt",
        "notes": "Current best native MIDAS skew-support bridge source for real roundtrip and authority-facing bridge write-back validation.",
    },
    {
        "source_id": "gtc_public_bridge_section_a3_local",
        "title": "GTC public curved bridge section A3 raw MIDAS model",
        "family_id": "curved_plan_bridge_torsion",
        "source_kind": "public_native_source",
        "formats": ["mgt"],
        "local_path": "implementation/phase1/open_data/midas/public_native_corpus/raw/gtc_public_bridge_section_a3.mgt",
        "source_urls": ["https://gtc.midasuser.com/"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "public_native_mgt",
        "notes": "Public raw MIDAS bridge section with curved-plan potential and direct native write-back value.",
    },
    {
        "source_id": "gtc_public_bridge_section_e1_03_local",
        "title": "GTC public curved bridge section E1-03 raw MIDAS model",
        "family_id": "curved_plan_bridge_torsion",
        "source_kind": "public_native_source",
        "formats": ["mgt"],
        "local_path": "implementation/phase1/open_data/midas/public_native_corpus/raw/gtc_public_bridge_section_e1_03.mgt",
        "source_urls": ["https://gtc.midasuser.com/"],
        "authority_fit": "high",
        "ai_learning_fit": "high",
        "evidence_class": "public_native_mgt",
        "notes": "Second public raw MIDAS bridge section for curved-plan bridge torsion breadth.",
    },
    {
        "source_id": "midas_fcm_bridge_archive_local",
        "title": "MIDAS support FCM bridge archive geometry proxy",
        "family_id": "curved_plan_bridge_torsion",
        "source_kind": "repo_local_proxy",
        "formats": ["mcb", "gh", "rhino_3dm"],
        "local_path": "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_beam_archive/FCM Bridge.mcb",
        "companion_paths": [
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_beam_archive/FCM Bridge_Final(v2.0.5).gh",
            "implementation/phase1/open_data/midas/quality_corpus/extracted/midas_support_beam_archive/FCM Tendon_1.3dm"
        ],
        "source_urls": ["https://gtc.midasuser.com/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "repo_local_archive_proxy",
        "notes": "Great AI-learning geometry proxy for segmental/FCM bridge authoring despite not being raw native MIDAS text.",
    },
    {
        "source_id": "iass_long_span_roof_remote",
        "title": "IASS long-span irregular roof truss candidate",
        "family_id": "long_span_irregular_roof_truss",
        "source_kind": "official_remote_candidate",
        "formats": ["ifc", "step", "report_pdf"],
        "source_urls": ["https://iass-structures.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "high",
        "evidence_class": "official_reference_remote",
        "notes": "Good route for long-span roof irregularity and snapping/bifurcation-aware shell-truss learning.",
    },
    {
        "source_id": "iass_freeform_shell_remote",
        "title": "IASS free-form shell core hybrid candidate",
        "family_id": "free_form_shell_core_hybrid",
        "source_kind": "official_remote_candidate",
        "formats": ["iges", "step", "report_pdf"],
        "source_urls": ["https://iass-structures.org/"],
        "authority_fit": "medium-high",
        "ai_learning_fit": "very-high",
        "evidence_class": "official_reference_remote",
        "notes": "Best shell-heavy family for AI shape generalization beyond orthogonal frame systems.",
    },
]


SUPPORTED_LOCAL_FORMATS = {
    "mgt",
    "inp",
    "tcl",
    "ifc",
    "dxf",
    "csv_tables",
    "step",
    "iges",
    "json_graph",
    "zip_bundle",
    "mcb",
    "meb",
    "mmbx",
    "gh",
    "rhino_3dm",
    "mat",
    "npz",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object json: {path}")
    return payload


def _load_source_seed(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("source_records")
    else:
        rows = payload
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("source seed payload must be a non-empty list of objects or an object with source_records")
    return [dict(row) for row in rows]


def _priority_families(priority_path: Path) -> list[dict[str, Any]]:
    payload = _load_json(priority_path)
    families = payload.get("families")
    if not isinstance(families, list) or not families:
        raise ValueError("priority family file must contain a non-empty families list")
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in families:
        if not isinstance(row, dict):
            raise ValueError("priority family rows must be objects")
        family_id = str(row.get("id", "")).strip()
        priority = int(row.get("priority", 0))
        if not family_id or priority < 1:
            raise ValueError("priority family rows require non-empty id and priority >= 1")
        if family_id in seen_ids:
            raise ValueError(f"duplicate family id: {family_id}")
        seen_ids.add(family_id)
        normalized.append(
            {
                "id": family_id,
                "priority": priority,
                "why_it_matters": str(row.get("why_it_matters", "")).strip(),
                "irregularity_tags": sorted({str(tag).strip() for tag in row.get("irregularity_tags", []) if str(tag).strip()}),
                "likely_formats": sorted({str(tag).strip() for tag in row.get("likely_formats", []) if str(tag).strip()}),
                "authority_fit": str(row.get("authority_fit", "")).strip() or "medium",
                "ai_learning_fit": str(row.get("ai_learning_fit", "")).strip() or "medium",
                "recommended_kpi_or_validation_angle": str(row.get("recommended_kpi_or_validation_angle", "")).strip(),
            }
        )
    return sorted(normalized, key=lambda row: (row["priority"], row["id"]))


def _format_rank(fmt: str) -> tuple[int, str]:
    preferred = [
        "mgt",
        "tcl",
        "ifc",
        "json_graph",
        "npz",
        "csv_tables",
        "dxf",
        "step",
        "iges",
        "mcb",
        "meb",
        "mmbx",
        "gh",
        "rhino_3dm",
        "mat",
        "report_pdf",
        "model_text",
        "metadata_json",
        "sensor_csv",
    ]
    try:
        return (preferred.index(fmt), fmt)
    except ValueError:
        return (len(preferred), fmt)


def _local_status(local_path: Path | None, formats: list[str]) -> str:
    if local_path is not None and local_path.exists() and local_path.is_file():
        if any(fmt in SUPPORTED_LOCAL_FORMATS for fmt in formats):
            return "local_ready"
        return "local_unclassified"
    return "remote_candidate"


def _normalize_source_rows(family_map: dict[str, dict[str, Any]], source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in source_rows:
        source_id = str(raw["source_id"]).strip()
        if source_id in seen:
            raise ValueError(f"duplicate source id: {source_id}")
        seen.add(source_id)
        family_id = str(raw["family_id"]).strip()
        if family_id not in family_map:
            raise ValueError(f"unknown family id: {family_id}")
        family = family_map[family_id]
        formats = [str(fmt).strip() for fmt in raw.get("formats", []) if str(fmt).strip()]
        if not formats:
            raise ValueError(f"source {source_id} must have at least one format")
        formats = sorted(dict.fromkeys(formats), key=_format_rank)
        local_path_value = str(raw.get("local_path", "")).strip()
        local_path = REPO_ROOT / local_path_value if local_path_value else None
        companion_paths = []
        for value in raw.get("companion_paths", []) or []:
            value_str = str(value).strip()
            if value_str:
                companion_paths.append(value_str)
        source_urls = sorted({str(url).strip() for url in raw.get("source_urls", []) if str(url).strip()})
        metadata = dict(raw.get("metadata", {}) if isinstance(raw.get("metadata"), dict) else {})
        source_kind = str(raw.get("source_kind", "seeded_candidate")).strip()
        evidence_class = str(raw.get("evidence_class", "seeded_candidate")).strip()
        source_kind, evidence_class, metadata = _promote_bridged_source_classification(
            source_kind=source_kind,
            evidence_class=evidence_class,
            local_path_value=local_path_value,
            companion_paths=companion_paths,
            metadata=metadata,
        )
        record = {
            "source_id": source_id,
            "title": str(raw.get("title", source_id)).strip(),
            "family_id": family_id,
            "priority": int(family["priority"]),
            "source_kind": source_kind,
            "formats": formats,
            "primary_format": formats[0],
            "source_urls": source_urls,
            "local_path": local_path_value,
            "local_path_exists": bool(local_path and local_path.exists() and local_path.is_file()),
            "companion_paths": companion_paths,
            "authority_fit": str(raw.get("authority_fit", family["authority_fit"])).strip() or family["authority_fit"],
            "ai_learning_fit": str(raw.get("ai_learning_fit", family["ai_learning_fit"])).strip() or family["ai_learning_fit"],
            "evidence_class": evidence_class,
            "irregularity_tags": list(family["irregularity_tags"]),
            "why_it_matters": family["why_it_matters"],
            "recommended_kpi_or_validation_angle": family["recommended_kpi_or_validation_angle"],
            "collection_status": _local_status(local_path, formats),
            "notes": str(raw.get("notes", "")).strip(),
            "metadata": metadata,
        }
        rows.append(record)
    return sorted(rows, key=lambda row: (row["priority"], row["family_id"], row["source_id"]))


def _count_by(rows: list[dict[str, Any]], key: str, label: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        counts[value] = counts.get(value, 0) + 1
    return [{label: value, "record_count": counts[value]} for value in sorted(counts, key=lambda item: (-counts[item], item))]


def _looks_bridged_path(value: object) -> bool:
    return "/bridged/" in str(value or "").replace("\\", "/").lower()


def _bridge_report_paths(companion_paths: list[str], metadata: dict[str, Any]) -> list[str]:
    candidates = [str(path).strip() for path in companion_paths if str(path).strip()]
    metadata_path = str(metadata.get("bridge_report_path", "") or "").strip()
    if metadata_path:
        candidates.append(metadata_path)
    return [path for path in candidates if Path(path).name == "bridge_report.json"]


def _resolve_repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def _bridge_evidence_metadata(companion_paths: list[str], metadata: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(metadata)
    bridge_paths = _bridge_report_paths(companion_paths, enriched)
    if bridge_paths:
        enriched["bridge_report_path"] = bridge_paths[0]
    if not bridge_paths:
        return enriched
    report_path = _resolve_repo_path(bridge_paths[0])
    if not report_path.exists() or not report_path.is_file():
        return enriched
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return enriched
    if not isinstance(payload, dict):
        return enriched
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    enriched["bridge_contract_pass"] = bool(payload.get("contract_pass", False))
    if str(payload.get("source_id", "") or "").strip():
        enriched["bridge_source_id"] = str(payload.get("source_id", "") or "").strip()
    if str(summary.get("bridge_mode", "") or "").strip():
        enriched["bridge_mode"] = str(summary.get("bridge_mode", "") or "").strip()
    if str(summary.get("preview_exactness_tier", "") or "").strip():
        enriched["bridge_exactness_tier"] = str(summary.get("preview_exactness_tier", "") or "").strip()
    return enriched


def _promote_bridged_source_classification(
    *,
    source_kind: str,
    evidence_class: str,
    local_path_value: str,
    companion_paths: list[str],
    metadata: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    enriched_metadata = _bridge_evidence_metadata(companion_paths, metadata)
    has_explicit_bridge_evidence = _looks_bridged_path(local_path_value) and bool(
        _bridge_report_paths(companion_paths, enriched_metadata)
    )
    normalized_source_kind = source_kind
    normalized_evidence_class = evidence_class
    if source_kind == "repo_local_proxy" and has_explicit_bridge_evidence:
        normalized_source_kind = BRIDGED_SOURCE_KIND
    if evidence_class == "repo_local_proxy" and has_explicit_bridge_evidence:
        normalized_evidence_class = BRIDGED_EVIDENCE_CLASS
    return normalized_source_kind, normalized_evidence_class, enriched_metadata


def _build_family_summary(families: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {family["id"]: {**family, "source_records": []} for family in families}
    for row in rows:
        grouped[row["family_id"]]["source_records"].append(row)
    out: list[dict[str, Any]] = []
    for family in families:
        family_rows = grouped[family["id"]]["source_records"]
        out.append(
            {
                **family,
                "source_record_count": len(family_rows),
                "local_ready_source_count": sum(1 for row in family_rows if row["collection_status"] == "local_ready"),
                "source_formats": sorted({fmt for row in family_rows for fmt in row["formats"]}, key=_format_rank),
                "evidence_classes": sorted({row["evidence_class"] for row in family_rows}),
            }
        )
    return out


def _build_tag_summary(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tag_counts: dict[str, int] = {}
    for family in families:
        for tag in family["irregularity_tags"]:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return [
        {"tag": tag, "family_count": tag_counts[tag]}
        for tag in sorted(tag_counts, key=lambda item: (-tag_counts[item], item))
    ]


def _level_summary(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts: dict[str, list[str]] = {}
    for row in rows:
        level = str(row.get(key, "")).strip() or "unknown"
        counts.setdefault(level, []).append(row["source_id"])
    return [
        {"level": level, "record_count": len(counts[level]), "source_ids": sorted(counts[level])}
        for level in sorted(counts, key=lambda item: (-len(counts[item]), item))
    ]


def _triage_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    native_candidates: list[dict[str, Any]] = []
    solver_candidates: list[dict[str, Any]] = []
    ai_candidates: list[dict[str, Any]] = []
    for row in rows:
        native_hit = row["primary_format"] in {"mgt", "ifc", "dxf", "mcb", "meb", "mmbx", "gh", "rhino_3dm"}
        solver_hit = row["evidence_class"] in {
            "official_benchmark_remote",
            "official_reference_remote",
            "measured_response_remote",
            "public_native_mgt",
            "repo_local_bridged_graph",
        }
        ai_hit = row["ai_learning_fit"] in {"high", "very-high"}
        base_row = {
            "source_id": row["source_id"],
            "family_id": row["family_id"],
            "priority": row["priority"],
            "primary_format": row["primary_format"],
            "collection_status": row["collection_status"],
            "evidence_class": row["evidence_class"],
        }
        if native_hit:
            native_candidates.append(base_row)
        if solver_hit:
            solver_candidates.append(base_row)
        if ai_hit:
            ai_candidates.append(base_row)
    sort_key = lambda row: (row["priority"], row["family_id"], row["source_id"])
    return {
        "native_roundtrip_candidates": sorted(native_candidates, key=sort_key),
        "solver_benchmark_candidates": sorted(solver_candidates, key=sort_key),
        "ai_learning_candidates": sorted(ai_candidates, key=sort_key),
    }


def build_catalog(
    priority_path: Path = DEFAULT_PRIORITY_PATH,
    source_rows: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    families = _priority_families(priority_path)
    family_map = {family["id"]: family for family in families}
    rows = _normalize_source_rows(family_map, source_rows or SOURCE_ROWS)
    triage = _triage_rows(rows)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "catalog_version": CATALOG_VERSION,
        "generated_at": _utc_now(),
        "purpose": PURPOSE,
        "summary": {
            "family_count": len(families),
            "source_record_count": len(rows),
            "local_ready_count": sum(1 for row in rows if row["collection_status"] == "local_ready"),
            "remote_candidate_count": sum(1 for row in rows if row["collection_status"] == "remote_candidate"),
            "authority_high_like_count": sum(1 for row in rows if row["authority_fit"] in {"high", "medium-high"}),
            "ai_high_like_count": sum(1 for row in rows if row["ai_learning_fit"] in {"high", "very-high"}),
        },
        "structure_families": _build_family_summary(families, rows),
        "source_records": rows,
        "irregularity_tags": _build_tag_summary(families),
        "authority_suitability": _level_summary(rows, "authority_fit"),
        "ai_learning_suitability": _level_summary(rows, "ai_learning_fit"),
        "per_format_summary": _count_by(rows, "primary_format", "primary_format"),
        "per_priority_summary": _count_by(rows, "priority", "priority"),
        "per_collection_status_summary": _count_by(rows, "collection_status", "collection_status"),
    }
    triage_report = {
        "schema_version": SCHEMA_VERSION,
        "catalog_version": CATALOG_VERSION,
        "generated_at": catalog["generated_at"],
        "purpose": "Triage view over the irregular-structure catalog for native-roundtrip, solver-benchmark, and AI-learning collection tracks.",
        "summary": {
            "native_roundtrip_candidate_count": len(triage["native_roundtrip_candidates"]),
            "solver_benchmark_candidate_count": len(triage["solver_benchmark_candidates"]),
            "ai_learning_candidate_count": len(triage["ai_learning_candidates"]),
            "quick_start_local_source_count": catalog["summary"]["local_ready_count"],
        },
        **triage,
    }
    return catalog, triage_report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--priority-json", default=str(DEFAULT_PRIORITY_PATH))
    parser.add_argument(
        "--seed-sources",
        default=str(DEFAULT_SOURCE_SEED_PATH) if DEFAULT_SOURCE_SEED_PATH.exists() else "",
        help="Optional JSON source-record seed. Accepts a list payload or an object containing source_records.",
    )
    parser.add_argument("--out", default=str(DEFAULT_CATALOG_PATH))
    parser.add_argument("--triage-out", default=str(DEFAULT_TRIAGE_PATH))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seed_sources = _load_source_seed(Path(args.seed_sources)) if str(args.seed_sources).strip() else None
    catalog, triage = build_catalog(Path(args.priority_json), source_rows=seed_sources)
    out_path = Path(args.out)
    triage_out_path = Path(args.triage_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    triage_out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(catalog, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    triage_out_path.write_text(json.dumps(triage, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote irregular structure source catalog: {out_path}")
    print(f"Wrote irregular structure triage report: {triage_out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
