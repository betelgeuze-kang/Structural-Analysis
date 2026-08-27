from __future__ import annotations

import hashlib
import importlib.util
import json
from copy import deepcopy
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/build_mgt_import_health_tenth_source_receipt.py"
MANIFEST = ROOT / "benchmarks/import_health/mgt_tenth_source_supplement.v1.json"
MANIFEST_SCHEMA = (
    ROOT / "canonical/mgt-import-health-tenth-source-manifest.v1.schema.json"
)

SPEC = importlib.util.spec_from_file_location("mgt_import_health_tenth", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def _dummy_source() -> tuple[dict, bytes, str]:
    body = b"*VERSION\n1\n*NODE\n2,1,0,0\n1,0,0,0\n*ELEMENT\n1,BEAM,1,1,1,2,0\n"
    case = {
        "repository": "owner/repository",
        "source_commit_sha": "a" * 40,
        "source_path": "fixtures/test model.mgt",
        "expected_size_bytes": len(body),
        "expected_sha256": hashlib.sha256(body).hexdigest(),
        "expected_git_blob_sha1": module._git_blob_sha1(body),
    }
    url = module._expected_raw_url(case)
    case["raw_url"] = url
    return case, body, url


def _fetch_result(
    *,
    url: str,
    body: bytes,
    final_url: str | None = None,
    redirects: tuple[str, ...] = (),
    content_length: int | None = None,
) -> module.FetchResult:
    return module.FetchResult(
        requested_url=url,
        final_url=final_url or url,
        redirect_chain=redirects,
        status_code=200,
        content_length_header=len(body) if content_length is None else content_length,
        content_encoding="identity",
        body=body,
    )


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _valid_external_case() -> dict:
    declared = _manifest()["case"]
    acquisition = {
        "repository": declared["repository"],
        "source_commit_sha": declared["source_commit_sha"],
        "source_path": declared["source_path"],
        "requested_url": declared["raw_url"],
        "final_url": declared["raw_url"],
        "redirect_chain": [],
        "http_status": 200,
        "content_encoding": "identity",
        "content_length_header": declared["expected_size_bytes"],
        "expected_size_bytes": declared["expected_size_bytes"],
        "observed_size_bytes": declared["expected_size_bytes"],
        "expected_sha256": declared["expected_sha256"],
        "observed_sha256": declared["expected_sha256"],
        "expected_git_blob_sha1": declared["expected_git_blob_sha1"],
        "observed_git_blob_sha1": declared["expected_git_blob_sha1"],
        "exact_commit_url_verified": True,
        "redirect_policy_verified": True,
        "content_integrity_verified": True,
        "raw_source_retained": False,
        "raw_source_uploaded": False,
    }
    id_hash_a = "a" * 64
    id_hash_b = "b" * 64
    return {
        "case_id": declared["case_id"],
        "lineage_id": declared["lineage_id"],
        "corpus_class": "clean",
        "expected_parser_outcome": "pass",
        "observed_parser_outcome": "pass",
        "acquisition": acquisition,
        "source_scan": {
            "data_row_count": 5184,
            "visible_unsupported_or_omitted_row_count": 0,
            "record_fingerprint_sha256": declared["expected_record_fingerprint_sha256"],
            "model_identity_sha256": declared["expected_model_identity_sha256"],
            "utf8_replacement_character_count": 0,
        },
        "provenance_and_rights": {
            key: declared[key]
            for key in (
                "source_owner",
                "provenance_status",
                "rights_status",
                "license_file_present",
                "redistribution_reviewed",
                "commercial_use_reviewed",
            )
        },
        "parser": {
            "script": "implementation/phase1/parse_midas_mgt_to_json_npz.py",
            "return_code": 0,
            "contract_pass": True,
            "reason_code": "PASS",
            "report_path": ".ci/mgt-import-health-tenth-source/case-reports/case.json",
            "report_sha256": "c" * 64,
        },
        "record_accounting": {
            "source_data_row_count": 5184,
            "parser_recognized_row_count": 5184,
            "visible_unsupported_or_omitted_row_count": 0,
            "visible_unsupported_or_omitted_by_section": {},
            "unaccounted_row_count": 0,
        },
        "entity_accounting": {
            "node": {
                "source_row_count": 1879,
                "source_id_count": 1879,
                "parser_reported_row_count": 1879,
                "parser_reported_parsed_count": 1879,
                "parser_reported_skipped_count": 0,
                "output_count": 1879,
                "source_id_sha256": id_hash_a,
                "output_id_sha256": id_hash_a,
            },
            "element": {
                "source_row_count": 3296,
                "source_id_count": 3296,
                "parser_reported_row_count": 3296,
                "parser_reported_parsed_count": 3296,
                "parser_reported_skipped_count": 0,
                "output_count": 3296,
                "source_id_sha256": id_hash_b,
                "output_id_sha256": id_hash_b,
            },
            "material": {
                "source_row_count": 1,
                "parser_reported_row_count": 1,
                "parser_reported_parsed_count": 1,
            },
            "section": {
                "source_row_count": 0,
                "parser_reported_row_count": 0,
                "parser_reported_parsed_count": 0,
            },
            "output_suppressed_by_parser_contract": False,
        },
        "negative_silent_loss_gate": {
            "source_record_deletion_detected": True,
            "accounting_record_deletion_detected": True,
            "parser_replay_executed": True,
            "parser_return_code": 0,
            "parser_contract_pass": True,
            "parser_return_code_matches_contract": True,
            "deleted_record_kind": "node",
            "mutated_source_sha256": "d" * 64,
            "mutated_source_data_row_count": 5183,
            "mutated_node_id_sha256": "e" * 64,
            "parser_report_path": (
                ".ci/mgt-import-health-tenth-source/case-reports/"
                "case.deleted-node.parser-report.json"
            ),
            "parser_report_semantic_sha256": "f" * 64,
            "raw_mutated_input_retained": False,
            "source_mutation_reason": "source_sha256_and_record_count_mismatch",
            "accounting_mutation_reason": (
                "live_parser_replay_detected_deleted_node_identity"
            ),
        },
        "contract_pass": True,
        "blockers": [],
    }


def test_manifest_is_exact_and_keeps_all_rights_false() -> None:
    manifest = _manifest()
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))

    assert module._schema_errors(manifest, schema) == []
    assert manifest["case"]["license_file_present"] is False
    assert manifest["case"]["redistribution_reviewed"] is False
    assert manifest["case"]["commercial_use_reviewed"] is False
    assert manifest["aggregation_policy"]["raw_source_retention_allowed"] is False
    assert manifest["aggregation_policy"]["raw_source_artifact_upload_allowed"] is False


