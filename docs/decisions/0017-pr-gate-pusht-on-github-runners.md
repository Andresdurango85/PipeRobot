# 0017. pr-gate evaluates the PushT policy on GitHub-hosted runners, with CPU-only torch

- Status: Accepted
- Date: 2026-10-27

## Context

`pr-gate` ran the mock evaluator ([0014](0014-mock-evaluator-and-pr-gate-workflow.md)). A real
evaluator now exists: `lerobot/vqbet_pusht` in PushT on CPU, ~1.6 s per episode on the home PC
([0016](0016-real-evaluator-lerobot-pusht.md)). Two facts shape where it runs:

- PyPI's Linux torch wheels bundle CUDA (36 `nvidia-*` packages plus `triton` in `uv.lock`,
  several GB), useless on a runner without a GPU. Windows and macOS wheels are CPU-only.
- Same seeds give the same episodes only on the same platform: two Windows CPUs flip 6 of 500
  episodes, CPU vs CUDA flips 143 ([lerobot.md](../knowledge/lerobot.md)). A baseline is only
  comparable to runs on the platform where it was measured.

## Decision

- `pr-gate` runs `eval.lerobot_eval` with `policies/pusht-vqbet.json`: 50 episodes, seeds
  1000–1049, on CPU, on `ubuntu-latest`, against `stats/baselines/vqbet-pusht.json`. The mock
  stays for tests and local demos.
- torch and torchvision come from the PyTorch CPU index on Linux (`tool.uv.sources` with a
  `sys_platform == 'linux'` marker, `explicit = true`); Windows and macOS keep PyPI. They are
  listed directly in the `lerobot` and `sim-pusht` extras, pinned to the versions LeRobot already
  resolved, so the sources apply.
- The baseline is measured where the gate runs: `baseline.yml` (manual) runs N episodes on
  `ubuntu-latest` and uploads the results; the counts are committed to `stats/baselines/` by PR.
  Until that first run, the Windows-measured 263/500 is used. Every run logs the runner's CPU
  model.
- The prepared policy is cached with `actions/cache`, keyed on the policy spec, `uv.lock` and
  `eval/lerobot_policy.py`. Videos of the first 10 episodes go in the run's artifact, and failed
  episodes among them link to it.
- A policy spec may set `config_overrides` (config values changed without retraining). Its cache
  directory name includes a hash of them, so a prepared policy is never reused across overrides.
  The deliberately worse demo PR sets `bet_softmax_temperature` from 0.1 to 2.0.
- `pr-gate` stays on every PR: it is a required check, and a path filter would leave it pending.

## Alternatives considered

- Self-hosted runner on the home PC: faster and already matches the 263/500 baseline, but a
  public repo lets fork PRs run code on it. Revisit with its own security ADR when Isaac needs the
  GPU.
- PyPI's CUDA wheels on GitHub runners: several GB per install for a CPU-only job.
- A separate CPU-only extra with `tool.uv.conflicts`: extras could no longer be combined
  (`--extra lerobot --extra sim-pusht`); a platform marker is enough today.

## Consequences

- Sampling temperature on the home PC CPU, 50 episodes vs the 263/500 baseline: 0.5 gives 26/50
  (PASS), 1.0 gives 20/50 (WARN, −12.6 pp), 2.0 gives 5/50 (BLOCK), 5.0 gives 1/50 (BLOCK). A
  50-episode run misses a drop like the one at 1.0, as ADR 0016 predicts.
- GitHub-hosted runners do not guarantee one CPU model, so a no-op PR may flip a few near-miss
  episodes between runs. That is harmless for the unpaired gate (BLOCK needs ~−15 pp) but a paired
  same-seed comparison must check the logged CPU model.
- A Linux machine with a GPU (e.g. for Isaac) would also get CPU-only torch from this marker; it
  needs its own source (a CUDA extra) when that machine exists.
- Docs-only PRs also pay the evaluation (~minutes per PR).
