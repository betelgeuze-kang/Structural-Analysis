use std::collections::BTreeMap;
use std::fmt;
use std::fs::OpenOptions;
use std::io::{self, Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Deserialize;
use serde_json::{json, Value};
use structural_contracts::model_ir::{canonicalize_model_ir_v2, decode_json_strict};
use structural_contracts::model_linear_job::MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES;
use structural_contracts::product_ir::sha256_identity;
use structural_runtime::{unix_time_millis, DurableJobError, DurableJobStoreV1};

use crate::{execute_next_durable_job, DurableJobCommandError};

pub const NATIVE_JOB_API_PROFILE_V1: &str = "structural-native-job-http-api.v1";
const CLAIM_BOUNDARY: &str = "loopback_single_host_single_tenant_static_role_credentials_not_tls_multitenant_distributed_worker_or_release_authority";
const MAX_HEADER_BYTES: usize = 16 * 1024;
const MAX_REQUEST_BODY_BYTES: usize = MODEL_IR_LINEAR_MAXIMUM_JOB_REQUEST_BYTES;
const MAX_WORKER_BODY_BYTES: usize = 64 * 1024;
const MAX_TOKEN_FILE_BYTES: usize = 512;
const MIN_TOKEN_BYTES: usize = 32;
const MAX_TOKEN_BYTES: usize = 256;
const DEFAULT_IO_TIMEOUT: Duration = Duration::from_secs(5);

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeJobApiError {
    pub code: String,
    pub detail: String,
}

impl fmt::Display for NativeJobApiError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "{}: {}", self.code, self.detail)
    }
}

impl std::error::Error for NativeJobApiError {}

/// Hashed static credentials for the bounded single-tenant API.
///
/// The raw tokens are discarded after construction and are never exposed by `Debug` or an
/// accessor. Client and worker roles must use different token bytes.
#[derive(Clone)]
pub struct NativeJobApiCredentialsV1 {
    client_digest: String,
    worker_digest: String,
}

impl fmt::Debug for NativeJobApiCredentialsV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("NativeJobApiCredentialsV1")
            .field("client_digest", &"[REDACTED]")
            .field("worker_digest", &"[REDACTED]")
            .finish()
    }
}

impl NativeJobApiCredentialsV1 {
    /// Validate and hash two distinct bounded bearer tokens.
    ///
    /// # Errors
    ///
    /// Returns a stable configuration error for weak, malformed, or identical role tokens.
    fn from_tokens(client_token: &[u8], worker_token: &[u8]) -> Result<Self, NativeJobApiError> {
        validate_token(client_token, "client")?;
        validate_token(worker_token, "worker")?;
        let client_digest = token_digest(client_token);
        let worker_digest = token_digest(worker_token);
        if constant_time_equal(client_digest.as_bytes(), worker_digest.as_bytes()) {
            return Err(api_error(
                "job_api_role_tokens_not_distinct",
                "client and worker bearer tokens must be different",
            ));
        }
        Ok(Self {
            client_digest,
            worker_digest,
        })
    }

    fn authorizes(&self, role: ApiRole, authorization: Option<&str>) -> bool {
        let Some(token) = authorization.and_then(|value| value.strip_prefix("Bearer ")) else {
            return false;
        };
        if token.len() < MIN_TOKEN_BYTES
            || token.len() > MAX_TOKEN_BYTES
            || !token.as_bytes().iter().all(u8::is_ascii_graphic)
        {
            return false;
        }
        let supplied = token_digest(token.as_bytes());
        let expected = match role {
            ApiRole::Client => &self.client_digest,
            ApiRole::Worker => &self.worker_digest,
        };
        constant_time_equal(supplied.as_bytes(), expected.as_bytes())
    }
}

