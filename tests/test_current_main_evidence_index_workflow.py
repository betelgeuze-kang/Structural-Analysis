from __future__ import annotations

import ast
from copy import deepcopy
from datetime import datetime
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


def _product_state_inventory_boundary(
    boundary, rows, direct_rows, *, total_count=None,
    source="1" * 40, selected_run=77, repository="owner/repository",
):
    tree = _post_publish_tree() if boundary == "terminal" else _inline_tree()
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "fail", "require", "positive", "canonical", "same_fields",
            "workflow_run", "unique_exact_source_workflow_run",
            "validate_terminal_run_payload",
        }
    ]
    calls = []
    payload = {
        "workflow_runs": rows,
        "total_count": len(rows) if total_count is None else total_count,
    }

    def api(endpoint, label):
        calls.append(endpoint)
        if endpoint.startswith("actions/workflows/"):
            assert "head_sha=" + source in endpoint
            return payload
        return direct_rows[int(endpoint.split("/")[2])]

    namespace = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "PurePosixPath": PurePosixPath,
        "quote": quote,
        "json": json,
        "source": source,
        "repository": repository,
        "api": api,
        "gh_json": api,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<product-state-boundary>", "exec"), namespace)

    def validate(*, path=None, name=None, events=None, completion_mode="success"):
        path = path or ".github/workflows/product-state-current.yml"
        name = name or "Product State Current"
        events = events or {"workflow_run"}
        if boundary == "terminal":
            return namespace["validate_terminal_run_payload"](
                payload, selected_run=selected_run, workflow_path=path, workflow_name=name,
                allowed_events=events, completion_mode=completion_mode,
            )
        return namespace["unique_exact_source_workflow_run"](
            selected_run, path=path, name=name, events=events,
            label="late:product_state" if boundary == "late_privileged" else "product_state",
        )

    return validate, calls


def _product_state_inventory_rows():
    target = {
        "id": 77, "run_number": 77, "run_attempt": 1,
        "head_sha": "1" * 40, "head_branch": "main",
        "path": ".github/workflows/product-state-current.yml",
        "name": "Product State Current", "event": "workflow_run",
        "status": "completed", "conclusion": "success",
        "head_repository": {"full_name": "owner/repository"},
    }
    failed = {**target, "id": 78, "run_number": 76, "conclusion": "failure"}
    return target, failed


