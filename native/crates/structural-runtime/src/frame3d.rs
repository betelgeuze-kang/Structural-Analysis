use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value};
use structural_contracts::model_ir::ModelIrV2Document;
use structural_contracts::result_ir::{
    create_linear_frame3d_result_ir_v1, Frame3dResultBindingsV1, Frame3dResultGatesV1,
    Frame3dResultMemberV1, Frame3dResultNodeV1, LinearFrame3dResultIrInput,
    LinearFrame3dResultIrV1,
};
use structural_ffi::{
    LinearFrame3dMember, LinearFrame3dNode, LinearFrame3dSection, LinearFrame3dUniformMemberLoad,
};

use crate::RuntimeError;

const INVALID_ARGUMENT: u32 = 1000;
const SEMANTIC_INVALID: u32 = 1101;
const ANALYSIS_NOT_READY: u32 = 1102;
const UNSUPPORTED: u32 = 1200;
const INTERNAL: u32 = 1900;
const FORCE_TO_KILO: f64 = 1.0 / 1000.0;
const KILO_TO_FORCE: f64 = 1000.0;
const DOF_NAMES: [&str; 6] = ["UX", "UY", "UZ", "RX", "RY", "RZ"];
const LOAD_NAMES: [&str; 6] = ["FX", "FY", "FZ", "MX", "MY", "MZ"];
const RESULT_GATE_TOLERANCE: f64 = 1.0e-9;

/// One node row in the authority-limited native linear `Frame3D` result.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dNodeResult {
    pub node_id: String,
    pub displacement_m_rad: [f64; 6],
    pub reaction_n_nm: [f64; 6],
}

/// One member row in the authority-limited native linear `Frame3D` result.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dMemberResult {
    pub member_id: String,
    pub end_i_force_n_nm: [f64; 6],
    pub end_j_force_n_nm: [f64; 6],
}

/// Independent output and global-resultant checks observed after the native solve.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dGateMetrics {
    pub free_residual_scaled_linf: f64,
    pub global_force_balance_scaled_linf: f64,
    pub global_moment_balance_scaled_linf: f64,
    pub member_force_replay_scaled_linf: f64,
}

/// Hash-bound result of the bounded `ModelIR` -> native CPU `Frame3D` path.
#[derive(Clone, Debug, PartialEq)]
pub struct LinearFrame3dAnalysisResult {
    pub schema_version: &'static str,
    pub model_id: String,
    pub model_content_hash: String,
    pub model_semantic_hash: String,
    pub model_provenance_hash: String,
    pub load_pattern_id: String,
    pub native_abi_version: u32,
    pub gates: LinearFrame3dGateMetrics,
    pub nodes: Vec<LinearFrame3dNodeResult>,
    pub members: Vec<LinearFrame3dMemberResult>,
    pub claim_boundary: &'static str,
}

pub(crate) struct PreparedFrame3d {
    pub nodes: Vec<LinearFrame3dNode>,
    pub sections: Vec<LinearFrame3dSection>,
    pub members: Vec<LinearFrame3dMember>,
    pub restrained_dofs: Vec<u32>,
    pub nodal_loads_kn_knm: Vec<f64>,
    pub loads_kn_knm: Vec<f64>,
    pub uniform_member_loads: Vec<LinearFrame3dUniformMemberLoad>,
    pub node_ids: Vec<String>,
    pub member_ids: Vec<String>,
}

struct PreparedElements {
    sections: Vec<LinearFrame3dSection>,
    members: Vec<LinearFrame3dMember>,
    member_ids: Vec<String>,
}

struct PreparedLoads {
    nodal_kn_knm: Vec<f64>,
    assembled_kn_knm: Vec<f64>,
    uniform_member_loads: Vec<LinearFrame3dUniformMemberLoad>,
}

pub(crate) fn prepare(
    document: &ModelIrV2Document,
    load_pattern_id: &str,
) -> Result<PreparedFrame3d, RuntimeError> {
    if document.capability_profile() != "engine_v2_phase0_linear_3d" {
        return Err(unsupported(
            "/capability_profile",
            "native linear Frame3D requires engine_v2_phase0_linear_3d",
        ));
    }
    let root = object(document.value(), "/")?;
    require_canonical_context(root)?;
    require_empty_array(root, "unsupported_features")?;
    require_empty_array(root, "load_combinations")?;
    require_empty_array(root, "time_functions")?;
    require_empty_array(root, "construction_stages")?;
    require_empty_extensions(root, "/extensions")?;

    let node_rows = array_field(root, "nodes", "/")?;
    let mut nodes = Vec::with_capacity(node_rows.len());
    let mut node_ids = Vec::with_capacity(node_rows.len());
    let mut node_lookup = BTreeMap::new();
    for (position, value) in node_rows.iter().enumerate() {
        let path = format!("/nodes/{position}");
        let row = object(value, &path)?;
        require_dense_index(row, position, &path)?;
        require_empty_extensions(row, &format!("{path}/extensions"))?;
        let id = string_field(row, "id", &path)?.to_owned();
        let coordinates = fixed_f64::<3>(
            field(row, "coordinates_m", &path)?,
            &format!("{path}/coordinates_m"),
        )?;
        let node_index = u32::try_from(position)
            .map_err(|_| invalid(&path, "node index exceeds the native range"))?;
        if node_lookup.insert(id.clone(), node_index).is_some() {
            return Err(invalid(&format!("{path}/id"), "duplicate node id"));
        }
        node_ids.push(id);
        nodes.push(LinearFrame3dNode::new(
            coordinates[0],
            coordinates[1],
            coordinates[2],
        ));
    }

    let materials = prepare_materials(root)?;
    let section_rows = prepare_sections(root)?;
    let prepared_elements = prepare_elements(root, &node_lookup, &materials, &section_rows)?;

    let restrained_dofs = prepare_constraints(root, &node_lookup)?;
    let member_lookup = prepared_elements
        .member_ids
        .iter()
        .enumerate()
        .map(|(index, id)| (id.clone(), index))
        .collect::<BTreeMap<_, _>>();
    let prepared_loads = prepare_loads(
        root,
        load_pattern_id,
        &node_lookup,
        &member_lookup,
        &nodes,
        &prepared_elements.sections,
        &prepared_elements.members,
    )?;
    Ok(PreparedFrame3d {
        nodes,
        sections: prepared_elements.sections,
        members: prepared_elements.members,
        restrained_dofs,
        nodal_loads_kn_knm: prepared_loads.nodal_kn_knm,
        loads_kn_knm: prepared_loads.assembled_kn_knm,
        uniform_member_loads: prepared_loads.uniform_member_loads,
        node_ids,
        member_ids: prepared_elements.member_ids,
    })
}

