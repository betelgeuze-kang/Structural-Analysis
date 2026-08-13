use std::fmt::Write as _;

use structural_contracts::product_ir::{
    sha256_identity, NonlinearNdthaReportIrDocumentV1, NonlinearNdthaResultIrDocumentV1,
    NonlinearNdthaTerminalStatusV1,
};

use crate::localized_font::{
    LOCALIZED_FONT_BYTES, LOCALIZED_FONT_BYTE_LENGTH, LOCALIZED_FONT_GLYPHS,
    LOCALIZED_FONT_GLYPH_COUNT, LOCALIZED_FONT_HASH, LOCALIZED_FONT_LICENSE_NOTICE_BYTES,
    LOCALIZED_FONT_LICENSE_NOTICE_BYTE_LENGTH, LOCALIZED_FONT_LICENSE_NOTICE_HASH,
    LOCALIZED_FONT_POSTSCRIPT_NAME, LOCALIZED_FONT_PROVENANCE_BYTES,
    LOCALIZED_FONT_PROVENANCE_BYTE_LENGTH, LOCALIZED_FONT_PROVENANCE_HASH,
};
use crate::{build_nonlinear_ndtha_report_v1, PdfRenderError};

const PDF_MEDIA_TYPE: &str = "application/pdf";
const PDF_CLAIM_BOUNDARY: &str = "deterministic_single_page_embedded_font_projection_for_fixed_en_us_or_ko_kr_labels_and_portable_ascii_dynamic_values_not_arbitrary_unicode_pdf_ua_accessibility_engineering_acceptance_or_design_code_compliance";
const OBJECT_COUNT: usize = 10;
const INFO_OBJECT_ID: usize = 10;

/// Explicit locale profiles supported by the bounded embedded-font PDF renderer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PdfReportLocaleV2 {
    EnUs,
    KoKr,
}

impl PdfReportLocaleV2 {
    #[must_use]
    pub fn language_tag(self) -> &'static str {
        match self {
            Self::EnUs => "en-US",
            Self::KoKr => "ko-KR",
        }
    }

    #[must_use]
    pub fn from_language_tag(value: &str) -> Option<Self> {
        match value {
            "en-US" => Some(Self::EnUs),
            "ko-KR" => Some(Self::KoKr),
            _ => None,
        }
    }
}

/// Exact localized PDF bytes plus every source and embedded-asset identity needed by a receipt.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NonlinearNdthaLocalizedPdfDocumentV2 {
    bytes: Vec<u8>,
    locale: PdfReportLocaleV2,
    source_result_hash: String,
    source_report_hash: String,
    document_source_hash: String,
    pdf_hash: String,
}

impl NonlinearNdthaLocalizedPdfDocumentV2 {
    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.bytes
    }

    #[must_use]
    pub fn media_type(&self) -> &'static str {
        PDF_MEDIA_TYPE
    }

    #[must_use]
    pub fn locale(&self) -> PdfReportLocaleV2 {
        self.locale
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
    pub fn embedded_font_hash(&self) -> &'static str {
        LOCALIZED_FONT_HASH
    }

    #[must_use]
    pub fn embedded_font_byte_length(&self) -> usize {
        LOCALIZED_FONT_BYTE_LENGTH
    }

    #[must_use]
    pub fn embedded_font_postscript_name(&self) -> &'static str {
        LOCALIZED_FONT_POSTSCRIPT_NAME
    }

    #[must_use]
    pub fn embedded_font_license_notice_hash(&self) -> &'static str {
        LOCALIZED_FONT_LICENSE_NOTICE_HASH
    }

    #[must_use]
    pub fn embedded_font_license_notice_byte_length(&self) -> usize {
        LOCALIZED_FONT_LICENSE_NOTICE_BYTE_LENGTH
    }

    #[must_use]
    pub fn embedded_font_provenance_hash(&self) -> &'static str {
        LOCALIZED_FONT_PROVENANCE_HASH
    }

    #[must_use]
    pub fn embedded_font_provenance_byte_length(&self) -> usize {
        LOCALIZED_FONT_PROVENANCE_BYTE_LENGTH
    }

    #[must_use]
    pub fn claim_boundary(&self) -> &'static str {
        PDF_CLAIM_BOUNDARY
    }
}

