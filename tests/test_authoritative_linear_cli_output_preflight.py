from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

output_integrity = importlib.import_module(
    "structural_analysis.api._output_integrity"
)
cli = importlib.import_module("structural_analysis.api.cli")


def _assert_cli_rejects_before_analysis(
    arguments: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis_started = False

    def unexpected_load_model(_path: str) -> object:
        nonlocal analysis_started
        analysis_started = True
        raise AssertionError("model loading must not start for invalid output paths")

    monkeypatch.setattr(cli, "load_model", unexpected_load_model)
    with pytest.raises(SystemExit) as raised:
        cli.main(arguments)

    assert raised.value.code == 2
    assert analysis_started is False


def test_cli_rejects_result_output_that_aliases_model_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    model_path.write_text("{}\n", encoding="utf-8")

    _assert_cli_rejects_before_analysis(
        [
            str(model_path),
            "--out",
            str(model_path),
            "--report-out",
            str(report_path),
        ],
        monkeypatch,
    )

    assert model_path.read_text(encoding="utf-8") == "{}\n"
    assert not report_path.exists()


def test_cli_rejects_report_output_that_hardlinks_reference_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model_path = tmp_path / "model.json"
    reference_path = tmp_path / "reference.json"
    report_path = tmp_path / "report-hardlink.json"
    result_path = tmp_path / "result.json"
    model_path.write_text("{}\n", encoding="utf-8")
    reference_path.write_text("{}\n", encoding="utf-8")
    try:
        os.link(reference_path, report_path)
    except OSError as error:
        pytest.skip(f"hardlink creation unavailable: {error}")

    _assert_cli_rejects_before_analysis(
        [
            str(model_path),
            "--reference",
            str(reference_path),
            "--out",
            str(result_path),
            "--report-out",
            str(report_path),
        ],
        monkeypatch,
    )

    assert reference_path.read_text(encoding="utf-8") == "{}\n"
    assert report_path.read_text(encoding="utf-8") == "{}\n"
    assert not result_path.exists()


def test_cli_rejects_existing_directory_target_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result-directory"
    result_path.mkdir()

    _assert_cli_rejects_before_analysis(
        [
            str(tmp_path / "model.json"),
            "--out",
            str(result_path),
            "--report-out",
            str(tmp_path / "report.json"),
        ],
        monkeypatch,
    )

    assert result_path.is_dir()


def test_cli_rejects_target_below_regular_file_parent_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("preserve me\n", encoding="utf-8")

    _assert_cli_rejects_before_analysis(
        [
            str(tmp_path / "model.json"),
            "--out",
            str(blocked_parent / "result.json"),
            "--report-out",
            str(tmp_path / "report.json"),
        ],
        monkeypatch,
    )

    assert blocked_parent.read_text(encoding="utf-8") == "preserve me\n"


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO contract")
def test_cli_rejects_fifo_target_before_analysis_without_blocking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo_path = tmp_path / "result.fifo"
    os.mkfifo(fifo_path)

    _assert_cli_rejects_before_analysis(
        [
            str(tmp_path / "model.json"),
            "--out",
            str(fifo_path),
            "--report-out",
            str(tmp_path / "report.json"),
        ],
        monkeypatch,
    )

    assert fifo_path.exists()


def test_output_cannot_be_nested_below_protected_input_directory(
    tmp_path: Path,
) -> None:
    protected_directory = tmp_path / "input-bundle"
    protected_directory.mkdir()

    with pytest.raises(output_integrity.OutputPathCollisionError):
        output_integrity.resolve_distinct_output_paths(
            protected_directory / "result.json",
            tmp_path / "report.json",
            protected_paths={"model input": protected_directory},
        )

    assert list(protected_directory.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX FIFO race defense")
def test_snapshot_rejects_nonregular_target_even_if_preflight_is_bypassed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fifo_path = tmp_path / "result.fifo"
    report_path = tmp_path / "report.json"
    os.mkfifo(fifo_path)

    monkeypatch.setattr(
        output_integrity,
        "_validate_output_target",
        lambda _target, _label: None,
    )

    with pytest.raises(output_integrity.OutputTargetTypeError):
        output_integrity.write_json_pair(
            fifo_path,
            {"status": "result"},
            report_path,
            {"status": "report"},
        )

    assert fifo_path.exists()
    assert not report_path.exists()
