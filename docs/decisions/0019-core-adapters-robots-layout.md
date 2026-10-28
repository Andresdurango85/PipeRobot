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
    lerobot/               #     evaluate.py, policy.py
    mock/                  #     evaluate.py
robots/                    # Robots whose files are public. Data and configuration, little code.
  mock/                    #   policy spec and baseline (a test fixture, not gated)
  pusht/                   #   policies/, baselines/
  so101/                   #   envs/ (tube-to-rack), tools/dataset_stats.py
```

Modules are named `evaluate.py`, not `eval.py`, which would shadow the builtin when imported by
name. `dataset_stats.py` is a developer tool with an SO-101 default, so it stays out of the
package.

- **Core**: `piperobot/` except `piperobot/adapters/`. Standard library and core modules only.
  It never names a robot or a data file: every baseline is passed explicitly.
- **Adapters**: may import the core and their framework (LeRobot, later Isaac or MuJoCo), never
  `robots/`. Shipped in the same package, with the framework behind an extra, so another repo can
  install the core plus the adapter it needs.
- **Robots**: one folder each, holding data and configuration only. Folders that would be empty
  are not created. The crab is not here: its private repo holds its description, scenarios and
  workflow and installs `piperobot` from this repo.
- **Architecture test**: layers are found by module prefix (`pkgutil.walk_packages`), relative
  imports are resolved, and the test fails when a layer is empty or a module belongs to no layer.
  Today's globs would turn into a silent skip once the folders move.
- **Packaging**: tests import the built package, not the source tree (no `pytest` `pythonpath`),
  and CI builds the wheel and imports every module in a clean environment without extras, so an
  eager `import lerobot` or a missing file shows up before a consumer hits it. Extras use version
  ranges; this repo's lock keeps the exact pins. The PushT simulator deps become a dependency
  group, which is not published, instead of a robot-named extra.
- **Migration in three PRs**, tests green and `pr-gate` passing at each step:
  1. Allow-list architecture test on the current layout; the core loses its default baseline.
  2. Data into `robots/` (policy specs, baselines, envs), so it moves only once.
  3. The package: core and adapters under `piperobot/`, build backend, clean-install check.

  Each PR updates the `python -m` paths and the `actions/cache` `hashFiles` keys of the files it
  moves (`hashFiles` silently ignores a missing path, which would reuse a stale prepared policy),
  and dispatches `baseline.yml` with 50 episodes after merging, since no PR runs it. Old ADRs may
  get link-only path fixes; their text does not change.
- **Deferred until a second public task is gated**: gate manifests, choosing robots by changed
  paths, and one comment with a section per task. Today PushT is the only gated public task, so
  the existing `pr-gate` job stays as it is. When they come: a single job still named `pr-gate`
  that always reports (a matrix renames the check, path filters leave it pending), treats
  `uv.lock`, `pyproject.toml` and the workflow as changes to every robot, decides robots before
  installing extras, overwrites a stale comment when no robot is selected, orders verdicts as
  unusable data > BLOCK > WARN > PASS, gives each task its own work directory, and fails when a
  PR removes or weakens a task of the base branch.

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
- Making the repo installable needs a build backend in `pyproject.toml`; `uv_build` expects a
  `src/` layout by default (to verify against the current uv docs when the package step starts).
- A consumer does not inherit this repo's uv settings: the Pillow override (ADR 0012) and the
  CPU torch index (ADR 0017) must be declared again in the crab's repo.
- With no required review ([0018](0018-no-required-review-for-the-owner.md)), a PR can weaken
  its own gate by editing `pr-gate.yml` or a baseline, and still merge. The guard against a task
  being removed or weakened comes with the manifests; until then, read those diffs in every PR.
