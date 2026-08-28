# Frame3D External Comparison Alpha

PM-1의 `Run -> Compare -> Report` 흐름은 네이티브 결과와 외부 결과의 모델·하중·축·단위
정체성이 먼저 고정되어야 한다. 이 슬라이스는 bounded Frame Alpha `ResultIR`와 strict external
`ReferenceIR`를 component별로 비교해 hash-bound `ComparisonIR` 또는 deterministic HTML을
생성한다.

## Command

~~~bash
structural-cli result compare-frame3d \
  result-ir.json external-reference.json \
  --comparison-id frame-alpha.LC1.sap2000 \
  --output comparison-ir

structural-cli result compare-frame3d \
  result-ir.json external-reference.json \
  --comparison-id frame-alpha.LC1.sap2000 \
  --output html > comparison.html
~~~

`--output` 기본값은 `comparison-ir`이다. 모든 tolerance row가 통과하면 exit `0`, 비교는
정상 수행됐지만 하나 이상 실패하면 ComparisonIR/HTML을 그대로 출력하고 exit `2`를 반환한다.
입력 읽기나 strict contract가 실패하면 비교 artifact를 만들지 않는다.

## External reference contract

입력 schema는
`native/crates/structural-contracts/schemas/external_linear_frame3d_reference_v1.schema.json`이다.

- `model_content_hash`와 load pattern/combination ID가 ResultIR와 정확히 같아야 한다.
- node/member ID는 native result를 누락·추가 없이 정확히 한 번씩 포함해야 한다.
- node displacement/reaction은 global, member end force는 member-local i-then-j 순서다.
- sign convention은 native ResultIR와 호환된다고 명시해야 한다.
- translation은 `m|mm`, rotation은 `rad`, force는 `N|kN`, moment는 `N*m|kN*m`만 허용하며
  ComparisonIR row는 `m|rad|N|N*m`로 정규화한다.
- SAP2000, MIDAS GEN, OpenSees, CalculiX는 `operator_attached_external` origin만 허용한다.
  contract test fixture는 `synthetic_fixture`/`synthetic_contract_fixture`만 허용한다.
- `export_sha256`은 원본 export identity를 보존하지만 현재는 operator declaration이다. 제품이
  원본 파일을 재해석하거나 외부 프로그램 실행을 인증했다는 뜻이 아니다.

MIDAS GEN NX/SAP2000의 operator-attached full-result CSV는
[`commercial-frame3d-full-result-adapter.md`](commercial-frame3d-full-result-adapter.md)의
fail-closed normalization-only adapter로 이 ReferenceIR에 연결할 수 있다. Adapter는 raw
byte/checksum, exact load filter와 result-table coverage를 검증하고 operator-declared axis,
release, rigid-offset, load와 solver-setting transform의 내부 일관성만 확인한다. Vendor model을
parse하지 않으며 commercial solver 실행이나 same-model semantics를 인증하지 않는다. 어떤
caller-provided key/receipt도 V&V credit이나 promotion authority를 만들지 못한다.

## Gate policy

각 row의 scaled difference는 다음과 같다.

~~~text
abs(native - normalized_reference)
-------------------------------------------------------
max(abs(native), abs(normalized_reference), absolute_floor)
~~~

| Quantity | Relative gate | Absolute floor |
| --- | ---: | ---: |
| displacement/rotation | `0.005` | `1e-12 m/rad` |
| reaction force/moment | `0.005` | `1e-6 N/N*m` |
| member-local end force/moment | `0.01` | `1e-6 N/N*m` |

ComparisonIR은 모든 component row, family별 최대 scaled difference와 worst location, failure
count와 전체 verdict를 보존한다. source ResultIR, canonical external reference, comparison
payload는 각각 SHA-256 identity로 결속된다. source transplant, duplicate key, partial mapping,
unit/axis/profile drift, stale hash와 authority promotion은 fail closed한다.

## Authority boundary

이 기능은 strict mapping, unit normalization과 bounded tolerance evaluation을 구현한 C5 CLI
경로다. 실제 SAP2000/MIDAS/OpenSees/CalculiX 실행 receipt는 아직 없고, operator가 선언한
same-model mapping과 export hash를 독립 확인하지 않는다. 따라서 PASS도
`external_validation=not_established`이며 실험 validation, 설계 승인, 상업 사용 또는 release
authority가 아니다. 기존 ReportIR v1의 comparison은 계속 `not_evaluated`이다.

## Workbench read-only consumer

Workbench v2는 verified ResultIR에 같은 origin의 ReferenceIR/ComparisonIR pair를 선택적으로
부착할 수 있다. build-time 설정은 `VITE_NATIVE_FRAME_REFERENCE_URL`과
`VITE_NATIVE_FRAME_COMPARISON_URL`, runtime 설정은 `nativeFrameReferenceUrl`과
`nativeFrameComparisonUrl`이며 두 URL은 반드시 함께 설정한다. Job/bundle/direct ResultIR 중
어느 source에도 pair를 부착할 수 있지만, source ResultIR가 먼저 strict 검증되어야 한다.

브라우저는 duplicate key, exact fields, model/load/entity coverage, axes/sign, units, reference
canonical hash, ResultIR/reference source binding, component rows, family/overall summary와 zeroed-hash
ComparisonIR digest를 다시 계산한다. 이 재생이 모두 일치할 때만 pair 전체를 표시한다. 하나라도
어긋나거나 Web Crypto digest가 없으면 ReferenceIR와 ComparisonIR를 모두 숨기며, 이미 검증된
ResultIR/ReportIR는 별도 authority로 유지한다. PASS/CHECK 표시는 fixed tolerance evaluation일 뿐
actual external execution이나 independent validation receipt가 아니다. 별도 source-tree PDF 도구는
CLI에서 동일 pair를 다시 재생해 presentation에 포함할 수 있지만 Workbench action이나 portable
distribution에 통합되지 않았고 validation authority를 승격하지 않는다.
