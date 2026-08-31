from __future__ import annotations

import ast
from copy import deepcopy
import io
import json
import math
from pathlib import Path
from pathlib import PurePosixPath
import re
import stat
import textwrap
import unicodedata
from urllib.parse import quote
import zipfile

import pytest
import yaml

from scripts import check_github_actions_runner_policy as runner_policy


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/current-main-evidence-index.yml"


def test_workflow_is_product_state_to_evidence_index_only() -> None:
    text = WORKFLOW.read_text()
    payload = yaml.safe_load(text)
    trigger = payload[True]
    assert trigger["workflow_run"]["workflows"] == ["Product State Current"]
    assert "workflow_dispatch" not in trigger
    assert "Nightly Full Quality" not in trigger["workflow_run"]["workflows"]
    assert "pull_request_target" not in trigger
    assert "nightly_to_product_state_to_evidence_index" in text
    assert '"consumed": True' in text
    assert "authenticated-product-state-overlay.v1" in text


def test_candidate_digest_is_normalized_to_the_github_api_shape() -> None:
    payload = yaml.safe_load(WORKFLOW.read_text())
    assert payload["jobs"]["collect-and-validate"]["outputs"]["candidate-digest"] == (
        "${{ format('sha256:{0}', steps.upload.outputs.artifact-digest) }}"
    )


def test_embedded_contract_and_upstream_root_lists_match_the_builder() -> None:
    from scripts import build_current_main_evidence_index as builder

    tree = _inline_tree()
    assignments = {
        name: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for name in _assignment_names(node)
        if name in {"CONTRACT_FILES", "UPSTREAM_ROOT_FILES"}
    }
    assert assignments["CONTRACT_FILES"] == list(builder.CONTRACT_FILES)
    assert len(assignments["CONTRACT_FILES"]) == len(
        set(assignments["CONTRACT_FILES"])
    ) == 15
    assert assignments["UPSTREAM_ROOT_FILES"] == list(
        builder.PRODUCT_STATE_ROOT_FILES
    )
    assert len(assignments["UPSTREAM_ROOT_FILES"]) == 18


def test_privileged_catalog_policy_and_schema_consts_are_runtime_bound() -> None:
    from scripts import build_current_main_evidence_index as builder

    tree = _inline_tree()
    lane_policy = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and "lane_policy" in _assignment_names(node)
    )
    assert lane_policy == builder.LANE_POLICY_ROOTS
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    assert 'files["canonical/current-main-evidence-lanes.v1.schema.json"]' in privileged
    assert "catalog_schema_lane_constants_mismatch" in privileged
    assert "canonical(schema_lane_constants) == canonical(catalog_lanes)" in privileged
    assert "canonical(lane_policy[lane])" in privileged


def test_privileged_datetime_boundary_rejects_invalid_calendar_values() -> None:
    tree = _inline_tree()
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"fail", "require", "aware_datetime"}
    ]
    namespace: dict[str, object] = {
        "datetime": __import__("datetime").datetime,
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]),
            "<privileged-datetime-boundary>",
            "exec",
        ),
        namespace,
    )
    validate = namespace["aware_datetime"]
    assert validate("2026-08-31T12:34:56Z", "valid") == "2026-08-31T12:34:56Z"
    for invalid in (
        "2026-13-40T25:61:61Z",
        "2026-08-31T12:34:56",
        20260831,
    ):
        with pytest.raises(SystemExit):
            validate(invalid, "invalid")


def test_catalog_product_state_jobs_match_the_live_workflow() -> None:
    catalog = json.loads(
        (ROOT / "canonical/current-main-evidence-lanes.v1.json").read_text()
    )
    product_state = yaml.safe_load(
        (ROOT / ".github/workflows/product-state-current.yml").read_text()
    )

    assert catalog["product_state_upstream"]["required_jobs"] == list(
        product_state["jobs"]
    )


def test_catalog_and_generator_enforce_final_chain_event_uniqueness() -> None:
    catalog = json.loads(
        (ROOT / "canonical/current-main-evidence-lanes.v1.json").read_text()
    )
    events = {row["lane_id"]: row["allowed_events"] for row in catalog["lanes"]}
    assert events == {
        "medium": ["push"],
        "ifc": ["push"],
        "mgt9": ["push"],
        "mgt10": ["push"],
        "native": ["push", "workflow_dispatch"],
    }
    workflow = yaml.safe_load(WORKFLOW.read_text())
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_catalog_binds_issue_state_as_a_separate_non_authoritative_observation() -> (
    None
):
    catalog = json.loads(
        (ROOT / "canonical/current-main-evidence-lanes.v1.json").read_text()
    )
    issue_state = yaml.safe_load(
        (ROOT / ".github/workflows/issue-state-current.yml").read_text()
    )
    observation = catalog["issue_state_observation"]
    assert catalog["required_lane_count"] == 5
    assert [row["lane_id"] for row in catalog["lanes"]] == [
        "medium",
        "ifc",
        "mgt9",
        "mgt10",
        "native",
    ]
    assert observation["required_jobs"] == list(issue_state["jobs"])
    assert observation["technical_lane"] is False
    assert observation["promotion_eligible"] is False
    assert observation["observation_scope"] == "github_issue_state_hygiene_only"