/// Load two mode-restricted regular token files without following their final symlinks.
///
/// One optional trailing LF (or CRLF) is removed. The token itself must remain printable ASCII.
///
/// # Errors
///
/// Returns a stable error without including token bytes or filesystem paths.
pub fn load_native_job_api_credentials(
    client_token_file: &Path,
    worker_token_file: &Path,
) -> Result<NativeJobApiCredentialsV1, NativeJobApiError> {
    let client = read_token_file(client_token_file, "client")?;
    let worker = read_token_file(worker_token_file, "worker")?;
    NativeJobApiCredentialsV1::from_tokens(&client, &worker)
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeJobApiServerConfigV1 {
    pub listen_address: SocketAddr,
    pub store_directory: PathBuf,
    pub maximum_requests: Option<u64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NativeJobApiServeReceiptV1 {
    pub listen_address: SocketAddr,
    pub handled_requests: u64,
    pub recovered_jobs_on_start: usize,
}

impl NativeJobApiServeReceiptV1 {
    #[must_use]
    pub fn canonical_json(&self) -> String {
        canonical_json(&json!({
            "schema_version": "structural-native-job-http-api-serve-receipt.v1",
            "listen_address": self.listen_address.to_string(),
            "handled_requests": self.handled_requests,
            "recovered_jobs_on_start": self.recovered_jobs_on_start,
            "service_profile": NATIVE_JOB_API_PROFILE_V1,
            "claim_boundary": CLAIM_BOUNDARY,
        }))
    }
}

pub struct NativeJobApiServerV1 {
    listener: TcpListener,
    api: NativeJobHttpApiV1,
    maximum_requests: Option<u64>,
    recovered_jobs_on_start: usize,
}

impl NativeJobApiServerV1 {
    /// Bind a loopback-only HTTP/1.1 server and reopen/reconcile its durable local store.
    ///
    /// # Errors
    ///
    /// Returns a stable setup error for a non-loopback address, invalid request bound, corrupt
    /// durable store, or socket bind failure.
    pub fn bind(
        config: &NativeJobApiServerConfigV1,
        credentials: NativeJobApiCredentialsV1,
    ) -> Result<Self, NativeJobApiError> {
        if !config.listen_address.ip().is_loopback() {
            return Err(api_error(
                "job_api_non_loopback_bind_rejected",
                "bounded v1 service may bind only to an explicit loopback IP address",
            ));
        }
        if config.maximum_requests == Some(0) {
            return Err(api_error(
                "job_api_request_limit_invalid",
                "maximum request count must be greater than zero",
            ));
        }
        let store = DurableJobStoreV1::open(&config.store_directory)
            .map_err(|_| setup_store_error("job_api_store_open_failed"))?;
        let recovered_jobs_on_start = store
            .recover_expired_leases(
                unix_time_millis().map_err(|_| setup_store_error("job_api_clock_failed"))?,
            )
            .map_err(|_| setup_store_error("job_api_store_recovery_failed"))?;
        let listener = TcpListener::bind(config.listen_address).map_err(|_| {
            api_error(
                "job_api_bind_failed",
                "loopback service socket could not be bound",
            )
        })?;
        Ok(Self {
            listener,
            api: NativeJobHttpApiV1 { store, credentials },
            maximum_requests: config.maximum_requests,
            recovered_jobs_on_start,
        })
    }

    /// Return the actual bound address, including an operating-system-selected port.
    ///
    /// # Errors
    ///
    /// Returns a stable socket error if the bound address cannot be queried.
    pub fn local_address(&self) -> Result<SocketAddr, NativeJobApiError> {
        self.listener.local_addr().map_err(|_| {
            api_error(
                "job_api_local_address_failed",
                "bound loopback address could not be queried",
            )
        })
    }

    /// Return deterministic startup metadata without credential or filesystem disclosure.
    ///
    /// # Errors
    ///
    /// Returns a stable socket error if the bound address cannot be queried.
    pub fn ready_json(&self) -> Result<String, NativeJobApiError> {
        Ok(canonical_json(&json!({
            "schema_version": "structural-native-job-http-api-ready.v1",
            "listen_address": self.local_address()?.to_string(),
            "service_profile": NATIVE_JOB_API_PROFILE_V1,
            "recovered_jobs_on_start": self.recovered_jobs_on_start,
            "claim_boundary": CLAIM_BOUNDARY,
        })))
    }

    /// Publish startup metadata to a caller-selected create-new regular file.
    ///
    /// # Errors
    ///
    /// Returns a stable error if the destination already exists or cannot be durably written.
    pub fn publish_ready_file(&self, path: &Path) -> Result<(), NativeJobApiError> {
        let bytes = self.ready_json()?;
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(path)
            .map_err(|_| {
                api_error(
                    "job_api_ready_file_create_failed",
                    "ready file must be a new writable regular file",
                )
            })?;
        file.write_all(bytes.as_bytes()).map_err(|_| {
            api_error(
                "job_api_ready_file_write_failed",
                "ready metadata could not be written",
            )
        })?;
        file.sync_all().map_err(|_| {
            api_error(
                "job_api_ready_file_sync_failed",
                "ready metadata could not be synchronized",
            )
        })
    }

    /// Serve one request per connection until the optional drain bound is reached.
    ///
    /// # Errors
    ///
    /// Returns a stable error if accepting a connection fails. Malformed or disconnected clients
    /// are isolated to their individual connection and cannot stop the server.
    pub fn serve(self) -> Result<NativeJobApiServeReceiptV1, NativeJobApiError> {
        let listen_address = self.local_address()?;
        let mut handled_requests = 0_u64;
        loop {
            if self
                .maximum_requests
                .is_some_and(|maximum| handled_requests >= maximum)
            {
                break;
            }
            let (mut stream, _) = self.listener.accept().map_err(|_| {
                api_error(
                    "job_api_accept_failed",
                    "loopback client connection could not be accepted",
                )
            })?;
            let response =
                match configure_stream(&stream).and_then(|()| read_http_request(&mut stream)) {
                    Ok(request) => self.api.handle(&request),
                    Err(error) => wire_error_response(&error),
                };
            let _write_result = write_http_response(&mut stream, &response);
            handled_requests = handled_requests.checked_add(1).ok_or_else(|| {
                api_error(
                    "job_api_request_count_overflow",
                    "handled request counter overflowed",
                )
            })?;
        }
        Ok(NativeJobApiServeReceiptV1 {
            listen_address,
            handled_requests,
            recovered_jobs_on_start: self.recovered_jobs_on_start,
        })
    }
}

struct NativeJobHttpApiV1 {
    store: DurableJobStoreV1,
    credentials: NativeJobApiCredentialsV1,
}

impl NativeJobHttpApiV1 {
    fn handle(&self, request: &HttpRequest) -> HttpResponse {
        if request.path == "/v1/health" {
            return if request.method == "GET" && request.body.is_empty() {
                json_response(
                    200,
                    &json!({
                        "schema_version": "structural-native-job-http-api-health.v1",
                        "status": "ready",
                        "service_profile": NATIVE_JOB_API_PROFILE_V1,
                        "claim_boundary": CLAIM_BOUNDARY,
                    }),
                )
            } else {
                method_or_body_rejected(request, "GET")
            };
        }
        if request.path == "/v1/worker/run-once" {
            return self.handle_worker(request);
        }
        let segments = path_segments(&request.path);
        if segments.as_slice() == ["v1", "model-linear-jobs"] {
            if !self.authorize(ApiRole::Client, request) {
                return unauthorized_response();
            }
            return self.handle_model_ir_linear_submit(request);
        }
        if segments.as_slice() == ["v1", "model-buckling-jobs"] {
            if !self.authorize(ApiRole::Client, request) {
                return unauthorized_response();
            }
            return self.handle_model_ir_buckling_submit(request);
        }
        if segments.first() != Some(&"v1") || segments.get(1) != Some(&"jobs") {
            return error_response(
                404,
                "job_api_route_not_found",
                "/path",
                "route does not exist",
            );
        }
        if !self.authorize(ApiRole::Client, request) {
            return unauthorized_response();
        }
        match segments.as_slice() {
            ["v1", "jobs"] => self.handle_submit(request),
            ["v1", "jobs", job_id] => self.handle_poll(request, job_id),
            ["v1", "jobs", job_id, "cancel"] => self.handle_cancel(request, job_id),
            ["v1", "jobs", job_id, artifact] => self.handle_artifact(request, job_id, artifact),
            ["v1", "jobs", job_id, "artifacts", artifact] => {
                self.handle_named_artifact(request, job_id, artifact)
            }
            _ => error_response(
                404,
                "job_api_route_not_found",
                "/path",
                "route does not exist",
            ),
        }
    }

    fn handle_submit(&self, request: &HttpRequest) -> HttpResponse {
        if request.method != "POST" {
            return method_not_allowed("POST");
        }
        if !has_json_content_type(&request.headers) {
            return error_response(
                415,
                "job_api_content_type_invalid",
                "/headers/content-type",
                "POST /v1/jobs requires application/json",
            );
        }
        if request.body.is_empty() || request.body.len() > MAX_REQUEST_BODY_BYTES {
            return body_size_response();
        }
        let Some(idempotency_key) = request.headers.get("idempotency-key") else {
            return error_response(
                400,
                "job_api_idempotency_key_missing",
                "/headers/idempotency-key",
                "Idempotency-Key is required",
            );
        };
        match unix_time_millis()
            .map_err(DurableJobCommandError::Store)
            .and_then(|now| {
                self.store
                    .submit(idempotency_key, &request.body, now)
                    .map_err(DurableJobCommandError::Store)
            }) {
            Ok(view) => job_response(202, "submitted", &view),
            Err(error) => command_error_response(&error),
        }
    }

    fn handle_model_ir_linear_submit(&self, request: &HttpRequest) -> HttpResponse {
        if request.method != "POST" {
            return method_not_allowed("POST");
        }
        if !has_json_content_type(&request.headers) {
            return error_response(
                415,
                "job_api_content_type_invalid",
                "/headers/content-type",
                "POST /v1/model-linear-jobs requires application/json",
            );
        }
        if request.body.is_empty() || request.body.len() > MAX_REQUEST_BODY_BYTES {
            return body_size_response();
        }
        let Some(idempotency_key) = request.headers.get("idempotency-key") else {
            return error_response(
                400,
                "job_api_idempotency_key_missing",
                "/headers/idempotency-key",
                "Idempotency-Key is required",
            );
        };
        match unix_time_millis()
            .map_err(DurableJobCommandError::Store)
            .and_then(|now| {
                self.store
                    .submit_model_ir_linear_envelope(idempotency_key, &request.body, now)
                    .map_err(DurableJobCommandError::Store)
            }) {
            Ok(view) => job_response(202, "submitted", &view),
            Err(error) => command_error_response(&error),
        }
    }

    fn handle_model_ir_buckling_submit(&self, request: &HttpRequest) -> HttpResponse {
        if request.method != "POST" {
            return method_not_allowed("POST");
        }
        if !has_json_content_type(&request.headers) {
            return error_response(
                415,
                "job_api_content_type_invalid",
                "/headers/content-type",
                "POST /v1/model-buckling-jobs requires application/json",
            );
        }
        if request.body.is_empty() || request.body.len() > MAX_REQUEST_BODY_BYTES {
            return body_size_response();
        }
        let Some(idempotency_key) = request.headers.get("idempotency-key") else {
            return error_response(
                400,
                "job_api_idempotency_key_missing",
                "/headers/idempotency-key",
                "Idempotency-Key is required",
            );
        };
        match unix_time_millis()
            .map_err(DurableJobCommandError::Store)
            .and_then(|now| {
                self.store
                    .submit_model_ir_linear_buckling_envelope(idempotency_key, &request.body, now)
                    .map_err(DurableJobCommandError::Store)
            }) {
            Ok(view) => job_response(202, "submitted", &view),
            Err(error) => command_error_response(&error),
        }
    }

    fn handle_poll(&self, request: &HttpRequest, job_id: &str) -> HttpResponse {
        if request.method != "GET" {
            return method_not_allowed("GET");
        }
        if !request.body.is_empty() {
            return unexpected_body_response();
        }
        match self.store.poll(job_id) {
            Ok(view) => job_response(200, "found", &view),
            Err(error) => store_error_response(&error),
        }
    }

    fn handle_cancel(&self, request: &HttpRequest, job_id: &str) -> HttpResponse {
        if request.method != "POST" {
            return method_not_allowed("POST");
        }
        if !request.body.is_empty() {
            return unexpected_body_response();
        }
        match unix_time_millis()
            .map_err(DurableJobCommandError::Store)
            .and_then(|now| {
                self.store
                    .request_cancel(job_id, now)
                    .map_err(DurableJobCommandError::Store)
            }) {
            Ok(view) => job_response(200, "cancel_requested", &view),
            Err(error) => command_error_response(&error),
        }
    }

    fn handle_artifact(&self, request: &HttpRequest, job_id: &str, artifact: &str) -> HttpResponse {
        if request.method != "GET" {
            return method_not_allowed("GET");
        }
        if !request.body.is_empty() {
            return unexpected_body_response();
        }
        let result = match artifact {
            "checkpoint" => self.store.poll(job_id).and_then(|view| {
                self.store.read_checkpoint(job_id).map(|bytes| {
                    let media_type = match view.analysis_profile {
                        structural_runtime::DurableJobAnalysisProfileV1::NonlinearNdthaCpuV1 => {
                            "application/vnd.structural.ndtha-checkpoint"
                        }
                        structural_runtime::DurableJobAnalysisProfileV1::ModelIrLinearCpuV1 => {
                            "application/vnd.structural.model-ir-linear-checkpoint"
                        }
                        structural_runtime::DurableJobAnalysisProfileV1::ModelIrLinearBucklingCpuV1 => {
                            "application/vnd.structural.model-ir-linear-buckling-checkpoint"
                        }
                    };
                    artifact_response(media_type, bytes)
                })
            }),
            "result-ir" => self
                .store
                .read_result_ir(job_id)
                .map(|bytes| artifact_response("application/json", bytes)),
            "report-ir" => self
                .store
                .read_report_ir(job_id)
                .map(|bytes| artifact_response("application/json", bytes)),
            "report-document" => self
                .store
                .read_report_document(job_id)
                .map(|bytes| artifact_response("text/markdown; charset=utf-8", bytes)),
            "result-recovery-ir" => self
                .store
                .read_result_recovery_ir(job_id)
                .map(|bytes| artifact_response("application/json", bytes)),
            "reaction-result-ir" => self
                .store
                .read_reaction_result_ir(job_id)
                .map(|bytes| artifact_response("application/json", bytes)),
            _ => {
                return error_response(
                    404,
                    "job_api_route_not_found",
                    "/path",
                    "artifact route does not exist",
                );
            }
        };
        result.unwrap_or_else(|error| store_error_response(&error))
    }

    fn handle_named_artifact(
        &self,
        request: &HttpRequest,
        job_id: &str,
        artifact: &str,
    ) -> HttpResponse {
        if request.method != "GET" {
            return method_not_allowed("GET");
        }
        if !request.body.is_empty() {
            return unexpected_body_response();
        }
        let Some(media_type) = buckling_artifact_media_type(artifact) else {
            return error_response(
                404,
                "job_api_route_not_found",
                "/path",
                "named artifact route does not exist",
            );
        };
        self.store
            .read_product_artifact(job_id, artifact)
            .map_or_else(
                |error| store_error_response(&error),
                |bytes| artifact_response(media_type, bytes),
            )
    }

    fn handle_worker(&self, request: &HttpRequest) -> HttpResponse {
        if !self.authorize(ApiRole::Worker, request) {
            return unauthorized_response();
        }
        if request.method != "POST" {
            return method_not_allowed("POST");
        }
        if !has_json_content_type(&request.headers) {
            return error_response(
                415,
                "job_api_content_type_invalid",
                "/headers/content-type",
                "worker command requires application/json",
            );
        }
        if request.body.is_empty() || request.body.len() > MAX_WORKER_BODY_BYTES {
            return body_size_response();
        }
        let command = match parse_worker_command(&request.body) {
            Ok(command) => command,
            Err(response) => return response,
        };
        match execute_next_durable_job(
            &self.store,
            &command.worker_id,
            command.lease_millis,
            command.step_budget,
        ) {
            Ok(Some(view)) => job_response(200, "advanced", &view),
            Ok(None) => json_response(
                200,
                &json!({
                    "schema_version": "structural-native-job-http-api-response.v1",
                    "status": "idle",
                    "service_profile": NATIVE_JOB_API_PROFILE_V1,
                    "claim_boundary": CLAIM_BOUNDARY,
                }),
            ),
            Err(error) => command_error_response(&error),
        }
    }

    fn authorize(&self, role: ApiRole, request: &HttpRequest) -> bool {
        self.credentials.authorizes(
            role,
            request.headers.get("authorization").map(String::as_str),
        )
    }
}

#[derive(Clone, Copy)]
enum ApiRole {
    Client,
    Worker,
}

#[derive(Debug)]
struct HttpRequest {
    method: String,
    path: String,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

#[derive(Debug)]
struct HttpResponse {
    status: u16,
    content_type: &'static str,
    body: Vec<u8>,
    allow: Option<&'static str>,
    authenticate: bool,
}

#[derive(Debug)]
struct HttpWireError {
    status: u16,
    code: &'static str,
    detail: &'static str,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct WorkerRunOnceCommandV1 {
    schema_version: String,
    worker_id: String,
    lease_millis: u64,
    step_budget: u32,
}

fn parse_worker_command(bytes: &[u8]) -> Result<WorkerRunOnceCommandV1, HttpResponse> {
    let value = decode_json_strict(bytes).map_err(|_| {
        error_response(
            400,
            "job_api_json_invalid",
            "/body",
            "request body must be strict JSON without duplicate keys",
        )
    })?;
    let command: WorkerRunOnceCommandV1 = serde_json::from_value(value).map_err(|_| {
        error_response(
            400,
            "job_api_worker_command_invalid",
            "/body",
            "worker command fields do not satisfy the v1 contract",
        )
    })?;
    if command.schema_version != "structural-native-job-worker-command.v1"
        || command.step_budget == 0
    {
        return Err(error_response(
            400,
            "job_api_worker_command_invalid",
            "/body",
            "worker command identity or numeric bounds are invalid",
        ));
    }
    Ok(command)
}

fn configure_stream(stream: &TcpStream) -> Result<(), HttpWireError> {
    stream
        .set_read_timeout(Some(DEFAULT_IO_TIMEOUT))
        .and_then(|()| stream.set_write_timeout(Some(DEFAULT_IO_TIMEOUT)))
        .map_err(|_| HttpWireError {
            status: 500,
            code: "job_api_socket_configuration_failed",
            detail: "connection timeouts could not be configured",
        })
}

#[allow(clippy::too_many_lines)]
fn read_http_request(stream: &mut TcpStream) -> Result<HttpRequest, HttpWireError> {
    let mut bytes = Vec::with_capacity(4096);
    let header_end = loop {
        if let Some(position) = bytes.windows(4).position(|window| window == b"\r\n\r\n") {
            let end = position + 4;
            if end > MAX_HEADER_BYTES {
                return Err(header_too_large());
            }
            break end;
        }
        if bytes.len() >= MAX_HEADER_BYTES {
            return Err(header_too_large());
        }
        let mut chunk = [0_u8; 4096];
        let count = stream
            .read(&mut chunk)
            .map_err(|error| read_wire_error(&error))?;
        if count == 0 {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_request_incomplete",
                detail: "request headers ended before the HTTP delimiter",
            });
        }
        bytes.extend_from_slice(&chunk[..count]);
    };

    let header_bytes = bytes.get(..header_end - 4).ok_or(HttpWireError {
        status: 400,
        code: "job_api_request_invalid",
        detail: "request header boundary is invalid",
    })?;
    if !header_bytes.is_ascii() {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_header_invalid",
            detail: "bounded HTTP headers must be ASCII",
        });
    }
    let header_text = std::str::from_utf8(header_bytes)
        .map_err(|_| HttpWireError {
            status: 400,
            code: "job_api_header_invalid",
            detail: "bounded HTTP headers must be valid ASCII",
        })?
        .to_owned();
    let mut lines = header_text.split("\r\n");
    let request_line = lines.next().ok_or(HttpWireError {
        status: 400,
        code: "job_api_request_line_invalid",
        detail: "HTTP request line is missing",
    })?;
    let parts = request_line.split(' ').collect::<Vec<_>>();
    if parts.len() != 3 || parts[2] != "HTTP/1.1" {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_request_line_invalid",
            detail: "bounded service requires an HTTP/1.1 request line",
        });
    }
    let method = parts[0];
    if !matches!(method, "GET" | "POST") {
        return Err(HttpWireError {
            status: 405,
            code: "job_api_method_not_allowed",
            detail: "bounded service supports GET and POST only",
        });
    }
    validate_wire_path(parts[1])?;
    let mut headers = BTreeMap::new();
    for line in lines {
        let (name, value) = line.split_once(':').ok_or(HttpWireError {
            status: 400,
            code: "job_api_header_invalid",
            detail: "HTTP header is missing its colon delimiter",
        })?;
        if name.is_empty()
            || !name
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
        {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_header_invalid",
                detail: "HTTP header name is outside the bounded token grammar",
            });
        }
        let value = value.trim_matches(|character| matches!(character, ' ' | '\t'));
        if value
            .bytes()
            .any(|byte| byte.is_ascii_control() && byte != b'\t')
        {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_header_invalid",
                detail: "HTTP header value contains a control character",
            });
        }
        let normalized = name.to_ascii_lowercase();
        if headers.insert(normalized, value.to_owned()).is_some() {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_duplicate_header",
                detail: "duplicate HTTP headers are rejected",
            });
        }
    }
    if !headers.get("host").is_some_and(|value| !value.is_empty()) {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_host_missing",
            detail: "HTTP/1.1 Host header is required",
        });
    }
    if headers.contains_key("transfer-encoding") {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_transfer_encoding_rejected",
            detail: "Transfer-Encoding is not supported by the bounded service",
        });
    }
    if headers.contains_key("expect") {
        return Err(HttpWireError {
            status: 417,
            code: "job_api_expectation_rejected",
            detail: "Expect negotiation is not supported",
        });
    }
    let content_length = headers.get("content-length").map_or(Ok(0_usize), |value| {
        if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_content_length_invalid",
                detail: "Content-Length must be one bounded decimal integer",
            });
        }
        value.parse::<usize>().map_err(|_| HttpWireError {
            status: 400,
            code: "job_api_content_length_invalid",
            detail: "Content-Length must be one bounded decimal integer",
        })
    })?;
    if content_length > MAX_REQUEST_BODY_BYTES {
        return Err(HttpWireError {
            status: 413,
            code: "job_api_body_too_large",
            detail: "request body exceeds the bounded service limit",
        });
    }
    let expected_length = header_end
        .checked_add(content_length)
        .ok_or(HttpWireError {
            status: 413,
            code: "job_api_body_too_large",
            detail: "request length exceeds the bounded service limit",
        })?;
    while bytes.len() < expected_length {
        let remaining = expected_length - bytes.len();
        let mut chunk = [0_u8; 4096];
        let read_length = remaining.min(chunk.len());
        let count = stream
            .read(&mut chunk[..read_length])
            .map_err(|error| read_wire_error(&error))?;
        if count == 0 {
            return Err(HttpWireError {
                status: 400,
                code: "job_api_body_incomplete",
                detail: "request body ended before Content-Length bytes arrived",
            });
        }
        bytes.extend_from_slice(&chunk[..count]);
    }
    if bytes.len() != expected_length {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_pipelining_rejected",
            detail: "one connection may contain exactly one request",
        });
    }
    Ok(HttpRequest {
        method: method.to_owned(),
        path: parts[1].to_owned(),
        headers,
        body: bytes[header_end..].to_vec(),
    })
}

