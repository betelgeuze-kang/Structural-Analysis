use std::fmt::Write as _;

use structural_contracts::external_comparison::{
    ExternalComparisonStatusV1, ExternalEvidenceKindV1, ExternalSolverFamilyV1,
};
use structural_contracts::model_linear_comparison::ModelIrLinearExternalComparisonIrV1;

use crate::{WorkbenchError, WorkbenchReportLocaleV1};

pub(crate) const HTML_REPORT_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-html-report.v1";
pub(crate) const HTML_REPORT_RECEIPT_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-html-report-receipt.v1";
pub(crate) const HTML_REPORT_CLAIM_BOUNDARY_V1: &str = "deterministic_standalone_html_projection_of_verified_model_ir_linear_summary_displacements_reactions_element_forces_and_external_comparison_not_complete_schedules_html_accessibility_certification_engineering_acceptance_or_design_code_compliance";

const MAXIMUM_HTML_BYTES: usize = 16 * 1024 * 1024;

pub(crate) struct HtmlReportInputV1<'a> {
    pub locale: WorkbenchReportLocaleV1,
    pub model_id: &'a str,
    pub case_id: &'a str,
    pub summary_text: &'a str,
    pub displacement_text: &'a str,
    pub reaction_text: Option<&'a str>,
    pub element_recovery_text: &'a str,
    pub comparison: &'a ModelIrLinearExternalComparisonIrV1,
}

/// Render one deterministic, standalone, script-free HTML report.
#[allow(clippy::too_many_lines)]
pub(crate) fn render_model_ir_linear_html_report_v1(
    input: &HtmlReportInputV1<'_>,
) -> Result<String, WorkbenchError> {
    let labels = Labels::for_locale(input.locale);
    let comparison = input.comparison;
    let status = comparison_status(comparison.status);
    let mut html = String::with_capacity(
        input.summary_text.len()
            + input.displacement_text.len()
            + input.reaction_text.map_or(0, str::len)
            + input.element_recovery_text.len()
            + 16_384,
    );
    write!(
        html,
        "<!doctype html>\n<html lang=\"{}\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<title>{}</title>\n<style>{}</style>\n</head>\n<body>\n<main>\n<header><p class=\"eyebrow\">{}</p><h1>{}</h1><p>{}: <strong>{}</strong> · {}: <strong>{}</strong></p></header>\n<aside class=\"boundary\" aria-label=\"{}\"><strong>{}</strong><br>{}</aside>\n",
        input.locale.label(),
        escaped(labels.title),
        STYLE,
        escaped(HTML_REPORT_SCHEMA_V1),
        escaped(labels.title),
        escaped(labels.model),
        escaped(input.model_id),
        escaped(labels.case),
        escaped(input.case_id),
        escaped(labels.boundary),
        escaped(labels.boundary),
        escaped(labels.boundary_text),
    )
    .expect("writing to a String cannot fail");
    push_pre_section(&mut html, "summary", labels.summary, input.summary_text);
    push_pre_section(
        &mut html,
        "displacements",
        labels.displacements,
        input.displacement_text,
    );
    match input.reaction_text {
        Some(text) => push_pre_section(&mut html, "reactions", labels.reactions, text),
        None => {
            writeln!(
                html,
                "<section id=\"reactions\"><h2>{}</h2><p class=\"unavailable\">{}</p></section>",
                escaped(labels.reactions),
                escaped(labels.reactions_unavailable),
            )
            .expect("writing to a String cannot fail");
        }
    }
    push_pre_section(
        &mut html,
        "element-forces",
        labels.element_forces,
        input.element_recovery_text,
    );
    write!(
        html,
        "<section id=\"comparison\"><h2>{}</h2><dl class=\"facts\"><div><dt>{}</dt><dd><span class=\"status {}\">{}</span></dd></div><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd>{}</dd></div><div><dt>{}</dt><dd><code>{}</code></dd></div></dl>\n<div class=\"table-wrap\"><table><caption>{}</caption><thead><tr><th scope=\"col\">{}</th><th scope=\"col\">{}</th><th scope=\"col\">{}</th><th scope=\"col\">{}</th><th scope=\"col\">{}</th><th scope=\"col\">{}</th></tr></thead><tbody>\n",
        escaped(labels.comparison),
        escaped(labels.status),
        status,
        status,
        escaped(labels.solver),
        escaped(solver_family(comparison.source.solver_family)),
        escaped(labels.version),
        escaped(&comparison.source.solver_version),
        escaped(labels.evidence),
        escaped(evidence_kind(comparison.source.evidence_kind)),
        escaped(labels.comparison_hash),
        escaped(&comparison.comparison_hash),
        escaped(labels.comparison_rows),
        escaped(labels.observation),
        escaped(labels.location),
        escaped(labels.native),
        escaped(labels.external),
        escaped(labels.error),
        escaped(labels.within_tolerance),
    )
    .expect("writing to a String cannot fail");
    for row in &comparison.rows {
        writeln!(
            html,
            "<tr><th scope=\"row\">{}</th><td>{}</td><td><code>{:.17e} {}</code></td><td><code>{:.17e} {}</code></td><td><code>{:.17e}</code></td><td>{}</td></tr>",
            escaped(&row.observation_id),
            escaped(&row.external_location_id),
            row.native_value,
            escaped(&row.unit),
            row.external_value,
            escaped(&row.unit),
            row.absolute_error,
            if row.within_tolerance { labels.yes } else { labels.no },
        )
        .expect("writing to a String cannot fail");
    }
    write!(
        html,
        "</tbody></table></div></section>\n<footer><p>{}: <code>{}</code></p><p>{}</p></footer>\n</main>\n</body>\n</html>\n",
        escaped(labels.claim_boundary),
        escaped(HTML_REPORT_CLAIM_BOUNDARY_V1),
        escaped(labels.footer),
    )
    .expect("writing to a String cannot fail");
    if html.len() > MAXIMUM_HTML_BYTES {
        return Err(WorkbenchError::new(
            "workbench_html_report_size_invalid",
            "rendered HTML exceeds the bounded 16 MiB product limit",
        ));
    }
    Ok(html)
}

