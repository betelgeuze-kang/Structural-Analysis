# Performance Bottleneck Map

- `summary`: `Performance profiling: PASS | ndtha=106.34s(solver=92.93,state=7.81,iface=5.12,halo=0.47) | ssi_contact=160steps/1.01iters/newton=0/zero_gap_skip=1.00/pairs=290:354/sweep=4/4 | moving_load=warm=0.001/0.001s,steady=0.001/0.001s,scale=0.619/1.246/2.505s | gpu_host_ops=2 unavoidable/0 optimizable | sprint=3(ndtha_partitioned_runtime,ssi_contact_convergence_path,moving_load_kernel_warmup_observability)`
- `generated_at`: `2026-07-02T05:12:08.847890+00:00`

## Baseline

| Item | Value |
| --- | --- |
| NDTHA wall-clock mean | 106.341s |
| NDTHA wall-clock cov | 0.002389 |
| NDTHA step wall mean | 106.325232s |
| NDTHA solver mean | 92.933823s |
| NDTHA state-update mean | 7.808277s |
| NDTHA interface mean | 5.117861s |
| NDTHA solver reuse ratio | 0.000 |
| NDTHA stiffness refresh count mean | 19333.000 |
| NDTHA halo exchange mean | 0.465272s |
| NDTHA retry overhead mean | 0.000000s |
| SSI/contact step count | 160 |
| SSI/contact mean coupling iters | 1.006 |
| SSI/contact candidate pairs | 290 |
| SSI/contact rejected pairs | 354 |
| SSI/contact pruned track ratio | 0.298 |
| SSI/contact retained-force warm start ratio | 0.000 |
| SSI/contact stable zero-gap skip ratio | 1.000 |
| SSI/contact variant sweep pass | 4/4 |
| SSI/contact variant sweep zero-gap | 4/4 |
| SSI/contact variant sweep pruned | 1/4 |
| SSI/contact variant zero-gap range | 0.948-0.979 |
| SSI/contact variant pruned range | 0.000-0.182 |
| Moving-load Euler elapsed | 0.001316s |
| Moving-load Timoshenko elapsed | 0.001360s |
| Moving-load warmup skew | 1.108x |
| Moving-load Euler warm-up | 0.000757s |
| Moving-load Timoshenko warm-up | 0.000683s |
| Moving-load Euler steady-state | 0.000560s |
| Moving-load Timoshenko steady-state | 0.000677s |
| Moving-load fast path | True |
| Moving-load active axle mean | 3.438 |
| Moving-load sparse-step ratio | 0.000 |
| Moving-load integrator elapsed | 0.619326s |
| Moving-load large elapsed | 1.246049s |
| Moving-load xlarge elapsed | 2.505040s |
| Moving-load large cached inverse | True |
| Moving-load xlarge cached inverse | True |
| VTI elapsed | 0.044577s |
| GPU unavoidable host ops | 2 |
| GPU optimizable host ops | 0 |

## First Map

### ndtha_partitioned_runtime

- `priority`: `P0`
- `domain`: `ndtha`
- `status`: `open`
- `headline`: Full-duration NDTHA wall-clock is the largest measured solver hot path.
- `optimization_hypothesis`: The partitioned NDTHA path is now split into solver, state-update, interface, halo, and retry buckets. The next gain is to reduce the dominant solver bucket while keeping interface and state-update costs bounded.
- `evidence`: 
  - `elapsed_wall_s_mean`: `106.34080333699967`
  - `elapsed_wall_s_cov`: `0.002388507120782136`
  - `step_wall_seconds_mean`: `106.32523200148489`
  - `halo_exchange_seconds_mean`: `0.4652718305383132`
  - `retry_overhead_seconds_mean`: `0.0`
  - `solver_seconds_mean`: `92.93382280904461`
  - `state_update_seconds_mean`: `7.808276745873172`
  - `interface_seconds_mean`: `5.117860616028793`
  - `solver_reuse_ratio_mean`: `0.0001041493084485919`
  - `stiffness_refresh_count_mean`: `19333.0`
  - `retry_attempt_count_mean`: `0.0`
  - `retry_attempts_per_completed_step_mean`: `0.0`
  - `peak_vram_mb_mean`: `0.0`
  - `hip_kernel_invocation_count_total`: `883`
- `first_actions`:
  - Use the new solver/state-update/interface split to isolate the dominant portion of step solve time.
  - Apply Jacobian/stiffness reuse only if solver time dominates the new split.
  - Promote Jacobian/stiffness reuse counters into the NDTHA report.
  - Trial a reduced stiffness refresh cadence on the 10M long-profile path.
- `acceptance_signals`:
  - elapsed_wall_s_mean reduced by at least 15%
  - elapsed_wall_s_cov remains <= 0.01
  - no_cpu_fallback and production-kernel proof remain green

### ssi_contact_convergence_path

