from __future__ import annotations

import binascii
from copy import deepcopy
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


def test_issue_state_exact_bundle_rejects_extra_traversal_and_symlink() -> None:
    members = {path: b"x" for path in MODULE.ISSUE_STATE_BUNDLE_FILES}
    assert MODULE._validate_issue_state_bundle_members(members) == members
    with pytest.raises(
        MODULE.EvidenceIndexError, match="exact_five_file_bundle_required"
    ):
        MODULE._validate_issue_state_bundle_members({**members, "extra.json": b"{}"})
    for archive in (
        _github_zip([("../issue-state-current.json", b"{}")]),
        _github_zip([("issue-state-current.json", b"{}")], mode=0o120777),
    ):
        with pytest.raises(MODULE.EvidenceIndexError):
            MODULE.strict_github_artifact_archive(archive, "issue-state")


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
                "sigstore_bundle_sha256": "sha256:" + "e" * 64,
                "handoff_seal_sha256": "sha256:" + "f" * 64,
                "verified_pair_sha256": "sha256:" + "e" * 64,
                "contract_pass": True,
                "technical_scope": lane["technical_scope"],
                "authority_not_granted": lane["authority_not_granted"],
                "promotion_eligible": False,
                "promotion_blockers": lane["promotion_blockers"],
            }
        )
    return rows


def _issue_observation(source: str) -> dict[str, object]:
    bundle_files = [
        {
            "path": path,
            "sha256": "sha256:" + f"{index + 30:064x}",
            "bytes": 100 + index,
        }
        for index, path in enumerate(MODULE.ISSUE_STATE_BUNDLE_FILES)
    ]
    digests = {row["path"]: row["sha256"] for row in bundle_files}
    value: dict[str, object] = {
        "workflow_path": MODULE.ISSUE_STATE_WORKFLOW_PATH,
        "workflow_blob_sha": "e" * 40,
        "run_id": 500,
        "run_attempt": 1,
        "event": "push",
        "job_ids": {"offline_contract": 501, "live_exact_main": 502},
        "artifact": {
            "id": 5000,
            "name": f"issue-state-current-{source}-500-1",
            "api_digest": "sha256:" + "e" * 64,
            "size_in_bytes": 500,
            "workflow_run_id": 500,
            "workflow_run_attempt": 1,
            "source_sha": source,
            "expired": False,
            "expires_at": "2026-11-29T00:00:00Z",
        },
        "bundle": {"file_count": 5, "files": bundle_files},
        "report": {
            "path": MODULE.ISSUE_STATE_REPORT_PATH.as_posix(),
            "sha256": digests[MODULE.ISSUE_STATE_REPORT_PATH.as_posix()],
            "schema_path": MODULE.ISSUE_STATE_SCHEMA_PATH.as_posix(),
            "schema_sha256": digests[MODULE.ISSUE_STATE_SCHEMA_PATH.as_posix()],
            "schema_version": "issue-state-current.v1",
            "profile": "issue_state_current.v1",
            "status": "pass",
            "contract_pass": True,
        },
        "inventory": {
            "path": MODULE.ISSUE_STATE_INVENTORY_PATH.as_posix(),
            "sha256": digests[MODULE.ISSUE_STATE_INVENTORY_PATH.as_posix()],
            "observed_at": "2026-08-31T06:30:00Z",
            "open_issue_count": 2,
            "open_issue_numbers": [247, 257],
            "projection_sha256": "sha256:" + "f" * 64,
        },
        "authority": dict(MODULE.ISSUE_STATE_FALSE_AUTHORITY),
        "technical_lane": False,
        "promotion_eligible": False,
        "claim_boundary": MODULE.ISSUE_STATE_CLAIM_BOUNDARY,
    }
    value["observation_sha256"] = MODULE._observation_hash(value)
    return value


def _upstream_roots(
    source: str, *, product_state_run_id: int = 88, nightly_run_id: int = 89
) -> dict[str, object]:
    expires_at = "2026-11-29T00:00:00Z"

    def artifact(
        artifact_id: int, name: str, run_id: int, *, size: int = 100
    ) -> dict[str, object]:
        return {
            "id": artifact_id,
            "name": name,
            "api_digest": "sha256:" + f"{artifact_id:064x}",
            "size_in_bytes": size,
            "workflow_run_id": run_id,
            "workflow_run_attempt": 1,
            "source_sha": source,
            "expired": False,
            "expires_at": expires_at,
        }

    files = [
        {
            "path": f"{MODULE.UPSTREAM_BUNDLE_PREFIX}/{name}",
            "sha256": "sha256:" + f"{index + 100:064x}",
            "bytes": 100 + index,
        }
        for index, name in enumerate(MODULE.PRODUCT_STATE_ROOT_FILES)
    ]
    manifest = {row["path"]: row for row in files}

    def root(name: str) -> dict[str, object]:
        return dict(manifest[f"{MODULE.UPSTREAM_BUNDLE_PREFIX}/{name}"])

    return {
        "product_state_artifact": artifact(
            6000,
            f"product-state-current-success-{source}",
            product_state_run_id,
            size=1000,
        ),
        "root_bundle": {
            "artifact": artifact(
                6001,
                f"product-state-final-verification-{product_state_run_id}-1-{source}",
                product_state_run_id,
                size=2000,
            ),
            "file_count": len(files),
            "files": files,
        },
        "roots": {
            "product_state_document": root("product-state.json"),
            "product_state_attestation_bundle": root("product-state.sigstore.json"),
            "product_state_attestation_report": root(
                "product-state.embedded-verification.json"
            ),
            "provenance_document": root("provenance.json"),
            "provenance_attestation_bundle": root("provenance.sigstore.json"),
            "provenance_attestation_report": root(
                "provenance.embedded-verification.json"
            ),
            "candidate_seal": root("candidate-seal.json"),
            "candidate_seal_attestation_bundle": root(
                "candidate-seal.sigstore.json"
            ),
            "candidate_seal_attestation_report": root(
                "candidate-seal.verification.json"
            ),
        },
        "overlay": {
            "direction": "nightly_to_product_state_to_evidence_index",
            "consumed": True,
            "workflow_name": "Nightly Full Quality",
            "workflow_path": MODULE.NIGHTLY_WORKFLOW_PATH,
            "workflow_blob_sha": "5" * 40,
            "run_id": nightly_run_id,
            "run_attempt": 1,
            "event": "schedule",
            "artifact": artifact(
                6002,
                f"post-main-evidence-overlay-attested-{nightly_run_id}-1-{source}",
                nightly_run_id,
                size=3000,
            ),
            "seal": root("overlay-seal.json"),
            "attestation_bundle": root("overlay.sigstore.json"),
            "attestation_report": root("overlay.final-verification.json"),
        },
    }


