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
  --listen 127.0.0.1:8787
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
  -> synchronous Rust runtime -> C++ CPU Frame3D
  -> terminal bundle/manifest.json
  -> GET .../{job_id}/view.json
  -> existing Workbench manifest/hash/schema/source/gate replay
~~~

Workbench는 terminal job URL을 받은 뒤에도 결과를 바로 신뢰하지 않는다. 기존
`loadNativeFrameJob`/`loadNativeFrameBundle` 경로가 manifest, ModelIR/ResultIR/ReportIR/HTML의
byte length와 SHA-256, ResultIR/ReportIR canonical hashes, source binding, equilibrium/recovery
gates와 authority를 모두 재검증해야 화면에 표시한다. Failed job은 bundle authority가 없다.

## Open boundary

이 경로는 `loopback_single_process_synchronous.v1` source-tree integration이다. process isolation,
background worker, polling, cancellation, resume, stale-lock/crash recovery, authentication,
multi-user/multi-host, packaged Workbench application, installer, clean-machine receipt, external
solver execution, independent validation, design/commercial/release authority를 제공하지 않는다.
현재 제한된 sandbox에서는 socket bind가 금지되어 pure route submit/run/bundle test와 frontend
production build/test discovery를 수행하며, socket-capable CI의 integration test는 실제 loopback
listener를 사용한다.
