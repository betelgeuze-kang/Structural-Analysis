# Codex Goal Orchestration

이 문서는 명시적으로 worker orchestration이나 readiness/gap-closure 작업을 요청받았을 때만 참조한다. 일반 코드 수정, 질문, 디버깅에서는 `AGENTS.md`의 기본 경량 모드를 따르고 `.betelgeuze/` 상태를 자동으로 읽지 않는다.

이 저장소에서는 별도 자동 실행기나 로컬 runner를 실행하지 않는다. 반복 진행은 Codex의 goal 기능이 맡는다. 기본 코드 개선 파이프라인은 Kiro `opus-4.8` 설계, Cursor `composer-2.5` 구현, Codex `gpt-5.5` `xhigh` 검증이다. Codex가 Kiro 설계 slice를 실행할 때는 `scripts/ai-run-kiro-design.sh`를 기본 진입점으로 사용한다. 이 wrapper는 먼저 `scripts/ai-worker-kiro.sh --check`로 Kiro design prompt가 `opus-4.8`, design-only no-edit boundary, readiness-closure 금지 boundary를 명시하는지 확인한 뒤, 같은 worker로 `kiro chat --mode ask`를 launch한다. `scripts/ai-worker-kiro.sh`도 일반 실행마다 동일한 자동 prelaunch check를 다시 수행하고 receipt에 남긴다. wrapper는 Kiro CLI가 stdout을 emit하면 같은 run의 `.kiro-design.md` 파일로 자동 저장하고 receipt에 `headless_stdout_capture=true`, `design_output_path`, `design_output_sha256`를 기록한다. 현재 로컬 Kiro `chat` 명령은 GUI launch 후 stdout `0`바이트로 끝날 수 있으므로, 각 launch receipt의 `headless_stdout_capture` 값이 실제 자동 수집 여부의 권위 있는 증거다. Cursor auto와 OpenCode worker는 필요한 구현 조각만 처리하는 worker로 사용한다. 현재 OpenCode task assignment는 OpenCode 실행 대신 같은 prompt file을 Cursor `composer-2.5`에 바로 넘긴다.

```text
사용자가 Codex goal에 목표 입력
-> Codex가 목표를 추적하며 acceptance와 검증 경계 유지
-> 필요할 때 Kiro opus-4.8 compact design prompt 생성
-> scripts/ai-run-kiro-design.sh <kiro-prompt-file> 로 opus-4.8/no-edit prompt 검증 후 Kiro chat launch
-> Codex가 설계를 짧게 검토하고 Cursor 구현 prompt 생성
-> scripts/ai-worker-cursor.sh <prompt-file>
   또는 scripts/ai-worker-opencode.sh <prompt-file>
-> scripts/ai-verify.sh
-> Codex gpt-5.5 xhigh가 diff, evidence, claim boundary 리뷰
-> Codex goal 기능으로 계속 진행
```

## 역할

```text
Codex goal: 목표 추적, 설계, 리뷰, 최종 판단
Kiro design: `opus-4.8` compact design prompt를 wrapper로 실행; 파일 수정, readiness closure claim, 긴 설계문 금지; stdout capture가 있으면 `.kiro-design.md`를 Codex 검토 입력으로 사용하고, capture가 없으면 launch receipt만 증거로 취급
Cursor auto: scoped 구현, focused edit, test-fix loop, 현재 에디터 상태, 선택 영역, IDE affordance가 중요한 구현 slice 수행
OpenCode worker entrypoint: 호환용 wrapper로 남겨 두되 현재 assignment는 Cursor `composer-2.5`로 즉시 라우팅
Internal Codex subagent fallback: Cursor worker와 host bridge가 모두 불가할 때만 scoped 구현 worker로 사용하며 모델은 `gpt-5.4-mini`, reasoning effort는 `xhigh`
Codex verification: `gpt-5.5` `xhigh`로 최종 diff/evidence/claim-boundary/release-gate 판단
ai-verify.sh: 오케스트레이션 smoke 검증
Human owner: push, merge, deploy, release, billing, production mutation 승인
```

## 현재 목표에 붙이는 방식

현재 제품화 목표는 `docs/commercial-structural-solver-product-gap-ledger.md`와 `docs/structural-analysis-ai-engine-gap-ledger.md`의 G1-G10, AI-G1-AI-G10 readiness gap을 권위 있는 증거로 닫는 것이다.

- Codex는 `.betelgeuze/intent_spec.md`, `.betelgeuze/project_contract.yaml`, gap ledger, status reporter, productization receipt를 기준으로 claim boundary를 판단한다.
- 코드 개선 slice의 기본 흐름은 Kiro design brief -> Cursor implementation -> Codex verification이다.
- Kiro 설계 산출물은 compact brief로 제한하고, Codex가 다시 읽을 토큰 비용을 줄이기 위해 목표, blocker, 후보 파일, 구현 순서, 검증 기준, 위험 경계만 포함한다.
- Worker에게는 한 번에 하나의 구현 slice만 맡긴다.
- Codex TASK는 짧게 유지하며 목표, 범위, 파일 후보, 검증 기준만 담는다.
- Worker는 할당된 slice의 탐색, 구현, focused test 실행, 요약까지 책임진다.
- Worker 출력은 변경 파일, 테스트 결과, 실패 테스트명, 핵심 diff 요약, blocker로 제한하며 `scripts/validate-ai-worker-output.mjs`가 이 형식을 검사한다.
- Codex는 전체 worker 로그를 기본으로 읽지 않는다. 필요할 때만 특정 파일, 실패 테스트, diff를 본다.
- 50+ LOC 구현/기계적 수정, 3개 이상 파일, 10분 이상 탐색 예상, 넓은 grep/sweep, 반복 테스트 수정, 긴 로그/evidence/readiness-gate 진단은 worker 후보로 먼저 분류한다.
- 단순 문서, 작은 테스트, 명확한 수정은 위 worker 후보 조건에 걸릴 때만 위임한다.
- scoped 탐색, 대량 기계적 수정, 반복 테스트 수정, 다파일 리팩터링을 worker에 위임한다.
- partial/proxy/fallback/external-blocked 상태는 문서나 리포트에서 숨기지 않는다.

