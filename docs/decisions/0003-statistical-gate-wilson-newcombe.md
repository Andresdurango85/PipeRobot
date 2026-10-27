# 0003. Gate verdict from Wilson and Newcombe intervals

- Status: Accepted
- Date: 2026-10-26

## Context

Each evaluation is a series of independent pass/fail episodes, so a success rate is a binomial
proportion. With ~50 episodes per PR, random variation is large (about 10 to 14 pp either way),
and a naive "candidate rate < baseline rate" rule would block good PRs all the time: a flaky gate.

## Decision

Implemented in `stats/gate.py`:

- Wilson score interval for each success rate.
- Newcombe hybrid score interval (method 10, Newcombe 1998) for `candidate - baseline`, so the
  uncertainty of the baseline run counts too.
- **BLOCK** (exit 1) when the whole difference interval is below zero at 95% confidence;
  **WARN** when the observed drop exceeds the tolerance
  ([0004](0004-warn-tolerance-in-percentage-points.md)) but is not significant; **PASS** otherwise.
- The baseline is stored as counts (successes/trials), not only as a rate.

## Alternatives considered

- Normal (Wald) interval: wrong coverage for small n and rates near 0 or 1; can leave [0, 1].
- Comparing the candidate interval with the baseline point estimate: ignores baseline noise.
- Fisher's exact test: gives a p-value but no interval to show in the PR comment.
- Bayesian (Beta posteriors): sound, but harder to explain in a PR comment; can revisit later.

## Consequences

- When the policy is unchanged, the gate blocks ~2% of PRs (simulated, n = 50 each side).
- With 50 episodes per side it reliably catches only large regressions (80% to 50% is blocked
  ~89% of the time; 80% to 70% only ~22%). See the power table in
  [`stats/README.md`](../../stats/README.md).
- The cheapest way to gain power is a larger baseline (e.g. 200 episodes, built nightly), since it
  is evaluated once and reused by every PR.
- Verified against Newcombe's published examples in `tests/test_gate.py`.
