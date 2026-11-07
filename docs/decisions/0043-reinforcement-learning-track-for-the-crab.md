# 0043. Reinforcement learning track for the crab

- Status: Accepted
- Date: 2026-11-07

## Context

[Project Cangrejo](../cangrejo/README.md) is the second robot the gate validates. Its v0 is a
digital twin only: no crab hardware is bought until the SO-101 Phase 0 gate is met. So, for now,
the crab can learn only in simulation.

The plan so far trains every crab skill by imitation (ACT, the SO-101's policy family).
Imitation needs teleoperated demonstrations, which need a real robot and leader arms. That blocks
crab training on hardware that cannot be bought yet.

Reinforcement learning (RL) needs no demonstrations: a policy improves by trial and error in
simulation against a reward. It fits skills whose success is easy to define and whose motion is
hard to script: reaching, approaching and docking. It is a poor fit for motion with a closed-form
answer, and its known failure is **reward hacking**: the policy maximizes the reward without doing
the task.

Andrés approved an RL track for the crab, with the home PC's GPU training for about 36 hours over
a weekend. That GPU is shared:

- The SO-101 gate's `evaluate` job runs on the same RTX 5060 Ti through the self-hosted runner
  service ([ADR 0035](0035-so101-gate-on-the-self-hosted-runner.md)), and it is a required
  check ([ADR 0037](0037-so101-gate-verdict-is-a-required-check.md)).
- Isaac needs both VRAM and Windows commit charge; when commit runs out, Kit fails at start even
  with VRAM free ([isaac.md](../knowledge/isaac.md)).

Isaac Lab 3.0 already runs natively on this PC
([ADR 0021](0021-isaac-lab-3-on-windows-without-arena.md)). It ships an RL integration
(`isaaclab_rl`, with an `rsl_rl` wrapper and `scripts/reinforcement_learning/train.py`), and
`rsl-rl-lib` 5.5.1 is in the home PC's Isaac Lab environment.

## Decision

**RL where it pays, by skill:**

| Skill | Method | Why |
| --- | --- | --- |
| Omni-wheel motion | Classical kinematics, no RL | Three-wheel omni inverse kinematics is closed form: exact, cheap and testable |
| Reach, approach, dock | RL | The success test is simple (distance, alignment, contact) and needs no demonstrations |
| Grasp and lift | RL plus imitation | RL in simulation first; demonstrations refine it once the arms exist |
| Pick and place | ACT first | The same imitation path as the SO-101; RL only where ACT falls short |

**Where it runs:**

- Isaac Lab 3.0 with `rsl_rl` PPO on the home PC, on native Windows.
- Training runs as the owner's **user processes**, never through CI, a workflow or the runner
  service. The runner service stays dedicated to trusted CI jobs
  ([ADR 0020](0020-self-hosted-gpu-runner.md)).

**A queue runner that yields to the gate.** Training jobs run from a queue, one at a time. Before
each job, and at every checkpoint, the runner checks three conditions:

- a `PAUSE` file exists;
- a `Runner.Worker` process is alive, which means a CI job holds the runner;
- free VRAM or free commit charge is below its floor.

When any condition holds, the runner saves a checkpoint, stops the job, and waits. It resumes
from that checkpoint once all three clear. The gate always wins the GPU. The floor values are
measured on this PC and recorded in [isaac.md](../knowledge/isaac.md).

**Judged by the task, never by the reward.**

- Every checkpoint that is a candidate goes through the `piperobot` gate on fixed seeds: task
  success as a binomial outcome per episode, compared with the stored baseline, exactly like an
  SO-101 policy ([ADR 0003](0003-statistical-gate-wilson-newcombe.md)).
- The task's success test is written before training and is separate from the reward function. A
  rising reward with a flat task success rate is a reward-hacking signal, not progress.
- The training reward is logged as a diagnostic only.

**Privacy.** The crab's RL code and its tasks, rewards, checkpoints and results stay in the
private crab repository, which installs this repository's `piperobot` package
([ADR 0019](0019-core-adapters-robots-layout.md)). Nothing crab-specific comes here. The gate
code stays generic ([ADR 0015](0015-generic-core-vs-robot-specific.md)).

## Alternatives considered

- **MuJoCo Playground on JAX.** It has fast GPU-parallel RL and good examples, but JAX's CUDA
  builds run on Linux, so on this PC it needs WSL2. The crab would also get a second simulator
  next to the Isaac Lab stack the SO-101 already uses.
- **The Open Duck route** (MuJoCo Playground training for a small legged robot, on Linux or
  WSL): proven for legged locomotion. The crab has a wide wheeled base and no legs in v1, so it
  is the wrong problem, and the same Linux/WSL cost applies.
- **Imitation only.** It is the existing plan, but it needs demonstrations, and so hardware that
  cannot be bought before the Phase 0 gate. RL in simulation can start now.
- **RL for locomotion too.** Omni-wheel kinematics has an exact answer. A learned controller
  would be slower to train, harder to verify and no better.
- **Training through the self-hosted runner** (a workflow per training run). It gives CI-grade
  logs, but a 36-hour job would hold the runner and block the required SO-101 gate. It would also
  put long-lived, untested training code in the trusted CI path.

## Consequences

- Crab skills can start learning before any crab hardware exists. Reach, approach and dock
  results arrive first.
- The GPU is shared under a strict rule: when CI needs it, training pauses. A training weekend
  can therefore lose hours to gate runs; the queue resumes from checkpoints, so nothing is
  repeated.
- Every RL result is a gate verdict on task success, so a policy that games its reward is
  blocked like any other regression.
- Reward functions and success tests are two artifacts to review per task, not one.
- Two new costs to watch: disk for checkpoints, and wear from long GPU runs (temperature and
  power).
- If RL needs Linux-only tools later (JAX, multi-GPU), that is a new ADR.
