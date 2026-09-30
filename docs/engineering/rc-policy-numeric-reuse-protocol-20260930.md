# Predeclared numeric policy representation reuse diagnostic

This development experiment compares baseline commit
`63c05c317afae1190d62b0b8d29861c1db89c4cb` with the reviewed, committed
numeric-array reuse candidate on existing draft #527. It does not compare with
historical timing packets. The plan must identify both final source revisions,
every exported source/resource/helper byte, the independent measurement driver,
the schedule, and all inputs before the first numerical slot. Separate source
exports are verified against committed Git blobs; no in-process monkeypatch
selects the baseline. A source mismatch prevents execution.

The sole numerical implementation change reuses immutable C-order bytes,
NumPy dtype and shape descriptors for six policy fields, bounded to four exact
encoded JSON contents. Every inference obtains fresh read-only views. Full
policy construction, profile/model/feature checks, OOD arithmetic, material
capture and decode, guards, fallback, solver tolerances and accepted-state
authority remain unchanged. No array representation is prepared during input
loading or a warmup. Lazy preparation belongs to the first proposal callback.

Use only the previously declared synthetic F/G development cases from
`scripts/run_rc_cost_gate_development_pilot.py`, the 20 kN preload, twelve
original reversing targets, and the guard allowing target indices 2 through
10. Use the SAME frozen unpromoted policy
`sha256:748ca448dc4aacea36bea9d6672057aa3d76c15ff1d8ac6db6f9ff53e40e8e48`
from original inventory
`e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0`.
Its arithmetic is `retained-twofold-refinement.v1`; binary64 would cause a
profile rejection and is not included in the timing comparison. Valid policies
under both arithmetic profiles are covered by separate code tests.
Only the original A–E training model/request metadata is used for existing
preflight. No training or reserved case is numerically executed, no reserved
input or response is opened, and no policy is fit, resealed or promoted.
Material snapshot layout reuse is false for both source versions.

Declare twelve fresh process slots: baseline and candidate for each F/G case
and each of three repetitions, with zero warmups. In each repetition rotate
reference/secant/proposal arm order as in the previous development protocol;
alternate baseline/candidate process order by repetition plus case index.
Each slot computes reference, secant, guarded proposal and fresh reference
from genesis, giving 48 full paths. Launch strictly in declared index order.
Every started receipt binds the preceding outcome and inventory. A missing or
started-only slot prevents later launches. Raised, stopped and missing slots
remain unknown in the twelve-slot denominator, never zero-cost successes.

Keep absolute tolerance `1e-10`, relative tolerance `1e-8`, and the strict
one-percent diagnostic improvement rule. Recompute the equal-case mean of
three proposal/secant whole-path ratios per case for each source version;
strictly below `0.99` is the existing diagnostic screen, not promotion. Also
report all six paired candidate/baseline callback and whole proposal-path
ratios, and equal-case means. A whole-path optimization claim additionally
requires all six pairs eligible and byte-identical with its paired equal-case
mean strictly below `0.99`; a cheaper callback alone is not whole-path speedup.

Independently verify each original slot inventory, bound model/request,
policy/guard/source identities, complete response histories and known solver
work. Matched proposal paths require the exact fixed 24 context files (twelve
material contexts plus twelve guard contexts), thirteen step files including
preload, entry seed bytes and decision/fallback meanings. Preserve raw timing
reports; source stamps and observed timings are not semantic equality fields.
Any changed seed/context/step, failed history comparison, unknown work or
missing slot makes that pair ineligible.

Record wall/CPU separately for source admission, input loading and preflight,
the four-path benchmark, each path, material capture, proposal callbacks,
guards, numerical attempts, recovery, fresh child launch-through-exit, parent
process, and read-only audit. Nested scopes must not be summed; require each
scope and its sequential aggregate to fit its enclosing measurement. Child
launch-through-exit includes startup, imports and final outcome/inventory
writes. The first inference includes representation preparation. Prior label
generation, fitting and selection costs remain historical and are not zero.
This diagnostic does not establish full AI lifecycle break-even.

Use one BLAS thread, actual controller/child terminal outcomes and fixed
budgets: 1,800 seconds for the controller, 180 seconds per child, 1 GiB child
RSS and 1 GiB newly generated study files. Record actual peak RSS and disk
bytes and preserve interrupted work. A budget stop records unknown work;
there is no automatic retry, resumed numerical path or replacement slot.

F/G and A–E derive from a single public example template. Repeats do not create
independent projects or physical specimens. Secant stays selected and the
learned policy remains unpromoted regardless of this diagnostic. No result
authorizes reserved evaluation, physical validation, service deployment,
general speedup or currency savings. Existing experiment packets and source
datasets remain unchanged.
