# 중형 벤치마크 코퍼스와 과학적 판정 계약

이 문서는 Developer Preview의 `selected_medium_models_pass_or_approved_review` 게이트에 사용할 최소 과학적 증거 계약을 고정한다. 모델 파일, 파서 성공, 토폴로지 수량 또는 템플릿 검토만으로는 벤치마크 크레딧을 부여하지 않는다.

## 필수 다섯 구조형식

정확히 한 사례씩 다음 슬롯을 채워야 한다.

1. `steel_moment_frame_3d`: 3D 강재 모멘트 골조
2. `braced_frame_or_truss_tower`: 가새 골조 또는 트러스 타워
3. `irregular_multistory_frame`: 비정형 다층 골조
4. `frame_shell_diaphragm`: 골조와 셸 다이어프램
5. `foundation_link_or_mixed_element`: 기초·링크 또는 혼합요소 모델

각 사례는 `medium` 규모 근거와 슬롯별 기능을 실제 응답에 사용했다는 증거를 가져야 한다. 대형 모델은 별도 대형-model 레인에 남으며 중형 슬롯의 대체 크레딧을 얻지 못한다. 서로 다른 source family가 둘 이상이어야 하며, 독립 reference solver 조합에는 OpenSees와 OpenSees가 아닌 상용 또는 별도 오픈소스 솔버가 모두 포함되어야 한다.

## 사례별 필수 artifact chain

모든 사례는 다음 artifact receipt의 저장소 상대 경로, 실제 receipt SHA-256,
개별 계약 PASS를 제공해야 한다.

- canonical normalization receipt
- reference solver input
- reference output
- product solver output
- residual comparison
- reaction/equilibrium comparison
- local-axis member-force comparison
- tolerance policy
- PASS 또는 유효한 REVIEW decision receipt

각 `medium-benchmark-artifact-receipt.v1`은 다시 실제 payload의 저장소 상대
경로, SHA-256, byte length, media type과 제품 source commit을 결합한다. 집계기는
receipt와 payload를 모두 읽고 hash/길이를 재계산한다. 절대경로, `..`, 역슬래시,
저장소 밖 경로와 symlink는 fail-closed다.

Source는 원본 파일 bytes를 manifest checksum과 직접 비교한다. License는 별도
`medium-benchmark-source-license-receipt.v1` bytes를 결합하고 case/source/license
identity 및 승인 플래그를 inline 선언과 대조한다. Reference solver는 이름,
확인된 버전, solver class, 제품으로부터의 독립성을 기록한다.

다음 payload는 byte 결합 외에 내용도 재검사한다.

- normalization receipt: case/kind/contract PASS
- residual, reaction, member-force comparison: 과학적 acceptance schema,
  정확한 metric family, contract PASS
- tolerance policy: case와 선언된 metric family 전체 범위
- decision receipt: scientific decision schema, PASS/REVIEW credit, inline decision과
  byte-for-byte JSON 의미 일치

이 검증은 선언만으로 크레딧을 만들 수 없게 하지만, 외부 solver가 실제로
실행됐는지, 법무 승인자와 엔지니어 신원이 진짜인지까지 암호학적으로
인증하지는 않는다. 그 권위는 연결된 외부 run·license·human receipt에 남는다.

## 지표별 판정

하나의 전역 relative error로 모든 응답을 판정하지 않는다.

| 지표 | 최소 판정 |
|---|---|
| displacement | 성분별 absolute/relative 오차와 전체 L2 norm |
| reaction | 성분·norm 오차와 외력 합에 대한 독립 force/moment equilibrium norm |
| member force | 명명된 local-axis 성분별 오차와 norm |
| energy | 대칭 global stiffness에 대한 `sqrt(ΔuᵀKΔu)` |
| modal | frequency error와 부호에 무관한 MAC |
| buckling | eigenvalue error와 부호에 무관한 mode MAC |
| nonlinear | 정렬된 무차원 load-response path의 최대·RMS 거리 |
| residual | translation, rotation, scaled residual을 서로 다른 임계값으로 판정 |

