from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
import yaml

from scripts import build_product_state


ROOT = Path(__file__).resolve().parents[1]
NIGHTLY_PATH = ROOT / ".github/workflows/nightly-full-quality.yml"
PRODUCT_STATE_PATH = ROOT / ".github/workflows/product-state-current.yml"


def _workflow(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(text)
    assert isinstance(payload, dict)
    assert isinstance(payload.get("jobs"), dict)
    return text, payload


def _job_text(text: str, job_id: str, next_job_id: str | None) -> str:
    start = text.index(f"  {job_id}:\n")
    if next_job_id is None:
        return text[start:]
    end = text.index(f"  {next_job_id}:\n", start)
    return text[start:end]


def test_nightly_produces_then_attests_overlay_without_product_state_cycle() -> None:
    text, payload = _workflow(NIGHTLY_PATH)
    jobs = payload["jobs"]
    producer = jobs["build_post_main_overlay"]
    attestor = jobs["attest_post_main_overlay"]

    assert producer["needs"] == "full_quality"
    assert producer["if"] == "${{ always() }}"
    assert producer["permissions"] == {"contents": "read"}
    assert attestor["needs"] == "build_post_main_overlay"
    assert attestor["permissions"] == {
        "actions": "read",
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "artifact-metadata": "write",
    }
    assert "product-state-current.yml" not in text
    assert (
        "post-main-evidence-overlay-candidate-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$GITHUB_SHA"
        in text
    )
    assert (
        "post-main-evidence-overlay-attested-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$GITHUB_SHA"
        in text
    )
    assert '"release_leaf_contract_pass": True' in text
    assert '"violations": []' in text

    attestor_text = _job_text(text, "attest_post_main_overlay", None)
    assert "actions/checkout@" not in attestor_text
    assert "actions/setup-" not in attestor_text
    assert "python scripts/" not in attestor_text
    assert "pip install" not in attestor_text
    assert "duplicate_json_key" in attestor_text
    assert "nonfinite_json_number" in attestor_text
    assert "zip_version_profile_invalid" in attestor_text
    assert "candidate_artifact_api_identity_invalid" in attestor_text
    assert "workflow_blob_identity_invalid" in attestor_text
    assert "external_receipt_promotes_authority" in attestor_text
    assert "external_receipt_runtime_license_promoted" in attestor_text
    assert "external_receipt_replay_invalid" in attestor_text
    assert "external_receipt_claim_boundary_invalid" in attestor_text
    assert "external_schema_identity_invalid" in attestor_text
    assert "external_receipt_schema_shape_invalid" in attestor_text
    assert "external_receipt_promoted:" in attestor_text
    assert "nonpromotion-authority-key-policy.v1.json" in attestor_text
    assert "load_authority_policy" in attestor_text
    assert "canonical_authority_key" in attestor_text
    assert "authority_policy_allow_deny_overlap" in attestor_text
    assert "candidate_artifact_api_inventory_mismatch" in attestor_text
    assert (
        'identity_keys = ("id","name","digest","size_in_bytes",'
        '"archive_download_url","expired","workflow_run")' in attestor_text
    )
    assert "expected_archive_url" in attestor_text
    assert 'unicodedata.category(character) in {"Cc","Cf"}' in attestor_text
    assert "source_commit_response_invalid" in attestor_text
    assert (
        "any(value is not False for value in effective_claims.values())"
        in attestor_text
    )
    assert "key in claims and claims[key] is not False" in attestor_text


def test_product_state_uses_three_job_privilege_split_and_overlay_api_identity() -> (
    None
):
    text, payload = _workflow(PRODUCT_STATE_PATH)
    jobs = payload["jobs"]
    build = jobs["build-current-state"]
    attest = jobs["attest-current-state"]
    verify = jobs["verify-current-state"]

    assert build["permissions"] == {
        "actions": "read",
        "attestations": "read",
        "contents": "read",
    }
    assert attest["needs"] == "build-current-state"
    assert attest["permissions"] == {
        "actions": "read",
        "attestations": "write",
        "contents": "read",
        "id-token": "write",
        "artifact-metadata": "write",
    }
    assert verify["needs"] == "attest-current-state"
    assert verify["permissions"] == {
        "actions": "read",
        "attestations": "read",
        "contents": "read",
    }
    assert "id-token" not in build["permissions"]
    assert "id-token" not in verify["permissions"]

    attest_text = _job_text(text, "attest-current-state", "verify-current-state")
    assert "actions/checkout@" not in attest_text
    assert "actions/setup-" not in attest_text
    assert "python scripts/" not in attest_text
    assert "pip install" not in attest_text
    assert "duplicate_json_key" in attest_text
    assert "nonfinite_json_number" in attest_text
    assert "candidate_artifact_api_identity_invalid" in attest_text
    assert "workflow_blob_identity_invalid" in attest_text
    assert "product_state_authority_invalid" in attest_text
    assert "product_state_claim_boundary_invalid" in attest_text
    assert "external_promotion_contract_invalid" in attest_text
    assert "matrix_authority_claims_invalid" in attest_text
    assert "internal_license_authority_claims_invalid" in attest_text
    assert "promoted_authority:" in attest_text
    assert "nonpromotion-authority-key-policy.v1.json" in attest_text
    assert "load_authority_policy" in attest_text
    assert "canonical_authority_key" in attest_text
    assert "candidate_artifact_api_inventory_mismatch" in attest_text
    assert (
        'identity_keys = ("id","name","digest","size_in_bytes",'
        '"archive_download_url","expired","workflow_run")' in attest_text
    )
    assert "expected_archive_url" in attest_text
    assert "provenance_product_boundary_invalid" in attest_text
    assert "provenance_product_schema_invalid" in attest_text
    assert "external_receipt_schema_identity_invalid" in attest_text
    assert "external_receipt_schema_shape_invalid" in attest_text
    assert "external_receipt_replay_invalid" in attest_text
    assert "candidate_claim_boundary_invalid" in attest_text
    assert 'commit.get("sha") != source_sha' in attest_text
    assert 'unicodedata.normalize("NFC", name) != name' in attest_text
    assert "provenance_overlay_boundary_invalid" in attest_text
    assert 'overlay.get("producer", {}).get("run_id") != nightly_run_id' in attest_text
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/nightly-full-quality.yml"'
        in attest_text
    )
    assert "post-main-overlay-privileged-attestation-verification.json" in attest_text
    assert '"repos/$GITHUB_REPOSITORY/actions/runs/$NIGHTLY_RUN_ID"' in attest_text
    assert "nightly_run_rest_identity_invalid" in attest_text
    assert "nightly_product_provenance_rest_mismatch" in attest_text
    assert "nightly_nested_overlay_artifact_member_set_invalid" in attest_text
    assert "nightly-overlay-attested-api.json" in attest_text
    assert "nightly-overlay-candidate-api.json" in attest_text

    build_text = _job_text(text, "build-current-state", "attest-current-state")
    assert "post-main-evidence-overlay-attested-" in build_text
    assert 'row.get("digest")' in build_text
    assert 'row.get("workflow_run", {}).get("id")' in build_text
    assert 'run.get("run_attempt") == run_attempt' in build_text
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/nightly-full-quality.yml"'
        in build_text
    )
    assert "--deny-self-hosted-runners" in build_text
    assert "scripts/build_post_main_evidence_overlay.py materialize" in build_text
    assert '--post-main-overlay-manifest "$POST_MAIN_OVERLAY_SEAL"' in build_text
    assert 'unicodedata.category(character) in {"Cc", "Cf"}' in build_text
    assert "attested overlay list/direct API identity mismatch" in build_text
    assert "overlay candidate stored/list/direct API identity mismatch" in build_text
    assert "overlay candidate raw ZIP identity invalid" in build_text

    verify_text = _job_text(text, "verify-current-state", None)
    assert "Verify all exact-source attestations" in verify_text
    assert "post-main-overlay-final-attestation-verification.json" in verify_text
    assert (
        '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/nightly-full-quality.yml"'
        in verify_text
    )
    assert 'api.get("workflow_run", {}).get("id")' in verify_text
    assert "signed artifact member set invalid" in verify_text
    assert "not 0 < member.file_size" in attest_text
    assert "not 0 < member.file_size" in verify_text
    assert 'unicodedata.category(character) in {"Cc","Cf"}' in attest_text
    assert 'unicodedata.category(character) in {"Cc","Cf"}' in verify_text
    assert 'len(raw_archive) != api["size_in_bytes"]' in attest_text
    assert 'len(raw_archive) != api["size_in_bytes"]' in verify_text
    assert "signed candidate seal row keys invalid" in verify_text
    assert "signed candidate seal row bytes invalid" in verify_text
    assert (
        'gh attestation verify "$root/product-state-candidate.seal.json"' in verify_text
    )
    assert "candidate_seal_attestation_invocation_invalid" in verify_text
    assert "candidate_seal_attestation_subject_invalid" in verify_text
    assert "final_nightly_rest_identity_invalid" in verify_text
    assert "final_nightly_product_provenance_mismatch" in verify_text
    assert "final_artifact_raw_zip_identity_invalid" in verify_text
    assert "product-state-final-artifact-verification.v1" in verify_text
    assert "final_artifact_uploaded_bytes_mismatch" in verify_text
    assert "final_signed_artifact_member_set_not_sealed" in verify_text
    assert "final_artifact_unapproved_member_set" in verify_text
    assert "final_artifact_replaced_signed_member" in verify_text
    assert "Refresh exact-source attestations immediately before final publication" in verify_text
    assert "Cryptographically replay final artifact attestations without repository code" in verify_text
    assert 'actions/runs/$NIGHTLY_RUN_ID' in verify_text
    assert 'actions/artifacts/$SIGNED_ID/zip' in verify_text
    assert verify_text.count("gh attestation verify") >= 8
    for binding in (
        'cmp --silent "$verify_root/product-state.replay.json" "$verify_root/product-state.embedded.json"',
        'cmp --silent "$verify_root/provenance.replay.json" "$verify_root/provenance.embedded.json"',
        'cmp --silent "$verify_root/overlay.replay.json" "$verify_root/overlay-final.embedded.json"',
        'cmp --silent "$verify_root/overlay.replay.json" "$verify_root/overlay-privileged.embedded.json"',
    ):
        assert binding in verify_text
    assert "Confirm refs/heads/main immediately before final publication" in verify_text
    assert "final-main-pre-publish.json" in verify_text
    assert "final-main-post-publish.json" in verify_text
    assert verify_text.index("Replay exact-source overlay, full DAG, and provenance") < verify_text.index(
        "Refresh exact-source attestations immediately before final publication"
    )
    assert verify_text.index(
        "Confirm refs/heads/main immediately before final publication"
    ) < verify_text.index("Upload verified current and historical Product State artifact")
    assert 'unicodedata.normalize("NFKC", name) != name' in verify_text
    assert '"clock$", "conin$", "conout$"' in verify_text
    seal_attestation = next(
        step for step in attest["steps"] if step.get("id") == "attest_candidate_seal"
    )
    assert seal_attestation["with"]["subject-path"] == (
        "${{ runner.temp }}/verified-product-state-candidate/"
        "product-state-candidate.seal.json"
    )


