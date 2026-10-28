# 0019. Three layers: an installable core, framework adapters, and one folder per robot

- Status: Accepted
- Date: 2026-10-28

## Context

[0015](0015-generic-core-vs-robot-specific.md) drew the line between the generic core and
robot-specific code, but kept the folders "as they are for now, while there is a single robot".
That is no longer true. The repo already serves three "robots": the mock, PushT
([0016](0016-real-evaluator-lerobot-pusht.md)) and the SO-101 (envs and datasets).
[Project Cangrejo](../cangrejo/README.md) adds a fourth whose design files are private, so its
gate cannot run here: PR artifacts and videos of this repo are public. It runs in the crab's
private repo, which makes it the first consumer of the gate from outside this repo.

What is misplaced today:

- `eval/` mixes the results contract (`results.py`, core) with evaluators (`mock_eval.py`,
  `lerobot_eval.py`, `lerobot_policy.py`, `dataset_stats.py`).
- `eval/lerobot_eval.py` and `eval/lerobot_policy.py` are not SO-101 code: they run any LeRobot
  policy in any LeRobot simulator. The crab will use them too (a LeKiwi-style LeRobot robot).
- `stats/baseline.json` and `stats/baselines/*.json` are per-policy data inside the core, and
  `stats/baseline.py` defaults to the mock's baseline file.
- `envs/` describes only the SO-101 tube-to-rack task; `policies/` is a flat list.
- `pyproject.toml` is `so101-policy-ci` with `package = false`: nothing can be installed from
  another repo.
- `tests/test_architecture.py` lists forbidden imports, and the list is already stale: it misses
  `eval.lerobot_eval` and `eval.lerobot_policy`, added after the test.
- `pr-gate.yml` hardcodes one policy and one baseline.

## Decision

```
piperobot/                 # The installable package (`piperobot` distribution).
  results.py               #   core: results contract
  stats/                   #   core: gate, baseline loading, CLI inputs
  reports/                 #   core: PR comment, sticky comment
  adapters/                #   robot-agnostic framework adapters, behind extras
    lerobot/               #     eval.py, policy.py, dataset_stats.py
    mock/                  #     eval.py
robots/                    # Robots whose files are public. Data and configuration, little code.
  mock/                    #   policy spec, baseline, gate manifest (tests and demos only)
  pusht/                   #   policies/, baselines/, gate manifest
  so101/                   #   envs/ (tube-to-rack), policies/, baselines/, gate manifest
```

- **Core**: `piperobot/` except `piperobot/adapters/`. Standard library and core modules only.
  It never names a robot or a data file: every baseline is passed explicitly.
- **Adapters**: may import the core and their framework (LeRobot, later Isaac or MuJoCo), never
  `robots/`. Shipped in the same package, with the framework behind an extra, so another repo can
  install the core plus the adapter it needs.
- **Robots**: one folder each, with a gate manifest (`gate.toml`) listing per task the policy spec,
  the evaluator command, the baseline file, episodes and seeds. The crab is not here: its private
  repo holds its description, scenarios and manifest and installs `piperobot` from this repo.
- **Architecture test as an allow-list**, per layer, so it cannot go stale as modules are added.
- **One `pr-gate` job that always reports.** It reads the manifests, evaluates the robots whose
  files changed (all of them when the package changed), and posts one comment with a section per
  task; the verdict is the worst one. A matrix would rename the required check
  (`pr-gate (so101)`), and per-robot path filters would leave a required check pending forever.
- **Migration in small PRs**, tests green and `pr-gate` passing at each step: first the test and
  the core default, then the package, the adapters, the robots, and last the manifest and the
  workflow. Old ADRs may get link-only path fixes; their text does not change.

## Alternatives considered

- Keep the folders and extend the deny-list: cheap today, but every new robot and adapter mixes
  into the same folders, and the list rots (it already has).
- Adapters as a separate top-level package: cleaner imports, but two packages to install and
  version for one person; an extra per framework keeps the install light.
- The crab inside this repo with its design files fetched from the private repo by a CI token:
  its videos and artifacts would still be public, and the token would sit in a public repo's CI.
- One package per robot right away: premature; one lock and one CI are enough for one person.

## Consequences

- Adding a public robot means a folder under `robots/` and, only for a new framework, an adapter.
- The crab's private repo depends on `piperobot` from git, pinned to a commit or tag: the gate is
  used as a library from day one, which tests that it really is generic.
- Contract changes the crab will need, not part of this ADR:
  - several tasks per PR, so several results files per run;
  - fault-injection scenarios ("must fail safely"), whose outcome is not a plain success;
  - a platform block (CPU model, device, versions) in the results file, which a paired same-seed
    comparison needs ([lerobot.md](../knowledge/lerobot.md)).
- Making the repo installable needs a build backend in `pyproject.toml` (to verify against the
  current uv docs when the package step starts).
