from __future__ import annotations

import binascii
import importlib.util
import json
from pathlib import Path
import struct
import zlib

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_current_main_evidence_index.py"
SPEC = importlib.util.spec_from_file_location("current_main_evidence_index", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _github_zip(entries: list[tuple[str, bytes]], *, mode: int = 0o100644) -> bytes:
    local = bytearray()
    central = bytearray()
    rows = []
    for name, value in entries:
        name_raw = name.encode("utf-8")
        compressed = zlib.compress(value)[2:-4]
        crc = binascii.crc32(value) & 0xFFFFFFFF
        offset = len(local)
        flags = 0x808
        local.extend(
            struct.pack(
                "<4s5H3L2H",
                b"PK\x03\x04",
                20,
                flags,
                8,
                0,
                0,
                0,
                0,
                0,
                len(name_raw),
                0,
            )
        )
        local.extend(name_raw)
        local.extend(compressed)
        local.extend(
            struct.pack("<4s3L", b"PK\x07\x08", crc, len(compressed), len(value))
        )
        rows.append((name_raw, flags, crc, compressed, value, offset))
    directory_offset = len(local)
    for name_raw, flags, crc, compressed, value, offset in rows:
        central.extend(
            struct.pack(
                "<4s6H3L5H2L",
                b"PK\x01\x02",
                0x032D,
                20,
                flags,
                8,
                0,
                0,
                crc,
                len(compressed),
                len(value),
                len(name_raw),
                0,
                0,
                0,
                0,
                (mode << 16) | 0x20,
                offset,
            )
        )
        central.extend(name_raw)
    result = local + central
    result.extend(
        struct.pack(
            "<4s4H2LH",
            b"PK\x05\x06",
            0,
            0,
            len(rows),
            len(rows),
            len(central),
            directory_offset,
            0,
        )
    )
    return bytes(result)


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}',
        b'{"a":NaN}',
        b'{"a":Infinity}',
        b'{"a":-Infinity}',
        b'{"a":1e9999}',
        b'{"a":9007199254740992}',
    ],
)
def test_strict_json_rejects_ambiguous_or_unsafe_numbers(raw: bytes) -> None:
    with pytest.raises(MODULE.EvidenceIndexError):
        MODULE._strict_json_bytes(raw, "test")


def test_raw_github_zip_parser_accepts_exact_json_and_rejects_unsafe_members() -> None:
    archive = _github_zip([("nested/receipt.json", b'{"value":1}\n')])
    assert MODULE.strict_github_artifact_archive(archive, "good") == {
        "nested/receipt.json": b'{"value":1}\n'
    }
    for bad in (
        _github_zip([("../receipt.json", b"{}")]),
        _github_zip([("A.json", b"{}"), ("a.json", b"{}")]),
        _github_zip([("bad\nname.json", b"{}")]),
        _github_zip([("bad\x7fname.json", b"{}")]),
        _github_zip([("bad\u200bname.json", b"{}")]),
        _github_zip([("receipt.json", b'{"value":1e9999}')]),
        _github_zip([("receipt.json", b"{}")], mode=0o120777),
    ):
        with pytest.raises(MODULE.EvidenceIndexError):
            MODULE.strict_github_artifact_archive(bad, "bad")


