from __future__ import annotations

import structural_analysis.engine_v2 as engine_v2
import structural_analysis.engine_v2.assembly_backend as assembly_backend


def test_krylov_primitive_public_api_is_reexported_at_both_engine_boundaries() -> None:
    names = (
        "HIP_KRYLOV_PRIMITIVES_CONTEXT_RECEIPT_SCHEMA_VERSION",
        "HIP_KRYLOV_PRIMITIVES_BATCH_RECEIPT_SCHEMA_VERSION",
        "HIP_KRYLOV_PRIMITIVES_EVALUATION_RECEIPT_SCHEMA_VERSION",
        "HIP_RTC_KRYLOV_PRIMITIVES_IDENTITY_SCHEMA_VERSION",
        "HipKrylovPrimitivesExecutionContext",
        "HipKrylovPrimitivesContextOpenResult",
        "HipKrylovPrimitivesContextReceipt",
        "HipKrylovPrimitivesBatchReceipt",
        "HipKrylovPrimitivesEvaluation",
        "HipKrylovPrimitivesEvaluationReceipt",
        "HipRtcKrylovPrimitivesKernel",
        "HipRtcKrylovPrimitivesKernelIdentity",
        "HipRtcKrylovPrimitivesError",
        "compile_hip_rtc_krylov_primitives_kernel",
        "open_hip_krylov_primitives_execution_context",
        "reduction_output_count",
        "validate_hip_krylov_primitives_context_receipt",
        "validate_hip_krylov_primitives_batch_receipt",
        "validate_hip_krylov_primitives_evaluation_receipt",
        "validate_hip_krylov_primitives_evaluation",
    )
    for module in (assembly_backend, engine_v2):
        for name in names:
            assert name in module.__all__
            assert getattr(module, name) is getattr(assembly_backend, name)
