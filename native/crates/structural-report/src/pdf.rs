use std::fmt;
use std::fmt::Write as _;

use structural_contracts::product_ir::{
    sha256_identity, NonlinearNdthaReportIrDocumentV1, NonlinearNdthaResultIrDocumentV1,
    NonlinearNdthaTerminalStatusV1, ProductIrContractError,
};
use structural_contracts::sparse_product::{
    SparseLinearReportIrDocumentV1, SparseLinearResultIrDocumentV1,
};

use crate::{build_nonlinear_ndtha_report_v1, build_sparse_linear_report_v1};

const PDF_MEDIA_TYPE: &str = "application/pdf";
const PDF_CLAIM_BOUNDARY: &str = "deterministic_single_page_projection_of_one_bounded_candidate_report_not_pdf_a_accessibility_engineering_acceptance_or_design_code_compliance";

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PdfRenderError {
    Contract(ProductIrContractError),
    Binding {
        code: String,
        path: String,
        detail: String,
    },
    Pdf {
        code: String,
        detail: String,
    },
}

impl PdfRenderError {
    #[must_use]
    pub const fn is_input_error(&self) -> bool {
        matches!(self, Self::Contract(_) | Self::Binding { .. })
    }
}

impl fmt::Display for PdfRenderError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "{error}"),
            Self::Binding { code, path, detail } => write!(formatter, "{code} at {path}: {detail}"),
            Self::Pdf { code, detail } => write!(formatter, "{code}: {detail}"),
        }
    }
}

impl std::error::Error for PdfRenderError {}

impl From<ProductIrContractError> for PdfRenderError {
    fn from(error: ProductIrContractError) -> Self {
        Self::Contract(error)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NonlinearNdthaPdfDocumentV1 {
    bytes: Vec<u8>,
    source_result_hash: String,
    source_report_hash: String,
    document_source_hash: String,
    pdf_hash: String,
}

impl NonlinearNdthaPdfDocumentV1 {
    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[must_use]
    pub fn media_type(&self) -> &'static str {
        PDF_MEDIA_TYPE
    }

    #[must_use]
    pub fn source_result_hash(&self) -> &str {
        &self.source_result_hash
    }

    #[must_use]
    pub fn source_report_hash(&self) -> &str {
        &self.source_report_hash
    }

    #[must_use]
    pub fn document_source_hash(&self) -> &str {
        &self.document_source_hash
    }

    #[must_use]
    pub fn pdf_hash(&self) -> &str {
        &self.pdf_hash
    }

    #[must_use]
    pub fn claim_boundary(&self) -> &'static str {
        PDF_CLAIM_BOUNDARY
    }
}

/// Exact deterministic PDF projection for one bounded sparse-linear result.
///
/// The wire metadata is intentionally identical to the frozen nonlinear-NDTHA PDF document. The
/// distinct alias keeps the accepted source profile explicit at compile time without changing the
/// v1 byte-level PDF container contract.
pub type SparseLinearPdfDocumentV1 = NonlinearNdthaPdfDocumentV1;

/// Render one deterministic, single-page PDF from an exact bounded report projection.
///
/// The supplied `ReportIR` and Markdown bytes must be byte-identical to a fresh projection from
/// `result`; accepting merely self-consistent but independently forged report inputs is forbidden.
///
/// # Errors
///
/// Rejects report/document projection drift, non-ASCII printable identifiers, PDF construction
/// overflow and any invalid generated xref/object structure.
pub fn render_nonlinear_ndtha_pdf_v1(
    result: &NonlinearNdthaResultIrDocumentV1,
    report: &NonlinearNdthaReportIrDocumentV1,
    document_source: &[u8],
) -> Result<NonlinearNdthaPdfDocumentV1, PdfRenderError> {
    let expected = build_nonlinear_ndtha_report_v1(result)?;
    if expected.document_source.as_bytes() != document_source {
        return Err(binding_error(
            "pdf_document_source_projection_mismatch",
            "/document_source",
            "PDF source bytes are not the deterministic projection of the supplied ResultIR",
        ));
    }
    if expected.report_ir.canonical_bytes() != report.canonical_bytes() {
        return Err(binding_error(
            "pdf_report_ir_projection_mismatch",
            "/report_ir",
            "ReportIR bytes are not the deterministic projection of the supplied ResultIR and document source",
        ));
    }
    let bytes = build_pdf_bytes(result, report)?;
    validate_deterministic_pdf_v1(&bytes)?;
    Ok(NonlinearNdthaPdfDocumentV1 {
        pdf_hash: sha256_identity(&bytes),
        source_result_hash: result.result_hash().to_owned(),
        source_report_hash: report.report_hash().to_owned(),
        document_source_hash: sha256_identity(document_source),
        bytes,
    })
}