fn read_wire_error(error: &io::Error) -> HttpWireError {
    if matches!(
        error.kind(),
        io::ErrorKind::TimedOut | io::ErrorKind::WouldBlock
    ) {
        HttpWireError {
            status: 408,
            code: "job_api_request_timeout",
            detail: "request did not arrive within the bounded read timeout",
        }
    } else {
        HttpWireError {
            status: 400,
            code: "job_api_request_read_failed",
            detail: "request bytes could not be read",
        }
    }
}

fn header_too_large() -> HttpWireError {
    HttpWireError {
        status: 431,
        code: "job_api_headers_too_large",
        detail: "request headers exceed the bounded service limit",
    }
}

fn validate_wire_path(path: &str) -> Result<(), HttpWireError> {
    if path.is_empty()
        || path.len() > 2048
        || !path.starts_with('/')
        || path.contains("//")
        || (path.len() > 1 && path.ends_with('/'))
        || path.split('/').any(|segment| matches!(segment, "." | ".."))
        || path.bytes().any(|byte| {
            !(byte.is_ascii_alphanumeric() || matches!(byte, b'/' | b'-' | b'.' | b'_'))
        })
    {
        return Err(HttpWireError {
            status: 400,
            code: "job_api_path_invalid",
            detail: "request target is outside the exact ASCII path grammar",
        });
    }
    Ok(())
}

