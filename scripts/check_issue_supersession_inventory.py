#!/usr/bin/env python3
"""Validate the tracked issue authority queue and optionally bind it to live GitHub."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = Path("artifacts/manifests/issue_supersession_inventory.json")
DEFAULT_SCHEMA = Path("canonical/issue-state-current.v1.schema.json")
INVENTORY_SCHEMA_VERSION = "structural-analysis-issue-supersession-inventory.v2"
REPORT_SCHEMA_VERSION = "issue-state-current.v1"
REPORT_PROFILE = "issue_state_current.v1"
EXPECTED_REPOSITORY = "betelgeuze-kang/Structural-Analysis"
EXPECTED_REPOSITORY_ID = 1136685613
EXPECTED_WORKFLOW_PATH = ".github/workflows/issue-state-current.yml"
EXPECTED_WORKFLOW_REF = (
    "betelgeuze-kang/Structural-Analysis/"
    ".github/workflows/issue-state-current.yml@refs/heads/main"
)
EXPECTED_SOURCE_REF = "refs/heads/main"
GITHUB_API_VERSION = "2022-11-28"
REQUIRED_WORKFLOW_CONCLUSION = "success"
WORKFLOW_GITHUB_SETTLE_ATTEMPTS = 4
WORKFLOW_GITHUB_SETTLE_DELAY_SECONDS = 2
MAX_GITHUB_SETTLE_ATTEMPTS = 5
MAX_GITHUB_SETTLE_DELAY_SECONDS = 5
EXPECTED_SCHEMA_SHA256 = (
    "sha256:6aeffb56a839b7777cfb7642dd1c631bd0f5060018e3f3c5667c2ddefd597c99"
)
CLAIM_BOUNDARY = (
    "This inventory and live report describe GitHub issue-state hygiene only. "
    "They do not prove solver accuracy, external V&V, design authority, legal "
    "rights, commercial authority, release eligibility, or product readiness."
)
EXTERNAL_CLASSIFICATIONS = {
    "comprehensive_external_validation",
    "external_platform_operator_user",
    "hardware_runner_operator",
    "independent_human_review",
    "legal_rights_holder",
    "licensed_corpus_validation",
    "repository_admin_policy",
}
FALSE_AUTHORITY = {
    "commercial_authority": False,
    "design_authority": False,
    "external_validation_authority": False,
    "numerical_authority": False,
    "release_authority": False,
}
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")
_RUN_ID_RE = re.compile(r"[1-9][0-9]*")
_TIMESTAMP_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_GITHUB_SETTLE_BLOCKERS = {
    "github_open_issue_count_mismatch",
    "github_open_issue_numbers_mismatch",
    "github_open_issue_projection_mismatch",
    "github_open_issue_projection_sha256_mismatch",
}
_INVENTORY_KEYS = {
    "schema_version",
    "repository",
    "observed_at",
    "observation_source",
    "observed_open_issue_count",
    "open_issue_numbers",
    "open_issue_projection_sha256",
    "open_issues",
    "implemented_but_open_issues",
    "orphan_issues",
    "resolved_issues",
    "superseded_pull_requests",
    "claims",
    "claim_boundary",
}
_OPEN_ISSUE_KEYS = {
    "number",
    "title",
    "state",
    "updated_at",
    "url",
    "body_sha256",
    "labels",
    "classification",
    "linked_pull_requests",
    "merged_implementation_pull_requests",
    "disposition",
    "required_external_inputs",
    "closable_by_repository_code_alone",
    "current_product_authority",
}
_RESOLVED_ISSUE_KEYS = {
    "merge_commit_sha",
    "normalization_comment_id",
    "number",
    "resolution",
    "resolved_by_pull_request",
    "state",
    "state_reason",
}
_SUPERSEDED_PULL_REQUEST_KEYS = {
    "disposition",
    "merged",
    "normalization_comment_id",
    "number",
    "state",
    "superseded_by_pull_request",
}
_CONSISTENCY_GATE_KEYS = {
    "inventory_bytes_sha256_match",
    "live_projection_exact_match",
    "open_issue_count_match",
    "open_issue_numbers_match",
    "projection_sha256_match",
}
_REPORT_TOP_KEYS = {
    "authority",
    "blockers",
    "claim_boundary",
    "consistency_gates",
    "contract_pass",
    "inventory",
    "live_github",
    "mode",
    "profile",
    "repository",
    "run_identity",
    "schema_version",
    "source",
    "status",
}
_RUN_IDENTITY_KEYS = {
    "artifact_prefix",
    "github_run_attempt",
    "github_run_id",
    "required_workflow_conclusion",
    "repository_id",
    "source_ref",
    "workflow_path",
    "workflow_ref",
    "workflow_sha",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _strict_json(raw: bytes, *, label: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError(f"duplicate_json_key:{label}:{key}")
            value[key] = item
        return value

    try:

        def finite_float(token: str) -> float:
            value = float(token)
            if not math.isfinite(value):
                raise ValueError(f"nonfinite_json_number:{label}:{token}")
            return value

        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=finite_float,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite_json_number:{label}:{token}")
            ),
        )
    except UnicodeError as exc:
        raise ValueError(f"json_not_utf8:{label}") from exc


def _validate_schema_contract(payload: Any) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError("issue_state_schema_object_required")
    expected_top = {
        "$schema",
        "$id",
        "$defs",
        "additionalProperties",
        "allOf",
        "properties",
        "required",
        "title",
        "type",
    }
    if set(payload) != expected_top:
        raise ValueError("issue_state_schema_shape_invalid")
    if payload.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("issue_state_schema_dialect_invalid")
    if (
        payload.get("type") != "object"
        or payload.get("additionalProperties") is not False
    ):
        raise ValueError("issue_state_schema_top_contract_invalid")
    required = payload.get("required")
    properties = payload.get("properties")
    if (
        not isinstance(required, list)
        or set(required) != _REPORT_TOP_KEYS
        or len(required) != len(_REPORT_TOP_KEYS)
        or not isinstance(properties, Mapping)
        or set(properties) != _REPORT_TOP_KEYS
    ):
        raise ValueError("issue_state_schema_top_keys_invalid")
    nested_keys = {
        "source": {"repository_commit_sha", "repository_tree_sha"},
        "run_identity": _RUN_IDENTITY_KEYS,
        "inventory": {
            "open_issue_count",
            "open_issue_numbers",
            "observed_at",
            "path",
            "projection_sha256",
            "sha256",
        },
        "live_github": {
            "api_endpoint",
            "exact_match",
            "open_issue_count",
            "open_issue_numbers",
            "projection_sha256",
            "verified",
        },
        "consistency_gates": _CONSISTENCY_GATE_KEYS,
        "authority": set(FALSE_AUTHORITY),
    }
    for key, expected in nested_keys.items():
        node = properties.get(key)
        if (
            not isinstance(node, Mapping)
            or node.get("type") != "object"
            or node.get("additionalProperties") is not False
            or not isinstance(node.get("required"), list)
            or set(node["required"]) != expected
            or len(node["required"]) != len(expected)
            or not isinstance(node.get("properties"), Mapping)
            or set(node["properties"]) != expected
        ):
            raise ValueError(f"issue_state_schema_nested_contract_invalid:{key}")
    authority = properties["authority"]["properties"]
    if any(authority.get(key) != {"const": False} for key in FALSE_AUTHORITY):
        raise ValueError("issue_state_schema_authority_invalid")
    if properties.get("claim_boundary") != {"const": CLAIM_BOUNDARY}:
        raise ValueError("issue_state_schema_claim_boundary_invalid")
    clauses = payload.get("allOf")
    if not isinstance(clauses, list):
        raise ValueError("issue_state_schema_conditions_invalid")
    pass_live_clause: Mapping[str, Any] | None = None
    for clause in clauses:
        if not isinstance(clause, Mapping):
            continue
        condition = clause.get("if")
        if not isinstance(condition, Mapping):
            continue
        condition_properties = condition.get("properties")
        if condition_properties == {
            "contract_pass": {"const": True},
            "mode": {"const": "live_exact_main"},
        } and set(condition.get("required", [])) == {"contract_pass", "mode"}:
            pass_live_clause = clause
            break
    if pass_live_clause is None:
        raise ValueError("issue_state_schema_pass_live_condition_missing")
    then_properties = pass_live_clause.get("then", {}).get("properties", {})
    if then_properties.get("live_github", {}).get("properties", {}).get(
        "exact_match"
    ) != {"const": True}:
        raise ValueError("issue_state_schema_exact_match_gate_invalid")
    gate_properties = then_properties.get("consistency_gates", {}).get("properties", {})
    if not isinstance(gate_properties, Mapping) or any(
        gate_properties.get(key) != {"const": True} for key in _CONSISTENCY_GATE_KEYS
    ):
        raise ValueError("issue_state_schema_consistency_gates_invalid")


def _load_schema_contract(path: Path) -> Mapping[str, Any]:
    raw = path.read_bytes()
    if _sha256_bytes(raw) != EXPECTED_SCHEMA_SHA256:
        raise ValueError("issue_state_schema_sha256_invalid")
    payload = _strict_json(raw, label="issue_state_schema")
    _validate_schema_contract(payload)
    return payload


def _rows(
    payload: Mapping[str, Any], key: str, blockers: list[str]
) -> list[dict[str, Any]]:
    value = payload.get(key)
    if not isinstance(value, list):
        blockers.append(f"{key}_missing")
        return []
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            blockers.append(f"{key}[{index}]_invalid")
            continue
        rows.append(row)
    return rows


def _projection_row(row: Mapping[str, Any], *, github_payload: bool) -> dict[str, Any]:
    labels = row.get("labels")
    if not isinstance(labels, list):
        labels = []
    if github_payload:
        label_names = []
        for label in labels:
            name = label.get("name") if isinstance(label, Mapping) else label
            if isinstance(name, str):
                label_names.append(name)
        body = row.get("body")
        body_text = body if isinstance(body, str) else ""
        body_sha256 = _sha256_bytes(body_text.encode("utf-8"))
        url = row.get("html_url", row.get("url"))
    else:
        label_names = [label for label in labels if isinstance(label, str)]
        body_sha256 = row.get("body_sha256")
        url = row.get("url")
    return {
        "body_sha256": body_sha256,
        "labels": sorted(set(label_names)),
        "number": row.get("number"),
        "state": row.get("state"),
        "title": row.get("title"),
        "updated_at": row.get("updated_at"),
        "url": url,
    }


def issue_projection(
    rows: Iterable[Mapping[str, Any]],
    *,
    github_payload: bool = False,
) -> list[dict[str, Any]]:
    projected = [
        _projection_row(row, github_payload=github_payload)
        for row in rows
        if not github_payload or not row.get("is_pull_request", row.get("pull_request"))
    ]
    return sorted(
        projected,
        key=lambda row: (
            row.get("number") if type(row.get("number")) is int else 0,
            str(row),
        ),
    )


def projection_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_bytes(_canonical_bytes(list(rows)))


def _git_value(repo_root: Path, expression: str) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", expression],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    value = completed.stdout.strip()
    if completed.returncode != 0 or _COMMIT_RE.fullmatch(value) is None:
        raise ValueError(f"git_identity_unavailable:{expression}")
    return value


def _git_blob(repo_root: Path, source_sha: str, path: Path) -> bytes:
    completed = subprocess.run(
        ["git", "show", f"{source_sha}:{path.as_posix()}"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise ValueError(f"git_blob_unavailable:{path.as_posix()}")
    return completed.stdout


def _fetch_github_open_issues(
    repository: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> list[dict[str, Any]]:
    endpoint = f"repos/{repository}/issues?state=open&per_page=100"
    jq_filter = (
        ".[] | {number,title,state,updated_at,url:.html_url,body,"
        'labels:[.labels[].name],is_pull_request:has("pull_request")} | @json'
    )
    completed = runner(
        [
            "gh",
            "api",
            endpoint,
            "-H",
            f"X-GitHub-Api-Version: {GITHUB_API_VERSION}",
            "--paginate",
            "--jq",
            jq_filter,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise ValueError("github_issue_query_failed")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(completed.stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"github_issue_query_invalid_json:{line_number}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"github_issue_query_invalid_row:{line_number}")
        if row.get("is_pull_request") is True:
            continue
        rows.append(row)
    return rows


def _validate_github_settle_policy(attempts: int, delay_seconds: int) -> None:
    if (
        type(attempts) is not int
        or attempts < 1
        or attempts > MAX_GITHUB_SETTLE_ATTEMPTS
    ):
        raise ValueError("github_settle_attempts_invalid")
    if (
        type(delay_seconds) is not int
        or delay_seconds < 0
        or delay_seconds > MAX_GITHUB_SETTLE_DELAY_SECONDS
    ):
        raise ValueError("github_settle_delay_invalid")


def _build_exact_live_report_with_retry(
    *,
    repository: str,
    report_builder: Callable[[Sequence[Mapping[str, Any]]], dict[str, Any]],
    attempts: int,
    delay_seconds: int,
    fetcher: Callable[[str], list[dict[str, Any]]] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Requery a short-lived GitHub close transition and return only exact truth."""

    _validate_github_settle_policy(attempts, delay_seconds)
    live_fetcher = _fetch_github_open_issues if fetcher is None else fetcher
    wait = time.sleep if sleeper is None else sleeper
    last_reason = "github_issue_query_failed"
    for attempt in range(1, attempts + 1):
        try:
            live_rows = live_fetcher(repository)
        except (OSError, ValueError, subprocess.SubprocessError):
            last_reason = "github_issue_query_failed"
        else:
            report = report_builder(live_rows)
            live = report.get("live_github")
            if (
                report.get("contract_pass") is True
                and isinstance(live, Mapping)
                and live.get("exact_match") is True
            ):
                return report
            blockers = report.get("blockers")
            if (
                not isinstance(blockers, list)
                or not blockers
                or any(not isinstance(value, str) for value in blockers)
                or not set(blockers).issubset(_GITHUB_SETTLE_BLOCKERS)
            ):
                raise ValueError("github_live_report_nonretryable")
            last_reason = ",".join(sorted(blockers))
        if attempt < attempts:
            wait(delay_seconds)
    raise ValueError(f"github_issue_settle_exhausted:{attempts}:{last_reason}")