/// Render one deterministic, single-page PDF from an exact sparse-linear report projection.
///
/// The supplied `ReportIR` and Markdown bytes must be byte-identical to a fresh projection from
/// `result`; a separately self-consistent report is not sufficient.
///
/// # Errors
///
/// Rejects report/document projection drift, non-ASCII printable identifiers, PDF construction
/// overflow, and any invalid generated xref/object structure.
pub fn render_sparse_linear_pdf_v1(
    result: &SparseLinearResultIrDocumentV1,
    report: &SparseLinearReportIrDocumentV1,
    document_source: &[u8],
) -> Result<SparseLinearPdfDocumentV1, PdfRenderError> {
    let expected = build_sparse_linear_report_v1(result)?;
    if expected.document_source.as_bytes() != document_source {
        return Err(binding_error(
            "pdf_document_source_projection_mismatch",
            "/document_source",
            "PDF source bytes are not the deterministic projection of the supplied sparse ResultIR",
        ));
    }
    if expected.report_ir.canonical_json() != report.canonical_json() {
        return Err(binding_error(
            "pdf_report_ir_projection_mismatch",
            "/report_ir",
            "ReportIR bytes are not the deterministic projection of the supplied sparse ResultIR and document source",
        ));
    }
    let bytes = build_sparse_linear_pdf_bytes(result, report)?;
    validate_deterministic_pdf_v1(&bytes)?;
    Ok(NonlinearNdthaPdfDocumentV1 {
        pdf_hash: sha256_identity(&bytes),
        source_result_hash: result.result_hash().to_owned(),
        source_report_hash: report.report_hash().to_owned(),
        document_source_hash: sha256_identity(document_source),
        bytes,
    })
}

