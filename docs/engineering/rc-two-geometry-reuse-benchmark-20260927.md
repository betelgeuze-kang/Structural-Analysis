# Two-geometry RC nonlinear reuse campaign

The source-bound [two-case plan](../../examples/research/rc_reuse_campaign/two-geometry-plan.json) ran the existing serial reuse campaign with two order-balanced repetitions and retained arithmetic. It reused four unchanged authored input files: the one-member, 3 m cantilever with seven reversing targets and a 600 kN constant axial load; and the three-member, 4 m by 3 m portal with two fixed bases, three reversing targets and two constant 25 kN roof loads. The portal uses the explicitly derived v3 two-fixed-endpoint request. These are two authored geometries and load histories, not independently sourced projects or physical tests.

The campaign completed both cases and exited zero. Each repetition ran line-search assembly reuse off and on, and each benchmark ran reference, deterministic secant, a second secant proposal arm, and fresh reference from its own genesis. The eight benchmarks therefore contain **32 full paths**, **160 accepted target solves**, 32 constant-load preloads, 200 native step artifacts and **200 core calls / 1,448 Newton iterations and linear solves**. Eight portal seeded attempts failed, rolled back exactly, and were followed by successful unseeded retries; they remain in the work and time totals. Every invocation reports known work, every full-history comparison passes, all reference/fresh-reference repeats are exact, and each off/on pair's original native step files match byte for byte. No learned policy was used.

| Case | Two paired whole-benchmark times, reuse off → on | Reuse/on ratio for the two observations | Actual Newton assembly dispatches, off → on | Reuse hits |
| --- | ---: | ---: | ---: | ---: |
| Cantilever concrete damage | 5.597 → 4.475 s | 0.799390, 0.799753 | 664 → 476 | 188 |
| Two-fixed-endpoint portal, 20 mm | 39.742 → 30.765 s | 0.774937, 0.773317 | 1,008 → 752 | 256 |

The time columns sum two order-balanced whole benchmarks **within each case**. Each whole benchmark includes all four full paths, validation, recording and serialization. The dispatch identities close exactly: 664 = 476 + 188 and 1,008 = 752 + 256. Cantilever work across both off/on pairs is 128 core calls / 744 solves; portal work is 72 calls / 704 solves. The campaign intentionally leaves `aggregate_speed_ratio=null`; the two cases have different geometry, history and cost. The enclosing process took **82.05 s** (`user=81.84 s`, `sys=0.19 s`, peak RSS 141,936 KiB); its interval includes interpreter startup and exit. The campaign timer recorded **80.619227438 s** through the final receipt boundary, including case intervals of 10.085406842 and 70.527944599 s. These scopes overlap and are not summed.

The execution root is `/tmp/rc-two-geometry-reuse-fj70sFgf`. Its `run/plan.json` SHA-256 is `66696b89da7be1713260961fb8fca3ce81a124dbb04344e3df4ebc8a431a626f`, `run/campaign.json` is `d1e653ffbf94f87abc3a168d43e2931df973625642fd0a15d5c54b98068b9ef2`, and the cantilever and portal `results/summary.json` values are `fe87f0afd255342dd4c095bc15e60a7a026aea8efd934e717c291da734bfb5c9` and `ebff215b6007c9663da38d31343d94f1f1b597bfed260507b80f13ea4c0b3fee`. A read-only recheck verified all four original model/request byte bindings against Git, all eight self-hashed comparison reports, their complete paths and work counters, and all off/on step equivalences. The entire local root has 1,276 files / 50,777,495 bytes; sorted `relative_path\0sha256_of_file\n` entries hash to `988dfd41f671776e26d0217fe54455695141c5a4f0c4705f52ae31aabe04fa16`.

The reported source revision is `49457f0709a4fef6a58fcfc288f7c6004d53a5d9`. The runner and experiment scripts match that revision's Git blobs and have respective SHA-256 values `89a963a86efbf98972db1cbe904528deac4a7465ce42c2e48894b76d59da971c` and `beae29c1f5f561110a3052d8145d049f980a23429f55d2f43e3df1c74018ca18`. The four bound model/request hashes are `b642e14a56ca88b74dfbbb6749f7b4b87199ef1aafb94c5265ec35b89eab7968`, `7b1892d1f14ae884e2afee366cc2304ed718acefa8260e2272f8677404ae703b`, `6f8eec155f5fcf2f9ae942c021a8692e79ae1efd0d1b98342f8aea0b642d0ed6` and `92e94d3580bdf76edabef458ac0f769e054087ab04f897178f3692b2098c0e45`. The new plan itself hashes to `abe473beb01c2c4fa467a7c06e7006142b9d88cda4a8b7d227059deb37ab373a`. The plan was uncommitted during execution, and no full imported-source archive was captured; the source revision label alone is not a clean-checkout attestation.

To repeat on a new output path from the repository root:

```sh
PYTHONPATH=.:src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  python3 scripts/run_rc_reuse_campaign.py \
  examples/research/rc_reuse_campaign/two-geometry-plan.json \
  /absolute/new/output-directory
```

This is a two-repeat, shared-host, assembly-timing-instrumented software observation. It broadens the deterministic multi-case benchmark beyond one geometry and gives a stronger baseline for future learned-policy comparisons. It does not establish hardware-general speedup, learned benefit, physical response accuracy, independent validation or design readiness. The portal's failed seeded trials were retained and source-bound but were not independently reassembled by this campaign.
