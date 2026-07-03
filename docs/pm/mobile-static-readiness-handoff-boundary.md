# Mobile / Static Readiness Handoff Boundary

> Status: **mobile-safe PM/CTO boundary document**  
> Scope: what can be done from mobile / GitHub web / connector-only development  
> This document does **not** execute tests, mutate protected evidence, delete files, run ROCm/HIP probes, dispatch CI, or promote any product readiness claim.

## 1. Why this boundary exists

Current development is being coordinated from a mobile environment rather than a local workstation, CI runner, or ROCm/HIP GPU host. That changes what is safe to do.

Mobile-safe work is useful for PM/CTO handoff, release-scope planning, owner-decision preparation, and non-promoting documentation. It is not suitable for executing solvers, regenerating protected evidence, deleting files, or proving runtime/GPU readiness.

## 2. Mobile-safe work

The following work is safe from mobile / GitHub web / connector-only context:

| Work type | Mobile-safe? | Notes |
|---|---:|---|
| PM handoff documentation | yes | Markdown docs, checklists, acceptance criteria, owner packets. |
| CTO handoff documentation | yes | Required receipts, runtime blockers, command skeletons. |
| Static owner-decision matrix | yes | Recommendations only, no deletion/extraction. |
| Template creation | yes | Templates must state they are not approval or closure evidence. |
| PR body cleanup | yes | Clarify scope, validation, claim boundary. |
| Codex `/goal` handoff | yes | Good mobile output because execution is deferred. |
| Non-promoting claim-boundary review | yes | Safe if no tracked evidence is promoted. |
| Readiness discrepancy analysis | yes | Safe if it does not rewrite protected receipts. |

## 3. Work that must be deferred to local PC / CI / GPU

| Work type | Required environment | Why mobile is insufficient |
|---|---|---|
| Python / pytest execution | Local PC or CI | Requires runtime and dependency resolution. |
| npm / Playwright execution | Local PC or CI | Requires node/browser runtime. |
| Product readiness snapshot regeneration | Local PC / controlled CI | May rewrite tracked protected evidence. |
| Structural scope audit rerun | Local PC / controlled CI | Requires repository checkout and generated outputs. |
| File delete/extract operations | Local PC after owner approval | Destructive or repository-restructuring actions. |
| ROCm/HIP runtime proof | GPU host | Requires `/dev/kfd`, `/dev/dri`, ROCm/HIP runtime. |
| G1 residual/Jacobian probes | Local/GPU host | Requires solver runtime, checkpoint files, large-model execution. |
| Full-load 1.0 checkpoint generation | Local/GPU host | Heavy continuation run and solver evidence. |
| External benchmark receipt creation | External owner/operator | Requires external receipt or third-party closure evidence. |
| Customer shadow evidence | Customer/human owner | Must use real customer-retained metadata; no synthetic substitution. |

## 4. Mobile-safe acceptance criteria for PR #63

PR #63 should be considered mobile-complete when:

```text
- It contains PM handoff docs only.
- It contains owner-decision guidance and/or templates only.
- It contains Codex `/goal` handoffs for later local/GPU execution.
- It explicitly says no tests were run from mobile.
- It explicitly says no protected evidence was regenerated.
- It explicitly says no G1, Developer Preview, release, paid pilot, limited commercial, or GA readiness was promoted.
```

## 5. Claims allowed from mobile work

Allowed:

```text
PM/CTO handoff package prepared
mobile/static execution boundary clarified
owner-decision template available
Codex/local/GPU next goals documented
PR is documentation-only and non-promoting
```

Not allowed:

```text
G1 closed
Developer Preview ready
release_ready=true
paid_pilot_ready=true
limited_commercial_ready=true
production ROCm/HIP residency proven
full-load 1.0 checkpoint generated
medium/large model gates executed
CI streak evidence collected
customer shadow completed
```

## 6. Recommended mobile workflow

```text
1. Keep all changes in docs/templates/checklists.
2. Mark any execution as deferred to local PC, CI, GPU host, external owner, or human observer.
3. Keep PR as documentation-only unless the user explicitly asks for code or tracked evidence changes.
4. If the PR is ready for review, ensure the body states no runtime validation was performed.
5. Do not merge over failing or unknown product gates unless the team explicitly accepts documentation-only scope.
```

## 7. Claim boundary

This boundary document is not an execution receipt. It does not close any readiness gate. It exists to prevent mobile/static coordination work from being mistaken for local, CI, GPU, external benchmark, customer, or release evidence.
