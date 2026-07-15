from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import stat
import sys
from typing import IO

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

output_integrity = importlib.import_module(
    "structural_analysis.api._output_integrity"
)
cli = importlib.import_module("structural_analysis.api.cli")


def _temp_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob(".*.tmp")
        if path.is_file() or path.is_symlink()
    )


def _write_pair(
    result_path: Path,
    report_path: Path,
    *,
    result_payload: dict[str, object] | None = None,
    report_payload: dict[str, object] | None = None,
) -> None:
    output_integrity.write_json_pair(
        result_path,
        result_payload or {"z": 2, "a": 1},
        report_path,
        report_payload or {"status": "pass"},
    )


def test_cli_rejects_exact_output_collision_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "shared.json"
    analysis_started = False

    def unexpected_load_model(_path: str) -> object:
        nonlocal analysis_started
        analysis_started = True
        raise AssertionError("analysis must not start for colliding outputs")

    monkeypatch.setattr(cli, "load_model", unexpected_load_model)

    with pytest.raises(SystemExit) as raised:
        cli.main(
            [
                str(tmp_path / "missing-model.json"),
                "--out",
                str(target),
                "--report-out",
                str(target),
            ]
        )

    assert raised.value.code == 2
    assert analysis_started is False
    assert not target.exists()


def test_cli_rejects_resolved_equivalent_nonexistent_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    direct = tmp_path / "result.json"
    monkeypatch.chdir(tmp_path)
    equivalent = Path("nested") / ".." / "result.json"

    with pytest.raises(output_integrity.OutputPathCollisionError):
        output_integrity.resolve_distinct_output_paths(direct, equivalent)

    assert not direct.exists()


