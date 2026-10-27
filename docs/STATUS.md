# Status

Last updated: 2026-10-27 (laptop)

Current state and hand-off. Rewrite this file at the end of every session (`/handoff` in Claude
Code). Keep it under ~60 lines: history lives in git, decisions in ADRs, facts in knowledge.

## Phase 0 progress

| Done-criterion | State |
| --- | --- |
| GPU workflow, headless, < 30 min per PR | Not started (needs the home PC) |
| ≥ 50 episodes with seeds and scene variations | Mock only: 50 seeded episodes, 4 scene labels ([ADR 0014](decisions/0014-mock-evaluator-and-pr-gate-workflow.md)) |
| Statistical verdict vs. baseline | **Done**: `stats/gate.py` + `stats/baseline.json` ([ADR 0003](decisions/0003-statistical-gate-wilson-newcombe.md)) |
| Automatic PR comment with rate, verdict, failed videos | **Done** in `pr-gate.yml` (sticky comment); videos pending the simulation |
| Real-arm test, 20 attempts | Not started (Andrés is travelling, no hardware) |
| Deliberately worse PR blocked, normal PR passes | **Done with the mock** (tests + demo PR); repeat with the real policy |
| README reproducible in 30 min | Not started |

## Done recently

- 2026-10-26: repo published (`Andresdurango85/PipeRobot`, Apache-2.0), first CI run green.
- 2026-10-26: PR #1, PR comment renderer + `dataset_stats` exit codes + public dataset notes.
- 2026-10-26: memory system (AGENTS.md, ADRs, knowledge, STATUS, `/handoff`, docs tests), PR #3.
- 2026-10-27: `main` ruleset with owner-only bypass ([ADR 0010](decisions/0010-main-branch-ruleset.md))
  and free security gates: CodeQL, Dependabot, dependency review, ruff `S`
  ([ADR 0011](decisions/0011-free-security-gates.md)). First CodeQL scan: 0 alerts.
- 2026-10-27: Dependabot raised 46 alerts (all via LeRobot's caps). Pillow overridden to 13.0.0
  (fixes 41, all critical); 5 unreachable ones accepted
  ([ADR 0012](decisions/0012-dependency-vulnerability-triage.md)).
- 2026-10-27: git hooks with prek; pre-push runs the CI checks in a clean env
  ([ADR 0013](decisions/0013-pre-commit-hooks-mirror-ci.md)).
- 2026-10-27: `pr-gate.yml` end to end with a mock evaluator: results contract, stored baseline,
  sticky comment, BLOCK fails the job ([ADR 0014](decisions/0014-mock-evaluator-and-pr-gate-workflow.md));
  generic core vs SO-101 boundary enforced ([ADR 0015](decisions/0015-generic-core-vs-robot-specific.md)).

## Next

1. Run parallel agent sessions in separate git worktrees ([ci.md](knowledge/ci.md)).
2. Home PC: clone, `uv sync`, `uv run prek install`, write its `CLAUDE.local.md`, record the GPU
   model. Then plan the Isaac Sim / Isaac Lab-Arena install (ask before installing; several GB).
3. Replace the mock step in `pr-gate.yml` with an Isaac Lab-Arena evaluator that writes the same
   results contract (with `video_url`s), on the self-hosted GPU runner.
4. Look at the simulated rack dataset as training data for a first ACT policy
   ([datasets.md](knowledge/datasets.md)).
5. Find out why Dependabot bumped `setup-uv` only to v7 (latest is v10).

## Open questions for Andrés

- Home PC GPU model (RTX 3070 8 GB is the Isaac Sim minimum).
- Does the simulated rack dataset come from the NVIDIA Sim-to-Real path we follow?

## Learning

- Hugging Face Robotics Course: unit 0 ([docs/learning/](learning/README.md)).
