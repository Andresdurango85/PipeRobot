# 0002. uv, Python 3.12, LeRobot pinned as an optional extra

- Status: Accepted
- Date: 2026-10-26

## Context

The gate must be reproducible: the same commit must evaluate the same way months later and on
both machines. LeRobot 0.6.1 requires Python 3.12 or newer and pulls torch (several GB), which the
lint/test CI job and the low-RAM laptop do not need.

## Decision

- uv manages the project (`uv.lock` committed, `package = false`), Python pinned to 3.12.
- `uv sync` installs only dev tools (ruff, pytest). LeRobot is the optional extra `lerobot`
  pinned to `lerobot[dataset]==0.6.1`, installed with `uv sync --extra lerobot`.
- ruff for lint and format, pytest with `--strict-markers`; tests that need the network are
  marked `hub` and excluded by default.

## Alternatives considered

- pip-tools: works, but slower and with two files to keep in sync; uv also manages Python itself.
- LeRobot as a core dependency: every CI run and every machine would download torch.
- Unpinned LeRobot: the dataset format and APIs changed between versions (v2.1 to v3.0 format),
  so an unpinned install breaks reproducibility.

## Consequences

- The lint/test CI job installs in seconds, with no GPU or torch.
- Upgrading LeRobot is a deliberate PR: bump the pin, re-run `pytest -m hub`, note changes in
  [`docs/knowledge/lerobot.md`](../knowledge/lerobot.md).
- On Windows without CUDA, uv installs the CPU build of torch (~1.1 GB venv on the laptop).