Reference가 zero 또는 near-zero이면 relative 분모를 사용하지 않고 별도 absolute tolerance를 적용한다. NaN, infinity, 차원 불일치, 비대칭 energy matrix 등은 안정된 code/path를 갖는 입력 계약 오류다.

## PASS / REVIEW / FAIL

- `PASS`: 모든 필수 metric family가 통과한다.
- `REVIEW`: 실패 metric이 있더라도 승인된 엔지니어 검토가 그 실패 범위를 정확히 덮을 때만 제한적으로 크레딧을 허용한다.
- `FAIL`: 수치 실패 또는 불완전한 검토이며 크레딧은 0이다.

`REVIEW`에는 `engineer_id`, `reason`, 실패 범위를 덮는 `scope`, 외부 `evidence_ref`, 명시적 승인, timezone-aware `expires_at`이 모두 필요하다. Hard blocker, 만료된 검토, 템플릿/placeholder 증거, 범위가 좁은 검토는 REVIEW로 우회할 수 없다.
Serialized decision inspector는 생성 당시 `evaluated_at`뿐 아니라 현재 운영
`as_of` 시점에도 `expires_at`을 다시 검사하므로, 과거에 유효했던 REVIEW가
만료 뒤 계속 크레딧을 유지할 수 없다.

## 현재 상태

기계 생성 계획은 `implementation/phase1/release_evidence/productization/medium_benchmark_corpus_plan.json`이다. 현재 상태는 `blocked`, 과학적 크레딧은 `0/5`다.

실제 운영 증거는 같은 디렉터리의 `medium_benchmark_case_evidence.json`에
`medium-benchmark-case-evidence-manifest.v1` 형식으로 첨부한다. Manifest는
`binding_profile=repository_bytes_and_receipt_payloads.v1`을 반드시 선언한다.
이 파일이 없을 때만 생성기가 기존 canonical parser 후보를 비승격 계획으로
보여 준다. 운영 manifest가 존재하지만 schema, binding profile, `cases`, claim
boundary가 잘못되면 parser 후보로 조용히 되돌아가지 않고 명시적 input
blocker를 남긴다.

- `SCBF16B`: 가새 슬롯 후보지만 license 승인, 확인된 reference solver 버전, 실행/비교 artifact와 decision이 없어 차단됨
- `SCBF16B_shell_beam_mix`: 골조+셸 후보지만 다이어프램 load-path 증명과 source provenance를 포함한 필수 증거가 없어 차단됨
- `luxinzheng_megatall_model1`: 비정형 후보 자료지만 대형 모델이므로 중형 크레딧 0
- 3D 강재 모멘트 골조 슬롯: 선택 사례 없음
- 기초·링크/혼합요소 슬롯: 선택 사례 없음

기존 readiness receipt의 `3/5`는 parser-ready 후보 수이며 과학적 PASS/REVIEW 수가 아니다. 이 문서의 계약과 생성 계획은 그 값을 폐기하지 않고, 후보 준비도와 벤치마크 크레딧을 명시적으로 분리한다.

## 검증 명령

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_benchmark_scientific_acceptance.py \
  tests/test_medium_benchmark_corpus_contract.py \
  tests/test_build_medium_benchmark_corpus_plan.py
python3 scripts/build_medium_benchmark_corpus_plan.py --check
```

이 검증이 통과해도 실제 다섯 reference run, 외부/상용 solver 결과,
제품·법무 승인, 엔지니어 REVIEW 또는 Developer Preview 게이트가 생성되거나
닫히지는 않는다. 현재 계획은 계속 `0/5 blocked`이며 새 byte-binding 계약은
없는 증거를 합성하지 않는다.

Level 1–5 전체 승격 정책과 현재 단계별 누락은 `docs/structural-verification-hierarchy.md`에서 별도로 관리한다.