def _upstream_collection_fixture(
    *,
    mutate_roots=None,
    mutate_overlay=None,
):
    source = "1" * 40
    repository = "owner/repository"
    product_run_id = 88
    nightly_run_id = 89
    expires_at = "2026-11-29T00:00:00Z"
    root_members = {
        name: (json.dumps({"name": name}, sort_keys=True) + "\n").encode()
        for name in MODULE.PRODUCT_STATE_ROOT_FILES
    }
    for replay, embedded in (
        (
            "product-state.replay-verification.json",
            "product-state.embedded-verification.json",
        ),
        (
            "provenance.replay-verification.json",
            "provenance.embedded-verification.json",
        ),
        ("overlay.replay-verification.json", "overlay.final-verification.json"),
        (
            "candidate-seal.replay-verification.json",
            "candidate-seal.verification.json",
        ),
    ):
        root_members[replay] = root_members[embedded]
    root_members["overlay.privileged-verification.json"] = root_members[
        "overlay.final-verification.json"
    ]

    def api_artifact(
        artifact_id: int, name: str, run_id: int, size: int, digest: str
    ) -> dict[str, object]:
        url = (
            f"https://api.github.com/repos/{repository}/actions/artifacts/{artifact_id}"
        )
        return {
            "id": artifact_id,
            "name": name,
            "digest": digest,
            "size_in_bytes": size,
            "expired": False,
            "expires_at": expires_at,
            "url": url,
            "archive_download_url": url + "/zip",
            "workflow_run": {
                "id": run_id,
                "head_sha": source,
                "head_branch": "main",
            },
        }

    final_artifact = api_artifact(
        6000,
        f"product-state-current-success-{source}",
        product_run_id,
        1000,
        "sha256:" + "a" * 64,
    )
    signed_artifact = api_artifact(
        6002,
        f"product-state-signed-{product_run_id}-1-{source}",
        product_run_id,
        900,
        "sha256:" + "b" * 64,
    )
    nightly = {
        "id": nightly_run_id,
        "run_number": 91,
        "run_attempt": 1,
        "name": "Nightly Full Quality",
        "path": MODULE.NIGHTLY_WORKFLOW_PATH,
        "event": "schedule",
        "status": "completed",
        "conclusion": "success",
        "head_branch": "main",
        "head_sha": source,
        "head_repository": {"full_name": repository},
    }
    compact_to_final = {
        "product-state.json": "artifacts/manifests/product_state.current.v1.json",
        "product-state.sigstore.json": (
            ".ci/product-state-inputs/product-state.current.sigstore.json"
        ),
        "product-state.embedded-verification.json": (
            ".ci/product-state-inputs/product-state.current.attestation-verification.json"
        ),
        "provenance.json": (
            ".ci/product-state-inputs/product-state.provenance-bundle.v1.json"
        ),
        "provenance.sigstore.json": (
            ".ci/product-state-inputs/product-state.provenance-bundle.sigstore.json"
        ),
        "provenance.embedded-verification.json": (
            ".ci/product-state-inputs/"
            "product-state.provenance-bundle.attestation-verification.json"
        ),
        "overlay-seal.json": (
            ".ci/product-state-inputs/post-main-overlay/"
            "post-main-evidence-overlay.seal.json"
        ),
        "overlay.sigstore.json": (
            ".ci/product-state-inputs/post-main-overlay/"
            "post-main-evidence-overlay.sigstore.json"
        ),
        "overlay.privileged-verification.json": (
            ".ci/product-state-inputs/"
            "post-main-overlay-privileged-attestation-verification.json"
        ),
        "overlay.final-verification.json": (
            ".ci/product-state-inputs/"
            "post-main-overlay-final-attestation-verification.json"
        ),
        "candidate-seal.json": "product-state-candidate.seal.json",
        "candidate-seal.sigstore.json": (
            ".ci/product-state-inputs/product-state-candidate.seal.sigstore.json"
        ),
    }
    manifest = [
        {
            "path": full,
            "bytes": len(root_members[compact]),
            "sha256": MODULE._sha256_bytes(root_members[compact]),
        }
        for compact, full in sorted(compact_to_final.items(), key=lambda row: row[1])
    ]
    report = {
        "schema_version": "product-state-final-artifact-verification.v1",
        "repository": repository,
        "source_commit_sha": source,
        "workflow_path": MODULE.PRODUCT_STATE_WORKFLOW_PATH,
        "workflow_run_id": product_run_id,
        "workflow_run_number": 77,
        "workflow_run_attempt": 1,
        "main_ref_before_publish": source,
        "main_ref_after_publish": source,
        "nightly_run": {
            key: nightly[key]
            for key in (
                "id",
                "run_number",
                "run_attempt",
                "name",
                "path",
                "event",
                "conclusion",
                "head_branch",
                "head_sha",
            )
        },
        "signed_artifact": {
            "id": signed_artifact["id"],
            "name": signed_artifact["name"],
            "digest": signed_artifact["digest"],
            "raw_zip_bytes": signed_artifact["size_in_bytes"],
            "raw_zip_sha256": signed_artifact["digest"],
        },
        "final_artifact": {
            key: final_artifact[key]
            for key in (
                "id",
                "name",
                "digest",
                "size_in_bytes",
                "archive_download_url",
                "expired",
                "workflow_run",
            )
        },
        "raw_zip_bytes": final_artifact["size_in_bytes"],
        "raw_zip_sha256": final_artifact["digest"],
        "candidate_seal_sha256": MODULE._sha256_bytes(
            root_members["candidate-seal.json"]
        ),
        "candidate_seal_attestation_verification_bytes": len(
            root_members["candidate-seal.verification.json"]
        ),
        "candidate_seal_attestation_verification_sha256": MODULE._sha256_bytes(
            root_members["candidate-seal.verification.json"]
        ),
        "files": manifest,
        "technical_integrity_pass": True,
        "release_authority": False,
        "claim_boundary": (
            "Final artifact byte-integrity verification only; no release, legal, "
            "design, commercial, redistribution, or independent-verification "
            "authority is granted."
        ),
    }
    if mutate_roots is not None:
        mutate_roots(root_members, report)
    root_members["final-verification.json"] = MODULE._pretty_bytes(report)
    root_archive = _github_zip(sorted(root_members.items()))
    root_artifact = api_artifact(
        6001,
        f"product-state-final-verification-{product_run_id}-1-{source}",
        product_run_id,
        len(root_archive),
        MODULE._sha256_bytes(root_archive),
    )
    overlay_members = {
        "post-main-evidence-overlay.seal.json": root_members.get(
            "overlay-seal.json", b"{}\n"
        ),
        "post-main-evidence-overlay.sigstore.json": root_members.get(
            "overlay.sigstore.json", b"{}\n"
        ),
    }
    if mutate_overlay is not None:
        mutate_overlay(overlay_members)
    overlay_archive = _github_zip(sorted(overlay_members.items()))
    overlay_artifact = api_artifact(
        6003,
        f"post-main-evidence-overlay-attested-{nightly_run_id}-1-{source}",
        nightly_run_id,
        len(overlay_archive),
        MODULE._sha256_bytes(overlay_archive),
    )

    repository_value = repository

    class FakeApi:
        repository = repository_value

        @staticmethod
        def _api_url(endpoint: str) -> str:
            return f"https://api.github.com/repos/{repository}/{endpoint}"

        def json(self, endpoint: str, label: str):
            if endpoint == f"actions/runs/{product_run_id}/artifacts?per_page=100":
                rows = [final_artifact, root_artifact, signed_artifact]
                return {"artifacts": rows, "total_count": len(rows)}
            for artifact in (
                final_artifact,
                root_artifact,
                signed_artifact,
                overlay_artifact,
            ):
                if endpoint == f"actions/artifacts/{artifact['id']}":
                    return artifact
            if endpoint.startswith("actions/workflows/nightly-full-quality.yml/runs?"):
                return {"workflow_runs": [nightly], "total_count": 1}
            if endpoint == f"actions/runs/{nightly_run_id}/attempts/1":
                return nightly
            if endpoint == f"actions/runs/{nightly_run_id}/artifacts?per_page=100":
                return {"artifacts": [overlay_artifact], "total_count": 1}
            if endpoint.startswith("contents/.github/workflows/nightly-full-quality.yml"):
                return {
                    "type": "file",
                    "path": MODULE.NIGHTLY_WORKFLOW_PATH,
                    "sha": "2" * 40,
                    "size": 100,
                }
            raise AssertionError((endpoint, label))

        def artifact_archive(self, artifact, label):
            if artifact["id"] == root_artifact["id"]:
                return root_archive
            if artifact["id"] == overlay_artifact["id"]:
                return overlay_archive
            raise AssertionError((artifact, label))

    return FakeApi(), source, {
        "id": product_run_id,
        "run_number": 77,
        "updated_at": "2026-08-28T01:02:03Z",
    }


