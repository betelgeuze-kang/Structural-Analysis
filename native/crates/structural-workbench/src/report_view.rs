use std::fmt::Write as _;

use structural_contracts::product_ir::{
    sha256_identity, NonlinearNdthaResultIrV1, NonlinearNdthaTerminalStatusV1,
};

use crate::{WorkbenchError, WorkbenchReviewDecisionV1};

pub(crate) const LINEAR_REPORT_SCHEMA_V1: &str = "structural-native-workbench-linear-report.v1";

/// Supported deterministic operator languages for the bounded linear report view.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkbenchReportLocaleV1 {
    EnUs,
    KoKr,
}

impl WorkbenchReportLocaleV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::EnUs => "en-US",
            Self::KoKr => "ko-KR",
        }
    }

    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "en-US" => Some(Self::EnUs),
            "ko-KR" => Some(Self::KoKr),
            _ => None,
        }
    }
}

pub(crate) struct LinearReportReview<'a> {
    pub decision: WorkbenchReviewDecisionV1,
    pub reviewer: &'a str,
    pub comment: &'a str,
    pub review_hash: &'a str,
}

pub(crate) struct LinearReportInput<'a> {
    pub result: &'a NonlinearNdthaResultIrV1,
    pub report_hash: &'a str,
    pub document_hash: &'a str,
    pub comparison_passed: bool,
    pub comparison_hash: &'a str,
    pub pdf_hash: &'a str,
    pub review: Option<LinearReportReview<'a>>,
}

struct LinearReportLabels {
    title: &'static str,
    schema: &'static str,
    locale: &'static str,
    presentation: &'static str,
    summary: &'static str,
    case: &'static str,
    authority: &'static str,
    authority_value: &'static str,
    terminal_status: &'static str,
    completed_steps: &'static str,
    maximum_drift: &'static str,
    drift_unit: &'static str,
    maximum_plastic_stories: &'static str,
    residual_top_displacement: &'static str,
    backend: &'static str,
    external_comparison: &'static str,
    comparison_passed: &'static str,
    comparison_diverged: &'static str,
    provenance: &'static str,
    boundary: &'static str,
    view_hash: &'static str,
}

