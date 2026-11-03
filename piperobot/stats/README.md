# stats

Success-rate comparison against the stored baseline, with confidence intervals.

`gate.py` decides the PR verdict from two pass/fail counts (candidate and baseline):

- **Wilson score interval** for each success rate.
- **Newcombe hybrid score interval** for the difference `candidate - baseline`.
- **BLOCK** if the whole difference interval is below zero (confident regression),
  **WARN** if the observed drop exceeds `--tolerance` (default 10%) but is not significant,
  **PASS** otherwise. Exit code is 1 only on BLOCK.

```
uv run python -m piperobot.stats.gate --candidate 38/50 --baseline 45/50
uv run python -m piperobot.stats.gate --results out/results.json --baseline-file robots/mock/baseline.json
```

Baselines are per-robot data in [`robots/`](../../robots/README.md) (e.g.
`robots/pusht/baselines/vqbet.json`): counts plus provenance, loaded by `baseline.py`.
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

## Paired same-seed comparison

`paired.py` pairs two results files by seed (identical seed sets are required).
Run both policies under the same reproducible conditions, including CPU and scene
variations. Only discordant episodes inform the one-sided exact McNemar test:
**BLOCK** when p < alpha (default 0.025), otherwise **WARN** when the observed
loss exceeds the tolerance (default 10 pp), else **PASS**. The paired Newcombe
hybrid score interval at confidence `1 - 2*alpha` is reported only; it does not
decide the verdict. Alpha must be in (0, 0.5).

```
python -m piperobot.stats.paired --reference reference.json --candidate candidate.json
```

Exit codes: 0 PASS/WARN, 1 BLOCK, 2 invalid input or arguments.
