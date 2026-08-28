from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import zipfile

from jsonschema import Draft202012Validator
import pytest

import scripts.verify_technical_evidence_handoff_pair as pair_verifier


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "canonical/technical-evidence-handoff-pair.v1.schema.json"
SOURCE_SHA = "1" * 40
TREE_SHA = "2" * 40
WORKFLOW_BLOB_SHA = "3" * 40
ATTESTOR_BLOB_SHA = "4" * 40
RUN_ID = 123456
RUN_ATTEMPT = 2
SUBJECT_PATH = "artifacts/medium-scale/current-source/medium-scale-execution.v1.json"
BUNDLE_PATH = "attestation.json"


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, allow_nan=False, sort_keys=True) + "\n").encode()


def _write_zip(path: Path, entries: list[tuple[str | zipfile.ZipInfo, bytes]]) -> bytes:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries:
            archive.writestr(name, raw)
    return path.read_bytes()


def _fixture(tmp_path: Path) -> dict[str, object]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    subject_raw = _json_bytes(
        {
            "schema_version": "medium-scale-current-source-execution.v1",
            "source_commit_sha": SOURCE_SHA,
            "status": "technical_ready",
        }
    )
    seal_raw = _json_bytes(
        {
            "artifact_files": {SUBJECT_PATH: _sha256(subject_raw)},
            "lane": "medium",
            "run_attempt": RUN_ATTEMPT,
            "run_id": RUN_ID,
            "schema_version": "technical-evidence-handoff-seal.v1",
            "source_sha": SOURCE_SHA,
            "source_workflow_path": ".github/workflows/medium-scale-current-source.yml",
            "source_workflow_sha": SOURCE_SHA,
        }
    )
    handoff = tmp_path / "handoff.zip"
    handoff_raw = _write_zip(
        handoff,
        [(SUBJECT_PATH, subject_raw), ("handoff-seal.json", seal_raw)],
    )

    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {"buildDefinition": {"buildType": "fixture"}},
        "subject": [
            {
                "name": "medium-scale-execution.v1.json",
                "digest": {"sha256": _sha256(subject_raw).removeprefix("sha256:")},
            }
        ],
    }
    bundle = {
        "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
        "verificationMaterial": {"certificate": {"rawBytes": "fixture"}},
        "dsseEnvelope": {
            "payload": base64.b64encode(_json_bytes(statement)).decode("ascii"),
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": base64.b64encode(b"fixture-signature").decode("ascii")}],
        },
    }
    bundle_raw = _json_bytes(bundle)
    attestation = tmp_path / "attestation.zip"
    attestation_raw = _write_zip(attestation, [(BUNDLE_PATH, bundle_raw)])

    report = [
        {
            "attestation": {
                "bundle": deepcopy(bundle),
                "bundle_url": "",
                "initiator": "",
            },
            "verificationResult": {
                "signature": {"certificate": {"issuer": "fixture"}},
                "verifiedTimestamps": [{"type": "transparency-log"}],
                "statement": deepcopy(statement),
            },
        }
    ]
    report_path = tmp_path / "verification.json"
    report_raw = _json_bytes(report)
    report_path.write_bytes(report_raw)

    artifact_name = f"medium-technical-handoff-{RUN_ID}-{RUN_ATTEMPT}-{SOURCE_SHA}"
    pair = {
        "schema_version": "technical-evidence-handoff-pair.v1",
        "lane": "medium",
        "github_api": {
            "repository": "example/structural-analysis",
            "source_commit_sha": SOURCE_SHA,
            "source_tree_sha": TREE_SHA,
            "source_ref": "refs/heads/main",
            "workflow_path": ".github/workflows/medium-scale-current-source.yml",
            "workflow_blob_sha": WORKFLOW_BLOB_SHA,
            "attestor_workflow_path": ".github/workflows/_technical-evidence-attest.yml",
            "attestor_workflow_blob_sha": ATTESTOR_BLOB_SHA,
            "run_id": RUN_ID,
            "run_attempt": RUN_ATTEMPT,
        },
        "handoff_artifact": {
            "id": 8001,
            "name": artifact_name,
            "api_digest": _sha256(handoff_raw),
            "workflow_run_id": RUN_ID,
            "workflow_run_attempt": RUN_ATTEMPT,
            "source_sha": SOURCE_SHA,
        },
        "handoff_seal": {
            "path": "handoff-seal.json",
            "sha256": _sha256(seal_raw),
        },
        "technical_subject": {
            "path": SUBJECT_PATH,
            "sha256": _sha256(subject_raw),
            "schema_version": "medium-scale-current-source-execution.v1",
        },
        "attestation_artifact": {
            "id": 8002,
            "name": artifact_name + "-attestation",
            "api_digest": _sha256(attestation_raw),
            "workflow_run_id": RUN_ID,
            "workflow_run_attempt": RUN_ATTEMPT,
            "source_sha": SOURCE_SHA,
            "bundle_path": BUNDLE_PATH,
            "bundle_sha256": _sha256(bundle_raw),
        },
        "sigstore_verification": {
            "verified": True,
            "report_sha256": _sha256(report_raw),
            "bundle_sha256": _sha256(bundle_raw),
            "subject_name": "medium-scale-execution.v1.json",
            "subject_sha256": _sha256(subject_raw),
            "repository": "example/structural-analysis",
            "signer_workflow": "example/structural-analysis/.github/workflows/_technical-evidence-attest.yml",
            "signer_digest": SOURCE_SHA,
            "source_digest": SOURCE_SHA,
            "source_ref": "refs/heads/main",
            "deny_self_hosted_runners": True,
        },
    }
    pair_path = tmp_path / "pair.json"
    pair_path.write_bytes(_json_bytes(pair))
    return {
        "pair": pair,
        "pair_path": pair_path,
        "handoff": handoff,
        "attestation": attestation,
        "report": report,
        "report_path": report_path,
        "subject_raw": subject_raw,
        "seal_raw": seal_raw,
        "bundle_raw": bundle_raw,
        "bundle": bundle,
        "statement": statement,
    }


