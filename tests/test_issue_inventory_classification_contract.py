"""Focused issue-state taxonomy checks; no GitHub or solver execution."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "issue_inventory_classification_contract",
    ROOT / "scripts/check_issue_supersession_inventory.py",
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class IssueInventoryClassificationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads((ROOT / checker.DEFAULT_INVENTORY).read_text())
        self.number = self.payload["open_issues"][0]["number"]

    def blockers(self, payload: dict) -> list[str]:
        return checker._validate_inventory_contract(
            json.dumps(payload).encode("utf-8")
        )[-1]

    def implementation_payload(self) -> dict:
        payload = deepcopy(self.payload)
        row = payload["open_issues"][0]
        row["classification"] = "repository_implementation"
        row["closable_by_repository_code_alone"] = True
        row["required_external_inputs"] = []
        return payload

    def test_existing_external_inventory_remains_valid(self) -> None:
        self.assertEqual(self.blockers(self.payload), [])

    def test_repository_implementation_is_non_authoritative(self) -> None:
        payload = self.implementation_payload()
        self.assertEqual(self.blockers(payload), [])
        self.assertIs(payload["open_issues"][0]["current_product_authority"], False)
        self.assertEqual(payload["claims"], checker.FALSE_AUTHORITY)

    def test_repository_implementation_rejects_external_inputs(self) -> None:
        for value in (["independent_reviewer"], None, "", [False]):
            with self.subTest(value=value):
                payload = self.implementation_payload()
                payload["open_issues"][0]["required_external_inputs"] = value
                self.assertIn(
                    f"open_issue_external_inputs_invalid:{self.number}",
                    self.blockers(payload),
                )

    def test_repository_implementation_requires_literal_true(self) -> None:
        for value in (False, 1, 0, None, "true"):
            with self.subTest(value=value):
                payload = self.implementation_payload()
                payload["open_issues"][0]["closable_by_repository_code_alone"] = value
                self.assertIn(
                    f"open_issue_repository_closure_boundary_invalid:{self.number}",
                    self.blockers(payload),
                )

    def test_external_classes_keep_external_boundary(self) -> None:
        for classification in checker.EXTERNAL_CLASSIFICATIONS:
            with self.subTest(classification=classification):
                payload = deepcopy(self.payload)
                row = payload["open_issues"][0]
                row["classification"] = classification
                self.assertEqual(self.blockers(payload), [])
                row["required_external_inputs"] = []
                self.assertIn(
                    f"open_issue_external_inputs_invalid:{self.number}",
                    self.blockers(payload),
                )
                row["closable_by_repository_code_alone"] = True
                self.assertIn(
                    f"open_issue_repository_closure_boundary_invalid:{self.number}",
                    self.blockers(payload),
                )

    def test_unknown_class_never_defaults_to_implementation(self) -> None:
        for value in ("repository_implementation_new", "", None, False):
            with self.subTest(value=value):
                payload = self.implementation_payload()
                payload["open_issues"][0]["classification"] = value
                self.assertIn(
                    f"open_issue_classification_invalid:{self.number}",
                    self.blockers(payload),
                )

    def test_implementation_never_grants_product_authority(self) -> None:
        for value in (True, 0, None):
            with self.subTest(value=value):
                payload = self.implementation_payload()
                payload["open_issues"][0]["current_product_authority"] = value
                self.assertIn(
                    f"open_issue_product_authority_invalid:{self.number}",
                    self.blockers(payload),
                )

    def test_observation_source_is_explicit_and_closed(self) -> None:
        for value in checker.OBSERVATION_SOURCES:
            with self.subTest(value=value):
                payload = deepcopy(self.payload)
                payload["observation_source"] = value
                self.assertEqual(self.blockers(payload), [])
        for value in ("manual", "inferred", "", None, [], {}):
            with self.subTest(value=value):
                payload = deepcopy(self.payload)
                payload["observation_source"] = value
                self.assertIn(
                    "inventory_observation_source_invalid", self.blockers(payload)
                )

    def test_closure_event_extension_is_not_implicitly_admitted(self) -> None:
        payload = deepcopy(self.payload)
        row = payload["resolved_issues"][0]
        row["closure_event_id"] = row.pop("normalization_comment_id")
        self.assertIn("resolved_issue_shape_invalid:207", self.blockers(payload))

    def test_schema_workflow_and_exact_projection_remain_unchanged(self) -> None:
        checker._load_schema_contract(ROOT / checker.DEFAULT_SCHEMA)
        workflow = (ROOT / ".github/workflows/issue-state-current.yml").read_text()
        self.assertEqual(workflow.count('test "$GITHUB_RUN_ATTEMPT" = "1"'), 2)
        payload = self.implementation_payload()
        before = checker.issue_projection(payload["open_issues"])
        for field, value in (
            ("updated_at", "2026-10-05T23:00:00Z"),
            ("body_sha256", "sha256:" + "0" * 64),
            ("labels", ["changed"]),
            ("title", "Changed title"),
        ):
            with self.subTest(field=field):
                changed = deepcopy(payload)
                changed["open_issues"][0][field] = value
                after = checker.issue_projection(changed["open_issues"])
                self.assertNotEqual(before, after)
                self.assertNotEqual(
                    checker.projection_sha256(before),
                    checker.projection_sha256(after),
                )


if __name__ == "__main__":
    unittest.main()