def test_privileged_job_has_no_checkout_setup_dependencies_or_repository_code() -> None:
    text = WORKFLOW.read_text()
    privileged = text.split("  attest-index:\n", 1)[1]
    assert "actions/checkout@" not in privileged
    assert "actions/setup-" not in privileged
    assert "pip install" not in privileged
    assert "npm " not in privileged
    assert "python3 scripts/" not in privileged
    assert "bash scripts/" not in privileged
    assert "id-token: write" in privileged
    assert "actions/attest@508db95dd578ae2727ebd6217d5ba78e4fbda05d" in privileged
    assert "technical-subject.json" in privileged
    assert "reject_nested_authority" in privileged
    assert "KNOWN_AUTHORITY_KEYS" in privileged
    assert "nested_authority_promoted" in privileged
    assert "candidate_source_blob_mismatch" in privileged
    assert 'require(artifact_id <= MAX_SAFE, "candidate_id_unsafe")' in privileged
    assert 'positive(value.get("run_number"), "workflow_run_number:" + label)' in privileged
    assert 'isinstance(source_commit["tree"].get("sha"), str)' in privileged
    assert 'isinstance(workflow_content.get("sha"), str)' in privileged
    assert "git_blob(files[path])" in privileged
    assert "medium_nested_authority_invalid" in privileged
    assert "ifc_nested_authority_invalid" in privileged
    assert "mgt_nested_authority_invalid" in privileged
    assert "native_nested_authority_invalid" in privileged
    assert '"gh", "attestation", "verify"' in privileged
    assert "trusted_pair_reconstruction_mismatch" in privileged
    assert '"verified_pair_sha256": sha256(files[verified_name])' in privileged
    assert "trusted_index_reconstruction_mismatch" in privileged
    assert "product_state_exact_four_job_success_required" in privileged
    assert "unique_exact_source_workflow_run" in privileged
    assert 'label="generator"' in privileged
    assert 'label="product_state"' in privileged
    assert 'label="product_state_overlay"' in privileged
    assert "generator_run_list_refetch_mismatch" in privileged
    assert "product_state_run_list_refetch_mismatch" in privileged
    assert "product_state_overlay_run_list_refetch_mismatch" in privileged
    assert "product_state_artifact_list_refetch_mismatch" in privileged
    assert "product_state_artifact_member_set_invalid" in privileged
    assert "product-state-candidate.seal.sigstore.json" in privileged
    assert "product_state_candidate_artifact_refetch_mismatch" in privileged
    assert "_candidate_to_final_bytes_mismatch" in privileged
    assert "product_state_signed_artifact_inventory_mismatch" in privileged
    assert "product_state_signed_to_final_bytes_mismatch" in privileged
    assert "product_state_candidate_seal_provenance_binding_invalid" in privileged
    assert "product_state_provenance_artifact_binding_invalid" in privileged
    assert "product_state_provenance_dag_binding_invalid" in privileged
    assert "product_state_post_main_overlay_identity_invalid" in privileged
    assert "product_state_overlay_attestor_job_invalid" in privileged
    assert 'label="product-overlay"' in privileged
    assert "product_state_final_verification_report_mismatch" in privileged
    assert 'type(final_report["raw_zip_bytes"]) is int' in privileged
    assert (
        'type(\n                  '
        'final_report["candidate_seal_attestation_verification_bytes"]\n'
        "              ) is int"
    ) in privileged
    assert 'label + "_source_schema_root_contract_invalid"' in privileged
    assert "product_state_external_promotion_boundary_invalid" in privileged
    assert 'label="product-state"' in privileged
    assert 'label="product-provenance"' in privileged
    assert "candidate_sigstore_bundle_bytes_mismatch" in privileged
    assert "candidate_handoff_seal_bytes_mismatch" in privileged
    assert '"sigstore_bundle_sha256": sha256(files[bundle_name])' in privileged
    assert '"handoff_seal_sha256": sha256(files[seal_name])' in privileged


def test_unprivileged_consumer_order_and_exact_action_pins() -> None:
    script = (ROOT / "scripts/build_current_main_evidence_index.py").read_text()
    lane_function = script.split("def _collect_lane(", 1)[1].split(
        "def _artifact_hash", 1
    )[0]
    assert lane_function.index("_run_sigstore_verification(") < lane_function.index(
        "_invoke_pair_verifier("
    )
    text = WORKFLOW.read_text()
    assert "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803" in text
    assert (
        text.count("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a")
        == 2
    )
    assert "run_attempt == 1" in text
    assert "PRODUCT_STATE_RUN_ID" in text


def test_privileged_consumer_reauthenticates_upstream_before_pair_use() -> None:
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    assert 'api(f"actions/runs/{run}/attempts/1"' in privileged
    assert 'api(f"actions/runs/{run}/attempts/1/jobs?per_page=100"' in privileged
    assert 'api(f"actions/artifacts/{upstream_id}"' in privileged
    assert 'f"actions/artifacts/{product_artifact_id}"' in privileged
    assert 'f"actions/runs/{product_state_run_id}/artifacts?per_page=100"' in privileged
    assert "artifact_size_mismatch" in privileged
    assert "artifact_digest_mismatch" in privileged
    assert 'source_blob(specification["workflow_path"]' in privileged
    assert privileged.index("result = subprocess.run(") < privileged.index(
        'strict_json(files[pair_name], "pair:" + lane)'
    )
    assert privileged.index("product_archive = download_artifact") < privileged.index(
        "product_document = strict_json"
    )
    assert privileged.index(
        "product_candidate_archive = download_artifact"
    ) < privileged.index("product_document = strict_json")


