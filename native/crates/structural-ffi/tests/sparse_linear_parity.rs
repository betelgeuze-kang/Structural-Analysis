use std::sync::Arc;
use std::thread;

use structural_ffi::{Api, SparseCsrMatrix, SparseLinearConfig};
use structural_ffi_sys::{
    SA_ERR_INCREMENT_LIMIT, SA_ERR_INDEFINITE_OPERATOR, SA_ERR_INVALID_ARGUMENT,
    SA_ERR_NONCONVERGENCE, SA_ERR_SINGULARITY, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
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

fn config() -> SparseLinearConfig {
    SparseLinearConfig {
        max_iterations: 100,
        absolute_residual_tolerance: 1.0e-13,
        relative_residual_tolerance: 1.0e-13,
        maximum_increment: 0.0,
    }
}

#[test]
fn safe_v1_8_sparse_solve_publishes_complete_cpu_result() {
    let api = Api::load_sparse_linear().expect("ABI v1.8 sparse table");
    let right_hand_side = [6.0, -12.0, 18.0, -20.0, 14.0];
    let result = api
        .solve_sparse_linear(&matrix(), &right_hand_side, None, config())
        .expect("bounded sparse solve");
    let expected = [1.0, -2.0, 3.0, -4.0, 5.0];
    assert_eq!(result.solution.len(), expected.len());
    for (actual, expected) in result.solution.iter().zip(expected) {
        assert!((actual - expected).abs() <= 2.0e-12);
    }
    assert!((1..=5).contains(&result.iterations));
    assert!(result.initial_residual_inf > 0.0);
    assert!(result.final_residual_inf <= 1.0e-11);
    assert!(result.final_residual_l2 <= 2.0e-11);
    assert!(result.last_increment_inf > 0.0);
    assert_eq!(result.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(result.fallback_count, 0);

    let exact = api
        .solve_sparse_linear(&matrix(), &right_hand_side, Some(&expected), config())
        .expect("exact initial guess");
    assert_eq!(exact.iterations, 0);
    assert_eq!(exact.solution, expected);
}

#[test]
fn old_table_and_malformed_dimensions_are_rejected() {
    let old = Api::load_reference_elements().expect("ABI v1.7 table");
    let unsupported = old
        .solve_sparse_linear(&matrix(), &[1.0; 5], None, config())
        .expect_err("v1.7 cannot expose sparse v1.8");
    assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

    let api = Api::load_sparse_linear().expect("ABI v1.8 table");
    let mut malformed = matrix();
    malformed.column_indices.pop();
    let error = api
        .solve_sparse_linear(&malformed, &[1.0; 5], None, config())
        .expect_err("shape mismatch");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
    let error = api
        .solve_sparse_linear(&matrix(), &[1.0; 4], None, config())
        .expect_err("RHS mismatch");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
}

#[test]
fn numerical_error_taxonomy_crosses_the_safe_wrapper() {
    let api = Api::load_sparse_linear().expect("ABI v1.8 table");
    let singular = SparseCsrMatrix {
        row_offsets: vec![0, 1, 2],
        column_indices: vec![0, 1],
        values: vec![0.0, 1.0],
    };
    let indefinite = SparseCsrMatrix {
        row_offsets: vec![0, 1, 2],
        column_indices: vec![0, 1],
        values: vec![-1.0, 2.0],
    };
    assert_eq!(
        api.solve_sparse_linear(&singular, &[1.0, 1.0], None, config())
            .expect_err("singularity")
            .code,
        SA_ERR_SINGULARITY
    );
    assert_eq!(
        api.solve_sparse_linear(&indefinite, &[1.0, 1.0], None, config())
            .expect_err("indefinite")
            .code,
        SA_ERR_INDEFINITE_OPERATOR
    );
    let mut exhausted = config();
    exhausted.max_iterations = 1;
    assert_eq!(
        api.solve_sparse_linear(&matrix(), &[1.0; 5], None, exhausted)
            .expect_err("nonconvergence")
            .code,
        SA_ERR_NONCONVERGENCE
    );
    let mut limited = config();
    limited.maximum_increment = 1.0e-20;
    assert_eq!(
        api.solve_sparse_linear(&matrix(), &[1.0; 5], None, limited)
            .expect_err("increment limit")
            .code,
        SA_ERR_INCREMENT_LIMIT
    );
}

#[test]
fn immutable_sparse_operation_is_reentrant_and_bitwise_deterministic() {
    let api = Api::load_sparse_linear().expect("ABI v1.8 table");
    let matrix = Arc::new(matrix());
    let right_hand_side = Arc::new([6.0, -12.0, 18.0, -20.0, 14.0]);
    let expected = api
        .solve_sparse_linear(matrix.as_ref(), right_hand_side.as_ref(), None, config())
        .expect("baseline solve");
    let workers: Vec<_> = (0..16)
        .map(|_| {
            let matrix = Arc::clone(&matrix);
            let right_hand_side = Arc::clone(&right_hand_side);
            thread::spawn(move || {
                api.solve_sparse_linear(matrix.as_ref(), right_hand_side.as_ref(), None, config())
                    .expect("concurrent sparse solve")
            })
        })
        .collect();
    for worker in workers {
        assert_eq!(worker.join().expect("thread joins"), expected);
    }
}
