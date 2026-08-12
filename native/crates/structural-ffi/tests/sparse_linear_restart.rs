use structural_ffi::{
    Api, SparseCsrMatrix, SparseLinearConfig, SparseLinearExecutionStatus,
    SparseLinearRestartState, SparseLinearSolverStatus,
};
use structural_ffi_sys::{
    SA_ERR_CHECKPOINT_MISMATCH, SA_ERR_INCREMENT_LIMIT, SA_ERR_NONCONVERGENCE, SA_ERR_SINGULARITY,
    SA_ERR_UNSUPPORTED,
};

fn matrix() -> SparseCsrMatrix {
    SparseCsrMatrix {
        row_offsets: vec![0, 2, 5, 8, 11, 13],
        column_indices: vec![0, 1, 0, 1, 2, 1, 2, 3, 2, 3, 4, 3, 4],
        values: vec![
            4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 4.0, -1.0, -1.0, 3.0, -1.0, -1.0, 2.0,
        ],
    }
}

fn right_hand_side() -> [f64; 5] {
    [6.0, -12.0, 18.0, -20.0, 14.0]
}

fn config() -> SparseLinearConfig {
    SparseLinearConfig {
        max_iterations: 100,
        absolute_residual_tolerance: 1.0e-13,
        relative_residual_tolerance: 1.0e-13,
        maximum_increment: 0.0,
    }
}

fn round_trip(state: &SparseLinearRestartState) -> SparseLinearRestartState {
    let bytes = serde_json::to_vec(state).expect("serialize pointer-free restart state");
    serde_json::from_slice(&bytes).expect("deserialize pointer-free restart state")
}

#[test]
fn safe_v1_10_restart_is_bitwise_identical_across_real_pcg_boundaries() {
    let matrix = matrix();
    let rhs = right_hand_side();
    let config = config();
    let one_shot = Api::load_sparse_linear()
        .expect("v1.8 table")
        .solve_sparse_linear(&matrix, &rhs, None, config)
        .expect("one-shot PCG");
    let api = Api::load_sparse_linear_restart().expect("v1.10 table");

    let mut segmented = api
        .begin_sparse_linear(&matrix, &rhs, None, config)
        .expect("iteration-zero state");
    assert_eq!(
        segmented.execution_status,
        SparseLinearExecutionStatus::Active
    );
    let zero = segmented.clone();
    api.advance_sparse_linear(&matrix, &rhs, config, 0, &mut segmented)
        .expect("zero-budget validation");
    assert_eq!(segmented, zero);
    api.advance_sparse_linear(&matrix, &rhs, config, 1, &mut segmented)
        .expect("first published PCG iteration");
    assert_eq!(
        segmented.execution_status,
        SparseLinearExecutionStatus::Active
    );
    assert_eq!(segmented.iterations, 1);
    segmented = round_trip(&segmented);
    api.advance_sparse_linear(&matrix, &rhs, config, 1, &mut segmented)
        .expect("second published PCG iteration");
    segmented = round_trip(&segmented);
    api.advance_sparse_linear(&matrix, &rhs, config, u32::MAX, &mut segmented)
        .expect("resumed completion");

    let mut direct = api
        .begin_sparse_linear(&matrix, &rhs, None, config)
        .expect("second iteration-zero state");
    api.advance_sparse_linear(&matrix, &rhs, config, u32::MAX, &mut direct)
        .expect("direct completion");
    assert_eq!(segmented, direct);
    assert_eq!(
        direct.execution_status,
        SparseLinearExecutionStatus::Terminal
    );
    assert_eq!(direct.solver_status, SparseLinearSolverStatus::Converged);
    assert_eq!(
        direct.terminal_solution().expect("terminal result"),
        one_shot
    );

    let terminal = direct.clone();
    api.advance_sparse_linear(&matrix, &rhs, config, 1, &mut direct)
        .expect("terminal state is idempotent");
    assert_eq!(direct, terminal);
}

