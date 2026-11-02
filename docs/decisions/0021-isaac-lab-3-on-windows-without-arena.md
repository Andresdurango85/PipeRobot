# 0021. Simulate the SO-101 in Isaac Lab 3.0 on native Windows, without Isaac Lab-Arena

- Status: Accepted
- Date: 2026-11-01

## Context

[AGENTS.md](../../AGENTS.md) names Isaac Lab-Arena as the SO-101 evaluation tool, and
[0020](0020-self-hosted-gpu-runner.md) put the GPU runner on native Windows, to be revisited if
Arena or the SO-101 tasks did not run there. That condition is now met. Verified on 2026-11-01
([isaac.md](../knowledge/isaac.md)):

- Isaac Lab-Arena supports Linux only ("Linux (Ubuntu 22.04+)") and ships no SO-101 embodiment.
- NVIDIA's SO-101 course (Isaac Sim 5.1, Isaac Lab 2.3, LeRobot 0.4.3) is tested on Ubuntu and set
  up only through Docker. Its task code is Apache-2.0.
- Isaac Lab 3.0 with Isaac Sim 6.2 supports Windows 11, uses Python 3.12 and torch 2.11.0, and
  ships an SO-101 asset (`isaaclab_assets.robots.so101`) and SO-101 cube-stacking tasks
  (`IsaacContrib-Stack-Cube-SO101-*`).
- LeRobot 0.6.1 needs Python ≥ 3.12 and torch < 2.12. Isaac Sim 5.1 runs on Python 3.11, so it
  could never share a process with this repo's LeRobot.

## Decision

- Simulate the SO-101 in **Isaac Lab 3.0.0 with Isaac Sim 6.2.0.0** on the home PC, native
  Windows 11, from Isaac Lab's `release/3.0.0` checkout and its `uv.lock` (`--extra isaacsim`,
  torch 2.11.0 `cu130`).
- Its environment lives outside this repo and apart from the other CUDA environment; this repo's
  lock does not change until an evaluator imports Isaac Lab.
- **Isaac Lab-Arena is dropped** for now. The tube-to-rack task is ported from the course's
  `source/sim_to_real_so101` to Isaac Lab 3.0, starting from the SO-101 asset Isaac Lab ships.
- The evaluator runs the policy in the same process if `lerobot==0.6.1` installs into the Isaac
  Lab environment without breaking either; otherwise the policy runs behind a server, as the
  course does.
- The Omniverse EULA is accepted by Andrés himself at the first launch. Only then may automation
  set `OMNI_KIT_ACCEPT_EULA=YES`. Andrés accepted it on 2026-11-01 at `import isaacsim` in the
  home PC's Isaac Lab env, which recorded it in `isaacsim/kit/EULA_ACCEPTED`
  ([isaac.md](../knowledge/isaac.md)); other envs (such as the runner's) set the variable as the
  record of that acceptance and never create the file by hand.

## Alternatives considered

- Dual-boot Ubuntu 24.04 (the fallback in [0020](0020-self-hosted-gpu-runner.md)): Arena and the
  course run as published, but a second OS to maintain and Windows tools unavailable while it
  runs.
- Isaac Sim 5.1 + Isaac Lab 2.3 on Windows (the course's and LeIsaac's versions): Python 3.11
  forces a policy server from day one; Isaac Lab 3.0 no longer supports Isaac Sim 5.1.
- WSL2: no Isaac Sim rendering ([0020](0020-self-hosted-gpu-runner.md)).

## Consequences

- The course's tutorials no longer apply as written: its task code must be ported from the
  Isaac Lab 2.3 API to 3.0, effort unknown, and its GR00T server container is not used.
- No Arena features (task/embodiment catalogs, policy-server contract, cuRobo reachability
  checks); the evaluator, its seeds and its results contract are ours.
- Dual-boot Ubuntu 24.04 stays the fallback: if rendering inside the runner's Windows service
  (session 0) fails, or the SO-101 port to Isaac Lab 3.0 does not work out, a new ADR moves to
  Linux, where Arena and the course run as published. The same applies if Arena gains Windows
  support.
- Two CUDA builds live side by side on the home PC (`cu128` for the PushT smoke, `cu130` for
  Isaac Lab), each in its own environment.
