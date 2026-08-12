use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use structural_contracts::legacy_runtime::{
    parse_legacy_runtime_case_v3, LegacyRuntimeCaseV3, NonlinearNdthaCaseV3,
};
use structural_ffi::NonlinearNdthaExecutionStatus;
use structural_runtime::{NonlinearNdthaCheckpoint, Runtime};

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);

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

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create() -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-runtime-checkpoint-test-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("create isolated test directory");
        Self(path)
    }
}

impl Drop for TestDirectory {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.0).expect("remove isolated test directory");
    }
}

#[test]
fn canonical_checkpoint_round_trip_and_durable_restart_are_bitwise_exact() {
    let case = case();
    let runtime = Runtime::new().expect("current native runtime");
    let mut direct = runtime
        .begin_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("direct initial state");
    runtime
        .advance_nonlinear_ndtha(&case.config, &case.inputs, u32::MAX, &mut direct)
        .expect("direct completion");

    let mut split = runtime
        .begin_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("split initial state");
    runtime
        .advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut split)
        .expect("first split boundary");
    let checkpoint = runtime
        .checkpoint_nonlinear_ndtha(&case.config, &case.inputs, &split)
        .expect("canonical checkpoint");
    let repeated = runtime
        .checkpoint_nonlinear_ndtha(&case.config, &case.inputs, &split)
        .expect("repeated canonical checkpoint");
    assert_eq!(checkpoint.as_bytes(), repeated.as_bytes());
    assert_eq!(checkpoint.receipt(), repeated.receipt());
    let receipt = checkpoint.receipt();
    assert_eq!(receipt.next_step, 1);
    assert_eq!(receipt.status, NonlinearNdthaExecutionStatus::Active);
    assert_eq!(receipt.artifact_bytes, 587);
    assert_eq!(
        receipt.model_hash,
        "sha256:65ac4cf6fa660cb50f3a86a27c42044a52612bd8c9782c11406cc51fb1bce87b"
    );
    assert_eq!(
        receipt.state_hash,
        "sha256:1d1f589d2a568ed8bffe0e1e510f9d065d508d636ddb272364201ae02720e4f3"
    );
    assert_eq!(
        receipt.execution_hash,
        "sha256:27a1b575a4b54031de2c297a2782c57abb80623166ce7ba224e602451aea12d4"
    );
    assert_eq!(
        receipt.checkpoint_hash,
        "sha256:5b91e2dab5ee3ed977a3d7fca0ea0c1944661c10ab0a3f17ec4a85bfef77aaac"
    );
    for hash in [
        &receipt.model_hash,
        &receipt.state_hash,
        &receipt.execution_hash,
        &receipt.checkpoint_hash,
    ] {
        assert_eq!(hash.len(), 71);
        assert!(hash.starts_with("sha256:"));
    }

    let decoded = NonlinearNdthaCheckpoint::from_bytes(checkpoint.as_bytes())
        .expect("standalone integrity decode");
    assert_eq!(decoded, checkpoint);
    let restored = runtime
        .restore_nonlinear_ndtha(&case.config, &case.inputs, checkpoint.as_bytes())
        .expect("bound restore");
    assert_eq!(restored, split);
    let resumed = runtime
        .resume_nonlinear_ndtha(&case.config, &case.inputs, checkpoint.as_bytes(), u32::MAX)
        .expect("resumed completion");
    assert_eq!(resumed, direct);

    let directory = TestDirectory::create();
    let path = directory.0.join("analysis.ndcp");
    let saved = runtime
        .save_nonlinear_ndtha_checkpoint(&path, &case.config, &case.inputs, &split)
        .expect("durable atomic save");
    assert_eq!(saved, receipt);
    assert_eq!(
        std::fs::read(&path).expect("saved bytes"),
        checkpoint.as_bytes()
    );
    assert_eq!(
        runtime
            .load_nonlinear_ndtha_checkpoint(&path, &case.config, &case.inputs)
            .expect("durable reload"),
        split
    );

    let mut later = split.clone();
    runtime
        .advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut later)
        .expect("later boundary");
    runtime
        .save_nonlinear_ndtha_checkpoint(&path, &case.config, &case.inputs, &later)
        .expect("atomic replacement");
    assert_eq!(
        runtime
            .load_nonlinear_ndtha_checkpoint(&path, &case.config, &case.inputs)
            .expect("replacement reload"),
        later
    );
    assert_eq!(
        std::fs::read_dir(&directory.0)
            .expect("test directory")
            .count(),
        1
    );
}

