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
    assert "nonzero prescribed constraints" in assembly["claim"]
    assert "shell/nonlinear ModelIR graphs" in assembly["claim"]
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
    assert "provenance-bound existing-entity editors" in workbench["claim"]
    assert "v1 frame and truss sections" in workbench["claim"]
    assert "compatible frame and truss element property references" in workbench["claim"]
    assert "model-edit-truss-section" in workbench["claim"]
    assert "model-edit-truss-element-properties" in workbench["claim"]
    assert "truss3d section/member" in workbench["claim"]
    assert "model-delete-frame3d-leaf-member" in workbench["claim"]
    assert "model-delete-truss3d-leaf-member" in workbench["claim"]
    assert "model-delete-fixed-constraint" in workbench["claim"]
    assert "English/Korean bounded self-hashed NDTHA response-history view" in workbench["claim"]
    assert "English/Korean exact-profile deformed-shape view" in workbench["claim"]
    assert "neither surface is WCAG, PDF/UA" in workbench["claim"]
    assert "React/TypeScript removal" in workbench["claim"]
    assert "HIP C2" in workbench["claim"]
    assert "C6" in workbench["claim"]
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
    assert "exact normalized-MGT-to-ModelIR-linear" in distribution["claim"]
    assert "existing-constraint prescribed-value edits" in distribution["claim"]
    assert "existing-v1-linear-elastic-material" in distribution["claim"]
    assert "existing-v1-frame3d-section" in distribution["claim"]
    assert "existing-frame3d-element local-axis rotation" in distribution["claim"]
    assert "NDTHA response-history channels" in distribution["claim"]
    assert "exact-profile deformed-shape projections" in distribution["claim"]
    assert "installed Korean topology, response and deformed views" in distribution["claim"]
    assert "frozen v1 through v19 receipts" in distribution["claim"]
    assert "frozen v1 through v34 receipts" in distribution["claim"]
    assert "last-neutral-truss-leaf deletion" in distribution["claim"]
    assert "last-neutral-frame-leaf deletion" in distribution["claim"]
    assert "orientation/offset/release metadata" in distribution["claim"]
    assert "last-neutral-fixed-constraint deletion" in distribution["claim"]
    assert "last-neutral-nodal-load deletion" in distribution["claim"]
    assert "distinct baseline/section/property displacement" in distribution["claim"]
    assert "one-real-iteration restart parity" in distribution["claim"]
    assert "structural-catalog" in distribution["claim"]
    assert "structural-evidence" in distribution["claim"]
    assert "explicit non-promoting review" in distribution["claim"]
    assert "rejects unresolved libamdhip64 dependencies" in distribution["claim"]
    assert "no authoritative ROCm distribution receipt" in distribution["claim"]
    assert "C6 remain open" in distribution["claim"]
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
    assert "distribution v35 E2E" in deployment["claim"]
    assert "frame/truss-section" in deployment["claim"]
    assert "compatible frame/truss-property" in deployment["claim"]
    assert "truss-section area replacement" in deployment["claim"]
    assert "compatible truss material/section reassignment" in deployment["claim"]
    assert "last-neutral-truss-leaf deletion" in deployment["claim"]
    assert "last-neutral-frame-leaf deletion" in deployment["claim"]
    assert "removed-frame-field binding" in deployment["claim"]
    assert "last-neutral fixed-constraint deletion" in deployment["claim"]
    assert "last-neutral nodal-load deletion" in deployment["claim"]
    assert "normalized-MGT-linear" in deployment["claim"]
    assert "v6 self-hashed local_rootfs_diagnostic_c5 receipt" in deployment["claim"]
    assert "frozen v1 through v5 rootfs receipts" in deployment["claim"]
    assert "outside .github/workflows" in deployment["claim"]
    assert "final C6 remain open" in deployment["claim"]


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
