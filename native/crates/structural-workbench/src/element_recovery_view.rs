use std::collections::{BTreeMap, BTreeSet};
use std::fmt::Write as _;

use serde_json::Value;
use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_recovery::ModelIrLinearResultRecoveryIrV1;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{SparseLinearBackendV1, SparseLinearResultIrV1};

use crate::{WorkbenchError, WorkbenchReportLocaleV1};

pub(crate) const ELEMENT_RECOVERY_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-element-recovery-view.v1";
pub const WORKBENCH_ELEMENT_RECOVERY_VIEW_DEFAULT_COUNT_V1: u32 = 64;
pub const WORKBENCH_ELEMENT_RECOVERY_VIEW_MAX_COUNT_V1: u32 = 256;

const FRAME_ELEMENT_TYPE: u32 = 1;
const TRUSS_ELEMENT_TYPE: u32 = 2;
const CLAIM_BOUNDARY: &str = "bounded_read_only_modelir_linear_frame3d_local_end_force_and_truss3d_axis_strain_stress_force_projection_not_shell_general_stress_contour_design_utilization_support_design_engineering_acceptance_or_code_compliance";
const HEADER_LABELS_EN_US: [&str; 27] = [
    "Schema",
    "Locale",
    "Authority",
    "Profile",
    "Selected state",
    "Case",
    "Model",
    "Load pattern",
    "Elements",
    "Displayed elements",
    "Frame3d components",
    "Truss3d components",
    "Coordinate frames",
    "Backend",
    "Transfer/sync counts",
    "Model content hash",
    "Model semantic hash",
    "Model provenance hash",
    "Source result hash",
    "Recovery hash",
    "Analysis request hash",
    "Assembly hash",
    "Sparse request hash",
    "Sparse model hash",
    "State hash",
    "Execution hash",
    "Checkpoint hash",
];
const HEADER_LABELS_KO_KR: [&str; 27] = [
    "스키마",
    "로케일",
    "권한",
    "프로파일",
    "선택 상태",
    "해석 사례",
    "모델",
    "하중 패턴",
    "요소",
    "표시 요소",
    "Frame3d 성분",
    "Truss3d 성분",
    "좌표계",
    "백엔드",
    "전송/동기 계수",
    "모델 콘텐츠 해시",
    "모델 의미 해시",
    "모델 출처 해시",
    "소스 결과 해시",
    "복원 해시",
    "분석 요청 해시",
    "조립 해시",
    "희소 요청 해시",
    "희소 모델 해시",
    "상태 해시",
    "실행 해시",
    "체크포인트 해시",
];

type ElementMetadata = (String, String, String, String);

#[derive(Clone, Debug)]
struct ElementRecoveryRow {
    id: String,
    index: u32,
    kind: String,
    node_i: String,
    node_j: String,
    element_type: u32,
    values: Vec<f64>,
}

#[derive(Clone, Copy, Debug)]
struct ElementWindow {
    start: usize,
    end: usize,
    total: usize,
}