def test_collect_upstream_roots_preserves_exact_offline_bundle(tmp_path: Path) -> None:
    api, source, product_state = _upstream_collection_fixture()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    result = MODULE._collect_upstream_roots(
        api=api,
        source_sha=source,
        product_state_run=product_state,
        source_root=ROOT,
        bundle_root=bundle,
    )
    assert result["root_bundle"]["file_count"] == len(
        MODULE.PRODUCT_STATE_ROOT_FILES
    )
    assert result["overlay"]["consumed"] is True
    assert tuple(sorted(path.name for path in (bundle / "upstream").iterdir())) == (
        MODULE.PRODUCT_STATE_ROOT_FILES
    )


def test_collect_upstream_roots_rejects_float_product_run_number(
    tmp_path: Path,
) -> None:
    api, source, product_state = _upstream_collection_fixture()
    product_state["run_number"] = 77.0
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    with pytest.raises(
        MODULE.EvidenceIndexError,
        match="safe_positive_integer_required:product_state_run_number",
    ):
        MODULE._collect_upstream_roots(
            api=api,
            source_sha=source,
            product_state_run=product_state,
            source_root=ROOT,
            bundle_root=bundle,
        )


def test_common_run_identity_rejects_float_run_number() -> None:
    source = "1" * 40
    run = {**_issue_run(source), "run_number": 70.0}
    with pytest.raises(
        MODULE.EvidenceIndexError,
        match="safe_positive_integer_required:run_number:Issue State Current",
    ):
        MODULE._validate_run_common(
            run,
            repository="betelgeuze-kang/Structural-Analysis",
            source_sha=source,
            workflow_path=MODULE.ISSUE_STATE_WORKFLOW_PATH,
            workflow_name="Issue State Current",
            allowed_events={"push"},
        )


