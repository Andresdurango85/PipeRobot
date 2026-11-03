# 0036. The SO-101 gate evaluates the scripted policy on 100 fixed seeds

- Status: Accepted
- Date: 2026-11-03

## Context

The SO-101 gate ([0035](0035-so101-gate-on-the-self-hosted-runner.md)) evaluates the replay of
the course's demos, which succeeds 6/75: the paired test can block only a total collapse, as the
registered weak-grip demo showed (#60: 0/75, p = 1/64). The scripted privileged-state policy
passed its registered go/no-go at 43/50
([0034](0034-so101-scripted-privileged-state-policy.md)) and was proposed as the gate's policy,
with a 500-seed baseline (100000-100499) and PR seeds drawn from it. With one Isaac worker
(~25 s per seed) every seed costs runner time; the evaluator gains concurrent workers in a
separate change, accepted only after a registered repeatability test.

## Decision

This supersedes 0035's "Gate policy and power" section and its baseline file names. The rest of
0035 (trust boundary, hosted reporter, platform guard, fail-closed baseline, concurrency) stands.

### Policy, seeds and baseline

- The gate evaluates `robots/so101/policies/scripted_pick_place.json` on
  `robots/so101/envs/vials_to_rack_task_randomized.json`, seeds **100000-100099**, one Isaac
  process per seed ([0033](0033-so101-isaac-evaluator-one-process-per-seed.md)).
- The baseline is the **same 100 seeds**: `robots/so101/baselines/scripted-pick-place.json` and
  `scripted-pick-place-episodes.json`, measured by the workflow's baseline mode on the runner.
  Pairing stays strict (identical seed sets); there is no subset pairing.
- **Why 100 and not 0034's 500**: while every PR runs the same fixed seeds, the other 400 seeds
  of a 500-seed baseline are never read by the paired test. They would cost 1.8-3.5 h of runner
  time, subset pairing, and shards merged across dispatches, for no power. 100 seeds take ~27
  minutes of evaluation with two workers at the baseline rate.
- The comment states what the policy is: "Privileged-state scripted policy: measures the
  simulated pipeline and regressions, not a deployable policy (ADR 0034)" (0034, Consequences).
- The replay, its specs and its baseline stay in the repository as the evaluator's acceptance
  test and the fallback policy (0034); the gate no longer reads them.

### Workers and the 30-minute budget

- The evaluate job runs up to two concurrent Isaac workers. The GPU preflight picks the largest
  count that fits the free VRAM (`VRAM_PER_WORKER_MB` each); when only one fits, it runs one,
  with a warning.
- **The seeds never depend on the worker count**: the fallback runs the same 100 seeds, over the
  30-minute Phase 0 budget, so the power is fixed. The 30-minute criterion is met only on the
  two-worker path, which needs ~8.7 GB of free GPU memory; a desktop session holding ~11 of the
  16 GB forces the fallback (the baseline run fell back to one worker).
- `workers` is recorded in `run_metadata.json` but is not a guarded platform key: the registered
  repeatability test (sequential vs two workers, 0 flips, identical fingerprints) is what allows
  a fallback run to be paired with a two-worker baseline. If that test ever fails, this rule is
  void.
- **A failed episode costs about twice a successful one**: it runs the full 600-step horizon
  (baseline run 41707984345: median 25 s per success, 43-57 s per failure). Wall time therefore
  grows with the regression a PR introduces. The evaluate step times out at 120 minutes and the
  job at 130, in both modes: sized for 100 failed seeds on one worker (~95 min, plus retries),
  because a timeout must never stand in for a verdict. A timed-out or failed `evaluate` skips
  `report`, so the check is red with no verdict, never a PASS.

### Baseline measured on the swap branch

- The swap PR is pushed without baseline files (the gate then finds none on main and only writes
  a note), the baseline is dispatched on that branch, and its artifact is committed into the
  same PR, whose gate run must PASS with no discordant episode. The gate is never without a
  baseline on main.
- The platform guard does not detect code drift. The branch must be up to date with main when
  the baseline is dispatched; a gate-relevant merge on main before the swap merges means
  updating the branch and measuring again. The same rule holds for any later baseline measured
  on a branch.

### Power

Exact one-sided McNemar at α = 0.025, computed with `piperobot.stats.paired`: the smallest
number of lost episodes `b` that blocks, given `c` gained episodes.

| Gained `c` | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Lost `b` needed | 6 | 8 | 10 | 12 | 13 | 15 | 17 |

- A change that only removes successes (c = 0) blocks once it loses 6 of the 100 seeds, a 6 pp
  drop on a reference near 86%.
- A general parameter change moves trajectories on every seed (0033: any perturbation changes
  fingerprints), so it can rescue some seeds while it breaks others; c > 0 is the normal case for
  a policy edit, and the threshold climbs about 2 lost episodes per gained one. The registered
  BLOCK demo uses a monotone mechanism (a looser gripper) so that c stays near 0 and the
  prediction is sharp.
- The comment shows `b`, `c`, the exact p and the difference with its interval, so a reader sees
  how close a PASS was.

### Baseline result

- Run 41707984345 (commit eed0025, one worker, 0 retries, no platform difference): **78/100**.
- All 22 failures are `not_placed`, and 16 of them hit the wrist_flex joint limit: the scripted
  policy's known failure mode (0034), a property of the policy, not a gate defect.
- The rate is below 0034's 43/50 on other seeds, but the two overlap: 95% Wilson intervals
  0.69-0.85 and 0.74-0.93.

## Alternatives considered

- **500-seed baseline with PR seeds as a subset (0034's proposal)**: no consumer for the extra
  seeds while PR seeds are fixed (above).
- **Rotating PR seeds within a 500-seed pool**: each PR, or a nightly, would draw different seeds,
  which limits tuning a policy against seeds visible in the comment, at the cost of per-PR
  reproducibility. It needs subset pairing in the comment (filter the reference to the
  candidate's seeds, error on a seed outside it), a baseline measured in shards and merged
  (disjoint ranges covering the pool, same commit and platform), and one concurrency group per
  shard (GitHub cancels an older pending run in a group). A later option; a nightly over the pool
  would be its first consumer.
- **50 seeds when only one worker fits**: keeps the budget but halves the power (c = 0 then needs
  a ~12 pp drop) and makes the verdict depend on the desktop's VRAM use.
- **Measuring the baseline on main after the swap merges**: leaves the gate without a baseline
  between the two PRs.

## Consequences

- Phase 0's 30-minute budget holds only with two workers: ~27 minutes of evaluation at the
  baseline rate. With one worker a run takes 52 minutes at 78% (the baseline run) and up to
  ~95 minutes if every seed fails. Whether the desktop leaves ~8.7 GB free during gate runs is
  the owner's open decision.
- A possible later lever, not part of this decision: ending an episode early once the tube is
  irrecoverable. It changes what an episode is, so it needs its own ADR and a new baseline.
- A change to the task, the randomization, the success tracker or the evaluator needs the
  baseline measured again (and voids 0034's go/no-go).
- The gate still measures a privileged-state policy in simulation; ACT replaces it through the
  same pipeline when it exists.
- The scripted policy's dominant failure mode (wrist_flex at its limit, 0034) is part of the
  baseline; a fix to it shows up as gained episodes.
