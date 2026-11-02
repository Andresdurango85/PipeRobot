# Status

Last updated: 2026-11-01 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Done for PushT**: `gpu-smoke` on the self-hosted RTX runner, ~2–3 min per PR, not a gate ([ADR 0020](decisions/0020-self-hosted-gpu-runner.md)); the gate stays on CPU ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)). Isaac's time on it not yet measured |
| ≥ 50 episodes with seeds and scene variations | **Real on PushT** (50 seeded episodes, randomized start poses, CPU, ~5 min); SO-101 scenes pending ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)) |
| Statistical verdict vs. baseline | **Done**: `piperobot/stats/gate.py` + `robots/pusht/baselines/vqbet.json` ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done** in `pr-gate.yml` (sticky comment), with PushT videos of the first 10 episodes in the run artifact |
| Real-arm test, 20 attempts | Not started: arm printed, electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md) |
| Deliberately worse PR blocked, normal PR passes | **Done with the real PushT policy**: #13 PASS (27/50), demo #14 BLOCK (sampling temperature 2.0, 4/50) |
| README reproducible in 30 min | Not started |

## Done recently

Older items are in git history and the ADRs (0001–0015: memory, tooling, statistics, rulesets,
security gates, hooks, mock gate, core boundary; 0018: no required review, agents merge with
a plain `gh pr merge --merge`).

- 2026-10-27: first real evaluator, `lerobot/vqbet_pusht` in PushT on CPU
  ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). Same seeds reproduce only on one
  platform: CPUs flip 6–10 near misses per 500 episodes, CUDA is not reproducible at all
  ([lerobot.md](knowledge/lerobot.md)).
- 2026-10-27: `pr-gate` runs it on `ubuntu-latest` with CPU-only torch in ~2–3 min
  ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)); demo PR #14 (sampling
  temperature 2.0) was blocked at 4/50. Baseline re-measured on the runner: 265/500.
- 2026-10-28: [Project Cangrejo](cangrejo/README.md), a crab-shaped robot as the gate's second
  robot; v0 (digital twin) can start now. Restructure plan accepted
  ([ADR 0019](decisions/0019-core-adapters-robots-layout.md)).
- 2026-11-01: ADR 0019 PRs 1 and 2 done: allow-list architecture test, no default baseline in the
  core, and per-robot data in [`robots/`](../robots/README.md) (policy specs, baselines, SO-101
  envs). The crab's private repo exists.
- 2026-11-01: self-hosted GPU runner on the home PC (native Windows, dedicated unprivileged
  user, trusted code only; fork PRs need approval for all external contributors) and the
  non-required `gpu-smoke` workflow: 50 PushT episodes on CUDA, job in ~2 min warm
  ([ADR 0020](decisions/0020-self-hosted-gpu-runner.md), [ci.md](knowledge/ci.md)).
- 2026-11-01: SO-101 bring-up runbook for LeRobot 0.6.1 on Windows, checked against the installed
  package ([so101-bringup.md](knowledge/so101-bringup.md)); the hardware steps are unverified
  until the electronics arrive.
- 2026-11-01: ADR 0019 done: the gate is the installable `piperobot` package (core + adapters,
  `uv_build`, flat layout) with a `clean-install` CI job; `dataset_stats.py` moved to
  `robots/so101/tools/`. Coded by Codex, reviewed by Claude ([ci.md](knowledge/ci.md)).

## Next

1. Dispatch `baseline.yml` with 50 episodes to confirm the moved evaluator (ADR 0019).
2. Start the crab's v0 in Onshape, in its private repo.
3. A nightly run on rotating seeds, and a paired same-seed comparison to catch smaller drops; it
   must tolerate CPU-dependent near-miss flips or compare runs on the same logged CPU model.
4. Isaac Lab 3.0 + Isaac Sim 6.2 are installed on the home PC, outside the repo, and pass the
   smoke tests: headless RTX rendering, the bundled SO-101 cube-stack task, bit-identical
   same-seed runs, LeRobot 0.6.1 in-process
   ([ADR 0021](decisions/0021-isaac-lab-3-on-windows-without-arena.md),
   [isaac.md](knowledge/isaac.md)). Next: test rendering inside the runner's service (session 0),
   then port the course's tube-to-rack task to Isaac Lab 3.0 and write the evaluator. It must call
   `policy.reset()` every episode, load normalization stats from the checkpoint, seed torch as
   well as the scene, and re-check reproducibility with cameras and a policy in the loop
   ([robot-learning-tutorial.md](learning/robot-learning-tutorial.md)).
5. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
6. Find out why Dependabot bumped `setup-uv` only to v7 (latest is v10).

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?
- How do the SO-101 hardware deps (LeRobot extras `feetech`, `hardware`, `viz`, `training`) enter
  `pyproject.toml`: extras or a dependency group (ADR 0019)? Install only after that.
- Enable Windows Developer Mode on the home PC? `lerobot-train` needs symlinks
  ([so101-bringup.md](knowledge/so101-bringup.md#11-train-act-locally-on-the-gpu)).

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
