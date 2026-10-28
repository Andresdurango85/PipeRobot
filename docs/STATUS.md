# Status

Last updated: 2026-10-28 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Headless on CPU**: PushT gate on `ubuntu-latest` in ~2–3 min ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)); GPU runner pending Isaac |
| ≥ 50 episodes with seeds and scene variations | **Real on PushT** (50 seeded episodes, randomized start poses, CPU, ~5 min); SO-101 scenes pending ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)) |
| Statistical verdict vs. baseline | **Done**: `stats/gate.py` + `stats/baseline.json` ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done** in `pr-gate.yml` (sticky comment), with PushT videos of the first 10 episodes in the run artifact |
| Real-arm test, 20 attempts | Not started (Andrés is travelling, no hardware) |
| Deliberately worse PR blocked, normal PR passes | **Done with the real PushT policy**: #13 PASS (27/50), demo #14 BLOCK (sampling temperature 2.0, 4/50) |
| README reproducible in 30 min | Not started |

## Done recently

Older items are in git history and the ADRs (0001–0015: memory, tooling, statistics, rulesets,
security gates, hooks, mock gate, core boundary).

- 2026-10-27: first real evaluator, `lerobot/vqbet_pusht` in PushT on CPU
  ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). Same seeds reproduce only on one
  platform: CPUs flip 6–10 near misses per 500 episodes, CUDA is not reproducible at all
  ([lerobot.md](knowledge/lerobot.md)).
- 2026-10-27: `pr-gate` runs it on `ubuntu-latest` with CPU-only torch in ~2–3 min
  ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)); demo PR #14 (sampling
  temperature 2.0) was blocked at 4/50. Baseline re-measured on the runner: 265/500.
- 2026-10-28: `main` needs a PR and green checks but no approving review
  ([ADR 0018](decisions/0018-no-required-review-for-the-owner.md)); agents merge with a plain
  `gh pr merge --merge`.
- 2026-10-28: [Project Cangrejo](cangrejo/README.md), a crab-shaped robot as the gate's second
  robot; v0 (digital twin) can start now. Restructure plan accepted
  ([ADR 0019](decisions/0019-core-adapters-robots-layout.md)).

## Next

1. Restructure per ADR 0019 in three PRs: (1) allow-list architecture test and no default
   baseline in the core (this PR); (2) data into `robots/`; (3) the installable `piperobot`
   package with a clean-install check.
2. Create the crab's private repo (design files, its gate) and start v0 in Onshape.
3. A nightly run on rotating seeds, and a paired same-seed comparison to catch smaller drops; it
   must tolerate CPU-dependent near-miss flips or compare runs on the same logged CPU model.
4. Plan the Isaac Sim / Isaac Lab-Arena install on the home PC (ask before installing). The
   Isaac evaluator runs on CUDA: first measure whether deterministic torch settings make
   same-seed runs reproducible; it must call `policy.reset()` every episode, load normalization
   stats from the checkpoint and seed torch as well as the scene
   ([robot-learning-tutorial.md](learning/robot-learning-tutorial.md)).
5. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
6. Find out why Dependabot bumped `setup-uv` only to v7 (latest is v10).

## Open questions for Andrés

- Name of the new private repo for the crab's design files and its gate (ADR 0019).
- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
