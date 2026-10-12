"""Complete-source admission and retained observation identities, no solver mocks."""

import csv
from dataclasses import replace
import hashlib
import io
import math
import os

import pytest

from structural_analysis.api.rc_corotational_ordinal_source import (
    CORRECTED_SENSOR_REFERENCE_SCOPE,
    CorrectedSensorReferenceMapping,
    INCH_TO_M,
    KIP_TO_KN,
    compile_corrected_sensor_reference,
)


def mapping():
    return CorrectedSensorReferenceMapping(
        "authored-sensor-source:specimen-A",
        "N_Face",
        "Axial",
        "Lateral",
        1,
        1,
        -1,
        "Declared numerical reference; sensor reduction and initial state unqualified.",
    )


def source_rows(count=4):
    metadata = [
        ["# authored CSV fixture", "", "", "", "", ""],
        ["Sensor_Data", "Corrected", "", "", "", ""],
        ["Sensor_Name", "Time", "Axial", "Lateral", "N_Face", "Strain"],
        ["Sensor_Type", "Time", "Force", "Force", "Displacement", "Strain"],
        ["Sensor_Direction", "", "", "", "", ""],
        ["Measurement_Type", "time", "force", "force", "displacement", "strain"],
        ["Sensor_Unit", "hh:mm:ss", "kip", "kip", "in", ""],
        ["Sensor_Time", "0", "", "", "", ""],
    ]
    data = [
        ["", str(i), "-1" if i < 2 else "-2", "2", "0.1", str(i / 1000)]
        for i in range(count)
    ]
    return metadata + data


def write_source(tmp_path, rows):
    output = io.StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    raw = output.getvalue().encode()
    path = tmp_path / "source.csv"
    path.write_bytes(raw)
    return path, "sha256:" + hashlib.sha256(raw).hexdigest()


def compile_source(path, checksum, count=4, definition=None):
    return compile_corrected_sensor_reference(
        path,
        expected_source_sha256=checksum,
        expected_record_count=count,
        mapping=mapping() if definition is None else definition,
    )


def test_full_sequence_repeat_and_observed_force_kept_with_explicit_mapping(tmp_path):
    path, checksum = write_source(tmp_path, source_rows())
    compiled = compile_source(path, checksum)
    rows = compiled.plan.rows
    assert len(rows) == len(compiled.observed_force_kn) == 4
    assert tuple(row.ordinal for row in rows) == (0, 1, 2, 3)
    assert (
        tuple(row.source_row for row in rows)
        == compiled.source_record_indices
        == (8, 9, 10, 11)
    )
    assert rows[0].target_m == rows[1].target_m == 0.1 * INCH_TO_M
    assert rows[0].axial_load_kn == rows[1].axial_load_kn == -KIP_TO_KN
    assert rows[2].axial_load_kn == -2 * KIP_TO_KN
    assert compiled.observed_force_kn == (-2 * KIP_TO_KN,) * 4
    assert len({row.source_row_sha256 for row in rows}) == 4
    declaration = compiled.mapping.to_dict()
    assert declaration["schema_version"] == CORRECTED_SENSOR_REFERENCE_SCOPE
    assert declaration["source_offset_or_retare"] == "none"
    assert declaration["source_measurement_formula_confirmed"] is False
    assert declaration["independent_physical_validation"] is False
    assert path.read_bytes().startswith(b"# authored CSV fixture")


def test_unused_channel_change_changes_the_source_and_only_its_row_identity(tmp_path):
    rows = source_rows()
    path, checksum = write_source(tmp_path, rows)
    original = compile_source(path, checksum)
    rows[-1][-1] = "0.12345"
    path, changed_checksum = write_source(tmp_path, rows)
    with pytest.raises(ValueError, match="complete source checksum"):
        compile_source(path, checksum)
    changed = compile_source(path, changed_checksum)
    assert original.plan.hash != changed.plan.hash
    assert original.plan.rows[:-1] == changed.plan.rows[:-1]
    assert original.plan.rows[-1].target_m == changed.plan.rows[-1].target_m
    assert (
        original.plan.rows[-1].source_row_sha256
        != changed.plan.rows[-1].source_row_sha256
    )


