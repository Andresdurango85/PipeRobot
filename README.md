# PipeRobot

A CI quality gate for robot policies. On every pull request that changes a policy's code or
weights, CI runs the policy in simulation many times, compares its success rate against a stored
baseline using a confidence interval, and blocks the PR if it regressed.

Think Playwright + GitHub Actions, but for a robot arm instead of a web app.

> **Status: Phase 0 (learning).** The goal of this phase is a working gate for **one** task:
> an [SO-101](https://github.com/TheRobotStudio/SO-ARM100) arm picking 50 ml centrifuge tubes
> and placing them in a yellow rack, trained and evaluated with
> [LeRobot](https://github.com/huggingface/lerobot) and NVIDIA Isaac Lab-Arena.

## How the gate will work

```
PR changes policy ──▶ GPU runner (headless Isaac Sim)
                          │  run N ≥ 50 episodes, fixed seeds + scene variations
                          ▼
                    success rate + confidence interval
                          │  compare against stored baseline
                          ▼
                PR comment (rate, verdict, videos of failed episodes)
                          │
                 regression? ──▶ ❌ block   /   no regression ──▶ ✅ pass
```

## Phase 0 definition of done

- [ ] GitHub Actions workflow on a GPU runner, headless, under 30 min per PR
- [ ] At least 50 evaluation episodes with distinct seeds and scene variations
- [ ] Statistical verdict: success rate with confidence interval vs. a stored baseline
- [ ] Automatic PR comment with rate, verdict and videos of failed episodes
- [ ] One real-arm test (20 attempts) documented next to the simulation number
- [ ] A deliberately degraded PR gets blocked; a neutral one passes
- [ ] This README lets anyone reproduce it in 30 minutes

## Repository layout

| Path | Purpose |
| --- | --- |
| `policies/` | Policy checkpoints or links to the Hugging Face Hub |
| `envs/` | Isaac Lab / Isaac Lab-Arena environment configuration |
| `eval/` | Evaluation scripts, seeds and metrics |
| `stats/` | Comparison against the baseline (confidence intervals) |
| `reports/` | PR comment template |
| `docs/STATUS.md` | Current state, next steps and hand-off between sessions |
| `docs/decisions/` | Architecture Decision Records: why things are the way they are |
| `docs/knowledge/` | Verified facts and gotchas (LeRobot, datasets, CI) |
| `docs/learning/` | Course notes |
| `.github/workflows/` | `ci.yml` (lint + tests), `pr-gate.yml` (the gate), `baseline.yml` (manual baseline); `nightly.yml` later |

Working on this repo, human or agent? Start with [AGENTS.md](AGENTS.md) and
[docs/STATUS.md](docs/STATUS.md).

## Quick start

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 for you if needed.

```bash
uv sync                 # dev tools only (ruff, pytest, prek) — lightweight
uv run prek install     # git hooks: lint on commit, CI-equivalent checks on push
uv run ruff check .
uv run pytest
```

To inspect a public SO-101 dataset you need LeRobot, which pulls in PyTorch (several GB):

```bash
uv sync --extra lerobot
uv run python -m eval.dataset_stats                      # default: lerobot/svla_so101_pickplace
uv run python -m eval.dataset_stats --repo-id <user>/<dataset> --json
uv run pytest -m hub                                     # tests that hit the Hub
```

Only the dataset's `meta/` folder is downloaded, not the videos. The script exits with code 1
if the metadata is internally inconsistent (e.g. frame counts don't add up).

## License

[Apache-2.0](LICENSE)