def test_product_state_inline_python_heredocs_compile() -> None:
    for path in (NIGHTLY_PATH, PRODUCT_STATE_PATH):
        _, payload = _workflow(path)
        compiled = 0
        for job in payload["jobs"].values():
            for step in job.get("steps", []):
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                lines = run.splitlines()
                index = 0
                while index < len(lines):
                    if lines[index].rstrip().endswith("<<'PY'"):
                        end = lines.index("PY", index + 1)
                        source = "\n".join(lines[index + 1 : end]) + "\n"
                        compile(source, f"{path}:{index + 1}", "exec")
                        compiled += 1
                        index = end
                    index += 1
        assert compiled > 0


def _attestor_python(path: Path, job_id: str) -> str:
    _, payload = _workflow(path)
    step = next(
        row
        for row in payload["jobs"][job_id]["steps"]
        if isinstance(row.get("run"), str) and "def load_authority_policy" in row["run"]
    )
    lines = step["run"].splitlines()
    start = next(
        index for index, line in enumerate(lines) if line.rstrip().endswith("<<'PY'")
    )
    end = lines.index("PY", start + 1)
    return "\n".join(lines[start + 1 : end]) + "\n"


@pytest.mark.parametrize(
    ("path", "job_id"),
    [
        (NIGHTLY_PATH, "attest_post_main_overlay"),
        (PRODUCT_STATE_PATH, "attest-current-state"),
    ],
)
def test_oidc_attestors_execute_production_authority_policy_fail_closed(
    path: Path,
    job_id: str,
) -> None:
    source = _attestor_python(path, job_id)
    tree = ast.parse(source)
    function_names = {
        "fail",
        "unique",
        "constant",
        "reject",
        "finite",
        "load",
        "load_authority_policy",
        "canonical_authority_key",
        "compact_authority_key",
        "nonpromoting",
        "reject_promoted_authority",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        or (isinstance(node, ast.FunctionDef) and node.name in function_names)
    ]
    namespace: dict[str, object] = {}
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), str(path), "exec"),
        namespace,
    )
    policy_raw = (
        ROOT / "canonical/nonpromotion-authority-key-policy.v1.json"
    ).read_bytes()
    namespace["authority_policy"] = namespace["load_authority_policy"](policy_raw)
    reject_authority = namespace["reject_promoted_authority"]

    for payload in (
        {"RELEASE_AUTHORITY": True},
        {"ＲＥＬＥＡＳＥ_authority": True},
        {"releаse_authority": True},
        {"release_authority\u200b": True},
        {"release_authority\n": True},
        {"releaseAuthority": True},
        {"releaseAUTHORity": True},
        {"releaseAUTHORity": False},
        {"release-authority": True},
        {"re-lease-authority": True},
        {"re-lease-authority": False},
        {"release_authority_confirmed": True},
        {"is_release_authority": True},
        {"paid_pilot_ready_flag": True},
        {"independent_verification_level_2_status": True},
        {"paid_pilot": True},
        {"paid_pilot_ready": True},
        {"release_ready": True},
        {"release_permitted": True},
        {"go_live": True},
        {"scientific_validation": True},
        {"scientific_decision_pass": True},
        {"commercially_ready": True},
        {"redistributable": True},
        {"production_ready": True},
        {"general_availability": True},
        {"level2_eligible": True},
        {"operator_identity_credentials_verified": True},
        {"certified_for_design": True},
        {"commercial": True},
        {"independent": True},
        {"legal": True},
        {"nested": [{"commercialAUTHORity": True}]},
        {"nested": [{"legal-authority": True}]},
        {"nested": [{"Independent_Operator_Attested": True}]},
        {"evidence": ["releaseAuthority"]},
        {"evidence": ["RELEASE-AUTHORITY"]},
        {"evidence": ["releаse_authority"]},
        {"evidence": ["indepen-dent-verification-level-2"]},
        {"evidence": ["paid-pilot"]},
        {"evidence": ["release_authority_confirmed"]},
        {"grants": ["release_authority"]},
        {"grants": ["unreviewed_technical_authority"]},
        {"grants": "bounded_developer_preview_technical_claims"},
        {"grants": [{"bounded_developer_preview_technical_claims": True}]},
        {"does_not_grant": ["ReleaseAuthority"]},
        {"does-not-grant": ["indepen-dent-verification-level-2"]},
        {"does_not_grant": ["release_authority_confirmed"]},
        {"does_not_grant": "release_authority"},
        {"does_not_grant": [{"release_authority": False}]},
        {"release_authority": {"status": "unavailable", "value": True}},
        {"claims": {"unregistered_claim": True}},
        {"stored_claims": {"future_technical_claim": True}},
    ):
        with pytest.raises(SystemExit):
            reject_authority(payload)

    reject_authority(
        {
            "release_authority": {"status": "unavailable"},
            "grants": ["bounded_developer_preview_technical_claims"],
            "does_not_grant": [
                "release_authority",
                "product_legal_license_approval",
                "independent_verification_level_2",
            ],
            "claims": {
                "actual_external_solver_execution": True,
                "internal_due_diligence_complete": True,
                "license_inventory_complete": True,
                "spdx_notices_complete": True,
                "redistribution_boundaries_explicit": True,
                "source_use_declarations_complete": True,
                "release_authority": False,
            },
            "blockers_remaining": ["release_authority_confirmed_missing"],
        }
    )
    current, _ = build_product_state.build_product_state(ROOT)
    reject_authority(current)
    populated = deepcopy(current)
    bounded = populated["bounded_planar_external_vv"]
    bounded.update(
        sha256="sha256:" + "a" * 64,
        stored_status="blocked",
        stored_contract_pass=True,
        summary={"requirement_count": 25, "promotion_eligible_count": 0},
        stored_summary={"requirement_count": 25, "promotion_eligible_count": 0},
        execution_package_binding={"external_solver_execution": False, "status": "unavailable"},
        same_operator_execution_binding={"actual_external_solver_execution": False, "operator_independence_declared": False},
        operator_intake_binding={"operator_identity_credentials_verified": False, "status": "unavailable"},
    )
    reject_authority(populated)


