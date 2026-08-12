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


def test_manifest_keeps_each_native_slice_at_its_verified_gate() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")

    assert capabilities.validate_capabilities(payload) == []
    assert capabilities.capability_is_enabled(payload, "abi_v1_base") is True
    assert (
        capabilities.capability_is_enabled(payload, "modelir_v2_rust_wire") is True
    )
    assert capabilities.capability_is_enabled(payload, "modelir_v2_cpp_core") is True
    assert payload["capabilities"]["modelir_v2_cpp_core"]["cutover_gate"] == "C1"
    assert capabilities.capability_is_enabled(payload, "modelir_v2") is True
    assert payload["capabilities"]["modelir_v2"]["cutover_gate"] == "C3"
    assert capabilities.capability_is_enabled(payload, "track_point_load_cpu") is True
    assert payload["capabilities"]["track_point_load_cpu"]["cutover_gate"] == "C1"
    assert "Python C1 oracle parity" in payload["capabilities"]["track_point_load_cpu"]["claim"]
    assert "broader input-space parity" in payload["capabilities"]["track_point_load_cpu"]["claim"]
    assert capabilities.capability_is_enabled(payload, "nonlinear_static_cpu") is True
    nonlinear = payload["capabilities"]["nonlinear_static_cpu"]
    assert nonlinear["cutover_gate"] == "C1"
    assert "Python C1 oracle parity" in nonlinear["claim"]
    assert "five-case" in nonlinear["claim"]
    assert "broader nonlinear input-space parity" in nonlinear["claim"]
    assert capabilities.capability_is_enabled(payload, "nonlinear_ndtha_cpu") is True
    ndtha = payload["capabilities"]["nonlinear_ndtha_cpu"]
    assert ndtha["cutover_gate"] == "C1"
    assert "ABI v1.4" in ndtha["claim"]
    assert "independent dense-matrix Python C1" in ndtha["claim"]
    assert "five-case" in ndtha["claim"]
    assert "broader dynamic input-space parity" in ndtha["claim"]
    assert (
        capabilities.capability_is_enabled(payload, "checkpoint_restart") is True
    )
    checkpoint = payload["capabilities"]["checkpoint_restart"]
    assert checkpoint["cutover_gate"] == "C4"
    assert "bounded CPU" in checkpoint["claim"]
    assert "model, state and execution SHA-256" in checkpoint["claim"]
    assert "job-state crash recovery" in checkpoint["claim"]
    assert capabilities.capability_is_enabled(payload, "product_e2e") is True
    product = payload["capabilities"]["product_e2e"]
    assert product["cutover_gate"] == "C5"
    assert "bounded CPU nonlinear-NDTHA" in product["claim"]
    assert "ResultIR, ReportIR" in product["claim"]
    assert "no Python or Node" in product["claim"]
    assert "durable jobs/API" in product["claim"]
    assert capabilities.capability_is_enabled(payload, "hip_backend") is False


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