fn prepare_elements(
    root: &Map<String, Value>,
    node_lookup: &BTreeMap<String, u32>,
    materials: &BTreeMap<String, Material>,
    section_rows: &BTreeMap<String, Section>,
) -> Result<PreparedElements, RuntimeError> {
    let element_rows = array_field(root, "elements", "/")?;
    let mut sections = Vec::with_capacity(element_rows.len());
    let mut members = Vec::with_capacity(element_rows.len());
    let mut member_ids = Vec::with_capacity(element_rows.len());
    let mut member_id_set = BTreeSet::new();
    for (position, value) in element_rows.iter().enumerate() {
        let path = format!("/elements/{position}");
        let row = object(value, &path)?;
        require_dense_index(row, position, &path)?;
        require_exact_string(row, "type", "frame_3d", &path)?;
        require_exact_string(row, "formulation", "linear_timoshenko_frame3d", &path)?;
        require_empty_extensions(row, &format!("{path}/extensions"))?;
        require_zero_offsets(row, &path)?;
        let release_masks = prepare_rotational_releases(row, &path)?;
        let endpoints = array_field(row, "node_ids", &path)?;
        if endpoints.len() != 2 {
            return Err(invalid(
                &format!("{path}/node_ids"),
                "Frame3D member requires exactly two node ids",
            ));
        }
        let first_node_id = string(&endpoints[0], &format!("{path}/node_ids/0"))?;
        let second_node_id = string(&endpoints[1], &format!("{path}/node_ids/1"))?;
        let node_i = *node_lookup
            .get(first_node_id)
            .ok_or_else(|| invalid(&format!("{path}/node_ids/0"), "member node id is unknown"))?;
        let node_j = *node_lookup
            .get(second_node_id)
            .ok_or_else(|| invalid(&format!("{path}/node_ids/1"), "member node id is unknown"))?;
        let material_id = string_field(row, "material_id", &path)?;
        let material = materials.get(material_id).ok_or_else(|| {
            invalid(
                &format!("{path}/material_id"),
                "member material id is unknown",
            )
        })?;
        let section_id = string_field(row, "section_id", &path)?;
        let section = section_rows.get(section_id).ok_or_else(|| {
            invalid(
                &format!("{path}/section_id"),
                "member section id is unknown",
            )
        })?;
        sections.push(LinearFrame3dSection::new(
            section.area_m2,
            material.elastic_modulus_pa * FORCE_TO_KILO,
            material.shear_modulus_pa * FORCE_TO_KILO,
            section.iy_m4,
            section.iz_m4,
            section.j_m4,
            section.shear_area_y_m2,
            section.shear_area_z_m2,
        ));
        let section_index = u32::try_from(position)
            .map_err(|_| invalid(&path, "section index exceeds the native range"))?;
        let mut member = LinearFrame3dMember::new(node_i, node_j, section_index);
        member.local_axis_roll_deg = f64_field(row, "local_axis_rotation_rad", &path)?.to_degrees();
        member.released_dof_mask_i = release_masks[0];
        member.released_dof_mask_j = release_masks[1];
        members.push(member);
        let member_id = string_field(row, "id", &path)?.to_owned();
        if !member_id_set.insert(member_id.clone()) {
            return Err(invalid(&format!("{path}/id"), "duplicate member id"));
        }
        member_ids.push(member_id);
    }
    Ok(PreparedElements {
        sections,
        members,
        member_ids,
    })
}

pub(crate) fn project_result(
    document: &ModelIrV2Document,
    load_pattern_id: &str,
    abi_version: u32,
    prepared: &PreparedFrame3d,
    result: &structural_ffi::LinearFrame3dResult,
) -> Result<LinearFrame3dAnalysisResult, RuntimeError> {
    let node_count = prepared.node_ids.len();
    let member_count = prepared.member_ids.len();
    if result.displacements.len() != node_count * 6
        || result.reactions.len() != node_count * 6
        || result.member_end_forces.len() != member_count * 12
    {
        return Err(RuntimeError {
            code: INTERNAL,
            message: "native Frame3D result shape changed after checked compilation".to_owned(),
        });
    }
    let nodes = prepared
        .node_ids
        .iter()
        .enumerate()
        .map(|(index, node_id)| {
            let start = index * 6;
            let mut displacement_m_rad = [0.0; 6];
            let mut reaction_n_nm = [0.0; 6];
            displacement_m_rad.copy_from_slice(&result.displacements[start..start + 6]);
            for (target, value) in reaction_n_nm
                .iter_mut()
                .zip(&result.reactions[start..start + 6])
            {
                *target = *value * KILO_TO_FORCE;
            }
            LinearFrame3dNodeResult {
                node_id: node_id.clone(),
                displacement_m_rad,
                reaction_n_nm,
            }
        })
        .collect::<Vec<_>>();
    let members = prepared
        .member_ids
        .iter()
        .enumerate()
        .map(|(index, member_id)| {
            let start = index * 12;
            let mut near_end_force = [0.0; 6];
            let mut far_end_force = [0.0; 6];
            for (target, value) in near_end_force
                .iter_mut()
                .zip(&result.member_end_forces[start..start + 6])
            {
                *target = *value * KILO_TO_FORCE;
            }
            for (target, value) in far_end_force
                .iter_mut()
                .zip(&result.member_end_forces[start + 6..start + 12])
            {
                *target = *value * KILO_TO_FORCE;
            }
            LinearFrame3dMemberResult {
                member_id: member_id.clone(),
                end_i_force_n_nm: near_end_force,
                end_j_force_n_nm: far_end_force,
            }
        })
        .collect::<Vec<_>>();
    let projection_is_finite = nodes.iter().all(|node| {
        node.displacement_m_rad
            .iter()
            .all(|value| value.is_finite())
            && node.reaction_n_nm.iter().all(|value| value.is_finite())
    }) && members.iter().all(|member| {
        member
            .end_i_force_n_nm
            .iter()
            .chain(&member.end_j_force_n_nm)
            .all(|value| value.is_finite())
    });
    if !projection_is_finite {
        return Err(RuntimeError {
            code: INTERNAL,
            message: "native Frame3D result is non-finite after SI projection".to_owned(),
        });
    }
    let gates = result_gate_metrics(prepared, result)?;
    Ok(LinearFrame3dAnalysisResult {
        schema_version: "structural-native-linear-frame3d-result.v1",
        model_id: document.model_id().to_owned(),
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        load_pattern_id: load_pattern_id.to_owned(),
        native_abi_version: abi_version,
        gates,
        nodes,
        members,
        claim_boundary: "bounded_cpu_linear_timoshenko_frame3d_rotational_end_release_not_resultir_or_release_authority",
    })
}

pub(crate) fn promote_result_ir(
    raw: &LinearFrame3dAnalysisResult,
    result_id: &str,
) -> Result<LinearFrame3dResultIrV1, RuntimeError> {
    create_linear_frame3d_result_ir_v1(LinearFrame3dResultIrInput {
        result_id: result_id.to_owned(),
        bindings: Frame3dResultBindingsV1 {
            model_id: raw.model_id.clone(),
            model_content_hash: raw.model_content_hash.clone(),
            model_semantic_hash: raw.model_semantic_hash.clone(),
            model_provenance_hash: raw.model_provenance_hash.clone(),
            load_pattern_id: raw.load_pattern_id.clone(),
            native_abi_version: raw.native_abi_version,
        },
        gates: Frame3dResultGatesV1 {
            native_residual_gate_passed: true,
            free_residual_scaled_linf: raw.gates.free_residual_scaled_linf,
            free_residual_scaled_linf_tolerance: RESULT_GATE_TOLERANCE,
            global_force_balance_scaled_linf: raw.gates.global_force_balance_scaled_linf,
            global_force_balance_scaled_linf_tolerance: RESULT_GATE_TOLERANCE,
            global_moment_balance_scaled_linf: raw.gates.global_moment_balance_scaled_linf,
            global_moment_balance_scaled_linf_tolerance: RESULT_GATE_TOLERANCE,
            global_resultant_gate_passed: true,
            independent_recovery_replay_passed: true,
            member_force_replay_scaled_linf: raw.gates.member_force_replay_scaled_linf,
            member_force_replay_scaled_linf_tolerance: RESULT_GATE_TOLERANCE,
            zero_prescribed_displacement_gate_passed: true,
            fallback_count: 0,
            regularization_count: 0,
        },
        nodes: raw
            .nodes
            .iter()
            .map(|node| Frame3dResultNodeV1 {
                node_id: node.node_id.clone(),
                displacement_m_rad: node.displacement_m_rad,
                reaction_n_nm: node.reaction_n_nm,
            })
            .collect(),
        members: raw
            .members
            .iter()
            .map(|member| Frame3dResultMemberV1 {
                member_id: member.member_id.clone(),
                end_i_force_n_nm: member.end_i_force_n_nm,
                end_j_force_n_nm: member.end_j_force_n_nm,
            })
            .collect(),
    })
    .map_err(|source| RuntimeError {
        code: if source.code == "frame3d_result_ir_id_invalid" {
            INVALID_ARGUMENT
        } else {
            INTERNAL
        },
        message: source.to_string(),
    })
}