def test_technical_lane_inventory_is_complete_all_status_and_exact_source() -> None:
    script = (ROOT / "scripts/build_current_main_evidence_index.py").read_text()
    selector = script.split("def _select_lane_run", 1)[1].split(
        "def _validate_lane_jobs", 1
    )[0]
    assert "head_sha={source_sha}" in selector
    assert "status=success" not in selector
    assert 'payload["total_count"] == len(rows)' in selector
    assert "first_attempt_run_not_successful" in selector
    assert "unique_exact_source_run_required" in selector

    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    lane_selector = privileged.split("lane_workflow_file = quote(", 1)[1].split(
        "lane_run = workflow_run(", 1
    )[0]
    assert '"&head_sha=" + source' in lane_selector
    assert "status=success" not in lane_selector
    assert 'lane_run_inventory["total_count"] == len(lane_run_rows)' in lane_selector
    assert "len(lane_run_rows) == 1" in lane_selector
    assert 'lane_run_rows[0].get("run_attempt") == 1' in lane_selector
    assert 'lane_run_rows[0].get("conclusion") == "success"' in lane_selector


def test_issue_state_companion_has_bounded_poll_and_independent_privileged_replay() -> (
    None
):
    script = (ROOT / "scripts/build_current_main_evidence_index.py").read_text()
    selector = script.split("def _select_issue_state_run(", 1)[1].split(
        "def _validate_issue_state_jobs", 1
    )[0]
    collector = script.split("def _collect_issue_state_observation(", 1)[1].split(
        "def _select_lane_run", 1
    )[0]
    assert "ISSUE_STATE_MAX_POLL_ATTEMPTS" in selector
    assert "sleep(poll_interval_seconds)" in selector
    assert "event=push" in selector and "head_sha={source_sha}" in selector
    assert 'payload["total_count"] == len(rows)' in selector
    assert "issue_state_unique_exact_source_push_run_required" in selector
    assert "_run_issue_state_replay(" in collector
    assert "issue_state_artifact_exact_five_file_bundle_required" in script

    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    assert "issue_state_unique_successful_exact_source_push_run_required" in privileged
    issue_selector = privileged.split("issue_runs = api(", 1)[1].split(
        "issue_run = workflow_run(", 1
    )[0]
    assert "&status=success" not in issue_selector
    assert "len(issue_run_rows) == 1" in issue_selector
    assert 'issue_run_rows[0].get("run_attempt") == 1' in issue_selector
    assert 'issue_run_rows[0].get("status") == "completed"' in issue_selector
    assert 'issue_run_rows[0].get("conclusion") == "success"' in issue_selector
    assert "issue_state_exact_two_job_success_required" in privileged
    assert "issue_state_artifact_list_refetch_mismatch" in privileged
    assert "issue_state_artifact_expiry_or_repository_identity_invalid" in privileged
    assert "issue_state_artifact_exact_five_file_bundle_required" in privileged
    assert "issue_state_schema_pass_live_contract_invalid" in privileged
    assert "issue_state_strict_report_schema_replay_invalid" in privileged
    assert "trusted_issue_state_observation_reconstruction_mismatch" in privileged
    assert '"issue_state_observation": expected_issue_observation' in privileged
    assert "issues?state=open&per_page=100" in privileged
    assert 'api(f"repos/{repository}/issues' not in privileged


def test_privileged_issue_inventory_and_report_require_exact_false_authority() -> None:
    namespace = _inline_security_namespace()
    validate_inventory = namespace["validate_issue_inventory_authority"]
    boundary = namespace["ISSUE_CLAIM_BOUNDARY"]
    authority = dict(namespace["ISSUE_AUTHORITY"])
    valid = {"claims": authority, "claim_boundary": boundary}
    validate_inventory(valid)
    for mutation in (
        {**valid, "claims": {**authority, "release_authority": True}},
        {**valid, "claims": {**authority, "release_authority": 0}},
        {**valid, "claim_boundary": boundary + " broadened"},
    ):
        with pytest.raises(SystemExit):
            validate_inventory(mutation)
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    assert "issue_report_authority = exact_issue_false_authority(" in privileged
    assert (
        'issue_row["authority"], "index_issue_state_observation_authority"'
        in privileged
    )


def test_privileged_authenticates_all_eight_nightly_overlay_jobs() -> None:
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    overlay = privileged.split(
        'overlay_jobs = workflow_jobs(overlay_run_id, "product_state_overlay")', 1
    )[1].split("overlay_claims =", 1)[0]
    for name in (
        "nightly-pytest-full-shard-0",
        "nightly-pytest-full-shard-1",
        "nightly-pytest-full-shard-2",
        "nightly-pytest-full-shard-3",
        "deterministic-quality",
        "full-quality",
        "build-post-main-overlay",
        "attest-post-main-overlay",
    ):
        assert name in overlay
    assert "len(overlay_jobs) == 8" in overlay
    assert "for job in overlay_jobs" in overlay
    assert "github_hosted_job(" in overlay
    assert "product_state_overlay_exact_job_inventory_invalid" in overlay


