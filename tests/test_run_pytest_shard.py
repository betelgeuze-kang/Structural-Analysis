from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_pytest_shard.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_pytest_shard", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _fixture_repo(tmp_path: Path, count: int = 24) -> Path:
    test_root = tmp_path / "tests"
    test_root.mkdir(parents=True)
    for index in range(count):
        (test_root / f"test_case_{index:02d}.py").write_text(
            f"def test_case_{index:02d}():\n    assert True\n",
            encoding="utf-8",
        )
    return tmp_path


def test_shards_are_deterministic_disjoint_and_complete(tmp_path: Path) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path)
    files = module.discover_test_files(repo, Path("tests"))

    shards = [
        module.select_shard(files, shard_index=index, shard_count=4)
        for index in range(4)
    ]

    assert tuple(sorted(path for shard in shards for path in shard)) == files
    assert sum(len(shard) for shard in shards) == len(
        {path for shard in shards for path in shard}
    )
    assert shards == [
        module.select_shard(files, shard_index=index, shard_count=4)
        for index in range(4)
    ]


def test_shard_assignment_is_independent_of_input_order(tmp_path: Path) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path)
    files = module.discover_test_files(repo, Path("tests"))

    assert set(module.select_shard(files, shard_index=2, shard_count=4)) == set(
        module.select_shard(tuple(reversed(files)), shard_index=2, shard_count=4)
    )


def test_discovery_includes_nested_modules_and_rejects_symlinks(tmp_path: Path) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path, count=1)
    nested = repo / "tests" / "nested"
    nested.mkdir()
    (nested / "test_nested.py").write_text("def test_nested(): pass\n", encoding="utf-8")
    (nested / "test_link.py").symlink_to(nested / "test_nested.py")

    assert module.discover_test_files(repo, Path("tests")) == (
        "tests/nested/test_nested.py",
        "tests/test_case_00.py",
    )


@pytest.mark.parametrize(
    ("shard_index", "shard_count"),
    [(-1, 4), (4, 4), (0, 0)],
)
def test_invalid_shard_bounds_fail_closed(
    shard_index: int,
    shard_count: int,
) -> None:
    module = _load_module()

    with pytest.raises(ValueError):
        module.select_shard(
            ("tests/test_example.py",),
            shard_index=shard_index,
            shard_count=shard_count,
        )


def test_discovery_rejects_test_root_outside_repository(tmp_path: Path) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path / "repo", count=1)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(ValueError, match="inside the repository"):
        module.discover_test_files(repo, outside)


def test_manifest_hash_is_order_sensitive_and_newline_bound() -> None:
    module = _load_module()

    first = module.manifest_sha256(("tests/test_a.py", "tests/test_b.py"))
    second = module.manifest_sha256(("tests/test_b.py", "tests/test_a.py"))

    assert first != second
    assert first == module.manifest_sha256(("tests/test_a.py", "tests/test_b.py"))


def test_list_only_prints_a_bounded_manifest(tmp_path: Path, capsys) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path)

    result = module.main(
        [
            "--repo-root",
            str(repo),
            "--shard-index",
            "1",
            "--shard-count",
            "4",
            "--list-only",
        ]
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "pytest_shard_v1 index=1 count=4" in output
    assert "suite_manifest_sha256=" in output
    assert "shard_manifest_sha256=" in output
    assert "tests/test_case_" in output


def test_main_invokes_pytest_with_only_the_selected_modules(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path)
    calls: list[tuple[list[str], Path, bool]] = []

    class Completed:
        returncode = 7

    def fake_run(command, *, cwd, check):
        calls.append((command, cwd, check))
        return Completed()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.main(
        [
            "--repo-root",
            str(repo),
            "--shard-index",
            "3",
            "--shard-count",
            "4",
            "--",
            "-q",
            "--deselect",
            "tests/test_not_in_this_shard.py::test_example",
        ]
    )
    files = module.discover_test_files(repo, Path("tests"))
    selected = module.select_shard(files, shard_index=3, shard_count=4)

    assert result == 7
    assert calls == [
        (
            [
                module.sys.executable,
                "-m",
                "pytest",
                "-q",
                "--deselect",
                "tests/test_not_in_this_shard.py::test_example",
                *selected,
            ],
            repo.resolve(),
            False,
        )
    ]


def test_main_executes_selected_shard_with_unmatched_deselect(tmp_path: Path) -> None:
    module = _load_module()
    repo = _fixture_repo(tmp_path)

    result = module.main(
        [
            "--repo-root",
            str(repo),
            "--shard-index",
            "0",
            "--shard-count",
            "4",
            "--",
            "-q",
            "--deselect",
            "tests/test_not_in_this_shard.py::test_example",
        ]
    )

    assert result == 0
