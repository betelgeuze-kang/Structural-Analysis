//! Rust-owned, call-scoped `ModelIR` descriptor arena.

use core::marker::PhantomData;
use core::mem::size_of;
use core::ptr;

use serde_json::{Map, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, ModelIrV2Document};
use structural_ffi_sys as sys;

use crate::Error;

pub(crate) struct DescriptorArena<'a> {
    root: sys::SaModelIrDescriptorV1,
    _owned_json: Vec<Box<str>>,
    _dof_arrays: Vec<Box<[sys::SaDofV1]>>,
    _prescribed_arrays: Vec<Box<[sys::SaPrescribedValueV1]>>,
    _nodal_load_arrays: Vec<Box<[sys::SaNodalLoadDescriptorV1]>>,
    _combination_term_arrays: Vec<Box<[sys::SaLoadCombinationTermV1]>>,
    _time_point_arrays: Vec<Box<[sys::SaTimePointV1]>>,
    _string_view_arrays: Vec<Box<[sys::SaStringViewV1]>>,
    _nodes: Box<[sys::SaNodeDescriptorV1]>,
    _materials: Box<[sys::SaMaterialDescriptorV1]>,
    _sections: Box<[sys::SaSectionDescriptorV1]>,
    _elements: Box<[sys::SaElementDescriptorV1]>,
    _constraints: Box<[sys::SaConstraintDescriptorV1]>,
    _load_patterns: Box<[sys::SaLoadPatternDescriptorV1]>,
    _load_combinations: Box<[sys::SaLoadCombinationDescriptorV1]>,
    _time_functions: Box<[sys::SaTimeFunctionDescriptorV1]>,
    _construction_stages: Box<[sys::SaConstructionStageDescriptorV1]>,
    _roundtrip_rows: Box<[sys::SaRoundtripRowDescriptorV1]>,
    _unsupported_features: Box<[sys::SaUnsupportedFeatureDescriptorV1]>,
    _document: PhantomData<&'a ModelIrV2Document>,
}

impl<'a> DescriptorArena<'a> {
    // The root constructor assigns every public C field in header order so ABI review remains
    // mechanical; splitting it would hide the one-to-one descriptor audit trail.
    #[allow(clippy::too_many_lines)]
    pub(crate) fn build(document: &'a ModelIrV2Document) -> Result<Self, Error> {
        let root_object = object(document.value(), "/")?;
        let mut builder = Builder::default();

        let nodes = builder.nodes(array_field(root_object, "nodes", "/")?)?;
        let materials = builder.materials(array_field(root_object, "materials", "/")?)?;
        let sections = builder.sections(array_field(root_object, "sections", "/")?)?;
        let elements = builder.elements(array_field(root_object, "elements", "/")?)?;
        let constraints = builder.constraints(array_field(root_object, "constraints", "/")?)?;
        let load_patterns =
            builder.load_patterns(array_field(root_object, "load_patterns", "/")?)?;
        let load_combinations =
            builder.load_combinations(array_field(root_object, "load_combinations", "/")?)?;
        let time_functions =
            builder.time_functions(array_field(root_object, "time_functions", "/")?)?;
        let construction_stages =
            builder.construction_stages(array_field(root_object, "construction_stages", "/")?)?;
        let roundtrip_rows =
            builder.roundtrip_rows(array_field(root_object, "roundtrip_map", "/")?)?;
        let unsupported_features =
            builder.unsupported_features(array_field(root_object, "unsupported_features", "/")?)?;

        let canonical_units = source_units(object_field(root_object, "units", "/")?)?;
        let coordinate = object_field(root_object, "coordinate_system", "/")?;
        let coordinate_system = sys::SaCoordinateSystemDescriptorV1 {
            abi_version: sys::SA_ABI_V1_1,
            struct_size: abi_size::<sys::SaCoordinateSystemDescriptorV1>(),
            is_global: bool_flag(
                string_field(coordinate, "frame_id", "/coordinate_system")? == "global",
            ),
            axis_order_xyz: bool_flag(
                string_array(coordinate, "axis_order", "/coordinate_system")? == ["X", "Y", "Z"],
            ),
            up_axis_z: bool_flag(string_field(coordinate, "up_axis", "/coordinate_system")? == "Z"),
            right_handed: bool_flag(
                string_field(coordinate, "handedness", "/coordinate_system")? == "right",
            ),
            origin_m: fixed_f64_array::<3>(
                required(coordinate, "origin_m", "/coordinate_system")?,
                "/coordinate_system/origin_m",
            )?,
        };

        let (dof_components, dof_component_count) = builder.store_dofs(
            required(root_object, "dof_components", "/")?,
            "/dof_components",
        )?;
        let provenance = builder.provenance(object_field(root_object, "provenance", "/")?)?;
        let extensions_json =
            builder.extension(required(root_object, "extensions", "/")?, "/extensions")?;

        let (nodes_ptr, node_count) = slice_parts(&nodes);
        let (materials_ptr, material_count) = slice_parts(&materials);
        let (sections_ptr, section_count) = slice_parts(&sections);
        let (elements_ptr, element_count) = slice_parts(&elements);
        let (constraints_ptr, constraint_count) = slice_parts(&constraints);
        let (load_patterns_ptr, load_pattern_count) = slice_parts(&load_patterns);
        let (load_combinations_ptr, load_combination_count) = slice_parts(&load_combinations);
        let (time_functions_ptr, time_function_count) = slice_parts(&time_functions);
        let (construction_stages_ptr, construction_stage_count) = slice_parts(&construction_stages);
        let (roundtrip_rows_ptr, roundtrip_row_count) = slice_parts(&roundtrip_rows);
        let (unsupported_features_ptr, unsupported_feature_count) =
            slice_parts(&unsupported_features);

        let root = sys::SaModelIrDescriptorV1 {
            abi_version: sys::SA_ABI_V1_1,
            struct_size: abi_size::<sys::SaModelIrDescriptorV1>(),
            schema_version: view(string_field(root_object, "schema_version", "/")?),
            model_id: view(document.model_id()),
            capability_profile: capability_profile(document.capability_profile())?,
            reserved0: 0,
            canonical_units,
            coordinate_system,
            dof_components,
            dof_component_count,
            provenance,
            nodes: nodes_ptr,
            node_count,
            materials: materials_ptr,
            material_count,
            sections: sections_ptr,
            section_count,
            elements: elements_ptr,
            element_count,
            constraints: constraints_ptr,
            constraint_count,
            load_patterns: load_patterns_ptr,
            load_pattern_count,
            load_combinations: load_combinations_ptr,
            load_combination_count,
            time_functions: time_functions_ptr,
            time_function_count,
            construction_stages: construction_stages_ptr,
            construction_stage_count,
            roundtrip_rows: roundtrip_rows_ptr,
            roundtrip_row_count,
            unsupported_features: unsupported_features_ptr,
            unsupported_feature_count,
            extensions_json,
            canonical_json: view(document.canonical_json()),
            content_hash: view(document.content_hash()),
            semantic_hash: view(document.semantic_hash()),
            provenance_hash: view(document.provenance_hash()),
            flags: 0,
            reserved: [0; 3],
        };

        Ok(Self {
            root,
            _owned_json: builder.owned_json,
            _dof_arrays: builder.dof_arrays,
            _prescribed_arrays: builder.prescribed_arrays,
            _nodal_load_arrays: builder.nodal_load_arrays,
            _combination_term_arrays: builder.combination_term_arrays,
            _time_point_arrays: builder.time_point_arrays,
            _string_view_arrays: builder.string_view_arrays,
            _nodes: nodes,
            _materials: materials,
            _sections: sections,
            _elements: elements,
            _constraints: constraints,
            _load_patterns: load_patterns,
            _load_combinations: load_combinations,
            _time_functions: time_functions,
            _construction_stages: construction_stages,
            _roundtrip_rows: roundtrip_rows,
            _unsupported_features: unsupported_features,
            _document: PhantomData,
        })
    }

