"""Actual public prepared CPU execution, validation and exact prefix restart."""

from pathlib import Path
import os
import runpy
import shutil
import subprocess
import sys

import pytest

from structural_analysis.api.nonlinear_fiber_frame import (
    PublicRCFiberFrameConfig,
    analyze_public_rc_fiber_frame,
    validate_public_rc_fiber_frame_result,
)
from structural_analysis.materials.native_steel_batch import (
    NativeSteelBatch,
    use_native_steel_batch,
)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    supplied = os.environ.get("SA_PREPARED_STEEL_LIBRARY")
    if supplied:
        return Path(supplied).resolve(strict=True)
    compiler = shutil.which("g++")
    if compiler is None or sys.platform != "linux":
        pytest.skip("optional prepared OpenMP backend requires Linux g++")
    source = (
        Path(__file__).resolve().parents[1] / "native/cpp/src/materials/steel_batch.cpp"
    )
    output = tmp_path_factory.mktemp("public-prepared-native") / "libsteel.so"
    subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c++20",
            "-shared",
            "-fPIC",
            "-fopenmp",
            "-ffp-contract=off",
            str(source),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
    )
    return output


def test_public_prepared_full_response_validation_and_restart_match_python(
    library, tmp_path, record_property
):
    write_model = runpy.run_path(
        str(Path(__file__).with_name("test_public_rc_fiber_frame_api.py"))
    )["_write_model"]
    model = write_model(tmp_path / "prepared-rc.json")
    config = PublicRCFiberFrameConfig(load_steps=2)
    expected = analyze_public_rc_fiber_frame(model, config)
    expected_report = validate_public_rc_fiber_frame_result(expected)
    assert (
        expected.status == "ready"
        and expected.contract_pass
        and expected_report.contract_pass
    )
    backend = NativeSteelBatch(library, prepared=True)
    fixed_configuration = backend.execution_configuration()
    with use_native_steel_batch(backend):
        actual = analyze_public_rc_fiber_frame(model, config)
        report = validate_public_rc_fiber_frame_result(actual)
    assert actual.status == "ready" and actual.contract_pass and report.contract_pass
    # Execution selection and its enclosing result hash are the only differences.
    expected_payload, actual_payload = expected.to_dict(), actual.to_dict()
    expected_payload.pop("result_hash")
    actual_payload.pop("result_hash")
    assert (
        actual_payload["configuration"].pop("material_execution_backend")
        == fixed_configuration
    )
    assert actual_payload == expected_payload
    artifact = expected.checkpoint_artifact()
    assert actual.checkpoint_artifact() == artifact
    assert backend.group_calls > 0 and backend.prepared_calls == backend.calls
    assert backend.calls > 0 and backend.points > backend.calls
    first_calls = backend.calls
    with use_native_steel_batch(backend):
        restarted = analyze_public_rc_fiber_frame(
            model,
            config,
            restart_checkpoint_chain=expected.checkpoint_artifact(epoch=1),
        )
        restarted_report = validate_public_rc_fiber_frame_result(restarted)
    assert (
        restarted.status == "ready"
        and restarted.contract_pass
        and restarted_report.contract_pass
    )
    assert restarted.checkpoint_artifact() == artifact
    assert restarted.configuration["material_execution_backend"] == fixed_configuration
    assert backend.calls > first_calls
    assert actual.configuration["material_execution_backend"] == fixed_configuration
    assert report.fallback_count == restarted_report.fallback_count == 0
    assert report.regularization_count == restarted_report.regularization_count == 0
    record_property("prepared_native_calls", backend.calls)
    record_property("prepared_group_calls", backend.group_calls)
    record_property("native_library_sha256", backend.library_sha256)