fn result_gate_metrics(
    prepared: &PreparedFrame3d,
    result: &structural_ffi::LinearFrame3dResult,
) -> Result<LinearFrame3dGateMetrics, RuntimeError> {
    let free_residual = free_residual_metric(prepared, result);
    let member_force_replay = member_force_replay_metric(prepared, result)?;

    let mut applied_resultant = [0.0; 6];
    let mut reaction_resultant = [0.0; 6];
    let mut force_scale = 1.0_f64;
    let mut moment_scale = 1.0_f64;
    for (node_index, node) in prepared.nodes.iter().enumerate() {
        let start = node_index * 6;
        let applied_force = [
            prepared.loads_kn_knm[start] * KILO_TO_FORCE,
            prepared.loads_kn_knm[start + 1] * KILO_TO_FORCE,
            prepared.loads_kn_knm[start + 2] * KILO_TO_FORCE,
        ];
        let applied_moment = [
            prepared.loads_kn_knm[start + 3] * KILO_TO_FORCE,
            prepared.loads_kn_knm[start + 4] * KILO_TO_FORCE,
            prepared.loads_kn_knm[start + 5] * KILO_TO_FORCE,
        ];
        let reaction_force = [
            result.reactions[start] * KILO_TO_FORCE,
            result.reactions[start + 1] * KILO_TO_FORCE,
            result.reactions[start + 2] * KILO_TO_FORCE,
        ];
        let reaction_moment = [
            result.reactions[start + 3] * KILO_TO_FORCE,
            result.reactions[start + 4] * KILO_TO_FORCE,
            result.reactions[start + 5] * KILO_TO_FORCE,
        ];
        let coordinates = [node.x_m, node.y_m, node.z_m];
        accumulate_resultant(
            &mut applied_resultant,
            coordinates,
            applied_force,
            applied_moment,
        );
        accumulate_resultant(
            &mut reaction_resultant,
            coordinates,
            reaction_force,
            reaction_moment,
        );
        force_scale += applied_force
            .iter()
            .chain(&reaction_force)
            .map(|value| value.abs())
            .sum::<f64>();
        moment_scale += applied_moment
            .iter()
            .chain(&reaction_moment)
            .map(|value| value.abs())
            .sum::<f64>();
        moment_scale += cross(coordinates, applied_force)
            .iter()
            .chain(&cross(coordinates, reaction_force))
            .map(|value| value.abs())
            .sum::<f64>();
    }
    let imbalance = std::array::from_fn::<_, 6, _>(|index| {
        applied_resultant[index] + reaction_resultant[index]
    });
    let force_balance = imbalance[..3]
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max)
        / force_scale;
    let moment_balance = imbalance[3..]
        .iter()
        .map(|value| value.abs())
        .fold(0.0_f64, f64::max)
        / moment_scale;
    let metrics = LinearFrame3dGateMetrics {
        free_residual_scaled_linf: free_residual,
        global_force_balance_scaled_linf: force_balance,
        global_moment_balance_scaled_linf: moment_balance,
        member_force_replay_scaled_linf: member_force_replay,
    };
    if [
        free_residual,
        force_balance,
        moment_balance,
        member_force_replay,
    ]
    .iter()
    .any(|value| !value.is_finite() || *value > RESULT_GATE_TOLERANCE)
    {
        return Err(RuntimeError {
            code: INTERNAL,
            message:
                "native Frame3D output failed ResultIR numerical, equilibrium or recovery gates"
                    .to_owned(),
        });
    }
    Ok(metrics)
}

fn member_force_replay_metric(
    prepared: &PreparedFrame3d,
    result: &structural_ffi::LinearFrame3dResult,
) -> Result<f64, RuntimeError> {
    let mut scaled_linf = 0.0_f64;
    for (member_index, member) in prepared.members.iter().enumerate() {
        let node_i = usize::try_from(member.node_i).map_err(|_| recovery_replay_error())?;
        let node_j = usize::try_from(member.node_j).map_err(|_| recovery_replay_error())?;
        let section_index =
            usize::try_from(member.section_index).map_err(|_| recovery_replay_error())?;
        let start = prepared
            .nodes
            .get(node_i)
            .ok_or_else(recovery_replay_error)?;
        let end = prepared
            .nodes
            .get(node_j)
            .ok_or_else(recovery_replay_error)?;
        let section = prepared
            .sections
            .get(section_index)
            .ok_or_else(recovery_replay_error)?;
        let delta = [
            end.x_m - start.x_m,
            end.y_m - start.y_m,
            end.z_m - start.z_m,
        ];
        let length = vector_norm(delta);
        let rotation = recovery_rotation(delta, member.local_axis_roll_deg)?;
        let stiffness = recovery_local_stiffness(section, length)?;
        let start_displacement = recovery_node_displacement(result, node_i)?;
        let end_displacement = recovery_node_displacement(result, node_j)?;
        let mut global_displacement = [0.0_f64; 12];
        global_displacement[..6].copy_from_slice(start_displacement);
        global_displacement[6..].copy_from_slice(end_displacement);
        let mut local_displacement = [0.0_f64; 12];
        for offset in [0_usize, 3, 6, 9] {
            for row in 0..3 {
                for column in 0..3 {
                    local_displacement[offset + row] +=
                        rotation[row * 3 + column] * global_displacement[offset + column];
                }
            }
        }
        let mut equivalent_local_load = [0.0_f64; 12];
        for load in prepared
            .uniform_member_loads
            .iter()
            .filter(|load| usize::try_from(load.member_index).ok() == Some(member_index))
        {
            let row = uniform_member_equivalent_local_load(length, load.components_kn_per_m)?;
            for (accumulated, value) in equivalent_local_load.iter_mut().zip(row) {
                *accumulated += value;
            }
        }
        let (stiffness, equivalent_local_load) = recovery_condense_releases(
            &stiffness,
            equivalent_local_load,
            member.released_dof_mask_i,
            member.released_dof_mask_j,
        )?;
        for row in 0..12 {
            let mut replayed = -equivalent_local_load[row];
            for column in 0..12 {
                replayed += stiffness[row * 12 + column] * local_displacement[column];
            }
            let force_index = member_index
                .checked_mul(12)
                .and_then(|start| start.checked_add(row))
                .ok_or_else(recovery_replay_error)?;
            let native = *result
                .member_end_forces
                .get(force_index)
                .ok_or_else(recovery_replay_error)?;
            if !replayed.is_finite() || !native.is_finite() {
                return Err(recovery_replay_error());
            }
            let scale = 1.0_f64.max(replayed.abs()).max(native.abs());
            scaled_linf = scaled_linf.max((replayed - native).abs() / scale);
        }
    }
    Ok(scaled_linf)
}

