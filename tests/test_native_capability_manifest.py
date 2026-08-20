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
    assert capabilities.capability_is_enabled(payload, "backend_selector") is True
    backend_selector = payload["capabilities"]["backend_selector"]
    assert backend_selector["cutover_gate"] == "C3"
    assert "ABI v1.12" in backend_selector["claim"]
    assert "sa_get_api_v1" in backend_selector["claim"]
    assert "fails closed" in backend_selector["claim"]
    assert "C6" in backend_selector["claim"]
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
    assert "constraint-reduced canonical-CSR" in assembly["claim"]
    assert "sorted active-DOF map" in assembly["claim"]
    assert "irregular constrained three-element CSR graph" in assembly["claim"]
    assert "typed ModelIR linear-graph" in assembly["claim"]
    assert "six canonical DOFs per node" in assembly["claim"]
    assert "content/semantic/provenance identities" in assembly["claim"]
    assert "seven active DOFs and 43 structural entries" in assembly["claim"]
    assert "internal/external/equilibrium residual" in assembly["claim"]
    assert "sorted constrained global DOFs" in assembly["claim"]
    assert "constrained internal load, external load and reaction" in assembly["claim"]
    assert "ABI v1.14" in assembly["claim"]
    assert "product reaction publication" in assembly["claim"]
    assert "nonzero prescribed constraints" in assembly["claim"]
    assert "shell/nonlinear ModelIR graphs" in assembly["claim"]
    assert "HIP C2" in assembly["claim"]
    reaction_results = payload["capabilities"]["modelir_linear_reaction_results"]
    assert reaction_results["cutover_gate"] == "C5"
    assert reaction_results["owner"] == "structural-contracts"
    assert "ABI v1.14" in reaction_results["claim"]
    assert "internal-minus-external reaction" in reaction_results["claim"]
    assert "canonical self-hashed reaction ResultIR" in reaction_results["claim"]
    assert "durable jobs and loopback retrieval" in reaction_results["claim"]
    assert "Workbench inspect/review/export" in reaction_results["claim"]
    assert "distribution v84" in reaction_results["claim"]
    assert "rootfs diagnostic v7" in reaction_results["claim"]
    assert "HIP C2" in reaction_results["claim"]
    assert "C6" in reaction_results["claim"]
    model_linear_checkpoint = payload["capabilities"]["modelir_linear_checkpoint"]
    assert model_linear_checkpoint["cutover_gate"] == "C4"
    assert model_linear_checkpoint["owner"] == "structural-runtime"
    assert "SAMLPC01" in model_linear_checkpoint["claim"]
    assert "separately derived constrained-reaction ResultIR" in model_linear_checkpoint["claim"]
    assert "not duplicated inside the checkpoint" in model_linear_checkpoint["claim"]
    model_linear_product = payload["capabilities"]["modelir_linear_product_e2e"]
    assert model_linear_product["cutover_gate"] == "C5"
    assert model_linear_product["owner"] == "structural-cli"
    assert "ABI v1.14" in model_linear_product["claim"]
    assert "constrained-reaction ResultIR" in model_linear_product["claim"]
    assert "15-artifact directories" in model_linear_product["claim"]
    model_linear_jobs = payload["capabilities"]["modelir_linear_durable_jobs"]
    assert model_linear_jobs["cutover_gate"] == "C5"
    assert model_linear_jobs["owner"] == "structural-runtime"
    assert "constrained-reaction ResultIR" in model_linear_jobs["claim"]
    assert "six artifacts" in model_linear_jobs["claim"]
    assert "legacy no-reaction claim" in model_linear_jobs["claim"]
    model_linear_service = payload["capabilities"]["modelir_linear_service_api"]
    assert model_linear_service["cutover_gate"] == "C5"
    assert model_linear_service["owner"] == "structural-cli"
    assert "/v1/jobs/{job_id}/reaction-result-ir" in model_linear_service["claim"]
    assert "socket-free service test" in model_linear_service["claim"]
    assert "HIP C2" in model_linear_service["claim"]
    assert "C6" in model_linear_service["claim"]
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
    assert "iteration control resident" in sparse["claim"]
    assert "fallback 0" in sparse["claim"]
    assert "native-hip-approved" in sparse["claim"]
    assert "C6" in sparse["claim"]
    assert capabilities.capability_is_enabled(payload, "sparse_linear_checkpoint") is True
    sparse_checkpoint = payload["capabilities"]["sparse_linear_checkpoint"]
    assert sparse_checkpoint["cutover_gate"] == "C4"
    assert sparse_checkpoint["owner"] == "structural-runtime"
    assert "SAPCGC01" in sparse_checkpoint["claim"]
    assert "real iteration state" in sparse_checkpoint["claim"]
    assert "HIP C2" in sparse_checkpoint["claim"]
    assert "C6" in sparse_checkpoint["claim"]
    assert capabilities.capability_is_enabled(payload, "sparse_linear_product_e2e") is True
    sparse_product = payload["capabilities"]["sparse_linear_product_e2e"]
    assert sparse_product["cutover_gate"] == "C5"
    assert sparse_product["owner"] == "structural-cli"
    assert "ResultIR, ReportIR" in sparse_product["claim"]
    assert "no Python or Node" in sparse_product["claim"]
    assert "HIP C2" in sparse_product["claim"]
    assert "C6" in sparse_product["claim"]
    assert capabilities.capability_is_enabled(
        payload, "generalized_eigen_solver_cpu"
    ) is True
    generalized = payload["capabilities"]["generalized_eigen_solver_cpu"]
    assert generalized["cutover_gate"] == "C1"
    assert generalized["owner"] == "structural_solver_cpu"
    assert "modal and linear-buckling" in generalized["claim"]
    assert "independent SciPy generalized-eigen oracle" in generalized["claim"]
    assert "coordinate-axis canonical mode bases" in generalized["claim"]
    assert "HIP C2" in generalized["claim"]
    assert "ABI C3" in generalized["claim"]
    assert "fallback 0" in generalized["claim"]
    assert "C6" in generalized["claim"]
    assert capabilities.capability_is_enabled(
        payload, "generalized_eigen_checkpoint"
    ) is True
    generalized_checkpoint = payload["capabilities"]["generalized_eigen_checkpoint"]
    assert generalized_checkpoint["cutover_gate"] == "C4"
    assert generalized_checkpoint["owner"] == "structural-runtime"
    assert "SAEIGC01" in generalized_checkpoint["claim"]
    assert "mid-Jacobi" in generalized_checkpoint["claim"]
    assert "HIP C2" in generalized_checkpoint["claim"]
    assert "C6" in generalized_checkpoint["claim"]
    assert capabilities.capability_is_enabled(
        payload, "generalized_eigen_product_e2e"
    ) is True
    generalized_product = payload["capabilities"]["generalized_eigen_product_e2e"]
    assert generalized_product["cutover_gate"] == "C5"
    assert generalized_product["owner"] == "structural-cli"
    assert "ResultIR, ReportIR" in generalized_product["claim"]
    assert "no Python or Node" in generalized_product["claim"]
    assert "HIP C2" in generalized_product["claim"]
    assert "C6" in generalized_product["claim"]
    assert capabilities.capability_is_enabled(
        payload, "modelir_modal_product_e2e"
    ) is True
    modelir_modal = payload["capabilities"]["modelir_modal_product_e2e"]
    assert modelir_modal["cutover_gate"] == "C5"
    assert modelir_modal["owner"] == "structural-cli"
    assert "typed-ModelIR frame3d/truss3d CPU modal" in modelir_modal["claim"]
    assert "ABI v1.14" in modelir_modal["claim"]
    assert "ABI v1.9" in modelir_modal["claim"]
    assert "linear buckling" in modelir_modal["claim"]
    assert "HIP C2" in modelir_modal["claim"]
    assert "C6" in modelir_modal["claim"]
    assert capabilities.capability_is_enabled(
        payload, "modelir_modal_request_authoring"
    ) is True
    modal_authoring = payload["capabilities"]["modelir_modal_request_authoring"]
    assert modal_authoring["cutover_gate"] == "C5"
    assert modal_authoring["owner"] == "structural-workbench"
    assert "model-create-modal-analysis-request" in modal_authoring["claim"]
    assert "ABI v1.14" in modal_authoring["claim"]
    assert "ABI v1.9" in modal_authoring["claim"]
    assert "execution_started false" in modal_authoring["claim"]
    assert "installed distribution" in modal_authoring["claim"]
    assert "HIP C2" in modal_authoring["claim"]
    assert "C6" in modal_authoring["claim"]
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
    assert "bounded single-thread FP64 HIP C2 candidate" in nonlinear["claim"]
    assert "exact local CPU/HIP status/iteration/plastic/backtrack parity" in nonlinear["claim"]
    assert "native-hip-approved" in nonlinear["claim"]
    assert capabilities.capability_is_enabled(payload, "nonlinear_ndtha_cpu") is True
    ndtha = payload["capabilities"]["nonlinear_ndtha_cpu"]
    assert ndtha["cutover_gate"] == "C1"
    assert "ABI v1.4" in ndtha["claim"]
    assert "independent dense-matrix Python C1" in ndtha["claim"]
    assert "five-case" in ndtha["claim"]
    assert "broader dynamic input-space parity" in ndtha["claim"]
    assert "single-thread FP64 HIP C2 candidate" in ndtha["claim"]
    assert "Newmark/Newton control" in ndtha["claim"]
    assert "exact local CPU/HIP" in ndtha["claim"]
    assert "native-hip-approved" in ndtha["claim"]
    assert "fallback 0" in ndtha["claim"]
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
    assert capabilities.capability_is_enabled(payload, "native_workbench") is True
    workbench = payload["capabilities"]["native_workbench"]
    assert workbench["cutover_gate"] == "C5"
    assert workbench["owner"] == "structural-workbench"
    assert "Import -> Validate -> Run -> Resume -> Compare -> Report" in workbench["claim"]
    assert (
        "Inspect -> Report-view -> Result-view -> Result-deformed-view -> Review -> Export"
        in workbench["claim"]
    )
    assert "process death after checkpoint publication" in workbench["claim"]
    assert "no Python, Node, browser, CLI subprocess" in workbench["claim"]
    assert "never inferred" in workbench["claim"]
    assert "Catalog/Catalog-show" in workbench["claim"]
    assert "Evidence/Evidence-show" in workbench["claim"]
    assert "English/Korean UTF-8 linear report view" in workbench["claim"]
    assert "general ModelIR terminal topology view" in workbench["claim"]
    assert "closed `en-US`/`ko-KR` paths" in workbench["claim"]
    assert "provenance-bound editors cover the root model identity" in workbench["claim"]
    assert "typed-reference-cascading node identity" in workbench["claim"]
    assert "v1 frame and truss sections" in workbench["claim"]
    assert "compatible frame and truss element property references" in workbench["claim"]
    assert "model-edit-truss-section" in workbench["claim"]
    assert "model-edit-truss-element-properties" in workbench["claim"]
    assert "truss3d section/member" in workbench["claim"]
    assert "model-delete-frame3d-leaf-member" in workbench["claim"]
    assert "model-delete-truss3d-leaf-member" in workbench["claim"]
    assert "model-delete-fixed-constraint" in workbench["claim"]
    assert "model-delete-linear-material" in workbench["claim"]
    assert "model-delete-frame-section" in workbench["claim"]
    assert "model-delete-truss-section" in workbench["claim"]
    assert "one standalone neutral node" in workbench["claim"]
    assert "model-add-node" in workbench["claim"]
    assert "model-delete-orphan-node" in workbench["claim"]
    assert "model-add-linear-load-combination" in workbench["claim"]
    assert "model-delete-linear-load-combination" in workbench["claim"]
    assert "two through 64 unique pattern terms" in workbench["claim"]
    assert "v2 deletion provenance beyond two terms" in workbench["claim"]
    assert "depth-eight/64-leaf acyclic nested root" in workbench["claim"]
    assert "nested v3 root/expanded-term provenance" in workbench["claim"]
    assert "retained child-combination CPU execution" in workbench["claim"]
    assert "English/Korean bounded self-hashed NDTHA response-history view" in workbench["claim"]
    assert "English/Korean exact-profile deformed-shape view" in workbench["claim"]
    assert "neither surface is WCAG, PDF/UA" in workbench["claim"]
    assert "React/TypeScript removal" in workbench["claim"]
    assert "HIP C2" in workbench["claim"]
    assert "C6" in workbench["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_model_identity_edit") is True
    model_identity_edit = payload["capabilities"]["modelir_model_identity_edit"]
    assert model_identity_edit["cutover_gate"] == "C5"
    assert model_identity_edit["owner"] == "structural-workbench"
    assert "exact expected source model_id" in model_identity_edit["claim"]
    assert "C++-canonical source document with model_id removed" in model_identity_edit["claim"]
    assert "distribution v75 E2E" in model_identity_edit["claim"]
    assert "byte-identical initialized restart" in model_identity_edit["claim"]
    assert "fallback 0" in model_identity_edit["claim"]
    assert "HIP C2" in model_identity_edit["claim"]
    assert "C6" in model_identity_edit["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_node_add") is True
    node_add = payload["capabilities"]["modelir_node_add"]
    assert node_add["cutover_gate"] == "C5"
    assert node_add["owner"] == "structural-workbench"
    assert "next contiguous index" in node_add["claim"]
    assert "neutral source ownership" in node_add["claim"]
    assert "single C ABI into C++" in node_add["claim"]
    assert "exact unchanged active DOFs/load" in node_add["claim"]
    assert "fallback 0" in node_add["claim"]
    assert "HIP C2" in node_add["claim"]
    assert "C6" in node_add["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_node_identity_cascade_edit"
        )
        is True
    )
    node_identity_cascade = payload["capabilities"][
        "modelir_node_identity_cascade_edit"
    ]
    assert node_identity_cascade["cutover_gate"] == "C5"
    assert node_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every typed" in node_identity_cascade["claim"]
    assert "direct node round-trip" in node_identity_cascade["claim"]
    assert "distribution v76 E2E" in node_identity_cascade["claim"]
    assert "N2_LINKED" in node_identity_cascade["claim"]
    assert "byte-identical initialized restart" in node_identity_cascade["claim"]
    assert "fallback 0" in node_identity_cascade["claim"]
    assert "approved HIP C2" in node_identity_cascade["claim"]
    assert "C6" in node_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_frame_section_identity_cascade_edit"
        )
        is True
    )
    frame_section_identity_cascade = payload["capabilities"][
        "modelir_frame_section_identity_cascade_edit"
    ]
    assert frame_section_identity_cascade["cutover_gate"] == "C5"
    assert frame_section_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every typed" in frame_section_identity_cascade["claim"]
    assert "direct section round-trip" in frame_section_identity_cascade["claim"]
    assert "distribution v77 E2E" in frame_section_identity_cascade["claim"]
    assert "S1_LINKED" in frame_section_identity_cascade["claim"]
    assert "byte-identical initialized restart" in frame_section_identity_cascade["claim"]
    assert "fallback 0" in frame_section_identity_cascade["claim"]
    assert "approved HIP C2" in frame_section_identity_cascade["claim"]
    assert "C6" in frame_section_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_material_identity_cascade_edit"
        )
        is True
    )
    linear_material_identity_cascade = payload["capabilities"][
        "modelir_linear_material_identity_cascade_edit"
    ]
    assert linear_material_identity_cascade["cutover_gate"] == "C5"
    assert linear_material_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every typed" in linear_material_identity_cascade["claim"]
    assert "direct material round-trip" in linear_material_identity_cascade["claim"]
    assert "distribution v78 E2E" in linear_material_identity_cascade["claim"]
    assert "M1_LINKED" in linear_material_identity_cascade["claim"]
    assert "byte-identical initialized restart" in linear_material_identity_cascade["claim"]
    assert "fallback 0" in linear_material_identity_cascade["claim"]
    assert "approved HIP C2" in linear_material_identity_cascade["claim"]
    assert "C6" in linear_material_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_truss_section_identity_cascade_edit"
        )
        is True
    )
    truss_section_identity_cascade = payload["capabilities"][
        "modelir_truss_section_identity_cascade_edit"
    ]
    assert truss_section_identity_cascade["cutover_gate"] == "C5"
    assert truss_section_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every typed" in truss_section_identity_cascade["claim"]
    assert "direct section round-trip" in truss_section_identity_cascade["claim"]
    assert "distribution v79 E2E" in truss_section_identity_cascade["claim"]
    assert "T1_LINKED" in truss_section_identity_cascade["claim"]
    assert "byte-identical initialized restart" in truss_section_identity_cascade["claim"]
    assert "fallback 0" in truss_section_identity_cascade["claim"]
    assert "approved HIP C2" in truss_section_identity_cascade["claim"]
    assert "C6" in truss_section_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_pattern_identity_cascade_edit"
        )
        is True
    )
    load_pattern_identity_cascade = payload["capabilities"][
        "modelir_linear_load_pattern_identity_cascade_edit"
    ]
    assert load_pattern_identity_cascade["cutover_gate"] == "C5"
    assert load_pattern_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every typed" in load_pattern_identity_cascade["claim"]
    assert "construction-stage" in load_pattern_identity_cascade["claim"]
    assert "direct load_pattern round-trip" in load_pattern_identity_cascade["claim"]
    assert "distribution v80 E2E" in load_pattern_identity_cascade["claim"]
    assert "LC_WEAK_LINKED" in load_pattern_identity_cascade["claim"]
    assert "byte-identical initialized restart" in load_pattern_identity_cascade["claim"]
    assert "fallback 0" in load_pattern_identity_cascade["claim"]
    assert "approved HIP C2" in load_pattern_identity_cascade["claim"]
    assert "C6" in load_pattern_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_combination_identity_cascade_edit"
        )
        is True
    )
    load_combination_identity_cascade = payload["capabilities"][
        "modelir_linear_load_combination_identity_cascade_edit"
    ]
    assert load_combination_identity_cascade["cutover_gate"] == "C5"
    assert load_combination_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every downstream" in load_combination_identity_cascade["claim"]
    assert "direct load_combination round-trip" in load_combination_identity_cascade["claim"]
    assert "mathematical expansion is verified unchanged" in load_combination_identity_cascade["claim"]
    assert "distribution v81 E2E" in load_combination_identity_cascade["claim"]
    assert "COMBO_BASE_LINKED" in load_combination_identity_cascade["claim"]
    assert "byte-identical initialized restart" in load_combination_identity_cascade["claim"]
    assert "fallback 0" in load_combination_identity_cascade["claim"]
    assert "approved HIP C2" in load_combination_identity_cascade["claim"]
    assert "C6" in load_combination_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_element_identity_cascade_edit"
        )
        is True
    )
    element_identity_cascade = payload["capabilities"][
        "modelir_element_identity_cascade_edit"
    ]
    assert element_identity_cascade["cutover_gate"] == "C5"
    assert element_identity_cascade["owner"] == "structural-workbench"
    assert "atomically updates every construction_stages" in element_identity_cascade["claim"]
    assert "direct element round-trip" in element_identity_cascade["claim"]
    assert "normalized MGT round-trip mapping" in element_identity_cascade["claim"]
    assert "distribution v82 E2E" in element_identity_cascade["claim"]
    assert "E_1 with E1_LINKED" in element_identity_cascade["claim"]
    assert "byte-identical initialized restart" in element_identity_cascade["claim"]
    assert "fallback 0" in element_identity_cascade["claim"]
    assert "approved HIP C2" in element_identity_cascade["claim"]
    assert "C6" in element_identity_cascade["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_fixed_constraint_identity_cascade_edit"
        )
        is True
    )
    fixed_constraint_identity_cascade = payload["capabilities"][
        "modelir_fixed_constraint_identity_cascade_edit"
    ]
    assert fixed_constraint_identity_cascade["cutover_gate"] == "C5"
    assert fixed_constraint_identity_cascade["owner"] == "structural-workbench"
    assert (
        "atomically updates every construction_stages"
        in fixed_constraint_identity_cascade["claim"]
    )
    assert "direct constraint round-trip" in fixed_constraint_identity_cascade["claim"]
    assert "normalized MGT round-trip mapping" in fixed_constraint_identity_cascade["claim"]
    assert "distribution v83 E2E" in fixed_constraint_identity_cascade["claim"]
    assert "C_1 with C1_LINKED" in fixed_constraint_identity_cascade["claim"]
    assert "byte-identical initialized restart" in fixed_constraint_identity_cascade["claim"]
    assert "fallback 0" in fixed_constraint_identity_cascade["claim"]
    assert "approved HIP C2" in fixed_constraint_identity_cascade["claim"]
    assert "C6" in fixed_constraint_identity_cascade["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_orphan_node_delete") is True
    orphan_node_delete = payload["capabilities"]["modelir_orphan_node_delete"]
    assert orphan_node_delete["cutover_gate"] == "C5"
    assert orphan_node_delete["owner"] == "structural-workbench"
    assert "last contiguous" in orphan_node_delete["claim"]
    assert "extension-free" in orphan_node_delete["claim"]
    assert "element, constraint, nested nodal-load" in orphan_node_delete["claim"]
    assert "single C ABI into C++" in orphan_node_delete["claim"]
    assert "exact restored two-node topology" in orphan_node_delete["claim"]
    assert "fallback 0" in orphan_node_delete["claim"]
    assert "HIP C2" in orphan_node_delete["claim"]
    assert "C6" in orphan_node_delete["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_combination_add"
        )
        is True
    )
    load_combination_add = payload["capabilities"][
        "modelir_linear_load_combination_add"
    ]
    assert load_combination_add["cutover_gate"] == "C5"
    assert load_combination_add["owner"] == "structural-workbench"
    assert "exactly two ordered terms" in load_combination_add["claim"]
    assert "distinct existing linear_static load patterns" in load_combination_add["claim"]
    assert "finite nonzero factors" in load_combination_add["claim"]
    assert "single C ABI into C++" in load_combination_add["claim"]
    assert "bounded C++ CPU combination-execution surface" in load_combination_add["claim"]
    assert "nested combination references" in load_combination_add["claim"]
    assert "approved HIP C2" in load_combination_add["claim"]
    assert "C6" in load_combination_add["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_combination_deletion"
        )
        is True
    )
    load_combination_delete = payload["capabilities"][
        "modelir_linear_load_combination_deletion"
    ]
    assert load_combination_delete["cutover_gate"] == "C5"
    assert load_combination_delete["owner"] == "structural-workbench"
    assert "last contiguous" in load_combination_delete["claim"]
    assert "exactly two ordered terms" in load_combination_delete["claim"]
    assert "distinct existing linear_static load patterns" in load_combination_delete["claim"]
    assert "single C ABI into C++" in load_combination_delete["claim"]
    assert "restores direct load-pattern CPU request/execution" in load_combination_delete["claim"]
    assert "checkpoint/restart parity" in load_combination_delete["claim"]
    assert "fallback 0" in load_combination_delete["claim"]
    assert "approved HIP C2" in load_combination_delete["claim"]
    assert "C6" in load_combination_delete["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_combination_execution"
        )
        is True
    )
    load_combination_execution = payload["capabilities"][
        "modelir_linear_load_combination_execution"
    ]
    assert load_combination_execution["cutover_gate"] == "C5"
    assert load_combination_execution["owner"] == "structural-workbench"
    assert "frozen ABI v1.13 table" in load_combination_execution["claim"]
    assert "unambiguous load-case selector" in load_combination_execution["claim"]
    assert "exactly two distinct direct linear_static patterns" in load_combination_execution["claim"]
    assert "distribution v44 E2E" in load_combination_execution["claim"]
    assert "byte-identical direct/restart output" in load_combination_execution["claim"]
    assert "fallback 0" in load_combination_execution["claim"]
    assert "HIP C2" in load_combination_execution["claim"]
    assert "C6" in load_combination_execution["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_authoring_execution"
        )
        is True
    )
    direct_combination = payload["capabilities"][
        "modelir_direct_linear_load_combination_authoring_execution"
    ]
    assert direct_combination["cutover_gate"] == "C5"
    assert direct_combination["owner"] == "structural-workbench"
    assert "two through 64 ordered terms" in direct_combination["claim"]
    assert "exact two-term v1 provenance and request-receipt contract" in direct_combination["claim"]
    assert "three through 64 terms" in direct_combination["claim"]
    assert "frozen ABI v1.13 table" in direct_combination["claim"]
    assert "distribution v45 E2E" in direct_combination["claim"]
    assert "exact three-pattern active external load" in direct_combination["claim"]
    assert "byte-identical direct/restart output" in direct_combination["claim"]
    assert "fallback 0" in direct_combination["claim"]
    assert "nested combinations" in direct_combination["claim"]
    assert "HIP C2" in direct_combination["claim"]
    assert "C6" in direct_combination["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_factor_edit"
        )
        is True
    )
    direct_combination_factor_edit = payload["capabilities"][
        "modelir_direct_linear_load_combination_factor_edit"
    ]
    assert direct_combination_factor_edit["cutover_gate"] == "C5"
    assert direct_combination_factor_edit["owner"] == "structural-workbench"
    assert "changes exactly one existing factor" in direct_combination_factor_edit["claim"]
    assert "reference identity" in direct_combination_factor_edit["claim"]
    assert "term order" in direct_combination_factor_edit["claim"]
    assert "term count" in direct_combination_factor_edit["claim"]
    assert "single C ABI into C++" in direct_combination_factor_edit["claim"]
    assert "distribution v49 E2E" in direct_combination_factor_edit["claim"]
    assert "[25000,-13500,5000,0,0,0]" in direct_combination_factor_edit["claim"]
    assert "byte-identical direct/restart output" in direct_combination_factor_edit["claim"]
    assert "fallback 0" in direct_combination_factor_edit["claim"]
    assert "approved HIP C2" in direct_combination_factor_edit["claim"]
    assert "C6" in direct_combination_factor_edit["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_reference_edit"
        )
        is True
    )
    direct_combination_reference_edit = payload["capabilities"][
        "modelir_direct_linear_load_combination_reference_edit"
    ]
    assert direct_combination_reference_edit["cutover_gate"] == "C5"
    assert direct_combination_reference_edit["owner"] == "structural-workbench"
    assert (
        "replaces exactly one existing load_pattern"
        in direct_combination_reference_edit["claim"]
    )
    assert "every factor" in direct_combination_reference_edit["claim"]
    assert "term order/count" in direct_combination_reference_edit["claim"]
    assert "single C ABI into C++" in direct_combination_reference_edit["claim"]
    assert "distribution v51 E2E" in direct_combination_reference_edit["claim"]
    assert "[120000,0,5000,0,0,0]" in direct_combination_reference_edit["claim"]
    assert "byte-identical direct/restart output" in direct_combination_reference_edit["claim"]
    assert "fallback 0" in direct_combination_reference_edit["claim"]
    assert "approved HIP C2" in direct_combination_reference_edit["claim"]
    assert "C6" in direct_combination_reference_edit["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_term_add"
        )
        is True
    )
    direct_combination_term_add = payload["capabilities"][
        "modelir_direct_linear_load_combination_term_add"
    ]
    assert direct_combination_term_add["cutover_gate"] == "C5"
    assert direct_combination_term_add["owner"] == "structural-workbench"
    assert "appends exactly one new load_pattern term" in direct_combination_term_add["claim"]
    assert "two through 63 ordered" in direct_combination_term_add["claim"]
    assert "yielding three through 64 terms" in direct_combination_term_add["claim"]
    assert "single C ABI into C++" in direct_combination_term_add["claim"]
    assert "distribution v53 E2E" in direct_combination_term_add["claim"]
    assert "[25000,-12000,5000,0,0,0]" in direct_combination_term_add["claim"]
    assert "byte-identical direct/restart output" in direct_combination_term_add["claim"]
    assert "fallback 0" in direct_combination_term_add["claim"]
    assert "approved HIP C2" in direct_combination_term_add["claim"]
    assert "C6" in direct_combination_term_add["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_term_delete"
        )
        is True
    )
    direct_combination_term_delete = payload["capabilities"][
        "modelir_direct_linear_load_combination_term_delete"
    ]
    assert direct_combination_term_delete["cutover_gate"] == "C5"
    assert direct_combination_term_delete["owner"] == "structural-workbench"
    assert "removes exactly one existing load_pattern term" in direct_combination_term_delete["claim"]
    assert "three through 64 ordered" in direct_combination_term_delete["claim"]
    assert "yielding two through 63 terms" in direct_combination_term_delete["claim"]
    assert "single C ABI into C++" in direct_combination_term_delete["claim"]
    assert "distribution v54 E2E" in direct_combination_term_delete["claim"]
    assert "[25000,-12000,0,0,0,0]" in direct_combination_term_delete["claim"]
    assert "byte-identical direct/restart output" in direct_combination_term_delete["claim"]
    assert "fallback 0" in direct_combination_term_delete["claim"]
    assert "approved HIP C2" in direct_combination_term_delete["claim"]
    assert "C6" in direct_combination_term_delete["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_direct_linear_load_combination_deletion"
        )
        is True
    )
    direct_combination_delete = payload["capabilities"][
        "modelir_direct_linear_load_combination_deletion"
    ]
    assert direct_combination_delete["cutover_gate"] == "C5"
    assert direct_combination_delete["owner"] == "structural-workbench"
    assert "two through 64 ordered terms" in direct_combination_delete["claim"]
    assert "exact-two v1 provenance/receipt field set" in direct_combination_delete["claim"]
    assert "v2 deletion provenance" in direct_combination_delete["claim"]
    assert "distribution v47 E2E" in direct_combination_delete["claim"]
    assert "exact restored direct-pattern active load" in direct_combination_delete["claim"]
    assert "byte-identical direct/restart output" in direct_combination_delete["claim"]
    assert "nested deletion" in direct_combination_delete["claim"]
    assert "fallback 0" in direct_combination_delete["claim"]
    assert "HIP C2" in direct_combination_delete["claim"]
    assert "C6" in direct_combination_delete["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_authoring_execution"
        )
        is True
    )
    nested_combination = payload["capabilities"][
        "modelir_nested_linear_load_combination_authoring_execution"
    ]
    assert nested_combination["cutover_gate"] == "C5"
    assert nested_combination["owner"] == "structural-workbench"
    assert "root-inclusive depth at most eight" in nested_combination["claim"]
    assert "64 expanded leaf contributions" in nested_combination["claim"]
    assert "repeated-path factor consolidation" in nested_combination["claim"]
    assert "frozen ABI v1.13 table" in nested_combination["claim"]
    assert "direct v1/v2 receipt bytes remain unchanged" in nested_combination["claim"]
    assert "v3 provenance" in nested_combination["claim"]
    assert "distribution v46 E2E" in nested_combination["claim"]
    assert "exact nested active external load" in nested_combination["claim"]
    assert "byte-identical direct/restart output" in nested_combination["claim"]
    assert "fallback 0" in nested_combination["claim"]
    assert "HIP C2" in nested_combination["claim"]
    assert "C6" in nested_combination["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_term_add"
        )
        is True
    )
    nested_combination_term_add = payload["capabilities"][
        "modelir_nested_linear_load_combination_term_add"
    ]
    assert nested_combination_term_add["cutover_gate"] == "C5"
    assert nested_combination_term_add["owner"] == "structural-workbench"
    assert "appends exactly one new explicitly typed" in nested_combination_term_add["claim"]
    assert "two through 63 ordered unique typed terms" in nested_combination_term_add["claim"]
    assert "yielding three through 64 root terms" in nested_combination_term_add["claim"]
    assert "root-inclusive depth at most eight" in nested_combination_term_add["claim"]
    assert "both complete expansions" in nested_combination_term_add["claim"]
    assert "single C ABI into C++" in nested_combination_term_add["claim"]
    assert "distribution v55 E2E" in nested_combination_term_add["claim"]
    assert "[25000,-6000,1500,0,0,0]" in nested_combination_term_add["claim"]
    assert "byte-identical direct/restart output" in nested_combination_term_add["claim"]
    assert "fallback 0" in nested_combination_term_add["claim"]
    assert "approved HIP C2" in nested_combination_term_add["claim"]
    assert "C6" in nested_combination_term_add["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_term_delete"
        )
        is True
    )
    nested_combination_term_delete = payload["capabilities"][
        "modelir_nested_linear_load_combination_term_delete"
    ]
    assert nested_combination_term_delete["cutover_gate"] == "C5"
    assert nested_combination_term_delete["owner"] == "structural-workbench"
    assert "removes exactly one existing explicitly typed" in nested_combination_term_delete["claim"]
    assert "three through 64 ordered unique typed terms" in nested_combination_term_delete["claim"]
    assert "yielding two through 63 root terms" in nested_combination_term_delete["claim"]
    assert "edited root must retain at least one load_combination reference" in nested_combination_term_delete["claim"]
    assert "root-inclusive depth at most eight" in nested_combination_term_delete["claim"]
    assert "both complete expansions" in nested_combination_term_delete["claim"]
    assert "single C ABI into C++" in nested_combination_term_delete["claim"]
    assert "distribution v56 E2E" in nested_combination_term_delete["claim"]
    assert "[0,-6000,1500,0,0,0]" in nested_combination_term_delete["claim"]
    assert "byte-identical direct/restart output" in nested_combination_term_delete["claim"]
    assert "fallback 0" in nested_combination_term_delete["claim"]
    assert "approved HIP C2" in nested_combination_term_delete["claim"]
    assert "C6" in nested_combination_term_delete["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_factor_edit"
        )
        is True
    )
    nested_combination_factor_edit = payload["capabilities"][
        "modelir_nested_linear_load_combination_factor_edit"
    ]
    assert nested_combination_factor_edit["cutover_gate"] == "C5"
    assert nested_combination_factor_edit["owner"] == "structural-workbench"
    assert "changes exactly one existing root factor" in nested_combination_factor_edit["claim"]
    assert "explicit load_pattern or load_combination" in nested_combination_factor_edit["claim"]
    assert "root term order/count" in nested_combination_factor_edit["claim"]
    assert "descendant combinations" in nested_combination_factor_edit["claim"]
    assert "root-inclusive depth at most eight" in nested_combination_factor_edit["claim"]
    assert "both complete expansions" in nested_combination_factor_edit["claim"]
    assert "distribution v50 E2E" in nested_combination_factor_edit["claim"]
    assert "[25000,-9000,3750,0,0,0]" in nested_combination_factor_edit["claim"]
    assert "byte-identical direct/restart output" in nested_combination_factor_edit["claim"]
    assert "fallback 0" in nested_combination_factor_edit["claim"]
    assert "approved HIP C2" in nested_combination_factor_edit["claim"]
    assert "C6" in nested_combination_factor_edit["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_reference_edit"
        )
        is True
    )
    nested_combination_reference_edit = payload["capabilities"][
        "modelir_nested_linear_load_combination_reference_edit"
    ]
    assert nested_combination_reference_edit["cutover_gate"] == "C5"
    assert nested_combination_reference_edit["owner"] == "structural-workbench"
    assert "replaces exactly one existing root" in nested_combination_reference_edit["claim"]
    assert "explicit source and replacement kinds" in nested_combination_reference_edit["claim"]
    assert "selected factor" in nested_combination_reference_edit["claim"]
    assert "root term order/count" in nested_combination_reference_edit["claim"]
    assert "descendant combinations" in nested_combination_reference_edit["claim"]
    assert "root-inclusive depth at most eight" in nested_combination_reference_edit["claim"]
    assert "both complete expansions" in nested_combination_reference_edit["claim"]
    assert "distribution v52 E2E" in nested_combination_reference_edit["claim"]
    assert "[0,-8000,2000,0,0,0]" in nested_combination_reference_edit["claim"]
    assert "byte-identical direct/restart output" in nested_combination_reference_edit["claim"]
    assert "fallback 0" in nested_combination_reference_edit["claim"]
    assert "approved HIP C2" in nested_combination_reference_edit["claim"]
    assert "C6" in nested_combination_reference_edit["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_nested_linear_load_combination_deletion"
        )
        is True
    )
    nested_combination_delete = payload["capabilities"][
        "modelir_nested_linear_load_combination_deletion"
    ]
    assert nested_combination_delete["cutover_gate"] == "C5"
    assert nested_combination_delete["owner"] == "structural-workbench"
    assert "last contiguous" in nested_combination_delete["claim"]
    assert "two through 64 uniquely typed" in nested_combination_delete["claim"]
    assert "root-inclusive depth at most eight" in nested_combination_delete["claim"]
    assert "64 expanded leaf contributions" in nested_combination_delete["claim"]
    assert "direct exact-two v1" in nested_combination_delete["claim"]
    assert "explicit v3 root/expanded-term provenance" in nested_combination_delete["claim"]
    assert "distribution v48 E2E" in nested_combination_delete["claim"]
    assert "retaining and executing the child combination" in nested_combination_delete["claim"]
    assert "[0,-12000,5000,0,0,0]" in nested_combination_delete["claim"]
    assert "byte-identical direct/restart output" in nested_combination_delete["claim"]
    assert "fallback 0" in nested_combination_delete["claim"]
    assert "HIP C2" in nested_combination_delete["claim"]
    assert "C6" in nested_combination_delete["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_truss3d_authoring") is True
    truss_authoring = payload["capabilities"]["modelir_truss3d_authoring"]
    assert truss_authoring["cutover_gate"] == "C5"
    assert truss_authoring["owner"] == "structural-workbench"
    assert "v1 truss_3d section" in truss_authoring["claim"]
    assert "truss_3d/linear_truss_3d member" in truss_authoring["claim"]
    assert "typed frame-plus-truss recovery" in truss_authoring["claim"]
    assert "byte-identical restart" in truss_authoring["claim"]
    assert "fallback 0" in truss_authoring["claim"]
    assert "HIP C2" in truss_authoring["claim"]
    assert "C6" in truss_authoring["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_truss3d_editing") is True
    truss_editing = payload["capabilities"]["modelir_truss3d_editing"]
    assert truss_editing["cutover_gate"] == "C5"
    assert truss_editing["owner"] == "structural-workbench"
    assert "existing v1 truss_3d section" in truss_editing["claim"]
    assert "existing truss_3d element" in truss_editing["claim"]
    assert "distinct baseline/section/property displacement" in truss_editing["claim"]
    assert "byte-identical restart" in truss_editing["claim"]
    assert "fallback 0" in truss_editing["claim"]
    assert "HIP C2" in truss_editing["claim"]
    assert "C6" in truss_editing["claim"]
    assert (
        capabilities.capability_is_enabled(payload, "modelir_frame3d_leaf_deletion")
        is True
    )
    frame_leaf_deletion = payload["capabilities"]["modelir_frame3d_leaf_deletion"]
    assert frame_leaf_deletion["cutover_gate"] == "C5"
    assert frame_leaf_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral frame_3d/euler_bernoulli_3d member"
        in frame_leaf_deletion["claim"]
    )
    assert "last contiguous orphan endpoint node" in frame_leaf_deletion["claim"]
    assert "local rotation, offsets, releases" in frame_leaf_deletion["claim"]
    assert "frame-only typed recovery" in frame_leaf_deletion["claim"]
    assert "byte-identical restart" in frame_leaf_deletion["claim"]
    assert "fallback 0" in frame_leaf_deletion["claim"]
    assert "HIP C2" in frame_leaf_deletion["claim"]
    assert "C6" in frame_leaf_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_fixed_constraint_deletion"
        )
        is True
    )
    fixed_constraint_deletion = payload["capabilities"][
        "modelir_fixed_constraint_deletion"
    ]
    assert fixed_constraint_deletion["cutover_gate"] == "C5"
    assert fixed_constraint_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral homogeneous six-DOF zero fixed_dofs row"
        in fixed_constraint_deletion["claim"]
    )
    assert "exact active DOFs and loads" in fixed_constraint_deletion["claim"]
    assert "typed frame recovery" in fixed_constraint_deletion["claim"]
    assert "byte-identical restart" in fixed_constraint_deletion["claim"]
    assert "fallback 0" in fixed_constraint_deletion["claim"]
    assert "HIP C2" in fixed_constraint_deletion["claim"]
    assert "C6" in fixed_constraint_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(payload, "modelir_nodal_load_deletion")
        is True
    )
    nodal_load_deletion = payload["capabilities"]["modelir_nodal_load_deletion"]
    assert nodal_load_deletion["cutover_gate"] == "C5"
    assert nodal_load_deletion["owner"] == "structural-workbench"
    assert "last contiguous neutral nonzero six-component" in nodal_load_deletion["claim"]
    assert "another nonzero load" in nodal_load_deletion["claim"]
    assert "exact retained active load" in nodal_load_deletion["claim"]
    assert "typed frame recovery" in nodal_load_deletion["claim"]
    assert "byte-identical restart" in nodal_load_deletion["claim"]
    assert "fallback 0" in nodal_load_deletion["claim"]
    assert "HIP C2" in nodal_load_deletion["claim"]
    assert "C6" in nodal_load_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_load_pattern_deletion"
        )
        is True
    )
    load_pattern_deletion = payload["capabilities"][
        "modelir_linear_load_pattern_deletion"
    ]
    assert load_pattern_deletion["cutover_gate"] == "C5"
    assert load_pattern_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral zero-self-weight linear_static pattern"
        in load_pattern_deletion["claim"]
    )
    assert "load-combination and construction-stage references" in load_pattern_deletion["claim"]
    assert "exact retained active load" in load_pattern_deletion["claim"]
    assert "typed frame recovery" in load_pattern_deletion["claim"]
    assert "byte-identical restart" in load_pattern_deletion["claim"]
    assert "fallback 0" in load_pattern_deletion["claim"]
    assert "HIP C2" in load_pattern_deletion["claim"]
    assert "C6" in load_pattern_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_material_deletion"
        )
        is True
    )
    material_deletion = payload["capabilities"][
        "modelir_linear_material_deletion"
    ]
    assert material_deletion["cutover_gate"] == "C5"
    assert material_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral unreferenced parameter-set-v1 "
        "linear_elastic_isotropic material"
        in material_deletion["claim"]
    )
    assert "element material_id references" in material_deletion["claim"]
    assert (
        "section steel_material_id or concrete_material_id references"
        in material_deletion["claim"]
    )
    assert "single C ABI into C++" in material_deletion["claim"]
    assert "exact retained material and active load" in material_deletion["claim"]
    assert "fallback 0" in material_deletion["claim"]
    assert "HIP C2" in material_deletion["claim"]
    assert "C6" in material_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_frame_section_deletion"
        )
        is True
    )
    frame_section_deletion = payload["capabilities"][
        "modelir_frame_section_deletion"
    ]
    assert frame_section_deletion["cutover_gate"] == "C5"
    assert frame_section_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral unreferenced parameter-set-v1 frame_3d section"
        in frame_section_deletion["claim"]
    )
    assert "element section_id references" in frame_section_deletion["claim"]
    assert "single C ABI into C++" in frame_section_deletion["claim"]
    assert "exact retained section and active load" in frame_section_deletion["claim"]
    assert "fallback 0" in frame_section_deletion["claim"]
    assert "HIP C2" in frame_section_deletion["claim"]
    assert "C6" in frame_section_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_truss_section_deletion"
        )
        is True
    )
    truss_section_deletion = payload["capabilities"][
        "modelir_truss_section_deletion"
    ]
    assert truss_section_deletion["cutover_gate"] == "C5"
    assert truss_section_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral unreferenced parameter-set-v1 truss_3d section"
        in truss_section_deletion["claim"]
    )
    assert "another truss_3d section" in truss_section_deletion["claim"]
    assert "element section_id references" in truss_section_deletion["claim"]
    assert "single C ABI into C++" in truss_section_deletion["claim"]
    assert "exact retained truss section and active load" in truss_section_deletion["claim"]
    assert "fallback 0" in truss_section_deletion["claim"]
    assert "HIP C2" in truss_section_deletion["claim"]
    assert "C6" in truss_section_deletion["claim"]
    assert (
        capabilities.capability_is_enabled(payload, "modelir_truss3d_leaf_deletion")
        is True
    )
    truss_leaf_deletion = payload["capabilities"]["modelir_truss3d_leaf_deletion"]
    assert truss_leaf_deletion["cutover_gate"] == "C5"
    assert truss_leaf_deletion["owner"] == "structural-workbench"
    assert (
        "last contiguous neutral truss_3d/linear_truss_3d member"
        in truss_leaf_deletion["claim"]
    )
    assert "last contiguous orphan endpoint node" in truss_leaf_deletion["claim"]
    assert "frame-only typed recovery" in truss_leaf_deletion["claim"]
    assert "byte-identical restart" in truss_leaf_deletion["claim"]
    assert "fallback 0" in truss_leaf_deletion["claim"]
    assert "HIP C2" in truss_leaf_deletion["claim"]
    assert "C6" in truss_leaf_deletion["claim"]
    assert capabilities.capability_is_enabled(payload, "modelir_linear_workbench") is True
    linear_workbench = payload["capabilities"]["modelir_linear_workbench"]
    assert linear_workbench["cutover_gate"] == "C5"
    assert linear_workbench["owner"] == "structural-workbench"
    assert "model_ir_linear_cpu_v1" in linear_workbench["claim"]
    assert "real PCG checkpoint.mlpcp" in linear_workbench["claim"]
    assert "typed recovered global-DOF" in linear_workbench["claim"]
    assert "existing fixed-guided NDTHA session and receipt bytes" in linear_workbench["claim"]
    assert "deterministic single-page sparse PDF" in linear_workbench["claim"]
    assert "localized sparse PDF" in linear_workbench["claim"]
    assert "authoritative numerical C2/C3" in linear_workbench["claim"]
    assert "C6" in linear_workbench["claim"]
    linear_workbench_evidence = linear_workbench["evidence_contract"]
    assert "constrained_reaction_result" in linear_workbench_evidence["current_review_claim"]
    assert "constrained_reaction_result" not in linear_workbench_evidence["legacy_review_claim"]
    assert linear_workbench_evidence["reaction_artifact"] == "04-resume/reaction-result-ir.json"
    assert (
        linear_workbench_evidence["compatibility"]
        == "frozen_pre_reaction_review_remains_verifiable"
    )
    assert (
        capabilities.capability_is_enabled(payload, "modelir_linear_reaction_view")
        is True
    )
    reaction_view = payload["capabilities"]["modelir_linear_reaction_view"]
    assert reaction_view["cutover_gate"] == "C5"
    assert reaction_view["owner"] == "structural-workbench"
    assert "reaction-view" in reaction_view["claim"]
    assert "terminal run receipt" in reaction_view["claim"]
    assert "actual node ID" in reaction_view["claim"]
    assert "internal-minus-external reaction" in reaction_view["claim"]
    assert "en-US or ko-KR" in reaction_view["claim"]
    assert "1 through 256 rows" in reaction_view["claim"]
    assert "byte-identical direct/restart views" in reaction_view["claim"]
    assert "frozen pre-reaction missing-artifact rejection" in reaction_view["claim"]
    assert "installed static/shared CPU distribution v85" in reaction_view["claim"]
    assert "local rootfs diagnostic v8" in reaction_view["claim"]
    assert "public/customer distribution publication" in reaction_view["claim"]
    assert "HIP C2" in reaction_view["claim"]
    assert "C6" in reaction_view["claim"]
    assert (
        capabilities.capability_is_enabled(payload, "modelir_linear_reaction_audit")
        is True
    )
    reaction_audit = payload["capabilities"]["modelir_linear_reaction_audit"]
    assert reaction_audit["cutover_gate"] == "C5"
    assert reaction_audit["owner"] == "structural-workbench"
    assert "reaction-audit" in reaction_audit["claim"]
    assert "complete generalized external-load vector" in reaction_audit["claim"]
    assert "model-global origin" in reaction_audit["claim"]
    assert "256 times IEEE754 binary64 epsilon" in reaction_audit["claim"]
    assert "within_numeric_tolerance" in reaction_audit["claim"]
    assert "installed static/shared CPU distribution v86" in reaction_audit["claim"]
    assert "local rootfs diagnostic v9" in reaction_audit["claim"]
    assert "public/customer distribution publication" in reaction_audit["claim"]
    assert "HIP C2" in reaction_audit["claim"]
    assert "C6" in reaction_audit["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_nodal_displacement_view"
        )
        is True
    )
    displacement_view = payload["capabilities"][
        "modelir_linear_nodal_displacement_view"
    ]
    assert displacement_view["cutover_gate"] == "C5"
    assert displacement_view["owner"] == "structural-workbench"
    assert "nodal-displacement-view" in displacement_view["claim"]
    assert "terminal run receipt" in displacement_view["claim"]
    assert "actual node ID" in displacement_view["claim"]
    assert "metre/radian FP64 components" in displacement_view["claim"]
    assert "en-US or ko-KR" in displacement_view["claim"]
    assert "1 through 256 nodes" in displacement_view["claim"]
    assert "byte-identical strict-ModelIR and normalized-MGT direct/restart views" in displacement_view["claim"]
    assert "frozen pre-reaction compatibility" in displacement_view["claim"]
    assert "installed static/shared CPU distribution v87" in displacement_view["claim"]
    assert "local rootfs diagnostic v10" in displacement_view["claim"]
    assert "five distinct strict-ModelIR/normalized-MGT locale/window identities" in displacement_view["claim"]
    assert "public/customer distribution publication" in displacement_view["claim"]
    assert "HIP C2" in displacement_view["claim"]
    assert "C6" in displacement_view["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_element_recovery_view"
        )
        is True
    )
    element_recovery_view = payload["capabilities"][
        "modelir_linear_element_recovery_view"
    ]
    assert element_recovery_view["cutover_gate"] == "C5"
    assert element_recovery_view["owner"] == "structural-workbench"
    assert "element-recovery-view" in element_recovery_view["claim"]
    assert "terminal run receipt" in element_recovery_view["claim"]
    assert "native C++ semantic boundary" in element_recovery_view["claim"]
    assert "immutable element identifiers" in element_recovery_view["claim"]
    assert "frame3d local end forces" in element_recovery_view["claim"]
    assert "truss3d axial strain, stress, and force" in element_recovery_view["claim"]
    assert "en-US or ko-KR" in element_recovery_view["claim"]
    assert "1 through 256 elements" in element_recovery_view["claim"]
    assert (
        "byte-identical strict-ModelIR and normalized-MGT direct/restart views"
        in element_recovery_view["claim"]
    )
    assert "installed CPU static/shared distribution v89" in element_recovery_view["claim"]
    assert "local rootfs diagnostic v12" in element_recovery_view["claim"]
    assert "four distinct strict-ModelIR/normalized-MGT locale identities" in element_recovery_view["claim"]
    assert "Truss3D row formatting remains source-tested" in element_recovery_view["claim"]
    assert "general stress contour" in element_recovery_view["claim"]
    assert "public/customer distribution publication" in element_recovery_view["claim"]
    assert "HIP C2" in element_recovery_view["claim"]
    assert "C6" in element_recovery_view["claim"]
    assert (
        capabilities.capability_is_enabled(
            payload, "modelir_linear_deformed_shape_view"
        )
        is True
    )
    deformed_view = payload["capabilities"]["modelir_linear_deformed_shape_view"]
    assert deformed_view["cutover_gate"] == "C5"
    assert deformed_view["owner"] == "structural-workbench"
    assert "result-deformed-view" in deformed_view["claim"]
    assert "single static state" in deformed_view["claim"]
    assert "native C++ semantic boundary" in deformed_view["claim"]
    assert "UX/UY/UZ metre translations" in deformed_view["claim"]
    assert "reports but does not apply RX/RY/RZ radians" in deformed_view["claim"]
    assert "at most 512 original/deformed nodes plus 1024 two-node centerlines" in deformed_view["claim"]
    assert "fixed 73x25 isometric/xy/xz/yz" in deformed_view["claim"]
    assert "byte-identical strict-ModelIR and normalized-MGT direct/restart views" in deformed_view["claim"]
    assert "frozen pre-reaction compatibility" in deformed_view["claim"]
    assert "installed static/shared CPU distribution v88" in deformed_view["claim"]
    assert "local rootfs diagnostic v11" in deformed_view["claim"]
    assert "five distinct strict-ModelIR/normalized-MGT locale/projection identities" in deformed_view["claim"]
    assert "interactive 3D" in deformed_view["claim"]
    assert "public/customer distribution publication" in deformed_view["claim"]
    assert "HIP C2" in deformed_view["claim"]
    assert "C6" in deformed_view["claim"]


