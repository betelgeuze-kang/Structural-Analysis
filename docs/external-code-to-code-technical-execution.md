# 외부 code-to-code 기술 실행 영수증

이 문서는 OpenSees와 CalculiX를 실제 로컬 실행해 저장한 좁은 기술 비교와
현재 제품 replay를 설명한다. 현재 source에서는 고정된 다섯 외부 asset으로
OpenSees와 CalculiX를 같은 generation에서 다시 실행했고 두 child receipt 모두
fresh다. 이는 동일 운영자의 좁은 기술 증거이므로 Level 2 증거로 등록하거나
제품의 법무·재배포·상용 동등성·출시 준비를 승인하지 않는다.

## 실행 범위

`external_code_to_code_technical_execution_receipt.json`은 정확히 열한 case를
기록한다.

| Case | 외부 기준 | 제품 경로 | 비교 항목 | 결과 |
|---|---|---|---|---|
| 2자유도 shear modal | OpenSees 3.7.1 | deterministic generalized-eigen modal kernel | 고유값 2개 | PASS |
| cantilever tip load | OpenSees 3.7.1 | authoritative linear-static frame 경로 | tip 변위, base 전단반력, base 모멘트 | PASS |
| public corotational portal load path | OpenSees 3.7.1 `Corotational` elastic beam-column | 공개 J1-J5 stateful corotational fiber-frame 경로, 4개 load step | N3/N4 변위·회전 6개, N1/N2 지점반력 6개 | PASS |
| bounded planar member-feature load path | OpenSees 3.7.1 `Corotational elasticBeamColumn`, `-jntOffset`, `-release 2`, `beamUniform` | `bounded_planar_frame_alpha` ModelIR v2 경로, 4개 load step | N2 변위 2개, N1/N2 지점반력 4개, E1 양단 모멘트 2개 | PASS |
| bounded planar prescribed-settlement load path | OpenSees 3.7.1 `Corotational elasticBeamColumn`, `Transformation`, `sp` | source-bound `bounded_planar_frame_alpha` ModelIR v2 경로, 1 kN 축 기준하중 + N2 UY `-0.1 mm`, 4개 load step | N2 변위 2개, N1/N2 지점반력 5개, E1 양단 모멘트 2개 | PASS |
| spatial Frame3D cantilever combined load | OpenSees 3.7.1 `ElasticTimoshenkoBeam` | stateful sparse corotational Frame3D load-control 경로, 2 m one-element cantilever | tip UY/UZ/RX/RY/RZ, base FY/FZ/MX/MY/MZ | PASS |
| Frame3D axial-yield direct control | OpenSees 3.7.1 `forceBeamColumn` + `Steel01` | source-bound bounded Frame3D ModelIR v2 direct-displacement-control API, N2 UX four-target path through first yield | control UX, load factor, base UX reaction, axial stress, plastic strain, backstress, accumulated plastic strain, dissipated energy density | PASS |
| Frame3D rotational direct control | OpenSees 3.7.1 3D `forceBeamColumn` + elastic `GJ` | source-bound bounded Frame3D ModelIR v2 direct-displacement-control API, N2 RX four-target torsional path | control RX, moment-load factor, base RX reaction | PASS |
| Frame3D bending-rotational direct control | OpenSees 3.7.1 3D `forceBeamColumn` + elastic `EIy/EIz` | separate source-bound N2 RY and RZ four-target pure-axis bending paths | each control angle, moment-load factor, same-axis base moment | PASS |
| axial member tip load | CalculiX CrunchiX 2.17 | authoritative linear-static frame 경로 | tip 변위, base 축반력 | PASS |
| tetrahedral spatial truss combined load | CalculiX CrunchiX 2.17 `T3D2` | authoritative linear-static 3D truss 경로, 6개 부재 | apex 3축 변위, base 3개 절점의 3축 반력 9개 | PASS |