def _lineage_inventory_rows(kind):
    target, failed = _product_state_inventory_rows()
    specification = {
        "product_state": (
            ".github/workflows/product-state-current.yml", "Product State Current",
            {"workflow_run"}, "workflow_run", "success",
        ),
        "nightly": (
            ".github/workflows/nightly-full-quality.yml", "Nightly Full Quality",
            {"schedule", "workflow_dispatch"}, "schedule", "success",
        ),
        "generator": (
            ".github/workflows/current-main-evidence-index.yml", "Current Main Evidence Index",
            {"workflow_run"}, "workflow_run", "active",
        ),
    }[kind]
    path, name, events, event, mode = specification
    target = {**target, "path": path, "name": name, "event": event, "run_number": 1}
    historical = {**target, "id": 79, "run_number": 99}
    failed = {**historical, "id": 78, "run_number": 98, "conclusion": "failure"}
    if kind == "nightly":
        historical["event"] = "workflow_dispatch"
    if kind == "generator":
        target = {**target, "status": "in_progress", "conclusion": None}
    return target, historical, failed, {
        "path": path, "name": name, "events": events, "completion_mode": mode,
    }


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("kind", ["product_state", "nightly", "generator"])
@pytest.mark.parametrize("selected_position", [0, 1, 2])
def test_explicit_lineage_id_is_order_independent_and_reauthenticates_all_history(
    boundary, kind, selected_position,
):
    target, historical, failed, specification = _lineage_inventory_rows(kind)
    rows = [historical, failed]
    rows.insert(selected_position, target)
    original_rows = deepcopy(rows)
    validate, calls = _product_state_inventory_boundary(
        boundary, rows, {77: target, 78: failed, 79: historical},
    )
    selected = validate(**specification)
    if boundary == "terminal":
        assert selected is None
    else:
        assert selected == target
    assert calls.count("actions/runs/78/attempts/1") == 1
    assert calls.count("actions/runs/79/attempts/1") == 1
    assert rows == original_rows


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("kind", ["product_state", "nightly", "generator"])
def test_explicit_lineage_never_substitutes_another_success_for_missing_selected_id(boundary, kind):
    target, historical, failed, specification = _lineage_inventory_rows(kind)
    validate, _ = _product_state_inventory_boundary(
        boundary, [historical, target, failed], {77: target, 78: failed, 79: historical},
        selected_run=80,
    )
    with pytest.raises(SystemExit):
        validate(**specification)


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("kind", ["product_state", "nightly", "generator"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"head_sha": "2" * 40}, {"head_repository": {"full_name": "other/repository"}},
        {"run_attempt": 2}, {"run_attempt": True}, {"run_attempt": 1.0},
        {"status": "in_progress", "conclusion": None}, {"conclusion": "cancelled"},
        {"head_branch": "other"}, {"path": ".github/workflows/other.yml"},
        {"event": "pull_request"}, {"run_number": True},
    ],
)
def test_explicit_lineage_rejects_invalid_successful_history(boundary, kind, mutation):
    target, historical, _, specification = _lineage_inventory_rows(kind)
    historical = {**historical, **mutation}
    validate, _ = _product_state_inventory_boundary(
        boundary, [historical, target], {77: target, 79: historical},
    )
    with pytest.raises(SystemExit):
        validate(**specification)


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("kind", ["product_state", "nightly", "generator"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"id": 80}, {"run_number": 100}, {"run_attempt": 2},
        {"head_sha": "2" * 40}, {"head_repository": {"full_name": "other/repository"}},
        {"conclusion": "failure"}, {"status": "in_progress"},
    ],
)
def test_explicit_lineage_rejects_successful_history_refetch_drift(boundary, kind, mutation):
    target, historical, _, specification = _lineage_inventory_rows(kind)
    validate, _ = _product_state_inventory_boundary(
        boundary, [historical, target], {77: target, 79: {**historical, **mutation}},
    )
    with pytest.raises(SystemExit):
        validate(**specification)


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("kind", ["product_state", "nightly", "generator"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"head_sha": "2" * 40}, {"head_repository": {"full_name": "other/repository"}},
        {"run_attempt": 2}, {"conclusion": "failure"}, {"path": ".github/workflows/other.yml"},
    ],
)
def test_explicit_lineage_does_not_hide_invalid_selected_run_behind_successful_history(
    boundary, kind, mutation,
):
    target, historical, _, specification = _lineage_inventory_rows(kind)
    target = {**target, **mutation}
    validate, _ = _product_state_inventory_boundary(
        boundary, [historical, target], {77: target, 79: historical},
    )
    with pytest.raises(SystemExit):
        validate(**specification)


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("failure_first", [True, False])
def test_product_state_workflow_accepts_only_validated_failed_sibling(boundary, failure_first):
    target, failed = _product_state_inventory_rows()
    rows = [failed, target] if failure_first else [target, failed]
    validate, calls = _product_state_inventory_boundary(boundary, rows, {77: target, 78: failed})
    validate()
    assert "actions/runs/78/attempts/1" in calls


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
def test_product_state_workflow_accepts_observed_fafd_failure_success_list(boundary):
    source = "fafd6a852c83670fb0377e20fd1432ee51998c78"
    repository = "betelgeuze-kang/Structural-Analysis"
    target, _ = _product_state_inventory_rows()
    target = {
        **target, "id": 38354652295, "run_number": 101, "head_sha": source,
        "head_repository": {"full_name": repository},
    }
    failed = {**target, "id": 38339482507, "run_number": 100, "conclusion": "failure"}
    validate, calls = _product_state_inventory_boundary(
        boundary, [target, failed], {target["id"]: target, failed["id"]: failed},
        source=source, selected_run=target["id"], repository=repository,
    )
    validate()
    assert "actions/runs/38339482507/attempts/1" in calls


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"status": "in_progress", "conclusion": None},
        {"run_attempt": 2}, {"run_attempt": True}, {"run_attempt": 1.0},
        {"status": "in_progress"}, {"head_sha": "2" * 40},
        {"head_branch": "other"}, {"path": ".github/workflows/other.yml"},
        {"name": "Other"}, {"event": "push"},
        {"event": []}, {"head_repository": []},
        {"head_repository": {"full_name": "other/repository"}},
        {"run_number": True}, {"id": True}, {"id": 77},
    ],
)
def test_product_state_workflow_rejects_invalid_or_ambiguous_failed_sibling(boundary, mutation):
    target, failed = _product_state_inventory_rows()
    failed = {**failed, **mutation}
    validate, _ = _product_state_inventory_boundary(boundary, [target, failed], {77: target, 78: failed})
    with pytest.raises(SystemExit):
        validate()


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize(
    "field",
    ["id", "run_number", "run_attempt", "status", "conclusion", "head_sha",
     "head_branch", "path", "name", "event", "head_repository"],
)
def test_product_state_workflow_rejects_incomplete_failed_sibling(boundary, field):
    target, failed = _product_state_inventory_rows()
    del failed[field]
    validate, _ = _product_state_inventory_boundary(boundary, [target, failed], {77: target, 78: failed})
    with pytest.raises(SystemExit):
        validate()


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"run_number": 99}, {"id": 79}, {"run_attempt": 2}, {"run_attempt": 1.0},
        {"head_sha": "2" * 40}, {"path": ".github/workflows/other.yml"},
        {"head_repository": {"full_name": "other/repository"}},
        {"conclusion": "success"}, {"status": "in_progress"},
        {"event": []},
    ],
)
def test_product_state_workflow_rejects_failed_sibling_refetch_drift(boundary, mutation):
    target, failed = _product_state_inventory_rows()
    validate, _ = _product_state_inventory_boundary(
        boundary, [target, failed], {77: target, 78: {**failed, **mutation}},
    )
    with pytest.raises(SystemExit):
        validate()


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("total_count", [1, 3, 2.0, True])
def test_product_state_workflow_rejects_incomplete_inventory_before_filtering(boundary, total_count):
    target, failed = _product_state_inventory_rows()
    validate, _ = _product_state_inventory_boundary(
        boundary, [target, failed], {77: target, 78: failed}, total_count=total_count,
    )
    with pytest.raises(SystemExit):
        validate()


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
@pytest.mark.parametrize("conclusion", ["success", "failure"])
@pytest.mark.parametrize(
    ("path", "name", "events"),
    [
        (".github/workflows/issue-state-current.yml", "Issue State Current", {"push"}),
        (".github/workflows/medium-scale-current-source.yml", "Medium Scale Current Source", {"push"}),
        (".github/workflows/ifc-import-health-current-source.yml", "IFC Import Health Current Source", {"push"}),
        (".github/workflows/mgt-import-health-current-source.yml", "MGT Import Health Current Source", {"push"}),
        (".github/workflows/mgt-import-health-tenth-source.yml", "MGT Import Health Tenth Source", {"push"}),
        (".github/workflows/native-frame-alpha-clean-install.yml", "Native Frame Alpha Clean Install",
         {"push", "workflow_dispatch"}),
    ],
)
def test_issue_and_technical_workflows_still_require_unique_exact_source_run(
    boundary, conclusion, path, name, events,
):
    target, failed = _product_state_inventory_rows()
    target = {**target, "path": path, "name": name, "event": "push"}
    failed = {**failed, "path": path, "name": name, "event": "push", "conclusion": conclusion}
    validate, calls = _product_state_inventory_boundary(boundary, [target, failed], {77: target, 78: failed})
    with pytest.raises(SystemExit):
        validate(path=path, name=name, events=events)
    assert not any("/attempts/1" in endpoint for endpoint in calls)


