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
| Real-arm test, 20 attempts | Not started: arm printed, electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md), `so101` dependency group and manual-outcome adapter ready ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)) |
| Deliberately worse PR blocked, normal PR passes | **Done with the real PushT policy**: #13 PASS (27/50), demo #14 BLOCK (sampling temperature 2.0, 4/50) |
| README reproducible in 30 min | Not started |

## Done recently

Older items are in git history and the ADRs (0001–0019: memory, tooling, statistics, rulesets,
security gates, hooks, mock gate, core boundary, PushT evaluator and gate, no required review,
Project Cangrejo, the `piperobot` package).

- 2026-11-01: the gate is the installable `piperobot` package with a `clean-install` CI job
  ([ADR 0019](decisions/0019-core-adapters-robots-layout.md)).
- 2026-11-01: self-hosted GPU runner on the home PC and the non-required `gpu-smoke` workflow
  ([ADR 0020](decisions/0020-self-hosted-gpu-runner.md)).
- 2026-11-01: SO-101 bring-up runbook for LeRobot 0.6.1
  ([so101-bringup.md](knowledge/so101-bringup.md)); hardware steps unverified.
- 2026-11-01: `so101` dependency group (LeRobot's `feetech`, `hardware`, `viz`, `training`), no
  Hub uploads from the real arm, Developer Mode for training, and
  `piperobot.adapters.manual.evaluate` to turn hand-scored attempts (CSV) into gate results
  ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)).
- 2026-11-01: Isaac Lab 3.0 + Isaac Sim 6.2 installed natively on the home PC, without Arena
  (Linux-only). Headless RTX rendering works, Isaac Lab ships an SO-101 task, and same-seed runs
  are bit-identical (random actions, no camera, no policy)
  ([ADR 0021](decisions/0021-isaac-lab-3-on-windows-without-arena.md),
  [isaac.md](knowledge/isaac.md)).

## Next

1. Andrés turns on Windows Developer Mode on the home PC before the first training run
   ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)).
2. Start the crab's v0 in Onshape, in its private repo.
3. A nightly run on rotating seeds, and a paired same-seed comparison to catch smaller drops; it
   must tolerate CPU-dependent near-miss flips or compare runs on the same logged CPU model.
4. Isaac: test rendering in the runner's service (session 0); then port the course's
   tube-to-rack task to Isaac Lab 3.0 and write the evaluator, re-checking reproducibility with
   cameras and a policy in the loop ([isaac.md](knowledge/isaac.md),
   [robot-learning-tutorial.md](learning/robot-learning-tutorial.md)).
5. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
6. Find out why Dependabot bumped `setup-uv` only to v7 (latest is v10).

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
