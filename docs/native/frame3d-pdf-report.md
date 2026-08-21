# Native Frame3D PDF Report Alpha

이 슬라이스는 저장된 bounded Frame3D `ResultIR`을 사람이 검토할 수 있는 PDF와 canonical
receipt로 투영한다. 수치·보고서 권한은 Python이 만들지 않는다. 지정한 `structural-cli`가
`result report-frame3d`로 `ResultIR`을 strict 재검증하고 source-bound `ReportIR`을 재생한 뒤에만
ReportLab이 표시를 담당한다.

## Persisted result replay

~~~bash
structural-cli result report-frame3d result-ir.json \
  --report-id frame-alpha.LC1.report \
  --output report-ir

structural-cli result report-frame3d result-ir.json \
  --report-id frame-alpha.LC1.report \
  --output html
~~~

기본 출력은 `report-ir`이다. duplicate key, schema/hash/profile drift, source gate 또는 report
identity가 잘못되면 ReportIR/HTML artifact 없이 exit `2`로 닫힌다. 입력 읽기나 직렬화 실패는
exit `1`이다. 이 경로는 ModelIR을 다시 해석·해석실행하지 않고 이미 저장된 ResultIR을 동일한
Rust contract와 report builder로 재생한다.

## PDF and receipt

~~~bash
python3 scripts/render_native_frame3d_pdf.py \
  --structural-cli native/target/release/structural-cli \
  --result-ir result-ir.json \
  --report-id frame-alpha.LC1.pdf-report \
  --out output/pdf/frame-alpha-LC1.pdf
~~~

선택 비교를 붙일 때는 두 인자를 반드시 함께 준다.

~~~bash
python3 scripts/render_native_frame3d_pdf.py \
  --structural-cli native/target/release/structural-cli \
  --result-ir result-ir.json \
  --report-id frame-alpha.LC1.pdf-report \
  --reference-ir external-reference.json \
  --comparison-id frame-alpha.LC1.external \
  --out output/pdf/frame-alpha-LC1-comparison.pdf
~~~

기본 receipt 경로는 `<PDF>.receipt.json`이다. `--receipt-out`으로 별도 경로를 지정할 수 있다.
PDF와 receipt는 어느 한쪽이라도 이미 존재하면 덮어쓰지 않는다. 성공 receipt는 다음을 결속한다.

- renderer profile, exact `structural-cli --version`, ReportLab version
- PDF SHA-256, byte length와 page count
- ResultIR ID/hash/model content hash와 replayed ReportIR ID/hash
- 선택 ComparisonIR/reference ID와 canonical hash, evaluated PASS/CHECK
- 고정된 presentation/validation/design/commercial/release authority 경계

PDF는 ReportLab `invariant=1`, A4, 내장 ASCII font, 고정 metadata와 page compression 설정을
사용한다. 같은 ReportLab runtime과 같은 source artifact에서는 byte-identical PDF를 재생한다.
ReportLab 버전이 달라도 byte identity가 같다는 주장은 하지 않는다. 모든 페이지에 bounded
authority footer가 있고, node/member 결과와 선택 비교 component row가 여러 페이지로 넘어가도
header/footer와 여백을 보존한다.

## Comparison behavior

선택 비교는 PDF 도구가 직접 계산하지 않는다. 지정한 CLI의 strict
`result compare-frame3d`를 다시 실행한다. 모든 tolerance가 통과한 exit `0`과 평가 완료 CHECK인
exit `2`만 ComparisonIR artifact로 받을 수 있다. malformed/transplanted reference나 failure JSON은
PDF를 만들지 않는다. PDF의 PASS는 fixed tolerance evaluation일 뿐이며
`external_validation=not_established`를 바꾸지 않는다.

## Authority boundary

이 기능은 source-tree C0 report tooling이다. 네이티브 바이너리 PDF backend, portable CLI ZIP,
설치 프로그램 또는 Workbench action에 포함되지 않았다. 실제 SAP2000/MIDAS/OpenSees/CalculiX
실행 receipt도 없으므로 독립 validation, 설계 승인, 상업 사용 또는 release authority를
확립하지 않는다.