def test_native_evidence_bundle_capability_is_bounded_c5() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_evidence_bundle") is True
    evidence = payload["capabilities"]["native_evidence_bundle"]
    assert evidence["cutover_gate"] == "C5"
    assert evidence["owner"] == "structural-evidence"
    assert "former Node source list" in evidence["claim"]
    assert "duplicate keys, mixed commits" in evidence["claim"]
    assert "atomically publishes" in evidence["claim"]
    assert "without inferring readiness or approval" in evidence["claim"]
    assert "Python/Node lookup 0" in evidence["claim"]
    assert "C6 remain open" in evidence["claim"]


def test_native_benchmark_catalog_capability_is_bounded_c5() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_benchmark_catalog") is True
    catalog = payload["capabilities"]["native_benchmark_catalog"]
    assert catalog["cutover_gate"] == "C5"
    assert catalog["owner"] == "structural-catalog"
    assert "former Node directory and first-target rules" in catalog["claim"]
    assert "21 tracked open-data reports and five PEER" in catalog["claim"]
    assert "reproduces all 26 prior case projections exactly" in catalog["claim"]
    assert "network and command execution counts 0" in catalog["claim"]
    assert "Python/Node lookup 0" in catalog["claim"]
    assert "C6 remain open" in catalog["claim"]