def _validate_open_rows(
    rows: Sequence[Mapping[str, Any]],
    blockers: list[str],
) -> tuple[list[int], list[dict[str, Any]]]:
    numbers: list[int] = []
    seen: set[int] = set()
    for row in rows:
        number = row.get("number")
        if type(number) is not int or number <= 0 or number in seen:
            blockers.append(f"open_issue_number_invalid_or_duplicate:{number}")
            continue
        seen.add(number)
        numbers.append(number)
        if set(row) != _OPEN_ISSUE_KEYS:
            blockers.append(f"open_issue_shape_invalid:{number}")
        projection = _projection_row(row, github_payload=False)
        if projection["state"] != "open":
            blockers.append(f"non_open_issue_in_open_inventory:{number}")
        if not isinstance(projection["title"], str) or not projection["title"].strip():
            blockers.append(f"open_issue_title_invalid:{number}")
        if (
            not isinstance(projection["updated_at"], str)
            or _TIMESTAMP_RE.fullmatch(projection["updated_at"]) is None
        ):
            blockers.append(f"open_issue_updated_at_invalid:{number}")
        if projection["url"] != (
            f"https://github.com/{EXPECTED_REPOSITORY}/issues/{number}"
        ):
            blockers.append(f"open_issue_url_invalid:{number}")
        if not _valid_hash(projection["body_sha256"]):
            blockers.append(f"open_issue_body_sha256_invalid:{number}")
        labels = row.get("labels")
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or not label for label in labels
        ):
            blockers.append(f"open_issue_labels_invalid:{number}")
        elif labels != sorted(set(labels)):
            blockers.append(f"open_issue_labels_invalid:{number}")
        if row.get("classification") not in EXTERNAL_CLASSIFICATIONS:
            blockers.append(f"open_issue_classification_invalid:{number}")
        if row.get("closable_by_repository_code_alone") is not False:
            blockers.append(f"open_issue_repository_closure_boundary_invalid:{number}")
        if row.get("current_product_authority") is not False:
            blockers.append(f"open_issue_product_authority_invalid:{number}")
        if (
            not isinstance(row.get("disposition"), str)
            or not row["disposition"].strip()
        ):
            blockers.append(f"open_issue_disposition_missing:{number}")
        external_inputs = row.get("required_external_inputs")
        if (
            not isinstance(external_inputs, list)
            or not external_inputs
            or any(not isinstance(value, str) or not value for value in external_inputs)
        ):
            blockers.append(f"open_issue_external_inputs_invalid:{number}")
        elif external_inputs != sorted(set(external_inputs)):
            blockers.append(f"open_issue_external_inputs_invalid:{number}")
        for link_key in ("linked_pull_requests", "merged_implementation_pull_requests"):
            links = row.get(link_key)
            if not isinstance(links, list) or any(
                type(value) is not int or value <= 0 for value in links
            ):
                blockers.append(f"{link_key}_invalid:{number}")
            elif links != sorted(set(links)):
                blockers.append(f"{link_key}_invalid:{number}")
        linked = row.get("linked_pull_requests")
        merged = row.get("merged_implementation_pull_requests")
        if (
            isinstance(linked, list)
            and isinstance(merged, list)
            and all(type(value) is int and value > 0 for value in linked + merged)
            and not set(merged).issubset(linked)
        ):
            blockers.append(f"merged_pull_request_not_linked:{number}")
    if numbers != sorted(numbers):
        blockers.append("open_issue_order_invalid")
    return sorted(numbers), issue_projection(rows)


