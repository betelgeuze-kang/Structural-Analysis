use std::fmt::Write as _;

use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_recovery::ModelIrLinearResultRecoveryIrV1;
use structural_contracts::product_ir::sha256_identity;
use structural_contracts::sparse_product::{SparseLinearBackendV1, SparseLinearResultIrV1};

use crate::{WorkbenchError, WorkbenchReportLocaleV1};

pub(crate) const NODAL_DISPLACEMENT_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-nodal-displacement-view.v1";
pub const WORKBENCH_NODAL_DISPLACEMENT_VIEW_DEFAULT_COUNT_V1: u32 = 64;
pub const WORKBENCH_NODAL_DISPLACEMENT_VIEW_MAX_COUNT_V1: u32 = 256;

struct NodeWindow {
    start: usize,
    end: usize,
    total: usize,
}

/// Render one deterministic bounded node window over verified global displacements.
pub(crate) fn render_model_ir_linear_nodal_displacement_view(
    model: &ModelIrV2Document,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    locale: WorkbenchReportLocaleV1,
    start_node: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    verify_model_identity(model, result, recovery)?;
    let node_ids = indexed_node_ids(model, recovery)?;
    let window = node_window(node_ids.len(), start_node, count)?;
    let mut output = String::new();
    match locale {
        WorkbenchReportLocaleV1::EnUs => {
            push_header_en_us(&mut output, result, recovery, &window);
            push_rows(&mut output, recovery, &node_ids, &window);
            push_line(&mut output, "");
            push_line(
                &mut output,
                "Boundary: bounded read-only nodal displacement components from one verified ModelIR linear CPU recovery; not a deformed-shape, stress, contour, modal, serviceability, support-design, or engineering verdict.",
            );
        }
        WorkbenchReportLocaleV1::KoKr => {
            push_header_ko_kr(&mut output, result, recovery, &window);
            push_rows(&mut output, recovery, &node_ids, &window);
            push_line(&mut output, "");
            push_line(
                &mut output,
                "경계: 검증된 ModelIR 선형 CPU 복원의 노드 변위 성분을 읽기 전용으로 표시하는 제한된 뷰입니다. 변형 형상, 응력, 등고선, 모드, 사용성, 지점 설계 또는 공학적 판정을 의미하지 않습니다.",
            );
        }
    }
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
        return Err(WorkbenchError::new(
            "workbench_nodal_displacement_view_unsafe",
            "nodal displacement view unexpectedly contains an escape byte",
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
        return Err(WorkbenchError::new(
            "workbench_nodal_displacement_view_model_mismatch",
            "verified recovery identities do not match the immutable ModelIR and sparse result",
        ));
    }
    Ok(())
}

fn indexed_node_ids(
    model: &ModelIrV2Document,
    recovery: &ModelIrLinearResultRecoveryIrV1,
) -> Result<Vec<String>, WorkbenchError> {
    let global_dof_count = usize::try_from(recovery.global_dof_count).map_err(|_| {
        WorkbenchError::new(
            "workbench_nodal_displacement_view_model_invalid",
            "global DOF count does not fit the native node address space",
        )
    })?;
    let node_count = global_dof_count / 6;
    let nodes = model
        .value()
        .get("nodes")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_nodal_displacement_view_model_invalid",
                "verified ModelIR has no node array",
            )
        })?;
    if nodes.len() != node_count || recovery.global_displacement.len() != global_dof_count {
        return Err(WorkbenchError::new(
            "workbench_nodal_displacement_view_model_mismatch",
            "ModelIR nodes and recovered global displacement dimensions differ",
        ));
    }
    let mut ids = vec![None; node_count];
    for node in nodes {
        let index = node
            .get("index")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|&value| value < node_count)
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_nodal_displacement_view_model_invalid",
                    "ModelIR node index is missing or outside the displacement mapping",
                )
            })?;
        let id = node
            .get("id")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.is_empty() && !value.chars().any(char::is_control))
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_nodal_displacement_view_model_invalid",
                    "ModelIR node identifier is missing or unsafe for terminal presentation",
                )
            })?;
        if ids[index].replace(id.to_owned()).is_some() {
            return Err(WorkbenchError::new(
                "workbench_nodal_displacement_view_model_invalid",
                "ModelIR node indices are not unique",
            ));
        }
    }
    ids.into_iter()
        .map(|id| {
            id.ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_nodal_displacement_view_model_invalid",
                    "ModelIR node indices do not form a complete contiguous mapping",
                )
            })
        })
        .collect()
}

