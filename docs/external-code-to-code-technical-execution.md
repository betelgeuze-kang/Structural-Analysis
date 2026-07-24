# 외부 code-to-code 기술 실행 영수증

이 문서는 OpenSees와 CalculiX를 실제 로컬 실행한 좁은 기술 비교를 설명한다. 이
실행은 검증 계층 Level 2 후보를 준비하지만, Level 2 증거로 등록하거나 제품의
법무·재배포·상용 동등성·출시 준비를 승인하지 않는다.

## 실행 범위

`external_code_to_code_technical_execution_receipt.json`은 정확히 다섯 case를
기록한다.

| Case | 외부 기준 | 제품 경로 | 비교 항목 | 결과 |
|---|---|---|---|---|
| 2자유도 shear modal | OpenSees 3.7.1 | deterministic generalized-eigen modal kernel | 고유값 2개 | PASS |
| cantilever tip load | OpenSees 3.7.1 | authoritative linear-static frame 경로 | tip 변위, base 전단반력, base 모멘트 | PASS |
| public corotational portal load path | OpenSees 3.7.1 `Corotational` elastic beam-column | 공개 J1-J5 stateful corotational fiber-frame 경로, 4개 load step | N3/N4 변위·회전 6개, N1/N2 지점반력 6개 | PASS |
| axial member tip load | CalculiX CrunchiX 2.17 | authoritative linear-static frame 경로 | tip 변위, base 축반력 | PASS |
| tetrahedral spatial truss combined load | CalculiX CrunchiX 2.17 `T3D2` | authoritative linear-static 3D truss 경로, 6개 부재 | apex 3축 변위, base 3개 절점의 3축 반력 9개 | PASS |

총 31개 수치 비교가 통과했다. Modal 고유값과 axial 결과의 절대오차는 `0`이고,
spatial-truss case의 최대 절대오차는 `4.694679409237196e-13`이다. 전체 최대
절대오차는 portal 반력의 `2.438173396512866e-08`, 전체 최대 상대오차는
CalculiX 출력 정밀도의 영향을 받는 spatial-truss 변위의
`3.6168200235569254e-07`이다. 비교 허용오차는
`1e-10 + 1e-10 * max(abs(product), abs(reference), 1)`이며 제품 경로의
fallback과 regularization은 모두 `false`다.

Portal case는 공개 RC fiber section의 초기 탄성 강성 `EA=7,819,200 kN`,
`EI=200,700 kN·m²`를 OpenSees elastic section에 동일하게 적용한다. 모든 fiber
stress가 선언된 concrete/steel 강도 경계 안에 있음을 실행 시 검사한다. 따라서
이 case는 corotational geometry와 공개 J1-J5/exact recovery 연결을 확인하지만,
재료 비선형, 항복·손상, cyclic breadth를 검증하지 않는다.

Spatial-truss case는 세 고정 base 절점과 하나의 apex 절점, 여섯 `T3D2`
부재에 `FX=1.2`, `FY=-0.8`, `FZ=-1.5 kN`의 결합하중을 적용한다. 이는
CalculiX를 두 번째 외부 솔버로 사용한 3D 다부재 선형 정적 비교 범위를 넓히지만,
frame/shell 또는 재료·기하 비선형 비교와 독립 운영자 검토를 대신하지 않는다.

## 런타임과 결속

- OpenSeesPy distribution `3.7.1.2`, `ops.version()` `3.7.1`
- Ubuntu CalculiX package `2.17-3`, CrunchiX runtime `2.17`
- OpenSees wheel 2개와 CalculiX/dependency Debian package 3개의 이름, 버전,
  SHA-256을 영수증 스키마에 고정
- OpenSees driver, CalculiX input deck, stdout/stderr 및 CalculiX `.dat`/`.frd`
  출력은 SHA-256으로 결속
- 외부 package와 runtime은 저장소에 번들하지 않음

현재 receipt artifact hash는
`sha256:1b490fae40f6dafc559561367a33a2c2323f69efbbb2119ac35ab2ed4fc1f31d`,
internal source-set hash는
`sha256:734547310524ea4bbe6d5f196f879b1cb4b9bad6279bf97e0542cfc9bcfade5e`이다.
Receipt의 `source_commit_sha`는 후보 생성 시 base인
`d81cf64e731288b13bab06edcbe8459546819bfd`이며, 후보의 실제 source byte는 별도
input checksum과 source-set hash로 결속한다.

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
`sha256:77dce301c45f9f25c88445aff95d196ca1aa7b771f46fa79a94f9fea69d3e712`,
source-set hash는
`sha256:e70b17f36e473b94e0455dd28157c951436047f5cd23185a72173fbec575bda7`다.
이 추가 영수증도 제품 법무/재배포 승인, 독립 clean runner, broad corpus,
published benchmark decision 또는 hierarchy operator manifest를 만들지 않으며
`verification_level_2=false`, `commercial_equivalence=false`,
`release_readiness=false`를 유지한다.

