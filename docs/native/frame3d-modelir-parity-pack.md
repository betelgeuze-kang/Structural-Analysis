# Frame3D ModelIR Differential Parity Pack

이 pack은 Frame Alpha의 최근 기능을 `ModelIR v2 -> Rust adapter -> C++ CPU solver ->
ResultIR` 전체 경로에서 Python 수치 기준과 비교한다. 직접 C ABI element test를 대체하지
않고, adapter의 단위 변환, load binding, 조합 평탄화와 ResultIR recovery gate까지 한 번에
확인하는 보완 gate다.

## v1 고정 case

1. rotated/rolled member, rigid end offsets, nodal load, local uniform load와 self weight
2. 양단 rotational release, local uniform load와 multiple supports
3. nodal/local uniform/self-weight pattern을 포함한 nested linear combination

Python 기준은 tracked Frame3D/Timoshenko source로 강성, release static condensation,
fixed-end load, global assembly, solve, reaction과 local end force를 별도로 계산한다. Receipt는
두 Python source, runner와 실행한 `structural-cli` binary의 SHA-256을 보존한다. 세 ModelIR
identity와 ResultIR source binding도 exact match여야 한다.

~~~bash
cargo build --manifest-path native/Cargo.toml -p structural-cli --locked
python3 scripts/run_native_frame3d_modelir_parity.py \
  --structural-cli native/target/debug/structural-cli \
  --output build/native-frame3d-modelir-parity.json
~~~

출력은 canonical JSON이고 schema는
`src/structural_analysis/schemas/native_frame3d_modelir_parity_pack_v1.schema.json`이다.
CI는 같은 binary로 두 번 실행한 byte identity, schema, case/feature inventory와 authority
non-promotion을 검사한다.

## v2 다부재 확장

`expanded-v2`는 v1 세 사례를 변경하지 않고 다음 네 사례를 추가한다.

1. 두 부재 spatial chain
2. 양 기초가 고정된 planar portal
3. roll과 양단 rigid offset이 있는 spatial corner
4. 두 부재 multiple-support continuous line

Python 기준은 2–16 nodes, 1–32 members, 60 free equations의 현행 native Alpha 범위에서
전역 강성·하중을 독립 조립한다. 변위·반력·member local end force는 배열 순서가 아니라
stable node/member ID로 결합하며 누락과 중복 ID를 실패 처리한다.

~~~bash
python3 scripts/run_native_frame3d_modelir_parity.py \
  --profile expanded-v2 \
  --structural-cli native/target/debug/structural-cli \
  --output build/native-frame3d-modelir-parity-v2.json
python3 scripts/build_native_frame3d_reference_inventory.py \
  --parity-receipt build/native-frame3d-modelir-parity-v2.json \
  --native-cli native/target/debug/structural-cli \
  --output build/native-frame3d-reference-inventory-v2.json
~~~

PM-1 inventory는 선형 Frame Alpha 60개를 `12/8/10/10/8/12` family로 고정한다.
현재 실행 credit은 7/60이고 나머지 53개는 `planned`라서 credit을 얻지 않는다. Alpha 상한
5개도 현재 0/5이며 업계 중형 모델로 표현하지 않는다. Modal/buckling, 상용 코드와 물리
validation은 이 60개 내부 구현 credit으로 대체되지 않는다.

## v3 bounded Alpha 상한 확장

`alpha-upper-v3`는 v1/v2 receipt와 사례를 변경하지 않고, 60-case inventory에 이미 고정된
다음 다부재 사례 5개를 실행한다.

1. 2-bay, 2-story moment frame
2. 동일 규모의 braced frame
3. roll과 rigid offset을 포함한 irregular spatial frame
4. 네 기초를 가진 multiple-support frame
5. rotational release, roll, offset과 혼합 하중을 가진 spatial frame

~~~bash
python3 scripts/run_native_frame3d_modelir_parity.py \
  --profile alpha-upper-v3 \
  --structural-cli native/target/debug/structural-cli \
  --output build/native-frame3d-modelir-parity-v3.json
python3 scripts/build_native_frame3d_reference_inventory.py \
  --parity-receipt build/native-frame3d-modelir-parity-v3.json \
  --native-cli native/target/debug/structural-cli \
  --output build/native-frame3d-reference-inventory-v3.json
~~~

