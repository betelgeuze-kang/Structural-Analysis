from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "plan_source_boundary_cleanup.py"
SPEC = importlib.util.spec_from_file_location("plan_source_boundary_cleanup", SCRIPT_PATH)
assert SPEC is not None
plan_source_boundary_cleanup = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(plan_source_boundary_cleanup)


def test_classifies_cleanup_candidates_with_deterministic_counts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    files = [
        "implementation/phase1/output/report.json",
        "implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log",
        "node_modules/pkg/index.js",
        "dist/app.js",
        "pkg/__pycache__/module.cpython-311.pyc",
        "keys/private.pem",
        "keys/public.pub.pem",
        "data/large.bin",
        "src/app.py",
    ]
    for path, size in {
        "implementation/phase1/output/report.json": 10,
        "implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log": 20,
        "node_modules/pkg/index.js": 30,
        "dist/app.js": 40,
        "pkg/__pycache__/module.cpython-311.pyc": 50,
        "keys/private.pem": 60,
        "keys/public.pub.pem": 70,
        "data/large.bin": 2048,
        "src/app.py": 80,
    }.items():
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"x" * size)

    plan = plan_source_boundary_cleanup.build_plan(files, large_file_threshold_mib=0.001)

    assert plan["counts_by_bucket"] == {
        "build_output": 4,
        "generated_boundary": 1,
        "large_file": 1,
        "private_secret": 1,
    }
    assert plan["total_candidate_files"] == 7
    assert plan["total_candidate_bytes"] == 2258
    assert plan["records"] == [
        {
            "buckets": ["large_file"],
            "bytes": 2048,
            "path": "data/large.bin",
            "recommended_action": "externalize_or_allowlist",
        },
        {
            "buckets": ["build_output"],
            "bytes": 40,
            "path": "dist/app.js",
            "recommended_action": "remove_from_git",
        },
        {
            "buckets": ["generated_boundary"],
            "bytes": 10,
            "path": "implementation/phase1/output/report.json",
            "recommended_action": "remove_from_git",
        },
        {
            "buckets": ["build_output"],
            "bytes": 20,
            "path": "implementation/phase1/rust_hip_md3bead_hook/target/debug/build.log",
            "recommended_action": "remove_from_git",
        },
        {
            "buckets": ["private_secret"],
            "bytes": 60,
            "path": "keys/private.pem",
            "recommended_action": "manual_review",
        },
        {
            "buckets": ["build_output"],
            "bytes": 30,
            "path": "node_modules/pkg/index.js",
            "recommended_action": "remove_from_git",
        },
        {
            "buckets": ["build_output"],
            "bytes": 50,
            "path": "pkg/__pycache__/module.cpython-311.pyc",
            "recommended_action": "remove_from_git",
        },
    ]


def test_missing_local_file_sizes_are_reported_as_null_and_not_counted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    existing = tmp_path / "implementation" / "phase1" / "workspace" / "cache.json"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"x" * 123)

    plan = plan_source_boundary_cleanup.build_plan(
        [
            "implementation/phase1/workspace/cache.json",
            "implementation/phase1/stress/missing.json",
        ]
    )

    assert plan["counts_by_bucket"] == {"generated_boundary": 2}
    assert plan["total_candidate_bytes"] == 123
    assert plan["records"] == [
        {
            "buckets": ["generated_boundary"],
            "bytes": None,
            "path": "implementation/phase1/stress/missing.json",
            "recommended_action": "remove_from_git",
        },
        {
            "buckets": ["generated_boundary"],
            "bytes": 123,
            "path": "implementation/phase1/workspace/cache.json",
            "recommended_action": "remove_from_git",
        },
    ]


def test_write_pathspec_includes_remove_from_git_candidates_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    tracked_file = tmp_path / "tracked-files.txt"
    tracked_file.write_text(
        "\n".join(
            [
                "implementation/phase1/output/report.json",
                "data/large.bin",
                "keys/private.pem",
                "src/app.py",
            ]
        ),
        encoding="utf-8",
    )
    for path, size in {
        "implementation/phase1/output/report.json": 1,
        "data/large.bin": 2048,
        "keys/private.pem": 1,
        "src/app.py": 1,
    }.items():
        file_path = tmp_path / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"x" * size)
    pathspec_file = tmp_path / "cleanup.pathspec"

    exit_code = plan_source_boundary_cleanup.main(
        [
            "--tracked-files",
            str(tracked_file),
            "--large-file-threshold-mib",
            "0.001",
            "--write-pathspec",
            str(pathspec_file),
        ]
    )

    assert exit_code == 0
    assert pathspec_file.read_text(encoding="utf-8") == "implementation/phase1/output/report.json\n"