/// Render one deterministic localized PDF using only the vendored TrueType subset.
///
/// The exact v1 `ResultIR`, `ReportIR`, and Markdown binding remains authoritative. Only fixed
/// English or Korean presentation labels are localized; dynamic identifiers remain printable
/// ASCII. No host font, renderer process, Python, Node, browser, or network access is used.
///
/// # Errors
///
/// Rejects projection drift, unsupported locale text, non-portable dynamic identifiers, embedded
/// font identity drift, PDF construction overflow, and malformed generated object tables.
pub fn render_nonlinear_ndtha_localized_pdf_v2(
    result: &NonlinearNdthaResultIrDocumentV1,
    report: &NonlinearNdthaReportIrDocumentV1,
    document_source: &[u8],
    locale: PdfReportLocaleV2,
) -> Result<NonlinearNdthaLocalizedPdfDocumentV2, PdfRenderError> {
    verify_exact_projection(result, report, document_source)?;
    verify_font_asset()?;
    require_portable_dynamic_text(&result.result().case_id, "/result_ir/case_id")?;
    let bytes = build_pdf_bytes(result, report, locale)?;
    validate_deterministic_localized_pdf_v2(&bytes)?;
    Ok(NonlinearNdthaLocalizedPdfDocumentV2 {
        pdf_hash: sha256_identity(&bytes),
        source_result_hash: result.result_hash().to_owned(),
        source_report_hash: report.report_hash().to_owned(),
        document_source_hash: sha256_identity(document_source),
        locale,
        bytes,
    })
}

/// Validate the fixed localized PDF object graph, embedded font, `ToUnicode` map, and xref offsets.
///
/// # Errors
///
/// Returns a stable PDF error for truncation, font substitution, malformed offsets, missing
/// Unicode extraction metadata, or fixed-object-graph drift.
pub fn validate_deterministic_localized_pdf_v2(bytes: &[u8]) -> Result<(), PdfRenderError> {
    validate_fixed_object_graph(bytes)?;
    for marker in [
        b"/Subtype /Type0".as_slice(),
        b"/Encoding /Identity-H".as_slice(),
        b"/CIDToGIDMap /Identity".as_slice(),
        b"/ToUnicode 9 0 R".as_slice(),
        b"/FontFile2 8 0 R".as_slice(),
        b"begincodespacerange".as_slice(),
        b"beginbfchar".as_slice(),
        b"<0060> <AC04>".as_slice(),
    ] {
        if find_bytes(bytes, marker).is_none() {
            return Err(pdf_error(
                "pdf_localized_structure_invalid",
                "localized PDF font or ToUnicode marker is missing",
            ));
        }
    }
    let font_stream_prefix = format!(
        "8 0 obj\n<< /Length {LOCALIZED_FONT_BYTE_LENGTH} /Length1 {LOCALIZED_FONT_BYTE_LENGTH} >>\nstream\n"
    );
    let prefix_position = find_bytes(bytes, font_stream_prefix.as_bytes()).ok_or_else(|| {
        pdf_error(
            "pdf_embedded_font_invalid",
            "localized PDF embedded font stream declaration is missing",
        )
    })?;
    let font_start = prefix_position
        .checked_add(font_stream_prefix.len())
        .ok_or_else(|| pdf_error("pdf_embedded_font_invalid", "font stream offset overflowed"))?;
    let font_end = font_start
        .checked_add(LOCALIZED_FONT_BYTE_LENGTH)
        .filter(|end| *end <= bytes.len())
        .ok_or_else(|| {
            pdf_error(
                "pdf_embedded_font_invalid",
                "localized PDF embedded font stream is truncated",
            )
        })?;
    if bytes.get(font_start..font_end) != Some(LOCALIZED_FONT_BYTES) {
        return Err(pdf_error(
            "pdf_embedded_font_invalid",
            "localized PDF embedded font bytes do not match the vendored asset",
        ));
    }
    Ok(())
}

fn verify_exact_projection(
    result: &NonlinearNdthaResultIrDocumentV1,
    report: &NonlinearNdthaReportIrDocumentV1,
    document_source: &[u8],
) -> Result<(), PdfRenderError> {
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
    Ok(())
}

