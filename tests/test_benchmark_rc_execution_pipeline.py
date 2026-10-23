"""Pure driver contracts; no project import, solver execution or signal timer use."""

import copy
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/benchmark_rc_execution_pipeline.py"
SPEC = importlib.util.spec_from_file_location("rc_execution_pipeline_pure_test_driver", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


def result_payload():
    return {
        "result_hash": "backend-specific-result-hash",
        "configuration": {
            "material_execution_backend": "python",
            "matrix_backend": DRIVER.DENSE,
            "load_steps": 2,
            "nested": {"result_hash": "keep-this-nested-value"},
        },
        "physical": {"force_n": [1.0, -2.0], "tolerance": 1.0e-9},
        "authority": {"physical_validation": False, "release": "not_qualified"},
        "other": {"matrix_backend": "keep-this-unrelated-value"},
    }


class FakeResult:
    status = "ready"

    def __init__(self, value=None, checkpoint=b'{"state":"synthetic"}\n'):
        self.value = result_payload() if value is None else value
        self.checkpoint = checkpoint

    def to_dict(self):
        return self.value

    def checkpoint_artifact(self):
        return self.checkpoint


class FakeAPI:
    def __init__(self, results):
        self.results = iter(results)
        self.analyze_calls = []
        self.validate_calls = []

    def analyze_public_rc_fiber_frame(self, model, config):
        self.analyze_calls.append((model, config))
        return next(self.results)

    def validate_public_rc_fiber_frame_result(self, result):
        self.validate_calls.append(result)
        return SimpleNamespace(contract_pass=True)


class FakeLoader:
    def __init__(self):
        self.calls = []
        self.model = object()

    def load_neutral_json_bytes(self, data):
        self.calls.append(data)
        return self.model


class FakeBudget:
    def __init__(self, seconds):
        self.seconds = seconds

    def remaining(self):
        return self.seconds

    @contextmanager
    def api_call(self):
        yield


class BenchmarkRCExecutionPipelineTests(unittest.TestCase):
    def test_returned_matrix_backend_must_match_the_requested_execution(self):
        value = result_payload()
        DRIVER.execution_configuration(FakeResult(value), DRIVER.DENSE)
        value["configuration"]["matrix_backend"] = "numpy_dense_ndarray"
        DRIVER.execution_configuration(FakeResult(value), DRIVER.DENSE)
        with self.assertRaisesRegex(RuntimeError, "no fallback"):
            DRIVER.execution_configuration(FakeResult(value), DRIVER.SPARSE)
        value["configuration"]["matrix_backend"] = DRIVER.SPARSE
        DRIVER.execution_configuration(FakeResult(value), DRIVER.SPARSE)
        with self.assertRaisesRegex(RuntimeError, "no fallback"):
            DRIVER.execution_configuration(FakeResult(value), DRIVER.DENSE)

    def test_normalization_removes_only_three_metadata_fields_and_deep_copies(self):
        value = result_payload()
        original = copy.deepcopy(value)
        expected = copy.deepcopy(value)
        del expected["result_hash"]
        del expected["configuration"]["material_execution_backend"]
        del expected["configuration"]["matrix_backend"]

        normalized = DRIVER.normalize_result(value)

        self.assertEqual(normalized, expected)
        self.assertEqual(value, original)
        normalized["physical"]["force_n"][0] = 999.0
        normalized["configuration"]["nested"]["result_hash"] = "changed-copy"
        self.assertEqual(value, original)

    def test_fingerprints_bind_exact_checkpoint_bytes_and_unchanged_numerical_values(self):
        result = FakeResult()
        original = copy.deepcopy(result.value)
        fingerprint, normalized, checkpoint = DRIVER.fingerprint_result(result)
        expected_bytes = json.dumps(
            normalized, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        self.assertEqual(fingerprint["numerical_sha256"], hashlib.sha256(expected_bytes).hexdigest())
        self.assertEqual(fingerprint["checkpoint_sha256"], hashlib.sha256(result.checkpoint).hexdigest())
        self.assertEqual(checkpoint, result.checkpoint)
        self.assertEqual(result.value, original)

        metadata_only = copy.deepcopy(original)
        metadata_only["result_hash"] = "another-result-hash"
        metadata_only["configuration"]["matrix_backend"] = "sparse"
        metadata_only["configuration"]["material_execution_backend"] = "native"
        same, _, _ = DRIVER.fingerprint_result(FakeResult(metadata_only, checkpoint))
        self.assertEqual(same, fingerprint)
        changed_value = copy.deepcopy(original)
        changed_value["physical"]["force_n"][0] = 1.25
        changed, _, _ = DRIVER.fingerprint_result(FakeResult(changed_value, checkpoint + b" "))
        self.assertNotEqual(changed["numerical_sha256"], fingerprint["numerical_sha256"])
        self.assertNotEqual(changed["checkpoint_sha256"], fingerprint["checkpoint_sha256"])

    def test_profile_buckets_are_exclusive_and_sum_only_function_self_time(self):
        cases = [
            ("/source/materials/steel.py", "integrate", "material"),
            ("/source/assembly/frame.py", "assemble", "assembly"),
            ("/site/scipy/linalg/basic.py", "solve", "solve"),
            ("/stdlib/json/encoder.py", "iterencode", "canonical_json"),
            ("/site/jsonschema/validators.py", "validate", "schema"),
            ("/source/contracts/state.py", "replay_state", "proof_state"),
            ("~", "<built-in method array>", "other"),
        ]
        self.assertEqual({category for _, _, category in cases}, set(DRIVER.CATEGORIES))
        stats = {}
        expected_groups = {}
        for index, (filename, function, category) in enumerate(cases, 1):
            self.assertEqual(DRIVER.profile_category(filename, function), category)
            self_time = float(index)
            stats[(filename, index, function)] = (index, index + 1, self_time, 1.0e9, {})
            expected_groups[category] = self_time
        self.assertEqual(DRIVER.profile_category(r"C:\source\materials\steel.py", "integrate"), "material")
        self.assertEqual(DRIVER.profile_category("/source/schema.py", "canonical_json"), "schema")
        self.assertEqual(DRIVER.profile_category("/unknown.py", "global_tangent"), "assembly")
        self.assertEqual(DRIVER.profile_category("/unknown.py", "checkpoint"), "proof_state")
        fake_stats = SimpleNamespace(stats=stats, total_tt=sum(expected_groups.values()))

        summary = DRIVER.summarize_profile(fake_stats)

        self.assertEqual(summary["category_self_seconds"], expected_groups)
        self.assertEqual(summary["category_self_seconds_sum"], fake_stats.total_tt)
        self.assertEqual(summary["total_self_seconds"], 28.0)
        self.assertEqual([row["self_seconds"] for row in summary["functions"]], list(range(7, 0, -1)))
        self.assertEqual(summary["functions"][0]["primitive_calls"], 7)
        self.assertEqual(summary["functions"][0]["calls"], 8)
        with self.assertRaisesRegex(RuntimeError, "do not sum"):
            DRIVER.summarize_profile(SimpleNamespace(stats=stats, total_tt=1.0e9))

    def test_loaded_source_identities_hash_only_verified_fake_project_modules(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "checkout"
            package = root / "src/structural_analysis"
            package.mkdir(parents=True)
            init = package / "__init__.py"
            fake = package / "fake.py"
            init.write_bytes(b"# fake package source, never imported\n")
            fake.write_bytes(b"sentinel = 7\n")
            modules = {
                "structural_analysis": SimpleNamespace(__file__=str(init)),
                "structural_analysis.fake": SimpleNamespace(__file__=str(fake)),
                "unrelated": SimpleNamespace(__file__=str(Path(raw) / "not-read.py")),
            }
            identities = DRIVER.loaded_project_sources(root, modules)
            self.assertEqual(set(identities), {str(init.resolve()), str(fake.resolve())})
            self.assertEqual(identities[str(fake.resolve())]["bytes"], len(b"sentinel = 7\n"))
            self.assertEqual(identities[str(fake.resolve())]["sha256"], hashlib.sha256(b"sentinel = 7\n").hexdigest())
            namespace = {"structural_analysis": SimpleNamespace(__path__=[str(package)])}
            self.assertEqual(DRIVER.loaded_project_sources(root, namespace), {})

    def test_wrong_or_preloaded_roots_are_rejected_before_any_project_import(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / "checkout"
            package = root / "src/structural_analysis"
            package.mkdir(parents=True)
            (package / "__init__.py").write_bytes(b"# never imported\n")
            wrong = Path(raw) / "wrong.py"
            wrong.write_bytes(b"# another checkout, never imported\n")
            for name in ["structural_analysis", "structural_analysis.fake"]:
                with self.subTest(module=name), self.assertRaisesRegex(RuntimeError, "another source root"):
                    DRIVER.loaded_project_sources(root, {name: SimpleNamespace(__file__=str(wrong))})
            for module in [SimpleNamespace(), SimpleNamespace(__path__=[str(wrong.parent)])]:
                with self.assertRaisesRegex(RuntimeError, "no verified source origin"):
                    DRIVER.loaded_project_sources(root, {"structural_analysis": module})
            before_path = list(sys.path)
            with patch.object(DRIVER, "loaded_project_sources", side_effect=RuntimeError("wrong preloaded root")), \
                    patch.object(DRIVER.importlib, "import_module") as imported:
                with self.assertRaisesRegex(RuntimeError, "wrong preloaded root"):
                    DRIVER.load_runtime(root, DRIVER.DENSE)
                imported.assert_not_called()
            self.assertEqual(sys.path, before_path)

    def test_source_custody_rejects_missing_and_changed_files_but_allows_new_sources(self):
        before = {"/synthetic/first.py": {"sha256": "first"}}
        DRIVER.verify_unchanged(before, {
            "/synthetic/first.py": {"sha256": "first"},
            "/synthetic/late.py": {"sha256": "late"},
        })
        for after in [{}, {"/synthetic/first.py": {"sha256": "changed"}}]:
            with self.subTest(after=after), self.assertRaisesRegex(RuntimeError, "source changed"):
                DRIVER.verify_unchanged(before, after)

    def test_owned_report_preserves_existing_files_symlinks_and_temporary_collisions(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            existing = root / "existing.json"
            existing.write_bytes(b"foreign report\n")
            with self.assertRaises(FileExistsError):
                DRIVER.OwnedReport(existing)
            link = root / "report-link.json"
            link.symlink_to(existing)
            with self.assertRaises(FileExistsError):
                DRIVER.OwnedReport(link)
            self.assertTrue(link.is_symlink())
            self.assertEqual(existing.read_bytes(), b"foreign report\n")
            owner = DRIVER.OwnedReport(root / "owned.json")
            collision = owner.path.with_name(f".{owner.path.name}.{os.getpid()}.1.tmp")
            collision.write_bytes(b"another writer's temporary file\n")
            with self.assertRaises(FileExistsError):
                owner.save({"status": "must-not-replace"})
            self.assertEqual(collision.read_bytes(), b"another writer's temporary file\n")
            self.assertEqual(owner.path.read_bytes(), b"{}\n")

    def test_owned_report_updates_atomically_and_preserves_failed_updates_and_sidecars(self):
        with tempfile.TemporaryDirectory() as raw:
            owner = DRIVER.OwnedReport(Path(raw) / "report.json")
            with patch.object(DRIVER.os, "replace", wraps=os.replace) as replace:
                owner.save({"status": "running", "cases": []})
                owner.save({"status": "completed", "cases": [{"authority": False}]})
                self.assertEqual(replace.call_count, 2)
                self.assertTrue(all(call.args[1] == owner.path for call in replace.call_args_list))
            expected = {"status": "completed", "cases": [{"authority": False}]}
            self.assertEqual(json.loads(owner.path.read_text()), expected)
            with self.assertRaises(ValueError):
                owner.save({"invalid": float("nan")})
            self.assertEqual(json.loads(owner.path.read_text()), expected)
            self.assertEqual(list(Path(raw).glob("*.tmp")), [])
            checkpoint = b"synthetic checkpoint\n"
            identity = owner.sidecar("1x2", "checkpoint.json", checkpoint)
            with self.assertRaises(FileExistsError):
                owner.sidecar("1x2", "checkpoint.json", b"overwrite")
            self.assertEqual(Path(identity["path"]).read_bytes(), checkpoint)

    def test_argument_parser_defaults_and_strict_admission_without_runtime_loading(self):
        base = ["--source-root", "/synthetic/source", "--output", "/synthetic/report.json"]
        with patch.object(DRIVER.os, "sched_getaffinity", return_value={0, 1, 2, 3}):
            defaults = DRIVER.parse_arguments(base)
            self.assertFalse(defaults.profile)
            self.assertFalse(defaults.prepared)
            self.assertEqual(defaults.cases, ["1x2"])
            self.assertEqual(defaults.repetitions, 5)
            self.assertEqual(defaults.matrix_backend, DRIVER.DENSE)
            valid = DRIVER.parse_arguments(base + [
                "--cases", "1x2", "4x2", "--repetitions", "3", "--profile",
                "--elapsed-budget-seconds", "0.25", "--matrix-backend", DRIVER.SPARSE,
                "--steel-library", "/synthetic/native.so", "--steel-workers", "4", "--prepared",
            ])
            self.assertTrue(valid.profile)
            self.assertTrue(valid.prepared)
            self.assertEqual(valid.cases, ["1x2", "4x2"])
            invalid = [
                ["--cases", "unknown"], ["--cases", "1x2", "1x2"],
                ["--repetitions", "2"], ["--repetitions", "21"], ["--repetitions", "1.5"],
                ["--matrix-backend", "implicit-fallback"], ["--prepared"],
                ["--steel-workers", "2"], ["--steel-workers", "0"],
                ["--steel-library", "/synthetic/native.so", "--steel-workers", "5"],
            ]
            invalid.extend(["--elapsed-budget-seconds", value] for value in ["0", "-1", "3600.1", "nan", "inf"])
            for extra in invalid:
                with self.subTest(arguments=extra), redirect_stderr(io.StringIO()) as stderr:
                    with self.assertRaises(SystemExit) as error:
                        DRIVER.parse_arguments(base + extra)
                    self.assertEqual(error.exception.code, 2)
                    self.assertIn("usage:", stderr.getvalue())

    def test_case_remaining_budget_uses_deadline_without_installing_a_signal(self):
        with patch.object(DRIVER.time, "monotonic", return_value=100.0):
            budget = DRIVER.CaseBudget(5.0)
        with patch.object(DRIVER.time, "monotonic", return_value=102.5), \
                patch.object(DRIVER.signal, "setitimer") as timer:
            self.assertEqual(budget.remaining(), 2.5)
            timer.assert_not_called()
        for now in [105.0, 106.0]:
            with patch.object(DRIVER.time, "monotonic", return_value=now):
                with self.assertRaisesRegex(DRIVER.CaseBudgetExceeded, "no automatic retry"):
                    budget.remaining()

    def test_fake_pipeline_records_one_first_call_and_three_matching_samples(self):
        with tempfile.TemporaryDirectory() as raw:
            owner = DRIVER.OwnedReport(Path(raw) / "report.json")
            report = {"cases": []}
            result = FakeResult()
            api = FakeAPI([result] * 4)
            loader = FakeLoader()
            config = object()
            args = SimpleNamespace(repetitions=3, elapsed_budget_seconds=30.0, profile=False, matrix_backend=DRIVER.DENSE)
            snapshots = []
            original_save = owner.save

            def save_snapshot(value):
                snapshots.append(copy.deepcopy(value))
                original_save(value)

            clock = [0, 1000, 1000, 3000, 3000, 6000, 6000, 10000]
            with patch.object(DRIVER, "CaseBudget", FakeBudget), \
                    patch.object(DRIVER, "peak_rss", return_value={"bytes": 7}), \
                    patch.object(DRIVER.time, "perf_counter_ns", side_effect=clock), \
                    patch.object(owner, "save", side_effect=save_snapshot), \
                    patch.object(DRIVER.signal, "setitimer") as timer, \
                    redirect_stdout(io.StringIO()) as stdout:
                DRIVER.measure_case(args, "1x2", api, loader, config,
                                    lambda members, layers: {"members": members, "layers": layers},
                                    owner, report, None)
                timer.assert_not_called()
            row = report["cases"][0]
            self.assertEqual(len(api.analyze_calls), 4)
            self.assertEqual(len(api.validate_calls), 4)
            self.assertTrue(all(model is loader.model and used is config for model, used in api.analyze_calls))
            self.assertEqual(loader.calls, [b'{"layers":2,"members":1}'])
            self.assertEqual(row["first_call_ns"], 1000)
            self.assertEqual(row["samples_ns"], [2000, 3000, 4000])
            self.assertEqual(row["median_ns"], 3000)
            self.assertEqual(row["sample_fingerprints"], [row["first_fingerprint"]] * 3)
            self.assertEqual(Path(row["first_checkpoint"]["path"]).read_bytes(), result.checkpoint)
            self.assertEqual(row["status"], "completed")
            self.assertTrue(row["all_steady_samples_match_first"])
            self.assertNotIn("active_sample", row)
            self.assertNotIn("profile", row)
            self.assertEqual(snapshots[0]["cases"][0]["status"], "preparing")
            self.assertEqual(snapshots[-1]["cases"][0]["status"], "completed")
            self.assertEqual(json.loads(owner.path.read_text()), report)
            stages = [json.loads(line) for line in stdout.getvalue().splitlines()]
            self.assertEqual([stage["sample"] for stage in stages], [0, 1, 2, 3])

    def test_fake_pipeline_refuses_and_retains_a_changed_sample_fingerprint(self):
        with tempfile.TemporaryDirectory() as raw:
            owner = DRIVER.OwnedReport(Path(raw) / "report.json")
            report = {"cases": []}
            changed = result_payload()
            changed["physical"]["force_n"][0] = 3.0
            api = FakeAPI([FakeResult(), FakeResult(changed)])
            args = SimpleNamespace(repetitions=3, elapsed_budget_seconds=30.0, profile=False, matrix_backend=DRIVER.DENSE)
            with patch.object(DRIVER, "CaseBudget", FakeBudget), \
                    patch.object(DRIVER, "peak_rss", return_value={"bytes": 7}), \
                    patch.object(DRIVER.time, "perf_counter_ns", side_effect=[0, 10, 10, 30]), \
                    patch.object(DRIVER.signal, "setitimer") as timer, \
                    redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "fingerprint changed"):
                    DRIVER.measure_case(args, "1x2", api, FakeLoader(), object(),
                                        lambda members, layers: {"members": members, "layers": layers},
                                        owner, report, None)
                timer.assert_not_called()
            row = report["cases"][0]
            self.assertEqual(len(api.analyze_calls), 2)
            self.assertEqual(len(api.validate_calls), 2)
            self.assertEqual(row["samples_ns"], [20])
            self.assertEqual(len(row["sample_fingerprints"]), 1)
            self.assertNotEqual(row["sample_fingerprints"][0], row["first_fingerprint"])
            self.assertEqual(row["status"], "running_steady_api_call")
            self.assertNotIn("all_steady_samples_match_first", row)

    def test_expired_diagnostic_entry_preserves_budget_error_and_empty_profile_records(self):
        deadline_error = DRIVER.CaseBudgetExceeded("diagnostic deadline before profiler start")

        class DiagnosticEntryBudget(FakeBudget):
            def __init__(self, seconds):
                super().__init__(seconds)
                self.entries = 0

            @contextmanager
            def api_call(self):
                self.entries += 1
                if self.entries == 5:
                    raise deadline_error
                yield

        class FakeEmptyProfiler:
            def __init__(self):
                self.stats = {}
                self.create_calls = 0
                self.dump_calls = []

            def create_stats(self):
                self.create_calls += 1

            def dump_stats(self, path):
                self.dump_calls.append(path)
                Path(path).write_bytes(b"synthetic empty profile bytes\n")

        with tempfile.TemporaryDirectory() as raw:
            owner = DRIVER.OwnedReport(Path(raw) / "report.json")
            report = {"cases": []}
            api = FakeAPI([FakeResult()] * 4)
            profiler = FakeEmptyProfiler()
            args = SimpleNamespace(repetitions=3, elapsed_budget_seconds=30.0,
                                   profile=True, matrix_backend=DRIVER.DENSE)
            with patch.object(DRIVER, "CaseBudget", DiagnosticEntryBudget), \
                    patch.object(DRIVER, "peak_rss", return_value={"bytes": 7}), \
                    patch.object(DRIVER.time, "perf_counter_ns", side_effect=[0, 10, 10, 30, 30, 60, 60, 100]), \
                    patch.object(DRIVER.cProfile, "Profile", return_value=profiler) as profile_factory, \
                    patch.object(DRIVER.pstats, "Stats") as stats, \
                    patch.object(DRIVER.signal, "setitimer") as timer, \
                    redirect_stdout(io.StringIO()):
                with self.assertRaises(DRIVER.CaseBudgetExceeded) as raised:
                    DRIVER.measure_case(args, "1x2", api, FakeLoader(), object(),
                                        lambda members, layers: {"members": members, "layers": layers},
                                        owner, report, None)
                self.assertIs(raised.exception, deadline_error)
                profile_factory.assert_called_once_with()
                stats.assert_not_called()
                timer.assert_not_called()
            row = report["cases"][0]
            self.assertEqual(len(api.analyze_calls), 4)
            self.assertEqual(len(api.validate_calls), 4)
            self.assertEqual(row["samples_ns"], [20, 30, 40])
            self.assertEqual(row["sample_fingerprints"], [row["first_fingerprint"]] * 3)
            self.assertEqual(row["status"], "running_separate_diagnostic_profile")
            self.assertNotIn("all_steady_samples_match_first", row)
            self.assertEqual(profiler.create_calls, 1)
            self.assertEqual(len(profiler.dump_calls), 1)
            profile = row["profile"]
            self.assertEqual(profile["status"], "interrupted")
            self.assertFalse(profile["has_function_records"])
            self.assertEqual(profile["total_self_seconds"], 0.0)
            self.assertEqual(profile["category_self_seconds"], {key: 0.0 for key in DRIVER.CATEGORIES})
            self.assertEqual(profile["category_self_seconds_sum"], 0.0)
            self.assertEqual(profile["functions"], [])
            self.assertEqual(Path(profile["raw_pstats"]["path"]).read_bytes(), b"synthetic empty profile bytes\n")
            self.assertEqual(json.loads(owner.path.read_text())["cases"][0]["profile"], profile)


if __name__ == "__main__":
    unittest.main()
