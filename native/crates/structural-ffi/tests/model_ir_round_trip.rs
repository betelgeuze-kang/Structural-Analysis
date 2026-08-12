use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use structural_contracts::model_ir::{parse_model_ir_v2, ModelIrV2Document};
use structural_ffi::Api;

const GOLDEN_FIXTURES: [&str; 8] = [
    "tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json",
    "examples/bounded_planar_frame_alpha.model-ir.v2.json",
    "examples/bounded_planar_settlement.model-ir.v2.json",
    "examples/bounded_frame3d_direct_control.model-ir.v2.json",
    "examples/bounded_frame3d_direct_control_axial_yield.model-ir.v2.json",
    "examples/bounded_frame3d_direct_control_ry_bending.model-ir.v2.json",
    "examples/bounded_frame3d_direct_control_rz_bending.model-ir.v2.json",
    "examples/bounded_frame3d_direct_control_torsion.model-ir.v2.json",
];

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn fixture_value() -> Value {
    serde_json::from_slice(
        &std::fs::read(repository_root().join(GOLDEN_FIXTURES[0])).expect("fixture bytes"),
    )
    .expect("fixture JSON")
}

fn document(value: &Value) -> ModelIrV2Document {
    parse_model_ir_v2(&serde_json::to_vec(value).expect("JSON bytes"))
        .expect("schema-valid ModelIR")
}

#[test]
fn every_tracked_positive_fixture_completes_the_native_round_trip() {
    let api = Api::load_model_ir().expect("v1.1 API");
    for relative in GOLDEN_FIXTURES {
        let bytes = std::fs::read(repository_root().join(relative)).expect("fixture bytes");
        let source = parse_model_ir_v2(&bytes).expect("schema-valid fixture");
        let validation = api
            .validate_model_ir(&source)
            .expect("verified native round-trip");
        assert!(validation.report.contract_valid, "{relative}");
        assert!(validation.report.analysis_ready, "{relative}");
        assert!(validation.report.issues.is_empty(), "{relative}");
        assert_eq!(
            validation.snapshot.canonical_bytes(),
            source.canonical_bytes(),
            "{relative}"
        );
        assert_eq!(
            validation.report.content_hash,
            source.content_hash(),
            "{relative}"
        );
        assert_eq!(
            validation.report.semantic_hash,
            source.semantic_hash(),
            "{relative}"
        );
        assert_eq!(
            validation.report.provenance_hash,
            source.provenance_hash(),
            "{relative}"
        );
    }
}

