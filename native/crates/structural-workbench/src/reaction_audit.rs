use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::model_linear_reactions::ModelIrLinearReactionResultDocumentV1;
use structural_contracts::model_linear_recovery::ModelIrLinearResultRecoveryDocumentV1;
use structural_contracts::product_ir::sha256_identity;

use crate::{WorkbenchError, WorkbenchReportLocaleV1};

const REACTION_AUDIT_SCHEMA_V1: &str =
    "structural-native-workbench-model-ir-linear-reaction-audit.v1";
const DOFS_PER_NODE: usize = 6;
const NUMERIC_TOLERANCE_MULTIPLIER: f64 = 256.0;

#[derive(Clone, Copy, Debug)]
struct ResultantAudit {
    applied_force: [f64; 3],
    applied_moment: [f64; 3],
    reaction_force: [f64; 3],
    reaction_moment: [f64; 3],
    force_residual: [f64; 3],
    moment_residual: [f64; 3],
    force_scale: f64,
    moment_scale: f64,
    force_tolerance: f64,
    moment_tolerance: f64,
    active_residual_inf: f64,
    active_residual_scale: f64,
    active_residual_tolerance: f64,
}

impl ResultantAudit {
    fn force_within_tolerance(self) -> bool {
        infinity_norm(self.force_residual) <= self.force_tolerance
    }

    fn moment_within_tolerance(self) -> bool {
        infinity_norm(self.moment_residual) <= self.moment_tolerance
    }

    fn active_within_tolerance(self) -> bool {
        self.active_residual_inf <= self.active_residual_tolerance
    }

    fn overall_within_tolerance(self) -> bool {
        self.force_within_tolerance()
            && self.moment_within_tolerance()
            && self.active_within_tolerance()
    }
}

