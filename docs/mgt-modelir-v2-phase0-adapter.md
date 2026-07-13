# MGT → ModelIR v2 Phase 0 Adapter Contract

- Subset contract: `midas_mgt_phase0_linear_frame.v1`
- Audit schema: `structural-analysis-mgt-model-ir-v2-audit.v1`
- Claim boundary: `phase0_supported_subset_import_audit_not_full_midas_interoperability`
- Model contract: [ModelIR v2 Phase 0](modelir-v2-contract.md)

이 문서는 MIDAS MGT 전체 호환성이 아니라 Engine v2 walking skeleton에 필요한 최소 선형 3D frame subset의 import, 단위 정규화, 출처 감사 계약을 고정한다. Schema-valid, solver-ready, MIDAS와의 수치 동치는 서로 다른 주장이다.

## v1과 v2의 공존 경계

| 경로 | 역할 | 현재 주장 |
| --- | --- | --- |
| [v1 MGT loader](../src/structural_analysis/io/midas/loader.py) | `CanonicalModel` topology, model-health, provenance용 thin adapter | 유지. MGT 하중 조립이나 완전한 solver closure를 주장하지 않음 |
| [v1 core API](../src/structural_analysis/api/core.py) | `.mgt`를 v1 `load_midas_mgt()`로 routing | 기존 API/CLI 기본 경로로 유지 |
| [v2 package](../src/structural_analysis/io/midas/v2/) | lossless source document, strict subset, ModelIR v2/audit 경계 | v1의 암묵적 upgrade가 아닌 별도 opt-in 경로 |

v2가 준비되었다는 사실만으로 `load_model()`의 `.mgt` routing을 바꾸지 않는다. 전환은 독립 API, fixture, roundtrip audit, solver preflight가 모두 검증된 후의 별도 변경이다.

## Lossless lexer와 source span

[lexer](../src/structural_analysis/io/midas/v2/lexer.py)와 [immutable token model](../src/structural_analysis/io/midas/v2/tokens.py)은 의미 변환 전의 출처 계약이다.

