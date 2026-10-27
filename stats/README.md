# stats

Success-rate comparison against the stored baseline, with confidence intervals.

`gate.py` decides the PR verdict from two pass/fail counts (candidate and baseline):

- **Wilson score interval** for each success rate.
- **Newcombe hybrid score interval** for the difference `candidate - baseline`.
- **BLOCK** if the whole difference interval is below zero (confident regression),
  **WARN** if the observed drop exceeds `--tolerance` (default 10%) but is not significant,
  **PASS** otherwise. Exit code is 1 only on BLOCK.

```
uv run python -m stats.gate --candidate 38/50 --baseline 45/50
uv run python -m stats.gate --results out/results.json --baseline-file stats/baseline.json
```

`baseline.json` holds the mock policy's baseline; `baselines/<policy>.json` holds real ones (e.g.
`baselines/vqbet-pusht.json`). All are counts plus provenance, loaded by `baseline.py`.
Exit codes: 0 PASS/WARN, 1 BLOCK, 2 invalid input files.

## What 50 episodes can and cannot detect

Seeded simulation, baseline success rate 80%, 95% confidence, candidate evaluated with 50 episodes:

| Baseline episodes | Unchanged policy blocked | 80% → 70% blocked | 80% → 60% blocked | 80% → 50% blocked |
|---|---|---|---|---|
| 50  | ~2% | ~22% | ~59% | ~89% |
| 200 | ~2% | ~34% | ~82% | — |

With 50 episodes per PR the gate reliably catches large regressions (≥ 30 points) and rarely
blocks a good PR. Small regressions need more episodes; a larger baseline (e.g. built nightly)
is the cheapest way to gain power, since it is evaluated once and reused by every PR.
