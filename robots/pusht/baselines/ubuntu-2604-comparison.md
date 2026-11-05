# Registered comparison: PushT on Ubuntu 24.04 vs 26.04

Registered 2026-11-04, before any run, on branch `exp/ubuntu-2604-compare` (this file's first
commit precedes the workflow that runs it). Andrés approved running it on 2026-11-04.
Context: [ADR 0039](../../../docs/decisions/0039-explicit-hosted-runner-images.md),
[ci.md](../../../docs/knowledge/ci.md), [lerobot.md](../../../docs/knowledge/lerobot.md).

## Question

Can the numeric PushT jobs (`pr-gate`, `baseline.yml`, `nightly.yml`, `history.yml` `evaluate`,
`readme.yml` `linux`) move from `ubuntu-24.04` to `ubuntu-26.04`, and does
`robots/pusht/baselines/vqbet.json` need a new baseline?

## What differs, and the confounder

- Userland: glibc/libm 2.39 → 2.43; Python 3.12.3 from the OS → a uv-managed 3.12.
- Kernel: identical (7.0.0-1017-azure on both images, 2026-10-26 manifests).
- Host: the confounder. Two 24.04 runners that both reported "AMD EPYC 9V74" disagreed in 10 of
  500 episodes, and one of them matched an EPYC 7763 run exactly, so the CPU model name does not
  predict flips; the CPU flags line is the working hypothesis. Any comparison across VMs has a
  floor of 0–10 discordant episodes in 500.

## Design

Policy `robots/pusht/policies/vqbet.json`, CPU torch from `uv.lock`, seeds 1000–1499 (500
episodes, the committed baseline's seeds), workflow `.github/workflows/image-compare.yml` on
this branch only (push-triggered, never merged, no self-hosted job).

**Arm A (primary: same host by construction).** Four jobs on `ubuntu-24.04`. Each runs the
500 seeds three times on the same VM:

- `N`: the runner's own userland, exactly as `pr-gate` runs today.
- `C24`: a `ubuntu:24.04` container (pinned by digest), the OS's `python3` 3.12, same `uv`. The
  control for running in a container.
- `C26`: a `ubuntu:26.04` container (pinned by digest), a uv-managed Python 3.12, same `uv`. The
  26.04 userland on the same CPU.

**Arm B (corroboration: the real images).** Three jobs on `ubuntu-24.04` and three on
`ubuntu-26.04`, each running the 500 seeds natively. It catches anything in the 26.04 runner
image that the container misses, and re-measures the 24.04 noise floor.

Every arm records the CPU model, the sha256 of the `/proc/cpuinfo` flags line, the runner image
version, glibc, Python and torch versions. Runs are grouped by flags digest.

## Decision rule (fixed now)

`python -m piperobot.stats.paired`, alpha 0.025, per job, on all 500 seeds.

0. **Validity**: `N` and `C24` identical on all 500 seeds in every arm-A job. If not, arm A is
   void and the decision rests on arm B alone under rule 2 (with `vqbet-episodes.json` as the
   reference).
1. **Move, keep the baseline**: `C26` identical to `C24` in every arm-A job, and every arm-B
   26.04 run at most 10 discordant episodes from `vqbet-episodes.json`. Every numeric pin moves
   in one PR; `vqbet.json` stays, with this evidence in its `how`.
2. **Move, refresh the baseline**: `C26` differs from `C24` somewhere, but in every arm-A job
   the paired verdict is PASS in both directions (`C24` → `C26` and `C26` → `C24`, so a
   two-sided 0.05 test) with at most 10 discordant episodes. The pins move, and `vqbet.json` and
   `vqbet-episodes.json` are refreshed from a `baseline.yml` run on 26.04 in the same PR.
3. **Do not move**: any BLOCK or WARN, or more than 10 discordant episodes in any arm-A job. The
   numeric jobs stay on 24.04; the finding goes in `ci.md`; revisit when GitHub announces
   24.04's deprecation.

The cap of 10 is the largest cross-host difference already seen on 24.04, not fitted to this
result. A job that fails for infrastructure reasons (download, timeout) is re-run, never
dropped; an arm-B run is never discarded for its outcome.

## Series

- The nightly paired verdict does not depend on the image: both arms run in one job.
- Unpaired lines against the committed 265/500 (nightly's fresh-seed rate, history points): no
  break under rule 1; under rule 2 the refresh lands with the switch. Schema-2 records carry
  `runner_image`, which the history page shows, so the first 26.04 point is visible; `ci.md`
  names its run id.
- Certificates are unaffected (`runner_image` is signed evidence).

## Result

Pending.