/// Validate the deterministic PDF object's header, xref offsets, object count and trailer.
///
/// # Errors
///
/// Returns a stable renderer error for truncation, malformed offsets or object-table drift.
pub fn validate_deterministic_pdf_v1(bytes: &[u8]) -> Result<(), PdfRenderError> {
    if !bytes.starts_with(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n") || !bytes.ends_with(b"%%EOF\n") {
        return Err(pdf_error(
            "pdf_structure_invalid",
            "PDF header, binary marker or EOF marker is invalid",
        ));
    }
    let startxref_marker = b"startxref\n";
    let startxref_position = find_last(bytes, startxref_marker).ok_or_else(|| {
        pdf_error(
            "pdf_xref_missing",
            "PDF startxref marker is missing from the trailer",
        )
    })?;
    let offset_start = startxref_position
        .checked_add(startxref_marker.len())
        .filter(|offset| *offset <= bytes.len())
        .ok_or_else(|| pdf_error("pdf_xref_invalid", "PDF startxref offset overflowed"))?;
    let offset_end = bytes[offset_start..]
        .iter()
        .position(|byte| *byte == b'\n')
        .map(|relative| offset_start + relative)
        .ok_or_else(|| pdf_error("pdf_xref_invalid", "PDF startxref offset is unterminated"))?;
    let xref_offset = parse_usize(&bytes[offset_start..offset_end]).ok_or_else(|| {
        pdf_error(
            "pdf_xref_invalid",
            "PDF startxref offset is not a bounded decimal integer",
        )
    })?;
    let xref_header_end = xref_offset
        .checked_add(9)
        .filter(|offset| *offset <= bytes.len())
        .ok_or_else(|| {
            pdf_error(
                "pdf_xref_invalid",
                "PDF startxref offset is outside the document",
            )
        })?;
    if bytes.get(xref_offset..xref_header_end) != Some(b"xref\n0 9\n") {
        return Err(pdf_error(
            "pdf_xref_invalid",
            "PDF xref offset or fixed object count is invalid",
        ));
    }
    let mut cursor = xref_offset + 9;
    let free_line = read_line(bytes, &mut cursor)
        .ok_or_else(|| pdf_error("pdf_xref_invalid", "PDF free xref entry is missing"))?;
    if free_line != b"0000000000 65535 f " {
        return Err(pdf_error(
            "pdf_xref_invalid",
            "PDF free xref entry is invalid",
        ));
    }
    for object_id in 1..=8 {
        let line = read_line(bytes, &mut cursor)
            .ok_or_else(|| pdf_error("pdf_xref_invalid", "PDF object xref entry is missing"))?;
        if line.len() != 19 || &line[10..] != b" 00000 n " {
            return Err(pdf_error(
                "pdf_xref_invalid",
                "PDF object xref entry has an invalid fixed-width form",
            ));
        }
        let object_offset = parse_usize(&line[..10]).ok_or_else(|| {
            pdf_error(
                "pdf_xref_invalid",
                "PDF object xref offset is not a decimal integer",
            )
        })?;
        let marker = format!("{object_id} 0 obj\n");
        let marker_end = object_offset
            .checked_add(marker.len())
            .filter(|offset| *offset <= bytes.len())
            .ok_or_else(|| {
                pdf_error(
                    "pdf_object_offset_invalid",
                    "PDF object offset is outside the document",
                )
            })?;
        if bytes.get(object_offset..marker_end) != Some(marker.as_bytes()) {
            return Err(pdf_error(
                "pdf_object_offset_invalid",
                "PDF xref entry does not point to its declared object",
            ));
        }
    }
    let trailer = bytes.get(cursor..startxref_position).ok_or_else(|| {
        pdf_error(
            "pdf_trailer_invalid",
            "PDF xref entries overlap or exceed the trailer boundary",
        )
    })?;
    if !trailer.windows(12).any(|window| window == b"/Root 1 0 R ")
        || !trailer.windows(12).any(|window| window == b"/Info 8 0 R ")
        || !trailer.windows(8).any(|window| window == b"/Size 9 ")
    {
        return Err(pdf_error(
            "pdf_trailer_invalid",
            "PDF trailer does not bind the fixed catalog, info and object count",
        ));
    }
    Ok(())
}