def test_overlay_contract_names_all_current_technical_handoff_lanes() -> None:
    text = (ROOT / "scripts/build_post_main_evidence_overlay.py").read_text(
        encoding="utf-8"
    )
    for lane, workflow in {
        "medium": "medium-scale-current-source.yml",
        "ifc": "ifc-import-health-current-source.yml",
        "mgt9": "mgt-import-health-current-source.yml",
        "mgt10": "mgt-import-health-tenth-source.yml",
        "native": "native-frame-alpha-clean-install.yml",
    }.items():
        assert f'"{lane}"' in text
        assert workflow in text
    assert "technical_only" in text
    assert '"promotion_eligible": False' in text


def test_final_attestation_authority_is_isolated_from_repository_code() -> None:
    text, workflow = _workflow(PRODUCT_STATE_PATH)
    job = workflow["jobs"]["replay-final-attestations"]
    assert job["needs"] == "verify-current-state"
    replay = _job_text(text, "replay-final-attestations", None)
    assert "actions/checkout" not in replay
    assert "setup-python" not in replay
    assert "pip install" not in replay
    assert replay.count("/usr/bin/gh attestation verify") == 3
    assert 'test ! -e "$GITHUB_WORKSPACE/.git"' in replay
    assert replay.count("/usr/bin/cmp --silent") == 4