def test_privileged_exact_source_inventory_rejects_attempt_two_sibling() -> None:
    tree = _inline_tree()
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {"fail", "require", "positive", "unique_exact_source_workflow_run"}
    ]
    source = "1" * 40
    workflow_path = ".github/workflows/example.yml"
    run = {
        "id": 101,
        "run_number": 101,
        "run_attempt": 1,
        "head_sha": source,
        "head_branch": "main",
        "path": workflow_path,
        "name": "Example",
        "event": "push",
    }
    payload = {"workflow_runs": [run], "total_count": 1}

    def api(endpoint: str, label: str):
        assert "head_sha=" + source in endpoint
        return payload

    namespace: dict[str, object] = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "PurePosixPath": PurePosixPath,
        "api": api,
        "quote": quote,
        "source": source,
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]),
            "<unique-exact-source-workflow-run>",
            "exec",
        ),
        namespace,
    )
    validate = namespace["unique_exact_source_workflow_run"]
    assert (
        validate(
            101,
            path=workflow_path,
            name="Example",
            events={"push"},
            label="example",
        )
        == run
    )

    payload["workflow_runs"] = [run, {**run, "id": 102, "run_attempt": 2}]
    payload["total_count"] = 2
    with pytest.raises(SystemExit, match="unique_exact_source_workflow_run_required"):
        validate(
            101,
            path=workflow_path,
            name="Example",
            events={"push"},
            label="example",
        )

    for field, alias in (("id", True), ("run_attempt", True), ("run_attempt", 1.0)):
        payload["workflow_runs"] = [{**run, field: alias}]
        payload["total_count"] = 1
        with pytest.raises(SystemExit):
            validate(
                101,
                path=workflow_path,
                name="Example",
                events={"push"},
                label="example",
            )


def test_final_publish_uses_one_exact_root_and_reauthenticates_archive() -> None:
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    assert "Stage exact single-root final artifact" in privileged
    stage = privileged.split("- name: Stage exact single-root final artifact", 1)[
        1
    ].split("- name: Publish technical-only index and provenance bundle", 1)[0]
    assert 'gh attestation verify "$index_subject"' in stage
    assert '--bundle "$ATTESTATION_BUNDLE_PATH"' in stage
    assert "--deny-self-hosted-runners" in stage
    assert "index_attestation_subject_invalid" in stage
    assert "index_attestation_provenance_identity_invalid" in stage
    assert "index_attestation_verification_report_invalid" in stage
    assert "verified_final_source_member_set_invalid" in privileged
    assert "staged_final_artifact_member_set_invalid" in privileged
    publish = privileged.split(
        "- name: Publish technical-only index and provenance bundle", 1
    )[1].split("- name: Reauthenticate published artifact and final main", 1)[0]
    assert "id: publish" in publish
    assert "path: ${{ runner.temp }}/current-main-evidence-index-publish" in publish
    assert "steps.attest.outputs.bundle-path" not in publish
    post_publish = privileged.split(
        "- name: Reauthenticate published artifact and final main", 1
    )[1]
    assert "steps.publish.outputs.artifact-id" in post_publish
    assert "steps.publish.outputs.artifact-digest" in post_publish
    assert "published_artifact_list_refetch_mismatch" in post_publish
    assert "published_artifact_archive_identity_invalid" in post_publish
    assert "published_archive_exact_member_bytes_mismatch" in post_publish
    assert "validate_terminal_run_payload" in post_publish
    assert "terminal_specs = (" in post_publish
    assert '{"schedule", "workflow_dispatch"}' in post_publish
    assert '{"push", "workflow_dispatch"}' in post_publish
    assert 'type(payload.get("total_count")) is int' in post_publish
    assert 'type(row.get("id")) is int' in post_publish
    assert 'type(row.get("run_attempt")) is int' in post_publish
    assert '"floating_json_number:" + label' in post_publish
    assert "published_local_member_set_invalid" in post_publish
    assert "len(expected_files) == 70" in post_publish
    assert post_publish.count("git/ref/heads/main") >= 3


def _post_publish_tree() -> ast.Module:
    source = WORKFLOW.read_text()
    post_publish = source.split(
        "- name: Reauthenticate published artifact and final main", 1
    )[1]
    block = post_publish.split("          python3 -I - <<'PY'\n", 1)[1].split(
        "\n          PY", 1
    )[0]
    return ast.parse(textwrap.dedent(block))


def test_post_publish_terminal_validator_rejects_float_integer_aliases() -> None:
    tree = _post_publish_tree()
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name
        in {
            "fail",
            "require",
            "pairs",
            "strict_json_bytes",
            "positive",
            "validate_terminal_run_payload",
        }
    ]
    source = "1" * 40
    namespace: dict[str, object] = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "json": json,
        "source": source,
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]),
            "<post-publish-terminal-validator>",
            "exec",
        ),
        namespace,
    )
    strict_json_bytes = namespace["strict_json_bytes"]
    with pytest.raises(SystemExit, match="floating_json_number"):
        strict_json_bytes(b'{"id":1.0}', "float-alias")

    validate = namespace["validate_terminal_run_payload"]
    row = {
        "id": 77,
        "run_number": 77,
        "run_attempt": 1,
        "head_sha": source,
        "head_branch": "main",
        "path": ".github/workflows/example.yml",
        "name": "Example",
        "event": "push",
        "status": "completed",
        "conclusion": "success",
    }
    payload = {"total_count": 1, "workflow_runs": [row]}
    validate(
        payload,
        selected_run=77,
        workflow_path=row["path"],
        workflow_name=row["name"],
        allowed_events={"push"},
        completion_mode="success",
    )
    for mutation in (
        {"total_count": 1.0, "workflow_runs": [row]},
        {"total_count": 1, "workflow_runs": [{**row, "id": 77.0}]},
        {"total_count": 1, "workflow_runs": [{**row, "run_attempt": 1.0}]},
    ):
        with pytest.raises(SystemExit):
            validate(
                mutation,
                selected_run=77,
                workflow_path=row["path"],
                workflow_name=row["name"],
                allowed_events={"push"},
                completion_mode="success",
            )


