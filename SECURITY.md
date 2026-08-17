# Security Policy

## Supported versions

Structural Analysis is a pre-1.0 Developer Preview. Security fixes are made
only on the current default branch and explicitly named preview lines. No
support lifetime, response-time SLA, or production-safety certification is
promised.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Use the repository's
[private vulnerability reporting form](https://github.com/betelgeuze-kang/Structural-Analysis/security/advisories/new).
If that surface is unavailable, contact the repository owner privately through
the contact method published on the owner's GitHub profile.

Include:

- affected commit or tag and execution environment;
- operating system and architecture;
- whether ROCm/HIP, a native library, the local web surface, or an imported
  model is involved;
- a minimal reproduction without secrets, restricted benchmark material, or
  proprietary customer data;
- expected and observed behavior;
- likely confidentiality, integrity, availability, or numerical-authority
  impact and any known workaround.

Do not attach credentials, signing material, license tokens, customer models,
unpublished benchmark data, or personally identifying information.
Maintainers will acknowledge the report when operationally possible, validate
scope, and coordinate a fix and disclosure plan.

## Engineering-safety and evidence-integrity boundary

A numerical discrepancy, silent fallback, evidence-integrity failure, or
incorrect structural result can be safety relevant even when it is not a
conventional software exploit. Treat the following as security-relevant
integrity failures:

- a failed or non-converged run presented as an authoritative result;
- source, model, checkpoint, result, or evidence hash substitution;
- silent CPU fallback from a required HIP execution;
- unsafe native ABI ownership or memory behavior;
- untrusted report or project content causing code execution;
- signing-key, credential, or private-model leakage;
- a generated artifact being accepted against a different source epoch.

Report those cases privately and label them `engineering-safety`. Until
reviewed, do not use affected results for design, permit, construction, or
autonomous engineering decisions.

The repository's security policy and any validated reproduction receipt do not
promote solver, AI, GPU/HIP, external-validation, design, public-support, or
release authority beyond current evidence-backed status.