fn write_http_response(stream: &mut TcpStream, response: &HttpResponse) -> io::Result<()> {
    let reason = status_reason(response.status);
    write!(
        stream,
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nX-Structural-Job-Api: {}\r\nConnection: close\r\n",
        response.status,
        reason,
        response.content_type,
        response.body.len(),
        NATIVE_JOB_API_PROFILE_V1,
    )?;
    if let Some(allow) = response.allow {
        write!(stream, "Allow: {allow}\r\n")?;
    }
    if response.authenticate {
        write!(
            stream,
            "WWW-Authenticate: Bearer realm=\"structural-native-job-api\"\r\n"
        )?;
    }
    stream.write_all(b"\r\n")?;
    stream.write_all(&response.body)?;
    stream.flush()
}

fn status_reason(status: u16) -> &'static str {
    match status {
        200 => "OK",
        202 => "Accepted",
        400 => "Bad Request",
        401 => "Unauthorized",
        403 => "Forbidden",
        404 => "Not Found",
        405 => "Method Not Allowed",
        408 => "Request Timeout",
        409 => "Conflict",
        413 => "Content Too Large",
        415 => "Unsupported Media Type",
        417 => "Expectation Failed",
        422 => "Unprocessable Content",
        431 => "Request Header Fields Too Large",
        _ => "Internal Server Error",
    }
}

