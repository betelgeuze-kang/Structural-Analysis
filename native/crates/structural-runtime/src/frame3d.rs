use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value};
use structural_contracts::model_ir::ModelIrV2Document;
use structural_ffi::{LinearFrame3dMember, LinearFrame3dNode, LinearFrame3dSection};

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
    pub nodes: Vec<LinearFrame3dNodeResult>,
    pub members: Vec<LinearFrame3dMemberResult>,
    pub claim_boundary: &'static str,
}

pub(crate) struct PreparedFrame3d {
    pub nodes: Vec<LinearFrame3dNode>,
    pub sections: Vec<LinearFrame3dSection>,
    pub members: Vec<LinearFrame3dMember>,
    pub restrained_dofs: Vec<u32>,
    pub loads_kn_knm: Vec<f64>,
    pub node_ids: Vec<String>,
    pub member_ids: Vec<String>,
}

struct PreparedElements {
    sections: Vec<LinearFrame3dSection>,
    members: Vec<LinearFrame3dMember>,
    member_ids: Vec<String>,
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
    let loads_kn_knm = prepare_loads(root, load_pattern_id, &node_lookup, nodes.len())?;
    Ok(PreparedFrame3d {
        nodes,
        sections: prepared_elements.sections,
        members: prepared_elements.members,
        restrained_dofs,
        loads_kn_knm,
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
        require_no_releases(row, &path)?;
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
    Ok(LinearFrame3dAnalysisResult {
        schema_version: "structural-native-linear-frame3d-result.v1",
        model_id: document.model_id().to_owned(),
        model_content_hash: document.content_hash().to_owned(),
        model_semantic_hash: document.semantic_hash().to_owned(),
        model_provenance_hash: document.provenance_hash().to_owned(),
        load_pattern_id: load_pattern_id.to_owned(),
        native_abi_version: abi_version,
        nodes,
        members,
        claim_boundary: "bounded_cpu_linear_timoshenko_frame3d_not_resultir_or_release_authority",
    })
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
    node_count: usize,
) -> Result<Vec<f64>, RuntimeError> {
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
    let mut loads = vec![0.0; node_count * 6];
    for (position, value) in array_field(pattern, "nodal_loads", &path)?
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
            loads[node_index * 6 + component] +=
                f64_field(components, name, &format!("{load_path}/components_si"))? * FORCE_TO_KILO;
        }
    }
    if !loads.iter().all(|value| value.is_finite()) {
        return Err(invalid(
            &format!("{path}/nodal_loads"),
            "accumulated nodal load is non-finite",
        ));
    }
    Ok(loads)
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

fn require_no_releases(row: &Map<String, Value>, path: &str) -> Result<(), RuntimeError> {
    let releases = object_field(row, "releases", path)?;
    for end in ["i", "j"] {
        if !array_field(releases, end, &format!("{path}/releases"))?.is_empty() {
            return Err(unsupported(
                &format!("{path}/releases/{end}"),
                "member releases are outside Frame Alpha",
            ));
        }
    }
    Ok(())
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
