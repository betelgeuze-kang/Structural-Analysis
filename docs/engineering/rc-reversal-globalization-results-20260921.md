# Fixed reversal globalization probe: all nine paths remain incomplete

The predeclared three-model/three-configuration probe completed nine analyses and nine fresh-source validations using frozen `ca07bb1ea` API/solver code from the original sealed packet. All three original-configuration result hashes exactly reproduce the original failed results. All nine artifact contracts pass, with no verification errors or unknown execution work; physical-path completeness remains false in every case.

| Candidate | Original final relative residual | Extended-grid final relative residual | Original / extended total Newton iterations per analysis |
| --- | ---: | ---: | ---: |
| width 0.32, cheap | 0.1094998856 | 0.1093972259 | 28 / 30 |
| width 0.32, middle | 0.5720162150 | 0.5693857330 | 26 / 34 |
| width 0.48, cheap | 0.1401052175 | 0.1390789288 | 24 / 30 |

Both extended-grid profiles use alphas 1 through 1/65536. Increasing the iteration limit from 25 to 100 gives the same final residual and work as the 25-iteration extended-grid profile for each model. All failures still occur through `line_search_failed_to_reduce_residual`, not iteration exhaustion. The numbers above include preload and accepted prefix work; they are not all iterations at the failed reversal.

The added alpha values produce a small residual reduction and more work but no completion. Accepted targets remain -20 and -40 mm; +20 mm fails, with the accepted parent unchanged and exact rollback. Residual/increment/control tolerances, target sequence, constant axial load and material parameters were unchanged. No hidden target subdivision, production default change or policy promotion follows.

The run accounts for 72 attempted steps and 532 Newton iterations/linear solves including mandatory fresh validation. Enclosing driver time is 7.660691871 seconds. Single ordered diagnostic runs do not support speed comparisons. These failures do not establish physical instability or prove that every globalization method fails; they rule out the two fixed extensions as solutions for these three cases.

All 60 diagnostic packet files were inventoried and reread. Inventory SHA-256: `c5cad2a77ed4ef1b7d4c43572d71e88eeafb0300e8f15f4488fff2f6c7a86fcc`. The driver verifies source and inputs against original packet inventory `dc9cee74b0cefb318f6b6f846b925f091af116b994a8542ed4a2522cc4e748ca` before execution. The complete roster, configuration grids, original bytes, timings and outcomes are retained; [the summary](rc-reversal-globalization-results-20260921.summary.json) contains packet/source identities and work totals.

The next diagnostic should examine the final Newton direction, residual merit and tangent response at the retained failing state before proposing another solver change. Larger iteration limits alone are not justified by these results. Independent physics, broader capability and the full roadmap remain open.
