# 0031. A nightly paired run on rotating seeds, decided by an exact McNemar test

- Status: Accepted
- Date: 2026-11-03

## Context

`pr-gate` evaluates 50 episodes on the fixed seeds 1000–1049 and compares the count, unpaired,
with the stored 265/500 ([0003](0003-statistical-gate-wilson-newcombe.md),
[0017](0017-pr-gate-pusht-on-github-runners.md)). Two weaknesses:

- **Fixed seeds invite overfitting.** Every change is judged on the same 50 episodes; a change
  tuned to them, even by accident, passes.
- **Unpaired 50 vs 500 is blunt.** The Newcombe interval only rules out drops of roughly 20 pp or
  more.

When two policies run on the same seeds, episodes where both succeed or both fail say nothing
about the difference; only the discordant ones do. PushT on CPU is bit-reproducible on one
runner, so an unchanged policy gives zero discordant episodes. Across runners it is not: 6–10 of
500 near-miss episodes flip, and the logged CPU model does not predict which (two runners that
both logged "AMD EPYC 9V74" disagreed on 10 episodes; [lerobot.md](../knowledge/lerobot.md)).
`piperobot.stats.paired` (PR #47) implements the paired decision.

## Decision

1. **A nightly workflow** (`nightly.yml`, `ubuntu-latest`, never self-hosted, `contents: read`)
   evaluates two arms on the **same 500 fresh seeds, in the same job**, one after the other:
   - the **reference**: the repository at the commit recorded in
     `robots/pusht/baselines/vqbet.json` (`"commit"`), with its own `uv.lock`;
   - the **candidate**: `main` HEAD.
   The first seed rotates daily, `100000 + 500 × days since 2026-01-01` (`piperobot.seeds`), so
   ranges never repeat and never overlap the gate's 1000–1499. Dispatch inputs can change the
   episode count and the first seed.
2. **The reference is fixed**, refreshed only with an explicit baseline refresh (baseline.yml,
   then a PR that updates `vqbet.json`). Comparing with yesterday's `main` instead would let small
   drops pile up unseen, one acceptable step at a time (the boiling-frog problem).
3. **Paired verdict** (`piperobot.stats.paired`): with `b` episodes the reference solved and the
   candidate lost and `c` the reverse, the exact one-sided McNemar p-value
   `P(X >= b)`, `X ~ Binomial(b + c, 1/2)`. **BLOCK** if p < 0.025 (the same 2.5% tail as the
   95% two-sided intervals of 0003); **WARN** if not significant but the paired drop
   `(b − c) / N` exceeds the 10 pp tolerance ([0004](0004-warn-tolerance-in-percentage-points.md));
   **PASS** otherwise. Newcombe's paired interval is reported in pp but does not decide.
4. **The unpaired comparison** of the candidate's fresh seeds with the committed counts is
   reported as well, informational only: it is the overfitting signal (a fixed-seed rate that
   fresh seeds do not confirm).
5. **A nightly BLOCK is an alert, never a merge block.** The verdict job fails, so GitHub emails
   the owner. Triage: a rerun on the same seeds only reproduces the result (CPU PushT is
   deterministic within a runner); the real check is the next nights' fresh seeds, or a paired
   dispatch with more episodes.
6. **Nightly only evaluates and alerts.** It uploads a fixed artifact, `nightly-evaluation`
   (`reference.json`, `candidate.json`, `reference_commit.txt`, `candidate_commit.txt`,
   `platform.txt`, `evaluated_at.txt`, and the raw `/proc/cpuinfo` flags line in
   `cpu_flags.txt`). Signing it and appending it to the history page as a `nightly` series is
   done by the reusable `certify.yml` from the success-rate history work, which recomputes the
   paired record from those files in the signing job.

## Alternatives considered

- **Pair against committed per-episode outcomes** (one arm, half the time): cross-runner flips
  would be false discordances, and 6 one-way flips alone reach p = 1/64 < 0.025.
- **Pair only runs whose logged CPU model matches**: unsafe, since the model name does not
  predict the flips.
- **Yesterday's `main` as reference**: catches day-to-day changes but not slow drift (decision 2).
- **Let the interval decide**, as gate.py does: Newcombe's paired interval and the exact test can
  disagree at the edge. With 5 losses and no gains in 500 the interval is [−0.019, −0.001],
  entirely below zero, while p = 1/32: the exact test decides, so the verdict is PASS. The
  interval is shown for scale, not as a verdict.
- **250 episodes per arm**: half the time, half the power. Hosted minutes are free for a public
  repo and a nightly is not latency-bound; the dispatch input can drop to 250 if runs grow.

## Consequences

- **Power**: an unchanged `main` gives b = c = 0 every night, so it never raises a false BLOCK.
  A real change shows up as discordant pairs: 6 losses and no gains (1.2 pp at 500 episodes)
  already BLOCK (p = 1/64), against ~20 pp for pr-gate's unpaired check.
- **False alarms**: once `main` differs from the reference without a real effect (a neutral
  refactor or dependency bump), each night re-tests that difference on fresh seeds at α = 0.025,
  so roughly one false BLOCK every 40 nights, about 9 a year, until the reference is refreshed.
  Hence decision 5.
- About 50 minutes of hosted runner time per night (two arms of ~22 min, two installs).
- The reference commit's evaluator CLI (`piperobot.adapters.lerobot.evaluate`) must keep
  working for as long as that commit is the reference; a baseline refresh moves it forward.
- GitHub disables scheduled workflows after 60 days without repository activity.
- A paired mode for pr-gate (reference arm on 1000–1049 in the same job) is a later decision,
  after the nightly has run for a while.