- UTF-8과 UTF-8 BOM을 구분하고 원본 `raw_bytes`, byte count, SHA-256를 보존한다.
- LF, CRLF, CR, mixed, newline 없음과 physical-line count를 별도로 기록한다. Lexer enum은 소문자 value, audit JSON은 `LF|CRLF|CR|MIXED|NONE`으로 정규화한다.
- `SourceSpan` line은 1-based inclusive, byte range는 0-based half-open `[byte_start, byte_end)`이다.
- `PhysicalLine.raw`는 해당 newline을 포함한 정확한 bytes를 보존한다.
- `;` 주석은 quoted text 밖에서만 분리하며, 파싱에서 제외해도 raw fragment는 유지한다.
- `*HEADER,arg1,arg2` 이름은 대문자로 정규화하고 각 이름별 occurrence index를 1부터 부여한다. Header 전 preamble은 synthetic `ROOT` occurrence `0`으로 보존될 수 있다.
- 끝의 `\`로 연결된 physical line은 하나의 `LogicalRow`로 합친다. 합친 row에도 전체 line span, 각 raw fragment, fragment SHA-256, 주석이 남는다.
- Continuation 중 새 header나 EOF를 만나면 `MGT_UNTERMINATED_CONTINUATION`을 남기고, 불완전 row를 조용히 버리지 않는다.
- `*ENDDATA` 이후 비주석 콘텐츠는 `MGT_CONTENT_AFTER_ENDDATA`로 진단하며 원본은 보존한다.
- 알 수 없는 header도 block으로 보존한다. 보존은 지원을 의미하지 않으며, 의미 분류는 fail-closed이다.

Lexer의 SHA-256 field는 64자 hex이고, [audit schema](../src/structural_analysis/schemas/mgt_model_ir_v2_audit.schema.json)의 hash는 `sha256:<64 hex>` 형식이다. Adapter가 audit를 만들 때 prefix를 명시적으로 추가해야 한다.

## Phase 0 supported subset

아래 모든 제한을 만족한 경우에만 `midas_mgt_phase0_linear_frame.v1`으로 solver-ready 판정할 수 있다. 정상적으로 출처 값을 SI ModelIR로 변환하므로 card-level 기본 분류는 `SUPPORTED_NORMALIZED`이다.

행 단위 위치·arity·값 검증의 정본은 [strict grammar](../src/structural_analysis/io/midas/v2/grammar.py)이다. Grammar에서 row를 parse했다는 사실과 document-level ID/context/reference 검증을 통과했다는 사실은 다르다.

| Card | Phase 0에서 허용하는 의미 |
| --- | --- |
| `VERSION` | 정확히 하나의 data row이며 현재 dialect gate는 `9.3.0`이다. 다른 version의 positional 의미를 추정하지 않는다. |
| `UNIT` | 하나의 force/length 단위 계약. 현 grammar와 canonical writer의 import/역투영 범위는 `N|KN|MN`, `M|MM|CM`이다. Heat/temperature token은 선형 frame solver 입력이 아니다. |
| `STRUCTYPE` | 정확히 10 fields. `iSTYP,iMASS,iSMAS`는 integer, 다섯 flag는 `YES|NO`, gravity는 positive finite, reference temperature는 finite여야 한다. Grammar는 각 field를 보존하지만 parse 성공만으로 모든 flag 조합의 solver 지원을 주장하지 않는다. Gravity는 unit-weight→mass-density 정규화에 사용한다. |
| `NODE` | positive unique ID와 finite `X,Y,Z`. 좌표를 m로 변환한다. |
| `MATERIAL` | 정확히 15 fields의 explicit data selector `2` isotropic linear-elastic row. `TYPE=CONC|STEEL|USER`, `PLAST` empty, `bMASS=NO`, `MASS=0`, positive `E`, `-1<ν<0.5`, non-negative force/length³ unit weight가 필수다. DB selector, named-only, SRC, nonlinear material은 범위 밖이다. |
| `SECTION` | 정확히 24 fields의 `DBUSER`, centered `CC`, `bSD=YES`, `bWE=NO`, shape `SB`, selector `2`, positive `H=D1,B=D2` solid rectangle. Offset-related 값과 `D3…D10`은 모두 zero여야 하며 단면 특성은 아래 고정 식으로 파생한다. |
| `ELEMENT` | 정확히 `ID, BEAM, MAT, SEC, NODE-I, NODE-J, ANGLE, iSUB`인 8-field BEAM. Euler–Bernoulli 3D frame으로 mapping하며 material/section/node 참조, 서로 다른 두 node, 지원되는 `iSUB`를 검증한다. Offset/release는 영으로 생성한다. |
| `CONSTRAINT` | positive node ID의 공백 목록 또는 `to`/`by` range, 6자 `0|1` DOF mask, optional group. 오름·내림차순을 지원하지만 중복 node와 zero/non-positive ID는 거부한다. `1`인 DOF에 영 prescribed value를 생성한다. |
| `STLDCASE` | unique static-load-case name, type, optional description. Phase 0에서는 linear-static load pattern ID를 생성한다. |
| `USE-STLD` | 이후 load card에 적용할 active static-load-case context. 기존 `STLDCASE`를 참조해야 한다. |
| `CONLOAD` | active `USE-STLD` context 아래의 node ID/range와 `FX,FY,FZ,MX,MY,MZ`, optional group/structure-type name. 하중 node와 load case 참조를 검증한다. |

`VERSION`은 field 의미를 결정하므로 `SUPPORTED_NORMALIZED`와 명시적 dialect gate를 적용한다. 명시적으로 allowlist된 color card만 [classification vocabulary](../src/structural_analysis/io/midas/v2/classification.py)에서 `PRESERVED_NONANALYTIC`일 수 있다. `ENDDATA`는 모델 물리가 아닌 문서 종료 계약이다. 이들은 solver capability를 늘리지 않는다.

표본 [minimal frame fixture](../tests/fixtures/midas_v2/minimal_frame_normalized.mgt)는 explicit selector-2 material, `DBUSER/SB` 단면, 8-field BEAM, 고정 경계, 두 개의 `USE-STLD`–`CONLOAD` context를 담는다. 이 fixture의 모양을 지원한다는 것이 일반 MIDAS model을 지원한다는 뜻은 아니다.

## SI 정규화 차원식

소스 값을 `q_src`, ModelIR SI 값을 `q_SI`라 하고 다음 scale을 사용한다.

- `L = length_to_m`
- `F = force_to_n`
- `T = time_to_s = 1 s`
- coherent mass scale `M = F T² / L`
- MGT angle degree의 rotation scale `R = π / 180`

| 물리량 | 변환 |
| --- | --- |
| 좌표, 단면 치수 | `x_SI = x_src L` |
| 면적, shear area | `A_SI = A_src L²` |
| 단면 2차 모멘트, torsional constant | `I_SI = I_src L⁴`, `J_SI = J_src L⁴` |
| 힘 | `P_SI = P_src F` |
| 모멘트 | `M_SI = M_src F L` |
| 탄성계수 | `E_SI = E_src F / L²` |
| 중력가속도 | `g_SI = g_src L / T²` |
| unit weight | `γ_SI = γ_src F / L³` |
| 질량밀도 | `ρ_SI = γ_SI / g_SI` |
| BEAM local-axis angle | `θ_SI = θ_deg R` |

예를 들어 fixture의 `KN, M`, `E=2.0e8`, `γ=78.5`, `g=10`은 각각 `E=2.0e11 Pa`, `γ=78500 N/m³`, `ρ=7850 kg/m³`로 정규화된다. Poisson ratio는 무차원이며 scale을 적용하지 않는다.

## DBUSER/SB 직사각형 파생 계약

Source row에는 `H,B`만 있고 ModelIR `frame_3d` section에는 `A,Iy,Iz,J,Ay,Az`가 필요하므로, 다음 값은 `SUPPORTED_EXACT`가 아닌 `SUPPORTED_NORMALIZED`이다. `H` 및 `B`를 먼저 m로 변환하고 `H`는 local-z, `B`는 local-y 치수로 정의한다.

```text
A  = B H
Iy = B H³ / 12
Iz = H B³ / 12
Ay = Az = 5 A / 6

