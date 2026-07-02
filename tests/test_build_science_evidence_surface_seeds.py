from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build_science_evidence_surface_seeds.py"
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

spec = importlib.util.spec_from_file_location("build_science_evidence_surface_seeds", SCRIPT_PATH)
assert spec is not None
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def test_science_evidence_surface_seeds_are_retired_for_structural_scope() -> None:
    surfaces = module.build_science_evidence_surface_seeds(repo_root=REPO_ROOT)
    guard = module.build_surface_seed_guard(repo_root=REPO_ROOT)

    assert surfaces == {}
    assert guard["schema_version"] == (
        "structural-release-non-structural-surface-seed-guard.v1"
    )
    assert guard["status"] == "retired_from_structural_release_surface"
    assert guard["contract_pass"] is True
    assert guard["surface_written_count"] == 0
    assert guard["structural_release_surface_mutated"] is False


def test_science_evidence_surface_seed_cli_writes_no_release_surface_files(
    tmp_path: Path,
) -> None:
    surface_dir = tmp_path / "surface"

    assert (
        module.main(
            [
                "--surface-dir",
                str(surface_dir),
                "--repo-root",
                str(REPO_ROOT),
            ]
        )
        == 0
    )

    assert not surface_dir.exists()


def test_science_evidence_surface_seed_cli_json_reports_guard(
    tmp_path: Path,
    capsys,
) -> None:
    assert (
        module.main(
            [
                "--surface-dir",
                str(tmp_path / "surface"),
                "--repo-root",
                str(REPO_ROOT),
                "--family",
                "legacy-non-structural",
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["surfaces"] == {}
    assert payload["guard"]["requested_family"] == "legacy-non-structural"
    assert payload["guard"]["surface_written_count"] == 0