def test_final_attestation_subject_rejects_empty_wrong_name_or_digest() -> None:
    source = WORKFLOW.read_text()
    stage = source.split("- name: Stage exact single-root final artifact", 1)[1].split(
        "- name: Publish technical-only index and provenance bundle", 1
    )[0]
    block = stage.split("          python3 -I - <<'PY'\n", 1)[1].split(
        "\n          PY", 1
    )[0]
    tree = ast.parse(textwrap.dedent(block))
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"require", "validate_index_attestation_subject"}
    ]
    namespace: dict[str, object] = {"hashlib": __import__("hashlib")}
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]),
            "<final-attestation-subject>",
            "exec",
        ),
        namespace,
    )
    validate = namespace["validate_index_attestation_subject"]
    raw = b'{"contract_pass":true}\n'
    digest = __import__("hashlib").sha256(raw).hexdigest()
    valid = {
        "_type": "https://in-toto.io/Statement/v1",
        "predicateType": "https://slsa.dev/provenance/v1",
        "subject": [{"name": "index.json", "digest": {"sha256": digest}}],
    }
    validate(valid, raw, "index.json")
    for mutation in (
        {},
        {**valid, "subject": []},
        {
            **valid,
            "subject": [{"name": "wrong.json", "digest": {"sha256": digest}}],
        },
        {
            **valid,
            "subject": [{"name": "index.json", "digest": {"sha256": "0" * 64}}],
        },
    ):
        with pytest.raises(SystemExit, match="index_attestation_subject_invalid"):
            validate(mutation, raw, "index.json")


def test_exact_source_clean_tree_guard_preserves_git_failure() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'test -z "$(git status' not in source
    assert (
        'checkout_status="$(git status --porcelain=v1 --untracked-files=all)"' in source
    )
    assert 'test -z "$checkout_status"' in source


def test_consumer_requires_all_four_product_state_stages() -> None:
    script = (ROOT / "scripts/build_current_main_evidence_index.py").read_text()
    product_state = script.split("def _product_state_run(", 1)[1].split(
        "def _select_lane_run", 1
    )[0]
    for job in (
        "build-current-state",
        "attest-current-state",
        "verify-current-state",
        "replay-final-attestations",
    ):
        assert job in product_state
    assert "product_state_four_stage_success_required" in product_state


def test_evidence_index_is_an_explicit_github_hosted_lane() -> None:
    assert (
        str(WORKFLOW.relative_to(ROOT)) in runner_policy.DEFAULT_GITHUB_HOSTED_WORKFLOWS
    )
    result = runner_policy.check_runner_policy()
    assert result["contract_pass"] is True, result["blockers"]


def _inline_tree() -> ast.Module:
    source = WORKFLOW.read_text()
    block = source.split("          python3 -I - <<'PY'\n", 1)[1].split(
        "\n          PY", 1
    )[0]
    return ast.parse(textwrap.dedent(block))


def _assignment_names(node: ast.stmt) -> set[str]:
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def _inline_security_namespace() -> dict[str, object]:
    tree = _inline_tree()
    wanted = {
        "fail",
        "require",
        "exact",
        "canonical_contract_token",
        "authority_semantic_key",
        "nonpromoting_authority",
        "reject_nested_authority",
        "exact_issue_false_authority",
        "validate_issue_inventory_authority",
        "exact_nonpromotion",
        "canonical",
        "validate_sigstore_report",
    }
    assignments = {
        "KNOWN_AUTHORITY_KEYS",
        "KNOWN_AUTHORITY_COMPACT",
        "SENSITIVE_AUTHORITY_SCOPES",
        "AUTHORITY_DECISIONS",
        "TECHNICAL_GRANTS",
        "SAFE_AUTHORITY_STATUSES",
        "ISSUE_AUTHORITY",
        "ISSUE_CLAIM_BOUNDARY",
    }
    selected = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or bool(_assignment_names(node) & assignments)
    ]
    namespace: dict[str, object] = {
        "json": json,
        "re": re,
        "unicodedata": unicodedata,
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]), "<inline-security>", "exec"
        ),
        namespace,
    )
    return namespace


def test_privileged_validator_rejects_extra_release_authority() -> None:
    namespace = _inline_security_namespace()
    validate = namespace["exact_nonpromotion"]
    value = {"status": "pass", "release_authority": True}
    try:
        validate(value, {"status", "release_authority"}, "index")
    except SystemExit as error:
        assert "nested_authority_promoted:$index.release_authority" in str(error)
    else:
        raise AssertionError("extra release authority was accepted")


def test_privileged_validator_uses_the_production_known_authority_denyset() -> None:
    namespace = _inline_security_namespace()
    denyset = namespace["KNOWN_AUTHORITY_KEYS"]
    assert {
        "formal_verification_level_2",
        "verification_level_2",
        "independent_operator_attested",
        "independent_operator_attestation",
        "independent_operator_identity_authentication",
        "formal_level_2_promotion",
        "independent_verification_level_2",
        "paid_pilot",
        "paid_pilot_ready",
    } <= denyset


@pytest.mark.parametrize(
    "key",
    [
        "formal_verification_level_2",
        "verification_level_2",
        "independent_operator_attested",
        "independent_operator_attestation",
        "independent_operator_identity_authentication",
        "formal_level_2_promotion",
        "paid_pilot_ready",
        "RELEASE_AUTHORITY",
        "Release_Authority",
        "releaseAuthority",
        "release-authority",
        "release authority",
        "re-lease-authority",
        "independentVerificationLevel2",
        "indepen-dent verification level 2",
        "commercialRightsApproved",
        "legalAuthority",
        "paidPilotReady",
    ],
)
def test_privileged_validator_recursively_rejects_known_authority_variants(
    key: str,
) -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="nested_authority_promoted"):
        validate({"outer": [{"claims": {key: True}}]}, "$subject")