fn job_response(
    status: u16,
    disposition: &str,
    view: &structural_runtime::DurableJobViewV1,
) -> HttpResponse {
    json_response(
        status,
        &json!({
            "schema_version": "structural-native-job-http-api-response.v1",
            "status": disposition,
            "job": view,
            "service_profile": NATIVE_JOB_API_PROFILE_V1,
            "claim_boundary": CLAIM_BOUNDARY,
        }),
    )
}

fn artifact_response(content_type: &'static str, body: Vec<u8>) -> HttpResponse {
    HttpResponse {
        status: 200,
        content_type,
        body,
        allow: None,
        authenticate: false,
    }
}

fn buckling_artifact_media_type(name: &str) -> Option<&'static str> {
    match name {
        "checkpoint.eigcp" => Some("application/vnd.structural.dense-spectral-checkpoint"),
        "checkpoint.mbcp" => Some("application/vnd.structural.model-ir-linear-buckling-checkpoint"),
        "reference-checkpoint.mlpcp" => {
            Some("application/vnd.structural.model-ir-linear-checkpoint")
        }
        "reference-checkpoint.pcgcp" => Some("application/vnd.structural.sparse-linear-checkpoint"),
        "report.md" => Some("text/markdown; charset=utf-8"),
        "buckling-assembly-receipt.json"
        | "dense-run-receipt.json"
        | "generated-dense-request.json"
        | "generated-reference-request.json"
        | "model-buckling-request.json"
        | "model-ir.json"
        | "reference-assembly-receipt.json"
        | "reference-reaction-ir.json"
        | "reference-recovery-ir.json"
        | "reference-result-ir.json"
        | "report-ir.json"
        | "result-ir.json"
        | "run-receipt.json" => Some("application/json"),
        _ => None,
    }
}

fn json_response(status: u16, value: &Value) -> HttpResponse {
    HttpResponse {
        status,
        content_type: "application/json",
        body: canonical_json(value).into_bytes(),
        allow: None,
        authenticate: false,
    }
}

fn canonical_json(value: &Value) -> String {
    canonicalize_model_ir_v2(value).unwrap_or_else(|_| {
        "{\"error\":{\"code\":\"job_api_response_encoding_failed\"},\"schema_version\":\"structural-native-job-http-api-error.v1\"}".to_owned()
    })
}

fn error_response(status: u16, code: &str, path: &str, detail: &str) -> HttpResponse {
    json_response(
        status,
        &json!({
            "schema_version": "structural-native-job-http-api-error.v1",
            "error": {
                "code": code,
                "path": path,
                "detail": detail,
            },
            "service_profile": NATIVE_JOB_API_PROFILE_V1,
            "claim_boundary": CLAIM_BOUNDARY,
        }),
    )
}

fn wire_error_response(error: &HttpWireError) -> HttpResponse {
    let mut response = error_response(error.status, error.code, "/http", error.detail);
    response.allow = (error.status == 405).then_some("GET, POST");
    response
}

fn unauthorized_response() -> HttpResponse {
    let mut response = error_response(
        401,
        "job_api_unauthorized",
        "/headers/authorization",
        "valid bearer authorization is required for this role",
    );
    response.authenticate = true;
    response
}

fn method_not_allowed(allow: &'static str) -> HttpResponse {
    let mut response = error_response(
        405,
        "job_api_method_not_allowed",
        "/method",
        "method is not allowed for this route",
    );
    response.allow = Some(allow);
    response
}

