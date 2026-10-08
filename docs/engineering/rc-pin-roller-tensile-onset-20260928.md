# Synthetic pin/roller beam tensile onset

At source `908915df6bf6fa2b5cd74cee456898498b300d47`, the synthetic v4
four-point beam in `tests/test_rc_fiber_pin_roller_beam_public.py` uses N4 UY
as control DOF 10. The short target path `(-0.00015, -0.00016) m` reaches
concrete tensile onset: `f_t / E = 3 / 30000 = 0.0001` strain. The default
solve commits the first target, then stops with
`line_search_failed_to_reduce_residual` and exact rollback. Immediately before
failure, the maximum concrete tensile strain is about `0.0000999962`; every
candidate in the final default line search crosses the threshold and increases
the residual.
This is a strict monotone line-search limitation at the constitutive kink, not
evidence that equilibrium is absent.

An explicit `StatefulFiberFrame2DDisplacementControlConfig(control_tolerance_m=1e-15)`
weights the control equation more strongly while retaining the default Newton
equilibrium tolerance. It commits both short-path targets with concrete damage
at the second target, and fresh artifact verification passes. Three same-host
runs per configuration produced identical result and checkpoint hashes. These
hash observations do not establish cross-platform reproducibility.

The section, loads, and beam are synthetic. The stricter control setting is a
bounded diagnostic for this path, not a new default, a stability guarantee for
other models, or physical validation against a measured beam.
