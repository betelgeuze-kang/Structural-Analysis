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
  --output build/native-frame3d-reference-inventory-v3.json
~~~

v3 실행 credit은 12/60, Alpha 상한은 5/5다. 이 5개는 현행 Alpha의 node/member/free-equation
한계 안에서 다부재 topology와 기능 조합을 넓히는 사례이며, 공식 Developer Preview의
업계 중형 모델 5개를 충족하거나 대체하지 않는다. 따라서 inventory의 scale claim은
`bounded_alpha_upper_envelope_not_industry_medium_scale`로 고정된다.

## 권한 경계

v1 PASS는 세 case, v2 PASS는 일곱 case, v3 PASS는 열두 case에 한정된 cross-implementation verification이다. 외부 상용 코드 비교,
실험 validation, CPU/HIP parity, engineering design, commercial use 또는 release readiness를
확립하지 않는다. ResultIR도 기존 `bounded_native_cpu_result_candidate.v1`보다 승격되지
않으며 fallback과 regularization은 모두 0이어야 한다.
