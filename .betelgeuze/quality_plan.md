# Betelgeuze Quality Plan

Generated: 2026-05-31T10:05:19Z

## Project Profile
- Languages: javascript/typescript, python
- Frameworks: react, typescript
- Confidence: high

## Oracle Ladder
1. Project contract: goal, non-goals, protected areas, architecture constraints.
2. Static checks: syntax, typecheck, lint, formatting when available.
3. Tests: focused unit/integration/e2e or documented absence.
4. Diff review: scope drift, risky files, deletions, API/contract changes.
5. Runtime smoke: app/service starts or key flow works when applicable.
6. Human decision: product direction or external-state ambiguity.

## Discovered Commands
- build: `npm run build`
- test: `pytest`
- typecheck: `python -m compileall .`

## Missing / Weak Oracles
- no lint command discovered
