# 외부 code-to-code 기술 실행 영수증

이 문서는 OpenSees와 CalculiX를 실제 로컬 실행한 좁은 기술 비교를 설명한다. 이
실행은 검증 계층 Level 2 후보를 준비하지만, Level 2 증거로 등록하거나 제품의
법무·재배포·상용 동등성·출시 준비를 승인하지 않는다.

## 실행 범위

`external_code_to_code_technical_execution_receipt.json`은 정확히 세 case를
기록한다.

| Case | 외부 기준 | 제품 경로 | 비교 항목 | 결과 |
|---|---|---|---|---|
| 2자유도 shear modal | OpenSees 3.7.1 | deterministic generalized-eigen modal kernel | 고유값 2개 | PASS |
| cantilever tip load | OpenSees 3.7.1 | authoritative linear-static frame 경로 | tip 변위, base 전단반력, base 모멘트 | PASS |
| axial member tip load | CalculiX CrunchiX 2.17 | authoritative linear-static frame 경로 | tip 변위, base 축반력 | PASS |

총 7개 수치 비교가 통과했다. Modal 고유값과 axial 결과의 절대오차는 `0`이고,
cantilever 반력 두 항목의 최대 절대오차는
`3.552713678800501e-15`이다. 비교 허용오차는
`1e-10 + 1e-10 * max(abs(product), abs(reference), 1)`이며 제품 경로의
fallback과 regularization은 모두 `false`다.

## 런타임과 결속

- OpenSeesPy distribution `3.7.1.2`, `ops.version()` `3.7.1`
- Ubuntu CalculiX package `2.17-3`, CrunchiX runtime `2.17`
- OpenSees wheel 2개와 CalculiX/dependency Debian package 3개의 이름, 버전,
  SHA-256을 영수증 스키마에 고정
- OpenSees driver, CalculiX input deck, stdout/stderr 및 CalculiX `.dat`/`.frd`
  출력은 SHA-256으로 결속
- 외부 package와 runtime은 저장소에 번들하지 않음

현재 receipt artifact hash는
`sha256:ab4def3d1bc564fab21e7d563a975ad425d08c3b4cea16b1103c0f6c4b6977f1`,
internal source-set hash는
`sha256:481cd404c4353e144a58071a037f7b39b7631fd7ac9b670b784ffe5846ef03cb`이다.
Receipt의 `source_commit_sha`는 PR #104 기준
`b243f083e258327a5556483f6cb61d3124b15acc`이며, 실제 변경 source byte는 별도
source-set hash로 결속한다.

## 전체 모델 modal·buckling 추가 영수증

`external_modal_buckling_technical_execution_receipt.json`은 같은 고정 runtime
bytes를 실제 실행하되 제품의 공개 전체 모델 경로 두 개를 직접 비교한다.

| Case | 외부 기준 | 비교 정책 | 결과 |
|---|---|---|---|
| one-element frame consistent-mass modal | OpenSees 3.7.1 `elasticBeamColumn -cMass` | 고유값 2개 `1e-9 + 1e-10 scale`, per-mode MAC `>= 0.999999999999` | PASS |
| 16-element pin-ended square-column linear buckling | CalculiX CrunchiX 2.17 B32 | 좌굴계수 2개 `1e-8 + 1e-2 scale`, 반복 2모드 최소 principal-correlation-squared `>= 0.999999` | PASS |

Modal 첫 고유값은 정확히 일치하고 두 번째 고유값의 상대오차는
`4.827577502824829e-16`이다. 두 MAC는 `1.0`이다. 제품 좌굴계수는
`7.48629313198525`, `7.486293131988246`, CalculiX `.dat` 값은 두 모드 모두
`7.539292`이며 최대 상대오차는 `0.007029687670241386`이다. 두 솔버의 반복
모드 기저는 개별 벡터 방향에 의존하지 않는 부분공간으로 비교하며 최소
principal-correlation-squared는 `0.9999999970332671`이다. 이는 서로 다른
Euler-Bernoulli frame과 CalculiX expanded B32 formulation을 동일하다고
주장하지 않고, 선언된 1% 좌굴계수 tolerance 안의 좁은 code-to-code
비교만 기록한다.

네 mode matrix는 JSON에 넣지 않는다. `<f8`, C-order, little-endian raw binary
artifact로 저장하고 shape, byte length, data hash, content hash, repository path를
receipt에 기록한다. 현재 artifact hash는
`sha256:1a96b69041ba9b3ab54438ac3da07ceedb8701a072157070698a5355f0c675f0`,
source-set hash는
`sha256:d5e036962c7f0b150f9ee01e9243811c4350a7f2256f74d61dbb5f04b889fec7`다.
이 추가 영수증도 제품 법무/재배포 승인, 독립 clean runner, broad corpus,
published benchmark decision 또는 hierarchy operator manifest를 만들지 않으며
`verification_level_2=false`, `commercial_equivalence=false`,
`release_readiness=false`를 유지한다.

## 크레딧 경계

이 기술 영수증은 다음을 참으로 기록한다.

- 두 독립 외부 솔버의 실제 로컬 실행
- 고정된 외부 runtime 버전 확인
- 세 좁은 code-to-code case의 수치 계약 통과

다음은 명시적으로 `false`다.

- 제품 법무·라이선스 승인
- 외부 runtime 상용 재배포 승인
- verification hierarchy operator manifest 첨부
- Verification Level 2 크레딧
- 상용 솔버 동등성
- release readiness

OpenSeesPy license 문구는 내부 사용과 commercial redistribution을 구분하며,
CalculiX package는 GPL-2 posture를 기록한다. 이 저장소에는 어느 runtime에
대한 제품 법무 승인도 첨부돼 있지 않다. 또한 독립 clean runner 재현과
frame/shell/modal/buckling/nonlinear 구조형식 폭이 없다. 따라서 이 receipt를
`verification_hierarchy_evidence.json`에 넣어 Level 2로 승격하면 안 된다.

## 오프라인 검사

```bash
PYTHONPATH=src python3 scripts/run_external_code_to_code_technical_receipt.py --check
PYTHONPATH=src python3 scripts/run_external_modal_buckling_technical_receipt.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_external_code_to_code_technical_receipt.py \
  tests/test_external_modal_buckling_technical_receipt.py
```

`--check`는 저장된 receipt의 schema, artifact hash, 내부 source checksum,
외부 asset identity, 메트릭 재계산, case/claim 관계를 검사한다. 외부 package가
저장소에 없으므로 이 명령은 외부 솔버를 다시 실행하지 않는다. 새 실제 실행은
고정된 5개 package bytes와 두 license file, OpenSees Python runtime, CalculiX
binary/library 경로를 명시적으로 공급해야 한다.