a = max(H, B), b = min(H, B)
J = (a b³ / 3) [1 - (192 b / (π⁵ a))
                    Σ(n in fixed finite odd-term set)
                    tanh(n π a / (2 b)) / n⁵]
```

`J`는 무한 급수의 근삿값을 구하는 deterministic finite odd-term Saint-Venant series다. [현 grammar 구현](../src/structural_analysis/io/midas/v2/grammar.py)은 `n=1,3,…,401`(최대 201 terms)을 순서대로 더하고, 더한 현재 term이 `1e-16`보다 작으면 조기 종료한다. 이 term 순서·상한·종료 규칙은 semantic hash의 일부이므로 adapter version 없이 바꾸지 않는다. `Ay,Az`는 schema/buffer completeness를 위한 derived metadata이며 현 Phase 0 Euler–Bernoulli operator의 stiffness에는 사용되지 않는다.

이 파생은 `DBUSER/SB` solid rectangle에 대한 v2 adapter 규칙이지 MIDAS의 모든 section database, taper, composite, SRC, user property, shear/torsion 내부 알고리즘을 exact하게 재현한다는 주장이 아니다. 반드시 source mapping에 치수 단위 변환과 section-property derivation을 transformation으로 남겨야 한다.

## Fail-closed 범위

[default classification](../src/structural_analysis/io/midas/v2/classification.py)은 알 수 없는 card를 무해하다고 간주하지 않는다.

- `OFFSET`, `SELFWEIGHT`, `PRESSURE`, `BEAMLOAD`는 보존하되 해석 준비 상태를 `BLOCKED_UNSUPPORTED`로 만든다.
- 같은 규칙을 `ELASTICLINK`, `LOADCASE`, `LOADCOMB`, `NODALMASS`, `SPRING`, `STORY-ECCEN`, `THICKNESS`에 적용한다.
- 모든 unknown card는 `MGT_UNKNOWN_CARD_FAIL_CLOSED:<CARD>`로 blocking한다. Raw block 보존은 지원 판정이 아니다.
- `CONLOAD`가 `USE-STLD`없이 나오면 `BLOCKED_CONTEXT_MISSING`이다. [Missing-context fixture](../tests/fixtures/midas_v2/blocked_missing_load_context.mgt)가 이 경계를 고정한다.
- [Offset fixture](../tests/fixtures/midas_v2/blocked_offset.mgt)처럼 supported subset과 unsupported analytical card가 함께 있어도 전체 import를 ready로 승격하지 않는다.
- Malformed row, non-finite value, invalid mask/range는 `BLOCKED_INVALID_SYNTAX`, duplicate ID는 `BLOCKED_DUPLICATE_ID`, dangling node/material/section/load-case reference는 `BLOCKED_DANGLING_REFERENCE`다.

`STRUCTYPE`의 gravity/self-weight 관련 flag를 읽었다고 해서 `SELFWEIGHT` load card를 조립했다고 간주하지 않는다. Phase 0 load pattern의 `self_weight` vector는 zero이며 explicit `SELFWEIGHT`는 blocking한다.

## Audit와 semantic roundtrip

[audit implementation](../src/structural_analysis/io/midas/v2/audit.py)은 [Draft 2020-12 schema](../src/structural_analysis/schemas/mgt_model_ir_v2_audit.schema.json)를 검증한 후 canonical JSON과 그 SHA-256를 immutable envelope로 만든다. Audit에는 반드시 다음이 있어야 한다.

- source ref/hash/byte·line·encoding·newline identity
- adapter ID/version/subset contract
- `ready|blocked` status와 ModelIR contract/readiness/hash
- block occurrence, header line, active load case, card disposition/reason
- 각 logical source record의 line span/raw hash에서 ModelIR JSON pointer로 가는 source mapping
- duplicate/dangling reference audit
- 지원 subset source hash, reverse-projection hash, semantic-equivalence, silent-loss count, target-pointer error count
- `linear_static_ready`, `solver_buffers_packable`, `supported_subset_roundtrip_ready`
- 진단, disposition별 count, 고정 claim boundary

Disposition vocabulary는 `SUPPORTED_EXACT`, `SUPPORTED_NORMALIZED`, `PRESERVED_NONANALYTIC`, `BLOCKED_UNSUPPORTED`, `BLOCKED_INVALID_SYNTAX`, `BLOCKED_DUPLICATE_ID`, `BLOCKED_DANGLING_REFERENCE`, `BLOCKED_CONTEXT_MISSING`이다. 모든 logical data row는 정확히 하나의 disposition을 가져야 하며 `silent_loss_count`는 ready에서 0이어야 한다.

[canonical subset writer](../src/structural_analysis/io/midas/v2/writer.py)는 analysis-ready ModelIR, `midas_mgt` provenance, 일치하는 subset/version/unit contract, unique source ID/load-case name, zero offset/release/prescribed value/self-weight, empty combination/time/stage, 허용된 roundtrip status를 재검증하고 canonical MGT를 만든다. 보존한 `H/B`에서 여섯 단면 물성을 다시 산출해 canonical `A/Iy/Iz/J/Ay/Az`와 일치하지 않으면 차단한다. CR/LF/NUL/semicolon을 포함한 source text도 header/comment injection을 막기 위해 차단한다. Solver semantic hash는 ModelIR에서 source ID와 namespaced extension을 제외한 물리 projection을 canonical JSON으로 직렬화해 계산한다.

Roundtrip pass의 의미는 다음과 같다.

```text
MGT supported subset
  → SI ModelIR v2
  → canonical supported-subset MGT
  → SI ModelIR v2
  → solver semantic projection hash equality