#[test]
fn corruption_binding_mismatch_and_impossible_state_fail_closed() {
    let case = case();
    let runtime = Runtime::new().expect("current native runtime");
    let mut state = runtime
        .begin_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("initial state");
    runtime
        .advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut state)
        .expect("first boundary");
    let checkpoint = runtime
        .checkpoint_nonlinear_ndtha(&case.config, &case.inputs, &state)
        .expect("checkpoint");

    let mut corrupted = checkpoint.as_bytes().to_vec();
    let final_byte = corrupted.last_mut().expect("nonempty checkpoint");
    *final_byte ^= 0x80;
    let error = NonlinearNdthaCheckpoint::from_bytes(&corrupted)
        .expect_err("state corruption must be detected");
    assert_eq!(error.code, 1301);

    let error = NonlinearNdthaCheckpoint::from_bytes(
        &checkpoint.as_bytes()[..checkpoint.as_bytes().len() - 1],
    )
    .expect_err("truncation must be detected");
    assert_eq!(error.code, 1301);
    let mut trailing = checkpoint.as_bytes().to_vec();
    trailing.push(0);
    let error = NonlinearNdthaCheckpoint::from_bytes(&trailing)
        .expect_err("trailing data must be detected");
    assert_eq!(error.code, 1301);

    let mut wrong_model = case.inputs.clone();
    wrong_model.story_k_n_per_m[0] += 1.0;
    let error = runtime
        .restore_nonlinear_ndtha(&case.config, &wrong_model, checkpoint.as_bytes())
        .expect_err("model hash mismatch");
    assert_eq!(error.code, 1301);

    let mut wrong_execution = case.inputs.clone();
    wrong_execution.ag_g[1] += 1.0e-6;
    let error = runtime
        .restore_nonlinear_ndtha(&case.config, &wrong_execution, checkpoint.as_bytes())
        .expect_err("execution hash mismatch");
    assert_eq!(error.code, 1301);

    let mut impossible = state.clone();
    impossible.response.step_iterations[2] = 1;
    let original = impossible.clone();
    let error = runtime
        .checkpoint_nonlinear_ndtha(&case.config, &case.inputs, &impossible)
        .expect_err("impossible state must not be serialized");
    assert_eq!(error.code, 1301);
    assert_eq!(impossible, original);
}

#[test]
fn every_single_byte_mutation_of_the_frozen_checkpoint_is_rejected() {
    let case = case();
    let runtime = Runtime::new().expect("current native runtime");
    let mut state = runtime
        .begin_nonlinear_ndtha(&case.config, &case.inputs)
        .expect("initial state");
    runtime
        .advance_nonlinear_ndtha(&case.config, &case.inputs, 1, &mut state)
        .expect("first boundary");
    let checkpoint = runtime
        .checkpoint_nonlinear_ndtha(&case.config, &case.inputs, &state)
        .expect("checkpoint");
    for index in 0..checkpoint.as_bytes().len() {
        let mut mutated = checkpoint.as_bytes().to_vec();
        mutated[index] ^= 1;
        let error = NonlinearNdthaCheckpoint::from_bytes(&mutated)
            .expect_err("single-byte mutation must fail");
        assert_eq!(error.code, 1301, "mutation at byte {index}");
    }
}

#[test]
fn collapse_checkpoint_is_terminal_and_reload_idempotent() {
    let case = case();
    let mut collapse = case.config.clone();
    collapse.collapse_drift_threshold_pct = 1.0e-6;
    let runtime = Runtime::new().expect("current native runtime");
    let mut state = runtime
        .begin_nonlinear_ndtha(&collapse, &case.inputs)
        .expect("initial state");
    runtime
        .advance_nonlinear_ndtha(&collapse, &case.inputs, u32::MAX, &mut state)
        .expect("collapse terminal state");
    assert_eq!(state.status, NonlinearNdthaExecutionStatus::Collapsed);
    let checkpoint = runtime
        .checkpoint_nonlinear_ndtha(&collapse, &case.inputs, &state)
        .expect("collapse checkpoint");
    let resumed = runtime
        .resume_nonlinear_ndtha(&collapse, &case.inputs, checkpoint.as_bytes(), u32::MAX)
        .expect("collapsed checkpoint is idempotent");
    assert_eq!(resumed, state);
}
