# Status

Last updated: 2026-11-05 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Done for PushT**: `gpu-smoke` on the self-hosted RTX runner, ~2–3 min per PR, not a gate ([ADR 0020](decisions/0020-self-hosted-gpu-runner.md)); the gate stays on CPU ([ADR 0017](decisions/0017-pr-gate-pusht-on-github-runners.md)). **SO-101**: `so101-gate` on the same runner, 75 seeds paired against a same-runner baseline, ~26.5 min per run (setup 32 s warm), its verdict job `so101-gate-verdict` runs on every push and is a required check ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md), [ADR 0037](decisions/0037-so101-gate-verdict-is-a-required-check.md)) |
| ≥ 50 episodes with seeds and scene variations | **Real on PushT** (50 seeded episodes, randomized start poses, CPU, ~5 min) ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). **SO-101 on Isaac**: evaluator runs 75 seeds, one process each, ~20 s per seed, repeatable bit for bit; a scripted privileged-state policy on the seeded randomized layout passed its registered go/no-go, 43/50, ~25 s per seed ([ADR 0033](decisions/0033-so101-isaac-evaluator-one-process-per-seed.md), [ADR 0034](decisions/0034-so101-scripted-privileged-state-policy.md)) |
| Statistical verdict vs. baseline | **Done**: `piperobot/stats/gate.py` + `robots/pusht/baselines/vqbet.json` ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done** in `pr-gate.yml` (sticky comment), with PushT videos of the first 10 episodes in the run artifact. **SO-101**: after the verdict, up to 5 lost seeds are re-run with a camera, verified bit for bit against the judged episode, and linked as MP4s in a second comment ([ADR 0038](decisions/0038-so101-failed-episode-videos.md)): #75, demo #76 recorded its 5 lost seeds, all matched, ~400 KB per MP4, +4 min 52 s of runner after the verdict |
| Real-arm test, 20 attempts | Not started: arm printed, electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md), `so101` dependency group and manual-outcome adapter ready ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)) |
| Deliberately worse PR blocked, normal PR passes | **Done with the real PushT policy**: #13 PASS (27/50), demo #14 BLOCK (sampling temperature 2.0, 4/50). **SO-101 scripted policy on Isaac, paired, 100 fixed seeds**: swap PR #63 PASS (78/100 vs 78/100, b = c = 0); demo #65 (gripper_closed 5 -> 12, registered beforehand, tuned on dev seeds only) BLOCK as predicted, 20/100, 59 lost / 1 gained, exact McNemar p = 5.3e-17 ([result](../robots/so101/policies/scripted_gripper_closed_12_result.json)). Replay era: #59 PASS, #60 BLOCK (p = 1/64) |
| README reproducible in 30 min | **Done, tested by CI**: `readme.yml` runs the README's commands on a fresh checkout with cold caches; 4 min 14 s on `ubuntu-24.04`, 4 min 59 s on `windows-2025`, PASS (27/50) and the demo BLOCK (4–5/50) on both (run 41597539505) |

## Done recently

Older items are in git history and the ADRs (0001–0019: memory, tooling, statistics, rulesets,
security gates, hooks, mock gate, core boundary, PushT evaluator and gate, no required review,
Project Cangrejo, the `piperobot` package).

- 2026-11-05: the numeric PushT jobs (`pr-gate`, `baseline`, `nightly`, `history` `evaluate`,
  `readme` `linux`) run on `ubuntu-26.04`. The registered comparison
  ([design and result](../robots/pusht/baselines/ubuntu-2604-comparison.md), run 41959796057)
  found no image effect: same outcomes on the same VM for both userlands on four hosts, and
  26.04 runs identical to `vqbet-episodes.json`, so the baseline stays. Outcomes split by host,
  likely AVX-512 on AMD ([ci.md](knowledge/ci.md)). Scorecard publishes from 26.04.