@pytest.mark.parametrize(
    ("mutate_roots", "mutate_overlay", "failure"),
    [
        (
            lambda members, report: report["signed_artifact"].__setitem__("id", 1),
            None,
            "product_state_final_verification_identity_invalid",
        ),
        (
            lambda members, report: report["nightly_run"].__setitem__("id", True),
            None,
            "safe_positive_integer_required:nightly_run_id",
        ),
        (
            lambda members, report: report.__setitem__("workflow_run_id", True),
            None,
            "product_state_final_verification_identity_invalid",
        ),
        (
            lambda members, report: report.__setitem__("workflow_run_attempt", True),
            None,
            "product_state_final_verification_identity_invalid",
        ),
        (
            lambda members, report: report.__setitem__("raw_zip_bytes", 1000.0),
            None,
            "product_state_final_verification_identity_invalid",
        ),
        (
            lambda members, report: report.__setitem__(
                "candidate_seal_attestation_verification_bytes",
                float(report["candidate_seal_attestation_verification_bytes"]),
            ),
            None,
            "product_state_offline_replay_root_mismatch",
        ),
        (
            lambda members, report: members.pop("candidate-seal.sigstore.json"),
            None,
            "product_state_root_bundle_member_set_invalid",
        ),
        (
            lambda members, report: members.__setitem__("extra.json", b"{}\n"),
            None,
            "product_state_root_bundle_member_set_invalid",
        ),
        (
            None,
            lambda members: members.__setitem__(
                "post-main-evidence-overlay.seal.json", b'{"forged":true}\n'
            ),
            "product_state_consumed_overlay_bytes_mismatch",
        ),
    ],
)
def test_collect_upstream_roots_rejects_broken_transitive_binding(
    tmp_path: Path, mutate_roots, mutate_overlay, failure: str
) -> None:
    api, source, product_state = _upstream_collection_fixture(
        mutate_roots=mutate_roots,
        mutate_overlay=mutate_overlay,
    )
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    with pytest.raises(MODULE.EvidenceIndexError, match=failure):
        MODULE._collect_upstream_roots(
            api=api,
            source_sha=source,
            product_state_run=product_state,
            source_root=ROOT,
            bundle_root=bundle,
        )


def _issue_run(source: str, run_id: int = 700) -> dict[str, object]:
    return {
        "id": run_id,
        "run_number": 70,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": source,
        "head_branch": "main",
        "path": MODULE.ISSUE_STATE_WORKFLOW_PATH,
        "name": "Issue State Current",
        "event": "push",
        "head_repository": {"full_name": "betelgeuze-kang/Structural-Analysis"},
    }


def test_issue_state_run_poll_is_bounded_and_selects_unique_exact_push() -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    specification = catalog["issue_state_observation"]
    source = "1" * 40
    pending = {**_issue_run(source), "status": "in_progress", "conclusion": None}
    complete = _issue_run(source)
    inventories = [
        {"workflow_runs": [], "total_count": 0},
        {"workflow_runs": [pending], "total_count": 1},
        {"workflow_runs": [complete], "total_count": 1},
    ]
    sleeps: list[int] = []

    class FakeApi:
        repository = "betelgeuze-kang/Structural-Analysis"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                assert "event=push" in endpoint and f"head_sha={source}" in endpoint
                return inventories.pop(0)
            return complete

    selected = MODULE._select_issue_state_run(
        FakeApi(),
        specification,
        source,
        max_poll_attempts=3,
        poll_interval_seconds=0,
        sleep=sleeps.append,
    )
    assert selected == complete
    assert sleeps == [0, 0]


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (
            lambda source: {
                "workflow_runs": [_issue_run(source, 700), _issue_run(source, 701)],
                "total_count": 2,
            },
            "unique_exact_source_push_run_required",
        ),
        (
            lambda source: {
                "workflow_runs": [
                    _issue_run(source, 700),
                    {**_issue_run(source, 701), "run_attempt": 2},
                ],
                "total_count": 2,
            },
            "unique_exact_source_push_run_required",
        ),
        (
            lambda source: {
                "workflow_runs": [_issue_run(source, 700)],
                "total_count": 101,
            },
            "workflow_run_inventory_invalid",
        ),
        (
            lambda source: {
                "workflow_runs": [{**_issue_run(source, 700), "run_attempt": True}],
                "total_count": 1,
            },
            "exact_source_push_run_identity_invalid",
        ),
    ],
)
def test_issue_state_run_rejects_duplicate_or_truncated_inventory(
    payload, error: str
) -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    source = "1" * 40

    class FakeApi:
        repository = "betelgeuze-kang/Structural-Analysis"

        def json(self, endpoint: str, label: str):
            return payload(source)

    with pytest.raises(MODULE.EvidenceIndexError, match=error):
        MODULE._select_issue_state_run(
            FakeApi(),
            catalog["issue_state_observation"],
            source,
            max_poll_attempts=1,
            poll_interval_seconds=0,
            sleep=lambda _: None,
        )


def _technical_lane_run(
    lane: dict[str, object], source: str, *, run_id: int = 701
) -> dict[str, object]:
    return {
        "id": run_id,
        "run_number": 71,
        "run_attempt": 1,
        "status": "completed",
        "conclusion": "success",
        "head_sha": source,
        "head_branch": "main",
        "path": lane["workflow_path"],
        "name": lane["workflow_name"],
        "event": lane["allowed_events"][0],
        "head_repository": {"full_name": "betelgeuze-kang/Structural-Analysis"},
    }


