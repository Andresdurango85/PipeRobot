# Registered comparison: PushT on Ubuntu 24.04 vs 26.04

Registered before any run, on branch `exp/ubuntu-2604-compare`: this file's first commit
`88950bf` (2026-11-05 02:59 UTC) precedes the workflow `76840b3` (03:07 UTC) and the run's first
job (03:09 UTC). Only the Result section was written after the run. Andrés approved running it
on 2026-11-04 (local time). The branch is kept on the remote as the evidence of this
registration: never delete or merge it.
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
this branch only (push-triggered, never merged, no self-hosted job;
[as run](https://github.com/Andresdurango85/PipeRobot/blob/76840b352a7bc05b1d208f14ce834925c091b8cb/.github/workflows/image-compare.yml)).

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

Run [41959796057](https://github.com/Andresdurango85/PipeRobot/actions/runs/41959796057)
(2026-11-05, commit `76840b3`), all 10 jobs succeeded on the first attempt; nothing re-run or
dropped. 24.04 images 20261026.354.1 and 20261101.360.1, 26.04 image 20261026.180.1; glibc 2.39
vs 2.43; Python 3.12.3 (OS) vs 3.12.16 (uv-managed); torch 2.11.0+cpu everywhere. The run's
artifacts expire on 2026-12-05; the 267/500 vector differs from `vqbet-episodes.json` in the 10
seeds listed in [lerobot.md](../../../docs/knowledge/lerobot.md).

| Job | Host (flags digest) | N vs C24 | C24 vs C26 | vs `vqbet-episodes.json` |
| --- | --- | --- | --- | --- |
| same-vm 1 | EPYC 7763 (`9e641570`) | identical | identical | 0 discordant |
| same-vm 2 | EPYC 9V74 (`c8543a3b`) | identical | identical | 10 (6 gained, 4 lost) |
| same-vm 3 | EPYC 9V74 (`c8543a3b`) | identical | identical | 10 (6 gained, 4 lost) |
| same-vm 4 | EPYC 9V45 (`4aece38d`) | identical | identical | 10 (6 gained, 4 lost) |
| native-2404 1 | EPYC 7763 (`9e641570`) | | | 0 discordant |
| native-2404 2, 3 | EPYC 9V74 (`c8543a3b`) | | | 10 (6 gained, 4 lost) |
| native-2604 1, 2, 3 | EPYC 7763 (`9e641570`) | | | 0 discordant |

- Rule 0 (validity): met in all four arm-A jobs.
- Rule 1: met. `C26` is identical to `C24` in every arm-A job, on three host types; every 26.04
  run is identical to `vqbet-episodes.json` (paired verdict PASS, 0 lost, 0 gained, p = 1).
  **Decision: the numeric pins move to `ubuntu-26.04`; `vqbet.json` stays.**
- The 18 evaluations produced exactly two outcome vectors (265/500 and 267/500), and which one a
  run got followed the host, never the image. Across these AMD hosts the split matches AVX-512:
  the EPYC 7763 flags line has no `avx512*` flag and gives the committed vector; the 9V74 and
  9V45 lines both have AVX-512 and give the other vector, although their flags digests differ
  (the 9V45 adds `avx512_vp2intersect`, `avx_vnni`, `x2apic`). The flags digest therefore
  over-splits hosts; the committed baseline, recorded on a runner that reported "9V74", most likely ran without AVX-512.
  A hypothesis from one run, not a verified rule, and only for AMD hosts: the 2026-11-03 probe's
  Intel Xeon Platinum 8370C (which has AVX-512) gave a third vector on 26.04, 263/500, 8
  discordant from the committed one ([ci.md](../../../docs/knowledge/ci.md)).
- Evaluation wall time on the same host type did not change (EPYC 7763: 1266–1312 s on 26.04,
  1294 s on 24.04).