- 2026-11-04: SO-101 failed-episode videos. A registered check showed that a camera-on re-run
  reproduces the judged episode bit for bit (30/30 dev pairs), at about +20 s per failed seed
  and twice the Windows commit ([result](../robots/so101/envs/camera_record_check_result.json)).
  The gate re-runs up to 5 lost seeds with a camera after the verdict and links MP4s in a second
  comment; the verdict never depends on it
  ([ADR 0038](decisions/0038-so101-failed-episode-videos.md), #75). Demo #76 (BLOCK as #65)
  recorded its 5 lost seeds, all matched, ~400 KB per MP4, +4 min 52 s of runner, the comment
  5 min 46 s after the verdict. Two evaluate workers now also need free commit.
- 2026-11-04: no job runs on `ubuntu-latest` any more
  ([ADR 0039](decisions/0039-explicit-hosted-runner-images.md)). `ci`, `dependency-review`,
  `mutation`, `scorecard` and `zizmor` run on `ubuntu-26.04`, ahead of the 2026-11-19 flip. The
  numeric PushT jobs, `certify.yml` and the SO-101 hosted jobs followed on 2026-11-05, each
  with its own validating run; no job runs on `ubuntu-24.04` any more.
- 2026-11-04: `nightly.yml` calls `certify.yml` with series `nightly` on `main`, so every night
  becomes a signed point of the history's `nightly` series, BLOCK nights included
  ([ADR 0031](decisions/0031-history-schema-2-and-certify-trusted-builder.md),
  [ci.md](knowledge/ci.md)). The first `main` v2 certificate verified (run 41770900924), and the
  first `nightly` one (run 41779993747, signer `certify.yml`, config `nightly.yml`, 259/500
  PASS). Night 2's unpaired fresh-seed rate was 51.8% against the committed 53.0%, so night 1's
  +8.8 pp did not repeat. `certificate verify` now hints at CRLF line endings
  (`core.autocrlf`) when a file is NOT CERTIFIED.
- 2026-11-03: `certify.yml`, the single signer of the history
  ([ADR 0031](decisions/0031-history-schema-2-and-certify-trusted-builder.md),
  [ci.md](knowledge/ci.md)): `history.yml` keeps its evaluation and calls it with series `main`;
  new points are schema 2 (`history record --schema` now defaults to 2), and the page links a
  nightly point's candidate, reference and bundle.
- 2026-11-03: the SO-101 verdict becomes a required check (Andrés's decision,
  [ADR 0037](decisions/0037-so101-gate-verdict-is-a-required-check.md)): `so101-gate.yml` runs on
  every push, a hosted `changes` job decides relevance, and `so101-gate-verdict` passes in seconds
  when nothing relevant changed. Docs-only #69 got it green in ~16 s without the runner, and e5
  added it to the `main` ruleset's required checks on 2026-11-04.
- 2026-11-03: the SO-101 gate runs the scripted policy on 100 fixed seeds (#63, baseline 78/100,
  [ADR 0036](decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)), and a registered
  regression it was not tuned on was blocked: gripper_closed 5 -> 12, 20/100, 59 lost / 1 gained,
  p = 5.3e-17, every reported range held (#65, closed unmerged;
  [result](../robots/so101/policies/scripted_gripper_closed_12_result.json)). The demo also
  mirrored the value in the module's DEFAULTS and a unit test, as a real PR would: unit tests
  green, only the gate caught it.
- 2026-11-03: the gate's sticky comment retries GitHub 5xx and network errors without
  double-posting, after a 500 turned a correct SO-101 PASS red ([ci.md](knowledge/ci.md)).
- 2026-11-03: ready for `ubuntu-latest` → Ubuntu 26.04 (by 2026-11-19). A probe on both images
  gave the same ci results and the same mutation survivors. The pinned jobs stay on
  `ubuntu-24.04`: PushT moves 4-8 near-miss episodes with the image and CPU together
  ([ci.md](knowledge/ci.md)). Tests that need `pwsh` or `git` now fail in CI instead of skipping.
- 2026-11-03: the Isaac evaluator runs seeds on concurrent workers (`--workers N`, still one
  process per seed). Registered test: 1 vs 2 workers on 125 seeds, 0 flips and identical
  fingerprints; 2 workers take 16.4 s per scripted seed instead of 27.5 s and need ~8.7 GB of
  free GPU memory ([result](../robots/so101/envs/workers_acceptance_result.json),
  [isaac.md](knowledge/isaac.md)).
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
2. After a week of nightlies, check the unpaired fresh-seed rate (+8.8 pp on night 1, -1.2 pp on
   night 2) and decide on a paired mode for pr-gate
   ([ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md)). Watch the evaluate
   time (22 and 43.5 min so far, 90-min timeout); the 03:17 UTC cron starts ~7 h 41 min late
   ([ci.md](knowledge/ci.md)). The first 26.04 night is the next point of the series.
3. Isaac: the gate runs the scripted policy on 100 fixed seeds and blocked its registered demo
   (#63, #65, [ADR 0036](decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)).
   Optional: gripper_closed 10 (about -15 pp on dev, with rescues) as a second registered demo,
   closer to the threshold. Later: the wrist_flex-at-limit failure mode (needs a new untouched
   go/no-go range).
4. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
5. CI: check that Monday's Dependabot runs work under the new Actions permissions and that the
   `uv` job stays green with the torch ignore rule ([ci.md](knowledge/ci.md)); ask Andrés to add
   `zizmor` to the ruleset's required checks.
6. After the SO-101 scene PR: put `robots/` and the excluded SO-101 tests under mypy strict;
   after about four clean weekly `mutation.yml` runs, make a NEW surviving mutant (one not in
   `tests/mutation_equivalents.txt`) fail the job, instead of a score threshold
   ([testing.md](knowledge/testing.md)).
7. SO-101 failed-episode videos ([ADR 0038](decisions/0038-so101-failed-episode-videos.md)):
   re-run the camera on/off check after any Isaac or Kit upgrade. Before a GPU run, check free
   Windows commit as well as VRAM ([isaac.md](knowledge/isaac.md)). Watch for CUDA out-of-memory
   retries in 2-worker gate runs (2 of 3 used in demo #76's evaluate).
8. Ubuntu 26.04 ([ADR 0039](decisions/0039-explicit-hosted-runner-images.md)): name the first
   26.04 nightly run in [ci.md](knowledge/ci.md). `exp/ubuntu-2604-compare` stays on the remote
   for good: it is the comparison's registration evidence.
9. GitHub keeps one pending run per concurrency group, so the SO-101 gate's "main queues" in
   [ADR 0037](decisions/0037-so101-gate-verdict-is-a-required-check.md) can skip the middle of
   three quick merges ([ci.md](knowledge/ci.md), `so101-gate.yml` entry). Space gate-relevant
   merges, or dispatch a gate run on `main` after a burst.

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: Andrés on unit 0; notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md) (units 5–7 not published yet).
- Robot Learning Tutorial: notes in [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