def test_github_zip64_writer_profile_remains_accepted(tmp_path: Path) -> None:
    archive_path = tmp_path / "github-artifact.zip"
    member = zipfile.ZipInfo("post-main-evidence-overlay.seal.json")
    member.create_system = 3
    member.create_version = 45
    member.extract_version = 20
    member.external_attr = (0o100644 & 0xFFFF) << 16
    member.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(member, b"{}\n")
    with zipfile.ZipFile(archive_path) as archive:
        observed = archive.infolist()[0]
    assert observed.create_system == 3
    assert observed.create_version == 45
    assert observed.extract_version == 20

    for workflow_path in (NIGHTLY_PATH, PRODUCT_STATE_PATH):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "member.create_version not in {20, 45}" in workflow
        assert "member.extract_version != 20" in workflow


def _step_python(job_id: str, step_name: str, marker: str) -> str:
    _, payload = _workflow(PRODUCT_STATE_PATH)
    step = next(
        row for row in payload["jobs"][job_id]["steps"] if row.get("name") == step_name
    )
    lines = step["run"].splitlines()
    start = next(
        index
        for index, line in enumerate(lines)
        if marker in line and line.rstrip().endswith("<<'PY'")
    )
    end = lines.index("PY", start + 1)
    return "\n".join(lines[start + 1 : end]) + "\n"