def test_native_frontend_contract_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_contract") is True
    frontend = payload["capabilities"]["native_frontend_contract"]
    assert frontend["cutover_gate"] == "C0"
    assert frontend["owner"] == "structural-frontend-contract"
    assert "former Node static package, build-smoke wrapper, built Vite delivery" in frontend["claim"]
    assert "offline prototype DOM shim" in frontend["claim"]
    assert "source Viewer HTTP server" in frontend["claim"]
    assert "source Viewer and Workbench prototype browser-smoke wrappers" in frontend["claim"]
    assert "direct Viewer performance verification entrypoint" in frontend["claim"]
    assert (
        "prototype-browser-smoke/workbench-v2-browser-smoke/browser-smoke/"
        "viewer-performance-probe/viewer-report-pdf-smoke" in frontend["claim"]
    )
    assert "bounded non-symlink required-file and emitted-asset inventories" in frontend["claim"]
    assert "exact neutral-JSON-to-JavaScript runtime projection" in frontend["claim"]
    assert "confine Viewer artifact paths to the declared repo" in frontend["claim"]
    assert "locally present artifact-count parity" in frontend["claim"]
    assert "project all six prototype states without positive demo status" in frontend["claim"]
    assert "reject innerHTML/eval source markers" in frontend["claim"]
    assert "binds only fixed IPv4 loopback" in frontend["claim"]
    assert "traversal, dotfile and symlink rejection" in frontend["claim"]
    assert "server dry-run binds 0 listeners" in frontend["claim"]
    assert "sandbox denies loopback bind with EPERM" in frontend["claim"]
    assert "hosted/clean-machine live-listener evidence remains open" in frontend["claim"]
    assert "Rust directly owns the frozen stop-on-failure npm ci and npm run build" in frontend["claim"]
    assert "dry-run spawns 0 processes" in frontend["claim"]
    assert "direct child exits" in frontend["claim"]
    assert "registry/cache access uninstrumented" in frontend["claim"]
    assert "all three browser-smoke dry-runs bind 0 listeners and spawn 0 processes" in frontend["claim"]
    assert "one direct Node child running the pinned Playwright CLI" in frontend["claim"]
    assert "prototype server is scoped to prototype/structural-workbench" in frontend["claim"]
    assert "Workbench v2 server is scoped to the verified dist tree" in frontend["claim"]
    assert "hashes the JSON loader and six specifications" in frontend["claim"]
    assert "fixed VITE_BASE_PATH=/ npm build" in frontend["claim"]
    assert "replaces inherited NODE_OPTIONS with the exact loader value" in frontend["claim"]
    assert "both direct child exits are zero" in frontend["claim"]
    assert "Viewer PDF command hashes the retained exporter" in frontend["claim"]
    assert "temporary/explicit-output cleanup" in frontend["claim"]
    assert "five HTML markers" in frontend["claim"]
    assert "three pdftotext markers" in frontend["claim"]
    assert "Viewer performance command hashes four frozen probe inputs" in frontend["claim"]
    assert "strictly decodes the bounded artifact" in frontend["claim"]
    assert "source-row identities, loopback URL, viewport, browser errors" in frontend["claim"]
    assert "canvas framing, ready-time and RAF budgets" in frontend["claim"]
    assert "dry-run creates no output and spawns 0 processes" in frontend["claim"]
    assert "browser page requests uninstrumented" in frontend["claim"]
    assert "delivery consumes an already-built tree" in frontend["claim"]
    assert "command and network execution counts 0" in frontend["claim"]
    assert "Node, Playwright, Chromium, the static Viewer runtime" in frontend["claim"]
    assert "retained Viewer PDF exporter" in frontend["claim"]
    assert "retained Viewer performance probe" in frontend["claim"]
    assert "runtime DOM/input/export/accessibility evidence" in frontend["claim"]
    assert "authorize legacy deletion" in frontend["claim"]
    assert "close C5/C6" in frontend["claim"]


