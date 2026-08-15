use std::fmt::Write as _;

use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_reactions::ModelIrLinearReactionResultIrV1;
use structural_contracts::product_ir::sha256_identity;

use crate::{WorkbenchError, WorkbenchReportLocaleV1};

pub(crate) const REACTION_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-reaction-view.v1";
pub const WORKBENCH_REACTION_VIEW_DEFAULT_COUNT_V1: u32 = 64;
pub const WORKBENCH_REACTION_VIEW_MAX_COUNT_V1: u32 = 256;

struct ReactionWindow {
    start: usize,
    end: usize,
    total: usize,
}

/// Render one deterministic bounded window over verified constrained reactions.
pub(crate) fn render_model_ir_linear_reaction_view(
    model: &ModelIrV2Document,
    reaction: &ModelIrLinearReactionResultIrV1,
    locale: WorkbenchReportLocaleV1,
    start_row: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    verify_model_identity(model, reaction)?;
    let node_ids = indexed_node_ids(model, reaction)?;
    let window = reaction_window(reaction, start_row, count)?;
    let mut output = String::new();
    match locale {
        WorkbenchReportLocaleV1::EnUs => {
            push_header_en_us(&mut output, reaction, &window);
            push_rows(&mut output, reaction, &node_ids, &window);
            push_line(&mut output, "");
            push_line(
                &mut output,
                "Boundary: bounded read-only view of constrained reactions from one verified ModelIR linear CPU result; not an equilibrium audit, support-design verdict, engineering acceptance, or design-code compliance.",
            );
        }
        WorkbenchReportLocaleV1::KoKr => {
            push_header_ko_kr(&mut output, reaction, &window);
            push_rows(&mut output, reaction, &node_ids, &window);
            push_line(&mut output, "");
            push_line(
                &mut output,
                "경계: 검증된 ModelIR 선형 CPU 결과의 구속 반력을 읽기 전용으로 표시하는 제한된 뷰입니다. 평형 감사, 지점 설계 판정, 공학적 승인 또는 설계기준 준수를 의미하지 않습니다.",
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
            "workbench_reaction_view_unsafe",
            "reaction view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn verify_model_identity(
    model: &ModelIrV2Document,
    reaction: &ModelIrLinearReactionResultIrV1,
) -> Result<(), WorkbenchError> {
    if model.model_id() != reaction.model_id
        || model.content_hash() != reaction.model_identity.content_hash
        || model.semantic_hash() != reaction.model_identity.semantic_hash
        || model.provenance_hash() != reaction.model_identity.provenance_hash
    {
        return Err(WorkbenchError::new(
            "workbench_reaction_view_model_mismatch",
            "verified reaction identities do not match the immutable ModelIR used for node labels",
        ));
    }
    Ok(())
}

fn indexed_node_ids(
    model: &ModelIrV2Document,
    reaction: &ModelIrLinearReactionResultIrV1,
) -> Result<Vec<String>, WorkbenchError> {
    let node_count = usize::try_from(reaction.global_dof_count / 6).map_err(|_| {
        WorkbenchError::new(
            "workbench_reaction_view_model_invalid",
            "global DOF count does not fit the native node-label address space",
        )
    })?;
    let nodes = model
        .value()
        .get("nodes")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            WorkbenchError::new(
                "workbench_reaction_view_model_invalid",
                "verified ModelIR has no node array",
            )
        })?;
    if nodes.len() != node_count {
        return Err(WorkbenchError::new(
            "workbench_reaction_view_model_mismatch",
            "ModelIR node count does not match the verified reaction global DOF count",
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
                    "workbench_reaction_view_model_invalid",
                    "ModelIR node index is missing or outside the reaction mapping",
                )
            })?;
        let id = node
            .get("id")
            .and_then(serde_json::Value::as_str)
            .filter(|value| !value.is_empty() && !value.chars().any(char::is_control))
            .ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_reaction_view_model_invalid",
                    "ModelIR node identifier is missing or unsafe for terminal presentation",
                )
            })?;
        if ids[index].replace(id.to_owned()).is_some() {
            return Err(WorkbenchError::new(
                "workbench_reaction_view_model_invalid",
                "ModelIR node indices are not unique",
            ));
        }
    }
    ids.into_iter()
        .map(|id| {
            id.ok_or_else(|| {
                WorkbenchError::new(
                    "workbench_reaction_view_model_invalid",
                    "ModelIR node indices do not form a complete contiguous mapping",
                )
            })
        })
        .collect()
}