fn verify_font_asset() -> Result<(), PdfRenderError> {
    if LOCALIZED_FONT_BYTES.len() != LOCALIZED_FONT_BYTE_LENGTH
        || sha256_identity(LOCALIZED_FONT_BYTES) != LOCALIZED_FONT_HASH
        || LOCALIZED_FONT_LICENSE_NOTICE_BYTES.len() != LOCALIZED_FONT_LICENSE_NOTICE_BYTE_LENGTH
        || sha256_identity(LOCALIZED_FONT_LICENSE_NOTICE_BYTES)
            != LOCALIZED_FONT_LICENSE_NOTICE_HASH
        || LOCALIZED_FONT_PROVENANCE_BYTES.len() != LOCALIZED_FONT_PROVENANCE_BYTE_LENGTH
        || sha256_identity(LOCALIZED_FONT_PROVENANCE_BYTES) != LOCALIZED_FONT_PROVENANCE_HASH
        || LOCALIZED_FONT_GLYPHS.len() != LOCALIZED_FONT_GLYPH_COUNT
    {
        return Err(pdf_error(
            "pdf_embedded_font_identity_mismatch",
            "vendored localized font bytes or generated glyph inventory drifted",
        ));
    }
    for (index, (character, glyph_id, width)) in LOCALIZED_FONT_GLYPHS.iter().enumerate() {
        let expected_id = u16::try_from(index + 1).map_err(|_| {
            pdf_error(
                "pdf_embedded_font_inventory_invalid",
                "localized font glyph inventory exceeded its bounded id space",
            )
        })?;
        if *glyph_id != expected_id
            || *width == 0
            || index > 0 && *character <= LOCALIZED_FONT_GLYPHS[index - 1].0
        {
            return Err(pdf_error(
                "pdf_embedded_font_inventory_invalid",
                "localized font glyph ids, widths, or Unicode ordering are invalid",
            ));
        }
    }
    Ok(())
}

