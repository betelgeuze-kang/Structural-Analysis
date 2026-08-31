from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_issue_supersession_inventory.py"
MANIFEST = ROOT / "artifacts" / "manifests" / "issue_supersession_inventory.json"
SCHEMA = ROOT / "canonical" / "issue-state-current.v1.schema.json"
WORKFLOW = ROOT / ".github" / "workflows" / "issue-state-current.yml"
SPEC = importlib.util.spec_from_file_location(
    "check_issue_supersession_inventory",
    SCRIPT,
)
assert SPEC is not None and SPEC.loader is not None
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)


def _payload() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _temporary_repo(tmp_path: Path, payload: dict) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Issue State Test")
    target = repo / inventory.DEFAULT_INVENTORY
    _write(target, payload)
    schema_target = repo / inventory.DEFAULT_SCHEMA
    schema_target.parent.mkdir(parents=True, exist_ok=True)
    schema_target.write_bytes(SCHEMA.read_bytes())
    script_target = repo / "scripts" / SCRIPT.name
    script_target.parent.mkdir(parents=True, exist_ok=True)
    script_target.write_bytes(SCRIPT.read_bytes())
    workflow_target = repo / ".github" / "workflows" / WORKFLOW.name
    workflow_target.parent.mkdir(parents=True, exist_ok=True)
    workflow_target.write_bytes(WORKFLOW.read_bytes())
    _git(repo, "add", target.relative_to(repo).as_posix())
    _git(repo, "add", schema_target.relative_to(repo).as_posix())
    _git(repo, "add", script_target.relative_to(repo).as_posix())
    _git(repo, "add", workflow_target.relative_to(repo).as_posix())
    _git(repo, "commit", "-qm", "fixture")
    return repo


def _identity(repo: Path) -> dict[str, object]:
    head = _git(repo, "rev-parse", "HEAD")
    tree = _git(repo, "rev-parse", "HEAD^{tree}")
    return {
        "expected_source_sha": head,
        "expected_source_tree_sha": tree,
        "expected_repository": inventory.EXPECTED_REPOSITORY,
        "repository_id": inventory.EXPECTED_REPOSITORY_ID,
        "workflow_path": inventory.EXPECTED_WORKFLOW_PATH,
        "workflow_ref": inventory.EXPECTED_WORKFLOW_REF,
        "workflow_sha": head,
        "source_ref": inventory.EXPECTED_SOURCE_REF,
        "github_run_id": "12345",
        "github_run_attempt": 1,
    }


def _validate(report: dict, repo: Path, raw: bytes) -> None:
    identity = _identity(repo)
    inventory.validate_live_report(
        report,
        inventory_raw=raw,
        expected_source_sha=str(identity["expected_source_sha"]),
        expected_source_tree_sha=str(identity["expected_source_tree_sha"]),
        expected_repository=str(identity["expected_repository"]),
        expected_repository_id=int(identity["repository_id"]),
        expected_workflow_path=str(identity["workflow_path"]),
        expected_workflow_ref=str(identity["workflow_ref"]),
        expected_workflow_sha=str(identity["workflow_sha"]),
        expected_source_ref=str(identity["source_ref"]),
        expected_run_id=str(identity["github_run_id"]),
        expected_run_attempt=int(identity["github_run_attempt"]),
    )


def _cli_identity(repo: Path) -> list[str]:
    identity = _identity(repo)
    return [
        "--expected-source-sha",
        str(identity["expected_source_sha"]),
        "--expected-source-tree-sha",
        str(identity["expected_source_tree_sha"]),
        "--repository",
        str(identity["expected_repository"]),
        "--repository-id",
        str(identity["repository_id"]),
        "--workflow-path",
        str(identity["workflow_path"]),
        "--workflow-ref",
        str(identity["workflow_ref"]),
        "--workflow-sha",
        str(identity["workflow_sha"]),
        "--source-ref",
        str(identity["source_ref"]),
        "--github-run-id",
        str(identity["github_run_id"]),
        "--github-run-attempt",
        str(identity["github_run_attempt"]),
    ]


