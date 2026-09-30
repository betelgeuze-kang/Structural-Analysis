# Fixed whole-path secant comparison for failed reversal models

Compare original reference starts and the existing causal secant start on all three failed 40 mm candidate models from packet `dc9cee74b0cefb318f6b6f846b925f091af116b994a8542ed4a2522cc4e748ca`. Use its frozen `ca07bb1ea` source and original targets, axial loads, materials, tolerances, alpha grid and iteration limit. No learned policy, hidden target subdivision or new training occurs.

Run two fixed orders per model: reference/secant and secant/reference. Each comparison also runs a fresh reference, giving six comparisons and eighteen attempted full paths. Every path retains solver attempts, original checkpoints, response recovery, costs and failed/unattempted targets. A secant path completing when the reference remains incomplete is only a candidate convergence observation; it cannot pass the existing complete-history comparator or earn a qualified speed ratio. Repeated secant states can be checked for internal reproducibility, not independent physical accuracy.

The experiment is diagnostic and changes no production starting policy. All cases remain in the denominator. Record errors and known/unknown work rather than dropping failed comparisons. Results must precede any decision to integrate an optional seed into the design API.
