# Readiness Surface Discrepancy Report

> Status: **non-promoting PM governance report**  
> Scope: readiness-count and source-of-truth alignment  
> This report does **not** rewrite protected evidence, regenerate receipts, promote `release_ready`, close G1, or change commercial claims.

## 1. Why this report exists

The repository now has multiple readiness surfaces that intentionally serve different audiences:

| Surface | Audience | Purpose |
|---|---|---|
| `README.md` | humans, quick repo orientation | Short canonical status and claim boundaries. |
| `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json` | release tooling | Machine-readable rollup over direct upstream artifacts. |
| `implementation/phase1/release_evidence/productization/structural_product_development_roadmap.md` | PM roadmap | Stage-based structural product roadmap summary. |
| PM release gate reports | release manager | Release-area blockers and milestone evidence. |
| Developer Preview readiness/RC reports | preview owners | DP deliverables and final gates. |

These surfaces are allowed to expose different slices, but they must not contradict the authoritative release claim. Current observed issue: blocker counts are close but not identical across surfaces.

## 2. Current observed counts

| Surface | Current signal | Interpretation |
|---|---:|---|
| README canonical product readiness | blocker_count approximately `36` | Human-facing structural readiness summary. |
| Structural product roadmap | snapshot_blocker_count approximately `41` in recent roadmap, `36` in latest refreshed roadmap surface | Stage-level PM summary may lag or use structural-only filter. |
| Raw product readiness snapshot | blocker_count approximately `42` in latest machine rollup | Most detailed direct rollup; includes structural scope and fresh validation integrity blockers. |

PM interpretation:

```text
All surfaces agree on the important point: readiness is blocked.
They do not yet perfectly agree on exact blocker count.
Before any release claim moves, the repository needs a single source-of-truth policy and refreshed synced surfaces.
```

## 3. Known drivers of count drift

| Driver | Effect on count | PM handling |
|---|---|---|
| Structural scope quarantine / owner decisions | Adds structural-scope blockers until owner decisions are recorded. | Keep visible; do not treat quarantine alone as closure. |
| Fresh validation artifact integrity | Adds benchmark/software blockers when artifact checksums mismatch. | Fix or refresh receipts; do not override manually. |
| README summarization | May show a compact structural-only blocker count. | README should name the authoritative source and update after snapshot refresh. |
| Roadmap stage rollup | May group blockers by stage and count ready stages instead of raw blockers. | Valid if clearly labeled; should not claim release readiness. |
| GitHub sync / worktree state | Can change quickly during active development. | Use tracked preflight for release, live state for diagnostics. |
| Developer Preview split | DP blockers and future-commercial blockers are intentionally separated. | Do not mix DP readiness with commercial readiness. |

## 4. Source-of-truth policy

Recommended policy:

1. `product_readiness_snapshot.json` is the machine-readable authoritative readiness rollup.
2. `structural_product_development_roadmap.md` is the PM stage view and may group blockers.
3. `README.md` is a short human-facing mirror and must be refreshed after the authoritative snapshot changes.
4. No release claim may move unless:

```text
README count == product_readiness_snapshot headline count OR the README explicitly states that it is a structural-only compact count
structural roadmap snapshot status matches the authoritative snapshot status
PM release gate report has no unresolved release-area blockers for the target claim
```

## 5. Recommended sync workflow

Run these in a clean checkout; avoid rewriting protected evidence unless the command is explicitly a generator for tracked evidence and the owner has approved it.

```bash
# Inspect authoritative snapshot without accidental refresh
python3 scripts/build_product_readiness_snapshot.py --json --no-write

# Check release freshness
python3 scripts/report_release_evidence_freshness.py

# Rebuild roadmap only when upstream receipts are intentionally current
python3 scripts/build_structural_product_development_roadmap.py --json

# Release-mode gate, no protected-evidence rewrite
python3 scripts/verify_quality_gate.py --mode release
```

If a generator updates tracked evidence, follow with:

```bash
python3 scripts/build_product_readiness_snapshot.py --check --fail-blocked
python3 scripts/report_release_evidence_freshness.py
```

## 6. Blocking categories to keep visible

Even after count sync, these blocker families must remain visible until truly closed:

| Family | Must remain visible because |
|---|---|
| G1 numerical blockers | Full-load/full-mesh/material Newton/ROCm residency are not closed. |
| External benchmark receipts | EB receipts remain required for commercial solver claim upgrade. |
| Customer shadow | Paid pilot needs completed-project customer-retained metadata. |
| License/legal | Commercial release needs active product-scope license evidence. |
| CI/runner streak | Release-area trust needs 30-run PR/nightly evidence and self-hosted runner status. |
| Human UX observation | Developer Preview and release confidence need observed workflow evidence. |
| Structural scope owner decisions | Quarantine is not the same as owner closure. |

## 7. PM exit criteria

| Exit criterion | Target |
|---|---|
| README headline status | matches authoritative target surface or explicitly labels compact count |
| Product readiness snapshot | generated/checked and committed intentionally if changed |
| Roadmap | regenerated after upstream changes and matches status semantics |
| Freshness | release-decision artifact freshness PASS |
| Structural scope | owner decisions recorded or explicitly accepted as quarantined by policy |
| Release claim | remains blocked until release areas and solver/customer/license gates pass |

## 8. Recommended next action

The next PM action should be:

```text
Close the structural scope owner-decision blocker first, then refresh product_readiness_snapshot, structural_product_development_roadmap, and README in one controlled PR.
```

Do not use a blocker-count sync PR to promote product readiness. The correct outcome may still be:

```text
status = blocked
```

with cleaner, consistent reasons.

## 9. Claim boundary

This document is a discrepancy report only. It does not close:

```text
release_ready
paid_pilot_ready
Developer Preview ready
G1
external benchmark receipts
customer shadow
license/legal readiness
```