fn node_window(total: usize, start_node: u32, count: u32) -> Result<NodeWindow, WorkbenchError> {
    if start_node == 0 || count == 0 || count > WORKBENCH_NODAL_DISPLACEMENT_VIEW_MAX_COUNT_V1 {
        return Err(window_error(format!(
            "start node must be at least 1 and count must be in 1..={WORKBENCH_NODAL_DISPLACEMENT_VIEW_MAX_COUNT_V1}"
        )));
    }
    let start = usize::try_from(start_node - 1)
        .map_err(|_| window_error("start node does not fit the native address space"))?;
    if start >= total {
        return Err(window_error(format!(
            "start node {start_node} exceeds the {total} recovered nodes"
        )));
    }
    let requested = usize::try_from(count)
        .map_err(|_| window_error("count does not fit the native address space"))?;
    Ok(NodeWindow {
        start,
        end: start.saturating_add(requested).min(total),
        total,
    })
}

fn push_header_en_us(
    output: &mut String,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    window: &NodeWindow,
) {
    push_line(
        output,
        "Structural ModelIR Linear Workbench - Nodal Displacements",
    );
    push_field(output, "Schema", NODAL_DISPLACEMENT_VIEW_SCHEMA_V1);
    push_field(output, "Locale", WorkbenchReportLocaleV1::EnUs.label());
    push_field(output, "Case", &recovery.case_id);
    push_field(output, "Model", &recovery.model_id);
    push_field(output, "Load pattern", &recovery.load_pattern_id);
    push_field(output, "Authority", "bounded candidate");
    push_field(output, "Nodes", &window.total.to_string());
    push_field(
        output,
        "Displayed nodes",
        &format!("{}-{} of {}", window.start + 1, window.end, window.total),
    );
    push_common_header(output, result, recovery, false);
    push_line(output, "");
    push_line(
        output,
        "Row\tNode ID\tNode index\tUX (m)\tUY (m)\tUZ (m)\tRX (rad)\tRY (rad)\tRZ (rad)",
    );
}

fn push_header_ko_kr(
    output: &mut String,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    window: &NodeWindow,
) {
    push_line(output, "Structural ModelIR 선형 Workbench - 노드 변위");
    push_field(output, "스키마", NODAL_DISPLACEMENT_VIEW_SCHEMA_V1);
    push_field(output, "로케일", WorkbenchReportLocaleV1::KoKr.label());
    push_field(output, "해석 사례", &recovery.case_id);
    push_field(output, "모델", &recovery.model_id);
    push_field(output, "하중 패턴", &recovery.load_pattern_id);
    push_field(output, "권한", "제한된 후보");
    push_field(output, "노드", &window.total.to_string());
    push_field(
        output,
        "표시 노드",
        &format!("{}-{} / {}", window.start + 1, window.end, window.total),
    );
    push_common_header(output, result, recovery, true);
    push_line(output, "");
    push_line(
        output,
        "행\t노드 ID\t노드 인덱스\tUX (m)\tUY (m)\tUZ (m)\tRX (rad)\tRY (rad)\tRZ (rad)",
    );
}