def _lane_rows(
    catalog_lanes: list[dict[str, object]], source: str
) -> list[dict[str, object]]:
    rows = []
    for index, lane in enumerate(catalog_lanes, start=1):
        lane_id = str(lane["lane_id"])
        run_id = 100 + index
        name = f"{lane_id}-technical-handoff-{run_id}-1-{source}"
        artifact = {
            "id": 1000 + index * 2,
            "name": name,
            "api_digest": "sha256:" + f"{index:064x}",
            "size_in_bytes": 100,
            "workflow_run_id": run_id,
            "workflow_run_attempt": 1,
            "source_sha": source,
        }
        attestation = dict(artifact)
        attestation["id"] += 1
        attestation["name"] += "-attestation"
        attestation["api_digest"] = "sha256:" + f"{index + 10:064x}"
        rows.append(
            {
                "lane_id": lane_id,
                "workflow_path": lane["workflow_path"],
                "workflow_blob_sha": f"{index:040x}",
                "attestor_workflow_path": MODULE.ATTESTOR_WORKFLOW_PATH,
                "attestor_workflow_blob_sha": "a" * 40,
                "run_id": run_id,
                "run_attempt": 1,
                "event": "push",
                "producer_job_id": 200 + index * 2,
                "attestor_job_id": 201 + index * 2,
                "handoff_artifact": artifact,
                "attestation_artifact": attestation,
                "technical_subject_path": lane["subject_path"],
                "technical_subject_sha256": "sha256:" + "b" * 64,
                "pair_sha256": "sha256:" + "c" * 64,
                "sigstore_verification_report_sha256": "sha256:" + "d" * 64,
                "contract_pass": True,
                "technical_scope": lane["technical_scope"],
                "authority_not_granted": lane["authority_not_granted"],
                "promotion_eligible": False,
                "promotion_blockers": lane["promotion_blockers"],
            }
        )
    return rows


def test_catalog_and_index_preserve_technical_only_authority(tmp_path: Path) -> None:
    catalog, lanes = MODULE._load_catalog(ROOT)
    source = "1" * 40
    product_state = {"id": 88, "updated_at": "2026-08-28T01:02:03Z"}
    payload = MODULE._build_index(
        catalog=catalog,
        lanes=lanes,
        lane_rows=_lane_rows(lanes, source),
        repository="owner/repository",
        source_sha=source,
        tree_sha="2" * 40,
        generator_blob_sha="3" * 40,
        product_state_blob_sha="4" * 40,
        generator_event="local_test",
        generator_run_id=99,
        product_state_run=product_state,
        source_root=ROOT,
    )
    path = tmp_path / "index.json"
    path.write_bytes(MODULE._pretty_bytes(payload))
    assert (
        MODULE.check_index(index_path=path, source_root=ROOT)["contract_pass"] is True
    )
    assert payload["authority"] == {
        "technical_only": True,
        "scientific_validation": False,
        "legal_authority": False,
        "commercial_use": False,
        "engineering_design": False,
        "release": False,
    }
    payload["authority"]["release"] = True
    payload["artifact_hash"] = MODULE._artifact_hash(payload)
    path.write_bytes(MODULE._pretty_bytes(payload))
    with pytest.raises(MODULE.EvidenceIndexError, match="promotion"):
        MODULE.check_index(index_path=path, source_root=ROOT)


