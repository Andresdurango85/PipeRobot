# Status

Last updated: 2026-11-07 (home PC)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | **Done.** `so101-gate` on the self-hosted RTX runner: ~28 min with 2 workers, ~41 min with 1 when desktop apps hold the VRAM ([ADR 0035](decisions/0035-so101-gate-on-the-self-hosted-runner.md), [ADR 0036](decisions/0036-so101-gate-scripted-policy-on-100-fixed-seeds.md)). Required check `so101-gate-verdict` ([ADR 0037](decisions/0037-so101-gate-verdict-is-a-required-check.md)) |
| ≥ 50 episodes with seeds and scene variations | **Done.** PushT: 50 seeded episodes on CPU ([ADR 0016](decisions/0016-real-evaluator-lerobot-pusht.md)). SO-101 on Isaac: 100 fixed seeds of a randomized layout, one process per seed, bit-for-bit repeatable ([ADR 0033](decisions/0033-so101-isaac-evaluator-one-process-per-seed.md)) |
| Statistical verdict vs. baseline | **Done.** Wilson/Newcombe for PushT ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)); exact paired McNemar for SO-101 and the nightly ([ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done.** Sticky comments on both gates; SO-101 re-runs up to 5 lost seeds with a camera and links MP4s ([ADR 0038](decisions/0038-so101-failed-episode-videos.md)) |
| Real-arm test, 20 attempts | **Not started**: electronics pending; runbook in [so101-bringup.md](knowledge/so101-bringup.md), manual-outcome adapter ready ([ADR 0022](decisions/0022-so101-hardware-deps-and-manual-outcomes.md)) |
| Deliberately worse PR blocked, normal PR passes | **Done.** PushT #13 PASS / #14 BLOCK; SO-101 #63 PASS (78/100) / registered demo #65 BLOCK (20/100, p = 5.3e-17) |
| README reproducible in 30 min | **Done, tested by CI** (`readme.yml`, Linux and Windows, ~5 min) |

## Done recently

- 2026-11-07: retro output-signal excerpts redact the full text before locating and slicing
  the signal, preserving token and reminder removal at excerpt boundaries (brief 29d).

Older items: git history and ADRs 0001–0039.

- 2026-11-07: first signed release `v0.1.0` (`git archive` tarball + Sigstore bundle + DSSE
  envelope, verified and reproducible byte for byte; tag rulesets on `v*`)
  ([ADR 0041](decisions/0041-signed-source-releases.md), [ci.md](knowledge/ci.md)).
  `CONTRIBUTING.md` and the OpenSSF badge [answer sheet](knowledge/openssf-best-practices.md).
- 2026-11-05/07: OpenSSF Scorecard 6.3 → 7.5: Vulnerabilities 10 (`osv-scanner.toml` mirrors
  [ADR 0012](decisions/0012-dependency-vulnerability-triage.md); its stale "no packages"
  reason is corrected in [ci.md](knowledge/ci.md)), Fuzzing 10 (atheris on hosted runners,
  [ADR 0040](decisions/0040-fuzz-untrusted-parsers-with-atheris.md)), Signed-Releases 10.
- 2026-11-05: the untrusted-input parsers (results, history, certificates, specs, video
  manifest) raise their documented errors instead of crashing (#84, #85,
  [testing.md](knowledge/testing.md)).
- 2026-11-05/06: every hosted job runs on a pinned `ubuntu-26.04`; the registered comparison
  found no image effect, and the first 26.04 nightly (run 42206404058) passed, 285/500, 0
  discordant ([ADR 0039](decisions/0039-explicit-hosted-runner-images.md)).
- 2026-11-07: ADR rule: only a dated `## Outcome` section may be appended to an accepted ADR
  ([decisions/README.md](decisions/README.md)).

## Next

1. The daily retrospective, phase 1
   ([ADR 0042](decisions/0042-daily-retrospective-report-only.md)): run `/retro` by hand for 3–4
   days, report only; the first run covers 2026-11-05..2026-11-07 (the acceptance check).
   Reports go to the private repo. The machine paths for `PIPEROBOT_RETRO_*` go in
   `CLAUDE.local.md` ([harness.md](knowledge/harness.md)). Phase 2, a schedule plus a watchdog,
   needs its own ADR.
2. **This weekend (Anita, Carla):** the crab's RL run, about 36 h of GPU
   ([ADR 0043](decisions/0043-reinforcement-learning-track-for-the-crab.md)). The code and
   results go in the private crab repo. Check that the queue runner pauses for every SO-101
   gate run, and that candidate checkpoints are judged by task success through the gate. Record
   the verified RL commands, versions and VRAM/commit floors in [isaac.md](knowledge/isaac.md).
3. **In progress (Carla):** reject non-integer seeds in `results.json` (`3.7`, `true`, `"42"`),
   Andrés's decision on ADR 0040's open question.
4. Andrés: fill in the OpenSSF badge form from the answer sheet (decisions 2 and 4 are his),
   then add the README badge with the project id.
5. Andrés: the real-arm test (20 attempts) once the electronics arrive; then the crab's v0 in
   Onshape, in its private repo.
6. Nightly: after a week, check the unpaired fresh-seed rate (+8.8, -1.2, +4.0 pp so far) and
   decide on a paired pr-gate ([ADR 0032](decisions/0032-nightly-paired-run-on-rotating-seeds.md));
   evaluate takes 22–43 min (90-min timeout); the cron starts ~7 h 41 min late
   ([ci.md](knowledge/ci.md)).
7. SO-101 gate: it exceeds the 30-min budget with 1 worker. Decide whether to accept that or
   shorten it. Unverified: the `video-report` ffmpeg install on 26.04 (first gate run that loses
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
12. CI: check Monday's Dependabot runs; ask Andrés about `zizmor` as a required check; put
    `robots/` under mypy strict; after ~4 clean weekly mutation runs, fail on a NEW survivor
    ([testing.md](knowledge/testing.md)).

## Open questions for Andrés

- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: notes for units 0–2 in
  [hf-robotics-course.md](learning/hf-robotics-course.md). Robot Learning Tutorial:
  [robot-learning-tutorial.md](learning/robot-learning-tutorial.md).