def test_manifest_schema_rejects_forged_commit_and_url() -> None:
    manifest = _manifest()
    schema = json.loads(MANIFEST_SCHEMA.read_text(encoding="utf-8"))
    manifest["case"]["source_commit_sha"] = "f" * 40
    manifest["case"]["raw_url"] = manifest["case"]["raw_url"].replace(
        "raw.githubusercontent.com", "example.invalid"
    )

    errors = module._schema_errors(manifest, schema)

    assert any("source_commit_sha" in error for error in errors)
    assert any("raw_url" in error for error in errors)


def test_acquisition_accepts_exact_commit_url_hash_size_and_blob() -> None:
    case, body, url = _dummy_source()

    acquisition, observed = module.acquire_source(
        case,
        fetcher=lambda requested, maximum: _fetch_result(url=requested, body=body),
    )

    assert observed == body
    assert acquisition["final_url"] == url
    assert acquisition["content_integrity_verified"] is True
    assert acquisition["raw_source_retained"] is False
    assert acquisition["raw_source_uploaded"] is False


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda case: case.__setitem__(
                "raw_url",
                case["raw_url"].replace("raw.githubusercontent.com", "evil.invalid"),
            ),
            "source_url_mismatch",
        ),
        (
            lambda case: case.__setitem__("source_commit_sha", "b" * 40),
            "source_url_mismatch",
        ),
        (
            lambda case: case.__setitem__("expected_sha256", "f" * 64),
            "source_sha256_mismatch",
        ),
        (
            lambda case: case.__setitem__("expected_git_blob_sha1", "f" * 40),
            "source_git_blob_sha1_mismatch",
        ),
    ],
)
def test_acquisition_rejects_forged_descriptor(mutate, expected: str) -> None:
    case, body, _ = _dummy_source()
    mutate(case)

    with pytest.raises(module.ReceiptError, match=expected):
        module.acquire_source(
            case,
            fetcher=lambda requested, maximum: _fetch_result(url=requested, body=body),
        )