#[allow(clippy::too_many_lines)]
fn build_pdf_bytes(
    result: &NonlinearNdthaResultIrDocumentV1,
    report: &NonlinearNdthaReportIrDocumentV1,
) -> Result<Vec<u8>, PdfRenderError> {
    let source = result.result();
    let report_source = report.report();
    let case_id = pdf_literal(&source.case_id)?;
    let terminal_status = match source.summary.terminal_status {
        NonlinearNdthaTerminalStatusV1::Completed => "completed",
        NonlinearNdthaTerminalStatusV1::Collapsed => "collapsed",
    };

    let mut content = String::new();
    writeln!(&mut content, "q").expect("String writes cannot fail");
    writeln!(&mut content, "0.055 0.118 0.204 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 742 595 100 re f").expect("String writes cannot fail");
    writeln!(&mut content, "0.129 0.588 0.953 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 734 595 8 re f").expect("String writes cannot fail");
    writeln!(&mut content, "Q").expect("String writes cannot fail");
    text_line(
        &mut content,
        "F2",
        21.0,
        1.0,
        1.0,
        1.0,
        48.0,
        794.0,
        "Structural Analysis Report",
    )?;
    text_line(
        &mut content,
        "F1",
        10.0,
        0.82,
        0.88,
        0.95,
        48.0,
        773.0,
        "Bounded nonlinear NDTHA - deterministic native PDF v1",
    )?;

    panel(&mut content, 48.0, 550.0, 499.0, 154.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        678.0,
        "Analysis summary",
    )?;
    label_value(&mut content, 66.0, 653.0, "Case", &case_id)?;
    label_value(
        &mut content,
        66.0,
        633.0,
        "Terminal status",
        terminal_status,
    )?;
    label_value(
        &mut content,
        66.0,
        613.0,
        "Completed steps",
        &source.summary.step_count_completed.to_string(),
    )?;
    label_value(
        &mut content,
        66.0,
        593.0,
        "Maximum drift ratio",
        &format!("{:.8e} percent", source.summary.max_drift_ratio_pct),
    )?;
    label_value(
        &mut content,
        66.0,
        573.0,
        "Residual top displacement",
        &format!("{:.8e} m", source.summary.residual_top_displacement_m),
    )?;

    panel(&mut content, 48.0, 315.0, 499.0, 215.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        504.0,
        "Provenance",
    )?;
    let provenance = [
        ("Result", source.result_hash.as_str()),
        ("Report", report_source.report_hash.as_str()),
        ("Document", report_source.document_source_hash.as_str()),
        ("Request", source.identity.request_hash.as_str()),
        ("Model", source.identity.model_hash.as_str()),
        ("State", source.identity.state_hash.as_str()),
        ("Execution", source.identity.execution_hash.as_str()),
        ("Checkpoint", source.identity.checkpoint_hash.as_str()),
    ];
    for (index, (label, hash)) in provenance.iter().enumerate() {
        let index = u32::try_from(index).map_err(|_| {
            pdf_error(
                "pdf_layout_overflow",
                "provenance row index exceeded the bounded page layout",
            )
        })?;
        let y = 480.0 - f64::from(index) * 20.0;
        text_line(&mut content, "F2", 7.2, 0.29, 0.35, 0.43, 66.0, y, label)?;
        text_line(&mut content, "F3", 7.2, 0.08, 0.12, 0.18, 126.0, y, hash)?;
    }

    panel(&mut content, 48.0, 170.0, 499.0, 120.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        264.0,
        "Execution receipt",
    )?;
    label_value(&mut content, 66.0, 239.0, "Backend", "cpu / fp64")?;
    label_value(
        &mut content,
        66.0,
        219.0,
        "Determinism",
        "serial_fixed_order",
    )?;
    label_value(&mut content, 66.0, 199.0, "Fallback count", "0")?;

    text_line(
        &mut content,
        "F2",
        9.0,
        0.55,
        0.16,
        0.10,
        48.0,
        136.0,
        "Authority boundary",
    )?;
    text_line(
        &mut content,
        "F1",
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        119.0,
        "Bounded candidate result. Not engineering acceptance or design-code compliance.",
    )?;
    text_line(
        &mut content,
        "F1",
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        103.0,
        "Verify the ResultIR, ReportIR and receipt hashes before review or redistribution.",
    )?;
    writeln!(&mut content, "0.78 0.81 0.85 RG 0.5 w 48 72 m 547 72 l S")
        .expect("String writes cannot fail");
    text_line(
        &mut content,
        "F1",
        7.5,
        0.42,
        0.46,
        0.52,
        48.0,
        54.0,
        "structural-native / report-pdf.v1",
    )?;
    text_line(
        &mut content,
        "F1",
        7.5,
        0.42,
        0.46,
        0.52,
        505.0,
        54.0,
        "Page 1 / 1",
    )?;

    let content_bytes = content.into_bytes();
    let content_object = format!("<< /Length {} >>\nstream\n", content_bytes.len())
        .into_bytes()
        .into_iter()
        .chain(content_bytes)
        .chain(b"endstream\n".iter().copied())
        .collect::<Vec<_>>();
    let title = pdf_literal("Structural Analysis Report")?;
    let subject = pdf_literal("Bounded nonlinear NDTHA deterministic report")?;
    let producer = pdf_literal("structural-report 0.1.0 native PDF renderer")?;
    let objects = vec![
        b"<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /DisplayDocTitle true >> >>\n".to_vec(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n".to_vec(),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R >> >> /Contents 4 0 R >>\n".to_vec(),
        content_object,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\n".to_vec(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\n".to_vec(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>\n".to_vec(),
        format!("<< /Title ({title}) /Subject ({subject}) /Creator ({producer}) /Producer ({producer}) /Trapped /False >>\n").into_bytes(),
    ];
    assemble_pdf(&objects, result.result_hash())
}

#[allow(clippy::too_many_lines)]
fn build_sparse_linear_pdf_bytes(
    result: &SparseLinearResultIrDocumentV1,
    report: &SparseLinearReportIrDocumentV1,
) -> Result<Vec<u8>, PdfRenderError> {
    let source = result.result();
    let report_source = report.report();
    let case_id = pdf_literal(&source.case_id)?;

    let mut content = String::new();
    writeln!(&mut content, "q").expect("String writes cannot fail");
    writeln!(&mut content, "0.055 0.118 0.204 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 742 595 100 re f").expect("String writes cannot fail");
    writeln!(&mut content, "0.129 0.588 0.953 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 734 595 8 re f").expect("String writes cannot fail");
    writeln!(&mut content, "Q").expect("String writes cannot fail");
    text_line(
        &mut content,
        "F2",
        21.0,
        1.0,
        1.0,
        1.0,
        48.0,
        794.0,
        "Structural Analysis Report",
    )?;
    text_line(
        &mut content,
        "F1",
        10.0,
        0.82,
        0.88,
        0.95,
        48.0,
        773.0,
        "Bounded sparse linear static - deterministic native PDF v1",
    )?;

    panel(&mut content, 48.0, 550.0, 499.0, 154.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        678.0,
        "Analysis summary",
    )?;
    label_value(&mut content, 66.0, 653.0, "Case", &case_id)?;
    label_value(
        &mut content,
        66.0,
        633.0,
        "Matrix order",
        &source.summary.order.to_string(),
    )?;
    label_value(
        &mut content,
        66.0,
        613.0,
        "Canonical nonzeros",
        &source.summary.nonzero_count.to_string(),
    )?;
    label_value(
        &mut content,
        66.0,
        593.0,
        "PCG iterations",
        &source.summary.iterations.to_string(),
    )?;
    label_value(
        &mut content,
        66.0,
        573.0,
        "Final residual infinity norm",
        &format!("{:.8e}", source.summary.final_residual_inf),
    )?;

    panel(&mut content, 48.0, 315.0, 499.0, 215.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        504.0,
        "Provenance",
    )?;
    let provenance = [
        ("Result", source.result_hash.as_str()),
        ("Report", report_source.report_hash.as_str()),
        ("Document", report_source.document_source_hash.as_str()),
        ("Request", source.identity.request_hash.as_str()),
        ("Model", source.identity.model_hash.as_str()),
        ("State", source.identity.state_hash.as_str()),
        ("Execution", source.identity.execution_hash.as_str()),
        ("Checkpoint", source.identity.checkpoint_hash.as_str()),
    ];
    for (index, (label, hash)) in provenance.iter().enumerate() {
        let index = u32::try_from(index).map_err(|_| {
            pdf_error(
                "pdf_layout_overflow",
                "provenance row index exceeded the bounded page layout",
            )
        })?;
        let y = 480.0 - f64::from(index) * 20.0;
        text_line(&mut content, "F2", 7.2, 0.29, 0.35, 0.43, 66.0, y, label)?;
        text_line(&mut content, "F3", 7.2, 0.08, 0.12, 0.18, 126.0, y, hash)?;
    }

    panel(&mut content, 48.0, 170.0, 499.0, 120.0)?;
    text_line(
        &mut content,
        "F2",
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        264.0,
        "Execution receipt",
    )?;
    label_value(&mut content, 66.0, 239.0, "Backend", "cpu / fp64")?;
    label_value(
        &mut content,
        66.0,
        219.0,
        "Determinism",
        &source.backend_receipt.deterministic_policy,
    )?;
    label_value(
        &mut content,
        66.0,
        199.0,
        "Fallback count",
        &source.backend_receipt.fallback_count.to_string(),
    )?;

    text_line(
        &mut content,
        "F2",
        9.0,
        0.55,
        0.16,
        0.10,
        48.0,
        136.0,
        "Authority boundary",
    )?;
    text_line(
        &mut content,
        "F1",
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        119.0,
        "Bounded CPU candidate. Not engineering acceptance or design-code compliance.",
    )?;
    text_line(
        &mut content,
        "F1",
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        103.0,
        "Verify ResultIR, recovery, ReportIR and receipt hashes before redistribution.",
    )?;
    writeln!(&mut content, "0.78 0.81 0.85 RG 0.5 w 48 72 m 547 72 l S")
        .expect("String writes cannot fail");
    text_line(
        &mut content,
        "F1",
        7.5,
        0.42,
        0.46,
        0.52,
        48.0,
        54.0,
        "structural-native / sparse-report-pdf.v1",
    )?;
    text_line(
        &mut content,
        "F1",
        7.5,
        0.42,
        0.46,
        0.52,
        505.0,
        54.0,
        "Page 1 / 1",
    )?;

    let content_bytes = content.into_bytes();
    let content_object = format!("<< /Length {} >>\nstream\n", content_bytes.len())
        .into_bytes()
        .into_iter()
        .chain(content_bytes)
        .chain(b"endstream\n".iter().copied())
        .collect::<Vec<_>>();
    let title = pdf_literal("Structural Analysis Report")?;
    let subject = pdf_literal("Bounded sparse linear deterministic report")?;
    let producer = pdf_literal("structural-report 0.1.0 native PDF renderer")?;
    let objects = vec![
        b"<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /DisplayDocTitle true >> >>\n".to_vec(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n".to_vec(),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R /F2 6 0 R /F3 7 0 R >> >> /Contents 4 0 R >>\n".to_vec(),
        content_object,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\n".to_vec(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>\n".to_vec(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>\n".to_vec(),
        format!("<< /Title ({title}) /Subject ({subject}) /Creator ({producer}) /Producer ({producer}) /Trapped /False >>\n").into_bytes(),
    ];
    assemble_pdf(&objects, result.result_hash())
}

fn assemble_pdf(objects: &[Vec<u8>], identity: &str) -> Result<Vec<u8>, PdfRenderError> {
    if objects.len() != 8 || identity.len() != 71 {
        return Err(pdf_error(
            "pdf_object_contract_invalid",
            "PDF object count or source identity is outside the fixed v1 contract",
        ));
    }
    let mut output = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n".to_vec();
    let mut offsets = Vec::with_capacity(objects.len());
    for (index, object) in objects.iter().enumerate() {
        offsets.push(output.len());
        let object_id = index + 1;
        output.extend_from_slice(format!("{object_id} 0 obj\n").as_bytes());
        output.extend_from_slice(object);
        output.extend_from_slice(b"endobj\n");
    }
    let xref_offset = output.len();
    output.extend_from_slice(format!("xref\n0 {}\n", objects.len() + 1).as_bytes());
    output.extend_from_slice(b"0000000000 65535 f \n");
    for offset in offsets {
        if offset > 9_999_999_999 {
            return Err(pdf_error(
                "pdf_offset_overflow",
                "PDF object offset exceeds the fixed ten-digit xref contract",
            ));
        }
        output.extend_from_slice(format!("{offset:010} 00000 n \n").as_bytes());
    }
    let document_id = &identity[7..39];
    output.extend_from_slice(
        format!(
            "trailer\n<< /Size {} /Root 1 0 R /Info 8 0 R /ID [<{document_id}> <{document_id}>] >>\nstartxref\n{xref_offset}\n%%EOF\n",
            objects.len() + 1
        )
        .as_bytes(),
    );
    Ok(output)
}

#[allow(clippy::too_many_arguments)]
fn text_line(
    content: &mut String,
    font: &str,
    size: f64,
    red: f64,
    green: f64,
    blue: f64,
    x: f64,
    y: f64,
    text: &str,
) -> Result<(), PdfRenderError> {
    let text = pdf_literal(text)?;
    writeln!(
        content,
        "BT /{font} {size:.1} Tf {red:.3} {green:.3} {blue:.3} rg 1 0 0 1 {x:.1} {y:.1} Tm ({text}) Tj ET"
    )
    .expect("String writes cannot fail");
    Ok(())
}

fn label_value(
    content: &mut String,
    x: f64,
    y: f64,
    label: &str,
    value: &str,
) -> Result<(), PdfRenderError> {
    text_line(content, "F2", 8.5, 0.36, 0.41, 0.48, x, y, label)?;
    text_line(content, "F1", 9.5, 0.08, 0.12, 0.18, x + 142.0, y, value)
}

fn panel(
    content: &mut String,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> Result<(), PdfRenderError> {
    for value in [x, y, width, height] {
        if !value.is_finite() || value < 0.0 {
            return Err(pdf_error(
                "pdf_layout_invalid",
                "PDF panel coordinate is outside the bounded page layout",
            ));
        }
    }
    writeln!(
        content,
        "q 0.965 0.973 0.984 rg {x:.1} {y:.1} {width:.1} {height:.1} re f 0.82 0.86 0.91 RG 0.6 w {x:.1} {y:.1} {width:.1} {height:.1} re S Q"
    )
    .expect("String writes cannot fail");
    Ok(())
}

fn pdf_literal(value: &str) -> Result<String, PdfRenderError> {
    if value.bytes().any(|byte| !(b' '..=b'~').contains(&byte)) {
        return Err(pdf_error(
            "pdf_text_encoding_unsupported",
            "PDF v1 text must be printable ASCII",
        ));
    }
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        if matches!(character, '\\' | '(' | ')') {
            escaped.push('\\');
        }
        escaped.push(character);
    }
    Ok(escaped)
}

fn find_last(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .rposition(|window| window == needle)
}

fn read_line<'a>(bytes: &'a [u8], cursor: &mut usize) -> Option<&'a [u8]> {
    let relative = bytes
        .get(*cursor..)?
        .iter()
        .position(|byte| *byte == b'\n')?;
    let end = cursor.checked_add(relative)?;
    let line = bytes.get(*cursor..end)?;
    *cursor = end.checked_add(1)?;
    Some(line)
}

fn parse_usize(bytes: &[u8]) -> Option<usize> {
    if bytes.is_empty() || bytes.iter().any(|byte| !byte.is_ascii_digit()) {
        return None;
    }
    std::str::from_utf8(bytes).ok()?.parse().ok()
}

fn binding_error(code: &str, path: &str, detail: &str) -> PdfRenderError {
    PdfRenderError::Binding {
        code: code.to_owned(),
        path: path.to_owned(),
        detail: detail.to_owned(),
    }
}

fn pdf_error(code: &str, detail: &str) -> PdfRenderError {
    PdfRenderError::Pdf {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn literal_escaping_is_ascii_and_pdf_safe() {
        assert_eq!(
            super::pdf_literal(r"a(b)\c").expect("literal"),
            r"a\(b\)\\c"
        );
        assert!(super::pdf_literal("non-ascii: 한").is_err());
    }

    #[test]
    fn decimal_parser_rejects_signs_and_empty_values() {
        assert_eq!(super::parse_usize(b"0012"), Some(12));
        assert_eq!(super::parse_usize(b""), None);
        assert_eq!(super::parse_usize(b"-1"), None);
    }
}
