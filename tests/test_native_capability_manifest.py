from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_native_capabilities.py"
SPEC = importlib.util.spec_from_file_location("check_native_capabilities", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
capabilities = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = capabilities
SPEC.loader.exec_module(capabilities)


def test_modelir_slice_d_and_frame_alpha_keep_independent_cutover_gates() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")

    assert capabilities.validate_capabilities(payload) == []
    assert capabilities.capability_is_enabled(payload, "abi_v1_base") is True
    assert capabilities.capability_is_enabled(payload, "modelir_v2_rust_wire") is True
    assert capabilities.capability_is_enabled(payload, "modelir_v2_cpp_core") is True
    assert payload["capabilities"]["modelir_v2_cpp_core"]["cutover_gate"] == "C1"
    assert capabilities.capability_is_enabled(payload, "modelir_v2") is True
    assert payload["capabilities"]["modelir_v2"]["cutover_gate"] == "C3"
    assert (
        capabilities.capability_is_enabled(payload, "linear_frame3d_cpu_alpha") is True
    )
    assert payload["capabilities"]["linear_frame3d_cpu_alpha"]["cutover_gate"] == "C1"
    frame_claim = payload["capabilities"]["linear_frame3d_cpu_alpha"]["claim"]
    for open_boundary in (
        "no HIP parity",
        "checkpoint",
        "Workbench",
        "release authority",
    ):
        assert open_boundary in frame_claim
    assert "independent Rust member-force recovery replay" in frame_claim
    assert "ABI v1.5" in frame_claim
    assert "uniform initial-member-local QX/QY/QZ" in frame_claim
    assert "RX/RY/RZ member-end releases" in frame_claim
    assert "rigid offsets" in frame_claim
    assert "released-member static-condensation" in frame_claim
    for load_boundary in (
        "no nonuniform or member-point load",
        "self weight",
        "translational release",
    ):
        assert load_boundary in frame_claim
    assert (
        capabilities.capability_is_enabled(
            payload, "linear_frame3d_result_report_alpha"
        )
        is True
    )
    assert (
        payload["capabilities"]["linear_frame3d_result_report_alpha"]["cutover_gate"]
        == "C5"
    )
    result_report_claim = payload["capabilities"][
        "linear_frame3d_result_report_alpha"
    ]["claim"]
    for open_boundary in (
        "no PDF",
        "Workbench execution flow",
        "external comparison",
        "HIP parity",
        "release authority",
    ):
        assert open_boundary in result_report_claim
    assert "independent Rust recovery-replay-gated" in result_report_claim
    assert "uniform initial-member-local force loads" in result_report_claim
    assert "RX/RY/RZ member-end releases" in result_report_claim
    assert "finite global rigid end offsets" in result_report_claim
    assert "no translational release" in result_report_claim
    assert (
        capabilities.capability_is_enabled(
            payload, "linear_frame3d_workbench_consumer_alpha"
        )
        is True
    )
    assert (
        payload["capabilities"]["linear_frame3d_workbench_consumer_alpha"][
            "cutover_gate"
        ]
        == "C0"
    )
    workbench_claim = payload["capabilities"][
        "linear_frame3d_workbench_consumer_alpha"
    ]["claim"]
    for open_boundary in (
        "no analysis submission",
        "durable native job",
        "browser-side recovery reconstruction",
        "external comparison",
        "WorkBench execution E2E",
        "release authority",
    ):
        assert open_boundary.lower() in workbench_claim.lower()
    for capability in (
        "checkpoint_restart",
        "product_e2e",
        "hip_backend",
    ):
        assert capabilities.capability_is_enabled(payload, capability) is False


def test_implemented_capability_requires_a_cutover_gate() -> None:
    payload = {
        "schema_version": "native-capabilities.v1",
        "capabilities": {
            capability: {
                "status": "planned",
                "cutover_gate": None,
                "owner": owner,
                "claim": "not implemented",
            }
            for capability, owner in capabilities.EXPECTED_OWNERS.items()
        },
    }
    payload["capabilities"]["modelir_v2"]["status"] = "implemented"

    assert "native_capability_gate_missing:modelir_v2" in (
        capabilities.validate_capabilities(payload)
    )