#[test]
// One cohesive fixture intentionally enumerates every otherwise-uncovered descriptor family.
#[allow(clippy::too_many_lines)]
fn descriptor_arena_covers_the_remaining_typed_families_and_nullable_fields() {
    let mut value = fixture_value();
    value["extensions"] = json!({"test.native:payload": {"signed_zero": -0.0}});
    value["materials"][0]["admissibility"] = json!({
        "loading_domain": "three_dimensional",
        "supports_unloading": true,
        "supports_reversal": true,
        "supports_cyclic": true,
        "supports_tension": true,
        "supports_compression": true,
        "supports_multiaxial": true
    });
    value["nodes"].as_array_mut().expect("nodes").push(json!({
        "id": "N3",
        "index": 2,
        "coordinates_m": [2.0, 1.0, 0.0],
        "source_id": null,
        "extensions": {"test.native:node": "nullable-source"}
    }));
    value["sections"]
        .as_array_mut()
        .expect("sections")
        .push(json!({
            "id": "S2",
            "index": 1,
            "family_id": "truss_3d",
            "parameter_set_version": "1",
            "parameters": {"area_m2": 0.005},
            "source_id": null,
            "extensions": {}
        }));
    value["elements"]
        .as_array_mut()
        .expect("elements")
        .push(json!({
            "id": "E2",
            "index": 1,
            "type": "truss_3d",
            "formulation": "linear_truss_3d",
            "node_ids": ["N2", "N3"],
            "material_id": "M1",
            "section_id": "S2",
            "offsets": {"i_global_m": [0.0, 0.0, 0.0], "j_global_m": [0.0, 0.0, 0.0]},
            "source_id": null,
            "extensions": {}
        }));
    value["load_combinations"] = json!([
        {
            "id": "COMB1",
            "index": 0,
            "combination_type": "linear",
            "terms": [{"ref_id": "LC_AXIAL", "ref_kind": "load_pattern", "factor": 1.2}],
            "source_id": null,
            "extensions": {}
        },
        {
            "id": "COMB2",
            "index": 1,
            "combination_type": "linear",
            "terms": [{"ref_id": "COMB1", "ref_kind": "load_combination", "factor": 0.8}],
            "source_id": "generated:COMB2",
            "extensions": {}
        }
    ]);
    value["time_functions"] = json!([{
        "id": "TF1",
        "index": 0,
        "type": "piecewise_linear",
        "points": [[0.0, 0.0], [1.0, 1.0]],
        "extensions": {"test.native:time": true}
    }]);
    value["construction_stages"] = json!([{
        "id": "STAGE1",
        "index": 0,
        "active_element_ids": ["E1", "E2"],
        "active_constraint_ids": ["BC1"],
        "load_pattern_ids": ["LC_AXIAL"],
        "extensions": {}
    }]);
    value["roundtrip_map"] = json!([
        {"source_entity_id": "source:N1", "entity_kind": "node", "model_ir_entity_id": "N1", "mapping_status": "exact", "extensions": {}},
        {"source_entity_id": "source:M1", "entity_kind": "material", "model_ir_entity_id": "M1", "mapping_status": "canonicalized", "extensions": {}},
        {"source_entity_id": "source:S1", "entity_kind": "section", "model_ir_entity_id": "S1", "mapping_status": "approximated", "extensions": {}},
        {"source_entity_id": "source:E1", "entity_kind": "element", "model_ir_entity_id": "E1", "mapping_status": "exact", "extensions": {}},
        {"source_entity_id": "source:BC1", "entity_kind": "constraint", "model_ir_entity_id": "BC1", "mapping_status": "canonicalized", "extensions": {}},
        {"source_entity_id": "source:LC_AXIAL", "entity_kind": "load_pattern", "model_ir_entity_id": "LC_AXIAL", "mapping_status": "approximated", "extensions": {}},
        {"source_entity_id": "source:COMB1", "entity_kind": "load_combination", "model_ir_entity_id": "COMB1", "mapping_status": "exact", "extensions": {}},
        {"source_entity_id": "source:TF1", "entity_kind": "time_function", "model_ir_entity_id": "TF1", "mapping_status": "canonicalized", "extensions": {}},
        {"source_entity_id": "source:STAGE1", "entity_kind": "construction_stage", "model_ir_entity_id": "STAGE1", "mapping_status": "approximated", "extensions": {}}
    ]);
    value["unsupported_features"] = json!([
        {
            "feature_id": "feature.preserved",
            "kind": "source_annotation",
            "source_entity_id": null,
            "disposition": "preserved_only",
            "blocking": false,
            "detail": "Preserved for round-trip without solver meaning.",
            "extensions": {}
        },
        {
            "feature_id": "feature.partial",
            "kind": "partial_import",
            "source_entity_id": "source:E1",
            "disposition": "partial_import",
            "blocking": false,
            "detail": "A non-blocking portion was imported.",
            "extensions": {}
        },
        {
            "feature_id": "feature.approximated",
            "kind": "approximation",
            "source_entity_id": "source:S1",
            "disposition": "approximated",
            "blocking": false,
            "detail": "A non-blocking approximation was recorded.",
            "extensions": {}
        }
    ]);

    let source = document(&value);
    let validation = Api::load_model_ir()
        .expect("v1.1 API")
        .validate_model_ir(&source)
        .expect("full typed family round-trip");
    assert!(validation.report.contract_valid);
    assert!(validation.report.analysis_ready);
    assert!(validation.report.issues.is_empty());
    assert_eq!(validation.report.entity_counts.nodes, 3);
    assert_eq!(validation.report.entity_counts.sections, 2);
    assert_eq!(validation.report.entity_counts.elements, 2);
    assert_eq!(validation.report.entity_counts.load_combinations, 2);
    assert_eq!(validation.report.entity_counts.time_functions, 1);
    assert_eq!(validation.report.entity_counts.construction_stages, 1);
    assert_eq!(validation.report.entity_counts.roundtrip_map, 9);
    assert_eq!(validation.report.entity_counts.unsupported_features, 3);
    assert_eq!(
        validation.snapshot.canonical_bytes(),
        source.canonical_bytes()
    );
}