총 75개 수치 비교가 통과했다. Modal 고유값과 axial 결과의 절대오차는 `0`이고,
spatial-truss case의 최대 절대오차는 `4.694679409237196e-13`이다. 새 Frame3D
case의 최대 절대·상대오차는 base torsional reaction에서 각각
`7.531298538004938e-07`과 `3.765649269002469e-05`다. 기존 일곱 case는
`1e-10 + 1e-10 * max(abs(product), abs(reference), 1)`을 유지하고, 작은
corotational-대-linear formulation 차이를 숨기지 않는 Frame3D case만
`1e-10 + 1e-4 * max(abs(product), abs(reference), tiny)`를 사용한다. 축항복
direct-control case는 `1e-10 + 1e-8 * scale`을 사용하며 최대 절대·상대오차는
각각 `5.667998266289942e-07`과 `1.1181012204986017e-10`이다. RX direct-control
case도 `1e-10 + 1e-8 * scale`을 사용한다. 제품 경로의 fallback과
regularization은 모두 `false`다.

Portal case는 공개 RC fiber section의 초기 탄성 강성 `EA=7,819,200 kN`,
`EI=200,700 kN·m²`를 OpenSees elastic section에 동일하게 적용한다. 모든 fiber
stress가 선언된 concrete/steel 강도 경계 안에 있음을 실행 시 검사한다. 따라서
이 case는 corotational geometry와 공개 J1-J5/exact recovery 연결을 확인하지만,
재료 비선형, 항복·손상, cyclic breadth를 검증하지 않는다.

Member-feature case는 물리 절점 좌표 `0–4 m`와 변형 부재 길이 `3.6 m`를
구분한다. 양단 `0.2 m` rigid offset, J-end RZ release, initial-local
`qy=-2 kN/m` dead load를 두 solver에 동일하게 적용한다. 총 하중 `7.2 kN`,
N1 물리 support moment `14.399999978... kN·m`, J-end member moment
수치영점을 포함해 변위·반력·부재단 모멘트 8개가 통과한다. 이는 세 member
feature와 exact engineering recovery의 동일 의미 비교이지 재료 비선형
검증이나 독립 운영자 판정이 아니다.

Prescribed-settlement case는 자유 UX 방정식에 명시적인 `1 kN` 축 기준하중을
적용하면서 N2 UY에 `-0.1 mm`를 처방한다. 제품의 EquationScaling 기준력은
`1000 N`으로 available이고, solver 실행·4단계 수렴 trace·exact checkpoint
replay·engineering recovery가 모두 활성화된다. OpenSees와 비교한 변위 2개,
반력 5개, 부재단 모멘트 2개의 최대 절대차는
`1.8189894035458565e-12`다. 이는 하중과 지점침하가 결합된 경계 사례의
same-operator 기술 비교이며, 자유방정식 기준력이 없는 displacement-only
no-solve 또는 direct displacement-control authority를 만들지 않는다.

Spatial Frame3D case는 global X축 방향 2 m cantilever에 `FY=-0.1 kN`,
`FZ=0.075 kN`, `MX=0.02 kN·m`를 동시에 적용한다. 제품의 stateful sparse
corotational load-control 경로와 OpenSees `ElasticTimoshenkoBeam`이 동일한
`A/Iy/Iz/J/Avy/Avz`, `E=200 GPa`, `G=80 GPa`를 소비한다. Tip kinematics 5개와
base reaction 5개가 모두 통과하고 제품 재료점의 accumulated plastic strain은
정확히 `0`이다. 이는 작은 변형의 same-operator elastic 3D load-control
비교다. 재료 비선형, 큰 회전 breadth, 직접 변위제어, 독립 운영자 검토 또는
formal Level 2를 대신하지 않는다.

Frame3D axial-yield direct-control case는 같은 2 m 축부재를 N2 UX
`0.0015/0.003/0.0045/0.006 m`의 네 target으로 제어한다. 제품의 bilinear
combined-hardening 상태와 OpenSees `Steel01`의 동일 단조 등가 후항복 탄젠트를
사용해 최종 하중계수 `5069.3069302603735`, 축응력 `253.4653465130187 MPa`,
소성변형률 `0.0017326732673266254`까지 비교한다. 네 target 모두 수렴하고 exact
checkpoint가 생성됐으며 cutback, fallback, regularization은 없었다. 이는 동일
운영자의 단일 UX·단조 축항복 기술 비교만 닫는다. 다축/다중제어, 반복·역전하중,
일반 fiber/shear/torsion coupling, 독립 운영자 또는 formal Level 2는 닫지 않는다.

