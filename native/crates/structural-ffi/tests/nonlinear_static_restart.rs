use std::path::{Path, PathBuf};

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearStaticCaseV3,
};
use structural_ffi::{Api, NonlinearStaticExecutionStatus, NonlinearStaticRestartState};
use structural_ffi_sys::{SA_ERR_CHECKPOINT_MISMATCH, SA_ERR_NONCONVERGENCE, SA_ERR_UNSUPPORTED};

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

fn case() -> NonlinearStaticCaseV3 {
    let bytes = std::fs::read(
        repository_root().join("native/tests/fixtures/legacy_runtime_v3/nonlinear_static.json"),
    )
    .expect("tracked nonlinear-static fixture");
    match parse_legacy_runtime_case_v3(&bytes).expect("strict fixture") {
        LegacyRuntimeCaseV3::NonlinearStatic(case) => case,
        _ => panic!("fixture decoded as another family"),
    }
}

fn round_trip(state: &NonlinearStaticRestartState) -> NonlinearStaticRestartState {
    let bytes = serde_json::to_vec(state).expect("serialize pointer-free state");
    serde_json::from_slice(&bytes).expect("deserialize pointer-free state")
}

#[test]
fn safe_v1_11_restart_is_bitwise_identical_across_real_newton_boundaries() {
    let case = case();
    let one_shot = Api::load_nonlinear_static()
        .expect("v1.3 table")
        .solve_nonlinear_static(&case.config, &case.inputs)
        .expect("one-shot Newton solve");
    let api = Api::load_nonlinear_static_restart().expect("v1.11 table");

    let mut segmented = api
        .begin_nonlinear_static(&case.config, &case.inputs)
        .expect("iteration-zero state");
    assert_eq!(segmented.status, NonlinearStaticExecutionStatus::Active);
    let zero = segmented.clone();
    api.advance_nonlinear_static(&case.config, &case.inputs, 0, &mut segmented)
        .expect("zero-budget validation");
    assert_eq!(segmented, zero);
    api.advance_nonlinear_static(&case.config, &case.inputs, 1, &mut segmented)
        .expect("first published Newton iteration");
    assert_eq!(segmented.status, NonlinearStaticExecutionStatus::Active);
    assert_eq!(segmented.iterations, 1);
    segmented = round_trip(&segmented);
    api.advance_nonlinear_static(&case.config, &case.inputs, 2, &mut segmented)
        .expect("two resumed Newton iterations");
    segmented = round_trip(&segmented);
    api.advance_nonlinear_static(&case.config, &case.inputs, u32::MAX, &mut segmented)
        .expect("resumed completion");

    let mut direct = api
        .begin_nonlinear_static(&case.config, &case.inputs)
        .expect("second iteration-zero state");
    api.advance_nonlinear_static(&case.config, &case.inputs, u32::MAX, &mut direct)
        .expect("direct completion");
    assert_eq!(segmented, direct);
    assert_eq!(direct.status, NonlinearStaticExecutionStatus::Converged);
    assert_eq!(
        direct.terminal_solution().expect("terminal result"),
        one_shot
    );

    let terminal = direct.clone();
    api.advance_nonlinear_static(&case.config, &case.inputs, 1, &mut direct)
        .expect("terminal state is idempotent");
    assert_eq!(direct, terminal);
}

#[test]
fn safe_v1_11_restart_rejects_tamper_and_binding_changes_atomically() {
    let api = Api::load_nonlinear_static_restart().expect("v1.11 table");
    let case = case();
    let mut state = api
        .begin_nonlinear_static(&case.config, &case.inputs)
        .expect("iteration-zero state");
    api.advance_nonlinear_static(&case.config, &case.inputs, 1, &mut state)
        .expect("first iteration");

    state.residual_inf = f64::from_bits(state.residual_inf.to_bits() ^ 1);
    let corrupt = state.clone();
    let error = api
        .advance_nonlinear_static(&case.config, &case.inputs, 1, &mut state)
        .expect_err("changed derived metric must fail");
    assert_eq!(error.code, SA_ERR_CHECKPOINT_MISMATCH);
    assert_eq!(state, corrupt);

    let mut bound = api
        .begin_nonlinear_static(&case.config, &case.inputs)
        .expect("fresh state");
    api.advance_nonlinear_static(&case.config, &case.inputs, 1, &mut bound)
        .expect("bind a nonzero state");
    let original = bound.clone();
    let mut changed_inputs = case.inputs.clone();
    changed_inputs.floor_load_n[0] += 1.0;
    let error = api
        .advance_nonlinear_static(&case.config, &changed_inputs, 1, &mut bound)
        .expect_err("changed problem binding must fail");
    assert_eq!(error.code, SA_ERR_CHECKPOINT_MISMATCH);
    assert_eq!(bound, original);
}

#[test]
fn numerical_nonconvergence_remains_a_terminal_checkpoint_state() {
    let api = Api::load_nonlinear_static_restart().expect("v1.11 table");
    let case = case();
    let mut config = case.config.clone();
    config.max_iter = 1;
    let mut state = api
        .begin_nonlinear_static(&config, &case.inputs)
        .expect("bounded initial state");
    api.advance_nonlinear_static(&config, &case.inputs, u32::MAX, &mut state)
        .expect("nonconvergence is a terminal transition");
    assert_eq!(state.status, NonlinearStaticExecutionStatus::Nonconverged);
    assert_eq!(
        state
            .terminal_solution()
            .expect_err("nonconvergence taxonomy")
            .code,
        SA_ERR_NONCONVERGENCE
    );
}

#[test]
fn v1_10_table_cannot_expose_v1_11_restart() {
    let old = Api::load_sparse_linear_restart().expect("v1.10 table");
    let case = case();
    let error = old
        .begin_nonlinear_static(&case.config, &case.inputs)
        .expect_err("v1.10 cannot expose nonlinear-static restart");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}
