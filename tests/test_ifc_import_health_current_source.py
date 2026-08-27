from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
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
UPSTREAM_SHA = "b" * 40


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
    cases = []
    for index in range(10):
        content = f"ISO-10303-21;\n#{index + 1}=IFCBEAM();\nENDSEC;\n".encode()
        case_id = f"case_{index:02d}"
        local_path = f"private_corpus/phase3/buildingsmart/test/{case_id}.ifc"
        path = repo_root / local_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        cases.append(
            {
                "byte_length": len(content),
                "case_id": case_id,
                "download_url": (
                    "https://raw.githubusercontent.com/example/repo/"
                    f"{UPSTREAM_SHA}/cases/{case_id}.ifc"
                ),
                "filename": f"{case_id}.ifc",
                "lane_kind": "clean" if index < 2 else "dirty",
                "license_id": "license_a" if index < 2 else "license_b",
                "local_path": local_path,
                "sha256": _sha256_bytes(content),
                "upstream_commit_sha": UPSTREAM_SHA,
                "upstream_path": f"cases/{case_id}.ifc",
                "upstream_repository": "example/repo",
            }
        )
    licenses = []
    for license_id in ("license_a", "license_b"):
        content = f"CC BY 4.0 fixture {license_id}\n".encode()
        local_path = (
            f"private_corpus/phase3/buildingsmart/licenses/{license_id}.LICENSE"
        )
        path = repo_root / local_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        licenses.append(
            {
                "authority_boundary": (
                    "Upstream license bytes and SPDX identity are recorded; product/legal "
                    "approval is not granted by this manifest."
                ),
                "byte_length": len(content),
                "download_url": (
                    "https://raw.githubusercontent.com/example/repo/"
                    f"{UPSTREAM_SHA}/{license_id}.LICENSE"
                ),
                "license_id": license_id,
                "local_path": local_path,
                "sha256": _sha256_bytes(content),
                "spdx_expression": "CC-BY-4.0",
                "upstream_commit_sha": UPSTREAM_SHA,
                "upstream_path": f"{license_id}.LICENSE",
                "upstream_repository": "example/repo",
            }
        )
    payload = {
        "case_count": 10,
        "cases": cases,
        "claim_boundary": "fixture",
        "licenses": licenses,
        "schema_version": "buildingsmart-ifc-current-source-manifest.v1",
        "storage_boundary": "download_to_gitignored_private_corpus_never_bundle_or_upload",
    }
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
        _write_json(repo_root / result_path, {"case_id": case_id, "status": "blocked"})
        _write_json(repo_root / report_path, {"case_id": case_id, "status": "blocked"})
        case_receipts.append(
            {
                "case_id": case_id,
                "lane_kind": row["lane_kind"],
                "source_file_acquired": True,
                "source_sha256": row["sha256"],
                "import_health_executed": True,
                "import_health_contract_pass": True,
                "silent_import_loss_gate": {
                    "contract_pass": True,
                    "visible_entity_accounting": True,
                    "record_count": 5,
                    "parsed_record_count": 5,
                },
                "execution": {
                    "result_path": result_path.as_posix(),
                    "report_path": report_path.as_posix(),
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
        "source_sha256_mismatch:case:case_00" in item for item in blocked["blockers"]
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

    payload, support_files = summary.build_current_source_receipt(
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
    assert all(path.suffix != ".ifc" for path in support_files)


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
    bundled = [path for path in (tmp_path / support_dir).iterdir() if path.is_file()]
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