@pytest.mark.parametrize("direct_target", [False, True])
@pytest.mark.parametrize(
    "mutation",
    [
        {"conclusion": "failure"}, {"run_attempt": 2},
        {"head_sha": "2" * 40}, {"path": ".github/workflows/other.yml"},
        {"head_repository": {"full_name": "other/repository"}},
        {"run_number": 99},
    ],
)
def test_privileged_product_state_target_gates_still_reject_drift(direct_target, mutation):
    tree = _inline_tree()
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in {"fail", "require", "positive", "canonical", "same_fields",
                          "workflow_run", "unique_exact_source_workflow_run"}
    ]
    start = next(
        index for index, node in enumerate(tree.body)
        if isinstance(node, ast.Assign)
        and "product_state_inventory_row" in _assignment_names(node)
    )
    target, failed = _product_state_inventory_rows()
    inventory_target = target if direct_target else {**target, **mutation}
    direct = target if not direct_target else {**target, **mutation}

    def api(endpoint, label):
        if endpoint.startswith("actions/workflows/"):
            return {"workflow_runs": [failed, inventory_target], "total_count": 2}
        return {77: direct, 78: failed}[int(endpoint.split("/")[2])]

    namespace = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "PurePosixPath": PurePosixPath, "quote": quote, "json": json,
        "source": "1" * 40, "repository": "owner/repository", "api": api,
        "product_state_run_id": 77,
    }
    with pytest.raises(SystemExit):
        exec(
            compile(ast.Module(body=functions + tree.body[start:start + 3], type_ignores=[]),
                    "<actual-product-state-selection-and-refetch>", "exec"),
            namespace,
        )


