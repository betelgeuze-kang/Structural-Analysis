from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_public_benchmark_operator_bundle_from_rows.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location(
    "materialize_public_benchmark_operator_bundle_from_rows",
    SCRIPT_PATH,
)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _checksum(seed: str) -> str:
    return f"sha256:{hashlib.sha256(seed.encode('utf-8')).hexdigest()}"


def _provenance_ref(*parts: str) -> str:
    return "https://zenodo.org/records/1357911/files/" + "/".join(parts)


def test_public_benchmark_operator_bundle_from_row_files_groups_flat_rows(
    tmp_path: Path,
) -> None:
    subset_rows = tmp_path / "subset.jsonl"
    pose_rows = tmp_path / "pose.json"
    enrichment_rows = tmp_path / "enrichment.csv"
    vina_gnina_rows = tmp_path / "vina_gnina.csv"

    _write_jsonl(
        subset_rows,
        [
            {
                "case_id": "case_a",
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "complex_id": "case_a_complex",
                "protein_structure_path": "benchmarks/case_a/protein.pdb",
                "reference_ligand_path": "benchmarks/case_a/ref.sdf",
                "predicted_ligand_path_or_docking_run_id": "benchmarks/case_a/pred.sdf",
                "ligand_atom_order_contract": {"atom_count": 2, "atom_ids": ["C1", "O1"]},
                "symmetry_permutation_contract": {"permutations": [[0, 1]]},
                "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                "source_checksum": _checksum("PDBBind-CASF-2016-core:case_a"),
                "provenance_ref": _provenance_ref(
                    "public-benchmark", "casf-pdbbind", "case_a.json"
                ),
                "pose_success_metric": "symmetry_aware_ligand_rmsd_angstrom",
                "rmsd_threshold_angstrom": 2.0,
            }
        ],
    )
    pose_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "receptor_context": {
                            "provenance_ref": _provenance_ref(
                                "public-benchmark", "pose", "case_a.json"
                            )
                        },
                        "reference_atoms": [{"element": "C", "x": 0, "y": 0, "z": 0}],
                        "predicted_atoms": [{"element": "C", "x": 0.1, "y": 0, "z": 0}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _write_csv(
        enrichment_rows,
        [
            {
                "benchmark_family": "DUD-E",
                "target_id": "AA2AR",
                "score_direction": "higher_is_better",
                "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                "source_checksum": _checksum("DUD-E:AA2AR:release-2015"),
                "provenance_ref": _provenance_ref(
                    "public-benchmark", "dud-e", "AA2AR.json"
                ),
                "molecule_id": "active_1",
                "is_active": "true",
                "score": "0.9",
            },
            {
                "benchmark_family": "DUD-E",
                "target_id": "AA2AR",
                "score_direction": "higher_is_better",
                "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                "source_checksum": _checksum("DUD-E:AA2AR:release-2015"),
                "provenance_ref": _provenance_ref(
                    "public-benchmark", "dud-e", "AA2AR.json"
                ),
                "molecule_id": "decoy_1",
                "is_active": "false",
                "score": "0.1",
            },
        ],
    )
    _write_csv(
        vina_gnina_rows,
        [
            {
                "case_id": "case_a",
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "complex_id": "case_a_complex",
                "reference_pose_id": "case_a_ref",
                "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                "source_checksum": _checksum("vina-gnina-case-a"),
                "provenance_ref": _provenance_ref(
                    "public-benchmark", "vina-gnina", "case_a.json"
                ),
                "engine_id": "vina",
                "docking_run_id": "case_a_vina",
                "predicted_ligand_path_or_pose_ref": (
                    _provenance_ref(
                        "public-benchmark", "vina-gnina", "case_a", "vina.sdf"
                    )
                ),
                "symmetry_aware_rmsd_angstrom": "1.4",
                "pose_success": "true",
                "score": "-7.2",
                "score_direction": "lower_is_better",
            },
            {
                "case_id": "case_a",
                "source_family": "CASF/PDBBind",
                "benchmark_split": "CASF-core",
                "complex_id": "case_a_complex",
                "reference_pose_id": "case_a_ref",
                "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                "source_checksum": _checksum("vina-gnina-case-a"),
                "provenance_ref": _provenance_ref(
                    "public-benchmark", "vina-gnina", "case_a.json"
                ),
                "engine_id": "gnina",
                "docking_run_id": "case_a_gnina",
                "predicted_ligand_path_or_pose_ref": (
                    _provenance_ref(
                        "public-benchmark", "vina-gnina", "case_a", "gnina.sdf"
                    )
                ),
                "symmetry_aware_rmsd_angstrom": "1.6",
                "pose_success": "true",
                "score": "-7.8",
                "score_direction": "lower_is_better",
            },
        ],
    )

    payload = module.build_public_benchmark_operator_bundle_from_rows(
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
        enrichment_rows_path=enrichment_rows,
        vina_gnina_rows_path=vina_gnina_rows,
        target_subset_case_count=12,
        repo_root=REPO_ROOT,
    )

    assert payload["schema_version"] == "public-benchmark-operator-bundle.v1"
    assert payload["target_subset_case_count"] == 12
    assert payload["casf_pdbbind_subset_intake"]["cases"][0]["case_id"] == "case_a"
    assert payload["pose_validity_intake"]["cases"][0]["case_id"] == "case_a"
    assert payload["pose_validity_intake"]["consumer_chain"] == [
        "public_benchmark_pose_validity_input",
        "public_benchmark_posebusters_validity_packet",
        "public_benchmark_symmetry_rmsd_scorecard",
        "public_benchmark_pose_success_harness",
    ]
    targets = payload["dud_e_lit_pcba_enrichment_intake"]["targets"]
    assert len(targets) == 1
    assert targets[0]["target_id"] == "AA2AR"
    assert [row["is_active"] for row in targets[0]["scored_molecules"]] == [True, False]
    comparison_cases = payload["vina_gnina_comparison_intake"]["cases"]
    assert len(comparison_cases) == 1
    assert [row["engine_id"] for row in comparison_cases[0]["engine_runs"]] == [
        "vina",
        "gnina",
    ]
    report = payload["materialization_report"]
    assert {
        key: report[key]
        for key in (
            "schema_version",
            "subset_row_count",
            "pose_row_count",
            "pose_validity_case_count",
            "posebusters_validity_case_count",
            "enrichment_row_count",
            "enrichment_target_count",
            "vina_gnina_row_count",
            "vina_gnina_case_count",
            "accepted_row_formats",
            "phase2_harness_inputs",
        )
    } == {
        "schema_version": "public-benchmark-operator-bundle-from-rows.v1",
        "subset_row_count": 1,
        "pose_row_count": 1,
        "pose_validity_case_count": 1,
        "posebusters_validity_case_count": 1,
        "enrichment_row_count": 2,
        "enrichment_target_count": 1,
        "vina_gnina_row_count": 2,
        "vina_gnina_case_count": 1,
        "accepted_row_formats": ["json", "jsonl", "ndjson", "csv"],
        "phase2_harness_inputs": {
            "casf_pdbbind_pose_success_harness": True,
            "symmetry_aware_ligand_rmsd": True,
            "posebusters_style_pose_validity": True,
            "vina_gnina_comparison_adapter": True,
            "dud_e_lit_pcba_enrichment": True,
        },
    }
    assert report["source_actuality_check"]["contract_pass"] is True
    assert report["source_actuality_check"]["blockers"] == []
    assert report["source_actuality_check"]["policy"][
        "row_file_artifact_sha256_policy"
    ].startswith("Every operator row file materialized by this importer")
    assert report["source_actuality_blockers"] == []
    row_file_receipts = report["row_file_artifact_receipts"]
    assert set(row_file_receipts) == {
        "subset_rows",
        "pose_rows",
        "enrichment_rows",
        "vina_gnina_rows",
    }
    assert row_file_receipts["subset_rows"] == {
        "row_input_id": "subset_rows",
        "path": str(subset_rows),
        "format": "jsonl",
        "source_artifact_sha256": module.file_sha256(subset_rows),
    }
    assert row_file_receipts["pose_rows"]["source_artifact_sha256"] == (
        module.file_sha256(pose_rows)
    )
    assert row_file_receipts["enrichment_rows"]["source_artifact_sha256"] == (
        module.file_sha256(enrichment_rows)
    )
    assert row_file_receipts["vina_gnina_rows"]["source_artifact_sha256"] == (
        module.file_sha256(vina_gnina_rows)
    )


def test_public_benchmark_operator_bundle_from_rows_flags_placeholder_sources(
    tmp_path: Path,
) -> None:
    subset_rows = tmp_path / "subset.json"
    pose_rows = tmp_path / "pose.json"
    enrichment_rows = tmp_path / "enrichment.json"
    vina_gnina_rows = tmp_path / "vina_gnina.json"

    subset_rows.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": "case_a",
                        "source_license_or_accession": "CASF/PDBBind:test-accession",
                        "source_checksum": "sha256:" + "a" * 64,
                        "provenance_ref": "operator://case_a",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pose_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "receptor_context": {"provenance_ref": "operator://pose/case_a"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    enrichment_rows.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "target_id": "AA2AR",
                        "source_license_or_accession": "fixture-only",
                        "source_checksum": "sha256:" + "b" * 64,
                        "provenance_ref": "operator://dud-e/AA2AR",
                        "scored_molecules": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    vina_gnina_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "source_license_or_accession": "CASF/PDBBind:test-accession",
                        "source_checksum": "sha256:" + "c" * 64,
                        "provenance_ref": "operator://vina-gnina/case_a",
                        "engine_runs": [
                            {
                                "engine_id": "vina",
                                "predicted_ligand_path_or_pose_ref": (
                                    "operator://poses/vina.sdf"
                                ),
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = module.build_public_benchmark_operator_bundle_from_rows(
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
        enrichment_rows_path=enrichment_rows,
        vina_gnina_rows_path=vina_gnina_rows,
        target_subset_case_count=12,
        repo_root=REPO_ROOT,
    )

    source_check = payload["materialization_report"]["source_actuality_check"]
    assert source_check["contract_pass"] is False
    assert "subset_rows:case_a:source_license_or_accession_placeholder" in source_check["blockers"]
    assert "subset_rows:case_a:source_checksum_placeholder_digest" in source_check["blockers"]
    assert "subset_rows:case_a:provenance_ref_placeholder" in source_check["blockers"]
    assert "pose_rows:case_a:receptor_context.provenance_ref_placeholder" in source_check["blockers"]
    assert "enrichment_rows:AA2AR:source_license_or_accession_placeholder" in source_check["blockers"]
    assert (
        "vina_gnina_rows:case_a:engine_run_0:"
        "predicted_ligand_path_or_pose_ref_placeholder"
    ) in source_check["blockers"]


def test_public_benchmark_operator_bundle_from_rows_flags_local_proxy_sources(
    tmp_path: Path,
) -> None:
    subset_rows = tmp_path / "subset.json"
    pose_rows = tmp_path / "pose.json"
    enrichment_rows = tmp_path / "enrichment.json"
    vina_gnina_rows = tmp_path / "vina_gnina.json"

    subset_rows.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "case_id": "case_a",
                        "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                        "source_checksum": _checksum("case_a"),
                        "provenance_ref": (
                            "local-evidence://public-benchmark/casf-pdbbind/case_a"
                        ),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    pose_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "receptor_context": {
                            "provenance_ref": (
                                "local-evidence://public-benchmark/pose/case_a"
                            )
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    enrichment_rows.write_text(
        json.dumps(
            {
                "targets": [
                    {
                        "target_id": "AA2AR",
                        "source_license_or_accession": "DUD-E:AA2AR:release-2015",
                        "source_checksum": _checksum("AA2AR"),
                        "provenance_ref": "local-evidence://public-benchmark/dud-e/AA2AR",
                        "scored_molecules": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    vina_gnina_rows.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "case_id": "case_a",
                        "source_license_or_accession": "PDBBind-CASF-2016-core:case_a",
                        "source_checksum": _checksum("vina-gnina-case-a"),
                        "provenance_ref": (
                            "local-evidence://public-benchmark/vina-gnina/case_a"
                        ),
                        "engine_runs": [
                            {
                                "engine_id": "vina",
                                "predicted_ligand_path_or_pose_ref": (
                                    "local-evidence://public-benchmark/vina-gnina/"
                                    "case_a/vina.sdf"
                                ),
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = module.build_public_benchmark_operator_bundle_from_rows(
        subset_rows_path=subset_rows,
        pose_rows_path=pose_rows,
        enrichment_rows_path=enrichment_rows,
        vina_gnina_rows_path=vina_gnina_rows,
        target_subset_case_count=12,
        repo_root=REPO_ROOT,
    )

    source_check = payload["materialization_report"]["source_actuality_check"]
    assert source_check["contract_pass"] is False
    assert source_check["policy"]["placeholder_provenance_prefixes_rejected"] == [
        "operator://",
        "local-evidence://",
        "local://",
        "fixture://",
        "mock://",
        "synthetic://",
        "placeholder://",
        "test://",
        "unit-test://",
        "file://",
    ]
    assert "subset_rows:case_a:provenance_ref_placeholder" in source_check["blockers"]
    assert (
        "pose_rows:case_a:receptor_context.provenance_ref_placeholder"
        in source_check["blockers"]
    )
    assert "enrichment_rows:AA2AR:provenance_ref_placeholder" in source_check["blockers"]
    assert "vina_gnina_rows:case_a:provenance_ref_placeholder" in source_check["blockers"]
    assert (
        "vina_gnina_rows:case_a:engine_run_0:"
        "predicted_ligand_path_or_pose_ref_placeholder"
    ) in source_check["blockers"]


def test_public_benchmark_operator_bundle_from_rows_cli_writes_bundle(
    tmp_path: Path,
) -> None:
    subset_rows = tmp_path / "subset.json"
    pose_rows = tmp_path / "pose.json"
    enrichment_rows = tmp_path / "enrichment.json"
    vina_gnina_rows = tmp_path / "vina_gnina.json"
    out = tmp_path / "operator_bundle.json"

    subset_rows.write_text(json.dumps({"rows": [{"case_id": "case_a"}]}), encoding="utf-8")
    pose_rows.write_text(json.dumps({"cases": [{"case_id": "case_a"}]}), encoding="utf-8")
    enrichment_rows.write_text(
        json.dumps({"targets": [{"target_id": "AA2AR", "scored_molecules": []}]}),
        encoding="utf-8",
    )
    vina_gnina_rows.write_text(
        json.dumps({"cases": [{"case_id": "case_a", "engine_runs": []}]}),
        encoding="utf-8",
    )

    assert (
        module.main(
            [
                "--subset-rows",
                str(subset_rows),
                "--pose-rows",
                str(pose_rows),
                "--enrichment-rows",
                str(enrichment_rows),
                "--vina-gnina-rows",
                str(vina_gnina_rows),
                "--target-subset-case-count",
                "12",
                "--out",
                str(out),
            ]
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["target_subset_case_count"] == 12
    assert payload["materialization_report"]["subset_row_count"] == 1