def test_native_frontend_build_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_build") is True
    frontend = payload["capabilities"]["native_frontend_build"]
    assert frontend["cutover_gate"] == "C0"
    assert frontend["owner"] == "structural-frontend-contract"
    assert "package build" in frontend["claim"]
    assert "frontend-build" in frontend["claim"]
    assert "bounded complete inventory" in frontend["claim"]
    assert "TypeScript and Vite CLI entrypoint bytes" in frontend["claim"]
    assert "removes inherited NODE_OPTIONS" in frontend["claim"]
    assert "two direct Node children" in frontend["claim"]
    assert "dry-run requires no node_modules" in frontend["claim"]
    assert "build-time network behavior remain outside" in frontend["claim"]
    assert "C5, or C6" in frontend["claim"]


def test_native_frontend_dev_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_dev") is True
    dev = payload["capabilities"]["native_frontend_dev"]
    assert dev["cutover_gate"] == "C0"
    assert dev["owner"] == "structural-frontend-contract"
    assert "package dev" in dev["claim"]
    assert "frontend-dev" in dev["claim"]
    assert "launch-time frontend contract" in dev["claim"]
    assert "installed Vite CLI entrypoint" in dev["claim"]
    assert "removes inherited NODE_OPTIONS" in dev["claim"]
    assert "IPv4 loopback and strict-port" in dev["claim"]
    assert "source mutation remains deliberately allowed for HMR" in dev["claim"]
    assert "listener readiness" in dev["claim"]
    assert "C5 and C6 remain open" in dev["claim"]


