# PR 28 Split Plan

PR #28 is mergeable, but it is too broad to treat as a single product-readiness change. It mixes architecture documentation, AI orchestration wiring, readiness/evidence receipts, gap-ledger audit logic, and generated artifacts. This plan defines a safe split so web-only review can proceed without mutating protected evidence accidentally.

## Current risk

- Scope: hybrid-AI architecture + readiness evidence + gap-ledger audit + generated artifact intake.
- Scale: hundreds of files and generated outputs.
- Risk: a single merge would make it difficult to identify which part changed release claims, generated receipts, or AI orchestration behavior.

## Split order

### 28-A — docs/hybrid-ai-architecture

**Goal:** land explanatory architecture docs only.

Allowed paths:

```text
docs/**
README.md
```

Blocked paths:

```text
implementation/phase1/release_evidence/productization/**
docs/commercial-structural-solver-product-gap-ledger.md
docs/structural-analysis-ai-engine-gap-ledger.md
.github/**
```

Acceptance:

- No generated evidence changes.
- No readiness status promoted.
- Claim boundary text explicitly states that AI is advisory until physical solver gates pass.

### 28-B — ai/kiro-orchestration

**Goal:** bring in Kiro/AI orchestration files and shell/script wiring.

Allowed paths:

```text
AGENTS.md
docs/ai/**
scripts/ai-*
scripts/validate-ai-worker-output.mjs
tests/ai-*
opencode.json
package.json
.github/workflows/ai-contract-verify.yml
```

Acceptance:

- `npm run ai:verify:contract` passes.
- New scripts are invoked through `bash` or `node`; executable-bit loss remains non-fatal.
- No protected evidence files changed.

### 28-C — evidence/readiness-sync-dry-run

**Goal:** introduce readiness-sync code and reports in dry-run form only.

Allowed paths:

```text
scripts/*readiness*.py
scripts/*snapshot*.py
tests/test_*readiness*.py
tests/test_*snapshot*.py
```

Acceptance:

- Dry-run/check mode available.
- No tracked receipt is rewritten by default.
- Tests prove stale/missing evidence remains blocked.

### 28-D — gap-ledger-audit

**Goal:** tighten source-receipt/gap-ledger audit without changing closure claims.

Allowed paths:

```text
scripts/*gap*ledger*.py
tests/test_*gap*ledger*.py
docs/*gap*ledger*.md
```

Acceptance:

- Audit can report more blockers.
- Existing partial/external-blocked rows are not promoted to closed unless matching receipts exist.
- Any claim-boundary wording changes are reviewed explicitly.

### 28-E — protected-evidence-refresh

**Goal:** refresh protected evidence only after scripts and claim boundaries are reviewed.

Allowed paths:

```text
implementation/phase1/release_evidence/productization/**
implementation/phase1/release/**
implementation/phase1/*status*.json
```

Acceptance:

- Every refreshed artifact declares `source_commit_sha`, `generated_at`, producer command, and input checksums.
- Mixed-source snapshots remain blocked.
- Product readiness is not promoted while G1, fresh validation, external benchmark, customer-shadow, or license blockers remain.

## Review sequence

1. Merge 28-A and 28-B first; they are web-reviewable and low-risk.
2. Review 28-C and 28-D with focused tests and no protected output writes.
3. Only then review 28-E as a protected-evidence change.
4. Close PR #28 after all accepted slices land, or replace it with a small integration PR if anything remains.

## Non-goals

- No solver tolerance changes.
- No G1/full-load/full-mesh closure claim.
- No production release readiness claim.
- No manual editing of generated evidence to make a gate pass.
