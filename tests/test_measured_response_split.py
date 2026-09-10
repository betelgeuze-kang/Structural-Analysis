"""Known experiment aliases must be rejected before solver label generation."""

from dataclasses import replace
from decimal import localcontext
import hashlib
import io
from pathlib import Path
import zipfile

import pytest

from structural_analysis.benchmark.measured_response_split import (
    MeasuredSplitLeakageError,
    measured_response_split_identity,
    validate_measured_response_split_sources,
)
from structural_analysis.benchmark import rc_control_learning as learning
from structural_analysis.io.measured_response_workbook import (
    MeasuredChannelSpec,
    decode_measured_response_workbook,
)
from structural_analysis.api.rc_fiber_frame_direct_control_request import (
    BoundedRCFiberDirectControlRequest,
)
from structural_analysis.io.neutral.loader import load_neutral_json


def source(
    *,
    campaign="experiment",
    test="initial",
    swapped=False,
    metres=False,
    changed=False,
    reordered=False,
    extra_sensor=False,
    force_values=None,
    displacement_values=None,
):
    ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    disps = (
        ["-0.000", "1.2300", "1.2300"] if not metres else ["+0", "0.00123", "0.001230"]
    )
    forces = ["0", "2", "3" if changed else "2"]
    if force_values is not None:
        forces = force_values
    if displacement_values is not None:
        disps = displacement_values
    pairs = list(zip(disps, forces))
    if reordered:
        pairs = list(reversed(pairs))
    quantities = ("force", "displacement") if swapped else ("displacement", "force")
    units = (
        ("kN", "m" if metres else "mm") if swapped else ("m" if metres else "mm", "kN")
    )
    columns = "ABC" if extra_sensor else "AB"
    if extra_sensor:
        quantities += ("strain",)
        units += ("%",)
    specs = tuple(
        MeasuredChannelSpec(c, q, u, (c,))
        for c, q, u in zip(columns, quantities, units)
    )
    header = (
        '<row r="1">'
        + "".join(f'<c r="{c}1" t="inlineStr"><is><t>{c}</t></is></c>' for c in columns)
        + "</row>"
    )
    rows = header
    for row, values in enumerate(pairs, 2):
        if swapped:
            values = values[::-1]
        if extra_sensor:
            values += (str(row),)
        rows += (
            f'<row r="{row}">'
            + "".join(
                f'<c r="{c}{row}"><v>{v}</v></c>' for c, v in zip(columns, values)
            )
            + "</row>"
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr(
            "xl/workbook.xml",
            f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets><sheet name="Data" sheetId="1" r:id="r1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<Relationships xmlns="{pkg}"><Relationship Id="r1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<worksheet xmlns="{ns}"><sheetData>{rows}</sheetData></worksheet>',
        )
    raw = out.getvalue()
    return decode_measured_response_workbook(
        raw,
        expected_source_sha256=hashlib.sha256(raw).hexdigest(),
        sheet_name="Data",
        channels=specs,
        campaign_id=campaign,
        specimen_id="frame",
        test_id=test,
    )


@pytest.mark.parametrize(
    "second",
    [dict(test="retrofitted", changed=True), dict(test="collapse", metres=True)],
)
def test_same_campaign_across_test_states_is_one_split(second):
    with pytest.raises(MeasuredSplitLeakageError, match="measured_campaign") as error:
        validate_measured_response_split_sources(
            [("a", "train", source()), ("b", "holdout", source(**second))]
        )
    assert error.value.details["measured_sources_processed"] == 2
    assert error.value.details["screen_wall_ns"] > 0
    assert (
        error.value.details["structural_calls"]
        == error.value.details["training_fits"]
        == 0
    )


def test_same_original_bytes_cannot_be_relabelled_as_independent():
    first = source()
    second = replace(
        first, campaign_id="renamed", specimen_id="renamed", test_id="renamed"
    )
    with pytest.raises(MeasuredSplitLeakageError, match="measured_original_workbook"):
        validate_measured_response_split_sources(
            [("a", "train", first), ("b", "validation", second)]
        )


def test_repackaged_units_column_order_and_zero_spelling_do_not_make_new_data():
    first, second = source(), source(campaign="other", metres=True, swapped=True)
    assert first.source.source_sha256 != second.source.source_sha256
    with localcontext() as context:
        context.prec = 2
        assert (
            measured_response_split_identity(first)["si_observation_content_sha256"]
            == measured_response_split_identity(second)["si_observation_content_sha256"]
        )
    with pytest.raises(
        MeasuredSplitLeakageError, match="measured_si_observation_content"
    ):
        validate_measured_response_split_sources(
            [("a", "train", first), ("b", "holdout", second)]
        )
    assert first.source.source_numeric_tokens[0][0] == "-0.000"


def test_sample_order_and_observed_values_remain_part_of_content_identity():
    first = measured_response_split_identity(source())["si_observation_content_sha256"]
    for kwargs in [dict(changed=True), dict(reordered=True)]:
        assert (
            measured_response_split_identity(source(**kwargs))[
                "si_observation_content_sha256"
            ]
            != first
        )


def test_same_split_reuse_and_missing_sources_have_explicit_scope():
    report = validate_measured_response_split_sources(
        [
            ("a", "train", source()),
            ("b", "train", source(test="retrofitted")),
            ("c", "holdout", None),
        ]
    )
    assert len(report["sources"]) == 2
    assert report["cases_without_measured_source"] == ["c"]
    assert report["all_cases_have_declared_measured_sources"] is False
    assert not report["independent_provenance_verified"]
    assert not report["training_admission_granted"]


def test_distinct_records_can_pass_without_independent_physics_credit():
    report = validate_measured_response_split_sources(
        [
            ("a", "train", source()),
            ("b", "holdout", source(campaign="other", changed=True)),
        ]
    )
    assert report["all_cases_have_declared_measured_sources"]
    assert not report["source_model_correspondence_verified"]


@pytest.mark.parametrize("reverse", [False, True])
def test_response_subset_cannot_cross_splits_after_repackaging(reverse):
    full = source(extra_sensor=True)
    subset = source(campaign="mirror", swapped=True, metres=True)
    assert (
        measured_response_split_identity(full)["si_observation_content_sha256"]
        != measured_response_split_identity(subset)["si_observation_content_sha256"]
    )
    records = [("full", "train", full), ("subset", "holdout", subset)]
    if reverse:
        records.reverse()
    with localcontext() as context:
        context.prec = 2
        with pytest.raises(
            MeasuredSplitLeakageError, match="measured_si_force_displacement_trajectory"
        ) as error:
            validate_measured_response_split_sources(records)
    assert error.value.details["structural_calls"] == 0
    assert error.value.details["training_fits"] == 0


@pytest.mark.parametrize(
    "changes",
    [dict(changed=True), dict(reordered=True)],
)
def test_subset_requires_same_response_values_and_row_order(changes):
    report = validate_measured_response_split_sources(
        [
            ("full", "train", source(extra_sensor=True)),
            ("subset", "holdout", source(campaign="other", **changes)),
        ]
    )
    assert report["exact_nonconstant_force_displacement_subset_screened"]
    assert not report["training_admission_granted"]


@pytest.mark.parametrize(
    "constant",
    [
        dict(force_values=["0", "-0.00", "+0"]),
        dict(force_values=["600", "600.0", "6e2"]),
        dict(displacement_values=["1", "1.00", "1e0"]),
    ],
)
def test_constant_channel_and_shared_loading_alone_do_not_link_subsets(constant):
    report = validate_measured_response_split_sources(
        [
            ("full", "train", source(extra_sensor=True, **constant)),
            ("subset", "holdout", source(campaign="other", **constant)),
        ]
    )
    assert len(report["sources"]) == 2


def test_subset_can_share_training_partition():
    report = validate_measured_response_split_sources(
        [
            ("full", "train", source(extra_sensor=True)),
            ("subset", "train", source(campaign="mirror", metres=True)),
        ]
    )
    assert report["schema_version"] == "measured-response-learning-split-screen.v2"
    assert not report["independent_provenance_verified"]


@pytest.mark.parametrize("subset", [False, True])
def test_actual_learning_entry_rejects_before_compile_solve_fit_or_output(
    tmp_path, monkeypatch, subset
):
    model = load_neutral_json(Path("examples/public_rc_fiber_frame_cantilever.json"))
    request = BoundedRCFiberDirectControlRequest(4, (-1e-6, -2e-6))

    def unexpected(*args, **kwargs):
        pytest.fail("must reject before compile/solve/fit")

    monkeypatch.setattr(learning.public, "_compile", unexpected)
    monkeypatch.setattr(learning, "benchmark_rc_control_seed_paths", unexpected)
    monkeypatch.setattr(learning, "_fit", unexpected)
    # Authored models here test the preflight connection only. They are not
    # claimed to represent the measurement fixture's physical experiment.
    cases = [
        learning.RCControlLearningCase(
            name,
            name,
            name,
            name,
            split,
            model,
            request,
            measurement_source=source(
                test=name,
                campaign=name if subset else "experiment",
                extra_sensor=subset and name == "a",
            ),
        )
        for name, split in [("a", "train"), ("b", "holdout")]
    ]
    reason = "si_force_displacement_trajectory" if subset else "campaign"
    with pytest.raises(MeasuredSplitLeakageError, match=f"measured_{reason}"):
        learning.run_rc_control_learning_study(
            cases, source_revision="a" * 40, output_directory=tmp_path / "study"
        )
    assert not (tmp_path / "study").exists()