/// Render an independently recomputed, deterministic algebraic global-resultant audit.
#[allow(clippy::too_many_lines)] // Keep the bilingual output contract in one auditable sequence.
pub(crate) fn render_model_ir_linear_reaction_audit(
    model: &ModelIrV2Document,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
    reaction: &ModelIrLinearReactionResultDocumentV1,
    locale: WorkbenchReportLocaleV1,
) -> Result<String, WorkbenchError> {
    let audit = compute_audit(model, recovery, reaction)?;
    let recovery = recovery.recovery();
    let reaction = reaction.result();
    let mut output = String::new();
    let korean = locale == WorkbenchReportLocaleV1::KoKr;

    push_line(
        &mut output,
        if korean {
            "Structural ModelIR 선형 Workbench - 대수적 전역 평형 감사"
        } else {
            "Structural ModelIR Linear Workbench - Algebraic Global Equilibrium Audit"
        },
    );
    push_field(
        &mut output,
        localized(korean, "Schema", "스키마"),
        REACTION_AUDIT_SCHEMA_V1,
    );
    push_field(
        &mut output,
        localized(korean, "Locale", "로케일"),
        locale.label(),
    );
    push_field(
        &mut output,
        localized(korean, "Case", "해석 사례"),
        &reaction.case_id,
    );
    push_field(
        &mut output,
        localized(korean, "Model", "모델"),
        &reaction.model_id,
    );
    push_field(
        &mut output,
        localized(korean, "Load pattern", "하중 패턴"),
        &reaction.load_pattern_id,
    );
    push_field(
        &mut output,
        localized(korean, "Authority", "권한"),
        localized(korean, "bounded candidate", "제한된 후보"),
    );
    push_field(
        &mut output,
        localized(korean, "Reference point", "기준점"),
        "model_global_origin_[0,0,0]_m",
    );
    push_field(
        &mut output,
        localized(korean, "Tolerance policy", "허용오차 정책"),
        "256*IEEE754_BINARY64_EPSILON*max(1,absolute_contribution_scale)",
    );
    push_field(
        &mut output,
        localized(korean, "Status vocabulary", "상태 용어"),
        "within_numeric_tolerance|outside_numeric_tolerance",
    );
    push_line(&mut output, "");

    push_vector_section(
        &mut output,
        korean,
        "Applied force resultant",
        "적용 하중 합력",
        audit.applied_force,
        "N",
    );
    push_vector_section(
        &mut output,
        korean,
        "Support reaction force resultant",
        "지점 반력 합력",
        audit.reaction_force,
        "N",
    );
    push_vector_section(
        &mut output,
        korean,
        "Force closure residual",
        "힘 폐합 잔차",
        audit.force_residual,
        "N",
    );
    push_scalar(
        &mut output,
        localized(korean, "Force contribution scale", "힘 기여량 크기"),
        audit.force_scale,
        "N",
    );
    push_scalar(
        &mut output,
        localized(korean, "Force numeric tolerance", "힘 수치 허용오차"),
        audit.force_tolerance,
        "N",
    );
    push_field(
        &mut output,
        localized(korean, "Force status", "힘 상태"),
        numeric_status(audit.force_within_tolerance()),
    );
    push_line(&mut output, "");

    push_vector_section(
        &mut output,
        korean,
        "Applied moment resultant",
        "적용 하중 합모멘트",
        audit.applied_moment,
        "N*m",
    );
    push_vector_section(
        &mut output,
        korean,
        "Support reaction moment resultant",
        "지점 반력 합모멘트",
        audit.reaction_moment,
        "N*m",
    );
    push_vector_section(
        &mut output,
        korean,
        "Moment closure residual",
        "모멘트 폐합 잔차",
        audit.moment_residual,
        "N*m",
    );
    push_scalar(
        &mut output,
        localized(korean, "Moment contribution scale", "모멘트 기여량 크기"),
        audit.moment_scale,
        "N*m",
    );
    push_scalar(
        &mut output,
        localized(korean, "Moment numeric tolerance", "모멘트 수치 허용오차"),
        audit.moment_tolerance,
        "N*m",
    );
    push_field(
        &mut output,
        localized(korean, "Moment status", "모멘트 상태"),
        numeric_status(audit.moment_within_tolerance()),
    );
    push_line(&mut output, "");

    push_scalar(
        &mut output,
        localized(
            korean,
            "Active equation residual infinity norm",
            "활성 방정식 잔차 무한 노름",
        ),
        audit.active_residual_inf,
        "generalized_N_or_N*m",
    );
    push_scalar(
        &mut output,
        localized(
            korean,
            "Active equation contribution scale",
            "활성 방정식 기여량 크기",
        ),
        audit.active_residual_scale,
        "generalized_N_or_N*m",
    );
    push_scalar(
        &mut output,
        localized(
            korean,
            "Active equation numeric tolerance",
            "활성 방정식 수치 허용오차",
        ),
        audit.active_residual_tolerance,
        "generalized_N_or_N*m",
    );
    push_field(
        &mut output,
        localized(korean, "Active equation status", "활성 방정식 상태"),
        numeric_status(audit.active_within_tolerance()),
    );
    push_field(
        &mut output,
        localized(korean, "Overall numeric status", "종합 수치 상태"),
        numeric_status(audit.overall_within_tolerance()),
    );
    push_line(&mut output, "");

    push_field(
        &mut output,
        localized(korean, "Backend", "백엔드"),
        &format!(
            "{} / {} / ABI {} / fallback {} / H2D {} / D2H {} / sync {}",
            reaction.backend_receipt.backend,
            reaction.backend_receipt.precision,
            reaction.backend_receipt.abi_version,
            reaction.backend_receipt.fallback_count,
            reaction.backend_receipt.h2d_bytes,
            reaction.backend_receipt.d2h_bytes,
            reaction.backend_receipt.sync_count,
        ),
    );
    push_field(
        &mut output,
        localized(korean, "Recovery backend", "복원 백엔드"),
        &format!(
            "{} / {} / fallback {}",
            recovery.backend, recovery.precision, recovery.fallback_count
        ),
    );
    push_identity_fields(&mut output, korean, recovery, reaction);
    push_line(&mut output, "");
    push_line(
        &mut output,
        if korean {
            "경계: 검증된 ModelIR 선형 CPU 일반화 외력과 구속 반력의 대수적 전역 합력·원점 모멘트·활성 방정식 잔차를 IEEE 754 수치 허용오차와 비교하는 제한된 읽기 전용 감사입니다. 지점 설계, 안정성·특이성 판정, 설계기준 준수, 공학적 수용, HIP 패리티를 의미하지 않습니다."
        } else {
            "Boundary: bounded read-only IEEE 754 numeric-tolerance audit of algebraic global force, global-origin moment, and active-equation residual closure from verified ModelIR linear CPU generalized external loads and constrained reactions; not support design, stability or singularity assessment, design-code compliance, engineering acceptance, or HIP parity."
        },
    );
    let audit_hash = sha256_identity(output.as_bytes());
    push_field(
        &mut output,
        localized(korean, "Audit hash", "감사 해시"),
        &audit_hash,
    );
    if output.as_bytes().contains(&0x1b) {
        return Err(audit_error(
            "workbench_reaction_audit_unsafe",
            "reaction audit unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

#[allow(clippy::too_many_lines)] // Keep the three coupled closure derivations visibly ordered.
fn compute_audit(
    model: &ModelIrV2Document,
    recovery_document: &ModelIrLinearResultRecoveryDocumentV1,
    reaction_document: &ModelIrLinearReactionResultDocumentV1,
) -> Result<ResultantAudit, WorkbenchError> {
    let recovery = recovery_document.recovery();
    let reaction = reaction_document.result();
    verify_identity(model, recovery_document, reaction_document)?;

    let global_dof_count = usize::try_from(reaction.global_dof_count).map_err(|_| {
        audit_error(
            "workbench_reaction_audit_dimension_invalid",
            "global DOF count does not fit the native address space",
        )
    })?;
    if global_dof_count == 0 || global_dof_count % DOFS_PER_NODE != 0 {
        return Err(audit_error(
            "workbench_reaction_audit_dimension_invalid",
            "global DOF count does not form complete six-DOF nodes",
        ));
    }
    let coordinates = indexed_node_coordinates(model, global_dof_count / DOFS_PER_NODE)?;
    let mut external = vec![None; global_dof_count];
    for (&index, &value) in recovery
        .active_dof_indices
        .iter()
        .zip(&recovery.active_external_load)
    {
        assign_partition_value(&mut external, index, value)?;
    }
    for (&index, &value) in reaction
        .constrained_dof_indices
        .iter()
        .zip(&reaction.constrained_external_load)
    {
        assign_partition_value(&mut external, index, value)?;
    }
    let external = external
        .into_iter()
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| {
            audit_error(
                "workbench_reaction_audit_partition_invalid",
                "active and constrained external-load partitions do not cover every global DOF",
            )
        })?;
    let mut support_reaction = vec![0.0; global_dof_count];
    for (&index, &value) in reaction
        .constrained_dof_indices
        .iter()
        .zip(&reaction.reactions)
    {
        let index = usize::try_from(index).map_err(|_| {
            audit_error(
                "workbench_reaction_audit_partition_invalid",
                "constrained reaction index does not fit the native address space",
            )
        })?;
        let target = support_reaction.get_mut(index).ok_or_else(|| {
            audit_error(
                "workbench_reaction_audit_partition_invalid",
                "constrained reaction index exceeds the global DOF count",
            )
        })?;
        *target = value;
    }

    let (applied_force, applied_moment, applied_force_scale, applied_moment_scale) =
        resultant(&coordinates, &external);
    let (reaction_force, reaction_moment, reaction_force_scale, reaction_moment_scale) =
        resultant(&coordinates, &support_reaction);
    let force_residual = add(applied_force, reaction_force);
    let moment_residual = add(applied_moment, reaction_moment);
    let force_scale = applied_force_scale + reaction_force_scale;
    let moment_scale = applied_moment_scale + reaction_moment_scale;

    let mut active_residual_inf = 0.0_f64;
    let mut active_residual_scale = 0.0_f64;
    for ((&internal, &external), &recorded) in recovery
        .active_internal_force
        .iter()
        .zip(&recovery.active_external_load)
        .zip(&recovery.active_equilibrium_residual)
    {
        let derived = canonical_zero(internal - external);
        if derived.to_bits() != recorded.to_bits() {
            return Err(audit_error(
                "workbench_reaction_audit_active_residual_invalid",
                "recorded active residual differs from the independent internal-minus-external derivation",
            ));
        }
        active_residual_inf = active_residual_inf.max(derived.abs());
        active_residual_scale += internal.abs() + external.abs();
    }
    if active_residual_inf.to_bits() != recovery.summary.active_residual_inf.to_bits() {
        return Err(audit_error(
            "workbench_reaction_audit_active_residual_invalid",
            "active residual summary differs from the independent infinity-norm derivation",
        ));
    }

    Ok(ResultantAudit {
        applied_force,
        applied_moment,
        reaction_force,
        reaction_moment,
        force_residual,
        moment_residual,
        force_scale,
        moment_scale,
        force_tolerance: numeric_tolerance(force_scale),
        moment_tolerance: numeric_tolerance(moment_scale),
        active_residual_inf,
        active_residual_scale,
        active_residual_tolerance: numeric_tolerance(active_residual_scale),
    })
}

fn verify_identity(
    model: &ModelIrV2Document,
    recovery: &ModelIrLinearResultRecoveryDocumentV1,
    reaction: &ModelIrLinearReactionResultDocumentV1,
) -> Result<(), WorkbenchError> {
    let recovery = recovery.recovery();
    let reaction = reaction.result();
    if model.model_id() != reaction.model_id
        || model.content_hash() != reaction.model_identity.content_hash
        || model.semantic_hash() != reaction.model_identity.semantic_hash
        || model.provenance_hash() != reaction.model_identity.provenance_hash
        || model.model_id() != recovery.model_id
        || model.content_hash() != recovery.model_identity.content_hash
        || model.semantic_hash() != recovery.model_identity.semantic_hash
        || model.provenance_hash() != recovery.model_identity.provenance_hash
    {
        return Err(audit_error(
            "workbench_reaction_audit_model_mismatch",
            "verified recovery and reaction identities do not match the immutable ModelIR",
        ));
    }
    Ok(())
}

fn indexed_node_coordinates(
    model: &ModelIrV2Document,
    node_count: usize,
) -> Result<Vec<[f64; 3]>, WorkbenchError> {
    let nodes = model
        .value()
        .get("nodes")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            audit_error(
                "workbench_reaction_audit_model_invalid",
                "verified ModelIR has no node array",
            )
        })?;
    if nodes.len() != node_count {
        return Err(audit_error(
            "workbench_reaction_audit_model_mismatch",
            "ModelIR node count does not match the verified global DOF count",
        ));
    }
    let mut coordinates = vec![None; node_count];
    for node in nodes {
        let index = node
            .get("index")
            .and_then(serde_json::Value::as_u64)
            .and_then(|value| usize::try_from(value).ok())
            .filter(|&value| value < node_count)
            .ok_or_else(|| {
                audit_error(
                    "workbench_reaction_audit_model_invalid",
                    "ModelIR node index is missing or outside the global DOF mapping",
                )
            })?;
        let values = node
            .get("coordinates_m")
            .and_then(serde_json::Value::as_array)
            .filter(|values| values.len() == 3)
            .ok_or_else(|| {
                audit_error(
                    "workbench_reaction_audit_model_invalid",
                    "ModelIR node coordinates are missing or not three-dimensional",
                )
            })?;
        let mut point = [0.0; 3];
        for (target, value) in point.iter_mut().zip(values) {
            *target = value
                .as_f64()
                .filter(|value| value.is_finite())
                .ok_or_else(|| {
                    audit_error(
                        "workbench_reaction_audit_model_invalid",
                        "ModelIR node coordinate is not a finite FP64 value",
                    )
                })?;
        }
        if coordinates[index].replace(point).is_some() {
            return Err(audit_error(
                "workbench_reaction_audit_model_invalid",
                "ModelIR node indices are not unique",
            ));
        }
    }
    coordinates
        .into_iter()
        .collect::<Option<Vec<_>>>()
        .ok_or_else(|| {
            audit_error(
                "workbench_reaction_audit_model_invalid",
                "ModelIR node indices do not form a complete contiguous mapping",
            )
        })
}

fn assign_partition_value(
    target: &mut [Option<f64>],
    index: u32,
    value: f64,
) -> Result<(), WorkbenchError> {
    let index = usize::try_from(index).map_err(|_| {
        audit_error(
            "workbench_reaction_audit_partition_invalid",
            "global DOF index does not fit the native address space",
        )
    })?;
    let slot = target.get_mut(index).ok_or_else(|| {
        audit_error(
            "workbench_reaction_audit_partition_invalid",
            "global DOF index exceeds the verified global DOF count",
        )
    })?;
    if slot.replace(value).is_some() {
        return Err(audit_error(
            "workbench_reaction_audit_partition_invalid",
            "active and constrained external-load partitions overlap",
        ));
    }
    Ok(())
}

fn resultant(coordinates: &[[f64; 3]], generalized: &[f64]) -> ([f64; 3], [f64; 3], f64, f64) {
    let mut force = [0.0; 3];
    let mut moment = [0.0; 3];
    let mut force_scale = 0.0;
    let mut moment_scale = 0.0;
    for (node_index, point) in coordinates.iter().enumerate() {
        let offset = node_index * DOFS_PER_NODE;
        let node_force = [
            generalized[offset],
            generalized[offset + 1],
            generalized[offset + 2],
        ];
        let node_moment = [
            generalized[offset + 3],
            generalized[offset + 4],
            generalized[offset + 5],
        ];
        force = add(force, node_force);
        moment = add(moment, add(cross(*point, node_force), node_moment));
        force_scale += node_force.iter().map(|value| value.abs()).sum::<f64>();
        moment_scale += node_moment.iter().map(|value| value.abs()).sum::<f64>()
            + point[1].mul_add(node_force[2], 0.0).abs()
            + point[2].mul_add(node_force[1], 0.0).abs()
            + point[2].mul_add(node_force[0], 0.0).abs()
            + point[0].mul_add(node_force[2], 0.0).abs()
            + point[0].mul_add(node_force[1], 0.0).abs()
            + point[1].mul_add(node_force[0], 0.0).abs();
    }
    (
        force.map(canonical_zero),
        moment.map(canonical_zero),
        force_scale,
        moment_scale,
    )
}

fn cross(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]
}

