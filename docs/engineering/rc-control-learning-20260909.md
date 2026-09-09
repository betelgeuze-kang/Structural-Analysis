# Train-only learned proposals for experimental cyclic RC control

`run_rc_control_learning_study` connects full original RC control analyses to an
immutable ridge correction of the existing secant initial iterate. The original
Newton, material, equilibrium, increment, control, parent and rollback authority
is unchanged. This is a separate cyclic-control profile; the monotonic-load
learning input/policy is not relabeled or reused as cyclic training evidence.

Every case carries a detached canonical model, exact typed control request,
caller-declared project/geometry-family/history identities and a train, validation
or holdout label. All cases are compiled and screened before creating output or
producing labels. Declared identities and entity-name-invariant physical/geometry
hashes cannot cross splits. Geometry is screened independently of changed loads,
sections or materials. Amplitude/sign-normalized target sequences and complete
prefix aliases also cannot cross splits. The history screen uses 12 significant
digits and conservatively groups aliases; the geometry screen is not a general
rotation/translation equivalence test. These checks do not authenticate project
or family provenance. Authored development labels are not independent projects.

Only train cases are analyzed before fitting. Each runs separate reference,
secant and fresh reference paths, with complete original recovery and retained
costs. Only an exact complete reference repeat supplies labels; a failed secant
comparison does not invalidate those original reference labels or become passing
evidence. Training pairs contain the original accepted coordinates minus the
secant predictor, original step byte hash, immutable parent and own accepted-prefix
context. No evaluation labels or future response labels enter features, fitting,
preprocessing, OOD limits or hyperparameter selection. The first target abstains
because no prior accepted increment exists.

Features combine pre-analysis model declarations, the current target/increment,
previous increment, accepted-prefix length, current augmented coordinates and
previous coordinate increment. Mean, scale, target scale, limits and ridge weights
use only train rows. The frozen finite JSON policy binds the model feature layout,
free-DOF order, controlled coordinate, solver configuration and original training
sample hashes. Duplicate JSON keys, malformed/boolean numeric arrays, invalid
scales, dimensions and hashes are rejected. Hashes establish consistency, not
source or training-data authentication.

Evaluation begins only after the policy is frozen and uses the existing independent
reference/secant/proposal/fresh-reference benchmark. An incompatible or OOD input
returns to the parent start; inference cannot commit a physical state. Prescribed
control is imposed only on the proposed initial coordinate. All other acceptance
conditions remain in the original solver. Policy identity is checked after each
evaluation and every proposal/abstention is recorded. Generation and evaluation
known/unknown core, Newton and linear costs are separate; fitting and whole-study
CPU/wall include the actual phase work. The whole study includes all generation
arms, full verification, fitting, inference, recovery and I/O, excluding the final
report write. Failed generation retains the roster and skips fitting/evaluation;
a fit failure retains generation costs and marks evaluation not attempted.

Validation passes 198 related tests, including 13 new learning tests, actual cyclic
label generation, actual proposal entry, OOD abstention, split aliases, train-only
statistics, immutable policy decoding, unknown generation work and fit failures.
The initial development run had one incorrect test expectation: a nearby geometry
was inside its explicitly extended OOD margin. A farther held-out test geometry
now tests actual abstention; the policy admission rule was not changed. The
original failed test log is retained. Ruff and diff checks pass. These are local
implementation checks, not full-repository or independent physical acceptance.

A separate frozen observation uses two authored training geometries and two
authored evaluation geometries with distinct declared control-history shapes,
all 242 targets and the same shared terminal finishing profile. Three serial fresh
processes are predeclared with alternating strategy order. Each repetition charges
its complete training generation and fit again. The existing unpolished and
shared-finishing strict-tolerance failures remain unchanged. Cyclic learning does
not waive those physical tolerances or license independent provenance, design
approval, net acceleration, public API expansion or release claims.
