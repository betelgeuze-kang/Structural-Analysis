"""Execute the production shell offline with its real artifact consumer.

Only GitHub transport/attestation, sleep, and the downstream receipt builder are
shims. Synthetic ZIPs and signature replies establish orchestration contracts,
not physical, cryptographic, independent-verification, or release evidence.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/product-state-current.yml"
STEP = "Download and reverify exact-SHA supplemental technical attestations"
REPOSITORY = "example/repo"
SOURCE_SHA = "a" * 40
FAMILIES = (
    (
        "linear",
        "bounded-planar-opensees-technical",
        "bounded-planar-opensees-technical",
        "bounded-planar-opensees",
    ),
    (
        "negative",
        "bounded-planar-negative-opensees-technical",
        "bounded-planar-negative-opensees",
        "bounded-planar-negative-opensees",
    ),
    (
        "scaling",
        "bounded-planar-scaling-opensees-technical",
        "bounded-planar-scaling-opensees",
        "bounded-planar-scaling-opensees",
    ),
    (
        "modal_buckling",
        "bounded-planar-modal-buckling-technical",
        "bounded-planar-modal-buckling",
        "bounded-planar-modal-buckling",
    ),
    (
        "nonlinear_material_recovery",
        "bounded-planar-nonlinear-material-recovery-technical",
        "bounded-planar-nonlinear-material-recovery",
        "bounded-planar-nonlinear-material-recovery",
    ),
)
REAL_SCRIPTS = (
    "consume_supplemental_artifact.py",
    "verify_supplemental_artifact_identity.py",
    "strict_json.py",
)


def workflow_shell() -> str:
    """Read the literal run block without a YAML dependency or shell rewrite."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    marker = f"      - name: {STEP}"
    if lines.count(marker) != 1:
        raise AssertionError("production supplemental step must exist exactly once")
    start = lines.index(marker) + 1
    while start < len(lines) and lines[start] != "        run: |":
        if lines[start].startswith("      - "):
            raise AssertionError("supplemental step lost its literal run block")
        start += 1
    result = []
    for line in lines[start + 1 :]:
        if line and not line.startswith("          "):
            break
        result.append(line[10:] if line else "")
    if not result:
        raise AssertionError("supplemental shell is empty")
    return "\n".join(result) + "\n"


# This program is installed only inside each TemporaryDirectory. It cannot call
# a real gh executable, sleep, solver, or receipt builder.
SHIM = r"""
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["SUPPLEMENTAL_TEST_ROOT"])
control = json.loads((root / "control.json").read_text())
args = sys.argv[1:]
program = Path(sys.argv[0]).name

def record(kind, **fields):
    with (root / "events.jsonl").open("a") as handle:
        handle.write(json.dumps({"kind": kind, **fields}) + "\n")

if program == "sleep":
    record("sleep", args=args)
    raise SystemExit(0)

if program == "gh":
    if args[:2] == ["attestation", "verify"]:
        handoff = Path(args[2])
        family = json.loads(handoff.read_text())["family_id"]
        record("attestation", family=family, args=args)
        if control.get("fail_attestation") == family:
            raise SystemExit(23)
        print(json.dumps({"fixture_only": True, "signature_authority": False}))
        raise SystemExit(0)
    if not args or args[0] != "api" or "--method" not in args or args[args.index("--method") + 1] != "GET":
        record("forbidden_transport", args=args)
        raise SystemExit(91)
    endpoint = args[-1]
    selected = None
    for family, row in control["families"].items():
        prefix = "repos/example/repo/actions/"
        endpoints = {
            "index": prefix + "workflows/" + row["workflow"] + "/runs?branch=main&status=success&head_sha=" + "a" * 40 + "&per_page=100",
            "run": prefix + "runs/" + str(row["run_id"]),
            "inventory": prefix + "runs/" + str(row["run_id"]) + "/artifacts?per_page=100",
            "direct": prefix + "artifacts/" + str(row["artifact_id"]),
            "zip": prefix + "artifacts/" + str(row["artifact_id"]) + "/zip",
        }
        for stage, expected in endpoints.items():
            if endpoint == expected:
                selected = (family, row, stage)
    if selected is None:
        record("forbidden_endpoint", args=args)
        raise SystemExit(92)
    family, row, stage = selected
    record("api", family=family, stage=stage, endpoint=endpoint, args=args)
    state_path = root / "transport-counts.json"
    counts = json.loads(state_path.read_text()) if state_path.exists() else {}
    key = family + ":" + stage
    counts[key] = counts.get(key, 0) + 1
    state_path.write_text(json.dumps(counts))
    if counts[key] <= control.get("failures", {}).get(key, 0):
        raise SystemExit(17)
    if stage == "zip":
        sys.stdout.buffer.write((root / row["archive_file"]).read_bytes())
    elif "raw_" + stage in row:
        sys.stdout.write(row["raw_" + stage])
    else:
        print(json.dumps(row[stage]))
    raise SystemExit(0)

if program != "build_bounded_planar_current_source_supplemental_attestation.py":
    raise SystemExit(93)
kind = "receipt_check" if "--check" in args else "receipt_build"
record(kind, args=args)
if control.get("fail_builder") == kind:
    raise SystemExit(41 if kind == "receipt_build" else 42)
output = Path(args[args.index("--out") + 1])
if kind == "receipt_build":
    input_root = Path(args[args.index("--input-root") + 1])
    if len(list(input_root.glob("*/product-state-attestation-verification.json"))) != 5:
        raise SystemExit(94)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"fixture_only": True, "release_authority": False}))
elif not output.is_file():
    raise SystemExit(95)
"""


