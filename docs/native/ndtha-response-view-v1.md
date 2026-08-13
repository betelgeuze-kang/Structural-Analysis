# Bounded NDTHA response-history view v1

## Contract

`structural-workbench result-view` is a read-only terminal projection of one durable Workbench
session at `terminal`, `compared`, or `reported`. `NativeWorkbench::open` first verifies every
published stage receipt and artifact inventory. The command then strictly parses and self-hash
verifies `04-resume/result-ir.json`; a changed ResultIR is rejected before rendering.

The closed v1 channel vocabulary is:

- `top-displacement` in metres;
- `drift-ratio` in percent;
- `base-shear` in kilonewtons, matching the ResultIR response field;
- `residual-inf` in newtons.

The default window starts at one-based step 1 and requests 64 rows. `--count` is restricted to
1..=256 and `--start-step` must select the completed response prefix. A short terminal tail is
returned without synthetic padding. This keeps output bounded even though the solver contract can
carry up to one million steps; any completed step can still be selected explicitly.

`--locale` accepts only `en-US` or `ko-KR` and defaults to English with the original bytes
preserved. Korean changes fixed labels and guidance while keeping exact row data and provenance
tokens. See `docs/native/localized-terminal-result-views-v1.md`.

## Determinism and provenance

Each row contains the exact `.17e` response value together with convergence, iteration,
plastic-story-count and residual-infinity metadata for that step. The 41-column ASCII plot is
normalized against the minimum and maximum of the whole completed selected channel, not the
current window, so moving the window does not change its axis. The final `View hash` binds every
preceding output byte.

The header preserves ResultIR, request, model, state, execution and checkpoint identities and the
fixed CPU/fp64/fallback-zero backend boundary. Output has no ANSI escape byte and does not mutate
the durable workspace.

## Deliberate boundary

ResultIR v1 does not contain `dt_s`, so this view labels the horizontal coordinate only with the
one-based step index. It does not infer time. It is not a 3D/deformed/modal/contour renderer,
general visual result explorer, engineering acceptance, or design-code compliance evidence. The
`general_visual_model_editing_and_3d_result_exploration` transition blocker therefore remains open.