def test_candidate_metadata_does_not_shadow_the_privileged_run_authenticator():
    tree = _inline_tree()
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in {"fail", "require", "positive", "workflow_run"}
    ]
    metadata_binding = next(
        node for node in tree.body if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.IfExp)
        and isinstance(node.value.body, ast.Call)
        and isinstance(node.value.body.func, ast.Attribute)
        and isinstance(node.value.body.func.value, ast.Name)
        and node.value.body.func.value.id == "metadata"
        and node.value.body.args
        and isinstance(node.value.body.args[0], ast.Constant)
        and node.value.body.args[0].value == "workflow_run"
    )
    target, _ = _product_state_inventory_rows()
    namespace = {
        "MAX_SAFE": 9_007_199_254_740_991, "source": "1" * 40,
        "repository": "owner/repository", "metadata": {"workflow_run": {"id": 123}},
        "api": lambda endpoint, label: target,
    }
    exec(
        compile(ast.Module(body=functions + [metadata_binding], type_ignores=[]),
                "<actual-candidate-metadata-binding>", "exec"),
        namespace,
    )
    assert callable(namespace["workflow_run"])
    assert namespace["workflow_run"](
        77, path=target["path"], name=target["name"], events={"workflow_run"}, label="product_state",
    ) == target


@pytest.mark.parametrize(
    ("artifact_case", "expected_error"),
    [
        ("selected", None),
        ("successful_sibling", "artifact_identity_invalid"),
        ("old_source", "artifact_identity_invalid"),
        ("expired", "artifact_identity_invalid"),
        ("refetch_digest_drift", "product_state_artifact_list_refetch_mismatch"),
    ],
)
def test_actual_product_state_artifact_selection_remains_bound_to_explicit_run(
    artifact_case, expected_error,
):
    tree = _inline_tree()
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in {
            "fail", "require", "positive", "canonical", "same_fields", "workflow_run",
            "unique_exact_source_workflow_run", "artifact_identity",
        }
    ]
    selection_start = next(
        index for index, node in enumerate(tree.body)
        if isinstance(node, ast.Assign) and "product_state_inventory_row" in _assignment_names(node)
    )
    artifact_start = next(
        index for index, node in enumerate(tree.body)
        if isinstance(node, ast.Assign) and "product_inventory" in _assignment_names(node)
    )
    artifact_end = next(
        index for index, node in enumerate(tree.body)
        if isinstance(node, ast.Assign) and "product_root_name" in _assignment_names(node)
    )
    target, historical, _, _ = _lineage_inventory_rows("product_state")
    api_root = "https://api.github.com/repos/owner/repository"
    artifact = {
        "id": 900, "name": f"product-state-current-success-{target['head_sha']}",
        "digest": "sha256:" + "a" * 64, "size_in_bytes": 100,
        "expired": False, "expires_at": "2099-01-01T00:00:00Z",
        "url": api_root + "/actions/artifacts/900",
        "archive_download_url": api_root + "/actions/artifacts/900/zip",
        "workflow_run": {"id": 77, "head_sha": target["head_sha"], "head_branch": "main"},
    }
    if artifact_case == "successful_sibling":
        artifact["workflow_run"]["id"] = 79
    elif artifact_case == "old_source":
        artifact["workflow_run"]["head_sha"] = "2" * 40
    elif artifact_case == "expired":
        artifact["expired"] = True
    fetched_artifact = deepcopy(artifact)
    if artifact_case == "refetch_digest_drift":
        fetched_artifact["digest"] = "sha256:" + "b" * 64
    calls = []

    def api(endpoint, label):
        calls.append(endpoint)
        if endpoint.startswith("actions/workflows/"):
            return {"workflow_runs": [historical, target], "total_count": 2}
        if endpoint == "actions/runs/77/artifacts?per_page=100":
            return {"artifacts": [artifact], "total_count": 1}
        if endpoint == "actions/artifacts/900":
            return fetched_artifact
        return {77: target, 79: historical}[int(endpoint.split("/")[2])]

    namespace = {
        "MAX_SAFE": 9_007_199_254_740_991, "MAX_UPSTREAM_TOTAL": 4096,
        "MAX_PRODUCT_TOTAL": 4096, "PurePosixPath": PurePosixPath, "quote": quote,
        "json": json, "datetime": datetime, "SHA256": re.compile(r"sha256:[0-9a-f]{64}"),
        "source": target["head_sha"], "repository": "owner/repository", "api": api,
        "api_root": api_root, "product_state_run_id": 77,
    }
    actual_selection = (
        tree.body[selection_start:selection_start + 3] + tree.body[artifact_start:artifact_end]
    )
    program = compile(
        ast.Module(body=functions + actual_selection, type_ignores=[]),
        "<actual-product-state-run-and-artifact-selection>", "exec",
    )
    if expected_error is None:
        exec(program, namespace)
        assert namespace["product_artifact"]["workflow_run"]["id"] == 77
    else:
        with pytest.raises(SystemExit, match=expected_error):
            exec(program, namespace)
    assert "actions/runs/77/artifacts?per_page=100" in calls
    assert "actions/runs/79/artifacts?per_page=100" not in calls


