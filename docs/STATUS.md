# Status

Last updated: 2026-11-03 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Done for PushT**: `gpu-smoke` on the self-hosted RTX runner, ~2–3 min per PR, not a gate ([ADR 0020](decisions/0020-self-hosted-gpu-runner.md)); the gate stays on CPU ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)). **SO-101**: `so101-gate` on the same runner, 75 seeds paired against a same-runner baseline, ~26.5 min per run (setup 32 s warm), not a required check ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md)) |
| ≥ 50 episodes with seeds and scene variations | **Real on PushT** (50 seeded episodes, randomized start poses, CPU, ~5 min) ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). **SO-101 on Isaac**: evaluator runs 75 seeds, one process each, ~20 s per seed, repeatable bit for bit; a scripted privileged-state policy on the seeded randomized layout passed its registered go/no-go, 43/50, ~25 s per seed ([ADR 0033](decisions/0033-so101-isaac-evaluator-one-process-per-seed.md), [ADR 0034](decisions/0034-so101-scripted-privileged-state-policy.md)) |
| Statistical verdict vs. baseline | **Done**: `piperobot/stats/gate.py` + `robots/pusht/baselines/vqbet.json` ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done** in `pr-gate.yml` (sticky comment), with PushT videos of the first 10 episodes in the run artifact |
| Real-arm test, 20 attempts | Not started: arm printed, electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md), `so101` dependency group and manual-outcome adapter ready ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)) |
| Deliberately worse PR blocked, normal PR passes | **Done with the real PushT policy**: #13 PASS (27/50), demo #14 BLOCK (sampling temperature 2.0, 4/50). **SO-101 on Isaac, paired**: baseline PR #59 PASS (6/75 vs 6/75, 0 discordant); demo #60 (gripper floored at 25, registered beforehand) BLOCK as predicted, 0/75, 6 lost / 0 gained, exact McNemar p = 1/64 |
| README reproducible in 30 min | **Done, tested by CI**: `readme.yml` runs the README's commands on a fresh checkout with cold caches; 4 min 14 s on `ubuntu-24.04`, 4 min 59 s on `windows-2025`, PASS (27/50) and the demo BLOCK (4–5/50) on both (run 41597539505) |

## Done recently

Older items are in git history and the ADRs (0001–0019: memory, tooling, statistics, rulesets,
security gates, hooks, mock gate, core boundary, PushT evaluator and gate, no required review,
Project Cangrejo, the `piperobot` package).

- 2026-11-03: the SO-101 gate runs on the self-hosted runner (`so101-gate.yml`): evidence from
  the GPU runner without a write token, paired verdict and sticky comment from a hosted job,
  fail closed on a missing baseline, platform guard
  ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md)). Three runs as
  `gh-runner` (two branch heads and the baseline dispatch on main) gave 6/75 with 75/75
  trajectory fingerprints identical to the interactive acceptance run R1, in ~25 min of
  evaluation. Baseline `robots/so101/baselines/demo-replay.json` (6/75, seeds 0-74).
  The registered weak-grip regression (#60, closed unmerged) was blocked exactly as predicted:
  0/75 (all `no_grasp`), p = 1/64, red check and ❌ comment. Only a total collapse of the
  replay is detectable; the scripted policy (ADR 0034) is next.
- 2026-11-03: a scripted privileged-state pick-and-place policy (it sees the simulator's object
  poses; not deployable) passed its pre-registered go/no-go on the seeded randomized layout:
  43/50 through the evaluator, after tuning on separate seeds (91/100). It is proposed as the
  SO-101 gate's policy in place of the 6/75 demo replay
  ([ADR 0034](decisions/0034-so101-scripted-privileged-state-policy.md)).
- 2026-11-03: the Isaac Lab evaluator (`piperobot.adapters.isaaclab`) runs every seed in a fresh
  Isaac process: in one process an episode's outcome depends on the episodes before it (12/75
  change in reverse order), and neither enhanced determinism nor a full reset fixes it. Worker
  crashes are retried once and never count as trials. Acceptance (registered): first attempt
  failed on a Kit shutdown hang; after the fix, 2 × 75 seeds bit-identical, 6/75 replay
  successes, ~20 s per seed ([ADR 0033](decisions/0033-so101-isaac-evaluator-one-process-per-seed.md)).
- 2026-11-03: the README reproduces the PushT gate in about 5 minutes, PASS and a demo BLOCK,
  and CI runs it as written on Linux and Windows (`readme.yml`, [ci.md](knowledge/ci.md)).