def test_native_frontend_install_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_install") is True
    install = payload["capabilities"]["native_frontend_install"]
    assert install["cutover_gate"] == "C0"
    assert install["owner"] == "structural-frontend-contract"
    assert "all five hosted frontend/browser workflows invoke" in install["claim"]
    assert "instead of direct npm ci or an npm package-script launcher" in install["claim"]
    assert "package install:dependencies remains only a local launcher convenience" in install["claim"]
    assert "removes inherited NODE_OPTIONS" in install["claim"]
    assert "one exact npm ci direct child" in install["claim"]
    assert "direct Rust dry-run requires no node_modules, network or filesystem mutation" in install["claim"]
    assert "resolves neither npm nor Node and spawns no child" in install["claim"]
    assert "registry/cache access, lifecycle scripts" in install["claim"]
    assert "extracted package bytes, node_modules contents and rollback" in install["claim"]
    assert "C5 and C6 remain open" in install["claim"]


def test_native_frontend_audit_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_audit") is True
    audit = payload["capabilities"]["native_frontend_audit"]
    assert audit["cutover_gate"] == "C0"
    assert audit["owner"] == "structural-frontend-contract"
    assert "frontend-web invokes structural-frontend-contract frontend-audit directly" in audit["claim"]
    assert "one exact npm audit --audit-level high direct child" in audit["claim"]
    assert "removes inherited NODE_OPTIONS" in audit["claim"]
    assert "non-blocking numeric-exit policy" in audit["claim"]
    assert "advisory_or_tool_failure" in audit["claim"]
    assert "does not parse or independently classify" in audit["claim"]
    assert "dry-run resolves neither npm nor Node and spawns no child" in audit["claim"]
    assert "finding counts and identities, dependency/license clearance" in audit["claim"]
    assert "C5 and C6 remain open" in audit["claim"]