fn push_pre_section(output: &mut String, id: &str, title: &str, text: &str) {
    writeln!(
        output,
        "<section id=\"{}\"><h2>{}</h2><pre>{}</pre></section>",
        id,
        escaped(title),
        escaped(text),
    )
    .expect("writing to a String cannot fail");
}

fn escaped(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&#39;"),
            _ => escaped.push(character),
        }
    }
    escaped
}

const fn comparison_status(value: ExternalComparisonStatusV1) -> &'static str {
    match value {
        ExternalComparisonStatusV1::Passed => "passed",
        ExternalComparisonStatusV1::Diverged => "diverged",
    }
}

const fn solver_family(value: ExternalSolverFamilyV1) -> &'static str {
    match value {
        ExternalSolverFamilyV1::MidasGen => "midas_gen",
        ExternalSolverFamilyV1::OpenSees => "opensees",
        ExternalSolverFamilyV1::Calculix => "calculix",
        ExternalSolverFamilyV1::ReferenceOracle => "reference_oracle",
    }
}

const fn evidence_kind(value: ExternalEvidenceKindV1) -> &'static str {
    match value {
        ExternalEvidenceKindV1::LiveExternalExecution => "live_external_execution",
        ExternalEvidenceKindV1::LanguageNeutralGolden => "language_neutral_golden",
        ExternalEvidenceKindV1::Proxy => "proxy",
    }
}

struct Labels {
    title: &'static str,
    model: &'static str,
    case: &'static str,
    boundary: &'static str,
    boundary_text: &'static str,
    summary: &'static str,
    displacements: &'static str,
    reactions: &'static str,
    reactions_unavailable: &'static str,
    element_forces: &'static str,
    comparison: &'static str,
    status: &'static str,
    solver: &'static str,
    version: &'static str,
    evidence: &'static str,
    comparison_hash: &'static str,
    comparison_rows: &'static str,
    observation: &'static str,
    location: &'static str,
    native: &'static str,
    external: &'static str,
    error: &'static str,
    within_tolerance: &'static str,
    yes: &'static str,
    no: &'static str,
    claim_boundary: &'static str,
    footer: &'static str,
}