def test_collect_lane_runs_sigstore_before_pair_verifier(
    monkeypatch, tmp_path: Path
) -> None:
    catalog, lanes = MODULE._load_catalog(ROOT)
    lane = lanes[0]
    source = "1" * 40
    handoff_artifact = {
        "id": 11,
        "name": f"medium-technical-handoff-7-1-{source}",
        "digest": "sha256:" + "1" * 64,
        "size_in_bytes": 10,
    }
    attestation_artifact = {
        "id": 12,
        "name": handoff_artifact["name"] + "-attestation",
        "digest": "sha256:" + "2" * 64,
        "size_in_bytes": 10,
    }
    events: list[str] = []

    class FakeApi:
        repository = "owner/repository"

        def artifact_archive(self, artifact, label):
            return b"handoff" if artifact["id"] == 11 else b"attestation"

    monkeypatch.setattr(
        MODULE, "_select_lane_run", lambda *args: {"id": 7, "event": "push"}
    )
    monkeypatch.setattr(MODULE, "_validate_lane_jobs", lambda *args: (21, 22))
    monkeypatch.setattr(MODULE, "_blob_identity", lambda *args: "4" * 40)
    monkeypatch.setattr(
        MODULE,
        "_select_lane_artifacts",
        lambda *args: (handoff_artifact, attestation_artifact),
    )

    subject = json.dumps(
        {"schema_version": lane["subject_schema_version"], "source_commit_sha": source}
    ).encode()

    def archive(raw, label):
        if raw == b"handoff":
            return {"handoff-seal.json": b"{}", lane["subject_path"]: subject}
        return {"attestation.json": b"{}"}

    monkeypatch.setattr(MODULE, "strict_github_artifact_archive", archive)

    def sigstore(**kwargs):
        events.append("sigstore")
        kwargs["report_path"].write_bytes(b"[]")
        return b"[]"

    def verifier(**kwargs):
        events.append("pair")
        assert events == ["sigstore", "pair"]
        pair = json.loads(kwargs["pair_path"].read_text())
        assert pair["github_api"]["event"] == "push"
        verified = {
            "valid": True,
            "lane": "medium",
            "source_commit_sha": source,
            "source_tree_sha": "2" * 40,
            "event": "push",
            "workflow_blob_sha": "4" * 40,
            "attestor_workflow_blob_sha": "3" * 40,
            "run_attempt": 1,
            "handoff_artifact_id": 11,
            "attestation_artifact_id": 12,
        }
        return verified, MODULE._pretty_bytes(verified)

    monkeypatch.setattr(MODULE, "_run_sigstore_verification", sigstore)
    monkeypatch.setattr(MODULE, "_invoke_pair_verifier", verifier)
    row = MODULE._collect_lane(
        api=FakeApi(),
        lane=lane,
        source_sha=source,
        source_tree_sha="2" * 40,
        attestor_blob_sha="3" * 40,
        input_root=tmp_path / "input",
        bundle_root=tmp_path / "bundle",
    )
    assert events == ["sigstore", "pair"]
    assert row["contract_pass"] is True
    assert row["promotion_eligible"] is False


def _hosted_job(name: str, *, run_id: int, source: str, job_id: int) -> dict[str, object]:
    runner_id = job_id + 1000
    return {
        "id": job_id,
        "name": name,
        "run_id": run_id,
        "run_attempt": 1,
        "head_sha": source,
        "status": "completed",
        "conclusion": "success",
        "labels": ["ubuntu-latest"],
        "runner_id": runner_id,
        "runner_name": f"GitHub Actions {runner_id}",
        "runner_group_id": 0,
        "runner_group_name": "GitHub Actions",
    }


def _product_state_fixture() -> tuple[str, int, dict[str, object], list[dict[str, object]]]:
    source = "1" * 40
    run_id = 77
    run: dict[str, object] = {
        "id": run_id,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": source,
        "head_branch": "main",
        "path": ".github/workflows/product-state-current.yml",
        "name": "Product State Current",
        "event": "workflow_run",
        "head_repository": {"full_name": "owner/repository"},
    }
    jobs = [
        _hosted_job(name, run_id=run_id, source=source, job_id=index)
        for index, name in enumerate(
            (
                "build-current-state",
                "attest-current-state",
                "verify-current-state",
            ),
            start=1,
        )
    ]
    return source, run_id, run, jobs


def test_product_state_accepts_exact_367_three_stage_hosted_shape() -> None:
    source, run_id, run, jobs = _product_state_fixture()

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": len(jobs)}
            return run

    assert MODULE._product_state_run(FakeApi(), source, run_id) == run