def _validate_historical_rows(
    payload: Mapping[str, Any], blockers: list[str]
) -> tuple[set[int], set[int]]:
    resolved = _rows(payload, "resolved_issues", blockers)
    superseded = _rows(payload, "superseded_pull_requests", blockers)
    seen_resolved: set[int] = set()
    for row in resolved:
        number = row.get("number")
        if set(row) != _RESOLVED_ISSUE_KEYS:
            blockers.append(f"resolved_issue_shape_invalid:{number}")
        if type(number) is not int or number <= 0 or number in seen_resolved:
            blockers.append(f"resolved_issue_number_invalid_or_duplicate:{number}")
            continue
        seen_resolved.add(number)
        if row.get("state") != "closed" or row.get("state_reason") != "completed":
            blockers.append(f"resolved_issue_not_completed:{number}")
        if row.get("resolution") != "resolved_by":
            blockers.append(f"resolved_issue_disposition_missing:{number}")
        resolved_by = row.get("resolved_by_pull_request")
        if type(resolved_by) is not int or resolved_by <= 0:
            blockers.append(f"resolved_issue_pull_request_missing:{number}")
        merge_sha = row.get("merge_commit_sha")
        if not isinstance(merge_sha, str) or _COMMIT_RE.fullmatch(merge_sha) is None:
            blockers.append(f"resolved_issue_merge_sha_invalid:{number}")
        comment_id = row.get("normalization_comment_id")
        if type(comment_id) is not int or comment_id <= 0:
            blockers.append(f"resolved_issue_comment_missing:{number}")
    seen_prs: set[int] = set()
    for row in superseded:
        number = row.get("number")
        if set(row) != _SUPERSEDED_PULL_REQUEST_KEYS:
            blockers.append(f"superseded_pr_shape_invalid:{number}")
        if type(number) is not int or number <= 0 or number in seen_prs:
            blockers.append(f"superseded_pr_number_invalid_or_duplicate:{number}")
            continue
        seen_prs.add(number)
        if row.get("state") != "closed" or row.get("merged") is not False:
            blockers.append(f"superseded_pr_state_invalid:{number}")
        if row.get("disposition") != "superseded":
            blockers.append(f"superseded_pr_disposition_missing:{number}")
        superseded_by = row.get("superseded_by_pull_request")
        if type(superseded_by) is not int or superseded_by <= 0:
            blockers.append(f"superseding_pr_missing:{number}")
        comment_id = row.get("normalization_comment_id")
        if type(comment_id) is not int or comment_id <= 0:
            blockers.append(f"supersession_comment_missing:{number}")
    resolved_numbers = [
        row.get("number") for row in resolved if type(row.get("number")) is int
    ]
    superseded_numbers = [
        row.get("number") for row in superseded if type(row.get("number")) is int
    ]
    if resolved_numbers != sorted(resolved_numbers):
        blockers.append("resolved_issue_order_invalid")
    if superseded_numbers != sorted(superseded_numbers):
        blockers.append("superseded_pr_order_invalid")
    return seen_resolved, seen_prs


