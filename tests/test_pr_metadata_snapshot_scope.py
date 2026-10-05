"""Read-only snapshot metadata exception, including failed and racing reads."""

from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "pr_metadata_snapshot_scope",
    ROOT / "scripts/check_pr_issue_metadata.py",
)
assert SPEC is not None and SPEC.loader is not None
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def _event() -> dict:
    repo = {
        "id": validator.SNAPSHOT_REPOSITORY_ID,
        "full_name": validator.SNAPSHOT_REPOSITORY,
    }
    return {
        "number": 900,
        "repository": deepcopy(repo),
        "pull_request": {
            "number": 900,
            "title": "Refresh the observed issue-state snapshot",
            "body": "Refs #493\n\nPurpose: issue-state snapshot maintenance\n",
            "state": "open",
            "commits": 1,
            "changed_files": 1,
            "base": {"ref": "main", "sha": "a" * 40, "repo": deepcopy(repo)},
            "head": {"ref": "refresh", "sha": "b" * 40, "repo": deepcopy(repo)},
        },
    }


def _files() -> list[dict]:
    return [{"filename": validator.SNAPSHOT_INVENTORY_PATH, "status": "modified"}]


def _fetcher(event: dict, files: list[dict] | None = None):
    calls = []
    rows = _files() if files is None else files

    def fetch(endpoint: str):
        calls.append(endpoint)
        if "/files?" in endpoint:
            page = int(endpoint.rsplit("=", 1)[1])
            return deepcopy(rows[(page - 1) * 100:page * 100])
        if endpoint.endswith("/issues/493"):
            return {"number": 493, "state": "open"}
        return deepcopy(event["pull_request"])

    return fetch, calls


class SnapshotScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = _event()
        self.fetch, self.calls = _fetcher(self.event)
        self.observation = validator.collect_snapshot_observation(
            self.event, fetcher=self.fetch
        )

    def report(self, event=None, observation=None):
        return validator.build_report(
            self.event if event is None else event,
            snapshot_observation=(
                self.observation if observation is None else observation
            ),
        )

    def test_inventory_only_exception_requires_authenticated_observation(self):
        report = self.report()
        self.assertTrue(report["contract_pass"])
        self.assertTrue(report["require_closing_issue"])
        self.assertTrue(report["snapshot_maintenance_verified"])
        self.assertEqual(report["closing_issue_numbers"], [])
        self.assertEqual(report["snapshot_scope"]["head_sha"], "b" * 40)
        self.assertEqual(report["snapshot_scope"]["base_sha"], "a" * 40)
        self.assertEqual(report["snapshot_scope"]["changed_paths"], [
            validator.SNAPSHOT_INVENTORY_PATH,
        ])
        absent = validator.build_report(self.event)
        self.assertFalse(absent["contract_pass"])
        self.assertIn(
            "snapshot_authenticated_observation_missing", absent["blockers"]
        )

    def test_associated_existing_expectation_test_is_optional(self):
        self.event["pull_request"]["changed_files"] = 2
        files = _files() + [{
            "filename": "tests/test_check_issue_supersession_inventory.py",
            "status": "modified",
        }]
        fetch, _ = _fetcher(self.event, files)
        observation = validator.collect_snapshot_observation(
            self.event, fetcher=fetch
        )
        self.assertTrue(self.report(observation=observation)["contract_pass"])

    def test_bootstrap_remains_a_normal_closing_issue_pr(self):
        event = deepcopy(self.event)
        event["pull_request"]["body"] = "Closes #549.\n\nAdd governed maintenance."
        event["pull_request"]["changed_files"] = 5
        report = validator.build_report(event)
        self.assertTrue(report["contract_pass"])
        self.assertFalse(report["snapshot_maintenance_requested"])
        self.assertEqual(report["closing_issue_numbers"], [549])

    def test_purpose_and_governing_reference_are_both_required(self):
        for body in (
            "Refs #493",
            validator.SNAPSHOT_PURPOSE,
            validator.SNAPSHOT_PURPOSE + "\nRefs #492",
            "Purpose: another task\nRefs #493",
        ):
            with self.subTest(body=body):
                event = deepcopy(self.event)
                event["pull_request"]["body"] = body
                self.assertFalse(self.report(event=event)["contract_pass"])

    def test_body_declared_paths_do_not_replace_authenticated_files(self):
        event = deepcopy(self.event)
        event["pull_request"]["body"] += (
            "\nChanged paths: artifacts/manifests/issue_supersession_inventory.json"
        )
        report = validator.build_report(event)
        self.assertFalse(report["contract_pass"])

    def test_closing_hash_url_or_qualified_reference_is_forbidden(self):
        for suffix in (
            "Closes #493",
            "Fixes: #493",
            "Resolves betelgeuze-kang/Structural-Analysis#493",
            "Closes https://github.com/betelgeuze-kang/Structural-Analysis/issues/493",
            "Closes #999",
        ):
            with self.subTest(suffix=suffix):
                event = deepcopy(self.event)
                event["pull_request"]["body"] += "\n" + suffix
                fetch, _ = _fetcher(event)
                observation = validator.collect_snapshot_observation(
                    event, fetcher=fetch
                )
                report = self.report(event, observation)
                self.assertFalse(report["contract_pass"])
                self.assertIn(
                    "snapshot_closing_reference_forbidden", report["blockers"]
                )

    def test_other_issue_governance_is_forbidden(self):
        for suffix in (
            "Refs #494",
            "Refs someone/else#493",
            "https://github.com/someone/else/issues/493",
            "https://github.com/betelgeuze-kang/Structural-Analysis/issues/549",
        ):
            with self.subTest(suffix=suffix):
                event = deepcopy(self.event)
                event["pull_request"]["body"] += "\n" + suffix
                fetch, _ = _fetcher(event)
                observation = validator.collect_snapshot_observation(
                    event, fetcher=fetch
                )
                self.assertFalse(self.report(event, observation)["contract_pass"])

    def test_generic_code_policy_schema_and_workflow_paths_are_forbidden(self):
        for path in (
            "scripts/check_issue_supersession_inventory.py",
            "scripts/check_pr_issue_metadata.py",
            ".github/workflows/pr-metadata-ci.yml",
            ".github/workflows/issue-state-current.yml",
            "canonical/issue-state-current.v1.schema.json",
            "src/structural_analysis/solver.py",
            ".betelgeuze/intent_spec.md",
            "implementation/phase1/release_evidence/productization/state.json",
        ):
            with self.subTest(path=path):
                event = deepcopy(self.event)
                event["pull_request"]["changed_files"] = 2
                fetch, _ = _fetcher(event, _files() + [{
                    "filename": path, "status": "modified",
                }])
                observation = validator.collect_snapshot_observation(
                    event, fetcher=fetch
                )
                report = self.report(event, observation)
                self.assertIn("snapshot_file_scope_invalid", report["blockers"])
                self.assertFalse(report["contract_pass"])

    def test_missing_inventory_renames_deletions_and_duplicates_fail(self):
        for files in (
            [{
                "filename": "tests/test_check_issue_supersession_inventory.py",
                "status": "modified",
            }],
            [{"filename": validator.SNAPSHOT_INVENTORY_PATH, "status": "removed"}],
            [{"filename": validator.SNAPSHOT_INVENTORY_PATH, "status": "added"}],
            [{
                "filename": validator.SNAPSHOT_INVENTORY_PATH,
                "status": "renamed",
                "previous_filename": "src/solver.py",
            }],
            [{
                "filename": validator.SNAPSHOT_INVENTORY_PATH,
                "status": "modified",
                "previous_filename": "old.json",
            }],
            _files() * 2,
        ):
            with self.subTest(files=files):
                event = deepcopy(self.event)
                event["pull_request"]["changed_files"] = len(files)
                fetch, _ = _fetcher(event, files)
                observation = validator.collect_snapshot_observation(
                    event, fetcher=fetch
                )
                self.assertFalse(self.report(event, observation)["contract_pass"])

    def test_incomplete_or_stale_observation_fails(self):
        for key, value in (
            ("complete", False),
            ("complete", 1),
            ("repository", "someone/else"),
            ("repository_id", 1),
            ("governing_issue_state", "closed"),
            ("files", []),
            ("before", {}),
            ("after", {}),
        ):
            with self.subTest(key=key, value=value):
                observation = deepcopy(self.observation)
                observation[key] = value
                self.assertFalse(self.report(observation=observation)["contract_pass"])

    def test_repository_fork_branch_and_event_types_fail(self):
        events = []
        for side in ("base", "head"):
            event = deepcopy(self.event)
            event["pull_request"][side]["repo"]["full_name"] = "someone/fork"
            events.append(event)
        for key, value in (("sha", "not-a-sha"), ("ref", "development")):
            event = deepcopy(self.event)
            event["pull_request"]["base"][key] = value
            events.append(event)
        for key, value in (
            ("number", True), ("changed_files", True), ("state", "closed")
        ):
            event = deepcopy(self.event)
            event["pull_request"][key] = value
            events.append(event)
        event = deepcopy(self.event)
        event["repository"]["id"] = "1136685613"
        events.append(event)
        for event in events:
            with self.subTest(event=event):
                self.assertFalse(self.report(event=event)["contract_pass"])

    def test_precollection_stale_head_base_body_or_count_fails(self):
        for change in ("head", "base", "body", "changed_files"):
            with self.subTest(change=change):
                actual = deepcopy(self.event)
                if change in ("head", "base"):
                    actual["pull_request"][change]["sha"] = "c" * 40
                elif change == "body":
                    actual["pull_request"][change] += "edited"
                else:
                    actual["pull_request"][change] = 2
                fetch, _ = _fetcher(actual)
                with self.assertRaisesRegex(ValueError, "changed_before_collection"):
                    validator.collect_snapshot_observation(self.event, fetcher=fetch)

    def test_racing_head_base_body_count_or_governing_closure_fails(self):
        for change in ("head", "base", "body", "changed_files", "issue"):
            with self.subTest(change=change):
                fetch, calls = _fetcher(self.event)

                def racing(endpoint):
                    result = fetch(endpoint)
                    if len(calls) >= 4:
                        if change == "issue" and endpoint.endswith("/issues/493"):
                            result["state"] = "closed"
                        elif endpoint.endswith("/pulls/900"):
                            if change in ("head", "base"):
                                result[change]["sha"] = "c" * 40
                            elif change == "body":
                                result[change] += "edited"
                            elif change == "changed_files":
                                result[change] = 2
                    return result

                with self.assertRaises(ValueError):
                    validator.collect_snapshot_observation(self.event, fetcher=racing)

    def test_closed_or_pr_shaped_governing_issue_fails(self):
        for issue in (
            {"number": 493, "state": "closed"},
            {"number": 493, "state": "open", "pull_request": {}},
            {"number": 492, "state": "open"},
        ):
            with self.subTest(issue=issue):
                fetch, _ = _fetcher(self.event)

                def wrong_issue(endpoint):
                    if endpoint.endswith("/issues/493"):
                        return issue
                    return fetch(endpoint)

                with self.assertRaisesRegex(ValueError, "governing_issue_not_open"):
                    validator.collect_snapshot_observation(
                        self.event, fetcher=wrong_issue
                    )

    def test_file_count_mismatch_fails(self):
        fetch, _ = _fetcher(self.event, [])
        with self.assertRaisesRegex(ValueError, "file_count_mismatch"):
            validator.collect_snapshot_observation(self.event, fetcher=fetch)

    def test_paginated_files_are_fetched_to_the_terminal_page(self):
        files = [
            {"filename": f"file-{index}", "status": "modified"}
            for index in range(101)
        ]
        fetch, calls = _fetcher(self.event, files)
        actual = validator._fetch_snapshot_files("repos/example/pulls/900", fetch)
        self.assertEqual(actual, files)
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[-1].endswith("per_page=100&page=2"))
        fetch, calls = _fetcher(self.event, files[:100])
        self.assertEqual(
            len(validator._fetch_snapshot_files("repos/example/pulls/900", fetch)),
            100,
        )
        self.assertEqual(len(calls), 2)

    def test_malformed_and_unbounded_pagination_fails(self):
        for value in ({}, [None], [{}] * 101):
            with self.subTest(value_type=type(value)):
                with self.assertRaisesRegex(ValueError, "file_page_invalid"):
                    validator._fetch_snapshot_files("x", lambda _: value)
        with self.assertRaisesRegex(ValueError, "file_limit_exceeded"):
            validator._fetch_snapshot_files("x", lambda _: [{}] * 100)

    def test_github_reads_are_get_only_versioned_and_fail_closed(self):
        commands = []

        def runner(command, **kwargs):
            commands.append((command, kwargs))
            return subprocess.CompletedProcess(command, 0, stdout="[]", stderr="")

        self.assertEqual(
            validator._github_json("repos/example/pulls/900", runner=runner), []
        )
        command, kwargs = commands[0]
        self.assertEqual(command[:3], ["gh", "api", "repos/example/pulls/900"])
        self.assertNotIn("--method", command)
        self.assertIn("X-GitHub-Api-Version: 2022-11-28", command)
        self.assertEqual(kwargs["timeout"], 120)
        for status, stdout in ((1, "secret error"), (0, "not-json")):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    validator._github_json(
                        "x",
                        runner=lambda *a, **k: subprocess.CompletedProcess(
                            a[0], status, stdout=stdout
                        ),
                    )

    def test_cli_without_authentication_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            out = Path(tmp) / "report.json"
            event.write_text(json.dumps(self.event))
            with patch.dict(os.environ, {}, clear=True):
                result = validator.main(["--event-json", str(event), "--out", str(out)])
            report = json.loads(out.read_text())
            self.assertEqual(result, 1)
            self.assertIn("snapshot_github_authentication_missing", report["blockers"])

    def test_normal_closing_cli_never_needs_snapshot_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            out = Path(tmp) / "report.json"
            payload = deepcopy(self.event)
            payload["pull_request"]["body"] = "Closes #549."
            event.write_text(json.dumps(payload))
            with patch.dict(os.environ, {}, clear=True), patch.object(
                validator,
                "collect_snapshot_observation",
                side_effect=AssertionError("network"),
            ):
                self.assertEqual(
                    validator.main([
                        "--event-json", str(event), "--out", str(out)
                    ]),
                    0,
                )

    def test_workflow_keeps_read_only_permissions_and_no_unlinked_override(self):
        workflow = (ROOT / ".github/workflows/pr-metadata-ci.yml").read_text()
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("issues: read", workflow)
        self.assertIn("pull-requests: read", workflow)
        self.assertNotIn("--allow-unlinked", workflow)
        self.assertNotIn("issues: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertEqual(validator.SNAPSHOT_ALLOWED_PATHS, {
            validator.SNAPSHOT_INVENTORY_PATH,
            "tests/test_check_issue_supersession_inventory.py",
        })


if __name__ == "__main__":
    unittest.main()