def test_technical_lane_selector_uses_complete_all_status_exact_sha_inventory() -> None:
    _catalog, lanes = MODULE._load_catalog(ROOT)
    lane = lanes[0]
    source = "1" * 40
    run = _technical_lane_run(lane, source)

    class FakeApi:
        repository = "betelgeuze-kang/Structural-Analysis"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                assert f"head_sha={source}" in endpoint
                assert "status=" not in endpoint
                return {"workflow_runs": [run], "total_count": 1}
            return run

    assert MODULE._select_lane_run(FakeApi(), lane, source) == run


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        (
            lambda lane, source: {
                "workflow_runs": [
                    _technical_lane_run(lane, source, run_id=701),
                    {
                        **_technical_lane_run(lane, source, run_id=702),
                        "status": "completed",
                        "conclusion": "failure",
                    },
                ],
                "total_count": 2,
            },
            "unique_exact_source_run_required",
        ),
        (
            lambda lane, source: {
                "workflow_runs": [
                    _technical_lane_run(lane, source, run_id=701),
                    {
                        **_technical_lane_run(lane, source, run_id=702),
                        "run_attempt": 2,
                    },
                ],
                "total_count": 2,
            },
            "unique_exact_source_run_required",
        ),
        (
            lambda lane, source: {
                "workflow_runs": [_technical_lane_run(lane, source)],
                "total_count": 101,
            },
            "workflow_run_inventory_invalid",
        ),
        (
            lambda lane, source: {
                "workflow_runs": [
                    {
                        **_technical_lane_run(lane, source),
                        "status": "completed",
                        "conclusion": "failure",
                    }
                ],
                "total_count": 1,
            },
            "first_attempt_run_not_successful",
        ),
        (
            lambda lane, source: {
                "workflow_runs": [
                    {**_technical_lane_run(lane, source), "run_attempt": 1.0}
                ],
                "total_count": 1,
            },
            "exact_source_run_identity_invalid",
        ),
    ],
)
def test_technical_lane_selector_rejects_hidden_duplicate_truncation_or_failure(
    payload, error: str
) -> None:
    _catalog, lanes = MODULE._load_catalog(ROOT)
    lane = lanes[0]
    source = "1" * 40

    class FakeApi:
        repository = "betelgeuze-kang/Structural-Analysis"

        def json(self, endpoint: str, label: str):
            return payload(lane, source)

    with pytest.raises(MODULE.EvidenceIndexError, match=error):
        MODULE._select_lane_run(FakeApi(), lane, source)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"expired": True}, "artifact_identity_invalid"),
        ({"digest": "not-a-digest"}, "artifact_identity_invalid"),
        ({"size_in_bytes": 0}, "safe_positive_integer_required"),
        ({"expires_at": "not-a-timestamp"}, "datetime_invalid"),
    ],
)
def test_issue_state_artifact_rejects_invalid_digest_size_or_expiry(
    mutation: dict[str, object], error: str
) -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    specification = catalog["issue_state_observation"]
    source = "1" * 40
    run_id = 700
    name = f"issue-state-current-{source}-{run_id}-1"
    workflow_run = {
        "id": run_id,
        "head_sha": source,
        "head_branch": "main",
        "repository_id": 1136685613,
        "head_repository_id": 1136685613,
    }
    artifact = {
        "id": 900,
        "name": name,
        "digest": "sha256:" + "a" * 64,
        "size_in_bytes": 100,
        "expired": False,
        "expires_at": "2026-11-29T00:00:00Z",
        "url": "https://api.github.com/repos/betelgeuze-kang/Structural-Analysis/actions/artifacts/900",
        "archive_download_url": "https://api.github.com/repos/betelgeuze-kang/Structural-Analysis/actions/artifacts/900/zip",
        "workflow_run": workflow_run,
    }
    artifact.update(mutation)

    class FakeApi:
        repository = "betelgeuze-kang/Structural-Analysis"

        def _api_url(self, endpoint: str) -> str:
            return f"https://api.github.com/repos/{self.repository}/{endpoint}"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/runs/"):
                return {"artifacts": [artifact], "total_count": 1}
            return artifact

    with pytest.raises(MODULE.EvidenceIndexError, match=error):
        MODULE._issue_state_artifact(FakeApi(), specification, source, run_id)


def test_issue_state_requires_both_successful_github_hosted_jobs() -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    specification = catalog["issue_state_observation"]
    source = "1" * 40
    run_id = 700
    jobs = [
        {
            **_hosted_job(name, run_id=run_id, source=source, job_id=index),
            "labels": ["ubuntu-24.04"],
        }
        for index, name in enumerate(specification["required_jobs"], start=1)
    ]
    jobs[1]["conclusion"] = "skipped"

    class FakeApi:
        def json(self, endpoint: str, label: str):
            return {"jobs": jobs, "total_count": len(jobs)}

    with pytest.raises(
        MODULE.EvidenceIndexError, match="github_hosted_job_identity_invalid"
    ):
        MODULE._validate_issue_state_jobs(FakeApi(), specification, source, run_id)


def test_issue_state_job_inventory_rejects_float_total_count() -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    specification = catalog["issue_state_observation"]
    source = "1" * 40
    run_id = 700
    jobs = [
        {
            **_hosted_job(name, run_id=run_id, source=source, job_id=index),
            "labels": ["ubuntu-24.04"],
        }
        for index, name in enumerate(specification["required_jobs"], start=1)
    ]

    class FakeApi:
        def json(self, endpoint: str, label: str):
            return {"jobs": jobs, "total_count": float(len(jobs))}

    with pytest.raises(
        MODULE.EvidenceIndexError, match="issue_state_exact_two_job_success_required"
    ):
        MODULE._validate_issue_state_jobs(FakeApi(), specification, source, run_id)


def test_issue_state_replay_is_artifact_only_and_never_requeries_live_issues(
    monkeypatch, tmp_path: Path
) -> None:
    commands: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = b"issue state current report: pass\n"

    def run(command, **kwargs):
        commands.append(command)
        return Result()

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    MODULE._run_issue_state_replay(
        source_root=ROOT,
        report_path=tmp_path / "report.json",
        inventory_path=tmp_path / "inventory.json",
        schema_path=tmp_path / "schema.json",
        repository="betelgeuze-kang/Structural-Analysis",
        source_sha="1" * 40,
        source_tree_sha="2" * 40,
        run_id=700,
    )
    assert len(commands) == 1
    assert "--check-report" in commands[0]
    assert "--verify-github" not in commands[0]


def test_issue_state_observation_rejects_authority_and_digest_tampering() -> None:
    catalog, _ = MODULE._load_catalog(ROOT)
    source = "1" * 40
    for mutation, error in (
        (
            lambda value: value["authority"].__setitem__("release_authority", True),
            "issue_state_contract_invalid",
        ),
        (
            lambda value: value.__setitem__("observation_sha256", "sha256:" + "0" * 64),
            "issue_state_contract_invalid",
        ),
    ):
        observation = deepcopy(_issue_observation(source))
        mutation(observation)
        if observation["authority"]["release_authority"] is True:
            observation["observation_sha256"] = MODULE._observation_hash(observation)
        with pytest.raises(MODULE.EvidenceIndexError, match=error):
            MODULE._check_issue_state_observation(
                observation,
                issue_state=catalog["issue_state_observation"],
                source_sha=source,
            )


