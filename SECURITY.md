# Security Policy

## Supported versions

structural-analysis is a pre-1.0 Developer Preview. Security fixes are made
only on the current default branch and the current 0.3.x development line.
No support lifetime, response-time SLA, or production-safety certification is
promised.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's
[private vulnerability reporting form](https://github.com/betelgeuze-kang/Structural-Analysis/security/advisories/new).
Include:

- affected commit and execution environment;
- a minimal reproduction without secrets or proprietary customer data;
- expected and observed behavior;
- likely impact and any known workaround.

Do not attach credentials, license tokens, customer models, unpublished
benchmark data, or personally identifying information. Maintainers will
acknowledge the report when operationally possible, validate scope, and
coordinate a fix and disclosure plan.

## Engineering-safety boundary

A numerical discrepancy, silent fallback, evidence-integrity failure, or
incorrect structural result can be safety relevant even when it is not a
conventional software exploit. Report those cases privately and label them
engineering-safety. Until reviewed, do not use affected results for design,
permit, construction, or autonomous engineering decisions.

The repository's security policy does not promote any solver, AI, GPU/HIP, or
external-validation capability beyond its current evidence-backed status.