@pytest.mark.parametrize(
    "key",
    [
        "ＲＥＬＥＡＳＥ_authority",
        "releаse_authority",  # Cyrillic small a.
        "release_au\u200bthority",
        "release_\nauthority",
    ],
)
def test_privileged_validator_rejects_unicode_or_confusable_contract_keys(
    key: str,
) -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="contract_token_unicode_invalid"):
        validate({"outer": [{key: True}]}, "$subject")


@pytest.mark.parametrize("document", ["product", "ifc", "medium"])
@pytest.mark.parametrize(
    "key",
    [
        "releaseAuthority",
        "commercial-redistribution-approved",
        "legal approval",
        "independentVerificationLevel2",
        "paidPilot",
        "go_live",
        "general_availability",
        "production_ready",
        "scientific_decision_pass",
        "redistributable",
        "release_permitted",
        "fit_for_use",
        "commercializable",
        "level2_eligible",
        "operator_identity_credentials_verified",
    ],
)
def test_privileged_validator_rejects_semantic_authority_aliases_in_every_subject(
    document: str,
    key: str,
) -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="nested_authority_promoted"):
        validate({"payload": [{"claims": {key: True}}]}, f"${document}")


def test_privileged_validator_rejects_semantically_duplicate_keys() -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="contract_key_semantic_collision"):
        validate(
            {"claims": {"releaseAuthority": False, "release_authority": False}},
            "$product",
        )


def test_privileged_validator_allows_only_the_exact_technical_grant_allowlist() -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    validate(
        {"grants": ["bounded_developer_preview_technical_claims"]},
        "$product.authority_tracks.solo_developer_technical",
    )
    for token in (
        "release_authority",
        "releaseAuthority",
        "commercial-use-approved",
        "independent verification level 2",
        "paidPilotReady",
    ):
        with pytest.raises(SystemExit, match="technical_grants_invalid"):
            validate({"grants": [token]}, "$product")


@pytest.mark.parametrize(
    "key",
    ["GrantS", "g-rants", "G R A N T S", "technicalGrants", "release-grant"],
)
def test_privileged_validator_does_not_allow_grants_container_aliases(key: str) -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="technical_grants_invalid"):
        validate({key: ["releaseAuthority"]}, "$product")


@pytest.mark.parametrize(
    "token",
    [
        "ｂｏｕｎｄｅｄ_developer_preview_technical_claims",
        "bounded_developer_preview\u200b_technical_claims",
        "bounded_developer_preview\ntechnical_claims",
    ],
)
def test_privileged_validator_rejects_unicode_or_control_grant_tokens(
    token: str,
) -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    with pytest.raises(SystemExit, match="contract_token_unicode_invalid"):
        validate({"grants": [token]}, "$product")


def test_privileged_validator_requires_exact_safe_status_wrapper() -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    validate({"releaseAuthority": {"status": "unavailable"}}, "$product")
    with pytest.raises(SystemExit, match="nested_authority_promoted"):
        validate(
            {"releaseAuthority": {"status": "unavailable", "value": True}},
            "$product",
        )
    with pytest.raises(SystemExit, match="nested_authority_promoted"):
        validate(
            {"releaseAuthority": {"status": "ｕｎａｖａｉｌａｂｌｅ"}},
            "$product",
        )


def test_privileged_validator_allows_technical_completeness_claims_but_not_authority() -> (
    None
):
    validate = _inline_security_namespace()["reject_nested_authority"]
    validate(
        {
            "contract_pass": True,
            "internal_due_diligence_complete": True,
            "license_inventory_complete": True,
            "spdx_notices_complete": True,
            "redistribution_boundaries_explicit": True,
            "source_use_declarations_complete": True,
            "claims": {
                "formal_verification_level_2": False,
                "paid_pilot_ready": {"status": "unavailable"},
            },
        },
        "$subject",
    )


def test_privileged_validator_allows_exact_product_nonpromotion_containers() -> None:
    validate = _inline_security_namespace()["reject_nested_authority"]
    validate(
        {
            "authority_tracks": {
                "solo_developer_technical": {
                    "grants": ["bounded_developer_preview_technical_claims"],
                    "requires_counsel_legal_approval": False,
                    "does_not_grant": [
                        "independent_verification_level_2",
                        "commercial_equivalence",
                        "design_authority",
                        "release_authority",
                    ],
                },
                "external_promotion": {
                    "status": "unavailable",
                    "evidence": {
                        "independent_operator_identity_authentication": {
                            "status": "unavailable"
                        },
                        "product_legal_license_approval": {"status": "unavailable"},
                        "formal_level_2_promotion": {"status": "unavailable"},
                    },
                },
            }
        },
        "$product",
    )


def _inline_archive_namespace() -> dict[str, object]:
    tree = _inline_tree()
    wanted = {"fail", "require", "pairs", "strict_json", "safe_archive"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace: dict[str, object] = {
        "io": io,
        "json": json,
        "math": math,
        "PurePosixPath": PurePosixPath,
        "stat": stat,
        "unicodedata": unicodedata,
        "zipfile": zipfile,
        "MAX_SAFE": 9007199254740991,
    }
    exec(
        compile(ast.Module(body=selected, type_ignores=[]), "<inline-archive>", "exec"),
        namespace,
    )
    return namespace


@pytest.mark.parametrize(
    "name", ["bad\nname.json", "bad\x7fname.json", "bad\u200bname.json"]
)
def test_privileged_archive_rejects_control_or_format_member_names(name: str) -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(name, b"{}")
    validate = _inline_archive_namespace()["safe_archive"]
    with pytest.raises(SystemExit, match="archive_member_path_invalid"):
        validate(
            archive.getvalue(),
            "test",
            archive_limit=1_000_000,
            entries=5,
            member=1000,
            total_limit=1000,
        )


def _inline_product_binding_namespace() -> dict[str, object]:
    tree = _inline_tree()
    wanted = {
        "fail",
        "require",
        "exact",
        "sha256",
        "validate_sealed_file_rows",
        "validate_candidate_to_final_files",
        "validate_product_provenance_bindings",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace: dict[str, object] = {
        "hashlib": __import__("hashlib"),
        "SHA256": re.compile(r"sha256:[0-9a-f]{64}"),
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]),
            "<inline-product-binding>",
            "exec",
        ),
        namespace,
    )
    return namespace