def test_catalog_and_index_preserve_technical_only_authority(tmp_path: Path) -> None:
    catalog, lanes = MODULE._load_catalog(ROOT)
    source = "1" * 40
    product_state = {"id": 88, "updated_at": "2026-08-28T01:02:03Z"}
    payload = MODULE._build_index(
        catalog=catalog,
        lanes=lanes,
        lane_rows=_lane_rows(lanes, source),
        issue_state_observation=_issue_observation(source),
        repository="owner/repository",
        source_sha=source,
        tree_sha="2" * 40,
        generator_blob_sha="3" * 40,
        product_state_blob_sha="4" * 40,
        generator_event="workflow_run",
        generator_run_id=99,
        product_state_run=product_state,
        upstream_roots=_upstream_roots(source),
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
    lane_bundle = tmp_path / "bundle" / "medium"
    assert (lane_bundle / "sigstore-bundle.json").read_bytes() == b"{}"
    assert (lane_bundle / "handoff-seal.json").read_bytes() == b"{}"
    assert row["sigstore_bundle_sha256"] == MODULE._sha256_bytes(b"{}")
    assert row["handoff_seal_sha256"] == MODULE._sha256_bytes(b"{}")


@pytest.mark.parametrize("alias", [True, 1.0])
def test_pair_verifier_output_rejects_run_attempt_alias(
    monkeypatch, tmp_path: Path, alias: object
) -> None:
    payload = MODULE._pretty_bytes(
        {
            "valid": True,
            "lane": "medium",
            "source_commit_sha": "1" * 40,
            "run_attempt": alias,
        }
    )

    class Completed:
        returncode = 0
        stdout = payload

    monkeypatch.setattr(MODULE.subprocess, "run", lambda *args, **kwargs: Completed())
    with pytest.raises(MODULE.EvidenceIndexError, match="technical_pair_result_invalid"):
        MODULE._invoke_pair_verifier(
            pair_path=tmp_path / "pair.json",
            handoff_archive_path=tmp_path / "handoff.zip",
            attestation_archive_path=tmp_path / "attestation.zip",
            report_path=tmp_path / "report.json",
            expected_lane="medium",
            expected_source_sha="1" * 40,
        )


def _hosted_job(
    name: str, *, run_id: int, source: str, job_id: int
) -> dict[str, object]:
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


def _product_state_fixture() -> tuple[
    str, int, dict[str, object], list[dict[str, object]]
]:
    source = "1" * 40
    run_id = 77
    run: dict[str, object] = {
        "id": run_id,
        "run_number": 77,
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
                "replay-final-attestations",
            ),
            start=1,
        )
    ]
    return source, run_id, run, jobs


def test_product_state_accepts_exact_four_stage_hosted_shape() -> None:
    source, run_id, run, jobs = _product_state_fixture()

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                return {"workflow_runs": [run], "total_count": 1}
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": len(jobs)}
            return run

    assert MODULE._product_state_run(FakeApi(), source, run_id) == run


def test_product_state_job_inventory_rejects_float_total_count() -> None:
    source, run_id, run, jobs = _product_state_fixture()

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                return {"workflow_runs": [run], "total_count": 1}
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": float(len(jobs))}
            return run

    with pytest.raises(
        MODULE.EvidenceIndexError, match="product_state_job_inventory_invalid"
    ):
        MODULE._product_state_run(FakeApi(), source, run_id)


def test_product_state_requires_exact_four_successful_first_attempt_jobs() -> None:
    source, run_id, run, jobs = _product_state_fixture()

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                return {"workflow_runs": [run], "total_count": 1}
            if endpoint.endswith("/jobs?per_page=100"):
                rows = jobs + [
                    dict(jobs[0], name="unexpected-skipped", conclusion="skipped")
                ]
                return {"jobs": rows, "total_count": len(rows)}
            return run

    with pytest.raises(MODULE.EvidenceIndexError, match="four_stage"):
        MODULE._product_state_run(FakeApi(), source, run_id)


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"labels": ["self-hosted"]}, "github_hosted_job_identity_invalid"),
        (
            {"labels": ["ubuntu-latest", "self-hosted"]},
            "github_hosted_job_identity_invalid",
        ),
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
            if endpoint.startswith("actions/workflows/"):
                return {"workflow_runs": [run], "total_count": 1}
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": len(jobs)}
            return run

    with pytest.raises(MODULE.EvidenceIndexError, match=error):
        MODULE._product_state_run(FakeApi(), source, run_id)


def test_product_state_rejects_exact_source_attempt_two_sibling() -> None:
    source, run_id, run, jobs = _product_state_fixture()
    attempt_two = {**run, "id": run_id + 1, "run_attempt": 2}

    class FakeApi:
        repository = "owner/repository"

        def json(self, endpoint: str, label: str):
            if endpoint.startswith("actions/workflows/"):
                return {"workflow_runs": [run, attempt_two], "total_count": 2}
            if endpoint.endswith("/jobs?per_page=100"):
                return {"jobs": jobs, "total_count": len(jobs)}
            return run

    with pytest.raises(
        MODULE.EvidenceIndexError,
        match="product_state_unique_exact_source_run_required",
    ):
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

    with pytest.raises(
        MODULE.EvidenceIndexError, match="github_hosted_job_identity_invalid"
    ):
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


def test_lane_job_inventory_rejects_float_total_count() -> None:
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
            (lane["producer_job"], lane["attestor_job_suffix"]), start=1
        )
    ]

    class FakeApi:
        def json(self, endpoint: str, label: str):
            return {"jobs": jobs, "total_count": float(len(jobs))}

    with pytest.raises(
        MODULE.EvidenceIndexError, match="job_inventory_must_be_complete"
    ):
        MODULE._validate_lane_jobs(FakeApi(), lane, source, run_id)


