# Local-free PM release blocker closure pack

Purpose: prepare the remaining PM release blockers for closure without local PC, self-hosted runner, human observer, or legal/product-owner authority.

This packet is **non-promoting**. It does not create CI streak evidence, human UX evidence, license approval, or full release readiness.

## Current state

PM milestones are complete, but full release readiness is still partial.

Known current position:

- PM milestones: `5/5`
- PM release areas: `13/16`
- PM release gate stage progress: `85.7%`
- Full release gate: not ready

Open release-area blockers:

1. `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`
2. `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing`
3. `ux::human_new_user_observation_missing_or_failed`
4. `ux::human_new_user_30min_sample_evidence_missing`
5. `security::license_status_not_configured`

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json`
- `implementation/phase1/release_evidence/productization/pm_release_blocker_closure_board.json`
- `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `implementation/phase1/release_evidence/productization/license_status_closure_report.json`

## Closure tracks

### Track A — PR CI 30-run streak

Required evidence:

- 30 consecutive PR CI runs pass.
- Runs are tied to the tracked self-hosted runner policy.
- No GitHub-hosted fallback is counted unless the policy is explicitly changed and approved.
- Evidence includes run ids, branch/ref, workflow names, conclusion, timestamps, and runner labels.

Local/runner dependency:

- Requires online self-hosted GitHub Actions runner and actual workflow execution.

Non-local prep this packet provides:

- Defines evidence content and claim boundary.
- Prevents counting synthetic/manual rows as CI streak evidence.

### Track B — Nightly CI 30-run streak

Required evidence:

- 30 consecutive nightly full-quality runs pass.
- Workflow metadata confirms intended runner labels.
- Failures or skipped starts reset or explicitly segment the streak.

Local/runner dependency:

- Requires online self-hosted runner and actual nightly workflow runs.

### Track C — Human new-user UX observation

Required evidence:

- Real human participant who is new to the product.
- Workflow steps observed: import, model health, analysis setup, run/monitor, compare/report.
- Completion in <= 30 minutes.
- Separate evidence reference that is not the generated gate artifact itself.
- Approval decision accepted/pass/signed/approved_for_release.

Local/human dependency:

- Requires a real human observer and participant.

### Track D — License/product approval

Required evidence:

- Active/approved/valid status.
- Tier: `paid-pilot` or `limited-commercial`.
- License id, issuer/approver, approver role, approval ref, approved_at timestamp, evidence ref, product scope, expiry/perpetual approval.
- Product scope includes review-assist, specified structure families, specified workflows, and engine/reviewer evidence package.

External dependency:

- Requires product owner or legal counsel approval.

## Recommended execution order

1. Keep the now-closed structural-scope audit green (`86/86` owner delete decisions, current matching paths `0`).
2. Attach license approval evidence.
3. Attach human UX observation evidence.
4. Bring self-hosted runner online and record PR/nightly streaks.
5. Regenerate PM release gate report.
6. Regenerate PM blocker action register and closure board.
7. Regenerate product readiness snapshot in check mode.

## Acceptance criteria

This PM release track is closed only when:

- PM release areas reach `16/16`;
- full release blockers list is empty;
- CI streak evidence is attached and passes validation;
- UX observation report passes;
- license status closure report passes;
- product readiness snapshot no longer reports PM release blockers.

## Claim boundary

Allowed current claim:

> PM milestones and most release-area infrastructure are ready, but full release requires CI streak, human UX, and license/legal evidence.

Forbidden current claim:

- `full_release_gate_ready=true`
- `release_ready=true`
- `paid_pilot_ready=true`
- `limited_commercial_ready=true`
- human UX pass based only on automated browser smoke
- license pass based on a template or generated gate artifact