v3 실행 credit은 12/60, Alpha 상한은 5/5다. 이 5개는 현행 Alpha의 node/member/free-equation
한계 안에서 다부재 topology와 기능 조합을 넓히는 사례이며, 공식 Developer Preview의
업계 중형 모델 5개를 충족하거나 대체하지 않는다. 따라서 inventory의 scale claim은
`bounded_alpha_upper_envelope_not_industry_medium_scale`로 고정된다.

## v4 PM-1 core 검증 폭 확장

`pm1-core-v4`는 v3의 12개 실행 receipt를 그대로 포함하고, PM-1 inventory에
이미 고정된 결손 사례 20개를 실행한다.

- Basic response 8개: 축 인장·압축, 순수 비틀림, 강축·약축·2축 휘,
  Y·Z 방향 전단. 모든 사례는 Native↔Python differential에 더해 prismatic
  Timoshenko cantilever 변위와 기초 반력을 폐형식으로 독립 검산한다.
- Metamorphic 8개: node ID 전치, member row 순서, 전역 좌표 회전,
  N-mm-MPa→SI 정규화, 하중 scale, member i/j 반전, 대칭 반사, 동일 입력
  replay. 두 모델을 각각 Python 기준과 비교한 뒤 Native 결과 사이의 불변·
  공변 관계를 직접 검사한다. 단위 사례는 raw N-mm-MPa 값을
  `bounded_native_frame3d_n_mm_mpa_to_model_ir_v2.v1` production adapter에 넣고,
  raw source hash와 normalized ModelIR content·semantic·provenance hash를 receipt에
  결합한다. SI baseline과는 semantic hash가 같고 source provenance는 달라야 한다.
- Negative 4개: 중복 stable ID, unknown field, 순환 combination, singular model.
  기대 exit/code/path/native status, ResultIR 미생성과 2회 실패 payload byte identity를
  모두 요구한다. 중복 stable ID 사례는 원래 `N2`를 보존한 채 세 번째 `N1` row만
  추가하며, native validation preflight가 정확히 `duplicate_id` at `/nodes`를 내고
  `dangling_reference`는 0개임을 별도로 고정한다.

~~~bash
python3 scripts/run_native_frame3d_modelir_parity.py \
  --profile pm1-core-v4 \
  --structural-cli native/target/debug/structural-cli \
  --output build/native-frame3d-modelir-parity-v4.json
python3 scripts/build_native_frame3d_reference_inventory.py \
  --parity-receipt build/native-frame3d-modelir-parity-v4.json \
  --native-cli native/target/debug/structural-cli \
  --output build/native-frame3d-reference-inventory-v4.json
~~~

v4 execution credit은 32/60이다. Family별로 Basic 12/12, orientation 3/8,
member-load/self-weight 1/10, release/offset 3/10, combination 1/8,
negative/metamorphic 12/12이다. Inventory builder는 v4 schema를 먼저 검증한 후
receipt에 기록된 source 파일과 native CLI binary를 현재 regular-file bytes로 다시
해시한다. Symlink 입력과 0 SHA-256 evidence digest는 거부한다. 이어 schema version에
고정된 공식 profile로 parity producer를 같은 CLI에 대해 독립 재실행하고, 제출 receipt와
재생성 receipt의 canonical semantics와 전체 bytes가 모두 같아야 한다. 현재 receipt에는
경로 비결정 필드가 없으므로 비교 제외 필드도 없다. 그 뒤 각 case receipt의 canonical
SHA-256과 verification kind를 결합하므로 요약 카운트·metric·hash 문자열만 바꾸어 credit을
올릴 수 없다. 이 replay는 제공된 binary의 결정적 동작을 검증할 뿐, 그 binary가 현재 Native
source에서 신뢰된 환경으로 build됐다는 provenance나 release authority를 만들지 않는다.

## 권한 경계

v1 PASS는 세 case, v2 PASS는 일곱 case, v3 PASS는 열두 case, v4 PASS는 실행·
스키마에 결합된 서른두 case에 한정된 검증이다. 외부 상용 코드 비교,
실험 validation, CPU/HIP parity, engineering design, commercial use 또는 release readiness를
확립하지 않는다. ResultIR도 기존 `bounded_native_cpu_result_candidate.v1`보다 승격되지
않으며 fallback과 regularization은 모두 0이어야 한다.