def test_cli_rejects_existing_symlink_target_alias(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    alias = tmp_path / "result-link.json"
    target.write_text("original\n", encoding="utf-8")
    try:
        alias.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    with pytest.raises(output_integrity.OutputPathCollisionError):
        output_integrity.resolve_distinct_output_paths(target, alias)

    assert target.read_text(encoding="utf-8") == "original\n"


def test_cli_rejects_existing_hardlink_target_alias(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    alias = tmp_path / "result-hardlink.json"
    target.write_text("original\n", encoding="utf-8")
    try:
        os.link(target, alias)
    except OSError as error:
        pytest.skip(f"hardlink creation unavailable: {error}")

    with pytest.raises(output_integrity.OutputPathCollisionError):
        output_integrity.resolve_distinct_output_paths(target, alias)

    assert target.read_text(encoding="utf-8") == "original\n"


def test_cli_rejects_output_nested_below_other_output_before_mutation(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = result_path / "report.json"

    with pytest.raises(output_integrity.OutputPathCollisionError):
        output_integrity.resolve_distinct_output_paths(result_path, report_path)

    assert not result_path.exists()


def test_serialization_failure_preserves_both_targets(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    result_path.write_bytes(b"old result\n")
    report_path.write_bytes(b"old report\n")

    with pytest.raises(TypeError):
        _write_pair(
            result_path,
            report_path,
            report_payload={"not_json": object()},
        )

    assert result_path.read_bytes() == b"old result\n"
    assert report_path.read_bytes() == b"old report\n"
    assert _temp_files(tmp_path) == []


@pytest.mark.parametrize("failing_write", [1, 2])
def test_temp_write_failure_preserves_both_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_write: int,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    result_path.write_bytes(b"old result\n")
    report_path.write_bytes(b"old report\n")

    real_fdopen = output_integrity.os.fdopen
    text_handle_count = 0

    class FailingWriteHandle:
        def __init__(self, wrapped: IO[str], should_fail: bool) -> None:
            self._wrapped = wrapped
            self._should_fail = should_fail

        def __enter__(self) -> FailingWriteHandle:
            return self

        def __exit__(self, *args: object) -> object:
            return self._wrapped.__exit__(*args)

        def write(self, text: str) -> int:
            if self._should_fail:
                raise OSError(f"temp write {failing_write} failed")
            return self._wrapped.write(text)

        def __getattr__(self, name: str) -> object:
            return getattr(self._wrapped, name)

    def fail_selected_text_write(
        file_descriptor: int,
        mode: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        nonlocal text_handle_count
        handle = real_fdopen(file_descriptor, mode, *args, **kwargs)
        if "b" in mode:
            return handle
        text_handle_count += 1
        return FailingWriteHandle(handle, text_handle_count == failing_write)

    monkeypatch.setattr(output_integrity.os, "fdopen", fail_selected_text_write)

    with pytest.raises(OSError, match=f"temp write {failing_write} failed"):
        _write_pair(result_path, report_path)

    assert result_path.read_bytes() == b"old result\n"
    assert report_path.read_bytes() == b"old report\n"
    assert _temp_files(tmp_path) == []


def test_second_replacement_failure_rolls_back_first_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    result_path.write_bytes(b"old result\n")
    report_path.write_bytes(b"old report\n")
    result_path.chmod(0o640)
    report_path.chmod(0o604)
    real_replace = output_integrity.os.replace
    call_count = 0

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("second replacement failed")
        real_replace(source, target)

    monkeypatch.setattr(output_integrity.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="second replacement failed"):
        _write_pair(result_path, report_path)

    assert call_count == 3
    assert result_path.read_bytes() == b"old result\n"
    assert report_path.read_bytes() == b"old report\n"
    if os.name == "posix":
        assert stat.S_IMODE(result_path.stat().st_mode) == 0o640
        assert stat.S_IMODE(report_path.stat().st_mode) == 0o604
    assert _temp_files(tmp_path) == []


def test_second_replacement_failure_removes_new_first_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "new-result.json"
    report_path = tmp_path / "report.json"
    report_path.write_bytes(b"old report\n")
    real_replace = output_integrity.os.replace
    call_count = 0

    def fail_second_replace(source: str | Path, target: str | Path) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("second replacement failed")
        real_replace(source, target)

    monkeypatch.setattr(output_integrity.os, "replace", fail_second_replace)

    with pytest.raises(OSError, match="second replacement failed"):
        _write_pair(result_path, report_path)

    assert call_count == 2
    assert not result_path.exists()
    assert report_path.read_bytes() == b"old report\n"
    assert _temp_files(tmp_path) == []


def test_successful_pair_creates_parents_and_preserves_json_format(
    tmp_path: Path,
) -> None:
    result_path = tmp_path / "result" / "nested" / "result.json"
    report_path = tmp_path / "report" / "nested" / "report.json"
    result_payload = {"z": 2, "a": {"d": 4, "b": 3}}
    report_payload = {"status": "pass", "contract_pass": True}

    _write_pair(
        result_path,
        report_path,
        result_payload=result_payload,
        report_payload=report_payload,
    )

    expected_result = json.dumps(result_payload, indent=2, sort_keys=True) + "\n"
    expected_report = json.dumps(report_payload, indent=2, sort_keys=True) + "\n"
    assert result_path.read_text(encoding="utf-8") == expected_result
    assert report_path.read_text(encoding="utf-8") == expected_report
    assert result_path.read_bytes().endswith(os.linesep.encode("utf-8"))
    assert report_path.read_bytes().endswith(os.linesep.encode("utf-8"))
    assert _temp_files(tmp_path) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode contract")
def test_successful_pair_preserves_existing_modes_and_new_file_umask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    result_path.write_text("old result\n", encoding="utf-8")
    result_path.chmod(0o640)
    real_fdopen = output_integrity.os.fdopen
    staging_modes: list[int] = []

    def record_staging_mode(
        file_descriptor: int,
        mode: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        if "b" not in mode:
            staging_modes.append(stat.S_IMODE(os.fstat(file_descriptor).st_mode))
        return real_fdopen(file_descriptor, mode, *args, **kwargs)

    monkeypatch.setattr(output_integrity.os, "fdopen", record_staging_mode)

    previous_umask = os.umask(0o027)
    try:
        _write_pair(result_path, report_path)
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(result_path.stat().st_mode) == 0o640
    assert stat.S_IMODE(report_path.stat().st_mode) == 0o640
    assert staging_modes == [0o600, 0o600]


def test_all_temp_handles_are_closed_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    report_path = tmp_path / "report.json"
    real_fdopen = output_integrity.os.fdopen
    real_replace = output_integrity.os.replace
    opened_handles: list[object] = []

    def tracking_fdopen(file_descriptor: int, *args: object, **kwargs: object):
        handle = real_fdopen(file_descriptor, *args, **kwargs)
        opened_handles.append(handle)
        return handle

    def assert_closed_then_replace(source: str | Path, target: str | Path) -> None:
        assert opened_handles
        assert all(getattr(handle, "closed") for handle in opened_handles)
        real_replace(source, target)

    monkeypatch.setattr(output_integrity.os, "fdopen", tracking_fdopen)
    monkeypatch.setattr(output_integrity.os, "replace", assert_closed_then_replace)

    _write_pair(result_path, report_path)

    assert len(opened_handles) == 2
    assert all(getattr(handle, "closed") for handle in opened_handles)
    assert _temp_files(tmp_path) == []
