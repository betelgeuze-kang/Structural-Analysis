"""Executable regressions for supplemental upload identity, without GitHub access."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    spec = importlib.util.spec_from_file_location(
        "supplemental_artifact_identity_under_test",
        SCRIPTS / "verify_supplemental_artifact_identity.py",
    )
    assert spec is not None and spec.loader is not None
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
finally:
    sys.path.pop(0)


class SupplementalArtifactIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = {
            "repository": "example/structural-analysis", "source_sha": "a" * 40,
            "run_id": 901, "run_attempt": 2, "family": "negative",
        }
        self.prefix = "repos/example/structural-analysis/actions"
        self.run_endpoint = self.prefix + "/runs/901"
        self.inventory_endpoint = self.run_endpoint + "/artifacts?per_page=100"
        self.direct_endpoint = self.prefix + "/artifacts/701"
        self.zip_endpoint = self.direct_endpoint + "/zip"
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("receipt.json", '{"technical_credit_granted": false}')
        self.raw = buffer.getvalue()
        self.row = {
            "id": 701, "name": "bounded-planar-negative-opensees-901-2",
            "digest": "sha256:" + hashlib.sha256(self.raw).hexdigest(),
            "size_in_bytes": len(self.raw), "expired": False,
            "archive_download_url": "https://api.github.com/" + self.zip_endpoint,
            "workflow_run": {
                "id": 901, "repository_id": 17, "head_repository_id": 17,
                "head_branch": "main", "head_sha": "a" * 40,
            },
        }
        self.run = {
            "id": 901, "run_attempt": 2, "head_sha": "a" * 40,
            "head_branch": "main", "event": "push", "status": "in_progress",
            "conclusion": None,
            "path": ".github/workflows/bounded-planar-negative-opensees-technical.yml",
            "repository": {"id": 17, "full_name": "example/structural-analysis"},
            "head_repository": {"id": 17, "full_name": "example/structural-analysis"},
        }
        self.responses = {
            self.run_endpoint: copy.deepcopy(self.run),
            self.inventory_endpoint: {"total_count": 1, "artifacts": [copy.deepcopy(self.row)]},
            self.direct_endpoint: copy.deepcopy(self.row),
            self.zip_endpoint: self.raw,
        }
        self.calls: list[str] = []

    def stream(self, endpoint: str, limit: int, sink) -> None:
        self.calls.append(endpoint)
        response = self.responses[endpoint]
        raw = response if isinstance(response, bytes) else json.dumps(response).encode()
        if len(raw) > limit:
            raise verifier.ArtifactIdentityError("api_response_too_large")
        # Exercise chunked rather than one-shot hashing.
        for offset in range(0, len(raw), 13):
            sink(raw[offset:offset + 13])

    def inspect(self):
        return verifier.inspect_upload(**self.context, stream=self.stream)

    def assert_rejected(self, diagnostic, code):
        self.assertEqual(diagnostic["status"], "rejected")
        self.assertEqual(diagnostic["error_code"], code)
        for key in ("release_authority", "independent_verification", "technical_credit_granted"):
            self.assertIs(diagnostic[key], False)
        self.assertNotIn("artifact_id", diagnostic)

    def test_exact_id_is_rechecked_and_downloaded_without_authority(self):
        result = self.inspect()
        self.assertEqual(result["status"], "transport_verified")
        self.assertEqual(result["artifact_id"], 701)
        self.assertEqual(self.calls, [
            self.run_endpoint, self.inventory_endpoint, self.direct_endpoint, self.zip_endpoint,
        ])
        self.assertIs(result["release_authority"], False)
        self.assertIs(result["independent_verification"], False)
        self.assertIs(result["technical_credit_granted"], False)

    def test_all_five_family_contracts(self):
        for family, (workflow, prefix) in verifier.FAMILIES.items():
            with self.subTest(family=family):
                self.context["family"] = family
                self.responses[self.run_endpoint]["path"] = ".github/workflows/" + workflow
                for row in (
                    self.responses[self.inventory_endpoint]["artifacts"][0],
                    self.responses[self.direct_endpoint],
                ):
                    row["name"] = prefix + "-901-2"
                self.assertEqual(self.inspect()["status"], "transport_verified")

    def test_missing_and_expired_are_not_credited_or_downloaded(self):
        self.responses[self.inventory_endpoint] = {"total_count": 0, "artifacts": []}
        self.assert_rejected(self.inspect(), "artifact_missing")
        self.assertNotIn(self.zip_endpoint, self.calls)
        self.responses[self.inventory_endpoint] = {
            "total_count": 1, "artifacts": [dict(self.row, expired=True)],
        }
        self.assert_rejected(self.inspect(), "artifact_expired")
        self.assertNotIn(self.zip_endpoint, self.calls)

    def test_observed_three_identical_digest_uploads_remain_ambiguous(self):
        rows = [dict(self.row, id=value) for value in (9810071413, 9810071293, 9810071157)]
        self.responses[self.inventory_endpoint] = {"total_count": 3, "artifacts": rows}
        result = self.inspect()
        self.assert_rejected(result, "artifact_inventory_ambiguous")
        self.assertEqual(result["matching_count"], 3)
        self.assertEqual([row["id"] for row in result["matching_artifacts"]],
                         [9810071413, 9810071293, 9810071157])
        self.assertNotIn(self.direct_endpoint, self.calls)
        # Repeated same-ID rows are also ambiguous, not silently deduplicated.
        self.responses[self.inventory_endpoint] = {"total_count": 2, "artifacts": [self.row, self.row]}
        self.assert_rejected(self.inspect(), "artifact_inventory_ambiguous")

    def test_partial_or_malformed_inventory_fails_closed(self):
        for value, code in (
            ({"total_count": 101, "artifacts": [self.row]}, "artifact_inventory_incomplete"),
            ({"total_count": 0, "artifacts": [self.row]}, "artifact_inventory_incomplete"),
            ({"artifacts": [self.row]}, "artifact_inventory_invalid"),
            ({"total_count": True, "artifacts": [self.row]}, "artifact_inventory_invalid"),
            ({"total_count": 1, "artifacts": [None]}, "artifact_inventory_invalid"),
            ({"total_count": 1, "artifacts": {}}, "artifact_inventory_invalid"),
        ):
            with self.subTest(value=value):
                self.responses[self.inventory_endpoint] = value
                self.assert_rejected(self.inspect(), code)

    def test_invalid_metadata_never_reaches_download(self):
        for key, value in (
            ("id", True), ("id", 0), ("id", 1.5), ("id", verifier.SAFE_INTEGER + 1),
            ("digest", "sha256:" + "z" * 64), ("digest", None),
            ("size_in_bytes", True), ("size_in_bytes", 0),
            ("size_in_bytes", verifier.MAX_ARCHIVE_BYTES + 1),
            ("expired", "false"), ("expired", None),
            ("archive_download_url", "https://attacker.invalid/archive"),
            ("workflow_run", []),
        ):
            with self.subTest(key=key, value=value):
                self.calls.clear()
                self.responses[self.inventory_endpoint]["artifacts"] = [dict(self.row, **{key: value})]
                self.assert_rejected(self.inspect(), "artifact_metadata_invalid")
                self.assertNotIn(self.direct_endpoint, self.calls)

    def test_wrong_source_run_and_repository_are_rejected(self):
        for key, value in (
            ("id", 902), ("id", True), ("head_sha", "b" * 40),
            ("head_branch", "other"), ("repository_id", 18),
            ("head_repository_id", 18), ("repository_id", True),
        ):
            with self.subTest(key=key):
                row = copy.deepcopy(self.row)
                row["workflow_run"][key] = value
                self.responses[self.inventory_endpoint]["artifacts"] = [row]
                self.assert_rejected(self.inspect(), "artifact_metadata_invalid")

    def test_direct_api_cannot_substitute_another_artifact(self):
        for key, value, expected in (
            ("id", 702, "artifact_metadata_invalid"),
            ("digest", "sha256:" + "b" * 64, "artifact_list_direct_mismatch"),
            ("size_in_bytes", len(self.raw) + 1, "artifact_list_direct_mismatch"),
            ("expired", True, "artifact_expired"),
        ):
            with self.subTest(key=key):
                self.responses[self.direct_endpoint] = dict(self.row, **{key: value})
                self.assert_rejected(self.inspect(), expected)
                self.assertNotIn(self.zip_endpoint, self.calls)

    def test_archive_hash_and_size_are_verified(self):
        for raw, code in (
            (self.raw[:-1], "archive_size_mismatch"),
            (self.raw[:-1] + bytes([self.raw[-1] ^ 1]), "archive_digest_mismatch"),
            (self.raw + b"x", "api_response_too_large"),
        ):
            with self.subTest(code=code):
                self.responses[self.zip_endpoint] = raw
                self.assert_rejected(self.inspect(), code)

    def test_current_job_run_can_be_in_progress_but_failed_runs_cannot(self):
        self.responses[self.run_endpoint].update(status="completed", conclusion="success")
        self.assertEqual(self.inspect()["status"], "transport_verified")
        for key, value in (
            ("run_attempt", 1), ("id", True), ("event", "pull_request"),
            ("head_branch", "feature"), ("head_sha", "b" * 40),
            ("path", ".github/workflows/unrelated.yml"),
            ("status", "queued"), ("conclusion", "failure"),
        ):
            with self.subTest(key=key):
                self.responses[self.run_endpoint] = dict(self.run, **{key: value})
                self.assert_rejected(self.inspect(), "workflow_run_identity_invalid")
        self.responses[self.run_endpoint] = copy.deepcopy(self.run)
        self.responses[self.run_endpoint]["head_repository"]["full_name"] = "fork/repository"
        self.assert_rejected(self.inspect(), "workflow_run_identity_invalid")

    def test_strict_json_rejects_duplicate_nonfinite_and_wrong_type(self):
        for raw, code in (
            (b'{"id":1,"id":2}', "api_json_invalid"),
            (b'{"secret":NaN}', "api_json_invalid"),
            (b'{"secret":Infinity}', "api_json_invalid"),
            (b'{"secret":1e999}', "api_json_invalid"),
            (b'\xff', "api_json_invalid"),
            (b'[]', "api_object_required"),
        ):
            with self.subTest(raw=raw):
                self.responses[self.run_endpoint] = raw
                self.assert_rejected(self.inspect(), code)

    def test_diagnostic_is_bounded_and_excludes_untrusted_text(self):
        secret = "ghp_" + "secretvalue" * 100
        rows = [dict(self.row, id=i + 1, description=secret, url=secret) for i in range(100)]
        self.responses[self.inventory_endpoint] = {"total_count": 100, "artifacts": rows}
        result = self.inspect()
        self.assert_rejected(result, "artifact_inventory_ambiguous")
        self.assertEqual(len(result["matching_artifacts"]), verifier.MAX_DIAGNOSTIC_MATCHES)
        self.assertTrue(result["matching_artifacts_truncated"])
        encoded = json.dumps(result)
        self.assertNotIn("secretvalue", encoded)
        self.assertLess(len(encoded), verifier.MAX_DIAGNOSTIC_BYTES)
        self.assertEqual(result["matching_count"], 100)

    def test_oversized_api_body_is_rejected_before_json_parsing(self):
        self.responses[self.run_endpoint] = b"x" * (verifier.MAX_JSON_BYTES + 1)
        result = self.inspect()
        self.assert_rejected(result, "api_response_too_large")
        self.assertEqual(result["stage"], "workflow_run")

    def test_invalid_context_does_not_make_network_requests(self):
        for key, value in (
            ("repository", "--bad"), ("source_sha", "secret"), ("family", "unknown"),
            ("run_id", True), ("run_id", 0), ("run_attempt", -1),
        ):
            with self.subTest(key=key):
                context = dict(self.context, **{key: value})
                self.assert_rejected(
                    verifier.inspect_upload(**context, stream=self.stream), "context_invalid",
                )
        self.assertEqual(self.calls, [])

    def test_transport_exceptions_do_not_leak_error_text(self):
        def broken(endpoint, limit, sink):
            raise OSError("token=do-not-copy-this-error")
        result = verifier.inspect_upload(**self.context, stream=broken)
        self.assert_rejected(result, "transport_verifier_error")
        self.assertNotIn("do-not-copy", json.dumps(result))

    def test_diagnostic_file_refuses_overwrite_and_is_not_a_receipt(self):
        result = self.inspect()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "transport.json"
            verifier.write_diagnostic(path, result)
            self.assertEqual(json.loads(path.read_text()), result)
            with self.assertRaises(FileExistsError):
                verifier.write_diagnostic(path, result)
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                link = Path(directory) / "link.json"
                link.symlink_to(path)
                with self.assertRaises(FileExistsError):
                    verifier.write_diagnostic(link, result)

    def test_cli_failure_preserves_diagnostic_and_nonzero_exit(self):
        self.responses[self.inventory_endpoint] = {"total_count": 2, "artifacts": [self.row, self.row]}
        result = self.inspect()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "diagnostic.json"
            args = [
                "verifier", "--repository", self.context["repository"],
                "--source-sha", self.context["source_sha"], "--run-id", "901",
                "--run-attempt", "2", "--family", "negative", "--output", str(target),
            ]
            with patch.object(sys, "argv", args), patch.object(verifier, "inspect_upload", return_value=result):
                with patch("sys.stderr", new_callable=io.StringIO) as stderr:
                    self.assertEqual(verifier.main(), 1)
                self.assertEqual(stderr.getvalue().strip(), "artifact_inventory_ambiguous")
            self.assertEqual(json.loads(target.read_text())["matching_count"], 2)

    def test_stream_hard_limits_deadline_and_exit_status(self):
        output = io.BytesIO()
        verifier.stream_command([sys.executable, "-c", "print('bounded')"], 64, output.write)
        self.assertEqual(output.getvalue().strip(), b"bounded")
        for code, limit, timeout, expected in (
            ("import sys;sys.stdout.write('x'*1000000)", 16, 5, "api_response_too_large"),
            ("import time;time.sleep(10)", 64, 0.1, "api_timeout"),
            ("import sys,time;sys.stdout.write('x');sys.stdout.flush();time.sleep(10)",
             64, 0.1, "api_timeout"),
            ("import sys;sys.stderr.write('secret-password');sys.exit(2)", 64, 5, "api_request_failed"),
        ):
            with self.subTest(expected=expected, code=code):
                start = time.monotonic()
                with self.assertRaisesRegex(verifier.ArtifactIdentityError, "^" + expected + "$"):
                    verifier.stream_command([sys.executable, "-c", code], limit, lambda _: None, timeout=timeout)
                self.assertLess(time.monotonic() - start, 5)

    def test_workflow_guard_is_read_only_and_retains_only_its_diagnostic(self):
        workflow = (ROOT / ".github/workflows/bounded-planar-sealed-technical-attestor.yml").read_text()
        invocation = workflow.split("\n  verify-upload-identity:\n", 1)[1]
        self.assertIn("needs: attest", invocation)
        self.assertIn("uses: ./.github/workflows/bounded-planar-upload-identity.yml", invocation)
        self.assertIn("family-id: ${{ inputs.family-id }}", invocation)
        self.assertIn("source-sha: ${{ inputs.source-sha }}", invocation)
        self.assertNotIn("id-token:", invocation)
        self.assertNotIn("attestations: write", invocation)
        self.assertNotIn("actions/checkout@", workflow)
        self.assertNotIn("actions/setup-python@", workflow)
        self.assertNotIn("pip install", workflow)
        guard = (ROOT / ".github/workflows/bounded-planar-upload-identity.yml").read_text()
        self.assertIn("actions: read", guard)
        self.assertIn("contents: read", guard)
        self.assertNotIn("id-token:", guard)
        self.assertNotIn("attestations: write", guard)
        self.assertNotIn("continue-on-error", guard)
        self.assertNotIn("secrets: inherit", guard)
        self.assertIn("persist-credentials: false", guard)
        self.assertIn("ref: ${{ env.SOURCE_SHA }}", guard)
        self.assertIn("verify_supplemental_artifact_identity.py", guard)
        self.assertIn("if: ${{ always() }}", guard)
        self.assertIn("path: ${{ runner.temp }}/supplemental-upload-identity.json", guard)
        self.assertIn("bounded-planar-${{ inputs.family-id }}-upload-identity-", guard)
        self.assertNotIn("path: .ci", guard)
        self.assertNotIn("rm -", guard)


if __name__ == "__main__":
    unittest.main()
