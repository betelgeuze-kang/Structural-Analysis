from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
ACQUIRE_SCRIPT = REPO_ROOT / "scripts/acquire_buildingsmart_ifc_current_source.py"
SUMMARY_SCRIPT = REPO_ROOT / "scripts/build_ifc_import_health_current_source_receipt.py"
LEGACY_IMPORT_SCRIPT = (
    REPO_ROOT / "scripts/build_phase3_ifc_import_health_execution_receipt.py"
)
DEFAULT_MANIFEST = (
    REPO_ROOT / "benchmarks/import_health/buildingsmart_ifc_current_source.v1.json"
)
SOURCE_SHA = "a" * 40
LICENSE_FIXTURE_BYTES = {
    "buildingsmart_certification_datasets_cc_by_4_0": base64.b64decode(
        "KEMpIGJ1aWxkaW5nU01BUlQgSW50ZXJuYXRpb25hbCBMdGQuCgpUaGlzIHdvcmsgaXMgbGljZW5zZWQgdW5kZXIgdGhlIENyZWF0aXZlIENvbW1vbnMgQXR0cmlidXRpb24gNC4wIEludGVybmF0aW9uYWwgTGljZW5zZS4gCk1vcmUgaW5mbyBhbmQgYSBsaW5rIHRvIHRoZSBmdWxsIGxpY2Vuc2UgdGV4dCBpcyBhdmFpbGFibGUgb24gaHR0cDovL2NyZWF0aXZlY29tbW9ucy5vcmcvbGljZW5zZXMvYnkvNC4wLwoKUmVhZCB0aGUgZnVsbCBsaWNlbnNlIG9uIGh0dHBzOi8vY3JlYXRpdmVjb21tb25zLm9yZy9saWNlbnNlcy9ieS80LjAvbGVnYWxjb2RlLnR4dAo="
    ),
    "buildingsmart_community_samples_cc_by_4_0": base64.b64decode(
        "KEMpIG9yaWdpbmFsIGF1dGhvcnMKClRoaXMgd29yayBpcyBsaWNlbnNlZCB1bmRlciB0aGUgQ3JlYXRpdmUgQ29tbW9ucyBBdHRyaWJ1dGlvbiA0LjAgSW50ZXJuYXRpb25hbCBMaWNlbnNlLiAKTW9yZSBpbmZvIGFuZCBhIGxpbmsgdG8gdGhlIGZ1bGwgbGljZW5zZSB0ZXh0IGlzIGF2YWlsYWJsZSBvbiBodHRwOi8vY3JlYXRpdmVjb21tb25zLm9yZy9saWNlbnNlcy9ieS80LjAvCg=="
    ),
}


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


acquire = _load_module("acquire_buildingsmart_ifc_current_source", ACQUIRE_SCRIPT)
summary = _load_module("build_ifc_import_health_current_source_receipt", SUMMARY_SCRIPT)
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))
legacy_import = _load_module(
    "build_phase3_ifc_import_health_execution_receipt_for_manifest_test",
    LEGACY_IMPORT_SCRIPT,
)
from structural_analysis.api.core import AnalysisConfig, analyze, load_model  # noqa: E402
from structural_analysis.results.schema import AnalysisResult  # noqa: E402
from structural_analysis.results.validation import validate  # noqa: E402


REAL_GIT_SOURCE_BINDING = summary._git_source_binding