def _verify(fixture: dict[str, object]) -> dict[str, object]:
    return pair_verifier.verify_pair(
        pair_path=fixture["pair_path"],
        handoff_archive_path=fixture["handoff"],
        attestation_archive_path=fixture["attestation"],
        sigstore_report_path=fixture["report_path"],
    )


def _rewrite_pair(fixture: dict[str, object]) -> None:
    fixture["pair_path"].write_bytes(_json_bytes(fixture["pair"]))


def test_schema_and_validator_bind_complete_artifact_pair(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(fixture["pair"])

    result = _verify(fixture)

    assert result == {
        "schema_version": "technical-evidence-handoff-pair.v1",
        "lane": "medium",
        "repository": "example/structural-analysis",
        "source_commit_sha": SOURCE_SHA,
        "source_tree_sha": TREE_SHA,
        "workflow_path": ".github/workflows/medium-scale-current-source.yml",
        "workflow_blob_sha": WORKFLOW_BLOB_SHA,
        "attestor_workflow_path": ".github/workflows/_technical-evidence-attest.yml",
        "attestor_workflow_blob_sha": ATTESTOR_BLOB_SHA,
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
        "handoff_artifact_id": 8001,
        "handoff_artifact_digest": fixture["pair"]["handoff_artifact"]["api_digest"],
        "attestation_artifact_id": 8002,
        "attestation_artifact_digest": fixture["pair"]["attestation_artifact"]["api_digest"],
        "technical_subject_path": SUBJECT_PATH,
        "subject_sha256": fixture["pair"]["technical_subject"]["sha256"],
        "sigstore_report_sha256": fixture["pair"]["sigstore_verification"]["report_sha256"],
        "valid": True,
    }


def test_lane_contract_matches_all_five_producer_callers() -> None:
    for lane, config in pair_verifier.LANES.items():
        source = (ROOT / config["workflow"]).read_text(encoding="utf-8")
        assert f"lane: {lane}" in source
        assert f"receipt-path: {config['subject']}" in source
        assert (
            f'artifact_name="{lane}-technical-handoff-$GITHUB_RUN_ID-'
            '$GITHUB_RUN_ATTEMPT-$SOURCE_SHA"'
        ) in source or (
            lane == "native"
            and 'artifact_name="native-technical-handoff-$GITHUB_RUN_ID-'
            '$GITHUB_RUN_ATTEMPT-$GITHUB_SHA"' in source
        )


@pytest.mark.parametrize(
    "needle,replacement,reason",
    [
        ('"lane": "medium"', '"lane": "medium", "lane": "ifc"', "json_duplicate_key:lane"),
        ('"run_id": 123456', '"run_id": NaN', "json_nonfinite_number:NaN"),
        ('"run_id": 123456', '"run_id": Infinity', "json_nonfinite_number:Infinity"),
        ('"run_id": 123456', '"run_id": 1e9999', "json_nonfinite_number"),
    ],
)
def test_pair_strict_json_rejects_duplicate_and_nonfinite_values(
    tmp_path: Path,
    needle: str,
    replacement: str,
    reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    raw = fixture["pair_path"].read_text(encoding="utf-8")
    fixture["pair_path"].write_text(raw.replace(needle, replacement, 1), encoding="utf-8")
    with pytest.raises(pair_verifier.PairContractError, match=reason):
        _verify(fixture)


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda pair: pair.__setitem__("unknown_claim", True), "pair_keys_invalid"),
        (lambda pair: pair["github_api"].__setitem__("run_id", 9_007_199_254_740_992), "run_id_safe_positive_integer_required"),
        (lambda pair: pair["github_api"].__setitem__("source_tree_sha", "f" * 39), "source_tree_sha_invalid"),
        (lambda pair: pair["github_api"].__setitem__("workflow_path", ".github/workflows/ifc-import-health-current-source.yml"), "workflow_path_lane_mismatch"),
        (lambda pair: pair["handoff_artifact"].__setitem__("id", pair["attestation_artifact"]["id"]), "artifact_id_not_unique"),
        (lambda pair: pair["attestation_artifact"].__setitem__("workflow_run_attempt", RUN_ATTEMPT + 1), "attestation_artifact_run_attempt_mismatch"),
        (lambda pair: pair["attestation_artifact"].__setitem__("bundle_path", "renamed-attestation.json"), "attestation_bundle_path_invalid"),
        (lambda pair: pair["sigstore_verification"].__setitem__("subject_name", "renamed-technical-subject.json"), "sigstore_subject_name_path_mismatch"),
        (lambda pair: pair["sigstore_verification"].__setitem__("source_digest", "a" * 40), "sigstore_source_digest_mismatch"),
        (lambda pair: pair["sigstore_verification"].__setitem__("deny_self_hosted_runners", False), "sigstore_self_hosted_not_denied"),
    ],
)
def test_pair_identity_and_uniqueness_attacks_fail_closed(
    tmp_path: Path,
    mutation,
    reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    mutation(fixture["pair"])
    _rewrite_pair(fixture)
    with pytest.raises(pair_verifier.PairContractError, match=reason):
        _verify(fixture)


def test_handoff_seal_run_identity_cannot_be_rebound(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    seal = json.loads(fixture["seal_raw"])
    seal["run_attempt"] += 1
    seal_raw = _json_bytes(seal)
    handoff_raw = _write_zip(
        fixture["handoff"],
        [(SUBJECT_PATH, fixture["subject_raw"]), ("handoff-seal.json", seal_raw)],
    )
    fixture["pair"]["handoff_artifact"]["api_digest"] = _sha256(handoff_raw)
    fixture["pair"]["handoff_seal"]["sha256"] = _sha256(seal_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError, match="handoff_seal_identity_mismatch"):
        _verify(fixture)


@pytest.mark.parametrize("attack", ["traversal", "symlink", "duplicate", "prefix"])
@pytest.mark.filterwarnings("ignore:Duplicate name")
def test_handoff_zip_path_attacks_fail_closed(tmp_path: Path, attack: str) -> None:
    fixture = _fixture(tmp_path)
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] = [
        (SUBJECT_PATH, fixture["subject_raw"]),
        ("handoff-seal.json", fixture["seal_raw"]),
    ]
    if attack == "traversal":
        entries.append(("../outside.json", b"{}"))
    elif attack == "symlink":
        link = zipfile.ZipInfo("link.json")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        entries.append((link, b"handoff-seal.json"))
    elif attack == "duplicate":
        entries.append((SUBJECT_PATH, fixture["subject_raw"]))
    else:
        entries.extend((("prefix", b"{}"), ("prefix/child.json", b"{}")))
    handoff_raw = _write_zip(fixture["handoff"], entries)
    fixture["pair"]["handoff_artifact"]["api_digest"] = _sha256(handoff_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError):
        _verify(fixture)


def test_archive_input_symlink_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    alias = tmp_path / "handoff-alias.zip"
    alias.symlink_to(fixture["handoff"])
    fixture["handoff"] = alias

    with pytest.raises(pair_verifier.PairContractError, match="handoff_archive_symlink_forbidden"):
        _verify(fixture)


def test_attestation_artifact_and_report_are_byte_bound(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["attestation"].write_bytes(fixture["attestation"].read_bytes() + b"tamper")
    with pytest.raises(pair_verifier.PairContractError, match="attestation_artifact_api_digest_mismatch"):
        _verify(fixture)

    fixture = _fixture(tmp_path / "report-case")
    fixture["report_path"].write_bytes(fixture["report_path"].read_bytes() + b" ")
    with pytest.raises(pair_verifier.PairContractError, match="sigstore_report_digest_mismatch"):
        _verify(fixture)


def test_sigstore_statement_subject_cannot_be_swapped(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    report = deepcopy(fixture["report"])
    report[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = "f" * 64
    report_raw = _json_bytes(report)
    fixture["report_path"].write_bytes(report_raw)
    fixture["pair"]["sigstore_verification"]["report_sha256"] = _sha256(report_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError, match="sigstore_report_statement_mismatch"):
        _verify(fixture)


def test_sigstore_bundle_and_report_statement_field_transplant_fails_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    bundle = deepcopy(fixture["bundle"])
    transplanted_statement = deepcopy(fixture["statement"])
    transplanted_statement["subject"][0]["digest"]["sha256"] = "f" * 64
    bundle["dsseEnvelope"]["payload"] = base64.b64encode(
        _json_bytes(transplanted_statement)
    ).decode("ascii")
    bundle_raw = _json_bytes(bundle)
    attestation_raw = _write_zip(fixture["attestation"], [(BUNDLE_PATH, bundle_raw)])
    fixture["pair"]["attestation_artifact"]["api_digest"] = _sha256(attestation_raw)
    fixture["pair"]["attestation_artifact"]["bundle_sha256"] = _sha256(bundle_raw)
    fixture["pair"]["sigstore_verification"]["bundle_sha256"] = _sha256(bundle_raw)

    report = deepcopy(fixture["report"])
    report[0]["attestation"]["bundle"] = deepcopy(bundle)
    report_raw = _json_bytes(report)
    fixture["report_path"].write_bytes(report_raw)
    fixture["pair"]["sigstore_verification"]["report_sha256"] = _sha256(report_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError, match="sigstore_report_statement_mismatch"):
        _verify(fixture)


def test_coordinated_sigstore_subject_swap_cannot_rebind_technical_subject(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    bundle = deepcopy(fixture["bundle"])
    swapped_statement = deepcopy(fixture["statement"])
    swapped_statement["subject"][0]["digest"]["sha256"] = "f" * 64
    bundle["dsseEnvelope"]["payload"] = base64.b64encode(
        _json_bytes(swapped_statement)
    ).decode("ascii")
    bundle_raw = _json_bytes(bundle)
    attestation_raw = _write_zip(fixture["attestation"], [(BUNDLE_PATH, bundle_raw)])
    fixture["pair"]["attestation_artifact"]["api_digest"] = _sha256(attestation_raw)
    fixture["pair"]["attestation_artifact"]["bundle_sha256"] = _sha256(bundle_raw)
    fixture["pair"]["sigstore_verification"]["bundle_sha256"] = _sha256(bundle_raw)

    report = deepcopy(fixture["report"])
    report[0]["attestation"]["bundle"] = deepcopy(bundle)
    report[0]["verificationResult"]["statement"] = deepcopy(swapped_statement)
    report_raw = _json_bytes(report)
    fixture["report_path"].write_bytes(report_raw)
    fixture["pair"]["sigstore_verification"]["report_sha256"] = _sha256(report_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError, match="sigstore_statement_subject_mismatch"):
        _verify(fixture)


@pytest.mark.parametrize(
    "payload,reason",
    [
        ("%%%not-base64%%%", "sigstore_dsse_payload_base64_invalid"),
        (
            base64.b64encode(
                b'{"_type":"https://in-toto.io/Statement/v1",'
                b'"_type":"https://in-toto.io/Statement/v1"}'
            ).decode("ascii"),
            "json_duplicate_key:_type",
        ),
    ],
)
def test_sigstore_dsse_payload_parser_fails_closed(
    tmp_path: Path,
    payload: str,
    reason: str,
) -> None:
    fixture = _fixture(tmp_path)
    bundle = deepcopy(fixture["bundle"])
    bundle["dsseEnvelope"]["payload"] = payload
    bundle_raw = _json_bytes(bundle)
    attestation_raw = _write_zip(fixture["attestation"], [(BUNDLE_PATH, bundle_raw)])
    fixture["pair"]["attestation_artifact"]["api_digest"] = _sha256(attestation_raw)
    fixture["pair"]["attestation_artifact"]["bundle_sha256"] = _sha256(bundle_raw)
    fixture["pair"]["sigstore_verification"]["bundle_sha256"] = _sha256(bundle_raw)
    _rewrite_pair(fixture)

    with pytest.raises(pair_verifier.PairContractError, match=reason):
        _verify(fixture)
