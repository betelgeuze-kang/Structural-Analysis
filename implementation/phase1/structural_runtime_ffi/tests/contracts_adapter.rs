use std::path::{Path, PathBuf};

use structural_contracts::legacy_runtime::{parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3};
use structural_runtime_ffi::contracts::{
    inplace_scale_case_v3, nonlinear_ndtha_case_v3, nonlinear_static_case_v3, track_case_v3,
    NonlinearNdthaBuffers, NonlinearStaticBuffers,
};
use structural_runtime_ffi::{
    InplaceScaleStats, NlFrameNdthaConfig, NlFrameNdthaResult, NlFrameSolveConfig,
    NlFrameSolveResult, TrackSolveConfig, TrackSolveResult,
};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn golden(name: &str) -> LegacyRuntimeCaseV3 {
    let path = repository_root()
        .join("native/tests/fixtures/legacy_runtime_v3")
        .join(name);
    parse_legacy_runtime_case_v3(&std::fs::read(path).expect("golden fixture"))
        .expect("valid golden fixture")
}

#[test]
fn raw_track_and_scale_types_convert_to_pointer_free_golden_contracts() {
    let track_config = TrackSolveConfig {
        length_m: 10.0,
        node_count: 9,
        support_type: 0,
        theory: 0,
        bending_stiffness_n_m2: 1.0e8,
        shear_stiffness_n: 1.0e9,
        winkler_k_n_per_m2: 1.0e5,
        pasternak_g_n: 1.0e4,
        tolerance: 1.0e-9,
        cg_max_iter: 500,
        point_force_n: -10_000.0,
        point_position_m: 5.0,
    };
    let displacement = [
        0.0,
        -0.000_703_792_692_632_069_1,
        -0.001_321_670_876_610_801,
        -0.001_765_988_375_262_38,
        -0.001_945_845_157_517_316,
        -0.001_765_988_375_262_380_7,
        -0.001_321_670_876_610_801_4,
        -0.000_703_792_692_632_069_1,
        0.0,
    ];
    let rotation = [
        -0.000_528_668_350_644_320_4,
        -0.000_528_668_350_644_320_4,
        -0.000_424_878_273_052_124_4,
        -0.000_249_669_712_362_605_97,
        -2.602_085_213_965_210_5e-19,
        0.000_249_669_712_362_605_8,
        0.000_424_878_273_052_124_65,
        0.000_528_668_350_644_320_6,
        0.000_528_668_350_644_320_6,
    ];
    let track_result = TrackSolveResult {
        converged: 1,
        iterations: 4,
        residual_inf: 7.657_748_132_248_844e-10,
        max_abs_displacement_m: 0.001_945_845_157_517_316,
        mid_displacement_m: -0.001_945_845_157_517_316,
        status_code: 0,
    };
    let actual = track_case_v3(&track_config, &track_result, &displacement, &rotation)
        .expect("track adapter");
    assert_eq!(
        LegacyRuntimeCaseV3::Track(actual),
        golden("track_point_load.json")
    );

    let input = [1.0_f32, -2.0, 0.5, 4.0];
    let output = [1.25_f32, -2.5, 0.625, 5.0];
    let stats = InplaceScaleStats {
        ptr_before: 0x1000,
        ptr_after: 0x1000,
        len: 4,
        alpha: 1.25,
        sum_before: 3.5,
        sum_after: 4.375,
        max_abs_before: 4.0,
        max_abs_after: 5.0,
        status_code: 0,
    };
    let actual = inplace_scale_case_v3(&input, &output, &stats).expect("scale adapter");
    assert_eq!(
        LegacyRuntimeCaseV3::InplaceScale(actual),
        golden("inplace_scale_f32.json")
    );
}