def test_large_file_allowlist_closes_known_artifacts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    large = tmp_path / "data" / "large.bin"
    large.parent.mkdir(parents=True)
    large.write_bytes(b"x" * 2048)

    plan = plan_source_boundary_cleanup.build_plan(
        ["data/large.bin"],
        large_file_threshold_mib=0.001,
        allowlist={
            "data/large.bin": {
                "classification": "external_restore",
                "rationale": "kept for deterministic restore testing",
            }
        },
    )

    assert plan["contract_pass"] is True
    assert plan["total_candidate_files"] == 0
    assert plan["total_allowlisted_files"] == 1
    assert plan["allowlisted_counts_by_classification"] == {"external_restore": 1}
    assert plan["allowlisted_records"][0]["classification"] == "external_restore"


def test_large_file_allowlist_keeps_generated_remove_candidate_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    large = tmp_path / "data" / "large.bin"
    large.parent.mkdir(parents=True)
    large.write_bytes(b"x" * 2048)

    plan = plan_source_boundary_cleanup.build_plan(
        ["data/large.bin"],
        large_file_threshold_mib=0.001,
        allowlist={
            "data/large.bin": {
                "classification": "generated_remove_candidate",
                "rationale": "must be removed from git tracking",
            }
        },
    )

    assert plan["contract_pass"] is False
    assert plan["records"][0]["recommended_action"] == "remove_from_git"


def test_cli_writes_json_and_markdown_inventory_and_can_fail_on_candidates(tmp_path: Path) -> None:
    tracked_file = tmp_path / "tracked-files.txt"
    tracked_file.write_text(
        "\0".join(["implementation/phase1/output/report.json", "src/app.py"]) + "\0",
        encoding="utf-8",
    )
    candidate = tmp_path / "implementation" / "phase1" / "output" / "report.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("generated", encoding="utf-8")
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('ok')\n", encoding="utf-8")
    out_json = tmp_path / "inventory.json"
    out_md = tmp_path / "inventory.md"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--tracked-files",
            str(tracked_file),
            "--out",
            str(out_json),
            "--out-md",
            str(out_md),
            "--fail-on-candidates",
        ],
        check=False,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 1
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    markdown = out_md.read_text(encoding="utf-8")
    assert payload["schema_version"] == "source-boundary-cleanup-plan.v1"
    assert payload["contract_pass"] is False
    assert payload["reason_code"] == "ERR_SOURCE_BOUNDARY_CLEANUP_CANDIDATES"
    assert payload["total_candidate_files"] == 1
    assert "Source Boundary Cleanup Plan" in markdown
    assert "implementation/phase1/output/report.json" in markdown
    assert "remove_from_git" in markdown
    assert result.stderr == ""


def test_cli_fail_on_candidates_passes_when_inventory_is_clean(tmp_path: Path) -> None:
    tracked_file = tmp_path / "tracked-files.txt"
    tracked_file.write_text("src/app.py\n", encoding="utf-8")
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("print('ok')\n", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--tracked-files",
            str(tracked_file),
            "--fail-on-candidates",
        ],
        check=False,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["contract_pass"] is True
    assert payload["reason_code"] == "PASS"
    assert payload["records"] == []


def test_cli_uses_fixture_and_does_not_run_mutating_git_commands(tmp_path: Path) -> None:
    tracked_file = tmp_path / "tracked-files.txt"
    tracked_file.write_text("implementation/phase1/output/report.json\n", encoding="utf-8")
    candidate = tmp_path / "implementation" / "phase1" / "output" / "report.json"
    candidate.parent.mkdir(parents=True)
    candidate.write_text("generated", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--tracked-files",
            str(tracked_file),
            "--write-pathspec",
            str(tmp_path / "cleanup.pathspec"),
        ],
        check=True,
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["total_candidate_files"] == 1
    assert payload["records"][0]["path"] == "implementation/phase1/output/report.json"
    assert candidate.exists()
    assert result.stderr == ""