fn add(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [
        canonical_zero(left[0] + right[0]),
        canonical_zero(left[1] + right[1]),
        canonical_zero(left[2] + right[2]),
    ]
}

fn infinity_norm(values: [f64; 3]) -> f64 {
    values.into_iter().map(f64::abs).fold(0.0, f64::max)
}

fn numeric_tolerance(scale: f64) -> f64 {
    NUMERIC_TOLERANCE_MULTIPLIER * f64::EPSILON * scale.max(1.0)
}

fn canonical_zero(value: f64) -> f64 {
    if value == 0.0 {
        0.0
    } else {
        value
    }
}

fn push_identity_fields(
    output: &mut String,
    korean: bool,
    recovery: &structural_contracts::model_linear_recovery::ModelIrLinearResultRecoveryIrV1,
    reaction: &structural_contracts::model_linear_reactions::ModelIrLinearReactionResultIrV1,
) {
    for (english, translated, value) in [
        (
            "Analysis request hash",
            "분석 요청 해시",
            reaction.analysis_request_hash.as_str(),
        ),
        (
            "Assembly hash",
            "조립 해시",
            reaction.assembly_hash.as_str(),
        ),
        (
            "Model content hash",
            "모델 콘텐츠 해시",
            reaction.model_identity.content_hash.as_str(),
        ),
        (
            "Model semantic hash",
            "모델 의미 해시",
            reaction.model_identity.semantic_hash.as_str(),
        ),
        (
            "Model provenance hash",
            "모델 출처 해시",
            reaction.model_identity.provenance_hash.as_str(),
        ),
        (
            "Sparse request hash",
            "희소 요청 해시",
            reaction.identity.request_hash.as_str(),
        ),
        (
            "Sparse model hash",
            "희소 모델 해시",
            reaction.identity.model_hash.as_str(),
        ),
        (
            "State hash",
            "상태 해시",
            reaction.identity.state_hash.as_str(),
        ),
        (
            "Execution hash",
            "실행 해시",
            reaction.identity.execution_hash.as_str(),
        ),
        (
            "Checkpoint hash",
            "체크포인트 해시",
            reaction.identity.checkpoint_hash.as_str(),
        ),
        (
            "Source result hash",
            "소스 결과 해시",
            reaction.source_result_hash.as_str(),
        ),
        (
            "Recovery hash",
            "복원 해시",
            recovery.recovery_hash.as_str(),
        ),
        ("Reaction hash", "반력 해시", reaction.result_hash.as_str()),
    ] {
        push_field(output, localized(korean, english, translated), value);
    }
}

