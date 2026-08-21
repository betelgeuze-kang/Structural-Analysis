use std::fmt::Write as _;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};

use serde_json::{json, Value};

static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let sequence = NEXT_TEMP.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-cli-workstation-{}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir(&path).expect("temporary workstation root");
        Self(path)
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _removed = std::fs::remove_dir_all(&self.0);
    }
}

fn source_fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json")
}

fn start_server(
    root: &TempRoot,
    maximum_requests: u32,
) -> Result<(Child, String, String), (Child, Value)> {
    let workbench = root.0.join("workbench");
    std::fs::create_dir(&workbench).expect("Workbench directory");
    std::fs::write(
        workbench.join("index.html"),
        "<!doctype html><html><body>Frame Alpha Workbench</body></html>",
    )
    .expect("Workbench index");
    let mut child = Command::new(env!("CARGO_BIN_EXE_structural-cli"))
        .args([
            "workstation",
            "serve",
            "--store",
            root.0.join("jobs").to_str().expect("store path"),
            "--workbench",
            workbench.to_str().expect("Workbench path"),
            "--listen",
            "127.0.0.1:0",
            "--max-requests",
            &maximum_requests.to_string(),
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("start workstation server");
    let mut reader = BufReader::new(child.stdout.take().expect("server stdout"));
    let mut line = String::new();
    reader.read_line(&mut line).expect("startup receipt line");
    let receipt: Value = serde_json::from_str(&line).expect("startup receipt JSON");
    if receipt["schema_version"] == "structural-native-frame-alpha-workstation-host-failure.v1" {
        return Err((child, receipt));
    }
    assert_eq!(
        receipt["service_profile"], "loopback_worker_process_concurrent_polling.v1",
        "startup receipt: {receipt}"
    );
    assert_eq!(receipt["capabilities"]["process_isolation"], true);
    assert_eq!(receipt["capabilities"]["privilege_sandbox"], false);
    assert_eq!(receipt["capabilities"]["concurrent_request_handling"], true);
    assert_eq!(receipt["capabilities"]["job_view_polling_during_run"], true);
    assert_eq!(receipt["capabilities"]["max_concurrent_requests"], 16);
    assert_eq!(
        receipt["capabilities"]["running_worker_failure_finalization"],
        true
    );
    assert_eq!(receipt["capabilities"]["cancellation"], false);
    let origin = receipt["origin"].as_str().expect("origin").to_owned();
    let address = origin
        .strip_prefix("http://")
        .expect("HTTP origin")
        .to_owned();
    Ok((child, origin, address))
}

fn request(
    address: &str,
    method: &str,
    path: &str,
    origin: Option<&str>,
    body: &[u8],
) -> (u16, Vec<u8>) {
    let mut stream = TcpStream::connect(address).expect("connect workstation");
    let mut headers =
        format!("{method} {path} HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n");
    if let Some(origin) = origin {
        let _write_result = write!(&mut headers, "Origin: {origin}\r\n");
    }
    if method == "POST" {
        headers.push_str("Content-Type: application/json\r\n");
        let _write_result = write!(&mut headers, "Content-Length: {}\r\n", body.len());
    }
    headers.push_str("\r\n");
    stream
        .write_all(headers.as_bytes())
        .expect("request headers");
    stream.write_all(body).expect("request body");
    stream.flush().expect("flush request");
    let mut response = Vec::new();
    stream.read_to_end(&mut response).expect("read response");
    let split = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .expect("response header delimiter");
    let header = std::str::from_utf8(&response[..split]).expect("response header UTF-8");
    let status = header
        .lines()
        .next()
        .expect("status line")
        .split(' ')
        .nth(1)
        .expect("status code")
        .parse::<u16>()
        .expect("numeric status");
    (status, response[split + 4..].to_vec())
}

#[test]
#[allow(clippy::too_many_lines)]
fn loopback_workstation_serves_submit_run_and_hash_bound_bundle_flow() {
    let root = TempRoot::new();
    let (mut child, origin, address) = match start_server(&root, 10) {
        Ok(value) => value,
        Err((mut child, receipt)) if receipt["issues"][0]["code"] == "workstation_bind_failed" => {
            let status = child.wait().expect("failed server exit");
            assert!(!status.success());
            eprintln!(
                "loopback socket unavailable in this sandbox; pure route tests remain active"
            );
            return;
        }
        Err((_child, receipt)) => panic!("workstation startup failed: {receipt}"),
    };

    let (status, index) = request(&address, "GET", "/", None, &[]);
    assert_eq!(status, 200);
    assert!(String::from_utf8(index)
        .expect("index UTF-8")
        .contains("Frame Alpha Workbench"));

    let (status, capability_bytes) = request(&address, "GET", "/api/v1/capabilities", None, &[]);
    assert_eq!(status, 200);
    let capabilities: Value = serde_json::from_slice(&capability_bytes).expect("capabilities JSON");
    assert_eq!(capabilities["browser_submission"], true);
    assert_eq!(capabilities["crash_recovery"], false);

    let mut model: Value =
        serde_json::from_slice(&std::fs::read(source_fixture()).expect("tracked ModelIR fixture"))
            .expect("fixture JSON");
    model["elements"][0]["formulation"] = json!("linear_timoshenko_frame3d");
    let submission = serde_json::to_vec(&json!({
        "schema_version": "structural-native-linear-frame3d-job-submission.v1",
        "job_id": "job_0123456789abcdef0123456789abcdef",
        "load_source": {"kind": "pattern", "id": "LC_AXIAL"},
        "result_id": "result.workbench.LC_AXIAL",
        "report_id": "report.workbench.LC_AXIAL",
        "model_ir_json": serde_json::to_string(&model).expect("embedded ModelIR"),
        "claim_boundary": "browser_submission_to_bounded_loopback_native_job_not_result_design_or_release_authority"
    }))
    .expect("submission JSON");

    let (status, forbidden) = request(
        &address,
        "POST",
        "/api/v1/frame3d/jobs",
        Some("http://attacker.invalid"),
        &submission,
    );
    assert_eq!(status, 403);
    assert_eq!(
        serde_json::from_slice::<Value>(&forbidden).expect("forbidden JSON")["issues"][0]["code"],
        "workstation_origin_forbidden"
    );

    let (status, queued_bytes) = request(
        &address,
        "POST",
        "/api/v1/frame3d/jobs",
        Some(&origin),
        &submission,
    );
    assert_eq!(status, 201);
    assert_eq!(
        serde_json::from_slice::<Value>(&queued_bytes).expect("queued JSON")["status"],
        "queued"
    );

    let job_path = "/api/v1/frame3d/jobs/job_0123456789abcdef0123456789abcdef";
    let (status, terminal_bytes) = request(
        &address,
        "POST",
        &format!("{job_path}/run"),
        Some(&origin),
        b"{}",
    );
    assert_eq!(status, 200);
    let terminal: Value = serde_json::from_slice(&terminal_bytes).expect("terminal JSON");
    assert_eq!(terminal["status"], "succeeded");
    assert_eq!(terminal["bundle_manifest"]["path"], "bundle/manifest.json");

    let (status, view_bytes) =
        request(&address, "GET", &format!("{job_path}/view.json"), None, &[]);
    assert_eq!(status, 200);
    assert_eq!(
        serde_json::from_slice::<Value>(&view_bytes).expect("view JSON"),
        terminal
    );

    let (status, manifest_bytes) = request(
        &address,
        "GET",
        &format!("{job_path}/bundle/manifest.json"),
        None,
        &[],
    );
    assert_eq!(status, 200);
    let manifest: Value = serde_json::from_slice(&manifest_bytes).expect("manifest JSON");
    assert_eq!(manifest["status"], "complete");

    let (status, result_bytes) = request(
        &address,
        "GET",
        &format!("{job_path}/bundle/result-ir.json"),
        None,
        &[],
    );
    assert_eq!(status, 200);
    let result: Value = serde_json::from_slice(&result_bytes).expect("ResultIR JSON");
    assert_eq!(
        result["authority"]["release_readiness"],
        "not_authoritative"
    );

    let (status, _) = request(&address, "GET", "/../outside", None, &[]);
    assert_eq!(status, 400);

    let (status, conflict) = request(
        &address,
        "POST",
        &format!("{job_path}/run"),
        Some(&origin),
        b"{}",
    );
    assert_eq!(status, 409);
    assert_eq!(
        serde_json::from_slice::<Value>(&conflict).expect("conflict JSON")["issues"][0]["code"],
        "workstation_run_failed"
    );

    let status = child.wait().expect("workstation server exit");
    assert!(status.success());
}