def _validate_inventory_contract(
    raw_inventory: bytes,
) -> tuple[
    Mapping[str, Any],
    list[dict[str, Any]],
    list[int],
    list[dict[str, Any]],
    str,
    list[str],
]:
    payload = _strict_json(raw_inventory, label="issue_inventory")
    if not isinstance(payload, dict):
        raise ValueError("issue_inventory_object_required")
    blockers: list[str] = []
    if set(payload) != _INVENTORY_KEYS:
        blockers.append("inventory_shape_invalid")
    if payload.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        blockers.append("inventory_schema_version_invalid")
    if payload.get("repository") != EXPECTED_REPOSITORY:
        blockers.append("inventory_repository_invalid")
    if payload.get("claims") != FALSE_AUTHORITY:
        blockers.append("inventory_authority_claims_invalid")
    observed_at = payload.get("observed_at")
    if not isinstance(observed_at, str) or _TIMESTAMP_RE.fullmatch(observed_at) is None:
        blockers.append("inventory_observed_at_invalid")
    if payload.get("observation_source") != "gh_cli_read_only_current_github_state":
        blockers.append("inventory_observation_source_invalid")
    if payload.get("claim_boundary") != CLAIM_BOUNDARY:
        blockers.append("inventory_claim_boundary_invalid")

    open_issues = _rows(payload, "open_issues", blockers)
    numbers, embedded_projection = _validate_open_rows(open_issues, blockers)
    observed_count = payload.get("observed_open_issue_count")
    if type(observed_count) is not int or observed_count != len(open_issues):
        blockers.append("open_issue_inventory_incomplete")
    declared_numbers = payload.get("open_issue_numbers")
    if (
        not isinstance(declared_numbers, list)
        or any(type(number) is not int or number <= 0 for number in declared_numbers)
        or declared_numbers != numbers
    ):
        blockers.append("open_issue_numbers_inconsistent")
    embedded_projection_sha256 = projection_sha256(embedded_projection)
    if payload.get("open_issue_projection_sha256") != embedded_projection_sha256:
        blockers.append("open_issue_projection_sha256_mismatch")
    if _rows(payload, "implemented_but_open_issues", blockers):
        blockers.append("implemented_but_open_issues_must_be_empty_for_external_queue")
    if _rows(payload, "orphan_issues", blockers):
        blockers.append("orphan_issues_must_be_empty")
    resolved_numbers, superseded_numbers = _validate_historical_rows(payload, blockers)
    overlap = sorted(set(numbers) & resolved_numbers)
    if overlap:
        blockers.append("open_resolved_issue_overlap:" + ",".join(map(str, overlap)))
    cross_family_overlap = sorted(
        (set(numbers) | resolved_numbers) & superseded_numbers
    )
    if cross_family_overlap:
        blockers.append(
            "issue_pull_request_number_overlap:"
            + ",".join(map(str, cross_family_overlap))
        )
    return (
        payload,
        open_issues,
        numbers,
        embedded_projection,
        embedded_projection_sha256,
        sorted(set(blockers)),
    )