- 2026-11-03: `nightly.yml` runs the reference and `main` on the same 500 fresh seeds every
  night and alerts on a paired regression (exact McNemar,
  [ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md), [ci.md](knowledge/ci.md)).
- 2026-11-03: `piperobot.stats.paired` decides a same-seed comparison with an exact McNemar
  test; the PushT baseline was re-measured on main (265/500, identical episode by episode to
  10-27) and now records its commit and per-episode results ([lerobot.md](knowledge/lerobot.md)).
- 2026-11-03: the course's tube-to-rack scene runs on Isaac Lab 3.0's SO-101 asset at the
  course pose with the course's gains; assets are fetched by sha256 outside the repo; the success
  term is ported with a 5 N grasp threshold and a slot-depth rule; registered sensing checks pass
  ([ADR 0028](decisions/0028-so101-scene-gains-and-mount.md)). Replays with contacts vary run to
  run (2/75 outcomes).
- 2026-11-03: history schema 2, core part: `series` (main, nightly), a `paired` block, the CPU
  flags digest and the runner image; v2 certificates whose series is bound to the calling workflow
  ([ADR 0031](decisions/0031-history-schema-2-and-certify-trusted-builder.md)). `certify.yml`, the
  single signer for `history.yml` and the nightly job, follows.
- 2026-11-03: certificates of evaluation, core part: `history record` / `append --record` and
  `python -m piperobot.reports.certificate verify` (pins signer workflow, `main`, hosted runner,
  predicate type; checks the signed record against `results.json`)
  ([ADR 0030](decisions/0030-signed-certificates-of-evaluation.md)). `history.yml` now signs each
  point (`attest` job) and publishes its results and bundle; points before that are "not signed".
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
## Next

1. Start the crab's v0 in Onshape, in its private repo.
2. Add the `certify` job to `nightly.yml` once Carla's reusable `certify.yml` lands, so nights
   join the history as a `nightly` series
   ([ADR 0031](decisions/0031-history-schema-2-and-certify-trusted-builder.md),
   [ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md)); after a week of
   nightlies, decide on a paired mode for pr-gate.
3. Isaac (with Berta's gate workflow,
   [ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md)): switch the gate's policy
   to the scripted one ([ADR 0034](decisions/0034-so101-scripted-privileged-state-policy.md)),
   measure its 500-seed baseline (100000-100499) with the workflow's baseline mode, and register a
   deliberately worse scripted parameter for the BLOCK demo. Right after the first gate merge:
   two parallel workers with a registered repeatability test (~25 min per run with one).
   Later: the wrist_flex-at-limit failure mode (needs a new untouched go/no-go range), cameras
   for failed-episode videos.
4. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
5. CI: check that Monday's Dependabot runs work under the new Actions permissions and that the
   `uv` job stays green with the torch ignore rule ([ci.md](knowledge/ci.md)); ask Andrés to add
   `zizmor` to the ruleset's required checks.
6. After the SO-101 scene PR: put `robots/` and the excluded SO-101 tests under mypy strict;
   after about four clean weekly `mutation.yml` runs, make a NEW surviving mutant (one not in
   `tests/mutation_equivalents.txt`) fail the job, instead of a score threshold
   ([testing.md](knowledge/testing.md)).
7. SO-101 gate: two parallel Isaac workers with a registered repeatability test (fingerprints
   identical to the sequential run, 0 flips), to bring 75 seeds well under the 30-minute budget
   ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md)). Then videos of failed
   episodes in the SO-101 comment (a Phase 0 criterion; needs cameras in the Isaac scene).
8. Proposal, for Andrés to decide: make the SO-101 verdict a required check. Today "blocked" means
   a red `so101-gate` check plus the ❌ comment, not a merge refusal (ADR 0035: not required).
   Snags and the design to solve them:
   - Job names are generic (`evaluate`, `report`). Add one uniquely named final job,
     `so101-gate-verdict`, and require only that.
   - The push `paths` filter means most PRs never produce the check, which would leave them
     pending forever. Drop the filter. A hosted `changes` job diffs the push against `main` with
     the same path list, and `evaluate` and `report` run only when it matches.
     `so101-gate-verdict` runs `if: always()` on a hosted runner. It passes when nothing
     relevant changed, and otherwise mirrors `report`'s result (a skipped or cancelled
     `evaluate` fails).
   - The runner is a PC that can be off. A required check would then leave relevant PRs pending,
     so Andrés needs a ruleset bypass for himself.
   - Fork PRs never get the check, because the workflow is push-only. A collaborator pushes
     their commits to a branch here, as today.
   Changing the ruleset is Andrés's call, in the GitHub UI. Write an ADR if he says yes.

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