fn recovery_node_displacement(
    result: &structural_ffi::LinearFrame3dResult,
    node_index: usize,
) -> Result<&[f64], RuntimeError> {
    let range_start = node_index
        .checked_mul(6)
        .ok_or_else(recovery_replay_error)?;
    let range_end = range_start
        .checked_add(6)
        .ok_or_else(recovery_replay_error)?;
    result
        .displacements
        .get(range_start..range_end)
        .ok_or_else(recovery_replay_error)
}

fn uniform_member_equivalent_local_load(
    length: f64,
    components_kn_per_m: [f64; 3],
) -> Result<[f64; 12], RuntimeError> {
    if !length.is_finite()
        || length <= 1.0e-12
        || !components_kn_per_m.iter().all(|value| value.is_finite())
    {
        return Err(recovery_replay_error());
    }
    let half_length = 0.5 * length;
    let twelfth_length_squared = length * length / 12.0;
    let axial = components_kn_per_m[0] * half_length;
    let transverse_y = components_kn_per_m[1] * half_length;
    let transverse_z = components_kn_per_m[2] * half_length;
    let moment_z = components_kn_per_m[1] * twelfth_length_squared;
    let moment_y = components_kn_per_m[2] * twelfth_length_squared;
    let load = [
        axial,
        transverse_y,
        transverse_z,
        0.0,
        -moment_y,
        moment_z,
        axial,
        transverse_y,
        transverse_z,
        0.0,
        moment_y,
        -moment_z,
    ];
    if load.iter().all(|value| value.is_finite()) {
        Ok(load)
    } else {
        Err(recovery_replay_error())
    }
}

fn recovery_rotation(delta: [f64; 3], roll_deg: f64) -> Result<[f64; 9], RuntimeError> {
    let x_axis = normalize_vector(delta).ok_or_else(recovery_replay_error)?;
    let reference = if vector_dot(x_axis, [0.0, 0.0, 1.0]).abs() > 0.95 {
        [0.0, 1.0, 0.0]
    } else {
        [0.0, 0.0, 1.0]
    };
    let mut y_axis =
        normalize_vector(cross(reference, x_axis)).ok_or_else(recovery_replay_error)?;
    let mut z_axis = normalize_vector(cross(x_axis, y_axis)).ok_or_else(recovery_replay_error)?;
    if roll_deg.abs() > 1.0e-14 {
        let angle = roll_deg.to_radians();
        let (sine, cosine) = angle.sin_cos();
        let y_base = y_axis;
        let z_base = z_axis;
        for index in 0..3 {
            y_axis[index] = cosine * y_base[index] + sine * z_base[index];
            z_axis[index] = -sine * y_base[index] + cosine * z_base[index];
        }
    }
    let rotation = [
        x_axis[0], x_axis[1], x_axis[2], y_axis[0], y_axis[1], y_axis[2], z_axis[0], z_axis[1],
        z_axis[2],
    ];
    if rotation.iter().all(|value| value.is_finite()) {
        Ok(rotation)
    } else {
        Err(recovery_replay_error())
    }
}

fn recovery_local_stiffness(
    section: &LinearFrame3dSection,
    length: f64,
) -> Result<[f64; 144], RuntimeError> {
    if !length.is_finite() || length <= 1.0e-12 {
        return Err(recovery_replay_error());
    }
    let mut stiffness = [0.0_f64; 144];
    recovery_add_pair(
        &mut stiffness,
        0,
        6,
        section.elastic_modulus_kn_per_m2 * section.area_m2 / length,
    );
    recovery_add_pair(
        &mut stiffness,
        3,
        9,
        section.shear_modulus_kn_per_m2 * section.j_m4 / length,
    );

    let phi_z = 12.0 * section.elastic_modulus_kn_per_m2 * section.iz_m4
        / (section.shear_modulus_kn_per_m2 * section.effective_shear_area_y_m2 * length * length);
    let factor_z = section.elastic_modulus_kn_per_m2 * section.iz_m4
        / (length * length * length * (1.0 + phi_z));
    let six_l_z = 6.0 * length;
    recovery_scatter_bending(
        &mut stiffness,
        [1, 5, 7, 11],
        [
            12.0 * factor_z,
            six_l_z * factor_z,
            -12.0 * factor_z,
            six_l_z * factor_z,
            six_l_z * factor_z,
            (4.0 + phi_z) * length * length * factor_z,
            -six_l_z * factor_z,
            (2.0 - phi_z) * length * length * factor_z,
            -12.0 * factor_z,
            -six_l_z * factor_z,
            12.0 * factor_z,
            -six_l_z * factor_z,
            six_l_z * factor_z,
            (2.0 - phi_z) * length * length * factor_z,
            -six_l_z * factor_z,
            (4.0 + phi_z) * length * length * factor_z,
        ],
    );

    let phi_y = 12.0 * section.elastic_modulus_kn_per_m2 * section.iy_m4
        / (section.shear_modulus_kn_per_m2 * section.effective_shear_area_z_m2 * length * length);
    let factor_y = section.elastic_modulus_kn_per_m2 * section.iy_m4
        / (length * length * length * (1.0 + phi_y));
    let six_l_y = -6.0 * length;
    recovery_scatter_bending(
        &mut stiffness,
        [2, 4, 8, 10],
        [
            12.0 * factor_y,
            six_l_y * factor_y,
            -12.0 * factor_y,
            six_l_y * factor_y,
            six_l_y * factor_y,
            (4.0 + phi_y) * length * length * factor_y,
            -six_l_y * factor_y,
            (2.0 - phi_y) * length * length * factor_y,
            -12.0 * factor_y,
            -six_l_y * factor_y,
            12.0 * factor_y,
            -six_l_y * factor_y,
            six_l_y * factor_y,
            (2.0 - phi_y) * length * length * factor_y,
            -six_l_y * factor_y,
            (4.0 + phi_y) * length * length * factor_y,
        ],
    );
    for row in 0..12 {
        for column in row + 1..12 {
            let value = 0.5 * (stiffness[row * 12 + column] + stiffness[column * 12 + row]);
            stiffness[row * 12 + column] = value;
            stiffness[column * 12 + row] = value;
        }
    }
    if stiffness.iter().all(|value| value.is_finite()) {
        Ok(stiffness)
    } else {
        Err(recovery_replay_error())
    }
}