def test_native_frontend_audit_report_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(payload, "native_frontend_audit_report")
        is True
    )
    audit = payload["capabilities"]["native_frontend_audit_report"]
    assert audit["cutover_gate"] == "C0"
    assert audit["owner"] == "structural-frontend-contract"
    assert "launches one direct Cargo" in audit["claim"]
    assert "direct Python npm, npx and Node entrypoints 0" in audit["claim"]
    assert "one exact npm audit --json child" in audit["claim"]
    assert "duplicate-key, non-finite, oversized" in audit["claim"]
    assert "frontend-dependency-audit-report.v1" in audit["claim"]
    assert "staging, backup rename and rollback" in audit["claim"]
    assert "retains only CLI/output compatibility" in audit["claim"]
    assert "npm remains the advisory oracle" in audit["claim"]
    assert "dependency/license clearance" in audit["claim"]
    assert "C5 and C6 remain open" in audit["claim"]


def test_native_quality_gate_frontend_entrypoints_are_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(
            payload, "native_quality_gate_frontend_entrypoints"
        )
        is True
    )
    gate = payload["capabilities"]["native_quality_gate_frontend_entrypoints"]
    assert gate["cutover_gate"] == "C0"
    assert gate["owner"] == "structural-frontend-contract"
    assert "retains overall Python sequencing" in gate["claim"]
    assert "direct Cargo structural-frontend-contract commands" in gate["claim"]
    assert "npm and npm package-script entrypoints 0" in gate["claim"]
    assert "publishes the same canonical advisory_or_tool_failure receipt" in gate["claim"]
    assert "fails the Rust command on numeric nonzero" in gate["claim"]
    assert "frontend-web retains its separate non-blocking audit policy" in gate["claim"]
    assert "Python sequencing" in gate["claim"]
    assert "C5 and C6 remain open" in gate["claim"]