def test_product_state_requires_exact_three_successful_first_attempt_jobs() -> None:
    source, run_id, run, jobs = _product_state_fixture()

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.endswith("/jobs?per_page=100"):
                rows = jobs + [dict(jobs[0], name="unexpected-skipped", conclusion="skipped")]
                return {"jobs": rows, "total_count": len(rows)}
            return run

    with pytest.raises(MODULE.EvidenceIndexError, match="three_stage"):
        MODULE._product_state_run(FakeApi(), source, run_id)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"labels": ["self-hosted"]}, "github_hosted_job_identity_invalid"),
        ({"labels": ["ubuntu-latest", "self-hosted"]}, "github_hosted_job_identity_invalid"),
        ({"labels": ["unknown-image"]}, "github_hosted_job_identity_invalid"),
        ({"runner_id": None}, "runner_id"),
        ({"runner_group_id": None}, "github_hosted_job_identity_invalid"),
        ({"runner_group_name": "unknown"}, "github_hosted_job_identity_invalid"),
        ({"runner_name": "runner-forged"}, "github_hosted_job_identity_invalid"),
    ],
)
def test_product_state_rejects_nonhosted_or_incomplete_job_identity(
    mutation: dict[str, object], error: str
) -> None:
    source, run_id, run, jobs = _product_state_fixture()
    jobs[1] = {**jobs[1], **mutation}

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": len(jobs)}
            return run

    with pytest.raises(MODULE.EvidenceIndexError, match=error):
        MODULE._product_state_run(FakeApi(), source, run_id)


def test_lane_job_inventory_rejects_unselected_self_hosted_job() -> None:
    _, lanes = MODULE._load_catalog(ROOT)
    lane = lanes[0]
    source = "1" * 40
    run_id = 77
    jobs = [
        {
            **_hosted_job(name, run_id=run_id, source=source, job_id=index),
            "labels": ["ubuntu-24.04"],
        }
        for index, name in enumerate(
            (
                lane["producer_job"],
                lane["attestor_job_suffix"],
                "unselected-helper",
            ),
            start=1,
        )
    ]
    jobs[2] = {
        **jobs[2],
        "labels": ["self-hosted"],
        "runner_group_id": 99,
        "runner_group_name": "private",
    }

    class FakeApi:
        def json(self, endpoint: str, label: str):
            return {"jobs": jobs, "total_count": len(jobs)}

    with pytest.raises(MODULE.EvidenceIndexError, match="github_hosted_job_identity_invalid"):
        MODULE._validate_lane_jobs(FakeApi(), lane, source, run_id)


def test_native_lane_job_inventory_accepts_declared_github_windows_image() -> None:
    _, lanes = MODULE._load_catalog(ROOT)
    lane = next(row for row in lanes if row["lane_id"] == "native")
    source = "1" * 40
    run_id = 77
    jobs = [
        {
            **_hosted_job(name, run_id=run_id, source=source, job_id=index),
            "labels": ["windows-2025" if index == 3 else "ubuntu-24.04"],
        }
        for index, name in enumerate(
            (
                lane["producer_job"],
                lane["attestor_job_suffix"],
                "windows-package",
            ),
            start=1,
        )
    ]

    class FakeApi:
        def json(self, endpoint: str, label: str):
            return {"jobs": jobs, "total_count": len(jobs)}

    assert MODULE._validate_lane_jobs(FakeApi(), lane, source, run_id) == (1, 2)


def test_catalog_and_index_schemas_validate() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    catalog = json.loads((ROOT / MODULE.CATALOG_PATH).read_text())
    catalog_schema = json.loads((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_text())
    jsonschema.Draft202012Validator.check_schema(catalog_schema)
    jsonschema.Draft202012Validator(catalog_schema).validate(catalog)
    index_schema = json.loads((ROOT / MODULE.INDEX_SCHEMA_PATH).read_text())
    jsonschema.Draft202012Validator.check_schema(index_schema)
    source = "1" * 40
    index = MODULE._build_index(
        catalog=catalog,
        lanes=catalog["lanes"],
        lane_rows=_lane_rows(catalog["lanes"], source),
        repository="owner/repository",
        source_sha=source,
        tree_sha="2" * 40,
        generator_blob_sha="3" * 40,
        product_state_blob_sha="4" * 40,
        generator_event="local_test",
        generator_run_id=99,
        product_state_run={"id": 88, "updated_at": "2026-08-28T01:02:03Z"},
        source_root=ROOT,
    )
    jsonschema.Draft202012Validator(index_schema).validate(index)
