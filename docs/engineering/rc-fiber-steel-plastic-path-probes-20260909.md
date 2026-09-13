# Steel-plastic path diagnostics in the existing public RC profile

Nine declared load-path diagnostics at frozen source
`f37ebeda286a2e3cd4304767b749ec9652b5dcc6` all ended in nonconvergence. None
retained positive steel accumulated plastic strain in an accepted checkpoint.
Three failed trial assemblies reported a yielded member; those trials rolled
back exactly and do not establish committed plastic history. No full public
confirmation or constitutive companion was requested because no diagnostic met
the predeclared selection rule.

The purpose was to find a force-controlled, monotonic steel-plastic case for
the existing original J1–J5/public pipeline, without changing material strengths,
softening laws, convergence tolerances or acceptance. Existing section and beam
tests provide a useful strain/curvature region: default RC at axial strain
-3e-4 and curvature 6e-3/m has yielded steel in a section trial. The manufactured
beam path reaches steel yielding with independently specified axial/curvature
targets. Those tests prescribe strain or construct nonproportional target forces;
they are not complete public proportional-load verification.

## Protocol and full failure denominator

All models are straight 3 m, fixed-base, single-member RC cantilevers with three
integration points. The default 0.4 x 0.6 m section, twelve concrete layers,
0.05 m cover and 3.87e-4 m² individual bar area remain. Only the declared number
of bars per reinforcing layer and fixed tip axial-force/moment pair vary.
Steel remains E=200,000 MPa, fy=250 MPa and combined hardening 3,000/5,000 MPa;
concrete remains E=30,000 MPa, ft=3 MPa, fc=30 MPa and softening rates 3,000/400.
This is an existing synthetic constitutive recipe, not calibrated independent data.

Each diagnostic uses eight proportional increments, residual tolerance 1e-10,
increment tolerance 1e-12 and maximum iterations 40. The original public compiler
and load-path executor run; full public authority/recovery is deliberately not
credited to this diagnostic stage. All source and input bytes were frozen before
their corresponding stage. The initial six cases were declared together. At most
one complete steel-plastic case per bar-count group would receive a separate
full public and companion confirmation; none qualified.

| Stage | Bars per layer | Axial force (kN) | Moment (kNm) | Accepted / declared steps | Failed target factor | Failed trial yielded members |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Initial | 4 | 0 | 300 | 4/8 | .625 | 1 |
| Initial | 4 | 0 | 400 | 3/8 | .500 | 0 |
| Initial | 2 | 0 | 200 | 4/8 | .625 | 0 |
| Initial | 2 | 0 | 300 | 2/8 | .375 | 0 |
| Initial | 4 | -500 | 400 | 6/8 | .875 | 1 |
| Initial | 2 | -500 | 300 | 4/8 | .625 | 0 |
| Refinement | 4 | -390.625 | 312.5 | 7/8 | 1.000 | 1 |
| Refinement | 4 | -406.25 | 325 | 4/8 | .625 | 0 |
| Refinement | 4 | -421.875 | 337.5 | 4/8 | .625 | 0 |

The second stage was explicitly exploratory: the initial axial -500/moment 400
path accepted through moment 300 and failed at moment 350. Three additional
terminal pairs subdivided that bracket while preserving its axial/moment ratio.
Their eight-step schedules also change the preceding accepted targets, so this
is not a fixed-history bisection or a capacity bound. All three new inputs were
declared before their execution, and the first complete steel-plastic path would
receive one public confirmation. Again, none qualified. There were no automatic
retries or material/tolerance changes.

Every failure reports `line_search_failed_to_reduce_residual`, an immutable parent,
exact rollback and no regularization/fallback. Every accepted checkpoint across
all nine paths retains zero steel accumulated plastic strain. A terminal
diagnostic has 42 modeled fiber points, including six aggregate steel states;
these are not six physical bars. Failed-trial yielding is retained separately.
The results neither prove physical capacity nor prove that every other supported
load schedule must fail. They show that this declared force-controlled candidate
set did not supply the missing complete steel-plastic public evidence.

## Costs and retained records

Artifacts are sealed at `/tmp/structural-rc-steel-plastic-probe.0zqbubj6/`:
the 397-file committed package export, both protocols, nine exact model inputs,
nine path/checkpoint/attempt groups, selection decisions and original logs.
The original and refinement source-after files exactly match source-before.
Both execution handles completed successfully as drivers; their nine physical
load-path outcomes remain blocked.

Summed diagnostic wall/CPU intervals are 6.839022740/6.838590850 seconds. They
include original compilation/load-path execution and saved path/checkpoint
persistence. Refinement intervals also include model parsing, while initial
parsing occurs outside those individual timers. These differing diagnostic
intervals are not repeated performance comparisons or full public-analysis costs.

The saved-artifact audit passed **623 checks**, covering source/input identities,
the 6+3 denominator, all accepted checkpoint material counts/values, schedules,
terminal/parent bindings, rollback and zero public-confirmation decisions. It
performed no numerical replay. The local inventory covers **450 files /
17,803,358 bytes**, excluding itself. `inventory.json` is 87,075 bytes with raw
SHA-256 `047682eb00546bdfca73583904b2e0d13830b8b08c1cc230f9c0b1825191b1d1`.
Each inventoried file was reread and checked after creation. These hashes are
local consistency evidence, not signatures or independent physical validation.

Committed steel-plastic and cyclic public-path evidence remains open. Changing
loading/control scope requires its own input, receipt, history, restart and
verification contracts; these failures do not authorize bypassing existing gates.
The earlier [complete tensile-damage observation](rc-fiber-damaged-history-runtime-20260908.md)
retains its original limited scope and is not relabeled as steel-yield evidence.