```

이것은 byte-identical MGT 재생성, 주석/포맷의 동일성, MIDAS 실행 결과 parity를 의미하지 않는다. Source byte hash와 semantic hash는 결코 혼용하지 않는다. Schema validation 단독도 hash equality, pointer 존재, silent-loss 0을 실행적으로 증명하지 않으므로 adapter orchestration이 이 invariant를 검증해야 한다.

Audit 계약은 [focused schema tests](../tests/test_midas_v2_audit.py), lexer/source preservation은 [focused lexer tests](../tests/test_midas_v2_lexer.py), SI 차원·arity·rectangle series는 [focused grammar tests](../tests/test_midas_v2_grammar.py), end-to-end import/buffer/CPU/CLI 경계는 [focused import tests](../tests/test_midas_v2_import.py)에서 검증한다.

## 현재 사용 경계

현재 public v2 export는 lossless lexer와 end-to-end strict import를 분리한다.

```python
from structural_analysis.io.midas.v2 import import_mgt_v2

result = import_mgt_v2("model.mgt")
print(result.ready, result.audit.status)
if result.model_ir is not None:
    print(result.model_ir.content_hash)
```

`require_ready=True`이면 blocked audit를 포함한 `MGTImportBlockedError`를 발생시킨다. 기존 `structural-analysis` CLI의 `.mgt` routing은 여전히 v1이며 변경하지 않았다. 별도 스크립트는 opt-in 변환 경로다.

```bash
python3 scripts/convert_mgt_to_model_ir_v2.py model.mgt \
  --model-ir-out model.ir.v2.json \
  --audit-out model.mgt.audit.json \
  --canonical-mgt-out model.canonical.mgt
```

Ready이면 exit `0`, 문법·참조·미지원 기능으로 blocked이면 audit를 기록하고 exit `2`, I/O/UTF-8 decode 실패는 exit `3`이다. Blocked 결과에 canonical MGT를 생성하지 않는다.

## 주장하지 않는 것

이 Phase 0 adapter는 다음을 증명하지 않는다.

- MIDAS/Gen MGT 전체 grammar 및 모든 version의 exact 호환성
- Shell, solid, truss, nonlinear, staged construction, contact, spectrum/time-history, design card import
- Offset, release, rigid link, self-weight, member/distributed/surface load 조립
- MIDAS database section/material 값과 내부 section-property 산출의 exact 재현
- MIDAS, ETABS, OpenSees 결과와의 외부 수치 parity
- HIP/ROCm 가속, 성능, 상용 release readiness

이 항목들은 각각 별도 grammar, operator, benchmark, external receipt가 있을 때만 승격할 수 있다.
