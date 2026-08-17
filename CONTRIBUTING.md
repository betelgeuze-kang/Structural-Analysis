# Contributing

## Current legal boundary

This repository is publicly visible but is **not currently open source**. The default `LICENSE` grants no permission to use, copy, modify, publish, distribute, sublicense, sell, or create derivative works without a separate written agreement from the applicable copyright holder.

Do not submit code, generated binaries, third-party datasets, or derivative benchmark packages unless the repository owner has first confirmed the applicable contribution and redistribution terms in writing. Opening an issue does not grant a software or data license.

## Contributions currently suitable for discussion

The following may be proposed through an issue without representing product or verification authority:

- reproducible bug descriptions that contain no restricted source or data;
- public-source citations and license metadata;
- proposed analytical benchmark definitions;
- community reproduction receipt metadata produced under an applicable written permission;
- documentation corrections that do not reproduce third-party protected material.

## Future contribution workflow

After a contribution license policy is approved, code contributions are expected to follow this sequence:

1. Link the change to a dedicated issue.
2. State the exact source commit and claim boundary.
3. Keep product code, generated evidence, and external data in separate review surfaces.
4. Add focused deterministic tests.
5. Preserve unsupported, failed, blocked, and non-converged states without silent fallback.
6. Do not claim external V&V, hardware, design, public, or release authority from a self-authored change.
7. Include a rollback section in the pull request.

## Numerical evidence

A passing internal test is not independent validation. Analytical verification, cross-code comparison, experimental validation, blind prediction, community reproduction, and public support are separate evidence levels.

## Security reports

Do not disclose suspected vulnerabilities in a public issue. Follow `SECURITY.md`.
