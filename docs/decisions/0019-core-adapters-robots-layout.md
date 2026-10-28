# 0019. Three layers: generic core, framework adapters, and one folder per robot

- Status: Proposed
- Date: 2026-10-28

## Context

[0015](0015-generic-core-vs-robot-specific.md) drew the line between the generic core and
robot-specific code, but kept the folders "as they are for now, while there is a single robot".
That is no longer true. The repo already serves three "robots": the mock, PushT
([0016](0016-real-evaluator-lerobot-pusht.md)) and the SO-101 (envs and datasets), and
[Project Cangrejo](../cangrejo/README.md) adds a fourth with its own tasks, scenarios and
hardware. What is misplaced today:

- `eval/` mixes the results contract (`results.py`, core) with evaluators (`mock_eval.py`,
  `lerobot_eval.py`, `lerobot_policy.py`, `dataset_stats.py`).
- `eval/lerobot_eval.py` and `eval/lerobot_policy.py` are not SO-101 code: they run any LeRobot
  policy in any LeRobot simulator. The crab will use them too (LeKiwi-style LeRobot robot).
- `stats/baseline.json` and `stats/baselines/*.json` are per-policy data inside the core.
- `envs/` describes only the SO-101 tube-to-rack task; `policies/` is a flat list.
- `pyproject.toml` is still named `so101-policy-ci`, with an SO-101 description.
- `tests/test_architecture.py` lists forbidden imports, and the list is already stale: it misses
  `eval.lerobot_eval` and `eval.lerobot_policy`, added after the test.
- `pr-gate.yml` hardcodes one policy and one baseline.

## Decision

Three layers, each importing only the layers above it:

```
piperobot/                 # 1. Core: stdlib only. The future standalone library.
  results.py               #    results contract
  stats/                   #    gate, baseline loading, CLI inputs
  reports/                 #    PR comment, sticky comment
adapters/                  # 2. Framework adapters: robot-agnostic, may import LeRobot/Isaac/MuJoCo.
  lerobot/                 #    lerobot_eval.py, lerobot_policy.py, dataset_stats.py
  mock/                    #    mock_eval.py
robots/                    # 3. Robots: data and configuration, little or no code.
  mock/                    #    policy spec, baseline, gate manifest
  pusht/                   #    pusht-vqbet.json, baselines/, gate manifest
  so101/                   #    envs/ (tube-to-rack), policies/, baselines/, gate manifest
  cangrejo/                #    description/ (URDF/MJCF), envs/, scenarios, gate manifest
```

- **Gate manifest per robot** (`robots/<robot>/gate.toml`): one entry per task with the policy
  spec, the evaluator command, the baseline file, episodes and seeds. The core reads manifests;
  it never imports adapters, it runs the evaluator command and reads the results file.
- **One `pr-gate` job that always reports.** It decides from the changed paths which robots and
  tasks to evaluate, runs them, and posts one comment with a section per task; the verdict is the
  worst one. A matrix would rename the required check (`pr-gate (so101)`), and per-robot path
  filters would leave a required check pending forever.
- **Allow-list architecture test**: `piperobot/` may import only the standard library and
  `piperobot`; `adapters/` may not import `robots/`. An allow-list cannot go stale when modules
  are added.
- Rename the project in `pyproject.toml` to `piperobot`.
- Migrate in small PRs (`git mv` plus import updates, tests green at each step), in this order:
  core, adapters, robots, manifest and workflow. The real `pr-gate` validates every step.

## Alternatives considered

- Keep the folders and only extend the deny-list: cheap today, but every new robot and adapter
  mixes into the same folders, and the list rots (it already has).
- One package per robot right away (separate `pyproject.toml` each): premature; one lock and one
  CI are enough for one person.
- Robot code inside the adapters (`adapters/lerobot/so101.py`): couples the robots to one
  framework, while the crab may mix LeRobot (hardware) with MuJoCo or Isaac (simulation).

## Consequences

- Adding a robot means adding a folder under `robots/` and, only if it needs a new framework, an
  adapter. The core and the report do not change.
- Contract changes the crab will need, not part of this ADR:
  - several tasks per PR, so several results files per run;
  - fault-injection scenarios ("must fail safely"), whose outcome is not a plain success;
  - a platform block (CPU model, device, versions) in the results file, which a paired same-seed
    comparison needs ([lerobot.md](../knowledge/lerobot.md)).
- Open: where the crab's CAD exports and meshes live (in `robots/cangrejo/description/`, Git LFS,
  or the Hugging Face Hub), and under which license the hardware design is published (Apache-2.0
  covers code, not hardware designs).