class Scenario:
    def __init__(self, root: Path):
        self.root = root
        self.inputs = root / "inputs"
        self.output = root / "receipt.json"
        self.github_output = root / "github-output.txt"
        self.runner = root / "runner-temp"
        self.runner.mkdir()
        self.bin = root / "bin"
        self.bin.mkdir()
        (root / "scripts").mkdir()
        for name in REAL_SCRIPTS:
            (root / "scripts" / name).write_bytes(
                (ROOT / "scripts" / name).read_bytes()
            )
        for name in ("gh", "sleep"):
            path = self.bin / name
            path.write_text(f"#!{sys.executable}\n" + SHIM, encoding="utf-8")
            path.chmod(0o700)
        (self.bin / "python").symlink_to(sys.executable)
        builder = (
            root
            / "scripts/build_bounded_planar_current_source_supplemental_attestation.py"
        )
        builder.write_text(SHIM, encoding="utf-8")
        self.control = {"families": {}, "failures": {}}
        for index, (family, workflow, prefix, directory) in enumerate(FAMILIES):
            run_id, artifact_id = 901 + index, 701 + index
            run = dict(
                id=run_id,
                run_attempt=2,
                head_sha=SOURCE_SHA,
                head_branch="main",
                path=f".github/workflows/{workflow}.yml",
                event="push",
                status="completed",
                conclusion="success",
                repository={"id": 17, "full_name": REPOSITORY},
                head_repository={"id": 17, "full_name": REPOSITORY},
            )
            row = dict(
                workflow=workflow + ".yml",
                directory=directory,
                run_id=run_id,
                artifact_id=artifact_id,
                index={"workflow_runs": [copy.deepcopy(run)]},
                run=run,
                archive_file=family + ".zip",
            )
            self.control["families"][family] = row
            self.set_archive(family)
            artifact = dict(
                id=artifact_id,
                name=f"{prefix}-{run_id}-2",
                expired=False,
                archive_download_url=f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip",
                workflow_run=dict(
                    id=run_id,
                    repository_id=17,
                    head_repository_id=17,
                    head_branch="main",
                    head_sha=SOURCE_SHA,
                ),
            )
            row["direct"] = artifact
            self.refresh_digest(family)

    def set_archive(self, family, *, eligibility=True, seal=True):
        row = self.control["families"][family]
        directory = ".ci/" + row["directory"]
        members = {
            "technical-receipt.json": {"family_id": family, "fixture_only": True},
            "artifact-handoff.json": {"family_id": family, "fixture_only": True},
            "artifact-handoff.sigstore.json": {"fixture_only": True},
        }
        if seal:
            members["producer-seal.json"] = {
                "family_id": family,
                "runtime_binding": {
                    "technical_authority_eligible": eligibility,
                    "blockers": [] if eligibility is True else ["test_runtime_blocked"],
                },
            }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, payload in members.items():
                archive.writestr(directory + "/" + name, json.dumps(payload).encode())
        (self.root / row["archive_file"]).write_bytes(buffer.getvalue())
        if "direct" in row:
            self.refresh_digest(family)

    def refresh_digest(self, family):
        row = self.control["families"][family]
        raw = (self.root / row["archive_file"]).read_bytes()
        row["direct"].update(
            size_in_bytes=len(raw), digest="sha256:" + hashlib.sha256(raw).hexdigest()
        )
        row["inventory"] = {
            "total_count": 1,
            "artifacts": [copy.deepcopy(row["direct"])],
        }

    def run(self):
        (self.root / "control.json").write_text(
            json.dumps(self.control), encoding="utf-8"
        )
        return subprocess.run(
            ["/bin/bash", "-c", workflow_shell()],
            cwd=self.root,
            env={
                "PATH": str(self.bin) + ":/usr/bin:/bin",
                "SUPPLEMENTAL_TEST_ROOT": str(self.root),
                "GITHUB_REPOSITORY": REPOSITORY,
                "PRODUCT_STATE_SHA": SOURCE_SHA,
                "RUNNER_TEMP": str(self.runner),
                "GITHUB_OUTPUT": str(self.github_output),
                "SUPPLEMENTAL_ATTESTATION_INPUT_DIR": str(self.inputs),
                "SAME_OPERATOR_SUPPLEMENTAL_RECEIPT_PATH": str(self.output),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def events(self, kind=None):
        path = self.root / "events.jsonl"
        rows = (
            [json.loads(line) for line in path.read_text().splitlines()]
            if path.exists()
            else []
        )
        return [row for row in rows if kind is None or row["kind"] == kind]

    def diagnostics(self):
        return {
            p.stem: json.loads(p.read_text())
            for p in self.runner.glob("supplemental-consumer.*/**/*.json")
        }


class SupplementalProductionWorkflowTests(unittest.TestCase):
    def scenario(self):
        temporary = tempfile.TemporaryDirectory(
            prefix="supplemental-production-workflow-"
        )
        self.addCleanup(temporary.cleanup)
        return Scenario(Path(temporary.name))

    def assert_success(self, scene, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            [r["kind"] for r in scene.events() if r["kind"].startswith("receipt_")],
            ["receipt_build", "receipt_check"],
        )

    def assert_unavailable(self, scene, result, reason):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(reason, result.stderr)
        self.assertFalse(scene.output.exists())
        self.assertFalse(any(r["kind"].startswith("receipt_") for r in scene.events()))

    def assert_diagnostics_outside_inputs(self, scene):
        lines = scene.github_output.read_text().splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith("diagnostic_dir="))
            path = Path(line.removeprefix("diagnostic_dir="))
            self.assertEqual(path.parent, scene.runner)
            self.assertTrue(path.is_dir())
            self.assertFalse(path.is_relative_to(scene.inputs))
        self.assertFalse(list(scene.inputs.glob("**/*consumer*.json")))

    def test_five_families_use_real_consumer_exact_ids_then_attest_build_check(self):
        scene = self.scenario()
        result = scene.run()
        self.assert_success(scene, result)
        self.assert_diagnostics_outside_inputs(scene)
        expected = []
        for family, *_ in FAMILIES:
            expected += [
                ("api", family, stage)
                for stage in ("index", "run", "inventory", "direct", "zip")
            ]
            expected.append(("attestation", family, None))
        expected += [("receipt_build", None, None), ("receipt_check", None, None)]
        self.assertEqual(
            [(r["kind"], r.get("family"), r.get("stage")) for r in scene.events()],
            expected,
        )
        diagnostics = scene.diagnostics()
        self.assertEqual(set(diagnostics), {r[0] for r in FAMILIES})
        self.assertEqual(len(list(scene.runner.iterdir())), 1)
        for family, row in scene.control["families"].items():
            diagnostic = diagnostics[family]
            self.assertEqual(
                (diagnostic["status"], diagnostic["artifact_id"]),
                ("materialized", row["artifact_id"]),
            )
            for field in (
                "release_authority",
                "independent_verification",
                "technical_credit_granted",
            ):
                self.assertIs(diagnostic[field], False)
            self.assertTrue(
                (
                    scene.inputs
                    / family
                    / "artifact/.ci"
                    / row["directory"]
                    / "technical-receipt.json"
                ).is_file()
            )
        for event in scene.events("attestation"):
            args = event["args"]
            self.assertEqual(args[args.index("--repo") + 1], REPOSITORY)
            self.assertEqual(
                args[args.index("--signer-workflow") + 1],
                REPOSITORY
                + "/.github/workflows/bounded-planar-sealed-technical-attestor.yml",
            )
            for flag in ("--signer-digest", "--source-digest"):
                self.assertEqual(args[args.index(flag) + 1], SOURCE_SHA)
            self.assertEqual(args[args.index("--source-ref") + 1], "refs/heads/main")
            self.assertIn("--deny-self-hosted-runners", args)
            self.assertEqual(args[args.index("--format") + 1], "json")
            self.assertTrue(Path(args[args.index("--bundle") + 1]).is_file())
        for event in scene.events("receipt_build") + scene.events("receipt_check"):
            args = event["args"]
            self.assertEqual(args[args.index("--source-commit") + 1], SOURCE_SHA)
            self.assertEqual(args[args.index("--repository") + 1], REPOSITORY)
            self.assertEqual(Path(args[args.index("--out") + 1]), scene.output)
        for name in REAL_SCRIPTS:
            self.assertEqual(
                (scene.root / "scripts" / name).read_bytes(),
                (ROOT / "scripts" / name).read_bytes(),
            )
        self.assertIs(json.loads(scene.output.read_text())["release_authority"], False)

    def test_missing_and_expired_remove_stale_receipt_without_promotion(self):
        for mode in ("missing", "expired", "expired_direct"):
            with self.subTest(mode=mode):
                scene = self.scenario()
                scene.output.write_text("stale synthetic receipt")
                row = scene.control["families"]["linear"]
                if mode == "missing":
                    row["inventory"] = {"total_count": 0, "artifacts": []}
                elif mode == "expired":
                    row["inventory"]["artifacts"][0]["expired"] = True
                else:
                    row["direct"]["expired"] = True
                result = scene.run()
                availability = "missing" if mode == "missing" else "expired"
                self.assert_unavailable(
                    scene, result, "exact_sha_artifact_" + availability
                )
                self.assertEqual(
                    scene.diagnostics()["linear"]["availability"], availability
                )
                self.assertFalse(
                    any(
                        r.get("stage") == "zip" or r["kind"] == "attestation"
                        for r in scene.events()
                    )
                )

    def test_duplicate_changed_identity_and_corrupt_zip_fail_closed(self):
        for mode, error in (
            ("duplicate", "artifact_inventory_ambiguous"),
            ("changed_identity", "artifact_list_direct_mismatch"),
            ("corrupt", "archive_digest_mismatch"),
            ("run_source", "workflow_run_identity_invalid"),
            ("duplicate_json_key", "api_json_invalid"),
        ):
            with self.subTest(mode=mode):
                scene = self.scenario()
                row = scene.control["families"]["linear"]
                if mode == "duplicate":
                    row["inventory"] = {
                        "total_count": 3,
                        "artifacts": [
                            dict(row["direct"], id=i) for i in (701, 1701, 2701)
                        ],
                    }
                elif mode == "changed_identity":
                    row["direct"]["digest"] = "sha256:" + "b" * 64
                elif mode == "corrupt":
                    path = scene.root / row["archive_file"]
                    raw = path.read_bytes()
                    path.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
                elif mode == "run_source":
                    row["run"]["head_sha"] = "b" * 40
                else:
                    row["raw_inventory"] = json.dumps(row["inventory"]).replace(
                        '"total_count": 1', '"total_count": 1, "total_count": 1'
                    )
                result = scene.run()
                self.assertNotEqual(result.returncode, 0)
                self.assert_diagnostics_outside_inputs(scene)
                self.assertEqual(scene.diagnostics()["linear"]["error_code"], error)
                self.assertFalse(scene.output.exists())
                self.assertFalse(scene.events("attestation"))
                self.assertFalse(
                    any(r["kind"].startswith("receipt_") for r in scene.events())
                )
                self.assertFalse((scene.inputs / "linear/artifact").exists())

    def test_bounded_lookup_retries_can_recover_without_repeating_the_consumer(self):
        for stage, delay in (("index", "10"), ("run", "5"), ("inventory", "5")):
            with self.subTest(stage=stage):
                scene = self.scenario()
                scene.control["failures"]["linear:" + stage] = 2
                result = scene.run()
                self.assert_success(scene, result)
                calls = [r for r in scene.events("api") if r["family"] == "linear"]
                self.assertEqual(sum(r["stage"] == stage for r in calls), 3)
                self.assertEqual(sum(r["stage"] == "direct" for r in calls), 1)
                self.assertEqual(sum(r["stage"] == "zip" for r in calls), 1)
                self.assertEqual(
                    [r["args"] for r in scene.events("sleep")], [[delay], [delay]]
                )

    def test_lookup_exhaustion_is_bounded_and_never_promotes(self):
        cases = (
            ("index", 30, "10", "workflow_run_lookup_failed_after_bounded_retry"),
            ("run", 3, "5", "workflow_run_metadata_lookup_failed_after_bounded_retry"),
            ("inventory", 3, "5", "artifact_lookup_failed_after_bounded_retry"),
        )
        for stage, attempts, delay, reason in cases:
            with self.subTest(stage=stage):
                scene = self.scenario()
                scene.output.write_text("stale synthetic receipt")
                scene.control["failures"]["linear:" + stage] = attempts
                self.assert_unavailable(scene, scene.run(), reason)
                calls = [r for r in scene.events("api") if r["family"] == "linear"]
                self.assertEqual(sum(r["stage"] == stage for r in calls), attempts)
                self.assertEqual(
                    [r["args"] for r in scene.events("sleep")],
                    [[delay]] * (attempts - 1),
                )
                self.assertFalse(scene.diagnostics())
                self.assertFalse(scene.events("attestation"))

    def test_successful_empty_run_lookup_has_distinct_unavailable_reason(self):
        scene = self.scenario()
        scene.control["families"]["linear"]["index"] = {"workflow_runs": []}
        scene.output.write_text("stale synthetic receipt")
        self.assert_unavailable(
            scene, scene.run(), "successful_exact_sha_workflow_run_missing"
        )
        self.assertEqual(len(scene.events("api")), 30)
        self.assertEqual(len(scene.events("sleep")), 29)

    def test_attestation_and_receipt_failures_propagate(self):
        for mode, expected_status, receipt_events in (
            ("attestation", 23, []),
            ("receipt_build", 41, ["receipt_build"]),
            ("receipt_check", 42, ["receipt_build", "receipt_check"]),
        ):
            with self.subTest(mode=mode):
                scene = self.scenario()
                if mode == "attestation":
                    scene.control["fail_attestation"] = "scaling"
                else:
                    scene.control["fail_builder"] = mode
                result = scene.run()
                self.assertEqual(result.returncode, expected_status, result.stderr)
                self.assertEqual(
                    [
                        r["kind"]
                        for r in scene.events()
                        if r["kind"].startswith("receipt_")
                    ],
                    receipt_events,
                )
                self.assertEqual(
                    len(scene.events("attestation")), 3 if mode == "attestation" else 5
                )

    def test_runtime_blocked_or_missing_seal_stays_nonpromoting_after_attestation(self):
        for eligibility, seal in ((False, True), (1, True), (True, False)):
            with self.subTest(eligibility=eligibility, seal=seal):
                scene = self.scenario()
                scene.output.write_text("stale synthetic receipt")
                scene.set_archive(
                    "nonlinear_material_recovery", eligibility=eligibility, seal=seal
                )
                result = scene.run()
                self.assert_unavailable(
                    scene, result, "non-promoting until every runtime byte lock passes"
                )
                self.assertEqual(len(scene.events("attestation")), 5)
                self.assertEqual(len(scene.diagnostics()), 5)

    def test_later_run_uses_new_diagnostic_directory_and_refuses_existing_target(self):
        scene = self.scenario()
        self.assert_success(scene, scene.run())
        old = {
            p: p.read_bytes()
            for p in scene.runner.glob("supplemental-consumer.*/*.json")
        }
        result = scene.run()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(list(scene.runner.iterdir())), 2)
        self.assertTrue(all(path.read_bytes() == raw for path, raw in old.items()))
        new = [
            p
            for p in scene.runner.glob("supplemental-consumer.*/*.json")
            if p not in old
        ]
        self.assertEqual(len(new), 1)
        self.assertEqual(
            json.loads(new[0].read_text())["error_code"], "extraction_target_exists"
        )

    def test_consumer_status_stdout_is_closed_and_no_name_download_remains(self):
        shell = workflow_shell()
        self.assertIn("python scripts/consume_supplemental_artifact.py", shell)
        self.assertNotIn("gh run download", shell)
        self.assertNotIn('mkdir -p "$artifact_root"', shell)
        self.assertIn('mktemp -d "$RUNNER_TEMP/supplemental-consumer.XXXXXX"', shell)
        for status in ("missing", "expired"):
            self.assertIn(f'if test "$artifact_status" = "{status}"; then', shell)
        self.assertRegex(
            shell,
            re.compile(
                r'if test "\$artifact_status" != "available"; then\n.*?exit 1\n\s*fi',
                re.S,
            ),
        )


if __name__ == "__main__":
    unittest.main()