@pytest.mark.parametrize(
    "mutation",
    [{"conclusion": "failure"}, {"run_attempt": 2}, {"head_sha": "2" * 40},
     {"head_repository": {"full_name": "other/repository"}},
     {"path": ".github/workflows/other.yml"}, {"run_attempt": True}],
)
def test_terminal_product_state_target_must_still_be_successful(mutation):
    target, failed = _product_state_inventory_rows()
    target = {**target, **mutation}
    validate, _ = _product_state_inventory_boundary("terminal", [target, failed], {77: target, 78: failed})
    with pytest.raises(SystemExit, match="terminal_unique_run_identity_invalid"):
        validate()


@pytest.mark.parametrize(
    ("status", "conclusion"),
    [("completed", "failure"), ("in_progress", None)],
)
def test_actual_late_product_state_recheck_rejects_unsuccessful_target(status, conclusion):
    tree = _inline_tree()
    functions = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
        and node.name in {"fail", "require", "positive", "canonical", "same_fields",
                          "workflow_run", "unique_exact_source_workflow_run"}
    ]
    late_loop = next(
        node for node in tree.body if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Name) and node.iter.id == "late_specs"
    )
    target, failed = _product_state_inventory_rows()
    target = {**target, "status": status, "conclusion": conclusion}

    def api(endpoint, label):
        if endpoint.startswith("actions/workflows/"):
            return {"workflow_runs": [target, failed], "total_count": 2}
        return {77: target, 78: failed}[int(endpoint.split("/")[2])]

    namespace = {
        "MAX_SAFE": 9_007_199_254_740_991,
        "PurePosixPath": PurePosixPath, "quote": quote, "json": json,
        "source": "1" * 40, "repository": "owner/repository", "api": api,
        "late_specs": [(77, target["path"], target["name"], {"workflow_run"}, "product_state")],
    }
    with pytest.raises(SystemExit):
        exec(
            compile(ast.Module(body=functions + [late_loop], type_ignores=[]),
                    "<actual-late-product-state-recheck>", "exec"),
            namespace,
        )


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
def test_failed_sibling_policy_preserves_active_generator_candidate(boundary):
    target, _ = _product_state_inventory_rows()
    target = {
        **target, "path": ".github/workflows/current-main-evidence-index.yml",
        "name": "Current Main Evidence Index", "status": "in_progress", "conclusion": None,
    }
    validate, _ = _product_state_inventory_boundary(boundary, [target], {77: target})
    validate(path=target["path"], name=target["name"], completion_mode="active")


