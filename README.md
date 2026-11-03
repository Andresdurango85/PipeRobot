# PipeRobot

[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Andresdurango85/PipeRobot/badge)](https://scorecard.dev/viewer/?uri=github.com/Andresdurango85/PipeRobot)

A CI quality gate for robot policies. On every pull request that changes a policy's code or
weights, CI runs the policy in simulation many times, compares its success rate against a stored
baseline with a confidence interval, and blocks the PR if it regressed.

Think Playwright + GitHub Actions, but for a robot arm instead of a web app. Today the gate runs
on a 2D pushing task (PushT, LeRobot's VQ-BeT policy) on CPU; the target task is an
[SO-101](https://github.com/TheRobotStudio/SO-ARM100) arm placing centrifuge tubes in a rack,
simulated in NVIDIA Isaac Lab.

## Reproduce the gate in 30 minutes

You need git and [uv](https://docs.astral.sh/uv/getting-started/installation/) (uv installs
Python 3.12 itself). No GPU. The same commands work in bash (Linux, macOS) and PowerShell
(Windows). CI runs the marked blocks below on a fresh clone, on Linux and Windows, so this page
cannot drift from the code ([ci.md](docs/knowledge/ci.md)).

```bash
git clone https://github.com/Andresdurango85/PipeRobot.git
cd PipeRobot
```

**1. Install and run the tests** (the light install: the gate's core, ruff, pytest).

<!-- readme-test -->
```bash
uv sync
uv run pytest -q
```

**2. Install the simulator.** LeRobot, CPU-only PyTorch and the PushT environment: the slowest
step, a few minutes on a cold cache.

<!-- readme-test -->
```bash
uv sync --extra lerobot --group sim-pusht
```

**3. A policy that passes.** Evaluate the committed policy on the gate's 50 fixed seeds (the
first run downloads it from the Hugging Face Hub), compare with the stored baseline, and render
the PR comment that CI would post.

<!-- readme-test -->
```bash
uv run python -m piperobot.adapters.lerobot.evaluate --policy robots/pusht/policies/vqbet.json --work-dir out/pass --output out/pass/results.json
uv run python -m piperobot.stats.gate --results out/pass/results.json --baseline-file robots/pusht/baselines/vqbet.json
uv run python -m piperobot.reports.pr_comment --results out/pass/results.json --baseline-file robots/pusht/baselines/vqbet.json --output out/pass/comment.md
```

The gate prints the candidate's success rate (about 25–30 of 50), the baseline's (265/500), the
95% interval of the difference and `Verdict: PASS`, and exits 0. `out/pass/comment.md` is the
Markdown comment a pull request would get.

**4. A policy that is blocked.** `robots/pusht/policies/demo-degraded.json` is the same policy
with its sampling temperature raised to 2.0, the deliberately worse change of demo PR #14. It
is a demo file only; no workflow uses it.

<!-- readme-test -->
```bash
uv run python -m piperobot.adapters.lerobot.evaluate --policy robots/pusht/policies/demo-degraded.json --work-dir out/block --output out/block/results.json
```

<!-- readme-test: exit 1 -->
```bash
uv run python -m piperobot.stats.gate --results out/block/results.json --baseline-file robots/pusht/baselines/vqbet.json
```

The gate prints a success rate of a few episodes out of 50, an interval entirely below zero and
`Verdict: BLOCK`, and exits 1: in CI that fails the check and blocks the merge.

On Linux your counts match CI's exactly: PushT on CPU is deterministic for a given machine. On
other CPUs, Windows included, one or two near-miss episodes out of 50 can land differently, and
the verdicts stay the same ([lerobot.md](docs/knowledge/lerobot.md)).

## How it works

```
PR changes a policy ──▶ pr-gate (GitHub-hosted, CPU)
                          │  50 episodes, fixed seeds, PushT simulator
                          ▼
                success rate + Wilson interval
                          │  Newcombe interval of (candidate − baseline)
                          ▼
           sticky PR comment: rate, verdict, failed-episode videos
                          │
     interval below zero ──▶ ❌ BLOCK   /   otherwise ──▶ ✅ PASS (WARN on large, unsure drops)
```

The statistics are in [ADR 0003](docs/decisions/0003-statistical-gate-wilson-newcombe.md) and
[ADR 0004](docs/decisions/0004-warn-tolerance-in-percentage-points.md); why the gate runs on
CPU, in [ADR 0017](docs/decisions/0017-pr-gate-pusht-on-github-runners.md). Every night a
second check runs the stored reference and `main` on the same 500 fresh seeds and compares them
episode by episode ([ADR 0032](docs/decisions/0032-nightly-paired-run-on-rotating-seeds.md)),
and the [success-rate history](https://andresdurango85.github.io/PipeRobot/) records each
evaluation of `main` with a signed certificate
([ADR 0026](docs/decisions/0026-success-rate-history-data-branch-and-pages.md),
[ADR 0030](docs/decisions/0030-signed-certificates-of-evaluation.md)).

## Status

Phase 0 (learning): progress against its definition of done is tracked in
[docs/STATUS.md](docs/STATUS.md).

## Further

- **GPU runner**: a self-hosted Windows runner with an RTX GPU, hardened for a public repo
  ([ADR 0020](docs/decisions/0020-self-hosted-gpu-runner.md),
  [ADR 0027](docs/decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md),
  [ADR 0029](docs/decisions/0029-refused-jobs-end-their-worker-and-workspaces-are-wiped.md)).
- **SO-101 in Isaac Lab**: the target task on Isaac Lab 3.0, native Windows
  ([ADR 0021](docs/decisions/0021-isaac-lab-3-on-windows-without-arena.md),
  [isaac.md](docs/knowledge/isaac.md)).
- **The real arm**: bring-up and hand-scored trials ([so101-bringup.md](docs/knowledge/so101-bringup.md)).
- **Datasets**: inspect a public SO-101 dataset's metadata with
  `uv run python -m robots.so101.tools.dataset_stats` ([datasets.md](docs/knowledge/datasets.md)).
- **Verify a history certificate**: [docs/attestations/](docs/attestations/).
- **Supply chain**: SHA-pinned actions, zizmor and OpenSSF Scorecard
  ([ADR 0027](docs/decisions/0027-self-hosted-runner-push-only-and-pinned-actions.md)).

## Repository layout

| Path | Purpose |
| --- | --- |
| `piperobot/` | Installable gate core: results contract, statistics, reports |
| `piperobot/adapters/` | Framework adapters (LeRobot, manual scoring, mock) |
| `robots/` | One folder per robot: policy specs, baselines, task data and tools |
| `docs/STATUS.md` | Current state, next steps and hand-off between sessions |
| `docs/decisions/` | Architecture Decision Records: why things are the way they are |
| `docs/knowledge/` | Verified facts and gotchas (LeRobot, Isaac, CI, testing) |
| `docs/learning/` | Course notes |
| `.github/workflows/` | `pr-gate` (the gate), `ci`, `baseline`, `nightly`, `history`, `mutation`, `readme`, security checks, and the GPU runner's `gpu-smoke`, `isaac-render` |

Working on this repo, human or agent? Start with [AGENTS.md](AGENTS.md). Developer setup:
`uv run prek install` once per clone installs the git hooks, which mirror CI.

## License

[Apache-2.0](LICENSE)
