//! Deterministic bounded-product report projection owner.

#![forbid(unsafe_code)]

use std::fmt::Write as _;

mod localized_font;
mod localized_pdf;
mod pdf;

pub use localized_pdf::{
    render_nonlinear_ndtha_localized_pdf_v2, render_sparse_linear_localized_pdf_v2,
    validate_deterministic_localized_pdf_v2, NonlinearNdthaLocalizedPdfDocumentV2,
    PdfReportLocaleV2, SparseLinearLocalizedPdfDocumentV2,
};
pub use pdf::{
    render_nonlinear_ndtha_pdf_v1, render_sparse_linear_pdf_v1, validate_deterministic_pdf_v1,
    NonlinearNdthaPdfDocumentV1, PdfRenderError, SparseLinearPdfDocumentV1,
};

use structural_contracts::product_ir::{
    build_nonlinear_ndtha_report_ir_v1, NonlinearNdthaReportIrDocumentV1,
    NonlinearNdthaResultIrDocumentV1, ProductIrContractError,
};
use structural_contracts::sparse_product::{
    build_sparse_linear_report_ir_v1, SparseLinearReportIrDocumentV1,
    SparseLinearResultIrDocumentV1,
};
use structural_contracts::spectral_product::{
    build_dense_spectral_report_ir_v1, DenseSpectralReportIrDocumentV1,
    DenseSpectralResultIrDocumentV1, SpectralAnalysisKindV1, SpectralModeV1,
};
use structural_contracts::static_product::{
    build_nonlinear_static_report_ir_v1, NonlinearStaticReportIrDocumentV1,
    NonlinearStaticResultIrDocumentV1,
};

/// Exact `ReportIR` plus deterministic Markdown document source suitable for a later PDF renderer.
#[derive(Clone, Debug)]
pub struct NonlinearNdthaReportBundleV1 {
    pub report_ir: NonlinearNdthaReportIrDocumentV1,
    pub document_source: String,
}

/// Exact spectral `ReportIR` plus deterministic Markdown document source.
#[derive(Clone, Debug)]
pub struct DenseSpectralReportBundleV1 {
    pub report_ir: DenseSpectralReportIrDocumentV1,
    pub document_source: String,
}

/// Exact sparse `ReportIR` plus deterministic Markdown document source.
#[derive(Clone, Debug)]
pub struct SparseLinearReportBundleV1 {
    pub report_ir: SparseLinearReportIrDocumentV1,
    pub document_source: String,
}

/// Exact nonlinear-static `ReportIR` plus deterministic Markdown document source.
#[derive(Clone, Debug)]
pub struct NonlinearStaticReportBundleV1 {
    pub report_ir: NonlinearStaticReportIrDocumentV1,
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

/// Project one bounded modal or linear-buckling `ResultIR` into deterministic report artifacts.
///
/// # Errors
///
/// Returns a contract error if the exact result cannot be bound into `ReportIR`.
pub fn build_dense_spectral_report_v1(
    result: &DenseSpectralResultIrDocumentV1,
) -> Result<DenseSpectralReportBundleV1, ProductIrContractError> {
    let source = result.result();
    let primary = match &source.modes[0] {
        SpectralModeV1::Modal {
            eigenvalue_rad2_per_s2,
            ..
        } => *eigenvalue_rad2_per_s2,
        SpectralModeV1::LinearBuckling { load_factor, .. } => *load_factor,
    };
    let primary_label = match source.analysis_kind {
        SpectralAnalysisKindV1::Modal => "First positive eigenvalue (rad^2/s^2)",
        SpectralAnalysisKindV1::LinearBuckling => "Critical load factor",
    };
    let mut document = String::new();
    writeln!(&mut document, "# Dense Spectral Analysis Report").expect("String writes cannot fail");
    writeln!(&mut document).expect("String writes cannot fail");
    writeln!(&mut document, "- Case: `{}`", source.case_id).expect("String writes cannot fail");
    writeln!(&mut document, "- Analysis: `{}`", source.analysis_kind)
        .expect("String writes cannot fail");
    writeln!(&mut document, "- Authority: `bounded_candidate`").expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Published modes: {}",
        source.summary.mode_count
    )
    .expect("String writes cannot fail");
    writeln!(&mut document, "- {primary_label}: {primary:.17e}")
        .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Metric orthogonality error: {:.17e}",
        source.summary.metric_orthogonality_error_inf
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Operator diagonalization error: {:.17e}",
        source.summary.operator_diagonalization_error_inf
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
        "> This report is a deterministic projection of a bounded dense spectral candidate; it is not sparse whole-model authority, engineering acceptance, or design-code compliance."
    )
    .expect("String writes cannot fail");
    let report_ir = build_dense_spectral_report_ir_v1(result, document.as_bytes())?;
    Ok(DenseSpectralReportBundleV1 {
        report_ir,
        document_source: document,
    })
}