def _live_fixture(payload: dict) -> list[dict]:
    rows: list[dict] = []
    for row in payload["open_issues"]:
        body = f"body-for-issue-{row['number']}"
        row["body_sha256"] = inventory._sha256_bytes(body.encode("utf-8"))
        rows.append(
            {
                "number": row["number"],
                "title": row["title"],
                "state": "open",
                "updated_at": row["updated_at"],
                "html_url": row["url"],
                "body": body,
                "labels": [{"name": label} for label in row["labels"]],
                "is_pull_request": False,
            }
        )
    projection = inventory.issue_projection(payload["open_issues"])
    payload["open_issue_projection_sha256"] = inventory.projection_sha256(projection)
    return rows


def test_inventory_is_exact_external_queue_and_offline_non_authoritative() -> None:
    report = inventory.build_report(ROOT)

    assert report["contract_pass"] is True
    assert report["mode"] == "offline_inventory"
    assert report["inventory"]["open_issue_numbers"] == [
        247,
        258,
        260,
        290,
        291,
        293,
        297,
    ]
    assert report["live_github"] == {
        "verified": False,
        "exact_match": None,
        "api_endpoint": (
            "repos/betelgeuze-kang/Structural-Analysis/issues?state=open&per_page=100"
        ),
        "open_issue_count": None,
        "open_issue_numbers": [],
        "projection_sha256": None,
    }
    assert report["authority"] == inventory.FALSE_AUTHORITY
    assert all(value is False for value in report["authority"].values())


def test_offline_report_validates_against_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(inventory.build_report(ROOT))


def test_offline_build_never_queries_github(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        inventory,
        "_fetch_github_open_issues",
        lambda *_args, **_kwargs: pytest.fail("offline path queried GitHub"),
    )

    assert inventory.build_report(ROOT)["contract_pass"] is True


def test_live_exact_projection_passes_and_retains_false_authority(
    tmp_path: Path,
) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)

    report = inventory.build_report(
        repo,
        live_rows=live_rows,
        **_identity(repo),
    )

    assert report["contract_pass"] is True
    assert report["live_github"]["exact_match"] is True
    assert report["authority"] == inventory.FALSE_AUTHORITY
    assert report["run_identity"]["required_workflow_conclusion"] == "success"
    _validate(report, repo, (repo / inventory.DEFAULT_INVENTORY).read_bytes())


def test_rehashed_inventory_tamper_is_rejected_by_live_projection(
    tmp_path: Path,
) -> None:
    original = _payload()
    live_rows = _live_fixture(original)
    tampered = deepcopy(original)
    tampered["open_issues"][0]["title"] += " tampered"
    tampered["open_issue_projection_sha256"] = inventory.projection_sha256(
        inventory.issue_projection(tampered["open_issues"])
    )
    repo = _temporary_repo(tmp_path, tampered)

    report = inventory.build_report(
        repo,
        live_rows=live_rows,
        **_identity(repo),
    )

    assert report["contract_pass"] is False
    assert "github_open_issue_projection_mismatch" in report["blockers"]


