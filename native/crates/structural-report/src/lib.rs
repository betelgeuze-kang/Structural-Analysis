//! Deterministic bounded-product report projection owner.

#![forbid(unsafe_code)]

use std::fmt::Write as _;

mod pdf;

pub use pdf::{
    render_nonlinear_ndtha_pdf_v1, validate_deterministic_pdf_v1, NonlinearNdthaPdfDocumentV1,
    PdfRenderError,
};

use structural_contracts::product_ir::{
    build_nonlinear_ndtha_report_ir_v1, NonlinearNdthaReportIrDocumentV1,
    NonlinearNdthaResultIrDocumentV1, ProductIrContractError,
};

/// Exact `ReportIR` plus deterministic Markdown document source suitable for a later PDF renderer.
#[derive(Clone, Debug)]
pub struct NonlinearNdthaReportBundleV1 {
    pub report_ir: NonlinearNdthaReportIrDocumentV1,
    pub document_source: String,
}

/// Project one bounded `ResultIR` into `ReportIR` and deterministic Markdown source.
///
/// # Errors
///
/// Returns a contract error if a non-finite result cannot be rendered or `ReportIR` identity
/// construction fails.
pub fn build_nonlinear_ndtha_report_v1(
    result: &NonlinearNdthaResultIrDocumentV1,
) -> Result<NonlinearNdthaReportBundleV1, ProductIrContractError> {
    let source = result.result();
    let mut document = String::new();
    writeln!(&mut document, "# Nonlinear NDTHA Analysis Report")
        .expect("String writes cannot fail");
    writeln!(&mut document).expect("String writes cannot fail");
    writeln!(&mut document, "- Case: `{}`", source.case_id).expect("String writes cannot fail");
    writeln!(&mut document, "- Authority: `bounded_candidate`").expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Terminal status: `{:?}`",
        source.summary.terminal_status
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Completed steps: {}",
        source.summary.step_count_completed
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Maximum drift ratio: {:.17e} %",
        source.summary.max_drift_ratio_pct
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Maximum plastic stories: {}",
        source.summary.max_plastic_story_count
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Residual top displacement: {:.17e} m",
        source.summary.residual_top_displacement_m
    )
    .expect("String writes cannot fail");
    writeln!(&mut document, "- Backend: `cpu` / `fp64` / fallback `0`")
        .expect("String writes cannot fail");
    writeln!(&mut document, "- Result hash: `{}`", source.result_hash)
        .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Model hash: `{}`",
        source.identity.model_hash
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- State hash: `{}`",
        source.identity.state_hash
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Execution hash: `{}`",
        source.identity.execution_hash
    )
    .expect("String writes cannot fail");
    writeln!(&mut document).expect("String writes cannot fail");
    writeln!(
        &mut document,
        "> This report is a deterministic projection of a bounded candidate result; it is not engineering acceptance or design-code compliance."
    )
    .expect("String writes cannot fail");
    let report_ir = build_nonlinear_ndtha_report_ir_v1(result, document.as_bytes())?;
    Ok(NonlinearNdthaReportBundleV1 {
        report_ir,
        document_source: document,
    })
}
