"""Socket-free fixture contracts; these do not claim a browser/hosted pass."""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from structural_analysis.execution.job_http_api import DurableJobHttpApi


SPEC = importlib.util.spec_from_file_location(
    "rc_lifecycle_http_fixture",
    Path(__file__).parent / "frontend/rc_lifecycle_http_fixture.py",
)
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class FixtureContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="structural-rc-browser-")
        self.workspace = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def headers(self):
        return {
            "X-Structural-Tenant": "a",
            "Authorization": f"Bearer {fixture.TENANTS['a']}",
        }

    def test_driver_has_no_submit_or_report_creation_commands(self):
        supervisor = fixture.Supervisor(self.workspace)
        try:
            for command in ("submit", "save_prices", "inject_result", "mock_review"):
                with self.assertRaisesRegex(ValueError, "unsupported stdin command"):
                    supervisor.command({"command": command})
            with fixture.sqlite3.connect(
                supervisor.store / "jobs.sqlite3"
            ) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0
                )
        finally:
            supervisor.close()

    def test_http_mount_has_no_process_control_backdoor(self):
        application = fixture.build_application(self.workspace)
        for path in ("/v1/restart", "/v1/fixture/complete", "/v1/fixture/kill"):
            statuses = []
            body = b"{}"
            response = application(
                {
                    "PATH_INFO": path,
                    "REQUEST_METHOD": "POST",
                    "CONTENT_LENGTH": str(len(body)),
                    "CONTENT_TYPE": "application/json",
                    "wsgi.input": io.BytesIO(body),
                    "HTTP_X_STRUCTURAL_TENANT": "a",
                    "HTTP_AUTHORIZATION": f"Bearer {fixture.TENANTS['a']}",
                },
                lambda status, headers: statuses.append(status),
            )
            self.assertTrue(b"".join(response))
            self.assertTrue(statuses[0].startswith("404"))

    def test_http_guard_records_and_rejects_all_numerical_entrypoints(self):
        with fixture.forbid_numerical_calls(self.workspace):
            for function in (
                fixture.rc_api.analyze_bounded_rc_fiber_direct_control,
                fixture.rc_api.validate_bounded_rc_fiber_direct_control_artifacts,
                fixture.paths._execute_raw,
                fixture.newton.newton_raphson_vector,
            ):
                with self.assertRaisesRegex(AssertionError, "zero numerical calls"):
                    function()
        rows = (
            (self.workspace / "http-numerical-attempts.jsonl").read_text().splitlines()
        )
        self.assertEqual(len(rows), 4)

    def test_actual_worker_death_restore_and_report_inspection_without_sockets(self):
        supervisor = fixture.Supervisor(self.workspace)
        api = DurableJobHttpApi(fixture.service(supervisor.store))
        try:
            # Only this socket-free contract test uses the adapter directly.
            # The hosted Playwright scenario submits and saves through the UI.
            submitted = api.handle(
                "POST",
                "/v1/jobs",
                headers={
                    **self.headers(),
                    "Idempotency-Key": "fixture-contract-test",
                },
                body=fixture.canonical(fixture.authored_request()),
            )
            self.assertEqual(submitted.status, 202)
            job = json.loads(submitted.body)
            job_id = job["job_id"]
            first = supervisor.command({"command": "first_checkpoint"})
            self.assertEqual(first["actual_calls"], {"analysis": 1, "verification": 1})
            killed = supervisor.command({"command": "kill_first"})
            self.assertEqual(killed["signal"], "SIGKILL")
            restored = supervisor.command({"command": "resume_ready"})
            self.assertEqual(restored["checkpoint_hash"], first["checkpoint_hash"])
            self.assertNotEqual(restored["pid"], first["pid"])
            completed = supervisor.command({"command": "complete"})
            self.assertEqual(completed["job"]["status"], "succeeded")
            supervisor.command({"command": "begin_prices", "job_id": job_id})
            result = completed["job"]["result"]
            prices = {
                "concrete_per_m3": 120.0,
                "rebar_per_kg": 2.0,
                "currency": "USD",
                "as_of": "2026-10-07",
                "source": "authored fixture contract declaration",
            }
            with fixture.forbid_numerical_calls(self.workspace):
                for concrete in (120.0, 150.0):
                    saved = api.handle(
                        "POST",
                        f"/v1/jobs/{job_id}/rc-quantity-reports",
                        headers=self.headers(),
                        body=fixture.canonical(
                            {
                                "expected_request_hash": job["request"]["content_hash"],
                                "expected_result_artifact_hash": result["content_hash"],
                                "declared_prices": {
                                    **prices,
                                    "concrete_per_m3": concrete,
                                },
                            }
                        ),
                    )
                    self.assertEqual(saved.status, 200, saved.body)
                proof = supervisor.command(
                    {"command": "verify_prices", "job_id": job_id}
                )
                self.assertTrue(proof["numerical_state_unchanged"])
                self.assertEqual([ref["revision"] for ref in proof["reports"]], [1, 2])
                report = supervisor.command(
                    {
                        "command": "inspect_report",
                        "job_id": job_id,
                        "report_id": proof["reports"][1]["report_id"],
                    }
                )
                self.assertEqual(report["sha256"], proof["reports"][1]["content_hash"])
            for headers, expected in (
                ({**self.headers(), "Authorization": "Bearer wrong-test-token"}, 401),
                (
                    {
                        "X-Structural-Tenant": "b",
                        "Authorization": f"Bearer {fixture.TENANTS['b']}",
                    },
                    404,
                ),
            ):
                self.assertEqual(
                    api.handle("GET", f"/v1/jobs/{job_id}", headers=headers).status,
                    expected,
                )
        finally:
            supervisor.close()
        self.assertTrue(
            all(row["child"].poll() is not None for row in supervisor.processes)
        )


if __name__ == "__main__":
    unittest.main()