fn reaction_window(
    reaction: &ModelIrLinearReactionResultIrV1,
    start_row: u32,
    count: u32,
) -> Result<ReactionWindow, WorkbenchError> {
    if start_row == 0 || count == 0 || count > WORKBENCH_REACTION_VIEW_MAX_COUNT_V1 {
        return Err(window_error(format!(
            "start row must be at least 1 and count must be in 1..={WORKBENCH_REACTION_VIEW_MAX_COUNT_V1}"
        )));
    }
    let total = reaction.constrained_dof_indices.len();
    let start = usize::try_from(start_row - 1)
        .map_err(|_| window_error("start row does not fit the native address space"))?;
    if start >= total {
        return Err(window_error(format!(
            "start row {start_row} exceeds the {total} constrained reaction rows"
        )));
    }
    let requested = usize::try_from(count)
        .map_err(|_| window_error("count does not fit the native address space"))?;
    Ok(ReactionWindow {
        start,
        end: start.saturating_add(requested).min(total),
        total,
    })
}

fn push_header_en_us(
    output: &mut String,
    reaction: &ModelIrLinearReactionResultIrV1,
    window: &ReactionWindow,
) {
    push_line(
        output,
        "Structural ModelIR Linear Workbench - Constrained Reactions",
    );
    push_field(output, "Schema", REACTION_VIEW_SCHEMA_V1);
    push_field(output, "Locale", WorkbenchReportLocaleV1::EnUs.label());
    push_field(output, "Case", &reaction.case_id);
    push_field(output, "Model", &reaction.model_id);
    push_field(output, "Load pattern", &reaction.load_pattern_id);
    push_field(output, "Authority", "bounded candidate");
    push_field(output, "Constrained DOFs", &window.total.to_string());
    push_field(
        output,
        "Displayed rows",
        &format!("{}-{} of {}", window.start + 1, window.end, window.total),
    );
    push_common_header(output, reaction, false);
    push_line(output, "");
    push_line(
        output,
        "Row\tNode ID\tDOF\tGlobal DOF\tInternal force\tExternal load\tReaction\tUnit",
    );
}

fn push_header_ko_kr(
    output: &mut String,
    reaction: &ModelIrLinearReactionResultIrV1,
    window: &ReactionWindow,
) {
    push_line(output, "Structural ModelIR 선형 Workbench - 구속 반력");
    push_field(output, "스키마", REACTION_VIEW_SCHEMA_V1);
    push_field(output, "로케일", WorkbenchReportLocaleV1::KoKr.label());
    push_field(output, "해석 사례", &reaction.case_id);
    push_field(output, "모델", &reaction.model_id);
    push_field(output, "하중 패턴", &reaction.load_pattern_id);
    push_field(output, "권한", "제한된 후보");
    push_field(output, "구속 자유도", &window.total.to_string());
    push_field(
        output,
        "표시 행",
        &format!("{}-{} / {}", window.start + 1, window.end, window.total),
    );
    push_common_header(output, reaction, true);
    push_line(output, "");
    push_line(
        output,
        "행\t노드 ID\t자유도\t전역 자유도\t내부력\t외부 하중\t반력\t단위",
    );
}