@pytest.mark.parametrize("count", [3, 5])
def test_prefix_or_wrong_complete_count_is_refused(tmp_path, count):
    path, checksum = write_source(tmp_path, source_rows())
    with pytest.raises(ValueError, match="complete record count"):
        compile_source(path, checksum, count=count)


@pytest.mark.parametrize(
    "change, detail",
    [
        (lambda r: r[-1].__setitem__(1, "2"), "ordinal"),
        (lambda r: r[-1].__setitem__(4, "nan"), "nonfinite"),
        (lambda r: r[-1].__setitem__(2, "1e309"), "nonfinite"),
        (lambda r: r[-1].__setitem__(3, ""), "missing"),
        (lambda r: r[6].__setitem__(4, "mm"), "type or unit"),
        (lambda r: r[2].__setitem__(5, "N_Face"), "distinct"),
        (lambda r: r[-1].append("extra"), "width"),
        (lambda r: r[1].__setitem__(1, "Raw"), "corrected ordinal"),
    ],
)
def test_corrupt_or_incompatible_source_refused_before_admission(
    tmp_path, change, detail
):
    rows = source_rows()
    change(rows)
    path, checksum = write_source(tmp_path, rows)
    with pytest.raises(ValueError, match=detail):
        compile_source(path, checksum)


def test_mapping_change_is_frozen_without_tare_or_observed_force_fitting(tmp_path):
    path, checksum = write_source(tmp_path, source_rows())
    first = compile_source(path, checksum)
    second = compile_source(
        path, checksum, definition=replace(mapping(), target_sign=-1)
    )
    assert first.plan.hash != second.plan.hash
    assert first.plan.mapping_hash != second.plan.mapping_hash
    assert second.plan.rows[0].target_m == -first.plan.rows[0].target_m
    assert first.observed_force_kn == second.observed_force_kn
    with pytest.raises(ValueError, match="explicitly"):
        replace(mapping(), axial_sign=True)


def test_source_symlink_fifo_and_environment_name_refused_without_opening(tmp_path):
    path, checksum = write_source(tmp_path, source_rows())
    alias = tmp_path / "alias.csv"
    alias.symlink_to(path)
    with pytest.raises(OSError):
        compile_source(alias, checksum)
    real_directory = tmp_path / "real-directory"
    real_directory.mkdir()
    real_source, real_checksum = write_source(real_directory, source_rows())
    parent_alias = tmp_path / "parent-alias"
    parent_alias.symlink_to(real_directory, target_is_directory=True)
    with pytest.raises(OSError):
        compile_source(parent_alias / real_source.name, real_checksum)
    fifo = tmp_path / "pipe.csv"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular file"):
        compile_source(fifo, checksum)
    # No environment file is created or read, even in this negative test.
    with pytest.raises(ValueError, match="environment files"):
        compile_source(tmp_path / ".env.csv", checksum)


def test_signed_zero_and_raw_lexeme_identity_are_preserved(tmp_path):
    rows = source_rows()
    rows[8][4] = "-0.0"
    rows[9][4] = "0"
    path, checksum = write_source(tmp_path, rows)
    compiled = compile_source(path, checksum)
    assert math.copysign(1, compiled.plan.rows[0].target_m) == -1
    assert math.copysign(1, compiled.plan.rows[1].target_m) == 1
    assert (
        compiled.plan.rows[0].source_row_sha256
        != compiled.plan.rows[1].source_row_sha256
    )


def test_all_30574_source_records_compile_in_order_without_prefix_selection(tmp_path):
    path, checksum = write_source(tmp_path, source_rows(30574))
    compiled = compile_source(path, checksum, count=30574)
    assert len(compiled.plan.rows) == len(compiled.observed_force_kn) == 30574
    assert compiled.plan.rows[0].source_row == 8
    assert compiled.plan.rows[-1].ordinal == 30573
    assert compiled.plan.rows[-1].source_row == 30581
