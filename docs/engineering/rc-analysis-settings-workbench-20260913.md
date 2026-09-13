# Recorded analysis settings in RC comparison review

The [smaller-bar line-search observation](rc-reinforcement-linesearch-20260913.md)
showed that the same design and targets could fail or converge depending on the
declared backtracking fractions. Workbench now exposes a collapsed analysis
settings section from the validated comparison request, allowing that distinction
to be reviewed alongside performance and cost.

The section displays relative residual tolerance, increment tolerance in solver
coordinates, control tolerance, maximum Newton iterations, every backtracking
fraction, terminal polishing, matrix backend and load-factor coordinate scale.
Values retain their original numeric representation through JavaScript `String`;
no rounded summary or assumed solver defaults are substituted. It is read-only
and adds no input, solver execution, parameter change or qualification claim.

The existing desktop/mobile selection test now checks all eight fields against
the original fixture request and checks horizontal overflow. The combined design
and candidate-search browser selection passes **24 tests in 1.6 minutes**;
TypeScript and `git diff --check` pass. Existing failure, corruption, selection
and original-download behavior remains covered by those tests.

The actual successful 242-target baseline/smaller-bars comparison was also opened
at 1440 and 390 pixel widths, with 17 original-artifact reads per view. All eight
displayed settings match its request, including 40 maximum iterations, unchanged
`1e-10`/`1e-12` tolerances and the extended fractions down to `1/1024`. The
verified smaller-bars candidate remains selectable. Both screenshots were saved;
the mobile rendering was visually inspected and shows the fractions wrapping
within the panel.

This actual-output review used local Vite and Playwright route fulfillment with
original bytes, not a production service mount. It performed no new numerical
analysis. The numerical packet remains unchanged and has inventory SHA-256
`0891d6d92064bcc28e18e67050b29dde704928c959e50543bc0e8945a4155f8d`.

Review logs, images, script and source patch are preserved at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-settings-review-wi0s_hhn`:
8 files / 124,962 bytes; reread inventory SHA-256
`9c8dc5c77c5d2012ec173eeef4ec701ceb6b286e2a367ba5c408452922e94c37`.
Prior source `8b8ef6a16` has hosted frontend/development/topology passes, separately
retained on GitHub; those are not hosted validation of this new display change.
Full Python preparation, independent physics and the broader roadmap remain open.