@pytest.mark.parametrize("boundary", ["privileged", "late_privileged", "terminal"])
def test_product_state_workflow_rejects_duplicate_failed_siblings_before_filtering(boundary):
    target, failed = _product_state_inventory_rows()
    validate, calls = _product_state_inventory_boundary(
        boundary, [target, failed, dict(failed)], {77: target, 78: failed},
    )
    with pytest.raises(SystemExit):
        validate()
    assert not any("/attempts/1" in endpoint for endpoint in calls)


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


def _product_archive(rows, *, compression=zipfile.ZIP_DEFLATED, mode=stat.S_IFREG):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression) as zipped:
        for name, raw in rows:
            entry = zipfile.ZipInfo(name)
            entry.compress_type = compression
            entry.external_attr = (mode | 0o644) << 16
            zipped.writestr(entry, raw)
    return archive.getvalue()


def _read_product_archive(raw, **options):
    return _inline_archive_namespace()["safe_archive"](
        raw,
        "product_state",
        **({
            "archive_limit": 1_000_000,
            "entries": 5,
            "member": 100_000,
            "total_limit": 100_000,
        } | options),
    )


def test_privileged_product_archive_preserves_exact_public_source_schema_bytes() -> None:
    source_path = (
        "src/structural_analysis/schemas/"
        "stateful_corotational_fiber_frame2d_checkpoint_v1.schema.json"
    )
    raw = (ROOT / source_path).read_bytes()
    # A JSONschema constraint is source data, not an attestation/run identifier.
    assert json.loads(raw)["properties"]["epoch"]["maximum"] == 2**64 - 1
    name = "source-snapshot/" + source_path
    archive = _product_archive([(name, raw)])
    with pytest.raises(SystemExit, match="unsafe_json_integer:product_state:"):
        _read_product_archive(archive)
    assert _read_product_archive(archive, validate_json_members=False) == {name: raw}


@pytest.mark.parametrize(
    "raw,error",
    [
        (b'{"run_id":9007199254740992}', "unsafe_json_integer"),
        (b'{"run_id":1,"run_id":2}', "duplicate_json_key"),
        (b'{"value":NaN}', "nonfinite_json_number"),
        (b'{"value":1e9999}', "nonfinite_json_number"),
    ],
)
def test_privileged_opaque_archive_does_not_validate_consumed_receipts(
    raw: bytes, error: str,
) -> None:
    archive = _product_archive([("receipt.json", raw)])
    with pytest.raises(SystemExit, match=error):
        _read_product_archive(archive)
    stored = _read_product_archive(archive, validate_json_members=False)
    assert stored == {"receipt.json": raw}
    # Byte admission never substitutes for the strict parser at receipt use.
    with pytest.raises(SystemExit, match=error):
        _inline_archive_namespace()["strict_json"](stored["receipt.json"], "consumed")


@pytest.mark.parametrize("policy", [None, 0, 1, "opaque"])
def test_privileged_archive_json_policy_requires_an_explicit_boolean(policy) -> None:
    with pytest.raises(SystemExit, match="archive_json_policy_invalid"):
        _read_product_archive(_product_archive([("receipt.json", b"{}")]),
                              validate_json_members=policy)


