use structural_contracts::native_job::{
    create_native_frame3d_job_event_v1, create_native_frame3d_job_request_v1,
    create_native_frame3d_job_view_v1, parse_native_frame3d_job_event_v1,
    parse_native_frame3d_job_request_v1, parse_native_frame3d_job_submission_v1,
    parse_native_frame3d_job_view_v1, NativeFrame3dJobArtifactV1, NativeFrame3dJobEventTypeV1,
    NativeFrame3dJobLoadSourceV1, NativeFrame3dJobStatusV1,
};

const MODEL_IR: &str =
    include_str!("../../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json");

const MODEL_HASH: &str = "sha256:1111111111111111111111111111111111111111111111111111111111111111";
const MANIFEST_HASH: &str =
    "sha256:2222222222222222222222222222222222222222222222222222222222222222";

fn request() -> structural_contracts::native_job::NativeFrame3dJobRequestV1 {
    create_native_frame3d_job_request_v1(
        "job_0123456789abcdef0123456789abcdef",
        1_700_000_000_000,
        MODEL_HASH,
        NativeFrame3dJobLoadSourceV1::Pattern {
            id: "LC1".to_owned(),
        },
        "result.LC1",
        "report.LC1",
    )
    .expect("valid request")
}

#[test]
fn request_is_canonical_self_hashed_and_strictly_replayable() {
    let request = request();
    let canonical = request.canonical_json().expect("canonical request");
    let replay = parse_native_frame3d_job_request_v1(canonical.as_bytes()).expect("strict replay");
    assert_eq!(replay, request);
    assert_eq!(
        replay.service_profile,
        "filesystem_append_only_single_host.v1"
    );
    assert_eq!(replay.request_hash.len(), 71);

    let transplanted = canonical.replace(MODEL_HASH, MANIFEST_HASH);
    let error = parse_native_frame3d_job_request_v1(transplanted.as_bytes())
        .expect_err("stale request hash must fail");
    assert_eq!(error.code, "native_job_request_hash_mismatch");
}

#[test]
fn append_only_events_bind_the_exact_bounded_lifecycle() {
    let request = request();
    let submitted = create_native_frame3d_job_event_v1(
        &request,
        0,
        request.submitted_unix_ms,
        NativeFrame3dJobEventTypeV1::Submitted,
        NativeFrame3dJobStatusV1::Queued,
        None,
        None,
        None,
    )
    .expect("submitted event");
    let started = create_native_frame3d_job_event_v1(
        &request,
        1,
        request.submitted_unix_ms + 1,
        NativeFrame3dJobEventTypeV1::Started,
        NativeFrame3dJobStatusV1::Running,
        Some(submitted.event_hash.clone()),
        None,
        None,
    )
    .expect("started event");
    let completed = create_native_frame3d_job_event_v1(
        &request,
        2,
        request.submitted_unix_ms + 2,
        NativeFrame3dJobEventTypeV1::Completed,
        NativeFrame3dJobStatusV1::Succeeded,
        Some(started.event_hash.clone()),
        Some(MANIFEST_HASH.to_owned()),
        None,
    )
    .expect("completed event");

    for event in [&submitted, &started, &completed] {
        let bytes = event.canonical_json().expect("canonical event");
        assert_eq!(
            parse_native_frame3d_job_event_v1(bytes.as_bytes()).expect("event replay"),
            *event
        );
    }
    assert_eq!(started.previous_event_hash, Some(submitted.event_hash));
    assert_eq!(completed.previous_event_hash, Some(started.event_hash));

    assert!(create_native_frame3d_job_event_v1(
        &request,
        1,
        request.submitted_unix_ms + 1,
        NativeFrame3dJobEventTypeV1::Completed,
        NativeFrame3dJobStatusV1::Succeeded,
        None,
        Some(MANIFEST_HASH.to_owned()),
        None,
    )
    .is_err());
}

#[test]
fn succeeded_view_is_the_only_shape_that_exposes_a_bundle() {
    let request = request();
    let terminal = create_native_frame3d_job_event_v1(
        &request,
        2,
        request.submitted_unix_ms + 2,
        NativeFrame3dJobEventTypeV1::Completed,
        NativeFrame3dJobStatusV1::Succeeded,
        Some(MANIFEST_HASH.to_owned()),
        Some(MANIFEST_HASH.to_owned()),
        None,
    )
    .expect("terminal event shape");
    let view = create_native_frame3d_job_view_v1(
        &request,
        &terminal,
        Some(NativeFrame3dJobArtifactV1 {
            path: "bundle/manifest.json".to_owned(),
            content_hash: MANIFEST_HASH.to_owned(),
            byte_length: 512,
        }),
        None,
    )
    .expect("succeeded view");
    let bytes = view.canonical_json().expect("canonical view");
    let replay = parse_native_frame3d_job_view_v1(bytes.as_bytes()).expect("view replay");
    assert_eq!(replay, view);
    assert!(!replay.capabilities.process_isolation);
    assert!(!replay.capabilities.cancellation);
    assert!(!replay.capabilities.resume);
    assert!(!replay.capabilities.crash_recovery);
    assert!(!replay.capabilities.multi_host);
}

#[test]
fn unknown_fields_and_duplicate_keys_fail_closed() {
    let canonical = request().canonical_json().expect("canonical request");
    let unknown = canonical.replacen('{', "{\"unexpected\":true,", 1);
    assert!(parse_native_frame3d_job_request_v1(unknown.as_bytes()).is_err());
    let duplicate = canonical.replacen(
        '{',
        "{\"schema_version\":\"structural-native-linear-frame3d-job-request.v1\",",
        1,
    );
    assert!(parse_native_frame3d_job_request_v1(duplicate.as_bytes()).is_err());
}

#[test]
fn browser_submission_preserves_strict_embedded_model_ir_validation() {
    let payload = serde_json::json!({
        "schema_version": "structural-native-linear-frame3d-job-submission.v1",
        "job_id": "job_0123456789abcdef0123456789abcdef",
        "load_source": {"kind": "pattern", "id": "LC_AXIAL"},
        "result_id": "result.browser.LC_AXIAL",
        "report_id": "report.browser.LC_AXIAL",
        "model_ir_json": MODEL_IR,
        "claim_boundary": "browser_submission_to_bounded_loopback_native_job_not_result_design_or_release_authority"
    });
    let bytes = serde_json::to_vec(&payload).expect("submission JSON");
    let submission =
        parse_native_frame3d_job_submission_v1(&bytes).expect("valid browser submission");
    assert_eq!(submission.load_source.id(), "LC_AXIAL");
    assert_eq!(submission.model_ir_json, MODEL_IR);

    let duplicate_outer = String::from_utf8(bytes).expect("UTF-8").replacen(
        '{',
        "{\"job_id\":\"job_ffffffffffffffffffffffffffffffff\",",
        1,
    );
    let error = parse_native_frame3d_job_submission_v1(duplicate_outer.as_bytes())
        .expect_err("outer duplicate key must fail");
    assert_eq!(error.code, "native_job_submission_json_invalid");

    let mut embedded_duplicate = payload;
    embedded_duplicate["model_ir_json"] =
        serde_json::Value::String(MODEL_IR.replacen('{', "{\"schema_version\":\"duplicate\",", 1));
    let error = parse_native_frame3d_job_submission_v1(
        &serde_json::to_vec(&embedded_duplicate).expect("duplicate embedded payload"),
    )
    .expect_err("embedded duplicate key must fail");
    assert_eq!(error.code, "native_job_submission_model_invalid");
}