fn recovery_condense_releases(
    original: &[f64; 144],
    original_load: [f64; 12],
    released_dof_mask_i: u32,
    released_dof_mask_j: u32,
) -> Result<([f64; 144], [f64; 12]), RuntimeError> {
    let mut released = Vec::with_capacity(6);
    for local in 3..6 {
        let bit = 1_u32 << local;
        if released_dof_mask_i & bit != 0 {
            released.push(local);
        }
        if released_dof_mask_j & bit != 0 {
            released.push(local + 6);
        }
    }
    if released.is_empty() {
        return Ok((*original, original_load));
    }
    let count = released.len();
    let width = count * 2;
    let mut augmented = vec![0.0_f64; count * width];
    for row in 0..count {
        let row_scale = (0..count)
            .map(|column| original[released[row] * 12 + released[column]].abs())
            .fold(0.0_f64, f64::max);
        if !row_scale.is_finite() || row_scale <= 0.0 {
            return Err(recovery_replay_error());
        }
        for column in 0..count {
            augmented[row * width + column] =
                original[released[row] * 12 + released[column]] / row_scale;
        }
        augmented[row * width + count + row] = 1.0 / row_scale;
    }
    for column in 0..count {
        let pivot_row = (column..count)
            .max_by(|left, right| {
                augmented[*left * width + column]
                    .abs()
                    .total_cmp(&augmented[*right * width + column].abs())
            })
            .ok_or_else(recovery_replay_error)?;
        let pivot = augmented[pivot_row * width + column];
        if !pivot.is_finite() || pivot.abs() <= 1.0e-13 {
            return Err(recovery_replay_error());
        }
        if pivot_row != column {
            for entry in 0..width {
                augmented.swap(column * width + entry, pivot_row * width + entry);
            }
        }
        let pivot = augmented[column * width + column];
        for entry in 0..width {
            augmented[column * width + entry] /= pivot;
        }
        for row in 0..count {
            if row == column {
                continue;
            }
            let factor = augmented[row * width + column];
            for entry in 0..width {
                augmented[row * width + entry] -= factor * augmented[column * width + entry];
            }
        }
    }
    let inverse = |row: usize, column: usize| augmented[row * width + count + column];
    let released_set = released.iter().copied().collect::<BTreeSet<_>>();
    let mut condensed = [0.0_f64; 144];
    let mut condensed_load = [0.0_f64; 12];
    for row in 0..12 {
        if released_set.contains(&row) {
            continue;
        }
        condensed_load[row] = original_load[row];
        for left in 0..count {
            for right in 0..count {
                condensed_load[row] -= original[row * 12 + released[left]]
                    * inverse(left, right)
                    * original_load[released[right]];
            }
        }
        for column in 0..12 {
            if released_set.contains(&column) {
                continue;
            }
            condensed[row * 12 + column] = original[row * 12 + column];
            for left in 0..count {
                for right in 0..count {
                    condensed[row * 12 + column] -= original[row * 12 + released[left]]
                        * inverse(left, right)
                        * original[released[right] * 12 + column];
                }
            }
        }
    }
    if condensed
        .iter()
        .chain(&condensed_load)
        .all(|value| value.is_finite())
    {
        Ok((condensed, condensed_load))
    } else {
        Err(recovery_replay_error())
    }
}

fn recovery_add_pair(matrix: &mut [f64; 144], first: usize, second: usize, value: f64) {
    matrix[first * 12 + first] += value;
    matrix[first * 12 + second] -= value;
    matrix[second * 12 + first] -= value;
    matrix[second * 12 + second] += value;
}

fn recovery_scatter_bending(matrix: &mut [f64; 144], indices: [usize; 4], values: [f64; 16]) {
    for row in 0..4 {
        for column in 0..4 {
            matrix[indices[row] * 12 + indices[column]] += values[row * 4 + column];
        }
    }
}

fn vector_dot(left: [f64; 3], right: [f64; 3]) -> f64 {
    left[0] * right[0] + left[1] * right[1] + left[2] * right[2]
}

fn vector_norm(value: [f64; 3]) -> f64 {
    vector_dot(value, value).sqrt()
}

fn normalize_vector(value: [f64; 3]) -> Option<[f64; 3]> {
    let magnitude = vector_norm(value);
    if !magnitude.is_finite() || magnitude <= 1.0e-12 {
        return None;
    }
    Some([
        value[0] / magnitude,
        value[1] / magnitude,
        value[2] / magnitude,
    ])
}

fn recovery_replay_error() -> RuntimeError {
    RuntimeError {
        code: INTERNAL,
        message: "independent Rust member-force recovery replay failed".to_owned(),
    }
}

#[cfg(test)]
mod recovery_replay_tests {
    use structural_ffi::{
        LinearFrame3dMember, LinearFrame3dNode, LinearFrame3dResult, LinearFrame3dSection,
    };

    use super::{member_force_replay_metric, PreparedFrame3d, RESULT_GATE_TOLERANCE};