Frame3D rotational direct-control case는 별도 source-bound ModelIR에서 N2 RX를
`0.0005/0.001/0.0015/0.002 rad`로 제어하고, `1 kN·m` 기준모멘트에 대한 최종
하중계수와 base RX 반력을 비교한다. 제품과 OpenSees 모두 최종
`RX=0.002 rad`, 하중계수 약 `0.8`, 반력 약 `-0.8 kN·m`에 도달한다. 네 target
모두 수렴하고 exact checkpoint가 생성됐으며 cutback, fallback,
regularization은 없다. 이는 rotational row/column equilibration과 rad·kN·m
단위를 같은 3D six-DOF 문제에서 확인하는 same-operator 기술 비교다. 일반
회전·큰회전 breadth, 비선형 torsion, 다중제어 또는 독립 V&V를 뜻하지 않는다.

Frame3D bending-rotational case는 RY와 RZ를 별도 source-bound ModelIR에서
각각 `0.0005/0.001/0.0015/0.002 rad`로 제어한다. `1 kN·m` 순수축 기준모멘트와
서로 다른 `Iy/Iz`를 사용해 최종 하중계수 약 `10/16`, base moment 약
`-10/-16 kN·m`를 OpenSees와 비교한다. 이 비교는 두 principal bending axis의
rotation scaling과 exact checkpoint를 닫지만, MY+MZ 동시 기준하중에서 생기는
second-order torsional coupling은 비교 범위 밖이며 일반 다축 결합으로 승격하지
않는다.

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

현재 receipt의 live hash authority는
`artifacts/vv/opensees_calculix_clean_runner/external_code_to_code_receipt.json`의
`artifact_hash`와 `internal_source.source_set_hash` 필드다. 재생성 시각을 포함하는
volatile replay hash를 문서에 복제하지 않는다.
Receipt의 `source_commit_sha`는 후보 생성 시 base인
`f8929fa0cab55778131321eed348e7ec28d2eca0`이며, 후보의 실제 source byte는 별도
input checksum과 source-set hash로 결속한다.

## 전체 모델 modal·buckling 추가 영수증

`external_modal_buckling_technical_execution_receipt.json`은 같은 고정 runtime
bytes에서 보존된 외부 값을 제품의 공개 전체 모델 경로 두 개와 비교한다. 현재
source generation에서는 제품 replay만 다시 실행됐고 외부 runtime은 재사용됐다.

| Case | 외부 기준 | 비교 정책 | 결과 |
|---|---|---|---|
| one-element frame consistent-mass modal | OpenSees 3.7.1 `elasticBeamColumn -cMass` | 고유값 2개 `1e-9 + 1e-10 scale`, per-mode MAC `>= 0.999999999999` | PASS |
| 16-element pin-ended square-column linear buckling | CalculiX CrunchiX 2.17 B32 | 좌굴계수 2개 `1e-8 + 1e-2 scale`, 반복 2모드 최소 principal-correlation-squared `>= 0.999999` | PASS |

### 권장 matrix의 rigid/repeated modal 및 portal buckling 패키지

`artifacts/vv/bounded_planar_external_modal_buckling_case_package/`는 다음 세
행의 정확한 canonical model, 현재 제품 replay, 공용 외부 runner, source-file
hash, pinned runtime, main 전용 attested workflow를 묶는 비승격 실행 패키지다.
별도 로컬 동일 운영자 번들은 이 패키지로 실제 실행한 원시 결과와 3/3 기술
영수증을 저장소에 결속한다.

- `modal.rigid_mode` → `bounded_planar_modal_rigid_mode` (OpenSees)
- `modal.repeated_mode` → `bounded_planar_modal_repeated_mode` (OpenSees)
- `buckling.portal` → `bounded_planar_buckling_portal` (CalculiX B32)

