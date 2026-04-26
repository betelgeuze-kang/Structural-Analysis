from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from implementation.phase1.generate_native_authoring_family_corpus_manifest import (
    build_native_authoring_family_corpus_manifest,
)


SCRIPT = Path("implementation/phase1/generate_native_authoring_family_corpus_manifest.py")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_family_release_artifacts(
    root: Path,
    *,
    family_id: str,
    label: str,
    description: str,
    preferred_design_family: str,
) -> None:
    family_dir = root / family_id
    _write_json(
        family_dir / "native_authoring_ops_bundle.json",
        {"contract_pass": True, "summary_line": f"{family_id} bundle"},
    )
    _write_json(
        family_dir / "native_authoring_project_registry.json",
        {"contract_pass": True, "summary_line": f"{family_id} registry"},
    )
    _write_json(
        family_dir / "native_authoring_workspace_summary.json",
        {
            "selected_family": {
                "family_id": family_id,
                "label": label,
                "description": description,
                "preferred_design_family": preferred_design_family,
                "representative_member_types": ["column", "beam"],
            }
        },
    )
    _write_json(
        family_dir / "native_authoring_solver_session.json",
        {"contract_pass": True, "summary_line": f"{family_id} solver"},
    )


def test_build_native_authoring_family_corpus_manifest_generates_linkage_surface(tmp_path: Path) -> None:
    release_root = tmp_path / "release" / "authoring" / "portfolio"
    out = release_root / "native_authoring_family_corpus_manifest.json"
    korean_catalog = tmp_path / "open_data" / "korea" / "korean_source_catalog.json"
    benchmark_catalog = tmp_path / "open_data" / "benchmark_diversification_catalog.json"
    authority_catalog = tmp_path / "open_data" / "global_authority" / "authority_source_catalog.json"

    _write_family_release_artifacts(
        release_root,
        family_id="steel_braced_frame",
        label="Steel Braced Frame",
        description="Lateral steel braced frame with tube columns and X braces.",
        preferred_design_family="KDS-2022-STEEL-BASIC",
    )
    _write_family_release_artifacts(
        release_root,
        family_id="deep_transfer_basement",
        label="Deep Transfer Basement",
        description="Deep transfer and basement scaffold with foundations, walls, and girders.",
        preferred_design_family="KDS-2022",
    )

    _write_json(
        korean_catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "buildingSMART Korea BIM Awards 2023 구조 골조 curated IFC",
                    "structure_type": "public_facility",
                    "structural_system": "steel_frame",
                    "origin_org": "buildingSMART Korea",
                    "provenance_url": "https://event.buildingsmart.or.kr/Awards/2023",
                },
                {
                    "source_id": "kci_strut_tie_model_design_examples",
                    "title": "콘크리트구조부재의 스트럿-타이 모델 설계예제집",
                    "structure_type": "component_design",
                    "structural_system": "rc_deep_member",
                    "origin_org": "AIK/KCI",
                    "provenance_url": "https://bookstore.kci.or.kr/kci/Book/bookList",
                },
                {
                    "source_id": "koneps_goyang_changneung_powerplant_design_service",
                    "title": "고양창릉 복합발전소 건설사업 설계기술용역",
                    "structure_type": "industrial_facility",
                    "structural_system": "steel_rc_hybrid",
                    "origin_org": "조달청",
                    "provenance_url": "https://www.g2b.go.kr/powerplant",
                },
            ]
        },
    )
    _write_json(
        benchmark_catalog,
        {
            "candidates": [
                {
                    "id": "designsafe_liquefaction_pile_foundations",
                    "benchmark_domain": "foundation_ssi",
                    "source_name": "DesignSafe liquefaction-induced downdrag on pile foundations dataset",
                    "source_urls": [
                        "https://www.designsafe-ci.org/community/news/2022/july/bridges-under-pressure/"
                    ],
                    "gap_targets": ["foundation / mat / pile optimization"],
                    "integration_fit": ["pile demand validation cases"],
                    "notes": "Foundation benchmark diversification candidate.",
                }
            ]
        },
    )
    _write_json(
        authority_catalog,
        {
            "tracks": {
                "sac": {
                    "cases": [
                        {
                            "case_id": "SAC20_LA_holdout_01",
                            "source_url": "https://femap58.atcouncil.org/sac-steel-project",
                            "source_file_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                        }
                    ]
                },
                "opensees": {
                    "models": [
                        {
                            "id": "SCBF16B",
                            "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                            "source_class": "opensees_text",
                        },
                        {
                            "id": "SCBF16B_shell_beam_mix",
                            "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
                            "source_class": "opensees_text",
                        },
                    ]
                },
            }
        },
    )

    payload = build_native_authoring_family_corpus_manifest(
        portfolio_payload={
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "draft_label": "steel-alt",
                    "commercialization_status": "ready",
                    "commercialization_score": 100,
                    "member_type_label": "beam, brace, column, slab",
                    "story_count": 8,
                    "member_count": 208,
                    "solver_combo_count": 23,
                },
                {
                    "family_id": "deep_transfer_basement",
                    "family_label": "Deep Transfer Basement",
                    "project_id": "native-authoring-deep-transfer-basement",
                    "project_name": "Native Authoring Deep Transfer Basement",
                    "draft_label": "transfer-basement",
                    "commercialization_status": "ready",
                    "commercialization_score": 100,
                    "member_type_label": "beam, column, foundation, slab",
                    "story_count": 6,
                    "member_count": 94,
                    "solver_combo_count": 23,
                },
            ],
        },
        portfolio_json_path=None,
        release_root=release_root,
        korean_source_catalog_path=korean_catalog,
        benchmark_diversification_catalog_path=benchmark_catalog,
        authority_source_catalog_path=authority_catalog,
        out=out,
        generated_at="2026-04-21T12:00:00+00:00",
    )

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 2
    assert payload["summary"]["ready_family_count"] == 2
    assert payload["summary"]["internal_corpus_entry_count"] == 8
    assert payload["summary"]["public_reference_count"] == 6
    assert payload["summary"]["design_reference_count"] == 3
    assert payload["summary"]["benchmark_reference_count"] == 1
    assert payload["summary"]["authority_reference_count"] == 2
    assert payload["summary"]["coverage_axis_count"] == 4
    assert payload["summary"]["family_scoped_repo_path_count"] == 10
    assert payload["summary"]["unique_repo_path_count"] == 10
    assert payload["summary"]["family_scoped_public_source_url_count"] == 5
    assert payload["summary"]["unique_public_source_url_count"] == 5
    assert payload["summary"]["families_with_design_reference_count"] == 2
    assert payload["summary"]["families_with_benchmark_reference_count"] == 1
    assert payload["summary"]["families_with_authority_reference_count"] == 1
    assert payload["checks"]["all_families_mapped"] is True
    assert payload["checks"]["all_references_resolved"] is True
    assert payload["checks"]["all_required_internal_entries_present"] is True
    assert payload["coverage_summary"]["axis_family_counts"] == {
        "local": 2,
        "public": 2,
        "reference": 2,
        "design_authority": 2,
    }
    assert len(payload["linkage_rows"]) == 14
    assert payload["artifacts"]["native_authoring_family_corpus_manifest_json"] == str(out)

    steel_row = next(row for row in payload["family_rows"] if row["family_id"] == "steel_braced_frame")
    assert steel_row["commercialization_lane"] == "core"
    assert steel_row["family_description"].startswith("Lateral steel braced frame")
    assert steel_row["authority_reference_count"] == 2
    assert steel_row["design_reference_count"] == 1
    assert steel_row["benchmark_reference_count"] == 0
    assert steel_row["coverage_axes"] == ["local", "public", "reference", "design_authority"]
    assert steel_row["local_repo_path_count"] == 6
    assert steel_row["public_source_url_count"] == 2
    assert steel_row["resolved_reference_count"] == 3
    assert steel_row["design_authority_span_count"] == 2
    assert "benchmark_story" in steel_row["surface_ids"]
    assert "regional_design_seed" in steel_row["surface_ids"]
    assert {entry["reference_id"] for entry in steel_row["reference_source_entries"]} == {
        "sac_holdout_bundle",
        "opensees_scbf_bundle",
        "ifc_public_award_structure",
    }
    assert steel_row["coverage"]["local"]["reference_repo_path_count"] == 2
    assert steel_row["coverage"]["public"]["source_url_count"] == 2
    assert steel_row["coverage"]["design_authority"]["authority_reference_ids"] == [
        "sac_holdout_bundle",
        "opensees_scbf_bundle",
    ]
    assert all(entry["exists"] for entry in steel_row["internal_corpus_entries"])
    scbf_entry = next(
        entry for entry in steel_row["reference_source_entries"] if entry["reference_id"] == "opensees_scbf_bundle"
    )
    assert scbf_entry["repo_backed_path_count"] == 2
    assert scbf_entry["existing_repo_backed_path_count"] == 2
    assert "reference" in scbf_entry["coverage_axes"]
    assert scbf_entry["design_authority_kind"] == "authority_reference"

    basement_row = next(row for row in payload["family_rows"] if row["family_id"] == "deep_transfer_basement")
    assert basement_row["commercialization_lane"] == "advanced"
    assert basement_row["benchmark_reference_count"] == 1
    assert basement_row["design_reference_count"] == 2
    assert basement_row["coverage_axes"] == ["local", "public", "reference", "design_authority"]
    assert basement_row["local_repo_path_count"] == 4
    assert basement_row["public_source_url_count"] == 3
    assert basement_row["coverage"]["local"]["reference_repo_path_count"] == 0
    assert basement_row["coverage"]["design_authority"]["benchmark_reference_ids"] == [
        "designsafe_liquefaction_pile_foundations"
    ]
    assert {entry["reference_id"] for entry in basement_row["reference_source_entries"]} == {
        "designsafe_liquefaction_pile_foundations",
        "kci_strut_tie_model_design_examples",
        "koneps_goyang_changneung_powerplant_design_service",
    }

    steel_reference_link = next(
        row for row in payload["linkage_rows"] if row["link_id"] == "steel_braced_frame::reference::opensees_scbf_bundle"
    )
    assert steel_reference_link["design_authority_kind"] == "authority_reference"
    assert steel_reference_link["repo_backed_path_count"] == 2
    assert "reference" in steel_reference_link["coverage_axes"]

    persisted = json.loads(out.read_text(encoding="utf-8"))
    assert persisted["summary"]["surface_label"]
    assert persisted["family_rows"][0]["surface_ids"]
    assert persisted["family_rows"][0]["coverage"]["reference"]["reference_count"] == 3