    fn axial_case() -> (PreparedFrame3d, LinearFrame3dResult) {
        let prepared = PreparedFrame3d {
            nodes: vec![
                LinearFrame3dNode::new(0.0, 0.0, 0.0),
                LinearFrame3dNode::new(1.0, 0.0, 0.0),
            ],
            sections: vec![LinearFrame3dSection::new(
                0.01, 2.0e8, 8.0e7, 1.0e-5, 2.0e-5, 3.0e-5, 0.008, 0.007,
            )],
            members: vec![LinearFrame3dMember::new(0, 1, 0)],
            restrained_dofs: (0..6).collect(),
            nodal_loads_kn_knm: vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            loads_kn_knm: vec![0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            uniform_member_loads: Vec::new(),
            node_ids: vec!["N1".to_owned(), "N2".to_owned()],
            member_ids: vec!["E1".to_owned()],
        };
        let result = LinearFrame3dResult {
            displacements: vec![
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0e-5, 0.0, 0.0, 0.0, 0.0, 0.0,
            ],
            reactions: vec![
                -100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            ],
            member_end_forces: vec![
                -100.0, 0.0, 0.0, 0.0, 0.0, 0.0, 100.0, 0.0, 0.0, 0.0, 0.0, 0.0,
            ],
        };
        (prepared, result)
    }

    #[test]
    fn independent_recovery_replay_rejects_native_member_force_drift() {
        let (prepared, result) = axial_case();
        assert!(
            member_force_replay_metric(&prepared, &result).expect("exact independent replay")
                <= RESULT_GATE_TOLERANCE
        );

        let mut drifted = result;
        drifted.member_end_forces[6] = 101.0;
        assert!(
            member_force_replay_metric(&prepared, &drifted).expect("finite drift metric")
                > RESULT_GATE_TOLERANCE
        );
    }
}

fn free_residual_metric(
    prepared: &PreparedFrame3d,
    result: &structural_ffi::LinearFrame3dResult,
) -> f64 {
    let restrained = prepared
        .restrained_dofs
        .iter()
        .copied()
        .collect::<BTreeSet<_>>();
    let load_scale = prepared
        .loads_kn_knm
        .iter()
        .map(|value| value.abs())
        .fold(1.0_f64, f64::max);
    result
        .reactions
        .iter()
        .enumerate()
        .filter(|(index, _)| {
            u32::try_from(*index)
                .ok()
                .is_some_and(|dof| !restrained.contains(&dof))
        })
        .map(|(_, value)| value.abs())
        .fold(0.0_f64, f64::max)
        / load_scale
}

fn accumulate_resultant(
    resultant: &mut [f64; 6],
    coordinates: [f64; 3],
    force: [f64; 3],
    moment: [f64; 3],
) {
    let arm_moment = cross(coordinates, force);
    for index in 0..3 {
        resultant[index] += force[index];
        resultant[index + 3] += moment[index] + arm_moment[index];
    }
}

fn cross(left: [f64; 3], right: [f64; 3]) -> [f64; 3] {
    [
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    ]
}

#[derive(Clone, Copy)]
struct Material {
    elastic_modulus_pa: f64,
    shear_modulus_pa: f64,
}

fn prepare_materials(
    root: &Map<String, Value>,
) -> Result<BTreeMap<String, Material>, RuntimeError> {
    let rows = array_field(root, "materials", "/")?;
    let mut output = BTreeMap::new();
    for (position, value) in rows.iter().enumerate() {
        let path = format!("/materials/{position}");
        let row = object(value, &path)?;
        require_dense_index(row, position, &path)?;
        require_exact_string(row, "law_id", "linear_elastic_isotropic", &path)?;
        require_empty_extensions(row, &format!("{path}/extensions"))?;
        let state = object_field(row, "state_schema", &path)?;
        if bool_field(state, "stateful", &format!("{path}/state_schema"))? {
            return Err(unsupported(
                &format!("{path}/state_schema/stateful"),
                "native linear Frame3D does not accept stateful material",
            ));
        }
        let parameters = object_field(row, "parameters", &path)?;
        let elastic_modulus_pa = f64_field(
            parameters,
            "elastic_modulus_pa",
            &format!("{path}/parameters"),
        )?;
        let poisson_ratio = f64_field(parameters, "poisson_ratio", &format!("{path}/parameters"))?;
        let shear_modulus_pa = elastic_modulus_pa / (2.0 * (1.0 + poisson_ratio));
        if !(elastic_modulus_pa.is_finite()
            && elastic_modulus_pa > 0.0
            && shear_modulus_pa.is_finite()
            && shear_modulus_pa > 0.0)
        {
            return Err(invalid(
                &format!("{path}/parameters"),
                "material does not produce finite positive elastic moduli",
            ));
        }
        let id = string_field(row, "id", &path)?.to_owned();
        if output
            .insert(
                id,
                Material {
                    elastic_modulus_pa,
                    shear_modulus_pa,
                },
            )
            .is_some()
        {
            return Err(invalid(&format!("{path}/id"), "duplicate material id"));
        }
    }
    Ok(output)
}

#[derive(Clone, Copy)]
struct Section {
    area_m2: f64,
    iy_m4: f64,
    iz_m4: f64,
    j_m4: f64,
    shear_area_y_m2: f64,
    shear_area_z_m2: f64,
}

fn prepare_sections(root: &Map<String, Value>) -> Result<BTreeMap<String, Section>, RuntimeError> {
    let rows = array_field(root, "sections", "/")?;
    let mut output = BTreeMap::new();
    for (position, value) in rows.iter().enumerate() {
        let path = format!("/sections/{position}");
        let row = object(value, &path)?;
        require_dense_index(row, position, &path)?;
        require_exact_string(row, "family_id", "frame_3d", &path)?;
        require_empty_extensions(row, &format!("{path}/extensions"))?;
        let parameters = object_field(row, "parameters", &path)?;
        let section = Section {
            area_m2: positive_field(parameters, "area_m2", &format!("{path}/parameters"))?,
            iy_m4: positive_field(parameters, "iy_m4", &format!("{path}/parameters"))?,
            iz_m4: positive_field(parameters, "iz_m4", &format!("{path}/parameters"))?,
            j_m4: positive_field(
                parameters,
                "torsional_constant_m4",
                &format!("{path}/parameters"),
            )?,
            shear_area_y_m2: positive_field(
                parameters,
                "shear_area_y_m2",
                &format!("{path}/parameters"),
            )?,
            shear_area_z_m2: positive_field(
                parameters,
                "shear_area_z_m2",
                &format!("{path}/parameters"),
            )?,
        };
        let id = string_field(row, "id", &path)?.to_owned();
        if output.insert(id, section).is_some() {
            return Err(invalid(&format!("{path}/id"), "duplicate section id"));
        }
    }
    Ok(output)
}

fn prepare_constraints(
    root: &Map<String, Value>,
    node_lookup: &BTreeMap<String, u32>,
) -> Result<Vec<u32>, RuntimeError> {
    let rows = array_field(root, "constraints", "/")?;
    let mut restrained = Vec::new();
    for (position, value) in rows.iter().enumerate() {
        let path = format!("/constraints/{position}");
        let row = object(value, &path)?;
        require_dense_index(row, position, &path)?;
        require_exact_string(row, "type", "fixed_dofs", &path)?;
        require_empty_extensions(row, &format!("{path}/extensions"))?;
        let node_id = string_field(row, "node_id", &path)?;
        let node_index = *node_lookup
            .get(node_id)
            .ok_or_else(|| invalid(&format!("{path}/node_id"), "constraint node id is unknown"))?;
        let dofs = array_field(row, "dofs", &path)?;
        let prescribed = object_field(row, "prescribed_values_si", &path)?;
        if prescribed.len() != dofs.len() {
            return Err(unsupported(
                &format!("{path}/prescribed_values_si"),
                "native linear Frame3D requires one explicit zero value per restrained DOF",
            ));
        }
        for (dof_position, value) in dofs.iter().enumerate() {
            let dof_path = format!("{path}/dofs/{dof_position}");
            let name = string(value, &dof_path)?;
            let component = DOF_NAMES
                .iter()
                .position(|candidate| *candidate == name)
                .ok_or_else(|| invalid(&dof_path, "constraint DOF is unknown"))?;
            let prescribed_value = prescribed
                .get(name)
                .ok_or_else(|| invalid(&dof_path, "constraint prescribed value is missing"))?;
            if !is_zero_number(finite_number(
                prescribed_value,
                &format!("{path}/prescribed_values_si/{name}"),
            )?) {
                return Err(unsupported(
                    &format!("{path}/prescribed_values_si/{name}"),
                    "nonzero prescribed displacement is outside Frame Alpha",
                ));
            }
            let component = u32::try_from(component)
                .map_err(|_| invalid(&dof_path, "constraint DOF index exceeds native range"))?;
            restrained.push(node_index * 6 + component);
        }
    }
    restrained.sort_unstable();
    let original_len = restrained.len();
    restrained.dedup();
    if restrained.len() != original_len {
        return Err(invalid(
            "/constraints",
            "restrained DOF is declared more than once",
        ));
    }
    Ok(restrained)
}

fn prepare_loads(
    root: &Map<String, Value>,
    load_pattern_id: &str,
    node_lookup: &BTreeMap<String, u32>,
    member_lookup: &BTreeMap<String, usize>,
    nodes: &[LinearFrame3dNode],
    sections: &[LinearFrame3dSection],
    members: &[LinearFrame3dMember],
) -> Result<PreparedLoads, RuntimeError> {
    if load_pattern_id.trim().is_empty() {
        return Err(invalid(
            "/load_patterns",
            "load pattern id must not be empty",
        ));
    }
    let patterns = array_field(root, "load_patterns", "/")?;
    let mut matches = patterns.iter().enumerate().filter_map(|(index, value)| {
        value
            .as_object()
            .and_then(|row| row.get("id"))
            .and_then(Value::as_str)
            .filter(|id| *id == load_pattern_id)
            .map(|_| (index, value))
    });
    let (pattern_index, pattern_value) = matches
        .next()
        .ok_or_else(|| invalid("/load_patterns", "requested load pattern id does not exist"))?;
    if matches.next().is_some() {
        return Err(invalid(
            "/load_patterns",
            "requested load pattern id is not unique",
        ));
    }
    let path = format!("/load_patterns/{pattern_index}");
    let pattern = object(pattern_value, &path)?;
    require_exact_string(pattern, "analysis_type", "linear_static", &path)?;
    require_empty_extensions(pattern, &format!("{path}/extensions"))?;
    if !is_zero_vector(fixed_f64::<3>(
        field(pattern, "self_weight", &path)?,
        &format!("{path}/self_weight"),
    )?) {
        return Err(unsupported(
            &format!("{path}/self_weight"),
            "self weight is outside Frame Alpha",
        ));
    }
    let nodal_loads = prepare_nodal_loads(pattern, &path, node_lookup, nodes.len())?;
    let mut assembled_loads = nodal_loads.clone();
    let uniform_member_loads = prepare_uniform_member_loads(
        pattern,
        &path,
        member_lookup,
        nodes,
        sections,
        members,
        &mut assembled_loads,
    )?;
    Ok(PreparedLoads {
        nodal_kn_knm: nodal_loads,
        assembled_kn_knm: assembled_loads,
        uniform_member_loads,
    })
}

fn prepare_nodal_loads(
    pattern: &Map<String, Value>,
    path: &str,
    node_lookup: &BTreeMap<String, u32>,
    node_count: usize,
) -> Result<Vec<f64>, RuntimeError> {
    let mut nodal_loads = vec![0.0; node_count * 6];
    for (position, value) in array_field(pattern, "nodal_loads", path)?
        .iter()
        .enumerate()
    {
        let load_path = format!("{path}/nodal_loads/{position}");
        let row = object(value, &load_path)?;
        require_dense_index(row, position, &load_path)?;
        require_empty_extensions(row, &format!("{load_path}/extensions"))?;
        let node_id = string_field(row, "node_id", &load_path)?;
        let node_index = *node_lookup.get(node_id).ok_or_else(|| {
            invalid(
                &format!("{load_path}/node_id"),
                "nodal load node id is unknown",
            )
        })? as usize;
        let components = object_field(row, "components_si", &load_path)?;
        for (component, name) in LOAD_NAMES.iter().enumerate() {
            nodal_loads[node_index * 6 + component] +=
                f64_field(components, name, &format!("{load_path}/components_si"))? * FORCE_TO_KILO;
        }
    }
    if !nodal_loads.iter().all(|value| value.is_finite()) {
        return Err(invalid(
            &format!("{path}/nodal_loads"),
            "accumulated nodal load is non-finite",
        ));
    }
    Ok(nodal_loads)
}

fn prepare_uniform_member_loads(
    pattern: &Map<String, Value>,
    path: &str,
    member_lookup: &BTreeMap<String, usize>,
    nodes: &[LinearFrame3dNode],
    sections: &[LinearFrame3dSection],
    members: &[LinearFrame3dMember],
    assembled_loads: &mut [f64],
) -> Result<Vec<LinearFrame3dUniformMemberLoad>, RuntimeError> {
    let mut uniform_member_loads = Vec::new();
    let member_load_rows: &[Value] = match pattern.get("uniform_member_loads") {
        None => &[],
        Some(value) => value.as_array().ok_or_else(|| {
            invalid(
                &format!("{path}/uniform_member_loads"),
                "uniform member loads must be an array",
            )
        })?,
    };
    for (position, value) in member_load_rows.iter().enumerate() {
        let load_path = format!("{path}/uniform_member_loads/{position}");
        let row = object(value, &load_path)?;
        require_dense_index(row, position, &load_path)?;
        require_empty_extensions(row, &format!("{load_path}/extensions"))?;
        require_exact_string(row, "basis", "initial_member_local", &load_path)?;
        require_exact_string(row, "behavior", "dead", &load_path)?;
        let member_id = string_field(row, "member_id", &load_path)?;
        let member_index = *member_lookup.get(member_id).ok_or_else(|| {
            invalid(
                &format!("{load_path}/member_id"),
                "uniform member-load member id is unknown",
            )
        })?;
        let components = object_field(row, "components_si", &load_path)?;
        let components_kn_per_m = [
            f64_field(components, "QX", &format!("{load_path}/components_si"))? * FORCE_TO_KILO,
            f64_field(components, "QY", &format!("{load_path}/components_si"))? * FORCE_TO_KILO,
            f64_field(components, "QZ", &format!("{load_path}/components_si"))? * FORCE_TO_KILO,
        ];
        if components_kn_per_m.iter().all(|value| *value == 0.0) {
            return Err(invalid(
                &format!("{load_path}/components_si"),
                "uniform member-load row must be nonzero",
            ));
        }
        let native_index = u32::try_from(member_index)
            .map_err(|_| invalid(&load_path, "member-load index exceeds native range"))?;
        uniform_member_loads.push(LinearFrame3dUniformMemberLoad::new(
            native_index,
            components_kn_per_m,
        ));

        let member = members
            .get(member_index)
            .ok_or_else(|| invalid(&load_path, "member-load index is inconsistent"))?;
        let node_i = usize::try_from(member.node_i)
            .map_err(|_| invalid(&load_path, "member start-node index is invalid"))?;
        let node_j = usize::try_from(member.node_j)
            .map_err(|_| invalid(&load_path, "member end-node index is invalid"))?;
        let start = nodes
            .get(node_i)
            .ok_or_else(|| invalid(&load_path, "member start node is missing"))?;
        let end = nodes
            .get(node_j)
            .ok_or_else(|| invalid(&load_path, "member end node is missing"))?;
        let delta = [
            end.x_m - start.x_m,
            end.y_m - start.y_m,
            end.z_m - start.z_m,
        ];
        let rotation = recovery_rotation(delta, member.local_axis_roll_deg)?;
        let local_equivalent =
            uniform_member_equivalent_local_load(vector_norm(delta), components_kn_per_m)?;
        let section_index = usize::try_from(member.section_index)
            .map_err(|_| invalid(&load_path, "member section index is invalid"))?;
        let section = sections
            .get(section_index)
            .ok_or_else(|| invalid(&load_path, "member section is missing"))?;
        let stiffness = recovery_local_stiffness(section, vector_norm(delta))?;
        let (_, local_equivalent) = recovery_condense_releases(
            &stiffness,
            local_equivalent,
            member.released_dof_mask_i,
            member.released_dof_mask_j,
        )?;
        for (local_offset, global_node, dof_offset) in [
            (0_usize, node_i, 0_usize),
            (3, node_i, 3),
            (6, node_j, 0),
            (9, node_j, 3),
        ] {
            for global_component in 0..3 {
                let mut value = 0.0;
                for local_component in 0..3 {
                    value += rotation[local_component * 3 + global_component]
                        * local_equivalent[local_offset + local_component];
                }
                assembled_loads[global_node * 6 + dof_offset + global_component] += value;
            }
        }
    }
    if !assembled_loads.iter().all(|value| value.is_finite()) {
        return Err(invalid(
            &format!("{path}/uniform_member_loads"),
            "assembled member equivalent load is non-finite",
        ));
    }
    Ok(uniform_member_loads)
}

fn require_canonical_context(root: &Map<String, Value>) -> Result<(), RuntimeError> {
    let units = object_field(root, "units", "/")?;
    for (name, expected) in [
        ("length", "m"),
        ("force", "N"),
        ("mass", "kg"),
        ("time", "s"),
        ("rotation", "rad"),
    ] {
        require_exact_string(units, name, expected, "/units")?;
    }
    let coordinates = object_field(root, "coordinate_system", "/")?;
    require_exact_string(coordinates, "frame_id", "global", "/coordinate_system")?;
    require_exact_string(coordinates, "up_axis", "Z", "/coordinate_system")?;
    require_exact_string(coordinates, "handedness", "right", "/coordinate_system")?;
    let axis_order = array_field(coordinates, "axis_order", "/coordinate_system")?;
    if axis_order.iter().map(Value::as_str).collect::<Vec<_>>()
        != vec![Some("X"), Some("Y"), Some("Z")]
    {
        return Err(unsupported(
            "/coordinate_system/axis_order",
            "native linear Frame3D requires global X/Y/Z axis order",
        ));
    }
    if !is_zero_vector(fixed_f64::<3>(
        field(coordinates, "origin_m", "/coordinate_system")?,
        "/coordinate_system/origin_m",
    )?) {
        return Err(unsupported(
            "/coordinate_system/origin_m",
            "nonzero coordinate origin is outside Frame Alpha",
        ));
    }
    let dofs = array_field(root, "dof_components", "/")?;
    if dofs.iter().map(Value::as_str).collect::<Vec<_>>()
        != DOF_NAMES
            .iter()
            .map(|value| Some(*value))
            .collect::<Vec<_>>()
    {
        return Err(unsupported(
            "/dof_components",
            "native linear Frame3D requires canonical six-DOF order",
        ));
    }
    Ok(())
}

fn require_zero_offsets(row: &Map<String, Value>, path: &str) -> Result<(), RuntimeError> {
    let offsets = object_field(row, "offsets", path)?;
    for end in ["i_global_m", "j_global_m"] {
        if !is_zero_vector(fixed_f64::<3>(
            field(offsets, end, &format!("{path}/offsets"))?,
            &format!("{path}/offsets/{end}"),
        )?) {
            return Err(unsupported(
                &format!("{path}/offsets/{end}"),
                "rigid end offsets are outside Frame Alpha",
            ));
        }
    }
    Ok(())
}

fn prepare_rotational_releases(
    row: &Map<String, Value>,
    path: &str,
) -> Result<[u32; 2], RuntimeError> {
    let releases = object_field(row, "releases", path)?;
    let mut masks = [0_u32; 2];
    for (end_index, end) in ["i", "j"].iter().enumerate() {
        for (release_index, value) in array_field(releases, end, &format!("{path}/releases"))?
            .iter()
            .enumerate()
        {
            let name = string(value, &format!("{path}/releases/{end}/{release_index}"))?;
            let component = DOF_NAMES
                .iter()
                .position(|candidate| *candidate == name)
                .ok_or_else(|| {
                    invalid(
                        &format!("{path}/releases/{end}/{release_index}"),
                        "unknown release DOF",
                    )
                })?;
            if component < 3 {
                return Err(unsupported(
                    &format!("{path}/releases/{end}/{release_index}"),
                    "translational member releases are outside Frame Alpha",
                ));
            }
            masks[end_index] |= 1_u32 << component;
        }
    }
    Ok(masks)
}

fn require_dense_index(
    row: &Map<String, Value>,
    expected: usize,
    path: &str,
) -> Result<(), RuntimeError> {
    let actual = field(row, "index", path)?
        .as_u64()
        .ok_or_else(|| invalid(&format!("{path}/index"), "index is not an unsigned integer"))?;
    if actual != u64::try_from(expected).unwrap_or(u64::MAX) {
        return Err(unsupported(
            &format!("{path}/index"),
            "native Frame Alpha requires dense ordered entity indices",
        ));
    }
    Ok(())
}

fn require_empty_array(row: &Map<String, Value>, name: &str) -> Result<(), RuntimeError> {
    if !array_field(row, name, "/")?.is_empty() {
        return Err(unsupported(
            &format!("/{name}"),
            "feature family is outside native Frame Alpha",
        ));
    }
    Ok(())
}

fn require_empty_extensions(row: &Map<String, Value>, path: &str) -> Result<(), RuntimeError> {
    let extensions = row
        .get("extensions")
        .ok_or_else(|| invalid(path, "extensions field is missing"))?;
    if !object(extensions, path)?.is_empty() {
        return Err(unsupported(
            path,
            "nonempty extensions are outside native Frame Alpha",
        ));
    }
    Ok(())
}

fn require_exact_string(
    row: &Map<String, Value>,
    name: &str,
    expected: &str,
    path: &str,
) -> Result<(), RuntimeError> {
    if string_field(row, name, path)? != expected {
        return Err(unsupported(
            &format!("{path}/{name}"),
            "value is outside native Frame Alpha",
        ));
    }
    Ok(())
}

fn positive_field(row: &Map<String, Value>, name: &str, path: &str) -> Result<f64, RuntimeError> {
    let value = f64_field(row, name, path)?;
    if value > 0.0 {
        Ok(value)
    } else {
        Err(invalid(&format!("{path}/{name}"), "value must be positive"))
    }
}

fn fixed_f64<const N: usize>(value: &Value, path: &str) -> Result<[f64; N], RuntimeError> {
    let values = value
        .as_array()
        .ok_or_else(|| invalid(path, "value is not an array"))?;
    if values.len() != N {
        return Err(invalid(path, "array has the wrong fixed length"));
    }
    let mut output = [0.0; N];
    for (index, value) in values.iter().enumerate() {
        output[index] = finite_number(value, &format!("{path}/{index}"))?;
    }
    Ok(output)
}

fn is_zero_vector<const N: usize>(values: [f64; N]) -> bool {
    values.iter().copied().all(is_zero_number)
}

fn is_zero_number(value: f64) -> bool {
    let bits = value.to_bits();
    bits == 0.0_f64.to_bits() || bits == (-0.0_f64).to_bits()
}

fn object<'a>(value: &'a Value, path: &str) -> Result<&'a Map<String, Value>, RuntimeError> {
    value
        .as_object()
        .ok_or_else(|| invalid(path, "value is not an object"))
}