def test_acquisition_rejects_redirect_even_to_same_pinned_path() -> None:
    case, body, url = _dummy_source()

    with pytest.raises(module.ReceiptError, match="source_redirect_rejected"):
        module.acquire_source(
            case,
            fetcher=lambda requested, maximum: _fetch_result(
                url=requested,
                body=body,
                redirects=(url,),
            ),
        )


def test_acquisition_rejects_forged_final_host_or_path() -> None:
    case, body, _ = _dummy_source()

    with pytest.raises(module.ReceiptError, match="final_url_mismatch"):
        module.acquire_source(
            case,
            fetcher=lambda requested, maximum: _fetch_result(
                url=requested,
                final_url=requested.replace("test%20model.mgt", "other.mgt"),
                body=body,
            ),
        )


def test_acquisition_rejects_changed_content_with_same_size() -> None:
    case, body, _ = _dummy_source()
    changed = bytes([body[0] ^ 1]) + body[1:]

    with pytest.raises(module.ReceiptError, match="source_sha256_mismatch"):
        module.acquire_source(
            case,
            fetcher=lambda requested, maximum: _fetch_result(
                url=requested, body=changed
            ),
        )


@pytest.mark.parametrize(
    ("identity_key", "count_key", "blocker"),
    [
        ("case_id", "unique_case_id_count", "duplicate_case_id_credit"),
        ("lineage_id", "unique_lineage_count", "duplicate_lineage_id_credit"),
        (
            "source_sha256",
            "unique_source_sha256_count",
            "duplicate_source_sha256_credit",
        ),
        (
            "record_fingerprint_sha256",
            "unique_record_fingerprint_count",
            "duplicate_record_fingerprint_sha256_credit",
        ),
        (
            "model_identity_sha256",
            "unique_model_identity_count",
            "duplicate_model_identity_sha256_credit",
        ),
    ],
)
def test_identity_gate_rejects_every_duplicate_credit_dimension(
    identity_key: str, count_key: str, blocker: str
) -> None:
    rows = [
        {
            "case_id": f"case-{index}",
            "lineage_id": f"lineage-{index}",
            "source_sha256": f"{index:064x}",
            "record_fingerprint_sha256": f"{index + 20:064x}",
            "model_identity_sha256": f"{index + 40:064x}",
            "contract_pass": True,
        }
        for index in range(10)
    ]
    rows[9][identity_key] = rows[0][identity_key]

    gate = module._identity_gate(rows)

    assert gate["contract_pass"] is False
    assert gate[count_key] == 9
    assert gate["blockers"] == [blocker]


def test_external_case_rejects_accounting_forgery() -> None:
    case = _valid_external_case()
    case["entity_accounting"]["node"]["parser_reported_parsed_count"] -= 1

    errors = module._external_case_errors(case, _manifest()["case"])

    assert "node_parser_balance_mismatch" in errors
    assert "node_output_count_mismatch" in errors


