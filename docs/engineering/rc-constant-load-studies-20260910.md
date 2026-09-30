# Constant loading in RC design and learning studies

Source `da8ceb1c468d35a7d8b111be94501e5e553f1827` fixes a mismatch between
declared constant nodal loads and actual study execution. Design comparison had
rebuilt API keyword arguments without the constants. Seed comparison and learning
preflight had compiled the virgin model without binding the constant pattern.
An apparently verified study could therefore describe a different loading condition.

## Original before/after observation

The authored public cantilever uses three reversing lateral targets and an
independent -600 kN axial load at N2. The baseline and a width-0.5 m alternative
each undergo analysis and fresh full reference verification. Prices are authored
diagnostic values, not verified quotations. This is not the PEER U3 experiment.

| Observation | Before | After |
| --- | ---: | ---: |
| First baseline support axial reaction, N | 4.85722573273506e-14 | 600000.0000000001 |
| First seed-reference support axial reaction, N | 4.85722573273506e-14 | 600000.0000000001 |
| Two-design analysis and verification core calls | 12 | 16 |
| Reference, secant and fresh-reference core calls | 9 | 12 |

The original before-run direct API already returns the correct 600000 N reaction
in four core calls. Its result and the incorrect study originals remain retained.
The after-run seed study reports 22 Newton iterations and 22 linear solves,
unknown work false, and exact original/fresh-reference history and checkpoint
equality. The after observer takes 1.264118962 s across design and seed studies;
this is a single observation with concurrent development checks, not speedup.
Neither observer fits a model or admits an external experimental sample.

The after observation ran on a modified checkout based on `2bf288946`; its
unchanged numerical changes are now committed at the source above. The original
caller revision is retained in result bytes as a declaration, not rewritten into
a claim that the observation ran from an already committed source. The packet
includes the working diff and a subsequent 30-file exact Git-blob comparison.

## Execution and learning behavior

Every reference, secant, learned-proposal and fresh-reference arm executes its own
force-controlled preload before lateral targets. Original preload attempts,
Newton coordinates, assembly, response and work are retained. Binary64 and native
twofold recovery use original force-solver coordinates rather than reconstructing
them from rounded global rotations. A recovered preload becomes the accepted
origin; first-target and reversal checks use that origin. A failed preload or
recovery cannot enter the proposal path. Interruption retains a started unknown
record without fabricating a completed result.

Learning preflight binds the same constant-loaded physical model before deriving
features or applying experimental arithmetic wrappers. Constant-pattern features
and context identities distinguish the previous unloaded policies. Preflight
remains static; actual preload work is performed and counted separately for each
runtime arm. Existing project, geometry, history and measured-source split guards
remain enforced. Preload is the origin row, not an additional training label.

The actual four-case authored learning test generates 10 train-only labels in
42 core calls / 74 Newton iterations / 74 linear solves, performs one fit, and
evaluates the two separate evaluation cases in 56 core calls / 97 Newton iterations
/ 97 linear solves. Both work ledgers report no unknown counts. Original training,
fit and evaluation outputs are retained. These are small regression cases, not
evidence of transfer to external experiments or learned net acceleration.

An initial test declared only two reversals. Its preloaded holdout origin required
three, so all four holdout arms stopped after preload; evaluation retained 32
total calls. Those originals remain in the packet. The successful test explicitly
declares three reversals. A separate regression verifies that the stricter declared
budget still stops before any lateral solve. Other initial test failures were
invalid test setup: a zero-candidate design and dataclass replacement of a custom
learning-case constructor. Production scope and solver tolerances were not relaxed.

## Full-history design screens and Workbench

Design requests forward the complete public API configuration. Performance screens
include accepted preload plus lateral responses, and each full verification repeats
the preload. A regression uses a constant transverse preload followed by zero
controlled displacement: the preload strain exceeds the terminal strain, and a
limit between them prevents selection despite successful reference verification.

Workbench accepts the explicit constant-load request/result/native versions and
checks original preload step and assembly hashes, ancestry, request loading and
complete work counts using a shared stored-artifact validator. It recomputes the
performance screens from preload plus lateral history. The panel displays declared
constant loads and explains that both screens and execution costs include preload.
The browser checks stored bindings; it does not execute or authenticate the solver.
The new fixture is an exact copy of the after-design originals with provenance.

The Python regression selection passes 113 tests in 76.83 s. Two subsequently
added budget/interruption tests pass in 1.76 s: 115 distinct selected Python tests.
Three-source mypy, Ruff, TypeScript, build and production delivery checks pass.
The frontend selection passes 42 tests in 53.9 s, including existing proportional
studies and constant-load jobs using the shared validator. A two-test subset is
repeated in 17.3 s to capture the panel rather than the entire Workbench page;
these are not additional distinct tests. Desktop 1440 px and mobile 390 px panels
are visually reviewed, with bounded horizontal table scrolling and byte-exact
original downloads. The earlier standalone 21 contract tests are also a subset.

## Retained evidence and remaining scope

The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-constant-study-nid6nmlm`:
864 files / 32,353,215 bytes, inventory SHA-256
`6d20248aca3d803687b7838a03357f76d160387de060c39ad31606ea81e31c52`.
Every file is reread exactly. Before/after observers, original results, successful
and budget-limited learning runs, source audit, verification logs and final panel
screenshots are preserved. The two new Python-test results are recorded in the
verification summary; their original terminal output is in this task history.

Public experiment material/reinforcement/sensor reconstruction, the distinction
between measured traces and commanded targets, independent campaign coverage,
reuse conditions, learned net benefit and hosted/independent roadmap acceptance
remain open. This fix makes the studies honor declared loading; it does not admit
U3/ARISTA to training, change protected receipts or close the full objective.