fn push_common_header(
    output: &mut String,
    reaction: &ModelIrLinearReactionResultIrV1,
    korean: bool,
) {
    let labels = if korean {
        [
            "최대 절대 반력",
            "성분별 합계",
            "단위",
            "백엔드",
            "전송/동기 계수",
            "소스 결과 해시",
            "소스 복원 해시",
            "반력 해시",
        ]
    } else {
        [
            "Maximum absolute reaction",
            "Component sums",
            "Units",
            "Backend",
            "Transfer/sync counts",
            "Source result hash",
            "Source recovery hash",
            "Reaction hash",
        ]
    };
    push_field(
        output,
        labels[0],
        &format!(
            "{:+.17e}",
            reaction.summary.maximum_absolute_reaction_component
        ),
    );
    push_field(output, labels[1], &component_sums(reaction));
    push_field(
        output,
        labels[2],
        &format!(
            "translation {} / rotation {} / {}",
            reaction.units.translational_components,
            reaction.units.rotational_components,
            reaction.units.coordinate_frame
        ),
    );
    push_field(
        output,
        labels[3],
        &format!(
            "{} / {} / ABI {} / fallback {}",
            reaction.backend_receipt.backend,
            reaction.backend_receipt.precision,
            reaction.backend_receipt.abi_version,
            reaction.backend_receipt.fallback_count
        ),
    );
    push_field(
        output,
        labels[4],
        &format!(
            "H2D {} / D2H {} / sync {}",
            reaction.backend_receipt.h2d_bytes,
            reaction.backend_receipt.d2h_bytes,
            reaction.backend_receipt.sync_count
        ),
    );
    push_field(output, labels[5], &reaction.source_result_hash);
    push_field(output, labels[6], &reaction.source_recovery_hash);
    push_field(output, labels[7], &reaction.result_hash);
    push_identity_header(output, reaction, korean);
}

fn push_identity_header(
    output: &mut String,
    reaction: &ModelIrLinearReactionResultIrV1,
    korean: bool,
) {
    let identity_labels = if korean {
        [
            "분석 요청 해시",
            "조립 해시",
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
            "Analysis request hash",
            "Assembly hash",
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
    push_field(output, identity_labels[0], &reaction.analysis_request_hash);
    push_field(output, identity_labels[1], &reaction.assembly_hash);
    push_field(
        output,
        identity_labels[2],
        &reaction.model_identity.content_hash,
    );
    push_field(
        output,
        identity_labels[3],
        &reaction.model_identity.semantic_hash,
    );
    push_field(
        output,
        identity_labels[4],
        &reaction.model_identity.provenance_hash,
    );
    push_field(output, identity_labels[5], &reaction.identity.request_hash);
    push_field(output, identity_labels[6], &reaction.identity.model_hash);
    push_field(output, identity_labels[7], &reaction.identity.state_hash);
    push_field(
        output,
        identity_labels[8],
        &reaction.identity.execution_hash,
    );
    push_field(
        output,
        identity_labels[9],
        &reaction.identity.checkpoint_hash,
    );
}

fn component_sums(reaction: &ModelIrLinearReactionResultIrV1) -> String {
    reaction
        .summary
        .component_sums
        .iter()
        .enumerate()
        .map(|(index, value)| {
            let unit = component_unit(reaction, index);
            format!(
                "{}={:+.17e} {unit}",
                reaction.dof_order_per_node[index], value
            )
        })
        .collect::<Vec<_>>()
        .join("; ")
}

fn push_rows(
    output: &mut String,
    reaction: &ModelIrLinearReactionResultIrV1,
    node_ids: &[String],
    window: &ReactionWindow,
) {
    for position in window.start..window.end {
        let global_dof = usize::try_from(reaction.constrained_dof_indices[position])
            .expect("validated reaction DOF index fits usize");
        let component = global_dof % 6;
        writeln!(
            output,
            "{:06}\t{}\t{}\t{:010}\t{:+.17e}\t{:+.17e}\t{:+.17e}\t{}",
            position + 1,
            node_ids[global_dof / 6],
            reaction.dof_order_per_node[component],
            global_dof,
            reaction.constrained_internal_force[position],
            reaction.constrained_external_load[position],
            reaction.reactions[position],
            component_unit(reaction, component),
        )
        .expect("writing to a String cannot fail");
    }
}

fn component_unit(reaction: &ModelIrLinearReactionResultIrV1, component: usize) -> &str {
    if component < 3 {
        &reaction.units.translational_components
    } else {
        &reaction.units.rotational_components
    }
}

fn window_error(detail: impl Into<String>) -> WorkbenchError {
    WorkbenchError::new("workbench_reaction_view_window_invalid", detail)
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
    use super::{window_error, WORKBENCH_REACTION_VIEW_MAX_COUNT_V1};

    #[test]
    fn reaction_view_window_error_is_stable() {
        let error = window_error(format!(
            "count must be in 1..={WORKBENCH_REACTION_VIEW_MAX_COUNT_V1}"
        ));
        assert_eq!(error.code, "workbench_reaction_view_window_invalid");
    }
}
