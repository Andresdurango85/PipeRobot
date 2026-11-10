# Status

Last updated: 2026-11-10 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Done.** `so101-gate` on the self-hosted RTX runner: ~26-28 min with 2 workers when the PC is idle; ~41 min with 1 when desktop apps hold the VRAM, a case Andrés accepted on 2026-11-08 ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md), [ADR 0036](decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)). Required check `so101-gate-verdict` ([ADR 0037](decisions/0037-so101-gate-verdict-is-a-required-check.md)) |
| ≥ 50 episodes with seeds and scene variations | **Done.** PushT: 50 seeded episodes on CPU ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). SO-101 on Isaac: 100 fixed seeds of a randomized layout, one process per seed, bit-for-bit repeatable ([ADR 0033](decisions/0033-so101-isaac-evaluator-one-process-per-seed.md)) |
| Statistical verdict vs. baseline | **Done.** Wilson/Newcombe for PushT ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)); exact paired McNemar for SO-101 and the nightly ([ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done.** Sticky comments on both gates; SO-101 re-runs up to 5 lost seeds with a camera and links MP4s ([ADR 0038](decisions/0038-so101-failed-episode-videos.md)) |
| Real-arm test, 20 attempts | **Not started**: electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md), manual-outcome adapter ready ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)) |
| Deliberately worse PR blocked, normal PR passes | **Done.** PushT #13 PASS / #14 BLOCK; SO-101 #63 PASS (78/100) / registered demo #65 BLOCK (20/100, p = 5.3e-17) |
| README reproducible in 30 min | **Done, tested by CI** (`readme.yml`, Linux and Windows, ~5 min) |

## Done recently

- 2026-11-10: the daily retrospective's phase 2
  ([ADR 0045](decisions/0045-daily-retrospective-phase-2-window-and-watchdog.md)): each run
  covers the complete days since the last report, never today. Approved retro fixes: a
  huggingface-hub major ignore for Dependabot, and source-citing review rules in
  [ci.md](knowledge/ci.md).
- 2026-11-08: the RL track's first weekend (ADR 0043) ended with registered results in the
  private crab repo. Isaac Lab's Franka Reach and Lift ran as references, three training seeds
  each. Its gate lessons became
  [ADR 0044](decisions/0044-gate-trained-policies-against-a-spec-with-checked-repeatability.md):
  - judge against a written spec, never training's metrics;
  - check repeatability per task before pairing;
  - require seeds to vary the scene;
  - show a continuous metric next to the rate;
  - treat the recipe as the unit under test.
  Generic Isaac facts are in [isaac.md](knowledge/isaac.md).
- 2026-11-07: the daily retrospective, phase 1
  ([ADR 0042](decisions/0042-daily-retrospective-report-only.md)): first report published to
  the private repo.
- 2026-11-07: non-integer seeds (`3.7`, `true`, `"42"`) are rejected in `results.json` (#91).
- 2026-11-07: first signed release `v0.1.0`, with tag rulesets on `v*`
  ([ADR 0041](decisions/0041-signed-source-releases.md)). `CONTRIBUTING.md` and the OpenSSF
  badge [answer sheet](knowledge/openssf-best-practices.md). Scorecard 6.3 → 7.5.

Older items: git history and ADRs 0001–0043.

## Next

1. The daily retrospective, phase 2 ([ADR 0045](decisions/0045-daily-retrospective-phase-2-window-and-watchdog.md)):
   - run `/retro` each weekday morning (it covers yesterday, or since the last report);
   - the watchdog workflow in the private repo (its PR needs Andrés's OK);
   - Andrés: the Task Scheduler task with `dontAsk` and an allow list
     ([harness.md](knowledge/harness.md));
   - `retro_collect.py trend` per-day normalization (in progress).
2. ADR 0044's points 2-4 are in the generic core ([testing.md](knowledge/testing.md)):
   - optional digests, `metric` and `metric_spec` in `results.json`, with the seed-variation
     check;
   - `python -m piperobot.stats.repeatability`, which picks the paired or unpaired gate;
   - metric median, p90 and IQR in both PR comments.
   The SO-101 Isaac evaluator now emits the digests and `box_signed_distance`, and passed the
   admission check: REPEATABLE, 100/100 ([isaac.md](knowledge/isaac.md)), so its gate stays
   paired. Next: re-record the SO-101 baseline (a `baseline` dispatch) so that the paired
   comment shows the reference's metric row too.
3. The crab's RL track continues in its private repo (PR authorization until 2026-11-15).
   Next candidates, each registered first:
   - a Lift run with `deterministic_mode="run_to_run"`, to test the admission check's fix;
   - a crab task with harder variation, because approach sits at its ceiling.
4. Andrés: fill in the OpenSSF badge form from the answer sheet (decisions 2 and 4 are his),
   then add the README badge with the project id.
5. Andrés: the real-arm test (20 attempts) once the electronics arrive; then the crab's v0 in
   Onshape, in its private repo.
6. Nightly: after a week, check the unpaired fresh-seed rate (+8.8, -1.2, +4.0 pp so far) and
   decide on a paired pr-gate ([ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md));
   evaluate takes 22–43 min (90-min timeout); the cron starts ~7 h 41 min late
   ([ci.md](knowledge/ci.md)).
7. SO-101 gate: unverified: the `video-report` ffmpeg install on 26.04 (first gate run that loses
   an episode). Before GPU runs, check free commit as well as VRAM, and watch for CUDA OOM
   retries with 2 workers ([isaac.md](knowledge/isaac.md)).
8. Three quick gate-relevant merges can skip the middle one's run on `main` (one pending run
   per concurrency group, [ci.md](knowledge/ci.md)): space them, or dispatch a gate afterwards.
9. Scorecard upkeep: triage weekly fuzz crashes under ADR 0040's policy; `osv-scanner.toml`
   expires 2027-05-05 and changes with every LeRobot upgrade. Optional: branch coverage
   (`test_most`), a results reference page, a structure-aware results harness.
10. Isaac (optional): a second registered demo (gripper_closed 10); the wrist_flex-at-limit
   failure mode; re-run the camera on/off check after any Isaac or Kit upgrade.
11. A first ACT policy from the simulated rack dataset ([datasets.md](knowledge/datasets.md)).
12. CI: Dependabot #100 and #101 wait for Andrés (ADR 0037); ask Andrés about `zizmor` as a
    required check; put `robots/` under mypy strict; after ~4 clean weekly mutation runs, fail on a NEW survivor
    ([testing.md](knowledge/testing.md)).

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md). Robot Learning Tutorial:
  [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
