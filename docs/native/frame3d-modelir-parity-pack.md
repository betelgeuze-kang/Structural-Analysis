# Frame3D ModelIR Differential Parity Pack

이 pack은 Frame Alpha의 최근 기능을 `ModelIR v2 -> Rust adapter -> C++ CPU solver ->
ResultIR` 전체 경로에서 Python 수치 기준과 비교한다. 직접 C ABI element test를 대체하지
않고, adapter의 단위 변환, load binding, 조합 평탄화와 ResultIR recovery gate까지 한 번에
확인하는 보완 gate다.

## 고정 case

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

## 권한 경계

PASS는 세 case에 한정된 cross-implementation verification이다. 외부 상용 코드 비교,
실험 validation, CPU/HIP parity, engineering design, commercial use 또는 release readiness를
확립하지 않는다. ResultIR도 기존 `bounded_native_cpu_result_candidate.v1`보다 승격되지
않으며 fallback과 regularization은 모두 0이어야 한다.