def test_artifact_identity_rejects_float_workflow_run_id() -> None:
    source = "1" * 40
    run_id = 77
    artifact_id = 88

    class FakeApi:
        repository = "owner/repository"

        def _api_url(self, endpoint: str) -> str:
            return f"https://api.github.com/repos/{self.repository}/{endpoint}"

    artifact_url = FakeApi()._api_url(f"actions/artifacts/{artifact_id}")
    artifact = {
        "id": artifact_id,
        "name": "artifact",
        "digest": "sha256:" + "a" * 64,
        "size_in_bytes": 100,
        "expired": False,
        "url": artifact_url,
        "archive_download_url": artifact_url + "/zip",
        "workflow_run": {
            "id": float(run_id),
            "head_sha": source,
            "head_branch": "main",
        },
    }
    with pytest.raises(MODULE.EvidenceIndexError, match="artifact_identity_invalid"):
        MODULE._artifact_identity(
            FakeApi(),
            artifact,
            lane_id="test",
            expected_id=artifact_id,
            expected_name="artifact",
            run_id=run_id,
            source_sha=source,
        )


def _valid_index_payload() -> tuple[dict[str, object], dict[str, object]]:
    catalog = json.loads((ROOT / MODULE.CATALOG_PATH).read_text())
    source = "1" * 40
    index = MODULE._build_index(
        catalog=catalog,
        lanes=catalog["lanes"],
        lane_rows=_lane_rows(catalog["lanes"], source),
        issue_state_observation=_issue_observation(source),
        repository="owner/repository",
        source_sha=source,
        tree_sha="2" * 40,
        generator_blob_sha="3" * 40,
        product_state_blob_sha="4" * 40,
        generator_event="workflow_run",
        generator_run_id=99,
        product_state_run={"id": 88, "updated_at": "2026-08-28T01:02:03Z"},
        upstream_roots=_upstream_roots(source),
        source_root=ROOT,
    )
    return catalog, index