fn push_vector_section(
    output: &mut String,
    korean: bool,
    english: &str,
    translated: &str,
    values: [f64; 3],
    unit: &str,
) {
    push_field(
        output,
        localized(korean, english, translated),
        &format!(
            "X={:+.17e}; Y={:+.17e}; Z={:+.17e} {unit}",
            values[0], values[1], values[2]
        ),
    );
}

fn push_scalar(output: &mut String, label: &str, value: f64, unit: &str) {
    push_field(output, label, &format!("{value:+.17e} {unit}"));
}

fn numeric_status(within: bool) -> &'static str {
    if within {
        "within_numeric_tolerance"
    } else {
        "outside_numeric_tolerance"
    }
}

fn localized<'a>(korean: bool, english: &'a str, translated: &'a str) -> &'a str {
    if korean {
        translated
    } else {
        english
    }
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

fn audit_error(code: &'static str, detail: &'static str) -> WorkbenchError {
    WorkbenchError::new(code, detail)
}

#[cfg(test)]
mod tests {
    use super::{numeric_status, numeric_tolerance, resultant};

    #[test]
    fn resultant_includes_force_lever_arm_and_nodal_moment() {
        let coordinates = [[0.0, 0.0, 0.0], [2.0, 3.0, 4.0]];
        let generalized = [
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0, 7.0, 11.0, 13.0, 17.0, 19.0,
        ];
        let (force, moment, force_scale, moment_scale) = resultant(&coordinates, &generalized);
        assert_eq!(force.map(f64::to_bits), [5.0, 7.0, 11.0].map(f64::to_bits));
        assert_eq!(
            moment.map(f64::to_bits),
            [18.0, 15.0, 18.0].map(f64::to_bits)
        );
        assert_eq!(force_scale.to_bits(), 23.0_f64.to_bits());
        assert_eq!(moment_scale.to_bits(), 181.0_f64.to_bits());
    }

    #[test]
    fn tolerance_and_status_vocabulary_are_fixed() {
        assert_eq!(
            numeric_tolerance(0.0).to_bits(),
            (256.0 * f64::EPSILON).to_bits()
        );
        assert_eq!(numeric_status(true), "within_numeric_tolerance");
        assert_eq!(numeric_status(false), "outside_numeric_tolerance");
    }
}