def _artifact_zip(files: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, raw in sorted(files.items()):
            member = zipfile.ZipInfo(name)
            member.create_system = 3
            member.create_version = 45
            member.extract_version = 20
            member.external_attr = (0o100644 & 0xFFFF) << 16
            member.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(member, raw)
    return stream.getvalue()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def test_final_signed_verifier_rejects_forged_sealed_member(tmp_path: Path) -> None:
    source = _step_python(
        "verify-current-state",
        "Download signed artifact by immutable API identity",
        "SIGNED_ROOT=",
    )
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    tree_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True
    ).strip()
    workflow_blob = subprocess.check_output(
        ["git", "rev-parse", "HEAD:.github/workflows/product-state-current.yml"],
        cwd=ROOT,
        text=True,
    ).strip()
    sealed_path = "sealed.json"
    original = b'{"trusted":true}\n'
    forged = b'{"forged":true}\n'
    boundary = (
        "OIDC handoff candidate only; attestation does not grant release, legal, "
        "design, commercial, or independent-verification authority."
    )
    seal = {
        "schema_version": "product-state-candidate-seal.v1",
        "repository": "example/repo",
        "source_commit_sha": source_sha,
        "source_tree_sha": tree_sha,
        "source_ref": "refs/heads/main",
        "workflow_path": ".github/workflows/product-state-current.yml",
        "workflow_blob_sha": workflow_blob,
        "workflow_run_id": 701,
        "workflow_run_number": 41,
        "workflow_run_attempt": 1,
        "files": [
            {
                "path": sealed_path,
                "bytes": len(original),
                "sha256": _sha256(original),
            }
        ],
        "release_authority": False,
        "claim_boundary": boundary,
    }
    files = {
        "product-state-candidate.seal.json": (
            json.dumps(seal, indent=2, sort_keys=True) + "\n"
        ).encode(),
        sealed_path: forged,
        "candidate-artifact-api.json": b"{}\n",
        ".ci/product-state-inputs/post-main-overlay-privileged-attestation-verification.json": b"{}\n",
        ".ci/product-state-inputs/product-state.current.sigstore.json": b"{}\n",
        ".ci/product-state-inputs/product-state.provenance-bundle.sigstore.json": b"{}\n",
    }
    archive = _artifact_zip(files)
    signed_id = "801"
    signed_name = f"product-state-signed-701-1-{source_sha}"
    _write_json(
        tmp_path / "signed-api.json",
        {
            "id": int(signed_id),
            "name": signed_name,
            "digest": _sha256(archive),
            "size_in_bytes": len(archive),
            "archive_download_url": (
                f"https://api.github.test/repos/example/repo/actions/artifacts/{signed_id}/zip"
            ),
            "expired": False,
            "workflow_run": {"id": 701},
        },
    )
    (tmp_path / "signed.zip").write_bytes(archive)
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "SIGNED_ROOT": str(tmp_path / "extracted"),
        "GITHUB_API_URL": "https://api.github.test",
        "GITHUB_REPOSITORY": "example/repo",
        "SIGNED_ID": signed_id,
        "SIGNED_NAME": signed_name,
        "SIGNED_DIGEST": _sha256(archive),
        "GITHUB_RUN_ID": "701",
        "GITHUB_RUN_NUMBER": "41",
        "GITHUB_RUN_ATTEMPT": "1",
        "PRODUCT_STATE_SHA": source_sha,
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "signed candidate seal row bytes invalid" in completed.stderr
    files[sealed_path] = original
    archive = _artifact_zip(files)
    api = json.loads((tmp_path / "signed-api.json").read_text())
    api["digest"] = _sha256(archive)
    api["size_in_bytes"] = len(archive)
    _write_json(tmp_path / "signed-api.json", api)
    (tmp_path / "signed.zip").write_bytes(archive)
    env["SIGNED_ROOT"] = str(tmp_path / "extracted-valid")
    env["SIGNED_DIGEST"] = _sha256(archive)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        (lambda stored, direct: None, None),
        (lambda stored, direct: stored.update(size_in_bytes=1), "mismatch"),
        (
            lambda stored, direct: stored.update(
                archive_download_url="https://attacker.invalid/archive.zip"
            ),
            "mismatch",
        ),
        (lambda stored, direct: direct.update(size_in_bytes=1), "mismatch"),
    ],
)
def test_build_overlay_candidate_direct_rest_and_raw_zip_binding(
    tmp_path: Path, mutation, failure: str | None
) -> None:
    source = _step_python(
        "build-current-state",
        "Consume authenticated exact-Nightly post-main overlay by API identity",
        "OVERLAY_CANDIDATE_ID=",
    )
    repository = "example/repo"
    source_sha = "a" * 40
    run_id = 501
    run_attempt = 1
    artifact_id = 601
    name = f"post-main-evidence-overlay-candidate-{run_id}-{run_attempt}-{source_sha}"
    root = tmp_path / "overlay"
    root.mkdir()
    seal = {"release_files": [], "external_vv_nonpromotion": {"receipts": []}}
    seal_raw = (json.dumps(seal, indent=2, sort_keys=True) + "\n").encode()
    (root / "post-main-evidence-overlay.seal.json").write_bytes(seal_raw)
    archive = _artifact_zip({"post-main-evidence-overlay.seal.json": seal_raw})
    api = {
        "id": artifact_id,
        "name": name,
        "digest": _sha256(archive),
        "size_in_bytes": len(archive),
        "archive_download_url": (
            f"https://api.github.test/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        ),
        "expired": False,
        "workflow_run": {"id": run_id},
    }
    stored = deepcopy(api)
    direct = deepcopy(api)
    mutation(stored, direct)
    _write_json(root / "candidate-artifact-api.json", stored)
    _write_json(
        tmp_path / ".ci/product-state-inputs/nightly-overlay-artifacts.json",
        {"artifacts": [api], "total_count": 1},
    )
    _write_json(tmp_path / "post-main-overlay-candidate-api.json", direct)
    (tmp_path / "post-main-overlay-candidate.zip").write_bytes(archive)
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "POST_MAIN_OVERLAY_ROOT": str(root),
        "NIGHTLY_RUN_ID": str(run_id),
        "NIGHTLY_RUN_ATTEMPT": str(run_attempt),
        "PRODUCT_STATE_SHA": source_sha,
        "GITHUB_API_URL": "https://api.github.test",
        "GITHUB_REPOSITORY": repository,
        "OVERLAY_CANDIDATE_ID": str(artifact_id),
        "OVERLAY_CANDIDATE_DIGEST": _sha256(archive),
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if failure is None:
        assert completed.returncode == 0, completed.stderr
    else:
        assert completed.returncode != 0
        assert (
            "overlay candidate stored/list/direct API identity mismatch"
            in completed.stderr
            or "overlay candidate direct API identity invalid" in completed.stderr
        )


def _final_nightly_fixture(root: Path, temp: Path) -> tuple[dict, dict[str, str]]:
    nightly = {
        "id": 501,
        "run_number": 71,
        "run_attempt": 1,
        "name": "Nightly Full Quality",
        "path": ".github/workflows/nightly-full-quality.yml",
        "event": "schedule",
        "conclusion": "success",
        "status": "completed",
        "head_branch": "main",
        "head_sha": "a" * 40,
    }
    _write_json(temp / "final-nightly-run.json", nightly)
    _write_json(
        root / ".ci/product-state-inputs/nightly-workflow-run-event.json",
        {"workflow_run": nightly},
    )
    _write_json(root / ".ci/product-state-inputs/nightly-overlay-run.json", nightly)
    evidence = {
        "status": "available",
        "authority": "github_actions_workflow_run_event",
        "workflow_name": nightly["name"],
        "run_id": nightly["id"],
        "run_number": nightly["run_number"],
        "run_attempt": nightly["run_attempt"],
        "trigger_event": nightly["event"],
        "conclusion": nightly["conclusion"],
        "head_branch": nightly["head_branch"],
        "head_sha": nightly["head_sha"],
    }
    provenance_run = {
        **evidence,
        "workflow_path": nightly["path"],
    }
    provenance_run.pop("status")
    _write_json(
        root / "artifacts/manifests/product_state.current.v1.json",
        {"quality_evidence": evidence},
    )
    _write_json(
        root / ".ci/product-state-inputs/product-state.provenance-bundle.v1.json",
        {"workflow_runs": {"nightly_full_quality": provenance_run}},
    )
    _write_json(
        root
        / ".ci/product-state-inputs/post-main-overlay/post-main-evidence-overlay.seal.json",
        {
            "source": {"commit_sha": nightly["head_sha"]},
            "producer": {
                "workflow_name": nightly["name"],
                "workflow_path": nightly["path"],
                "event": nightly["event"],
                "run_id": nightly["id"],
                "run_attempt": nightly["run_attempt"],
            },
        },
    )
    env = {
        **os.environ,
        "ROOT": str(root),
        "RUNNER_TEMP": str(temp),
        "NIGHTLY_RUN_ID": str(nightly["id"]),
        "NIGHTLY_RUN_NUMBER": str(nightly["run_number"]),
        "NIGHTLY_RUN_ATTEMPT": str(nightly["run_attempt"]),
        "PRODUCT_STATE_CONCLUSION": nightly["conclusion"],
        "PRODUCT_STATE_SHA": nightly["head_sha"],
    }
    return nightly, env


@pytest.mark.parametrize(
    ("relative_path", "mutate"),
    [
        (
            ".ci/product-state-inputs/nightly-workflow-run-event.json",
            lambda value: value["workflow_run"].update(conclusion="failure"),
        ),
        (
            "artifacts/manifests/product_state.current.v1.json",
            lambda value: value["quality_evidence"].update(run_attempt=2),
        ),
        (
            ".ci/product-state-inputs/product-state.provenance-bundle.v1.json",
            lambda value: value["workflow_runs"]["nightly_full_quality"].update(
                run_number=999
            ),
        ),
        (
            ".ci/product-state-inputs/post-main-overlay/post-main-evidence-overlay.seal.json",
            lambda value: value["producer"].update(run_id=999),
        ),
    ],
)
def test_final_nightly_rest_binding_rejects_candidate_replay(
    tmp_path: Path, relative_path: str, mutate
) -> None:
    source = _step_python(
        "verify-current-state",
        "Independently bind final replay to the live Nightly run",
        "ROOT=",
    )
    root = tmp_path / "root"
    root.mkdir()
    _, env = _final_nightly_fixture(root, tmp_path)
    target = root / relative_path
    payload = json.loads(target.read_text())
    mutate(payload)
    _write_json(target, payload)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "final_nightly_" in completed.stderr


def test_final_nightly_rest_binding_accepts_exact_live_identity(tmp_path: Path) -> None:
    source = _step_python(
        "verify-current-state",
        "Independently bind final replay to the live Nightly run",
        "ROOT=",
    )
    root = tmp_path / "root"
    root.mkdir()
    _, env = _final_nightly_fixture(root, tmp_path)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def _attestation_report(subject_name: str, subject_raw: bytes) -> bytes:
    payload = [
        {
            "verificationResult": {
                "signature": {"certificate": {"verified": True}},
                "verifiedTimestamps": [{"verified": True}],
                "statement": {
                    "_type": "https://in-toto.io/Statement/v1",
                    "subject": [
                        {
                            "name": subject_name,
                            "digest": {
                                "sha256": hashlib.sha256(subject_raw).hexdigest()
                            },
                        }
                    ],
                    "predicateType": "https://slsa.dev/provenance/v1",
                    "predicate": {},
                },
            }
        }
    ]
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()


def _write_final_artifact_fixture(
    tmp_path: Path,
    env: dict[str, str],
    signed_files: dict[str, bytes],
    final_files: dict[str, bytes],
) -> None:
    root = Path(env["FINAL_ROOT"])
    for name, raw in final_files.items():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    signed_archive = _artifact_zip(signed_files)
    (tmp_path / "signed.zip").write_bytes(signed_archive)
    env["SIGNED_DIGEST"] = _sha256(signed_archive)
    signed_api = {
        "id": int(env["SIGNED_ID"]),
        "name": env["SIGNED_NAME"],
        "digest": env["SIGNED_DIGEST"],
        "size_in_bytes": len(signed_archive),
        "archive_download_url": (
            f"{env['GITHUB_API_URL']}/repos/{env['GITHUB_REPOSITORY']}"
            f"/actions/artifacts/{env['SIGNED_ID']}/zip"
        ),
        "expired": False,
        "workflow_run": {
            "id": int(env["GITHUB_RUN_ID"]),
            "head_branch": "main",
            "head_sha": env["PRODUCT_STATE_SHA"],
        },
    }
    _write_json(tmp_path / "signed-api.json", signed_api)
    final_archive = _artifact_zip(final_files)
    (tmp_path / "final-artifact.zip").write_bytes(final_archive)
    env["FINAL_DIGEST"] = _sha256(final_archive)
    final_api = {
        "id": int(env["FINAL_ID"]),
        "name": env["FINAL_NAME"],
        "digest": env["FINAL_DIGEST"],
        "size_in_bytes": len(final_archive),
        "archive_download_url": (
            f"{env['GITHUB_API_URL']}/repos/{env['GITHUB_REPOSITORY']}"
            f"/actions/artifacts/{env['FINAL_ID']}/zip"
        ),
        "expired": False,
        "workflow_run": {
            "id": int(env["GITHUB_RUN_ID"]),
            "head_branch": "main",
            "head_sha": env["PRODUCT_STATE_SHA"],
        },
    }
    _write_json(
        tmp_path / "final-artifacts.json",
        {"artifacts": [final_api], "total_count": 1},
    )
    _write_json(tmp_path / "final-artifact-api.json", final_api)


def _final_artifact_fixture(
    tmp_path: Path,
) -> tuple[str, dict[str, str], dict[str, bytes], dict[str, bytes]]:
    source = _step_python(
        "verify-current-state",
        "Re-fetch and seal the published final artifact by REST identity",
        "FINAL_ROOT=",
    )
    root = tmp_path / "final-root"
    root.mkdir()
    source_sha = "a" * 40
    final_id = 901
    run_id = 701
    run_number = 41
    run_attempt = 1
    nightly = {
        "id": 501, "run_number": 71, "run_attempt": 1,
        "name": "Nightly Full Quality", "path": ".github/workflows/nightly-full-quality.yml",
        "event": "schedule", "conclusion": "success", "status": "completed",
        "head_branch": "main", "head_sha": source_sha,
    }
    nightly_raw = (json.dumps(nightly, indent=2, sort_keys=True) + "\n").encode()
    sealed_files = {
        "artifacts/manifests/product_state.current.v1.json": b'{"release_authority":false}\n',
        ".ci/product-state-inputs/product-state.provenance-bundle.v1.json": b'{"release_authority":false}\n',
        ".ci/product-state-inputs/post-main-overlay/post-main-evidence-overlay.seal.json": b'{"release_authority":false}\n',
        ".ci/product-state-inputs/nightly-workflow-run-event.json": (json.dumps({"workflow_run": nightly}, indent=2, sort_keys=True) + "\n").encode(),
        ".ci/product-state-inputs/nightly-overlay-run.json": nightly_raw,
    }
    seal = {
        "schema_version": "product-state-candidate-seal.v1",
        "repository": "example/repo",
        "source_commit_sha": source_sha,
        "source_tree_sha": "b" * 40,
        "source_ref": "refs/heads/main",
        "workflow_path": ".github/workflows/product-state-current.yml",
        "workflow_blob_sha": "c" * 40,
        "workflow_run_id": run_id,
        "workflow_run_number": run_number,
        "workflow_run_attempt": run_attempt,
        "files": [
            {"path": name, "bytes": len(raw), "sha256": _sha256(raw)}
            for name, raw in sorted(sealed_files.items())
        ],
        "release_authority": False,
        "claim_boundary": (
            "OIDC handoff candidate only; attestation does not grant release, legal, "
            "design, commercial, or independent-verification authority."
        ),
    }
    seal_raw = (json.dumps(seal, indent=2, sort_keys=True) + "\n").encode()
    signed_files = {
        **sealed_files,
        "product-state-candidate.seal.json": seal_raw,
        "candidate-artifact-api.json": b"{}\n",
        ".ci/product-state-inputs/post-main-overlay-privileged-attestation-verification.json": b"{}\n",
        ".ci/product-state-inputs/product-state.current.sigstore.json": b"{}\n",
        ".ci/product-state-inputs/product-state.provenance-bundle.sigstore.json": b"{}\n",
    }
    final_files = {
        **signed_files,
        ".ci/product-state-inputs/product-state.current.attestation-verification.json": _attestation_report(
            "product_state.current.v1.json",
            sealed_files["artifacts/manifests/product_state.current.v1.json"],
        ),
        ".ci/product-state-inputs/product-state.provenance-bundle.attestation-verification.json": _attestation_report(
            "product-state.provenance-bundle.v1.json",
            sealed_files[
                ".ci/product-state-inputs/product-state.provenance-bundle.v1.json"
            ],
        ),
        ".ci/product-state-inputs/post-main-overlay-final-attestation-verification.json": _attestation_report(
            "post-main-evidence-overlay.seal.json",
            sealed_files[
                ".ci/product-state-inputs/post-main-overlay/post-main-evidence-overlay.seal.json"
            ],
        ),
    }
    _write_json(tmp_path / "final-nightly-run.json", nightly)
    env = {
        **os.environ,
        "RUNNER_TEMP": str(tmp_path),
        "FINAL_ROOT": str(root),
        "FINAL_ID": str(final_id),
        "FINAL_NAME": f"product-state-current-success-{source_sha}",
        "SIGNED_ID": "801",
        "SIGNED_NAME": f"product-state-signed-{run_id}-{run_attempt}-{source_sha}",
        "GITHUB_API_URL": "https://api.github.test",
        "GITHUB_REPOSITORY": "example/repo",
        "GITHUB_RUN_ID": str(run_id),
        "GITHUB_RUN_NUMBER": str(run_number),
        "GITHUB_RUN_ATTEMPT": str(run_attempt),
        "PRODUCT_STATE_SHA": source_sha,
        "PRODUCT_STATE_CONCLUSION": "success",
        "NIGHTLY_RUN_ID": "501",
    }
    main_ref = {
        "ref": "refs/heads/main",
        "object": {"type": "commit", "sha": source_sha},
    }
    _write_json(tmp_path / "final-main-pre-publish.json", main_ref)
    _write_json(tmp_path / "final-main-post-publish.json", main_ref)
    (
        tmp_path / "product-state-candidate.seal.attestation-verification.json"
    ).write_bytes(_attestation_report("product-state-candidate.seal.json", seal_raw))
    _write_final_artifact_fixture(tmp_path, env, signed_files, final_files)
    return source, env, signed_files, final_files


def test_published_final_artifact_rest_report_binds_raw_zip_and_disk_bytes(
    tmp_path: Path,
) -> None:
    source, env, _, final_files = _final_artifact_fixture(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(
        (tmp_path / "product-state-final-artifact-verification.v1.json").read_text()
    )
    assert report["raw_zip_sha256"] == env["FINAL_DIGEST"]
    assert report["candidate_seal_sha256"] == _sha256(
        final_files["product-state-candidate.seal.json"]
    )
    assert report["main_ref_before_publish"] == env["PRODUCT_STATE_SHA"]
    assert report["main_ref_after_publish"] == env["PRODUCT_STATE_SHA"]
    assert report["technical_integrity_pass"] is True
    assert report["release_authority"] is False

    forged_api = json.loads((tmp_path / "final-artifact-api.json").read_text())
    forged_api["archive_download_url"] = "https://attacker.invalid/final.zip"
    _write_json(
        tmp_path / "final-artifacts.json",
        {"artifacts": [forged_api], "total_count": 1},
    )
    _write_json(tmp_path / "final-artifact-api.json", forged_api)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "final_artifact_api_identity_invalid" in completed.stderr

    forged_archive = _artifact_zip(
        {"product-state-candidate.seal.json": b'{"forged":true}\n'}
    )
    forged_api = json.loads((tmp_path / "final-artifact-api.json").read_text())
    forged_api["archive_download_url"] = (
        f"{env['GITHUB_API_URL']}/repos/{env['GITHUB_REPOSITORY']}"
        f"/actions/artifacts/{env['FINAL_ID']}/zip"
    )
    forged_api["digest"] = _sha256(forged_archive)
    forged_api["size_in_bytes"] = len(forged_archive)
    _write_json(
        tmp_path / "final-artifacts.json",
        {"artifacts": [forged_api], "total_count": 1},
    )
    _write_json(tmp_path / "final-artifact-api.json", forged_api)
    (tmp_path / "final-artifact.zip").write_bytes(forged_archive)
    env["FINAL_DIGEST"] = _sha256(forged_archive)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "final_artifact_uploaded_bytes_mismatch" in completed.stderr


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        ("sealed_replacement", "final_candidate_seal_row_bytes_invalid"),
        ("candidate_seal_replacement", "final_candidate_seal_signed_bytes_mismatch"),
        ("signed_extra", "final_signed_artifact_member_set_not_sealed"),
        ("final_extra", "final_artifact_unapproved_member_set"),
        ("attestation_replacement", "final_product_attestation_subject_invalid"),
    ],
)
def test_final_artifact_rejects_unsealed_replacement_and_extra_members(
    tmp_path: Path, mutation: str, failure: str
) -> None:
    source, env, signed_files, final_files = _final_artifact_fixture(tmp_path)
    if mutation == "sealed_replacement":
        final_files["artifacts/manifests/product_state.current.v1.json"] = (
            b'{"forged":true}\n'
        )
    elif mutation == "candidate_seal_replacement":
        final_files["product-state-candidate.seal.json"] = b'{"forged":true}\n'
    elif mutation == "signed_extra":
        signed_files["unexpected-signed.json"] = b"{}\n"
        final_files["unexpected-signed.json"] = b"{}\n"
    elif mutation == "final_extra":
        final_files["unexpected-final.json"] = b"{}\n"
    elif mutation == "attestation_replacement":
        final_files[
            ".ci/product-state-inputs/product-state.current.attestation-verification.json"
        ] = _attestation_report("forged.json", b'{"forged":true}\n')
    else:  # pragma: no cover - parameter contract
        raise AssertionError(mutation)
    _write_final_artifact_fixture(tmp_path, env, signed_files, final_files)

    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert failure in completed.stderr