/// Render one deterministic bounded element-recovery window from a verified linear result.
pub(crate) fn render_model_ir_linear_element_recovery_view(
    model: &ModelIrV2Document,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    locale: WorkbenchReportLocaleV1,
    start_element: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    verify_model_identity(model, result, recovery)?;
    let rows = indexed_recovery_rows(model, recovery)?;
    let window = element_window(rows.len(), start_element, count)?;
    let mut output = String::new();
    push_header(&mut output, result, recovery, locale, &window);
    push_rows(&mut output, &rows, locale, &window);
    push_line(&mut output, "");
    push_field(
        &mut output,
        match locale {
            WorkbenchReportLocaleV1::EnUs => "Claim boundary",
            WorkbenchReportLocaleV1::KoKr => "주장 경계",
        },
        CLAIM_BOUNDARY,
    );
    let view_hash = sha256_identity(output.as_bytes());
    push_field(
        &mut output,
        match locale {
            WorkbenchReportLocaleV1::EnUs => "View hash",
            WorkbenchReportLocaleV1::KoKr => "보기 해시",
        },
        &view_hash,
    );
    if output.as_bytes().contains(&0x1b) {
        return Err(view_error(
            "workbench_element_recovery_view_unsafe",
            "element recovery view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn verify_model_identity(
    model: &ModelIrV2Document,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<(), WorkbenchError> {
    if model.model_id() != recovery.model_id
        || model.content_hash() != recovery.model_identity.content_hash
        || model.semantic_hash() != recovery.model_identity.semantic_hash
        || model.provenance_hash() != recovery.model_identity.provenance_hash
        || result.case_id != recovery.case_id
        || result.result_hash != recovery.source_result_hash
    {
        return Err(view_error(
            "workbench_element_recovery_view_model_mismatch",
            "verified recovery identities do not match the immutable ModelIR and sparse result",
        ));
    }
    Ok(())
}

fn indexed_recovery_rows(
    model: &ModelIrV2Document,
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<Vec<ElementRecoveryRow>, WorkbenchError> {
    let mut by_index = indexed_element_metadata(model)?;
    let record_count = recovery.recovery_stable_indices.len();
    if by_index.len() != record_count
        || recovery.recovery_element_types.len() != record_count
        || recovery.recovery_offsets.len() != record_count.saturating_add(1)
    {
        return Err(view_error(
            "workbench_element_recovery_view_model_mismatch",
            "ModelIR elements and typed recovery record dimensions differ",
        ));
    }

    let mut rows = Vec::with_capacity(record_count);
    for position in 0..record_count {
        let stable_index = recovery.recovery_stable_indices[position];
        let element_type = recovery.recovery_element_types[position];
        let (id, kind, node_i, node_j) = by_index.remove(&stable_index).ok_or_else(|| {
            view_error(
                "workbench_element_recovery_view_model_mismatch",
                "recovery stable index is absent from the immutable ModelIR",
            )
        })?;
        let expected_kind = match element_type {
            FRAME_ELEMENT_TYPE => "frame_3d",
            TRUSS_ELEMENT_TYPE => "truss_3d",
            _ => {
                return Err(result_error(
                    "typed recovery contains an unsupported element type code",
                ))
            }
        };
        if kind != expected_kind {
            return Err(view_error(
                "workbench_element_recovery_view_model_mismatch",
                "ModelIR element family differs from its typed recovery record",
            ));
        }
        let begin = usize::try_from(recovery.recovery_offsets[position])
            .map_err(|_| result_error("recovery offset does not fit the native address space"))?;
        let end = usize::try_from(recovery.recovery_offsets[position + 1])
            .map_err(|_| result_error("recovery offset does not fit the native address space"))?;
        let expected_count = if element_type == FRAME_ELEMENT_TYPE {
            12
        } else {
            3
        };
        if end.checked_sub(begin) != Some(expected_count) || end > recovery.recovery_values.len() {
            return Err(result_error(
                "typed recovery offsets do not match the element family",
            ));
        }
        let values = recovery.recovery_values[begin..end].to_vec();
        if values.iter().any(|value| !value.is_finite()) {
            return Err(result_error(
                "element recovery contains a non-finite FP64 value",
            ));
        }
        rows.push(ElementRecoveryRow {
            id,
            index: stable_index,
            kind,
            node_i,
            node_j,
            element_type,
            values,
        });
    }
    if !by_index.is_empty() {
        return Err(view_error(
            "workbench_element_recovery_view_model_mismatch",
            "immutable ModelIR contains an element without typed recovery",
        ));
    }
    Ok(rows)
}

fn indexed_element_metadata(
    model: &ModelIrV2Document,
) -> Result<BTreeMap<u32, ElementMetadata>, WorkbenchError> {
    let elements = array_field(model.value(), "elements")?;
    let mut by_index = BTreeMap::new();
    let mut identifiers = BTreeSet::new();
    for element in elements {
        let index = element
            .get("index")
            .and_then(Value::as_u64)
            .and_then(|value| u32::try_from(value).ok())
            .ok_or_else(|| model_error("ModelIR element index is missing or out of range"))?;
        let id = safe_string_field(element, "id")?.to_owned();
        let kind = safe_string_field(element, "type")?.to_owned();
        let node_ids = array_field(element, "node_ids")?;
        if node_ids.len() != 2 {
            return Err(model_error(
                "bounded element recovery view supports only two-node elements",
            ));
        }
        let node_i = safe_value_string(&node_ids[0], "element first node")?.to_owned();
        let node_j = safe_value_string(&node_ids[1], "element second node")?.to_owned();
        if node_i == node_j {
            return Err(model_error("element endpoints must be distinct"));
        }
        if !identifiers.insert(id.clone())
            || by_index.insert(index, (id, kind, node_i, node_j)).is_some()
        {
            return Err(model_error(
                "ModelIR element indices and identifiers must be unique",
            ));
        }
    }
    Ok(by_index)
}

fn element_window(
    total: usize,
    start_element: u32,
    count: u32,
) -> Result<ElementWindow, WorkbenchError> {
    if start_element == 0 || count == 0 || count > WORKBENCH_ELEMENT_RECOVERY_VIEW_MAX_COUNT_V1 {
        return Err(window_error(format!(
            "start element must be at least 1 and count must be in 1..={WORKBENCH_ELEMENT_RECOVERY_VIEW_MAX_COUNT_V1}"
        )));
    }
    let start = usize::try_from(start_element - 1)
        .map_err(|_| window_error("start element does not fit the native address space"))?;
    if start >= total {
        return Err(window_error(format!(
            "start element {start_element} exceeds the {total} recovered elements"
        )));
    }
    let requested = usize::try_from(count)
        .map_err(|_| window_error("count does not fit the native address space"))?;
    Ok(ElementWindow {
        start,
        end: start.saturating_add(requested).min(total),
        total,
    })
}

fn push_header(
    output: &mut String,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    locale: WorkbenchReportLocaleV1,
    window: &ElementWindow,
) {
    let (title, labels) = match locale {
        WorkbenchReportLocaleV1::EnUs => (
            "Structural ModelIR Linear Workbench - Element Recovery",
            &HEADER_LABELS_EN_US,
        ),
        WorkbenchReportLocaleV1::KoKr => (
            "Structural ModelIR 선형 Workbench - 요소 복원",
            &HEADER_LABELS_KO_KR,
        ),
    };
    push_line(output, title);
    push_field(output, labels[0], ELEMENT_RECOVERY_VIEW_SCHEMA_V1);
    push_field(output, labels[1], locale.label());
    push_field(
        output,
        labels[2],
        match locale {
            WorkbenchReportLocaleV1::EnUs => "bounded candidate",
            WorkbenchReportLocaleV1::KoKr => "제한된 후보",
        },
    );
    push_field(output, labels[3], "model_ir_linear_cpu_v1");
    push_field(output, labels[4], "1 of 1 (terminal linear static)");
    push_field(output, labels[5], &recovery.case_id);
    push_field(output, labels[6], &recovery.model_id);
    push_field(output, labels[7], &recovery.load_pattern_id);
    push_field(output, labels[8], &window.total.to_string());
    push_field(
        output,
        labels[9],
        &format!("{}-{} of {}", window.start + 1, window.end, window.total),
    );
    push_field(
        output,
        labels[10],
        "i_FX/i_FY/i_FZ/j_FX/j_FY/j_FZ=N; i_MX/i_MY/i_MZ/j_MX/j_MY/j_MZ=N*m",
    );
    push_field(
        output,
        labels[11],
        "axial_strain=1; axial_stress=Pa; axial_force=N",
    );
    push_field(
        output,
        labels[12],
        "frame3d=element_local; truss3d=element_axis",
    );
    push_field(
        output,
        labels[13],
        &format!(
            "{} / {} / ABI {} / fallback {}",
            sparse_backend_label(result.backend_receipt.backend),
            result.backend_receipt.precision,
            result.backend_receipt.abi_version,
            result.backend_receipt.fallback_count,
        ),
    );
    push_field(
        output,
        labels[14],
        &format!(
            "H2D {} / D2H {} / sync {}",
            result.backend_receipt.h2d_bytes,
            result.backend_receipt.d2h_bytes,
            result.backend_receipt.sync_count,
        ),
    );
    for (label, value) in [
        (labels[15], recovery.model_identity.content_hash.as_str()),
        (labels[16], recovery.model_identity.semantic_hash.as_str()),
        (labels[17], recovery.model_identity.provenance_hash.as_str()),
        (labels[18], recovery.source_result_hash.as_str()),
        (labels[19], recovery.recovery_hash.as_str()),
        (labels[20], recovery.analysis_request_hash.as_str()),
        (labels[21], recovery.assembly_hash.as_str()),
        (labels[22], result.identity.request_hash.as_str()),
        (labels[23], result.identity.model_hash.as_str()),
        (labels[24], result.identity.state_hash.as_str()),
        (labels[25], result.identity.execution_hash.as_str()),
        (labels[26], result.identity.checkpoint_hash.as_str()),
    ] {
        push_field(output, label, value);
    }
    push_line(output, "");
    push_line(
        output,
        match locale {
            WorkbenchReportLocaleV1::EnUs => {
                "Row\tElement ID\tElement index\tType\tNodes\tCoordinate frame\tComponents"
            }
            WorkbenchReportLocaleV1::KoKr => "행\t요소 ID\t요소 인덱스\t유형\t절점\t좌표계\t성분",
        },
    );
}

fn push_rows(
    output: &mut String,
    rows: &[ElementRecoveryRow],
    _locale: WorkbenchReportLocaleV1,
    window: &ElementWindow,
) {
    for (position, row) in rows[window.start..window.end].iter().enumerate() {
        let (frame, components) = if row.element_type == FRAME_ELEMENT_TYPE {
            ("element_local", frame_components(&row.values))
        } else {
            ("element_axis", truss_components(&row.values))
        };
        writeln!(
            output,
            "{:06}\t{}\t{:010}\t{}\t{}->{}\t{}\t{}",
            window.start + position + 1,
            row.id,
            row.index,
            row.kind,
            row.node_i,
            row.node_j,
            frame,
            components,
        )
        .expect("writing to a String cannot fail");
    }
}

fn frame_components(values: &[f64]) -> String {
    let names = [
        "i_FX_N", "i_FY_N", "i_FZ_N", "i_MX_N_m", "i_MY_N_m", "i_MZ_N_m", "j_FX_N", "j_FY_N",
        "j_FZ_N", "j_MX_N_m", "j_MY_N_m", "j_MZ_N_m",
    ];
    names
        .iter()
        .zip(values)
        .map(|(name, value)| format!("{name}={value:+.17e}"))
        .collect::<Vec<_>>()
        .join(";")
}

fn truss_components(values: &[f64]) -> String {
    ["axial_strain_1", "axial_stress_Pa", "axial_force_N"]
        .iter()
        .zip(values)
        .map(|(name, value)| format!("{name}={value:+.17e}"))
        .collect::<Vec<_>>()
        .join(";")
}

fn array_field<'a>(value: &'a Value, field: &str) -> Result<&'a [Value], WorkbenchError> {
    value
        .get(field)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| model_error(format!("ModelIR field {field} is not an array")))
}

fn safe_string_field<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .get(field)
        .ok_or_else(|| model_error(format!("ModelIR field {field} is missing")))
        .and_then(|value| safe_value_string(value, field))
}

fn safe_value_string<'a>(value: &'a Value, field: &str) -> Result<&'a str, WorkbenchError> {
    value
        .as_str()
        .filter(|text| !text.is_empty() && !text.chars().any(char::is_control))
        .ok_or_else(|| {
            model_error(format!(
                "ModelIR field {field} is not a safe terminal string"
            ))
        })
}

