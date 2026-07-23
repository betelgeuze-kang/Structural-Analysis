# 구조 검증 계층 Level 1–5

이 계약은 검증 evidence를 `Analytic → Code-to-code → Published benchmark → Experimental → Customer shadow` 순서로 분리한다. 높은 단계의 자료가 있어도 낮은 단계의 누락을 우회해 승격할 수 없다. 각 단계는 자체 증거 충족 여부(`intrinsic_contract_pass`)와 하위 단계까지 포함한 연속 승격 여부(`promotion_contract_pass`)를 따로 기록한다.

## 단계별 최소 슬롯

| Level | Truth basis | 필수 슬롯 |
|---:|---|---|
| 1 | `analytic_closed_form` | single bar, cantilever beam, simply supported beam, portal frame, patch tests |
| 2 | `code_to_code` | OpenSees, 두 번째 독립 open-source 또는 commercial solver |
| 3 | `published_benchmark` | NAFEMS, published shell patch, nonlinear snap-through, material cyclic |
| 4 | `experimental` | load-displacement, failure mode, strain distribution |
| 5 | `customer_shadow` | 서로 다른 completed-project review metadata 최소 3건 |

모델 수가 많아도 동일 구조형식 반복은 다른 슬롯을 채우지 않는다. 예를 들어 axial bar 20건은 `single_bar` 한 슬롯의 증거이며 cantilever/portal 증거가 아니다.

## 공통 evidence 계약

모든 행은 `structural-verification-evidence.v1`을 사용하고 다음을 포함한다.

- level/category와 해당 단계의 정확한 `truth_basis`
- source URL/DOI 또는 허용된 privacy-safe/generated URI와 SHA-256
- 승인 상태가 명시된 license/use receipt
- path, SHA-256, `contract_pass`를 가진 artifact
- `benchmark-scientific-decision.v1` PASS 또는 scoped REVIEW
- 명시적 declared blocker

Level 2는 독립 reference solver 이름·확인된 버전이 필요하다. Level 3은 benchmark 이름과 publisher, Level 4는 dataset ID와 측정 종류가 필요하다. Level 5는 raw customer data를 저장하지 않고 hashed case ID, completed 상태, reviewer ID, `raw_data_retained_by_customer=true`, `redistribution_allowed=false`만 사용한다.

단순 `benchmark_credit: true`, readiness packet, source URL, parser receipt, 템플릿, 제출 queue 또는 artifact hash 없는 검토는 크레딧을 얻지 못한다.

## 현재 상태

생성 상태는 `implementation/phase1/release_evidence/productization/verification_hierarchy_status.json`이다.

- 전체: `BLOCKED`, 연속 검증 최고 단계 `1/5`
- Level 1: `ready`; `single_bar`, `cantilever_beam`, `simply_supported_beam`,
  `portal_frame`, `patch_tests`의 다섯 슬롯이 모두 통과
- `analytic_frame_verification.json`은 authoritative CPU 6-DOF 경로를 실제
  실행해 cantilever tip-load 식, simply-supported midpoint-load 식, 유한
  column `EA/EI`와 beam `EI`를 포함한 one-bay portal slope-deflection 식과
  비교한다. Artifact hash는
  `sha256:c9f789c4f04a25fb317f043c9c50cbd633ba77ab68340fcc83c957896342b90b`다.
- Portal의 12개 displacement/rotation/reaction 비교에서 최대 절대 오차는
  `1.4921397450962104e-13`, 최대 상대 오차는
  `9.237055564881303e-15`이고, free relative residual은
  `1.4210854715202004e-14`다. Binary64 결과는 17자리 round-trip decimal로
  보존하며 fallback과 regularization은 모두 `false`다.