fn method_or_body_rejected(request: &HttpRequest, allow: &'static str) -> HttpResponse {
    if request.method == allow {
        unexpected_body_response()
    } else {
        method_not_allowed(allow)
    }
}

fn unexpected_body_response() -> HttpResponse {
    error_response(
        400,
        "job_api_unexpected_body",
        "/body",
        "this route requires an empty request body",
    )
}

fn body_size_response() -> HttpResponse {
    error_response(
        413,
        "job_api_body_size_invalid",
        "/body",
        "request body is empty or exceeds its route limit",
    )
}

fn command_error_response(error: &DurableJobCommandError) -> HttpResponse {
    match error {
        DurableJobCommandError::Store(error) => store_error_response(error),
        DurableJobCommandError::Product(error) => error_response(
            if error.is_contract_error() { 422 } else { 500 },
            "job_api_native_execution_failed",
            "/worker",
            "native worker execution failed within its bounded authority",
        ),
        DurableJobCommandError::ModelLinearProduct(error) => error_response(
            if error.is_contract_error() { 422 } else { 500 },
            "job_api_model_ir_linear_execution_failed",
            "/worker",
            "typed ModelIR linear worker execution failed within its bounded authority",
        ),
        DurableJobCommandError::ModelBucklingProduct(error) => error_response(
            if error.is_contract_error() { 422 } else { 500 },
            "job_api_model_ir_buckling_execution_failed",
            "/worker",
            "typed ModelIR buckling worker execution failed within its bounded authority",
        ),
        DurableJobCommandError::Invariant { code, .. } => error_response(
            400,
            code,
            "/worker",
            "worker command violates the bounded durable-job contract",
        ),
    }
}

fn store_error_response(error: &DurableJobError) -> HttpResponse {
    let status = match error.code.as_str() {
        "job_not_found" => 404,
        "job_idempotency_conflict"
        | "job_terminal_state_conflict"
        | "job_artifact_not_published"
        | "job_cancel_pending" => 409,
        "job_lease_unauthorized" => 403,
        code if code.ends_with("_invalid") => 400,
        _ => 500,
    };
    let detail = match status {
        400 => "durable job input violates the bounded contract",
        403 => "worker is not authorized for this lease",
        404 => "durable job does not exist",
        409 => "durable job state conflicts with the requested operation",
        _ => "durable job storage or integrity validation failed",
    };
    error_response(status, &error.code, &error.path, detail)
}

fn has_json_content_type(headers: &BTreeMap<String, String>) -> bool {
    headers
        .get("content-type")
        .is_some_and(|value| value.eq_ignore_ascii_case("application/json"))
}

fn path_segments(path: &str) -> Vec<&str> {
    path.strip_prefix('/')
        .map_or_else(Vec::new, |value| value.split('/').collect())
}

fn read_token_file(path: &Path, role: &str) -> Result<Vec<u8>, NativeJobApiError> {
    let metadata = std::fs::symlink_metadata(path).map_err(|_| {
        api_error(
            "job_api_token_file_metadata_failed",
            &format!("{role} token file metadata could not be read"),
        )
    })?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(api_error(
            "job_api_token_file_type_invalid",
            &format!("{role} token must be a regular non-symlink file"),
        ));
    }
    if metadata.len() > u64::try_from(MAX_TOKEN_FILE_BYTES).unwrap_or(u64::MAX) {
        return Err(api_error(
            "job_api_token_file_size_invalid",
            &format!("{role} token file exceeds its bounded size"),
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        if metadata.permissions().mode() & 0o077 != 0 {
            return Err(api_error(
                "job_api_token_file_permissions_invalid",
                &format!("{role} token file must not grant group or other permissions"),
            ));
        }
    }
    let mut options = OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW);
    }
    let file = options.open(path).map_err(|_| {
        api_error(
            "job_api_token_file_open_failed",
            &format!("{role} token file could not be opened safely"),
        )
    })?;
    let opened = file.metadata().map_err(|_| {
        api_error(
            "job_api_token_file_metadata_failed",
            &format!("opened {role} token file metadata could not be read"),
        )
    })?;
    if !opened.is_file() || opened.len() != metadata.len() {
        return Err(api_error(
            "job_api_token_file_changed",
            &format!("{role} token file changed while opening"),
        ));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        if opened.dev() != metadata.dev()
            || opened.ino() != metadata.ino()
            || opened.mode() & 0o077 != 0
        {
            return Err(api_error(
                "job_api_token_file_changed",
                &format!("{role} token file identity or permissions changed while opening"),
            ));
        }
    }
    let mut bytes = Vec::new();
    file.take(u64::try_from(MAX_TOKEN_FILE_BYTES + 1).unwrap_or(u64::MAX))
        .read_to_end(&mut bytes)
        .map_err(|_| {
            api_error(
                "job_api_token_file_read_failed",
                &format!("{role} token file could not be read"),
            )
        })?;
    if bytes.len() > MAX_TOKEN_FILE_BYTES {
        return Err(api_error(
            "job_api_token_file_size_invalid",
            &format!("{role} token file exceeds its bounded size"),
        ));
    }
    if bytes.last() == Some(&b'\n') {
        bytes.pop();
        if bytes.last() == Some(&b'\r') {
            bytes.pop();
        }
    }
    validate_token(&bytes, role)?;
    Ok(bytes)
}

fn validate_token(token: &[u8], role: &str) -> Result<(), NativeJobApiError> {
    if token.len() < MIN_TOKEN_BYTES
        || token.len() > MAX_TOKEN_BYTES
        || !token.iter().all(u8::is_ascii_graphic)
    {
        return Err(api_error(
            "job_api_token_invalid",
            &format!("{role} token must be 32-256 printable ASCII bytes"),
        ));
    }
    Ok(())
}

fn token_digest(token: &[u8]) -> String {
    let mut material = Vec::with_capacity(35 + token.len());
    material.extend_from_slice(b"structural-native-job-api-token.v1\0");
    material.extend_from_slice(token);
    sha256_identity(&material)
}

fn constant_time_equal(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    left.iter()
        .zip(right)
        .fold(0_u8, |difference, (left, right)| {
            difference | (left ^ right)
        })
        == 0
}

fn api_error(code: &str, detail: &str) -> NativeJobApiError {
    NativeJobApiError {
        code: code.to_owned(),
        detail: detail.to_owned(),
    }
}