Rigid-mode 비교는 강체모드 수와 강체모드 제거 뒤의 유연 고유치를 확인한다.
OpenSees 3D 일관질량의 비틀림 항과 제품의 극2차모멘트 항이 같은 문제를
풀도록 modal 단면은 `J = Iy + Iz`를 명시한다.
Repeated-mode 비교는 개별 고유벡터의 부호나 기저를 고정하지 않고 최소
subspace correlation `>= 0.999`를 사용한다. Portal buckling은 제품의
16개 선형 요소/부재를 원형 단면 CalculiX B32 8개/부재로 완전 피복 매핑하고,
Euler-Bernoulli initial-stress formulation 차이를 숨기지 않은 채 좌굴계수에
상대 `5%` 허용오차를 둔다.

준비 manifest의 `external_solver_execution`, `external_reference_attached`,
`verification_matrix_credit`, `verification_level_2`는 계속 `false`다. 별도
`bounded_planar_same_operator_supplemental_execution/receipt.json`이 실제 실행을
결속해 V&V matrix의 세 행은 `fresh_external_technical`이지만, 이 로컬 실행은
컨테이너 attestation·독립 operator·법적 승인·formal promotion receipt를
제공하지 않으므로 승격되지 않는다.

```bash
PYTHONPATH=src python3 scripts/build_bounded_planar_external_modal_buckling_case_package.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_build_bounded_planar_external_modal_buckling_case_package.py \
  tests/test_ingest_bounded_planar_external_modal_buckling_results.py
```

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
receipt에 기록한다. 현재 live hash authority는
`artifacts/vv/opensees_calculix_clean_runner/external_modal_buckling_receipt.json`의
`artifact_hash`와 `internal_source.source_set_hash` 필드이며, volatile replay hash를
문서에 복제하지 않는다.
이 추가 영수증도 제품 법무/재배포 승인, 독립 clean runner, broad corpus,
published benchmark decision 또는 hierarchy operator manifest를 만들지 않으며
`verification_level_2=false`, `commercial_equivalence=false`,
`release_readiness=false`를 유지한다.

## 동일 운영자 격리 clean runner

`benchmarks/clean-runners/opensees-calculix/`는 위 두 영수증을 고정된
Python 3.11 base image에서 다시 생성한다. 실행 시 repository mount는 read-only,
runtime network는 `none`, 지정 output mount만 writable이며 다섯 외부 package의
SHA-256을 추출 전에 검사한다. 생성 bundle은
`artifacts/vv/opensees_calculix_clean_runner/`에 있고 summary의 live hash authority는
`clean_runner_receipt.json`의 `artifact_hash` 필드다. volatile replay hash를 문서에
복제하지 않는다.

보존된 container generation은 네트워크 차단·read-only source·고정 자산 계약을
유지하지만, 현재 host receipt에 추가된 cyclic direct-control metric과 source 변경을
포함하지 않는다. 갱신된 summary는 host/container scalar 수 `199/161`, metric/source
set match `false`, `cross_environment_numerical_parity=false`를 기록한다. 따라서 현재
matrix의 `same_operator_execution_binding`은
`current_source_clean_runner_cross_environment_parity_missing` 사유로 unavailable이며,
container parity나 isolation credit을 부여하지 않는다. 별도의 current-source host
OpenSees/CalculiX receipt가 실제 외부 실행과 9개 core row의 fresh 기술 증거를
제공한다. 독립 운영자 attestation, 제품 법무·재배포 승인, Verification Level 2 또는
release readiness는 여전히 승격되지 않는다.

이 실행은 동일 운영자가 만든 기술 후보다. 독립 운영자 재현·서명, 법무·재배포
승인, hierarchy operator manifest가 아니므로 Verification Level 2에 편입하지
않는다. 함께 실행되는 CalculiX 회귀도 별도 second-solver 로드맵 항목을 폐쇄하지
않는다.

## 크레딧 경계

이 기술 영수증은 다음을 참으로 기록한다.

- 두 독립 외부 솔버의 실제 로컬 실행
- 고정된 외부 runtime 버전 확인
- 열한 좁은 code-to-code case의 75개 수치 계약 통과
- 저장된 host/container 값에 대한 current-product 수치 계약 통과
- current-source external runtime rerun
- same-operator current-source container-isolated reproduction

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