- Level 2: OpenSees 3.7.1과 CalculiX CrunchiX 2.17을 실제 실행한 좁은 기술
  candidate는 존재하지만 hierarchy evidence credit은 여전히 `0/2`다.
  `external_code_to_code_technical_execution_receipt.json`은 2자유도 modal,
  cantilever static, 공개 corotational portal의 4-step elastic-state load path,
  axial-member static의 네 case와 19개 metric을 통과하며
  artifact hash
  `sha256:7a47f3671b4fb665630a835c0ff49723f7ae67b70bbb5c0ea8cae87606685ca1`를
  기록한다. 추가
  `external_modal_buckling_technical_execution_receipt.json`은 공개 전체 모델
  frame modal을 OpenSees에, 반복 2모드 frame 선형좌굴을 CalculiX B32에
  비교한다. Modal 고유값 2개와 MAC 2개가 통과하고, 좌굴계수 2개는 선언된
  1% tolerance에서 최대 상대오차 `0.007029687670241386`, 반복군집 최소
  principal-correlation-squared는 `0.9999999970332671`로 통과한다. 네 mode
  matrix는 little-endian binary artifact로 분리돼 있다. 추가 receipt의
  artifact hash는
  `sha256:f8e39b1d04913522a18414909dc674f4691b2c56fc98c067663fee9459af2572`다.
  동일 운영자 container-isolated clean runner도 두 영수증을 재현했고 49개
  host/container scalar 계약을 통과했다. 해당 summary artifact hash는
  `sha256:39f33bbf5a03872fb2c1a9b86daa95bf8fdc343e01f7485fc0a1346699884c0f`다.
  그러나 제품 법무 승인, redistribution 승인, 독립 운영자 재현·서명,
  material-nonlinear 구조형식 breadth, published benchmark decision과 operator manifest가 없으므로
  `verification_hierarchy_credit=false`이고 Level 2로 승격하지 않는다. 중형
  corpus의 과학적 크레딧도 `0/5`다. 중형 corpus는 별도
  `repository_bytes_and_receipt_payloads.v1` 계약으로 source, license receipt,
  artifact receipt와 실제 payload bytes를 이중 hash 결합한다. 현재 bound case는
  `0/5`이므로 이 강화가 Level 2 또는 Developer Preview 크레딧을 새로 만들지는
  않는다.
- `phase2_whole_model_modal_result.json`과
  `phase2_whole_model_buckling_result.json`은 각각 bounded frame/truss 공개
  모달 및 compression-only frame 선형좌굴 경로에서 analytic/invariant gate
  `4/4`를 통과한다. 위 별도 기술 receipt가 각각 한 frame/column의 독립
  reference 비교를 추가했고 같은 운영자 격리 재현도 통과했지만 법무/use approval,
  독립 운영자 attestation, breadth,
  published decision과 hierarchy operator manifest가 없으므로 Level 2 슬롯을
  채우지 않는다. 따라서 receipts를 추가해도 최고 검증 단계는 `1`이다.
- Level 3: published benchmark 실행·비교·판정 evidence 없음
- Level 4: 공개 실험 측정 데이터 비교 evidence 없음
- Level 5: customer shadow completed-project evidence `0/3`

따라서 Level 1 analytic hierarchy는 완료됐지만 전체 hierarchy와 Developer
Preview는 계속 `BLOCKED`다. 세 frame case는 small-displacement,
linear-elastic, prismatic Euler-Bernoulli 가정의 Level 1 증거일 뿐이며 독립
solver, published/experimental/customer truth 또는 release readiness로 승격할 수
없다.

## 운영 evidence 첨부

추가 증거는 `implementation/phase1/release_evidence/productization/verification_hierarchy_evidence.json`의 `structural-verification-evidence-manifest.v1` 형식으로 첨부한다. Manifest가 존재하지만 schema, `evidence`, claim boundary가 잘못되면 기존 로컬 증거로 조용히 되돌아가지 않고 input blocker를 남긴다.

```bash
PYTHONPATH=src python3 scripts/build_analytic_frame_verification_artifact.py --check
PYTHONPATH=src python3 scripts/run_external_code_to_code_technical_receipt.py --check
PYTHONPATH=src python3 scripts/run_external_modal_buckling_technical_receipt.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_analytic_frame_verification.py \
  tests/test_external_code_to_code_technical_receipt.py \
  tests/test_external_modal_buckling_technical_receipt.py \
  tests/test_verification_hierarchy_contract.py \
  tests/test_build_verification_hierarchy_status.py
python3 scripts/build_verification_hierarchy_status.py --check
```

이 검사는 evidence metadata와 선언된 hash/판정을 집계한다. Solver를 재실행하거나 source byte, publisher, 실험 데이터, customer reviewer 신원을 독립 인증하지 않는다.
