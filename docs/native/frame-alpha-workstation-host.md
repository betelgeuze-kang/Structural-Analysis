# Frame Alpha Loopback Workstation Host

PM-1의 source-tree Workbench 실행 경로는 `structural-cli`의 bounded job store를 loopback HTTP
composition으로 노출한다. 호스트는 지정한 Workbench 정적 build와 job API를 같은 origin에서
제공하며, 브라우저가 제출한 exact ModelIR text를 Rust strict decoder와 C++ Frame Alpha runtime에
연결한다.

~~~bash
VITE_NATIVE_FRAME_SUBMISSION_URL=/api/v1/frame3d/jobs npm run build
cargo build --manifest-path native/Cargo.toml -p structural-cli --locked
native/target/debug/structural-cli workstation serve \
  --store build/frame-alpha-jobs \
  --workbench dist \
  --listen 127.0.0.1:8787 \
  --worker-timeout-seconds 300
~~~

호스트는 non-loopback bind를 거부한다. 모든 mutation은 bound `Host`, exact same-origin `Origin`,
`application/json`, bounded `Content-Length`를 요구하고 transfer encoding, duplicate header,
oversized body와 static path escape를 차단한다. Submission envelope는
`structural-native-linear-frame3d-job-submission.v1`이며 embedded ModelIR은 object로 재직렬화하지
않고 JSON string 원문으로 전달되어 nested duplicate key도 authoritative ModelIR decoder에서
다시 거부된다.

## Bounded workflow

~~~text
Workbench ModelIR file
  -> POST /api/v1/frame3d/jobs
  -> queued immutable request/event/view
  -> POST /api/v1/frame3d/jobs/{job_id}/run
  -> bounded structural-cli child worker process
  -> Rust runtime -> C++ CPU Frame3D
  -> terminal bundle/manifest.json
  -> GET .../{job_id}/view.json
  -> existing Workbench manifest/hash/schema/source/gate replay
~~~

Workbench는 terminal job URL을 받은 뒤에도 결과를 바로 신뢰하지 않는다. 기존
`loadNativeFrameJob`/`loadNativeFrameBundle` 경로가 manifest, ModelIR/ResultIR/ReportIR/HTML의
byte length와 SHA-256, ResultIR/ReportIR canonical hashes, source binding, equilibrium/recovery
gates와 authority를 모두 재검증해야 화면에 표시한다. Failed job은 bundle authority가 없다.

## Open boundary

이 경로는 `loopback_worker_process_concurrent_polling.v1` source-tree integration이다. 각 run은 현재
`structural-cli` executable의 별도 자식 프로세스에서 실행되고, 1~3600초 bounded timeout을 넘으면
그 worker를 종료한다. 이는 server crash containment를 위한 프로세스 경계이며 privilege/security
sandbox나 CPU/memory resource limit가 아니다. Host는 최대 16개 요청을 동시 처리하여 synchronous
run POST가 진행 중이어도 Workbench가 별도 GET으로 strict job view를 polling할 수 있다.
같은 job에 대한 중복 active worker는 거부하고, server가 정상 종료할 때는 accepted request thread를
join한다. 이는 background queue, user cancellation, resume,
stale-lock/crash recovery, authentication, multi-user/multi-host, packaged Workbench application,
installer, clean-machine receipt, external solver execution, independent validation,
design/commercial/release authority를 제공하지 않는다. Worker가 strict revision-1 Running 상태에
도달한 뒤 timeout 또는 process/status failure가 나면 host는 기존 Started event에 이은 revision-2
Failed event/view를 append-only로 기록하고 bundle authority를 만들지 않는다. Queued, terminal,
corrupt, partial 상태에는 전이를 발명하지 않고 fail closed한다. 이는 failure finalization일 뿐
retry/resume, stale-lock cleanup, durable crash recovery 또는 중단 사유 증명이 아니며 `run.lock`도 유지한다.
Polling read는 event append와 atomic view replace 사이의 짧은 불일치에서만 bounded retry하며,
각 시도는 전체 event/view binding을 strict replay한다. 영속 partial/tampered state를 수용하지 않는다.
기존 `filesystem_append_only_single_host.v1` materialized job view의 `process_isolation=false`는
그 storage contract 자체가 worker provenance를 증명하지 않기 때문에 보수적으로 유지한다. 프로세스
경계 선언은 host startup/capability receipt에만 있으며 결과 authority로 승격되지 않는다.
현재 제한된 sandbox에서는 socket bind가 금지되어 pure route submit/run/bundle test와 frontend
production build/test discovery를 수행하며, socket-capable CI의 integration test는 실제 loopback
listener를 사용한다.
