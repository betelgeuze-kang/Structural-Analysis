use std::sync::Arc;
use std::thread;

use structural_ffi::{Api, DenseSymmetricMatrix, GeneralizedEigenConfig};
use structural_ffi_sys::{
    SA_ABI_V1_9, SA_CAPABILITY_GENERALIZED_EIGEN_CPU, SA_ERR_INVALID_ARGUMENT,
    SA_ERR_NONCONVERGENCE, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
};

fn diagonal(values: &[f64]) -> DenseSymmetricMatrix {
    let order = values.len();
    let mut matrix = vec![0.0; order * order];
    for (index, value) in values.iter().enumerate() {
        matrix[index * order + index] = *value;
    }
    DenseSymmetricMatrix {
        order,
        values: matrix,
    }
}

fn near(left: f64, right: f64, tolerance: f64) -> bool {
    (left - right).abs() <= tolerance * left.abs().max(right.abs()).max(1.0)
}

#[test]
fn v1_9_modal_and_buckling_results_cross_the_safe_boundary() {
    let api = Api::load_generalized_eigen().expect("v1.9 table");
    assert_eq!(api.abi_version(), SA_ABI_V1_9);
    assert_ne!(api.capabilities() & SA_CAPABILITY_GENERALIZED_EIGEN_CPU, 0);

    let modal = api
        .solve_modal_modes(
            &diagonal(&[0.0, 4.0, 9.0]),
            &diagonal(&[1.0, 1.0, 1.0]),
            None,
            GeneralizedEigenConfig::modal(2),
        )
        .expect("modal solve");
    assert_eq!(modal.modes.len(), 2);
    assert_eq!(modal.rigid_mode_count, 1);
    assert_eq!(modal.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(modal.fallback_count, 0);
    assert!(near(modal.modes[0].eigenvalue_rad2_per_s2, 4.0, 5.0e-12));
    assert!(near(modal.modes[1].eigenvalue_rad2_per_s2, 9.0, 5.0e-12));
    assert_eq!(modal.modes[0].mass_normalized_shape, [0.0, 1.0, 0.0]);
    assert_eq!(modal.modes[1].mass_normalized_shape, [0.0, 0.0, 1.0]);
    assert!(near(
        modal.modes[0].frequency_hz,
        1.0 / std::f64::consts::PI,
        5.0e-12
    ));

    let buckling = api
        .solve_linear_buckling(
            &diagonal(&[6.0, 8.0, 10.0]),
            &diagonal(&[3.0, 2.0, 0.0]),
            None,
            GeneralizedEigenConfig::buckling(2),
        )
        .expect("buckling solve");
    assert_eq!(buckling.modes.len(), 2);
    assert_eq!(buckling.finite_positive_eigenvalue_count, 2);
    assert_eq!(buckling.geometric_stiffness_positive_rank, 2);
    assert!(near(buckling.critical_load_factor, 2.0, 5.0e-12));
    assert!(near(buckling.modes[0].load_factor, 2.0, 5.0e-12));
    assert!(near(buckling.modes[1].load_factor, 4.0, 5.0e-12));
    assert!(near(
        buckling.modes[0].stiffness_normalized_shape[0],
        1.0 / 6.0_f64.sqrt(),
        5.0e-12
    ));
    assert_eq!(buckling.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(buckling.fallback_count, 0);
}

#[test]
fn safe_wrapper_preserves_stable_failure_taxonomy_and_version_gate() {
    let old = Api::load_sparse_linear().expect("v1.8 table");
    let unsupported = old
        .solve_modal_modes(
            &diagonal(&[1.0]),
            &diagonal(&[1.0]),
            None,
            GeneralizedEigenConfig::modal(1),
        )
        .expect_err("old table must reject modal use");
    assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

    let api = Api::load_generalized_eigen().expect("v1.9 table");
    let cluster_cut = api
        .solve_modal_modes(
            &diagonal(&[4.0, 4.0, 9.0]),
            &diagonal(&[1.0, 1.0, 1.0]),
            None,
            GeneralizedEigenConfig::modal(1),
        )
        .expect_err("cluster cut must fail closed");
    assert_eq!(cluster_cut.code, SA_ERR_INVALID_ARGUMENT);

    let coupled = DenseSymmetricMatrix {
        order: 3,
        values: vec![4.0, 0.3, 0.2, 0.3, 5.0, 0.4, 0.2, 0.4, 7.0],
    };
    let mut config = GeneralizedEigenConfig::modal(2);
    config.maximum_sweeps = 1;
    let nonconvergence = api
        .solve_modal_modes(&coupled, &diagonal(&[1.0, 1.0, 1.0]), None, config)
        .expect_err("one sweep cannot converge");
    assert_eq!(nonconvergence.code, SA_ERR_NONCONVERGENCE);
}

#[test]
fn immutable_inputs_are_concurrent_and_bitwise_deterministic() {
    let api = Api::load_generalized_eigen().expect("v1.9 table");
    let stiffness = Arc::new(DenseSymmetricMatrix {
        order: 3,
        values: vec![6.0, -1.0, 0.0, -1.0, 8.0, -0.5, 0.0, -0.5, 10.0],
    });
    let mass = Arc::new(diagonal(&[2.0, 3.0, 4.0]));
    let baseline = api
        .solve_modal_modes(&stiffness, &mass, None, GeneralizedEigenConfig::modal(2))
        .expect("baseline");
    let baseline_bits: Vec<u64> = baseline
        .modes
        .iter()
        .flat_map(|mode| {
            std::iter::once(mode.eigenvalue_rad2_per_s2.to_bits()).chain(
                mode.mass_normalized_shape
                    .iter()
                    .map(|value| value.to_bits()),
            )
        })
        .collect();
    let workers: Vec<_> = (0..12)
        .map(|_| {
            let stiffness = Arc::clone(&stiffness);
            let mass = Arc::clone(&mass);
            let baseline_bits = baseline_bits.clone();
            thread::spawn(move || {
                let solution = api
                    .solve_modal_modes(&stiffness, &mass, None, GeneralizedEigenConfig::modal(2))
                    .expect("concurrent solve");
                let bits: Vec<u64> = solution
                    .modes
                    .iter()
                    .flat_map(|mode| {
                        std::iter::once(mode.eigenvalue_rad2_per_s2.to_bits()).chain(
                            mode.mass_normalized_shape
                                .iter()
                                .map(|value| value.to_bits()),
                        )
                    })
                    .collect();
                assert_eq!(bits, baseline_bits);
                assert_eq!(solution.fallback_count, 0);
            })
        })
        .collect();
    for worker in workers {
        worker.join().expect("worker");
    }
}
