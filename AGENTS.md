# AGENTS.md

Instructions for every agent working on this repo (Claude Code, Codex, CI agents, cloud sessions)
and for human contributors. Keep it short and stable: details live in `docs/`.

## Project

**PipeRobot** is a quality gate for robot policies. On every pull request that changes a
policy's code or weights, CI runs the policy in simulation many times, compares its success rate
against a stored baseline with a confidence interval, and blocks the PR if it regressed. It is
what Playwright + GitHub Actions do for web apps, applied to robots. It is the seed of a company.

This repo is **Phase 0** (learning, ~8 weeks, 8–10 h/week). Deliverable: the gate working on ONE
task. Phase 0 is done when:

- A GitHub Actions workflow runs on a GPU runner, headless, in under 30 min per PR.
- It evaluates at least 50 episodes with different seeds and scene variations.
- It gives a statistical verdict: success rate with confidence interval vs. the stored baseline.
- It posts an automatic PR comment with the rate, the verdict and videos of failed episodes.
- One test on the real arm (20 attempts) is documented next to the simulation figure.
- A PR that deliberately worsens the policy is blocked; one that does not, passes.
- The README lets someone reproduce it in 30 minutes.

## Owner

Andrés: Lead QA Automation Engineer / SDET, 9+ years in software quality (Playwright,
TypeScript, CI/CD with GitHub Actions and Jenkins, AWS, performance testing). **New to robotics**:
explain robotics concepts (ROS, kinematics, imitation learning, sim-to-real…) when they come up,
but not CI/CD or testing concepts.

## Hardware and stack

- Robot: SO-101 arm (leader + follower), 3D-printed.
  - Leader: 6 Feetech STS3215 servos, 7.4 V (1× 1/345, 2× 1/191, 3× 1/147), 5 V supply.
  - Follower: 6 STS3215 servos, 12 V, 12 V supply. **Never swap the power supplies.**
- Cameras: Logitech C920 (scene) + 720p USB camera on the wrist.
- Task: pick 50 ml centrifuge tubes and place them in a yellow rack inside a light box, following
  NVIDIA's "Train an SO-101 Robot From Sim-to-Real With NVIDIA Isaac" path.
- Software: LeRobot 0.6+ (Hugging Face), Isaac Sim + Isaac Lab, Isaac Lab-Arena for evaluation,
  Rerun to visualize episodes, GitHub Actions with a self-hosted GPU runner.
- First policy: ACT (small, trainable without a big GPU). GR00T only via NVIDIA checkpoints or cloud.
- Machines: see [ADR 0005](docs/decisions/0005-two-machine-setup.md). Home PC with RTX does the
  heavy work; the travel laptop has no RTX and little RAM (no heavy builds or suites there).

## How to work

- Talk to Andrés in **Spanish**. Code, identifiers, comments, commits, PRs and shared docs
  (`AGENTS.md`, `docs/STATUS.md`, `docs/decisions/`, `docs/knowledge/`) in **English**.
  `docs/learning/` holds Andrés's own course notes, in Spanish.
- Typed Python, pytest, ruff; pinned dependencies with uv ([ADR 0002](docs/decisions/0002-python-tooling-and-pinning.md)).
- Keep the generic gate core (`stats/`, `reports/`, `eval/results.py`) free of SO-101, LeRobot and
  Isaac code; robot/task-specific code lives in `envs/`, `policies/` and evaluators
  ([ADR 0015](docs/decisions/0015-generic-core-vs-robot-specific.md), enforced by a test).
- Small, verifiable steps. Propose a plan before big changes. **Ask before installing anything
  heavy** (Isaac Sim, CUDA, multi-GB Docker images, the `lerobot` extra on a new machine).
- Treat evaluation as a testing problem: flakiness, seeds, reproducibility and reports are
  first-class citizens.
- Verify commands against the current docs of LeRobot 0.6+ and Isaac Lab-Arena; old tutorials use
  commands that changed (e.g. `control_robot.py`). Record what you verified in `docs/knowledge/`.
- Personal, public repo on Andrés's personal GitHub account (`Andresdurango85/PipeRobot`).
  **Never use any employer's credentials, accounts or resources.** Nothing secret or
  employer-related goes into the repo; machine-specific setup goes in `CLAUDE.local.md` (gitignored).
- Commit or push only when Andrés asks. Work on a branch and open a PR; never push to `main`.

## Memory: where the know-how lives

The repo is the only memory shared by both machines and every agent
([ADR 0001](docs/decisions/0001-memory-system-in-repo.md)). Each kind of knowledge has one home:

| Kind | Where | Lifetime |
| --- | --- | --- |
| Rules and project context | `AGENTS.md` (this file) | Stable; change rarely |
| Current state, next steps, hand-off | [`docs/STATUS.md`](docs/STATUS.md) | Rewritten every session |
| Decisions and their reasons | [`docs/decisions/`](docs/decisions/README.md) (ADRs) | Immutable; superseded by a new ADR |
| Verified facts, gotchas, how-tos | [`docs/knowledge/`](docs/knowledge/README.md) | Living; dated entries |
| Course notes | [`docs/learning/`](docs/learning/README.md) | Andrés's notes |
| Raw outputs (eval JSON, logs, videos) | CI artifacts, Hugging Face Hub | Ephemeral; never in memory |

### Protocol

1. **Start**: `git pull`, read `docs/STATUS.md`, then the ADRs and knowledge files for the topic.
2. **During**: a non-trivial decision → new ADR (copy the template in `docs/decisions/README.md`).
   Something that cost time to find out, or a command verified against a given version → a dated
   entry in `docs/knowledge/`. Don't duplicate: link instead.
3. **End**: update `docs/STATUS.md` (done, next, open questions). Memory changes go in the **same
   PR** as the code they describe, so reviewing the PR reviews the memory. In Claude Code, the
   `/handoff` skill runs this step.
4. **Agents never write memory straight to `main`**: they propose memory changes in a PR, and a
   human (or a lead agent) reviews them. A wrong conclusion must not become a "fact".
5. `uv run pytest` includes `tests/test_docs.py`, which checks the memory itself (links, ADR
   format and index).

## Commands

```
uv sync                       # light: ruff + pytest + prek
uv run prek install           # once per clone: hooks on commit and push (ADR 0013)
uv sync --extra lerobot       # adds LeRobot 0.6.1 + torch (GBs) — ask first on a new machine
uv run ruff check . && uv run ruff format --check .
uv run pytest                 # unit tests + docs checks (no network)
uv run pytest -m hub          # tests that hit the Hugging Face Hub
uv run prek run --all-files --hook-stage pre-push   # what CI's lint-and-test job runs
```

Never bypass the hooks (`git commit/push --no-verify`). If a hook fails, fix the cause.