- `priority`: `P0`
- `domain`: `ssi_contact`
- `status`: `open`
- `headline`: SSI/contact convergence is stable, but iterative coupling and settle handling still dominate the nonlinear interaction path.
- `optimization_hypothesis`: Broadphase pair counts and track-solve pruning are now exposed, so the next gain is to push more non-contact steps down the pruned path and cut Newton work without touching correctness-critical convergence thresholds.
- `evidence`: 
  - `step_count`: `160`
  - `mean_coupling_iters`: `1.00625`
  - `adaptive_newton_call_count`: `0`
  - `adaptive_newton_avg_iterations`: `0.0`
  - `broadphase_pair_count_total`: `644`
  - `broadphase_candidate_pair_count_total`: `290`
  - `broadphase_rejected_pair_count_total`: `354`
  - `broadphase_candidate_pair_ratio`: `0.4503105590062112`
  - `broadphase_rejected_pair_ratio`: `0.5496894409937888`
  - `track_static_pruned_ratio`: `0.2981366459627329`
  - `variant_sweep_variant_count`: `4`
  - `variant_sweep_pass_count`: `4`
  - `variant_sweep_zero_gap_positive_count`: `4`
  - `variant_sweep_retained_force_positive_count`: `0`
  - `variant_sweep_track_static_pruned_positive_count`: `1`
  - `variant_sweep_zero_gap_skip_ratio_min`: `0.9478260869565217`
  - `variant_sweep_zero_gap_skip_ratio_max`: `0.9786856127886323`
  - `variant_sweep_track_static_pruned_ratio_min`: `0.0`
  - `variant_sweep_track_static_pruned_ratio_max`: `0.18232044198895028`
  - `residual_settle_case_count`: `4`
  - `contact_converged_ratio`: `0.99375`
- `first_actions`:
  - Use broadphase pair ratios and pruned-track-solve ratio to target pair pruning and contact warm starts in stable SSI windows.
  - Cache previous-step contact state as a Newton warm start for stable wheel-rail and SSI cases.
  - Split residual-settle time from solve time in SSI reports.
- `acceptance_signals`:
  - mean_coupling_iters reduced without lowering converged_ratio
  - adaptive_newton_call_count reduced by at least 10%
  - residual_settle_case_count unchanged or lower

### moving_load_kernel_warmup_observability

- `priority`: `P1`
- `domain`: `moving_load`
- `status`: `open`
- `headline`: Moving-load runtime observability is now coarse-grained, but warm-up skew and missing stage-level timers still block fast optimization loops.
- `optimization_hypothesis`: Warm-up and steady-state timers are now separated and the benchmark fast path is active, so the next gain is to keep the first-kernel path cheap while optimizing the steady-state moving-load path independently.
- `evidence`: 
  - `track_euler_elapsed_seconds`: `0.001316345999839541`
  - `track_timoshenko_elapsed_seconds`: `0.0013601470004687144`
  - `track_euler_warmup_elapsed_seconds`: `0.0007566660001430137`
  - `track_timoshenko_warmup_elapsed_seconds`: `0.0006830840002294281`
  - `track_euler_steady_state_elapsed_seconds`: `0.0005596799996965274`
  - `track_timoshenko_steady_state_elapsed_seconds`: `0.0006770630002392863`
  - `benchmark_fast_path_enabled`: `True`
  - `warmup_skew_ratio`: `1.1077202802127872`
  - `steady_state_skew_ratio`: `1.209732348138949`
  - `moving_load_integrator_elapsed_seconds`: `0.6193264630001067`
  - `moving_load_integrator_time_steps_per_second`: `775.0355082113088`
  - `moving_load_large_elapsed_seconds`: `1.2460488920041826`
  - `moving_load_large_time_steps_per_second`: `770.4352583275502`
  - `moving_load_large_cached_track_solve_inverse_enabled`: `True`
  - `moving_load_xlarge_elapsed_seconds`: `2.5050403800269123`
  - `moving_load_xlarge_time_steps_per_second`: `766.454710793673`
  - `moving_load_xlarge_cached_track_solve_inverse_enabled`: `True`
  - `moving_load_active_axle_count_mean`: `3.4375`
  - `moving_load_sparse_contact_step_ratio`: `0.0`
  - `vti_elapsed_seconds`: `0.04457676200036076`
  - `vti_time_steps_per_second`: `3589.3140914700157`
  - `integrator_residual_ratio`: `5.901887975897032e-06`
  - `integrator_max_residual`: `1.3377612745366605`
- `first_actions`:
  - Use the warm-up versus steady-state split to optimize the steady-state track LF path separately from first-kernel startup.
  - Batch axle-load interpolation and contact-force accumulation per time step.
  - Keep moving-load integrator and VTI coarse timers aligned with the track LF split.
- `acceptance_signals`:
  - warmup_skew_ratio materially reduced or explicitly isolated
  - moving-load reports expose elapsed seconds and per-step throughput
  - equilibrium_residual and energy balance remain green