## 동일 운영자 격리 clean runner

`benchmarks/clean-runners/opensees-calculix/`는 위 두 영수증을 고정된
Python 3.11 base image에서 다시 생성한다. 실행 시 repository mount는 read-only,
runtime network는 `none`, 지정 output mount만 writable이며 다섯 외부 package의
SHA-256을 추출 전에 검사한다. 생성 bundle은
`artifacts/vv/opensees_calculix_clean_runner/`에 있고 summary artifact hash는
`sha256:99c7fc02f3f76c6a6b84c3f5da6b0a9218a73fb4b49fc579c546c2774983a85e`다.

호스트와 container의 73개 scalar가 `1e-12 + 1e-12 * scale` 계약을 통과했다.
최대 절대 delta는 `2.219557870830613e-12`, 최대 상대 delta는
`1.6209256159527285e-12`다. Model hash는 일치하지만 buckling semantic result
hash는 실행 환경의 허용오차 내 부동소수점 차이로 동일하지 않다. 따라서 summary는
`same_operator_container_isolated_reproduction=true`만 기록하고
`exact_semantic_hash_parity=false`를 보존한다.

이 실행은 동일 운영자가 만든 기술 후보다. 독립 운영자 재현·서명, 법무·재배포
승인, hierarchy operator manifest가 아니므로 Verification Level 2에 편입하지
않는다. 함께 실행되는 CalculiX 회귀도 별도 second-solver 로드맵 항목을 폐쇄하지
않는다.

## 크레딧 경계

이 기술 영수증은 다음을 참으로 기록한다.

- 두 독립 외부 솔버의 실제 로컬 실행
- 고정된 외부 runtime 버전 확인
- 다섯 좁은 code-to-code case의 31개 수치 계약 통과
- 동일 운영자 container-isolated 재현과 호스트/컨테이너 수치 계약 통과

다음은 명시적으로 `false`다.

- 제품 법무·라이선스 승인
- 외부 runtime 상용 재배포 승인
- verification hierarchy operator manifest 첨부
- Verification Level 2 크레딧
- 상용 솔버 동등성
- release readiness

OpenSeesPy license 문구는 내부 사용과 commercial redistribution을 구분하며,
CalculiX package는 GPL-2 posture를 기록한다. 이 저장소에는 어느 runtime에
대한 제품 법무 승인도 첨부돼 있지 않다. 또한 독립 운영자 clean-runner 재현과
frame/shell/modal/buckling/material-nonlinear 구조형식 폭이 없다. 따라서 이 receipt를
`verification_hierarchy_evidence.json`에 넣어 Level 2로 승격하면 안 된다.

## 오프라인 검사

```bash
PYTHONPATH=src python3 scripts/run_external_code_to_code_technical_receipt.py --check
PYTHONPATH=src python3 scripts/run_external_modal_buckling_technical_receipt.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_external_code_to_code_technical_receipt.py \
  tests/test_external_modal_buckling_technical_receipt.py \
  tests/test_external_vv_clean_runner_contract.py
```

외부 asset directory가 준비된 재현 명령은 다음과 같다.

```bash
scripts/run_external_vv_clean_runner.sh <external-asset-directory>
```

`--check`는 저장된 receipt의 schema, artifact hash, 내부 source checksum,
외부 asset identity, 메트릭 재계산, case/claim 관계를 검사한다. 외부 package가
저장소에 없으므로 이 명령은 외부 솔버를 다시 실행하지 않는다. 새 실제 실행은
고정된 5개 package bytes와 두 license file, OpenSees Python runtime, CalculiX
binary/library 경로를 명시적으로 공급해야 한다.

현재 제품 재생은 NumPy/SciPy 및 BLAS 구현 차이로 생기는 반올림 편차를
code-to-code scalar에는 절대 `1e-10`와 상대 `1e-10`의 합으로, modal·buckling
고유값에는 절대 `1e-12`와 상대 `1e-12`의 합으로 제한한다. source checksum과
model hash는 여전히 완전 일치해야 하며, modal mode는 MAC, repeated buckling
mode는 basis-invariant subspace correlation으로 검증한다. semantic result hash가
플랫폼별로 달라도 이 좁은 수치·모드 계약을 통과해야 하며, 허용오차 밖의 변화는
stale evidence로 거부된다.

외부 runtime을 현재 source에서 다시 실행할 수 없는 환경에서는 공식
`--refresh-product-replay` 경로만 사용한다. 이 경로는
`external_runtime_current_source_rerun_missing`을 추가하고 재사용 이유를
checksum-bound receipt에 기록하므로 fresh external execution이나 Level 2로
승격할 수 없다.
