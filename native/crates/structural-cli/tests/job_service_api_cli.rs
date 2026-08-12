use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Output, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use structural_cli::execute_native_analysis;

static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const CLIENT_TOKEN: &str = "client-role-token-0123456789-abcdef";
const WORKER_TOKEN: &str = "worker-role-token-0123456789-abcdef";

fn repository_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .canonicalize()
        .expect("repository root")
}

struct TestDirectory(PathBuf);

impl TestDirectory {
    fn create() -> Self {
        let sequence = TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "structural-native-job-api-cli-test-{}-{sequence}",
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

struct ServerProcess {
    child: Child,
    address: SocketAddr,
}

impl ServerProcess {
    fn start(
        root: &Path,
        store: &Path,
        client_token_file: &Path,
        worker_token_file: &Path,
        name: &str,
        maximum_requests: Option<u64>,
    ) -> Self {
        let ready = root.join(format!("{name}.ready.json"));
        let mut command = Command::new(env!("CARGO_BIN_EXE_structural-cli"));
        command
            .env_clear()
            .arg("service")
            .arg("serve")
            .arg("--listen")
            .arg("127.0.0.1:0")
            .arg("--store")
            .arg(store)
            .arg("--client-token-file")
            .arg(client_token_file)
            .arg("--worker-token-file")
            .arg(worker_token_file)
            .arg("--ready-file")
            .arg(&ready)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(maximum) = maximum_requests {
            command.arg("--max-requests").arg(maximum.to_string());
        }
        let mut child = command.spawn().expect("spawn native service");
        let deadline = Instant::now() + Duration::from_secs(5);
        while !ready.exists() {
            if let Some(status) = child.try_wait().expect("probe service process") {
                let output = child.wait_with_output().expect("failed service output");
                panic!(
                    "service exited before ready: {status}; stdout={}; stderr={}",
                    String::from_utf8_lossy(&output.stdout),
                    String::from_utf8_lossy(&output.stderr)
                );
            }
            assert!(Instant::now() < deadline, "service ready timeout");
            std::thread::sleep(Duration::from_millis(10));
        }
        let payload: Value =
            serde_json::from_slice(&std::fs::read(&ready).expect("read service ready metadata"))
                .expect("service ready JSON");
        assert_eq!(
            payload["schema_version"],
            "structural-native-job-http-api-ready.v1"
        );
        let address = payload["listen_address"]
            .as_str()
            .expect("service address")
            .parse()
            .expect("socket address");
        Self { child, address }
    }

    fn kill(self) -> Output {
        let mut child = self.child;
        child.kill().expect("terminate service process");
        child.wait_with_output().expect("killed service output")
    }

    fn wait(self) -> Output {
        self.child
            .wait_with_output()
            .expect("drained service output")
    }
}

#[derive(Debug)]
struct HttpResponse {
    status: u16,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

fn http_request(
    address: SocketAddr,
    method: &str,
    path: &str,
    token: Option<&str>,
    extra_headers: &[(&str, &str)],
    body: &[u8],
) -> HttpResponse {
    let mut stream = TcpStream::connect(address).expect("connect to native service");
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .expect("client read timeout");
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .expect("client write timeout");
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: {address}\r\nContent-Length: {}\r\nConnection: close\r\n",
        body.len()
    )
    .expect("request line");
    if let Some(token) = token {
        write!(stream, "Authorization: Bearer {token}\r\n").expect("authorization header");
    }
    for (name, value) in extra_headers {
        write!(stream, "{name}: {value}\r\n").expect("request header");
    }
    stream.write_all(b"\r\n").expect("header delimiter");
    stream.write_all(body).expect("request body");
    stream.flush().expect("request flush");
    let mut bytes = Vec::new();
    stream.read_to_end(&mut bytes).expect("response bytes");
    parse_response(&bytes)
}

fn parse_response(bytes: &[u8]) -> HttpResponse {
    let boundary = bytes
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .expect("HTTP response delimiter");
    let head = std::str::from_utf8(&bytes[..boundary]).expect("ASCII response head");
    let mut lines = head.split("\r\n");
    let status = lines
        .next()
        .and_then(|line| line.split(' ').nth(1))
        .and_then(|value| value.parse().ok())
        .expect("HTTP status");
    let headers = lines
        .map(|line| {
            let (name, value) = line.split_once(':').expect("response header");
            (name.to_ascii_lowercase(), value.trim().to_owned())
        })
        .collect::<BTreeMap<_, _>>();
    let body = bytes[boundary + 4..].to_vec();
    assert_eq!(
        headers["content-length"].parse::<usize>().expect("length"),
        body.len()
    );
    assert_eq!(headers["cache-control"], "no-store");
    assert_eq!(headers["x-content-type-options"], "nosniff");
    assert_eq!(
        headers["x-structural-job-api"],
        "structural-native-job-http-api.v1"
    );
    HttpResponse {
        status,
        headers,
        body,
    }
}

fn json_body(response: &HttpResponse) -> Value {
    serde_json::from_slice(&response.body).expect("JSON response body")
}

fn worker_body(step_budget: u32) -> Vec<u8> {
    serde_json::to_vec(&json!({
        "schema_version": "structural-native-job-worker-command.v1",
        "worker_id": "native-api-worker",
        "lease_millis": 3_600_000,
        "step_budget": step_budget,
    }))
    .expect("worker command")
}

fn create_token_file(path: &Path, token: &str) {
    std::fs::write(path, token.as_bytes()).expect("write test token file");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600))
            .expect("restrict test token file");
    }
}

