# Fixed globalization probe for three failed reversal models

This development-only probe uses the three failed candidate models and original requests from sealed packet `dc9cee74b0cefb318f6b6f846b925f091af116b994a8542ed4a2522cc4e748ca`. It runs the packet's frozen `ca07bb1ea` API/solver source. Later design-report changes do not participate.

Each model is executed from genesis under three fixed configurations: original 25-iteration/six-alpha configuration; 25 iterations with binary backtracking alphas from 1 through 1/65536; and 100 iterations with the same extended alpha grid. All residual, increment and control tolerances, constant axial loads, targets (-20, -40, +20) mm, materials and geometry remain unchanged. No intermediate target, hidden retry or accepted-state reset is introduced.

The roster is nine analyses and nine fresh-source validations. All outcomes, clocks, control work and original result bytes are retained, including failures. Original-config result hashes must reproduce the retained results. New-config success requires complete original target execution and fresh validation under that same configuration. This does not prove equivalence to an unavailable converged original solution, global capacity or independent physics. Single ordered runs diagnose convergence rather than speed.

The protocol is frozen before execution. No production default or previously failed tolerance changes. A failure at the finer alpha grid remains a failure and does not trigger another unplanned grid. Results must distinguish increased work, unchanged failure and verified completion before deciding whether any further implementation is warranted.