def test_native_phase5_task_browser_smoke_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(
            payload, "native_phase5_task_browser_smoke"
        )
        is True
    )
    smoke = payload["capabilities"]["native_phase5_task_browser_smoke"]
    assert smoke["cutover_gate"] == "C0"
    assert smoke["owner"] == "structural-frontend-contract"
    assert "one direct Cargo structural-frontend-contract" in smoke["claim"]
    assert "direct npm, npx, Node, preview-server and socket-readiness entrypoints 0" in smoke[
        "claim"
    ]
    assert "fixed five-step workflow vocabulary" in smoke["claim"]
    assert "fixed 127.0.0.1:4173 SPA route" in smoke["claim"]
    assert "all child exits are zero and request errors are 0" in smoke["claim"]
    assert "dry-run requires no dist, runtime, listener, browser or process" in smoke["claim"]
    assert "Python strictly validates that receipt" in smoke["claim"]
    assert "human usability observation, hosted live evidence" in smoke["claim"]
    assert "C5 and C6 remain open" in smoke["claim"]


def test_native_frontend_ci_entrypoints_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_ci_entrypoints") is True
    entrypoints = payload["capabilities"]["native_frontend_ci_entrypoints"]
    assert entrypoints["cutover_gate"] == "C0"
    assert entrypoints["owner"] == "structural-frontend-contract"
    assert "frontend-web, nightly-full-quality" in entrypoints["claim"]
    assert "direct Cargo structural-frontend-contract commands" in entrypoints["claim"]
    assert "native benchmark-catalog and evidence-bundle Bash wrappers" in entrypoints["claim"]
    assert "npm run entrypoints 0" in entrypoints["claim"]
    assert "npx entrypoints 0" in entrypoints["claim"]
    assert "direct Node entrypoints 0" in entrypoints["claim"]
    assert "direct npm audit entrypoints 0" in entrypoints["claim"]
    assert "setup-node, npm, Node, TypeScript, Vite, Playwright" in entrypoints["claim"]
    assert "AI worker contract workflow is intentionally outside" in entrypoints["claim"]
    assert "C5 and C6 remain open" in entrypoints["claim"]


def test_native_frontend_preview_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_frontend_preview") is True
    preview = payload["capabilities"]["native_frontend_preview"]
    assert preview["cutover_gate"] == "C0"
    assert preview["owner"] == "structural-frontend-contract"
    assert "package preview" in preview["claim"]
    assert "frontend-preview" in preview["claim"]
    assert "already-built delivery receipt" in preview["claim"]
    assert "one fixed IPv4 loopback listener" in preview["claim"]
    assert "rejects traversal, dotfiles and symlinks" in preview["claim"]
    assert "spawns zero child processes" in preview["claim"]
    assert "requires no Node, Vite, browser or Python" in preview["claim"]
    assert "C5 and C6 remain open" in preview["claim"]


def test_native_playwright_install_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_playwright_install") is True
    install = payload["capabilities"]["native_playwright_install"]
    assert install["cutover_gate"] == "C0"
    assert install["owner"] == "structural-frontend-contract"
    assert "all five hosted browser workflows invoke" in install["claim"]
    assert "instead of npx or an npm package-script launcher" in install["claim"]
    assert "package install:browser-runtime remains a local convenience" in install["claim"]
    assert "playwright-install" in install["claim"]
    assert "installed Playwright CLI entrypoint" in install["claim"]
    assert "removes inherited NODE_OPTIONS" in install["claim"]
    assert "one exact node CLI.js install --with-deps chromium child" in install["claim"]
    assert "dry-run requires no node_modules, network, host mutation" in install["claim"]
    assert "downloads, caches, elevation and host-package mutation" in install["claim"]
    assert "downloaded byte identities, transitive processes, rollback" in install["claim"]
    assert "C5 and C6 remain outside" in install["claim"]


def test_native_viewer_visual_regression_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(
            payload, "native_viewer_visual_regression"
        )
        is True
    )
    visual = payload["capabilities"]["native_viewer_visual_regression"]
    assert visual["cutover_gate"] == "C0"
    assert visual["owner"] == "structural-frontend-contract"
    assert "viewer-visual-regression" in visual["claim"]
    assert "tracked baseline plus four frozen source inputs" in visual["claim"]
    assert "all 11 ordered workflow cases" in visual["claim"]
    assert "recomputed baseline deltas" in visual["claim"]
    assert "dry-run creates no output, listener or process" in visual["claim"]
    assert "retained Node probe still owns" in visual["claim"]
    assert "explicit baseline refresh remains a direct operator Node command" in visual["claim"]
    assert "pixel-perfect rendering" in visual["claim"]
    assert "C6 remain open" in visual["claim"]


def test_native_viewer_report_pdf_export_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(payload, "native_viewer_report_pdf_export")
        is True
    )
    export = payload["capabilities"]["native_viewer_report_pdf_export"]
    assert export["cutover_gate"] == "C0"
    assert export["owner"] == "structural-frontend-contract"
    assert "export:viewer-report-pdf" in export["claim"]
    assert "viewer-report-pdf-export" in export["claim"]
    assert "rejects symlinks and PDF/HTML aliasing" in export["claim"]
    assert "destination mutation during generation" in export["claim"]
    assert "backup/rename publication with rollback" in export["claim"]
    assert "dry-run creates no output or process" in export["claim"]
    assert "retained Node exporter" in export["claim"]
    assert "C5 and C6 remain open" in export["claim"]


def test_native_viewer_readme_capture_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(payload, "native_viewer_readme_capture")
        is True
    )
    capture = payload["capabilities"]["native_viewer_readme_capture"]
    assert capture["cutover_gate"] == "C0"
    assert capture["owner"] == "structural-frontend-contract"
    assert "capture:readme-viewer-image" in capture["claim"]
    assert "viewer-readme-capture" in capture["claim"]
    assert "replaces inherited camera environment variables" in capture["claim"]
    assert "CRC-correct PNG chunks" in capture["claim"]
    assert "exact 1600x900 IHDR" in capture["claim"]
    assert "shared staging/backup/rename rollback contract" in capture["claim"]
    assert "dry-run creates no output, listener or process" in capture["claim"]
    assert "retained capture script" in capture["claim"]
    assert "C5 and C6 remain open" in capture["claim"]


def test_native_viewer_js_syntax_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_viewer_js_syntax") is True
    syntax = payload["capabilities"]["native_viewer_js_syntax"]
    assert syntax["cutover_gate"] == "C0"
    assert syntax["owner"] == "structural-frontend-contract"
    assert "runtime-input-viewer CI" in syntax["claim"]
    assert "verify:viewer-js-syntax" in syntax["claim"]
    assert "exact ordered SHA-256 identities" in syntax["claim"]
    assert "ten Viewer JavaScript sources" in syntax["claim"]
    assert "retained Node --check" in syntax["claim"]
    assert "dry-run spawns no process" in syntax["claim"]
    assert "does not execute Viewer behavior" in syntax["claim"]
    assert "authorize C6 removal" in syntax["claim"]


def test_native_viewer_sample_workflow_capability_is_bounded_c0() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert (
        capabilities.capability_is_enabled(payload, "native_viewer_sample_workflow")
        is True
    )
    workflow = payload["capabilities"]["native_viewer_sample_workflow"]
    assert workflow["cutover_gate"] == "C0"
    assert workflow["owner"] == "structural-frontend-contract"
    assert "viewer-sample-workflow" in workflow["claim"]
    assert "exact four ordered MIDAS33/real-drawing rehearsal steps" in workflow["claim"]
    assert "browser warning/error aggregates" in workflow["claim"]
    assert "no outer npm package-script launcher" in workflow["claim"]
    assert "Python retains readiness-report assembly" in workflow["claim"]
    assert "dry-run creates no output, listener or process" in workflow["claim"]
    assert "retained Node probe still owns" in workflow["claim"]
    assert "not human new-user observation" in workflow["claim"]
    assert "C6 remain open" in workflow["claim"]