impl Labels {
    const fn for_locale(locale: WorkbenchReportLocaleV1) -> Self {
        match locale {
            WorkbenchReportLocaleV1::EnUs => Self {
                title: "Structural ModelIR Linear Workbench Report",
                model: "Model",
                case: "Case",
                boundary: "Authority boundary",
                boundary_text: "Verified deterministic candidate evidence. This report is not an engineering verdict, design-code check, commercial-solver certification, or release approval.",
                summary: "Analysis summary and identities",
                displacements: "Nodal displacements",
                reactions: "Constrained reactions",
                reactions_unavailable: "Unavailable in this legacy artifact set.",
                element_forces: "Member forces and element recovery",
                comparison: "External comparison",
                status: "Status",
                solver: "Solver family",
                version: "Version",
                evidence: "Evidence kind",
                comparison_hash: "Comparison hash",
                comparison_rows: "Bounded external comparison observations",
                observation: "Observation",
                location: "Location",
                native: "Native",
                external: "External",
                error: "Absolute error",
                within_tolerance: "Within tolerance",
                yes: "yes",
                no: "no",
                claim_boundary: "Claim boundary",
                footer: "The canonical JSON artifacts and receipt hashes remain authoritative; presentation does not alter the analysis.",
            },
            WorkbenchReportLocaleV1::KoKr => Self {
                title: "구조 ModelIR 선형 Workbench 보고서",
                model: "모델",
                case: "해석 사례",
                boundary: "권한 경계",
                boundary_text: "검증된 결정론적 후보 증거입니다. 공학적 판정, 설계기준 검토, 상용 솔버 인증 또는 출시 승인을 의미하지 않습니다.",
                summary: "해석 요약 및 식별자",
                displacements: "절점 변위",
                reactions: "구속 반력",
                reactions_unavailable: "기존 산출물 세트에는 없습니다.",
                element_forces: "부재력 및 요소 복원",
                comparison: "외부 비교",
                status: "상태",
                solver: "솔버 계열",
                version: "버전",
                evidence: "증거 종류",
                comparison_hash: "비교 해시",
                comparison_rows: "제한된 외부 비교 관측값",
                observation: "관측값",
                location: "위치",
                native: "네이티브",
                external: "외부",
                error: "절대 오차",
                within_tolerance: "허용오차 이내",
                yes: "예",
                no: "아니요",
                claim_boundary: "주장 경계",
                footer: "정규 JSON 산출물과 영수증 해시가 권위 있는 원본이며, 표시는 해석 결과를 변경하지 않습니다.",
            },
        }
    }
}

const STYLE: &str = "*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#17212b;font-family:system-ui,-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif;line-height:1.5}main{max-width:1200px;margin:auto;padding:32px}header,section,aside,footer{background:#fff;border:1px solid #d9e0e7;border-radius:10px;margin:0 0 20px;padding:24px}h1,h2{line-height:1.2}h1{margin:.2rem 0 1rem}h2{margin-top:0}.eyebrow{color:#496579;font-size:.8rem;letter-spacing:.05em}.boundary{border-left:6px solid #b66b00;background:#fff8e8}.facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}.facts div{background:#f6f8fa;padding:12px}.facts dt{font-size:.8rem;color:#52606d}.facts dd{margin:4px 0 0}.status{font-weight:700}.status.passed{color:#176b35}.status.diverged{color:#9c2f24}pre{overflow:auto;padding:16px;background:#101820;color:#f1f5f8;border-radius:6px;font:12px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;min-width:760px}caption{text-align:left;font-weight:600;margin:16px 0 8px}th,td{border:1px solid #d9e0e7;padding:8px;text-align:left;vertical-align:top}thead{background:#edf2f6}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}.unavailable{color:#6b7280}@media print{body{background:#fff}main{max-width:none;padding:0}header,section,aside,footer{break-inside:avoid;border-color:#aaa}pre{white-space:pre-wrap;color:#000;background:#f7f7f7}}";

#[cfg(test)]
mod tests {
    use super::escaped;

    #[test]
    fn html_escape_covers_markup_and_attribute_delimiters() {
        assert_eq!(escaped("<&>\"' 안전"), "&lt;&amp;&gt;&quot;&#39; 안전");
    }
}