fn setup_store_error(code: &str) -> NativeJobApiError {
    api_error(
        code,
        "durable job store could not be opened or reconciled without disclosing filesystem details",
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;
    use std::io::Write as _;
    use std::net::{TcpListener, TcpStream};
    use std::path::Path;
    use std::thread;
    use std::time::{SystemTime, UNIX_EPOCH};

    use structural_contracts::model_buckling_job::build_model_ir_linear_buckling_durable_job_request_v1;
    use structural_contracts::model_buckling_product::{
        build_model_ir_linear_buckling_analysis_request_v1, ModelIrLinearBucklingAnalysisRequestV1,
        ModelIrLinearBucklingBackendV1, MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1,
    };
    use structural_contracts::model_ir::parse_model_ir_v2;
    use structural_contracts::model_linear_job::build_model_ir_linear_durable_job_request_v1;
    use structural_contracts::product_ir::ModelIrIdentityV1;
    use structural_contracts::sparse_product::SparseLinearConfigV1;
    use structural_contracts::spectral_product::SpectralGeneralizedEigenConfigV1;
    use structural_runtime::DurableJobStoreV1;

    use super::{
        constant_time_equal, read_http_request, validate_wire_path, HttpRequest,
        NativeJobApiCredentialsV1, NativeJobApiServerConfigV1, NativeJobApiServerV1,
        NativeJobHttpApiV1, MAX_REQUEST_BODY_BYTES,
    };

    #[test]
    fn credentials_are_role_separated_and_debug_redacted() {
        let client = b"client-token-0123456789-abcdefghijkl";
        let worker = b"worker-token-0123456789-abcdefghijkl";
        let credentials = NativeJobApiCredentialsV1::from_tokens(client, worker)
            .expect("valid distinct role credentials");
        let debug = format!("{credentials:?}");
        assert!(debug.contains("[REDACTED]"));
        assert!(!debug.contains("client-token"));
        assert!(NativeJobApiCredentialsV1::from_tokens(client, client).is_err());
        assert!(constant_time_equal(b"same", b"same"));
        assert!(!constant_time_equal(b"same", b"diff"));
    }

    #[test]
    fn path_grammar_rejects_queries_encoding_and_ambiguity() {
        assert!(validate_wire_path("/v1/jobs/job-abc").is_ok());
        for path in [
            "/v1/jobs?x=1",
            "/v1/%6aobs",
            "/v1//jobs",
            "/v1/../jobs",
            "/v1/jobs/",
            "v1/jobs",
            "/v1/jobs\\x",
        ] {
            assert!(validate_wire_path(path).is_err(), "accepted {path}");
        }
    }

    #[test]
    fn non_loopback_bind_fails_before_store_or_socket_access() {
        let credentials = NativeJobApiCredentialsV1::from_tokens(
            b"client-token-0123456789-abcdefghijkl",
            b"worker-token-0123456789-abcdefghijkl",
        )
        .expect("test credentials");
        let config = NativeJobApiServerConfigV1 {
            listen_address: "0.0.0.0:8080".parse().expect("socket address"),
            store_directory: "must-not-be-opened".into(),
            maximum_requests: None,
        };
        let error = NativeJobApiServerV1::bind(&config, credentials)
            .err()
            .expect("non-loopback bind rejection");
        assert_eq!(error.code, "job_api_non_loopback_bind_rejected");
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn model_ir_linear_submit_worker_and_reaction_routes_are_socket_free_and_profile_bound() {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "structural-model-linear-http-{}-{nanos}",
            std::process::id()
        ));
        let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()
            .expect("repository root");
        let model = std::fs::read(
            repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("model fixture");
        let request = std::fs::read(
            repository
                .join("native/tests/fixtures/model_ir_linear/frame_cantilever_weak_request.json"),
        )
        .expect("request fixture");
        let envelope = build_model_ir_linear_durable_job_request_v1(&model, &request)
            .expect("durable envelope");
        let client_token = "client-token-0123456789-abcdefghijkl";
        let worker_token = "worker-token-0123456789-abcdefghijkl";
        let api = NativeJobHttpApiV1 {
            store: DurableJobStoreV1::open(&root).expect("job store"),
            credentials: NativeJobApiCredentialsV1::from_tokens(
                client_token.as_bytes(),
                worker_token.as_bytes(),
            )
            .expect("credentials"),
        };
        let submitted = api.handle(&HttpRequest {
            method: "POST".to_owned(),
            path: "/v1/model-linear-jobs".to_owned(),
            headers: BTreeMap::from([
                ("authorization".to_owned(), format!("Bearer {client_token}")),
                ("content-type".to_owned(), "application/json".to_owned()),
                ("idempotency-key".to_owned(), "http-model-linear".to_owned()),
            ]),
            body: envelope.canonical_bytes().to_vec(),
        });
        assert_eq!(submitted.status, 202);
        let submitted_json: serde_json::Value =
            serde_json::from_slice(&submitted.body).expect("submit response");
        assert_eq!(
            submitted_json["job"]["analysis_profile"],
            "model_ir_linear_cpu_v1"
        );
        let job_id = submitted_json["job"]["job_id"]
            .as_str()
            .expect("job id")
            .to_owned();

        for (worker_id, step_budget, expected_status) in [
            ("http-worker-first", 1_u32, "checkpointed"),
            ("http-worker-resume", u32::MAX, "succeeded"),
        ] {
            let advanced = api.handle(&HttpRequest {
                method: "POST".to_owned(),
                path: "/v1/worker/run-once".to_owned(),
                headers: BTreeMap::from([
                    ("authorization".to_owned(), format!("Bearer {worker_token}")),
                    ("content-type".to_owned(), "application/json".to_owned()),
                ]),
                body: serde_json::to_vec(&serde_json::json!({
                    "schema_version": "structural-native-job-worker-command.v1",
                    "worker_id": worker_id,
                    "lease_millis": 10_000,
                    "step_budget": step_budget,
                }))
                .expect("worker command"),
            });
            assert_eq!(advanced.status, 200);
            let value: serde_json::Value =
                serde_json::from_slice(&advanced.body).expect("worker response");
            assert_eq!(value["job"]["status"], expected_status);
        }

        let recovery = api.handle(&HttpRequest {
            method: "GET".to_owned(),
            path: format!("/v1/jobs/{job_id}/result-recovery-ir"),
            headers: BTreeMap::from([(
                "authorization".to_owned(),
                format!("Bearer {client_token}"),
            )]),
            body: Vec::new(),
        });
        assert_eq!(recovery.status, 200);
        assert_eq!(recovery.content_type, "application/json");
        let value: serde_json::Value =
            serde_json::from_slice(&recovery.body).expect("recovery JSON");
        assert_eq!(
            value["schema_version"],
            "structural-model-ir-linear-result-recovery-ir.v1"
        );
        let reaction = api.handle(&HttpRequest {
            method: "GET".to_owned(),
            path: format!("/v1/jobs/{job_id}/reaction-result-ir"),
            headers: BTreeMap::from([(
                "authorization".to_owned(),
                format!("Bearer {client_token}"),
            )]),
            body: Vec::new(),
        });
        assert_eq!(reaction.status, 200);
        assert_eq!(reaction.content_type, "application/json");
        let value: serde_json::Value =
            serde_json::from_slice(&reaction.body).expect("reaction JSON");
        assert_eq!(
            value["schema_version"],
            "structural-model-ir-linear-reaction-result-ir.v1"
        );
        assert_eq!(value["backend_receipt"]["fallback_count"], 0);
        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    #[allow(clippy::too_many_lines)]
    fn model_ir_buckling_submit_worker_and_named_artifact_routes_are_profile_bound() {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock")
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "structural-model-buckling-http-{}-{nanos}",
            std::process::id()
        ));
        let repository = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()
            .expect("repository root");
        let source = std::fs::read(
            repository.join("tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json"),
        )
        .expect("model fixture");
        let source = parse_model_ir_v2(&source).expect("source model");
        let mut model_value = source.value().clone();
        model_value["load_patterns"][0]["nodal_loads"][0]["components_si"]["FX"] =
            serde_json::json!(-100_000.0);
        let model =
            parse_model_ir_v2(&serde_json::to_vec(&model_value).expect("compression model JSON"))
                .expect("compression model");
        let request = build_model_ir_linear_buckling_analysis_request_v1(
            ModelIrLinearBucklingAnalysisRequestV1 {
                schema_version: MODEL_IR_LINEAR_BUCKLING_ANALYSIS_REQUEST_V1.to_owned(),
                operation: "solve_model_ir_linear_buckling".to_owned(),
                case_id: "http-buckling".to_owned(),
                backend: ModelIrLinearBucklingBackendV1::Cpu,
                model_identity: ModelIrIdentityV1 {
                    content_hash: model.content_hash().to_owned(),
                    semantic_hash: model.semantic_hash().to_owned(),
                    provenance_hash: model.provenance_hash().to_owned(),
                },
                reference_load_pattern_id: "LC_AXIAL".to_owned(),
                reference_linear_config: SparseLinearConfigV1 {
                    max_iterations: 64,
                    absolute_residual_tolerance: 1e-12,
                    relative_residual_tolerance: 1e-12,
                    maximum_increment: 0.0,
                },
                buckling_config: SpectralGeneralizedEigenConfigV1 {
                    mode_count: 2,
                    maximum_sweeps: 4_096,
                    symmetry_relative_tolerance: 1e-12,
                    positive_semidefinite_relative_tolerance: 1e-12,
                    mode_relative_tolerance: 1e-10,
                    cluster_relative_tolerance: 1e-9,
                    residual_relative_tolerance: 1e-9,
                    orthogonality_tolerance: 1e-9,
                    eigensolver_relative_tolerance: 1e-12,
                },
            },
        )
        .expect("buckling request");
        let envelope = build_model_ir_linear_buckling_durable_job_request_v1(
            model.canonical_bytes(),
            request.canonical_bytes(),
        )
        .expect("durable envelope");
        let client_token = "client-token-0123456789-abcdefghijkl";
        let worker_token = "worker-token-0123456789-abcdefghijkl";
        let api = NativeJobHttpApiV1 {
            store: DurableJobStoreV1::open(&root).expect("job store"),
            credentials: NativeJobApiCredentialsV1::from_tokens(
                client_token.as_bytes(),
                worker_token.as_bytes(),
            )
            .expect("credentials"),
        };
        let submitted = api.handle(&HttpRequest {
            method: "POST".to_owned(),
            path: "/v1/model-buckling-jobs".to_owned(),
            headers: BTreeMap::from([
                ("authorization".to_owned(), format!("Bearer {client_token}")),
                ("content-type".to_owned(), "application/json".to_owned()),
                (
                    "idempotency-key".to_owned(),
                    "http-model-buckling".to_owned(),
                ),
            ]),
            body: envelope.canonical_bytes().to_vec(),
        });
        assert_eq!(submitted.status, 202);
        let submitted_json: serde_json::Value =
            serde_json::from_slice(&submitted.body).expect("submit response");
        assert_eq!(
            submitted_json["job"]["analysis_profile"],
            "model_ir_linear_buckling_cpu_v1"
        );
        let job_id = submitted_json["job"]["job_id"]
            .as_str()
            .expect("job id")
            .to_owned();
        let advanced = api.handle(&HttpRequest {
            method: "POST".to_owned(),
            path: "/v1/worker/run-once".to_owned(),
            headers: BTreeMap::from([
                ("authorization".to_owned(), format!("Bearer {worker_token}")),
                ("content-type".to_owned(), "application/json".to_owned()),
            ]),
            body: serde_json::to_vec(&serde_json::json!({
                "schema_version": "structural-native-job-worker-command.v1",
                "worker_id": "http-buckling-worker",
                "lease_millis": 10_000,
                "step_budget": 1,
            }))
            .expect("worker command"),
        });
        assert_eq!(advanced.status, 200);
        let advanced_json: serde_json::Value =
            serde_json::from_slice(&advanced.body).expect("worker response");
        assert_eq!(advanced_json["job"]["status"], "succeeded");
        assert_eq!(
            advanced_json["job"]["product_artifacts"]
                .as_array()
                .expect("inventory")
                .len(),
            18
        );
        let result = api.handle(&HttpRequest {
            method: "GET".to_owned(),
            path: format!("/v1/jobs/{job_id}/artifacts/result-ir.json"),
            headers: BTreeMap::from([(
                "authorization".to_owned(),
                format!("Bearer {client_token}"),
            )]),
            body: Vec::new(),
        });
        assert_eq!(result.status, 200);
        assert_eq!(result.content_type, "application/json");
        let value: serde_json::Value = serde_json::from_slice(&result.body).expect("result JSON");
        assert_eq!(value["analysis_kind"], "linear_buckling");
        std::fs::remove_dir_all(root).expect("cleanup");
    }

    #[test]
    fn wire_parser_rejects_duplicate_headers_and_oversized_lengths() {
        let duplicate = b"GET /v1/health HTTP/1.1\r\nHost: localhost\r\nHost: duplicate\r\n\r\n";
        let error = parse_over_loopback(duplicate).expect_err("duplicate header");
        assert_eq!(error.code, "job_api_duplicate_header");

        let oversized = format!(
            "POST /v1/jobs HTTP/1.1\r\nHost: localhost\r\nContent-Length: {}\r\n\r\n",
            MAX_REQUEST_BODY_BYTES + 1
        );
        let error = parse_over_loopback(oversized.as_bytes()).expect_err("oversized body");
        assert_eq!(error.status, 413);
    }

    fn parse_over_loopback(bytes: &[u8]) -> Result<super::HttpRequest, super::HttpWireError> {
        let listener = TcpListener::bind("127.0.0.1:0").expect("test listener");
        let address = listener.local_addr().expect("test address");
        let payload = bytes.to_vec();
        let writer = thread::spawn(move || {
            let mut stream = TcpStream::connect(address).expect("test client");
            stream.write_all(&payload).expect("test request");
        });
        let (mut stream, _) = listener.accept().expect("test accept");
        let result = read_http_request(&mut stream);
        writer.join().expect("test writer");
        result
    }
}