struct Labels {
    title: &'static str,
    subtitle: &'static str,
    summary: &'static str,
    case_id: &'static str,
    terminal_status: &'static str,
    completed_steps: &'static str,
    maximum_drift: &'static str,
    residual_displacement: &'static str,
    provenance: &'static str,
    provenance_headings: [&'static str; 8],
    execution_receipt: &'static str,
    backend: &'static str,
    determinism: &'static str,
    fallback_count: &'static str,
    authority_boundary: &'static str,
    boundary_line_one: &'static str,
    boundary_line_two: &'static str,
    footer: &'static str,
    page: &'static str,
    completed: &'static str,
    collapsed: &'static str,
}

fn labels(locale: PdfReportLocaleV2) -> Labels {
    match locale {
        PdfReportLocaleV2::EnUs => Labels {
            title: "Structural Analysis Report",
            subtitle: "Bounded nonlinear NDTHA - deterministic native PDF v2",
            summary: "Analysis summary",
            case_id: "Case",
            terminal_status: "Terminal status",
            completed_steps: "Completed steps",
            maximum_drift: "Maximum drift ratio",
            residual_displacement: "Residual top displacement",
            provenance: "Provenance",
            provenance_headings: [
                "Result",
                "Report",
                "Document",
                "Request",
                "Model",
                "State",
                "Execution",
                "Checkpoint",
            ],
            execution_receipt: "Execution receipt",
            backend: "Backend",
            determinism: "Determinism",
            fallback_count: "Fallback count",
            authority_boundary: "Authority boundary",
            boundary_line_one:
                "Bounded candidate result. Not engineering acceptance or design-code compliance.",
            boundary_line_two:
                "Verify the ResultIR, ReportIR and receipt hashes before review or redistribution.",
            footer: "structural-native / report-pdf.v2 / en-US",
            page: "Page 1 / 1",
            completed: "completed",
            collapsed: "collapsed",
        },
        PdfReportLocaleV2::KoKr => Labels {
            title: "구조 해석 보고서",
            subtitle: "제한된 비선형 시간이력해석 결정론적 네이티브 PDF v2",
            summary: "해석 요약",
            case_id: "케이스",
            terminal_status: "종료 상태",
            completed_steps: "완료 단계",
            maximum_drift: "최대 층간변위비",
            residual_displacement: "잔류 최상층 변위",
            provenance: "출처",
            provenance_headings: [
                "결과",
                "보고서",
                "문서",
                "요청",
                "모델",
                "상태",
                "실행",
                "체크포인트",
            ],
            execution_receipt: "실행 영수증",
            backend: "백엔드",
            determinism: "결정론",
            fallback_count: "폴백 횟수",
            authority_boundary: "권한 경계",
            boundary_line_one: "제한된 후보 결과. 공학적 승인 또는 설계 기준 적합성 인증이 아님.",
            boundary_line_two:
                "검토 또는 재배포 전에 결과 보고서 문서와 영수증 해시를 확인하십시오.",
            footer: "구조 네이티브 / report-pdf.v2 / ko-KR",
            page: "페이지 1 / 1",
            completed: "완료",
            collapsed: "붕괴",
        },
    }
}

#[allow(clippy::too_many_lines)]
fn build_pdf_bytes(
    result: &NonlinearNdthaResultIrDocumentV1,
    report: &NonlinearNdthaReportIrDocumentV1,
    locale: PdfReportLocaleV2,
) -> Result<Vec<u8>, PdfRenderError> {
    let source = result.result();
    let report_source = report.report();
    let labels = labels(locale);
    let terminal_status = match source.summary.terminal_status {
        NonlinearNdthaTerminalStatusV1::Completed => labels.completed,
        NonlinearNdthaTerminalStatusV1::Collapsed => labels.collapsed,
    };

    let mut content = String::new();
    writeln!(&mut content, "q").expect("String writes cannot fail");
    writeln!(&mut content, "0.055 0.118 0.204 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 742 595 100 re f").expect("String writes cannot fail");
    writeln!(&mut content, "0.129 0.588 0.953 rg").expect("String writes cannot fail");
    writeln!(&mut content, "0 734 595 8 re f").expect("String writes cannot fail");
    writeln!(&mut content, "Q").expect("String writes cannot fail");
    text_line(&mut content, 21.0, 1.0, 1.0, 1.0, 48.0, 794.0, labels.title)?;
    text_line(
        &mut content,
        10.0,
        0.82,
        0.88,
        0.95,
        48.0,
        773.0,
        labels.subtitle,
    )?;

    panel(&mut content, 48.0, 550.0, 499.0, 154.0)?;
    text_line(
        &mut content,
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        678.0,
        labels.summary,
    )?;
    label_value(&mut content, 66.0, 653.0, labels.case_id, &source.case_id)?;
    label_value(
        &mut content,
        66.0,
        633.0,
        labels.terminal_status,
        terminal_status,
    )?;
    label_value(
        &mut content,
        66.0,
        613.0,
        labels.completed_steps,
        &source.summary.step_count_completed.to_string(),
    )?;
    label_value(
        &mut content,
        66.0,
        593.0,
        labels.maximum_drift,
        &format!("{:.8e} percent", source.summary.max_drift_ratio_pct),
    )?;
    label_value(
        &mut content,
        66.0,
        573.0,
        labels.residual_displacement,
        &format!("{:.8e} m", source.summary.residual_top_displacement_m),
    )?;

    panel(&mut content, 48.0, 315.0, 499.0, 215.0)?;
    text_line(
        &mut content,
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        504.0,
        labels.provenance,
    )?;
    let provenance = [
        source.result_hash.as_str(),
        report_source.report_hash.as_str(),
        report_source.document_source_hash.as_str(),
        source.identity.request_hash.as_str(),
        source.identity.model_hash.as_str(),
        source.identity.state_hash.as_str(),
        source.identity.execution_hash.as_str(),
        source.identity.checkpoint_hash.as_str(),
    ];
    for (index, (label, hash)) in labels
        .provenance_headings
        .iter()
        .zip(provenance.iter())
        .enumerate()
    {
        let index = u32::try_from(index).map_err(|_| {
            pdf_error(
                "pdf_layout_overflow",
                "provenance row index exceeded the bounded page layout",
            )
        })?;
        let y = 480.0 - f64::from(index) * 20.0;
        text_line(&mut content, 7.2, 0.29, 0.35, 0.43, 66.0, y, label)?;
        text_line(&mut content, 7.2, 0.08, 0.12, 0.18, 126.0, y, hash)?;
    }

    panel(&mut content, 48.0, 170.0, 499.0, 120.0)?;
    text_line(
        &mut content,
        13.0,
        0.055,
        0.118,
        0.204,
        66.0,
        264.0,
        labels.execution_receipt,
    )?;
    label_value(&mut content, 66.0, 239.0, labels.backend, "cpu / fp64")?;
    label_value(
        &mut content,
        66.0,
        219.0,
        labels.determinism,
        "serial_fixed_order",
    )?;
    label_value(&mut content, 66.0, 199.0, labels.fallback_count, "0")?;

    text_line(
        &mut content,
        9.0,
        0.55,
        0.16,
        0.10,
        48.0,
        136.0,
        labels.authority_boundary,
    )?;
    text_line(
        &mut content,
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        119.0,
        labels.boundary_line_one,
    )?;
    text_line(
        &mut content,
        8.5,
        0.27,
        0.31,
        0.38,
        48.0,
        103.0,
        labels.boundary_line_two,
    )?;
    writeln!(&mut content, "0.78 0.81 0.85 RG 0.5 w 48 72 m 547 72 l S")
        .expect("String writes cannot fail");
    text_line(
        &mut content,
        7.5,
        0.42,
        0.46,
        0.52,
        48.0,
        54.0,
        labels.footer,
    )?;
    text_line(
        &mut content,
        7.5,
        0.42,
        0.46,
        0.52,
        505.0,
        54.0,
        labels.page,
    )?;

    let content_object = stream_object(content.as_bytes(), None);
    let widths = font_widths()?;
    let to_unicode = build_to_unicode_cmap()?;
    let font_file_object = stream_object(
        LOCALIZED_FONT_BYTES,
        Some(&format!("/Length1 {LOCALIZED_FONT_BYTE_LENGTH}")),
    );
    let to_unicode_object = stream_object(to_unicode.as_bytes(), None);
    let title = pdf_literal("Localized Structural Analysis Report")?;
    let subject = pdf_literal("Bounded nonlinear NDTHA deterministic embedded-font report")?;
    let producer = pdf_literal("structural-report 0.1.0 native localized PDF renderer")?;
    let objects = vec![
        format!(
            "<< /Type /Catalog /Pages 2 0 R /Lang ({}) /ViewerPreferences << /DisplayDocTitle true >> >>\n",
            locale.language_tag()
        )
        .into_bytes(),
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n".to_vec(),
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\n".to_vec(),
        content_object,
        format!(
            "<< /Type /Font /Subtype /Type0 /BaseFont /{LOCALIZED_FONT_POSTSCRIPT_NAME} /Encoding /Identity-H /DescendantFonts [6 0 R] /ToUnicode 9 0 R >>\n"
        )
        .into_bytes(),
        format!(
            "<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{LOCALIZED_FONT_POSTSCRIPT_NAME} /CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor 7 0 R /DW 1000 /W [1 [{widths}]] /CIDToGIDMap /Identity >>\n"
        )
        .into_bytes(),
        format!(
            "<< /Type /FontDescriptor /FontName /{LOCALIZED_FONT_POSTSCRIPT_NAME} /Flags 4 /FontBBox [9 -198 1005 785] /ItalicAngle 0 /Ascent 920 /Descent -230 /CapHeight 700 /StemV 80 /FontFile2 8 0 R >>\n"
        )
        .into_bytes(),
        font_file_object,
        to_unicode_object,
        format!("<< /Title ({title}) /Subject ({subject}) /Creator ({producer}) /Producer ({producer}) /Trapped /False >>\n").into_bytes(),
    ];
    let identity = sha256_identity(
        format!(
            "{}|{}|{}",
            result.result_hash(),
            locale.language_tag(),
            LOCALIZED_FONT_HASH
        )
        .as_bytes(),
    );
    assemble_pdf(&objects, &identity)
}

fn font_widths() -> Result<String, PdfRenderError> {
    let mut widths = String::new();
    for (index, (_, glyph_id, width)) in LOCALIZED_FONT_GLYPHS.iter().enumerate() {
        let expected_id = u16::try_from(index + 1).map_err(|_| {
            pdf_error(
                "pdf_embedded_font_inventory_invalid",
                "localized font glyph inventory exceeded its bounded id space",
            )
        })?;
        if *glyph_id != expected_id {
            return Err(pdf_error(
                "pdf_embedded_font_inventory_invalid",
                "localized font glyph ids are not contiguous",
            ));
        }
        if index > 0 {
            widths.push(' ');
        }
        write!(&mut widths, "{width}").expect("String writes cannot fail");
    }
    Ok(widths)
}

fn build_to_unicode_cmap() -> Result<String, PdfRenderError> {
    let mut cmap = String::from(
        "/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n/CMapName /StructuralReportKoreanSubset-UCS def\n/CMapType 2 def\n1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n",
    );
    for chunk in LOCALIZED_FONT_GLYPHS.chunks(100) {
        writeln!(&mut cmap, "{} beginbfchar", chunk.len()).expect("String writes cannot fail");
        for (character, glyph_id, _) in chunk {
            let codepoint = u32::from(*character);
            if codepoint > u32::from(u16::MAX) || *glyph_id == 0 {
                return Err(pdf_error(
                    "pdf_embedded_font_inventory_invalid",
                    "localized font inventory contains an unsupported Unicode scalar or glyph id",
                ));
            }
            writeln!(&mut cmap, "<{glyph_id:04X}> <{codepoint:04X}>")
                .expect("String writes cannot fail");
        }
        writeln!(&mut cmap, "endbfchar").expect("String writes cannot fail");
    }
    cmap.push_str("endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n");
    Ok(cmap)
}

#[allow(clippy::too_many_arguments)]
fn text_line(
    content: &mut String,
    size: f64,
    red: f64,
    green: f64,
    blue: f64,
    x: f64,
    y: f64,
    text: &str,
) -> Result<(), PdfRenderError> {
    let encoded = encode_text(text)?;
    writeln!(
        content,
        "BT /F1 {size:.1} Tf {red:.3} {green:.3} {blue:.3} rg 1 0 0 1 {x:.1} {y:.1} Tm <{encoded}> Tj ET"
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
    text_line(content, 8.5, 0.36, 0.41, 0.48, x, y, label)?;
    text_line(content, 9.5, 0.08, 0.12, 0.18, x + 142.0, y, value)
}

fn encode_text(value: &str) -> Result<String, PdfRenderError> {
    let mut encoded = String::with_capacity(value.chars().count() * 4);
    for character in value.chars() {
        let glyph_id = LOCALIZED_FONT_GLYPHS
            .binary_search_by_key(&character, |(candidate, _, _)| *candidate)
            .ok()
            .map(|index| LOCALIZED_FONT_GLYPHS[index].1)
            .ok_or_else(|| {
                pdf_error(
                    "pdf_text_encoding_unsupported",
                    "localized PDF text is outside the fixed embedded glyph inventory",
                )
            })?;
        write!(&mut encoded, "{glyph_id:04X}").expect("String writes cannot fail");
    }
    Ok(encoded)
}

fn require_portable_dynamic_text(value: &str, path: &str) -> Result<(), PdfRenderError> {
    if value.is_empty() || value.bytes().any(|byte| !(b' '..=b'~').contains(&byte)) {
        return Err(binding_error(
            "pdf_dynamic_text_encoding_unsupported",
            path,
            "localized PDF v2 dynamic text must be non-empty printable ASCII",
        ));
    }
    Ok(())
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

fn stream_object(bytes: &[u8], additional_dictionary: Option<&str>) -> Vec<u8> {
    let additional = additional_dictionary.map_or(String::new(), |value| format!(" {value}"));
    let mut object = format!("<< /Length {}{additional} >>\nstream\n", bytes.len()).into_bytes();
    object.extend_from_slice(bytes);
    object.extend_from_slice(b"\nendstream\n");
    object
}

fn assemble_pdf(objects: &[Vec<u8>], identity: &str) -> Result<Vec<u8>, PdfRenderError> {
    if objects.len() != OBJECT_COUNT || identity.len() != 71 || !identity.starts_with("sha256:") {
        return Err(pdf_error(
            "pdf_object_contract_invalid",
            "localized PDF object count or document identity is outside the fixed v2 contract",
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
            "trailer\n<< /Size {} /Root 1 0 R /Info {INFO_OBJECT_ID} 0 R /ID [<{document_id}> <{document_id}>] >>\nstartxref\n{xref_offset}\n%%EOF\n",
            objects.len() + 1
        )
        .as_bytes(),
    );
    Ok(output)
}

#[allow(clippy::too_many_lines)]
fn validate_fixed_object_graph(bytes: &[u8]) -> Result<(), PdfRenderError> {
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
    let xref_header = format!("xref\n0 {}\n", OBJECT_COUNT + 1);
    let xref_header_end = xref_offset
        .checked_add(xref_header.len())
        .filter(|offset| *offset <= bytes.len())
        .ok_or_else(|| {
            pdf_error(
                "pdf_xref_invalid",
                "PDF startxref offset is outside the document",
            )
        })?;
    if bytes.get(xref_offset..xref_header_end) != Some(xref_header.as_bytes()) {
        return Err(pdf_error(
            "pdf_xref_invalid",
            "PDF xref offset or fixed object count is invalid",
        ));
    }
    let mut cursor = xref_header_end;
    let free_line = read_line(bytes, &mut cursor)
        .ok_or_else(|| pdf_error("pdf_xref_invalid", "PDF free xref entry is missing"))?;
    if free_line != b"0000000000 65535 f " {
        return Err(pdf_error(
            "pdf_xref_invalid",
            "PDF free xref entry is invalid",
        ));
    }
    for object_id in 1..=OBJECT_COUNT {
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
    let info_marker = format!("/Info {INFO_OBJECT_ID} 0 R ");
    let size_marker = format!("/Size {} ", OBJECT_COUNT + 1);
    if find_bytes(trailer, b"/Root 1 0 R ").is_none()
        || find_bytes(trailer, info_marker.as_bytes()).is_none()
        || find_bytes(trailer, size_marker.as_bytes()).is_none()
    {
        return Err(pdf_error(
            "pdf_trailer_invalid",
            "PDF trailer does not bind the fixed catalog, info and object count",
        ));
    }
    Ok(())
}

fn pdf_literal(value: &str) -> Result<String, PdfRenderError> {
    if value.bytes().any(|byte| !(b' '..=b'~').contains(&byte)) {
        return Err(pdf_error(
            "pdf_metadata_encoding_unsupported",
            "localized PDF metadata must be printable ASCII",
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

fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
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
    use super::{build_to_unicode_cmap, encode_text, labels, verify_font_asset, PdfReportLocaleV2};

    #[test]
    fn vendored_font_inventory_covers_every_fixed_locale_label() {
        verify_font_asset().expect("fixed embedded font identity");
        for locale in [PdfReportLocaleV2::EnUs, PdfReportLocaleV2::KoKr] {
            let labels = labels(locale);
            for value in [
                labels.title,
                labels.subtitle,
                labels.summary,
                labels.case_id,
                labels.terminal_status,
                labels.completed_steps,
                labels.maximum_drift,
                labels.residual_displacement,
                labels.provenance,
                labels.execution_receipt,
                labels.backend,
                labels.determinism,
                labels.fallback_count,
                labels.authority_boundary,
                labels.boundary_line_one,
                labels.boundary_line_two,
                labels.footer,
                labels.page,
                labels.completed,
                labels.collapsed,
            ]
            .into_iter()
            .chain(labels.provenance_headings)
            {
                encode_text(value).expect("fixed locale label must have an embedded glyph");
            }
        }
        assert!(encode_text("unsupported emoji: 😀").is_err());
        let cmap = build_to_unicode_cmap().expect("ToUnicode CMap");
        assert!(cmap.contains("<0060> <AC04>"));
        assert!(cmap.contains(" <D574>"));
    }

    #[test]
    fn locale_tags_are_exact_and_closed() {
        assert_eq!(
            PdfReportLocaleV2::from_language_tag("en-US"),
            Some(PdfReportLocaleV2::EnUs)
        );
        assert_eq!(
            PdfReportLocaleV2::from_language_tag("ko-KR"),
            Some(PdfReportLocaleV2::KoKr)
        );
        assert_eq!(PdfReportLocaleV2::from_language_tag("ko-kr"), None);
    }
}