fn object_field<'a>(
    row: &'a Map<String, Value>,
    name: &str,
    path: &str,
) -> Result<&'a Map<String, Value>, RuntimeError> {
    object(field(row, name, path)?, &format!("{path}/{name}"))
}

fn array_field<'a>(
    row: &'a Map<String, Value>,
    name: &str,
    path: &str,
) -> Result<&'a [Value], RuntimeError> {
    row.get(name)
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .ok_or_else(|| invalid(&format!("{path}/{name}"), "value is not an array"))
}

fn field<'a>(
    row: &'a Map<String, Value>,
    name: &str,
    path: &str,
) -> Result<&'a Value, RuntimeError> {
    row.get(name)
        .ok_or_else(|| invalid(&format!("{path}/{name}"), "required field is missing"))
}

fn string_field<'a>(
    row: &'a Map<String, Value>,
    name: &str,
    path: &str,
) -> Result<&'a str, RuntimeError> {
    string(field(row, name, path)?, &format!("{path}/{name}"))
}

fn string<'a>(value: &'a Value, path: &str) -> Result<&'a str, RuntimeError> {
    value
        .as_str()
        .ok_or_else(|| invalid(path, "value is not a string"))
}

fn bool_field(row: &Map<String, Value>, name: &str, path: &str) -> Result<bool, RuntimeError> {
    field(row, name, path)?
        .as_bool()
        .ok_or_else(|| invalid(&format!("{path}/{name}"), "value is not a boolean"))
}

