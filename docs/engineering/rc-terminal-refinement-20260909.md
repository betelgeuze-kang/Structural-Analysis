# Bounded retained-coordinate terminal refinement

The previous full observation passes one of two fixed comparisons, with three
base-case axial/reaction differences remaining. An original-parent local trial
supports one additional retained-coordinate correction. This implementation adds
explicit benchmark-only `terminal_refinement_limit=2`; the validated problem can
select one through four attempts, with one preserving the previous default wire
contract. Additional attempts require enabled twofold terminal polishing and the
existing rational/native twofold frame profile. The problem contract and benchmark
identity bind any nondefault limit.

Each attempt adds the selected high coordinate, its retained low component and the
original Newton correction in rational arithmetic, then rounds to a canonical
pair of binary64 values. This three-term sum can require more than two components;
the twofold projection is explicit, not an arbitrary-precision coordinate claim.
Every candidate uses the same original native material parent and the original
strict residual improvement and residual/increment gates. A rejected later attempt
preserves the earlier accepted pair. The original Newton iteration budget also
bounds refinement. Ordinary iterations and line search are unchanged.

The optional refinement record retains every attempted/skipped candidate, its
original and proposed pair, residuals, increment and numerical errors. Selected
summary fields identify the last accepted candidate; separate stop reason and
summed assembly/linear/exception counts include subsequent rejected work. Each
accepted candidate enters convergence history, and final assembly, commit and
original transition recovery consume the selected pair. No material state is
committed between attempts.

Validation covers two sub-ulp corrections with the same high coordinate, later
residual/increment/assembly failure after an accepted correction, complete work
counts, original iteration limit, invalid options, profile-bound native restart
in a fresh interpreter, failure rollback, cyclic original transition recovery and
compensation tamper rejection. Two complete 242-target geometries must still pass
the unchanged absolute `1e-10` / relative `1e-8` comparisons before repeat admission.
All full costs and negative results will remain visible. This implementation alone
does not establish full comparison acceptance, speedup or roadmap closure.

Focused refinement tests pass 21 in 13.01 s. The related original/sparse Newton,
polishing, native control/recovery, rational assembly and quality-contract
neighborhood passes 208 in 52.46 s. Ruff and diff checks pass.