def test_external_case_requires_live_negative_parser_replay() -> None:
    case = _valid_external_case()
    case["negative_silent_loss_gate"]["parser_replay_executed"] = False
    case["negative_silent_loss_gate"]["raw_mutated_input_retained"] = True

    errors = module._external_case_errors(case, _manifest()["case"])

    assert "negative_parser_replay_not_executed" in errors
    assert "negative_raw_input_retention_invalid" in errors


@pytest.mark.parametrize(
    "evidence_dir",
    [Path("."), Path(".."), Path(".ci/other"), Path("/tmp")],
)
def test_evidence_directory_is_bounded_to_canonical_default(
    tmp_path: Path, evidence_dir: Path
) -> None:
    with pytest.raises(module.ReceiptError, match="evidence_dir"):
        module._validated_evidence_dir(tmp_path, evidence_dir)


def test_external_case_and_claims_reject_authority_promotion() -> None:
    case = _valid_external_case()
    case["provenance_and_rights"]["redistribution_reviewed"] = True

    errors = module._external_case_errors(case, _manifest()["case"])
    semantic_errors = module.validate_receipt_semantics(
        {"claims": {"release_authority": True}}, manifest=_manifest()
    )

    assert "redistribution_review_unexpectedly_true" in errors
    assert "authority_claim_not_false:release_authority" in semantic_errors


def test_entity_identity_comparison_normalizes_source_record_order() -> None:
    scan = {
        "section_rows": {
            "NODE": ["2,1,0,0", "1,0,0,0"],
            "ELEMENT": [
                "2,BEAM,1,1,2,1,0",
                "1,BEAM,1,1,1,2,0",
            ],
        }
    }
    report = {
        "contract_pass": True,
        "parser_diagnostics": {
            "row_parse": {
                "node_rows": 2,
                "node_rows_parsed": 2,
                "node_rows_skipped": 0,
                "element_rows": 2,
                "element_rows_parsed": 2,
                "element_rows_skipped": 0,
            }
        },
    }
    model = {
        "model": {
            "nodes": [{"id": 1}, {"id": 2}],
            "elements": [{"id": 1}, {"id": 2}],
        }
    }

    accounting = module.CORE._entity_accounting(scan, report, model)

    assert (
        accounting["node"]["source_id_sha256"] == accounting["node"]["output_id_sha256"]
    )
    assert (
        accounting["element"]["source_id_sha256"]
        == accounting["element"]["output_id_sha256"]
    )


def test_report_projection_ignores_only_timestamp_and_runtime_paths() -> None:
    report = {
        "generated_at": "2026-08-28T00:00:00+00:00",
        "run_id": "stable-run",
        "contract_pass": True,
        "inputs": {
            "mgt": "/tmp/source-a.mgt",
            "json_out": ".ci/one/model.json",
            "npz_out": ".ci/one/graph.npz",
            "report_out": ".ci/one/report.json",
            "edge_list_out": ".ci/one/edges.json",
        },
        "artifacts": {
            "json_out": ".ci/one/model.json",
            "npz_out": ".ci/one/graph.npz",
            "edge_list_out": ".ci/one/edges.json",
        },
        "source_provenance": {
            "path": "/tmp/source-a.mgt",
            "sha256": "a" * 64,
            "size_bytes": 10,
        },
        "parser_diagnostics": {"row_parse": {"node_rows": 4}},
    }
    replay = deepcopy(report)
    replay["generated_at"] = "2026-08-28T01:00:00+00:00"
    replay["inputs"]["mgt"] = "/tmp/source-b.mgt"
    replay["inputs"]["json_out"] = ".ci/two/model.json"
    replay["inputs"]["npz_out"] = ".ci/two/graph.npz"
    replay["inputs"]["report_out"] = ".ci/two/report.json"
    replay["inputs"]["edge_list_out"] = ".ci/two/edges.json"
    replay["artifacts"]["json_out"] = ".ci/two/model.json"
    replay["artifacts"]["npz_out"] = ".ci/two/graph.npz"
    replay["artifacts"]["edge_list_out"] = ".ci/two/edges.json"
    replay["source_provenance"]["path"] = "/tmp/source-b.mgt"

    assert module._report_semantic_projection(
        report, normalize_source_path=True
    ) == module._report_semantic_projection(replay, normalize_source_path=True)

    replay["parser_diagnostics"]["row_parse"]["node_rows"] = 999999
    assert module._report_semantic_projection(
        report, normalize_source_path=True
    ) != module._report_semantic_projection(replay, normalize_source_path=True)