def _product_binding_fixture() -> tuple[
    dict[str, bytes],
    str,
    str,
    list[dict[str, object]],
    dict[str, object],
]:
    product_path = "artifacts/manifests/product_state.current.v1.json"
    seal_path = "product-state-candidate.seal.json"
    paths = {
        "product_state": product_path,
        "product_state_schema": "canonical/product-state.current.v1.schema.json",
        "canonical_receipt": (
            "artifacts/manifests/canonical_verification_environment.current.v1.json"
        ),
        "canonical_project_wheel_contract": ".ci/canonical-project-wheel-contract.json",
        "canonical_project_wheel": (
            ".ci/canonical-wheel/structural_analysis-0.3.0-py3-none-any.whl"
        ),
        "generated_artifact_dag_state": (
            ".ci/product-state-inputs/generated-artifact-dag-state.v2.json"
        ),
        "generated_artifact_dag_report": (
            ".ci/product-state-inputs/generated-artifact-dag-report.v2.json"
        ),
        "product_state_workflow_definition": ".github/workflows/product-state-current.yml",
        "post_main_overlay_seal": (
            ".ci/product-state-inputs/post-main-overlay/"
            "post-main-evidence-overlay.seal.json"
        ),
    }
    files = {path: (label + "\n").encode() for label, path in paths.items()}
    files[seal_path] = b"sealed candidate\n"
    digest = _inline_product_binding_namespace()["sha256"]
    rows = [
        {"path": path, "bytes": len(files[path]), "sha256": digest(files[path])}
        for path in paths.values()
    ]
    artifacts = {
        label: {
            "path": path,
            "sha256": digest(files[path]),
            "byte_length": len(files[path]),
        }
        for label, path in paths.items()
    }
    nodes = {
        "canonical_receipt": "verification-receipts",
        "canonical_project_wheel_contract": "verification-receipts",
        "canonical_project_wheel": "verification-receipts",
        "product_state": "product-state",
    }
    provenance = {
        "artifacts": artifacts,
        "dag_artifact_bindings": {
            label: {
                "artifact": label,
                "node_id": node,
                "path": artifacts[label]["path"],
                "sha256": artifacts[label]["sha256"],
            }
            for label, node in nodes.items()
        },
    }
    return files, seal_path, product_path, rows, provenance


def test_privileged_product_candidate_replays_every_sealed_byte() -> None:
    namespace = _inline_product_binding_namespace()
    files, seal_path, _product_path, rows, _provenance = _product_binding_fixture()
    sealed_paths, _sealed_rows = namespace["validate_sealed_file_rows"](
        files, seal_path, rows, "product_state_seal"
    )
    final_files = {**files, "fresh-attestation.json": b"fresh\n"}
    assert namespace["validate_candidate_to_final_files"](
        files, final_files, sealed_paths, seal_path, "product_state"
    ) == namespace["sha256"](files[seal_path])
    final_files[rows[0]["path"]] = b"tampered\n"
    with pytest.raises(SystemExit, match="candidate_to_final_bytes_mismatch"):
        namespace["validate_candidate_to_final_files"](
            files, final_files, sealed_paths, seal_path, "product_state"
        )


@pytest.mark.parametrize("field", ["bytes", "sha256"])
def test_privileged_product_seal_rejects_every_row_mismatch(field: str) -> None:
    namespace = _inline_product_binding_namespace()
    files, seal_path, _product_path, rows, _provenance = _product_binding_fixture()
    if field == "bytes":
        rows[0][field] = int(rows[0][field]) + 1
    else:
        rows[0][field] = "sha256:" + "f" * 64
    with pytest.raises(SystemExit, match="product_state_seal_file_invalid"):
        namespace["validate_sealed_file_rows"](
            files, seal_path, rows, "product_state_seal"
        )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (
            lambda provenance: provenance["artifacts"]["product_state"].__setitem__(
                "sha256", "sha256:" + "f" * 64
            ),
            "product_state_provenance_artifact_binding_invalid",
        ),
        (
            lambda provenance: provenance["artifacts"]["canonical_receipt"].__setitem__(
                "path", "artifacts/manifests/swapped.json"
            ),
            "product_state_provenance_artifact_binding_invalid",
        ),
        (
            lambda provenance: provenance["dag_artifact_bindings"][
                "product_state"
            ].__setitem__("node_id", "verification-receipts"),
            "product_state_provenance_dag_binding_invalid",
        ),
    ],
)
def test_privileged_product_provenance_binding_fails_closed(
    mutation,
    reason: str,
) -> None:
    namespace = _inline_product_binding_namespace()
    files, seal_path, product_path, rows, provenance = _product_binding_fixture()
    sealed_paths, _sealed_rows = namespace["validate_sealed_file_rows"](
        files, seal_path, rows, "product_state_seal"
    )
    namespace["validate_product_provenance_bindings"](
        files, sealed_paths, product_path, provenance
    )
    mutation(provenance)
    with pytest.raises(SystemExit, match=reason):
        namespace["validate_product_provenance_bindings"](
            files, sealed_paths, product_path, provenance
        )