fn f64_field(row: &Map<String, Value>, name: &str, path: &str) -> Result<f64, RuntimeError> {
    finite_number(field(row, name, path)?, &format!("{path}/{name}"))
}

fn finite_number(value: &Value, path: &str) -> Result<f64, RuntimeError> {
    let number = value
        .as_f64()
        .ok_or_else(|| invalid(path, "value is not a real number"))?;
    if number.is_finite() {
        Ok(number)
    } else {
        Err(invalid(path, "value is not finite"))
    }
}

fn invalid(path: &str, detail: &str) -> RuntimeError {
    RuntimeError {
        code: INVALID_ARGUMENT,
        message: format!("{detail} at {path}"),
    }
}

fn unsupported(path: &str, detail: &str) -> RuntimeError {
    RuntimeError {
        code: UNSUPPORTED,
        message: format!("{detail} at {path}"),
    }
}

pub(crate) fn semantic_invalid() -> RuntimeError {
    RuntimeError {
        code: SEMANTIC_INVALID,
        message: "ModelIR is not contract-valid for native analysis".to_owned(),
    }
}

pub(crate) fn analysis_not_ready() -> RuntimeError {
    RuntimeError {
        code: ANALYSIS_NOT_READY,
        message: "ModelIR declares blocking unsupported features".to_owned(),
    }
}