/// Project one converged bounded sparse `ResultIR` into deterministic report artifacts.
///
/// # Errors
///
/// Returns a contract error if the exact result cannot be rendered or bound into a canonical,
/// self-hashed `ReportIR`.
pub fn build_sparse_linear_report_v1(
    result: &SparseLinearResultIrDocumentV1,
) -> Result<SparseLinearReportBundleV1, ProductIrContractError> {
    let source = result.result();
    let maximum_absolute_solution = source
        .solution
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max);
    let mut document = String::new();
    writeln!(&mut document, "# Sparse Linear Analysis Report").expect("String writes cannot fail");
    writeln!(&mut document).expect("String writes cannot fail");
    writeln!(&mut document, "- Case: `{}`", source.case_id).expect("String writes cannot fail");
    writeln!(&mut document, "- Authority: `bounded_candidate`").expect("String writes cannot fail");
    writeln!(&mut document, "- Matrix order: {}", source.summary.order)
        .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Canonical nonzeros: {}",
        source.summary.nonzero_count
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- PCG iterations: {}",
        source.summary.iterations
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Initial residual infinity norm: {:.17e}",
        source.summary.initial_residual_inf
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Final true residual infinity norm: {:.17e}",
        source.summary.final_residual_inf
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Final true residual L2 norm: {:.17e}",
        source.summary.final_residual_l2
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Maximum absolute solution component: {maximum_absolute_solution:.17e}"
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
        "> This report is a deterministic projection of a bounded canonical-CSR CPU candidate; it is not whole-model assembly authority, engineering acceptance, or design-code compliance."
    )
    .expect("String writes cannot fail");
    let report_ir = build_sparse_linear_report_ir_v1(result, document.as_bytes())?;
    Ok(SparseLinearReportBundleV1 {
        report_ir,
        document_source: document,
    })
}

/// Project one converged nonlinear-static `ResultIR` into deterministic report artifacts.
///
/// # Errors
///
/// Returns a contract error if the exact result cannot be rendered or bound into a canonical,
/// self-hashed `ReportIR`.
pub fn build_nonlinear_static_report_v1(
    result: &NonlinearStaticResultIrDocumentV1,
) -> Result<NonlinearStaticReportBundleV1, ProductIrContractError> {
    let source = result.result();
    let mut document = String::new();
    writeln!(&mut document, "# Nonlinear Static Analysis Report")
        .expect("String writes cannot fail");
    writeln!(&mut document).expect("String writes cannot fail");
    writeln!(&mut document, "- Case: `{}`", source.case_id).expect("String writes cannot fail");
    writeln!(&mut document, "- Authority: `bounded_candidate`").expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Story count: {}",
        source.summary.story_count
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Newton iterations: {}",
        source.summary.iterations
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Final residual infinity norm: {:.17e} N",
        source.summary.residual_inf
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Maximum absolute displacement: {:.17e} m",
        source.summary.max_abs_displacement_m
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Top displacement: {:.17e} m",
        source.summary.top_displacement_m
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Base shear: {:.17e} kN",
        source.summary.base_shear_kn
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Plastic stories: {}",
        source.summary.plastic_story_count
    )
    .expect("String writes cannot fail");
    writeln!(
        &mut document,
        "- Line-search backtracks: {}",
        source.summary.line_search_backtracks
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
        "> This report is a deterministic projection of a bounded story-frame CPU Newton candidate; it is not general whole-model authority, engineering acceptance, or design-code compliance."
    )
    .expect("String writes cannot fail");
    let report_ir = build_nonlinear_static_report_ir_v1(result, document.as_bytes())?;
    Ok(NonlinearStaticReportBundleV1 {
        report_ir,
        document_source: document,
    })
}