def test_native_distribution_capability_is_bounded_c5():
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_distribution") is True
    distribution = payload["capabilities"]["native_distribution"]
    assert distribution["cutover_gate"] == "C5"
    assert distribution["owner"] == "structural-distribution"
    assert "static/shared" in distribution["claim"]
    assert "install/update/rollback" in distribution["claim"]
    assert "Python/Node lookup 0" in distribution["claim"]
    assert "append-only v14 receipt" in distribution["claim"]
    assert "append-only v16" in distribution["claim"]
    assert "append-only v17" in distribution["claim"]
    assert "append-only v18" in distribution["claim"]
    assert "append-only v19" in distribution["claim"]
    assert "append-only v20" in distribution["claim"]
    assert "append-only v30" in distribution["claim"]
    assert "append-only v31" in distribution["claim"]
    assert "append-only v32" in distribution["claim"]
    assert "append-only v33" in distribution["claim"]
    assert "append-only v34" in distribution["claim"]
    assert "append-only v35" in distribution["claim"]
    assert "append-only v36" in distribution["claim"]
    assert "append-only v37" in distribution["claim"]
    assert "append-only v38" in distribution["claim"]
    assert "append-only v39" in distribution["claim"]
    assert "append-only v40" in distribution["claim"]
    assert "append-only v41" in distribution["claim"]
    assert "append-only v42" in distribution["claim"]
    assert "append-only v43" in distribution["claim"]
    assert "append-only v44" in distribution["claim"]
    assert "append-only v45" in distribution["claim"]
    assert "append-only v46" in distribution["claim"]
    assert "append-only v47" in distribution["claim"]
    assert "append-only v48" in distribution["claim"]
    assert "append-only v49" in distribution["claim"]
    assert "append-only v50" in distribution["claim"]
    assert "exact normalized-MGT-to-ModelIR-linear" in distribution["claim"]
    assert "existing-constraint prescribed-value edits" in distribution["claim"]
    assert "existing-v1-linear-elastic-material" in distribution["claim"]
    assert "existing-v1-frame3d-section" in distribution["claim"]
    assert "existing-frame3d-element local-axis rotation" in distribution["claim"]
    assert "NDTHA response-history channels" in distribution["claim"]
    assert "exact-profile deformed-shape projections" in distribution["claim"]
    assert "installed Korean topology, response and deformed views" in distribution["claim"]
    assert "frozen v1 through v19 receipts" in distribution["claim"]
    assert "frozen v1 through v49 receipts" in distribution["claim"]
    assert "last-neutral-truss-leaf deletion" in distribution["claim"]
    assert "last-neutral-frame-leaf deletion" in distribution["claim"]
    assert "last-neutral-frame-section deletion" in distribution["claim"]
    assert "last-neutral-truss-section deletion" in distribution["claim"]
    assert "standalone neutral-node creation" in distribution["claim"]
    assert "last-neutral orphan-node deletion" in distribution["claim"]
    assert "two-pattern linear-load-combination creation" in distribution["claim"]
    assert "last-neutral linear-load-combination deletion" in distribution["claim"]
    assert "bounded two-pattern linear-load-combination assembly" in distribution["claim"]
    assert "bounded two-through-64 direct linear-load-combination authoring" in distribution["claim"]
    assert "bounded acyclic nested linear-load-combination authoring" in distribution["claim"]
    assert "depth-eight/64-leaf flattening" in distribution["claim"]
    assert "two-through-64 direct linear-load-combination deletion" in distribution["claim"]
    assert "bounded nested linear-load-combination deletion" in distribution["claim"]
    assert "retained child-combination" in distribution["claim"]
    assert "bounded direct linear-load-combination single-factor editing" in distribution["claim"]
    assert "[25000,-13500,5000,0,0,0]" in distribution["claim"]
    assert "bounded nested linear-load-combination typed-root-factor editing" in distribution["claim"]
    assert "[25000,-9000,3750,0,0,0]" in distribution["claim"]
    assert "exact-two v1 field preservation" in distribution["claim"]
    assert "v2 deletion provenance beyond two terms" in distribution["claim"]
    assert "exact unchanged active DOFs/load" in distribution["claim"]
    assert "orientation/offset/release metadata" in distribution["claim"]
    assert "last-neutral-fixed-constraint deletion" in distribution["claim"]
    assert "last-neutral-nodal-load deletion" in distribution["claim"]
    assert "last-neutral-linear-load-pattern deletion" in distribution["claim"]
    assert "last-neutral-linear-material deletion" in distribution["claim"]
    assert "distinct baseline/section/property displacement" in distribution["claim"]
    assert "one-real-iteration restart parity" in distribution["claim"]
    assert "structural-catalog" in distribution["claim"]
    assert "structural-evidence" in distribution["claim"]
    assert "explicit non-promoting review" in distribution["claim"]
    assert "append-only v84 binds the exact constrained-reaction ResultIR" in distribution["claim"]
    assert "append-only v85 binds deterministic installed en-US" in distribution["claim"]
    assert "append-only v86 binds deterministic installed algebraic reaction audits" in distribution["claim"]
    assert "append-only v87 binds deterministic installed strict-ModelIR" in distribution["claim"]
    assert "append-only v88 binds deterministic installed strict-ModelIR" in distribution["claim"]
    assert "append-only v89 binds deterministic installed strict-ModelIR" in distribution["claim"]
    assert "Frame3D element-local end-force views" in distribution["claim"]
    assert "linear deformed-centerline views" in distribution["claim"]
    assert "frozen v1 through v88 receipts" in distribution["claim"]
    assert "rejects unresolved libamdhip64 dependencies" in distribution["claim"]
    assert "no authoritative ROCm distribution receipt" in distribution["claim"]
    assert "C6 remain open" in distribution["claim"]
    distribution_evidence = distribution["evidence_contract"]
    assert (
        distribution_evidence["latest_installed_receipt_schema"]
        == "structural-native-distribution-e2e.v89"
    )
    assert distribution_evidence["frozen_installed_receipts"] == "v1-v88"
    assert distribution_evidence["reaction_hash_fields"] == [
        "model_ir_linear_reaction_result_ir_sha256",
        "mgt_model_ir_linear_reaction_result_ir_sha256",
    ]
    assert distribution_evidence["reaction_view_hash_fields"] == [
        "model_ir_linear_reaction_view_en_us_sha256",
        "model_ir_linear_reaction_view_ko_kr_sha256",
        "model_ir_linear_reaction_view_window_sha256",
        "mgt_model_ir_linear_reaction_view_en_us_sha256",
        "mgt_model_ir_linear_reaction_view_ko_kr_sha256",
    ]
    assert distribution_evidence["reaction_audit_hash_fields"] == [
        "model_ir_linear_reaction_audit_en_us_sha256",
        "model_ir_linear_reaction_audit_ko_kr_sha256",
        "mgt_model_ir_linear_reaction_audit_en_us_sha256",
        "mgt_model_ir_linear_reaction_audit_ko_kr_sha256",
    ]
    assert distribution_evidence["nodal_displacement_view_hash_fields"] == [
        "model_ir_linear_nodal_displacement_view_en_us_sha256",
        "model_ir_linear_nodal_displacement_view_ko_kr_sha256",
        "model_ir_linear_nodal_displacement_view_window_sha256",
        "mgt_model_ir_linear_nodal_displacement_view_en_us_sha256",
        "mgt_model_ir_linear_nodal_displacement_view_ko_kr_sha256",
    ]
    assert distribution_evidence["linear_deformed_view_hash_fields"] == [
        "model_ir_linear_deformed_view_en_us_sha256",
        "model_ir_linear_deformed_view_ko_kr_sha256",
        "model_ir_linear_deformed_view_projection_sha256",
        "mgt_model_ir_linear_deformed_view_en_us_sha256",
        "mgt_model_ir_linear_deformed_view_ko_kr_sha256",
    ]
    assert distribution_evidence["linear_element_recovery_view_hash_fields"] == [
        "model_ir_linear_element_recovery_view_en_us_sha256",
        "model_ir_linear_element_recovery_view_ko_kr_sha256",
        "mgt_model_ir_linear_element_recovery_view_en_us_sha256",
        "mgt_model_ir_linear_element_recovery_view_ko_kr_sha256",
    ]
    assert distribution_evidence["authority"] == "hosted_cpu_c5"
    assert capabilities.capability_is_enabled(payload, "hip_backend") is False


def test_native_deployment_capability_is_bounded_c5() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_deployment") is True
    deployment = payload["capabilities"]["native_deployment"]
    assert deployment["cutover_gate"] == "C5"
    assert deployment["owner"] == "structural-workbench"
    assert "cpu-only static native distribution" in deployment["claim"]
    assert "no network namespace, listener, port, secret, Python, Node or React runtime" in deployment["claim"]
    assert "explicit non-promoting review" in deployment["claim"]
    assert "operator artifact self-hashes" in deployment["claim"]
    assert "catalog/evidence projections" in deployment["claim"]
    assert "English/Korean ModelIR topology" in deployment["claim"]
    assert "English/Korean NDTHA response-history" in deployment["claim"]
    assert "exact-profile deformed-shape views" in deployment["claim"]
    assert "distribution v50 E2E" in deployment["claim"]
    assert "standalone neutral-node creation" in deployment["claim"]
    assert "last-neutral orphan-node deletion" in deployment["claim"]
    assert "two-pattern linear-load-combination creation" in deployment["claim"]
    assert "last-neutral exact-two linear-load-combination deletion" in deployment["claim"]
    assert "bounded two-pattern linear-load-combination CPU execution" in deployment["claim"]
    assert "bounded two-through-64 direct linear-load-combination authoring and CPU execution" in deployment["claim"]
    assert "bounded direct linear-load-combination single-factor editing" in deployment["claim"]
    assert "[25000,-13500,5000,0,0,0]" in deployment["claim"]
    assert "bounded nested linear-load-combination typed-root-factor editing" in deployment["claim"]
    assert "[25000,-9000,3750,0,0,0]" in deployment["claim"]
    assert "bounded two-through-64 direct linear-load-combination deletion" in deployment["claim"]
    assert "bounded acyclic nested linear-load-combination authoring and CPU execution" in deployment["claim"]
    assert "bounded acyclic nested linear-load-combination deletion" in deployment["claim"]
    assert "retained child-combination execution" in deployment["claim"]
    assert "depth-eight/64-leaf flattening" in deployment["claim"]
    assert "frame/truss-section" in deployment["claim"]
    assert "compatible frame/truss-property" in deployment["claim"]
    assert "truss-section area replacement" in deployment["claim"]
    assert "last-neutral frame-section deletion" in deployment["claim"]
    assert "last-neutral truss-section deletion" in deployment["claim"]
    assert "compatible truss material/section reassignment" in deployment["claim"]
    assert "last-neutral-truss-leaf deletion" in deployment["claim"]
    assert "last-neutral-frame-leaf deletion" in deployment["claim"]
    assert "removed-frame-field binding" in deployment["claim"]
    assert "last-neutral fixed-constraint deletion" in deployment["claim"]
    assert "last-neutral nodal-load deletion" in deployment["claim"]
    assert "last-neutral linear-load-pattern deletion" in deployment["claim"]
    assert "last-neutral linear-material deletion" in deployment["claim"]
    assert "normalized-MGT-linear" in deployment["claim"]
    assert "v12 self-hashed local_rootfs_diagnostic_c5 receipt" in deployment["claim"]
    assert "strict-ModelIR and normalized-MGT constrained-reaction views" in deployment["claim"]
    assert "algebraic reaction audits" in deployment["claim"]
    assert "bounded nodal-displacement views" in deployment["claim"]
    assert "bounded linear deformed views" in deployment["claim"]
    assert "Frame3D element-local end-force views" in deployment["claim"]
    assert "Truss3D installed execution explicitly open" in deployment["claim"]
    assert "visible nonzero normalized-MGT FP64 roundoff" in deployment["claim"]
    assert "frozen v1 through v11 rootfs receipts" in deployment["claim"]
    deployment_evidence = deployment["evidence_contract"]
    assert (
        deployment_evidence["latest_rootfs_receipt_schema"]
        == "structural-native-rootfs-isolation-e2e.v12"
    )
    assert deployment_evidence["frozen_rootfs_receipts"] == "v1-v11"
    assert (
        deployment_evidence["required_installed_receipt_schema"]
        == "structural-native-distribution-e2e.v89"
    )
    assert deployment_evidence["authority"] == "local_rootfs_diagnostic_c5"
    assert deployment_evidence["customer_image_authority"] is False
    assert "outside .github/workflows" in deployment["claim"]
    assert "final C6 remain open" in deployment["claim"]


def test_reaction_evidence_contract_drift_fails_closed() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    payload["capabilities"]["native_distribution"]["evidence_contract"][
        "latest_installed_receipt_schema"
    ] = "structural-native-distribution-e2e.v83"

    assert (
        "native_capability_evidence_contract_invalid:native_distribution"
        in capabilities.validate_capabilities(payload)
    )


def test_native_automation_cutover_is_bounded_c5() -> None:
    payload = capabilities.load_capabilities(ROOT / "native/capabilities.json")
    assert capabilities.capability_is_enabled(payload, "native_automation_cutover") is True
    automation = payload["capabilities"]["native_automation_cutover"]
    assert automation["cutover_gate"] == "C5"
    assert automation["owner"] == "structural-distribution"
    assert "contents:write and branch-push authority 0" in automation["claim"]
    assert "rollback-only" in automation["claim"]
    assert "final C6 remain open" in automation["claim"]


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
