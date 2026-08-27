# Current-source 중형 규모 실행 계약

`python-reference-medium-scale.v1`은 현재 source의 공개 Python 6-DOF 선형
Frame/Truss 경로가 Native Frame Alpha의 60 자유방정식 한계를 넘어 실제 희소
조립과 해를 만들 수 있는지 검증한다. 대형 fixture는 저장소에 두지 않고 다섯
모델을 결정적으로 생성한다.

| 사례 | 구조형식 슬롯 | 자유방정식 | 권한 경계 |
| --- | --- | ---: | --- |
| `generated_steel_moment_frame_3d` | 3D 모멘트 골조 | 480 | 연결·설계기준 권한 없음 |
| `generated_braced_truss_tower` | 공간 가새/트러스 타워 | 288 | 좌굴·접합 권한 없음 |
| `generated_irregular_multistory_frame` | 비정형 다층 골조 | 432 | 외부 validation 없음 |
| `generated_frame_diaphragm_surrogate` | 다이어프램 슬롯의 frame/truss surrogate | 360 | shell을 실행하거나 검증하지 않음 |
| `generated_mixed_frame_truss_foundation_surrogate` | 혼합요소 슬롯의 frame/truss surrogate | 378 | link·spring·soil·foundation을 실행하지 않음 |

각 worker는 다음 gate를 모두 통과해야 기술 실행 크레딧을 얻는다.

- 257~2,048 자유방정식의 중형 규모
- SciPy CSR 희소 조립과 SuperLU factorization
- 동일 6-DOF scaling을 적용한 SPD 최소·최대 고유치 조건수 추정
- 희소 경로의 status/residual과 fallback·regularization 부재
- NumPy dense 경로와 변위·반력·local member force·energy 비교
- production assembly·element·solver를 import하지 않는 별도 Euler--Bernoulli
  Frame3D/axial-truss oracle의 조립·해·복원 결과를 명시적 단위·축·i/j·부호
  normalization 뒤 같은 네 결과군으로 비교
- 희소 경로 두 번의 의미 결과 hash exact match
- 30초 case runtime, 45초 worker wall time, 1 GiB peak RSS 한도
- child crash와 OOM 부재

조건수는 기존 공개 결과가 256식을 넘으면 exact 값을 생성하지 않는 정책을
유지한다. 이 profile은 2,048 방정식 제한 안에서 대칭 dense 고유치 진단으로
최소·최대 대수 고유치와 잔차를 기록하고 `1e9` 이하를 요구한다. 이
진단은 sparse 제품 경로와 별도이며, 제품 solver의 범용 exact-condition 권한을
넓히지 않는다.

## 실행과 증거

로컬 검증은 다음 명령으로 수행한다.

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
PYTHONHASHSEED=0 PYTHONPATH=src \
python3 -m pytest -q tests/test_medium_scale_current_source_execution.py

python3 scripts/run_medium_scale_current_source_profile.py \
  --source-sha "$(git rev-parse HEAD)"
```

두 번째 명령은 tracked tree가 깨끗하지 않으면 fail-closed한다. 출력 receipt는
`artifacts/medium-scale/current-source/` 아래의 비추적 runtime artifact다.
`Medium Scale Current Source` workflow는 main의 exact SHA에서 hash-locked Python
환경으로 이를 재실행하고 GitHub provenance attestation과 함께 90일 보존한다.

의미 validator는 동일 runtime에서 결정적 모델·조립·조건·dense/sparse 결과와
독립 내부 oracle을 재실행해 영수증과 비교한다. Oracle receipt는 정확한 oracle
source bytes, canonical model checksum, raw/normalized result hash, normalization
policy와 residual을 결합한다. Validator는 runtime·memory 측정치의 순서 관계와 전체
payload digest도 확인한다. 다른 환경에서 다운로드한 영수증의 진정성은 자체
digest만으로 확립하지 않으며, exact source·workflow·subject digest를 결합한
Sigstore attestation 검증이 필수다.

각 case의 runtime과 peak-memory 필드는
`non_authoritative_pre_attestation_observation`으로 표시된다. 측정 API는
실행 platform과 일치해야 하지만, 관측 수치 자체는
`verified_exact_source_github_provenance_attestation`을 검증하기 전에는 권위가 없다.
Worker가 timeout·signal·nonzero exit·invalid JSON·identity/schema 오류를 내면
유형·crash/OOM·wall-limit·blocker가 서로 결합된 blocked receipt로
정규화한다. Workflow는 실행 실패 시에도 생성된 blocked receipt를
`always()` artifact로 보존하며, 그 경우 attestation과 기술 통과를 수행하지 않는다.

## 만들지 않는 주장

5/5 기술 실행은 기존 `medium-benchmark-corpus-readiness.v1`의 과학적 5/5가
아니다. Dense와 sparse는 같은 제품 구현이다. 별도 내부 oracle은 production
assembly·element·solver code를 사용하지 않는 두 번째 구현이지만 같은 저장소와
operator가 만든 differential reference이므로 외부 reference solver나 독립 V&V가
아니다. 생성 모델에는 source/license receipt, OpenSees와 제2 solver 결과, 완전한
artifact chain, 엔지니어 PASS/REVIEW가 없다. 따라서 다음 값은 명시적으로
계속 0/5다.

- scientific medium benchmark credit
- Native medium product authority

Native 승격에는 별도 sparse production profile이 필요하다. 과학적 승격에는
실제 다섯 구조형식에서 OpenSees와 OpenSees 이외 reference, normalization,
residual/reaction/local-force 비교, license/use 판단과 engineer decision이 모두
필요하다.