pub(crate) fn render_linear_report(
    locale: WorkbenchReportLocaleV1,
    input: &LinearReportInput<'_>,
) -> Result<String, WorkbenchError> {
    let result = input.result;
    let labels = report_labels(locale);
    let mut output = String::new();
    push_line(&mut output, labels.title);
    push_field(&mut output, labels.schema, LINEAR_REPORT_SCHEMA_V1);
    push_field(&mut output, labels.locale, locale.label());
    push_line(&mut output, labels.presentation);
    push_line(&mut output, "");
    push_line(&mut output, labels.summary);
    push_field(&mut output, labels.case, &result.case_id);
    push_field(&mut output, labels.authority, labels.authority_value);
    push_field(
        &mut output,
        labels.terminal_status,
        terminal_status(locale, result.summary.terminal_status),
    );
    push_field(
        &mut output,
        labels.completed_steps,
        &result.summary.step_count_completed.to_string(),
    );
    push_field(
        &mut output,
        labels.maximum_drift,
        &format!(
            "{:.17e} {}",
            result.summary.max_drift_ratio_pct, labels.drift_unit
        ),
    );
    push_field(
        &mut output,
        labels.maximum_plastic_stories,
        &result.summary.max_plastic_story_count.to_string(),
    );
    push_field(
        &mut output,
        labels.residual_top_displacement,
        &format!("{:.17e} m", result.summary.residual_top_displacement_m),
    );
    push_field(&mut output, labels.backend, "cpu / fp64 / fallback 0");
    push_field(
        &mut output,
        labels.external_comparison,
        if input.comparison_passed {
            labels.comparison_passed
        } else {
            labels.comparison_diverged
        },
    );
    push_line(&mut output, "");
    push_line(&mut output, labels.provenance);
    push_provenance(&mut output, locale, input);
    push_line(&mut output, "");
    push_review(&mut output, locale, input.review.as_ref());
    push_line(&mut output, "");
    push_line(&mut output, labels.boundary);
    let view_hash = sha256_identity(output.as_bytes());
    push_field(&mut output, labels.view_hash, &view_hash);
    if output.as_bytes().contains(&0x1b) {
        return Err(WorkbenchError::new(
            "workbench_linear_report_unsafe",
            "linear report unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

const fn report_labels(locale: WorkbenchReportLocaleV1) -> LinearReportLabels {
    match locale {
        WorkbenchReportLocaleV1::EnUs => LinearReportLabels {
            title: "Structural Native Workbench - linear report",
            schema: "Schema",
            locale: "Locale",
            presentation:
                "Presentation: UTF-8 linear text; meaning does not depend on color, position, or graphics.",
            summary: "Analysis summary",
            case: "Case",
            authority: "Authority",
            authority_value: "bounded candidate",
            terminal_status: "Terminal status",
            completed_steps: "Completed steps",
            maximum_drift: "Maximum drift ratio",
            drift_unit: "percent",
            maximum_plastic_stories: "Maximum plastic stories",
            residual_top_displacement: "Residual top displacement",
            backend: "Backend",
            external_comparison: "External comparison",
            comparison_passed: "passed",
            comparison_diverged: "diverged",
            provenance: "Provenance",
            boundary:
                "Boundary: bounded UTF-8 linear alternative for one verified candidate report; not WCAG, PDF/UA, engineering acceptance, or design-code compliance.",
            view_hash: "View hash",
        },
        WorkbenchReportLocaleV1::KoKr => LinearReportLabels {
            title: "구조 네이티브 워크벤치 - 선형 보고서",
            schema: "스키마",
            locale: "언어",
            presentation: "표현: UTF-8 선형 텍스트; 의미는 색상, 위치 또는 그래픽에 의존하지 않음.",
            summary: "해석 요약",
            case: "케이스",
            authority: "권한",
            authority_value: "제한된 후보 결과",
            terminal_status: "종료 상태",
            completed_steps: "완료 단계 수",
            maximum_drift: "최대 층간변위비",
            drift_unit: "퍼센트",
            maximum_plastic_stories: "최대 소성 층 수",
            residual_top_displacement: "잔류 최상층 변위",
            backend: "백엔드",
            external_comparison: "외부 비교",
            comparison_passed: "통과",
            comparison_diverged: "불일치",
            provenance: "출처",
            boundary:
                "경계: 검증된 하나의 후보 보고서에 대한 제한된 UTF-8 선형 대체 텍스트; WCAG, PDF/UA, 공학적 승인 또는 설계 기준 적합성 인증이 아님.",
            view_hash: "보기 해시",
        },
    }
}

fn push_provenance(
    output: &mut String,
    locale: WorkbenchReportLocaleV1,
    input: &LinearReportInput<'_>,
) {
    let identity = &input.result.identity;
    let labels = match locale {
        WorkbenchReportLocaleV1::EnUs => [
            "Result hash",
            "Report hash",
            "Document hash",
            "PDF hash",
            "Comparison hash",
            "Request hash",
            "Model hash",
            "State hash",
            "Execution hash",
            "Checkpoint hash",
        ],
        WorkbenchReportLocaleV1::KoKr => [
            "결과 해시",
            "보고서 해시",
            "문서 해시",
            "PDF 해시",
            "비교 해시",
            "요청 해시",
            "모델 해시",
            "상태 해시",
            "실행 해시",
            "체크포인트 해시",
        ],
    };
    let values = [
        input.result.result_hash.as_str(),
        input.report_hash,
        input.document_hash,
        input.pdf_hash,
        input.comparison_hash,
        identity.request_hash.as_str(),
        identity.model_hash.as_str(),
        identity.state_hash.as_str(),
        identity.execution_hash.as_str(),
        identity.checkpoint_hash.as_str(),
    ];
    for (label, value) in labels.into_iter().zip(values) {
        push_field(output, label, value);
    }
}

fn push_review(
    output: &mut String,
    locale: WorkbenchReportLocaleV1,
    review: Option<&LinearReportReview<'_>>,
) {
    let (heading, not_recorded, decision, reviewer, comment, review_hash, empty) = match locale {
        WorkbenchReportLocaleV1::EnUs => (
            "Human review",
            "not recorded",
            "Decision",
            "Reviewer",
            "Comment",
            "Review hash",
            "(empty)",
        ),
        WorkbenchReportLocaleV1::KoKr => (
            "사람 검토",
            "기록되지 않음",
            "결정",
            "검토자",
            "의견",
            "검토 해시",
            "(비어 있음)",
        ),
    };
    let Some(review) = review else {
        push_field(output, heading, not_recorded);
        return;
    };
    push_line(output, heading);
    push_field(output, decision, review_decision(locale, review.decision));
    push_field(output, reviewer, &safe_terminal_text(review.reviewer));
    push_field(output, review_hash, review.review_hash);
    push_line(output, &format!("{comment}:"));
    if review.comment.is_empty() {
        push_line(output, &format!("  {empty}"));
    } else {
        for line in review.comment.split('\n') {
            push_line(
                output,
                &format!("  {}", safe_terminal_text(&line.replace('\t', "    "))),
            );
        }
    }
}

const fn terminal_status(
    locale: WorkbenchReportLocaleV1,
    status: NonlinearNdthaTerminalStatusV1,
) -> &'static str {
    match (locale, status) {
        (WorkbenchReportLocaleV1::EnUs, NonlinearNdthaTerminalStatusV1::Completed) => "completed",
        (WorkbenchReportLocaleV1::EnUs, NonlinearNdthaTerminalStatusV1::Collapsed) => "collapsed",
        (WorkbenchReportLocaleV1::KoKr, NonlinearNdthaTerminalStatusV1::Completed) => "완료",
        (WorkbenchReportLocaleV1::KoKr, NonlinearNdthaTerminalStatusV1::Collapsed) => "붕괴",
    }
}

const fn review_decision(
    locale: WorkbenchReportLocaleV1,
    decision: WorkbenchReviewDecisionV1,
) -> &'static str {
    match (locale, decision) {
        (WorkbenchReportLocaleV1::EnUs, WorkbenchReviewDecisionV1::Pass) => "pass",
        (WorkbenchReportLocaleV1::EnUs, WorkbenchReviewDecisionV1::Review) => "review",
        (WorkbenchReportLocaleV1::EnUs, WorkbenchReviewDecisionV1::Fail) => "fail",
        (WorkbenchReportLocaleV1::KoKr, WorkbenchReviewDecisionV1::Pass) => "통과",
        (WorkbenchReportLocaleV1::KoKr, WorkbenchReviewDecisionV1::Review) => "재검토",
        (WorkbenchReportLocaleV1::KoKr, WorkbenchReviewDecisionV1::Fail) => "실패",
    }
}

fn push_field(output: &mut String, label: &str, value: &str) {
    push_line(output, &format!("{label}: {value}"));
}

fn push_line(output: &mut String, value: &str) {
    output.push_str(value);
    output.push('\n');
}

fn safe_terminal_text(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    for character in value.chars() {
        if matches!(
            character,
            '\u{061c}'
                | '\u{200e}'
                | '\u{200f}'
                | '\u{202a}'..='\u{202e}'
                | '\u{2066}'..='\u{2069}'
        ) {
            write!(output, "\\u{{{:x}}}", u32::from(character)).expect("String writes cannot fail");
        } else {
            output.push(character);
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::{safe_terminal_text, WorkbenchReportLocaleV1};

    #[test]
    fn locale_contract_is_exact_and_case_sensitive() {
        assert_eq!(
            WorkbenchReportLocaleV1::parse("en-US"),
            Some(WorkbenchReportLocaleV1::EnUs)
        );
        assert_eq!(
            WorkbenchReportLocaleV1::parse("ko-KR"),
            Some(WorkbenchReportLocaleV1::KoKr)
        );
        assert_eq!(WorkbenchReportLocaleV1::parse("ko-kr"), None);
        assert_eq!(WorkbenchReportLocaleV1::parse("C"), None);
    }

    #[test]
    fn terminal_projection_escapes_directional_spoofing_controls() {
        assert_eq!(safe_terminal_text("한\u{202e}abc"), "한\\u{202e}abc");
    }
}
