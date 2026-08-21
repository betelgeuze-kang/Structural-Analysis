# Frame Alpha CLI Distribution Candidate

PM-0/PM-1의 첫 설치 경로는 C++ SDK 설치 테스트와 별도로 실제 Rust 제품 진입점인
`structural-cli`를 전달해야 한다. 이 계약은 CPU-only release binary, 분석 가능한 ModelIR
예제, distribution/smoke/external-comparison schema, 사용 경계와 license를 하나의 portable
ZIP으로 묶는다.

## Build contract

~~~bash
cargo build --manifest-path native/Cargo.toml \
  --package structural-cli --release --locked
python3 scripts/build_native_frame_alpha_distribution.py build \
  --structural-cli native/target/release/structural-cli \
  --platform-tag linux-x86_64-gnu \
  --source-commit "$(git rev-parse HEAD)" \
  --source-tree "$(git rev-parse HEAD^{tree})" \
  --output build/frame-alpha-linux.zip
~~~

Builder는 tracked file이 깨끗한 checkout의 commit/tree와 입력 identity가 정확히 일치하지
않으면 실패한다. ZIP entry는 정렬되고 timestamp, mode와 compression profile이 고정된다.
Manifest는 각 payload의 길이와 SHA-256, binary version, platform과 source identity를
보존한다. 기존 output을 덮어쓰지 않는다.

## Extracted smoke contract

~~~bash
python3 scripts/build_native_frame_alpha_distribution.py verify \
  --archive build/frame-alpha-linux.zip \
  --receipt build/frame-alpha-linux.smoke.json
~~~

Verifier는 duplicate/path traversal/symlink-shaped entry, manifest drift와 file hash drift를
거부한 뒤 새 임시 디렉터리에 직접 추출한다. 추출된 binary만 사용하여 version 확인,
ModelIR strict validation과 `analysis_ready`, 선형 Frame3D 실행, manifest-last Workbench bundle
생성을 확인한다.

PR gate는 `linux-x86_64-gnu`와 `windows-x86_64-msvc`를 별도 host에서 build/smoke하고 source
commit이 포함된 artifact 이름으로 ZIP과 receipt를 보존한다. 한 host의 PASS는 Linux/Windows
parity를 뜻하지 않으며, 두 workflow row도 같은-runner 추출 검증일 뿐 clean-machine 설치나
offline dependency 검증은 아니다.

Binary는 strict external ReferenceIR를 받아 ComparisonIR/HTML을 만드는 command를 포함하지만,
package에는 operator-attached reference나 외부 프로그램 실행 receipt를 넣지 않는다. 따라서
distribution smoke는 external comparison을 통과했다고 주장하지 않는다.

## Workstation v2 candidate

같은 builder의 별도 v2 경로는 production Workbench 정적 build를 release CLI와 함께 해시 결속한다.
Workbench는 반드시 same-origin job endpoint가 compile된 상태로 먼저 빌드한다.

~~~bash
VITE_NATIVE_FRAME_SUBMISSION_URL=/api/v1/frame3d/jobs npm run build
python3 scripts/build_native_frame_alpha_distribution.py build-workstation \
  --structural-cli native/target/release/structural-cli \
  --workbench dist \
  --platform-tag linux-x86_64-gnu \
  --source-commit "$(git rev-parse HEAD)" \
  --source-tree "$(git rev-parse HEAD^{tree})" \
  --output build/frame-alpha-workstation-linux.zip
python3 scripts/build_native_frame_alpha_distribution.py verify-workstation \
  --archive build/frame-alpha-workstation-linux.zip \
  --receipt build/frame-alpha-workstation-linux.smoke.json
~~~

v2 verifier는 기존 ModelIR validate/analyze smoke를 반복한 다음 추출된 binary만으로 loopback host를
기동한다. Package에 결속된 index와 그 index가 참조하는 asset 하나를 byte-for-byte 확인하고, v2
host capability route가 child-process isolation, bounded cancellation, no resume/crash recovery 경계를
그대로 노출하는지 확인한다. 이 smoke는 브라우저를 실행하지 않으며, Workbench build는 source tree에
의해 재생성됐다고 자동 증명하지 않는 `hash_bound_operator_supplied_vite_output.v1` 입력이다. Hosted
CI가 exact checkout에서 npm build 직후 package를 생성하는 이유가 이 경계를 보완하기 위해서다.

## Open boundary

CLI candidate와 workstation v2 candidate 모두 installer, code signing, SBOM, auto-update,
clean-machine/crash-free receipt, browser execution receipt, operator-attached external comparison receipt,
PDF, 설계·상업·출시 권한을 제공하지 않는다. v2가 제공하는 것은 hash-bound static Workbench와
같은-runner extracted loopback static/capability smoke이지, 브라우저가 실제 submit/run/result replay를
완료했다는 증거가 아니다.