def test_bundled_core_report_rejects_coherent_diagnostic_forgery() -> None:
    case = {
        "path": "benchmarks/import_health/source.mgt",
        "source": {"observed_sha256": "a" * 64, "observed_size_bytes": 123},
        "parser": {"contract_pass": True, "reason_code": "PASS"},
        "entity_accounting": {
            "node": {
                "parser_reported_row_count": 2,
                "parser_reported_parsed_count": 2,
                "parser_reported_skipped_count": 0,
            },
            "element": {
                "parser_reported_row_count": 1,
                "parser_reported_parsed_count": 1,
                "parser_reported_skipped_count": 0,
            },
            "material": {
                "parser_reported_row_count": 0,
                "parser_reported_parsed_count": 0,
            },
            "section": {
                "parser_reported_row_count": 0,
                "parser_reported_parsed_count": 0,
            },
        },
    }
    report = {
        "contract_pass": True,
        "reason_code": "PASS",
        "source_provenance": {
            "path": case["path"],
            "sha256": "a" * 64,
            "size_bytes": 123,
        },
        "inputs": {
            "mgt": case["path"],
            "forbid_synthetic_source": False,
            "min_nodes": 2,
            "min_elements": 1,
            "resolve_rigid_links": False,
            "drop_unreferenced_nodes": False,
            "strict_unknown_sections": False,
            "max_element_skip_count": 1000000,
            "max_element_skip_ratio": 1.0,
        },
        "parser_diagnostics": {
            "row_parse": {
                "node_rows": 2,
                "node_rows_parsed": 2,
                "node_rows_skipped": 0,
                "element_rows": 1,
                "element_rows_parsed": 1,
                "element_rows_skipped": 0,
                "material_rows": 0,
                "material_rows_parsed": 0,
                "section_rows": 0,
                "section_rows_parsed": 0,
            }
        },
    }

    assert module._bundled_core_report_errors(case, report) == []
    report["parser_diagnostics"]["row_parse"]["node_rows"] = 999999
    assert "node_parser_reported_row_count_mismatch" in (
        module._bundled_core_report_errors(case, report)
    )


def test_bundle_inventory_rejects_raw_and_unmanifested_members(tmp_path: Path) -> None:
    evidence = tmp_path / ".ci/mgt-import-health-tenth-source"
    evidence.mkdir(parents=True)
    (evidence / "technical-receipt.json").write_text("{}\n", encoding="utf-8")
    (evidence / "source.mgt").write_bytes(b"*NODE\n1,0,0,0\n")
    (evidence / "raw-renamed.json").write_text(
        '{"raw_mgt": "*NODE"}\n', encoding="utf-8"
    )

    errors = module._evidence_bundle_inventory_errors(
        {"support_artifacts": []}, repo_root=tmp_path
    )

    assert (
        "evidence_bundle_non_json:.ci/mgt-import-health-tenth-source/source.mgt"
        in errors
    )
    assert (
        "evidence_bundle_unmanifested_member:.ci/mgt-import-health-tenth-source/source.mgt"
        in errors
    )
    assert (
        "evidence_bundle_unmanifested_member:.ci/mgt-import-health-tenth-source/raw-renamed.json"
        in errors
    )
