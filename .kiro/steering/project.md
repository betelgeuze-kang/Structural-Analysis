---
inclusion: always
---

# Kiro Project Steering

- Default to normal codebase assistance; do not auto-load Betelgeuze goal state.
- Use `docs/ai/ORCHESTRATION.md` only when the user explicitly requests orchestration or a design-only worker slice.
- Keep design briefs compact: goal, blockers, candidate files, implementation order, verification, and risk boundaries.
- Do not edit files or claim readiness closure from a design-only pass.
- Do not inspect `.betelgeuze/`, worker raw logs, or productization evidence unless readiness/gap-closure work is explicitly requested.
- Preserve partial/proxy/fallback/external-blocked evidence boundaries when readiness work is explicitly in scope.
