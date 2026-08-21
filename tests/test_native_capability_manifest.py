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
    assert "standard-gravity self weight" in frame_claim
    assert "material density and section area" in frame_claim
    assert "nested linear load combinations" in frame_claim
    assert "4096 expanded terms" in frame_claim
    for load_boundary in (
        "no nonuniform or member-point load",
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
    result_report_claim = payload["capabilities"]["linear_frame3d_result_report_alpha"][
        "claim"
    ]
    for open_boundary in (
        "native-binary or portable-distribution PDF",
        "durable or packaged Workbench execution",
        "external comparison authority",
        "HIP parity",
        "release authority",
    ):
        assert open_boundary in result_report_claim
    assert "independent Rust recovery-replay-gated" in result_report_claim
    assert "uniform initial-member-local force loads" in result_report_claim
    assert "RX/RY/RZ member-end releases" in result_report_claim
    assert "finite global rigid end offsets" in result_report_claim
    assert "standard-gravity self weight" in result_report_claim
    assert "explicit pattern-or-combination selection" in result_report_claim
    assert "nested linear load-combination superposition" in result_report_claim
    assert "no envelope/nonlinear combination" in result_report_claim
    assert "no translational release" in result_report_claim
    assert "no-overwrite completed Workbench artifact bundle" in result_report_claim
    assert "strict persisted ResultIR-to-ReportIR/HTML replay" in result_report_claim
    assert (
        capabilities.capability_is_enabled(
            payload, "linear_frame3d_external_comparison_alpha"
        )
        is True
    )
    comparison_claim = payload["capabilities"][
        "linear_frame3d_external_comparison_alpha"
    ]["claim"]
    assert "strict external ReferenceIR" in comparison_claim
    assert "0.5%" in comparison_claim
    assert "1%" in comparison_claim
    assert "operator declarations" in comparison_claim
    assert "no SAP2000/MIDAS/OpenSees/CalculiX execution receipt" in comparison_claim
    assert "independent validation" in comparison_claim
    assert "optional source-tree PDF presentation" in comparison_claim
    assert (
        capabilities.capability_is_enabled(
            payload, "linear_frame3d_pdf_report_alpha"
        )
        is True
    )
    pdf_claim = payload["capabilities"]["linear_frame3d_pdf_report_alpha"]["claim"]
    assert payload["capabilities"]["linear_frame3d_pdf_report_alpha"]["cutover_gate"] == "C0"
    assert "strict persisted ResultIR-to-ReportIR replay" in pdf_claim
    assert "optional ReferenceIR-to-ComparisonIR replay" in pdf_claim
    assert "byte-deterministic invariant A4 ASCII PDF" in pdf_claim
    assert "canonical no-overwrite receipt" in pdf_claim
    assert "external_validation=not_established" in pdf_claim
    assert "workstation delivery builder packages only a parseable PDF" in pdf_claim
    assert "no longer fabricates a placeholder report" in pdf_claim
    assert "no native-binary PDF backend" in pdf_claim
    assert "independent validation" in pdf_claim
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
        "cancellation",
        "resume",
        "crash recovery",
        "browser-side solver recovery reconstruction",
        "actual external execution receipt",
        "independent external validation",
        "packaged Workbench",
        "release authority",
    ):
        assert open_boundary.lower() in workbench_claim.lower()
    assert "completed CLI bundle" in workbench_claim
    assert "manifest byte/hash" in workbench_claim
    assert "job-view" in workbench_claim
    assert "same-origin loopback submission endpoint" in workbench_claim
    assert "synchronously runs" in workbench_claim
    assert "failure finalization" in workbench_claim
    assert "strict revision-1 Running" in workbench_claim
    assert "ReferenceIR/ComparisonIR" in workbench_claim
    assert "comparison mapping/unit/tolerance/row/summary/hash replay" in workbench_claim
    assert "invalid or partial comparisons expose neither comparison artifact" in workbench_claim
    assert (
        capabilities.capability_is_enabled(payload, "linear_frame3d_job_alpha") is True
    )
    job_claim = payload["capabilities"]["linear_frame3d_job_alpha"]["claim"]
    assert "filesystem_append_only_single_host.v1" in job_claim
    assert "loopback-only same-origin HTTP host" in job_claim
    assert "strict browser submission envelope" in job_claim
    assert "child structural-cli process" in job_claim
    assert "not a privilege sandbox" in job_claim
    assert "CPU/memory resource limit" in job_claim
    assert "crash recovery" in job_claim
    assert "revision-2 Failed event/view" in job_claim
    assert "queued, terminal, corrupt and partial states are not rewritten" in job_claim
    assert (
        capabilities.capability_is_enabled(
            payload, "linear_frame3d_cli_distribution_alpha"
        )
        is True
    )
    distribution_claim = payload["capabilities"][
        "linear_frame3d_cli_distribution_alpha"
    ]["claim"]
    assert "portable ZIP candidate" in distribution_claim
    assert "same-runner" in distribution_claim
    assert "no installer" in distribution_claim
    assert "clean-machine" in distribution_claim
    assert "bounded external comparison schemas" in distribution_claim
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