const fn sparse_backend_label(backend: SparseLinearBackendV1) -> &'static str {
    match backend {
        SparseLinearBackendV1::Cpu => "cpu",
    }
}

fn push_line(output: &mut String, line: &str) {
    output.push_str(line);
    output.push('\n');
}

fn push_field(output: &mut String, label: &str, value: &str) {
    writeln!(output, "{label}: {value}").expect("writing to a String cannot fail");
}

fn model_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_element_recovery_view_model_invalid", detail)
}

fn result_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_element_recovery_view_result_invalid", detail)
}

fn window_error(detail: impl Into<String>) -> WorkbenchError {
    view_error("workbench_element_recovery_view_window_invalid", detail)
}

fn view_error(code: &'static str, detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn element_recovery_window_is_bounded_and_stable() {
        let window = element_window(4, 2, 2).expect("bounded window");
        assert_eq!((window.start, window.end, window.total), (1, 3, 4));
        for (start, count) in [(0, 1), (1, 0), (1, 257), (5, 1)] {
            let error = element_window(4, start, count).expect_err("invalid window");
            assert_eq!(error.code, "workbench_element_recovery_view_window_invalid");
        }
    }

    #[test]
    fn component_labels_and_fp64_format_are_stable_for_both_families() {
        let frame = frame_components(&[
            1.0, -2.0, 3.0, -4.0, 5.0, -6.0, 7.0, -8.0, 9.0, -10.0, 11.0, -12.0,
        ]);
        assert_eq!(
            frame,
            concat!(
                "i_FX_N=+1.00000000000000000e0;i_FY_N=-2.00000000000000000e0;",
                "i_FZ_N=+3.00000000000000000e0;i_MX_N_m=-4.00000000000000000e0;",
                "i_MY_N_m=+5.00000000000000000e0;i_MZ_N_m=-6.00000000000000000e0;",
                "j_FX_N=+7.00000000000000000e0;j_FY_N=-8.00000000000000000e0;",
                "j_FZ_N=+9.00000000000000000e0;j_MX_N_m=-1.00000000000000000e1;",
                "j_MY_N_m=+1.10000000000000000e1;j_MZ_N_m=-1.20000000000000000e1"
            )
        );
        assert_eq!(
            truss_components(&[1.25e-4, -2.5e6, 3.75e3]),
            concat!(
                "axial_strain_1=+1.25000000000000003e-4;",
                "axial_stress_Pa=-2.50000000000000000e6;",
                "axial_force_N=+3.75000000000000000e3"
            )
        );
    }
}