@pytest.mark.parametrize("validate_json_members", [True, False])
@pytest.mark.parametrize(
    "case,error",
    [
        ("traversal", "archive_member_path_invalid"),
        ("duplicate_alias", "archive_duplicate_member"),
        ("symlink", "archive_nonregular_member"),
        ("compression", "archive_compression_invalid"),
        ("ratio", "archive_compression_ratio_invalid"),
        ("member_limit", "archive_member_size_invalid"),
        ("total_limit", "archive_total_size_invalid"),
        ("entry_limit", "archive_entry_count_invalid"),
        ("archive_limit", "archive_size_invalid"),
        ("encrypted", "archive_encrypted_member"),
    ],
)
def test_privileged_opaque_archive_preserves_container_security(
    validate_json_members: bool, case: str, error: str,
) -> None:
    rows = [("receipt.json", b"{}")]
    options = {"validate_json_members": validate_json_members}
    compression = zipfile.ZIP_DEFLATED
    mode = stat.S_IFREG
    if case == "traversal":
        rows = [("../receipt.json", b"{}")]
    elif case == "duplicate_alias":
        rows = [("Receipt.json", b"{}"), ("receipt.json", b"{}")]
    elif case == "symlink":
        mode = stat.S_IFLNK
    elif case == "compression":
        compression = zipfile.ZIP_BZIP2
    elif case == "ratio":
        rows = [("source.txt", b"x" * 50_000)]
    elif case == "member_limit":
        options["member"] = 1
    elif case == "total_limit":
        rows = [("one.json", b"{}"), ("two.json", b"{}")]
        options["total_limit"] = 3
    elif case == "entry_limit":
        options["entries"] = 0
    elif case == "archive_limit":
        options["archive_limit"] = 22
    archive = _product_archive(rows, compression=compression, mode=mode)
    if case == "encrypted":
        archive = bytearray(archive)
        central = archive.index(b"PK\x01\x02")
        archive[central + 8:central + 10] = (1).to_bytes(2, "little")
        archive = bytes(archive)
    with pytest.raises(SystemExit, match=error):
        _read_product_archive(archive, **options)


def test_privileged_only_full_product_archive_copies_opt_into_opaque_bytes() -> None:
    tree = _inline_tree()
    opted_in = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not isinstance(call.func, ast.Name) or call.func.id != "safe_archive":
            continue
        policy = [kw.value for kw in call.keywords if kw.arg == "validate_json_members"]
        if policy:
            assert len(policy) == 1 and isinstance(policy[0], ast.Constant)
            assert policy[0].value is False
            assert len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
            assert isinstance(call.args[1], ast.Constant)
            assert node.targets[0].id not in opted_in
            opted_in[node.targets[0].id] = call.args[1].value
    assert opted_in == {
        "product_files": "product_state",
        "product_candidate_files": "product_state_candidate",
        "product_signed_files": "product_state_signed",
    }
    archive = next(node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name == "safe_archive")
    defaults = dict(zip((arg.arg for arg in archive.args.kwonlyargs),
                        archive.args.kw_defaults, strict=True))
    assert isinstance(defaults["validate_json_members"], ast.Constant)
    assert defaults["validate_json_members"].value is True


def test_privileged_consumed_json_still_uses_the_safe_integer_parser() -> None:
    tree = _inline_tree()
    strict = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "strict_json")
    json_loads = [node for node in ast.walk(tree)
                  if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                  and isinstance(node.func.value, ast.Name)
                  and node.func.value.id == "json" and node.func.attr == "loads"]
    assert len(json_loads) == 1 and json_loads[0] in list(ast.walk(strict))
    labels = {node.args[1].value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "strict_json" and len(node.args) >= 2
              and isinstance(node.args[1], ast.Constant)}
    assert {
        "product_state_seal", "product_state_candidate_artifact_api",
        "product_state_document", "product_state_provenance",
        "product_state_overlay_privileged_verification",
        "product_state_final_verification", "product_state_provenance_final_verification",
    } <= labels


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