def test_privileged_requires_every_consumed_workflow_job_to_be_github_hosted() -> None:
    privileged = WORKFLOW.read_text().split("  attest-index:\n", 1)[1]
    lane_block = privileged.split("for row, specification in zip", 1)[1].split(
        "substitutions =", 1
    )[0]
    assert "for job in jobs" in lane_block
    assert "github_hosted_job(" in lane_block
    assert 'type(job.get("runner_group_id")) is int' in privileged
    assert 'job["runner_group_id"] == 0' in privileged
    assert 'job.get("runner_group_name") == "GitHub Actions"' in privileged
    assert 'job.get("runner_name") == f"GitHub Actions {runner_id}"' in privileged


def test_privileged_validator_rejects_empty_fake_sigstore_report() -> None:
    namespace = _inline_security_namespace()
    validate = namespace["validate_sigstore_report"]
    try:
        validate([], [], {}, {}, "medium")
    except SystemExit as error:
        assert "sigstore_report_shape_invalid:medium" in str(error)
    else:
        raise AssertionError("empty fake Sigstore report was accepted")


def _inline_predicate_namespace() -> dict[str, object]:
    tree = _inline_tree()
    wanted = {"fail", "require", "exact", "validate_sigstore_predicate"}
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    namespace: dict[str, object] = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "re": re,
        "repository": "example/structural-analysis",
        "source": "1" * 40,
    }
    exec(
        compile(
            ast.Module(body=selected, type_ignores=[]), "<inline-predicate>", "exec"
        ),
        namespace,
    )
    return namespace


def _sigstore_statement() -> dict[str, object]:
    repository_url = "https://github.com/example/structural-analysis"
    workflow = ".github/workflows/medium-scale-current-source.yml"
    return {
        "predicate": {
            "buildDefinition": {
                "buildType": "https://actions.github.io/buildtypes/workflow/v1",
                "externalParameters": {
                    "workflow": {
                        "path": workflow,
                        "ref": "refs/heads/main",
                        "repository": repository_url,
                    }
                },
                "internalParameters": {
                    "github": {
                        "event_name": "push",
                        "repository_id": "1234",
                        "repository_owner_id": "5678",
                        "runner_environment": "github-hosted",
                    }
                },
                "resolvedDependencies": [
                    {
                        "uri": f"git+{repository_url}@refs/heads/main",
                        "digest": {"gitCommit": "1" * 40},
                    }
                ],
            },
            "runDetails": {
                "builder": {
                    "id": (
                        f"{repository_url}/.github/workflows/"
                        "_technical-evidence-attest.yml@refs/heads/main"
                    )
                },
                "metadata": {
                    "invocationId": f"{repository_url}/actions/runs/123456/attempts/1"
                },
            },
        }
    }


def _validate_inline_predicate(
    statement: dict[str, object], **overrides: object
) -> None:
    arguments: dict[str, object] = {
        "workflow_path": ".github/workflows/medium-scale-current-source.yml",
        "builder_path": ".github/workflows/_technical-evidence-attest.yml",
        "event": "push",
        "run": 123456,
        "run_attempt": 1,
        "label": "medium",
    }
    arguments.update(overrides)
    _inline_predicate_namespace()["validate_sigstore_predicate"](
        statement,
        **arguments,
    )


def test_privileged_sigstore_predicate_binds_canonical_run_and_hosted_builder() -> None:
    _validate_inline_predicate(_sigstore_statement())


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (
            ("predicate", "runDetails", "metadata", "invocationId"),
            "https://github.com/example/structural-analysis/actions/runs/123455/attempts/1",
            "sigstore_invocation_identity_mismatch",
        ),
        (
            ("predicate", "runDetails", "metadata", "invocationId"),
            "https://github.com/example/structural-analysis/actions/runs/%31%32%33%34%35%36/attempts/1",
            "sigstore_invocation_identity_mismatch",
        ),
        (
            (
                "predicate",
                "buildDefinition",
                "internalParameters",
                "github",
                "event_name",
            ),
            "workflow_dispatch",
            "sigstore_github_identity_mismatch",
        ),
        (
            (
                "predicate",
                "buildDefinition",
                "internalParameters",
                "github",
                "runner_environment",
            ),
            "self-hosted",
            "sigstore_github_identity_mismatch",
        ),
        (
            ("predicate", "buildDefinition", "externalParameters", "workflow", "ref"),
            "refs/tags/old",
            "sigstore_workflow_identity_mismatch",
        ),
        (
            ("predicate", "runDetails", "builder", "id"),
            "https://github.com/example/structural-analysis/.github/workflows/medium-scale-current-source.yml@refs/heads/main",
            "sigstore_builder_identity_mismatch",
        ),
    ],
)
def test_privileged_sigstore_predicate_rejects_replay_and_identity_aliases(
    path: tuple[str, ...],
    value: object,
    reason: str,
) -> None:
    statement = deepcopy(_sigstore_statement())
    cursor: object = statement
    for key in path[:-1]:
        assert isinstance(cursor, dict)
        cursor = cursor[key]
    assert isinstance(cursor, dict)
    cursor[path[-1]] = value
    with pytest.raises(SystemExit, match=reason):
        _validate_inline_predicate(statement)


def test_privileged_sigstore_predicate_requires_first_attempt() -> None:
    with pytest.raises(SystemExit, match="sigstore_run_attempt_invalid"):
        _validate_inline_predicate(_sigstore_statement(), run_attempt=2)