@pytest.mark.parametrize(
    "unsafe_name",
    [
        "AUX.txt",
        "nested/COM1.log",
        "nested/CONOUT$.txt",
        "nested/trailing.",
        "nested/trailing ",
        "nested/less<than.json",
        "nested/greater>than.json",
        'nested/double\"quote.json',
        "nested/pipe|name.json",
        "nested/question?.json",
        "nested/star*.json",
        "ＦＯＯ.json",
    ],
)
def test_final_artifact_rejects_cross_platform_confusable_paths(
    tmp_path: Path, unsafe_name: str
) -> None:
    source, env, signed_files, final_files = _final_artifact_fixture(tmp_path)
    final_files[unsafe_name] = b"{}\n"
    _write_final_artifact_fixture(tmp_path, env, signed_files, final_files)

    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "final_zip_member_invalid" in completed.stderr


def test_final_artifact_rejects_main_change_after_publication(tmp_path: Path) -> None:
    source, env, _, _ = _final_artifact_fixture(tmp_path)
    _write_json(
        tmp_path / "final-main-post-publish.json",
        {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": "b" * 40},
        },
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "post_publish_main_ref_not_exact_source" in completed.stderr


def test_final_artifact_rest_identity_rejects_stale_workflow_source(
    tmp_path: Path,
) -> None:
    source, env, _, _ = _final_artifact_fixture(tmp_path)
    api = json.loads((tmp_path / "final-artifact-api.json").read_text())
    api["workflow_run"]["head_sha"] = "b" * 40
    _write_json(tmp_path / "final-artifact-api.json", api)
    _write_json(
        tmp_path / "final-artifacts.json",
        {"artifacts": [api], "total_count": 1},
    )

    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "final_artifact_api_identity_invalid" in completed.stderr


def test_candidate_seal_attestation_predicate_binds_exact_product_invocation(
    tmp_path: Path,
) -> None:
    source = _step_python(
        "verify-current-state",
        "Verify all exact-source attestations",
        "ROOT=",
    )
    repository = "example/repo"
    source_sha = "a" * 40
    run_id = 701
    run_attempt = 1
    root = tmp_path / "root"
    root.mkdir()
    seal_raw = b'{"release_authority":false}\n'
    (root / "product-state-candidate.seal.json").write_bytes(seal_raw)
    repository_url = f"https://github.com/{repository}"
    statement = {
        "_type": "https://in-toto.io/Statement/v1",
        "subject": [
            {
                "name": "product-state-candidate.seal.json",
                "digest": {"sha256": hashlib.sha256(seal_raw).hexdigest()},
            }
        ],
        "predicateType": "https://slsa.dev/provenance/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://actions.github.io/buildtypes/workflow/v1",
                "externalParameters": {
                    "workflow": {
                        "path": ".github/workflows/product-state-current.yml",
                        "ref": "refs/heads/main",
                        "repository": repository_url,
                    }
                },
                "internalParameters": {
                    "github": {
                        "event_name": "workflow_run",
                        "runner_environment": "github-hosted",
                    }
                },
                "resolvedDependencies": [
                    {
                        "uri": f"git+{repository_url}@refs/heads/main",
                        "digest": {"gitCommit": source_sha},
                    }
                ],
            },
            "runDetails": {
                "builder": {
                    "id": (
                        f"{repository_url}/.github/workflows/"
                        "product-state-current.yml@refs/heads/main"
                    )
                },
                "metadata": {
                    "invocationId": (
                        f"{repository_url}/actions/runs/{run_id}/attempts/{run_attempt}"
                    )
                },
            },
        },
    }
    report = [
        {
            "attestation": {},
            "verificationResult": {
                "signature": {"certificate": {"verified": True}},
                "verifiedTimestamps": [{"verified": True}],
                "statement": statement,
            },
        }
    ]
    report_path = (
        tmp_path / "product-state-candidate.seal.attestation-verification.json"
    )
    _write_json(report_path, report)
    env = {
        **os.environ,
        "ROOT": str(root),
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_REPOSITORY": repository,
        "GITHUB_RUN_ID": str(run_id),
        "GITHUB_RUN_ATTEMPT": str(run_attempt),
        "PRODUCT_STATE_SHA": source_sha,
    }
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report[0]["verificationResult"]["statement"]["predicate"]["runDetails"]["metadata"][
        "invocationId"
    ] = f"{repository_url}/actions/runs/{run_id}/attempts/2"
    _write_json(report_path, report)
    completed = subprocess.run(
        [sys.executable, "-I", "-c", source],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "candidate_seal_attestation_invocation_invalid" in completed.stderr
