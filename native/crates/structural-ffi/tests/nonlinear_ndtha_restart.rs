use std::path::{Path, PathBuf};

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearNdthaCaseV3,
};
use structural_ffi::{Api, NonlinearNdthaExecutionStatus, NonlinearNdthaRestartState};
use structural_ffi_sys::{SA_ERR_CHECKPOINT_MISMATCH, SA_ERR_NONCONVERGENCE};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn case() -> NonlinearNdthaCaseV3 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/legacy_runtime_v3/nonlinear_ndtha.json"),
    )
    .expect("tracked neutral fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict nonlinear NDTHA fixture") {
        LegacyRuntimeCaseV3::NonlinearNdtha(case) => *case,
        _ => panic!("nonlinear NDTHA fixture decoded as another family"),
    }
}

fn assert_same_bits(left: f64, right: f64) {
    assert_eq!(left.to_bits(), right.to_bits());
}

fn assert_completed_state_matches_one_shot(
    state: &NonlinearNdthaRestartState,
    solution: &structural_ffi::NonlinearNdthaSolution,
) {
    assert_eq!(state.status, NonlinearNdthaExecutionStatus::Completed);
    assert_eq!(state.next_step, solution.step_count_completed);
    assert_eq!(state.collapse_step, solution.collapse_step);
    assert_same_bits(state.collapse_time_s, solution.collapse_time_s);
    assert_same_bits(
        state.collapse_drift_ratio_pct,
        solution.collapse_drift_ratio_pct,
    );
    assert_same_bits(
        state.collapse_top_displacement_m,
        solution.collapse_top_displacement_m,
    );
    assert_eq!(
        state.max_plastic_story_count,
        solution.max_plastic_story_count
    );
    assert_same_bits(state.max_drift_ratio_pct, solution.max_drift_ratio_pct);
    assert_eq!(
        state.total_line_search_backtracks,
        solution.total_line_search_backtracks
    );
    assert_eq!(state.response, solution.response);
    assert_same_bits(
        *state.displacement_m.last().expect("top displacement"),
        solution.residual_top_displacement_m,
    );
    assert_eq!(state.execution_backend, solution.execution_backend);
    assert_eq!(state.fallback_count, solution.fallback_count);
}

#[test]
fn safe_v1_5_restart_is_bitwise_identical_across_segmentations() {
    let case = case();
    let one_shot = Api::load_nonlinear_ndtha()
        .expect("v1.4 API")
        .solve_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("one-shot solve");
    let api = Api::load_nonlinear_ndtha_restart().expect("v1.5 API");

    let mut segmented = api
        .initial_nonlinear_ndtha_state(&case.config, &case.inputs)
        .expect("initial restart state");
    let zero = segmented.clone();
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, 0, &mut segmented)
        .expect("zero-budget no-op");
    assert_eq!(segmented, zero);
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut segmented)
        .expect("first segment");
    assert_eq!(segmented.status, NonlinearNdthaExecutionStatus::Active);
    assert_eq!(segmented.next_step, 1);
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, u32::MAX, &mut segmented)
        .expect("resumed completion");

    let mut bulk = api
        .initial_nonlinear_ndtha_state(&case.config, &case.inputs)
        .expect("second initial state");
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, u32::MAX, &mut bulk)
        .expect("bulk completion");
    assert_eq!(segmented, bulk);
    assert_completed_state_matches_one_shot(&segmented, &one_shot);

    let terminal = segmented.clone();
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, u32::MAX, &mut segmented)
        .expect("terminal resume is idempotent");
    assert_eq!(segmented, terminal);
}

#[test]
fn safe_v1_5_restart_rejects_tamper_and_nonconvergence_atomically() {
    let case = case();
    let api = Api::load_nonlinear_ndtha_restart().expect("v1.5 API");
    let mut state = api
        .initial_nonlinear_ndtha_state(&case.config, &case.inputs)
        .expect("initial restart state");
    api.advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut state)
        .expect("first segment");
    state.response.step_iterations[2] = 1;
    let corrupt = state.clone();
    let error = api
        .advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut state)
        .expect_err("tail tamper must fail");
    assert_eq!(error.code, SA_ERR_CHECKPOINT_MISMATCH);
    assert_eq!(state, corrupt);

    let mut bounded = case.config.clone();
    bounded.max_step_iterations = 1;
    bounded.newton_max_iter = 1;
    bounded.tolerance = 1.0e-30;
    let mut failed = api
        .initial_nonlinear_ndtha_state(&bounded, &case.inputs)
        .expect("bounded initial state");
    let original = failed.clone();
    let error = api
        .advance_nonlinear_ndtha(&bounded, &case.inputs, 1, &mut failed)
        .expect_err("bounded solve must not converge");
    assert_eq!(error.code, SA_ERR_NONCONVERGENCE);
    assert_eq!(failed, original);
}

#[test]
fn safe_v1_5_restart_preserves_collapse_as_a_terminal_state() {
    let case = case();
    let mut collapse = case.config.clone();
    collapse.collapse_drift_threshold_pct = 1.0e-6;
    let api = Api::load_nonlinear_ndtha_restart().expect("v1.5 API");
    let mut state = api
        .initial_nonlinear_ndtha_state(&collapse, &case.inputs)
        .expect("initial collapse state");
    api.advance_nonlinear_ndtha(&collapse, &case.inputs, u32::MAX, &mut state)
        .expect("collapse is a complete checkpoint");
    assert_eq!(state.status, NonlinearNdthaExecutionStatus::Collapsed);
    assert_eq!(state.next_step, 1);
    assert_eq!(state.collapse_step, 0);
    let terminal = state.clone();
    api.advance_nonlinear_ndtha(&collapse, &case.inputs, u32::MAX, &mut state)
        .expect("collapsed resume is idempotent");
    assert_eq!(state, terminal);
}