fn assert_no_token_leak(output: &Output) {
    for token in [CLIENT_TOKEN, WORKER_TOKEN] {
        assert!(!output
            .stdout
            .windows(token.len())
            .any(|row| row == token.as_bytes()));
        assert!(!output
            .stderr
            .windows(token.len())
            .any(|row| row == token.as_bytes()));
    }
}

#[test]
#[allow(clippy::too_many_lines)]
fn clean_environment_http_checkpoint_survives_process_kill_and_restarts_exactly() {
    let temporary = TestDirectory::create();
    let store = temporary.0.join("store");
    let client_token_file = temporary.0.join("client.token");
    let worker_token_file = temporary.0.join("worker.token");
    create_token_file(&client_token_file, CLIENT_TOKEN);
    create_token_file(&worker_token_file, WORKER_TOKEN);
    let request = std::fs::read(
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
    )
    .expect("native request fixture");

    let first = ServerProcess::start(
        &temporary.0,
        &store,
        &client_token_file,
        &worker_token_file,
        "first",
        None,
    );
    let unauthorized = http_request(
        first.address,
        "POST",
        "/v1/jobs",
        None,
        &[
            ("Content-Type", "application/json"),
            ("Idempotency-Key", "service-resume-e2e"),
        ],
        &request,
    );
    assert_eq!(unauthorized.status, 401);
    assert!(unauthorized.headers.contains_key("www-authenticate"));

    let submitted = http_request(
        first.address,
        "POST",
        "/v1/jobs",
        Some(CLIENT_TOKEN),
        &[
            ("Content-Type", "application/json"),
            ("Idempotency-Key", "service-resume-e2e"),
        ],
        &request,
    );
    assert_eq!(submitted.status, 202);
    let submitted_json = json_body(&submitted);
    assert_eq!(submitted_json["job"]["status"], "queued");
    let job_id = submitted_json["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();

    let wrong_role = http_request(
        first.address,
        "POST",
        "/v1/worker/run-once",
        Some(CLIENT_TOKEN),
        &[("Content-Type", "application/json")],
        &worker_body(2),
    );
    assert_eq!(wrong_role.status, 401);
    let checkpointed = http_request(
        first.address,
        "POST",
        "/v1/worker/run-once",
        Some(WORKER_TOKEN),
        &[("Content-Type", "application/json")],
        &worker_body(2),
    );
    assert_eq!(checkpointed.status, 200);
    assert_eq!(json_body(&checkpointed)["job"]["status"], "checkpointed");
    assert_eq!(json_body(&checkpointed)["job"]["progress_completed"], 2);

    let first_output = first.kill();
    assert_no_token_leak(&first_output);

    let second = ServerProcess::start(
        &temporary.0,
        &store,
        &client_token_file,
        &worker_token_file,
        "second",
        Some(7),
    );
    let polled = http_request(
        second.address,
        "GET",
        &format!("/v1/jobs/{job_id}"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    assert_eq!(polled.status, 200);
    assert_eq!(json_body(&polled)["job"]["status"], "checkpointed");

    let completed = http_request(
        second.address,
        "POST",
        "/v1/worker/run-once",
        Some(WORKER_TOKEN),
        &[("Content-Type", "application/json")],
        &worker_body(u32::MAX),
    );
    assert_eq!(completed.status, 200);
    assert_eq!(json_body(&completed)["job"]["status"], "succeeded");
    assert_eq!(json_body(&completed)["job"]["attempt"], 2);

    let result_ir = http_request(
        second.address,
        "GET",
        &format!("/v1/jobs/{job_id}/result-ir"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    let report_ir = http_request(
        second.address,
        "GET",
        &format!("/v1/jobs/{job_id}/report-ir"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    let report_document = http_request(
        second.address,
        "GET",
        &format!("/v1/jobs/{job_id}/report-document"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    let checkpoint = http_request(
        second.address,
        "GET",
        &format!("/v1/jobs/{job_id}/checkpoint"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    for response in [&result_ir, &report_ir, &report_document, &checkpoint] {
        assert_eq!(response.status, 200);
    }
    let terminal_cancel = http_request(
        second.address,
        "POST",
        &format!("/v1/jobs/{job_id}/cancel"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    assert_eq!(terminal_cancel.status, 409);

    let second_output = second.wait();
    assert!(second_output.status.success());
    assert_no_token_leak(&second_output);
    let direct = execute_native_analysis(&request, None, u32::MAX).expect("direct native run");
    assert_eq!(
        result_ir.body,
        direct.result_ir_json().expect("direct ResultIR").as_bytes()
    );
    assert_eq!(
        report_ir.body,
        direct.report_ir_json().expect("direct ReportIR").as_bytes()
    );
    assert_eq!(
        report_document.body,
        direct
            .report_document()
            .expect("direct report document")
            .as_bytes()
    );
    assert_eq!(checkpoint.body, direct.checkpoint_bytes());
}

#[test]
fn queued_cancellation_is_exposed_without_worker_or_secret_disclosure() {
    let temporary = TestDirectory::create();
    let store = temporary.0.join("store");
    let client_token_file = temporary.0.join("client.token");
    let worker_token_file = temporary.0.join("worker.token");
    create_token_file(&client_token_file, CLIENT_TOKEN);
    create_token_file(&worker_token_file, WORKER_TOKEN);
    let request = std::fs::read(
        repository_root().join("native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json"),
    )
    .expect("native request fixture");
    let server = ServerProcess::start(
        &temporary.0,
        &store,
        &client_token_file,
        &worker_token_file,
        "cancel",
        Some(2),
    );
    let submitted = http_request(
        server.address,
        "POST",
        "/v1/jobs",
        Some(CLIENT_TOKEN),
        &[
            ("Content-Type", "application/json"),
            ("Idempotency-Key", "service-cancel-e2e"),
        ],
        &request,
    );
    let job_id = json_body(&submitted)["job"]["job_id"]
        .as_str()
        .expect("job id")
        .to_owned();
    let cancelled = http_request(
        server.address,
        "POST",
        &format!("/v1/jobs/{job_id}/cancel"),
        Some(CLIENT_TOKEN),
        &[],
        &[],
    );
    assert_eq!(cancelled.status, 200);
    assert_eq!(json_body(&cancelled)["job"]["status"], "cancelled");
    let output = server.wait();
    assert!(output.status.success());
    assert_no_token_leak(&output);
}
