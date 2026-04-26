from __future__ import annotations

from pathlib import Path

from implementation.phase1.project_registry_portfolio_scanner import discover_project_registry_paths


def test_discover_project_registry_paths_handles_paths_directories_globs_and_dedupes(tmp_path: Path) -> None:
    registry_a = tmp_path / "tower-a" / "project_registry.json"
    registry_a.parent.mkdir(parents=True, exist_ok=True)
    registry_a.write_text("{}", encoding="utf-8")

    registry_b = tmp_path / "bridge-b" / "release_registry.json"
    registry_b.parent.mkdir(parents=True, exist_ok=True)
    registry_b.write_text("{}", encoding="utf-8")

    discovery = discover_project_registry_paths(
        registry_paths=[registry_a, tmp_path / "missing.json"],
        registry_dirs=[tmp_path / "bridge-b"],
        registry_globs=[
            str(tmp_path / "**" / "project_registry.json"),
            str(tmp_path / "**" / "not_there.json"),
        ],
    )

    assert [path.name for path in discovery["registry_paths"]] == [
        "project_registry.json",
        "release_registry.json",
    ]
    assert discovery["scan"]["summary"]["path_input_count"] == 2
    assert discovery["scan"]["summary"]["directory_input_count"] == 1
    assert discovery["scan"]["summary"]["glob_input_count"] == 2
    assert discovery["scan"]["summary"]["discovered_registry_count"] == 2
    assert discovery["scan"]["summary"]["missing_input_count"] == 1
    assert discovery["scan"]["summary"]["unmatched_input_count"] == 1
    assert discovery["scan"]["summary"]["duplicate_registry_count"] == 1

    source_details = {
        row["path"]: row
        for row in discovery["scan"]["source_details"]
    }
    assert source_details[str(registry_a)]["source_kinds"] == ["path", "glob"]
    assert source_details[str(registry_b)]["source_kinds"] == ["directory"]


def test_discover_project_registry_paths_includes_native_authoring_registry_defaults(tmp_path: Path) -> None:
    native_registry = tmp_path / "authoring" / "native_authoring_project_registry.json"
    native_registry.parent.mkdir(parents=True, exist_ok=True)
    native_registry.write_text("{}", encoding="utf-8")

    discovery = discover_project_registry_paths(
        registry_dirs=[tmp_path / "authoring"],
    )

    assert [path.name for path in discovery["registry_paths"]] == [
        "native_authoring_project_registry.json",
    ]
    assert discovery["scan"]["summary"]["discovered_registry_count"] == 1
