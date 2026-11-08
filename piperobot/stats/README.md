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

## Repeatability admission check

Evaluate one checkpoint twice in fresh processes, then run:

```
python -m piperobot.stats.repeatability --first first.json --second second.json --json
```

Policy strings and seed sets must agree. Initial and final digest presence must agree between
files; a contract mismatch is invalid input. Re-run after evaluator or simulator upgrades.

| Evidence | Verdict | Recommended gate | Exit |
| --- | --- | --- | ---: |
| Any outcome or supplied digest mismatch | NOT_REPEATABLE | Unpaired Wilson/Newcombe (ADR 0003) | 1 |
| Outcomes match, no final digests | UNVERIFIED | None; caller decides | 3 |
| Outcomes and final digests match, initial digests also match if supplied | REPEATABLE | Paired (ADR 0032) | 0 |
| Invalid input or arguments | Error | None | 2 |

Exit 1 is a finding, not a crash: the check ran and the task must use the unpaired gate.

An outcome mismatch alone conclusively disproves repeatability. Identical outcomes alone do not
prove episodes reproduce: add final digests to the evaluator. Text is the default; `--json`
emits one object with verdict, gate, seed count, matching outcome/final/initial counts (null for
absent digests), up to ten sorted mismatched seeds, and a reason.

## Continuous metric summary

`metric.py` summarizes optional episode metrics with count, median, p90 and IQR (q75 - q25).
Quantiles use Hyndman-Fan type 7 linear interpolation, including singleton inputs (IQR zero).
Reports warn when `abs(threshold - median) <= IQR`, including equality with zero IQR.
The optional `metric_spec` names the metric, unit, finite threshold and direction (below/above).
It describes the threshold without deriving success: a task may have additional conditions.
