use std::sync::Arc;
use std::thread;

use structural_ffi::{Api, ReferenceElementInput, ReferenceMaterial};
use structural_ffi_sys::{
    SA_ERR_INVALID_ARGUMENT, SA_ERR_UNSUPPORTED, SA_EXECUTION_BACKEND_CPU,
    SA_REFERENCE_ELEMENT_FRAME3D, SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE,
    SA_REFERENCE_ELEMENT_TRUSS3D,
};

fn material() -> ReferenceMaterial {
    ReferenceMaterial {
        youngs_modulus_pa: 200.0,
        poisson_ratio: 0.25,
        density_kg_per_m3: 1000.0,
    }
}

fn truss() -> ReferenceElementInput {
    ReferenceElementInput::Truss3d {
        node_coordinates_m: [0.0, 0.0, 0.0, 2.0, 0.0, 0.0],
        area_m2: 0.01,
        displacement_m: vec![0.0, 0.0, 0.0, 0.002, 0.0, 0.0],
        direction_m: vec![0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
    }
}

#[test]
fn safe_v1_7_reference_profiles_publish_complete_cpu_responses() {
    let api = Api::load_reference_elements().expect("ABI v1.7 reference table");
    let truss = api
        .evaluate_reference_element(material(), &truss())
        .expect("truss response");
    assert_eq!(truss.kind, SA_REFERENCE_ELEMENT_TRUSS3D);
    assert_eq!(truss.dof_count, 6);
    assert_eq!(truss.tangent.len(), 36);
    assert_eq!(truss.consistent_mass.len(), 36);
    assert_eq!(truss.residual, [-0.002, 0.0, 0.0, 0.002, 0.0, 0.0]);
    assert_eq!(truss.jvp, [-1.0, 0.0, 0.0, 1.0, 0.0, 0.0]);
    assert_eq!(truss.recovery, [0.001, 0.2, 0.002]);
    assert_eq!(truss.execution_backend, SA_EXECUTION_BACKEND_CPU);
    assert_eq!(truss.fallback_count, 0);

    let frame = api
        .evaluate_reference_element(
            material(),
            &ReferenceElementInput::Frame3d {
                node_coordinates_m: [0.0, 0.0, 0.0, 2.0, 0.0, 0.0],
                area_m2: 0.01,
                iy_m4: 2.0e-5,
                iz_m4: 3.0e-5,
                torsional_constant_m4: 4.0e-5,
                local_axis_rotation_rad: 0.0,
                displacement: vec![
                    0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.001, 0.002, -0.003, 0.004, -0.005, 0.006,
                ],
                direction: (1_u32..=12).map(f64::from).collect(),
            },
        )
        .expect("frame response");
    assert_eq!(frame.kind, SA_REFERENCE_ELEMENT_FRAME3D);
    assert_eq!(frame.dof_count, 12);
    assert_eq!(frame.tangent.len(), 144);
    assert_eq!(frame.recovery.len(), 12);
    assert!((frame.tangent[0] - 1.0).abs() <= 1.0e-15);
    assert!((frame.tangent[13] - 0.009).abs() <= 1.0e-15);
    assert!((frame.tangent[26] - 0.006).abs() <= 1.0e-15);
    assert!((frame.tangent[39] - 0.0016).abs() <= 1.0e-15);

    let shell = api
        .evaluate_reference_element(
            material(),
            &ReferenceElementInput::Shell3Membrane {
                node_coordinates_m: [0.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                thickness_m: 0.1,
                displacement_m: vec![0.0, 0.0, 0.0, 0.002, 0.0, 0.0, 0.0, 0.001, 0.0],
                direction_m: vec![0.0, 0.0, 1.0, 0.0, 0.0, 2.0, 0.0, 0.0, 3.0],
            },
        )
        .expect("shell response");
    assert_eq!(shell.kind, SA_REFERENCE_ELEMENT_SHELL3_MEMBRANE);
    assert_eq!(shell.dof_count, 9);
    assert_eq!(shell.tangent.len(), 81);
    assert_eq!(
        shell.recovery,
        [
            0.001,
            0.001,
            0.0,
            0.266_666_666_666_666_66,
            0.266_666_666_666_666_66,
            0.0,
        ]
    );
    assert!(shell.jvp.iter().all(|value| *value == 0.0));
}

#[test]
fn old_table_and_invalid_inputs_fail_without_a_fallback() {
    let old = Api::load_model_ir_ndtha_adapter().expect("ABI v1.6 table");
    let unsupported = old
        .evaluate_reference_element(material(), &truss())
        .expect_err("v1.6 cannot expose the v1.7 operation");
    assert_eq!(unsupported.code, SA_ERR_UNSUPPORTED);

    let api = Api::load_reference_elements().expect("ABI v1.7 table");
    let invalid = ReferenceElementInput::Truss3d {
        node_coordinates_m: [0.0; 6],
        area_m2: 0.01,
        displacement_m: vec![0.0; 6],
        direction_m: vec![0.0; 6],
    };
    let error = api
        .evaluate_reference_element(material(), &invalid)
        .expect_err("zero-length element must fail");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
    let wrong_length = ReferenceElementInput::Truss3d {
        node_coordinates_m: [0.0, 0.0, 0.0, 2.0, 0.0, 0.0],
        area_m2: 0.01,
        displacement_m: vec![0.0; 5],
        direction_m: vec![0.0; 6],
    };
    let error = api
        .evaluate_reference_element(material(), &wrong_length)
        .expect_err("wrong caller-owned length must fail");
    assert_eq!(error.code, SA_ERR_INVALID_ARGUMENT);
}

#[test]
fn immutable_reference_operation_is_reentrant_and_deterministic() {
    let api = Api::load_reference_elements().expect("ABI v1.7 table");
    let input = Arc::new(truss());
    let expected = api
        .evaluate_reference_element(material(), input.as_ref())
        .expect("baseline response");
    let handles: Vec<_> = (0..16)
        .map(|_| {
            let input = Arc::clone(&input);
            thread::spawn(move || {
                api.evaluate_reference_element(material(), input.as_ref())
                    .expect("concurrent response")
            })
        })
        .collect();
    for handle in handles {
        assert_eq!(handle.join().expect("thread joins"), expected);
    }
}