#[test]
fn raw_static_and_ndtha_types_convert_to_golden_contracts() {
    let static_config = NlFrameSolveConfig {
        story_count: 3,
        tolerance: 1.0e-7,
        max_iter: 60,
        hardening_ratio: 0.04,
        line_search_decay: 0.5,
        line_search_min: 0.031_25,
        pdelta_factor: 1.0,
    };
    let static_result = NlFrameSolveResult {
        converged: 1,
        iterations: 6,
        residual_inf: 6.795_744_411_647_32e-9,
        residual_l2: 7.319_227_424_693_27e-9,
        max_abs_displacement_m: 0.000_470_555_555_555_699_4,
        top_displacement_m: 0.000_470_555_555_555_699_4,
        base_shear_kn: 24.000_000_000_010_04,
        plastic_story_count: 0,
        line_search_backtracks: 0,
        status_code: 0,
    };
    let stiffness = [1.0e8, 9.0e7, 8.0e7];
    let heights = [3.0, 3.0, 3.0];
    let axial = [1.0e6, 8.0e5, 6.0e5];
    let yield_drift = [0.02, 0.02, 0.02];
    let loads = [10_000.0, 8_000.0, 6_000.0];
    let displacement = [
        0.000_240_000_000_000_100_4,
        0.000_395_555_555_555_692,
        0.000_470_555_555_555_699_4,
    ];
    let actual = nonlinear_static_case_v3(
        &static_config,
        &static_result,
        NonlinearStaticBuffers {
            story_k_n_per_m: &stiffness,
            story_h_m: &heights,
            story_axial_n: &axial,
            story_yield_drift_m: &yield_drift,
            floor_load_n: &loads,
            u_story_m: &displacement,
        },
    )
    .expect("static adapter");
    assert_eq!(
        LegacyRuntimeCaseV3::NonlinearStatic(actual),
        golden("nonlinear_static.json")
    );

    let ndtha_config = NlFrameNdthaConfig {
        story_count: 2,
        step_count: 3,
        dt_s: 0.01,
        newmark_beta: 0.25,
        newmark_gamma: 0.5,
        tolerance: 1.0e-5,
        max_step_iterations: 16,
        adaptive_load_decay: 0.82,
        damping_force_cap_ratio: 0.6,
        newton_max_iter: 120,
        line_search_decay: 0.5,
        line_search_min: 0.031_25,
        hardening_ratio: 0.2,
        pdelta_factor: 1.0,
        collapse_drift_threshold_pct: 10.0,
    };
    let ndtha_result = NlFrameNdthaResult {
        converged_all_steps: 1,
        rust_backend_all_steps: 1,
        collapsed: 0,
        collapse_step: -1,
        collapse_time_s: 0.0,
        collapse_drift_ratio_pct: 0.0,
        collapse_top_displacement_m: 0.0,
        step_count_completed: 3,
        max_plastic_story_count: 0,
        max_drift_ratio_pct: 8.560_401_406_754_784e-5,
        avg_step_iterations: 1.0,
        residual_top_displacement_m: 3.795_754_248_884_991e-6,
        residual_drift_ratio_pct: 8.560_401_406_754_784e-5,
        status_code: 0,
    };
    let stiffness = [1.0e8, 9.0e7];
    let heights = [3.0, 3.0];
    let axial = [1.0e6, 8.0e5];
    let yield_drift = [0.02, 0.02];
    let mass = [10_000.0, 8_000.0];
    let damping = [1_000.0, 900.0];
    let loads = [10_000.0, 8_000.0];
    let acceleration = [0.0, 0.01, -0.005];
    let top = [
        4.084_273_705_964_167e-7,
        2.008_674_095_445_957e-6,
        3.795_754_248_884_991e-6,
    ];
    let drift = [
        1.167_731_071_112_621_1e-5,
        5.301_851_826_285_648e-5,
        8.560_401_406_754_784e-5,
    ];
    let base = [
        0.035_031_932_133_378_636,
        0.159_055_554_788_569_42,
        0.256_812_042_202_643_6,
    ];
    let residual = [
        9.752_318_419_486_983e-8,
        2.736_757_522_825_428e-7,
        4.408_786_935_528_042e-8,
    ];
    let story_drift = [8.560_401_406_754_784e-5, 4.092_112_756_195_183_6e-5];
    let actual = nonlinear_ndtha_case_v3(
        &ndtha_config,
        &ndtha_result,
        NonlinearNdthaBuffers {
            story_k_n_per_m: &stiffness,
            story_h_m: &heights,
            story_axial_n: &axial,
            story_yield_drift_m: &yield_drift,
            story_mass_kg: &mass,
            story_damping_n_s_per_m: &damping,
            floor_load_base_n: &loads,
            ag_g: &acceleration,
            top_displacement_m: &top,
            drift_ratio_pct: &drift,
            base_shear_kn: &base,
            core_drift_pct: &drift,
            core_shear_kn: &base,
            step_converged: &[1, 1, 1],
            step_iterations: &[1, 1, 1],
            step_plastic_story_count: &[0, 0, 0],
            step_residual_inf: &residual,
            story_drift_envelope_pct: &story_drift,
            final_story_drift_pct: &story_drift,
        },
    )
    .expect("NDTHA adapter");
    assert_eq!(
        LegacyRuntimeCaseV3::NonlinearNdtha(Box::new(actual)),
        golden("nonlinear_ndtha.json")
    );
}

#[test]
fn adapter_rejects_unknown_raw_values_and_length_drift() {
    let config = TrackSolveConfig {
        length_m: 10.0,
        node_count: 9,
        support_type: 7,
        theory: 0,
        bending_stiffness_n_m2: 1.0,
        shear_stiffness_n: 1.0,
        winkler_k_n_per_m2: 0.0,
        pasternak_g_n: 0.0,
        tolerance: 1.0e-6,
        cg_max_iter: 1,
        point_force_n: 0.0,
        point_position_m: 0.0,
    };
    let result = TrackSolveResult {
        converged: 2,
        iterations: 0,
        residual_inf: 0.0,
        max_abs_displacement_m: 0.0,
        mid_displacement_m: 0.0,
        status_code: 0,
    };
    let error =
        track_case_v3(&config, &result, &[0.0; 9], &[0.0; 9]).expect_err("unknown support enum");
    assert_eq!(error.code, "legacy_runtime_unknown_enum");
    assert_eq!(error.field, "support_type");

    let stats = InplaceScaleStats {
        ptr_before: 1,
        ptr_after: 1,
        len: 4,
        alpha: 1.0,
        sum_before: 0.0,
        sum_after: 0.0,
        max_abs_before: 0.0,
        max_abs_after: 0.0,
        status_code: 0,
    };
    let error = inplace_scale_case_v3(&[0.0; 3], &[0.0; 4], &stats).expect_err("length mismatch");
    assert_eq!(error.code, "legacy_runtime_vector_length_mismatch");
}