fn push_common_header(
    output: &mut String,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    korean: bool,
) {
    let labels = if korean {
        [
            "성분 단위",
            "좌표계",
            "최대 절대 복원 성분(혼합 m/rad)",
            "백엔드",
            "전송/동기 계수",
            "소스 결과 해시",
            "복원 해시",
            "분석 요청 해시",
            "조립 해시",
        ]
    } else {
        [
            "Component units",
            "Coordinate frame",
            "Maximum absolute recovered component (mixed m/rad)",
            "Backend",
            "Transfer/sync counts",
            "Source result hash",
            "Recovery hash",
            "Analysis request hash",
            "Assembly hash",
        ]
    };
    push_field(output, labels[0], "UX/UY/UZ=m; RX/RY/RZ=rad");
    push_field(
        output,
        labels[1],
        &recovery
            .coordinate_frame
            .global_displacement_and_active_force,
    );
    push_field(
        output,
        labels[2],
        &format!("{:+.17e}", recovery.summary.maximum_absolute_displacement),
    );
    push_field(
        output,
        labels[3],
        &format!(
            "{} / {} / ABI {} / fallback {}",
            sparse_backend_label(result.backend_receipt.backend),
            result.backend_receipt.precision,
            result.backend_receipt.abi_version,
            result.backend_receipt.fallback_count
        ),
    );
    push_field(
        output,
        labels[4],
        &format!(
            "H2D {} / D2H {} / sync {}",
            result.backend_receipt.h2d_bytes,
            result.backend_receipt.d2h_bytes,
            result.backend_receipt.sync_count
        ),
    );
    push_field(output, labels[5], &recovery.source_result_hash);
    push_field(output, labels[6], &recovery.recovery_hash);
    push_field(output, labels[7], &recovery.analysis_request_hash);
    push_field(output, labels[8], &recovery.assembly_hash);
    push_identity_header(output, result, recovery, korean);
}

const fn sparse_backend_label(backend: SparseLinearBackendV1) -> &'static str {
    match backend {
        SparseLinearBackendV1::Cpu => "cpu",
    }
}

fn push_identity_header(
    output: &mut String,
    result: &SparseLinearResultIrV1,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    korean: bool,
) {
    let labels = if korean {
        [
            "모델 콘텐츠 해시",
            "모델 의미 해시",
            "모델 출처 해시",
            "희소 요청 해시",
            "희소 모델 해시",
            "상태 해시",
            "실행 해시",
            "체크포인트 해시",
        ]
    } else {
        [
            "Model content hash",
            "Model semantic hash",
            "Model provenance hash",
            "Sparse request hash",
            "Sparse model hash",
            "State hash",
            "Execution hash",
            "Checkpoint hash",
        ]
    };
    push_field(output, labels[0], &recovery.model_identity.content_hash);
    push_field(output, labels[1], &recovery.model_identity.semantic_hash);
    push_field(output, labels[2], &recovery.model_identity.provenance_hash);
    push_field(output, labels[3], &result.identity.request_hash);
    push_field(output, labels[4], &result.identity.model_hash);
    push_field(output, labels[5], &result.identity.state_hash);
    push_field(output, labels[6], &result.identity.execution_hash);
    push_field(output, labels[7], &result.identity.checkpoint_hash);
}

fn push_rows(
    output: &mut String,
    recovery: &ModelIrLinearResultRecoveryIrV1,
    node_ids: &[String],
    window: &NodeWindow,
) {
    for (node_index, node_id) in node_ids
        .iter()
        .enumerate()
        .take(window.end)
        .skip(window.start)
    {
        let offset = node_index * 6;
        writeln!(
            output,
            "{:06}\t{}\t{:010}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{:+.17e}",
            node_index + 1,
            node_id,
            node_index,
            recovery.global_displacement[offset],
            recovery.global_displacement[offset + 1],
            recovery.global_displacement[offset + 2],
            recovery.global_displacement[offset + 3],
            recovery.global_displacement[offset + 4],
            recovery.global_displacement[offset + 5],
        )
        .expect("writing to a String cannot fail");
    }
}

fn window_error(detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new("workbench_nodal_displacement_view_window_invalid", detail)
}

fn push_line(output: &mut String, value: &str) {
    output.push_str(value);
    output.push('\n');
}

fn push_field(output: &mut String, label: &str, value: &str) {
    output.push_str(label);
    output.push_str(": ");
    push_line(output, value);
}

#[cfg(test)]
mod tests {
    use super::{window_error, WORKBENCH_NODAL_DISPLACEMENT_VIEW_MAX_COUNT_V1};

    #[test]
    fn nodal_displacement_view_window_error_is_stable() {
        let error = window_error(format!(
            "count must be in 1..={WORKBENCH_NODAL_DISPLACEMENT_VIEW_MAX_COUNT_V1}"
        ));
        assert_eq!(
            error.code,
            "workbench_nodal_displacement_view_window_invalid"
        );
    }
}
