"""Offline executable consumer regressions; no engineering evidence is created."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    spec = importlib.util.spec_from_file_location(
        "supplemental_consumer_under_test", ROOT / "scripts/consume_supplemental_artifact.py"
    )
    assert spec and spec.loader
    consumer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(consumer)
finally:
    sys.path.pop(0)


class SupplementalConsumerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.context = dict(
            repository="example/repo", source_sha="a" * 40, run_id=901,
            run_attempt=2, family="negative", run_json=self.root / "run.json",
            inventory_json=self.root / "inventory.json", target=self.root / "artifact",
        )
        self.run = dict(
            id=901, run_attempt=2, head_sha="a" * 40, head_branch="main",
            path=".github/workflows/bounded-planar-negative-opensees-technical.yml",
            event="push", status="completed", conclusion="success",
            repository={"id": 17, "full_name": "example/repo"},
            head_repository={"id": 17, "full_name": "example/repo"},
        )
        self.prefix = "repos/example/repo/actions/artifacts/701"
        self.row = dict(
            id=701, name="bounded-planar-negative-opensees-901-2", expired=False,
            archive_download_url="https://api.github.com/" + self.prefix + "/zip",
            workflow_run=dict(id=901, repository_id=17, head_repository_id=17,
                              head_branch="main", head_sha="a" * 40),
        )
        self.calls = []
        self.set_archive([(".ci/evidence/receipt.json", b'{"technical_credit_granted":false}')])

    def set_raw(self, raw):
        self.raw = raw
        self.row.update(size_in_bytes=len(raw), digest="sha256:" + hashlib.sha256(raw).hexdigest())
        self.inventory = dict(total_count=1, artifacts=[copy.deepcopy(self.row)])
        self.direct = copy.deepcopy(self.row)

    def set_archive(self, members):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name, body in members:
                    archive.writestr(name, body)
        self.set_raw(buffer.getvalue())

    def stream(self, endpoint, limit, sink):
        self.calls.append(endpoint)
        value = self.direct if endpoint == self.prefix else self.raw
        if endpoint not in (self.prefix, self.prefix + "/zip"):
            self.fail("unexpected endpoint")
        raw = value if isinstance(value, bytes) else json.dumps(value).encode()
        if len(raw) > limit:
            raise consumer.ArtifactIdentityError("api_response_too_large")
        for offset in range(0, len(raw), 13):
            sink(raw[offset:offset + 13])

    def write_inputs(self):
        for key, value in (("run_json", self.run), ("inventory_json", self.inventory)):
            raw = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.context[key].write_bytes(raw)

    def consume(self):
        self.write_inputs()
        return consumer.consume(**self.context, stream=self.stream)

    def assert_rejected(self, result, code=None):
        self.assertEqual(result["status"], "rejected")
        if code:
            self.assertEqual(result["error_code"], code)
        for key in ("release_authority", "independent_verification", "technical_credit_granted"):
            self.assertIs(result[key], False)
        self.assertNotIn("artifact_id", result)

    def test_exact_id_download_and_materialization_do_not_grant_authority(self):
        result = self.consume()
        self.assertEqual(result["status"], "materialized")
        self.assertEqual(result["artifact_id"], 701)
        self.assertEqual(self.calls, [self.prefix, self.prefix + "/zip"])
        self.assertTrue((self.context["target"] / ".ci/evidence/receipt.json").is_file())
        for key in ("release_authority", "independent_verification", "technical_credit_granted"):
            self.assertIs(result[key], False)

    def test_missing_is_unavailable_and_never_downloaded(self):
        self.inventory = dict(total_count=0, artifacts=[])
        result = self.consume()
        self.assertEqual((result["status"], result["availability"]), ("unavailable", "missing"))
        self.assertEqual(self.calls, [])
        self.assertFalse(self.context["target"].exists())

    def test_expired_is_unavailable_and_never_downloaded(self):
        self.inventory["artifacts"][0]["expired"] = True
        result = self.consume()
        self.assertEqual((result["status"], result["availability"]), ("unavailable", "expired"))
        self.assertEqual(self.calls, [])

    def test_expiry_between_list_and_direct_lookup_remains_unavailable(self):
        self.direct["expired"] = True
        result = self.consume()
        self.assertEqual(result["availability"], "expired")
        self.assertEqual(self.calls, [self.prefix])

    def test_three_identical_digest_artifacts_are_not_auto_selected(self):
        self.inventory = dict(total_count=3, artifacts=[
            dict(self.row, id=value) for value in (9810071413, 9810071293, 9810071157)
        ])
        result = self.consume()
        self.assert_rejected(result, "artifact_inventory_ambiguous")
        self.assertEqual(result["matching_count"], 3)
        self.assertEqual(self.calls, [])

    def test_incomplete_inventory_is_not_misreported_missing(self):
        self.inventory = dict(total_count=101, artifacts=[])
        self.assert_rejected(self.consume(), "artifact_inventory_incomplete")

    def test_consumer_refuses_in_progress_or_unsuccessful_runs(self):
        for status, conclusion in (("in_progress", None), ("completed", "failure"),
                                   ("completed", "cancelled"), ("queued", None)):
            with self.subTest(status=status, conclusion=conclusion):
                self.run.update(status=status, conclusion=conclusion)
                self.assert_rejected(self.consume(), "workflow_run_not_successful")
        self.assertEqual(self.calls, [])

    def test_wrong_source_attempt_family_repository_and_branch(self):
        original = copy.deepcopy(self.run)
        for key, value in (("head_sha", "b" * 40), ("run_attempt", 1),
                           ("path", ".github/workflows/other.yml"),
                           ("repository", {"id": 17, "full_name": "fork/repo"}),
                           ("head_branch", "feature"), ("id", True)):
            with self.subTest(key=key):
                self.run = dict(original, **{key: value})
                self.assert_rejected(self.consume(), "workflow_run_identity_invalid")
        self.assertEqual(self.calls, [])

    def test_list_direct_identity_changes_are_rejected(self):
        for key, value in (("digest", "sha256:" + "b" * 64),
                           ("size_in_bytes", len(self.raw) + 1)):
            with self.subTest(key=key):
                self.direct = dict(self.row, **{key: value})
                self.assert_rejected(self.consume(), "artifact_list_direct_mismatch")
        self.assertNotIn(self.prefix + "/zip", self.calls)

    def test_id_and_archive_url_substitution_are_rejected(self):
        for key, value in (("id", 702), ("id", True),
                           ("archive_download_url", "https://invalid.example/archive")):
            with self.subTest(key=key):
                self.direct = dict(self.row, **{key: value})
                self.assert_rejected(self.consume(), "artifact_metadata_invalid")
        self.assertNotIn(self.prefix + "/zip", self.calls)

    def test_corrupt_download_fails_before_extraction(self):
        self.raw = self.raw[:-1] + bytes([self.raw[-1] ^ 1])
        self.assert_rejected(self.consume(), "archive_digest_mismatch")
        self.assertFalse(self.context["target"].exists())

    def test_truncated_and_oversized_downloads_fail(self):
        raw = self.raw
        for value, code in ((raw[:-1], "archive_size_mismatch"),
                            (raw + b"x", "api_response_too_large")):
            with self.subTest(code=code):
                self.raw = value
                self.assert_rejected(self.consume(), code)
        self.assertFalse(self.context["target"].exists())

    def test_non_zip_bytes_with_matching_digest_fail(self):
        self.set_raw(b"not a zip")
        self.assert_rejected(self.consume(), "archive_zip_invalid")

    def test_portable_paths_reject_traversal_absolute_and_aliases(self):
        for name in ("../escape", "/absolute", "a/../../escape", "a\\escape", "a//b",
                     "a/./b", "C:/absolute", "a/CON.txt", "a/NUL", "a/trailing.",
                     "a/trailing ", "a/com1.log", "a/\u202eevil", "a/\uff41", "a/e\u0301"):
            with self.subTest(name=name):
                self.set_archive([(name, b"bad")])
                self.assert_rejected(self.consume(), "archive_member_invalid")
                self.assertFalse(self.context["target"].exists())
        self.assertFalse((self.root.parent / "escape").exists())

    def test_nul_truncated_zip_filename_is_rejected(self):
        self.set_archive([("a/bx.txt", b"bad")])
        self.set_raw(self.raw.replace(b"a/bx.txt", b"a/b\x00.txt"))
        self.assert_rejected(self.consume(), "archive_member_invalid")

    def test_symlink_and_special_entries_are_rejected(self):
        for mode in (stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600, stat.S_IFBLK | 0o600):
            with self.subTest(mode=mode):
                info = zipfile.ZipInfo("a/link")
                info.create_system = 3
                info.external_attr = mode << 16
                self.set_archive([(info, b"../../escape")])
                self.assert_rejected(self.consume(), "archive_member_invalid")

    def test_duplicates_case_aliases_and_file_directory_conflicts(self):
        for names in (("a/file", "a/file"), ("a/File", "a/file"),
                      ("a/file", "A/other"), ("a", "a/file"),
                      ("a/file", "a"), ("a/", "a/")):
            with self.subTest(names=names):
                self.set_archive([(name, b"" if name.endswith("/") else b"value") for name in names])
                self.assert_rejected(self.consume(), "archive_path_collision")
                self.assertFalse(self.context["target"].exists())

    def test_directory_entries_are_allowed_but_not_payloads_in_directories(self):
        self.set_archive([("a/", b""), ("a/empty.txt", b"")])
        self.assertEqual(self.consume()["status"], "materialized")
        self.assertTrue((self.context["target"] / "a/empty.txt").exists())
        self.context["target"] = self.root / "bad-directory"
        self.set_archive([("a/", b"hidden bytes")])
        self.assert_rejected(self.consume(), "archive_member_invalid")

    def test_zip_member_and_expansion_bounds(self):
        self.set_archive([("a/one", b"abc"), ("a/two", b"def")])
        with patch.object(consumer, "MAX_MEMBERS", 1):
            self.assert_rejected(self.consume(), "archive_member_count_invalid")
        with patch.object(consumer, "MAX_EXPANDED_BYTES", 5):
            self.assert_rejected(self.consume(), "archive_expansion_too_large")

    def test_crc_failure_removes_partially_extracted_directory(self):
        info = zipfile.ZipInfo("a/bad.txt")
        info.compress_type = zipfile.ZIP_STORED
        self.set_archive([("a/good.txt", b"fine"), (info, b"unique-content-123")])
        self.set_raw(self.raw.replace(b"unique-content-123", b"corruptcontent-123"))
        self.assert_rejected(self.consume(), "archive_zip_invalid")
        self.assertFalse(self.context["target"].exists())

    def test_unsupported_compression_is_rejected(self):
        info = zipfile.ZipInfo("a/file")
        info.compress_type = zipfile.ZIP_BZIP2
        self.set_archive([(info, b"bad")])
        self.assert_rejected(self.consume(), "archive_member_invalid")

    def test_encrypted_member_is_rejected(self):
        raw = bytearray(self.raw)
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            location = raw.index(signature) + offset
            flags = struct.unpack_from("<H", raw, location)[0]
            struct.pack_into("<H", raw, location, flags | 1)
        self.set_raw(bytes(raw))
        self.assert_rejected(self.consume(), "archive_member_invalid")

    def test_existing_target_is_preserved(self):
        self.context["target"].mkdir()
        marker = self.context["target"] / "keep.txt"
        marker.write_text("do not overwrite")
        self.assert_rejected(self.consume(), "extraction_target_exists")
        self.assertEqual(marker.read_text(), "do not overwrite")

    def test_symlink_target_and_parent_are_preserved(self):
        real = self.root / "real"
        real.mkdir()
        self.context["target"].symlink_to(real, target_is_directory=True)
        self.assert_rejected(self.consume(), "extraction_target_exists")
        self.context["target"] = self.root / "artifact" / "nested"
        self.assert_rejected(self.consume(), "extraction_parent_symlink")
        self.assertEqual(list(real.iterdir()), [])

    def test_strict_local_api_parser_rejects_duplicates_nonfinite_and_wrong_type(self):
        for field in ("run", "inventory"):
            old = copy.deepcopy(getattr(self, field))
            for raw, code in ((b'{"id":1,"id":2}', "api_json_invalid"),
                              (b'{"n":NaN}', "api_json_invalid"),
                              (b'{"n":1e999}', "api_json_invalid"),
                              (b'\xff', "api_json_invalid"), (b'[]', "api_object_required")):
                with self.subTest(field=field, raw=raw):
                    setattr(self, field, raw)
                    self.assert_rejected(self.consume(), code)
            setattr(self, field, old)

    def test_local_metadata_size_and_symlink_bounds(self):
        file = self.root / "saved.json"
        file.write_bytes(b" " * 32)
        with patch.object(consumer, "MAX_JSON_BYTES", 16):
            with self.assertRaisesRegex(consumer.ArtifactIdentityError, "api_response_too_large"):
                consumer.read_saved_api(file)
        link = self.root / "link.json"
        link.symlink_to(file)
        with self.assertRaisesRegex(consumer.ArtifactIdentityError, "saved_api_not_regular"):
            consumer.read_saved_api(link)

    def test_sensitive_response_and_exception_text_are_not_in_diagnostic(self):
        secret = "ghp_do_not_copy_this_value"
        self.inventory = dict(total_count=2, artifacts=[dict(self.row, secret=secret)] * 2)
        self.assertNotIn(secret, json.dumps(self.consume()))
        self.inventory = dict(total_count=1, artifacts=[self.row])
        self.write_inputs()
        def fail(*args):
            raise RuntimeError(secret)
        result = consumer.consume(**self.context, stream=fail)
        self.assert_rejected(result, "artifact_consumer_error")
        self.assertNotIn(secret, json.dumps(result))

    def test_cli_exit_codes_diagnostic_persistence_and_no_stale_overwrite(self):
        for status, availability, expected_code, expected_output in (
            ("materialized", None, 0, "available\n"),
            ("unavailable", "missing", 0, "missing\n"),
            ("unavailable", "expired", 0, "expired\n"),
            ("rejected", None, 1, ""),
        ):
            with self.subTest(status=status, availability=availability):
                output = self.root / f"{status}-{availability}.json"
                result = dict(status=status, error_code="artifact_inventory_ambiguous")
                if availability:
                    result["availability"] = availability
                argv = ["consumer", "--repository", "example/repo", "--source-sha", "a" * 40,
                        "--run-id", "901", "--run-attempt", "2", "--family", "negative",
                        "--run-json", "run.json", "--inventory-json", "inventory.json",
                        "--target", "artifact", "--diagnostic", str(output)]
                with patch.object(sys, "argv", argv), patch.object(consumer, "consume", return_value=result), \
                     patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                     patch("sys.stderr", new_callable=io.StringIO):
                    self.assertEqual(consumer.main(), expected_code)
                    self.assertEqual(stdout.getvalue(), expected_output)
                    self.assertEqual(json.loads(output.read_text()), result)
                    self.assertEqual(consumer.main(), 1)  # Existing diagnostic is not overwritten.


if __name__ == "__main__":
    unittest.main()