    pub(crate) const fn root(&self) -> &sys::SaModelIrDescriptorV1 {
        &self.root
    }
}

#[derive(Default)]
struct Builder {
    owned_json: Vec<Box<str>>,
    dof_arrays: Vec<Box<[sys::SaDofV1]>>,
    prescribed_arrays: Vec<Box<[sys::SaPrescribedValueV1]>>,
    nodal_load_arrays: Vec<Box<[sys::SaNodalLoadDescriptorV1]>>,
    combination_term_arrays: Vec<Box<[sys::SaLoadCombinationTermV1]>>,
    time_point_arrays: Vec<Box<[sys::SaTimePointV1]>>,
    string_view_arrays: Vec<Box<[sys::SaStringViewV1]>>,
}

impl Builder {
    fn extension(&mut self, value: &Value, path: &str) -> Result<sys::SaStringViewV1, Error> {
        let rendered = canonicalize_model_ir_v2(value)
            .map_err(|_| invariant(path, "extension canonicalization failed"))?
            .into_boxed_str();
        let result = view(&rendered);
        self.owned_json.push(rendered);
        Ok(result)
    }

    fn optional_extension(
        &mut self,
        row: &Map<String, Value>,
        path: &str,
    ) -> Result<sys::SaStringViewV1, Error> {
        match row.get("extensions") {
            Some(value) => self.extension(value, &format!("{path}/extensions")),
            None => Ok(view("{}")),
        }
    }

    fn identity(
        &mut self,
        row: &Map<String, Value>,
        path: &str,
    ) -> Result<sys::SaEntityIdentityV1, Error> {
        Ok(sys::SaEntityIdentityV1 {
            abi_version: sys::SA_ABI_V1_1,
            struct_size: abi_size::<sys::SaEntityIdentityV1>(),
            id: view(string_field(row, "id", path)?),
            index: u64_field(row, "index", path)?,
            source_id: optional_string(
                required(row, "source_id", path)?,
                &format!("{path}/source_id"),
            )?,
            extensions_json: self.extension(
                required(row, "extensions", path)?,
                &format!("{path}/extensions"),
            )?,
        })
    }

    fn provenance(
        &mut self,
        row: &Map<String, Value>,
    ) -> Result<sys::SaProvenanceDescriptorV1, Error> {
        let scales = object_field(row, "unit_scales_to_si", "/provenance")?;
        Ok(sys::SaProvenanceDescriptorV1 {
            abi_version: sys::SA_ABI_V1_1,
            struct_size: abi_size::<sys::SaProvenanceDescriptorV1>(),
            source_format: source_format(string_field(row, "source_format", "/provenance")?)?,
            reserved: 0,
            source_ref: view(string_field(row, "source_ref", "/provenance")?),
            source_sha256: view(string_field(row, "source_sha256", "/provenance")?),
            normalizer_id: view(string_field(row, "normalizer_id", "/provenance")?),
            normalizer_version: view(string_field(row, "normalizer_version", "/provenance")?),
            source_units: source_units(object_field(row, "source_units", "/provenance")?)?,
            unit_scales_to_si: sys::SaUnitScalesV1 {
                abi_version: sys::SA_ABI_V1_1,
                struct_size: abi_size::<sys::SaUnitScalesV1>(),
                length_to_m: f64_field(scales, "length_to_m", "/provenance/unit_scales_to_si")?,
                force_to_n: f64_field(scales, "force_to_n", "/provenance/unit_scales_to_si")?,
                mass_to_kg: f64_field(scales, "mass_to_kg", "/provenance/unit_scales_to_si")?,
                time_to_s: f64_field(scales, "time_to_s", "/provenance/unit_scales_to_si")?,
                rotation_to_rad: f64_field(
                    scales,
                    "rotation_to_rad",
                    "/provenance/unit_scales_to_si",
                )?,
            },
            extensions_json: self.optional_extension(row, "/provenance")?,
        })
    }