#[test]
fn semantic_invalidity_and_explicit_blockers_remain_distinct_success_reports() {
    let api = Api::load_model_ir().expect("v1.1 API");
    let mut mismatch = fixture_value();
    mismatch["provenance"]["unit_scales_to_si"]["length_to_m"] = json!(10.0);
    let mismatch = api
        .validate_model_ir(&document(&mismatch))
        .expect("semantic invalidity is a report");
    assert!(!mismatch.report.semantics_valid);
    assert!(!mismatch.report.contract_valid);
    assert!(!mismatch.report.analysis_ready);
    assert!(mismatch.report.issues.iter().any(|issue| {
        issue.code == "unit_scale_mismatch"
            && issue.path == "/provenance/unit_scales_to_si/length_to_m"
    }));

    let mut blocked = fixture_value();
    blocked["unsupported_features"] = json!([{
        "feature_id": "feature.blocked",
        "kind": "unsupported_solver_feature",
        "source_entity_id": null,
        "disposition": "blocked",
        "blocking": true,
        "detail": "Requires a solver capability outside this slice.",
        "extensions": {}
    }]);
    let blocked = api
        .validate_model_ir(&document(&blocked))
        .expect("explicit blocker is a report");
    assert!(blocked.report.semantics_valid);
    assert!(blocked.report.contract_valid);
    assert!(!blocked.report.analysis_ready);
    assert_eq!(blocked.report.blocking_feature_ids, ["feature.blocked"]);
    assert!(blocked.report.issues.is_empty());
}

#[test]
fn every_schema_profile_source_format_and_source_unit_enum_crosses_the_abi() {
    let api = Api::load_model_ir().expect("v1.1 API");
    let planar_bytes = std::fs::read(
        repository_root().join("examples/bounded_planar_frame_alpha.model-ir.v2.json"),
    )
    .expect("planar fixture");
    let mut verified: Value = serde_json::from_slice(&planar_bytes).expect("fixture JSON");
    verified["capability_profile"] = json!("planar_frame_verified_alpha.v1");
    let verified = api
        .validate_model_ir(&document(&verified))
        .expect("verified profile descriptor");
    assert!(verified.report.analysis_ready);

    for source_format in [
        "neutral_json",
        "midas_mgt",
        "ifc",
        "opensees",
        "etabs_e2k",
        "dxf",
        "generated",
    ] {
        let mut value = fixture_value();
        value["provenance"]["source_format"] = json!(source_format);
        let validation = api
            .validate_model_ir(&document(&value))
            .expect("source format descriptor");
        assert!(validation.report.contract_valid, "{source_format}");
    }

    for (family, symbol, scale_key, scale) in [
        ("length", "m", "length_to_m", 1.0),
        ("length", "mm", "length_to_m", 1.0e-3),
        ("length", "cm", "length_to_m", 1.0e-2),
        ("length", "ft", "length_to_m", 0.3048),
        ("length", "in", "length_to_m", 0.0254),
        ("force", "N", "force_to_n", 1.0),
        ("force", "kN", "force_to_n", 1.0e3),
        ("force", "MN", "force_to_n", 1.0e6),
        ("force", "lbf", "force_to_n", 4.448_221_615_260_5),
        ("force", "kip", "force_to_n", 4_448.221_615_260_5),
        ("mass", "kg", "mass_to_kg", 1.0),
        ("mass", "tonne", "mass_to_kg", 1.0e3),
        ("mass", "slug", "mass_to_kg", 14.593_902_937_206),
        ("time", "s", "time_to_s", 1.0),
        ("rotation", "rad", "rotation_to_rad", 1.0),
        (
            "rotation",
            "deg",
            "rotation_to_rad",
            std::f64::consts::PI / 180.0,
        ),
    ] {
        let mut value = fixture_value();
        value["provenance"]["source_units"][family] = json!(symbol);
        value["provenance"]["unit_scales_to_si"][scale_key] = json!(scale);
        let validation = api
            .validate_model_ir(&document(&value))
            .expect("source unit descriptor");
        assert!(validation.report.contract_valid, "{family}:{symbol}");
    }
}