@pytest.fixture(autouse=True)
def _exact_git_identity_for_isolated_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        summary,
        "_git_source_binding",
        lambda _repo_root, source_commit_sha, allowed_generated_paths: {
            "verification_mode": "git_exact_source_with_generated_evidence_allowlist",
            "declared_source_commit_sha": source_commit_sha,
            "git_head_commit_sha": source_commit_sha,
            "git_head_tree_sha": "d" * 40,
            "source_commit_matches": True,
            "source_tree_clean": True,
            "changed_generated_paths": [],
            "dirty_source_paths": [],
        },
    )


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture_manifest(repo_root: Path) -> tuple[Path, dict]:
    schema_target = repo_root / summary.DEFAULT_SCHEMA
    schema_target.parent.mkdir(parents=True, exist_ok=True)
    schema_target.write_bytes((REPO_ROOT / summary.DEFAULT_SCHEMA).read_bytes())
    result_schema_target = repo_root / summary.RESULT_SCHEMA
    result_schema_target.parent.mkdir(parents=True, exist_ok=True)
    result_schema_target.write_bytes((REPO_ROOT / summary.RESULT_SCHEMA).read_bytes())
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    sparse_cases = {
        "buildingsmart_community_duplex_electrical",
        "buildingsmart_community_duplex_mep",
        "buildingsmart_community_clinic_electrical",
        "buildingsmart_community_clinic_hvac",
        "buildingsmart_community_clinic_plumbing",
    }
    for row in payload["cases"]:
        case_id = row["case_id"]
        if case_id == "buildingsmart_pcert_building_structural":
            entities = (
                "IFCBEAM",
                "IFCWALL",
                "IFCMATERIALLAYERSET",
                "IFCRECTANGLEPROFILEDEF",
            )
        elif case_id == "buildingsmart_pcert_infra_bridge":
            entities = ("IFCBEAM", "IFCMEMBER", "IFCSLAB")
        elif case_id in sparse_cases:
            entities = ("IFCPROJECT",)
        else:
            entities = ("IFCBEAM",)
        content = (
            "ISO-10303-21;\n"
            f"/* fixture-case:{case_id} */\n"
            "DATA;\n"
            + "\n".join(
                f"#{index}={entity}();" for index, entity in enumerate(entities, 1)
            )
            + "\nENDSEC;\nEND-ISO-10303-21;\n"
        ).encode()
        path = repo_root / row["local_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        row["byte_length"] = len(content)
        row["sha256"] = _sha256_bytes(content)
        row["model_identity_sha256"] = row["sha256"]
    for row in payload["licenses"]:
        path = repo_root / row["local_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(LICENSE_FIXTURE_BYTES[row["license_id"]])
    manifest_path = Path("benchmarks/import_health/fixture-manifest.json")
    _write_json(repo_root / manifest_path, payload)
    return manifest_path, payload


def _write_summary_support(
    repo_root: Path,
    *,
    manifest_path: Path,
    manifest: dict,
) -> Path:
    acquisition_path = Path(
        ".ci/ifc-import-health-current-source/acquisition-receipt.json"
    )
    acquisition = acquire.build_acquisition_receipt(
        repo_root=repo_root,
        manifest_path=manifest_path,
        source_commit_sha=SOURCE_SHA,
        download_missing=False,
    )
    _write_json(repo_root / acquisition_path, acquisition)

    case_receipts = []
    for row in manifest["cases"]:
        case_id = row["case_id"]
        result_path = summary.PRODUCTIZATION / f"{case_id}.result.json"
        report_path = summary.PRODUCTIZATION / f"{case_id}.report.json"
        model = load_model(repo_root / row["local_path"])
        analysis_result = analyze(
            model,
            AnalysisConfig(
                analysis_type="model_health",
                solver="developer_preview_model_health",
            ),
        )
        result = analysis_result.to_dict()
        report = validate(analysis_result).to_dict()
        _write_json(repo_root / result_path, result)
        _write_json(repo_root / report_path, report)
        metrics = result["metrics"]
        case_receipts.append(
            {
                "case_id": case_id,
                "lane_kind": row["lane_kind"],
                "filename": row["filename"],
                "source_url": row["download_url"],
                "local_path": row["local_path"],
                "selected_benchmark_lanes": ["fixture"],
                "truth_class": "fixture",
                "source_file_acquired": True,
                "source_sha256": row["sha256"],
                "import_health_executed": True,
                "import_health_contract_pass": True,
                "silent_import_loss_gate": {
                    "contract_pass": True,
                    "visible_entity_accounting": True,
                    "record_count": metrics["record_count"],
                    "parsed_record_count": metrics["parsed_record_count"],
                    "structural_entity_count": metrics["structural_entity_count"],
                    "material_entity_count": metrics["material_entity_count"],
                    "section_entity_count": metrics["section_entity_count"],
                    "load_related_entity_count": metrics[
                        "load_related_entity_count"
                    ],
                },
                "execution": {
                    "return_code": 2,
                    "result_exists": True,
                    "report_exists": True,
                    "result_path": result_path.as_posix(),
                    "report_path": report_path.as_posix(),
                    "result": result,
                    "report": report,
                },
            }
        )
    common = {
        "schema_version": "fixture.v1",
        "source_commit_sha": SOURCE_SHA,
    }
    _write_json(repo_root / summary.CLEAN_ACQUISITION, common)
    _write_json(repo_root / summary.DIRTY_ACQUISITION, common)
    _write_json(
        repo_root / summary.IMPORT_HEALTH,
        {
            **common,
            "source_file_acquired_count": 10,
            "source_checksum_attached_count": 10,
            "import_health_execution_count": 10,
            "import_health_contract_pass_count": 10,
            "visible_entity_accounting_case_count": 10,
            "silent_import_loss_gate_pass_count": 10,
            "case_receipts": case_receipts,
        },
    )
    _write_json(
        repo_root / summary.SOURCE_LICENSE,
        {
            **common,
            "contract_pass": False,
            "blockers": ["product_legal_license_review_pending"],
        },
    )
    _write_json(
        repo_root / summary.SILENT_IMPORT_LOSS,
        {
            **common,
            "contract_pass": False,
            "technical_silent_import_loss_zero": True,
            "technical_direct_blockers": [],
            "product_release_credit_ready": False,
            "product_release_credit_blockers": [
                "product_legal_license_review_pending",
                "phase3_ifc_import_case_quantity_credit_missing",
            ],
        },
    )
    return acquisition_path


def test_tracked_manifest_pins_ten_exact_sources_and_two_exact_licenses() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

    acquire.validate_manifest(payload)

    assert payload["case_count"] == 10
    assert len(payload["cases"]) == 10
    assert sum(row["lane_kind"] == "clean" for row in payload["cases"]) == 2
    assert sum(row["lane_kind"] == "dirty" for row in payload["cases"]) == 8
    assert len(payload["licenses"]) == 2
    assert all(
        row["upstream_commit_sha"] in row["download_url"] for row in payload["cases"]
    )
    assert all(row["sha256"].startswith("sha256:") for row in payload["cases"])
    assert all(row["byte_length"] > 0 for row in payload["cases"])
    assert all(row["spdx_expression"] == "CC-BY-4.0" for row in payload["licenses"])
    assert all(value is False for value in payload["authority_claims"].values())


def test_ifc_manifest_schema_is_exact_and_rejects_unknown_properties() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    payload["unknown_authority"] = True
    with pytest.raises(acquire.ManifestError, match="manifest_schema_invalid"):
        acquire.validate_manifest(payload)


@pytest.mark.parametrize("lane", ["clean", "dirty"])
def test_ifc_manifest_rejects_duplicate_model_credit_within_each_lane(
    lane: str,
) -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    rows = [row for row in payload["cases"] if row["lane_kind"] == lane]
    rows[1]["sha256"] = rows[0]["sha256"]
    rows[1]["model_identity_sha256"] = rows[0]["model_identity_sha256"]
    with pytest.raises(acquire.ManifestError, match="manifest_duplicate_source_sha256"):
        acquire.validate_manifest(payload)


@pytest.mark.parametrize(
    "raw",
    [
        '{"schema_version":"a","schema_version":"b"}',
        '{"metric":NaN}',
        '{"metric":Infinity}',
        '{"metric":1e9999}',
    ],
)
def test_ifc_raw_json_loaders_reject_duplicate_and_nonfinite_input(
    tmp_path: Path,
    raw: str,
) -> None:
    target = tmp_path / "attack.json"
    target.write_text(raw, encoding="utf-8")
    with pytest.raises((acquire.ManifestError, ValueError)):
        acquire._load_json(target)
    with pytest.raises(summary.ReceiptError):
        summary._load_json(tmp_path, Path("attack.json"))


def test_tracked_manifest_case_set_matches_existing_phase3_execution_contract() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    legacy_rows = legacy_import._candidate_rows(REPO_ROOT, SOURCE_SHA)

    manifest_identity = {
        (row["case_id"], row["lane_kind"], row["local_path"])
        for row in payload["cases"]
    }
    legacy_identity = {
        (row["case_id"], row["lane_kind"], row["local_path"]) for row in legacy_rows
    }

    assert manifest_identity == legacy_identity


def test_manifest_rejects_mutable_download_url() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    tampered = deepcopy(payload)
    tampered["cases"][0]["download_url"] = tampered["cases"][0]["download_url"].replace(
        tampered["cases"][0]["upstream_commit_sha"], "main"
    )

    with pytest.raises(
        acquire.ManifestError, match="download_url_not_exact_commit_path"
    ):
        acquire.validate_manifest(tampered)


def test_offline_acquisition_verifies_exact_private_bytes_and_fails_on_tamper(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)

    ready = acquire.build_acquisition_receipt(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        source_commit_sha=SOURCE_SHA,
        download_missing=False,
    )

    assert ready["status"] == "ready"
    assert ready["technical_contract_pass"] is True
    assert ready["verified_case_count"] == 10
    assert ready["verified_license_material_count"] == 2
    assert ready["product_legal_approval"] is False
    assert ready["redistribution_authority"] is False
    assert ready["commercial_use_authority"] is False
    assert ready["release_authority"] is False

    first = tmp_path / manifest["cases"][0]["local_path"]
    first.write_bytes(first.read_bytes() + b"tamper")
    blocked = acquire.build_acquisition_receipt(
        repo_root=tmp_path,
        manifest_path=manifest_path,
        source_commit_sha=SOURCE_SHA,
        download_missing=False,
    )

    assert blocked["status"] == "blocked"
    assert blocked["technical_contract_pass"] is False
    assert any(
        "source_sha256_mismatch:case:buildingsmart_pcert_building_structural"
        in item
        for item in blocked["blockers"]
    )


def test_current_source_summary_closes_only_technical_silent_loss(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )

    payload, support_entries = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["status"] == "technical_ready_product_authority_blocked"
    assert payload["technical_contract_pass"] is True
    assert payload["counts"]["case_count"] == 10
    assert payload["counts"]["clean_case_count"] == 2
    assert payload["counts"]["dirty_case_count"] == 8
    assert payload["counts"]["import_health_contract_pass_count"] == 10
    assert payload["claims"]["technical_silent_import_loss_zero"] is True
    assert payload["claims"]["text_scan_import_health_only"] is True
    assert payload["claims"]["solver_ready_geometry_or_topology"] is False
    assert payload["claims"]["product_legal_approval"] is False
    assert payload["claims"]["redistribution_authority"] is False
    assert payload["claims"]["commercial_use_authority"] is False
    assert payload["claims"]["phase3_quantity_credit"] is False
    assert payload["claims"]["release_authority"] is False
    assert (
        "product_legal_license_review_pending" in payload["legal_and_product_blockers"]
    )
    assert len(support_entries) == 26
    assert all(row["source_path"].endswith(".json") for row in support_entries)
    assert all(row["artifact_path"].startswith("support/repository/") for row in support_entries)


def test_current_source_summary_fails_closed_on_case_hash_drift(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    import_health_path = tmp_path / summary.IMPORT_HEALTH
    import_health = json.loads(import_health_path.read_text(encoding="utf-8"))
    import_health["case_receipts"][0]["source_sha256"] = "sha256:" + "0" * 64
    _write_json(import_health_path, import_health)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["status"] == "technical_blocked"
    assert payload["technical_contract_pass"] is False
    assert any(
        blocker.endswith(":import_source_hash_manifest_mismatch")
        for blocker in payload["technical_blockers"]
    )


def test_current_source_schema_forbids_redistribution_promotion(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )
    payload["claims"]["redistribution_authority"] = True

    with pytest.raises(
        summary.ReceiptError,
        match="technical_receipt_schema_invalid:claims.redistribution_authority",
    ):
        summary.validate_receipt_schema(payload, repo_root=tmp_path)


def test_current_source_writer_bundles_receipts_but_not_raw_ifc(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    output = Path(".ci/ifc-import-health-current-source/technical-receipt.json")
    support_dir = Path(".ci/ifc-import-health-current-source/support")

    payload = summary.write_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        out_path=output,
        support_dir=support_dir,
    )

    assert payload["technical_contract_pass"] is True
    bundled = [
        path for path in (tmp_path / support_dir).rglob("*") if path.is_file()
    ]
    assert len(bundled) == 26
    assert all(path.suffix != ".ifc" for path in bundled)
    assert not any("private_corpus" in path.as_posix() for path in bundled)

    (tmp_path / support_dir / "raw.ifc").write_bytes(b"ISO-10303-21;\n")
    with pytest.raises(
        summary.ReceiptError, match="support_bundle_unexpected_entries:raw.ifc"
    ):
        summary.write_current_source_receipt(
            repo_root=tmp_path,
            source_commit_sha=SOURCE_SHA,
            manifest_path=manifest_path,
            acquisition_path=acquisition_path,
            out_path=output,
            support_dir=support_dir,
        )


def test_writer_and_checker_use_configured_support_dir_independent_of_output(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    output = Path("receipts/current-source.json")
    support_dir = Path("portable/custom-evidence-root")

    payload = summary.write_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        out_path=output,
        support_dir=support_dir,
    )

    ok, message = summary.verify_support_bundle(
        payload,
        support_dir=tmp_path / support_dir,
    )
    assert ok is True
    assert message == "support_bundle_integrity_consistent_nonfresh"
    checked, checked_message = summary.check_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        out_path=output,
        support_dir=support_dir,
    )
    assert checked is True
    assert checked_message == "current_source_receipt_consistent_and_technical_ready"

    wrong_location, wrong_message = summary.verify_support_bundle(
        payload,
        bundle_root=(tmp_path / output).parent,
    )
    assert wrong_location is False
    assert wrong_message.startswith("support_manifest_file_missing:")


def test_manifest_rejects_canonical_lane_and_license_identity_forgery() -> None:
    payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    lane_forged = deepcopy(payload)
    clean = next(row for row in lane_forged["cases"] if row["lane_kind"] == "clean")
    dirty = next(row for row in lane_forged["cases"] if row["lane_kind"] == "dirty")
    clean["lane_kind"], dirty["lane_kind"] = dirty["lane_kind"], clean["lane_kind"]
    with pytest.raises(
        acquire.ManifestError,
        match="manifest_canonical_case_lane_invalid",
    ):
        acquire.validate_manifest(lane_forged)

    license_forged = deepcopy(payload)
    license_forged["licenses"][0]["upstream_repository"] = "attacker/repository"
    with pytest.raises(
        acquire.ManifestError,
        match="manifest_download_url_not_exact_commit_path|"
        "manifest_canonical_license_identity_invalid",
    ):
        acquire.validate_manifest(license_forged)


def test_current_source_fails_closed_when_raw_ifc_is_missing(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    (tmp_path / manifest["cases"][0]["local_path"]).unlink()

    with pytest.raises(summary.ReceiptError, match="raw_ifc_file_unavailable"):
        summary.build_current_source_receipt(
            repo_root=tmp_path,
            source_commit_sha=SOURCE_SHA,
            manifest_path=manifest_path,
            acquisition_path=acquisition_path,
        )


def test_current_source_fails_closed_on_raw_byte_tamper_after_acquisition(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    raw_path = tmp_path / manifest["cases"][0]["local_path"]
    raw_path.write_bytes(raw_path.read_bytes() + b"\nTAMPER\n")

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert "current_raw_source_or_license_replay_blocked" in payload[
        "technical_blockers"
    ]
    assert payload["claims"]["immutable_source_and_license_byte_identity"] is False


def test_current_source_fails_closed_when_pinned_license_bytes_are_missing(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    (tmp_path / manifest["licenses"][0]["local_path"]).unlink()

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert any(
        "source_file_missing:license" in blocker
        for blocker in payload["technical_blockers"]
    )


def test_current_source_fails_closed_on_record_accounting_false_positive(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    import_path = tmp_path / summary.IMPORT_HEALTH
    import_health = json.loads(import_path.read_text(encoding="utf-8"))
    gate = import_health["case_receipts"][0]["silent_import_loss_gate"]
    gate["record_count"] = 999
    gate["parsed_record_count"] = 0
    _write_json(import_path, import_health)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert payload["claims"]["technical_silent_import_loss_zero"] is False
    assert any(
        "silent_gate_metric_mismatch" in blocker
        for blocker in payload["technical_blockers"]
    )


def test_current_source_fails_closed_on_result_semantic_tamper_with_new_hash(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    import_path = tmp_path / summary.IMPORT_HEALTH
    import_health = json.loads(import_path.read_text(encoding="utf-8"))
    execution = import_health["case_receipts"][0]["execution"]
    result_path = tmp_path / execution["result_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["status"] = "ready"
    execution["result"] = result
    _write_json(result_path, result)
    _write_json(import_path, import_health)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert any(
        "result_status_not_blocked" in blocker
        or "report_authoritative_replay_mismatch" in blocker
        for blocker in payload["technical_blockers"]
    )


def test_current_source_fails_closed_on_coherent_entity_accounting_forge(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    import_path = tmp_path / summary.IMPORT_HEALTH
    import_health = json.loads(import_path.read_text(encoding="utf-8"))
    case = next(
        row
        for row in import_health["case_receipts"]
        if row["case_id"] == "buildingsmart_pcert_building_structural"
    )
    execution = case["execution"]
    result_path = tmp_path / execution["result_path"]
    report_path = tmp_path / execution["report_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))

    # Preserve the raw/parser total and the contract's two required structural
    # classes while forging away the material and section entities.  A digest-only
    # or result-to-report replay cannot distinguish this from genuine product output.
    result["metrics"].update(
        {
            "entity_counts": {"IFCBEAM": 1, "IFCWALL": 1, "IFCPROJECT": 2},
            "record_count": 4,
            "parsed_record_count": 4,
            "structural_entity_count": 2,
            "material_entity_count": 0,
            "section_entity_count": 0,
            "load_related_entity_count": 0,
            "element_count": 2,
            "load_count": 0,
        }
    )
    forged_result = AnalysisResult(**result)
    report = validate(forged_result).to_dict()
    execution["result"] = result
    execution["report"] = report
    case["silent_import_loss_gate"].update(
        {
            "record_count": 4,
            "parsed_record_count": 4,
            "structural_entity_count": 2,
            "material_entity_count": 0,
            "section_entity_count": 0,
            "load_related_entity_count": 0,
            "visible_entity_accounting": True,
            "contract_pass": True,
        }
    )
    _write_json(result_path, result)
    _write_json(report_path, report)
    _write_json(import_path, import_health)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert payload["claims"]["technical_silent_import_loss_zero"] is False
    assert any(
        blocker.endswith(":result_authoritative_product_replay_mismatch")
        for blocker in payload["technical_blockers"]
    )


def test_current_source_fails_closed_on_forged_license_rows(tmp_path: Path) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    acquisition_file = tmp_path / acquisition_path
    acquisition = json.loads(acquisition_file.read_text(encoding="utf-8"))
    for index, row in enumerate(
        item
        for item in acquisition["artifacts"]
        if item["artifact_kind"] == "license"
    ):
        row["artifact_id"] = f"forged_license_{index}"
        row["license_id"] = f"forged_license_{index}"
        row["upstream_repository"] = "attacker/repository"
        row["upstream_commit_sha"] = "f" * 40
        row["expected_sha256"] = "sha256:" + "0" * 64
        row["observed_sha256"] = "sha256:" + "0" * 64
        row["verified"] = True
        row["blockers"] = []
    _write_json(acquisition_file, acquisition)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert "acquisition_receipt_current_raw_replay_mismatch" in payload[
        "technical_blockers"
    ]
    assert payload["claims"]["immutable_source_and_license_byte_identity"] is False


def test_current_source_fails_closed_on_coherent_hash_forge_without_raw_bytes(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    fake_sha = "sha256:" + "1" * 64
    case_id = manifest["cases"][0]["case_id"]
    manifest["cases"][0]["sha256"] = fake_sha
    manifest["cases"][0]["model_identity_sha256"] = fake_sha
    _write_json(tmp_path / manifest_path, manifest)
    manifest_sha = _sha256_bytes((tmp_path / manifest_path).read_bytes())

    acquisition_file = tmp_path / acquisition_path
    acquisition = json.loads(acquisition_file.read_text(encoding="utf-8"))
    acquisition["manifest_sha256"] = manifest_sha
    acquired = next(
        row for row in acquisition["artifacts"] if row.get("case_id") == case_id
    )
    acquired["expected_sha256"] = fake_sha
    acquired["observed_sha256"] = fake_sha
    acquired["model_identity_sha256"] = fake_sha
    acquired["verified"] = True
    acquired["blockers"] = []
    _write_json(acquisition_file, acquisition)

    import_path = tmp_path / summary.IMPORT_HEALTH
    import_health = json.loads(import_path.read_text(encoding="utf-8"))
    imported = next(
        row for row in import_health["case_receipts"] if row["case_id"] == case_id
    )
    imported["source_sha256"] = fake_sha
    execution = imported["execution"]
    result_path = tmp_path / execution["result_path"]
    report_path = tmp_path / execution["report_path"]
    result = json.loads(result_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result["input_checksum"] = fake_sha
    report["input_checksum"] = fake_sha
    execution["result"] = result
    execution["report"] = report
    _write_json(result_path, result)
    _write_json(report_path, report)
    _write_json(import_path, import_health)

    payload, _ = summary.build_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
    )

    assert payload["technical_contract_pass"] is False
    assert "current_raw_source_or_license_replay_blocked" in payload[
        "technical_blockers"
    ]


def test_raw_assignment_scanner_is_independent_of_strings_and_comments(
    tmp_path: Path,
) -> None:
    path = tmp_path / "scanner.ifc"
    path.write_text(
        "ISO-10303-21;\n"
        "DATA;\n"
        "#1=IFCBEAM('#98=NOT_AN_ASSIGNMENT');\n"
        "/* #97=IFCBEAM(); */\n"
        "#2=IFCCOLUMN(\n"
        ");\n"
        "#3=IFCSLAB(\n",
        encoding="utf-8",
    )

    assert summary._raw_step_assignment_ids(path) == ["1", "2", "3"]


def test_support_bundle_verifier_is_nonfresh_and_detects_hash_tamper(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    output = Path(".ci/ifc-import-health-current-source/technical-receipt.json")
    payload = summary.write_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        out_path=output,
    )
    bundle_root = (tmp_path / output).parent

    ok, message = summary.verify_support_bundle(payload, bundle_root=bundle_root)
    assert ok is True
    assert message == "support_bundle_integrity_consistent_nonfresh"
    assert "acquisition-receipt.json" in payload["supporting_receipts"]
    assert payload["support_manifest"]["file_count"] == 26

    first = bundle_root / payload["support_manifest"]["entries"][0]["artifact_path"]
    first.write_bytes(first.read_bytes() + b"tamper")
    ok, message = summary.verify_support_bundle(payload, bundle_root=bundle_root)
    assert ok is False
    assert message.startswith("support_manifest_file_hash_mismatch:")


def test_bundle_integrity_does_not_substitute_for_missing_raw_sources(
    tmp_path: Path,
) -> None:
    manifest_path, manifest = _fixture_manifest(tmp_path)
    acquisition_path = _write_summary_support(
        tmp_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )
    output = Path(".ci/ifc-import-health-current-source/technical-receipt.json")
    payload = summary.write_current_source_receipt(
        repo_root=tmp_path,
        source_commit_sha=SOURCE_SHA,
        manifest_path=manifest_path,
        acquisition_path=acquisition_path,
        out_path=output,
    )
    for row in [*manifest["cases"], *manifest["licenses"]]:
        (tmp_path / row["local_path"]).unlink()

    ok, message = summary.verify_support_bundle(
        payload,
        bundle_root=(tmp_path / output).parent,
    )
    assert ok is True
    assert message.endswith("_nonfresh")
    with pytest.raises(summary.ReceiptError, match="raw_ifc_file_unavailable"):
        summary.check_current_source_receipt(
            repo_root=tmp_path,
            source_commit_sha=SOURCE_SHA,
            manifest_path=manifest_path,
            acquisition_path=acquisition_path,
            out_path=output,
        )


def test_real_git_source_binding_rejects_declared_sha_forgery() -> None:
    binding = REAL_GIT_SOURCE_BINDING(
        REPO_ROOT,
        "c" * 40,
        allowed_generated_paths=[],
    )

    assert binding["source_commit_matches"] is False


def test_real_git_source_binding_allows_only_declared_generated_paths(
    tmp_path: Path,
) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    source = tmp_path / "source.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=IFC Test",
            "-c",
            "user.email=ifc-test@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    generated = tmp_path / "generated.json"
    generated.write_text("{}\n", encoding="utf-8")
    source.write_text("VALUE = 2\n", encoding="utf-8")

    binding = REAL_GIT_SOURCE_BINDING(
        tmp_path,
        head,
        allowed_generated_paths=[generated],
    )

    assert binding["source_commit_matches"] is True
    assert binding["source_tree_clean"] is False
    assert binding["changed_generated_paths"] == ["generated.json"]
    assert binding["dirty_source_paths"] == ["source.py"]