def build_report(
    repo_root: Path = ROOT,
    *,
    inventory_path: Path = DEFAULT_INVENTORY,
    inventory_raw: bytes | None = None,
    schema_path: Path = DEFAULT_SCHEMA,
    live_rows: Sequence[Mapping[str, Any]] | None = None,
    expected_source_sha: str | None = None,
    expected_source_tree_sha: str | None = None,
    expected_repository: str | None = None,
    repository_id: int | None = None,
    workflow_path: str | None = None,
    workflow_ref: str | None = None,
    workflow_sha: str | None = None,
    source_ref: str | None = None,
    github_run_id: str | None = None,
    github_run_attempt: int | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    path = (
        inventory_path if inventory_path.is_absolute() else repo_root / inventory_path
    )
    resolved_schema_path = (
        schema_path if schema_path.is_absolute() else repo_root / schema_path
    )
    _load_schema_contract(resolved_schema_path)
    raw_inventory = path.read_bytes() if inventory_raw is None else inventory_raw
    (
        payload,
        open_issues,
        numbers,
        embedded_projection,
        embedded_projection_sha256,
        blockers,
    ) = _validate_inventory_contract(raw_inventory)
    repository = EXPECTED_REPOSITORY

    source_sha = _git_value(repo_root, "HEAD")
    source_tree_sha = _git_value(repo_root, "HEAD^{tree}")
    if expected_source_sha is not None:
        if _COMMIT_RE.fullmatch(expected_source_sha) is None:
            blockers.append("expected_source_sha_invalid")
        elif source_sha != expected_source_sha:
            blockers.append("source_sha_not_expected_head")
    if expected_source_tree_sha is not None:
        if _COMMIT_RE.fullmatch(expected_source_tree_sha) is None:
            blockers.append("expected_source_tree_sha_invalid")
        elif source_tree_sha != expected_source_tree_sha:
            blockers.append("source_tree_sha_not_expected_head")

    live_verified = live_rows is not None
    live_projection: list[dict[str, Any]] = []
    live_projection_sha256: str | None = None
    live_numbers: list[int] = []
    live_exact_match: bool | None = None
    count_match: bool | None = None
    numbers_match: bool | None = None
    projection_hash_match: bool | None = None
    if live_rows is not None:
        live_projection = issue_projection(live_rows, github_payload=True)
        live_projection_sha256 = projection_sha256(live_projection)
        live_numbers = [
            int(row["number"])
            for row in live_projection
            if isinstance(row.get("number"), int)
        ]
        live_exact_match = live_projection == embedded_projection
        count_match = len(live_projection) == len(open_issues)
        numbers_match = live_numbers == numbers
        projection_hash_match = live_projection_sha256 == embedded_projection_sha256
        if not live_exact_match:
            blockers.append("github_open_issue_projection_mismatch")
        if not count_match:
            blockers.append("github_open_issue_count_mismatch")
        if not numbers_match:
            blockers.append("github_open_issue_numbers_mismatch")
        if not projection_hash_match:
            blockers.append("github_open_issue_projection_sha256_mismatch")

    if live_verified:
        if expected_source_sha is None:
            blockers.append("expected_source_sha_missing")
        if expected_source_tree_sha is None:
            blockers.append("expected_source_tree_sha_missing")
        if expected_repository != EXPECTED_REPOSITORY:
            blockers.append("repository_identity_invalid")
        if type(repository_id) is not int or repository_id != EXPECTED_REPOSITORY_ID:
            blockers.append("repository_id_invalid")
        if workflow_path != EXPECTED_WORKFLOW_PATH:
            blockers.append("workflow_path_invalid")
        if workflow_ref != EXPECTED_WORKFLOW_REF:
            blockers.append("workflow_ref_invalid")
        if (
            not isinstance(workflow_sha, str)
            or _COMMIT_RE.fullmatch(workflow_sha) is None
            or workflow_sha != source_sha
        ):
            blockers.append("workflow_sha_invalid")
        if source_ref != EXPECTED_SOURCE_REF:
            blockers.append("source_ref_invalid")
        if (
            not isinstance(github_run_id, str)
            or _RUN_ID_RE.fullmatch(github_run_id) is None
        ):
            blockers.append("github_run_id_invalid")
        if (
            type(github_run_attempt) is bool
            or not isinstance(github_run_attempt, int)
            or github_run_attempt <= 0
        ):
            blockers.append("github_run_attempt_invalid")
    artifact_prefix = None
    if (
        live_verified
        and isinstance(github_run_id, str)
        and _RUN_ID_RE.fullmatch(github_run_id) is not None
        and isinstance(github_run_attempt, int)
        and not isinstance(github_run_attempt, bool)
        and github_run_attempt > 0
    ):
        artifact_prefix = (
            f"issue-state-current-{source_sha}-{github_run_id}-{github_run_attempt}"
        )

    blockers = sorted(set(blockers))
    contract_pass = not blockers
    try:
        inventory_display_path = path.relative_to(repo_root).as_posix()
    except ValueError:
        inventory_display_path = path.as_posix()
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "profile": REPORT_PROFILE,
        "status": "pass" if contract_pass else "blocked",
        "contract_pass": contract_pass,
        "mode": "live_exact_main" if live_verified else "offline_inventory",
        "repository": repository,
        "source": {
            "repository_commit_sha": source_sha,
            "repository_tree_sha": source_tree_sha,
        },
        "run_identity": {
            "github_run_id": github_run_id,
            "github_run_attempt": github_run_attempt,
            "artifact_prefix": artifact_prefix,
            "repository_id": repository_id if live_verified else None,
            "required_workflow_conclusion": (
                REQUIRED_WORKFLOW_CONCLUSION if live_verified else None
            ),
            "workflow_path": workflow_path if live_verified else None,
            "workflow_ref": workflow_ref if live_verified else None,
            "workflow_sha": workflow_sha if live_verified else None,
            "source_ref": source_ref if live_verified else None,
        },
        "inventory": {
            "path": inventory_display_path,
            "sha256": _sha256_bytes(raw_inventory),
            "observed_at": payload.get("observed_at"),
            "open_issue_count": len(open_issues),
            "open_issue_numbers": numbers,
            "projection_sha256": embedded_projection_sha256,
        },
        "live_github": {
            "verified": live_verified,
            "exact_match": live_exact_match,
            "api_endpoint": f"repos/{repository}/issues?state=open&per_page=100",
            "open_issue_count": len(live_projection) if live_verified else None,
            "open_issue_numbers": live_numbers if live_verified else [],
            "projection_sha256": live_projection_sha256,
        },
        "consistency_gates": {
            "inventory_bytes_sha256_match": True if live_verified else None,
            "live_projection_exact_match": live_exact_match,
            "open_issue_count_match": count_match,
            "open_issue_numbers_match": numbers_match,
            "projection_sha256_match": projection_hash_match,
        },
        "authority": dict(FALSE_AUTHORITY),
        "blockers": blockers,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def validate_live_report(
    payload: Mapping[str, Any],
    *,
    inventory_raw: bytes,
    expected_source_sha: str,
    expected_source_tree_sha: str,
    expected_repository: str,
    expected_repository_id: int,
    expected_workflow_path: str,
    expected_workflow_ref: str,
    expected_workflow_sha: str,
    expected_source_ref: str,
    expected_run_id: str,
    expected_run_attempt: int,
) -> None:
    if expected_repository != EXPECTED_REPOSITORY:
        raise ValueError("issue_state_expected_repository_invalid")
    if (
        type(expected_repository_id) is not int
        or expected_repository_id != EXPECTED_REPOSITORY_ID
    ):
        raise ValueError("issue_state_expected_repository_id_invalid")
    if expected_workflow_path != EXPECTED_WORKFLOW_PATH:
        raise ValueError("issue_state_expected_workflow_path_invalid")
    if expected_workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ValueError("issue_state_expected_workflow_ref_invalid")
    if expected_source_ref != EXPECTED_SOURCE_REF:
        raise ValueError("issue_state_expected_source_ref_invalid")
    if (
        _COMMIT_RE.fullmatch(expected_source_sha) is None
        or _COMMIT_RE.fullmatch(expected_source_tree_sha) is None
        or _COMMIT_RE.fullmatch(expected_workflow_sha) is None
        or expected_workflow_sha != expected_source_sha
    ):
        raise ValueError("issue_state_expected_source_identity_invalid")
    if _RUN_ID_RE.fullmatch(expected_run_id) is None:
        raise ValueError("issue_state_expected_run_id_invalid")
    if type(expected_run_attempt) is not int or expected_run_attempt <= 0:
        raise ValueError("issue_state_expected_run_attempt_invalid")
    if set(payload) != _REPORT_TOP_KEYS:
        raise ValueError("issue_state_report_shape_invalid")
    if payload.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("issue_state_report_schema_version_invalid")
    if payload.get("profile") != REPORT_PROFILE:
        raise ValueError("issue_state_report_profile_invalid")
    if payload.get("status") != "pass" or payload.get("contract_pass") is not True:
        raise ValueError("issue_state_report_not_passed")
    if payload.get("mode") != "live_exact_main":
        raise ValueError("issue_state_report_mode_invalid")
    if payload.get("repository") != EXPECTED_REPOSITORY:
        raise ValueError("issue_state_report_repository_invalid")
    if payload.get("claim_boundary") != CLAIM_BOUNDARY:
        raise ValueError("issue_state_report_claim_boundary_invalid")
    if payload.get("authority") != FALSE_AUTHORITY:
        raise ValueError("issue_state_report_authority_invalid")
    if payload.get("blockers") != []:
        raise ValueError("issue_state_report_blockers_invalid")
    source = payload.get("source")
    if not isinstance(source, Mapping) or set(source) != {
        "repository_commit_sha",
        "repository_tree_sha",
    }:
        raise ValueError("issue_state_report_source_invalid")
    if any(
        not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None
        for value in source.values()
    ):
        raise ValueError("issue_state_report_source_identity_invalid")
    if source != {
        "repository_commit_sha": expected_source_sha,
        "repository_tree_sha": expected_source_tree_sha,
    }:
        raise ValueError("issue_state_report_source_selector_mismatch")
    run_identity = payload.get("run_identity")
    if not isinstance(run_identity, Mapping) or set(run_identity) != _RUN_IDENTITY_KEYS:
        raise ValueError("issue_state_report_run_identity_invalid")
    run_id = run_identity.get("github_run_id")
    run_attempt = run_identity.get("github_run_attempt")
    if not isinstance(run_id, str) or _RUN_ID_RE.fullmatch(run_id) is None:
        raise ValueError("issue_state_report_run_id_invalid")
    if (
        type(run_attempt) is bool
        or not isinstance(run_attempt, int)
        or run_attempt <= 0
    ):
        raise ValueError("issue_state_report_run_attempt_invalid")
    expected_prefix = (
        f"issue-state-current-{expected_source_sha}-{expected_run_id}-"
        f"{expected_run_attempt}"
    )
    if run_identity.get("artifact_prefix") != expected_prefix:
        raise ValueError("issue_state_report_artifact_prefix_invalid")
    if run_identity != {
        "artifact_prefix": expected_prefix,
        "github_run_attempt": expected_run_attempt,
        "github_run_id": expected_run_id,
        "repository_id": expected_repository_id,
        "required_workflow_conclusion": REQUIRED_WORKFLOW_CONCLUSION,
        "source_ref": expected_source_ref,
        "workflow_path": expected_workflow_path,
        "workflow_ref": expected_workflow_ref,
        "workflow_sha": expected_workflow_sha,
    }:
        raise ValueError("issue_state_report_run_selector_mismatch")
    live = payload.get("live_github")
    inventory = payload.get("inventory")
    if not isinstance(live, Mapping) or not isinstance(inventory, Mapping):
        raise ValueError("issue_state_report_projection_invalid")
    if set(inventory) != {
        "path",
        "sha256",
        "observed_at",
        "open_issue_count",
        "open_issue_numbers",
        "projection_sha256",
    } or set(live) != {
        "verified",
        "exact_match",
        "api_endpoint",
        "open_issue_count",
        "open_issue_numbers",
        "projection_sha256",
    }:
        raise ValueError("issue_state_report_projection_shape_invalid")
    if inventory.get("path") != DEFAULT_INVENTORY.as_posix():
        raise ValueError("issue_state_report_inventory_path_invalid")
    if (
        not isinstance(inventory.get("observed_at"), str)
        or _TIMESTAMP_RE.fullmatch(inventory["observed_at"]) is None
    ):
        raise ValueError("issue_state_report_observed_at_invalid")
    if live.get("api_endpoint") != (
        f"repos/{EXPECTED_REPOSITORY}/issues?state=open&per_page=100"
    ):
        raise ValueError("issue_state_report_api_endpoint_invalid")
    if live.get("verified") is not True or live.get("exact_match") is not True:
        raise ValueError("issue_state_report_live_match_invalid")
    inventory_numbers = inventory.get("open_issue_numbers")
    live_numbers = live.get("open_issue_numbers")
    if (
        not isinstance(inventory_numbers, list)
        or any(type(number) is not int or number <= 0 for number in inventory_numbers)
        or inventory_numbers != sorted(set(inventory_numbers))
        or not isinstance(live_numbers, list)
        or any(type(number) is not int or number <= 0 for number in live_numbers)
        or live_numbers != sorted(set(live_numbers))
    ):
        raise ValueError("issue_state_report_issue_number_shape_invalid")
    for count in (inventory.get("open_issue_count"), live.get("open_issue_count")):
        if type(count) is not int or count < 0:
            raise ValueError("issue_state_report_issue_count_shape_invalid")
    if live.get("open_issue_numbers") != inventory.get("open_issue_numbers"):
        raise ValueError("issue_state_report_issue_numbers_invalid")
    if live.get("open_issue_count") != inventory.get("open_issue_count"):
        raise ValueError("issue_state_report_issue_count_invalid")
    if inventory.get("open_issue_count") != len(inventory_numbers):
        raise ValueError("issue_state_report_issue_count_inconsistent")
    if live.get("projection_sha256") != inventory.get("projection_sha256"):
        raise ValueError("issue_state_report_projection_hash_invalid")
    for value in (
        inventory.get("sha256"),
        inventory.get("projection_sha256"),
        live.get("projection_sha256"),
    ):
        if not _valid_hash(value):
            raise ValueError("issue_state_report_hash_invalid")
    (
        companion,
        _open_rows,
        companion_numbers,
        _companion_projection,
        companion_projection_sha256,
        companion_blockers,
    ) = _validate_inventory_contract(inventory_raw)
    if companion_blockers:
        raise ValueError(
            "issue_state_report_companion_inventory_invalid:"
            + ",".join(companion_blockers)
        )
    if inventory.get("sha256") != _sha256_bytes(inventory_raw):
        raise ValueError("issue_state_report_inventory_bytes_sha256_mismatch")
    if inventory.get("observed_at") != companion.get("observed_at"):
        raise ValueError("issue_state_report_inventory_observed_at_mismatch")
    if inventory.get("open_issue_numbers") != companion_numbers:
        raise ValueError("issue_state_report_inventory_numbers_mismatch")
    if inventory.get("open_issue_count") != len(companion_numbers):
        raise ValueError("issue_state_report_inventory_count_mismatch")
    if inventory.get("projection_sha256") != companion_projection_sha256:
        raise ValueError("issue_state_report_inventory_projection_mismatch")
    gates = payload.get("consistency_gates")
    if (
        not isinstance(gates, Mapping)
        or set(gates) != _CONSISTENCY_GATE_KEYS
        or any(gates.get(key) is not True for key in _CONSISTENCY_GATE_KEYS)
    ):
        raise ValueError("issue_state_report_consistency_gates_invalid")


def _write_atomic_portable(path: Path, raw: bytes) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("issue_state_output_parent_invalid")
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("issue_state_output_leaf_invalid")
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        try:
            offset = 0
            while offset < len(raw):
                written = os.write(descriptor, raw[offset:])
                if written <= 0:
                    raise OSError("issue_state_output_short_write")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            temporary.unlink()


def _write_atomic_posix(path: Path, raw: bytes) -> None:
    absolute = Path(os.path.abspath(path))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    parent_fd = os.open(absolute.anchor, directory_flags)
    temporary_name: str | None = None
    descriptor: int | None = None
    try:
        for part in absolute.parent.parts[1:]:
            try:
                next_fd = os.open(
                    part,
                    directory_flags | nofollow,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise ValueError(f"issue_state_output_parent_invalid:{part}") from exc
            os.close(parent_fd)
            parent_fd = next_fd
        try:
            metadata = os.stat(
                absolute.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("issue_state_output_leaf_invalid")
        for counter in range(100):
            candidate = f".{absolute.name}.{os.getpid()}.{counter}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow,
                    0o600,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor is None or temporary_name is None:
            raise ValueError("issue_state_output_temporary_name_exhausted")
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                raise OSError("issue_state_output_short_write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            absolute.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


def _write_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    absolute = Path(os.path.abspath(path))
    if os.name == "posix":
        _write_atomic_posix(absolute, raw)
    else:  # pragma: no cover - exercised by the Windows CI matrix
        _write_atomic_portable(absolute, raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--verify-github", action="store_true")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-source-tree-sha")
    parser.add_argument("--repository")
    parser.add_argument("--repository-id", type=int)
    parser.add_argument("--workflow-path")
    parser.add_argument("--workflow-ref")
    parser.add_argument("--workflow-sha")
    parser.add_argument("--source-ref")
    parser.add_argument("--github-run-id")
    parser.add_argument("--github-run-attempt", type=int)
    parser.add_argument("--github-settle-attempts", type=int)
    parser.add_argument("--github-settle-delay-seconds", type=int)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check-report", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    identity_values = {
        "--expected-source-sha": args.expected_source_sha,
        "--expected-source-tree-sha": args.expected_source_tree_sha,
        "--repository": args.repository,
        "--repository-id": args.repository_id,
        "--workflow-path": args.workflow_path,
        "--workflow-ref": args.workflow_ref,
        "--workflow-sha": args.workflow_sha,
        "--source-ref": args.source_ref,
        "--github-run-id": args.github_run_id,
        "--github-run-attempt": args.github_run_attempt,
    }
    missing_identity = [key for key, value in identity_values.items() if value is None]
    settle_values = {
        "--github-settle-attempts": args.github_settle_attempts,
        "--github-settle-delay-seconds": args.github_settle_delay_seconds,
    }
    missing_settle = [key for key, value in settle_values.items() if value is None]
    if (args.verify_github or args.check_report is not None) and missing_identity:
        parser.error(
            "live build/check requires selectors: " + ", ".join(missing_identity)
        )
    if args.verify_github and args.out is None:
        parser.error("--verify-github requires --out")
    if args.verify_github and missing_settle:
        parser.error(
            "--verify-github requires bounded retry selectors: "
            + ", ".join(missing_settle)
        )
    if not args.verify_github and any(
        value is not None for value in settle_values.values()
    ):
        parser.error("only --verify-github accepts bounded retry selectors")
    if args.verify_github and args.out is not None and os.path.lexists(args.out):
        parser.error("--verify-github requires an absent --out target")
    if args.check_report is not None and (
        args.verify_github or args.out is not None or args.json
    ):
        parser.error("--check-report rejects --verify-github, --out, and --json")
    if (
        not args.verify_github
        and args.check_report is None
        and any(value is not None for value in identity_values.values())
    ):
        parser.error("offline inventory mode rejects live identity selectors")
    inventory_path = (
        args.inventory
        if args.inventory.is_absolute()
        else args.repo_root.resolve() / args.inventory
    )
    schema_path = (
        args.schema
        if args.schema.is_absolute()
        else args.repo_root.resolve() / args.schema
    )
    try:
        if args.verify_github:
            _validate_github_settle_policy(
                args.github_settle_attempts,
                args.github_settle_delay_seconds,
            )
        _load_schema_contract(schema_path)
        inventory_raw = inventory_path.read_bytes()
        inventory_contract = _validate_inventory_contract(inventory_raw)
        if inventory_contract[-1]:
            raise ValueError(
                "issue_inventory_contract_invalid:" + ",".join(inventory_contract[-1])
            )
        if args.check_report is not None:
            payload = _strict_json(
                args.check_report.read_bytes(), label="issue_state_report"
            )
            if not isinstance(payload, dict):
                raise ValueError("issue_state_report_object_required")
            actual_source_sha = _git_value(args.repo_root, "HEAD")
            actual_source_tree_sha = _git_value(args.repo_root, "HEAD^{tree}")
            if (
                actual_source_sha != args.expected_source_sha
                or actual_source_tree_sha != args.expected_source_tree_sha
            ):
                raise ValueError("issue_state_check_checkout_identity_mismatch")
            if inventory_raw != _git_blob(
                args.repo_root, args.expected_source_sha, DEFAULT_INVENTORY
            ):
                raise ValueError("issue_state_companion_inventory_source_mismatch")
            if schema_path.read_bytes() != _git_blob(
                args.repo_root, args.expected_source_sha, DEFAULT_SCHEMA
            ):
                raise ValueError("issue_state_companion_schema_source_mismatch")
            validate_live_report(
                payload,
                inventory_raw=inventory_raw,
                expected_source_sha=args.expected_source_sha,
                expected_source_tree_sha=args.expected_source_tree_sha,
                expected_repository=args.repository,
                expected_repository_id=args.repository_id,
                expected_workflow_path=args.workflow_path,
                expected_workflow_ref=args.workflow_ref,
                expected_workflow_sha=args.workflow_sha,
                expected_source_ref=args.source_ref,
                expected_run_id=args.github_run_id,
                expected_run_attempt=args.github_run_attempt,
            )
            print("issue state current report: pass")
            return 0
        if args.verify_github:
            if (
                _git_value(args.repo_root, "HEAD") != args.expected_source_sha
                or _git_value(args.repo_root, "HEAD^{tree}")
                != args.expected_source_tree_sha
            ):
                raise ValueError("issue_state_build_checkout_identity_mismatch")
            if inventory_raw != _git_blob(
                args.repo_root, args.expected_source_sha, DEFAULT_INVENTORY
            ):
                raise ValueError("issue_state_build_inventory_source_mismatch")
            if schema_path.read_bytes() != _git_blob(
                args.repo_root, args.expected_source_sha, DEFAULT_SCHEMA
            ):
                raise ValueError("issue_state_build_schema_source_mismatch")
            report = _build_exact_live_report_with_retry(
                repository=EXPECTED_REPOSITORY,
                report_builder=lambda rows: build_report(
                    args.repo_root,
                    inventory_path=args.inventory,
                    inventory_raw=inventory_raw,
                    schema_path=args.schema,
                    live_rows=rows,
                    expected_source_sha=args.expected_source_sha,
                    expected_source_tree_sha=args.expected_source_tree_sha,
                    expected_repository=args.repository,
                    repository_id=args.repository_id,
                    workflow_path=args.workflow_path,
                    workflow_ref=args.workflow_ref,
                    workflow_sha=args.workflow_sha,
                    source_ref=args.source_ref,
                    github_run_id=args.github_run_id,
                    github_run_attempt=args.github_run_attempt,
                ),
                attempts=args.github_settle_attempts,
                delay_seconds=args.github_settle_delay_seconds,
            )
            validate_live_report(
                report,
                inventory_raw=inventory_raw,
                expected_source_sha=args.expected_source_sha,
                expected_source_tree_sha=args.expected_source_tree_sha,
                expected_repository=args.repository,
                expected_repository_id=args.repository_id,
                expected_workflow_path=args.workflow_path,
                expected_workflow_ref=args.workflow_ref,
                expected_workflow_sha=args.workflow_sha,
                expected_source_ref=args.source_ref,
                expected_run_id=args.github_run_id,
                expected_run_attempt=args.github_run_attempt,
            )
        else:
            report = build_report(
                args.repo_root,
                inventory_path=args.inventory,
                inventory_raw=inventory_raw,
                schema_path=args.schema,
            )
        if args.out is not None:
            _write_atomic(args.out, report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"issue supersession inventory: blocked | {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(
            "issue supersession inventory: "
            f"{report['status']} | mode={report['mode']} | "
            f"open={report['inventory']['open_issue_count']} | "
            f"live_match={report['live_github']['exact_match']}"
        )
    return 0 if report["contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