## Worker 실행

Kiro 설계가 필요하면 Codex가 run-specific compact design prompt를 만든다. 이 prompt는 `docs/ai/prompts/kiro_design_slice.md` 형식을 따른다. 그 다음 check-before-launch wrapper를 실행한다.

```bash
./scripts/ai-run-kiro-design.sh docs/ai/dispatch/<kiro-task-id>.md
```

`scripts/ai-run-kiro-design.sh`는 `scripts/ai-worker-kiro.sh --check <prompt>`를 먼저 실행하고, 통과한 prompt만 launch한다. 내부 Kiro worker는 prompt 안의 `opus-4.8` target, design-only no-edit boundary, readiness-closure 금지 boundary를 일반 실행의 자동 prelaunch check로 다시 검사하고 Kiro chat을 launch한다. 이 검사는 `wrapper_prelaunch_check_passed`와 `equivalent_prompt_check_command`로 launch receipt에 남는다. `./scripts/ai-worker-kiro.sh --check docs/ai/prompts/kiro_design_slice.md`는 Kiro CLI를 실행하지 않고 같은 검증만 수행하므로 preflight와 verify에서 자동으로 확인할 수 있다. wrapper는 Kiro stdout이 non-empty일 때 설계 결과를 `.kiro-design.md`로 저장한다. launch receipt의 `headless_stdout_capture=true`와 `codex_consumable_design_output=true`가 있어야 Codex가 Kiro design을 자동 수집한 것으로 취급한다. stdout이 없으면 launch receipt는 호출/검증 증거로만 사용하고 readiness closure나 Codex-consumed design evidence로 승격하지 않는다. Kiro는 설계만 작성하며 파일을 수정하지 않는다.

Cursor worker가 필요하면 Codex가 run-specific prompt를 만들고 다음 형태로 실행한다.

```bash
./scripts/ai-worker-cursor.sh docs/ai/dispatch/<task-id>.md
```

OpenCode worker가 필요하면 다음 형태로 실행한다. 현재 이 wrapper는 OpenCode를 실행하지 않고 Cursor `composer-2.5`에 같은 prompt file을 넘긴다. `scripts/build_ai_orchestration_preflight_report.py`는 이 assignment routing을 별도 evidence로 기록한다.

```bash
./scripts/ai-worker-opencode.sh docs/ai/dispatch/<task-id>.md
```

OpenCode assignment routing의 Cursor 모델은 기본 `composer-2.5`이며, 필요하면 `AI_WORKER_OPENCODE_ASSIGNMENT_CURSOR_MODEL`로 바꿀 수 있다. 이는 같은 scoped slice의 worker 선택만 바꾸는 것이며, Codex가 여전히 diff review와 최종 acceptance를 맡는다.

Codex terminal sandbox에서 `api2.cursor.sh` DNS/network access가 막힌 경우에는 host terminal에서 다음 bridge를 한 번 켜 둔다.

```bash
./scripts/ai-worker-cursor-host-bridge.sh
```

이 bridge가 실행 중이면 `scripts/ai-worker-cursor.sh`가 Cursor API DNS 실패를 감지했을 때 `.betelgeuze/cursor_worker_bridge/` queue에 job을 넣고, host bridge가 같은 prompt file을 Cursor Agent로 실행한 뒤 결과 raw output을 돌려준다. Codex wrapper는 이후 기존과 같이 validator를 통과한 요약만 출력한다.

Cursor worker와 host bridge가 모두 불가한 상태에서 Codex가 내부 서브에이전트로 구현 fallback을 해야 하면, 내부 subagent는 `agent_type=worker`, `model=gpt-5.4-mini`, `reasoning_effort=xhigh`로만 호출한다. 이 fallback은 Cursor를 대체하는 마지막 scoped implementation 경로이며, OpenCode assignment routing이나 Codex의 diff review, verification, final acceptance 책임을 바꾸지 않는다.

둘 다 같은 목표 안에서 쓸 수 있지만, 동시에 여러 worker를 돌리지 않는다.

Wrapper는 worker 원본 출력을 먼저 `.betelgeuze/worker_outputs/`에 캡처하고, validator를 통과한 요약만 stdout에 출력한다. 유효한 실행의 raw output은 기본적으로 삭제되며, 디버깅용 보존이 필요할 때만 `AI_WORKER_KEEP_RAW=1`을 사용한다.

## TASK 형식

Worker에게 넘기는 prompt는 다음 네 필드만 상세화한다.

```text
Goal: <무엇을 끝낼지>
Scope: <허용되는 작업 범위와 금지 범위>
Candidate files: <우선 확인할 파일 후보>
Verification criteria: <통과해야 할 테스트/게이트/증거 기준>
```

## 검증

```bash
./scripts/ai-preflight.sh
./scripts/ai-verify.sh
```

`ai-verify.sh`는 오케스트레이션 파일의 smoke 검증이다. 제품 readiness 변경을 완료로 판단할 때는 별도로 `pytest`, `npm run build`, `python -m compileall .`, 그리고 관련 gap/status/readiness gate를 실행한다.

## 안전 경계

자동으로 실행하지 않는다.

```text
git push
merge
deploy
publish/release
production migration
payment/refund/billing mutation
cloud resource mutation
secret rotation
permission/OAuth scope escalation
destructive data operation
```