@pytest.mark.parametrize(
    ("field", "alias"),
    [("required_lane_count", True), ("required_run_attempt", 1.0)],
)
def test_catalog_loader_rejects_boolean_or_float_integer_aliases(
    tmp_path: Path, field: str, alias: object
) -> None:
    catalog = json.loads((ROOT / MODULE.CATALOG_PATH).read_text())
    catalog[field] = alias
    path = tmp_path / MODULE.CATALOG_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(MODULE._pretty_bytes(catalog))
    schema_path = tmp_path / MODULE.CATALOG_SCHEMA_PATH
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_bytes((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_bytes())
    with pytest.raises(MODULE.EvidenceIndexError, match="catalog_header_invalid"):
        MODULE._load_catalog(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row.__setitem__(
            "technical_scope",
            "Independent scientific validation and release-authoritative results.",
        ),
        lambda row: row.__setitem__("allowed_events", ["workflow_dispatch"]),
        lambda row: row.__setitem__(
            "authority_not_granted",
            [
                value
                for value in row["authority_not_granted"]
                if value != "scientific_validation"
            ],
        ),
    ],
)
def test_catalog_loader_binds_every_lane_to_schema_full_row_const(
    tmp_path: Path, mutation
) -> None:
    catalog = json.loads((ROOT / MODULE.CATALOG_PATH).read_text())
    mutation(catalog["lanes"][0])
    catalog_path = tmp_path / MODULE.CATALOG_PATH
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_bytes(MODULE._pretty_bytes(catalog))
    schema_path = tmp_path / MODULE.CATALOG_SCHEMA_PATH
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_bytes((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_bytes())
    with pytest.raises(
        MODULE.EvidenceIndexError, match="catalog_schema_lane_constants_mismatch"
    ):
        MODULE._load_catalog(tmp_path)


def test_catalog_loader_rejects_catalog_and_schema_policy_drift_in_lockstep(
    tmp_path: Path,
) -> None:
    catalog = json.loads((ROOT / MODULE.CATALOG_PATH).read_text())
    schema = json.loads((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_text())
    drift = "Independent scientific validation and release-authoritative results."
    catalog["lanes"][0]["technical_scope"] = drift
    schema["properties"]["lanes"]["prefixItems"][0]["const"][
        "technical_scope"
    ] = drift
    catalog_path = tmp_path / MODULE.CATALOG_PATH
    catalog_path.parent.mkdir(parents=True)
    catalog_path.write_bytes(MODULE._pretty_bytes(catalog))
    schema_path = tmp_path / MODULE.CATALOG_SCHEMA_PATH
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path.write_bytes(MODULE._pretty_bytes(schema))
    with pytest.raises(MODULE.EvidenceIndexError, match="catalog_lane_contract_invalid"):
        MODULE._load_catalog(tmp_path)


def test_catalog_and_index_schemas_validate() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    catalog, index = _valid_index_payload()
    catalog_schema = json.loads((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_text())
    jsonschema.Draft202012Validator.check_schema(catalog_schema)
    format_checker = jsonschema.FormatChecker()
    jsonschema.Draft202012Validator(
        catalog_schema, format_checker=format_checker
    ).validate(catalog)
    index_schema = json.loads((ROOT / MODULE.INDEX_SCHEMA_PATH).read_text())
    jsonschema.Draft202012Validator.check_schema(index_schema)
    jsonschema.Draft202012Validator(
        index_schema, format_checker=format_checker
    ).validate(index)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.__setitem__("contract_pass", 1),
        lambda value: value.__setitem__("technical_pair_count", True),
        lambda value: value["generator"].__setitem__("run_attempt", True),
        lambda value: value["lanes"][0].__setitem__("run_attempt", True),
        lambda value: value["authority"].__setitem__("technical_only", 1),
        lambda value: value["authority"].__setitem__("release", 0),
        lambda value: value["upstream"]["product_state_artifact"].__setitem__(
            "workflow_run_id", 88.0
        ),
        lambda value: value["upstream"]["root_bundle"]["artifact"].__setitem__(
            "workflow_run_id", 88.0
        ),
        lambda value: value["upstream"]["overlay"]["artifact"].__setitem__(
            "workflow_run_id", 89.0
        ),
    ],
)
def test_standalone_checker_rejects_boolean_integer_aliases(
    tmp_path: Path, mutation
) -> None:
    _catalog, index = _valid_index_payload()
    mutation(index)
    index["artifact_hash"] = MODULE._artifact_hash(index)
    path = tmp_path / "index.json"
    path.write_bytes(MODULE._pretty_bytes(index))
    with pytest.raises(MODULE.EvidenceIndexError):
        MODULE.check_index(index_path=path, source_root=ROOT)


@pytest.mark.parametrize(
    ("target", "timestamp"),
    [
        ("generated_at", "2026-08-28"),
        ("generated_at", "2026-08-28T01:02:03"),
        ("issue_expiry", "2026-11-29T00:00:00"),
        ("upstream_expiry", "2026-11-29"),
        ("observed_at", "2026-13-40T25:61:61Z"),
        ("observed_at", "0000-00-00T00:00:00Z"),
        ("observed_at", "2026-02-29T00:00:00Z"),
    ],
)
def test_standalone_checker_rejects_non_rfc3339_or_naive_timestamps(
    tmp_path: Path, target: str, timestamp: str
) -> None:
    _catalog, index = _valid_index_payload()
    if target == "generated_at":
        index["generated_at"] = timestamp
    elif target == "issue_expiry":
        index["issue_state_observation"]["artifact"]["expires_at"] = timestamp
        index["issue_state_observation"]["observation_sha256"] = (
            MODULE._observation_hash(index["issue_state_observation"])
        )
    elif target == "observed_at":
        index["issue_state_observation"]["inventory"]["observed_at"] = timestamp
        index["issue_state_observation"]["observation_sha256"] = (
            MODULE._observation_hash(index["issue_state_observation"])
        )
    else:
        index["upstream"]["product_state_artifact"]["expires_at"] = timestamp
    index["artifact_hash"] = MODULE._artifact_hash(index)
    path = tmp_path / "index.json"
    path.write_bytes(MODULE._pretty_bytes(index))
    with pytest.raises(MODULE.EvidenceIndexError, match="datetime"):
        MODULE.check_index(index_path=path, source_root=ROOT)


def test_schema_rejects_lane_and_issue_bundle_topology_substitution() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    catalog, index = _valid_index_payload()
    catalog_schema = json.loads((ROOT / MODULE.CATALOG_SCHEMA_PATH).read_text())
    index_schema = json.loads((ROOT / MODULE.INDEX_SCHEMA_PATH).read_text())
    validators = (
        jsonschema.Draft202012Validator(
            catalog_schema, format_checker=jsonschema.FormatChecker()
        ),
        jsonschema.Draft202012Validator(
            index_schema, format_checker=jsonschema.FormatChecker()
        ),
    )

    swapped_catalog = deepcopy(catalog)
    swapped_catalog["lanes"][0], swapped_catalog["lanes"][1] = (
        swapped_catalog["lanes"][1],
        swapped_catalog["lanes"][0],
    )
    assert list(validators[0].iter_errors(swapped_catalog))

    mutated_catalog = deepcopy(catalog)
    mutated_catalog["lanes"][0]["category"] = "distribution"
    assert list(validators[0].iter_errors(mutated_catalog))

    duplicated_lane_index = deepcopy(index)
    duplicated_lane_index["lanes"][0] = deepcopy(duplicated_lane_index["lanes"][1])
    assert list(validators[1].iter_errors(duplicated_lane_index))

    mutated_lane_index = deepcopy(index)
    mutated_lane_index["lanes"][0]["technical_subject_path"] = (
        mutated_lane_index["lanes"][1]["technical_subject_path"]
    )
    assert list(validators[1].iter_errors(mutated_lane_index))

    swapped_issue_index = deepcopy(index)
    issue_files = swapped_issue_index["issue_state_observation"]["bundle"]["files"]
    issue_files[0], issue_files[1] = issue_files[1], issue_files[0]
    assert list(validators[1].iter_errors(swapped_issue_index))


@pytest.mark.parametrize(
    ("target", "timestamp"),
    [
        ("generated_at", "2026-08-28"),
        ("generated_at", "2026-08-28T01:02:03"),
        ("generated_at", "0000-01-01T00:00:00Z"),
        ("generated_at", "2026-04-31T00:00:00Z"),
        ("generated_at", "2026-01-01T24:00:00Z"),
        ("generated_at", "2026-01-01T00:60:00Z"),
        ("generated_at", "2026-01-01T00:00:60Z"),
        ("generated_at", "2026-01-01T00:00:00+24:00"),
        ("generated_at", "2026-01-01T00:00:00Z\n"),
        ("observed_at", "2026-13-40T25:61:61Z"),
        ("observed_at", "2026-02-29T00:00:00Z"),
        ("observed_at", "2026-01-01T00:00:00Z\n"),
        ("issue_expiry", "2026-11-31T00:00:00Z"),
        ("issue_expiry", "2026-01-01T00:00:00Z\n"),
        ("upstream_expiry", "1900-02-29T00:00:00Z"),
        ("upstream_expiry", "2026-01-01T00:00:00Z\n"),
    ],
)
def test_schema_rejects_invalid_timestamp_without_optional_format_checker(
    target: str, timestamp: str
) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    _catalog, index = _valid_index_payload()
    if target == "generated_at":
        index["generated_at"] = timestamp
    elif target == "observed_at":
        index["issue_state_observation"]["inventory"]["observed_at"] = timestamp
    elif target == "issue_expiry":
        index["issue_state_observation"]["artifact"]["expires_at"] = timestamp
    else:
        index["upstream"]["product_state_artifact"]["expires_at"] = timestamp
    schema = json.loads((ROOT / MODULE.INDEX_SCHEMA_PATH).read_text())
    # JSON Schema deliberately treats unknown formats as annotations.  The
    # evidence contract must therefore stay fail-closed even when the optional
    # RFC 3339 format package is absent from a clean runner.
    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors(index))


@pytest.mark.parametrize(
    "timestamp",
    [
        "0001-01-01T00:00:00Z",
        "0004-02-29T23:59:59Z",
        "1900-02-28T12:34:56Z",
        "2000-02-29T12:34:56.123456Z",
        "2024-02-29T00:00:00+23:59",
        "9999-12-31T23:59:59-23:59",
    ],
)
def test_schema_accepts_valid_timestamp_boundaries_without_format_checker(
    timestamp: str,
) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    _catalog, index = _valid_index_payload()
    index["generated_at"] = timestamp
    schema = json.loads((ROOT / MODULE.INDEX_SCHEMA_PATH).read_text())
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(index)
