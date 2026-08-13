use std::path::{Path, PathBuf};

use structural_contracts::product_ir::{
    average_step_iterations, build_nonlinear_ndtha_report_ir_v1,
    build_nonlinear_ndtha_result_ir_v1, parse_native_analysis_request_v1,
    NonlinearNdthaResultIrDocumentV1, NonlinearNdthaResultSummaryV1,
    NonlinearNdthaTerminalStatusV1, ResultIdentityV1,
};
use structural_contracts::solver_cpu::parse_nonlinear_ndtha_cpu_case_v1;
use structural_contracts::sparse_product::{
    build_sparse_linear_request_v1, build_sparse_linear_result_ir_v1,
    sparse_linear_execution_hash_v1, sparse_linear_model_hash_v1, SparseLinearAnalysisRequestV1,
    SparseLinearBackendV1, SparseLinearConfigV1, SparseLinearResultIrDocumentV1,
    SparseLinearResultSummaryV1, SPARSE_LINEAR_REQUEST_V1,
};
use structural_report::{
    build_nonlinear_ndtha_report_v1, render_nonlinear_ndtha_localized_pdf_v2,
    render_nonlinear_ndtha_pdf_v1, render_sparse_linear_pdf_v1,
    validate_deterministic_localized_pdf_v2, validate_deterministic_pdf_v1, PdfRenderError,
    PdfReportLocaleV2,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn result_document() -> NonlinearNdthaResultIrDocumentV1 {
    let root = repository_root();
    let request = parse_native_analysis_request_v1(
        &std::fs::read(root.join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"))
            .expect("tracked request"),
    )
    .expect("strict request");
    let golden = parse_nonlinear_ndtha_cpu_case_v1(
        &std::fs::read(root.join(
            "native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json",
        ))
        .expect("tracked C1 golden"),
    )
    .expect("strict CPU golden");
    let result = golden.result;
    let completed = usize::try_from(result.step_count_completed).expect("step count");
    let adaptive_iteration_sum = result.response.step_iterations[..completed]
        .iter()
        .map(|value| u64::from(*value))
        .sum();
    build_nonlinear_ndtha_result_ir_v1(
        &request,
        ResultIdentityV1 {
            request_hash: request.request_hash().to_owned(),
            model_hash:
                "sha256:ec014742cc1079fe02be7379b49b969f219e89fd8cf715dcee3c4590f2929fc0"
                    .to_owned(),
            state_hash:
                "sha256:1111111111111111111111111111111111111111111111111111111111111111"
                    .to_owned(),
            execution_hash:
                "sha256:2222222222222222222222222222222222222222222222222222222222222222"
                    .to_owned(),
            checkpoint_hash:
                "sha256:3333333333333333333333333333333333333333333333333333333333333333"
                    .to_owned(),
        },
        NonlinearNdthaResultSummaryV1 {
            terminal_status: NonlinearNdthaTerminalStatusV1::Completed,
            step_count_completed: result.step_count_completed,
            max_plastic_story_count: result.max_plastic_story_count,
            max_drift_ratio_pct: result.max_drift_ratio_pct,
            adaptive_iteration_sum,
            avg_step_iterations: average_step_iterations(
                adaptive_iteration_sum,
                result.step_count_completed,
            )
            .expect("average"),
            total_line_search_backtracks: result.total_line_search_backtracks,
            collapse_step: result.collapse_step,
            collapse_time_s: result.collapse_time_s,
            collapse_drift_ratio_pct: result.collapse_drift_ratio_pct,
            collapse_top_displacement_m: result.collapse_top_displacement_m,
            residual_top_displacement_m: result.residual_top_displacement_m,
            residual_drift_ratio_pct: result.residual_drift_ratio_pct,
        },
        result.response,
    )
    .expect("bounded ResultIR")
}

fn sparse_result_document() -> SparseLinearResultIrDocumentV1 {
    let request = build_sparse_linear_request_v1(SparseLinearAnalysisRequestV1 {
        schema_version: SPARSE_LINEAR_REQUEST_V1.to_owned(),
        operation: "solve_sparse_spd_pcg".to_owned(),
        case_id: "sparse-pdf-c5".to_owned(),
        backend: SparseLinearBackendV1::Cpu,
        order: 2,
        row_offsets: vec![0, 2, 4],
        column_indices: vec![0, 1, 0, 1],
        values: vec![2.0, -1.0, -1.0, 2.0],
        right_hand_side: vec![0.0, 3.0],
        initial_guess: Vec::new(),
        config: SparseLinearConfigV1 {
            max_iterations: 8,
            absolute_residual_tolerance: 1.0e-14,
            relative_residual_tolerance: 1.0e-14,
            maximum_increment: 0.0,
        },
    })
    .expect("sparse request");
    build_sparse_linear_result_ir_v1(
        &request,
        ResultIdentityV1 {
            request_hash: request.request_hash().to_owned(),
            model_hash: sparse_linear_model_hash_v1(&request).expect("sparse model hash"),
            state_hash: format!("sha256:{}", "4".repeat(64)),
            execution_hash: sparse_linear_execution_hash_v1(&request)
                .expect("sparse execution hash"),
            checkpoint_hash: format!("sha256:{}", "5".repeat(64)),
        },
        SparseLinearResultSummaryV1 {
            order: 2,
            nonzero_count: 4,
            iterations: 2,
            initial_residual_inf: 3.0,
            final_residual_inf: 0.0,
            final_residual_l2: 0.0,
            last_increment_inf: 1.0,
        },
        vec![1.0, 2.0],
    )
    .expect("sparse result")
}

#[test]
fn sparse_linear_pdf_is_deterministic_and_exactly_projection_bound() {
    let result = sparse_result_document();
    let report = structural_report::build_sparse_linear_report_v1(&result)
        .expect("deterministic sparse report");
    let first = render_sparse_linear_pdf_v1(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
    )
    .expect("sparse PDF");
    let second = render_sparse_linear_pdf_v1(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
    )
    .expect("repeated sparse PDF");
    assert_eq!(first, second);
    assert_eq!(first.source_result_hash(), result.result_hash());
    assert_eq!(first.source_report_hash(), report.report_ir.report_hash());
    validate_deterministic_pdf_v1(first.as_bytes()).expect("valid sparse PDF structure");
    assert!(first
        .as_bytes()
        .windows(b"sparse-report-pdf.v1".len())
        .any(|window| window == b"sparse-report-pdf.v1"));

    assert!(matches!(
        render_sparse_linear_pdf_v1(&result, &report.report_ir, b"forged document"),
        Err(PdfRenderError::Binding { ref code, .. })
            if code == "pdf_document_source_projection_mismatch"
    ));
}

#[test]
fn deterministic_pdf_is_hash_bound_to_exact_report_projection() {
    let result = result_document();
    let report = build_nonlinear_ndtha_report_v1(&result).expect("deterministic report");
    let first = render_nonlinear_ndtha_pdf_v1(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
    )
    .expect("native PDF");
    let second = render_nonlinear_ndtha_pdf_v1(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
    )
    .expect("repeated native PDF");
    assert_eq!(first, second);
    assert_eq!(first.media_type(), "application/pdf");
    assert_eq!(first.source_result_hash(), result.result_hash());
    assert_eq!(first.source_report_hash(), report.report_ir.report_hash());
    assert_eq!(
        first.document_source_hash(),
        &structural_contracts::product_ir::sha256_identity(report.document_source.as_bytes())
    );
    assert!(first.claim_boundary().contains("not_pdf_a_accessibility"));
    validate_deterministic_pdf_v1(first.as_bytes()).expect("valid generated PDF structure");
}

#[test]
fn forged_document_and_self_consistent_alternate_report_are_rejected() {
    let result = result_document();
    let report = build_nonlinear_ndtha_report_v1(&result).expect("deterministic report");
    let error = render_nonlinear_ndtha_pdf_v1(&result, &report.report_ir, b"forged document")
        .expect_err("forged document");
    assert!(matches!(
        error,
        PdfRenderError::Binding { ref code, .. }
            if code == "pdf_document_source_projection_mismatch"
    ));

    let alternate = build_nonlinear_ndtha_report_ir_v1(&result, b"alternate source")
        .expect("self-consistent alternate ReportIR");
    let error =
        render_nonlinear_ndtha_pdf_v1(&result, &alternate, report.document_source.as_bytes())
            .expect_err("alternate report");
    assert!(matches!(
        error,
        PdfRenderError::Binding { ref code, .. }
            if code == "pdf_report_ir_projection_mismatch"
    ));
}

#[test]
fn xref_tamper_is_detected_without_a_pdf_parser_dependency() {
    let result = result_document();
    let report = build_nonlinear_ndtha_report_v1(&result).expect("deterministic report");
    let document = render_nonlinear_ndtha_pdf_v1(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
    )
    .expect("native PDF");
    let mut tampered = document.as_bytes().to_vec();
    let xref = tampered
        .windows(b"xref\n0 9\n".len())
        .position(|window| window == b"xref\n0 9\n")
        .expect("xref table");
    let first_object_offset = xref + b"xref\n0 9\n".len() + b"0000000000 65535 f \n".len();
    tampered[first_object_offset] = b'9';
    assert!(matches!(
        validate_deterministic_pdf_v1(&tampered),
        Err(PdfRenderError::Pdf { ref code, .. }) if code == "pdf_object_offset_invalid"
    ));

    for prefix_length in 0..document.as_bytes().len() {
        assert!(
            validate_deterministic_pdf_v1(&document.as_bytes()[..prefix_length]).is_err(),
            "truncated PDF accepted at byte {prefix_length}"
        );
    }
    let out_of_range = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nstartxref\n9999999999\n%%EOF\n";
    assert!(validate_deterministic_pdf_v1(out_of_range).is_err());
}

#[test]
fn embedded_font_localized_pdfs_are_deterministic_distinct_and_extractable() {
    let result = result_document();
    let report = build_nonlinear_ndtha_report_v1(&result).expect("deterministic report");
    let mut rendered = Vec::new();
    for locale in [PdfReportLocaleV2::EnUs, PdfReportLocaleV2::KoKr] {
        let first = render_nonlinear_ndtha_localized_pdf_v2(
            &result,
            &report.report_ir,
            report.document_source.as_bytes(),
            locale,
        )
        .expect("localized native PDF");
        let second = render_nonlinear_ndtha_localized_pdf_v2(
            &result,
            &report.report_ir,
            report.document_source.as_bytes(),
            locale,
        )
        .expect("repeated localized native PDF");
        assert_eq!(first, second);
        assert_eq!(first.locale(), locale);
        assert_eq!(first.media_type(), "application/pdf");
        assert_eq!(first.source_result_hash(), result.result_hash());
        assert_eq!(first.source_report_hash(), report.report_ir.report_hash());
        assert_eq!(
            first.embedded_font_hash(),
            "sha256:bdcc6ac7747f102ba1dc64a0d034d9695bab41b1f82b098ffb836334c9329a68"
        );
        assert!(first
            .claim_boundary()
            .contains("not_arbitrary_unicode_pdf_ua_accessibility"));
        validate_deterministic_localized_pdf_v2(first.as_bytes())
            .expect("localized PDF structure and embedded font");
        assert!(first
            .as_bytes()
            .windows(b"<0060> <AC04>".len())
            .any(|window| window == b"<0060> <AC04>"));
        rendered.push(first);
    }
    assert_ne!(rendered[0].pdf_hash(), rendered[1].pdf_hash());
    assert_ne!(rendered[0].as_bytes(), rendered[1].as_bytes());
}

#[test]
fn localized_pdf_rejects_projection_and_embedded_font_tampering() {
    let result = result_document();
    let report = build_nonlinear_ndtha_report_v1(&result).expect("deterministic report");
    let error = render_nonlinear_ndtha_localized_pdf_v2(
        &result,
        &report.report_ir,
        b"forged document",
        PdfReportLocaleV2::KoKr,
    )
    .expect_err("forged localized document");
    assert!(matches!(
        error,
        PdfRenderError::Binding { ref code, .. }
            if code == "pdf_document_source_projection_mismatch"
    ));

    let document = render_nonlinear_ndtha_localized_pdf_v2(
        &result,
        &report.report_ir,
        report.document_source.as_bytes(),
        PdfReportLocaleV2::KoKr,
    )
    .expect("localized native PDF");
    let mut tampered = document.as_bytes().to_vec();
    let font_header = b"8 0 obj\n<< /Length 37356 /Length1 37356 >>\nstream\n";
    let font_start = tampered
        .windows(font_header.len())
        .position(|window| window == font_header)
        .expect("embedded font stream")
        + font_header.len();
    tampered[font_start] ^= 1;
    assert!(matches!(
        validate_deterministic_localized_pdf_v2(&tampered),
        Err(PdfRenderError::Pdf { ref code, .. }) if code == "pdf_embedded_font_invalid"
    ));
    assert!(validate_deterministic_localized_pdf_v2(
        &document.as_bytes()[..document.as_bytes().len() - 1]
    )
    .is_err());
}