def test_generate_native_authoring_family_corpus_manifest_cli_reads_catalogs(tmp_path: Path) -> None:
    release_root = tmp_path / "release" / "authoring" / "portfolio"
    portfolio_json = release_root / "native_authoring_ops_portfolio.json"
    out = release_root / "native_authoring_family_corpus_manifest.json"
    korean_catalog = tmp_path / "open_data" / "korea" / "korean_source_catalog.json"
    benchmark_catalog = tmp_path / "open_data" / "benchmark_diversification_catalog.json"
    authority_catalog = tmp_path / "open_data" / "global_authority" / "authority_source_catalog.json"

    _write_family_release_artifacts(
        release_root,
        family_id="steel_braced_frame",
        label="Steel Braced Frame",
        description="Lateral steel braced frame with tube columns and X braces.",
        preferred_design_family="KDS-2022-STEEL-BASIC",
    )
    _write_json(
        portfolio_json,
        {
            "portfolio_name": "phase1-native-authoring-ops-portfolio",
            "family_rows": [
                {
                    "family_id": "steel_braced_frame",
                    "family_label": "Steel Braced Frame",
                    "project_id": "native-authoring-steel-braced",
                    "project_name": "Native Authoring Steel Braced",
                    "draft_label": "steel-alt",
                    "commercialization_status": "ready",
                    "commercialization_score": 100,
                    "member_type_label": "beam, brace, column, slab",
                    "story_count": 8,
                    "member_count": 208,
                    "solver_combo_count": 23,
                }
            ],
        },
    )
    _write_json(
        korean_catalog,
        {
            "source_records": [
                {
                    "source_id": "ifc_public_award_structure",
                    "title": "buildingSMART Korea BIM Awards 2023 구조 골조 curated IFC",
                    "origin_org": "buildingSMART Korea",
                    "structure_type": "public_facility",
                    "structural_system": "steel_frame",
                    "provenance_url": "https://event.buildingsmart.or.kr/Awards/2023",
                }
            ]
        },
    )
    _write_json(benchmark_catalog, {"candidates": []})
    _write_json(
        authority_catalog,
        {
            "tracks": {
                "sac": {
                    "cases": [
                        {
                            "case_id": "SAC20_LA_holdout_01",
                            "source_url": "https://femap58.atcouncil.org/sac-steel-project",
                            "source_file_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                        }
                    ]
                },
                "opensees": {
                    "models": [
                        {
                            "id": "SCBF16B",
                            "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B.tcl",
                            "source_class": "opensees_text",
                        },
                        {
                            "id": "SCBF16B_shell_beam_mix",
                            "model_path": "implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl",
                            "source_class": "opensees_text",
                        },
                    ]
                },
            }
        },
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--portfolio-json",
            str(portfolio_json),
            "--release-root",
            str(release_root),
            "--korean-source-catalog",
            str(korean_catalog),
            "--benchmark-diversification-catalog",
            str(benchmark_catalog),
            "--authority-source-catalog",
            str(authority_catalog),
            "--out",
            str(out),
            "--generated-at",
            "2026-04-21T12:30:00+00:00",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 1
    assert payload["summary"]["authority_reference_count"] == 2
    assert payload["summary"]["design_reference_count"] == 1
    assert payload["summary"]["public_reference_count"] == 3
    assert payload["summary"]["coverage_axis_count"] == 4
    assert payload["summary"]["family_scoped_repo_path_count"] == 6
    assert payload["summary"]["unique_repo_path_count"] == 6
    assert payload["summary"]["family_scoped_public_source_url_count"] == 2
    assert payload["coverage_summary"]["axis_family_counts"] == {
        "local": 1,
        "public": 1,
        "reference": 1,
        "design_authority": 1,
    }
    assert "Native authoring family corpus manifest: PASS" in proc.stdout


def test_build_native_authoring_family_corpus_manifest_default_release_portfolio_covers_eight_families(
    tmp_path: Path,
) -> None:
    out = tmp_path / "native_authoring_family_corpus_manifest.json"
    payload = build_native_authoring_family_corpus_manifest(
        portfolio_json_path=Path("implementation/phase1/release/authoring/portfolio/native_authoring_ops_portfolio.json"),
        release_root=Path("implementation/phase1/release/authoring/portfolio"),
        korean_source_catalog_path=Path("implementation/phase1/open_data/korea/korean_source_catalog.json"),
        benchmark_diversification_catalog_path=Path("implementation/phase1/open_data/benchmark_diversification_catalog.json"),
        authority_source_catalog_path=Path("implementation/phase1/open_data/global_authority/authority_source_catalog.json"),
        out=out,
        generated_at="2026-04-21T13:00:00+00:00",
    )

    expected_family_ids = [
        "sample_tower",
        "steel_braced_frame",
        "rc_wall_core",
        "composite_podium",
        "outrigger_transfer_tower",
        "dual_system_hospital",
        "belt_truss_mega_frame",
        "deep_transfer_basement",
    ]

    assert payload["contract_pass"] is True
    assert payload["summary"]["family_count"] == 8
    assert payload["summary"]["ready_family_count"] == 8
    assert payload["summary"]["internal_corpus_entry_count"] == 32
    assert payload["summary"]["public_reference_count"] == 24
    assert payload["summary"]["design_reference_count"] == 9
    assert payload["summary"]["benchmark_reference_count"] == 10
    assert payload["summary"]["authority_reference_count"] == 5
    assert payload["summary"]["coverage_axis_count"] == 4
    assert payload["summary"]["family_scoped_repo_path_count"] == 120
    assert payload["summary"]["unique_repo_path_count"] == 117
    assert payload["summary"]["family_scoped_public_source_url_count"] == 37
    assert payload["summary"]["unique_public_source_url_count"] == 26
    assert payload["summary"]["families_with_design_reference_count"] == 6
    assert payload["summary"]["families_with_benchmark_reference_count"] == 7
    assert payload["summary"]["families_with_authority_reference_count"] == 4
    assert payload["summary"]["unresolved_family_count"] == 0
    assert payload["summary"]["unresolved_reference_count"] == 0
    assert payload["coverage_summary"]["axis_family_counts"] == {
        "local": 8,
        "public": 8,
        "reference": 8,
        "design_authority": 8,
    }
    assert [row["family_id"] for row in payload["family_rows"]] == expected_family_ids

    mega_frame_row = next(row for row in payload["family_rows"] if row["family_id"] == "belt_truss_mega_frame")
    assert mega_frame_row["commercialization_lane"] == "premium"
    assert mega_frame_row["coverage_axes"] == ["local", "public", "reference", "design_authority"]
    assert mega_frame_row["local_repo_path_count"] == 13
    assert mega_frame_row["public_source_url_count"] == 7
    assert mega_frame_row["design_authority_span_count"] == 2
    assert {entry["reference_id"] for entry in mega_frame_row["reference_source_entries"]} == {
        "canton_tower_megastructure",
        "tpu_highrise_wind_pressure_and_force",
        "opensees_luxinzheng_megatall_model",
    }
    assert mega_frame_row["coverage"]["local"]["reference_repo_path_count"] == 2
    assert mega_frame_row["coverage"]["design_authority"]["authority_reference_ids"] == [
        "opensees_luxinzheng_megatall_model"
    ]
    assert all(entry["exists"] for entry in mega_frame_row["internal_corpus_entries"])

    steel_row = next(row for row in payload["family_rows"] if row["family_id"] == "steel_braced_frame")
    ifc_entry = next(
        entry for entry in steel_row["reference_source_entries"] if entry["reference_id"] == "ifc_public_award_structure"
    )
    assert ifc_entry["local_path"].endswith("ifc_public_award_structure.ifc")
    assert ifc_entry["repo_backed_path_count"] == 1
    assert ifc_entry["existing_repo_backed_path_count"] == 1
    assert ifc_entry["coverage_axes"] == ["local", "public", "reference", "design_authority"]