@pytest.mark.parametrize("mutation", ["missing", "unexpected"])
def test_live_projection_rejects_missing_or_unexpected_issue(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    if mutation == "missing":
        live_rows.pop()
    else:
        live_rows.append(
            {
                "number": 999,
                "title": "unexpected",
                "state": "open",
                "updated_at": "2026-08-31T00:00:00Z",
                "html_url": (
                    "https://github.com/betelgeuze-kang/Structural-Analysis/issues/999"
                ),
                "body": "unexpected",
                "labels": [],
                "is_pull_request": False,
            }
        )
    repo = _temporary_repo(tmp_path, payload)

    report = inventory.build_report(
        repo,
        live_rows=live_rows,
        **_identity(repo),
    )

    assert report["contract_pass"] is False
    assert "github_open_issue_projection_mismatch" in report["blockers"]


def test_github_query_is_paginated_and_filters_pull_requests() -> None:
    calls: list[list[str]] = []

    def runner(args: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        issue = {
            "number": 247,
            "title": "issue",
            "state": "open",
            "updated_at": "2026-08-31T00:00:00Z",
            "url": "https://example.invalid/issues/247",
            "body": "body",
            "labels": [],
            "is_pull_request": False,
        }
        pull_request = {**issue, "number": 419, "is_pull_request": True}
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="\n".join((json.dumps(issue), json.dumps(pull_request))),
            stderr="",
        )

    rows = inventory._fetch_github_open_issues(
        inventory.EXPECTED_REPOSITORY,
        runner=runner,
    )

    assert [row["number"] for row in rows] == [247]
    assert calls and "--paginate" in calls[0]
    assert "state=open&per_page=100" in calls[0][2]
    assert f"X-GitHub-Api-Version: {inventory.GITHUB_API_VERSION}" in calls[0]


def test_exact_live_retry_requeries_mismatch_then_returns_only_pass(
    tmp_path: Path,
) -> None:
    payload = _payload()
    exact_rows = _live_fixture(payload)
    mismatch_rows = deepcopy(exact_rows)
    mismatch_rows.pop()
    repo = _temporary_repo(tmp_path, payload)
    queued = [mismatch_rows, exact_rows]
    queries: list[str] = []
    sleeps: list[float] = []

    def fetcher(repository: str) -> list[dict]:
        queries.append(repository)
        return queued.pop(0)

    report = inventory._build_exact_live_report_with_retry(
        repository=inventory.EXPECTED_REPOSITORY,
        report_builder=lambda rows: inventory.build_report(
            repo,
            live_rows=rows,
            **_identity(repo),
        ),
        attempts=4,
        delay_seconds=2,
        fetcher=fetcher,
        sleeper=sleeps.append,
    )

    assert queries == [inventory.EXPECTED_REPOSITORY] * 2
    assert sleeps == [2]
    assert report["contract_pass"] is True
    assert report["live_github"]["exact_match"] is True
    assert report["blockers"] == []


@pytest.mark.parametrize("failure", ["api", "persistent_mismatch"])
def test_exact_live_retry_exhaustion_is_bounded_and_fail_closed(
    tmp_path: Path,
    failure: str,
) -> None:
    payload = _payload()
    exact_rows = _live_fixture(payload)
    mismatch_rows = deepcopy(exact_rows)
    mismatch_rows.pop()
    repo = _temporary_repo(tmp_path, payload)
    queries: list[str] = []
    sleeps: list[float] = []

    def fetcher(repository: str) -> list[dict]:
        queries.append(repository)
        if failure == "api":
            raise ValueError("transient API failure")
        return mismatch_rows

    with pytest.raises(ValueError, match="github_issue_settle_exhausted:3"):
        inventory._build_exact_live_report_with_retry(
            repository=inventory.EXPECTED_REPOSITORY,
            report_builder=lambda rows: inventory.build_report(
                repo,
                live_rows=rows,
                **_identity(repo),
            ),
            attempts=3,
            delay_seconds=2,
            fetcher=fetcher,
            sleeper=sleeps.append,
        )

    assert queries == [inventory.EXPECTED_REPOSITORY] * 3
    assert sleeps == [2, 2]


@pytest.mark.parametrize(
    ("attempts", "delay_seconds", "reason"),
    [
        (0, 0, "github_settle_attempts_invalid"),
        (inventory.MAX_GITHUB_SETTLE_ATTEMPTS + 1, 0, "github_settle_attempts_invalid"),
        (True, 0, "github_settle_attempts_invalid"),
        (1, -1, "github_settle_delay_invalid"),
        (
            1,
            inventory.MAX_GITHUB_SETTLE_DELAY_SECONDS + 1,
            "github_settle_delay_invalid",
        ),
        (1, False, "github_settle_delay_invalid"),
    ],
)
def test_exact_live_retry_policy_has_hard_bounds(
    attempts: int,
    delay_seconds: int,
    reason: str,
) -> None:
    with pytest.raises(ValueError, match=reason):
        inventory._validate_github_settle_policy(attempts, delay_seconds)


def test_live_cli_settles_then_writes_only_passing_exact_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    exact_rows = _live_fixture(payload)
    mismatch_rows = deepcopy(exact_rows)
    mismatch_rows.pop()
    repo = _temporary_repo(tmp_path, payload)
    queued = [mismatch_rows, exact_rows]
    queries: list[str] = []

    def fetcher(repository: str) -> list[dict]:
        queries.append(repository)
        return queued.pop(0)

    monkeypatch.setattr(inventory, "_fetch_github_open_issues", fetcher)
    monkeypatch.setattr(inventory.time, "sleep", lambda _seconds: None)
    output = tmp_path / "settled-report.json"
    result = inventory.main(
        [
            "--repo-root",
            str(repo),
            "--verify-github",
            "--github-settle-attempts",
            "4",
            "--github-settle-delay-seconds",
            "0",
            "--out",
            str(output),
            *_cli_identity(repo),
        ]
    )

    assert result == 0
    assert queries == [inventory.EXPECTED_REPOSITORY] * 2
    report = inventory._strict_json(output.read_bytes(), label="settled_report")
    assert report["contract_pass"] is True
    assert report["live_github"]["exact_match"] is True


@pytest.mark.parametrize("failure", ["api", "persistent_mismatch"])
def test_live_cli_persistent_failure_leaves_no_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    payload = _payload()
    exact_rows = _live_fixture(payload)
    mismatch_rows = deepcopy(exact_rows)
    mismatch_rows.pop()
    repo = _temporary_repo(tmp_path, payload)
    queries: list[str] = []

    def fetcher(repository: str) -> list[dict]:
        queries.append(repository)
        if failure == "api":
            raise ValueError("transient API failure")
        return mismatch_rows

    monkeypatch.setattr(inventory, "_fetch_github_open_issues", fetcher)
    monkeypatch.setattr(inventory.time, "sleep", lambda _seconds: None)
    output = tmp_path / "blocked-report.json"
    result = inventory.main(
        [
            "--repo-root",
            str(repo),
            "--verify-github",
            "--github-settle-attempts",
            "3",
            "--github-settle-delay-seconds",
            "0",
            "--out",
            str(output),
            *_cli_identity(repo),
        ]
    )

    assert result == 1
    assert queries == [inventory.EXPECTED_REPOSITORY] * 3
    assert not output.exists()


def test_inventory_shape_and_authority_overclaim_fail_closed(tmp_path: Path) -> None:
    payload = _payload()
    payload["claims"]["release_authority"] = True
    payload["open_issues"][0]["unexpected"] = "hidden"
    path = _write(tmp_path / "inventory.json", payload)

    report = inventory.build_report(ROOT, inventory_path=path)

    assert report["contract_pass"] is False
    assert "inventory_authority_claims_invalid" in report["blockers"]
    assert "open_issue_shape_invalid:247" in report["blockers"]


@pytest.mark.parametrize(
    "raw",
    [
        b'{"claim":false,"claim":true}',
        b'{"release_authority":false,"release\\u005fauthority":true}',
        b'{"metric":NaN}',
        b'{"metric":1e9999}',
    ],
)
def test_strict_json_rejects_duplicate_polyglots_and_nonfinite_numbers(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError, match="duplicate_json_key|nonfinite_json_number"):
        inventory._strict_json(raw, label="adversarial")


def test_every_inventory_row_family_is_exact_and_nonpromoting(tmp_path: Path) -> None:
    mutations = [
        (
            "resolved_issue_shape_invalid:207",
            lambda payload: payload["resolved_issues"][0].__setitem__(
                "release_authority", True
            ),
        ),
        (
            "superseded_pr_shape_invalid:206",
            lambda payload: payload["superseded_pull_requests"][0].__setitem__(
                "commercial_authority", True
            ),
        ),
        (
            "resolved_issue_number_invalid_or_duplicate:True",
            lambda payload: payload["resolved_issues"][0].__setitem__("number", True),
        ),
        (
            "open_issue_inventory_incomplete",
            lambda payload: payload.__setitem__("observed_open_issue_count", 8.0),
        ),
        (
            "open_issue_numbers_inconsistent",
            lambda payload: payload.__setitem__(
                "open_issue_numbers",
                [float(value) for value in payload["open_issue_numbers"]],
            ),
        ),
        (
            "open_issue_disposition_missing:247",
            lambda payload: payload["open_issues"][0].__setitem__("disposition", 1),
        ),
        (
            "resolved_issue_merge_sha_invalid:207",
            lambda payload: payload["resolved_issues"][0].__setitem__(
                "merge_commit_sha", int("1" * 40)
            ),
        ),
        (
            "merged_pull_request_not_linked:258",
            lambda payload: payload["open_issues"][1].__setitem__(
                "merged_implementation_pull_requests", [999]
            ),
        ),
    ]
    for index, (reason, mutate) in enumerate(mutations):
        payload = _payload()
        mutate(payload)
        path = _write(tmp_path / f"inventory-{index}.json", payload)

        report = inventory.build_report(ROOT, inventory_path=path)

        assert report["contract_pass"] is False
        assert reason in report["blockers"]


def test_schema_pass_live_branch_requires_all_exactness_gates(tmp_path: Path) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    report = inventory.build_report(repo, live_rows=live_rows, **_identity(repo))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    validator.validate(report)

    mutations = [
        lambda value: value["live_github"].__setitem__("exact_match", False),
        lambda value: value["consistency_gates"].__setitem__(
            "open_issue_count_match", False
        ),
        lambda value: value["consistency_gates"].__setitem__(
            "projection_sha256_match", False
        ),
    ]
    for mutate in mutations:
        attack = deepcopy(report)
        mutate(attack)
        with pytest.raises(ValidationError):
            validator.validate(attack)


def test_schema_loader_rejects_duplicate_and_semantic_mutations(tmp_path: Path) -> None:
    raw = SCHEMA.read_bytes()
    attacks = {
        "duplicate.json": raw.replace(
            b'"release_authority": {"const": false}',
            b'"release_authority":{"const":true},'
            b'"release\\u005fauthority":{"const":false}',
            1,
        ),
        "repository-loosened.json": raw.replace(
            b'"repository": {"const": "betelgeuze-kang/Structural-Analysis"}',
            b'"repository": {}',
            1,
        ),
        "unsatisfiable.json": raw.replace(b'"allOf": [', b'"allOf": [{"not": {}},', 1),
    }
    for name, attack in attacks.items():
        assert attack != raw
        path = tmp_path / name
        path.write_bytes(attack)
        with pytest.raises(ValueError, match="schema_sha256_invalid"):
            inventory._load_schema_contract(path)


def test_live_report_binds_exact_companion_bytes_and_callers(tmp_path: Path) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    companion = repo / inventory.DEFAULT_INVENTORY
    raw = companion.read_bytes()
    report = inventory.build_report(repo, live_rows=live_rows, **_identity(repo))
    _validate(report, repo, raw)

    with pytest.raises(ValueError, match="inventory_bytes_sha256_mismatch"):
        _validate(report, repo, raw + b"\n")

    identity = _identity(repo)
    with pytest.raises(ValueError, match="artifact_prefix_invalid"):
        inventory.validate_live_report(
            report,
            inventory_raw=raw,
            expected_source_sha=str(identity["expected_source_sha"]),
            expected_source_tree_sha=str(identity["expected_source_tree_sha"]),
            expected_repository=str(identity["expected_repository"]),
            expected_repository_id=int(identity["repository_id"]),
            expected_workflow_path=str(identity["workflow_path"]),
            expected_workflow_ref=str(identity["workflow_ref"]),
            expected_workflow_sha=str(identity["workflow_sha"]),
            expected_source_ref=str(identity["source_ref"]),
            expected_run_id="99999",
            expected_run_attempt=1,
        )


def test_check_report_cli_executes_exact_and_adversarial_replays(
    tmp_path: Path,
) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    report = inventory.build_report(repo, live_rows=live_rows, **_identity(repo))
    report_path = _write(tmp_path / "report.json", report)
    base = [
        sys.executable,
        str(SCRIPT),
        "--repo-root",
        str(repo),
        "--inventory",
        str(repo / inventory.DEFAULT_INVENTORY),
        "--schema",
        str(repo / inventory.DEFAULT_SCHEMA),
        "--check-report",
        str(report_path),
        *_cli_identity(repo),
    ]
    completed = subprocess.run(base, check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr

    selector_attack = list(base)
    run_index = selector_attack.index("--github-run-id") + 1
    selector_attack[run_index] = "99999"
    completed = subprocess.run(
        selector_attack, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 1

    tampered_inventory = tmp_path / "inventory-byte-tamper.json"
    tampered_inventory.write_bytes(
        (repo / inventory.DEFAULT_INVENTORY).read_bytes() + b"\n"
    )
    companion_attack = list(base)
    inventory_index = companion_attack.index("--inventory") + 1
    companion_attack[inventory_index] = str(tampered_inventory)
    completed = subprocess.run(
        companion_attack, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 1
    assert "companion_inventory_source_mismatch" in completed.stderr

    duplicate_report = tmp_path / "duplicate-report.json"
    raw = report_path.read_bytes()
    duplicate_report.write_bytes(
        raw.replace(
            b'"schema_version": "issue-state-current.v1"',
            b'"schema_version":"attacker",'
            b'"schema\\u005fversion": "issue-state-current.v1"',
            1,
        )
    )
    duplicate_attack = list(base)
    report_index = duplicate_attack.index("--check-report") + 1
    duplicate_attack[report_index] = str(duplicate_report)
    completed = subprocess.run(
        duplicate_attack, check=False, capture_output=True, text=True
    )
    assert completed.returncode == 1


def test_workflow_adversarial_replay_step_executes_verbatim(tmp_path: Path) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    identity = _identity(repo)
    report = inventory.build_report(repo, live_rows=live_rows, **identity)
    output_dir = tmp_path / "workflow-output"
    bundle = output_dir / "bundle"
    (bundle / "artifacts" / "manifests").mkdir(parents=True)
    (bundle / "canonical").mkdir()
    (bundle / "scripts").mkdir()
    (bundle / ".github" / "workflows").mkdir(parents=True)
    _write(bundle / "issue-state-current.json", report)
    (bundle / inventory.DEFAULT_INVENTORY).write_bytes(
        (repo / inventory.DEFAULT_INVENTORY).read_bytes()
    )
    (bundle / inventory.DEFAULT_SCHEMA).write_bytes(
        (repo / inventory.DEFAULT_SCHEMA).read_bytes()
    )
    (bundle / "scripts" / SCRIPT.name).write_bytes(
        (repo / "scripts" / SCRIPT.name).read_bytes()
    )
    (bundle / ".github" / "workflows" / WORKFLOW.name).write_bytes(
        (repo / ".github" / "workflows" / WORKFLOW.name).read_bytes()
    )
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    step = next(
        row
        for row in workflow["jobs"]["live-exact-main"]["steps"]
        if row.get("name") == "Execute adversarial replay and exact bundle probes"
    )
    env = {
        **os.environ,
        "BUNDLE_ROOT": str(bundle),
        "CONTRACT_WORKFLOW_PATH": inventory.EXPECTED_WORKFLOW_PATH,
        "GITHUB_REF": inventory.EXPECTED_SOURCE_REF,
        "GITHUB_REPOSITORY": inventory.EXPECTED_REPOSITORY,
        "GITHUB_REPOSITORY_ID": str(inventory.EXPECTED_REPOSITORY_ID),
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_RUN_ID": "12345",
        "GITHUB_WORKFLOW_REF": inventory.EXPECTED_WORKFLOW_REF,
        "GITHUB_WORKFLOW_SHA": str(identity["workflow_sha"]),
        "OUTPUT_DIR": str(output_dir),
        "OUTPUT_PATH": str(bundle / "issue-state-current.json"),
        "SOURCE_SHA": str(identity["expected_source_sha"]),
    }

    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", step["run"]],
        cwd=repo,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


def test_live_report_rejects_authority_promotion(tmp_path: Path) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    report = inventory.build_report(
        repo,
        live_rows=live_rows,
        **_identity(repo),
    )
    report["authority"]["release_authority"] = True

    with pytest.raises(ValueError, match="authority_invalid"):
        _validate(report, repo, (repo / inventory.DEFAULT_INVENTORY).read_bytes())


@pytest.mark.parametrize(
    ("mutate", "reason"),
    [
        (
            lambda report: report.__setitem__("repository", "attacker/repository"),
            "repository_invalid",
        ),
        (
            lambda report: report.__setitem__("claim_boundary", "promoted"),
            "claim_boundary_invalid",
        ),
        (
            lambda report: report["inventory"].__setitem__("hidden", True),
            "projection_shape_invalid",
        ),
    ],
)
def test_live_report_rejects_identity_or_hidden_field_tamper(
    tmp_path: Path,
    mutate,
    reason: str,
) -> None:
    payload = _payload()
    live_rows = _live_fixture(payload)
    repo = _temporary_repo(tmp_path, payload)
    report = inventory.build_report(
        repo,
        live_rows=live_rows,
        **_identity(repo),
    )
    mutate(report)

    with pytest.raises(ValueError, match=reason):
        _validate(report, repo, (repo / inventory.DEFAULT_INVENTORY).read_bytes())


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink contract")
def test_atomic_output_rejects_leaf_and_parent_symlinks(tmp_path: Path) -> None:
    victim = tmp_path / "victim.json"
    victim.write_text("preserve", encoding="utf-8")
    leaf = tmp_path / "leaf.json"
    leaf.symlink_to(victim)

    with pytest.raises(ValueError, match="output_leaf_invalid"):
        inventory._write_atomic(leaf, {"value": 1})
    assert victim.read_text(encoding="utf-8") == "preserve"

    victim_dir = tmp_path / "victim-dir"
    victim_dir.mkdir()
    parent = tmp_path / "linked-parent"
    parent.symlink_to(victim_dir, target_is_directory=True)
    with pytest.raises(ValueError, match="output_parent_invalid"):
        inventory._write_atomic(parent / "report.json", {"value": 1})
    assert not (victim_dir / "report.json").exists()


def test_workflow_separates_offline_pr_and_live_exact_main() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    offline = source.split("  offline-contract:", 1)[1].split(
        "\n  live-exact-main:", 1
    )[0]
    live = source.split("\n  live-exact-main:", 1)[1]

    assert "pull_request: {}" in source
    assert 'branches: ["main"]' in source
    assert "workflow_dispatch: {}" in source
    assert 'GH_TOKEN: ""' in offline
    assert "--verify-github" not in offline
    assert "issues: read" in live
    assert "github.run_attempt == 1" in live
    assert live.count("--verify-github") == 3
    assert live.count('--github-settle-attempts "$GITHUB_SETTLE_ATTEMPTS"') == 3
    assert (
        live.count('--github-settle-delay-seconds "$GITHUB_SETTLE_DELAY_SECONDS"') == 3
    )
    assert '--expected-source-sha "$SOURCE_SHA"' in live
    assert '--expected-source-tree-sha "$source_tree_sha"' in live
    assert '--repository "$GITHUB_REPOSITORY"' in live
    assert '--repository-id "$GITHUB_REPOSITORY_ID"' in live
    assert '--workflow-ref "$GITHUB_WORKFLOW_REF"' in live
    assert '--workflow-sha "$GITHUB_WORKFLOW_SHA"' in live
    assert '--source-ref "$GITHUB_REF"' in live
    assert 'test "$GITHUB_WORKFLOW_REF" = "$CONTRACT_WORKFLOW_REF"' in live
    assert 'test "$GITHUB_WORKFLOW_SHA" = "$WORKFLOW_SHA"' in live
    assert 'replay "$OUTPUT_PATH" "$companion" "$GITHUB_RUN_ID"' in live
    assert ".run_identity.artifact_prefix" in live
    assert "adversarial report was accepted" in live
    assert live.count('cmp "$OUTPUT_PATH"') == 2
    assert source.count('gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main"') >= 3
    assert "persist-credentials: false" in live
    assert "Reject a moving main after upload" in live
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in live
    upload = live.split(
        "      - name: Upload exact-run non-authoritative issue-state artifact", 1
    )[1].split("      - name: Reject a moving main after upload", 1)[0]
    assert "path: ${{ env.BUNDLE_ROOT }}/" in upload
    assert "env.OUTPUT_PATH" not in upload
    assert "artifacts/manifests/issue_supersession_inventory.json" not in upload
    assert "UPLOADED_ARTIFACT_DIGEST" in live
    assert ".workflow_run.id == $run_id" in live
    assert "id-token: write" not in source
    assert "attestations: write" not in source


def test_workflow_clean_tree_and_symlink_guards_preserve_command_failures() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert 'test -z "$(git status' not in source
    assert 'test -z "$(find ' not in source
    assert (
        source.count(
            'checkout_status="$(git status --porcelain=v1 --untracked-files=all)"'
        )
        == 4
    )
    assert source.count('test -z "$checkout_status"') == 4
    assert 'first_symlink="$(find -P "$BUNDLE_ROOT" -type l -print -quit)"' in source
    assert 'test -z "$first_symlink"' in source


def test_workflow_trigger_permissions_and_actions_are_exact_structures() -> None:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    assert set(workflow["on"]) == {"pull_request", "push", "workflow_dispatch"}
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["permissions"] == {"contents": "read"}
    assert set(workflow["jobs"]) == {"offline-contract", "live-exact-main"}
    assert workflow["jobs"]["offline-contract"]["permissions"] == {
        "contents": "read",
        "issues": "none",
    }
    live = workflow["jobs"]["live-exact-main"]
    assert workflow["env"]["GITHUB_SETTLE_ATTEMPTS"] == "4"
    assert workflow["env"]["GITHUB_SETTLE_DELAY_SECONDS"] == "2"
    assert live["permissions"] == {
        "actions": "read",
        "contents": "read",
        "issues": "read",
    }
    assert "github.event_name != 'pull_request'" in live["if"]
    assert "github.ref == 'refs/heads/main'" in live["if"]
    assert "github.run_attempt == 1" in live["if"]
    uses = [step["uses"] for step in live["steps"] if "uses" in step]
    assert uses == [
        "actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    ]


def test_each_live_workflow_requery_uses_the_same_bounded_retry_selectors() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = {
        step["name"]: step["run"]
        for step in workflow["jobs"]["live-exact-main"]["steps"]
        if "run" in step
    }
    for name in (
        "Query live GitHub issue state and require exact tracked projection",
        "Confirm main remains exact before upload",
        "Reject a moving main after upload",
    ):
        command = steps[name]
        assert command.count("--verify-github") == 1
        verify_selectors = command.split("--verify-github", 1)[1].split("--out", 1)[0]
        assert (
            verify_selectors.count('--github-settle-attempts "$GITHUB_SETTLE_ATTEMPTS"')
            == 1
        )
        assert (
            verify_selectors.count(
                '--github-settle-delay-seconds "$GITHUB_SETTLE_DELAY_SECONDS"'
            )
            == 1
        )
        assert verify_selectors.count('--github-run-id "$GITHUB_RUN_ID"') == 1
        assert verify_selectors.count('--github-run-attempt "$GITHUB_RUN_ATTEMPT"') == 1

    assert int(workflow["env"]["GITHUB_SETTLE_ATTEMPTS"]) == (
        inventory.WORKFLOW_GITHUB_SETTLE_ATTEMPTS
    )
    assert int(workflow["env"]["GITHUB_SETTLE_DELAY_SECONDS"]) == (
        inventory.WORKFLOW_GITHUB_SETTLE_DELAY_SECONDS
    )
