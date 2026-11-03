# Status

Last updated: 2026-11-02 (home PC)

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

- 2026-11-03: the course's tube-to-rack scene runs on Isaac Lab 3.0's SO-101 asset at the
  course pose with the course's gains; assets are fetched by sha256 outside the repo; the success
  term is ported with a 5 N grasp threshold and a slot-depth rule; registered sensing checks pass
  ([ADR 0028](decisions/0028-so101-scene-gains-and-mount.md)). Replays with contacts vary run to
  run (2/75 outcomes).
- 2026-11-03: success-rate history, core part: `piperobot/reports/history.py` appends one record
  per evaluation to an append-only `history.json` and renders a static page (inline SVG, no JS);
  `piperobot/platform_info.py` labels the CPU like `pr-gate`
  ([ADR 0026](decisions/0026-success-rate-history-data-branch-and-pages.md)). `history.yml`
  evaluates each relevant push to `main`, appends to the `history` branch and deploys to Pages;
  `pr-gate` and `baseline` now label the CPU with the same helper. Live since 2026-11-03 at
  <https://andresdurango85.github.io/PipeRobot/> (first point 29/50, PASS).
- 2026-11-03: mypy --strict also checks `tests/` (except the SO-101 tests, which join with
  `robots/` later), and tolerances and confidences print exactly ("12.5 pp", "97.5%")
  ([testing.md](knowledge/testing.md)).
- 2026-11-03: CI hardening. `gpu-smoke` runs on push, never on PRs; a job-started hook on the
  runner skips the steps of any job that is not one of our self-hosted workflows on a push,
  dispatch or schedule, and ends the job's worker so not even `if: always()` steps run; a
  job-completed hook wipes the workspace; the runner folder's ACL no longer lets every local
  account read or write it; every action is pinned by SHA, and the repo allows only GitHub's and
  two listed actions; zizmor runs in CI and the hooks; OpenSSF Scorecard runs weekly (6.3)
  ([ADR 0027](decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md),
  [ADR 0029](decisions/0029-refused-jobs-end-their-worker-and-workspaces-are-wiped.md),
  [ci.md](knowledge/ci.md)).
- 2026-11-02: Hypothesis property tests and weekly mutation testing (`mutation.yml`, Linux) for
  `piperobot/stats`. **Gate verdicts change**: a drop of exactly the tolerance (e.g. 35/50 vs
  40/50) could WARN through float rounding; it now PASSes, as ADR 0004 says (only WARN → PASS
  at the exact boundary; no 50-episode verdict against a committed baseline changes). Also
  fixed: a NaN tolerance, float or bool counts, and non-integer baselines were accepted silently
  ([testing.md](knowledge/testing.md)).
- 2026-11-02: mypy --strict checks the `piperobot` package on push and in CI (`type-check`
  job); it found no errors in our own code
  ([ADR 0025](decisions/0025-mypy-strict-type-checking.md), [testing.md](knowledge/testing.md)).
- 2026-11-02: the Isaac Lab 3.0 SO-101 asset passed the object-free go/no-go on the course's
  75 demos (all grasps and releases in the course's tube and rack regions, no limit hits), and
  the course dataset's real rate is 60 Hz despite its 30-fps label, measured by replaying it with
  the course's gains ([ADR 0024](decisions/0024-so101-demo-replay-go-no-go-and-control-rate.md),
  [isaac.md](knowledge/isaac.md)).
- 2026-11-02: Codex CLI writes the code and the Claude sessions (one orchestrator, several
  workers in their own worktrees) brief it and review its diff
  ([ADR 0023](decisions/0023-codex-writes-code-claude-reviews.md), recipe in
  [ci.md](knowledge/ci.md)).
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

1. Start the crab's v0 in Onshape, in its private repo.
2. A nightly run on rotating seeds, and a paired same-seed comparison to catch smaller drops; it
   must tolerate CPU-dependent near-miss flips or compare runs on the same logged CPU model.
3. Isaac: the `piperobot.adapters.isaaclab` evaluator on the tube-to-rack scene (lazy Isaac
   imports, task data in `robots/so101/envs/`, results contract, `failure` from the success
   tracker), Codex coding. First measure same-seed repeatability with contacts (2/75 outcomes
   flipped between runs, [ADR 0028](decisions/0028-so101-scene-gains-and-mount.md)) and whether
   PhysX's enhanced determinism or a fresh process per episode fixes it; then per-episode
   randomization with seeds, cameras, and a policy in the loop.
4. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
5. CI: check that Monday's Dependabot run works under the new Actions permissions, fix its
   failing `uv` job (torch/torchvision, [ci.md](knowledge/ci.md)), and ask Andrés to add `zizmor`
   to the ruleset's required checks.
6. After the SO-101 scene PR: put `robots/` and the excluded SO-101 tests under mypy strict;
   after a few weekly `mutation.yml` runs, decide a mutation-score threshold
   ([testing.md](knowledge/testing.md)).

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
