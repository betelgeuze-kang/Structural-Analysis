# Smaller steps descend along the failed two-story Newton direction

Following the [iteration diagnostic](planar-two-story-failure-diagnostic-20260914.md),
one separate API execution repeated the same dense problem using its frozen
`29af2b0f9bcd481058cae1cabb192b91f65c4506` source. Source/input identities were
checked first. A wrapper captured the problem and coordinates at the rejected
line search, without altering its returned value. Public result bytes again
match original high-load slot 0000 exactly.

After that API execution finished, 21 separate assembly calls examined only the
captured trial state. These calls are additional diagnostic work, outside the
original benchmark and outside its API timing. They took 1.165180476 s. Complete
vectors, tangent, original line-search trials and individual diagnostic residuals
are retained in the packet referenced by the
[machine summary](planar-two-story-direction-20260914.summary.json).

The original six candidates end at alpha 1/32 and all reject. Every additionally
probed alpha from 1/64 through 1/65536, halving each time, reduces the original
residual infinity norm. The first extra candidate therefore supplies a descent
point that the fixed default schedule did not test. This point was not accepted
as a step or published as an engineering solution.

The linear equation relative error `norm(K*d+r, inf)/norm(r, inf)` is
1.1269708460687212e-14. Central directional finite differences at alpha 1e-4 and
1e-5 differ from `K*d` by relative infinity-norm errors 1.86669e-6 and 6.10140e-7.
Smaller finite-difference intervals become less accurate; all forward, backward
and central estimates remain in the receipt. These local checks do not establish
global tangent correctness or prove convergence of a continued path.

Reassembling the original coordinates after the probes returns exactly the
original residual and tangent. All retained parent/accepted checkpoint bytes are
unchanged. No tolerances, input, accepted path or default solver policy changed.

The next bounded experiment can test an explicitly longer line-search schedule
with the same residual/increment gates and complete attempt costs. Reducing one
residual is not enough to promote that policy: it must still complete the path,
retain full response/history checks and account for new failures and extra work.
This is a generated numerical diagnosis, not independent physical validation,
learned gain or roadmap completion.