#[test]
fn safe_v1_10_restart_rejects_tamper_and_binding_changes_atomically() {
    let api = Api::load_sparse_linear_restart().expect("v1.10 table");
    let matrix = matrix();
    let rhs = right_hand_side();
    let config = config();
    let mut state = api
        .begin_sparse_linear(&matrix, &rhs, None, config)
        .expect("iteration-zero state");
    api.advance_sparse_linear(&matrix, &rhs, config, 1, &mut state)
        .expect("first iteration");

    state.direction.pop();
    let corrupt = state.clone();
    let error = api
        .advance_sparse_linear(&matrix, &rhs, config, 1, &mut state)
        .expect_err("truncated direction must fail");
    assert_eq!(error.code, SA_ERR_CHECKPOINT_MISMATCH);
    assert_eq!(state, corrupt);

    let mut bound = api
        .begin_sparse_linear(&matrix, &rhs, None, config)
        .expect("fresh state");
    let original = bound.clone();
    let changed_config = SparseLinearConfig {
        relative_residual_tolerance: 2.0e-13,
        ..config
    };
    let error = api
        .advance_sparse_linear(&matrix, &rhs, changed_config, 1, &mut bound)
        .expect_err("changed convergence binding must fail");
    assert_eq!(error.code, SA_ERR_CHECKPOINT_MISMATCH);
    assert_eq!(bound, original);
}

#[test]
fn numerical_outcomes_remain_terminal_checkpoint_states() {
    let api = Api::load_sparse_linear_restart().expect("v1.10 table");

    let singular = SparseCsrMatrix {
        row_offsets: vec![0, 1, 2],
        column_indices: vec![0, 1],
        values: vec![0.0, 1.0],
    };
    let singular_state = api
        .begin_sparse_linear(&singular, &[1.0, 1.0], None, config())
        .expect("singularity remains a state");
    assert_eq!(
        singular_state.execution_status,
        SparseLinearExecutionStatus::Terminal
    );
    assert_eq!(
        singular_state.solver_status,
        SparseLinearSolverStatus::Singularity
    );
    assert_eq!(
        singular_state
            .terminal_solution()
            .expect_err("singular terminal taxonomy")
            .code,
        SA_ERR_SINGULARITY
    );

    let matrix = matrix();
    let mut exhausted_config = config();
    exhausted_config.max_iterations = 1;
    let mut exhausted = api
        .begin_sparse_linear(&matrix, &[1.0; 5], None, exhausted_config)
        .expect("bounded state");
    api.advance_sparse_linear(
        &matrix,
        &[1.0; 5],
        exhausted_config,
        u32::MAX,
        &mut exhausted,
    )
    .expect("nonconvergence is a terminal transition");
    assert_eq!(
        exhausted.solver_status,
        SparseLinearSolverStatus::Nonconvergence
    );
    assert_eq!(
        exhausted
            .terminal_solution()
            .expect_err("nonconvergence taxonomy")
            .code,
        SA_ERR_NONCONVERGENCE
    );

    let mut increment_config = config();
    increment_config.maximum_increment = 1.0e-20;
    let mut increment = api
        .begin_sparse_linear(&matrix, &[1.0; 5], None, increment_config)
        .expect("increment-bounded state");
    api.advance_sparse_linear(&matrix, &[1.0; 5], increment_config, 1, &mut increment)
        .expect("increment failure is a terminal transition");
    assert_eq!(
        increment.solver_status,
        SparseLinearSolverStatus::IncrementLimit
    );
    assert_eq!(
        increment
            .terminal_solution()
            .expect_err("increment taxonomy")
            .code,
        SA_ERR_INCREMENT_LIMIT
    );
}

#[test]
fn v1_9_table_cannot_expose_v1_10_restart() {
    let old = Api::load_generalized_eigen().expect("v1.9 table");
    let error = old
        .begin_sparse_linear(&matrix(), &right_hand_side(), None, config())
        .expect_err("v1.9 cannot expose sparse restart");
    assert_eq!(error.code, SA_ERR_UNSUPPORTED);
}