    fn nodes(&mut self, values: &[Value]) -> Result<Box<[sys::SaNodeDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/nodes/{index}");
                let row = object(value, &path)?;
                Ok(sys::SaNodeDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaNodeDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    coordinates_m: fixed_f64_array::<3>(
                        required(row, "coordinates_m", &path)?,
                        &format!("{path}/coordinates_m"),
                    )?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    // All three tagged-union arms live together to keep law/parameter coupling exhaustive.
    #[allow(clippy::too_many_lines)]
    fn materials(&mut self, values: &[Value]) -> Result<Box<[sys::SaMaterialDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/materials/{index}");
                let row = object(value, &path)?;
                let parameters = object_field(row, "parameters", &path)?;
                let law_name = string_field(row, "law_id", &path)?;
                let (law_id, parameters) = match law_name {
                    "linear_elastic_isotropic" => (
                        sys::SA_MATERIAL_LINEAR_ELASTIC_ISOTROPIC,
                        sys::SaMaterialParametersV1 {
                            linear: sys::SaLinearMaterialParametersV1 {
                                elastic_modulus_pa: f64_field(
                                    parameters,
                                    "elastic_modulus_pa",
                                    &format!("{path}/parameters"),
                                )?,
                                poisson_ratio: f64_field(
                                    parameters,
                                    "poisson_ratio",
                                    &format!("{path}/parameters"),
                                )?,
                                density_kg_m3: f64_field(
                                    parameters,
                                    "density_kg_m3",
                                    &format!("{path}/parameters"),
                                )?,
                            },
                        },
                    ),
                    "bilinear_combined_hardening_steel" => {
                        let shear = parameters.get("shear_modulus_pa").and_then(Value::as_f64);
                        (
                            sys::SA_MATERIAL_BILINEAR_COMBINED_HARDENING_STEEL,
                            sys::SaMaterialParametersV1 {
                                steel: sys::SaSteelMaterialParametersV1 {
                                    elastic_modulus_pa: f64_field(
                                        parameters,
                                        "elastic_modulus_pa",
                                        &format!("{path}/parameters"),
                                    )?,
                                    shear_modulus_pa: shear.unwrap_or(0.0),
                                    yield_stress_pa: f64_field(
                                        parameters,
                                        "yield_stress_pa",
                                        &format!("{path}/parameters"),
                                    )?,
                                    isotropic_hardening_modulus_pa: f64_field(
                                        parameters,
                                        "isotropic_hardening_modulus_pa",
                                        &format!("{path}/parameters"),
                                    )?,
                                    kinematic_hardening_modulus_pa: f64_field(
                                        parameters,
                                        "kinematic_hardening_modulus_pa",
                                        &format!("{path}/parameters"),
                                    )?,
                                    yield_tolerance_pa: f64_field(
                                        parameters,
                                        "yield_tolerance_pa",
                                        &format!("{path}/parameters"),
                                    )?,
                                    has_shear_modulus: bool_flag(shear.is_some()),
                                    reserved: 0,
                                },
                            },
                        )
                    }
                    "asymmetric_concrete_damage" => (
                        sys::SA_MATERIAL_ASYMMETRIC_CONCRETE_DAMAGE,
                        sys::SaMaterialParametersV1 {
                            concrete: sys::SaConcreteMaterialParametersV1 {
                                elastic_modulus_pa: f64_field(
                                    parameters,
                                    "elastic_modulus_pa",
                                    &format!("{path}/parameters"),
                                )?,
                                tensile_strength_pa: f64_field(
                                    parameters,
                                    "tensile_strength_pa",
                                    &format!("{path}/parameters"),
                                )?,
                                compressive_strength_pa: f64_field(
                                    parameters,
                                    "compressive_strength_pa",
                                    &format!("{path}/parameters"),
                                )?,
                                tensile_softening_rate: f64_field(
                                    parameters,
                                    "tensile_softening_rate",
                                    &format!("{path}/parameters"),
                                )?,
                                compressive_softening_rate: f64_field(
                                    parameters,
                                    "compressive_softening_rate",
                                    &format!("{path}/parameters"),
                                )?,
                                history_tolerance: f64_field(
                                    parameters,
                                    "history_tolerance",
                                    &format!("{path}/parameters"),
                                )?,
                            },
                        },
                    ),
                    _ => return Err(invariant(&format!("{path}/law_id"), "unknown material law")),
                };
                let state = object_field(row, "state_schema", &path)?;
                let stateful = bool_field(state, "stateful", &format!("{path}/state_schema"))?;
                let epoch = match string_field(
                    state,
                    "state_update_epoch",
                    &format!("{path}/state_schema"),
                )? {
                    "none" => sys::SA_MATERIAL_STATE_EPOCH_NONE,
                    "accepted_step" => sys::SA_MATERIAL_STATE_EPOCH_ACCEPTED_STEP,
                    _ => return Err(invariant(&path, "unknown material state epoch")),
                };
                Ok(sys::SaMaterialDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaMaterialDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    law_id,
                    parameter_set_version: parameter_version(row, &path)?,
                    parameters,
                    stateful: bool_flag(stateful),
                    state_update_epoch: epoch,
                    supports_trial_commit_rollback: bool_flag(bool_field(
                        state,
                        "supports_trial_commit_rollback",
                        &format!("{path}/state_schema"),
                    )?),
                    reserved: 0,
                    admissibility: Self::admissibility(row.get("admissibility"), &path)?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn admissibility(
        value: Option<&Value>,
        parent_path: &str,
    ) -> Result<sys::SaMaterialAdmissibilityV1, Error> {
        let Some(value) = value else {
            return Ok(sys::SaMaterialAdmissibilityV1 {
                abi_version: sys::SA_ABI_V1_1,
                struct_size: abi_size::<sys::SaMaterialAdmissibilityV1>(),
                is_present: 0,
                reserved: 0,
                loading_domain: empty_view(),
                supports_unloading: 0,
                supports_reversal: 0,
                supports_cyclic: 0,
                supports_tension: 0,
                supports_compression: 0,
                supports_multiaxial: 0,
            });
        };
        let path = format!("{parent_path}/admissibility");
        let row = object(value, &path)?;
        Ok(sys::SaMaterialAdmissibilityV1 {
            abi_version: sys::SA_ABI_V1_1,
            struct_size: abi_size::<sys::SaMaterialAdmissibilityV1>(),
            is_present: 1,
            reserved: 0,
            loading_domain: view(string_field(row, "loading_domain", &path)?),
            supports_unloading: bool_flag(bool_field(row, "supports_unloading", &path)?),
            supports_reversal: bool_flag(bool_field(row, "supports_reversal", &path)?),
            supports_cyclic: bool_flag(bool_field(row, "supports_cyclic", &path)?),
            supports_tension: bool_flag(bool_field(row, "supports_tension", &path)?),
            supports_compression: bool_flag(bool_field(row, "supports_compression", &path)?),
            supports_multiaxial: bool_flag(bool_field(row, "supports_multiaxial", &path)?),
        })
    }

    fn sections(&mut self, values: &[Value]) -> Result<Box<[sys::SaSectionDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/sections/{index}");
                let row = object(value, &path)?;
                let parameters = object_field(row, "parameters", &path)?;
                let (family_id, parameters) = match string_field(row, "family_id", &path)? {
                    "frame_3d" => (
                        sys::SA_SECTION_FRAME_3D,
                        sys::SaSectionParametersV1 {
                            frame: sys::SaFrameSectionParametersV1 {
                                area_m2: f64_field(parameters, "area_m2", &path)?,
                                iy_m4: f64_field(parameters, "iy_m4", &path)?,
                                iz_m4: f64_field(parameters, "iz_m4", &path)?,
                                torsional_constant_m4: f64_field(
                                    parameters,
                                    "torsional_constant_m4",
                                    &path,
                                )?,
                                shear_area_y_m2: f64_field(parameters, "shear_area_y_m2", &path)?,
                                shear_area_z_m2: f64_field(parameters, "shear_area_z_m2", &path)?,
                            },
                        },
                    ),
                    "truss_3d" => (
                        sys::SA_SECTION_TRUSS_3D,
                        sys::SaSectionParametersV1 {
                            truss: sys::SaTrussSectionParametersV1 {
                                area_m2: f64_field(parameters, "area_m2", &path)?,
                            },
                        },
                    ),
                    "rectangular_rc_fiber_2d" => (
                        sys::SA_SECTION_RECTANGULAR_RC_FIBER_2D,
                        sys::SaSectionParametersV1 {
                            rc_fiber: sys::SaRcFiberSectionParametersV1 {
                                width_m: f64_field(parameters, "width_m", &path)?,
                                depth_m: f64_field(parameters, "depth_m", &path)?,
                                cover_m: f64_field(parameters, "cover_m", &path)?,
                                concrete_layer_count: u64_field(
                                    parameters,
                                    "concrete_layer_count",
                                    &path,
                                )?,
                                top_bar_count: u64_field(parameters, "top_bar_count", &path)?,
                                bottom_bar_count: u64_field(parameters, "bottom_bar_count", &path)?,
                                bar_area_m2: f64_field(parameters, "bar_area_m2", &path)?,
                            },
                        },
                    ),
                    _ => {
                        return Err(invariant(
                            &format!("{path}/family_id"),
                            "unknown section family",
                        ))
                    }
                };
                Ok(sys::SaSectionDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaSectionDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    family_id,
                    parameter_set_version: parameter_version(row, &path)?,
                    parameters,
                    steel_material_id: optional_row_string(row, "steel_material_id", &path)?,
                    concrete_material_id: optional_row_string(row, "concrete_material_id", &path)?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn elements(&mut self, values: &[Value]) -> Result<Box<[sys::SaElementDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/elements/{index}");
                let row = object(value, &path)?;
                let node_ids = array_field(row, "node_ids", &path)?;
                if node_ids.len() != 2 {
                    return Err(invariant(
                        &format!("{path}/node_ids"),
                        "expected two node IDs",
                    ));
                }
                let offsets = object_field(row, "offsets", &path)?;
                let end_releases = if let Some(releases) = row.get("releases") {
                    let releases = object(releases, &format!("{path}/releases"))?;
                    let first = self.store_dofs(
                        required(releases, "i", &format!("{path}/releases"))?,
                        &format!("{path}/releases/i"),
                    )?;
                    let second = self.store_dofs(
                        required(releases, "j", &format!("{path}/releases"))?,
                        &format!("{path}/releases/j"),
                    )?;
                    [first, second]
                } else {
                    [(ptr::null(), 0), (ptr::null(), 0)]
                };
                let element_type = match string_field(row, "type", &path)? {
                    "frame_3d" => sys::SA_ELEMENT_FRAME_3D,
                    "truss_3d" => sys::SA_ELEMENT_TRUSS_3D,
                    "frame_2d" => sys::SA_ELEMENT_FRAME_2D,
                    _ => return Err(invariant(&format!("{path}/type"), "unknown element type")),
                };
                let formulation = match string_field(row, "formulation", &path)? {
                    "euler_bernoulli_3d" => sys::SA_FORMULATION_EULER_BERNOULLI_3D,
                    "linear_truss_3d" => sys::SA_FORMULATION_LINEAR_TRUSS_3D,
                    "stateful_corotational_timoshenko_frame3d" => {
                        sys::SA_FORMULATION_STATEFUL_COROTATIONAL_TIMOSHENKO_FRAME3D
                    }
                    "stateful_corotational_rc_fiber_frame2d" => {
                        sys::SA_FORMULATION_STATEFUL_COROTATIONAL_RC_FIBER_FRAME2D
                    }
                    _ => {
                        return Err(invariant(
                            &format!("{path}/formulation"),
                            "unknown formulation",
                        ))
                    }
                };
                let local_axis = row.get("local_axis_rotation_rad").and_then(Value::as_f64);
                let integration_order = row.get("integration_order").and_then(Value::as_u64);
                let uniform = row
                    .get("uniform_distributed_load_local")
                    .map(|value| object(value, &format!("{path}/uniform_distributed_load_local")))
                    .transpose()?;
                Ok(sys::SaElementDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaElementDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    element_type,
                    formulation,
                    node_ids: [
                        view(string_value(&node_ids[0], &format!("{path}/node_ids/0"))?),
                        view(string_value(&node_ids[1], &format!("{path}/node_ids/1"))?),
                    ],
                    material_id: optional_row_string(row, "material_id", &path)?,
                    section_id: view(string_field(row, "section_id", &path)?),
                    local_axis_rotation_rad: local_axis.unwrap_or(0.0),
                    has_local_axis_rotation: bool_flag(local_axis.is_some()),
                    reserved0: 0,
                    offset_i_global_m: fixed_f64_array::<3>(
                        required(offsets, "i_global_m", &format!("{path}/offsets"))?,
                        &format!("{path}/offsets/i_global_m"),
                    )?,
                    offset_j_global_m: fixed_f64_array::<3>(
                        required(offsets, "j_global_m", &format!("{path}/offsets"))?,
                        &format!("{path}/offsets/j_global_m"),
                    )?,
                    releases_i: end_releases[0].0,
                    releases_i_count: end_releases[0].1,
                    releases_j: end_releases[1].0,
                    releases_j_count: end_releases[1].1,
                    integration_order: integration_order.unwrap_or(0),
                    has_integration_order: bool_flag(integration_order.is_some()),
                    has_uniform_distributed_load_local: bool_flag(uniform.is_some()),
                    uniform_qx_n_per_m: uniform
                        .map_or(Ok(0.0), |item| f64_field(item, "qx_n_per_m", &path))?,
                    uniform_qy_n_per_m: uniform
                        .map_or(Ok(0.0), |item| f64_field(item, "qy_n_per_m", &path))?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn constraints(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaConstraintDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/constraints/{index}");
                let row = object(value, &path)?;
                let (dofs, dof_count) =
                    self.store_dofs(required(row, "dofs", &path)?, &format!("{path}/dofs"))?;
                let prescribed = object_field(row, "prescribed_values_si", &path)?;
                let mut values = Vec::with_capacity(prescribed.len());
                for name in ["UX", "UY", "UZ", "RX", "RY", "RZ"] {
                    if let Some(value) = prescribed.get(name) {
                        values.push(sys::SaPrescribedValueV1 {
                            dof: dof(name)?,
                            reserved: 0,
                            value_si: f64_value(
                                value,
                                &format!("{path}/prescribed_values_si/{name}"),
                            )?,
                        });
                    }
                }
                let values = values.into_boxed_slice();
                let (prescribed_values, prescribed_value_count) = slice_parts(&values);
                if !values.is_empty() {
                    self.prescribed_arrays.push(values);
                }
                Ok(sys::SaConstraintDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaConstraintDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    node_id: view(string_field(row, "node_id", &path)?),
                    dofs,
                    dof_count,
                    prescribed_values,
                    prescribed_value_count,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn load_patterns(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaLoadPatternDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/load_patterns/{index}");
                let row = object(value, &path)?;
                let mut loads = Vec::new();
                for (load_index, load) in array_field(row, "nodal_loads", &path)?.iter().enumerate()
                {
                    let load_path = format!("{path}/nodal_loads/{load_index}");
                    let load = object(load, &load_path)?;
                    let components = object_field(load, "components_si", &load_path)?;
                    loads.push(sys::SaNodalLoadDescriptorV1 {
                        abi_version: sys::SA_ABI_V1_1,
                        struct_size: abi_size::<sys::SaNodalLoadDescriptorV1>(),
                        identity: self.identity(load, &load_path)?,
                        node_id: view(string_field(load, "node_id", &load_path)?),
                        components_si: [
                            f64_field(components, "FX", &load_path)?,
                            f64_field(components, "FY", &load_path)?,
                            f64_field(components, "FZ", &load_path)?,
                            f64_field(components, "MX", &load_path)?,
                            f64_field(components, "MY", &load_path)?,
                            f64_field(components, "MZ", &load_path)?,
                        ],
                    });
                }
                let loads = loads.into_boxed_slice();
                let (nodal_loads, nodal_load_count) = slice_parts(&loads);
                if !loads.is_empty() {
                    self.nodal_load_arrays.push(loads);
                }
                Ok(sys::SaLoadPatternDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaLoadPatternDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    analysis_type: analysis_type(string_field(row, "analysis_type", &path)?)?,
                    reserved: 0,
                    self_weight: fixed_f64_array::<3>(
                        required(row, "self_weight", &path)?,
                        &format!("{path}/self_weight"),
                    )?,
                    nodal_loads,
                    nodal_load_count,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn load_combinations(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaLoadCombinationDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/load_combinations/{index}");
                let row = object(value, &path)?;
                let terms = array_field(row, "terms", &path)?
                    .iter()
                    .enumerate()
                    .map(|(term_index, term)| {
                        let term_path = format!("{path}/terms/{term_index}");
                        let term = object(term, &term_path)?;
                        Ok(sys::SaLoadCombinationTermV1 {
                            abi_version: sys::SA_ABI_V1_1,
                            struct_size: abi_size::<sys::SaLoadCombinationTermV1>(),
                            ref_id: view(string_field(term, "ref_id", &term_path)?),
                            ref_kind: match string_field(term, "ref_kind", &term_path)? {
                                "load_pattern" => sys::SA_LOAD_REF_PATTERN,
                                "load_combination" => sys::SA_LOAD_REF_COMBINATION,
                                _ => {
                                    return Err(invariant(
                                        &term_path,
                                        "unknown load reference kind",
                                    ))
                                }
                            },
                            reserved: 0,
                            factor: f64_field(term, "factor", &term_path)?,
                        })
                    })
                    .collect::<Result<Vec<_>, Error>>()?
                    .into_boxed_slice();
                let (terms_ptr, term_count) = slice_parts(&terms);
                if !terms.is_empty() {
                    self.combination_term_arrays.push(terms);
                }
                Ok(sys::SaLoadCombinationDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaLoadCombinationDescriptorV1>(),
                    identity: self.identity(row, &path)?,
                    terms: terms_ptr,
                    term_count,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn time_functions(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaTimeFunctionDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/time_functions/{index}");
                let row = object(value, &path)?;
                let points = array_field(row, "points", &path)?
                    .iter()
                    .enumerate()
                    .map(|(point_index, point)| {
                        let pair =
                            fixed_f64_array::<2>(point, &format!("{path}/points/{point_index}"))?;
                        Ok(sys::SaTimePointV1 {
                            time: pair[0],
                            value: pair[1],
                        })
                    })
                    .collect::<Result<Vec<_>, Error>>()?
                    .into_boxed_slice();
                let (points_ptr, point_count) = slice_parts(&points);
                if !points.is_empty() {
                    self.time_point_arrays.push(points);
                }
                Ok(sys::SaTimeFunctionDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaTimeFunctionDescriptorV1>(),
                    id: view(string_field(row, "id", &path)?),
                    index: u64_field(row, "index", &path)?,
                    points: points_ptr,
                    point_count,
                    extensions_json: self.extension(
                        required(row, "extensions", &path)?,
                        &format!("{path}/extensions"),
                    )?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn construction_stages(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaConstructionStageDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/construction_stages/{index}");
                let row = object(value, &path)?;
                let (active_element_ids, active_element_id_count) = self.store_strings(
                    required(row, "active_element_ids", &path)?,
                    &format!("{path}/active_element_ids"),
                )?;
                let (active_constraint_ids, active_constraint_id_count) = self.store_strings(
                    required(row, "active_constraint_ids", &path)?,
                    &format!("{path}/active_constraint_ids"),
                )?;
                let (load_pattern_ids, load_pattern_id_count) = self.store_strings(
                    required(row, "load_pattern_ids", &path)?,
                    &format!("{path}/load_pattern_ids"),
                )?;
                Ok(sys::SaConstructionStageDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaConstructionStageDescriptorV1>(),
                    id: view(string_field(row, "id", &path)?),
                    index: u64_field(row, "index", &path)?,
                    active_element_ids,
                    active_element_id_count,
                    active_constraint_ids,
                    active_constraint_id_count,
                    load_pattern_ids,
                    load_pattern_id_count,
                    extensions_json: self.extension(
                        required(row, "extensions", &path)?,
                        &format!("{path}/extensions"),
                    )?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn roundtrip_rows(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaRoundtripRowDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/roundtrip_map/{index}");
                let row = object(value, &path)?;
                Ok(sys::SaRoundtripRowDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaRoundtripRowDescriptorV1>(),
                    source_entity_id: view(string_field(row, "source_entity_id", &path)?),
                    entity_kind: entity_kind(string_field(row, "entity_kind", &path)?)?,
                    reserved: 0,
                    model_ir_entity_id: view(string_field(row, "model_ir_entity_id", &path)?),
                    mapping_status: mapping_status(string_field(row, "mapping_status", &path)?)?,
                    reserved1: 0,
                    extensions_json: self.extension(
                        required(row, "extensions", &path)?,
                        &format!("{path}/extensions"),
                    )?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn unsupported_features(
        &mut self,
        values: &[Value],
    ) -> Result<Box<[sys::SaUnsupportedFeatureDescriptorV1]>, Error> {
        values
            .iter()
            .enumerate()
            .map(|(index, value)| {
                let path = format!("/unsupported_features/{index}");
                let row = object(value, &path)?;
                Ok(sys::SaUnsupportedFeatureDescriptorV1 {
                    abi_version: sys::SA_ABI_V1_1,
                    struct_size: abi_size::<sys::SaUnsupportedFeatureDescriptorV1>(),
                    feature_id: view(string_field(row, "feature_id", &path)?),
                    kind: view(string_field(row, "kind", &path)?),
                    source_entity_id: optional_string(
                        required(row, "source_entity_id", &path)?,
                        &format!("{path}/source_entity_id"),
                    )?,
                    disposition: disposition(string_field(row, "disposition", &path)?)?,
                    blocking: bool_flag(bool_field(row, "blocking", &path)?),
                    detail: view(string_field(row, "detail", &path)?),
                    extensions_json: self.extension(
                        required(row, "extensions", &path)?,
                        &format!("{path}/extensions"),
                    )?,
                })
            })
            .collect::<Result<Vec<_>, _>>()
            .map(Vec::into_boxed_slice)
    }

    fn store_dofs(
        &mut self,
        value: &Value,
        path: &str,
    ) -> Result<(*const sys::SaDofV1, u64), Error> {
        let values = array(value, path)?
            .iter()
            .enumerate()
            .map(|(index, value)| dof(string_value(value, &format!("{path}/{index}"))?))
            .collect::<Result<Vec<_>, _>>()?
            .into_boxed_slice();
        let parts = slice_parts(&values);
        if !values.is_empty() {
            self.dof_arrays.push(values);
        }
        Ok(parts)
    }

    fn store_strings(
        &mut self,
        value: &Value,
        path: &str,
    ) -> Result<(*const sys::SaStringViewV1, u64), Error> {
        let values = array(value, path)?
            .iter()
            .enumerate()
            .map(|(index, value)| string_value(value, &format!("{path}/{index}")).map(view))
            .collect::<Result<Vec<_>, _>>()?
            .into_boxed_slice();
        let parts = slice_parts(&values);
        if !values.is_empty() {
            self.string_view_arrays.push(values);
        }
        Ok(parts)
    }
}

fn abi_size<T>() -> u32 {
    u32::try_from(size_of::<T>()).unwrap_or(u32::MAX)
}

fn bool_flag(value: bool) -> u32 {
    u32::from(value)
}

fn view(value: &str) -> sys::SaStringViewV1 {
    sys::SaStringViewV1 {
        data: value.as_ptr().cast(),
        length: u64::try_from(value.len()).unwrap_or(u64::MAX),
    }
}

const fn empty_view() -> sys::SaStringViewV1 {
    sys::SaStringViewV1 {
        data: ptr::null(),
        length: 0,
    }
}

fn optional_string(value: &Value, path: &str) -> Result<sys::SaOptionalStringViewV1, Error> {
    match value {
        Value::Null => Ok(sys::SaOptionalStringViewV1 {
            value: empty_view(),
            is_present: 0,
            reserved: 0,
        }),
        Value::String(value) => Ok(sys::SaOptionalStringViewV1 {
            value: view(value),
            is_present: 1,
            reserved: 0,
        }),
        _ => Err(invariant(path, "expected nullable string")),
    }
}

fn optional_row_string(
    row: &Map<String, Value>,
    key: &str,
    path: &str,
) -> Result<sys::SaOptionalStringViewV1, Error> {
    row.get(key).map_or(
        Ok(sys::SaOptionalStringViewV1 {
            value: empty_view(),
            is_present: 0,
            reserved: 0,
        }),
        |value| optional_string(value, &format!("{path}/{key}")),
    )
}

fn slice_parts<T>(values: &[T]) -> (*const T, u64) {
    if values.is_empty() {
        (ptr::null(), 0)
    } else {
        (
            values.as_ptr(),
            u64::try_from(values.len()).unwrap_or(u64::MAX),
        )
    }
}

fn object<'a>(value: &'a Value, path: &str) -> Result<&'a Map<String, Value>, Error> {
    value
        .as_object()
        .ok_or_else(|| invariant(path, "expected object"))
}

fn array<'a>(value: &'a Value, path: &str) -> Result<&'a [Value], Error> {
    value
        .as_array()
        .map(Vec::as_slice)
        .ok_or_else(|| invariant(path, "expected array"))
}

fn required<'a>(row: &'a Map<String, Value>, key: &str, path: &str) -> Result<&'a Value, Error> {
    row.get(key)
        .ok_or_else(|| invariant(&format!("{path}/{key}"), "required field missing"))
}

fn object_field<'a>(
    row: &'a Map<String, Value>,
    key: &str,
    path: &str,
) -> Result<&'a Map<String, Value>, Error> {
    object(required(row, key, path)?, &format!("{path}/{key}"))
}

fn array_field<'a>(
    row: &'a Map<String, Value>,
    key: &str,
    path: &str,
) -> Result<&'a [Value], Error> {
    array(required(row, key, path)?, &format!("{path}/{key}"))
}

fn string_value<'a>(value: &'a Value, path: &str) -> Result<&'a str, Error> {
    value
        .as_str()
        .ok_or_else(|| invariant(path, "expected string"))
}

fn string_field<'a>(row: &'a Map<String, Value>, key: &str, path: &str) -> Result<&'a str, Error> {
    string_value(required(row, key, path)?, &format!("{path}/{key}"))
}

fn string_array<'a>(
    row: &'a Map<String, Value>,
    key: &str,
    path: &str,
) -> Result<Vec<&'a str>, Error> {
    array_field(row, key, path)?
        .iter()
        .enumerate()
        .map(|(index, value)| string_value(value, &format!("{path}/{key}/{index}")))
        .collect()
}

fn f64_value(value: &Value, path: &str) -> Result<f64, Error> {
    value
        .as_f64()
        .ok_or_else(|| invariant(path, "expected finite number"))
}

fn f64_field(row: &Map<String, Value>, key: &str, path: &str) -> Result<f64, Error> {
    f64_value(required(row, key, path)?, &format!("{path}/{key}"))
}

fn u64_field(row: &Map<String, Value>, key: &str, path: &str) -> Result<u64, Error> {
    required(row, key, path)?
        .as_u64()
        .ok_or_else(|| invariant(&format!("{path}/{key}"), "expected exact unsigned integer"))
}

fn bool_field(row: &Map<String, Value>, key: &str, path: &str) -> Result<bool, Error> {
    required(row, key, path)?
        .as_bool()
        .ok_or_else(|| invariant(&format!("{path}/{key}"), "expected boolean"))
}

fn fixed_f64_array<const N: usize>(value: &Value, path: &str) -> Result<[f64; N], Error> {
    let values = array(value, path)?;
    if values.len() != N {
        return Err(invariant(path, "fixed array length mismatch"));
    }
    let mut output = [0.0; N];
    for (index, value) in values.iter().enumerate() {
        output[index] = f64_value(value, &format!("{path}/{index}"))?;
    }
    Ok(output)
}

fn parameter_version(row: &Map<String, Value>, path: &str) -> Result<u32, Error> {
    match string_field(row, "parameter_set_version", path)? {
        "1" => Ok(1),
        _ => Err(invariant(
            &format!("{path}/parameter_set_version"),
            "unknown parameter set version",
        )),
    }
}

fn capability_profile(value: &str) -> Result<u32, Error> {
    match value {
        "engine_v2_phase0_linear_3d" => Ok(sys::SA_MODEL_IR_PROFILE_ENGINE_V2_PHASE0_LINEAR_3D),
        "bounded_planar_frame_alpha" => Ok(sys::SA_MODEL_IR_PROFILE_BOUNDED_PLANAR_FRAME_ALPHA),
        "planar_frame_verified_alpha.v1" => {
            Ok(sys::SA_MODEL_IR_PROFILE_PLANAR_FRAME_VERIFIED_ALPHA_V1)
        }
        "bounded_frame3d_direct_displacement_control" => {
            Ok(sys::SA_MODEL_IR_PROFILE_BOUNDED_FRAME3D_DIRECT_DISPLACEMENT_CONTROL)
        }
        _ => Err(invariant(
            "/capability_profile",
            "unknown capability profile",
        )),
    }
}

fn source_format(value: &str) -> Result<u32, Error> {
    match value {
        "neutral_json" => Ok(sys::SA_SOURCE_FORMAT_NEUTRAL_JSON),
        "midas_mgt" => Ok(sys::SA_SOURCE_FORMAT_MIDAS_MGT),
        "ifc" => Ok(sys::SA_SOURCE_FORMAT_IFC),
        "opensees" => Ok(sys::SA_SOURCE_FORMAT_OPENSEES),
        "etabs_e2k" => Ok(sys::SA_SOURCE_FORMAT_ETABS_E2K),
        "dxf" => Ok(sys::SA_SOURCE_FORMAT_DXF),
        "generated" => Ok(sys::SA_SOURCE_FORMAT_GENERATED),
        _ => Err(invariant(
            "/provenance/source_format",
            "unknown source format",
        )),
    }
}

fn source_units(row: &Map<String, Value>) -> Result<sys::SaSourceUnitsV1, Error> {
    Ok(sys::SaSourceUnitsV1 {
        abi_version: sys::SA_ABI_V1_1,
        struct_size: abi_size::<sys::SaSourceUnitsV1>(),
        length: match string_field(row, "length", "/units")? {
            "m" => sys::SA_LENGTH_UNIT_M,
            "mm" => sys::SA_LENGTH_UNIT_MM,
            "cm" => sys::SA_LENGTH_UNIT_CM,
            "ft" => sys::SA_LENGTH_UNIT_FT,
            "in" => sys::SA_LENGTH_UNIT_IN,
            _ => return Err(invariant("/units/length", "unknown length unit")),
        },
        force: match string_field(row, "force", "/units")? {
            "N" => sys::SA_FORCE_UNIT_N,
            "kN" => sys::SA_FORCE_UNIT_KN,
            "MN" => sys::SA_FORCE_UNIT_MN,
            "lbf" => sys::SA_FORCE_UNIT_LBF,
            "kip" => sys::SA_FORCE_UNIT_KIP,
            _ => return Err(invariant("/units/force", "unknown force unit")),
        },
        mass: match string_field(row, "mass", "/units")? {
            "kg" => sys::SA_MASS_UNIT_KG,
            "tonne" => sys::SA_MASS_UNIT_TONNE,
            "slug" => sys::SA_MASS_UNIT_SLUG,
            _ => return Err(invariant("/units/mass", "unknown mass unit")),
        },
        time: match string_field(row, "time", "/units")? {
            "s" => sys::SA_TIME_UNIT_S,
            _ => return Err(invariant("/units/time", "unknown time unit")),
        },
        rotation: match string_field(row, "rotation", "/units")? {
            "rad" => sys::SA_ROTATION_UNIT_RAD,
            "deg" => sys::SA_ROTATION_UNIT_DEG,
            _ => return Err(invariant("/units/rotation", "unknown rotation unit")),
        },
        reserved: 0,
    })
}

fn dof(value: &str) -> Result<u32, Error> {
    match value {
        "UX" => Ok(sys::SA_DOF_UX),
        "UY" => Ok(sys::SA_DOF_UY),
        "UZ" => Ok(sys::SA_DOF_UZ),
        "RX" => Ok(sys::SA_DOF_RX),
        "RY" => Ok(sys::SA_DOF_RY),
        "RZ" => Ok(sys::SA_DOF_RZ),
        _ => Err(invariant("/dof", "unknown DOF")),
    }
}

fn analysis_type(value: &str) -> Result<u32, Error> {
    match value {
        "linear_static" => Ok(sys::SA_ANALYSIS_LINEAR_STATIC),
        "nonlinear_static_load_control" => Ok(sys::SA_ANALYSIS_NONLINEAR_STATIC_LOAD_CONTROL),
        "nonlinear_static_direct_displacement_control" => {
            Ok(sys::SA_ANALYSIS_NONLINEAR_STATIC_DIRECT_DISPLACEMENT_CONTROL)
        }
        _ => Err(invariant("/analysis_type", "unknown analysis type")),
    }
}

fn entity_kind(value: &str) -> Result<u32, Error> {
    match value {
        "node" => Ok(sys::SA_MODEL_IR_ENTITY_NODE),
        "material" => Ok(sys::SA_MODEL_IR_ENTITY_MATERIAL),
        "section" => Ok(sys::SA_MODEL_IR_ENTITY_SECTION),
        "element" => Ok(sys::SA_MODEL_IR_ENTITY_ELEMENT),
        "constraint" => Ok(sys::SA_MODEL_IR_ENTITY_CONSTRAINT),
        "load_pattern" => Ok(sys::SA_MODEL_IR_ENTITY_LOAD_PATTERN),
        "load_combination" => Ok(sys::SA_MODEL_IR_ENTITY_LOAD_COMBINATION),
        "time_function" => Ok(sys::SA_MODEL_IR_ENTITY_TIME_FUNCTION),
        "construction_stage" => Ok(sys::SA_MODEL_IR_ENTITY_CONSTRUCTION_STAGE),
        _ => Err(invariant("/entity_kind", "unknown entity kind")),
    }
}

fn mapping_status(value: &str) -> Result<u32, Error> {
    match value {
        "exact" => Ok(sys::SA_ROUNDTRIP_EXACT),
        "canonicalized" => Ok(sys::SA_ROUNDTRIP_CANONICALIZED),
        "approximated" => Ok(sys::SA_ROUNDTRIP_APPROXIMATED),
        "unsupported" => Ok(sys::SA_ROUNDTRIP_UNSUPPORTED),
        _ => Err(invariant("/mapping_status", "unknown mapping status")),
    }
}

fn disposition(value: &str) -> Result<u32, Error> {
    match value {
        "blocked" => Ok(sys::SA_UNSUPPORTED_BLOCKED),
        "partial_import" => Ok(sys::SA_UNSUPPORTED_PARTIAL_IMPORT),
        "approximated" => Ok(sys::SA_UNSUPPORTED_APPROXIMATED),
        "preserved_only" => Ok(sys::SA_UNSUPPORTED_PRESERVED_ONLY),
        _ => Err(invariant("/disposition", "unknown unsupported disposition")),
    }
}

fn invariant(path: &str, detail: &str) -> Error {
    Error {
        code: sys::SA_ERR_INTERNAL,
        message: format!("validated ModelIR descriptor invariant at {path}: {detail}"),
    }
}
