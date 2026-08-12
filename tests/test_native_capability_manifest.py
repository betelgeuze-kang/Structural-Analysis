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
    assert (
        capabilities.capability_is_enabled(payload, "modelir_ndtha_product_e2e")
        is True
    )
    model_product = payload["capabilities"]["modelir_ndtha_product_e2e"]
    assert model_product["cutover_gate"] == "C5"
    assert "content/semantic/provenance" in model_product["claim"]
    assert "Python/Node-free" in model_product["claim"]
    assert capabilities.capability_is_enabled(payload, "mgt_import_health") is True
    mgt_import = payload["capabilities"]["mgt_import_health"]
    assert mgt_import["cutover_gate"] == "C5"
    assert "original bytes" in mgt_import["claim"]
    assert "mapped/preserved_only/dropped/unsupported" in mgt_import["claim"]
    assert "Python C1" in mgt_import["claim"]
    assert "CP949" in mgt_import["claim"]
    assert "C6" in mgt_import["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "reference_materials_elements_cpu"
        )
        is True
    )
    reference = payload["capabilities"]["reference_materials_elements_cpu"]
    assert reference["cutover_gate"] == "C1"
    assert "trial/commit/rollback" in reference["claim"]
    assert "tangent, consistent-mass, residual, JVP and recovery" in reference["claim"]
    assert "ABI v1.7" in reference["claim"]
    assert "HIP C2" in reference["claim"]
    assert capabilities.capability_is_enabled(payload, "dense_assembly_cpu") is True
    assembly = payload["capabilities"]["dense_assembly_cpu"]
    assert assembly["cutover_gate"] == "C1"
    assert assembly["owner"] == "structural_assembly"
    assert "unique stable element order" in assembly["claim"]
    assert "CSR" in assembly["claim"]
    assert "HIP C2" in assembly["claim"]
    assert capabilities.capability_is_enabled(payload, "sparse_linear_solver_cpu") is True
    sparse = payload["capabilities"]["sparse_linear_solver_cpu"]
    assert sparse["cutover_gate"] == "C1"
    assert sparse["owner"] == "structural_solver_cpu"
    assert "canonical CSR" in sparse["claim"]
    assert "independent NumPy direct-solve oracle" in sparse["claim"]
    assert "ABI v1.8" in sparse["claim"]
    assert "safe reentrant Rust wrapper" in sparse["claim"]
    assert "sequential gate remains C1" in sparse["claim"]
    assert "HIP C2" in sparse["claim"]
    assert "C6" in sparse["claim"]
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
    assert "HIP C2" in checkpoint["claim"]
    assert capabilities.capability_is_enabled(payload, "product_e2e") is True
    product = payload["capabilities"]["product_e2e"]
    assert product["cutover_gate"] == "C5"
    assert "bounded CPU nonlinear-NDTHA" in product["claim"]
    assert "ResultIR, ReportIR" in product["claim"]
    assert "no Python or Node" in product["claim"]
    assert "durable jobs/API" in product["claim"]
    assert capabilities.capability_is_enabled(payload, "durable_jobs") is True
    durable = payload["capabilities"]["durable_jobs"]
    assert durable["cutover_gate"] == "C5"
    assert "bounded single-host CPU nonlinear-NDTHA" in durable["claim"]
    assert "expired-lease crash reconciliation" in durable["claim"]
    assert "tenant authorization" in durable["claim"]
    assert "HIP C2" in durable["claim"]
    assert "C6" in durable["claim"]
    assert capabilities.capability_is_enabled(payload, "service_api") is True
    service = payload["capabilities"]["service_api"]
    assert service["cutover_gate"] == "C5"
    assert service["owner"] == "structural-cli"
    assert "loopback single-host single-tenant" in service["claim"]
    assert "distinct hashed client/worker bearer credentials" in service["claim"]
    assert "process kill after checkpoint" in service["claim"]
    assert "byte-identical to direct native execution" in service["claim"]
    assert "tenant isolation" in service["claim"]
    assert "HIP C2" in service["claim"]
    assert "C6" in service["claim"]
    assert capabilities.capability_is_enabled(payload, "external_comparison") is True
    comparison = payload["capabilities"]["external_comparison"]
    assert comparison["cutover_gate"] == "C5"
    assert "bounded global nonlinear-NDTHA" in comparison["claim"]
    assert "verifies source artifact bytes" in comparison["claim"]
    assert "live MIDAS/OpenSees/CalculiX execution" in comparison["claim"]
    assert "node/member mapping" in comparison["claim"]
    assert "HIP C2" in comparison["claim"]
    assert "C6" in comparison["claim"]
    assert capabilities.capability_is_enabled(payload, "pdf_report") is True
    pdf = payload["capabilities"]["pdf_report"]
    assert pdf["cutover_gate"] == "C5"
    assert pdf["owner"] == "structural-report"
    assert "deterministic A4 PDF 1.7" in pdf["claim"]
    assert "validates its own xref/object/trailer" in pdf["claim"]
    assert "no Python, Node or external renderer lookup" in pdf["claim"]
    assert "PDF/A" in pdf["claim"]
    assert "tagged accessibility" in pdf["claim"]
    assert "HIP C2" in pdf["claim"]
    assert "C6" in pdf["claim"]
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
