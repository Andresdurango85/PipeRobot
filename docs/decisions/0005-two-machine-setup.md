# 0005. Home PC with RTX for heavy work, laptop for travel

- Status: Accepted
- Date: 2026-10-26

## Context

Isaac Sim needs an NVIDIA RTX GPU (at least an RTX 3070 with 8 GB). Andrés has an RTX at home and
a laptop without RTX and with little RAM, which he uses while travelling and which also holds
employer work.

## Decision

- Home PC: Isaac Sim / Isaac Lab-Arena, training, and the self-hosted GitHub Actions GPU runner.
- Laptop: code, light tests, dataset metadata, CPU-only work. No heavy builds or suites.
- GitHub (`Andresdurango85/PipeRobot`) is the only sync channel between them; project memory
  lives in the repo ([0001](0001-memory-system-in-repo.md)).
- Machine-specific setup goes in each machine's gitignored `CLAUDE.local.md`.
- When a GPU is needed while travelling: NVIDIA Brev or a cloud GPU instance.

## Alternatives considered

- Cloud GPU only: pay per hour for every PR run, while a capable GPU sits idle at home.
- Everything on the laptop: no RTX, so no Isaac Sim.

## Consequences

- PR gate runs depend on the home PC being on and online; a queued run waits for it.
- The home PC's GPU model and Isaac Sim performance are still unknown (see
  [`docs/STATUS.md`](../STATUS.md)).
- A runner on a personal PC executes code from PRs: only run it for trusted authors, or isolate it.
